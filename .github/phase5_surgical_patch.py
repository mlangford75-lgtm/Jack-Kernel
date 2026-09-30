from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require_replace(path: Path, old: str, new: str, *, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{path}: expected {count} exact match(es), found {found}")
    path.write_text(text.replace(old, new, count), encoding="utf-8", newline="\n")


def patch_kernel_installer() -> None:
    path = ROOT / "jack_kernel.py"
    text = path.read_text(encoding="utf-8")

    old_imports = (
        "    import jack_evidence_guard\n"
        "    import jack_path_policy\n"
        "    import jack_responses_compat\n"
    )
    new_imports = (
        "    import jack_consequence_gate\n"
        "    import jack_evidence_guard\n"
        "    import jack_path_policy\n"
        "    import jack_responses_compat\n"
    )
    if text.count(old_imports) != 1:
        raise RuntimeError("Kernel bundled-extension import seam changed")
    text = text.replace(old_imports, new_imports, 1)

    old_release = "    jack_responses_compat.register(module)\n"
    new_release = (
        "    # Phase 5 is Kernel-owned authority. Install it explicitly here,\n"
        "    # after predecessor security policy is bound and before compatibility\n"
        "    # surfaces are registered. Compatibility modules do not bootstrap it.\n"
        "    jack_consequence_gate.install(module)\n\n"
        "    jack_responses_compat.register(module)\n"
    )
    if text.count(old_release) != 1:
        raise RuntimeError("Kernel Responses registration seam changed")
    text = text.replace(old_release, new_release, 1)

    old_manifest = (
        '        "jack_evidence_guard.py": Path(jack_evidence_guard.__file__).resolve(),\n'
        '        "jack_path_policy.py": Path(jack_path_policy.__file__).resolve(),\n'
        '        "jack_responses_compat.py": Path(jack_responses_compat.__file__).resolve(),\n'
    )
    new_manifest = (
        '        "jack_evidence_guard.py": Path(jack_evidence_guard.__file__).resolve(),\n'
        '        "jack_path_policy.py": Path(jack_path_policy.__file__).resolve(),\n'
        '        "jack_consequence_gate.py": Path(jack_consequence_gate.__file__).resolve(),\n'
        '        "jack_responses_compat.py": Path(jack_responses_compat.__file__).resolve(),\n'
    )
    if text.count(old_manifest) != 1:
        raise RuntimeError("Kernel runtime-manifest seam changed")
    text = text.replace(old_manifest, new_manifest, 1)

    path.write_text(text, encoding="utf-8", newline="\n")


def patch_responses_compat() -> None:
    path = ROOT / "jack_responses_compat.py"
    text = path.read_text(encoding="utf-8")
    old = '''def register(jk: Any) -> None:\n    # This is the shared bundled-extension convergence seam used by direct\n    # jack_kernel.py startup, the secure launcher, and Responses compatibility.\n    # Install Phase 5 before route idempotence can return so every supported\n    # Kernel runtime path receives the same consequence-disposition boundary.\n    import jack_consequence_gate\n    jack_consequence_gate.install(jk)\n\n    if any(getattr(route, "path", None) == "/v1/responses" for route in jk.APP.routes):\n'''
    new = '''def register(jk: Any) -> None:\n    if any(getattr(route, "path", None) == "/v1/responses" for route in jk.APP.routes):\n'''
    if text.count(old) != 1:
        raise RuntimeError("Responses Phase-5 bootstrap seam changed")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


PATH_FACT_DATACLASS = '''\n\n@dataclass(frozen=True)\nclass RepresentedPathAuthorityFacts:\n    """Raw deterministic Phase-4 represented-target facts.\n\n    This is the single path-policy fact representation used by both the legacy\n    Phase-4 compatibility decision and the Phase-5 Consequence Gate. It never\n    claims filesystem-object resolution or host-effect realization.\n    """\n\n    canonical_target: Optional[str]\n    never_match: bool\n    workspace_configured: bool\n    deterministic: bool\n    inside_workspace: Optional[bool]\n    invalid: bool\n    deferred_to_executor: bool\n    reason: str\n'''


PATH_AUTH_BLOCK = r'''def inspect_represented_path(
    policy: RuntimePathPolicy,
    represented_path: Any,
    *,
    executor_cwd: Optional[str] = None,
    defer_relative_without_executor: bool = False,
) -> RepresentedPathAuthorityFacts:
    """Produce raw represented-path facts without choosing a security outcome."""

    if not isinstance(policy, RuntimePathPolicy):
        raise TypeError("policy must be a RuntimePathPolicy")

    environment = policy.path_environment()
    canonical_cwd = None

    if executor_cwd is not None:
        try:
            canonical_cwd = normalize_represented_windows_path(
                executor_cwd,
                environment=environment,
            )
        except RepresentedPathError as exc:
            return RepresentedPathAuthorityFacts(
                canonical_target=None,
                never_match=False,
                workspace_configured=policy.workspace_enabled,
                deterministic=False,
                inside_workspace=None,
                invalid=True,
                deferred_to_executor=False,
                reason=(
                    "executor cwd is not a deterministic absolute Windows path: "
                    f"{exc}"
                ),
            )

    try:
        canonical = normalize_represented_windows_path(
            represented_path,
            base_root=canonical_cwd,
            environment=environment,
        )
    except RepresentedPathNeedsExecutorCwd as exc:
        if defer_relative_without_executor:
            return RepresentedPathAuthorityFacts(
                canonical_target=None,
                never_match=False,
                workspace_configured=policy.workspace_enabled,
                deterministic=False,
                inside_workspace=None,
                invalid=False,
                deferred_to_executor=True,
                reason=f"executor cwd admission is required before execution: {exc}",
            )
        return RepresentedPathAuthorityFacts(
            canonical_target=None,
            never_match=False,
            workspace_configured=policy.workspace_enabled,
            deterministic=False,
            inside_workspace=None,
            invalid=False,
            deferred_to_executor=False,
            reason=(
                f"workspace membership cannot be established: {exc}"
                if policy.workspace_enabled
                else f"no workspace lock; represented target unresolved: {exc}"
            ),
        )
    except RepresentedPathInvalid as exc:
        return RepresentedPathAuthorityFacts(
            canonical_target=None,
            never_match=False,
            workspace_configured=policy.workspace_enabled,
            deterministic=False,
            inside_workspace=None,
            invalid=True,
            deferred_to_executor=False,
            reason=f"invalid represented path: {exc}",
        )
    except RepresentedPathAmbiguous as exc:
        return RepresentedPathAuthorityFacts(
            canonical_target=None,
            never_match=False,
            workspace_configured=policy.workspace_enabled,
            deterministic=False,
            inside_workspace=None,
            invalid=False,
            deferred_to_executor=False,
            reason=(
                f"workspace membership cannot be established: {exc}"
                if policy.workspace_enabled
                else f"no workspace lock; represented target unresolved: {exc}"
            ),
        )

    try:
        comparison_target = _policy_object_windows_path(canonical)
    except RepresentedPathAmbiguous as exc:
        return RepresentedPathAuthorityFacts(
            canonical_target=canonical,
            never_match=False,
            workspace_configured=policy.workspace_enabled,
            deterministic=False,
            inside_workspace=None,
            invalid=False,
            deferred_to_executor=False,
            reason=(
                f"workspace membership cannot be established: {exc}"
                if policy.workspace_enabled
                else f"no workspace lock; represented target unresolved: {exc}"
            ),
        )

    never_match = any(
        path_is_within_or_equal(comparison_target, never_root)
        for never_root in policy.never_roots
    )
    inside_workspace = (
        None
        if policy.workspace_root is None
        else path_is_within_or_equal(
            comparison_target,
            policy.workspace_root,
        )
    )

    if never_match:
        reason = "represented target positively matches a NEVER root"
    elif inside_workspace is False:
        reason = "represented target is outside the configured workspace"
    else:
        reason = "represented target is authorized by Phase-4 path policy"

    return RepresentedPathAuthorityFacts(
        canonical_target=canonical,
        never_match=never_match,
        workspace_configured=policy.workspace_enabled,
        deterministic=True,
        inside_workspace=inside_workspace,
        invalid=False,
        deferred_to_executor=False,
        reason=reason,
    )


def authorize_represented_path(
    policy: RuntimePathPolicy,
    represented_path: Any,
    *,
    executor_cwd: Optional[str] = None,
    defer_relative_without_executor: bool = False,
) -> PathAuthorizationDecision:
    """Legacy Phase-4 decision mapped from the shared raw fact producer."""

    facts = inspect_represented_path(
        policy,
        represented_path,
        executor_cwd=executor_cwd,
        defer_relative_without_executor=defer_relative_without_executor,
    )

    if facts.deferred_to_executor:
        outcome = PathAuthorizationOutcome.ALLOW
    elif facts.never_match:
        outcome = PathAuthorizationOutcome.HARD_INTERRUPT
    elif facts.invalid:
        outcome = PathAuthorizationOutcome.DENY_AND_CONTINUE
    elif facts.workspace_configured and (
        not facts.deterministic or facts.inside_workspace is False
    ):
        outcome = PathAuthorizationOutcome.DENY_AND_CONTINUE
    else:
        outcome = PathAuthorizationOutcome.ALLOW

    return PathAuthorizationDecision(
        outcome,
        facts.reason,
        facts.canonical_target,
    )
'''


def patch_path_policy() -> None:
    path = ROOT / "jack_path_policy.py"
    text = path.read_text(encoding="utf-8")

    if "class RepresentedPathAuthorityFacts" not in text:
        marker = "\n\n@dataclass(frozen=True)\nclass StructuredToolPathContract:"
        if text.count(marker) != 1:
            raise RuntimeError("Path-policy dataclass insertion seam changed")
        text = text.replace(marker, PATH_FACT_DATACLASS + marker, 1)

    start = text.find("\ndef authorize_represented_path(")
    end = text.find("\ndef authorize_structured_tool_call(", start)
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError("Path-policy authorize_represented_path seam changed")
    text = text[: start + 1] + PATH_AUTH_BLOCK + "\n\n" + text[end + 1 :]
    path.write_text(text, encoding="utf-8", newline="\n")


GATE_CONTENT = r'''from __future__ import annotations

import contextvars
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any, Callable, Iterable, Optional, Tuple, Union

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
    """The fact is authoritative, but Phase 5 has no justified mapping yet."""


@dataclass(frozen=True)
class StageToolAuthorityFact:
    authorized: bool


@dataclass(frozen=True)
class ToolSchemaFact:
    valid: bool
    errors: Tuple[str, ...] = ()


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
class ReservedEvidenceNamespaceFact:
    """Narrow evidence fact grounded in the existing reserved-marker guard.

    Unknown provenance is intentionally not represented as a violation here.
    Phase 5 does not claim a generalized evidence-trust classifier.
    """

    forged: bool


@dataclass(frozen=True)
class ApprovalFact:
    """Policy contract only; no live approval producer exists in Phase 5."""

    approval_required: bool
    approval_valid: bool


@dataclass(frozen=True)
class LifecycleAuthorityFact:
    """Grounded identity facts whose mismatch disposition remains unmapped."""

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
        raise RuntimeError(
            "Jack Kernel SecurityOutcome vocabulary is not iterable"
        ) from exc


def _require_compatible_outcome_type(outcome_type: Any) -> None:
    if _enum_values(outcome_type) != _EXPECTED_OUTCOME_VALUES:
        raise RuntimeError(
            "Jack Kernel SecurityOutcome vocabulary does not match Phase-5 contract"
        )


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
        denied = not fact.authorized
        return _single(
            fact,
            deny if denied else allow,
            ContainmentScope.TOOL_CALL if denied else ContainmentScope.NONE,
            denied,
        )

    if isinstance(fact, ToolSchemaFact):
        denied = not fact.valid
        return _single(
            fact,
            deny if denied else allow,
            ContainmentScope.TOOL_CALL if denied else ContainmentScope.NONE,
            denied,
        )

    if isinstance(fact, path_policy.RepresentedPathAuthorityFacts):
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

    if isinstance(fact, ReservedEvidenceNamespaceFact):
        return _single(
            fact,
            deny if fact.forged else allow,
            ContainmentScope.EVIDENCE_FRAGMENT if fact.forged else ContainmentScope.NONE,
            fact.forged,
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


def evaluate_consequence(
    facts: Iterable[AuthorityFact],
    *,
    outcome_type: Any,
    boundary: Optional[ConsequenceBoundary] = None,
) -> ConsequenceDecision:
    """Map grounded raw facts to outcome plus minimum containment scope.

    The Kernel supplies its authoritative SecurityOutcome type. This module does
    not import, discover, alias, or reconstruct a Jack Kernel module identity.
    """

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
        pair for pair in non_allow
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


def _bound_evaluator(outcome_type: Any) -> Callable[..., ConsequenceDecision]:
    _require_compatible_outcome_type(outcome_type)

    def bound(
        facts: Iterable[AuthorityFact],
        *,
        boundary: Optional[ConsequenceBoundary] = None,
    ) -> ConsequenceDecision:
        return evaluate_consequence(
            facts,
            outcome_type=outcome_type,
            boundary=boundary,
        )

    return bound


def _legacy_path_decision(
    decision: ConsequenceDecision,
    raw: path_policy.RepresentedPathAuthorityFacts,
) -> path_policy.PathAuthorizationDecision:
    try:
        legacy = path_policy.PathAuthorizationOutcome(decision.outcome.value)
    except ValueError as exc:
        raise AssertionError(
            "Phase-5 path decision cannot be represented by Phase-4 release machinery"
        ) from exc
    return path_policy.PathAuthorizationDecision(
        legacy,
        raw.reason,
        raw.canonical_target,
    )


def _install_represented_path_gate(
    evaluator: Callable[..., ConsequenceDecision],
) -> None:
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

    jk._JACK_CONSEQUENCE_GATE_INSTALLED = True
'''


CONSEQUENCE_TESTS = r'''from __future__ import annotations

from types import SimpleNamespace

import pytest

import jack_consequence_gate as gate
import jack_kernel as kernel
import jack_path_policy as path_policy


def decide(*facts, boundary=None):
    return gate.evaluate_consequence(
        facts,
        outcome_type=kernel.SecurityOutcome,
        boundary=boundary,
    )


def raw_path(**overrides):
    values = dict(
        canonical_target=r"d:\\projects\\jack\\item.txt",
        never_match=False,
        workspace_configured=False,
        deterministic=True,
        inside_workspace=None,
        invalid=False,
        deferred_to_executor=False,
        reason="test fact",
    )
    values.update(overrides)
    return path_policy.RepresentedPathAuthorityFacts(**values)


def test_allow_has_no_containment_scope():
    decision = decide(
        gate.StageToolAuthorityFact(authorized=True),
        gate.ToolSchemaFact(valid=True),
    )
    assert decision.outcome is kernel.SecurityOutcome.ALLOW
    assert decision.containment_scope is gate.ContainmentScope.NONE
    assert decision.decisive_fact is None


def test_stage_tool_denial_is_call_scoped():
    decision = decide(gate.StageToolAuthorityFact(authorized=False))
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert decision.containment_scope is gate.ContainmentScope.TOOL_CALL


def test_bad_schema_is_recoverable_and_call_scoped_policy_contract():
    decision = decide(
        gate.ToolSchemaFact(valid=False, errors=("missing required field",))
    )
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert decision.containment_scope is gate.ContainmentScope.TOOL_CALL


def test_workspace_outside_is_call_scoped_denial():
    decision = decide(
        raw_path(
            workspace_configured=True,
            inside_workspace=False,
        )
    )
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert decision.containment_scope is gate.ContainmentScope.TOOL_CALL


def test_workspace_ambiguity_is_not_hard_interrupt():
    decision = decide(
        raw_path(
            canonical_target=None,
            workspace_configured=True,
            deterministic=False,
            inside_workspace=None,
        )
    )
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert decision.containment_scope is gate.ContainmentScope.TOOL_CALL


def test_ambiguity_without_workspace_does_not_invent_restriction():
    decision = decide(
        raw_path(
            canonical_target=None,
            deterministic=False,
        )
    )
    assert decision.outcome is kernel.SecurityOutcome.ALLOW


def test_never_match_at_prerelease_keeps_existing_hard_batch_boundary():
    decision = decide(
        raw_path(
            never_match=True,
            workspace_configured=True,
            inside_workspace=False,
        ),
        boundary=gate.ConsequenceBoundary.TOOL_RELEASE_BATCH,
    )
    assert decision.outcome is kernel.SecurityOutcome.HARD_INTERRUPT
    assert decision.containment_scope is gate.ContainmentScope.TOOL_BATCH


def test_same_never_fact_at_executor_admission_has_narrower_blast_radius():
    decision = decide(
        raw_path(
            never_match=True,
            workspace_configured=True,
            inside_workspace=False,
        ),
        boundary=gate.ConsequenceBoundary.EXECUTOR_ADMISSION,
    )
    assert decision.outcome is kernel.SecurityOutcome.HARD_INTERRUPT
    assert decision.containment_scope is gate.ContainmentScope.EXECUTOR_ADMISSION


def test_executor_identity_mismatch_is_admission_scoped():
    decision = decide(
        gate.ExecutorAdmissionIdentityFact(
            runtime_matches=False,
            lane_matches=True,
            call_matches=True,
        )
    )
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert decision.containment_scope is gate.ContainmentScope.EXECUTOR_ADMISSION


def test_open_run_blocks_only_overlap_admission():
    decision = decide(
        gate.SettlementFact(
            run_open=True,
            overlapping_admission_requested=True,
        )
    )
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert decision.containment_scope is gate.ContainmentScope.OVERLAP_ADMISSION


def test_reserved_evidence_namespace_absent_does_not_invent_violation():
    decision = decide(gate.ReservedEvidenceNamespaceFact(forged=False))
    assert decision.outcome is kernel.SecurityOutcome.ALLOW


def test_reserved_evidence_forgery_is_fragment_scoped():
    decision = decide(gate.ReservedEvidenceNamespaceFact(forged=True))
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert decision.containment_scope is gate.ContainmentScope.EVIDENCE_FRAGMENT


def test_no_generalized_security_health_fact_is_claimed():
    assert not hasattr(gate, "SecurityHealthFact")
    with pytest.raises(TypeError):
        decide(SimpleNamespace(healthy=False))


def test_approval_contract_holds_only_that_consequence():
    decision = decide(
        gate.ApprovalFact(
            approval_required=True,
            approval_valid=False,
        )
    )
    assert decision.outcome is kernel.SecurityOutcome.REQUIRE_USER_DECISION
    assert decision.containment_scope is gate.ContainmentScope.CONSEQUENCE


def test_lifecycle_mismatch_refuses_unjustified_mapping():
    with pytest.raises(gate.UnmappedAuthorityFact):
        decide(
            gate.LifecycleAuthorityFact(
                task_matches=False,
                run_matches=True,
                run_epoch_matches=True,
            )
        )


def test_conflicting_nonhard_outcomes_are_not_reordered():
    with pytest.raises(RuntimeError):
        decide(
            gate.ToolSchemaFact(valid=False, errors=("invalid",)),
            gate.ApprovalFact(approval_required=True, approval_valid=False),
        )


def test_different_nonhard_scopes_are_not_broadened():
    with pytest.raises(RuntimeError):
        decide(
            gate.ToolSchemaFact(valid=False, errors=("invalid",)),
            gate.ExecutorAdmissionIdentityFact(
                runtime_matches=False,
                lane_matches=True,
                call_matches=True,
            ),
        )


def test_boundary_must_be_host_owned_enum():
    with pytest.raises(TypeError):
        gate.evaluate_consequence(
            (raw_path(),),
            outcome_type=kernel.SecurityOutcome,
            boundary="executor_admission",
        )


def test_empty_gate_does_not_silently_allow():
    with pytest.raises(ValueError):
        gate.evaluate_consequence((), outcome_type=kernel.SecurityOutcome)
'''


PATH_TESTS = r'''from __future__ import annotations

import inspect
import json

import pytest

import jack_consequence_gate as gate
import jack_kernel as kernel
import jack_path_policy as path_policy


HOST_ENV = {
    "SystemRoot": r"C:\Windows",
    "WINDIR": r"C:\Windows",
    "SystemDrive": "C:",
    "USERPROFILE": r"C:\Users\Operator",
}


def build(workspace=r"D:\Projects\Jack"):
    return path_policy.build_runtime_path_policy(
        runtime_id="phase5-test-runtime",
        lane_id="phase5-test-lane",
        raw_json=json.dumps(
            {
                "version": 1,
                "workspace_root": workspace,
                "never_paths": [r"D:\Sensitive"],
            }
        ),
        host_environment=HOST_ENV,
    )


@pytest.fixture
def installed_path_gate():
    original = path_policy.authorize_represented_path
    evaluator = gate._bound_evaluator(kernel.SecurityOutcome)
    gate._install_represented_path_gate(evaluator)
    try:
        yield
    finally:
        path_policy.authorize_represented_path = original


def test_path_policy_owns_single_raw_fact_producer():
    legacy_source = inspect.getsource(path_policy.authorize_represented_path)
    gate_source = inspect.getsource(gate._install_represented_path_gate)
    assert "inspect_represented_path(" in legacy_source
    assert "path_policy.inspect_represented_path(" in gate_source


def test_raw_path_facts_report_never_without_disposition():
    facts = path_policy.inspect_represented_path(
        build(),
        r"D:\Sensitive\secret.txt",
    )
    assert facts.never_match is True
    assert facts.workspace_configured is True
    assert facts.deterministic is True
    assert facts.canonical_target is not None
    assert not hasattr(facts, "outcome")


def test_raw_path_facts_report_workspace_membership_without_disposition():
    facts = path_policy.inspect_represented_path(
        build(),
        r"D:\Other\artifact.txt",
    )
    assert facts.never_match is False
    assert facts.inside_workspace is False
    assert facts.deterministic is True
    assert not hasattr(facts, "outcome")


def test_raw_path_facts_preserve_fail_soft_unknown():
    facts = path_policy.inspect_represented_path(
        build(None),
        r"relative\target.txt",
    )
    assert facts.workspace_configured is False
    assert facts.deterministic is False
    assert facts.invalid is False
    assert facts.canonical_target is None


def test_legacy_phase4_mapping_preserves_never_hard_interrupt():
    decision = path_policy.authorize_represented_path(
        build(),
        r"D:\Sensitive\secret.txt",
    )
    assert decision.outcome is path_policy.PathAuthorizationOutcome.HARD_INTERRUPT


def test_legacy_phase4_mapping_preserves_workspace_denial():
    decision = path_policy.authorize_represented_path(
        build(),
        r"D:\Other\artifact.txt",
    )
    assert decision.outcome is path_policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


def test_gate_preserves_never_hard_interrupt(installed_path_gate):
    decision = path_policy.authorize_represented_path(
        build(),
        r"D:\Sensitive\secret.txt",
    )
    assert decision.outcome is path_policy.PathAuthorizationOutcome.HARD_INTERRUPT


def test_gate_preserves_workspace_narrow_denial(installed_path_gate):
    decision = path_policy.authorize_represented_path(
        build(),
        r"D:\Other\artifact.txt",
    )
    assert decision.outcome is path_policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


def test_gate_preserves_inside_workspace_allow(installed_path_gate):
    decision = path_policy.authorize_represented_path(
        build(),
        r"D:\Projects\Jack\src\engine.py",
    )
    assert decision.outcome is path_policy.PathAuthorizationOutcome.ALLOW


def test_gate_preserves_no_workspace_fail_soft_ambiguity(installed_path_gate):
    decision = path_policy.authorize_represented_path(
        build(None),
        r"relative\target.txt",
    )
    assert decision.outcome is path_policy.PathAuthorizationOutcome.ALLOW
    assert decision.canonical_target is None


def test_gate_preserves_workspace_relative_cwd_requirement(installed_path_gate):
    decision = path_policy.authorize_represented_path(
        build(),
        r"relative\target.txt",
    )
    assert decision.outcome is path_policy.PathAuthorizationOutcome.DENY_AND_CONTINUE
    assert decision.canonical_target is None


def test_gate_preserves_deferred_executor_cwd_admission(installed_path_gate):
    decision = path_policy.authorize_represented_path(
        build(),
        r"relative\target.txt",
        defer_relative_without_executor=True,
    )
    assert decision.outcome is path_policy.PathAuthorizationOutcome.ALLOW
    assert decision.canonical_target is None
    assert "executor cwd admission" in decision.reason


def test_gate_preserves_invalid_path_rejection_without_workspace(installed_path_gate):
    decision = path_policy.authorize_represented_path(
        build(None),
        "",
    )
    assert decision.outcome is path_policy.PathAuthorizationOutcome.DENY_AND_CONTINUE
'''


RUNTIME_TESTS = r'''from __future__ import annotations

import inspect
from enum import Enum
from types import SimpleNamespace

import pytest

import jack_consequence_gate as gate
import jack_kernel as kernel
import jack_responses_compat as responses_compat


def test_kernel_installer_explicitly_owns_phase5_installation():
    source = inspect.getsource(kernel._install_bundled_runtime_extensions)
    assert "import jack_consequence_gate" in source
    assert "jack_consequence_gate.install(module)" in source
    assert "jack_responses_compat.register(module)" in source
    assert source.index("jack_consequence_gate.install(module)") < source.index(
        "jack_responses_compat.register(module)"
    )


def test_responses_compatibility_is_not_phase5_security_root():
    source = inspect.getsource(responses_compat.register)
    assert "jack_consequence_gate" not in source
    assert "Consequence Gate" not in source


def test_gate_does_not_reconstruct_kernel_identity_at_import_time():
    source = inspect.getsource(gate)
    assert "_active_kernel_module" not in source
    assert 'sys.modules["jack_kernel"]' not in source
    assert "import jack_kernel" not in source


def test_install_rejects_incompatible_kernel_outcome_vocabulary(monkeypatch):
    class OtherOutcome(str, Enum):
        ALLOW = "ALLOW"
        HARD_INTERRUPT = "HARD_INTERRUPT"

    fake = SimpleNamespace(SecurityOutcome=OtherOutcome)
    monkeypatch.setattr(gate, "_install_represented_path_gate", lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError, match="SecurityOutcome vocabulary"):
        gate.install(fake)


def test_equivalent_isolated_kernel_enum_receives_its_own_outcome_type(monkeypatch):
    class IsolatedOutcome(str, Enum):
        ALLOW = "ALLOW"
        DENY_AND_CONTINUE = "DENY_AND_CONTINUE"
        REQUIRE_USER_DECISION = "REQUIRE_USER_DECISION"
        HARD_INTERRUPT = "HARD_INTERRUPT"

    fake = SimpleNamespace(SecurityOutcome=IsolatedOutcome)
    monkeypatch.setattr(gate, "_install_represented_path_gate", lambda *args, **kwargs: None)

    gate.install(fake)
    decision = fake.evaluate_consequence((gate.StageToolAuthorityFact(authorized=False),))

    assert decision.outcome is IsolatedOutcome.DENY_AND_CONTINUE
    assert decision.containment_scope is gate.ContainmentScope.TOOL_CALL


def _fake_kernel_namespace():
    class FakeHTTPException(RuntimeError):
        def __init__(self, *, status_code, detail):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class FakeKernel:
        SecurityOutcome = kernel.SecurityOutcome
        HTTPException = FakeHTTPException
        PHASE4_EXECUTOR_ADMISSION_PROTOCOL_VERSION = 1
        RUNTIME_ID = "runtime-1"
        LANE_ID = "lane-1"

        @staticmethod
        def _phase4_executor_admission_decision(payload, *, expected_call=None):
            return {"outcome": "ALLOW", "payload": payload}

    return FakeKernel


def _executor_payload(*, runtime_id="runtime-1", lane_id="lane-1"):
    return {
        "protocol_version": 1,
        "runtime_id": runtime_id,
        "lane_id": lane_id,
        "tool_call_id": "phase5-integration-call",
        "tool_name": "read",
        "arguments": {"path": r"src\\engine.py"},
        "executor_cwd": r"D:\\Projects\\Jack",
        "executor_platform": "win32",
    }


def _install_admission_only(fake, monkeypatch):
    monkeypatch.setattr(gate, "_install_represented_path_gate", lambda *args, **kwargs: None)
    gate.install(fake)


def test_executor_runtime_identity_mismatch_remains_admission_scoped(monkeypatch):
    fake = _fake_kernel_namespace()
    _install_admission_only(fake, monkeypatch)

    with pytest.raises(fake.HTTPException) as caught:
        fake._phase4_executor_admission_decision(
            _executor_payload(runtime_id="wrong-runtime")
        )

    assert caught.value.status_code == 409
    assert "runtime identity mismatch" in str(caught.value.detail)


def test_executor_lane_identity_mismatch_remains_admission_scoped(monkeypatch):
    fake = _fake_kernel_namespace()
    _install_admission_only(fake, monkeypatch)

    with pytest.raises(fake.HTTPException) as caught:
        fake._phase4_executor_admission_decision(
            _executor_payload(lane_id="wrong-lane")
        )

    assert caught.value.status_code == 409
    assert "lane identity mismatch" in str(caught.value.detail)
'''


def rewrite_small_files() -> None:
    (ROOT / "jack_consequence_gate.py").write_text(
        GATE_CONTENT,
        encoding="utf-8",
        newline="\n",
    )
    (ROOT / "tests" / "test_phase5_consequence_gate.py").write_text(
        CONSEQUENCE_TESTS,
        encoding="utf-8",
        newline="\n",
    )
    (ROOT / "tests" / "test_phase5_path_gate_integration.py").write_text(
        PATH_TESTS,
        encoding="utf-8",
        newline="\n",
    )
    (ROOT / "tests" / "test_phase5_runtime_integration.py").write_text(
        RUNTIME_TESTS,
        encoding="utf-8",
        newline="\n",
    )

    old_fact_module = ROOT / "jack_path_authority_facts.py"
    if old_fact_module.exists():
        old_fact_module.unlink()

    ci = ROOT / ".github" / "workflows" / "ci.yml"
    ci_text = ci.read_text(encoding="utf-8")
    ci_text = ci_text.replace(
        "jack_path_policy.py jack_path_authority_facts.py jack_responses_compat.py jack_consequence_gate.py",
        "jack_path_policy.py jack_responses_compat.py jack_consequence_gate.py",
    )
    ci.write_text(ci_text, encoding="utf-8", newline="\n")


def cleanup_patch_scaffolding() -> None:
    for relative in (
        ".github/phase5_surgical_patch.py",
        ".github/workflows/phase5-surgical-patch.yml",
    ):
        path = ROOT / relative
        if path.exists():
            path.unlink()


def main() -> None:
    patch_kernel_installer()
    patch_responses_compat()
    patch_path_policy()
    rewrite_small_files()
    cleanup_patch_scaffolding()


if __name__ == "__main__":
    main()
