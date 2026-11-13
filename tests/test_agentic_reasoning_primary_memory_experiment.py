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
    assert [m["role"] for m in projected] == ["user", "assistant"]
    assert projected[0]["content"] == "CURRENT REQUEST: create three customers; end with STATE CARD"
    assert projected[1]["content"] == "FINAL USER-FACING ANSWER: three customers\nSTATE CARD"
    assert projected[1]["reasoning_content"] == (
        "Considered A; rejected for duplication.\n\n"
        "Chose B. Exact reusable insight: preserve unique relationships."
    )
    assert "PAST USER" not in json.dumps(projected)
    assert "PAST ANSWER" not in json.dumps(projected)
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
    assert [m["role"] for m in projected] == ["user", "assistant"]
    assert projected[1]["content"].endswith("STATE CARD")
    assert "reasoning_content" not in projected[1]
    assert "PAST USER" not in json.dumps(projected)


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
        "system", "user", "assistant", "user"
    ]
    assert payload["messages"][0]["content"] == k.AGENTIC_36_STAGE2_PROMPT
    assert payload["messages"][1]["content"] == "CURRENT REQUEST: create three customers; end with STATE CARD"
    assert "Chose B." in payload["messages"][2]["reasoning_content"]
    assert payload["messages"][2]["content"].endswith("STATE CARD")
    assert "PAST USER" not in json.dumps(payload["messages"])
    assert "CALLER SYSTEM MUST BE ISOLATED" not in json.dumps(payload["messages"])
    assert payload["messages"][3]["content"] == "Proceed."
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


def test_owned_stage2_sees_authentic_work_and_memory_attempt_ids(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path)
    initial = history()
    source_text = initial[2]["content"]
    answer_text = initial[-1]["content"]
    work_id = k._agentic_begin_turn(initial, fresh=True)
    assert work_id.startswith("jack-turn-")
    k._agentic_forensic_freeze(initial, answer_text)
    k._agentic_forensic_start_stage2(initial)
    record = k._agentic_forensic_turn(initial)
    assert record.turn_id == work_id
    assert record.stage2_attempt_id
    before = copy.deepcopy(initial)
    stage2_source = k._agentic_stage2_test_history(initial, k.STAGES["extended_reflection"])
    assert initial == before
    assert [m["role"] for m in stage2_source] == ["system", "user", "assistant"]
    binding = stage2_source[0]["content"]
    assert work_id in binding
    assert record.stage2_attempt_id in binding
    assert stage2_source[1]["content"] == source_text
    assert stage2_source[2]["content"] == answer_text
    assert "Chose B." in stage2_source[2]["reasoning_content"]
    projected = k.OpenAICompatibleBackend(k.CFG)._stage_messages_for_profile(
        stage2_source, k.STAGES["extended_reflection"]
    )
    assert work_id in projected[0]["content"]
    assert record.stage2_attempt_id in projected[0]["content"]
    assert all(not any(key.startswith("_jack_") for key in m) for m in projected)
    assert initial[2]["content"] == source_text


def test_stage1_work_id_is_visible_without_changing_original_request(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path, profile="exhaustive")
    original = history()
    request = original[2]["content"]
    work_id = k._agentic_begin_turn(original, fresh=True)
    initial_profile = k.STAGES["extended_initial"]
    projected = k.OpenAICompatibleBackend(k.CFG)._stage_messages_for_profile(
        original, initial_profile
    )
    assert projected[2]["content"] == request + "\nWork ID: " + work_id
    assert original[2]["content"] == request
    assert "_jack_agentic_turn_id" not in projected[2]


def test_work_id_survives_tool_resume_and_exhaustive_same_turn(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path, profile="exhaustive")
    h = history()
    work_id = k._agentic_begin_turn(h, fresh=True)
    k._agentic_turn_status(h, "awaiting_tool")
    assert k._agentic_begin_turn(h, fresh=False) == work_id
    h.insert(-1, {"role": "tool", "tool_call_id": "call-1", "content": "write succeeded"})
    stage1 = k.OpenAICompatibleBackend(k.CFG)._stage_messages_for_profile(
        h, k.STAGES["extended_initial"]
    )
    assert work_id in stage1[2]["content"]
    assert h[2]["content"] == "CURRENT REQUEST: create three customers; end with STATE CARD"


def test_compaction_retires_both_reasoning_traces_preserving_tool_history(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path)
    h = [
        {"role": "user", "content": "write file"},
        {"role": "assistant", "content": "", "reasoning_content": "R1 secret",
         "tool_calls": [{"id": "x", "type": "function",
                         "function": {"name": "write", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "x", "content": "write returned success"},
        {"role": "assistant", "content": "Completed file", "reasoning_content": "R2 secret"},
        {"role": "user", "content": "inspect file"},
    ]
    before = copy.deepcopy(h)
    compact = k._compact_agentic_completed_capsules(h)
    assert h == before
    assert compact is not None
    assert "R1 secret" not in json.dumps(compact)
    assert "R2 secret" not in json.dumps(compact)
    assert any(m.get("tool_calls") == h[1]["tool_calls"] for m in compact)
    assert any(m.get("role") == "tool" and m.get("content") == "write returned success" for m in compact)
    assert any(m.get("content") == "Completed file" for m in compact)
