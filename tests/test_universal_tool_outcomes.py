"""Universal tool-outcome contract and TAS failure propagation regression."""
import asyncio

from jack_tool_outcomes import reported_tool_outcome, FAILED, SUCCESS, UNKNOWN
from jack_deep_reasoning_orchestrator import (
    DeepReasoningOrchestrator, PendingToolRequest, CompletedAnswer,
)


PROMPTS = {
    "ULTRA_STAGE1_THESIS_PROMPT": "Thesis",
    "ULTRA_STAGE2_ANTITHESIS_PROMPT": "Antithesis",
    "ULTRA_STAGE3_SYNTHESIS_PROMPT": "Synthesis",
}
TOOLS = [{"type": "function", "function": {"name": "python_repl", "parameters": {"type": "object"}}}]


def test_universal_structured_outcomes():
    assert reported_tool_outcome({"is_error": True, "content": "bad"}) == FAILED
    assert reported_tool_outcome({"isError": True}) == FAILED
    assert reported_tool_outcome({"success": False}) == FAILED
    assert reported_tool_outcome({"status": "failed"}) == FAILED
    assert reported_tool_outcome({"error": {"message": "bad"}}) == FAILED
    assert reported_tool_outcome({"details": {"exitCode": 2}}) == FAILED
    assert reported_tool_outcome({"success": True}) == SUCCESS
    assert reported_tool_outcome({"details": {"exitCode": 0}}) == SUCCESS
    assert reported_tool_outcome({"content": "ERROR in user-facing documentation"}) == UNKNOWN
    assert reported_tool_outcome({"content": "all done"}) == UNKNOWN
    assert reported_tool_outcome({}) == UNKNOWN
    assert reported_tool_outcome({"success": True, "is_error": True}) == FAILED


def test_tas_failed_tool_is_not_verified_and_reaches_synthesis():
    replies = [
        {"content": "THESIS"},
        {"tool_calls": [{"id": "c1", "type": "function", "function": {"name": "python_repl", "arguments": "{}"}}]},
        {"content": "NO CONFIRMED DEFECTS"},
        {"content": "FINAL"},
    ]
    observed = []

    async def backend(**kwargs):
        observed.append(kwargs)
        return replies.pop(0)

    engine = DeepReasoningOrchestrator(backend, prompts=PROMPTS, tools=TOOLS)
    pending = asyncio.run(engine.start(request="Evaluate percentages", require_verification=True))
    assert isinstance(pending, PendingToolRequest)
    final = asyncio.run(engine.resume(pending, results=[{
        "tool_call_id": "c1",
        "content": "VERIFICATION_ERROR: Only numeric values are permitted",
        "tool_outcome": FAILED,
    }]))
    assert isinstance(final, CompletedAnswer)
    assert pending.session.first_verification_completed is False
    assert final.evidence[0]["tool_outcome"] == FAILED
    assert final.evidence[0]["execution_succeeded"] is False
    assert final.evidence[0]["methodology_verified"] is False
    assert "reported TOOL FAILURE" in str(observed[2]["messages"])
    assert "VERIFICATION_ERROR" in str(observed[2]["messages"])
    assert '"tool_outcome": "FAILED"' in str(observed[-1]["messages"])
    assert "reported TOOL FAILURE" not in final.answer


def test_tas_success_and_unknown_remain_distinct():
    for status in (SUCCESS, UNKNOWN):
        replies = [
            {"content": "THESIS"},
            {"tool_calls": [{"id": "c2", "type": "function", "function": {"name": "python_repl", "arguments": "{}"}}]},
            {"content": "CRITIQUE"},
            {"content": "FINAL"},
        ]

        async def backend(**kwargs):
            return replies.pop(0)

        engine = DeepReasoningOrchestrator(backend, prompts=PROMPTS, tools=TOOLS)
        pending = asyncio.run(engine.start(request="Compute the rate"))
        completed = asyncio.run(engine.resume(pending, results=[{
            "tool_call_id": "c2", "content": "0.1", "tool_outcome": status,
        }]))
        assert completed.evidence[0]["tool_outcome"] == status
        assert completed.evidence[0]["execution_succeeded"] is (status == SUCCESS)
        assert pending.session.first_verification_completed is (status == SUCCESS)


def test_shared_resume_preserves_legacy_shape_and_marks_reported_failures():
    import time
    import jack_kernel as kernel

    async def exercise(call_id, raw):
        state = kernel.PendingToolResume(
            resume_id="test-tool-outcome-" + call_id,
            stage_key="thesis",
            history=[{"role": "user", "content": "test"}],
            secondary_system="",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            tools=None, tool_choice=None,
            expected_tool_call_ids=[call_id],
            created_at=time.time(),
            debugging_run_id=None,
        )
        kernel.KERNEL._pending_tool_resumes[call_id] = state
        try:
            selected = await kernel.KERNEL._consume_pending_tool_resume([
                {"role": "tool", "tool_call_id": call_id, "content": "actual output", **raw}
            ])
            assert selected is not None
            return selected[1][0]
        finally:
            await kernel.KERNEL._retire_pending_tool_resume(state)

    legacy = asyncio.run(exercise("outcome-legacy", {}))
    assert legacy == {
        "role": "tool", "tool_call_id": "outcome-legacy",
        "content": "actual output", "_jack_internal_tool_exchange": True,
    }
    failed = asyncio.run(exercise("outcome-failed", {"is_error": True}))
    assert failed["_jack_tool_outcome"] == FAILED
    assert failed["_jack_internal_tool_failed"] is True
    assert failed["_jack_failure_carry_hops"] == 1
    assert failed["content"] == "actual output"


def test_pi_forwards_only_failures_to_jack_without_parsing_error_text():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "Pi" / "jack-kernel.ts").read_text(encoding="utf-8")
    assert 'pi.on("tool_execution_end"' in source
    assert 'pi.on("before_provider_request"' in source
    assert 'event?.isError === true' in source
    assert 'String(ctx?.model?.provider || "") !== PROVIDER_NAME' in source
    assert "failedToolCalls.get(id) !== sessionId" in source
    assert 'return { ...message, is_error: true }' in source
