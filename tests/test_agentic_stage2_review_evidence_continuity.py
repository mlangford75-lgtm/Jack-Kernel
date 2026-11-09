"""Stage-2 review must preserve source evidence and cached prefix, not re-digest it."""

import asyncio
import importlib.util
import json
import sys
import uuid
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(monkeypatch, tmp_path, cache):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "balanced")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT", "1" if cache else "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_FINAL_REVIEW", "1")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_review_evidence_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


def current_turn_history():
    return [
        {"role": "user", "content": "Earlier unrelated question"},
        {"role": "assistant", "content": "Earlier answer"},
        {"role": "user", "content": "Plan a family picnic for a rainy afternoon."},
        {"role": "assistant", "content": "Initial proposal",
         "reasoning_content": "R1_INITIAL: compare indoor and outdoor options."},
        {"role": "assistant", "content": "Initial proposal", "reasoning_content":
         "R1_VERIFICATION: check opening hours and travel time."},
        {"role": "assistant", "content": "", "_jack_internal_tool_exchange": True,
         "_jack_stage_key": "extended_initial",
         "tool_calls": [{"id": "lookup-1", "type": "function",
                         "function": {"name": "lookup", "arguments": '{"query":"opening hours"}'}}]},
        {"role": "tool", "tool_call_id": "lookup-1", "name": "lookup",
         "_jack_internal_tool_exchange": True, "_jack_stage_key": "extended_initial",
         "content": "Lookup unavailable", "_jack_internal_tool_failed": True},
        {"role": "assistant", "content": "Use an indoor option.",
         "reasoning_content": "R1_ALIGNMENT: failed lookup, do not claim opening hours."},
        {"role": "assistant", "content": "Suggest an indoor picnic without asserting opening hours.",
         "reasoning_content": "R1_FINAL: acknowledge uncertainty.",
         "_jack_extended_candidate_response": True,
         "_jack_agentic_stage1_tool_observation_complete": True,
         "_jack_stage_key": "extended_initial"},
    ]


async def capture_payloads(k, history, cache, stream):
    payloads = []

    def responder(request):
        payloads.append(json.loads(request.content))
        if stream:
            event = json.dumps({"choices": [{"index": 0, "delta": {"content": "Draft memory"},
                                             "finish_reason": None}]})
            last = json.dumps({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                               "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}})
            return httpx.Response(200, text="data: " + event + "\n\n"
                                  + "data: " + last + "\n\ndata: [DONE]\n\n",
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"choices": [{"index": 0, "message": {
            "role": "assistant", "content": "Draft memory"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}})

    backend = k.OpenAICompatibleBackend(k.CFG)
    await backend._client.aclose()
    backend._client = httpx.AsyncClient(transport=httpx.MockTransport(responder))

    async def resolve():
        return "test-model"

    backend.resolve_model = resolve

    async def once():
        if stream:
            async for _ in backend.chat_stream(
                messages=history, secondary_system="", profile=k.STAGES["extended_reflection"],
                tools=None, tool_choice=None):
                pass
        else:
            await backend.chat(
                messages=history, secondary_system="", profile=k.STAGES["extended_reflection"],
                tools=None, tool_choice=None)

    try:
        await once()
        k._agentic_begin_stage2_review(history, {
            "choices": [{"message": {"content": "Draft memory"}, "finish_reason": "stop"}]
        })
        await once()
    finally:
        await backend._client.aclose()
    return payloads


@pytest.mark.parametrize("cache", [False, True])
@pytest.mark.parametrize("stream", [False, True])
def test_review_preserves_exact_original_source_prefix_and_evidence(monkeypatch, tmp_path, cache, stream):
    k = load(monkeypatch, tmp_path, cache)
    history = current_turn_history()
    original = json.dumps(history, sort_keys=True)
    first, review = asyncio.run(capture_payloads(k, history, cache, stream))

    first_messages = first["messages"]
    reviewed_messages = review["messages"]
    assert reviewed_messages[:len(first_messages)] == first_messages
    assert len(reviewed_messages) == len(first_messages) + 2
    assert reviewed_messages[-2] == {"role": "assistant", "content": "Draft memory"}
    assert reviewed_messages[-1] == {"role": "user", "content": k.AGENTIC_STAGE2_FINAL_REVIEW_TRIGGER}
    assert reviewed_messages[-1]["content"] == "Wait, more verification is needed. Test the reasoning for errors, mistakes, or poor quality. Make changes, if necessary"

    serialized = json.dumps(first_messages)
    for marker in ("R1_INITIAL", "R1_VERIFICATION", "R1_ALIGNMENT", "R1_FINAL",
                   "lookup-1", "REPORTED_ERROR"):
        assert marker in serialized
    assert "Earlier unrelated question" not in serialized
    assert "Earlier answer" not in serialized
    assert "tools" not in first and "tools" not in review
    assert "tool_choice" not in first and "tool_choice" not in review
    assert k.active_response_target(history)["content"] == "Plan a family picnic for a rainy afternoon."
    assert history[-2]["content"] == "Draft memory"
    assert json.dumps(history[:-2], sort_keys=True) == original
