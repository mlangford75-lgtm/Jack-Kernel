# Jack Kernel — Cache Lifecycle Experiment (2026-11-17)

**Branch:** `experiment/universal-cache-lifecycle-20261117`  
**Parent:** `f8c0abc0ae8220808267dac4ac38e4ebb9290403` (PR #163 baseline)  
**Status:** Experimental; DO NOT merge into `main` before prompt-authority analysis, portability and regression validation.  
**Ownership:** Jack Kernel universal runtime work; tested primarily on Balanced with LM Studio / `qwen3.6-35b-a3b`.

## Preserve the complete experiment, not just the most recent fix

This branch is intended to hold ALL of the following, with complete contents and tests, copied byte-exact from the tested Windows checkout:

1. **Cache orchestration:** `jack_cache_orchestrator.py`; integration in `jack_kernel.py`; `tests/test_jack_cache_orchestrator.py`; original installation and launch scripts; the design README. The router plans primary vs auxiliary logical lanes, optionally supports an alternate OpenAI-compatible endpoint or explicit raw llama.cpp slot hints, with unsupported features falling back where implemented. A single LM Studio endpoint cannot be claimed to provide physical cache isolation: `backend_managed_fallback` and `slot_requested:null` mean no slot leasing.
2. **Byte-level prefix diagnostics:** `jack_cache_prefix_diagnostics.py`; integration in *both* streaming/nonstreaming inference; `tests/test_jack_cache_prefix_diagnostics.py`; original installer and README. Content-free keyed-digest comparisons of model-facing UTF-8 JSON and system regions; diagnostic data is not real KV cache telemetry.
3. **Stage 1 same-turn system stability:** `jack_stage1_cache_stability.py`; integration in both inference paths; `tests/test_jack_stage1_cache_stability.py`; original installer and README. The original system message is process-locally associated with authenticated work ID; only a validated *pure insertion* on same-work tool resume is reverted in the model-facing continuation. Unexpected changes are not rewritten. Canonical history, tool records and Stage 2 stay unchanged. This code covers shared Agentic Stage 1, **not all non-Agentic runtime modes yet**.
4. **PowerShell and regression assets:** original installers, launch script, previous branch/worktree helper, three targeted test modules, README files, and a manifest with SHA-256 checksums.
5. **Engineering history, results, risks, and outstanding work**, recorded below. Raw user/agent logs and local private prompts are intentionally not pushed to the repository.

## Evidence — initial live result

* Prior diagnostic (without Stage 1 stability fix): initial Stage 1 tool-continuation system message changed at UTF-8 byte offset **9,387**, system region **11,623 → 12,064 bytes** (+441). First continuation LM Studio LCP similarity **0.889**; **660** prompt tokens reevaluated in ~**1,210 ms**. Two-message prefix not append-only.
* With the fix: kernel reported `action: "snapshot"` followed by `action: "stabilized"`, `reason: "pure_insertion_on_same_work_tool_resume"`, insertion at character 9,381, 441 inserted characters. Both transport and byte-prefix diagnostics confirmed **`append_only`**, with **2 matching prior messages**.
* LM Studio first continuation: `f_sim_best = 0.996`, `f_keep = 1.000`, **20** prompt tokens reevaluated, **266.73 ms** prompt processing, backend slot id **0**. Initial Stage 1 prompt eval: **482** tokens, **792.83 ms**. Cache improvement is supported by backend logs, not just Jack's own fingerprint diagnostics.
* Stage 2 remained on logical `auxiliary` but physical backend routing fell back to the same LM Studio endpoint/slot, `alternate_endpoint:false`, `slot_requested:null`, `kv_cache_hit:unknown`. Separate Stage 2 prompt is intentionally a different prefix. Stage 2 was run in Balanced with thinking off; `reasoning_effort:"xhigh"` on Stage 1 was transmitted by Jack, LM Studio warned it only supports `on`/`off` and internally fell back to `on`.
* Original local targeted tests: orchestrator **11/11**, prefix diagnostics **8/8**, combined experiment **31/31** passed. Live test showed normal bash execution and Stage 2 commit. **These results are not proof of universal server/agent/mode compatibility.**

## Known problems — do not erase this history

* Stage 1 insertion of **441 characters** was only proven to be a pure insertion, **not semantically analyzed**. Silently removing a genuine safety/tool/work instruction could be wrong; inspect that instruction before production use.
* Original `Install-JackStage1CacheStability.ps1 -FullSuite` caused broad pytest failures. Rollback was interrupted/failed before complete cleanup; manual restoration from timestamped backup returned `False False` for import/module checks. The installer has a `finally` rollback path on normal failures but interruption may leave a partial install. Avoid full-suite run with this unreviewed baseline until the failures are triaged.
* First unrelated full-suite failure: `tests/test_agentic_balanced_stage2_no_thinking.py` expected a Stage 2 `assistant` message with Stage 1 reasoning, but current Stage 2 projects a read-only working-state `user` capsule; result: `len(assistant)==0` versus expected 1.
* Second unrelated full-suite failure: `tests/test_agentic_cache_append_experiment_phase3e.py` asserts an exact Stage 2 system prompt, but runtime adds the internal memory extraction trigger. These are candidate outdated test assertions—not sufficient to conclude *all* full-suite failures are unrelated to this experiment. **Do not delete or silently rewrite those tests**.
* Backend cache-reuse data differs from prompt transport diagnostics: `cached_prompt_tokens:null` means metric unavailable, not zero; `append_only` does not prove backend hit on other engines.
* Existing branch is an experimental preservation point; main should get only a later minimalist, universally validated, fail-open correction with no experimental toggles, scaffolding or provider-specific assumption.

## Validation remaining

- Check failure/recovery, multi-tool and cross-turn scope and unexpected system changes, together with preserving authenticated work IDs and tool output.
- Confirm inserted 441 characters are not consequential, even though stripping them improved LCP.
- Test streaming and nonstreaming, Flash / Balanced / Thorough / Exhaustive / Translator where present, plus non-Agentic modes (currently not covered by Stage 1 stabilizer), and alternative inference servers / agents.
- Audit optional alternate endpoint/slot fallback and prompt authority.
- Bring existing baseline tests in line with production Stage 2 *without changing production behavior*, then run a reliable full regression suite.
- No mainline merge until scope, safety, and regression tests are established.