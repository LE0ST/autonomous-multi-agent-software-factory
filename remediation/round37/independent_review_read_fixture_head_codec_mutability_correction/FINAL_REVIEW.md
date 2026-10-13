# Focused differential review — result immutability

## Decision A — CORRECTION ACCEPTED

The prior `ResponseValidation::verified_p11()` alias defect is closed. The accessor returns an owned `std::string`; its stored state is private and immutable; copy/move construction preserves the validated bytes; and assignment cannot replace a validated object's state. I found no equivalent ordinary public API bypass and no security-relevant regression in the focused change.

I independently rebuilt the complete pure codec suite with MSVC x64. It passed **577 checks**, exit 0. A separate reviewer probe passed **16 active/terminal isolation, copy, and move checks**. The forged-constructor probe failed with the intended C2248, and the prior alias probe failed with C4238 promoted to C2220 under `/W4 /WX`.

The exact request/error/active/terminal literals remain 64/66/365/366 bytes and match the controlling design byte-for-byte. All 64 correction-manifest rows match. Of the original 51 codec-manifest records, 49 are unchanged and match; only the intended header and positive test records changed.

This accepts the bounded pure codec/correlation slice only. It does not authorize native pipe transport, prove native peer authentication or custody, approve G1, or change status: G1 HOLD / UNAPPROVED; S1 OPEN; Stage A and Round 3.7 NOT PASSED.

Evidence and detailed reasoning are in the accompanying API, special-member, exception, build, and hash reports. Reviewer-owned build artifacts are under `build_msvc_x64/`.
