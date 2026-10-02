from __future__ import annotations

import contextvars
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any, Callable, Iterable, Optional, Tuple, Union

import jack_authority_ledger as authority_ledger
import jack_path_policy as path_policy


_EXPECTED_OUTCOME_VALUES = (
    "ALLOW",
    "DENY_AND_CONTINUE",
    "REQUIRE_USER_DECISION",
    "HARD_INTERRUPT",
)


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
    """An authoritative fact exists, but Phase 5 has no justified mapping yet."""


@dataclass(frozen=True)
class StageToolAuthorityFact:
    authorized: bool


@dataclass(frozen=True)
class ToolSchemaFact:
    valid: bool
    errors: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutorAdmissionIdentityFact:
    """Live Phase-5 identity facts currently integrated at executor admission.

    Exact pending tool-call correlation remains owned by the existing Phase-4
    admission mechanism until its raw-fact seam is centralized without changing
    validation order or blast radius.
    """

    runtime_matches: bool
    lane_matches: bool


@dataclass(frozen=True)
class SettlementFact:
    run_open: bool
    overlapping_admission_requested: bool


@dataclass(frozen=True)
class ReservedEvidenceNamespaceFact:
    """The one live evidence violation Phase 5 can currently name precisely.

    Unknown provenance is intentionally not represented as a violation. This is
    not a generalized evidence-trust classifier.
    """

    forged: bool


@dataclass(frozen=True)
class ApprovalFact:
    """Policy contract only; Phase 5 has no live approval-state producer."""

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
    path_policy.RepresentedPathAuthorityFacts,
    ExecutorAdmissionIdentityFact,
    SettlementFact,
    ReservedEvidenceNamespaceFact,
    ApprovalFact,
    LifecycleAuthorityFact,
]

_AUTHORITY_FACT_TYPES = (
    StageToolAuthorityFact,
    ToolSchemaFact,
    path_policy.RepresentedPathAuthorityFacts,
    ExecutorAdmissionIdentityFact,
    SettlementFact,
    ReservedEvidenceNamespaceFact,
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


def _enum_values(outcome_type: Any) -> Tuple[str, ...]:
    try:
        return tuple(member.value for member in outcome_type)
    except Exception as exc:
        raise RuntimeError("Jack Kernel SecurityOutcome vocabulary is not iterable") from exc


def _require_compatible_outcome_type(outcome_type: Any) -> None:
    if _enum_values(outcome_type) != _EXPECTED_OUTCOME_VALUES:
        raise RuntimeError(
            "Jack Kernel SecurityOutcome vocabulary does not match Phase-5 contract"
        )


def _single(fact: AuthorityFact, outcome: Any, scope: ContainmentScope, decisive: bool) -> ConsequenceDecision:
    return ConsequenceDecision(
        outcome=outcome,
        containment_scope=scope,
        decisive_fact=fact if decisive else None,
        evaluated_fact_types=(type(fact).__name__,),
    )


def _path_scope(boundary: ConsequenceBoundary, *, hard: bool) -> ContainmentScope:
    if boundary is ConsequenceBoundary.EXECUTOR_ADMISSION:
        return ContainmentScope.EXECUTOR_ADMISSION
    if hard and boundary is ConsequenceBoundary.TOOL_RELEASE_BATCH:
        return ContainmentScope.TOOL_BATCH
    return ContainmentScope.TOOL_CALL


def _decision_for_fact(fact: AuthorityFact, *, boundary: ConsequenceBoundary, outcome_type: Any) -> ConsequenceDecision:
    allow = outcome_type.ALLOW
    deny = outcome_type.DENY_AND_CONTINUE
    require = outcome_type.REQUIRE_USER_DECISION
    hard = outcome_type.HARD_INTERRUPT

    if isinstance(fact, StageToolAuthorityFact):
        denied = not fact.authorized
        return _single(fact, deny if denied else allow, ContainmentScope.TOOL_CALL if denied else ContainmentScope.NONE, denied)

    if isinstance(fact, ToolSchemaFact):
        denied = not fact.valid
        return _single(fact, deny if denied else allow, ContainmentScope.TOOL_CALL if denied else ContainmentScope.NONE, denied)

    if isinstance(fact, path_policy.RepresentedPathAuthorityFacts):
        if fact.deferred_to_executor:
            return _single(fact, allow, ContainmentScope.NONE, False)
        if fact.never_match:
            return _single(fact, hard, _path_scope(boundary, hard=True), True)
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
        ok = fact.runtime_matches and fact.lane_matches
        return _single(fact, allow if ok else deny, ContainmentScope.NONE if ok else ContainmentScope.EXECUTOR_ADMISSION, not ok)

    if isinstance(fact, SettlementFact):
        denied = fact.run_open and fact.overlapping_admission_requested
        return _single(fact, deny if denied else allow, ContainmentScope.OVERLAP_ADMISSION if denied else ContainmentScope.NONE, denied)

    if isinstance(fact, ReservedEvidenceNamespaceFact):
        return _single(fact, deny if fact.forged else allow, ContainmentScope.EVIDENCE_FRAGMENT if fact.forged else ContainmentScope.NONE, fact.forged)

    if isinstance(fact, ApprovalFact):
        pending = fact.approval_required and not fact.approval_valid
        return _single(fact, require if pending else allow, ContainmentScope.CONSEQUENCE if pending else ContainmentScope.NONE, pending)

    if isinstance(fact, LifecycleAuthorityFact):
        ok = fact.task_matches and fact.run_matches and fact.run_epoch_matches
        if ok:
            return _single(fact, allow, ContainmentScope.NONE, False)
        raise UnmappedAuthorityFact(
            "task/run/run_epoch mismatch has authoritative facts but no single Phase-5 severity may be invented until the exact existing boundary semantics are mapped"
        )

    raise TypeError(f"Unsupported authority fact type: {type(fact).__name__}")


def evaluate_consequence(
    facts: Iterable[AuthorityFact],
    *,
    outcome_type: Any,
    boundary: Optional[ConsequenceBoundary] = None,
) -> ConsequenceDecision:
    """Map grounded raw facts to outcome plus minimum necessary containment."""

    items = tuple(facts)
    if not items:
        raise ValueError("Consequence Gate requires at least one authority fact")
    if any(not isinstance(fact, _AUTHORITY_FACT_TYPES) for fact in items):
        raise TypeError("Consequence Gate accepts only typed deterministic authority facts")
    _require_compatible_outcome_type(outcome_type)

    resolved_boundary = boundary or _CURRENT_CONSEQUENCE_BOUNDARY.get()
    if not isinstance(resolved_boundary, ConsequenceBoundary):
        raise TypeError("Consequence Gate boundary must be host-owned ConsequenceBoundary")

    decisions = tuple(
        _decision_for_fact(fact, boundary=resolved_boundary, outcome_type=outcome_type)
        for fact in items
    )
    fact_types = tuple(type(fact).__name__ for fact in items)
    non_allow = tuple(
        (fact, decision)
        for fact, decision in zip(items, decisions)
        if decision.outcome is not outcome_type.ALLOW
    )
    if not non_allow:
        return ConsequenceDecision(outcome_type.ALLOW, ContainmentScope.NONE, None, fact_types)

    hard_pairs = tuple(pair for pair in non_allow if pair[1].outcome is outcome_type.HARD_INTERRUPT)
    if hard_pairs:
        scopes = frozenset(pair[1].containment_scope for pair in hard_pairs)
        if len(scopes) != 1:
            raise RuntimeError("Consequence Gate received hard facts with conflicting containment scopes")
        fact, decision = hard_pairs[0]
        return ConsequenceDecision(outcome_type.HARD_INTERRUPT, decision.containment_scope, fact, fact_types)

    outcomes = frozenset(pair[1].outcome for pair in non_allow)
    if len(outcomes) != 1:
        raise RuntimeError("Consequence Gate received conflicting authoritative non-hard dispositions")
    scopes = frozenset(pair[1].containment_scope for pair in non_allow)
    if len(scopes) != 1:
        raise RuntimeError("Consequence Gate will not guess a broader containment scope for multiple non-hard facts")

    fact, decision = non_allow[0]
    return ConsequenceDecision(decision.outcome, decision.containment_scope, fact, fact_types)


def _bound_evaluator(outcome_type: Any) -> Callable[..., ConsequenceDecision]:
    _require_compatible_outcome_type(outcome_type)

    def bound(facts: Iterable[AuthorityFact], *, boundary: Optional[ConsequenceBoundary] = None) -> ConsequenceDecision:
        return evaluate_consequence(facts, outcome_type=outcome_type, boundary=boundary)

    return bound


def _legacy_path_decision(decision: ConsequenceDecision, raw: path_policy.RepresentedPathAuthorityFacts) -> path_policy.PathAuthorizationDecision:
    try:
        legacy = path_policy.PathAuthorizationOutcome(decision.outcome.value)
    except ValueError as exc:
        raise AssertionError("Phase-5 path decision cannot be represented by Phase-4 release machinery") from exc
    return path_policy.PathAuthorizationDecision(legacy, raw.reason, raw.canonical_target)


def _install_represented_path_gate(evaluator: Callable[..., ConsequenceDecision]) -> None:
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
        raw = path_policy.inspect_represented_path(
            policy,
            represented_path,
            executor_cwd=executor_cwd,
            defer_relative_without_executor=defer_relative_without_executor,
        )
        decision = evaluator((raw,))
        authority_ledger.record_represented_path_decision_failsoft(
            deterministic=raw.deterministic,
            never_match=raw.never_match,
            workspace_configured=raw.workspace_configured,
            inside_workspace=raw.inside_workspace,
            invalid=raw.invalid,
            deferred_to_executor=raw.deferred_to_executor,
            outcome=decision.outcome,
            containment_scope=decision.containment_scope,
            boundary=_CURRENT_CONSEQUENCE_BOUNDARY.get(),
        )
        return _legacy_path_decision(decision, raw)

    governed._jack_phase5_consequence_gate = True
    governed._jack_phase5_legacy_authorizer = original
    path_policy.authorize_represented_path = governed


def install(jk: Any) -> None:
    """Install grounded disposition seams from the authoritative Kernel owner."""

    if getattr(jk, "_JACK_CONSEQUENCE_GATE_INSTALLED", False):
        return

    outcome_type = getattr(jk, "SecurityOutcome", None)
    _require_compatible_outcome_type(outcome_type)

    # Phase 6 is installed only for the real Kernel-owned convergence path.
    # Lightweight policy-test fakes remain valid Phase-5 evaluator hosts without
    # acquiring runtime/process authority they do not possess.
    ledger = None
    if callable(getattr(jk, "_install_bundled_runtime_extensions", None)):
        ledger = authority_ledger.install(jk)

    evaluator = _bound_evaluator(outcome_type)

    jk.ConsequenceBoundary = ConsequenceBoundary
    jk.ContainmentScope = ContainmentScope
    jk.UnmappedAuthorityFact = UnmappedAuthorityFact
    jk.StageToolAuthorityFact = StageToolAuthorityFact
    jk.ToolSchemaFact = ToolSchemaFact
    jk.RepresentedPathAuthorityFacts = path_policy.RepresentedPathAuthorityFacts
    jk.ExecutorAdmissionIdentityFact = ExecutorAdmissionIdentityFact
    jk.SettlementFact = SettlementFact
    jk.ReservedEvidenceNamespaceFact = ReservedEvidenceNamespaceFact
    jk.ApprovalFact = ApprovalFact
    jk.LifecycleAuthorityFact = LifecycleAuthorityFact
    jk.ConsequenceDecision = ConsequenceDecision
    jk.evaluate_consequence = evaluator

    _install_represented_path_gate(evaluator)

    original_partition = getattr(jk, "_phase4_partition_structured_tool_calls", None)
    if callable(original_partition):
        @wraps(original_partition)
        def governed_partition(calls: Any) -> Any:
            token = _CURRENT_CONSEQUENCE_BOUNDARY.set(ConsequenceBoundary.TOOL_RELEASE_BATCH)
            try:
                if ledger is None:
                    return original_partition(calls)
                with authority_ledger.live_ledger_scope(ledger):
                    return original_partition(calls)
            finally:
                _CURRENT_CONSEQUENCE_BOUNDARY.reset(token)
        jk._phase4_partition_structured_tool_calls = governed_partition

    original_admission = getattr(jk, "_phase4_executor_admission_decision", None)
    if callable(original_admission):
        @wraps(original_admission)
        def governed_admission(payload: Any, *, expected_call: Optional[dict[str, Any]] = None) -> Any:
            allowed_fields = {
                "protocol_version", "runtime_id", "lane_id", "tool_call_id",
                "tool_name", "arguments", "executor_cwd", "executor_platform",
                "command_dialect",
            }
            protocol_version = getattr(jk, "PHASE4_EXECUTOR_ADMISSION_PROTOCOL_VERSION", None)
            if isinstance(payload, dict) and not (set(payload) - allowed_fields) and payload.get("protocol_version") == protocol_version:
                runtime_matches = str(payload.get("runtime_id") or "").strip() == str(getattr(jk, "RUNTIME_ID", ""))
                lane_matches = str(payload.get("lane_id") or "").strip() == str(getattr(jk, "LANE_ID", ""))
                decision = evaluator(
                    (ExecutorAdmissionIdentityFact(runtime_matches=runtime_matches, lane_matches=lane_matches),),
                    boundary=ConsequenceBoundary.EXECUTOR_ADMISSION,
                )
                if ledger is not None:
                    authority_ledger.record_executor_identity_decision_failsoft(
                        ledger,
                        runtime_matches=runtime_matches,
                        lane_matches=lane_matches,
                        outcome=decision.outcome,
                        containment_scope=decision.containment_scope,
                    )
                if decision.outcome is outcome_type.DENY_AND_CONTINUE:
                    if decision.containment_scope is not ContainmentScope.EXECUTOR_ADMISSION:
                        raise AssertionError("Executor identity denial escaped admission scope")
                    if not runtime_matches:
                        raise jk.HTTPException(status_code=409, detail="Phase-4 executor admission runtime identity mismatch")
                    if not lane_matches:
                        raise jk.HTTPException(status_code=409, detail="Phase-4 executor admission lane identity mismatch")

            token = _CURRENT_CONSEQUENCE_BOUNDARY.set(ConsequenceBoundary.EXECUTOR_ADMISSION)
            try:
                if ledger is None:
                    return original_admission(payload, expected_call=expected_call)
                with authority_ledger.live_ledger_scope(ledger):
                    return original_admission(payload, expected_call=expected_call)
            finally:
                _CURRENT_CONSEQUENCE_BOUNDARY.reset(token)
        jk._phase4_executor_admission_decision = governed_admission

    jk._JACK_CONSEQUENCE_GATE_INSTALLED = True
