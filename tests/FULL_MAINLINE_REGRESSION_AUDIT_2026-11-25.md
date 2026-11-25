# Current-main full Windows and Pi regression audit — 2026-11-25

**Source baseline:** `915b77a119d1790af7c94b615109b08692cde4fc` (main after merged Phase 9B startup test fix PR #174)
**Diagnostic branch:** `ci/full-regression-diagnostics-20261125`, commit `41a065cf6e20a3b9afeb5376a84c7c8c3b0ac817` adds *only* a CI diagnostic workflow.
**Workflow:** [run 45620143464](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/45620143464)
**Windows environment:** Python 3.14.6; pinned test requirements; Node 24.16.0
**Scope:** Every Python test was executed as `python -m pytest -q -ra` without exclusions, skip additions, or xfails. The Pi bridge harnesses ran as an independent parallel job.

## Actual baseline results

- **Python:** **1,419 passed; 242 failed; 2 warnings** (165.50 seconds), across **39 failing files**. The overall Python job and workflow are **FAIL**.
- **Pi:** All **8 independent Pi control/ownership/cancellation/deferred-dispatch/retry/multi-endpoint/provider-runtime/Phase4 executor/edit-origin Node harnesses PASS**. This is not a claim that Python Pi or Coder stages passed.
- **Current main CI before this diagnostic:** Phase 5–8, Ultra and Planner-specific gates all pass after PR #174; the older broad Coder suite remains **24 failed / 24 passed** and prevents subsequent regular CI steps. This independent run discloses the downstream failures.

## Failure distribution (full Python suite)

| File | Failures |
|---|---:|
| `test_agentic_coder_planner_executor.py` | 24 |
| `test_agentic_stage2_withhold_a1.py` | 23 |
| `test_agentic_reasoning_primary_memory_experiment.py` | 22 |
| `test_agentic_stage2_turn_local_retention.py` | 17 |
| `test_agentic_stage2_final_review_balanced.py` | 16 |
| `test_universal_tool_recovery.py` | 16 |
| `test_agentic_balanced_stage2_no_thinking.py` | 15 |
| `test_agentic_stage_scoped_system_authority.py` | 14 |
| `test_agentic_cache_append_experiment_phase3e.py` | 8 |
| `test_model_native_reasoning_controls.py` | 7 |
| `test_agentic_historical_memory_presentation_recovery_ab.py` | 6 |
| `test_agentic_memory_data_channel_ab.py` | 6 |
| `test_agentic_phase3g_recovery_contract.py` | 6 |
| `test_agentic_stage1_verify_then_align.py` | 6 |
| `test_agentic_four_profile_extensions.py` | 5 |
| `test_agentic_portable_anchor_stream_contract.py` | 5 |
| `test_agentic_final_review_hold_on.py` | 4 |
| `test_agentic_stage2_current_turn_anchor.py` | 4 |
| `test_agentic_stage2_review_evidence_continuity.py` | 4 |
| `test_agentic_file_mutation_readback.py` | 3 |
| `test_agentic_optional_draft_recovery.py` | 3 |
| 10 additional 2-failure files, 8 additional 1-failure files | 28 |

The source of truth for all individual failing test names and tracebacks is the linked workflow log, not the abbreviated grouping above.

## Failure categories — classification is provisional, NOT an exemption

1. **Clearly stale contract assertions need migration but not deletion.** The current approved Coder Architect has **no tools**, while old `test_agentic_coder_planner_executor.py` cases expect read-only Architect tools, a previous wire task-role contract, older prompt strings and CLI selection. Newer dedicated `test_coder_architect_no_tools.py`, `test_coder_architect_readonly_role_isolation_20261124.py`, `test_coder_planner_delegation.py` and `test_coder_planner_history_isolation.py` already test the accepted no-tool, role-isolated design. Preserve negative cases proving tool/mutation authority never leaks; rewrite fixtures to the real contract, not runtime prompts to satisfy them.
2. **Retired profiles and frozen Stage2 prompt variants:** old `exhaustive` selectors, old Stage2 prompt literals, historical R1/R2 projection and retention assumptions account for many failures. Confirm approved new contract before changing each expected result. Do not blindly map Exhaustive to Translated; semantics differ.
3. **Potentially substantive security/reliability failures requiring independent triage:** `test_universal_tool_recovery.py` has **16 failures**, including missing `total_tokens` in some mock usage and streaming tool-cycle recovery where a proposed action did not switch to the expected different command. The latter could affect whether repeated unsafe tool cycles are blocked or retried correctly; treat as unproven until rerun with current approved deterministic fixtures. `test_phase4_nonstream_authorization.py` has **1 failure**: separately inspect actual expected NEVER-path and checkpoint behavior before classifying as stale. `test_coder_planner_recovery_boundary.py` has **2 failures** and the Coder broad-suite partial-spec/tool-resume tests may surface genuine useful-work/security regressions.
4. **Role/historical data isolation:** several errors compare legacy system/user capsule positions with the newer role-separated current task; preserve current authenticated current request and prevent untrusted former tool transcripts from becoming executable authority.
5. **Bench/experiment fixture drift:** explicit removed attribute `_agentic_zero_reasoning`, retired prompt references and variant counters are test migration candidates, not evidence that Phase 9B itself failed. Still require direct tests for their relevant safety promises.

## No-false-green rules

- Do not touch current approved Architect, Coder, Agentic or Stage2 prompts solely for obsolete assertions.
- No mass delete/skip/xfail and no high-level classification as “all stale” without exact test-level evidence.
- Preserve actual protected NEVER-path denial, executor admission, streamed/nonstream release, historical tool authentication, cancellation, completed work, and stage/memory isolation.
- Fix real security/functionality regressions surgically on an isolated branch, then compare exact same candidate SHA with complete Windows and Pi suite.
- Phase 9B current targeted security passes cannot be promoted to a complete full-security release while broader runtime suite remains red.

## Next triage order

1. `test_phase4_nonstream_authorization.py`: security-critical single failure.
2. `test_universal_tool_recovery.py`: distinguish usage metadata fixture drift from repeat-action/cycle containment.
3. `test_coder_planner_recovery_boundary.py` and broad Coder suite: active task preservation, mutating tool rejection, legitimate tool resume, role isolation.
4. Agentic Stage2 and old profile test matrices: migrate only with explicit approved contract evidence from newer passing tests and retained historical assertions.
5. Re-run all tests, fresh Windows bootstrap and independent Pi harnesses.

**Result: full current-main regression is RED, and the exact failure set is now observed rather than inferred.**
