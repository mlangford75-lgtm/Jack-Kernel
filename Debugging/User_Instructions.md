# Jack Code Debugging — User Instructions

Use **Code Debugging** or **Code Debugging (Deep)** when you want Jack to investigate a real codebase or file deeply and produce a repair-ready debugging report for the agent or developer who will make the changes. The two modes are identical except for reasoning effort: standard Code Debugging uses **Medium** reasoning and Code Debugging (Deep) uses **X-High** reasoning.

**Code Debugging is report-only. It does not patch your project.** Before the five audit passes begin, Jack opens a diagnostic conversation so you can describe what you have actually observed and guide the audit. The five fresh audit passes then inspect the same unchanged target. Each pass is deliberately limited to **one problem**, but every pass may search the **full professional code-review category set**. Categories are not tied to pass numbers.

## What to tell Jack

A useful request usually gives Jack:

1. **The exact file or project path** to inspect.
2. **What is going wrong** or what you expected instead.
3. Any reproduction details, errors, environment information, or constraints you already know.

You do not need to describe Jack's five-pass process. Select **Code Debugging** for Medium reasoning or **Code Debugging (Deep)** for X-High reasoning, then describe the problem normally.

### Example

> My application at `C:\Projects\MyApp\app.py` doesn't launch correctly. It loads, then crashes about five seconds later. Review the code and relevant project files, determine the cause, and produce a detailed repair report telling my work agent exactly what needs to be changed and how to verify the repair. Do not modify the project files.

For a single file:

> Audit `C:\Projects\MySite\index.html`. The page loads, but the controls stop responding after a few seconds. Find the cause and produce a repair-ready report for my coding agent. Do not edit the file.

A broad review request also works:

> Audit `C:\Projects\MyApp` for material defects. Produce a repair-ready report for my coding agent. Do not patch the codebase.

## Before Pass 1: diagnostic intake

Code Debugging first records your request in a tools-off pre-pass intake. **Your original message is enough. You are not required to answer diagnostic questions before the five audit passes can run.** The intake preserves whatever you already supplied, including the target path, requested/expected behavior, witnessed symptoms, reproduction details, logs, environment constraints, or things already tried.

The debugger may ask a focused optional question when your observation could materially improve the later audit. You can answer it, add different guidance, or simply say **proceed**, **go ahead**, **use what you have**, **just do your directive**, or equivalent. Jack must then continue instead of demanding more information.

If your initial request is already usable, the intake should normally complete without asking anything further. Jack freezes only your own supplied intake as Pass 0 and starts a completely fresh Pass 1. The intake model's reasoning, acknowledgements, and questions are temporary same-stage scaffolding and are not carried into the audit passes.

When your client requests streaming, the intake follows the same observability rule as the rest of Jack: **native reasoning and visible output stream live**. Intake reasoning is not silently buffered until completion.

## Every pass searches the same review categories

Passes are **not assigned different categories**. Every fresh pass may search all of these common professional code-review areas:

- **Functional correctness and runtime behavior**
- **Security, input validation, authorization, and trust boundaries**
- **State, lifecycle, concurrency, async behavior, and error handling**
- **Performance, resource management, scalability, and reliability**
- **Interfaces, data integrity, integration, configuration, maintainability, and testability**

Each pass surveys that whole space, selects the strongest credible **new** problem, and then locks onto that one problem for the rest of the pass. If that candidate is disproved, the pass records that outcome instead of switching to another problem. If there is no credible new problem, the pass can report no material finding rather than inventing one.

Multiple passes may find different problems in the same category. Some categories may have no finding. The category list is a search checklist, not a five-stage schedule.

## Cascading temperature is the control mechanism

All passes are fresh contexts at the selected debugging reasoning effort and search the same review space. Standard **Code Debugging** uses Medium; **Code Debugging (Deep)** uses X-High. Their temperatures are:

`1.00 -> 0.80 -> 0.70 -> 0.60 -> 0.50`

That cascade is intentional: early passes can search more broadly/diversely, while later passes become progressively more conservative and precise. The temperatures—not category assignment—differentiate the five audits.

## Severity

Every real finding should be classified as one of:

- **LOW** — limited/localized impact;
- **MEDIUM** — meaningful but generally contained/recoverable impact;
- **HIGH** — major primary-workflow, security, data-integrity, reliability, or availability impact;
- **CRITICAL** — severe high-consequence failure supported by strong evidence.

The debugger is instructed not to inflate severity. A hypothetical concern or code smell is not automatically a critical bug.

## The debugger may ask you questions

During a live pass, the debugger may pause and ask you for information that static inspection cannot establish, such as runtime symptoms, timing, reproduction steps, logs, environment details, or what you expected to happen.

The question must remain about the **one problem currently being audited**. Answer normally and as concretely as you can. Jack resumes the **same pass** after your reply; the clarification does not count as another pass.

Every debugger question also includes a reminder that the model remains bound by its primary `Debugging/Instructions.md` directive. Your answer can improve the diagnosis, but it cannot redirect the debugger away from its report-only, one-problem, five-pass contract.

## Handoffs are semantic, not brittle schemas

Jack asks each pass to produce a detailed repair-ready handoff with useful information such as category, finding, severity, status, evidence, location, root cause, repair direction, and verification steps.

Those labels are **not a host parser test**. Jack does not fail an otherwise useful pass because the model used a heading twice, changed field ordering, included extra explanatory text, or omitted a magic continuation line. A non-empty completed handoff is durably saved and the host-owned pass counter advances.

## What to expect

The passes remain fresh inference contexts at the selected debugging reasoning effort. Preserve Thinking may survive only inside the active pass for diagnostic tool continuation or user clarification. It does not cross pass boundaries.

Every debugging invocation creates a **new report file** under:

`Debugging/Reports/`

The filename is based on local date and time and includes a uniqueness suffix, for example:

`Debugging_Report_2026-09-09_14-41-02_123456_a1b2c3d4.md`

Jack saves the frozen **user-origin Pass 0 intake** and every later pass summary to that run-specific file. Assistant pre-stage chatter and pre-stage native reasoning are not written into durable Pass 0. The bundled core files `Instructions.md`, `User_Instructions.md`, and `Debugging_Report.md` are not overwritten. A later debugging run creates a new report, so Code Debugging can be used repeatedly without destroying earlier reports.

Every fresh pass receives the complete user-origin Pass 0 intake again, so your exact requirements do not have to survive a chain of model summaries. Pass 1 receives only that user-origin intake. Passes 2–5 receive only a compact host-derived confirmed prior-finding registry from already committed outcomes so they can avoid duplicate work. Full prior handoffs, repair instructions, residual observations, future-candidate suggestions, native reasoning, and earlier tool traffic stay out of later live pass context while the complete original handoffs remain in the run report for the final reporter.

After Pass 5, Jack starts one final fresh tools-off reporting stage at temperature **1.00** using the same selected debugging reasoning effort. It reads **all saved Pass 0–5 summaries from that run's unique report file** and produces the final consolidated report, which is appended to the same file.


## Why the passes do not inherit previous search suggestions

The temperature cascade is meant to create five genuinely fresh searches over the same professional review space. A previous pass may incidentally notice another possible defect while auditing its one locked problem, but that speculation should not tell the next pass what to investigate. Jack therefore separates **durable report history** from **live search guidance**: useful residual notes can remain on disk for the final report while the next fresh pass receives only exact user authority plus a compact host-derived registry of already established prior outcomes.

## What the final report contains

The final report is intended for your **work/coding agent**. It should provide:

- up to five deeply audited primary findings;
- the review category associated with each finding when established;
- LOW / MEDIUM / HIGH / CRITICAL severity for each real finding;
- confirmed, suspected/unresolved, rejected, or no-finding outcomes as supported;
- exact affected files, symbols, and locations where known;
- observed versus expected behavior;
- root cause and supporting evidence;
- concrete repair instructions;
- behavior and constraints the patch must preserve;
- exact post-patch verification steps;
- useful negative coverage where a pass established no new material problem.

Because every pass searches the same full category set, categories may repeat in the final report. That is expected. The final report reflects the strongest problems found by five fresh audits under the cascading temperature schedule, not a forced one-category-per-pass quota.
