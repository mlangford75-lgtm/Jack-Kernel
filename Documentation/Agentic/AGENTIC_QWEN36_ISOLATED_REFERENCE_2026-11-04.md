# Agentic Qwen3.6 isolated reference — 2026-11-04

This is the canonical configuration of the **November 4, 2026, 01:34–01:41 America/New_York** LM Studio live run supplied by the owner: clear empty clock workspace, recreate a luxury clock, then modify it with **CATAPHRACT**. It is **not** the earlier five-turn clock session.

## Runtime and backend

- Agentic mode: `Local Agentic (Preserve Thinking)`.
- Backend profile: `lmstudio`; base URL: `http://127.0.0.1:1234/v1`.
- Backend model alias in the recorded requests: `qwen3.6-35b-a3b`.
- Backend model file reported by LM Studio: `ggml-org/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-Q4_K_M.gguf`.
- Stage 1: temperature `0.7`, top-p `0.95`, top-k `20`, min-p `0`, presence penalty `0`, repeat penalty `1.0`; streaming and Preserve Thinking on, tools authorized.
- Stage 2: temperature `0.5`, same top-p/top-k/min-p/presence/repeat penalties; streaming and Preserve Thinking on, no tool schemas or execution.
- Stage 1 exact x-high instruction is preserved. **LM Studio falls back to thinking `on`** for this model; the backend does not expose a separate native x-high setting.
- Stage 2 append-layout is on by default for LM Studio (`JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT=1`). This is the observed layout, not a promise of full Stage 1-to-Stage 2 KV-cache reuse.
- Transaction-linked U/M/A history, `JACK_AGENTIC_TRANSACTION_LINKS=1` and `JACK_AGENTIC_TASK_ANCHOR=0`, is selected by `start.bat` for the normal launcher.

## The sole Stage 2 cognitive policy

Stage 2 receives only **current authentic user request U, complete current Stage-1 native R1 across tool continuations, and exact frozen Stage-1 answer A1**, followed by its local distillation instruction. The native R1 fragments are consolidated into A1's reasoning field. Raw tool calls, raw tool results, historical turns, and prior Stage-2 native R2 are not part of its model-facing payload. Jack preserves complete tool evidence separately.

The sole instruction is `_AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION`, which faithfully distills useful cognition without reconstruction or speculation. The older `baseline`, `isolate`, differential-memory and final-paper prompt alternatives cannot switch the Stage-2 model-facing policy. The legacy `JACK_AGENTIC_STAGE2_RETENTION_TEST` environment variable is ignored.

**This reference locks the input topology, not a guarantee of memory accuracy.** The live run still contained a speculative Stage-2 memory after an empty-directory inspection, which is a model-quality failure to measure separately.

## Selection and rollout

A fresh or reset Jack launcher defaults to this LM Studio/Qwen3.6 Agentic profile. An existing user-saved launcher configuration and explicit `JACK_*` environment overrides are not overwritten. For a saved configuration, explicitly select Agentic and the backend model or reset launcher defaults. LM Studio still must have the referenced model installed and available.

The reference was recorded without changing sampling, cache or streaming code. Runtime sampling settings already matched the live run; only new-install launcher defaults and canonical isolation-policy selection needed pinning.
