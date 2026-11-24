"""Deterministic checks for the Planner -> Coder delegated assignment.

Do not judge model sampling. Verify the exact model-facing task, role authority,
cache-stable prefix, multimodal fidelity, and tool-free delegation.
"""
import asyncio
import json
import uuid

import httpx
import pytest

from test_agentic_coder_planner_executor import load


@pytest.mark.parametrize("planner", ("flash", "thorough"))
@pytest.mark.parametrize("task", (
    "I need an SVG of a nice cuckoo clock",
    "C:\\Users\\default.DESKTOP-M8143Q1\\Desktop\\clock\\Agentic_Testing is the workspace. Verify it is empty.",
    "Make the clock luxurious. Use black, gold and diamonds.",
    "Investigate the failed read-only tool call and complete the work.",
))
def test_planner_receives_original_task_with_separate_planning_system_contract(monkeypatch, tmp_path, planner, task):
    k = load(monkeypatch, tmp_path, planner=planner)
    history = [{"role": "user", "content": task}]
    saved = json.dumps(history, sort_keys=True)
    wire = k._coder_isolate_planner_request(history, k.STAGES["coder_planner"], source_history=history)
    assert [m["role"] for m in wire] == ["system", "user"]
    assert wire[0]["content"] == k.STAGES["coder_planner"].prompt
    assert "architectural specification" in wire[0]["content"]
    assert "You have no tools and no execution authority" in wire[0]["content"]
    assert wire[1]["content"].startswith(k._CODER_ARCHITECT_TASK_SOURCE_HEADER)
    assert task in wire[1]["content"]
    assert wire[1]["content"].count(task) == 1
    assert wire[1]["content"].endswith(k._CODER_ARCHITECT_TASK_SOURCE_FOOTER)
    assert "Never provide the final answer" in wire[0]["content"]
    assert wire[0]["content"] == k.STAGES["coder_planner"].prompt
    assert json.dumps(history, sort_keys=True) == saved
    assert k.STAGES["coder_planner"].thinking is (planner == "thorough")
    assert k.STAGES["extended_initial"].thinking is True
    assert k.STAGES["extended_initial"].force_preserve_thinking is True


@pytest.mark.parametrize("planner", ("flash", "thorough"))
def test_multimodal_original_request_preserves_every_block(monkeypatch, tmp_path, planner):
    k = load(monkeypatch, tmp_path, planner=planner)
    blocks = [
        {"type": "text", "text": "Plan a clock inspired by this picture"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        {"type": "text", "text": "Keep the proportions"},
    ]
    history = [{"role": "user", "content": blocks}]
    frozen = json.dumps(history, sort_keys=True)
    wire = k._coder_isolate_planner_request(history, k.STAGES["coder_planner"])
    assert [m["role"] for m in wire] == ["system", "user"]
    delegated = wire[1]["content"]
    assert delegated[0]["text"] == k._CODER_ARCHITECT_TASK_SOURCE_HEADER
    assert delegated[1:-1] == blocks
    assert delegated[1] is blocks[0]
    assert delegated[-1]["text"] == k._CODER_ARCHITECT_TASK_SOURCE_FOOTER
    assert json.dumps(history, sort_keys=True) == frozen


@pytest.mark.parametrize("planner", ("flash", "thorough"))
def test_delegation_excludes_previous_architect_tool_continuation(monkeypatch, tmp_path, planner):
    k = load(monkeypatch, tmp_path, planner=planner)
    history = [
        {"role": "user", "content": "Verify that the testing workspace is empty"},
        {"role": "assistant", "content": "",
             "_jack_internal_tool_exchange": True, "_jack_stage_key": "coder_planner",
             "tool_calls": [
            {"id": "inspect-1", "type": "function", "function": {
                "name": "bash", "arguments": '{"command":"ls -la"}'}}]},
        {"role": "tool", "tool_call_id": "inspect-1",
             "_jack_internal_tool_exchange": True, "content": "total 8\ndrwxr-x .\ndrwxr-x .."},
    ]
    wire = k._coder_isolate_planner_request(history, k.STAGES["coder_planner"], source_history=history)
    assert [m["role"] for m in wire] == ["system", "user"]
    assert "Verify that the testing workspace is empty" in wire[1]["content"]
    assert "inspect-1" not in json.dumps(wire)
    assert "total 8" not in json.dumps(wire)


@pytest.mark.parametrize("planner", ("flash", "thorough"))
def test_backend_wire_preserves_original_request_without_changing_coder_and_has_stable_prefix(monkeypatch, tmp_path, planner):
    async def run():
        k = load(monkeypatch, tmp_path, planner=planner)
        requests = []
        def respond(request):
            requests.append(json.loads(request.content))
            delta = {"choices": [{"index": 0, "delta": {"content": "Coder should create an SVG and verify it."},
                                  "finish_reason": "stop"}]}
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  text="data: " + json.dumps(delta) + "\n\ndata: [DONE]\n\n")
        backend = k.OpenAICompatibleBackend(k.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async def model():
            return "test-model"
        backend.resolve_model = model
        try:
            for task in ("Create a cuckoo clock SVG", "Create a black and gold clock SVG"):
                async for _ in backend.chat_stream(
                    messages=[{"role": "user", "content": task}],
                    secondary_system="Caller system must not replace Planner",
                    profile=k.STAGES["coder_planner"], tools=None, tool_choice="none",
                ):
                    pass
        finally:
            await backend._client.aclose()
        assert len(requests) == 2
        first, second = requests
        assert first["messages"][0] == second["messages"][0]
        assert first["messages"][0]["content"] == k.STAGES["coder_planner"].prompt
        assert "Create a cuckoo clock SVG" in first["messages"][1]["content"]
        assert "Create a black and gold clock SVG" in second["messages"][1]["content"]
        assert first["messages"][1]["content"].startswith(k._CODER_ARCHITECT_TASK_SOURCE_HEADER)
        assert first["chat_template_kwargs"]["enable_thinking"] is (planner == "thorough")
        assert first["chat_template_kwargs"]["preserve_thinking"] is (planner == "thorough")
        assert first["reasoning_effort"] == ("none" if planner == "flash" else "xhigh")
        assert "Caller system must not replace Planner" not in str(first["messages"])
        assert k.STAGES["extended_initial"].thinking is True
        assert "sole implementation and answer-authority" in k.CODER_EXECUTOR_PROMPT
    asyncio.run(run())
