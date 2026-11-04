# Agentic Stage 2 — host-observed execution claim check (Nov 4, 2026)

Status: experimental on PR #95, layered on plain-language memory PR #94. Not merged into main.

## Purpose

Help smaller models retain accurate execution status without requiring a new model pass, reconstructing raw tool transcripts, or making claims of unobserved effects.

When Stage 2 receives the latest user request, its native reasoning, and its exact final answer, it also receives a Jack-owned current-turn tool outcome note (where host evidence is available). The note clearly says it is tool execution metadata, *not* user instruction, reasoning, or a final answer. Stage 2 is asked narrowly to compare claims of completed tool use with this separate evidence, preserve material discrepancies, and avoid speculative reconciliation.

## Three record states

- **COMPLETE_CURRENT_TURN / NO_TOOL_CALLS_RECORDED**: Only when Jack froze its own completed Stage 1 and no tool calls/results were present. This is a negative observation *inside Jack*, not proof of what happened outside Jack.
- **COMPLETE_CURRENT_TURN / tool results present**: Host-observed returned results including structured failures; returned without error is *not* proof of completed filesystem or visual effects.
- **INCOMPLETE_OR_UNCONFIRMED**: The completion evidence is absent or a known tool call has no matching return. Do not treat missing outcomes as evidence that the tool was never used.

When the current turn has no host-owned records and no Jack-issued completion marker, no negative record is generated.

## Invariants

- Current turn only. No previous-turn tool evidence injected into Stage 2.
- Source U/R1/A1 projection is unchanged. Stage 1 exact x-high prompt and streaming are unchanged.
- No raw tool result bodies or arguments supplied to Stage 2.
- Maximum six selected host observations and a bounded result body; failures and mutations outrank routine reads.
- The note precedes the existing Stage 2 directive to preserve Stage 1 model-facing prefix where possible.
- Stage 2 stays tool-disabled. Preserve Thinking bridge, delayed retirement and host receipt archives are unchanged.
- No new tool calls, audits or post-action verification are initiated by the instruction.

## Validation

Automated cases cover real host-owned no-tool completion, synthetic/untrusted unconfirmed history, a call without a returned result, failed then returned tool results, both cache and fallback layouts, streamed and nonstreamed requests, and previously retired receipts. Windows CI must be green before any acceptance. Live model behavior must be evaluated independently of the deterministic runtime gates.
