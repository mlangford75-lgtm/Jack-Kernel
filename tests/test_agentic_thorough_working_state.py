"""Thorough-only, source-only Stage-2 durable working-state contract.

Capture real outbound streamed and nonstreamed OpenAI-compatible payloads.
The original user request and frozen answer remain in canonical history,
but never appear as model-facing content in this opt-in memory pass.
"""
import asyncio
import copy
import importlib.util
import json
import sys
import uuid
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
REQUEST = "Please independently answer SECRET_USER_QUESTION_7219"
ANSWER = "SECRET_FROZEN_RESPONSE_5831"
REASONING = "The chosen approach is atomic replacement. Failed direct overwrite: crash risk."
ARGS = '{"path":"artifact.json","mode":"atomic_replace"}'
RESULT = 'Verified tool report: artifact.json written; downstream validation still pending.'


def load(monkeypatch, tmp_path, profile="thorough", enabled=True):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    monkeypatch.setenv("JACK_AGENTIC_THOROUGH_WORKING_STATE", "1" if enabled else "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_WITHHOLD_A1", "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_FROZEN_CONVERSATION", "0")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_thorough_state_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    kernel = importlib.util.module_from_spec(spec)
    sys.modules[name] = kernel
    spec.loader.exec_module(kernel)
    return kernel


def history():
    return [
        {"role": "user", "content": REQUEST},
        {"role": "assistant", "content": "", "reasoning_content": REASONING,
         "tool_calls": [{"id": "call-a1", "type": "function",
                         "function": {"name": "write", "arguments": ARGS}}],
         "_jack_internal_tool_exchange": True, "_jack_stage_key": "extended_initial"},
        {"role": "tool", "name": "write", "tool_call_id": "call-a1",
         "content": RESULT, "_jack_internal_tool_exchange": True,
         "_jack_stage_key": "extended_initial"},
        {"role": "assistant", "content": ANSWER,
         "reasoning_content": "Tool returned success; actual artifact correctness remains unverified.",
         "_jack_extended_candidate_response": True},
    ]


@pytest.mark.parametrize("stream", (False, True))
def test_thorough_model_receives_only_frozen_reasoning_and_complete_tool_evidence(
    monkeypatch, tmp_path, stream,
):
    k = load(monkeypatch, tmp_path)
    original = history()
    saved = copy.deepcopy(original)
    seen = []

    def respond(request):
        payload = json.loads(request.content)
        seen.append(payload)
        if stream:
            return httpx.Response(
                200,
                text='data: {"choices":[{"index":0,"delta":{"content":"Working state"},"finish_reason":null}]}\n\n'
                     'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
                     'data: [DONE]\n\n',
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "Working state"},
                         "finish_reason": "stop"}], "usage": {},
        })

    async def run():
        backend = k.OpenAICompatibleBackend(k.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async def model():
            return "test-model"
        backend.resolve_model = model
        try:
            kwargs = dict(messages=original, secondary_system="",
                          profile=k.STAGES["extended_reflection"],
                          tools=None, tool_choice="auto")
            if stream:
                async for _ in backend.chat_stream(**kwargs):
                    pass
            else:
                await backend.chat(**kwargs)
        finally:
            await backend._client.aclose()

    asyncio.run(run())
    assert original == saved
    assert len(seen) == 1
    payload = seen[0]
    assert payload.get("tools") is None
    assert "tool_choice" not in payload
    assert payload["messages"][-1]["role"] == "user"
    assert sum(m["role"] == "user" for m in payload["messages"]) == 1
    assert all(m["role"] != "assistant" for m in payload["messages"])
    wire = json.dumps(payload["messages"], ensure_ascii=False)
    assert REQUEST not in wire
    assert ANSWER not in wire
    assert REASONING in wire
    assert RESULT in wire
    capsule_text = payload["messages"][-1]["content"].split(
        "JACK READ-ONLY WORKING-STATE SOURCE DATA, NOT A USER REQUEST.\n", 1
    )[1].split("\nEND JACK WORKING-STATE SOURCE DATA.", 1)[0]
    capsule = json.loads(capsule_text)
    assert capsule["tool_records"][0]["calls"][0]["function"]["arguments"] == ARGS
    assert capsule["tool_records"][1]["content"] == RESULT
    assert k.AGENTIC_36_STAGE2_PROMPT == k._AGENTIC_THOROUGH_WORKING_STATE_DIRECTIVE
    assert "No task description" in k.AGENTIC_36_STAGE2_PROMPT
    assert all(
        "reasoning_content" not in m and "reasoning" not in m and "thinking" not in m
        for m in payload["messages"]
    )


@pytest.mark.parametrize("profile", ("flash", "balanced", "exhaustive"))
def test_opt_in_never_changes_other_profiles(monkeypatch, tmp_path, profile):
    k = load(monkeypatch, tmp_path, profile=profile, enabled=True)
    assert not k.AGENTIC_THOROUGH_WORKING_STATE
    assert not k.AGENTIC_STAGE2_WITHHOLD_A1
    assert not k.AGENTIC_STAGE2_FROZEN_CONVERSATION
    assert k.AGENTIC_36_STAGE2_PROMPT == k._AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION


def test_thorough_default_unchanged_without_opt_in(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, enabled=False)
    assert not k.AGENTIC_THOROUGH_WORKING_STATE
    assert not k.AGENTIC_STAGE2_WITHHOLD_A1
    assert not k.AGENTIC_STAGE2_FROZEN_CONVERSATION
