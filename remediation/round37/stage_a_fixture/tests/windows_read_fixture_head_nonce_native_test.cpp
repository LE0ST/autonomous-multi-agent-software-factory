#include "../src/windows_read_fixture_head_nonce.hpp"

#include <iostream>
#include <stdexcept>

using namespace stage_a::read_fixture_head;
namespace {
int checks = 0;
void check(bool condition, const char* message) {
    ++checks;
    if (!condition) throw std::runtime_error(message);
}
}
int main() {
    try {
        const auto result = generate_read_fixture_head_nonce();
        check(result.ok(), "real local BCryptGenRandom call reported success");
        check(result.error() == NonceGenerationError::none, "no typed failure on success");
        check(result.nonce().has_value(), "exactly one nonce value is available");
        check(result.nonce()->size() == 16, "nonce uses the accepted 16-byte type");
        check(result.failure_step()[0] == '\0', "success has no failure step");
        std::cout << "read fixture head nonce native-local checks: " << checks << " passed\n";
        return 0;
    } catch (const std::exception& failure) {
        std::cerr << "nonce native-local failure: " << failure.what() << '\n';
        return 1;
    }
}
