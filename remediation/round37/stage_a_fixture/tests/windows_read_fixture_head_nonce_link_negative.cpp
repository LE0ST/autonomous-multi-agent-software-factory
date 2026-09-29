#include "windows_read_fixture_head_nonce_test_port.hpp"

// Intentional link-negative when linked only with the production object.
int main() {
    auto result = stage_a::read_fixture_head::test_generate_read_fixture_head_nonce(nullptr);
    return result.ok() ? 0 : 1;
}
