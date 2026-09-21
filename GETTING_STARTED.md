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

Install dependencies from the repository root:

```powershell
py -3 -m pip install -r requirements.txt
```

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
Windows CRLF representation SHA-256: E758883F3C18CBEFBF5590C720DBEDF7AB8E85D3314B5EA77E277B1A8C3BD3E4
Canonical repository LF SHA-256:    723338D4F67295AEC5B75886EFEF7843C1A44D01934BF9CBB7C2304B4603F92C
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

## 10. Documentation authority

Active orchestration documentation is intentionally small:

- `Documentation/Orchestration/ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md` — canonical protocol, lifecycle, authority, and supervisor compatibility contract.
- `Documentation/Orchestration/ORCHESTRATOR_INSTRUCTIONS.md` — canonical operating instructions for supervisory agents, including the Codex cloud-supervisor quickstart.
- `Documentation/Orchestration/Historical/` — dated acceptance evidence and historical records; not current runtime identity authority.

Current Primary-Pi bridge identity is also published in `Pi/README.md`.