# Orchestrator Instructions

**Applies to:** any supervisory agent operating through Jack Kernel Orchestration Gateway v2  
**Normative protocol:** [`ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md`](ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md)

## 1. Governing rule

> **Model source may vary. Jack remains the control boundary.**

> **Strict authority. Resilient execution. Preserved useful work.**

For worker supervision, every control action goes through Jack Kernel.

If the orchestration agent uses a local model, its own inference also goes through Jack Kernel. A cloud-model supervisor keeps its native cloud cognition and uses Jack for worker control and observation.

Never bypass Jack to control the worker. Never bypass Jack to reach the local model backend when the supervisor itself is locally modeled.

## 2. Know your operating mode

### Cloud-model supervisor

```text
Cloud model <-> Supervisor
Supervisor -> Jack /jack/orchestration -> Worker
Worker     -> Jack /v1 -> Local Model
```

Keep the supervisor's cognition on its native cloud provider. Do not configure Jack as the cloud supervisor's model provider merely because the worker uses Jack.

### Local-model supervisor

```text
Supervisor -> Jack /v1 -> Local Model
Supervisor -> Jack /jack/orchestration -> Worker
Worker     -> Jack /v1 -> Local Model
```

Use Jack for both supervisor cognition and worker control. Do not connect directly to the configured local backend.

## 3. Allowed public Jack routes

For worker control:

```text
GET  http://127.0.0.1:8001/jack/orchestration/status
GET  http://127.0.0.1:8001/jack/orchestration/events
POST http://127.0.0.1:8001/jack/orchestration/tasks
POST http://127.0.0.1:8001/jack/orchestration/tasks/cancel
POST http://127.0.0.1:8001/jack/orchestration/session/new
```

For local supervisor cognition, use Jack's `/v1` model-facing surface.

Do not independently discover or select the backend behind Jack.

In a multi-endpoint deployment, preserve the intended Jack lane's logical `runtime_id`/`lane_id` context. Default/example ports such as `8001` and `8013` are transport locations, not identity or authority.

## 4. Forbidden direct paths

Do not:

- call the private worker bridge directly;
- use `127.0.0.1:8013` as a supervisor control endpoint;
- request, read, cache, or use the Pi control token;
- connect directly to LM Studio or another configured backend as a substitute for Jack;
- fabricate task/run/settlement/readiness state;
- silently create a fallback path around Jack.

If Jack cannot reach the worker bridge, report the failure through Jack's observed state. Do not bypass the failed boundary.

## 5. Before submitting work

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

If another controlled run is physically open, do not submit overlapping controlled work.

Elapsed time, a fixed sleep, or an unchanged status snapshot is not proof that the worker is ready, stalled, failed, or settled.

## 6. Preferred supervised-task sequence

```text
1. GET /jack/orchestration/status
2. Confirm ready and not transitioning
3. Open /jack/orchestration/events
4. Retain the latest processed seq
5. POST /jack/orchestration/tasks
6. Record task_id
7. Consume live events
8. Track run_id and run_epoch when Jack exposes them
9. Observe worker messages and tool events
10. Observe agent_end without treating it as settlement
11. Continue through retries/continuations as needed
12. Wait for terminal state with runOpen == false
13. Require settlement metadata before treating the run as physically complete
```

Task submission body:

```json
{"prompt":"<non-empty task text>"}
```

A `task_id` is not a `run_id`. Do not invent run identity.

## 7. Active supervision requires SSE

During an active supervised task, consume:

```text
GET /jack/orchestration/events
```

Status polling is useful for compact lifecycle state and terminal confirmation. It does not replace the chronological event stream.

While `runOpen == true`:

- continue observing the existing run;
- do not infer failure from silence, repetition, latency, or an unchanged compact status snapshot;
- do not infer settlement from a local SSE-reader timeout;
- reconnect with replay after interruption;
- do not create competing overlapping controlled work.

If an SSE connection drops, reconnect from the last processed `seq` using `Last-Event-ID` or `?after=<seq>`.

If Jack returns `409 orchestration_replay_gap`, report that part of the event history is unavailable. Do not reconstruct missing execution from inference.

## 8. Preserve Jack-provided identity

Retain and interpret:

```text
seq
task_id
run_id
run_epoch
attribution
source
```

Only treat an event as run-bound when Jack reports positive run-bound attribution.

If an event is unowned, leave it unowned.

Do not assign an event to a task merely because that task appears current.

The same rule applies to runtime routing: registry state may locate a candidate runtime, but positive live runtime identity is the stronger identity fact. Do not equate a port number or stale manifest status with logical ownership.

## 9. Tool activity and evidence

Observe worker tool lifecycle through Jack when available:

```text
tool_start
tool_update
tool_end
```

Model narration about a tool is not proof that the tool executed.

A structured tool failure is diagnostic evidence. It does not automatically mean the user's overall objective failed. Distinguish:

- the individual tool failure;
- the worker's substantive work;
- final task state;
- physical settlement.

Do not infer structured execution failure from free-form tool/model text when Jack does not report structured failure state.

## 10. Completion and settlement

Do not conflate:

```text
message_end
agent_end
agent_settled
```

`message_end` is not task completion.

`agent_end` is not proof that the complete control run has physically settled.

For orchestration purposes, the strongest terminal condition is a terminal task state with:

```text
runOpen == false
settledAt present
```

Before reporting a definitive current task state:

1. process live events already received;
2. replay missed events if disconnected;
3. query current status for terminal confirmation;
4. reconcile event history with current status;
5. then report the state.

## 11. Cancellation

Request cancellation only through:

```text
POST /jack/orchestration/tasks/cancel
```

The supervisor is allowed to decide that cancellation is appropriate based on the user's instruction, the task objective, observed worker behavior, or other supervisory judgment.

However, requesting cancellation does **not** authorize the supervisor to invent the resulting state. Jack remains authoritative for whether cancellation was accepted, whether the worker remains physically open, and when settlement occurs.

A task may be logically cancelled while:

```text
runOpen == true
```

Do not submit overlapping controlled work until Jack reports that the prior run is physically closed.

A lost HTTP/SSE client connection is not an implicit cancellation request. Reconnect, replay, and reconcile Jack state rather than inferring that cognition stopped or was cancelled.

## 12. Session replacement

Request replacement only through:

```text
POST /jack/orchestration/session/new
```

Required sequence:

```text
1. GET status
2. Record old sessionInstanceId
3. Require ready + not transitioning
4. POST /session/new through Jack
5. Stop task admission during transition
6. Poll Jack status only
7. Tolerate temporary Jack 502 while the private bridge is replaced
8. Require sessionReady == true
9. Require sessionTransitioning == false
10. Require new sessionInstanceId != old sessionInstanceId
11. Only then submit follow-up work
```

Do not use a fixed sleep as readiness proof and do not contact the private bridge to determine whether replacement succeeded.

## 13. What the supervisor may decide

The supervisor may decide:

- what work to delegate;
- how to decompose the user's objective;
- whether more worker work is needed;
- whether a result should be checked or revised;
- whether cancellation or session replacement is appropriate;
- whether the overall user objective has been satisfied.

These are cognitive/supervisory decisions.

## 14. What the supervisor may not invent

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

Those come from Jack and the worker-control path.

> **Probabilistic cognition may interpret deterministic state. It does not create deterministic state.**

## 15. Direct inference is not worker orchestration

A direct model request such as:

```text
client -> Jack /v1 -> local model
```

is not equivalent to:

```text
supervisor -> Jack /jack/orchestration/tasks -> worker
worker -> Jack /v1 -> local model
```

If the user's intent is to have the privileged worker perform work, submit a worker task and supervise it through Jack's orchestration stream.

## 16. Failure behavior

If Jack reports a deterministic gateway or worker-availability failure:

- report the actual failure;
- do not bypass Jack;
- do not redirect to the private bridge;
- do not redirect worker control to the model backend;
- do not blindly retry ambiguous task submission.

Blind retry can duplicate work. Resolve task state through Jack before submitting another controlled task.

Do not convert recoverable endpoint movement, stale observational status, runtime-activity telemetry degradation, or client transport disconnect into authoritative failure. `/jack/runtime/status` is observability only; degraded telemetry may truthfully report unknown.

## 17. Minimum operating checklist

Before work:

```text
[ ] supervisor mode identified: cloud or local
[ ] Jack reachable on 127.0.0.1:8001
[ ] sessionReady == true
[ ] sessionTransitioning == false
[ ] no prior controlled run physically open
```

During work:

```text
[ ] SSE stream active
[ ] seq retained
[ ] task_id retained
[ ] run_id/run_epoch tracked when bound
[ ] message/tool events observed
[ ] no stale-snapshot guessing
[ ] SSE timeout not treated as worker state
[ ] silence not treated as settlement
```

After work:

```text
[ ] terminal worker state observed
[ ] runOpen == false
[ ] settledAt present where terminal settlement is expected
[ ] tool failures distinguished from overall task result
[ ] user-facing status reflects current authoritative state
```

## 18. Codex Desktop quickstart

Codex Desktop is a reference **cloud-model supervisor**, not an architectural dependency.

Its own cognition remains on OpenAI. Its worker-control path is:

```text
Native Codex / OpenAI
  -> Jack Kernel :8001/jack/orchestration
  -> private Pi bridge
  -> Primary Pi
  -> Jack Kernel :8001/v1
  -> local backend
```

Codex must not use Jack `/v1` as its own model provider in this cloud-supervisor mode.

Example status check from Codex's shell:

```powershell
Invoke-RestMethod `
    http://127.0.0.1:8001/jack/orchestration/status |
    ConvertTo-Json -Depth 20
```

Example task submission:

```powershell
$body = @{
    prompt = "Return exactly: PI_THROUGH_JACK_OK"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri http://127.0.0.1:8001/jack/orchestration/tasks `
    -ContentType "application/json" `
    -Body $body
```

For active work, open and maintain the SSE stream rather than relying on status polling alone.

Recommended standing instruction:

```text
You are a native cloud-model supervisory agent operating a local worker through Jack Kernel.

Keep your own native cloud cognition. All worker supervision and control must go through Jack Kernel at http://127.0.0.1:8001.

Use only Jack's public orchestration routes for worker control. Never contact the private worker bridge, never use its control token, never infer task/run/settlement state from timing, and never bypass Jack.

Check readiness before submission. During active work consume Jack's SSE event stream, retain seq/task_id/run_id/run_epoch/attribution, replay after interruption, and treat the controlled run as physically complete only when authoritative terminal state reports runOpen=false with settlement metadata.
```

## 19. Canonical summary

```text
status     -> readiness and compact lifecycle state
SSE        -> chronological execution history
replay     -> missed transport history recovery
settlement -> physical completion
```

> **Never bypass Jack for worker control. Never bypass Jack for local-model inference. Never replace live event supervision with stale polling. Silence is not settlement.**