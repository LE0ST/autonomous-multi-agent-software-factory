# Fixed binary `ReadFixtureHead` wire contract

This is the only application protocol on the accepted local message-mode pipe for this operation. It is not JSON, a generic dispatcher, a negotiated protocol, or a change to canonical P11. All integers are unsigned little-endian. All exact lengths count bytes. Exactly one complete application envelope occupies exactly one native named-pipe message.

## Header (12 bytes)

| Offset | Width | Field | Exact value/rule |
|---:|---:|---|---|
| 0 | 4 | magic | ASCII `S1RH`, bytes `53 31 52 48` |
| 4 | 2 | version | `1`, bytes `01 00`; no negotiation |
| 6 | 2 | message kind | request `0x0001`; success response `0x8001`; error response `0x8002` |
| 8 | 4 | total length | Entire envelope including header, exact value required |

Unknown magic/version/kind is rejected. No extension bytes or reserved header space exists.

## Request: exactly 64 bytes

| Offset | Width | Field | Exact value/rule |
|---:|---:|---|---|
| 12 | 2 | operation | `0x0001` = `ReadFixtureHead`; all other values rejected; this is not a dispatch table |
| 14 | 2 | flags | `0`; all nonzero values rejected |
| 16 | 16 | nonce | Raw 16-byte A2 CSPRNG output; no text encoding |
| 32 | 32 | P10 binding | Raw SHA-256 of exact canonical P10 bytes, copied from A2's independently validated assignment. A3 compares to its own independent P10 digest and rejects mismatch. It is an assertion, not authority to choose an expected seal or P11. |

The request has no case ID, path, P11 digest, credential, retry, error preference or arbitrary verb. The operation value is fixed to one. A3 uses its preconfigured case and P11 expectation. P11 request data cannot select that state.

## Response

Common fixed response prefix is 66 bytes:

| Offset | Width | Field | Exact value/rule |
|---:|---:|---|---|
| 0–11 | 12 | header | As above, kind `0x8001` success or `0x8002` error |
| 12 | 2 | operation | `0x0001` |
| 14 | 2 | status | success: `0`; error: `1` (`READ_INCOMPLETE`) |
| 16 | 16 | nonce echo | Exact byte-for-byte request nonce |
| 32 | 32 | P10 binding echo | Exact byte-for-byte request P10 binding; A2 also compares to its independently validated P10 digest |
| 64 | 2 | payload length | Exact payload byte count |
| 66 | 0–300 | payload | Success only: exact canonical P11 JSON bytes, unchanged and without terminator |

Success is allowed only for payload length 299 (active selected case) or 300 (terminal selected case). A2 additionally requires the length and exact bytes to match its independently selected case expectation. Error kind `0x8002` has status 1, payload length 0 and total length 66. It reveals no native error detail. A2 maps it to typed `STOP_INCONCLUSIVE`, with no `BoundComparisonInput`. A3 records detailed native failures only in protected evidence.

Exact maxima: request **64** bytes; error **66** bytes; success **365** bytes active / **366** bytes terminal; maximum response **366**. These are application limits, independent of the pipe's 4096-byte buffers.

## Native-message mapping and parser rules

- One 64-byte request envelope is one native request message. A3 performs one `ReadFile` for that message. A short result, API error, or `ERROR_MORE_DATA` is incomplete; no multi-message accumulation is allowed.
- One response envelope is one native response message. A2 performs one bounded read. A short result, API error or `ERROR_MORE_DATA` is incomplete; no multi-message accumulation is allowed.
- No app envelope may be split across native messages; no native message may contain more than one envelope. Header total length, actual native-message byte count, and fixed type length must all agree exactly.
- A3 rejects malformed, truncated, wrong-version, wrong-operation, nonzero-flags, wrong-binding, overlong, trailing-byte, or second-request input before any P11 access. It never dispatches a second request on that connection. After the one response or failure it disconnects the client connection. Messages queued beyond the one accepted request are never dispatched; detected extra data makes the attempt fail.
- A2 rejects malformed/truncated/oversized response, wrong kind/status/op, total/payload mismatch, extra bytes, wrong nonce, wrong P10 echo, wrong case payload/length, or extra response data. It accepts no second response; after the one accepted response it closes the connection. `PeekNamedPipe` after the one complete message is used to reject already-queued extra bytes before accepting the response. Any failure in this check is incomplete.
- Unknown/malformed requests that cannot be safely correlated receive no response: A3 closes the connection. For a structurally valid, authenticated request whose protected head read fails, A3 may send exactly the generic 66-byte `READ_INCOMPLETE` response echoing the request nonce and P10 binding. No native status is sent on wire.
- Unknown/trailing/partial/extra messages never trigger retry, fallback, another protected read, a new case selection, or a second response. The client closes after the one response/error. Server instance lifetime remains retained across separate client connections; connection/request lifetime is one-shot.

## Literal valid vectors

For these synthetic examples only, the raw P10 digest is `AA` repeated 32 bytes and its P11 textual value is lowercase `a` repeated 64 characters. Nonce is bytes `00` through `0F`. Neither digest is G2 evidence.

### Valid request (64 bytes)

Hex bytes, in order:

```text
53 31 52 48 01 00 01 00 40 00 00 00 01 00 00 00
00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F
AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
```

### Valid active success response (365 bytes)

The first 66 bytes are:

```text
53 31 52 48 01 00 01 80 6D 01 00 00 01 00 00 00
00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F
AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
2B 01
```

Append exactly these 299 ASCII bytes as payload, with no quote wrapper and no final LF:

```text
{"schema_version":1,"marker":"S1PF-260926-A-STAGE-A-V1","p10_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","case_id":"spent-budget-active","latest_digest":"4d5d63027a1578256a003328664c48f1328cc5171ef29db4a9c0046b8ce4d22d","generation":1,"worker_runs":1,"terminal":false}
```

### Valid terminal success response (366 bytes)

The first 66 bytes are:

```text
53 31 52 48 01 00 01 80 6E 01 00 00 01 00 00 00
00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F
AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
2C 01
```

Append exactly these 300 ASCII bytes, with no quote wrapper and no final LF:

```text
{"schema_version":1,"marker":"S1PF-260926-A-STAGE-A-V1","p10_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","case_id":"spent-budget-terminal","latest_digest":"eb2c260344d3c33075cb817a6ff8ce7c216b3a57dace342bb58fbe086ee33764","generation":2,"worker_runs":1,"terminal":true}
```

### Valid generic error response (66 bytes)

With the same synthetic nonce and P10 binding:

```text
53 31 52 48 01 00 02 80 42 00 00 00 01 00 01 00
00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F
AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA AA
00 00
```

## Literal malformed/invalid cases

Every case below is rejected; none yields P11 bytes or a comparison input.

1. **Wrong version:** valid request with byte offset 4 changed from `01` to `02` (`02 00` version). Close without response.
2. **Unknown operation:** valid request with offset 12 changed from `01 00` to `02 00`. Close without response.
3. **Reserved flags:** valid request with offset 14 changed from `00 00` to `01 00`. Close without response.
4. **Declared trailing byte:** valid request with total-length bytes at offsets 8–11 changed to `41 00 00 00`, then append `00` as byte 65 in the same native message. Reject exact-length mismatch.
5. **Truncated request:** first 63 bytes of the valid request, with declared total still 64. Reject; do not accumulate from a second native message.
6. **Wrong nonce echo:** valid active response with response nonce byte 16 changed from `00` to `01`. Reject before accepting the payload.
7. **Wrong P10 echo:** valid active response with one raw binding byte changed from `AA` to `AB`. Reject.
8. **Case mismatch:** deliver the literal active success response when A2's independently approved selected case is terminal. Reject despite valid framing and correlation.
9. **Wrong response total:** active response with total length changed from 365 (`6D 01 00 00`) to 366 (`6E 01 00 00`) without adding a payload byte. Reject.
10. **Wrong payload length:** active response with payload length changed from 299 (`2B 01`) to 300 (`2C 01`) while retaining the 299-byte active payload. Reject.
11. **Unknown response kind:** valid response with kind bytes at offsets 6–7 changed to `03 80`. Reject.
12. **Extra native message:** after the valid request native message, send a second native message containing the same 64-byte request. A3 dispatches only the first; it detects queued extra data where present, rejects the attempt, and never performs a second P11 read. If the extra arrives after the check, the connection is closed after the sole response and the extra request is not processed.
13. **Second response:** after the valid success native message, send another response message. A2 accepts no second message; the one-shot connection is closed and the extra response cannot alter the already bound result. If extra bytes are already queued before acceptance, the attempt is rejected.

These vectors are design literals. A later pure-source review must independently encode/decode them and add byte-by-byte offset mutations without deriving expectations by calling the implementation under test.
