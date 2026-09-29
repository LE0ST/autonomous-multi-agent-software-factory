#include "../src/read_fixture_head_codec.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

using namespace stage_a::read_fixture_head;
namespace {
int checks = 0;
void check(bool yes, const char* why) { ++checks; if (!yes) throw std::runtime_error(why); }

std::uint8_t nybble(char c) {
    if (c >= '0' && c <= '9') return static_cast<std::uint8_t>(c - '0');
    if (c >= 'A' && c <= 'F') return static_cast<std::uint8_t>(c - 'A' + 10);
    if (c >= 'a' && c <= 'f') return static_cast<std::uint8_t>(c - 'a' + 10);
    throw std::runtime_error("bad independent test hex");
}
std::vector<std::uint8_t> literal_hex(std::string_view hex) {
    std::vector<std::uint8_t> out;
    int high = -1;
    for (char c : hex) {
        if (c == ' ' || c == '\n' || c == '\r' || c == '\t') continue;
        const auto digit = nybble(c);
        if (high < 0) high = digit;
        else { out.push_back(static_cast<std::uint8_t>((high << 4) | digit)); high = -1; }
    }
    if (high >= 0) throw std::runtime_error("odd independent test hex");
    return out;
}
std::vector<std::uint8_t> ascii(std::string_view value) {
    return {value.begin(), value.end()};
}

// These are transcribed from READ_FIXTURE_HEAD_WIRE_CONTRACT.md, not built by
// the production encoder, renderer, or response parser.
const std::vector<std::uint8_t> request = literal_hex(
    "53 31 52 48 01 00 01 00 40 00 00 00 01 00 00 00 "
    "00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F "
    "AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA "
    "AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA");
const std::vector<std::uint8_t> active_prefix = literal_hex(
    "53 31 52 48 01 00 01 80 6D 01 00 00 01 00 00 00 "
    "00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F "
    "AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA "
    "AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA 2B 01");
const std::vector<std::uint8_t> terminal_prefix = literal_hex(
    "53 31 52 48 01 00 01 80 6E 01 00 00 01 00 00 00 "
    "00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F "
    "AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA "
    "AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA 2C 01");
const std::vector<std::uint8_t> error = literal_hex(
    "53 31 52 48 01 00 02 80 42 00 00 00 01 00 01 00 "
    "00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F "
    "AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA "
    "AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA 00 00");
constexpr std::string_view active_p11 =
    R"({"schema_version":1,"marker":"S1PF-260926-A-STAGE-A-V1","p10_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","case_id":"spent-budget-active","latest_digest":"4d5d63027a1578256a003328664c48f1328cc5171ef29db4a9c0046b8ce4d22d","generation":1,"worker_runs":1,"terminal":false})";
constexpr std::string_view terminal_p11 =
    R"({"schema_version":1,"marker":"S1PF-260926-A-STAGE-A-V1","p10_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","case_id":"spent-budget-terminal","latest_digest":"eb2c260344d3c33075cb817a6ff8ce7c216b3a57dace342bb58fbe086ee33764","generation":2,"worker_runs":1,"terminal":true})";

std::vector<std::uint8_t> literal_success(const std::vector<std::uint8_t>& prefix,
                                          std::string_view body) {
    auto out = prefix;
    const auto payload = ascii(body);
    out.insert(out.end(), payload.begin(), payload.end());
    return out;
}
Nonce nonce() { Nonce value{}; for (std::uint8_t i = 0; i < value.size(); ++i) value[i] = i; return value; }
P10Digest p10() { P10Digest value{}; value.fill(0xaa); return value; }
void request_failure(const std::vector<std::uint8_t>& wire, Failure expected) {
    const auto result = validate_request(wire, p10());
    check(!result.ok() && result.failure() == expected && !result.nonce(),
          "request failure never exposes correlated nonce");
}
void response_failure(const std::vector<std::uint8_t>& wire, Failure expected,
                      std::string_view selected = active_p11) {
    const auto expected_bytes = ascii(selected);
    const auto result = validate_response(wire, nonce(), p10(), expected_bytes, expected_bytes.size());
    check(!result.ok() && result.failure() == expected && result.verified_p11().empty(),
          "response failure never exposes trusted P11");
}
} // namespace

int main() {
    try {
        static_assert(request_bytes == 64 && error_response_bytes == 66 &&
                      active_p11_bytes == 299 && terminal_p11_bytes == 300 &&
                      maximum_response_bytes == 366);
        static_assert(std::is_same_v<
                      decltype(std::declval<const ResponseValidation&>().verified_p11()),
                      std::string>, "verified P11 must be returned by owned value");
        static_assert(!std::is_assignable_v<ResponseValidation&, const ResponseValidation&>,
                      "validated result state cannot be replaced by assignment");
        const auto active = literal_success(active_prefix, active_p11);
        const auto terminal = literal_success(terminal_prefix, terminal_p11);
        check(request.size() == 64 && error.size() == 66 &&
              active_prefix.size() == 66 && terminal_prefix.size() == 66 &&
              active_p11.size() == 299 && terminal_p11.size() == 300 &&
              active.size() == 365 && terminal.size() == 366,
              "independent literal design lengths");
        check(request[0] == 0x53 && request[3] == 0x48 && request[4] == 1 &&
              request[6] == 1 && request[8] == 0x40 && request[12] == 1 &&
              request[14] == 0 && request[16] == 0 && request[31] == 15 &&
              request[32] == 0xaa && request[63] == 0xaa, "request literal offsets");
        check(active[6] == 1 && active[7] == 0x80 && active[8] == 0x6d &&
              active[9] == 1 && active[14] == 0 && active[64] == 0x2b &&
              active[65] == 1 && active[66] == '{' && active.back() == '}',
              "active literal offsets");
        check(terminal[8] == 0x6e && terminal[64] == 0x2c &&
              terminal[65] == 1 && terminal[66] == '{' && terminal.back() == '}',
              "terminal literal offsets");
        check(error[6] == 2 && error[7] == 0x80 && error[8] == 0x42 &&
              error[14] == 1 && error[64] == 0 && error[65] == 0,
              "generic error literal offsets");

        const auto encoded_request = encode_request(nonce(), p10());
        check(std::equal(encoded_request.begin(), encoded_request.end(), request.begin(), request.end()),
              "encoder matches independent 64-byte request literal");
        const auto validated_request = validate_request(request, p10());
        check(validated_request.ok() && validated_request.nonce() == nonce(),
              "independent request validates only after P10 assertion");
        const auto active_bytes = ascii(active_p11);
        const auto terminal_bytes = ascii(terminal_p11);
        const auto active_encoded = encode_verified_success_response(nonce(), p10(), active_bytes);
        const auto terminal_encoded = encode_verified_success_response(nonce(), p10(), terminal_bytes);
        check(active_encoded.ok() && active_encoded.bytes == active, "active encoder matches independent literal");
        check(terminal_encoded.ok() && terminal_encoded.bytes == terminal, "terminal encoder matches independent literal");
        const auto encoded_error = encode_generic_error_response(nonce(), p10());
        check(std::equal(encoded_error.begin(), encoded_error.end(), error.begin(), error.end()),
              "generic error encoder matches independent literal");
        const auto av = validate_response(active, nonce(), p10(), active_bytes, 299);
        const auto tv = validate_response(terminal, nonce(), p10(), terminal_bytes, 300);
        check(av.ok() && av.verified_p11() == active_p11, "active exact literal response accepted");
        check(tv.ok() && tv.verified_p11() == terminal_p11, "terminal exact literal response accepted");
        auto active_copy = av.verified_p11();
        active_copy[0] ^= 1;
        check(active_copy != active_p11, "caller can modify its active P11 copy");
        check(av.ok() && av.verified_p11() == active_p11,
              "active validation and stored P11 survive caller copy mutation");
        check(av.verified_p11() == active_p11,
              "repeated active accessor returns original verified bytes");
        auto terminal_copy = tv.verified_p11();
        terminal_copy[0] ^= 1;
        check(terminal_copy != terminal_p11, "caller can modify its terminal P11 copy");
        check(tv.ok() && tv.verified_p11() == terminal_p11,
              "terminal validation and stored P11 survive caller copy mutation");
        check(tv.verified_p11() == terminal_p11,
              "repeated terminal accessor returns original verified bytes");
        auto move_source = validate_response(active, nonce(), p10(), active_bytes, 299);
        auto moved_result = std::move(move_source);
        check(move_source.ok() && move_source.verified_p11() == active_p11,
              "moving a result preserves its source validation state");
        check(moved_result.ok() && moved_result.verified_p11() == active_p11,
              "move construction preserves validated P11 in the new result");
        response_failure(error, Failure::read_incomplete);

        // Literal malformed cases from the controlling design.
        { auto v=request; v[4]=2; request_failure(v,Failure::malformed); }
        { auto v=request; v[12]=2; request_failure(v,Failure::malformed); }
        { auto v=request; v[14]=1; request_failure(v,Failure::malformed); }
        { auto v=request; v[8]=0x41; v.push_back(0); request_failure(v,Failure::malformed); }
        { auto v=request; v.pop_back(); request_failure(v,Failure::malformed); }
        { auto v=active; v[16]=1; response_failure(v,Failure::correlation_mismatch); }
        { auto v=active; v[32]=0xab; response_failure(v,Failure::correlation_mismatch); }
        response_failure(active,Failure::correlation_mismatch,terminal_p11);
        { auto v=active; v[8]=0x6e; response_failure(v,Failure::malformed); }
        { auto v=active; v[64]=0x2c; response_failure(v,Failure::malformed); }
        { auto v=active; v[6]=3; response_failure(v,Failure::malformed); }

        for (std::size_t size : {0u,1u,11u,12u,63u,65u}) {
            std::vector<std::uint8_t> v(request.begin(), request.begin() + (std::min)(size,request.size()));
            if (size > request.size()) v.push_back(0x7e);
            request_failure(v,Failure::malformed);
        }
        { auto v=request; v[0]^=1; request_failure(v,Failure::malformed); }
        { auto v=error; v[14]=0; response_failure(v,Failure::malformed); }
        for (std::size_t size : {0u,1u,11u,12u,63u,64u,65u,66u,364u,367u}) {
            std::vector<std::uint8_t> v(active.begin(), active.begin() + (std::min)(size,active.size()));
            if (size > active.size()) v.insert(v.end(),size-active.size(),0x7e);
            response_failure(v,Failure::malformed);
        }
        { auto v=active; v.push_back(0x7e); response_failure(v,Failure::malformed); }
        { auto v=terminal; v.push_back(0x93); response_failure(v,Failure::malformed); }
        { auto v=error; v.push_back(0x7e); response_failure(v,Failure::malformed); }
        std::uint32_t trail_seed=0x91e10da5u;
        for (int i=0;i<32;++i) {
            trail_seed ^= trail_seed << 13;
            trail_seed ^= trail_seed >> 17;
            trail_seed ^= trail_seed << 5;
            const auto extra=static_cast<std::uint8_t>(trail_seed);
            auto q=request; q.push_back(extra); request_failure(q,Failure::malformed);
            auto r=active; r.push_back(extra); response_failure(r,Failure::malformed);
        }
        { auto v=error; v[64]=1; response_failure(v,Failure::malformed); }
        { auto v=error; v[6]=1; response_failure(v,Failure::malformed); }
        { auto v=error; v[16]^=1; response_failure(v,Failure::correlation_mismatch); }
        { auto v=error; v[32]^=1; response_failure(v,Failure::correlation_mismatch); }
        { auto v=active; v[66]^=1; response_failure(v,Failure::correlation_mismatch); }
        response_failure(terminal,Failure::correlation_mismatch,active_p11);
        { auto v=active; v.push_back(' '); v[8]=0x6e; v[64]=0x2c;
          response_failure(v,Failure::correlation_mismatch); }
        { auto v=active_bytes; v.push_back('x'); v.push_back('y');
          const auto x=encode_verified_success_response(nonce(),p10(),v);
          check(!x.ok() && x.failure==Failure::invalid_trusted_input && x.bytes.empty(),
                "encoder refuses noncanonical length"); }
        { const auto x=validate_response(active,nonce(),p10(),active_bytes,300);
          check(!x.ok() && x.failure()==Failure::invalid_trusted_input && x.verified_p11().empty(),
                "selected trusted length must match selected bytes"); }

        // Every fixed header byte is independently corrupted in an otherwise
        // literal vector. Echo and payload mutations must be correlation faults.
        for (std::size_t offset=0;offset<16;++offset) {
            auto v=request; v[offset]^=0x01; request_failure(v,Failure::malformed);
            auto r=active; r[offset]^=0x01; response_failure(r,Failure::malformed);
        }
        for (std::size_t offset=16;offset<64;++offset) {
            auto r=active; r[offset]^=0x01;
            response_failure(r,Failure::correlation_mismatch);
        }
        for (std::size_t offset=32;offset<64;++offset) {
            auto q=request; q[offset]^=0x01;
            request_failure(q,Failure::correlation_mismatch);
        }
        for (std::size_t offset=16;offset<32;++offset) {
            auto q=request; q[offset]^=0x01;
            const auto result=validate_request(q,p10());
            check(result.ok() && result.nonce()->at(offset-16)==q[offset],
                  "request nonce bytes are opaque and returned only after P10 check");
        }
        for (std::size_t offset=64;offset<66;++offset) {
            auto r=active; r[offset]^=0x01; response_failure(r,Failure::malformed);
        }
        for (std::size_t offset=0;offset<16;++offset) {
            auto r=error; r[offset]^=0x01; response_failure(r,Failure::malformed);
        }
        for (std::size_t offset=66;offset<active.size();++offset) {
            auto r=active; r[offset]^=0x01;
            response_failure(r,Failure::correlation_mismatch);
        }

        for (std::uint8_t fill : {std::uint8_t{0},std::uint8_t{0xff}}) {
            Nonce n{}; n.fill(fill);
            P10Digest p{}; p.fill(fill);
            const auto raw=encode_request(n,p);
            const auto rq=validate_request(raw,p);
            check(rq.ok() && rq.nonce()==n, "all-zero/all-FF values are opaque request data");
            const auto answer=encode_verified_success_response(n,p,active_bytes);
            check(answer.ok(), "opaque values do not block success encoding");
            const auto rs=validate_response(answer.bytes,n,p,active_bytes,299);
            check(rs.ok() && rs.verified_p11()==active_p11,
                  "all-zero/all-FF values are opaque correlation data");
        }
        std::cout << "read fixture head codec synthetic checks: " << checks << " passed\n";
        return 0;
    } catch (const std::exception& failure) {
        std::cerr << "read fixture head codec failure after " << checks << " checks: " << failure.what() << '\n';
        return 1;
    }
}
