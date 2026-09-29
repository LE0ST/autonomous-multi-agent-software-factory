#include "contracts.hpp"

#include <windows.h>
#include <bcrypt.h>
#include <algorithm>
#include <array>
#include <cctype>
#include <limits>
#include <stdexcept>

namespace stage_a {
namespace {
bool hex64(std::string_view s) {
    return s.size() == 64 && std::all_of(s.begin(), s.end(), [](char c) { return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'); });
}
bool sid(std::string_view s) {
    if (s.size() < 5 || s.substr(0, 4) != "S-1-" || s.back() == '-') return false;
    bool digit = false;
    for (char c : s.substr(4)) {
        if (c == '-') { if (!digit) return false; digit = false; }
        else if (c >= '0' && c <= '9') digit = true;
        else return false;
    }
    return digit;
}
std::string quoted(std::string_view s) {
    std::string out = "\"";
    for (char c : s) {
        if (c == '"' || c == '\\') out += '\\';
        if (static_cast<unsigned char>(c) < 0x20) throw std::invalid_argument("control character");
        out += c;
    }
    return out + '"';
}
std::string decimal(std::uint32_t n) { return std::to_string(n); }
} // namespace

std::string sha256(std::string_view bytes) {
    if (bytes.size() > (std::numeric_limits<ULONG>::max)()) throw std::length_error("SHA-256 input too large");
    BCRYPT_ALG_HANDLE alg = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    if (BCryptOpenAlgorithmProvider(&alg, BCRYPT_SHA256_ALGORITHM, nullptr, 0) < 0) throw std::runtime_error("BCryptOpenAlgorithmProvider");
    std::array<UCHAR, 32> digest{};
    auto* data = reinterpret_cast<PUCHAR>(const_cast<char*>(bytes.data()));
    NTSTATUS status = BCryptCreateHash(alg, &hash, nullptr, 0, nullptr, 0, 0);
    if (status >= 0) status = BCryptHashData(hash, data, static_cast<ULONG>(bytes.size()), 0);
    if (status >= 0) status = BCryptFinishHash(hash, digest.data(), static_cast<ULONG>(digest.size()), 0);
    if (hash) BCryptDestroyHash(hash);
    BCryptCloseAlgorithmProvider(alg, 0);
    if (status < 0) throw std::runtime_error("BCrypt SHA-256");
    constexpr char alphabet[] = "0123456789abcdef";
    std::string result;
    for (UCHAR b : digest) { result += alphabet[b >> 4]; result += alphabet[b & 15]; }
    return result;
}

std::string mutable_digest(const std::map<std::string, std::string>& files) {
    // Canonical v1: sorted ASCII file names, regular type, decimal byte length and SHA-256.
    // The final LF is included. No path, directory metadata or unordered-map iteration enters the digest.
    std::string manifest = "S1PF-MUTABLE-SET-V1\n";
    for (const auto& [name, bytes] : files) {
        if (name.empty() || name == "." || name == ".." || name.find_first_of("/\\\r\n\t") != std::string::npos)
            throw std::invalid_argument("invalid child name");
        manifest += name + "\tregular\t" + std::to_string(bytes.size()) + "\t" + sha256(bytes) + "\n";
    }
    return sha256(manifest);
}

std::vector<FixtureCase> fixture_cases() {
    std::vector<FixtureCase> cases = {
        {"spent-budget-active", "INIT", "ACTIVE", 1, 1,
            {{"lock.bin", "S1PF-LOCK-V1\n"}, {"state.json", "{\"generation\":0,\"worker_runs\":0,\"terminal\":false}\n"}, {"witness.txt", "S1PF-WITNESS-V1:0:0:ACTIVE\n"}},
            {{"lock.bin", "S1PF-LOCK-V1\n"}, {"state.json", "{\"generation\":1,\"worker_runs\":1,\"terminal\":false}\n"}, {"witness.txt", "S1PF-WITNESS-V1:1:1:ACTIVE\n"}}, "", ""},
        {"spent-budget-terminal", "HALT_HUMAN", "FAILED", 2, 1,
            {{"lock.bin", "S1PF-LOCK-V1\n"}, {"state.json", "{\"generation\":0,\"worker_runs\":0,\"terminal\":false}\n"}, {"witness.txt", "S1PF-WITNESS-V1:0:0:ACTIVE\n"}},
            {{"lock.bin", "S1PF-LOCK-V1\n"}, {"state.json", "{\"generation\":2,\"worker_runs\":1,\"terminal\":true}\n"}, {"witness.txt", "S1PF-WITNESS-V1:2:1:FAILED\n"}}, "", ""}
    };
    for (auto& c : cases) { c.old_digest = mutable_digest(c.old_files); c.latest_digest = mutable_digest(c.latest_files); }
    return cases;
}

std::string p10_template() {
    return R"({"schema_version":1,"run_id":"260926_A","namespace_id":"s1pf-260926-a","repository_id":"s1pf-repo-260926-a","task_id":"s1pf-task-260926-a-01","broker_path":"C:\\S1PF_260926_A\\bin\\broker.exe","controller_path":"C:\\S1PF_260926_A\\bin\\controller.exe","writer_path":"C:\\S1PF_260926_A\\bin\\writer.exe","capture_path":"C:\\S1PF_260926_A\\bin\\native_capture.exe","pipe":"\\\\.\\pipe\\S1PF-broker-260926-A","broker_service":"S1PF_Broker_260926_A","controller_service":"S1PF_Controller_260926_A","marker":"S1PF-260926-A-STAGE-A-V1","a1_sid":"<PENDING_G2_A1_SID>","a2_sid":"<PENDING_G2_A2_SID>","a3_sid":"<PENDING_G2_A3_SID>","broker_sha256":"<PENDING_G1_BROKER_SHA256>","controller_sha256":"<PENDING_G1_CONTROLLER_SHA256>","writer_sha256":"<PENDING_G1_WRITER_SHA256>","capture_sha256":"<PENDING_G1_CAPTURE_SHA256>","active_old_digest":")" + fixture_cases()[0].old_digest + R"(","active_latest_digest":")" + fixture_cases()[0].latest_digest + R"(","terminal_old_digest":")" + fixture_cases()[1].old_digest + R"(","terminal_latest_digest":")" + fixture_cases()[1].latest_digest + "\"}";
}

std::string render_p10(const SidSet& sids, const P10BuildHashes& hashes) {
    if (!sid(sids.writer) || !sid(sids.controller) || !sid(sids.broker) || sids.writer == sids.controller || sids.writer == sids.broker || sids.controller == sids.broker)
        throw std::invalid_argument("distinct created SIDs required");
    if (!hex64(hashes.broker) || !hex64(hashes.controller) || !hex64(hashes.writer) || !hex64(hashes.capture))
        throw std::invalid_argument("reviewed executable hashes required");
    std::string out = p10_template();
    const auto replace_one = [&out](std::string_view key, std::string_view value) {
        const auto at = out.find(key);
        if (at == std::string::npos || out.find(key, at + key.size()) != std::string::npos) throw std::logic_error("template slot");
        out.replace(at, key.size(), value);
    };
    replace_one("<PENDING_G2_A1_SID>", sids.writer);
    replace_one("<PENDING_G2_A2_SID>", sids.controller);
    replace_one("<PENDING_G2_A3_SID>", sids.broker);
    replace_one("<PENDING_G1_BROKER_SHA256>", hashes.broker);
    replace_one("<PENDING_G1_CONTROLLER_SHA256>", hashes.controller);
    replace_one("<PENDING_G1_WRITER_SHA256>", hashes.writer);
    replace_one("<PENDING_G1_CAPTURE_SHA256>", hashes.capture);
    return out;
}

std::string render_p11(const FixtureCase& fixture, std::string_view rendered_p10_sha256) {
    if (!hex64(rendered_p10_sha256)) throw std::invalid_argument("rendered P10 hash required");
    return "{\"schema_version\":1,\"marker\":\"S1PF-260926-A-STAGE-A-V1\",\"p10_sha256\":" + quoted(rendered_p10_sha256) +
        ",\"case_id\":" + quoted(fixture.id) + ",\"latest_digest\":" + quoted(fixture.latest_digest) +
        ",\"generation\":" + decimal(fixture.generation) + ",\"worker_runs\":" + decimal(fixture.worker_runs) +
        ",\"terminal\":" + (fixture.status == "FAILED" ? "true" : "false") + "}";
}

WriterResult parse_writer_result(std::string_view bytes) {
    if (bytes.size() > 256) throw std::length_error("writer result over 256 bytes");
    constexpr std::string_view prefix = "{\"schema_version\":1,\"artifact_sha256\":\"";
    constexpr std::string_view middle = "\",\"artifact_bytes\":";
    if (bytes.substr(0, prefix.size()) != prefix) throw std::invalid_argument("writer result prefix");
    bytes.remove_prefix(prefix.size());
    if (bytes.size() < 64 + middle.size() + 2 || !hex64(bytes.substr(0, 64))) throw std::invalid_argument("writer result digest");
    WriterResult result{std::string(bytes.substr(0, 64)), 0};
    bytes.remove_prefix(64);
    if (bytes.substr(0, middle.size()) != middle) throw std::invalid_argument("writer result fields");
    bytes.remove_prefix(middle.size());
    if (bytes.size() < 2 || bytes.back() != '}' || (bytes[0] == '0' && bytes.size() != 2)) throw std::invalid_argument("writer result decimal");
    bytes.remove_suffix(1);
    for (char c : bytes) {
        if (c < '0' || c > '9' || result.artifact_bytes > (1048576u - static_cast<unsigned>(c - '0')) / 10u)
            throw std::invalid_argument("writer result decimal range");
        result.artifact_bytes = result.artifact_bytes * 10u + static_cast<unsigned>(c - '0');
    }
    return result;
}

Evidence writer_result_evidence(std::string_view bytes, std::string_view actual_m5_sha256, std::uint32_t actual_m5_bytes) {
    Evidence e; e.object = "M4/writer-result.json"; e.profile = "data-only-v1"; e.step = "parse-and-correlate";
    try {
        auto parsed = parse_writer_result(bytes);
        if (parsed.artifact_sha256 != actual_m5_sha256 || parsed.artifact_bytes != actual_m5_bytes) {
            e.verdict = Verdict::reject_mismatch; e.detail = "M5 correlation mismatch";
        } else { e.verdict = Verdict::accept_current; e.detail = "DATA_ACCEPTED only"; }
    } catch (const std::length_error& ex) { e.error = ErrorKind::oversized; e.detail = ex.what(); }
      catch (const std::invalid_argument& ex) { e.error = ErrorKind::malformed; e.detail = ex.what(); }
    return e;
}

std::string verdict_name(Verdict v) {
    switch (v) { case Verdict::accept_current: return "ACCEPT_CURRENT"; case Verdict::reject_restored_old: return "REJECT_RESTORED_OLD"; case Verdict::reject_deleted: return "REJECT_DELETED"; case Verdict::reject_mismatch: return "REJECT_MISMATCH"; default: return "STOP_INCONCLUSIVE"; }
}
std::string error_name(ErrorKind e) {
    switch (e) { case ErrorKind::none: return "NONE"; case ErrorKind::malformed: return "MALFORMED"; case ErrorKind::oversized: return "OVERSIZED"; case ErrorKind::incomplete: return "INCOMPLETE"; case ErrorKind::sharing_conflict: return "SHARING_CONFLICT"; case ErrorKind::reparse: return "REPARSE"; case ErrorKind::identity_drift: return "IDENTITY_DRIFT"; case ErrorKind::unexpected_entry: return "UNEXPECTED_ENTRY"; case ErrorKind::native_failure: return "NATIVE_FAILURE"; case ErrorKind::binding_failure: return "BINDING_FAILURE"; case ErrorKind::hash_failure: return "HASH_FAILURE"; }
    return "UNKNOWN";
}
} // namespace stage_a
