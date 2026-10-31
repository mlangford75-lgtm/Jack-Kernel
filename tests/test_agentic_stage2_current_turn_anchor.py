"""Agentic: retain current R1, retire prior R2, preserve Stage-2 cache prefix."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
STAGE1 = (
    "Reasoning effort is set to xhigh. Please think carefully through the task, "
    "validate key assumptions, consider plausible alternatives, and prioritize "
    "correctness, consistency, and clarity in the final answer."
)
STAGE2 = "Generate a detailed summary of why you came to this conclusion."

def load(cache):
    os.environ["JACK_REASONING_LEVEL"] = "agentic"
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "off"
    os.environ["JACK_BACKEND_MODEL"] = "test-model"
    os.environ["JACK_BACKEND_PROFILE"] = "lmstudio"
    os.environ["JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT"] = "1" if cache else "0"
    name = "jack_turn_anchor_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k

def history():
    return [
        {"role": "user", "content": "Turn 1: inspect empty workspace"},
        {"role": "assistant", "content": "Turn 1 retrospective"},
        {"role": "assistant", "content": "Turn 1 frozen answer"},
        {"role": "user", "content": "Turn 2: generate cuckoo clock SVG"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "write-1", "type": "function", "function": {"name": "write", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "write-1", "name": "write", "content": "Successfully wrote cuckoo-clock.svg"},
        {"role": "assistant", "content": "Turn 2 frozen answer: created cuckoo-clock.svg", "reasoning_content": "R1_2 created SVG"},
    ]

def tools():
    return [{"type": "function", "function": {"name": "write", "description": "write file", "parameters": {"type": "object", "properties": {}}}}]

async def payloads(k, full_history, cache):
    recorded = []
    def responder(request):
        recorded.append(json.loads(request.content))
        data = json.dumps({"choices": [{"index": 0, "delta": {"content": "M"}, "finish_reason": None}]})
        end = json.dumps({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
        return httpx.Response(200, text="data: " + data + "\n\ndata: " + end + "\n\ndata: [DONE]\n\n", headers={"content-type": "text/event-stream"})
    backend = k.OpenAICompatibleBackend(k.CFG)
    await backend._client.aclose()
    backend._client = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    async def model():
        return "test-model"
    backend.resolve_model = model
    async for _ in backend.chat_stream(
        messages=full_history,
        secondary_system="",
        profile=k.STAGES["extended_reflection"],
        tools=tools() if cache else None,
        tool_choice="auto" if cache else None,
    ):
        pass
    await backend._client.aclose()
    assert len(recorded) == 1
    return recorded[0]

@pytest.mark.parametrize("cache", [True, False])
def test_stage2_sees_current_r1_but_never_old_r2(cache):
    k = load(cache)
    h = history()
    original = json.dumps(h, sort_keys=True)
    p = asyncio.run(payloads(k, h, cache))
    assert json.dumps(h, sort_keys=True) == original
    rendered = json.dumps(p["messages"], sort_keys=True)
    assert "R2_1 investigated empty workspace" not in rendered
    assert "R1_2 created SVG" in rendered
    assert p["messages"][-2]["content"] == h[-1]["content"]
    assert p["messages"][-2]["reasoning_content"] == "R1_2 created SVG"
    assert p["messages"][-1]["role"] == "user"
    assert k.AGENTIC_STAGE1_PROMPT == STAGE1
    assert k.AGENTIC_36_STAGE2_PROMPT == STAGE2
    assert k.STAGES["extended_reflection"].allow_tools is False
    if cache:
        assert p["messages"][0]["content"] == STAGE1
        assert p["messages"][-1]["content"].startswith(STAGE2 + "\\n\\n".replace("\\n", "\n"))
        assert p["tool_choice"] == "auto"
        assert len(p["tools"]) == 1
    else:
        assert p["messages"][0]["content"] == STAGE2
        assert "tools" not in p

def test_stage1_prefix_unchanged_when_stage2_is_appended():
    k = load(True)
    h = history()
    stage1 = k.BACKEND._stage_messages_for_profile(h[:-1], k.STAGES["extended_initial"])
    stage2 = k.BACKEND._stage_messages_for_profile(h, k.STAGES["extended_reflection"])
    assert stage2[:len(stage1)] == stage1
    assert stage2[-1]["content"] == "Turn 2 frozen answer: created cuckoo-clock.svg"
    assert k._stage_continuation(k.STAGES["extended_reflection"], h).startswith(
        "[JACK RUNTIME STAGE CONTINUATION"
    )

def test_incoming_history_never_recovers_previous_r2():
    k = load(True)
    h = [
        {"role": "user", "content": "workspace"},
        {"role": "assistant", "content": "previous answer",
         "reasoning_content": "===== JACK AGENTIC NATIVE PASS 2 =====\n"
                              "[NATIVE REASONING]\nold private R2"},
        {"role": "user", "content": "create svg"},
    ]
    original = json.dumps(h, sort_keys=True)
    projected = k.compact_incoming_history(h)
    assert json.dumps(h, sort_keys=True) == original
    assert not any("reasoning_content" in item for item in projected)
    assert "old private R2" not in json.dumps(projected)
    assert projected[-1]["content"] == "create svg"

def test_historical_u_m_a_is_still_available_without_r2():
    k = load(True)
    h = history()
    assert [m["role"] for m in h] == [
        "user", "assistant", "assistant", "user", "assistant", "tool", "assistant"
    ]
    assert h[0]["content"] == "Turn 1: inspect empty workspace"
    assert h[1]["content"] == "Turn 1 retrospective"
    assert h[2]["content"] == "Turn 1 frozen answer"
    assert h[-1]["reasoning_content"] == "R1_2 created SVG"
