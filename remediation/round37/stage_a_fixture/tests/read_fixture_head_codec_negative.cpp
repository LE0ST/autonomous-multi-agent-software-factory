#include "../src/read_fixture_head_codec.hpp"

// Intentional production-API compile-negative: outside code cannot manufacture
// a correlated success result or expose P11 through an unvalidated decoder.
int main() {
    stage_a::read_fixture_head::ResponseValidation forged(
        stage_a::read_fixture_head::Failure::none, "unvalidated P11 bytes");
    return forged.ok() ? 0 : 1;
}
