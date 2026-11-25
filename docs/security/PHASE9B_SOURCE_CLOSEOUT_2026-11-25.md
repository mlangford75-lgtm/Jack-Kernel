# Phase 9B source identity close-out — experimental security evidence

**Date:** 2026-11-25
**Branch:** `security/phase9b-source-closure-20261125`
**Draft PR:** [#176](https://github.com/mlangford75-lgtm/Jack-Kernel/pull/176)
**Successful Windows run:** [45619814751](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/45619814751)
**Candidate SHA validated:** `a7d6bf0f4935f931bb9b842460d7f3d09dadc4ed`
**Status:** target-qualified source-integrity increment, not full Phase 9 final acceptance

## Gap and narrow remedy

The validated and frozen historical Phase 8 source manifest was established before the new `jack_runtime_code_guard.py` and `jack_phase9b_enforcement.py` files existed. Loaded executable function-identity checks cannot alone detect later source-disk edits that do not change already imported bytecode. Phase 9B now explicitly measures its **two new source files** using the existing Phase 8 exact regular-file measurement primitive and seals their canonical paths and byte SHA-256 values into **shared Phase 9B authority**. This does not mutate Phase 8's validated source modules or rewrite its historical checkpoint.

A post-start change in bytes, disappearance of a file, or substitution of an expected regular file with a different kind of filesystem object is a confirmed integrity mismatch. Required source read failure is classified as measurement unavailable, not automatically proven attacker tampering; new dependent public authority is withheld and can only recover by exact trustworthy re-verification. A confirmed mismatch remains terminal for that process even if file bytes are later restored.

## Windows tests and real startup qualification

At the source candidate SHA, all dedicated tests passed under pinned Windows Python 3.14.6:

- **63 passed**: Phase 9B identity, effective Phase 8 wrappers, integrated ASGI admission/release, source-change and missing/kind/uncertainty tests
- **3 passed**: fresh-process real Jack Kernel + Phase 8/Phase 9B protected dispatch
- **1 passed**: actual mandatory secured `jack_secure_entrypoint.py --serve` HTTP startup, warm middleware lifecycle
- **1 passed**: actual secured-child post-start malicious executable replacement and blocked HTTP consequence
- **1 passed**: comparative source-verification timing evidence
- **39 passed**: unchanged Phase 8 source integrity and adversarial preservation
- **108 passed total** across the dedicated qualification stages (existing third-party deprecation warnings remain)

The broader mainline workflow still fails the legacy Coder compatibility suite; this is a pre-existing full-regression blocker and is not concealed or reclassified as a passing full suite.

## Measured per-verification overhead

The [same Windows run](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/45619814751) compared 200 baseline checks with 200 checks registering both Phase 9B source files, after a 10-sample warm-up.

| Metric | Observed, Windows hosted runner |
|---|---:|
| Baseline selected-code verification, median | 0.02840 ms |
| Selected-code + two source files, median | 1.35015 ms |
| Combined verification p95 | 1.43370 ms |
| Incremental median source-check cost | **1.32175 ms** |

These are benchmark observations, not global production latency claims or security success thresholds. At high SSE event rates, repeatedly hashing source bytes may impose meaningful CPU/latency cost. Do not omit a necessary security measurement merely to optimize a benchmark; future performance work must preserve the same consequence-boundary guarantee, or explicitly document any weaker check cadence and its attack window. CPU/IO concurrency and real model workloads remain unmeasured.

## Security guarantees and limitations

The added source checks prevent new protected HTTP release after a confirmed change to either newly authoritative Phase 9B source file, as far as the in-process verifier remains trusted and the guarded ingress/release path is invoked. They do not establish immutable filesystem objects between checks, continuous historical attestation, protection from arbitrary same-process interpreter code that rewrites the verifier itself, or complete external tool/worker side-effect attestation. The existing selected loaded-code checks and their ASGI/host-release boundaries remain intact.

**Open release work:** full current Coder/Pi regression reconciliation, real external tool-consequence attack tests, long-running SSE and concurrent mutation/cancellation, explicit TOCTOU review and throughput measurement. The present PR is an isolated security change with targeted validation; formal full Phase 9 closure/tagging is not claimed.
