# F4 — ETW startup attribution and P6/service observation

## Event-to-process incarnation

The provider GUID and `EVENT_HEADER.ProcessId` are necessary filters, not identity proof. The fixed provider emits a three-stage transcript. Each event is version 1 and begins with `status:u32LE=0, process_creation_filetime:u64LE`; A3 obtains creation FILETIME through `GetProcessTimes(GetCurrentProcess(), ...)`.

| Event | ID | Payload after common 12 bytes |
|---|---:|---|
| `PROCESS_READY_FOR_BASELINE` | 2 | none; total 12 bytes |
| `PROCESS_DACL_FINAL` | 3 | none; total 12 bytes |
| `PIPE_FIRST_INSTANCE_READY` | 1 | Existing startup payload fields, in existing order, excluding the old status field because it is in the common prefix; maximum total 4207 bytes |

For all three records the `EVENT_DESCRIPTOR` is exactly `Version=1, Channel=0, Level=0, Opcode=0, Task=0, Keyword=0`; only `Id` differs as shown. The provider GUID remains `{7C3A2609-CC37-4E9A-8C92-4F52B7B31D37}`.

The only accepted transcript is exactly ID 2, BA disable/enable provider pulse 1, ID 3, BA disable/enable provider pulse 2, ID 1. The A3 provider callback acknowledges only the two post-event transitions from the one configured session; it ignores the initial enable. The collector independently obtains creation FILETIME from a held `OpenProcess` handle for the SCM PID. It accepts an event only when all of these agree:

1. ETW header PID = current SCM `dwProcessId` = PID of the retained BA process handle.
2. Event `process_creation_filetime` = `GetProcessTimes` creation FILETIME from that held handle.
3. The held handle remains unsignaled; `QueryFullProcessImageNameW` equals the fixed P10/P6 path; its owner/group/process DACL equal their independent expectations.
4. The service is the fixed own-process service and each event is the exact reviewed provider GUID, expected phase ID (2, 3, or 1), version 1, task/opcode/level/keyword and phase payload grammar.
5. The pinned P6 implementation emits each phase only at its specified barrier; ID 1 is emitted only after successful first-instance creation and descriptor readback. Its reported SID/pipe fields match independent expected values.

The process creation time is an incarnation discriminator carried by the pinned source, not trusted alone. OS ETW header PID binds the emission to the process that actually called the provider; BA’s handle supplies the independent creation time. An earlier process that reused the PID has a different creation FILETIME and is rejected. An event with only matching PID/provider, any extra event from the fixed provider, or a missing/duplicate/malformed/reordered phase prevents P14 publication. ETW timestamp remains diagnostic and is never interpreted as FILETIME.

The original maximum 4199-byte ID 1 event included the four-byte status. The corrected common prefix adds eight-byte process creation FILETIME while retaining status, so ID 1 maximum is **4207 bytes**. All remaining field widths/order stay as specified in the endpoint contract. IDs 2/3 are exactly 12 bytes. No response over the A2/A3 pipe participates in this proof.

## Session identity, mode, security, and lifetime

Use one ordinary cross-process real-time ETW session, not a private logger:

- `LogFileMode` is exactly `EVENT_TRACE_REAL_TIME_MODE`; do not set `EVENT_TRACE_PRIVATE_LOGGER_MODE`, `EVENT_TRACE_SECURE_MODE`, a file mode, or a kernel/system logger flag. This is an access-restricted ordinary cross-process real-time session, not an ETW “private logger.”
- `Wnode.Guid = {2F8F2609-CC37-4E9A-8C92-4F52B7B31D37}`, `Wnode.Flags = WNODE_FLAG_TRACED_GUID`, and `Wnode.ClientContext = 1` (QPC). The timestamp remains diagnostic only.
- Fixed descriptive session name: `S1PF-260926-A-EndpointStartup`; the GUID above is fixed for this Stage A design. `StartTraceW` collision/`ERROR_ALREADY_EXISTS` is a hard failure. Never attach to, adopt, update, or stop a session not returned by this invocation. An existing orphan requires separate authorized cleanup.
- BA is the sole controller and real-time consumer; SY retains system access. B may register/write only the fixed startup provider. C, W, and other providers receive no access. No role is added to Performance Log Users.
- Before start, set and verify session/provider DACLs using `EventAccessControl`/`EventAccessQuery`. On the session GUID, BA and SY each have exactly `TRACELOG_CREATE_REALTIME | WMIGUID_QUERY | TRACELOG_ACCESS_REALTIME`. On the provider GUID, B and SY each have `TRACELOG_REGISTER_GUIDS`; BA and SY each have `TRACELOG_GUID_ENABLE`. Use `EventSecuritySetDACL` for the first ACE and `EventSecurityAddDACL` for subsequent ACEs, then query and compare the complete ACL. No C/W ACE is added. Any additional effective grant beyond the trusted SY/BA administration boundary, or any API failure, is fatal. This configuration grants no new Windows account/group membership and no service/file/token right.
- Start session, enable only the fixed provider, open the real-time consumer, and confirm it is ready before `StartServiceW`. Collect the exact F1 two-pulse/three-event transcript. Disable the provider, stop the session, drain the stream to completion, and check final `EventsLost`, `LogBuffersLost`, `RealTimeBuffersLost`, and consumer completion state before P14 publication. Every loss counter must be zero. A missing, duplicate, extra fixed-provider event, malformed payload, wrong PID/start time, failure to drain/stop, or nonzero loss means no P14 and `STOP_INCONCLUSIVE`.
- The session is owned by this BA collector invocation only. A collision is not repaired automatically. It is stopped by the same returned session handle after sealing; it does not remain as a monitor. Collector death before commit means no P14. After commit the collector may exit; P14’s process/pipe/retirement contract governs runtime validity.

These mode and access statements use Microsoft’s ETW mode and access contracts: [logging-mode constants](https://learn.microsoft.com/en-us/windows/win32/etw/logging-mode-constants), [EventAccessControl](https://learn.microsoft.com/en-us/windows/win32/api/evntcons/nf-evntcons-eventaccesscontrol), [EVENTSECURITYOPERATION](https://learn.microsoft.com/en-us/windows/win32/api/evntcons/ne-evntcons-eventsecurityoperation), and [EVENT_TRACE_HEADER](https://learn.microsoft.com/en-us/windows/win32/api/evntcons/ns-evntcons-event_header). No native session was created or tested by this design adjudication.

## Startup order, service SID, and executable continuity

1. BA establishes the ETW session/consumer and holds the approved P6 file/ancestor handles. It verifies P6 path, parent, volume/file ID, protected descriptor, and full-file hash against P10/G2 before start. The fixed SCM binary command points to that P6. P6 and its ancestors remain non-replaceable/non-writable by A1/M4/M5 throughout the service lifetime; BA does not replace them while the image is running.
2. BA starts the fixed own-process service. It queries service configuration/status/descriptor and specifically obtains the service SID type using `QueryServiceConfig2W(..., SERVICE_CONFIG_SERVICE_SID_INFO, ...)`, requiring `SERVICE_SID_TYPE_NONE`.
3. BA opens and retains the exact SCM PID, checks process creation time, owner/group/DACL and image path. It hashes only the protected P6 object already bound by handle; a current pathname hash alone is not accepted as proof of launched bytes. Continuity comes from the fixed SCM command, protected P6 identity/hash before launch, no replacement during launch/lifetime, held P6/process handles, and source/build review.
4. A3 emits ID 2 and waits; BA independently verifies the initial descriptor and pulses the provider. A3 changes the DACL, locally reads back and emits ID 3; BA independently verifies the final descriptor and pulses again. A3 then creates the fixed first-instance pipe, reads back its descriptor, emits ID 1, and reports `SERVICE_RUNNING`. BA validates all observations, seals/stops ETW, and only then publishes P14.

The exact `QueryServiceConfig2W` query is required because `QueryServiceConfigW` does not return `SERVICE_SID_TYPE_NONE`. Any access/API failure, mismatch, service restart, P6 replacement, lost held handle, or uncertain source-to-image continuity is `STOP_INCONCLUSIVE`; do not add a C service/P6 right, debug privilege, process-memory read, or fallback hash source.
