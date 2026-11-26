# StreamingIRQ sensitivity

Security Center option 9 sets the global sensitivity for consecutive matching
characters required to interrupt a model-output stream. Adaptive is the default:
25%, with a minimum of 16 matching characters (exact for shorter values).
Explicit presets: Maximum 5%, High 10%, Standard 25%, Low 50%, Exact 100%,
or Custom 1–100%.
Option 10 sets or clears a session Canary's individual override. Global settings
persist; custom Canary values and overrides stay in the launcher session.
An administrator-provided JACK_CANARY_POLICY_JSON overrides local settings.

For a value of length L, Adaptive uses `min(L, max(16, ceil(L/4)))`.
Explicit sensitivity P uses `ceil(L*P/100)` without the adaptive floor.
For example, a 10-character value matches exactly, a 32-character value requires
16 characters, a 64-character value requires 16, and a 1024-character value
requires 256. An explicitly selected 10% on a 1024-character value requires 103.
Matching is case-sensitive and covers contiguous fragments at any position
inside the protected value. The active look-behind is the largest effective
threshold minus one across registered values. Confirmed matches hard-interrupt
before the fragment is released. Shorter thresholds can match ordinary output,
including common key prefixes. The adaptive floor reduces false positives but
does not eliminate them.

The custom quarantine ceiling is configurable to 16,384 characters, and custom
values may be up to 16,385 characters (minimum eight). Local session policy defaults
to a ceiling of 4096; legacy JSON without a ceiling retains 256. Existing automatic
credential output-DLP ceiling is at least 4096 and may expand to the configured
ceiling. Global sensitivity also applies to automatic credential-derived Canaries;
credential input isolation remains exact and independent. No secret values are
saved in launcher settings. Static Policy Integrity seals the adaptive/explicit
selection, resolved per-value sensitivities, effective thresholds and quarantine.

Omit the global `sensitivity_percent` field to select Adaptive in startup JSON;
explicit integer percentages (including saved settings from older versions)
remain authoritative. A missing per-value override inherits the global policy.
An explicit `null` is invalid rather than an alternative configuration spelling.
The low-level exact-match Canary constructor remains available for internal callers;
resolved runtime policies and automatic credentials use Adaptive by default.

Example startup JSON (synthetic values only; Adaptive with an exact override):
```json
{"version":1,"max_window":4096,"patterns":[{"id":"synthetic","tier":"B","value":"SYNTHETIC-EXAMPLE-ONLY","sensitivity_percent":100}]}
```

Explicit global sensitivity example:
```json
{"version":1,"sensitivity_percent":10,"max_window":4096,"patterns":[{"id":"synthetic","tier":"B","value":"SYNTHETIC-EXAMPLE-ONLY","sensitivity_percent":100}]}
```

This protects represented native text streams and tool arguments, not all possible
encodings, transformations, or aggregate disclosures across separate channels.

## Qualification benchmark

Windows GitHub Actions run [45759464785](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/45759464785),
commit `3bdeb78e46821e0a8245c7ccb15830a1e8850892`, passed all 27 isolated
matcher configurations and the combined security qualification.

Representative median processing times for 4,096 synthetic output characters:

| Key length | Sensitivity | Key count | Chunk characters | Held characters | Median ms |
|---:|---:|---:|---:|---:|---:|
| 128 | 5% | 1 | 16 | 6 | 1.000 |
| 256 | 5% | 1 | 16 | 12 | 0.988 |
| 1024 | 5% | 1 | 16 | 51 | 1.143 |
| 1024 | 25% | 1 | 16 | 255 | 1.612 |
| 1024 | 100% | 1 | 16 | 1023 | 0.463 |
| 1024 | 5% | 128 | 64 | 51 | 95.350 |
| 1024 | 25% | 128 | 64 | 255 | 155.244 |
| 1024 | 100% | 128 | 64 | 1023 | 6.188 |

These numbers isolate the matcher, with a synthetic clean-output workload
and a separate positive detection check. They do not measure policy construction,
full-process memory, real-model latency, token-cache reuse, provider prefill,
or total executable/policy-integrity verification costs. The benchmark's
traced peak measures temporary Python allocations during scanning, excluding
already-registered values. Retain the current design pending live acceptance;
do not infer universal throughput from this one runner.
