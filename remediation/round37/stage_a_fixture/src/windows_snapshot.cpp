#include "windows_snapshot.hpp"

#include <aclapi.h>
#include <sddl.h>
#include <winternl.h>
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstring>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <utility>

namespace stage_a::windows {
namespace {
constexpr std::size_t max_child_bytes = 1048576;
constexpr std::size_t max_pages = 16;
constexpr std::size_t max_entries = 32;
constexpr std::size_t directory_buffer_bytes = 65536;
constexpr std::int64_t status_sharing_violation = static_cast<std::int32_t>(0xC0000043u);

std::string utf8(const std::wstring& wide) {
    if (wide.empty()) return {};
    if (wide.size() > static_cast<std::size_t>((std::numeric_limits<int>::max)()))
        throw std::length_error("UTF-16 name too long");
    const int count = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide.data(),
                                         static_cast<int>(wide.size()), nullptr, 0, nullptr, nullptr);
    if (count <= 0) throw std::runtime_error("invalid UTF-16 from Windows");
    std::string out(static_cast<std::size_t>(count), '\0');
    if (WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide.data(),
                            static_cast<int>(wide.size()), out.data(), count, nullptr, nullptr) != count)
        throw std::runtime_error("UTF-16 conversion changed");
    return out;
}
std::wstring wide_component(const std::string& name) {
    if (name.empty() || name.size() > 255) throw std::invalid_argument("invalid child length");
    const int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, name.data(),
                                          static_cast<int>(name.size()), nullptr, 0);
    if (count <= 0) throw std::invalid_argument("invalid child UTF-8");
    std::wstring out(static_cast<std::size_t>(count), L'\0');
    if (MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, name.data(),
                            static_cast<int>(name.size()), out.data(), count) != count || !valid_component(out))
        throw std::invalid_argument("invalid child component");
    return out;
}
bool nonzero_id(const std::array<std::uint8_t, 16>& id) {
    return std::any_of(id.begin(), id.end(), [](std::uint8_t b) { return b != 0; });
}
bool same_identity(const Metadata& a, const Metadata& b) {
    return a.volume_guid_path == b.volume_guid_path && a.final_path == b.final_path &&
           a.sddl == b.sddl && a.volume_serial == b.volume_serial && a.file_id == b.file_id &&
           a.directory == b.directory && a.dacl_protected == b.dacl_protected &&
           ((a.attributes & FILE_ATTRIBUTE_REPARSE_POINT) == (b.attributes & FILE_ATTRIBUTE_REPARSE_POINT)) &&
           a.reparse_tag == b.reparse_tag;
}
void require_identity(const Metadata& actual, const Metadata& expected, const std::string& object,
                      const std::string& profile, const std::string& step) {
    if (!same_identity(actual, expected) || actual.final_path.empty() || actual.volume_guid_path.empty() ||
        actual.sddl.empty() || !nonzero_id(actual.file_id) || (actual.attributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0 || actual.reparse_tag != 0)
        throw ObservationFailure(ErrorKind::identity_drift, object, profile, step, "held identity, descriptor or reparse state differs");
}
std::wstring child_final_path(const std::wstring& parent, const std::wstring& component) {
    return parent + (parent.empty() || parent.back() == L'\\' ? L"" : L"\\") + component;
}
void require_child(const Metadata& actual, const Metadata& parent, const std::wstring& component,
                   const std::wstring& expected_sddl, const std::string& object, const std::string& step) {
    if (actual.directory || (actual.attributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_DEVICE)) != 0 ||
        !actual.dacl_protected || actual.sddl.empty() ||
        (actual.attributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0 || actual.reparse_tag != 0 ||
        actual.volume_guid_path != parent.volume_guid_path || actual.volume_serial != parent.volume_serial ||
        actual.final_path != child_final_path(parent.final_path, component) || !nonzero_id(actual.file_id) ||
        actual.sddl != expected_sddl)
        throw ObservationFailure(ErrorKind::identity_drift, object, child_profile, step, "child type, parent binding, descriptor or reparse state differs");
}
} // namespace

RootOpenSpec root_identity_spec() {
    return {FILE_READ_ATTRIBUTES | READ_CONTROL, FILE_SHARE_READ | FILE_SHARE_WRITE,
            OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT};
}
OpenSpec ancestor_identity_spec() {
    return {FILE_READ_ATTRIBUTES | READ_CONTROL | SYNCHRONIZE, FILE_SHARE_READ | FILE_SHARE_WRITE,
            FILE_OPEN, FILE_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT | FILE_OPEN_FOR_BACKUP_INTENT | FILE_SYNCHRONOUS_IO_NONALERT,
            OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE};
}
OpenSpec snapshot_directory_spec() {
    return {FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES | READ_CONTROL | SYNCHRONIZE, FILE_SHARE_READ,
            FILE_OPEN, FILE_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT | FILE_OPEN_FOR_BACKUP_INTENT | FILE_SYNCHRONOUS_IO_NONALERT,
            OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE};
}
OpenSpec snapshot_child_spec() {
    return {FILE_READ_DATA | FILE_READ_ATTRIBUTES | READ_CONTROL | SYNCHRONIZE, FILE_SHARE_READ,
            FILE_OPEN, FILE_NON_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT | FILE_SYNCHRONOUS_IO_NONALERT,
            OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE};
}
std::string file_id_hex(const std::array<std::uint8_t, 16>& id) {
    constexpr char alphabet[] = "0123456789abcdef";
    std::string out;
    out.reserve(32);
    for (const auto b : id) { out += alphabet[b >> 4]; out += alphabet[b & 15]; }
    return out;
}
std::string identity_key(const Metadata& identity) {
    return std::to_string(identity.volume_serial) + ":" + file_id_hex(identity.file_id) + ":" + utf8(identity.final_path);
}
bool valid_component(const std::wstring& component) {
    if (component.empty() || component.size() > 255 || component == L"." || component == L".." ||
        component.back() == L'.' || component.back() == L' ') return false;
    for (wchar_t c : component)
        if (!((c >= L'a' && c <= L'z') || (c >= L'A' && c <= L'Z') ||
              (c >= L'0' && c <= L'9') || c == L'_' || c == L'-' || c == L'.')) return false;
    return true;
}
bool enumeration_end_error(std::uint32_t win32_error, bool restart) {
    // A first empty directory query can map STATUS_NO_SUCH_FILE to
    // ERROR_FILE_NOT_FOUND; subsequent exhaustion maps to ERROR_NO_MORE_FILES.
    // No other Win32 failure is evidence of a complete enumeration.
    return win32_error == ERROR_NO_MORE_FILES || (restart && win32_error == ERROR_FILE_NOT_FOUND);
}
ObservationFailure nt_failure(ErrorKind fallback, std::string object, std::string profile,
                              std::string step, std::int64_t status,
                              std::uint32_t mapped_win32, bool has_mapped_win32) {
    const auto kind = status == status_sharing_violation || (has_mapped_win32 && mapped_win32 == ERROR_SHARING_VIOLATION)
        ? ErrorKind::sharing_conflict : fallback;
    return ObservationFailure(kind, std::move(object), std::move(profile), std::move(step), "NtCreateFile failed",
                              status, true, mapped_win32, has_mapped_win32);
}
ObservationFailure win32_failure(ErrorKind fallback, std::string object, std::string profile,
                                 std::string step, std::uint32_t error) {
    const auto kind = error == ERROR_SHARING_VIOLATION ? ErrorKind::sharing_conflict : fallback;
    return ObservationFailure(kind, std::move(object), std::move(profile), std::move(step), "Windows handle operation failed",
                              0, false, error, true);
}

DirectoryPage parse_file_id_extd_directory_buffer(const std::uint8_t* bytes, std::size_t size) {
    if (!size)
        throw ObservationFailure(ErrorKind::incomplete, "state/", directory_profile, "enumeration-page", "successful empty page");
    constexpr std::size_t header_size = offsetof(FILE_ID_EXTD_DIR_INFO, FileName);
    if (!bytes || size > directory_buffer_bytes || size < header_size)
        throw ObservationFailure(ErrorKind::incomplete, "state/", directory_profile, "enumeration-buffer", "invalid or truncated directory buffer");
    DirectoryPage page;
    std::size_t offset = 0;
    for (;;) {
        if (offset > size - header_size)
            throw ObservationFailure(ErrorKind::incomplete, "state/", directory_profile, "enumeration-buffer", "truncated directory header");
        FILE_ID_EXTD_DIR_INFO entry{};
        std::memcpy(&entry, bytes + offset, header_size);
        const std::size_t name_bytes = entry.FileNameLength;
        if (!name_bytes || name_bytes % sizeof(WCHAR) || name_bytes > size - offset - header_size)
            throw ObservationFailure(ErrorKind::incomplete, "state/", directory_profile, "enumeration-buffer", "truncated directory name");
        std::wstring wide(name_bytes / sizeof(WCHAR), L'\0');
        std::memcpy(wide.data(), bytes + offset + header_size, name_bytes);
        NativeEntry result;
        try { result.name = utf8(wide); }
        catch (const std::exception& failure) {
            throw ObservationFailure(ErrorKind::malformed, "state/", directory_profile, "enumeration-name", failure.what());
        }
        std::memcpy(result.file_id.data(), entry.FileId.Identifier, result.file_id.size());
        result.attributes = entry.FileAttributes;
        result.reparse_tag = entry.ReparsePointTag;
        if ((result.attributes & FILE_ATTRIBUTE_DEVICE) != 0)
            throw ObservationFailure(ErrorKind::identity_drift, result.name, child_profile, "enumeration-type", "device-marked state child is not a regular file");
        page.entries.push_back(std::move(result));
        if (entry.NextEntryOffset == 0) break;
        const auto next = static_cast<std::size_t>(entry.NextEntryOffset);
        if (next % 8 || next < header_size + name_bytes || next > size - offset)
            throw ObservationFailure(ErrorKind::incomplete, "state/", directory_profile, "enumeration-buffer", "invalid next entry offset");
        offset += next;
    }
    if (page.entries.empty())
        throw ObservationFailure(ErrorKind::incomplete, "state/", directory_profile, "enumeration-page", "successful empty page");
    return page;
}

namespace {
class SystemNativeCalls final : public NativeCalls {
public:
    HANDLE open_root(const std::wstring& path, RootOpenSpec spec) override {
        const HANDLE handle = CreateFileW(path.c_str(), spec.access, spec.share, nullptr,
                                          spec.disposition, spec.flags, nullptr);
        if (handle == INVALID_HANDLE_VALUE)
            throw win32_failure(ErrorKind::native_failure, "volume-root", general_identity_profile, "open-root", GetLastError());
        return handle;
    }
    HANDLE open_relative(HANDLE parent, const std::wstring& component, OpenSpec spec,
                         const std::string& object, const std::string& profile) override {
        if (!valid_component(component) || component.size() > USHRT_MAX / sizeof(WCHAR))
            throw ObservationFailure(ErrorKind::malformed, object, profile, "relative-component", "component is not one reviewed name");
        UNICODE_STRING name{};
        name.Length = static_cast<USHORT>(component.size() * sizeof(WCHAR));
        name.MaximumLength = name.Length;
        name.Buffer = const_cast<PWSTR>(component.data());
        OBJECT_ATTRIBUTES attributes{};
        InitializeObjectAttributes(&attributes, &name, spec.object_attributes, parent, nullptr);
        IO_STATUS_BLOCK iosb{};
        HANDLE handle = nullptr;
        const NTSTATUS status = NtCreateFile(&handle, spec.access, &attributes, &iosb, nullptr, 0,
                                             spec.share, spec.disposition, spec.options, nullptr, 0);
        if (status < 0) {
            const ULONG mapped = RtlNtStatusToDosError(status);
            throw nt_failure(ErrorKind::native_failure, object, profile, "relative-open", status,
                             mapped, mapped != ERROR_MR_MID_NOT_FOUND);
        }
        if (!handle || handle == INVALID_HANDLE_VALUE)
            throw ObservationFailure(ErrorKind::incomplete, object, profile, "relative-open", "successful status without a valid handle",
                                     status, true);
        return handle;
    }
    Metadata inspect(HANDLE handle, const std::string& object, const std::string& profile,
                     const std::string& step) override {
        FILE_ID_INFO id{};
        if (!GetFileInformationByHandleEx(handle, FileIdInfo, &id, sizeof(id)))
            throw win32_failure(ErrorKind::native_failure, object, profile, step + "/FileIdInfo", GetLastError());
        FILE_ATTRIBUTE_TAG_INFO tag{};
        if (!GetFileInformationByHandleEx(handle, FileAttributeTagInfo, &tag, sizeof(tag)))
            throw win32_failure(ErrorKind::native_failure, object, profile, step + "/FileAttributeTagInfo", GetLastError());
        if (profile == child_profile && (tag.FileAttributes & FILE_ATTRIBUTE_DEVICE) != 0)
            throw ObservationFailure(ErrorKind::identity_drift, object, profile, step + "/FileAttributeTagInfo", "device-marked held child is not a regular file");
        FILE_STANDARD_INFO standard{};
        if (!GetFileInformationByHandleEx(handle, FileStandardInfo, &standard, sizeof(standard)))
            throw win32_failure(ErrorKind::native_failure, object, profile, step + "/FileStandardInfo", GetLastError());
        constexpr DWORD path_flags = VOLUME_NAME_GUID | FILE_NAME_NORMALIZED;
        const DWORD needed = GetFinalPathNameByHandleW(handle, nullptr, 0, path_flags);
        if (!needed)
            throw win32_failure(ErrorKind::native_failure, object, profile, step + "/final-path-size", GetLastError());
        if (needed > 32767)
            throw ObservationFailure(ErrorKind::incomplete, object, profile, step + "/final-path-size", "final path exceeds reviewed bound");
        std::wstring path(static_cast<std::size_t>(needed) + 1, L'\0');
        const DWORD written = GetFinalPathNameByHandleW(handle, path.data(), static_cast<DWORD>(path.size()), path_flags);
        if (!written)
            throw win32_failure(ErrorKind::native_failure, object, profile, step + "/final-path", GetLastError());
        if (written >= path.size())
            throw ObservationFailure(ErrorKind::incomplete, object, profile, step + "/final-path", "final path changed or exceeded buffer");
        path.resize(written);
        const std::wstring prefix = L"\\\\?\\Volume{";
        if (path.rfind(prefix, 0) != 0)
            throw ObservationFailure(ErrorKind::identity_drift, object, profile, step + "/volume-guid", "final path is not a volume GUID path");
        const auto close = path.find(L'}', prefix.size());
        if (close == std::wstring::npos || close + 1 >= path.size() || path[close + 1] != L'\\')
            throw ObservationFailure(ErrorKind::identity_drift, object, profile, step + "/volume-guid", "malformed volume GUID path");
        PSECURITY_DESCRIPTOR descriptor = nullptr;
        const DWORD security_error = GetSecurityInfo(handle, SE_FILE_OBJECT,
            OWNER_SECURITY_INFORMATION | GROUP_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
            nullptr, nullptr, nullptr, nullptr, &descriptor);
        if (security_error != ERROR_SUCCESS)
            throw win32_failure(ErrorKind::native_failure, object, profile, step + "/security", security_error);
        LPWSTR text = nullptr;
        SECURITY_DESCRIPTOR_CONTROL control{};
        DWORD revision = 0;
        const BOOL got_control = GetSecurityDescriptorControl(descriptor, &control, &revision);
        const BOOL got_sddl = got_control && ConvertSecurityDescriptorToStringSecurityDescriptorW(descriptor,
            SDDL_REVISION_1, OWNER_SECURITY_INFORMATION | GROUP_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
            &text, nullptr);
        const DWORD conversion_error = got_sddl ? ERROR_SUCCESS : GetLastError();
        std::wstring sddl = text ? text : L"";
        if (text) LocalFree(text);
        LocalFree(descriptor);
        if (!got_sddl)
            throw win32_failure(ErrorKind::native_failure, object, profile, step + "/sddl", conversion_error);
        Metadata result;
        result.volume_guid_path = path.substr(0, close + 2);
        result.final_path = std::move(path);
        result.sddl = std::move(sddl);
        result.volume_serial = id.VolumeSerialNumber;
        std::memcpy(result.file_id.data(), id.FileId.Identifier, result.file_id.size());
        result.attributes = tag.FileAttributes;
        result.reparse_tag = tag.ReparseTag;
        result.directory = standard.Directory != FALSE;
        result.dacl_protected = (control & SE_DACL_PROTECTED) != 0;
        return result;
    }
    DirectoryPage next_page(HANDLE directory, bool restart) override {
        alignas(FILE_ID_EXTD_DIR_INFO) std::array<std::uint8_t, directory_buffer_bytes> buffer{};
        const auto info_class = restart ? FileIdExtdDirectoryRestartInfo : FileIdExtdDirectoryInfo;
        if (!GetFileInformationByHandleEx(directory, info_class, buffer.data(), static_cast<DWORD>(buffer.size()))) {
            const DWORD error = GetLastError();
            if (enumeration_end_error(error, restart)) return {true, {}};
            const ErrorKind kind = error == ERROR_MORE_DATA || error == ERROR_INSUFFICIENT_BUFFER
                ? ErrorKind::incomplete : ErrorKind::native_failure;
            throw win32_failure(kind, "state/", directory_profile, "enumeration-page", error);
        }
        return parse_file_id_extd_directory_buffer(buffer.data(), buffer.size());
    }
    std::string read_all(HANDLE file, std::size_t max_bytes, const std::string& object) override {
        FILE_STANDARD_INFO initial{};
        if (!GetFileInformationByHandleEx(file, FileStandardInfo, &initial, sizeof(initial)))
            throw win32_failure(ErrorKind::incomplete, object, child_profile, "read-size", GetLastError());
        if (initial.Directory || initial.EndOfFile.QuadPart < 0 ||
            static_cast<std::uint64_t>(initial.EndOfFile.QuadPart) > max_bytes)
            throw ObservationFailure(ErrorKind::incomplete, object, child_profile, "read-size", "unexpected type or oversized child");
        LARGE_INTEGER zero{};
        if (!SetFilePointerEx(file, zero, nullptr, FILE_BEGIN))
            throw win32_failure(ErrorKind::incomplete, object, child_profile, "read-seek", GetLastError());
        const auto expected = static_cast<std::size_t>(initial.EndOfFile.QuadPart);
        std::string result(expected, '\0');
        std::size_t done = 0;
        while (done < expected) {
            DWORD got = 0;
            const DWORD requested = static_cast<DWORD>((std::min)(expected - done, static_cast<std::size_t>(65536)));
            if (!ReadFile(file, result.data() + done, requested, &got, nullptr))
                throw win32_failure(ErrorKind::incomplete, object, child_profile, "read-child", GetLastError());
            if (!got) throw ObservationFailure(ErrorKind::incomplete, object, child_profile, "read-child", "early EOF");
            done += got;
        }
        char extra = 0;
        DWORD got = 0;
        if (!ReadFile(file, &extra, 1, &got, nullptr))
            throw win32_failure(ErrorKind::incomplete, object, child_profile, "read-eof", GetLastError());
        if (got) throw ObservationFailure(ErrorKind::identity_drift, object, child_profile, "read-eof", "content grew during read");
        FILE_STANDARD_INFO final{};
        if (!GetFileInformationByHandleEx(file, FileStandardInfo, &final, sizeof(final)))
            throw win32_failure(ErrorKind::incomplete, object, child_profile, "final-read-size", GetLastError());
        if (final.EndOfFile.QuadPart != initial.EndOfFile.QuadPart || final.Directory)
            throw ObservationFailure(ErrorKind::identity_drift, object, child_profile, "final-read-size", "content size drift");
        return result;
    }
    void close(HANDLE handle) noexcept override { if (handle && handle != INVALID_HANDLE_VALUE) CloseHandle(handle); }
};

class WindowsSession final : public SnapshotSession {
public:
    WindowsSession(SnapshotConfig config, std::shared_ptr<NativeCalls> calls, std::shared_ptr<SnapshotAudit> audit)
        : config_(std::move(config)), calls_(std::move(calls)), audit_(std::move(audit)) {}
    ~WindowsSession() override {
        for (auto it = handles_.rbegin(); it != handles_.rend(); ++it) calls_->close(*it);
    }
    void initialize() {
        HANDLE current = calls_->open_root(config_.volume_root_path, root_identity_spec());
        handles_.push_back(current);
        verified_.push_back({current, config_.root_identity, "volume-root", general_identity_profile, ""});
        verify_node(verified_.back(), "root-identity");
        Metadata parent = config_.root_identity;
        for (const auto& ancestor : config_.ancestors) {
            current = calls_->open_relative(current, ancestor.component, ancestor_identity_spec(),
                                            utf8(ancestor.component), general_identity_profile);
            handles_.push_back(current);
            verified_.push_back({current, ancestor.identity, utf8(ancestor.component), general_identity_profile, identity_key(parent)});
            verify_node(verified_.back(), "ancestor-identity");
            require_parent_binding(ancestor.identity, parent, ancestor.component, utf8(ancestor.component), general_identity_profile);
            parent = ancestor.identity;
        }
        current = calls_->open_relative(current, config_.state_directory.component, snapshot_directory_spec(),
                                        "state/", directory_profile);
        handles_.push_back(current);
        directory_ = current;
        verified_.push_back({current, config_.state_directory.identity, "state/", directory_profile, identity_key(parent)});
        verify_node(verified_.back(), "state-directory-identity");
        require_parent_binding(config_.state_directory.identity, parent, config_.state_directory.component, "state/", directory_profile);
    }
    std::string directory_identity() override {
        for (const auto& node : verified_) verify_node(node, "held-identity");
        return identity_key(config_.state_directory.identity);
    }
    std::vector<Entry> inventory() override {
        directory_identity();
        std::vector<Entry> result;
        std::map<std::string, NativeEntry> observed;
        audit_->inventories.push_back({initial_inventory_set_ ? "final" : "initial", {}, 0, false});
        auto& audit_inventory = audit_->inventories.back();
        bool ended = false;
        for (std::size_t page_number = 0; page_number < max_pages; ++page_number) {
            const auto page = calls_->next_page(directory_, page_number == 0);
            if (page.end) { ended = true; break; }
            ++audit_inventory.pages;
            if (page.entries.empty())
                throw ObservationFailure(ErrorKind::incomplete, "state/", directory_profile, "enumeration-page", "empty data page");
            for (const auto& native : page.entries) {
                if (native.name == "." || native.name == "..") continue;
                audit_inventory.entries.push_back(native);
                if ((native.attributes & FILE_ATTRIBUTE_DEVICE) != 0)
                    throw ObservationFailure(ErrorKind::identity_drift, native.name, child_profile, "enumeration-type", "device-marked state child is not a regular file");
                if (result.size() >= max_entries)
                    throw ObservationFailure(ErrorKind::incomplete, "state/", directory_profile, "enumeration-limit", "state entry limit exceeded");
                if (native.name.empty() || !observed.emplace(native.name, native).second)
                    throw ObservationFailure(ErrorKind::malformed, native.name, directory_profile, "enumeration-entry", "empty or duplicate name");
                const bool reparse = (native.attributes & FILE_ATTRIBUTE_REPARSE_POINT) != 0 || native.reparse_tag != 0;
                const bool directory = (native.attributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
                result.push_back({native.name, directory ? "directory" : "regular", file_id_hex(native.file_id),
                                  identity_key(config_.state_directory.identity), reparse});
            }
        }
        if (!ended)
            throw ObservationFailure(ErrorKind::incomplete, "state/", directory_profile, "enumeration-limit", "no explicit enumeration end");
        audit_inventory.explicit_end = true;
        if (!initial_inventory_set_) { initial_inventory_ = std::move(observed); initial_inventory_set_ = true; }
        return result;
    }
    void hold_child(const std::string& name) override {
        if (!initial_inventory_set_ || !initial_inventory_.contains(name) || children_.contains(name))
            throw ObservationFailure(ErrorKind::incomplete, name, child_profile, "hold-child", "child absent from initial inventory or already held");
        if (!config_.child_sddl.contains(name))
            throw ObservationFailure(ErrorKind::unexpected_entry, name, child_profile, "hold-child", "child absent from exact descriptor manifest");
        std::wstring component;
        try { component = wide_component(name); }
        catch (const std::exception& failure) {
            throw ObservationFailure(ErrorKind::malformed, name, child_profile, "hold-child-name", failure.what());
        }
        const HANDLE handle = calls_->open_relative(directory_, component, snapshot_child_spec(), name, child_profile);
        handles_.push_back(handle);
        const auto actual = calls_->inspect(handle, name, child_profile, "hold-child-identity");
        audit_->identities.push_back({name, child_profile, "hold-child-identity", identity_key(config_.state_directory.identity), actual});
        require_child(actual, config_.state_directory.identity, component, config_.child_sddl.at(name), name, "hold-child-identity");
        if (file_id_hex(actual.file_id) != file_id_hex(initial_inventory_.at(name).file_id))
            throw ObservationFailure(ErrorKind::identity_drift, name, child_profile, "hold-child-identity", "opened child differs from directory entry");
        children_.emplace(name, Child{handle, std::move(component), actual});
    }
    std::string held_identity(const std::string& name) override {
        const auto& child = find_child(name);
        const auto actual = calls_->inspect(child.handle, name, child_profile, "held-child-identity");
        audit_->identities.push_back({name, child_profile, "held-child-identity", identity_key(config_.state_directory.identity), actual});
        require_child(actual, config_.state_directory.identity, child.component, config_.child_sddl.at(name), name, "held-child-identity");
        require_identity(actual, child.initial, name, child_profile, "held-child-identity");
        return file_id_hex(actual.file_id);
    }
    std::string read_child(const std::string& name) override {
        const auto& child = find_child(name);
        return calls_->read_all(child.handle, max_child_bytes, name);
    }
private:
    struct Verified { HANDLE handle; Metadata expected; std::string object, profile, parent_id; };
    struct Child { HANDLE handle; std::wstring component; Metadata initial; };
    static void require_parent_binding(const Metadata& actual, const Metadata& parent,
                                       const std::wstring& component, const std::string& object,
                                       const std::string& profile) {
        if (actual.volume_guid_path != parent.volume_guid_path || actual.volume_serial != parent.volume_serial ||
            actual.final_path != child_final_path(parent.final_path, component))
            throw ObservationFailure(ErrorKind::identity_drift, object, profile, "parent-binding", "held node does not bind to held parent");
    }
    void verify_node(const Verified& node, const std::string& step) const {
        const auto actual = calls_->inspect(node.handle, node.object, node.profile, step);
        audit_->identities.push_back({node.object, node.profile, step, node.parent_id, actual});
        require_identity(actual, node.expected, node.object, node.profile, step);
        if (!actual.directory)
            throw ObservationFailure(ErrorKind::identity_drift, node.object, node.profile, step, "expected held directory");
    }
    const Child& find_child(const std::string& name) const {
        const auto found = children_.find(name);
        if (found == children_.end())
            throw ObservationFailure(ErrorKind::incomplete, name, child_profile, "held-child", "child handle is not held");
        return found->second;
    }
    SnapshotConfig config_;
    std::shared_ptr<NativeCalls> calls_;
    std::shared_ptr<SnapshotAudit> audit_;
    std::vector<HANDLE> handles_;
    std::vector<Verified> verified_;
    HANDLE directory_ = nullptr;
    bool initial_inventory_set_ = false;
    std::map<std::string, NativeEntry> initial_inventory_;
    std::map<std::string, Child> children_;
};
} // namespace

std::shared_ptr<NativeCalls> make_system_native_calls() { return std::make_shared<SystemNativeCalls>(); }
WindowsSnapshotSource::WindowsSnapshotSource(SnapshotConfig config)
    : WindowsSnapshotSource(std::move(config), make_system_native_calls(), true) {}
WindowsSnapshotSource::WindowsSnapshotSource(SnapshotConfig config, std::shared_ptr<NativeCalls> calls)
    : WindowsSnapshotSource(std::move(config), std::move(calls), false) {}
WindowsSnapshotSource::WindowsSnapshotSource(SnapshotConfig config, std::shared_ptr<NativeCalls> calls, bool system_backend)
    : config_(std::move(config)), calls_(std::move(calls)), audit_(std::make_shared<SnapshotAudit>()) {
    audit_->system_backend = system_backend;
    if (!calls_ || config_.volume_root_path.size() != 3 || config_.volume_root_path[1] != L':' ||
        config_.volume_root_path[2] != L'\\' || config_.ancestors.size() != 2 ||
        !valid_component(config_.ancestors[0].component) || !valid_component(config_.ancestors[1].component) ||
        !valid_component(config_.state_directory.component) || config_.root_identity.final_path.empty() ||
        config_.state_directory.identity.final_path.empty())
        throw std::invalid_argument("incomplete reviewed snapshot configuration");
    if (config_.child_sddl.size() != 3 || !config_.child_sddl.contains("lock.bin") ||
        !config_.child_sddl.contains("state.json") || !config_.child_sddl.contains("witness.txt") ||
        config_.child_sddl.at("lock.bin").empty() || config_.child_sddl.at("state.json").empty() ||
        config_.child_sddl.at("witness.txt").empty())
        throw std::invalid_argument("exact three-child descriptor manifest is required");
}
std::unique_ptr<SnapshotSession> WindowsSnapshotSource::open(std::string_view profile) {
    if (profile != directory_profile)
        throw ObservationFailure(ErrorKind::binding_failure, "state/", std::string(profile), "snapshot-profile", "unsupported snapshot profile");
    audit_->identities.clear();
    audit_->inventories.clear();
    auto session = std::make_unique<WindowsSession>(config_, calls_, audit_);
    session->initialize();
    return session;
}
std::string WindowsSnapshotSource::expected_directory_id() const { return identity_key(config_.state_directory.identity); }
const SnapshotAudit& WindowsSnapshotSource::audit() const noexcept { return *audit_; }
} // namespace stage_a::windows
