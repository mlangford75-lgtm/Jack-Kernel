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

## Operator walkthrough (current mainline)

On Windows, launch Jack with `start.bat`, then choose K at the launcher.
Use the following sequence before starting a secured serving session.

1. Choose **1** and enter the absolute authorized workspace directory, for
   example `C:\Jack_Testing\workspace`. Blank cancels. Workspace Lock is
   optional; enable it when the agent should operate only inside that root.
2. Choose **3** and enter an absolute NEVER path, for example
   `C:\Jack_Testing\restricted`. Repeat for additional roots. NEVER restrictions
   remain effective independently of Workspace Lock. Option 4 removes only
   user-defined entries; it does not remove built-in protected roots.
3. Choose **9**. Enter `adaptive` to select the recommended default explicitly,
   then press Enter to retain the current quarantine ceiling (4096 on fresh
   local settings). A previously saved explicit 100% setting is not migrated
   automatically; select Adaptive if that is your intended policy.
4. Choose **5** to register a protected value using the hidden input prompt.
   For a test, use a disposable synthetic value of at least eight characters.
   Repeat for additional values. Do not paste production secrets into test prompts.
5. Optionally choose **10**, enter the displayed Canary number, then enter
   an integer percentage (1–100) or `inherit`. Entering 0 at the selection
   prompt cancels. Confirm the warning if you deliberately choose a match
   shorter than eight characters.
6. Choose **7** to review the workspace, restricted roots, global sensitivity,
   individual effective match lengths and active quarantine. Values remain hidden.
7. Choose **S** to save and apply the configuration for the next Kernel start.
   Start the secured server through the launcher and point the agent at Jack's
   authenticated endpoint, not directly at the inference backend.

To remove a restriction, choose 4 or 6, select its number and confirm with
`y`. To disable Workspace Lock, choose 2 and confirm with `y`. To abandon
unsaved editor changes, choose M. Restart the serving process for changed
policies to take effect. Session Canaries must be registered again after
restarting the launcher; saved global sensitivity and path settings persist.

### Selecting sensitivity in practice

| Protected length | Adaptive match | Explicit 25% match |
|---:|---:|---:|
| 8 | 8 | 2 |
| 10 | 10 | 3 |
| 16 | 16 | 4 |
| 32 | 16 | 8 |
| 64 | 16 | 16 |
| 128 | 32 | 32 |
| 256 | 64 | 64 |
| 1024 | 256 | 256 |

A lower percentage means **more sensitive** detection, not stronger encryption
or a guaranteed bound on total leakage. Option 9 accepts preset names,
`adaptive`, an integer, or `custom` followed by an integer at the next prompt.
Explicit partial global sensitivity requires confirmation because it also
applies to automatic credential Canaries. Blank input retains the existing
selection. Option 10 overrides only the selected session Canary; `inherit`
restores the global policy. The quarantine ceiling is a capacity limit, not
the match threshold: the active window is derived from effective matches.
If a setting conflicts with the policy or capacity, Jack retains the previous
setting. Review option 7 after each change.

### Operational verification and response

Use an authorized disposable workspace and synthetic protected values.
Verify an allowed operation succeeds, an outside-root or NEVER operation
is denied, a below-threshold synthetic fragment is permitted, and a matching
fragment produces a hard interrupt without being released. Confirm the
actual host security decision and filesystem state, not merely the model's
statement. After a hard interrupt, start a fresh authorized request; do not
retry the prohibited operation through a different tool or path.

The November 26, 2026 live qualification reported nine supported cognitive
configurations and three security cases passing on candidate
[`610377b6`](https://github.com/mlangford75-lgtm/Jack-Kernel/commit/610377b6aa4f1f931f7b0a3a70bf90aaafa2e013),
merged in [PR #178](https://github.com/mlangford75-lgtm/Jack-Kernel/pull/178).
With `ling-3.0-tiny` and four simultaneous requests, the 15-character control
was released, the 16-character protected fragment was blocked, unrelated
streams completed independently, invalid authentication was rejected, and
a subsequent request recovered. This is reported live qualification of
those cases, not a universal security guarantee or independent certification.

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
