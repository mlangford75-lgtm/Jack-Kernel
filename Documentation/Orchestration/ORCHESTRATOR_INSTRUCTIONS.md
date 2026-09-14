# Orchestrator Instructions

**Applies to:** Any supervisory agent operating through Jack Kernel Orchestration Gateway v2

## Purpose

This file is the operational instruction set for an orchestration agent.

It is not a research paper and not a high-level capability description. It tells the orchestration agent exactly where it may connect, what it may do, how it must observe active work, and which boundaries it must never cross.

The governing rule is:

> **Model source may vary. Jack remains the control boundary.**

For worker supervision, every control action goes through Jack Kernel.

When the orchestration agent uses a local model, its own inference also goes through Jack Kernel.

---

## 1. Know your operating mode

There are two supported supervisor modes.

### Cloud-model orchestration agent

If your cognition comes from a cloud provider, keep using that native cloud model.

Your worker-control path is:

```text
Cloud orchestration agent
    |
    | supervision / worker control
    v
Jack Kernel
http://127.0.0.1:8001/jack/orchestration
    |
    v
Primary Pi or another local worker
    |
    | model inference
    v
Jack Kernel /v1
    |
    v
local model backend
```

Do **not** configure Jack as the cloud supervisor's own model provider in this mode.

### Local-model orchestration agent

If your own cognition uses the local model, your inference must use Jack:

```text
Local orchestration agent
    |
    | cognition
    v
Jack Kernel /v1
    |
    v
local model backend
```

Your worker-control path is still:

```text
Local orchestration agent
    |
    | supervision / worker control
    v
Jack Kernel /jack/orchestration
    |
    v
Primary Pi or another local worker
```

The local orchestration agent and the worker may both infer through Jack concurrently when the configured backend and Jack concurrency permit it.

Neither may bypass Jack and connect directly to the local model server.

---

## 2. Public Jack endpoints you are allowed to use

Use Jack's public orchestration surface only:

```text
GET  http://127.0.0.1:8001/jack/orchestration/status
GET  http://127.0.0.1:8001/jack/orchestration/events
POST http://127.0.0.1:8001/jack/orchestration/tasks
POST http://127.0.0.1:8001/jack/orchestration/tasks/cancel
POST http://127.0.0.1:8001/jack/orchestration/session/new
```

For local supervisor cognition, use Jack's model-facing surface:

```text
http://127.0.0.1:8001/v1
```

Use the Jack virtual model/configuration exposed by the running Jack instance.

Do not independently discover or select the backend behind Jack.

---

## 3. Endpoints you must never use directly

Do not connect directly to the private worker bridge.

Reference Pi bridge port:

```text
http://127.0.0.1:8013
```

Do not call it.

Do not request, read, cache, or use the Pi control token.

Do not connect directly to LM Studio or any other configured backend, including common local backend ports such as:

```text
127.0.0.1:1234
```

Do not bypass Jack for worker control or local-model cognition.

If Jack cannot reach the private worker bridge, stop and report the failure. There is no direct fallback.

---

## 4. Before submitting any worker task

Query:

```text
GET /jack/orchestration/status
```

Require:

```text
sessionReady == true
sessionTransitioning == false
```

Record at minimum:

```text
sessionInstanceId
status
runOpen
```

If a task is already active or a prior run remains physically open, do not submit overlapping controlled work.

Do not use elapsed time, guesses, or a fixed sleep as proof that the worker is ready.

---

## 5. Active supervision requires the live event stream

This is mandatory.

> **During an active supervised task, consume Jack's `/jack/orchestration/events` SSE stream. Status polling may be used for readiness and terminal confirmation, but it must not replace live event observation.**

Do not supervise a build by occasional status polling alone.

The event stream is:

```text
GET http://127.0.0.1:8001/jack/orchestration/events
```

Use a real SSE reader capable of keeping the connection open and processing events as they arrive.

Do not use a request pattern that expects the SSE endpoint to return one finite JSON response.

---

## 6. Preferred task sequence

Whenever practical, use this sequence:

```text
1. GET /jack/orchestration/status
2. Confirm ready and not transitioning
3. Open /jack/orchestration/events
4. Record the current/latest event sequence position
5. POST /jack/orchestration/tasks
6. Record task_id
7. Consume live events
8. Bind and track run_id and run_epoch when Jack exposes them
9. Observe worker messages and tool events live
10. Observe agent_end
11. Continue until physical settlement
12. Confirm terminal status and runOpen == false
13. Only then treat the controlled task as physically complete
```

Do not declare a task complete merely because the worker produced visible output.

---

## 7. Task submission

Submit work through:

```text
POST /jack/orchestration/tasks
```

Current gateway wire contract:

```json
{"prompt":"<non-empty task text>"}
```

Do not call the worker directly.

Record the returned `task_id`.

A task ID is not a run ID.

Do not invent run identity.

---

## 8. Track task and run identity correctly

When events arrive, preserve Jack-provided identity fields such as:

```text
seq
task_id
run_id
run_epoch
attribution
source
```

Do not assume an event belongs to a task simply because that task is currently active.

Only treat an event as run-bound when Jack reports positive run-bound attribution.

If an event is unowned, leave it unowned.

---

## 9. Observe worker tools live

When the worker uses tools, observe the tool lifecycle through Jack when available:

```text
tool_start
tool_update
tool_end
```

Do not treat model narration about a tool as proof that the tool executed.

Use Jack/worker event state as the execution record.

> **Silence is not settlement.** If `runOpen == true` and the last run-bound event is an unterminated tool operation, report that exact state. Do not call the task complete, stopped, or failed merely because the event stream is quiet.

For example, if a `tool_start` for `read index.html` has been observed but no matching `tool_end` has arrived, the supervisor knows that the run remains open and that the tool operation has not reached an observed terminal event. It does **not** know whether the tool is slow, blocked, hung, or otherwise unable to complete unless Jack or the worker reports additional evidence.

A tool failure does not automatically mean the entire user objective failed. Distinguish:

- the worker's substantive work;
- the individual tool failure;
- final task state;
- physical settlement.

If a screenshot or secondary verification tool fails after the worker already produced the requested artifact, do not tell the user the artifact does not exist unless the evidence actually shows that.

---

## 10. Do not confuse message completion with task completion

These are not equivalent:

```text
message_end
agent_end
agent_settled
```

Do not use `message_end` as proof of task completion.

Do not use `agent_end` as proof that all worker activity has physically stopped.

The controlled task is physically settled only when authoritative state shows the run has closed, for example:

```text
runOpen == false
```

with terminal task state / settlement metadata.

---

## 11. Do not answer from stale snapshots

Never tell the user that a task is still running, failed, or incomplete based solely on an old status response if active supervision is available.

Before reporting current task state:

1. process all live events already received;
2. if disconnected, replay missed events;
3. query current status for terminal confirmation;
4. reconcile event state and current status;
5. then answer the user.

If your last observation is stale, say that the state is stale and refresh it before making a definitive claim.

---

## 12. SSE replay and reconnection

Retain the last processed Jack `seq`.

If the SSE connection drops or you attach after task submission, use Jack replay rather than guessing what occurred while disconnected.

Supported replay mechanisms include:

```text
Last-Event-ID: <last processed seq>
```

or:

```text
GET /jack/orchestration/events?after=<last processed seq>
```

If Jack reports:

```text
409 orchestration_replay_gap
```

do not silently continue as if history were complete.

Report that part of the event history is unavailable and use current authoritative status only for what it can actually establish.

> **If you join an active task late or reconnect after interruption, use replay from the last known sequence position whenever possible. Do not reconstruct missed execution from a later status snapshot.**

> **A local SSE-reader timeout is not a worker-state event.** If the reader times out or the connection closes locally, do not interpret that as worker completion, worker failure, or settlement. Reconnect using replay from the last processed `seq`, then reconcile the replayed events with current Jack status before reporting the task state.

---

## 13. Cancellation

Cancel through:

```text
POST /jack/orchestration/tasks/cancel
```

Cancellation and physical settlement are different.

A task can be logically cancelled while:

```text
runOpen == true
```

Do not submit overlapping controlled work until Jack reports that the prior run is physically closed.

---

## 14. Session replacement

Request a new worker session only through:

```text
POST /jack/orchestration/session/new
```

Required sequence:

```text
1. GET status
2. Record old sessionInstanceId
3. Require ready + not transitioning
4. POST /session/new through Jack
5. Stop task admission
6. Poll Jack status only during replacement
7. Temporary Jack 502 may occur while the private bridge is replaced
8. Wait for sessionReady == true
9. Wait for sessionTransitioning == false
10. Require new sessionInstanceId != old sessionInstanceId
11. Only then submit follow-up work
```

Do not use a fixed sleep as readiness proof.

Do not contact the private bridge to determine whether replacement succeeded.

---

## 15. What you are allowed to decide

As the orchestration agent, you may decide:

- what worker task to submit;
- how to decompose the user's objective;
- whether more worker work is needed;
- whether a result should be checked or revised;
- whether cancellation or session replacement is appropriate;
- whether the overall user objective has been satisfied.

Those are cognitive/supervisory decisions.

---

## 16. What you are not allowed to invent

Do not invent or infer authoritative values for:

- task admission;
- `task_id`;
- `run_id`;
- `run_epoch`;
- event ownership;
- worker readiness;
- cancellation state;
- physical settlement;
- session replacement state;
- replay sequence;
- worker availability;
- tool execution evidence.

Those come from Jack and the worker control path.

Probabilistic cognition may interpret them, but it does not create them.

---

## 17. Direct inference is not worker orchestration

A call to:

```text
POST /v1/chat/completions
```

or another Jack `/v1` inference route is a model-inference transaction.

It does not automatically create a Primary Pi worker task.

Therefore:

```text
client -> Jack /v1 -> local model
```

is different from:

```text
supervisor -> Jack /jack/orchestration/tasks -> Primary Pi
Primary Pi -> Jack /v1 -> local model
```

If the user's intent is "ask the model," direct inference may be correct.

If the user's intent is "have the build agent do this," submit a worker task through `/jack/orchestration/tasks` and supervise it through the live event stream.

Do not claim that a direct `/v1` call appeared on the worker orchestration stream.

---

## 18. Cloud-supervisor specific rules

When you are a cloud-model supervisor:

- keep your native cloud cognition;
- do not route your own cognition through Jack `/v1` merely because the worker uses Jack;
- use Jack `/jack/orchestration/*` for worker control;
- consume Jack SSE for active worker supervision;
- never contact the private worker bridge;
- never contact the local model backend directly as a substitute for worker orchestration.

Codex is one example of a cloud-model supervisor. It is not a special architectural requirement.

---

## 19. Local-supervisor specific rules

When you are a local-model supervisor:

- use Jack `/v1` for your own cognition;
- use Jack `/jack/orchestration/*` for worker control;
- consume Jack SSE for active worker supervision;
- never connect directly to the local backend;
- never contact the private worker bridge;
- allow Jack/backend concurrency to provide simultaneous supervisor and worker inference when configured.

Reference topology:

```text
Local Supervisor -> Jack /v1 -> local model
Local Supervisor -> Jack /jack/orchestration -> Worker
Worker           -> Jack /v1 -> local model
```

---

## 20. Failure behavior

If Jack reports a deterministic gateway or availability failure:

- stop;
- report the actual failure;
- do not bypass Jack;
- do not silently redirect to the private bridge;
- do not silently redirect the worker to the backend;
- do not blindly retry an ambiguous task submission.

Blind retry can duplicate work.

If you are uncertain whether a task was accepted, resolve state through Jack before attempting another submission.

---

## 21. Minimum operating checklist

Before work:

```text
[ ] Correct supervisor mode identified: cloud or local
[ ] Jack reachable on 127.0.0.1:8001
[ ] Worker sessionReady == true
[ ] worker sessionTransitioning == false
[ ] No prior controlled run physically open
```

During work:

```text
[ ] SSE stream active
[ ] seq retained
[ ] task_id retained
[ ] run_id/run_epoch tracked when bound
[ ] message and tool events observed live
[ ] no stale-snapshot guessing
[ ] SSE-reader timeout never treated as a worker-state event
[ ] quiet stream never treated as settlement
```

After work:

```text
[ ] terminal worker state observed
[ ] runOpen == false
[ ] relevant tool failures distinguished from substantive task result
[ ] user-facing status reflects current authoritative state
```

After reconnect:

```text
[ ] replay from last processed seq attempted
[ ] replay gap handled explicitly if returned
[ ] current status reconciled with replayed events
```

---

## 22. Canonical summary

```text
CLOUD SUPERVISOR

Cloud model <-> Orchestration Agent
Orchestration Agent -> Jack /jack/orchestration -> Worker
Worker -> Jack /v1 -> Local Model

LOCAL SUPERVISOR

Orchestration Agent -> Jack /v1 -> Local Model
Orchestration Agent -> Jack /jack/orchestration -> Worker
Worker -> Jack /v1 -> Local Model
```

During active worker supervision:

```text
status establishes readiness
SSE establishes live execution history
replay restores missed history
settlement establishes physical completion
```

> **Never bypass Jack for worker control. Never bypass Jack for local-model inference. Never replace live event supervision with stale polling. Silence is not settlement.**

Related specification:

- `ORCHESTRATION_AGENT_CAPABILITY_CONTRACT.md`

The capability contract defines what an orchestration agent must support. This file defines how the orchestration agent must operate.