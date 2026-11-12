# Jack Agentic — Execution Continuity and Stage 2 Simplification
**Engineering specification · November 12, 2026 · Jonathan M. Langford**

## Authoritative architectural decisions

1. **Distilled native reasoning is assumed superior to raw native reasoning** for downstream work. Preserve consequential discoveries, causal lessons, decisions, corrections, constraints and unresolved matters through Stage 2. Prune redundant historical native R1/R2 after a successful memory commit; do not reopen the philosophical assumption for benchmarking.
2. **Jack must never degrade the baseline agent's tool capabilities, history or execution evidence.** Actual tool calls, exact arguments, result contents, result status, order, failures and recovery remain available to subsequent Stage 1 turns. No arbitrary token, character or count budget for tool history.
3. **Stage 1 executes; Stage 2 distills.** Stage 1 remains the only stage with execution authority. Stage 2 is current-turn-only, tools-off, preserves consequential working knowledge, and never invents execution facts. Host-owned evidence is authoritative on what calls returned; return does not establish on-disk correctness absent read-back.
4. **Preserve Thinking is optional.** Both stages must function when native reasoning is unavailable. Qwen models can derive additional value from native reasoning, but no baseline memory or tool-evidence guarantee depends on it.
5. **Remove optional Stage 2 extensions.** No Stage 2 review or verification extension or legacy toggle in any Agentic profile. Keep its central memory directive and host evidence classification intact. Thorough's optional Stage 1 review is independent.
6. **Accuracy takes priority over artificial tool-context savings.** If a better full-fidelity, recoverable representation is later developed, it can replace raw protocol only once it preserves equal-or-greater downstream utility and exact facts. Until then, retain the records.

## Concrete defects prompting this change

The analog-clock task included successful `write` tool calls for `index.html`, `style.css` and `script.js`. On a later turn, Stage 1 treated those writes as absent, then rewrote files. Jack's historical projection discarded completed raw tool calls/results and omitted its host receipt from model-facing memory. A separate 4,800-character receipt budget could also remove past evidence.

The November 11 Nemotron ten-turn state run demonstrated accurate cognitive-state continuity on a tools-free task, including a changed budget, replacement, arithmetic and recall. Its scope did not cover tool history. Preserve the proven cognitive topology and fix the deterministic execution evidence.

## Contracts

| Component | Responsibilities | Must not |
| --- | --- | --- |
| Stage 1 | Reason, execute, inspect, recover, verify, integrate prior memory and exact tool history | Interpret absent historical protocol after kernel pruning as proof of nonexecution |
| Stage 2 | Distill **only current-turn** reasoning (if present), frozen answer, user request and authenticated host tool evidence | Execute tools, review unrelated turns, replay task, introduce a separate verification extension |
| Jack host | Record and preserve tool calls/args/results in chronological order and classify provenance | Drop raw history merely to save context; substitute hash-only summaries; misreport successful return as verified disk effect |
| Completed-turn projection | Preserve U / M / A1 plus original tool protocol; prune historical R1/R2 | Remove completed tool calls/results or host receipts because of arbitrary budgets |

## Required lifecycle

- **Tool continuation:** retain the valid assistant `tool_calls` / `tool` result sequence in the active Stage 1 transaction, including explicit failures and recoveries; preserve cache-sensitive stage topology and original ordering.
- **Stage 1 terminal:** freeze its exact answer and keep authentic tool evidence for Stage 2. Do not prematurely erase evidence.
- **Stage 2:** isolated, tools-off distillation from current request, native R1 if present, frozen A1 and host evidence. Distinguish attempted, reported, completed and independently verified.
- **Successful commit:** append Stage 2 consequential memory and the frozen answer; prune old native reasoning. Keep tool history available to the next Stage 1 and across process restarts when client history or authenticated persistence provides it.
- **Failure:** preserve completed work, report incomplete/unknown state accurately, and retain enough evidence for safe retry. Never infer that a missing entry means no tool execution occurred.

## Surgical implementation targets

- Remove the `_AGENTIC_TOOL_CONTEXT_BUDGET_CHARS` value and the historical receipt-truncation routine.
- Retain caller-replayed raw historical `tool_calls` and `tool` messages in `_compact_agentic_completed_capsules`.
- Expose authenticated historical host receipts to subsequent Stage 1 projections, without treating them as commands.
- Maintain Stage 2's isolated view; do not force full transcripts into its own memory output.
- Delete unused optional Stage 2 extension toggles and review suffix; retain core Prime Directive and stage authority.
- Update deterministic regression checks for tool order, exact argument/result payload, current-turn Stage 2 isolation, default profile, and native reasoning retirement.

## Promotion

Apply to the experimental branch first. Run targeted and existing CI. Transfer only the verified corrective changes to main after branch-specific review; don't broadly merge unrelated experimental differences. Verify with a freshly cloned Windows checkout, not an existing local folder.

This document is a design specification. It does not claim that a tool's returned success proves an independently verified filesystem effect.
