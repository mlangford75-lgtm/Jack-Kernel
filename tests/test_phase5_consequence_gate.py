from __future__ import annotations

import pytest

import jack_consequence_gate as gate
import jack_kernel as kernel


def fact(
    producer: str,
    outcome: kernel.SecurityOutcome,
    reason: str = "",
) -> gate.ConsequenceFact:
    return gate.ConsequenceFact(
        producer=producer,
        outcome=outcome,
        reason=reason,
    )


def test_valid_action_is_allowed():
    decision = gate.evaluate_consequence((
        fact("stage_authority", kernel.SecurityOutcome.ALLOW),
        fact("tool_authority", kernel.SecurityOutcome.ALLOW),
        fact("path_policy", kernel.SecurityOutcome.ALLOW),
    ))
    assert decision.outcome is kernel.SecurityOutcome.ALLOW
    assert decision.decisive_fact is None


def test_bad_tool_schema_preserves_existing_recoverable_denial():
    decision = gate.evaluate_consequence((
        fact("tool_schema", kernel.SecurityOutcome.DENY_AND_CONTINUE),
    ))
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE


def test_wrong_stage_preserves_existing_recoverable_denial():
    decision = gate.evaluate_consequence((
        fact("stage_authority", kernel.SecurityOutcome.DENY_AND_CONTINUE),
    ))
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE


@pytest.mark.parametrize("producer", ["task_id", "run_id", "run_epoch"])
@pytest.mark.parametrize(
    "producer_outcome",
    [
        kernel.SecurityOutcome.DENY_AND_CONTINUE,
        kernel.SecurityOutcome.REQUIRE_USER_DECISION,
        kernel.SecurityOutcome.HARD_INTERRUPT,
    ],
)
def test_lifecycle_mismatch_cannot_be_silently_promoted_to_allow(
    producer: str,
    producer_outcome: kernel.SecurityOutcome,
):
    """Phase 5 must preserve lifecycle-producer severity, not invent it.

    Current orchestration/lifecycle code does not expose task/run/epoch mismatch
    as SecurityOutcome yet. This test therefore verifies composition only: once
    the owning producer supplies a non-ALLOW disposition, unrelated ALLOW facts
    cannot erase it.
    """
    decision = gate.evaluate_consequence((
        fact(producer, producer_outcome),
        fact("tool_authority", kernel.SecurityOutcome.ALLOW),
    ))
    assert decision.outcome is producer_outcome
    assert decision.decisive_fact is not None
    assert decision.decisive_fact.producer == producer


def test_valid_evidence_survives_centralization():
    decision = gate.evaluate_consequence((
        fact("evidence_provenance", kernel.SecurityOutcome.ALLOW),
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
        fact("evidence_provenance", producer_outcome),
    ))
    assert decision.outcome is producer_outcome


def test_approval_required_is_distinct_from_security_failure():
    decision = gate.evaluate_consequence((
        fact("approval_state", kernel.SecurityOutcome.REQUIRE_USER_DECISION),
    ))
    assert decision.outcome is kernel.SecurityOutcome.REQUIRE_USER_DECISION


def test_workspace_denial_preserves_phase4_narrow_containment():
    decision = gate.evaluate_consequence((
        fact("workspace_policy", kernel.SecurityOutcome.DENY_AND_CONTINUE),
    ))
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE


def test_never_path_hard_interrupt_cannot_be_masked_by_recoverable_fact():
    decision = gate.evaluate_consequence((
        fact("tool_schema", kernel.SecurityOutcome.DENY_AND_CONTINUE),
        fact("path_policy", kernel.SecurityOutcome.HARD_INTERRUPT),
    ))
    assert decision.outcome is kernel.SecurityOutcome.HARD_INTERRUPT
    assert decision.decisive_fact is not None
    assert decision.decisive_fact.producer == "path_policy"


def test_conflicting_non_hard_dispositions_are_not_silently_reordered():
    with pytest.raises(RuntimeError, match="conflicting authoritative non-hard"):
        gate.evaluate_consequence((
            fact("tool_schema", kernel.SecurityOutcome.DENY_AND_CONTINUE),
            fact("approval_state", kernel.SecurityOutcome.REQUIRE_USER_DECISION),
        ))


def test_matching_non_hard_dispositions_compose_without_escalation():
    decision = gate.evaluate_consequence((
        fact("stage_authority", kernel.SecurityOutcome.DENY_AND_CONTINUE),
        fact("tool_schema", kernel.SecurityOutcome.DENY_AND_CONTINUE),
    ))
    assert decision.outcome is kernel.SecurityOutcome.DENY_AND_CONTINUE


def test_non_authoritative_telemetry_cannot_drive_disposition():
    with pytest.raises(ValueError, match="Non-authoritative"):
        gate.evaluate_consequence((
            gate.ConsequenceFact(
                producer="telemetry",
                outcome=kernel.SecurityOutcome.HARD_INTERRUPT,
                authoritative=False,
            ),
        ))


def test_empty_gate_does_not_silently_authorize_without_facts():
    with pytest.raises(ValueError, match="at least one authoritative fact"):
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
