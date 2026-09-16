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

Accepted bridge SHA-256:

`E758883F3C18CBEFBF5590C720DBEDF7AB8E85D3314B5EA77E277B1A8C3BD3E4`

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
