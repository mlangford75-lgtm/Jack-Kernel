# Jack Kernel Security Layer — Phase 5 Validated Checkpoint

**Date:** 2026-10-01  
**Phase:** Deterministic Consequence Gate  
**Baseline before Phase 5:** `0c3395154b89b3dbdb1b5448ecce6e38d5d8238e`  
**Accepted implementation head:** `551eda0d200fe4b819c3b09cb9480c1ad52f0bdd`  
**Release merge commit on `main`:** `eaf0c2e9663bf9b877c51918f7ccead2b07cb1ba`  
**Pull request:** #25 — `Phase 5: deterministic Consequence Gate`  
**Architectural acceptance:** accepted at the Phase-5 stop-gate boundary before merge  
**Release state:** merged to `main`; Phase 6 not started

## Scope

Phase 5 introduces a shared deterministic consequence-disposition boundary without centralizing fact production, execution authority, or failure blast radius.

The governing architecture is:

```text
existing deterministic fact producers
                |
                v
         Consequence Gate
                |
                v
         SecurityOutcome
                |
                v
     narrow existing enforcement seam
```

Fact production remains with the subsystem that actually possesses deterministic knowledge. The Gate consumes those facts and decides disposition. It does not re-derive facts, invent host effects, or become the executor.

## Governing invariant

> The Consequence Gate MUST select the smallest disposition sufficient to preserve the violated deterministic invariant. It MUST NOT destroy cognition, state, or unrelated authorized work merely because one consequence cannot proceed.

Phase 5 therefore treats `SecurityOutcome` as a classification of the consequence boundary being evaluated, not as a blanket verdict on the surrounding cognition, task, run, connection, or Kernel process.

## Security outcomes

Phase 5 uses the existing four-outcome vocabulary:

- `ALLOW`
- `DENY_AND_CONTINUE`
- `REQUIRE_USER_DECISION`
- `HARD_INTERRUPT`

`UnmappedAuthorityFact` is **not** a fifth runtime security outcome. It is an internal Phase-5 refusal to fabricate a policy mapping where current Jack semantics have not established one.

## Outcome and containment are separate

Phase 5 explicitly separates security disposition from containment scope.

Current containment vocabulary includes:

- `NONE`
- `TOOL_CALL`
- `TOOL_BATCH`
- `EXECUTOR_ADMISSION`
- `OVERLAP_ADMISSION`
- `EVIDENCE_FRAGMENT`
- `CONSEQUENCE`

A hard invariant does not automatically authorize global destruction. The same underlying violation can be contained at different boundaries depending on where the consequence is about to escape.

Examples:

- positive deterministic NEVER-path match at tool-release batch -> `HARD_INTERRUPT`, `TOOL_BATCH`;
- the same NEVER fact at executor admission -> `HARD_INTERRUPT`, `EXECUTOR_ADMISSION`;
- configured Workspace Lock plus deterministic outside target -> `DENY_AND_CONTINUE`, normally `TOOL_CALL`;
- runtime/lane identity mismatch at executor admission -> `DENY_AND_CONTINUE`, `EXECUTOR_ADMISSION`.

## Kernel-owned installation

The Kernel owns Phase-5 installation.

`jack_kernel._install_bundled_runtime_extensions()` installs `jack_consequence_gate` directly. Responses compatibility does not bootstrap Kernel security.

The Gate receives the authoritative Kernel context through `install(jk)` and uses the Kernel-supplied `SecurityOutcome` enum. It does not import, discover, alias, or reconstruct a `jack_kernel` module identity through `__main__` or `sys.modules` manipulation.

## Single represented-path fact source

`jack_path_policy.py` remains the single deterministic source for represented-path authority facts.

`inspect_represented_path(...)` produces `RepresentedPathAuthorityFacts`, including:

- normalized represented target;
- deterministic NEVER match;
- whether Workspace Lock is configured;
- deterministic/ambiguous state;
- workspace membership;
- invalid represented path;
- executor-cwd deferral;
- explanatory reason.

Both the legacy Phase-4 path authorization behavior and Phase-5 disposition consume those same raw facts. Phase 5 does not maintain a second path-policy implementation.

The Phase-4 limitation remains binding:

`RepresentedPath != NecessarilyResolvedObject`

No universal filesystem-object attestation was introduced.

## Executor-admission integration

Live Phase-5 executor identity facts are intentionally narrow:

- `runtime_matches`
- `lane_matches`

A runtime or lane mismatch is denied at the executor-admission boundary without broad cancellation or destruction of unrelated work.

Exact pending tool-call correlation remains owned by the existing Phase-4 admission mechanism. Phase 5 does not falsely claim that correlation as a centralized live fact seam.

## Lifecycle identity remains intentionally unmapped

The original Phase-5 required matrix includes separate coverage for:

- stale task;
- wrong run;
- wrong `run_epoch`.

All three are now independently tested:

```text
stale task:
    task_matches=False
    run_matches=True
    run_epoch_matches=True

wrong run:
    task_matches=True
    run_matches=False
    run_epoch_matches=True

wrong run_epoch:
    task_matches=True
    run_matches=True
    run_epoch_matches=False
```

Each currently raises `UnmappedAuthorityFact` inside the policy evaluator.

This is deliberate. Existing Jack behavior proves that lifecycle/correlation mismatches are boundary-specific: some mismatches are ignored as unrelated input, some invalidate only pending correlation state, and cancellation ownership must not affect unrelated active work. Phase 5 therefore does not invent one universal mapping such as `DENY_AND_CONTINUE` or `HARD_INTERRUPT` for every task/run/epoch mismatch.

No live consequential path is wired to surface `UnmappedAuthorityFact` as a broad runtime denial.

## Evidence policy

Phase 5 intentionally narrows evidence policy to the grounded violation Jack can name precisely: forgery of Jack's reserved evidence namespace.

- valid/non-forged Jack evidence namespace -> `ALLOW`;
- forged Jack reserved evidence namespace -> `DENY_AND_CONTINUE`, `EVIDENCE_FRAGMENT`.

Unknown provenance alone is not promoted into a security violation. Phase 5 does not claim a generalized evidence-trust classifier.

## Approval and security-health nonclaims

`ApprovalFact` exists as a policy contract and demonstrates the intended `REQUIRE_USER_DECISION` semantics, but no live approval authority producer was invented in Phase 5.

There is no generalized `SecurityHealthFact`. Telemetry, registry state, manifests, UI state, logging health, and other observational surfaces remain non-authoritative unless a separate deterministic authority contract explicitly says otherwise.

## Tool/schema and settlement policy surfaces

Phase 5 includes typed policy facts for stage/tool authority, tool schema, approval, evidence, lifecycle, settlement, and executor identity.

Typed policy presence does not imply that every fact type has been wired into a live runtime seam. In particular, Phase 5 does not overclaim call-scoped schema containment where the existing runtime cannot yet prove safe-sibling preservation at that exact boundary.

Settlement policy preserves the existing distinction:

> Cancellation is not settlement.

An open run can block only overlapping admission without erasing the valid run already in progress.

## Conflict handling

The Gate does not invent precedence between unrelated non-hard outcomes.

- conflicting non-hard outcomes raise an internal inconsistency rather than silently selecting one;
- equal non-hard outcomes with incompatible containment scopes do not silently broaden blast radius;
- hard outcomes dominate only where an established deterministic fact actually maps to `HARD_INTERRUPT`.

## Validation evidence

### Accepted pre-merge stop gate — GitHub Actions run #106

Exact head: `551eda0d200fe4b819c3b09cb9480c1ad52f0bdd`

- `git diff --check`: **PASS**
- runtime module compilation: **PASS**
- targeted Phase-5 suite: **37/37 PASS**
- full Python suite: **413/413 PASS**
- Pi harnesses: **7/7 PASS**
- Pi bridge LF SHA-256: `8ffd33fd33ae15a785e2bf9015f17fc14f1de27b09515d5e868ec163d54c15f0`
- Pi bridge CRLF SHA-256: `93a6843cdaaeda637474b584919ed003930296de281570e3ddc391f54ef65565`

### Post-merge validation — GitHub Actions run #107

Exact `main` merge commit: `eaf0c2e9663bf9b877c51918f7ccead2b07cb1ba`

The merge commit tree is identical to the accepted implementation head.

Post-merge CI passed:

- runtime module compilation: **PASS**
- targeted Phase-5 suite: **37/37 PASS**
- full Python suite: **413/413 PASS**
- Pi harnesses: **7/7 PASS**

The PR-only whitespace step is skipped on push events; the exact accepted PR diff had already passed `git diff --check` in run #106.

## Released file scope

The accepted Phase-5 implementation changed ten repository files relative to the pre-Phase-5 baseline:

- `.github/workflows/ci.yml`
- `jack_consequence_gate.py`
- `jack_kernel.py`
- `jack_path_policy.py`
- `jack_secure_entrypoint.py`
- `tests/test_phase5_consequence_gate.py`
- `tests/test_phase5_path_gate_integration.py`
- `tests/test_phase5_runtime_integration.py`
- `tests/test_phase5_secure_entrypoint.py`
- `tests/test_surgical_regressions.py`

Notably absent from the final implementation diff:

- changes to `jack_responses_compat.py`;
- a duplicate `jack_path_authority_facts.py`;
- temporary patch scripts or write-enabled workflows;
- Phase-6 implementation.

## Explicitly unclaimed

This checkpoint does not claim:

- a universal filesystem sandbox;
- final-object filesystem attestation;
- shell semantic interpretation;
- arbitrary custom-tool effect prediction;
- universal host-effect knowledge;
- generalized telemetry authority;
- generalized evidence trust;
- a live approval subsystem;
- generalized security-health/integrity authority;
- one universal lifecycle-mismatch severity;
- Phase-6 ledger integrity or cross-runtime serialization.

## Historical chain

Phase 5 is cumulative.

The Phase 0-3 and Phase-4 checkpoints remain historical evidence and are not rewritten by this release.

Phase 4 continues to own represented-path fact production and path-policy semantics. Phase 5 adds the shared deterministic disposition boundary on top of those established facts.

## Closure state

Phase-5 architecture, implementation, validation, and release to `main` are accepted.

Phase 6 has not started.
