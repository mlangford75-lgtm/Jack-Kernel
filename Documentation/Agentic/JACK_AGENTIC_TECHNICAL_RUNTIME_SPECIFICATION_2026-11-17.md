# JACK AGENTIC
## Technical Runtime Specification
**Current mainline implementation | 17 November 2026**

**Jonathan Michael Langford | Jack Kernel project**

> **November 27, 2026 — experimental audit reconciliation:** This November 17 edition records its original implementation and validation state. For subsequent candidate behavior, including the tool-free Coder Architect, frozen-A1 preservation after retrospective budget exhaustion, and current Responses caller-instruction scope, see the [independent audit remediation register](../Independent_Audit_Remediation_Register.md). This note does not retroactively change the original evidence or claim a merged release.

**A deterministic host contract for multi-stage agentic cognition, execution evidence, prompt authority and cache continuity.**

This is the complete, source-aligned current edition. It replaces contradictory operational claims in the November 12 revision while **preserving the complete November 12 PDF, including its November 6 edition, unchanged** after the archival divider. The present edition is the governing description; historical sections are historical evidence, not instructions to implement obsolete behavior.

**Verified merge:** Jack-Kernel PR #164, commit `f71e89c6fcfdce32d6a8ae1937e9084d2ced4f86`. **Release qualification:** promotion is real; a clean post-merge Windows full-suite pass is *not* established. The pre-merge candidate returned 1,207 passes and 199 inherited failures.

## Editorial basis, scope and source hierarchy

The governing doctrine has not changed: **probabilistic cognition may propose, but deterministic software must dispose.** Jack Kernel remains the deterministic local-first mediation chassis between the calling application or agent and its model backend. The agent owns the human interaction, workspace, ordinary tool execution and external effects. The probabilistic model supplies proposals, reasoning and response content. Jack owns the finite-state stage contract, tool-checkpoint admission, prompt authority separation, answer freeze, memory commit, historical projection, evidence classification and bounded release decisions. A model assertion is never proof that the host performed a mutation.

This revision was checked against `main` after PR #164, including `jack_kernel.py`, `jack_evidence_guard.py`, `jack_stage1_cache_stability.py`, `jack_cache_orchestrator.py`, `jack_cache_prefix_diagnostics.py`, the Windows Phase-4 path policy and relevant tests. It also distinguishes the November 17 LM Studio live logs from inferred behavior. Runtime source and authenticated host traces outrank descriptions from an older paper. A passed focused test does not establish an unrelated safety guarantee; an old failed assertion is not automatically harmless.

The previous November 12 paper correctly introduced retained raw historical tool protocol, same-turn Stage 2 scope, Pi built-in edit-origin discrimination and explicit degraded-turn semantics. **Those obligations remain**. It is obsolete specifically on profile count, Flash's Stage 2 inference, the model-facing source of Stage 2, the treatment of legitimate tool-provenance system insertions, available cache diagnostics and the release status.

## 1. Kernel boundaries and invariant ownership

| Boundary | Responsible owner | Required result |
|---|---|---|
| Request and caller system | Authentic user/caller plus Jack's system gates | Never promote lower-priority tool content to host instruction |
| Stage topology | Jack host | Correct stage identity and tool permissions; no stage self-election |
| Tool release and completion | Jack host + external calling agent | Pending call IDs must match returned results; no reexecution from a replayed transcript |
| External filesystem/network effect | Calling tool/executor | Return is observed evidence, not independent effect attestation |
| Completed answer A1 | Jack freeze after Stage 1 | Immutable to Stage 2 and later retrospective work |
| Memory M | Dedicated host-managed lifecycle | Stage 2 cannot execute tools or change A1; Flash never requires second model inference |
| Historical projection | Jack host | Preserve authenticated U/A1/M and raw tool protocol; retire historical R1/R2 |
| Cache optimization | Jack input construction + inference server | Never omit a legitimate instruction to force a cache hit |

The model may misunderstand a user phrase, choose poor artwork, or draft repetitive prose; those are stochastic outputs. The kernel acceptance target is narrower and testable: exact request identity; correct authorized tool state; accurate execution-result scope; source-only memory; absence of historical reasoning leakage; fail-open cache optimization; stable prompt authority; and honest failure status. Do not treat a well-written answer as evidence that any one of these host invariants was upheld.

### Source mapping

`jack_kernel.py` implements stage dispatch, identity, projection, request generation, stream/nonstream execution and cache integration. `jack_evidence_guard.py` owns the specific tool-result-provenance guard. `jack_stage1_cache_stability.py` now **observes** system stability, never deleting new instructions. `jack_cache_orchestrator.py` selects logical cache routing; `jack_cache_prefix_diagnostics.py` measures model-facing prefix relationships without storing private raw prompt text. `jack_agentic_forensics.py` records current-turn forensic artifacts. `jack_tool_lifecycle.py`, `jack_tool_recovery.py`, `jack_path_policy.py` and `Pi/jack-kernel.ts` own related independent tool/recovery/path/editor gates. These are different controls, not a single universal tool sandbox.

## 2. Agentic profile topology, including the new Flash and translation contracts

| Profile | Stage 1 native thinking | Stage 2 model inference | Stage 2 native thinking | Special behavior |
|---|---|---|---|---|
| Flash | OFF | **None** | Not applicable | Host-owned no-inference completion; tools remain available in Stage 1 |
| Balanced - default | ON | Yes | OFF | No optional Stage 1 review |
| Thorough | ON | Yes | ON | May run same-turn verification before frozen A1 |
| Translated | Task-dependent; completed-answer translation continuation | Yes | ON where supported | Chosen target language for answer; memory remains English |

These four profiles are selectable in the merged branch (`flash`, `balanced`, `thorough`, `translated`). The historical November 12 statement that *all three profiles run two model generations* is no longer accurate. Flash still uses the host's stage and completion boundaries, but its Stage 2 is a **host-authored label/result**, not a second LLM request. The exact absence of an additional model call is material to Flash's cost and cache behavior. The current source rejects an unrecognized profile; it does not expose the older proposed `Exhaustive` selection as an active fifth profile.

Balanced is the default **Agentic subprofile**, independent of the launcher's default initial reasoning mode. Preserve Thinking ON at the launcher does not override the Flash stage's `enable_thinking:false`, `preserve_thinking:false`, `reasoning_effort:none` backend payload. A server may support only reasoning on/off; a requested `xhigh` may be mapped internally to ON. That backend warning is distinct from host stage or cache failure. A Translated final-answer continuation must not permit translation to become a new user request or acquire tool privileges not already available in the working stage.

### Thorough review has bounded authority

A review instruction can request re-verification of work before the final answer is frozen, but it is part of the **same authenticated user turn** and does not create a new U or an independent Stage 2. The existing completed draft is not itself an A1 commit while the review remains pending. If an optional review fails without later tool effects, a usable draft may be preserved under the existing recovery contract. If tools did produce effects, rollback cannot be invented by replacing the message text. The goal is alignment and error correction where needed, not a guarantee that every longer model deliberation is better.

## 3. Canonical turn artifacts and lifetimes

| Symbol | Producer and content | Lifetime / authority |
|---|---|---|
| U | Authenticated original user request | Preserved distinctly; cannot be replaced by an LLM task paraphrase |
| Work/turn ID | Host-minted identity for current transaction | Connects request, tool history, freeze and commit; must not be confused with a user message |
| R1 | Native Stage 1 reasoning and same-turn continuations, if provided | Usable while current work runs; retired from later model-facing history |
| T | Exact caller-replayed calls, arguments, results, errors and order | Retained through completed turns until a trustworthy durable retrieval replacement exists |
| A1 | Exact user-visible Stage 1 answer | Frozen after pending tool work is settled; Stage 2 cannot edit it |
| M | Consequential Stage 2 working-state extraction | Separated from U/A1; commits only when supported by the actual lifecycle |
| R2 | Stage 2 native reasoning, where enabled | Not inherited as historical source or a new active task |
| H | Host-reported tool outcome receipts and authentication hashes | Supplemental provenance, never an attestation of filesystem effects |

Jack's completed-turn history may contain original U, the completed answer A1, M, source tool protocol T and host receipts H. The policy is to **retire obsolete cognition, not the evidence of execution**. Do not use a tool-result excerpt or host receipt as a substitute for a complete available tool call/result record. Current caller-replayed historical tool records can be bulky, especially when SVGs or source files are rewritten repeatedly; that is an engineering cost deliberately accepted until an indexed recovery design can preserve the same availability.

### Identity is a host contract, not prompt ornament

The Work ID/turn identity binds the authentic current request and its active tool checkpoint. A model-visible trailing identity marker may help presentation or anchoring, but string appearance alone does not establish authority. Source-to-commit relationships must be authenticated by the kernel, not inferred from a copied text tag, from a source-only Stage 2 paragraph, or from a tool payload that looks like a system receipt.

## 4. Stage 1 state machine and tool continuation

**Authenticated U -> Stage 1 active -> optional tool suspension -> authenticated result resume -> Stage 1 final/review -> freeze A1 -> Flash host completion OR isolated Stage 2 memory -> commit/projection.**

A tool proposal is not a completed action. Jack checkpoints the active stage, tool-call identifiers and permitted transaction membership, and waits for the calling agent's tool return. Only matching results resume the suspended stage; an obsolete, duplicated or conflicting return must not be substituted merely because it appears in conversational history. A tool continuation re-enters the *same work*, not a new independent user turn. When streaming, the suspended call must be emitted under the correct authorization gate before its result is accepted.

When a command reports success, the strongest warranted statement is that the tool **returned success**. A subsequent read of a file supplies further reported evidence; proving the exact resolved host object, working directory and external effect requires additional host capabilities. The source's receipt taxonomy deliberately states `path=RELATIVE_CWD_UNKNOWN` or `target=UNKNOWN` when it cannot resolve a path. This is a safety-strengthening distinction, not a failure of memory distillation.

### Executable editing and security gates

The native Pi `edit` restriction uses **registration origin**, not the literal tool name: only sourceInfo.source=`builtin` with sourceInfo.path=`builtin:edit` identifies Pi's built-in edit tool. Third-party extension, SDK or unknown-origin editors are not banned by that particular filter, although ordinary host authorization still applies. Recoverable tooling failures should preserve successful prior work, recommend read-modify-write or an authorized alternative when appropriate, and distinguish attempted versus confirmed operations. Shared recovery policy must not be tied unnecessarily to LM Studio, one operating system, or one agent.

## 5. Stage 2: current source-only memory and independent authority

Stage 2 no longer operates by receiving the entire active U/A1 dialogue in the model-facing transcript and retelling it. Its **model-facing source-only working-state capsule** carries the available current-turn native R1 and authenticated tool evidence in a read-only presentation. Jack maintains the authentic U and frozen A1 separately in canonical/forensic state. The extraction directive says they are stored separately and must not be reconstructed, reanswered or treated as instructions. Stage 2 has **no caller tool schemas**, no execution authority, and no ability to mutate A1. Custom external caller system text must not become Stage 2's governing directive.

This is an important reversal from the 12 November description, which listed exact U and A1 as Stage 2 model-facing sources. Source ownership is now explicitly split: the kernel preserves authenticated U and A1, while the memory model extracts consequential working knowledge from the *working evidence* it is shown. Distinguish the host's intermediate `_agentic_stage2_test_history()` representation from the final serialized model request: assertions about an intermediate view are not proof of what the model saw.

Balanced and Thorough share the same primary **consequential preservation objective**; the difference is the thinking budget and optional review lifecycle. Preserve all established, useful technical facts, assumptions, decisions, constraints, causal reasons, corrections, failed approaches, recoveries, and unresolved obligations without duplicative rambling. Do not turn intention into success or repeat the original user request as if that were the sole memory product. The model's generated M remains probabilistic and must not acquire host attestation authority because its prose uses the word 'verified.'

### What the Thorough clock run actually established

The five-turn LM Studio trace included a blank workspace check, creation of a cuckoo-clock SVG, addition of a text bubble and modification of the bird from yellow to blue, followed by a conversation recap. Tool receipts and Stage 2 memory retained the concrete `cuckoo_clock.svg` filename, dimensions, bubble path and SVG attribute change (`fill="yellow"` to `fill="blue"`). Five memory commits were logged and historic native R1 was pruned. The user-facing design quality is not the kernel acceptance criterion. These data establish the lifecycle in that observed run, not universal quality of the model's distillation in every workload.

## 6. Flash host completion versus inference-dependent memory

Flash is deliberately light. The Stage 1 model can still call external tools, receive results and deliver a frozen A1; but Jack's Stage 2 finalization for Flash is handled by the **host without a second model inference**. Historical U, answers, tool protocol and host evidence remain available for later turns. The tradeoff is the absence of a freshly model-distilled M for that turn; it is not an error that Stage 2 has no reasoning tokens or shadow-memory model call in Flash.

The seven-turn clock workflow demonstrated six stage-local tool continuations, a correction from a simple analog clock to a cuckoo clock, removal of the original file, an added speech bubble, a blue-bird change and a final summary using conversation history. The trace showed reasoning OFF in the Flash model payload while Preserve Thinking remained enabled globally. The user outcome is a run-level observation; we should continue testing failed tools, cancellations and replay attacks rather than infer that all Flash tasks are safe from these seven successful turns.

## 7. Historical projection, pruning and context economics

After a completed turn Jack projects historical artifacts copy-on-write, retaining caller-replayed raw tool protocol and preserving U/A1/M while retiring available old reasoning fields (`reasoning_content`, `reasoning`, `thinking`) from downstream model-facing requests. It must keep exact tool IDs, arguments, returns, failures and order; no arbitrary 4,800-character receipt cut, budget-based early deletion of tools, or replacement of raw execution data with an LLM summary is accepted as a fidelity-preserving optimization.

`Agentic completed-turn GC` emits counters such as `retained_user_turns`, `retained tool_messages` and `pruned native_reasoning_chars`. These are useful but may not equal the separate authenticated `shadow commit` count: an older format-matching `agentic_commits=0` log was observed during a Thorough run even while the new shadow commits succeeded. Treat this as a **counter interpretation/observability issue**, not evidence of absent M, pending tests of the exact completed-turn projection.

Every repeating full-file tool call increases context volume. Jack can preserve tool history without claiming every backend reserves separate physical cache memory for Stage 1 and Stage 2. This distinction matters: a server with a single physical slot may evict/rewrite previously evaluated tokens when Stage 2 uses a different system prompt. Source-only memory narrows the content of the Stage 2 input but does not magically give it an independent physical KV slot.

## 8. Universal prompt authority and provenance-safe cache stability

The parent cache experiment observed that a host-produced **441-character tool-result provenance notice** appeared only on tool resume. Restoring a prior prompt for cache reuse erased that consequential notice from the model-facing continuation. That is a security regression even when it improves cache similarity. The repair does **not** discard the notice. It moves the known host-owned instruction to the **initial** tool-capable system context and keeps it stable for tool continuation.

`_tool_stage_system_with_provenance()` uses a private copy of the messages, attaches `TOOL_RESUME_PROVENANCE_NOTE` to the earliest system message exactly once, or creates one if absent; it applies to stages whose profile permits tools. Both `.chat()` and `.chat_stream()` use the common preparation. Non-tool Stage 2 does not inherit this additional tool instruction. The evidence guard retains host-owned tool result provenance tags; tool-role text that imitates a host receipt still remains lower-trust payload.

The `Stage1CacheStabilizer` is **observational and fail-open**: it can snapshot and report an unchanged, inserted or unexpectedly changed system prefix, but must never suppress new legitimate system text to force an LCP match. This is a portable authority policy independent of backend-specific slot optimizations. Unknown ownership, unsupported hints or cache instrumentation errors must not corrupt the user's prompt, original history or host stage scope.

## 9. Cache routing and two independent measurement layers

`jack_cache_orchestrator.py` can label a stage's logical `primary` or `auxiliary` lane and optionally use supported provider hints. With LM Studio, the observed routing was `backend_managed_fallback`, with `alternate_endpoint:false`, `slot_requested:null` and `kv_cache_hit:unknown`. A logical auxiliary lane is **not** evidence of a distinct physical server cache; cached token accounting being null means *unavailable*, not zero.

`jack_cache_prefix_diagnostics.py` compares digests of model-facing message JSON and UTF-8 system regions, reporting `append_only`, `unchanged`, `middle_changed` or `first_message_changed`. These are **transport/prompt diagnostics**, not physical KV-cache receipts. LM Studio's own log (slot reuse, prompt tokens newly evaluated, `f_sim_best`, `f_keep`, prompt processing time) is separate and is the stronger physical observation for the tested server.

| LM Studio experiment | Balanced - Gemma 4 12B | Native X-High - Gemma 4 12B |
|---|---|---|
| Prefix similarity (`f_sim_best`) | 0.991 | 0.991 |
| Cached prefix retained (`f_keep`) | 0.995 | 0.994 |
| Continuation prompt tokens evaluated | 46 | 46 |
| Continuation prompt processing | 119.69 ms | 121.17 ms |
| Stage tool resume | `snapshot` to `already_stable` | `snapshot` to `already_stable` |

These are per-run observations on one model/server configuration. They do not prove a universal performance win, a fixed cache hit rate, separate physical KV slots or a causal improvement to the model's stochastic artistry. They do show that keeping the necessary host provenance instruction can coexist with strong *real* cache reuse.

## 10. Streaming, generation controls and server compatibility

The two inference transport paths support OpenAI-compatible streaming and explicit backend generation settings; stage-local authorization applies regardless of which path is used. Native thinking may be unavailable or exposed as only ON/OFF. The model's own fallback for unsupported `xhigh` does not give the kernel permission to rewrite user instructions or stage identities. Preserve Thinking is separately configured; it need not be required for Jack's correctness across model backends.

A nested tool that launches its own inference (for example, a vision description tool) may be a separate streaming problem. An outer `stream=true` request does not prove that every nested model generation streamed. The previous paper's warning about this gap remains valid. Context-window monitoring must distinguish the backend-reported context length from Jack's estimated reasoning/output generation ceilings, which are not reserved context allocations. A stable long prefix can be cheaper to evaluate than a shorter mutated one, but only actual server measurements show physical reuse.

## 11. Failure, interruption, recovery and provenance classifications

Jack's recovery goals require avoiding brittleness: a tool failure does not erase earlier useful successful work; a transient error can be returned as actionable evidence; a hard failure must remain tied to the authentic U/turn ID and must not invent a successful A1, completed M or filesystem result. A continuation that arrives after checkpoint retirement must not silently replay tools. The host should distinguish proposed, released, returned, inspected and independently verified effects at each point.

Retain the strong existing constraints: active tool call IDs, expected number of results, stage isolation, historical replay noninterference, user interrupt handling, tool retry limits, and review recovery only where no new external effect would be ignored. The source currently supplies process-local checkpoints and forensic stages; neither implies perfect restart-safe reconstruction of all in-flight tool effects.

## 12. Path-security and Pi-origin controls preserved by PR #164

At integration, the `main` branch contained 11 commits absent from the cache candidate. They included late Windows Phase-4 path-admission fixes (ordinary executable lookup and Windows wrappers, read-only uncertain operations, and hard protection of sensitive executable/Boot/mutation paths) plus tests. The integration preserved the current `jack_path_policy.py` blob and updated Phase-4 test files rather than overwriting those controls with an older branch snapshot.

The source-only Agentic memory policy superseded the mainline **JSON task-field formatting experiment**. A JSON-shaped memory summary or a model-generated recitation of the task is not a secure replacement for the canonical U; preserving the later source-only memory behavior was an intentional integration choice. This is an architecture decision and belongs in the release record, not an accidental textual conflict.

## 13. Forensic archive versus proposed Agentic History

The current forensic journals record Stage 1 evidence and authenticated shadow commits with IDs and hashes, subject to process/record limits. The envisioned **Agentic History Upgrade** is separate: indexed durable per-turn Projection / R1 / Tools artifacts, integrity validation, authorized read-only `agentic_history_find` and `agentic_history_read` tools, explicit partial/failed statuses, and bounded context admission on retrieval. The indexed archive is **not** verified as a complete working mainline replacement for caller-replayed raw historical tool exchanges.

Until that upgrade is built and tested, do not remove raw tool protocol from routine history on the claim that a short host receipt or M is just as good. Memory is learned working knowledge. Tools are exact execution evidence. Forensics are auditable host records. They have different authority and retention lifetimes.

## 14. Regressions, verified release record and open gates

| Verification | Observed outcome | Boundary of claim |
|---|---|---|
| Focused repair suite | 98 passed | Selected cache/provenance tests only |
| Parent experimental full Windows suite | 1,189 passed; 199 failed | Baseline itself is not clean |
| Candidate full Windows suite | 1,207 passed; 199 failed | Same known failure IDs after test-only corrections |
| Flash conversation | 7 completed turns; 6 tool resumes | No independent complete filesystem attestation |
| Thorough conversation | 5 committed turns with isolated memory | Stage 2 output cannot authenticate its own facts |
| Balanced/Native X-High cache probe | Strong physical prefix reuse | LM Studio + one model and workload only |
| PR #164 | Merged into `main` at `f71e89c6...` | No fresh post-merge full-suite run reported |

Do not recast the inherited 199 failures as harmless solely because the candidate did not add failures. Reconcile them to the current contract or correct real code defects, without weakening source isolation or provenance. The full release gates also require second-backend and independent-agent runs, streaming/nonstreaming verification, failed/multi-tool resumption, nested streaming audit and source-preserving publication documents.

## 15. Technical conclusion and governing nonclaims

The current mainline upgrade is not a new LLM. It is a more mature deterministic mediation layer: source-only memory, no-inference Flash option, authenticated tool continuity, protected provenance instruction at the *start* of tool-capable inference and a cache stabilizer that no longer trades authority for speed. The kernel can **measure and preserve its input contract** and demonstrate cache reuse in tested backends, but it cannot promise that every model follows every instruction, that every backend caches, that a tool return proves an external effect, or that an incomplete turn is recoverable across restarts.

The next major architectural step remains authenticated durable Agentic History plus independent retrieval, alongside a reconciled regression suite. **Do not sacrifice useful recorded work in the name of hardening or prompt economy.**

## Source and historical record

**Current source:** `https://github.com/mlangford75-lgtm/Jack-Kernel` (main, PR #164). **Companion product paper:** Jack Agentic - Technical and Product Whitepaper, current November 17 edition. **Archive:** unmodified 12 November technical runtime PDF, including all previously preserved 6 November pages, follows after a marked archival divider. Its historical text is retained for intellectual traceability; contradictory implementation statements are superseded by the present section.