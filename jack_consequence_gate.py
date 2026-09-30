from __future__ import annotations

import contextvars
import importlib
import os
import sys
from dataclasses import dataclass, replace
from enum import Enum
from functools import wraps
from typing import Any, Callable, Iterable, Optional, Tuple, Union


def _active_kernel_module() -> Any:
    """Return the active Jack Kernel module without silently duplicating it.

    Direct ``python jack_kernel.py`` execution names the runtime ``__main__``.
    In that case alias the active module as ``jack_kernel`` before any ordinary
    import can create a second runtime authority domain.  Isolated regression
    modules loaded under synthetic names are not treated as the active runtime.
    """

    named = sys.modules.get("jack_kernel")
    main = sys.modules.get("__main__")
    main_file = os.path.basename(str(getattr(main, "__file__", "") or ""))
    direct = main if main_file in {"jack_kernel.py", "jack_kernel.pyc"} else None

    if direct is not None:
        if named is not None and named is not direct:
            raise RuntimeError(
                "Jack Kernel module identity is split between __main__ and jack_kernel"
            )
        sys.modules["jack_kernel"] = direct
        return direct

    if named is not None:
        return named
    return importlib.import_module("jack_kernel")


_ACTIVE_KERNEL = _active_kernel_module()
SecurityOutcome = _ACTIVE_KERNEL.SecurityOutcome
_EXPECTED_OUTCOME_VALUES = tuple(member.value for member in SecurityOutcome)


class ConsequenceBoundary(str, Enum):
    TOOL_CALL = "tool_call"
    TOOL_RELEASE_BATCH = "tool_release_batch"
    EXECUTOR_ADMISSION = "executor_admission"
    OVERLAP_ADMISSION = "overlap_admission"
    EVIDENCE_FRAGMENT = "evidence_fragment"
    CONSEQUENCE = "consequence"


class ContainmentScope(str, Enum):
    NONE = "none"
    TOOL_CALL = "tool_call"
    TOOL_BATCH = "tool_batch"
    EXECUTOR_ADMISSION = "executor_admission"
    OVERLAP_ADMISSION = "overlap_admission"
    EVIDENCE_FRAGMENT = "evidence_fragment"
    CONSEQUENCE = "consequence"


class UnmappedAuthorityFact(RuntimeError):
    """The fact is authoritative, but Phase 5 has no justified mapping yet."""


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
    invalid: bool = False
    deferred_to_executor: bool = False


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

_CURRENT_CONSEQUENCE_BOUNDARY: contextvars.ContextVar[ConsequenceBoundary] = (
    contextvars.ContextVar(
        "jack_phase5_consequence_boundary",
        default=ConsequenceBoundary.TOOL_CALL,
    )
)


@dataclass(frozen=True)
class ConsequenceDecision:
    outcome: Any
    containment_scope: ContainmentScope
    decisive_fact: Optional[AuthorityFact]
    evaluated_fact_types: Tuple[str, ...]


def _single(
    fact: AuthorityFact,
    outcome: Any,
    scope: ContainmentScope,
    decisive: bool,
) -> ConsequenceDecision:
    return ConsequenceDecision(
        outcome=outcome,
        containment_scope=scope,
        decisive_fact=fact if decisive else None,
        evaluated_fact_types=(type(fact).__name__,),
    )


def _path_scope(
    boundary: ConsequenceBoundary,
    *,
    hard: bool,
) -> ContainmentScope:
    if boundary is ConsequenceBoundary.EXECUTOR_ADMISSION:
        return ContainmentScope.EXECUTOR_ADMISSION
    if hard and boundary is ConsequenceBoundary.TOOL_RELEASE_BATCH:
        return ContainmentScope.TOOL_BATCH
    return ContainmentScope.TOOL_CALL


def _decision_for_fact(
    fact: AuthorityFact,
    *,
    boundary: ConsequenceBoundary,
    outcome_type: Any,
) -> ConsequenceDecision:
    allow = outcome_type.ALLOW
    deny = outcome_type.DENY_AND_CONTINUE
    require = outcome_type.REQUIRE_USER_DECISION
    hard = outcome_type.HARD_INTERRUPT

    if isinstance(fact, StageToolAuthorityFact):
        return _single(
            fact,
            allow if fact.authorized else deny,
            ContainmentScope.NONE if fact.authorized else ContainmentScope.TOOL_CALL,
            not fact.authorized,
        )

    if isinstance(fact, ToolSchemaFact):
        return _single(
            fact,
            allow if fact.valid else deny,
            ContainmentScope.NONE if fact.valid else ContainmentScope.TOOL_CALL,
            not fact.valid,
        )

    if isinstance(fact, PathPolicyFact):
        if fact.deferred_to_executor:
            return _single(fact, allow, ContainmentScope.NONE, False)
        if fact.never_match:
            return _single(
                fact,
                hard,
                _path_scope(boundary, hard=True),
                True,
            )
        denied = fact.invalid or (
            fact.workspace_configured
            and (not fact.deterministic or fact.inside_workspace is False)
        )
        return _single(
            fact,
            deny if denied else allow,
            _path_scope(boundary, hard=False) if denied else ContainmentScope.NONE,
            denied,
        )

    if isinstance(fact, ExecutorAdmissionIdentityFact):
        ok = fact.runtime_matches and fact.lane_matches and fact.call_matches
        return _single(
            fact,
            allow if ok else deny,
            ContainmentScope.NONE if ok else ContainmentScope.EXECUTOR_ADMISSION,
            not ok,
        )

    if isinstance(fact, SettlementFact):
        denied = fact.run_open and fact.overlapping_admission_requested
        return _single(
            fact,
            deny if denied else allow,
            ContainmentScope.OVERLAP_ADMISSION if denied else ContainmentScope.NONE,
            denied,
        )

    if isinstance(fact, EvidenceProvenanceFact):
        denied = fact.forged_reserved_namespace
        return _single(
            fact,
            deny if denied else allow,
            ContainmentScope.EVIDENCE_FRAGMENT if denied else ContainmentScope.NONE,
            denied,
        )

    if isinstance(fact, ApprovalFact):
        pending = fact.approval_required and not fact.approval_valid
        return _single(
            fact,
            require if pending else allow,
            ContainmentScope.CONSEQUENCE if pending else ContainmentScope.NONE,
            pending,
        )

    if isinstance(fact, LifecycleAuthorityFact):
        ok = fact.task_matches and fact.run_matches and fact.run_epoch_matches
        if ok:
            return _single(fact, allow, ContainmentScope.NONE, False)
        raise UnmappedAuthorityFact(
            "task/run/run_epoch mismatch has authoritative facts but no single "
            "Phase-5 severity may be invented until the exact existing boundary "
            "semantics are mapped"
        )

    raise TypeError(f"Unsupported authority fact type: {type(fact).__name__}")


def _enum_values(outcome_type: Any) -> Tuple[str, ...]:
    try:
        return tuple(member.value for member in outcome_type)
    except Exception as exc:
        raise RuntimeError(
            "Jack Kernel SecurityOutcome vocabulary is not iterable"
        ) from exc


def _require_compatible_outcome_type(outcome_type: Any) -> None:
    if _enum_values(outcome_type) != _EXPECTED_OUTCOME_VALUES:
        raise RuntimeError(
            "Jack Kernel SecurityOutcome vocabulary does not match Phase-5 contract"
        )


def _evaluate(
    facts: Iterable[AuthorityFact],
    *,
    boundary: Optional[ConsequenceBoundary],
    outcome_type: Any,
) -> ConsequenceDecision:
    items = tuple(facts)
    if not items:
        raise ValueError("Consequence Gate requires at least one authority fact")
    if any(not isinstance(fact, _AUTHORITY_FACT_TYPES) for fact in items):
        raise TypeError(
            "Consequence Gate accepts only typed deterministic authority facts"
        )
    _require_compatible_outcome_type(outcome_type)

    resolved_boundary = boundary or _CURRENT_CONSEQUENCE_BOUNDARY.get()
    if not isinstance(resolved_boundary, ConsequenceBoundary):
        raise TypeError("Consequence Gate boundary must be host-owned ConsequenceBoundary")

    decisions = tuple(
        _decision_for_fact(
            fact,
            boundary=resolved_boundary,
            outcome_type=outcome_type,
        )
        for fact in items
    )
    fact_types = tuple(type(fact).__name__ for fact in items)
    non_allow = tuple(
        (fact, decision)
        for fact, decision in zip(items, decisions)
        if decision.outcome is not outcome_type.ALLOW
    )

    if not non_allow:
        return ConsequenceDecision(
            outcome_type.ALLOW,
            ContainmentScope.NONE,
            None,
            fact_types,
        )

    hard_pairs = tuple(
        pair
        for pair in non_allow
        if pair[1].outcome is outcome_type.HARD_INTERRUPT
    )
    if hard_pairs:
        scopes = frozenset(pair[1].containment_scope for pair in hard_pairs)
        if len(scopes) != 1:
            raise RuntimeError(
                "Consequence Gate received hard facts with conflicting containment scopes"
            )
        fact, decision = hard_pairs[0]
        return ConsequenceDecision(
            outcome_type.HARD_INTERRUPT,
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


def evaluate_consequence(
    facts: Iterable[AuthorityFact],
    *,
    boundary: Optional[ConsequenceBoundary] = None,
) -> ConsequenceDecision:
    """Map raw deterministic facts plus release boundary to outcome and scope."""
    return _evaluate(
        facts,
        boundary=boundary,
        outcome_type=SecurityOutcome,
    )


def _bound_evaluator(outcome_type: Any) -> Callable[..., ConsequenceDecision]:
    _require_compatible_outcome_type(outcome_type)

    def bound(
        facts: Iterable[AuthorityFact],
        *,
        boundary: Optional[ConsequenceBoundary] = None,
    ) -> ConsequenceDecision:
        return _evaluate(
            facts,
            boundary=boundary,
            outcome_type=outcome_type,
        )

    return bound


def _legacy_path_decision(
    path_policy: Any,
    decision: ConsequenceDecision,
    reason: str,
    canonical: Optional[str],
) -> Any:
    try:
        legacy = path_policy.PathAuthorizationOutcome(decision.outcome.value)
    except ValueError as exc:
        raise AssertionError(
            "Phase-5 path decision cannot be represented by Phase-4 release machinery"
        ) from exc
    return path_policy.PathAuthorizationDecision(legacy, reason, canonical)


def _install_represented_path_gate(
    evaluator: Callable[..., ConsequenceDecision] = evaluate_consequence,
) -> None:
    import jack_path_authority_facts as path_facts
    import jack_path_policy as path_policy

    original = path_policy.authorize_represented_path
    if getattr(original, "_jack_phase5_consequence_gate", False):
        return

    @wraps(original)
    def governed(
        policy: Any,
        represented_path: Any,
        *,
        executor_cwd: Optional[str] = None,
        defer_relative_without_executor: bool = False,
    ) -> Any:
        raw = path_facts.inspect_represented_path(
            policy,
            represented_path,
            executor_cwd=executor_cwd,
            defer_relative_without_executor=defer_relative_without_executor,
        )
        decision = evaluator((
            PathPolicyFact(
                never_match=raw.never_match,
                workspace_configured=raw.workspace_configured,
                deterministic=raw.deterministic,
                inside_workspace=raw.inside_workspace,
                invalid=raw.invalid,
                deferred_to_executor=raw.deferred_to_executor,
            ),
        ))
        return _legacy_path_decision(
            path_policy,
            decision,
            raw.reason,
            raw.canonical_target,
        )

    governed._jack_phase5_consequence_gate = True
    path_policy.authorize_represented_path = governed


def install(jk: Any) -> None:
    """Install only grounded disposition seams; do not invent missing authority."""
    if getattr(jk, "_JACK_CONSEQUENCE_GATE_INSTALLED", False):
        return

    outcome_type = getattr(jk, "SecurityOutcome", None)
    _require_compatible_outcome_type(outcome_type)
    evaluator = _bound_evaluator(outcome_type)

    jk.ConsequenceBoundary = ConsequenceBoundary
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
    jk.evaluate_consequence = evaluator

    _install_represented_path_gate(evaluator)

    original_partition = getattr(jk, "_phase4_partition_structured_tool_calls", None)
    if callable(original_partition):
        @wraps(original_partition)
        def governed_partition(calls: Any) -> Any:
            token = _CURRENT_CONSEQUENCE_BOUNDARY.set(
                ConsequenceBoundary.TOOL_RELEASE_BATCH
            )
            try:
                return original_partition(calls)
            finally:
                _CURRENT_CONSEQUENCE_BOUNDARY.reset(token)

        jk._phase4_partition_structured_tool_calls = governed_partition

    original_admission = getattr(jk, "_phase4_executor_admission_decision", None)
    if callable(original_admission):
        @wraps(original_admission)
        def governed_admission(
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
                decision = evaluator(
                    (
                        ExecutorAdmissionIdentityFact(
                            runtime_matches=runtime_matches,
                            lane_matches=lane_matches,
                            call_matches=True,
                        ),
                    ),
                    boundary=ConsequenceBoundary.EXECUTOR_ADMISSION,
                )
                if decision.outcome is outcome_type.DENY_AND_CONTINUE:
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

            token = _CURRENT_CONSEQUENCE_BOUNDARY.set(
                ConsequenceBoundary.EXECUTOR_ADMISSION
            )
            try:
                return original_admission(
                    payload,
                    expected_call=expected_call,
                )
            finally:
                _CURRENT_CONSEQUENCE_BOUNDARY.reset(token)

        jk._phase4_executor_admission_decision = governed_admission

    # Runtime manifests remain observational. Authority comes from the installed
    # consequence boundary, not from manifest presence.
    jk._JACK_CONSEQUENCE_GATE_INSTALLED = True
