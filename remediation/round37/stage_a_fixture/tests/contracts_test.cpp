#include "../src/contracts.hpp"
#include "../src/snapshot.hpp"
#include <array>
#include <functional>
#include <iostream>
#include <memory>
#include <set>
#include <stdexcept>

using namespace stage_a;
namespace {
int checks = 0;
void require(bool value, const char* message) { ++checks; if (!value) throw std::runtime_error(message); }
template<class F> void must_throw(F fn) { bool raised = false; try { fn(); } catch (const std::exception&) { raised = true; } require(raised, "expected rejection"); }

struct MockSession final : SnapshotSession {
    std::string directory_id = "G2-state-dir-id";
    std::map<std::string, std::string> files;
    std::vector<Entry> extra;
    std::vector<Entry> initial_override, final_override;
    std::string fail_step;
    bool held = false, final = false;
    unsigned inventory_calls = 0;
    std::set<std::string> opened;
    explicit MockSession(std::map<std::string, std::string> f) : files(std::move(f)) {}
    void fail(const std::string& step, const std::string& name, const char* profile) {
        if (fail_step == step) throw ObservationFailure(step == "hold" ? ErrorKind::sharing_conflict : ErrorKind::incomplete,
            name, profile, step, "synthetic native failure", -1073741757, true, 32, true);
    }
    std::string directory_identity() override { fail("directory-identity", "state/", directory_profile); return directory_id; }
    std::vector<Entry> inventory() override {
        ++inventory_calls;
        fail("inventory", "state/", directory_profile);
        if (inventory_calls == 1 && !initial_override.empty()) return initial_override;
        if (inventory_calls == 2 && !final_override.empty()) return final_override;
        std::vector<Entry> out;
        for (const auto& [name, bytes] : files) out.push_back({name, "regular", "id:" + name, directory_id, false});
        out.insert(out.end(), extra.begin(), extra.end());
        return out;
    }
    void hold_child(const std::string& name) override { fail("hold", name, child_profile); opened.insert(name); held = true; }
    std::string held_identity(const std::string& name) override { fail("held-identity", name, child_profile); return "id:" + name; }
    std::string read_child(const std::string& name) override {
        require(held && opened.contains(name), "read without held child");
        fail("read", name, child_profile);
        return files.at(name);
    }
};
struct MockSource final : SnapshotSource {
    std::unique_ptr<MockSession> next;
    std::string profile_seen;
    explicit MockSource(std::map<std::string, std::string> files) : next(std::make_unique<MockSession>(std::move(files))) {}
    std::unique_ptr<SnapshotSession> open(std::string_view profile) override {
        profile_seen = profile;
        if (next && next->fail_step == "open") throw ObservationFailure(ErrorKind::sharing_conflict, "state/", directory_profile, "open", "synthetic sharing conflict", -1073741757, true, 32, true);
        return std::move(next);
    }
};
Evidence compare(MockSource& source, const FixtureCase& fixture, bool reach = true) {
    const auto p10 = sha256("synthetic G2 rendered P10");
    return compare_fresh_controller(source, fixture, "G2-state-dir-id", render_p11(fixture, p10), p10, reach, reach);
}
struct FixtureOracle {
    const char* id;
    unsigned generation;
    const char* state;
    const char* terminal_status;
    std::map<std::string, std::string> old_files, latest_files;
    std::map<std::string, std::string> old_hashes, latest_hashes;
    const char* old_digest;
    const char* latest_digest;
};
const std::array<FixtureOracle, 2> literal_oracles = {{
    {"spent-budget-active", 1, "INIT", nullptr,
     {{"lock.bin", "S1PF-LOCK-V1\n"}, {"state.json", "{\"generation\":0,\"worker_runs\":0,\"terminal\":false}\n"}, {"witness.txt", "S1PF-WITNESS-V1:0:0:ACTIVE\n"}},
     {{"lock.bin", "S1PF-LOCK-V1\n"}, {"state.json", "{\"generation\":1,\"worker_runs\":1,\"terminal\":false}\n"}, {"witness.txt", "S1PF-WITNESS-V1:1:1:ACTIVE\n"}},
     {{"lock.bin", "970b93f640d45c28881099decf03f12535a7f8f0124e301490fc418688adfcec"}, {"state.json", "51a36f84657b0e8d9655a628a488cbcad78fe37de7240318528e05196e6c3bf3"}, {"witness.txt", "5986c5c825b9724522a7fa1a1b99dda9b4dd4612263a0119116428f3a576b7fe"}},
     {{"lock.bin", "970b93f640d45c28881099decf03f12535a7f8f0124e301490fc418688adfcec"}, {"state.json", "339a817ef474a6b7e4d522ee4fa6869bdc74eb54891a463521861ff601acd5fb"}, {"witness.txt", "34be10aa4b0f0cac2708bcde23010f3930e0086d690e2062ab8187d8d7b6788e"}},
     "5d77da03bca39bc5eb9884dd2c0b35738b16b3fe46c18f3353bc4699bfb768d3", "4d5d63027a1578256a003328664c48f1328cc5171ef29db4a9c0046b8ce4d22d"},
    {"spent-budget-terminal", 2, "HALT_HUMAN", "FAILED",
     {{"lock.bin", "S1PF-LOCK-V1\n"}, {"state.json", "{\"generation\":0,\"worker_runs\":0,\"terminal\":false}\n"}, {"witness.txt", "S1PF-WITNESS-V1:0:0:ACTIVE\n"}},
     {{"lock.bin", "S1PF-LOCK-V1\n"}, {"state.json", "{\"generation\":2,\"worker_runs\":1,\"terminal\":true}\n"}, {"witness.txt", "S1PF-WITNESS-V1:2:1:FAILED\n"}},
     {{"lock.bin", "970b93f640d45c28881099decf03f12535a7f8f0124e301490fc418688adfcec"}, {"state.json", "51a36f84657b0e8d9655a628a488cbcad78fe37de7240318528e05196e6c3bf3"}, {"witness.txt", "5986c5c825b9724522a7fa1a1b99dda9b4dd4612263a0119116428f3a576b7fe"}},
     {{"lock.bin", "970b93f640d45c28881099decf03f12535a7f8f0124e301490fc418688adfcec"}, {"state.json", "c1e348ab1690bc8cfe882ca9e42029ab694be32ad395213f08fa8090694d10d2"}, {"witness.txt", "0dc88bb4825effb66dcf6615df6f8b91547e29887586c71da9c2bf7da54012ab"}},
     "5d77da03bca39bc5eb9884dd2c0b35738b16b3fe46c18f3353bc4699bfb768d3", "eb2c260344d3c33075cb817a6ff8ce7c216b3a57dace342bb58fbe086ee33764"}
}};
void check_child_oracle(const std::map<std::string, std::string>& actual,
                        const std::map<std::string, std::string>& expected_bytes,
                        const std::map<std::string, std::string>& expected_hashes) {
    require(actual == expected_bytes, "literal fixture filenames and bytes");
    require(actual.size() == expected_hashes.size(), "literal child hash inventory");
    for (const auto& [name, hash] : expected_hashes)
        require(sha256(actual.at(name)) == hash, "literal child SHA-256");
}
struct FaultHashProvider final : SnapshotHashProvider {
    bool fail_p11 = false, fail_final = false;
    std::string hash_p11(std::string_view bytes) override {
        if (fail_p11) throw std::runtime_error("injected P11 BCrypt failure");
        return sha256(bytes);
    }
    std::string digest_mutable_set(const std::map<std::string, std::string>& files) override {
        if (fail_final) throw std::runtime_error("injected final BCrypt failure");
        return mutable_digest(files);
    }
};
Evidence compare_fault(MockSource& source, const FixtureCase& fixture, FaultHashProvider& provider) {
    const auto p10 = sha256("synthetic G2 rendered P10");
    return test_seam::compare_with_hash_provider(source, fixture, "G2-state-dir-id",
        render_p11(fixture, p10), p10, true, true, provider);
}
void test_fixtures() {
    const auto cases = fixture_cases();
    require(cases.size() == 2, "case count");
    for (std::size_t i = 0; i < literal_oracles.size(); ++i) {
        const auto& f = cases.at(i);
        const auto& oracle = literal_oracles[i];
        require(f.id == oracle.id && f.generation == oracle.generation && f.worker_runs == 1, "literal frozen case identity and witness");
        require(f.state == oracle.state, "frozen state field");
        if (oracle.terminal_status) require(f.status == oracle.terminal_status, "frozen terminal status");
        check_child_oracle(f.old_files, oracle.old_files, oracle.old_hashes);
        check_child_oracle(f.latest_files, oracle.latest_files, oracle.latest_hashes);
        require(f.old_digest == oracle.old_digest && f.latest_digest == oracle.latest_digest, "literal complete-set digest constants");
        require(mutable_digest(f.old_files) == oracle.old_digest && mutable_digest(f.latest_files) == oracle.latest_digest, "canonical digest matches independent constants");
        MockSource latest(f.latest_files); auto accepted = compare(latest, f);
        require(accepted.verdict == Verdict::accept_current && accepted.snapshot_complete && accepted.before_inventory.size() == 3, "untampered latest");
        require(latest.profile_seen == directory_profile, "snapshot profile");
        MockSource old(f.old_files); auto rollback = compare(old, f);
        require(rollback.verdict == Verdict::reject_restored_old && rollback.snapshot_complete && rollback.error == ErrorKind::none, "full old restore is comparison rejection");
        MockSource deleted({}); auto gone = compare(deleted, f);
        require(gone.verdict == Verdict::reject_deleted && gone.snapshot_complete && gone.before_inventory.empty(), "full deletion is comparison rejection");
    }
}
void test_snapshot_stops() {
    const auto f = fixture_cases()[0];
    MockSource missing(f.latest_files); missing.next->files.erase("witness.txt");
    require(compare(missing, f).verdict == Verdict::reject_mismatch, "complete missing child comparison");
    MockSource changed(f.latest_files); changed.next->files["witness.txt"] = "changed\n";
    require(compare(changed, f).verdict == Verdict::reject_mismatch, "complete changed child comparison");
    MockSource extra(f.latest_files); extra.next->extra.push_back({"sidecar", "regular", "id:sidecar", "G2-state-dir-id", false});
    auto added = compare(extra, f); require(added.verdict == Verdict::stop_inconclusive && added.error == ErrorKind::unexpected_entry, "unexpected child stop");
    MockSource reparse(f.latest_files); reparse.next->extra.push_back({"link", "regular", "id:link", "G2-state-dir-id", true});
    auto link = compare(reparse, f); require(link.verdict == Verdict::stop_inconclusive && link.error == ErrorKind::reparse, "reparse stop");
    MockSource malformed(f.latest_files); malformed.next->extra.push_back({"state.json", "regular", "id:state.json", "G2-state-dir-id", false});
    auto duplicate = compare(malformed, f); require(duplicate.verdict == Verdict::stop_inconclusive && duplicate.error == ErrorKind::malformed, "duplicate inventory stop");
    MockSource badtype(f.latest_files); badtype.next->extra.push_back({"unexpected-dir", "directory", "id:unexpected-dir", "G2-state-dir-id", false});
    require(compare(badtype, f).verdict == Verdict::stop_inconclusive, "unexpected type stop");
    MockSource incomplete(f.latest_files); incomplete.next->fail_step = "inventory";
    auto partial = compare(incomplete, f); require(partial.verdict == Verdict::stop_inconclusive && partial.error == ErrorKind::incomplete && partial.has_ntstatus && partial.has_win32_error, "incomplete native evidence");
    MockSource conflict(f.latest_files); conflict.next->fail_step = "hold";
    auto blocked = compare(conflict, f); require(blocked.verdict == Verdict::stop_inconclusive && blocked.error == ErrorKind::sharing_conflict && blocked.step == "hold", "sharing conflict stop");
    MockSource failed_read(f.latest_files); failed_read.next->fail_step = "read";
    auto unreadable = compare(failed_read, f);
    require(unreadable.verdict == Verdict::stop_inconclusive && !unreadable.snapshot_complete && unreadable.error == ErrorKind::incomplete && unreadable.step == "read", "held child read failure stop");
    MockSource failed_identity(f.latest_files); failed_identity.next->fail_step = "held-identity";
    auto unbound = compare(failed_identity, f);
    require(unbound.verdict == Verdict::stop_inconclusive && !unbound.snapshot_complete && unbound.error == ErrorKind::incomplete && unbound.step == "held-identity", "held identity failure stop");
    MockSource wrong_dir(f.latest_files); wrong_dir.next->directory_id = "replacement";
    require(compare(wrong_dir, f).error == ErrorKind::identity_drift, "directory identity stop");
    MockSource final_drift(f.latest_files);
    final_drift.next->final_override = {{"lock.bin", "regular", "id:lock.bin", "G2-state-dir-id", false},
        {"state.json", "regular", "replacement-id", "G2-state-dir-id", false},
        {"witness.txt", "regular", "id:witness.txt", "G2-state-dir-id", false}};
    auto drift = compare(final_drift, f);
    require(drift.verdict == Verdict::stop_inconclusive && drift.error == ErrorKind::identity_drift && !drift.snapshot_complete, "final identity drift stop");
    MockSource final_inventory_drift(f.latest_files);
    final_inventory_drift.next->final_override = {{"lock.bin", "regular", "id:lock.bin", "G2-state-dir-id", false},
        {"state.json", "regular", "id:state.json", "G2-state-dir-id", false}};
    auto renamed = compare(final_inventory_drift, f);
    require(renamed.verdict == Verdict::stop_inconclusive && !renamed.snapshot_complete && renamed.error == ErrorKind::identity_drift && renamed.step == "final-inventory", "final inventory drift stop");
    MockSource no_reach(f.latest_files); require(compare(no_reach, f, false).error == ErrorKind::binding_failure, "reach required");
}
void test_hash_failures() {
    const auto f = fixture_cases()[0];
    MockSource p11_source(f.latest_files); FaultHashProvider p11_provider; p11_provider.fail_p11 = true;
    const auto p11 = compare_fault(p11_source, f, p11_provider);
    require(p11.verdict == Verdict::stop_inconclusive && !p11.snapshot_complete && p11.error == ErrorKind::hash_failure, "P11 provider failure is typed stop");
    require(p11.object == "P11" && p11.profile == "BCrypt-SHA256/P11" && p11.step == "p11-hash" && p11_source.profile_seen.empty(), "P11 failure location and no state open");
    MockSource final_source(f.latest_files); FaultHashProvider final_provider; final_provider.fail_final = true;
    const auto final = compare_fault(final_source, f, final_provider);
    require(final.verdict == Verdict::stop_inconclusive && !final.snapshot_complete && final.error == ErrorKind::hash_failure, "final digest provider failure is typed stop");
    require(final.object == "state/" && final.profile == "BCrypt-SHA256/mutable-set-v1" && final.step == "final-mutable-digest", "final digest failure location");
    require(final.before_inventory.size() == 3 && final.after_inventory.size() == 3 && final.observed_digest.empty(), "final digest failure after complete inventories but before comparison");
}
void test_binding_and_parser() {
    const auto f = fixture_cases()[0];
    require(sha256("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "SHA256 known vector");
    const std::string hash(64, 'a');
    P10BuildHashes hashes{hash, hash, hash, hash};
    auto rendered = render_p10({"S-1-5-21-1", "S-1-5-21-2", "S-1-5-21-3"}, hashes);
    require(rendered.find("<PENDING") == std::string::npos && rendered.find("S-1-5-21-1") != std::string::npos, "created SID render");
    must_throw([&] { render_p10({"S-1-5-21-1", "S-1-5-21-1", "S-1-5-21-3"}, hashes); });
    require(render_p11(f, sha256(rendered)).find(f.latest_digest) != std::string::npos, "P11 latest binding");
    auto valid = std::string("{\"schema_version\":1,\"artifact_sha256\":\"") + hash + "\",\"artifact_bytes\":0}";
    auto accepted = writer_result_evidence(valid, hash, 0);
    require(accepted.verdict == Verdict::accept_current && accepted.detail == "DATA_ACCEPTED only", "zero is canonical data value");
    const auto decimal_result = [&hash](std::string_view decimal) {
        return std::string("{\"schema_version\":1,\"artifact_sha256\":\"") + hash + "\",\"artifact_bytes\":" + std::string(decimal) + "}";
    };
    require(parse_writer_result(decimal_result("1048576")).artifact_bytes == 1048576, "maximum artifact bytes accepted");
    require(parse_writer_result(decimal_result("1")).artifact_bytes == 1, "single nonzero decimal accepted");
    require(parse_writer_result(decimal_result("0")).artifact_bytes == 0, "canonical zero accepted");
    for (std::string_view bad_number : {"1048577", "00", "01", "+1", "-0", "1.0", "", "99999999999999999999"}) {
        auto invalid = writer_result_evidence(decimal_result(bad_number), hash, 0);
        require(invalid.verdict == Verdict::stop_inconclusive && invalid.error == ErrorKind::malformed, "decimal format/range classified malformed");
    }
    require(writer_result_evidence(std::string(257, 'x'), hash, 0).error == ErrorKind::oversized, "oversized category");
    require(writer_result_evidence("{}", hash, 0).error == ErrorKind::malformed, "malformed category");
    std::vector<std::string> bad = {"{}", valid + " ", valid + "\n", std::string(257, 'x'),
        std::string("{\"schema_version\":1,\"schema_version\":1,\"artifact_sha256\":\"") + hash + "\",\"artifact_bytes\":0}",
        std::string("{\"schema_version\":1,\"artifact_sha256\":\"") + hash + "\",\"artifact_bytes\":00}",
        std::string("{\"schema_version\":1,\"artifact_sha256\":\"") + hash + "\",\"artifact_bytes\":1048577}",
        std::string("{\"schema_version\":1,\"artifact_sha256\":\"") + hash + "\",\"artifact_bytes\":0,\"broker_verb\":\"WriteControlP12\"}",
        std::string("{\"schema_version\":1,\"artifact_sha256\":\"") + hash + "\",\"artifact_bytes\":0,\"task\":\"other\"}"};
    for (const auto& bytes : bad) {
        auto e = writer_result_evidence(bytes, hash, 0);
        require(e.verdict == Verdict::stop_inconclusive, "malformed writer bytes rejected locally");
    }
    require(writer_result_evidence(valid, hash, 1).verdict == Verdict::reject_mismatch, "independent M5 size correlation");
}
} // namespace
int main() {
    try { test_fixtures(); test_snapshot_stops(); test_hash_failures(); test_binding_and_parser();
        for (const auto& f : fixture_cases()) {
            std::cout << f.id << " old=" << f.old_digest << " latest=" << f.latest_digest << '\n';
            for (const auto& [name, bytes] : f.old_files)
                std::cout << f.id << " old " << name << " bytes=" << bytes.size() << " sha256=" << sha256(bytes) << '\n';
            for (const auto& [name, bytes] : f.latest_files)
                std::cout << f.id << " latest " << name << " bytes=" << bytes.size() << " sha256=" << sha256(bytes) << '\n';
        }
        std::cout << "P10 template sha256=" << sha256(p10_template()) << '\n';
        std::cout << "P10 template=" << p10_template() << '\n';
        std::cout << "P11 active synthetic=" << render_p11(fixture_cases()[0], sha256("synthetic G2 rendered P10")) << '\n';
        std::cout << "PASS " << checks << " checks; synthetic fixture/parser/snapshot seam only\n"; return 0;
    } catch (const std::exception& ex) { std::cerr << "FAIL after " << checks << " checks: " << ex.what() << '\n'; return 1; }
}
