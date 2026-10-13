#include "../src/windows_p11_custody.hpp"

// Intentional compile-negative in production mode: no injected constructor.
// The same TU compiles in test mode but cannot link to a production-mode object.
int main() {
    stage_a::windows::P11CustodyConfig config;
    auto calls = std::shared_ptr<stage_a::windows::P11CustodyCalls>{};
    stage_a::windows::WindowsP11CustodyReader reader(std::move(config), calls);
    return 0;
}
