# Phase 4 — capability-aware safe defaults (2026-10-21)

## Purpose

The host-derived Windows NEVER roots are intentionally conservative, but treating every ordinary **read** as a terminal security violation needlessly interrupts benign agent work. The safe-default change adds an exception at the *recognized tool capability boundary* rather than deleting those roots.

## Policy

- Raw `authorize_represented_path()` and Phase-5 source authority facts keep legacy NEVER behavior. No arbitrary caller-supplied 'read_only' switch exists.
- Known `read`/`ls` structured operations and narrow single-command shell reads may inspect ordinary `C:\Windows` metadata.
- `write`, `edit`, other mutators, unknown shell commands, scripts, wrappers, pipelines, redirects, and dynamic command syntax remain under legacy NEVER enforcement.
- Sensitive default Windows subtrees (including registry hives, machine policy, task configuration, credential-protection locations, unattended setup material, and event logs) return recoverable denial for otherwise read-only operations.
- Any explicit nondefault NEVER root remains terminal, including one nested below the Windows system root.
- An active Workspace Lock remains authoritative: even a read-only system inspection outside that workspace is denied and continued.
- Phase-7 protected credential resources are denied independently.
- No model prompt, reasoning mode, tool schema, Pi extension, Git main branch, or backend-specific transport behavior is changed.

## Limitations

This is capability-aware represented-path authorization, **not** an OS-level read-only sandbox. Executing arbitrary shell commands remains outside the narrowly classified exception. Symbolic links and final resolved filesystem objects require executor/OS enforcement, as before.

The narrow default exception applies only to the system-root directory; `C:\Boot`, `C:\Recovery`, and `System Volume Information` remain strict NEVER roots.

## Validation and migration

Legacy Phase-4 tests historically expect even `read C:\Windows\...` and `cat C:\Windows\...` to hard-interrupt. Those specific cases must be updated to assert capability-specific behavior while retaining explicit tests for hard denials of writes, explicit NEVER paths, and ambiguous shell operations. Full Windows CI must pass before merge.

This proposal is separate from the local Phase 3F context-accounting work and must not pull uncommitted local Agentic changes into GitHub.
