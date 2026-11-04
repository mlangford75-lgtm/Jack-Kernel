"""Retired final-paper switch cannot replace the sole current-turn Stage-2 directive."""
import asyncio
import importlib.util
import json
import sys
import uuid
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(monkeypatch, tmp_path, *, paper):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_AGENTIC_TRANSACTION_LINKS", "1")
    monkeypatch.setenv("JACK_AGENTIC_TASK_ANCHOR", "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT", "1")
    monkeypatch.setenv("JACK_AGENTIC_DIFFERENTIAL_MEMORY", "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_FINAL_PAPER", "1" if paper else "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_RETENTION_TEST", "baseline")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_paper_retired_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


async def capture(k, stream):
    seen = []
    def reply(request):
        seen.append(json.loads(request.content))
        if stream:
            return httpx.Response(200, text='data: {"choices":[{"index":0,"delta":{"content":"M"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "M"}, "finish_reason": "stop"}], "usage": {}})
    backend = k.OpenAICompatibleBackend(k.CFG)
    await backend._client.aclose()
    backend._client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
    async def model():
        return "test-model"
    backend.resolve_model = model
    history = [
        {"role": "user", "content": "Old request"},
        {"role": "assistant", "content": "Old memory"},
        {"role": "user", "content": "Fix the clock"},
        {"role": "assistant", "content": "Fixed clock; visual status unverified.",
         "reasoning_content": "Corrected gradient syntax.",
         "_jack_extended_candidate_response": True},
    ]
    try:
        kw = dict(messages=history, secondary_system="", profile=k.STAGES["extended_reflection"],
                  tools=[], tool_choice="auto")
        if stream:
            async for _ in backend.chat_stream(**kw):
                pass
        else:
            await backend.chat(**kw)
    finally:
        await backend._client.aclose()
    assert len(seen) == 1
    return seen[0]


@pytest.mark.parametrize("stream", [False, True])
def test_final_paper_flag_cannot_change_current_turn_memory(monkeypatch, tmp_path, stream):
    control = load(monkeypatch, tmp_path, paper=False)
    a = asyncio.run(capture(control, stream))
    alternate = load(monkeypatch, tmp_path, paper=True)
    b = asyncio.run(capture(alternate, stream))
    assert a == b
    assert len(a["messages"]) == 4
    assert a["messages"][1]["content"] == "Fix the clock"
    assert a["messages"][2]["content"] == "Fixed clock; visual status unverified."
    assert a["messages"][2]["reasoning_content"] == "Corrected gradient syntax."
    assert "Old memory" not in json.dumps(a)
    assert "Treat the current Stage-1 native reasoning as a draft" in a["messages"][3]["content"]
    assert "tools" not in a
