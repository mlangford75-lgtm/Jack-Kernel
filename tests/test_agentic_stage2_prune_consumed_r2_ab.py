"""A/B: caller system isolation + Stage-2-only inherited-R2 pruning.

Run: python -m pytest -q tests/test_agentic_stage2_prune_consumed_r2_ab.py
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
CUSTOM = "RETROSPECTIVE_BLOCKED_BY_CUSTOM_SYSTEM"
OLD_R2 = "PREVIOUS_NATIVE_R2_UNIQUE_SENTINEL"
CURRENT_R1 = "CURRENT_NATIVE_R1_UNIQUE_SENTINEL"


def load(monkeypatch, tmp_path, *, early_prune, cache_enabled):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "Local Agentic (Preserve Thinking)")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_PRUNE_CONSUMED_R2_AB", "1" if early_prune else "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT", "1" if cache_enabled else "0")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    name = "jack_prune_r2_ab_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


def history():
    return [
        {"role": "user", "content": "prior user request"},
        {"role": "assistant", "content": "prior clean memory",
         "reasoning_content": OLD_R2, "reasoning": OLD_R2,
         "_jack_agentic_one_hop_r2": True},
        {"role": "user", "content": "current user request"},
        {"role": "assistant", "content": "exact frozen current A1",
         "reasoning_content": CURRENT_R1, "reasoning": CURRENT_R1,
         "_jack_stage_key": "extended_initial"},
    ]


async def payload(k, messages, profile, stream):
    seen = []
    def respond(request):
        seen.append(json.loads(request.content))
        if stream:
            return httpx.Response(
                200,
                text=('data: {"choices":[{"index":0,"delta":{"content":"memory"},"finish_reason":null}]}\n\n'
                      'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
                      'data: [DONE]\n\n'),
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "memory"},
                         "finish_reason": "stop"}],
            "usage": {},
        })
    backend = k.OpenAICompatibleBackend(k.CFG)
    await backend._client.aclose()
    backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    async def model():
        return "test-model"
    backend.resolve_model = model
    tools = [{"type": "function", "function": {
        "name": "read", "parameters": {"type": "object", "properties": {}},
    }}]
    try:
        kwargs = dict(
            messages=messages, secondary_system=CUSTOM,
            profile=k.STAGES[profile], tools=tools, tool_choice="auto",
        )
        if stream:
            async for _ in backend.chat_stream(**kwargs):
                pass
        else:
            await backend.chat(**kwargs)
    finally:
        await backend._client.aclose()
    assert len(seen) == 1
    return seen[0]


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("cache_enabled", [False, True])
@pytest.mark.parametrize("early_prune", [False, True])
def test_stage2_prunes_only_consumed_r2_in_provider_view(
        monkeypatch, tmp_path, stream, cache_enabled, early_prune):
    async def exercise():
        k = load(monkeypatch, tmp_path, early_prune=early_prune, cache_enabled=cache_enabled)
        h = history()
        before = json.dumps(h, sort_keys=True)
        stage1 = await payload(k, h, "extended_initial", stream)
        stage2 = await payload(k, h, "extended_reflection", stream)
        text1 = json.dumps(stage1)
        text2 = json.dumps(stage2)
        assert CUSTOM in text1 and CUSTOM not in text2
        assert OLD_R2 in text1
        assert (OLD_R2 in text2) is (not early_prune)
        assert CURRENT_R1 in text2
        assert "prior clean memory" in text2
        assert "exact frozen current A1" in text2
        assert json.dumps(h, sort_keys=True) == before
        assert all(not any(str(key).startswith("_jack_") for key in msg) for msg in stage2["messages"])
        if cache_enabled:
            assert stage2["messages"][0]["content"] == k.AGENTIC_STAGE1_PROMPT
            assert stage2["messages"][-1]["content"].startswith(k.AGENTIC_36_STAGE2_PROMPT)
            assert stage2["tools"] == stage1["tools"]
        else:
            assert stage2["messages"][0]["content"] == k.AGENTIC_36_STAGE2_PROMPT
            assert "tools" not in stage2
    asyncio.run(exercise())


@pytest.mark.parametrize("stream", [False, True])
def test_inherited_r2_retirement_preserves_current_r1_and_future_bridge(
        monkeypatch, tmp_path, stream):
    k = load(monkeypatch, tmp_path, early_prune=True, cache_enabled=True)
    h = history()
    projected = k.KERNEL.backend._stage_messages_for_profile(
        h, k.STAGES["extended_reflection"]
    )
    assert OLD_R2 not in json.dumps(projected)
    assert CURRENT_R1 in json.dumps(projected)
    assert h[1]["reasoning_content"] == OLD_R2
    k._agentic_retire_consumed_one_hop(h)
    assert "reasoning_content" not in h[1]
    assert "reasoning" not in h[1]
    assert h[-1]["reasoning_content"] == CURRENT_R1
    new_r2 = k._agentic_extract_one_hop_stage2_reasoning({
        "role": "assistant",
        "reasoning_content": (
            "===== JACK AGENTIC NATIVE PASS 2 =====\n"
            "[NATIVE REASONING]\nNEW_STAGE2_R2_UNIQUE\n"
            "[STAGE 2 REASONING DISTILLATION]\nclean memory"
        ),
    })
    assert new_r2 == "NEW_STAGE2_R2_UNIQUE"
