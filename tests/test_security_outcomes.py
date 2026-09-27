from __future__ import annotations

import jack_kernel as kernel


def test_security_outcome_vocabulary_is_exact():
    assert tuple(member.value for member in kernel.SecurityOutcome) == (
        "ALLOW",
        "DENY_AND_CONTINUE",
        "REQUIRE_USER_DECISION",
        "HARD_INTERRUPT",
    )


def test_only_hard_interrupt_is_classified_as_hard():
    assert kernel.is_hard_security_outcome(kernel.SecurityOutcome.HARD_INTERRUPT)

    assert not kernel.is_hard_security_outcome(kernel.SecurityOutcome.ALLOW)
    assert not kernel.is_hard_security_outcome(
        kernel.SecurityOutcome.DENY_AND_CONTINUE
    )
    assert not kernel.is_hard_security_outcome(
        kernel.SecurityOutcome.REQUIRE_USER_DECISION
    )


def test_non_hard_outcomes_are_explicit_and_immutable():
    assert isinstance(kernel.NON_HARD_SECURITY_OUTCOMES, frozenset)

    assert kernel.NON_HARD_SECURITY_OUTCOMES == frozenset(
        {
            kernel.SecurityOutcome.ALLOW,
            kernel.SecurityOutcome.DENY_AND_CONTINUE,
            kernel.SecurityOutcome.REQUIRE_USER_DECISION,
        }
    )

    assert (
        kernel.SecurityOutcome.HARD_INTERRUPT
        not in kernel.NON_HARD_SECURITY_OUTCOMES
    )


def test_phase_one_does_not_attach_enforcement_side_effects():
    # Phase 1 defines decision vocabulary only. No outcome object performs
    # cancellation, teardown, mutation, or cognition disposal by itself.
    for outcome in kernel.SecurityOutcome:
        assert not callable(outcome)
