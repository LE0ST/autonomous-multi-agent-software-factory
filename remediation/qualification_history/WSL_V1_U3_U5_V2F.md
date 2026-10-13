# Bounded WSL and V2F qualification history

This is a derived, redacted summary of historical records identified in `supplemental-research-sources.csv`. It is a research note, not a qualification report or evidence bundle. Private machine paths, runtime endpoints, and host-specific identifiers are omitted.

## Factory Core V1 and U.3/U.5 (WSL, 2026-10-10)

The continuation status records a bounded deterministic demonstration with positive and intended-negative outcomes attributed to an independent Luna High review supplied by the operator. Worker and audit transports were mocked; Docker TESTING and Semgrep ran in the reported Linux environment. The raw Docker and Semgrep outputs were not retained for independent recomputation. The checkout remained at the pre-integration commit after the successful ref update (F1), and that synchronization issue remains open. This does not establish full Factory acceptance or real-provider readiness.

The U.3 source package was used to prepare the bounded run. U.5 records four runtime probes as completed pending operator review. Those observations are historical Linux/WSL evidence; they are not Windows qualification, Docker TESTING acceptance, or a current-host claim.

## V2E-R2 baseline and V2F (offline only)

The frozen V2F package identifies a V2E-R2 baseline and retains source/package inventories. V2F implements an offline-only supervised boundary. It has no physical HTTPS sender or real credential input path, and the experimental core stops before candidate construction.

The V2F results document reports 183 focused tests passed and a retained selection of 339 passed with 13 deselected. The freeze also retains independently produced XML for 183, 339, and 8 additional SAST-related tests. The freeze did not rerun these tests; the XML is historical Linux evidence, not execution performed by the Windows transfer. The focused suites use controlled doubles and do not establish live provider behavior, real Docker TESTING, Semgrep qualification, E2E, or native Windows support. Five Semgrep integration exclusions remain documented.

Historical V2E all-denied concurrency evidence remains unresolved. S1 paired rollback/deletion remains OPEN; F1 checkout synchronization remains separate. Physical HTTPS, real credential delivery, the hard USD 1 cost ceiling, and the whole-controller watchdog remain unqualified.

## Incomplete version history

The frozen handoff provides the V2E-R2 baseline and V2F checkpoint, but does not provide a complete, independently reviewable V2A-to-V2D history or every intermediate V2E package and raw result. Those versions must not be reconstructed from V2F or represented as complete here. Raw Linux runtime reports, XML, and signing/state material are not included in this public summary.

**Current governance:** Factory Core V1 = NOT PASSED; Round 3.7 = NOT PASSED; G1 = HOLD; S1 = OPEN; V2F = PASS for bounded offline development only.
