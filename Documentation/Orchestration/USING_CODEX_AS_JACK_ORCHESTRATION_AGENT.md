# Using Codex as a Jack Kernel Orchestration Agent

**Jack Kernel version:** v0.1.1  
**Orchestration subsystem:** Orchestration Gateway v2  
**Status:** Live-tested with Codex Desktop  
**Scope:** Codex as a supervisory client for Primary Pi through Jack Kernel

> **Invariant:** Codex may supervise Primary Pi, but the supervisory path must cross Jack Kernel. Codex must not contact the private Pi control bridge directly.

---

## 1. Purpose

Jack Kernel's Orchestration Gateway v2 is client-agnostic. The reference supervisor is Jack Orchestrator, but Codex Desktop can also act as an orchestration agent without modifying Codex and without adding MCP.

If you are adapting another worker or agent runtime to this architecture, first read [`ORCHESTRATE_WITH_CODEX.md`](ORCHESTRATE_WITH_CODEX.md). This guide assumes the worker adapter already implements the required Jack mediation contract.

Codex already has the capabilities required to operate the gateway through its normal local shell/tool surface:

- make HTTP requests;
- open and consume an SSE stream;
- submit work;
- inspect live worker activity;
- cancel work;
- create a new worker session;
- inspect Jack-authoritative model/context metadata.

The required topology is:

```text
                          ┌─────────────────────────────┐
                          │        Jack Kernel          │
                          │         :8001               │
                          └──────────────┬──────────────┘
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 │                                               │
                 │                                               │
        Codex cognition                                  Codex supervision
        /v1/responses                                    /jack/orchestration/*
                 │                                               │
                 ▼                                               ▼
        Jack-selected model                              private Pi bridge :8013
                                                                 │
                                                                 ▼
                                                            Primary Pi
                                                                 │
                                                                 │ model inference
                                                                 ▼
                                                          Jack Kernel /v1
                                                                 │
                                                                 ▼
                                                        Jack-selected model
```

The private Pi bridge remains loopback-only and authenticated. Jack holds the downstream Pi bridge credential. Codex does not need that credential and must not read or use it.

---

## 2. What Codex does — and does not — require

### Codex does not require modification

No Codex source-code changes are required.

No MCP server is required.

No direct connection from Codex to port `8013` is required or permitted.

Codex uses its existing shell/tool capability to call Jack Kernel's public local orchestration API.

### Important security distinction

The reference **Jack Orchestrator** is intentionally execution-restricted and exposes only the five supervisory capabilities defined by the Jack architecture.

Codex Desktop is different: Codex normally has its own local shell/tool capabilities. Using Codex as an orchestration agent therefore does **not** make Codex equivalent to the restricted Jack Orchestrator security profile.

This guide establishes only the worker-control invariant:

> **All Codex control of Primary Pi must cross Jack Kernel's public orchestration gateway.**

It does not claim that Jack intercepts every filesystem, shell, or process action Codex may independently perform through Codex's own local tools.

---

## 3. Required services

Before using Codex as the orchestration agent, start Jack Kernel and Primary Pi.

### Start Jack Kernel

From PowerShell:

```powershell
$repo = "C:\path\to\Jack Kernel"
Set-Location -LiteralPath $repo
.\start.bat
```

Jack's normal local listener is:

```text
127.0.0.1:8001
```

### Start Primary Pi

In a second PowerShell window:

```powershell
$repo = "C:\path\to\Jack Kernel"
Set-Location -LiteralPath (Join-Path $repo "Pi")
pi
```

The private Pi control bridge is expected on:

```text
127.0.0.1:8013
```

Codex must not connect to that port directly.

### Verify both listeners

```powershell
Get-NetTCPConnection -State Listen |
    Where-Object LocalPort -in 8001,8013 |
    Select-Object LocalAddress,LocalPort,OwningProcess
```

---

## 4. Route Codex cognition through Jack Kernel

When the goal is for the complete Codex supervisory workflow to use Jack Kernel, Codex's model provider should point to Jack's Responses-compatible inference surface.

Example Codex configuration:

```toml
model = "jack-kernel"
model_provider = "jack_kernel"

[model_providers.jack_kernel]
name = "Jack Kernel"
base_url = "http://127.0.0.1:8001/v1"
wire_api = "responses"
requires_openai_auth = false
supports_websockets = false
```

With this configuration, Codex cognition goes through:

```text
Codex -> Jack Kernel /v1/responses -> Jack-selected backend/model
```

Primary Pi independently uses Jack for its own model inference.

For simultaneous Codex cognition and Primary-Pi cognition, the live-accepted Jack configuration used:

```text
Maximum concurrent Kernel requests = 2
```

The orchestration SSE transport itself remains outside Jack's inference semaphore.

---

## 5. Public orchestration API used by Codex

Codex should use only these Jack routes for Primary-Pi supervision:

```text
GET  /jack/orchestration/status
GET  /jack/orchestration/events
POST /jack/orchestration/tasks
POST /jack/orchestration/tasks/cancel
POST /jack/orchestration/session/new
```

Jack then communicates privately with the authenticated Pi control bridge.

The task submission wire body is:

```json
{
  "prompt": "..."
}
```

The public API is deliberately separate from the model-facing wording a supervisor may use internally. A supervisor may call the concept an `instruction`; the Jack/Pi task wire contract remains `prompt`.

## 6. Check worker status

From Codex's shell:

```powershell
Invoke-RestMethod `
    http://127.0.0.1:8001/jack/orchestration/status |
    ConvertTo-Json -Depth 20
```

A ready idle worker returns a readiness-bearing snapshot such as:

```json
{
  "status": "idle",
  "sessionReady": true,
  "sessionTransitioning": false,
  "sessionInstanceId": "worker-instance-uuid"
}
```

Do not treat `"status": "idle"` by itself as task-admission authority.

Before submitting controlled work, Codex should require:

```text
sessionReady == true
sessionTransitioning == false
sessionInstanceId is nonempty
```

During or after controlled work, the status snapshot can additionally include:

```json
{
  "id": "task-uuid",
  "status": "running",
  "createdAt": "...",
  "toolErrors": [],
  "final": null,
  "runId": "run-uuid",
  "runEpoch": 1,
  "runOpen": true,
  "sessionReady": true,
  "sessionTransitioning": false,
  "sessionInstanceId": "worker-instance-uuid"
}
```

Status answers both the current controlled-task state and whether the current worker instance is ready to admit controlled work.

It is not a substitute for the event stream.

---

## 7. Read Jack-authoritative model and context information

Codex can inspect Jack's projected model metadata through:

```powershell
Invoke-RestMethod `
    http://127.0.0.1:8001/api/v1/models |
    ConvertTo-Json -Depth 20
```

Jack projects the context length of the backend instance it actually resolved.

A live Codex orchestration test reported:

```text
virtual model:  jack-kernel
backend model:  qwen3.8-27b-gsq-rco
context window: 90,112 tokens
context source: lmstudio_loaded_instance
```

Treat this as authoritative model/context-window metadata.

Do not invent a "tokens remaining" value unless an authoritative source actually provides one.

Completed Pi responses may also include run usage such as input, output, reasoning, and total-token counts. Those usage values describe the completed response; they are not the same thing as the model's maximum context window.

---

## 8. Open the live Pi event stream

For real supervision, Codex should open the SSE stream **before** submitting a task whenever possible:

```powershell
$job = Start-Job -ScriptBlock {
    curl.exe -N -s `
        http://127.0.0.1:8001/jack/orchestration/events
}
```

`curl.exe -N` disables output buffering so the SSE frames are visible as they arrive.

The public stream can include events such as:

```text
task
message
message_end
tool_start
tool_update
tool_end
session
status
```

Jack adds transport/run information including:

```text
seq
task_id
run_id
run_epoch
attribution
type
source
source_at
jack_received_at
data
source_event
```

---

## 9. Submit work to Primary Pi

After the event stream is open:

```powershell
$body = @{
    prompt = "Return exactly: PI_THROUGH_JACK_OK"
} | ConvertTo-Json

$submit = Invoke-RestMethod `
    -Method Post `
    -Uri http://127.0.0.1:8001/jack/orchestration/tasks `
    -ContentType "application/json" `
    -Body $body

$submit | ConvertTo-Json -Depth 20
```

The initial response is normally queued:

```json
{
  "id": "task-uuid",
  "status": "queued",
  "runId": null,
  "runEpoch": null,
  "runOpen": false
}
```

A null `runId` while the task is still queued is expected. Pi has not yet opened the controlled run.

When the matching `agent_start` occurs, the bridge binds the task to a stable `run_id` and `run_epoch`.

---

## 10. Observe the task live

Consume the watcher:

```powershell
Receive-Job -Job $job -Wait
```

A normal controlled run can look conceptually like:

```text
queued
  ↓
running + run_id assigned
  ↓
message / message / tool events ...
  ↓
message_end
  ↓
settling
  ↓
completed
  ↓
runOpen=false + settledAt
```

Codex should track at least:

```text
task_id
run_id
run_epoch
seq
attribution
status
runOpen
settledAt
```

For a live build task it should also inspect:

```text
message
tool_start
tool_update
tool_end
message_end
```

The goal is not merely to receive the final answer. The orchestration agent should be able to observe Primary Pi while the worker is actively reasoning, generating messages, and using tools.

---

## 11. Event ownership rules

Gateway v2 deliberately does not guess event ownership.

Run-bound message/tool events use:

```text
attribution = pi_run_bound
```

Task lifecycle events use:

```text
attribution = task_state
```

Events without positive run evidence remain unowned:

```json
{
  "task_id": null,
  "run_id": null,
  "run_epoch": null,
  "attribution": "none"
}
```

Codex must not assign an unowned event to the current task merely because the timing looks convenient.

The core rule is:

> **Current task is not the same thing as event provenance.**

---

## 12. Completion and settlement rules

Do not treat `message_end` as task completion.

Do not treat `agent_end` as complete physical settlement.

The complete controlled operation closes at Pi's `agent_settled` boundary.

For orchestration purposes, the strongest terminal state is:

```text
status   = completed | failed | cancelled
runOpen  = false
settledAt is present
```

This distinction is especially important after cancellation.

---

## 13. Cancellation

Cancel through Jack only:

```powershell
Invoke-RestMethod `
    -Method Post `
    -Uri http://127.0.0.1:8001/jack/orchestration/tasks/cancel |
    ConvertTo-Json -Depth 20
```

Cancellation is best-effort.

A cancellation response may legitimately show:

```text
status  = cancelled
runOpen = true
```

That means the logical task has been cancelled but the underlying Pi activity has not yet reached physical settlement.

Codex should continue observing the stream until it sees the same run reach:

```text
status    = cancelled
runOpen   = false
settledAt = ...
```

Do not submit another controlled task while the previous control run remains open.

## 14. Start a new Pi session

Session replacement is asynchronous. Do not submit a follow-up task merely because the `/session/new` POST returned.

First query Jack status and require a physically settled worker with:

```text
sessionReady = true
sessionTransitioning = false
sessionInstanceId = A
```

Record the current `sessionInstanceId` as `A`.

Then request the replacement through Jack only:

```powershell
Invoke-RestMethod `
    -Method Post `
    -Uri http://127.0.0.1:8001/jack/orchestration/session/new |
    ConvertTo-Json -Depth 20
```

A successful request begins the transition and returns HTTP `202` with state equivalent to:

```json
{
  "status": "starting",
  "sessionReady": false,
  "sessionTransitioning": true,
  "previousSessionInstanceId": "A"
}
```

The old bridge instance immediately closes task admission. If it is still reachable during transition, a task request fails closed with HTTP `409`:

```json
{
  "error": "Pi session transition in progress",
  "sessionReady": false,
  "sessionTransitioning": true,
  "sessionInstanceId": "A"
}
```

During actual Pi runtime replacement the private bridge listener may temporarily disappear, so Jack may temporarily return HTTP `502`:

```json
{
  "detail": "Pi control bridge is unavailable"
}
```

That transient `502` is not permission to bypass Jack.

Codex must poll only:

```text
GET http://127.0.0.1:8001/jack/orchestration/status
```

until Jack returns a successful status satisfying all of:

```text
sessionReady == true
sessionTransitioning == false
sessionInstanceId = B
B != A
```

Only after the fresh ready instance `B` is confirmed may Codex submit the next controlled task.

Do not use a fixed sleep as proof of readiness. Do not silently retry a task submitted into an ambiguous transition.

---

## 15. SSE sequence and replay

Every Jack orchestration event receives a monotonically increasing process-local `seq`.

The default replay buffer retains:

```text
512 events
```

If Codex disconnects after sequence `42`, reconnect with:

```text
GET /jack/orchestration/events?after=42
```

PowerShell/curl example:

```powershell
curl.exe -N -s `
    "http://127.0.0.1:8001/jack/orchestration/events?after=42"
```

Jack also supports `Last-Event-ID`.

Codex should verify that replayed sequence numbers are strictly increasing and greater than the last sequence it had already processed.

If the requested point has fallen outside the replay window, Jack returns HTTP `409` with:

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

Do not silently treat a replay gap as complete history.

---

## 16. Primary Pi unavailable behavior

If Jack remains alive but Primary Pi is stopped, Codex should expect the orchestration routes to fail deterministically.

The accepted behavior is HTTP `502` with:

```json
{
  "detail": "Pi control bridge is unavailable"
}
```

Outside a deliberate session replacement, Codex must stop, report, or wait.

During a deliberate `/session/new` transition, the same `502` can occur temporarily while the old private listener has closed and the replacement Pi extension has not yet reached `session_start`. In that case Codex should continue polling **Jack only** until the replacement readiness contract is satisfied.

It must **not** bypass Jack and connect directly to the Pi bridge.

## 17. Recommended standing instruction for Codex

The following can be given to Codex when it is expected to act as the Primary-Pi orchestration agent:

```text
You are operating Primary Pi through Jack Kernel.

Primary rule:
All Primary-Pi supervision and control must go through Jack Kernel at
http://127.0.0.1:8001.

Allowed worker-control routes:
GET  /jack/orchestration/status
GET  /jack/orchestration/events
POST /jack/orchestration/tasks
POST /jack/orchestration/tasks/cancel
POST /jack/orchestration/session/new

Model/context metadata:
GET /api/v1/models

Never:
- connect directly to port 8013;
- read or use Pi's private control token;
- create a fallback path around Jack;
- infer event ownership from timing;
- treat message_end as task completion;
- treat logical cancellation as physical settlement;
- infer worker readiness from elapsed time;
- submit controlled work while sessionReady is false;
- submit controlled work while sessionTransitioning is true;
- treat an unchanged sessionInstanceId as proof that session replacement completed.

For supervised work:
1. Check worker status.
2. Require sessionReady=true, sessionTransitioning=false, and a nonempty sessionInstanceId.
3. Read Jack-authoritative model/context metadata when relevant.
4. Open the Jack orchestration SSE stream before task submission when practical.
5. Submit the worker task through Jack.
6. Track seq, task_id, run_id, run_epoch, attribution, message events,
   tool events, task lifecycle, runOpen, and settledAt.
7. On stream interruption, reconnect with ?after=<last_seq>.
8. If Jack reports orchestration_replay_gap, explicitly report the lost interval.
9. Consider the controlled operation physically settled only when the terminal
   task state has runOpen=false and settledAt is populated.
10. Never submit overlapping controlled work against an unsettled prior run.

For a new worker session:
1. Record the current ready sessionInstanceId A.
2. POST /jack/orchestration/session/new through Jack.
3. Do not submit a task while replacement is in progress.
4. A transient Jack 502 is acceptable while the private bridge is replaced.
5. Poll Jack status only.
6. Require sessionReady=true, sessionTransitioning=false, and a new
   sessionInstanceId B where B != A.
7. Only then submit follow-up work.
```

---

## 18. Live Codex validation record

A real Codex Desktop test was performed with Codex using Jack only.

Observed control path:

```text
Codex
  -> Jack Kernel :8001
  -> /jack/orchestration
  -> private Pi bridge
  -> Primary Pi
```

Validated run:

```text
task_id:        8e9670a0-059b-4a70-a0a4-955901b78f37
run_id:         f46736be-22e4-4891-acb5-8207afc3fa1d
run_epoch:      1
first seq:      2
last seq:       17
message events: 10
tool events:    0
terminal state: completed
settledAt:      2026-09-14T01:50:05.972Z
final runOpen:  false
final answer:   PI_CODEX_THROUGH_JACK_OK
context window: 90,112 tokens
```

Observed lifecycle:

```text
seq 2     queued
seq 3     running; run ID assigned
seq 4     message_end
seq 5-14  live message events
seq 15    message_end
seq 16    settling
seq 17    completed
```

The task prohibited tools, so zero tool events were expected.

Codex reported that every control request used `127.0.0.1:8001`, that it never contacted `:8013`, never read Pi credentials, and did not use MCP.

This establishes the essential capability:

> **Codex can supervise and control Primary Pi in real time while the worker-control path remains mediated by Jack Kernel.**

### Live session-replacement regression

The Pi runtime-replacement path was exercised through Codex using Jack only.

```text
initial sessionInstanceId:
5ae06183-6e48-49a9-94c2-27e1e4def184

POST /jack/orchestration/session/new:
HTTP 202
sessionReady: false
sessionTransitioning: true

replacement sessionInstanceId:
828c6ee0-5766-44d4-9b7f-df7ab1b540f4

replacement status:
status: idle
sessionReady: true
sessionTransitioning: false

follow-up task_id:
7afa70c5-e85e-4a3a-a5e5-290969071e7b

run_id:
33416989-b433-48d9-9f4c-b485f9da839f

run_epoch: 1
message events: 10
terminal state: completed
settledAt: 2026-09-14T03:43:02.383Z
final runOpen: false
final answer: PI_NEW_SESSION_THROUGH_JACK_OK
```

The follow-up task was submitted only after Jack reported the replacement instance ready and its `sessionInstanceId` differed from the pre-transition instance. No `Extension runtime not initialized` failure occurred.

Codex reported that all supervision remained on Jack `:8001`; it did not contact `:8013`, read Pi credentials/configuration, use MCP, or modify files.

## 19. Operational checklist

Before starting supervised work:

- Jack Kernel is running on `127.0.0.1:8001`.
- Primary Pi is running.
- Jack status reports `sessionReady: true`.
- Jack status reports `sessionTransitioning: false`.
- Jack status reports a nonempty `sessionInstanceId`.
- Codex cognition is configured through Jack when full Jack mediation is desired.
- Codex does not possess or use Pi's downstream control token.
- Codex uses only Jack's public orchestration routes for Primary-Pi control.
- The SSE watcher is active for work that requires live supervision.
- The last processed `seq` is retained for reconnect/replay.
- Unowned events remain unowned.
- Cancellation is followed through physical settlement.
- A new controlled task is not started while the prior run remains open.
- A requested session replacement is not complete until Jack reports a ready, non-transitioning worker with a `sessionInstanceId` different from the pre-transition instance.
- A transient `502` during deliberate session replacement is handled by polling Jack only; it is never handled by bypassing Jack.

---

## 20. Relationship to Jack Orchestrator

**Jack Orchestrator** remains the reference execution-restricted supervisor architecture documented by Jack Kernel.

**Codex as an orchestration agent** is a practical alternative supervisory client that uses the same Jack Orchestration Gateway v2 transport but retains Codex's normal local tool environment.

Both may use:

```text
Jack Kernel /jack/orchestration
```

to supervise Primary Pi.

They should not be conflated:

```text
Jack Orchestrator
    = reference cognition-only, execution-restricted supervisor

Codex orchestration agent
    = general Codex client using Jack as the mandatory Primary-Pi control boundary
```

The common architectural requirement is:

> **Jack knows the private worker control path. The supervisor uses Jack. The supervisor does not bypass Jack.**
