# Agentic Stage 2 — Turn-Local Retention A/B/C (experimental)

**Status:** Live-tested and approved for merger as an opt-in turn-local feature, with the existing full-history Stage 2 default retained for regression compatibility. `baseline` remains the backward-compatible default; `isolate` and `isolate-retain` remain available for explicit selection. The new evidence-qualification rule also applies to the default linked continuation.

## Hypothesis

Giving Stage 2 only the **current turn's exact user request U, complete native Stage-1 reasoning R1, current-turn tool-call/result chronology T, and exact frozen A1** will improve its causal memory M and one-hop native R2 for downstream Agentic tasks. It may increase Stage-2 prefill because removing historical context changes the cached prompt prefix.

This is a **backend request projection only**: no mutation of the canonical host history, stage transitions, frozen A1, tool authorization, journal, receipts, one-hop R2 eligibility, streaming, or failure/cancellation lifecycle.

Stage 1 still receives its established full-context history and the preceding authenticated R2. Stage 2 does not separately receive older U/M/A, old tool protocol, or inherited R2 (although information from that history can naturally be reflected in Stage-1 reasoning).

## Variants

Set `JACK_AGENTIC_STAGE2_RETENTION_TEST` before `start.bat` to select an opt-in isolation variant:

| Value | Stage-2 backend messages | Stage-2 continuation |
| --- | --- | --- |
| `baseline` (default) | Accepted full active history | Accepted linked continuation |
| `isolate` | Current U, all current-turn Stage-1 assistant/native reasoning, tool calls/results, and frozen A1 | Accepted linked continuation |
| `isolate-retain` | Same turn-local view as `isolate` | New future-work preservation directive |

`isolate` tests context isolation with the same wording. `isolate-retain` tests the combined context + instruction change. The core `AGENTIC_STAGE1_PROMPT` and `AGENTIC_36_STAGE2_PROMPT` remain byte-exact. With the normal launcher, transaction links are enabled.

**Crucial:** The isolated view is still an ordered chat protocol, not concatenated reasoning text. Multi-tool requests keep actual call IDs, tool messages, failed results, and subsequent Stage-1 reasoning. It intentionally includes no fabricated snapshots. Model memory and host-recorded receipts remain separate.

## Windows test procedure

For replay testing, use a fresh clone of the branch while the PR remains open (after merge, clone `main` instead):

```powershell
Set-Location "$env:USERPROFILE\Desktop"
git clone --branch experiment/agentic-stage2-turn-local-retention-20261103 --single-branch https://github.com/mlangford75-lgtm/Jack-Kernel.git Jack-Stage2-Test
Set-Location ".\Jack-Stage2-Test"
py -3 -m pip install -r requirements.txt
py -3 -m pip install -r requirements-test.txt
py -3 -m pytest -q tests/test_agentic_stage2_turn_local_retention.py tests/test_agentic_transaction_linked_memory.py tests/test_agentic_stage_scoped_system_authority.py
py -3 -m pytest -q
```

For independent runs, close Jack, then set the variant and launch from the repository root:

```powershell
$env:JACK_AGENTIC_STAGE2_RETENTION_TEST="baseline"
$env:JACK_AGENTIC_CONTEXT_ACCOUNTING="1"
.\start.bat
```

Repeat with `"isolate"` and `"isolate-retain"`. Do not run competing Jack instances on the same listener port. The environment switch must be set **before launch**, and changing it requires a restart. Unset the variable or use `"baseline"` to restore the accepted full-history default afterward.

Keep the same backend model, parameters, context window, system prompt, tool schemas and workspace state for all runs. Use separate Pi sessions (or restored copies) so prior experimental memories do not contaminate another variant. Use comparable task prompts; preferably replay the same captured Stage-1 execution when exercising the three Stage-2 payloads in a controlled harness.

## What to measure

1. **Stage 2 prefill:** backend actually evaluated prompt tokens, prompt evaluation milliseconds, TTFT, and cold/warm state. Do not confuse transmitted context size with tokens evaluated.
2. **Stage 2 output:** R2 generation tokens, latency, M length, and missing/incorrect/invented tool-evidence claims.
3. **Downstream recall:** whether the next Stage 1 correctly reuses decisions, fixes and unresolved limitations, and whether it wrongly inherits retrospective-only restrictions.
4. **System guarantees:** Stage 1 unchanged, native reasoning streamed, tool calls not reissued, A1 byte-exact, journal U/A1/M linkage intact, one-hop R2 carried then retired, and no new failures after abort or tool resume.

Use one short request, a multi-tool request with a failed tool and a corrected retry, and a long-reasoning request. An 80K thought trace requires a separate hardware/backend-capacity check; do not extrapolate short-context prefill measurements to 80K.

## Decision criteria

- Reject isolation if downstream recall loses consequential evidence or the current-turn tool chronology.
- Reject it if the memory is shorter but measurably less useful, or if future Stage 1 imitates Stage-2 restrictions.
- Favor the experiment only if independently repeated downstream benefits compensate for any added Stage-2 prefill and latency.
- A passing unit test establishes **request shape and host invariants**, not model-level improvement. No measured gain is claimed until a real LM Studio/Pi test is performed.

**Live observations (Nov 3, 2026):** A seven-turn analog-clock implementation showed Stage-1 tool continuity, source editing, one loop interruption and successful recovery, and a Stage-2 retrospective with current-turn scope. Backend logs showed streaming, substantial same-stage prefix cache reuse, and multi-second Stage-2 prefill on context isolation. Retrospective memory sometimes promoted a successful file edit into an unverified claim of correct visual output. To address this narrowly, both the established default linked continuation and the opt-in future-work retention directive add explicit evidence discipline: successful writes/edits establish only tool-reported actions, not runtime or visual correctness; checks and unresolved issues must be distinguished and consequential recovery history preserved. This live test supports the authorized merge, but is **not** a controlled A/B proof of faster performance or improved downstream answer correctness.

**Rollback:** `$env:JACK_AGENTIC_STAGE2_RETENTION_TEST="baseline"` followed by a server restart restores full-history Stage 2. The established default keeps the new short evidence-discipline sentence, and the original accepted core stage prompts remain unchanged. The immutable Stage-1 and Stage-2 core prompts, host lifecycle, streaming, and one-hop R2 bridge remain unchanged.
