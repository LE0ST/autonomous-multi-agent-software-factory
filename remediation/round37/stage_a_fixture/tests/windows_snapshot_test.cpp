#include "../src/windows_snapshot.hpp"
#include <winternl.h>
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using namespace stage_a;
using namespace stage_a::windows;
namespace {
int checks = 0;
void require(bool truth, const char* message) {
    ++checks;
    if (!truth) throw std::runtime_error(message);
}
template<class Fn> ObservationFailure expect_failure(Fn operation) {
    try { operation(); }
    catch (const ObservationFailure& failure) { ++checks; return failure; }
    throw std::runtime_error("expected typed observation failure");
}
constexpr wchar_t volume[] = L"\\\\?\\Volume{00000000-0000-0000-0000-000000000001}\\";
std::wstring append(const std::wstring& parent, const std::wstring& component) {
    return parent + (parent.back() == L'\\' ? L"" : L"\\") + component;
}
std::string ascii_name(const std::wstring& component) {
    std::string result;
    for (const wchar_t character : component) {
        require(character <= 127, "synthetic fixture name is ASCII");
        result.push_back(static_cast<char>(character));
    }
    return result;
}
Metadata metadata(std::uint8_t id, std::wstring path, bool directory) {
    Metadata result;
    result.volume_guid_path = volume;
    result.final_path = std::move(path);
    result.sddl = L"O:BAG:BAD:P(A;;FA;;;SY)";
    result.volume_serial = 42;
    result.file_id[0] = id;
    result.attributes = directory ? FILE_ATTRIBUTE_DIRECTORY : FILE_ATTRIBUTE_NORMAL;
    result.directory = directory;
    result.dacl_protected = true;
    return result;
}
SnapshotConfig configuration() {
    SnapshotConfig config;
    config.volume_root_path = L"G:\\";
    config.root_identity = metadata(1, volume, true);
    const auto first = append(config.root_identity.final_path, L"S1PF_260926_A");
    const auto second = append(first, L"work");
    config.ancestors = {{L"S1PF_260926_A", metadata(2, first, true)},
                        {L"work", metadata(3, second, true)}};
    config.state_directory = {L"state", metadata(4, append(second, L"state"), true)};
    config.child_sddl = {{"lock.bin", L"O:BAG:BAD:P(A;;FA;;;SY)"},
                         {"state.json", L"O:BAG:BAD:P(A;;FA;;;SY)"},
                         {"witness.txt", L"O:BAG:BAD:P(A;;FA;;;SY)"}};
    return config;
}
HANDLE handle_of(std::uintptr_t number) { return reinterpret_cast<HANDLE>(number); }
struct OpenRecord { HANDLE parent; std::wstring component; OpenSpec spec; std::string profile; };
class FakeNativeCalls final : public NativeCalls {
public:
    explicit FakeNativeCalls(SnapshotConfig config, std::map<std::string, std::string> bytes)
        : config_(std::move(config)), bytes_(std::move(bytes)) {
        nodes_[L"S1PF_260926_A"] = config_.ancestors[0].identity;
        nodes_[L"work"] = config_.ancestors[1].identity;
        nodes_[L"state"] = config_.state_directory.identity;
        std::uint8_t id = 5;
        for (const auto& [name, ignored] : bytes_) {
            (void)ignored;
            const std::wstring component(name.begin(), name.end());
            nodes_[component] = metadata(id++, append(config_.state_directory.identity.final_path, component), false);
        }
    }
    HANDLE open_root(const std::wstring& path, RootOpenSpec spec) override {
        require(path == L"G:\\", "synthetic root path");
        root_spec = spec;
        return add(config_.root_identity, L"root");
    }
    HANDLE open_relative(HANDLE parent, const std::wstring& component, OpenSpec spec,
                         const std::string&, const std::string& profile) override {
        require(live_.contains(parent), "relative open uses held parent");
        opened.push_back({parent, component, spec, profile});
        if (fail_open_component == component)
            throw nt_failure(ErrorKind::native_failure, ascii_name(component), profile,
                             "relative-open", static_cast<std::int32_t>(0xC0000043u), 32, true);
        const auto found = nodes_.find(component);
        require(found != nodes_.end(), "synthetic component exists");
        require(found->second.final_path == append(live_.at(parent).final_path, component), "synthetic held parent binding");
        return add(found->second, component);
    }
    Metadata inspect(HANDLE handle, const std::string& object, const std::string& profile,
                     const std::string& step) override {
        require(live_.contains(handle), "inspect uses held handle");
        if (fail_inspect_step == step)
            throw win32_failure(ErrorKind::incomplete, object, profile, step, ERROR_ACCESS_DENIED);
        auto result = live_.at(handle);
        if (device_child_metadata && step == "hold-child-identity" && names_.at(handle) == L"lock.bin")
            result.attributes |= FILE_ATTRIBUTE_DEVICE;
        if (wrong_child_descriptor && step == "hold-child-identity" && names_.at(handle) == L"lock.bin")
            result.sddl = L"O:BAG:BAD:P(A;;FA;;;WD)";
        if (drift_on_final && step == "held-child-identity" && names_.at(handle) == L"lock.bin" && ++lock_inspections_ >= 2)
            result.file_id[0] = 88;
        return result;
    }
    DirectoryPage next_page(HANDLE directory, bool restart) override {
        require(live_.contains(directory) && live_.at(directory).directory, "enumeration uses held directory");
        if (restart) { ++scan_; page_ = 0; }
        require(scan_ >= 0, "enumeration began with restart");
        if (enumeration_error)
            throw win32_failure(ErrorKind::incomplete, "state/", directory_profile,
                                "enumeration-page", ERROR_MORE_DATA);
        if (truncated) {
            NativeEntry entry;
            entry.name = "synthetic_page_" + std::to_string(page_++);
            entry.file_id[0] = static_cast<std::uint8_t>(page_);
            entry.attributes = FILE_ATTRIBUTE_NORMAL;
            return {false, {entry}};
        }
        if (scan_ == 0 && raw_initial_buffer) {
            if (page_++ == 0) return parse_file_id_extd_directory_buffer(raw_initial_buffer->data(), raw_initial_buffer->size());
            return {true, {}};
        }
        if (scan_ == 1 && raw_final_buffer) {
            if (page_++ == 0) return parse_file_id_extd_directory_buffer(raw_final_buffer->data(), raw_final_buffer->size());
            return {true, {}};
        }
        if (scan_ == 0 && !initial_pages_override.empty()) {
            if (page_ < initial_pages_override.size()) return {false, initial_pages_override[page_++]};
            return {true, {}};
        }
        if (scan_ == 0 && initial_entries_override) {
            if (page_++ == 0) return {false, *initial_entries_override};
            return {true, {}};
        }
        if (scan_ == 1 && final_entries_override) {
            if (page_++ == 0) return {false, *final_entries_override};
            return {true, {}};
        }
        if (page_++ == 0 && !bytes_.empty()) return {false, generated_entries()};
        return {true, {}};
    }
    std::string read_all(HANDLE file, std::size_t max_bytes, const std::string& object) override {
        require(live_.contains(file) && !live_.at(file).directory, "read uses held regular child");
        require(max_bytes == 1048576, "child read cap");
        const auto listed = initial_entries_override ? initial_entries_override->size() : bytes_.size();
        require(live_.size() == 4 + listed, "all listed child handles held before first read");
        if (fail_read)
            throw win32_failure(ErrorKind::incomplete, object, child_profile, "read-child", ERROR_READ_FAULT);
        const auto component = names_.at(file);
        return bytes_.at(ascii_name(component));
    }
    void close(HANDLE handle) noexcept override {
        closed.push_back(handle);
        live_.erase(handle);
        names_.erase(handle);
    }
    std::vector<NativeEntry> generated_entries() const {
        std::vector<NativeEntry> result;
        for (const auto& [name, ignored] : bytes_) {
            (void)ignored;
            const std::wstring component(name.begin(), name.end());
            const auto& node = nodes_.at(component);
            result.push_back({name, node.file_id, node.attributes, node.reparse_tag});
        }
        return result;
    }
    std::size_t live_count() const { return live_.size(); }
    std::vector<OpenRecord> opened;
    std::vector<HANDLE> closed;
    RootOpenSpec root_spec{};
    std::wstring fail_open_component;
    std::string fail_inspect_step;
    bool enumeration_error = false, truncated = false, fail_read = false, drift_on_final = false;
    bool wrong_child_descriptor = false, device_child_metadata = false;
    std::unique_ptr<std::vector<std::uint8_t>> raw_initial_buffer, raw_final_buffer;
    std::vector<std::vector<NativeEntry>> initial_pages_override;
    std::unique_ptr<std::vector<NativeEntry>> initial_entries_override;
    std::unique_ptr<std::vector<NativeEntry>> final_entries_override;
private:
    HANDLE add(const Metadata& node, const std::wstring& name) {
        const HANDLE handle = handle_of(++last_handle_);
        live_[handle] = node;
        names_[handle] = name;
        return handle;
    }
    SnapshotConfig config_;
    std::map<std::string, std::string> bytes_;
    std::map<std::wstring, Metadata> nodes_;
    std::map<HANDLE, Metadata> live_;
    std::map<HANDLE, std::wstring> names_;
    std::uintptr_t last_handle_ = 0;
    int scan_ = -1;
    unsigned page_ = 0, lock_inspections_ = 0;
};
Evidence compare(WindowsSnapshotSource& source, const FixtureCase& fixture) {
    const auto p10 = sha256("synthetic G2 P10; no host binding");
    return compare_fresh_controller(source, fixture, source.expected_directory_id(),
                                    render_p11(fixture, p10), p10, true, true);
}
void require_stop(const Evidence& result, ErrorKind kind, const char* step) {
    if (result.error != kind || result.step != step)
        std::cerr << "Observed stop: error=" << static_cast<int>(result.error)
                  << " step=" << result.step << " object=" << result.object << '\n';
    require(result.verdict == Verdict::stop_inconclusive, "native failure stops inconclusively");
    require(!result.snapshot_complete, "failed native observation is incomplete");
    require(result.error == kind, "native error category");
    require(result.step == step, "native failed step");
}

// Independent literal FILE_ID_EXTD_DIR_INFO wire offsets on the pinned x64 SDK.
// These writers encode bytes directly; they never construct the parser's struct.
constexpr std::size_t raw_header = 88, raw_attributes = 56, raw_name_length = 60;
constexpr std::size_t raw_reparse_tag = 68, raw_file_id = 72, raw_name = 88;
static_assert(offsetof(FILE_ID_EXTD_DIR_INFO, FileAttributes) == raw_attributes);
static_assert(offsetof(FILE_ID_EXTD_DIR_INFO, FileNameLength) == raw_name_length);
static_assert(offsetof(FILE_ID_EXTD_DIR_INFO, ReparsePointTag) == raw_reparse_tag);
static_assert(offsetof(FILE_ID_EXTD_DIR_INFO, FileId) == raw_file_id);
static_assert(offsetof(FILE_ID_EXTD_DIR_INFO, FileName) == raw_name);
void put_u32(std::vector<std::uint8_t>& bytes, std::size_t at, std::uint32_t value) {
    if (at + 4 > bytes.size()) throw std::runtime_error("raw test writer exceeds buffer");
    for (unsigned shift = 0; shift < 32; shift += 8)
        bytes[at + shift / 8] = static_cast<std::uint8_t>(value >> shift);
}
void put_raw_record(std::vector<std::uint8_t>& bytes, std::size_t at, std::uint32_t next,
                    const std::string& name, std::uint32_t attributes, std::uint8_t file_id,
                    std::uint32_t reparse_tag = 0) {
    if (at + raw_header + name.size() * 2 > bytes.size())
        throw std::runtime_error("raw test record exceeds buffer");
    put_u32(bytes, at, next);
    put_u32(bytes, at + raw_attributes, attributes);
    put_u32(bytes, at + raw_name_length, static_cast<std::uint32_t>(name.size() * 2));
    put_u32(bytes, at + raw_reparse_tag, reparse_tag);
    bytes[at + raw_file_id] = file_id;
    for (std::size_t i = 0; i < name.size(); ++i) {
        bytes[at + raw_name + i * 2] = static_cast<std::uint8_t>(name[i]);
        bytes[at + raw_name + i * 2 + 1] = 0;
    }
}
std::vector<std::uint8_t> single_raw(std::uint32_t attributes = FILE_ATTRIBUTE_NORMAL,
                                     std::uint32_t reparse_tag = 0) {
    std::vector<std::uint8_t> bytes(104);
    put_raw_record(bytes, 0, 0, "lock.bin", attributes, 5, reparse_tag);
    return bytes;
}
std::vector<std::uint8_t> complete_raw() {
    // 88+16=104, 88+20=108 rounded to 112, 88+22=110.
    std::vector<std::uint8_t> bytes(326);
    put_raw_record(bytes, 0, 104, "lock.bin", FILE_ATTRIBUTE_NORMAL, 5);
    put_raw_record(bytes, 104, 112, "state.json", FILE_ATTRIBUTE_NORMAL, 6);
    put_raw_record(bytes, 216, 0, "witness.txt", FILE_ATTRIBUTE_NORMAL, 7);
    return bytes;
}
void require_raw_failure(const std::vector<std::uint8_t>& bytes, ErrorKind kind, const char* step) {
    const auto failure = expect_failure([&] {
        (void)parse_file_id_extd_directory_buffer(bytes.data(), bytes.size());
    });
    require(failure.kind == kind && failure.step == step, "raw production parser typed failure");
}
void test_raw_parser(const FixtureCase& fixture) {
    const auto single = single_raw();
    const auto one = parse_file_id_extd_directory_buffer(single.data(), single.size());
    require(!one.end && one.entries.size() == 1 && one.entries[0].name == "lock.bin", "literal single raw record and zero final offset");
    require(one.entries[0].file_id[0] == 5 && one.entries[0].attributes == FILE_ATTRIBUTE_NORMAL, "literal single raw identity and attributes");
    const auto three = complete_raw();
    const auto page = parse_file_id_extd_directory_buffer(three.data(), three.size());
    require(page.entries.size() == 3 && page.entries[0].name == "lock.bin" &&
            page.entries[1].name == "state.json" && page.entries[2].name == "witness.txt", "aligned multi-record traversal and final zero offset");
    require(page.entries[0].file_id[0] == 5 && page.entries[1].file_id[0] == 6 &&
            page.entries[2].file_id[0] == 7, "independent literal 128-bit ID fields");
    {
        auto fake = std::make_shared<FakeNativeCalls>(configuration(), fixture.latest_files);
        fake->raw_initial_buffer = std::make_unique<std::vector<std::uint8_t>>(three);
        fake->raw_final_buffer = std::make_unique<std::vector<std::uint8_t>>(three);
        WindowsSnapshotSource source(configuration(), fake);
        const auto result = compare(source, fixture);
        require(result.verdict == Verdict::accept_current && result.snapshot_complete,
                "both inventories use production raw decoder with literal three-child page");
    }
    {
        auto bytes = three;
        put_u32(bytes, 0, 105);
        require_raw_failure(bytes, ErrorKind::incomplete, "enumeration-buffer");
    }
    {
        auto bytes = three;
        put_u32(bytes, 0, 88);
        require_raw_failure(bytes, ErrorKind::incomplete, "enumeration-buffer");
    }
    {
        auto bytes = single;
        put_u32(bytes, 0, 400);
        require_raw_failure(bytes, ErrorKind::incomplete, "enumeration-buffer");
    }
    require_raw_failure(std::vector<std::uint8_t>(raw_header - 1), ErrorKind::incomplete, "enumeration-buffer");
    {
        auto bytes = std::vector<std::uint8_t>(104 + raw_header - 1);
        put_raw_record(bytes, 0, 104, "lock.bin", FILE_ATTRIBUTE_NORMAL, 5);
        require_raw_failure(bytes, ErrorKind::incomplete, "enumeration-buffer");
    }
    for (const auto length : {0u, 3u, 300u}) {
        auto bytes = single;
        put_u32(bytes, raw_name_length, length);
        require_raw_failure(bytes, ErrorKind::incomplete, "enumeration-buffer");
    }
    {
        auto bytes = single;
        put_u32(bytes, raw_name_length, 2);
        bytes[raw_name] = 0;
        bytes[raw_name + 1] = 0xD8; // unpaired UTF-16 high surrogate
        require_raw_failure(bytes, ErrorKind::malformed, "enumeration-name");
    }
    require_raw_failure({}, ErrorKind::incomplete, "enumeration-page");
    require_raw_failure(std::vector<std::uint8_t>(104), ErrorKind::incomplete, "enumeration-buffer");
    require_raw_failure(std::vector<std::uint8_t>(65537), ErrorKind::incomplete, "enumeration-buffer");
    require_raw_failure(single_raw(FILE_ATTRIBUTE_DEVICE), ErrorKind::identity_drift, "enumeration-type");
    for (const std::uint32_t attributes : {static_cast<std::uint32_t>(FILE_ATTRIBUTE_DIRECTORY),
                                           static_cast<std::uint32_t>(FILE_ATTRIBUTE_REPARSE_POINT)}) {
        const auto bytes = single_raw(attributes, attributes == FILE_ATTRIBUTE_REPARSE_POINT ? IO_REPARSE_TAG_SYMLINK : 0);
        const auto flagged = parse_file_id_extd_directory_buffer(bytes.data(), bytes.size());
        require(flagged.entries.size() == 1 && flagged.entries[0].attributes == attributes,
                "raw parser preserves unsupported type for inventory policy");
        auto fake = std::make_shared<FakeNativeCalls>(configuration(), fixture.latest_files);
        fake->raw_initial_buffer = std::make_unique<std::vector<std::uint8_t>>(bytes);
        WindowsSnapshotSource source(configuration(), fake);
        require_stop(compare(source, fixture), attributes == FILE_ATTRIBUTE_DIRECTORY ? ErrorKind::identity_drift : ErrorKind::reparse,
                     "initial-inventory");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(configuration(), fixture.latest_files);
        auto bytes = three;
        put_u32(bytes, 0, 105);
        fake->raw_initial_buffer = std::make_unique<std::vector<std::uint8_t>>(std::move(bytes));
        WindowsSnapshotSource source(configuration(), fake);
        require_stop(compare(source, fixture), ErrorKind::incomplete, "enumeration-buffer");
        require(source.audit().inventories.size() == 1 && !source.audit().inventories[0].explicit_end,
                "malformed raw page cannot complete inventory");
    }
}
void test_profiles() {
    // Construct the production backend to force native API linkage; do not call open().
    WindowsSnapshotSource production_source(configuration());
    require(production_source.audit().system_backend && production_source.audit().identities.empty(),
            "production backend linked without opening a filesystem object");
    const auto root = root_identity_spec();
    require(root.access == (FILE_READ_ATTRIBUTES | READ_CONTROL), "root access");
    require(root.share == (FILE_SHARE_READ | FILE_SHARE_WRITE), "root sharing");
    require(root.disposition == OPEN_EXISTING, "root disposition");
    require(root.flags == (FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT), "root flags");
    const auto ancestor = ancestor_identity_spec();
    const auto directory = snapshot_directory_spec();
    const auto child = snapshot_child_spec();
    require(ancestor.access == (FILE_READ_ATTRIBUTES | READ_CONTROL | SYNCHRONIZE), "ancestor access");
    require(ancestor.share == (FILE_SHARE_READ | FILE_SHARE_WRITE), "ancestor sharing");
    require(ancestor.options == (FILE_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT | FILE_OPEN_FOR_BACKUP_INTENT | FILE_SYNCHRONOUS_IO_NONALERT), "ancestor options");
    require(directory.access == (FILE_LIST_DIRECTORY | FILE_READ_ATTRIBUTES | READ_CONTROL | SYNCHRONIZE), "state directory access");
    require(directory.share == FILE_SHARE_READ, "state directory sharing");
    require(directory.options == ancestor.options, "state directory options");
    require(child.access == (FILE_READ_DATA | FILE_READ_ATTRIBUTES | READ_CONTROL | SYNCHRONIZE), "child access");
    require(child.share == FILE_SHARE_READ, "child sharing");
    require(child.options == (FILE_NON_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT | FILE_SYNCHRONOUS_IO_NONALERT), "child options");
    for (const auto& spec : {ancestor, directory, child}) {
        require(spec.disposition == FILE_OPEN, "relative FILE_OPEN");
        require(spec.object_attributes == (OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE), "relative object flags");
    }
    require(valid_component(L"state.json"), "valid component");
    require(!valid_component(L"..") && !valid_component(L"x\\y") && !valid_component(L"x/y"), "invalid components");
    require(enumeration_end_error(ERROR_FILE_NOT_FOUND, true), "first empty query completes empty directory");
    require(!enumeration_end_error(ERROR_FILE_NOT_FOUND, false), "later file-not-found is not enumeration end");
    require(enumeration_end_error(ERROR_NO_MORE_FILES, true) && enumeration_end_error(ERROR_NO_MORE_FILES, false),
            "explicit no-more-files completes scan");
    require(!enumeration_end_error(ERROR_MORE_DATA, true) && !enumeration_end_error(ERROR_ACCESS_DENIED, false),
            "truncation or access denial cannot complete scan");
}
void test_error_mapping() {
    const auto nt = nt_failure(ErrorKind::native_failure, "lock.bin", child_profile, "relative-open",
                               static_cast<std::int32_t>(0xC0000043u), 32, true);
    require(nt.kind == ErrorKind::sharing_conflict && nt.has_ntstatus && nt.has_win32_error, "raw NT and mapped Win32 sharing conflict");
    require(nt.ntstatus == static_cast<std::int32_t>(0xC0000043u) && nt.win32_error == 32, "raw native values retained");
    const auto unmapped = nt_failure(ErrorKind::native_failure, "state/", directory_profile, "relative-open",
                                      static_cast<std::int32_t>(0xC0000001u), 0, false);
    require(unmapped.kind == ErrorKind::native_failure && unmapped.has_ntstatus && !unmapped.has_win32_error, "unmapped NT status remains unmapped");
    const auto win = win32_failure(ErrorKind::incomplete, "state/", directory_profile, "enumeration-page", ERROR_MORE_DATA);
    require(win.kind == ErrorKind::incomplete && !win.has_ntstatus && win.has_win32_error && win.win32_error == ERROR_MORE_DATA, "Win32 failure has no invented NT status");
    const auto share = win32_failure(ErrorKind::native_failure, "state/", directory_profile, "open-root", ERROR_SHARING_VIOLATION);
    require(share.kind == ErrorKind::sharing_conflict, "Win32 sharing conflict classification");
}
void test_current_and_lifetime(const FixtureCase& fixture) {
    auto config = configuration();
    auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
    WindowsSnapshotSource source(config, fake);
    const auto result = compare(source, fixture);
    require(result.verdict == Verdict::accept_current && result.snapshot_complete, "synthetic latest accepted");
    const auto& audit = source.audit();
    require(!audit.system_backend, "injected identities are labelled synthetic");
    require(audit.inventories.size() == 2 && audit.inventories[0].phase == "initial" &&
            audit.inventories[1].phase == "final", "independent initial and final inventory records");
    require(audit.inventories[0].explicit_end && audit.inventories[1].explicit_end &&
            audit.inventories[0].entries.size() == fixture.latest_files.size() &&
            audit.inventories[1].entries.size() == fixture.latest_files.size(), "both inventories reached explicit end");
    require(!audit.identities.empty() && audit.identities.front().observed.volume_guid_path == volume &&
            audit.identities.front().observed.volume_serial == 42 && audit.identities.front().parent_id.empty(),
            "root volume and file identity recorded");
    require(audit.identities[1].parent_id == identity_key(config.root_identity) &&
            audit.identities[1].observed.final_path == config.ancestors[0].identity.final_path,
            "ancestor parent binding and final path recorded");
    require(std::any_of(audit.identities.begin(), audit.identities.end(), [&](const IdentityObservation& record) {
        return record.object == "lock.bin" && record.parent_id == source.expected_directory_id() &&
               record.observed.reparse_tag == 0 && record.observed.file_id[0] != 0;
    }), "held child identity, parent and reparse state recorded");
    require(fake->opened.size() == 3 + fixture.latest_files.size(), "one relative open per ancestor state and child");
    require(fake->opened[0].spec.share == (FILE_SHARE_READ | FILE_SHARE_WRITE), "general ancestor profile retained");
    require(fake->opened[2].spec.share == FILE_SHARE_READ, "state snapshot profile retained");
    for (std::size_t i = 3; i < fake->opened.size(); ++i)
        require(fake->opened[i].spec.share == FILE_SHARE_READ && fake->opened[i].parent == handle_of(4), "children opened relative to held state directory");
    require(fake->live_count() == 0 && fake->closed.size() == 4 + fixture.latest_files.size(), "all held handles released after verdict");
    for (std::size_t i = 1; i < fake->closed.size(); ++i)
        require(reinterpret_cast<std::uintptr_t>(fake->closed[i - 1]) > reinterpret_cast<std::uintptr_t>(fake->closed[i]), "reverse-order close");
}
void test_old_and_deleted(const FixtureCase& fixture) {
    auto config = configuration();
    auto old = std::make_shared<FakeNativeCalls>(config, fixture.old_files);
    WindowsSnapshotSource old_source(config, old);
    const auto restored = compare(old_source, fixture);
    require(restored.verdict == Verdict::reject_restored_old && restored.snapshot_complete, "complete old set rejected");
    auto empty = std::make_shared<FakeNativeCalls>(config, std::map<std::string, std::string>{});
    WindowsSnapshotSource empty_source(config, empty);
    const auto deleted = compare(empty_source, fixture);
    require(deleted.verdict == Verdict::reject_deleted && deleted.snapshot_complete, "complete empty set rejected");
    require(empty->opened.size() == 3 && empty->closed.size() == 4, "empty state holds only ancestor and directory handles");
}
void test_fail_closed(const FixtureCase& fixture) {
    const auto config = configuration();
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        fake->fail_open_component = L"lock.bin";
        WindowsSnapshotSource source(config, fake);
        const auto result = compare(source, fixture);
        require_stop(result, ErrorKind::sharing_conflict, "relative-open");
        require(result.has_ntstatus && result.has_win32_error && result.ntstatus == static_cast<std::int32_t>(0xC0000043u), "child sharing raw status");
        require(fake->opened.size() == 4, "no relaxed retry after sharing conflict");
        require(fake->live_count() == 0 && fake->closed.size() == 4, "exceptional child open closes already held chain");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        fake->enumeration_error = true;
        WindowsSnapshotSource source(config, fake);
        require_stop(compare(source, fixture), ErrorKind::incomplete, "enumeration-page");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        fake->initial_entries_override = std::make_unique<std::vector<NativeEntry>>(fake->generated_entries());
        fake->initial_entries_override->push_back({"extra.bin", {}, FILE_ATTRIBUTE_NORMAL, 0});
        WindowsSnapshotSource source(config, fake);
        require_stop(compare(source, fixture), ErrorKind::unexpected_entry, "initial-inventory");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        fake->initial_entries_override = std::make_unique<std::vector<NativeEntry>>(fake->generated_entries());
        fake->initial_entries_override->at(0).attributes = FILE_ATTRIBUTE_REPARSE_POINT;
        fake->initial_entries_override->at(0).reparse_tag = IO_REPARSE_TAG_SYMLINK;
        WindowsSnapshotSource source(config, fake);
        require_stop(compare(source, fixture), ErrorKind::reparse, "initial-inventory");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        fake->initial_entries_override = std::make_unique<std::vector<NativeEntry>>(fake->generated_entries());
        fake->initial_entries_override->at(0).attributes = FILE_ATTRIBUTE_DIRECTORY;
        WindowsSnapshotSource source(config, fake);
        require_stop(compare(source, fixture), ErrorKind::identity_drift, "initial-inventory");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        fake->initial_entries_override = std::make_unique<std::vector<NativeEntry>>(fake->generated_entries());
        fake->initial_entries_override->at(0).attributes = FILE_ATTRIBUTE_DEVICE;
        WindowsSnapshotSource source(config, fake);
        require_stop(compare(source, fixture), ErrorKind::identity_drift, "enumeration-type");
        require(fake->opened.size() == 3 && fake->live_count() == 0, "device-marked directory record never opens as regular child");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        fake->device_child_metadata = true;
        WindowsSnapshotSource source(config, fake);
        require_stop(compare(source, fixture), ErrorKind::identity_drift, "hold-child-identity");
        require(fake->live_count() == 0 && fake->closed.size() == 5, "device-marked held child closes all opened handles");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        auto duplicate = fake->generated_entries();
        duplicate.push_back(duplicate.front());
        fake->initial_entries_override = std::make_unique<std::vector<NativeEntry>>(std::move(duplicate));
        WindowsSnapshotSource source(config, fake);
        require_stop(compare(source, fixture), ErrorKind::malformed, "enumeration-entry");
        require(!source.audit().inventories.at(0).explicit_end, "same-page duplicate cannot complete inventory");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        const auto first = fake->generated_entries().front();
        fake->initial_pages_override = {{first}, {first}};
        WindowsSnapshotSource source(config, fake);
        require_stop(compare(source, fixture), ErrorKind::malformed, "enumeration-entry");
        require(!source.audit().inventories.at(0).explicit_end, "cross-page duplicate cannot complete inventory");
    }
    {
        std::vector<std::uint8_t> raw(208);
        put_raw_record(raw, 0, 104, "lock.bin", FILE_ATTRIBUTE_NORMAL, 5);
        put_raw_record(raw, 104, 0, "lock.bin", FILE_ATTRIBUTE_NORMAL, 5);
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        fake->raw_initial_buffer = std::make_unique<std::vector<std::uint8_t>>(std::move(raw));
        WindowsSnapshotSource source(config, fake);
        require_stop(compare(source, fixture), ErrorKind::malformed, "enumeration-entry");
        require(!source.audit().inventories.at(0).explicit_end, "production raw parser duplicates cannot accept current state");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        fake->initial_entries_override = std::make_unique<std::vector<NativeEntry>>(fake->generated_entries());
        fake->initial_entries_override->pop_back();
        WindowsSnapshotSource source(config, fake);
        require_stop(compare(source, fixture), ErrorKind::identity_drift, "final-inventory");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        fake->truncated = true;
        WindowsSnapshotSource source(config, fake);
        require_stop(compare(source, fixture), ErrorKind::incomplete, "enumeration-limit");
        require(source.audit().inventories.size() == 1 && !source.audit().inventories[0].explicit_end,
                "incomplete enumeration audit never marks complete");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        fake->fail_inspect_step = "held-identity";
        WindowsSnapshotSource source(config, fake);
        require_stop(compare(source, fixture), ErrorKind::incomplete, "held-identity");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        fake->fail_read = true;
        WindowsSnapshotSource source(config, fake);
        require_stop(compare(source, fixture), ErrorKind::incomplete, "read-child");
        require(fake->live_count() == 0 && fake->closed.size() == 4 + fixture.latest_files.size(),
                "exceptional child read closes complete held handle set");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        fake->drift_on_final = true;
        WindowsSnapshotSource source(config, fake);
        require_stop(compare(source, fixture), ErrorKind::identity_drift, "held-child-identity");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        fake->wrong_child_descriptor = true;
        WindowsSnapshotSource source(config, fake);
        require_stop(compare(source, fixture), ErrorKind::identity_drift, "hold-child-identity");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        fake->final_entries_override = std::make_unique<std::vector<NativeEntry>>(fake->generated_entries());
        fake->final_entries_override->pop_back();
        WindowsSnapshotSource source(config, fake);
        require_stop(compare(source, fixture), ErrorKind::identity_drift, "final-inventory");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        fake->final_entries_override = std::make_unique<std::vector<NativeEntry>>(fake->generated_entries());
        fake->final_entries_override->at(0).file_id[0] = 99;
        WindowsSnapshotSource source(config, fake);
        require_stop(compare(source, fixture), ErrorKind::identity_drift, "final-child-identity");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        WindowsSnapshotSource source(config, fake);
        const auto failure = expect_failure([&] { (void)source.open(general_identity_profile); });
        require(failure.kind == ErrorKind::binding_failure && fake->opened.empty(), "unsupported profile cannot open");
    }
    {
        auto fake = std::make_shared<FakeNativeCalls>(config, fixture.latest_files);
        auto bad = config;
        bad.ancestors[1].identity.final_path += L"_wrong";
        WindowsSnapshotSource source(bad, fake);
        require_stop(compare(source, fixture), ErrorKind::identity_drift, "ancestor-identity");
        require(fake->live_count() == 0 && fake->closed.size() == 3, "exceptional ancestor initialization closes held chain");
    }
}
} // namespace
int main() {
    try {
        test_profiles();
        test_error_mapping();
        const auto& cases = fixture_cases();
        require(cases.size() == 2, "both frozen paired cases");
        for (const auto& fixture : cases) {
            test_raw_parser(fixture);
            test_current_and_lifetime(fixture);
            test_old_and_deleted(fixture);
            test_fail_closed(fixture);
        }
        std::cout << "PASS " << checks << " Windows adapter synthetic checks; no native fixture open attempted\n";
        return 0;
    } catch (const std::exception& failure) {
        std::cerr << "FAIL after " << checks << " checks: " << failure.what() << '\n';
        return 1;
    }
}
