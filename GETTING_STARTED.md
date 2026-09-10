# Getting Started with Jack Kernel v.0.1.1

Jack Kernel sits between an agent/client and an OpenAI-compatible model backend. The default local topology is:

`agent -> Jack Kernel :8001 -> backend`

LM Studio is the default backend at `http://127.0.0.1:1234/v1`.

## 1. Requirements

- Windows 10/11
- Python 3
- A supported OpenAI-compatible backend with a model loaded

Install Jack's Python dependency from the repository root:

```powershell
py -3 -m pip install -r requirements.txt
```

## 2. Start Jack

From the repository root:

```powershell
.\start.bat
```

Jack's default agent-facing endpoint is:

`http://127.0.0.1:8001/v1`

The caller-facing model ID is:

`jack-kernel`

Health check:

`http://127.0.0.1:8001/health`

Port 8000 is intentionally left available for a custom OpenAI-compatible/vLLM backend. Do not globally replace backend port 8000 with Jack's listener port 8001.

## 3. Choose a mode

- **Off** — native thinking disabled.
- **Medium** — direct native Medium reasoning.
- **X-High** — direct native X-High reasoning.
- **Deep Research** — X-High Thesis -> Medium Antithesis -> X-High authoritative Synthesis.
- **Agentic** — native Stage-1 cognition followed by semantic Jack XML consolidation.
- **Code Debugging** — five-pass report-only forensic audit at Medium reasoning.
- **Code Debugging (Deep)** — the same forensic topology at X-High reasoning.

Deep Research Antithesis uses **Medium @ 0.70 with Preserve Thinking ON, tools OFF, and zero final-answer authority**.

## 4. Optional Pi integration

Install the bundled Pi provider extension:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Pi\install-jack-kernel-extension.ps1"
```

Then restart Pi or reload its extensions.

The extension defaults to `http://127.0.0.1:8001` and reads Jack's live backend context metadata. If `%USERPROFILE%\.pi\agent\jack-kernel.json` exists, its `url` overrides that default. The bundled loader tolerates a UTF-8 BOM in this JSON file.

## 5. Run the regression checks

From the repository root:

```powershell
py -3 tests\test_backend_retry.py
py -3 tests\test_debugging_modes.py
py -3 tests\test_resilience.py
py -3 tests\test_release_profiles.py
```

For the architecture, context-lifetime rules, authority model, Agentic XML semantics, Code Debugging topology, and limitations, see `Documentation/Jack_Kernel_Plain_English_Master_Guide_v0.1.1.docx`.
