"""Three Agentic profiles: exact Stage-1 directive and deterministic stage scheduling.

Tests exercise outbound generations and native-thinking controls, not model quality.
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
STAGE1_EXTENSION = (
    "Wait, more verification is needed. Test the reasoning for errors, mistakes, "
    "or poor quality. Make changes, if necessary, to ensure alignment with "
    "instructions and user request before responding"
)

MATRIX = [
    ("flash", False, False, False),
    ("balanced", True, False, False),
    ("thorough", True, True, True),
]


def load(monkeypatch, tmp_path, profile):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    # Intentionally set conflicting legacy toggles: profiles own their routing.
    monkeypatch.setenv("JACK_AGENTIC_FINAL_REVIEW", "1" if profile in {"flash", "balanced"} else "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_FINAL_REVIEW", "1")  # obsolete override must have no effect
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT", "0")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + '.sqlite')))
    name = 'agentic_three_profiles_' + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / 'jack_kernel.py')
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


async def run_stage(k, stage_key, streaming):
    payloads = []

    def responder(request):
        payload = json.loads(request.content)
        payloads.append(payload)
        n = len(payloads)
        text = f"Output {n}"
        if streaming:
            rows = [
                {"choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 30, "completion_tokens": 5, "total_tokens": 35}},
            ]
            return httpx.Response(200, text=''.join('data: ' + json.dumps(x) + '\n\n' for x in rows) + 'data: [DONE]\n\n',
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 5, "total_tokens": 35},
        })

    backend = k.OpenAICompatibleBackend(k.CFG)
    await backend._client.aclose()
    backend._client = httpx.AsyncClient(transport=httpx.MockTransport(responder))

    async def model():
        return 'test-model'

    backend.resolve_model = model
    kernel = k.JackQwenKernel(backend, k.CFG)
    h = [{"role": "user", "content": "Check that the output follows the request."}]
    if stage_key == "extended_reflection":
        h.append({"role": "assistant", "content": "Draft response", "reasoning_content": "R1 source content",
                  "_jack_extended_candidate_response": True, "_jack_stage_key": "extended_initial"})
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    try:
        if streaming:
            packets = [p async for p in kernel._run_stage_streamed(
                h, "", stage_key, usage, tools=None, tool_choice=None, append=False)]
            result = [p["data"] for p in packets if p["kind"] == "result"]
            assert len(result) == 1
            result = result[0]
        else:
            result = await kernel._run_stage(
                h, "", stage_key, usage, tools=None, tool_choice=None, append=False)
        return payloads, h, usage, result
    finally:
        await backend._client.aclose()


@pytest.mark.parametrize('streaming', [False, True])
@pytest.mark.parametrize('profile,stage1_thinking,stage1_extra,stage2_thinking', MATRIX)
def test_profile_matrix_and_exact_continuations(
    monkeypatch, tmp_path, streaming, profile, stage1_thinking, stage1_extra, stage2_thinking
):
    k = load(monkeypatch, tmp_path, profile)
    assert k.CFG.agentic_final_review is stage1_extra
    assert k.STAGES['extended_initial'].thinking is stage1_thinking
    assert k.STAGES['extended_reflection'].thinking is stage2_thinking
    assert not k.STAGES['extended_reflection'].allow_tools
    assert k.AGENTIC_FINAL_REVIEW_TRIGGER == STAGE1_EXTENSION
    assert k.AGENTIC_36_STAGE2_PROMPT.count('Remove unnecessary conversational language') == 1

    first, h1, usage1, out1 = asyncio.run(run_stage(k, 'extended_initial', streaming))
    assert len(first) == 1 + int(stage1_extra)
    assert usage1['completion_tokens'] == len(first) * 5
    assert out1['choices'][0]['message']['content'] == f'Output {len(first)}'
    for payload in first:
        assert payload['chat_template_kwargs']['enable_thinking'] is stage1_thinking
    if stage1_extra:
        assert first[1]['messages'][-1]['content'] == STAGE1_EXTENSION
        assert first[1]['messages'][-2]['content'] == 'Output 1'

    second, h2, usage2, out2 = asyncio.run(run_stage(k, 'extended_reflection', streaming))
    assert len(second) == 1
    assert usage2['completion_tokens'] == len(second) * 5
    assert out2['choices'][0]['message']['content'] == f'Output {len(second)}'
    for payload in second:
        assert payload['chat_template_kwargs']['enable_thinking'] is stage2_thinking
        assert 'tools' not in payload
    assert not any(m.get('_jack_internal_agentic_stage2_review_trigger') for m in h2)
    assert not any('re-verify that the Prime Directive' in str(m.get('content', '')) for m in second[0]['messages'])
    if profile in {'balanced', 'thorough'}:
        assert second[0]['messages'][-2]['reasoning_content'] == 'R1 source content'
        assert second[0]['chat_template_kwargs']['preserve_thinking'] is True
    else:
        assert 'reasoning_content' not in second[0]['messages'][-2]


def test_default_profile_is_balanced_and_both_legacy_toggles_ignored(monkeypatch, tmp_path):
    monkeypatch.delenv('JACK_AGENTIC_PROFILE', raising=False)
    k = load(monkeypatch, tmp_path, 'balanced')
    assert k.CFG.agentic_profile == 'balanced'
    assert not k.CFG.agentic_final_review


def test_exhaustive_is_not_a_runtime_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "exhaustive")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    name = "obsolete_exhaustive_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    with pytest.raises(RuntimeError, match="must be flash, balanced, or thorough"):
        spec.loader.exec_module(module)


def test_legacy_exhaustive_saved_config_migrates_to_thorough(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, "balanced")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "config_schema_version": k.CONFIG_SCHEMA_VERSION,
        "agentic_profile": "exhaustive",
        "backend_model": "test-model",
    }), encoding="utf-8")
    monkeypatch.setattr(k, "_config_paths", lambda: (config_path, tmp_path / "secondary.txt"))
    loaded = k._load_cli_config()
    assert loaded["agentic_profile"] == "thorough"
    assert k._config_to_env(loaded)["JACK_AGENTIC_PROFILE"] == "thorough"
    assert k._config_to_env({"agentic_profile":"exhaustive", **{
        key: val for key, val in loaded.items() if key != "agentic_profile"
    }})["JACK_AGENTIC_PROFILE"] == "thorough"
