"""Tool-free Coder Architect contracts: wire isolation, no execution, preserved handoff."""
import asyncio
import json
import uuid

import httpx
import pytest

from test_agentic_coder_planner_executor import load


@pytest.mark.parametrize("planner", ("flash", "thorough"))
def test_architect_has_no_tools_and_delegates_repository_review(monkeypatch, tmp_path, planner):
    k = load(monkeypatch, tmp_path, planner=planner)
    p = k.STAGES["coder_planner"]
    assert p.allow_tools is False
    assert p.thinking is (planner == "thorough")
    assert "You have no tool interface of any kind" in p.prompt
    assert "Instruct Coder to use its authorized tools to review existing work" in p.prompt
    assert "Never claim to have reviewed previous work" in p.prompt
    assert "Coder must use its authorized tools to inspect the actual directory contents" in p.prompt
    assert k.STAGES["extended_initial"].allow_tools is True
    assert k.STAGES["extended_initial"].thinking is True
    assert k.STAGES["extended_reflection"].allow_tools is False


@pytest.mark.parametrize("planner", ("flash", "thorough"))
@pytest.mark.parametrize("stream", (False, True))
def test_architect_request_exposes_no_tool_schema_or_external_system(monkeypatch, tmp_path, planner, stream):
    k = load(monkeypatch, tmp_path, planner=planner)
    seen = []
    def respond(request):
        wire = json.loads(request.content)
        seen.append(wire)
        if stream:
            return httpx.Response(
                200,
                text='data: {"choices":[{"index":0,"delta":{"content":"Coder must inspect prior work."},"finish_reason":null}]}\n\n'
                     'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
                     'data: [DONE]\n\n',
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "Coder must inspect prior work."},
                         "finish_reason": "stop"}], "usage": {},
        })
    async def run():
        b = k.OpenAICompatibleBackend(k.CFG)
        await b._client.aclose()
        b._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async def model():
            return "test-model"
        b.resolve_model = model
        offered = [{"type": "function", "function": {"name": "bash",
                    "parameters": {"type": "object", "properties": {}}}}]
        history = [{"role": "system", "content": "EXTERNAL AGENT OVERRIDE"},
                   {"role": "developer", "content": "EXTERNAL DEVELOPER OVERRIDE"},
                   {"role": "user", "content": "Review existing work and fix it."}]
        try:
            kwargs = dict(messages=history, secondary_system="EXTERNAL SECONDARY OVERRIDE",
                          profile=k.STAGES["coder_planner"], tools=offered, tool_choice="required")
            if stream:
                async for _ in b.chat_stream(**kwargs):
                    pass
            else:
                await b.chat(**kwargs)
        finally:
            await b._client.aclose()
    asyncio.run(run())
    assert len(seen) == 1
    wire = seen[0]
    assert "tools" not in wire
    assert "tool_choice" not in wire
    assert [m["role"] for m in wire["messages"]] == ["system", "user"]
    assert wire["messages"][0]["content"] == k.STAGES["coder_planner"].prompt
    assert wire["messages"][1]["content"] == "Review existing work and fix it."
    assert "EXTERNAL AGENT OVERRIDE" not in json.dumps(wire)
    assert "EXTERNAL DEVELOPER OVERRIDE" not in json.dumps(wire)
    assert "EXTERNAL SECONDARY OVERRIDE" not in json.dumps(wire)


@pytest.mark.parametrize("planner", ("flash", "thorough"))
def test_architect_cannot_read_legacy_tool_exchange_but_coder_retains_it(monkeypatch, tmp_path, planner):
    k = load(monkeypatch, tmp_path, planner=planner)
    old = [
        {"role": "user", "content": "Inspect the directory"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "old-read", "type": "function", "function": {
                "name": "bash", "arguments": '{"command":"ls -la"}'}}]},
        {"role": "tool", "tool_call_id": "old-read", "content": "file-a.txt"},
        {"role": "assistant", "content": "Existing observation: file-a.txt"},
    ]
    snapshot = json.dumps(old, sort_keys=True)
    view = k._coder_isolate_planner_request(old, k.STAGES["coder_planner"])
    assert [m["role"] for m in view] == ["system", "user", "assistant"]
    assert "file-a.txt" in view[-1]["content"]
    assert not any("tool_calls" in m or m["role"] == "tool" for m in view)
    assert json.dumps(old, sort_keys=True) == snapshot


@pytest.mark.parametrize("planner", ("flash", "thorough"))
def test_host_never_offers_architect_tools_even_if_caller_supplies_them(monkeypatch, tmp_path, planner):
    k = load(monkeypatch, tmp_path, planner=planner)
    observed = []
    class Backend:
        async def chat(self, *, messages, profile, tools=None, tool_choice=None, **kwargs):
            observed.append((profile.name, tools, tool_choice))
            return {"choices": [{"message": {"role": "assistant", "content": "Coder must inspect and verify."},
                                 "finish_reason": "stop"}], "usage": {}}
    async def run():
        kernel = k.JackQwenKernel(Backend(), k.CFG)
        offered = [{"type": "function", "function": {"name": "write", "parameters": {}}}]
        history = [{"role": "user", "content": "Fix the repository"}]
        result = await kernel._run_stage(history, "", "coder_planner", {}, tools=offered, tool_choice="required", append=False)
        assert "Coder must inspect and verify." in result["choices"][0]["message"]["content"]
    asyncio.run(run())
    assert observed == [("Agentic Coder Planner", None, None)]


@pytest.mark.parametrize("planner", ("flash", "thorough"))
def test_unadvertised_tool_proposal_cannot_execute_and_falls_forward_to_coder(monkeypatch, tmp_path, planner):
    k = load(monkeypatch, tmp_path, planner=planner)
    class Backend:
        async def chat(self, *, messages, profile, tools=None, tool_choice=None, **kwargs):
            assert tools is None
            return {"choices": [{"message": {"role": "assistant", "content": "",
                "tool_calls": [{"id": "blocked", "type": "function",
                    "function": {"name": "bash", "arguments": '{"command":"ls -la"}'}}]},
                "finish_reason": "tool_calls"}], "usage": {}}
    async def run():
        kernel = k.JackQwenKernel(Backend(), k.CFG)
        history = [{"role": "user", "content": "Verify my existing work"}]
        result = await kernel._run_stage(history, "", "coder_planner", {}, tools=[
            {"type": "function", "function": {"name": "bash"}}], append=False)
        message = result["choices"][0]["message"]
        assert message.get("tool_calls") is None
        assert "Jack host recovery handoff to Coder" in message["content"]
        assert "Verify my existing work" in message["content"]
    asyncio.run(run())


@pytest.mark.parametrize("planner", ("flash", "thorough"))
def test_streamed_unadvertised_tool_proposal_never_reaches_caller(monkeypatch, tmp_path, planner):
    k = load(monkeypatch, tmp_path, planner=planner)
    class Backend:
        async def chat_stream(self, *, messages, profile, tools=None, tool_choice=None, **kwargs):
            assert profile.name == "Agentic Coder Planner"
            assert tools is None and tool_choice is None
            yield {"choices": [{"index": 0, "delta": {"tool_calls": [
                {"index": 0, "id": "unadvertised-tool", "type": "function",
                 "function": {"name": "bash", "arguments": '{"command":"ls -la"}'}}
            ]}, "finish_reason": None}]}
            yield {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}

    async def run():
        kernel = k.JackQwenKernel(Backend(), k.CFG)
        packets = [p async for p in kernel._run_stage_streamed(
            [{"role": "user", "content": "Review the existing repository"}],
            "", "coder_planner", {}, tools=[{"type": "function", "function": {"name": "bash"}}],
            tool_choice="required", append=False,
        )]
        assert not any(p.get("kind") == "tool_call" or p.get("kind") == "tool_calls" for p in packets)
        assert not any("tool_calls" in p for p in packets)
        results = [p["data"] for p in packets if p.get("kind") == "result"]
        assert len(results) == 1
        reply = results[0]["choices"][0]["message"]
        assert reply.get("tool_calls") is None
        assert "Jack host recovery handoff to Coder" in reply["content"]
        assert "Review the existing repository" in reply["content"]
    asyncio.run(run())
