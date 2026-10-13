# Research evidence scope of the public checkpoint

The public checkpoint is a curated research snapshot. It contains selected Python runtime and verifier source, selected frozen tests, isolated Stage A C++ source/tests, design contracts, final reviews, and concise public summaries. It is useful for understanding the engineering and review method, but it is not a complete Round 3.7 security evidence bundle.

The internal research archive retains historical manifests, raw build and process evidence, intermediate reviews, and ongoing Round 3.7 research. It has one known **ARCHIVAL_GAP**: the byte-identical original of the first pure `ReadFixtureHead` codec Decision-B review is unavailable. An internal codec-correction manifest pins that original, and a later nonce manifest pins the correction manifest. Neither manifest is changed or presented as a complete public verification chain.

The first codec review found that validated P11 bytes could be mutated through a result reference after validation. A bounded correction changed the result storage/accessor boundary and received a subsequent independent Decision A. The [public review support summary](PUBLIC_REVIEW_SUPPORT_SUMMARY.md) records that chronology and links to the later review. The currently edited intermediate report is omitted; its original identity is not claimed.

**The public checkpoint does not claim that every internal historical manifest can be independently reproduced from the GitHub checkout.** Historical review documents may retain links to raw local support that is deliberately omitted. Portfolio navigation uses this scope document and the support summary; an original review link to omitted raw evidence is a historical reference, not a promise that the target is published.

A future `PORTFOLIO_CHECKPOINT_SHA256.txt`, if generated after the exact staged tree is frozen, would establish integrity only for this curated public snapshot. It would not repair or supersede an internal manifest and would not constitute security acceptance.

Current status remains **G1 HOLD / UNAPPROVED; S1 OPEN; Stage A NOT PASSED; Round 3.7 NOT PASSED**. S2–S5 have bounded local reviews but await final global regression against final S1; F1–F3 remain pending. The selected Python evidence is 573 collected, 100 application passes, 45 S2–S5 passes, and S1 one pass/four failures. The full suite and G1/G2/G3 were not run; live Docker and native POSIX remain unverified where applicable.
