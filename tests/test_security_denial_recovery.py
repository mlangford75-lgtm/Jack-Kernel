from jack_tool_recovery import ToolRecoveryState, POLICY_REPEAT_LIMIT, HARD_ATTEMPTS


def test_policy_denial_stops_identical_proposals_without_generic_retry_advice():
    tracker = ToolRecoveryState()
    tracker.progress("read:authorized", call_id="good")
    for index in range(POLICY_REPEAT_LIMIT):
        tracker.fail("read:restricted", "host policy denied", policy_denial=True,
                     policy_key="same-full-proposal")
        assert "Do not retry" in tracker.advice()
        assert tracker.exhausted is (index == POLICY_REPEAT_LIMIT - 1)
    assert "Repeated immutable security denial" in tracker.host_report()
    assert "read:authorized" in tracker.host_report()
    assert "without suggesting bypass" in tracker.handoff_instruction()


def test_different_proposals_and_real_progress_do_not_trigger_same_denial_limit():
    tracker = ToolRecoveryState()
    for index in range(5):
        tracker.fail("read:restricted", "denied", policy_denial=True, policy_key=str(index))
        assert not tracker.exhausted
    tracker.progress("read:authorized")
    assert tracker.consecutive_policy_denials == 0
    assert tracker.consecutive_failures == 0
    for index in range(HARD_ATTEMPTS):
        tracker.fail("ordinary", "correctable error")
    assert tracker.exhausted
    assert "hard ceiling" in tracker.host_report()
