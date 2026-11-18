# Jack Agentic - Technical and Product Whitepaper

**Author:** Jonathan Michael Langford  
**Revision:** 17 November 2026  
**Lineage:** 6 November original; 12 November corrected mainline; 17 November source-aligned provenance-safe cache and source-only memory upgrade.

## Executive thesis

Jack is not an agent, and it is not the language model. It is a deterministic local-first runtime between an application/agent and an OpenAI-compatible inference backend. The agent owns its workflow and external tool execution. The model proposes reasoning and actions. **Jack authenticates stage identity, governs tool continuation, freezes the exact completed answer, protects evidence provenance and decides what working knowledge survives.** Probabilistic cognition may propose, but deterministic software must dispose.

The decisive advance since 12 November is the **compatibility of security guidance and real prompt-prefix caching**. Jack no longer needs to silently erase legitimate host safety instructions to obtain cache reuse. It also retains authentic tool history without keeping expired native reasoning in routine model input.

## The four supported Agentic profiles

- **Flash:** native thinking off, tools available, no Stage 2 inference; host still owns finalization and turn identity. A seven-turn clock-edit session completed successfully with six tool continuations and cross-turn cache reuse.
- **Balanced (default):** native Stage 1 reasoning, authenticated tool continuations, tools-off Stage 2 consequential memory with its own native thinking disabled; no optional review.
- **Thorough:** native Stage 1 reasoning and review where configured, then isolated tools-off Stage 2 native reasoning and knowledge extraction. A five-turn clock session produced five shadow commits and preserved exact SVG implementation details.
- **Translated:** the Agentic translation continuation with selectable target language; source-only memory remains in English while names, source quotations and paths are preserved.

There is no selectable Exhaustive profile in the tested leading candidate. Native X-High is a separate cognition mode on the shared backend, not an Agentic profile.

## Distinguish memory from execution evidence

The completed answer **A1** belongs to the original user turn and freezes before memory extraction. The current-turn **R1** is useful source cognition, but past native reasoning is not automatically replayed as authority. Stage 2 extracts a concise yet consequential **M** from authenticated read-only working evidence rather than reconstructing or answering the original user request. Stage 2 cannot run tools, revise A1 or treat caller system prompts as its own authority.

The separate tool protocol **T** includes authentic tool arguments, return values, errors and sequence. Jack preserves caller-replayed raw historical tool records and host receipts through later turns until a durable, authorized, searchable archival substitute can demonstrably replace routine context. Deleting useful work to meet an arbitrary character limit violates the architecture.

A tool saying it wrote a file proves only that the tool *reported* the write. Jack does not invent physical filesystem attestations or resolved CWD identity. A failed tool turn should preserve meaningful partial work and remain labeled failed.

## Provenance protection with measurable cache economics

A previous experiment reverted 441 characters appended to the system prompt on a tool resume. Those characters were real host provenance guidance distinguishing untrusted tool-result text from authenticated host-origin instructions. The leading candidate moves this same notice into the **initial tool-capable system prefix**, adds it only once, and carries it forward unchanged on continuations. Its cache stabilizer reports prefix changes without suppressing new system instructions. The shared backend implements this for streaming and nonstreaming, and for Agentic and non-Agentic tool-capable stages.

LM Studio logs measured **99.5% prefix retention** (Balanced) and **99.4%** (Native X-High), with just **46 newly evaluated prompt tokens** for the tested tool continuation in either case. Both used Gemma-4-12B. These are physical server measurements from two configurations, not a promise for Ollama, llama.cpp or other backends. Jack does not own LM Studio's physical KV slots; auxiliary logical lanes may share the same server cache.

## Empirical evidence without judging stochastic artistry

A seven-turn Flash clock run demonstrated chronological editing of the same workspace file after a mistaken initial interpretation, tool execution, deletion, speech-bubble and bird-color refinement, and a final chat recap. A five-turn Thorough run demonstrated source-only memory that preserved actionable filenames, dimensions, bubble geometry and the yellow-to-blue SVG attribute edit. Their kernel significance is correct stage execution, tool provenance, historical continuity, memory retention and cache reuse; no claim is made that the model generated an objectively superior design.

## Release truth and next steps

The leading candidate passed **1,207** Windows Python tests with **199 inherited failures**, compared with **1,189 passes / the same 199 failures** on its parent. All fifteen newly introduced prompt-assertion failures disappeared after four test-only updates. **The full suite is not green.** Focused repair tests passed 98 cases. The current promotion incorporates the tested candidate while preserving post-November-12 mainline Phase-4 Windows path-security corrections; it deliberately uses the source-only working-state design instead of mainline's brief JSON task-prompt experiment.

Remaining validation includes legacy suite reconciliation, independently configured agents and inference servers, failure and interruption paths, real nested streaming, crash/restart archival recovery, and optionally physical isolation of Stage 2 cache slots. The proposed indexed Agentic History archive is not yet demonstrated as a drop-in substitute for full tool evidence.

**Product conclusion:** Jack's differentiator is a deterministic chassis for stochastic cognition: authenticated continuity, trustworthy evidence separation, model-independent tool-stage orchestration, and measured cache reuse without sacrificing higher-priority instructions.

**Historical preservation:** The 17 November PDF edition includes the complete previous 12 November product whitepaper (itself containing the original 6 November edition) as an unmodified appendix.
