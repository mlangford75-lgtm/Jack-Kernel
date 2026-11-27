# Security Documentation

Jack Kernel's security documentation is cumulative. Current implementation truth and historical checkpoint evidence are intentionally separated so earlier validation records remain intact while users can still identify the present runtime state immediately.

## Current validated security state

Start with [`../../CURRENT_SECURITY_STATUS.md`](../../CURRENT_SECURITY_STATUS.md).

Current checkpoint:

- **Source Drift Protection**
- validated tag: `security-layer-phase8-validated-2026-10-06`
- annotated tag object: `20e35610444f409bbccd62a461e42e2dce06ac6a`
- validated closure target: `cebe9fd75fe30a9c84a0af08d2105af448fc3d00`
- validated closure tree: `7288396653db3590834d9ac1093207c4e1b19c3b`
- closure-complete Windows CI #218: **PASS**
- status: **VALIDATED / MERGED / DOCUMENTED / TAGGED / FROZEN**
- tag state: **unsigned annotated tag**

Historical post-Source Drift Protection status-publication checkpoint (not the current `main` branch identity):

- historical publication commit: `7e00f7209ccb168387da2bbd2fd2344e57c2f82d`
- historical publication tree: `cde43597139637a461c04d446d7d165dea1fa46b`
- post-freeze Windows CI #220: **PASS**

Later merged maintenance includes PR #45 (Agentic tool-resume correction), PR #46 (Responses error non-disclosure), and PR #47 (runtime-code research checkpoint). The documented October 14 post-fix runtime baseline at `ef613e46e70181f7fa8d054aabc3b5a744d8f704` passed 527 Windows Python tests. For current branch identity, inspect GitHub `main` rather than treating a dated checkpoint SHA as perpetually current.

The immutable Source Drift Protection tag remains pinned to the CI-validated closure commit above. The historical post-freeze publication commit documented above did not move the tag or redefine Source Drift Protection runtime behavior.

**runtime-code research: RESEARCH CLOSED (not a validated security checkpoint).** At that historical research checkpoint, Runtime Code Integrity enforcement had not been implemented or merged. The [separate runtime-code research checkpoint](../../docs/security/SECURITY_LAYER_PHASE9A_RESEARCH_CHECKPOINT_2026-10-14.md) records experiments, limitations, and unresolved differences. Source Drift Protection remains the last fully validated/frozen checkpoint.

## Governing security architecture

[`Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md`](Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md) preserves the complete hardening design and its dated implementation-status updates.

Status notes inside that paper describe the repository at the dates printed in those notes. They are historical implementation records, not the current repository checkpoint. Use `CURRENT_SECURITY_STATUS.md` for present truth.

## Cumulative governing amendments

The formal governing-amendment series currently preserved in this directory is:

- [`GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASES_0_3_2026-09-27.md`](GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASES_0_3_2026-09-27.md)
- [`GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_4_2026-09-30.md`](GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_4_2026-09-30.md)
- [`GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_5_2026-10-01.md`](GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_5_2026-10-01.md)
- [`GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_6_2026-10-02.md`](GOVERNING_DOCUMENT_SECURITY_AMENDMENT_PHASE_6_2026-10-02.md)

These amendments preserve the state and claims accepted at their respective phase boundaries. The formal amendment-file series stops at Authority & Security Ledger; this does **not** mean later validated phases are absent or provisional. Current validated Credential Isolation and DLP and Source Drift Protection implementation truth is recorded in `CURRENT_SECURITY_STATUS.md` and the exact validated closure records under `docs/security/`.

Older governing papers and amendments are not silently rewritten merely because later implementation exists.

## Detailed checkpoint archive

Exact phase validation records, implementation identities, regression counts, and nonclaims are preserved under [`../../docs/security/`](../../docs/security/).

The archive contains:

- Phases 0–3 validated checkpoint
- Restricted Paths / Workspace Lock validated checkpoint
- Consequence Gate validated checkpoint
- Authority & Security Ledger validated checkpoint / closure record
- Credential Isolation and DLP validated closure record
- Source Drift Protection validated frozen closure record
- runtime-code research experimental research-closure record (not security validation)

Current Source Drift Protection closure record:

- [`../../docs/security/SECURITY_LAYER_PHASE8_VALIDATED_2026-10-06.md`](../../docs/security/SECURITY_LAYER_PHASE8_VALIDATED_2026-10-06.md)

The Credential Isolation and DLP detailed closure record preserves pre-tag process wording from before the final Credential Isolation and DLP annotated tag existed. That wording is historical process-state evidence, not current repository status.

The Source Drift Protection detailed closure record has been reconciled after independent annotated-tag verification and is the authoritative frozen Source Drift Protection checkpoint record.

## Governing interpretation

Current security behavior must be interpreted cumulatively:

- Phases 0–3 own the validated release-boundary security substrate and Canary behavior;
- Restricted Paths / Workspace Lock owns represented-path fact production and path-policy semantics;
- Consequence Gate owns deterministic consequence disposition;
- Authority & Security Ledger owns the process-local authority/security chain and bounded forensic projection semantics;
- Credential Isolation and DLP adds closed known-credential authority, exact model ingress/egress DLP, orchestration and diagnostic release protection, exact credential-resource containment, and safe Credential Isolation and DLP observations in the existing Authority & Security Ledger chain;
- Source Drift Protection adds bounded active-runtime source authority: immutable protected-source baseline, exact bounded remeasurement, `ACTIVE` / `SUSPENDED_UNVERIFIED` / `INVALIDATED` lifecycle, preservation-aware runtime enforcement, fail-soft lifecycle observation, concurrency-safe forensic ordering, and adversarial anti-brittleness closure.

Permanent Source Drift Protection preservation statement:

> **Source-authority loss withdraws new Kernel-authoritative admission. It does not imply process death, blanket cancellation, invented worker failure, erasure of completed cognition, or loss of safe observation.**

Permanent Source Drift Protection execution boundary:

> **Source Drift Protection serializes Kernel-authoritative admission, not physical continuous-world execution after an admission already occurred.**

Permanent Source Drift Protection nonclaim:

> **Source Drift Protection protects active-runtime source identity through bounded exact measurements. It does not provide continuous historical attestation, loaded-code/function-binding integrity, authority-state integrity, universal filesystem-object identity, or hostile in-process tamper resistance.**

The runtime-code research checkpoint is historical. Consult the current security status and independent audit register for the later implementation and qualification of Runtime Code Integrity, Policy Integrity and Diagnostic Privacy.
