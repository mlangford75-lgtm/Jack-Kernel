# Jack Kernel Orchestration Gateway v2
## Run-Bound Supervisory Transport for Jack Kernel

**Status:** live-accepted Gateway v2 transport specification
**Date:** 2026-09-12
**Scope:** orchestration transport only

## 1. Purpose

Jack Kernel Orchestration Gateway v1 established the control path:

`Supervisor -> Jack Kernel -> Pi Control Bridge -> Privileged Pi Build Agent`

The live v1 tests established four important facts:

1. Jack can proxy status, task submission, cancellation, new-session requests, and Pi SSE events.
2. The supervisor can remain on Jack's public orchestration surface without reading Pi's downstream control token or contacting Pi's private bridge port.
3. When Pi is unavailable, Jack can fail with a gateway error and the supervisor can stop rather than bypass Jack.
4. Pi can continue using Jack for model inference while the orchestration SSE stream is open.

A subsequent instrumented timing run also showed that the apparent ~40-second completion delay was not in Jack, Pi settlement, LM Studio, or Codex completion recognition. The measured `message_end -> settling -> completed` path was effectively immediate. The real v2 problem is therefore **event identity and continuity**, not completion speed.

The v1 stream could expose `message`, `message_end`, and tool events without a task identifier. One observed `message_end` arrived before the first assistant `message` update for a newly submitted task. Pi's documented event model explains why this can happen: `message_end` is emitted for user messages as well as assistant messages. More importantly, a supervisor must never decide that an event belongs to a task merely because that task happens to be current when the event is observed.

Gateway v2 therefore establishes this invariant:

> **A task-associated event receives a task identity only when the Pi control path has positive run-bound evidence that the event originates from that controlled run. Otherwise its task identity is null.**

This corrects the first v2 draft, which derived attribution from the currently active controlled task. Current-task lookup is not run identity and is not sufficient for autonomous supervision.

---

## 2. System roles

### 2.1 Privileged Pi build agent

The user's existing Pi instance remains the privileged worker. It owns its normal build/tool capabilities and continues to reach the model through Jack Kernel.

Conceptually:

`Primary Pi -> Jack inference API -> local model backend`

The primary Pi's private control bridge remains loopback-only and authenticated. Jack holds the downstream bridge credential. The supervisor does not.

### 2.2 Jack Kernel

Jack is the mandatory supervisory control intermediary. It exposes:

- `GET /jack/orchestration/status`
- `GET /jack/orchestration/events`
- `POST /jack/orchestration/tasks`
- `POST /jack/orchestration/tasks/cancel`
- `POST /jack/orchestration/session/new`

The orchestration SSE path remains outside Jack's inference semaphore so an open supervisory stream cannot deadlock `Pi -> Jack -> model` inference.

### 2.3 Supervisory client

Gateway v2 is client-agnostic. The accepted reference supervisor architecture is a separate local Pi-derived process named **Jack Orchestrator**. Jack Orchestrator uses Jack for both cognition (`/v1`) and supervision (`/jack/orchestration`) while remaining intentionally execution-restricted: exactly five model-facing supervisory tools, no direct filesystem/shell/process tools, no direct backend endpoint, no private bridge access, and no Pi `controlToken`.

This package implements the Gateway/Primary-Pi side of that architecture. Any supervisor using the gateway must preserve the same boundary: public Jack orchestration only, no bypass to the private Pi bridge.

---

## 3. Exact Pi 0.84.2 lifecycle facts used by v2

This build targets the user's installed Pi `0.84.2` behavior rather than assuming a hypothetical native run-ID field.

The Pi 0.84.2 extension documentation establishes the relevant ordering:

`input -> before_agent_start -> agent_start -> message/tool events -> agent_end -> agent_settled`

It also states that:

- `input.event.source` distinguishes `"extension"` input created through `pi.sendUserMessage()` from interactive and RPC input;
- `before_agent_start` occurs after the submitted prompt is accepted and before the agent loop begins;
- `agent_start` begins a low-level run;
- `agent_end` ends that low-level run;
- Pi may still retry, auto-compact/retry, or continue queued follow-ups after `agent_end`;
- `agent_settled` is the status boundary after automatic retry/compaction/follow-up activity has finished;
- `message_end` occurs for user, assistant, and tool-result messages, not only assistant responses.

The 0.84.2 extension event schema does **not** provide a universal native `run_id` on every message/tool callback. v2 therefore does not pretend that one exists.

Reference: `https://github.com/earendil-works/pi/blob/v0.84.2/packages/coding-agent/docs/extensions.md`

---

## 4. Corrected run-correlation mechanism

### 4.1 Why current-task attribution is rejected

The following design is invalid:

```text
event arrives
    -> read controlledTask.id
    -> stamp event with that ID
```

That answers only "which task is current now?" It does not answer "which run generated this event?"

If a stale, delayed, unrelated, or post-run event is observed after task state changes, current-task lookup can misattribute it.

### 4.2 Private dispatch correlation

When Jack forwards `POST /tasks` to the Pi control bridge, the bridge creates:

- a controlled `task_id`;
- a separate cryptographically random `run_id` correlation value;
- a private correlation marker prepended to the user message passed to `pi.sendUserMessage()`.

The marker is bridge-private transport metadata. It is not intended to become model context.

Conceptually:

```text
wire input = PRIVATE_RUN_MARKER(run_id) + exact user prompt
```

### 4.3 Input-bound stripping

The bridge subscribes to Pi's `input` event.

A controlled dispatch is recognized only when all of the following hold:

- `event.source == "extension"`;
- the raw input contains the exact private marker for the pending dispatch;
- the marker's `run_id` matches the bridge's pending dispatch record.

The bridge then returns Pi's documented input transformation result so the private marker is removed **before skill/template expansion and before the prompt enters the model-visible agent flow**.

The exact visible prompt remains the user's original prompt.

This gives the bridge positive evidence that the particular Pi prompt flow now entering `before_agent_start` is the one created for the controlled task. Two identical visible prompts no longer collide because their private run markers are different.

### 4.4 Run binding

The binding then advances through Pi's documented lifecycle:

```text
POST /tasks accepted
      |
      v
pending dispatch {task_id, run_id}
      |
      | exact private marker observed on source="extension" input
      v
input-bound correlation
      |
      v
before_agent_start
      |
      v
agent_start
      |
      +--> active low-level run epoch
```

At `agent_start`, the bridge freezes an immutable correlation record:

```json
{
  "taskId": "...",
  "runId": "...",
  "runEpoch": 1
}
```

Every message/tool handler snapshots that active run binding at callback entry. It does **not** look up whichever task happens to be current later.

### 4.5 Low-level run epochs

A controlled task may span more than one low-level Pi run because Pi can retry or continue after `agent_end` before `agent_settled`.

The task therefore owns one stable `run_id` across the complete controlled operation, while each low-level `agent_start..agent_end` segment receives an incrementing `run_epoch`:

```text
run_id = R
  epoch 1: agent_start ... agent_end
  epoch 2: retry agent_start ... agent_end
  epoch 3: continuation agent_start ... agent_end
  ...
agent_settled closes R
```

This lets the supervisor distinguish one controlled task from its individual low-level retry/continuation epochs without inventing a Pi-native identifier that Pi 0.84.2 does not expose.

### 4.6 Clearing at agent_end

`activeRun` is cleared immediately at `agent_end`.

That rule is critical.

An event observed after `agent_end` but before a later retry `agent_start` does not inherit the task ID just because the higher-level controlled task remains in `settling`.

Such an event is emitted as unowned unless a new run epoch has been positively opened.

### 4.7 Closing at agent_settled

`agent_settled` closes the complete control-run correlation. The accepted bridge first captures the settled run identity, then clears `controlRun` and `activeRun`, and only then emits the terminal task snapshot. This ordering is intentional: a terminal snapshot carrying `settledAt` must report `runOpen:false`; it must not preserve stale live-run authority in its public state.

This preserves the existing distinction:

```text
message_end != task complete
agent_end   != task complete
agent_settled -> controlled task terminalization
```

---

## 5. Pi source event contract

Task-associated Pi wrappers now use this structure:

```json
{
  "type": "message_end",
  "task_id": "1330ab9d-af03-4752-89ce-d1bef5b77bba",
  "run_id": "56bb3277-e89d-4e20-9b9e-fb8d624fbf04",
  "run_epoch": 1,
  "attribution": "pi_run_bound",
  "data": {
    "message": {
      "role": "assistant",
      "content": "Hi"
    }
  },
  "at": "2026-09-12T08:44:20.132Z"
}
```

The meanings are:

- `task_id` â€” controlled task identity;
- `run_id` â€” bridge-generated immutable correlation identity for the complete controlled operation;
- `run_epoch` â€” low-level Pi run number inside that control run;
- `attribution: "pi_run_bound"` â€” event ownership came from an open run binding, not current-task inference;
- `data` â€” original Pi callback payload;
- `at` â€” Pi bridge emission time.

Task lifecycle wrappers use `attribution: "task_state"` because their task identity is intrinsic to the task snapshot itself.

Events lacking positive run/task evidence carry:

```json
{
  "task_id": null,
  "run_id": null,
  "run_epoch": null,
  "attribution": "none"
}
```

Jack must preserve those nulls. It must not repair them by guessing.

---

## 6. Task snapshots

Pi status/task snapshots retain the v1 fields and add run-observability fields:

```json
{
  "id": "...",
  "status": "running",
  "createdAt": "...",
  "toolErrors": [],
  "final": null,
  "runId": "...",
  "runEpoch": 1,
  "runOpen": true
}
```

`runOpen` means the controlled operation still has live run correlation even if the task was already marked `cancelled` by a best-effort cancellation request.

When the underlying Pi activity actually reaches `agent_settled`, `runOpen` becomes false and `settledAt` is recorded.

This matters because cancellation remains best-effort. A cancellation response does not prove the underlying model/tool activity has physically stopped at that exact instant.

---

## 7. Cancellation and overlap

v1 cancellation immediately marked the task `cancelled`. v2 preserves that visible semantic but tightens only the overlap behavior required for correct attribution.

A new controlled task is not accepted while a previous control run remains un-settled, even if the previous task has already been marked `cancelled`.

Reason:

```text
cancel requested
    -> underlying Pi abort is best-effort
    -> old run may still emit callbacks briefly
    -> accepting task B before old run settles would reintroduce attribution overlap
```

Therefore:

> **terminal task state and run settlement are distinct facts.**

A queued controlled task that is cancelled before Pi consumes its private marked input is swallowed by the bridge's `input` handler. The marker is never forwarded to the model and no controlled run is opened for that cancelled task.

This is a correctness fix for correlation, not a new general task-content policy.

---

## 8. Jack v2 event envelope

Jack operates one downstream Pi SSE ingestion stream and adds transport identity without rewriting Pi's evidence.

Example:

```json
{
  "seq": 184,
  "task_id": "1330ab9d-af03-4752-89ce-d1bef5b77bba",
  "run_id": "56bb3277-e89d-4e20-9b9e-fb8d624fbf04",
  "run_epoch": 1,
  "attribution": "pi_run_bound",
  "type": "message_end",
  "source": "pi",
  "source_at": "2026-09-12T08:44:20.132Z",
  "jack_received_at": "2026-09-12T08:44:20.133Z",
  "data": {
    "message": {
      "role": "assistant",
      "content": "Hi"
    }
  },
  "source_event": {
    "type": "message_end",
    "task_id": "1330ab9d-af03-4752-89ce-d1bef5b77bba",
    "run_id": "56bb3277-e89d-4e20-9b9e-fb8d624fbf04",
    "run_epoch": 1,
    "attribution": "pi_run_bound",
    "data": {
      "message": {
        "role": "assistant",
        "content": "Hi"
      }
    },
    "at": "2026-09-12T08:44:20.132Z"
  }
}
```

Jack adds:

- `seq` â€” strictly increasing process-local orchestration sequence;
- `source` â€” `"pi"`;
- `jack_received_at` â€” Jack ingress timestamp.

Jack promotes Pi's source identity fields for convenient supervisor access while retaining the complete parsed `source_event`.

The principle remains:

> **Normalize transport identity; preserve source evidence.**

---

## 9. Sequence and replay

Every Jack orchestration event receives a monotonically increasing `seq` and enters a bounded in-memory replay buffer.

Default:

`512 events`

Optional test override:

`JACK_ORCHESTRATION_REPLAY_EVENTS`

Reconnect can request retained events after a known sequence using either:

- `Last-Event-ID: <seq>`
- `GET /jack/orchestration/events?after=<seq>`

If the requested sequence is older than the retained window, Jack returns HTTP `409` with `orchestration_replay_gap` plus the oldest and latest retained sequence numbers.

Jack does not silently pretend that an incomplete stream is complete.

The replay buffer is short-lived transport recovery state, not durable forensic memory.

---

## 10. Status and event history answer different questions

`GET /jack/orchestration/status` answers:

> What is the current controlled-task state?

`GET /jack/orchestration/events` answers:

> What happened, in what order, and which run produced it?

A current status of `completed` does not prove that an observer received every tool or message event. Sequence/replay exists so the supervisor can distinguish absence from loss.

---

## 11. Failure behavior

The mandatory control path remains:

`Supervisor -> Jack -> Pi`

The supervisor must not:

- contact Pi port `8013` directly;
- read Pi's `controlToken`;
- read the worker's Pi credential/config file for downstream access;
- create a fallback path around Jack.

If Pi is unavailable, Jack returns a gateway failure and the supervisor stops/reports/waits.

No direct-Pi fallback is introduced by v2.

---


---

## 12. Non-goals

Gateway v2 does not add or redesign:

- Jack Agentic, Deep Research, or Code Debugging inference programs;
- Jack XML semantics;
- backend/model selection;
- model reasoning policy;
- filesystem sandboxing for the privileged worker;
- universal task-content policy;
- a new inference routing algorithm for the supervisor; Jack Orchestrator uses the existing Jack `/v1` surface;
- a new concurrency scheduler; simultaneous supervisor/worker inference uses Jack's existing `max_concurrent_requests` configuration;
- direct interception of every privileged filesystem/shell/process consequence inside Primary Pi.

Those are separate engineering boundaries.

---

## 13. Acceptance boundary â€” completed

Gateway v2 live acceptance is complete. The accepted system proved all of the following on the user's local Windows runtime:

1. Jack Orchestrator isolation/no-direct-backend/no-direct-private-bridge boundary.
2. Dynamic supervisor context-window projection through Jack.
3. Exactly five model-facing supervisory tools.
4. Semantic `instruction` -> wire `prompt` adapter correctness.
5. Controlled task dispatch through Jack.
6. Run-bound task ID, run ID, epoch, and `pi_run_bound` attribution.
7. Post-`agent_end` unowned events remain unowned.
8. `agent_settled` closes the complete control run.
9. Direct Jack concurrency with `Maximum concurrent Kernel requests = 2` produced simultaneous physical backend inference.
10. Full topology concurrency produced simultaneous Jack Orchestrator and Primary Pi inference through Jack, confirmed by overlapping LM Studio slots.
11. Normal disconnect/reconnect replay returned every retained missed event in strictly increasing sequence order with no duplicates.
12. The default replay window retained exactly 512 events; stale replay returned HTTP `409` with `orchestration_replay_gap`.
13. Cancellation immediately exposed terminal `cancelled` state while the physical run could remain open briefly.
14. No new controlled task was admitted before the cancelled run settled.
15. The accepted terminal settlement event carries the same run identity, `settledAt`, and `runOpen:false`.
16. Normal controlled admission works again after settlement.
17. With Primary Pi stopped and Jack still alive, status/task/cancel/new-session orchestration operations failed deterministically with HTTP `502` and `{"detail":"Pi control bridge is unavailable"}`.
18. No fabricated worker task and no fallback around Jack were observed.

The accepted Primary-Pi control bridge SHA-256 is:

`D066FA2F9B8A3735A60F57F028087F314F484B28DBD10640FB3D64A4FA29C664`

The live evidence is summarized in `ORCHESTRATION_GATEWAY_V2_ACCEPTANCE_REPORT.md`.

---

## 14. Accepted implementation sequence

The final accepted sequence was:

```text
v1 proven gateway
   -> private dispatch/run correlation at Pi input boundary
   -> run binding at before_agent_start / agent_start
   -> clear low-level attribution at agent_end
   -> close control run at agent_settled
   -> Pi wrappers carry task_id + run_id + run_epoch
   -> Jack preserves/promotes identity
   -> Jack adds seq + timestamps + bounded replay
   -> adapter correction (instruction -> prompt)
   -> run-bound live acceptance
   -> correct launcher concurrency configuration
   -> physical direct + full-topology concurrency acceptance
   -> replay + replay-gap acceptance
   -> cancellation acceptance
   -> terminal settlement-snapshot ordering correction
   -> cancellation closure regression acceptance
   -> Primary-Pi-unavailable deterministic failure acceptance
   -> freeze Gateway v2
```

The final settlement ordering correction is a correctness repair, not a policy expansion: control-run authority is cleared before the terminal task snapshot is emitted.

---

## 15. Architectural meaning

Gateway v1 proved:

> **The supervisor can reach the worker through Jack.**

The accepted Gateway v2 proves:

> **The supervisor can determine which controlled run produced an observed event without borrowing identity from mutable current-task state.**

That run-bound, replayable boundary is the minimum reliable transaction substrate used by the accepted supervisory architecture. Jack Orchestrator remains cognition-capable but execution-restricted; its consequential influence over Primary Pi crosses Jack rather than bypassing it.
