"""Universal Agentic source-only Stage-2 durable working-state contract.

Capture real outbound streamed and nonstreamed OpenAI-compatible payloads.
The original user request and frozen answer remain in canonical history,
but never appear as model-facing content in any Agentic memory pass.
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
REQUEST = "Please independently answer SECRET_USER_QUESTION_7219"
ANSWER = "SECRET_FROZEN_RESPONSE_5831"
REASONING = "The chosen approach is atomic replacement. Failed direct overwrite: crash risk."
ARGS = '{"path":"artifact.json","mode":"atomic_replace"}'
RESULT = 'Verified tool report: artifact.json written; downstream validation still pending.'


def load(monkeypatch, tmp_path, profile="thorough"):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    # A stale environment setting must NOT turn the branch's experiment off.
    monkeypatch.setenv("JACK_AGENTIC_THOROUGH_WORKING_STATE", "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_WITHHOLD_A1", "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_FROZEN_CONVERSATION", "0")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_thorough_state_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    kernel = importlib.util.module_from_spec(spec)
    sys.modules[name] = kernel
    spec.loader.exec_module(kernel)
    return kernel


def history():
    return [
        {"role": "user", "content": REQUEST},
        {"role": "assistant", "content": "", "reasoning_content": REASONING,
         "tool_calls": [{"id": "call-a1", "type": "function",
                         "function": {"name": "write", "arguments": ARGS}}],
         "_jack_internal_tool_exchange": True, "_jack_stage_key": "extended_initial"},
        {"role": "tool", "name": "write", "tool_call_id": "call-a1",
         "content": RESULT, "_jack_internal_tool_exchange": True,
         "_jack_stage_key": "extended_initial"},
        {"role": "assistant", "content": ANSWER,
         "reasoning_content": "Tool returned success; actual artifact correctness remains unverified.",
         "_jack_extended_candidate_response": True},
    ]


@pytest.mark.parametrize("profile", ("flash", "balanced", "thorough", "translated"))
@pytest.mark.parametrize("stream", (False, True))
def test_all_profiles_receive_only_frozen_reasoning_and_complete_tool_evidence(
    monkeypatch, tmp_path, profile, stream,
):
    k = load(monkeypatch, tmp_path, profile=profile)
    original = history()
    saved = copy.deepcopy(original)
    seen = []

    def respond(request):
        payload = json.loads(request.content)
        seen.append(payload)
        if stream:
            return httpx.Response(
                200,
                text='data: {"choices":[{"index":0,"delta":{"content":"Working state"},"finish_reason":null}]}\n\n'
                     'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
                     'data: [DONE]\n\n',
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "Working state"},
                         "finish_reason": "stop"}], "usage": {},
        })

    async def run():
        backend = k.OpenAICompatibleBackend(k.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async def model():
            return "test-model"
        backend.resolve_model = model
        try:
            kwargs = dict(messages=original, secondary_system="",
                          profile=k.STAGES["extended_reflection"],
                          tools=None, tool_choice="auto")
            if stream:
                async for _ in backend.chat_stream(**kwargs):
                    pass
            else:
                await backend.chat(**kwargs)
        finally:
            await backend._client.aclose()

    asyncio.run(run())
    assert original == saved
    assert len(seen) == 1
    payload = seen[0]
    assert payload.get("tools") is None
    assert "tool_choice" not in payload
    assert payload["messages"][-1]["role"] == "user"
    assert sum(m["role"] == "user" for m in payload["messages"]) == 1
    assert all(m["role"] != "assistant" for m in payload["messages"])
    wire = json.dumps(payload["messages"], ensure_ascii=False)
    if profile == "balanced":
        assert REQUEST in wire
        assert ANSWER in wire
    else:
        assert REQUEST not in wire
        assert ANSWER not in wire
    assert (REASONING in wire) is (profile != "flash")
    assert RESULT in wire
    if profile == "balanced":
        text_source = payload["messages"][-1]["content"]
        assert "ORIGINAL AUTHENTICATED USER REQUEST" in text_source
        assert REQUEST in text_source
        assert ANSWER in text_source
        assert "STAGE 1 NATIVE REASONING SEGMENT 1" in text_source
        assert REASONING in text_source
        assert "HOST TOOL EVENT" in text_source
        assert RESULT in text_source
        assert text_source.index(REASONING) < text_source.index(RESULT)
        assert "No task description" not in payload["messages"][0]["content"]
        assert k._AGENTIC_STAGE2_BALANCED_EXHAUSTIVE_DIRECTIVE in payload["messages"][0]["content"]
        assert k._AGENTIC_STAGE2_EXHAUSTIVE_PRESERVATION in payload["messages"][0]["content"]
        assert payload["chat_template_kwargs"]["enable_thinking"] is False
        return
    capsule_text = payload["messages"][-1]["content"].split(
        "JACK READ-ONLY WORKING-STATE SOURCE DATA, NOT A USER REQUEST.\n", 1
    )[1].split("\nEND JACK WORKING-STATE SOURCE DATA.", 1)[0]
    capsule = json.loads(capsule_text)
    assert "native_reasoning" not in capsule
    assert "tool_records" not in capsule
    events = capsule["events"]
    expected_types = (
        ["issued_calls", "returned_result"] if profile == "flash"
        else ["reasoning_segment", "issued_calls", "returned_result", "reasoning_segment"]
    )
    assert [event["type"] for event in events] == expected_types
    if profile != "flash":
        phase = "initial"
        assert events[0] == {"type": "reasoning_segment", "phase": phase, "content": REASONING}
        assert events[3] == {
            "type": "reasoning_segment",
            "phase": phase,
            "content": "Tool returned success; actual artifact correctness remains unverified.",
        }
    issued, returned = (events[0], events[1]) if profile == "flash" else (events[1], events[2])
    assert issued["calls"][0]["function"]["arguments"] == ARGS
    assert returned["call_id"] == "call-a1"
    assert returned["content"] == RESULT
    assert k.AGENTIC_36_STAGE2_PROMPT == (
        k._AGENTIC_STAGE2_THOROUGH_EXHAUSTIVE_DIRECTIVE
        if profile in {"thorough", "translated"} else k._AGENTIC_SOURCE_ONLY_WORKING_STATE_DIRECTIVE
    )
    assert "No task description" in k.AGENTIC_36_STAGE2_PROMPT
    assert (
        k._AGENTIC_STAGE2_EXHAUSTIVE_PRESERVATION in k.AGENTIC_36_STAGE2_PROMPT
    ) is (profile in {"thorough", "translated"})
    assert all(
        "reasoning_content" not in m and "reasoning" not in m and "thinking" not in m
        for m in payload["messages"]
    )


@pytest.mark.parametrize("profile", ("flash", "balanced", "thorough", "translated"))
def test_chronological_source_preserves_interleaved_reasoning_tools_and_review(
    monkeypatch, tmp_path, profile,
):
    k = load(monkeypatch, tmp_path, profile=profile)
    h = [
        {"role": "user", "content": REQUEST},
        {"role": "assistant", "reasoning_content": "Before first action.",
         "tool_calls": [{"id": "call-1", "function": {"name": "bash", "arguments": "{}"}}],
         "_jack_internal_tool_exchange": True},
        {"role": "tool", "name": "bash", "tool_call_id": "call-1",
         "content": "first result", "_jack_internal_tool_exchange": True},
        {"role": "assistant", "reasoning_content": "Observed first result; changing approach.",
         "tool_calls": [{"id": "call-2", "function": {"name": "write", "arguments": "{}"}}],
         "_jack_internal_tool_exchange": True},
        {"role": "tool", "name": "write", "tool_call_id": "call-2",
         "content": "second result", "_jack_internal_tool_exchange": True},
        {"role": "system", "_jack_internal_agentic_final_review_trigger": True,
         "content": "Private host review boundary"},
        {"role": "assistant", "reasoning_content": "Verified second action after review.",
         "_jack_extended_candidate_response": True, "content": ANSWER},
    ]
    saved = copy.deepcopy(h)
    events = k._agentic_stage2_chronological_source(h)
    assert h == saved
    if profile == "flash":
        assert [e["type"] for e in events] == [
            "issued_calls", "returned_result", "issued_calls", "returned_result"
        ]
    else:
        assert [e["type"] for e in events] == [
            "reasoning_segment", "issued_calls", "returned_result",
            "reasoning_segment", "issued_calls", "returned_result",
            "reasoning_segment"
        ]
        # Translated uses Thorough chronology with its extension marked as translation.
        expected_phases = (
            ["initial", "initial", "translation"] if profile == "translated"
            else ["initial", "initial", "verification"]
        )
        assert [e["phase"] for e in events if e["type"] == "reasoning_segment"] == expected_phases
        assert [e["content"] for e in events if e["type"] == "reasoning_segment"] == [
            "Before first action.",
            "Observed first result; changing approach.",
            "Verified second action after review.",
        ]
    assert [e["call_id"] for e in events if e["type"] == "returned_result"] == [
        "call-1", "call-2"
    ]
    assert REQUEST not in json.dumps(events)
    assert ANSWER not in json.dumps(events)


@pytest.mark.parametrize("profile", ("flash", "balanced", "thorough", "translated"))
def test_source_only_is_universal_even_when_stale_env_requests_legacy(monkeypatch, tmp_path, profile):
    k = load(monkeypatch, tmp_path, profile=profile)
    assert k.AGENTIC_SOURCE_ONLY_WORKING_STATE
    assert k.AGENTIC_STAGE2_WITHHOLD_A1
    assert k.AGENTIC_STAGE2_FROZEN_CONVERSATION
    assert k.AGENTIC_36_STAGE2_PROMPT == (
        k._AGENTIC_STAGE2_BALANCED_EXHAUSTIVE_DIRECTIVE
        if profile == "balanced" else
        k._AGENTIC_STAGE2_THOROUGH_EXHAUSTIVE_DIRECTIVE
        if profile in {"thorough", "translated"} else k._AGENTIC_SOURCE_ONLY_WORKING_STATE_DIRECTIVE
    )
    assert k._runtime_identity_details()["agentic_stage2_source_only"] is True


@pytest.mark.parametrize("profile", ("flash", "balanced", "thorough", "translated"))
@pytest.mark.parametrize("stream", (False, True))
def test_all_profile_stage_seeds_are_base_and_base_plus_two(monkeypatch, tmp_path, profile, stream):
    monkeypatch.setenv("JACK_SEED", "314159")
    k = load(monkeypatch, tmp_path, profile=profile)
    requests = []
    def respond(req):
        requests.append(json.loads(req.content))
        if stream:
            return httpx.Response(
                200,
                text='data: {"choices":[{"index":0,"delta":{"content":"ok"},"finish_reason":null}]}\n\n'
                     'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
                     'data: [DONE]\n\n',
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json={"choices": [
            {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
        ], "usage": {}})

    async def run_stage(stage):
        backend = k.OpenAICompatibleBackend(k.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async def model(): return "test-model"
        backend.resolve_model = model
        try:
            kwargs = dict(messages=history(), secondary_system="",
                          profile=k.STAGES[stage], tools=None, tool_choice="auto")
            if stream:
                async for _ in backend.chat_stream(**kwargs):
                    pass
            else:
                await backend.chat(**kwargs)
        finally:
            await backend._client.aclose()

    asyncio.run(run_stage("extended_initial"))
    asyncio.run(run_stage("extended_reflection"))
    assert [r["seed"] for r in requests] == [314159, 314161]


@pytest.mark.parametrize("profile", ("flash", "balanced", "thorough", "translated"))
def test_random_work_id_seed_stable_across_tool_continuations(monkeypatch, tmp_path, profile):
    monkeypatch.setenv("JACK_SEED", "")
    k = load(monkeypatch, tmp_path, profile=profile)
    h = history()
    h[0]["_jack_agentic_turn_id"] = "jack-turn-1234abcd0123456789abcdef01234567"
    original_seed = k.OpenAICompatibleBackend(k.CFG)._seed_for_stage(
        k.STAGES["extended_initial"], h
    )
    h.insert(-1, {"role": "tool", "content": "subsequent tool result",
                   "tool_call_id": "call-new"})
    resumed_seed = k.OpenAICompatibleBackend(k.CFG)._seed_for_stage(
        k.STAGES["extended_initial"], h
    )
    stage2_seed = k.OpenAICompatibleBackend(k.CFG)._seed_for_stage(
        k.STAGES["extended_reflection"], h
    )
    assert 0 <= original_seed < 2**31 - 2
    assert resumed_seed == original_seed
    assert stage2_seed == original_seed + 2


@pytest.mark.parametrize("profile", ("flash", "balanced", "thorough", "translated"))
def test_seed_separation_preserves_explicit_base_in_all_profiles(monkeypatch, tmp_path, profile):
    monkeypatch.setenv("JACK_SEED", "123")
    k = load(monkeypatch, tmp_path, profile=profile)
    backend = k.OpenAICompatibleBackend(k.CFG)
    assert backend._seed_for_stage(k.STAGES["extended_initial"], history()) == 123
    assert backend._seed_for_stage(k.STAGES["extended_reflection"], history()) == 125


@pytest.mark.parametrize("profile", ("flash", "balanced", "thorough", "translated"))
@pytest.mark.parametrize("stream", (False, True))
def test_agentic_qwen_single_system_template_wire_contract(monkeypatch, tmp_path, profile, stream):
    """A model template that rejects a second system role must accept Jack's wire.

    Exercise the real outbound chat/completions paths, not an after-the-fact
    helper-only assertion. Keep all model-facing system instructions in order,
    preserve the user's exact content, and keep Stage-2 source-only isolation.
    """
    k = load(monkeypatch, tmp_path, profile=profile)
    original = history()
    saved = copy.deepcopy(original)
    system_error = "Jinja Exception: System message must be at the beginning."
    requests = []

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        system_messages = [m for m in payload["messages"] if m["role"] == "system"]
        if len(system_messages) > 1 or (system_messages and payload["messages"][0]["role"] != "system"):
            return httpx.Response(500, json={"error": {"message": system_error}})
        if stream:
            return httpx.Response(
                200,
                text='data: {"choices":[{"index":0,"delta":{"content":"Working state"},"finish_reason":null}]}\n\n'
                     'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
                     'data: [DONE]\n\n',
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "Working state"},
                         "finish_reason": "stop"}], "usage": {},
        })

    async def run():
        backend = k.OpenAICompatibleBackend(k.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async def model():
            return "test-model"
        backend.resolve_model = model
        try:
            kwargs = dict(messages=original, secondary_system="",
                          profile=k.STAGES["extended_reflection"],
                          tools=None, tool_choice="auto")
            if stream:
                async for _ in backend.chat_stream(**kwargs):
                    pass
            else:
                await backend.chat(**kwargs)
        finally:
            await backend._client.aclose()

    asyncio.run(run())
    assert len(requests) == 1, "Backend must not need a 500 retry"
    assert original == saved
    wire = requests[0]["messages"]
    assert wire[0]["role"] == "system"
    assert sum(m["role"] == "system" for m in wire) == 1
    assert k.AGENTIC_36_STAGE2_PROMPT in wire[0]["content"]
    assert k.AGENTIC_STAGE2_MEMORY_TRIGGER in wire[0]["content"]
    assert wire[0]["content"].index(k.AGENTIC_36_STAGE2_PROMPT) < wire[0]["content"].index(k.AGENTIC_STAGE2_MEMORY_TRIGGER)
    if profile == "balanced":
        assert REQUEST in json.dumps(wire)
        assert ANSWER in json.dumps(wire)
    else:
        assert REQUEST not in json.dumps(wire)
        assert ANSWER not in json.dumps(wire)


def test_work_id_and_review_system_authority_are_folded_without_losing_identity(monkeypatch, tmp_path):
    """Reproduce the Qwen three-message failure and a review continuation."""
    k = load(monkeypatch, tmp_path)
    original = [
        {"role": "system", "content": "Pi caller system instructions"},
        {"role": "system", "content": "Authenticated current work ID: jack-turn-abc"},
        {"role": "user", "content": [{"type": "text", "text": REQUEST}]},
    ]
    preserved = copy.deepcopy(original)
    folded = k.OpenAICompatibleBackend._fold_model_facing_system_messages(original)
    assert original == preserved
    assert len(folded) == 2
    assert folded[0] == {
        "role": "system",
        "content": "Pi caller system instructions\n\nAuthenticated current work ID: jack-turn-abc",
    }
    assert folded[1] == original[2]

    review = original + [
        {"role": "assistant", "content": "Frozen answer"},
        {"role": "system", "content": "Jack current-turn review instruction"},
    ]
    collapsed = k.OpenAICompatibleBackend._fold_model_facing_system_messages(review)
    assert [m["role"] for m in collapsed] == ["system", "user", "assistant"]
    assert collapsed[0]["content"].endswith("Jack current-turn review instruction")
    assert collapsed[-1]["content"] == "Frozen answer"


@pytest.mark.parametrize("profile", ("flash", "balanced", "thorough", "translated"))
def test_exhaustive_retention_is_profile_scoped_and_not_future_usefulness_filtered(
    monkeypatch, tmp_path, profile,
):
    k = load(monkeypatch, tmp_path, profile=profile)
    prompt = k.AGENTIC_36_STAGE2_PROMPT
    if profile in ("balanced", "thorough", "translated"):
        assert k._AGENTIC_STAGE2_EXHAUSTIVE_PRESERVATION in prompt
        assert "Do not discard established information." in prompt
        assert "Remove only redundant deliberation, superseded speculation" in prompt
        assert "Before retaining information, determine whether it would materially help" not in prompt
        assert "materially help a future agent" not in prompt
        assert k._stage_continuation(k.STAGES["extended_reflection"]) == prompt
        assert k.STAGES["extended_reflection"].thinking is (profile in {"thorough", "translated"})
    else:
        assert k._AGENTIC_STAGE2_EXHAUSTIVE_PRESERVATION not in prompt

@pytest.mark.parametrize("profile", ("flash", "balanced", "thorough", "translated"))
def test_translated_is_thorough_plus_translation_extension(monkeypatch, tmp_path, profile):
    monkeypatch.setenv("JACK_TRANSLATED_LANGUAGE", "es")
    k = load(monkeypatch, tmp_path, profile=profile)
    assert k.CFG.agentic_final_review is (profile == "translated")
    assert k.AGENTIC_TRANSLATED_MODE is (profile == "translated")
    assert k.STAGES["extended_initial"].thinking is (profile != "flash")
    assert k.STAGES["extended_reflection"].thinking is (profile in ("thorough", "translated"))
    assert k.AGENTIC_36_STAGE2_PROMPT == (
        k._AGENTIC_STAGE2_THOROUGH_EXHAUSTIVE_DIRECTIVE
        if profile in {"thorough", "translated"} else
        k._AGENTIC_STAGE2_BALANCED_EXHAUSTIVE_DIRECTIVE
        if profile == "balanced" else k._AGENTIC_SOURCE_ONLY_WORKING_STATE_DIRECTIVE
    )
    if profile == "translated":
        assert "Spanish" in k.AGENTIC_FINAL_REVIEW_TRIGGER
        assert "Translate the completed Stage 1 response" in k.AGENTIC_FINAL_REVIEW_TRIGGER
        assert "do not resume the original task" in k.AGENTIC_FINAL_REVIEW_TRIGGER
        assert k._runtime_identity_details()["agentic_translation_target_language"] == "Spanish"
    else:
        assert "Spanish" not in k.AGENTIC_FINAL_REVIEW_TRIGGER


def test_translator_coming_soon_and_exhaustive_rejected(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    assert k.REASONING_PROFILES["translator"]["disabled"] is True
    assert "Coming Soon" in k.REASONING_PROFILES["translator"]["label"]
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "exhaustive")
    with pytest.raises(RuntimeError, match="flash, balanced, thorough, or translated"):
        load(monkeypatch, tmp_path, profile="exhaustive")


def test_translated_extension_captures_prior_completed_draft(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_TRANSLATED_LANGUAGE", "fr")
    k = load(monkeypatch, tmp_path, profile="translated")
    h = [{"role": "user", "content": "Explain the calculation."}]
    response = {"choices": [{"finish_reason": "stop", "message": {
        "role": "assistant", "content": "The calculation is accurate.",
        "reasoning_content": "Checked the values independently."
    }}]}
    k._agentic_begin_final_review(h, response)
    assert h[-2]["content"] == "The calculation is accurate."
    assert h[-2]["reasoning_content"] == "Checked the values independently."
    assert h[-1]["_jack_internal_agentic_final_review_trigger"] is True
    assert "French" in h[-1]["content"]
    assert "Translate the completed Stage 1 response" in h[-1]["content"]
    assert k._agentic_final_review_is_pending(h)
