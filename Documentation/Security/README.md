# Security Documentation

Jack Kernel's security documentation is cumulative. Current implementation truth and historical checkpoint evidence are intentionally separated so earlier validation records remain intact while users can still identify the present runtime state immediately.

## Current validated security state

Start with [`../../CURRENT_SECURITY_STATUS.md`](../../CURRENT_SECURITY_STATUS.md).

Current checkpoint:

- **Phase 7 — Credential Isolation and Integrated DLP**
- validated tag: `security-layer-phase7-validated-2026-10-05`
- annotated tag object: `ffde3865178ac14c44d6222a39e0e59e6d8518a9`
- validated closure target: `59aef730e11031b23f67c735e35f1e68c9ecc394`
- status: **VALIDATED / MERGED / DOCUMENTED / TAGGED / FROZEN**

Phases 8–11 have not started.

## Governing security architecture

[`Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md`](Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md) preserves the complete hardening design and its dated implementation-status updates.

Some status notes inside that paper describe earlier checkpoints. Those notes are historical implementation records, not the current repository checkpoint. Use `CURRENT_SECURITY_STATUS.md` for present truth.

## Cumulative governing amendments

- [`GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASES_0_3_2026-09-27.md`](GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASES_0_3_2026-09-27.md)
- [`GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_4_2026-09-30.md`](GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_4_2026-09-30.md)
- [`GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_5_2026-10-01.md`](GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_5_2026-10-01.md)
- [`GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_6_2026-10-02.md`](GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_6_2026-10-02.md)

These amendments preserve the state and claims accepted at their respective phase boundaries. Later validated phases add current implementation reality without silently rewriting earlier records.

## Detailed checkpoint archive

Exact phase validation records, implementation identities, regression counts, and nonclaims are preserved under [`../../docs/security/`](../../docs/security/).

The archive contains:

- Phases 0–3 validated checkpoint
- Phase 4 validated checkpoint
- Phase 5 validated checkpoint
- Phase 6 validated checkpoint / closure record
- Phase 7 validated closure record

The Phase-7 detailed closure record was authored before the final annotated tag existed. Its pre-tag freeze wording is historical process-state evidence. The completed Phase-7 tag identity is recorded in `CURRENT_SECURITY_STATUS.md`.

## Governing interpretation

Current security behavior must be interpreted cumulatively:

- Phases 0–3 own the validated release-boundary security substrate and Canary behavior;
- Phase 4 owns represented-path fact production and path-policy semantics;
- Phase 5 owns deterministic consequence disposition;
- Phase 6 owns the process-local authority/security chain and bounded forensic projection semantics;
- Phase 7 adds closed known-credential authority, exact model ingress/egress DLP, orchestration and diagnostic release protection, exact credential-resource containment, and safe Phase-7 observations in the existing Phase-6 chain.

No Phase 8–11 implementation should be inferred from design sections alone. Those later phases remain unimplemented until separately built, tested, documented, and checkpointed.
