# Getting Started with Jack Kernel v0.1.1

Jack Kernel is a host-authoritative inference mediation/control layer between an application or agent and an OpenAI-compatible model backend.

Default inference topology:

`agent -> Jack Kernel :8001/v1 -> backend`

With the accepted Orchestration Gateway v2 enabled, Jack can also mediate a supervisory control plane:

`Jack Orchestrator -> Jack :8001/jack/orchestration -> private Primary-Pi bridge :8013 -> Primary Pi`

Jack Kernel remains **v0.1.1**. **Orchestration Gateway v2** is the accepted orchestration subsystem/protocol revision.

> **Read first:** `00_Jack_Kernel_Plain_English_Master_Guide_v0.1.1.docx`

## 1. Requirements

- Windows 10/11
- Python 3
- A supported OpenAI-compatible backend with a model loaded

Install dependencies from the repository root:

```powershell
py -3 -m pip install -r requirements.txt
```

## 2. Start Jack

```powershell
.\start.bat
```

Default agent-facing endpoint:

`http://127.0.0.1:8001/v1`

Virtual model ID:

`jack-kernel`

Health check:

`http://127.0.0.1:8001/health`

Port 8000 is intentionally available for a custom OpenAI-compatible/vLLM backend. Do not globally replace backend port 8000 with Jack's listener port 8001.

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

Stop Primary Pi, then install the accepted run-bound control bridge:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Pi\install-pi-control-bridge-v2.ps1"
```

Restart Primary Pi afterward. The installer backs up the previously installed bridge and preserves Pi's Jack configuration.

Accepted bridge SHA-256:

`D066FA2F9B8A3735A60F57F028087F314F484B28DBD10640FB3D64A4FA29C664`

The bridge creates separate task/run identities, strips its private correlation marker before model-visible prompt processing, binds ownership only from positive run evidence, clears low-level ownership at `agent_end`, and physically closes the control run at `agent_settled`. Terminal task snapshots are emitted only after control-run authority has been cleared, so a settled event reports `runOpen:false`.

## 6. Concurrent supervisor and worker inference

Jack's inference semaphore is configurable. Full-topology live acceptance proved Jack Orchestrator and Primary Pi can perform backend inference simultaneously when the saved launcher configuration allows two concurrent requests.

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

The private Primary-Pi bridge remains at `127.0.0.1:8013` and is authenticated separately. Supervisory clients should not bypass Jack or read the bridge control token.

## 8. Accepted replay, cancellation, and failure behavior

- Public SSE events receive monotonic process-local `seq` values.
- Default replay retention is 512 events.
- Reconnect with `Last-Event-ID` or `?after=<seq>`.
- A request older than the retained window returns HTTP `409` with `orchestration_replay_gap`.
- Cancellation is immediately visible but physical run settlement is separate.
- A new controlled task is not admitted while the cancelled control run is still unsettled.
- After settlement the terminal task snapshot reports `runOpen:false` and `settledAt`.
- If Primary Pi is unavailable while Jack remains alive, all Pi-dependent gateway operations return HTTP `502` with `{"detail":"Pi control bridge is unavailable"}`. There is no direct-Pi or backend-control fallback.

## 9. Regression checks

```powershell
py -3 -m py_compile jack_kernel.py
node tests\pi_control_bridge_v2_harness.mjs
py -3 -m pytest -q tests\test_orchestration_gateway_v2.py
py -3 tests\test_backend_retry.py
py -3 tests\test_debugging_modes.py
py -3 tests\test_resilience.py
py -3 tests\test_release_profiles.py
```

For architecture and operating guidance, read `00_Jack_Kernel_Plain_English_Master_Guide_v0.1.1.docx` first. For exact transport semantics see `ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md`. For live acceptance evidence see `ORCHESTRATION_GATEWAY_V2_ACCEPTANCE_REPORT.md`.
