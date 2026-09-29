#include "authority_binding.hpp"

#include <algorithm>
#include <stdexcept>
#include <utility>
#include <vector>

namespace stage_a {
namespace {
constexpr char p10_profile[] = "protected-P10/handle-bound-identity-read";
constexpr char p11_profile[] = "A3/ReadFixtureHead/authenticated-response";

[[noreturn]] void binding_stop(ErrorKind kind, const char* object, const char* profile,
                               const char* step, const char* message) {
    throw ObservationFailure(kind, object, profile, step, message);
}

std::string checked_hash(std::string_view bytes, const char* object, const char* step) {
    try { return sha256(bytes); }
    catch (const std::exception& failure) {
        throw ObservationFailure(ErrorKind::hash_failure, object, "BCrypt-SHA256/authority-binding", step, failure.what());
    }
}
} // namespace

AuthorityBindingResult bind_protected_authority(ProtectedAuthorityReader& reader,
                                                 const ApprovedAuthorityBinding& approved,
                                                 const FixtureCase& selected_case,
                                                 std::string_view actual_controller_sid) {
    AuthorityBindingResult result;
    auto& evidence = result.evidence;
    try {
        evidence.case_id = selected_case.id;
        if (approved.selected_case_id != selected_case.id || approved.state_directory_identity.empty())
            binding_stop(ErrorKind::binding_failure, "P10", p10_profile, "g2-selection", "case or state-directory binding missing");
        std::vector<FixtureCase> frozen_cases;
        try { frozen_cases = fixture_cases(); }
        catch (const std::exception& failure) {
            throw ObservationFailure(ErrorKind::hash_failure, "P10", "BCrypt-SHA256/frozen-case",
                                     "frozen-case-digest", failure.what());
        }
        const auto frozen = std::find_if(frozen_cases.begin(), frozen_cases.end(),
                                         [&](const FixtureCase& item) { return item.id == selected_case.id; });
        if (frozen == frozen_cases.end() || frozen->state != selected_case.state || frozen->status != selected_case.status ||
            frozen->generation != selected_case.generation || frozen->worker_runs != selected_case.worker_runs ||
            frozen->old_files != selected_case.old_files || frozen->latest_files != selected_case.latest_files ||
            frozen->old_digest != selected_case.old_digest || frozen->latest_digest != selected_case.latest_digest)
            binding_stop(ErrorKind::binding_failure, "P10", p10_profile, "frozen-case", "selected fixture differs from frozen source case");
        if (actual_controller_sid.empty() || actual_controller_sid != approved.created_sids.controller)
            binding_stop(ErrorKind::binding_failure, "A2-token", p10_profile, "controller-sid", "actual controller SID differs from created C SID");

        std::string expected_p10;
        try { expected_p10 = render_p10(approved.created_sids, approved.reviewed_images); }
        catch (const std::exception& failure) {
            throw ObservationFailure(ErrorKind::binding_failure, "P10", p10_profile, "g2-render", failure.what());
        }
        const auto expected_p10_hash = checked_hash(expected_p10, "P10", "p10-expected-hash");
        if (expected_p10_hash != approved.rendered_p10_sha256)
            binding_stop(ErrorKind::binding_failure, "P10", p10_profile, "g2-rendered-hash", "rendered P10 differs from approved G2 hash");

        std::string observed_p10;
        try { observed_p10 = reader.read_verified_p10(); }
        catch (const ObservationFailure&) { throw; }
        catch (const std::exception& failure) {
            throw ObservationFailure(ErrorKind::incomplete, "P10", p10_profile, "read-verified-p10", failure.what());
        }
        catch (...) {
            throw ObservationFailure(ErrorKind::incomplete, "P10", p10_profile, "read-verified-p10",
                                     "non-standard C++ exception from P10 reader");
        }
        if (observed_p10 != expected_p10)
            binding_stop(ErrorKind::binding_failure, "P10", p10_profile, "p10-canonical-bytes", "P10 bytes differ from approved canonical rendering");
        evidence.p10_sha256 = checked_hash(observed_p10, "P10", "p10-observed-hash");
        if (evidence.p10_sha256 != approved.rendered_p10_sha256)
            binding_stop(ErrorKind::binding_failure, "P10", p10_profile, "p10-observed-hash", "observed P10 hash differs from G2 record");

        std::string expected_p11;
        try { expected_p11 = render_p11(selected_case, evidence.p10_sha256); }
        catch (const std::exception& failure) {
            throw ObservationFailure(ErrorKind::binding_failure, "P11", p11_profile, "case-head-render", failure.what());
        }
        const auto expected_p11_hash = checked_hash(expected_p11, "P11", "p11-expected-hash");
        if (expected_p11_hash != approved.selected_p11_sha256)
            binding_stop(ErrorKind::binding_failure, "P11", p11_profile, "g2-head-hash", "selected P11 differs from approved G2 hash");

        std::string observed_p11;
        try { observed_p11 = reader.read_authenticated_fixture_head(); }
        catch (const ObservationFailure&) { throw; }
        catch (const std::exception& failure) {
            throw ObservationFailure(ErrorKind::incomplete, "P11", p11_profile, "read-fixture-head", failure.what());
        }
        catch (...) {
            throw ObservationFailure(ErrorKind::incomplete, "P11", p11_profile, "read-fixture-head",
                                     "non-standard C++ exception from P11 reader");
        }
        if (observed_p11 != expected_p11)
            binding_stop(ErrorKind::binding_failure, "P11", p11_profile, "head-canonical-bytes", "A3 head differs from selected canonical fixture record");
        evidence.p11_sha256 = checked_hash(observed_p11, "P11", "p11-observed-hash");
        if (evidence.p11_sha256 != approved.selected_p11_sha256)
            binding_stop(ErrorKind::binding_failure, "P11", p11_profile, "p11-observed-hash", "observed P11 hash differs from G2 record");

        result.comparison_input = BoundComparisonInput{selected_case, approved.state_directory_identity,
                                                        std::move(observed_p11), evidence.p10_sha256};
        evidence.ready_for_snapshot = true;
        evidence.detail = "canonical protected content bound; native reader proof and snapshot remain separate";
    } catch (const ObservationFailure& failure) {
        evidence.ready_for_snapshot = false;
        result.comparison_input.reset();
        evidence.error = failure.kind;
        evidence.object = failure.object; evidence.profile = failure.profile;
        evidence.step = failure.step; evidence.detail = failure.what();
        evidence.ntstatus = failure.ntstatus; evidence.has_ntstatus = failure.has_ntstatus;
        evidence.win32_error = failure.win32_error; evidence.has_win32_error = failure.has_win32_error;
    } catch (const std::exception& failure) {
        evidence.ready_for_snapshot = false;
        result.comparison_input.reset();
        evidence.error = ErrorKind::incomplete;
        evidence.object = "P10/P11"; evidence.profile = "protected-authority-binding";
        evidence.step = "unclassified-binding"; evidence.detail = failure.what();
    } catch (...) {
        evidence.ready_for_snapshot = false;
        result.comparison_input.reset();
        evidence.error = ErrorKind::incomplete;
        evidence.object = "P10/P11"; evidence.profile = "protected-authority-binding";
        evidence.step = "unclassified-binding"; evidence.detail = "unexpected non-standard C++ exception";
    }
    return result;
}
} // namespace stage_a
