# Internal evidence excluded from the public checkpoint

This is a publication exclusion ledger, not a deletion instruction. The internal files remain in the development worktree. The public tree is base `c5fd13c890bc4dffec7c4b6812292b5a0235cc52` plus the reviewed overlay; none of the paths below is an overlay operation.

## Exact codec and nonce evidence cut (8 paths)

| Internal path under `remediation/round37/` | Public reason |
| --- | --- |
| `independent_review_read_fixture_head_codec_increment/FINAL_REVIEW.md` | Current copy is edited; the original Decision-B report's required byte identity is unavailable. |
| `stage_a_fixture/read_fixture_head_codec_increment/SHA256.txt` | Internal source/build preservation manifest, not a public proof bundle. |
| `stage_a_fixture/read_fixture_head_codec_mutability_correction/SHA256.txt` | Directly pins unavailable original codec report bytes. |
| `stage_a_fixture/windows_read_fixture_head_nonce_increment/SHA256.txt` | Pins the correction manifest transitively. |
| `independent_review_read_fixture_head_codec_increment/HASH_VERIFICATION.md` | Historical internal manifest-verification output. |
| `independent_review_read_fixture_head_codec_mutability_correction/HASH_VERIFICATION.md` | Reports a hash-chain result that the curated public tree cannot reproduce completely. |
| `independent_review_windows_read_fixture_head_nonce_increment/HASH_VERIFICATION.md` | Reports a hash-chain result that transitively depends on the missing codec original. |
| `ARTIFACTS_SHA256.txt` | Indexes omitted raw/internal artifacts and is not offered as a complete public bundle. |

The later codec-correction and nonce `FINAL_REVIEW.md` reports may be included as historical bounded independent reviews. [Research evidence scope](RESEARCH_EVIDENCE_SCOPE.md) and the [public support summary](PUBLIC_REVIEW_SUPPORT_SUMMARY.md) explain that their complete internal hash chain is omitted.

## Round35 frozen checksum exclusion

`tests/security_acceptance/ROUND35_FROZEN_SHA256.txt` is excluded from this public checkpoint because the exact historical test bytes required by that manifest are not presently recoverable. This publication decision does not modify or repair the internal historical evidence. The included `tests/security_acceptance/test_round35_blockers.py` is current ordinary test source, not frozen-manifest proof.

## Other omitted classes

- Raw compiler outputs, local process logs, XML/JSON run captures, host evidence, temporary probes, `build*/` and `reviewer_build*/` trees, `.obj`, `.exe`, `.pdb`, `.ilk`, caches, and pytest temporary directories.
- Machine-specific manifests/ledgers and redundant intermediate forensic records whose support files are outside the curated tree.
- Root `.env`, local authentication material, dynamic controller state and payloads.
- Luna review/adjudication packages and local checkpoint-preparation records. The prior `PUBLIC_INCLUDE_LIST.md`, its exact `PUBLIC_INCLUDE_LIST_V2_226.md` snapshot, and `WORKTREE_INVENTORY.md` remain local history; they are not publication overlays. `PUBLIC_INCLUDE_LIST.md` is **SUPERSEDED FOR STAGING BY PORTFOLIO_OVERLAY_PATHS.md**.

The dirty-development deletion of `tests/test_e2e_dry_run.py` is excluded as an operation. The test is inherited unchanged from the fixed base. No public deletion is approved.
