# StreamingIRQ sensitivity

Security Center option 9 sets the global percentage of consecutive matching
characters required to interrupt a model-output stream. Presets: Maximum 5%,
High 10%, Standard 25%, Low 50%, Exact 100% (default), or Custom 1–100%.
Option 10 sets or clears a session Canary's individual override. Global settings
persist; custom Canary values and overrides stay in the launcher session.
An administrator-provided JACK_CANARY_POLICY_JSON overrides local settings.

For a value of length L and sensitivity P, the threshold is ceil(L*P/100).
Matching is case-sensitive and covers contiguous fragments at any position
inside the protected value. A 1024-character value at 10% requires 103 matching
characters. The active look-behind is the largest threshold minus one across
registered values. Confirmed matches hard-interrupt before the fragment is
released. Exact matching remains the default. Smaller thresholds can match
ordinary output, including common key prefixes; use partial matching deliberately.

The custom quarantine ceiling is configurable to 16,384 characters, and custom
values may be up to 16,385 characters (minimum eight). Local session policy defaults
to a ceiling of 4096; legacy JSON without a ceiling retains 256. Existing automatic
credential output-DLP ceiling is at least 4096 and may expand to the configured
ceiling. Global sensitivity also applies to automatic credential-derived Canaries;
credential input isolation remains exact and independent. No secret values are
saved in launcher settings. Static Policy Integrity seals the resolved percentages.

Example startup JSON (synthetic values only):
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
