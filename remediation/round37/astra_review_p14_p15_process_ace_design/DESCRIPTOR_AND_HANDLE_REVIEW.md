# Descriptor and handle-relative access review

## File descriptors and least privilege

Proposed in [endpoint §2](../read_fixture_head_design_delta_after_luna_b/ENDPOINT_EVIDENCE_CONTRACT.md) and [manifest P15 row](../read_fixture_head_design_delta_after_luna_b/G1_MANIFEST_DELTA_PROPOSAL.md):

```text
P14: O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;0x00120081;;;C)
P15: O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;0x00120081;;;C)(A;;0x00120081;;;B)
```

`C` and `B` here are proposal placeholders for the independently created actual SIDs, not literal SDDL aliases. SY and BA are well-known principals. The full protected descriptor must be resolved and compared; a string containing an unresolved role is not an executable descriptor.

| Right/property | P14 | P15 | Review |
| --- | --- | --- | --- |
| FILE_READ_DATA | C | C and B | Needed to read the respective record. |
| FILE_READ_ATTRIBUTES | C | C and B | Needed for identity/type/reparse checks. |
| READ_CONTROL | C | C and B | Needed for each reader's owner/group/DACL verification. Removing B's right would defeat the proposed independent A3 P15 check. |
| SYNCHRONIZE | C | C and B | Required by P14's FILE_SYNCHRONOUS_IO_NONALERT profile; coherent for the analogous P15 profile, which must be made explicit. |
| Write/delete/WRITE_DAC/WRITE_OWNER | Neither C nor B | Neither C nor B | Not granted by `0x00120081`. SY/BA remain trusted full-access principals. |
| Protected DACL | D:P | D:P | No inherited ACEs or inheritance flags are selected. Verify actual protection and complete ACE set; do not infer it from the parent. |
| Owner/group | BA/BA | BA/BA | Coherent with administrative provisioning; not automatic merely because the creator belongs to BA. Readback must match, or stop. |

GetSecurityInfo requires READ_CONTROL to obtain owner/group/DACL. See [Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo). FILE_SYNCHRONOUS_IO_NONALERT requires SYNCHRONIZE. See [NtCreateFile](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/nf-ntifs-ntcreatefile). These are verification/operation rights, not aesthetic extras.

The selected file-right masks are coherent. Effective-access claims still assume the prescribed C/B/W account memberships and privileges; “B absent from P14” is an ACE statement, not an observed denial for an arbitrary token. No backup/restore/debug privilege or permissive fallback may be inferred. The accepted [creation identity contract](../s1_g1_design_corrections_after_independent_review/FILE_IDENTITY_AND_PROBE_CONTRACT.md) explicitly requires naming/checking any privilege needed to establish BA ownership and stopping on failure. This is not authority to modify a preexisting descriptor.

File DACL syntax is substantially specified: exact principals, masks, protection and no inheritance. Source still needs a consistent semantic comparison/serialization convention. This is especially material to P14's embedded SDDL byte strings (F2) and process baseline transformation (F1). SDDL text equality must not accidentally accept extra ACEs or reject/normalize a distinct security policy as merely a spelling variant.

## Accepted protected readers are the relevant comparison

The [P10 config/interface](../stage_a_fixture/src/windows_p10_reader.hpp) takes trusted root/P1/P3/P10 metadata, canonical bytes and SHA-256. The [P11 config/interface](../stage_a_fixture/src/windows_p11_custody.hpp) takes trusted root/P1/P4/P11 metadata, frozen selected case, P10 digest and P11 digest. Their source binds the opened object to those expectations, performs bounded complete reads, compares canonical bytes/hash, repeats content observation and rechecks held identities.

Both accepted protected child profiles use FILE_SHARE_READ | FILE_SHARE_WRITE, without FILE_SHARE_DELETE: [P10 profile and read](../stage_a_fixture/src/windows_p10_reader.cpp), [P11 profile and read](../stage_a_fixture/src/windows_p11_custody.cpp). P14 explicitly selects FILE_SHARE_READ only. That narrower P14 share profile is a proposed operation-specific choice, not a contradiction or permission to alter the accepted P10/P11 sources. P15 has no equally complete share row yet. Do not infer its profile from a similarly named snapshot function.

## Check-by-check classification

“Required” below means explicit in the proposed boundary or an existing accepted identity constraint it depends on. “Necessary consequence” is an enforcement obligation, not permission to choose an unspecified API policy.

| Check | Classification and rationale |
| --- | --- |
| Verified volume/root, P1 and P3 handles kept through protected access | Required by the inherited protected identity model; a verified leaf reached through an unverified/replaced parent is insufficient. |
| Single-component fixed child, relative to verified parent | Explicit for P14 and intended for P15. Neither record may supply its own lookup path. |
| OBJ_DONT_REPARSE and reparse rejection | Explicit for P14; required no-follow identity behavior for P15. Freeze P15's exact flags in F5. |
| FILE_OPEN_REPARSE_POINT on protected reader | Explicit P14 and consistent with accepted protected readers. It permits leaf inspection without normal reparse traversal. Together with OBJ_DONT_REPARSE and rejection it is the chosen profile; this does not prove every flag is independently indispensable to every possible no-follow implementation. Do not copy every reader option into FILE_CREATE. |
| FILE_CREATE for creation, FILE_OPEN for reads | No overwrite/adoption; creation success alone is not final validated publication. |
| Final normalized path, parent ID, volume GUID/serial, 128-bit file ID | Required inherited creation-record identity. A hash, serial or path alone is insufficient. The P14 image-volume field is not a substitute for metadata of P14 itself. |
| Owner/group, full DACL/control/protection/type/reparse metadata | Required per-object comparison; the parent's ACL or requested creation SDDL is insufficient. |
| Retain opened child and ancestors; no unchecked path reopen | Required to bind use to observation. P14 explicitly retains through exchange; P15's retention window must be fixed relative to admission/attempt/lifecycle. |
| Complete bounded content, EOF/size consistency, canonical bytes/seal | Necessary for a trusted finite record; partial successful reads cannot become evidence. P15 bounds derive from its exact grammar; P14 bound needs F2 correction. |
| Repeated content and final held-identity observation | Existing P10/P11 protected-read pattern; appropriate to carry forward explicitly or replace only with a reviewed stability argument. P14/P15 text does not currently freeze the exact observation schedule. F5 must do so. A sharing flag is not by itself a proof of every possible content change being impossible. |
| Full directory inventory, all mutable-state children retained and compared | Not required for these fixed single-child protected records. This belongs to SnapshotSession's complete mutable-state set. |
| Accept a different file ID because mutable files may legitimately be replaced | Forbidden here. These are protected creation identities, unlike the accepted mutable-state child-ID rule. |
| C direct access to E1, P6 data, SCM or A3 token | Not implied. The design chooses protected delegated evidence for those observations. |
| New signatures, permanent replay store, additional broker privileges | Optional architecture changes, not deductions from file identity rules. Not selected by this review. |

The underlying [identity contract](../s1_g1_design_corrections_after_independent_review/FILE_IDENTITY_AND_PROBE_CONTRACT.md), sections “Executable path-to-object binding” and “Fresh-controller complete mutable-state snapshot profile,” expressly distinguishes protected-object sharing from mutable snapshot sharing. Its original every-object list covers P1–P13/E1; the P14/P15 delta must expressly extend the relevant identity obligations, not claim the earlier list already named the new resources.

## F5: exact native profile still needed

For P15, freeze creator desired access/share/options/descriptor-at-creation and flush/readback/publication; reader desired access/share/options; root/parent opening and checking; bounded reads and final observations; handle retention and closure; and identical case/seal/generation validation obligations in A2/A3. The current row's FILE_CREATE and “immutable handle-relative” wording does not determine all these security-relevant behavior choices.

For P14, most native arguments are already fixed. Clarify final/repeated identity/content observations and publication/current-lifecycle input delivery (F3), then reconcile the cap/canonical descriptor encoding (F2). There is no reason to reopen its fixed name, C read-only mask, no-follow child or no-update rule.

For both, failure to obtain the prescribed rights or observations must be STOP_INCONCLUSIVE with the failed stage/native error. Never fall back to name-only identity, a wider share mask, backup/restore privileges, a different path, observed-as-expected hashes or a response-supplied record. This follows the accepted fail-closed pattern; it does not establish any host denial here.
