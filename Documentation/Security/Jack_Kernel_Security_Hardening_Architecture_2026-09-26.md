# Implementation Status Update — 30 September 2026

This status update is additive. Every earlier status note and the complete Security Hardening Architecture remain preserved below.

**Validated / implemented through Phase 4:**

- Phase 0 reality and authority mapping
- deterministic `SecurityOutcome` semantics
- StreamingIRQ bounded pre-release quarantine
- malformed-SSE release-barrier correction
- deterministic Canary enforcement
- immutable runtime/lane-bound Canary policy
- Restricted Paths
- optional Workspace Lock
- non-stream and streaming represented-target enforcement
- executor admission
- bounded recognized Bash/PowerShell command authorization
- multi-call minimum containment
- Slice-10 Windows/PowerShell representation closure

**Phase-4 implementation freeze:** `0e897b801d5b5da8d604cf21556b40da769c26fe`

**Checkpoint tag:** `security-layer-phase4-validated-2026-09-30` (target: `0c15331d4673412befc626b64d7c4e52f7018fb4`)

**Regression state:** 201 targeted Phase-4 tests; 376 full Python tests; seven Pi harnesses; `git diff --check` PASS.

Deterministic NEVER matches remain hard security. Ordinary outside-workspace consequences are denied while safe cognition is preserved. Lack of universal knowledge about unrelated execution semantics is not itself a security violation.

The Path Resolution Gap remains explicit: represented-target authorization does not prove the final object resolved by an external executor or operating system.

Earlier prospective Phase-4 design sections remain preserved below as design provenance.

---

# Implementation Status Update — 27 September 2026

This repository copy preserves the full Security Hardening Architecture design paper below and adds this implementation-status note rather than rewriting the design history.

**Validated / implemented through Phase 3:**
- Phase 0 reality and authority mapping
- deterministic SecurityOutcome semantics
- StreamingIRQ bounded pre-release quarantine
- malformed-SSE release-barrier correction
- deterministic Canary matcher/detection/enforcement
- immutable runtime/lane-bound Canary policy
- static Tier A/B startup activation

**Validated checkpoint:** `9dda35a358baf2814102dcb9c45346116271acfc`  
**Checkpoint tag:** `security-layer-phase0-3-validated-2026-09-27`  
**Regression state:** 175 Python tests passed; six Pi harnesses passed.

**Next authorized layer:** Phase 4 — Restricted Paths + Workspace Lock.

The design sections describing later layers remain prospective until separately implemented, tested, documented, and checkpointed. Nothing in this status note deletes or silently rewrites the original architecture paper.

---

# Jack Kernel Security Hardening Architecture
## Deterministic Security Without Brittleness at the Agent–Model Boundary

**Status:** Technical Design Paper  
**Project:** Jack Kernel  
**Scope:** Jack Kernel only  
**Date:** September 25, 2026

---

## Abstract

Jack Kernel is a local-first, host-authoritative inference mediation and control runtime positioned between an agent or client and an OpenAI-compatible probabilistic model backend. It is not itself the autonomous worker, filesystem executor, browser, sandbox, or general-purpose build environment. Its role is to govern the boundary through which probabilistic cognition becomes visible, attributable, authorized, or consequential. The current Kernel already owns request authority, backend/model authority, inference controls, context projection, tool exposure, tool-call validation, stage authority, runtime identity, evidence provenance, orchestration mediation, and Kernel persistence.

Its governing law is:

> **Probabilistic cognition may propose, but deterministic software must dispose.**

This paper defines a security hardening architecture that deepens that principle while introducing an equally important second requirement:

> **Security must not make Jack brittle.**

A secure Kernel that routinely destroys valid cognition, discards useful work, or terminates sessions because of harmless irregularities is not a successful security system. Jack must fail closed when actual authority, identity, evidence, secrets, protected resources, or Kernel integrity are violated, while preserving recoverable cognition and legitimate work whenever the security invariant remains intact. This formalizes and extends an existing Jack principle: **fail closed on authority; fail soft on non-authoritative observability and recoverable cognition.**

The proposed hardening architecture therefore combines nine complementary Kernel-native security areas:

1. **StreamingIRQ with a configurable pre-release quarantine window**
2. **Three-tier Canary Tokens**
3. **Restricted Path Enforcement**
4. **Optional Workspace Lock**
5. **A deterministic Consequence Gate**
6. **A Kernel-local Authority and Security Ledger**
7. **Kernel-scoped credential isolation**
8. **Kernel-visible DLP and telemetry/privacy controls**
9. **A three-part live-integrity architecture comprising Source Drift Guard, Runtime Code Integrity Guard, and Authority State Integrity Guard, with controlled versioned evolution for legitimate dynamic security state**

These mechanisms are unified by one operational rule:

> **Contain the violation at the narrowest boundary that preserves the security invariant.**

Jack should deny the unsafe consequence without destroying safe cognition whenever possible. Connection severance and runtime termination are reserved for genuine hard-security failures.

---

# 1. Jack Kernel's Actual Security Boundary

Jack Kernel sits between an agent/client and an OpenAI-compatible model backend. Its present architecture already separates caller-visible virtual model identity from actual backend identity, reconstructs agent requests through an explicit authority allowlist, strips caller `system` and `developer` messages from hidden authority, controls stage-specific tool exposure, validates tool-call structure, and protects a host-owned evidence namespace.

The current system also distinguishes runtime identity from transport location, tracks identities such as:

```text
runtime_id
lane_id
bridge_id
task_id
run_id
run_epoch
sessionInstanceId
```

and treats cancellation, settlement, transport disconnect, and observability as separate facts rather than collapsing them into one state.

Security hardening must preserve those distinctions.

The governing placement rule is:

> **A security mechanism belongs inside Jack Kernel only when Jack possesses the information needed to make the decision and the authority needed to enforce that decision.**

This is why StreamingIRQ belongs inside the Kernel: Jack physically receives the model stream before forwarding it.

It is also why a textual path authorization check belongs inside the Kernel: a structured path argument may pass directly through Jack before the tool call is released.

But the Kernel does not thereby acquire possession of the filesystem object eventually opened by an external executor.

The distinction is:

```text
what Jack sees
    !=
what the operating system ultimately resolves
```

That boundary must remain explicit throughout this architecture.

---

# 2. Security Without Brittleness

Security controls have four possible outcomes.

## 2.1 ALLOW

The request is valid, authorized, and may proceed.

## 2.2 DENY AND CONTINUE

The proposed action is not authorized, but nothing indicates that the broader cognition or session has become unsafe.

Examples include:

- a malformed tool call;
- a tool unavailable to the current stage;
- an ordinary request outside an optional workspace;
- a recoverable schema error;
- a request whose structured target is not permitted but does not constitute a hard security breach.

Jack rejects only the unsafe action and preserves useful work.

## 2.3 REQUIRE USER DECISION

Jack has insufficient authority to decide automatically, or policy intentionally requires human approval.

The current cognition and state are preserved while the consequential action is withheld.

## 2.4 HARD INTERRUPT

A deterministic security invariant has been violated.

Examples include:

- a confirmed secret canary in unreleased model output;
- forged host-owned evidence;
- a confirmed target inside a path declared **NEVER accessible**;
- Kernel runtime-code integrity compromise;
- Kernel authority-policy integrity compromise;
- unauthorized mutation of protected security state;
- direct Kernel security-policy tampering;
- confirmed exposure of Kernel-owned credentials.

A hard interrupt withholds the unsafe material or action and severs the affected security boundary.

This gives Jack a fundamental rule:

> **Do not destroy more state than the violation requires.**

A bad tool call does not invalidate a good analysis.

An out-of-workspace request does not automatically invalidate a whole reasoning trajectory.

Telemetry failure does not invalidate cognition.

A genuine Kernel-integrity violation does.

## 2.5 Preservation Requirement

The anti-brittleness rule is not merely advisory. It is an acceptance condition for the security architecture:

> **Jack must preserve all useful cognition and state that can be preserved without weakening the violated security invariant.**

Containment should therefore escalate only as far as necessary:

```text
1. Reject only the proposed consequence
        ↓ if insufficient
2. Withhold only the affected output span / tool call
        ↓ if insufficient
3. Invalidate only the affected run/security scope
        ↓ if insufficient
4. Sever only the affected connection
        ↓ only when Kernel authority itself cannot be trusted
5. Terminate or make inert the Kernel runtime
```

Every security feature must be tested in both directions:

> **Did Jack stop the unsafe thing?**

and:

> **Did Jack preserve everything that remained safe and useful?**

A phase fails if it permits a defined security violation **or** if it unnecessarily destroys valid cognition, valid state, unrelated work, or recoverable progress.

---

# 3. Security-State Precedence

Security state outranks cognitive utility.

If valuable model output conflicts with a deterministic hard-security invariant, the invariant wins.

Formally:

\[
SecurityInvariant > CognitiveUtility
\]

But this must not be misinterpreted as:

\[
AnyIrregularity = SecurityViolation
\]

That distinction is what prevents Jack from becoming brittle.

For example:

```text
useful reasoning
+
malformed tool JSON
=
preserve reasoning, reject tool call
```

while:

```text
useful reasoning
+
confirmed Kernel canary leak
=
withhold unsafe stream, hard interrupt
```

and:

```text
excellent analysis
+
live authority function replaced in memory
=
terminate Kernel authority
```

and:

```text
unchanged authority code
+
protected NEVER-path policy silently weakened
=
authority-state integrity failure
```

The Kernel should be severe only when the evidence warrants severity.

---

# 4. StreamingIRQ

StreamingIRQ is the primary release-boundary security mechanism.

Its purpose is to prevent protected information from crossing the model-to-caller boundary before Jack has had an opportunity to validate it.

The architecture is:

```text
MODEL BACKEND
      │
      ▼
probabilistic stream
      │
      ▼
┌───────────────────────────────┐
│        STREAMING IRQ          │
│                               │
│ unreleased quarantine         │
│ normalization                 │
│ canary detection              │
│ DLP                           │
│ evidence-namespace protection │
└───────────────┬───────────────┘
                │
        ┌───────┴────────┐
        ▼                ▼
      RELEASE       HARD INTERRUPT
```

The crucial property is **pre-release enforcement**.

Post-processing can discover a leak after it has happened.

StreamingIRQ instead holds enough of the stream that a defined protected condition can be detected before the relevant protected span becomes visible downstream.

The earlier security design correctly identified this as a Kernel-native boundary because Jack physically occupies the path between model generation and caller release.

---

# 5. Configurable Quarantine Window

The historical 256-character value is not an architectural constant.

The actual invariant is:

> **Jack retains enough unreleased stream state to detect a configured violation before the protected span can be released.**

The window should therefore be configurable or policy-derived within bounded limits.

Factors include:

- maximum protected-pattern length;
- canary length;
- encoding and normalization behavior;
- backend chunking;
- stream channel type;
- latency tolerance;
- memory limits.

The policy must have a hard ceiling.

A pathological configuration must not be permitted to convert the security mechanism into an unbounded buffering or latency problem. The earlier security design already established that 256 characters is an implementation precedent rather than a defining invariant.

StreamingIRQ must also be careful not to treat weak suspicions as hard violations.

A partial match that later proves benign should simply clear and release.

Only a configured hard condition should trigger severance.

---

# 6. Three-Tier Canary Tokens

Canaries provide deterministic evidence that protected state escaped its intended boundary.

Jack should support three classes.

### Tier A - Kernel Canaries

These protect state owned by Jack itself, including Kernel credentials, private security metadata, bridge secrets, and other Kernel-owned sensitive values.

### Tier B - User Canaries

The user may register deployment-specific protected values or markers.

### Tier C - Dynamic Run Canaries

Jack may create ephemeral markers bound to a specific runtime context, for example:

```text
task_id
run_id
run_epoch
session
evidence epoch
protected context
```

Positive identity tells Jack:

> Who owns this state?

Canaries answer:

> Did that state escape the boundary that owned it?

These two forms of evidence complement one another.

A confirmed Canary match is a hard security event.

Jack does not send the match back to the model and ask it to try again.

---

# 7. Restricted Path Enforcement

Jack should maintain a default set of operating-system-critical paths that model- or agent-authored consequential requests must never target.

The user may add additional paths designated:

> **NEVER ACCESS**

For a Windows-oriented release, the default policy may cover categories such as:

```text
Windows system directories
System32
SysWOW64
WinSxS
Boot
Recovery
System Volume Information
boot / EFI resources where identifiable
```

The exact defaults should be generated from the host environment rather than assuming every system has identical drive layout.

User-defined additions are cumulative.

A model or agent cannot remove them through normal inference.

---

# 8. What Restricted Path Enforcement Actually Proves

This mechanism must be described precisely.

Jack can inspect the **represented target** contained in a request it can see.

It can ask:

> Is the path the model or agent is asking for inside a prohibited root?

It cannot prove:

> What filesystem object will an external executor ultimately open?

For example:

```text
C:\Users\Project\data.txt
```

may textually appear safe while the operating system later resolves part of the path through:

```text
junction
symlink
reparse point
mount
hard-link relationship
```

to a protected object.

Therefore Restricted Path Enforcement is a real Kernel security layer, but it is a **request-target authorization control**, not physical filesystem attestation.

Its known limitation should be explicitly named:

## The Path Resolution Gap

\[
RepresentedPath \neq NecessarilyResolvedObject
\]

This is not a weakness to hide.

It defines the exact property Jack can enforce.

The mechanism remains valuable because naive and direct attempts to target protected resources are stopped before release, but the paper must not claim that textual normalization is equivalent to descriptor-level filesystem security.

---

# 9. Path Normalization

Before applying path policy, Jack should normalize what it can deterministically normalize.

Examples include:

```text
case normalization on Windows
slash normalization
"." and ".." collapse
known Windows path prefixes
environment-variable expansion where safely deterministic
quoted structured path values
drive normalization
```

The aim is to prevent trivial textual bypasses such as:

```text
C:\Windows\System32
C:\Windows\Temp\..\System32
c:/windows/system32
```

from being treated as unrelated targets.

However, if Jack cannot deterministically extract a path from an opaque free-form command, it should not pretend that it has perfectly reconstructed the command's eventual filesystem effects.

Ambiguity should result in denial of that action or user approval where policy requires it, not invented certainty.

---

# 10. NEVER Paths Versus Ordinary Policy Denials

A confirmed attempt to target a path explicitly designated **NEVER accessible** is a hard security event.

That is stronger than an ordinary policy denial.

```text
confirmed NEVER-path target
        ↓
withhold action
        ↓
record security event
        ↓
close affected connection
```

Because the policy is explicit, the model should not receive:

> "That path is blocked. Try another technique."

That would turn a hard boundary into a probing interface.

The system should nevertheless avoid brittleness by requiring a **positive deterministic match** before escalating.

An ambiguous parse is not the same as a confirmed NEVER-path access attempt.

---

# 11. Optional Workspace Lock

A user may optionally define one workspace root.

If no workspace is configured, normal Jack behavior applies subject to NEVER paths and other security policy.

If a workspace is configured:

\[
AllowedTarget =
InsideWorkspace
\land
\neg RestrictedPath
\]

Thus:

```text
inside workspace      → potentially allowed
outside workspace     → denied
inside NEVER path     → hard denied
```

The Workspace Lock does not need to be more complicated than that.

It exists for users who want Jack-mediated activity restricted to a particular project or exposed working directory.

---

# 12. Workspace Denials Should Usually Be Recoverable

Workspace Lock exists primarily as an authorization boundary, not an intrusion detector.

Therefore an ordinary request outside the workspace should usually be:

```text
DENY AND CONTINUE
```

rather than:

```text
HARD INTERRUPT
```

A model can misunderstand a project layout.

A tool may produce a stale path.

A relative path may resolve outside the declared root.

Those conditions do not automatically mean the entire cognitive session is unsafe.

Jack should reject the action, preserve the reasoning, and continue.

Repeated deliberate probing may be escalated according to policy, but the default behavior should preserve legitimate work.

This is one of the clearest examples of **security without brittleness**.

---

# 13. Deterministic Consequence Gate

The Consequence Gate is the generalized authorization boundary through which model-authored consequential requests must pass.

The Kernel is well positioned to decide facts such as:

- Does this stage possess the required tool authority?
- Does the active task/run/epoch own this request?
- Is the represented target prohibited?
- Is the represented target outside the active workspace?
- Does the requested effect require explicit user approval?
- Is required evidence current and correctly sourced?
- Has this authorization already been consumed or settled?
- Is the Kernel currently in a healthy security state?

The earlier security design already identified these as legitimate Kernel-level decisions while warning against having the Kernel claim authority over physical facts it does not possess.

The Gate returns:

```text
ALLOW
DENY_AND_CONTINUE
REQUIRE_USER_DECISION
HARD_INTERRUPT
```

The fourth state is reserved for actual hard-security conditions.

---

# 14. Evidence May Establish Facts; Policy Disposes

Evidence should inform the Consequence Gate without becoming authority itself.

This principle remains:

> **Evidence may establish facts. Deterministic policy disposes of those facts.**

Jack already maintains a host-owned evidence namespace and prevents ordinary model output from impersonating that namespace. It distinguishes evidence origin such as:

```text
caller_supplied_tool_result
pi_session_recovery
host_internal
unknown
```

and keeps provenance separate from arbitrary strings inside tool payloads.

The hardened Consequence Gate should build on that boundary.

A payload that says:

```text
"verified": true
```

does not become verified evidence merely because the text claims it is.

---

# 15. Kernel Authority and Security Ledger

The historical Jack WAL concept contains an important idea worth transferring:

> Critical authority state should not depend on model memory.

Jack Kernel should therefore maintain a durable ledger for events Jack itself owns.

Representative records include:

```text
AUTHORIZATION_GRANTED
AUTHORIZATION_DENIED
USER_APPROVAL_REQUIRED

CANARY_MATCH
STREAM_HARD_INTERRUPT

RESTRICTED_PATH_ATTEMPT
WORKSPACE_DENIED

SOURCE_DRIFT_DETECTED
RUNTIME_INTEGRITY_COMPROMISED
AUTHORITY_POLICY_INTEGRITY_COMPROMISED
UNAUTHORIZED_SECURITY_STATE_TRANSITION

TASK_BOUND
RUN_BOUND
RUN_EPOCH_CHANGED

SECURITY_STATE_TRANSITION
SECURITY_STATE_VERSION_ADVANCED

CANCELLATION_REQUESTED
SETTLEMENT_OBSERVED

EVIDENCE_ACCEPTED
EVIDENCE_REJECTED
```

The previous security design correctly limited this ledger to Kernel-owned authority and lifecycle facts rather than turning Jack into a universal filesystem transaction system.

The ledger should help Jack preserve state, not make Jack punitive.

A rejected action can be recorded without discarding the rest of the run.

For controlled dynamic security state, the ledger should also preserve the relationship between successive authorized security-state versions.

Conceptually:

```text
previous_state_digest
transition_type
new_state_digest
new_state_version
task_id / run_id / run_epoch where applicable
```

This does not make the ledger the authority that permits mutation. The transition function does that.

The ledger records that the transition occurred under Kernel authority.

## 15.1 Runtime-Scoped Authority Chains

In a multi-endpoint deployment, the Authority and Security Ledger is **logically Kernel-wide but physically and authoritatively runtime-scoped**.

Each Jack runtime maintains its own ledger namespace and ledger head, bound to its positive `lane_id` / `runtime_id` identity.

```text
runtime A
    ledger namespace A
    head A
    version A

runtime B
    ledger namespace B
    head B
    version B

runtime C
    ledger namespace C
    head C
    version C
```

A runtime may append only to its own authoritative chain.

The architecture does not rely on one mutable ledger head shared implicitly across Jack processes.

The governing invariant is:

> **A ledger head is mutable authority state belonging to one runtime namespace. No Jack process may directly advance another runtime's ledger head.**

This preserves the process-isolation model used by Jack's multi-endpoint lanes and avoids reintroducing cross-process mutable authority state through the ledger.

A unified audit view does not require a unified mutable head.

```text
lane A ledger
lane B ledger
lane C ledger
      │
      ▼
read-only aggregation / forensic view
```

A unified forensic view may aggregate events from multiple runtime-scoped ledgers, but aggregation does not acquire authority to rewrite, reorder, or advance the underlying chains.

For the runtime-scoped extension, authoritative ledger records should additionally bind:

```text
lane_id
runtime_id
previous_state_digest
transition_type
new_state_digest
new_state_version
task_id
run_id
run_epoch
```

Task/run fields may be null where no task exists, but `runtime_id` is not optional because it defines the authoritative ledger namespace.

# 16. Kernel Credential Isolation

Jack should custody only secrets that genuinely belong to Jack Kernel.

Examples include:

```text
backend authentication credentials
Jack API credentials
private bridge credentials
Kernel-managed service credentials
```

Where practical, model cognition should operate on logical references rather than plaintext values.

The preferred pattern is:

```text
cognition references credential X
            ↓
Jack resolves X at last responsible moment
            ↓
credential used only in authorized transport
            ↓
transient representation discarded where practical
```

This maintains the original design intent while respecting modern Kernel boundaries.

Kernel credentials should integrate with Tier-A canaries so custody and leakage detection reinforce one another.

---

# 17. Kernel-Visible DLP

DLP belongs in Jack only for information Jack actually sees.

Relevant surfaces include:

```text
model output
tool calls passing through Jack
tool results passing through Jack
evidence receipts
orchestration payloads passing through Jack
Kernel diagnostics exposed externally
```

For streaming output, DLP should be integrated directly into StreamingIRQ.

The architecture should not be:

```text
release output
then scan it
```

It should be:

```text
scan while unreleased
then decide whether release is permitted
```

The previous design explicitly identifies Kernel-visible DLP as distinct from physical artifact inspection outside the Kernel.

---

# 18. Telemetry and Privacy Control

Jack's own diagnostics can become an information channel.

A strict privacy policy should therefore govern:

```text
external callbacks
model-visible infrastructure details
stack traces
forensic archive content
backend diagnostics
runtime metadata
nonessential error payloads
```

The objective is not to eliminate local diagnostics.

The distinction is:

```text
LOCAL FORENSIC INFORMATION
    available under host policy

EXTERNAL / MODEL-VISIBLE INFORMATION
    minimized and controlled
```

This mirrors the original proposed telemetry/privacy boundary.

Telemetry itself remains non-authoritative.

A telemetry failure should not kill safe cognition.

---

# 19. Kernel Integrity: Three Different Problems

The earlier draft incorrectly treated one disk-hashing mechanism as though it proved live interpreter integrity.

It does not.

The revised architecture separates three distinct properties.

## 19.1 Source Stability

Did the source tree from which this active Kernel was launched change while Jack remained active?

## 19.2 Runtime Code Integrity

Did the authority-bearing Python modules, function bindings, or code objects currently executing inside Jack's interpreter change after the Kernel began serving?

## 19.3 Authority State Integrity

Did the protected policy data consumed by otherwise unchanged authority code change outside an explicitly authorized Kernel transition?

These are different threats.

They require different checks.

A Kernel may have perfectly unchanged source files and perfectly unchanged function bytecode while its effective security behavior has still been weakened through mutation of the policy data those functions consult.

For example:

```python
RESTRICTED_PATHS.remove(r"C:\Windows\System32")
```

could alter enforcement behavior without changing:

```text
jack_kernel.py
function identity
function.__code__
```

Likewise, deleting a Tier-B Canary or weakening a quarantine limit in an ordinary mutable dictionary could change real authority behavior while every code-integrity test remained green.

Therefore Jack must protect:

```text
source
+
executing authority code
+
authority-bearing policy/state
```

rather than treating code integrity alone as complete runtime integrity.

---

# 20. Live Source Drift Guard

At startup, Jack records cryptographic hashes of its own authority-bearing source files.

Only Jack Kernel files should be included.

The source of another process is not part of Jack's runtime-integrity boundary.

The precise monitored set should be derived from the current implementation, but candidates include:

```text
jack_kernel.py
jack_evidence_guard.py
jack_responses_compat.py
jack_secure_entrypoint.py where relevant to active launch integrity
```

The operational invariant is:

> **The source tree used to start an active Jack Kernel runtime must remain stable for the lifetime of that runtime.**

This is not a claim that changing the file automatically changes the already-imported Python process.

In the current Kernel architecture, Jack launches as a normal Uvicorn process and does not rely on development hot-reload. Therefore modifying an imported `.py` file on disk generally changes the next execution of Jack, not the already-loaded code in the current interpreter.

The Source Drift Guard therefore detects:

```text
source tree changed during active runtime
```

not:

```text
running Python function necessarily changed
```

That distinction is mandatory.

---

# 21. Why Source Drift Still Matters

Even though disk modification does not normally mutate already-imported code, source drift during an active secure runtime is undesirable.

It creates uncertainty about:

- what a subsequent spawned process would execute;
- what future lazy imports might load;
- what code a crash/restart would immediately pick up;
- whether the active runtime's source of record still matches its startup state;
- whether a user or process is modifying security code during active operation.

Jack therefore treats confirmed source drift in protected Kernel files as a live-integrity event.

The user remains free to modify the Kernel while Jack is stopped.

The lifecycle is:

```text
Jack OFF
    source editing permitted

Jack STARTS
    source baseline established

Jack RUNNING
    protected source expected stable

Jack STOPS
    source editing permitted again
```

This satisfies the development requirement without requiring a permanent static release seal.

---

# 22. Live Runtime Code Integrity Guard

A stronger protection is needed to detect changes to the authority implementation actually loaded in memory.

After Jack loads its runtime modules and installs its authority/security extensions, but before public service becomes available, Jack should establish an in-memory baseline for selected authority-bearing Python objects.

That code baseline should include:

```text
module object identity
critical function object identity
critical code-object fingerprint
```

For a critical callable \(F\), conceptually:

\[
RuntimeDigest(F) = H(SerializedCodeObject(F))
\]

A practical implementation could use a stable-in-process representation of `function.__code__`, potentially including the bytecode and selected code metadata, or an in-process serialization such as:

```python
marshal.dumps(function.__code__)
```

where appropriate.

The exact representation should be tested for the supported Python version rather than treated as an abstract guarantee.

Runtime code integrity and authority-state integrity should remain separate checks.

The runtime-code baseline proves things about loaded executable authority.

The authority-state baseline proves things about the policy data that executable authority consumes.

Neither substitutes for the other.

---

# 23. Runtime Rebinding Detection

A code fingerprint alone is insufficient if the module attribute is replaced with an entirely different function.

Jack should therefore also retain original object references.

For selected authority functions:

```text
original_function_reference
original_code_digest
```

and verify:

```text
module.function is original_function_reference
```

plus:

```text
digest(module.function.__code__) == startup_digest
```

This detects ordinary runtime events such as:

```python
jack_kernel.some_authority_function = replacement
```

or:

```python
jack_evidence_guard.some_guard = bypass
```

as well as many reload/rebinding scenarios.

The two checks are intentionally complementary.

Object-identity checking catches replacement of the module binding.

Code-object measurement catches mutation of the code underlying the originally captured function.

A robust Runtime Code Integrity Guard should therefore not rely on only one of them.

---

# 23A. Authority Policy Integrity Guard

Authority functions are only as strong as the policy data they read.

Jack must therefore distinguish between:

```text
authority code
```

and:

```text
authority data
```

A function can remain completely untouched while enforcement behavior changes because its policy structures were silently altered.

Examples include:

```text
removing a NEVER path
deleting a Tier-B Canary
weakening a hard DLP signature set
raising or disabling a quarantine safety bound
changing a hard-interrupt classification
replacing the active workspace boundary
disabling a security feature during an active authority scope
```

These are security-significant changes even if:

```text
function identity is unchanged
and
function code digest is unchanged
```

The static authority policy for an active scope should therefore be projected into an immutable runtime representation.

The preferred lifecycle is:

```text
mutable configuration input
        ↓
validation
        ↓
normalization
        ↓
canonicalization
        ↓
construction of fresh immutable security snapshot
        ↓
discard mutable construction references
        ↓
bind snapshot to active authority scope
```

Appropriate immutable structures may include:

```text
tuple
frozenset
frozen dataclass
deeply immutable nested structures
read-only mapping constructed from a private copied dictionary
```

A simple `MappingProxyType` around a dictionary is not by itself sufficient if another live reference to the underlying mutable dictionary remains available.

Therefore the implementation should not merely wrap shared mutable state.

It should construct a fresh protected representation whose mutable source objects are no longer authoritative.

---

# 23B. Canonical Authority-Policy Measurement

Immutability prevents ordinary mutation attempts from succeeding through the expected references.

Measurement provides a second independent check.

At establishment of an authority scope:

\[
PolicyDigest = H(CanonicalSecurityPolicy)
\]

The canonical representation must avoid unstable or incidental Python representations.

It should use deterministic normalization rules such as:

```text
explicit field names
stable encoding
normalized filesystem paths
sorted representation of unordered sets
canonical booleans and numeric fields
no object memory addresses
no default repr() output
no ordering derived from unrelated insertion history
```

The active integrity baseline should therefore include:

```text
protected policy snapshot identity
+
canonical policy digest
```

Conceptually:

```text
AuthorityPolicyBaseline
    snapshot_reference
    canonical_digest
    policy_version
```

An unauthorized replacement such as:

```python
jack_kernel.SECURITY_POLICY = weakened_policy
```

should fail the identity expectation.

A successful mutation of some improperly retained nested mutable value should fail the canonical digest expectation.

As with function identity plus code-object digest, the two checks cover different failure modes.

---

# 23C. Static Policy Versus Dynamic Security State

Not every security value is supposed to remain unchanged.

Jack must not become brittle by treating legitimate runtime evolution as tampering.

Security state therefore divides into two categories.

### Static or Scope-Frozen Authority Policy

Examples include:

```text
default NEVER paths
user-defined NEVER paths
Tier-B user Canary definitions
hard DLP signatures
security outcome classification policy
quarantine hard ceilings
security feature enable/disable flags
host-selected workspace policy for the active scope
other host-authoritative hard policy
```

These should remain immutable for the authority scope in which they were established.

### Legitimately Dynamic Security State

Examples include:

```text
Tier-C run/session Canaries
current task_id
current run_id
run_epoch
approval state
security event counters
ledger chain head
active transaction state
settlement state
run-scoped security epoch
```

These values are expected to change.

They must therefore not simply be frozen forever.

Instead, Jack should control how they are allowed to change.

## 23C.1 Concurrency Domain Is Part of Security-State Classification

For every security-relevant state field, classification must identify not only whether the field is static or dynamic, but also:

```text
1. mutability class
2. owning authority
3. concurrency scope
```

The current multi-endpoint architecture uses process isolation for mutable Jack state. Accordingly, task/run/epoch state and the authoritative ledger head are runtime-scoped unless a future design explicitly promotes them to a shared cross-process authority domain.

A representative classification is:

| State | Mutability | Authority | Concurrency scope |
|---|---|---|---|
| NEVER paths | Frozen | Host/runtime policy | Runtime |
| Tier-B canaries | Frozen | Host/runtime policy | Runtime |
| Tier-C canaries | Dynamic | Kernel transition | Runtime/run |
| `task_id` | Dynamic | Lifecycle authority | Runtime |
| `run_id` | Dynamic | Lifecycle authority | Runtime |
| `run_epoch` | Dynamic | Lifecycle authority | Runtime |
| Approval state | Dynamic | Consequence Gate | Runtime/run |
| Settlement state | Dynamic | Lifecycle authority | Runtime/run |
| Ledger namespace identity | Frozen | Runtime identity | Runtime |
| Ledger head | Dynamic | Ledger append authority | **Runtime** |
| Ledger sequence/version | Dynamic | Ledger append authority | **Runtime** |

This classification prevents an in-process transition protocol from being silently relied upon for state that actually has multiple concurrent writers.

---

# 23D. Controlled Dynamic Security State

Dynamic security state should evolve only through explicit Kernel-owned transition functions.

The preferred pattern is copy-on-write immutable snapshots rather than arbitrary in-place mutation.

Conceptually:

```text
SecurityState v17
        │
        │ authorized Kernel transition
        ▼
SecurityState v18
```

rather than:

```python
security_state.dynamic_canaries.append(value)
```

Each new state should be built from the prior state through a validated transition.

A conceptual state object may contain:

```text
version
task_id
run_id
run_epoch
dynamic_canaries
approval_state
security_event_state
ledger_head
other explicitly dynamic fields
```

An authorized transition should:

```text
validate the requested transition
verify current state/version
construct a new immutable state snapshot
advance the version
calculate the new canonical digest
replace the active state reference
record the transition in the Kernel Authority Ledger
```

Conceptually:

\[
State_{n+1}
=
AuthorizedTransition(State_n, Event_n)
\]

and:

\[
Digest_{n+1}
=
H(Canonical(State_{n+1}))
\]

This allows legitimate state evolution without opening a generic mutation surface.

## 23D.1 Concurrency-Domain Atomicity

The predecessor check and state installation must be atomic within the state object's declared concurrency domain.

For the current Jack multi-endpoint architecture, task/run/epoch state and the authoritative ledger head are runtime-process scoped, so their transition primitive is required to be atomic within one Jack process, not across all Jack processes.

If a future design intentionally promotes an authority-bearing state object to shared cross-process scope, ordinary in-process replacement is no longer sufficient. That state must acquire an explicit cross-process coordination primitive before it may become authoritative.

Acceptable future coordination mechanisms may include, depending on the storage and crash model:

```text
OS/file lock with defined crash semantics
database transaction / compare-and-swap
single-writer coordinator process
other proven atomic storage primitive
```

The governing concurrency rule is:

> **Never implement shared authority with check-then-act when the authority domain permits concurrent writers.**

This requirement does not justify adding cross-process machinery to runtime-scoped state that does not need it.

# 23E. Unauthorized Security-State Mutation

A dynamic security state being allowed to change does not mean arbitrary code may change it.

For example:

```text
legitimate:
    advance run_epoch through Kernel lifecycle authority

illegitimate:
    assign run_epoch directly to bypass ownership logic
```

or:

```text
legitimate:
    register Tier-C Canary through run initialization

illegitimate:
    delete active Canary directly from internal state
```

The Kernel should distinguish these through transition authority, not merely by asking whether the resulting value looks plausible.

If protected dynamic state changes without an authorized transition, the event should be classified as:

```text
UNAUTHORIZED_SECURITY_STATE_TRANSITION
```

or an equivalent hard-integrity condition.

The affected security boundary should fail closed.

---

# 23F. Authority State Integrity Invariant

The resulting invariant is:

> **Security behavior may not be altered by silently mutating the policy data consumed by unchanged authority code. Static security policy is projected into an immutable, measured runtime snapshot; dynamic security state may change only through explicit Kernel-owned, versioned transitions.**

This closes the policy-data gap without requiring Jack to freeze every piece of runtime state.

It also preserves the central non-brittleness principle:

> **Expected state evolution is not tampering. Unauthorized authority-state mutation is.**

---

# 24. Runtime or Authority Integrity Failure

Confirmed unexpected modification of a protected live authority object is a hard security event:

```text
RUNTIME_INTEGRITY_COMPROMISED
```

Confirmed unauthorized modification of protected authority policy is likewise a hard security event:

```text
AUTHORITY_POLICY_INTEGRITY_COMPROMISED
```

Confirmed unauthorized evolution of protected dynamic security state is also an integrity event:

```text
UNAUTHORIZED_SECURITY_STATE_TRANSITION
```

Jack should:

```text
withhold pending consequential release
stop accepting new requests where integrity can no longer be trusted
sever affected active inference connections
record minimal local forensic state where safe
terminate or enter an inert state when Kernel authority itself is compromised
```

Where the integrity failure is demonstrably limited to a narrower run/security scope and Kernel authority remains trustworthy, Jack should invalidate only that affected scope rather than discarding unrelated safe work.

This is one of the circumstances where aggressive failure is appropriate, but the containment level must still match the actual loss of trust.

A Kernel that has evidence that its own active authority implementation or authority-bearing policy has changed outside its permitted transition model should not continue exercising that compromised authority.

---

# 25. Limit of Self-Inspection

The paper must not overclaim what in-process integrity checking proves.

If an attacker obtains arbitrary code execution inside the same Python interpreter, that attacker may potentially modify:

```text
the protected function
the stored code baseline
the authority policy
the policy baseline
the dynamic state
the transition authority
the checker
the checker result
```

Therefore Jack's Live Runtime Integrity and Authority State Integrity Guards are valuable against:

- accidental monkey-patching;
- unexpected extension interference;
- ordinary function rebinding;
- code-object replacement;
- module reloads;
- ordinary unauthorized policy mutation;
- accidental mutable-state corruption;
- direct replacement of protected policy objects;
- unauthorized dynamic-state mutation;
- many forms of application-level runtime tampering.

They are not cryptographic remote attestation against an attacker with arbitrary memory control of the entire Jack process.

A stronger guarantee would require an external root of trust.

That is outside the scope of this Kernel upgrade.

Being precise about this limit strengthens the security claim rather than weakening it.

---

# 26. Integrity Without Brittleness

Only authority-bearing Kernel code and state should be monitored.

Jack should not terminate because:

```text
README.md changed
documentation changed
a test file changed
a temporary artifact changed
a log changed
an ordinary request-local object changed
telemetry state changed
a legitimate run transition advanced run_epoch
a legitimate Tier-C Canary was created
an approval state changed through its authorized transition
```

Those are not necessarily integrity violations.

Integrity monitoring should therefore operate over a narrow, deliberate protected set.

Static security policy should be frozen and measured.

Dynamic security state should be versioned and transitioned through explicit authority.

Ordinary application state should not be pulled into the security-integrity system merely because it happens to be mutable.

This avoids turning legitimate runtime behavior into unnecessary service destruction.

## 26.1 Multi-Runtime Preservation

Under the current multi-endpoint architecture, one runtime advancing its own authorized ledger head and another runtime advancing its independent ledger head are normal runtime-scoped state transitions, not cross-runtime integrity violations.

An event or denial confined to one runtime must not, by itself, invalidate another runtime's independent safe state.

# 27. Narrowest-Boundary Containment

Every security control should define the smallest boundary it needs to close.

Examples:

```text
malformed tool call
    → reject tool call

outside-workspace target
    → reject action

approval required
    → pause consequence, preserve cognition

telemetry failure
    → degrade telemetry, continue cognition

confirmed NEVER-path attempt
    → hard interrupt affected connection

confirmed canary leakage
    → stop unreleased stream and sever

source drift
    → terminate active Kernel according to integrity policy

runtime-code integrity compromise
    → terminate Kernel authority

authority-policy integrity compromise
    → terminate Kernel authority

unauthorized protected dynamic-state mutation
    → terminate or invalidate the affected authority scope
```

This policy should be implemented deliberately rather than left to ad hoc exception handling.

## 27.1 Preservation Escalation Order

Containment should escalate only as far as necessary:

```text
1. Reject only the proposed consequence
        ↓ if insufficient
2. Withhold only the affected output span / tool call
        ↓ if insufficient
3. Invalidate only the affected run/security scope
        ↓ if insufficient
4. Sever only the affected connection
        ↓ only when Kernel authority itself cannot be trusted
5. Terminate or make inert the Kernel runtime
```

The hierarchy does not weaken hard-security handling. It prevents implementation convenience from becoming a reason to destroy unrelated safe work.

# 28. Unified Security Pipeline

The resulting architecture is:

```text
                    AGENT / CLIENT
                          │
                          ▼
                 REQUEST AUTHORITY
                          │
                          ▼
                  JACK KERNEL STATE
                          │
     ┌────────────────────┼─────────────────────┐
     │                    │                     │
     ▼                    ▼                     ▼
SOURCE DRIFT       RUNTIME CODE         AUTHORITY STATE
   GUARD             INTEGRITY             INTEGRITY
                                                │
                         ┌──────────────────────┤
                         │                      │
                         ▼                      ▼
                STATIC POLICY           DYNAMIC STATE
             immutable + measured     controlled versions
                         │                      │
                         └──────────┬───────────┘
                                    ▼
                              MODEL BACKEND
                                    │
                                    ▼
                          probabilistic output
                                    │
                                    ▼
                        ┌────────────────────┐
                        │   STREAMING IRQ    │
                        │   CANARIES         │
                        │   DLP              │
                        │   EVIDENCE GUARD   │
                        └──────────┬─────────┘
                                   ▼
                          proposed consequence
                                   │
                                   ▼
                        ┌────────────────────┐
                        │ Restricted Paths   │
                        │ Workspace Lock     │
                        │ Stage Authority    │
                        │ Tool Authority     │
                        │ Run Identity       │
                        │ Evidence State     │
                        │ Approval State     │
                        │ Consequence Gate   │
                        └──────────┬─────────┘
                                   │
                 ┌─────────────────┼─────────────────┐
                 ▼                 ▼                 ▼
               ALLOW        DENY / CONTINUE      USER DECISION

                                   │
                      HARD INTERRUPT only
                      for defined hard breach
```

The Authority Ledger records the Kernel-owned security transitions across this path.

Credential isolation and privacy controls operate across the same boundary.

---

# 29. Security Event Classes

Jack should use explicit event classes rather than treating all problems alike.

### Recoverable Policy Events

```text
TOOL_SCHEMA_REJECTED
STAGE_TOOL_DENIED
WORKSPACE_TARGET_DENIED
USER_APPROVAL_REQUIRED
UNSUPPORTED_ACTION
```

### Hard Security Events

```text
CANARY_MATCH
KERNEL_SECRET_EXPOSURE
FORGED_KERNEL_EVIDENCE
RESTRICTED_NEVER_PATH_ATTEMPT
RUNTIME_INTEGRITY_COMPROMISED
AUTHORITY_POLICY_INTEGRITY_COMPROMISED
UNAUTHORIZED_SECURITY_STATE_TRANSITION
SOURCE_DRIFT_DETECTED
SECURITY_POLICY_TAMPER
```

### Authorized Dynamic Security Events

These are security-significant state transitions but are not violations:

```text
SECURITY_STATE_INITIALIZED
SECURITY_STATE_VERSION_ADVANCED
DYNAMIC_CANARY_REGISTERED
RUN_EPOCH_ADVANCED
APPROVAL_STATE_CHANGED
SETTLEMENT_STATE_CHANGED
LEDGER_HEAD_ADVANCED
```

The names may change during implementation.

The distinctions should not.

---

# 30. Source Drift Severity

Source Drift deserves one nuance.

Because current Jack does not hot-reload ordinary source into the existing process, source drift does not mean that the active function body necessarily changed.

Nevertheless, the user has defined active Kernel modification as disallowed.

Therefore Source Drift is treated as a hard operational-integrity event.

That decision is policy-based and accurately stated:

> The running Kernel source tree changed when it was required to remain stable.

It is not falsely described as:

> The loaded interpreter code definitely changed.

Runtime Code Integrity Guard covers the second property.

Authority State Integrity Guard covers the further property that unchanged code may nevertheless have been made to enforce different rules through unauthorized policy mutation.

---

# 31. Configuration Surface

A future configuration may remain compact:

```yaml
security:

  streaming_irq:
    enabled: true
    quarantine_window: auto
    max_window: <bounded ceiling>

  canaries:
    kernel: true
    dynamic_run: true
    user_defined: []

  restricted_paths:
    system_defaults: true
    additional: []

  workspace:
    enabled: false
    root: null

  integrity:
    source_drift_guard: true
    runtime_code_guard: true
    authority_state_guard: true

  consequence_gate:
    enabled: true

  authority_ledger:
    enabled: true

  dlp:
    enabled: true

  privacy:
    strict_external_diagnostics: true
```

The exact schema should follow implementation rather than force implementation to match premature names.

Most importantly, ordinary agent/model requests must not be able to modify these host-authoritative settings.

The mutable configuration representation should not remain the active enforcement object indefinitely.

Instead:

```text
configuration
    ↓
validation
    ↓
canonicalization
    ↓
immutable authority-policy snapshot
    ↓
measured active policy
```

Run-scoped dynamic security state should be created separately through explicitly authorized state-transition mechanisms.

---

# 32. Adversarial Verification: StreamingIRQ

StreamingIRQ tests should cover:

- match entirely within one chunk;
- match divided at every possible chunk boundary;
- one-character chunks;
- very large chunks;
- escaped forms;
- normalization variants;
- partial match at EOS;
- benign near-match;
- multiple simultaneous patterns;
- minimum allowed window;
- maximum allowed window;
- policy asking for a window beyond the hard ceiling.

The defining assertion is:

> **No hard-protected match becomes visible before Jack detects it.**

False-positive behavior must also be tested.

A detector that constantly destroys harmless output is a failed security design.

---

# 33. Adversarial Verification: Path Policy

Test:

```text
normal allowed path
normal NEVER path
mixed case
mixed separators
.. traversal
environment variable representation
quoted structured path
sibling directory
similar harmless prefix
nested protected child
opaque unparseable shell text
```

Two different assertions must be tested.

First:

> Jack correctly authorizes the represented target it can determine.

Second:

> Jack does not claim to know the final resolved filesystem object when it does not.

The second is as important as the first.

---

# 34. Adversarial Verification: Workspace Lock

With one workspace configured:

```text
workspace root             → allowed
workspace descendant       → allowed
parent                     → denied
sibling                    → denied
outside workspace          → denied and continue
confirmed NEVER path       → hard interrupt
workspace disabled         → ordinary policy restored
```

The test suite should verify that an ordinary workspace denial does not discard unrelated valid cognition.

---

# 35. Adversarial Verification: Source Drift

Test:

1. Start Jack.
2. Establish protected source baseline.
3. Modify one protected Kernel source file.
4. Confirm Source Drift event.
5. Confirm active service is terminated or made inert.
6. Stop Jack.
7. Keep the legitimate source modification.
8. Restart Jack.
9. Confirm the new source becomes the new valid baseline.

The last steps are essential.

The mechanism must protect live integrity without preventing legitimate development.

---

# 36. Adversarial Verification: Runtime Code Integrity

Start Jack, then deliberately test:

```python
replace protected function
replace module attribute
alter function __code__
reload protected module
rebind critical validator
```

Expected result:

```text
RUNTIME_INTEGRITY_COMPROMISED
```

Also test irrelevant mutations:

```text
change local temporary object
change ordinary request state
modify non-authority diagnostic state
```

Those should not trigger the integrity guard.

This validates that Jack is secure without being indiscriminately fragile.

---

# 36A. Adversarial Verification: Authority Policy Integrity

The policy-integrity suite should attempt to modify effective security behavior while leaving protected function code untouched.

Test:

```text
attempt to remove a default NEVER path
attempt to remove a user-defined NEVER path
attempt to replace the entire restricted-path set
attempt to delete a Tier-B Canary
attempt to replace the Tier-B Canary set
attempt to weaken a hard DLP signature set
attempt to increase the quarantine ceiling beyond policy
attempt to disable DLP in active policy
attempt to disable StreamingIRQ in active policy
attempt to replace the active workspace policy
attempt to replace the security outcome classification policy
```

Where the implementation uses truly immutable structures, ordinary mutation should fail immediately.

Where replacement of the enclosing object remains technically possible, baseline identity and canonical digest verification should detect the change.

Expected hard result:

```text
AUTHORITY_POLICY_INTEGRITY_COMPROMISED
```

The test should prove that:

> **Unchanged authority code cannot silently begin enforcing weakened policy because the data it consults was mutated.**

---

# 36B. Adversarial Verification: Controlled Dynamic Security State

The corresponding non-brittleness tests must prove that legitimate dynamic state evolution is accepted.

Test authorized transitions such as:

```text
register legitimate Tier-C run Canary
advance run_epoch
bind new task/run state
change approval state through authorized interface
advance settlement state
rotate run-scoped security state
advance ledger head
```

Expected result:

```text
authorized new state snapshot
version advanced
canonical digest updated
ledger transition recorded
no integrity failure
```

Then test the same changes attempted outside the authorized transition path.

Examples:

```text
directly delete Tier-C Canary
directly replace run_id
directly change run_epoch
directly reset approval state
directly replace active security-state snapshot
reuse stale state version
construct transition from wrong predecessor digest
```

Expected result:

```text
UNAUTHORIZED_SECURITY_STATE_TRANSITION
```

This two-sided test is essential.

Jack must prove both:

> Unauthorized mutation is detected.

and:

> Legitimate security-state evolution does not trigger false tamper alarms.

# 36C. Adversarial Verification: Runtime-Scoped Ledger Concurrency

Run two independent runtime/lane instances and verify:

```text
runtime A advances head A
runtime B advances head B

A does not overwrite B
B does not overwrite A

both event streams remain attributable
```

Attempting to directly advance another runtime's ledger head must be rejected as an authority violation.

Then aggregate both histories and verify that aggregation changes neither authoritative chain.

# 37. Adversarial Verification: Consequence Gate

Test:

- unavailable tool;
- malformed tool call;
- stale task identity;
- wrong run epoch;
- valid current evidence;
- forged evidence text;
- action requiring approval;
- repeated settled authorization;
- out-of-workspace target;
- NEVER-path target.

Expected outcomes must differ appropriately.

The test should explicitly verify the four-state security model:

```text
ALLOW
DENY_AND_CONTINUE
REQUIRE_USER_DECISION
HARD_INTERRUPT
```

A security implementation that turns all four into the same failure mode is incorrect.

---

# 38. Adversarial Verification: Preservation of Useful Work

This deserves its own test family.

Jack should intentionally be given scenarios where:

- the reasoning is valuable but the tool call is malformed;
- the analysis is valid but the proposed path is outside the workspace;
- one consequential action fails policy while later safe work remains possible;
- observability fails during otherwise valid cognition;
- a model self-corrects after a recoverable policy denial;
- a legitimate dynamic security-state transition occurs during an otherwise healthy run.

The assertion is:

> **Safe cognition survives recoverable enforcement whenever preserving it does not weaken a hard invariant.**

This is not an optimization.

It is part of the security design.

## 38.1 Multi-Runtime Preservation Cases

Additional preservation tests should verify that:

- one runtime may record a security event while another independent runtime continues valid work;
- an affected run/security scope can be invalidated without destroying unrelated safe state when Kernel authority remains trustworthy.

Every new hardening mechanism should pair its negative security test with a preservation assertion for unrelated safe work.

# 39. Recommended Upgrade Sequence

The implementation order should follow security dependencies rather than historical feature ranking.

### Phase 0 - Exact Runtime and Insertion-Point Mapping

No code changes.

Map from the actual current source:

```text
backend stream ingress
Kernel stream processing
evidence guard
Chat Completions release
Responses translation
non-stream release
tool-call reconstruction
tool-call validation
runtime configuration
existing mutable security-relevant state
```

This phase exists to ensure later controls are inserted into the real shared boundaries rather than duplicated across endpoints.

#### Phase 0 Concurrency Inventory Addendum

For each mutable security-relevant field identified during Phase 0, also record its owning authority and concurrency scope. Identify existing ledger state and persistence boundaries explicitly.

### Phase 1 - Security Outcome Model

Introduce the explicit outcome classes:

```text
ALLOW
DENY_AND_CONTINUE
REQUIRE_USER_DECISION
HARD_INTERRUPT
```

Without this distinction, later controls risk becoming brittle.

### Phase 2 - StreamingIRQ Core

Introduce the bounded configurable pre-release quarantine mechanism without Canary logic initially.

First prove:

```text
buffer correctness
stream ordering
SSE correctness
EOS behavior
tool-call delta compatibility
Responses parity
non-stream parity
```

### Phase 3 - Three-Tier Canary Tokens

Add:

```text
Tier A Kernel Canaries
Tier B user-defined Canaries
Tier C dynamic run/session Canaries
```

Integrate them into the already-proven StreamingIRQ release boundary.

### Phase 4 - Restricted Paths and Workspace Lock

Introduce request-target authorization while preserving the explicit Path Resolution Gap.

### Phase 5 - Consequence Gate

Unify stage authority, tool authority, runtime identity, target policy, evidence, approval state, and the four-state security outcome model.

### Phase 6 - Authority and Security Ledger

Persist Kernel-owned decisions, integrity events, and security-state transitions.

#### Phase 6 Runtime-Scoped Ledger Addendum

The current multi-endpoint architecture uses one authoritative ledger namespace and one authoritative ledger head per Jack runtime process. Every authoritative record binds to `lane_id` / `runtime_id`, and where applicable `task_id` / `run_id` / `run_epoch`.

A multi-runtime forensic view may aggregate records but is not an authority-bearing shared ledger head.

### Phase 7 - Credential Isolation and Integrated DLP

Reduce secret exposure and integrate Kernel-visible DLP into the pre-release security boundary.

### Phase 8 - Source Drift Guard

Protect the active source tree while preserving full freedom to edit Jack when stopped.

### Phase 9 - Runtime Code Integrity Guard

Protect selected loaded authority modules, function bindings, and code objects against unexpected replacement or mutation.

### Phase 10 - Authority Policy Integrity and Controlled Dynamic Security State

Project static security policy into immutable measured snapshots.

Introduce:

```text
authority-policy object identity
canonical policy digest
deep immutability where practical
version identity
```

Then move legitimately dynamic security state to controlled copy-on-write/versioned snapshots with explicit Kernel-owned transitions.

This phase must prove both unauthorized-mutation detection and legitimate-transition tolerance before acceptance.

#### Phase 10 Concurrency Addendum

For every protected security field, classify:

```text
mutability class
owning authority
concurrency scope
```

The predecessor check and active-state replacement must be atomic within that declared concurrency scope. Current task/run/epoch state and authoritative ledger heads are runtime-process scoped. Any future shared cross-process authority state requires an explicit cross-process serialization primitive before it can become authoritative.

### Phase 11 - Privacy and Telemetry Hardening

Constrain external diagnostic leakage while preserving local forensic usefulness and the existing non-authoritative telemetry model.

This extends the earlier security-upgrade proposal without changing the original goal: make Jack more secure **without making it more operationally privileged**.

## 39.1 Global Phase Acceptance Addendum

Every phase must prove both:

> **Did Jack stop the unsafe thing?**

and:

> **Did Jack preserve everything that remained safe and useful?**

A phase fails if it permits a defined security violation or if it unnecessarily destroys valid cognition, valid state, unrelated work, or recoverable progress.

# 40. Final Security Invariants

After implementation and successful adversarial verification, Jack Kernel should be able to assert the following narrowly defined properties.

### Invariant 1 - Cognition Is Not Authority

Model output cannot authorize itself.

### Invariant 2 - Protected Output Can Be Withheld Before Release

StreamingIRQ operates before downstream visibility.

### Invariant 3 - Protected-State Leakage Can Be Detected

Canaries create deterministic evidence of boundary escape.

### Invariant 4 - Hard Security and Recoverable Error Are Different States

Jack does not destroy useful work merely because something went wrong.

### Invariant 5 - NEVER Paths Are Not Authorized

A positively identified request targeting a configured NEVER path does not cross the Kernel boundary.

### Invariant 6 - Workspace Lock Restricts Represented Targets

When enabled, Jack denies represented filesystem targets outside the configured workspace.

### Invariant 7 - Path Authorization Does Not Pretend to Be Object Attestation

Jack explicitly acknowledges the Path Resolution Gap.

### Invariant 8 - Consequences Require Kernel Authorization

A proposal only becomes releasable when deterministic policy allows it.

### Invariant 9 - Security State Does Not Depend on Model Memory

Kernel-owned authority transitions are independently recorded.

### Invariant 10 - Kernel Secrets Need Not Become Model Context

Credentials remain scoped to the Kernel boundary wherever practical.

### Invariant 11 - Active Source Drift Is Detectable

Authority-bearing Kernel source is expected to remain stable during a live run.

### Invariant 12 - Loaded Authority-Code Rebinding or Mutation Is Detectable Within the Defined Threat Model

Selected Python authority objects are monitored independently of the source tree.

### Invariant 13 - Authority Data Cannot Silently Redefine Unchanged Authority Code

Static security policy is immutable and measured for the active authority scope.

### Invariant 14 - Legitimate Dynamic Security State Evolves Only Through Explicit Authority

Dynamic security state advances through validated, versioned Kernel-owned transitions rather than arbitrary mutation.

### Invariant 15 - Unauthorized Dynamic Security-State Mutation Is Detectable

A protected state change occurring outside the authorized transition model is a security-integrity event.

### Invariant 16 - Observability Is Not Authority

Telemetry degradation does not automatically alter cognition or authorization.

### Invariant 17 - Hard Failure Is Narrowly Scoped

Jack closes no more of the system than necessary to preserve the violated invariant, except where Kernel authority itself is compromised.

### Invariant 18 - Ledger Authority Is Runtime-Scoped Under the Current Multi-Endpoint Architecture

Each Jack runtime owns its authoritative ledger namespace and head; read-only aggregation does not create a shared mutable authority head.

### Invariant 19 - Transition Atomicity Matches the Declared Concurrency Domain

An in-process transition primitive is used only for runtime-scoped authority state. Shared cross-process authority requires an explicit cross-process serialization mechanism.

### Invariant 20 - Useful Work Is Preserved Whenever Security Allows It

Jack preserves all cognition, state, and progress that can remain safely valid after enforcement.

# 41. Non-Goals and Explicit Limits

Jack Kernel does not claim through these upgrades to provide:

```text
universal filesystem object containment
descriptor-level path attestation
arbitrary process-memory attestation
cryptographic remote attestation of its own Python process
universal sandboxing
complete external process control
perfect shell semantic analysis
universal host safety
```

The current Kernel already explicitly avoids claiming universal filesystem sandboxing or complete interception of consequences outside the authority it actually owns.

The Authority State Integrity Guard likewise does not imply that a process with arbitrary memory compromise can reliably attest itself.

It closes ordinary application-level authority-data mutation pathways within the stated threat model.

Narrow, true claims are stronger than broad, false ones.

## 41.1 Runtime-Scoped Ledger Ordering Limit

The runtime-scoped ledger architecture does not claim one total authoritative ordering across independent Jack runtime processes. A forensic aggregator may present a combined view without becoming a shared mutation authority.

# 42. Central Security Doctrine

The hardened Jack Kernel can be summarized through four laws.

> **Probabilistic cognition may propose, but deterministic software must dispose.**

> **Put each security mechanism at the boundary where Jack actually has the information and authority to enforce it.**

> **Fail closed on authority; fail soft on recoverable cognition and non-authoritative observability.**

> **Contain the violation at the narrowest boundary that preserves the security invariant.**

These four rules prevent two opposite failures.

The first is a weak Kernel that trusts cognition too much.

The second is an over-hardened Kernel that becomes unusable because it treats every anomaly as an attack.

Jack should be neither.

## 42.1 Operational Corollary

> **Jack must preserve all useful cognition and state that can be preserved without weakening the violated security invariant. Never discard useful work merely because discarding it is easier to implement.**

# Conclusion

Jack Kernel occupies a strategically valuable position because it sits directly between autonomous software and the probabilistic model supplying its cognition.

That position gives Jack control over something more fundamental than content moderation.

It controls the transition from:

```text
proposal
```

to:

```text
authorized release
```

The proposed security upgrade strengthens that transition in several ways.

**StreamingIRQ** holds potentially sensitive output before release.

**Canary Tokens** provide deterministic leakage evidence.

**Restricted Paths** give users explicit NEVER-access boundaries.

**Workspace Lock** lets users confine represented filesystem targets to one declared project without turning every accidental escape into catastrophic session failure.

**The Consequence Gate** centralizes deterministic authorization.

**The Authority Ledger** preserves Jack's own security history independently of model memory.

**Credential isolation and DLP** reduce the amount of protected state cognition ever needs to possess.

**Source Drift Guard** detects changes to the active Kernel source tree while preserving complete freedom to modify Jack when it is stopped.

**Runtime Code Integrity Guard** separately monitors the actual Python authority objects loaded into the live interpreter and does not confuse disk modification with runtime code modification.

**Authority Policy Integrity Guard** closes a separate class of tampering in which unchanged authority code is made to enforce weakened rules because the data it consults has been silently changed.

Static security policy is therefore projected into immutable, canonically measured snapshots rather than left as ordinary mutable application structures.

**Controlled Dynamic Security State** ensures that security state which legitimately must evolve—run identity, run epochs, dynamic Canaries, approval state, settlement state, ledger state—can continue to evolve without making Jack brittle. It changes through explicit Kernel-owned, versioned transitions rather than arbitrary in-place mutation.

**Privacy controls** prevent Jack's own observability surfaces from becoming accidental information channels.

Most importantly, the architecture explicitly rejects the idea that security quality can be measured by how aggressively Jack kills work.

A malformed action is not automatically an attack.

An accidental workspace escape is not automatically a compromised session.

A telemetry failure is not a reason to discard cognition.

A legitimate run-state transition is not tampering.

Jack should preserve safe work wherever the deterministic boundary remains intact.

But when a real hard invariant is crossed—protected-state leakage, a confirmed NEVER-path request, forged host authority, Kernel secret exposure, live Kernel code compromise, unauthorized authority-policy modification, or unauthorized protected security-state mutation—Jack must not negotiate with probabilistic cognition.

It must dispose.

The resulting design is therefore not merely a hardened Kernel.

It is a **selectively hard Kernel**:

> **Strict where authority is real.  
> Recoverable where cognition is still useful.  
> Mutable only where mutation is explicitly authorized.  
> Deterministic where security depends on it.**