# Pi Integration for Jack Kernel v0.1.1

This directory contains two separate Pi integrations:

1. `jack-kernel.ts` — Jack provider/context-window synchronization.
2. `pi-control-bridge.ts` — accepted private Primary-Pi control bridge for Orchestration Gateway v2.

They serve different authority boundaries.

## Provider/context synchronization

Jack exposes the resolved backend context window through its model metadata. Pi custom models can retain stale static context metadata, so `jack-kernel.ts` registers/refreshes the `jack-kernel` provider from Jack's live metadata.

Install:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\install-jack-kernel-extension.ps1"
```

Default Jack root:

`http://127.0.0.1:8001`

The authority chain is:

`loaded backend context -> Jack detection -> Jack model metadata -> Pi contextWindow`

## Accepted Orchestration Gateway v2 control bridge

`pi-control-bridge.ts` runs inside the **privileged Primary Pi worker**. It is private to Jack; Jack Orchestrator does not connect to it directly and does not receive its control token.

Install with Primary Pi stopped:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\install-pi-control-bridge-v2.ps1"
```

The installer is idempotent with respect to bridge configuration. If `~/.pi/agent/jack-kernel.json` is missing the orchestration fields, it provisions only the missing `controlPort` and `controlToken`; the default provisioned control port is `8013`. Existing provider settings, custom control ports, and existing control tokens are preserved.

Restart Primary Pi after installation.

Accepted Windows CRLF bridge SHA-256:

`93A6843CDAAEDA637474B584919ED003930296DE281570E3DDC391F54EF65565`

Canonical repository LF SHA-256:

`8FFD33FD33AE15A785E2BF9015F17FC14F1DE27B09515D5E868EC163D54C15F0`

## Multi-endpoint worker bridges

The default private bridge remains `127.0.0.1:8013` for compatibility. Multi-endpoint operation adds per-process environment overrides without changing the existing single-worker configuration file.

For an effect-capable Jack lane, start a dedicated named Pi worker:

```powershell
.\start-pi-worker.ps1 -BridgeId debug-worker-01 -ControlPort 8014 -ControlToken "<worker-specific-secret>"
```

The bridge supports:

- `JACK_PI_CONTROL_PORT` — preferred loopback control port; `0` requests an OS-assigned port.
- `JACK_PI_CONTROL_PORT_FALLBACK` — when enabled, an occupied preferred port falls back to an OS-assigned loopback port.
- `JACK_PI_CONTROL_BRIDGE_ID` — stable worker/bridge identity.
- `JACK_PI_CONTROL_TOKEN` — explicit private control credential.
- `JACK_PI_CONTROL_REGISTRY_DIR` — optional bridge-manifest directory override.

A running bridge publishes a local manifest containing its bridge ID, session instance ID, PID, preferred port, actual port, and fallback state. Named Jack worker bindings require an explicit `JACK_PI_CONTROL_TOKEN`; they do not inherit the ambient persisted token as worker-scoped authority. Jack also sends `X-Jack-Bridge-Id` on named control requests, and a mismatched named bridge rejects the request.

Multiple Jack lanes must not implicitly share one privileged Pi worker in the first multi-endpoint release. A future shared multi-tenant worker requires its own independently validated worker-side isolation contract.

### Run-bound identity

For an accepted controlled task, the bridge:

1. creates a task UUID and independent `runId`;
2. inserts a private per-dispatch correlation marker;
3. accepts/strips that marker only at the Pi `input` boundary for extension-injected input;
4. binds the pending identity through `before_agent_start`;
5. freezes `{taskId, runId, runEpoch}` at `agent_start`;
6. snapshots that positive binding for message/tool callbacks;
7. clears low-level attribution at `agent_end` so delayed events do not inherit stale ownership;
8. reuses the same `runId` and advances `runEpoch` on automatic retry/continuation;
9. closes the complete controlled run at `agent_settled`.

Unowned events remain unowned rather than borrowing the current task identity.

### Settlement ordering correction

The final accepted bridge clears `controlRun` and `activeRun` **before** emitting the terminal task snapshot from `agent_settled`. This ensures the public settled task event reports:

- the same task/run identity;
- `settledAt` populated;
- `runOpen:false`.

This is a correctness repair discovered during live cancellation acceptance; it does not change the architecture or narrow valid behavior.

### Cancellation

Cancellation is best-effort and becomes visible immediately. Physical settlement is distinct. Until the cancelled control run reaches `agent_settled`, a new controlled task is rejected. A queued cancelled private marker is swallowed at the exact input boundary rather than beginning model cognition.

## Authority boundary

Jack Orchestrator is a separate cognition-only supervisory client. It should use only Jack's public surfaces:

- cognition: `http://127.0.0.1:8001/v1`
- supervision: `http://127.0.0.1:8001/jack/orchestration`

The private bridge at `127.0.0.1:8013`, its `controlToken`, backend endpoints, and Primary Pi mutable state remain behind Jack.
