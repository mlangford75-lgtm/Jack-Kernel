from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, Iterable, Optional, Tuple, Union

from jack_kernel import SecurityOutcome


class ContainmentScope(str, Enum):
    """Smallest consequential boundary the Gate is allowed to contain."""

    NONE = "none"
    TOOL_CALL = "tool_call"
    TOOL_BATCH = "tool_batch"
    EXECUTOR_ADMISSION = "executor_admission"
    OVERLAP_ADMISSION = "overlap_admission"
    EVIDENCE_FRAGMENT = "evidence_fragment"
    CONSEQUENCE = "consequence"


class UnmappedAuthorityFact(RuntimeError):
    """An authoritative fact exists but Phase 5 has no justified mapping yet."""


@dataclass(frozen=True)
class StageToolAuthorityFact:
    authorized: bool


@dataclass(frozen=True)
class ToolSchemaFact:
    valid: bool
    errors: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PathPolicyFact:
    never_match: bool = False
    workspace_configured: bool = False
    deterministic: bool = True
    inside_workspace: Optional[bool] = None


@dataclass(frozen=True)
class ExecutorAdmissionIdentityFact:
    runtime_matches: bool
    lane_matches: bool
    call_matches: bool = True


@dataclass(frozen=True)
class SettlementFact:
    run_open: bool
    overlapping_admission_requested: bool


@dataclass(frozen=True)
class EvidenceProvenanceFact:
    origin_known: bool
    forged_reserved_namespace: bool = False


@dataclass(frozen=True)
class ApprovalFact:
    approval_required: bool
    approval_valid: bool


@dataclass(frozen=True)
class LifecycleAuthorityFact:
    task_matches: bool
    run_matches: bool
    run_epoch_matches: bool


AuthorityFact = Union[
    StageToolAuthorityFact,
    ToolSchemaFact,
    PathPolicyFact,
    ExecutorAdmissionIdentityFact,
    SettlementFact,
    EvidenceProvenanceFact,
    ApprovalFact,
    LifecycleAuthorityFact,
]

_AUTHORITY_FACT_TYPES = (
    StageToolAuthorityFact,
    ToolSchemaFact,
    PathPolicyFact,
    ExecutorAdmissionIdentityFact,
    SettlementFact,
    EvidenceProvenanceFact,
    ApprovalFact,
    LifecycleAuthorityFact,
)


@dataclass(frozen=True)
class ConsequenceDecision:
    outcome: SecurityOutcome
    containment_scope: ContainmentScope
    decisive_fact: Optional[AuthorityFact]
    evaluated_fact_types: Tuple[str, ...]


def _single_decision(
    fact: AuthorityFact,
    outcome: SecurityOutcome,
    scope: ContainmentScope,
    *,
    decisive: bool,
) -> ConsequenceDecision:
    return ConsequenceDecision(
        outcome=outcome,
        containment_scope=scope,
        decisive_fact=fact if decisive else None,
        evaluated_fact_types=(type(fact).__name__,),
    )


def _decision_for_fact(fact: AuthorityFact) -> ConsequenceDecision:
    if isinstance(fact, StageToolAuthorityFact):
        if fact.authorized:
            return _single_decision(
                fact, SecurityOutcome.ALLOW, ContainmentScope.NONE, decisive=False
            )
        return _single_decision(
            fact,
            SecurityOutcome.DENY_AND_CONTINUE,
            ContainmentScope.TOOL_CALL,
            decisive=True,
        )

    if isinstance(fact, ToolSchemaFact):
        if fact.valid:
            return _single_decision(
                fact, SecurityOutcome.ALLOW, ContainmentScope.NONE, decisive=False
            )
        return _single_decision(
            fact,
            SecurityOutcome.DENY_AND_CONTINUE,
            ContainmentScope.TOOL_CALL,
            decisive=True,
        )

    if isinstance(fact, PathPolicyFact):
        if fact.never_match:
            return _single_decision(
                fact,
                SecurityOutcome.HARD_INTERRUPT,
                ContainmentScope.TOOL_BATCH,
                decisive=True,
            )
        if fact.workspace_configured and (
            not fact.deterministic or fact.inside_workspace is False
        ):
            return _single_decision(
                fact,
                SecurityOutcome.DENY_AND_CONTINUE,
                ContainmentScope.TOOL_CALL,
                decisive=True,
            )
        return _single_decision(
            fact, SecurityOutcome.ALLOW, ContainmentScope.NONE, decisive=False
        )

    if isinstance(fact, ExecutorAdmissionIdentityFact):
        if fact.runtime_matches and fact.lane_matches and fact.call_matches:
            return _single_decision(
                fact, SecurityOutcome.ALLOW, ContainmentScope.NONE, decisive=False
            )
        return _single_decision(
            fact,
            SecurityOutcome.DENY_AND_CONTINUE,
            ContainmentScope.EXECUTOR_ADMISSION,
            decisive=True,
        )

    if isinstance(fact, SettlementFact):
        if fact.run_open and fact.overlapping_admission_requested:
            return _single_decision(
                fact,
                SecurityOutcome.DENY_AND_CONTINUE,
                ContainmentScope.OVERLAP_ADMISSION,
                decisive=True,
            )
        return _single_decision(
            fact, SecurityOutcome.ALLOW, ContainmentScope.NONE, decisive=False
        )

    if isinstance(fact, EvidenceProvenanceFact):
        if fact.forged_reserved_namespace:
            return _single_decision(
                fact,
                SecurityOutcome.DENY_AND_CONTINUE,
                ContainmentScope.EVIDENCE_FRAGMENT,
                decisive=True,
            )
        # Unknown provenance alone is not proof of a violation.
        return _single_decision(
            fact, SecurityOutcome.ALLOW, ContainmentScope.NONE, decisive=False
        )

    if isinstance(fact, ApprovalFact):
        if fact.approval_required and not fact.approval_valid:
            return _single_decision(
                fact,
                SecurityOutcome.REQUIRE_USER_DECISION,
                ContainmentScope.CONSEQUENCE,
                decisive=True,
            )
        return _single_decision(
            fact, SecurityOutcome.ALLOW, ContainmentScope.NONE, decisive=False
        )

    if isinstance(fact, LifecycleAuthorityFact):
        if fact.task_matches and fact.run_matches and fact.run_epoch_matches:
            return _single_decision(
                fact, SecurityOutcome.ALLOW, ContainmentScope.NONE, decisive=False
            )
        raise UnmappedAuthorityFact(
            "task/run/run_epoch mismatch has authoritative facts but no single "
            "Phase-5 severity may be invented until the exact existing boundary "
            "semantics are mapped"
        )

    raise TypeError(f"Unsupported authority fact type: {type(fact).__name__}")


def evaluate_consequence(facts: Iterable[AuthorityFact]) -> ConsequenceDecision:
    """Map raw deterministic authority facts to disposition and blast radius.

    Callers do not supply a desired SecurityOutcome. The Gate refuses to invent
    precedence among conflicting recoverable outcomes or to silently widen the
    containment scope merely because several facts are evaluated together.
    """

    items = tuple(facts)
    if not items:
        raise ValueError("Consequence Gate requires at least one authority fact")

    for fact in items:
        if not isinstance(fact, _AUTHORITY_FACT_TYPES):
            raise TypeError(
                "Consequence Gate accepts only typed deterministic authority facts"
            )

    decisions = tuple(_decision_for_fact(fact) for fact in items)
    fact_types = tuple(type(fact).__name__ for fact in items)
    non_allow = tuple(
        (fact, decision)
        for fact, decision in zip(items, decisions)
        if decision.outcome is not SecurityOutcome.ALLOW
    )

    if not non_allow:
        return ConsequenceDecision(
            SecurityOutcome.ALLOW,
            ContainmentScope.NONE,
            None,
            fact_types,
        )

    hard = tuple(
        pair
        for pair in non_allow
        if pair[1].outcome is SecurityOutcome.HARD_INTERRUPT
    )
    if hard:
        scopes = frozenset(pair[1].containment_scope for pair in hard)
        if len(scopes) != 1:
            raise RuntimeError(
                "Consequence Gate received hard facts with conflicting containment scopes"
            )
        fact, decision = hard[0]
        return ConsequenceDecision(
            SecurityOutcome.HARD_INTERRUPT,
            decision.containment_scope,
            fact,
            fact_types,
        )

    outcomes = frozenset(pair[1].outcome for pair in non_allow)
    if len(outcomes) != 1:
        raise RuntimeError(
            "Consequence Gate received conflicting authoritative non-hard dispositions"
        )

    scopes = frozenset(pair[1].containment_scope for pair in non_allow)
    if len(scopes) != 1:
        raise RuntimeError(
            "Consequence Gate will not guess a broader containment scope for "
            "multiple non-hard facts"
        )

    fact, decision = non_allow[0]
    return ConsequenceDecision(
        decision.outcome,
        decision.containment_scope,
        fact,
        fact_types,
    )


def install(jk: Any) -> None:
    """Install only live integrations whose mapping and containment are proven.

    Fact contracts may exist before live wiring. A domain is not integrated
    merely because the Gate knows how to evaluate a hypothetical typed fact.
    In particular, schema and path release remain untouched until their raw
    producer seams can satisfy the declared containment scope.
    """

    if getattr(jk, "_JACK_CONSEQUENCE_GATE_INSTALLED", False):
        return

    jk.ContainmentScope = ContainmentScope
    jk.UnmappedAuthorityFact = UnmappedAuthorityFact
    jk.StageToolAuthorityFact = StageToolAuthorityFact
    jk.ToolSchemaFact = ToolSchemaFact
    jk.PathPolicyFact = PathPolicyFact
    jk.ExecutorAdmissionIdentityFact = ExecutorAdmissionIdentityFact
    jk.SettlementFact = SettlementFact
    jk.EvidenceProvenanceFact = EvidenceProvenanceFact
    jk.ApprovalFact = ApprovalFact
    jk.LifecycleAuthorityFact = LifecycleAuthorityFact
    jk.ConsequenceDecision = ConsequenceDecision
    jk.evaluate_consequence = evaluate_consequence

    # Executor runtime/lane identity has a clear existing policy and an exact
    # admission-only containment boundary. Gate it before the legacy function
    # repeats the same identity comparison, while preserving structural/protocol
    # validation order and the established HTTP response behavior.
    original_executor_admission = getattr(jk, "_phase4_executor_admission_decision", None)
    if callable(original_executor_admission):
        @wraps(original_executor_admission)
        def governed_executor_admission(
            payload: Any,
            *,
            expected_call: Optional[dict[str, Any]] = None,
        ) -> Any:
            allowed_fields = {
                "protocol_version",
                "runtime_id",
                "lane_id",
                "tool_call_id",
                "tool_name",
                "arguments",
                "executor_cwd",
                "executor_platform",
                "command_dialect",
            }
            protocol_version = getattr(
                jk, "PHASE4_EXECUTOR_ADMISSION_PROTOCOL_VERSION", None
            )
            structurally_gateable = (
                isinstance(payload, dict)
                and not (set(payload) - allowed_fields)
                and payload.get("protocol_version") == protocol_version
            )
            if structurally_gateable:
                runtime_matches = (
                    str(payload.get("runtime_id") or "").strip()
                    == str(getattr(jk, "RUNTIME_ID", ""))
                )
                lane_matches = (
                    str(payload.get("lane_id") or "").strip()
                    == str(getattr(jk, "LANE_ID", ""))
                )
                decision = evaluate_consequence((
                    ExecutorAdmissionIdentityFact(
                        runtime_matches=runtime_matches,
                        lane_matches=lane_matches,
                        call_matches=True,
                    ),
                ))
                if decision.outcome is SecurityOutcome.DENY_AND_CONTINUE:
                    if (
                        decision.containment_scope
                        is not ContainmentScope.EXECUTOR_ADMISSION
                    ):
                        raise AssertionError(
                            "Executor identity denial escaped admission scope"
                        )
                    if not runtime_matches:
                        raise jk.HTTPException(
                            status_code=409,
                            detail="Phase-4 executor admission runtime identity mismatch",
                        )
                    if not lane_matches:
                        raise jk.HTTPException(
                            status_code=409,
                            detail="Phase-4 executor admission lane identity mismatch",
                        )

            return original_executor_admission(
                payload,
                expected_call=expected_call,
            )

        jk._phase4_executor_admission_decision = governed_executor_admission

    register_manifest = getattr(jk, "_register_runtime_manifest_components", None)
    if callable(register_manifest):
        register_manifest({
            "jack_consequence_gate.py": Path(__file__).resolve(),
        })

    jk._JACK_CONSEQUENCE_GATE_INSTALLED = True
