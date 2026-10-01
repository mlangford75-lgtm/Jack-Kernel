from __future__ import annotations

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
    d = decide(gate.ExecutorAdmissionIdentityFact(False, True))
    assert d.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert d.containment_scope is gate.ContainmentScope.EXECUTOR_ADMISSION


def test_open_run_blocks_only_overlap_admission():
    d = decide(gate.SettlementFact(True, True))
    assert d.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert d.containment_scope is gate.ContainmentScope.OVERLAP_ADMISSION


def test_valid_nonforged_jack_evidence_namespace_allows():
    assert decide(gate.ReservedEvidenceNamespaceFact(False)).outcome is kernel.SecurityOutcome.ALLOW


def test_forged_jack_reserved_evidence_namespace_is_fragment_scoped_denial():
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


def test_stale_task_authority_is_not_silently_mapped():
    with pytest.raises(gate.UnmappedAuthorityFact):
        decide(gate.LifecycleAuthorityFact(False, True, True))


def test_wrong_run_authority_is_not_silently_mapped():
    with pytest.raises(gate.UnmappedAuthorityFact):
        decide(gate.LifecycleAuthorityFact(True, False, True))


def test_wrong_run_epoch_authority_is_not_silently_mapped():
    with pytest.raises(gate.UnmappedAuthorityFact):
        decide(gate.LifecycleAuthorityFact(True, True, False))


def test_conflicting_nonhard_outcomes_are_not_reordered():
    with pytest.raises(RuntimeError):
        decide(gate.ToolSchemaFact(False), gate.ApprovalFact(True, False))


def test_different_nonhard_scopes_are_not_broadened():
    with pytest.raises(RuntimeError):
        decide(gate.ToolSchemaFact(False), gate.ExecutorAdmissionIdentityFact(False, True))


def test_empty_gate_does_not_silently_allow():
    with pytest.raises(ValueError):
        gate.evaluate_consequence((), outcome_type=kernel.SecurityOutcome)
