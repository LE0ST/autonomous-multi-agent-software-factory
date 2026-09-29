#include "windows_controller_token_sid.hpp"

#include <sddl.h>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <utility>

namespace stage_a::windows {
namespace {
constexpr DWORD min_sid_bytes = 8;
constexpr DWORD max_token_user_bytes = TOKEN_USER_MAX_SIZE;

[[noreturn]] void stop(ErrorKind kind, const char* step, const char* message,
                       DWORD error = 0, bool has_error = false) {
    throw ObservationFailure(kind, "A2-token", controller_token_sid_profile, step,
                             message, 0, false, error, has_error);
}

class SystemTokenSidCalls final : public TokenSidNativeCalls {
public:
    HANDLE open_current_process_token(DWORD access, DWORD& win32_error) override {
        HANDLE token = nullptr;
        if (!OpenProcessToken(GetCurrentProcess(), access, &token)) {
            win32_error = GetLastError();
            return nullptr;
        }
        win32_error = ERROR_SUCCESS;
        return token;
    }
    bool query_token_user(HANDLE token, void* buffer, DWORD capacity,
                          DWORD& returned_length, DWORD& win32_error) override {
        const BOOL success = GetTokenInformation(token, TokenUser, buffer, capacity, &returned_length);
        win32_error = success ? ERROR_SUCCESS : GetLastError();
        return success != FALSE;
    }
    void close(HANDLE token) noexcept override { CloseHandle(token); }
};

class HeldToken {
public:
    HeldToken(TokenSidNativeCalls& calls, HANDLE handle) : calls_(calls), handle_(handle) {}
    ~HeldToken() { calls_.close(handle_); }
    HeldToken(const HeldToken&) = delete;
    HeldToken& operator=(const HeldToken&) = delete;
private:
    TokenSidNativeCalls& calls_;
    HANDLE handle_;
};

class LocalSidText {
public:
    ~LocalSidText() { if (text) LocalFree(text); }
    LPWSTR text = nullptr;
};

std::string decode_token_user_sid(const std::byte* buffer, DWORD returned_length) {
    if (!buffer || returned_length < sizeof(TOKEN_USER) + min_sid_bytes ||
        returned_length > max_token_user_bytes)
        stop(ErrorKind::incomplete, "TokenUser/length", "TokenUser result length is incomplete or out of bounds");
    TOKEN_USER user{};
    std::memcpy(&user, buffer, sizeof(user));
    const auto base = reinterpret_cast<std::uintptr_t>(buffer);
    const auto sid_address = reinterpret_cast<std::uintptr_t>(user.User.Sid);
    if (!user.User.Sid || sid_address < base || sid_address - base < sizeof(TOKEN_USER) ||
        sid_address - base > returned_length - min_sid_bytes)
        stop(ErrorKind::malformed, "TokenUser/SidPointer", "SID pointer is outside the returned TokenUser buffer");
    const auto offset = static_cast<std::size_t>(sid_address - base);
    const auto available = static_cast<std::size_t>(returned_length) - offset;
    const auto* sid_bytes = reinterpret_cast<const unsigned char*>(buffer) + offset;
    if (sid_bytes[0] != SID_REVISION || sid_bytes[1] > SID_MAX_SUB_AUTHORITIES)
        stop(ErrorKind::malformed, "TokenUser/SidHeader", "SID revision or subauthority count is invalid");
    const auto sid_length = static_cast<std::size_t>(min_sid_bytes) +
                            static_cast<std::size_t>(sid_bytes[1]) * sizeof(DWORD);
    if (sid_length > available)
        stop(ErrorKind::incomplete, "TokenUser/SidLength", "SID extends beyond returned TokenUser bytes");
    if (!IsValidSid(user.User.Sid) || GetLengthSid(user.User.Sid) != sid_length)
        stop(ErrorKind::malformed, "TokenUser/SidValidation", "SID failed Windows validation");
    LocalSidText converted;
    if (!ConvertSidToStringSidW(user.User.Sid, &converted.text))
        stop(ErrorKind::native_failure, "ConvertSidToStringSidW", "SID conversion failed", GetLastError(), true);
    if (!converted.text)
        stop(ErrorKind::incomplete, "ConvertSidToStringSidW", "conversion succeeded without text");
    const std::size_t length = wcsnlen_s(converted.text, SECURITY_MAX_SID_STRING_CHARACTERS + 1);
    if (length < 5 || length > SECURITY_MAX_SID_STRING_CHARACTERS ||
        converted.text[0] != L'S' || converted.text[1] != L'-')
        stop(ErrorKind::malformed, "ConvertSidToStringSidW/text", "noncanonical SID text");
    std::string result;
    result.reserve(length);
    for (std::size_t i = 0; i < length; ++i) {
        const wchar_t c = converted.text[i];
        if (!((c >= L'0' && c <= L'9') || c == L'S' || c == L'-'))
            stop(ErrorKind::malformed, "ConvertSidToStringSidW/text", "SID text contains an invalid character");
        result.push_back(static_cast<char>(c));
    }
    return result;
}
} // namespace

WindowsControllerSidPort::WindowsControllerSidPort()
    : calls_(std::make_shared<SystemTokenSidCalls>()) {}
#if defined(STAGE_A_TOKEN_SID_TEST_SEAM)
WindowsControllerSidPort::WindowsControllerSidPort(std::shared_ptr<TokenSidNativeCalls> synthetic_calls)
    : calls_(std::move(synthetic_calls)) {}
#endif

std::string WindowsControllerSidPort::read_current_process_sid() {
    try {
        if (!calls_)
            stop(ErrorKind::incomplete, "token-backend", "token backend is absent");
        DWORD error = ERROR_SUCCESS;
        const HANDLE token = calls_->open_current_process_token(TOKEN_QUERY, error);
        if (!token || token == INVALID_HANDLE_VALUE)
            stop(error == ERROR_SUCCESS ? ErrorKind::incomplete : ErrorKind::native_failure,
                 "OpenProcessToken", "current process token open failed",
                 error, error != ERROR_SUCCESS);
        HeldToken held(*calls_, token);
        DWORD required = 0;
        error = ERROR_SUCCESS;
        const bool first_success = calls_->query_token_user(token, nullptr, 0, required, error);
        if (first_success || error != ERROR_INSUFFICIENT_BUFFER)
            stop(first_success ? ErrorKind::incomplete : ErrorKind::native_failure,
                 "TokenUser/size-query", "TokenUser sizing query did not return the required bound",
                 error, !first_success);
        if (required < sizeof(TOKEN_USER) + min_sid_bytes)
            stop(ErrorKind::incomplete, "TokenUser/size-query", "TokenUser required length is too small");
        if (required > max_token_user_bytes)
            stop(ErrorKind::oversized, "TokenUser/size-query", "TokenUser required length exceeds SDK SID bound");
        std::unique_ptr<std::byte[]> buffer(new std::byte[required]{});
        DWORD returned = 0;
        error = ERROR_SUCCESS;
        if (!calls_->query_token_user(token, buffer.get(), required, returned, error))
            stop(error == ERROR_INSUFFICIENT_BUFFER ? ErrorKind::incomplete : ErrorKind::native_failure,
                 "TokenUser/read", "TokenUser read failed without retry", error, true);
        if (returned > required)
            stop(ErrorKind::incomplete, "TokenUser/length", "TokenUser returned length exceeds allocated buffer");
        return decode_token_user_sid(buffer.get(), returned);
    } catch (const ObservationFailure&) {
        throw;
    } catch (const std::exception& failure) {
        throw ObservationFailure(ErrorKind::incomplete, "A2-token", controller_token_sid_profile,
                                 "token-reader-exception", failure.what());
    } catch (...) {
        throw ObservationFailure(ErrorKind::incomplete, "A2-token", controller_token_sid_profile,
                                 "token-reader-exception", "non-standard C++ token-reader exception");
    }
}
} // namespace stage_a::windows
