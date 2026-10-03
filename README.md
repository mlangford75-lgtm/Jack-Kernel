# Jack Kernel — The Harness for the Harness

**v0.1.1**

**Probabilistic cognition may propose, but deterministic software must dispose.**

Jack Kernel is a **local-first, host-authoritative inference mediation and control runtime** that sits between an application or agent and an OpenAI-compatible model backend.

Jack is **not the agent and not the LLM**. The agent chooses the task and workflow. The model supplies probabilistic cognition. Jack owns deterministic boundaries around that cognition: stage topology, reasoning and sampling controls, tool exposure, context projection, answer/commit authority, retention, evidence handling, runtime identity, consequence disposition, and selected security controls.

Deep Research, Agentic, and Code Debugging are **reference programs built on the kernel**. They demonstrate what Jack can express; they are not the product boundary.

> **Start here:** [`00_Jack_Kernel_Plain_English_Master_Guide_v0.1.1.docx`](00_Jack_Kernel_Plain_English_Master_Guide_v0.1.1.docx)
>
> **Install and run:** [`GETTING_STARTED.md`](GETTING_STARTED.md)
>
> **Current security state:** [`CURRENT_SECURITY_STATUS.md`](CURRENT_SECURITY_STATUS.md)

## Architecture at a glance

```text
Application / Agent / Supervisor
            |
            v
       Jack Kernel
            |
            v
OpenAI-compatible model backend
```

With Orchestration Gateway v2 enabled, Jack also mediates the supervisor-to-worker control boundary:

```text
Supervisor
   |
   v
Jack Kernel :8001/jack/orchestration
   |
   v
private authenticated worker bridge
   |
   v
Primary Pi / privileged worker
   |
   v
Jack Kernel :8001/v1
   |
   v
configured local backend
```

A cloud-model supervisor retains its native cloud cognition and uses Jack for worker control. A local-model supervisor uses Jack for both local cognition and worker control.

The accepted all-local architecture is illustrated here:

![Jack Kernel Orchestration Architecture Schematic](assets/orchestration/Jack_Kernel_Orchestration_Architecture_Schematic.png)

![Jack Orchestration Flow](assets/orchestration/jack_orchestration_flow_diagram.png)

## What Jack owns

Jack's host-authoritative boundary includes, where applicable:

- caller request reconstruction and hidden-authority stripping;
- virtual caller-facing model identity versus actual backend identity;
- mode and stage topology;
- stage-specific reasoning and sampling controls;
- tool visibility and tool-call validation;
- context preparation and long-horizon state projection;
- answer/commit authority;
- evidence namespace protection;
- runtime and lane identity surfaces;
- supervisor-to-worker orchestration mediation;
- deterministic security outcomes and consequence disposition;
- represented-path policy;
- the current runtime-scoped Authority & Security Ledger.

Jack does not acquire authority merely because it can observe a value. Observability is not authority, evidence is not authority, a port is not identity, cancellation is not settlement, and represented targets are not necessarily resolved host objects.

## What Jack does not claim

Jack is not a universal operating-system sandbox, filesystem-object attestation layer, shell-effects oracle, distributed consensus ledger, or proof that every represented consequence was physically realized by an external executor.

The current security checkpoint deliberately preserves these boundaries. See [`CURRENT_SECURITY_STATUS.md`](CURRENT_SECURITY_STATUS.md) for the exact current claims and nonclaims.

## Current validated state

The current frozen security checkpoint is **Phase 6 — Runtime-Scoped Authority & Security Ledger**.

Validated annotated tag:

`security-layer-phase6-validated-2026-10-02`

Tag object:

`1e46b9872db66cc3944b79550aa30509b4c84296`

Validated closure target:

`51e29b197ab62db410e6b4b43c92688ba613826f`

The cumulative validated security stack is:

- **Phases 0–3:** deterministic `SecurityOutcome`, StreamingIRQ bounded pre-release quarantine, malformed-SSE release protection, exact-match Canary enforcement, immutable runtime/lane-bound static Tier A/B Canary policy.
- **Phase 4:** Restricted Paths, optional Workspace Lock, represented-path normalization, bounded recognized command authorization, executor admission, and minimum multi-call containment.
- **Phase 5:** deterministic Consequence Gate that consumes typed authoritative facts and selects the narrowest justified disposition without centralizing failure blast radius.
- **Phase 6:** process-local Authority & Security Ledger with closed event schemas, canonical predecessor chaining, immutable committed projection, bounded fail-soft durability, restart isolation, and narrow ledger-authority freeze semantics.

Phase 7 and Phases 8–11 have not started.

For exact validation evidence and phase-by-phase nonclaims, use [`CURRENT_SECURITY_STATUS.md`](CURRENT_SECURITY_STATUS.md) and the detailed checkpoint records under [`docs/security/`](docs/security/).

## Run on Windows

The current validated development/release baseline is **Python 3.14.6**. Repository validation additionally uses **Node.js 24.16.0** for the Pi bridge harnesses.

Install runtime dependencies:

```powershell
py -3 -m pip install -r requirements.txt
```

Start Jack:

```powershell
.\start.bat
```

Default agent-facing endpoint:

```text
http://127.0.0.1:8001/v1
```

LM Studio is the default backend at `http://127.0.0.1:1234/v1`. Jack also supports Ollama, Jan.ai, raw llama.cpp `llama-server`, and custom OpenAI-compatible endpoints.

Port `8001` is Jack's default agent-facing listener. Port `8000` remains available for the common custom OpenAI-compatible/vLLM backend topology:

```text
agent -> Jack :8001 -> backend :8000
```

For complete startup, Pi, lane, security-policy, and regression instructions, see [`GETTING_STARTED.md`](GETTING_STARTED.md).

## Cognition programs

### Off / Medium / X-High

Direct native backend reasoning modes. They do not run a Jack cognitive stage graph or generate Jack XML and are useful as matched-model baselines.

### Deep Research

Deep Research is Jack's three-stage Preserve-Thinking reference program for difficult and complicated tasks.

- **Stage 1 — Thesis:** X-High @ **0.85**, Preserve Thinking ON, tools physically absent. Thesis develops a concentrated first-principles plan.
- **Stage 2 — Antithesis:** Medium @ **0.70**, Preserve Thinking ON, tools OFF. It adversarially challenges Thesis and has no answer authority.
- **Stage 3 — Synthesis:** X-High @ **0.70**, Preserve Thinking ON, caller tools available when supplied. Synthesis is the sole authoritative reasoning, execution, and final-answer stage.

Only actual host-returned tool results establish tool execution. Jack preserves the active Thesis→Antithesis→Synthesis cognitive trajectory through authoritative Synthesis and later retires transient upstream native reasoning according to the program's retention rules.

Deep Research uses host-side `max_tokens` runaway-loop ceilings of **100000 / 20000 / 100000** for Thesis / Antithesis / Synthesis.

### Agentic

Agentic is Jack's **Qwen-oriented Preserve-Thinking semantic-consolidation program** for capable multi-turn models.

- **Stage 1 — Full native cognition:** X-High @ **0.70**, Preserve Thinking ON, caller tools available when supplied, and no Jack cognitive system prompt. Stage 1 produces complete answer **A1**, which Jack freezes exactly.
- **Stage 2 — Semantic consolidation:** X-High @ **0.50**, Preserve Thinking ON, tools OFF, zero answer authority. Stage 2 receives the immediately preceding native reasoning/tool trajectory and frozen A1, then converts the future-useful epistemic state into strongly semantic Jack XML.

Jack XML carries four semantic responsibilities:

- **grounding** — what was actually observed and not observed;
- **verification** — only deterministic proof established by actual tool evidence, with narrow scope;
- **challenge** — prospective PREMISE / INVALIDATION / HIDDEN ASSUMPTION pressure;
- **audit** — concrete output mistakes Stage 2 actually determined are present in frozen A1.

Stage 2 cannot rewrite, repair, extend, select, or regenerate A1. There is no A2 and no post-XML answer-generation pass.

After semantic consolidation, the durable completed-turn capsule is:

```text
exact user message -> strongly semantic Jack XML -> exact frozen A1
```

Preserve Thinking is a short-lived high-bandwidth bridge across the immediate Stage-1→Stage-2 boundary. Jack XML carries the longer-horizon burden as compact semantic attention state. It is not independent truth or evidence.

### Code Debugging / Code Debugging (Deep)

**New user? Start with [`Debugging/User_Instructions.md`](Debugging/User_Instructions.md).**

The two debugging modes are identical in topology, prompts, tool policy, context isolation, temperature cascade, durable reporting, and final synthesis. **Code Debugging** uses **Medium** reasoning and **Code Debugging (Deep)** uses **X-High** reasoning.

Code Debugging begins with a non-blocking tools-off diagnostic intake, freezes user-origin intake as Pass 0, then runs five fresh report-only single-problem forensic passes against the unchanged target. Each pass searches the same review space under the temperature cascade **1.00 → 0.80 → 0.70 → 0.60 → 0.50**.

Every primary finding is evidence-bound and classified LOW, MEDIUM, HIGH, or CRITICAL. The program remains report-only and creates a unique durable report under `Debugging/Reports/` for each invocation.

## Tool and authority boundaries

Caller tools remain standard OpenAI tool definitions. Jack decides which stage can see and call them and resumes the exact interrupted stage after a host tool result.

In Deep Research, Thesis and Antithesis have no tool authority; Synthesis receives the caller-authorized tool surface. In Agentic, Stage 1 may use supplied tools while Stage 2 has tools disabled and zero answer authority. Model-authored claims do not substitute for host execution evidence.

Caller `system` / `developer` messages are blocked before backend cognition. The caller-facing model name is virtual and does not control the actual backend model. Jack owns the active mode, stage prompts, reasoning/sampling controls, context preparation, tool-resume routing, retention, and authority boundaries.

## State, memory, and evidence

Jack deliberately uses different memory lifetimes for different programs rather than treating all reasoning as permanent context.

- **Deep Research:** preserve the complete active Thesis→Antithesis→Synthesis cognition surface through Synthesis; later retire upstream transient native reasoning while retaining the durable authoritative trajectory required by the program.
- **Agentic:** use Preserve Thinking at the immediate Stage-1→Stage-2 boundary, distill native cognition into exact user + semantic Jack XML + frozen A1, then retire completed raw native cognition/tool protocol before later turns.
- **Code Debugging / Code Debugging (Deep):** keep Preserve Thinking only inside an active pass; durably retain exact pass summaries and a compact confirmed prior-finding registry for later fresh passes, then perform a fresh tools-off final reconciliation after Pass 5.

Jack XML is semantic attention state, not independent truth. Deterministic verification is represented as verified only when actual tool evidence establishes it.

## Supervisory orchestration — Orchestration Gateway v2

Jack's host-authoritative boundary extends beyond agent-to-model inference to a supervisor-to-worker control path.

Current orchestration documentation:

- [`Documentation/Orchestration/ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md`](Documentation/Orchestration/ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md) — canonical protocol, lifecycle, authority, and supervisor compatibility contract.
- [`Documentation/Orchestration/ORCHESTRATOR_INSTRUCTIONS.md`](Documentation/Orchestration/ORCHESTRATOR_INSTRUCTIONS.md) — canonical operating instructions for supervisory agents.
- [`Documentation/Orchestration/Historical/`](Documentation/Orchestration/Historical/) — dated acceptance evidence, not current runtime identity authority.

Gateway v2 provides positive run-bound `task_id` / `run_id` / `run_epoch` attribution, replayable SSE, readiness/session replacement state, cancellation/settlement separation, deterministic worker-unavailable failure, retry epochs, and structured tool-failure diagnostics.

Public routes:

```text
GET  /jack/orchestration/status
GET  /jack/orchestration/events
POST /jack/orchestration/tasks
POST /jack/orchestration/tasks/cancel
POST /jack/orchestration/session/new
```

The gateway governs supervisor-to-worker control. It does not claim Jack intercepts every filesystem/shell/process consequence inside privileged Primary Pi.

## Multi-endpoint runtime lanes

The multi-endpoint runtime substrate allows multiple independently addressable Jack OS processes to remain hot at once while sharing one configured backend model.

Examples:

```powershell
.\start-lane.ps1 -RuntimeId jack-agentic-01 -Mode agentic -Port 8101
.\start-lane.ps1 -RuntimeId jack-debug-01 -Mode code-debugging -Port 8102
.\start-lane.ps1 -RuntimeId jack-research-01 -Mode deep-research -Port 8103
```

The configured port is a preference, not identity. A runtime may move to a validated fallback endpoint without changing `runtime_id`, `lane_id`, mode, task/run ownership, or security ownership.

Runtime manifests are discovery evidence. Positive live `/health.runtime_id` verification establishes the runtime identity actually reached. A stale observational manifest status must not veto a positively verified live runtime; a live identity mismatch remains an identity failure.

`JACK_MAX_CONCURRENT` remains process-local. Lane availability is not fleet-wide backend admission and does not prove physical simultaneous GPU generation.

Authenticated `GET /jack/runtime/status` is observability only. It is not model context, cancellation authority, stage authority, or commit authority. Client transport disconnect is likewise not implicit cognition-cancellation authority.

Privileged effect-capable lanes should use positively named bridge/worker bindings. Shared multi-tenant privileged workers are not part of the first endpoint upgrade.

## Current security architecture

For current security truth, read [`CURRENT_SECURITY_STATUS.md`](CURRENT_SECURITY_STATUS.md).

The current Phase-6 stack preserves the governing rule:

> Contain the violation at the narrowest boundary that preserves the security invariant.

A security outcome applies to the consequential boundary being evaluated; it does not automatically widen to the surrounding cognition, task, run, connection, or process.

The current runtime includes represented-path policy, deterministic consequence disposition, and the process-local Authority & Security Ledger, but still does **not** claim universal filesystem sandboxing or complete host-effect knowledge.

## Pi context-window synchronization

Jack exposes the context window of the backend instance it actually resolved instead of forcing Pi or another agent to guess. The OpenAI-compatible `GET /v1/models` response includes context metadata aliases, and `GET /health` reports effective context length and source.

For `pi-lmstudio`, point its server URL at the **Jack server root** (for example `http://127.0.0.1:8001`, not the `/v1` suffix). It requests `GET /api/v1/models`; Jack returns an LM-Studio-compatible loaded-model record describing the backend instance Jack selected.

For the `jack-kernel` Pi provider, the package includes `Pi/jack-kernel.ts` plus `Pi/install-jack-kernel-extension.ps1`. The extension registers/refreshes the provider from Jack's live metadata so stale Pi-side context guesses do not remain authoritative.

```text
loaded backend context -> Jack detection -> Jack model metadata -> Pi contextWindow
```

## Runtime surface

Jack exposes an OpenAI-compatible `/v1/chat/completions` endpoint, root status, `/health`, and the public orchestration surface under `/jack/orchestration/*`. The downstream Primary-Pi bridge remains private and authenticated separately.

Release builds do not inject runtime identity, stage token counts, context-size telemetry, or similar diagnostic telemetry into model reasoning streams. Optional forensic archives remain out-of-band records and are not automatically rehydrated into model cognition.

## Documentation map

### Start here

- [`README.md`](README.md) — project front door.
- [`GETTING_STARTED.md`](GETTING_STARTED.md) — install, run, Pi setup, runtime lanes, and security configuration.
- [`CURRENT_SECURITY_STATUS.md`](CURRENT_SECURITY_STATUS.md) — current validated security state.
- [`00_Jack_Kernel_Plain_English_Master_Guide_v0.1.1.docx`](00_Jack_Kernel_Plain_English_Master_Guide_v0.1.1.docx) — full plain-English architecture and operating guide.

### Governing and research documentation

- [`Documentation/Jack_Kernel_Runtime_Specification_v0.1.1.docx`](Documentation/Jack_Kernel_Runtime_Specification_v0.1.1.docx) — normative runtime specification.
- [`Documentation/Overview/Jack_Kernel_Preview_Programmable_Cognition_Runtime_v0.1.1.docx`](Documentation/Overview/Jack_Kernel_Preview_Programmable_Cognition_Runtime_v0.1.1.docx) — public overview.
- [`Documentation/Research/Jack_Kernel_Long_Horizon_Cognition_Technical_Whitepaper_v0.1.1.docx`](Documentation/Research/Jack_Kernel_Long_Horizon_Cognition_Technical_Whitepaper_v0.1.1.docx) — research and architectural treatment.
- [`Documentation/Security/`](Documentation/Security/) — Security Hardening Architecture and cumulative governing amendments.
- [`docs/security/`](docs/security/) — detailed immutable phase checkpoint records.

### Historical engineering evidence

- [`Documentation/Historical-Build-Record/`](Documentation/Historical-Build-Record/) — dated demonstrations, superseded root checkpoint summaries, and preserved build evidence.
- [`Documentation/Orchestration/Historical/`](Documentation/Orchestration/Historical/) — orchestration acceptance history.

## Key files

- `jack_kernel.py` — Jack Kernel runtime and configuration interface.
- `jack_path_policy.py` — represented-path policy and deterministic path facts.
- `jack_consequence_gate.py` — Phase-5 deterministic consequence disposition.
- `jack_authority_ledger.py` — Phase-6 runtime-scoped Authority & Security Ledger.
- `Pi/jack-kernel.ts` — optional Pi provider extension using Jack's live context metadata.
- `Pi/pi-control-bridge.ts` — current validated run-bound Primary-Pi control bridge.
- `Debugging/User_Instructions.md` — user-facing debugging quick start.
- `Debugging/Instructions.md` — Code Debugging intake/pass instructions.
- `Debugging/Reports/` — one unique durable report per debugging invocation.
- `start.bat` — Windows launcher.
- `requirements.txt` — runtime Python dependencies.

## Historical Build Record

The repository preserves development evidence rather than deleting it as the implementation advances. Large demonstration logs, generated reports, and superseded root checkpoint summaries are organized under [`Documentation/Historical-Build-Record/`](Documentation/Historical-Build-Record/).

Historical records may state what was true at an earlier checkpoint. They are preserved as provenance and should not be mistaken for the current runtime state merely because they remain available.

## A Note from the Creator — JML

Jack Kernel is much more than the custom modes shipped with it. Deep Research, Agentic, and Code Debugging are examples of what becomes possible when a deterministic kernel sits between the agent and the LLM. The larger opportunity is to build your own inference layers: dynamic and adaptive reasoning and parameter control, orchestrated agentic workflows, custom staged reasoning, custom context and memory management, model routing, evidence and verification layers, approval gates, and other host-authoritative programs. Treat the bundled modes as starting points, not limits. Experiment, specialize them, replace them, and build new layers that fit your own models and workloads.

## License

Jack Kernel is source-available under the **PolyForm Noncommercial License 1.0.0** for permitted noncommercial use. The official, unmodified license terms are referenced in `LICENSE`.

**Required Notice:** Copyright 2026 Jonathan Michael Langford.

Commercial use requires a separate written commercial license from the licensor. For commercial licensing, contact **Jonathan Michael Langford** at **Mlangford75@protonmail.com**. See `COMMERCIAL_LICENSE.md`.
