# Jack Kernel — Phase 9B-A Current Runtime Authority Map and G0 Regression Gate

**Prepared:** 2026-11-25
**Status:** Read-only engineering assessment / **not** a Phase 9B enforcement implementation or approval to activate it.
**Repository:** [mlangford75-lgtm/Jack-Kernel](https://github.com/mlangford75-lgtm/Jack-Kernel)
**Inspected main HEAD:** `7ba82072647941f779f5c5fa955274112ca04844` (2026-11-24T18:21:12Z)
**Isolated planning branch:** `security/phase9b-runtime-code-integrity-20261125`, created from that exact HEAD.
**Last validated security release:** Phase 8, `security-layer-phase8-validated-2026-10-06`.
**Governing scope:** September 26 corrected architecture, October 14 Phase 9A research checkpoint, November 25 remaining-work specification.
**Read-only milestone:** No runtime or test sources are modified in this assessment.

## 1. Executive disposition

The intervening code changes are material. GitHub compare reports **892 commits** since the October 14 Phase 9 handoff (`ef613e46...` → `7ba82072...`). Code Debugging, Agentic, Deep Reasoning/Ultra, Coder, cache, tool-resume, and Pi paths have evolved. It would be unsafe to copy the October Phase 9A.4 exploratory observer into production.

The **shared secure-serving composition is still usable**: `jack_secure_entrypoint.main()` installs the bundled authority extensions, seals Phase 8 in the actual `--serve` process, installs the Phase 8 forensic observer, and activates Phase 8 before `jk.main()` enters the server. No Phase 9B production guard is installed in that entrypoint today.

**Decision:** Proceed with narrow P0 design and unit/serving-child proof, but **do not claim G0 green, activate a broad runtime fingerprint, merge, or tag**. This report is a phase stop gate, not implementation acceptance.

## 2. G0 — exact current CI evidence and constraints

GitHub Actions [main CI run 45458603830](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/45458603830), commit `7ba82072...`, completed on November 24 **with failure**.

| Workflow gate | Actual result |
|---|---|
| Python 3.14.6 setup, pinned dependency installation, compilation | PASS |
| Phase 5 consequence gate targeted tests | PASS |
| Phase 6 authority/ledger targeted tests | PASS |
| Phase 7 credential/DLP targeted tests | PASS |
| Phase 8 source authority / preservation targeted tests | PASS |
| Ultra review/prefix preservation | PASS |
| Delegated Planner task/cache-stable prompt boundary | PASS |
| Planner history isolation and failed-inspection handoff | PASS |
| `tests/test_agentic_coder_planner_executor.py` | **24 passed / 24 failed** |
| Full Python regression suite | **SKIPPED** (earlier gate failed) |
| Windows fresh-clone integration | **SKIPPED** |
| Pi/Node control bridge harnesses | **SKIPPED** |

The failures include assertions against old Architect prompt wording and old read-only tool schemas (`tools=["read"]`) while the November 24 merged task-data isolation and tool-free Architect contract changed the current runtime. They **cannot all be classified as stale without investigation**. The failing suite also reports tool-resume, stage continuation, user-role isolation, and partial-spec preservation cases that may reveal real regressions.

**G0 resolution:** Reconcile assertions against current approved behavior on a *separate* experimental regression branch/PR; preserve the current Architect and Coder production prompts, authentication, and user/tool authority. Retain negative tests proving forbidden tools remain unavailable. Do not blanket delete, skip, xfail, or rewrite tests merely to make CI green. Open PR #169 is a pre-existing test-reconciliation experiment based on an earlier branch; inspect and rebase deliberately rather than merging blindly. Re-run complete Windows regression, fresh-clone bootstrap, security tests, and Pi harnesses before a security release.

**Safe parallelism:** G0 is a *release prerequisite*, not a prohibition against read-only Phase 9B mapping or isolated tests.

## 3. Current secured startup and wrapper order

**Observed current source:**

1. `jack_kernel._install_bundled_runtime_extensions()` binds Phase 4 policy, installs evidence provenance / Static Canary / Phase 7 credential protection, Phase 5 consequence gate, Phase 6 ledger, and Responses compatibility in the supported shared installation path (`jack_kernel.py`, around lines 17916–17966).
2. `jack_secure_entrypoint.main()` in `--serve` invokes `jack_source_drift_guard.install(...)` to establish the Phase 8 source baseline; it then invokes `_install_phase8_ledger_observer(...)` and `jack_source_drift_guard.activate_runtime_enforcement(...)` (`jack_secure_entrypoint.py`, around lines 331–354).
3. Phase 8's activation wraps `jk.KERNEL.run`, `jk.KERNEL.stream`, `jk._phase4_partition_structured_tool_calls`, `jk._phase4_executor_admission_decision`, the Code Debugging durable-commit callables, and `jk._proxy_pi_control_request`; it adds the source status endpoint and an unavailable handler (`jack_source_drift_guard.py`, around lines 591–820).
4. The secure child enters the existing Jack server only **after** these wrappers exist. The interactive launcher is not a sealing authority.

**Implementation insertion candidate:** A separately reviewed `jack_runtime_code_guard.py` installed by the secure entrypoint *after* the accepted Phase 8 activation and *before* public serving. Avoid editing the frozen Phase 8 module solely to add Phase 9. Startup must either explicitly qualify and seal every required P0 slot or withhold public protected authority; never silently omit a mandatory slot or accept a before-first-request observer as complete ASGI attestation.

## 4. Grounded live authority/dispatch map — provisional P0

These are **candidate P0 bindings**, not yet an approved protection manifest. Names and line numbers refer to the above main commit. Priority reflects consequence, not the old Phase 9A 91-slot observation count.

| Candidate | Real active binding / dispatch path | Consequence if bypassed | Important lifecycle / binding caveat |
|---|---|---|---|
| **P0-01: nonstream result** | `jk.KERNEL.run` instance slot, Phase 7 output/evidence wrapper then Phase 8 source wrapper; Chat Completions calls through `chat_completions` (`jack_kernel.py:16341+`), Responses calls through registered route (`jack_responses_compat.py:426+`) | Model output/tool result released without protected checks | The instance attribute holds a wrapper and the captured predecessor; checking only `JackQwenKernel.run` class descriptor is insufficient |
| **P0-02: streamed release** | `jk.KERNEL.stream` instance slot, Phase 7 `_guarded_stream` wrapper then Phase 8 stream wrapper; `_safe_public_stream` (`jack_kernel.py:16279+`) and Responses `_stream` (`jack_responses_compat.py:242+`) | Unauthorized SSE/tool-call release | Check at meaningful pre-release points, including after inference; preserve safe prefix and blocked transaction semantics |
| **P0-03: tool-call release** | `jk._phase4_partition_structured_tool_calls` module binding, installed Phase 5 + Phase 8 wrappers; original defined `jack_kernel.py:5115` | NEVER/workspace/tool-policy escape before tool proposal is released | Code may refer dynamically to the module global; protect effective module slot *and* wrapper delegate |
| **P0-04: executor/path admission** | `jk._phase4_executor_admission_decision` module binding, Phase 5 + Phase 8 wrappers; `/jack/security/path-admission` route obtains live pending call (`jack_kernel.py:16136+`) | Unauthorized executor/path admission | Protect route's actual stored executable and Phase 4/5 delegates; do not mistake represented-path protection for final OS object attestation |
| **P0-05: represented-path policies** | `jack_path_policy.authorize_represented_path` is rebound by Phase 5; `authorize_structured_tool_call` and `authorize_executor_tool_call` are dynamic module functions (`jack_path_policy.py`) | Workspace/NEVER and capability policy bypass | Protect the Phase 5 effective wrapper and the policy-call functions that current executable paths actually read |
| **P0-06: mutating Pi control** | `jk._proxy_pi_control_request` module binding wrapped by security extensions and Phase 8; `POST` routes for tasks/cancel/session-new (`jack_kernel.py:16071–16084`) | Privileged worker action without correct admission | Existing Phase 8 admits *before* dispatch and does not claim physical worker settlement; retain that limit |
| **P0-07: source authority self-protection** | Active `RuntimeSourceAuthority` instance with `verify_now` observation wrapper, `verify_for_authority_boundary` class descriptor, `admit`, and underlying `_measure_regular_file` (`jack_source_drift_guard.py`) | Phase 8 source checks silently replaced | This is the hardest trust-boundary issue: an in-process verifier cannot resist arbitrary equally privileged interpreter mutation |
| **P0-08: entry/HTTP dispatch** | FastAPI `APP.routes` contains the `/v1/chat/completions` route; `jack_responses_compat.register` adds `/v1/responses`; path and mutating control routes are separately registered | Route or stored dependency bypass despite intact module symbol | Inspect `APIRoute.endpoint`, `APIRoute.dependant.call`, `APIRoute.app`, and exception handlers as *distinct* dispatch surfaces; `APP.middleware_stack` is lazy |
| **P0-09: output/credential delegate** | `jack_evidence_guard.install` captures the original `KERNEL.run/stream` and wraps result/stream protection (`jack_evidence_guard.py:1883–2022`); credentials and diagnostics are installed in Phase 7 | Secret/evidence release | Protect effective wrapper and explicitly approved delegate links; do not re-fingerprint ordinary mutable request or credential-policy state as executable identity |

**P1 candidates for a later bounded increment:** `jk._debugging_write_open_intake_report`, `jk._debugging_freeze_intake`, `jk._debugging_atomic_replace_report` (Phase 8 durable writes); `KERNEL._consume_pending_tool_resume` plus Coder/Agentic checkpoint selectors; protected backend HTTP transport wrappers; `OrchestrationEventHub` dispatch and exception handlers. Promote to P0 only where a direct real protected consequence demonstrates the need.

### Dispatch proof obligations

- **Chat streaming:** `APP` route → `chat_completions` → `_safe_public_stream` → active `KERNEL.stream` wrapper → backend/cognition → protected SSE release.
- **Chat nonstream:** `APP` route → `chat_completions` → active `KERNEL.run` wrapper → `completion_envelope` → `JSONResponse`.
- **Responses:** `jack_responses_compat.register` stores a route whose handler invokes the same active `jk.KERNEL.run/stream`; Responses event translation is another potential public-release seam.
- **Executor:** `APP` route → authenticated pending tool call snapshot → current `jk._phase4_executor_admission_decision` → effective policy/consequence delegates.
- **Pi mutating control:** route → `jk._proxy_pi_control_request` Phase 8 wrapper → private Pi bridge; protecting only inference calls leaves this consequential path uncovered.

These traces are **read from source**, not yet validated by a live same-process end-to-end probe. Actual release correctness must be demonstrated before they become authoritative P0 acceptance evidence.

## 5. Phase 9A reuse and required measurement qualification

The October 14 Phase 9A checkpoint documented 91 selected slots / 103 callable descriptors / 90 proposed delegate records, three bounded v1 stability observations, and a demonstrated **false negative** for a constant-only `co_consts` replacement. The stronger experimental 9A.4 candidate added constants/nested code/defaults/closures/selected globals but returned **three unexplained differences** during normal HTTP activity; the original evidence ZIP was unavailable for independent classification.

**Do not:** import the entire experimental probe as a trusted guard; fingerprint every Python object or mutable global; assume a wrapper's `__wrapped__` metadata is an authoritative execution trace; use process-local HMAC as proof against unrestricted same-process modification.

**Required narrow schema:** explicit version; logical stable slot ID; owner/location category; expected callable/descriptor/receiver identity; bounded code-object shape covering `co_code`, `co_consts` and nested code, defaults, kwdefaults, and explicitly selected closure/delegate references; omission/unavailable markers; supported runtime/Python-version assumptions. Avoid ephemeral `id(bound_method)` and mutable request-local data.

**Lifecycle:** Qualify legitimate lazy FastAPI middleware initialization instead of categorizing a normal `None → middleware` transition as compromise. Either seal at a safe framework lifecycle point or narrowly recognize an explicit approved transition before external authority. No silent blanket exclusions.

## 6. Concurrency and containment before coding

1. **Authority states:** `INITIALIZING`, `ACTIVE`, `SUSPENDED_UNVERIFIED`, `INVALIDATED` are reasonable proposed states, but the first production slice must specify exact semantics and lock scope without overwriting Phase 8's state.
2. **Confirmed difference:** make the protected authority terminally unavailable until a legitimate fresh secure-child initialization; report `RUNTIME_INTEGRITY_COMPROMISED` without leaking code or addresses. Matching again later is not an automatic rebaseline.
3. **Measurement unavailable:** withhold *new affected authority*, but do not label it confirmed compromise. Define whether/when accurate re-verification can restore it.
4. **Before action and before release:** design actual protected admission points. A periodic observer alone does not stop a bypass; a pre-request check alone does not protect a long stream or async dispatch.
5. **TOCTOU:** explicitly document and test concurrency between verification and use. A lock that only protects the verifier's own baseline cannot block arbitrary hostile Python mutation outside that lock; do not overclaim complete atomicity.
6. **Anti-brittleness:** preserve previously released safe SSE prefix, completed internal cognition, already-admitted external worker settlement, independent runtime lanes, and safe status/forensics as allowed. Never convert an observer/ledger write failure into an integrity compromise.
7. **Trust anchor:** no pure Python process-local fingerprint can establish independence against an attacker who can mutate the checker or its call sites. Declare the narrower capability threat model; isolated/hardware-root verification is separate future architecture.

## 7. Adversarial test plan — acceptance is consequence-based

**Negative tests (real secured serving child, with some isolated unit primitives):**

- Replace the effective `KERNEL.run` and `KERNEL.stream` slots; demonstrate protected release cannot be silently bypassed.
- Rebind `jk._phase4_partition_structured_tool_calls`, `_phase4_executor_admission_decision`, and the effective Phase 5 path authorizer; attempt a concrete previously blocked tool/path action.
- Mutate `function.__code__` including constant-only variants and closure/default delegates; close the known 9A v1 miss.
- Replace selected FastAPI route `endpoint`, `dependant.call`, or `app`; prove the protection applies to actual stored dispatch. Attempt relevant protected module reload.
- Alter Phase 8 verifier/measurement functions; demonstrate bounded failure where achievable, and clearly label any same-process control that can defeat the checker as outside the threat guarantee.
- Attempt tampering **during** an SSE stream or authenticated Agentic/Coder tool continuation. Verify no subsequent unauthorized release even though earlier safe output stays visible.
- Simulate unavailable measurement and forensic ledger failure. The first withholds new affected authority without falsely accusing tampering; the second does not restore or change the security outcome.

**Positive controls:** normal first HTTP request; unchanged code after warm middleware startup; ordinary status/log requests; streaming and nonstream backend failures; legitimate multi-stage Agentic, Coder Flash/Thorough, Deep Reasoning/Ultra; current Phase 4 Windows capability-aware inspection vs mutation rules; valid Phase 7 credentials; prior accepted tool resumes; pre-admitted worker settlements; unrelated independent runtime lanes.

**Required proof levels:** unit signature tests → secured startup and serving-child binding tests → actual end-to-end prevented consequence → negative/positive concurrency tests → full Windows/Pi regression gates → exact diff review. Tests run against the real frozen candidate SHA, not a different earlier tree.

## 8. First bounded implementation after this report (not yet authorized)

**Deliverables:** `jack_runtime_code_guard.py` (small versioned executable-binding primitive) + `tests/test_phase9_runtime_code_guard.py` (deterministic positive/negative controls), initially no public activation until the narrowly qualified P0 manifest proves stable. Review the exact code, compile, execute new targeted tests, execute relevant existing security tests, and inspect diff; stop. A separate follow-on increment installs the guard in the secure entrypoint and proves real boundary enforcement.

**Initial verification commands on a fresh Windows clone:**

```powershell
git switch security/phase9b-runtime-code-integrity-20261125
git status --short
py -3.14 -m py_compile jack_kernel.py jack_secure_entrypoint.py jack_source_drift_guard.py
py -3.14 -m pytest -q tests/test_phase8_source_baseline.py tests/test_phase8_runtime_enforcement.py tests/test_phase8_adversarial_preservation.py
py -3.14 -m pytest -q tests/test_agentic_coder_planner_executor.py
```

**Stop condition:** no source mutation or enforcement has been delivered by this Phase 9B-A report; recorded G0 red remains explicit. Do not merge or tag Phase 9 based on documentation, isolated tests, or the existence of the experimental branch.

## 9. Evidence links

- [Current security status](../../CURRENT_SECURITY_STATUS.md)
- [Phase 9A research close-out](SECURITY_LAYER_PHASE9A_RESEARCH_CHECKPOINT_2026-10-14.md)
- [Phase 8 validated closure](SECURITY_LAYER_PHASE8_VALIDATED_2026-10-06.md)
- [Governing security architecture](../../Documentation/Security/Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md)
- [Main CI run 45458603830](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/45458603830)
- [Open regression reconciliation PR #169](https://github.com/mlangford75-lgtm/Jack-Kernel/pull/169)

**Phase 9B-A closure assessment:** Current source and CI have been mapped to a defensible *candidate* P0 security scope; all P0 binding identity and real serving-child behavior remain implementation/validation tasks. The current experimental branch is not a completed security phase.
