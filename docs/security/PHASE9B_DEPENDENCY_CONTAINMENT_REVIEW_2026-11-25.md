# Phase 9B — Security Dependency and Containment Correction

**Date:** 2026-11-25  
**Candidate code SHA:** `bf3cfb4006c7c7eb31725622f3dd5462936df49c`  
**Draft:** [PR #173](https://github.com/mlangford75-lgtm/Jack-Kernel/pull/173)  
**Windows qualification:** [run 45601286075](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/45601286075): **SUCCESS**, pinned Python 3.14.6.  
**Release status:** NOT READY TO MERGE OR TAG. Phase 8 remains the last validated merged security phase.

## Security objective

The governing requirement is *effective prevention of unauthorized consequences*, not maximizing availability or mechanically minimizing containment. Narrow containment is permitted **only where the full execution, authorization and release dependency is intact**. Security dependencies take precedence over labels such as “read-only” and over preserving useful work when those concerns conflict.

No runtime enable/disable switch exists: `jack_secure_entrypoint.py` installs Phase 9B **unconditionally in the secured `--serve` child** after Phase 8. Required-manifest initialization failure prevents normal serving. The experimental **Git branch** remains the isolation boundary.

## Confirmed defects corrected

1. **Overbroad denial:** Earlier scoped code denied all public HTTP after any protected executable mismatch, even when the affected model path had no credible dependency on separately protected status. Replaced blanket invalidation with selected dependency measurements; shared trust-boundary failure still denies all affected public HTTP.
2. **Unsound observation exemption:** The initial allowlist treated Pi status/events and backend-dependent health/models as ordinary observation. Those paths depend on privileged Pi proxy or backend authorization. Removed these exemptions. The limited exception covers `GET /`, `GET /jack/runtime/status` and `GET /jack/runtimes`, with protected route dispatch and shared API/auth/security code.
3. **Improper task independence:** Starting `/jack/orchestration/tasks` can invoke the model and tools. It now requires healthy **orchestration + model + executor + shared authority**. Task cancellation remains permitted through verified orchestration and shared authority if model execution alone is invalidated. It cannot undo a previously admitted external side effect.
4. **Tool release dependency:** A generated tool-call proposal now also requires intact executor-admission executable identity, not just an intact model wrapper. Existing Phase 4/5 policy still independently decides if the call is authorized.
5. **Shared trust root wrongly scoped:** Phase 8 source verification, consequence evaluator, represented-path authorization, evidence protection and relevant source modules are now common trust dependencies; changing them blocks public release through the secured ASGI boundary, not merely one nominal scope.
6. **Streaming unsafe continuation:** The earlier implementation deliberately drained the predecessor generator after code-integrity failure, which could continue untrusted computation. It now closes the upstream async iterator on interruption, preserving previously committed safe bytes without executing remaining generator iterations after detecting compromise.
7. **Mutable route exception data:** Runtime scope classification no longer consults a rebindable global observation allowlist for its decision; the permitted exceptions are executable constants. The classifier and the internal check-method delegate are measured as shared authority. The checker also pins and calls the original check method to prevent straightforward subsequent method rebinding from fabricating verification success.
8. **Unprotected actual route delegates:** Current manifest now covers `jack_kernel.enforce_kernel_auth`, `sanitize_agent_request`, `_phase4_executor_context_from_request`, `_safe_public_stream`, and `completion_envelope`, in addition to existing selected kernel, Pi, path, source, Responses and FastAPI route bindings.

## Dependency release matrix

| Actual route or release | Mandatory measured dependencies | Containment consequence |
|---|---|---|
| `POST /v1/chat/completions`, `POST /v1/responses` | model, relevant request/output delegates, shared authorization and source/path/consequence trust | Deny release if any required identity fails |
| Generated structured tool-call release | model **and executor**, shared security/path/consequence trust | Withhold generated tool-call release; ordinary independent read-only status may continue if its own dependencies remain trusted |
| `POST /jack/security/path-admission` | executor admission and common security authority | Deny new executor admission, not retroactively undo prior external settlements |
| `POST /jack/orchestration/tasks` | orchestration, model, executor, common security authority | Withhold creation of new Pi task if model or executor trust fails |
| `POST /jack/orchestration/tasks/cancel` | orchestration bridge and common security authority | Permit cancellation if these are intact even when model execution is blocked |
| `GET /jack/orchestration/status` or `GET /jack/orchestration/events` | orchestration/Pi transport and shared authority | No unverified “read-only” exemption |
| `GET /health`, `GET /v1/models`, `GET /api/v1/models` | backend/model-dependent routes and shared trust | Withhold when dependencies unverified |
| `GET /`, `GET /jack/runtime/status`, `GET /jack/runtimes` | observation handler, authenticated route when applicable, shared ASGI/verifier/authorization and route table | May remain available after unrelated model or executor failure |
| Unclassified new route | all consequential scopes and common security authority | Conservative admission until audited and explicitly mapped |
| Shared source verifier, path/consequence authority, API authentication, route-table/verifier delegate | shared trust boundary | Block all dependent public HTTP until fresh secure-child startup after confirmed compromise |

**Important:** “Independent” above refers to the *specific executable identities and code paths qualified by this experiment*. It does not establish isolation from arbitrary same-interpreter compromise or from dependencies not yet measured. A pure Python guard cannot independently attest its own integrity against a fully privileged interpreter adversary.

## Actual Windows qualification

- **54 passed** Phase 9B primitive, real Phase 8 wrapper, adversarial ASGI, live FastAPI bypass/containment and preservation tests; two deprecation warnings from pinned dependencies.
- **3 passed** separately spawned Python process tests using the real loaded Kernel, actual Phase 8 and Phase 9B and genuine ASGI dispatch.
- **1 passed** actual secured `jack_secure_entrypoint.py --serve` loopback HTTP startup/warm lifecycle test with mandatory Phase 9B.
- **39 passed** unchanged Phase 8 source baseline, runtime enforcement, ledger observer and adversarial preservation tests.
- **97 passed total** under Windows/Python 3.14.6 at candidate SHA `bf3cfb4006c7c7eb31725622f3dd5462936df49c`. [Workflow evidence](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/45601286075).

Positive cases verify independent safe model/executor operations and cancellation. Negative cases cover common-security changes, route classification monkeypatch, mutable observer allowlist, API-auth/request sanitizer rebinding, tool-release/executor coupling, Pi proxy compromise and generator closure after tampering.

## Remaining mandatory release gates

1. **G0:** current main CI is red in legacy Coder assertions and never reaches the full regression and Pi harness. Resolve against approved Coder behavior; do not weaken or delete tests to get green.
2. Real backend simulation and long-lived SSE with concurrent changing state; safe prefix, actual cancellation/cleanup and early close; actual tool executor and Pi worker settlement evidence.
3. Detailed source and runtime trust-boundary qualification: Phase 9 files are not in the previously frozen Phase 8 source baseline; revise start-up source protection without silently altering the validated Phase 8 contract.
4. Race, performance, sustained streaming/throughput, Agentic/Ultra/Coder/Responses and multi-lane isolation/stability tests; audit exact active route/dependency chain.
5. Independent security review of same-process self-verification limits, ASGI root bypass threat and potential omitted mutable executable delegates.
6. Full Windows and Pi regressions + source diff review before promoting this draft to an eligible security release.

**Engineering disposition:** Security dependency and preservation-of-safe-work corrections implemented and Windows target-qualified. **This is not complete Phase 9B production validation. Do not merge/tag.**
