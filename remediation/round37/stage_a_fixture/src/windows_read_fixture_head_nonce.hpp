#pragma once

#include "read_fixture_head_codec.hpp"

#include <optional>

namespace stage_a::read_fixture_head {

enum class NonceGenerationError { none, incomplete };

class NonceGenerationResult final {
public:
    [[nodiscard]] bool ok() const noexcept { return error_ == NonceGenerationError::none; }
    [[nodiscard]] NonceGenerationError error() const noexcept { return error_; }
    [[nodiscard]] std::optional<Nonce> nonce() const noexcept { return nonce_; }
    [[nodiscard]] const char* failure_step() const noexcept {
        return ok() ? "" : "generate-readfixturehead-nonce";
    }

private:
    NonceGenerationResult(NonceGenerationError error, std::optional<Nonce> nonce) noexcept
        : error_(error), nonce_(nonce) {}

    const NonceGenerationError error_;
    const std::optional<Nonce> nonce_;

    friend NonceGenerationResult generate_read_fixture_head_nonce() noexcept;
#if defined(STAGE_A_NONCE_TEST_SEAM)
    friend NonceGenerationResult test_generate_read_fixture_head_nonce(
        long (__stdcall*)(void*, unsigned char*, unsigned long, unsigned long)) noexcept;
#endif
};

// A2-only source unit. One OS CSPRNG call per invocation; no caller-selected
// provider, length, flags, seed, or buffer exists in this production API.
[[nodiscard]] NonceGenerationResult generate_read_fixture_head_nonce() noexcept;

} // namespace stage_a::read_fixture_head
