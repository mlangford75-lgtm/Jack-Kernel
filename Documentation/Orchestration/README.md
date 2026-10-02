# Orchestration Documentation

Orchestration Gateway v2 is the current supervisor-to-worker control subsystem for Jack Kernel v0.1.1.

## Current normative documents

- [`ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md`](ORCHESTRATION_GATEWAY_V2_TECHNICAL_SPEC.md) — canonical protocol, lifecycle, authority, replay, settlement, identity, and supervisor compatibility contract.
- [`ORCHESTRATOR_INSTRUCTIONS.md`](ORCHESTRATOR_INSTRUCTIONS.md) — operating instructions for supervisory agents, including local and cloud-supervisor use.

## Historical evidence

- [`Historical/`](Historical/) — dated acceptance evidence and earlier bridge/runtime identities.

Historical acceptance artifacts are evidence for what was validated at the time. They are not current bridge/runtime identity authority merely because they remain in the repository.

## Current security interaction

The current Kernel security checkpoint is Phase 6. For exact current security claims and identities, read [`../../CURRENT_SECURITY_STATUS.md`](../../CURRENT_SECURITY_STATUS.md).

The orchestration authority model remains separate from the security phase stack:

- **Phases 0–3:** release-boundary security may withhold model material, but does not give a supervisor authority to fabricate task/run state, cancellation, settlement, or worker termination.
- **Phase 4:** represented-path and Workspace Lock decisions remain Kernel security decisions. They do not transfer lifecycle authority to the supervisor.
- **Phase 5:** the deterministic Consequence Gate selects the Kernel disposition for typed authoritative facts at the relevant consequence boundary. The supervisor cannot override or manufacture that disposition, and the outcome does not automatically widen to the whole task/run/process.
- **Phase 6:** the Authority & Security Ledger records selected established Kernel decisions/events. It is not Pi lifecycle authority, task/run/epoch authority, cancellation authority, settlement authority, or runtime-observability authority.

The separation remains:

```text
security decision / security record
!=
orchestration lifecycle fact
!=
runtime observability
!=
physical settlement
```

Pi and the existing orchestration machinery remain authoritative for lifecycle facts within their validated boundaries.

## Core orchestration doctrine

- ports and sockets are transport locators, not logical identity;
- live runtime identity verification outranks stale observational manifest status;
- observability does not become cognition, cancellation, or commit authority;
- client disconnect is not implicit cognition cancellation;
- cancellation and physical settlement remain separate facts;
- the supervisor may interpret deterministic state but must not fabricate it;
- recoverable transport or telemetry failure must not destroy otherwise valid cognition merely because coordination became inconvenient.
