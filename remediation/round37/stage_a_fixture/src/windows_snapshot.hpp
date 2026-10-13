#pragma once

#include "snapshot.hpp"
#include <windows.h>
#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <map>
#include <string>
#include <vector>

namespace stage_a::windows {

struct OpenSpec {
    std::uint32_t access, share, disposition, options, object_attributes;
};
struct RootOpenSpec {
    std::uint32_t access, share, disposition, flags;
};
RootOpenSpec root_identity_spec();
OpenSpec ancestor_identity_spec();
OpenSpec snapshot_directory_spec();
OpenSpec snapshot_child_spec();

struct Metadata {
    std::wstring volume_guid_path, final_path, sddl;
    std::uint64_t volume_serial = 0;
    std::array<std::uint8_t, 16> file_id{};
    std::uint32_t attributes = 0, reparse_tag = 0;
    bool directory = false, dacl_protected = false;
};
struct ExpectedNode { std::wstring component; Metadata identity; };
struct SnapshotConfig {
    std::wstring volume_root_path;
    Metadata root_identity;
    std::vector<ExpectedNode> ancestors; // each is one held component under its predecessor
    ExpectedNode state_directory;         // one component under the final held ancestor
    std::map<std::string, std::wstring> child_sddl; // exact G2 owner/group/DACL for each permitted mutable child
};

std::string file_id_hex(const std::array<std::uint8_t, 16>& id);
std::string identity_key(const Metadata& identity);
bool valid_component(const std::wstring& component);
bool enumeration_end_error(std::uint32_t win32_error, bool restart);
ObservationFailure nt_failure(ErrorKind fallback, std::string object, std::string profile,
                              std::string step, std::int64_t status,
                              std::uint32_t mapped_win32, bool has_mapped_win32);
ObservationFailure win32_failure(ErrorKind fallback, std::string object, std::string profile,
                                 std::string step, std::uint32_t error);

struct NativeEntry {
    std::string name; // strict UTF-8 derived from FILE_ID_EXTD_DIR_INFO.FileName
    std::array<std::uint8_t, 16> file_id{};
    std::uint32_t attributes = 0, reparse_tag = 0;
};
struct DirectoryPage { bool end = false; std::vector<NativeEntry> entries; };
// Decodes the same bounded FILE_ID_EXTD_DIR_INFO page used by SystemNativeCalls.
// Synthetic tests may pass raw bytes here without opening a filesystem object.
DirectoryPage parse_file_id_extd_directory_buffer(const std::uint8_t* bytes, std::size_t size);
struct IdentityObservation {
    std::string object, profile, step, parent_id;
    Metadata observed;
};
struct InventoryObservation {
    std::string phase;
    std::vector<NativeEntry> entries;
    std::size_t pages = 0;
    bool explicit_end = false;
};
struct SnapshotAudit {
    // False for injected NativeCalls: synthetic records are never native file-ID evidence.
    bool system_backend = false;
    std::vector<IdentityObservation> identities;
    std::vector<InventoryObservation> inventories;
};

// NativeCalls is the read-only adapter test seam. A fake can supply metadata,
// pages and handles without opening any local filesystem object. The production
// implementation is returned only by make_system_native_calls().
class NativeCalls {
public:
    virtual ~NativeCalls() = default;
    virtual HANDLE open_root(const std::wstring& path, RootOpenSpec spec) = 0;
    virtual HANDLE open_relative(HANDLE parent, const std::wstring& component, OpenSpec spec,
                                 const std::string& object, const std::string& profile) = 0;
    virtual Metadata inspect(HANDLE handle, const std::string& object, const std::string& profile,
                             const std::string& step) = 0;
    virtual DirectoryPage next_page(HANDLE directory, bool restart) = 0;
    virtual std::string read_all(HANDLE file, std::size_t max_bytes, const std::string& object) = 0;
    virtual void close(HANDLE handle) noexcept = 0;
};

std::shared_ptr<NativeCalls> make_system_native_calls();

class WindowsSnapshotSource final : public SnapshotSource {
public:
    explicit WindowsSnapshotSource(SnapshotConfig config);
    WindowsSnapshotSource(SnapshotConfig config, std::shared_ptr<NativeCalls> calls); // synthetic tests only
    std::unique_ptr<SnapshotSession> open(std::string_view profile) override;
    std::string expected_directory_id() const;
    const SnapshotAudit& audit() const noexcept;
private:
    WindowsSnapshotSource(SnapshotConfig config, std::shared_ptr<NativeCalls> calls, bool system_backend);
    SnapshotConfig config_;
    std::shared_ptr<NativeCalls> calls_;
    std::shared_ptr<SnapshotAudit> audit_;
};

} // namespace stage_a::windows
