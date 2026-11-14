"""Four Agentic profiles: exact Stage-1 directive, single-pass Stage-2 scheduling.

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
STAGE1_EXTENSION = "Wait, re-verify your reasoning. Test for errors, mistakes, or poor quality. Make changes, if necessary, to ensure alignment with the instructions and user request before responding"

MATRIX = [
    ("flash", False, False, False),
    ("balanced", True, False, False),
    ("thorough", True, False, True),
    ("exhaustive", True, True, True),
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
    assert not hasattr(k.CFG, 'agentic_stage2_final_review')
    assert k.STAGES['extended_initial'].thinking is stage1_thinking
    assert k.STAGES['extended_reflection'].thinking is stage2_thinking
    assert not k.STAGES['extended_reflection'].allow_tools
    assert k.AGENTIC_FINAL_REVIEW_PROMPT == STAGE1_EXTENSION
    assert k.AGENTIC_36_STAGE2_PROMPT.count('Remove repetition, unnecessary deliberation, and conversational language.') == 1

    first, h1, usage1, out1 = asyncio.run(run_stage(k, 'extended_initial', streaming))
    assert len(first) == 1 + int(stage1_extra)
    assert usage1['completion_tokens'] == len(first) * 5
    assert out1['choices'][0]['message']['content'] == f'Output {len(first)}'
    for payload in first:
        assert payload['chat_template_kwargs']['enable_thinking'] is stage1_thinking
    if stage1_extra:
        assert not any(m.get('content') == k.AGENTIC_FINAL_REVIEW_TRIGGER for m in first[1]['messages'])
        # Keep the current authenticated request before its own draft;
        # the final user-role message is Jack's short review control only.
        wire = first[1]['messages']
        assert wire[-1] == {'role': 'user', 'content': k.AGENTIC_FINAL_REVIEW_WIRE_TRIGGER}
        assert wire[-2]['role'] == 'assistant'
        assert wire[-2]['content'] == 'Output 1'
        original = k.active_response_target(h1)['content']
        assert sum(m.get('role') == 'user' and m.get('content') == original for m in wire) == 1
        assert wire.index(next(m for m in wire if m.get('content') == original)) < len(wire) - 2
        assert k.AGENTIC_FINAL_REVIEW_WIRE_TRIGGER == STAGE1_EXTENSION
        assert 'Jack' not in k.AGENTIC_FINAL_REVIEW_WIRE_TRIGGER
        assert sum(m.get('content') == k.AGENTIC_FINAL_REVIEW_WIRE_TRIGGER for m in wire) == 1

    second, h2, usage2, out2 = asyncio.run(run_stage(k, 'extended_reflection', streaming))
    assert len(second) == 1
    assert usage2['completion_tokens'] == 5
    assert out2['choices'][0]['message']['content'] == 'Output 1'
    for payload in second:
        assert payload['chat_template_kwargs']['enable_thinking'] is stage2_thinking
        assert 'tools' not in payload
    assert not any(m.get('_jack_internal_agentic_stage2_review_trigger') for m in h2)
    if profile in {'balanced', 'thorough', 'exhaustive'}:
        assert second[0]['messages'][-2]['reasoning_content'] == 'R1 source content'
        assert second[0]['chat_template_kwargs']['preserve_thinking'] is True
    else:
        assert 'reasoning_content' not in second[0]['messages'][-2]



@pytest.mark.parametrize("streaming", [False, True])
def test_exhaustive_review_one_question_one_draft_no_fake_repetition(monkeypatch, tmp_path, streaming):
    k = load(monkeypatch, tmp_path, "exhaustive")
    original = "what is battlefield"
    draft = "Battlefield is a tactical FPS series."
    h = [{"role": "user", "content": original}]
    k._agentic_begin_turn(h, fresh=True)
    work_id = k._agentic_forensic_turn(h).turn_id
    k._agentic_begin_final_review(h, {
        "choices": [{
            "message": {"role": "assistant", "content": draft,
                        "reasoning_content": "First pass considered EA and DICE."},
            "finish_reason": "stop",
        }]
    })
    source = list(h)
    backend = k.OpenAICompatibleBackend(k.CFG)
    stage = k.STAGES["extended_initial"]
    prepared = backend._stage_messages_for_profile(h, stage)
    wire = [{"role": "system", "content": k.AGENTIC_STAGE1_PROMPT}] + prepared
    k._agentic_attach_system_stage_control(wire, h, stage)
    k._agentic_stage1_review_put_authenticated_user_last(wire, source, prepared)
    assert k._agentic_forensic_turn(h).turn_id == work_id
    assert k.active_response_target(h)["content"] == original
    assert sum(m.get("role") == "user" and m.get("content") == original for m in wire) == 1
    assert sum(m.get("role") == "assistant" and m.get("content") == draft for m in wire) == 1
    positions = {
        "question": next(i for i, m in enumerate(wire) if m.get("content") == original),
        "draft": next(i for i, m in enumerate(wire) if m.get("content") == draft),
        "cue": next(i for i, m in enumerate(wire)
                    if m.get("content") == k.AGENTIC_FINAL_REVIEW_WIRE_TRIGGER),
    }
    assert positions["question"] < positions["draft"] < positions["cue"]
    assert wire[-1]["content"] == k.AGENTIC_FINAL_REVIEW_WIRE_TRIGGER
    assert not any(m.get("content") == k.AGENTIC_FINAL_REVIEW_TRIGGER for m in wire)
    assert draft not in k.AGENTIC_FINAL_REVIEW_WIRE_TRIGGER
    assert original not in k.AGENTIC_FINAL_REVIEW_WIRE_TRIGGER
    # Jack's historical record retains the original internal instruction.
    assert h[-1]["content"] == k.AGENTIC_FINAL_REVIEW_TRIGGER
    assert h[-1]["_jack_internal_agentic_final_review_trigger"] is True


@pytest.mark.parametrize("streaming", [False, True])
def test_exhaustive_review_tool_resume_preserves_protocol_suffix(monkeypatch, tmp_path, streaming):
    k = load(monkeypatch, tmp_path, "exhaustive")
    h = [{"role": "user", "content": "Verify the workspace."}]
    k._agentic_begin_turn(h, fresh=True)
    k._agentic_begin_final_review(h, {
        "choices": [{
            "message": {"role": "assistant", "content": "Draft",
                        "reasoning_content": "Inspect before editing"},
            "finish_reason": "stop",
        }]
    })
    h.extend([
        {"role": "assistant", "tool_calls": [{
            "id": "test-call", "type": "function",
            "function": {"name": "bash", "arguments": '{"command":"pwd"}'},
        }], "_jack_stage_key": "extended_initial"},
        {"role": "tool", "tool_call_id": "test-call", "content": "workspace", "_jack_stage_key": "extended_initial"},
    ])
    stage = k.STAGES["extended_initial"]
    prepared = k.OpenAICompatibleBackend(k.CFG)._stage_messages_for_profile(h, stage)
    wire = [{"role": "system", "content": k.AGENTIC_STAGE1_PROMPT}] + prepared
    k._agentic_attach_system_stage_control(wire, h, stage)
    k._agentic_stage1_review_put_authenticated_user_last(wire, h, prepared)
    assert wire[-1]["role"] == "tool"
    assert wire[-1]["tool_call_id"] == "test-call"
    assert wire[-2]["role"] == "assistant"
    assert wire[-3] == {"role": "user", "content": k.AGENTIC_FINAL_REVIEW_WIRE_TRIGGER}
    assert sum(m.get("content") == "Verify the workspace." for m in wire) == 1

def test_default_profile_is_balanced_and_both_legacy_toggles_ignored(monkeypatch, tmp_path):
    monkeypatch.delenv('JACK_AGENTIC_PROFILE', raising=False)
    k = load(monkeypatch, tmp_path, 'balanced')
    assert k.CFG.agentic_profile == 'balanced'
    assert not k.CFG.agentic_final_review
    assert not hasattr(k.CFG, 'agentic_stage2_final_review')


def test_exhaustive_is_a_runtime_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "exhaustive")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    name = "active_exhaustive_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    assert module.CFG.agentic_profile == "exhaustive"
    assert module.CFG.agentic_final_review is True
    assert module.STAGES["extended_reflection"].thinking is True


def test_saved_exhaustive_config_remains_exhaustive(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, "balanced")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "config_schema_version": k.CONFIG_SCHEMA_VERSION,
        "agentic_profile": "exhaustive",
        "backend_model": "test-model",
    }), encoding="utf-8")
    monkeypatch.setattr(k, "_config_paths", lambda: (config_path, tmp_path / "secondary.txt"))
    loaded = k._load_cli_config()
    assert loaded["agentic_profile"] == "exhaustive"
    assert k._config_to_env(loaded)["JACK_AGENTIC_PROFILE"] == "exhaustive"
    assert k._config_to_env({"agentic_profile":"exhaustive", **{
        key: val for key, val in loaded.items() if key != "agentic_profile"
    }})["JACK_AGENTIC_PROFILE"] == "exhaustive"
