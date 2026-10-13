# Round 3.7 Stage 2 — S3 implementation checkpoint

**Scope:** S3 executed implementation identity only. This is an engineering
handoff for independent review, not S3 self-approval or an overall Round 3.7
security PASS. S1 remains OPEN and release-blocking.

## Pre-edit preservation

Before the production edit, all 15 production hashes in the post-S2
`stage2_s2/RESULTS.json` matched. The original Round 3.6 and Round 3.7 manifests
and all 16 source entries matched, as did the separately frozen S1 and S2
extension manifests and their two source entries. The two completed S2 replay
XML hashes in `independent_review_stage2_s2/REVIEW_ADDENDUM.md` matched. The
pre-existing dirty working tree was retained. No protected input discrepancy
was found. The S2 checkpoint's later artifact manifest and status snapshot, and
the independent S2 review/addendum files, account for the additional S2 files
not listed in its earlier `git-status-after.txt`; no unrelated new path was
identified.

## Defect and trust boundary

The frozen S3 counterexample replaced `session.backend` after session creation.
TESTING executed that new object but signed the old backend class and source
identity. A same-class replacement and an instance `execute` override also
worked. The frozen audit adapter and materializer substitutions could append
evidence. Additional pre-edit tests reached suite-byte drift only at the
execution read, a backend method change during materialization, a scanner
replacement that restored its global name during the call, and a manifest
instance method override. All four appended or could authorize evidence.

The security boundary is the trusted in-process controller, its installation
and signing key, and the operating-system protection of those assets. Python
object checks are controller controls against substitution by faulty or
untrusted integration; they are not an independent boundary against arbitrary
controller memory/code compromise. Class names, paths and returned identity
claims alone do not prove the executable that ran. See `stage2_s3/THREAT_MODEL.md`.

## Implementation

`orchestrator/gate_controller.py` is the sole changed production source:

| File | Post-S2 SHA-256 | Post-S3 SHA-256 |
| --- | --- | --- |
| `orchestrator/gate_controller.py` | `5739f6449d1cf6ac226ff924d56c5d08e7d86457682b26a8fe15ae0d780c03ef` | `eccfcdfdd56074541634de2b1a8d97b7a67bcba63af3d7369d435db913945d88` |

The session now checks the frozen backend object by reference, its concrete
class and resolved `execute` function, and the manifest object and resolved
materializer. It captures the concrete gate callables and permits signing only
when a successful result came from the captured callable. The signed TESTING
record includes a controller-generated opaque backend object token, after the
reference check. Loaded identities now include the materializer, audit adapter
factory, and four provider audit methods. The factory and provider methods are
also checked by reference during the session. The compiled trusted suite's
reported byte hash must equal the frozen suite hash. The scanner and backend
are rechecked after materialization and before invocation; a final context,
implementation, callable and attempt check precedes HMAC signing.

The frozen Round 3.6 audit recovery test found one intermediate regression:
an UNCERTAIN audit issued no audit evidence, but changing its factory for the
recovery session invalidated the three earlier records. The final verifier
compares the audit adapter identities only on an actual LOGIC_AUDIT record.
Prior DIFF_GATE, TESTING and SAST records remain bound to all implementations
they executed. Within each session, an adapter change after identity freeze is
still rejected. The intermediate 61-case report with one failure is preserved;
the final complete 61-case replay passes.

## Tests and frozen additions

No original frozen test or manifest was edited. The added extension was run
against unchanged production and then frozen before the first production edit:

| Frozen file | SHA-256 |
| --- | --- |
| `tests/security_acceptance/test_round37_s3_extension.py` | `c8f80cc1ab04b29b81186c6c3ffe6ea7ea17d506f54c9bdbab0d3cc7c6e5636d` |
| `tests/security_acceptance/ROUND37_S3_EXTENSION_FROZEN_SHA256.txt` | `5879e27d004397cb0cff552c392fc48d542857234a421b52c2df978b0ff5c943` |

The four added cases cover suite bytes changed only at execution, backend
method replacement after materialization, scanner substitution and restoration
inside the call, and a manifest instance method override. The suite and backend
cases explicitly assert that their injection point was reached; all four check
that no new evidence was appended. The original S3 fixture uses actual Git
B/C/tree/M and prior signed gate records. A supplementary diagnostic in
`stage2_s3/probe_execution_bindings.py` records the exact rejection messages,
materialization reach and zero appended evidence in `PROBE_RESULTS.json`. It also
shows that a same-code scanner function clone can execute yet cannot sign.
This diagnostic was added after implementation and is not presented as part of
the pre-edit frozen acceptance set.

| Replay | Before S3 | Final post-S3 | Final pytest exit |
| --- | --- | --- | ---: |
| Original frozen S3 (10) | 5 passed, 5 failed | 10 passed | 0 |
| Frozen S3 extension (4) | 0 passed, 4 failed | 4 passed | 0 |
| Combined S3 final | — | 14 passed, 0 failed/error/skip | 0 |
| S2 original and extension | — | 30 passed, 0 failed/error/skip | 0 |
| Round 3.6 frozen | — | 61 passed, 0 failed/error/skip | 0 |
| S1 original control | — | 1 passed, 4 failed | 1 |

The exact XML report hashes, per-case failures, process exit codes and source
hashes are in `stage2_s3/RESULTS.json`. Test temporary directories were outside
the repository. Provisional/interrupted reports and the intermediate
Round 3.6 failure report remain in `stage2_s3/`; the authoritative final reports
are `s3-final.xml`, `s2-final.xml`, `round36-final.xml` and `s1-final-open.xml`.

## Preservation and limits

All 18 previously frozen source entries and four earlier manifests still match
their S2 recorded hashes; the S3 extension and manifest also match. All 14
post-S2 production files outside the intentional gate controller edit match.
The 14 entries in `stage2_s2/S2_ARTIFACTS_SHA256.txt` match, and the S2 review
addendum's completed replay reports remain intact. Transaction-only persistence,
S1 local parser hardening, S2 execution-to-signing, HMAC evidence, context
binding, and exact B-to-C CAS were preserved by the passing S2 and Round 3.6
regressions.

**S1 remains OPEN:** fresh-process paired rollback and deletion still have four
acceptance failures. S4, S5, F1, F2, F3, legacy fixture migration, the full
Round 3.7 acceptance suite and general verifier work were not undertaken.
Live Docker image/digest, UID, network, mounts, secret exclusion, output and
cleanup; native POSIX materialization/races/permissions; real Semgrep/Bandit
installed-file identity; and real model execution remain **NOT VERIFIED** by
these Windows boundary doubles.

Independent review should re-hash the five frozen manifests, the post-S2
production baseline, the S3 extension, and the final reports; inspect the
per-gate adapter comparison and the actual callable checks; and replay the
four named final suites using separate external `--basetemp` directories.
No S3 approval or overall Round 3.7 security PASS is claimed here.
