#pragma once

#include <cstdint>
#include <map>
#include <string>
#include <string_view>
#include <vector>

namespace stage_a {

enum class Verdict { accept_current, reject_restored_old, reject_deleted, reject_mismatch, stop_inconclusive };
enum class ErrorKind { none, malformed, oversized, incomplete, sharing_conflict, reparse, identity_drift, unexpected_entry, native_failure, binding_failure, hash_failure };

struct Evidence {
    Verdict verdict = Verdict::stop_inconclusive;
    ErrorKind error = ErrorKind::none;
    // Raw fields are populated by the later native collector; no synthetic value
    // may be presented as a G2/G3 observation.
    std::string attempt_id, utc_time, case_id, object, profile, step, detail;
    std::string native_call, native_arguments, process_id, token_user_sid, broker_server_id;
    std::string p11_before_sha256, p11_after_sha256;
    std::int64_t ntstatus = 0;
    std::uint32_t win32_error = 0;
    bool has_ntstatus = false, has_win32_error = false;
    bool process_reached = false, broker_read_reached = false, snapshot_complete = false;
    std::vector<std::string> before_inventory, after_inventory;
    std::map<std::string, std::string> held_file_ids, content_sha256;
    std::string expected_digest, observed_digest, p11_sha256;
};

struct WriterResult { std::string artifact_sha256; std::uint32_t artifact_bytes; };
struct FixtureCase {
    std::string id, state, status;
    unsigned generation, worker_runs;
    std::map<std::string, std::string> old_files, latest_files;
    std::string old_digest, latest_digest;
};

struct SidSet { std::string writer, controller, broker; };
struct P10BuildHashes { std::string broker, controller, writer, capture; };

std::string sha256(std::string_view bytes);
std::string mutable_digest(const std::map<std::string, std::string>& files);
std::vector<FixtureCase> fixture_cases();
std::string p10_template();
std::string render_p10(const SidSet& sids, const P10BuildHashes& hashes);
std::string render_p11(const FixtureCase& fixture, std::string_view rendered_p10_sha256);
WriterResult parse_writer_result(std::string_view bytes);
Evidence writer_result_evidence(std::string_view bytes, std::string_view actual_m5_sha256, std::uint32_t actual_m5_bytes);
std::string verdict_name(Verdict value);
std::string error_name(ErrorKind value);

} // namespace stage_a
