# Jack Stage-1 Prefix Stabilization (experimental)

**Local-only patch.** Requires both previous local experiments (`CacheOrchestrator` and `CacheBytePrefixProbe`). Does not push or merge GitHub.

Stop Jack, extract the ZIP into the existing `Desktop\Jack_Cache_Upgrade` folder, and run:

```powershell
& "$env:USERPROFILE\Desktop\Jack_Cache_Upgrade\Install-JackStage1CacheStability.ps1" -FullSuite
```

Without `-FullSuite`, the installer runs all three targeted cache test modules and Python syntax checking. On any failure, it restores the previous `jack_kernel.py` and removes the newly introduced module and test. A timestamped backup is preserved in `%APPDATA%\JackKernel\backups`.

After installation:

```powershell
& "$env:USERPROFILE\Desktop\Jack_Cache_Upgrade\Run-JackWithCache.ps1" -Policy auto
```

Select Balanced. Issue a simple tool request:

```text
Run Bash: python -c "print('CACHE_PREFIX_PROBE')". Report the output. Do not modify files.
```

Send the `Jack Stage-1 system cache stability`, `Agentic transport-prefix diagnostic`, and corresponding LM Studio slot/LCP logs.

## Exact behavior

- Records the initial system message for an authenticated Stage-1 work ID, in bounded process memory only.
- On same-work tool continuation, if the system message is unchanged, sends it unchanged.
- If the new message consists of the original system plus **one pure insertion**, restores the exact original system only in the backend-facing request. The original Stage-1 instructions and all tool messages are retained; canonical history is never modified.
- If the message was rewritten/shortened, the request lacks a recognizable work ID, a tool continuation is not verified, or the system is being legitimately changed for review, **no rewrite occurs**.
- No effect on Stage 2 or on any non-Agentic mode; backend slot routing remains independent.
- Enable/disable per runtime with `JACK_STAGE1_CACHE_STABILITY=1` (default after install) or `0` before launching Jack.

**Limitation:** The source logs identified a 441-byte increase and first-changed-byte offset, but do not show actual changed text. This repair is intentionally restricted to verified pure insertions to avoid discarding changed instructions. If the new system content is not a pure insertion, the patch reports `non_insert_change_preserved` and requests continue unchanged. Even for pure insertions, the new text is excluded from the continuation's model-facing system; use in a local experiment until the inserted instruction is understood. The patch is not evidence that backend KV cache slot isolation works.
