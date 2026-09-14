# Orchestrate with Codex

## Purpose

This document explains how to adapt an existing local agent runtime—such as Pi Agent—so that Codex can supervise and operate it through Jack Kernel without bypassing Jack’s deterministic control boundary.

For the operator-facing procedure after the worker adapter is installed, see [`USING_CODEX_AS_JACK_ORCHESTRATION_AGENT.md`](USING_CODEX_AS_JACK_ORCHESTRATION_AGENT.md).

The important distinction is architectural:

- **Codex is the supervising agent.**
- **Pi, or another local agent, is the worker.**
- **Jack Kernel is the mandatory mediation layer.**

Codex should never need direct access to the worker’s private control port, credentials, session files, or internal runtime objects. The worker must expose a deterministic control surface that Jack can own, normalize, and relay.

The resulting topology is:

```text
Codex
   │
   ├── cognition / model API
   │      └── Jack Kernel :8001/v1
   │
   └── orchestration / worker control
          └── Jack Kernel :8001/jack/orchestration
                 └── private worker bridge
                        └── Pi Agent or another local agent
```

For the reference Pi integration, the private worker bridge is local-only and is not a Codex endpoint.

---

## 1. What must change in an existing agent

A worker such as Pi does not need to become “Codex-aware.” It needs a small deterministic control adapter that exposes the worker’s existing runtime capabilities in a form Jack can safely mediate.

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

### Reference control surface

A Pi-like bridge can expose:

```text
GET  /v1/status
GET  /v1/events
POST /v1/tasks
POST /v1/tasks/cancel
POST /v1/session/new
```

The bridge should bind only to localhost or another private interface trusted by Jack.

Codex should not call these endpoints directly.

---

## 2. Do not modify Codex to understand the worker

Codex does not need custom Pi-specific code.

Codex only needs:

- an OpenAI-compatible model endpoint for cognition; and
- ordinary HTTP/SSE capability for orchestration through Jack.

For Jack Kernel, Codex can use a normal Responses API provider configuration:

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

This means Codex talks to Jack as its model provider.

The separate orchestration API remains under:

```text
http://127.0.0.1:8001/jack/orchestration
```

No Codex source modification is required for the reference architecture.

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

This distinction matters because logical cancellation and physical settlement are not the same event.

---

## 4. Separate task identity from run identity

A submitted task and a concrete model execution are not the same object.

Use separate identifiers:

```text
task_id
run_id
run_epoch
```

### task_id

The stable control request created when the supervisor submits work.

### run_id

The concrete worker/model execution bound when the agent actually begins running.

### run_epoch

A monotonically increasing execution generation inside the same controlled task when the worker legitimately re-enters inference.

A task must not be treated as run-bound merely because it is currently the active task.

Bind ownership only when the worker produces a positive lifecycle event proving that a real run has started.

For Pi, the useful binding point is `agent_start`.

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

Each event should carry enough correlation information to determine whether it is:

- bound to a concrete worker run,
- a task-state event,
- or unowned.

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

This prevents delayed callbacks from being falsely attributed to a completed task.

---

## 6. Expose live events over SSE

Server-Sent Events are sufficient for this control path.

Example:

```text
GET /v1/events
```

The bridge can emit:

```text
event: message
data: {...}

event: tool_start
data: {...}

event: task_state
data: {...}
```

Jack should maintain the external replay sequence.

A useful Jack-side event envelope is:

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

The supervisor should consume Jack’s SSE stream, not the private worker stream.

---

## 7. Session replacement requires an explicit readiness contract

This is one of the most important changes required for Pi-like agents.

A worker may destroy and rebuild its extension/runtime objects when a new session is created.

If the bridge begins listening before the worker has rebound its runtime action methods, a supervisor can submit work into a control plane that exists at the HTTP level but is not operational internally.

That is a real lifecycle race.

### Required readiness state

Expose:

```text
sessionReady
sessionTransitioning
sessionInstanceId
```

Normal ready state:

```json
{
  "status": "idle",
  "sessionReady": true,
  "sessionTransitioning": false,
  "sessionInstanceId": "5ae06183-6e48-49a9-94c2-27e1e4def184"
}
```

When session replacement starts:

```json
{
  "status": "starting",
  "sessionReady": false,
  "sessionTransitioning": true,
  "previousSessionInstanceId": "5ae06183-6e48-49a9-94c2-27e1e4def184"
}
```

After the new runtime has been created and rebound:

```json
{
  "status": "idle",
  "sessionReady": true,
  "sessionTransitioning": false,
  "sessionInstanceId": "828c6ee0-5766-44d4-9b7f-df7ab1b540f4"
}
```

The new `sessionInstanceId` must differ from the old one.

### Admission rule

A task must not be admitted unless:

```text
sessionReady == true
AND
sessionTransitioning == false
```

If a request reaches the old worker instance during transition, fail closed:

```http
409 Conflict
```

Example:

```json
{
  "error": "Pi session transition in progress",
  "sessionReady": false,
  "sessionTransitioning": true,
  "sessionInstanceId": "…"
}
```

Do not hide this race with a sleep.

Do not automatically retry the task.

Do not silently queue the task across runtime replacement.

The supervisor should wait for a fresh ready worker instance.

---

## 8. Start long-lived worker resources at the correct lifecycle boundary

For Pi specifically, the HTTP bridge must not start its listener from the extension factory while Pi is still loading the extension.

Instead:

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

On session shutdown:

```text
sessionReady = false
sessionTransitioning = true
        ↓
close SSE clients
        ↓
close private HTTP listener
        ↓
old extension instance disappears
```

The replacement extension then creates a new `sessionInstanceId` and repeats the startup lifecycle.

This is the correct boundary because the bridge should not advertise operational readiness before the worker’s action runtime actually exists.

---

## 9. Jack must remain the only orchestration gateway visible to Codex

Jack exposes the worker through:

```text
GET  /jack/orchestration/status
GET  /jack/orchestration/events
POST /jack/orchestration/tasks
POST /jack/orchestration/tasks/cancel
POST /jack/orchestration/session/new
```

Jack forwards these requests to the private worker bridge.

Codex should never be given:

- the worker bridge token;
- the worker bridge private configuration;
- the worker bridge port as an orchestration target;
- permission to read the worker’s control credentials.

If the private bridge is unavailable, Jack should fail deterministically.

Example:

```http
502 Bad Gateway
```

```json
{
  "detail": "Pi control bridge is unavailable"
}
```

There should be no hidden direct fallback from Codex to the worker.

---

## 10. Jack should own external event replay

The private worker bridge only needs to produce authoritative source events.

Jack can provide the supervisor-facing replay layer.

Useful properties:

- process-local monotonic `seq`;
- bounded replay buffer;
- `Last-Event-ID`;
- optional `?after=<seq>`;
- explicit replay-gap failure when requested history has been retired.

For example:

```text
409 orchestration_replay_gap
```

This lets Codex reconnect without forcing the worker to implement the complete external replay protocol itself.

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

Jack should not admit a new controlled task merely because logical cancellation was acknowledged.

The prior worker run must be physically settled first.

---

## 12. Tool events should remain observable

If the worker can use tools, Codex should be able to observe the worker’s tool lifecycle through Jack.

Useful events are:

```text
tool_start
tool_update
tool_end
```

`tool_update` can be optional.

A real tool call should preserve the same task/run/epoch correlation as the surrounding worker execution.

The bridge should report the tool event; it should not reinterpret the tool result.

---

## 13. Worker context metadata should come from the runtime

Do not invent context size or remaining-token data.

If the worker runtime exposes authoritative model/context metadata, retrieve it from the runtime.

For the Pi reference adapter, model/context metadata can be obtained through Jack’s normal model surface when available.

A supervisor can use authoritative fields such as:

```text
model
context_length
max_context_length
```

Unknown values should remain unknown.

---

## 14. Minimal Pi-style bridge implementation pattern

The following is illustrative pseudocode, not a drop-in implementation:

```javascript
export default async function install(pi) {
  const sessionInstanceId = randomUUID();

  let sessionReady = false;
  let sessionTransitioning = false;
  let serverListening = false;

  function statusSnapshot() {
    return {
      ...currentTaskState(),
      sessionReady,
      sessionTransitioning,
      sessionInstanceId,
    };
  }

  async function ensureServerListening() {
    if (serverListening) return;

    await listen();
    serverListening = true;
  }

  pi.on("session_start", async () => {
    sessionTransitioning = false;

    // Runtime actions are now bound.
    await ensureServerListening();

    sessionReady = true;
  });

  pi.on("session_shutdown", async () => {
    sessionReady = false;
    sessionTransitioning = true;

    await closeClients();
    await closeServer();

    serverListening = false;
  });

  // POST /v1/tasks
  async function submitTask(req, res) {
    if (!sessionReady || sessionTransitioning) {
      return conflict(res, "Pi session transition in progress");
    }

    if (priorRunStillOpen()) {
      return conflict(res, "prior run not yet settled");
    }

    // Create task_id.
    // Dispatch to Pi.
    // Bind run_id only on positive agent_start.
  }

  // POST /v1/session/new
  async function newSession(req, res) {
    if (!sessionReady || sessionTransitioning) {
      return conflict(res, "Pi session transition in progress");
    }

    if (!workerIsIdle()) {
      return conflict(res, "Pi is not idle");
    }

    sessionReady = false;
    sessionTransitioning = true;

    triggerNewSession();

    return accepted(res, {
      status: "starting",
      sessionReady: false,
      sessionTransitioning: true,
      previousSessionInstanceId: sessionInstanceId,
    });
  }
}
```

The important point is not the language or framework.

The important point is the control contract.

---

## 15. How Codex should perform a new-session handoff

Codex should follow this sequence:

```text
1. GET Jack orchestration status
2. Record current sessionInstanceId
3. Require ready + not transitioning
4. POST Jack /session/new
5. Poll Jack status only
6. Temporary Jack 502 is acceptable while worker bridge is being replaced
7. Wait for:
      sessionReady = true
      sessionTransitioning = false
      new sessionInstanceId != old sessionInstanceId
8. Only then submit the next task
```

Codex must not use elapsed time as proof of readiness.

A fixed `sleep(2)` is not a lifecycle guarantee.

---

## 16. Codex task flow

Once a worker instance is ready:

```text
Codex
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
message/tool events stream back
  ↓
agent_end
  ↓
agent_settled
  ↓
runOpen = false
```

Codex should use Jack’s SSE stream to observe the execution.

---

## 17. Security boundary

The orchestration design should preserve these rules:

### Codex may know

- Jack’s public local address;
- Jack orchestration routes;
- public task/run state;
- public worker events;
- readiness state;
- worker model/context metadata exposed by Jack.

### Codex should not know

- private worker control token;
- private worker credential files;
- private worker port as an allowed direct control route;
- internal runtime references;
- secrets required only for Jack-to-worker communication.

This gives Codex practical worker control without making the worker directly exposed to the supervising model.

---

## 18. What not to do

Do not implement any of the following:

### Direct Codex → Pi control

```text
Codex → :8013 → Pi
```

This bypasses Jack.

### Sleep-based readiness

```text
/new
sleep 2
submit task
```

This is timing speculation, not lifecycle proof.

### HTTP-listening-before-runtime-ready

Starting the control server while the extension is still loading can expose action methods before they have been initialized.

### Task ownership by assumption

Do not assign a task ID to every event just because that task happens to be current.

### Retry after ambiguous failure

A failed dispatch may already have partially entered the worker.

Blind retry can duplicate work.

### Treat cancellation as settlement

`cancelled` does not imply `runOpen == false`.

### Let the model invent control state

Task IDs, run IDs, event ownership, settlement, readiness, and evidence provenance must come from deterministic software.

---

## 19. Validation checklist

Before declaring a worker compatible with Codex through Jack, test all of the following.

### Startup

- Bridge does not listen before worker runtime initialization is complete.
- Status reports `sessionReady: true`.
- Status reports `sessionTransitioning: false`.
- Status reports a nonempty `sessionInstanceId`.

### Task execution

- Task receives a stable `task_id`.
- Real worker execution receives a non-null `run_id`.
- `run_epoch` is established.
- Live message events are visible.
- Tool events are visible when tools are used.
- Final task state is authoritative.
- Physical settlement produces `runOpen: false`.

### Cancellation

- Logical cancellation can be observed before physical settlement.
- New work is blocked while the cancelled run is still open.
- Final cancelled state has `runOpen: false`.

### Session replacement

- Old `sessionInstanceId` is recorded.
- `/session/new` returns asynchronous transition state.
- Task admission closes immediately.
- Old bridge shuts down.
- New bridge starts only after the worker runtime is rebound.
- New `sessionInstanceId` differs from the old one.
- Follow-up work is submitted only after ready state is confirmed.

### Isolation

- Codex never contacts the private worker bridge directly.
- Codex never reads the worker control token.
- Codex never reads private worker control configuration.
- Jack returns deterministic failure when the private bridge is unavailable.

### Replay

- SSE sequence is monotonic.
- reconnect/replay works;
- stale replay requests fail explicitly.

---

## 20. Proven reference behavior

The Pi reference integration has demonstrated the following live flow:

```text
initial session:
5ae06183-6e48-49a9-94c2-27e1e4def184

POST /jack/orchestration/session/new
→ 202 Accepted
→ sessionReady: false
→ sessionTransitioning: true

replacement session:
828c6ee0-5766-44d4-9b7f-df7ab1b540f4
→ status: idle
→ sessionReady: true
→ sessionTransitioning: false

follow-up task:
task_id: 7afa70c5-e85e-4a3a-a5e5-290969071e7b
run_id: 33416989-b433-48d9-9f4c-b485f9da839f
run_epoch: 1
message events: 10
terminal status: completed
runOpen: false
final: PI_NEW_SESSION_THROUGH_JACK_OK
```

The follow-up task was not submitted until the replacement worker instance was explicitly ready.

This is the behavior an adapter for another Pi-like agent should reproduce.

---

## 21. Generalizing beyond Pi

Pi is only the reference worker.

The same pattern applies to another local agent if it can expose equivalent deterministic lifecycle signals.

Map that agent’s native concepts onto:

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

The adapter should translate the worker’s native lifecycle into this control contract without fabricating information.

Jack can then provide Codex with one stable orchestration protocol regardless of the underlying worker.

---

## 22. Core rule

The orchestration design follows the same rule as the rest of Jack Kernel:

> **Probabilistic cognition may propose, but deterministic software must dispose.**

Codex may decide what work should be done.

The worker model may reason about how to do it.

But task admission, session readiness, run ownership, cancellation, settlement, replay, evidence, and authority must remain deterministic software state.

That is what makes a Pi-like worker safe and reliable to orchestrate with Codex.
