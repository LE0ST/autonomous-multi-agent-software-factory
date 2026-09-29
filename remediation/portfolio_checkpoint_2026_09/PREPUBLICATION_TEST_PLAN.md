# Prepublication test and reproducibility plan

## Checks performed for this checkpoint before staging

- `pytest --collect-only -q -p no:cacheprovider tests/`: **573 collected**, exit 0 on 2026-09-28. `pyproject.toml` excludes `*e2e*` by default. The pre-existing deletion of `tests/test_e2e_dry_run.py` remains visible in the dirty `dev` worktree but is excluded from the proposed checkpoint diff; its HEAD copy must be retained in the isolated portfolio worktree.
- `pytest -q -p no:cacheprovider --basetemp=<workspace checkpoint temp> tests/test_password_validator.py tests/test_rate_limiter.py tests/test_authorization_policy.py`: **100 passed**, exit 0. The initial run with the default pytest temp root had one setup error due to access denial outside the workspace; the rerun used a workspace temp directory and passed.
- Focused frozen S2–S5 selection (`test_s2_gate_authority.py`, both S3 source-binding files, `test_s4_completion_authority.py`, `test_s5_recovery_consumption.py`): **45 selected items passed**, exit 0.
- Focused frozen S1 durable-authority selection (`test_s1_durable_authority.py`): **four failed, one passed**, exit 1. Both paired rollback cases and both paired deletion cases accepted a fresh `INIT/RUNNING` state after restoring/deleting all colocated files. This directly supports **S1 OPEN**; it is a known security failure, not an environment skip.
- `git diff --check -- README.md README_ES.md .gitignore`: exit 0 after presentation edits. Repeat on the exact staged branch diff.

Environment: Windows PowerShell, `pytest 9.1.1` from a local Python 3.14 installation. The `python` app alias was inaccessible in this sandbox; the installed `pytest` command worked. The CI workflow targets Python 3.11 on Ubuntu, so this local run does not substitute for CI.

Luna independently reran the same selected checks for the publication review: **573 collected**, **100 application tests passed**, **45 selected frozen S2–S5 passed**, and **one S1 control passed with four S1 failures**. Luna's commands disabled the pytest cache. This Decision B correction changed only README, review and checkpoint Markdown; no test or security source changed, so the independent selected results remain the recorded checkpoint evidence without another expensive test rerun.

The final public-lineage curation restored four historical Astra Markdown files byte-for-byte and updated only portfolio documentation. No runtime, security, or test source changed in that pass, so the same independently reproduced selected results remain applicable. The public checkpoint omits the internal codec-to-nonce SHA manifest chain and does not offer those historical hash checks as a reproducible public proof. The Round35 test remains ordinary current test source after whitespace cleanup; its historical frozen manifest is omitted because currently available bytes do not match the recorded frozen digest. This does not change the 573 collected, 100 selected application passes, 45 selected S2–S5 passes, or S1 one-pass/four-fail evidence.

## Expected now, subject to rerun on exact staged snapshot

Run Python tests with an explicit writable `--basetemp` and `-p no:cacheprovider` on this host. Start with the application examples and focused S2–S5 frozen regression suites, then run the broader Python suite and classify each failure against historical Round 3.6 legacy fixtures, the open S1 boundary, or an actual new regression. Preserve the full command, exit code, test count and environment in the review record. Do not silently skip failures.

The Round 3.6 historical suite had 374 passed, 47 failed and one skipped; that is a historical baseline, not a forecast for this candidate. Current broad-suite pass status has not been established. Each frozen test manifest included in the public checkpoint must be checked against its listed file hashes; the public overlay must not remove a dependency required by those tests. The omitted Round35 manifest is not offered as reproducible public evidence.

## Native and unavailable environments

The C++ Stage A fixture contains synthetic and Windows-native-local source tests. Complete public native build and fixture-commissioning instructions are **pending** for this research checkpoint; no unreviewed recipe is presented as reproducible. Capture independent compile/link/test exits when an appropriate environment is available. A missing `cl` in Luna's publication-review shell is an environment limitation, not a source failure. G1/G2/G3 commissioning, live ACL/process/pipe/ETW observations, live Docker isolation, and native POSIX materialization are outside this checkpoint and **NOT VERIFIED** here.

## Security properties not verified by this checkpoint

S1 closure; G1 approval; Stage A pass; authenticated native A2↔A3 transport; P14/P15 or process-object ACE implementation/acceptance; G2/G3 commissioning; F1–F3 closure; final global S2–S5 regression against final S1; Round 3.7 release PASS. Passing selected Python tests must not be described as proof of any of these.
