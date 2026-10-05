# Security Checkpoint Archive

This directory preserves the detailed validated security checkpoint records for Jack Kernel.

These files are historical engineering evidence. Each checkpoint records what had been implemented, validated, and explicitly unclaimed at that phase boundary.

## Current checkpoint

For present repository truth, read [`../../CURRENT_SECURITY_STATUS.md`](../../CURRENT_SECURITY_STATUS.md).

Current validated checkpoint:

- **Phase 7 — Credential Isolation and Integrated DLP**
- tag: `security-layer-phase7-validated-2026-10-05`
- tag object: `ffde3865178ac14c44d6222a39e0e59e6d8518a9`
- target: `59aef730e11031b23f67c735e35f1e68c9ecc394`

Phase 7 is validated, merged, documented, tagged, and frozen.

## Preserved checkpoint records

- [`SECURITY_LAYER_PHASE0_3_VALIDATED_2026-09-27.md`](SECURITY_LAYER_PHASE0_3_VALIDATED_2026-09-27.md)
- [`SECURITY_LAYER_PHASE4_VALIDATED_2026-09-30.md`](SECURITY_LAYER_PHASE4_VALIDATED_2026-09-30.md)
- [`SECURITY_LAYER_PHASE5_VALIDATED_2026-10-01.md`](SECURITY_LAYER_PHASE5_VALIDATED_2026-10-01.md)
- [`SECURITY_LAYER_PHASE6_VALIDATED_2026-10-02.md`](SECURITY_LAYER_PHASE6_VALIDATED_2026-10-02.md)
- [`SECURITY_LAYER_PHASE7_VALIDATED_2026-10-05.md`](SECURITY_LAYER_PHASE7_VALIDATED_2026-10-05.md)

## Historical-reading rule

Do not retroactively rewrite an older checkpoint merely because later implementation exists.

Examples:

- a Phase-0–3 record may correctly state that Restricted Paths were not yet implemented;
- a Phase-4 record may correctly state that the Consequence Gate was not yet implemented;
- a Phase-5 record may correctly state that Phase 6 had not started;
- a Phase-6 record may preserve pre-tag closure-candidate language because it was authored before final Phase-6 annotated-tag creation;
- the Phase-7 closure record may preserve pre-tag freeze language because it was authored before the final Phase-7 annotated tag existed.

Those statements are evidence of the exact state at the time. They do not supersede the canonical current-state document.

## Related governing documents

The Security Hardening Architecture and cumulative governing amendments are under [`../../Documentation/Security/`](../../Documentation/Security/).
