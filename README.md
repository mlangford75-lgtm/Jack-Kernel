# Jack Kernel

**v0.1.1**

**Probabilistic cognition may propose, but deterministic software must dispose.**

> **START HERE — Plain-English Master Guide:** [`00_Jack_Kernel_Plain_English_Master_Guide_v0.1.1.docx`](00_Jack_Kernel_Plain_English_Master_Guide_v0.1.1.docx)
>
> This is the first document to read. It explains the kernel, the shipped cognition programs, long-horizon state, Pi integration, and Orchestration Gateway v2 in plain English.

**Current release reality:** Jack Kernel remains **v0.1.1**. Orchestration Gateway v2 is the current supervisory transport. The current validated Primary-Pi control bridge SHA-256 is `E758883F3C18CBEFBF5590C720DBEDF7AB8E85D3314B5EA77E277B1A8C3BD3E4`.

## Orchestration at a glance

The diagrams below depict the accepted **all-local Jack Orchestrator architecture**: the Jack Orchestrator is a cognition-capable but execution-restricted local supervisor, privileged host consequences remain with Primary Pi, and both supervisor and worker cognition can run through Jack against the configured local backend. With multiple backend concurrency slots, the Jack Orchestrator and Primary Pi may infer concurrently through the same Jack Kernel.

![Jack Kernel Orchestration Architecture Schematic](assets/orchestration/Jack_Kernel_Orchestration_Architecture_Schematic.png)

![Jack Orchestration Flow](assets/orchestration/jack_orchestration_flow_diagram.png)

**These diagrams depict the all-local reference architecture.** A cloud-model supervisor such as Codex Desktop retains its native cloud cognition and uses Jack only for the supervisor-to-worker control path. Primary Pi remains the local privileged worker whose model inference runs through Jack to the configured local backend. Codex is a reference example of a broader class of cloud-model supervisory agents, not an architectural dependency.

For installation and first-run steps, see [`GETTING_STARTED.md`](GETTING_STARTED.md).

Current orchestration documentation is intentionally limited to:

- [`ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md`](Documentation/Orchestration/ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md) — canonical protocol, lifecycle, authority, and supervisor compatibility contract.
- [`ORCHESTRATOR_INSTRUCTIONS.md`](Documentation/Orchestration/ORCHESTRATOR_INSTRUCTIONS.md) — canonical operating instructions for supervisory agents, including the Codex cloud-supervisor quickstart.
- [`Documentation/Orchestration/Historical/`](Documentation/Orchestration/Historical/) — dated acceptance evidence and historical records; these are not current runtime identity authority.

Jack Kernel is a local-first host-authoritative inference mediation/control layer between an agent/client and an OpenAI-compatible model backend. Jack is **not the agent and not the LLM**. The agent chooses the task and application workflow. The model supplies probabilistic cognition. Jack controls the host-governed inference environment and authority boundaries around model cognition: stage topology, reasoning and sampling, tool exposure, context projection, answer/commit authority, retention, evidence handling, and host-side execution boundaries.

Deep Research, Agentic, and Code Debugging are **reference programs that demonstrate what can be expressed on the kernel**. They are not the product boundary. Jack can be used to build other staged reasoning, memory, evidence, validation, safety, approval, routing, training-data, and long-horizon workflow layers.

## A Note from the Creator — JML

Jack Kernel is much more than the custom modes shipped with it. Deep Research, Agentic, and Code Debugging are examples of what becomes possible when a deterministic kernel sits between the agent and the LLM. The larger opportunity is to build your own inference layers: dynamic and adaptive reasoning and parameter control, orchestrated agentic workflows, custom staged reasoning, custom context and memory management, model routing, evidence and verification layers, approval gates, and other host-authoritative programs. Treat the bundled modes as starting points, not limits. Experiment, specialize them, replace them, and build new layers that fit your own models and workloads.

## Supervisory orchestration — Orchestration Gateway v2

Jack's host-authoritative boundary extends beyond agent-to-model inference to a supervisor-to-worker control path.

All-local reference topology:

```text
Jack Orchestrator
  -> cognition -> Jack Kernel :8001/v1 -> local backend
  -> supervision -> Jack Kernel :8001/jack/orchestration
                    -> private Pi bridge
                    -> Primary Pi
                    -> Jack Kernel :8001/v1
                    -> local backend
```

Cloud-supervisor topology:

```text
Cloud model <-> Cloud supervisor
Cloud supervisor -> Jack Kernel :8001/jack/orchestration
                  -> private Pi bridge
                  -> Primary Pi
                  -> Jack Kernel :8001/v1
                  -> local backend
```

Codex Desktop is one reference cloud supervisor, not an architectural dependency. In cloud-supervisor mode, the supervisor retains native cloud cognition; Jack governs the supervisor-to-worker control path. In local-supervisor mode, supervisor cognition also runs through Jack.

Gateway v2 provides:

- positive run-bound `task_id` / `run_id` / `run_epoch` attribution;
- replayable SSE with monotonic process-local sequence numbers;
- explicit readiness and session replacement state;
- separation of logical cancellation from physical settlement;
- deterministic worker-unavailable failure;
- recoverable retry epochs without stale assistant failure poisoning the new live epoch;
- structured tool failures retained as diagnostics without automatically forcing a recovered task to fail;
- current runtime identity through the validated bridge and runtime manifest surfaces.

Accepted public orchestration surface:

```text
GET  /jack/orchestration/status
GET  /jack/orchestration/events
POST /jack/orchestration/tasks
POST /jack/orchestration/tasks/cancel
POST /jack/orchestration/session/new
```

This gateway governs supervisor-to-worker control. It does not claim that Jack intercepts every filesystem/shell/process consequence inside privileged Primary Pi.

## Run on Windows

1. Install Python 3.
2. From this folder, install the runtime dependencies once:

   `py -3 -m pip install -r requirements.txt`

3. Start Jack with:

   `start.bat`

The launcher opens Jack's configuration interface and starts the local OpenAI-compatible server when requested.

## Backends

LM Studio is the default backend at `http://127.0.0.1:1234/v1`. Jack also supports Ollama, Jan.ai, raw llama.cpp `llama-server`, and custom OpenAI-compatible endpoints.

Jack's default **agent-facing** listener is `http://127.0.0.1:8001/v1`. Port 8001 is intentionally used so Jack does not collide with a stock vLLM OpenAI-compatible server on port 8000. The Custom OpenAI-compatible backend preset remains `http://127.0.0.1:8000/v1`, allowing the common topology `agent -> Jack :8001 -> vLLM :8000` with no manual port changes.

Jack keeps the caller-facing virtual model separate from the actually configured backend model. Reasoning and sampling controls are rebuilt from the active Jack profile rather than delegated to caller overrides.

## Reasoning modes

### Off / Medium / X-High

Direct native backend reasoning modes. They do not run a Jack cognitive stage graph or generate Jack XML and are useful as matched-model baselines.

### Deep Research

Deep Research is Jack's three-stage Preserve-Thinking reference program for deeply studying difficult and complicated tasks. It deliberately extends one task across Thesis, Antithesis, and Synthesis so the same model can develop a rigorous first-principles plan, challenge that work adversarially, and then authoritatively synthesize and execute the final response with access to the full active reasoning trajectory. Its purpose is to increase the depth, scrutiny, and rigor with which a complicated task is examined before commitment. It does not claim that staging increases the model's latent intelligence; it changes the cognitive process and inference topology around the task.

- **Stage 1 — Thesis:** X-High @ **0.85**, Preserve Thinking ON, tools physically absent. Thesis reasons from First Principles and produces a concentrated plan for Synthesis.
- **Stage 2 — Antithesis:** Medium @ **0.70**, Preserve Thinking ON, tools OFF. It challenges the Thesis and original request adversarially and has no answer authority.
- **Stage 3 — Synthesis:** X-High @ **0.70**, Preserve Thinking ON, caller tools available when supplied. Synthesis is the sole authoritative reasoning, execution, and final-answer stage.

Only actual host-returned tool results establish tool execution. Jack preserves the active Thesis→Antithesis→Synthesis cognitive trajectory through authoritative Synthesis and later retires transient upstream native reasoning according to the program's retention rules.

Deep Research uses host-side `max_tokens` runaway-loop failsafes of **100000 / 20000 / 100000** for Thesis / Antithesis / Synthesis. They are ceilings, not target lengths.

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

The two debugging modes are intentionally identical in topology, prompts, tool policy, context isolation, temperature cascade, durable reporting, and final synthesis. **Code Debugging** runs every debugging inference at **Medium** reasoning. **Code Debugging (Deep)** runs the same program at **X-High** reasoning.

Code Debugging begins with a non-blocking tools-off diagnostic intake, freezes user-origin intake as Pass 0, then runs five fresh report-only single-problem forensic passes against the unchanged target. Each pass searches the same professional review space under the temperature cascade **1.00 → 0.80 → 0.70 → 0.60 → 0.50**.

Every real primary finding is evidence-bound and classified LOW, MEDIUM, HIGH, or CRITICAL. Useful non-empty completed handoffs are preserved rather than rejected by brittle formatting requirements.

Code Debugging remains report-only. It produces repair-ready specifications for a separate work agent and creates a unique durable report under `Debugging/Reports/` for each invocation.

## Tool and authority boundaries

Caller tools remain standard OpenAI tool definitions. Jack decides which stage can see and call them and resumes the exact interrupted stage after a host tool result.

In Deep Research, Thesis and Antithesis have no tool authority; Synthesis receives the caller-authorized tool surface. In Agentic, Stage 1 may use supplied tools while Stage 2 has tools disabled and zero answer authority. Model-authored claims do not substitute for host execution evidence.

Caller system/developer messages are blocked before backend cognition. The caller-facing model name is virtual and does not control the actual backend model. Jack owns the active mode, stage prompts, reasoning/sampling controls, context preparation, tool-resume routing, retention, and authority boundaries.

For supervisory orchestration, Jack owns the public supervisor-to-worker gateway boundary. The supervisor may request worker status, observe events, submit/cancel work, or replace the worker session through Jack, while the downstream bridge credential remains private to Jack.

## State, memory, and evidence

Jack deliberately uses different memory lifetimes for different programs instead of treating all reasoning as permanent context.

- **Deep Research:** preserve the complete active Thesis→Antithesis→Synthesis cognition surface through Synthesis; later retire upstream transient native reasoning while retaining the durable authoritative trajectory required by the program.
- **Agentic:** use Preserve Thinking at the immediate Stage-1→Stage-2 boundary, distill native cognition into exact user + semantic Jack XML + frozen A1, then retire completed raw native cognition/tool protocol before later turns.
- **Code Debugging / Code Debugging (Deep):** keep Preserve Thinking only inside an active pass; durably retain exact pass summaries and a compact confirmed prior-finding registry for later fresh passes, then perform a fresh tools-off final reconciliation after Pass 5.

Jack XML is semantic attention state, not independent truth. Deterministic verification is represented as verified only when actual tool evidence establishes it.

## Host-side policy and safety layers

Because Jack sits between caller and backend and owns stage, tool, validation, and commit boundaries, deployments can add code-defined request, tool, validator, approval, output, or release gates whose authority does not depend on agent intent or model compliance.

Jack does **not** claim that this release ships a universal safety suite or filesystem sandbox. Those are programmable host-side layers deployments may add to the kernel control plane.

## Pi context-window synchronization

Jack exposes the context window of the backend instance it actually resolved instead of forcing Pi or another agent to guess. The OpenAI-compatible `GET /v1/models` response includes context metadata aliases, and `GET /health` reports effective context length and source.

For the existing `pi-lmstudio` extension, point its server URL at the **Jack server root** (for example `http://127.0.0.1:8001`, not the `/v1` suffix). It requests `GET /api/v1/models`; Jack returns an LM-Studio-compatible loaded-model record describing the backend instance Jack selected.

For the existing `jack-kernel` Pi provider, the package includes `Pi/jack-kernel.ts` plus `Pi/install-jack-kernel-extension.ps1`. The extension registers/refreshes the provider from Jack's live metadata so stale Pi-side context guesses do not remain authoritative after Jack has established the backend's actual loaded context.

Authority chain:

```text
loaded backend context -> Jack detection -> Jack model metadata -> Pi contextWindow
```

## Runtime surface

Jack exposes an OpenAI-compatible `/v1/chat/completions` endpoint, root status, `/health`, and the public orchestration surface under `/jack/orchestration/*`. The downstream Primary-Pi bridge remains private and authenticated separately.

Release builds do not inject runtime identity, stage token counts, context-size telemetry, or similar diagnostic telemetry into model reasoning streams. Optional forensic archives remain out-of-band records for failure analysis and are not automatically rehydrated into model cognition.

## Files

- `jack_kernel.py` — Jack Kernel runtime and configuration interface.
- `Pi/jack-kernel.ts` — optional Pi provider extension that registers `jack-kernel` from Jack's live context metadata.
- `Pi/install-jack-kernel-extension.ps1` — Windows installer for the Pi context-sync extension.
- `Pi/pi-control-bridge.ts` — current validated run-bound Primary-Pi control bridge for Orchestration Gateway v2.
- `Pi/install-pi-control-bridge-v2.ps1` — installer/backup helper for the Primary-Pi bridge.
- `Documentation/Orchestration/ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md` — canonical orchestration protocol, lifecycle, authority, and supervisor compatibility contract.
- `Documentation/Orchestration/ORCHESTRATOR_INSTRUCTIONS.md` — canonical supervisor operating instructions, including Codex Desktop quickstart guidance.
- `Documentation/Orchestration/Historical/` — dated acceptance evidence; not current runtime identity authority.
- `Debugging/User_Instructions.md` — user-facing debugging quick start.
- `Debugging/Instructions.md` — Code Debugging intake/pass instructions.
- `Debugging/Debugging_Report.md` — bundled report template/reference.
- `Debugging/Reports/` — one unique durable report per debugging invocation.
- `start.bat` — Windows launcher.
- `requirements.txt` — runtime Python dependencies.
- `LICENSE` — PolyForm Noncommercial License 1.0.0 reference and official terms URL.
- `NOTICE` — required copyright notice and licensor contact.
- `COMMERCIAL_LICENSE.md` — separate commercial-licensing notice and contact.
- `README.md` — repository front door and release documentation.
- `GETTING_STARTED.md` — concise installation, startup, Pi setup, and regression-check guide.
- `00_Jack_Kernel_Plain_English_Master_Guide_v0.1.1.docx` — front-door copy of the full plain-English architecture and operating guide.
- `Documentation/Jack_Kernel_Preview_Programmable_Cognition_Runtime_v0.1.1.docx` — concise programmable-cognition runtime preview.
- `Documentation/Jack_Kernel_Long_Horizon_Cognition_Technical_Whitepaper_v0.1.1.docx` — long-horizon cognition and architectural technical whitepaper.
- `Documentation/Jack_Kernel_Runtime_Specification_v0.1.1.docx` — normative Jack Kernel v0.1.1 runtime specification.

## License

Jack Kernel is source-available under the **PolyForm Noncommercial License 1.0.0** for permitted noncommercial use. The official, unmodified license terms are referenced in `LICENSE`.

**Required Notice:** Copyright 2026 Jonathan Michael Langford.

Commercial use requires a separate written commercial license from the licensor. For commercial licensing, contact **Jonathan Michael Langford** at **Mlangford75@protonmail.com**. See `COMMERCIAL_LICENSE.md`.