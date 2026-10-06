# Security Documentation

Jack Kernel's security documentation is cumulative. Current implementation truth and historical checkpoint evidence are intentionally separated so earlier validation records remain intact while users can still identify the present runtime state immediately.

## Current validated security state

Start with [`../../CURRENT_SECURITY_STATUS.md`](../../CURRENT_SECURITY_STATUS.md).

Current checkpoint:

- **Phase 8 — Active Source Authority / Source Drift Protection**
- validated tag: `security-layer-phase8-validated-2026-10-06`
- annotated tag object: `20e35610444f409bbccd62a461e42e2dce06ac6a`
- validated closure target: `cebe9fd75fe30a9c84a0af08d2105af448fc3d00`
- validated closure tree: `7288396653db3590834d9ac1093207c4e1b19c3b`
- closure-complete Windows CI #218: **PASS**
- status: **VALIDATED / MERGED / DOCUMENTED / TAGGED / FROZEN**
- tag state: **unsigned annotated tag**

Post-freeze repository status publication:

- current `main`: `7e00f7209ccb168387da2bbd2fd2344e57c2f82d`
- current `main` tree: `cde43597139637a461c04d446d7d165dea1fa46b`
- post-freeze Windows CI #220: **PASS**

The immutable Phase-8 tag remains pinned to the CI-validated closure commit above. The later `main` commit publishes already-verified frozen status only; it does not move the tag or redefine Phase-8 runtime behavior.

**Phase 9: NOT STARTED.**

## Governing security architecture

[`Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md`](Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md) preserves the complete hardening design and its dated implementation-status updates.

Status notes inside that paper describe the repository at the dates printed in those notes. They are historical implementation records, not the current repository checkpoint. Use `CURRENT_SECURITY_STATUS.md` for present truth.

## Cumulative governing amendments

The formal governing-amendment series currently preserved in this directory is:

- [`GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASES_0_3_2026-09-27.md`](GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASES_0_3_2026-09-27.md)
- [`GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_4_2026-09-30.md`](GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_4_2026-09-30.md)
- [`GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_5_2026-10-01.md`](GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_5_2026-10-01.md)
- [`GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_6_2026-10-02.md`](GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_6_2026-10-02.md)

These amendments preserve the state and claims accepted at their respective phase boundaries. The formal amendment-file series stops at Phase 6; this does **not** mean later validated phases are absent or provisional. Current validated Phase-7 and Phase-8 implementation truth is recorded in `CURRENT_SECURITY_STATUS.md` and the exact validated closure records under `docs/security/`.

Older governing papers and amendments are not silently rewritten merely because later implementation exists.

## Detailed checkpoint archive

Exact phase validation records, implementation identities, regression counts, and nonclaims are preserved under [`../../docs/security/`](../../docs/security/).

The archive contains:

- Phases 0–3 validated checkpoint
- Phase 4 validated checkpoint
- Phase 5 validated checkpoint
- Phase 6 validated checkpoint / closure record
- Phase 7 validated closure record
- Phase 8 validated frozen closure record

Current Phase-8 closure record:

- [`../../docs/security/SECURITY_LAYER_PHASE8_VALIDATED_2026-10-06.md`](../../docs/security/SECURITY_LAYER_PHASE8_VALIDATED_2026-10-06.md)

The Phase-7 detailed closure record preserves pre-tag process wording from before the final Phase-7 annotated tag existed. That wording is historical process-state evidence, not current repository status.

The Phase-8 detailed closure record has been reconciled after independent annotated-tag verification and is the authoritative frozen Phase-8 checkpoint record.

## Governing interpretation

Current security behavior must be interpreted cumulatively:

- Phases 0–3 own the validated release-boundary security substrate and Canary behavior;
- Phase 4 owns represented-path fact production and path-policy semantics;
- Phase 5 owns deterministic consequence disposition;
- Phase 6 owns the process-local authority/security chain and bounded forensic projection semantics;
- Phase 7 adds closed known-credential authority, exact model ingress/egress DLP, orchestration and diagnostic release protection, exact credential-resource containment, and safe Phase-7 observations in the existing Phase-6 chain;
- Phase 8 adds bounded active-runtime source authority: immutable protected-source baseline, exact bounded remeasurement, `ACTIVE` / `SUSPENDED_UNVERIFIED` / `INVALIDATED` lifecycle, preservation-aware runtime enforcement, fail-soft lifecycle observation, concurrency-safe forensic ordering, and adversarial anti-brittleness closure.

Permanent Phase-8 preservation statement:

> **Source-authority loss withdraws new Kernel-authoritative admission. It does not imply process death, blanket cancellation, invented worker failure, erasure of completed cognition, or loss of safe observation.**

Permanent Phase-8 execution boundary:

> **Phase 8 serializes Kernel-authoritative admission, not physical continuous-world execution after an admission already occurred.**

Permanent Phase-8 nonclaim:

> **Phase 8 protects active-runtime source identity through bounded exact measurements. It does not provide continuous historical attestation, loaded-code/function-binding integrity, authority-state integrity, universal filesystem-object identity, or hostile in-process tamper resistance.**

Phase 9 remains a separate, not-yet-started boundary for loaded modules, function bindings, and code objects. Phase 10 remains the separate authority-state-integrity boundary. Phase 11 remains the separate privacy/telemetry-hardening boundary.
