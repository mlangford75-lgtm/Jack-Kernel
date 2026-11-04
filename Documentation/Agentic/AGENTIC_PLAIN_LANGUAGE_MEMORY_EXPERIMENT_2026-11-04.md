# Agentic plain-language memory prompt experiment — November 4, 2026

Branch: `experiment/agentic-plain-language-memory-20261104` (not merged into main).

Purpose: Test whether a model better preserves consequential knowledge for future turns when instructed in natural language to review the latest user request, its own reasoning, and its final response. The full prompt is the one canonical `_AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION` string in `jack_kernel.py` (aliased as `AGENTIC_36_STAGE2_PROMPT` for compatibility).

Scope: Prompt-only semantic experiment. The unchanged Stage-1 x-high prompt, current-turn isolated U/R1/A1 projection, frozen A1, Stage-2 zero-tool authority, streaming, model sampling, context retirement, transaction links, and cache-append request topology remain unchanged. The normal cache path sends the canonical instruction once as the appended user-role directive. The disabled/fallback cache path uses the same canonical directive as Stage-2's system prompt with a short generation-opening transport message.

Validation: Regression tests assert one directive, all three authenticated source inputs, no prior R2 or raw tool history, stream and non-stream construction, and unchanged Stage-1 prompt.

Live acceptance is not established by unit tests. Compare with the November 4 Gemma 4 12B baseline on identical user tasks and score downstream recall of factual status, important distinctions, decisions and causality; maintain cache-reuse and prefill metrics. Do not judge by memory length or reasoning-token count. Do not merge until live evidence supports improvement.
