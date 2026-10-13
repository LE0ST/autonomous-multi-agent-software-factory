# Two-case P11 commissioning contract

This is an exact proposed G1 lifecycle, not authorization to provision. It preserves the one accepted P11 path and the already frozen case content. The case selector is never a request field.

## Shared immutable assignment

P10 is created and sealed once before the first service start. Its canonical schema and digest map contain both accepted cases and do not change between them. The independently approved P10 digest is the binding value in each P11 record and each wire request. No runtime endpoint observation is inserted into P10.

For each case lifetime, the authorized provisioner creates a new immutable P15 selected-case record containing the fixed run ID, P10 digest, that case's exact ID and independently established expected P11 SHA-256. P15 is created by BA with `CREATE_NEW` at the fixed protected config path, protected DACL granting only SY/BA full access and C/B read-only access, W absent. The current case's P15 is the trusted configuration input to both A2 and A3. P14 contains no case ID or P11 seal.

## Ordered lifecycle

### Lifecycle 1: `spent-budget-active`

1. G2 verifies the fixed roots/parents and P10 creation/readback, actual SID/image values, and approved manifests. No pre-existing P11 is adopted.
2. BA provisioner creates only the exact active canonical P11 bytes at `C:\S1PF_260926_A\store\authority.db` with CREATE_NEW and the accepted protected descriptor. It derives the expected SHA-256 from the independently frozen active literal bytes, reads back the same held file, and requires exact 299-byte equality, expected active P10 linkage/case fields, matching digest, identity and descriptor before sealing the active P11 creation record. It must not make the observed file itself the source of its expected hash.
3. BA creates P15 for `spent-budget-active` with that independently read-back P11 seal. A2 and A3 load/verify this same P15 generation and independently compare it to frozen source expectations. No request can alter it.
4. Start A3 under B only after static P10/P15 and P11 checks are complete. A3 installs the minimal process-object C query ACE before service RUNNING, creates exactly one first-instance message-mode pipe, emits the startup event and retains the returned server handle. BA collector verifies live endpoint facts and creates/readbacks active P14. If any check fails, no comparison attempt is run.
5. Each separately authorized active-case comparison attempt uses one fresh A2 nonce and one new one-request connection. The frozen active latest, old-restore and delete-all cases remain distinct comparison outcomes; each operator-authorized attempt gets its own connection/nonce. No writer result triggers another request.
6. End the active case lifetime: stop the relevant assigned A2/A3 services under separate authorization, close all client/server/process/P14/P15/P11 handles, verify no retained first-instance handle/process remains, and collect final protected evidence. Mark active P14 invalid, then remove/quarantine P14 and P15 by their recorded creation file IDs. The active P11 seal ceases to be an expectation for any later request.
7. Under the separately approved case-transition/reprovision operation, remove the active P11 by its exact recorded ID after the services stop and evidence is sealed. No name-based deletion/adoption is permitted.

### Lifecycle 2: `spent-budget-terminal`

8. Verify active P11/P14/P15 are absent or quarantined by exact ID and the prior services/handles are closed. Reverify fixed P10 and all common protected parent identities. Any mismatch returns to G1.
9. BA creates only the terminal canonical P11 at the same fixed P11 path with CREATE_NEW. It derives the expected SHA-256 from the independently frozen terminal literal bytes, then requires exact 300-byte readback equality, terminal P10 linkage/case fields, matching digest, and records the new file identity/descriptor. The observed file does not define its own expected seal.
10. BA creates a fresh terminal P15 with the terminal case ID and new seal. A2 and A3 independently load the same terminal P15 generation. The active P15/seal is invalid and may not be reused.
11. Start a new A3 process/first-instance lifetime. It must receive a new process creation time, server PID evidence, ETW endpoint event and endpoint generation. BA collector creates/readbacks a new terminal P14. No active P14, PID/start record, pipe handle, selected-case record or P11 seal carries forward.
12. Each separately authorized terminal-case comparison attempt uses one new connection and nonce. The terminal latest, old-restore and delete-all outcomes remain separate; no request field changes the preselected terminal case.
13. Stop/close the terminal case lifetime and preserve records. Any later teardown is a separate G5 authorization.

## Stop and transition rules

- No concurrent case transition, service restart or P11 replacement is permitted during an authorized comparison attempt.
- Service/process exit or original first-instance-handle loss invalidates its P14 and the current exchange. Automatic restart is prohibited. A replacement service must use a new P14 generation after separate authorization.
- P15 and P14 are different resources with different authority: P15 carries the trusted case choice/seal; P14 attests live endpoint facts only. P14 cannot select P11, and P15 cannot attest a running process.
- P12 remains only the fixed positive-control copy. It is never a second head, fallback, recovery source or substitution for P11.
- No old P11/P14/P15 is accepted just because its bytes or PID match; each use requires current generation, expected IDs/seals and the correct lifecycle.

This sequencing gives the accepted active case first and terminal case second. It does not provision accounts, services, ACLs, P11, P14 or P15 as part of this design task.
