# Jack Kernel Security Layer Checkpoint — Phases 0–3 Validated

**Date:** 2026-09-27
**Branch:** `jack-kernel-security-hardening`
**Validated code head:** `9dda35a358baf2814102dcb9c45346116271acfc`
**Parent Phase 3 freeze:** `0943df9f6a03114fdb2cfb33c7b263df638dfae4`
**Checkpoint tag:** `security-layer-phase0-3-validated-2026-09-27`

## Security doctrine

Fail closed on authority. Fail soft on recoverable cognition.
Contain violations at the narrowest boundary that preserves the security invariant.
Security must not make Jack brittle.

## Phase 0 — Reality mapping
Mapped the real Kernel release, authority, runtime identity, configuration, tool, resume, evidence, ownership, and concurrency boundaries without production changes.

## Phase 1 — Security outcomes
Defined ALLOW, DENY_AND_CONTINUE, REQUIRE_USER_DECISION, and HARD_INTERRUPT. Only HARD_INTERRUPT carries hard-security classification.

## Phase 2 — StreamingIRQ
Added bounded pre-release quarantine with safe-prefix preservation, ordinary-failure recovery, hard-interrupt withholding, bounded state, split invariance, field isolation, choice isolation, and concurrent-stream isolation.

## Retroactive Phase 2 correction
Adversarial validation discovered that malformed non-DONE SSE data frames could bypass inspection by being released raw when parsing returned no object.
The validated correction introduces StreamingIRQProtocolError, withholds the malformed current frame, preserves previously safe quarantined cognition, and does not promote protocol failure into hard-security authority.

## Phase 3 — Canary enforcement
Added deterministic exact-match Canary detection, immutable runtime/lane-bound policy, streaming text protection, non-stream protection, streamed function.arguments protection, and static Tier A/B startup policy through JACK_CANARY_POLICY_JSON.
Tier C live mutation remains deferred to controlled dynamic-state authority.

## Validation
- Retro Phase 0-2 adversarial suite: 17 passed
- Dedicated Phase 1 suite: 4 passed
- Existing Phase 2 suite: 40 passed
- Canary regression: 51 passed
- Responses regression: 7 passed
- Full Python regression: 175 passed
- Six Pi harnesses: PASS

## Accepted correction hashes
`jack_evidence_guard.py` — `B8E6DDA253977E2D636BC764FFADC6A573EEDD274602383801A5174A3F335194`
`tests/test_retro_phase0_2_validation.py` — `6603D1A4D2626985BA9338ACC0C1ED906A7E2D2427FB261764A6A95E8D964BFF`

## Scope boundary
This checkpoint does not claim Restricted Paths, Workspace Lock, Consequence Gate, credential DLP, hostile in-process tamper resistance, dynamic Tier C mutation, remote attestation, or global cross-process security-state serialization.

## Next layer
Phase 4 — Restricted Paths + Workspace Lock.
