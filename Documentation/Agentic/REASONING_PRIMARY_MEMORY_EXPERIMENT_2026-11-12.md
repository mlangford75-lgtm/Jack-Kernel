# Reasoning-primary retrospective memory experiment

**Status:** Opt-in prototype on `experiment/agentic-reasoning-primary-memory-20261112`. Mainline unchanged.

## Why

Jack already retains the authenticated original user request, frozen completed answer, and observed tool evidence in its canonical turn/history. The model's unique responsibility in the retrospective is to preserve **consequential working knowledge from native reasoning** before historical reasoning is retired. The November 12 Night Market test showed that including the entire original request and completed answer encouraged copies of the user-facing `STATE CARD`. The subsequent JSON task-line instruction did not eliminate copying.

## Enabling the A/B experiment

PowerShell, **before** launching Jack:

```powershell
$env:JACK_AGENTIC_REASONING_PRIMARY_EXPERIMENT = "1"
# Then launch from a fresh clone of this branch:
.\start.bat
```

To use the unchanged comparison projection:

```powershell
$env:JACK_AGENTIC_REASONING_PRIMARY_EXPERIMENT = "0"
.\start.bat
```

The switch defaults to OFF. It changes **only the retrospective model's input projection and associated plain-language instruction** when native initial reasoning exists. The original request and frozen answer remain intact in Jack's canonical state and following-turn history. No tools are granted to the retrospective, and no new memory-output validator or similarity gate is introduced.

## Experimental model-facing instruction

> Your task is to preserve useful working knowledge from the preceding reasoning. The reasoning is source material, not a new request to answer.
>
> Keep consequential discoveries, decisions and their explanations, exact technical details, constraints, important mistakes and corrections, established failure causes, reusable procedures, and unresolved matters. Preserve original meaning and important qualifications. Distinguish possibilities considered from conclusions reached, and attempted or reported actions from outcomes actually verified.
>
> Do not solve the original task again, copy a completed answer's presentation, invent missing information, or describe the summarization process. Remove repetitive deliberation and conversational filler, but retain every detail needed for future work.
>
> Output only the resulting working knowledge. If no consequential working knowledge is present in the available reasoning, say so plainly.

**No proprietary Jack terms, internal stage numbers, memory IDs or mandatory JSON output appear in the model instruction.** Those concepts belong to host code only.

## Behavioral and fallback contract

- Host validates current-turn ownership and exact frozen answer presence before constructing the retrospective view.
- The model sees native reasoning collected across current-turn tool continuations; it does not see the original request, final answer or host tool note in the experimental view.
- If there is **no native reasoning**, or initial thinking is OFF (Flash), the prototype uses the established retrospective projection instead of silently inventing reasoning or discarding U/A.
- Canonical host history, tool calls/results/receipts, UUID/fingerprints, the frozen answer, and historical retirement policy remain unchanged.
- The opt-in prototype uses an independent model-facing system directive, so it does **not** claim that the legacy cache-append path remains cache-equivalent. Measure actual prefill and latency.
- A nonempty model-authored memory is still not deterministic proof of a tool result or factual correctness.

## Tests and evaluation

Targeted source assertions are in `tests/test_agentic_reasoning_primary_memory_experiment.py`. Run the full Python suite on a clean clone before interpreting the prototype. Also capture streaming and nonstreaming backend request bodies to confirm identical isolation and absence of untrusted caller system content.

Matched live A/B: use the same model, hardware, quantization, settings and task script; compare baseline vs opt-in on the 10-turn Night Market, a complex file edit with failure/recovery, and code+verification turns.

Judge **consequential knowledge fidelity**, uncertainty labeling, no fabricated execution, cross-turn recall, answer copying, tool recovery continuity, exact A1 bytes, prompt/context cost, and next-turn JSON/format imitation. Shorter memory alone is not success. Do not merge to main until verified results support a net improvement.

## Current archival reality

The existing `jack_agentic_forensics.py` SQLite journal retains fingerprints and statuses, **not independently retrievable full source text**. The *Agentic History Upgrade — Index-First Revised* remains the proposed design for durable request/reasoning/tools archival and read-only retrieval. Do not prune otherwise retained evidence on the assumption that future archive capabilities already exist.

## Paper

Separate deliverable: **Jack Agentic — Reasoning-Primary Memory Preservation** (Jonathan Michael Langford, November 12, 2026). The design paper details source ownership, safeguards, rollout gates and A/B measurements.
