#include "snapshot.hpp"
#include <algorithm>
#include <set>

namespace stage_a {
ObservationFailure::ObservationFailure(ErrorKind k, std::string o, std::string p, std::string s, std::string message,
                                       std::int64_t nt, bool has_nt, std::uint32_t win, bool has_win)
    : std::runtime_error(std::move(message)), kind(k), object(std::move(o)), profile(std::move(p)), step(std::move(s)),
      ntstatus(nt), win32_error(win), has_ntstatus(has_nt), has_win32_error(has_win) {}

namespace {
std::vector<std::string> names(const std::vector<Entry>& entries) {
    std::vector<std::string> out;
    for (const auto& e : entries) if (e.name != "." && e.name != "..") out.push_back(e.name);
    std::sort(out.begin(), out.end());
    return out;
}
void check_entries(const std::vector<Entry>& entries, const FixtureCase& f, std::string_view dir_id, const char* step) {
    std::set<std::string> seen;
    for (const auto& e : entries) {
        if (e.name == "." || e.name == "..") continue;
        if (e.name.empty() || e.name.find_first_of("/\\\r\n\t") != std::string::npos || !seen.insert(e.name).second)
            throw ObservationFailure(ErrorKind::malformed, e.name, directory_profile, step, "malformed or duplicate entry");
        if (e.reparse) throw ObservationFailure(ErrorKind::reparse, e.name, child_profile, step, "reparse entry");
        if (e.type != "regular" || e.file_id.empty() || e.parent_id != dir_id)
            throw ObservationFailure(ErrorKind::identity_drift, e.name, child_profile, step, "type or parent identity mismatch");
        if (!f.latest_files.contains(e.name))
            throw ObservationFailure(ErrorKind::unexpected_entry, e.name, directory_profile, step, "unlisted state child");
    }
}
Evidence compare_impl(SnapshotSource& source, const FixtureCase& fixture,
                      std::string_view expected_directory_id,
                      std::string_view protected_p11_bytes,
                      std::string_view rendered_p10_sha256,
                      bool process_reached, bool broker_read_reached,
                      SnapshotHashProvider& hash_provider) {
    Evidence e; e.case_id = fixture.id; e.process_reached = process_reached; e.broker_read_reached = broker_read_reached;
    e.expected_digest = fixture.latest_digest;
    if (!process_reached || !broker_read_reached) {
        e.error = ErrorKind::binding_failure; e.step = "reach"; e.detail = "fresh A2 process and authenticated A3 read required"; return e;
    }
    try {
        try { e.p11_sha256 = hash_provider.hash_p11(protected_p11_bytes); }
        catch (const std::exception& failure) {
            throw ObservationFailure(ErrorKind::hash_failure, "P11", "BCrypt-SHA256/P11", "p11-hash", failure.what());
        }
        try {
            if (protected_p11_bytes != render_p11(fixture, rendered_p10_sha256))
                throw ObservationFailure(ErrorKind::binding_failure, "P11", "protected-marker-v1", "head-binding", "protected marker/head mismatch");
        } catch (const ObservationFailure&) { throw; }
          catch (const std::exception& failure) {
            throw ObservationFailure(ErrorKind::binding_failure, "P11", "protected-marker-v1", "head-binding", failure.what());
        }
        auto session = source.open(directory_profile);
        if (!session) throw ObservationFailure(ErrorKind::incomplete, "state/", directory_profile, "open", "null session");
        const std::string dir_id = session->directory_identity();
        if (dir_id.empty() || dir_id != expected_directory_id)
            throw ObservationFailure(ErrorKind::identity_drift, "state/", directory_profile, "directory-identity", "directory differs from G2 record");
        const auto before = session->inventory();
        e.before_inventory = names(before);
        check_entries(before, fixture, dir_id, "initial-inventory");
        std::map<std::string, std::string> ids, bytes;
        for (const auto& entry : before) {
            if (entry.name == "." || entry.name == "..") continue;
            session->hold_child(entry.name);
            const auto id = session->held_identity(entry.name);
            if (id != entry.file_id)
                throw ObservationFailure(ErrorKind::identity_drift, entry.name, child_profile, "hold-identity", "opened child differs from enumeration");
            ids.emplace(entry.name, id);
        }
        // The full present-child handle set is held before any validation read.
        for (const auto& [name, id] : ids) {
            bytes.emplace(name, session->read_child(name));
            e.held_file_ids[name] = id;
            try { e.content_sha256[name] = sha256(bytes.at(name)); }
            catch (const std::exception& failure) {
                throw ObservationFailure(ErrorKind::hash_failure, name, "BCrypt-SHA256/state-child", "child-hash", failure.what());
            }
        }
        const auto after = session->inventory();
        e.after_inventory = names(after);
        check_entries(after, fixture, dir_id, "final-inventory");
        if (e.before_inventory != e.after_inventory)
            throw ObservationFailure(ErrorKind::identity_drift, "state/", directory_profile, "final-inventory", "directory inventory changed");
        if (session->directory_identity() != dir_id)
            throw ObservationFailure(ErrorKind::identity_drift, "state/", directory_profile, "final-directory-identity", "directory identity changed");
        for (const auto& entry : after) {
            if (entry.name == "." || entry.name == "..") continue;
            if (ids.at(entry.name) != entry.file_id || session->held_identity(entry.name) != ids.at(entry.name))
                throw ObservationFailure(ErrorKind::identity_drift, entry.name, child_profile, "final-child-identity", "child identity changed");
            if (session->read_child(entry.name) != bytes.at(entry.name))
                throw ObservationFailure(ErrorKind::identity_drift, entry.name, child_profile, "final-content", "held content changed");
        }
        try { e.observed_digest = hash_provider.digest_mutable_set(bytes); }
        catch (const std::exception& failure) {
            throw ObservationFailure(ErrorKind::hash_failure, "state/", "BCrypt-SHA256/mutable-set-v1", "final-mutable-digest", failure.what());
        }
        e.snapshot_complete = true;
        if (bytes.empty()) { e.verdict = Verdict::reject_deleted; e.detail = "complete empty state set"; }
        else if (e.observed_digest == fixture.latest_digest && bytes == fixture.latest_files) {
            e.verdict = Verdict::accept_current; e.detail = "exact latest set";
        } else if (e.observed_digest == fixture.old_digest && bytes == fixture.old_files) {
            e.verdict = Verdict::reject_restored_old; e.detail = "complete old set";
        } else { e.verdict = Verdict::reject_mismatch; e.detail = "complete observed noncurrent set"; }
    } catch (const ObservationFailure& failure) {
        e.verdict = Verdict::stop_inconclusive; e.snapshot_complete = false;
        e.error = failure.kind; e.object = failure.object;
        e.profile = failure.profile; e.step = failure.step; e.detail = failure.what();
        e.ntstatus = failure.ntstatus; e.has_ntstatus = failure.has_ntstatus;
        e.win32_error = failure.win32_error; e.has_win32_error = failure.has_win32_error;
    } catch (const std::exception& failure) {
        e.verdict = Verdict::stop_inconclusive; e.snapshot_complete = false; e.error = ErrorKind::incomplete;
        e.object = "state/"; e.profile = directory_profile; e.step = "unclassified-observation"; e.detail = failure.what();
    }
    return e;
}

class BCryptSnapshotHashProvider final : public SnapshotHashProvider {
public:
    std::string hash_p11(std::string_view bytes) override { return sha256(bytes); }
    std::string digest_mutable_set(const std::map<std::string, std::string>& files) override { return mutable_digest(files); }
};
} // namespace

Evidence compare_fresh_controller(SnapshotSource& source, const FixtureCase& fixture,
                                  std::string_view expected_directory_id,
                                  std::string_view protected_p11_bytes,
                                  std::string_view rendered_p10_sha256,
                                  bool process_reached, bool broker_read_reached) {
    BCryptSnapshotHashProvider provider;
    return compare_impl(source, fixture, expected_directory_id, protected_p11_bytes,
                        rendered_p10_sha256, process_reached, broker_read_reached, provider);
}

namespace test_seam {
Evidence compare_with_hash_provider(SnapshotSource& source, const FixtureCase& fixture,
                                    std::string_view expected_directory_id,
                                    std::string_view protected_p11_bytes,
                                    std::string_view rendered_p10_sha256,
                                    bool process_reached, bool broker_read_reached,
                                    SnapshotHashProvider& hash_provider) {
    return compare_impl(source, fixture, expected_directory_id, protected_p11_bytes,
                        rendered_p10_sha256, process_reached, broker_read_reached, hash_provider);
}
} // namespace test_seam
} // namespace stage_a
