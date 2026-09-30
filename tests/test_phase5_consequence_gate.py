from __future__ import annotations

from types import SimpleNamespace

import pytest

import jack_consequence_gate as gate
import jack_kernel as kernel


def test_allow_has_no_containment_scope():
    decision = gate.evaluate_consequence((
        gate.StageToolAuthorityFact(authorized=True),
        gate.ToolSchemaFact(valid=True),
    ))
    assert decision.outcome is kernel.SecurityOutcome.ALLOW
    assert decision.containment_scope is gate.ContainmentScope.NONE
    assert decision.decisive_fact is None


def test_stage_tool_denial_is_call_scoped():
    decision = gate.evaluate_consequence((
        gate.StageToolAuthorityFact(authorized=False),
    ))
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert decision.containment_scope is gate.ContainmentScope.TOOL_CALL


def test_bad_schema_is_recoverable_and_call_scoped():
    decision = gate.evaluate_consequence((
        gate.ToolSchemaFact(valid=False, errors=("missing required field",)),
    ))
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert decision.containment_scope is gate.ContainmentScope.TOOL_CALL


def test_workspace_outside_is_call_scoped_denial():
    decision = gate.evaluate_consequence((
        gate.PathPolicyFact(
            never_match=False,
            workspace_configured=True,
            deterministic=True,
            inside_workspace=False,
        ),
    ))
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert decision.containment_scope is gate.ContainmentScope.TOOL_CALL


def test_workspace_ambiguity_is_not_hard_interrupt():
    decision = gate.evaluate_consequence((
        gate.PathPolicyFact(
            workspace_configured=True,
            deterministic=False,
            inside_workspace=None,
        ),
    ))
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert decision.containment_scope is gate.ContainmentScope.TOOL_CALL


def test_ambiguity_without_workspace_does_not_invent_restriction():
    decision = gate.evaluate_consequence((
        gate.PathPolicyFact(
            workspace_configured=False,
            deterministic=False,
            inside_workspace=None,
        ),
    ))
    assert decision.outcome is kernel.SecurityOutcome.ALLOW


def test_never_match_keeps_existing_hard_batch_boundary():
    decision = gate.evaluate_consequence((
        gate.PathPolicyFact(
            never_match=True,
            workspace_configured=True,
            deterministic=True,
            inside_workspace=False,
        ),
    ))
    assert decision.outcome is kernel.SecurityOutcome.HARD_INTERRUPT
    assert decision.containment_scope is gate.ContainmentScope.TOOL_BATCH


def test_executor_identity_mismatch_is_admission_scoped():
    decision = gate.evaluate_consequence((
        gate.ExecutorAdmissionIdentityFact(
            runtime_matches=False,
            lane_matches=True,
            call_matches=True,
        ),
    ))
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert decision.containment_scope is gate.ContainmentScope.EXECUTOR_ADMISSION


def test_open_run_blocks_only_overlap_admission():
    decision = gate.evaluate_consequence((
        gate.SettlementFact(
            run_open=True,
            overlapping_admission_requested=True,
        ),
    ))
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert decision.containment_scope is gate.ContainmentScope.OVERLAP_ADMISSION


def test_unknown_evidence_alone_is_allowed():
    decision = gate.evaluate_consequence((
        gate.EvidenceProvenanceFact(
            origin_known=False,
            forged_reserved_namespace=False,
        ),
    ))
    assert decision.outcome is kernel.SecurityOutcome.ALLOW


def test_reserved_evidence_forgery_is_fragment_scoped():
    decision = gate.evaluate_consequence((
        gate.EvidenceProvenanceFact(
            origin_known=False,
            forged_reserved_namespace=True,
        ),
    ))
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE
    assert decision.containment_scope is gate.ContainmentScope.EVIDENCE_FRAGMENT


def test_approval_contract_holds_only_that_consequence():
    decision = gate.evaluate_consequence((
        gate.ApprovalFact(
            approval_required=True,
            approval_valid=False,
        ),
    ))
    assert decision.outcome is kernel.SecurityOutcome.REQUIRE_USER_DECISION
    assert decision.containment_scope is gate.ContainmentScope.CONSEQUENCE


def test_lifecycle_mismatch_refuses_unjustified_mapping():
    with pytest.raises(gate.UnmappedAuthorityFact):
        gate.evaluate_consequence((
            gate.LifecycleAuthorityFact(
                task_matches=False,
                run_matches=True,
                run_epoch_matches=True,
            ),
        ))


def test_conflicting_nonhard_outcomes_are_not_reordered():
    with pytest.raises(RuntimeError):
        gate.evaluate_consequence((
            gate.ToolSchemaFact(valid=False, errors=("invalid",)),
            gate.ApprovalFact(approval_required=True, approval_valid=False),
        ))


def test_different_nonhard_scopes_are_not_broadened():
    with pytest.raises(RuntimeError):
        gate.evaluate_consequence((
            gate.ToolSchemaFact(valid=False, errors=("invalid",)),
            gate.ExecutorAdmissionIdentityFact(
                runtime_matches=False,
                lane_matches=True,
                call_matches=True,
            ),
        ))


def test_observability_object_is_not_gate_authority():
    with pytest.raises(TypeError):
        gate.evaluate_consequence((SimpleNamespace(healthy=False),))


def test_empty_gate_does_not_silently_allow():
    with pytest.raises(ValueError):
        gate.evaluate_consequence(())
