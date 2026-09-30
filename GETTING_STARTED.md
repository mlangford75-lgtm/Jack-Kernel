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

For the current orchestration protocol and compatibility contract, read `Documentation/Orchestration/ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md`.

For supervisor operating behavior, including Codex Desktop as a reference cloud supervisor, read `Documentation/Orchestration/ORCHESTRATOR_INSTRUCTIONS.md`.

Historical acceptance evidence is preserved under `Documentation/Orchestration/Historical/` and is not the current runtime identity authority.

## 1. Requirements

- Windows 10/11
- Python 3
- A supported OpenAI-compatible backend with a model loaded

The current validated development/release baseline is **Python 3.14.6**. The Pi control-bridge validation harnesses use **Node.js 24.16.0**. Other Python 3 and Node versions may work, but they are not the pinned CI baseline.

Install runtime dependencies from the repository root:

```powershell
py -3 -m pip install -r requirements.txt
```

To reproduce the repository validation environment, install the separate test requirements:

```powershell
py -3 -m pip install -r requirements-test.txt
```

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
- **Deep Research** — X-High Thesis -> Medium Antithesis -> X-High authoritative Synthesis.
- **Agentic** — full native Stage-1 cognition followed by semantic Jack XML consolidation.
- **Code Debugging** — five-pass report-only forensic audit at Medium reasoning.
- **Code Debugging (Deep)** — the same forensic topology at X-High reasoning.

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

Jack's inference semaphore is configurable. Full-topology live acceptance proved that Jack Orchestrator and Primary Pi can perform backend inference simultaneously when the saved launcher configuration allows two concurrent requests.

Use Jack's launcher:

1. Open **Advanced** settings.
2. Set **Maximum concurrent Kernel requests** to `2`.
3. Save.
4. Start Jack.

The saved launcher configuration is authoritative for the child server process. Setting only a parent-shell `JACK_MAX_CONCURRENT` variable is not sufficient when the launcher configuration still says `1`.

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

## 9. Regression checks

Representative regression checks include:

```powershell
py -3 -m py_compile jack_kernel.py
node tests\pi_control_bridge_v2_harness.mjs
py -3 -m pytest -q tests\test_surgical_regressions.py
```

Additional project regression tests remain under `tests/`.

## 10. Multi-endpoint runtime lanes

The legacy single-lane `start.bat` path remains valid. For independent hot runtime lanes, use `start-lane.ps1` from the repository root.

Example:

```powershell
.\start-lane.ps1 -RuntimeId jack-agentic-01 -Mode agentic -Port 8101
.\start-lane.ps1 -RuntimeId jack-debug-01 -Mode code-debugging -Port 8102
.\start-lane.ps1 -RuntimeId jack-research-01 -Mode deep-research -Port 8103
```

Each lane is a separate Jack process. All three may point to the same LM Studio backend and loaded model. The local `JACK_MAX_CONCURRENT` semaphore limits only one Jack process; it is not a cross-process GPU scheduler.

If a preferred loopback port is occupied and fallback is enabled, Jack binds an OS-assigned free loopback port. Discover the actual addresses with:

```powershell
Invoke-RestMethod http://127.0.0.1:8101/jack/runtimes | ConvertTo-Json -Depth 8
```

A lane that needs a privileged Pi worker should be paired with its own named bridge. Start the worker in a separate PowerShell window with a unique bridge ID and explicit token:

```powershell
.\Pi\start-pi-worker.ps1 -BridgeId agentic-worker-01 -ControlPort 8013 -ControlToken "<lane-specific-secret>" -JackRuntimeId jack-agentic-01
```

Then launch the owning Jack lane with the same worker identity/token:

```powershell
.\start-lane.ps1 -RuntimeId jack-agentic-01 -Mode agentic -Port 8101 -WorkerBridgeId agentic-worker-01 -WorkerControlToken "<lane-specific-secret>"
```

Named workers publish their actual control endpoint after binding. If the preferred worker port is occupied, the bridge can fall back to an OS-assigned port without changing worker identity. Jack resolves the named worker from the local bridge registry and rejects bridge-identity mismatches. The worker's Pi provider separately resolves its owning Jack runtime by `JackRuntimeId` from Jack's runtime registry and verifies that runtime identity before registering the provider; this prevents a named worker from falling back to the legacy global Jack endpoint for inference.

Do not treat an available lane count as an inference-slot count. Before declaring a shared backend qualified for many concurrent lanes, verify its backend-side admission/queueing behavior under N>K load.

### Multi-endpoint governance clarification

The setup examples above remain valid, but their port numbers are preferences/transport locations rather than permanent identities. A runtime or worker that moves to a validated fallback endpoint retains the same logical identity and ownership.

Runtime manifests are discovery evidence. A named Pi provider resolves the expected owning `runtime_id`, reaches the candidate endpoint, and verifies live `/health.runtime_id` before provider registration. A stale manifest status must not veto a positively verified live runtime, while a live identity mismatch remains a hard identity failure.

Authenticated process-local activity is available at `GET /jack/runtime/status`. That surface is best-effort observability, not cognition, stage, cancellation, or commit authority. If activity telemetry becomes unreliable, Jack reports degraded/unknown state rather than inventing a known state.

A disconnected HTTP client likewise does not, by itself, authorize cancellation of valid cognition. Explicit authorized cancellation remains separate.

The earlier statement that two configured Jack requests may infer concurrently is retained as historical setup guidance. Normatively, the acceptance evidence proves request-level coexistence through shared infrastructure; it does not by itself prove physically simultaneous GPU generation when the backend provides fewer physical generation slots.

## 11. Documentation authority

Active orchestration documentation is intentionally small:

- `Documentation/Orchestration/ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md` — canonical protocol, lifecycle, authority, and supervisor compatibility contract.
- `Documentation/Orchestration/ORCHESTRATOR_INSTRUCTIONS.md` — canonical operating instructions for supervisory agents, including the Codex cloud-supervisor quickstart.
- `Documentation/Orchestration/Historical/` — dated acceptance evidence and historical records; not current runtime identity authority.

Current Primary-Pi bridge identity is also published in `Pi/README.md`.

## Validated security layer (Phases 0–3)

The current security-hardening checkpoint adds deterministic host-side protection without changing Jack's core installation model.

The implemented boundary includes deterministic security outcomes, bounded StreamingIRQ pre-release quarantine, malformed-SSE release protection, and exact-match Canary enforcement. It follows the rule:

> Fail closed on authority. Fail soft on recoverable cognition.

Static Canary policy is optional and is transported at startup through `JACK_CANARY_POLICY_JSON`. An absent or blank policy preserves the empty-policy behavior. Static startup policy currently accepts Tier A and Tier B patterns only; live Tier C mutation remains deferred.

Example PowerShell startup value:

```powershell
$env:JACK_CANARY_POLICY_JSON='{"version":1,"patterns":[{"id":"operator.marker","tier":"B","value":"LONG_SECRET_MARKER"}]}'
```

Current static-policy constraints include schema version 1, a maximum of 128 patterns, a maximum deterministic look-behind window of 256 characters, and a minimum static Canary value length of 8 characters. Explicit malformed policy is a configuration error rather than something the runtime silently weakens.

A malformed non-DONE SSE `data:` frame is not passed through raw. Jack withholds that frame and raises `StreamingIRQProtocolError`. This is an ordinary protocol failure, not `HARD_INTERRUPT`; previously proven-safe held cognition is preserved.

For the exact validated checkpoint and current scope boundaries, read:

- `docs/security/SECURITY_LAYER_PHASE0_3_VALIDATED_2026-09-27.md`
- `Documentation/Security/GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASES_0_3_2026-09-27.md`

Jack still does not claim a universal filesystem sandbox or complete consequence-control system. **Restricted Paths + Workspace Lock begins in Phase 4 and is not part of the Phase 0–3 checkpoint.**

<!-- PHASE4_GETTING_STARTED_STATUS_2026-09-30 -->

## Current Phase-4 security checkpoint

Phase 4 — **Restricted Paths + Workspace Lock** — is now validated.

Implementation freeze: `0e897b801d5b5da8d604cf21556b40da769c26fe`.

Checkpoint release: `security-layer-phase4-validated-2026-09-30` at merge commit `0c15331d4673412befc626b64d7c4e52f7018fb4`.

Validation:

- **201/201** targeted Phase-4 tests;
- **376/376** full Python tests;
- **7/7** Pi harnesses;
- clean `git diff --check`.

Current references:

- `docs/security/SECURITY_LAYER_PHASE4_VALIDATED_2026-09-30.md`
- `Documentation/Security/GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_4_2026-09-30.md`
- `Documentation/Security/Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md`

The older Phase 0-3 section remains historical checkpoint documentation. Its statement that Restricted Paths and Workspace Lock were future work is no longer the current implementation state.

### Configure Phase 4 path policy

Phase 4 path policy is supplied at startup through `JACK_PATH_POLICY_JSON`. Jack snapshots that configuration into immutable runtime/lane policy. Model output, caller content, tool results, retries, and later environment changes do not redefine the active policy.

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
- User-supplied `never_paths` are cumulative with Jack's host-derived default NEVER roots. They do not replace or weaken those defaults.
- `workspace_root: null` disables Workspace Lock. It does not disable NEVER protection.
- If `JACK_PATH_POLICY_JSON` is absent or blank, Jack creates no Workspace Lock and adds no user NEVER paths; host-derived default NEVER roots still remain active.
- Explicit malformed JSON, unsupported schema versions, missing or extra keys, and invalid field types are startup configuration errors rather than conditions Jack silently weakens.

PowerShell example with Workspace Lock enabled:

```powershell
$env:JACK_PATH_POLICY_JSON='{"version":1,"workspace_root":"D:\\Projects\\Jack","never_paths":["D:\\Sensitive"]}'
.\start.bat
```

PowerShell example with no Workspace Lock and one additional NEVER path:

```powershell
$env:JACK_PATH_POLICY_JSON='{"version":1,"workspace_root":null,"never_paths":["D:\\Sensitive"]}'
.\start.bat
```

Set the environment value before starting the Jack runtime or lane. To change the active path policy, restart that runtime with the new startup configuration.

Phase 4 authorizes represented filesystem targets Jack can deterministically observe. It does not claim final-object or descriptor-level confinement across symlinks, junctions, reparse points, mounts, or hard-link relationships.

Jack still does not claim universal filesystem-object attestation.
