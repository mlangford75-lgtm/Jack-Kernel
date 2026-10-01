# Jack Kernel Governing-Document Security Amendment — Phase 5

**Date:** 2026-10-01  
**Status:** Current governing amendment  
**Applies to:** Jack Kernel v0.1.1 documentation set  
**Accepted implementation head:** `551eda0d200fe4b819c3b09cb9480c1ad52f0bdd`  
**Release merge commit:** `eaf0c2e9663bf9b877c51918f7ccead2b07cb1ba`  
**Predecessor:** `GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_4_2026-09-30.md`

## 1. Documentation preservation rule

Jack Kernel documentation remains cumulative.

This amendment does not delete or silently rewrite earlier governing architecture, rationale, limitations, examples, or validation evidence. Earlier Phase 0-3 and Phase-4 records remain historical evidence of their validated checkpoints.

Phase 5 updates the current security interpretation by adding the deterministic Consequence Gate and its minimum-containment rules.

## 2. Governing documents covered

This amendment applies to the same governing documentation set as the Phase-4 amendment, including:

- `00_Jack_Kernel_Plain_English_Master_Guide_v0.1.1.docx`
- `Documentation/Jack_Kernel_Runtime_Specification_v0.1.1.docx`
- `Documentation/Overview/Jack_Kernel_Preview_Programmable_Cognition_Runtime_v0.1.1.docx`
- `Documentation/Research/Jack_Kernel_Long_Horizon_Cognition_Technical_Whitepaper_v0.1.1.docx`
- `README.md`
- `GETTING_STARTED.md`
- `Documentation/Orchestration/ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md`
- `Documentation/Security/Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md`

The core DOCX bodies remain intact. They must now be interpreted together with this Phase-5 amendment for current security behavior.

## 3. Governing Phase-5 invariant

> The Consequence Gate MUST select the smallest disposition sufficient to preserve the violated deterministic invariant. It MUST NOT destroy cognition, state, or unrelated authorized work merely because one consequence cannot proceed.

This means `SecurityOutcome` classifies what happens to the consequence boundary under evaluation. It is not automatically a verdict on the surrounding model response, reasoning trajectory, task, run, worker, connection, or Kernel process.

## 4. Distributed fact production, shared disposition

Phase 5 does not centralize all security knowledge into one subsystem.

Authoritative fact production remains distributed to the subsystem that actually owns the deterministic fact:

- path policy owns represented-path facts;
- executor admission owns live runtime/lane admission facts;
- lifecycle machinery owns task/run/epoch truth;
- evidence machinery owns evidence facts;
- stage/tool machinery owns stage/tool facts;
- approval semantics remain policy-only unless and until a live authoritative producer exists.

The Consequence Gate consumes facts. It does not re-derive them and does not become a filesystem oracle, shell interpreter, executor, or host-effect predictor.

The governing objective is:

> Centralize deterministic consequence disposition without centralizing failure blast radius.

## 5. Security outcomes

The four security outcomes remain:

- `ALLOW`
- `DENY_AND_CONTINUE`
- `REQUIRE_USER_DECISION`
- `HARD_INTERRUPT`

`HARD_INTERRUPT` remains exceptional. It is reserved for an already-established hard-security invariant and does not authorize indiscriminate destruction of unrelated valid cognition or state.

## 6. Minimum containment

Disposition and containment scope are independent concepts.

A violation is contained at the narrowest boundary required by the deterministic invariant.

Examples include:

- NEVER-path violation at tool release -> hard interruption at the affected tool-release batch;
- the same NEVER fact at executor admission -> hard interruption at executor admission;
- Workspace Lock denial -> deny the affected consequence and continue where safe;
- runtime/lane mismatch at executor admission -> deny that admission only;
- forged reserved Jack evidence marker -> deny the evidence fragment rather than invalidate unrelated cognition.

The preservation rule is:

> Reject only the consequence that cannot safely proceed. Preserve everything else whose authority, identity, and integrity remain valid.

## 7. Phase-4 path authority remains authoritative

Phase 4 remains the authoritative source of represented-path facts.

`jack_path_policy.inspect_represented_path(...)` produces the raw facts used by both legacy Phase-4 mapping and Phase-5 consequence disposition.

Phase 5 does not maintain a second normalization or path-policy implementation.

The established limitation remains unchanged:

`RepresentedPath != NecessarilyResolvedObject`

No universal OS-level path-resolution attestation is claimed.

## 8. Kernel-owned installation

The Kernel itself installs Phase 5 through the bundled-runtime-extension seam.

Responses compatibility does not install security.

The Consequence Gate receives the authoritative Kernel module/context through `install(jk)` and uses the Kernel-owned `SecurityOutcome` vocabulary. It does not reconstruct Kernel identity through `__main__`, `sys.modules`, or equivalent import tricks.

## 9. Executor identity boundary

Current live Phase-5 executor identity integration is intentionally narrow:

- `runtime_matches`
- `lane_matches`

A mismatch denies the executor admission boundary without implying task destruction, runtime termination, or unrelated cancellation.

Exact pending tool-call correlation remains with the existing Phase-4 admission machinery and is not falsely reclassified as centralized Phase-5 authority.

## 10. Lifecycle mismatches are intentionally unmapped

The required Phase-5 test matrix separately covers:

- stale task;
- wrong run;
- wrong `run_epoch`.

The current Gate refuses to assign one universal `SecurityOutcome` to those mismatches and instead raises internal `UnmappedAuthorityFact` during direct policy evaluation.

This is deliberate because current Jack semantics are boundary-specific. A mismatched lifecycle marker can mean unrelated input that should be ignored, invalid pending correlation, or another narrow ownership failure depending on the exact seam.

Therefore:

- lifecycle mismatch does not universally mean `DENY_AND_CONTINUE`;
- lifecycle mismatch does not universally mean `HARD_INTERRUPT`;
- no runtime path should surface `UnmappedAuthorityFact` as a broad denial unless that lifecycle fact is deliberately integrated at a grounded consequence boundary.

`UnmappedAuthorityFact` is not a fifth runtime security outcome.

## 11. Evidence interpretation

Phase 5 narrows evidence policy to the grounded violation Jack can deterministically name: forgery of Jack's reserved evidence namespace.

- non-forged reserved namespace state -> `ALLOW`;
- forged reserved namespace state -> `DENY_AND_CONTINUE` with evidence-fragment containment.

Unknown provenance alone is not promoted to a hard-security failure.

Phase 5 does not claim a generalized evidence-trust classifier.

## 12. Approval and security-health nonclaims

Approval remains a policy contract rather than a live runtime authority producer in Phase 5.

The intended missing-approval disposition is `REQUIRE_USER_DECISION` at the affected consequence boundary when a real authoritative approval producer exists.

Phase 5 does not invent a broad `SecurityHealthFact`.

Telemetry, logs, registry state, manifests, UI state, and other observations remain non-authoritative unless separately bound by a deterministic authority contract.

## 13. Cancellation, settlement, and overlap

Phase 5 preserves the existing orchestration distinction:

> Cancellation is not settlement.

Logical cancellation does not prove physical closure.

An open run can block overlapping admission at that narrow boundary without authorizing broader state destruction.

## 14. Validation and release

Accepted implementation head:

`551eda0d200fe4b819c3b09cb9480c1ad52f0bdd`

GitHub Actions run #106 validated that head with:

- `git diff --check`: **PASS**
- runtime compilation: **PASS**
- Phase-5 targeted tests: **37/37 PASS**
- full Python suite: **413/413 PASS**
- Pi harnesses: **7/7 PASS**

The accepted tree was merged to `main` as:

`eaf0c2e9663bf9b877c51918f7ccead2b07cb1ba`

GitHub reported no file differences between the accepted implementation head and the merge commit tree.

Post-merge GitHub Actions run #107 also passed runtime compilation, all 37 targeted Phase-5 tests, all 413 Python tests, and all seven Pi harnesses.

Exact identities and the complete release record are documented in:

`docs/security/SECURITY_LAYER_PHASE5_VALIDATED_2026-10-01.md`

## 15. Explicit nonclaims

Phase 5 does not claim:

- universal host-effect inference;
- arbitrary shell semantic interpretation;
- universal filesystem sandboxing;
- final-object filesystem attestation;
- generalized evidence trust;
- telemetry as authority;
- a live approval subsystem;
- generalized security-health authority;
- one universal lifecycle mismatch severity;
- Phase-6 ledger integrity or cross-runtime serialization.

## 16. Historical preservation

The Phase 0-3 and Phase-4 checkpoints remain immutable historical evidence.

Phase 5 advances current implementation reality without rewriting those earlier validation boundaries.

Phase 6 has not started.
