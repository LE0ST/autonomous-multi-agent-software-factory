# Formal adjudication: authenticated `ReadFixtureHead` design

**Overall decision: B — DESIGN DECISIONS STILL REQUIRED.** The accepted record fixes the semantic authority and several important transport and custody constraints, but it does not define one exact authenticated exchange or its trusted live-endpoint evidence path. No complete `ReadFixtureHead` implementation can yet be specified without choices that remain open. I do not find enough evidence to adopt Astra's overall Decision C: the accepted text requires A2 to verify the connected server before sending, but does not unambiguously require A2 itself to perform every SCM, image, token, and descriptor observation. A direct-A2 reading conflicts with explicit access rows; a protected observer/delegation could preserve the same checks, but its evidence and delivery contract is absent.

This is a read-only design adjudication. **G1 remains HOLD / UNAPPROVED; S1 remains OPEN; Stage A and Round 3.7 remain NOT PASSED.** No fixture commissioning, native observation, source implementation, build, test, or host operation was performed. The prior accepted components remain bounded source preparation and synthetic evidence.

## Adjudication at a glance

| Cell | Result | Controlling reason |
|---|---|---|
| S1 — request/response | Mixed: transport mode, semantic operation, P11 representation and local fail-closed outcome are FROZEN/DERIVABLE; envelope, version, bounds and wire-error behavior are GENUINELY OPEN. | The topology fixes message-mode NPFS; the delegation contract fixes `ReadFixtureHead` and authority inputs, but no accepted codec defines bytes or envelope limits. |
| S2 — freshness/correlation | Mixed: A2-owned nonce, a fresh A3 read, no cached head and no M4/M5-triggered retry are FROZEN; nonce construction, correlation, exchange lifetime and wire replay handling are GENUINELY OPEN. | `CONTROLLER_DELEGATION_CONTRACT.md` requires a nonce and fixes its source, while the accepted modules do not define its representation or exchange state. |
| S3 — two-case P11 lifecycle | Frozen case records, canonical content, independent seals, trusted case authority and no request-selected P11 are FROZEN; initial case/order, same-path sequential provisioning and seal/config invalidation are GENUINELY OPEN. | The fixture manifest and P11 source explicitly mark the two-case native arrangement PENDING G1. |
| S4 — trusted bootstrap | G2 creation/readback origin and the values to be checked are FROZEN; trusted loading, evidence readers, anchoring, post-start delivery and invalidation are GENUINELY OPEN. | Accepted binders/readers compare trusted inputs but explicitly do not authenticate their provenance. P10 is sealed pre-start; live endpoint facts arise after start. |
| M1 — observer/access | **GENUINELY OPEN overall.** A2's connected-handle server-PID check is FROZEN. Direct C-side inspection of service configuration, P6 bytes, or the pipe descriptor conflicts with the proposed C access rows. A protected observer could preserve the required checks, but no current accepted contract binds and delivers its observations to A2. | Topology lines 15, 34, 39 and 51–53 plus the proposed pipe reconciliation. The topology says A2 “checks” facts but does not name a direct-observation API for each fact. |
| M2 — pre/post-start evidence | A pre-start record cannot contain measured live PID/first-instance facts; post-start evidence and invalidation are DERIVABLE. The trusted collector/delivery/lifetime mechanism is GENUINELY OPEN. | P10 is sealed before service start; pipe/PID/retained-handle facts arise at creation/start. No accepted bootstrap handoff closes that temporal gap. |

The classifications and precedence are detailed in [SOL_VS_ASTRA_CLASSIFICATION.md](SOL_VS_ASTRA_CLASSIFICATION.md). The value-by-value authority and observation map is in [OBSERVATION_ACCESS_MAP.md](OBSERVATION_ACCESS_MAP.md).

## L1–L5 decision cells

| Cell | Does accepted record close it? | Can engineering derive one solution? | Required next action | Operator/custody decision? | Accepted contradiction? |
|---|---|---|---|---|---|
| L1 — observer and access | **No.** It freezes checks and the directly observed connected PID, but not who obtains every backing endpoint fact or how evidence reaches A2. | **No.** Direct observation and trusted delegated observation are materially different and both are consistent with the current observer wording; direct C access conflicts with listed rights. | New observer/access/binding design delta. | **Yes if** rights, collector resources, delivery readers, or evidence custody change; otherwise technical design still required. | **No overall.** The direct-C variant conflicts with explicit rows; the requirements do not yet require that variant. |
| L2 — envelope and bounds | **No.** Semantic verb, authority source, transport mode and payload are fixed; encoding and envelope are not. | **No unique format.** Engineering can prepare alternatives and literal vectors, then freeze one exact protocol; the operator need not choose byte fields. | New exact wire-design delta. | Usually no; only if the chosen error/evidence channel changes resources or custody. | No. |
| L3 — freshness and lifetime | **Partial.** A2-owned nonce, fresh read, no cached head and no M4/M5-driven repeat are fixed. Representation, correlation and exchange lifetime are open. | **No unique solution.** A2 nonce-as-ID versus a separate ID and different connection lifetimes are materially different. | New exchange/correlation delta; keep durable replay out unless separately adopted. | Not for ordinary in-memory correlation; yes if persistent state or new protected resource is proposed. | No. |
| L4 — protected bootstrap | **No.** G2 origins and checks are stated; trusted loading and post-start evidence delivery are not. | **No.** P10 cannot carry measured post-start facts; E1 is not readable by C/B and no accepted alternate path exists. | New trusted-source, reader, binding, lifetime and invalidation design delta. | **Yes.** Resource, evidence owner/readers, retention/custody and any rights change require approval. | No proven global contradiction; a design path remains possible but unspecified. |
| L5 — two-case commissioning | **Partial.** Case values and trusted selection are fixed; same-path sequencing and change boundaries are not. | **No unique lifecycle.** Create-only at one path does not choose a safe sequence for two distinct records. | New case-specific manifest/lifecycle delta before provisioning. | **Yes.** Initial case/order, disposable resource sequence and custody/destructive boundary are operator decisions. | No. |

The evidence lineage and precedence are listed in [SOL_VS_ASTRA_CLASSIFICATION.md](SOL_VS_ASTRA_CLASSIFICATION.md); exact permission/source mapping is in [OBSERVATION_ACCESS_MAP.md](OBSERVATION_ACCESS_MAP.md).

## Why this is B, not A or C

### Precedence and source record

The adjudication gives precedence to the corrected minimum contract and controller delegation correction, with the accepted topology and accepted later source slices read as bounded implementations of those contracts. The topology itself says it is a proposal, not G1 approval, and marks identities/rights pending. The controller delegation contract supersedes the loose early writer-result rule; its no-writer-triggered request and fixed P10 authority are carried into the accepted binder and composition. The pipe reconciliation's own status says its runbook/checklist text remains proposed until separately adopted; the v1 gate remains controlling. The accepted P11 review confirms reader/case behavior but expressly leaves wire format, trusted config origin, two-case provisioning and native endpoint observations pending. These precedence constraints are recorded in [SOL_VS_ASTRA_CLASSIFICATION.md](SOL_VS_ASTRA_CLASSIFICATION.md).

Primary repository evidence:

- `s1_g1_preapproval_design/EXACT_TOPOLOGY_PROPOSAL.md` lines 10–15 (role/service DACL), 34–39 (P6/P11/E1 rights), 49–53 (message pipe, client mask, pre-send server check), 59 (collector responsibilities).
- `independent_review_s1_g1_preapproval_design/CREDENTIAL_LAUNCH_AND_PIPE_FINDINGS.md` line 31 (A2 must check/corroborate server PID with start, image, actual process token, SCM and first-instance record); this confirms the required A2 validation but still does not assign a direct observer/API for each fact.
- `s1_g1_design_corrections_after_independent_review/CONTROLLER_DELEGATION_CONTRACT.md` lines 7–11 and 25 (P10 trust source, A2-owned nonce/request fields, fixed order, no writer-triggered request or retry).
- `s1_g1_design_corrections_after_independent_review/MINIMUM_STAGE_A_CONTRACT.md` lines 7–15 and 27 (fresh head, typed failure, canonical head scope and Stage B deferrals).
- `s1_g1_design_corrections_after_independent_review/LOGON_POLICY_AND_PIPE_GATE_RECONCILIATION.md` final pipe paragraphs, paired with `independent_review_s1_g1_design_corrections_v2/RUNBOOK_DELTA_DISPOSITION.md` “Adoption condition” (actual B token/descriptor and first-instance checks; runbook v2 not yet adopted).
- `stage_a_fixture/G1_MANIFEST_DELTA.md` P10/P11 sections and rows 68–80 (canonical records, create-only objects, pending two-case arrangement and pending endpoint facts).
- `stage_a_fixture/authority_binding_increment/SOURCE_DEPENDENCY_MAP.md` “A2 controller,” “A3 broker,” “IPC boundary,” and “Protected P10/P11 objects” (fixed ordered call and pending transport/provenance).
- `independent_review_authority_binding_increment/AUTHORITY_AND_DELEGATION_FINDINGS.md` “Input provenance” and “P10/P11 order and case identity” (plain trusted input structs do not authenticate their source).
- `independent_review_controller_authority_composition_encapsulation/ORDER_AND_FAIL_CLOSED.md` “Implemented order” (one fixed A3 call after token/P10 binding; result-only composition).
- `independent_review_windows_p11_custody_increment/P11_AUTHORITY_AND_IDENTITY_FINDINGS.md`, `NEXT_G1_SOURCE_STEP.md`, and `stage_a_fixture/windows_p11_custody_increment/G1_MANIFEST_DELTA.md` (no request case switch; native response and two-case provisioning still pending).

Sol's `read_fixture_head_design_blocker/NEXT_G1_DECISIONS_REQUIRED.md` and Astra's `astra_review_read_fixture_head_design_blocker/` are the claims being adjudicated, not higher-precedence requirements. Astra's Decision C is not adopted merely because it identifies a direct-access conflict; the text must first establish that direct C observation is mandatory.

**Not A:** L1, L2, L3, L4 and L5 are not all closed. In particular, A2 must not send before server verification, but the accepted record does not say how a trusted observation of B's live service/process/token and the first pipe instance reaches C. Exact framing and correlation are also unresolved. A pure codec cannot be frozen without L2/L3.

**Not C:** the direct-observation interpretation of M1 is incompatible with several explicit proposed rights rows, but the accepted topology does not clearly require direct C-side reads for every corroborating fact. It requires A2 to check the connected endpoint against G2 creation/runtime facts and explicitly names only `GetNamedPipeServerProcessId` on A2's connected handle. Reading the word “checks” as “A2 must open/query every backing object itself” would add an observation-placement rule not stated in the accepted text. A protected G2/BA observer or another reviewed delegation might preserve the same checks; none is yet accepted. That is a real design gap, not proof that all compliant designs are impossible.

The direct-A2 option must not be implemented by adding C service/P6/`READ_CONTROL` rights, debug privilege, or by weakening checks. If the operator/engineering decision is to require direct reads, it needs a versioned topology/rights correction and independent review. If a protected observer is selected, its authority, evidence records, binding to the current connected handle/process lifetime, delivery readers, and invalidation must be reviewed first.

## Required next decisions

1. Resolve L1/L4 together: observer and access for every live fact, trusted record/delivery to A2, and the current-connection binding and invalidation rules.
2. Freeze L2/L3 as an engineering protocol delta: exact application envelope, maxima, pipe-message mapping, one-attempt correlation, malformed/extra-message behavior, and no implicit retries.
3. Obtain the operator/resource decision and reviewed technical sequence for two distinct case-specific P11 records at the one fixed protected path.
4. Keep actual SIDs, process/pipe IDs, descriptors, P10/P11 seals and native behavior as later G2/G3 observations. A design decision does not supply their values or approve commissioning.

No source slice is ready yet. See [NEXT_G1_SOURCE_STEP.md](NEXT_G1_SOURCE_STEP.md).
