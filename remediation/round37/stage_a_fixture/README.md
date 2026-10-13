# Minimum disposable Stage A fixture: first source slice

Status: isolated source and synthetic tests only. This directory is not a provisioner, service, pipe server, launcher or live probe. It does not modify installed S1. G1 remains unapproved.

## Source boundary

`src/contracts.*` owns P10 template/render rules, P11 marker/head rendering, frozen active and terminal fixture bytes, canonical mutable-set SHA-256, the strict M4 data-only decoder, typed decisions and raw-evidence fields. `src/snapshot.*` owns the fresh-controller comparison sequence and a mockable session interface. `tests/contracts_test.cpp` supplies only synthetic sessions; it cannot open a Windows state directory or dispatch a broker verb. These units preserve the future A1 mutable input, A2 comparison/parser and A3 protected-head boundary without implementing their processes.

The snapshot port's native implementation must open the verified directory and all present regular children with the exact `FILE_SHARE_READ` profile, keep those handles plus verified ancestors through the final comparison, read through the held child handles, repeat complete inventory and identity/content validation, and report raw native errors. The general protected-object identity/read profile has a different share mode and is never a snapshot fallback. G1 source review and G3 native evidence must examine actual sharing and mapping behavior. The requested share flags alone do not prove a stable snapshot against every pre-existing writable handle or mapping.

The C++ source and synthetic tests are included as research artifacts. Complete public native build and fixture-commissioning instructions are pending; reviewed build evidence exists in the research lineage, but host commissioning remains G1/G2/G3 work. Any locally built executable is a test binary, not a Stage A service or production artifact.
