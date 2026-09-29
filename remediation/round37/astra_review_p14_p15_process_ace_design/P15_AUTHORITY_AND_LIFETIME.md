# P15 authority, P11 relation and case lifetime

## Resource and exact schema

The [manifest P15 row](../read_fixture_head_design_delta_after_luna_b/G1_MANIFEST_DELTA_PROPOSAL.md) specifies fixed `C:\S1PF_260926_A\config\selected-case.json`, created by BA provisioner, owner/group BA, and:

```text
O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;0x00120081;;;C)(A;;0x00120081;;;B)
```

SY/BA have full access; C/A2 and B/A3 have read-data, read-attributes, READ_CONTROL and SYNCHRONIZE. W has no ACE. The record is created once per case with handle-relative NtCreateFile/FILE_CREATE; collision is not permission to adopt or overwrite. The proposal does not yet give P15 the complete creator/reader argument and retention profile that it gives P14 (F5).

Exact ordered compact UTF-8 JSON, without BOM, LF, extra whitespace, unknown or duplicate properties:

```text
{"schema_version":1,"run_id":"<P10 run_id>","p10_sha256":"<64 lowercase hex>","selected_case_id":"spent-budget-active|spent-budget-terminal","selected_p11_sha256":"<64 lowercase hex>","selection_generation":"<32 lowercase hex>"}
```

The bar denotes two alternatives; it is not literal data. At the fixed run ID `260926_A`, the canonical active form is 308 bytes and terminal form is 310 bytes. Those sizes are derived from the exact grammar, not newly selected transport limits. Source may reject every other encoding without deciding a new authority policy. Generation is an opaque 16-byte value encoded as 32 lowercase hex; its provisioning and current-lifecycle comparison are separate from parsing.

## Field provenance

| Field | Authorized source | Required comparison / forbidden substitution |
| --- | --- | --- |
| schema_version | Reviewed schema constant 1 | Reject other schema; do not negotiate from a response. |
| run_id | Independently validated P10 assignment | Exact fixed run; no caller-selected alternate run. |
| p10_sha256 | Independently sealed provisioner-rendered P10 | Compare to the trusted P10 seal. A P15 string cannot establish the P10 expectation by itself. |
| selected_case_id | Separately authorized operator/provisioner choice of the frozen active or terminal case, in the prescribed order | A2/A3 independently compare to frozen case definitions and the current approved selection. No request parameter or ordinary A2 caller payload can switch it. |
| selected_p11_sha256 | Frozen case rendering with the independently trusted actual P10 digest, checked against authorized P11 creation/readback | Must agree with the selected canonical case and protected P11. Hashing observed bytes alone cannot establish the expectation. |
| selection_generation | Authorized provisioner for this P15/case lifetime | Fresh lifecycle identifier; no request/response/M4/M5 source. Exact allocation/reuse/current-generation rules remain F3. |

A1/M4/M5 cannot originate any field or provide a fallback. A prior A3 response cannot update P15. A2 is a verifier/consumer, not the provisioner. A3's accepted custody reader has no request-supplied path, case or hash. These exclusions are explicit in [endpoint separation](../read_fixture_head_design_delta_after_luna_b/ENDPOINT_EVIDENCE_CONTRACT.md), [manifest](../read_fixture_head_design_delta_after_luna_b/G1_MANIFEST_DELTA_PROPOSAL.md), [commissioning](../read_fixture_head_design_delta_after_luna_b/TWO_CASE_COMMISSIONING_CONTRACT.md) and [authority adjudication](../independent_review_read_fixture_head_design_adjudication/OBSERVATION_ACCESS_MAP.md).

This proves the proposed direction of authority; it does not prove that future native producers/readers enforce it. An API accepting ordinary values may expose a pure comparison seam, but cannot label caller data as trusted production configuration without the protected provenance boundary.

## P11 expectation is not self-sealing

Commissioning steps 2 and 9 independently render the frozen active/terminal P11 using the actual trusted P10 linkage. They derive the expected digest from those expected bytes, then compare the held created P11's exact 299/300 bytes, fields, digest, identity and descriptor. P15 receives that case's independently checked seal. The manifest's shorter phrase “P11 readback seal” must be read with those explicit requirements; it is not permission to hash arbitrary observed P11 and trust the result.

The accepted [P11CustodyConfig](../stage_a_fixture/src/windows_p11_custody.hpp) separately requires root/P1/P4/P11 metadata, selected frozen case, rendered P10 SHA-256 and P11 SHA-256. Its [reader](../stage_a_fixture/src/windows_p11_custody.cpp) compares the complete frozen case, canonical rendering and expected hash before protected file access, then exact bytes/digest and repeated content/identity observations. P15 must supply or bind to that already-required trusted configuration; its six fields do not replace the P11 metadata.

## F3: content binding versus file-instance binding

The selected case plus P10 digest determines the expected P11 content and seal. It does not determine P11's creation file ID or volume/parent identity. Two files can have the same correct bytes and digest while being different creations. Similarly, a new selection generation written into a file is not evidence, by itself, that the consumer has the approved current generation.

The [commissioning stop rules](../read_fixture_head_design_delta_after_luna_b/TWO_CASE_COMMISSIONING_CONTRACT.md) already require current generation, expected IDs/seals and the correct lifecycle. The native binding/delivery contract must say where those expected IDs and the current-generation decision come from, how both A2 and A3 obtain the same admitted P15, and when that admission ends. It may use explicitly trusted G2/lifecycle inputs as the accepted P10/P11 readers do; implementing an isolated reader need not wait for actual host IDs. It may not use the newly observed object's ID as its own independent expectation.

The missing binding is an authorized association of:

- approved P10/run and frozen case selection;
- P15 creation identity, canonical seal and selection generation;
- selected P11 creation identity, protected parent chain and independently derived seal;
- the A2/A3 lifecycle admitted to use that selection;
- the separately observed P14 identity/endpoint generation for that lifecycle.

This is a required relationship, not a demand to add all these fields to P15 or P14, create another file, expose E1, or use a particular IPC mechanism. Preserve P14's lack of case authority. Luna must choose and freeze the trusted association/delivery and retirement contract.

## Adversarial P15/P11 cases

| Case | Required result / evidence |
| --- | --- |
| Selected case ID says active but digest is terminal | Reject against independent canonical selected-case rendering. No P11 read or request-based case switch repairs it. |
| Active P15 retained for terminal, or terminal P15 used for active | Current authorized selection/generation and stopped-lifetime rules must reject it. Parsing a valid case name alone cannot detect the wrong lifecycle. |
| Correct case/hash but P11 replaced at same path | Accepted P11 creation metadata must reject a new file ID. Content equality is insufficient. |
| Old digest reused after legitimate same-content reprovision | Digest reuse can be mathematically correct; the new file identity and selection/lifetime must still be separately authorized. Do not require a digest to change merely because an object was recreated. |
| Old P15 bytes recreated at its path | Reject absent current approved creation identity/generation. Random-looking generation bytes are not provenance. |
| P15 remains open while transition starts | No transition during an attempt; stop admission, finish/abort attempts, close relevant handles, retire selection, then exact-ID removal. Failure to close/verify stops transition. |
| Observed P11 bytes define expected P15 hash | Forbidden self-seal; reject before publication even if the bytes are well formed. |
| A2 caller supplies case/hash as “trusted” data | Acceptable only in an explicitly synthetic/pure boundary; cannot establish production authority. Native provenance must be separate and enforced. |

## Case sequence and its limits

The chosen order is already explicit; it is not open policy:

1. Independently create/read back active P11, then active P15.
2. Start A3 only after required static checks; the BA observation session must already be established as required by endpoint §3.
3. Complete process-ACE/pipe startup observations and create/admit active P14; run only separately authorized active attempts.
4. Stop admission and the relevant A2/A3 lifetimes, close fixture handles, invalidate and exact-ID remove/quarantine P14/P15; exact-ID remove active P11 under separate authorization.
5. Verify the old lifetime/resources are retired, reverify common protected parents/P10, create/read back terminal P11 and fresh terminal P15.
6. Start a new A3/first-instance lifetime; create new terminal P14; run terminal attempts, then close and preserve evidence.

This summarizes [commissioning steps 1–13](../read_fixture_head_design_delta_after_luna_b/TWO_CASE_COMMISSIONING_CONTRACT.md); it does not authorize execution or change the order.

There is one selected P11/P15 at the fixed paths and one admitted endpoint lifetime at a time. Exact-ID quarantine can retain old evidence outside the live names; physical coexistence of quarantined evidence is not simultaneous authority. Automatic restart, overlapping admitted generations, live P11 replacement, late admission during transition and surviving original pipe instances are prohibited.

The requirement to verify no retained handle/process remains must be scoped to the controlled fixture lifetimes and owned handles, including collector handles. It is not a basis for inventing global handle enumeration, handle-duplication rights or a claim about every system handle. Process termination and releasing the observer's own process handle are distinct obligations. F3 must make the ownership/closure barrier and failure result explicit.

## Failure behavior

Absent, inaccessible, malformed, noncanonical, mismatched, stale or unadmitted P15 means STOP_INCONCLUSIVE before privileged read/attempt. P11 identity/descriptor/content mismatch produces no authenticated head. Failure to complete closure or exact-ID cleanup stops the transition; it does not permit overwriting, adoption, a name-based delete, terminal startup alongside active, or a P12 fallback. A partially created record is recorded residue until separately authorized cleanup.

The desired failures are already conservative. F3/F5 supply the missing enforceable admission, binding and reader rules. The pure six-field syntax remains independently implementable without resolving how the provisioner allocates generations.
