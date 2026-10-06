# Security Checkpoint Archive

This directory preserves the detailed validated security checkpoint records for Jack Kernel.

These files are historical engineering evidence. Each checkpoint records what had been implemented, validated, and explicitly unclaimed at that phase boundary.

## Current checkpoint

For present repository truth, read [`../../CURRENT_SECURITY_STATUS.md`](../../CURRENT_SECURITY_STATUS.md).

Current validated implementation checkpoint:

- **Phase 8 — Active Source Authority / Source Drift Protection**
- implementation merged through PR #41
- integrated implementation commit: `90077f157183f442bb1d41eb23af865fab94ea43`
- integrated implementation tree: `93771e59ab7f9213d438bc56dbe434961b07c0f4`
- Phase 8F closure/tag/freeze: in progress
- Phase 9: not started

The accepted Phase-8E candidate tree and the integrated implementation tree are identical. The annotated Phase-8 validation tag is intentionally not recorded here until it exists and has been independently verified.

## Preserved checkpoint records

- [`SECURITY_LAYER_PHASE0_3_VALIDATED_2026-09-27.md`](SECURITY_LAYER_PHASE0_3_VALIDATED_2026-09-27.md)
- [`SECURITY_LAYER_PHASE4_VALIDATED_2026-09-30.md`](SECURITY_LAYER_PHASE4_VALIDATED_2026-09-30.md)
- [`SECURITY_LAYER_PHASE5_VALIDATED_2026-10-01.md`](SECURITY_LAYER_PHASE5_VALIDATED_2026-10-01.md)
- [`SECURITY_LAYER_PHASE6_VALIDATED_2026-10-02.md`](SECURITY_LAYER_PHASE6_VALIDATED_2026-10-02.md)
- [`SECURITY_LAYER_PHASE7_VALIDATED_2026-10-05.md`](SECURITY_LAYER_PHASE7_VALIDATED_2026-10-05.md)
- [`SECURITY_LAYER_PHASE8_VALIDATED_2026-10-06.md`](SECURITY_LAYER_PHASE8_VALIDATED_2026-10-06.md)

## Phase-8 reading rule

The permanent Phase-8 containment statement is:

> **Source-authority loss withdraws new Kernel-authoritative admission. It does not imply process death, blanket cancellation, invented worker failure, erasure of completed cognition, or loss of safe observation.**

The permanent Phase-8 nonclaim is:

> **Phase 8 protects active-runtime source identity through bounded exact measurements. It does not provide continuous historical attestation, loaded-code/function-binding integrity, authority-state integrity, universal filesystem-object identity, or hostile in-process tamper resistance.**

Phase 8 also preserves:

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
- the Phase-7 closure record may preserve pre-tag freeze language because it was authored before the final Phase-7 annotated tag existed;
- the Phase-8 closure record may preserve staged Phase-8F wording from before the final annotated Phase-8 tag existed.

Those statements are evidence of the exact state at the time. They do not supersede the canonical current-state document.

## Related governing documents

The Security Hardening Architecture and cumulative governing amendments are under [`../../Documentation/Security/`](../../Documentation/Security/).
