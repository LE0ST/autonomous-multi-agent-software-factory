# Selected Factory Core research and qualification records

This directory contains a selected historical export, not the complete Factory Core development record. It preserves 97 research paths from the public `portfolio/round37-checkpoint` tree at commit `7b9ef8f2449ce771391595c7aa63fca187819f98`: 58 Markdown records and 39 reviewed Stage A C++ source/test files. Original `remediation/` paths are preserved.

It also includes a derived, redacted WSL/V2F qualification summary. Source records and their hashes are listed in `supplemental-research-sources.csv` in the preparation package; the exported file is clearly labeled as a summary and does not replace its source reports.

The checkpoint commit changes 180 paths. This candidate selects 97 of them; the other 83 changed paths are inventoried as excluded in the preparation manifest. Further Windows Round 3.7 work, full WSL history, U.3/U.5 raw evidence, and V2A-V2E intermediate records remain unpublished or incomplete. No missing history is reconstructed here.

**Qualification status:** Factory Core V1 = NOT PASSED; Round 3.7 = NOT PASSED; G1 = HOLD; S1 = OPEN; V2F = PASS for bounded offline development only. Historical reports retain their original scope and attribution.

## Publication formatting delta — 2026-10-13

The original byte-exact export remains preserved in integration commit `071b5d9198b4aba1801936e1bb2d70a8d7260786`. The publication tree has one explicitly documented formatting correction in `round37/independent_review_stage2_s2/REVIEW.md`, line 49.

- Original source: public `portfolio/round37-checkpoint` commit `7b9ef8f2449ce771391595c7aa63fca187819f98`, path `remediation/round37/independent_review_stage2_s2/REVIEW.md`.
- Original file SHA-256: `5477ad47149e35aff8e16d9935f16faba11c43de52142b38f9b351a6265811f2`.
- Corrected publication file SHA-256: `a228fa7cbbdea47cb69d5f0a67e533de3de7e4815145f3e7ed8c9bbffce7230f`.
- Exact transformation: replace the two trailing ASCII spaces (`20 20`) immediately before the LF on line 49 with one ASCII backslash (`5c`). Both representations encode a Markdown hard line break. All other bytes, wording and historical verdicts in the review are unchanged.

The original candidate and `research-manifest.csv` remain unchanged. The original manifest continues to describe the historical export, not the corrected publication bytes. A separate `research-publication-delta-20261013.json` in the preparation package records this correction and the scope-note update. This formatting change adds no qualification claim.
