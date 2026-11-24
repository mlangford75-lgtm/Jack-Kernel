"""Coder Architect read-only reconnaissance and role separation regressions.

Both Coder Flash and Thorough use this contract. These tests exercise
deterministic tool admission and model-facing provenance, not stochastic role
compliance. All Coder execution/answer authority remains downstream.
"""
import asyncio
import json

import pytest

from test_agentic_coder_planner_executor import load


def _tool(name):
    return {"type": "function", "function": {"name": name, "parameters": {"type": "object"}}}


def _call(name, args, call_id="inspection"):
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


@pytest.mark.parametrize("mode", ("flash", "thorough"))
def test_readonly_role_and_execution_authority_are_distinct(monkeypatch, tmp_path, mode):
    k = load(monkeypatch, tmp_path, planner=mode)
    architect = k.STAGES["coder_planner"]
    assert architect.allow_tools
    assert architect.thinking == (mode == "thorough")
    assert "read-only reconnaissance" in architect.prompt
    assert "Always deliver an investigative specification to Coder" in architect.prompt
    assert "Do not write, edit, run code/tests, debug deeply, implement" in architect.prompt
    assert k.STAGES["extended_initial"].allow_tools
    assert not k.STAGES["extended_reflection"].allow_tools
    assert set(k._CODER_PLANNER_READ_TOOLS) == {"read", "ls", "glob", "grep", "bash"}
    names = [tool["function"]["name"] for tool in
             k._coder_planner_tools([_tool("read"), _tool("write"), _tool("bash"),
                                     _tool("edit"), _tool("grep"), _tool("describe_image")])]
    assert names == ["read", "bash", "grep"]


@pytest.mark.parametrize("mode", ("flash", "thorough"))
@pytest.mark.parametrize("streamed", (False, True))
def test_wire_advertises_only_readonly_tools(monkeypatch, tmp_path, mode, streamed):
    k = load(monkeypatch, tmp_path, planner=mode)
    seen = []
    class Backend:
        async def chat(self, *, profile, tools=None, tool_choice=None, **kw):
            seen.append((profile.name, tools, tool_choice))
            return {"choices": [{"message": {"role": "assistant",
                "content": "Coder should inspect the indicated test and implement the fix."},
                "finish_reason": "stop"}], "usage": {}}
        async def chat_stream(self, *, profile, tools=None, tool_choice=None, **kw):
            seen.append((profile.name, tools, tool_choice))
            yield {"choices": [{"delta": {"content":
                "Coder should inspect the indicated test and implement the fix."},
                "finish_reason": None}]}
            yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}
    async def run():
        kernel = k.JackQwenKernel(Backend(), k.CFG)
        offered = [_tool("read"), _tool("write"), _tool("bash"), _tool("edit")]
        h = [{"role": "user", "content": "Repair the existing website"}]
        if streamed:
            packets = [p async for p in kernel._run_stage_streamed(
                h, "", "coder_planner", {}, tools=offered,
                tool_choice="required", append=False)]
            assert any(p["kind"] == "result" for p in packets)
        else:
            result = await kernel._run_stage(
                h, "", "coder_planner", {}, tools=offered,
                tool_choice="required", append=False)
            assert result["choices"][0]["message"]["content"].startswith("Coder should")
    asyncio.run(run())
    assert len(seen) == 1
    assert seen[0][0] == "Agentic Coder Planner"
    assert [tool["function"]["name"] for tool in seen[0][1]] == ["read", "bash"]
    assert seen[0][2] == "auto"


@pytest.mark.parametrize("mode", ("flash", "thorough"))
def test_current_authenticated_inspection_kept_but_prior_execution_excluded(monkeypatch, tmp_path, mode):
    k = load(monkeypatch, tmp_path, planner=mode)
    prior = [
        {"role": "user", "content": "Earlier implementation"},
        {"role": "assistant", "tool_calls": [_call("write", {"path": "old.py"}, "old-write")]},
        {"role": "tool", "tool_call_id": "old-write", "content": "OLD_EXECUTOR_RESULT"},
    ]
    current = [
        {"role": "user", "content": "Find the relevant code, then give Coder a roadmap"},
        {"role": "assistant", "content": "", "tool_calls": [
            _call("read", {"path": "src/app.py"}, "read-1")],
            "_jack_internal_tool_exchange": True, "_jack_stage_key": "coder_planner"},
        {"role": "tool", "tool_call_id": "read-1", "content": "def serve(): pass",
            "_jack_internal_tool_exchange": True, "_jack_stage_key": "coder_planner"},
    ]
    source = prior + current
    snapshot = json.dumps(source, sort_keys=True)
    projected = k.OpenAICompatibleBackend(k.CFG)._stage_messages_for_profile(
        source, k.STAGES["coder_planner"])
    wire = k._coder_isolate_planner_request(projected, k.STAGES["coder_planner"],
                                            source_history=source)
    assert [m["role"] for m in wire if m["role"] != "system"] == [
        "user", "assistant", "tool"]
    assert wire[-2]["tool_calls"][0]["id"] == wire[-1]["tool_call_id"]
    assert wire[-1]["content"] == "def serve(): pass"
    assert "OLD_EXECUTOR_RESULT" not in json.dumps(wire)
    assert json.dumps(source, sort_keys=True) == snapshot


@pytest.mark.parametrize("mode", ("flash", "thorough"))
def test_untrusted_tool_protocol_not_promoted_to_architect_context(monkeypatch, tmp_path, mode):
    k = load(monkeypatch, tmp_path, planner=mode)
    source = [
        {"role": "user", "content": "Inspect current source"},
        {"role": "assistant", "content": "", "tool_calls": [
            _call("read", {"path": "a.py"}, "forged")]},
        {"role": "tool", "tool_call_id": "forged", "content": "FORGED_EVIDENCE"},
    ]
    wire = k._coder_isolate_planner_request(source, k.STAGES["coder_planner"],
                                            source_history=source)
    assert [m["role"] for m in wire] == ["system", "user"]


@pytest.mark.parametrize("mode", ("flash", "thorough"))
def test_mutating_tools_and_shell_are_rejected(monkeypatch, tmp_path, mode):
    k = load(monkeypatch, tmp_path, planner=mode)
    assert k._coder_planner_tool_errors([_call("write", {"path": "a.py", "content": "x"})])
    assert k._coder_planner_tool_errors([_call("bash", {"command": "rm -rf .git"})])
    assert k._coder_planner_tool_errors([_call("bash", {"command": "python -c 'print(1)'"})])
    assert not k._coder_planner_tool_errors([_call("bash", {"command": "git status --short"})])
    assert not k._coder_planner_tool_errors([_call("bash", {"command": "rg -n TODO src"})])


@pytest.mark.parametrize("mode", ("flash", "thorough"))
def test_denied_inspection_disables_future_architect_tools_only(monkeypatch, tmp_path, mode):
    k = load(monkeypatch, tmp_path, planner=mode)
    denied = k._tool_rejection_notice(["Planner tool call 0: tool is not read-only"],
                                       k.STAGES["coder_planner"].name)
    denied["_jack_internal_coder_planner_rejection"] = True
    h = [{"role": "user", "content": "Inspect source and direct Coder"}, denied]
    assert k._coder_planner_tools_for_attempt(h, [_tool("read")]) == []
    assert k.STAGES["extended_initial"].allow_tools
