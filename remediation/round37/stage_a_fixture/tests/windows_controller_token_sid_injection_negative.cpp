#include "../src/windows_controller_token_sid.hpp"

// Intentional production-mode compile-negative consumer: injected native calls
// must not be accepted when STAGE_A_TOKEN_SID_TEST_SEAM is undefined.
int main() {
    std::shared_ptr<stage_a::windows::TokenSidNativeCalls> injected;
    stage_a::windows::WindowsControllerSidPort port(injected);
    return 0;
}
