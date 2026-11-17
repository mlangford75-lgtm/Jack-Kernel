# Cache prefix + tool-result provenance authority experiment

**Branch:** `experiment/cache-provenance-prefix-authority-20261117`  
**Base:** `experiment/universal-cache-lifecycle-20261117`  
**Main and the original universal cache experiment remain unchanged.**

## Status — LEADING CANDIDATE for the universal cache/provenance upgrade (2026-11-17)

**Leading candidate, experimentally validated on LM Studio; NOT merged or approved for production.**
This branch is the preferred candidate over its parent
`experiment/universal-cache-lifecycle-20261117` because it corrects the
provenance-versus-cache conflict without suppressing instructions. Keep the
parent and its archived upgrade materials intact as historical controls.
This designation is a comparative engineering recommendation, **not** a claim
that all modes, new agents, inference servers, or security boundaries have been
validated.

### Verified evidence and comparison

| Check | Evidence recorded on Windows, 2026-11-17 |
| --- | --- |
| Focused regression | **98 passed** on this branch before the broader suite run |
| Full suite — original parent | **1,189 passed, 199 failed** (`python -m pytest -q --tb=short tests`) |
| Full suite — leading candidate, after updating four stale prompt assertions | **1,207 passed, 199 failed** (`python -m pytest -q --tb=short tests`) |
| Exact failure-set comparison before test updates | All **199** parent failures were also present in the candidate; **15** additional failures were isolated to old assertions about exact system-prompt text/placement |
| Test updates | Four existing test files now assert the original instruction **plus** the one host provenance note when tools are enabled; Stage 2 remains tool-free. The 15 additional failures disappeared; **no production code was changed to make those tests pass** |
| Agentic / Balanced — LM Studio `gemma-4-12b-it` | `snapshot` → `already_stable`; model-facing messages `append_only`; LCP similarity **0.991**, retained fraction **0.995**, **46** prompt tokens reevaluated, **119.69 ms** continuation prompt evaluation (initial: **5,252 tokens**, **1,702.88 ms**) |
| Native X-High — same LM Studio model | `snapshot` → `already_stable`; normal stage-local Bash tool resume and retirement; LCP similarity **0.991**, retained fraction **0.994**, **46** prompt tokens reevaluated, **121.17 ms** continuation prompt evaluation (initial: **4,840 tokens**, **1,545.38 ms**) |
| Security/authority property | The host-owned **441-character** tool-result provenance notice is incorporated into the **initial** tool-capable system context, retained on continuation, and is never discarded merely to improve caching. Tool evidence origin marking remains in place |
| Backend cache accounting | LM Studio's slot logs demonstrate actual LCP-based reuse in these runs. Jack reported `kv_cache_hit: unknown`; no backend-independent hit guarantee is implied |

For both live probes, the user request was:
`Run Bash: python -c "print('CACHE_PREFIX_PROBE')". Report the output. Do not modify files.`
The Bash tool returned `CACHE_PREFIX_PROBE`, with no file modifications requested.
Both runs used streaming and Preserve Thinking ON. LM Studio warned that Gemma
supports reasoning `on/off` rather than `xhigh`, and fell back to `on`;
that is a model/backend reasoning-control compatibility warning, not a cache
or provenance failure.

### Why this branch leads

- The previous parent experiment improved cache reuse by reverting a pure
  system-text insertion on tool resume. Investigation identified that
  insertion as **real security provenance guidance**; removing it was unsafe.
- This branch establishes stable context **without deleting legitimate new
  instructions**. The shared `OpenAICompatibleBackend` applies the same rule
  for tool-capable stages in streaming and nonstreaming paths; the stabilizer
  observes changes but never rewrites away security/system content.
- Balanced **and** non-Agentic Native X-High showed strong physical prefix reuse
  in LM Studio with the provenance guidance present. This supports a common
  kernel-layer approach for future agents that route through Jack, not
  agent-specific workarounds.

### Remaining gates before promotion to `main`

1. **Reconcile the 199 inherited baseline failures** and establish a clean,
   meaningful full-suite pass; do not dismiss them as harmless without evidence.
2. Test an independently configured tool-capable agent and at least one
   additional inference backend, including streaming/nonstreaming, different
   tool-result shapes, and successful/failed/multi-call continuations.
3. Verify security invariants in unexpected prompt-change and adversarial
   provenance-payload cases; fail open for cache optimization without losing
   higher-priority instructions.
4. Review any intended mainline patch separately, with explicit approval.
   Do **not** automatically merge this experiment or its diagnostic scaffolding.

**Promotion decision: HOLD for further validation. Candidate priority: #1.**
**No changes to `main` or the original parent experiment are authorized by
this status record.**

## Root cause established by live Balanced diagnostic

The exact 441-character insertion at character offset 9381 is
`_TOOL_RESUME_PROVENANCE_NOTE` from `jack_evidence_guard.py`. The evidence
guard appended that host-owned provenance notice to `state.secondary_system`
on the *tool-resume request*, after the initial prompt had been cached.
The previous cache stabilizer restored the old system text, inadvertently
removing the newly inserted provenance instruction from the model-facing copy.

The notice means that role=tool result text (including anything that looks
like Jack host receipt metadata) is **caller-supplied task data**, not
authenticated host authority. It must remain available to the model.

## Corrected design

1. The same existing provenance notice is exposed from
   `jack_evidence_guard.py` for shared prompt construction.
2. `jack_kernel.py` injects that notice into the **first model-facing
   system message** of every tool-enabled stage, including first requests and
   subsequent tool continuations; if no system exists, it creates one.
   It does not modify caller-owned original dictionaries. The helper runs
   identically for streaming and nonstreaming.
3. Tool-result provenance tagging in `jack_evidence_guard.py` is kept.
   The guard no longer appends 441 characters to `secondary_system`
   *after* a tool arrives.
4. `Stage1CacheStabilizer` is now **observational only**: it can snapshot
   and report a stable prefix, or report an insertion/change, but never
   discard changed or newly inserted system instructions. Non-tool stages
   are untouched.
5. The known notice is idempotent: adding it twice does not duplicate it.

These are source-level properties, not claims that physical KV reuse or every
inference server has been verified. The cache remains controlled by the backend.

## Safety gates before any promotion

- Run focused cache tests and the existing provenance/security tests.
- Confirm a real Balanced initial-request/continuation prompt has exactly one
  complete host provenance notice and no 441-character continuation insertion.
- Confirm LM Studio physically reuses prefix tokens on the continuation
  (`f_sim_best`, `f_keep`, token reevaluation, prefill).
- Confirm no role=tool content is modified, provenance origin metadata remains
  host owned, and no custom caller system instruction is lost.
- Run broad existing regression suite; evaluate any differences before merge.
- Live-test at least one non-Agentic tool-capable mode and a second backend
  where feasible. Fail-open preserves instructions even if cache reuse degrades.

**No merge to main is authorized by this experiment.**

## Windows test command (on a fresh checkout of this branch)

```powershell
python -m pytest -q --tb=short tests/test_jack_cache_orchestrator.py tests/test_jack_cache_prefix_diagnostics.py tests/test_jack_stage1_cache_stability.py tests/test_jack_universal_cache_stability.py tests/test_jack_universal_cache_backend_integration.py tests/test_jack_cache_provenance_authority.py tests/test_evidence_provenance_guard.py tests/test_surgical_regressions.py
```

**Validation update (2026-11-17):** The focused Windows tests, full-suite
parent/candidate comparison, and the Balanced and Native X-High LM Studio
live probes have now been performed; see the leading-candidate record above.
This is still **experimental**. The 199 inherited full-suite failures and
cross-agent/provider validation remain open.
