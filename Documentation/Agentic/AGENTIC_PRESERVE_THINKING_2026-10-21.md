# Agentic (Preserve Thinking)

**Status:** Active replacement of the prior Agentic runtime implementation; retain the historical Agentic documents as archival descriptions rather than alternate live modes.

**Selector:** `JACK_REASONING_LEVEL=agentic`. **Display label:** `Agentic (Preserve Thinking)`.

Jack Kernel orchestrates this mode. The model generates cognition and proposes authorized tool calls; the host owns stage transitions, tool execution, identity/provenance, historical projection, and authoritative final-answer freezing. The native model's intelligence is not the same thing as the Kernel's contribution.

## Turn lifecycle

1. Stage 1 receives the current user turn and a host-projected authenticated history. It performs native reasoning and any permitted tools and generates **A1**, the answer frozen verbatim by the host.
2. Stage 2 is a tools-off retrospective memory operation, **M**, that considers the completed Stage-1 trajectory and explains why A1 was reached. This stage cannot revise A1 or independently certify an external effect.
3. The host retains distinct historical **U** (original user request), **M** (model-authored retrospective with host-owned provenance and bounded tool receipts), and **A** (the exact frozen answer) artifacts.
4. A completed turn's consumed tool-call protocol, older native reasoning, and internal stage scaffolding are retired from later model-facing context. The immediately preceding Stage-2 native reasoning may be carried into the following Stage 1 once and then retired. The next turn need not inherit the entire previous active trajectory.
5. Receipt status `RESULT_RETURNED` means a tool response was received, not that a requested on-disk change was independently verified. Follow-up read-back remains the evidence for file contents.

Stage-1 and Stage-2 cognition prompts remain as implemented; this release does not rewrite them. The label is a presentation change only. Historical XML parsing may be retained for reading old sessions, but the prior XML-audit mode is not a separately selectable live mode.

## Implementation milestones

- Phase 1 — untrusted identity/session hints do not authorize historical memory projection.
- Phase 2 — separate U/A/M artifacts and answer freezing.
- Phase 3A/B — user-origin and host-minted turn identity/lifecycle.
- Phase 3C — authenticated historical M/A projection and safe fallback.
- Phase 3D — immediate predecessor Stage-2 reasoning one-hop bridge and retirement.
- Phase 3E — LM Studio Stage-2 cache append, **enabled by default**; `JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT=0` restores the legacy request layout. Non-LM Studio backends and forced/named tool-choice Stage-2 requests retain the legacy layout. This changes the Stage-2 request role/representation, not either stage's prompt text. The three-turn local LM Studio experiment demonstrated cache reuse and successful retrospective memory production, but did not establish a same-workload disabled/enabled speedup.
- Phase 3F — optional reporting of request-byte/context-category sizes (`JACK_AGENTIC_CONTEXT_ACCOUNTING=1`); `JACK_AGENTIC_CONTEXT_REPORT_BUDGET_BYTES` is a reporting threshold, **not** a truncation budget.

## Evidence and limits

Local targeted Agentic regression tests passed on the inspected snapshot. Interactive Pi/LM Studio six-turn inventory and multi-turn clock debugging provided evidence of successful work continuation, historical recall, tool-use continuity, and backend omission of completed tool protocols in subsequent model requests. One earlier run exhibited temporary Stage-1/retrospective-format contamination; user-visible repeats are not, by themselves, evidence of duplicate model-facing requests.

These are operational observations, not proof that the model is more accurate under Jack than under an otherwise identical native Pi baseline. Some local model quantizations looped under load; that is not by itself a demonstrated Kernel defect. LM Studio may interpret a requested `xhigh` reasoning effort as `on` when that is all a specific quantization supports.

## Scope

This release replaces **only** the prior XML-based Agentic cognition topology. It does not remove the three-stage cognition family (publicly documented as **Deep Reasoning**), Code Debugging, security phases, or standard native inference. It does not advance the security validation baseline beyond Phase 8 or implement Phase 9B enforcement.
