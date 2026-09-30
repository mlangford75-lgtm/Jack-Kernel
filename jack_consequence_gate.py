from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, Iterable, Optional, Tuple

from jack_kernel import SecurityOutcome


class ConsequenceFactKind(str, Enum):
    """Deterministic authority domains Phase 5 is permitted to compose.

    The enum is intentionally closed. Ordinary telemetry, UI state, logging
    health, natural-language claims, and other observational data are not fact
    kinds and therefore cannot enter disposition merely by naming themselves
    authoritative.
    """

    STAGE_AUTHORITY = "stage_authority"
    TOOL_AUTHORITY = "tool_authority"
    TOOL_SCHEMA = "tool_schema"
    TASK_AUTHORITY = "task_authority"
    RUN_AUTHORITY = "run_authority"
    RUN_EPOCH_AUTHORITY = "run_epoch_authority"
    PATH_POLICY = "path_policy"
    WORKSPACE_POLICY = "workspace_policy"
    EVIDENCE_PROVENANCE = "evidence_provenance"
    APPROVAL_STATE = "approval_state"
    SETTLEMENT_STATE = "settlement_state"
    SECURITY_HEALTH = "security_health"
    EXECUTOR_ADMISSION = "executor_admission"


@dataclass(frozen=True)
class ConsequenceFact:
    """One already-established deterministic authority fact.

    Phase 5 consumes this representation; it does not discover the fact or
    reinterpret the producer's existing severity. Only the explicit authority
    domains above are accepted by the shared gate.
    """

    kind: ConsequenceFactKind
    outcome: SecurityOutcome
    reason: str = ""


@dataclass(frozen=True)
class ConsequenceDecision:
    outcome: SecurityOutcome
    decisive_fact: Optional[ConsequenceFact]
    evaluated_kinds: Tuple[ConsequenceFactKind, ...]


def evaluate_consequence(facts: Iterable[ConsequenceFact]) -> ConsequenceDecision:
    """Compose deterministic producer outcomes without inventing new facts.

    HARD_INTERRUPT is the only universally dominant outcome because an already
    established hard-security fact may not be masked by a recoverable denial.
    If authoritative producers disagree between distinct non-hard dispositions,
    the gate surfaces the inconsistency instead of inventing a new precedence
    rule for Phase 5.
    """

    items = tuple(facts)
    if not items:
        raise ValueError("Consequence Gate requires at least one authority fact")

    for fact in items:
        if not isinstance(fact, ConsequenceFact):
            raise TypeError("Consequence Gate accepts ConsequenceFact values only")
        if not isinstance(fact.kind, ConsequenceFactKind):
            raise TypeError("Consequence fact kind must be ConsequenceFactKind")
        if not isinstance(fact.outcome, SecurityOutcome):
            raise TypeError(
                f"Consequence fact {fact.kind.value!r} must use SecurityOutcome"
            )

    kinds = tuple(fact.kind for fact in items)

    for fact in items:
        if fact.outcome is SecurityOutcome.HARD_INTERRUPT:
            return ConsequenceDecision(
                outcome=SecurityOutcome.HARD_INTERRUPT,
                decisive_fact=fact,
                evaluated_kinds=kinds,
            )

    non_allow = tuple(
        fact for fact in items if fact.outcome is not SecurityOutcome.ALLOW
    )
    if not non_allow:
        return ConsequenceDecision(
            outcome=SecurityOutcome.ALLOW,
            decisive_fact=None,
            evaluated_kinds=kinds,
        )

    outcomes = frozenset(fact.outcome for fact in non_allow)
    if len(outcomes) != 1:
        rendered = ", ".join(
            f"{fact.kind.value}={fact.outcome.value}" for fact in non_allow
        )
        raise RuntimeError(
            "Consequence Gate received conflicting authoritative non-hard "
            f"dispositions: {rendered}"
        )

    decisive = non_allow[0]
    return ConsequenceDecision(
        outcome=decisive.outcome,
        decisive_fact=decisive,
        evaluated_kinds=kinds,
    )


def _single_fact_decision(
    kind: ConsequenceFactKind,
    outcome: SecurityOutcome,
    reason: str = "",
) -> SecurityOutcome:
    return evaluate_consequence(
        (ConsequenceFact(kind=kind, outcome=outcome, reason=reason),)
    ).outcome


def install(jk: Any) -> None:
    """Converge existing consequence surfaces on the shared Phase-5 gate.

    The wrapped producers remain authoritative. Their established return values,
    exceptions, containment, and executor behavior are preserved exactly; this
    installer only routes their already-determined disposition through the
    shared gate. Missing future producers (approval/integrity health, etc.) are
    intentionally not fabricated.
    """

    if getattr(jk, "_JACK_CONSEQUENCE_GATE_INSTALLED", False):
        return

    jk.ConsequenceFactKind = ConsequenceFactKind
    jk.ConsequenceFact = ConsequenceFact
    jk.ConsequenceDecision = ConsequenceDecision
    jk.evaluate_consequence = evaluate_consequence

    original_validation = getattr(jk, "_tool_call_validation_errors", None)
    if callable(original_validation):
        @wraps(original_validation)
        def governed_validation(calls: Any, tools: Any) -> Any:
            errors = original_validation(calls, tools)
            outcome = (
                SecurityOutcome.DENY_AND_CONTINUE
                if errors
                else SecurityOutcome.ALLOW
            )
            _single_fact_decision(
                ConsequenceFactKind.TOOL_SCHEMA,
                outcome,
                "existing tool/schema validation result",
            )
            return errors

        jk._tool_call_validation_errors = governed_validation

    original_partition = getattr(jk, "_phase4_partition_structured_tool_calls", None)
    phase4_interrupt = getattr(jk, "Phase4RestrictedPathInterrupt", None)
    if callable(original_partition):
        @wraps(original_partition)
        def governed_partition(calls: Any) -> Any:
            try:
                allowed, errors = original_partition(calls)
            except BaseException as exc:
                if phase4_interrupt is not None and isinstance(exc, phase4_interrupt):
                    decision = _single_fact_decision(
                        ConsequenceFactKind.PATH_POLICY,
                        SecurityOutcome.HARD_INTERRUPT,
                        "existing Phase-4 restricted-path hard interrupt",
                    )
                    if decision is not SecurityOutcome.HARD_INTERRUPT:
                        raise AssertionError(
                            "Consequence Gate masked Phase-4 hard security"
                        )
                raise

            outcome = (
                SecurityOutcome.DENY_AND_CONTINUE
                if errors
                else SecurityOutcome.ALLOW
            )
            _single_fact_decision(
                ConsequenceFactKind.PATH_POLICY,
                outcome,
                "existing Phase-4 represented-target decision",
            )
            return allowed, errors

        jk._phase4_partition_structured_tool_calls = governed_partition

    original_executor_admission = getattr(jk, "_phase4_executor_admission_decision", None)
    if callable(original_executor_admission):
        @wraps(original_executor_admission)
        def governed_executor_admission(*args: Any, **kwargs: Any) -> Any:
            result = original_executor_admission(*args, **kwargs)
            raw_outcome = result.get("outcome") if isinstance(result, dict) else None
            if isinstance(raw_outcome, SecurityOutcome):
                outcome = raw_outcome
            else:
                try:
                    outcome = SecurityOutcome(str(raw_outcome))
                except ValueError:
                    return result
            decision = _single_fact_decision(
                ConsequenceFactKind.EXECUTOR_ADMISSION,
                outcome,
                "existing Phase-4 executor-admission result",
            )
            if decision is not outcome:
                raise AssertionError(
                    "Consequence Gate changed executor-admission semantics"
                )
            return result

        jk._phase4_executor_admission_decision = governed_executor_admission

    register_manifest = getattr(jk, "_register_runtime_manifest_components", None)
    if callable(register_manifest):
        register_manifest({
            "jack_consequence_gate.py": Path(__file__).resolve(),
        })

    jk._JACK_CONSEQUENCE_GATE_INSTALLED = True
