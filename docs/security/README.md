# Security Checkpoint Archive

This directory preserves the detailed validated security checkpoint records for Jack Kernel.

These files are historical engineering evidence. Each checkpoint records what had been implemented, validated, and explicitly unclaimed at that phase boundary.

## Current checkpoint

For present repository truth, read [`../../CURRENT_SECURITY_STATUS.md`](../../CURRENT_SECURITY_STATUS.md).

Current validated security checkpoint:

- **Phase 8 — Active Source Authority / Source Drift Protection**
- status: **VALIDATED / MERGED / DOCUMENTED / TAGGED / FROZEN**
- implementation merged through PR #41
- Phase-8F closure merge / PR #42: `cebe9fd75fe30a9c84a0af08d2105af448fc3d00`
- validated closure tree: `7288396653db3590834d9ac1093207c4e1b19c3b`
- closure-complete Windows CI #218: **PASS**
- annotated validation tag: `security-layer-phase8-validated-2026-10-06`
- annotated tag object: `20e35610444f409bbccd62a461e42e2dce06ac6a`
- peeled tag target: `cebe9fd75fe30a9c84a0af08d2105af448fc3d00`
- tag state: unsigned annotated tag
- Phase 9: **NOT STARTED**

The accepted Phase-8E candidate tree and integrated implementation tree are identical:

`93771e59ab7f9213d438bc56dbe434961b07c0f4`

## Preserved checkpoint records

- [`SECURITY_LAYER_PHASE0_3_VALIDATED_2026-09-27.md`](SECURITY_LAYER_PHASE0_3_VALIDATED_2026-09-27.md)
- [`SECURITY_LAYER_PHASE4_VALIDATED_2026-09-30.md`](SECURITY_LAYER_PHASE4_VALIDATED_2026-09-30.md)
- [`SECURITY_LAYER_PHASE5_VALIDATED_2026-10-01.md`](SECURITY_LAYER_PHASE5_VALIDATED_2026-10-01.md)
- [`SECURITY_LAYER_PHASE6_VALIDATED_2026-10-02.md`](SECURITY_LAYER_PHASE6_VALIDATED_2026-10-02.md)
- [`SECURITY_LAYER_PHASE7_VALIDATED_2026-10-05.md`](SECURITY_LAYER_PHASE7_VALIDATED_2026-10-05.md)
- [`SECURITY_LAYER_PHASE8_VALIDATED_2026-10-06.md`](SECURITY_LAYER_PHASE8_VALIDATED_2026-10-06.md)

## Phase-8 reading rule

Permanent containment statement:

> **Source-authority loss withdraws new Kernel-authoritative admission. It does not imply process death, blanket cancellation, invented worker failure, erasure of completed cognition, or loss of safe observation.**

Permanent semantic execution boundary:

> **Phase 8 serializes Kernel-authoritative admission, not physical continuous-world execution after an admission already occurred.**

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
!= Phase-10 integrity protection

ordering-buffer health
!= source-enforcement health
```

## Historical-reading rule

Do not retroactively rewrite an older checkpoint merely because later implementation exists.

Examples:

- a Phase-0–3 record may correctly state that Restricted Paths were not yet implemented;
- a Phase-4 record may correctly state that the Consequence Gate was not yet implemented;
- a Phase-5 record may correctly state that Phase 6 had not started;
- a Phase-6 record may preserve pre-tag closure-candidate language because it was authored before final Phase-6 annotated-tag creation;
- the Phase-7 closure record may preserve pre-tag process wording from before the final Phase-7 annotated tag existed.

Those statements are evidence of the exact state at the time. They do not supersede the canonical current-state document.

The Phase-8 closure record has been reconciled after independent tag verification and is the authoritative Phase-8 frozen checkpoint record.

## Related governing documents

The Security Hardening Architecture and cumulative governing amendments are under [`../../Documentation/Security/`](../../Documentation/Security/).
