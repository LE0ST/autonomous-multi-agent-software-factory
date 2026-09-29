#include "windows_p10_reader.hpp"
#include <winternl.h>

#include <algorithm>
#include <array>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>

namespace stage_a::windows {
namespace {
constexpr std::size_t max_p10_bytes = 65536;
constexpr wchar_t volume_root[] = L"C:\\";
constexpr wchar_t p1_name[] = L"S1PF_260926_A";
constexpr wchar_t p3_name[] = L"config";
constexpr wchar_t p10_name[] = L"binding.json";

bool nonzero_id(const Metadata& m) {
    return std::any_of(m.file_id.begin(), m.file_id.end(), [](std::uint8_t b) { return b != 0; });
}
std::wstring child_path(const std::wstring& parent, const wchar_t* child) {
    return parent + (parent.empty() || parent.back() == L'\\' ? L"" : L"\\") + child;
}
[[noreturn]] void fail(ErrorKind kind, const std::string& object, const std::string& step,
                       const char* detail) {
    throw ObservationFailure(kind, object, p10_read_profile, step, detail);
}
std::string checked_sha256(std::string_view bytes, const char* step) {
    try { return sha256(bytes); }
    catch (...) { fail(ErrorKind::hash_failure, "P10", step, "BCrypt SHA-256 failed"); }
}
void check_node(const Metadata& actual, const Metadata& expected, const Metadata* parent,
                const wchar_t* component, bool directory, bool protected_dacl,
                const std::string& object, const std::string& step) {
    if ((actual.attributes & FILE_ATTRIBUTE_REPARSE_POINT) || actual.reparse_tag)
        fail(ErrorKind::reparse, object, step, "reparse object or tag");
    if (actual.directory != directory ||
        bool(actual.attributes & FILE_ATTRIBUTE_DIRECTORY) != directory ||
        (actual.attributes & FILE_ATTRIBUTE_DEVICE))
        fail(ErrorKind::identity_drift, object, step, "unexpected object type or device attribute");
    if (!nonzero_id(actual) || actual.volume_guid_path.empty() || actual.final_path.empty() ||
        actual.sddl.empty() || (protected_dacl && !actual.dacl_protected))
        fail(ErrorKind::incomplete, object, step, "required identity or descriptor field absent");
    if (parent && (actual.volume_guid_path != parent->volume_guid_path ||
                   actual.volume_serial != parent->volume_serial ||
                   actual.final_path != child_path(parent->final_path, component)))
        fail(ErrorKind::identity_drift, object, step, "parent binding differs");
    if (actual.volume_guid_path != expected.volume_guid_path ||
        actual.volume_serial != expected.volume_serial || actual.file_id != expected.file_id ||
        actual.final_path != expected.final_path || actual.directory != expected.directory ||
        actual.attributes != expected.attributes || actual.reparse_tag != expected.reparse_tag ||
        actual.sddl != expected.sddl || actual.dacl_protected != expected.dacl_protected)
        fail(ErrorKind::identity_drift, object, step, "G2 identity or owner/group/full DACL differs");
}
class HeldHandles {
public:
    explicit HeldHandles(P10Calls& calls) : calls_(calls) {}
    ~HeldHandles() { for (auto i = held_.rbegin(); i != held_.rend(); ++i) calls_.close(*i); }
    HANDLE add(HANDLE h) {
        if (!h || h == INVALID_HANDLE_VALUE) fail(ErrorKind::incomplete, "P10", "open-handle", "invalid native handle");
        try { held_.push_back(h); } catch (...) { calls_.close(h); throw; }
        return h;
    }
private:
    P10Calls& calls_;
    std::vector<HANDLE> held_;
};

class SystemP10Calls final : public P10Calls {
public:
    SystemP10Calls() : base_(make_system_native_calls()) {}
    HANDLE open_root(const std::wstring& path, RootOpenSpec spec) override {
        return base_->open_root(path, spec);
    }
    HANDLE open_relative(HANDLE parent, const std::wstring& component, OpenSpec spec,
                         const std::string& object) override {
        return base_->open_relative(parent, component, spec, object, p10_read_profile);
    }
    Metadata inspect(HANDLE handle, const std::string& object, const std::string& step) override {
        return base_->inspect(handle, object, p10_read_profile, step);
    }
    std::string read_content(HANDLE handle, std::size_t max_bytes) override {
        FILE_STANDARD_INFO info{};
        if (!GetFileInformationByHandleEx(handle, FileStandardInfo, &info, sizeof(info)))
            throw win32_failure(ErrorKind::incomplete, "P10", p10_read_profile, "read-size", GetLastError());
        if (info.Directory || info.EndOfFile.QuadPart < 0)
            fail(ErrorKind::incomplete, "P10", "read-size", "invalid file size or directory");
        if (static_cast<std::uint64_t>(info.EndOfFile.QuadPart) > max_bytes)
            fail(ErrorKind::oversized, "P10", "read-size", "P10 exceeds approved byte count");
        LARGE_INTEGER zero{};
        if (!SetFilePointerEx(handle, zero, nullptr, FILE_BEGIN))
            throw win32_failure(ErrorKind::incomplete, "P10", p10_read_profile, "read-seek", GetLastError());
        const auto expected = static_cast<std::size_t>(info.EndOfFile.QuadPart);
        std::string bytes(expected, '\0');
        std::size_t done = 0;
        while (done < expected) {
            DWORD got = 0;
            const DWORD count = static_cast<DWORD>((std::min)(expected - done, std::size_t{16384}));
            if (!ReadFile(handle, bytes.data() + done, count, &got, nullptr))
                throw win32_failure(ErrorKind::incomplete, "P10", p10_read_profile, "read-content", GetLastError());
            if (!got || got > count) fail(ErrorKind::incomplete, "P10", "read-content", "incomplete read");
            done += got;
        }
        char extra = 0;
        DWORD got = 0;
        if (!ReadFile(handle, &extra, 1, &got, nullptr))
            throw win32_failure(ErrorKind::incomplete, "P10", p10_read_profile, "read-eof", GetLastError());
        if (got) fail(ErrorKind::identity_drift, "P10", "read-eof", "content grew during read");
        FILE_STANDARD_INFO final{};
        if (!GetFileInformationByHandleEx(handle, FileStandardInfo, &final, sizeof(final)))
            throw win32_failure(ErrorKind::incomplete, "P10", p10_read_profile, "read-final-size", GetLastError());
        if (final.Directory || final.EndOfFile.QuadPart != info.EndOfFile.QuadPart)
            fail(ErrorKind::identity_drift, "P10", "read-final-size", "content size drift");
        return bytes;
    }
    void close(HANDLE h) noexcept override { base_->close(h); }
private:
    std::shared_ptr<NativeCalls> base_;
};
} // namespace

OpenSpec p10_file_read_spec() {
    return {FILE_READ_DATA | FILE_READ_ATTRIBUTES | READ_CONTROL | SYNCHRONIZE,
            FILE_SHARE_READ | FILE_SHARE_WRITE, FILE_OPEN,
            FILE_NON_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT | FILE_SYNCHRONOUS_IO_NONALERT,
            OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE};
}
std::shared_ptr<P10Calls> make_system_p10_calls() { return std::make_shared<SystemP10Calls>(); }
WindowsP10Reader::WindowsP10Reader(P10ReaderConfig config)
    : config_(std::move(config)), calls_(make_system_p10_calls()) {}
WindowsP10Reader::WindowsP10Reader(P10ReaderConfig config, std::shared_ptr<P10Calls> calls)
    : config_(std::move(config)), calls_(std::move(calls)) {}

std::string WindowsP10Reader::read_verified_p10() {
    try {
        if (!calls_ || config_.canonical_bytes.empty() || config_.canonical_bytes.size() > max_p10_bytes ||
            config_.sha256.empty() || config_.root.final_path != config_.root.volume_guid_path ||
            config_.p1.final_path != child_path(config_.root.final_path, p1_name) ||
            config_.p3.final_path != child_path(config_.p1.final_path, p3_name) ||
            config_.p10.final_path != child_path(config_.p3.final_path, p10_name))
            fail(ErrorKind::binding_failure, "P10", "trusted-config", "incomplete or inconsistent G2 P10 binding");
        if (checked_sha256(config_.canonical_bytes, "trusted-config-hash") != config_.sha256)
            fail(ErrorKind::binding_failure, "P10", "trusted-config-hash", "G2 P10 bytes and digest disagree");
        HeldHandles held(*calls_);
        const HANDLE root = held.add(calls_->open_root(volume_root, root_identity_spec()));
        const Metadata root_meta = calls_->inspect(root, "volume-root", "initial-identity");
        check_node(root_meta, config_.root, nullptr, nullptr, true, false, "volume-root", "initial-identity");
        const HANDLE p1 = held.add(calls_->open_relative(root, p1_name, ancestor_identity_spec(), "P1"));
        const Metadata p1_meta = calls_->inspect(p1, "P1", "initial-identity");
        check_node(p1_meta, config_.p1, &root_meta, p1_name, true, true, "P1", "initial-identity");
        const HANDLE p3 = held.add(calls_->open_relative(p1, p3_name, ancestor_identity_spec(), "P3"));
        const Metadata p3_meta = calls_->inspect(p3, "P3", "initial-identity");
        check_node(p3_meta, config_.p3, &p1_meta, p3_name, true, true, "P3", "initial-identity");
        const HANDLE p10 = held.add(calls_->open_relative(p3, p10_name, p10_file_read_spec(), "P10"));
        const Metadata p10_meta = calls_->inspect(p10, "P10", "initial-identity");
        check_node(p10_meta, config_.p10, &p3_meta, p10_name, false, true, "P10", "initial-identity");
        const std::string bytes = calls_->read_content(p10, config_.canonical_bytes.size());
        if (bytes != config_.canonical_bytes) fail(ErrorKind::binding_failure, "P10", "canonical-bytes", "P10 bytes differ from G2 seal");
        if (checked_sha256(bytes, "content-sha256") != config_.sha256)
            fail(ErrorKind::hash_failure, "P10", "content-sha256", "P10 digest differs from G2 seal");
        if (calls_->read_content(p10, config_.canonical_bytes.size()) != bytes)
            fail(ErrorKind::identity_drift, "P10", "final-content", "P10 content changed during read window");
        check_node(calls_->inspect(root, "volume-root", "final-identity"), root_meta,
                   nullptr, nullptr, true, false, "volume-root", "final-identity");
        check_node(calls_->inspect(p1, "P1", "final-identity"), p1_meta,
                   &root_meta, p1_name, true, true, "P1", "final-identity");
        check_node(calls_->inspect(p3, "P3", "final-identity"), p3_meta,
                   &p1_meta, p3_name, true, true, "P3", "final-identity");
        check_node(calls_->inspect(p10, "P10", "final-identity"), p10_meta,
                   &p3_meta, p10_name, false, true, "P10", "final-identity");
        return bytes;
    } catch (const ObservationFailure&) {
        throw;
    } catch (const std::exception& e) {
        throw ObservationFailure(ErrorKind::incomplete, "P10", p10_read_profile, "reader-exception", e.what());
    } catch (...) {
        throw ObservationFailure(ErrorKind::incomplete, "P10", p10_read_profile, "reader-exception", "non-standard C++ exception");
    }
}
} // namespace stage_a::windows
