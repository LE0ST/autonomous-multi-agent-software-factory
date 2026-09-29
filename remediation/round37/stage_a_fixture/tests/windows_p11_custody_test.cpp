#include "../src/windows_p11_custody.hpp"
#include <winternl.h>
#include <algorithm>
#include <cstdint>
#include <iostream>
#include <map>
#include <stdexcept>
#include <vector>

using namespace stage_a;
using namespace stage_a::windows;
namespace {
int checks = 0;
void check(bool value, const char* why) { ++checks; if (!value) throw std::runtime_error(why); }
constexpr wchar_t volume[] = L"\\\\?\\Volume{11111111-2222-3333-4444-555555555555}\\";
constexpr char p10_hash[] = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
constexpr char active_bytes[] = "{\"schema_version\":1,\"marker\":\"S1PF-260926-A-STAGE-A-V1\",\"p10_sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"case_id\":\"spent-budget-active\",\"latest_digest\":\"4d5d63027a1578256a003328664c48f1328cc5171ef29db4a9c0046b8ce4d22d\",\"generation\":1,\"worker_runs\":1,\"terminal\":false}";
constexpr char terminal_bytes[] = "{\"schema_version\":1,\"marker\":\"S1PF-260926-A-STAGE-A-V1\",\"p10_sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"case_id\":\"spent-budget-terminal\",\"latest_digest\":\"eb2c260344d3c33075cb817a6ff8ce7c216b3a57dace342bb58fbe086ee33764\",\"generation\":2,\"worker_runs\":1,\"terminal\":true}";
constexpr char active_hash[] = "69a19feb75da965fc1d5220d52c9b59af3172d5a58646b8b3a1a7570cd86c820";
constexpr char terminal_hash[] = "d91e5ee63308e89390d04e48d731eea5b133551921eea978dcc5098f280d02ac";

Metadata node(std::wstring path, unsigned id, bool directory, bool protected_acl = true) {
    Metadata m;
    m.volume_guid_path = volume; m.final_path = std::move(path);
    m.volume_serial = 0x12345678; m.file_id[0] = static_cast<std::uint8_t>(id);
    m.attributes = directory ? FILE_ATTRIBUTE_DIRECTORY : FILE_ATTRIBUTE_ARCHIVE;
    m.directory = directory; m.dacl_protected = protected_acl;
    m.sddl = protected_acl ? L"O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;S-1-5-21-1-2-3-1003)"
                           : L"O:BAG:BAD:(A;;FA;;;SY)";
    return m;
}
P11CustodyConfig config(unsigned index) {
    const std::wstring p1 = std::wstring(volume) + L"S1PF_260926_A";
    const std::wstring p4 = p1 + L"\\store";
    P11CustodyConfig c{node(volume, 1, true, false), node(p1, 2, true),
        node(p4, 3, true), node(p4 + L"\\authority.db", 4, false),
        fixture_cases().at(index), p10_hash, index == 0 ? active_hash : terminal_hash};
    return c;
}
HANDLE handle(int n) { return reinterpret_cast<HANDLE>(static_cast<std::intptr_t>(n)); }
int number(HANDLE h) { return static_cast<int>(reinterpret_cast<std::intptr_t>(h)); }

struct FakeCalls final : P11CustodyCalls {
    P11CustodyConfig expected;
    std::map<int, Metadata> metadata;
    std::string bytes;
    std::vector<std::string> trace;
    std::vector<int> held, closed;
    int open_fail = 0, inspect_fail = 0, read_fail = 0, reads = 0;
    bool changed_content = false, changed_identity = false, throw_std = false, throw_other = false;
    int inspections[5]{};
    explicit FakeCalls(unsigned index) : expected(config(index)),
        metadata{{1,expected.root},{2,expected.p1},{3,expected.p4},{4,expected.p11}},
        bytes(index == 0 ? active_bytes : terminal_bytes) {}
    HANDLE open_root(const std::wstring& path, RootOpenSpec spec) override {
        check(path == L"C:\\", "fixed volume root");
        check(spec.access == (FILE_READ_ATTRIBUTES | READ_CONTROL) &&
              spec.share == (FILE_SHARE_READ | FILE_SHARE_WRITE) && spec.disposition == OPEN_EXISTING &&
              spec.flags == (FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT), "root profile");
        trace.push_back("open-root");
        if (open_fail == 1) throw win32_failure(ErrorKind::native_failure, "volume-root", p11_custody_profile, "open-root", ERROR_ACCESS_DENIED);
        held.push_back(1); return handle(1);
    }
    HANDLE open_relative(HANDLE parent, const std::wstring& component, OpenSpec spec,
                         const std::string& object) override {
        const int id = object == "P1" ? 2 : object == "P4" ? 3 : 4;
        check(number(parent) == id - 1 && held.size() == static_cast<std::size_t>(id-1), "held relative parent");
        check(component == (id == 2 ? L"S1PF_260926_A" : id == 3 ? L"store" : L"authority.db"), "fixed relative component");
        const std::uint32_t access = id == 4
            ? (FILE_READ_DATA | FILE_READ_ATTRIBUTES | READ_CONTROL | SYNCHRONIZE)
            : (FILE_READ_ATTRIBUTES | READ_CONTROL | SYNCHRONIZE);
        const std::uint32_t options = id == 4
            ? (FILE_NON_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT | FILE_SYNCHRONOUS_IO_NONALERT)
            : (FILE_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT | FILE_OPEN_FOR_BACKUP_INTENT | FILE_SYNCHRONOUS_IO_NONALERT);
        check(spec.access == access && spec.share == (FILE_SHARE_READ | FILE_SHARE_WRITE) &&
              spec.disposition == FILE_OPEN && spec.options == options &&
              spec.object_attributes == (OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE),
              "independent exact relative open profile");
        check(spec.share == (FILE_SHARE_READ | FILE_SHARE_WRITE) &&
              spec.object_attributes == (OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE), "general protected share and no-reparse");
        trace.push_back("open-" + object);
        if (open_fail == id) throw win32_failure(ErrorKind::sharing_conflict, object, p11_custody_profile, "relative-open", ERROR_SHARING_VIOLATION);
        held.push_back(id); return handle(id);
    }
    Metadata inspect(HANDLE h, const std::string& object, const std::string& step) override {
        const int id = number(h);
        check(std::find(held.begin(), held.end(), id) != held.end() && closed.empty(), "identity from held handle");
        trace.push_back("inspect-" + object + "-" + step);
        if (inspect_fail == id) throw win32_failure(ErrorKind::native_failure, object, p11_custody_profile, step + "/FileIdInfo", ERROR_ACCESS_DENIED);
        ++inspections[id];
        Metadata value = metadata.at(id);
        if (changed_identity && id == 4 && inspections[id] == 2) value.file_id[0] ^= 1;
        return value;
    }
    std::string read_content(HANDLE h, std::size_t maximum) override {
        check(number(h) == 4 && held == std::vector<int>({1,2,3,4}) && closed.empty(), "all ancestor and P11 handles held");
        check(maximum == (expected.selected_case.id == "spent-budget-active" ?
                          sizeof(active_bytes)-1 : sizeof(terminal_bytes)-1), "sealed byte bound");
        trace.push_back("read-P11"); ++reads;
        if (throw_std) throw std::runtime_error("synthetic std failure");
        if (throw_other) throw 19;
        if (read_fail) throw win32_failure(read_fail == 1 ? ErrorKind::incomplete : ErrorKind::oversized,
                                          "P11", p11_custody_profile,
                                          read_fail == 1 ? "read-content" : "read-size", ERROR_ACCESS_DENIED);
        if (changed_content && reads == 2) return bytes + "x";
        return bytes;
    }
    void close(HANDLE h) noexcept override { closed.push_back(number(h)); trace.push_back("close"); }
};

void failure(P11CustodyConfig c, const std::shared_ptr<FakeCalls>& fake,
             ErrorKind kind, const char* object, const char* step,
             std::vector<int> closes) {
    try { (void)WindowsP11CustodyReader(std::move(c), fake).read_verified_p11(); check(false, "failure expected"); }
    catch (const ObservationFailure& e) {
        check(e.kind == kind && e.object == object && e.profile == p11_custody_profile && e.step == step,
              "typed P11 custody failure provenance");
        if (std::string(step) == "open-root" || std::string(step) == "relative-open")
            check(e.has_win32_error && e.win32_error ==
                  static_cast<std::uint32_t>(std::string(step) == "open-root" ?
                      ERROR_ACCESS_DENIED : ERROR_SHARING_VIOLATION),
                  "raw Win32 failure retained");
    }
    check(fake->closed == closes, "reverse cleanup after failure");
    if (closes.empty()) check(fake->trace.empty() || fake->trace == std::vector<std::string>{"open-root"},
                              "trusted config failure never opens a protected component");
}
} // namespace

int main() {
    try {
        check(sizeof(void*) == 8, "x64 synthetic test");
        check(sha256(active_bytes) == active_hash && sha256(terminal_bytes) == terminal_hash,
              "independently literal P11 bytes and hashes");
        check(std::string(active_bytes).size() == 299 && std::string(terminal_bytes).size() == 300,
              "independent literal P11 lengths");
        for (unsigned index : {0u,1u}) {
            auto f = std::make_shared<FakeCalls>(index);
            const auto result = WindowsP11CustodyReader(config(index), f).read_verified_p11();
            check(result == (index == 0 ? active_bytes : terminal_bytes), "exact selected P11 bytes");
            check(f->reads == 2 && f->closed == std::vector<int>({4,3,2,1}), "two reads and reverse close");
            for (int id = 1; id <= 4; ++id) check(f->inspections[id] == 2, "two held identity observations");
        }
        for (int id = 1; id <= 4; ++id) {
            auto f = std::make_shared<FakeCalls>(0); f->open_fail = id;
            failure(config(0), f, id == 1 ? ErrorKind::native_failure : ErrorKind::sharing_conflict,
                    id == 1 ? "volume-root" : id == 2 ? "P1" : id == 3 ? "P4" : "P11",
                    id == 1 ? "open-root" : "relative-open",
                    id == 1 ? std::vector<int>{} : id == 2 ? std::vector<int>{1} :
                    id == 3 ? std::vector<int>{2,1} : std::vector<int>{3,2,1});
        }
        { auto f=std::make_shared<FakeCalls>(0); f->inspect_fail=4;
          failure(config(0),f,ErrorKind::native_failure,"P11","initial-identity/FileIdInfo",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(0); f->metadata[3].sddl=L"O:SYG:SYD:P(A;;FA;;;SY)";
          failure(config(0),f,ErrorKind::identity_drift,"P4","initial-identity",{3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(0); f->metadata[4].file_id[0]^=1;
          failure(config(0),f,ErrorKind::identity_drift,"P11","initial-identity",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(0); f->metadata[4].attributes|=FILE_ATTRIBUTE_REPARSE_POINT;
          failure(config(0),f,ErrorKind::reparse,"P11","initial-identity",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(0); f->metadata[4].attributes|=FILE_ATTRIBUTE_DEVICE;
          failure(config(0),f,ErrorKind::identity_drift,"P11","initial-identity",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(0); f->metadata[4].directory=true; f->metadata[4].attributes=FILE_ATTRIBUTE_DIRECTORY;
          failure(config(0),f,ErrorKind::identity_drift,"P11","initial-identity",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(0); f->metadata[4].final_path+=L".wrong";
          failure(config(0),f,ErrorKind::identity_drift,"P11","initial-identity",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(0); f->metadata[4].dacl_protected=false;
          failure(config(0),f,ErrorKind::incomplete,"P11","initial-identity",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(0); f->bytes[0]='X';
          failure(config(0),f,ErrorKind::binding_failure,"P11","canonical-bytes",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(0); f->bytes=terminal_bytes;
          failure(config(0),f,ErrorKind::binding_failure,"P11","canonical-bytes",{4,3,2,1}); }
        for (int mode : {1,2}) { auto f=std::make_shared<FakeCalls>(0); f->read_fail=mode;
          failure(config(0),f,mode==1?ErrorKind::incomplete:ErrorKind::oversized,"P11",
                  mode==1?"read-content":"read-size",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(0); f->changed_content=true;
          failure(config(0),f,ErrorKind::identity_drift,"P11","final-content",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(0); f->changed_identity=true;
          failure(config(0),f,ErrorKind::identity_drift,"P11","final-identity",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(0); f->throw_std=true;
          failure(config(0),f,ErrorKind::incomplete,"P11","reader-exception",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(0); f->throw_other=true;
          failure(config(0),f,ErrorKind::incomplete,"P11","reader-exception",{4,3,2,1}); }
        { auto c=config(0); c.selected_case.id="writer-selected"; auto f=std::make_shared<FakeCalls>(0);
          failure(c,f,ErrorKind::binding_failure,"P11","trusted-case",{}); }
        { auto c=config(0); c.selected_case.latest_files["state.json"]="writer"; auto f=std::make_shared<FakeCalls>(0);
          failure(c,f,ErrorKind::binding_failure,"P11","trusted-case",{}); }
        { auto c=config(0); c.p11_sha256[0]='0'; auto f=std::make_shared<FakeCalls>(0);
          failure(c,f,ErrorKind::binding_failure,"P11","trusted-config-hash",{}); }
        { auto c=config(0); c.rendered_p10_sha256="bad"; auto f=std::make_shared<FakeCalls>(0);
          failure(c,f,ErrorKind::binding_failure,"P11","trusted-case",{}); }
        { auto c=config(0); c.p11.final_path+=L".wrong"; auto f=std::make_shared<FakeCalls>(0);
          failure(c,f,ErrorKind::binding_failure,"P11","trusted-config",{}); }
        check(std::make_unique<WindowsP11CustodyReader>(config(0)) != nullptr,
              "production constructor links without protected open");
        std::cout << "windows P11 custody synthetic checks: " << checks << " passed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "windows P11 custody synthetic failure after " << checks << " checks: " << e.what() << '\n';
        return 1;
    }
}
