from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Any, Iterable, Optional, Tuple

from jack_kernel import SecurityOutcome


@dataclass(frozen=True)
class ConsequenceFact:
    """One already-established deterministic authority fact.

    Phase 5 consumes this representation; it does not discover the fact or
    reinterpret the producer's existing severity. Non-authoritative state is
    not valid gate input and should remain outside the disposition boundary.
    """

    producer: str
    outcome: SecurityOutcome
    reason: str = ""
    authoritative: bool = True


@dataclass(frozen=True)
class ConsequenceDecision:
    outcome: SecurityOutcome
    decisive_fact: Optional[ConsequenceFact]
    evaluated_producers: Tuple[str, ...]


def evaluate_consequence(facts: Iterable[ConsequenceFact]) -> ConsequenceDecision:
    """Compose deterministic producer outcomes without inventing new facts.

    HARD_INTERRUPT is the only universally dominant outcome because an already
    established hard-security fact may not be masked by a recoverable denial.
    Among non-hard outcomes, the caller-provided order is preserved. That keeps
    existing boundary semantics authoritative instead of creating a new global
    Phase-5 precedence table.
    """

    items = tuple(facts)
    if not items:
        raise ValueError("Consequence Gate requires at least one authoritative fact")

    for fact in items:
        if not isinstance(fact, ConsequenceFact):
            raise TypeError("Consequence Gate accepts ConsequenceFact values only")
        if not fact.producer.strip():
            raise ValueError("Consequence fact producer must be named")
        if not fact.authoritative:
            raise ValueError(
                f"Non-authoritative fact from {fact.producer!r} cannot drive disposition"
            )
        if not isinstance(fact.outcome, SecurityOutcome):
            raise TypeError(
                f"Consequence fact {fact.producer!r} must use SecurityOutcome"
            )

    producers = tuple(fact.producer for fact in items)

    for fact in items:
        if fact.outcome is SecurityOutcome.HARD_INTERRUPT:
            return ConsequenceDecision(
                outcome=SecurityOutcome.HARD_INTERRUPT,
                decisive_fact=fact,
                evaluated_producers=producers,
            )

    for fact in items:
        if fact.outcome is not SecurityOutcome.ALLOW:
            return ConsequenceDecision(
                outcome=fact.outcome,
                decisive_fact=fact,
                evaluated_producers=producers,
            )

    return ConsequenceDecision(
        outcome=SecurityOutcome.ALLOW,
        decisive_fact=None,
        evaluated_producers=producers,
    )


def _single_fact_decision(producer: str, outcome: SecurityOutcome, reason: str = "") -> SecurityOutcome:
    return evaluate_consequence(
        (ConsequenceFact(producer=producer, outcome=outcome, reason=reason),)
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
                "tool_schema",
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
                        "path_policy",
                        SecurityOutcome.HARD_INTERRUPT,
                        "existing Phase-4 restricted-path hard interrupt",
                    )
                    if decision is not SecurityOutcome.HARD_INTERRUPT:
                        raise AssertionError("Consequence Gate masked Phase-4 hard security")
                raise

            outcome = (
                SecurityOutcome.DENY_AND_CONTINUE
                if errors
                else SecurityOutcome.ALLOW
            )
            _single_fact_decision(
                "path_policy",
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
                "executor_admission",
                outcome,
                "existing Phase-4 executor-admission result",
            )
            if decision is not outcome:
                raise AssertionError("Consequence Gate changed executor-admission semantics")
            return result

        jk._phase4_executor_admission_decision = governed_executor_admission

    jk._JACK_CONSEQUENCE_GATE_INSTALLED = True
