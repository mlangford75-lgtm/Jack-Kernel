# Pi context-window synchronization

Jack Kernel exposes the resolved backend context window through OpenAI-compatible model metadata and an LM-Studio-compatible `GET /api/v1/models` endpoint.

Pi custom models normally keep `contextWindow` in Pi-side model metadata. A stale static `models.json` entry can therefore continue to show an old value even when Jack advertises the correct backend context. The bundled `jack-kernel.ts` extension removes that static mismatch by registering the `jack-kernel` provider from Jack's live model metadata at Pi startup and refreshing it after assistant turns.

## Install on Windows

From this `Pi` folder, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-jack-kernel-extension.ps1
```

Then start Jack and restart Pi (or use `/reload`).

The extension defaults to Jack at `http://127.0.0.1:8001`. For another address or an authenticated Jack server, create `%USERPROFILE%\.pi\agent\jack-kernel.json`:

```json
{
  "url": "http://127.0.0.1:8001",
  "token": "$JACK_API_KEY"
}
```

The token may be literal or an environment-variable reference beginning with `$`.

The bundled loader also strips a leading UTF-8 BOM (`U+FEFF`) before parsing this file, so PowerShell-created UTF-8 JSON does not fail at `JSON.parse`.

The resulting authority chain is:

`LM Studio loaded context -> Jack -> /api/v1/models -> Pi provider contextWindow`

A loaded LM Studio instance at 80,000 tokens therefore registers `jack-kernel` in Pi at 80,000 tokens rather than relying on a static Pi-side guess.
