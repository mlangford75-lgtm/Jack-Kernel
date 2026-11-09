"""Two distinct streaming Stage-1 continuations: verification then alignment."""
import asyncio
import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(monkeypatch, tmp_path, *, verify=True, align=True):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "balanced")
    monkeypatch.setenv("JACK_AGENTIC_FINAL_REVIEW", "1" if align else "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE1_VERIFY_BEFORE_ALIGNMENT", "1" if verify else "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_FINAL_REVIEW", "0")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "unit-test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_LOOP_DETECTOR", "0")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_verify_align_" + uuid.uuid4().hex
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
def test_three_stage1_generations_verification_before_alignment(monkeypatch, tmp_path, stream):
    k = load(monkeypatch, tmp_path)
    class Backend:
        def __init__(self):
            self.calls = []
        async def chat(self, *, messages, **kwargs):
            self.calls.append([dict(m) for m in messages])
            n = len(self.calls)
            return stage_result(["Draft", "Verified provisional", "Aligned final"][n-1], f"R{n}")
        async def chat_stream(self, *, messages, **kwargs):
            self.calls.append([dict(m) for m in messages])
            n = len(self.calls)
            yield {"choices": [{"index": 0, "delta": {"reasoning_content": f"R{n}"}, "finish_reason": None}]}
            yield {"choices": [{"index": 0, "delta": {"content": ["Draft", "Verified provisional", "Aligned final"][n-1]}, "finish_reason": None}]}
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
            "Draft", "Verified provisional", "Aligned final"]
        result = results[0]
    else:
        result = asyncio.run(kernel._run_stage(h, "", "extended_initial", usage, append=False))
    assert len(b.calls) == 3
    assert b.calls[0][-1]["content"] == "Verify a claim using available tools."
    assert b.calls[1][-1]["content"] == k.AGENTIC_STAGE1_VERIFICATION_TRIGGER
    assert b.calls[2][-1]["content"] == k.AGENTIC_FINAL_REVIEW_TRIGGER
    assert b.calls[1][-1]["content"].count(k.AGENTIC_STAGE1_VERIFICATION_PROMPT) == 1
    assert b.calls[2][-1]["content"].count(k.AGENTIC_FINAL_REVIEW_PROMPT) == 1
    assert b.calls[2][-2]["content"] == "Verified provisional"
    assert len([x for x in h if x.get("_jack_internal_agentic_stage1_verification_trigger")]) == 1
    assert len([x for x in h if x.get("_jack_internal_agentic_final_review_trigger")]) == 1
    assert k.active_response_target(h)["content"] == "Verify a claim using available tools."
    assert result["choices"][0]["message"]["content"] == "Aligned final"
    assert k.extended_stage1_reasoning_trace(h, result["choices"][0]["message"]) == "R1\n\nR2\n\nR3"
    assert usage["completion_tokens"] == 15


@pytest.mark.parametrize("verify,align,expected", [
    (False, False, 1),
    (True, False, 1),
    (False, True, 2),
])
def test_switches_and_legacy_behavior(monkeypatch, tmp_path, verify, align, expected):
    k = load(monkeypatch, tmp_path, verify=verify, align=align)
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
    assert not k._agentic_stage1_verification_is_pending(h)
    assert k._agentic_final_review_is_pending(h) == (align and expected == 2)


def test_verification_and_alignment_share_turn_identity_without_a1_freeze(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Original"}]
    k._agentic_begin_turn(h, fresh=True)
    original = k._agentic_forensic_turn(h).turn_id
    k._agentic_begin_stage1_verification(h, stage_result("First draft", "R0"))
    assert k._agentic_forensic_turn(h).turn_id == original
    assert k._agentic_forensic_turn(h).status == "stage1_active"
    assert not any(m.get("_jack_extended_candidate_response") for m in h)
    k._agentic_begin_final_review(h, stage_result("Second draft", "R1"))
    assert k._agentic_forensic_turn(h).turn_id == original
    assert k.active_response_target(h)["content"] == "Original"
    assert len([x for x in h if x.get("_jack_internal_agentic_stage1_verification_trigger")]) == 1
    assert len([x for x in h if x.get("_jack_internal_agentic_final_review_trigger")]) == 1
    with pytest.raises(k.HTTPException, match="already started"):
        k._agentic_begin_stage1_verification(h, stage_result("Duplicate", "R2"))


@pytest.mark.parametrize("stream", [False, True])
def test_verification_tool_resume_moves_to_alignment_once(monkeypatch, tmp_path, stream):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Inspect the local clock workspace."}]
    k._agentic_begin_turn(h, fresh=True)
    k._agentic_begin_stage1_verification(h, stage_result("Initial draft", "Initial reasoning"))
    # Simulate the host's normal validated tool checkpoint and Pi's tool result
    # during the first verification continuation. The verification cue remains
    # in canonical history across resume and must not be fired a second time.
    h.extend([
        {"role": "assistant", "tool_calls": [
            {"id": "tool-verify-1", "type": "function",
             "function": {"name": "bash", "arguments": '{"command":"ls -a"}'}}],
         "_jack_stage_key": "extended_initial"},
        {"role": "tool", "tool_call_id": "tool-verify-1", "content": ".\\n..\\n"},
    ])
    class Backend:
        def __init__(self):
            self.calls = []
        async def chat(self, *, messages, **kwargs):
            self.calls.append([dict(m) for m in messages])
            return stage_result("Verified" if len(self.calls) == 1 else "Aligned", "R")
        async def chat_stream(self, *, messages, **kwargs):
            self.calls.append([dict(m) for m in messages])
            content = "Verified" if len(self.calls) == 1 else "Aligned"
            yield {"choices": [{"index": 0, "delta": {"reasoning_content": "R"}, "finish_reason": None}]}
            yield {"choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}]}
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
    assert len(b.calls) == 2
    assert b.calls[0][-1]["role"] == "tool"
    assert b.calls[0][-1]["content"] == ".\\n..\\n"
    assert b.calls[1][-1]["content"] == k.AGENTIC_FINAL_REVIEW_TRIGGER
    assert result["choices"][0]["message"]["content"] == "Aligned"
    assert len([x for x in h if x.get("_jack_internal_agentic_stage1_verification_trigger")]) == 1
    assert len([x for x in h if x.get("_jack_internal_agentic_final_review_trigger")]) == 1
