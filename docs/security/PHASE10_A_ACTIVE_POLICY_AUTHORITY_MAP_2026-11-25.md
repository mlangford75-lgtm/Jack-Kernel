# Phase 10-A — Active Security-Policy Authority Inventory and Implementation Gates

**Date:** 2026-11-25
**Status:** source-grounded design and scoped implementation inventory; **no Phase 10 policy enforcement active**.
**Initial main baseline:** \`9a03b011c963443d892474c640821b2b00005f9f\`.
**Branch:** \`security/phase10-authority-policy-integrity-20261125\`.
**Governing requirements:** \`Documentation/Security/Jack_Kernel_Security_Hardening_Architecture_2026-09-26.md\`, §§23A–23E, 36A–36B and Phase 10 build order.
**Predecessors:** Phase 8 source integrity (validated, frozen); Phase 9B selected runtime executable integrity (merged, targeted qualification, full regression pending).
**Boundary:** Never mistake static policy *data* for loaded code, a forensic record for authority, or independently scoped process state for shared cross-process consensus.

## Problem and acceptance

An unchanged, apparently healthy authorization function can admit an unauthorized consequence if it consumes a silently substituted or weakened active policy object. Phase 10 must establish **what the actual consumer reads**, pin that active object identity, deterministically measure behavior-bearing policy fields without exposing secrets, and block relevant consequences when those fields or the active reference are replaced. A frozen dataclass prevents ordinary assignment to its attributes but does not prevent replacing a module/host binding to another equally immutable object.

Do **not** copy all transient task/run/ledger state into a global frozen structure or introduce blanket hard interrupts for any state change. Static policy and legitimately dynamic state have different ownership, update and concurrency contracts. Only a demonstrated authority-bearing policy field merits mandatory measurement.

## Inventory of actual currently deployed producers, consumers and ownership

| Authority object and source | Active producer/holder | Consumers and concrete authorization boundary | Mutability and scope | Phase 10 disposition |
|---|---|---|---|---|
| \`RuntimePathPolicy\`, \`jack_path_policy.py:194+\` | \`jack_kernel._bind_runtime_path_policy()\` sets \`jk._RUNTIME_PATH_POLICY\` once at startup (\`jack_kernel.py:444–476\`); source environment copied into a canonical tuple | \`jk._runtime_path_policy()\`, Phase 4 structured tool partition (\`jack_kernel.py:5115+\`) and executor admission, Phase 5 consequence wrapper | Static, deeply tuple/frozen; runtime/lane | **P0**: pin effective module holder object and measured policy fields; authorize only if actual current consumer sees same object; do not rewrite existing deep-frozen construction |
| \`RuntimeCanaryPolicy\`, \`jack_evidence_guard.py:274+\` | \`jack_kernel._install_bundled_runtime_extensions()\` builds static Tier A/B snapshot, merges Phase 7 credentials, passes to \`jack_evidence_guard.install()\` | Local closure \`canary_policy\` captured by the effective guarded \`KERNEL.run/stream\` and release helpers (\`jack_evidence_guard.py:1883+\`) | Static, frozen policy/tuple-backed canary set; runtime/lane, **closure not necessarily module-global** | **P0**: map and pin the precise active closure cell/delegate; avoid inventing a global holder. Digest only canary IDs, tiers and hashes of secret values, not raw secrets or repr() |
| \`RuntimeCredentialPolicy\`, \`jack_credential_guard.py:123+\` | \`jack_credential_guard.install()\` holds policy at \`jk._JACK_RUNTIME_CREDENTIAL_POLICY\` (\`jack_credential_guard.py:752+\`) and captures it in backend \`_client.post/build_request\` guarded transport closures | Model ingress, guarded backend requests, model egress and selected orchestration observer release; effective closure captured alongside holder | Static, frozen nested credential records and tuples; runtime/lane | **P0**: holder and real backend transport closures must agree; pin both rather than digesting a detached snapshot. Never expose values in logs, exceptions, or error payloads |
| Runtime identity and source baseline | \`jk.RUNTIME_ID\`, \`jk.LANE_ID\`; \`jk._JACK_SOURCE_AUTHORITY\` stores Phase 8 runtime-scoped sealed source manifest | Phase 8 protected source admission, runtime/ledger scope and security marker checks | Static runtime/lane; Phase 8 frozen authority | **P0 dependency**: bind Phase 10 baseline to exact runtime/lane and active Phase 8 instance; preserve independent Phase 8 semantics |
| Phase 9B runtime code guard | \`jk._JACK_RUNTIME_CODE_AUTHORITY\` installed automatically in secured child | Selected executor, HTTP, stream, Pi and tool-release checks | Static executable identity baseline plus invalidation state | **P0 dependency**: validate required Phase 9B active state before permitting Phase 10 installation. Do not silently downgrade or loop on already-invalidated authority |
| Phase 6 Authority Ledger | \`jk._JACK_AUTHORITY_LEDGER\`, \`jack_authority_ledger.py\` process-local lock and predecessor chain | Records established authority facts, status for selected security transitions | Dynamic ledger head/sequence **per runtime process** | **P1**, but ledger is not itself the origin of authority: preserve fail-soft durability, pre-authority internal state, and per-lane process isolation. No global compare-and-swap |
| Task/run/epoch lifecycle | Task contexts and Pi/Agentic orchestration; held in active lifecycle objects and controlled methods | Authorization facts for tool continuation, cancellation, run epoch, current active task | Legitimately dynamic, runtime/run; concurrency within one serving process | **Research classification** first; do not invent all-purpose mutable \`SecurityState\` or freeze ephemeral counters |
| Dynamic Tier C canaries, approvals and settlement | Architecture discusses controlled transitions, but an actual current authoritative producer must be demonstrated before adding any | When genuinely implemented: validated transition to new snapshot and ledger fact | Dynamic, runtime/run; process-local transition lock | **Deferred until actual active data/transition owner is identified**. Do not manufacture a security state producer to satisfy a design diagram |

## Proposed acceptance gates

**10A — Source and holder proof:** identify each named producer, effective holder, captured delegate and actual consumer; confirm mutability and cross-process ownership. Include trace of P0 tool release and Phase 7 backend transport. Do not claim all relevant security fields are represented by these three policies; continue coverage review.

**10B — Canonical measurement primitive, initially not activated:** versioned, deterministic schema with explicit field serialization, sorted sets, full tuple structure and scalar types, hash-based secret representation; pin active *object identity* plus owner scope. No arbitrary \`repr()\`, addresses, user-provided JSON keys not normalized, or validation via calling user-defined object methods. Reject unsupported policy schema or unmeasurable P0.

**10C — Actual authority installation, isolated branch only:** install after legitimate static policy construction and after Phase 8 and Phase 9B are stable, before protected public serving; verify before actual policy-dependent tool/executor, output release and credential/Canary backend boundaries. Prefer checking *the same policy instance actually read by the existing consumer*. Replacing a holder but not the closure should be detected as a conflicting policy identity, not an accepted transition.

**10D — Legitimate transition mechanism, only when evidenced:** define explicit owner and event contract, current predecessor and version, atomic process-local lock around transition, immutable successor, and narrowly scoped authority-withdrawal disposition. Preserve independent runtime lanes and already-settled consequences. An observer's inability to write a ledger entry must not invent a compromise.

**10E — Adversarial and positive tests:** holder replacement with permissive frozen policy, closure replacement with retained original holder, constant policy field weakening, changed NEVER root, dropped Canary/credential, unknown/opaque type, race/compare-and-swap with two process-local writers, safe unchanged model and tool flow, ordinary config/environment changes after sealing, legitimate dynamic successor, normal backend and Pi API. Verify an *actual blocked consequence*, not only a digest mismatch.

**10F — Close-out:** same-commit Windows Python 3.14.6 and Pi security/regression suite, targeted real secured-child attacks, concurrency and performance checks, exact diff review, updated current-status docs, and clear remaining nonclaims before any merge/tag.

## No-brittleness versus real security

- Confirmed corruption of a common authorization policy must block every consequence depending on it, including ostensibly read-only routes that in fact invoke compromised transport or authorization delegates.
- A model output failure does not automatically prove unrelated closed executor or independent runtime policy corruption.
- Measurement temporarily unavailable means prohibit **new affected consequences** until exact trustworthy re-verification; it does not magically establish an attacker or justify blanketing all other lanes.
- Recoverable tool/programming errors must not invalidate unchanged policy identity.
- All policy integrity claims are limited to actual consumers, verified scope boundaries and the stated in-process attacker model. No pure-Python checker independently attests itself against arbitrary equal-privilege interpreter rewrite.

## Release prerequisites and known blockers

**Current GitHub main CI** first fails a Phase 5 secure-entrypoint startup-ordering test whose Phase 8 monkeypatch does not account for mandatory Phase 9B; a separate experimental correction is in PR #174. The Nov 24 Coder compatibility suite also had 24 fails/24 passes; no claim of complete current \`main\` regression validation is permitted until resolved. **No Phase 10 source enforcement should merge while those regressions remain unresolved.**

Phase 8 frozen source guard does not automatically include the new Phase 9B modules as protected source. Resolve that gap as a Phase 9 security close-out, not by silently rewriting the Phase 8 historical record. Do not conflate a code fingerprint with the integrity of active policy data.

**Disposition: Phase 10-A source inventory created, no implementation release.**
