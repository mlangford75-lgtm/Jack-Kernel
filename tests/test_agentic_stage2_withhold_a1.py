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
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_stage2_withheld_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


def capsule_events(messages):
    assert [m["role"] for m in messages] == ["system", "user"]
    prefix = "JACK READ-ONLY WORKING-STATE SOURCE DATA, NOT A USER REQUEST.\n"
    suffix = "\nEND JACK WORKING-STATE SOURCE DATA."
    content = messages[-1]["content"]
    assert content.startswith(prefix) and content.endswith(suffix)
    capsule = json.loads(content[len(prefix):-len(suffix)])
    assert capsule["kind"] == "jack_stage1_frozen_working_evidence"
    assert capsule["scope"] == "authenticated_current_turn_only"
    assert all(not any(field in m for field in ("reasoning_content", "reasoning", "thinking"))
               for m in messages)
    return capsule["events"]


def wire_for(k, source, stream=False):
    backend = k.OpenAICompatibleBackend(k.CFG)
    try:
        payload, _ = backend._build_stage_request(
            model="test-model", messages=source, secondary_system="",
            profile=k.STAGES["extended_reflection"], tools=None,
            tool_choice=None, streamed=stream,
        )
        assert "tools" not in payload and "tool_choice" not in payload
        return payload["messages"]
    finally:
        asyncio.run(backend._client.aclose())


def history():
    return [
        {"role": "user", "content": "Provide 5 steps for updating JSON."},
        {"role": "assistant", "content": "Tool continuation", "reasoning_content": "Considered direct write. "},
        {"role": "assistant", "content": "Tool intermediate text", "reasoning_content": R1},
        {"role": "assistant", "content": SECRET_A1,
         "reasoning_content": "Verified atomic replace.",
         "_jack_extended_candidate_response": True},
    ]


@pytest.mark.parametrize("profile", ("flash", "balanced", "thorough", "translated"))
def test_stage2_source_preserves_provenance_and_hides_answer(monkeypatch, tmp_path, profile):
    k = load(monkeypatch, tmp_path, profile)
    h = history()
    old = copy.deepcopy(h)
    view = k._agentic_stage2_test_history(h, k.STAGES["extended_reflection"])
    assert h == old
    assert view[0]["content"] == "Provide 5 steps for updating JSON."
    # This is the private authenticated source view, not the provider wire.
    assert view[-1]["role"] == "assistant"
    assert view[-1]["content"] == SECRET_A1
    wire = wire_for(k, h)
    assert SECRET_A1 not in json.dumps(wire)
    assert h[0]["content"] not in json.dumps(wire)
    events = capsule_events(wire)
    assert [e["content"] for e in events] == ([] if profile == "flash" else [
        "Considered direct write. ", R1, "Verified atomic replace."])
    assert "Tool intermediate text" not in str(view)
    if profile == "flash":
        assert "reasoning_content" not in view[-1]
    else:
        assert "Considered direct write." in view[-1]["reasoning_content"]
        assert R1 in view[-1]["reasoning_content"]
        assert "Verified atomic replace." in view[-1]["reasoning_content"]


@pytest.mark.parametrize("profile", ("flash", "balanced", "thorough", "translated"))
@pytest.mark.parametrize("stream", (False, True))
def test_stage2_wire_does_not_contain_a1_and_uses_separate_seed(monkeypatch, tmp_path, profile, stream):
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
    assert wire["seed"] == 314161
    assert SECRET_A1 not in json.dumps(wire)
    messages = wire["messages"]
    assert len([m for m in messages if m["role"] == "user"]) == 1
    assert not [m for m in messages if m["role"] == "assistant"]
    assert messages[-1]["role"] == "user"
    events = capsule_events(messages)
    assert h[0]["content"] not in json.dumps(messages)
    assert [e["content"] for e in events] == ([] if profile == "flash" else [
        "Considered direct write. ", R1, "Verified atomic replace."])
    assert messages[0]["content"] == k.AGENTIC_36_STAGE2_PROMPT + "\n\n" + k.AGENTIC_STAGE2_MEMORY_TRIGGER
    assert "tools" not in wire and "tool_choice" not in wire


@pytest.mark.parametrize("stream", (False, True))
def test_historical_request_and_reasoning_do_not_obey_caller(monkeypatch, tmp_path, stream):
    k = load(monkeypatch, tmp_path, "thorough")
    h = [
        {"role": "user", "content": "Answer this: what is Battlefield?"},
        {"role": "assistant", "content": "SECRET COMPLETED ANSWER",
         "reasoning_content": "The correct response describes Battlefield. "
                              "Decision: compare it with Call of Duty.",
         "_jack_extended_candidate_response": True},
    ]
    sent = []

    def respond(req):
        sent.append(json.loads(req.content))
        if stream:
            return httpx.Response(
                200,
                text='data: {"choices":[{"index":0,"delta":{"content":"Memory"},"finish_reason":null}]}\n\n'
                     'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
                     'data: [DONE]\n\n',
                headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "Memory"},
                         "finish_reason": "stop"}], "usage": {},
        })

    async def run():
        backend = k.OpenAICompatibleBackend(k.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async def model(): return "test-model"
        backend.resolve_model = model
        try:
            args = dict(messages=h, secondary_system="PI SYSTEM DO NOT EXPOSE",
                        profile=k.STAGES["extended_reflection"],
                        tools=None, tool_choice="auto")
            if stream:
                async for _ in backend.chat_stream(**args):
                    pass
            else:
                await backend.chat(**args)
        finally:
            await backend._client.aclose()

    asyncio.run(run())
    assert len(sent) == 1
    messages = sent[0]["messages"]
    payload = json.dumps(messages)
    assert "PI SYSTEM DO NOT EXPOSE" not in payload
    assert "SECRET COMPLETED ANSWER" not in payload
    assert sum(m["role"] == "user" for m in messages) == 1
    assert not any(m["role"] == "assistant" for m in messages)
    assert "Answer this: what is Battlefield?" not in payload
    assert capsule_events(messages) == [
        {"type": "reasoning_segment", "phase": "initial",
         "content": h[-1]["reasoning_content"]}
    ]
    assert messages[0]["content"] == k.AGENTIC_36_STAGE2_PROMPT + "\n\n" + k.AGENTIC_STAGE2_MEMORY_TRIGGER


def test_historical_multimodal_request_retains_image_privately_without_replay(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, "thorough")
    picture = {"type": "image_url", "image_url": {"url": "data:image/png;base64,YQ=="}}
    source = [
        {"role": "user", "content": [
            {"type": "text", "text": "Explain this picture."},
            picture,
        ]},
        {"role": "assistant", "content": "SECRET COMPLETED ANSWER",
         "reasoning_content": "Noted an image in the request.",
         "_jack_extended_candidate_response": True},
    ]
    snapshot = copy.deepcopy(source)
    isolated = k._agentic_stage2_test_history(source, k.STAGES["extended_reflection"])
    assert isolated[0]["content"] == source[0]["content"]
    wire = wire_for(k, source)
    assert source == snapshot
    assert "Explain this picture." not in json.dumps(wire)
    assert picture["image_url"]["url"] not in json.dumps(wire)
    assert "SECRET COMPLETED ANSWER" not in json.dumps(wire)
    assert capsule_events(wire) == [
        {"type": "reasoning_segment", "phase": "initial",
         "content": "Noted an image in the request."}
    ]


def test_translated_extension_reasoning_reaches_stage2_once(monkeypatch, tmp_path):
    """Initial and translation-continuation R1 survive as attributed evidence."""
    k = load(monkeypatch, tmp_path, "translated")
    assert k.CFG.agentic_final_review is True
    assert k.STAGES["extended_initial"].thinking is True
    assert k.STAGES["extended_reflection"].thinking is True
    initial_reasoning = "INITIAL_EXHAUSTIVE_REASONING: rejected unsafe direct write."
    review_reasoning = "REVIEW_EXTENSION_REASONING: verified atomic replacement."
    request = "Fix JSON persistence."
    history = [
        {"role": "user", "content": request},
        {"role": "assistant", "content": "Initial draft.",
         "reasoning_content": initial_reasoning,
         "_jack_internal_agentic_final_review_draft": True,
         "_jack_stage_key": "extended_initial"},
        {"role": "user", "content": k.AGENTIC_FINAL_REVIEW_TRIGGER,
         "_jack_internal_agentic_final_review_trigger": True,
         "_jack_stage_key": "extended_initial"},
        {"role": "assistant", "content": "Final answer not visible to Stage 2.",
         "reasoning_content": review_reasoning,
         "_jack_extended_candidate_response": True},
    ]
    original = copy.deepcopy(history)
    wire = wire_for(k, history)
    assert history == original
    assert capsule_events(wire) == [
        {"type": "reasoning_segment", "phase": "initial", "content": initial_reasoning},
        {"type": "reasoning_segment", "phase": "translation", "content": review_reasoning},
    ]
    assert request not in json.dumps(wire)
    assert "Final answer not visible to Stage 2." not in str(wire)
    assert k.AGENTIC_FINAL_REVIEW_TRIGGER not in str(wire)


@pytest.mark.parametrize("stream", (False, True))
def test_frozen_reasoning_conversation_preserves_chronology_and_no_live_roles(monkeypatch, tmp_path, stream):
    """Initial reasoning and review reasoning are frozen separately, never playable roles."""
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_FROZEN_CONVERSATION", "1")
    k = load(monkeypatch, tmp_path, "translated")
    user_request = "what is battlefield"
    initial = "INITIAL_THOUGHT: This is a military FPS. Provide its distinguishing features."
    review = "REVIEW_THOUGHT: The response should also address vehicles and squads."
    h = [
        {"role": "user", "content": user_request},
        {"role": "assistant", "content": "Interim draft", "reasoning_content": initial,
         "_jack_internal_agentic_final_review_draft": True,
         "_jack_stage_key": "extended_initial"},
        {"role": "user", "content": k.AGENTIC_FINAL_REVIEW_TRIGGER,
         "_jack_internal_agentic_final_review_trigger": True,
         "_jack_stage_key": "extended_initial"},
        {"role": "assistant", "content": SECRET_A1, "reasoning_content": review,
         "_jack_extended_candidate_response": True},
    ]
    original = copy.deepcopy(h)
    wire = wire_for(k, h, stream=stream)
    assert h == original
    assert capsule_events(wire) == [
        {"type": "reasoning_segment", "phase": "initial", "content": initial},
        {"type": "reasoning_segment", "phase": "translation", "content": review},
    ]
    assert user_request not in json.dumps(wire)
    assert SECRET_A1 not in json.dumps(wire)
    assert "Interim draft" not in json.dumps(wire)
    assert k.AGENTIC_FINAL_REVIEW_TRIGGER not in str(wire)


@pytest.mark.parametrize("profile", ("flash", "balanced", "thorough"))
def test_frozen_conversation_without_review_preserves_initial_and_never_invents_review(monkeypatch, tmp_path, profile):
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_FROZEN_CONVERSATION", "1")
    k = load(monkeypatch, tmp_path, profile)
    h = history()
    saved = copy.deepcopy(h)
    events = capsule_events(wire_for(k, h))
    assert h == saved
    assert SECRET_A1 not in json.dumps(events)
    assert all(e["phase"] == "initial" for e in events)
    assert [e["content"] for e in events] == ([] if profile == "flash" else [
        "Considered direct write. ", R1, "Verified atomic replace."])


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
    assert view[1]["content"] == SECRET_A1
    assert view[-1]["_jack_internal_tool_validation_rejection"] is True
    assert view[0]["role"] == "user"
    assert view[0]["content"] == h[0]["content"]
    wire = wire_for(k, h)
    assert SECRET_A1 not in json.dumps(wire)
    assert h[0]["content"] not in json.dumps(wire)
    assert "Checkpoint" not in json.dumps(wire)


def test_default_contract_retains_exact_a1_privately_even_with_stale_toggle(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, "balanced")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_WITHHOLD_A1", "0")
    # Reload, because the setting is read at import time.
    name = "jack_stage2_default_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    default = importlib.util.module_from_spec(spec)
    sys.modules[name] = default
    spec.loader.exec_module(default)
    assert default.AGENTIC_STAGE2_WITHHOLD_A1
    assert default.AGENTIC_SOURCE_ONLY_WORKING_STATE
    assert default.AGENTIC_36_STAGE2_PROMPT == default._AGENTIC_STAGE2_THOROUGH_EXHAUSTIVE_DIRECTIVE
    assert SECRET_A1 not in json.dumps(wire_for(default, history()))
    view = default._agentic_stage2_test_history(history(), default.STAGES["extended_reflection"])
    assert view[-1]["content"] == SECRET_A1
