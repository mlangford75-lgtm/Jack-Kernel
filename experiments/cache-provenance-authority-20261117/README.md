# Cache prefix + tool-result provenance authority experiment

**Branch:** `experiment/cache-provenance-prefix-authority-20261117`  
**Base:** `experiment/universal-cache-lifecycle-20261117`  
**Main and the original universal cache experiment remain unchanged.**

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

**Status at publication:** edits and test additions committed on GitHub.
The Windows tests and live inference retest have **not** been executed for
this branch; do not present it as validated production code.
