# Jack Kernel Loop Detector — implementation and live acceptance test

This feature governs **native reasoning streams only**. It is a deterministic
repetition policy, not a mathematical proof that a model can never finish.

## Launcher

Run `start.bat` from the repository root. The branded startup screen displays
**Loop Detector: ON / 32 repetitions** by default.

Choose **L — Loop Detector** on the main screen:

- On / Off (On by default).
- Consecutive exact repetitions: **16, 32 (default), 48, 64, 128**.
- Minimum exact repeated cycle: **128 completed whitespace-delimited words**.

The setting is stored in Jack's normal launcher config and passed to the
server as `JACK_LOOP_DETECTOR` and `JACK_LOOP_REPETITIONS`. Direct server
launches also accept those environment variables. Detection is performed
on the new `reasoning_content` or `reasoning` field from the backend only.
The original user message, conversation history, tool results, visible output,
and the one-hop Stage-2 Preserve Thinking bridge are not scanned.

Exact repetition is tested after ignoring whitespace differences; case,
punctuation, and all other word characters must match. Hashes select candidates
for a full exact-equality check, never authorize termination alone. The
monitor retains at most a bounded history and checks cycles up to 2,048 words.
Detection can be delayed by up to 15 completed words to reduce CPU overhead.

## Inference outcomes

- **No detection:** Normal live streaming, tools, stage completion, cache,
  forensics, and native agent cancellation remain unchanged.
- **First detection:** Stop that backend inference and retry **only the same
  inference** once. The aborted inference cannot freeze A1 or Agentic Memory.
  Previous tool results are evidence; Jack does not call agent tools again.
- **Second detection:** Stop and report
  `Jack Kernel interrupt - Repeated Loop Failure`; do not automatically
  start a third inference. Never manufacture a completed A1 or Stage-2 memory.
- **User abort:** Pi owns the action and the conversation. Jack closes its
  inference and discards incomplete internal continuation state; it does
  **not** auto-retry or reinsert the user request.
- **Token budgets:** No proposed 100K reasoning or output ceilings are
  imposed by Jack. Backend-native context/generation limits still apply.

This is deliberately narrow. An exact matcher cannot catch all nonterminating
behaviors or semantic loops with changing language. Nor can any finite
text-pattern detector guarantee zero false positives in intentionally
repetitive reasoning. This remains a selectable policy.

## Validation

Automated:
```powershell
python -m pytest -q tests/test_loop_detector.py tests/test_loop_kernel_integration.py
python -m pytest -q
```

Live in **Pi + LM Studio** after cloning this feature branch:

1. Start Jack with Loop Detector ON / 32, and verify the status line.
2. Run a normal two-stage Agentic request and confirm frozen A1, Stage-2
   distilled memory, and normal later-turn R2 bridge.
3. Run a multi-tool request and **press Escape during its active model
   generation**, then ask an unrelated new question immediately in the
   same Pi session. Confirm no `ForensicConflict`, no stale tool replay,
   no fabricated memory, and prompt model cancellation.
4. Force a synthetic repeated reasoning stream in an isolated test backend.
   Confirm one retry and one terminal failure, with no repeated tool execution.
5. Repeat with Loop Detector OFF. Confirm no loop-based interruption and
   normal agent cancellation.
6. Compare cache TTFT and stage-token accounting against accepted `main`.

**Do not merge** until Windows CI and these live interruption tests pass.
