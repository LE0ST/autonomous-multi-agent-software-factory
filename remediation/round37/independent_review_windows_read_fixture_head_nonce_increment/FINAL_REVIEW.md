# Independent review — A2 `ReadFixtureHead` nonce generator

## Decision A — ACCEPTED BOUNDED SOURCE SLICE

The source implements the frozen one-call nonce policy. A production invocation has no caller inputs and calls the fixed BCrypt function once through a private helper with null algorithm handle, a 16-byte local `Nonce`, and `BCRYPT_USE_SYSTEM_PREFERRED_RNG`. It returns the opaque bytes only for a successful NTSTATUS. Failure, including a provider throw at the test seam, produces typed incomplete with no nonce. I found no retry, fallback, alternate RNG, transformation, or test-provider path in the production object.

Independent checks: the deterministic suite passed **68 checks**; my separate provider-fault probe passed **40 checks**, including zero/partial/full buffer writes followed by failure and exceptions after partial writes; the authorized native-local test printed **5 checks passed** after one production generator call; the accepted codec regression passed **577 checks**, exit 0. The public API and test seam negatives failed for their intended reasons. Production imports `BCryptGenRandom` from `bcrypt.dll`; the production object contains no test-seam symbol.

The nonce manifest matched **60/60** rows with no duplicates, missing files, mismatches, or unlisted scoped payload files. The preceding codec-correction manifest remains unchanged and matched **64/64** rows.

This accepts only the nonce-generator source slice. It does not authorize P14/P15, a pipe, endpoint evidence, another source increment, or host security work. G1 remains HOLD / UNAPPROVED; S1 OPEN; Stage A and Round 3.7 NOT PASSED.

The reviewer build and probes are preserved under `reviewer_build_msvc_x64/`. No implementation source was changed.
