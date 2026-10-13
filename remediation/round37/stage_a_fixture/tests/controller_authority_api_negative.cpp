#include "../src/controller_authority_composition.hpp"

// Intentional compile-negative consumer: this concrete adapter was formerly
// public. The corrected composition header must not declare it or provide a
// ProtectedAuthorityReader object/reference through which it can be called.
int main() {
    stage_a::windows::ControllerProtectedReader* bypass = nullptr;
    return bypass != nullptr;
}
