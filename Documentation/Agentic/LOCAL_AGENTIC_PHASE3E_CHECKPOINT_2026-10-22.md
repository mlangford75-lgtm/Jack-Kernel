# Local Agentic (Preserve Thinking) — Phase 3E operational checkpoint

**Date:** October 22, 2026  
**Scope:** The current locally tested Agentic (Preserve Thinking) implementation using Qwen3.8-27B-GSQ-RCO IQ3_S through LM Studio and Pi.  
**Canonical selector:** `JACK_REASONING_LEVEL="Local Agentic (Preserve Thinking)"`; legacy `agentic` accepted as alias.  
**Runtime display:** Local Agentic (Preserve Thinking).

## Current implementation

- Stage 1: native reasoning with authorized tools, frozen exact answer A1.
- Stage 2: zero-tool-authority retrospective M, with native Preserve Thinking available from the current Stage-1 trajectory.
- Completed history: authenticated U/M/A projection; completed tool protocol and obsolete reasoning retired. Immediately prior R2 bridges into next Stage 1 once and is retired when A1 freezes.
- Phase 3E cache-compatible Stage-2 request is **on by default when using LM Studio Agentic**. It keeps the Stage-1 system instruction and tool schemas in the Stage-2 backend request, appending the unchanged retrospective directive in a user continuation. Stage-2 tool execution is still denied by Jack.
- **Rollback:** `JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT=0` (restart Jack).
- Other backend profiles, and forced/named tool-choice Stage-2 calls, retain their pre-3E request representation. No claim of a cloud-optimized implementation is made.
- Optional Phase 3F byte accounting remains disabled by default; enable with `JACK_AGENTIC_CONTEXT_ACCOUNTING=1`.

## Observed three-turn local test

An interactive three-turn clock/SVG workflow exercised Stage-1 tool continuation, Stage-2 retrospective memory, and cross-turn recall, with Phase 3E enabled.

| Stage-2 retrospective | Freshly evaluated prompt tokens | Prefill time | Generation time |
|---|---:|---:|---:|
| Turn 1: SVG creation | 475 | 0.54 s | 61.71 s |
| Turn 2: clock verification | 14,543 | 8.75 s | 72.43 s |
| Turn 3: session summary | 7,212 | 4.31 s | 39.81 s |
| **Total** | **22,230** | **13.60 s** | **173.95 s** |

LM Studio reported approximate prefix similarities of **97.1%, 18.0%, and 59.5%** at these three Stage-2 transitions. This is evidence of cache reuse on the first turn and reduced reuse on later turns, not a controlled speedup calculation.

Stage 1 created and corrected the SVG; retrospective memories completed; subsequent turns recalled the work and tool-verification limitations. No unauthorized Stage-2 tool execution or functional regression was observed *in this workload*. The experiment does not establish general equivalence, universal performance improvement, or a security validation milestone.

## Known technical tradeoffs

- Retiring consumed one-hop R2 at the Stage-1 freeze can change historical prompt content before Stage 2, reducing reusable-prefix length.
- Preserving R2 through Stage 2 is an **untested idea**, not the current implementation. No R2-retirement change was made.
- Cache residency/eviction and the full Stage-1 tool trajectory also influence fresh prefill. Prefix similarity is not itself a cost or latency guarantee.
- Stage-2 generation time was much larger than measured prefill time in this workload.
- No identical-workload Phase 3E enabled/disabled A/B result is recorded. No measured improvement against a native Pi control is claimed.

## Source of truth

- Runtime: `jack_kernel.py`, `REASONING_PROFILES["Local Agentic (Preserve Thinking)"]["label"]`, `AGENTIC_CACHE_APPEND_EXPERIMENT`, `_agentic_cache_append_enabled`, and `_agentic_retire_consumed_one_hop`.
- Regressions: `tests/test_agentic_cache_append_experiment_phase3e.py`, `tests/test_agentic_one_hop_bridge_phase3d.py`, and `tests/test_runtime_identity.py`.
- Phase 3E default-on merge: [PR #60](https://github.com/mlangford75-lgtm/Jack-Kernel/pull/60).

This checkpoint records local operating reality; historical release records remain archival and are not rewritten.
