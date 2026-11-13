"""Profile-scoped Stage-1 verification and alignment continuation, streamed or nonstream."""
import asyncio
import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMBINED_PROMPT = "Wait, re-verify your reasoning. Test for errors, mistakes, or poor quality. Make changes, if necessary, to ensure alignment with the instructions and user request before responding"


def load(monkeypatch, tmp_path, *, enabled=True):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "exhaustive" if enabled else "balanced")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "unit-test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_LOOP_DETECTOR", "0")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_combined_review_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


def stage_result(content, reason):
    return {"choices": [{"index": 0, "message": {"role": "assistant", "content": content,
           "reasoning_content": reason}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


@pytest.mark.parametrize("stream", [False, True])
def test_combined_checks_run_in_exactly_one_continuation(monkeypatch, tmp_path, stream):
    k = load(monkeypatch, tmp_path)
    class Backend:
        def __init__(self):
            self.calls = []
        async def chat(self, *, messages, **kwargs):
            self.calls.append([dict(m) for m in messages])
            return stage_result("Draft" if len(self.calls) == 1 else "Verified and aligned", f"R{len(self.calls)}")
        async def chat_stream(self, *, messages, **kwargs):
            self.calls.append([dict(m) for m in messages])
            n = len(self.calls)
            yield {"choices": [{"index": 0, "delta": {"reasoning_content": f"R{n}"}, "finish_reason": None}]}
            yield {"choices": [{"index": 0, "delta": {"content": "Draft" if n == 1 else "Verified and aligned"}, "finish_reason": None}]}
            yield {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                   "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
    b = Backend()
    kernel = k.JackQwenKernel(b, k.CFG)
    h = [{"role": "user", "content": "Verify a claim using available tools."}]
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if stream:
        async def run():
            return [p async for p in kernel._run_stage_streamed(h, "", "extended_initial", usage, append=False)]
        packets = asyncio.run(run())
        results = [p["data"] for p in packets if p["kind"] == "result"]
        assert len(results) == 1
        assert [p["text"] for p in packets if p["kind"] == "content"] == [
            "Draft", "Verified and aligned"]
        result = results[0]
    else:
        result = asyncio.run(kernel._run_stage(h, "", "extended_initial", usage, append=False))
    assert len(b.calls) == 2
    assert b.calls[0][-1]["content"] == "Verify a claim using available tools."
    assert b.calls[1][-1]["content"] == k.AGENTIC_FINAL_REVIEW_TRIGGER
    assert b.calls[1][-1]["content"] == k.AGENTIC_FINAL_REVIEW_TRIGGER
    assert b.calls[1][-2]["content"] == "Draft"
    assert len([x for x in h if x.get("_jack_internal_agentic_final_review_trigger")]) == 1
    assert not any(x.get("_jack_internal_agentic_stage1_verification_trigger") for x in h)
    assert k.active_response_target(h)["content"] == "Verify a claim using available tools."
    assert result["choices"][0]["message"]["content"] == "Verified and aligned"
    assert k.extended_stage1_reasoning_trace(h, result["choices"][0]["message"]) == "R1\n\nR2"
    assert usage["completion_tokens"] == 10


@pytest.mark.parametrize("enabled,expected", [(False, 1), (True, 2)])
def test_single_switch_and_disabled_path(monkeypatch, tmp_path, enabled, expected):
    k = load(monkeypatch, tmp_path, enabled=enabled)
    class Backend:
        def __init__(self):
            self.calls = 0
        async def chat(self, **kwargs):
            self.calls += 1
            return stage_result(f"Result {self.calls}", f"Reason {self.calls}")
    b = Backend()
    h = [{"role": "user", "content": "Original task."}]
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    result = asyncio.run(k.JackQwenKernel(b, k.CFG)._run_stage(
        h, "", "extended_initial", usage, append=False))
    assert b.calls == expected
    assert result["choices"][0]["message"]["content"] == f"Result {expected}"
    assert k._agentic_final_review_is_pending(h) == enabled


def test_combined_review_keeps_turn_id_and_a1_unfrozen(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Original"}]
    k._agentic_begin_turn(h, fresh=True)
    original = k._agentic_forensic_turn(h).turn_id
    k._agentic_begin_final_review(h, stage_result("First draft", "R0"))
    assert k._agentic_forensic_turn(h).turn_id == original
    assert k._agentic_forensic_turn(h).status == "stage1_active"
    assert not any(m.get("_jack_extended_candidate_response") for m in h)
    assert k.active_response_target(h)["content"] == "Original"
    assert len([x for x in h if x.get("_jack_internal_agentic_final_review_trigger")]) == 1
    with pytest.raises(k.HTTPException, match="already started"):
        k._agentic_begin_final_review(h, stage_result("Duplicate", "R1"))


@pytest.mark.parametrize("stream", [False, True])
def test_combined_review_tool_resume_does_not_restart_extension(monkeypatch, tmp_path, stream):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Inspect the local clock workspace."}]
    k._agentic_begin_turn(h, fresh=True)
    k._agentic_begin_final_review(h, stage_result("Initial draft", "Initial reasoning"))
    h.extend([
        {"role": "assistant", "tool_calls": [
            {"id": "tool-review-1", "type": "function",
             "function": {"name": "bash", "arguments": '{"command":"ls -a"}'}}],
         "_jack_stage_key": "extended_initial"},
        {"role": "tool", "tool_call_id": "tool-review-1", "content": ".\\n..\\n"},
    ])
    class Backend:
        def __init__(self):
            self.calls = []
        async def chat(self, *, messages, **kwargs):
            self.calls.append([dict(m) for m in messages])
            return stage_result("Verified and aligned", "R")
        async def chat_stream(self, *, messages, **kwargs):
            self.calls.append([dict(m) for m in messages])
            yield {"choices": [{"index": 0, "delta": {"reasoning_content": "R"}, "finish_reason": None}]}
            yield {"choices": [{"index": 0, "delta": {"content": "Verified and aligned"}, "finish_reason": None}]}
            yield {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                   "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
    b = Backend()
    kernel = k.JackQwenKernel(b, k.CFG)
    u = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if stream:
        async def run():
            return [x async for x in kernel._run_stage_streamed(
                h, "", "extended_initial", u, append=False, same_stage_resume=True)]
        packets = asyncio.run(run())
        results = [x["data"] for x in packets if x["kind"] == "result"]
        assert len(results) == 1
        result = results[0]
    else:
        result = asyncio.run(kernel._run_stage(
            h, "", "extended_initial", u, append=False, same_stage_resume=True))
    assert len(b.calls) == 1
    assert b.calls[0][-1]["role"] == "tool"
    assert result["choices"][0]["message"]["content"] == "Verified and aligned"
    assert len([x for x in h if x.get("_jack_internal_agentic_final_review_trigger")]) == 1
