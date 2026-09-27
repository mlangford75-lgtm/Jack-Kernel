# Jack Kernel Governing-Document Security Amendment — Phases 0–3

**Date:** 2026-09-27  
**Status:** Current governing amendment  
**Applies to:** Jack Kernel v0.1.1 documentation set  
**Validated code head:** `9dda35a358baf2814102dcb9c45346116271acfc`  
**Checkpoint documentation head:** `bdb05a5b364759f5e79ced524bc2a47934a80fee`  
**Checkpoint tag:** `security-layer-phase0-3-validated-2026-09-27`

## 1. Documentation preservation rule

Jack Kernel documentation is cumulative.

Existing substantive architecture, rationale, limitations, historical evidence, validation records, examples, and prior claims are not deleted merely because implementation reality advances. New implementation reality is expressed through additive amendment, clarification, qualification, or later consolidated editions.

When older wording is historically accurate but no longer the complete current description, preserve that wording and state what changed.

This amendment therefore **does not erase or supersede unaffected information** in the existing v0.1.1 governing documents. It updates the security-status interpretation that must be read together with them.

## 2. Documents amended by this record

This amendment applies to the current repository copies of:

- `00_Jack_Kernel_Plain_English_Master_Guide_v0.1.1.docx`
- `Documentation/Jack_Kernel_Runtime_Specification_v0.1.1.docx`
- `Documentation/Overview/Jack_Kernel_Preview_Programmable_Cognition_Runtime_v0.1.1.docx`
- `Documentation/Research/Jack_Kernel_Long_Horizon_Cognition_Technical_Whitepaper_v0.1.1.docx`
- `README.md`
- `GETTING_STARTED.md`
- Orchestration Gateway v2 technical and operator documentation

The four DOCX bodies are intentionally preserved rather than rewritten during this checkpoint. This avoids accidental information or formatting loss. Their existing content remains governing for the subjects it covers; the security-status changes below are additive current reality.

## 3. Governing security doctrine now in force

The security hardening work formalizes these rules:

> **Probabilistic cognition may propose, but deterministic software must dispose.**

> **Fail closed on authority. Fail soft on recoverable cognition.**

> **Contain the violation at the narrowest boundary that preserves the security invariant.**

> **Security must not make Jack brittle.**

The containment preference is:

1. reject only the proposed consequence;
2. withhold only the affected output span or tool call;
3. invalidate only the affected run/security scope;
4. sever only the affected connection;
5. terminate or make the runtime inert only when Kernel authority itself cannot remain trusted.

## 4. Phase 0 — reality and authority mapping

Phase 0 made no production changes. It mapped the actual release, tool, resume, evidence, runtime-identity, configuration, ownership, and concurrency seams on which later security enforcement depends.

Retroactive validation proves that Chat Completions and Responses cognition still crosses the wrapped `KERNEL.run` / `KERNEL.stream` release boundaries and that evidence/security wrapping precedes Responses compatibility registration.

## 5. Phase 1 — deterministic security outcomes

Jack now defines:

- `ALLOW`
- `DENY_AND_CONTINUE`
- `REQUIRE_USER_DECISION`
- `HARD_INTERRUPT`

Only `HARD_INTERRUPT` is hard-security classification. The outcome representation itself does not independently cancel work, destroy cognition, clear state, sever connections, or terminate the runtime. The owning deterministic mechanism disposes of the consequence.

## 6. Phase 2 — StreamingIRQ pre-release quarantine

StreamingIRQ now supplies bounded unreleased-tail quarantine at the model-to-caller release boundary.

Validated behavior includes:

- bounded retained state;
- chunk/split-point invariance;
- independent choice state;
- independent content/reasoning state;
- concurrent-stream isolation;
- safe-prefix preservation;
- benign held-tail recovery on ordinary failure;
- unreleased-tail withholding on a hard security interrupt.

### 6.1 Malformed SSE correction

Retroactive adversarial testing exposed one real Phase 2 defect: an unparseable non-DONE SSE `data:` frame could be passed through raw.

The validated correction introduces `StreamingIRQProtocolError`.

Current semantics:

```text
valid model SSE data
    -> normal guarded inspection

SSE comment / keepalive
    -> transparent passthrough

malformed non-DONE SSE data
    -> current malformed frame withheld
    -> generic protocol error
    -> previously proven-safe held cognition preserved
    -> no hard-security authority acquired
```

`StreamingIRQProtocolError` is deliberately not a `StreamingIRQHardInterrupt`.

## 7. Phase 3 — deterministic Canary enforcement

The current runtime implements deterministic exact-literal Canary enforcement with:

- immutable Canary definitions and match metadata;
- bounded streaming detection;
- runtime/lane-bound immutable policy ownership;
- streamed text-field enforcement;
- non-stream content/reasoning/tool-call enforcement;
- streamed `function.arguments` enforcement;
- safe-prefix preservation;
- hard release withholding for Canary matches.

Static startup policy is transported through `JACK_CANARY_POLICY_JSON`. The environment is startup transport only; authority resides in the immutable runtime policy after construction.

Static startup policy currently permits Tier A and Tier B. Tier C matching semantics exist, while controlled live Tier C mutation remains deferred.

## 8. Validation state

At the validated code checkpoint:

- Retro Phase 0–2 adversarial suite: **17 passed**
- Dedicated Phase 1 suite: **4 passed**
- Existing Phase 2 suite: **40 passed**
- Canary regression: **51 passed**
- Responses regression: **7 passed**
- Full Python regression: **175 passed**
- Six Pi harnesses: **PASS**

The accepted correction file identities are recorded in `docs/security/SECURITY_LAYER_PHASE0_3_VALIDATED_2026-09-27.md`.

## 9. How this amends each governing document

### Plain-English Master Guide

Earlier language describing independent safety/policy layers as programmable capability remains valid. The current reality is now stronger: Jack ships a validated **specific** Phase 0–3 security substrate. The broader architecture remains extensible and does not become a universal sandbox merely because these protections now exist.

### Runtime Specification

The existing independent safety/policy boundary remains valid. Its earlier statement that v0.1.1 does not define a universal deployment safety-policy set must now be read together with this amendment: the runtime still does not define a universal policy set, but it now implements the specific deterministic Phase 0–3 mechanisms described here.

The existing non-normative capability-confinement/workspace example remains non-normative at this checkpoint. Restricted Paths and Workspace Lock are Phase 4 work.

### Programmable Cognition Runtime Preview

The product-level description must now include deterministic security release enforcement as one implemented example of the host-authoritative Kernel boundary, while preserving the wider programmable-cognition framing and the distinction between Kernel, agent, and model.

### Long-Horizon Cognition Technical Whitepaper

The research argument that host-side safety/policy authority can remain independent of probabilistic cognition is now partially instantiated in validated runtime mechanisms. This implementation evidence strengthens that architecture claim without changing the paper's distinction between host conformance and semantic-quality claims.

### Orchestration Gateway v2

Security release decisions do not collapse orchestration lifecycle semantics. Security outcome, runtime observability, task/run identity, cancellation, and settlement remain separate deterministic domains. Supervisors must not bypass Jack or invent lifecycle consequences from a security release event.

## 10. What remains explicitly unclaimed

The Phase 0–3 checkpoint does not claim:

- universal filesystem sandboxing;
- Restricted Paths enforcement;
- Workspace Lock;
- deterministic Consequence Gate;
- complete credential isolation/DLP;
- Source Drift Guard;
- Runtime Code Integrity;
- Authority Policy Integrity;
- controlled live Tier C mutation;
- remote attestation;
- global cross-process security-state serialization.

## 11. Next layer

The next authorized security layer is:

**Phase 4 — Restricted Paths + Workspace Lock**

Phase 4 must build on the validated Phase 0–3 baseline without weakening its authority/resilience invariants.

## 12. Historical preservation

The checkpoint tag `security-layer-phase0-3-validated-2026-09-27` remains an immutable historical identity. Later documentation or implementation must not move or rewrite that tag. New validated reality receives new commits/checkpoints while this record remains available as evidence of what was true at this stage.
