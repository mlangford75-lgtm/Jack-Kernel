# Historical Build Record

This directory preserves dated build evidence, demonstration runs, validation artifacts, superseded current-state summaries, and other engineering provenance from Jack Kernel development.

Nothing here is deleted merely because implementation reality advances. Historical material remains available for audit, reproducibility, architectural provenance, and comparison with later validated checkpoints.

## How to read this directory

Material in the Historical Build Record may accurately describe an earlier validated state while no longer describing the current runtime. A statement such as “Phase 6 has not started” remains historically correct inside a Phase-5 checkpoint even after Phase 6 is later implemented.

For current repository truth, start with:

- [`/README.md`](../../README.md) — project front door and architecture overview.
- [`/GETTING_STARTED.md`](../../GETTING_STARTED.md) — installation and operational setup.
- [`/CURRENT_SECURITY_STATUS.md`](../../CURRENT_SECURITY_STATUS.md) — current validated security checkpoint and cumulative phase status.

For current governing documentation, see [`/Documentation/`](../).

## Contents

### Exact pre-cleanup user-facing documents

- [`Pre-Cleanup/README_PHASE6_FROZEN_PRE_CLEANUP_2026-10-02.md`](Pre-Cleanup/README_PHASE6_FROZEN_PRE_CLEANUP_2026-10-02.md) — exact README as it existed at the frozen Phase-6 checkpoint before repository cleanup.
- [`Pre-Cleanup/GETTING_STARTED_PHASE6_FROZEN_PRE_CLEANUP_2026-10-02.md`](Pre-Cleanup/GETTING_STARTED_PHASE6_FROZEN_PRE_CLEANUP_2026-10-02.md) — exact Getting Started guide from the same pre-cleanup tree.

These copies preserve every word of the previous GitHub presentation while allowing the active documents to become clearer and current.

### Demonstrations

- [`Demonstrations/Agentic/`](Demonstrations/Agentic/) — preserved Agentic run logs and the Jack XML five-turn case study.
- [`Demonstrations/Debugging/`](Demonstrations/Debugging/) — preserved dated debugging reports, full logs, generated HTML views, and the zero-compaction debugging demonstration.

These are evidence and demonstrations, not current runtime authority.

### Security checkpoint summaries

- [`Security/Phase-5/`](Security/Phase-5/) — root-level Phase-5 checkpoint summary preserved after Phase 6 superseded it as the current checkpoint.
- [`Security/Phase-6/`](Security/Phase-6/) — pre-final-tag Phase-6 closure summary preserved exactly as authored at that stop-gate boundary.

The formal detailed security checkpoint archive remains in [`/docs/security/`](../../docs/security/) so existing validation references and historical links remain stable.

The cumulative governing security amendments and Security Hardening Architecture remain in [`/Documentation/Security/`](../Security/).

### Orchestration history

Orchestration keeps its domain-specific historical evidence beside the current normative documents at [`/Documentation/Orchestration/Historical/`](../Orchestration/Historical/). It is indexed here conceptually but is intentionally not duplicated or moved.

## Preservation rule

The cleanup that created this directory is organizational only. Moving an artifact here does not alter its historical meaning, validation status, authorship, or relationship to the commit/tag at which it was originally accepted.

Current truth comes first in the active documentation. Historical truth remains preserved and clearly labeled as history.
