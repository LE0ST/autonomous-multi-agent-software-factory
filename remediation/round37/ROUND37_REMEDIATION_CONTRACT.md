# Round 3.7 remediation contract for Astra

## Scope and preservation rules

Keep the transaction-only `StateManager` architecture. Do not restore `save()`, `_save_unlocked()`, or any general snapshot-writing test API. Do not edit any already-frozen Round 3.6 test. Record new adversarial acceptance tests in a Round 3.7 frozen manifest before implementation changes and never edit a test after freezing it; create a versioned replacement if a frozen test is defective.

Preserve the completed properties: explicit immutable B/C/tree/M/context, tree lookup from C, exact B-to-C `update-ref` CAS, controller-side typed behavioral challenges for password-v36, ordered HMAC evidence validation, changed-context rejection, key-loss fail-closed behavior, and SAST tool-error rejection.

## Security defects

### S1 — durable state authority

**Required invariant:** Once a task is initialized, no restoration or deletion of all files writable by the state principal may lower its authoritative generation, erase terminal state, reset budgets, or recreate it as a new task.

**Existing failing counterexamples:**

* `test_paired_state_and_witness_rollback_is_accepted_by_fresh_process`
* `test_deleting_state_and_witness_reinitializes_terminal_task`

**Expected secure behavior:** A fresh process rejects the restored old pair and the deleted pair as rollback/corruption. Recovery requires an explicit controller-owned administrative migration path. The durable authority is authenticated and anchored outside the ACL available to the state writer; protecting only another file in the same mutable directory is insufficient.

**Acceptance criteria:**

1. Freeze both counterexamples as Round 3.7 tests and reproduce them failing before the fix.
2. Restore an older state plus every colocated witness: construction fails closed.
3. Delete state plus every colocated marker: construction fails closed.
4. Repeat from a fresh process with no in-memory generation.
5. Demonstrate controller-only ACLs or an equivalent protected authority on Windows.
6. Add fault injection around snapshot replacement and durable-authority update; every crash state must either recover the latest complete transaction or fail closed.

### S2 — gate-result authority

**Required invariant:** No general caller can create accepted gate evidence by naming a gate or claiming success. Each record must require a non-forgeable result tied to the concrete execution path and current attempt.

**Existing failing counterexample:** `test_private_record_success_can_authorize_merge_without_gates`.

**Expected secure behavior:** Calling an internal/general issuer, traversing FSM states, or constructing a result-like object cannot produce a record. Each concrete gate owns its issuance path and binds the actual result and implementation identity.

**Acceptance criteria:**

1. Freeze the counterexample and reproduce the unauthorized merge before the fix.
2. Remove any issuer accepting an arbitrary gate name or PASS result from a general caller.
3. Attempt direct issuance for each mandatory gate; no evidence is appended.
4. Execute each real gate successfully; exactly one ordered record is appended immediately.
5. A duplicate, reordered, simulated, failed, or exception result cannot append evidence.
6. The full four-gate path still authorizes exact B-to-C CAS.

### S3 — executed implementation identity

**Required invariant:** Evidence must identify the exact backend object and implementation that produced the result. The executing backend cannot be substituted after identity freeze.

**Existing failing counterexample:** `test_backend_can_be_substituted_after_identity_capture`.

**Expected secure behavior:** Backend configuration is immutable for the attempt, or the exact executing backend is re-derived and verified immediately before and after execution. A substituted backend fails before evidence issuance.

**Acceptance criteria:**

1. Freeze the substitution counterexample and reproduce the mismatched signed identity before the fix.
2. Replace the backend after session creation; TESTING rejects and appends no evidence.
3. Mutate relevant backend implementation between freeze and execution; reject.
4. Confirm valid TESTING evidence names the backend that actually executed.
5. Apply the same binding principle to suite, scanner, rule set, audit adapter, and materializer identities.

### S4 — terminal completion authorization

**Required invariant:** `COMPLETED` is reachable only as part of the authorized integration operation after four current authentic gate records and successful exact-ref CAS.

**Existing failing counterexample:** `test_public_status_setter_can_claim_completed_without_merge`.

**Expected secure behavior:** General status setters reject `COMPLETED`. State validation rejects any persisted state/status/history combination claiming completion without the required integration transition and receipt.

**Acceptance criteria:**

1. Freeze the counterexample and reproduce `INIT/COMPLETED` before the fix.
2. General status APIs reject COMPLETED from every state.
3. Direct transaction attempts to create an inconsistent completed snapshot fail validation.
4. A failed CAS cannot produce COMPLETED.
5. A successful four-gate CAS produces one semantically valid completed state.

### S5 — one-shot recovery capability

**Required invariant:** The first call using a recovery capability consumes it regardless of validation, transition, or persistence success.

**Existing failing counterexample:** `test_failed_recovery_attempt_does_not_consume_capability`.

**Expected secure behavior:** After the first failed attempt, reusing the same object always raises the dedicated authorization error. A new capability may be issued only after strict validation succeeds again.

**Acceptance criteria:**

1. Freeze the counterexample and reproduce successful reuse before the fix.
2. Pop or atomically mark the capability used before any fallible recovery validation.
3. Exercise context drift, missing evidence, Git errors, persistence errors, and transition errors; reuse always fails.
4. Confirm capabilities remain generation-, task-, repository-, base-branch-, and recovery-mode-bound.

## Functional and recovery work

### F1 — integration repository coherence

Choose and document one supported model:

* operate on a bare/control repository and leave user worktrees outside the integration primitive; or
* require a clean main worktree and safely synchronize it after CAS without losing operator data.

Acceptance requires frozen tests for dirty tracked files, untracked files, staged files, detached HEAD, CAS failure, and post-CAS synchronization failure. Never discard user changes.

### F2 — audit recovery outcomes

Define state transitions for audit PASS, FAIL, UNCERTAIN, rate limit, tool error, and exception. Every return path must end in a valid resumable, review, terminal, or completed state. Freeze the semantic-FAIL counterexample and verify budget changes and state transition atomically.

### F3 — preserved-worktree policy

Decide whether the worktree is required recovery evidence. If required, missing, dirty, or wrong-HEAD worktrees fail closed. If optional, remove obsolete expectations and prove recovery reconstructs every required input from immutable Git objects. Record this as a policy decision rather than an incidental `exists()` branch.

## Legacy test migrations

The 47 full-suite failures consist of 33 removed `_save_unlocked` fixtures, seven security-acceptance failures, and seven other obsolete fixtures or platform expectations. Preserve production invariants while migrating them.

Build recovery fixtures through public behavior:

1. Create a temporary Git repository with exact B, C, base branch, and task ref.
2. Capture a real `VerificationContext`.
3. Reach BUILDING through public FSM transitions.
4. Execute controller gates with narrow boundary doubles to create authentic signed evidence.
5. For merge recovery, inject failure only at final CAS after four evidence records.
6. For audit recovery, create HUMAN_REVIEW through a real UNCERTAIN audit after three records.
7. Obtain the opaque capability from `authorize_recovery()`.
8. Apply the intended branch, context, evidence, worktree, or policy mutation after authentic setup.

Specific migrations:

* Give manifest tests real base and candidate object IDs so they reach mutation, alias, and race assertions.
* Test incomplete evidence by fault-injecting record loss into otherwise authentic state; do not restore snapshot writers.
* Replace `compute_verification_candidate` tests with `VerificationContext` and explicit C materialization.
* Update merge tests to `execute_fast_forward_merge(repo, B, C, branch)`.
* Use existing mount directories in Docker process mocks.
* Run positive native materialization on POSIX CI and retain Windows fail-closed coverage.
* Split sanitizer crash and review cases into different tasks.
* Insert SPEC_GATE into old FSM transition tests.

Happy-path recovery, exact-SHA integration, and basic terminal rejection already have Round 3.6 equivalents. Retain negative branch drift, context drift, incomplete evidence, dirty/missing worktree, divergence, budgets, retry/rate-limit, secret sanitation, audit fallback, and zero-unrelated-stage coverage.

## Native properties requiring dedicated environments

Do not infer these from boundary doubles:

* live Docker image selection and digest;
* real UID, network, filesystem mounts, and secret exclusion;
* bounded output and cleanup against a Docker daemon;
* container disappearance after timeout and cleanup failure;
* descriptor-relative POSIX materialization under symlink/rename races;
* permissions and immutable output modes on POSIX;
* actual Semgrep/Bandit execution and installed-file identity;
* real logic/security model execution.

Round 3.7 acceptance must label these VERIFIED only when run in the corresponding native environment. Otherwise retain NOT VERIFIED.

## General-purpose verification track

This track is separate from S1 through S5 and F1 through F3:

1. Define a controller-owned registry of trusted behavioral suites for multiple task types.
2. Bind suite selection and oracle version into frozen policy and evidence.
3. Implement authoritative pytest completion when policy requires it.
4. Validate coverage from controller-owned instrumentation rather than candidate claims.
5. Retain post-freeze randomized challenges and controller-side expected answers.
6. Reject unsupported task types explicitly until their trusted suite exists.

Do not describe password-v36 success as general-purpose factory verification.

## Required Round 3.7 final evidence

Round 3.7 is ready for independent review only when:

* every newly frozen adversarial test hash is unchanged;
* all S1-S5 acceptance criteria pass;
* F1-F3 have explicit documented policies and passing tests;
* migrated legacy tests reach their intended assertions;
* the complete security-acceptance and full configured suites are reported without hiding failures;
* all seven production schedules are repeated after the last production change;
* native Docker/POSIX results are clearly separated from doubles;
* production hashes and final on-disk rereads are retained;
* no insecure snapshot-writing compatibility API is restored.
