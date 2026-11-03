# Agentic Stage 2 — Native Reasoning Reflection Extension (Experiment)

**Status:** Opt-in test branch only; not promoted to main; **no production token-level adapter yet**.

## User hypothesis

Before the model leaves Stage 2's *native reasoning* to write its retrospective Agentic memory, a one-time host-injected sentence could expose omissions and improve downstream memory:

> Hold on, I need to ensure I've included everything that helps later turns recall this work.

This does **not** mean extending after Stage 2 returns its memory or generating a third stage.

## Critical transport distinction

A standard OpenAI-compatible `/v1/chat/completions` SSE response reports already-generated `reasoning_content` and `content`. Jack can observe the transition but cannot unsample an already committed `</think>`, Gemma channel delimiter, or model-specific reasoning boundary. **Do not claim that an SSE text rewrite is a native inference continuation.**

Full support requires an inference-backend sampler adapter that (1) recognizes the loaded model's actual end-of-reasoning boundary, (2) suppresses the first boundary BEFORE commitment, (3) injects the sentence into the active decoder/KV state, (4) resumes native reasoning in the *same* streaming generation, and (5) permits later natural termination. A model-brand substring is never proof of those capabilities.

## Experiment added to Jack

- Environment switch: `JACK_AGENTIC_STAGE2_NATIVE_REFLECTION=1` (default is **off**).
- Scope: Agentic `extended_reflection` only. Stage 1 and all other modes/stages unchanged.
- Protocol: `jack.stage2.native-reflection.precommit.v1`.
- Backend contract: `native_reflection_capability() -> PROTOCOL` and `chat_stream_with_native_reflection(..., reflection_instruction=..., max_reflections=1)`.
- Unsupported backend: exact original `chat_stream` method, arguments, one request, and original streamed output. No artificial continuation or additional inference.
- Capable backend: must emit precisely one private `_jack_native_reflection_receipt`, recording exact instruction and protocol, between first and resumed native reasoning and before output memory; receipt is not forwarded as reasoning or content.
- Adapter violation: hard contract failure; never silently retry an already-streaming inference with potentially released bytes. Existing loop guard still applies to generated reasoning.

The simulated capable-backend test verifies a **transport contract, not a live model's sampling behavior**. Transport receipts alone cannot cryptographically attest the adapter's internals; real adapter integration and decoder instrumentation are prerequisites to declaring support.

## Test matrix

1. Feature off: unchanged stage behavior, including for a simulated capable backend.
2. Feature on + backend without capability: unchanged one-request streaming; no added tokens/prefill.
3. Non-Stage-2: unchanged streaming even when feature is on.
4. Simulated capable backend: one receipt, continued native reasoning, then one memory.
5. Missing/duplicate/late receipt: fail closed; no completed memory accepted.
6. Prompt invariants: Stage 1 x-high text byte-identical; Stage 2 immutable core prompt byte-identical; no tools in Stage 2.
7. Run full Windows GitHub CI to verify no impact on forensic linkage, loop interruption, R2 one-hop bridge, context pruning and cache behavior.

## What has NOT been demonstrated

- No live Qwen/Gemma/Nemotron/DeepSeek/Kimi sampler interception.
- No measured increase in downstream Agentic intelligence.
- No measured in-engine KV-cache preservation.
- No universally supported token-boundary interface.

These remain acceptance gates before any default-on implementation or merge to main. Continue to test with the working baseline as control; do not interpret a mock receipt as a demonstrated model extension.
