#include "windows_read_fixture_head_nonce.hpp"

#include <windows.h>
#include <bcrypt.h>

#include <type_traits>

#if defined(STAGE_A_NONCE_TEST_SEAM)
#include "../tests/windows_read_fixture_head_nonce_test_port.hpp"
#endif

namespace stage_a::read_fixture_head {
namespace {
using NativeCall = NTSTATUS (WINAPI*)(BCRYPT_ALG_HANDLE, PUCHAR, ULONG, ULONG);
static_assert(std::is_same_v<NativeCall, decltype(&BCryptGenRandom)>);
static_assert(sizeof(Nonce) == 16);

std::optional<Nonce> generate_once(NativeCall call) noexcept {
    if (!call) return std::nullopt;
    Nonce bytes{};
    try {
        const NTSTATUS status = call(nullptr, bytes.data(), 16,
                                     BCRYPT_USE_SYSTEM_PREFERRED_RNG);
        if (BCRYPT_SUCCESS(status)) return bytes;
    } catch (...) {
        // A test provider can throw; the production BCrypt call is native.
    }
    return std::nullopt;
}
} // namespace

NonceGenerationResult generate_read_fixture_head_nonce() noexcept {
    const auto nonce = generate_once(&BCryptGenRandom);
    if (!nonce) return {NonceGenerationError::incomplete, std::nullopt};
    return {NonceGenerationError::none, nonce};
}

#if defined(STAGE_A_NONCE_TEST_SEAM)
NonceGenerationResult test_generate_read_fixture_head_nonce(NativeCall call) noexcept {
    const auto nonce = generate_once(call);
    if (!nonce) return {NonceGenerationError::incomplete, std::nullopt};
    return {NonceGenerationError::none, nonce};
}
#endif
} // namespace stage_a::read_fixture_head
