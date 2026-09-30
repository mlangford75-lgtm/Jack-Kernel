from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, Iterable, Optional, Tuple, Union

from jack_kernel import SecurityOutcome


class ContainmentScope(str, Enum):
    NONE = "none"
    TOOL_CALL = "tool_call"
    TOOL_BATCH = "tool_batch"
    EXECUTOR_ADMISSION = "executor_admission"
    OVERLAP_ADMISSION = "overlap_admission"
    EVIDENCE_FRAGMENT = "evidence_fragment"
    CONSEQUENCE = "consequence"


class UnmappedAuthorityFact(RuntimeError):
    pass


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


@dataclass(frozen=True)
class ConsequenceDecision:
    outcome: SecurityOutcome
    containment_scope: ContainmentScope
    decisive_fact: Optional[AuthorityFact]
    evaluated_fact_types: Tuple[str, ...]


def _single(
    fact: AuthorityFact,
    outcome: SecurityOutcome,
    scope: ContainmentScope,
    decisive: bool,
) -> ConsequenceDecision:
    return ConsequenceDecision(
        outcome,
        scope,
        fact if decisive else None,
        (type(fact).__name__,),
    )


def _decision_for_fact(fact: AuthorityFact) -> ConsequenceDecision:
    if isinstance(fact, StageToolAuthorityFact):
        return _single(
            fact,
            SecurityOutcome.ALLOW if fact.authorized else SecurityOutcome.DENY_AND_CONTINUE,
            ContainmentScope.NONE if fact.authorized else ContainmentScope.TOOL_CALL,
            not fact.authorized,
        )

    if isinstance(fact, ToolSchemaFact):
        return _single(
            fact,
            SecurityOutcome.ALLOW if fact.valid else SecurityOutcome.DENY_AND_CONTINUE,
            ContainmentScope.NONE if fact.valid else ContainmentScope.TOOL_CALL,
            not fact.valid,
        )

    if isinstance(fact, PathPolicyFact):
        if fact.deferred_to_executor:
            return _single(fact, SecurityOutcome.ALLOW, ContainmentScope.NONE, False)
        if fact.never_match:
            return _single(
                fact,
                SecurityOutcome.HARD_INTERRUPT,
                ContainmentScope.TOOL_BATCH,
                True,
            )
        if fact.invalid:
            return _single(
                fact,
                SecurityOutcome.DENY_AND_CONTINUE,
                ContainmentScope.TOOL_CALL,
                True,
            )
        if fact.workspace_configured and (
            not fact.deterministic or fact.inside_workspace is False
        ):
            return _single(
                fact,
                SecurityOutcome.DENY_AND_CONTINUE,
                ContainmentScope.TOOL_CALL,
                True,
            )
        return _single(fact, SecurityOutcome.ALLOW, ContainmentScope.NONE, False)

    if isinstance(fact, ExecutorAdmissionIdentityFact):
        ok = fact.runtime_matches and fact.lane_matches and fact.call_matches
        return _single(
            fact,
            SecurityOutcome.ALLOW if ok else SecurityOutcome.DENY_AND_CONTINUE,
            ContainmentScope.NONE if ok else ContainmentScope.EXECUTOR_ADMISSION,
            not ok,
        )

    if isinstance(fact, SettlementFact):
        denied = fact.run_open and fact.overlapping_admission_requested
        return _single(
            fact,
            SecurityOutcome.DENY_AND_CONTINUE if denied else SecurityOutcome.ALLOW,
            ContainmentScope.OVERLAP_ADMISSION if denied else ContainmentScope.NONE,
            denied,
        )

    if isinstance(fact, EvidenceProvenanceFact):
        denied = fact.forged_reserved_namespace
        return _single(
            fact,
            SecurityOutcome.DENY_AND_CONTINUE if denied else SecurityOutcome.ALLOW,
            ContainmentScope.EVIDENCE_FRAGMENT if denied else ContainmentScope.NONE,
            denied,
        )

    if isinstance(fact, ApprovalFact):
        required = fact.approval_required and not fact.approval_valid
        return _single(
            fact,
            SecurityOutcome.REQUIRE_USER_DECISION if required else SecurityOutcome.ALLOW,
            ContainmentScope.CONSEQUENCE if required else ContainmentScope.NONE,
            required,
        )

    if isinstance(fact, LifecycleAuthorityFact):
        ok = fact.task_matches and fact.run_matches and fact.run_epoch_matches
        if ok:
            return _single(fact, SecurityOutcome.ALLOW, ContainmentScope.NONE, False)
        raise UnmappedAuthorityFact(
            "task/run/run_epoch mismatch has authoritative facts but no single "
            "Phase-5 severity may be invented until the exact existing boundary "
            "semantics are mapped"
        )

    raise TypeError(f"Unsupported authority fact type: {type(fact).__name__}")


def evaluate_consequence(facts: Iterable[AuthorityFact]) -> ConsequenceDecision:
    """Map raw deterministic authority facts to disposition and blast radius."""
    items = tuple(facts)
    if not items:
        raise ValueError("Consequence Gate requires at least one authority fact")
    if any(not isinstance(fact, _AUTHORITY_FACT_TYPES) for fact in items):
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
            SecurityOutcome.ALLOW, ContainmentScope.NONE, None, fact_types
        )

    hard = tuple(
        pair for pair in non_allow
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


def _legacy_path_decision(path_policy: Any, decision: ConsequenceDecision, reason: str, canonical: Optional[str] = None) -> Any:
    try:
        legacy_outcome = path_policy.PathAuthorizationOutcome(decision.outcome.value)
    except ValueError as exc:
        raise AssertionError(
            "Phase-5 path decision cannot be represented by the Phase-4 release mechanism"
        ) from exc
    return path_policy.PathAuthorizationDecision(
        legacy_outcome,
        reason,
        canonical,
    )


def _install_represented_path_gate() -> None:
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
        if not isinstance(policy, path_policy.RuntimePathPolicy):
            raise TypeError("policy must be a RuntimePathPolicy")

        environment = policy.path_environment()
        canonical_cwd = None
        if executor_cwd is not None:
            try:
                canonical_cwd = path_policy.normalize_represented_windows_path(
                    executor_cwd,
                    environment=environment,
                )
            except path_policy.RepresentedPathError as exc:
                decision = evaluate_consequence((
                    PathPolicyFact(
                        workspace_configured=policy.workspace_enabled,
                        deterministic=False,
                        invalid=True,
                    ),
                ))
                return _legacy_path_decision(
                    path_policy,
                    decision,
                    f"executor cwd is not a deterministic absolute Windows path: {exc}",
                )

        try:
            canonical = path_policy.normalize_represented_windows_path(
                represented_path,
                base_root=canonical_cwd,
                environment=environment,
            )
        except path_policy.RepresentedPathNeedsExecutorCwd as exc:
            if defer_relative_without_executor:
                decision = evaluate_consequence((
                    PathPolicyFact(
                        workspace_configured=policy.workspace_enabled,
                        deterministic=False,
                        deferred_to_executor=True,
                    ),
                ))
                return _legacy_path_decision(
                    path_policy,
                    decision,
                    f"executor cwd admission is required before execution: {exc}",
                )
            decision = evaluate_consequence((
                PathPolicyFact(
                    workspace_configured=policy.workspace_enabled,
                    deterministic=False,
                ),
            ))
            reason = (
                f"workspace membership cannot be established: {exc}"
                if policy.workspace_enabled
                else f"no workspace lock; represented target unresolved: {exc}"
            )
            return _legacy_path_decision(path_policy, decision, reason)
        except path_policy.RepresentedPathInvalid as exc:
            decision = evaluate_consequence((
                PathPolicyFact(
                    workspace_configured=policy.workspace_enabled,
                    deterministic=False,
                    invalid=True,
                ),
            ))
            return _legacy_path_decision(
                path_policy,
                decision,
                f"invalid represented path: {exc}",
            )
        except path_policy.RepresentedPathAmbiguous as exc:
            decision = evaluate_consequence((
                PathPolicyFact(
                    workspace_configured=policy.workspace_enabled,
                    deterministic=False,
                ),
            ))
            reason = (
                f"workspace membership cannot be established: {exc}"
                if policy.workspace_enabled
                else f"no workspace lock; represented target unresolved: {exc}"
            )
            return _legacy_path_decision(path_policy, decision, reason)

        try:
            comparison_target = path_policy._policy_object_windows_path(canonical)
        except path_policy.RepresentedPathAmbiguous as exc:
            decision = evaluate_consequence((
                PathPolicyFact(
                    workspace_configured=policy.workspace_enabled,
                    deterministic=False,
                ),
            ))
            reason = (
                f"workspace membership cannot be established: {exc}"
                if policy.workspace_enabled
                else f"no workspace lock; represented target unresolved: {exc}"
            )
            return _legacy_path_decision(path_policy, decision, reason, canonical)

        never_match = any(
            path_policy.path_is_within_or_equal(comparison_target, never_root)
            for never_root in policy.never_roots
        )
        inside_workspace = (
            None
            if policy.workspace_root is None
            else path_policy.path_is_within_or_equal(
                comparison_target,
                policy.workspace_root,
            )
        )
        fact = PathPolicyFact(
            never_match=never_match,
            workspace_configured=policy.workspace_enabled,
            deterministic=True,
            inside_workspace=inside_workspace,
        )
        decision = evaluate_consequence((fact,))

        if decision.outcome is SecurityOutcome.HARD_INTERRUPT:
            reason = "represented target positively matches a NEVER root"
        elif decision.outcome is SecurityOutcome.DENY_AND_CONTINUE:
            reason = "represented target is outside the configured workspace"
        else:
            reason = "represented target is authorized by Phase-4 path policy"
        return _legacy_path_decision(path_policy, decision, reason, canonical)

    governed._jack_phase5_consequence_gate = True
    path_policy.authorize_represented_path = governed


def install(jk: Any) -> None:
    """Install only integrations whose disposition and containment are grounded."""
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

    # Phase 4 still owns path normalization and represented-target facts. Phase 5
    # now owns the final mapping of those facts into ALLOW / DENY / HARD while
    # preserving the existing Phase-4 release object and containment behavior.
    _install_represented_path_gate()

    original_executor_admission = getattr(jk, "_phase4_executor_admission_decision", None)
    if callable(original_executor_admission):
        @wraps(original_executor_admission)
        def governed_executor_admission(
            payload: Any,
            *,
            expected_call: Optional[dict[str, Any]] = None,
        ) -> Any:
            allowed_fields = {
                "protocol_version", "runtime_id", "lane_id", "tool_call_id",
                "tool_name", "arguments", "executor_cwd", "executor_platform",
                "command_dialect",
            }
            protocol_version = getattr(
                jk, "PHASE4_EXECUTOR_ADMISSION_PROTOCOL_VERSION", None
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
                        call_matches=True,
                    ),
                ))
                if decision.outcome is SecurityOutcome.DENY_AND_CONTINUE:
                    if decision.containment_scope is not ContainmentScope.EXECUTOR_ADMISSION:
                        raise AssertionError("Executor identity denial escaped admission scope")
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
            return original_executor_admission(payload, expected_call=expected_call)

        jk._phase4_executor_admission_decision = governed_executor_admission

    register_manifest = getattr(jk, "_register_runtime_manifest_components", None)
    if callable(register_manifest):
        register_manifest({"jack_consequence_gate.py": Path(__file__).resolve()})

    jk._JACK_CONSEQUENCE_GATE_INSTALLED = True
