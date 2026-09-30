from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_kernel() -> None:
    path = ROOT / "jack_kernel.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "    import jack_evidence_guard\n    import jack_path_policy\n    import jack_responses_compat\n",
        "    import jack_consequence_gate\n    import jack_evidence_guard\n    import jack_path_policy\n    import jack_responses_compat\n",
        "kernel bundled imports",
    )
    text = replace_once(
        text,
        "\n    jack_responses_compat.register(module)\n    root = Path(__file__).resolve().parent\n",
        "\n    # Phase 5 is Kernel-owned authority. Install it explicitly from the shared\n"
        "    # bundled-extension seam after predecessor security policy is bound and\n"
        "    # before compatibility surfaces are registered.\n"
        "    jack_consequence_gate.install(module)\n\n"
        "    jack_responses_compat.register(module)\n"
        "    root = Path(__file__).resolve().parent\n",
        "kernel gate install seam",
    )
    text = replace_once(
        text,
        '        "jack_path_policy.py": Path(jack_path_policy.__file__).resolve(),\n        "jack_responses_compat.py": Path(jack_responses_compat.__file__).resolve(),\n',
        '        "jack_path_policy.py": Path(jack_path_policy.__file__).resolve(),\n        "jack_consequence_gate.py": Path(jack_consequence_gate.__file__).resolve(),\n        "jack_responses_compat.py": Path(jack_responses_compat.__file__).resolve(),\n',
        "kernel runtime manifest",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_responses() -> None:
    path = ROOT / "jack_responses_compat.py"
    text = path.read_text(encoding="utf-8")
    old = '''def register(jk: Any) -> None:\n    # This is the shared bundled-extension convergence seam used by direct\n    # jack_kernel.py startup, the secure launcher, and Responses compatibility.\n    # Install Phase 5 before route idempotence can return so every supported\n    # Kernel runtime path receives the same consequence-disposition boundary.\n    import jack_consequence_gate\n    jack_consequence_gate.install(jk)\n\n    if any(getattr(route, "path", None) == "/v1/responses" for route in jk.APP.routes):\n'''
    new = '''def register(jk: Any) -> None:\n    if any(getattr(route, "path", None) == "/v1/responses" for route in jk.APP.routes):\n'''
    text = replace_once(text, old, new, "Responses compatibility gate bootstrap")
    path.write_text(text, encoding="utf-8", newline="\n")


RAW_FACT_CLASS = '''\n\n@dataclass(frozen=True)\nclass RepresentedPathAuthorityFacts:\n    """Raw deterministic Phase-4 represented-target facts.\n\n    This is the single fact representation for represented-path normalization,\n    NEVER matching, Workspace Lock membership, ambiguity, and executor-cwd\n    deferral. It never claims final filesystem-object resolution or host effect.\n    """\n\n    canonical_target: Optional[str]\n    never_match: bool\n    workspace_configured: bool\n    deterministic: bool\n    inside_workspace: Optional[bool]\n    invalid: bool\n    deferred_to_executor: bool\n    reason: str\n'''


RAW_AND_LEGACY = r'''def inspect_represented_path(
    policy: RuntimePathPolicy,
    represented_path: Any,
    *,
    executor_cwd: Optional[str] = None,
    defer_relative_without_executor: bool = False,
) -> RepresentedPathAuthorityFacts:
    """Establish raw path facts without choosing a Phase-5 SecurityOutcome."""

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
        else path_is_within_or_equal(comparison_target, policy.workspace_root)
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
    """Legacy Phase-4 mapping from the shared raw represented-path facts."""

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
    marker = "\n\n@dataclass(frozen=True)\nclass StructuredToolPathContract:"
    if "class RepresentedPathAuthorityFacts" not in text:
        text = replace_once(
            text,
            marker,
            RAW_FACT_CLASS + marker,
            "raw path fact insertion",
        )

    start = text.find("def authorize_represented_path(\n")
    end = text.find("\n\ndef authorize_command_tool_call(\n", start)
    if start < 0:
        raise RuntimeError("authorize_represented_path start not found")
    if end < 0:
        # Current source orders authorize_command_tool_call before the represented
        # path mapper, so use EOF after the represented-path function instead.
        end = len(text)
    else:
        raise RuntimeError("unexpected path-policy function ordering")

    # The represented-path mapper is currently the final function in this module.
    current_tail = text[start:]
    if "return PathAuthorizationDecision(" not in current_tail:
        raise RuntimeError("represented-path mapper tail is not recognized")
    text = text[:start] + RAW_AND_LEGACY + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


GATE = r'''from __future__ import annotations

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
    runtime_matches: bool
    lane_matches: bool
    call_matches: bool = True


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
        ok = fact.runtime_matches and fact.lane_matches and fact.call_matches
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
        return _legacy_path_decision(evaluator((raw,)), raw)

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
            token = _CURRENT_CONSEQUENCE_BOUNDARY.set(ConsequenceBoundary.TOOL_RELEASE_BATCH)
            try:
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
                    (ExecutorAdmissionIdentityFact(runtime_matches=runtime_matches, lane_matches=lane_matches, call_matches=True),),
                    boundary=ConsequenceBoundary.EXECUTOR_ADMISSION,
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
                return original_admission(payload, expected_call=expected_call)
            finally:
                _CURRENT_CONSEQUENCE_BOUNDARY.reset(token)
        jk._phase4_executor_admission_decision = governed_admission

    jk._JACK_CONSEQUENCE_GATE_INSTALLED = True
'''


TEST_GATE = r'''from __future__ import annotations

from types import SimpleNamespace

import pytest

import jack_consequence_gate as gate
import jack_kernel as kernel
import jack_path_policy as path_policy


def decide(*facts, boundary=None):
    return gate.evaluate_consequence(facts, outcome_type=kernel.SecurityOutcome, boundary=boundary)


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


def test_valid_action_allows_without_containment():
    d = decide(gate.StageToolAuthorityFact(True), gate.ToolSchemaFact(True))
    assert d.outcome is kernel.SecurityOutcome.ALLOW
    assert d.containment_scope is gate.ContainmentScope.NONE


def test_bad_schema_is_recoverable_call_scoped_contract():
    d = decide(gate.ToolSchemaFact(False, ("bad",)))
    assert d.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert d.containment_scope is gate.ContainmentScope.TOOL_CALL


def test_wrong_stage_tool_authority_is_recoverable_call_scoped():
    d = decide(gate.StageToolAuthorityFact(False))
    assert d.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert d.containment_scope is gate.ContainmentScope.TOOL_CALL


def test_never_match_preserves_hard_batch_boundary():
    d = decide(raw_path(never_match=True), boundary=gate.ConsequenceBoundary.TOOL_RELEASE_BATCH)
    assert d.outcome is kernel.SecurityOutcome.HARD_INTERRUPT
    assert d.containment_scope is gate.ContainmentScope.TOOL_BATCH


def test_same_never_fact_at_executor_admission_is_admission_scoped():
    d = decide(raw_path(never_match=True), boundary=gate.ConsequenceBoundary.EXECUTOR_ADMISSION)
    assert d.outcome is kernel.SecurityOutcome.HARD_INTERRUPT
    assert d.containment_scope is gate.ContainmentScope.EXECUTOR_ADMISSION


def test_workspace_denial_is_call_scoped():
    d = decide(raw_path(workspace_configured=True, inside_workspace=False))
    assert d.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert d.containment_scope is gate.ContainmentScope.TOOL_CALL


def test_ambiguity_without_workspace_does_not_invent_restriction():
    d = decide(raw_path(canonical_target=None, deterministic=False))
    assert d.outcome is kernel.SecurityOutcome.ALLOW


def test_executor_identity_mismatch_is_admission_only():
    d = decide(gate.ExecutorAdmissionIdentityFact(False, True, True))
    assert d.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert d.containment_scope is gate.ContainmentScope.EXECUTOR_ADMISSION


def test_open_run_blocks_only_overlap_admission():
    d = decide(gate.SettlementFact(True, True))
    assert d.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert d.containment_scope is gate.ContainmentScope.OVERLAP_ADMISSION


def test_reserved_evidence_namespace_absent_is_not_violation():
    assert decide(gate.ReservedEvidenceNamespaceFact(False)).outcome is kernel.SecurityOutcome.ALLOW


def test_reserved_evidence_forgery_is_fragment_scoped():
    d = decide(gate.ReservedEvidenceNamespaceFact(True))
    assert d.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert d.containment_scope is gate.ContainmentScope.EVIDENCE_FRAGMENT


def test_no_generalized_security_health_fact_is_claimed():
    assert not hasattr(gate, "SecurityHealthFact")
    with pytest.raises(TypeError):
        decide(SimpleNamespace(healthy=False))


def test_approval_contract_requires_user_only_for_consequence():
    d = decide(gate.ApprovalFact(True, False))
    assert d.outcome is kernel.SecurityOutcome.REQUIRE_USER_DECISION
    assert d.containment_scope is gate.ContainmentScope.CONSEQUENCE


def test_lifecycle_mismatch_remains_unmapped():
    with pytest.raises(gate.UnmappedAuthorityFact):
        decide(gate.LifecycleAuthorityFact(False, True, True))


def test_conflicting_nonhard_outcomes_are_not_reordered():
    with pytest.raises(RuntimeError):
        decide(gate.ToolSchemaFact(False), gate.ApprovalFact(True, False))


def test_different_nonhard_scopes_are_not_broadened():
    with pytest.raises(RuntimeError):
        decide(gate.ToolSchemaFact(False), gate.ExecutorAdmissionIdentityFact(False, True, True))


def test_empty_gate_does_not_silently_allow():
    with pytest.raises(ValueError):
        gate.evaluate_consequence((), outcome_type=kernel.SecurityOutcome)
'''


TEST_PATH = r'''from __future__ import annotations

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
        raw_json=json.dumps({"version": 1, "workspace_root": workspace, "never_paths": [r"D:\Sensitive"]}),
        host_environment=HOST_ENV,
    )


@pytest.fixture
def installed_path_gate():
    original = path_policy.authorize_represented_path
    gate._install_represented_path_gate(gate._bound_evaluator(kernel.SecurityOutcome))
    try:
        yield
    finally:
        path_policy.authorize_represented_path = original


def test_path_policy_owns_single_raw_fact_producer():
    assert "inspect_represented_path(" in inspect.getsource(path_policy.authorize_represented_path)
    assert "path_policy.inspect_represented_path(" in inspect.getsource(gate._install_represented_path_gate)


def test_raw_facts_have_no_outcome():
    f = path_policy.inspect_represented_path(build(), r"D:\Sensitive\secret.txt")
    assert f.never_match is True
    assert not hasattr(f, "outcome")


def test_raw_workspace_membership_is_fact_not_disposition():
    f = path_policy.inspect_represented_path(build(), r"D:\Other\artifact.txt")
    assert f.inside_workspace is False
    assert f.deterministic is True


def test_raw_no_workspace_ambiguity_remains_nonviolation_fact():
    f = path_policy.inspect_represented_path(build(None), r"relative\target.txt")
    assert f.workspace_configured is False
    assert f.deterministic is False
    assert f.invalid is False


def test_legacy_phase4_never_mapping_is_preserved():
    assert path_policy.authorize_represented_path(build(), r"D:\Sensitive\secret.txt").outcome is path_policy.PathAuthorizationOutcome.HARD_INTERRUPT


def test_legacy_phase4_workspace_mapping_is_preserved():
    assert path_policy.authorize_represented_path(build(), r"D:\Other\artifact.txt").outcome is path_policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


def test_gate_preserves_never_mapping(installed_path_gate):
    assert path_policy.authorize_represented_path(build(), r"D:\Sensitive\secret.txt").outcome is path_policy.PathAuthorizationOutcome.HARD_INTERRUPT


def test_gate_preserves_workspace_denial(installed_path_gate):
    assert path_policy.authorize_represented_path(build(), r"D:\Other\artifact.txt").outcome is path_policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


def test_gate_preserves_inside_workspace_allow(installed_path_gate):
    assert path_policy.authorize_represented_path(build(), r"D:\Projects\Jack\src\engine.py").outcome is path_policy.PathAuthorizationOutcome.ALLOW


def test_gate_preserves_fail_soft_no_workspace_ambiguity(installed_path_gate):
    d = path_policy.authorize_represented_path(build(None), r"relative\target.txt")
    assert d.outcome is path_policy.PathAuthorizationOutcome.ALLOW
    assert d.canonical_target is None


def test_gate_preserves_workspace_relative_denial(installed_path_gate):
    d = path_policy.authorize_represented_path(build(), r"relative\target.txt")
    assert d.outcome is path_policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


def test_gate_preserves_executor_cwd_deferral(installed_path_gate):
    d = path_policy.authorize_represented_path(build(), r"relative\target.txt", defer_relative_without_executor=True)
    assert d.outcome is path_policy.PathAuthorizationOutcome.ALLOW
    assert "executor cwd admission" in d.reason
'''


TEST_RUNTIME = r'''from __future__ import annotations

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
    assert source.index("jack_consequence_gate.install(module)") < source.index("jack_responses_compat.register(module)")


def test_responses_compatibility_is_not_security_root():
    source = inspect.getsource(responses_compat.register)
    assert "jack_consequence_gate" not in source
    assert "Consequence Gate" not in source


def test_gate_does_not_reconstruct_kernel_identity():
    source = inspect.getsource(gate)
    assert "_active_kernel_module" not in source
    assert 'sys.modules["jack_kernel"]' not in source
    assert "import jack_kernel" not in source


def test_install_rejects_incompatible_outcome_vocabulary(monkeypatch):
    class OtherOutcome(str, Enum):
        ALLOW = "ALLOW"
        HARD_INTERRUPT = "HARD_INTERRUPT"
    fake = SimpleNamespace(SecurityOutcome=OtherOutcome)
    monkeypatch.setattr(gate, "_install_represented_path_gate", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="SecurityOutcome vocabulary"):
        gate.install(fake)


def test_isolated_equivalent_kernel_receives_its_own_enum(monkeypatch):
    class OtherOutcome(str, Enum):
        ALLOW = "ALLOW"
        DENY_AND_CONTINUE = "DENY_AND_CONTINUE"
        REQUIRE_USER_DECISION = "REQUIRE_USER_DECISION"
        HARD_INTERRUPT = "HARD_INTERRUPT"
    fake = SimpleNamespace(SecurityOutcome=OtherOutcome)
    monkeypatch.setattr(gate, "_install_represented_path_gate", lambda *a, **k: None)
    gate.install(fake)
    d = fake.evaluate_consequence((gate.StageToolAuthorityFact(False),))
    assert d.outcome is OtherOutcome.DENY_AND_CONTINUE
'''


FINAL_CI = '''name: CI\n\non:\n  push:\n    branches: [main]\n  pull_request:\n\npermissions:\n  contents: read\n\njobs:\n  windows-validated-baseline:\n    runs-on: windows-latest\n\n    steps:\n      - name: Check out repository\n        uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262\n\n      - name: Set up Python 3.14.6\n        uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065\n        with:\n          python-version: "3.14.6"\n\n      - name: Set up Node 24.16.0\n        uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020\n        with:\n          node-version: "24.16.0"\n\n      - name: Install validated Python test environment\n        shell: pwsh\n        run: |\n          python -m pip install pip==26.2.1\n          python -m pip install -r requirements-test.txt\n\n      - name: Report validated toolchain\n        shell: pwsh\n        run: |\n          python --version\n          python -m pip --version\n          node --version\n          python -c "import sys,fastapi,uvicorn,httpx,pytest,starlette,pydantic; expected={'python':'3.14.6','fastapi':'0.137.1','uvicorn':'0.49.0','httpx':'0.28.1','pytest':'9.1.1','starlette':'1.3.1','pydantic':'2.13.4'}; actual={'python':sys.version.split()[0],'fastapi':fastapi.__version__,'uvicorn':uvicorn.__version__,'httpx':httpx.__version__,'pytest':pytest.__version__,'starlette':starlette.__version__,'pydantic':pydantic.__version__}; print(actual); assert actual == expected, (actual, expected)"\n\n      - name: Compile runtime modules\n        shell: pwsh\n        run: |\n          python -m py_compile jack_kernel.py jack_secure_entrypoint.py jack_evidence_guard.py jack_path_policy.py jack_responses_compat.py jack_consequence_gate.py\n\n      - name: Report Pi bridge identities\n        shell: pwsh\n        run: |\n          python -c "from pathlib import Path; import hashlib; b=Path('Pi/pi-control-bridge.ts').read_bytes(); lf=b.replace(b'\\r\\n',b'\\n'); crlf=lf.replace(b'\\n',b'\\r\\n'); print('PI_BRIDGE_LF_SHA256='+hashlib.sha256(lf).hexdigest()); print('PI_BRIDGE_CRLF_SHA256='+hashlib.sha256(crlf).hexdigest())"\n\n      - name: Run Phase-5 targeted tests\n        shell: pwsh\n        run: python -m pytest -q tests/test_phase5_consequence_gate.py tests/test_phase5_path_gate_integration.py tests/test_phase5_runtime_integration.py tests/test_phase5_secure_entrypoint.py\n\n      - name: Run Python regression suite\n        shell: pwsh\n        run: python -m pytest -q\n\n      - name: Run Pi control bridge harnesses\n        shell: pwsh\n        run: |\n          node tests/pi_control_bridge_v2_harness.mjs\n          node tests/pi_control_bridge_cancel_ownership_harness.mjs\n          node tests/pi_control_bridge_deferred_dispatch_harness.mjs\n          node tests/pi_control_bridge_retry_recovery_harness.mjs\n          node tests/pi_control_bridge_multi_endpoint_harness.mjs\n          node tests/pi_provider_runtime_binding_harness.mjs\n          node tests/pi_phase4_executor_admission_harness.mjs\n'''


def write_small_files() -> None:
    (ROOT / "jack_consequence_gate.py").write_text(GATE, encoding="utf-8", newline="\n")
    (ROOT / "tests" / "test_phase5_consequence_gate.py").write_text(TEST_GATE, encoding="utf-8", newline="\n")
    (ROOT / "tests" / "test_phase5_path_gate_integration.py").write_text(TEST_PATH, encoding="utf-8", newline="\n")
    (ROOT / "tests" / "test_phase5_runtime_integration.py").write_text(TEST_RUNTIME, encoding="utf-8", newline="\n")
    old = ROOT / "jack_path_authority_facts.py"
    if old.exists():
        old.unlink()
    (ROOT / ".github" / "workflows" / "ci.yml").write_text(FINAL_CI, encoding="utf-8", newline="\n")


def main() -> None:
    patch_kernel()
    patch_responses()
    patch_path_policy()
    write_small_files()
    Path(__file__).unlink()


if __name__ == "__main__":
    main()
