# Source readiness after F1–F5 adjudication

“Ready” describes a source boundary, not authorization to perform native or host work. This review selects only the pure P15 slice as the immediate increment; later rows are not authorized by this selection.

| Source unit | Status | Reason / prerequisite |
|---|---|---|
| Pure P15 parser/renderer + explicit comparison | **READY FOR SOURCE** | Six-field canonical grammar, exact case alternatives, fixed P10 run/digest expectations, byte lengths and failure semantics are sufficient. Must return ordinary data only. |
| P15 protected reader | **BLOCKED BY DESIGN** | F3 still requires an approved delivery source for the independent current P15/P11 creation identity/seal/generation expectation; the protected reader must not use the opened record as its own expectation. |
| Pure P14 parser/renderer | **READY FOR SOURCE** | F2 freezes the canonical field/descriptor grammar and 8192-byte bound. It is a separate future slice and is not selected in this increment. |
| P14 protected reader | **BLOCKED BY DESIGN** | Requires a reviewed source contract for the current-lifecycle P15 binding/admission dependency in F3, in addition to the pure P14 codec and protected-record implementation. |
| Process DACL setup/readback | **READY FOR SOURCE** | F1 freezes exact baseline/delta and the two BA-gated SCM startup checkpoints. It is a distinct later source review and does not authorize host application. |
| Bounded A2 process comparator | **BLOCKED BY SOURCE DEPENDENCY** | Requires native client connection source and P14 reader to provide actual connected PID and trusted expected fields. No host query is authorized. |
| Broker startup emitter | **BLOCKED BY SOURCE DEPENDENCY** | Requires process DACL source plus the accepted P11 custody and native startup/pipe source. |
| BA endpoint collector | **BLOCKED BY SOURCE DEPENDENCY** | Requires emitter, ETW session/security/seal source, P14 writer, P14 codec, and protected identity checks. |
| A2 endpoint gate | **BLOCKED BY SOURCE DEPENDENCY** | Requires P14/P15 readers, process comparator, nonce/codec, and lifecycle integration. |
| A3 connection gate | **BLOCKED BY SOURCE DEPENDENCY** | Requires P15 reader, accepted P11 custody, startup emitter and fixed message protocol/peer authentication source. |
| Full native transport | **BLOCKED BY SOURCE DEPENDENCY** | Requires all preceding components and independent review; no native A2↔A3 transport is accepted. |

No item is blocked because G2 identities must be fabricated: later readers can take explicitly trusted metadata. Actual resource creation, ACL results, token denial, ETW behavior, and two-case commissioning remain **BLOCKED BY HOST EVIDENCE** and separately authorized work.
