# Deep Reasoning — TAS v6 integration gate

> **Public mode name:** **Deep Reasoning**. **Public stages:** Thesis → Antithesis → Synthesis. This document is a historical TAS v6 integration gate; its implementation details and statuses are retained for traceability.

**Status: NOT MERGE-READY.** This branch stages the approved design and public-mode naming decision, not an implementation of TAS v6. Do not rename the existing `ultra` Deep Research mode to imply TAS v6 is active.

## Naming
- New public mode: **Deep Reasoning**.
- Proposed selector: `deep-reasoning` (alias `deep_reasoning`).
- Retain existing `deep-research` selector and label for its existing behavior until compatibility and migration are explicitly tested.
- Avoid modifying Agentic, Code Debugging, and native reasoning mode behavior.

## Verified experimental behavior
The standalone LM Studio TAS v6 runner, tested with `gemma-4-12b-it`, achieved A=450, B=17, C=25/77 on the 18-position bracelet task. Initial Antithesis request used `tool_choice="required"`, returned a structured Python tool call after 2,098 completion tokens, encountered a missing NumPy dependency, retried using the standard library, and returned grounded evidence. This is one successful mathematical trial, not production-Kernel integration or general validation.

## Immutable prompt pins
- Thesis SHA-256: `46987d871465c957727105309ec8c7856ea1abc0dc6db9849428c944d35f6752`
- Antithesis SHA-256: `b90f5b048ceeacdf5924e30d9648455c55d4733c1afe44a788f79fae9e12939e`
- Synthesis SHA-256: `8e16b81b1f70b1582f2bcb8766181db8e1b3965835248a7e053094ac662aea8a`

The complete exact prompt content is in the previously delivered `Deep_Reasoning_Exact_Prompts.json` and context-isolation handoff. Do not alter prompts during the first integration A/B test.

## Tested generation setup
| Stage | Temperature | Reasoning effort | Tools | Tool choice |
| --- | --- | --- | --- | --- |
| Thesis | 1.0 | xhigh | enabled | auto |
| Antithesis | 0.5 | medium | enabled | **required on first request**; auto thereafter |
| Synthesis | 0.5 | xhigh | enabled | auto |

No model-facing `max_tokens` in the standalone experiment. Tool execution requires real host authorization, actual response receipts and security controls, not merely prompt claims. Do not blindly execute model-generated Python without an approved sandbox.

## Reasoning isolation proposal
- Each stage may generate its own native reasoning.
- Antithesis receives original request + visible Thesis A1, never Thesis R1 or prior Synthesis R3.
- Synthesis receives original request + visible A1 + Antithesis findings A2 + independently attributable tool receipts, never R1 or R2.
- Within-stage tool continuation retains valid assistant tool_calls / matching tool responses without replaying previous native reasoning, subject to backend compatibility tests.
- **Experimental cross-turn switch:** immediately previous Synthesis R3 and authoritative A3 may be visible only to the next Thesis when Preserve Thinking is ON. OFF retains A3 but not R3. Neither the benefit nor backend roundtrip of this bridge has been established; default to OFF until tested.
- Forensic records may preserve complete traces but are never model-facing unless a specific projection permits them.

## Required implementation work before merge
1. Create a separate Deep Reasoning mode profile and public label. Keep existing Deep Research running unchanged until deliberate replacement/migration.
2. Stage-specific message projections must drop *all* alternate native reasoning aliases; preserve ordinary necessary user constraints and authenticated tool evidence.
3. Enable Antithesis tool authorization and tool checkpoint/resume through existing Kernel validators for both streaming and nonstreaming. Force only a relevant first verification action when appropriate; fail closed if backend cannot honor required tool choice. Avoid a meaningless forced tool call.
4. Deliver structured success/error receipts, source, stdout/stderr, and provenance to Synthesis; do not treat exit 0 as proof of correctness.
5. Keep Synthesis final answer authoritative; save its R3 in a separate one-turn store rather than returning a composite R1/R2/R3 history as reusable reasoning.
6. Explicitly bound/expire pending resumes and evidence; preserve existing safety properties.
7. Cover first action, Python error recovery, mixed tool policies, broken tool call IDs, nonstream/stream, disconnect/resume, R3 ON/OFF cross-turn and negative contamination tests.
8. Prove regression compatibility for existing modes and check documentation, README, runtime spec, UI selectors, CLI/env labels and migration aliases.
9. Validate with local LM Studio model plus independent tasks, then review CI.

## Merge rule
**Do not merge merely because this design document exists or because the standalone benchmark succeeded.** Merge only after an implementation PR includes tested runtime changes and passing CI, with explicit observation of the stage-isolated request/response envelopes.
