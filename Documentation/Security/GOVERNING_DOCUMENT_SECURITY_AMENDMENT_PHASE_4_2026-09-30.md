# Jack Kernel Governing-Document Security Amendment ? Phase 4

**Date:** 2026-09-30
**Status:** Current governing amendment
**Applies to:** Jack Kernel v0.1.1 documentation set
**Implementation freeze:** `0e897b801d5b5da8d604cf21556b40da769c26fe`
**Planned checkpoint tag:** `security-layer-phase4-validated-2026-09-30`
**Predecessor:** `GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASES_0_3_2026-09-27.md`

## 1. Documentation preservation rule

Jack Kernel documentation is cumulative.

This amendment does not delete, collapse, or silently rewrite substantive architecture, rationale, limitations, evidence, examples, or historical claims already present in the governing documentation.

Older wording that accurately described an earlier checkpoint remains historical evidence. This Phase-4 amendment supplies the current implementation interpretation.

## 2. Governing documents covered

This amendment applies to:

- `00_Jack_Kernel_Plain_English_Master_Guide_v0.1.1.docx`
- `Documentation/Jack_Kernel_Runtime_Specification_v0.1.1.docx`
- `Documentation/Overview/Jack_Kernel_Preview_Programmable_Cognition_Runtime_v0.1.1.docx`
- `Documentation/Research/Jack_Kernel_Long_Horizon_Cognition_Technical_Whitepaper_v0.1.1.docx`
- `README.md`
- `GETTING_STARTED.md`
- `Documentation/Orchestration/ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md`
- `Documentation/Security/Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md`

Following the Phase 0-3 preservation precedent, the four core DOCX bodies remain intact. They must now be read together with this Phase-4 amendment when interpreting current security implementation reality.

## 3. Governing Phase-4 invariant

> Jack Kernel MUST make configured NEVER paths and an explicitly configured Workspace Lock non-negotiable authority boundaries. It MUST NOT weaken those boundaries because probabilistic cognition requests, rationalizes, retries, or reformulates an unauthorized consequence. Outside those explicit boundaries, Phase 4 MUST NOT discard, suppress, or disable useful work merely because Jack lacks universal knowledge of external execution semantics. When enforcement is necessary, Jack MUST contain the smallest consequential unit compatible with protocol truth and preserve all cognition, evidence, state, and independently valid work that can remain safe.

## 4. Host-owned policy authority

Workspace Lock and NEVER policy are host-owned configuration.

`JACK_PATH_POLICY_JSON` is startup transport only. Authority resides in the immutable runtime policy after construction.

Model output, caller prompt text, caller system/developer content, tool-result text, retry cognition, and ordinary request fields cannot redefine, relax, subtract, or remove the active Workspace Lock or configured NEVER roots.

Host-derived default NEVER roots remain in force. User NEVER roots are cumulative.

## 5. Restricted Paths

Restricted Paths are now validated runtime behavior.

A positive deterministic match against a configured NEVER root produces `HARD_INTERRUPT`.

The implementation performs deterministic represented-path normalization before comparison, including validated Windows handling for standard aliases, deterministic environment expansion, relative components, drive-rooted paths where executor drive is known, and NTFS stream-owner comparison.

## 6. Workspace Lock

Workspace Lock is optional and explicit.

When configured, a deterministically outside filesystem consequence is denied with `DENY_AND_CONTINUE` unless a stronger NEVER rule applies.

That denial does not automatically invalidate the cognitive session.

No workspace is invented when none is configured.

## 7. Non-brittleness

Phase 4 does not convert lack of universal execution knowledge into a security violation.

Pathless commands remain usable where no filesystem consequence exists.

Deterministic non-filesystem PowerShell providers remain outside Phase-4 filesystem authority.

Absolute in-workspace targets are not denied because incidental cwd is elsewhere.

Relative and cwd-scoped filesystem consequences remain bound to authoritative executor cwd.

## 8. Consequence surfaces

Validated enforcement covers:

- structured path-capable tool calls;
- recognized Bash/PowerShell command forms;
- non-stream tool-call release;
- streaming tool-call release;
- executor admission;
- multi-call minimum containment.

Unknown custom tool semantics are not invented merely from superficial argument names.

## 9. Path Resolution Gap

The earlier architectural limitation remains in force:

`RepresentedPath != NecessarilyResolvedObject`

Jack authorizes represented targets it can deterministically observe. It does not claim descriptor-level proof of the final filesystem object reached through symlinks, junctions, reparse points, mounts, or hard-link relationships.

Object-level confinement belongs at the executor/OS boundary.

## 10. Orchestration relationship

Phase-4 security authority does not collapse orchestration lifecycle authority.

A path denial or hard interrupt does not authorize a supervisor to fabricate task cancellation, settlement, worker termination, run ownership, or telemetry state.

Security outcome, runtime observability, task/run lifecycle, cancellation, and physical settlement remain separate deterministic domains.

## 11. Validation

Implementation freeze `0e897b801d5b5da8d604cf21556b40da769c26fe` passed:

- **201/201** targeted Phase-4 tests;
- **376/376** full Python tests;
- **7/7** Pi harnesses;
- clean `git diff --check`.

Exact identities are recorded in:

`docs/security/SECURITY_LAYER_PHASE4_VALIDATED_2026-09-30.md`

## 12. Historical preservation

The Phase 0-3 checkpoint and tag remain immutable evidence of the earlier validated state.

Phase 4 advances current implementation reality without rewriting that history.
