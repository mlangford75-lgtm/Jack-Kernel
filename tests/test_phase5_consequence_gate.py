from __future__ import annotations

import pytest

import jack_consequence_gate as gate
import jack_kernel as kernel


def fact(
    kind: gate.ConsequenceFactKind,
    outcome: kernel.SecurityOutcome,
    reason: str = "",
) -> gate.ConsequenceFact:
    return gate.ConsequenceFact(
        kind=kind,
        outcome=outcome,
        reason=reason,
    )


def test_valid_action_is_allowed():
    decision = gate.evaluate_consequence((
        fact(gate.ConsequenceFactKind.STAGE_AUTHORITY, kernel.SecurityOutcome.ALLOW),
        fact(gate.ConsequenceFactKind.TOOL_AUTHORITY, kernel.SecurityOutcome.ALLOW),
        fact(gate.ConsequenceFactKind.PATH_POLICY, kernel.SecurityOutcome.ALLOW),
    ))
    assert decision.outcome is kernel.SecurityOutcome.ALLOW
    assert decision.decisive_fact is None


def test_bad_tool_schema_preserves_existing_recoverable_denial():
    decision = gate.evaluate_consequence((
        fact(
            gate.ConsequenceFactKind.TOOL_SCHEMA,
            kernel.SecurityOutcome.DENY_AND_CONTINUE,
        ),
    ))
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE


def test_wrong_stage_preserves_existing_recoverable_denial():
    decision = gate.evaluate_consequence((
        fact(
            gate.ConsequenceFactKind.STAGE_AUTHORITY,
            kernel.SecurityOutcome.DENY_AND_CONTINUE,
        ),
    ))
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE


@pytest.mark.parametrize(
    "kind",
    [
        gate.ConsequenceFactKind.TASK_AUTHORITY,
        gate.ConsequenceFactKind.RUN_AUTHORITY,
        gate.ConsequenceFactKind.RUN_EPOCH_AUTHORITY,
    ],
)
@pytest.mark.parametrize(
    "producer_outcome",
    [
        kernel.SecurityOutcome.DENY_AND_CONTINUE,
        kernel.SecurityOutcome.REQUIRE_USER_DECISION,
        kernel.SecurityOutcome.HARD_INTERRUPT,
    ],
)
def test_lifecycle_mismatch_cannot_be_silently_promoted_to_allow(
    kind: gate.ConsequenceFactKind,
    producer_outcome: kernel.SecurityOutcome,
):
    """Phase 5 must preserve lifecycle-producer severity, not invent it.

    Current orchestration/lifecycle code does not expose task/run/epoch mismatch
    as SecurityOutcome yet. This test therefore verifies composition only: once
    the owning producer supplies a non-ALLOW disposition, unrelated ALLOW facts
    cannot erase it.
    """
    decision = gate.evaluate_consequence((
        fact(kind, producer_outcome),
        fact(gate.ConsequenceFactKind.TOOL_AUTHORITY, kernel.SecurityOutcome.ALLOW),
    ))
    assert decision.outcome is producer_outcome
    assert decision.decisive_fact is not None
    assert decision.decisive_fact.kind is kind


def test_valid_evidence_survives_centralization():
    decision = gate.evaluate_consequence((
        fact(
            gate.ConsequenceFactKind.EVIDENCE_PROVENANCE,
            kernel.SecurityOutcome.ALLOW,
        ),
    ))
    assert decision.outcome is kernel.SecurityOutcome.ALLOW


@pytest.mark.parametrize(
    "producer_outcome",
    [
        kernel.SecurityOutcome.DENY_AND_CONTINUE,
        kernel.SecurityOutcome.HARD_INTERRUPT,
    ],
)
def test_invalid_evidence_preserves_producer_severity(
    producer_outcome: kernel.SecurityOutcome,
):
    """The gate does not reclassify evidence authority on its own."""
    decision = gate.evaluate_consequence((
        fact(gate.ConsequenceFactKind.EVIDENCE_PROVENANCE, producer_outcome),
    ))
    assert decision.outcome is producer_outcome


def test_approval_required_is_distinct_from_security_failure():
    decision = gate.evaluate_consequence((
        fact(
            gate.ConsequenceFactKind.APPROVAL_STATE,
            kernel.SecurityOutcome.REQUIRE_USER_DECISION,
        ),
    ))
    assert decision.outcome is kernel.SecurityOutcome.REQUIRE_USER_DECISION


def test_workspace_denial_preserves_phase4_narrow_containment():
    decision = gate.evaluate_consequence((
        fact(
            gate.ConsequenceFactKind.WORKSPACE_POLICY,
            kernel.SecurityOutcome.DENY_AND_CONTINUE,
        ),
    ))
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE


def test_never_path_hard_interrupt_cannot_be_masked_by_recoverable_fact():
    decision = gate.evaluate_consequence((
        fact(
            gate.ConsequenceFactKind.TOOL_SCHEMA,
            kernel.SecurityOutcome.DENY_AND_CONTINUE,
        ),
        fact(
            gate.ConsequenceFactKind.PATH_POLICY,
            kernel.SecurityOutcome.HARD_INTERRUPT,
        ),
    ))
    assert decision.outcome is kernel.SecurityOutcome.HARD_INTERRUPT
    assert decision.decisive_fact is not None
    assert decision.decisive_fact.kind is gate.ConsequenceFactKind.PATH_POLICY


def test_conflicting_non_hard_dispositions_are_not_silently_reordered():
    with pytest.raises(RuntimeError, match="conflicting authoritative non-hard"):
        gate.evaluate_consequence((
            fact(
                gate.ConsequenceFactKind.TOOL_SCHEMA,
                kernel.SecurityOutcome.DENY_AND_CONTINUE,
            ),
            fact(
                gate.ConsequenceFactKind.APPROVAL_STATE,
                kernel.SecurityOutcome.REQUIRE_USER_DECISION,
            ),
        ))


def test_matching_non_hard_dispositions_compose_without_escalation():
    decision = gate.evaluate_consequence((
        fact(
            gate.ConsequenceFactKind.STAGE_AUTHORITY,
            kernel.SecurityOutcome.DENY_AND_CONTINUE,
        ),
        fact(
            gate.ConsequenceFactKind.TOOL_SCHEMA,
            kernel.SecurityOutcome.DENY_AND_CONTINUE,
        ),
    ))
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE


def test_observability_telemetry_is_not_an_accepted_fact_domain():
    with pytest.raises(ValueError):
        gate.ConsequenceFactKind("telemetry")


def test_empty_gate_does_not_silently_authorize_without_facts():
    with pytest.raises(ValueError, match="at least one authority fact"):
        gate.evaluate_consequence(())


def _fake_kernel_namespace():
    class FakeInterrupt(RuntimeError):
        pass

    class FakeKernel:
        SecurityOutcome = kernel.SecurityOutcome
        Phase4RestrictedPathInterrupt = FakeInterrupt

        @staticmethod
        def _tool_call_validation_errors(calls, tools):
            return ["schema denied"] if calls == "bad" else []

        @staticmethod
        def _phase4_partition_structured_tool_calls(calls):
            if calls == "hard":
                raise FakeInterrupt("never path")
            if calls == "deny":
                return [], ["workspace denied"]
            return list(calls), []

        @staticmethod
        def _phase4_executor_admission_decision(payload):
            return {"outcome": payload}

        @staticmethod
        def _register_runtime_manifest_components(components):
            FakeKernel.registered_manifest_components = dict(components)

    return FakeKernel


def test_installer_is_idempotent_and_exposes_shared_gate():
    fake = _fake_kernel_namespace()
    gate.install(fake)
    first_validation = fake._tool_call_validation_errors
    first_partition = fake._phase4_partition_structured_tool_calls

    gate.install(fake)

    assert fake._tool_call_validation_errors is first_validation
    assert fake._phase4_partition_structured_tool_calls is first_partition
    assert fake.evaluate_consequence is gate.evaluate_consequence
    assert fake.ConsequenceFactKind is gate.ConsequenceFactKind
    assert fake.ConsequenceFact is gate.ConsequenceFact
    assert "jack_consequence_gate.py" in fake.registered_manifest_components


def test_installed_wrappers_preserve_existing_results_and_hard_interrupt():
    fake = _fake_kernel_namespace()
    gate.install(fake)

    assert fake._tool_call_validation_errors("bad", None) == ["schema denied"]
    assert fake._tool_call_validation_errors("good", None) == []
    assert fake._phase4_partition_structured_tool_calls("deny") == (
        [],
        ["workspace denied"],
    )
    assert fake._phase4_partition_structured_tool_calls(["safe"]) == (
        ["safe"],
        [],
    )
    with pytest.raises(fake.Phase4RestrictedPathInterrupt):
        fake._phase4_partition_structured_tool_calls("hard")
    assert fake._phase4_executor_admission_decision("ALLOW") == {
        "outcome": "ALLOW"
    }
    assert fake._phase4_executor_admission_decision("DENY_AND_CONTINUE") == {
        "outcome": "DENY_AND_CONTINUE"
    }
