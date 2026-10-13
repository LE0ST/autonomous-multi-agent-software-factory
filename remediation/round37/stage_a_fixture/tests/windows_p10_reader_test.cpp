#include "../src/windows_p10_reader.hpp"
#include <winternl.h>

#include <algorithm>
#include <cstdint>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

using namespace stage_a;
using namespace stage_a::windows;
namespace {
int checks = 0;
void check(bool yes, const char* why) { ++checks; if (!yes) throw std::runtime_error(why); }
constexpr wchar_t guid_root[] = L"\\\\?\\Volume{11111111-2222-3333-4444-555555555555}\\";
constexpr char literal_p10[] = "{\"schema_version\":1,\"run_id\":\"260926_A\"}";

Metadata node(std::wstring path, unsigned id, bool directory, bool protect = true) {
    Metadata m;
    m.volume_guid_path = guid_root;
    m.final_path = std::move(path);
    m.volume_serial = 0x11223344;
    m.file_id[0] = static_cast<std::uint8_t>(id);
    m.attributes = directory ? FILE_ATTRIBUTE_DIRECTORY : FILE_ATTRIBUTE_ARCHIVE;
    m.directory = directory;
    m.dacl_protected = protect;
    m.sddl = protect ? L"O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;0x1200a9;;;S-1-5-21-1-2-3-1002)"
                     : L"O:BAG:BAD:(A;;FA;;;SY)";
    return m;
}
P10ReaderConfig config() {
    const std::wstring root = guid_root;
    const std::wstring p1 = root + L"S1PF_260926_A";
    const std::wstring p3 = p1 + L"\\config";
    const std::wstring p10 = p3 + L"\\binding.json";
    P10ReaderConfig c{node(root, 1, true, false), node(p1, 2, true),
                      node(p3, 3, true), node(p10, 4, false), literal_p10, {}};
    c.sha256 = sha256(c.canonical_bytes);
    return c;
}
HANDLE handle(int value) { return reinterpret_cast<HANDLE>(static_cast<std::intptr_t>(value)); }
int number(HANDLE value) { return static_cast<int>(reinterpret_cast<std::intptr_t>(value)); }

struct FakeCalls final : P10Calls {
    P10ReaderConfig expected = config();
    std::map<int, Metadata> metadata{{1, expected.root}, {2, expected.p1}, {3, expected.p3}, {4, expected.p10}};
    std::vector<std::string> trace;
    std::vector<int> open_handles, closed;
    std::string bytes = literal_p10;
    int open_fail = 0, inspect_fail = 0, read_fail = 0;
    bool mutate_final_p10 = false, mutate_final_content = false, throw_nonstandard = false;
    int inspect_count[5]{};
    int read_count = 0;
    HANDLE open_root(const std::wstring& path, RootOpenSpec spec) override {
        check(path == L"C:\\", "fixed C root");
        check(spec.access == (FILE_READ_ATTRIBUTES | READ_CONTROL), "root access");
        check(spec.share == (FILE_SHARE_READ | FILE_SHARE_WRITE), "root share");
        check(spec.disposition == OPEN_EXISTING, "root disposition");
        check(spec.flags == (FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT), "root flags");
        trace.push_back("open-root");
        if (open_fail == 1) throw ObservationFailure(ErrorKind::native_failure, "volume-root", p10_read_profile, "open-root", "synthetic denied", 0, false, ERROR_ACCESS_DENIED, true);
        open_handles.push_back(1); return handle(1);
    }
    HANDLE open_relative(HANDLE parent, const std::wstring& component, OpenSpec spec,
                         const std::string& object) override {
        const int id = object == "P1" ? 2 : object == "P3" ? 3 : 4;
        check(number(parent) == id - 1, "held parent handle");
        check(component == (id == 2 ? L"S1PF_260926_A" : id == 3 ? L"config" : L"binding.json"), "fixed component");
        check(spec.share == (FILE_SHARE_READ | FILE_SHARE_WRITE), "general share without delete");
        check(spec.disposition == FILE_OPEN, "relative FILE_OPEN");
        check(spec.object_attributes == (OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE), "relative object flags");
        const std::uint32_t expected_access = id == 4 ? (FILE_READ_DATA | FILE_READ_ATTRIBUTES | READ_CONTROL | SYNCHRONIZE)
                                                      : (FILE_READ_ATTRIBUTES | READ_CONTROL | SYNCHRONIZE);
        check(spec.access == expected_access, "relative access");
        const std::uint32_t expected_options = id == 4 ? (FILE_NON_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT | FILE_SYNCHRONOUS_IO_NONALERT)
                                                       : (FILE_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT | FILE_OPEN_FOR_BACKUP_INTENT | FILE_SYNCHRONOUS_IO_NONALERT);
        check(spec.options == expected_options, "relative options");
        trace.push_back("open-" + object);
        if (open_fail == id) throw ObservationFailure(ErrorKind::sharing_conflict, object, p10_read_profile, "relative-open", "synthetic sharing", static_cast<std::int32_t>(0xc0000043u), true, ERROR_SHARING_VIOLATION, true);
        open_handles.push_back(id); return handle(id);
    }
    Metadata inspect(HANDLE h, const std::string& object, const std::string& step) override {
        const int id = number(h);
        check(std::find(open_handles.begin(), open_handles.end(), id) != open_handles.end(), "inspect held handle");
        check(closed.empty(), "no close before final verification");
        trace.push_back("inspect-" + object + "-" + step);
        if (inspect_fail == id) throw ObservationFailure(ErrorKind::native_failure, object, p10_read_profile, step + "/FileIdInfo", "synthetic query error", 0, false, ERROR_ACCESS_DENIED, true);
        ++inspect_count[id];
        Metadata m = metadata.at(id);
        if (mutate_final_p10 && id == 4 && inspect_count[id] == 2) m.file_id[0] ^= 1;
        return m;
    }
    std::string read_content(HANDLE h, std::size_t max_bytes) override {
        check(number(h) == 4 && open_handles.size() == 4 && closed.empty(), "all four handles held during read");
        check(max_bytes == sizeof(literal_p10) - 1, "approved exact byte bound");
        trace.push_back("read-P10"); ++read_count;
        if (throw_nonstandard) throw 17;
        if (read_fail) throw ObservationFailure(read_fail == 1 ? ErrorKind::incomplete : ErrorKind::oversized,
            "P10", p10_read_profile, read_fail == 1 ? "read-content" : "read-size", "synthetic read fault");
        if (mutate_final_content && read_count == 2) return bytes + "x";
        return bytes;
    }
    void close(HANDLE h) noexcept override { closed.push_back(number(h)); trace.push_back("close"); }
};

void expect_failure(P10ReaderConfig c, std::shared_ptr<FakeCalls> fake, ErrorKind kind,
                    const std::string& object, const std::string& step, std::vector<int> closes) {
    try { (void)WindowsP10Reader(std::move(c), fake).read_verified_p10(); check(false, "failure expected"); }
    catch (const ObservationFailure& e) {
        check(e.kind == kind, "typed kind"); check(e.object == object, "typed object");
        check(e.step == step, "typed step");
    }
    check(fake->closed == closes, "reverse held-handle cleanup");
}
} // namespace

int main() {
    try {
        // Construct the production backend to retain/link native imports; no open is invoked.
        check(make_system_p10_calls() != nullptr, "production backend links without opening P10");
        {
            auto f = std::make_shared<FakeCalls>();
            check(WindowsP10Reader(config(), f).read_verified_p10() == literal_p10, "synthetic exact P10 accepted");
            check(f->read_count == 2, "two held content observations");
            for (int id = 1; id <= 4; ++id) check(f->inspect_count[id] == 2, "two held identity observations");
            check(f->closed == std::vector<int>({4,3,2,1}), "success reverse close");
        }
        for (int id = 1; id <= 4; ++id) {
            auto f = std::make_shared<FakeCalls>(); f->open_fail = id;
            expect_failure(config(), f, id == 1 ? ErrorKind::native_failure : ErrorKind::sharing_conflict,
                           id == 1 ? "volume-root" : id == 2 ? "P1" : id == 3 ? "P3" : "P10",
                           id == 1 ? "open-root" : "relative-open",
                           id == 1 ? std::vector<int>{} : id == 2 ? std::vector<int>{1} : id == 3 ? std::vector<int>{2,1} : std::vector<int>{3,2,1});
        }
        { auto f=std::make_shared<FakeCalls>(); f->inspect_fail=4;
          expect_failure(config(),f,ErrorKind::native_failure,"P10","initial-identity/FileIdInfo",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(); f->metadata[2].file_id[0]^=1;
          expect_failure(config(),f,ErrorKind::identity_drift,"P1","initial-identity",{2,1}); }
        { auto f=std::make_shared<FakeCalls>(); f->metadata[3].sddl=L"O:SYG:SYD:P(A;;FA;;;SY)";
          expect_failure(config(),f,ErrorKind::identity_drift,"P3","initial-identity",{3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(); f->metadata[4].sddl=L"O:SYG:SYD:P(A;;FA;;;SY)";
          expect_failure(config(),f,ErrorKind::identity_drift,"P10","initial-identity",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(); f->metadata[4].volume_serial^=1;
          expect_failure(config(),f,ErrorKind::identity_drift,"P10","initial-identity",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(); f->metadata[4].file_id.fill(0);
          expect_failure(config(),f,ErrorKind::incomplete,"P10","initial-identity",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(); f->metadata[4].attributes|=FILE_ATTRIBUTE_REPARSE_POINT;
          expect_failure(config(),f,ErrorKind::reparse,"P10","initial-identity",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(); f->metadata[4].attributes|=FILE_ATTRIBUTE_DEVICE;
          expect_failure(config(),f,ErrorKind::identity_drift,"P10","initial-identity",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(); f->metadata[4].directory=true; f->metadata[4].attributes=FILE_ATTRIBUTE_DIRECTORY;
          expect_failure(config(),f,ErrorKind::identity_drift,"P10","initial-identity",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(); f->metadata[4].final_path+=L".wrong";
          expect_failure(config(),f,ErrorKind::identity_drift,"P10","initial-identity",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(); f->metadata[4].dacl_protected=false;
          expect_failure(config(),f,ErrorKind::incomplete,"P10","initial-identity",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(); f->bytes[0]='X';
          expect_failure(config(),f,ErrorKind::binding_failure,"P10","canonical-bytes",{4,3,2,1}); }
        for (int mode : {1,2}) { auto f=std::make_shared<FakeCalls>(); f->read_fail=mode;
          expect_failure(config(),f,mode==1?ErrorKind::incomplete:ErrorKind::oversized,"P10",
                         mode==1?"read-content":"read-size",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(); f->mutate_final_p10=true;
          expect_failure(config(),f,ErrorKind::identity_drift,"P10","final-identity",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(); f->mutate_final_content=true;
          expect_failure(config(),f,ErrorKind::identity_drift,"P10","final-content",{4,3,2,1}); }
        { auto f=std::make_shared<FakeCalls>(); f->throw_nonstandard=true;
          expect_failure(config(),f,ErrorKind::incomplete,"P10","reader-exception",{4,3,2,1}); }
        { auto c=config(); c.p10.final_path+=L".wrong"; auto f=std::make_shared<FakeCalls>();
          expect_failure(c,f,ErrorKind::binding_failure,"P10","trusted-config",{}); }
        { auto c=config(); c.sha256[0]='0'; auto f=std::make_shared<FakeCalls>();
          expect_failure(c,f,ErrorKind::binding_failure,"P10","trusted-config-hash",{}); }
        std::cout << "windows_p10_reader synthetic checks: " << checks << " passed\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "windows_p10_reader synthetic failure after " << checks << " checks: " << e.what() << '\n';
        return 1;
    }
}
