# F1 — A3 process descriptor baseline and permitted delta

This contract supersedes only the conflicting proposed process-descriptor wording in `ENDPOINT_EVIDENCE_CONTRACT.md` and its corresponding process row in `G1_MANIFEST_DELTA_PROPOSAL.md`. It does not change service, file, pipe, token, or SCM rights.

## Accepted baseline

Before A3 changes its own process DACL, the actual process descriptor MUST satisfy all of the following:

1. Owner SID is the independently approved B SID; primary group SID is the same approved B SID.
2. The DACL is present, non-null, protected from inheritance, and contains no inherited ACEs.
3. Its complete ordered DACL consists of exactly these three explicit allow ACEs, with no object GUIDs, callback data, inheritance flags, deny ACEs, audit ACEs, or other ACEs:

   ```text
   (A;;GA;;;<SY SID>)(A;;GA;;;<BA SID>)(A;;GA;;;<B SID>)
   ```

   Here `<SY SID>`, `<BA SID>`, and `<B SID>` mean the independently resolved canonical SIDs, not SDDL aliases in the descriptor comparison.
4. There is no C ACE, including a deny ACE. There are no broad group, Everyone, Authenticated Users, Creator Owner, or other trustee ACEs. The accepted C token must not be a member of SY, BA, or B, and its effective groups/privileges must not grant additional process rights. These effective-token conditions remain a separate G2 check.
5. Control state is exact: `SE_DACL_PRESENT` and `SE_DACL_PROTECTED` are set; `SE_DACL_DEFAULTED`, `SE_DACL_AUTO_INHERIT_REQ`, and `SE_DACL_AUTO_INHERITED` are clear; `SE_SACL_PRESENT` is clear. Owner/group defaulted flags are clear. No SACL is present. This operation is not permission to repair owner/group or change the SACL.

Any mismatch—including a pre-existing C right, a group ACE that can grant C extra access, an inherited ACE, an unexpected deny, an unprotected/null DACL, or a different owner/group—fails closed before pipe creation and before `SERVICE_RUNNING`. Do not merge, preserve, normalize away, or replace an unexpected baseline.

## Exact transformation and final descriptor

The only permitted change is adding one explicit, non-inheriting C allow ACE granting exactly `PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE` (`0x00101000`). No other owner/group/control flag/SACL/ACE/right may change. The final ordered DACL is exactly:

```text
(A;;GA;;;<SY SID>)(A;;GA;;;<BA SID>)(A;;GA;;;<B SID>)(A;;0x00101000;;;<C SID>)
```

The DACL remains protected. ACE order is this exact sequence; the source must not rely on an OS serializer’s ACE reordering. Generic masks are expanded using the Windows process-object `GENERIC_MAPPING` for semantic comparison. The three `GA` ACEs must normalize to full generic process access for their exact trustees. The C mask must contain no generic bits and normalize to exactly `0x00101000`. Any extra effective bit is fatal.

The implementation changes only the DACL. It reads owner/group before and after and confirms byte-independent SID equality, exact control state, exact ACE sequence, and no SACL. A3 performs its own full readback. BA independently reads the same held process object before and after the change; it binds both observations to the same PID and `GetProcessTimes` creation time. A mismatch or inability to observe either state prevents pipe creation/publication and fails service startup.

## Independent observation order and startup barrier

Use the already proposed BA-owned ETW session as the synchronization path; do not create a new named event, pipe, file, or principal right. The A3 source registers the fixed provider and waits on its provider enable callback between startup phases:

1. BA starts/enables the fixed ETW provider and opens its consumer before service start. A3 registers the provider, reports `START_PENDING`, emits exactly one `PROCESS_READY_FOR_BASELINE` event (ID 2), and waits on an unnamed process-local event signaled only by its provider callback for the fixed BA session’s disable/enable pulse. It does not modify the descriptor or create a pipe. BA obtains the PID from `QueryServiceStatusEx` while the service is `START_PENDING`, opens/retains it with query/synchronize/`READ_CONTROL`, records its creation time with `GetProcessTimes`, and independently reads owner/group/DACL with `GetSecurityInfo` to verify the initial descriptor above. If SCM has not exposed a PID or any access/observation fails, no pulse is sent.
2. Only after the initial comparison succeeds does BA disable then re-enable the provider once. The callback pulse releases A3 to call `SetSecurityInfo` for the DACL-only change and perform exact local `GetSecurityInfo` readback. A3 advances its start-pending checkpoint, emits exactly one `PROCESS_DACL_FINAL` event (ID 3), and waits for the second BA disable/enable pulse.
3. BA independently calls `GetSecurityInfo` on its retained process handle, verifies the exact final descriptor and unchanged owner/group/creation time, and only then performs the second provider pulse. Only then may A3 create its first pipe instance and read back its descriptor.
4. A3 emits exactly one `PIPE_FIRST_INSTANCE_READY` event (ID 1) after successful pipe creation/readback, then reports `SERVICE_RUNNING`. BA validates the ordered three-event/two-pulse transcript, independent process/SCM/P6 facts and zero ETW loss, seals/stops the session, and only then publishes P14.

The provider callback accepts a pulse only when its `SourceId` is the fixed session GUID, the provider is already in the exact expected phase, and the observed transition is disable followed by enable. No second ETW session may be registered. If an event/pulse is missing, unexpected, duplicated, reordered, malformed, or received from a different process incarnation, if a checkpoint/PID/creation time changes, or if any comparison fails, A3 creates no later-stage resource and never reports `SERVICE_RUNNING`; BA publishes no P14. A3 accepts no client request before the final stage. Provider toggles are internal one-shot collector barriers, not message operations or A1/M4/M5 inputs. No retry or alternate signal path is added; native startup failure is typed and commissioning stops.

## Rights condition retained

The C process ACE is only a process-object prerequisite for the exact A2 observations. It grants no token-object access. G2 must separately prove that the actual C token cannot query B’s token under effective access. If C can query B’s token, reject this topology; do not edit the token DACL or add debug privilege.
