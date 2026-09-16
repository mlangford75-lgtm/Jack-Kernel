# Orchestrate with a Cloud- or Local-Model Agent

## Purpose

This document explains how an orchestration agent supervises and operates a local worker—such as Primary Pi—through Jack Kernel without bypassing Jack’s deterministic control boundary.

Codex Desktop is the current reference cloud-model example. Jack Orchestrator is the current reference local-model example. Neither is the architectural requirement. Any supervisory agent may qualify if it satisfies the Jack orchestration contract.

For the normative interoperability requirements, read [`ORCHESTRATION_AGENT_CAPABILITY_CONTRACT.md`](ORCHESTRATION_AGENT_CAPABILITY_CONTRACT.md).

For the Codex-specific operator procedure, see [`USING_CODEX_AS_JACK_ORCHESTRATION_AGENT.md`](USING_CODEX_AS_JACK_ORCHESTRATION_AGENT.md).

The central rule is:

> **MODEL SOURCE MAY VARY. CONTROL BOUNDARY DOES NOT.**

Every supervisor-to-worker control action crosses Jack Kernel. When the orchestration agent uses a local model, its own model inference must also cross Jack Kernel. No locally modeled supervisor or worker may connect directly to the local model server.

---

## 1. Supported supervisory topologies

### 1.1 Cloud-model supervisor

A cloud-model supervisor keeps cognition on its native cloud provider and uses Jack for worker supervision/control.

```text
User
  |
  v
Cloud-model orchestration agent
(native cloud cognition; Codex is one example)
  |
  | supervision / worker control
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

There is no supervisor-cognition path through Jack `/v1` in this mode. Jack does not replace the cloud agent’s model provider.

### 1.2 Local-model supervisor

A locally modeled orchestration agent uses Jack for both its own cognition and worker supervision.

```text
User
  |
  v
Local-model orchestration agent
  |
  | cognition
  v
Jack Kernel :8001/v1
  |
  v
local LLM server / configured backend

Local-model orchestration agent
  |
  | supervision / worker control
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

This is the reference Jack Orchestrator pattern. With multiple backend concurrency slots, the local supervisor and Primary Pi may infer concurrently through the same Jack Kernel. They still do not bypass Jack.

---

## 2. What the orchestration agent must be able to do

A compatible orchestration agent must be able to:

1. understand the user’s objective and decide what to delegate;
2. query worker status/readiness through Jack;
3. submit worker tasks through Jack;
4. consume Jack’s live worker-event SSE stream;
5. track `seq`, `task_id`, `run_id`, `run_epoch`, and attribution;
6. observe worker messages and tool activity;
7. distinguish message generation from physical settlement;
8. cancel controlled work through Jack;
9. replace the worker session safely through Jack;
10. reconnect/replay SSE using Jack sequence state;
11. detect and report replay gaps;
12. interpret worker results and issue follow-up instructions when needed;
13. never bypass Jack to the private worker bridge;
14. when locally modeled, send all supervisor inference through Jack rather than directly to the local model server.

The full normative version of this list is in [`ORCHESTRATION_AGENT_CAPABILITY_CONTRACT.md`](ORCHESTRATION_AGENT_CAPABILITY_CONTRACT.md).

---

## 3. What must change in an existing worker

A worker such as Pi does not need to become aware of Codex, OpenAI, or any other specific supervisor. It needs a small deterministic control adapter that exposes the worker’s existing runtime capabilities in a form Jack can safely mediate.

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

The supervisor must not call these private endpoints directly.

---

## 4. Public Jack orchestration surface

A supervisor uses:

```text
GET  /jack/orchestration/status
GET  /jack/orchestration/events
POST /jack/orchestration/tasks
POST /jack/orchestration/tasks/cancel
POST /jack/orchestration/session/new
```

A cloud supervisor uses these routes while keeping cognition on its native provider.

A local supervisor uses these routes for control and also uses Jack’s `/v1` inference surface for its own cognition.

The worker independently uses Jack `/v1` for its model inference.

---

## 5. The worker bridge must be deterministic

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

When a run is logically cancelled but the underlying worker is still physically unwinding:

```json
{
  "status": "cancelled",
  "runOpen": true
}
```

Only after the worker has actually settled should it report:

```json
{
  "status": "cancelled",
  "runOpen": false,
  "settledAt": "…"
}
```

Logical cancellation and physical settlement are not the same event.

---

## 6. Separate task identity from run identity

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

## 7. Preserve event attribution

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

## 8. Expose live events over SSE

The private worker bridge can expose an SSE stream such as:

```text
GET /v1/events
```

Jack owns the supervisor-facing replay layer at:

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


### 8.1 Status snapshots are not live-progress streams

Jack's orchestration status surface and Jack's SSE event stream have different responsibilities.

The status endpoint exposes authoritative compact control and lifecycle state, including readiness, task identity, run identity, `run_epoch`, cancellation state, `runOpen`, and physical settlement.

The SSE event stream exposes the authoritative chronological record of worker activity and lifecycle transitions, including messages, tool activity, run binding, task-state changes, agent completion, and settlement.

A supervisor MUST NOT use a compact status snapshot as the sole source of truth for whether an active worker is making progress.

While `runOpen=true`, the supervisor must continue consuming Jack's SSE stream. If a status snapshot appears unchanged, stale, incomplete, or inconsistent with newer SSE events, the supervisor must inspect the live or replayed event stream before concluding that the worker is inactive, failed, stalled, or eligible for retry.

Absence of visible progress in a status response is not evidence that the worker has stopped progressing.

A supervisor MUST NOT cancel, replace, retry, or declare an active run failed merely because the compact status snapshot has not changed.

When an SSE connection is interrupted, the supervisor must reconnect using Jack's sequence/replay contract and recover available events rather than assuming that no activity occurred during the interruption.

Status remains authoritative for compact lifecycle/control facts. SSE remains authoritative for chronological worker activity. Neither surface should be substituted for the other.

---

## 9. Session replacement requires an explicit readiness contract

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

## 10. Start long-lived worker resources at the correct lifecycle boundary

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

## 11. Jack is the only worker-control gateway visible to the supervisor

The supervisor must never be given:

- the worker bridge token;
- the worker bridge private configuration;
- the worker bridge port as an allowed direct control target;
- permission to bypass Jack for worker control.

If the private bridge is unavailable, Jack fails deterministically. There is no hidden direct fallback.

---

## 12. Jack owns external replay

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

A replay gap must be reported explicitly. Missing history must not be silently treated as complete history.

---

## 13. Cancellation must preserve physical truth

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

## 14. Tool events remain observable

If the worker can use tools, the supervisor should be able to observe the worker’s tool lifecycle through Jack:

```text
tool_start
tool_update
tool_end
```

A real tool call preserves the same task/run/epoch correlation as the surrounding worker execution.

The supervisor must not treat model-authored tool claims as host execution evidence.

---

## 15. Worker model/context metadata comes from the worker path

Worker model/context metadata describes the model used by the local worker through Jack. When Jack exposes authoritative worker/backend metadata, the supervisor may inspect fields such as:

```text
model
context_length
max_context_length
```

Unknown values remain unknown.

For a cloud supervisor, this metadata describes the worker path, not the cloud supervisor’s own model/context.

For a local supervisor, its own cognition also runs through Jack and therefore has a Jack-mediated local inference path.

---

## 16. Supervisor session-handoff sequence

Any supervisor should perform worker session replacement as follows:

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

## 17. Supervisor task flow

```text
Orchestration agent
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

The supervisor interprets returned events/results, decides whether the user’s objective has been satisfied, and issues follow-up worker instructions through Jack when needed.


### 17.1 Active-run supervision policy

While a controlled worker run remains physically open, the supervisor observes and supervises that existing run rather than treating latency, silence, repetition, or apparent lack of progress as proof of failure.

The supervisor MUST NOT cancel, interrupt, replace, or otherwise terminate an active worker run merely because it appears slow, repetitive, stalled, or unproductive.

A supervisor-side timeout, SSE disconnect, quiet period, repeated model behavior, or suspected worker stall is not authoritative evidence that the worker has failed or settled. The supervisor MUST continue consuming Jack's event stream, reconnect with replay when necessary, and rely on Jack's deterministic lifecycle state.

Cancellation or session replacement requires either:

- an explicit user instruction; or
- an authoritative deterministic condition exposed through Jack that makes continued execution impossible or invalid under the orchestration contract.

While `runOpen=true`, the supervisor MUST NOT create competing overlapping controlled work. Corrective follow-up work is normally submitted only after the current controlled run reaches authoritative physical settlement with `runOpen=false`.

The supervisor may evaluate streamed worker messages and tool events while the run is active, but those observations remain supervisory evidence. They do not themselves authorize cancellation, establish failure, or establish settlement.

This rule preserves the distinction between probabilistic supervisory judgment and deterministic execution authority: the model may suspect that a run is stuck, but Jack's lifecycle state determines whether the run is actually open, cancelled, failed, or settled.

---

## 18. Security boundary

The supervisor may know:

- Jack’s public local address;
- Jack orchestration routes;
- public task/run state;
- public worker events;
- worker readiness state;
- worker model/context metadata intentionally exposed by Jack.

The supervisor should not know:

- private worker control token;
- private worker credential files;
- private worker port as an allowed direct control route;
- internal worker runtime references;
- secrets required only for Jack-to-worker communication.

A cloud supervisor may possess independent tools of its own. Jack’s orchestration contract governs supervisor-to-worker control; it does not claim to intercept every independent action of an external cloud agent.

A local supervisor must not use an independent direct connection to the local model server. Its local model cognition crosses Jack.

---

## 19. What not to do

### Supervisor → private worker directly

```text
Supervisor → :8013 → Pi
```

This bypasses Jack and is forbidden.

### Local supervisor → local model directly

```text
Local supervisor → local LLM server
```

This bypasses Jack and is forbidden.

### Worker → local model directly

```text
Worker → local LLM server
```

This bypasses Jack and is forbidden.

### Cloud supervisor cognition → Jack → local model

```text
Cloud supervisor → Jack /v1 → local LLM
```

That is the local-supervisor deployment mode, not the cloud-supervisor architecture.

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

## 20. Validation checklist

### Common requirements

- worker bridge starts only after runtime initialization;
- `sessionReady: true` and `sessionTransitioning: false` before task admission;
- stable `task_id`;
- real `run_id` and `run_epoch`;
- live message events visible;
- active-run progress is observed through Jack's SSE stream rather than inferred from the compact status snapshot alone;
- tool events visible when tools are used;
- authoritative final task state;
- physical settlement produces `runOpen: false`;
- logical cancellation can precede settlement;
- new work is blocked while the prior run is open;
- session replacement produces a new `sessionInstanceId`;
- supervisor never contacts the private worker bridge directly;
- Jack returns deterministic failure when the private bridge is unavailable;
- SSE sequence is monotonic;
- reconnect/replay works;
- stale replay requests fail explicitly.

### Cloud-supervisor requirements

- supervisor cognition remains on its native cloud provider;
- Jack is used for worker supervision/control only;
- Jack is not configured as the cloud supervisor’s model provider for this architecture.

### Local-supervisor requirements

- all supervisor model inference runs through Jack;
- supervisor never connects directly to the local model server;
- worker also reaches the local model only through Jack;
- concurrent local supervisor/worker inference, when desired, uses Jack/backend concurrency rather than bypass connections.

---

## 21. Codex and Jack Orchestrator as reference implementations

### Codex

Codex Desktop is the current reference cloud supervisor:

```text
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

Codex is a reference proxy for the broader class of cloud-model supervisory agents, not the architectural endpoint.

### Jack Orchestrator

Jack Orchestrator is the current reference local supervisor:

```text
Jack Orchestrator
  ↓ cognition
Jack /v1
  ↓
local LLM backend

Jack Orchestrator
  ↓ supervision
Jack /jack/orchestration
  ↓
Primary Pi
  ↓ inference
Jack /v1
  ↓
local LLM backend
```

The same rule applies to any other locally modeled orchestration agent.

---

## 22. Generalizing beyond Pi, Codex, and Jack Orchestrator

Pi is only the reference worker. Codex is only the current reference cloud supervisor. Jack Orchestrator is only the current reference local supervisor.

The reusable contract is:

```text
Cloud cognition:
Cloud model <-> Supervisor
Supervisor -> Jack -> Worker
Worker     -> Jack -> Local model

Local cognition:
Supervisor -> Jack -> Local model
Supervisor -> Jack -> Worker
Worker     -> Jack -> Local model
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

Map another supervisor onto Jack’s public orchestration API and, if its cognition is local, Jack’s model-facing inference API.

Neither side should need to know the other’s private implementation details.

---

## 23. Core rule

The orchestration design follows the same rule as the rest of Jack Kernel:

> **Probabilistic cognition may propose, but deterministic software must dispose.**

The supervisor may decide what work should be done.

The worker model may reason about how to do it.

But task admission, session readiness, run ownership, cancellation, settlement, replay, evidence, and authority remain deterministic software state.

And the connection rule is absolute:

> **No locally modeled participant may bypass Jack to reach the local model server, and no orchestration agent may bypass Jack to control the worker.**