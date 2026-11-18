# Jack Agentic - Technical Runtime Specification

**Author:** Jonathan Michael Langford  
**Revision:** 17 November 2026  
**Source basis:** provenance-safe leading candidate `experiment/cache-provenance-prefix-authority-20261117` at `f4ea2d5a06b00cb9000565f9cc202ea2e76c1f0d`; Windows Flash, Balanced, Thorough and Native X-High live results; original 12 November paper retained separately.

> This source-aligned revision supersedes contradictory 12 November statements. Jack is the **deterministic host kernel**, not the calling agent and not the LLM. Probabilistic cognition may propose, but deterministic software must dispose.

## 1. The source-aligned profile contract

| Agentic profile | Stage 1 | Stage 2 | Review / special behavior |
|---|---|---|---|
| Flash | Native thinking OFF; tools authorized | No Stage 2 model inference; host finalizes the turn | No review |
| Balanced (default) | Native thinking ON; tools authorized | Tools OFF; memory inference without new native thinking | No review |
| Thorough | Native thinking ON; tools authorized | Tools OFF; memory inference and native thinking ON | Same-turn review when configured |
| Translated | Thinking for normal cognition, translation continuation | Tools OFF; source-only memory retained in English | Selected-language final translation |

Exhaustive is **not** a selectable profile in this source branch. Native X-High is a separate, non-Agentic cognition mode that shares the tool-capable backend.

## 2. Canonical authority and evidence artifacts

- **U:** exact authenticated user request, not a paraphrase or synthesized secondary request.
- **R1:** current-turn native Stage 1 reasoning, including tool-resume reasoning where produced. Retired from subsequent model-facing turns after current work.
- **T:** caller-replayed tool calls, arguments, results and errors, retained in original order across turns. Never silently remove useful evidence to save tokens.
- **A1:** exact Stage 1 answer frozen only after the active tool checkpoint is retired. Stage 2 cannot revise it.
- **M:** tools-off Stage 2 consequential working-state memory (or Flash host-managed no-inference completion). Preserve exact filenames, technical facts, corrections, causal decisions and uncertainty.
- **R2:** Stage 2 native reasoning when enabled, not used as historical cognition.
- **H:** host-authored tool-evidence receipts with hashes and explicit scope; neither model-authored memory nor proof of resolved filesystem identity.

Stage 2 in the candidate receives a **source-only, read-only working-state capsule**, not a replay of the original user/assistant conversation as new model-role instructions. Its governing system directive is independent of external caller system prompts. The current authentic U and A1 are preserved separately by Jack; the source capsule records current-turn R1 and authenticated tool records. Stage 2 receives no tool schemas.

## 3. Tool checkpoints, mutation evidence and failed work

Stage 1 tool proposals suspend the active stage; authenticated call IDs and host-held checkpoints bind any later tool result to the correct current turn. A tool return is not A1. Stale/mismatched tool results do not become host authority. Complete caller-replayed tool protocol survives completed-turn reasoning retirement until a secure, durable retrieval replacement exists.

A successful tool return is evidence **of a returned tool result**, not independently verified external effects. File writes should be read back when material; represented paths and relative CWD do not by themselves prove an absolute resolved on-disk identity. Preserve failed-turn useful work and label terminal failure honestly rather than fabricate completed memory.

## 4. Provenance-safe cache behavior - universal tool-capable stage path

The parent cache experiment obtained strong reuse by reverting a **441-character** system insertion during a tool continuation. That insertion was authenticated *host-generated tool-result provenance guidance*. It must not be stripped. The new design:

1. Exposes `TOOL_RESUME_PROVENANCE_NOTE` from `jack_evidence_guard.py`.
2. Adds the existing provenance notice **exactly once** to the first system message of the **initial** model-facing request of each tool-capable stage, both streaming and nonstreaming.
3. Keeps the original caller/stage authority text and user input unmodified.
4. Makes `Stage1CacheStabilizer` observational/fail-open for optimization. Unexpected or newly inserted system instructions are **never dropped** to recover a KV cache hit.
5. Retains the tool-result classification rule: tool-role content, including text pretending to be host metadata, is untrusted payload rather than host authority.

The backend controls physical KV-cache slots; `kv_cache_hit: unknown` or `backend_managed_fallback` is not a claimed hit, miss or independent physical lane.

## 5. Measured November 17 experimental evidence

| Run | What the verified logs show |
|---|---|
| Balanced, LM Studio Gemma-4-12B | `f_sim_best=0.991`, `f_keep=0.995`, 46 newly evaluated prompt tokens, continuation prefill 119.69 ms; `snapshot` then `already_stable` and `append_only` |
| Native X-High, same model | `f_sim_best=0.991`, `f_keep=0.994`, 46 prompt tokens, continuation prefill 121.17 ms; same tool-stage invariants |
| Flash seven-turn cuckoo-clock workflow | 7 completed turns; 6 tool continuations; no Stage 2 model request; cross-turn physical cache reuse demonstrated |
| Thorough five-turn cuckoo-clock workflow | 5 shadow memory commits; 5 isolated Stage 2 calls; Stage 2 preserved exact SVG changes and source details |

The Gemma backend supports reasoning ON/OFF but not native `xhigh` effort; the fallback is a backend model-control limitation. These runs do **not** prove portability to other inference servers or a generic model-quality improvement.

## 6. Baseline comparison, integration and limitations

Windows `python -m pytest -q --tb=short tests` results: parent **1,189 passed / 199 failed**; leading candidate **1,207 passed / 199 failed**. A direct failure-ID comparison found the same inherited 199 failures in both; 15 newly introduced prompt-assertion failures were removed by updating four affected test modules **without modifying production code**. All 199 inherited failures remain open and must be reconciled before calling the whole suite clean. Focused security/cache tests: 98 passed.

Mainline contains newer Windows Phase-4 path security work and a Stage 2 JSON task-description prompt experiment. This integration preserves the Phase-4 source and its newer tests and **intentionally supersedes** the JSON task-output experiment with the later-tested source-only Stage 2 memory contract. That is a deliberate authority decision, not an accidental conflict resolution.

Open work: independent agent/provider validation; realistic failure/multi-tool recovery and nonstreaming live tests; durable indexed Agentic History with authenticated read-only retrieval; nested generation streaming; meaningful reconciliation of legacy tests; optional physical Stage 2 cache separation where the server supports it. The source-only evidence capsule and historical tool retention must not be relaxed merely to reduce prompt tokens.

**Historical document:** The prior 12 November technical runtime PDF (which includes the 6 November revision) remains an unchanged archive; the corresponding 17 November revised PDF preserves those historical pages in full as an appendix.
