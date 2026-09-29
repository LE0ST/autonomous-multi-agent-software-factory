# Luna Decision B publication corrections — 2026-09-28

This records a documentation/curation pass only. It does not change Python or C++ security source, frozen acceptance tests, process ACL logic, P14/P15 implementation, or current gate status. **G1 HOLD / UNAPPROVED; S1 OPEN; Stage A NOT PASSED; Round 3.7 NOT PASSED.** S2–S5 retain bounded local review status pending final regression against final S1; F1–F3 remain pending.

| Luna blocker | Correction |
| --- | --- |
| 60 relative links into excluded artifacts | Replaced all 60 links across 20 selected historical Markdown files with references to the included [public review support summary](PUBLIC_REVIEW_SUPPORT_SUMMARY.md) or accurate plain descriptions of excluded raw evidence. One additional directory link to an excluded raw-record directory was removed after checking the public tree. No raw JSON, compiler transcript, local build output or machine-specific support document was added. |
| Publication-state wording | Both READMEs now call this the Round 3.7 research checkpoint and identify `c5fd13c` as the earlier public baseline. Wording remains accurate after a future commit. |
| Fresh-clone quick start | Both READMEs start from the public checkout, use a new local demo branch and `TASK-006`, pass the current branch with `--base`, require a committed specification and clean tree, and identify the supported `password-v36` verification scope. Routine checks use the selected application tests. |
| Stage A public build claim | Chose Option B. Both READMEs and the included fixture README say that source/tests are research artifacts and complete public native build/commissioning instructions are pending. No excluded build artifact is linked. |
| E2E deletion | Excluded the deletion of `tests/test_e2e_dry_run.py` from the future checkpoint diff. Its HEAD copy must remain in the isolated portfolio worktree pending separate source review. |
| Allow-list | Regenerated as **226 existing, unique selected worktree paths**, up from 224: this document and the public review support summary are the two additions. The final Git tree has **227 files**, counting the unchanged HEAD E2E test. The Luna review package remains excluded. |

The published selected evidence remains 573 Python items collected, 100 selected application tests passed, 45 selected S2–S5 cases passed, and four failing S1 durable-authority cases with one passing control. Luna independently reproduced those results before this documentation-only pass. The full suite and G1/G2/G3 were not run for this pass; MSVC was unavailable in the review shell; live Docker and native POSIX materialization remain NOT VERIFIED. The exact staged tree still requires Luna differential review and staged-blob validation before any publication action.

## Corrected candidate validation

The regenerated allow-list has **226/226 existing paths, zero duplicates, zero ignored selections and zero build/debug/binary selections**. It contains **69 Markdown files**. A fresh inline Markdown-link scan, excluding fenced code, found **230 links**: 35 public external URLs and 195 relative internal links. All 195 internal targets are selected files/directories or valid same-file fragments; **excluded-target links = 0, broken/outside-root links = 0**. The six README heading fragments were checked against their headings.

The selected-file credential scan found no private-key header or apparent genuine token. Four `sk-`-shaped matches and one bearer-shaped match occur only in explicit dummy/sanitizer test fixtures; the retained HEAD E2E test has no credential-pattern or developer-home match. Root `.env` is not selected, remains ignored, and was not read. No selected file contains developer-home absolute paths. `git diff --check` passed on tracked changes; new Markdown documents were also checked for trailing whitespace. No test suite was rerun because this correction changed documentation and curation only.

## Exact Markdown differential for Luna

Publication prose changed in `README.md`, `README_ES.md`, and `remediation/round37/stage_a_fixture/README.md`. The following selected historical documents received link/prose corrections; the number is the original Luna excluded-target link count in each:

| Selected document under `remediation/round37/` | Original links corrected |
| --- | ---: |
| `astra_review_p14_p15_process_ace_design/DESCRIPTOR_AND_HANDLE_REVIEW.md` | 2 |
| `astra_review_p14_p15_process_ace_design/FINAL_REVIEW.md` | 3 |
| `astra_review_p14_p15_process_ace_design/P15_AUTHORITY_AND_LIFETIME.md` | 1 |
| `astra_review_p14_p15_process_ace_design/TRUST_CHAIN_AND_CIRCULARITY.md` | 1 |
| `independent_review_authority_binding_exception_correction/FINAL_REVIEW.md` | 3 |
| `independent_review_controller_authority_composition_encapsulation/FINAL_REVIEW.md` | 2 |
| `independent_review_read_fixture_head_codec_increment/FINAL_REVIEW.md` | 3 |
| `independent_review_read_fixture_head_design_adjudication/FINAL_ADJUDICATION.md` | 6 |
| `independent_review_stage_a_fixture_slice1_correction/FINAL_REVIEW.md` | 3 |
| `independent_review_stage2_s4_reentrant_repair/FINAL_REVIEW.md` | 3 |
| `independent_review_stage2_s5_alias_repair/FINAL_REVIEW.md` | 4 |
| `independent_review_windows_controller_token_sid_increment/FINAL_REVIEW.md` | 4 |
| `independent_review_windows_p10_reader_increment/FINAL_REVIEW.md` | 2 |
| `independent_review_windows_p11_custody_increment/FINAL_REVIEW.md` | 4 |
| `independent_review_windows_snapshot_device_parser_correction/FINAL_REVIEW.md` | 4 |
| `independent_review_windows_snapshot_increment/FINAL_REVIEW.md` | 4 |
| `s1_g1_design_corrections_after_independent_review/MINIMUM_STAGE_A_CONTRACT.md` | 3 |
| `s1_g1_preapproval_design/EXACT_TOPOLOGY_PROPOSAL.md` | 1 |
| `STAGE2_S2_CHECKPOINT.md` | 3 |
| `STAGE2_S5_ALIAS_COUNTEREXAMPLE_REPAIR_CHECKPOINT.md` | 4 |
| **Total** | **60** |

`STAGE2_S5_ALIAS_COUNTEREXAMPLE_REPAIR_CHECKPOINT.md` also lost one directory link to omitted raw console records. In the checkpoint package, `CHECKPOINT_PLAN.md`, `PUBLIC_INCLUDE_LIST.md`, `PUBLIC_EXCLUDE_LIST.md`, `README_CHANGE_PLAN.md`, `SECURITY_CLAIMS_MATRIX.md`, `PREPUBLICATION_TEST_PLAN.md`, and `WORKTREE_INVENTORY.md` were updated. This file and `PUBLIC_REVIEW_SUPPORT_SUMMARY.md` are the two new selected documents. The eight-file Luna review package was not edited.

Most corrected historical review documents and checkpoint files are still untracked in `dev`; ordinary `git diff` does not display their edits. Luna's differential review should read the exact files above against the original link ledger and rerun the allow-list/link checks. After later explicit staging in an isolated worktree, the complete staged diff and staged blobs must receive the final publication gate.

## Git state at correction handoff

Branch `dev` and HEAD `c5fd13c890bc4dffec7c4b6812292b5a0235cc52` are unchanged. The dirty worktree has 15 tracked modifications, the same one pre-existing tracked E2E deletion, 668 nonignored untracked files including these two new checkpoint documents, and 1,247 ignored entries. **Nothing is staged.** The same four pre-existing worktrees remain listed; no branch, worktree, commit or push was created in this pass. The deletion remains visible locally but is expressly forbidden in the later checkpoint diff.

## Final public evidence-lineage curation

Luna subsequently approved a separate, curated public evidence set while retaining the **internal ARCHIVAL_GAP** for the byte-identical original of `independent_review_read_fixture_head_codec_increment/FINAL_REVIEW.md`. The modified copy is excluded from publication; no historical manifest was rewritten. The public support summary now records the initial codec Decision B mutability finding, Sol's correction, and the later bounded independent Decision A. [RESEARCH_EVIDENCE_SCOPE.md](RESEARCH_EVIDENCE_SCOPE.md) states that the internal codec-to-nonce hash chain is not reproduced from the public checkout.

Four Astra historical reports were restored by raw copy from authoritative recovered originals; their destination byte counts and SHA-256 digests matched:

| Historical report | Bytes | SHA-256 |
| --- | ---: | --- |
| `DESCRIPTOR_AND_HANDLE_REVIEW.md` | 9273 | `2a71946f74778f1afe3f85484d3c3af9fe39e2eea063be50c5b0c3693a7e6918` |
| `FINAL_REVIEW.md` | 8743 | `277089124f4681d35d0e142f015b4acf22d404052de533cae44d950968e4d6b2` |
| `P15_AUTHORITY_AND_LIFETIME.md` | 10842 | `0c252c102180ec8fa97c20ad4d23476a67bfa7f88d7bbc510e5e74e8abae67a2` |
| `TRUST_CHAIN_AND_CIRCULARITY.md` | 10698 | `22c28b9cca0ef2d81433ecd22e20730b25eca844f3d32bbe77af681bae6a3321` |

The earlier 60-link correction and 226-path list above are retained as historical preparation results; they are not the final public-link policy or staging authority. Immutable historical links may reference omitted raw support. Portfolio-facing links must resolve in the resulting public tree. [PORTFOLIO_OVERLAY_PATHS.md](PORTFOLIO_OVERLAY_PATHS.md) is the new operation list; [PORTFOLIO_EXCLUDED_INTERNAL_EVIDENCE.md](PORTFOLIO_EXCLUDED_INTERNAL_EVIDENCE.md) records the transitive manifest cut. The exact old list bytes are preserved in local `PUBLIC_INCLUDE_LIST_V2_226.md` (SHA-256 `38465a1b278d60d249bcf034d9a9a95ec4e8cc3591f4e5dfd1e8463b124b48cf`); the working list is marked **SUPERSEDED FOR STAGING**. The E2E deletion remains excluded.

The final proposed overlay contains **15 MODIFY + 166 ADD = 181 operations**, applied to a **61-file base** for a **227-file resulting tree**. The exact codec/nonce internal-evidence exclusion ledger names **eight paths**; broader raw/build/private classes remain excluded by pattern. A portfolio-facing scan of both READMEs and the ten selected checkpoint Markdown documents found **102 relative/internal links and 6 external links (108 total)**, **zero broken internal links and zero omitted-target navigation links** (external URLs not network checked). The selected 227-file scan found no genuine credential, developer-home path, selected `.env`, or build binary; credential-shaped matches were example/template values, source identifiers, or dummy test data. No runtime/security/test source changed during this pass, so Luna's selected test evidence remains the checkpoint evidence.

The separate historical Markdown scan found 58 references in 19 historical documents to intentionally omitted local/raw targets, with zero genuinely missing local targets. These original references are retained under the immutable-history policy and are explained in the public support and evidence-scope documents; they are not recruiter-facing navigation links.
