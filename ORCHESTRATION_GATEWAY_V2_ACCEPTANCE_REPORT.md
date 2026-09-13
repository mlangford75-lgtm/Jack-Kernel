# Jack Kernel v0.1.1 â€” Orchestration Gateway v2 Acceptance Report

**Status:** ACCEPTED
**Acceptance completed:** 2026-09-12
**Kernel version:** Jack Kernel v0.1.1
**Subsystem:** Orchestration Gateway v2

## Scope

This report records the live acceptance of the Jack-mediated supervisor-to-worker transport. It does not rename Jack Kernel to v2 and it does not claim that Jack currently intercepts every privileged filesystem, shell, or process action executed inside Primary Pi.

Accepted supervisory topology:

```text
Jack Orchestrator
    â”‚
    â”œâ”€â”€ cognition â”€â”€â”€â”€â”€â”€â”€> Jack Kernel :8001/v1 â”€â”€â”€â”€â”€â”€â”€> backend/model
    â”‚
    â””â”€â”€ supervision â”€â”€â”€â”€â”€> Jack Kernel :8001/jack/orchestration
                                â”‚
                                â–¼
                       private Pi bridge :8013
                                â”‚
                                â–¼
                       privileged Primary Pi
```

Jack Orchestrator is cognition-capable but execution-restricted. Its model-facing tool surface is exactly five supervisory tools: `worker_status`, `watch_worker`, `submit_worker_task`, `cancel_worker_task`, and `new_worker_session`. It has no direct filesystem/shell/process tools, no direct backend endpoint, no private `:8013` access, and no Pi `controlToken` access.

## Accepted component identity

Final accepted Primary-Pi bridge:

```text
Pi/pi-control-bridge.ts
SHA-256 D066FA2F9B8A3735A60F57F028087F314F484B28DBD10640FB3D64A4FA29C664
```

Pre-fix run-bound donor bridge:

```text
SHA-256 FB7DB0AFE4587C395653B8DB88BE3525E25AD8D3DC53E53BBEABAB7508582957
```

The final change is a narrow correctness repair: on `agent_settled`, the bridge captures the settled run identity, clears `controlRun` and `activeRun`, and only then emits the terminal task snapshot. This makes `settledAt` consistent with `runOpen:false`.

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

A short controlled worker task completed with stable task/run identity and epoch 1. The event stream demonstrated the intended lifecycle:

```text
queued task_state
    -> running task_state with run_id
    -> run-bound user/message/tool observations
    -> settling task_state
    -> terminal task_state at agent_settled
```

A deliberately post-`agent_end` event was not permitted to inherit the current task/run merely because the higher-level controlled task had not yet settled. The bridge's Node regression harness also covers this rule.

## Physical concurrency acceptance

### Direct Jack concurrency

Jack was started through its launcher with the saved setting:

```text
Maximum concurrent Kernel requests = 2
```

Two simultaneous non-streaming `/v1/chat/completions` requests were sent directly through Jack. LM Studio showed both requests active at the same time on separate slots for a sustained interval. This proved that the running Jack process admitted at least two concurrent inference requests and that the backend physically processed them simultaneously.

A prior failed concurrency probe was traced to configuration precedence: `start.bat` launches the interactive Jack configuration process, which then writes the saved `max_concurrent_requests` value into the child server environment. Setting `JACK_MAX_CONCURRENT=2` only in the parent shell was therefore insufficient while the launcher configuration still held `1`.

### Full topology concurrency

A controlled Primary Pi worker task and Jack Orchestrator cognition were then run together through the same Jack Kernel. LM Studio showed the Primary Pi request active on one slot while multiple Jack Orchestrator continuations executed on the second slot before the worker released. This was physical backend overlap, not merely an application-level `running` status.

## Replay acceptance

Normal replay test:

```text
last sequence observed before disconnect: 42
reconnect request: /jack/orchestration/events?after=42
replayed sequence IDs: 43 through 90
```

Observed:

- replay events received;
- sequence strictly monotonic;
- every replayed ID greater than the disconnect point;
- no duplicate replay IDs;
- the task created while disconnected appeared in the replay;
- `source="pi"` preserved;
- `source_event` preserved.

Replay-gap test deliberately requested a position that had fallen outside the retained buffer:

```json
{
  "detail": {
    "error": "orchestration_replay_gap",
    "requested_after": 1,
    "oldest_available_seq": 123,
    "latest_seq": 634
  }
}
```

The server returned HTTP `409`. The retained range `123..634` is exactly 512 events inclusive, confirming the configured default replay window.

## Cancellation acceptance

### Discovery of the terminal-snapshot defect

The first live cancellation run correctly demonstrated the semantic distinction between logical cancellation and physical settlement:

- cancellation response: `status=cancelled`, `runOpen=true`;
- underlying model response aborted;
- status shortly afterward: same run, `runOpen=false`, `settledAt` populated.

However, raw SSE showed that the terminal task event still carried `runOpen:true` even though `settledAt` had been set. This was a representation-ordering defect: the bridge emitted the terminal snapshot before clearing `controlRun`.

### Narrow repair

The bridge was patched so `controlRun` and `activeRun` are cleared before terminal task emission. No new policy or state was added.

### Closure retest

Retest identity:

```text
task_id: d2d83d9b-cd66-41d5-9b1a-965d9bc3a06a
run_id:  a6895974-d482-4ee3-9bd5-285169b85d84
run_epoch: 1
```

Cancellation task event:

```text
seq:      1207
status:   cancelled
runOpen:  true
source_at: 2026-09-12T22:58:48.630Z
```

Terminal settlement task event:

```text
seq:       1210
status:    cancelled
runOpen:   false
settledAt: 2026-09-12T22:58:48.666Z
same run_id / run_epoch
```

The race probes did not produce any controlled task lifecycle before the original run's settlement boundary. Normal controlled work was accepted again after settlement. Cancellation is therefore accepted with the intended invariant:

> terminal task state and physical run settlement are distinct facts, and a new controlled task may not overlap an unsettled prior control run.

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

No fake queued/running/completed worker task was fabricated. No direct bridge or backend fallback was used.

## Local regression validation after the final bridge repair

```text
PASS  python -m py_compile jack_kernel.py
PASS  node tests/pi_control_bridge_v2_harness.mjs
PASS  pytest -q tests/test_orchestration_gateway_v2.py   (4 passed)
PASS  python tests/test_backend_retry.py
PASS  python tests/test_debugging_modes.py
PASS  python tests/test_resilience.py
PASS  python tests/test_release_profiles.py
```

The Node bridge harness now explicitly checks that terminal completed and terminal cancelled task events containing `settledAt` expose `runOpen:false`.

## Final verdict

**Orchestration Gateway v2 is accepted.**

The accepted boundary is specific and testable:

> Jack Orchestrator cannot execute privileged host consequences itself. Its consequential influence over the privileged Primary Pi worker crosses the Jack-mediated supervisory boundary. Gateway v2 provides run-bound identity, replayable observation, explicit cancellation/settlement semantics, concurrent inference support through Jack's existing semaphore configuration, and deterministic failure when the worker control bridge is unavailable.

This does not imply that Jack already intercepts every privileged action inside Primary Pi. That is a separate future chassis/tool-dispatch enforcement boundary.
