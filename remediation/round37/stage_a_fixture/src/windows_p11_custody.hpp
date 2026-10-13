#pragma once

#include "windows_snapshot.hpp"
#include <memory>

namespace stage_a::windows {

inline constexpr char p11_custody_profile[] = "A3/P11/handle-bound-protected-read";

// Every value is a separately sealed G2 creation/readback input. The selected
// case is fixed by that seal; this reader has no writer or request parameter.
struct P11CustodyConfig {
    Metadata root, p1, p4, p11;
    FixtureCase selected_case;
    std::string rendered_p10_sha256, p11_sha256;
};

OpenSpec p11_file_read_spec();

class P11CustodyCalls {
public:
    virtual ~P11CustodyCalls() = default;
    virtual HANDLE open_root(const std::wstring& path, RootOpenSpec spec) = 0;
    virtual HANDLE open_relative(HANDLE parent, const std::wstring& component,
                                 OpenSpec spec, const std::string& object) = 0;
    virtual Metadata inspect(HANDLE handle, const std::string& object,
                             const std::string& step) = 0;
    virtual std::string read_content(HANDLE handle, std::size_t maximum) = 0;
    virtual void close(HANDLE handle) noexcept = 0;
};

class WindowsP11CustodyReader final {
public:
    explicit WindowsP11CustodyReader(P11CustodyConfig trusted_g2);
#if defined(STAGE_A_P11_CUSTODY_TEST_SEAM)
    WindowsP11CustodyReader(P11CustodyConfig synthetic_g2,
                            std::shared_ptr<P11CustodyCalls> synthetic_calls);
#endif
    std::string read_verified_p11();
private:
    P11CustodyConfig config_;
    std::shared_ptr<P11CustodyCalls> calls_;
};

} // namespace stage_a::windows
