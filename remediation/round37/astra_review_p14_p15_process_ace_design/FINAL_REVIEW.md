# Independent adversarial review: P14, P15 and the A3 process ACE

## Decision B — FOCUSED DESIGN CORRECTION REQUIRED

The architecture is viable. The proposed records separate endpoint evidence from case authority, and the proposed process mask supports the stated observations. However, the current text does not yet determine one reproducible, fail-closed native implementation. The corrections below are required before implementing the affected boundaries. This review does not change the proposal or authorize source or host operations.

**Status preserved exactly:**

- G1: HOLD / UNAPPROVED.
- S1: OPEN.
- Stage A: NOT PASSED.
- Round 3.7: NOT PASSED.

No P14/P15 object exists. No process-object C ACE has been applied. No endpoint collector or ETW provider is accepted. No native A2↔A3 transport is accepted. No G2/G3 action has occurred.

## Findings requiring correction

| ID | Concrete defect or ambiguity | Minimum correction; no operator choice made here |
| --- | --- | --- |
| F1 | The process descriptor is specified both as one exact protected descriptor and as a delta preserving every existing owner/group/ACE/right. No admissible initial descriptor is specified. An unexpected permissive baseline cannot satisfy both instructions merely by adding C's ACE. | Define the permitted initial descriptor and exact final comparison, or an equally explicit controlled-delta rule that rejects unexpected rights. State failure behavior before any pipe creation, independent BA readback, and the separate effective token-access gate. |
| F2 | P14's 2048-byte cap is not sufficient for all permitted values under the full-descriptor reading of its SDDL fields. The descriptor serialization is also not sufficiently canonical: full descriptor versus DACL-only, SID aliases and generic/numeric masks matter to the bytes. | Freeze the exact descriptor grammar/normalization and a length rule sufficient for every allowed value, or explicitly narrow the allowed values. Reconcile the reader, renderer, event normalization and manifest. Do not silently increase the bound in source. |
| F3 | Publication, current-generation admission and post-publication invalidation are described as outcomes but lack a complete consumer-visible state transition. Invalidation is in E1, which C/B cannot read. Holding a file/process handle does not deliver an E1 invalidation. P15/P11 file-instance bindings and the joint A2/A3 generation check are incompletely connected. | Specify the trusted inputs and admission/retirement protocol for each lifecycle, publication commit point, P15/P11 identity binding, transition exclusion, and what makes invalidation observable before acceptance. Decide whether collector survival is required after publication. Preserve the P14/P15 authority separation. |
| F4 | Startup ETW PID attribution is required to match an incarnation, but the payload has no creation time and the header timestamp is explicitly diagnostic only. The observation interval proving that the event came from the held incarnation is not defined. The term “private” real-time session also needs precise configuration/security semantics. | Define event-to-incarnation attribution, the P6 file-to-running-image continuity premise, session ownership/collision/security and sealing/drain rules. Identify the actual observation API for service SID type. Do not treat provider GUID, PID or source hash alone as authentication. |
| F5 | P14 has an explicit child-open profile; P15's manifest row does not equivalently freeze reader/creator flags, sharing, readback/retention and common A2/A3 validation. Protected-record repeat checks are not expressly distinguished from the accepted mutable snapshot algorithm. | Publish the exact P15 access/identity/content/lifetime profile and the P14 repeat/final checks or explicit reliance on an accepted protected-reader profile. Keep the verified ancestor walk; do not copy mutable inventory or mutable-ID rules. |

Sources: [endpoint contract §§2–6](../read_fixture_head_design_delta_after_luna_b/ENDPOINT_EVIDENCE_CONTRACT.md), [manifest rows and schemas](../read_fixture_head_design_delta_after_luna_b/G1_MANIFEST_DELTA_PROPOSAL.md), [commissioning sequence](../read_fixture_head_design_delta_after_luna_b/TWO_CASE_COMMISSIONING_CONTRACT.md). Each finding is developed in the linked reports below. F3–F5 are missing enforceable contracts, not claims of a demonstrated host exploit.

## Attempts to falsify the design that did not establish a defect

- **Unavoidable circular trust:** not established. BA can authenticate the protected executable/service/process independently of the pipe. Source-pinned startup telemetry can then report the process's own token and pipe creation. Those fields remain A3 observations, not independently queried BA measurements. F4 must make their attribution concrete.
- **Unavoidable B token access from the new ACE:** not established. `0x00101000` satisfies the process-handle prerequisite of `OpenProcessToken`; token access still depends on the token object's access check. The proposal's independent G2 denial requirement is necessary and can be meaningful. No denial was observed here.
- **P14 case selection or P15 endpoint authentication:** prohibited by the proposed contracts. Fixed path/service/image strings in P14 are equality assertions, not lookup instructions. P15 must not choose an endpoint or substitute for P14.
- **Removing READ_CONTROL or SYNCHRONIZE as surplus:** unsupported. Descriptor verification needs READ_CONTROL; the specified synchronous file-open mode needs SYNCHRONIZE. The C process mask also needs SYNCHRONIZE for liveness waiting.
- **A new wire case selector, token read by C, E1 read by C, signature scheme, replay database or heartbeat is necessarily required:** not established. These would be policy choices or rights changes, not deductions from the accepted requirements.

## Smallest separable source finding

The **pure P15 canonical parser/renderer and explicit expected-value comparison** can be specified from the six-field schema without host values. Its result must be ordinary parsed data, not proof of BA provenance, current generation, selected-case authority or P11 custody. It may neither choose a case nor mint a trusted production binding from untrusted input.

This narrow syntax slice is marked READY FOR SOURCE in the [matrix](IMPLEMENTABILITY_MATRIX.md); it does not make the proposed native resource model ready. F1–F5 must be adjudicated before their dependent source slices. No implementation occurs in this review. No accepted contracts, SnapshotSession, authority binding, P10/P11 readers, A2 composition/SID source, wire codec/immutability correction or nonce generator is reopened.

## Evidence and method

Read the complete controlling [design delta](../read_fixture_head_design_delta_after_luna_b/FINAL_DESIGN_DELTA.md), endpoint contract, manifest, commissioning, exchange/freshness, wire contract and next-step document; the complete [design adjudication](../independent_review_read_fixture_head_design_adjudication/FINAL_ADJUDICATION.md) package; and the complete [next source slice review](../independent_review_next_read_fixture_head_source_slice/FINAL_RECOMMENDATION.md) package. The latter explicitly says these resource/ACE details were proposed, not independently accepted.

Cross-checked the earlier [identity contract](../s1_g1_design_corrections_after_independent_review/FILE_IDENTITY_AND_PROBE_CONTRACT.md), [pipe reconciliation](../s1_g1_design_corrections_after_independent_review/LOGON_POLICY_AND_PIPE_GATE_RECONCILIATION.md), protected P10/P11 source interfaces and read paths, and accepted codec-immutability/nonce reviews. Windows API claims use Microsoft documentation linked at the claim. Synthetic schema-length arithmetic is identified as such; it is not a G2 observation or a source test.

Only repository documents/source were read, public API documentation consulted, and this review package written. No source/design artifact was modified, no tests/builds were run, and no fixture file, token, pipe, service, process, ACL, policy or ETW operation was performed. No git state-changing operation was performed.

## Report map

- [P14 authority, publication and lifetime](P14_AUTHORITY_AND_LIFETIME.md)
- [P15 authority, P11 binding and two-case lifecycle](P15_AUTHORITY_AND_LIFETIME.md)
- [Process ACE sufficiency, token boundary and installation](PROCESS_ACE_REVIEW.md)
- [Trust bootstrap, ETW and circularity](TRUST_CHAIN_AND_CIRCULARITY.md)
- [Descriptors and handle-relative access](DESCRIPTOR_AND_HANDLE_REVIEW.md)
- [Implementability and failure matrix](IMPLEMENTABILITY_MATRIX.md)
- [Minimum corrections and source order](RECOMMENDED_SOURCE_ORDER.md)
