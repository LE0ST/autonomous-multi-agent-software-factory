# F2 — Canonical P14 bytes, descriptor fields, and maximum

This is the byte-level correction to P14 §4 and the corresponding manifest row. It preserves all P14 fields and their authority exclusions. P14 continues to be endpoint evidence only.

## JSON envelope

P14 is one UTF-8 JSON object, no BOM, no trailing LF, no whitespace outside strings, exactly the 35 fields in the existing proposal in exactly that property order. Reject unknown, missing, duplicate, reordered, or trailing data. Non-ASCII values are forbidden. Within JSON strings, only `\\` and `\"` escapes are permitted, and they are used only where required by the fixed path/command string. Integers use unsigned canonical decimal without sign or leading zero (except literal `0`); booleans are lowercase `true`/`false`. Hex is lowercase with the exact width already specified per field.

`run_id` is exactly `260926_A`; service, image, command, pipe, schema, numeric pipe modes/buffers, and all fixed literals remain those in the controlling endpoint contract. PID is 1 through `4294967295` in canonical decimal. FILETIME and serial values are 16 lowercase hex digits; file IDs and SHA-256 values retain their fixed lowercase-hex widths. All fields are comparisons, never selectors.

The exact ordered property list and types are:

|#|Property|Canonical value|
|---:|---|---|
|1|`schema_version`|integer `1`|
|2|`run_id`|string `260926_A`|
|3|`p10_sha256`|64 lowercase hex|
|4|`endpoint_generation`|32 lowercase hex|
|5|`observed_filetime`|16 lowercase hex|
|6|`server_pid`|decimal `1..4294967295`|
|7|`process_start_filetime`|16 lowercase hex|
|8|`process_owner_sid`|canonical numeric SID|
|9|`process_group_sid`|canonical numeric SID|
|10|`process_dacl_sddl`|exact DACL-only form below|
|11|`service_name`|`S1PF_Broker_260926_A`|
|12|`service_type`|integer `16`|
|13|`service_start_type`|integer `3`|
|14|`service_binary_path`|`\"C:\\S1PF_260926_A\\bin\\broker.exe\" --service --binding \"C:\\S1PF_260926_A\\config\\binding.json\"`|
|15|`service_account_sid`|canonical numeric B SID|
|16|`service_state`|`RUNNING`|
|17|`service_owner_sid`|canonical numeric SID|
|18|`service_group_sid`|canonical numeric SID|
|19|`service_dacl_sddl`|exact DACL-only form below|
|20|`token_user_sid`|canonical numeric B SID|
|21|`image_path`|`C:\\S1PF_260926_A\\bin\\broker.exe`|
|22|`image_volume_serial`|16 lowercase hex|
|23|`image_file_id`|32 lowercase hex|
|24|`image_sha256`|64 lowercase hex|
|25|`pipe_name`|`\\\\.\\pipe\\S1PF-broker-260926-A`|
|26|`pipe_open_mode`|`00080003`|
|27|`pipe_mode`|`0000000e`|
|28|`pipe_max_instances`|integer `1`|
|29|`pipe_out_buffer`|integer `4096`|
|30|`pipe_in_buffer`|integer `4096`|
|31|`pipe_owner_sid`|canonical numeric SID|
|32|`pipe_group_sid`|canonical numeric SID|
|33|`pipe_dacl_sddl`|exact DACL-only form below|
|34|`first_instance_create_succeeded`|boolean `true`|
|35|`first_instance_collector_observed_filetime`|16 lowercase hex|

The outer bytes are exactly `{` + these quoted property names and values separated by `,` with `:` and no spaces + `}`. There is no newline or trailing byte. The service command is an equality field, not executable input.

## Descriptor fields

`process_dacl_sddl`, `service_dacl_sddl`, and `pipe_dacl_sddl` are **DACL-only SDDL**, not owner/group/DACL descriptors. Each begins with `D:P`; owner and group are independently represented by their adjacent `*_owner_sid` and `*_group_sid` fields and independently checked against the actual security descriptor.

The exact canonical strings are:

```text
process_dacl_sddl = D:P(A;;GA;;;<SY>)(A;;GA;;;<BA>)(A;;GA;;;<B>)(A;;0x00101000;;;<C>)
service_dacl_sddl = D:P(A;;GA;;;<SY>)(A;;GA;;;<BA>)
pipe_dacl_sddl    = D:P(A;;FA;;;<B>)(A;;0x00100183;;;<C>)(A;;0x00020000;;;<BA>)
```

`<SY>`, `<BA>`, `<B>`, and `<C>` are replaced with the independently approved canonical numeric SID strings. All trustees, including well-known principals, use numeric SID spelling: SY is `S-1-5-18`; BA is `S-1-5-32-544`; no `SY`, `BA`, `WD`, account-name, or role alias is emitted. Role SIDs must be valid revision-1 SIDs with no more than 15 subauthorities; canonical decimal subauthorities have no leading zeros. Their maximum canonical string length is 183 bytes.

ACE order, flags, and masks are fixed exactly by the strings above. No inheritance flags, object/callback ACEs, conditional ACEs, or alternate ACE types are allowed. `GA` and `FA` are accepted only in the exact positions shown and are normalized with the applicable process/file generic mapping during semantic descriptor comparison. The restricted masks are canonical eight-digit lowercase numeric hex after `0x`; equivalent symbolic spellings, uppercase hex, shortened masks, and generic bits in restricted ACEs are rejected. Before a record is accepted, the parsed canonical DACL is compared semantically with the actual owner/group/full DACL/control state from the held native handle; byte equality alone is not a descriptor check.

## Exact maximum

The corrected maximum accepted P14 size is **8192 bytes**. It is an admission limit, not a buffer-size inference. The field domain above makes it sufficient for every permitted value:

- eight standalone SID fields and nine trustee SID occurrences across the three DACL-only strings: at most 17 × 183 = 3111 bytes;
- every other value is either a fixed literal, a fixed-width hex string, a bounded canonical PID, or fixed path/command text. The non-SID allowance is conservative and auditable: at most 35 × 64 = 2240 bytes for each fixed key plus its punctuation/quotes (64 covers the longest key and all JSON delimiters); at most 1400 bytes for all non-SID values (fixed names/paths after JSON escaping, the bounded decimal PID, schema/boolean values, and all fixed-width hex fields); and at most 256 bytes for the fixed DACL grammar/punctuation excluding trustee SIDs. Thus the non-SID portion is at most 3896 bytes, below the 4096-byte budget. Every string/value has a fixed or explicit maximum above; no unconstrained string remains.
- therefore the maximum canonical record is below 7007 bytes and is admitted under 8192. The reader rejects any actual input above 8192 before parsing or allocation.

The exact Astra synthetic 2050-byte vector used the old full-descriptor interpretation and is therefore not a canonical record under the corrected DACL-only grammar. Its substantive boundary case—PID `123456`—is expressly permitted. Replacing the full descriptors with the canonical DACL-only fields yields a record within 8192; the six-digit PID is not rejected. A ten-digit PID is likewise permitted and bounded by the PID domain.

## Failure result

Missing, malformed, noncanonical, over-8192, wrong-order, wrong-descriptor, or inconsistent P10/endpoint data is `STOP_INCONCLUSIVE`. The parser does not repair SDDL, resolve account names, choose a role SID, or turn an observed descriptor into its own expected descriptor.
