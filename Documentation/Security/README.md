# Security Documentation

Jack Kernel's security documentation is cumulative. Current implementation truth and historical checkpoint evidence are intentionally separated so earlier validation records remain intact while users can still identify the present runtime state immediately.

## Current validated security state

Start with [`../../CURRENT_SECURITY_STATUS.md`](../../CURRENT_SECURITY_STATUS.md).

Current checkpoint:

- **Phase 6 — Runtime-Scoped Authority & Security Ledger**
- validated tag: `security-layer-phase6-validated-2026-10-02`
- annotated tag object: `1e46b9872db66cc3944b79550aa30509b4c84296`
- validated closure target: `51e29b197ab62db410e6b4b43c92688ba613826f`
- status: **VALIDATED / MERGED / DOCUMENTED / TAGGED / FROZEN**

Phase 7 and Phases 8–11 have not started.

## Governing security architecture

[`Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md`](Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md) preserves the complete hardening design and its dated implementation-status updates.

Some status notes near the top of that paper describe earlier checkpoints, such as implementation through Phase 4. Those notes are historical implementation records, not the current repository checkpoint. Use `CURRENT_SECURITY_STATUS.md` for present truth.

## Cumulative governing amendments

- [`GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASES_0_3_2026-09-27.md`](GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASES_0_3_2026-09-27.md)
- [`GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_4_2026-09-30.md`](GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_4_2026-09-30.md)
- [`GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_5_2026-10-01.md`](GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_5_2026-10-01.md)
- [`GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_6_2026-10-02.md`](GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_6_2026-10-02.md)

These amendments preserve the state and claims accepted at their respective phase boundaries. Later phases add current implementation reality without silently rewriting the earlier records.

## Detailed checkpoint archive

Exact phase validation records, implementation identities, regression counts, and nonclaims are preserved under [`../../docs/security/`](../../docs/security/).

The archive contains:

- Phases 0–3 validated checkpoint
- Phase 4 validated checkpoint
- Phase 5 validated checkpoint
- Phase 6 validated checkpoint candidate / closure record

The Phase-6 detailed record was authored before the final annotated tag existed. Its pre-tag candidate language is therefore historical process-state evidence. The completed checkpoint identity is recorded in `CURRENT_SECURITY_STATUS.md`.

## Governing interpretation

Current security behavior must be interpreted cumulatively:

- Phases 0–3 own the validated release-boundary security substrate and Canary behavior;
- Phase 4 owns represented-path fact production and path-policy semantics;
- Phase 5 owns deterministic consequence disposition;
- Phase 6 records selected established authority/security events without becoming the source of those facts.

Later phase implementation must not be inferred from design sections alone. Phase 7 and Phases 8–11 remain unimplemented until separately built, tested, documented, and checkpointed.
