# Formal adjudication — P14, P15 and the A3 process ACE

## Decision B — OPERATOR / RESOURCE DECISION REQUIRED

F1, F2, F4, and F5 are specified as focused technical corrections. The authority model is not reopened. F3’s publication and retirement behavior is substantially specified, but one trusted-delivery fact remains genuinely open: how A2 and A3 receive and validate an independently approved current P15 creation identity/seal/generation without reading E1 or trusting P15 to authenticate itself. O1–O7 do not name that delivery/custody mechanism. Engineering cannot silently choose a new shared resource, rights row, or startup channel.

The independently separable **pure P15 parser/renderer and explicit expected-value comparator remains READY FOR SOURCE** while that decision is pending. It cannot carry trusted provenance or lifecycle admission. [NEXT_G1_SOURCE_STEP.md](NEXT_G1_SOURCE_STEP.md) specifies this only pure increment and the stop boundary.

The controlling record is the accepted minimum contract, topology/delegation contracts, O1–O7 in the user authorization, the accepted P10/P11 readers, and the source-sequencing boundary. Astra’s report is a review claim and is adopted only where the comparison below supports it. The earlier Luna design adjudication remains controlling for authority placement; this package closes the later, local technical gaps without reversing that adjudication.

## Adjudication of Astra

| Finding | Adjudication | Effect |
|---|---|---|
| F1 process descriptor conflict | **Confirmed.** “Exact final descriptor” and “preserve all existing rights” need one admissible baseline. | Freeze the exact baseline and one-ACE delta in [F1](F1_PROCESS_DESCRIPTOR_CONTRACT.md). A permissive or different baseline is fatal; it is never merged or repaired. |
| F2 P14 bound/SDDL ambiguity | **Confirmed.** The proposal’s 2048-byte maximum rejects an allowed six-digit PID under the full-descriptor interpretation, and the descriptor fields lack one byte grammar. | Replace those fields with exact DACL-only canonical strings and use an 8192-byte maximum with enumerated field bounds in [F2](F2_P14_CANONICAL_FORMAT.md). Astra’s exact full-descriptor 2050-byte vector is not canonical under the corrected grammar; its six-digit PID remains permitted after descriptor canonicalization. |
| F3 publication/currentness | **Partly confirmed; one resource/custody decision remains.** E1 invalidation alone cannot notify C/B. P14 currentness and runtime failure can be tied to direct connection/process observations, but the independent current P15 file-instance/seal/generation expectation is not delivered to either reader by the accepted record. | [F3](F3_PUBLICATION_AND_LIFETIME.md) freezes commit, failure, transition, and no-E1-reader rules, and names the missing operator choice. |
| F4 ETW attribution/session | **Confirmed.** PID and provider GUID alone do not establish a process incarnation; “private real-time” conflates incompatible ETW modes. | Freeze a creation-time-bound startup event, exact ordinary real-time session, access policy, drain/seal point, service SID query, and P6 continuity premise in [F4](F4_ETW_ATTRIBUTION_AND_SESSION.md). |
| F5 P15/P14 native profiles | **Confirmed.** P15 needs separate creator and reader profiles; P14 needs explicit repeated/final observations. | Freeze exact profiles and common identity/content checks in [F5](F5_P15_PROTECTED_PROFILE.md). These are protected-record profiles, not mutable SnapshotSession inventory rules. |

Astra did not establish circular trust, a need for token-query access by C, an excessive `0x00101000` process mask, a need to remove `READ_CONTROL`/`SYNCHRONIZE`, or a need for HMAC, signatures, durable replay state, heartbeat, or another endpoint. Those conclusions remain unchanged.

The minimum remaining operator/resource choice is to name an already approved trusted delivery source for the current P15 file ID, canonical seal, selection generation, and matching P11 identity/seal to both A2 and A3—or explicitly authorize a narrowly scoped protected lifecycle-admission resource and its writer/owner/readers, integrity binding, and retirement rule. E1 cannot be that consumer path under the accepted role boundary. P15 cannot be its own independent expected value. No specific new resource or right is selected here.

## Required later edits to the proposed design/manifest

Do not rewrite the proposal in place as if it were accepted history. A versioned correction must update the affected proposed rows before native implementation:

- **A3 process object:** replace unspecified preserved-baseline wording with the F1 exact initial/final descriptor and BA-held before/after observation; add the ETW provider-callback barrier phases. No new process/service/token right is added by this correction.
- **P14:** change maximum `2048` to `8192`; define the three descriptor strings as the F2 DACL-only canonical form; retain owner/group as separate numeric SID fields; update the ETW event schema to the F4 three-stage, process-creation-time-bound transcript and maximum 4207-byte ID 1 event; specify the F3 commit/retirement semantics and F5 final observations.
- **P15:** add the F5 exact creator/reader open profiles, DACL, sharing, readback, repeat/final checks, and retention; add the F3 current-identity delivery as pending until the operator/resource choice is made. Do not label the P15 reader production-ready before that decision.
- **ETW/collector:** replace “private real-time” wording with F4’s ordinary real-time session, fixed session identity/security, provider access, event phases, drain/loss checks, and `QueryServiceConfig2W(SERVICE_CONFIG_SERVICE_SID_INFO)` requirement.

These are design/manifest deltas only; this task performs no edit to the controlling proposal.

## Evidence and precedence

- Astra’s finding and its own readiness distinction are in [FINAL_REVIEW.md](../astra_review_p14_p15_process_ace_design/FINAL_REVIEW.md), [PROCESS_ACE_REVIEW.md](../astra_review_p14_p15_process_ace_design/PROCESS_ACE_REVIEW.md), [DESCRIPTOR_AND_HANDLE_REVIEW.md](../astra_review_p14_p15_process_ace_design/DESCRIPTOR_AND_HANDLE_REVIEW.md), [P14_AUTHORITY_AND_LIFETIME.md](../astra_review_p14_p15_process_ace_design/P14_AUTHORITY_AND_LIFETIME.md), [P15_AUTHORITY_AND_LIFETIME.md](../astra_review_p14_p15_process_ace_design/P15_AUTHORITY_AND_LIFETIME.md), [TRUST_CHAIN_AND_CIRCULARITY.md](../astra_review_p14_p15_process_ace_design/TRUST_CHAIN_AND_CIRCULARITY.md), [IMPLEMENTABILITY_MATRIX.md](../astra_review_p14_p15_process_ace_design/IMPLEMENTABILITY_MATRIX.md), and [RECOMMENDED_SOURCE_ORDER.md](../astra_review_p14_p15_process_ace_design/RECOMMENDED_SOURCE_ORDER.md).
- The proposal being corrected is [ENDPOINT_EVIDENCE_CONTRACT.md](../read_fixture_head_design_delta_after_luna_b/ENDPOINT_EVIDENCE_CONTRACT.md), [G1_MANIFEST_DELTA_PROPOSAL.md](../read_fixture_head_design_delta_after_luna_b/G1_MANIFEST_DELTA_PROPOSAL.md), and [TWO_CASE_COMMISSIONING_CONTRACT.md](../read_fixture_head_design_delta_after_luna_b/TWO_CASE_COMMISSIONING_CONTRACT.md). These are proposed design, not previously accepted host permissions.
- Authority precedence comes from [the earlier Luna adjudication](../independent_review_read_fixture_head_design_adjudication/FINAL_ADJUDICATION.md), the accepted [exact topology proposal](../s1_g1_preapproval_design/EXACT_TOPOLOGY_PROPOSAL.md), [minimum Stage A contract](../s1_g1_design_corrections_after_independent_review/MINIMUM_STAGE_A_CONTRACT.md), and the accepted P10/P11 source/reviews. The operator decisions O1–O7 supplied with this task further constrain the correction.
- The P10 fixed `run_id` is `260926_A` in [contracts.cpp](../stage_a_fixture/src/contracts.cpp); the active-first/terminal-second provisioning order is controlling in the supplied O7 decision and the proposed two-case contract.

## Authority and status limits

P10 remains immutable pre-start static assignment. P15 remains the only selected-case record; P14 remains endpoint evidence and contains no case, P11, operation, retry, or request authority. A2 obtains the server PID from the connected pipe itself. A3’s authenticated response is not used to authenticate A3. A1/M4/M5 cannot choose a case, alter an expectation, invoke a retry, or select a native operation.

The contracts here specify what future source must do where closed, and preserve the exact open F3 custody decision. They are not observations of G2 identities, ACLs, process/token behavior, ETW behavior, or commissioning.

**G1 remains HOLD / UNAPPROVED. S1 remains OPEN. Stage A and Round 3.7 remain NOT PASSED.** No P14/P15 object or process ACE exists by virtue of this adjudication. No source or host work was performed.
