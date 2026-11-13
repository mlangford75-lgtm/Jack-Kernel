"""Model-native strongest-reasoning controls are scoped to backend requests.

Muse Glimmer supports reasoning_strength=xhigh rather than Qwen
reasoning_effort=xhigh. Preserve stage messages, tool authority, streaming,
and fallback behavior. No live model inference occurs in these tests.
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


def load(monkeypatch, tmp_path, *, model, extra=""):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    # Exercise the native-reasoning backend contract under explicit Thorough;
    # Balanced is now the runtime default and disables Stage 2 native thinking.
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "thorough")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_BACKEND_MODEL", model)
    monkeypatch.setenv("JACK_BACKEND_MAX_REASONING_OVERRIDES", extra)
    monkeypatch.setenv("JACK_AGENTIC_TRANSACTION_LINKS", "1")
    monkeypatch.setenv("JACK_AGENTIC_TASK_ANCHOR", "0")
    monkeypatch.setenv("JACK_AGENTIC_DIFFERENTIAL_MEMORY", "0")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_native_max_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def task_history():
    return [{"role": "user", "content": "Build a clock"}]


async def payload(k, *, stream, profile="extended_initial"):
    collected = []

    def mock(request):
        collected.append(json.loads(request.content))
        if stream:
            data = "\n\n".join((
                'data: {"choices":[{"index":0,"delta":{"content":"ok"},"finish_reason":null}]}',
                'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}',
                'data: [DONE]',
            )) + "\n\n"
            return httpx.Response(200, text=data, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {},
        })

    backend = k.OpenAICompatibleBackend(k.CFG)
    await backend._client.aclose()
    backend._client = httpx.AsyncClient(transport=httpx.MockTransport(mock))

    async def model():
        return k.CFG.backend_model

    backend.resolve_model = model
    kwargs = {
        "messages": (task_history() + [{"role": "assistant", "content": "Frozen answer",
                            "_jack_extended_candidate_response": True}]
                      if profile == "extended_reflection" else task_history()),
        "secondary_system": "",
        "profile": k.STAGES[profile],
        "tools": [{"type": "function", "function": {
            "name": "read", "description": "Read a file",
            "parameters": {"type": "object", "properties": {}},
        }}],
        "tool_choice": "auto",
    }
    try:
        if stream:
            async for _ in backend.chat_stream(**kwargs):
                pass
        else:
            await backend.chat(**kwargs)
    finally:
        await backend._client.aclose()
    assert len(collected) == 1
    return collected[0]


@pytest.mark.parametrize("stream", [True, False])
@pytest.mark.parametrize("model", [
    "meta/muse-glimmer",
    "meta-models/Muse-Glimmer-30B-GGUF",
    "muse_glimmer_30b_q6",
])
@pytest.mark.parametrize("stage", ["extended_initial", "extended_reflection"])
def test_muse_uses_its_template_max_without_generic_effort(monkeypatch, tmp_path, model, stage, stream):
    k = load(monkeypatch, tmp_path, model=model)
    p = asyncio.run(payload(k, stream=stream, profile=stage))
    assert p["stream"] == stream
    if stage == "extended_initial":
        assert p["chat_template_kwargs"]["reasoning_strength"] == "xhigh"
    else:
        # Thorough Stage 2 now thinks, using the same model-native control.
        assert p["chat_template_kwargs"]["reasoning_strength"] == "xhigh"
    assert "reasoning_effort" not in p["chat_template_kwargs"]
    if stage == "extended_initial":
        assert "reasoning_effort" not in p
    else:
        assert "reasoning_effort" not in p
        assert p["chat_template_kwargs"]["enable_thinking"] is True
    assert p["messages"][0]["content"] == (
        k.AGENTIC_STAGE1_PROMPT if stage == "extended_initial"
        else k.AGENTIC_36_STAGE2_PROMPT
    )
    assert p["messages"][1]["content"] == "Build a clock"
    if stage == "extended_initial":
        assert p["tools"][0]["function"]["name"] == "read"
    else:
        assert "tools" not in p


@pytest.mark.parametrize("stream", [True, False])
def test_unknown_model_falls_back_to_existing_effort(monkeypatch, tmp_path, stream):
    k = load(monkeypatch, tmp_path, model="unknown-local-gguf")
    p = asyncio.run(payload(k, stream=stream))
    assert p["reasoning_effort"] == "xhigh"
    assert p["chat_template_kwargs"]["reasoning_effort"] == "xhigh"
    assert "reasoning_strength" not in p["chat_template_kwargs"]


@pytest.mark.parametrize("stream", [True, False])
def test_explicit_model_override_uses_exact_id(monkeypatch, tmp_path, stream):
    config = json.dumps({"special-custom-id": {"field": "reasoning_strength", "value": "max"}})
    k = load(monkeypatch, tmp_path, model="special-custom-id", extra=config)
    p = asyncio.run(payload(k, stream=stream))
    assert p["chat_template_kwargs"]["reasoning_strength"] == "max"
    assert "reasoning_effort" not in p
    assert "reasoning_effort" not in p["chat_template_kwargs"]


@pytest.mark.parametrize("stream", [True, False])
def test_override_not_applied_to_different_model(monkeypatch, tmp_path, stream):
    config = json.dumps({"other-id": {"field": "reasoning_strength", "value": "max"}})
    k = load(monkeypatch, tmp_path, model="special-custom-id", extra=config)
    p = asyncio.run(payload(k, stream=stream))
    assert p["reasoning_effort"] == "xhigh"
    assert "reasoning_strength" not in p["chat_template_kwargs"]


def test_off_stage_does_not_force_muse_max(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, model="meta/muse-glimmer")
    from dataclasses import replace
    off = replace(k.STAGES["extended_initial"], thinking=False, reasoning_effort=None)
    backend = k.OpenAICompatibleBackend(k.CFG)
    p = {"model": k.CFG.backend_model}
    backend._apply_qwen_controls(p, off)
    assert p.get("reasoning_effort") == "none"
    assert "reasoning_strength" not in p.get("chat_template_kwargs", {})


def test_invalid_override_fails_closed_without_guess(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, model="special-custom-id",
             extra='{"special-custom-id":{"field":"arbitrary","value":"max"}}')
    backend = k.OpenAICompatibleBackend(k.CFG)
    with pytest.raises(RuntimeError, match="Invalid JACK_BACKEND_MAX_REASONING_OVERRIDES"):
        backend._apply_qwen_controls({"model": k.CFG.backend_model}, k.STAGES["extended_initial"])


def test_frozen_prompts_remain_unchanged(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, model="meta/muse-glimmer")
    assert k.AGENTIC_STAGE1_PROMPT.startswith("Reasoning effort is set to xhigh.")
    assert k.AGENTIC_36_STAGE2_PROMPT == k._AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION
