# Independent security review: Round 3.7 Stage 2, S3 executable implementation identity

**Reviewer:** Independent reviewer (separate session from Sol's implementation)
**Review date:** 2026-09-25
**Decision:** **S3 acceptance GRANTED within the declared trust boundary.** The original S3 backend substitution bypass is closed. All 14 frozen S3 acceptance cases (10 original + 4 extension) pass. No counterexample survives against the in-process controller threat model. **S1 remains OPEN and release-blocking.** S2 is preserved. **No overall Round 3.7 security PASS is granted or implied.**

This review only writes to `remediation/round37/independent_review_stage2_s3/`. No production code, tests, existing manifests, checkpoints, or Git history was modified.

---

## 1. Source hash verification

All five frozen manifests and their 18 listed source entries were independently re-read from disk and hashed with SHA-256. Every entry matches the values recorded in Sol's `RESULTS.json` and `STAGE2_S3_CHECKPOINT.md`. Full details in `SOURCE_VERIFICATION.json`.

| Manifest | SHA-256 (first 16 hex) | Entries | Status |
|---|---|---|---|
| `ROUND36_FROZEN_SHA256.txt` | `c6f065ac5eb704f4…` | 8/8 | ✓ |
| `ROUND37_FROZEN_SHA256.txt` | `a2d0ae027d718c51…` | 8/8 | ✓ |
| `ROUND37_S1_EXTENSION_FROZEN_SHA256.txt` | `231d28d16c28b014…` | 1/1 | ✓ |
| `ROUND37_S2_EXTENSION_FROZEN_SHA256.txt` | `27efe8bd5e0dfbfc…` | 1/1 | ✓ |
| `ROUND37_S3_EXTENSION_FROZEN_SHA256.txt` | `5879e27d004397cb…` | 1/1 | ✓ |

All 15 production files were re-hashed. **14/15 match their post-S2 hashes exactly.** Only `orchestrator/gate_controller.py` changed (the intentional S3 edit):

| File | Post-S2 SHA-256 | Post-S3 SHA-256 | Changed |
|---|---|---|---|
| `orchestrator/gate_controller.py` | `5739f6449d1cf6ac…` | `eccfcdfdd5607454…` | **Yes (intentional)** |
| All other 14 files | unchanged | unchanged | No |

Sol's `summarize_results.py` equivalent verification confirms all matches.

---

## 2. Exact S3 production delta

The sole production change is `orchestrator/gate_controller.py` (post-S2 → post-S3). The delta implements the S3 binding:

1. **Backend object reference freeze** (`__init__`): `self._bound_backend = backend`, `self._bound_backend_type`, `self._bound_backend_execute`, and a controller-generated `_backend_object_token`.

2. **Gate callable capture** (`__init__`): `self._bound_gate_functions` maps each gate to its concrete callable.

3. **Materializer object/method freeze** (`__init__`): `self._bound_manifest`, `self._bound_materialize`.

4. **Audit adapter factory/method freeze** (`__init__`): `self._bound_adapter_factory`, `self._bound_adapter_methods`.

5. **Re-check in `_current()`** (called before each gate, after materialization, and inside signing lock):
   - Backend object reference (`self.backend is self._bound_backend`)
   - Backend class and `execute` method identity
   - Backend instance method binding (`__self__` and `__func__`)
   - Manifest object reference and `materialize` method binding
   - Audit adapter factory and all four provider method references
   - Full `implementation_identities()` map comparison (source hashes + loaded code identities)

6. **Execution-time callable capture** (`_run_gate`): Local `operation` variable bound before execution.

7. **Post-execution callable verification** (inside signing lock): `if operation is not self._bound_gate_functions[gate]`.

8. **TESTING suite byte verification**: Compares `result[4].get('trusted_suite_version')` against frozen `identities['trusted_tests/suite.py']`.

9. **Signed TESTING record includes backend object token** for in-process correlation.

10. **Recovery identity comparison change** in `verify_evidence()`: DIFF_GATE/TESTING/SAST records exclude `AUDIT_ADAPTER_KEYS` from implementation comparison; LOGIC_AUDIT requires full map match.

---

## 3. Original S3 bypass — closed

**Original counterexample:** `test_backend_can_be_substituted_after_identity_capture` (frozen in Round 3.7 S3 suite). The pre-S3 code froze `backend_type` but left `session.backend` writable. TESTING constructed `TestSupervisor(self.backend, ...)` and executed a replacement backend while signing the old backend class/source identity.

**Current protection:** The session now binds the backend *object* by reference (`self._bound_backend`), its class, and the resolved `execute` function. `_current()` checks:
- `self.backend is self._bound_backend` (object identity)
- `self.backend_type is self._bound_backend_type` (class identity)
- `self._bound_backend_type.execute is self._bound_backend_execute` (class method identity)
- If backend exists: instance method binding (`__self__ is self.backend` and `__func__ is self._bound_backend_execute`)

The three original substitution vectors are explicitly tested and rejected:

| Substitution kind | Test | Result |
|---|---|---|
| Different-class backend | `test_backend_substitution_is_rejected_without_testing_evidence[different-class]` | **Rejected** — object reference check fails |
| Same-class instance | `test_backend_substitution_is_rejected_without_testing_evidence[same-class-instance]` | **Rejected** — object reference check fails |
| Instance method override | `test_backend_substitution_is_rejected_without_testing_evidence[instance-method]` | **Rejected** — `__func__`/`__self__` check fails |

**All three original bypasses are closed.** No evidence is appended; the signed backend identity in the (non-existent) record would have matched the frozen backend, but the gate fails before signing.

---

## 4. Adversarial attack surface — independent investigation

Each named attack vector from the review instructions was examined against the current implementation:

### 4.1 Different-class backend substitution
**Blocked.** `_current()` checks `self.backend is self._bound_backend` and `type(self.backend) is self._bound_backend_type`. A different class instance fails both.

### 4.2 Same-class backend instance substitution
**Blocked.** Object identity check (`is`) fails even for same-class instances.

### 4.3 Instance-level `execute` override
**Blocked.** `_current()` verifies `getattr(method, '__func__', None) is self._bound_backend_execute` and `getattr(method, '__self__', None) is self.backend`. A bound method replacement fails the `__func__` check.

### 4.4 Backend method mutation after materialization
**Blocked.** `_current()` is called *after* materialization (line 208 in TESTING path) and again inside the signing lock. The extension test `test_backend_method_changed_during_materialization_cannot_execute` confirms the substitution point is reached but rejected.

### 4.5 Function substitution with identical bytecode but different callable identity
**Blocked.** Dual verification: (a) `operation is not self._bound_gate_functions[gate]` checks callable object identity (`is`), which differs even for bytecode-identical functions. (b) `implementation_identities()` hashes semantic code fields via `loaded_code_identity()`. The probe `scanner-same-code-clone` (function clone with same `__code__`) is caught by the callable identity check: "Gate executable callable changed after freeze".

### 4.6 Scanner substitution followed by restoration during execution
**Blocked.** The extension test `test_scanner_substituted_then_restored_during_call_cannot_sign` intercepts `_materialize`, replaces `gates.run_sast` during materialization, and restores it before the scanner call. The `_current()` check after materialization (line 224 in SAST path) compares `implementation_identities()` and detects `sast_loaded` change. The probe confirms: "Gate implementation changed after freeze: sast_loaded", reached `["materialization completed and scanner replaced"]`, zero new evidence.

### 4.7 Trusted suite bytes changed only at the execution read
**Blocked.** Extension test `test_suite_bytes_changed_only_for_execution_cannot_sign` monkeypatches `Path.read_bytes` to inject drift only when the caller is `verify_candidate`. The TESTING gate checks `result[4].get('trusted_suite_version') == self.identities['trusted_tests/suite.py']` after execution. The altered bytes reach execution (asserted by test), the suite version mismatches, and signing is rejected.

### 4.8 Materializer object or method substitution
**Blocked.** `_current()` checks `self.manifest is self._bound_manifest` and the `materialize` method binding. Extension test `test_manifest_instance_override_cannot_materialize_for_gate` overrides `manifest.materialize` on the instance; the `__func__`/`__self__` check catches it. Probe `manifest-instance` confirms: "Gate materializer implementation changed after freeze", zero new evidence.

### 4.9 Audit adapter factory and provider-method substitution
**Blocked within session.** `_current()` checks `audit_module.create_security_adapter is self._bound_adapter_factory` and each provider's `audit_logic_and_security` method by reference. The original S3 implementation-bindings test `test_changed_gate_implementation_cannot_append_evidence[audit-adapter]` replaces the factory before LOGIC_AUDIT; rejected.

**Recovery relaxation (see Section 5):** Across recovery sessions, DIFF_GATE/TESTING/SAST records exclude audit adapter keys from comparison. This is a deliberate design for legitimate audit adapter change during recovery, not a bypass.

### 4.10 Context, candidate, or attempt changes between execution and signing
**Blocked.** `_current()` inside the signing lock re-validates:
- `context.verify_current()` (B, C, tree, M, spec, config, policy)
- `data['verification_context'] == self.context.to_dict()`
- `data['attempt'] == self.attempt`
- `data.get('evidence_key_id') == self._key.identity`
- Key readability (`self._key.read()`)

The S2 extension test `test_candidate_identity_change_after_real_diff_cannot_sign` and `test_real_success_becomes_ineligible_if_spec_changes_before_signing` cover these paths.

---

## 5. Recovery regression — priority review

**Finding:** The final implementation excludes `AUDIT_ADAPTER_KEYS` when comparing earlier DIFF_GATE, TESTING, and SAST evidence during `verify_evidence()`, while requiring the full map for LOGIC_AUDIT evidence.

```python
# gate_controller.py lines 306–312
if gate == 'LOGIC_AUDIT':
    implementations_match = recorded_impl == self.identities
else:
    implementations_match = ({k: v for k, v in recorded_impl.items()
        if k not in AUDIT_ADAPTER_KEYS} ==
        {k: v for k, v in self.identities.items()
        if k not in AUDIT_ADAPTER_KEYS})
```

**Analysis:** This change was made to resolve the Round 3.6 regression where `test_authentic_audit_recovery_preserves_budgets` failed after the first S3 edit. The regression occurred because an UNCERTAIN audit issued no LOGIC_AUDIT record, but changing the audit adapter factory for the recovery session invalidated the three earlier records.

**Assessment:** This change **preserves legitimate recovery without allowing a previously executed gate's actual implementation identity to be disregarded.**

**Reasoning:**
1. The excluded keys (`adapter_factory_loaded`, `gemini_adapter_loaded`, `deepseek_adapter_loaded`, `glm_adapter_loaded`, `qwen_adapter_loaded`) are **only audit adapter identities**. They are not used by DIFF_GATE, TESTING, or SAST gates.
2. Within a single session, adapter mutation after freeze is **still rejected** by `_current()` checks (factory and provider method reference checks). The relaxation only applies *across* recovery sessions.
3. The three earlier gates' evidence remains bound to all implementations they **actually used**: backend, suite, scanner, materializer, diff/verifier/sast loaded code, installed scanner versions, Python version, and core implementation file hashes.
4. A new LOGIC_AUDIT record in the recovery session **must match the complete current identities map**, including the new audit adapter.
5. An attacker cannot exploit this to disregard a previously executed gate's *actual* implementation (backend, suite, scanner, materializer) because those keys are still compared.

**No bypass found.** The tradeoff is sound for the declared threat model. The intermediate regression report (`round36-regression-final.xml`, 60/61 passed) and final report (`round36-final.xml`, 61/61 passed) are preserved.

---

## 6. Trust boundary analysis

The S3 threat model (`THREAT_MODEL.md`) explicitly declares:
- **Trusted:** In-process Python controller, its installed code, HMAC signing key, OS protections on that installation.
- **Untrusted:** Candidate code (runs behind execution backend).
- **Not a boundary:** Python object checks, private attributes, class names, module paths, source hashes alone.

**S3 correctly operates within this boundary.** The object/reference/callable checks are controller controls against *faulty or untrusted integration* (accidental or hostile substitution by code that has access to the controller process but not arbitrary memory compromise). They do not resist a fully compromised controller process.

**Native properties NOT VERIFIED** (as declared):
- Live Docker image selection/digest, UID/network/mounts/secret exclusion, container lifecycle/cleanup
- POSIX descriptor-relative materialization, races, permissions
- Real Semgrep/Bandit installed-file identity and execution
- Real model inference execution

These require dedicated environments and are correctly labeled NOT VERIFIED.

---

## 7. Compatibility and regression findings

| Suite | Cases | Passed | Failed | Status |
|---|---|---|---|---|
| Original S3 (10) | 10 | 10 | 0 | **Preserved** |
| S3 Extension (4) | 4 | 4 | 0 | **New — frozen before edit** |
| S2 Original (11) | 11 | 11 | 0 | **Preserved** |
| S2 Extension (19) | 19 | 19 | 0 | **Preserved** |
| Round 3.6 Frozen (61) | 61 | 61 | 0 | **Preserved** |
| S1 Control (5) | 5 | 1 | 4 | **OPEN — unchanged** |

**No regressions** in S2, Round 3.6, or S3 acceptance. S1 remains open with the same four paired rollback/deletion failures.

---

## 8. Remaining native security properties not demonstrated

As declared in `STAGE2_S3_CHECKPOINT.md` and `THREAT_MODEL.md`:

| Property | Status | Requires |
|---|---|---|
| Live Docker image selection and digest | NOT VERIFIED | Docker daemon, image pull |
| Real UID, network, filesystem mounts, secret exclusion | NOT VERIFIED | Linux container runtime |
| Bounded output and cleanup against Docker daemon | NOT VERIFIED | Docker daemon stress |
| Container disappearance after timeout/cleanup failure | NOT VERIFIED | Docker daemon fault injection |
| Descriptor-relative POSIX materialization under symlink/rename races | NOT VERIFIED | POSIX OS, `O_NOFOLLOW`, `dir_fd` |
| Permissions and immutable output modes on POSIX | NOT VERIFIED | POSIX OS |
| Actual Semgrep/Bandit execution and installed-file identity | NOT VERIFIED | Installed scanners |
| Real logic/security model execution | NOT VERIFIED | API keys, model access |

The Windows boundary doubles exercise controller routing and fail-closed decisions only.

---

## 9. S1 status

**S1 remains OPEN and release-blocking.** Four acceptance failures persist:
- `test_restoring_all_colocated_files_is_rejected_by_fresh_process[spent-budget]`
- `test_restoring_all_colocated_files_is_rejected_by_fresh_process[terminal]`
- `test_deleting_all_colocated_files_is_rejected_by_fresh_process[spent-budget]`
- `test_deleting_all_colocated_files_is_rejected_by_fresh_process[terminal]`

Each fresh process still accepts generation 0, `INIT/RUNNING`, worker count 0 after the paired attack. This review independently confirmed these failures. No result from this S3 review waives these failures or implies any S1 progress.

---

## 10. S2 preservation status

**S2 fully preserved.** All 30 S2 cases (11 original + 19 extension) pass. The S3 changes do not weaken S2's gate-result authority:
- `_run_gate` dispatcher and eligibility predicates unchanged
- HMAC evidence chain, ordering, context binding, attempt binding, key identity unchanged
- `execution_result_sha256` commitment and HMAC coverage unchanged
- `verify_evidence` validation logic for non-audit gates unchanged (audit keys were not part of S2 scope)

---

## 11. S3 readiness for next engineering stage

**S3 is ready for the next engineering stage** (S4/S5/F1-F3/legacy migration/general verifier) **within the declared scope and trust boundary.**

**Conditions:**
1. S1 must be resolved before any release (release-blocking).
2. Native Docker/POSIX/scanner/model properties require dedicated environment verification before production use.
3. The recovery audit-adapter comparison relaxation should be documented in the security model as an explicit policy decision.
4. Full Round 3.7 acceptance suite (all 7 production schedules) must be re-run after the last production change.

**No overall Round 3.7 security PASS is claimed.** This review covers S3 scope only.

---

## 12. Evidence files

All evidence written to `remediation/round37/independent_review_stage2_s3/`:
- `SOURCE_VERIFICATION.json` — complete hash verification
- `TEST_RESULTS.json` — independently executed test results with exit codes
- `REVIEW.md` — this report

No modifications to production, tests, frozen manifests, or prior review evidence.