"""Stage-2 A1 withholding: isolate backend content, retain canonical A1/R1.

Provider-neutral and transport-neutral. The completed A1 must not leak into
Stage 2 input even though Jack authenticates and commits it separately.
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
SECRET_A1 = "SECRET_FROZEN_A1_DO_NOT_EXPOSE_39271"
R1 = "Decision: rejected temp overwrite because crashes can truncate data; use atomic replace."


def load(monkeypatch, tmp_path, profile):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_WITHHOLD_A1", "1")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_stage2_withheld_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


def history():
    return [
        {"role": "user", "content": "Provide 5 steps for updating JSON."},
        {"role": "assistant", "content": "Tool continuation", "reasoning_content": "Considered direct write. "},
        {"role": "assistant", "content": "Tool intermediate text", "reasoning_content": R1},
        {"role": "assistant", "content": SECRET_A1,
         "reasoning_content": "Verified atomic replace.",
         "_jack_extended_candidate_response": True},
    ]


@pytest.mark.parametrize("profile", ("flash", "balanced", "thorough", "exhaustive"))
def test_stage2_source_preserves_provenance_and_hides_answer(monkeypatch, tmp_path, profile):
    k = load(monkeypatch, tmp_path, profile)
    h = history()
    old = copy.deepcopy(h)
    view = k._agentic_stage2_test_history(h, k.STAGES["extended_reflection"])
    assert h == old
    assert view[0]["content"] == "Provide 5 steps for updating JSON."
    assert SECRET_A1 not in str(view)
    assert view[-1]["role"] == "assistant"
    assert view[-1]["content"] == "[Jack: completed response withheld from memory pass]"
    assert "Tool intermediate text" not in str(view)
    if profile == "flash":
        assert "reasoning_content" not in view[-1]
    else:
        assert "Considered direct write." in view[-1]["reasoning_content"]
        assert R1 in view[-1]["reasoning_content"]
        assert "Verified atomic replace." in view[-1]["reasoning_content"]


@pytest.mark.parametrize("profile", ("flash", "balanced", "thorough", "exhaustive"))
@pytest.mark.parametrize("stream", (False, True))
def test_stage2_wire_does_not_contain_a1_and_seed_unchanged(monkeypatch, tmp_path, profile, stream):
    monkeypatch.setenv("JACK_SEED", "314159")
    k = load(monkeypatch, tmp_path, profile)
    h = history()
    old = copy.deepcopy(h)
    captured = []

    def responder(req):
        captured.append(json.loads(req.content))
        if stream:
            return httpx.Response(
                200, text='data: {"choices":[{"index":0,"delta":{"content":"Memory"},"finish_reason":null}]}\n\n'
                          'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
                          'data: [DONE]\n\n',
                headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "Memory"}, "finish_reason": "stop"}],
            "usage": {}})

    async def run():
        backend = k.OpenAICompatibleBackend(k.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(responder))
        async def model(): return "test-model"
        backend.resolve_model = model
        try:
            args = dict(messages=h, secondary_system="", profile=k.STAGES["extended_reflection"],
                        tools=None, tool_choice="auto")
            if stream:
                async for _ in backend.chat_stream(**args):
                    pass
            else:
                await backend.chat(**args)
        finally:
            await backend._client.aclose()
    asyncio.run(run())
    assert h == old
    assert len(captured) == 1
    wire = captured[0]
    assert wire["seed"] == 314159
    assert SECRET_A1 not in json.dumps(wire)
    assert wire["messages"][-1] == {"role": "user", "content": h[0]["content"]}
    assert len([m for m in wire["messages"] if m["role"] == "user"]) == 1
    model_assistant = [m for m in wire["messages"] if m["role"] == "assistant"]
    assert len(model_assistant) == 1
    assert model_assistant[0]["content"] == "[Jack: completed response withheld from memory pass]"
    if profile != "flash":
        assert R1 in model_assistant[0]["reasoning_content"]
    else:
        assert "reasoning_content" not in model_assistant[0]
    assert "completed response is withheld" in json.dumps(wire["messages"])


def test_stage1_retains_actual_answer_and_is_not_masked(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, "thorough")
    h = history()
    view = k.OpenAICompatibleBackend(k.CFG)._stage_messages_for_profile(
        h, k.STAGES["extended_initial"])
    assert SECRET_A1 in json.dumps(view)


def test_source_does_not_use_recovery_notice_as_new_user_request(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, "thorough")
    h = history()
    h += [
        {"role": "assistant", "content": "Checkpoint",
         "_jack_internal_tool_validation_checkpoint": True},
        {"role": "user", "content": "This is host validation, not user request",
         "_jack_internal_tool_validation_rejection": True},
    ]
    view = k._agentic_stage2_test_history(h, k.STAGES["extended_reflection"])
    assert SECRET_A1 not in str(view)
    assert "host validation" in str(view)
    assert view[0]["role"] == "user"


def test_default_contract_retains_exact_a1(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, "balanced")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_WITHHOLD_A1", "0")
    # Reload, because the setting is read at import time.
    name = "jack_stage2_default_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    default = importlib.util.module_from_spec(spec)
    sys.modules[name] = default
    spec.loader.exec_module(default)
    assert not default.AGENTIC_STAGE2_WITHHOLD_A1
    assert default.AGENTIC_36_STAGE2_PROMPT == default._AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION
    assert default.AGENTIC_STAGE2_MEMORY_TRIGGER == default._AGENTIC_STAGE2_MEMORY_TRIGGER_BASE
    view = default._agentic_stage2_test_history(history(), default.STAGES["extended_reflection"])
    assert view[-1]["content"] == SECRET_A1
