#include "../src/windows_read_fixture_head_nonce.hpp"

// Intentional compile-negative: the production header declares no test seam.
int main() {
    auto result = stage_a::read_fixture_head::test_generate_read_fixture_head_nonce(nullptr);
    return result.ok() ? 0 : 1;
}
