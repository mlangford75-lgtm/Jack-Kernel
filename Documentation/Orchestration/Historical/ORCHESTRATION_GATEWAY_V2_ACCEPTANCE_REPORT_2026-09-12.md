# Jack Kernel v0.1.1 — Orchestration Gateway v2 Acceptance Report

**Historical acceptance record**  
**Acceptance completed:** 2026-09-12  
**Kernel version:** Jack Kernel v0.1.1  
**Subsystem:** Orchestration Gateway v2  
**Status at time of test:** ACCEPTED

> This file preserves the September 12, 2026 live acceptance evidence. It is historical, not the current runtime identity authority. The bridge accepted in this test was `D066FA2F9B8A3735A60F57F028087F314F484B28DBD10640FB3D64A4FA29C664`. The current repository bridge identity is published in `Pi/README.md` and the current normative orchestration contract is `../ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md`.

## Scope

This acceptance tested the Jack-mediated supervisor-to-worker transport. It did not rename Jack Kernel to v2 and did not claim that Jack intercepted every privileged filesystem, shell, or process action executed inside Primary Pi.

Accepted test topology:

```text
Jack Orchestrator
  -> cognition -> Jack Kernel :8001/v1 -> backend/model
  -> supervision -> Jack Kernel :8001/jack/orchestration
                    -> private Pi bridge :8013
                    -> privileged Primary Pi
```

The tested Jack Orchestrator was cognition-capable but execution-restricted. Its model-facing tool surface was exactly five supervisory tools: `worker_status`, `watch_worker`, `submit_worker_task`, `cancel_worker_task`, and `new_worker_session`. It had no direct filesystem/shell/process tools, no direct backend endpoint, no direct private `:8013` access, and no Pi `controlToken` access.

## Accepted component identity at time of test

```text
Pi/pi-control-bridge.ts
SHA-256 D066FA2F9B8A3735A60F57F028087F314F484B28DBD10640FB3D64A4FA29C664
```

Pre-fix run-bound donor bridge:

```text
SHA-256 FB7DB0AFE4587C395653B8DB88BE3525E25AD8D3DC53E53BBEABAB7508582957
```

The final tested correctness repair captured settled run identity, cleared `controlRun` and `activeRun`, and only then emitted the terminal task snapshot so `settledAt` was consistent with `runOpen:false`.

## Acceptance matrix

| Boundary | Result |
| --- | --- |
| Jack Orchestrator isolation / no direct backend or private bridge | PASS |
| Dynamic context projection through Jack | PASS |
| Exactly five model-facing supervisory tools | PASS |
| `instruction` -> Pi wire `prompt` adapter | PASS |
| Gateway task dispatch | PASS |
| Run-bound task ID / run ID / epoch attribution | PASS |
| `pi_run_bound` event ownership | PASS |
| Post-`agent_end` unowned-event behavior | PASS |
| `agent_settled` physical settlement boundary | PASS |
| Direct Jack physical inference concurrency | PASS |
| Full Jack Orchestrator + Primary Pi physical inference concurrency | PASS |
| Normal SSE replay after disconnect | PASS |
| Strict monotonic replay sequence | PASS |
| No replay duplicates | PASS |
| Pi source/source-event preservation | PASS |
| 512-event replay window | PASS |
| HTTP 409 `orchestration_replay_gap` | PASS |
| Logical cancellation vs physical settlement | PASS |
| Unsettled-run admission guard | PASS |
| Terminal settlement event `runOpen:false` | PASS |
| Post-cancellation recovery | PASS |
| Primary-Pi-unavailable deterministic failure | PASS |
| No fabricated worker success / no fallback | PASS |

## Run-bound acceptance

A short controlled worker task completed with stable task/run identity and epoch 1:

```text
queued task_state
  -> running task_state with run_id
  -> run-bound user/message/tool observations
  -> settling task_state
  -> terminal task_state at agent_settled
```

A deliberately post-`agent_end` event did not inherit current task/run ownership merely because the higher-level controlled task had not settled.

## Physical concurrency acceptance

Jack was started with:

```text
Maximum concurrent Kernel requests = 2
```

Two simultaneous non-streaming `/v1/chat/completions` requests were observed physically active on separate LM Studio slots.

A controlled Primary Pi worker task and Jack Orchestrator cognition were then run together through the same Jack Kernel. LM Studio showed worker inference on one slot while Jack Orchestrator continuations executed on another before the worker released. This was physical backend overlap rather than only application-level `running` state.

A prior failed concurrency probe was traced to launcher configuration precedence: the saved launcher value governed the child server process, so setting only a parent-shell `JACK_MAX_CONCURRENT=2` was insufficient while the saved launcher configuration remained `1`.

## Replay acceptance

Normal replay test:

```text
last sequence before disconnect: 42
reconnect: /jack/orchestration/events?after=42
replayed sequence IDs: 43 through 90
```

Observed:

- replay events were received;
- sequence IDs were strictly monotonic;
- every replayed ID was greater than the disconnect point;
- no duplicate replay IDs were observed;
- the task created while disconnected appeared in replay;
- `source="pi"` was preserved;
- `source_event` was preserved.

Replay-gap test deliberately requested a position outside the retained buffer. Jack returned HTTP `409` with `orchestration_replay_gap`. The retained range `123..634` was exactly 512 events inclusive.

## Cancellation acceptance

The first live cancellation run demonstrated the distinction between logical cancellation and physical settlement:

- cancellation response: `status=cancelled`, `runOpen=true`;
- underlying model response aborted;
- later status: same run, `runOpen=false`, `settledAt` populated.

Raw SSE then exposed a representation-ordering defect: the terminal task event still carried `runOpen:true` even though `settledAt` had been set.

The bridge was narrowly repaired so `controlRun` and `activeRun` were cleared before terminal task emission.

Closure retest identity:

```text
task_id: d2d83d9b-cd66-41d5-9b1a-965d9bc3a06a
run_id:  a6895974-d482-4ee3-9bd5-285169b85d84
run_epoch: 1
```

Cancellation event:

```text
seq:       1207
status:    cancelled
runOpen:   true
source_at: 2026-09-12T22:58:48.630Z
```

Terminal settlement event:

```text
seq:       1210
status:    cancelled
runOpen:   false
settledAt: 2026-09-12T22:58:48.666Z
same run_id / run_epoch
```

No new controlled task lifecycle was admitted before the original run's settlement boundary. Normal controlled work was accepted again after settlement.

## Primary Pi unavailable acceptance

Primary Pi was stopped while Jack and the backend remained running.

Observed:

```text
Jack /v1 alive:                    true
private Pi bridge :8013 reachable: false
```

Jack orchestration results:

```text
GET  /jack/orchestration/status       -> 502
POST /jack/orchestration/tasks        -> 502
POST /jack/orchestration/tasks/cancel -> 502
POST /jack/orchestration/session/new  -> 502
```

Each returned:

```json
{"detail":"Pi control bridge is unavailable"}
```

No fake worker task was fabricated and no direct bridge/backend fallback was used.

## Local regression validation at acceptance time

```text
PASS  python -m py_compile jack_kernel.py
PASS  node tests/pi_control_bridge_v2_harness.mjs
PASS  pytest -q tests/test_orchestration_gateway_v2.py   (4 passed)
PASS  python tests/test_backend_retry.py
PASS  python tests/test_debugging_modes.py
PASS  python tests/test_resilience.py
PASS  python tests/test_release_profiles.py
```

The Node bridge harness checked that terminal completed/cancelled task events containing `settledAt` exposed `runOpen:false`.

## Historical verdict

**Orchestration Gateway v2 was accepted on September 12, 2026 against bridge `D066FA2F...`.**

The accepted boundary was specific:

> Jack Orchestrator could not execute privileged host consequences itself. Its consequential influence over the privileged Primary Pi worker crossed the Jack-mediated supervisory boundary. Gateway v2 supplied run-bound identity, replayable observation, explicit cancellation/settlement semantics, concurrent inference support through Jack's semaphore configuration, and deterministic failure when the worker bridge was unavailable.

This historical acceptance did not claim that Jack intercepted every privileged action inside Primary Pi. Later validated bridge revisions superseded the tested bridge identity; they do not rewrite which artifact this acceptance run actually tested.