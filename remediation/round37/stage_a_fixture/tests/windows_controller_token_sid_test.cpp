#include "../src/windows_controller_token_sid.hpp"

#include <array>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <vector>

using namespace stage_a;
using namespace stage_a::windows;
namespace {
static_assert(sizeof(void*) == 8 && sizeof(TOKEN_USER) == 16);
static_assert(std::is_base_of_v<ControllerSidPort, WindowsControllerSidPort>);
constexpr DWORD literal_length = 44; // 16-byte TOKEN_USER + 28-byte SID, independently specified below.
constexpr std::array<unsigned char, 28> literal_sid{
    0x01,0x05,0x00,0x00,0x00,0x00,0x00,0x05,
    0x15,0x00,0x00,0x00, 0x64,0x00,0x00,0x00,
    0xc8,0x00,0x00,0x00, 0x2c,0x01,0x00,0x00,
    0xea,0x03,0x00,0x00
};
constexpr char expected_sid[] = "S-1-5-21-100-200-300-1002";
int checks = 0;
void check(bool okay, const char* message) { ++checks; if (!okay) throw std::runtime_error(message); }
HANDLE fake_handle() { return reinterpret_cast<HANDLE>(static_cast<std::intptr_t>(0x77)); }

struct FakeCalls final : TokenSidNativeCalls {
    enum class Mode { normal, open_denied, open_empty, size_denied, size_success,
                      size_too_small, size_oversized, read_denied, read_changed_size,
                      returned_too_large, returned_too_small, null_sid, outside_sid,
                      wrong_revision, too_many_subauthorities, truncated_sid,
                      different_sid, throw_standard, throw_nonstandard };
    Mode mode = Mode::normal;
    std::vector<std::string> trace;
    int close_count = 0;
    HANDLE open_current_process_token(DWORD access, DWORD& error) override {
        trace.push_back("open-current-process-token");
        check(access == TOKEN_QUERY, "exact TOKEN_QUERY access");
        if (mode == Mode::open_denied) { error = ERROR_ACCESS_DENIED; return nullptr; }
        if (mode == Mode::open_empty) { error = ERROR_SUCCESS; return nullptr; }
        error = ERROR_SUCCESS;
        return fake_handle();
    }
    bool query_token_user(HANDLE token, void* buffer, DWORD capacity,
                          DWORD& returned, DWORD& error) override {
        check(token == fake_handle(), "held synthetic token handle");
        if (!buffer) {
            trace.push_back("TokenUser-size");
            check(capacity == 0, "null sizing buffer has zero capacity");
            if (mode == Mode::size_denied) { error = ERROR_ACCESS_DENIED; return false; }
            if (mode == Mode::size_success) { returned = literal_length; error = ERROR_SUCCESS; return true; }
            returned = mode == Mode::size_too_small ? 4 :
                       mode == Mode::size_oversized ? TOKEN_USER_MAX_SIZE + 1 : literal_length;
            error = ERROR_INSUFFICIENT_BUFFER;
            return false;
        }
        trace.push_back("TokenUser-read");
        check(capacity == literal_length, "exact bounded second query");
        if (mode == Mode::throw_standard) throw std::runtime_error("synthetic provider exception");
        if (mode == Mode::throw_nonstandard) throw 19;
        if (mode == Mode::read_denied) { error = ERROR_ACCESS_DENIED; return false; }
        if (mode == Mode::read_changed_size) { error = ERROR_INSUFFICIENT_BUFFER; return false; }
        auto* bytes = static_cast<unsigned char*>(buffer);
        std::memset(bytes, 0, capacity);
        std::memcpy(bytes + 16, literal_sid.data(), literal_sid.size());
        std::uintptr_t sid_pointer = reinterpret_cast<std::uintptr_t>(bytes + 16);
        if (mode == Mode::null_sid) sid_pointer = 0;
        if (mode == Mode::outside_sid) sid_pointer = reinterpret_cast<std::uintptr_t>(bytes + capacity + 1);
        std::memcpy(bytes, &sid_pointer, sizeof(sid_pointer));
        if (mode == Mode::wrong_revision) bytes[16] = 2;
        if (mode == Mode::too_many_subauthorities) bytes[17] = 16;
        if (mode == Mode::different_sid) bytes[40] = 0xeb; // 1003, not the literal C SID.
        returned = mode == Mode::returned_too_large ? capacity + 1 :
                   mode == Mode::returned_too_small ? 4 :
                   mode == Mode::truncated_sid ? 26 : literal_length;
        error = ERROR_SUCCESS;
        return true;
    }
    void close(HANDLE token) noexcept override {
        trace.push_back("close-token");
        if (token == fake_handle()) ++close_count;
    }
};

void stopped(FakeCalls::Mode mode, ErrorKind kind, const char* step,
             bool native_error = false, DWORD error = 0, int closes = 1) {
    auto fake = std::make_shared<FakeCalls>(); fake->mode = mode;
    try {
        (void)WindowsControllerSidPort(fake).read_current_process_sid();
        check(false, "expected typed token failure");
    } catch (const ObservationFailure& failure) {
        check(failure.kind == kind, "typed kind");
        check(failure.object == "A2-token", "typed object");
        check(failure.profile == controller_token_sid_profile, "typed profile");
        check(failure.step == step, "typed step");
        check(failure.has_win32_error == native_error, "raw Win32 availability");
        if (native_error) check(failure.win32_error == error, "raw Win32 value");
        check(!failure.has_ntstatus, "no invented NTSTATUS for Win32 calls");
    }
    check(fake->close_count == closes, "token handle cleanup");
    check(fake->trace.front() == "open-current-process-token", "no process selector");
}
}

int main() {
    try {
        // Retain/link the production backend; its read method is never called here.
        auto production = std::make_unique<WindowsControllerSidPort>();
        check(production != nullptr, "system backend constructs and links");
        {
            auto fake = std::make_shared<FakeCalls>();
            const std::string sid = WindowsControllerSidPort(fake).read_current_process_sid();
            check(sid == expected_sid, "independent literal SID vector");
            check(fake->trace == std::vector<std::string>({"open-current-process-token","TokenUser-size",
                  "TokenUser-read","close-token"}), "fixed native call order");
            check(fake->close_count == 1, "successful handle closed once");
        }
        {
            auto fake = std::make_shared<FakeCalls>(); fake->mode = FakeCalls::Mode::different_sid;
            check(WindowsControllerSidPort(fake).read_current_process_sid() ==
                  "S-1-5-21-100-200-300-1003", "observed SID is returned without caller-supplied C substitution");
        }
        stopped(FakeCalls::Mode::open_denied, ErrorKind::native_failure, "OpenProcessToken", true,
                ERROR_ACCESS_DENIED, 0);
        stopped(FakeCalls::Mode::open_empty, ErrorKind::incomplete, "OpenProcessToken", false, 0, 0);
        stopped(FakeCalls::Mode::size_denied, ErrorKind::native_failure, "TokenUser/size-query", true,
                ERROR_ACCESS_DENIED);
        stopped(FakeCalls::Mode::size_success, ErrorKind::incomplete, "TokenUser/size-query");
        stopped(FakeCalls::Mode::size_too_small, ErrorKind::incomplete, "TokenUser/size-query");
        stopped(FakeCalls::Mode::size_oversized, ErrorKind::oversized, "TokenUser/size-query");
        stopped(FakeCalls::Mode::read_denied, ErrorKind::native_failure, "TokenUser/read", true,
                ERROR_ACCESS_DENIED);
        stopped(FakeCalls::Mode::read_changed_size, ErrorKind::incomplete, "TokenUser/read", true,
                ERROR_INSUFFICIENT_BUFFER);
        stopped(FakeCalls::Mode::returned_too_large, ErrorKind::incomplete, "TokenUser/length");
        stopped(FakeCalls::Mode::returned_too_small, ErrorKind::incomplete, "TokenUser/length");
        stopped(FakeCalls::Mode::null_sid, ErrorKind::malformed, "TokenUser/SidPointer");
        stopped(FakeCalls::Mode::outside_sid, ErrorKind::malformed, "TokenUser/SidPointer");
        stopped(FakeCalls::Mode::wrong_revision, ErrorKind::malformed, "TokenUser/SidHeader");
        stopped(FakeCalls::Mode::too_many_subauthorities, ErrorKind::malformed, "TokenUser/SidHeader");
        stopped(FakeCalls::Mode::truncated_sid, ErrorKind::incomplete, "TokenUser/SidLength");
        stopped(FakeCalls::Mode::throw_standard, ErrorKind::incomplete, "token-reader-exception");
        stopped(FakeCalls::Mode::throw_nonstandard, ErrorKind::incomplete, "token-reader-exception");
        std::cout << "windows controller token SID synthetic checks: " << checks << " passed\n";
        return 0;
    } catch (const std::exception& failure) {
        std::cerr << "windows controller token SID synthetic failure after " << checks
                  << " checks: " << failure.what() << '\n';
        return 1;
    }
}
