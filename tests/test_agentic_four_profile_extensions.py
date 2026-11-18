"""Agentic profile routing and Stage-1 translation-extension regression coverage.

The retired Exhaustive mode is replaced by Translated. Translated retains
Thorough's two thinking-on stages and source-only working-memory contract;
only Translated adds a same-turn Stage-1 translation continuation.
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
MATRIX = [
    ("flash", False, False, False),
    ("balanced", True, False, False),
    ("thorough", True, False, True),
    ("translated", True, True, True),
]


def load(monkeypatch, tmp_path, profile, language="es"):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    monkeypatch.setenv("JACK_TRANSLATED_LANGUAGE", language)
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "agentic_profiles_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("profile,stage1_thinking,extension,stage2_thinking", MATRIX)
def test_profile_matrix(monkeypatch, tmp_path, profile, stage1_thinking, extension, stage2_thinking):
    k = load(monkeypatch, tmp_path, profile)
    assert k.STAGES["extended_initial"].thinking is stage1_thinking
    assert k.STAGES["extended_reflection"].thinking is stage2_thinking
    assert not k.STAGES["extended_reflection"].allow_tools
    assert k.CFG.agentic_final_review is extension
    assert k._agentic_zero_reasoning(k.STAGES["extended_reflection"]) is (profile in {"flash", "balanced"})
    if profile in {"thorough", "translated"}:
        assert k.AGENTIC_36_STAGE2_PROMPT == k._AGENTIC_STAGE2_THOROUGH_EXHAUSTIVE_DIRECTIVE
    if profile == "translated":
        assert "Spanish" in k.AGENTIC_FINAL_REVIEW_TRIGGER
        assert "Translate the completed Stage 1 response" in k.AGENTIC_FINAL_REVIEW_TRIGGER
        assert k._runtime_identity_details()["agentic_translation_target_language"] == "Spanish"
    else:
        assert "Spanish" not in k.AGENTIC_FINAL_REVIEW_TRIGGER


@pytest.mark.parametrize("streaming", (False, True))
def test_translated_extension_is_a_same_turn_second_stage1_generation(monkeypatch, tmp_path, streaming):
    k = load(monkeypatch, tmp_path, "translated", "fr")
    observed = []

    def responder(request):
        payload = json.loads(request.content)
        observed.append(payload)
        value = "Original English response." if len(observed) == 1 else "Réponse française."
        if streaming:
            parts = [
                {"choices": [{"index": 0, "delta": {"content": value}, "finish_reason": None}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17}},
            ]
            return httpx.Response(
                200,
                text="".join("data: " + json.dumps(p) + "\n\n" for p in parts) + "data: [DONE]\n\n",
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json={
            "choices": [{"index": 0, "message": {"role": "assistant", "content": value}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
        })

    async def run():
        backend = k.OpenAICompatibleBackend(k.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(responder))
        async def model():
            return "test-model"
        backend.resolve_model = model
        kernel = k.JackQwenKernel(backend, k.CFG)
        history = [{"role": "user", "content": "Explain the result."}]
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        try:
            if streaming:
                packets = [p async for p in kernel._run_stage_streamed(
                    history, "", "extended_initial", usage, append=False
                )]
                results = [p["data"] for p in packets if p["kind"] == "result"]
                assert len(results) == 1
                result = results[0]
            else:
                result = await kernel._run_stage(
                    history, "", "extended_initial", usage, append=False
                )
            assert result["choices"][0]["message"]["content"] == "Réponse française."
            assert len(observed) == 2
            assert [m["role"] for m in observed[1]["messages"]] == ["system", "user"]
            assert "French" in observed[1]["messages"][0]["content"]
            assert "Original English response." in observed[1]["messages"][1]["content"]
            assert "Explain the result." not in json.dumps(observed[1]["messages"])
            assert "tool_calls" not in json.dumps(observed[1]["messages"])
            assert "tools" not in observed[1]
            assert "tool_choice" not in observed[1]
            # Only the translation continuation disables native thinking.
            assert observed[0]["chat_template_kwargs"]["enable_thinking"] is True
            assert observed[1]["chat_template_kwargs"]["enable_thinking"] is False
            assert observed[1]["chat_template_kwargs"]["preserve_thinking"] is False
            assert observed[1]["reasoning_effort"] == "none"
            assert k.STAGES["extended_initial"].thinking is True
            assert k.STAGES["extended_reflection"].thinking is True
        finally:
            await backend._client.aclose()

    asyncio.run(run())


def test_retired_exhaustive_and_document_translator_not_selectable(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, "balanced")
    assert k.REASONING_PROFILES["translator"]["disabled"]
    assert "Coming Soon" in k.REASONING_PROFILES["translator"]["label"]
    with pytest.raises(RuntimeError, match="flash, balanced, thorough, translated, or coder"):
        load(monkeypatch, tmp_path, "exhaustive")


def test_saved_exhaustive_migrates_without_reenabling_it(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, "balanced")
    saved = tmp_path / "config.json"
    saved.write_text(json.dumps({
        "config_schema_version": k.CONFIG_SCHEMA_VERSION,
        "agentic_profile": "exhaustive",
        "backend_model": "test-model",
    }), encoding="utf-8")
    monkeypatch.setattr(k, "_config_paths", lambda: (saved, tmp_path / "secondary.txt"))
    loaded = k._load_cli_config()
    assert loaded["agentic_profile"] == "translated"
    assert k._config_to_env(loaded)["JACK_AGENTIC_PROFILE"] == "translated"


def test_translated_projection_never_replays_authenticated_request_or_tools(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, "translated", "de")
    authenticated_request = "Inspect a local workspace and execute bash."
    original_reasoning = "The user requested file inspection."
    previous_tool_call = "call-real-1"
    h = [
        {"role": "user", "content": authenticated_request},
        {"role": "assistant", "content": "", "reasoning_content": original_reasoning,
         "_jack_internal_tool_exchange": True,
         "tool_calls": [{"id": previous_tool_call, "type": "function", "function": {
             "name": "bash", "arguments": '{"command":"ls -la"}'
         }}]},
        {"role": "tool", "tool_call_id": previous_tool_call, "content": "only . and ..",
         "_jack_internal_tool_exchange": True},
    ]
    k._agentic_begin_final_review(h, {"choices": [{"finish_reason": "stop", "message": {
        "role": "assistant", "content": "Workspace is empty.",
        "reasoning_content": "Confirmed by ls listing."
    }}]})
    original_h = json.dumps(h, ensure_ascii=False)
    payload = [{"role": "system", "content": "This will be overwritten."},
               {"role": "user", "content": authenticated_request}]
    k._agentic_translated_project_completed_answer(payload, h)
    assert [m["role"] for m in payload] == ["system", "user"]
    assert "German" in payload[0]["content"]
    assert "Workspace is empty." in payload[1]["content"]
    wire = json.dumps(payload, ensure_ascii=False)
    for forbidden in (authenticated_request, previous_tool_call, original_reasoning,
                      "only . and ..", "bash", "tool_calls"):
        assert forbidden not in wire
    assert json.dumps(h, ensure_ascii=False) == original_h


def test_translated_literal_fake_tool_call_preserves_verified_stage1_draft(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, "translated", "es")
    h = [{"role": "user", "content": "Verify the workspace."}]
    k._agentic_begin_final_review(h, {"choices": [{"finish_reason": "stop", "message": {
        "role": "assistant", "content": "The workspace is empty."
    }}]})
    model_message = {"role": "assistant", "content": (
        "I should check the folder again.<tool_call><function=bash>"
        "<parameter=command>ls -la</parameter></function></tool_call>"
    )}
    k._agentic_translated_guard_literal_tool_call(h, model_message)
    assert "original completed response preserved" in model_message["content"]
    assert "The workspace is empty." in model_message["content"]
    assert "<tool_call>" not in model_message["content"]
    assert "tool_calls" not in model_message
    assert h[-2]["content"] == "The workspace is empty."


def test_translated_tool_call_guard_allows_ordinary_translation(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, "translated", "fr")
    h = [{"role": "user", "content": "Verify the workspace."}]
    k._agentic_begin_final_review(h, {"choices": [{"finish_reason": "stop", "message": {
        "role": "assistant", "content": "The workspace is empty."
    }}]})
    msg = {"role": "assistant", "content": "L'espace de travail est vide."}
    k._agentic_translated_guard_literal_tool_call(h, msg)
    assert msg["content"] == "L'espace de travail est vide."


def test_translated_memory_is_english_only_and_thorough_unchanged(monkeypatch, tmp_path):
    translated = load(monkeypatch, tmp_path, "translated", "fr")
    assert "Write the retained working knowledge in English" in translated.AGENTIC_36_STAGE2_PROMPT
    assert translated.STAGES["extended_reflection"].thinking is True
    assert translated._agentic_zero_reasoning(translated.STAGES["extended_initial"]) is False
    thorough = load(monkeypatch, tmp_path, "thorough", "fr")
    assert "Write the retained working knowledge in English" not in thorough.AGENTIC_36_STAGE2_PROMPT
    assert thorough.STAGES["extended_reflection"].thinking is True
