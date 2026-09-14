# Jack Kernel Orchestration Agent Capability Contract

**Applies to:** Orchestration Gateway v2 supervisory agents

## Purpose

This document defines the minimum capabilities and authority boundaries required for any agent that supervises a local worker through Jack Kernel.

The orchestration agent may use either:

- a cloud-hosted model; or
- a local model.

The model source may vary. The Jack control boundary does not.

> **Core invariant:** Every supervisor-to-worker control action crosses Jack Kernel. When the orchestration agent uses a local model, its own model inference also crosses Jack Kernel. No locally modeled supervisor or worker may connect directly to the local model server.

---

## 1. Two supported supervisory modes

### 1.1 Cloud-model supervisor

A cloud-model supervisor keeps its cognition on its native cloud provider and uses Jack only for worker supervision.

```text
User
  |
  v
Cloud-model orchestration agent
(native cloud cognition)
  |
  | worker supervision / control
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

Examples include Codex Desktop or another agent connected to a cloud model.

The cloud supervisor does not use Jack as its own model provider in this mode.

### 1.2 Local-model supervisor

A locally modeled orchestration agent must use Jack for both its own cognition and its control of the worker.

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
  | worker supervision / control
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

This is the architecture used by the reference Jack Orchestrator.

When Jack is configured with multiple backend concurrency slots, the local orchestration agent and the worker may infer concurrently through the same Jack Kernel. They still do not bypass Jack.

---

## 2. Mandatory orchestration-agent capabilities

An orchestration agent is compatible with Jack Kernel only if it can perform all of the following through Jack's public orchestration surface.

### 2.1 Accept and interpret the user's objective

The supervisor must be able to understand the user's goal, decide what work should be delegated to the worker, and determine whether follow-up work is required after receiving worker results.

### 2.2 Query worker status and readiness

The supervisor must be able to call:

```text
GET /jack/orchestration/status
```

It must understand at minimum:

```text
status
sessionReady
sessionTransitioning
sessionInstanceId
task_id
run_id
run_epoch
runOpen
settledAt
```

A task must not be submitted unless the current worker instance is ready and not transitioning.

### 2.3 Submit worker tasks

The supervisor must be able to call:

```text
POST /jack/orchestration/tasks
```

It must treat the resulting `task_id` as control identity and must not invent or guess run identity.

### 2.4 Observe live worker activity

The supervisor must be able to consume:

```text
GET /jack/orchestration/events
```

The stream may include worker messages, tool events, task lifecycle events, status transitions, and settlement events.

The supervisor should be able to observe the worker while work is in progress rather than relying only on the final answer.

### 2.5 Track run-bound identity and provenance

The supervisor must preserve and interpret:

```text
seq
task_id
run_id
run_epoch
attribution
source
```

It must not assign an unowned event to a task merely because that task is currently active.

### 2.6 Observe tool activity

When the worker uses tools, the supervisor must be able to observe the worker's tool lifecycle through Jack, including where available:

```text
tool_start
tool_update
tool_end
```

The supervisor must not reinterpret unverified tool claims as execution evidence.

### 2.7 Distinguish answer generation from physical settlement

The supervisor must not treat `message_end` as task completion.

It must not treat `agent_end` as complete physical settlement.

The strongest terminal condition is a terminal task state with:

```text
runOpen == false
settledAt present
```

### 2.8 Cancel controlled work

The supervisor must be able to call:

```text
POST /jack/orchestration/tasks/cancel
```

It must understand that logical cancellation can occur before physical settlement and must not submit overlapping controlled work while the previous run remains open.

### 2.9 Replace the worker session safely

The supervisor must be able to call:

```text
POST /jack/orchestration/session/new
```

It must:

1. record the current ready `sessionInstanceId`;
2. request replacement through Jack;
3. avoid submitting work during transition;
4. tolerate a temporary Jack `502` while the private worker bridge is being replaced;
5. poll Jack only;
6. require a new ready `sessionInstanceId` before follow-up work.

Elapsed time is not proof of readiness.

### 2.10 Reconnect and replay SSE safely

The supervisor must retain the last processed `seq` and use Jack's replay capability after interruption.

It must handle:

```text
?after=<last_seq>
Last-Event-ID
409 orchestration_replay_gap
```

A replay gap must be reported explicitly. Missing history must not be silently treated as complete history.

### 2.11 Interpret results and issue follow-up instructions

The supervisor must be able to inspect worker output, tool activity, errors, and terminal state, decide whether the user's objective has been satisfied, and issue another worker instruction through Jack when needed.

This is what makes the supervisor an orchestration agent rather than a one-shot task sender.

---

## 3. Mandatory connection rules

### 3.1 Worker control always goes through Jack

For every orchestration agent:

```text
Supervisor -> Jack /jack/orchestration -> private worker bridge -> worker
```

Forbidden:

```text
Supervisor -> private worker bridge directly
```

The supervisor must not receive or use the private bridge credential as a bypass path.

### 3.2 Local worker inference always goes through Jack

For the local worker:

```text
Worker -> Jack /v1 -> local model backend
```

Forbidden:

```text
Worker -> local model backend directly
```

### 3.3 Local supervisor inference always goes through Jack

When the orchestration agent itself uses a local model:

```text
Local supervisor -> Jack /v1 -> local model backend
```

Forbidden:

```text
Local supervisor -> local model backend directly
```

This requirement is universal for locally modeled orchestration agents, not specific to Jack Orchestrator.

### 3.4 Cloud supervisor cognition stays native

When the orchestration agent uses a cloud model:

```text
Cloud supervisor <-> native cloud model/provider
Cloud supervisor -> Jack /jack/orchestration -> worker
```

Jack does not replace the cloud supervisor's model provider in this mode.

---

## 4. Authority boundaries

The orchestration agent may decide:

- what work to delegate;
- when additional worker work is needed;
- how to interpret worker results;
- whether to cancel or replace a worker session;
- when the user's overall objective has been satisfied.

Jack and the worker control path remain authoritative for:

- task admission;
- worker readiness;
- task identity;
- run identity and epochs;
- event provenance;
- cancellation state;
- physical settlement;
- session replacement state;
- replay sequencing;
- worker availability;
- private bridge authentication.

The orchestration agent must not fabricate these states from model inference.

---

## 5. Minimum public Jack surface

A compatible orchestration agent must be able to use:

```text
GET  /jack/orchestration/status
GET  /jack/orchestration/events
POST /jack/orchestration/tasks
POST /jack/orchestration/tasks/cancel
POST /jack/orchestration/session/new
```

A locally modeled orchestration agent additionally requires Jack's model-facing inference surface, such as:

```text
POST /v1/chat/completions
```

or another Jack-supported OpenAI-compatible inference route appropriate to the client.

A cloud-model orchestration agent does not use Jack's model-facing inference surface for its own cognition.

---

## 6. Compatibility checklist

An agent qualifies as a Jack orchestration agent only if all applicable checks pass.

### Common requirements

- Understand the user's objective.
- Query worker readiness through Jack.
- Submit tasks through Jack.
- Consume Jack's live SSE worker stream.
- Track `seq`, `task_id`, `run_id`, `run_epoch`, and attribution.
- Observe worker tool activity.
- Distinguish message completion from physical settlement.
- Cancel work through Jack.
- Replace the worker session through Jack.
- Handle replay and replay gaps.
- Interpret worker results and issue follow-up instructions.
- Never contact the private worker bridge directly.
- Never bypass Jack for worker control.

### Cloud-model supervisor requirements

- Keep cognition on the native cloud provider.
- Use Jack only for worker control and worker-observation transport.
- Do not configure Jack as the cloud supervisor's model provider for this architecture.

### Local-model supervisor requirements

- Send all supervisor model inference through Jack.
- Never connect the supervisor directly to the local model server.
- Ensure the worker also reaches the local model only through Jack.
- When concurrent inference is desired, use Jack/backend concurrency rather than separate bypass connections.

---

## 7. Canonical rule

The complete architecture can be summarized as:

```text
MODEL SOURCE MAY VARY.
CONTROL BOUNDARY DOES NOT.

Cloud cognition:
Cloud model <-> Supervisor
Supervisor -> Jack -> Worker
Worker     -> Jack -> Local model

Local cognition:
Supervisor -> Jack -> Local model
Supervisor -> Jack -> Worker
Worker     -> Jack -> Local model
```

> **No locally modeled participant may bypass Jack to reach the local model server, and no orchestration agent may bypass Jack to control the worker.**

This capability contract is the minimum interoperability boundary for an orchestration agent on Jack Kernel Orchestration Gateway v2.