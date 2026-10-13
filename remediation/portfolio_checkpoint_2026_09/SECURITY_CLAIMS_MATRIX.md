# Security claims matrix — current candidate

| Claim | Evidence allowed in public description | Limit |
| --- | --- | --- |
| Python runtime has FSM, worktree isolation, deterministic gates, immutable verification context, controller-side `password-v36` challenges, HMAC records, and Git ref CAS | Source under `orchestrator/`, `scripts/`, `trusted_tests/`, plus tests | These are implemented mechanisms; they do not establish a production-ready or fully secure system. Hidden challenges are restricted to `password-v36`. |
| Round 3.6 independent audit confirmed S1–S5 and F1–F3 | `round37/INDEPENDENT_AUDIT.md`; Stage 1 frozen cases/manifests | Historical diagnostic, not the current result of every local repair. |
| S2–S5 locally repaired and independently reviewed | Selected Stage 2 checkpoints and independent final reviews; frozen regression tests | Reviews are bounded to their local trust assumptions; final global regression against final S1 remains required. |
| Stage A C++/Windows accepted bounded source increments | `stage_a_fixture/src/`, `tests/`, selected independent reviews | Isolated fixture research. Contracts/snapshot, authority/P10, A2 composition/TokenUser, A3 P11, ReadFixtureHead wire/codec, immutability and BCrypt nonce are source-slice acceptances only. |
| Codec and nonce historical independent reviews | Later codec-correction and nonce `FINAL_REVIEW.md` reports, plus the public support summary | Initial codec review was Decision B for a post-validation P11 mutability bypass; original intermediate bytes are unavailable. The complete internal codec-to-nonce hash chain is omitted from the public set. Historical bounded decisions are not public manifest proof. |
| Public Stage A reproducibility | Included C++ source/tests and bounded final reviews | Complete public native build and fixture-commissioning instructions are pending. Historical reviewed build results do not establish this host's MSVC result or G1/G2/G3. |
| S1 durable-state authority | Active remediation | **OPEN.** No G1 security approval or native authenticated A2↔A3 completion. |
| P14/P15/process-object ACE | Design proposal, adversarial review and Luna adjudication | Open trusted-delivery decision; not accepted native source, installed ACE, live process observation or transport. |
| G1 / Stage A / Round 3.7 | Current controlling status | **HOLD / UNAPPROVED; NOT PASSED; NOT PASSED.** G2/G3 commissioning pending. |
| F1–F3 | Historical audit findings and open work list | Integration/recovery policy and final regression pending. |
| Native Windows, Docker, POSIX isolation | Synthetic/native-local source tests and earlier bounded observations where stated | No general host commissioning, live Docker or native POSIX guarantee follows from this checkpoint. |
| Selected Python publication evidence | Luna independently reran collection (573), 100 application tests (pass), 45 S2–S5 frozen tests (pass), and S1 durable authority (1 pass, 4 fail) | Full suite not run. The four S1 failures are current open-security evidence; G1/G2/G3 not run. MSVC unavailable in publication-review shell; live Docker and native POSIX remain NOT VERIFIED. |
| Public research evidence set | [Research evidence scope](RESEARCH_EVIDENCE_SCOPE.md), selected source/tests, design and final review documents | Curated portfolio subset, not the complete internal Round 3.7 archive or a security attestation; one internal archival gap remains. |

Forbidden headline claims include `secure`, `stable`, `production-ready`, `Round 3.7 PASS`, `S1 closed`, `G1 approved`, `P14/P15 accepted`, `authenticated native boundary complete`, and `G2/G3 complete`.
