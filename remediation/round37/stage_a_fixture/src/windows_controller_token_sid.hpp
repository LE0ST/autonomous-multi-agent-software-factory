#pragma once

#include "controller_authority_composition.hpp"
#include <windows.h>
#include <memory>

namespace stage_a::windows {

inline constexpr char controller_token_sid_profile[] = "A2/current-process-token/SID";

// The native-call port has no process selector: production always opens the
// current process token. Injection is available only in a test-mode build.
class TokenSidNativeCalls {
public:
    virtual ~TokenSidNativeCalls() = default;
    virtual HANDLE open_current_process_token(DWORD access, DWORD& win32_error) = 0;
    virtual bool query_token_user(HANDLE token, void* buffer, DWORD capacity,
                                  DWORD& returned_length, DWORD& win32_error) = 0;
    virtual void close(HANDLE token) noexcept = 0;
};

class WindowsControllerSidPort final : public ControllerSidPort {
public:
    WindowsControllerSidPort(); // system backend; constructor performs no token query
#if defined(STAGE_A_TOKEN_SID_TEST_SEAM)
    explicit WindowsControllerSidPort(std::shared_ptr<TokenSidNativeCalls> synthetic_calls);
#endif
    std::string read_current_process_sid() override;
private:
    std::shared_ptr<TokenSidNativeCalls> calls_;
};

} // namespace stage_a::windows
