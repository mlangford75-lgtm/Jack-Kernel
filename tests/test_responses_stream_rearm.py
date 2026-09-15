from __future__ import annotations

import asyncio
import importlib.util
import json
import time
from pathlib import Path

import jack_kernel as kernel

MODULE = Path(__file__).resolve().parents[1] / "jack_responses_compat.py"
spec = importlib.util.spec_from_file_location("jack_responses_compat_rearm_test", MODULE)
compat = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(compat)


def test_responses_stream_failure_rearms_real_pending_tool_resume_and_allows_retry(monkeypatch):
    call_id = "call-responses-rearm"
    messages = [{"role": "tool", "tool_call_id": call_id, "content": "result"}]
    state = kernel.PendingToolResume(
        resume_id="jack-resume-responses-rearm",
        stage_key="thesis",
        history=[{"role": "user", "content": "test"}],
        secondary_system="",
        usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        tools=None,
        tool_choice=None,
        expected_tool_call_ids=[call_id],
        created_at=time.time(),
        debugging_run_id=None,
    )
    state.in_flight = True
    kernel.KERNEL._pending_tool_resumes[call_id] = state

    async def failing_stream(_body):
        if False:
            yield b""
        raise RuntimeError("injected stream failure")

    monkeypatch.setattr(kernel.KERNEL, "stream", failing_stream)

    class JK:
        CFG = kernel.CFG
        KERNEL = kernel.KERNEL

    chat = {"messages": messages, "stream": True}

    async def exercise():
        events = []
        try:
            async for chunk in compat._stream(JK, chat, {}):
                data = next(
                    line[6:]
                    for line in chunk.decode().splitlines()
                    if line.startswith("data: ")
                )
                events.append(json.loads(data))

            assert events[-1]["type"] == "response.failed"
            assert events[-1]["error"]["code"] == "jack_responses_stream_error"
            assert state.in_flight is False

            resumed = await kernel.KERNEL._consume_pending_tool_resume(messages)
            assert resumed is not None
            resumed_state, resumed_messages = resumed
            assert resumed_state is state
            assert state.in_flight is True
            assert resumed_messages == [
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": "result",
                    "_jack_internal_tool_exchange": True,
                }
            ]
        finally:
            await kernel.KERNEL._retire_pending_tool_resume(state)

    asyncio.run(exercise())
    assert call_id not in kernel.KERNEL._pending_tool_resumes
