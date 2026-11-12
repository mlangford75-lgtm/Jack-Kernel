"""Unconditional reasoning-derived memory for every Agentic profile.

Mock captures model-facing backend messages; no live model is required.
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
PROFILES = ("flash", "balanced", "thorough", "exhaustive")


def kernel(monkeypatch, tmp_path, *, profile="thorough", legacy_env="0"):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "mock-model")
    # Legacy experiment switches must not change the new branch's policy.
    monkeypatch.setenv("JACK_AGENTIC_REASONING_PRIMARY_EXPERIMENT", legacy_env)
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT", "1")
    monkeypatch.setenv(
        "JACK_AGENTIC_FORENSIC_DB",
        str(tmp_path / (uuid.uuid4().hex + ".sqlite")),
    )
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    name = "reasoning_primary_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def history(reasoning=True):
    h = [
        {"role": "user", "content": "PAST USER: make a recipe"},
        {"role": "assistant", "content": "PAST ANSWER"},
        {"role": "user", "content": "CURRENT REQUEST: create three customers; end with STATE CARD"},
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "Considered A; rejected for duplication.",
            "_jack_internal_tool_exchange": True,
        },
        {
            "role": "assistant",
            "content": "FINAL USER-FACING ANSWER: three customers\nSTATE CARD",
            "reasoning_content": "Chose B. Exact reusable insight: preserve unique relationships.",
            "_jack_extended_candidate_response": True,
        },
    ]
    if not reasoning:
        for msg in h:
            msg.pop("reasoning_content", None)
    return h


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("legacy_env", ("0", "1"))
def test_all_agentic_profiles_get_same_reasoning_only_source(monkeypatch, tmp_path, profile, legacy_env):
    k = kernel(monkeypatch, tmp_path, profile=profile, legacy_env=legacy_env)
    initial = history()
    before = copy.deepcopy(initial)
    projected = k._agentic_stage2_test_history(initial, k.STAGES["extended_reflection"])
    assert initial == before
    assert len(projected) == 1
    assert projected[0]["role"] == "assistant"
    assert projected[0]["content"] == "Reasoning is available for distillation."
    assert projected[0]["reasoning_content"] == (
        "Considered A; rejected for duplication.\n\n"
        "Chose B. Exact reusable insight: preserve unique relationships."
    )
    assert "STATE CARD" not in json.dumps(projected)
    assert "CURRENT REQUEST" not in json.dumps(projected)
    assert "FINAL USER-FACING ANSWER" not in json.dumps(projected)
    assert not hasattr(k, "AGENTIC_REASONING_PRIMARY_EXPERIMENT")
    directive = k.AGENTIC_36_STAGE2_PROMPT
    for forbidden in ("Stage 1", "Stage 2", "Jack", "R1", "A1", "JSON"):
        assert forbidden not in directive
    assert "preceding reasoning" in directive
    assert "decisions" in directive and "corrections" in directive


@pytest.mark.parametrize("profile", PROFILES)
def test_no_reasoning_is_explicit_not_a_legacy_fallback(monkeypatch, tmp_path, profile):
    k = kernel(monkeypatch, tmp_path, profile=profile)
    original = history(reasoning=False)
    projected = k._agentic_stage2_test_history(original, k.STAGES["extended_reflection"])
    assert len(projected) == 1
    assert projected[0]["role"] == "assistant"
    assert projected[0]["content"] == "No reasoning was supplied for distillation."
    assert "reasoning_content" not in projected[0]
    assert "STATE CARD" not in json.dumps(projected)


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("stream", (False, True))
def test_backend_payload_is_restricted_and_model_neutral(monkeypatch, tmp_path, profile, stream):
    k = kernel(monkeypatch, tmp_path, profile=profile)
    snapshots = []
    def responder(req):
        snapshots.append(json.loads(req.content))
        if stream:
            return httpx.Response(
                200,
                text='data: {"choices":[{"index":0,"delta":{"content":"Working knowledge"},"finish_reason":null}]}\n\n'
                     'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
                     "data: [DONE]\n\n",
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "Working knowledge"},
                         "finish_reason": "stop"}],
            "usage": {},
        })
    async def execute():
        backend = k.OpenAICompatibleBackend(k.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(responder))
        async def resolve(): return "mock-model"
        backend.resolve_model = resolve
        try:
            args = dict(messages=history(), secondary_system="CALLER SYSTEM MUST BE ISOLATED",
                        profile=k.STAGES["extended_reflection"], tools=None, tool_choice="auto")
            if stream:
                async for _ in backend.chat_stream(**args):
                    pass
            else:
                await backend.chat(**args)
        finally:
            await backend._client.aclose()
    asyncio.run(execute())
    assert len(snapshots) == 1
    payload = snapshots[0]
    assert [m["role"] for m in payload["messages"]] == [
        "system", "assistant", "user"
    ]
    assert payload["messages"][0]["content"] == k.AGENTIC_36_STAGE2_PROMPT
    assert payload["messages"][1]["content"] == "Reasoning is available for distillation."
    assert "Chose B." in payload["messages"][1]["reasoning_content"]
    assert "STATE CARD" not in json.dumps(payload["messages"])
    assert "CALLER SYSTEM MUST BE ISOLATED" not in json.dumps(payload["messages"])
    assert payload["messages"][2]["content"].startswith("Preserve the useful working knowledge")
    assert "tools" not in payload and "tool_choice" not in payload


def test_frozen_answer_required_and_canonical_history_untouched(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path)
    original = history()
    before = copy.deepcopy(original)
    k._agentic_stage2_test_history(original, k.STAGES["extended_reflection"])
    assert original == before
    with pytest.raises(k.HTTPException) as error:
        k._agentic_stage2_test_history(original[:-1], k.STAGES["extended_reflection"])
    assert error.value.status_code == 409


def test_other_stage_does_not_see_modified_history(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path)
    original = history()
    assert k._agentic_stage2_test_history(
        original, k.STAGES["extended_initial"]
    ) is original
