# Using Codex as a Jack Kernel Orchestration Agent

**Jack Kernel version:** v0.1.1  
**Orchestration subsystem:** Orchestration Gateway v2  
**Status:** Live-tested with Codex Desktop  
**Scope:** Codex as a cloud-model supervisory client for Primary Pi through Jack Kernel

> **Invariant:** Codex retains its native OpenAI cognition. All Codex supervision and control of Primary Pi must cross Jack Kernel. Codex must not contact the private Pi control bridge directly.

---

## 1. Purpose

Jack Kernel's Orchestration Gateway v2 is client-agnostic. Codex Desktop is one practical cloud-model supervisor, but it is not the architectural requirement. Any supervisory agent connected to a cloud model can use the same Jack control plane if it can make equivalent HTTP/SSE requests and preserves the same authority boundary.

Codex is therefore a reference proxy for a broader class of cloud-model agents.

The critical separation is:

- **Codex/OpenAI cognition stays native and cloud-hosted.**
- **Jack governs Codex's control of the local worker.**
- **Primary Pi remains the local privileged build agent.**
- **Primary Pi's model inference runs through Jack `/v1` to the configured local backend.**

The correct topology is:

```text
User
  |
  v
Native Codex / OpenAI model
  |
  | supervision / worker control only
  v
Jack Kernel :8001/jack/orchestration
  |
  v
private Pi bridge :8013
  |
  v
Primary Pi
  |
  | model inference
  v
Jack Kernel :8001/v1
  |
  v
local LLM server / configured backend
```

There is no Codex-cognition lane through Jack `/v1` in this mode.

Jack does not replace Codex's model provider.

This is different from the all-local Jack Orchestrator architecture, where a local cognition-only supervisor and Primary Pi may both infer through Jack against the same local backend, including with multiple concurrent backend slots.

---

## 2. What Codex does — and does not — require

Codex requires no source modification for this architecture.

Codex uses its normal OpenAI model and its existing local shell/tool capability to call Jack Kernel's public orchestration API.

Codex does **not** require:

- Jack configured as Codex's model provider;
- direct connection to port `8013`;
- Pi's private control token;
- Pi's private configuration;
- a fallback path around Jack.

The worker-control invariant is:

> **All Codex control of Primary Pi must cross Jack Kernel's public orchestration gateway.**

Codex may still possess independent local shell/filesystem capabilities of its own. Jack's orchestration contract governs Codex-to-worker control; it does not claim that Jack intercepts every independent action Codex itself can perform.

---

## 3. Required services

Start Jack Kernel and Primary Pi.

### Start Jack Kernel

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

```powershell
$repo = "C:\path\to\Jack Kernel"
Set-Location -LiteralPath (Join-Path $repo "Pi")
pi
```

The private Pi control bridge is expected on:

```text
127.0.0.1:8013
```

Codex must never use that port as its control endpoint.

---

## 4. Public orchestration API used by Codex

Codex should use only these Jack routes for Primary-Pi supervision:

```text
GET  /jack/orchestration/status
GET  /jack/orchestration/events
POST /jack/orchestration/tasks
POST /jack/orchestration/tasks/cancel
POST /jack/orchestration/session/new
```

Jack then communicates privately with the authenticated Pi control bridge.

Task submission uses:

```json
{
  "prompt": "..."
}
```

Codex decides what work should be delegated. Jack deterministically mediates the control operation. Primary Pi performs the local work.

---

## 5. Check worker status

From Codex's shell:

```powershell
Invoke-RestMethod `
    http://127.0.0.1:8001/jack/orchestration/status |
    ConvertTo-Json -Depth 20
```

Before submitting controlled work, require:

```text
sessionReady == true
sessionTransitioning == false
sessionInstanceId is nonempty
```

A task snapshot may additionally contain:

```text
task_id
run_id
run_epoch
status
runOpen
settledAt
```

Status is authoritative control state. It is not a substitute for the event stream when live supervision is required.

---

## 6. Worker model/context metadata

Codex's own model/provider/context are independent of the worker path.

When relevant, Codex may inspect Jack's worker/backend projection through:

```powershell
Invoke-RestMethod `
    http://127.0.0.1:8001/api/v1/models |
    ConvertTo-Json -Depth 20
```

Those values describe the model/backend resolved by Jack for the local worker path. They do not describe Codex's OpenAI model.

Do not invent unknown context or remaining-token values.

---

## 7. Open the live Pi event stream

For live supervision, open the Jack SSE stream before task submission when practical:

```powershell
$job = Start-Job -ScriptBlock {
    curl.exe -N -s `
        http://127.0.0.1:8001/jack/orchestration/events
}
```

The stream can include:

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

Jack adds correlation/transport fields such as:

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
```

Codex should consume Jack's stream, never the private Pi stream.

The SSE endpoint is long-lived. Do not treat it like a finite JSON REST response.

---

## 8. Submit work to Primary Pi

After readiness is confirmed:

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

A queued task may initially have no `runId`. That is expected until Pi produces the positive lifecycle event that binds the worker run.

---

## 9. Observe run identity and tool activity

Gateway v2 does not infer event ownership from timing.

Run-bound worker events use positive run evidence and carry:

```text
task_id
run_id
run_epoch
attribution
```

Tool events should remain observable:

```text
tool_start
tool_update
tool_end
```

Codex can use these events and worker messages as evidence when deciding what instruction to send next.

---

## 10. Completion and physical settlement

Do not treat `message_end` as task completion.

Do not treat `agent_end` as complete physical settlement.

For orchestration purposes, the strongest terminal state is:

```text
status = completed | failed | cancelled
runOpen = false
settledAt is present
```

Do not submit overlapping controlled work against a prior run that remains physically open.

---

## 11. Cancellation

Cancel through Jack only:

```powershell
Invoke-RestMethod `
    -Method Post `
    -Uri http://127.0.0.1:8001/jack/orchestration/tasks/cancel |
    ConvertTo-Json -Depth 20
```

Logical cancellation may occur before physical settlement.

A state such as:

```text
status = cancelled
runOpen = true
```

means the worker is still unwinding. Continue observing until `runOpen=false` and `settledAt` is populated.

---

## 12. New Pi session

Session replacement is asynchronous.

Required sequence:

```text
1. GET Jack orchestration status
2. Record ready sessionInstanceId A
3. POST /jack/orchestration/session/new
4. Do not submit work during transition
5. Poll Jack status only
6. Temporary Jack 502 is acceptable while the private bridge is replaced
7. Require:
      sessionReady = true
      sessionTransitioning = false
      sessionInstanceId = B
      B != A
8. Only then submit follow-up work
```

A fixed sleep is not lifecycle proof.

A transient `502` during deliberate replacement is not permission to bypass Jack.

---

## 13. SSE replay

Jack assigns process-local monotonic sequence numbers and maintains a bounded replay window.

Reconnect after a known sequence with:

```text
GET /jack/orchestration/events?after=<last_seq>
```

If history has fallen outside the replay window, Jack returns an explicit replay-gap failure. Do not silently treat a replay gap as complete history.

---

## 14. Primary Pi unavailable

If Jack remains alive but Primary Pi is unavailable, orchestration routes should fail deterministically, for example:

```json
{
  "detail": "Pi control bridge is unavailable"
}
```

Outside deliberate session replacement, Codex should stop, report, or wait. It must not bypass Jack.

---

## 15. Recommended standing instruction for Codex

```text
You are a native Codex/OpenAI supervisory agent operating Primary Pi through Jack Kernel.

Your own cognition remains on the native OpenAI model. Do not configure Jack Kernel as your model provider.

All Primary-Pi supervision and control must go through Jack Kernel at:
http://127.0.0.1:8001

Allowed worker-control routes:
GET  /jack/orchestration/status
GET  /jack/orchestration/events
POST /jack/orchestration/tasks
POST /jack/orchestration/tasks/cancel
POST /jack/orchestration/session/new

Worker model/context metadata, when relevant:
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
3. Open the Jack orchestration SSE stream before task submission when practical.
4. Submit the worker task through Jack.
5. Track seq, task_id, run_id, run_epoch, attribution, message events, tool events, task lifecycle, runOpen, and settledAt.
6. On interruption, reconnect with ?after=<last_seq>.
7. Consider the controlled operation physically settled only when terminal state has runOpen=false and settledAt is populated.
8. Never submit overlapping controlled work against an unsettled prior run.
```

---

## 16. What the validated Codex path proves

The intended Codex control path is:

```text
Native Codex / OpenAI
  -> Jack Kernel :8001/jack/orchestration
  -> private Pi bridge
  -> Primary Pi
```

Primary Pi's inference path is separately:

```text
Primary Pi
  -> Jack Kernel :8001/v1
  -> local LLM backend
```

Together these establish the intended capability:

> **A cloud-model agent can supervise and control a local privileged worker in real time while worker control remains mediated by Jack Kernel and worker inference remains local through Jack.**

Codex is the current reference implementation of that cloud-supervisor role, not the architectural limit.

---

## 17. Relationship to Jack Orchestrator

Do not conflate the two deployment modes.

### All-local Jack Orchestrator mode

```text
Jack Orchestrator
  -> Jack /v1 -> local backend       [supervisor cognition]
  -> Jack /jack/orchestration -> Pi  [worker control]

Primary Pi
  -> Jack /v1 -> local backend       [worker cognition]
```

This mode can use multiple local backend concurrency slots so supervisor and worker cognition run through the same Jack/local-model infrastructure.

### Cloud-supervisor mode

```text
Cloud-model supervisor
  -> native cloud model              [supervisor cognition]
  -> Jack /jack/orchestration -> Pi  [worker control]

Primary Pi
  -> Jack /v1 -> local backend       [worker cognition]
```

Codex Desktop is one example of the cloud-model supervisor.

The common invariant is:

> **Jack knows the private worker control path. The supervisor uses Jack. The supervisor does not bypass Jack.**

---

## 18. Generalizing beyond Codex

Any cloud-model agent may fill the supervisory role if it can:

- preserve its own native cloud cognition;
- call Jack's public orchestration API;
- consume worker status/events/results;
- maintain task/run correlation;
- obey Jack's readiness, settlement, replay, and isolation contracts;
- avoid direct access to the private worker bridge.

The architecture is therefore not "Codex connected to Jack's model API."

It is:

```text
cloud-model intelligence
        ↓ supervision
Jack deterministic control boundary
        ↓
local privileged agent
        ↓ local inference through Jack
local model/backend
```

That is the intended cloud-to-local orchestration pattern.