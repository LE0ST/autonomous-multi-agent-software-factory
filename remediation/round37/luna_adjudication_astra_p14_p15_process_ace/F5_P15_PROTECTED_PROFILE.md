# F5 — P15 creator/readers and P14 final observations

This extends the accepted protected identity/read method to the new protected records. P14/P15 are protected creation identities, not mutable SnapshotSession children. Do not import complete directory inventory or replacement-ID tolerance.

## P15 creator (BA provisioner)

1. Retain the already verified root/P1/P3 directory handles. Verify P3 parent identity and that the one-component child `selected-case.json` is absent. The only path component is fixed by source; no record/request/environment field selects it.
2. Build the exact protected descriptor at creation: owner/group BA; protected DACL `D:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;0x00120081;;;C)(A;;0x00120081;;;B)`, with actual resolved role SIDs and no inherited/extraneous ACE. The P15 DACL rights are exactly data/read-attributes/READ_CONTROL/SYNCHRONIZE for C and B; no write/delete/WRITE_DAC/WRITE_OWNER. Verify owner/group/full DACL/control/protection after creation.
3. Relative `NtCreateFile`: `OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE`; `DesiredAccess = FILE_WRITE_DATA | FILE_READ_DATA | FILE_READ_ATTRIBUTES | READ_CONTROL | SYNCHRONIZE | DELETE`; `ShareAccess = FILE_SHARE_READ`; `CreateDisposition = FILE_CREATE`; `CreateOptions = FILE_NON_DIRECTORY_FILE | FILE_SYNCHRONOUS_IO_NONALERT`; provide the descriptor in `OBJECT_ATTRIBUTES`; no inheritance. `DELETE` is creator-handle cleanup authority only and is not granted to C/B by the object DACL. No overwrite, reopen, backup/restore privilege, or wider-share fallback.
4. Write exactly the canonical P15 bytes; flush; query size/type/reparse/identity/descriptor; read the exact byte count to EOF; compare byte-for-byte with independently rendered expectations; repeat a complete same-handle read and compare again. Capture final path, volume identity/serial, 128-bit file ID, verified parent ID, owner/group/full DACL and protection. Close only after all checks succeed. This close after complete readback is the publication commit point.
5. On any failure, mark exact-handle deletion and verify the pathname absent after cleanup. If deletion/absence cannot be proven or the process crashes leaving a name occupant, stop; never adopt or overwrite it. P15’s actual creation ID/seal/generation is retained in BA’s administrative evidence.

## P15 A2 and A3 reader profile (identical child profile)

Both readers traverse held verified ancestors to the fixed single child `selected-case.json`, use `OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE`, `FILE_OPEN`, `FILE_NON_DIRECTORY_FILE | FILE_SYNCHRONOUS_IO_NONALERT | FILE_OPEN_REPARSE_POINT`, and exact desired access `FILE_READ_DATA | FILE_READ_ATTRIBUTES | READ_CONTROL | SYNCHRONIZE`. Both use `FILE_SHARE_READ` only. No reparse, device, directory, alternate stream, unsupported object, name reopen, privilege fallback, or delete-sharing is accepted.

At the fixed run `260926_A`, size must be exactly 308 bytes for active or 310 bytes for terminal. Each independently:

- validates volume identity/serial, 128-bit file ID, final normalized path, parent file ID, regular-file type, non-reparse state, owner BA/group BA, complete protected DACL/control state, and exact resolved descriptor;
- reads the full bounded file to EOF, validates exact canonical P15 bytes/schema, and compares `run_id`, P10 SHA-256, selected-case ID, and P11 SHA-256 to explicit trusted P10/frozen-case/P11 expectations; generation is an opaque value and never chooses the case;
- performs a second complete read and exact byte comparison before use; retains all ancestor and child handles without reopening by name.

A2 retains P15 and its verified parent through the one request/response and final acceptance check. A3 retains P15 and ancestors for the service lifetime, rechecks held-object identity/descriptor/content before each P11 read and before response, and never loads another P15 generation in-process. There is no A2/A3 profile difference in rights, share, parsing, descriptor, or identity checks. The separate lifetime of the child handle is the only difference.

The same BA-created fixed object is read by both principals during one O7 case lifetime. Since both use no-delete/no-write compatible read handles and commissioning excludes transitions while either reader/attempt remains live, a replacement cannot create a second admitted selection. P15 is not an IPC case selector and never authenticates the endpoint.

## Common protected-record observation method; P14-specific schedule

For P14, retain verified ancestors and the fixed `endpoint-evidence.json` child. A2 opens relative to P3 with `OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE`, `FILE_OPEN`, `FILE_NON_DIRECTORY_FILE | FILE_SYNCHRONOUS_IO_NONALERT | FILE_OPEN_REPARSE_POINT`, desired access `FILE_READ_DATA | FILE_READ_ATTRIBUTES | READ_CONTROL | SYNCHRONIZE`, and `FILE_SHARE_READ` only. Apply the F2 8192-byte bound before parsing.

P14/P15 reads use protected-record observations, not mutable-inventory semantics:

1. Before admitting the record, query and validate held-handle type/reparse, parent and leaf IDs, volume, final path, owner/group/full descriptor/control flags and exact size.
2. Read the complete declared size plus EOF; require exact canonical bytes and independent expectation comparisons.
3. Repeat the complete read on the same handle and require exact equality.
4. Immediately before returning any A2 success, perform a final complete read of P14 and P15, recheck identity/descriptor/path/size and the live pipe/process observations. Require byte equality with the pre-request reads. Recheck once after P11 is read and before A3 sends its sole response.

Any failed query, short read, growth/shrinkage, content/hash mismatch, identity/descriptor drift, reparse/type mismatch, access/share conflict, or missing final observation is `STOP_INCONCLUSIVE`. No fallback to pathname-only identity, an observed-as-expected seal, or the mutable snapshot share profile is permitted.

## What the profile does not claim

The share mask and repeated reads are not a proof against privileged BA/SY mutation, arbitrary pre-existing writable mappings, kernel compromise, or malicious code inside the trusted A3 process. BA/SY and the pinned service are inside the stated trust boundary. Actual IDs, descriptors, seals, ACL effectiveness, and successful reads remain G2 observations.
