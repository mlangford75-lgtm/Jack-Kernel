# Agentic (Preserve Thinking) — October 15 Retrospective Memory Precursor

> **ARCHIVED DEVELOPMENT RECORD (October 15, 2026).** This document describes a historical release candidate and retains its dated validation/status claims as evidence of the development timeline. The implemented successor, **Agentic (Preserve Thinking)**, was merged through [PR #57](https://github.com/mlangford75-lgtm/Jack-Kernel/pull/57). Refer to the [current implementation contract](AGENTIC_PRESERVE_THINKING_2026-10-21.md) for active behavior. The XML excerpts below are historical examples, not a second selectable mode.

**Status:** Release candidate on `release/agentic-retrospective-memory-20261015`. Not merged or tagged until validation is complete.

**Scope:** The Agentic cognition program on Jack Kernel v0.1.1. This is **not** a new security validation phase.

## Architecture and authority

Jack is the **Kernel**, not the agent or language model. Agentic is one programmable cognition topology managed by Jack. The fundamental authority rule remains:

> Probabilistic cognition may propose, but deterministic software must dispose.

Stage 1 is the substantive model cognition and tool-use stage. It creates the user-facing answer, **A1**, which Jack freezes exactly. Stage 2 is a separate, **tools-off**, **zero-answer-authority** retrospective memory stage. Stage 2 cannot replace, repair, or independently verify A1.

### Stage 1 — native reasoning

Current minimal Stage-1 instruction:

```text
Reasoning effort is set to xhigh. Please think carefully through the task, validate key assumptions, consider plausible alternatives, and prioritize correctness, consistency, and clarity in the final answer.
```

The native model may reason extensively and use authorized tools. Stage 1's response is frozen after substantive work completes.

### Stage 2 — retrospective distillation

Current minimal Stage-2 instruction:

```text
Generate a detailed summary of why you came to this conclusion.
```

The Kernel also supplies a same-turn continuation directive so that the model interprets Stage 2 as retrospective explanation of the **already completed Stage-1 answer**, not as a new user request. When the backend exposes native reasoning across this stage transition, Stage 2 can draw on Stage-1 thinking and observed tool outcomes. Transport of native reasoning is backend/model dependent and should not be assumed universally.

Unlike the prior Agentic design, the current Stage 2 is **not** an instruction-heavy `<Jack XML>` audit with grounding/verification/challenge/audit forms. It produces a model-authored narrative of why the answer was reached. This narrative is **semantic memory**, not independently verified evidence.

## Host-owned completed-turn capsule

The Kernel wraps memory and A1 in a completed assistant response:

```text
<Agentic Memory>
[Stage-2 retrospective reasoning summary]
[Jack Tool History - Host-Recorded Receipt]
[bounded host-recorded tool result metadata, if any]
[/Jack Tool History - Host-Recorded Receipt]
</Agentic Memory>

<Model Response>
[exact frozen Stage-1 A1]
```

The tool receipt section is optional. The Kernel creates the structural wrapper and receipt metadata; it does not ask the model to invent a tool ledger. Implementation constants currently limit the host receipt projection to the last **six** entries and **2,400 characters** per completed turn, with a **4,800-character** cross-turn host-receipt budget. These budgets do **not** cap user text, A1, or Stage-2 semantic memory.

Tool receipts record selected call identity, represented target, error/returned-result status, and cryptographic hashes. They do not prove the tool's requested effect occurred, establish its resolved working directory, or grant execution authority.

## Pruning and continuity

After the completed turn, the Kernel's Agentic context projection retains the original user request, the distilled memory, the exact frozen answer, and bounded retained host receipts as applicable. Completed native reasoning, consumed tool protocols, and obsolete intermediate stage traffic are retired from **subsequent** model-facing context. Stage-1/Stage-2 reasoning still incurs its full active-turn context and inference cost.

A client-side context percentage or cumulative input-token count is not a reliable measurement of **post-pruning** model input. The decisive metric is the actual next backend request after Kernel projection.

The design aims to retain useful causal decisions, failed attempts, resolved constraints, and task continuity without retaining raw multi-turn reasoning. It does **not** guarantee perfect memory extraction, and a model-authored retrospective should not be promoted to deterministic tool proof.

## Evidence and limits

October 15 local interactive tests exercised a local 16 GB GPU, reasoning-heavy quantized models, multi-turn webpage editing, tool errors, design revisions, and later reflective tasks. The visible Stage-1 reasoning was substantially larger than the resulting Stage-2 memory while subsequent work retained useful task continuity.

These tests demonstrate promising real-world behavior but are not a controlled native-versus-Jack quality benchmark, exact post-pruning backend token measurement, or new security validation.

The change set in local commit `88f3cd2` is restricted to `jack_kernel.py` and replaces the old Stage-2 XML prompts and output format, adds bounded host tool receipts, and introduces completed-turn receipt pruning.

## Release validation — not yet complete

The local October 15 run reported:

- Runtime syntax compilation: passed.
- Git whitespace validation: passed.
- Python regression tests: **525 passed, 2 failed**, both failing in fresh subprocesses because `httpx` was not importable in the isolated test environment. A clean virtual-environment rerun and/or GitHub CI is required.
- Pi Node harnesses: **seven passed**.

Before merge, confirm a clean environment, full Python and Pi regression results, and Agentic-specific tests covering exact A1, same-turn Stage 2, host-owned boundaries, receipt budgets, historical tool-result handling, and context pruning. The source's introductory Agentic docstring also still describes the preceding XML audit schema and should be corrected before release. Review the Stage-2 continuation string's encoding before release.

## Scope boundaries

This Agentic update does not alter or supersede the validated Phase-8 security checkpoint. Phase 9A remains research-only; Phase 9B runtime-code-integrity enforcement is not implemented. Historic validation tags remain untouched.

The four other planned/available cognition topologies and multi-endpoint orchestration are independent of this Agentic release; future multi-mode autonomous orchestration is not claimed as a shipped capability here.
