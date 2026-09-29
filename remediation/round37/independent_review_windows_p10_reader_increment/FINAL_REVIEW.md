# Independent review — native P10 reader

**Decision: A — the native P10 reader source is accepted for the next bounded G1 source-preparation increment.** This accepts only this source slice for that next preparation step. It does not approve G1 or report Stage A, S1, or Round 3.7 as passing.

The fixed root/P1/P3/P10 path walk, relative opens, requested access/share profiles, handle-derived identity and descriptor comparisons, bounded canonical-byte read, repeated read, final identity checks, typed failures, and reverse handle cleanup match the accepted Stage A P10 contract. The source uses the accepted Windows SnapshotSession native primitives and does not call the snapshot-only restrictive share profile for P10.

All 38 Sol manifest rows independently matched. An isolated reviewer MSVC x64 build and rerun succeeded with 795 synthetic checks. The reviewer executable is separate from Sol’s evidence. Its PE differs from Sol’s same-sized PE at two four-byte timestamp fields only; see [BUILD_AND_PROVENANCE.md](BUILD_AND_PROVENANCE.md).

Every file ID, descriptor, final path, approved byte seal, and expected volume record in this review is source/configuration behavior or synthetic test input. No protected P10 file was opened. The test’s production-backend constructor call establishes link retention only; it does not establish live handle, ACL, share, token, or filesystem behavior. P10 reader integration with `ProtectedAuthorityReader`, actual A2 token-derived identity, G2 sealed configuration provenance, actual P10 identity/descriptor readback, and authorized G2/G3 observations remain separate work.

The code compares only the content and identity observed at its read/metadata points. Its general profile allows `FILE_SHARE_WRITE`; repeated reads and no delete sharing do not prove continuous content stability or defeat a pre-existing writable mapping. Those limits are consistent with the accepted contract and are stated in [CONTENT_STABILITY_AND_FAIL_CLOSED.md](CONTENT_STABILITY_AND_FAIL_CLOSED.md).

No Sol source, prior review, historical evidence, accepted SnapshotSession/Authority Binding source, frozen tests, runbook, checklist, or production S1 file was edited. No protected object, broker, or host security operation was exercised.
