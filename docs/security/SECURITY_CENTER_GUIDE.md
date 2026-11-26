# JACK KERNEL — SECURITY CENTER

## Purpose and scope

Security Center is the local startup configuration interface for Jack Kernel.
Kernel governs model-output release, represented tool actions, pending transaction
authority, and selected credential, diagnostic and executable integrity boundaries.
The external agent/executor owns actual filesystem effects. These controls are
not a general operating-system sandbox, a universal filesystem-object attestation,
or a guarantee against all forms of secret transformation.

## Getting started

At the launcher splash screen, select **K — Security Center**. Configure policy
before starting the serving process. Select **S** to save and apply settings;
**M** discards the current editor transaction. Restart the serving process to
change its bound policy. Environment-provided policy takes precedence over
local settings; an administrator override cannot be edited from the menu.

| Option | Function |
|---|---|
| 1 | Set or change the absolute Windows Workspace Lock root |
| 2 | Disable Workspace Lock with explicit confirmation |
| 3 | Add a user-defined NEVER root; repeat to add more |
| 4 | Remove a numbered user-defined NEVER root, with confirmation |
| 5 | Register a hidden session Canary |
| 6 | Remove a numbered session Canary |
| 7 | Review effective startup policy, thresholds and core protections |
| 8 | Configure existing forensic archive settings |
| 9 | Set global StreamingIRQ sensitivity and quarantine ceiling |
| 10 | Set or clear an individual session Canary's percentage override |

Workspace Lock, user-defined restricted roots and global StreamingIRQ settings
are persisted in local launcher settings. Session Canary values and their
overrides are not saved to the configuration file. Register them again on
each new launcher session, or supply an administrator-controlled startup policy.
The review screen is a configuration check, not a live serving-process
attestation. Keep configuration and environment access appropriately restricted.

## Restricted Paths and Workspace Lock

Workspace Lock is optional; when enabled it denies represented filesystem
targets outside the authorized root. Default protected system roots remain
enforced. User-defined NEVER roots are additional restrictions. A positive
NEVER match causes a hard interrupt before release of the consequential tool
batch. Recoverable denials with independent authorized siblings preserve those
siblings. A narrow exception for ordinary default Windows metadata is not
permission to read protected system resources or bypass Workspace Lock.

The Kernel cannot independently establish every final filesystem object
accessed by an external executor; it evaluates its owned represented-target
and executor-admission contracts. Never interpret ALLOW as proof of completion.

## StreamingIRQ and sensitivity

StreamingIRQ quarantines native model text and supported tool-argument streams
before public release, detecting contiguous protected values across chunk
boundaries. The Reasoning Airlock covers represented native reasoning fields;
it cannot inspect hidden provider reasoning that is not supplied to Kernel.

Sensitivity determines how many consecutive matching characters within a
registered value trigger a hard interrupt before the fragment is released.
The Adaptive default uses `min(L, max(16, ceil(L/4)))`, where L is the value
length. Values of 16 characters or fewer match exactly, medium-length values
require at least 16, and values of 64 characters or more use 25% (rounded up).
Explicit percentages use `ceil(L * percentage / 100)` without that floor.

| Preset | Required match | 256-character value | 1024-character value |
|---|---:|---:|---:|
| Adaptive (default) | 25%, minimum 16, short values exact | 64 | 256 |
| Maximum | 5% | 13 | 52 |
| High | 10% | 26 | 103 |
| Standard | 25% | 64 | 256 |
| Low | 50% | 128 | 512 |
| Exact | 100% | 256 | 1024 |
| Custom example | 9% | 24 | 93 |

Option 9 accepts Adaptive, a preset name, an integer percentage, or Custom
followed by an integer 1–100. Existing explicitly saved percentages and
administrator overrides remain authoritative. Option 10 allows different
values to inherit or override the global setting. Adaptive is distinct from
explicit Standard 25%; only Adaptive enforces the 16-character floor. The active quarantine is the largest effective threshold
minus one across the registered values. The custom ceiling is configurable
to 16,384 characters. Values are limited to 16,385 characters; the minimum
custom value length is eight. The default local custom ceiling is 4096.
The automatic credential output-DLP ceiling is at least 4096 and may expand
to the configured ceiling. Legacy environment JSON without a ceiling keeps
its former 256-character custom ceiling. Invalid policies fail closed.

Low percentages can match ordinary text, especially for short, repetitive,
or predictable values. Adaptive reduces but does not eliminate false positives. Global sensitivity includes automatically registered
credential Canaries. Use an appropriately conservative threshold. The exact
case-sensitive matcher does not claim encoded, fuzzy, case-insensitive or
cross-channel aggregate leakage detection. Known credential input isolation
and diagnostic redaction remain separate exact-value controls.

## Core security controls

| Control | What it enforces |
|---|---|
| StreamingIRQ / Reasoning Airlock | Deterministic represented output quarantine and interruption |
| Canary Tripwires | Registered exact or contiguous partial matches |
| Restricted Paths / Workspace Lock | Represented target and executor admission authority |
| Consequence Gate | Host-owned consequence dispositions |
| Authority Ledger | Records supported host authority decisions |
| Credential Isolation and DLP | Known credential values and protected credential resources |
| Source Drift Guard | Selected source authority measurement |
| Runtime Code Integrity | Selected loaded executable and binding identity |
| Static Policy Integrity | Bound policy identity and resolved policy values |
| Dynamic Authority Integrity | Pending tool transaction authority and authenticated results |
| Diagnostic Privacy | Withholds or redacts protected exact-value diagnostics and archives |

These controls are required at secured startup and are not model prompt
instructions. Configuration cannot make an unauthorized action authorized.
A deliberate hard interrupt is a security outcome, not a backend success.

## Recovery and verification

The Loop Detector is configured separately from Security Center. Its default
is 12 repetitions of a 64-word-or-longer exact reasoning cycle, with selectable
thresholds from 4 to 128. Previously saved thresholds remain valid. It observes
generated native reasoning, not user prompts. Same-stage correction attempts
retain detector state; a deliberate retry or new tool-result resume starts
fresh. Ordinary tool recovery has its existing 25-attempt ceiling. Three
identical consecutive all-denied immutable security proposals terminate in
a deterministic host handoff, without another inference. A denied operation
must not be retried through alternate access.

For acceptance testing, use synthetic values and disposable workspaces.
Verify an allowed read, a blocked outside-root read, a separate explicit NEVER
denial, a synthetic partial Canary match across stream chunks, and a near-match
that remains permitted. Do not test using real credential contents.
Automated benchmark: python tests/benchmark_streaming_irq.py. It reports
isolated matcher throughput and retained text, not end-to-end model latency
or total runtime-integrity overhead.

## Policy authority

Administrator startup environment variables: JACK_PATH_POLICY_JSON and
JACK_CANARY_POLICY_JSON. Example values must be synthetic. The policy is
validated before start, and static policy integrity binds the resolved
sensitivity and quarantine settings. Mandatory security remains independent
of agentic mode and backend choice.

See [StreamingIRQ sensitivity](STREAMING_IRQ_SENSITIVITY.md) and
[Recovery boundaries](RECOVERY_BOUNDARIES.md) for technical details.
