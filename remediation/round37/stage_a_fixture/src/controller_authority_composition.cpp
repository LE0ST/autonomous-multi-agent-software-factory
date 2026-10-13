#include "controller_authority_composition.hpp"
#include "windows_p10_reader.hpp"

#include <exception>
#include <utility>

namespace stage_a::windows {
namespace {
constexpr char token_profile[] = "A2/current-process-token/SID";

// The accepted binder is the only caller of these methods. This type and any
// ProtectedAuthorityReader reference to it have translation-unit scope only.
class InternalProtectedReader final : public ProtectedAuthorityReader {
public:
    InternalProtectedReader(P10ReaderConfig config, AuthenticatedHeadPort& a3)
        : p10_(std::move(config)), a3_(a3) {}
    InternalProtectedReader(P10ReaderConfig config, std::shared_ptr<P10Calls> calls,
                            AuthenticatedHeadPort& a3)
        : p10_(std::move(config), std::move(calls)), a3_(a3) {}
    std::string read_verified_p10() override { return p10_.read_verified_p10(); }
    std::string read_authenticated_fixture_head() override { return a3_.read_fixture_head(); }
private:
    WindowsP10Reader p10_;
    AuthenticatedHeadPort& a3_;
};

AuthorityBindingResult token_stop(const FixtureCase& selected_case, const ObservationFailure& failure) {
    AuthorityBindingResult result;
    result.evidence.case_id = selected_case.id;
    result.evidence.error = failure.kind;
    result.evidence.object = failure.object;
    result.evidence.profile = failure.profile;
    result.evidence.step = failure.step;
    result.evidence.detail = failure.what();
    result.evidence.ntstatus = failure.ntstatus;
    result.evidence.has_ntstatus = failure.has_ntstatus;
    result.evidence.win32_error = failure.win32_error;
    result.evidence.has_win32_error = failure.has_win32_error;
    return result;
}

template <class MakeReader>
AuthorityBindingResult bind_internal(ControllerSidPort& token, const ApprovedAuthorityBinding& approved,
    const FixtureCase& selected_case, MakeReader make_reader) {
    std::string sid;
    try { sid = token.read_current_process_sid(); }
    catch (const ObservationFailure& failure) { return token_stop(selected_case, failure); }
    catch (const std::exception& failure) {
        return token_stop(selected_case, ObservationFailure(ErrorKind::incomplete, "A2-token",
                          token_profile, "read-current-sid", failure.what()));
    }
    catch (...) {
        return token_stop(selected_case, ObservationFailure(ErrorKind::incomplete, "A2-token",
                          token_profile, "read-current-sid", "non-standard C++ token-port exception"));
    }
    std::unique_ptr<ProtectedAuthorityReader> reader;
    try { reader = make_reader(); }
    catch (const ObservationFailure& failure) { return token_stop(selected_case, failure); }
    catch (const std::exception& failure) {
        return token_stop(selected_case, ObservationFailure(ErrorKind::incomplete, "P10",
                          p10_read_profile, "construct-reader", failure.what()));
    }
    catch (...) {
        return token_stop(selected_case, ObservationFailure(ErrorKind::incomplete, "P10",
                          p10_read_profile, "construct-reader", "non-standard C++ reader construction exception"));
    }
    try { return bind_protected_authority(*reader, approved, selected_case, sid); }
    catch (const ObservationFailure& failure) { return token_stop(selected_case, failure); }
    catch (const std::exception& failure) {
        return token_stop(selected_case, ObservationFailure(ErrorKind::incomplete, "P10/P11",
                          "protected-authority-binding", "bind-protected-authority", failure.what()));
    }
    catch (...) {
        return token_stop(selected_case, ObservationFailure(ErrorKind::incomplete, "P10/P11",
                          "protected-authority-binding", "bind-protected-authority",
                          "unexpected non-standard C++ binder exception"));
    }
}
} // namespace

AuthorityBindingResult bind_controller_precomparison(ControllerSidPort& token,
    AuthenticatedHeadPort& a3, P10ReaderConfig trusted_g2_p10,
    const ApprovedAuthorityBinding& approved, const FixtureCase& selected_case) {
    return bind_internal(token, approved, selected_case, [&]() {
        return std::make_unique<InternalProtectedReader>(std::move(trusted_g2_p10), a3);
    });
}

#if defined(STAGE_A_COMPOSITION_TEST_SEAM)
namespace test_seam {
AuthorityBindingResult bind_controller_precomparison(ControllerSidPort& token,
    AuthenticatedHeadPort& a3, P10ReaderConfig synthetic_p10,
    std::shared_ptr<P10Calls> synthetic_calls,
    const ApprovedAuthorityBinding& approved, const FixtureCase& selected_case) {
    return bind_internal(token, approved, selected_case, [&]() {
        return std::make_unique<InternalProtectedReader>(
            std::move(synthetic_p10), std::move(synthetic_calls), a3);
    });
}
}
#endif
} // namespace stage_a::windows
