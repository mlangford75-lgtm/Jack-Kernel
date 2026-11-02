# Agentic Differential Memory — Live Experiment Record (2026-11-01)

## Scope and decision

Jack's previously validated Agentic pipeline remains the production default:
immutable Stage-1 answer (A1), Stage-2 retrospective memory (M), host-owned
user/A1/M transaction linkage, host-recorded tool receipts, streaming, context
pruning, and cache-aware Stage-2 continuation. No frozen Stage-1 or Stage-2
base instruction was changed in this experiment.

**Retain only as an optional A/B capability, disabled by default.**
Do not interpret the results as proof of a general memory-quality improvement.
Do not enable the Nemotron-specific thinking-history override in production:
its effective GGUF prompt rendering and value were not established.

## Differential-memory hypothesis and switch

Flag: `JACK_AGENTIC_DIFFERENTIAL_MEMORY=1` (default `0`).

When Agentic transaction links are active, only the **trailing Stage-2
continuation** receives this sentence:

> Prioritize important reasoning, decisions, tool evidence, and unresolved details that are not already clear from the completed answer.

The pre-existing retrospective continuation and the frozen Stage-2 core prompt
`Generate a detailed summary of why you came to this conclusion.` remain
byte-exact. Stage-1 messages, tool schemas, authorization, and the model-facing
prefix are not modified by this flag.

The code path is guarded by the existing transaction-linked Agentic Stage-2
condition; if transaction links are disabled, the experiment has no effect.

## Observations from live Pi + LM Studio tests

These are single exploratory runs, **not randomized paired tests**.
Measurements of memory size below use whitespace-delimited words,
exclude Jack's separate tool-receipt block, and are **not token counts**.

| Trial | Observed result | Interpretation |
| --- | --- | --- |
| Gemma 4 12B, differential off | ~2,006 Stage-2 words across 5 turns | Baseline |
| Gemma 4 12B, differential on | ~1,670 Stage-2 words across 5 turns | ~16.7% fewer overall; ~19.8% fewer in substantive turns 2–5 |
| Gemma live cache/pre-fill comparison | Stage-2 prefix reuse remained generally high; comparable prefill timings | No meaningful penalty detected, not a controlled latency benchmark |
| Nemotron 3.5 Lightning with differential on | ~6,304 Stage-2 words across 6 turns; extensive recycling of prior memory | Failed to demonstrate selective distillation; cannot attribute repetition to this instruction alone |
| Nemotron with an experimental thinking-history override | ~4,412 Stage-2 words across 4 completed turns; historical repetition continued | Not directly comparable in length or turn sequence; no proof that the installed GGUF honored the override |

### Specific risks and limitations

- The model may omit a detail that it incorrectly judges to be obvious from A1.
  A1 is retained, but omitted hidden reasoning may be valuable in future turns.
- We observed **historical overinclusion**, not a demonstrated return of the
  prior wrong-turn transaction-anchoring defect.
- In the Nemotron trial, merely declaring an empty workspace prompted Stage 1
  to read outside that workspace and create `index.html` without a user request
  to create anything. This was a **Stage-1 model/tool-use issue**, predating
  Stage-2 generation, and **not evidence** that Stage-2 memory or the experimental
  template flag caused the unauthorized write.
- LM Studio request logs show chat-template keyword arguments, not proof of
  what the GGUF ultimately renders. Reasoning-retention compatibility must
  be verified at the template/rendering layer before being recommended.
- Some Stage-2 memories overstated verification: reading code is not equivalent
  to testing it in a browser.

## Promotion rationale

Retain the one-sentence differential-memory path and payload-level regression
tests as an **off-by-default experiment** because the Gemma trial showed a
possible efficiency benefit and the change did not demonstrably alter streaming
or cache/prefill behavior. Do not turn it on globally, broaden it across modes,
change the core prompts, or add model-specific mitigations based on these trials.

**Not promoted:** `JACK_NEMOTRON_STAGE2_RETAIN_THINKING` and its associated
`truncate_history_thinking=false` override. These remain in the closed-out
experimental history/branch, not in production `main`.

## Further evaluation if reopened

Use matched tasks and fresh, isolated workspaces in Pi; record both the complete
Pi conversation and LM Studio developer telemetry. Measure memory novelty,
verified-fact recall on downstream turns, Stage-2 tool authority, prefix reuse,
prefill, and context pruning. Attribute differences conservatively. Do not
change prompts in response to individual stochastic failures.
