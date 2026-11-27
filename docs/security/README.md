# Security Checkpoint Archive

This directory preserves the detailed validated security checkpoint records for Jack Kernel.

These files are historical engineering evidence. Each checkpoint records what had been implemented, validated, and explicitly unclaimed at that phase boundary.

## Current checkpoint

For present repository truth, read [`../../CURRENT_SECURITY_STATUS.md`](../../CURRENT_SECURITY_STATUS.md).

Current validated security checkpoint:

- **Source Drift Protection**
- status: **VALIDATED / MERGED / DOCUMENTED / TAGGED / FROZEN**
- implementation merged through PR #41
- Phase-8F closure merge / PR #42: `cebe9fd75fe30a9c84a0af08d2105af448fc3d00`
- validated closure tree: `7288396653db3590834d9ac1093207c4e1b19c3b`
- closure-complete Windows CI #218: **PASS**
- annotated validation tag: `security-layer-phase8-validated-2026-10-06`
- annotated tag object: `20e35610444f409bbccd62a461e42e2dce06ac6a`
- peeled tag target: `cebe9fd75fe30a9c84a0af08d2105af448fc3d00`
- tag state: unsigned annotated tag
- Phase 9A: **EXPERIMENTAL RESEARCH CLOSED; NO SECURITY VALIDATION / NO ENFORCEMENT**. Annotated research milestone: `security-layer-phase9a-research-closed-2026-10-14` (target: `5e909494eb354c45907bb15c9a621980f99b2263`).

The accepted Phase-8E candidate tree and integrated implementation tree are identical:

`93771e59ab7f9213d438bc56dbe434961b07c0f4`

## Runtime Code Integrity — Current implemented layer (2026-11-25)

Runtime Code Integrity adds **mandatory selected runtime executable-identity enforcement** in the actual secured `--serve` process, composed after Source Drift Protection source authority. There is **no runtime toggle**. This implementation was **merged to `main` through [PR #173](https://github.com/mlangford75-lgtm/Jack-Kernel/pull/173)** at merge commit `6565e08b2e4bd114725b8edea6987880498f3087` (2026-11-25). The new layer checks selected executable bindings, code constants/delegates, modules, and FastAPI dispatch plus actual consequential release/admission boundaries. The host retains narrowly scoped containment only when dependencies have been established; shared security-control corruption withholds dependent public authority.

**Validation classification:** Implemented and **target-qualified**, but **not formally complete / frozen / tagged**. The latest isolated Windows 3.14.6 run [45606058846](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/45606058846) on commit `563d02f682a5213ea7962263477b717e30a152ff` passed **98 targeted tests**, including a real secured-child live HTTP executable-substitution attack. The injected model and shared authentication replacements were blocked before execution. The pre-existing general Coder regression remains unresolved and comprehensive Pi/Windows security closure is not established.

**Current-phase evidence (not historical frozen checkpoints):**

- [Runtime Code Integrity-A live authority map](PHASE9B_A_CURRENT_RUNTIME_AUTHORITY_MAP_2026-11-25.md)
- [Runtime Code Integrity-B executable identity measurement](PHASE9B_B_EXPERIMENTAL_IDENTITY_QUALIFICATION_2026-11-25.md)
- [Runtime Code Integrity-C guarded release](PHASE9B_C_EXPERIMENTAL_ENFORCEMENT_QUALIFICATION_2026-11-25.md)
- [Security dependency / containment audit](PHASE9B_DEPENDENCY_CONTAINMENT_REVIEW_2026-11-25.md)

**Limits:** selected process-local identity monitoring is not independent in-process or remote attestation, complete protection from arbitrary same-interpreter mutation, physical side-effect cancellation, or a general OS sandbox. Backend streaming, actual worker/tool effects, performance and complete Windows/Pi regressions remain future release evidence. See [current security status](../../CURRENT_SECURITY_STATUS.md) for the authoritative latest classification.

## Preserved checkpoint records

- [`SECURITY_LAYER_PHASE0_3_VALIDATED_2026-09-27.md`](SECURITY_LAYER_PHASE0_3_VALIDATED_2026-09-27.md)
- [`SECURITY_LAYER_PHASE4_VALIDATED_2026-09-30.md`](SECURITY_LAYER_PHASE4_VALIDATED_2026-09-30.md)
- [`SECURITY_LAYER_PHASE5_VALIDATED_2026-10-01.md`](SECURITY_LAYER_PHASE5_VALIDATED_2026-10-01.md)
- [`SECURITY_LAYER_PHASE6_VALIDATED_2026-10-02.md`](SECURITY_LAYER_PHASE6_VALIDATED_2026-10-02.md)
- [`SECURITY_LAYER_PHASE7_VALIDATED_2026-10-05.md`](SECURITY_LAYER_PHASE7_VALIDATED_2026-10-05.md)
- [`SECURITY_LAYER_PHASE8_VALIDATED_2026-10-06.md`](SECURITY_LAYER_PHASE8_VALIDATED_2026-10-06.md)

Separate, **non-validated research** checkpoint:

- [`SECURITY_LAYER_PHASE9A_RESEARCH_CHECKPOINT_2026-10-14.md`](SECURITY_LAYER_PHASE9A_RESEARCH_CHECKPOINT_2026-10-14.md) — evidence and unresolved limitations; no production integrity guard.

## Source Drift Protection reading rule

Permanent containment statement:

> **Source-authority loss withdraws new Kernel-authoritative admission. It does not imply process death, blanket cancellation, invented worker failure, erasure of completed cognition, or loss of safe observation.**

Permanent semantic execution boundary:

> **Source Drift Protection serializes Kernel-authoritative admission, not physical continuous-world execution after an admission already occurred.**

Permanent nonclaim:

> **Phase 8 protects active-runtime source identity through bounded exact measurements. It does not provide continuous historical attestation, loaded-code/function-binding integrity, authority-state integrity, universal filesystem-object identity, or hostile in-process tamper resistance.**

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

## Historical-reading rule

Do not retroactively rewrite an older checkpoint merely because later implementation exists.

Examples:

- a Phase-0–3 record may correctly state that Restricted Paths were not yet implemented;
- a Restricted Paths / Workspace Lock record may correctly state that the Consequence Gate was not yet implemented;
- a Consequence Gate record may correctly state that Authority & Security Ledger had not started;
- a Authority & Security Ledger record may preserve pre-tag closure-candidate language because it was authored before final Authority & Security Ledger annotated-tag creation;
- the Credential Isolation and DLP closure record may preserve pre-tag process wording from before the final Credential Isolation and DLP annotated tag existed.

Those statements are evidence of the exact state at the time. They do not supersede the canonical current-state document.

The Phase-8 closure record has been reconciled after independent tag verification and is the authoritative Phase-8 frozen checkpoint record.

## Related governing documents

The Security Hardening Architecture and cumulative governing amendments are under [`../../Documentation/Security/`](../../Documentation/Security/).
