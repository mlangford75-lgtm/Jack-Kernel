# Independent audit remediation register

Baseline: 9a6fe53d02c890698724929486365f0803cc775f
Reviewed branch head before this change: fd53d7bae30d67fbf452f6921815a2e271ceb7e0
Draft PR: #179. Main is not a target. No item is closed solely on static analysis.

| Finding | Disposition at this revision | Required acceptance evidence |
|---|---|---|
| M-1 | Partial; message-scanned cleanup remains | Exact owner, queued cancellation, terminal retirement, normal recovery, both APIs |
| M-2 | Partial; malformed/EOF tests present; Phase 7 safe-prefix failure inherited per handoff | Logical SSE reconstruction; hard stops and benign completion |
| M-3 | Candidate patch present | Structured and command Windows ADS tests |
| M-4 | Candidate patch integrates operation-aware default Windows read facts into shared gate; live ledger regression cases added | Read exemption through shared gate and ledgers |
| M-5 | Typed terminal failure patch present | End-to-end no model retry |
| M-6 | Candidate patch present | Mixed authorized/invalid sibling release |
| M-7 | Pi cancellation patch and harness; independent Pi CI passed | Retain physical settlement |
| M-8 | Provider refresh serialization; Pi CI passed | Concurrent refresh, mismatch fail-closed |
| M-9 | Open; recursive history copies confirmed | Retry checkpoints retained in pending state and Stage 2 without restoring retired history |
| M-10 | Partial terminal classification; public parity not qualified | Both APIs, buffered/streamed canonical security disposition |
| M-11 | Candidate translation peak-context patch and deterministic tests in this revision | Windows regression and actual Pi usage, aggregate remains separate |
| M-12 | Existing app_lifespan closes ledger through asyncio.to_thread | Lifespan drain and shutdown failure qualification |
| M-13 | Partial; report atomicity, Responses indexes, SQLite DDL changes present | CLI defaults, run retirement, SSE roles and concurrency |
| P-1 | Open; benchmark before redesign | Secured per-chunk runtime-integrity overhead; preserve check timing |
| P-2 | Open; benchmark before redesign | Coder 3-turn backend prefill/cache evidence |
| P-3 | Open; benchmark before redesign | 64/128 KiB serialization and event-loop/RSS measurement |
| P-4 | Open | Registry lifecycle and buffer measurements |
| C-1 | Maintainer scope decision | Secret-header identification without false positives |
| C-2 | Maintainer scope decision | Evidence endpoint disclosure and integrity coverage |
| C-3 | Maintainer scope decision | Worker-event quarantine and replay semantics |
| C-4 | Maintainer scope decision | Represented path coverage without claiming OS sandbox |
| C-5 | Maintainer scope decision | Secured operational entrypoint and test escape hatch |
| C-6 | Maintainer scope decision | Demonstrated authority-bearing dependency inventory |
| CL-1 | Open | Dependency proof and regression before dead code removal |
| CL-2 | Open | Request-builder equivalence |
| CL-3 | Open | Current tool-free Architect documentation, verified artifact cleanup |
| V-1 | Maintainer decision | Frozen A1 on Stage 2 budget failure |
| V-2 | Open | Transaction link/memory accounting regression |
| V-3 | Open | Strict-provider fixtures, model switching, missing env resolution |
| V-4 | Maintainer decision | Responses instructions authority |
| V-5 | Maintainer decision | Credential/Canary collision, strictest threshold |
| V-6 | No retirement authorized | Explicit approval and compatibility proof |

## CI evidence

Head fd53d7bae30d67fbf452f6921815a2e271ceb7e0: independent Pi bridge and tool-free Coder qualification passed. Combined security run 45828252442 failed at Phase 7 safe-prefix preservation; full Windows run 45828253229 failed Phase 7 and regression. Compared deduplicated FAILED test identities in full workflow jobs 139932539338 and 139937935086: earlier candidate 221, current 220; only removed identity is tests/test_retro_phase0_2_validation.py::test_phase2_malformed_frame_preserves_prior_safe_quarantine_tail; no added identities. This comparison is not the exact main baseline differential. Inherited failures require baseline verification. No Windows live inference or performance measurements performed in this session.

## Non-negotiables

No main merge, no disabled tests, no change to cognitive prompts or Canary threshold. Preserve deterministic authority, safe output, authorized siblings, active reasoning, deliberate historical retirement, role separation, cache semantics and physical settlement. Scope decisions remain distinct from routine implementation. All candidate fixes require qualification.
