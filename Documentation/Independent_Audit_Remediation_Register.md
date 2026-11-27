# Independent audit remediation register

Baseline: 9a6fe53d02c890698724929486365f0803cc775f
Reviewed branch head before this change: fd53d7bae30d67fbf452f6921815a2e271ceb7e0
Draft PR: #179. Main is not a target. No item is closed solely on static analysis.

| Finding | Disposition at this revision | Required acceptance evidence |
|---|---|---|
| M-1 | Core ownership candidate: exact acquired checkpoint, settlement under semaphore, adapters no longer scan messages; outer release-barrier terminal propagation still needs qualification | Exact owner, queued cancellation, terminal retirement, normal recovery, both APIs |
| M-2 | Partial; malformed/EOF tests present; Phase 7 safe-prefix failure inherited per handoff | Logical SSE reconstruction; hard stops and benign completion |
| M-3 | Candidate patch present | Structured and command Windows ADS tests |
| M-4 | Candidate patch integrates operation-aware default Windows read facts into shared gate; live ledger regression cases added | Read exemption through shared gate and ledgers |
| M-5 | Typed terminal failure patch present | End-to-end no model retry |
| M-6 | Candidate patch present | Mixed authorized/invalid sibling release |
| M-7 | Pi cancellation patch and harness; independent Pi CI passed | Retain physical settlement |
| M-8 | Provider refresh serialization; Pi CI passed | Concurrent refresh, mismatch fail-closed |
| M-9 | Candidate patch retains recovered stage history and host rejection events; four deterministic tests | Retry checkpoints retained in pending state and Stage 2 without restoring retired history |
| M-10 | Partial terminal classification; public parity not qualified | Both APIs, buffered/streamed canonical security disposition |
| M-11 | Candidate translation peak-context patch and deterministic tests in this revision | Windows regression and actual Pi usage, aggregate remains separate |
| M-12 | Existing lifespan hook retained; candidate makes bounded shutdown close admission before drain, starts an outstanding writer, and reports incomplete drain | Normal/exceptional lifespan, pre-writer enqueue, timeout/retry, full regression |
| M-13 | Candidate completed-run retirement and exact request-scoped orphan/expiry cleanup; report atomicity, Responses indexes, SQLite DDL and CLI defaults already present | Debugging durability, exact completed follow-up, active/resumable ownership, expiry, SSE roles and full regression |
| P-1 | Open; benchmark before redesign | Secured per-chunk runtime-integrity overhead; preserve check timing |
| P-2 | Open; benchmark before redesign | Coder 3-turn backend prefill/cache evidence |
| P-3 | Open; benchmark before redesign | 64/128 KiB serialization and event-loop/RSS measurement |
| P-4 | Open | Registry lifecycle and buffer measurements |
| C-1 | Maintainer scope decision | Secret-header identification without false positives |
| C-2 | Candidate caller-bound evidence gate, unchanged exact internal recovery, omission of session storage path, Phase-9B route and Phase-10 policy consumer sealing | Safe exact evidence/hash, credential and partial Canary withholding, auth, missing evidence, route tampering, full regression |
| C-3 | Maintainer scope decision | Worker-event quarantine and replay semantics |
| C-4 | Candidate narrow alignment of unknown Bash/PowerShell literal operand extraction with existing represented-path authority; no new shell sandbox claim | Positive NEVER, exact credential resource, benign unlocked commands, locked ambiguity, full regression |
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

### Qualification at 7e32db22790bb3effa8582b1676d1947d5373688
Full Windows CI: 1597 passed, 229 failed. Compared with fd53d7b's 220 distinct failure identities, nine additional failures: eight M-4 ledger fixture construction failures (missing queue_capacity) and one source-structure assertion requiring direct calls to inspect_represented_path. This revision supplies the required queue capacity and checks the new shared operation-aware fact producer still calls the original raw normalizer. M-9 and M-11 test identities did not appear among failures. Combined security qualification remains red at inherited Phase 7 safe-prefix test. No closure inferred from counts alone.

### Qualification at 0139e9694367198789109ef9737fd84de8eb0d26
Windows full CI: 1597 passed, 230 failed. Eight prior M-4 fixture/structural failures resolved, one M-4 bash ADS fixture remains (double quotes allowed expansion of $DATA). This revision keeps the structured literal ADS test and uses the exact explicit protected path for the bash gate case. Nine further failures concern request scope cleanup fixtures and prior adapter rearm expectations; changes distinguish explicit in-flight checkpoint ownership from bare registration, restore exact frozen-bridge cleanup and preserve no-rearm behavior for unowned API requests. Combined security still fails Phase 7 safe-prefix preservation. No test has been disabled.

### Qualification at c6323613dc7fc9adfbe1ca3ad56c6ff6b51d8541

Full Windows CI: 1,614 passed, 218 failed. Exact comparison with main 9a6fe53d (1,585 passed, 219 failed): zero new failed test identities and one resolved inherited failure, `tests/test_phase7_output_dlp.py::test_live_release_barrier_uses_credential_tier_a_and_preserves_safe_work`. Pi bridge, tool-free Coder Architect, combined security and isolated Phase 9B qualification all passed. No measured performance conclusions from CI runtime differences. This revision's debugging lifecycle changes require qualification. Completed report follow-up remains process-local and tools-off; the secondary temporary index retains only digest and identity, never report cognition. Pending durability is not arbitrarily expired, and index failures retain the completed identity rather than lose a valid follow-up.

### M-12 shutdown qualification candidate

The actual lifespan already invokes ledger.close off the event loop after orchestration and backend cleanup. Source review identified an enqueue-before-writer-start race and silent bounded-drain timeout in close itself. This revision closes projection admission under the authority lock before drain, preserves queued records, makes repeated closure safe, and logs incomplete shutdown without changing security outcomes or predecessor authority. New tests exercise real lifespan normal/backend-failure paths in an isolated process and deterministic queue-start and timeout/retry behavior. Pending CI; no closure claimed. C-1 is deliberately excluded by the existing closed-known-source credential-policy tests; a future extension must distinguish explicitly identified secret headers from ordinary header values rather than enroll all extra headers indiscriminately.

### M-13 executed qualification and C-4 candidate

Commit 3ce3c1e2: all four specialized workflows passed; full Windows regression 1,616 passed / 218 failed, zero new failure identities versus main 9a6fe53d. The two additional debugging durability/lifecycle tests passed. Full CI remains red due to inherited failures. Commit 83fbf1b7 qualification remains pending.

C-4 scope choice for the experimental branch: extend the existing represented-path contract to obvious literal operands of otherwise unknown Bash/PowerShell commands. Keep ambiguity, existing Workspace Lock rules, and normal unlocked use for unclassified semantics without a positive prohibited path. Skip URI operands and do not evaluate arbitrary command expressions. Existing Phase-4/5/6/7 admission owns consequences; no new sandbox promise. This is a candidate for review and qualification, not an approved expansion to general command execution control.

### C-2 candidate and completed qualification

Commit 83fbf1b7: 1,619 passed / 218 failed; commit 46d220ed: 1,627 passed / 218 failed. Both passed all four specialized workflows, and both have zero new failure identities compared with main 9a6fe53d. Full regression remains red due to inherited failures.

The public exact-key evidence route now applies the existing merged Canary policy and exact credential policy before caller release, without altering authoritative recovered text or SHA-256. The HTTP projection omits session_file and uses a non-reflecting not-found diagnostic. The secured entrypoint binds the new evidence consumer into both Phase-10 policy authorities and Phase-9B executable/route authority. Direct internal recovery retains full provenance. Credential matches use a distinct tool_evidence_http_release ledger boundary rather than model input/output. Live release and tamper regression cases added. Qualification pending. No universal host-path privacy claim for arbitrary tool results.


### C-3 executed qualification and C-5 candidate

Commit 4fdc49cc: 1,631 passed / 218 failed. Exact failing identity set unchanged from 29832af; all four specialized workflows passed. Both added orchestration quarantine tests passed. Candidate bounds simultaneous carries at 256 channels, never evicts a live prefix to admit a new one, and clears held fragments on upstream disconnect. This is exact credential protection at the existing known Pi delta seams, not a general guarantee over arbitrary worker event schemas.

C-5 candidate: interactive Kernel launch targets the secure entrypoint; direct Kernel --serve delegates to the secure child and propagates its exit status; direct Responses entrypoint calls the same secure startup. Explicit --serve --unsecured-test-serve is a conspicuous isolated test-only escape hatch on the base Kernel, never selected by the launcher. The secure entrypoint rejects that flag. A partially installed source authority cannot silently fall back to an unsecured server. Frozen executable behavior without secure composition fails closed. Programmatic ASGI/unit test imports remain available. No changes to policy thresholds or cognitive modes. Qualification pending.
