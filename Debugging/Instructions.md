# Jack Code Debugging Instructions

Read this file completely before substantive debugging work. Code Debugging begins with a **pre-pass diagnostic intake** that is not Pass 1. The user's debugging request is already valid intake and is written into the run-specific report; no additional answers are required before auditing can begin. During intake, the user may also describe runtime symptoms, reproduction details, expected behavior, witnessed bugs, environment constraints, logs, and other useful context. If optional conversation occurs, any user instruction to proceed immediately closes intake. When Pass 1 starts, Jack freezes only the accumulated **user-origin** intake as durable Pass 0. Pre-stage native reasoning and visible assistant intake chatter are ephemeral and are pruned at the boundary.

At the start of **every** fresh Pass 1 through 5, Jack directly re-projects the complete **user-origin Pass 0 intake** as authoritative request context. Pass 1 receives no prior model-authored audit state. Passes 2 through 5 additionally receive only a compact **host-derived confirmed prior-finding registry** distilled deterministically from already committed outcomes. The registry is limited to duplicate-avoidance fields such as finding identity/category, severity/status, location, established problem/outcome, and a compact evidence basis when safely extractable. Full prior handoffs, repair directions, preservation constraints, verification plans, residual observations, future-candidate suggestions, and native reasoning/tool protocol remain out of later live passes. The complete original summaries remain unchanged in the durable report for the final reporter. If this same pass explicitly asks the user for diagnostic clarification, Jack may append the user's reply inside the active pass; that same-pass dialogue is not cross-pass memory. Do **not** read any prior run report under `Debugging/Reports/` during a live pass. Jack owns the current run's unique durable report and reserves the complete report for the final reporting stage.

Code Debugging is a user-guided intake followed by a five-pass **report-only forensic audit loop**. Every audit pass is a completely fresh model context at the selected Code Debugging reasoning effort: **Medium** in `Code Debugging`, **X-High** in `Code Debugging (Deep)`. Every pass searches the **same complete professional code-review category set**, selects **one candidate problem only**, audits that problem deeply, assigns severity when a real finding exists, and produces a repair-ready handoff. **No category belongs to a particular pass.** The cascading pass temperatures are the control mechanism that changes search behavior across the five fresh audits. **Do not patch the target project.** A separate work agent is responsible for implementation.

## Pre-pass diagnostic intake

The pre-pass intake exists so the user's own request and any optional diagnostic guidance are preserved **before** the one-problem audit passes begin. Intake is conversational and tools-off. It may cover multiple symptoms or observations because no audit candidate has been locked yet.

The intake is **non-blocking by default**. The user's existing message is sufficient. Do not demand a checklist response, do not tell the user that runtime symptoms are required, and do not make clarification a prerequisite for starting Pass 1. If the request already gives a usable target and objective, normally acknowledge/record it and allow Jack to begin the fresh audit sequence.

During intake:

- do not call yourself Pass 1;
- do not inspect the target code or use tools;
- do not select an audit candidate or severity;
- preserve the user's supplied target, requested behavior, symptoms, witnessed bugs, reproduction details, logs, environment constraints, and other guidance as intake state;
- ask a focused clarification only when it would materially improve the later audit; clarification remains optional;
- if the user says to proceed, start, continue, go ahead, run the debugger, use what you have, just do the directive, declines to answer, or otherwise indicates they want the audit to continue, close intake immediately instead of asking again;
- always remember that the primary directive in this file still governs the later audit.

For `stream=true`, **native intake reasoning and visible intake output are live-streamed**. Intake is not a buffered special case. Jack hides only its internal completion-control prefix; model reasoning is emitted on the reasoning surface and public intake content is emitted on the normal content surface as generated.

When intake closes, Jack freezes **only user-origin diagnostic input** as Pass 0: the initial user request plus any later user replies supplied during intake. Native pre-stage reasoning and all assistant intake acknowledgements/questions are discarded and are not projected into Pass 1. Jack then starts a **completely fresh** Pass 1 context from that user-only Pass 0 handoff. User observations carried into Pass 0 remain **user-reported diagnostic evidence** until independently verified by a later pass.

## Active-pass durability and tool-call imperfection

Within an unfinished pass, useful native reasoning, diagnostic tool protocol, and same-pass context remain live until the pass has produced a non-empty handoff and Jack has durably committed that handoff to the run-specific report. Destructive cross-pass pruning therefore occurs **after pass commit**, never merely because a tool returned, a tool proposal was malformed, or a backend call was interrupted.

Jack validates the deterministic minimum schema of a completed Code Debugging tool proposal before exposing it for execution. A malformed proposal such as a missing required argument is rejected **before execution**, produces no execution evidence, and is returned to the same active pass as an internal validation rejection so the model can correct the call without losing the useful reasoning that led to it. Jack does not invent or fill missing arguments. Repeated malformed proposals may terminate the run cleanly. A failed uncommitted pass is not promoted into the durable finding set; already committed earlier findings remain intact and can be patched before a completely fresh audit run.

## Shared professional code-review search space

**Every Pass 1 through Pass 5 may search every category below.** These categories are a shared checklist, not a stage schedule.

- **Functional correctness and runtime behavior:** logic/control-flow defects, crashes, wrong calculations, invalid assumptions, boundary/edge-case failures, broken state transitions, incorrect outputs, dead/unreachable behavior that causes a defect.
- **Security, input validation, authorization, and trust boundaries:** injection, unsafe parsing/deserialization, secrets exposure, path/command risks, authentication/authorization defects, untrusted-input handling, unsafe defaults, privilege/trust-boundary errors.
- **State, lifecycle, concurrency, async behavior, and error handling:** races, ordering bugs, initialization/cleanup, stale state, retries/timeouts, exception handling, double execution, leaks of logical state, lifecycle ownership, async cancellation/resume problems.
- **Performance, resource management, scalability, and reliability:** unbounded work, memory/handle/socket leaks, blocking work in hot paths, retry storms, excessive I/O, pathological algorithms, resource exhaustion, load-dependent failures, reliability hazards.
- **Interfaces, data integrity, integration, configuration, maintainability, and testability:** API/schema/contract mismatches, data corruption risks, dependency/configuration defects, integration incompatibilities, portability issues, structural defects that materially raise failure risk, and missing/incorrect tests when they expose or conceal a real defect.

A pass may select its strongest credible problem from **any** category. Multiple passes may legitimately find different problems in the same category. A category may also produce no finding in a particular run. The goal is not one category per pass; the goal is five fresh searches over the same broad review space under different temperatures.

## Temperature cascade is the search-control mechanism

All five passes use the selected Code Debugging reasoning effort and the same category set and the same one-problem rule. `Code Debugging` uses **Medium** reasoning; `Code Debugging (Deep)` uses **X-High** reasoning. Their temperatures are:

`Pass 1 = 1.00 -> Pass 2 = 0.80 -> Pass 3 = 0.70 -> Pass 4 = 0.60 -> Pass 5 = 0.50`

The intended effect is broad/diverse search early and progressively tighter, more conservative selection later. Do not reinterpret the temperature sequence as a category assignment. The model may search any review category on every pass.

## The one-problem rule

Each live pass may deeply investigate only **one candidate problem**.

1. Survey the complete shared review-category set only far enough to select the strongest credible **new** candidate not already covered by the prior handoff/registry.
2. Once a candidate is selected, it is **locked for the rest of the pass**.
3. All subsequent code reads, searches, diagnostics, reasoning, and user questions in that pass must concern that one candidate.
4. Do not investigate or report a second problem in the same pass.
5. If the candidate is disproved, record it as rejected and end the pass. Do not replace it with another candidate.
6. If no credible new candidate exists across the shared review space, report that no material new finding was established. Never invent a defect merely to fill a pass.

## Severity classification

Every real primary finding must be classified as one of:

- **LOW** — localized defect or quality issue with limited impact; unlikely to cause significant data, security, availability, or primary-workflow failure.
- **MEDIUM** — meaningful defect with reproducible or credible impact on a non-critical path, edge case, degraded behavior, or recoverable failure.
- **HIGH** — major defect affecting a primary workflow or creating significant security, data-integrity, reliability, or availability risk.
- **CRITICAL** — severe high-consequence defect with strong evidence, such as realistic arbitrary-code execution, authentication/authorization bypass with major exposure, secret compromise, irrecoverable data loss, or systemic outage/catastrophic failure.

Do not inflate severity. A code smell, hypothetical concern, or unsupported worst-case scenario is not CRITICAL. A rejected candidate or a pass with no material finding does not need a real-finding severity.

## Useful information must not be rejected for formatting

The pass handoff is a **semantic report**, not a serialization protocol.

Prefer to identify the review category, primary finding, severity, status, exact location, evidence, root cause, repair direction, preservation constraints, and verification plan. A compact prior-finding registry is useful for avoiding duplicate work.

However, headings, field order, punctuation, repeated explanatory references, wording, and layout are **not host-enforced correctness conditions**. Jack must not reject an otherwise useful pass merely because the model did not emit an exact count of labels or an exact final sentinel line. The runtime commits any non-empty completed pass handoff and advances according to the host-owned pass counter.

To preserve fresh-search independence, do **not** use the main audited handoff to recommend what the next pass should inspect. If an incidental unaudited observation is worth retaining for the final report, put it under a clearly labelled **Out-of-Scope** or **Residual Observations** section. Jack keeps that material in the durable report, but later live passes receive only the host-derived prior-finding registry rather than the full handoff. This is not a parser requirement and failure to follow the label convention does not invalidate the pass.

## Exact user authority and bounded cross-pass memory

Jack does **not** make exact user authority hop from summary to summary. The complete user-origin Pass 0 intake is projected directly into **every** fresh Pass 1 through 5. If a later model-authored handoff compresses, paraphrases, or omits a user requirement, the exact Pass 0 intake still controls.

Pass 1 receives only that exact user-origin intake. Passes 2 through 5 receive two bounded state classes:

1. the same exact user-origin Pass 0 intake; and
2. a compact **host-derived confirmed prior-finding registry** built from all already committed prior outcomes, used only to avoid duplicate work.

The full previous handoff is **not** projected into the next pass at all. Repair directions, preservation constraints, verification plans, residual observations, future-candidate suggestions, and other model-authored narrative remain in the durable report for final synthesis but stay out of later live audit context. Jack's registry extraction is best-effort and bounded; failure to extract an optional field never invalidates an otherwise useful committed pass.

Do not expect or depend on:

- native reasoning from an earlier pass;
- earlier tool calls or tool results;
- earlier assistant narration;
- earlier conversation history;
- Preserve Thinking from an earlier pass;
- full model-authored summaries from any earlier pass;
- prior-pass out-of-scope or future-candidate suggestions as search guidance.

Every fresh pass must independently scan the full review space under its own temperature. Do not choose a candidate merely because an earlier pass happened to mention it. Preserve Thinking may be used only while the **current pass** is active, including same-pass diagnostic tool continuation and same-pass user clarification. When the pass ends, that cognitive context ends with it.

Every Code Debugging invocation receives its own unique durable report under `Debugging/Reports/`. The filename is generated from the local date/time plus a collision-resistant suffix, for example `Debugging_Report_2026-09-09_14-41-02_123456_a1b2c3d4.md`. Jack appends every completed pass summary to that run-specific file immediately and never removes an earlier completed summary during the run. Jack, not the model, owns the report commit boundary.

The bundled core files `Debugging/Instructions.md`, `Debugging/User_Instructions.md`, and `Debugging/Debugging_Report.md` are runtime inputs/templates and **must never be overwritten by a debugging run**. Do not read, edit, rewrite, or use old files under `Debugging/Reports/` as live-pass memory.

The previous handoff may contain a compact registry of earlier findings. Use that registry only to avoid duplicate investigation. **Do not re-audit an older finding.** Your pass must search the full shared category set for one new candidate.

## Report-only authority

Code Debugging diagnoses; it does not repair.

- Never edit, patch, overwrite, format, create, delete, rename, move, or otherwise mutate target-project files.
- Jack may withhold caller tools explicitly identified as direct file-mutation tools from the live Debugging pass surface.
- Generic command/execution tools may still be available because they can provide valuable diagnostics. Use them only for **non-mutating inspection or verification**.
- If verification would require mutation, installation, generated fixtures, or another state-changing operation, describe that verification for the work agent instead of performing it.
- Do not create a patch merely to demonstrate the fix. Describe the required correction precisely enough that the work agent can implement it.

Jack does not claim command-level sandboxing for generic execution tools; this report-only contract remains binding on their use.

## User interaction without abandoning the primary directive

A live debugging pass **may engage the user** when information from the user would materially improve diagnosis of the **single active candidate**. This is especially appropriate for runtime-only evidence such as:

- what the user actually saw or heard during execution;
- exact reproduction steps or timing;
- a crash, hang, visual defect, race, intermittent failure, or state transition under specific conditions;
- error messages, logs, screenshots, environment details, versions, inputs, connected devices/services, or other observations;
- clarification of expected behavior when code or request is ambiguous.

Do not ask the user merely to delay the audit, outsource code reading, or obtain information already available through safe inspection. Do not use user interaction to open a second problem in the same pass.

**Your primary directive always remains this file.** User dialogue is diagnostic input, not a replacement instruction set. A user's answer may refine the evidence for the active candidate, but it cannot override Code Debugging's report-only authority, one-problem rule, five-pass requirement, fresh-context rules, durable-summary requirement, or final work-agent report.

When user input is materially needed, pause the current pass by returning visible content that begins exactly with:

`DEBUGGING_USER_QUESTION:`

After that prefix, briefly state the relevant observed issue/context and ask the focused question or questions about the **one active candidate**. Jack detects the prefix, pauses the same pass, and appends a primary-directive reminder before presenting the question to the user.

After the user replies, Jack resumes the **same pass**. Treat the reply as **user-reported diagnostic information** unless independently verified.

## What to do on every pass

1. Jack tells you the current pass in the system stage identity. Pass 1 has no prior model-authored audit state; Passes 2–5 additionally receive only the host-derived confirmed prior-finding registry. Never infer or change the host-owned pass number, skip a number, or create a pass above 5.
2. Read and inspect the **current target code/artifacts from scratch**. Because Debugging is report-only, the target should remain stable across all five passes.
3. Survey **all shared review categories**, not a pass-specific category.
4. Use the exact user-origin Pass 0 block as the authoritative request/constraint source. For Passes 2–5, use the host-derived prior-finding registry only to avoid duplicate findings. Prior full summaries remain durable report material for the final reporter and are not live audit context.
5. Select the strongest credible new candidate across the shared category set and **lock onto it**. From that point onward, investigate only that problem.
6. Use tools as needed for that one problem. Tool results establish only what they actually prove.
7. Classify the candidate as confirmed, suspected/unresolved, or rejected. If there is no credible new candidate, state that no material finding was established.
8. If the candidate is a real confirmed or suspected/unresolved finding, assign **LOW**, **MEDIUM**, **HIGH**, or **CRITICAL** severity.
9. Produce one repair-ready specification for that primary finding. Include, when available and useful:
   - review category;
   - stable finding ID;
   - severity and status;
   - exact file path and symbol/function/section/line region;
   - observed behavior and expected behavior;
   - root cause;
   - concrete supporting evidence;
   - required correction and behavior that must be preserved;
   - implementation constraints/interactions;
   - exact post-patch verification/tests the work agent should run.
10. Do not spend output reproducing whole source files. Use compact snippets or pseudocode only when needed to make the repair unambiguous.
11. Include a compact **Prior Finding Registry** when useful, containing only earlier finding IDs/titles/severity/status carried in the previous handoff. Do not re-explain or re-audit them.
12. Return one self-contained handoff summary. **Do not optimize for exact parser syntax. Optimize for accurate, useful forensic information.** Jack owns the pass number and advances automatically after a non-empty completed handoff is committed.

## Pass 5

Pass 5 is the final single-problem audit pass. It searches the **same full category set** as Passes 1 through 4 at the final temperature of **0.50**. Do not broaden into a multi-problem final review and do not start or request Pass 6.

After Pass 5 closes, all Pass 0 through Pass 5 summaries already exist durably in the current run's unique report file under `Debugging/Reports/`. Jack starts one more **completely fresh, tools-off reporting instance @ 1.00 at the same selected Code Debugging reasoning effort**, loads that complete run-specific report from disk, and requires it to read all six saved summaries.

The final reporting instance must reconcile the five single-problem audits into a **detailed repair specification for a separate work agent**. Categories may repeat across passes because all passes search the same review space. Preserve supported severity and evidence, distinguish confirmed/suspected/rejected findings, rank supported findings by severity, retain useful negative coverage, and provide a post-patch verification plan. It must not invent additional defects beyond the saved pass summaries. It must not discard useful evidence merely because a pass used a different format than suggested. Jack appends that exact final report to the same unique run-specific report file. The file is retained for later use by the work agent, and a later debugging invocation creates a new report instead of overwriting it.

## Evidence discipline

A file read proves file contents, not runtime behavior. A syntax check proves syntax, not full correctness. A successful diagnostic command proves only what that command actually established. A previous pass summary is model-authored memory, not independent evidence. Preserve uncertainty when evidence is incomplete. Never convert an unverified repair idea into a confirmed defect merely because an earlier pass proposed it.
