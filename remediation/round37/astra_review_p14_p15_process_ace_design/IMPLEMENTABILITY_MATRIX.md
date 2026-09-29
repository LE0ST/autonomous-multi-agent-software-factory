# Implementability and failure matrix

## Scope of readiness

READY FOR SOURCE means a bounded source unit can be built against explicit trusted inputs without selecting new security policy. It does not mean accepted source exists, a host operation is authorized, actual G2 values are known, or a complete authenticated endpoint is ready. The accepted P10/P11 interfaces already illustrate this distinction.

Decision B concerns the combined resource/process/collector authority model. It does not require blocking every pure parser or limited observation helper until commissioning occurs.

## Requested source units

| Unit | Classification | Exact boundary / reason |
| --- | --- | --- |
| P14 canonical parser/renderer | **NEEDS DESIGN CLARIFICATION** | F2: descriptor representation and size limit can select different accepted bytes. Must reconcile field semantics, SDDL normalization and maximum before a production codec is frozen. No G2 IDs are needed to implement the corrected format with explicit values. |
| P14 protected reader | **NEEDS DESIGN CLARIFICATION** | F2/F3/F5: corrected codec, protected identity expectations, publication/current-generation inputs, lifetime and final observations. A later reader may consume trusted metadata and report validated file contents; it must not imply live endpoint authentication. Collector need not already exist to implement that seam. |
| P15 canonical parser/renderer | **READY FOR SOURCE** | Exact six-field grammar, fixed run/case alternatives, lowercase widths and explicit expected P10/P11 comparisons are determinate. Generation is an opaque input; this unit neither creates it nor establishes freshness/provenance. Parsing returns data, not a trusted current-case capability. |
| P15 protected reader | **NEEDS DESIGN CLARIFICATION** | F3/F5: exact access/share/readback/retention, current P15/P11 identity association and identical A2/A3 checks. It can subsequently take explicit trusted creation/lifecycle inputs; actual G2 values are not a source prerequisite. |
| Process DACL setup/readback helper | **NEEDS DESIGN CLARIFICATION** | F1: accepted initial descriptor versus exact final descriptor and permitted delta. The mask's API sufficiency is settled; host default assumptions must not choose a transformation. Actual token-denial evidence is a later independent gate. |
| BA endpoint collector | **NEEDS DESIGN CLARIFICATION** | F1–F4 and relevant F5: event attribution/session security/sealing, image continuity, process descriptor comparison, P14 encoding/publication and post-publication duty. Also depends on a separately reviewed broker startup emitter and record writer. This is not merely waiting for a real PID. |
| A2 live process comparator | **READY FOR SOURCE**, limited to direct observation/comparison | The proposed APIs/mask and PID/creation-time/path/liveness equality checks can be implemented against an already acquired connection and explicit trusted expected values, retaining the process handle. It must report only those observations/comparisons, not certify current P14 admission, token/pipe descriptor, SCM state, first-instance continuity or complete server authentication. Integration with the retirement/acceptance gate remains F3. |

The last row deliberately does not conflate a process comparator with the full A2 endpoint gate. No fixture pipe is created/connected or live process queried in this review. Future source review must preserve this narrow interface and no-token/no-debug/no-widened-access behavior.

## Dependencies and host evidence

| Item | Classification | What is actually missing |
| --- | --- | --- |
| Full A2 endpoint gate and authenticated native transport | **NEEDS DESIGN CLARIFICATION** now; then **BLOCKED BY ANOTHER SOURCE DEPENDENCY** | F3/F4 acceptance/lifetime contract, P14/P15 trusted readers, collector/provider, process comparator and server gate. Accepted wire/nonce slices alone do not provide provenance. |
| Collector integration once its design is corrected | **BLOCKED BY ANOTHER SOURCE DEPENDENCY** | Reviewed emitter/startup lifecycle, canonical P14 renderer, protected publication helper and process setup/readback. |
| Actual P14/P15 IDs, seals, BA creation/readback and C/B effective file access | **BLOCKED BY HOST EVIDENCE** | Separately authorized G2 observations, not values to invent before implementing an explicit-input reader. |
| Actual process before/after descriptor, C limited-open success and B-token query denial | **BLOCKED BY HOST EVIDENCE** | Actual identities/descriptors/effective access under the approved topology. API documentation proves sufficiency, not a denial on this host. |
| Real ETW loss/collision/access behavior and endpoint lifetime behavior | **BLOCKED BY HOST EVIDENCE** | Authorized commissioning after source/design acceptance. A passing synthetic codec is not this evidence. |

## Failure matrix

All incomplete or uncertain evidence means **STOP_INCONCLUSIVE**, not a completed fixture comparison, a claim of security denial, or permission to adopt another source. A service-startup failure may have its own native error; dependent A2 work still cannot advance.

| Stage | Failure class | Required result | Is the enforcement fully specified? |
| --- | --- | --- | --- |
| BA verifies P3/ancestors and expected source/config | Missing observation, wrong parent/volume/file identity, descriptor/reparse mismatch, unapproved image | No record creation/admission; stop and preserve failure evidence. | Core identity rule explicit; extend exact row to new resources in F5. |
| P11/P15 selection preparation | Wrong case/hash/P10, observed-as-expected seal, unknown current generation | No selected-case admission and no A3 start/attempt. | Content source explicit; current association/delivery needs F3. |
| P15 create/write/flush/readback | Collision, partial write, bad descriptor/bytes/identity, unavailable observation | No publication/adoption; residue only; separate exact-ID cleanup. | No-adoption explicit; complete native profile/commit needs F3/F5. |
| A2/A3 P15 load | Missing, malformed, stale, differing generations or wrong expected P11 identity | No privileged read/attempt; no request-based correction. | Required result clear; shared-generation mechanism needs F3/F5. |
| Process ACE preparation | Unexpected baseline, wrong owner/group, preexisting extra C/group rights | Fatal startup before pipe/RUNNING; no merge/adoption. | F1 must specify admissible baseline and exact comparison. |
| Process ACE set/readback | API error, unexpected final DACL/control flags | Fatal startup; BA must not publish P14. | Timing explicit; F1 defines equality. |
| Token-access commissioning gate | C can query B token under proposed topology, or required evidence unavailable | Reject commissioning/topology claim and return to review; do not silently change token ACL. | Requirement explicit; actual outcome pending host evidence. |
| ETW startup/observation | Session cannot be owned/verified, collision, loss, duplicate/malformed/wrong-origin event | No P14 publication; no A2 send. | Result explicit; F4 defines attribution/session/sealing. |
| SCM/process/image/startup facts | Missing/mismatched PID/start/path/hash/account/token report/pipe descriptor/first-instance result | No P14 publication; no broadened query privilege fallback. | Most comparisons explicit; F1/F4 complete inputs. |
| P14 generation/create/readback | RNG failure, collision, malformed/oversize record, descriptor/identity/seal mismatch | No admitted P14; no generation reuse or update-in-place. | F2 encoding; F3 publication commit; F5 final observations. |
| A2 P14 load and connect-time comparison | Missing/inaccessible/stale/mismatched P14; wrong connected PID/start/path; dead process | Close attempt handles; no send/comparison input. | Direct equality checks specified; F3 current-record admission still needed. |
| Loss during an A2 attempt | Pipe failure, process signal, original instance loss, required observation unavailable | Abort; discard response/comparison input; retire endpoint as required. | Direct loss cases clear; service/first-instance retirement propagation needs F3. |
| After P14 publication | Collector death, E1 invalidation, service stop before process/pipe teardown completes | No use of evidence whose required validity has ended. | F3: decide continued collector duty and consumer-visible retirement/acceptance behavior. |
| Endpoint replacement/restart | Same pipe/path/PID number with another process/incarnation or instance | Reject old evidence; separate lifecycle/new P14 before any send. | Prohibition clear; F3/F4 supply complete enforcement chain. |
| Case teardown | Late attempt, still-live service/first-instance, retained owned handle, inability to seal evidence | Do not start terminal lifecycle or delete by name. Stop transition. | F3 must identify admission owner and closure barrier. |
| Exact-ID removal/quarantine/recreation | Wrong object, unknown ID, name collision, incomplete prior closure | Stop; no overwrite or adoption. | Identity rule explicit; actual cleanup separately authorized. |

## Required versus additional hardening

Required by the proposal: protected BA-created records, one case at a time, fixed operation/path, independent canonical P11 expectation, current creation identities, before-send connected-peer comparison, first-instance continuity, no restart/retry/adoption, complete evidence or stop.

Necessary consequences: compare every value to its independent authority rather than to itself; associate startup telemetry with the measured incarnation; finish publication before admission; make retirement effective before acceptance; prevent transition from racing admitted attempts. F1–F5 address concrete missing rules for those obligations.

Not newly required: C token/SCM/P6/E1 access; a signed P14; a durable request replay database; permanent ETW; a heartbeat; global handle enumeration; process-memory hashing; extra fields on the accepted request; or altering accepted P10/P11/snapshot behavior. Any such choice would require its own justification and review.
