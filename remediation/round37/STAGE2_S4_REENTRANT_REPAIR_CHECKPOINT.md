# Round 3.7 Stage 2 — S4 reentrant completion repair checkpoint

**Scope:** S4 engineering repair and independent-review handoff. S4 is not self-approved. S5 was not started. S1 remains OPEN and release-blocking. No overall Round 3.7 security PASS is claimed.

## Preservation and reproduced defect

Before production changes, `stage2_s4_reentrant_repair/PRE_EDIT_VERIFICATION.json` reread and matched all **15/15** reviewed production hashes, **7/7** earlier frozen manifest hashes, and **21/21** listed frozen source hashes. It also hashed all **34** artifacts in the two independent Luna review directories. The reviews, earlier evidence, earlier frozen tests, and manifests were not modified. The existing dirty worktree was left in place; no reset, restore, clean, commit, push, or release was performed.

On unchanged production, the independent reentrant diagnostic exited **0** with its attack assertions satisfied (`second_bypass_before-*.process.json` and console). Four current authentic gates had run. The third instance-level `VerificationSession.verify_evidence` call entered after signed durable pending intent and before the merge helper. It constructed a correctly signed receipt using the callable key accessor, set completion, called `_persist()` directly, and then raised. `_persist()` accepted it because `_integrate()` was an ancestor frame. The base ref remained the original B; the helper and exact CAS had not executed. A fresh manager loaded `COMPLETED` with a receipt. The prior Luna review's probe, process, console, and hash records were located and preserved.

The exact independent records are `independent_review_stage2_s4_repair/probe_reentrant_completion.py` (SHA-256 `b537f33b3a495b95fecc8fe65483e0b9f9cb4c5cd098d881ce5afdd19918b46f`), `reentrant_callback_counterexample-a673088539a14420a40e9ebe6ed477a2.console.txt` (SHA-256 `0b7fba8c4077627008c2787efa591332dbfaafa17e2e7f94529547170117989e`), its actual exit-0 process entry in `FOCUSED_REPLAY_RESULTS.json` (SHA-256 `7878eb5feaabd4b7d2673ae962a8ddd22cae62eee101b070dd15b15bc0977d0c`), and `ARTIFACT_SHA256.txt`. `PRESERVATION_VERIFICATION.json` independently checks the earlier production and frozen records.

The original first Luna route used a mutable authority slot and signer. The first repair removed those, but authorized any direct persistence call with `_integrate()` anywhere in its stack. The second bypass shows why an ancestor frame is not an authorization boundary.

## Frozen acceptance before edits

`tests/security_acceptance/test_round37_s4_reentrant_counterexample.py` and its separate `ROUND37_S4_REENTRANT_FROZEN_SHA256.txt` were frozen before the first production edit. Its four cases each reached the intended boundary: the third evidence callback after pending intent, a callback replacing the merge helper, the fourth evidence callback after real CAS, and a helper that moved the ref unconditionally while claiming success. The pre-edit run was **4 failed**, exit **1**. The completed repair passes all four.

Investigation exposed a second mutable approval reference in the first draft of this repair. A versioned `test_round37_s4_reentrant_counterexample_v2.py` and separate manifest were frozen before the next production edit. It replaces both the helper and the writable reference, moves the ref without conditional B-to-C CAS, and observes unauthorized completion on the intermediate code (**1 failed**, exit **1**). The final code passes the case. Neither frozen file or manifest was edited after freezing.

| Frozen artifact | SHA-256 |
| --- | --- |
| `test_round37_s4_reentrant_counterexample.py` | `14ce34c07c44f7fc48065b3b0a89ccbbde26114d0e7ed415d58c4401c307ea1f` |
| `ROUND37_S4_REENTRANT_FROZEN_SHA256.txt` | `5b3df785a37040c42f2509d95f4d87ffad56e1589d20b7ae9520c3f38215a645` |
| `test_round37_s4_reentrant_counterexample_v2.py` | `228a379ef1f6d7a1abe55b0888882295008bda49f1d584682580e38127a98da9` |
| `ROUND37_S4_REENTRANT_V2_FROZEN_SHA256.txt` | `d1f1b480cfc9380c1e1193086b213d2d148553aa5ab9a153a7a36c360f4fc14b` |

## Integration persistence design

Only `orchestrator/state_manager.py` changed among the 15 production files: reviewed SHA-256 `8cf8c8ca2ce60e7485b94589c24d1be9fe89aff4a54daebc0be7f2dbfed19cb6` to final SHA-256 `b4fac6231e7186037695a8e3481590a985d436be021ec70fec7d689a7984aab4`. The other 14 values and final on-disk rereads are in `FINAL_RESULTS.json`.

`StateManager._persist()` compares the entire proposed integration-sensitive transition with the durable snapshot. It accepts only the exact pending-intent addition, pending-intent rollback, or one completion history row and receipt, each with generation advanced by one. The immediate caller for intent and rollback must be installed `_integrate()` code. Completion passes through a separate `_persist_completion()` call site directly beneath `_integrate()`; arbitrary callbacks cannot use that call site merely because integration is higher on the stack. This is code provenance plus a complete state delta, not a mutable capability or a signing API. General transactions still reject pending/receipt/completion changes.

The selected C and candidate-ref observation retain distinct roles. C remains frozen in `VerificationContext` for all gates and the exact B-to-C CAS. The observation detects task-ref drift after session creation; a capture-time selection race remains allowed. Intent is durable before Git execution. The installed merge helper uses `git update-ref <base> C B`. Before receipt creation, `_integrate()` checks the helper's loaded code and source against fixed installed-build digests, requires reported success, rereads the actual base ref as C and the candidate ref as its frozen observation, and revalidates evidence. The completion persistence boundary rereads the base ref C and validates the signed state. The old writable helper-identity reference remains inert solely so the versioned frozen attack can prove that changing it has no effect.

An unsuccessful CAS with B still at B clears intent and advances generation. An exception after intent persistence leaves a nonterminal pending state. A successful CAS followed by completion-persistence failure leaves C with nonterminal pending intent; ordinary retry and recovery reject, and reconciliation is read-only. Git and state persistence remain separate transactions.

## Reentrant execution inventory

Before intent, the session evidence and current-context calls, Git ref reads, transition transaction, key read, time and nonce generation can invoke Python code. None has completion persistence authority. After intent and before CAS, the candidate-ref read and third evidence call can invoke caller-controlled code; a direct `_persist()` call from that code is rejected. During CAS, the helper and its subprocess boundary may invoke or be replaced by caller code; a substituted success is rejected by fixed implementation identity, while the actual ref is also checked. On failed CAS, ref reread and rollback execute under the state lock; rollback requires B and an exact durable-state delta. After CAS, ref rereads and the fourth evidence call may invoke code; direct persistence is rejected. The completion call site itself accepts only the one allowed delta. Exception handlers restore in-memory state, while already durable pending intent remains for fail-closed reconciliation.

## Trust assumption and remaining architectural limit

These controls are valid under the existing declared **trusted installed controller code and in-process runtime** assumption. They distinguish an allowed session-instance callback from installed `_integrate()` and `_persist_completion()` code. They do **not** enforce the absolute S4 invariant against a caller who can change trusted class code, replace the Python runtime or subprocess implementation, directly write state and witness files, or read the HMAC key as the same OS principal. Fixed code digests are build checks, not an OS isolation boundary. A ref at C and a signed `cas` string alone are not proof of an actual B-to-C CAS.

If those actions are inside the intended general-caller threat model, the current architecture cannot provide the requested guarantee. The minimum real separation is an isolated controller-owned integration worker with its own OS principal and exclusive custody of the evidence key, state/witness writer, and Git base-ref mutation permission. The worker must accept only a data request, independently validate the frozen context and four gate records, persist intent, execute `git update-ref C B` itself, check the exit and ref, then sign and persist completion. No caller-controlled Python callback may execute in that worker between intent and completion. S1 additionally needs an authority anchor outside the state writer's ACL.

## Verification and status

Complete per-selection commands, unique external pytest base directories, JUnit XML, console logs, actual process exit codes, and hashes are indexed in `stage2_s4_reentrant_repair/FINAL_RESULTS.json`. The unchanged original second Luna script is retained and rerun: after repair its callback reaches pending intent and gets `TerminalStateError`; its historical “attack accepted” assertion then exits **1** with `KeyError`. The new frozen suite verifies rejection with exit **0** and asserts that the callback, helper, and ref-update paths were actually reached.

The final schedule includes the two new frozen suites, the prior five-case S4 counterexample, original S4, S4 extension, combined S3 and S2, Round 3.6, completion/recovery legacy regressions, and original S1 control. Native Docker, POSIX materialization, live scanners/models, and Windows controller-only ACL properties were not inferred from boundary doubles.

| Final selection | Result | Actual process exit |
| --- | ---: | ---: |
| New frozen reentrant suite | 4 passed | 0 |
| Versioned helper identity counterexample | 1 passed | 0 |
| Previous S4 counterexample | 5 passed | 0 |
| Original S4 | 17 passed | 0 |
| S4 extension | 18 passed | 0 |
| Combined S3 | 14 passed | 0 |
| Combined S2 | 30 passed | 0 |
| Round 3.6 frozen | 61 passed | 0 |
| Completion/recovery legacy | 19 passed, 34 failed | 1 |
| Original S1 control | 1 passed, 4 failed | 1 |

The genuine four-gate exact B-to-C CAS positive is included in original S4 and completed with one valid receipt and history row. The S4 extension confirmed candidate-ref drift rejection, post-CAS nonterminal persistence failure and read-only reconciliation. The Round 3.6 61/61 result includes the frozen selection race with immutable selected C. The new negative tests assert that their post-intent, helper, post-CAS and unconditional ref-update paths were reached; no AttributeError or early fixture rejection is counted as an adversarial pass.

The 34 legacy failures retain the prior classification: 30 removed `_save_unlocked` fixture uses, one obsolete candidate-computation API, one old merge call signature, one FSM path missing `SPEC_GATE`, and one expectation that the public status setter accepts `COMPLETED`. S1's four failures remain the paired rollback and delete-all fresh-process counterexamples. S4 remains an engineering repair for independent review under the declared installed-code trust model; it is not self-approved and S5 remains untouched.
