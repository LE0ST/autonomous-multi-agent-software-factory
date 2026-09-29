# Trust chain and circularity

## Overall judgment

A non-circular chain is possible under the proposed principals:

```text
accepted source/build + authorized G2 static identities and seals
  -> BA checks protected P6, SCM configuration and held A3 process
  -> OS-attributed startup event from that verified incarnation
  -> BA validates startup facts and creates/seals P14 under verified P3
  -> A2 validates protected P14 against trusted current expectations
  -> A2 checks the PID on its actual connected pipe and the held process
  -> one already-authorized request and correlated response
```

Neither a ReadFixtureHead response nor a fact selected by the wire request is needed to begin the chain. This defeats the assertion that every use of A3 self-observation is necessarily circular. It does not prove that the current proposal has completed every arrow. F3 and F4 identify the incomplete arrows.

The controlling [observation adjudication](../independent_review_read_fixture_head_design_adjudication/OBSERVATION_ACCESS_MAP.md) explicitly distinguishes A2 as verifier from the observer of each corroborating fact. It permits a protected delegated observation design; it does not permit an unauthenticated A3 response to establish its own authority. The proposed collector should be assessed on that basis.

## Who actually observes each fact

| Fact | Actual observer in endpoint §3 | Independent corroboration / limitation |
| --- | --- | --- |
| Service registration, binary command, configured account, current service PID/state, service descriptor | BA through SCM APIs | Independent of A3's pipe response. Configured account is not itself proof of actual TokenUser. |
| Process creation time/path and process owner/group/DACL | BA through a held process handle | Independent runtime observation of the opened process; must be the same incarnation as the event and SCM PID. |
| Protected P6 bytes/hash/file identity | BA through protected file access | Independent file observation compared to prior G2/P10 expectations. A current file at a returned pathname is not automatically proof of the running image's original bytes. |
| Actual B TokenUser | A3 self-query, emitted in startup ETW | BA compares the attributed observation to independent B SID and SCM account. BA does **not** directly open/query B's token. |
| Actual pipe owner/group/DACL | A3 GetSecurityInfo on returned server handle, in startup ETW | BA validates the descriptor and event origin. BA does **not** independently open that server handle for readback. |
| Successful first-instance creation, flags, returned handle | A3's reviewed creation path and event | A self-report whose credibility depends on executing the pinned code in the attributed incarnation. Handle value is explicitly diagnostic, not a transferable handle/proof. |
| Original handle retained without replacement | A3 source invariant over service lifetime | Startup ETW cannot measure the future. A2's direct connection/process checks only corroborate continuity within their observable limits. |
| P14 file identity/descriptor/seal | BA creation/readback; A2 protected reader | BA origin does not dispense with current-generation admission or checking the actual opened object. |
| Connected server PID | A2 GetNamedPipeServerProcessId on actual connection | Direct, before send. P14's PID is not a replacement for this observation. |
| Current process creation time/path/liveness | A2 through limited process handle | Direct comparison with P14, retained through acceptance. Not a direct token, SCM or server-descriptor observation. |

Source: [ENDPOINT_EVIDENCE_CONTRACT.md §3](../read_fixture_head_design_delta_after_luna_b/ENDPOINT_EVIDENCE_CONTRACT.md). Describing all fields as independently BA-measured would overstate the design. Describing the entire chain as A3 self-attestation would also be inaccurate.

## When source-pinned self-observation is acceptable

It is acceptable as delegated evidence if BA establishes, independently of the event contents, which protected reviewed program is executing as the observed service incarnation, and the event is bound to that incarnation. The source must actually query TokenUser and the returned pipe's descriptor, fail startup on failure, emit only after first-instance success, and enforce retention/no replacement. Static source/hash approval gives meaning to that telemetry; it is not itself a runtime signature.

This model trusts the integrity and execution of the authorized B program. It does not prove resistance to arbitrary code execution inside that same B process. Such a stronger threat model would need another architecture and is not introduced by this review. A1/M4/M5 remain untrusted and cannot supply startup facts or trusted expectations.

## F4a: event-to-incarnation attribution

The event fixes a provider GUID, ID/version, payload and header PID. Endpoint §3 requires the collector to validate the PID against SCM PID and the measured process creation time. But the payload has no process creation time, and the contract explicitly makes ETW header time an opaque diagnostic that is not interpreted as FILETIME.

Thus “against creation time” is not yet a specified comparison. An event could be queued from an earlier process before the collector establishes which incarnation it is holding. Numeric equality to a later SCM PID plus a current creation-time measurement alone does not timestamp the queued event. This is a missing proof of attribution, not an assertion that PID reuse was observed.

The correction must specify a capture/lifetime interval that excludes an earlier incarnation, or a documented timestamp attribution method with a defined clock domain, or another explicit binding. This is separate from a wall-clock freshness window. No new payload field or clock policy is selected here.

Microsoft defines EVENT_HEADER.ProcessId as the generating process ID and explains timestamp conversion/raw timestamp behavior. The provider identifier identifies the provider, not an approved executable hash. See [EVENT_HEADER](https://learn.microsoft.com/en-us/windows/win32/api/evntcons/ns-evntcons-event_header). The producer API/configuration must preserve that OS attribution; a public GUID alone cannot authenticate the sender.

## F4b: ETW session, sealing and loss

The phrase “private EVENT_TRACE_REAL_TIME_MODE session” is ambiguous. If “private” means EVENT_TRACE_PRIVATE_LOGGER_MODE, Microsoft documents that private logger mode cannot be combined with real-time mode. If it means a separately named, access-restricted ordinary real-time session, that is a different configuration and needs an exact ownership/security rule. See [ETW logging-mode constants](https://learn.microsoft.com/en-us/windows/win32/etw/logging-mode-constants).

The manifest calls the session BA-only without defining how its session/provider access is established and checked. Freeze the flags, session identification, collision/no-adoption rule, allowed controller/consumer/producer principals, and access-verification mechanism. Do not silently request a new ACL or ETW privilege in implementation.

The proposal already requires missing, duplicate, malformed, wrong-PID and lost-event failures to stop publication. The collector must have a defined sealing point: which buffered events and final counters are consumed before the record becomes admitted evidence. Publication followed by discovery of pre-seal loss/duplicate data cannot be counted as a successful startup observation. Real-time delivery is buffered; stopping the session is not a continuing endpoint monitor. These are completion rules for the selected observation method, not a request for permanent ETW.

## F4c: executable and service observations

The collector hashes the protected P6 file at the process's reported path and compares independent G2/P10 seals. Endpoint §3 explicitly defers the running-image binding to source/build review. Make that premise enforceable: the accepted P6/ancestor identity and no-replacement lifecycle must cover service launch and observation, and the process path must refer to that approved image. Do not promote a file currently found at a path into proof of what was launched without that continuity. This can use protected identity/lifetime rules; it does not inherently require C VM read access or hashing process memory.

The selected service checks include SERVICE_SID_TYPE_NONE, but the listed QueryServiceConfigW call does not return that optional service configuration. Name the corresponding query, such as QueryServiceConfig2W with SERVICE_CONFIG_SERVICE_SID_INFO, in the collector contract; it uses the already proposed SERVICE_QUERY_CONFIG right. See [QueryServiceConfig2W](https://learn.microsoft.com/en-us/windows/win32/api/winsvc/nf-winsvc-queryserviceconfig2w). This is a local API-manifest omission, not a new C service right.

## F3: startup evidence versus live retirement

P14 may truthfully certify a startup observation while no longer being valid for an attempt. An immutable record cannot update its own RUNNING/first-instance facts. The collector holds a process handle after publication, but its E1 invalidation is invisible to C/B. The design must connect the source-enforced endpoint lifetime and/or an authorized retirement mechanism to A2 admission and acceptance.

A2 retaining process/pipe handles is useful and required; retaining P14 additionally binds file identity. None is a subscription to E1. In particular, service STOPPED while process/pipe teardown is still pending and collector failure are not necessarily signaled by the process wait at that instant. The required result remains STOP_INCONCLUSIVE for lost required evidence; what detects that loss must be explicit. See the [P14 failure scenarios](P14_AUTHORITY_AND_LIFETIME.md).

## P14 and P15 cannot authenticate each other

P15 comes from the authorized case provisioner and binds a selected frozen case to an independent P11 expectation. P14 comes from the endpoint collector and binds independent startup observations to a connected process. Both compare to the same independently sealed P10. Their identities/generations can be associated in the authorized lifecycle record without making either resource authoritative for the other's content.

Forbidden shortcuts include taking P14's digest as the source of trusted P10, taking P15's existence as proof of a live endpoint, deriving P11 expectations from an A3 response, or using either record's parsing success as proof that its generation is current. No such shortcut is authorized by the proposal; F3 is needed so implementation cannot fill the missing delivery/admission link with one.
