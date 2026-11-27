# Jack Kernel Documentation

This directory contains the current governing, architectural, research, orchestration, and security documentation for Jack Kernel v0.1.1.

For a new user, read in this order:

1. [`../README.md`](../README.md) — what Jack Kernel is, what it owns, and the current architecture.
2. [`../GETTING_STARTED.md`](../GETTING_STARTED.md) — installation and operational setup.
3. [`../00_Jack_Kernel_Plain_English_Master_Guide_v0.1.1.docx`](../00_Jack_Kernel_Plain_English_Master_Guide_v0.1.1.docx) — full plain-English guide.
4. [`../CURRENT_SECURITY_STATUS.md`](../CURRENT_SECURITY_STATUS.md) — current validated security checkpoint.

## Normative runtime documentation

- [`Jack_Kernel_Runtime_Specification_v0.1.1.docx`](Jack_Kernel_Runtime_Specification_v0.1.1.docx) — normative runtime specification.

## Overview

- [`Overview/Jack_Kernel_Preview_Programmable_Cognition_Runtime_v0.1.1.docx`](Overview/Jack_Kernel_Preview_Programmable_Cognition_Runtime_v0.1.1.docx) — concise public overview of Jack as a programmable cognition runtime.

## Research

- [`Research/Jack_Kernel_Long_Horizon_Cognition_Technical_Whitepaper_v0.1.1.docx`](Research/Jack_Kernel_Long_Horizon_Cognition_Technical_Whitepaper_v0.1.1.docx) — research and architectural treatment of long-horizon cognition.

## Local Agentic (Preserve Thinking)

- **Current runtime:** see the [root README](../README.md#local-agentic-preserve-thinking--current-runtime-contract) for the source-only, tools-off retrospective, authenticated history, current profile selectors and tool-free Coder Architect contract.
- **Historical implementation:** [`October 21 operating contract`](Agentic/AGENTIC_PRESERVE_THINKING_2026-10-21.md) preserves the earlier one-hop bridge and Phase 3E cache-append design; these are not current runtime guarantees.
- **Local Phase 3E test checkpoint:** [`October 22 three-turn cache and memory findings`](Agentic/LOCAL_AGENTIC_PHASE3E_CHECKPOINT_2026-10-22.md) — observed cache reuse with no demonstrated functional regression in the tested workload; not a controlled A/B speedup.
- **Historical precursor:** [`October 15 retrospective-memory release candidate`](Agentic/AGENTIC_RETROSPECTIVE_MEMORY_RELEASE_2026-10-15.md) — retained for design provenance only; its unmerged status is superseded by [PR #57](https://github.com/mlangford75-lgtm/Jack-Kernel/pull/57). Prior DOCX descriptions of the XML-based predecessor are dated references, not the current mode.

## Deep Reasoning

- **Deep Reasoning** — Thesis → Antithesis → Synthesis.

## Orchestration

- [`Orchestration/README.md`](Orchestration/README.md) — current navigation and interaction notes.
- [`Orchestration/ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md`](Orchestration/ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md) — canonical protocol, lifecycle, authority, and compatibility contract.
- [`Orchestration/ORCHESTRATOR_INSTRUCTIONS.md`](Orchestration/ORCHESTRATOR_INSTRUCTIONS.md) — supervisory-agent operating instructions.
- [`Orchestration/Historical/`](Orchestration/Historical/) — dated acceptance evidence.

## Security

- [`Security/README.md`](Security/README.md) — current security-document map.
- [`Security/Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md`](Security/Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md) — full hardening design and implementation-status history.
- cumulative governing amendments for Phases 0–6 remain in [`Security/`](Security/).
- exact detailed phase checkpoints remain under [`../docs/security/`](../docs/security/).

See [Current Security Status](../CURRENT_SECURITY_STATUS.md) for the current validated security lineage. [Phase 9A research closed without enforcement](../docs/security/SECURITY_LAYER_PHASE9A_RESEARCH_CHECKPOINT_2026-10-14.md) is a dated checkpoint, not a statement of the current enforcement boundary. The [independent audit register](Independent_Audit_Remediation_Register.md) records experimental remediation and qualification, not a merged release guarantee.

## Historical Build Record

[`Historical-Build-Record/`](Historical-Build-Record/) preserves demonstrations, generated reports, superseded root checkpoint summaries, and exact pre-cleanup user-facing documents.

Historical evidence is retained for provenance and reproducibility. It does not supersede the active README, Getting Started guide, current security status, or current normative documentation.
