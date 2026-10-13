#include "../src/controller_authority_composition.hpp"
#include "../src/windows_p10_reader.hpp"

#include <algorithm>
#include <cstdint>
#include <iostream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

using namespace stage_a;
using namespace stage_a::windows;
static_assert(std::is_same_v<decltype(bind_controller_precomparison(
    std::declval<ControllerSidPort&>(), std::declval<AuthenticatedHeadPort&>(),
    std::declval<P10ReaderConfig>(), std::declval<const ApprovedAuthorityBinding&>(),
    std::declval<const FixtureCase&>())), AuthorityBindingResult>);
namespace {
int checks = 0;
void check(bool value, const char* message) { ++checks; if (!value) throw std::runtime_error(message); }
constexpr wchar_t root_path[] = L"\\\\?\\Volume{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}\\";
const SidSet sids{"S-1-5-21-100-200-300-1001", "S-1-5-21-100-200-300-1002", "S-1-5-21-100-200-300-1003"};
const P10BuildHashes images{std::string(64,'1'), std::string(64,'2'), std::string(64,'3'), std::string(64,'4')};
using Events = std::vector<std::string>;
HANDLE handle(int n) { return reinterpret_cast<HANDLE>(static_cast<std::intptr_t>(n)); }
int number(HANDLE h) { return static_cast<int>(reinterpret_cast<std::intptr_t>(h)); }

Metadata meta(std::wstring path, int id, bool directory, bool protected_dacl = true) {
    Metadata m;
    m.volume_guid_path = root_path;
    m.final_path = std::move(path);
    m.sddl = protected_dacl ? L"O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;0x1200a9;;;S-1-5-21-100-200-300-1002)"
                             : L"O:BAG:BAD:(A;;FA;;;SY)";
    m.volume_serial = 0x11223344;
    m.file_id[0] = static_cast<std::uint8_t>(id);
    m.attributes = directory ? FILE_ATTRIBUTE_DIRECTORY : FILE_ATTRIBUTE_ARCHIVE;
    m.directory = directory;
    m.dacl_protected = protected_dacl;
    return m;
}
P10ReaderConfig p10_config(const std::string& bytes) {
    const std::wstring root = root_path;
    const std::wstring p1 = root + L"S1PF_260926_A";
    const std::wstring p3 = p1 + L"\\config";
    return {meta(root,1,true,false), meta(p1,2,true), meta(p3,3,true),
            meta(p3+L"\\binding.json",4,false), bytes, sha256(bytes)};
}
struct FakeP10Calls final : P10Calls {
    Events& events;
    std::map<int,Metadata> data;
    std::string bytes;
    int fail_open = 0;
    bool bad_descriptor = false;
    int read_count = 0;
    std::vector<int> held, closed;
    FakeP10Calls(Events& e, P10ReaderConfig c) : events(e),
        data{{1,c.root},{2,c.p1},{3,c.p3},{4,c.p10}}, bytes(c.canonical_bytes) {}
    HANDLE open_root(const std::wstring& path, RootOpenSpec) override {
        check(path == L"C:\\", "fixed native root"); events.push_back("P10:root");
        held.push_back(1); return handle(1);
    }
    HANDLE open_relative(HANDLE parent, const std::wstring& component, OpenSpec,
                         const std::string& object) override {
        const int n = object == "P1" ? 2 : object == "P3" ? 3 : 4;
        check(number(parent) == n-1, "held relative parent");
        check(component == (n==2 ? L"S1PF_260926_A" : n==3 ? L"config" : L"binding.json"), "fixed component");
        events.push_back("P10:open-"+object);
        if (fail_open == n) throw ObservationFailure(ErrorKind::sharing_conflict,object,p10_read_profile,
            "relative-open","synthetic sharing conflict",static_cast<std::int32_t>(0xc0000043u),true,32,true);
        held.push_back(n); return handle(n);
    }
    Metadata inspect(HANDLE h, const std::string&, const std::string&) override {
        const int n=number(h); check(std::find(held.begin(),held.end(),n)!=held.end(),"inspect held handle");
        events.push_back("P10:inspect");
        Metadata result=data.at(n);
        if (bad_descriptor && n==4) result.sddl=L"O:SYG:SYD:P(A;;FA;;;SY)";
        return result;
    }
    std::string read_content(HANDLE h, std::size_t max_bytes) override {
        check(number(h)==4 && held.size()==4 && closed.empty(),"four handles held for P10 content");
        check(max_bytes==bytes.size(),"sealed byte bound");
        events.push_back("P10:read"); ++read_count; return bytes;
    }
    void close(HANDLE h) noexcept override { events.push_back("P10:close"); closed.push_back(number(h)); }
};
struct FakeToken final : ControllerSidPort {
    Events& events; std::string sid=sids.controller; int mode=0;
    explicit FakeToken(Events& e):events(e){}
    std::string read_current_process_sid() override {
        events.push_back("token");
        if(mode==1) throw ObservationFailure(ErrorKind::native_failure,"A2-token","A2/current-process-token/SID",
            "GetTokenInformation","synthetic token error",0,false,5,true);
        if(mode==2) throw std::runtime_error("synthetic token exception");
        if(mode==3) throw 7;
        return sid;
    }
};
struct FakeHead final : AuthenticatedHeadPort {
    Events& events; std::string bytes; int mode=0; int calls=0;
    FakeHead(Events& e,std::string b):events(e),bytes(std::move(b)){}
    std::string read_fixture_head() override {
        events.push_back("A3:synthetic-head"); ++calls;
        if(mode==1) throw ObservationFailure(ErrorKind::native_failure,"P11",
            "A3/ReadFixtureHead/authenticated-response","synthetic-response","synthetic A3 failure",0,false,5,true);
        if(mode==2) throw std::runtime_error("synthetic A3 exception");
        if(mode==3) throw 9;
        return bytes;
    }
};
struct Scenario {
    FixtureCase fixture;
    std::string p10, p11;
    ApprovedAuthorityBinding approved;
    Events events;
    FakeToken token;
    FakeHead head;
    std::shared_ptr<FakeP10Calls> native;
    explicit Scenario(FixtureCase f)
        : fixture(std::move(f)), p10(render_p10(sids,images)), p11(render_p11(fixture,sha256(p10))),
          approved{sids,images,sha256(p10),fixture.id,sha256(p11),"synthetic-g2-state-directory-id"},
          token(events), head(events,p11), native(std::make_shared<FakeP10Calls>(events,p10_config(p10))) {}
    AuthorityBindingResult bind() {
        return stage_a::windows::test_seam::bind_controller_precomparison(
            token,head,p10_config(p10),native,approved,fixture);
    }
};
void stopped(const AuthorityBindingResult& r, ErrorKind kind, const std::string& object,
             const std::string& step) {
    check(!r.evidence.ready_for_snapshot,"no readiness after failure");
    check(!r.comparison_input.has_value(),"no comparison input after failure");
    check(r.evidence.error==kind,"typed failure kind");
    check(r.evidence.object==object,"typed failure object");
    check(r.evidence.step==step,"typed failure step");
}
}
int main() {
    try {
        {
            Events events;
            FakeHead head(events, "unused synthetic head");
            FakeToken token(events);
            token.sid="S-1-5-21-100-200-300-9999";
            const FixtureCase fixture=fixture_cases().front();
            const std::string p10=render_p10(sids,images);
            const std::string p11=render_p11(fixture,sha256(p10));
            const ApprovedAuthorityBinding approved{sids,images,sha256(p10),fixture.id,
                                                    sha256(p11),"synthetic-g2-state-directory-id"};
            const auto result=bind_controller_precomparison(token,head,p10_config(p10),approved,fixture);
            check(!result.evidence.ready_for_snapshot && !result.comparison_input,
                  "production composition wrong synthetic SID stops before native open");
            check(events==Events({"token"}),"production wiring made no P10 open or A3 call");
        }
        for(const auto& fixture:fixture_cases()) {
            Scenario s(fixture); const auto r=s.bind();
            check(r.evidence.ready_for_snapshot && r.comparison_input.has_value(),"synthetic content binding ready");
            check(r.comparison_input->fixture.id==fixture.id,"fixed case preserved");
            check(r.comparison_input->protected_p11_bytes==s.p11,"exact synthetic head forwarded");
            check(r.comparison_input->rendered_p10_sha256==s.approved.rendered_p10_sha256,"sealed P10 hash forwarded");
            check(s.events.front()=="token","token port before protected reads");
            check(s.events.back()=="A3:synthetic-head","head after P10 verified and closed");
            check(s.native->read_count==2 && s.head.calls==1,"exact P10/P11 read counts");
            check(s.native->closed==std::vector<int>({4,3,2,1}),"P10 handles closed in reverse order");
        }
        const FixtureCase f=fixture_cases().front();
        { Scenario s(f); s.token.sid="S-1-5-21-100-200-300-9999"; const auto r=s.bind();
          stopped(r,ErrorKind::binding_failure,"A2-token","controller-sid");
          check(s.events==Events({"token"}) && s.head.calls==0,"wrong SID blocks all reads"); }
        { Scenario s(f); s.token.sid.clear(); const auto r=s.bind();
          stopped(r,ErrorKind::binding_failure,"A2-token","controller-sid");
          check(s.events==Events({"token"}),"empty SID blocks all reads"); }
        for(int mode:{1,2,3}) { Scenario s(f); s.token.mode=mode; const auto r=s.bind();
          stopped(r,mode==1?ErrorKind::native_failure:ErrorKind::incomplete,"A2-token",
                  mode==1?"GetTokenInformation":"read-current-sid");
          check(s.events==Events({"token"}) && s.head.calls==0,"token failure blocks all reads");
          if(mode==1) check(r.evidence.has_win32_error && r.evidence.win32_error==5,"raw token error retained"); }
        { Scenario s(f); s.native->fail_open=4; const auto r=s.bind();
          stopped(r,ErrorKind::sharing_conflict,"P10","relative-open");
          check(r.evidence.has_ntstatus && r.evidence.has_win32_error,"raw P10 errors retained");
          check(s.head.calls==0 && s.native->closed==std::vector<int>({3,2,1}),"P10 failure blocks A3 and closes held handles"); }
        { Scenario s(f); s.native->bad_descriptor=true; const auto r=s.bind();
          stopped(r,ErrorKind::identity_drift,"P10","initial-identity");
          check(s.head.calls==0,"P10 descriptor failure blocks A3"); }
        { Scenario s(f); s.approved.selected_case_id="unapproved"; const auto r=s.bind();
          stopped(r,ErrorKind::binding_failure,"P10","g2-selection");
          check(s.events==Events({"token"}),"case mismatch blocks protected reads"); }
        for(int mode:{1,2,3}) { Scenario s(f); s.head.mode=mode; const auto r=s.bind();
          stopped(r,mode==1?ErrorKind::native_failure:ErrorKind::incomplete,"P11",
                  mode==1?"synthetic-response":"read-fixture-head");
          check(s.native->read_count==2 && s.head.calls==1,"A3 attempted only after P10");
          if(mode==1) check(r.evidence.has_win32_error && r.evidence.win32_error==5,"raw A3 error retained"); }
        { Scenario s(f); s.head.bytes+="x"; const auto r=s.bind();
          stopped(r,ErrorKind::binding_failure,"P11","head-canonical-bytes");
          check(s.head.calls==1,"one synthetic head result rejected"); }
        std::cout << "controller authority composition synthetic checks: " << checks << " passed\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr << "controller authority composition synthetic failure after " << checks << " checks: " << e.what() << '\n';
        return 1;
    }
}
