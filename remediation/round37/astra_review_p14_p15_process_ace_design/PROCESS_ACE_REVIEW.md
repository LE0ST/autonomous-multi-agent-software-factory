# Process-object C ACE review

## Finding

The mask `0x00101000 = PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE` is sufficient for the three proposed A2 observations on modern Windows. It is the minimum combination for those stated APIs. It is not an API allow-list and does not independently guarantee that C cannot query B's token. Installation semantics need F1 correction; no host descriptor or denial is asserted.

## API/access analysis

| Operation | Required access relevant here | Conclusion |
| --- | --- | --- |
| GetProcessTimes | PROCESS_QUERY_LIMITED_INFORMATION is sufficient on Vista and later. | `0x1000` suffices; no full query right needed. [Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes) |
| QueryFullProcessImageNameW | PROCESS_QUERY_LIMITED_INFORMATION or PROCESS_QUERY_INFORMATION. | Use the limited right. A Win32-path result must be compared under the fixed path contract; the record cannot choose a new image. [Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-queryfullprocessimagenamew) |
| Waiting for process termination | SYNCHRONIZE. | Needed for the retained process-handle liveness check. [Microsoft process access rights](https://learn.microsoft.com/en-us/windows/win32/procthread/process-security-and-access-rights) |
| OpenProcessToken | A process handle with PROCESS_QUERY_LIMITED_INFORMATION; requested token access is checked against the token descriptor. | The new ACE enables the process prerequisite. It does not itself grant TOKEN_QUERY. [Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-openprocesstoken) |

The process mask has no PROCESS_VM_READ, PROCESS_VM_WRITE, PROCESS_VM_OPERATION, PROCESS_DUP_HANDLE, PROCESS_TERMINATE, CREATE_THREAD, SET_INFORMATION, SUSPEND_RESUME, WRITE_DAC, WRITE_OWNER or READ_CONTROL bits. It does not confer general process control or memory/handle access. It does enable other limited-query APIs; “A2 calls only these three APIs” describes reviewed source behavior, not an operating-system restriction on C. These access-right distinctions follow the [Microsoft process-rights table](https://learn.microsoft.com/en-us/windows/win32/procthread/process-security-and-access-rights).

No unconditional escalation follows from these bits alone. Effective access also depends on other ACEs, group membership, privileges and already-held/inherited handles. The proposal may not assume that an exact C SID ACE is C's entire effective authority. The accepted separate W/C/B accounts, group/logon restrictions and no-debug assumption still matter. No live group, token, privilege or handle state was inspected.

## Token-object boundary

The sentence “A2 does not call OpenProcessToken” is insufficient as a least-privilege proof against arbitrary code running as C. The proposal correctly adds a separate condition: G2 must establish that the actual token DACL does not give C query access, and otherwise return the topology delta to review. See [endpoint contract §3, Minimal direct A2 process-object right](../read_fixture_head_design_delta_after_luna_b/ENDPOINT_EVIDENCE_CONTRACT.md).

That condition is feasible in principle: the process and token are different securable objects. There is no rule in the cited OpenProcessToken contract automatically adding a C token ACE when the process ACE is added. Conversely, denial must not be inferred from “no explicit C token ACE”: effective group grants and the actual calling context matter. A future gate must establish access under the actual C identity and preserve the accepted privilege restrictions. A token-query success is grounds to reject this topology proposal, not permission to repair or broaden token ACLs silently.

This review makes neither an empirical denial claim nor a claim that a suitable token descriptor already exists. The exact host token result is BLOCKED BY HOST EVIDENCE, while code that consumes an explicitly trusted descriptor/expectation need not wait for actual G2 SIDs.

## Installation: what is possible

A3 modifying its own process DACL is not inherently impossible. On current Windows, GetCurrentProcess supplies a pseudo-handle with PROCESS_ALL_ACCESS to the caller's process. Setting a DACL requires WRITE_DAC; reading it requires READ_CONTROL. This supports a local setup/readback implementation without assuming SeDebugPrivilege. See [GetCurrentProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getcurrentprocess), [SetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo) and [GetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo).

Do not infer that any desired owner/group is already present. Process default security comes from the creator's token context, not the executable file's ACL. Nor does changing a DACL establish permission to change owner/group. The proposal says preserve them; an unexpected owner/group must therefore stop rather than be repaired. A future helper must check every return/readback and must not request an unreviewed privilege or create a null DACL.

## F1: exact descriptor versus an unspecified preserved baseline

The [endpoint contract §3](../read_fixture_head_design_delta_after_luna_b/ENDPOINT_EVIDENCE_CONTRACT.md) proposes:

```text
O:<B>G:<B>D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GA;;;<B>)(A;;0x00101000;;;<C>)
```

It also says “no other ACE or right may change.” The [manifest process row](../read_fixture_head_design_delta_after_luna_b/G1_MANIFEST_DELTA_PROPOSAL.md) says to preserve all existing rights/owner/group and add no other ACE.

These rules can coexist only for a suitably constrained initial descriptor. The proposal does not state that prerequisite or prescribe the comparison when the baseline differs. Consider an existing C full-access ACE, a broad group grant covering C, a different owner/group, inherited ACEs, an unprotected DACL, or an extra deny ACE. Preserving them is not equality to the proposed final descriptor; replacing the entire descriptor may change rights that the delta forbids changing. This is a design ambiguity even if a future host happens to have the desired initial descriptor.

Required clarification:

1. Define the admissible initial owner/group, control flags and complete ordered ACE semantics, including how existing C rights are handled. Unexpected permissive rights must fail, not be merged or adopted.
2. Define the exact permitted transformation and final equality test, including generic-mask normalization, SID resolution, inheritance/protection and ACE order. Do not compare an arbitrary serializer's spelling as if it were the policy.
3. Specify no pipe creation, no startup evidence and no SERVICE_RUNNING before successful final readback. Wrong readback, inability to read/set, or unexpected baseline is fatal startup failure.
4. Have BA independently compare the final process descriptor before P14 publication and retain the before/after evidence. A3's readback alone is not the independent record.

This is a focused correction, not a request to select a new DACL here.

## Races and lifecycle

Installing the ACE before pipe creation is a sound ordering constraint. The source must make that ordering executable: a service thread cannot announce RUNNING or start accepting pipe clients while setup/readback is still pending. ETW publication cannot substitute for completing setup.

Changing a descriptor must not be treated as revocation of previously granted handles. An unexpectedly permissive startup baseline is therefore not safely repaired merely by producing the desired final text. The lifecycle must start from an accepted baseline; independent BA collection must not excuse a broader startup interval. This is especially relevant if implementation proposes replacing rather than validating a default descriptor.

The process ACE is scoped to this A3 process object, not a service-object, executable-file, pipe or token grant. It must be established again for each separately authorized A3 lifetime. A new PID/process cannot inherit the previous P14's authority. Automatic service restart and in-process pipe replacement remain prohibited. The collector's descriptor observation and the trusted source's no-change behavior are the continuity premise; A2's limited handle cannot reread the process DACL.

## Outcomes

| Condition | Required outcome |
| --- | --- |
| Initial descriptor unexpected; installation/readback fails | Fatal A3 startup; no pipe/RUNNING/P14; STOP_INCONCLUSIVE for dependent attempt. |
| BA cannot obtain or match final descriptor | No P14 publication; no A2 send. |
| C cannot obtain the limited process handle | STOP_INCONCLUSIVE; no expanded access or debug fallback. |
| Process signals or live PID/start/path mismatches | Abandon attempt and comparison input; retire endpoint generation. |
| C can query B token under the proposed topology | Reject topology delta and return to design review; not successful commissioning. |
| Unexpected descriptor change after publication | Endpoint evidence invalid; F3 must define how retirement reaches the attempt gate. |

The mask need not be enlarged. The installation contract and independent effective-access evidence do need completion.
