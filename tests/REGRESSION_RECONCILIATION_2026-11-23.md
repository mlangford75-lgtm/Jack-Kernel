# Jack Kernel regression reconciliation — 2026-11-23

**Status:** first-pass investigation and scoped regression repairs, **not** a claim of full-suite compliance.

## Authoritative measurements

- Base branch: `main` at `0796da1f45259c4eda7156f3c5d2c32ce47b985e` (Coder/Agentic merge, Flash default, 5-repeat mutation cycle).
- First new focused Windows CI: **89 passed, 15 failed**.
- After reconciling legacy assertions: focused Windows CI run **45153071820**, **104 passed** (commit `bf702a0ff39036f10e749ada6b834682dcdc66a6`).
- Full Windows Python suite (run **45153071657**, same commit): **1,393 passed, 193 failed in 133.60s** across **34** test files. It followed the passing delegated Architect CI step; the full CI job ended in failure. The failure count is a *triage baseline*, not an approved known-failure exception.
- Subsequent changes to focused CI include delegated Architect tests. Validate the latest branch SHA separately. No green full-suite claim.

## Broad failures by concentration

| Test file | Failure count | First-pass evidence class |
|---|---:|---|
| `test_agentic_stage2_withhold_a1.py` | 23 | Prior Stage 2 source/projection assumptions; must inspect actual canonical A1 and wire isolation before updating |
| `test_agentic_reasoning_primary_memory_experiment.py` | 22 | Legacy profile and source-only contract assumptions |
| `test_agentic_stage2_turn_local_retention.py` | 17 | Old byte-exact Stage 2 prompt / historical source shape |
| `test_agentic_stage2_final_review_balanced.py` | 16 | Old review scheduling, answer-containing Stage 2, and missing Flash authenticated freeze fixture |
| `test_agentic_stage_scoped_system_authority.py` | 14 | Old Stage 2 system-prompt/role presentation; verify authority isolation |
| `test_agentic_balanced_stage2_no_thinking.py` | 10 | Old assistant-role reasoning projection; now working-state source may be transport-quoted |
| `test_agentic_cache_append_experiment_phase3e.py` | 8 | Historical Stage 2 prompt literal |
| `test_model_native_reasoning_controls.py` | 7 | Backend-specific thinking-control expectations; may be real transport regression |
| All remaining 26 affected files | 76 | See full CI run 45153071657; mixed legacy source, profile, cache, and recovery contracts |

Total: **193**. These are preliminary diagnoses from failure signatures, not established declarations that the runtime is correct.

## Migration rules

1. **Do not delete, skip, xfail, or weaken security/authority/caching assertions** to eliminate failures. When old semantics were intentionally retired, substitute assertions of the actual new invariant.
2. **Preserve real regression detection.** Check that original user authority, stage/tool separation, exact tool evidence, prompt-prefix stability, and cache reuse measures still behave correctly. A textual mismatch is not automatically harmless.
3. **Retired Exhaustive is not Translated.** Only migrate generic profile coverage by substitution. Old verification/review extension scenarios require their own successor tests or archival separation.
4. **Stage 2 source and prompt updates require transport-level evidence.** Determine whether each test expected old A1 replay, assistant-role reasoning, or an obsolete prompt; rewrite against current frozen evidence without permitting instruction replay, hidden tool authority, or data loss.
5. **Thinking OFF must not force numeric zero budgets.** Current serving controls avoid numeric zero on backends that may stop producing useful output. Assert actual intended request semantics and model-specific controls.
6. **Avoid introducing new context or inference work.** This reconciliation modifies tests/CI only; no production prompt, cache, tool, or stage changes unless a real runtime defect is separately demonstrated.
7. Keep historical experiment artifacts and the prior tests' rationale available until a successor test covers the consequential behavior. Do not wholesale mass-rename or mass-delete.

## Next focused cohorts for semantic investigation

1. `test_model_native_reasoning_controls.py` and `test_coder_planner_recovery_boundary.py` (check for genuine regressions in transport/safety).
2. `test_agentic_stage2_withhold_a1.py`, `test_agentic_stage_scoped_system_authority.py`, `test_agentic_stage2_turn_local_retention.py` (source isolation, provenance and completion).
3. `test_agentic_reasoning_primary_memory_experiment.py` and `test_agentic_stage2_final_review_balanced.py` (historical contract migration).
4. Remaining stage-transition and cache experiments, with actual serialized request and cache-prefix comparison.
5. Fresh-clone Windows bootstrap and Pi/streaming security gates after the full Python suite passes.

**Promotion:** only merge after repeatable, reviewed full regression results, no lost useful coverage, and an evidence-backed evaluation of any genuine kernel defects.
