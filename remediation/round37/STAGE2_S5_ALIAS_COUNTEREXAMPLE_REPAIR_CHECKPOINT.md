# Round 3.7 Stage 2 — S5 alias counterexample repair checkpoint

**Scope:** Repair of Luna's independently reproduced S5 recovery capability identity bypass only. This checkpoint is evidence for another independent review, not S5 self-approval. S1 remains **OPEN and release-blocking**. No overall Round 3.7 security PASS is claimed. S1 and F1–F3 were not changed.

## Preservation and prerequisites

Before the production edit, [PRE_EDIT_VERIFICATION.json](stage2_s5_alias_repair/PRE_EDIT_VERIFICATION.json) reread and matched all 15/15 reviewed S5 production hashes, 10/10 frozen manifests, 24/24 listed frozen sources and manifest entries, and 34/34 earlier review artifacts. The dirty working tree was preserved; prior checkpoints, tests, manifests, independent reviews, and diagnostics were left intact. [PRE_EDIT_GIT_STATUS.txt](stage2_s5_alias_repair/PRE_EDIT_GIT_STATUS.txt) and [POST_EDIT_GIT_STATUS.txt](stage2_s5_alias_repair/POST_EDIT_GIT_STATUS.txt) retain working tree context.

The bypass requires an authentic capability's hash. It is **not** a no-token privilege escalation. The attacker presents a never-issued object whose `__hash__` collides with that authentic capability and whose `__eq__` returns true. Python dictionary `pop` used equality as authority, so the alias could remove the authentic entry. In the wrong mode, the alias spent the authentic capability without recovery. In merge mode, the alias authorized recovery to `AUTO_MERGE/RUNNING` and spent the genuine capability. The root cause is equality in place of exact identity.

Luna's unchanged-production diagnostic passed with actual process exit 0. A separate instrumented diagnostic also passed with exit 0, proving both outcomes and recording **one `__hash__` and one `__eq__` call in each attack path**. The complete process output is in the `luna_alias_before` and `instrumented_alias_before` console records under [stage2_s5_alias_repair](stage2_s5_alias_repair). The source under test still had SHA-256 `4fe56699c2cfbf0619c4e0b18af18ae750371ec23787fd1ffc34259123804cb3` at that point.

## Frozen acceptance and repair

Before changing production, the six-case [counterexample suite](../../tests/security_acceptance/test_round37_s5_alias_counterexample.py) was frozen in [its manifest](../../tests/security_acceptance/ROUND37_S5_ALIAS_COUNTEREXAMPLE_FROZEN_SHA256.txt). Source SHA-256: `26d60ffdcef034052128d6ad584d36f9e2a8ae12dbb217f7af3cc12b5ce8b404`. Manifest SHA-256: `597efd4ffa94d743bb85d6f1907430ff7e713824a0e322f51763a985d8624d28`. The source and manifest were not edited after freezing. Before the production edit it produced 3 passed, 3 failed, actual exit 1. Its failed cases were alias consumption, alias authorization, and malformed caller hash/equality. The passing controls were genuine wrong-mode consumption, reentrant one-shot use, and concurrent one-shot use.

The [production repair](../../orchestrator/state_manager.py) keys the registry by built-in `id(capability)` and stores the issued object as a strong reference with generation, resolved repository, base branch, and mode. `_recover()` retrieves by the presented object's `id`, checks `stored_capability is presented_capability`, and deletes only that exact entry. Built-in `id` and `is` do not invoke caller-defined `__hash__` or `__eq__`. Keeping the issued object alive prevents its ID being reused while authority is outstanding. The manager-local registry retains the task/manager binding. Deletion remains under the state lock and precedes mode, generation, context, Git, evidence, transition, and persistence checks. The in-progress capability is still cleared in `finally`; S4's installed completion authorization was not changed.

The only changed file among the 15 reviewed production files was `orchestrator/state_manager.py`: SHA-256 `4fe56699c2cfbf0619c4e0b18af18ae750371ec23787fd1ffc34259123804cb3` → `cce58f4e044ec96fc010290526609a4b870ed03c512ccaf70e400dc03eed2ccc`. The other 14 production hashes remain unchanged.

## Final replay after the last production change

Every selection used a distinct external pytest `--basetemp`. [FINAL_RESULTS.json](stage2_s5_alias_repair/FINAL_RESULTS.json) records complete console files, JUnit reports, actual process exit codes, commands, file hashes, and basetemp paths. All recorded console and JUnit hashes match on reread.

| Selection | Result | Actual exit |
| --- | ---: | ---: |
| New frozen alias suite | 6 passed | 0 |
| Original frozen S5 | 7 passed | 0 |
| Previous frozen S5 extension | 3 passed | 0 |
| All reviewed S4 acceptance suites | 45 passed | 0 |
| Combined S3 | 14 passed | 0 |
| Combined S2 | 30 passed | 0 |
| Round 3.6 frozen | 61 passed | 0 |
| Focused audit and concurrent recovery controls | 2 passed | 0 |
| Merge/audit legacy regression selection | 19 passed, 34 failed | 1 |
| Original S1 control | 1 passed, 4 failed | 1 |

The genuine capability remains usable after an alias is rejected while strict recovery validation remains valid; the alias cannot consume or authorize it. The actual issued capability is spent on wrong-mode presentation. Unhashable and malformed caller objects cannot spend it, and malformed hash/equality methods are not called. Reentrant and concurrent presentations remain one-shot. A successfully consumed capability cannot be replayed. Original S5 success and the focused audit control demonstrate legitimate merge and audit reopening, while the reviewed S4 suite preserves exact-ref completion controls.

Luna's historical exploit probe now exits 1 because it expects the authentic token to have been consumed after alias rejection; the genuine token remains valid. The instrumented historical diagnostic exits 1 at its expected exploit assertion and records zero attacker `__hash__`/`__eq__` calls. These are **secure-negative diagnostic outcomes**, not acceptance failures. Their complete failing output and JUnit reports are preserved alongside the pre-edit vulnerability reproductions.

The legacy selection retains the exact same 34 failing case names as the prior S5 baseline: 30 fixtures depend on removed `_save_unlocked`, and four retain obsolete candidate, merge signature, FSM schedule, or public completion expectations. The original S1 control retains the exact same four failures. Neither group is counted as passing or concealed. S1's paired mutable state/witness still lacks an external durable rollback anchor.

## Trust boundary and native limits

This in-memory identity mechanism assumes the installed `StateManager` and controller code, Python runtime and built-ins, `StateLock`/`threading.RLock`, process memory, Git executable and ref permissions, evidence HMAC key custody, and state files are trusted. Arbitrary mutation of private manager internals, loaded module code, or the runtime is outside this API boundary. A caller that learns only a token hash cannot recover without the exact issued object after this repair. The registry is not a durable S1 authority.

Native Docker image/digest selection, UID/network/mount and secret boundaries, bounded output and cleanup against a Docker daemon, POSIX descriptor-relative materialization race and permission properties, actual installed Semgrep/Bandit execution identity, real logic/security model execution, controller-only Windows ACLs, and external durable S1 authority remain **NOT VERIFIED**. The password-v36 boundary suite does not prove general-purpose verification.
