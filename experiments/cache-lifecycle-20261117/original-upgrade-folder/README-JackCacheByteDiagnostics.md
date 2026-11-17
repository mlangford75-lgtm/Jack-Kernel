# Jack Kernel — Byte-Level Cache Prefix Diagnostic Experiment

This is a surgical local-only upgrade for the **installed** PR #163 Universal Cache Orchestrator experiment. It does not alter prompts, routing decisions, model parameters, memory, tool authority, or the A1/Stage 2 lifecycle. It does not push or merge GitHub changes.

## Install with PowerShell

1. Stop Jack before applying the patch.
2. Download `Jack_Cache_Byte_Diagnostics_PowerShell.zip` into the Windows Downloads folder.
3. Open PowerShell and run:

```powershell
$archive = "$env:USERPROFILE\Downloads\Jack_Cache_Byte_Diagnostics_PowerShell.zip"
$upgrade = "$env:USERPROFILE\Desktop\Jack_Cache_Upgrade"
Expand-Archive -LiteralPath $archive -DestinationPath $upgrade -Force
& "$upgrade\Install-JackCacheByteDiagnostics.ps1"
```

The installer verifies that `Jack_Kernel\jack_kernel.py` already contains the experimental `CacheOrchestrator` integration, checks exact source anchors, backs up the original to `%APPDATA%\JackKernel\backups`, patches in-place, and validates Python syntax and focused tests. It refuses duplicate installations. On validation failure, it restores the original `jack_kernel.py` and removes the two files it added.

Start Jack as before:

```powershell
& "$env:USERPROFILE\Desktop\Jack_Cache_Upgrade\Run-JackWithCache.ps1" -Policy auto
```

Select Balanced. In **one conversation**, request a single Bash tool command and wait for the result, to reproduce the first-continuation fingerprint change:

```text
Run Bash: python -c "print('CACHE_PREFIX_PROBE')". Report the output. Do not modify files.
```

Optionally use a second turn with an explicitly sequential failing tool and recovery, but it is not required to establish the first-system-message divergence.

## Read the logs

Find records beginning with:

```
Jack cache byte-prefix diagnostic: {"schema":"jack.cache.byte_prefix.v1", ...}
```

For the first Stage 1 tool continuation, look at:

- `same_stage.relation`: `first_message_changed` or `append_only`.
- `same_stage.first_changed_message_json.first_differing_utf8_byte_offset`: first changed byte of canonical **message JSON**, if captured.
- `same_stage.first_system_content_utf8.first_differing_utf8_byte_offset`: first changed byte of system **content**, if captured.
- `same_stage.pre_fold_system_regions.first_changed_pre_fold_region`: `jack_stage_directive`, `caller_or_source_system_1`, or `jack_injected_system_1`, as available.
- `same_stage.pre_fold_system_regions.region_byte_difference`: within-region offset, if captured.

All offsets are **zero-based UTF-8 byte positions**, not token positions. They diagnose Jack's model-facing JSON and text, **not LM Studio's rendered/tokenized prompt** or physical KV-cache state. Compare with LM Studio LCP selection and prompt-evaluation counters for the same requests.

If bytes diverge beyond the capture cap, the log explicitly reports `unknown_beyond_capture_cap` rather than inventing an offset.

## Privacy, bounds, and universality

- No prompt text is written to log or stored by the probe; it holds only process-local keyed prefix digests and SHA-256 fingerprints. No token data, file writes, or prompt alterations.
- Defaults to 128 KiB of per-field capture and 256 KiB total message prefix capture per request. Long histories have bounded digest storage; they may report an unknown offset.
- Disable instrumentation with `JACK_CACHE_PREFIX_BYTE_DIAGNOSTICS=0` before launching Jack, or set `JACK_CACHE_PREFIX_BYTE_CAP` to 1024–262144.
- Backend-independent; no slot API is required. Diagnostic failures are warnings and do not block inference.

## Unit verification

The package includes `test_jack_cache_prefix_diagnostics.py`. The installer executes these and existing `test_jack_cache_orchestrator.py` from the Jack repo. The byte-prefix module's 8 focused unit tests passed in the build environment. Actual installation and full regressions must be verified on your Windows host.
