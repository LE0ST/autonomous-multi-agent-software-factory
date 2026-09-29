# Round 3.7 — Stage 1 checkpoint

Stage 1's requested test-and-freeze work is complete. **Production remains
vulnerable; no security PASS or independent approval is claimed.** No production
remediation, F1–F3 implementation, legacy-test migration or general-purpose
verifier expansion was started.

Read the original five handoff documents, then
`stage1/SECURITY_INVARIANTS.md`, `stage1/STAGE1_RESULTS.json` and
`stage1/REPLAY.md`. The independent diagnostics and all Round 3.6 frozen files
remain unchanged.

## Verified baseline and preservation

All nine original handoff artifact hashes, both diagnostic source hashes, all
eight Round 3.6 frozen test hashes, the auditor's Round 3.6 manifest hash, and
all 15 recorded Round 3.6 production hashes matched. The before/after inventory
in `stage1/PREEXISTING_SHA256.txt` contains 170 existing tracked or unignored
files; every entry still matches. Existing user modifications and the preexisting
deletion of `tests/test_e2e_dry_run.py` were preserved. Ignored runtime/secret
files are not part of this inventory.

The **exact** `REPRODUCTION.md` baseline command completed with exit code 0:
**16 passed in 198.82s**. These are diagnostic PASS results, including reproduced
vulnerabilities. See `stage1/BASELINE_REPRODUCTION.md`.

## Secure acceptance and genuine FAIL-before

Two completed acceptance invocations exercised 50 cases on the unchanged
vulnerable implementation. The first reported **29 failed, 16 passed in 534.98s**;
the supplementary S3 run reported **2 failed, 3 passed in 89.60s**. Both returned
exit code 1. Combined: **31 intended security assertion failures, 19 passing
controls, 0 errors, 0 skips, 0 xfails**. All failures reached the intended secure
assertion, rather than setup, import or environment failures. Both XML reports
retain the assertion messages. All 50 cases also collect under the repository's
default import mode; all eight new Python files parse successfully.

| Invariant | Genuine FAIL-before | Passing controls | Frozen |
| --- | ---: | ---: | --- |
| S1 durable state authority | 4 | 1 | All 5 cases |
| S2 concrete gate-result authority | 5 | 6 | All 11 cases |
| S3 executed implementation identity | 5 | 5 | All 10 cases across two files |
| S4 completion authorization | 13 | 4 | All 17 cases |
| S5 one-shot recovery capability | 4 | 3 | All 7 cases |

Exact failing cases, using filenames below `tests/security_acceptance/round37/`:

- `test_s1_durable_authority.py`: both `test_restoring_all_colocated_files_is_rejected_by_fresh_process` and `test_deleting_all_colocated_files_is_rejected_by_fresh_process`, each with `[spent-budget]` and `[terminal]`. Separate Python processes accepted generation 0, INIT/RUNNING and worker count 0 after each attack.
- `test_s2_gate_authority.py`: `test_direct_issuer_cannot_append_for_any_mandatory_gate` for `[DIFF_GATE]`, `[TESTING]`, `[SAST]`, `[LOGIC_AUDIT]`; and `test_issuer_only_fsm_traversal_cannot_authorize_real_cas`. The latter executed zero gates, accepted all four fabricated signed records and moved the real temporary base ref from B to C.
- `test_s3_executed_identity.py`: `test_backend_substitution_is_rejected_without_testing_evidence` for `[different-class]`, `[same-class-instance]`, `[instance-method]`. Each replacement executed once and appended TESTING evidence. The different-class record named the nonexecuting ClaimedBackend.
- `test_s3_implementation_bindings.py`: `test_changed_gate_implementation_cannot_append_evidence[audit-adapter]` and `[materializer]`. Both replacement implementations executed and appended evidence.
- `test_s4_completion_authority.py`: `test_general_status_setter_rejects_completed_from_every_state` for `[INIT]`, `[SPEC_DESIGN]`, `[SPEC_GATE]`, `[BUILDING]`, `[DIFF_GATE]`, `[TESTING]`, `[TRIAGING]`, `[SAST_SCAN]`, `[SAST_FILTER]`, `[LOGIC_AUDIT]`, `[AUTO_MERGE]`; and `test_direct_transaction_cannot_persist_completion_without_integration[INIT]` / `[AUTO_MERGE]`. Each persisted COMPLETED with zero evidence.
- `test_s5_recovery_consumption.py`: `test_failed_first_recovery_use_consumes_capability` for `[context-drift]`, `[missing-evidence-read]`, `[git-error]`, `[wrong-mode]`. After restoration and successful strict revalidation, the same capability reopened AUTO_MERGE/RUNNING.

The passing S5 persistence-error and transition-error cases are **controls, not
FAIL-before evidence**: the existing transaction-finally path already consumes
those capabilities. The successful-first-use control also passes. The complete
per-node list, including all passing controls, is in `stage1/STAGE1_RESULTS.json`.

## Frozen files and filename-associated SHA-256

The immutable acceptance manifest is
`tests/security_acceptance/ROUND37_FROZEN_SHA256.txt`. Every listed file was
executed or imported at its current bytes before freezing. No frozen acceptance
file was edited afterward. The external `LocalBoundary`/`GOOD` dependency remains
protected by the original Round 3.6 manifest.

```text
b3fc4dcdf5dec08994033164f172c7f5dff2aef0c3837dc09b613061b20c770f  tests/security_acceptance/round37/__init__.py
39b8c2a25bd3af12c57130eac76b97ead11b61b352b0dc6f54ce961dd5264581  tests/security_acceptance/round37/_support.py
0822bd5982c9aca99d84eebce18e14f5ac7223f00a4963980698024fd3ac55f3  tests/security_acceptance/round37/test_s1_durable_authority.py
789960c6ae95e81f7f1e3ac8f25b58430910bf215f21b144e2434737358dcb70  tests/security_acceptance/round37/test_s2_gate_authority.py
6db4011e969a6af15326e367e82ccb0f7f33323c3a119815328a3cd5ec3c563d  tests/security_acceptance/round37/test_s3_executed_identity.py
9f576cfe91fec45f120aed026381da4fb25abe87b74d14c2935cc0f73a8274a9  tests/security_acceptance/round37/test_s3_implementation_bindings.py
1ad25b164e84d8956f4a3758ab91c36ae68de678357197a739511c958b834113  tests/security_acceptance/round37/test_s4_completion_authority.py
cd52182465fdcbb836ac930f3b191b0d7b70642d57bbc24e99a845171d1de13f  tests/security_acceptance/round37/test_s5_recovery_consumption.py
```

The additional `stage1/STAGE1_ARTIFACTS_SHA256.txt` binds this checkpoint, the
acceptance manifest, reports, preservation inventory and supporting Stage 1
documents. It does not replace or modify the auditor's original artifact manifest.

## Next implementation session: remaining work

No core S1–S5 counterexample still needs Stage 1 FAIL-before evidence or freezing.
All production fixes remain pending. This test set is not a claim that every
final contract criterion has already been exhaustively encoded or verified.
Before modifying the corresponding production boundary, add and freeze any
additional cases below that can be exercised against the vulnerable baseline;
do not retrofit the already-frozen tests.

1. **S1:** design authenticated durable authority outside the state writer's
   effective ACL, with explicit administrative migration/recovery policy. Add
   native principal-separation/ACL evidence and fault injection around snapshot
   replacement and the selected durable-authority update, including crash states
   and restart recovery. The existing ACL read confirms inherited Authenticated
   Users Modify, not a secure deployment. State-file replay/deletion tests alone
   cannot establish an external anchor's protection or power-loss durability.
2. **S2:** remove general gate-name/PASS issuance authority and bind issuance to
   the concrete successful execution and current attempt. Extend frozen coverage
   for caller-constructed result objects, duplicate results for every gate, and
   failed/exception results for every gate. Preserve immediate ordered issuance
   and genuine four-gate exact-C integration. Do not replace actual gate execution
   with test-authored signatures or restore generic evidence APIs.
3. **S3:** freeze or verify the exact executing backend and all relevant loaded
   implementation inputs. Close backend-instance/method, audit-adapter and
   materializer substitution, retaining the existing suite/scanner/rule checks.
   Add mutation-during-execution/post-execution checks and any receipt fields
   needed to establish object/implementation identity. Doubles do not establish
   live image, installed scanner or model provenance.
4. **S4:** reserve completion for authorized integration after successful exact
   CAS and validate persisted completion/history against its integration receipt.
   Add receipt tamper/replay and a forged completion transaction with four valid
   gate records but no successful CAS. Keep failed-CAS and successful-once
   controls. Do not use generic status setters as completion authority.
5. **S5:** consume the capability atomically before fallible recovery work,
   retaining generation/task/repository/base-branch/mode binding and atomic
   transition validation. Extend cross-task/repository/branch/generation and
   audit-mode coverage, plus concurrent-use/crash cases as appropriate. Do not
   accidentally remove terminal transaction authorization while moving the pop.

Preserve transaction-only mutation and immutable B/C/tree/M/context; no `save()`,
`_save_unlocked()`, caller-selected evidence or symbolic candidate rediscovery.
Fix defective frozen tests only by an explicitly documented versioned replacement
while preserving the original file and hash.

F1–F3 policies, legacy migrations, all seven production schedules, complete
security/full-suite runs and final independent audit remain for later authorized
stages. They were not rerun or implemented here. Live Docker, POSIX materialization,
native durable-authority protection/crash behavior, real scanners and real models
remain **NOT VERIFIED**. No commit, push, merge, tag, release or self-approval was
performed on the main repository. The only Git commits/CAS operations were in
the disposable test repositories required by the reproductions.
