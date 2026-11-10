"""Opt-in Agentic one-shot final-review continuation before A1 freeze.

The test isolates Jack's transaction behavior from stochastic model competence.
"""
import asyncio
import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ("Wait, more verification is needed. Test the reasoning for errors, mistakes, or poor quality. Make changes, if necessary"
          "Hold on, ensure the response is in full alignment with user request")


def load(monkeypatch, tmp_path, enabled):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "balanced")
    monkeypatch.setenv("JACK_AGENTIC_FINAL_REVIEW", "1" if enabled else "0")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "unit-test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_LOOP_DETECTOR", "0")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_review_test_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def stage_result(content, reasoning):
    return {
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content, "reasoning_content": reasoning},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def test_exact_prompt_and_single_same_turn_review_nonstream(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, True)
    class Backend:
        def __init__(self):
            self.calls = []
        async def chat(self, *, messages, **kwargs):
            self.calls.append([dict(m) for m in messages])
            return stage_result(
                "Unverified draft" if len(self.calls) == 1 else "Corrected final",
                "reasoning-1" if len(self.calls) == 1 else "reasoning-2"
            )
    backend = Backend()
    kernel = k.JackQwenKernel(backend, k.CFG)
    history = [{"role": "user", "content": "What is 7*8?"}]
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    result = asyncio.run(kernel._run_stage(history, "", "extended_initial", usage, append=False))
    assert len(backend.calls) == 2
    assert backend.calls[0] == [{"role": "user", "content": "What is 7*8?", "_jack_agentic_turn_id": history[0]["_jack_agentic_turn_id"]}]
    assert backend.calls[1][-1]["content"] == PROMPT
    assert backend.calls[1][-1]["content"] == k.AGENTIC_FINAL_REVIEW_TRIGGER
    assert backend.calls[1][-1]["_jack_internal_agentic_final_review_trigger"] is True
    assert backend.calls[1][-2]["content"] == "Unverified draft"
    assert backend.calls[1][-2]["reasoning_content"] == "reasoning-1"
    assert k.active_response_target(history)["content"] == "What is 7*8?"
    assert result["choices"][0]["message"]["content"] == "Corrected final"
    assert k.extended_stage1_reasoning_trace(history, result["choices"][0]["message"]) == "reasoning-1\n\nreasoning-2"
    assert usage["completion_tokens"] == 10


def test_review_streams_second_generation_and_does_not_repeat(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, True)
    class Backend:
        def __init__(self):
            self.calls = []
        async def chat_stream(self, *, messages, **kwargs):
            self.calls.append([dict(m) for m in messages])
            n = len(self.calls)
            yield {"choices": [{"index": 0, "delta": {"reasoning_content": f"reason-{n}"}, "finish_reason": None}]}
            yield {"choices": [{"index": 0, "delta": {"content": "Draft" if n == 1 else "Revised"}, "finish_reason": None}]}
            yield {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                   "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
    backend = Backend()
    kernel = k.JackQwenKernel(backend, k.CFG)
    history = [{"role": "user", "content": "Check the answer."}]
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    async def run():
        return [p async for p in kernel._run_stage_streamed(
            history, "", "extended_initial", usage, append=False
        )]
    packets = asyncio.run(run())
    assert len(backend.calls) == 2
    assert backend.calls[1][-1]["content"] == k.AGENTIC_FINAL_REVIEW_TRIGGER
    results = [p["data"] for p in packets if p["kind"] == "result"]
    assert len(results) == 1
    assert results[0]["choices"][0]["message"]["content"] == "Revised"
    assert k.active_response_target(history)["content"] == "Check the answer."
    assert len([m for m in history if m.get("_jack_internal_agentic_final_review_trigger")]) == 1
    assert [p["text"] for p in packets if p["kind"] == "content"] == ["Draft", "Revised"]


def test_default_path_has_no_review(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, False)
    class Backend:
        def __init__(self):
            self.calls = 0
        async def chat(self, **kwargs):
            self.calls += 1
            return stage_result("Original answer", "one reason")
    backend = Backend()
    history = [{"role": "user", "content": "Hello"}]
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    result = asyncio.run(k.JackQwenKernel(backend, k.CFG)._run_stage(
        history, "", "extended_initial", usage, append=False
    ))
    assert backend.calls == 1
    assert result["choices"][0]["message"]["content"] == "Original answer"
    assert not k._agentic_final_review_is_pending(history)


def test_review_draft_is_not_frozen_a1(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, True)
    history = [{"role": "user", "content": "Task"}]
    k._agentic_begin_turn(history, fresh=True)
    k._agentic_begin_final_review(history, stage_result("Draft only", "R0"))
    assert k._agentic_forensic_turn(history).status == "stage1_active"
    assert not any(m.get("_jack_extended_candidate_response") for m in history)
    assert k._agentic_final_review_is_pending(history)
    with pytest.raises(k.HTTPException, match="already started"):
        k._agentic_begin_final_review(history, stage_result("Duplicate", "R1"))


def test_review_transport_trigger_does_not_retarget_user_request(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, True)
    history = [{"role": "user", "content": "The original task is to verify the clock workspace."}]
    k._agentic_begin_turn(history, fresh=True)
    original_id = k._agentic_forensic_turn(history).turn_id
    k._agentic_begin_final_review(history, stage_result("Initial answer", "Initial reasoning"))
    assert k.active_response_target(history)["content"] == "The original task is to verify the clock workspace."
    assert k._agentic_forensic_turn(history).turn_id == original_id
    assert k._agentic_final_review_is_pending(history)
    assert history[-1]["content"] == k.AGENTIC_FINAL_REVIEW_PROMPT
    assert history[-1]["_jack_internal_agentic_final_review_trigger"] is True
    assert history[-1]["content"].count(k.AGENTIC_FINAL_REVIEW_PROMPT) == 1
