# Jack Agentic: reasoning-primary memory experiment

**Date:** November 12, 2026  
**Status:** Experimental implementation. Not validated by a live local-model trial.  
**Branch:** `experiment/agentic-reasoning-primary-memory-20261112`  
**Main:** Unchanged.

## Experiment definition

The original request, exact frozen answer, and all authenticated tool observations are the responsibility of Jack's deterministic host and canonical history. The retrospective model's only specialized cognitive job is to **distill consequential working knowledge from the preceding native reasoning before that reasoning is retired from active context**. It does not reconstruct the request or duplicate the completed answer.

**This experimental branch applies that role to every Agentic profile: Flash, Balanced, Thorough, and Exhaustive.** There is **no new toggle, opt-in switch, profile-selection submenu, or fallback to the previous interaction summarizer**. Checking out the experimental branch selects the experiment. Main remains untouched.

## Model-facing directive (verbatim)

> Preserve the useful working knowledge from the preceding reasoning before that reasoning is removed from active context.
>
> Retain consequential discoveries, established decisions and their explanations, exact technical details, constraints, failure causes and successful corrections when known, reusable methods, significant caveats, and unresolved matters. Preserve important names, numbers, paths, identifiers, and qualifications exactly.
>
> Distinguish hypotheses and abandoned approaches from conclusions; distinguish attempted or reported actions from verified results. Do not invent missing evidence, new reasoning, or outcomes. Keep important details even if they require substantial space.
>
> This is an internal working-memory task, not a request to repeat the original work. Do not continue the original task, reproduce an answer, imitate presentation or conversational style, or add formatting rituals. Remove redundant deliberation and filler.
>
> Output only the resulting working knowledge. If no reasoning was supplied, state only that no reasoning was available to distill.

No proprietary host stage names, Jack terminology, mandatory JSON, or human-facing task recap is included in these model-facing instructions.

## Host implementation

1. Validate authentic current-turn request ownership and the existence of a frozen final answer in **canonical history** before creating the model's view.
2. Collect all available native reasoning fragments produced during that current turn, including reasoning across tool continuations.
3. Provide only those reasoning fragments (as native reasoning when available) plus neutral completion text to the retrospective model. **Never include the full original user request, complete frozen answer, or verbose tool-evidence note in that model-facing view.**
4. Retain original request, frozen answer, exact observed tools/results, transaction ID and status in Jack's canonical state and historical projection. The model does not have tool authority in the retrospective.
5. When native reasoning is absent (notably in Flash), pass a clear notice that there is no reasoning to distill. Do not invent reasoning and do not silently switch to summarizing the answer.
6. Keep the existing deterministic turn association, A1 freezing/commit and history-retirement boundaries. Do not introduce similarity or JSON-validity commit gates.

The current forensic SQLite journal stores source **fingerprints and transaction status**, not all original source bytes as independently retrievable files. The separate Agentic History Upgrade is needed for independently recoverable exact archival text.

## Profiles and scope

| Agentic profile | Native reasoning during initial work | Retrospective role |
| --- | --- | --- |
| Flash | Off | Same reasoning-distillation role; explicit absence if no source reasoning |
| Balanced | On | Same reasoning-distillation role; no new native retrospective reasoning |
| Thorough | On | Same reasoning-distillation role; retrospective may generate native reasoning |
| Exhaustive | On | Same reasoning-distillation role; existing extended review configuration preserved |

Profile controls for reasoning effort are unchanged. No profile switches to an old response summarizer.

## Acceptance criteria

Assess fidelity to established knowledge, correct tentative-versus-final distinctions, retained failure lessons, complete exact host evidence, next-turn recall, format contamination and copy/re-answer behavior. Test both streaming and nonstreaming backend payloads, all four profiles, missing reasoning, tool-rejection recovery, partial failure, fixed A1 hashes, original request retention, and cache/prefill costs. The absence of duplicate prose is not sufficient if useful working knowledge is lost.

The new tests in `tests/test_agentic_reasoning_primary_memory_experiment.py` cover model-facing projection and mock request structure. Some historical tests encode the previous U/R/A retrospective contract; they must be reconciled with this intentional branch experiment before claiming a passing full regression suite.

## Evidence and limits

The November 12 Night Market tests show that the old retrospective sometimes copied its completed answer and that a compulsory JSON task field was not an adequate fix. The new source-isolation architecture is a hypothesis requiring live-model validation, not a demonstrated performance improvement. No code has been changed on main.

**Companion paper:** *Jack Agentic — Reasoning-Primary Memory Preservation, Revised Experimental Specification* (Jonathan Michael Langford, November 12, 2026), issued as PDF and Markdown.
