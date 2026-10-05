# Jack Kernel Security Layer — Phase 7 Validated Closure

**Validation date:** 2026-10-05  
**Status:** COMPLETE / VALIDATED / MERGED IMPLEMENTATION  
**Implementation PR:** #35  
**Baseline main:** `0c2a65a20cc9639efe8aa59f8ec73a2578e57b8e`  
**Accepted pre-merge implementation head:** `e33a529bc3035207475b3cf530cadac62b3533fd`  
**Implementation merge commit:** `ec47aeb32702876ba1cd91078457e027325c5e04`  
**Acceptance PR CI:** #182 PASS  
**Post-merge main CI:** #183 PASS  
**Desired validated tag:** `security-layer-phase7-validated-2026-10-05`

---

## 1. Closure statement

Phase 7 is complete for its defined scope: deterministic credential authority, exact known-credential isolation at model ingress and Kernel-controlled release boundaries, exact credential-resource represented-path protection, and safe Phase-7 security-event recording in the existing process-local Authority Ledger.

Phase 7 does not redefine Jack's core doctrine:

> **Probabilistic cognition may propose, but deterministic software must dispose.**

The Phase-7 security objective is not generic secret-looking-text classification. It is narrower and stronger:

> A credential that Jack deterministically knows to be protected must not become model-visible cognition or unauthorized Kernel-controlled release merely because probabilistic cognition, a backend, an orchestration observer, or a diagnostic path contains that exact value.

Authorized credential transport remains distinct from credential leakage.

---

## 2. Governing preservation doctrine

Phase 7 was reviewed under the standing Jack gate:

1. **Reality:** what does the live system actually do?
2. **Authority:** what fact is host-authoritative, and who owns it?
3. **Invariant:** what must not be violated?
4. **Preservation:** what useful cognition/state can survive without violating the invariant?
5. **Regression surface:** what capability, latency, recovery, complexity, false-positive, or blast-radius cost is introduced?
6. **Evidence:** do tests prove the intended invariant rather than merely encode current implementation?
7. **Boundary:** is the behavior Kernel mechanism/authority or program-level strategy/cognition?

Active distinctions:

- `primitive correctness != integration correctness != phase completion`
- `credential authority > matching implementation convenience`
- `reality > legacy test`
- `cognition != release authority`
- `observability != authority`
- `error truth != release authority`
- `evidence != authority`
- `unsafe observer/diagnostic release != worker cancellation/settlement/failure`

The Phase-7 containment rule remains:

> Block the unsafe consequence while preserving all useful work and state that can safely survive.

---

## 3. Closed protected credential source set

Initial Phase-7 credential authority is intentionally closed. The live runtime snapshots exact protected values from:

- `CFG.api_key`
- `CFG.backend_api_key`
- `CFG.backend_header_value`
- `CFG.backend_password`
- `CFG.backend_authorization_value`
- the deterministic HTTP Basic Authorization representation derived from configured backend username/password
- the resolved private Pi control token

Closed credential classes:

- `JACK_API`
- `BACKEND_BEARER`
- `BACKEND_NAMED_HEADER`
- `BACKEND_BASIC_PASSWORD`
- `BACKEND_BASIC_WIRE`
- `BACKEND_AUTHORIZATION`
- `PI_CONTROL`

Phase 7 does **not** make a hard credential claim merely because text is:

- `sk-*`-looking
- JWT-looking
- base64-looking
- high-entropy-looking
- hex-looking
- password-looking
- authorization-looking
- from an unknown provenance

The hard criterion is an exact match to a registered host-owned protected value at an unauthorized boundary.

---

## 4. Immutable runtime/lane credential authority

`RuntimeCredentialPolicy` is built once for a runtime/lane from the closed source set and remains the active supported policy snapshot.

Phase 7 intentionally separates credential authority from output-streaming matcher convenience:

- a non-empty configured credential is protected even if short;
- model-input protection does not inherit an arbitrary minimum length;
- future/output StreamingIRQ suitability remains a separate bounded-mechanism concern.

Supported environment/configuration mutation or installer re-entry does not silently replace the active credential snapshot.

This is an installation-time supported-transition immutability claim, **not** hostile in-process tamper resistance.

---

## 5. Model-input isolation

At model dispatch, Jack inspects the final model-bound JSON payload for exact registered protected values before backend transport is allowed to proceed.

The validated semantic distinction is:

```text
credential value in model-bound cognition
!=
credential value in authorized transport
```

A protected credential in the final model payload causes the dispatch boundary to be withheld. The same value may still be used in its explicitly authorized backend authentication destination.

The Phase-7 ledger observes the raw model-input match at the guarded transport seam that owns the fact. It does not infer the fact later from a translated backend exception.

---

## 6. Model-output credential DLP

Credential-derived exact values are merged into the existing Tier-A Canary policy **before** the evidence/output release guard activates.

The architecture remains one release barrier:

```text
RuntimeCredentialPolicy
        ↓
credential-derived Tier-A values
        ↓
immutable RuntimeCanaryPolicy
        ↓
existing jack_evidence_guard / StreamingIRQ
        ↓
KERNEL.run / KERNEL.stream release
```

No second model-output scanner or duplicate StreamingIRQ subsystem was introduced.

Validated output surfaces include streamed/non-stream:

- content
- reasoning content
- reasoning/thinking aliases
- tool-call arguments

Streaming behavior preserves already-proven-safe prefix material while withholding the completing credential-bearing release. Non-stream cognition may complete internally while the violating result remains unreleased.

Therefore:

```text
cognition completed internally
!=
release authorized externally
```

---

## 7. Orchestration release DLP

Phase 7 protects two Jack-owned orchestration observer release surfaces:

1. ordinary public orchestration HTTP responses;
2. the replayable orchestration SSE event hub.

Credential-bearing HTTP response material is replaced with safe structural output before caller release.

Credential-bearing Pi SSE source events do not enter Jack's replay buffer raw. They are replaced with a safe sequenced observer event.

Known Pi textual streaming delta channels use bounded cross-event carry scoped by:

```text
(task_id, run_id, run_epoch, delta_channel)
```

This prevents a complete registered credential from escaping when it is split across successive known message-delta events without inventing a universal arbitrary-event concatenation oracle.

A partial prefix is not independently classified as secret merely because it could become part of a protected value later. The event that completes the exact registered value is withheld.

Most importantly:

```text
observer release blocked
!= worker cancellation
!= run settlement
!= worker failure
```

Observability remains non-authoritative over worker cognition and lifecycle.

---

## 8. Diagnostic/backend-error release DLP

Phase 7 preserves precise internal failure truth where useful and separates that truth from release authority.

Validated Jack-owned diagnostic release surfaces include:

- caller-visible `HTTPException.detail`
- nested diagnostic dictionary keys and values
- caller-visible exception headers
- streamed `KERNEL.stream` failure propagation
- Chat Completions public SSE failure rendering
- Responses API `response.failed` rendering
- Jack-owned `LOG` records and traceback material
- retained `OrchestrationEventHub._last_error` state

If a registered credential is present, the secret-bearing representation is withheld and safe host-owned structure is emitted. Meaningful HTTP status and independently clean headers survive.

The process-global logger `logging.getLogger("jack-kernel")` is treated as a real shared observer boundary. It aggregates immutable policies for installed runtime instances rather than allowing the first runtime to monopolize logger security.

The logger policy is intentionally conservative for process lifetime; Phase 7 does not claim dynamic runtime-policy deregistration authority.

---

## 9. Exact credential-resource represented-path protection

Phase 7 protects the exact known credential-bearing configuration resources rather than entire user profiles/directories.

Initial resource identities include the Jack configuration resource and the Pi Jack configuration resource derived from the runtime's known credential-resource locations.

The critical containment rule is:

```text
exact protected credential resource
→ DENY_AND_CONTINUE

parent directory
→ not denied merely because it contains that file

adjacent harmless file
→ not denied merely because it is nearby
```

Credential resources are **not** converted into Phase-4 NEVER roots. A model-authored attempt to access the exact protected resource is a narrow consequence denial, not automatically a global HARD_INTERRUPT.

Phase 7 preserves the existing Phase-4 represented-path authority model. It does not claim filesystem-object attestation, symlink/reparse-point resolution proof, universal child-process effect knowledge, or a universal OS sandbox.

The validated credential-resource integration follows the existing Phase-4 Windows represented-path model and is not a universal POSIX enforcement claim.

---

## 10. Phase-7 Authority Ledger extension

Phase 7 extends the **same** process-local Authority Ledger chain established by Phase 6. It does not create a second mutable authority ledger.

Closed Phase-7 event types:

- `PROTECTED_CREDENTIAL_MATCH`
- `PROTECTED_CREDENTIAL_RESOURCE_BLOCKED`

Phase-7 ledger records contain safe structural metadata only. They do not contain credential bytes or protected absolute resource paths.

Recording is fail-soft and observational:

```text
security fact/disposition
        ↓ already established by owning boundary
Phase-7 ledger observation
```

The ledger does not create the credential match, DLP result, resource denial, cancellation state, or settlement fact.

Phase-6 represented-path record meaning is preserved. When an exact credential resource is otherwise allowed by predecessor Phase-4 path facts, the Phase-6 `REPRESENTED_PATH_DECISION` remains an `ALLOW` record for those predecessor facts; Phase 7 appends a separate `PROTECTED_CREDENTIAL_RESOURCE_BLOCKED` record for the new credential-resource authority.

Live evidence covers ledger observation for:

- model-input dispatch
- model-output release
- orchestration HTTP release
- orchestration SSE event release
- diagnostic HTTP release
- diagnostic streamed release
- Jack log release
- retained diagnostic state
- exact credential-resource denial

Configured `runtime_id`/`lane_id` strings are not treated as globally unique runtime-instance identity within an embedding/test process. Shared process-global observer registration binds the exact immutable credential-policy object to its owning ledger.

---

## 11. Validation evidence

### Accepted pre-merge implementation candidate

Commit:

`e33a529bc3035207475b3cf530cadac62b3533fd`

CI #182: **PASS**

Exact validated counts:

- Phase-5 targeted: **37 passed**
- Phase-6 targeted: **18 passed**
- Phase-7 targeted: **34 passed**
- full Python regression: **483 passed**
- Pi harnesses: **7 / 7 PASS**
- compile: PASS
- pull-request diff whitespace check: PASS

Validated Windows toolchain:

- Python 3.14.6
- pip 26.2.1
- Node 24.16.0
- FastAPI 0.137.1
- Uvicorn 0.49.0
- HTTPX 0.28.1
- pytest 9.1.1
- Starlette 1.3.1
- Pydantic 2.13.4

### Implementation merge

PR #35 merged as:

`ec47aeb32702876ba1cd91078457e027325c5e04`

### Post-merge validation

Main push CI #183: **PASS**

The merged main commit passed compilation, Phase-5 targeted, Phase-6 targeted, Phase-7 targeted, full Python regression, and all seven Pi control-bridge harnesses.

---

## 12. Evidence corrections that materially changed the implementation

Phase 7 deliberately records its failed assumptions because green tests were not treated as complete evidence.

### Credential authority vs matcher convenience

The early foundation inherited an 8-character minimum from future StreamingIRQ considerations. That was rejected: a host-configured credential remains authoritative regardless of convenient matcher length. Input authority and output streaming bounds were separated.

### Runtime manifest truth

As live Phase-7 modules became runtime participants, predecessor exact-component tests became stale. Tests were corrected rather than hiding real components from runtime identity.

### Real Pi cross-event streaming topology

An earlier green orchestration CI did not cover credentials split across repeated Pi `message_update` delta events. The live Pi topology was audited, bounded cross-event carry was added, and stronger adversarial evidence was required.

### Process-global logging ownership

The first diagnostic logger design let one runtime policy effectively own the process-global Jack logger. CI exposed the mismatch. The design was corrected so the shared observer accounts for all installed runtime policies.

### Diagnostic key/header release carriers

Post-implementation review identified nested diagnostic keys and HTTP exception headers as release-capable surfaces. They were covered explicitly rather than relying on current producers never to use them.

### Runtime instance vs configured identity

The first final-ledger registry treated `(runtime_id, lane_id)` as globally unique for an entire Python process. This was too strong for isolated runtime instances that legitimately reuse configured identity. The process-global observer mapping was corrected to bind the exact immutable credential-policy object.

### Fact-owner ledger observation

Model-input credential interrupts are translated by the backend into generic transport failure. The ledger therefore records the raw credential-match fact at the guarded transport seam that owns it, rather than trying to infer backward from an outer translated exception.

### Live hook evidence

A final ledger-hook test initially used the wrong synthetic output shape. The test was corrected to the real KernelResult-like release shape, runtime code was left unchanged, and the full gate was rerun. Diagnostic stream ledger evidence was also made explicit before closure.

---

## 13. Explicit nonclaims

Phase 7 does **not** claim:

- hostile in-process tamper resistance;
- impossibility of deliberate monkeypatching by code with equivalent process authority;
- universal third-party/service logger control;
- universal filesystem-object attestation;
- universal shell-effect or external-child-process effect knowledge;
- a universal OS sandbox;
- encrypted-at-rest secret custody redesign;
- arbitrary-prefix secrecy beyond exact registered credential semantics;
- distributed or cross-runtime consensus ledger authority;
- shared mutable cross-runtime ledger head;
- dynamic process-global logger policy deregistration;
- proof that represented filesystem consequences physically occurred;
- Phase 8 Source Drift guarantees;
- Phase 9 Runtime Code Integrity guarantees;
- Phase 10 Authority State Integrity guarantees;
- Phase 11 Privacy/Telemetry Hardening guarantees.

These are later or separate authority domains and must not be retroactively attributed to Phase 7.

---

## 14. Final Phase-7 architecture

```text
closed host credential sources
        ↓
immutable runtime/lane RuntimeCredentialPolicy
        ├─ model-input dispatch isolation
        ├─ credential-derived Tier-A policy
        │      ↓
        │  existing StreamingIRQ model-output release barrier
        ├─ orchestration HTTP / SSE observer release DLP
        ├─ diagnostic/error release DLP
        └─ exact credential-resource authority
               ↓
           DENY_AND_CONTINUE at represented path

all owning enforcement boundaries
        ↓
safe Phase-7 event observation
        ↓
existing process-local Authority Ledger chain
```

The resulting design remains faithful to Jack's governing objective:

> **Be strict about truth, identity, authority, and irreversible consequences; be resilient about useful work.**

---

## 15. Freeze state

Phase-7 implementation is merged and post-merge validated.

The intended validated checkpoint name is:

`security-layer-phase7-validated-2026-10-05`

The final freeze identity must point to the closure-complete main commit after this closure document itself is merged and validated. A tag is only considered created if an actual Git tag/reference is present in the repository; a branch or documentation string is not a substitute for a tag.

Phase 8-11 remain separate future work and are not authorized or implied by this Phase-7 closure.
