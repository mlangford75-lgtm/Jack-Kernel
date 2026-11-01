"""Nemotron-only Agentic Stage-2 preservation experiment.

Tests observable backend request shape for real LM Studio-compatible streaming
and nonstreaming code paths without changing frozen stage prompts or caller data.
Does not claim to verify GGUF Jinja render behavior (requires local LM Studio).
"""
import asyncio
import importlib.util
import json
import sys
import uuid
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


def kernel(monkeypatch, tmp_path, *, enabled, model, mode="agentic"):
    monkeypatch.setenv("JACK_REASONING_LEVEL", mode)
    monkeypatch.setenv("JACK_BACKEND_MODEL", model)
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_AGENTIC_TRANSACTION_LINKS", "1")
    monkeypatch.setenv("JACK_AGENTIC_TASK_ANCHOR", "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT", "1")
    monkeypatch.setenv("JACK_AGENTIC_DIFFERENTIAL_MEMORY", "1")
    monkeypatch.setenv("JACK_NEMOTRON_STAGE2_RETAIN_THINKING", "1" if enabled else "0")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_nemotron_stage2_test_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def history():
    return [
        {"role": "user", "content": "Build a clock"},
        {"role": "assistant", "content": "A1 frozen", "reasoning_content": "Unseen reasoning on clock design and tool failure", "reasoning": "Unseen reasoning on clock design and tool failure"},
    ]


async def capture(k, *, stream, stage2=True):
    payloads = []
    def respond(request):
        payloads.append(json.loads(request.content))
        if stream:
            chunks = [
                'data: {"choices":[{"index":0,"delta":{"content":"retained"},"finish_reason":null}]}',
                'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}',
                'data: [DONE]',
            ]
            return httpx.Response(200, text="\n\n".join(chunks) + "\n\n", headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"choices":[{"message":{"role":"assistant","content":"retained"},"finish_reason":"stop"}],"usage":{}})
    b = k.OpenAICompatibleBackend(k.CFG)
    await b._client.aclose()
    b._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    async def resolve():
        return k.CFG.backend_model
    b.resolve_model = resolve
    stage = "extended_reflection" if stage2 else "extended_initial"
    kwargs = {
        "messages": history(), "secondary_system": "", "profile": k.STAGES[stage],
        "tools": [{"type":"function","function":{"name":"read","description":"read","parameters":{"type":"object","properties":{}}}}],
        "tool_choice": "auto",
    }
    try:
        if stream:
            async for _ in b.chat_stream(**kwargs):
                pass
        else:
            await b.chat(**kwargs)
    finally:
        await b._client.aclose()
    assert len(payloads) == 1
    return payloads[0]


@pytest.mark.parametrize("stream", [False, True])
def test_nemotron_only_stage2_template_setting_changes(monkeypatch, tmp_path, stream):
    model = "nvidia-nemotron-3.5-lightning-30b-a3b-apex"
    control = kernel(monkeypatch, tmp_path, enabled=False, model=model)
    a = asyncio.run(capture(control, stream=stream))
    experiment = kernel(monkeypatch, tmp_path, enabled=True, model=model)
    b = asyncio.run(capture(experiment, stream=stream))
    assert "truncate_history_thinking" not in a["chat_template_kwargs"]
    assert b["chat_template_kwargs"]["truncate_history_thinking"] is False
    assert a["chat_template_kwargs"]["preserve_thinking"] is True
    assert b["chat_template_kwargs"]["preserve_thinking"] is True
    assert a["messages"] == b["messages"]
    assert a["stream"] == b["stream"] == stream
    assert b["messages"][-2]["reasoning_content"] == history()[-1]["reasoning_content"]
    assert b["messages"][-1]["role"] == "user"
    assert "Prioritize important reasoning" in b["messages"][-1]["content"]
    assert b["tools"] == a["tools"]
    a["chat_template_kwargs"].pop("truncate_history_thinking", None)
    b["chat_template_kwargs"].pop("truncate_history_thinking", None)
    assert a == b


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("model", ["gemma-4-12b-it", "qwen3.6-35b-a3b", "unrelated-model"])
def test_other_models_not_modified(monkeypatch, tmp_path, model, stream):
    k = kernel(monkeypatch, tmp_path, enabled=True, model=model)
    data = asyncio.run(capture(k, stream=stream))
    assert "truncate_history_thinking" not in data.get("chat_template_kwargs", {})


@pytest.mark.parametrize("stream", [False, True])
def test_nemotron_stage1_not_modified(monkeypatch, tmp_path, stream):
    k = kernel(monkeypatch, tmp_path, enabled=True, model="nvidia-nemotron-3.5-lightning-30b-a3b-apex")
    data = asyncio.run(capture(k, stream=stream, stage2=False))
    assert "truncate_history_thinking" not in data["chat_template_kwargs"]
    assert data["messages"][0]["content"] == k.AGENTIC_STAGE1_PROMPT
    assert k.AGENTIC_36_STAGE2_PROMPT == "Generate a detailed summary of why you came to this conclusion."
