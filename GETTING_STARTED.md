# Getting Started with Jack Kernel v0.1.1

Jack Kernel is a host-authoritative inference mediation/control layer between an application or agent and an OpenAI-compatible model backend.

Default inference topology:

```text
agent -> Jack Kernel :8001/v1 -> backend
```

With Orchestration Gateway v2 enabled, Jack can also mediate a supervisory control plane:

```text
Supervisor -> Jack :8001/jack/orchestration -> private worker bridge -> worker
```

Primary Pi remains the reference local worker. Jack Kernel remains **v0.1.1**; **Orchestration Gateway v2** is the orchestration subsystem/protocol revision.

> **Read first:** `00_Jack_Kernel_Plain_English_Master_Guide_v0.1.1.docx`
>
> **Current security truth:** `CURRENT_SECURITY_STATUS.md`

For the current orchestration protocol and compatibility contract, read `Documentation/Orchestration/ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md`.

For supervisor operating behavior, including Codex Desktop as a reference cloud supervisor, read `Documentation/Orchestration/ORCHESTRATOR_INSTRUCTIONS.md`.

Historical acceptance/build evidence is preserved under `Documentation/Orchestration/Historical/` and `Documentation/Historical-Build-Record/`. Historical material is not current runtime identity or security authority merely because it remains available.

## 1. Requirements

- Windows 10/11
- Python 3
- A supported OpenAI-compatible backend with a model loaded

The current validated development/release baseline is **Python 3.14.6**. The Pi control-bridge validation harnesses use **Node.js 24.16.0**. Other Python 3 and Node versions may work, but they are not the pinned CI baseline.

From the repository root on Windows, run the one-command setup **before launching Jack**:

```powershell
.\setup.bat
```

This creates a repository-local `.venv` and installs the pinned runtime dependencies into that interpreter, without depending on the user's global or roaming-site Python packages. Both `start.bat` and `start-lane.ps1` already prefer this `.venv` when it exists.

To install the regression-test dependencies and run tests on a fresh clone:

```powershell
.\setup.bat --test
& ".\.venv\Scripts\python.exe" -m pytest -q tests
```

Use the `.venv` interpreter for tests: some security tests launch subprocesses with isolated `USERPROFILE` and `APPDATA` paths; globally or per-user installed packages might not be visible in those subprocesses. If setup fails, fix the reported Python or pip problem rather than launching with a different interpreter. Setup is explicit and does not start a server or change any cognition or security policies.

The runtime requirements pin the validated FastAPI, Uvicorn, and HTTPX versions. `constraints.txt` also pins the FastAPI-facing Starlette and Pydantic versions from the accepted Windows baseline.

## 2. Start Jack

```powershell
.\start.bat
```

Default agent-facing endpoint:

```text
http://127.0.0.1:8001/v1
```

Virtual model ID:

```text
jack-kernel
```

Health check:

```text
http://127.0.0.1:8001/health
```

Port 8000 remains available for a custom OpenAI-compatible/vLLM backend. Do not globally replace backend port 8000 with Jack's listener port 8001.

## 3. Choose a cognition program

- **Off** — native thinking disabled.
- **Medium** — direct native Medium reasoning.
- **X-High** — direct native X-High reasoning.
- **Deep Reasoning** — Thesis → Antithesis → Synthesis.
- **Local Agentic (Preserve Thinking)** — the current locally tested implementation of Agentic (Preserve Thinking), replacing the earlier Agentic implementation ([PR #57](https://github.com/mlangford75-lgtm/Jack-Kernel/pull/57)), selected with `JACK_REASONING_LEVEL="Local Agentic (Preserve Thinking)"` (the prior `agentic` spelling is an accepted compatibility alias). Stage 1 has native reasoning and authorized tools and freezes A1; tools-off Stage 2 generates retrospective memory; Jack keeps authenticated U/M/A history, one-hop previous-stage reasoning when supported, tool-result receipts, and completed-turn pruning. See the [current technical reference](Documentation/Agentic/AGENTIC_PRESERVE_THINKING_2026-10-21.md); the [October 15 precursor](Documentation/Agentic/AGENTIC_RETROSPECTIVE_MEMORY_RELEASE_2026-10-15.md) is historical, not the current release.
- **Code Debugging** — five-pass report-only forensic audit at Medium reasoning.
- **Code Debugging (Deep)** — the same forensic topology at X-High reasoning.

The cognition programs are examples built on Jack Kernel. They are not the Kernel itself.

## 4. Optional Pi provider/context synchronization

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Pi\install-jack-kernel-extension.ps1"
```

Restart Pi or reload its extensions. The provider extension obtains the effective context window from Jack rather than relying on a stale Pi-side static guess.

## 5. Optional Orchestration Gateway v2 worker bridge

Stop Primary Pi, then install the current validated run-bound control bridge:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Pi\install-pi-control-bridge-v2.ps1"
```

Restart Primary Pi afterward. The installer backs up the previously installed bridge and preserves Pi's Jack configuration.

Current validated bridge identities:

```text
Windows CRLF representation SHA-256: 93A6843CDAAEDA637474B584919ED003930296DE281570E3DDC391F54EF65565
Canonical repository LF SHA-256:    8FFD33FD33AE15A785E2BF9015F17FC14F1DE27B09515D5E868EC163D54C15F0
```

The bridge creates separate task/run identities, strips its private correlation marker before model-visible prompt processing, binds ownership only from positive run evidence, clears low-level ownership at `agent_end`, and physically closes the control run at `agent_settled`.

Retry/continuation epochs retain one stable `run_id` while incrementing `run_epoch`. Historical assistant failure from an older epoch can remain diagnostic without poisoning a live retry epoch. Structured tool failures remain visible as diagnostics but do not automatically force the overall task to fail if the worker recovers successfully.

## 6. Concurrent supervisor and worker inference

Jack's inference semaphore is configurable.

Use Jack's launcher:

1. Open **Advanced** settings.
2. Set **Maximum concurrent Kernel requests** to `2`.
3. Save.
4. Start Jack.

The saved launcher configuration is authoritative for the child server process. Setting only a parent-shell `JACK_MAX_CONCURRENT` variable is not sufficient when the launcher configuration still says `1`.

Validated evidence establishes request-level coexistence through shared Jack/backend infrastructure. It does not by itself prove physically simultaneous GPU generation when the backend exposes fewer physical generation slots.

## 7. Public orchestration routes

```text
GET  /jack/orchestration/status
GET  /jack/orchestration/events
POST /jack/orchestration/tasks
POST /jack/orchestration/tasks/cancel
POST /jack/orchestration/session/new
```

Normal task body:

```json
{"prompt":"..."}
```

The private Primary-Pi bridge remains separately authenticated. Supervisory clients must not bypass Jack or use the bridge control token.

## 8. Replay, cancellation, recovery, and failure behavior

- Public SSE events receive monotonic process-local `seq` values.
- Default replay retention is 512 events.
- Reconnect with `Last-Event-ID` or `?after=<seq>`.
- A request older than the retained window returns HTTP `409` with `orchestration_replay_gap`.
- Cancellation and physical settlement are separate facts.
- A new controlled task is not admitted while the prior control run remains physically open.
- Terminal settlement reports `runOpen:false` with settlement metadata.
- A retry/continuation keeps the controlled `run_id` and advances `run_epoch`.
- Structured tool failures remain diagnostic and can be recovered from by later successful worker execution.
- If Primary Pi is unavailable while Jack remains alive, Pi-dependent gateway operations fail deterministically. There is no direct-Pi or backend-control fallback.
- A lost HTTP/SSE client transport connection is not implicit cognition-cancellation authority.

## 9. Regression checks

Representative checks include:

```powershell
py -3 -m py_compile jack_kernel.py
node tests\pi_control_bridge_v2_harness.mjs
py -3 -m pytest -q tests\test_surgical_regressions.py
```

Additional project regression tests remain under `tests/`.

Historical Phase-6 validation evidence (not the current full-suite baseline):

- Phase-5 targeted regression: **37/37 PASS**;
- Phase-6 targeted regression: **18/18 PASS**;
- complete Python regression suite: **431/431 PASS**;
- Pi harnesses: **7/7 PASS**;
- runtime compilation: **PASS**.

See `CURRENT_SECURITY_STATUS.md` for exact checkpoint identities. The post-PR #46 clean Windows baseline passed **527 Python tests**; that is a later regression result, not a new Phase 8 validation tag.

## 10. Multi-endpoint runtime lanes

The legacy single-lane `start.bat` path remains valid. For independent hot runtime lanes, use `start-lane.ps1` from the repository root.

Example:

```powershell
.\start-lane.ps1 -RuntimeId jack-agentic-01 -Mode "Local Agentic (Preserve Thinking)" -Port 8101
.\start-lane.ps1 -RuntimeId jack-debug-01 -Mode code-debugging -Port 8102
.\start-lane.ps1 -RuntimeId jack-research-01 -Mode deep-research -Port 8103
```

Each lane is a separate Jack process. All may point to the same backend and loaded model. The local `JACK_MAX_CONCURRENT` semaphore limits only one Jack process; it is not a cross-process GPU scheduler.

If a preferred loopback port is occupied and fallback is enabled, Jack binds an OS-assigned free loopback port. Discover runtime addresses with:

```powershell
Invoke-RestMethod http://127.0.0.1:8101/jack/runtimes | ConvertTo-Json -Depth 8
```

A lane that needs a privileged Pi worker should be paired with its own named bridge. Start the worker in a separate PowerShell window with a unique bridge ID and explicit token:

```powershell
.\Pi\start-pi-worker.ps1 -BridgeId agentic-worker-01 -ControlPort 8013 -ControlToken "<lane-specific-secret>" -JackRuntimeId jack-agentic-01
```

Then launch the owning Jack lane with the same worker identity/token:

```powershell
.\start-lane.ps1 -RuntimeId jack-agentic-01 -Mode "Local Agentic (Preserve Thinking)" -Port 8101 -WorkerBridgeId agentic-worker-01 -WorkerControlToken "<lane-specific-secret>"
```

Named workers publish their actual control endpoint after binding. Endpoint movement does not change worker identity. Jack resolves the named worker from the local bridge registry and rejects bridge-identity mismatches. The worker's Pi provider separately resolves its owning Jack runtime by `JackRuntimeId` and verifies live runtime identity before provider registration.

Do not treat available lane count as inference-slot count. Before declaring a shared backend qualified for many concurrent lanes, verify backend-side admission/queueing behavior under N>K load.

### Multi-endpoint governance clarification

- ports/sockets/URLs are transport locators, not runtime identity;
- runtime manifests provide discovery evidence;
- positive live `/health.runtime_id` verification establishes the identity actually reached;
- a stale manifest status must not veto positively verified live identity;
- live identity mismatch remains an identity failure;
- named privileged workers remain two-sided bindings: Jack lane -> named Pi worker/bridge and Pi provider -> owning Jack `runtime_id`;
- `JACK_MAX_CONCURRENT` remains process-local;
- authenticated `GET /jack/runtime/status` is best-effort observability, not cognition, stage, cancellation, or commit authority;
- degraded telemetry reports unknown rather than inventing state;
- client transport disconnect does not authorize cognition cancellation.

## 11. Current security configuration

The latest validated, frozen security checkpoint is **Phase 8**. The operational controls below describe earlier configuration cumulatively; later phases do not erase earlier configuration. Phase 9A produced experimental research only, with no loaded-code integrity enforcement. For current status see `CURRENT_SECURITY_STATUS.md`.

For exact current claims, checkpoint identities, validation results, and nonclaims, read:

`CURRENT_SECURITY_STATUS.md`

### 11.1 Canary protection — Phases 0–3

Static Canary policy is optional and is supplied at startup through `JACK_CANARY_POLICY_JSON`. An absent or blank policy preserves empty-policy behavior. Static startup policy accepts Tier A and Tier B patterns; live Tier C mutation remains deferred.

Example:

```powershell
$env:JACK_CANARY_POLICY_JSON='{"version":1,"patterns":[{"id":"operator.marker","tier":"B","value":"LONG_SECRET_MARKER"}]}'
```

Current static-policy constraints include schema version 1, a maximum of 128 patterns, a maximum deterministic look-behind window of 256 characters, and a minimum static Canary value length of 8 characters. Explicit malformed policy is a startup configuration error rather than something Jack silently weakens.

A malformed non-DONE SSE `data:` frame is withheld and raises `StreamingIRQProtocolError`. This is ordinary protocol failure, not `HARD_INTERRUPT`; previously proven-safe held cognition is preserved.

### 11.2 Restricted Paths + Workspace Lock — Phase 4

Path policy is supplied at startup through `JACK_PATH_POLICY_JSON`. Jack snapshots that configuration into immutable runtime/lane policy. Model output, caller content, tool results, retries, and later environment changes do not redefine the active policy.

The JSON object uses exactly these three keys:

```json
{
  "version": 1,
  "workspace_root": "D:\\Projects\\Jack",
  "never_paths": [
    "D:\\Sensitive"
  ]
}
```

- `version` must be integer `1`.
- `workspace_root` must be an absolute Windows path string or `null`.
- `never_paths` must be a list of path strings.
- user-supplied `never_paths` are cumulative with Jack's host-derived default NEVER roots;
- `workspace_root: null` disables Workspace Lock but does not disable NEVER protection;
- if `JACK_PATH_POLICY_JSON` is absent or blank, Jack creates no Workspace Lock and adds no user NEVER paths; host-derived defaults remain active;
- malformed JSON, unsupported schema versions, missing/extra keys, and invalid field types are startup errors.

Workspace Lock example:

```powershell
$env:JACK_PATH_POLICY_JSON='{"version":1,"workspace_root":"D:\\Projects\\Jack","never_paths":["D:\\Sensitive"]}'
.\start.bat
```

No Workspace Lock plus one additional NEVER path:

```powershell
$env:JACK_PATH_POLICY_JSON='{"version":1,"workspace_root":null,"never_paths":["D:\\Sensitive"]}'
.\start.bat
```

Set the environment value before starting the Jack runtime or lane. Restart the runtime to change active path policy.

Phase 4 authorizes represented filesystem targets Jack can deterministically observe. It does not claim final-object or descriptor-level confinement across symlinks, junctions, reparse points, mounts, or hard-link relationships.

### 11.3 Deterministic Consequence Gate — Phase 5

Phase 5 is automatic Kernel-owned runtime behavior. It does not require a separate user configuration variable.

The Gate consumes typed facts produced by the subsystems that actually own them and selects a deterministic `SecurityOutcome` plus containment scope. It does not infer arbitrary shell/filesystem semantics and does not turn observability into authority.

Its governing rule is minimum justified containment: deny or interrupt only the boundary required to preserve the violated invariant while preserving independently valid cognition and state.

### 11.4 Authority & Security Ledger — Phase 6

Phase 6 is also Kernel-owned runtime behavior. It adds a process-local Authority & Security Ledger for a deliberately closed set of established decisions/events:

- represented-path decisions;
- executor runtime/lane admission decisions;
- exact Canary matches;
- exact reserved-evidence-namespace blocks.

The ledger does not become the source of those facts. It does not record Pi lifecycle in Phase 6, does not promote persisted historical state into new process authority, and does not turn durable forensic projection into active authority.

For full Phase-6 semantics and validation evidence, read:

- `docs/security/SECURITY_LAYER_PHASE6_VALIDATED_2026-10-02.md`
- `Documentation/Security/GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_6_2026-10-02.md`

## 12. Documentation authority

Current user-facing documentation:

- `README.md` — project front door and architecture map.
- `GETTING_STARTED.md` — installation and operation.
- `CURRENT_SECURITY_STATUS.md` — current validated security state.
- `00_Jack_Kernel_Plain_English_Master_Guide_v0.1.1.docx` — full plain-English guide.

Active orchestration documentation:

- `Documentation/Orchestration/ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md` — canonical protocol, lifecycle, authority, and supervisor compatibility contract.
- `Documentation/Orchestration/ORCHESTRATOR_INSTRUCTIONS.md` — canonical supervisory-agent operating instructions.

Historical evidence:

- `Documentation/Historical-Build-Record/` — dated demonstrations, superseded root checkpoint summaries, and build evidence.
- `Documentation/Orchestration/Historical/` — orchestration acceptance history.
- `docs/security/` — detailed immutable security phase checkpoint records.

Historical statements remain preserved as evidence of what was true at their checkpoint. They must not be substituted for current-state documentation when determining present behavior.
