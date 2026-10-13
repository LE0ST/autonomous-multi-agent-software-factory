#pragma once

#include "../src/windows_read_fixture_head_nonce.hpp"

#include <windows.h>
#include <bcrypt.h>

// Declared only for the explicitly test-gated object. This file is not part of
// the production public header or linked production object.
namespace stage_a::read_fixture_head {
[[nodiscard]] NonceGenerationResult test_generate_read_fixture_head_nonce(
    NTSTATUS (WINAPI* call)(BCRYPT_ALG_HANDLE, PUCHAR, ULONG, ULONG)) noexcept;
}
