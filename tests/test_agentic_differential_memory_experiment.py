"""Retired differential-memory switch cannot change the sole isolated Stage-2 payload."""
import asyncio
import importlib.util
import json
import sys
import uuid
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(monkeypatch, tmp_path, *, differential):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_AGENTIC_TRANSACTION_LINKS", "1")
    monkeypatch.setenv("JACK_AGENTIC_TASK_ANCHOR", "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT", "1")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_FINAL_PAPER", "0")
    monkeypatch.setenv("JACK_AGENTIC_DIFFERENTIAL_MEMORY", "1" if differential else "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_RETENTION_TEST", "baseline")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_differential_retired_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


def history():
    return [
        {"role": "user", "content": "Prior work"},
        {"role": "assistant", "content": "Prior memory"},
        {"role": "user", "content": "Make the clock gold."},
        {"role": "assistant", "content": "Edited clock.html; rendering unverified.",
         "reasoning_content": "Used gold CSS; visual check unavailable.",
         "_jack_extended_candidate_response": True},
    ]


async def capture(k, stream):
    seen = []

    def reply(request):
        seen.append(json.loads(request.content))
        if stream:
            return httpx.Response(200, text='data: {"choices":[{"index":0,"delta":{"content":"Memory"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "Memory"}, "finish_reason": "stop"}], "usage": {}})

    backend = k.OpenAICompatibleBackend(k.CFG)
    await backend._client.aclose()
    backend._client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
    async def model():
        return "test-model"
    backend.resolve_model = model
    try:
        args = dict(messages=history(), secondary_system="", profile=k.STAGES["extended_reflection"],
                    tools=[{"type": "function", "function": {"name": "write", "parameters": {"type": "object"}}}],
                    tool_choice="auto")
        if stream:
            async for _ in backend.chat_stream(**args):
                pass
        else:
            await backend.chat(**args)
    finally:
        await backend._client.aclose()
    assert len(seen) == 1
    return seen[0]


@pytest.mark.parametrize("stream", [False, True])
def test_differential_flag_cannot_change_isolated_stage2(monkeypatch, tmp_path, stream):
    control = load(monkeypatch, tmp_path, differential=False)
    a = asyncio.run(capture(control, stream))
    alternate = load(monkeypatch, tmp_path, differential=True)
    b = asyncio.run(capture(alternate, stream))
    assert a == b
    assert len(a["messages"]) == 4
    assert a["messages"][1]["content"] == "Make the clock gold."
    assert a["messages"][2]["content"] == "Edited clock.html; rendering unverified."
    assert a["messages"][2]["reasoning_content"] == "Used gold CSS; visual check unavailable."
    assert "Prior memory" not in json.dumps(a)
    assert "tools" not in a
    assert alternate._stage_continuation(alternate.STAGES["extended_reflection"]) == alternate._AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION
