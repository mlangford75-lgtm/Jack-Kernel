# Jack Kernel Orchestration Gateway v2
## Canonical Technical Specification and Supervisor Compatibility Contract

**Kernel:** Jack Kernel v0.1.1  
**Subsystem:** Orchestration Gateway v2  
**Status:** current normative orchestration specification  
**Current validated Primary-Pi bridge SHA-256 (Windows CRLF representation):** `93A6843CDAAEDA637474B584919ED003930296DE281570E3DDC391F54EF65565`

**Canonical repository LF SHA-256:** `8FFD33FD33AE15A785E2BF9015F17FC14F1DE27B09515D5E868EC163D54C15F0`

## 1. Purpose and authority

Orchestration Gateway v2 defines the deterministic supervisor-to-worker control boundary around a privileged local worker such as Primary Pi.

The core rule is:

> **MODEL SOURCE MAY VARY. CONTROL BOUNDARY DOES NOT.**

A supervisor may use cloud-hosted cognition or local-model cognition. Every supervisor-to-worker control action crosses Jack Kernel. When the supervisor itself uses a local model, its own inference also crosses Jack Kernel. A locally modeled supervisor or worker does not connect directly to the local model backend.

This document is normative for orchestration protocol, lifecycle, authority, and compatibility. Operational behavior for a supervising agent is defined in [`ORCHESTRATOR_INSTRUCTIONS.md`](ORCHESTRATOR_INSTRUCTIONS.md).

The original September 12, 2026 live acceptance record is preserved as historical evidence under [`Historical/ORCHESTRATION_GATEWAY_V2_ACCEPTANCE_REPORT_2026-09-12.md`](Historical/ORCHESTRATION_GATEWAY_V2_ACCEPTANCE_REPORT_2026-09-12.md). That acceptance used an earlier bridge identity and must not be read as the identity of the current bridge.

## 2. Supported supervisory topologies

### 2.1 Cloud-model supervisor

```text
Cloud-model supervisor
  <-> native cloud model/provider

Cloud-model supervisor
  -> Jack Kernel :8001/jack/orchestration
  -> private worker bridge
  -> local worker
  -> Jack Kernel :8001/v1
  -> configured local backend
```

The cloud supervisor retains its native cloud cognition. Jack does not replace the cloud supervisor's model provider.

### 2.2 Local-model supervisor

```text
Local-model supervisor
  -> Jack Kernel :8001/v1
  -> configured local backend

Local-model supervisor
  -> Jack Kernel :8001/jack/orchestration
  -> private worker bridge
  -> local worker
  -> Jack Kernel :8001/v1
  -> configured local backend
```

When Jack and the backend are configured for multiple concurrent requests, local supervisor and worker inference may overlap through the same Jack Kernel. Neither may bypass Jack.

## 3. Public and private surfaces

### 3.1 Public Jack orchestration surface

A supervisor uses:

```text
GET  /jack/orchestration/status
GET  /jack/orchestration/events
POST /jack/orchestration/tasks
POST /jack/orchestration/tasks/cancel
POST /jack/orchestration/session/new
```

Task submission body:

```json
{"prompt":"<non-empty task text>"}
```

A local-model supervisor additionally uses Jack's model-facing `/v1` inference surface for its own cognition.

### 3.2 Private worker-control surface

The reference Pi bridge exposes a private control surface to Jack:

```text
GET  /v1/status
GET  /v1/events
POST /v1/tasks
POST /v1/tasks/cancel
POST /v1/session/new
```

The reference bridge is loopback/private and separately authenticated. The supervisor must not call the private bridge directly and must not receive, read, cache, or use the Pi control token.

## 4. Deterministic authority boundary

The supervisor may decide:

- what work to delegate;
- how to decompose the user's objective;
- whether more worker work is useful;
- whether a result should be checked or revised;
- whether to request cancellation or session replacement;
- when the user's overall objective has been satisfied.

Jack and the worker-control path remain authoritative for:

- task admission;
- worker readiness;
- `task_id`;
- `run_id` and `run_epoch`;
- event attribution/provenance;
- cancellation state;
- physical settlement;
- session replacement state;
- replay sequencing;
- worker availability;
- private bridge authentication.

The supervisor may interpret these facts. It must not fabricate them.

A supervisor may request cancellation based on its judgment or the user's instruction. The act of requesting cancellation does not allow the supervisor to invent that cancellation succeeded, that the worker failed, or that the run settled. Those facts remain deterministic Jack/worker state.

## 5. Required worker-adapter capabilities

A Pi-like worker adapter must expose enough deterministic state to support:

1. status and readiness;
2. live events;
3. task submission;
4. cancellation;
5. new-session control;
6. physical settlement;
7. stable task/run correlation;
8. explicit readiness during runtime/session replacement.

The bridge is infrastructure, not a reasoning agent. It must not guess task ownership, invent run identity, hide lifecycle transitions, or manufacture success.

## 6. Task identity, run identity, and epochs

Gateway v2 separates:

```text
task_id
run_id
run_epoch
```

- `task_id` is the stable control-request identity created for submitted work.
- `run_id` is the stable correlation identity for the complete controlled operation.
- `run_epoch` is the low-level worker execution generation within that control run.

A controlled operation may contain multiple low-level epochs because the worker may retry or continue after `agent_end` before final settlement.

```text
run_id = R
  epoch 1: agent_start ... agent_end
  epoch 2: retry agent_start ... agent_end
  epoch 3: continuation agent_start ... agent_end
  ...
agent_settled closes R
```

A task ID is not a run ID. Ownership is not inferred merely because a task happens to be current.

## 7. Reference Pi correlation mechanism

The validated Pi bridge creates a private per-dispatch correlation marker alongside a controlled `task_id` and `run_id`. The marker is recognized only at Pi's extension-injected `input` boundary and stripped before model-visible prompt processing.

Binding advances through the worker lifecycle:

```text
POST /tasks
  -> pending dispatch {task_id, run_id}
  -> exact extension-input marker observed
  -> before_agent_start
  -> agent_start
  -> active {task_id, run_id, run_epoch}
```

At `agent_start`, message/tool callbacks may snapshot the positive run binding. At `agent_end`, low-level active-run ownership is cleared immediately. Events arriving after `agent_end` do not inherit stale run ownership merely because the higher-level control task has not yet settled.

`agent_settled` closes the complete control run.

This design was originally validated against Pi 0.84.2 lifecycle semantics. When changing Pi versions, the extension lifecycle assumptions must be revalidated rather than treated as timeless Pi behavior.

## 8. Event attribution and preservation

Run-bound events may carry:

```json
{
  "seq": 123,
  "task_id": "...",
  "run_id": "...",
  "run_epoch": 1,
  "attribution": "pi_run_bound",
  "type": "message",
  "source": "pi",
  "source_at": "...",
  "jack_received_at": "...",
  "data": {},
  "source_event": {}
}
```

Task-state events use task-intrinsic attribution. Events without positive ownership evidence remain unowned with null task/run identity.

Jack normalizes transport identity while preserving the underlying source event. It must not repair missing ownership by guessing.

## 9. Status and SSE answer different questions

`GET /jack/orchestration/status` answers compact authoritative lifecycle/control questions such as readiness, current task/run identity, cancellation state, `runOpen`, and settlement.

`GET /jack/orchestration/events` provides the chronological record of worker activity and lifecycle transitions.

A status snapshot is not a live-progress stream. During active supervision, a supervisor must consume SSE rather than conclude that work is stalled merely because the compact status snapshot did not change.

Absence of visible progress is not proof of failure or settlement.

## 10. Replay and sequence contract

Jack assigns process-local monotonically increasing `seq` values and maintains a bounded in-memory replay window.

Default replay retention:

```text
512 events
```

Reconnect using either:

```text
Last-Event-ID: <last processed seq>
```

or:

```text
GET /jack/orchestration/events?after=<last processed seq>
```

If the requested position has fallen outside retained history, Jack returns HTTP `409` with `orchestration_replay_gap` and the retained range. A replay gap must not be silently treated as complete history.

The replay buffer is transport recovery state, not durable forensic memory.

## 11. Readiness and session replacement

A controlled task may be admitted only when authoritative status reports:

```text
sessionReady == true
sessionTransitioning == false
```

Session replacement uses the public Jack route and requires a new ready `sessionInstanceId` before follow-up work.

A temporary Jack `502` may occur while the private worker bridge is deliberately being replaced. The supervisor continues through Jack; it does not use the private bridge as a fallback.

Elapsed time or a fixed sleep is not readiness proof.

## 12. Completion and physical settlement

These are distinct lifecycle facts:

```text
message_end
agent_end
agent_settled
```

`message_end` is not task completion. `agent_end` closes a low-level worker epoch but does not necessarily establish physical settlement.

The strongest terminal condition is a terminal task state with:

```text
runOpen == false
settledAt present
```

Logical cancellation may be visible while `runOpen == true`. New overlapping controlled work is blocked until the prior control run is physically closed.

## 13. Retry and recoverable-failure semantics

A legitimate retry/continuation keeps the same `run_id` and increments `run_epoch`.

Historical assistant failure from an older epoch may remain visible as prior diagnostic state without poisoning the live retry epoch. A later successful assistant completion may clear that prior assistant failure state.

Structured tool failures remain diagnostic evidence. A tool error does not automatically force the overall controlled task to fail if the worker subsequently recovers and completes successfully.

The bridge must not infer failure from free-form model/tool text. Structured runtime metadata is authoritative.

## 14. Failure behavior

If Jack cannot reach the private worker bridge, Jack returns deterministic gateway failure. The supervisor must not fabricate queued/running/completed state and must not bypass Jack to contact the bridge or backend directly.

Ambiguous task submission must be resolved through Jack state before retrying because blind retry can duplicate work.

## 15. Supervisor compatibility contract

A compatible orchestration agent must be able to:

- interpret the user's objective and decide what to delegate;
- query worker readiness through Jack;
- submit tasks through Jack;
- consume Jack's live SSE worker stream;
- retain and interpret `seq`, `task_id`, `run_id`, `run_epoch`, attribution, and source;
- observe worker messages and tool activity;
- distinguish visible answer generation from physical settlement;
- request cancellation through Jack;
- replace the worker session through Jack;
- reconnect and replay SSE safely;
- report replay gaps explicitly;
- interpret results and issue follow-up instructions when needed;
- never contact the private worker bridge directly;
- never bypass Jack for worker control;
- when locally modeled, send supervisor inference through Jack rather than directly to the local model server.

A cloud-model supervisor keeps its own cognition on its native cloud provider and uses Jack for worker control/observation. A local-model supervisor uses Jack for both local cognition and worker control.

## 16. Current implementation identity and historical acceptance

The current validated Primary-Pi bridge distributed by this repository is:

```text
Pi/pi-control-bridge.ts
Windows CRLF SHA-256 93A6843CDAAEDA637474B584919ED003930296DE281570E3DDC391F54EF65565
Canonical repository LF SHA-256 8FFD33FD33AE15A785E2BF9015F17FC14F1DE27B09515D5E868EC163D54C15F0
```

The September 12 Gateway v2 live acceptance was performed against an earlier bridge identity:

```text
D066FA2F9B8A3735A60F57F028087F314F484B28DBD10640FB3D64A4FA29C664
```

That acceptance remains valid as historical evidence for the boundary tested at that time. Subsequent validated bridge revisions improved retry/recovery and settlement semantics without making the old acceptance artifact the identity authority for the current runtime.

Current bridge identity is published in `Pi/README.md` and should be treated as the repository's runtime identity reference.

## 17. Canonical architecture rule

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

> **Probabilistic cognition may propose, but deterministic software must dispose.**

The supervisor and worker models may reason. Jack and deterministic worker-control software own task admission, readiness, run ownership, cancellation state, settlement, replay, and control authority.