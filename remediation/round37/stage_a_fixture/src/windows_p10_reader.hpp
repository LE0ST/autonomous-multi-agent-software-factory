#pragma once

#include "windows_snapshot.hpp"
#include <memory>
#include <string>

namespace stage_a::windows {

// G2 supplies these four creation/readback identities and the sealed P10 bytes.
// No value in this configuration may come from A1-writable M4/M5.
struct P10ReaderConfig {
    Metadata root, p1, p3, p10;
    std::string canonical_bytes, sha256;
};

inline constexpr char p10_read_profile[] =
    "protected-P10/handle-bound-identity-read";

OpenSpec p10_file_read_spec();

class P10Calls {
public:
    virtual ~P10Calls() = default;
    virtual HANDLE open_root(const std::wstring& path, RootOpenSpec spec) = 0;
    virtual HANDLE open_relative(HANDLE parent, const std::wstring& component, OpenSpec spec,
                                 const std::string& object) = 0;
    virtual Metadata inspect(HANDLE handle, const std::string& object, const std::string& step) = 0;
    virtual std::string read_content(HANDLE handle, std::size_t max_bytes) = 0;
    virtual void close(HANDLE handle) noexcept = 0;
};

std::shared_ptr<P10Calls> make_system_p10_calls();

// This is only A2's P10 read obligation. A controller composition supplies the
// separate authenticated A3 head reader to ProtectedAuthorityReader later.
class WindowsP10Reader final {
public:
    explicit WindowsP10Reader(P10ReaderConfig config);
    WindowsP10Reader(P10ReaderConfig config, std::shared_ptr<P10Calls> calls);
    std::string read_verified_p10();
private:
    P10ReaderConfig config_;
    std::shared_ptr<P10Calls> calls_;
};

} // namespace stage_a::windows
