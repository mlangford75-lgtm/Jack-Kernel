# Phase 9B-C — Experimental Runtime Enforcement Windows Qualification

**Recorded:** 2026-11-25  
**Repo:** [mlangford75-lgtm/Jack-Kernel](https://github.com/mlangford75-lgtm/Jack-Kernel)  
**Candidate SHA:** `65c1312e76cec498a292daa6afee61ac7d6cf110`  
**Draft PR:** [#173](https://github.com/mlangford75-lgtm/Jack-Kernel/pull/173) — NOT FOR MERGE  
**Windows evidence:** [GitHub Actions run 45596092663](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/45596092663) — **SUCCESS**, Python 3.14.6  
**Test environment:** pinned `requirements-test.txt` and hosted Windows runner.

## 1. Experimental implementation

- `jack_runtime_code_guard.py`: versioned process-local callable, module and registered FastAPI route-table identity; differentiates confirmed replacement from unavailable measurement, with terminal invalidation on confirmed mismatch.
- `jack_phase9b_enforcement.py`: Phase-9B-C executable admission and release interception for `KERNEL.run`, `KERNEL.stream`, structured tool release, Phase-4 executor admission and privileged Pi control, plus an ASGI middleware that verifies before ingress, response headers and body chunks. SSE interruption preserves a previously released safe prefix while withholding later chunks.
- `jack_secure_entrypoint.py`: mandatory installation in the actual secured `--serve` child after Phase 8 activation and before Uvicorn starts. There is no Phase 9B disable switch. The experimental branch is the isolation boundary; the interactive parent never seals Phase 9B.
- All current Phase 8 source files and current Architect/Coder production prompts remain unchanged.

## 2. Actual Windows result at the candidate SHA

| Gate | Result |
|---|---|
| Compile all new modules and tests | PASS |
| Isolated Phase 9B identity, Phase 8-wrapper qualification, ASGI stream/nonstream and integrated FastAPI enforcement | **38 passed** (2 dependency deprecation warnings) |
| Fresh-process real loaded Jack Kernel + actual Phase 8 + mandatory Phase 9B ASGI dispatch/admission tests | **3 passed** |
| Fresh **actual secured `jack_secure_entrypoint.py --serve` child**, loopback HTTP, repeated first/warm requests and invalid executor-path admission | **1 passed** |
| Unmodified existing Phase 8 source baseline, runtime enforcement, ledger observation and adversarial-preservation tests | **39 passed** |
| **Total** | **81 passed, no targeted failures** |

The live child smoke test used the mandatory Phase 9B secure child, loopback host, a reserved test port, unique runtime/ledger directories, context monitor disabled and an unavailable mock backend endpoint. It did **not** invoke real backend inference, perform real executor work, or test a live SSE connection.

## 3. Material defect found and corrected during this phase

The first enforcement Windows candidate had **10 failed / 28 passed**: seven harness errors used a synchronous ASGI `send` collector, and three legitimate FastAPI requests yielded false integrity invalidations.

After correcting the harness, diagnostics showed that the exact same `Phase9BASGIGuard.__call__` function and six registered route-app function objects had **different short-lived code fingerprints during active execution**, then immediately returned to their baseline fingerprint after the request. The original experimental primitive relied on `marshal.dumps(code)`. Replaced that opaque representation with a bounded, explicitly traversed, deterministic fingerprint of executable attributes (non-adaptive `co_code`, nested `co_consts`/code objects, call flags, variable/free/cell names, exception table, defaults and selected closure delegates). Retained all constant-only, nested-code, default/closure and identity substitution negative controls. Temporary failure-diagnostic instrumentation was removed after verification. The revised Windows candidate passed 81 targeted checks.

**Interpretation:** The experiment establishes a reproducible transient incompatibility with the prior `marshal.dumps` code-object fingerprint under this pinned Python/ASGI workload, not independent proof of an underlying CPython defect. The corrected deterministic representation is validated on the listed workloads; stress and all mode combinations remain.

## 4. Security containment demonstrated — and explicitly NOT demonstrated

**Demonstrated in the isolated ASGI and integrated FastAPI harnesses:** previously protected run/executor/Pi binding replacement is detected before subsequent guarded HTTP requests; a replaced route endpoint or route dependency cannot be silently released through the protected ASGI ingress; ordinary unchanged requests are admitted; tampering between safe SSE chunks withholds subsequent untrusted chunks; nonstream body release after header commit is aborted instead of emitting unverified content; authenticated/invalid body routes preserve user-input errors.

**Demonstrated in fresh real Kernel subprocesses:** Phase 8 and Phase 9B compose on the actual dynamically installed Kernel, which handles normal ASGI calls; deliberate `KERNEL.run`, executor-admission and route-dependency mutations cause subsequent HTTP denial.

**Demonstrated in actual secured serving child:** the real `--serve` startup with the mandatory protection, middleware warm-up and ordinary loopback HTTP requests pass.

**Still NOT proven:** authoritative in-process P0 topology against every same-privilege mutation, true live backend generation and long-running SSE, real external tool admission/side-effect prevention, Pi worker settlement and cancellation, higher-load/concurrency, all Agentic/Coder/Ultra/Responses paths, or full Windows/Pi regression suite. An attacker able to modify the ASGI middleware root or equally privileged checker/call-site code may bypass a process-local guard: the current prototype does **not** claim tamper resistance against unrestricted same-interpreter control. Verification and consequence are not atomic against hostile code that does not honor the verifier lock.

Phase 8 source-component sealing currently predates Phase 9B installation, so the new Phase 9B files are not automatically added to the frozen Phase 8 protected source set. This must be explicitly resolved or accepted as a bounded threat-model limitation before security release; do not silently alter the validated Phase 8 baseline.

## 5. Release blockers

1. **Mainline G0 remains red.** The Nov 24 `main` CI Coder planner suite had 24 failures / 24 passes; full Windows/Pi suite was skipped at the earlier gate. Current PR #169 is an incomplete separate test reconciliation effort. Never mask tests, change current authorized Architect/Coder prompts, or merge on the strength of these 81 targeted tests.
2. Qualify real long SSE with model/backend simulator, Phase 4 represented-path negative cases, durable writes, Pi side effects, and permitted multi-stage continuation under opt-in security enforcement.
3. Review ASGI chain/root tamper surface, route-handler/exception registries and module-internal delegates; specify which mutations are in/out of the protected capability threat model. Guard must not claim self-attestation.
4. Independently review impact of per-SSE-event whole-manifest verification on cost, cache/streaming, concurrency and cleanup/cancellation. No premature performance or readiness claim.
5. Complete full pinned Windows regression, Pi harnesses, independently reviewed diff, and source security-document reconciliation before promotion/tag.

**Disposition:** Phase 9B-C **experimental execution interception and actual secured-child smoke-qualified**, but **NOT a validated production security release; NO MERGE**.
