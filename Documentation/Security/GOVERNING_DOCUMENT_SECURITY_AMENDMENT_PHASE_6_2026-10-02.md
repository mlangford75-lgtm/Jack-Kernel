# Jack Kernel Governing-Document Security Amendment — Phase 6

**Date:** 2026-10-02  
**Status:** Documentation/checkpoint closure candidate pending separate merge and tag authorization  
**Applies to:** Jack Kernel v0.1.1 documentation set  
**Accepted implementation head:** `6bb326bde22cd96ee8ba13227005b88e9d2184f0`  
**Implementation merge commit:** `04d7c0843ca6830afaeff4b1bd65e90c87770595`  
**Implementation merge tree:** `82485fc24b9960a3ea2125ef7e0898b470b52e84`  
**Predecessor:** `GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_5_2026-10-01.md`  
**Intended final checkpoint tag:** `security-layer-phase6-validated-2026-10-02` — not yet created

## 1. Documentation preservation rule

Jack Kernel documentation remains cumulative.

This amendment does not delete or silently rewrite earlier governing architecture, rationale, limitations, examples, or validation evidence. The Phase 0–3, Phase-4, and Phase-5 records remain historical evidence of their validated checkpoints.

Phase 6 advances the current security interpretation by adding the runtime-scoped Authority & Security Ledger on top of the already-established represented-path and Consequence Gate authority model.

## 2. Governing documents covered

This amendment applies to the same governing documentation set as the Phase-5 amendment, including:

- `00_Jack_Kernel_Plain_English_Master_Guide_v0.1.1.docx`
- `Documentation/Jack_Kernel_Runtime_Specification_v0.1.1.docx`
- `Documentation/Overview/Jack_Kernel_Preview_Programmable_Cognition_Runtime_v0.1.1.docx`
- `Documentation/Research/Jack_Kernel_Long_Horizon_Cognition_Technical_Whitepaper_v0.1.1.docx`
- `README.md`
- `GETTING_STARTED.md`
- `Documentation/Orchestration/ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md`
- `Documentation/Security/Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md`
- `Documentation/Security/GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_5_2026-10-01.md`

The core DOCX bodies remain intact. They must now be interpreted together with this Phase-6 amendment for current security behavior.

## 3. Governing Phase-6 invariant

> The Phase-6 ledger records deterministic Kernel authority decisions and Kernel-owned security events that actually occur within Jack. It does not become the source of the authority it records, and it does not infer realized host effects that Jack has not deterministically established.

The ledger therefore improves accountability without replacing distributed authority ownership.

The preservation doctrine remains:

> Be strict about truth, identity, authority, and irreversible consequences; be resilient about useful work.

## 4. Process-local ledger authority

Phase 6 is runtime-process scoped.

Each Jack runtime process owns:

- its existing `runtime_id`;
- its existing `lane_id`;
- one process-lifetime `ledger_instance_id`;
- one in-memory authoritative Phase-6 ledger head.

There is no mutable shared cross-runtime authority head.

Cross-runtime or historical aggregation is forensic only. An aggregate view cannot advance, rewrite, reorder, or supersede any individual runtime process's authoritative ledger head.

## 5. Live Phase-6 event vocabulary

Phase 6 deliberately integrates exactly four live event types:

- `REPRESENTED_PATH_DECISION`
- `EXECUTOR_IDENTITY_DECISION`
- `CANARY_MATCH`
- `RESERVED_EVIDENCE_NAMESPACE_BLOCKED`

The event vocabulary is closed at the host-owned schema boundary.

Phase 6 does not expose an arbitrary generic event-append API that lets callers supply free-form authority claims.

## 6. Authority record versus host effect

A Phase-6 represented-path or executor-admission record means that Jack deterministically reached the recorded decision at that boundary.

It does not imply that the host-side consequence was physically realized.

The governing limitation is:

`RepresentedConsequence != NecessarilyRealizedHostEffect`

Phase 6 does not create a universal filesystem-effect oracle, shell-effect oracle, or external-effect attestation system.

## 7. Closed schemas and protected data

Live Phase-6 records use fixed host-owned schemas.

Represented-path records contain only the deterministic represented-path facts and decision metadata required by the accepted design.

Executor identity records contain only runtime/lane match state and the resulting disposition metadata.

Canary records contain only safe Canary ID/tier metadata.

Secret Canary values and protected matched spans are not admitted to the ledger schema.

Reserved-evidence-namespace records capture only the structural block event and do not store arbitrary model payload.

Phase 6 therefore does not become a generalized evidence-trust or credential-content store.

## 8. Canonical SHA-256 predecessor chain

Phase-6 records are deterministically canonicalized and chained by SHA-256 predecessor digest.

Each record contains:

- monotonically allocated process-local sequence;
- `previous_record_digest`;
- `record_digest`.

The first record has no predecessor digest.

The Phase-6 cryptographic claim is intentionally narrow:

> SHA-256 predecessor chaining provides internal chain consistency under the Phase-6 trust model.

It does **not** provide hostile in-process tamper resistance or authenticity against an actor capable of rewriting records and projection metadata together.

Later integrity phases remain responsible for stronger claims.

## 9. Dedicated authority mutex

Phase 6 uses a dedicated process-local authority mutex.

Within the serialized authority transition Jack performs:

1. active predecessor/head validation;
2. next-sequence allocation;
3. canonical record construction;
4. digest construction;
5. immutable durable-representation construction;
6. authoritative in-memory head replacement;
7. bounded projection enqueue.

No filesystem I/O is permitted while this authority mutex is held.

The authority mutex is not telemetry and is not shared with observability state.

## 10. Immutable committed durable projection

The exact persistent record representation is frozen while the authority transition is still under the authority mutex.

The durability path receives a frozen `ProjectionRequest` containing the already-fixed bytes, sequence, and digest.

The writer writes those bytes directly and does not re-serialize caller-visible mutable state after the head transition has committed.

Caller-visible record payload is also exposed through an immutable mapping.

This closes ordinary Python aliasing inside the Phase-6 trust model without claiming hostile process-compromise resistance.

## 11. Durability is separate from authority

The governing separation is:

```text
authoritative process state
!=
durable forensic projection
!=
observability
```

Filesystem persistence occurs outside the authority mutex through a separately serialized bounded durability path.

Slow or failed storage therefore does not hold the authority lock and does not retroactively rewrite a deterministic decision already established by Jack's owning subsystem.

## 12. Bounded fail-soft projection

The Phase-6 projection queue is bounded by a host-owned capacity.

When projection capacity is exhausted or storage fails:

- active authority is not rolled back;
- valid cognition is not automatically cancelled;
- task state is not automatically destroyed;
- memory growth is bounded;
- projection completeness becomes false;
- lost projections are accounted for truthfully.

The implementation records bounded degradation through fields such as:

- `first_lost_sequence`;
- `last_lost_sequence`;
- `lost_projection_count`.

A gap in projected history remains a gap. Phase 6 does not silently manufacture continuity.

## 13. `projection_head.json` is forensic only

`projection_head.json` describes durable projection state.

It is not the active Phase-6 authority head.

It must never be loaded and promoted into a new process's active authority merely because logical `runtime_id` and `lane_id` match a prior process.

The active authority head exists only in the currently running Jack process's Phase-6 ledger state.

## 14. Restart isolation

Every new Jack runtime process lifetime receives a new `ledger_instance_id` and begins a new active Phase-6 chain from genesis.

Prior process histories remain forensic evidence only.

Phase 6 does not claim proven cross-process authority continuity and therefore does not silently promote a historical durable head into current authority.

## 15. `LEDGER_AUTHORITY_FROZEN` containment

If the active Phase-6 ledger detects an impossible internal head/predecessor state, Phase-6 advancement freezes.

`LEDGER_AUTHORITY_FROZEN` means:

- no further Phase-6 records are accepted;
- no fabricated chain continuity is created;
- no new active Phase-6 head is installed.

It does not independently authorize:

- cancellation of model cognition;
- reversal of path-policy decisions;
- reversal of executor-admission decisions;
- invalidation of Canary detection;
- destruction of evidence state outside the affected ledger boundary;
- killing Pi;
- killing Jack Kernel;
- invalidating another runtime;
- destroying unrelated task state.

Broader containment requires a separately established deterministic invariant.

## 16. Preservation of predecessor authority

Phase 6 records authority; it does not replace it.

Phase 4 remains authoritative for represented-path fact production and path-policy semantics.

Phase 5 remains authoritative for deterministic consequence disposition.

Executor admission continues to own runtime/lane admission facts.

Canary detection continues to own exact Canary-match truth.

Evidence filtering continues to own reserved-namespace blocking.

Pi and existing orchestration machinery continue to own lifecycle truth.

Model cognition and frozen-answer authority remain governed by their established mode/runtime contracts.

## 17. Kernel-owned installation and idempotence

Phase 6 is installed by Jack Kernel through the existing bundled-runtime-extension convergence seam.

Responses compatibility is not a security root.

Repeated installation must be idempotent:

- one ledger object per process runtime;
- one `ledger_instance_id` per process runtime;
- no active-head reset;
- no duplicate durability writer;
- no duplicate live-seam wrapping;
- one record for one actual invocation of an integrated live authority/event seam.

Exactly-once behavior does not mean content-based global deduplication of separate authority occurrences.

## 18. Runtime-manifest identity

`jack_authority_ledger.py` is included in Jack's runtime-manifest component set.

Changes to that authority-bearing module therefore affect `RUNTIME_MANIFEST_SHA256` along with the other registered runtime components.

The manifest remains forensic/runtime identity information. Phase 6 does not elevate the manifest into a new independent security-authority source.

## 19. Lifecycle remains out of Phase-6 live recording scope

Phase 6 intentionally does not add lifecycle recording.

There are no live Phase-6 `TASK_BOUND`, `RUN_BOUND`, `RUN_EPOCH_CHANGED`, `CANCELLATION_REQUESTED`, or `SETTLEMENT_OBSERVED` records in this implementation.

Pi remains the lifecycle authority.

The governing rule is:

> Eligibility is not integration.

A fact may be conceptually appropriate for future ledger recording while remaining unrecorded until its exact authoritative ingress is proven.

## 20. Validation and implementation merge

Accepted Phase-6 candidate:

`6bb326bde22cd96ee8ba13227005b88e9d2184f0`

Pre-merge GitHub Actions run #123 validated that exact head with:

- `git diff --check`: **PASS**
- runtime compilation including `jack_authority_ledger.py`: **PASS**
- Phase-5 targeted tests: **37/37 PASS**
- Phase-6 targeted tests: **18/18 PASS**
- full Python suite: **431/431 PASS**
- Pi harnesses: **7/7 PASS**

Pi bridge identities:

- LF SHA-256: `8ffd33fd33ae15a785e2bf9015f17fc14f1de27b09515d5e868ec163d54c15f0`
- CRLF SHA-256: `93a6843cdaaeda637474b584919ed003930296de281570e3ddc391f54ef65565`

The accepted implementation was merged to `main` with a normal merge commit:

`04d7c0843ca6830afaeff4b1bd65e90c87770595`

Merge parents:

- previous Phase-5 `main`: `a0ac5b3db1e9278bef8eecbc0bfd1bce94aa22a4`
- accepted Phase-6 candidate: `6bb326bde22cd96ee8ba13227005b88e9d2184f0`

Merge tree:

`82485fc24b9960a3ea2125ef7e0898b470b52e84`

The merge tree matched the accepted candidate tree exactly.

Post-merge GitHub Actions run #124 passed on exact `main` commit `04d7c0843ca6830afaeff4b1bd65e90c87770595` with:

- runtime compilation: **PASS**
- Phase-5 targeted tests: **37/37 PASS**
- Phase-6 targeted tests: **18/18 PASS**
- full Python suite: **431/431 PASS**
- Pi harnesses: **7/7 PASS**
- unchanged Pi bridge identities as listed above.

The complete implementation release record is documented in:

`docs/security/SECURITY_LAYER_PHASE6_VALIDATED_2026-10-02.md`

That document remains a closure candidate until the dedicated documentation PR is separately merged.

## 21. Explicit nonclaims

Phase 6 does not claim:

- universal host-effect inference;
- final-object filesystem attestation;
- shell semantic interpretation;
- hostile in-process tamper resistance;
- cryptographic authenticity against a process-level history rewriter;
- distributed ledger consensus;
- a mutable global cross-runtime authority head;
- promotion of projected historical state into current process authority;
- generalized evidence trust;
- a live approval subsystem;
- generalized security-health authority;
- lifecycle recording in the Phase-6 ledger;
- a redesign of `jack_path_policy.py`;
- Phase-7 credential or DLP controls;
- Phase-8 Source Drift protection;
- Phase-9 Runtime Code Integrity;
- Phase-10 Authority State Integrity;
- any Phase-11 mechanism.

## 22. Historical preservation

The Phase 0–3, Phase-4, and Phase-5 checkpoint records remain intact historical evidence.

Phase 6 advances current implementation reality without rewriting those prior validation boundaries.

The intended final Phase-6 checkpoint tag is:

`security-layer-phase6-validated-2026-10-02`

This amendment records the intended tag name but does **not** assert that the tag exists.

The documentation closure must be separately merged and tag creation must be separately authorized before Phase 6 is declared fully validated/frozen.

Phase 7 has not started.
