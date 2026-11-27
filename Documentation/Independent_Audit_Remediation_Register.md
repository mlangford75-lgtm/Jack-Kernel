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


### C-5 executed qualification and C-6 authority inventory candidate

Commit ed68f121: 1,634 passed / 218 failed. Exact failure identity set unchanged from 4fdc49cc; all four specialized workflows passed; three added startup tests passed.

C-6 first scoped candidate: pin the five consequence-bearing GET routes in the existing model/orchestration scopes, require their presence in the actual secured host, bind credential-resource policy identity and exact material at the actual Phase-10 path consequence boundary, add selected credential/resource/diagnostic executable and source dependencies, and prevent global verification from reporting success after confirmed scoped invalidation. Seven new qualification cases exercise the five GET routes, restored scoped identity, and missing/restored real resource registry binding. No general interpreter attestation claim. Remaining C-6 items (pending history/recovery state, exception handler and diagnostic coverage, other source dependencies, auth comparison and platform scope) remain open. Qualification pending.


### C-6 pending transaction authority candidate

All four specialized workflows passed at 35e77813; full Windows regression qualification was still running when this follow-on candidate was prepared. Seal complete pending history and deterministic recovery counter material; use request-local copies during owned execution, snapshot recovery on authorized rearm, and avoid mutating sealed historical bridges. Include actual recovery, outcome and forensic module dependencies in the Phase-9 inventory, with selected recovery and outcome callable pins. Seven additional tests cover historical user/tool/owner tampering, recovery counter and seen-ID mutation, authorized recovery settlement, and real Kernel interrupted-resume continuity. This changes checkpoint ownership/copying, not prompts, thresholds or cognitive projections. Pending qualification; exception-handler/diagnostic coverage and auth/portability items remain open.


### C-6 diagnostic integrity candidate

35e77813 full Windows regression: 1,641 passed / 218 inherited failed, exact failure identities unchanged; four specialized workflows passed. 151d3ea2: all four specialized workflows passed; full regression still running at preparation time. Candidate seals the complete registered exception-handler table and effective executable shapes (not Starlette's lazy middleware cache), applies configured contiguous Canary thresholds to diagnostic-only privacy, fixes retained-diagnostic ledger key/byte matching, and uses timing-safe comparisons for existing Kernel and Pi bearer authentication. No change to model-facing Canary sensitivity, authentication format, or authorized tool scope. Additional tests cover handler tamper/terminal invalidation and configured diagnostic threshold. Remaining C-6: phase-7 ledger coverage for Starlette/validation exceptions and explicit platform scope evaluation. Qualification pending.


### C-6 diagnostic ledger completion candidate

4537d949 qualification: 1,650 passed / 218 inherited failed, exact failure identities unchanged versus 35e77813; all four specialized workflows passed. Extend the existing Phase-7 diagnostic guard and ledger observation to the actual registered Starlette HTTP and request-validation handlers. Record only structural credential release blocks; preserve status, clean headers and ordinary diagnostics, including non-reflected validation input. No change to custom Canary sensitivity, model context or tool authority. Existing live ledger qualification expanded to check exact event increments and benign cases. Platform scope: README documents Windows execution; the Windows represented-path authority deliberately fails closed on non-Windows credential resource paths. Linux/macOS secure serving is not qualified and is not enabled by relaxing resource normalization. A native path-policy design and platform-specific tests would be a separate scope decision. Qualification pending.


### C-1 explicit backend extra-header credential candidate

C-6 diagnostic-ledger commit 2d2348a passed all four specialized workflows; full regression was still running during C-1 preparation. C-1 experimental scope: recognize a closed list of conventional authentication header names and allow the operator to explicitly designate arbitrary extra-header names as credentials (CLI prompt or JACK_BACKEND_SECRET_HEADER_NAMES JSON array). Preserve existing extra-header transport format and all ordinary metadata, with no entropy heuristic or minimum length. Multiple distinct protected values have stable per-header identities, exact duplicate values retain aliases, and stale/ambiguous explicit designations fail closed without reflecting secret values. Existing Phase-7, Tier-A Canary, orchestration, and diagnostic consumers receive the same immutable policy. Existing configs with unusual secret header names must explicitly designate them; this is not universal secret discovery. Tests cover selection, benign metadata, exact ingress, Canary registration, alias preservation and malformed configuration. Qualification pending.


### P-1 measurement harness (no production optimization)

Introduces a Windows benchmark of actual Jack Chat Completions ASGI dispatch and full bundled vs Phase 8/9B/10/11 secured release composition. The only synthetic component is a 1,000-frame SSE producer installed before authority sealing; separate processes use isolated synthetic credentials and no backend or listening socket. Three timed runs after warm-up report elapsed time, source frames/sec and cooperative scheduler gap statistics. Exact reconstructed content, normal completion and active authority are correctness gates, with no arbitrary performance threshold. This isolates host release overhead, not provider inference, Uvicorn/network throughput or local Defender impact. Hosted Windows CI provides initial measurements; maintainer workstation verification remains required before any enforcement redesign. No production code or security timing changed in this benchmark revision.


### C-6 executed qualification; P-2/P-3 measurement candidates

2d2348a final Windows regression: 1,650 passed / 218 inherited failed, identical failing identities to 4537d949; all four specialized workflows passed. C-6 complete within the existing Windows scope. C-1 2fb9729 all four specialized workflows passed, full regression pending at preparation. P-2 source inspection confirms both chat and chat_stream fold the current Coder specification into the leading system message. Added three-turn actual MockTransport wire capture for Flash/Thorough, streamed/buffered, with existing byte-probe reports and an offline-only attributed-tail comparison. This proves request-byte behavior, not actual provider cache reuse, and deliberately does not change plan authority or template semantics. P-3 measures real shared backend request preparation on 64/128 KiB synthetic histories with the byte probe enabled/disabled, component timings, separate allocation tracing and Windows process-wide high-water working set; no inference, no performance threshold. No production code or policy modifications. Local backend prefill/cache counters and workstation confirmation remain necessary before redesign.


### Executed C-1, P-2 and P-3 qualification; P-1 harness correction and P-4 evidence

C-1 2fb9729: 1,655 passed / 218 inherited failed, identical failing identities to 2d2348a; all four specialized workflows passed. P-2/P-3 workflow 45990015749 passed all six new measurement cases. P-2: both Coder profiles and transports report first_message_changed at index 0 for both transitions; leading system content common prefix 2,445 UTF-8 bytes, first changed pre-fold region caller_or_source_system_1. Offline tail projection shares 1 and 3 complete messages respectively; no actual KV hit/miss claim or change to plan authority. P-3 hosted Windows 64 KiB: 1.4506 ms disabled vs 56.8948 ms enabled; 128 KiB: 2.3669 vs 106.4862 ms. Byte-probe median 53.1695 / 101.7848 ms, dominating observed cost. Traced peaks 361114/972708 and 688593/1816621 bytes respectively; whole-process high-water not attributable memory. Maintain existing diagnostics semantics while evaluating optimization; actual workstation measurement remains outstanding.

P-1 workflow 45989724463 passed all pre-existing security gates but failed the benchmark after the bundled measurement (median 44.19 ms / 1000 synthetic frames); the secured warm-up succeeded but the first measured request returned 503. Harness changed a captured scalar from 20 to 1000 after Phase 9B sealed the callable; scalar closure content is part of executable identity. Fix harness with one fixed pre-seal workload for warm-up and all measurements, and report mismatched slots on any HTTP rejection. No production enforcement changes. Rerun required.

P-4: orchestration carry already bounded at 256 by C-3 with non-eviction and disconnect cleanup; do not add unsafe LRU. Remaining source findings: strong closed-ledger registry retention (policy filter also holds policy references, so do not remove historical protection indiscriminately), exact detector max-threshold allocation, synchronous long-cycle scanning, and blind FIFO eviction of unfinished Agentic owner. Added measurements of actual record-only 270k-word retention at thresholds 12/128, 12,288-word shadow negative scan timings, isolated exact-policy ledger registration/close retention, and actual lifecycle registration under reduced cap with an awaiting-tool owner. Informational reports, not permanent assertions of defective behavior. No production behavior changes; qualification pending.


### P-4 executed evidence and narrow correction candidate

Windows workflow 45990471529 passed five P-4 measurements. Exact detector at threshold 12 retained 265,903 words (30,729,868 traced bytes) versus required exact suffix capacity 24,576 words; threshold 128 had the same retained words. Long shadow detector negative sample (12,288 words) took 103.75 ms, scan total 93.58 ms, maximum scan 6.961 ms. Closed-ledger registry retained all 16 isolated ledgers; lifecycle pressure evicted the awaiting-tool owner while the durable journal still reported awaiting_tool. Correct exact-detector retention using the configured repetitions and bounded slack; preserve exact word comparison, range-hash correctness, 16-word cadence and all thresholds, and trim prefix arrays without rehash. Replace strong diagnostic ledger registry bindings with exact-object weak references and identity-safe cleanup; live host and wrapper ownership are unchanged, and the diagnostic filter still retains credential protection. Evict only terminal lifecycle records, never active/suspended/retryable work. When all lifecycle entries are live, the observational retention target may be exceeded; abandoned pending-work admission/expiry policy is not silently invented. Reproduction fixtures now assert the corrected behavior, plus live registry identity, all-live lifecycle pressure and full-width detection after multiple trims. Qualification pending. Long shadow scan and P-3 probe redesign remain under investigation, with no threshold change.


### P-3 digest-only incremental measurement optimization

Measured per-byte prefix signature cost is the dominant P-3 overhead. Reuse a retained trajectory only by complete SHA-256, exact byte length and exact captured-byte count, within the same probe's current observation and prior same-stage/immediately-preceding snapshots. No new persistent cache, prompt retention, reduced capture length, changed diagnostic schema or security/cognitive behavior. Generate new trajectories for changed content; serialize one message at a time rather than retain the full list of temporary serialized bytes. Preserve existing cap semantics, pre-fold provenance and exact offset reports. Tests verify identity reuse, differing capture budgets, UTF-8/changed-content offsets and comparison-report equivalence against forced fresh hashing across stages. Updated P-3 benchmark reports first/cold request and warmed repeated request independently. Cold/novel content still incurs generation cost; do not claim universal acceleration. Qualification pending.


### P-1 executed qualification; V-1 policy evidence and V-2 correction candidate

7eea765d full regression: 1,666 passed / 218 inherited failed, identical failing identities to 2fb9729, all four specialized workflows passed. P-1 run 45990471722: median bundled 0.0246639 s vs secured 43.8736099 s per 1000 frames; 43.848946 ms incremental/frame; secured throughput 22.79 source frames/s; median scheduler gap 43.2854 ms, max 156.6212 ms. All released byte counts identical (199398), correctness and active authorities passed. Serious host bottleneck; need attribute cost to actual per-boundary verification components before optimizing. No reduction of verification frequency authorized. Workstation/provider measurement remains outstanding.

V-1 source confirms current terminal generation-budget contract intentionally rethrows Stage-2 GenerationBudgetExceeded rather than using ordinary degraded A1-only result. A1 is journal-frozen, memory remains uncommitted, but outward budget failure replaces A1. Added actual buffered/streamed budget evidence without changing policy. Maintainer decision required on allowing exact frozen A1 release after a Stage-2 budget breach; no retry, partial M or new answer authority should follow any decision.

V-2 launcher start.bat enables transaction links and disables task anchor. Current projected authenticated M is unlabelled, while context accounting identifies M/A1 by legacy text markers, misattributing valid committed history as other assistant content. Add request-local diagnostic sidecar using identity of the actual projected assistant dictionaries, their authenticated historical kind and forensic role, not model-supplied labels. Strip all private keys as before; no payload changes, no new trust authority. Actual dispatch classifies unmarked/unowned prose as other assistant content; legacy direct diagnostic invocation retains historical descriptive parsing. Both transports report exact UTF-8 M/A1 bytes after journal-backed rehydration with production link flags. Optional memory-as-system capsule continues to count as system content, not assistant bytes. Qualification pending.


### V-1/V-2 executed qualification; V-3 tool-message projection candidate

P-3/P-4 commit d6e0571c: 1,672 passed / 218 inherited failed; all four specialized workflows passed. P-3 enabled warm preparation 2.36 ms (64 KiB), 3.81 ms (128 KiB), versus 56.89/106.49 ms before. P-4 threshold-12 retained traced allocations 3.33 MB versus 30.73 MB, peak retained words 29,696 versus 267,264, closed ledger retention 0 versus 16, awaiting-tool owner retained under pressure. V-1/V-2 commit a25fd324: 1,677 passed / 218 failed; exact failure identity comparison against d6e0571c unchanged and against main 9a6fe53d zero additions, one removal (Phase 7 safe prefix). All four specialized workflows passed. V-1 policy decision remains open; V-2 correction qualified.

V-3 first candidate: strip is_error, isError and tool_outcome only from model-facing copies of tool-role messages, including historical Pi replay without private Jack fields. Canonical status, text, IDs and recovery classification remain unchanged. Both transports exercise actual serialized request shape and unchanged source history. No change to sampler/template controls, model selection, or env resolution in this revision; these remain separate V-3 items. Qualification pending.

### V-3 Pi environment reference candidate

Explicit $NAME references now reject missing or whitespace-only values before health/model discovery, without reflecting the name or value; an explicitly referenced token cannot silently become a literal bearer or unauthenticated request. Runtime registry URL selection still takes precedence over an unused configured URL. Ordinary omitted credentials remain supported for intentionally unauthenticated deployments. The existing provider refresh error path clears activeRuntimeBinding and does not register a new provider; this is not a claim that Pi unregisters stale prior registrations. Harness covers missing and empty references with zero health requests, and successful resolved authentication. Qualification pending.

### V-3 explicit standard-wire candidate

Add opt-in openai_standard control shape for the existing Custom backend profile (JACK_QWEN_CONTROL_SHAPE or Advanced settings). It omits local sampler extensions top_k/min_p/repeat_penalty and native template/top-level thinking controls, while preserving message projection, common sampling fields, seed policy, tool-choice authority and existing local backend defaults. No automatic vendor inference or speculative retry. This is a narrow transport option, not full cloud qualification: provider-specific accepted sampling/seed/reasoning-history fields, thinking effort and actual cache behavior still require a capability contract and live qualification. The existing Custom/vLLM default stays unchanged. Actual buffered/streamed wire comparisons against local controls added. Qualification pending. Model switching remains separate because replacing the pinned backend during an active or suspended multi-stage transaction may change its model/continuity contract.

### V-3 executed transport qualification and idle LM Studio discovery candidate

80cb1b3 full regression: 1,681 passed / 218 inherited failed, exact identity comparison with main 9a6fe53d zero additions and one removal; all four specialized workflows passed. Historical outcome metadata, Pi environment resolution and explicit standard-wire transport are qualified. Idle LM Studio discovery candidate: existing authenticated health/model metadata endpoints re-discover loaded instances only when no admitted request, suspended tool/intake/user resume or live debugging run exists. Admission and idle refresh share a short discovery lock; inference and settlement do not hold that lock. Cached selection is stable throughout admitted and suspended work, explicit selections still reject mismatch, and failed idle discovery invalidates stale metadata. Changed selection/context resets observational prompt diagnostics, not cognitive history. Legacy Deep Reasoning auto-refresh deliberately excluded pending its distinct bridge lifecycle assessment. No per-token or per-stage discovery calls; direct clients must request model metadata to refresh, and this cannot prevent an external backend operator unloading a model during inference. Deterministic mock discovery, mismatch, suspended-owner and admission serialization cases added. Qualification pending.

### V-4 existing Responses authority evidence; P-1 cost attribution candidate

V-4 source and existing test_codex_request_mapping_preserves_client_tools_and_jack_authority_boundary explicitly require top-level instructions to map to developer context, and both caller-system selectors explicitly reject developer and non-leading system material. This is a deliberate existing authority boundary rather than an accidental untested mapping. New buffered/streamed wire evidence records the actual omission and leading-system/Stage-2 distinction; no production policy change. Maintainer choice still required if top-level Responses instructions should be admitted as the caller cognitive contract when no leading system exists; never promote arbitrary historical developer messages or alter Jack-owned stage/security authority.

P-1 adds a separate cProfile pass to the existing secured 1,000-frame benchmark after the unprofiled wall-clock samples. No guarded functions replaced or verification cadence changed. Reports aggregate own/cumulative time, primitive/total call counts, basename/line/function metadata and module exclusive totals; no argument values, source text, host paths, credentials or persisted profile dump. Inclusive timings overlap and profiling adds overhead; compare call counts and attribution, not profiled latency against earlier unprofiled runs. Actual content, completion and authority checks still apply. Qualification pending.

### P-1 measured fingerprint attribution and bounded immutable-transcript candidate

b11d700: 1,686 passed / 218 inherited failed, exact comparison with main zero added and one removed; all four specialized workflows passed. V-3 scoped corrections and V-4 current-policy evidence qualified. P-1 profiling run 45995518482: ordinary median bundled 0.02466 s / secured 47.12047 s, identical 199398 released bytes; profiled 2010 verify_for calls, 203010 _function_shape calls, 25330020 walk calls, 34883550 atom updates; inclusive fingerprint 129.142 s, source measurement 17.226 s, Canary verify 0.161 s. Profiling overhead and overlapping inclusive times are not ordinary latency measurements.

Candidate: combine the exact four framed atom updates into one byte-identical update and replay immutable CodeType subtree transcripts within a single synchronous _check_locked invocation only. Preserve original framed bytes, selected scopes, function/receiver identity, live defaults/closures, mutable/executable constants, route/handler checks, source reads, measurement limits and both release checks. Strong exact code identity, 128 entries of at most 64 KiB, no persistent memo, no skipping mutable or opaque code constants, no cross-boundary reuse. Cached node counts and relative depth enforce the original global traversal limits. Added equivalence, mutable code constant, depth/node and later-boundary mutation cases. Windows qualification and actual unprofiled before/after benchmark pending; no speedup claim yet.

### V-5 early rejection of conflicting credential/Canary configuration

The existing test_canary_collision_fails_instead_of_silently_dropping_policy explicitly requires fail-closed rejection. Preserve that contract, including Tier A ownership and the configured sensitivity; do not silently coalesce values. Security Center validation now invokes the existing Phase-7 credential builder and merge validator against the candidate launch configuration whenever effective custom patterns exist. Candidate values mirror the child environment, including backend-profile fallback, explicit extra header declarations, derived Basic wire credentials and resolved Pi token. No credential values are displayed; conflicts reject the candidate before accepting it or spawning a child. Secured child validation remains authoritative against later environment changes. Six regression cases cover configured and fallback sources, candidate rejection and administrator override rejection. Qualification pending.


## Candidate qualification and remaining scope (2026-11-27)

Qualified experimental code head: `753ce5c9e783b9691922870b9640fde5031e10f2` (61 remediation commits). This supersedes the earlier pending statuses in the historical register above; it is not a merge, a frozen security checkpoint, or a clean full-suite result.

| Qualification | Result |
|---|---|
| [Full Windows regression](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/46028576584) | 1,716 passed, 218 failed; exact failing identity set unchanged from the preceding qualified 1,712-pass head |
| [Combined security](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/46028576589) | Passed |
| [Isolated executable identity and benchmark](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/46028576635) | Passed |
| [Independent Pi bridge](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/46028576573) | Passed |
| [Tool-free Coder Architect](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/46028576556) | Passed |

The inherited mainline baseline had 219 failed identities; the earlier exact comparison established one resolved inherited failure and no added identities. The 218 outstanding inherited failures are not suppressed or reclassified as a clean pass.

### Current architectural dispositions

- **M-1–M-13 and C-1–C-6:** remediation accepted against the recorded regression baseline and specialized gates; scope remains selected authority enforcement on the supported Windows runtime, not general OS sandboxing or arbitrary same-process tamper resistance. Explicit extra-header credential designation is not universal discovery. Linux/macOS secured path authority is not qualified.
- **P-1:** sealed immutable code-tree transcripts reuse byte-identical framing with exact object identity, bounded entries, node/depth limits and live measurement of mutable dependencies. Both Kernel and HTTP release verification, full source-file measurement and terminal/scoped integrity consequences remain. The comparable hosted 1,000-frame mock stream improved from 40.1536 s to 26.8917 s (approximately 33% lower processing time; 24.9 to 37.2 frames/s). The same 199,398 bytes were released in every sample. Profiling walk calls declined from 16,769,430 to 4,112,460. No live inference throughput claim. Remaining per-frame integrity overhead is substantial; a lower verification cadence or periodic-only source verification would be a distinct security-timing decision, not part of this optimization.
- **P-2:** wire-level evidence confirms leading-system change across Coder turns. Actual backend tokenized cache/prefill comparison is deferred; the Architect specification remains in its current authority placement. A byte prefix is not KV-cache telemetry.
- **P-3:** qualified repeated-content diagnostic acceleration, 64/128 KiB warm preparation 2.36/3.81 ms versus 56.89/106.49 ms in the recorded hosted runs. Cold content still incurs digest generation.
- **P-4:** qualified bounded exact-detector retention, weak diagnostic-ledger ownership, non-eviction of live pending owners, shadow matching and vocabulary retirement/reappearance coverage. Long-cycle observation, source suppression and interruption eligibility are preserved.
- **CL-1:** final unreachable secondary Architect recovery branch removed and qualified. Still-referenced helpers remain; this is not authorization to retire cognitive profiles. **CL-2:** shared request assembly and exact wire-equivalence regression coverage qualified.
- **CL-3:** the following errata supplement dated technical papers. Historical artifacts and original qualification harnesses remain intact: the cache experiment is explicitly archival, the Phase 3G workflow targets its historical branch or manual dispatch only, and the NVIDIA workflow is a separate optional live-provider qualification (not an active audit gate). Do not delete potentially reusable qualification evidence merely because its original experiment is superseded.
- **V-1:** after exact A1 freeze, Stage-2 reasoning/output budget exhaustion terminates memory generation, returns exact A1 via the existing degraded-commit path, records memory_failed, and does not commit unverified M or retry tools. Stage-1 budget breaches remain terminal; hard security failures propagate. Both transports and forensic state are qualified.
- **V-2/V-3:** qualified authenticated M/A1 accounting, host-only tool outcome metadata, explicit standard-wire controls, Pi environment reference resolution, and idle LM Studio model discovery within the recorded scope. No universal cloud or live-provider qualification.
- **V-4:** top-level Responses instructions deliberately map to developer context, excluded from the current leading caller-system contract; later system/developer messages are not promoted. An explicitly leading system message retains its existing caller authority in permitted stages, never the retrospective stage. The existing behavior is retained and documented rather than silently broadening authority.
- **V-5:** explicit early rejection of credential/custom Canary collisions retains Tier A ownership and configured sensitivity; child validation remains authoritative.
- **V-6:** legacy cognitive modes and compatibility switches preserved. No retirement approval or change to legacy selectors.

### Whitepaper errata and document precedence

For the November 26 comprehensive architectural, computational and security whitepaper, sections 21.4 and 21.12 must be read as follows: current Coder Flash and Thorough use a tool-free Architect. Coder alone receives the applicable execution tools. The Architect specification is fallible working guidance, not new user authority or proof of tool execution. Read-only Architect inspection belongs to proposed Coder Hybrid (section 54), not current Coder. Retain the existing historical papers and their measured results; this is an explicit candidate addendum, not a silent revision of their original claims. The standalone November 26 comprehensive paper was not found as an editable source in the repository tree; this register supplies the erratum rather than claiming its original bytes were rewritten.

The November 17 Agentic product paper and runtime specification are dated historical records; their new cross-reference points here for the subsequent candidate contract. No historical benchmark is retroactively restated as a fresh release result.

### Remaining release boundary

P-2 live backend measurement and V-6 optional legacy retirement are deferred. P-1 preserves the present verification cadence; further redesign that changes the observation window is not authorized by performance evidence alone. All implemented corrections have completed regression-baseline and targeted qualification at the code head above. Documentation-only changes still require the ordinary candidate checks. Full CI remains red from inherited failures; no merge or frozen security validation is represented by this record.


### Follow-up regression reconciliation and P-1 qualification (2026-11-27)

Code head `d1808d86fee2e02e9e30e17f8e25dd612140dcd7` (67 experimental commits) completed [Windows regression](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/46040373423): **1,786 passed / 168 failed**. Independently extracted exact pytest failure identities from the completed Windows logs for this head and [the earlier documented 1,716-pass checkpoint](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/46030698847): 218 earlier identities, 168 current identities, 50 removed, zero added. This is a differential qualification, not a clean full-suite pass. The original mainline comparison remains inherited evidence from the preceding register; it was not freshly repeated here. [Combined security](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/46040373217), [isolated executable identity](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/46040373440), [independent Pi bridge](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/46040373218), and [tool-free Coder Architect](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/46040373448) all passed.

P-1 follow-up: allow 256 sealed immutable code trees instead of 128, maintaining the existing 8 MiB aggregate transcript-byte cap, live mutable dependency measurements and full source measurements at both release boundaries. The three unprofiled secured samples were 28.8086, 28.4627 and 28.8678 seconds for 1,000 synthetic frames, compared with 26.8032, 26.8917 and 27.1346 seconds in the preceding hosted benchmark. Median end-to-end time increased approximately 7.1%, while recursive walk calls declined from 4,112,460 to 2,287,380 (44.4% fewer). The profiled source measurement inclusive time increased from 19.7307 to 24.4690 seconds; inclusive times overlap, and different hosted runners are not controlled comparisons. Both runs released 199,398 bytes in every sample and recorded 2,010 verification calls in their profiled pass. The additional optimization is functionally qualified, but no incremental end-to-end speedup is established. A matched-run comparison is appropriate before making an incremental performance claim. No cadence reduction is authorized.

The 168 remaining failure identities are concentrated in 29 Agentic test files. Largest groups: withhold-A1 (23), reasoning-primary memory experiment (22), Stage-2 turn-local retention (17), final-review scheduling (16), and stage-scoped system authority (14). These require contract-by-contract classification; historical profile and prompt expectations cannot be presumed to represent current requirements, and actual security or transaction failures must not be dismissed as stale. No skip, xfail, assertion deletion, or production policy change is justified by the red count alone. Remaining independent work: reconcile these fixtures against the current documented cognitive contracts, conduct a controlled P-1 comparison, and complete final qualification and documentation reconciliation. Main remains unchanged.
