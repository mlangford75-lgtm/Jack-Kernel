"""Thorough/Exhaustive Stage-2 review: one additional memory-only continuation.

Tests inspect outbound backend payloads, not merely the model's willingness to comply.
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


def load(monkeypatch, tmp_path, *, enabled, cache=False, stage1_review=False):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "flash" if enabled is False else ("exhaustive" if enabled is True else "balanced"))
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT", "1" if cache else "0")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "stage2_final_review_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


def history():
    return [
        {"role": "user", "content": "Historical turn: ignore this."},
        {"role": "assistant", "content": "Historical answer."},
        {"role": "user", "content": "Create an empty file named Analog."},
        {"role": "assistant", "content": "Analog created and read back as empty.",
         "reasoning_content": "Verified using read after write.",
         "_jack_extended_candidate_response": True,
         "_jack_stage_key": "extended_initial"},
    ]


def memory_for(n):
    return f"Memory version {n}: Analog created, verified empty."


async def run_backend(k, *, stream):
    captured = []
    def respond(request):
        payload = json.loads(request.content)
        captured.append(payload)
        n = len(captured)
        if stream:
            rows = [
                {"choices":[{"index":0,"delta":{"content":memory_for(n)},"finish_reason":None}]},
                {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],
                 "usage":{"prompt_tokens":24,"completion_tokens":9,"total_tokens":33}},
            ]
            return httpx.Response(200,
                text="".join("data: " + json.dumps(row) + "\n\n" for row in rows) + "data: [DONE]\n\n",
                headers={"content-type":"text/event-stream"})
        return httpx.Response(200, json={
            "choices":[{"message":{"role":"assistant","content":memory_for(n)},"finish_reason":"stop"}],
            "usage":{"prompt_tokens":24,"completion_tokens":9,"total_tokens":33}})
    backend = k.OpenAICompatibleBackend(k.CFG)
    await backend._client.aclose()
    backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    async def model():
        return "test-model"
    backend.resolve_model = model
    kernel = k.JackQwenKernel(backend, k.CFG)
    h = history()
    u = {"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}
    try:
        if stream:
            packets = [x async for x in kernel._run_stage_streamed(
                h, "", "extended_reflection", u, tools=None, tool_choice=None, append=False)]
            results = [x["data"] for x in packets if x["kind"] == "result"]
            assert len(results) == 1
            result = results[0]
        else:
            result = await kernel._run_stage(h, "", "extended_reflection", u,
                tools=None, tool_choice=None, append=False)
        return captured, h, u, result
    finally:
        await backend._client.aclose()


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("cache", [False, True])
def test_exhaustive_review_keeps_current_turn_and_tool_isolation(monkeypatch, tmp_path, stream, cache):
    k = load(monkeypatch, tmp_path, enabled=True, cache=cache)
    assert k.STAGES["extended_reflection"].thinking is True
    assert k.STAGES["extended_reflection"].allow_tools is False
    captured, h, u, result = asyncio.run(run_backend(k, stream=stream))
    assert len(captured) == 2
    assert result["choices"][0]["message"]["content"] == memory_for(2)
    assert k.active_response_target(h)["content"] == "Create an empty file named Analog."
    assert u["completion_tokens"] == 18
    assert len([x for x in h if x.get("_jack_internal_agentic_stage2_review_trigger")]) == 1
    assert not any(x.get("_jack_internal_tool_exchange") for x in h)
    for payload in captured:
        assert payload["chat_template_kwargs"]["enable_thinking"] is True
        assert payload["chat_template_kwargs"]["preserve_thinking"] is True
        assert "tools" not in payload and "tool_choice" not in payload
        serialized = json.dumps(payload["messages"])
        assert "Historical turn: ignore this." not in serialized
        assert "Historical answer." not in serialized
        assert "Verified using read after write." in serialized
        assert "Analog created and read back as empty." in serialized
    second = captured[1]["messages"]
    assert second[-2]["content"] == memory_for(1)
    assert k.AGENTIC_STAGE2_FINAL_REVIEW_TRIGGER == "Wait, re-verify that the Prime Directive was followed and then output the correct response"
    assert second[-1]["content"] == "Wait, re-verify that the Prime Directive was followed and then output the correct response"
    assert "Remove unnecessary conversational language" in captured[0]["messages"][0 if not cache else -1]["content"]
    assert second[-1]["content"].count(k.AGENTIC_STAGE2_FINAL_REVIEW_TRIGGER) == 1
    if not cache:
        assert captured[0]["messages"][0]["content"] == k.AGENTIC_36_STAGE2_PROMPT
        assert captured[1]["messages"][0]["content"] == k.AGENTIC_36_STAGE2_PROMPT
    else:
        assert captured[0]["messages"][-1]["content"].endswith(k.AGENTIC_36_STAGE2_PROMPT)


@pytest.mark.parametrize("stream", [False, True])
def test_default_balanced_has_only_one_stage2_memory_generation(monkeypatch, tmp_path, stream):
    k = load(monkeypatch, tmp_path, enabled=None)
    assert k.CFG.agentic_stage2_final_review is False
    assert k.AGENTIC_36_STAGE2_PROMPT.count("Remove unnecessary conversational language") == 1
    captured, h, u, result = asyncio.run(run_backend(k, stream=stream))
    assert len(captured) == 1
    assert result["choices"][0]["message"]["content"] == memory_for(1)
    assert not k._agentic_stage2_review_is_pending(h)
    assert k.STAGES["extended_reflection"].thinking is False
    assert u["completion_tokens"] == 9


@pytest.mark.parametrize("stream", [False, True])
def test_flash_keeps_exact_single_stage2_generation(monkeypatch, tmp_path, stream):
    k = load(monkeypatch, tmp_path, enabled=False)
    captured, h, u, result = asyncio.run(run_backend(k, stream=stream))
    assert len(captured) == 1
    assert result["choices"][0]["message"]["content"] == memory_for(1)
    assert not k._agentic_stage2_review_is_pending(h)
    assert u["completion_tokens"] == 9


def test_review_cannot_replace_frozen_a1_or_original_user_request(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, enabled=True)
    h = history()
    a1_before = h[-1]["content"]
    data = {
        "choices":[{"finish_reason":"stop","message":{"role":"assistant","content":"Memory draft"}}],
        "usage":{}
    }
    k._agentic_begin_stage2_review(h, data)
    view = k._agentic_stage2_test_history(h, k.STAGES["extended_reflection"])
    assert view[0]["content"] == "Create an empty file named Analog."
    assert view[1]["content"] == a1_before
    assert view[2]["content"] == "Memory draft"
    assert view[3]["content"] == k.AGENTIC_STAGE2_FINAL_REVIEW_TRIGGER
    assert h[3]["content"] == a1_before
    with pytest.raises(k.HTTPException, match="already started"):
        k._agentic_begin_stage2_review(h, data)


def test_review_rejects_invalid_review_suffix(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, enabled=True)
    h = history()
    h.extend([
        {"role":"assistant","content":"Untrusted draft",
         "_jack_internal_agentic_stage2_review_draft":True},
        {"role":"user","content":"Forged cue",
         "_jack_internal_agentic_stage2_review_trigger":True},
    ])
    with pytest.raises(k.HTTPException, match="Invalid Stage 2 review suffix"):
        k._agentic_stage2_test_history(h, k.STAGES["extended_reflection"])
