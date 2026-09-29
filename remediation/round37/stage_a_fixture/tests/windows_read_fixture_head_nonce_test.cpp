#include "windows_read_fixture_head_nonce_test_port.hpp"

#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string_view>
#include <type_traits>
#include <utility>

using namespace stage_a::read_fixture_head;
namespace {
int checks = 0;
void check(bool yes, const char* why) { ++checks; if (!yes) throw std::runtime_error(why); }

enum class Mode { return_status, throw_standard, throw_nonstandard };
struct Probe {
    int calls = 0;
    BCRYPT_ALG_HANDLE algorithm = reinterpret_cast<BCRYPT_ALG_HANDLE>(1);
    ULONG length = 0;
    ULONG flags = 0;
    Mode mode = Mode::return_status;
    NTSTATUS status = 0;
    Nonce bytes{};
};
Probe* active_probe = nullptr;

NTSTATUS WINAPI fake_random(BCRYPT_ALG_HANDLE algorithm, PUCHAR output,
                            ULONG length, ULONG flags) {
    auto& probe = *active_probe;
    ++probe.calls;
    probe.algorithm = algorithm;
    probe.length = length;
    probe.flags = flags;
    if (probe.mode == Mode::throw_standard) throw std::runtime_error("synthetic RNG exception");
    if (probe.mode == Mode::throw_nonstandard) throw 29;
    for (std::size_t i = 0; i < probe.bytes.size(); ++i) output[i] = probe.bytes[i];
    return probe.status;
}

void exact_call(const Probe& probe) {
    check(probe.calls == 1, "one native-call attempt per invocation");
    check(probe.algorithm == nullptr, "null algorithm handle");
    check(probe.length == 16, "exact 16-byte output length");
    check(probe.flags == BCRYPT_USE_SYSTEM_PREFERRED_RNG, "exact system-preferred RNG flag");
}
void success_pattern(const Nonce& bytes, NTSTATUS status = 0) {
    Probe probe;
    probe.bytes = bytes;
    probe.status = status;
    active_probe = &probe;
    const auto result = test_generate_read_fixture_head_nonce(&fake_random);
    exact_call(probe);
    check(result.ok() && result.error() == NonceGenerationError::none,
          "successful native status gives typed success");
    check(result.nonce().has_value() && result.nonce().value() == bytes,
          "every returned byte equals fake output without transformation");
    check(std::string_view(result.failure_step()).empty(), "success has no failure step");
    auto copy = result.nonce().value();
    copy[0] ^= 1;
    check(result.nonce().value() == bytes, "caller-owned nonce copy cannot modify result");
    active_probe = nullptr;
}
void failure_case(NTSTATUS status, bool partial_write, Mode mode = Mode::return_status) {
    Probe probe;
    probe.status = status;
    probe.mode = mode;
    probe.bytes.fill(0xa5);
    if (!partial_write) probe.bytes.fill(0);
    active_probe = &probe;
    const auto result = test_generate_read_fixture_head_nonce(&fake_random);
    exact_call(probe);
    check(!result.ok() && result.error() == NonceGenerationError::incomplete,
          "failed native call is typed incomplete");
    check(!result.nonce().has_value(), "failed or partial native call exposes no nonce");
    check(std::string_view(result.failure_step()) == "generate-readfixturehead-nonce",
          "failure step is fixed and local");
    active_probe = nullptr;
}
} // namespace

int main() {
    try {
        static_assert(sizeof(Nonce) == 16);
        static_assert(std::is_same_v<decltype(std::declval<const NonceGenerationResult&>().nonce()),
                                     std::optional<Nonce>>);
        static_assert(!std::is_assignable_v<NonceGenerationResult&, NonceGenerationResult>);
        Nonce zero{};
        success_pattern(zero);
        Nonce ff{}; ff.fill(0xff);
        success_pattern(ff);
        Nonce ascending{};
        for (std::uint8_t i = 0; i < ascending.size(); ++i) ascending[i] = i;
        success_pattern(ascending);
        success_pattern(ascending, static_cast<NTSTATUS>(1)); // informational NTSTATUS is success
        failure_case(static_cast<NTSTATUS>(0xc0000001u), false);
        failure_case(static_cast<NTSTATUS>(0xc0000001u), true);
        failure_case(static_cast<NTSTATUS>(0x80000001u), true);
        failure_case(0, false, Mode::throw_standard);
        failure_case(0, false, Mode::throw_nonstandard);
        const auto null_result = test_generate_read_fixture_head_nonce(nullptr);
        check(!null_result.ok() && !null_result.nonce().has_value() &&
              null_result.error() == NonceGenerationError::incomplete,
              "absent test provider cannot create success");
        std::cout << "read fixture head nonce deterministic checks: " << checks << " passed\n";
        return 0;
    } catch (const std::exception& failure) {
        std::cerr << "nonce deterministic failure after " << checks << " checks: "
                  << failure.what() << '\n';
        return 1;
    }
}
