from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

MODULE = Path(__file__).resolve().parents[1] / "jack_responses_compat.py"
spec = importlib.util.spec_from_file_location("jack_responses_compat_test", MODULE)
compat = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(compat)


def test_codex_request_mapping_preserves_client_tools_and_jack_authority_boundary():
    chat, kinds = compat._chat_body({
        "model": "jack-kernel",
        "instructions": "caller developer instructions",
        "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hello"}]}],
        "tools": [
            {"type": "function", "name": "shell_command", "parameters": {"type": "object"}},
            {"type": "custom", "name": "apply_patch"},
            {"type": "web_search"},
        ],
        "tool_choice": "auto",
        "stream": True,
    })
    assert chat["messages"][0] == {"role": "developer", "content": "caller developer instructions"}
    assert chat["messages"][1] == {"role": "user", "content": "hello"}
    assert kinds == {"shell_command": "function", "apply_patch": "custom"}
    assert [tool["function"]["name"] for tool in chat["tools"]] == ["shell_command", "apply_patch"]


def test_named_responses_tool_choice_is_lowered_without_losing_exact_selection():
    chat, kinds = compat._chat_body({
        "input": "use the selected tool",
        "tools": [
            {"type": "function", "name": "alpha", "parameters": {"type": "object"}},
            {"type": "function", "name": "beta", "parameters": {"type": "object"}},
        ],
        "tool_choice": {"type": "function", "name": "beta"},
        "stream": True,
    })

    assert kinds == {"alpha": "function", "beta": "function"}
    assert chat["tool_choice"] == "required"
    assert [tool["function"]["name"] for tool in chat["tools"]] == ["beta"]

    with pytest.raises(HTTPException, match="does not match an available tool"):
        compat._chat_body({
            "input": "bad selection",
            "tools": [{"type": "function", "name": "alpha", "parameters": {"type": "object"}}],
            "tool_choice": {"type": "function", "name": "missing"},
        })


def test_plain_required_responses_tool_choice_is_preserved():
    chat, kinds = compat._chat_body({
        "input": "use a tool",
        "tools": [
            {"type": "function", "name": "alpha", "parameters": {"type": "object"}},
            {"type": "function", "name": "beta", "parameters": {"type": "object"}},
        ],
        "tool_choice": "required",
    })

    assert kinds == {"alpha": "function", "beta": "function"}
    assert chat["tool_choice"] == "required"
    assert [tool["function"]["name"] for tool in chat["tools"]] == ["alpha", "beta"]


def test_custom_tool_round_trip_and_structured_tool_output():
    kinds = {"apply_patch": "custom"}
    item = compat._tool_item({"id": "p", "function": {"name": "apply_patch", "arguments": '{"input":"PATCH"}'}}, kinds)
    assert item["type"] == "custom_tool_call"
    assert item["input"] == "PATCH"
    chat, _ = compat._chat_body({"input": [
        {"type": "function_call", "call_id": "x", "name": "shell_command", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "x", "output": {"body": [
            {"type": "input_text", "text": "line 1"}, {"type": "input_text", "text": "line 2"}
        ]}},
    ]})
    assert chat["messages"][1] == {"role": "tool", "tool_call_id": "x", "content": "line 1\nline 2"}


def test_stream_emits_live_reasoning_text_tool_call_and_required_completed_event():
    class StubCFG:
        virtual_model = "jack-kernel"

    class Kernel:
        async def stream(self, _body):
            for obj in [
                {"choices": [{"delta": {"reasoning_content": "think"}}]},
                {"choices": [{"delta": {"content": "OK"}}]},
                {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c", "function": {"name": "shell_command", "arguments": "{}"}}]}}]},
                {"usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}, "choices": []},
            ]:
                yield ("data: " + json.dumps(obj) + "\n\n").encode()
            yield b"data: [DONE]\n\n"

        async def _rearm_pending_tool_resume_for_messages(self, _messages):
            return None

        async def _rearm_pending_debugging_resumes_for_messages(self, _messages):
            return None

    class JK:
        CFG = StubCFG()
        KERNEL = Kernel()

    async def collect():
        events = []
        async for chunk in compat._stream(JK, {"messages": []}, {"shell_command": "function"}):
            data = next(line[6:] for line in chunk.decode().splitlines() if line.startswith("data: "))
            events.append(json.loads(data))
        return events

    events = asyncio.run(collect())
    kinds = [event["type"] for event in events]
    assert "response.reasoning_summary_text.delta" in kinds
    assert "response.output_text.delta" in kinds
    assert kinds[-1] == "response.completed"
    completed = events[-1]["response"]
    assert completed["output_text"] == "OK"
    assert completed["usage"]["total_tokens"] == 5
    assert any(item["type"] == "function_call" for item in completed["output"])
