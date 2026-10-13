# Independent review: second S4 counterexample repair

## Decision

**A. S4 satisfies its declared trusted-installed-controller boundary, with explicit remaining assumptions.** I found no reproducible completion bypass through the general `StateManager` operations, caller-controlled session callbacks, or instance-level substitutions exercised here. The reviewed invariant is that `COMPLETED` can be durably written only through the installed integration operation after four authentic current gate records and a successful exact-ref B-to-C update.

This is an S4 decision only. **S1 remains OPEN and release-blocking. No overall Round 3.7 security PASS is claimed.** S5, F1-F3, and S1 implementation were not started.

## Scope and preservation

I read the Round 3.7 contract and S4 checkpoint, both earlier independent reviews, Sol's final and pre-edit records, the final `StateManager`, `VerificationSession`, and merge-helper code, both new frozen tests and manifests, and the earlier frozen S4 acceptance tests.

Independent rereads matched all **15/15 final production hashes**, **9/9 frozen manifests**, and **23/23 frozen source entries**. All **34** recorded artifacts from the two earlier Luna review directories still match. Sol's 12 final process records, their complete console logs, JUnit files where applicable, actual process exit codes, and recorded artifact hashes all recompute successfully. Details and per-file hashes are in [EVIDENCE_VERIFICATION.json](EVIDENCE_VERIFICATION.json).

## Persistence authority and reentrancy

`_transaction()` rejects changes to pending intent, receipt, or completion. For an integration-sensitive `_persist()` call, the implementation requires the immediate caller to be the installed `_integrate()` code for intent/rollback, or the installed `_persist_completion()` code called directly by `_integrate()` for completion. `_persist_completion()` itself checks its immediate caller. The completion call uses `StateManager._persist_completion(self)` explicitly, so replacing that method on the manager instance does not replace the privileged call site.

Before writing, `_persist()` compares the complete candidate snapshot with a copy of the durable snapshot plus the one permitted integration delta and generation increment. The only accepted completion delta clears the durable pending intent, adds one completion history row, adds one receipt, and changes status to `COMPLETED`. Other callback-owned changes in that write are rejected. The state validator then checks the receipt, context, four ordered HMAC records, and history digest. This comparison also prevents an in-memory callback mutation from being carried into the subsequent authorized write.

I independently ran the first callback-authority frozen suite (**5 passed, exit 0**) and second reentrant suite (**4 passed, exit 0**). Their evidence callback cases reach the pre-CAS and post-CAS hooks; direct persistence is rejected and a fresh manager sees nonterminal pending intent with no receipt. Their helper callback case also reaches the hook. The helper-identity variant passes (**1 passed, exit 0**). The historical second-Luna diagnostic's exit 1 is not counted as proof; its obsolete success assertion fails after rejection. The fresh frozen suites themselves reach and assert the relevant boundaries.

I added a two-case probe for manager-instance overrides. Replacing `_persist` from the caller callback causes the write attempt to fail closed after real CAS, leaving C with durable nonterminal pending intent. Replacing the instance `_persist_completion` does not alter the privileged path because `_integrate()` calls the class implementation explicitly; normal exact-CAS completion succeeds. The corrected probe passes **2/2, exit 0**. An initial probe expected the instance override to run and failed that incorrect expectation; the initial run and its probe expectation are documented in [EXPLORATORY_PROBE_HISTORY.json](EXPLORATORY_PROBE_HISTORY.json), alongside the corrected run.

## Git CAS provenance

The merge function imported by `_integrate()` is checked against fixed installed-build code and source digests. A replacement helper that reports success without changing the base ref is rejected; the independent replay passes (**1 test, exit 0**). A substituted helper that unconditionally moves the ref to C is also rejected by helper identity. The frozen case verifies the replacement ran and moved the ref, while fresh state remains pending and nonterminal. The moved ref cannot be undone safely from this state: **this rejected helper path leaves an unresolved integration with the base ref at C and requires operator reconciliation.**

The checkpoint describes the trust assumption for this check: installed controller code, the in-process runtime and subprocess implementation remain trusted. Function/source digests plus a ref reread do not independently prove that Git performed the exact B-to-C CAS. In particular, a ref at C and a signed `cas` label are not proof. If arbitrary mutation of controller module globals, the helper's runtime dependencies, the Python runtime, or subprocess execution is included in the attacker model, this Python-process design cannot prove CAS provenance; an isolated controller-owned worker must perform and attest the CAS. That broader runtime/code compromise is outside the declared boundary, while the caller-controlled session callbacks and ordinary manager operations tested here remain inside it.

## Interruption and selected-C behavior

Intent is persisted before the helper can execute Git. A false helper result does not complete; intent is cleared only if a fresh base-ref read proves B is unchanged. Exceptions and uncertain ref reads leave pending intent in place. After exact CAS, a persistence failure also leaves nonterminal pending intent and no receipt; the focused replay passes (**1 test, exit 0**). Legitimate four-gate integration completes successfully (**1 test, exit 0**), and the full original S4 suite passes (**17/17, exit 0**).

Candidate-ref drift is rejected (**1 test, exit 0**). The Round 3.6 selected-C capture race passes (**1 test, exit 0**): immutable C remains the gate/materialization/CAS target, while the captured candidate-ref observation serves as a separate drift check.

## Independent replay evidence

Every fresh pytest selection used a distinct external `--basetemp`. Full console logs, JUnit, actual exit codes, and SHA-256 values are indexed in [INDEPENDENT_REPLAY_RESULTS.json](INDEPENDENT_REPLAY_RESULTS.json). The manager substitution probe's initial failed expectation is separately recorded in that file's sibling process evidence; it is not classified as a product failure.

Sol's broader final results also verify: original S4 **17/17** and extension **18/18**; reentrant and helper counterexamples **4/4** and **1/1**; previous S4 counterexample **5/5**; Round 3.6 **61/61**; S2 **30/30**; and S3 **14/14**, all with actual exit 0. The completion/recovery legacy selection reports **19 passed, 34 failed**, exit 1. The S1 selection reports **1 passed, 4 failed**, exit 1. Those S1 failures remain release-blocking; the S4 decision does not change them.

## Assumptions and limits

This conclusion assumes trusted installed class code, Python runtime and relevant module globals, subprocess implementation, HMAC key custody, state/witness files, and Git permissions. It does not claim security against arbitrary controller-memory or class-code modification, key theft, direct state-file tampering, or operating-system compromise. The state/witness pair is not an external rollback anchor. Native Docker, POSIX race properties, live scanners/models, and controller-only Windows ACL behavior were not verified by this S4 review.
