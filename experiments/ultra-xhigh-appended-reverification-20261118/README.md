# Ultra — X-High Native Re-Verification (Experimental)

**Status:** experimental; mainline unchanged. **PR:** #165. Do not promote until Windows regression and physical cache evidence reviewed.

## Position and semantics

The interactive reasoning selector places **Ultra** immediately after **X-High (default)** and before **Agentic**. Ultra is **not** the retired three-stage Deep Research TAS; that older flow remains separately addressable under `deep-research` for compatibility.

Ultra executes the ordinary tool-capable **X-High** answer stage, using the caller's authenticated system contract, normal tools and native thinking. On completion of current-turn tool work, Jack holds the provisional answer back and performs **one second inference in the same native reasoning stage**. Its input is an append-only continuation of the first request: unchanged system text + original user and exact historical tool messages + first-pass native R1 (as assistant reasoning), followed by the **retired Exhaustive combined verification and user-request realignment instruction**. The speculative first-pass answer is not injected into the second model prompt; it is host-only draft state. Only the final inference's content reaches the caller. Both passes use `reasoning_effort=xhigh` and native thinking controls.

Exact combined instruction reused from retired Exhaustive/Agentic:
> Wait, re-verify the latest reasoning and chain-of-thought. Test for errors, mistakes, or poor quality. Make changes, if necessary, to ensure alignment with the instructions and user request before responding

This is *not* model-side token insertion into an already-running decoder. Ordinary OpenAI-compatible APIs do not supply a universal deterministic injection point inside one native reasoning generation. Jack **ends the first backend request**, appends a Jack-owned continuation preserving the original prefix, then **opens a second backend request**. This is the portable approximation, with its inevitable second-generation cost. Physical KV-cache residency and prefill penalty must be measured at LM Studio or the selected server; a stable JSON/chat prefix alone is not a cache-hit claim.

## Host invariants

- **No Agentic Stage 2:** no model memory distillation, U/M/A1 pipeline, XML memory, or Stage-2 pruning.
- **No cognition/tool-history pruning:** complete native R1 from the initial pass and tool continuations, review reasoning, original U and tool protocol are preserved. Source and history are copy-on-write where appropriate.
- **No duplicate effects:** tool proposals in either pass use authenticated stage checkpoint/Phase-4 validation, and tool continuations resume the precise stage. No completed external action is replayed just to re-verify.
- **No provisional answer leak:** first-pass draft is host-only and is not copied into the second backend prompt or streamed as public response.
- **Prompt and provenance safety:** existing host-origin tool-result provenance instruction remains intact and in the initial tool-capable system context; no system instruction is dropped to improve cache reuse.
- **Spoof resistance:** a caller-supplied private `_jack_internal_ultra_review_trigger` key is not sufficient to skip the first inference.
- **No change to other modes:** ordinary Off/Medium/X-High, Agentic Flash/Balanced/Thorough/Translated, and legacy three-stage Deep Research retain separate dispatch.

## Validation

- New isolated tests: `tests/test_ultra_native_appended_review.py`; exercise CLI/profile contract, exact prompt, R1/R2 retention, streaming SSE, no first-draft output, first/second prompt-prefix identity, two-stage count, and tool resume before/after the review.
- CI adds an explicit Ultra test step ahead of the known inherited full-suite failures.
- Default pytest collection is scoped to `tests` to avoid duplicate test module names in the preserved archived experiment folder.
- **Pending:** CI targeted results and Windows live LM Studio prefill/retention metrics. No post-change physical cache claims are validated.
- **Inherited baseline:** the preceding mainline full suite had 199 previously inherited test failures, not a clean pass. Do not reinterpret absence of new tests as release approval.

This experimental mode is the user's requested **unpruned, native X-High plus appended re-verification** design. Keep it outside `main` until validation and explicit permission to merge.
