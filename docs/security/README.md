# Security Checkpoint Archive

This directory preserves the detailed validated security checkpoint records for Jack Kernel.

These files are historical engineering evidence. Each checkpoint records what had been implemented, validated, and explicitly unclaimed at that phase boundary.

## Current checkpoint

For present repository truth, read [`../../CURRENT_SECURITY_STATUS.md`](../../CURRENT_SECURITY_STATUS.md).

Current validated checkpoint:

- **Phase 6 — Runtime-Scoped Authority & Security Ledger**
- tag: `security-layer-phase6-validated-2026-10-02`
- tag object: `1e46b9872db66cc3944b79550aa30509b4c84296`
- target: `51e29b197ab62db410e6b4b43c92688ba613826f`

Phase 6 is validated, merged, documented, tagged, and frozen.

## Preserved checkpoint records

- [`SECURITY_LAYER_PHASE0_3_VALIDATED_2026-09-27.md`](SECURITY_LAYER_PHASE0_3_VALIDATED_2026-09-27.md)
- [`SECURITY_LAYER_PHASE4_VALIDATED_2026-09-30.md`](SECURITY_LAYER_PHASE4_VALIDATED_2026-09-30.md)
- [`SECURITY_LAYER_PHASE5_VALIDATED_2026-10-01.md`](SECURITY_LAYER_PHASE5_VALIDATED_2026-10-01.md)
- [`SECURITY_LAYER_PHASE6_VALIDATED_2026-10-02.md`](SECURITY_LAYER_PHASE6_VALIDATED_2026-10-02.md)

## Historical-reading rule

Do not retroactively rewrite an older checkpoint merely because later implementation exists.

Examples:

- a Phase-0–3 record may correctly state that Restricted Paths were not yet implemented;
- a Phase-4 record may correctly state that the Consequence Gate was not yet implemented;
- a Phase-5 record may correctly state that Phase 6 had not started;
- the Phase-6 record may preserve pre-tag closure-candidate language because it was authored before final annotated-tag creation.

Those statements are evidence of the exact state at the time. They do not supersede the canonical current-state document.

## Related governing documents

The Security Hardening Architecture and cumulative governing amendments are under [`../../Documentation/Security/`](../../Documentation/Security/).
