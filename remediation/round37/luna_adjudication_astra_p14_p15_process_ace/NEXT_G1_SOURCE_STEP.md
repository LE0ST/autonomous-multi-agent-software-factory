# Next bounded source step

## Selected increment

Implement only the **pure P15 canonical parser/renderer and explicit expected-value comparator**.

Suggested new files:

- `stage_a_fixture/src/selected_case_record.hpp`
- `stage_a_fixture/src/selected_case_record.cpp`
- `stage_a_fixture/tests/selected_case_record_test.cpp`

The exact file names may follow repository naming convention, but the source boundary must not expand.

## Inputs and permitted result

Inputs are byte arrays or ordinary value objects for the six exact fields, plus explicit trusted expected values supplied by the caller: fixed schema `1`, `run_id="260926_A"`, independently approved P10 digest, one already selected enum case, independently rendered expected P11 digest, and an opaque 16-byte selection generation. The parser accepts only exact compact UTF-8 without BOM/LF/whitespace/unknown/duplicate/reordered fields and returns owned parsed/canonical data or a typed failure.

Canonical field order is:

```text
schema_version, run_id, p10_sha256, selected_case_id,
selected_p11_sha256, selection_generation
```

Case is exactly `spent-budget-active` or `spent-budget-terminal`; SHA-256 values are exactly 64 lowercase hex characters; generation is exactly 32 lowercase hex characters. At the fixed run ID the active and terminal canonical lengths are exactly 308 and 310 bytes, respectively. No normalization or alternate JSON spelling is accepted.

## Must not do or claim

No filesystem, native API, token/process/service/pipe/ETW call, randomness, generation allocation, case selection, P11 read, BA provenance, current-generation freshness, lifecycle admission, or P11 custody. It must not construct a production trusted binding or label arbitrary caller values “approved.” It may compare only against explicit expected values and returns ordinary parsed data/typed failure.

Successful parsing proves only that these input bytes have the fixed canonical P15 syntax and match the explicit comparison values. It does not prove the bytes came from P15, were created by BA, are the current P15 object, match the held P11, or authorize a request.

## Required tests and independent review evidence

- Independent literal active/terminal byte vectors, lengths, and SHA-256; expected bytes must not be produced by the implementation under test.
- Valid render/parse round trip for both frozen cases and distinct literal generations.
- Wrong schema/run/P10/case/P11/generation; active/terminal swap; uppercase/short/long hex; unknown, duplicate, missing, reordered fields; BOM, whitespace, trailing LF/bytes; malformed UTF-8/JSON escapes; sizes 307/308/309/310/311 and maximum input checks.
- Explicitly verify that parsing never infers expected case/P11 from received bytes, never treats a received hash as its own expectation, and exposes no mutable trusted-success carrier.
- Count actual assertions, build from final source in a separate reviewer directory, and audit public API/result immutability.

Stop after this pure source slice and its independent review. Do not implement the protected reader, process helper, P14 codec, ETW/collector, service/pipe transport, or endpoint gates. G1 remains HOLD / UNAPPROVED; S1 remains OPEN; Stage A and Round 3.7 remain NOT PASSED.
