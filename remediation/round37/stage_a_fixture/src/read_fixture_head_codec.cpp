#include "read_fixture_head_codec.hpp"

#include <algorithm>
#include <utility>

namespace stage_a::read_fixture_head {
namespace {
constexpr std::uint8_t magic[4] = {'S', '1', 'R', 'H'};
constexpr std::uint16_t version = 1;
constexpr std::uint16_t request_kind = 0x0001;
constexpr std::uint16_t success_kind = 0x8001;
constexpr std::uint16_t error_kind = 0x8002;
constexpr std::uint16_t operation = 0x0001;
constexpr std::size_t prefix_bytes = 66;

void put16(std::uint8_t* out, std::uint16_t value) noexcept {
    out[0] = static_cast<std::uint8_t>(value);
    out[1] = static_cast<std::uint8_t>(value >> 8);
}
void put32(std::uint8_t* out, std::uint32_t value) noexcept {
    for (unsigned i = 0; i < 4; ++i) out[i] = static_cast<std::uint8_t>(value >> (8u * i));
}
std::uint16_t get16(const std::uint8_t* in) noexcept {
    return static_cast<std::uint16_t>(in[0]) |
           static_cast<std::uint16_t>(static_cast<std::uint16_t>(in[1]) << 8);
}
std::uint32_t get32(const std::uint8_t* in) noexcept {
    return static_cast<std::uint32_t>(in[0]) |
           (static_cast<std::uint32_t>(in[1]) << 8) |
           (static_cast<std::uint32_t>(in[2]) << 16) |
           (static_cast<std::uint32_t>(in[3]) << 24);
}
bool fixed_header(std::span<const std::uint8_t> wire) noexcept {
    return wire.size() >= 12 && std::equal(magic, magic + 4, wire.data()) &&
           get16(wire.data() + 4) == version;
}
void write_header(std::uint8_t* out, std::uint16_t kind, std::uint32_t total) noexcept {
    std::copy(magic, magic + 4, out);
    put16(out + 4, version);
    put16(out + 6, kind);
    put32(out + 8, total);
}
void write_common_response(std::uint8_t* out, std::uint16_t kind,
                           std::uint32_t total, std::uint16_t status,
                           const Nonce& nonce, const P10Digest& p10,
                           std::uint16_t payload_size) noexcept {
    write_header(out, kind, total);
    put16(out + 12, operation);
    put16(out + 14, status);
    std::copy(nonce.begin(), nonce.end(), out + 16);
    std::copy(p10.begin(), p10.end(), out + 32);
    put16(out + 64, payload_size);
}
} // namespace

std::array<std::uint8_t, request_bytes> encode_request(
    const Nonce& nonce, const P10Digest& trusted_p10) noexcept {
    std::array<std::uint8_t, request_bytes> out{};
    write_header(out.data(), request_kind, static_cast<std::uint32_t>(request_bytes));
    put16(out.data() + 12, operation);
    put16(out.data() + 14, 0);
    std::copy(nonce.begin(), nonce.end(), out.begin() + 16);
    std::copy(trusted_p10.begin(), trusted_p10.end(), out.begin() + 32);
    return out;
}

RequestValidation validate_request(std::span<const std::uint8_t> wire,
                                   const P10Digest& trusted_p10) noexcept {
    if (wire.size() != request_bytes || !fixed_header(wire) ||
        get16(wire.data() + 6) != request_kind ||
        get32(wire.data() + 8) != request_bytes ||
        get16(wire.data() + 12) != operation || get16(wire.data() + 14) != 0)
        return {Failure::malformed, std::nullopt};
    if (!std::equal(trusted_p10.begin(), trusted_p10.end(), wire.data() + 32))
        return {Failure::correlation_mismatch, std::nullopt};
    Nonce nonce{};
    std::copy_n(wire.data() + 16, nonce.size(), nonce.begin());
    return {Failure::none, nonce};
}

SuccessEncoding encode_verified_success_response(
    const Nonce& nonce, const P10Digest& trusted_p10,
    std::span<const std::uint8_t> verified_canonical_p11) noexcept {
    if (verified_canonical_p11.size() != active_p11_bytes &&
        verified_canonical_p11.size() != terminal_p11_bytes)
        return {Failure::invalid_trusted_input, {}};
    try {
        std::vector<std::uint8_t> out(prefix_bytes + verified_canonical_p11.size());
        write_common_response(out.data(), success_kind,
                              static_cast<std::uint32_t>(out.size()), 0,
                              nonce, trusted_p10,
                              static_cast<std::uint16_t>(verified_canonical_p11.size()));
        std::copy(verified_canonical_p11.begin(), verified_canonical_p11.end(),
                  out.begin() + prefix_bytes);
        return {Failure::none, std::move(out)};
    } catch (...) { return {Failure::internal_failure, {}}; }
}

std::array<std::uint8_t, error_response_bytes> encode_generic_error_response(
    const Nonce& nonce, const P10Digest& trusted_p10) noexcept {
    std::array<std::uint8_t, error_response_bytes> out{};
    write_common_response(out.data(), error_kind,
                          static_cast<std::uint32_t>(error_response_bytes), 1,
                          nonce, trusted_p10, 0);
    return out;
}

ResponseValidation validate_response(
    std::span<const std::uint8_t> wire, const Nonce& invocation_nonce,
    const P10Digest& trusted_p10,
    std::span<const std::uint8_t> selected_canonical_p11,
    std::size_t selected_expected_length) noexcept {
    if ((selected_expected_length != active_p11_bytes &&
         selected_expected_length != terminal_p11_bytes) ||
        selected_canonical_p11.size() != selected_expected_length)
        return {Failure::invalid_trusted_input, {}};
    if (wire.size() < prefix_bytes || wire.size() > maximum_response_bytes ||
        !fixed_header(wire) || get32(wire.data() + 8) != wire.size() ||
        get16(wire.data() + 12) != operation)
        return {Failure::malformed, {}};
    const auto kind = get16(wire.data() + 6);
    const auto status = get16(wire.data() + 14);
    const auto payload_length = get16(wire.data() + 64);
    const bool is_error = kind == error_kind && status == 1 &&
                          wire.size() == error_response_bytes && payload_length == 0;
    const bool is_success = kind == success_kind && status == 0 &&
                            (payload_length == active_p11_bytes ||
                             payload_length == terminal_p11_bytes) &&
                            wire.size() == prefix_bytes + payload_length;
    if (!is_error && !is_success) return {Failure::malformed, {}};
    if (!std::equal(invocation_nonce.begin(), invocation_nonce.end(), wire.data() + 16) ||
        !std::equal(trusted_p10.begin(), trusted_p10.end(), wire.data() + 32))
        return {Failure::correlation_mismatch, {}};
    if (is_error) return {Failure::read_incomplete, {}};
    if (payload_length != selected_expected_length ||
        !std::equal(selected_canonical_p11.begin(), selected_canonical_p11.end(),
                    wire.data() + prefix_bytes))
        return {Failure::correlation_mismatch, {}};
    try {
        return {Failure::none,
                std::string(reinterpret_cast<const char*>(wire.data() + prefix_bytes),
                            selected_expected_length)};
    } catch (...) { return {Failure::internal_failure, {}}; }
}

} // namespace stage_a::read_fixture_head
