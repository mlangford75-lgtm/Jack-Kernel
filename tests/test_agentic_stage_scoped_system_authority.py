"""Agentic: caller's custom system belongs only to Stage 1.

Tests complete backend payloads in both streaming and nonstreaming, including
Phase-3E cache append and legacy/forced-choice fallback. No live model required.
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
CALLER = "CALLER_SYSTEM_SENTINEL: always roleplay as a clockwork prince."


def load(monkeypatch, tmp_path, *, cache_enabled=True):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT", "1" if cache_enabled else "0")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    name = "jack_agentic_system_boundary_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    import jack_responses_compat
    jack_responses_compat.register(k)
    return k


def capture(k, *, stage, stream, tool_choice="auto"):
    seen = []

    def respond(request):
        seen.append(json.loads(request.content))
        if stream:
            chunks = [
                'data: {"choices":[{"index":0,"delta":{"content":"M"},"finish_reason":null}]}',
                'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}',
                "data: [DONE]",
            ]
            return httpx.Response(200, text="\n\n".join(chunks) + "\n\n",
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "M"},
                         "finish_reason": "stop"}], "usage": {},
        })

    async def run():
        backend = k.OpenAICompatibleBackend(k.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async def model():
            return "test-model"
        backend.resolve_model = model
        kwargs = {
            "messages": [
                {"role": "user", "content": "Make a clock."},
                {"role": "assistant", "content": "Made the clock.",
                 "reasoning_content": "Current R1 obeyed the caller where applicable.",
                 "_jack_extended_candidate_response": True},
            ],
            "secondary_system": CALLER,
            "profile": k.STAGES[stage],
            "tools": [{"type": "function", "function": {
                "name": "read", "parameters": {"type": "object", "properties": {}},
            }}],
            "tool_choice": tool_choice,
        }
        try:
            if stream:
                async for _ in backend.chat_stream(**kwargs):
                    pass
            else:
                await backend.chat(**kwargs)
        finally:
            await backend._client.aclose()
    asyncio.run(run())
    assert len(seen) == 1
    return seen[0]


@pytest.mark.parametrize("stream", [True, False])
@pytest.mark.parametrize("cache_enabled", [True, False])
def test_custom_system_never_governs_agentic_stage2(monkeypatch, tmp_path, stream, cache_enabled):
    k = load(monkeypatch, tmp_path, cache_enabled=cache_enabled)
    stage1 = capture(k, stage="extended_initial", stream=stream)
    stage2 = capture(k, stage="extended_reflection", stream=stream)
    assert CALLER in stage1["messages"][0]["content"]
    assert k.AGENTIC_STAGE1_PROMPT in stage1["messages"][0]["content"]
    assert CALLER not in json.dumps(stage2)
    assert all(m["role"] != "developer" for m in stage2["messages"])
    assert stage2["messages"][-2]["reasoning_content"] == "Current R1 obeyed the caller where applicable."
    assert stage2["messages"][-2]["content"] == "Made the clock."
    if cache_enabled:
        assert stage2["messages"][0]["content"] == k.AGENTIC_STAGE1_PROMPT
        assert stage2["messages"][-1]["content"].startswith(k.AGENTIC_36_STAGE2_PROMPT)
        assert stage2["chat_template_kwargs"]["preserve_thinking"] is True
        assert stage2["tools"] == stage1["tools"]
    else:
        assert stage2["messages"][0]["content"] == k.AGENTIC_36_STAGE2_PROMPT
        assert "tools" not in stage2


@pytest.mark.parametrize("stream", [True, False])
def test_forced_choice_fallback_is_still_isolated(monkeypatch, tmp_path, stream):
    k = load(monkeypatch, tmp_path)
    payload = capture(k, stage="extended_reflection", stream=stream, tool_choice="required")
    assert CALLER not in json.dumps(payload)
    assert payload["messages"][0]["content"] == k.AGENTIC_36_STAGE2_PROMPT
    assert "tools" not in payload


def test_builder_cannot_promote_caller_into_actual_review_stage(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    assert k.build_stage_system_prompt(CALLER, k.STAGES["extended_reflection"], []) == k.AGENTIC_36_STAGE2_PROMPT
    assert CALLER in k.build_stage_system_prompt(CALLER, k.STAGES["extended_initial"], [])


@pytest.mark.parametrize("stream", [True, False])
def test_final_causal_paper_is_still_caller_isolated(monkeypatch, tmp_path, stream):
    monkeypatch.setenv("JACK_AGENTIC_TRANSACTION_LINKS", "1")
    monkeypatch.setenv("JACK_AGENTIC_TASK_ANCHOR", "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_FINAL_PAPER", "1")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_RETENTION_TEST", "baseline")  # legacy causal-paper suffix test
    monkeypatch.setenv("JACK_AGENTIC_DIFFERENTIAL_MEMORY", "0")
    k = load(monkeypatch, tmp_path)
    payload = capture(k, stage="extended_reflection", stream=stream)
    assert CALLER not in payload["messages"][0]["content"]
    assert payload["messages"][0]["content"] == k.AGENTIC_STAGE1_PROMPT
    assert "rough draft" in payload["messages"][-1]["content"]
    assert payload["messages"][-1]["content"].startswith(k.AGENTIC_36_STAGE2_PROMPT)
    assert k.STAGES["extended_reflection"].allow_tools is False


def test_stage2_source_does_not_leak_into_other_modes(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    k = load(monkeypatch, tmp_path)
    # The helper must select the actual profile, not the synthetic cache system
    # profile, and must not mutate the original custom caller string.
    assert k._agentic_caller_system_for_actual_stage(CALLER, k.STAGES["extended_initial"]) == CALLER
    assert k._agentic_caller_system_for_actual_stage(CALLER, k.STAGES["extended_reflection"]) == ""
