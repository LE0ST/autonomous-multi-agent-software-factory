# Round 3.7 Stage 2 — S2-only implementation checkpoint

**Scope:** S2 gate-result authority only. This is ready for independent review;
it is not a Round 3.7 security PASS or self-approval. S1 remains OPEN and
release-blocking.

## Preservation before editing

Before the production edit, all 15 production hashes in the post-S1 checkpoint
matched disk. All eight Round 3.6 frozen source hashes, all eight original
Round 3.7 frozen source hashes, and the S1 extension source hash matched their
manifests. The three original manifest hashes also matched the independent
review: `c6f065ac5eb704f40bfa77a2fe318c9294b8590fe22be3e22d5a1c4817a9f9ac`,
`a2d0ae027d718c51b459f9bdf3a954dc7ab9eb098c34f0919a4dbf9c56d0b213`,
and `231d28d16c28b014909a183ab3cb3dbec3f9e785f9effa311d5d04750e8f733e`.
No protected input discrepancy was found. The pre-existing dirty tree and public
documentation edits were left in place; no checkout, reset, merge or rebase was
used.

## Trust boundary and change

Read [the pre-edit trust review](stage2_s2/TRUST_BOUNDARY.md). The old
`VerificationSession._record_success(gate)` signed `PASS` for any listed gate
after context and order checks, even if no gate ran. The frozen issuer-only
counterexample traversed the FSM, produced four valid HMAC records and completed
an actual B-to-C CAS with zero concrete gate calls.

The only production source changed is `orchestrator/gate_controller.py`, from
`877ae73d527eff513063ec91571a627c522ce25648d61acabb8d909d586d373c`
to `5739f6449d1cf6ac226ff924d56c5d08e7d86457682b26a8fe15ae0d780c03ef`.
The standalone issuer is removed. `_run_gate` dispatches to the fixed concrete
diff, trusted suite/backend, SAST, or logic-audit path; only an eligible result
from that same call can reach the transaction that signs a record. It signs a
SHA-256 digest of the returned result. A gate name selects execution, not a
standalone issuer. Failure, exception, simulation, duplicate or wrong order
cannot append. After execution and immediately before signing, `_current`
rechecks the exact B, C, tree, manifest M, specification, configuration,
policy, attempt, key and implementation identities. Existing HMAC chaining,
sequence/generation/TTL validation and exact B-to-C CAS remain in use.

The trusted controller installation and concrete boundary adapters are the
in-process authority. This does **not** resist arbitrary code execution with
unrestricted access inside that Python process or a compromised controller
installation/key. Python private names and attributes are not asserted as a
security boundary. The tests use narrow local execution, scanner, materializer
and audit doubles; native Docker, scanner and model behavior is not verified by
this stage. S3's executable implementation substitution remains separate work.

## Frozen tests and before/after results

The new tests were executed against the unchanged production hash and then
separately frozen before editing production:

- Test: `tests/security_acceptance/test_round37_s2_extension.py` SHA-256
  `26feb774b7d7be8c8e62de041abe684437115a3241c9997ddc9f28154487f998`.
- Manifest: `tests/security_acceptance/ROUND37_S2_EXTENSION_FROZEN_SHA256.txt`
  SHA-256 `27efe8bd5e0dfbfcee6834c011ac11a4f26f724cdd8cce6a0fb7e9b54abd7072`.
- Freeze record: [FREEZE.json](stage2_s2/FREEZE.json), including the before XML
  hashes and the production hash at freeze time.

| Selection | Before | After | Pytest exit before/after |
| --- | --- | --- | --- |
| Original frozen S2 (11) | 5 failed, 6 passed | 11 passed | 1 / 0 |
| S2 extension (19) | 6 failed, 13 passed | 19 passed | 1 / 0 |
| Round 3.6 frozen (61) | Not rerun before this change | 61 passed | — / 0 |
| Original frozen S1 (5) | Independent review: 4 failed, 1 passed | 4 failed, 1 passed | 1 / 1 |

There were zero errors or skips in all six S2-stage reports. The original five
S2 FAIL-before cases were the four direct issuer calls and issuer-only real CAS.
The extension's six FAIL-before cases were four caller-supplied PASS objects,
replayed success for the next gate, and missing signed result digests. Its
remaining controls exercised failure and exception paths for all four concrete
gates, stale authentic results after specification drift, candidate identity
drift, and rejection before signing. All 19 pass after. The Round 3.6 run includes
all seven frozen pipeline schedules. Exact per-case statuses, XML hashes and
production/frozen hashes are in [RESULTS.json](stage2_s2/RESULTS.json);
`summarize_results.py` recomputes them directly from disk.

The final S1 replay still accepts paired rollback and deletion for both active
spent-budget and terminal tasks in a fresh process. These are the same four
release-blocking failures identified by the independent S1 review. This S2 work
does not repair, waive or close S1.

## Files added and limits

Added `tests/security_acceptance/test_round37_s2_extension.py`, its separate
frozen manifest, this checkpoint, and the evidence under `stage2_s2/`:
`TRUST_BOUNDARY.md`, `FREEZE.json`, four S2 XML reports, the Round 3.6 XML,
the S1 XML, `RESULTS.json`, and `summarize_results.py`. All other 14 post-S1
production hashes and all frozen test hashes still match. No S1, S3–S5,
F1–F3, legacy fixture or general-purpose verifier source was edited.

Remaining defects and limits: S1 is open; S3–S5 and F1–F3 are not remediated
here; the full Round 3.7 acceptance and full configured suite were not run;
native Docker/POSIX/scanner/model properties are not established by these
doubles. A fully compromised trusted controller can still fabricate evidence.
Independent review must assess this S2 scope and its trust assumption. Stop
after S2; no commit, push, release or overall security PASS is claimed.
