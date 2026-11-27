"""CL-2: actual serialized buffered/streamed requests share one contract."""
import asyncio
import copy

import pytest

from test_agentic_coder_planner_executor import load, response, spec_text
from test_audit_cache_cost_evidence import mock_backend


@pytest.mark.parametrize("mode,planner,stage", [
    ("flash", "flash", "extended_initial"),
    ("balanced", "flash", "extended_initial"),
    ("thorough", "thorough", "extended_initial"),
    ("coder", "flash", "coder_planner"),
    ("coder", "thorough", "coder_planner"),
    ("coder", "flash", "extended_initial"),
    ("coder", "thorough", "extended_initial"),
    ("balanced", "flash", "extended_reflection"),
    ("thorough", "thorough", "extended_reflection"),
])
def test_buffered_and_streamed_wire_equivalence(monkeypatch, tmp_path, mode, planner, stage):
    monkeypatch.setenv("JACK_SEED", "314159")
    monkeypatch.setenv("JACK_CACHE_PREFIX_BYTE_DIAGNOSTICS", "1")
    monkeypatch.setenv("JACK_AGENTIC_CONTEXT_ACCOUNTING", "1")
    k = load(monkeypatch, tmp_path, profile=mode, planner=planner)
    history = [{"role": "user", "content": "Examine the example."}]
    k._agentic_begin_turn(history, fresh=True)
    if mode == "coder" and stage == "extended_initial":
        k._coder_append_plan(history, response(spec_text("example")))
    if stage == "extended_reflection":
        k.append_extended_candidate_response(history, {
            "role": "assistant", "content": "Frozen answer.",
            "reasoning_content": "Preserve the established result.",
        })
        k._agentic_forensic_start_stage2(history)
    original = copy.deepcopy(history)
    tools = [
        {"type": "function", "function": {"name": "inspect_example",
            "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {"name": "other_example",
            "parameters": {"type": "object", "properties": {}}}},
    ]
    choice = {"type": "function", "function": {"name": "inspect_example"}}
    received = []

    async def run():
        for streamed in (False, True):
            backend = await mock_backend(k, received)
            try:
                kwargs = dict(messages=history, secondary_system="Caller contract.",
                              profile=k.STAGES[stage], tools=tools, tool_choice=choice)
                if streamed:
                    async for _ in backend.chat_stream(**kwargs):
                        pass
                else:
                    await backend.chat(**kwargs)
            finally:
                await backend._client.aclose()
            assert history == original

    asyncio.run(run())
    assert len(received) == 2
    buffered, streamed = received
    assert buffered.pop("stream") is False
    assert streamed.pop("stream") is True
    assert "stream_options" not in buffered
    assert streamed.pop("stream_options") == {"include_usage": True}
    assert buffered == streamed
    assert list(buffered) == list(streamed)
    if k.STAGES[stage].allow_tools:
        assert buffered["tools"] == tools[:1]
        assert buffered["tool_choice"] == "required"
    else:
        assert "tools" not in buffered and "tool_choice" not in buffered
    if stage == "extended_reflection":
        assert buffered["seed"] == 314161
        assert "Frozen answer." not in str(buffered["messages"])
        assert "Caller contract." not in str(buffered["messages"])
        assert "Preserve the established result." in str(buffered["messages"])
    if stage == "coder_planner":
        assert buffered["messages"][0]["role"] == "system"
        assert "You are Architect" in buffered["messages"][0]["content"]
