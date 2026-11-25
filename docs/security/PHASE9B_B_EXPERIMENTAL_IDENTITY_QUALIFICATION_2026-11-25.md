# Phase 9B-B — Experimental Identity Primitive Windows Qualification (2026-11-25)

**Candidate commit:** `40b7a5a3e796490f77c6bfcf3390f667d4e30590`  
**Branch:** `security/phase9b-runtime-code-integrity-20261125`  
**PR:** [#173, DRAFT — NOT FOR MERGE](https://github.com/mlangford75-lgtm/Jack-Kernel/pull/173)  
**Runner:** Windows, pinned Python **3.14.6**, same pinned test requirements as current repository.  
**Evidence:** [GitHub Actions run 45591652795](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/45591652795), job `phase9b-windows-qualification`, **SUCCESS**.

## Executed and passed

- Compile: `jack_runtime_code_guard.py`, `tests/test_phase9_runtime_code_guard.py`, `tests/test_phase9_real_wrapper_qualification.py` — **PASS**.
- New targeted primitive/Phase-8-wrapper tests: **24 passed, 2 warnings** (0.51 seconds).
- Existing Phase 8 source-baseline/enforcement/ledger-observation/adversarial-preservation tests: **39 passed** (3.42 seconds).
- All 63 tests in this targeted Windows qualification completed successfully; they are **not** a substitute for the full repository regression suite.

Previous isolated prototype validation: **20 passed** under local Python **3.13.5**. The submitted GitHub tests comprise 20 primitive controls plus 4 real Phase 8 wrapper-qualification tests, run and verified at the candidate commit.

## What the primitive establishes

It can capture and later compare selected process-local Python executable identities, detect function rebinding and code-object mutation including constant-only/nested-code changes, selected closure/default/kwdefault delegate substitution, module-object replacement, registered FastAPI route table/endpoint/dependant/route-app substitutions, and avoid false differences from ephemeral bound-method wrappers and ordinary mutable state. Missing previously protected bindings are treated as confirmed mismatches, while transient measurement inability suspends pending exact re-verification. Confirmed compromise cannot be reset by an in-place return to matching code.

The real Phase 8 integration tests construct the actual `RuntimeSourceAuthority` and call the real `activate_runtime_enforcement(..., start_periodic=False)`; they test the unmodified Phase 8 wrappers for normal run/stream/executor/orchestration traffic and observe selected binding substitutions. These tests **do not** exercise the full `jack_secure_entrypoint --serve` process or live network effects.

## Not established by these tests

1. **No Phase 9B enforcement is installed or activated.** The module is currently only an opt-in identity primitive; nobody is required to call `verify()` before a tool action, response or external consequence. Detection in a standalone test is not prevention of a bypass.
2. The P0 actual-execution manifest remains provisional. Generic `__wrapped__` references are not proof of executed delegate order; selected globals, module reload-in-place and indirect dispatch require additional tests or explicit limited scope.
3. The previous Phase 9A.4 experiment's unexplained benign HTTP binding differences remain unresolved. Reproduce and classify them on current pinned runtime before freezing a larger manifest.
4. FastAPI lazy middleware build did not false-fail in one isolated positive control, but the actual secure-child middleware stack/handler identity, post-start startup order and ASGI send boundary are not validated.
5. No guarantee against arbitrary hostile same-interpreter modification; the checker and its call sites are within the same Python authority domain.
6. Phase 8 continues to be the most recently validated, merged and tagged security phase. Current `main` G0 Windows CI remains red in the older Coder suite (**24 failed / 24 passed**), with full regression and Pi harness skipped. The phase is not ready for promotion.

## Next bounded step — Phase 9B-C (separate review)

- Reconstruct **actual P0 dispatch graph** in the current `--serve` child with trusted module, route, closure and wrapper references; classify legitimate framework state transitions and exact protected owner scopes.
- Add an opt-in **pre-authority and pre-release enforcement boundary** only for proven P0 actions, with clearly specified failure mapping. Ensure checks are reached before external release even when the effective symbol/route itself changes, or openly limit the attack model and tests accordingly.
- Verify prevention, not merely detection, for one representative forbidden tool admission, one HTTP nonstream response, one stream after first safe prefix and one mutating Pi orchestration dispatch. Preserve harmless sibling work.
- Run the Phase 5–8 security tests, all current Coder/Agentic/Responses/Pi tests, full Windows regression, fresh-clone validation and exact diff on the *same candidate commit*.
- Stop for explicit diff review and phase acceptance before merge/tag. Do not automatically carry into Phase 10.

**Disposition:** Phase 9B-B measurement-only candidate qualified on Windows, but **Phase 9B itself remains NOT IMPLEMENTED AS ENFORCEMENT / NOT VALIDATED**.
