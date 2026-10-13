# P14 authority and lifetime

## Frozen within the proposal, not yet an accepted resource

Source: [ENDPOINT_EVIDENCE_CONTRACT.md §§1–6](../read_fixture_head_design_delta_after_luna_b/ENDPOINT_EVIDENCE_CONTRACT.md). This review evaluates those proposed rules; it does not certify their execution.

| Property | Proposed authority or obligation |
| --- | --- |
| Resource | Fixed `C:\S1PF_260926_A\config\endpoint-evidence.json`, single child of verified P3. |
| Creator/writer | Designated BA collector; SY/BA retain full file rights. Creation by arbitrary B/A3 or C/A2 is not permitted. |
| Owner/group | BA / BA, read back rather than inferred from creator membership. |
| Reader | C/A2 with `0x00120081`; SY/BA by their full rights. No B or W ACE. |
| Descriptor to verify | `O:BAG:BAD:P(A;;FA;;;SY)(A;;FA;;;BA)(A;;0x00120081;;;C)` with actual created C SID substituted, protected DACL, exact ACE semantics, no inherited/extraneous grants. |
| Creation | Relative NtCreateFile, FILE_CREATE, descriptor at creation, write once, flush and same-handle readback. Collision never permits adoption/overwrite. |
| A2 open | Fixed relative child, no-follow flags, FILE_OPEN, data/attributes/READ_CONTROL/SYNCHRONIZE, FILE_SHARE_READ, synchronous non-directory/reparse-point open; reject reparse; retain through exchange. |
| Identity | Verified P3/ancestor chain, P14 volume/file/parent identity, final path, descriptor, canonical bytes/seal and lifecycle generation. A filename is insufficient. |
| Retirement | Logical invalidation of exact file ID in E1; physical deletion/quarantine only after A2-held handles close and separately authorized cleanup. No update-in-place or automatic generation reuse. |

“Read-only” is relative to C. BA/SY full rights remain a trusted administrative capability. The design cannot claim immutability against a malicious provisioner/administrator; the intended adversarial boundary excludes those writers. It must still prevent accidental adoption of residue, stale commissioning state or a failed publication.

## Facts and authority exclusions

P14 records the run/P10 binding, endpoint generation and collector times; server PID/start; process owner/group/DACL; service configuration/account/state/descriptor; measured A3 TokenUser; protected image identity/hash; pipe name/modes/buffers/owner/group/DACL; and the successful first-instance observation. The 35-field schema is in endpoint §4.

It explicitly excludes case ID, P11 digest, operation, nonce, request ID, retry, path selector, credentials and authority updates. The exclusions are coherent provided consumers enforce the following direction of comparison:

| Potential indirect authority | Required interpretation |
| --- | --- |
| `run_id`, `p10_sha256` | Compare to independently trusted P10. Never select or load another assignment because P14 names its digest. |
| Image path, service binary path, service name, pipe name | Equality assertions against fixed P10/topology expectations. Never launch, open an alternate executable, connect elsewhere or execute the embedded command string. |
| B SID, process/pipe owner/group and SDDL | Compare with created-role expectations. Never enroll a new B, grant rights or trust whatever identity the record lists. |
| `server_pid` | Evidence to compare with GetNamedPipeServerProcessId on the actual connected pipe. Open the connected PID, not a substitute PID selected only by the file. |
| Endpoint generation/timestamps | Evidence identity, not permission for another attempt, a nonce source, a retry signal or case choice. No clock-age freshness window is specified. |
| `service_state=RUNNING`, first-instance boolean | Historical observations bound to the startup/lifetime. They are not self-renewing attestations of present state. |

No request or response can write P14. A1/M4/M5 cannot supply these expectations or trigger its publication. They can cause availability/comparison failure; that does not grant selection authority. The accepted nonce generator and fixed operation remain separate.

## F2: schema bound and canonicalization

Endpoint §4 fixes 2048 bytes while including resolved SIDs and multiple SDDL strings. The text does not say whether `process_dacl_sddl` and `pipe_dacl_sddl` contain the full owner/group/DACL descriptor or only its DACL. It names them DACL fields but requests “canonical resolved process SDDL” and compares owner/group/full DACL; the proposed full process descriptor is shown in §3. The service field explicitly uses DACL-only text. This must be unambiguous before byte-level implementation.

An auditable synthetic length calculation under the full-descriptor interpretation:

- Start with the exact §4 field order and constants, compact ASCII JSON with its required backslash/quote escaping.
- Use run `260926_A`; B `S-1-5-21-1111111111-2222222222-3333333333-1003`; C the same SID with RID `1002`. Both SIDs have 46 characters. These are hypothetical values, not created host identities.
- Use B for process/pipe owner/group, service account and TokenUser. Use BA's canonical SID `S-1-5-32-544` for service owner/group.
- Resolve the full process descriptor exactly as §3 proposes: length 243 characters. Resolve the pipe descriptor as `O:<B>G:<B>D:P(A;;FA;;;<B>)(A;;0x00100183;;;<C>)(A;;RC;;;BA)`: length 231 characters, consistent with the accepted B/C/BA pipe grants.
- Substitute strings of the stipulated widths for hashes, file ID, volume serial, generations and FILETIMEs. Their hex values do not change the size. Use the exact fixed service/image/pipe strings and booleans.
- A four-digit PID produces **2048 bytes**. A permitted six-digit PID, `123456`, produces **2050 bytes**; a ten-digit PID produces **2054 bytes**.

This is schema arithmetic, not a host observation, source test or claim that the synthetic IDs exist. It disproves the cap's sufficiency for all permitted values under that reading. A DACL-only representation could be shorter, but choosing it in source would resolve an open byte contract. Actual future SID lengths cannot cure the unspecified general bound.

The correction must also freeze how generic access masks, numeric masks, well-known SID aliases, resolved role SIDs, ACE order and protection flags serialize. Exact descriptor *semantics* can be checked independently; a canonical file format additionally needs one exact spelling. Do not assume any arbitrary Windows SDDL conversion call produces the proposal's chosen bytes.

## Publication and retention

The intended sequence is sound: collect independently bound facts, create a new protected file, write/flush/read back and seal, then allow A2 to use it. The missing part is the observable commit/admission rule (F3).

The writer requests FILE_WRITE_DATA and the reader shares only FILE_SHARE_READ. A2 cannot acquire its prescribed reader handle while an incompatible writer handle remains open. After the writer closes, however, a fully formed file left by a failed publication could become readable. File existence plus parseability cannot be the sole publication receipt. Define when the writer closes, when its exact identity/seal become approved current inputs, and who admits A2 only after that success. A rejected file is residue; it cannot be adopted on restart. The sharing inference follows [NtCreateFile's compatibility rules](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/nf-ntifs-ntcreatefile).

Retaining the P14 handle binds the consumed object and, under the prescribed sharing, excludes ordinary incompatible opens. It does not confer knowledge of an E1 state change. A new pathname occupant must never replace the held object as the evidence for an in-flight attempt.

## Adversarial lifetime cases

| Attempted stale-evidence path | Existing defense | Remaining limit or correction |
| --- | --- | --- |
| PID reuse after old A3 exit | Compare connected PID plus live process creation time; hold process and pipe; reject signaled process. | Sufficient against numeric-PID-only reuse at A2, assuming the original ETW incarnation attribution is sound. F4 addresses startup attribution. |
| New process at the same image path | P6 identity/hash plus new creation time and generation required. | Path equality alone is never enough; source/image continuity must be defined. |
| Automatic service restart using old P14 | Explicitly prohibited; new lifetime requires new observation/P14. | Runtime source/commissioning must enforce the prohibition. No host restart setting is claimed observed. |
| Original first-instance handle lost/replaced | A3 must retain the original, never replace in-process, and stop on loss. A2 detects a broken pipe/process. | A process handle alone cannot observe server-handle loss. F3 must tie loss to termination of admission/connection before response acceptance. Ordinary per-request disconnect is not first-instance destruction. |
| Service stops but process has not exited | E1 invalidation is required. | A2 has neither SCM access nor E1 access. A still-unsignaled process and connected pipe do not directly prove service RUNNING. Specify teardown/acceptance synchronization. |
| Old P14 survives case transition | Exact-ID retirement and absence/quarantine before new lifecycle; new generation. | A2 must have current-lifecycle admission inputs. The record deliberately has no case ID; it cannot identify the selected case by itself. |
| Identical bytes recreated under same path | Compare creation identity, not only bytes/digest/path. | Specify delivery of current expected P14 identity/generation. Otherwise self-observed identity alone does not identify the approved generation. |
| Replacement after A2 opens P14 | Held ancestor/file handles and no delete sharing; use that same handle. | Never unchecked reopen. Administrative replacement outside this trusted lifecycle is not a writer-controlled attack. |
| Collector dies after publication | A2 can still directly detect pipe/process failure. | Text says collector must maintain evidence but supplies no consumer-visible collector death/lease rule. Decide whether its continued life is required. Do not assume a heartbeat exists. |
| Endpoint changes after ETW session stops | Retained process/pipe, pinned source's no-replacement rule, direct PID/start/path comparison. | ETW does not monitor this interval. E1-only invalidation is not an A2 signal. A decision about source-enforced termination versus a live invalidation gate is needed. |
| Late request races lifecycle transition | Commissioning forbids transition during attempts and requires closure before reprovision. | Identify the admission/teardown owner and barrier so this is enforced rather than assumed. |

Endpoint §2 says ETW stops after startup evidence is sealed; §6 says service/first-instance/process loss immediately invalidates E1. Endpoint §3 step 6 nevertheless requires A2 to stop on “evidence invalidation.” That consumer path is unspecified. An E1 audit entry cannot alone implement it.

This does not establish an unavoidable bypass. Reviewed A3 termination/handle-retention behavior plus serialized commissioning could make the lifetime safe without giving C new rights. Alternatively a separately designed trusted retirement mechanism could do so. Choosing the mechanism is adjudication work; this review does not install one.

## Failure decisions

Before publication, unavailable/mismatched observation, ETW loss, invalid source/image, bad descriptor, creation collision, partial write/readback, generation failure or unsealed identity means no admitted P14 and STOP_INCONCLUSIVE. After publication, missing/malformed/replaced/stale P14 or live-process/pipe mismatch means no request or no accepted response/comparison, as applicable. No retry, alternate path, E1 lookup by C, or response-derived repair is allowed.

The intended result is unambiguous. F3 remains necessary for how a post-publication invalidation is detected and made effective before acceptance; F5 for exact final/repeated protected-record observations. Deletion by name or immediate deletion through outstanding reader handles is not an alternative to logical retirement and exact-ID cleanup.
