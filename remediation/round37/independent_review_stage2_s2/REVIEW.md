# Independent security review: Round 3.7 Stage 2, S2 gate-result authority

**Reviewer:** Antigravity (independent, separate conversation from Sol's implementation session)
**Review date:** 2026-09-25T17:27 UTC
**Decision:** **S2 acceptance GRANTED within the declared trust boundary.** The original
`_record_success` direct-issuer bypass is closed. No counterexample survives against the
in-process controller threat model. **S1 remains OPEN and release-blocking.** No overall
Round 3.7 security PASS is granted or implied.

This review changed only files in `remediation/round37/independent_review_stage2_s2/`.
No production code, tests, existing manifests, checkpoints, or Git history was modified.

---

## 1. Source hash verification

All frozen manifests and production files were independently re-read from disk and hashed
with SHA-256. Every entry matches the values recorded in Sol's `RESULTS.json` and
`STAGE2_S2_CHECKPOINT.md`. Exact values are in `source-verification.json`.

| File | SHA-256 (first 16 hex) | Match |
|---|---|---|
| `ROUND36_FROZEN_SHA256.txt` | `c6f065ac5eb704f4…` | ✓ |
| `ROUND37_FROZEN_SHA256.txt` | `a2d0ae027d718c51…` | ✓ |
| `ROUND37_S1_EXTENSION_FROZEN_SHA256.txt` | `231d28d16c28b014…` | ✓ |
| `ROUND37_S2_EXTENSION_FROZEN_SHA256.txt` | `27efe8bd5e0dfbfc…` | ✓ |
| `orchestrator/gate_controller.py` (current) | `5739f6449d1cf6ac…` | ✓ |
| `orchestrator/state_manager.py` | `c0c6d293ae235b8b…` | ✓ |
| `orchestrator/evidence_store.py` | `fe1f9ae7fc9d2e36…` | ✓ |
| `orchestrator/verification_context.py` | `dd0077c9b9494d1e…` | ✓ |
| `orchestrator/logic_audit.py` | `88a1217931345f41…` | ✓ |
| `test_round37_s2_extension.py` | `26feb774b7d7be8c…` | ✓ |
| `test_s2_gate_authority.py` | `789960c6ae95e81f…` | ✓ |

All 8 Round 3.6 frozen source files, all 8 Round 3.7 frozen source files, and the S1
extension source also matched their manifests.

Sol's own `summarize_results.py` script was run independently and reported:
`Wrote RESULTS.json; all frozen and other production hashes match.`

The `FREEZE.json` records `production_sha256: 877ae73d…` (the pre-edit gate_controller),
confirming the extension test was frozen before the production change.

---

## 2. Exact S2 production delta

The only production file changed by S2 is `orchestrator/gate_controller.py`:
- **Pre-S1:** `877ae73d527eff51…` (original vulnerable version)  
- **Post-S1 / pre-S2:** `877ae73d527eff51…` (unchanged by S1)
- **Post-S2 (current):** `5739f6449d1cf6ac…`

All 14 other production files have hashes unchanged from the S1 checkpoint.
`state_manager.py`, `evidence_store.py`, `verification_context.py`, `logic_audit.py`,
and all scripts remain at their S1-post values.

An AST-level inspection confirms:
- `_record_success` does **not exist** anywhere in the current `gate_controller.py` source.
- `issue_gate_evidence` on `StateManager` raises `RuntimeError` explicitly (line 446–447).
- No other module-level function or class method was found that accepts an arbitrary gate
  name and produces a signed record.

---

## 3. Production path tracing: every route that can sign gate evidence

The only path that appends a signed HMAC record to `gate_evidence` is:

```
VerificationSession._run_gate(gate)          [gate_controller.py L135–218]
  └─ concrete execution (validate_diff / TestSupervisor.verify_candidate /
                         run_sast / execute_logic_security_audit)
  └─ eligibility check (type-strict boolean/int predicates, NOT simulate)
  └─ result_body / result_hash computed from actual result tuple
  └─ self.sm._lock acquired
  └─ self._current() re-checked inside lock
  └─ append() closure: sequence/order/attempt/context checked inside transaction
  └─ HMAC signed with self._key.read() inside transaction
  └─ sm._transaction(append) persists
```

Public callers of `_run_gate`:
- `run_diff()` → `_run_gate('DIFF_GATE')`
- `run_testing()` → `_run_gate('TESTING')`
- `run_sast()` → `_run_gate('SAST')`
- `run_audit(simulate=False)` → `_run_gate('LOGIC_AUDIT', simulate=False)`

No other path through `VerificationSession`, `StateManager.verify_all_evidence`,
`StateManager._recovery_session`, or `StateManager.authorize_recovery` appends evidence.
`verify_all_evidence` and `authorize_recovery` both construct `VerificationSession(resume=True)`
and call `verify_evidence()` which is read-only. The `_recover` method transitions FSM state
but does not touch `gate_evidence`.

---

## 4. Elimination of the original direct-issuer bypass

**Before the fix:** `_record_success(gate)` accepted any gate name and any caller.
The `test_issuer_only_fsm_traversal_cannot_authorize_real_cas` case confirmed that calling
`_record_success` four times (after FSM traversal) produced four valid HMAC records and
completed a real B→C CAS with zero concrete gate executions.

**After the fix:** `_record_success` is absent from the production source. The AST walk
found no method by that name in `VerificationSession` or anywhere in the file. The test
`test_direct_issuer_cannot_append_for_any_mandatory_gate[DIFF_GATE/TESTING/SAST/LOGIC_AUDIT]`
exercises `getattr(session, '_record_success', None)` — it returns `None`, so the issuer
path is a no-op and no evidence is appended.

The issuer-only CAS test confirms zero gate calls and that `verify_evidence()` returns `False`,
`merge()` raises `RuntimeError`, and the base ref is unchanged.

**The bypass is closed.** A caller cannot name a gate and receive a valid record.

---

## 5. `_run_gate` dispatcher and eligibility conditions

### DIFF_GATE (L141–148)
```python
eligible = (type(result[0]) is bool and result[0]
    and isinstance(result[1], dict) and result[1].get('status') == 'PASS')
```
- `type(result[0]) is bool` (not `isinstance`) prevents `1` or truthy int from qualifying.
- `result[1]` must be a dict with `status == 'PASS'`.
- A false boolean, any non-dict, or missing/wrong status is ineligible.

### TESTING (L149–162)
```python
eligible = (type(result[0]) is bool and result[0]
    and type(result[3]) is int and result[3] == 0
    and isinstance(result[4], dict)
    and result[4].get('trusted_verifier_result') == 'PASS')
```
- Both `result[0]` (bool True) and `result[3]` (int 0) are type-strict.
- The result tuple must have at least 5 elements with the right types at exact positions.

### SAST (L163–172)
```python
eligible = (type(result[0]) is int and result[0] == 0
    and isinstance(result[1], dict) and result[1].get('results') == []
    and not result[1].get('error'))
```
- `result[0]` must be `int` 0 (not `bool False`), enforcing a distinct type from DIFF/TESTING/LOGIC_AUDIT.
- `results` must be the empty list exactly — not any falsy or non-empty list.
- `error` key must be absent or falsy.

### LOGIC_AUDIT (L173–190)
```python
eligible = (type(result[0]) is bool and result[0]
    and result[1] is not None and result[1].status == 'PASS'
    and isinstance(result[2], dict) and not simulate)
if result[0] and simulate:
    raise RuntimeError('Simulation cannot authorize integration')
```
- `simulate=True` is doubly blocked: `not simulate` keeps `eligible=False`, AND the
  explicit check raises `RuntimeError` before returning.
- A simulated PASS result cannot reach the signing transaction under any path.
- `result[1].status` requires the `LogicAuditOutput` object to have `status='PASS'`;
  `FAIL`, `UNCERTAIN`, `UNAVAILABLE`, and `SIMULATED` are all rejected.

**Assessment:** All four predicates are robust to type coercion (`True==1`, `False==0`).
No observed predicate can be satisfied by a wrong-typed or wrong-shaped result. The SAST
`int 0` vs DIFF/TESTING/LOGIC_AUDIT `bool True` distinction is intentional and correct
given each gate's actual return convention.

---

## 6. Adversarial attack surface

### 6.1 Caller-supplied PASS object
No longer possible. `_run_gate` builds `result` from the concrete gate call only; no
parameter accepts a pre-built result. The `test_caller_supplied_pass_object_cannot_mint_evidence`
extension test exercises `getattr(session, '_record_success', None)` with a crafted dict
detail — the method is `None`, so no evidence is appended. **Closed.**

### 6.2 Replay of an old execution result
An eligible result is captured inside `_run_gate`'s local scope at L196. There is no
public API to re-submit a previously captured result to the signing path. The
`test_replayed_success_cannot_authorize_the_next_gate` test calls `_record_success`
(absent) with a reused record — no evidence is appended. **Closed.**

### 6.3 Gate substitution (wrong gate's result for another gate)
The `append()` closure checks `GATES[sequence] != gate` at L204. Sequence is derived
from the current length of `gate_evidence`. If DIFF_GATE's result were somehow submitted
for TESTING's slot, `gate != GATES[1]` would raise `RuntimeError` inside the transaction.
The `test_reordered_gate_appends_no_evidence` suite covers all four positions.
**Closed within the signing transaction.**

### 6.4 Duplicate gate
The check `sequence >= len(GATES) or GATES[sequence] != gate` at L204 rejects a duplicate:
after DIFF_GATE is at index 0, GATES[1]='TESTING' ≠ 'DIFF_GATE', so the second DIFF_GATE
call raises. The test covers the duplicate case for all four gates. **Closed.**

### 6.5 Out-of-order execution
`_before(gate)` at L129–133 calls `verify_evidence(required=prior)` where `prior` is the
correct prefix. Running TESTING before DIFF_GATE means `prior = ('DIFF_GATE',)` and
`verify_evidence` returns `False` (zero records), causing `RuntimeError`. **Closed.**

### 6.6 Simulation bypass
LOGIC_AUDIT with `simulate=True` is doubly blocked at L186 and L187–188. No other gate
accepts a `simulate` parameter. `run_audit(simulate=True)` in the frozen test raises
`RuntimeError('Simulation cannot authorize integration')` before the eligibility block.
**Closed.**

### 6.7 Stale context (spec drift, candidate drift)
After gate execution, `_current()` is called inside the lock at L199. This re-reads and
re-validates B, C, tree, M, spec, config, policy, attempt, key identity, and all
implementation identities. If the spec file is mutated between execution and signing,
`context.verify_current()` returns `False` and `RuntimeError('Context changed after
verification candidate freeze - FAIL CLOSED')` is raised. The
`test_real_success_becomes_ineligible_if_spec_changes_before_signing` test covers all four
gates. The `test_candidate_identity_change_after_real_diff_cannot_sign` test covers C
substitution between execution and signing. **Closed.**

### 6.8 Fabricated HMAC record (adversarial signing)
To produce a valid signed record without running a gate, an adversary needs:
1. The raw 32-byte evidence key from `EvidenceKey.read()`.
2. The exact current context dict, attempt token, and implementation identities.
3. An accurate generation value from within the current lock window.

Items 1–3 are available only to code running inside the trusted Python controller process
with unrestricted access. This is the **declared threat boundary**: the controller
installation and its signing key are trusted. A fully compromised controller process can
fabricate records. This is acknowledged in `TRUST_BOUNDARY.md` and `STAGE2_S2_CHECKPOINT.md`
and is not a new finding.

**No bypass against the declared in-process controller trust boundary was found.**

### 6.9 Additional adversarial counterexample search

This review specifically searched for a counterexample that could satisfy the S2 acceptance
suite while still fabricating evidence. The following paths were examined:

**a. Can `state_manager.verify_all_evidence` be used to inject evidence?**
No. `verify_all_evidence` constructs a `VerificationSession(resume=True)` and calls
`verify_evidence()` which is read-only. It does not call `_run_gate` or `sm._transaction`.
No append path exists.

**b. Can `authorize_recovery` + returned session be used to skip execution?**
The returned session is a `VerificationSession(resume=True)` object. Calling `run_diff()`
on it would invoke `_run_gate` which calls the concrete gate (validate_diff), not skip it.
There is no special fast path for `resume=True` sessions in `_run_gate`. The recovery path
is only for restoring session state, not for bypassing execution.

**c. Can `_recover()` + `_transaction` be manipulated to inject `gate_evidence`?**
`_recover()` calls `_recovery_session`, then executes `change()` inside `_transaction`.
The `change()` closure only modifies `current_state` and `execution_status`. It does not
touch `gate_evidence`. The `_transaction` method itself only increments generation and
persists; it has no special privilege to write arbitrary fields.

**d. Can the `append` closure be injected through some other `_transaction` call?**
`_transaction(mutate)` accepts any callable `mutate`. Only `_run_gate` provides an `append`
closure that writes to `gate_evidence`. All other callers of `_transaction` (`transition`,
`set_execution_status`, `halt_human`, `_begin_verification`, `register_worker_run`,
`_consume`, `record_audit_model`, `_recover`) do not touch `gate_evidence`.

**No additional concrete counterexample was found.** The only remaining fabrication path
is full in-process controller compromise — the declared and accepted trust boundary.

---

## 7. Binding analysis

Each signed record (L208–215) contains:

| Field | Binding |
|---|---|
| `task` | `self.sm.task_id` |
| `repository` | `str(self.root)` (resolved path) |
| `gate` | The specific gate name from `_run_gate` |
| `context` | `self.context.to_dict()` — includes B, C, tree, M, spec/config/policy digests |
| `implementations` | `self.identities` — frozen at session init, re-checked at `_current()` |
| `attempt` | `self.attempt` — per-session random 64-hex token |
| `key_id` | `self._key.identity` — SHA-256 of the raw key bytes |
| `sequence` | Monotonically increasing, gapless, from 1 |
| `generation` | State generation at time of signing, strictly increasing |
| `previous` | HMAC signature of the preceding record (chain) |
| `supplemental.execution_result_sha256` | SHA-256 of the canonical serialization of the raw gate result |
| `signature` | HMAC-SHA-256 of all of the above fields |

`verify_evidence` independently validates:
- HMAC signature (with the live key re-read from disk)
- All identity fields against session's current `self.identities`
- `context`, `attempt`, `key_id` against session's frozen values
- `sequence`, `previous` (chain continuity)
- `generation` (monotonically increasing, within state bounds)
- `issued_at` (not in the future, not expired by `evidence_ttl_seconds`)
- `result` == 'PASS', `schema` == 36

The binding covers all required identities listed in the S2 contract.

---

## 8. `execution_result_sha256` — scope and limitations

**What it authenticates:** SHA-256 of `canonical(result_body)` where `result_body` is:
- For DIFF_GATE, TESTING, SAST: the raw result tuple returned by the concrete gate call.
- For LOGIC_AUDIT: `(result[0], result[1].model_dump(mode='json'), result[2])`.

The hash is computed at L197 (before the lock), then included in the signed record at L213–214.
The HMAC signature at L215 therefore covers the result hash. A different result tuple would
produce a different hash, and any tampering with the hash would invalidate the HMAC.

**What it does NOT prove:**
1. **Implementation identity:** The hash is of the Python object returned by the boundary
   adapter — it does not prove the adapter was the authentic Docker/native/scanner backend.
   An S3-substituted adapter could return an eligible result with the same structure, producing
   a valid `execution_result_sha256` that does not correspond to the authentic tool output.
   This is an S3 concern, not an S2 regression.
2. **External recomputation:** The result tuple is not stored durably outside the signed
   record. An external auditor cannot recompute `execution_result_sha256` without the original
   gate call. The hash is a commitment, not a self-contained proof of execution.
3. **Artifact identity:** For TESTING, the hash covers the Python tuple including the
   `trusted_verifier_result` dict — not the on-disk test artifacts or Docker image digest.
4. **Native tool behavior:** Does not prove live Docker execution, POSIX containment,
   real Semgrep/Bandit run, or real model inference. These remain NOT VERIFIED.
5. **Temporal binding:** The hash does not bind the execution to a wall-clock timestamp
   with external attestation. `issued_at` is the controller's local clock.

**Additional observation:** `result_hash` is computed before the lock is acquired (L197
before L198). The variable is an immutable string. Even if the underlying result tuple's
dict values were mutated after L197 by an in-process attacker, the committed hash would
not change. This is structurally sound for the declared in-process trust boundary.

---

## 9. Failure, exception, simulation, duplicate, and stale-context paths

Each is independently verified:

| Path | Mechanism | Test coverage |
|---|---|---|
| Gate failure | `eligible = False`, returns result without reaching signing | All 4 gates × failure mode |
| Gate exception | Exception propagates before `eligible` check; transaction not reached | All 4 gates × exception mode |
| Simulation | `eligible = False` + explicit `RuntimeError` for LOGIC_AUDIT | `test_simulated_audit_cannot_append_evidence` |
| Duplicate gate | `GATES[sequence] != gate` inside `append()`, transaction rolled back | All 4 gates |
| Out-of-order gate | `_before()` → `verify_evidence(required=prior)` fails before execution | All 4 gates |
| Stale spec | `_current()` → `context.verify_current()` returns `False` | All 4 gates × spec drift |
| Candidate drift | `_current()` detects C mismatch after diff execution | Dedicated test |
| Failed CAS (merge) | `execute_fast_forward_merge` returns `(False, reason)`, `COMPLETED` not set | Recovery controls |

The `test_each_gate_failure_or_exception_cannot_append` extension test covers all 8
combinations (4 gates × 2 modes). It uses `implementation_identities` monkeypatching
to isolate S2 result-path behavior from S3 identity rejection, which is appropriate:
the test verifies that a failure/exception does not append evidence regardless of
implementation drift.

---

## 10. Changed success predicates — legitimacy review

**Concern:** Could the type-strict predicates reject legitimate results or accept malformed
ones from TESTING, SAST, or LOGIC_AUDIT?

- **DIFF_GATE**: `validate_diff` returns `(bool, dict)`. The eligible predicate matches
  its documented return convention exactly.
- **TESTING**: `TestSupervisor.verify_candidate` returns a 5-tuple with bool at [0] and
  int at [3]. The predicate matches the documented convention.
- **SAST**: `run_sast` returns `(int, dict)`. The `type(result[0]) is int` predicate
  correctly distinguishes SAST from DIFF_GATE/TESTING returns. The `results == []` check
  correctly requires no findings (not just falsy).
- **LOGIC_AUDIT**: `execute_logic_security_audit` returns `(bool, LogicAuditOutput|None, dict|None)`.
  The predicate's `.status == 'PASS'` check is correct; SIMULATED status is rejected at
  both the predicate and the explicit `simulate` guard.

**No predicate was found that would reject legitimate successful gate output or accept
malformed output.** The type-strict (`type(x) is T`) checks prevent numeric
coercion edge cases and are appropriate.

---

## 11. Trust boundary and S3 separation

The declared S2 trust boundary is the **trusted in-process controller**:
- The controller installation, its Python code, and its HMAC signing key are trusted.
- Candidate code runs **outside** this boundary, behind the execution backend.
- `_run_gate` routes through concrete boundary adapters (not caller-supplied objects).
- Python attribute access and naming are not a separate security boundary.

**S3 distinction:** S3 concerns the identity of the actual backend/adapter object that
executed the gate. An in-process attacker with unrestricted access could replace
`DockerExecutionBackend.execute` before `_run_gate` runs, causing an untrusted implementation
to produce the result that gets signed. The `implementation_identities()` function captures
source file hashes and loaded code identity at session creation, and `_current()` re-checks
them at signing — but Python attribute replacement after identity freeze can circumvent
this (the S3 counterexamples). This is **S3's scope, not S2's**. The S2 tests correctly
isolate this by monkeypatching `implementation_identities` to return the frozen dict,
which is the correct approach for testing the S2 execution path independently.

---

## 12. Independently reproduced test results

### Original S2 suite (11 cases)
```
python -m pytest tests/security_acceptance/round37/test_s2_gate_authority.py
     -v --import-mode=importlib --tb=short --no-header -q
```
**Result:** `...........` [100%] — **11 passed, 0 failures, 0 errors, 0 skips.**

Pytest exited with code 1 due to a pre-existing Windows `PermissionError` during dead
symlink cleanup in `pytest-of-RENEC/pytest-current` (identical error seen in all test
runs on this host, including the S1 run). This is a pytest temporary-directory housekeeping
issue on Windows, unrelated to any test assertion. All 11 test assertions passed.

### S2 extension suite (19 cases)
```
python -m pytest tests/security_acceptance/test_round37_s2_extension.py
     -v --import-mode=importlib --tb=short --no-header -q
```
**Result:** `................... ` [100%] — **19 passed, 0 failures, 0 errors, 0 skips.**

Same post-session Windows `PermissionError` from dead symlink cleanup.
All 19 test assertions passed.

### S1 control (5 cases, confirming open failures)
```
python -m pytest tests/security_acceptance/round37/test_s1_durable_authority.py
     -v --import-mode=importlib --tb=line --no-header -q
```
**Result:** `FFFF.` — **4 failed, 1 passed.**

The four S1 paired rollback/deletion failures are present and unresolved. S2 work does
not repair them.

---

## 13. Round 3.6 regression evidence

Sol's `round36-after.xml` records **61 tests, 0 failures, 0 errors, 0 skips.** This XML
file was independently hash-verified at `30a311fb49e422473de6ac28245a5980812afb1374ee1c9f978c1c0b016ee57a`.
Its root structure confirms `testsuites/testsuite tests=61 failures=0`.

The 61-case count includes all 7 frozen pipeline schedule tests per the S1 checkpoint.
This review did not independently rerun all 61 Round 3.6 cases, as:
- Only `gate_controller.py` changed in S2.
- The S2 test run itself exercises the gate execution path extensively.
- The 61-case run exercises pipeline schedules, HMAC evidence, behavioral challenges,
  exact-SHA/CAS controls, persistence, concurrency, and state authority.
- No path from the gate_controller S2 change touches the state machine, scheduling,
  challenges, or CAS logic directly.

The Round 3.6 XML hash matches, the S2 tests pass, and no regression signal was observed.
A full 61-case independent rerun is acknowledged as not performed here.

---

## 14. S1 status

**S1 remains OPEN and release-blocking.** The four acceptance failures are:

- `test_restoring_all_colocated_files_is_rejected_by_fresh_process[spent-budget]` — FAIL
- `test_restoring_all_colocated_files_is_rejected_by_fresh_process[terminal]` — FAIL
- `test_deleting_all_colocated_files_is_rejected_by_fresh_process[spent-budget]` — FAIL
- `test_deleting_all_colocated_files_is_rejected_by_fresh_process[terminal]` — FAIL

Each fresh process still accepts generation 0, `INIT/RUNNING`, worker count 0 after the
paired attack. This review independently confirmed these failures. No result from this S2
review waives these failures or implies any S1 progress. The S1 independent review's
conclusion stands unchanged.

---

## 15. Separate conclusions

1. **Original bypass closed:** `_record_success` is absent from production. No path through
   `VerificationSession`, `StateManager`, or any other reachable in-process API can produce
   a signed gate record without executing the concrete gate via `_run_gate`. The frozen
   direct-issuer counterexample is closed within the declared boundary.

2. **No new counterexample found:** Extensive adversarial tracing of `_run_gate`,
   `verify_all_evidence`, `authorize_recovery`, `_recover`, and `_transaction` found no
   path capable of appending evidence without concrete gate execution. The only remaining
   fabrication path is full in-process controller compromise — the declared trust boundary.

3. **Source hashes verified:** All four manifests, all frozen test files, all 14 production
   files at their S2 values, and all six JUnit XML reports match their recorded hashes.
   Sol's `summarize_results.py` also independently confirms all matches.

4. **Test results independently reproduced:** 11/11 original S2 cases and 19/19 extension
   cases passed in fresh test runs. Pytest exit code 1 is a pre-existing Windows dead
   symlink cleanup error, not a test failure. S1: 4 failed / 1 passed, unchanged.

5. **`execution_result_sha256` limitations documented:** The hash commits the gate result
   at signing time and is covered by the HMAC signature. It does not prove implementation
   identity (S3 concern), support external recomputation, or establish native execution
   (Docker/POSIX/scanner/model). These limitations are known and correctly attributed to
   S3 scope and native environment verification requirements.

6. **Native execution properties not demonstrated:** Docker image digest, real UID/network/
   mounts/secret exclusion, container lifecycle, POSIX materialization races, real
   Semgrep/Bandit output, and real model inference remain NOT VERIFIED. The S2 doubles
   exercise controller routing, not these native properties.

7. **S2 scope respected:** S3–S5 and F1–F3 are not remediated here. S2 acceptance does not
   imply or enable S3–S5 bypass. Engineering may proceed to S3 as a separately scoped stage
   while S1 stays explicitly open and release-blocking.

8. **No overall Round 3.7 security PASS:** S1 is open. S3–S5 are unimplemented. Full
   acceptance suite, F1–F3 policies, and all seven production schedules have not been
   re-run. No Round 3.7 PASS is granted or implied by this S2 review.
