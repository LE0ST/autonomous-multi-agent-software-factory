#pragma once

#include "authority_binding.hpp"
#include <memory>

namespace stage_a::windows {

struct P10ReaderConfig;
class P10Calls;

// Future implementation must derive this value from the current A2 process
// token. This abstract port and its synthetic fakes are not token evidence.
class ControllerSidPort {
public:
    virtual ~ControllerSidPort() = default;
    virtual std::string read_current_process_sid() = 0;
};

// Future implementation must authenticate the connected A3 server and its
// response. This slice defines no pipe protocol, broker call or P11 open.
class AuthenticatedHeadPort {
public:
    virtual ~AuthenticatedHeadPort() = default;
    virtual std::string read_fixture_head() = 0;
};

// Only a separately implemented OS-token port may make the SID native evidence.
// The G2 approval and frozen case are trusted caller inputs, never M4/M5 data.
// Output is AuthorityBindingResult, not a snapshot or job-start verdict.
AuthorityBindingResult bind_controller_precomparison(ControllerSidPort& token,
    AuthenticatedHeadPort& a3, P10ReaderConfig trusted_g2_p10,
    const ApprovedAuthorityBinding& approved, const FixtureCase& selected_case);

#if defined(STAGE_A_COMPOSITION_TEST_SEAM)
namespace test_seam {
// Result-only synthetic seam; it never exposes ProtectedAuthorityReader.
AuthorityBindingResult bind_controller_precomparison(ControllerSidPort& synthetic_token,
    AuthenticatedHeadPort& synthetic_a3, P10ReaderConfig synthetic_p10,
    std::shared_ptr<P10Calls> synthetic_calls,
    const ApprovedAuthorityBinding& approved, const FixtureCase& selected_case);
}
#endif

} // namespace stage_a::windows
