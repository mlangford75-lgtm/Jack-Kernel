# Orchestrate with a Cloud-Model Agent

## Purpose

This document explains how a cloud-model agent can supervise and operate a local worker—such as Primary Pi—through Jack Kernel without bypassing Jack’s deterministic control boundary.

Codex Desktop is the current reference example because it provides a convenient native cloud-model agent and local tool surface. **Codex is not the architectural requirement.** The same pattern can be used by any supervisory agent whose cognition remains on its own cloud model and that can call Jack Kernel’s public orchestration API.

For the Codex-specific operator procedure, see [`USING_CODEX_AS_JACK_ORCHESTRATION_AGENT.md`](USING_CODEX_AS_JACK_ORCHESTRATION_AGENT.md).

The important distinction is architectural:

- **The cloud-model agent is the supervisor.** Its cognition remains on its native cloud model/provider.
- **Pi, or another local agent, is the worker/build agent.**
- **Jack Kernel is the mandatory supervisor-to-worker mediation layer.**
- **The worker’s model inference runs through Jack Kernel to the configured local backend.**

The required topology is:

```text
User
  |
  v
Cloud-model supervisory agent
(native cloud cognition; Codex is one example)
  |
  | supervision / worker control only
  v
Jack Kernel :8001/jack/orchestration
  |
  v
private worker bridge
  |
  v
Primary Pi or another local worker
  |
  | model inference
  v
Jack Kernel :8001/v1
  |
  v
local LLM server / configured backend
```

There is **no supervisor-cognition path through Jack `/v1` in this architecture**. Jack does not replace the cloud agent’s model provider. The cloud agent keeps its native cloud cognition and uses Jack only as the deterministic boundary for control of the local worker.

This differs from the all-local Jack Orchestrator architecture, where both the local supervisor and the local worker may perform inference through Jack against the same local backend, including with multiple backend concurrency slots. That all-local design remains valid, but it is a different deployment mode.

---

## 1. What must change in an existing worker

A worker such as Pi does not need to become aware of Codex, OpenAI, or any other cloud-model supervisor. It needs a small deterministic control adapter that exposes the worker’s existing runtime capabilities in a form Jack can safely mediate.

The adapter should provide, at minimum:

1. **Status**
2. **Live events**
3. **Task submission**
4. **Cancellation**
5. **New-session control**
6. **Physical settlement state**
7. **Stable task/run correlation**
8. **Explicit readiness during runtime/session replacement**

The worker remains responsible for its own model execution. The adapter only exposes control and observation.

### Reference private control surface

A Pi-like bridge can expose:

```text
GET  /v1/status
GET  /v1/events
POST /v1/tasks
POST /v1/tasks/cancel
POST /v1/session/new
```

The bridge should bind only to localhost or another private interface trusted by Jack.

The cloud supervisor must not call these private endpoints directly.

---

## 2. What the cloud supervisor needs

A cloud-model supervisor needs only:

- its normal native cloud-model cognition;
- ordinary HTTP capability for Jack’s orchestration API;
- SSE capability when live worker-event observation is required.

It does **not** need Jack Kernel configured as its model provider.

It does **not** need direct access to the worker bridge.

It does **not** need the worker’s private control credential.

The public orchestration surface is:

```text
GET  /jack/orchestration/status
GET  /jack/orchestration/events
POST /jack/orchestration/tasks
POST /jack/orchestration/tasks/cancel
POST /jack/orchestration/session/new
```

The reference Codex integration uses Codex’s existing local shell/tool capability to call these routes while Codex continues using its native OpenAI model.

Another cloud-model agent can use the same transport if it can make equivalent HTTP/SSE requests.

---

## 3. The worker bridge must be deterministic

The worker bridge is infrastructure, not a reasoning agent.

It must not guess which task owns an event. It must not invent run identity. It must not silently retry model work. It must not hide lifecycle transitions.

The bridge should expose concrete state such as:

```json
{
  "status": "running",
  "taskId": "…",
  "runId": "…",
  "runEpoch": 1,
  "runOpen": true
}
```

When idle:

```json
{
  "status": "idle"
}
```

When a run is logically cancelled but the underlying worker is still physically unwinding:

```json
{
  "status": "cancelled",
  "runOpen": true
}
```

Only after the worker has actually settled should the bridge report:

```json
{
  "status": "cancelled",
  "runOpen": false,
  "settledAt": "…"
}
```

Logical cancellation and physical settlement are not the same event.

---

## 4. Separate task identity from run identity

Use separate identifiers:

```text
task_id
run_id
run_epoch
```

`task_id` is the stable control request created when the supervisor submits work.

`run_id` is the concrete worker/model execution bound when the agent actually begins running.

`run_epoch` is a monotonically increasing execution generation inside the same controlled task when the worker legitimately re-enters inference.

Do not bind ownership merely because a task is current. Bind ownership only when the worker produces positive lifecycle evidence that a real run has started. For Pi, the useful binding point is `agent_start`.

---

## 5. Preserve event attribution

The worker bridge should expose live events such as:

```text
session
input
before_agent_start
agent_start
message
message_end
tool_start
tool_update
tool_end
agent_end
agent_settled
task_state
```

Each event should carry enough correlation information to determine whether it is run-bound, task-state, or unowned.

Example:

```json
{
  "type": "message",
  "task_id": "…",
  "run_id": "…",
  "run_epoch": 1,
  "attribution": "pi_run_bound",
  "data": {},
  "at": "…"
}
```

Events occurring after the worker has ended a run must not automatically inherit stale task/run ownership.

---

## 6. Expose live events over SSE

The private worker bridge can expose an SSE stream such as:

```text
GET /v1/events
```

Jack then owns the supervisor-facing replay layer at:

```text
GET /jack/orchestration/events
```

A Jack event envelope can include:

```json
{
  "seq": 123,
  "task_id": "…",
  "run_id": "…",
  "run_epoch": 1,
  "attribution": "pi_run_bound",
  "type": "message",
  "source": "pi",
  "source_at": "…",
  "jack_received_at": "…",
  "data": {},
  "source_event": {}
}
```

The supervisor consumes Jack’s SSE stream, never the private worker stream.

---

## 7. Session replacement requires an explicit readiness contract

Expose:

```text
sessionReady
sessionTransitioning
sessionInstanceId
```

A task must not be admitted unless:

```text
sessionReady == true
AND
sessionTransitioning == false
```

When replacement begins, task admission closes immediately. The replacement instance must report a new `sessionInstanceId` before follow-up work is accepted.

Do not use fixed sleeps as proof of readiness. Do not silently retry a task across a session replacement boundary.

---

## 8. Start long-lived worker resources at the correct lifecycle boundary

For Pi specifically, the private HTTP bridge must not begin advertising operational readiness from the extension factory while Pi is still loading the extension.

Correct lifecycle:

```text
extension factory loads
        ↓
Pi binds runtime/action methods
        ↓
session_start
        ↓
bridge starts listening
        ↓
sessionReady = true
```

On shutdown the old instance must close admission, close event clients/listeners, and disappear before the replacement instance becomes ready.

---

## 9. Jack is the only worker-control gateway visible to the supervisor

Jack exposes:

```text
GET  /jack/orchestration/status
GET  /jack/orchestration/events
POST /jack/orchestration/tasks
POST /jack/orchestration/tasks/cancel
POST /jack/orchestration/session/new
```

The supervisor must never be given:

- the worker bridge token;
- the worker bridge private configuration;
- the worker bridge port as an allowed direct control target;
- permission to bypass Jack for worker control.

If the private bridge is unavailable, Jack fails deterministically. There is no hidden direct fallback.

---

## 10. Jack owns external replay

Useful supervisor-facing replay properties include:

- process-local monotonic `seq`;
- bounded replay buffer;
- `Last-Event-ID`;
- optional `?after=<seq>`;
- explicit replay-gap failure when requested history has been retired.

For example:

```text
409 orchestration_replay_gap
```

---

## 11. Cancellation must preserve physical truth

Cancellation is not equivalent to settlement.

A correct sequence can look like:

```text
task running
    ↓
cancel requested
    ↓
status = cancelled
runOpen = true
    ↓
worker stops inference
    ↓
agent_settled
    ↓
status = cancelled
runOpen = false
settledAt = ...
```

Jack must not admit overlapping controlled work while the prior worker run remains physically open.

---

## 12. Tool events remain observable

If the worker can use tools, the cloud supervisor should be able to observe the worker’s tool lifecycle through Jack:

```text
tool_start
tool_update
tool_end
```

A real tool call preserves the same task/run/epoch correlation as the surrounding worker execution.

---

## 13. Worker model/context metadata comes from the worker path

Do not confuse supervisor cognition with worker cognition.

The cloud supervisor keeps its own provider/model/context independently.

Worker model/context metadata describes the model used by the local worker through Jack. When Jack exposes authoritative worker/backend metadata, the supervisor may inspect fields such as:

```text
model
context_length
max_context_length
```

Unknown values remain unknown.

---

## 14. Supervisor session-handoff sequence

A cloud-model supervisor should perform worker session replacement as follows:

```text
1. GET Jack orchestration status
2. Record current sessionInstanceId
3. Require ready + not transitioning
4. POST Jack /session/new
5. Poll Jack status only
6. Temporary Jack 502 is acceptable while the private worker bridge is replaced
7. Wait for:
      sessionReady = true
      sessionTransitioning = false
      new sessionInstanceId != old sessionInstanceId
8. Only then submit the next task
```

Elapsed time is not lifecycle proof.

---

## 15. Supervisor task flow

```text
Cloud-model supervisor
  ↓
POST /jack/orchestration/tasks
  ↓
Jack
  ↓
private worker bridge
  ↓
worker begins task
  ↓
agent_start binds run identity
  ↓
message/tool events stream back through Jack
  ↓
agent_end
  ↓
agent_settled
  ↓
runOpen = false
```

The supervisor can interpret those returned events/results with its own cloud model and decide the next instruction.

---

## 16. Security boundary

The cloud supervisor may know:

- Jack’s public local address;
- Jack orchestration routes;
- public task/run state;
- public worker events;
- worker readiness state;
- worker model/context metadata intentionally exposed by Jack.

The cloud supervisor should not know:

- private worker control token;
- private worker credential files;
- private worker port as an allowed direct control route;
- internal worker runtime references;
- secrets required only for Jack-to-worker communication.

The cloud supervisor may still possess its own independent tool capabilities. Jack’s orchestration contract governs the supervisor-to-worker control path; it does not claim to intercept every independent capability of the external cloud agent.

---

## 17. What not to do

Do not implement:

### Cloud supervisor → private worker directly

```text
cloud supervisor → :8013 → Pi
```

This bypasses Jack.

### Cloud supervisor cognition → Jack → local model

```text
cloud supervisor → Jack /v1 → local LLM
```

That is a different deployment mode and is not the cloud-supervisor architecture described here.

### Sleep-based readiness

```text
/new
sleep 2
submit task
```

Timing speculation is not lifecycle proof.

### Task ownership by assumption

Current task is not the same thing as event provenance.

### Retry after ambiguous failure

Blind retry can duplicate work.

### Treat cancellation as settlement

`cancelled` does not imply `runOpen == false`.

### Let a model invent control state

Task IDs, run IDs, event ownership, settlement, readiness, and evidence provenance must come from deterministic software.

---

## 18. Validation checklist

Before declaring a worker compatible with a cloud-model supervisor through Jack, verify:

### Startup

- Bridge starts only after worker runtime initialization is complete.
- `sessionReady: true`.
- `sessionTransitioning: false`.
- nonempty `sessionInstanceId`.

### Task execution

- stable `task_id`;
- real `run_id`;
- `run_epoch` established;
- live message events visible;
- tool events visible when tools are used;
- authoritative final task state;
- physical settlement produces `runOpen: false`.

### Cancellation

- logical cancellation is observable before physical settlement;
- new controlled work is blocked while the prior run remains open;
- final cancelled state has `runOpen: false`.

### Session replacement

- old `sessionInstanceId` recorded;
- `/session/new` begins asynchronous transition;
- task admission closes immediately;
- old bridge shuts down;
- replacement bridge starts only after runtime rebind;
- new `sessionInstanceId` differs from old;
- follow-up work waits for ready state.

### Isolation

- supervisor never contacts private worker bridge directly;
- supervisor never reads worker control token;
- Jack returns deterministic failure when private bridge is unavailable;
- supervisor’s own cloud cognition remains independent of Jack’s local inference path.

### Replay

- SSE sequence is monotonic;
- reconnect/replay works;
- stale replay requests fail explicitly.

---

## 19. Codex as the current reference cloud supervisor

Codex Desktop is useful for validating this architecture because it combines native OpenAI cognition with a local shell/tool surface capable of calling Jack’s public orchestration API.

In the intended Codex mode:

```text
User
  ↓
Native Codex / OpenAI model
  ↓ supervision
Jack /jack/orchestration
  ↓
Primary Pi
  ↓ inference
Jack /v1
  ↓
local LLM backend
```

Codex is therefore a **reference proxy for the broader class of cloud-model supervisory agents**, not the architectural endpoint.

A different cloud-model agent may replace Codex without changing the worker-side contract, provided it preserves the same Jack mediation boundary.

---

## 20. Generalizing beyond Pi and beyond Codex

Pi is only the reference worker. Codex is only the current reference cloud supervisor.

The reusable architecture is:

```text
cloud-model supervisor
        ↓
Jack deterministic orchestration boundary
        ↓
local privileged worker
        ↓
Jack inference boundary
        ↓
local model/backend
```

Map another worker’s native lifecycle onto:

```text
worker session
worker ready
task
run
run epoch
message
tool start/update/end
logical cancellation
physical settlement
session replacement
```

Map another cloud supervisor onto Jack’s public orchestration API.

Neither side should need to know the other’s private implementation details.

---

## 21. Core rule

The orchestration design follows the same rule as the rest of Jack Kernel:

> **Probabilistic cognition may propose, but deterministic software must dispose.**

The cloud supervisor may decide what work should be done.

The worker model may reason about how to do it.

But task admission, session readiness, run ownership, cancellation, settlement, replay, evidence, and authority remain deterministic software state.