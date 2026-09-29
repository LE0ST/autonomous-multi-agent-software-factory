# Independent corrected-slice review

**Decision: A — Corrected pure slice accepted for the next isolated Windows `SnapshotSession` source increment.**

The two earlier source findings are closed in `compare_impl()` (the implementation behind `compare_fresh_controller()`). P11 hashing is inside its typed observation-failure path. The final mutable-set digest is completed before `snapshot_complete` becomes true. Fault injection checks both failures return `STOP_INCONCLUSIVE`, leave the snapshot incomplete, and identify the expected object, profile, and step. Completed old-set and deletion comparisons still occur only after successful complete observation and digesting.

The fixture test oracle now independently asserts literal active and terminal old/latest bytes, each child SHA-256, and all four complete-set digests. The parser and failure cases requested by the prior review are present. The test counter increments at each executed `require()` assertion; independent reviewer reruns completed 133 counted checks under both MinGW and MSVC x64. The runs had identical 3,415-byte stdout and exit code 0.

All entries in `CORRECTION_SHA256.txt` recomputed successfully, including the preserved original 78-check executable/output and all four prior review documents. Reviewer executables, logs, and outputs are isolated under this package's `reviewer_build_mingw/` and `reviewer_build_msvc/` directories. Neither the fixture nor historical evidence was changed.

This accepts only the corrected pure source/test slice as the basis for one isolated read-only Windows `SnapshotSession` source increment. The current seam is synthetic: it does not prove native enumeration, Windows sharing, handle identity, process/token separation, live request isolation, or native denial. The default-zero dispatch counter was removed and is not presented as live evidence. This decision is not G1 approval, Stage A PASS, S1 PASS, or Round 3.7 PASS.

See [SOURCE_FINDING_CLOSURE.md](SOURCE_FINDING_CLOSURE.md), [DUAL_TOOLCHAIN_VERIFICATION.md](DUAL_TOOLCHAIN_VERIFICATION.md), and [NEXT_NATIVE_SOURCE_SCOPE.md](NEXT_NATIVE_SOURCE_SCOPE.md).
