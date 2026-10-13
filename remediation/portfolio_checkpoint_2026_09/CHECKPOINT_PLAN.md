# Portfolio checkpoint plan — 2026-09-28

**Proposed label:** `Round 3.7 research checkpoint`. This is a descriptive checkpoint label, not a release, version tag, G1 decision, or security milestone.

## Purpose and boundary

Present the Python factory, deterministic verification methodology, reviewed local Round 3.7 repairs, and isolated C++/Windows Stage A research without changing security semantics. Preserve **G1 HOLD / UNAPPROVED; S1 OPEN; Stage A NOT PASSED; Round 3.7 NOT PASSED**. P14/P15/process-object ACE design remains under adjudication. Native authenticated A2↔A3 transport, G2/G3, F1–F3 closure, and final regression remain pending.

## Candidate diff and public evidence scope

The corrected candidate in the current `dev` worktree is review material only. The future public tree is the exact base `c5fd13c890bc4dffec7c4b6812292b5a0235cc52` plus the additions and modifications in [PORTFOLIO_OVERLAY_PATHS.md](PORTFOLIO_OVERLAY_PATHS.md). The old `PUBLIC_INCLUDE_LIST.md` is **SUPERSEDED FOR STAGING BY PORTFOLIO_OVERLAY_PATHS.md**; it is retained locally as a prior reviewed preparation list and is excluded from the public overlay. [PORTFOLIO_EXCLUDED_INTERNAL_EVIDENCE.md](PORTFOLIO_EXCLUDED_INTERNAL_EVIDENCE.md) defines the explicit omissions. **The dirty-`dev` deletion of `tests/test_e2e_dry_run.py` is excluded**; the portfolio worktree must retain the unchanged base version. No Python or C++ source/security file was edited for this final curation pass.

The four Astra historical reviews named in the correction record were restored from exact original bytes. Their original links remain historical references. The modified initial codec Decision-B review is not published. The [research evidence scope](RESEARCH_EVIDENCE_SCOPE.md) and [public review support summary](PUBLIC_REVIEW_SUPPORT_SUMMARY.md) disclose the internal archival gap and the omitted codec-to-nonce manifest chain. The public set is a curated research snapshot, not complete internal evidence or a security attestation.

## Recommended Git route

Use a dedicated `portfolio/round37-checkpoint` branch **later**, after Luna differential review. Create it from exact HEAD `c5fd13c890bc4dffec7c4b6812292b5a0235cc52` in a separate worktree, then copy only the explicit overlay additions/modifications. Leave `tests/test_e2e_dry_run.py` untouched at its base version. Compare file hashes and the complete staged diff against the overlay operations; run the prepublication checks on that exact staged snapshot. Do not use `git add .`, merge wholesale, or stage during this preparation step.

Before any publication, Luna should independently review: (1) exact staged file names and any omissions of accepted source/test dependencies; (2) sensitive-data scan on staged blobs and historical references; (3) README claims against current source/reviews, especially S1 and G1; (4) P14/P15 documents as **proposals/adjudication**, not implemented boundary; (5) all failing/skipped/host-specific tests; (6) `.gitignore` effects and links from selected review documents. Publication requires a separate decision after that review.

Portfolio-facing links must resolve within the resulting public tree. Immutable historical reviews may retain links to omitted raw support, as explained in the public evidence-scope documents. Audit both classes separately on the exact staged tree after Luna reviews this candidate.

## Candidate readiness

This package is ready for Luna differential review, not publication. `PREPUBLICATION_TEST_PLAN.md` records Luna's independent rerun of 573 collected Python items, 100 passing application tests, 45 passing focused S2–S5 items, and **four failing S1 durable-authority cases with one passing control**. Only documentation and historical byte restoration changed in this pass, so those results remain the recorded selected evidence. The broad suite and exact staged-snapshot regression remain to be run.
