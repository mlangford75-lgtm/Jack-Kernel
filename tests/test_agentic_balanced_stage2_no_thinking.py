"""Balanced Agentic: Stage 2 reads R1 but does not generate native thinking.

Balanced is the default Agentic profile; Thorough remains explicitly selectable.
All assertions inspect the exact outgoing LM Studio backend request.
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


def load(monkeypatch, tmp_path, *, profile, cache_enabled=False):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    if profile is None:
        monkeypatch.delenv("JACK_AGENTIC_PROFILE", raising=False)
    else:
        monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    monkeypatch.setenv("JACK_BACKEND_MODEL", "qwen3.8-27b-gsq-rco")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_PRESERVE_THINKING", "1")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT", "1" if cache_enabled else "0")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "balanced_agentic_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def backend_payload(k, *, stage, stream):
    captured = []

    def respond(request):
        captured.append(json.loads(request.content))
        if stream:
            chunks = [
                'data: {"choices":[{"index":0,"delta":{"content":"Working knowledge"},"finish_reason":null}]}',
                'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}',
                "data: [DONE]",
            ]
            return httpx.Response(
                200, text="\n\n".join(chunks) + "\n\n",
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(
            200,
            json={"choices":[{"message":{"role":"assistant","content":"Working knowledge"},
                              "finish_reason":"stop"}],"usage":{}},
        )

    async def run():
        backend = k.OpenAICompatibleBackend(k.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async def resolve_model():
            return "qwen3.8-27b-gsq-rco"
        backend.resolve_model = resolve_model
        history = [
            {"role":"user","content":"Change the clock hand color."},
            {"role":"assistant","content":"Clock is gold.",
             "reasoning_content":"R1: inspect source then change hand color to gold.",
             "_jack_extended_candidate_response":True},
        ]
        original = json.dumps(history)
        try:
            args = dict(
                messages=history,
                secondary_system="CUSTOM CALLER SYSTEM: do not grant to Stage 2",
                profile=k.STAGES[stage],
                tools=None,
                tool_choice="auto",
            )
            if stream:
                async for _ in backend.chat_stream(**args):
                    pass
            else:
                await backend.chat(**args)
            assert json.dumps(history) == original
        finally:
            await backend._client.aclose()

    asyncio.run(run())
    assert len(captured) == 1
    return captured[0]


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("cache_enabled", [False, True])
def test_balanced_preserves_stage1_reasoning_in_stage2_request(monkeypatch, tmp_path, stream, cache_enabled):
    k = load(monkeypatch, tmp_path, profile="balanced", cache_enabled=cache_enabled)
    assert k.STAGES["extended_initial"].thinking is True
    assert k.STAGES["extended_reflection"].thinking is False
    assert k.STAGES["extended_reflection"].allow_tools is False

    p1 = backend_payload(k, stage="extended_initial", stream=stream)
    p2 = backend_payload(k, stage="extended_reflection", stream=stream)
    assert p1["chat_template_kwargs"]["enable_thinking"] is True
    assert p1["chat_template_kwargs"]["preserve_thinking"] is True
    assert p2["chat_template_kwargs"]["enable_thinking"] is False
    assert p2["chat_template_kwargs"]["preserve_thinking"] is True
    assert p2["reasoning_effort"] == "none"
    assert "tools" not in p2 and "tool_choice" not in p2
    assert "CUSTOM CALLER SYSTEM" not in json.dumps(p2)
    assistant = [m for m in p2["messages"] if m.get("role")=="assistant"]
    assert len(assistant) == 1
    assert assistant[0]["content"] == "Clock is gold."
    assert assistant[0]["reasoning_content"] == "R1: inspect source then change hand color to gold."
    if not cache_enabled:
        assert p2["messages"][0]["content"] == k.AGENTIC_36_STAGE2_PROMPT


@pytest.mark.parametrize("stream", [False, True])
def test_thorough_retains_existing_backend_contract(monkeypatch, tmp_path, stream):
    k = load(monkeypatch, tmp_path, profile="thorough")
    assert k.STAGES["extended_initial"].thinking is True
    assert k.STAGES["extended_reflection"].thinking is True
    p2 = backend_payload(k, stage="extended_reflection", stream=stream)
    assert p2["chat_template_kwargs"]["enable_thinking"] is True
    assert p2["chat_template_kwargs"]["preserve_thinking"] is True
    assert p2["reasoning_effort"] == "xhigh"
    assert p2["messages"][-2]["reasoning_content"] == "R1: inspect source then change hand color to gold."


def test_default_is_balanced(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, profile=None)
    assert k.CFG.agentic_profile == "balanced"
    assert k.AGENTIC_BALANCED_MODE is True
    assert k.STAGES["extended_initial"].thinking is True
    assert k.STAGES["extended_reflection"].thinking is False


def test_invalid_experimental_profile_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "something-else")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    name = "bad_balanced_profile_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    with pytest.raises(RuntimeError, match="JACK_AGENTIC_PROFILE"):
        spec.loader.exec_module(mod)


@pytest.mark.parametrize("profile,initial_thinking,reflection_thinking", [
    ("thorough", True, True),
    ("balanced", True, False),
    ("flash", False, False),
])
def test_three_agentic_profiles_share_sampler_without_mutating_stage_temperatures(
    monkeypatch, tmp_path, profile, initial_thinking, reflection_thinking
):
    # Deliberately different OFF sampler: Agentic must not switch samplers.
    monkeypatch.setenv("JACK_THINKING_TOP_P", "0.95")
    monkeypatch.setenv("JACK_NONTHINKING_TOP_P", "0.80")
    k = load(monkeypatch, tmp_path, profile=profile)
    assert k.STAGES["extended_initial"].thinking is initial_thinking
    assert k.STAGES["extended_reflection"].thinking is reflection_thinking
    p1 = backend_payload(k, stage="extended_initial", stream=True)
    p2 = backend_payload(k, stage="extended_reflection", stream=True)
    assert p1["top_p"] == 0.95
    assert p2["top_p"] == 0.95
    assert p1["temperature"] == 0.7
    assert p2["temperature"] == 0.5
    assert p1["presence_penalty"] == 0.0
    assert p2["presence_penalty"] == 0.0
    assert p1["chat_template_kwargs"]["enable_thinking"] is initial_thinking
    assert p2["chat_template_kwargs"]["enable_thinking"] is reflection_thinking
    assert "tools" not in p2
    if profile == "flash":
        # The test fixture includes an artificial R1; Flash must not leak it
        # into the isolated retrospective without native thinking.
        assistant = [m for m in p2["messages"] if m.get("role") == "assistant"]
        assert len(assistant) == 1
        assert "reasoning_content" not in assistant[0]
        assert p2["reasoning_effort"] == "none"
    elif profile == "balanced":
        assert p2["messages"][-2]["reasoning_content"].startswith("R1:")


@pytest.mark.parametrize("choice,profile", [
    ("1", "flash"),
    ("2", "balanced"),
    ("3", "thorough"),
    ("", "balanced"),
])
def test_agentic_submenu_selects_and_persists_profile(monkeypatch, tmp_path, choice, profile):
    k = load(monkeypatch, tmp_path, profile=None)
    cfg = dict(k.CLI_DEFAULTS)
    assert cfg["agentic_profile"] == "balanced"
    answers = iter(["6", choice])
    monkeypatch.setattr(k, "_cli_input", lambda *_a, **_kw: next(answers))
    k._run_transactional_editor(k._edit_reasoning, cfg)
    assert cfg["reasoning_level"] == "Local Agentic (Preserve Thinking)"
    assert cfg["agentic_profile"] == profile
    assert k._config_to_env(cfg)["JACK_AGENTIC_PROFILE"] == profile


def test_agentic_submenu_escape_rolls_back(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, profile=None)
    cfg = dict(k.CLI_DEFAULTS)
    original = dict(cfg)
    answers = iter(["6"])
    def input_or_escape(*_args, **_kwargs):
        try:
            return next(answers)
        except StopIteration:
            raise k._ReturnToMainMenu()
    monkeypatch.setattr(k, "_cli_input", input_or_escape)
    with pytest.raises(k._ReturnToMainMenu):
        k._run_transactional_editor(k._edit_reasoning, cfg)
    assert cfg == original


def test_unknown_agentic_profile_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "invalid-profile")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    name = "bad_three_profiles_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    with pytest.raises(RuntimeError, match="JACK_AGENTIC_PROFILE"):
        spec.loader.exec_module(mod)
