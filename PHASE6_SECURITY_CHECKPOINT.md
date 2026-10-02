# Phase 6 — Runtime-Scoped Authority & Security Ledger

**Status:** Implementation merged and post-merge validated on `main`; documentation/checkpoint closure candidate pending separate merge and tag authorization  
**Date:** 2026-10-02

Phase 6 adds a runtime-scoped Authority & Security Ledger that records Jack Kernel's deterministic authority decisions and Kernel-owned security events without becoming the source of the authority it records.

Accepted Phase-6 implementation candidate:

`6bb326bde22cd96ee8ba13227005b88e9d2184f0`

Implementation merge commit on `main`:

`04d7c0843ca6830afaeff4b1bd65e90c87770595`

Implementation merge tree:

`82485fc24b9960a3ea2125ef7e0898b470b52e84`

Merge parents:

- previous Phase-5 `main`: `a0ac5b3db1e9278bef8eecbc0bfd1bce94aa22a4`
- accepted Phase-6 candidate: `6bb326bde22cd96ee8ba13227005b88e9d2184f0`

Validation:

- pre-merge CI #123: **PASS**
  - Phase-5 targeted tests: **37/37 PASS**
  - Phase-6 targeted tests: **18/18 PASS**
  - full Python suite: **431/431 PASS**
  - Pi harnesses: **7/7 PASS**
- post-merge CI #124: **PASS**
  - runtime compilation: **PASS**
  - Phase-5 targeted tests: **37/37 PASS**
  - Phase-6 targeted tests: **18/18 PASS**
  - full Python suite: **431/431 PASS**
  - Pi harnesses: **7/7 PASS**
- Pi bridge LF SHA-256: `8ffd33fd33ae15a785e2bf9015f17fc14f1de27b09515d5e868ec163d54c15f0`
- Pi bridge CRLF SHA-256: `93a6843cdaaeda637474b584919ed003930296de281570e3ddc391f54ef65565`

Governing rule:

> The Phase-6 ledger records deterministic Kernel authority decisions and Kernel-owned security events that actually occur within Jack. It does not become the source of the authority it records, and it does not infer realized host effects that Jack has not deterministically established.

The live Phase-6 event vocabulary is intentionally closed:

- `REPRESENTED_PATH_DECISION`
- `EXECUTOR_IDENTITY_DECISION`
- `CANARY_MATCH`
- `RESERVED_EVIDENCE_NAMESPACE_BLOCKED`

Core invariants:

- one process-local `ledger_instance_id` per Jack runtime process lifetime;
- one in-memory authoritative Phase-6 ledger head per runtime process;
- no mutable shared cross-runtime authority head;
- multi-runtime aggregation is forensic only;
- SHA-256 predecessor chaining provides internal chain consistency under the Phase-6 trust model, not hostile in-process tamper resistance;
- the committed durable projection is immutable before the authority transition leaves the authority mutex;
- `projection_head.json` is forensic projection metadata only and is never active authority;
- persisted historical heads are never promoted into a new process's live authority;
- predecessor validation, sequence allocation, digest construction, active-head replacement, and bounded projection enqueue occur atomically under the dedicated authority mutex;
- filesystem I/O never occurs while that authority mutex is held;
- durability runs separately through a bounded projection queue;
- projection loss is accounted for truthfully instead of rolling back authority, cancelling cognition, or allowing unbounded memory growth;
- durability degradation is not cognition failure;
- `LEDGER_AUTHORITY_FROZEN` contains active ledger-state corruption to further Phase-6 advancement unless another established invariant independently requires broader containment.

Phase 6 preserves predecessor authority. Path policy, executor admission, Canary detection, evidence filtering, cognition, task state, and Pi lifecycle authority remain owned by their established subsystems.

Kernel installation remains Kernel-owned through the existing bundled-extension convergence seam. `jack_authority_ledger.py` participates in Jack's runtime-manifest identity. Installation is idempotent, and one live integrated seam invocation produces one ledger record without content-based global deduplication.

Phase 6 deliberately does **not** add lifecycle recording, change Pi, redesign `jack_path_policy.py`, implement Phase-7 credential/DLP controls, or implement any Phase 8–11 mechanism.

Full records:

- [Phase-6 security-layer checkpoint candidate](docs/security/SECURITY_LAYER_PHASE6_VALIDATED_2026-10-02.md)
- [Phase-6 governing security amendment candidate](Documentation/Security/GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_6_2026-10-02.md)
- [Security hardening architecture](Documentation/Security/Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md)

Historical checkpoints remain intact:

- [Phase 0–3 validated checkpoint](docs/security/SECURITY_LAYER_PHASE0_3_VALIDATED_2026-09-27.md)
- [Phase-4 validated checkpoint](docs/security/SECURITY_LAYER_PHASE4_VALIDATED_2026-09-30.md)
- [Phase-5 validated checkpoint](docs/security/SECURITY_LAYER_PHASE5_VALIDATED_2026-10-01.md)

Intended final checkpoint tag:

`security-layer-phase6-validated-2026-10-02`

This document records the intended tag name but does **not** assert that the tag exists. The documentation PR must be separately reviewed and merged, and tag creation must be separately authorized before Phase 6 is declared fully validated/frozen.

Phase 7 has not started.
