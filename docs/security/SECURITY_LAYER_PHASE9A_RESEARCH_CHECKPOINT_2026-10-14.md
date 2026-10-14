# Jack Kernel — Phase 9 Research Checkpoint

**Checkpoint date:** 2026-10-14
**Checkpoint class:** Retrospective technical research record; **NOT** a validated Phase-9 security release, not an enforcement authorization
**Phase:** 9 — Runtime Code Integrity (exploratory Phase 9A only)
**Repository:** <https://github.com/mlangford75-lgtm/Jack-Kernel>
**Current clean `main` and verified local-clone HEAD:** `ef613e46e70181f7fa8d054aabc3b5a744d8f704` (PR #46 merged)
**Frozen last fully validated security checkpoint:** Phase 8; annotated tag `security-layer-phase8-validated-2026-10-06`, peeled commit `cebe9fd75fe30a9c84a0af08d2105af448fc3d00`
**Current clean-clone Windows regression:** **527 passed in 8.88 seconds**, Python 3.14 virtual environment with pinned runtime/test dependencies
**Final Phase-9 decision:** **Phase 9A exploration closed and evidence preserved; Phase 9B code-integrity enforcement deferred/not authorized; P0/P1 inventory/fingerprint NOT frozen.**
**Scope:** This checkpoint is a retrospective Phase-9 research record, separate from any subsequent agent briefing or development plan.

---

## 1. Executive disposition — read this first

**What was actually completed:** A source-grounded Phase-9A design and callable/binding inventory, a live single-capture probe, three accepted same-process stability studies under benign HTTP and synthetic Agentic traffic, diagnostic negative controls that demonstrated a real fingerprint blind spot, and an improved *observation-only* identity candidate with 29 new tests and an isolated Windows integration. During the work, a real Agentic historical-tool-resume defect was discovered and fixed in merged **PR #45**. After Phase 9A exploration was deliberately stopped, a separate Responses API exception-disclosure defect was fixed in merged **PR #46**. The user then archived the experimental checkout, made a fresh clone of GitHub `main`, rebuilt `.venv`, and verified the clean baseline.

**What was not completed:** No approved production runtime-code-integrity guard; no Phase 9B admission/release enforcement; no frozen P0/P1 protected-dispatch manifest; no proven trusted runtime-fingerprint scheme; no formal Phase-9 security validation/tag/enforcement merge; no independent proof against hostile same-process mutation. The stronger Phase-9A.4 live comparison reported **three candidate binding differences** and unequal callable-node evidence under benign HTTP activity. Its underlying evidence ZIP was **not supplied for independent examination**, so those differences remain **unresolved**, not pronounced benign or malicious.

**Operational status:** Phase 8 remains the authoritative frozen security closure. Phase 9A diagnostic modules/hooks were **not merged** into `main`; they live in preserved experimental materials/old local checkout. Phase 10 can be implemented as a separate security boundary, but must not inherit a Phase-9 enforcement or runtime-object-attestation claim it has not earned. An immutable authority-state snapshot and trusted code-integrity check are different properties.

**No source changes or tests are requested by this checkpoint.** It records the completed work and constraints for a new agent. Retrospective statements about experiments are not equivalent to acceptance of new enforcement.

## 2. Jack Kernel identity and governing architecture

Jack Kernel v0.1.1 is a **local-first, host-authoritative inference mediation and control runtime** between agents/applications and OpenAI-compatible model backends. It is **not** the LLM and **not** the agent. Deep Research, Agentic, Code Debugging, and other cognition programs demonstrate what can be built on its host-owned programmable control plane; they are not the boundary of the product.

The governing doctrine is:

> **Probabilistic cognition may propose, but deterministic software must dispose.**

Closely related constraints, preserved from the Security Hardening Architecture and Phase-8 closure:

- Put each mechanism where Jack has both the information and the authority necessary to enforce it.
- Be strict about truth, identity, authority, and irreversible consequences; resilient about useful work.
- Contain a violation at the **narrowest** justified boundary; preserve completed cognition, previously released artifacts, safely recoverable state, and unrelated work.
- Observation is not authority. Evidence is not authority. A port is not identity. Cancellation is not physical settlement.
- Source mismatch, code/binding mutation, authority-policy mutation, and legitimate versioned state evolution are distinct classes of facts. Do not collapse their dispositions.
- The Kernel must not become so overzealous about self-measurement that normal execution is needlessly interrupted.

**Phase boundaries (do not conflate):**

| Phase | Object of protection | Actual state at this handoff |
|---|---|---|
| Phase 8 | Exact protected **on-disk active source** at bounded authority checks | **Validated, merged, tagged, frozen**; existing enforcement remains in force |
| Phase 9 | Selected **loaded Python module/function/binding/code identity** | **9A characterization only**; no enforcement, no approved protected fingerprint |
| Phase 10 | **Authority-bearing policy objects and legitimate dynamic security state transitions** | Separate next-phase scope; not delivered by Phase 9A |
| Phase 11 | Privacy and telemetry hardening | Planned; not delivered here |

At the time the checkpoint was drafted, live `CURRENT_SECURITY_STATUS.md` and `docs/security/README.md` had not been reconciled with Phase-9A experiments and still said “Phase 9 NOT STARTED.” The live guides may be updated independently without altering historical Phase-8 validation records or claiming Phase-9 runtime-code-integrity enforcement.

Governing reference: [`Documentation/Security/Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md`](https://github.com/mlangford75-lgtm/Jack-Kernel/blob/ef613e46e70181f7fa8d054aabc3b5a744d8f704/Documentation/Security/Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md), especially §§19, 22–23F, 36–36B, 39.

## 3. Baseline and secure serving-child composition mapped before experiments

The Phase 9A design began with read-only source inspection of `main` commit `b88feea7647403b0a77afc8d532ebef3e3240af6` (October 13). **This was a source-derived analysis**, not itself a real runtime attestation.

The supported secure `--serve` child constructs `jack_kernel` state, installs predecessor bundled runtime extensions, installs and seals Phase-8 source authority in the serving child, binds Phase-8 ledger observation, activates Phase-8 enforcement, and finally enters the server lifecycle. The optional Phase-9A probe ran only after the legitimate Phase-8 composition. The interactive parent and actual serving child must not be treated as equivalent authority surfaces.

Important selected host-owned dispatch bindings mapped and/or observed:

| Owner/binding surface | Relevant responsibility | Why Phase 9 inspection must distinguish it |
|---|---|---|
| `jk.KERNEL.run` | Inference admission, result/commit | Instance-assigned wrappers around native method |
| `jk.KERNEL.stream` | Stream admission and output | Longer composed wrapper/delegate chain |
| `jk._phase4_partition_structured_tool_calls` | Safe tool-call release | Module-global callable rebound through Phase 5 and Phase 8 |
| `jk._phase4_executor_admission_decision` | Executor/path admission | Module binding with security-critical wrapper layers |
| `jack_path_policy.authorize_represented_path` | Represented-path policy | Separate module binding; not implied by `jk` globals |
| `jk._proxy_pi_control_request` | Orchestration admission | Module-global proxy with credential, observation, and source layers |
| `jk.OrchestrationEventHub._publish`, `.__setattr__` | Event/diagnostic state | Class binding, not module or instance binding |
| `jk.BACKEND._client.post`, `.build_request` | Protected outbound model transport | Instance-bound HTTP transport wrappers |
| Phase-8 `source_authority.verify_now`, `._suspend_unverified` | Source authority measurement and suspension | Instance-level observer overrides with bound-class delegates |
| `source_authority.verify_for_authority_boundary`, `.admit` | Phase-8 admission | Class descriptors dynamically using instance methods |
| Code Debugging durable write/freeze/replace functions | Protected commits | Module bindings containing Phase-8 wrappers |
| `KERNEL._consume_pending_tool_resume`, related provenance helpers | Tool-result provenance | Resumed call history and exact live transaction identity |
| FastAPI `route.endpoint`, `route.dependant.call`, `route.app`, exception handlers, `middleware_stack` | Public ingress/dispatch and error release | Different dispatch locations can diverge; middleware is lazily constructed |

**Critical insight:** A function's displayed `__name__`, `__module__`, `__wrapped__`, or `_jack_*original` marker does not establish the actual executed delegate order. `functools.wraps` can copy metadata. Callables can be bound in `module.__dict__`, instance `__dict__`, class descriptors, route records, or exception handler registries. A fresh bound-method `getattr` can allocate a transient object: the meaningful identity is its owner and underlying descriptor/function, not the ephemeral bound-method wrapper ID. These observations motivated the inventory schema.

Early Phase-9A decisions were explicit: identify candidate P0/P1 authority surfaces first; observe rather than enforce; bound instrumentation; never freeze a fingerprint from static source inspection or a single idle capture.

## 4. Phase 9A.1 — probe construction and first actual secure-child capture

### 4.1 Probe implementation and iterations

The first experimental package, `Jack_Kernel_Phase9A1_Observe_Only_Probe.zip`, was revised to `..._v0_1_1.zip` to address safe evidence writing and capture semantics. The observer `jack_phase9a_inventory_probe.py`:

- Enumerates selected module, instance, class, FastAPI route/dependency, handler and middleware slots without calling the protected functions.
- Records stable logical **slot IDs**, owner categories, normalized binding locations, callable kinds and underlying method/owner relationships.
- Records bounded candidate delegate edges from specific closures, keyword defaults, `__wrapped__`, and wrapper attributes; it **does not prove** those edges are executed.
- Records exploratory code-shape descriptors (`co_code`-based information), scan/per-slot timing, omissions and truncation.
- Uses exclusive-create snapshot writing (`open('x')`): existing forensic evidence must never be overwritten.
- Has `authority: observation_only`, `fingerprint_schema_frozen: false`, and `no_authority_outcome_or_comparison: true` markers; it creates no new security disposition or API authority.

The v0.1.1 implementation report records **11 isolated probe tests passing** and compilation, including normalization, closure evidence, non-invocation, privacy, bounded cycles, routes/handlers, and exclusive-create behavior. Integration was opt-in on a diagnostic checkout only.

### 4.2 Initial live capture on original October 13 baseline

Original evidence file: `jack-phase9a1-live-c3122ca7df67.json`; byte SHA-256:

`d66fbf732016700d87315de557749df2ca8dd21da9ac40b46a451e5f8b72c9b9`

Captured in the real secured `--serve` child at **2026-10-13 15:46:40.272658 UTC**, on the then-current `b88feea...` baseline, Python 3.14.6:

| Fact | Initial actual observation |
|---|---:|
| Schema | `jack.phase9a1.observe-only.v1` |
| Dispatch slots | **91** |
| Resolved/unresolved | **90 / 1** |
| Python callable nodes | **103** |
| Candidate delegate evidence records | **90** |
| Candidate distinct `(from,to)` links | **45** |
| Registered FastAPI routes | **20** |
| Truncated | **False** |
| One scan | **1.2466 ms** |

Slot categories included 40 `route_object`, 16 `route_dependency_graph`, 14 `module`, five exception-handler registry slots, four source-authority class slots, four source-authority instance slots, three Kernel-instance slots, two backend transport slots, two orchestration hub class slots, and one app-instance slot. These are **selected inventory locations**, not 91 independently proven security-critical functions.

The single unresolved slot was `fastapi.middleware_stack`, legitimately `None` before the first HTTP request. This is framework lifecycle behavior, not an automatic security violation. The initial capture was accepted as **observational** evidence that the source-derived composition existed in the real child. It did **not** prove binding stability or complete executed call paths, and did not justify P0/P1 classification or Phase 9B.

### 4.3 From single snapshot to clean-main same-process v0.3 study

A one-shot second-capture marker/trigger was developed (`jack_phase9a_stability_trigger.py`) with a diagnostic hook, initially as post-workload v0.2 and then as `Jack_Phase9A1_Post_Workload_Clean_Main_v0_3.zip` for the repaired `main` baseline. A previous modified checkout was preserved rather than forcibly reset. The clean-main v0.3 diagnostic branch was `phase9a1-stability-05f5088b3639`, at commit `352f5feb949a44e65f83f6c7e83a58c235500cc8` (post-PR #45), with only `jack_secure_entrypoint.py` changed as a tracked optional hook. The observer and trigger modules/tests were untracked diagnostic files.

The established v0.3 suite added **19 tests (11 probe + 8 trigger)**; reported full regression count was **542 passed** (523 merged-main tests + 19 diagnostic tests).

### 4.4 Phase 9A.1 same-process result — **accepted within scope**

Evidence: `Jack_Phase9A1_Stability_Evidence_05f5088b3639.zip` — SHA-256:

`2a69ed28ebffc2d9ce75db5373802235e99918809d7c641049d400db334acf80`

Same secure process; before and after two read-only `GET /jack/runtime/status` requests. Capture interval **103.058 seconds**:

| Metric | Before | After |
|---|---:|---:|
| Slots | 91 | 91 |
| Python callable nodes | 103 | 103 |
| Delegate records | 90 | 90 |
| Unresolved slots | 1 | 0 |
| Scan cost | 1.4237 ms | 1.2934 ms |
| Truncated | No | No |

After removing per-scan timing and **normalizing ephemeral function/owner labels**, the other 90 slot records, 103 selected Python callable descriptors/code shapes, and 90 candidate delegate records were structurally unchanged. One genuine lifecycle transition was observed: `fastapi.middleware_stack` changed from `missing` to `callable_object_uninspected`. Five exception-handler temporary `fn-####`/owner references were renumbered as a consequence of the new middleware object being numbered. The corresponding handler descriptors did **not** materially change.

**9A.1 result:** PASS for repeatability and observed benign HTTP stability; no whole-ASGI internal measurement, no trusted baseline, no code-integrity enforcement.

## 5. Phase 9A.2 — warm Agentic integration and historical tool-result replay

### 5.1 PR #45: real defect uncovered during Phase 9 work (separate from Phase-9 integrity guard)

During integration preparation, a real **Agentic tool-resume regression** was discovered: a legitimate caller could include a historical **retired** tool result A while presenting the current live result B, and the Kernel rejected the continuation with HTTP **409** as if the retired result were an extra active tool result. The required distinction was **historical retired evidence versus a current withheld/live sibling**; the latter must remain rejected.

The repair was implemented in an isolated branch `fix/tool-resume-historical-results-20261013`, merged as **[PR #45](https://github.com/mlangford75-lgtm/Jack-Kernel/pull/45)** with merge commit:

`352f5feb949a44e65f83f6c7e83a58c235500cc8`

Changed source/tests included `jack_kernel.py`, `tests/test_phase4_multicall_containment.py`, and `tests/test_resilience.py`. Windows CI and merged-main full regression passed **523 tests**. The fix narrowed retired-history interpretation **without relaxing live transaction matching or withheld-result rejection**. This was an actual Kernel code fix made **during** Phase 9A, but **not** a Phase-9 runtime-code-integrity implementation.

### 5.2 Deterministic warm workload and evidence

Package: `Jack_Phase9A2_Warm_Runtime_Observation_v0_1.zip`, SHA-256:

`14ea7117ca5b4ba5174eb18076faacd78aef0c708f6a7d97b68e59ae5352b34f`

The package contained a deterministic fake OpenAI-compatible backend workload driver and tests. **Five targeted harness tests passed on Windows.** The actual secured Jack serving endpoint ran **Agentic** mode with Preserve Thinking on, talking to an isolated local mock backend. Its run token was `ab5dea4a4add` (Jack `127.0.0.1:50098`, mock `127.0.0.1:60002`). No LM Studio inference or external tool execution was involved.

Evidence: `Jack_Phase9A2_Warm_Runtime_Evidence_ab5dea4a4add.zip`, SHA-256:

`ac530c53fbd48cafed6c471bbcbcb72dedb6655b63c07521ad008f821cf07692`

Transcript and harness results established:

- Two completed nonstream Agentic turns, each with Stage-1 completion and Stage-2 Jack XML, across **six** deterministic mock phases.
- Two synthetic tool results, **zero real tool executions**, **zero model inference**.
- Historical retired result A replayed in the caller's message history during live B resume; current B was accepted and retired A was **not** included in the backend's active B-continuation history.
- Two completed commits; runtime identity checked; the successful scenario is specifically the positive retired-history regression, not a blanket validation of all tool-resume cases.

### 5.3 Phase 9A.2 graph comparison — **accepted within scope**

| Metric | Before | After |
|---|---:|---:|
| Slots | 91 | 91 |
| Python callable nodes | 103 | 103 |
| Candidate delegate records | 90 | 90 |
| Unresolved slots | 1 | 0 |
| Scan cost | 1.3545 ms | 1.3113 ms |
| Snapshot interval | 135.072 seconds between captures | — |

After normalization: stable 90 unaffected slot records, 103 descriptors and 90 delegate records; same expected lazy FastAPI middleware initialization and five temporary exception-handler reference renumberings. No observed authority-binding change under this **synthetic, nonstream** workload.

**9A.2 result:** PASS for the exercised positive integration path and the recorded graph's stability, **not** for streaming, real tool execution, all malicious replay, or Phase 9B enforcement.

## 6. Phase 9A.3 — negative controls, withheld-sibling regression, concurrent HTTP

### 6.1 9A.3A — disposable behavioral negative controls

Package: `Jack_Phase9A3_Negative_Control_Lifecycle_v0_1.zip`, SHA-256:

`b8a4573cf704dc282d8e53dd8b64ffda924d5ccbb032ba4b5d707f3881af94ee`

Windows execution succeeded with **10/10** new diagnostic tests plus **1/1** pre-existing `tests/test_phase4_multicall_containment.py::test_resume_rejects_extra_result_for_withheld_sibling`. The latter is a targeted unit-level rejection of a fabricated extra result for a withheld sibling, **not** proof of a fully exercised end-to-end hostile tool scenario.

In disposable local functions:

1. Repeated unchanged functions produced stable comparable shape evidence.
2. A wrapper/delegate substitution changed the observable wrapper shape and candidate link.
3. **Crucially, a constant-only substitution changed actual function behavior and `co_consts` while leaving `co_code` bytes and the v1 probe's recorded shape the same. The v1 probe failed to detect this meaningful behavioral alteration.**
4. No production Jack Kernel callable was mutated; the harness reported `production_kernel_mutated: false`.

The console showed the complete negative-control JSON report, including `current_probe_missed_constant_only_substitution: true`, `fingerprint_freeze_permitted: false`, and `phase9b_enforcement_permitted: false`. The separate negative-control report JSON was **not** included in the subsequent 9A.3B ZIP; the record here relies on the retained user PowerShell transcript, the kit, and its tests.

**9A.3A result:** PASS for executing the tests, but **FAIL of v1 fingerprint sufficiency**. A missing constant-sensitive identity component is a demonstrated blind spot, not a speculative threat. This is the principal reason not to freeze v1 production fingerprints.

### 6.2 9A.3B — bounded benign concurrency observation

Actual secure Jack child: `phase9a3-readonly-72031c518da8`, loopback port `53782`. Backend explicitly unavailable, cognition OFF. No model inference or tool calls. Four workers issued **32 HTTP requests**, split 16 `GET /` and 16 `GET /jack/runtime/status`; **32/32 HTTP 200** responses. Uvicorn logged normal shutdown; Python 3.14 displayed `CancelledError`/`KeyboardInterrupt` after Ctrl+C, not evidence of Kernel authority failure.

Evidence: `Jack_Phase9A3_Evidence_72031c518da8.zip`, SHA-256:

`12a297cbf5a99f7ed23f685066dd4805044d063a64bacf15a53d6090ec7d1e50`

| Metric | Before | After |
|---|---:|---:|
| Slots | 91 | 91 |
| Python callable nodes | 103 | 103 |
| Candidate delegate records | 90 | 90 |
| Unresolved slots | 1 | 0 |
| Scan cost | 1.4328 ms | 1.7193 ms |
| Snapshot interval | 108.062 seconds between captures | — |

The 90 other slot records, 103 descriptors and 90 candidate links were structurally stable after normalizing capture-local references. The only known middleware transition and temporary exception-handler reindexing recurred. This confirms no *recorded structural changes* in this scenario, **not** generalized concurrency correctness, tamper detection, or stable enforcement timing under load.

**9A.3B result:** PASS within concurrent benign read-only observation scope.

## 7. Phase 9A.4 — stronger identity candidate and **unresolved** live comparison

### 7.1 What was built

Package: `Jack_Phase9A4_Observer_Identity_Candidate_v0_1.zip`, SHA-256:

`e94f6a4af9aa7724c5be0afb9b0b66c3cd173a6b29f4821fb52a6e3baf0c1703`

The candidate **did not overwrite the v1 observer**. Its experimental components were:

| Component | Role |
|---|---|
| `jack_phase9a4_evidence.py` | Bounded, non-invoking process-local HMAC-digest descriptions of bytecode **and constants**, nested code objects, flags, defaults/kwdefaults, closure contents, selected globals, bound receiver/object alias |
| `jack_phase9a4_inventory_candidate.py` | Independent versioned candidate inventory and limited ASGI middleware-chain characterization |
| `jack_phase9a4_trigger.py` | One-shot opt-in second capture, exclusive evidence creation |
| `phase9a4_compare.py` | Offline slot/edge normalization and candidate delta report; observational only |
| `test_phase9a4_identity_candidate.py`, `test_phase9a4_trigger.py` | 29 tests for detection, stability, bounds, privacy/non-invocation, omission behavior |
| `phase9a4_optional_existing_diagnostic_hook.patch` | Additive opt-in integration into the **existing diagnostic** `jack_secure_entrypoint.py`, not clean `main` |

The candidate uses a **random in-process, nonserialized HMAC key**. Thus digest equality is intended only for same-process captures with the same observer instance: **not** deterministic cross-process fingerprints or a remote attestation proof. Opaque mutable state and dynamic lookups are expressly uninspected/partially covered, rather than silently promoted to an integrity guarantee. Snapshot instrumentation is nonauthoritative and does not replace Phase-8 source guard.

### 7.2 Windows installation and full regression

The user downloaded the package, validated SHA-256, verified the expected preceding branch/commit and unchanged v1 module, checked the optional patch with `git apply --check`, then created:

`phase9a4-identity-f1d13ac8ebf5`

at base HEAD `352f5feb949a44e65f83f6c7e83a58c235500cc8`, applied the optional patch, and copied six new diagnostic module/test files **without committing or merging the diagnostic implementation**.

Windows results:

- Phase-9A.4 candidate isolated tests: **29 passed**, two third-party deprecation warnings (FastAPI/Starlette TestClient stack).
- Full tests on the experimental working tree: **571 passed**, two warnings, 8.10 seconds (523 upstream base + 19 v1/trigger + 29 v2 tests).
- The only tracked working-tree change reported by the installation runbook was `jack_secure_entrypoint.py`. No service was started during installation.

**Passing unit/regression tests is not approval to use those digests as runtime integrity enforcement.**

### 7.3 Windows same-process live identity trial

Actual child: `phase9a4-identity-c4c19640cf96`, on `127.0.0.1:64080`, reasoning OFF, intentionally unavailable backend, two successful read-only `GET /jack/runtime/status` requests. The observer produced initial and second snapshots; the optional offline comparator ran successfully. Console result:

```text
SECOND IDENTITY SNAPSHOT CAPTURED
BEFORE SLOTS: 91
AFTER SLOTS:  91
PHASE9A4_OBSERVATIONAL_COMPARISON_CREATED
Candidate binding differences: 3
Enforcement authorized: False
CANDIDATE BINDING CHANGES: 3
CALLABLE MULTISETS MATCH: False
DELEGATE MULTISETS MATCH: True
PHASE 9A.4 EVIDENCE READY
```

ZIP created on the user's Desktop:

`Jack_Phase9A4_Identity_Evidence_c4c19640cf96.zip` (reported **85,716 bytes**), Windows-reported SHA-256:

`48a7335e71cc71993e2721bf82c89b0d8e91c426c1ba7c58bcb5eb2b51e71f0e`

**Important evidentiary limit:** In the supplied conversation archive, only the **PowerShell output** for this Phase-9A.4 comparison was supplied. The actual 9A.4 evidence ZIP and the three individual diff entries were **not received and independently reviewed**. Accordingly the following are **unknown**: which exact three slots or fingerprints differed; whether those differences are expected middleware initialization, alias/reference churn, sensitivity to legitimate runtime state, or an actual unexpected binding change. Do **not** infer their cause. Do **not** mark the strengthened schema “live stable” or use it to freeze P0/P1.

**9A.4 result:** Candidate implemented, Windows tests PASS, live collection/comparator EXECUTED, **stability qualification UNRESOLVED**. Phase 9B remains unauthorized.

## 8. Consolidated observations and the limits of what they prove

All three accepted **v1** same-process studies made the following exact selected observations:

| Study | Activity | Slots (before→after) | Callable descriptors | Delegate observations | Scan ms before→after | Interval |
|---|---|---|---|---|---|---|
| 9A.1 v0.3 | 2 benign status requests | 91→91 | 103→103 | 90→90 | 1.4237→1.2934 | 103.058 s |
| 9A.2 | 2 completed synthetic Agentic resume turns | 91→91 | 103→103 | 90→90 | 1.3545→1.3113 | 135.072 s |
| 9A.3B | 32 benign HTTP requests; 4 workers | 91→91 | 103→103 | 90→90 | 1.4328→1.7193 | 108.062 s |

In each v1 pair, the initial middleware slot was unresolved and the after-capture recorded a callable middleware object as **uninspected**. After stable slot-key comparison and normalization of ephemeral IDs, the remaining recorded descriptions and candidate delegates matched. This is evidence of **recorded structural repeatability under these workloads**, not of complete behavioral equivalence or security hardening.

**Explicit limits still in force:**

1. The original v1 code-shape scheme missed a constant-only behavior change in the disposable negative control.
2. The v2 candidate adds substantial coverage but still omits opaque mutable objects, some dynamic global/attribute lookups and runtime dispatch effects.
3. The observer is inside the very interpreter it measures and is not an independent trust anchor against unrestricted in-process mutation.
4. Snapshot equality at two instants does **not** prove that an object did not transiently change between them and change back.
5. Recorded wrapper/closure/marker **candidate** links are not proof of actual invocation/dispatch order.
6. FastAPI/Starlette middleware initialization must be treated as an explicit lifecycle transition, not automatically compromise; the v1 probe did not attest ASGI internals.
7. A handful of ~1–2 ms scan observations does not establish p95/p99 production overhead, low-impact under throughput, or correctness of checks added to hot paths.
8. Nothing in 9A establishes resistance to hostile same-process verifier mutation, arbitrary Python/native memory control, tampering with the integrity checker, or remote attestation.
9. 9A2 did not exercise real external tools or models, streaming resumes, all replay/withheld-sibling cross-products, or simultaneous real GPU inference.
10. The v2 live trial's three differences are not classified because underlying evidence was not reviewed.

## 9. Decisions, frozen constraints, and what **not** to do

**Decisions actually made:**

- **Phase 9A exploratory characterization STOPPED/CLOSED BY PROJECT DECISION** on October 14 after diminishing returns; evidence preserved, not deleted.
- **Phase 9B enforcement NOT designed/validated/activated.** There was never a production guard enforcing Phase-9 loaded-code identity.
- **P0/P1 protected runtime-callable classifications NOT FROZEN** and no candidate code-identity fingerprint schema promoted into an authority predicate.
- Existing Phase-8 source-authority installation/lifecycle and preserving-action semantics remain unchanged and govern current security behavior.
- Phase 9A.4 was not merged; the next agent must not assume the new observer is in `main` or available in the fresh active clone.
- Any later 9B effort requires an explicit threat model, trusted anchor, settled P0/P1 scope, canonical comparable identity scheme, treatment of lifecycle changes, confirmation vs uncertainty policy, non-brittle containment and adversarial closure. **It cannot infer these from 9A passing tests.**

**Do not represent Phase 9 as a validated security checkpoint.** Use `Phase 9A observation/research archived; Phase 9 enforcement deferred` as the precise status. The Phase-8 validated tag stays the last formal frozen security milestone.

**Do not retroactively assign the PR #45 tool-resume fix or PR #46 diagnostic release fix to the Phase-9 runtime-integrity guard.** They are real merged Kernel corrections that arose during/after the work but did not create Phase-9 object-integrity authority.

## 10. After Phase 9: separate merged fixes and clean-main restoration

### 10.1 PR #46 — Responses API exception non-disclosure (not Phase-9 integrity)

After the user directed the work away from extensive observer characterization, a separate concrete issue was identified in `/v1/responses`: raw internal exception strings could reach nonstream HTTP 500 diagnostics and streaming `response.failed` SSE error messages.

Fix on branch `fix/responses-error-nondisclosure-20261014` and merged [PR #46](https://github.com/mlangford75-lgtm/Jack-Kernel/pull/46): generic client-safe errors for internal exceptions; preserve existing `HTTPException` policy rejections (such as HTTP 409), and preserve Phase-7 **canonical sanitized** `protected_credential_diagnostic_withheld` and `diagnostic_stream_exception_release` markers.

The first draft had **9 targeted tests PASS**, but the complete Windows suite reported **525 PASS / 1 FAIL**: the change had inadvertently erased an established Phase-7 sanitized stream-error contract. It was **not merged in that state**. The fix was corrected, a preservation regression added, then **527/527 full Windows tests passed**. GitHub CI for the final head `95936aa0ff51204a271b74ea2b89f9edf57d99da` succeeded. Merge commit:

`ef613e46e70181f7fa8d054aabc3b5a744d8f704`.

This is a verified security defect repair, **not** a Phase-9 runtime-code-integrity deliverable and **not** Phase-11 formal closure. Phase-11 privacy/telemetry hardening remains broader future work.

### 10.2 Old diagnostic checkout preserved; fresh `main` cloned and tested

The user explicitly requested a clean new clone rather than continuing on a diagnosis-laden working directory. On October 14 the existing local folder was **moved**, not deleted, to:

`C:\Users\default.DESKTOP-M8143Q1\Desktop\Jack Kernel - Old Backup 20261014-051536`

The fresh repository was cloned to:

`C:\Users\default.DESKTOP-M8143Q1\Desktop\Jack Kernel`

PowerShell verified `main`, `HEAD == ef613e46e70181f7fa8d054aabc3b5a744d8f704`, PR #46 merge ancestry, and **clean `git status --porcelain`**. The user created a new `py -3.14 -m venv .venv`, installed pinned `requirements.txt` plus `requirements-test.txt`, and ran:

```text
527 passed in 8.88s
FRESH JACK KERNEL READY
```

**This is the verified source baseline at this checkpoint.** Do not use a stale experimental branch as the authoritative base. Keep the old backup available until its work is intentionally disposed of. The previous experimental diagnostic-only pytest total **571** is **not** the expected test count on the new clean `main`; **527** is the verified clean-main count after PR #46.

## 11. Chain-of-custody — preserved local evidence and package hashes

The files below were available in the Phase-9 research workspace, and the ZIP hashes below were recomputed from the local archived files when preparing this checkpoint. SHA-256 is evidence **file integrity**, not code-authority proof. A file's presence does not imply it is installed into current `main`.

| Artifact | SHA-256 / role |
|---|---|
| `jack-phase9a1-live-c3122ca7df67.json` | `d66fbf732016700d87315de557749df2ca8dd21da9ac40b46a451e5f8b72c9b9` — first live v1 capture on `b88feea...` |
| `Jack_Kernel_Phase9A1_Observe_Only_Probe_v0_1_1.zip` | `94c878c1bde9fe55ae82be4ae2c41239db30a71c77ba37d77f8b76ba5f5f7478` — corrected initial probe |
| `Jack_Phase9A1_Post_Workload_Clean_Main_v0_3.zip` | `5873916fa11c3b95d9a14d0adb7d9b3392bab0c32f1f849d63f96bc6624a2f16` — post-PR #45 composed hook and 19 tests |
| `Jack_Phase9A1_Stability_Evidence_05f5088b3639.zip` | `2a69ed28ebffc2d9ce75db5373802235e99918809d7c641049d400db334acf80` — before/after v1 benign HTTP |
| `Jack_Phase9A2_Warm_Runtime_Observation_v0_1.zip` | `14ea7117ca5b4ba5174eb18076faacd78aef0c708f6a7d97b68e59ae5352b34f` — deterministic warm Agentic kit |
| `Jack_Phase9A2_Warm_Runtime_Evidence_ab5dea4a4add.zip` | `ac530c53fbd48cafed6c471bbcbcb72dedb6655b63c07521ad008f821cf07692` — before/after v1 + Agentic summary |
| `Jack_Phase9A3_Negative_Control_Lifecycle_v0_1.zip` | `b8a4573cf704dc282d8e53dd8b64ffda924d5ccbb032ba4b5d707f3881af94ee` — disposable negative controls/concurrency driver |
| `Jack_Phase9A3_Evidence_72031c518da8.zip` | `12a297cbf5a99f7ed23f685066dd4805044d063a64bacf15a53d6090ec7d1e50` — before/after v1 + 32-request report |
| `Jack_Phase9A4_Observer_Identity_Candidate_v0_1.zip` | `e94f6a4af9aa7724c5be0afb9b0b66c3cd173a6b29f4821fb52a6e3baf0c1703` — improved unmerged observation-only candidate |
| `Jack_Phase9A4_Identity_Evidence_c4c19640cf96.zip` | **Not uploaded for independent verification**; user console reported `48a7335e71cc71993e2721bf82c89b0d8e91c426c1ba7c58bcb5eb2b51e71f0e` |

Supporting authored assessments/records preserved in the workspace:

- `Jack_Kernel_Phase_9A_Runtime_Code_Integrity_Design_v0_1.md` — architecture, source mapping, preliminary threat scope (proposed, not approved).
- `Jack_Kernel_Phase9A1_First_Live_Runtime_Evidence_Assessment_2026-10-13.md` — first actual secure-child inventory.
- `Jack_Phase9A1_Same_Process_Stability_Evidence_Assessment_2026-10-13.md` — v0.3 HTTP stability.
- `Jack_Phase9A2_Warm_Runtime_Stability_Assessment_2026-10-14.md` — synthetic Agentic evidence and graph normalization.
- `Jack_Phase9A_Consolidated_Evidence_and_9A4_Recommendation_2026-10-14.md` — prior v1 three-study consolidation.
- `Jack_Phase9A4_Observer_Identity_Candidate_v0_1/README.md` and runbook — candidate design limitations and installation.
- User-provided Windows PowerShell transcripts (Oct 13–14), including 9A.3A report, 9A.4 installation/comparison, PR #46 initial regression and recovery, and clean-clone verification.

The first three same-process ZIP archives have been parsed and hash-checked during the research, including exact member schemas and counts. Their `scan_ns` measurements, runtime labels, and timestamps were obtained from the JSON evidence, not guessed. The 9A.4 candidate differential classification could **not** be independently redone because its ZIP is missing from the conversation.

## 12. Phase 9 claim-disposition table

| Claim or proposed claim | Disposition | Supporting reason |
|---|---|---|
| Phase 8 protects selected active source identity at bounded checks | **Previously validated/frozen** | 2026-10-06 closure/tag; no Phase-9 change |
| A Phase-9A inventory successfully enumerated selected live secure-child bindings | **Supported** | Oct 13 actual first 91-slot capture |
| Original v1 graph was structurally stable under the three tested benign workloads | **Supported within recorded scope** | Three before/after archives with normalized 91/103/90 graph |
| PR #45 repaired specific retired-result replay and preserved withheld-sibling rejection | **Merged and tested** | PR #45; 523 regressions; targeted 9A.2 workload and 9A.3A unit |
| V1 snapshot code-shape digest binds actual function behavior | **False** | Constant-only negative-control behavior change was missed |
| V2 observer includes constants/defaults/closures/selected globals | **Implemented/tested experimentally** | 29 tests and Phase-9A.4 package, separate schema |
| V2 observer stable during normal HTTP lifecycle | **Unresolved** | Three live comparison differences; underlying ZIP not reviewed |
| Phase-9 P0/P1 fingerprint is frozen | **No** | Never approved |
| Phase-9 Runtime Code Integrity enforcement exists in `main` | **No** | Never merged or activated |
| Phase 9 formally validated, tagged, security-closed | **No** | Only research close-out; Phase 8 last formal frozen checkpoint |
| PR #46 hides raw Responses exception text while preserving Phase-7 markers | **Merged and tested** | 527/527 on final clean `main`, CI passed |
| Fresh local development clone is ready | **Yes** | Verified clean `main`, pinned venv, 527 regressions |
| Phase 10 may use Phase 9 enforcement as a predecessor dependency | **No** | It was never established; Phase 10 is a separate, bounded workstream |

## 13. Final Phase 9 checkpoint statement

**Phase 9A produced a credible map of selected loaded authority-dispatch bindings and successful limited stability observations, discovered a real weakness in the first measurement scheme, and produced an improved but unqualified observation-only candidate. It did not deliver enforceable Runtime Code Integrity.** The research was deliberately stopped to avoid disproportionate work on exploratory fingerprint characterization. The 9A.4 three-difference result remains an unresolved record, not a basis for either trust or alarm.

The production source at handoff is the fresh verified `main` at `ef613e46e70181f7fa8d054aabc3b5a744d8f704`, with PR #45 and PR #46 merged, **527 Windows regressions passing**, and all Phase-9 diagnostic implementation kept out of `main`. Phase-8 enforcement remains the last frozen integrated security baseline.

**Boundary for subsequent phases:** No subsequent phase may invent a Phase-9 enforcement guarantee, reopen the frozen Phase-8 closure, or treat the discontinued observer campaign as a production runtime protection. This checkpoint does not grant authority to a subsequent phase to assume unimplemented Phase-9 security guarantees.

---

*Prepared 2026-10-14 from Phase-9 research packages, live evidence archives, Windows execution records, project discussions, and the repository's governing Security Hardening Architecture. This is a historical Phase-9 checkpoint, not a release attestation.*