#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <string>
#include <utility>
#include <vector>

namespace stage_a::read_fixture_head {

using Nonce = std::array<std::uint8_t, 16>;
using P10Digest = std::array<std::uint8_t, 32>;

inline constexpr std::size_t request_bytes = 64;
inline constexpr std::size_t error_response_bytes = 66;
inline constexpr std::size_t active_p11_bytes = 299;
inline constexpr std::size_t terminal_p11_bytes = 300;
inline constexpr std::size_t maximum_response_bytes = 366;

enum class Failure {
    none,
    malformed,
    correlation_mismatch,
    read_incomplete,
    invalid_trusted_input,
    internal_failure
};

class RequestValidation final {
public:
    [[nodiscard]] Failure failure() const noexcept { return failure_; }
    [[nodiscard]] std::optional<Nonce> nonce() const noexcept { return nonce_; }
    [[nodiscard]] bool ok() const noexcept { return failure_ == Failure::none && nonce_.has_value(); }
private:
    RequestValidation(Failure failure, std::optional<Nonce> nonce) noexcept
        : failure_(failure), nonce_(nonce) {}
    Failure failure_;
    std::optional<Nonce> nonce_; // only after structure and P10 assertion validation
    friend RequestValidation validate_request(std::span<const std::uint8_t>,
                                              const P10Digest&) noexcept;
};

class ResponseValidation final {
public:
    [[nodiscard]] Failure failure() const noexcept { return failure_; }
    [[nodiscard]] std::string verified_p11() const { return verified_p11_; }
    [[nodiscard]] bool ok() const noexcept { return failure_ == Failure::none; }
private:
    ResponseValidation(Failure failure, std::string verified_p11) noexcept
        : failure_(failure), verified_p11_(std::move(verified_p11)) {}
    const Failure failure_;
    const std::string verified_p11_; // only after structure, echoes and selected payload equality
    friend ResponseValidation validate_response(
        std::span<const std::uint8_t>, const Nonce&, const P10Digest&,
        std::span<const std::uint8_t>, std::size_t) noexcept;
};

struct SuccessEncoding {
    Failure failure = Failure::invalid_trusted_input;
    std::vector<std::uint8_t> bytes;
    [[nodiscard]] bool ok() const noexcept { return failure == Failure::none; }
};

// The caller supplies the 16 raw nonce bytes and 32 raw trusted P10 hash.
// This pure unit never generates randomness, loads a seal or selects a case.
std::array<std::uint8_t, request_bytes> encode_request(
    const Nonce& nonce, const P10Digest& trusted_p10) noexcept;

// A3-side structural validation; the expected P10 digest is independently trusted.
// No generic request dispatcher or uncorrelated decoder is exposed.
RequestValidation validate_request(std::span<const std::uint8_t> wire,
                                   const P10Digest& trusted_p10) noexcept;

// A3-side wire encoding only. The caller must first obtain exact canonical
// bytes from its separately accepted protected P11 custody reader.
SuccessEncoding encode_verified_success_response(
    const Nonce& nonce, const P10Digest& trusted_p10,
    std::span<const std::uint8_t> verified_canonical_p11) noexcept;
std::array<std::uint8_t, error_response_bytes> encode_generic_error_response(
    const Nonce& nonce, const P10Digest& trusted_p10) noexcept;

// A2-side validation. The selected canonical P11 bytes and explicit length are
// trusted caller inputs; a response cannot select or manufacture them.
ResponseValidation validate_response(
    std::span<const std::uint8_t> wire, const Nonce& invocation_nonce,
    const P10Digest& trusted_p10,
    std::span<const std::uint8_t> selected_canonical_p11,
    std::size_t selected_expected_length) noexcept;

} // namespace stage_a::read_fixture_head
