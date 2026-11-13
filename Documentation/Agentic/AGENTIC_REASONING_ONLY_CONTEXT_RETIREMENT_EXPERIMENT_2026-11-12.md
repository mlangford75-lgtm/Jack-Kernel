---
title: "JACK AGENTIC | REASONING-ONLY CONTEXT RETIREMENT"
subtitle: "Experimental engineering specification: full useful-work continuity, lean active context, and compatibility with History and Evolution"
author: "Jonathan Michael Langford"
date: "12 November 2026"
geometry: "margin=0.85in"
fontsize: 10pt
colorlinks: true
linkcolor: teal
header-includes:
  - \usepackage{fancyhdr}
  - \pagestyle{fancy}
  - \fancyhead[L]{\small JACK KERNEL / AGENTIC EXPERIMENT}
  - \fancyhead[R]{\small NOVEMBER 2026}
  - \fancyfoot[C]{\thepage}
  - \setlength{\headheight}{14pt}
---

**Status:** New experiment specification. This document distinguishes architectural intent, current `main` behavior, proposed branch changes, and future upgrades. It does not claim a live-model quality improvement or completed History/Evolution capabilities.

**Source baseline:** `mlangford75-lgtm/Jack-Kernel` `main`, code inspected 12 November 2026. Future alignment: *Jack Agentic History Upgrade — Index-First Revised* and *Jack Evolution — Consolidation & Discovery*, both dated 12 November 2026.

# 1. Executive decision

Jack's Agentic Mode should make one central context-management trade: **replace historical native reasoning with useful distilled working memory; do not prune other useful information to obtain additional context savings.** This policy must hold in every currently supported Agentic profile, including thinking-off configurations.

Jack's Stage 1 completes the authenticated user request, using tools as authorized by the agent. Stage 1 reasoning may be large and can contain discoveries, failed approaches, corrections, and unresolved work. Stage 2 is an isolated, tools-off knowledge distiller, not another agent or task solver. Its principal input is the **current turn's reasoning and frozen outcome**, supplied with the existing authenticated request anchoring and host evidence. Its principal output is *M*: consequential working knowledge useful to subsequent turns.

The engineering design premise is:

$$\operatorname{Utility}(M \mid A1,\,U,\,T) \geq \operatorname{Utility}(R1 \mid A1,\,U,\,T)$$

Here *R1* is native Stage 1 reasoning; *M* is Stage 2 distilled memory; *A1* is the exact frozen Stage 1 answer; *U* is the original user request; and *T* is independently preserved tool evidence. The comparison concerns downstream **utility**, not token count or byte-for-byte duplication. It is a governing hypothesis for this experiment, not a deterministic theorem or a claim that every individual generation achieves it.

**Success is reached even if historical native reasoning is the only information removed from active context.** Further compression of tool history, original requests, outcomes, or user-authored content is neither required nor authorized by this experiment.

# 2. Definitions and immutable responsibility boundaries

| Element | Authority and retention |
|:--|:--|
| Original request (**U**) | Exact caller-authored request. Retain in active historical conversation while that is the current baseline; later archive separately. |
| Native reasoning (**R1**) | Working, potentially provisional cognition of Stage 1. Preserve throughout the active turn; retire from routine future model context at terminal completion, including Stage 2 failure. May be archived outside context. |
| Frozen outcome (**A1**) | Exact completed Stage 1 response. Stage 2 has zero authority to rewrite or replace it. Retain. |
| Tool evidence (**T**) | Exact available calls, arguments, results, errors, ordering and verification observations; distinguish actual returned evidence from claimed effects. Retain historical caller replay in the current baseline. |
| Distilled memory (**M**) | Model-authored consequential working knowledge from the current turn. Commit only if Stage 2 actually completes; never fabricate M upon failure. |
| Stage 2 native reasoning (**R2**) | Optional thinking generated during distillation. It is native reasoning, not an independent authoritative memory artifact. Retire from routine active context under the same reasoning-only policy; do not mistake it for M. |
| Turn identity/status | Host-owned UUID, hashes, stage state, failures, pending-tool identity and authentication. Preserve outside prompts as appropriate. |

Jack is the deterministic kernel *between* the agent and the model. The agent owns external workflows and approvals. The model reasons and interprets; Jack owns transport, deterministic boundaries, evidence custody, permissions and persistence. Nothing in this experiment turns Jack into an executing agent.

# 3. Current `main` baseline: what must not regress

The November 12 mainline already implements much of the target lifecycle:

1. The Stage 2 projection reads the authenticated current request, gathers native reasoning from the current Stage 1 tool-continuation messages, and places the exact frozen response beside it. Earlier turns are excluded from that projection.
2. Stage 1 tool suspensions retain their current reasoning and tool transcript; the self-adversarial Agentic path does **not** apply the generic rolling-frontier pruning during the active turn.
3. Completed-turn projection retains U, model-authored M, exact A1, and caller-replayed raw tool calls/results; it strips historical native R1/R2.
4. The historical tool receipt budget was removed, but host receipts remain *summaries*, not substitutes for all original tool-result bytes. Exact evidence may also be available through caller replay or Pi/forensic archives.
5. Stage 2 has no tool authority. Dedicated Stage 2 system instructions are the default. The optional Phase 3E cache-append path is already present but **off by default**; this experiment will not alter its transport semantics.
6. `main` exposes three current Agentic profiles: Flash, Balanced (default) and Thorough. Legacy stored `Exhaustive` is normalized to Thorough. One shared Stage 2 lifecycle therefore covers all supported modes without adding any profile or toggle.

**Known gap:** The degraded Stage 2 commit currently discards the pending Stage 1 forensic snapshot before clearing the active transaction. This preserves A1 for delivery but can forfeit the available out-of-context R1 snapshot precisely when memory distillation did not succeed. The experiment should attempt the already-supported optional forensic archive before retirement, without keeping raw R1 in subsequent model context and without claiming that an unavailable archive succeeded.

# 4. Exact active-context retirement policy

## 4.1 Successful Stage 2

- Stage 1 finishes, freezes A1 and provides the complete available current-turn R1 to Stage 2 alongside the current request and outcome.
- Stage 2 produces useful M using the **existing working Prime Directive**, surgically clarified rather than replaced. It should not imitate the presentation of A1 or attempt to carry out U again.
- Jack commits actual M, exact A1 and host evidence. Upon the next completed-turn projection, historical native R1/R2 are stripped from model-facing context. All other useful historical records remain.

## 4.2 Failed or interrupted Stage 2

- Stage 1's exact successful A1 remains deliverable. Stage 2 failure must not cause a new Stage 1 execution, tool replay or answer rewrite.
- **Native R1 does not stay in routine future prompts as a fallback.** Stage 2's native R2 similarly does not become a substitute for M.
- Jack records the actual failed/partial state. If an out-of-context forensic snapshot is available and enabled, archive it before clearing the transaction; if not, report the archival gap accurately. Do not invent M.
- Future Stage 1 works from retained prior Agentic Memory, U, A1 and tool history. Once History find/read is implemented and authorized, it may selectively recover exact historical material, including R1, when actually needed. This is **future** functionality, not a present guarantee.
- The absence of M for a failed turn is a known limitation. It is not a justification for permanently occupying the context with enormous raw reasoning traces.

## 4.3 Active, pending, and failed Stage 1

- Never prune active native reasoning mid-turn in ways that break the model's ongoing tool work or resumable transaction.
- Retain all available authenticated tool evidence, including partial execution, rejected proposals, corrections, and exact results.
- A failed Stage 1 without a frozen A1 does not suddenly become a successful user answer. Handoff/status remain attached to the original turn.
- No new execution is authorized by the act of recovering or archiving evidence.

# 5. Working Stage 2 directive: surgical change only

The previously working Prime Directive remains authoritative. Its provenance distinctions, fidelity protections, exact identifiers, causal lessons, and current-turn isolation all remain. No invented output schema, alternate summarizer, new stage name or additional model extension is introduced.

**Only the role sentence and the normal Stage 2 continuation should be clarified** so the model recognizes that the source is the **reasoning and completed response for this current user request**. Avoid ambiguous text such as "previous turn" or "preceding reasoning" that a model may interpret as another conversational turn. The existing JSON task anchor is retained in this experiment to avoid changing both role and output format simultaneously.

This is intentionally a minimal prompt experiment, not a replacement for the carefully developed preservation instructions.

# 6. Test coverage across Agentic profiles

| Profile in current `main` | Stage 1 | Stage 2 | Expected retirement behavior |
|:--|:--|:--|:--|
| Flash | Native thinking off | Native thinking off | A1 and U/T retained; absence of R1 is not a failure; no historical reasoning kept. |
| Balanced (default) | Native thinking on | New native thinking off | Stage 2 can read supplied R1; M replaces historical R1; no R1 survives in future context. |
| Thorough | Native thinking on, existing review | Native thinking on | Existing Stage 1 review remains; R1 and R2 retire after turn without losing M, A1 or tool evidence. |
| Legacy `Exhaustive` saved configuration | Mapped by main to Thorough | Mapped by main to Thorough | Do not introduce another profile merely to test the common lifecycle. |

**Structural tests**: stream and nonstream paths; authentic current-turn pairing; complete R1 fragments across tool checkpoints; frozen A1 fidelity; historical raw tool arguments/results/errors/order; no arbitrary evidence caps; successful and degraded commits; explicit absence of model-visible old R1/R2; optional archive success and archive-disabled/unavailable cases; no changed Stage 1 instruction; no new toggles or model proprietary vocabulary.

**Model tests**: multi-turn factual recall with new entities in A1; complicated tool tasks with read/edit failures and correction; long-context reasoning/answer preservation; no hallucinated recovered facts; adequate continuity after Stage 2 failure; compare prompt evaluation time, next-turn cache hits, TTFT, end-to-end latency and total context footprint against untouched main. These are acceptance experiments, not results already measured.

# 7. Cache, prefill and context economics

This experiment does not change request-prefix architecture, model sampling, stage ordering, active tool schema, generation streaming or cache-append defaults. Stage 2 already incurs prefill for the current-turn reasoning/outcome it is asked to distill. The win comes mainly on **subsequent turns**, where large historical native-reasoning blocks no longer enter the prompt.

Illustratively, a completed turn with 40,000 tokens of R1 replaced by 3,000 useful memory tokens removes about 37,000 tokens of historical reasoning from later requests, apart from existing U/A1/T contents. These figures are examples, not benchmark observations. Real savings depend on tokenizer, historical context structure, backend KV-slot and prefix reuse.

Do not conflate disk archival with cache retention: History storage is not KV storage. The backend owns physical prefix caching, allocation and eviction. Report Jack request projections alongside **backend-measured** prompt evaluation time or cache metrics when available.

# 8. Interface with the future History Upgrade

The future source-of-record design names three UUID-linked text artifacts under `%APPDATA%\JackKernel\Agentic History\`:

```text
jack-turn-<UUID>_Projection.txt  exact U, actual M (if any), A1 (if any), status
jack-turn-<UUID>.txt             available chronological R1 and partial segments
jack-turn-<UUID>_Tools.txt       exact tool proposals, admission, results, errors
history_index.sqlite            rebuildable metadata, source indexing and scopes
```

The future Stage 1-only `agentic_history_find` and `agentic_history_read` tools will allow authorized, bounded, exact retrieval without replaying all historical evidence automatically. This may eventually permit older tool transcripts to leave routine prompt context. **That later optimization is not authorized now.** Its prerequisite is verified durability, exact read-back, access control and non-regression against baseline tool capability.

Failed distillation does not require retaining R1 in active context. When the future archive exists, R1 can remain on disk, indexed and available if the model requests it. Until then, optional JSON forensic snapshots are not equivalent to that full future archive, and the runtime must accurately report availability.

# 9. Interface with future Jack Evolution

Evolution is a **separate** selective consolidation capability built on History evidence. Task-specific Stage 2 M is not automatically Jack Kernel Memory. A capable authorized model may later review episodes, evaluate correctness and usefulness, and propose source-linked updates to curated cross-session knowledge and validated procedures. Jack maintains deterministic provenance, access and publication rules.

The experimental Stage 2 should **not** decide whether facts deserve global promotion, prune details merely for global novelty, or invoke independent discovery. Those are later responsibilities. For now, faithfully preserve consequential working knowledge for subsequent task continuation.

# 10. Experimental implementation boundary and promotion rules

**Implement only on a new branch created directly from main.** Apply the shared Stage 2 directive adjustment and terminal failure archival/retirement semantics consistently to every current Agentic profile. Do not merge the old reasoning-primary branch. Do not touch main, inject a toggle, add an Agentic profile, rewrite tool policy, shrink arbitrary tool histories, or change cache topology.

Approval requires:

1. Existing deterministic regression suite remains green; any changed tests must represent an explicitly changed contract, not weaken a previous guarantee.
2. New targeted tests demonstrate identical retention and retirement behavior in Flash, Balanced and Thorough, with both success and memory failure.
3. Native reasoning is absent from subsequent model-facing context, regardless of Stage 2 success or failure, while useful non-reasoning evidence remains intact.
4. Normal completed-turn memory, frozen answer and tool history remain exactly available under main's present baseline.
5. A failed Stage 2 never fabricates M, never rewrites A1, and never forces historical R1 into future prompts.
6. Archived R1 is represented truthfully as archived, partial, unavailable or disabled; no false durability claims.
7. Fresh Windows clone, real-model tests, and backend context/prefill measurements are performed before any recommendation to promote changes to main.

**Success criterion:** Jack removes historical native reasoning alone and thereby achieves large context savings while keeping useful history and execution capability intact. Further historical tool-context reduction belongs to a future, independently verified History Upgrade.

# 11. Sources, status and caveats

- Jack Kernel mainline, `jack_kernel.py`: Stage 2 projection, forensic snapshot/archive, `_compact_agentic_completed_capsules`, tool-history receipts, Stage 2 degraded path and agentic profile configuration. GitHub: <https://github.com/mlangford75-lgtm/Jack-Kernel>.
- *Jack Agentic History Upgrade — Index-First Revised*, 12 November 2026: three-file archive, failed/partial history, mandatory exact recovery before future tool-history pruning.
- *Jack Evolution — Consolidation & Discovery*, 12 November 2026: source-linked selective Kernel Memory, no automatic model weight training, no kernel takeover of agent responsibilities.
- User's current governing directives: reasoning-only active-context retirement; successful or failed Stage 2 must not cause long R1 to persist; existing working Prime Directive should receive only minimal clarification; no unnecessary tool or evidence pruning.

**Implementation status at authorship:** The present paper is an experimental specification. The branch changes and tests, when made, require their own independent verification and reporting. This paper does not claim the future Agentic History or Evolution features have been implemented.
