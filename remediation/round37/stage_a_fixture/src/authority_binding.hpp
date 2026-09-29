#pragma once

#include "snapshot.hpp"
#include <optional>

namespace stage_a {

// This record must come from the separately approved G2 creation manifest. Its
// case selection is explicit because the two-case P11 provisioning arrangement
// is still PENDING G1; it is never selected from mutable writer bytes.
struct ApprovedAuthorityBinding {
    SidSet created_sids;
    P10BuildHashes reviewed_images;
    std::string rendered_p10_sha256;
    std::string selected_case_id;
    std::string selected_p11_sha256;
    std::string state_directory_identity;
};

// The later native implementations of these operations must perform the full
// handle-bound P10 identity/descriptor read and authenticated A3 head read.
// This source increment supplies no filesystem or IPC implementation. In
// particular, A2 must never open P11 directly.
class ProtectedAuthorityReader {
public:
    virtual ~ProtectedAuthorityReader() = default;
    virtual std::string read_verified_p10() = 0;
    virtual std::string read_authenticated_fixture_head() = 0;
};

struct BoundComparisonInput {
    FixtureCase fixture;
    std::string state_directory_identity;
    std::string protected_p11_bytes;
    std::string rendered_p10_sha256;
};

struct AuthorityBindingEvidence {
    bool ready_for_snapshot = false; // content binding only, never a snapshot verdict
    ErrorKind error = ErrorKind::none;
    std::string object, profile, step, detail;
    std::string p10_sha256, p11_sha256, case_id;
    std::int64_t ntstatus = 0;
    std::uint32_t win32_error = 0;
    bool has_ntstatus = false, has_win32_error = false;
};

struct AuthorityBindingResult {
    AuthorityBindingEvidence evidence;
    std::optional<BoundComparisonInput> comparison_input;
};

// The actual controller SID is supplied by a later OS-token read, never by M4.
// This function has no writer input, path selector, broker verb, job launch,
// gate decision, or native operation. It permits exactly one fixed head read
// after P10 has been bound to the approved G2 hash and current controller SID.
AuthorityBindingResult bind_protected_authority(ProtectedAuthorityReader& reader,
                                                 const ApprovedAuthorityBinding& approved,
                                                 const FixtureCase& selected_case,
                                                 std::string_view actual_controller_sid);

} // namespace stage_a
