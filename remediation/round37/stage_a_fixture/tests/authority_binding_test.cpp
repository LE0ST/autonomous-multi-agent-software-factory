#include "../src/authority_binding.hpp"

#include <algorithm>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

using namespace stage_a;

namespace {
int checks = 0;
void require(bool value, const char* message) {
    ++checks;
    if (!value) throw std::runtime_error(message);
}

const SidSet sids{"S-1-5-21-100-200-300-1001", "S-1-5-21-100-200-300-1002", "S-1-5-21-100-200-300-1003"};
const P10BuildHashes images{std::string(64, '1'), std::string(64, '2'),
                            std::string(64, '3'), std::string(64, '4')};
constexpr char literal_p10_hash[] = "2d33e2e4e838be12f260759274ebc05b393921dabc0bdd309015acf702a1225e";
constexpr char literal_active_p11_hash[] = "ab17d1625b6ec18bf6ef63f8fb4da62fd54c3d76369b1280454dfac25c549243";
constexpr char literal_terminal_p11_hash[] = "42e2c6d830cc70dcc35bc0ae4e4f2821862ddc05164ac375ac3e82b7ce706e19";

// Independently transcribed from the accepted P10 field order and literal
// fixture digests. This is not assembled from p10_template() or render_p10().
std::string literal_p10() {
    return R"({"schema_version":1,"run_id":"260926_A","namespace_id":"s1pf-260926-a","repository_id":"s1pf-repo-260926-a","task_id":"s1pf-task-260926-a-01","broker_path":"C:\\S1PF_260926_A\\bin\\broker.exe","controller_path":"C:\\S1PF_260926_A\\bin\\controller.exe","writer_path":"C:\\S1PF_260926_A\\bin\\writer.exe","capture_path":"C:\\S1PF_260926_A\\bin\\native_capture.exe","pipe":"\\\\.\\pipe\\S1PF-broker-260926-A","broker_service":"S1PF_Broker_260926_A","controller_service":"S1PF_Controller_260926_A","marker":"S1PF-260926-A-STAGE-A-V1","a1_sid":"S-1-5-21-100-200-300-1001","a2_sid":"S-1-5-21-100-200-300-1002","a3_sid":"S-1-5-21-100-200-300-1003","broker_sha256":")" + std::string(64, '1') +
        R"(","controller_sha256":")" + std::string(64, '2') +
        R"(","writer_sha256":")" + std::string(64, '3') +
        R"(","capture_sha256":")" + std::string(64, '4') +
        R"(","active_old_digest":"5d77da03bca39bc5eb9884dd2c0b35738b16b3fe46c18f3353bc4699bfb768d3","active_latest_digest":"4d5d63027a1578256a003328664c48f1328cc5171ef29db4a9c0046b8ce4d22d","terminal_old_digest":"5d77da03bca39bc5eb9884dd2c0b35738b16b3fe46c18f3353bc4699bfb768d3","terminal_latest_digest":"eb2c260344d3c33075cb817a6ff8ce7c216b3a57dace342bb58fbe086ee33764"})";
}

std::string literal_p11(const std::string& case_id, const std::string& p10_hash) {
    if (case_id == "spent-budget-active")
        return R"({"schema_version":1,"marker":"S1PF-260926-A-STAGE-A-V1","p10_sha256":")" + p10_hash +
            R"(","case_id":"spent-budget-active","latest_digest":"4d5d63027a1578256a003328664c48f1328cc5171ef29db4a9c0046b8ce4d22d","generation":1,"worker_runs":1,"terminal":false})";
    return R"({"schema_version":1,"marker":"S1PF-260926-A-STAGE-A-V1","p10_sha256":")" + p10_hash +
        R"(","case_id":"spent-budget-terminal","latest_digest":"eb2c260344d3c33075cb817a6ff8ce7c216b3a57dace342bb58fbe086ee33764","generation":2,"worker_runs":1,"terminal":true})";
}

struct FakeReader final : ProtectedAuthorityReader {
    std::string p10, p11;
    std::vector<std::string> calls;
    bool fail_p10 = false, fail_p11 = false, fail_p11_generic = false;
    bool fail_p10_nonstandard = false, fail_p11_nonstandard = false;
    FakeReader(std::string assignment, std::string head) : p10(std::move(assignment)), p11(std::move(head)) {}
    std::string read_verified_p10() override {
        calls.push_back("P10");
        if (fail_p10_nonstandard) throw 17;
        if (fail_p10) throw ObservationFailure(ErrorKind::native_failure, "P10", "protected-P10/handle-bound-identity-read",
                                                "read-verified-p10", "synthetic P10 open failure",
                                                static_cast<std::int32_t>(0xC0000043u), true, 32, true);
        return p10;
    }
    std::string read_authenticated_fixture_head() override {
        calls.push_back("A3:ReadFixtureHead");
        if (fail_p11_nonstandard) throw 23;
        if (fail_p11_generic) throw std::runtime_error("synthetic missing A3 response");
        if (fail_p11) throw ObservationFailure(ErrorKind::binding_failure, "P11", "A3/ReadFixtureHead/authenticated-response",
                                                "broker-peer", "synthetic unauthenticated broker");
        return p11;
    }
};

ApprovedAuthorityBinding approved_for(const FixtureCase& fixture, const std::string& p10,
                                       const std::string& p11) {
    return {sids, images, sha256(p10), fixture.id, sha256(p11), "g2-state-directory-id-synthetic"};
}

struct MiniSession final : SnapshotSession {
    std::map<std::string, std::string> files;
    explicit MiniSession(std::map<std::string, std::string> value) : files(std::move(value)) {}
    std::string directory_identity() override { return "g2-state-directory-id-synthetic"; }
    std::vector<Entry> inventory() override {
        std::vector<Entry> out;
        for (const auto& [name, bytes] : files) { (void)bytes; out.push_back({name,"regular",name+"-id",directory_identity(),false}); }
        return out;
    }
    void hold_child(const std::string& name) override { if (!files.contains(name)) throw std::runtime_error("missing child"); }
    std::string held_identity(const std::string& name) override { return name+"-id"; }
    std::string read_child(const std::string& name) override { return files.at(name); }
};
struct MiniSource final : SnapshotSource {
    std::map<std::string, std::string> files;
    explicit MiniSource(std::map<std::string, std::string> value) : files(std::move(value)) {}
    std::unique_ptr<SnapshotSession> open(std::string_view profile) override {
        if (profile != directory_profile) throw std::runtime_error("wrong snapshot profile");
        return std::make_unique<MiniSession>(files);
    }
};

void test_case(const FixtureCase& fixture, const std::string& p10) {
    const auto p10_hash = sha256(p10);
    const auto p11 = literal_p11(fixture.id, p10_hash);
    require(p10_hash == literal_p10_hash, "independent P10 digest constant");
    require(sha256(p11) == (fixture.id == "spent-budget-active" ? literal_active_p11_hash : literal_terminal_p11_hash),
            "independent P11 digest constant");
    require(render_p10(sids, images) == p10, "independent canonical P10 literal");
    require(render_p11(fixture, p10_hash) == p11, "independent canonical P11 literal");
    auto approved = approved_for(fixture, p10, p11);
    FakeReader reader{p10, p11};
    const auto bound = bind_protected_authority(reader, approved, fixture, sids.controller);
    require(bound.evidence.ready_for_snapshot && bound.evidence.error == ErrorKind::none, "bound content ready only");
    require(bound.comparison_input.has_value(), "bound comparison input produced");
    require(reader.calls == std::vector<std::string>{"P10", "A3:ReadFixtureHead"}, "P10 verified before exactly one fixed head read");
    require(bound.evidence.p10_sha256 == approved.rendered_p10_sha256 && bound.evidence.p11_sha256 == approved.selected_p11_sha256,
            "approved source hashes retained");
    const auto& input = *bound.comparison_input;
    require(input.fixture.id == fixture.id && input.fixture.latest_digest == fixture.latest_digest &&
            input.state_directory_identity == approved.state_directory_identity && input.protected_p11_bytes == p11 &&
            input.rendered_p10_sha256 == p10_hash, "comparison receives only fixed case and protected binding");
    for (const auto& [files, expected] : std::vector<std::pair<std::map<std::string,std::string>,Verdict>>{
             {fixture.latest_files,Verdict::accept_current}, {fixture.old_files,Verdict::reject_restored_old},
             {{},Verdict::reject_deleted}}) {
        MiniSource source(files);
        const auto compared = compare_fresh_controller(source, input.fixture, input.state_directory_identity,
                                                        input.protected_p11_bytes, input.rendered_p10_sha256, true, true);
        require(compared.snapshot_complete && compared.verdict == expected,
                "bound input preserves accepted synthetic comparison decisions");
    }

    { auto changed = reader; changed.p10 += '\n'; changed.calls.clear();
      const auto r = bind_protected_authority(changed, approved, fixture, sids.controller);
      require(!r.evidence.ready_for_snapshot && !r.comparison_input && r.evidence.error == ErrorKind::binding_failure &&
              r.evidence.object == "P10" && r.evidence.step == "p10-canonical-bytes", "noncanonical P10 stops");
      require(changed.calls == std::vector<std::string>{"P10"}, "bad P10 cannot trigger A3 read"); }
    { auto changed = reader; changed.p11 += '\n'; changed.calls.clear();
      const auto r = bind_protected_authority(changed, approved, fixture, sids.controller);
      require(!r.evidence.ready_for_snapshot && !r.comparison_input && r.evidence.error == ErrorKind::binding_failure &&
              r.evidence.object == "P11" && r.evidence.step == "head-canonical-bytes", "noncanonical P11 stops"); }
    { FakeReader fake{p10,literal_p11(fixture.id == "spent-budget-active" ? "spent-budget-terminal" : "spent-budget-active",p10_hash)};
      const auto r = bind_protected_authority(fake, approved, fixture, sids.controller);
      require(!r.evidence.ready_for_snapshot && !r.comparison_input && r.evidence.object == "P11" &&
              r.evidence.step == "head-canonical-bytes", "other case head cannot switch comparison case"); }
    { auto changed = approved; changed.rendered_p10_sha256 = std::string(64,'a'); FakeReader fake{p10,p11};
      const auto r = bind_protected_authority(fake, changed, fixture, sids.controller);
      require(!r.evidence.ready_for_snapshot && r.evidence.step == "g2-rendered-hash" && fake.calls.empty(), "wrong G2 P10 hash stops before read"); }
    { auto changed = approved; changed.selected_p11_sha256 = std::string(64,'b'); FakeReader fake{p10,p11};
      const auto r = bind_protected_authority(fake, changed, fixture, sids.controller);
      require(!r.evidence.ready_for_snapshot && r.evidence.step == "g2-head-hash" && fake.calls == std::vector<std::string>{"P10"},
              "wrong G2 P11 hash stops before broker read"); }
    { FakeReader fake{p10,p11}; const auto r = bind_protected_authority(fake, approved, fixture, sids.writer);
      require(!r.evidence.ready_for_snapshot && r.evidence.object == "A2-token" && r.evidence.step == "controller-sid" && fake.calls.empty(),
              "actual A1 SID cannot stand in for controller"); }
    { auto changed = approved; changed.selected_case_id = "other-case"; FakeReader fake{p10,p11};
      const auto r = bind_protected_authority(fake, changed, fixture, sids.controller);
      require(!r.evidence.ready_for_snapshot && r.evidence.step == "g2-selection" && fake.calls.empty(), "no runtime case switch"); }
    { auto changed = approved; changed.state_directory_identity.clear(); FakeReader fake{p10,p11};
      const auto r = bind_protected_authority(fake, changed, fixture, sids.controller);
      require(!r.evidence.ready_for_snapshot && !r.comparison_input && r.evidence.step == "g2-selection" && fake.calls.empty(),
              "missing G2 directory identity cannot reach protected reader"); }
    { auto changed = fixture; changed.latest_files.at("state.json") += "changed"; FakeReader fake{p10,p11};
      const auto r = bind_protected_authority(fake, approved, changed, sids.controller);
      require(!r.evidence.ready_for_snapshot && r.evidence.step == "frozen-case" && fake.calls.empty(), "mutable case data cannot alter frozen comparison input"); }
    { FakeReader fake{p10,p11}; fake.fail_p10 = true;
      const auto r = bind_protected_authority(fake, approved, fixture, sids.controller);
      require(!r.evidence.ready_for_snapshot && !r.comparison_input && r.evidence.error == ErrorKind::native_failure &&
              r.evidence.object == "P10" && r.evidence.step == "read-verified-p10" && r.evidence.has_ntstatus &&
              r.evidence.ntstatus == static_cast<std::int32_t>(0xC0000043u) && r.evidence.has_win32_error &&
              r.evidence.win32_error == 32,
              "typed P10 native failure and raw codes preserved");
      require(fake.calls == std::vector<std::string>{"P10"}, "failed P10 read never reaches broker"); }
    { FakeReader fake{p10,p11}; fake.fail_p10_nonstandard = true;
      const auto r = bind_protected_authority(fake, approved, fixture, sids.controller);
      require(r.evidence.error == ErrorKind::incomplete && r.evidence.object == "P10" &&
              r.evidence.profile == "protected-P10/handle-bound-identity-read" &&
              r.evidence.step == "read-verified-p10", "non-standard P10 exception has typed provenance");
      require(!r.evidence.ready_for_snapshot && !r.comparison_input, "non-standard P10 exception cannot produce comparison input");
      require(fake.calls == std::vector<std::string>{"P10"}, "non-standard P10 exception makes no P11 call"); }
    { FakeReader fake{p10,p11}; fake.fail_p11 = true;
      const auto r = bind_protected_authority(fake, approved, fixture, sids.controller);
      require(!r.evidence.ready_for_snapshot && !r.comparison_input && r.evidence.error == ErrorKind::binding_failure &&
              r.evidence.object == "P11" && r.evidence.step == "broker-peer", "unauthenticated head stops");
      require(fake.calls == std::vector<std::string>{"P10","A3:ReadFixtureHead"}, "only fixed precomparison read attempted"); }
    { FakeReader fake{p10,p11}; fake.fail_p11_generic = true;
      const auto r = bind_protected_authority(fake, approved, fixture, sids.controller);
      require(!r.evidence.ready_for_snapshot && !r.comparison_input && r.evidence.error == ErrorKind::incomplete &&
              r.evidence.object == "P11" && r.evidence.step == "read-fixture-head", "missing broker response is typed incomplete stop"); }
    { FakeReader fake{p10,p11}; fake.fail_p11_nonstandard = true;
      const auto r = bind_protected_authority(fake, approved, fixture, sids.controller);
      require(r.evidence.error == ErrorKind::incomplete && r.evidence.object == "P11" &&
              r.evidence.profile == "A3/ReadFixtureHead/authenticated-response" &&
              r.evidence.step == "read-fixture-head", "non-standard P11 exception has typed provenance");
      require(!r.evidence.ready_for_snapshot && !r.comparison_input, "non-standard P11 exception cannot produce comparison input");
      require(fake.calls == std::vector<std::string>{"P10","A3:ReadFixtureHead"}, "non-standard P11 exception follows only P10 read"); }
}
} // namespace

int main() {
    try {
        const auto p10 = literal_p10();
        const auto cases = fixture_cases();
        require(cases.size() == 2, "two frozen fixture cases");
        for (const auto& fixture : cases) test_case(fixture, p10);
        std::cout << "PASS " << checks << " authority-binding synthetic checks; no protected open or broker call attempted\n";
        std::cout << "literal synthetic P10 SHA-256=" << sha256(p10) << '\n';
        for (const auto& fixture : cases)
            std::cout << fixture.id << " literal synthetic P11 SHA-256=" << sha256(literal_p11(fixture.id,sha256(p10))) << '\n';
        return 0;
    } catch (const std::exception& failure) {
        std::cerr << "FAIL after " << checks << " checks: " << failure.what() << '\n';
        return 1;
    }
}
