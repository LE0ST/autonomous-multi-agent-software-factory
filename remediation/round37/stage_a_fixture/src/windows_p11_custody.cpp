#include "windows_p11_custody.hpp"
#include <winternl.h>
#include <algorithm>
#include <cstdint>
#include <stdexcept>
#include <utility>
#include <vector>

namespace stage_a::windows {
namespace {
constexpr wchar_t root_name[] = L"C:\\";
constexpr wchar_t p1_name[] = L"S1PF_260926_A";
constexpr wchar_t p4_name[] = L"store";
constexpr wchar_t p11_name[] = L"authority.db";
constexpr std::size_t max_p11_bytes = 4096;

[[noreturn]] void fail(ErrorKind kind, const std::string& object,
                       const std::string& step, const char* detail) {
    throw ObservationFailure(kind, object, p11_custody_profile, step, detail);
}
std::wstring child_path(const std::wstring& parent, const wchar_t* child) {
    return parent + (parent.empty() || parent.back() == L'\\' ? L"" : L"\\") + child;
}
bool nonzero_id(const Metadata& value) {
    return std::any_of(value.file_id.begin(), value.file_id.end(),
                       [](std::uint8_t b) { return b != 0; });
}
void check_node(const Metadata& actual, const Metadata& expected,
                const Metadata* parent, const wchar_t* component,
                bool directory, bool protected_dacl,
                const std::string& object, const std::string& step) {
    if ((actual.attributes & FILE_ATTRIBUTE_REPARSE_POINT) || actual.reparse_tag)
        fail(ErrorKind::reparse, object, step, "reparse object or tag");
    if (actual.directory != directory ||
        bool(actual.attributes & FILE_ATTRIBUTE_DIRECTORY) != directory ||
        (actual.attributes & FILE_ATTRIBUTE_DEVICE))
        fail(ErrorKind::identity_drift, object, step, "unexpected object type or device attribute");
    if (!nonzero_id(actual) || actual.volume_guid_path.empty() ||
        actual.final_path.empty() || actual.sddl.empty() ||
        (protected_dacl && !actual.dacl_protected))
        fail(ErrorKind::incomplete, object, step, "required identity or descriptor field absent");
    if (parent && (actual.volume_guid_path != parent->volume_guid_path ||
                   actual.volume_serial != parent->volume_serial ||
                   actual.final_path != child_path(parent->final_path, component)))
        fail(ErrorKind::identity_drift, object, step, "parent binding differs");
    if (actual.volume_guid_path != expected.volume_guid_path ||
        actual.volume_serial != expected.volume_serial ||
        actual.file_id != expected.file_id ||
        actual.final_path != expected.final_path ||
        actual.directory != expected.directory ||
        actual.attributes != expected.attributes ||
        actual.reparse_tag != expected.reparse_tag ||
        actual.sddl != expected.sddl ||
        actual.dacl_protected != expected.dacl_protected)
        fail(ErrorKind::identity_drift, object, step,
             "G2 identity or owner/group/full DACL differs");
}
std::string checked_hash(std::string_view bytes, const char* step) {
    try { return sha256(bytes); }
    catch (...) { fail(ErrorKind::hash_failure, "P11", step, "BCrypt SHA-256 failed"); }
}
class HeldHandles {
public:
    explicit HeldHandles(P11CustodyCalls& calls) : calls_(calls) {}
    ~HeldHandles() { for (auto i = held_.rbegin(); i != held_.rend(); ++i) calls_.close(*i); }
    HANDLE add(HANDLE handle) {
        if (!handle || handle == INVALID_HANDLE_VALUE)
            fail(ErrorKind::incomplete, "P11", "open-handle", "invalid native handle");
        try { held_.push_back(handle); }
        catch (...) { calls_.close(handle); throw; }
        return handle;
    }
private:
    P11CustodyCalls& calls_;
    std::vector<HANDLE> held_;
};
class SystemP11Calls final : public P11CustodyCalls {
public:
    SystemP11Calls() : base_(make_system_native_calls()) {}
    HANDLE open_root(const std::wstring& path, RootOpenSpec spec) override {
        return base_->open_root(path, spec);
    }
    HANDLE open_relative(HANDLE parent, const std::wstring& component,
                         OpenSpec spec, const std::string& object) override {
        return base_->open_relative(parent, component, spec, object, p11_custody_profile);
    }
    Metadata inspect(HANDLE handle, const std::string& object,
                     const std::string& step) override {
        return base_->inspect(handle, object, p11_custody_profile, step);
    }
    std::string read_content(HANDLE handle, std::size_t maximum) override {
        FILE_STANDARD_INFO first{};
        if (!GetFileInformationByHandleEx(handle, FileStandardInfo, &first, sizeof(first)))
            throw win32_failure(ErrorKind::incomplete, "P11", p11_custody_profile,
                                "read-size", GetLastError());
        if (first.Directory || first.EndOfFile.QuadPart < 0)
            fail(ErrorKind::incomplete, "P11", "read-size", "invalid file size or type");
        if (static_cast<std::uint64_t>(first.EndOfFile.QuadPart) > maximum)
            fail(ErrorKind::oversized, "P11", "read-size", "P11 exceeds sealed byte count");
        LARGE_INTEGER zero{};
        if (!SetFilePointerEx(handle, zero, nullptr, FILE_BEGIN))
            throw win32_failure(ErrorKind::incomplete, "P11", p11_custody_profile,
                                "read-seek", GetLastError());
        const auto size = static_cast<std::size_t>(first.EndOfFile.QuadPart);
        std::string result(size, '\0');
        std::size_t done = 0;
        while (done < size) {
            DWORD got = 0;
            const DWORD ask = static_cast<DWORD>((std::min)(size - done, std::size_t{4096}));
            if (!ReadFile(handle, result.data() + done, ask, &got, nullptr))
                throw win32_failure(ErrorKind::incomplete, "P11", p11_custody_profile,
                                    "read-content", GetLastError());
            if (!got || got > ask)
                fail(ErrorKind::incomplete, "P11", "read-content", "incomplete read");
            done += got;
        }
        char extra{};
        DWORD got = 0;
        if (!ReadFile(handle, &extra, 1, &got, nullptr))
            throw win32_failure(ErrorKind::incomplete, "P11", p11_custody_profile,
                                "read-eof", GetLastError());
        if (got) fail(ErrorKind::identity_drift, "P11", "read-eof", "content grew during read");
        FILE_STANDARD_INFO last{};
        if (!GetFileInformationByHandleEx(handle, FileStandardInfo, &last, sizeof(last)))
            throw win32_failure(ErrorKind::incomplete, "P11", p11_custody_profile,
                                "read-final-size", GetLastError());
        if (last.Directory || last.EndOfFile.QuadPart != first.EndOfFile.QuadPart)
            fail(ErrorKind::identity_drift, "P11", "read-final-size", "content size drift");
        return result;
    }
    void close(HANDLE handle) noexcept override { base_->close(handle); }
private:
    std::shared_ptr<NativeCalls> base_;
};
} // namespace

OpenSpec p11_file_read_spec() {
    return {FILE_READ_DATA | FILE_READ_ATTRIBUTES | READ_CONTROL | SYNCHRONIZE,
            FILE_SHARE_READ | FILE_SHARE_WRITE, FILE_OPEN,
            FILE_NON_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT | FILE_SYNCHRONOUS_IO_NONALERT,
            OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE};
}
WindowsP11CustodyReader::WindowsP11CustodyReader(P11CustodyConfig trusted_g2)
    : config_(std::move(trusted_g2)), calls_(std::make_shared<SystemP11Calls>()) {}
#if defined(STAGE_A_P11_CUSTODY_TEST_SEAM)
WindowsP11CustodyReader::WindowsP11CustodyReader(P11CustodyConfig synthetic_g2,
    std::shared_ptr<P11CustodyCalls> synthetic_calls)
    : config_(std::move(synthetic_g2)), calls_(std::move(synthetic_calls)) {}
#endif

std::string WindowsP11CustodyReader::read_verified_p11() {
    try {
        if (!calls_ || config_.root.final_path != config_.root.volume_guid_path ||
            config_.p1.final_path != child_path(config_.root.final_path, p1_name) ||
            config_.p4.final_path != child_path(config_.p1.final_path, p4_name) ||
            config_.p11.final_path != child_path(config_.p4.final_path, p11_name))
            fail(ErrorKind::binding_failure, "P11", "trusted-config", "invalid G2 P11 identity chain");
        const auto cases = fixture_cases();
        const auto found = std::find_if(cases.begin(), cases.end(), [&](const FixtureCase& item) {
            return item.id == config_.selected_case.id && item.latest_digest == config_.selected_case.latest_digest &&
                   item.generation == config_.selected_case.generation &&
                   item.worker_runs == config_.selected_case.worker_runs &&
                   item.status == config_.selected_case.status && item.state == config_.selected_case.state &&
                   item.old_digest == config_.selected_case.old_digest &&
                   item.old_files == config_.selected_case.old_files &&
                   item.latest_files == config_.selected_case.latest_files;
        });
        if (found == cases.end())
            fail(ErrorKind::binding_failure, "P11", "trusted-case", "selected case is not frozen");
        std::string expected;
        try { expected = render_p11(*found, config_.rendered_p10_sha256); }
        catch (...) { fail(ErrorKind::binding_failure, "P11", "trusted-case", "invalid rendered P10 digest"); }
        if (expected.empty() || expected.size() > max_p11_bytes ||
            checked_hash(expected, "trusted-config-hash") != config_.p11_sha256)
            fail(ErrorKind::binding_failure, "P11", "trusted-config-hash", "P11 seal does not match canonical case bytes");
        HeldHandles held(*calls_);
        const HANDLE root = held.add(calls_->open_root(root_name, root_identity_spec()));
        const Metadata root_meta = calls_->inspect(root, "volume-root", "initial-identity");
        check_node(root_meta, config_.root, nullptr, nullptr, true, false, "volume-root", "initial-identity");
        const HANDLE p1 = held.add(calls_->open_relative(root, p1_name, ancestor_identity_spec(), "P1"));
        const Metadata p1_meta = calls_->inspect(p1, "P1", "initial-identity");
        check_node(p1_meta, config_.p1, &root_meta, p1_name, true, true, "P1", "initial-identity");
        const HANDLE p4 = held.add(calls_->open_relative(p1, p4_name, ancestor_identity_spec(), "P4"));
        const Metadata p4_meta = calls_->inspect(p4, "P4", "initial-identity");
        check_node(p4_meta, config_.p4, &p1_meta, p4_name, true, true, "P4", "initial-identity");
        const HANDLE p11 = held.add(calls_->open_relative(p4, p11_name, p11_file_read_spec(), "P11"));
        const Metadata p11_meta = calls_->inspect(p11, "P11", "initial-identity");
        check_node(p11_meta, config_.p11, &p4_meta, p11_name, false, true, "P11", "initial-identity");
        const std::string bytes = calls_->read_content(p11, expected.size());
        if (bytes != expected) fail(ErrorKind::binding_failure, "P11", "canonical-bytes", "P11 differs from selected case");
        if (checked_hash(bytes, "content-sha256") != config_.p11_sha256)
            fail(ErrorKind::hash_failure, "P11", "content-sha256", "P11 digest differs from G2 seal");
        if (calls_->read_content(p11, expected.size()) != bytes)
            fail(ErrorKind::identity_drift, "P11", "final-content", "P11 content changed");
        check_node(calls_->inspect(root, "volume-root", "final-identity"), root_meta,
                   nullptr, nullptr, true, false, "volume-root", "final-identity");
        check_node(calls_->inspect(p1, "P1", "final-identity"), p1_meta,
                   &root_meta, p1_name, true, true, "P1", "final-identity");
        check_node(calls_->inspect(p4, "P4", "final-identity"), p4_meta,
                   &p1_meta, p4_name, true, true, "P4", "final-identity");
        check_node(calls_->inspect(p11, "P11", "final-identity"), p11_meta,
                   &p4_meta, p11_name, false, true, "P11", "final-identity");
        return bytes;
    } catch (const ObservationFailure&) { throw; }
    catch (const std::exception& failure) {
        throw ObservationFailure(ErrorKind::incomplete, "P11", p11_custody_profile,
                                 "reader-exception", failure.what());
    } catch (...) {
        throw ObservationFailure(ErrorKind::incomplete, "P11", p11_custody_profile,
                                 "reader-exception", "non-standard C++ reader exception");
    }
}
} // namespace stage_a::windows
