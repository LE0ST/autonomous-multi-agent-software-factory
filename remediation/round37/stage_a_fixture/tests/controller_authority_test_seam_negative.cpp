#include "../src/controller_authority_composition.hpp"

// Intentional production-mode compile-negative consumer. The injected P10
// seam must not be declared unless the test-build macro is explicitly set.
int main() {
    return stage_a::windows::test_seam::bind_controller_precomparison == nullptr;
}
