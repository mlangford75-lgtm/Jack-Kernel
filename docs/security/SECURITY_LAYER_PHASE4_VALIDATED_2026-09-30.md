# Jack Kernel Security Layer — Phase 4 Validated Checkpoint

**Date:** 2026-09-30
**Phase:** Restricted Paths + Workspace Lock
**Branch:** `security-phase4-restricted-paths-workspace-lock`
**Baseline before Phase 4:** `4c0703dfdb2f0082e4a358fe2ac474c9a2fdbf59`
**Implementation freeze:** `0e897b801d5b5da8d604cf21556b40da769c26fe`
**Checkpoint tag:** `security-layer-phase4-validated-2026-09-30` (target: `0c15331d4673412befc626b64d7c4e52f7018fb4`)

## Scope

Phase 4 implements host-authoritative represented-path security for configured NEVER roots and optional Workspace Lock while preserving Jack's fail-soft treatment of recoverable cognition.

## Governing invariant

> Jack Kernel MUST make configured NEVER paths and an explicitly configured Workspace Lock non-negotiable authority boundaries. It MUST NOT weaken those boundaries because probabilistic cognition requests, rationalizes, retries, or reformulates an unauthorized consequence. Outside those explicit boundaries, Phase 4 MUST NOT discard, suppress, or disable useful work merely because Jack lacks universal knowledge of external execution semantics. When enforcement is necessary, Jack MUST contain the smallest consequential unit compatible with protocol truth and preserve all cognition, evidence, state, and independently valid work that can remain safe.

## Implemented boundary

Phase 4 includes:

- immutable runtime-bound path policy;
- host-derived default NEVER roots;
- cumulative user-defined NEVER roots;
- deterministic represented-path normalization;
- structured path-tool authorization;
- bounded recognized Bash and PowerShell command authorization;
- non-stream tool-call release authorization;
- streaming tool-call release authorization;
- executor admission enforcement;
- multi-call minimum containment;
- Windows trailing-dot and trailing-space alias closure;
- NTFS stream-owner policy comparison;
- current-drive-rooted Windows path handling;
- PowerShell `FileSystem::` qualification;
- deliberate exclusion of deterministic non-filesystem PowerShell providers from Phase-4 filesystem authority.

## Authority rules

- Positive deterministic NEVER target -> `HARD_INTERRUPT`.
- Explicit Workspace Lock plus deterministic outside filesystem target -> `DENY_AND_CONTINUE`.
- Workspace denial preserves safe cognition and unrelated valid work.
- No configured workspace -> no invented workspace denial.
- Positive NEVER authority outranks workspace permission.
- Ambiguity alone does not become a hard-security violation.
- Caller/model content cannot relax host-owned path policy.

## Slice 10 closure

Slice 10 closed representation gaps involving:

- ordinary Win32 trailing-dot/trailing-space aliases;
- NTFS alternate-stream owner comparison;
- current-drive-rooted Windows paths when executor drive is known;
- PowerShell `FileSystem::` and module-qualified FileSystem syntax.

It also prevents over-hardening:

- pathless commands such as `Get-Process` remain usable;
- Registry and other deterministic non-filesystem PowerShell providers remain outside Phase-4 filesystem authority;
- an absolute in-workspace target is not rejected merely because incidental cwd is outside the workspace;
- relative and cwd-scoped filesystem work remains subject to Workspace Lock;
- cwd-dependent commands such as `git status` remain workspace-scoped.

## Path Resolution Gap

Phase 4 authorizes the represented target Jack can deterministically observe.

It does not claim final-object filesystem attestation.

`RepresentedPath != NecessarilyResolvedObject`

Symlinks, junctions, reparse points, mounts, hard-link relationships, and descriptor-level resolution remain executor/OS-boundary concerns.

## Validation evidence

- Targeted Phase-4/Slice-10 gate: **201/201 PASS**
- Full Python suite: **376/376 PASS**
- Pi harnesses: **7/7 PASS**
- `git diff --check`: **PASS**
- Implementation freeze working tree: **clean**

## Exact implementation identities

- `Pi/jack-kernel.ts` — `1C2E99BAEFF69E3FACD6495FA392EAC2FD2C54A7A8DD02468D6A29DBC21C8D5F`
- `jack_evidence_guard.py` — `2B205A702FCF5782F529FD2132A69F819FB8FAE54A4DCEDDD5A4380BA466D594`
- `jack_kernel.py` — `08AF835368E0723AA825334DDC0FBA46BFD0BA1DFB0B3E073014FACD7152DDB6`
- `jack_path_policy.py` — `B44E998ECF57CBED49A25DBE119F4AD79050EBE188241409F49BBDAF43DA7BDA`
- `jack_responses_compat.py` — `C05BFC0A311E70252A0CC904DC4AF2E30958FD63A2BFE101722295E166AFEBDC`
- `tests/pi_phase4_executor_admission_harness.mjs` — `ACD1E369C49103A375B4BC67012FD192B997C6A413BD37D9B26E6B69D5C21470`
- `tests/pi_provider_runtime_binding_harness.mjs` — `9879A636776CE100E7EB67F50264725178F8D515252DBF202B14C08580998F4E`
- `tests/test_phase4_command_contract.py` — `28AF1914E04E7235119EB733DFE9710C2C2401C1FF07AC0878B5A933E59351AF`
- `tests/test_phase4_executor_admission.py` — `6283FCE8C0C69B487C1842424B50720DF01E2697C5A8FB0570687E7A47E24DF8`
- `tests/test_phase4_final_audit.py` — `954F17DD5D7267656D6ED48F883B0B2F13E61A483B1BE591C48ECF6A35062F9E`
- `tests/test_phase4_multicall_containment.py` — `1075D9C07A8185D8F39A32E556710BC276E7CE7D9F0912BF4F5B4AC26A2F9685`
- `tests/test_phase4_nonstream_authorization.py` — `7AC43202777D2D9C7B4D26D43E6E867F734978B6D4F8D18F40337F8A57DCCB99`
- `tests/test_phase4_path_policy.py` — `FA91C9981207A7568D1DE9F154FCB5B1A230A4703F0E6377520390B6DBB06779`
- `tests/test_phase4_runtime_binding.py` — `942FEAFE294EDD95064A4EE039FAFA0D7D6B87C16EEB7AC29AE72BAE95DE1027`
- `tests/test_phase4_slice10_closure.py` — `3F2C9B5FBD9C96C7491FB5AFC45365653669BF0CD8AE1F42525A9E5F3E541DC7`
- `tests/test_phase4_streaming_release.py` — `263A4D5C3C6E94351799DE70855E9FD08224C0FEBF0FD7D9F26F2B7C687238AB`
- `tests/test_surgical_regressions.py` — `0896B01CA6F5F4F5E4C5BDED56B46B06CE23FB228B0DF23BFC27B007338FD751`

## Historical chain

The earlier Phase 0-3 checkpoint and tag remain immutable historical evidence.

Phase 4 is cumulative and does not retroactively rewrite the earlier validation boundary.

## Explicitly unclaimed

This checkpoint does not claim:

- universal filesystem sandboxing;
- object-level symlink/junction/reparse-point confinement;
- complete generalized Consequence Gate coverage;
- complete credential isolation or DLP;
- Source Drift Guard;
- Runtime Code Integrity Guard;
- Authority State Integrity Guard;
- remote attestation;
- global cross-process security-state serialization.
