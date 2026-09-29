# Independent security review — Round 3.7 S5 alias repair

## Finding

**A — S5 satisfies its declared capability-identity and first-use boundary under the assumptions below.** I found no reproducible alias bypass in the final implementation. This is an S5 finding only; it is not an overall Round 3.7 security PASS.

The authority check is object identity. `authorize_recovery()` creates a fresh opaque object and stores it in a manager-local registry keyed by built-in `id(capability)`. Each registry entry holds the issued object strongly together with generation, resolved repository, base branch, and mode. `_recover()` looks up the integer ID and requires `entry[0] is authorization`; it deletes only that matching entry while holding the state lock. The strong reference prevents ID reuse while that authority is outstanding. A consumed object has no registry entry, so later ID reuse cannot restore its spent authority.

The lookup and identity check do not call the supplied object’s `__hash__` or `__eq__`. An alias with a colliding hash, a permissive equality method, raising hash/equality methods, an unhashable object, and distinct ordinary objects that compare equal were rejected with the dedicated authorization error. The authentic object remained usable after an alias rejection.

Consumption occurs before the mode and generation checks, strict context/Git/evidence validation, state transition, transaction reload, and persistence. The original S5 failure matrix injects context drift, evidence loss on read, Git read failure, persistence failure, transition failure, and wrong mode. It restores valid fixture conditions and confirms strict validation succeeds before replaying the same object; replay is rejected. Generation drift was also independently injected on the final tree and replay was rejected. A fresh object was issued only after strict validation passed again.

The state lock serializes competing presentations. Reentrant and concurrent presentation of the same authentic capability cannot use it twice. `_active_recovery_cap` is set only after the registry entry is consumed and is cleared in `finally`. `_transaction()` permits a terminal recovery transition only when its authorization is the active object and its immediate caller is the installed `_recover()` code. A general transaction or callback therefore cannot use a visible active object to authorize a terminal transition through the supported API.

The successful merge recovery and exact B-to-C integration control passed. The separate successful audit recovery control passed with three authentic gate records and preserved its budgets and epoch. S4 completion, failed-CAS, unresolved-intent, post-CAS persistence failure, and reentrant completion controls passed.

## Preservation verification

The final reread matched **15/15 production hashes**. Of those 15 reviewed production files, only `orchestrator/state_manager.py` differs from the prior S5 baseline. All **11/11 frozen manifests**, **25/25 listed frozen source entries**, and **25/25 manifest entries** match. The new alias test and its manifest retain their frozen hashes.

The previous independent S5 review inventory matches **21/21**. The predecessor S4 evidence listed before the S5 edit matches **34/34**. Sol’s final run evidence has **45/45** process-record, console, and JUnit hashes matching on reread; all 15 JUnit totals and actual exit codes match the recorded values. The previous review’s initially incorrect probe harness (missing `threading` import) remains preserved with its corrected rerun. This review also preserves its initial preservation report, which incorrectly joined repository-relative artifact paths under the inventory directory; `PRESERVATION_VERIFICATION_CORRECTED.json` records the corrected root-relative check at 21/21.

Detailed records are in [final on-disk verification](FINAL_ON_DISK_VERIFICATION.json), [corrected preservation verification](PRESERVATION_VERIFICATION_CORRECTED.json), and [final evidence verification](FINAL_EVIDENCE_VERIFICATION.json). The initial incorrect preservation report remains at [PRESERVATION_VERIFICATION.json](PRESERVATION_VERIFICATION.json) for audit history.

## Independent executions

All runs used distinct external pytest basetemp directories. Each process record contains its exact command, actual exit code, basetemp, full console log, JUnit path, and SHA-256 values. The final verifier independently recomputed process, console, and JUnit hashes and parsed JUnit totals.

| Selection | Result | Exit |
| --- | ---: | ---: |
| New frozen six-case S5 alias suite | 6 passed | 0 |
| Original frozen S5 suite | 7 passed | 0 |
| Earlier frozen S5 extension | 3 passed | 0 |
| Review-owned equal-object and no-magic-method probes | 2 passed | 0 |
| Generation-drift consumption probe | 1 passed | 0 |
| Successful audit recovery and replay control | 1 passed | 0 |
| S4 completion and unresolved-integration controls | 19 passed | 0 |
| S4 reentrant completion controls | 5 passed | 0 |

The historical alias exploit diagnostic exited **1** because it expects the alias to consume the authentic token. It reached the intended wrong-mode alias presentation, then strict merge validation succeeded and the authentic token successfully reopened recovery. The diagnostic failed at its later assertion that the authentic token should already be spent. This confirms the alias was rejected without consuming the issued object; the nonzero exit is an expected secure-negative result, not a passing acceptance test.

Sol’s recorded broad results independently reparse as S4 **45/45**, S3 **14/14**, S2 **30/30**, and Round 3.6 **61/61**, each with actual exit 0 and matching process/log/JUnit hashes.

## Trust assumptions and remaining status

This finding assumes the installed `StateManager` and controller code, Python runtime and built-ins, `StateLock`/`threading.RLock`, process memory, Git executable and ref permissions, state files, and evidence-key custody are trusted. Arbitrary changes to installed controller code or the runtime, OS compromise, or direct mutation of private manager internals are outside the declared caller API boundary. The registry is in-memory and does not provide durable rollback protection.

The legacy merge/audit selection remains **19 passed, 34 failed of 53**, actual exit 1. Independent JUnit comparison confirms the same 34 failure names as the prior S5 baseline; these are the documented obsolete fixture/API expectations and are not classified as passing. The original S1 control remains **1 passed, 4 failed of 5**, actual exit 1, with the same four rollback/deletion failures as its prior baseline. **S1 remains OPEN and release-blocking.** S1 and F1–F3 were not started in this review. Native Docker, POSIX race/permission, installed SAST identity, live model execution, controller-only ACL, and external durable-authority properties remain NOT VERIFIED.

No production code, prior independent review, frozen test, or manifest was edited. No repository reset, restore, clean, commit, push, merge, rebase, tag, or release was performed.
