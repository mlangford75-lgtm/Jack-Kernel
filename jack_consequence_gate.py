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
    """An authoritative fact exists, but Phase 5 has no justified mapping yet."""


@dataclass(frozen=True)
class StageToolAuthorityFact:
    authorized: bool


@dataclass(frozen=True)
class ToolSchemaFact:
    valid: bool
    errors: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PathPolicyFact:
    """Raw represented-path facts already established by path authority.

    This is deliberately not constructed from a desired SecurityOutcome.  It is
    the Gate contract for the future raw Phase-4 path seam: a positive NEVER
    match, whether Workspace Lock exists, whether the represented target is
    deterministic enough for that lock, and whether it is inside the workspace.
    """

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
    """Evidence fact without treating unknown provenance as a violation."""

    origin_known: bool
    forged_reserved_namespace: bool = False


@dataclass(frozen=True)
class ApprovalFact:
    approval_required: bool
    approval_valid: bool


@dataclass(frozen=True)
class LifecycleAuthorityFact:
    """Current task/run/epoch identity facts.

    Current Jack establishes these facts, but Phase 5 intentionally does not
    guess a single severity for every possible lifecycle mismatch yet.
    """

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


def _decision_for_fact(fact: AuthorityFact) -> ConsequenceDecision:
    fact_name = type(fact).__name__

    if isinstance(fact, StageToolAuthorityFact):
        if fact.authorized:
            return ConsequenceDecision(
                SecurityOutcome.ALLOW,
                ContainmentScope.NONE,
                None,
                (fact_name,),
            )
        return ConsequenceDecision(
            SecurityOutcome.DENY_AND_CONTINUE,
            ContainmentScope.TOOL_CALL,
            fact,
            (fact_name,),
        )

    if isinstance(fact, ToolSchemaFact):
        if fact.valid:
            return ConsequenceDecision(
                SecurityOutcome.ALLOW,
                ContainmentScope.NONE,
                None,
                (fact_name,),
            )
        return ConsequenceDecision(
            SecurityOutcome.DENY_AND_CONTINUE,
            ContainmentScope.TOOL_CALL,
            fact,
            (fact_name,),
        )

    if isinstance(fact, PathPolicyFact):
        if fact.never_match:
            # Preserve the already-validated Phase-4 hard boundary.  Phase 4
            # currently prevents release of the complete consequential batch
            # when a positive NEVER match is established.
            return ConsequenceDecision(
                SecurityOutcome.HARD_INTERRUPT,
                ContainmentScope.TOOL_BATCH,
                fact,
                (fact_name,),
            )

        if fact.workspace_configured:
            if not fact.deterministic or fact.inside_workspace is False:
                return ConsequenceDecision(
                    SecurityOutcome.DENY_AND_CONTINUE,
                    ContainmentScope.TOOL_CALL,
                    fact,
                    (fact_name,),
                )

        # Ambiguity without Workspace Lock does not manufacture a restriction.
        return ConsequenceDecision(
            SecurityOutcome.ALLOW,
            ContainmentScope.NONE,
            None,
            (fact_name,),
        )

    if isinstance(fact, ExecutorAdmissionIdentityFact):
        if fact.runtime_matches and fact.lane_matches and fact.call_matches:
            return ConsequenceDecision(
                SecurityOutcome.ALLOW,
                ContainmentScope.NONE,
                None,
                (fact_name,),
            )
        return ConsequenceDecision(
            SecurityOutcome.DENY_AND_CONTINUE,
            ContainmentScope.EXECUTOR_ADMISSION,
            fact,
            (fact_name,),
        )

    if isinstance(fact, SettlementFact):
        if fact.run_open and fact.overlapping_admission_requested:
            return ConsequenceDecision(
                SecurityOutcome.DENY_AND_CONTINUE,
                ContainmentScope.OVERLAP_ADMISSION,
                fact,
                (fact_name,),
            )
        return ConsequenceDecision(
            SecurityOutcome.ALLOW,
            ContainmentScope.NONE,
            None,
            (fact_name,),
        )

    if isinstance(fact, EvidenceProvenanceFact):
        if fact.forged_reserved_namespace:
            return ConsequenceDecision(
                SecurityOutcome.DENY_AND_CONTINUE,
                ContainmentScope.EVIDENCE_FRAGMENT,
                fact,
                (fact_name,),
            )
        # Unknown provenance by itself is not proof of a security violation.
        return ConsequenceDecision(
            SecurityOutcome.ALLOW,
            ContainmentScope.NONE,
            None,
            (fact_name,),
        )

    if isinstance(fact, ApprovalFact):
        if fact.approval_required and not fact.approval_valid:
            return ConsequenceDecision(
                SecurityOutcome.REQUIRE_USER_DECISION,
                ContainmentScope.CONSEQUENCE,
                fact,
                (fact_name,),
            )
        return ConsequenceDecision(
            SecurityOutcome.ALLOW,
            ContainmentScope.NONE,
            None,
            (fact_name,),
        )

    if isinstance(fact, LifecycleAuthorityFact):
        if fact.task_matches and fact.run_matches and fact.run_epoch_matches:
            return ConsequenceDecision(
                SecurityOutcome.ALLOW,
                ContainmentScope.NONE,
                None,
                (fact_name,),
            )
        raise UnmappedAuthorityFact(
            "task/run/run_epoch mismatch has authoritative facts but no single "
            "Phase-5 severity may be invented until the exact existing boundary "
            "semantics are mapped"
        )

    raise TypeError(f"Unsupported authority fact type: {fact_name}")


def evaluate_consequence(facts: Iterable[AuthorityFact]) -> ConsequenceDecision:
    """Map authoritative state facts to the smallest justified disposition.

    This function owns disposition.  Callers do not supply SecurityOutcome as
    input.  HARD_INTERRUPT may dominate a recoverable decision only where a raw
    fact already maps to that established hard invariant.  The Gate refuses to
    guess between conflicting non-hard outcomes or conflicting blast radii.
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
        hard_scopes = frozenset(pair[1].containment_scope for pair in hard)
        if len(hard_scopes) != 1:
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
    """Install only Phase-5 integrations whose fact/severity mapping is clear.

    This deliberately does *not* wrap Phase-4 path partitioning merely to observe
    a disposition that Phase 4 already made.  PathPolicyFact defines the correct
    raw-fact Gate contract, but live path integration must wait for the raw path
    fact seam.  Likewise, no approval or future integrity authority is fabricated.
    """

    if getattr(jk, "_JACK_CONSEQUENCE_GATE_INSTALLED", False):
        return

    # Expose the pure Gate contract to the Kernel namespace for tests and later
    # authoritative producers without giving model/caller data a construction path.
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

    original_validation = getattr(jk, "_tool_call_validation_errors", None)
    if callable(original_validation):
        @wraps(original_validation)
        def governed_validation(calls: Any, tools: Any) -> Any:
            errors = list(original_validation(calls, tools))
            decision = evaluate_consequence((
                ToolSchemaFact(
                    valid=not errors,
                    errors=tuple(str(error) for error in errors),
                ),
            ))
            if decision.outcome is SecurityOutcome.ALLOW:
                return []
            if (
                decision.outcome is SecurityOutcome.DENY_AND_CONTINUE
                and decision.containment_scope is ContainmentScope.TOOL_CALL
            ):
                return errors
            raise AssertionError(
                "Tool-schema Gate produced an unsupported disposition/containment"
            )

        jk._tool_call_validation_errors = governed_validation

    original_executor_admission = getattr(jk, "_phase4_executor_admission_decision", None)
    if callable(original_executor_admission):
        @wraps(original_executor_admission)
        def governed_executor_admission(
            payload: Any,
            *,
            expected_call: Optional[dict[str, Any]] = None,
        ) -> Any:
            # Preserve the existing Phase-4 structural/protocol validation order.
            # The Gate takes authority only once the payload is structurally in
            # the current executor-admission protocol and runtime/lane identity is
            # the next consequential question the old code would answer.
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
                jk,
                "PHASE4_EXECUTOR_ADMISSION_PROTOCOL_VERSION",
                None,
            )
            if (
                isinstance(payload, dict)
                and not (set(payload) - allowed_fields)
                and payload.get("protocol_version") == protocol_version
            ):
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
                        # Exact pending-call correlation remains with the existing
                        # producer until its raw seam can be integrated without
                        # changing validation order.
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
