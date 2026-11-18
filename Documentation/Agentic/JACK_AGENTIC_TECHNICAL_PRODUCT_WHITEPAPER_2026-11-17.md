# JACK AGENTIC
## Technical & Product Whitepaper
**The provenance-safe, source-only memory architecture | 17 November 2026**

**Jonathan Michael Langford | Jack Kernel project**

**Reason when it is useful. Preserve consequential knowledge. Keep execution evidence authentic. Never trade instruction authority for a cache hit.**

This edition is a **fully developed current paper**, not a brief addendum. It maintains the architecture, distinctions, historical results, release reservations and product reasoning carried forward from the November 12 paper, while directly integrating the new Flash, Balanced, Thorough and Translated modes, Stage 2 source isolation and common cache/provenance path. The complete prior paper, including its November 6 original, is preserved page-for-page after the archival divider.

**Implementation state:** GitHub PR #164 merged to `main` on 17 November 2026 at `f71e89c6fcfdce32d6a8ae1937e9084d2ced4f86`. **Validation qualification:** the last candidate full Windows run reported 1,207 passing tests and 199 inherited failures, not a clean suite.

## Editorial framework: what is being claimed

Jack is a **local-first deterministic runtime around probabilistic inference**. It stands between an application or calling agent and a backend exposing an OpenAI-compatible interface. It does not replace the LLM, execute the caller's tools on its own, or make an agent's chosen workflow correct by fiat. The model can propose a plan, a command, a file and a response; Jack deterministically decides which stage is authorized to issue which proposal, what tool-result transaction may resume it, which answer is frozen, how evidence is labeled, and what information may survive into later work. The governing motto remains **probabilistic cognition may propose, but deterministic software must dispose**.

The November 12 edition had already established a crucial distinction: model reasoning and exact tool-execution records are **not interchangeable forms of memory**. The current architecture deepens that separation and adds a second: a **cache optimization cannot erase an authenticated host instruction**. With the two distinctions combined, Jack can offer flexible compute profiles without discarding useful work or weakening the host's prompt-authority boundary.

Claims in this document refer to source-level implementation and specific Windows/Gemma/LM Studio observations. A model's aesthetic success, fluent tone, or willingness to say 'I verified' is not a deterministic acceptance result. Neither one backend's cache behavior nor an incomplete regression suite proves universal model, server, agent or platform compatibility.

## 1. Executive overview: an agentic chassis, not an agent

Traditional long-running LLM work accumulates task instructions, model drafts, tool outputs, interim corrections and unrelated stale reasoning in a shared context. An LLM may read a proposed write as a completed write, a stale answer as the live user request, or low-trust tool text as if it were a system instruction. Simply retaining everything is expensive and confusing; simply summarizing everything can delete the exact evidence a future agent needs. Jack handles the lifetimes separately: the **current working cognition** is allowed to be rich; **completed knowledge** is distilled and bounded by the authentic turn; and **execution records** retain their original IDs, arguments and returns.

The deterministic chassis owns turn/work identity, stage-local tool checkpoints, prompt reconstruction, answer freeze, memory authority, history projection, certain security restrictions and audit records. The caller owns the actual project folder, operating-system tools, other agents, and effects that occur outside Jack. The model owns stochastic wording and choices inside the constraints. This is a product architecture for making comparatively small local models more dependable as participants in complex workflows **without claiming to remove their stochastic errors**.

| Layer | What it owns | What it cannot assert by itself |
|---|---|---|
| User and calling agent | Authentic task, tool implementation, workspace, external side effects | That an unverified model claim is a completed effect |
| Jack Kernel | Stage and tool authentication, prompt authority, frozen answer, memory/forensics and cache input shaping | That remote/OS effects occurred simply because a tool returned success |
| LLM backend | Generated reasoning, proposed tool calls, response and memory text, physical KV cache | Authority over stage identity, tool receipts or host policy |

## 2. The evolution from the November 6 and November 12 architecture

The November 6 edition established two-pass Agentic work, a Stage 1 tool loop, a frozen answer and separate Stage 2 memory. It also carried a historical proposition that completed tool protocol need not stay in routine context. That statement was superseded on November 12: when an agent revisits a real project, every tool argument, result, error and correction can matter, and untrusted summarization is not a substitute for those exact facts. The November 12 revision restored complete caller-replayed historical tool history while retiring stale native reasoning, clarified Pi-native edit origin, and documented failure/streaming boundaries.

The November 17 mainline then made four further changes of product significance. First, **Flash** became a genuine no-Stage-2-model option while preserving host finalization. Second, the model-facing Stage 2 memory source became **source-only working evidence** instead of replayed user/answer dialogue; canonical U and A1 are preserved separately. Third, the **Translated** profile joined Flash, Balanced and Thorough. Fourth, a new common tool-stage mechanism moved critical provenance guidance into the *initial* system prefix and made cache optimization fail open rather than remove security text.

These changes are not merely renamed prompts. They change compute cost, source visibility, authority semantics and the conditions under which long workflows can reuse an inference server's actual prompt-prefix cache. The original two-layer idea - work now, remember later - survives, but the precise implementation is no longer adequately described by saying every profile always makes two LLM calls.

## 3. Four compute profiles with one deterministic chassis

| Profile | Stage 1 cognition | Memory/finalization | Practical purpose |
|---|---|---|---|
| Flash | No native thinking, full authorized tool loop | Host finalization, **no second inference** | Fast, routine, tool-heavy work with continuous historical evidence |
| Balanced (default) | Native reasoning ON, no optional review | Isolated tools-off Stage 2, native thinking OFF | General-purpose work and compact consequential state |
| Thorough | Native reasoning ON; optional same-turn verification | Isolated tools-off Stage 2, native thinking ON | Involved multi-step work where memory extraction deserves added compute |
| Translated | Agentic work plus language-specific final continuation | Source-only working-state memory in English | Multilingual delivery without changing canonical tool and memory identity |

All profiles run through Jack's host-controlled stage machinery, but **not all profiles perform an additional Stage 2 inference**. Flash is intentionally simpler: Jack still knows the authentic U, A1, T and host status, but does not ask a second LLM to distill a new M. Balanced's default refers to the Agentic ladder, not the global launcher mode. Thorough's optional review is a *same-turn continuation* before answer freezing, not a license to invent a second user objective. Translated retains technical identifiers, paths and source quotations unchanged while the final answer may be rendered in the chosen human language.

The model may provide a backend-specific warning when an effort level such as `xhigh` is not natively supported. That is a backend compatibility property, not a reason to rewrite the author's prompt. Jack's authorized controls and task/turn identity remain the same. An older proposal for a selectable Exhaustive profile is not present as an active option in the reviewed mainline source.

### Why profile separation matters to small local models

A small model may excel at an uncomplicated command or edit but waste time in repeated retrospective reasoning. Flash avoids that second generation entirely. Balanced offers a different tradeoff: one active reasoning pass, followed by a cheaper memory pass. Thorough makes memory extraction itself a deliberative operation. The host's security and tool-evidence contract does not change with these choices. The system therefore offers compute scaling without requiring that every model behave the same way or that every completed turn carry an equally expensive cognition transcript.

## 4. The three different kinds of information an agent needs

**(a) Authentic task and completed outcome.** U is the exact current user request; A1 is the completed answer frozen when the authorized Stage 1 is finished. Neither should be substituted with a model's later paraphrase. In particular, a generated Stage 2 task summary is not the authenticated request and has no new request authority.

**(b) Consequential working knowledge.** R1 may contain insights, false starts and unresolved blockers. Stage 2 extracts M from available current-turn native reasoning and authenticated host/tool evidence. M should preserve facts, assumptions, decisions, causal relationships, exact names and file paths, repaired failures and remaining work, while leaving behind redundant deliberation and the tendency to imitate an old answer's format. Past R1/R2 is retired after the turn because expired reasoning can confuse the next model pass.

**(c) Exact execution evidence.** T is the complete caller-replayed protocol of tool proposals, arguments, results, errors and ordering. H is a separate host receipt describing authentication and the limited known outcome. T must not silently disappear merely because M seems to summarize it. The difference between a tool return and a verified on-disk effect persists even when the memory model writes confident prose. Maintaining both preserves the causal record and allows later work to continue from what actually happened.

This triad - **U/A1**, **M**, and **T/H** - is the heart of the product. It rejects both extremes: dumping endless obsolete thoughts into every request and using a short, fallible summary to erase exact tool history.

## 5. What changed in Stage 2: source-only memory

The most consequential memory change since November 12 concerns *what the second inference is allowed to see as task context*. Current Stage 2 operates on a **read-only working-state capsule** drawn from current-turn R1 and authenticated tool evidence. Jack stores the original user request and completed answer independently, and the memory directive explicitly says those records are not to be reconstructed, retold or answered. The model is asked to extract durable state from the evidence it is shown, not to turn a frozen assistant response into a new dialogue or to solve the original request again.

Stage 2 has no tool schemas and cannot execute. External custom system instructions that governed Stage 1 do not become Stage 2's system authority. Stage 2's generated text M is a reusable account, **not** a new source of truth about tool effects. Flash lacks the separate Stage 2 inference altogether; its host finalization preserves the ordinary turn artifacts without pretending to produce the same sort of model-authored distillation.

A strong memory should tell the following turn not simply that a clock exists, but that the file is `cuckoo_clock.svg`, which element was altered, what the previous color was, which new attribute was written, and whether the file was independently inspected. The observed Thorough memory did preserve `fill="yellow"` becoming `fill="blue"`, the speech bubble's geometry and the file's dimensions. These exact literals could help a later edit, but the write return remains evidence of a reported action, not proof that the kernel itself observed a filesystem mutation.

### The durable identity boundary

The authenticated Work/turn ID links the source request, tool continuations, frozen answer and memory commit. The model-facing label is a convenience; it is not the host identity authority. A malicious tool payload could repeat an ID or use host-sounding words; its role remains untrusted tool payload. This is why current Stage 2 memory is not simply 'whatever text arrived last', and why Jack retains original U, A1 and host receipts outside the probabilistic summary.

## 6. The full tool protocol stays useful after the model stops thinking

An autonomous task can write a source file, receive an error, recover by rewriting, read it back, and then be asked to improve the same file several turns later. If the system deletes the old tool arguments and results early, the next stage may know only that 'the file was fixed', not *which* file, *how* it failed, or *what* recovery was used. Jack's November 12 decision to retain the complete caller-replayed raw tool protocol is still correct, and the November 17 design continues it.

Host receipts add hashes and outcome categories, but cannot replace raw T. This is a deliberate cost. In one earlier workload, repeated full-file writes pushed model-facing context to about 52,000 tokens without backend truncation. Context can grow large despite a small amount of new user content; yet keeping exact evidence prevents brittle loss of useful actions. A later Agentic History archive can reduce repeated transmission **only** if authenticated search, read-only retrieval, identity, integrity and crash-recovery gates make the evidence continuously available.

A read-back is useful but its authority must also be understood correctly: a tool says it read a file and returned its contents; that is stronger evidence than a model's plan to write it, but still not independent object identity verification. Jack should be precise rather than falsely confident, and recoverable uncertainty should not cause otherwise useful work to be discarded.

## 7. Security without a false choice against prompt-cache reuse

The cache experiment exposed a concrete authority flaw. During an earlier implementation, a **441-character provenance instruction** was added to a system prompt only after a tool returned. A cache stabilizer saw this as a clean insertion and removed it to restore byte-for-byte prefix identity. LM Studio then showed better reuse, but a necessary instruction separating **untrusted tool-result text** from **host-issued metadata** had disappeared from the model-facing request. An optimization had crossed an authority boundary.

The current correction does the opposite: the known host provenance notice is added to the **first** system context of the initial inference for every tool-capable backend stage, and is carried unchanged on the tool continuation. It is added once; the caller's original dictionaries and content are not mutated. The shared preparation is used for both streaming and nonstreaming. The stabilizer observes prefix drift but must never throw away a new legitimate system instruction to buy a KV-cache hit.

This fix is universal in *policy* along Jack's shared tool-capable inference path. It is not evidence that every external agent uses that path or that every server implements the same physical KV-cache behavior. Lower-trust tool text remains lower trust even when it includes forged host receipt strings. Promoting a cache hit over an authenticated security message would invalidate the central doctrine of host authority.

## 8. Physical cache measurement versus source-level stability

Jack can compare model-facing message JSON, system instruction regions and hashed prefixes, and can record whether a continuation is `append_only`, `unchanged`, or unexpectedly modified. This proves something important about the **prompt**. It does not prove the server's real GPU cache contents. Actual physical reuse requires observing server behavior such as prompt tokens reevaluated, slot selection, retained prefix fraction and time spent on prefill. For LM Studio, these measurements were available in the November 17 tests.

| Live probe, LM Studio / Gemma-4-12B | Balanced | Native X-High |
|---|---|---|
| Prefix similarity `f_sim_best` | 0.991 | 0.991 |
| Fraction retained `f_keep` | 0.995 | 0.994 |
| Prompt tokens newly evaluated at tool resume | 46 | 46 |
| Tool-resume prompt processing | 119.69 ms | 121.17 ms |
| Host cache-stage relation | `snapshot` then `already_stable` | `snapshot` then `already_stable` |

The two modes reached comparable prompt-cache results while the provenance instruction remained in force. Jack's cache router identified logical `primary` and `auxiliary` stages but reported `backend_managed_fallback`, `slot_requested:null` and `kv_cache_hit:unknown`. Those labels do **not** certify a separate physical Stage 2 cache; an inference server can reuse or evict the same slot as it sees fit. Better cache use is an observed capability, not a blanket performance guarantee or a proxy for model output quality.

## 9. Multi-turn evidence: what Flash and Thorough actually demonstrated

**Flash, seven turns.** The user asked to inspect an empty workspace, generate a coo-coo clock, corrected an initial misunderstanding, removed the first clock, added a speech bubble, changed the bird's color and asked for a recap. Jack delivered seven completed turns with six tool continuations and no separate Stage 2 LLM request. LM Studio reported 53 newly evaluated prompt tokens on the last turn despite a much larger accumulated prompt. The kernel-level result is continuity of the caller and tool protocol with inexpensive cached subsequent turns; the initial artistic mistake is a model choice, not a failed host transition.

**Thorough, five turns.** The model checked a workspace, created a cuckoo clock, added a speech bubble, changed the bird to blue and summarized the work. The host logged five Stage 2 shadow commits, isolated tools-off second-stage requests and retention of useful technical state. A Stage 2 memory recorded the exact changed SVG circle attribute; the host retained associated tool receipts and historical protocol. The experiment also exposed a counter-format mismatch: `agentic_commits=0` appeared in an older completed-turn GC counter despite successful newer shadow commits. The discrepancy is an observability issue to test, not proof that the memories were missing.

These runs used the same local server and Gemma family and were not matched scientific controls for stochastic output quality. Their value lies in stage identity, tool-continuation behavior, lossless evidence, effective memory extraction, and recorded physical cache performance. The tests support retaining this architecture; they do not justify relaxing other release gates or declaring every backend compatible.

## 10. What Jack protects, and what it cannot promise

The kernel can block a stale tool continuation, distinguish untrusted tool text from host instructions, remove old native reasoning from the future model-facing projection, keep authentic tool protocol, freeze a completed answer and limit execution authority by stage. It can apply separate Windows Phase-4 path-admission rules and Pi editor-origin restrictions. These controls reduce particular hazards while **not making Jack an operating-system sandbox, a shell-effects oracle or a proof of real-world effect**.

Jack's Pi edit-origin filter intentionally applies to the positively identified built-in Pi editor, not every tool called `edit`. Newer mainline Windows Phase-4 fixes protect sensitive path behavior and preserve recoverable read-only uncertainty; the PR #164 integration retained these corrections and their tests. Cache and prompt stability do not supersede those security gates. When tools fail, the host should preserve useful work, mark status appropriately and offer a bounded recovery, not punish the user with brittle loss of context.

The failure/cancellation boundary matters commercially as well as technically: an agent that says it finished when a tool failed is less useful than one that preserves partial progress and explains exactly which step remains open. A model cannot grant itself completion or forge a successful memory commit by using the right words. Where process-local recovery is all that has been established, that limitation must be stated.

## 11. Product implications for local-first development

Jack's value is **chassis-level consistency** across heterogeneous models and caller workflows. A user can choose cheap fast cognition, balanced cognition plus memory, more expensive thorough reasoning, or translation without rebuilding the system's core tool-evidence logic for each model. The important improvement is not a particular seed or an aesthetically better cuckoo clock; it is that the kernel keeps task identity, tool evidence and output ownership intact while letting an LLM remain probabilistic.

The design also separates two distinct economic levers. **Memory retirement** reduces repeated old cognitive traces but deliberately keeps exact tool history. **Prompt-prefix stability** makes that retained history less expensive on servers that actually cache long identical prefixes. These levers are compatible but not identical: the first is a representation policy, the second a cache-alignment policy. Further context savings should come from an authenticated indexed archive, not a forced deletion of raw tool events.

A failure to preserve a legitimate security instruction would make the observed prefill improvement misleading. The November 17 provenance repair therefore strengthens the product thesis: **deterministic authority is the invariant, cache performance is a measured optimization**. That is more important than a marginal reduction in milliseconds on one backend.

## 12. Evidence status and release honesty

| Milestone | What was established | What remains open |
|---|---|---|
| November 12 mainline | Stage 1/2 separation, historical tool fidelity and editor origin restrictions | Later profile and source-only changes not yet present |
| Focused provenance-cache tests | 98 passes on experimental repair | Does not validate all modes and providers |
| Candidate Windows suite | 1,207 passes / 199 inherited failures | Full suite is not green; reconcile failures substantively |
| Live Balanced / Native X-High | 99.5% / 99.4% retained prefix on LM Studio | Different agents and servers untested |
| Flash / Thorough clock sessions | Successful tool continuations, Flash's no second model, Thorough commits | Failed tools and long-run adversarial recovery need further coverage |
| PR #164 | Merged to `main` with mainline Phase-4 path fixes retained | Fresh post-merge Windows regression not yet supplied |

It would be false to publish a clean-release claim on the basis of the candidate's matching 199 inherited failures. Those tests may encode obsolete expectations, real unresolved defects, or both. They must be reconciled by examining behavior, not simply deleting assertions that fail. The historical Phase-8 security and other frozen claims remain independently bounded; nothing in this experiment constitutes a new universal integrity certification.

## 13. The next two architectural investments

**First: durable Agentic History with authenticated retrieval.** The proposed archive has distinct per-turn Projection (U/M/A1 and status), R1 (available reasoning) and Tools (chronological execution evidence), keyed to a host-owned ID, with read-only authorized lookup, integrity checks, failure statuses and context-budget admission. It must preserve exact evidence through crashes and later tasks before any routine raw tool history is omitted. The prior 12 November paper correctly described this as proposed, not as a completed production substitute.

**Second: portability and cache isolation validation.** Real second-backend runs, separate independently configured agents, streaming/nonstreaming parity, multi-tool and failed-tool continuations, nested generation streaming and server-side context accounting are required to support broad product claims. If a backend provides independent cache slots for Stage 2, Jack can take advantage of them; if not, it must continue correctly without fabricating isolation or suppressing high-priority instructions.

The appropriate release discipline is to test the chassis contracts independent of whether the language model guessed the next word correctly. A stochastic output need not be identical across trials for a host-side identity, authorization or history-preservation check to be meaningful.

## 14. Conclusion, glossary and provenance record

Jack Agentic has advanced from a two-pass memory concept to a more explicit **authority-and-evidence lifecycle**. Its current form supports Flash without a second model pass, Balanced's efficient retrospective, Thorough's more deliberate extraction, and Translated delivery. It protects authentic turn identity, keeps execution evidence accessible, makes completed answers immutable and demonstrates in a real local test that prompt-cache reuse does not require stripping host safety instructions.

**U:** authenticated user request. **R1:** active native working reasoning. **T:** exact tool protocol. **A1:** frozen answer. **M:** consequential extracted state. **R2:** Stage 2 native reasoning. **H:** host receipt. **Work ID:** host-bound turn identity. **LCP:** longest common prefix, used to reason about possible cache reuse. **Physical KV reuse:** server-observed prompt tokens avoided, not deducible from text similarity alone.

**Mainline evidence:** `https://github.com/mlangford75-lgtm/Jack-Kernel`, PR #164, merged `f71e89c6fcfdce32d6a8ae1937e9084d2ced4f86`. **Companion:** Technical Runtime Specification, November 17 source-aligned edition. **Preservation:** the entire previous November 12 whitepaper (including its original November 6 appendix) follows unchanged, so historical framing, earlier tables, diagrams, and release provenance remain available without being presented as current code behavior.