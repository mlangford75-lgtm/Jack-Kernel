# Jack Kernel Security Layer — Phase 6 Validated Checkpoint Candidate

**Date:** 2026-10-02
**Phase:** Runtime-Scoped Authority & Security Ledger
**Baseline before Phase 6:** `a0ac5b3db1e9278bef8eecbc0bfd1bce94aa22a4`
**Accepted implementation head:** `6bb326bde22cd96ee8ba13227005b88e9d2184f0`
**Implementation merge commit on `main`:** `04d7c0843ca6830afaeff4b1bd65e90c87770595`
**Implementation merge tree:** `82485fc24b9960a3ea2125ef7e0898b470b52e84`
**Merge parent 1 — previous Phase-5 `main`:** `a0ac5b3db1e9278bef8eecbc0bfd1bce94aa22a4`
**Merge parent 2 — accepted Phase-6 candidate:** `6bb326bde22cd96ee8ba13227005b88e9d2184f0`
**Implementation pull request:** #27 — `Phase 6: runtime-scoped Authority & Security Ledger`
**Architectural acceptance:** accepted at the Phase-6 implementation stop-gate boundary before merge
**Implementation state:** merged to `main` and post-merge validated
**Documentation state:** closure candidate pending separate merge and tag authorization
**Intended final checkpoint tag:** `security-layer-phase6-validated-2026-10-02` — not yet created

## Scope

Phase 6 introduces a runtime-scoped Authority & Security Ledger that records Jack Kernel's deterministic authority decisions and Kernel-owned security events without becoming the source of the authority it records.

The governing architecture is:

```text
authoritative deterministic subsystem
                |
                v
     established decision / event
                |
                v
    Phase-6 Authority Ledger record
                |
                v
     bounded forensic projection
```

The ledger is downstream of established authority. It records what Jack deterministically decided or detected. It does not re-derive those facts and does not infer host effects that Jack has not actually established.

## Governing invariant

> The Phase-6 ledger records deterministic Kernel authority decisions and Kernel-owned security events that actually occur within Jack. It does not become the source of the authority it records, and it does not infer realized host effects that Jack has not deterministically established.

This preserves the existing Jack doctrine:

> Be strict about truth, identity, authority, and irreversible consequences; be resilient about useful work.

A ledger failure therefore does not automatically become a cognition failure, task failure, executor-authority failure, path-policy failure, or Pi lifecycle failure.

## Process-local authority model

Phase 6 establishes exactly one process-local ledger identity per Jack runtime process lifetime:

- `runtime_id` remains the Kernel's logical runtime identity;
- `lane_id` remains the Kernel's logical lane identity;
- `ledger_instance_id` identifies one physical process-lifetime Phase-6 authority chain.

Each active Jack runtime process owns one in-memory authoritative Phase-6 ledger head.

There is no mutable shared cross-runtime authority head.

A multi-runtime forensic view may aggregate historical chains for inspection, but that aggregation is read-only and cannot advance, rewrite, reorder, or replace any runtime's authoritative head.

## Closed live event vocabulary

The first Phase-6 implementation intentionally records only four live event types:

- `REPRESENTED_PATH_DECISION`
- `EXECUTOR_IDENTITY_DECISION`
- `CANARY_MATCH`
- `RESERVED_EVIDENCE_NAMESPACE_BLOCKED`

Eligibility for future recording is not the same as live integration. Lifecycle facts remain conceptually ledger-worthy but are not wired in this Phase-6 implementation.

## Closed host-owned schemas

Phase 6 does not expose an arbitrary caller-authored append API for generic event dictionaries.

Each live event type has a fixed host-owned schema.

### Represented-path decision

The record contains only the bounded deterministic facts required by the accepted design, including:

- deterministic state;
- NEVER match state;
- whether Workspace Lock is configured;
- workspace membership when deterministically known;
- invalid represented-path state;
- executor deferral state;
- `SecurityOutcome`;
- containment scope.

It does not store arbitrary tool arguments, model content, command text, credentials, or generalized free-form event payloads.

### Executor identity decision

The record contains only:

- `runtime_matches`;
- `lane_matches`;
- `SecurityOutcome`;
- containment scope.

### Canary match

The record contains only safe Canary metadata:

- `canary_id`;
- Canary tier.

The secret Canary value and protected matched span are not admitted to the ledger schema.

### Reserved evidence namespace block

The event records the structural fact that Jack's reserved evidence namespace was blocked. It does not ingest arbitrary model payload or create a generalized evidence-trust classifier.

## Decision record versus realized host effect

A Phase-6 represented-path or executor-admission record is a Kernel authority-decision record.

It can truthfully state that Jack deterministically reached a specific disposition at an authority boundary.

It does not prove that a represented filesystem mutation, shell effect, external side effect, or other host consequence actually occurred.

The established limitation remains:

`RepresentedConsequence != NecessarilyRealizedHostEffect`

Phase 6 does not create universal host-effect attestation.

## Canonical chaining

Each record uses deterministic canonical JSON under the fixed Phase-6 schema.

The chain includes:

- process-local sequence number;
- `previous_record_digest`;
- `record_digest`.

`record_digest` is SHA-256 over the canonical record material excluding the `record_digest` field itself.

The first record has:

```text
sequence = 1
previous_record_digest = null
```

Later records bind to the active predecessor digest.

### Explicit nonclaim

The SHA-256 chain establishes internal predecessor consistency under the Phase-6 trust model.

It does **not** provide hostile in-process tamper resistance or cryptographic authenticity against an actor capable of rewriting projected records and the projected head together.

Those stronger protections remain outside Phase 6 and belong to later integrity phases.

## Atomic authoritative transition

Phase 6 uses a dedicated process-local authority mutex.

The following operations occur under that mutex as one serialized authority transition:

1. validate the current active predecessor/head;
2. allocate the next sequence number;
3. construct the canonical record material;
4. compute the record digest;
5. construct and freeze the exact persistent representation;
6. install the new in-memory authoritative head;
7. enqueue the immutable projection request into the bounded in-memory projection queue.

No filesystem I/O occurs while the authority mutex is held.

The mutex is not an observability lock and is not reused from `RuntimeActivityTracker` or another telemetry subsystem.

## Immutable committed projection

The accepted Phase-6 implementation freezes the exact persistent representation before the authoritative transition leaves the authority mutex.

The durability worker receives an immutable `ProjectionRequest` containing:

- sequence;
- record digest;
- already-canonicalized persistent bytes.

The writer writes those bytes directly. It does not re-serialize a caller-visible mutable object after the authority head has committed.

The caller-visible `AuthorityRecord.payload` is also made immutable through `MappingProxyType`.

The dedicated regression proves that attempted post-commit mutation cannot alter the projected record and that recomputing the persisted digest from canonical record material produces the stored `record_digest` exactly.

## Durability separation

Phase 6 separates active authority from durable forensic projection.

```text
authoritative in-memory ledger state
                |
                v
bounded immutable projection queue
                |
                v
single durability serializer
                |
                v
forensic record files + projection_head.json
```

Filesystem work occurs outside the authority mutex.

The writer uses record-first durable projection and atomic replacement semantics for projected files.

Slow or failed storage cannot hold the authority mutex and cannot retroactively rewrite an already-established predecessor decision.

## `projection_head.json` is non-authoritative

`projection_head.json` is forensic projection metadata only.

It may describe information such as:

- last successfully projected sequence;
- last projected digest;
- projection completeness;
- known lost-projection range;
- projection metadata degradation.

It is never the active Phase-6 authority head.

Startup must not promote `projection_head.json` into the new process's active authority state.

## Restart isolation

A new Jack process lifetime receives a new `ledger_instance_id` and a new in-memory active ledger head beginning from genesis.

Historical projected chains remain forensic history.

Even if the same configured `runtime_id` and `lane_id` are reused after restart, the prior process's persisted head is not silently promoted into current authority.

This deliberately avoids claiming cross-process authority continuity that Phase 6 does not possess machinery to prove.

## Bounded fail-soft durability

The projection queue is strictly bounded by a host-owned Phase-6 capacity.

Authority advancement does not wait indefinitely for disk capacity.

If the queue is full or durable projection fails:

- the already-established authority decision remains valid;
- the active in-memory ledger chain remains authoritative for the process;
- durable projection completeness becomes false;
- lost projection accounting advances truthfully;
- Jack does not roll back the authority decision;
- Jack does not cancel valid cognition merely because forensic storage degraded;
- Jack does not grow an unbounded pending-record list in memory.

The implementation records bounded degradation through fields including:

- `first_lost_sequence`;
- `last_lost_sequence`;
- `lost_projection_count`;
- projection completeness state.

A later projected record may expose a sequence gap and unavailable predecessor on disk. That gap is treated as truthful incomplete projection, not silently repaired history.

## Durability degradation is not cognition failure

Phase 6 distinguishes:

```text
durability failure
!=
active ledger-authority corruption
!=
model cognition failure
```

Ordinary durable storage failure degrades forensic persistence while preserving the deterministic authority decision already established by the owning subsystem.

This continues the Jack preservation doctrine:

> Do not destroy more state than the violation requires.

## Active ledger corruption containment

If the active in-process Phase-6 ledger detects an impossible internal state, such as an invalid predecessor/head condition, it enters the narrow `LEDGER_AUTHORITY_FROZEN` state.

That means:

- no further Phase-6 authoritative records are accepted;
- no fabricated continuity is created;
- no new active ledger head is installed;
- the invalid ledger state is surfaced truthfully.

It does **not** automatically mean:

- cancel model generation;
- invalidate previously frozen cognition;
- reverse an existing path-policy decision;
- allow a previously denied consequence;
- kill Pi;
- kill Jack Kernel;
- invalidate another runtime;
- destroy task state.

Underlying deterministic subsystems retain their own authority.

## Preservation of predecessor authority

Phase 6 does not replace the systems it records.

The following remain authoritative in their established domains:

- Phase-4 represented-path fact production and path-policy semantics;
- Phase-5 consequence disposition;
- executor admission identity checks;
- exact Canary detection;
- reserved evidence namespace filtering;
- model cognition and frozen answer authority under their respective modes;
- task/run/lifecycle authority in Pi and existing orchestration machinery.

The ledger records those established decisions/events where live integration exists. It does not retroactively become their source.

## Kernel-owned installation

Phase-6 installation is Kernel-owned through the existing bundled-runtime-extension convergence seam.

The ledger does not bootstrap Kernel identity and does not make Responses compatibility a security root.

Repeated installation is idempotent:

- the same process retains one ledger object;
- the same process retains one `ledger_instance_id`;
- the active sequence/head is not reset;
- durability writers are not duplicated;
- live seams are not double-wrapped;
- one actual live integrated seam invocation yields one ledger record.

Exactly-once means one record per actual live seam invocation. It does not mean content-based global deduplication of distinct authority occurrences.

## Runtime-manifest identity

`jack_authority_ledger.py` participates in Jack's runtime-manifest component identity.

A change to the authority-bearing ledger module therefore changes `RUNTIME_MANIFEST_SHA256` along with the other registered runtime components.

The runtime manifest remains forensic/runtime identity information. Phase 6 does not give the manifest new independent authority.

## Initial integration scope

The implemented live integration is intentionally limited to:

- represented-path consequence decisions;
- executor runtime/lane admission decisions;
- exact Canary matches;
- exact reserved-evidence-namespace blocks.

No lifecycle recording is wired in this Phase-6 implementation.

Pi remains the lifecycle authority.

## Validation evidence

### Accepted pre-merge stop gate — GitHub Actions run #123

Exact accepted candidate:

`6bb326bde22cd96ee8ba13227005b88e9d2184f0`

Validation:

- `git diff --check`: **PASS**
- runtime module compilation including `jack_authority_ledger.py`: **PASS**
- Phase-5 targeted suite: **37/37 PASS**
- Phase-6 targeted suite: **18/18 PASS**
- full Python suite: **431/431 PASS**
- Pi harnesses: **7/7 PASS**
- Pi bridge LF SHA-256: `8ffd33fd33ae15a785e2bf9015f17fc14f1de27b09515d5e868ec163d54c15f0`
- Pi bridge CRLF SHA-256: `93a6843cdaaeda637474b584919ed003930296de281570e3ddc391f54ef65565`

### Implementation merge

The accepted candidate was merged to `main` with a normal merge commit, without squash or rebase:

`04d7c0843ca6830afaeff4b1bd65e90c87770595`

Parents:

- `a0ac5b3db1e9278bef8eecbc0bfd1bce94aa22a4`
- `6bb326bde22cd96ee8ba13227005b88e9d2184f0`

Merge tree:

`82485fc24b9960a3ea2125ef7e0898b470b52e84`

The merge tree is identical to the accepted candidate tree. No additional runtime changes were introduced by the merge itself.

### Post-merge validation — GitHub Actions run #124

Exact `main` commit:

`04d7c0843ca6830afaeff4b1bd65e90c87770595`

Post-merge validation:

- runtime module compilation: **PASS**
- Phase-5 targeted suite: **37/37 PASS**
- Phase-6 targeted suite: **18/18 PASS**
- full Python suite: **431/431 PASS**
- Pi harnesses: **7/7 PASS**
- Pi bridge LF SHA-256: `8ffd33fd33ae15a785e2bf9015f17fc14f1de27b09515d5e868ec163d54c15f0`
- Pi bridge CRLF SHA-256: `93a6843cdaaeda637474b584919ed003930296de281570e3ddc391f54ef65565`

The PR-only whitespace step is skipped on push events. The accepted candidate diff had already passed `git diff --check` in run #123.

## Released implementation file scope

Relative to the validated Phase-5 baseline, the accepted Phase-6 implementation changed nine repository files:

- `.github/workflows/ci.yml`
- `jack_authority_ledger.py`
- `jack_consequence_gate.py`
- `jack_kernel.py`
- `tests/test_phase6_authority_ledger.py`
- `tests/test_phase6_consequence_ledger_integration.py`
- `tests/test_phase6_runtime_installation.py`
- `tests/test_phase6_security_event_ledger.py`
- `tests/test_surgical_regressions.py`

Notably absent from the Phase-6 implementation diff:

- `Pi/pi-control-bridge.ts` changes;
- `jack_path_policy.py` redesign;
- lifecycle recording;
- Phase-7 implementation;
- Phase 8–11 implementation.

## Explicitly unclaimed

This checkpoint does not claim:

- universal realized host-effect knowledge;
- hostile in-process ledger tamper resistance;
- cryptographic authenticity against a process-level attacker able to rewrite history;
- shared cross-runtime authority serialization;
- distributed consensus;
- promotion of forensic persisted state into current process authority;
- generalized evidence trust;
- a live approval subsystem;
- one universal lifecycle mismatch severity;
- lifecycle recording in the Phase-6 ledger;
- Phase-7 credential or DLP controls;
- Phase-8 Source Drift protection;
- Phase-9 Runtime Code Integrity;
- Phase-10 Authority State Integrity;
- any Phase-11 mechanism.

## Historical chain

Phase 6 is cumulative.

The Phase 0–3, Phase-4, and Phase-5 checkpoints remain historical evidence and are not rewritten by this release.

Phase 4 continues to own represented-path fact production and path-policy semantics.

Phase 5 continues to own deterministic consequence disposition.

Phase 6 adds accountable process-local authority history and bounded forensic projection on top of those established authorities.

## Closure state

The Phase-6 architecture, implementation merge, and post-merge validation are accepted.

This document is a documentation/checkpoint-closure candidate only until its dedicated documentation PR is separately reviewed and merged.

The intended final checkpoint tag is:

`security-layer-phase6-validated-2026-10-02`

That tag does **not** yet exist and must not be treated as created or validated merely because its intended name appears here.

Phase 6 must not be declared fully frozen/closed until the documentation closure is merged and final checkpoint tag creation is separately authorized and completed.

Phase 7 has not started.
