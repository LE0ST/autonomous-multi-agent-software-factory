#include "../src/windows_read_fixture_head_nonce.hpp"

// Intentional compile-negative: an external consumer cannot forge success.
int main() {
    stage_a::read_fixture_head::Nonce bytes{};
    stage_a::read_fixture_head::NonceGenerationResult forged(
        stage_a::read_fixture_head::NonceGenerationError::none, bytes);
    return forged.ok() ? 0 : 1;
}
