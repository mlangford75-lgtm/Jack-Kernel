# Current Security Status

**Jack Kernel v0.1.1**

**Last fully validated and frozen security checkpoint:** Source Drift Protection

**Current implemented security layer (2026-11-25):** Runtime Code Integrity — Selected Runtime Executable Identity and Consequence-Boundary Enforcement. **Mandatory in secured `--serve` child on `main`; merged as [PR #173](https://github.com/mlangford75-lgtm/Jack-Kernel/pull/173), merge commit `6565e08b2e4bd114725b8edea6987880498f3087`.** Target-qualified, but **not fully validated/frozen/tagged**.

**Last validated/frozen security checkpoint date:** 2026-10-06

**Research/status reconciliation date:** 2026-10-14

**Validated annotated tag:** `security-layer-phase8-validated-2026-10-06`

**Annotated tag object:** `20e35610444f409bbccd62a461e42e2dce06ac6a`

**Validated tag target / Source Drift Protection closure commit:** `cebe9fd75fe30a9c84a0af08d2105af448fc3d00`

**Validated closure tree:** `7288396653db3590834d9ac1093207c4e1b19c3b`

**Tag state:** unsigned annotated tag

Source Drift Protection is **VALIDATED / MERGED / DOCUMENTED / TAGGED / FROZEN**.

**runtime-code research:** exploratory research closed 2026-10-14 (historical only).

**Runtime Code Integrity:** mandatory selected runtime-code-integrity enforcement **implemented and target-qualified on 2026-11-25** in [PR #173](https://github.com/mlangford75-lgtm/Jack-Kernel/pull/173); **not yet a complete production-security validation**. GitHub Actions [run 45606058846](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/45606058846) on candidate SHA `563d02f682a5213ea7962263477b717e30a152ff` completed **98 targeted Windows Python 3.14.6 tests** (54 Runtime Code Integrity primitive/enforcement, 3 real-Kernel subprocess, 1 mandatory secure-child startup, 1 live post-start adversarial HTTP, 39 unchanged Source Drift Protection). The live attack swapped actual `KERNEL.run` and API-authentication callables in the already-running secured child; both attempted releases were denied before the unauthorized functions executed. A successful targeted run does not replace the full cross-mode regression suite.

**Merge status:** Merged 2026-11-25 via PR #173, without declaring Runtime Code Integrity a frozen full-security checkpoint. The exact pre-merge security target-qualified SHA is `563d02f682a5213ea7962263477b717e30a152ff` (98 targeted Windows tests). Main's merged implementation is `6565e08b2e4bd114725b8edea6987880498f3087`. Post-merge full CI must be evaluated independently.

**Outstanding CI qualification:** The general PR workflow initially failed its `git diff --check` gate because of Markdown trailing whitespace (corrected on this branch). The prior Nov 24 `main` full-suite gate also failed in a Coder Planner compatibility test (24 passed / 24 failed in that file), preventing downstream full Windows and Pi gates. These failures must be reconciled without changing approved Architect/Coder behavior or concealing genuine regressions.

Research evidence: [`docs/security/SECURITY_LAYER_PHASE9A_RESEARCH_CHECKPOINT_2026-10-14.md`](docs/security/SECURITY_LAYER_PHASE9A_RESEARCH_CHECKPOINT_2026-10-14.md).

Post-Source Drift Protection maintenance: PR #45 (Agentic tool-result provenance correction), PR #46 (Responses API error non-disclosure), and PR #47 (runtime-code research documentation) merged. The verified October 14 post-fix source baseline `ef613e46e70181f7fa8d054aabc3b5a744d8f704` passed **527 Windows Python tests**. This is a dated test baseline, not a claim that this SHA remains the latest GitHub `main`. Neither maintenance fix implements Runtime Code Integrity Runtime Code Integrity. Source Drift Protection remains the latest validated/frozen security checkpoint.

**runtime-code research milestone:** annotated tag `security-layer-phase9a-research-closed-2026-10-14` points to documentation merge commit `5e909494eb354c45907bb15c9a621980f99b2263`. The tag marks **research closure only**, not Runtime Code Integrity security validation.

## Source Drift Protection validation identity

Source Drift Protection was developed and closed through these exact repository identities:

- Credential Isolation and DLP baseline `main`: `0168d60577deb62c93cc82607206395eab00edb8`
- source baseline accepted head: `956bcad5c7ca8e66a9c5355af0c58538a7e18845`
- source baseline merge / PR #38: `7274854e18bb54824669f7ef5f650c5c6c8a4b7b`
- source enforcement accepted head: `16ac1172d8cf5a5a33e21f6b626149d104db2c1a`
- source enforcement merge / PR #39: `2ee9967e5d3a6a5b33c748aa716842f6b6c9c672`
- source ledger observation accepted head: `c8b6f84f8f7f6818a1184d0d7c49cb523e71b2c2`
- source ledger observation merge / PR #40: `7e9b1fa74c74ee374110307ea9b8b5e779272a9e`
- source preservation accepted head: `106fab166d187ef381db90eb9dbe17ae2ae37cab`
- source preservation implementation merge / PR #41: `90077f157183f442bb1d41eb23af865fab94ea43`
- accepted/integrated source preservation implementation tree: `93771e59ab7f9213d438bc56dbe434961b07c0f4`
- source validation closure closure merge / PR #42: `cebe9fd75fe30a9c84a0af08d2105af448fc3d00`
- validated closure tree: `7288396653db3590834d9ac1093207c4e1b19c3b`
- annotated tag object: `20e35610444f409bbccd62a461e42e2dce06ac6a`
- annotated tag peeled target: `cebe9fd75fe30a9c84a0af08d2105af448fc3d00`

The accepted source preservation candidate tree and integrated implementation tree are identical. Dependency-order merge mechanics introduced no implementation-content drift.

Validation evidence:

- source baseline CI #194: **PASS**
- source enforcement CI #204: **PASS**
- source ledger observation CI #211: **PASS**
- source preservation CI #212: **PASS**
- integrated implementation CI #216: **PASS**
- closure-complete main CI #218: **PASS**
- Consequence Gate targeted regression: **38 passed**
- Authority & Security Ledger targeted regression: **18 passed**
- Credential Isolation and DLP targeted regression: **34 passed**
- Source Drift Protection targeted source-authority/preservation regression: **39 passed**
- complete Python regression: **523 passed**
- Pi harnesses: **7 / 7 PASS**
- runtime compilation: **PASS**

Validated toolchain:

- Windows Server 2025 / `windows-2025-vs2026`
- Python 3.14.6
- pip 26.2.1
- Node.js 24.16.0
- FastAPI 0.137.1
- Uvicorn 0.49.0
- HTTPX 0.28.1
- pytest 9.1.1
- Starlette 1.3.1
- Pydantic 2.13.4

Validated Pi bridge identities:

- canonical repository LF SHA-256: `8ffd33fd33ae15a785e2bf9015f17fc14f1de27b09515d5e868ec163d54c15f0`
- Windows CRLF representation SHA-256: `93a6843cdaaeda637474b584919ed003930296de281570e3ddc391f54ef65565`

## Cumulative validated security stack

### Phases 0–3 — deterministic release-boundary security

Deterministic `SecurityOutcome`, bounded StreamingIRQ pre-release quarantine, malformed-SSE release protection, exact-match Canary enforcement, and immutable runtime/lane-bound startup policy.

Historical record:

- `docs/security/SECURITY_LAYER_PHASE0_3_VALIDATED_2026-09-27.md`

### Restricted Paths / Workspace Lock

Host-owned represented-path policy, deterministic NEVER-path enforcement, optional Workspace Lock, bounded recognized command authorization, consequence-release enforcement, executor admission, and minimum multi-call containment.

Historical record:

- `docs/security/SECURITY_LAYER_PHASE4_VALIDATED_2026-09-30.md`

### Deterministic Consequence Gate

Consumes typed authoritative facts from the subsystems that actually own them and selects the narrowest deterministic disposition sufficient to preserve the violated invariant.

Historical record:

- `docs/security/SECURITY_LAYER_PHASE5_VALIDATED_2026-10-01.md`

### Runtime-Scoped Authority & Security Ledger

Process-local Authority & Security Ledger with canonical predecessor chaining, immutable committed projection, bounded fail-soft durability, restart isolation, and narrow ledger-authority freeze behavior. The ledger records selected established facts; it does not become the source of the authority it records.

Historical record:

- `docs/security/SECURITY_LAYER_PHASE6_VALIDATED_2026-10-02.md`

### Credential Isolation and DLP

Closed known-credential authority protecting exact registered values at validated model ingress, model egress, orchestration observer release, diagnostic release, credential-resource represented paths, and safe ledger observation boundaries.

Historical record:

- `docs/security/SECURITY_LAYER_PHASE7_VALIDATED_2026-10-05.md`

### Source Drift Protection

Source Drift Protection establishes bounded exact source identity for the authority-bearing active runtime and withdraws new Kernel-authoritative admission if that source identity becomes unavailable or mismatched.

Lifecycle:

```text
INITIALIZING -> ACTIVE
ACTIVE -> SUSPENDED_UNVERIFIED
SUSPENDED_UNVERIFIED -> ACTIVE      (exact re-verification)
ACTIVE/SUSPENDED -> INVALIDATED     (confirmed mismatch; terminal)
```

Validated Source Drift Protection authority includes:

- immutable protected-source baseline before ACTIVE;
- exact regular-file byte identity and canonical component identity;
- bounded pre-ready, authority-boundary, and periodic remeasurement;
- final non-stream result and streamed release enforcement;
- structured tool release and executor admission enforcement;
- mutating orchestration admission enforcement;
- selected Jack-owned durable-write enforcement;
- concurrency-safe lifecycle facts and forensic ordering;
- fail-soft Authority & Security Ledger ledger observation;
- adversarial anti-brittleness/preservation closure.

Permanent preservation statement:

> **Source-authority loss withdraws new Kernel-authoritative admission. It does not imply process death, blanket cancellation, invented worker failure, erasure of completed cognition, or loss of safe observation.**

Permanent execution boundary:

> **Source Drift Protection serializes Kernel-authoritative admission, not physical continuous-world execution after an admission already occurred.**

Permanent forensic distinction:

```text
transition_sequence
=
process-local source-transition chronology for truthful forensic ordering

transition_sequence
!= source authority
!= admission authority
!= Policy Integrity integrity protection

ordering-buffer health
!= source-enforcement health
```

Authoritative closure record:

- `docs/security/SECURITY_LAYER_PHASE8_VALIDATED_2026-10-06.md`

## Runtime Code Integrity — Current selected loaded-code enforcement (2026-11-25)

**Design and implementation:** The secured `jack_secure_entrypoint.py --serve` process installs Runtime Code Integrity **unconditionally after Source Drift Protection activation**. An absent required P0 manifest or invalid seal prevents normal secured-child startup. There is **no runtime enable/disable toggle**. The model can propose outputs, but code identity is measured against a stable protected binding manifest before consequential request, tool, executor, Pi and HTTP-release boundaries.

Key files:

- `jack_runtime_code_guard.py` — selected function/descriptor/receiver, code constants/nested-code/selected delegates, imported module and FastAPI route-table identity. It distinguishes confirmed mismatch from temporary measurement unavailability; confirmed compromise is terminal within the secured child.
- `jack_runtime_code_enforcement.py` — effective post-Source Drift Protection Kernel wrappers plus ASGI ingress and release interception for streaming and nonstreaming responses, selected executor paths and mutating Pi control.
- `jack_secure_entrypoint.py` — mandatory Runtime Code Integrity installation in the actual secured serving child.
- `tests/test_runtime_code_live_security_http_tamper.py` — actual secured-child post-start code replacement and blocked HTTP consequence, with explicit checks that substituted functions never ran.

**Containment is dependency driven, not unconditional survival or unconditional shutdown.** The shared verifier, API authentication, source-checking, represented-path and consequence-policy integrity are common security dependencies. New Pi tasks require model, executor and orchestration trust; independently verified cancellation can remain available without starting new work. Already-released safe SSE bytes are not erased, but later compromised streaming work is interrupted rather than deliberately drained.

**Security limits:** This is selected live Python executable-identity enforcement, **not** complete arbitrary same-process attacker resistance, remote attestation, operating-system isolation, final filesystem-object identity, or proof of already-admitted external side-effect settlement. The Runtime Code Integrity code files are not automatically in the frozen Source Drift Protection source-file set. No guarantee is made about every unmeasured delegate, ASGI root substitution, fully privileged interpreter mutation or TOCTOU adversaries. Real backend streaming under concurrent tampering, actual external tool/Pi consequences, performance and complete Windows/Pi regressions remain outstanding.

Evidence:

- [Runtime Code Integrity runtime authority map](docs/security/PHASE9B_A_CURRENT_RUNTIME_AUTHORITY_MAP_2026-11-25.md)
- [Runtime Code Integrity code-identity qualification](docs/security/PHASE9B_B_EXPERIMENTAL_IDENTITY_QUALIFICATION_2026-11-25.md)
- [Runtime Code Integrity enforcement qualification](docs/security/PHASE9B_C_EXPERIMENTAL_ENFORCEMENT_QUALIFICATION_2026-11-25.md)
- [Runtime Code Integrity dependency and containment review](docs/security/PHASE9B_DEPENDENCY_CONTAINMENT_REVIEW_2026-11-25.md)
- [Windows attack and targeted validation run](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/45606058846)

**Checkpoint classification:** Source Drift Protection is the last formally frozen/tagged full security validation. Runtime Code Integrity has passed its recorded targeted tests; **full closure and tagging are not claimed**.

## Explicit current nonclaims

The current security stack does **not** claim:

- continuous historical source attestation;
- proof that protected disk bytes were never transiently changed between bounded measurements;
- universal loaded-code/function-binding integrity beyond the selected Runtime Code Integrity manifest;
- proof that already imported Python objects correspond to current disk bytes;
- authority-state integrity;
- hostile in-process tamper resistance;
- impossibility of deliberate monkeypatching by code with equivalent process authority;
- universal filesystem-object identity or attestation;
- universal shell-effect or external-child-process effect knowledge;
- a universal operating-system sandbox;
- universal third-party/service logger control;
- encrypted-at-rest secret custody redesign;
- distributed or cross-runtime consensus ledger/source authority;
- proof that already admitted external consequences physically ceased after later invalidation;
- comprehensive/independent Runtime Code Integrity Runtime Code Integrity attestation beyond the selected process-local implementation;
- Policy Integrity Authority State Integrity;
- Diagnostic Privacy Privacy/Telemetry Hardening.

Permanent Source Drift Protection nonclaim:

> **Source Drift Protection protects active-runtime source identity through bounded exact measurements. It does not provide continuous historical attestation, loaded-code/function-binding integrity, authority-state integrity, universal filesystem-object identity, or hostile in-process tamper resistance.**

## Governing doctrine

> Probabilistic cognition may propose, but deterministic software must dispose.

> Be strict about truth, identity, authority, and irreversible consequences; be resilient about useful work.

> Contain the violation at the narrowest boundary that preserves the security invariant.

> Do not destroy more state than the violation requires.

Source Drift Protection's frozen historical checkpoint remains intact. runtime-code research was exploratory research; Runtime Code Integrity selected enforcement is now implemented and target-qualified but still awaiting complete acceptance. Policy Integrity authority-state integrity remains a distinct unvalidated protection boundary.