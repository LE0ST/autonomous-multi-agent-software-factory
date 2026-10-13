# Explicit public exclusions for the proposed checkpoint

This curation pass did not delete any file. The paths and artifact classes below must not be copied or staged on the checkpoint branch. [PORTFOLIO_EXCLUDED_INTERNAL_EVIDENCE.md](PORTFOLIO_EXCLUDED_INTERNAL_EVIDENCE.md) is the explicit internal-evidence exclusion ledger; [PORTFOLIO_OVERLAY_PATHS.md](PORTFOLIO_OVERLAY_PATHS.md) is the only staging path authority.

The **deletion operation** for `tests/test_e2e_dry_run.py` is excluded pending separate source review. The isolated checkpoint worktree retains the file unchanged from HEAD `c5fd13c`; it is not copied from the currently deleted path in `dev`.

## Sensitive and dynamic local state

- `.env`, `.env.*` except tracked `.env.example`; `apis.txt`; `*.key`; `.controller-secrets/`; `.evidence_key`.
- `.worktrees/`, `orchestrator/state/state_*.json`, `orchestrator/state/state_*.lock`, `orchestrator/payloads/*.json`, `CRASH_REPORT_*.md`, `HUMAN_REVIEW_*.md`.
- `.coverage`, `.pytest_cache/`, `__pycache__/`, `*.pyc`, `*.egg-info/`, local virtual environments and IDE metadata.

## Generated and temporary outputs

- Every `remediation/**/build*/` and `remediation/**/reviewer_build*/` directory; all `.obj`, `.exe`, `.pdb`, `.ilk`; generated observation-helper executables.
- Raw `remediation/**/*.xml`, `remediation/**/*.console.txt`, `remediation/**/*.process.json`, run-specific JSON, temporary logs and command transcripts, including `round36/logs/` and Round 3.7 `stage2_*/` run captures. This is a curated documentation checkpoint, not a full forensic artifact archive.
- Root scratch files: `0`, `2`, `1120`, `audit_failures.txt`, `mismatch_link_exit.txt`, `contracts.obj`, `snapshot.obj`, `windows_snapshot.obj`, `windows_snapshot_test.obj`.
- `remediation/portfolio_checkpoint_2026_09/pytest_tmp_*/` and any later local test output.

## Unreviewed or low-value local research material

- `specs/T1.md` and unselected Round 3.7 intermediate review/probe files, helper observations containing machine paths, exploratory scripts, and superseded drafts. Their presence in the local worktree does not make them part of this candidate.
- `remediation/round36/REPORT.md`, `remediation/round37/REPRODUCTION.md`, the S2/S3 `REVIEW_ADDENDUM.md` files, and `stage_a_fixture/G1_MANIFEST_DELTA.md` contain unnecessary absolute machine paths. They remain local pending a separate sanitized public version; selected base S2/S3 reviews and this checkpoint's test plan supply the public context.
- `remediation/round37/ARTIFACTS_SHA256.txt` and hashes of omitted raw artifact trees; including those without their target files would be misleading. Selected frozen test manifests in `tests/security_acceptance/` are included. `tests/security_acceptance/ROUND35_FROZEN_SHA256.txt` is excluded because the exact historical Round35 test bytes are unavailable; the current public test is ordinary source, not frozen-manifest proof.
- Supporting local review notes and raw records referenced by the historical reviews are summarized in `PUBLIC_REVIEW_SUPPORT_SUMMARY.md`; the original omitted support targets remain excluded unless separately reviewed.
- The currently edited `remediation/round37/independent_review_read_fixture_head_codec_increment/FINAL_REVIEW.md` is excluded from the public set because its byte-identical original is unavailable. The internal codec-increment, codec-correction, and nonce `SHA256.txt` manifests and associated hash-verification outputs are excluded under Luna's transitive dependency cut. Do not alter those internal records.
- The independent `remediation/portfolio_checkpoint_2026_09_luna_review/` package is local review material and is not included in this public candidate.
- The Luna differential, archival, and public-lineage review packages, along with `PUBLIC_INCLUDE_LIST.md`, its exact `PUBLIC_INCLUDE_LIST_V2_226.md` snapshot, and `WORKTREE_INVENTORY.md`, remain local preparation material. They are not copied into the curated public overlay.

The explicit overlay operations are authoritative for copied/staged worktree paths; all 61 base files are inherited, including `tests/test_e2e_dry_run.py`. No deletion is approved. Before staging, review every explicit pathspec; `.gitignore` is a safety net, not an allow-list.
