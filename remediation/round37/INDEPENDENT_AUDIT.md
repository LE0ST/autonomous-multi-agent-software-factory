# Round 3.6 independent diagnostic audit

## Decision

Round 3.6 must not receive a security PASS. It materially improves exact candidate binding, compare-and-swap integration, controller-side behavioral challenges, evidence verification, and transaction-only persistence, but durable state authority and several controller provenance and recovery invariants remain unresolved.

This handoff separates current security defects from functional recovery behavior, legacy fixture migration, unavailable native validation, and broader product scope.

## Confirmed security defects

### S1 — paired state and witness rollback or deletion

The authoritative state and its freshness witness are stored under the same mutable directory. A fresh process accepts an older matching pair. Deleting both makes an initialized terminal task appear new and recreates it as `INIT/RUNNING`.

Threat-model prerequisite: an OS principal, backup/restore actor, or controller-adjacent process able to modify the controller state directory. Candidate code confined to the intended Docker mounts does not have this access. On the audited Windows host, `orchestrator/state` inherited `Modify` for Authenticated Users.

Reproductions:

* `test_paired_state_and_witness_rollback_is_accepted_by_fresh_process`
* `test_deleting_state_and_witness_reinitializes_terminal_task`

The Round 3.6 frozen rollback test changes the state while retaining the later witness. It does not cover restoring or deleting both artifacts.

### S2 — gate evidence can be issued without executing a gate

`VerificationSession._record_success(gate)` accepts a caller-provided gate name and has no unforgeable result from the concrete gate. A controller-process caller can traverse the FSM, issue all four records, pass evidence verification, and authorize the real B-to-C CAS without running the gates.

Threat-model prerequisite: arbitrary Python execution, a malicious plugin, or a faulty privileged integration inside the controller process. Candidate sandbox code alone cannot call this method.

Reproduction: `test_private_record_success_can_authorize_merge_without_gates`.

### S3 — backend identity does not bind the backend object that executes TESTING

The session captures `backend_type` and identities during construction but later invokes mutable `self.backend`. Substituting that object after identity capture allows a different backend to produce a passing result while the signed record names the original backend.

Threat-model prerequisite: controller-process mutation or an unsafe privileged extension. Candidate sandbox code alone cannot replace the object.

Reproduction: `test_backend_can_be_substituted_after_identity_capture`.

### S4 — public status mutation can claim completion without integration

`StateManager.set_execution_status('COMPLETED')` succeeds from `INIT/RUNNING`. No verification context, evidence, integration state, or successful CAS is required.

Threat-model prerequisite: any in-process caller with access to the task's `StateManager`. This forges controller state but does not itself move a Git ref.

Reproduction: `test_public_status_setter_can_claim_completed_without_merge`.

### S5 — a failed recovery attempt does not consume its capability

The capability is removed only around the transaction that follows strict recovery validation. If validation fails first, the same capability remains usable after the invalid condition is reverted.

Threat-model prerequisite: possession of an authentic capability plus the ability to cause and revert a recovery validation failure during the controller process lifetime.

Reproduction: `test_failed_recovery_attempt_does_not_consume_capability`.

## Functional and recovery regressions

### F1 — dirty main repository can be marked completed after ref-only integration

An authentic merge recovery advances the base ref while uncommitted operator content remains. State becomes `AUTO_MERGE/COMPLETED`, but the checked-out worktree and index are not synchronized to the new branch tip.

Reproduction: `test_dirty_main_repo_is_merged_and_left_inconsistent`.

### F2 — audit semantic failure strands a task in an active state

After authorized audit recovery, a semantic FAIL returns false while leaving `LOGIC_AUDIT/RUNNING` and consuming a security replan. The task is not returned to BUILDING, HUMAN_REVIEW, or HALT_HUMAN.

Reproduction: `test_audit_recovery_semantic_fail_strands_running_state`.

### F3 — missing preserved worktree has no explicit policy

Strict recovery validates a worktree only if it exists. Audit recovery and merge can therefore succeed after the preserved worktree is removed. This can be safe when immutable Git objects are authoritative, but it conflicts with existing recovery tests and must be made an explicit contract.

Reproduction: `test_missing_preserved_worktree_does_not_block_audit_recovery`.

## Verified controls that should be preserved

Corrected independent fixtures confirmed:

* changed specification is rejected by authentic merge recovery;
* incomplete signed evidence is rejected by authentic merge recovery;
* manifest path aliases are rejected after using real Git identities;
* native Windows materialization fails closed before creating output;
* manifest materialization data is held in an immutable serialized snapshot;
* exact-SHA integration uses the verified C even after a task ref moves;
* compare-and-swap rejects a concurrent base-ref advance.

The seven retained Round 3.6 schedules also show clean, worktree-mutation, and selection-race paths integrating the frozen C, while changed spec/config/policy and SAST exit 2 halt before integration. Their use of doubles means they do not prove live Docker, POSIX materialization, or real scanner/model execution.

## Security-acceptance failures

The three legacy manifest failures use placeholder identities and stop before their assertions. The two strict-recovery failures invoke a retired no-argument manifest helper and never reach recovery. They require fixture migration rather than dismissal. The terminal-authorization test is rejected earlier by the freshness witness and has equivalent public-transition coverage, although paired rollback remains exploitable. The trusted positive test fails while decoding UTF-8 with Windows cp1252; the frozen hidden-challenge positive test is equivalent for the current password-v36 oracle.

## Product scope

The trusted verifier is currently a secure restricted verifier for the `password-v36` behavior only. Policy fixes `require_pytest` to false, and the controller fails closed when pytest is required or another suite is selected. Supporting arbitrary task semantics, authoritative pytest completion, and coverage is general-purpose factory work. It must be tracked separately so it does not delay or obscure S1 through S5.
