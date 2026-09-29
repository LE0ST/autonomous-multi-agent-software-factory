#pragma once
#include "contracts.hpp"
#include <memory>
#include <stdexcept>

namespace stage_a {

// These are requested native opens for the later Windows adapter, not a claim that
// a share flag alone defeats pre-existing writable mappings or every prior handle.
inline constexpr char directory_profile[] = "NtCreateFile:FILE_LIST_DIRECTORY|FILE_READ_ATTRIBUTES|READ_CONTROL|SYNCHRONIZE;FILE_SHARE_READ;FILE_OPEN;FILE_DIRECTORY_FILE|FILE_OPEN_REPARSE_POINT|FILE_OPEN_FOR_BACKUP_INTENT|FILE_SYNCHRONOUS_IO_NONALERT;OBJ_CASE_INSENSITIVE|OBJ_DONT_REPARSE";
inline constexpr char child_profile[] = "NtCreateFile:FILE_READ_DATA|FILE_READ_ATTRIBUTES|READ_CONTROL|SYNCHRONIZE;FILE_SHARE_READ;FILE_OPEN;FILE_NON_DIRECTORY_FILE|FILE_OPEN_REPARSE_POINT|FILE_SYNCHRONOUS_IO_NONALERT;OBJ_CASE_INSENSITIVE|OBJ_DONT_REPARSE";
inline constexpr char general_identity_profile[] = "protected-object identity/read: operation-specific access;default FILE_SHARE_READ|FILE_SHARE_WRITE without FILE_SHARE_DELETE;never a mutable snapshot profile";

struct Entry { std::string name, type, file_id, parent_id; bool reparse = false; };
struct ObservationFailure : std::runtime_error {
    ErrorKind kind;
    std::string object, profile, step;
    std::int64_t ntstatus;
    std::uint32_t win32_error;
    bool has_ntstatus, has_win32_error;
    ObservationFailure(ErrorKind k, std::string o, std::string p, std::string s, std::string message,
                       std::int64_t nt = 0, bool has_nt = false, std::uint32_t win = 0, bool has_win = false);
};

// A native adapter must own and retain the verified ancestor, directory and every
// present child HANDLE for this session's lifetime. hold_child opens one component
// relative to the held directory; read_child reads that held HANDLE. No relaxed retry.
class SnapshotSession {
public:
    virtual ~SnapshotSession() = default;
    virtual std::string directory_identity() = 0;
    virtual std::vector<Entry> inventory() = 0; // complete independent enumeration or throw
    virtual void hold_child(const std::string& name) = 0;
    virtual std::string held_identity(const std::string& name) = 0;
    virtual std::string read_child(const std::string& name) = 0;
};
class SnapshotSource {
public:
    virtual ~SnapshotSource() = default;
    virtual std::unique_ptr<SnapshotSession> open(std::string_view profile) = 0;
};

// The normal entrypoint below always uses the BCrypt-backed sha256 and
// mutable_digest functions. This narrow interface exists only to inject
// deterministic provider failures in the synthetic comparison tests.
class SnapshotHashProvider {
public:
    virtual ~SnapshotHashProvider() = default;
    virtual std::string hash_p11(std::string_view bytes) = 0;
    virtual std::string digest_mutable_set(const std::map<std::string, std::string>& files) = 0;
};

Evidence compare_fresh_controller(SnapshotSource& source, const FixtureCase& fixture,
                                  std::string_view expected_directory_id,
                                  std::string_view protected_p11_bytes,
                                  std::string_view rendered_p10_sha256,
                                  bool process_reached, bool broker_read_reached);
namespace test_seam {
Evidence compare_with_hash_provider(SnapshotSource& source, const FixtureCase& fixture,
                                    std::string_view expected_directory_id,
                                    std::string_view protected_p11_bytes,
                                    std::string_view rendered_p10_sha256,
                                    bool process_reached, bool broker_read_reached,
                                    SnapshotHashProvider& hash_provider);
}
} // namespace stage_a
