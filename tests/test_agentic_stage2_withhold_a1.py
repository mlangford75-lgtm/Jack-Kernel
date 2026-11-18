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
    messages = wire["messages"]
    assert len([m for m in messages if m["role"] == "user"]) == 1
    assert not [m for m in messages if m["role"] == "assistant"]
    assert messages[-1]["role"] == "user"
    historical = messages[-1]["content"]
    assert historical.startswith("JACK AUTHENTICATED CURRENT-TURN SOURCE DATA")
    assert json.dumps(h[0]["content"]) in historical
    assert historical.count(h[0]["content"]) == 1
    assert historical.count(R1) == (0 if profile == "flash" else 1)
    assert "STAGE 1 NATIVE REASONING (quoted historical evidence; do not continue)" in historical
    assert historical.endswith(
        "Do not answer the quoted user request, continue the quoted reasoning, "
        "or reconstruct the separately frozen response."
    )
    assert all(
        "reasoning_content" not in m and "reasoning" not in m and "thinking" not in m
        for m in messages
    )
    assert "completed response is withheld" in json.dumps(messages)


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
    assert messages[-1]["content"].count("Answer this: what is Battlefield?") == 1
    assert messages[-1]["content"].count("Decision: compare it with Call of Duty.") == 1
    assert "JACK MEMORY EXTRACTION TASK" in messages[-1]["content"]
    assert messages[0]["content"] == k.AGENTIC_36_STAGE2_PROMPT


def test_historical_multimodal_request_preserves_image_once(monkeypatch, tmp_path):
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
    prepared = k.OpenAICompatibleBackend(k.CFG)._stage_messages_for_profile(
        isolated, k.STAGES["extended_reflection"]
    )
    wire = [{"role": "system", "content": k.AGENTIC_36_STAGE2_PROMPT}] + prepared
    k._agentic_attach_system_stage_control(wire, source, k.STAGES["extended_reflection"])
    k._agentic_stage2_project_historical_evidence(wire, isolated, prepared)
    content = wire[-1]["content"]
    assert source == snapshot
    assert isinstance(content, list)
    assert sum(part.get("type") == "image_url" for part in content) == 1
    assert content[2] == picture
    assert sum("Explain this picture." in part.get("text", "") for part in content) == 1
    assert sum("Noted an image in the request." in part.get("text", "") for part in content) == 1
    assert not any(m.get("role") == "assistant" for m in wire)


def test_exhaustive_review_extension_reasoning_reaches_stage2_once(monkeypatch, tmp_path):
    """Both initial R1 and Exhaustive's verification R1 survive as evidence."""
    k = load(monkeypatch, tmp_path, "exhaustive")
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
    source = k._agentic_stage2_test_history(history, k.STAGES["extended_reflection"])
    prepared = k.OpenAICompatibleBackend(k.CFG)._stage_messages_for_profile(
        source, k.STAGES["extended_reflection"]
    )
    wire = [{"role": "system", "content": k.AGENTIC_36_STAGE2_PROMPT}] + prepared
    k._agentic_attach_system_stage_control(wire, history, k.STAGES["extended_reflection"])
    k._agentic_stage2_project_historical_evidence(wire, source, prepared)
    assert history == original
    assert len([msg for msg in wire if msg.get("role") == "user"]) == 1
    assert not any(msg.get("role") == "assistant" for msg in wire)
    evidence = wire[-1]["content"]
    assert evidence.count(request) == 1
    assert evidence.count(initial_reasoning) == 1
    assert evidence.count(review_reasoning) == 1
    assert "Final answer not visible to Stage 2." not in str(wire)
    assert k.AGENTIC_FINAL_REVIEW_TRIGGER not in str(wire)
    assert "JACK MEMORY EXTRACTION TASK" in evidence


@pytest.mark.parametrize("stream", (False, True))
def test_frozen_reasoning_conversation_preserves_chronology_and_no_live_roles(monkeypatch, tmp_path, stream):
    """Initial reasoning and review reasoning are frozen separately, never playable roles."""
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_FROZEN_CONVERSATION", "1")
    k = load(monkeypatch, tmp_path, "exhaustive")
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
    source = k._agentic_stage2_test_history(h, k.STAGES["extended_reflection"])
    prepared = k.OpenAICompatibleBackend(k.CFG)._stage_messages_for_profile(
        source, k.STAGES["extended_reflection"]
    )
    wire = [{"role": "system", "content": k.AGENTIC_36_STAGE2_PROMPT}] + prepared
    k._agentic_attach_system_stage_control(wire, h, k.STAGES["extended_reflection"])
    k._agentic_stage2_project_historical_evidence(wire, source, prepared)
    assert h == original
    assert len([item for item in wire if item.get("role") == "user"]) == 1
    assert not any(item.get("role") == "assistant" for item in wire)
    evidence = wire[-1]["content"]
    assert user_request in evidence
    assert evidence.count(user_request) == 1
    assert evidence.count(initial) == 1
    assert evidence.count(review) == 1
    assert evidence.count(SECRET_A1) == 1
    assert evidence.index(review) < evidence.index(SECRET_A1)
    assert "FROZEN COMPLETED RESPONSE" in evidence
    assert "already delivered" in evidence
    assert k.AGENTIC_36_STAGE2_PROMPT == k._AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION
    assert "memory must complement that response" in k.AGENTIC_36_STAGE2_PROMPT
    assert evidence.index(initial) < evidence.index(review)
    assert "Assistant (initial working reasoning; quoted)" in evidence
    assert "Assistant (later verification reasoning; quoted)" in evidence
    assert k.AGENTIC_FINAL_REVIEW_TRIGGER not in str(wire)
    assert str(wire).count(SECRET_A1) == 1
    assert not any("reasoning_content" in item for item in wire)


@pytest.mark.parametrize("profile", ("flash", "balanced", "thorough"))
def test_frozen_conversation_without_review_preserves_initial_and_never_invents_review(monkeypatch, tmp_path, profile):
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_FROZEN_CONVERSATION", "1")
    k = load(monkeypatch, tmp_path, profile)
    h = history()
    source = k._agentic_stage2_test_history(h, k.STAGES["extended_reflection"])
    prepared = k.OpenAICompatibleBackend(k.CFG)._stage_messages_for_profile(
        source, k.STAGES["extended_reflection"]
    )
    wire = [{"role": "system", "content": k.AGENTIC_36_STAGE2_PROMPT}] + prepared
    k._agentic_attach_system_stage_control(wire, h, k.STAGES["extended_reflection"])
    k._agentic_stage2_project_historical_evidence(wire, source, prepared)
    text = str(wire)
    assert text.count(SECRET_A1) == 1
    assert "later verification reasoning" not in text
    assert "FROZEN COMPLETED RESPONSE" in text
    if profile == "flash":
        assert R1 not in text
    else:
        assert R1 in text
    assert "JACK MEMORY EXTRACTION TASK" in text


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
