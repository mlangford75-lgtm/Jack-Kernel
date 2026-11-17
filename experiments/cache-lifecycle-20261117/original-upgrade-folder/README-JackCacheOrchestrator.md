# Jack Kernel — Universal Cache Orchestrator (PR #163 experiment)

This package implements **optional, stage-aware cache affinity** with a PowerShell installer for the current PR #163 checkout. It does not change the Prime Directive, user prompts, stage source selection, memory commits, Work ID placement, or tool outcomes. It patches both streaming and nonstreaming inference paths.

**Status:** Experimental. The portable Python routing module passed 11 local unit tests; the full Jack integration regression and actual LM Studio/llama.cpp KV behavior must be validated on the Windows machine. The provided installer checks anchors against the exact PR revision, compiles the modified Python files, and runs the included unit tests. No GitHub PR or mainline changes are performed by this package.

## Installation (PowerShell)

Extract this ZIP to a folder outside `Jack_Kernel`, e.g. `Desktop\Jack_Cache_Upgrade`. Run PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
& "C:\Users\default.DESKTOP-M8143Q1\Desktop\Jack_Cache_Upgrade\Install-JackCacheOrchestrator.ps1"
```

The installer requires a **clean checkout** of PR #163 commit `f8c0abc0ae8220808267dac4ac38e4ebb9290403`. It creates a **local** branch named `experiment/universal-cache-orchestrator-20261117`, modifies `jack_kernel.py`, adds `jack_cache_orchestrator.py` and its test, and checks syntax/tests. It refuses to overwrite local changes; on failure it restores the original `jack_kernel.py` and removes its added files. It does not push or merge anything.

## Run in PowerShell

### Default auto mode — works on any existing backend

```powershell
& "C:\Users\default.DESKTOP-M8143Q1\Desktop\Jack_Cache_Upgrade\Run-JackWithCache.ps1" -Policy auto
```

In this default mode, when there is only **one** LM Studio server and it exposes **no external slot-selection capability**, the orchestrator records routing decisions and preserves existing behavior. **It cannot guarantee physical isolation on one unsupported server.** The existing backend still selects/evicts the physical KV cache. This is intentionally fail-open, not a guaranteed performance upgrade.

### Physical isolation using two compatible OpenAI endpoints

Configure a separate Stage 2 server with the same model ID available:

```powershell
& "C:\Users\default.DESKTOP-M8143Q1\Desktop\Jack_Cache_Upgrade\Run-JackWithCache.ps1" `
  -Policy prefer_isolated `
  -AuxBaseUrl "http://127.0.0.1:2234/v1"
```

Primary endpoint continues to use Jack's existing `JACK_BACKEND_BASE_URL`. When Stage 2 is configured as an auxiliary stage, its requests go to the auxiliary endpoint, isolating **server-owned** KV caches. Only explicitly identified auxiliary stages route there. A connection refusal or HTTP 404 on that optional endpoint falls back to the primary backend and disables repeated use of the auxiliary endpoint for the running process. If the primary and auxiliary endpoints do not serve the same model ID, the secondary inference may be rejected. Do not supply an untrusted auxiliary URL: it receives the same backend authentication headers.

### Direct llama.cpp explicit slots (opt-in)

Use this **only** with raw `llama-server` configured for at least two slots and when its chat completion route supports `id_slot`:

```powershell
$env:JACK_BACKEND_PROFILE = 'llamacpp'
& "C:\Users\default.DESKTOP-M8143Q1\Desktop\Jack_Cache_Upgrade\Run-JackWithCache.ps1" `
  -Policy prefer_isolated -SlotAdapter llamacpp -PrimarySlot 0 -AuxSlot 1
```

This sends `id_slot=0` to primary inference and `id_slot=1` to Stage 2. A backend HTTP 400 rejecting the optional slot field causes a retry without that field and disables further slot hints for this process. The adapter refuses explicit slot hints if Jack's configured concurrency is greater than one, or when the profile is not `llamacpp`. Slot capacity must be configured by the **server operator**; Jack cannot create slots by adding an API parameter.

### Shared baseline (control test)

```powershell
& "C:\Users\default.DESKTOP-M8143Q1\Desktop\Jack_Cache_Upgrade\Run-JackWithCache.ps1" -Policy shared
```

No routing or slot hints are sent, which is the PR #163-compatible behavior.

## Settings

| Env variable | Default | Meaning |
|---|---|---|
| `JACK_CACHE_POLICY` | `auto` | `auto`, `shared`, `prefer_isolated` |
| `JACK_CACHE_AUX_BASE_URL` | empty | Optional fully qualified, separate OpenAI-compatible `/v1` endpoint |
| `JACK_CACHE_SLOT_ADAPTER` | `off` | `off` or explicit `llamacpp` |
| `JACK_CACHE_PRIMARY_SLOT` | `0` | Primary cache slot for eligible raw llama.cpp |
| `JACK_CACHE_AUX_SLOT` | `1` | Auxiliary cache slot; must differ from primary |
| `JACK_CACHE_MIN_PRIMARY_BYTES` | `8192` | Auto mode isolation threshold, approximate serialized-message bytes, **not tokens** |
| `JACK_CACHE_AUX_STAGES` | `Agentic native pass 2` | Semicolon-separated exact stage names eligible for auxiliary routing |

The policy and slot choices are host-only. No Work ID or cache ID is inserted into the model-facing prompt. A tool failure does **not** switch the cache lane.

## Verification and limitations

After installation:

```powershell
cd 'C:\Users\default.DESKTOP-M8143Q1\Desktop\Jack_Kernel'
python -m pytest -q tests/test_jack_cache_orchestrator.py
python -m pytest -q tests/test_agentic_universal_cache_prefix.py
python -m pytest -q
```

Look for `Jack cache routing` in the kernel logs. These logs record requested transport, not a confirmed KV hit. Compare per-request slot selection, cached tokens (if backend reports them), prefills, and prompt-fingerprint diagnostics from PR #163. Testing on separate backends is required to demonstrate physical cache retention. A successful tool call and a failed tool call should both remain on the primary lane, barring policy changes.

**Not included:** backend slot creation, independent cache migration, guaranteed cache restoration, a new provider-specific LM Studio slot API, or per-agent physical slot leasing on a shared concurrent backend. Those require additional backend capabilities and tests.
