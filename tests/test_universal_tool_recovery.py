"""Shared kernel tool-cycle and malformed-response regression coverage.

Exercises native/Agentic/Deep Research/Deep Reasoning/Code Debugging stages.
No model behavior is graded; all backend outputs are deterministic fixtures.
"""
import asyncio
import importlib.util
import json
import sys
import uuid
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(monkeypatch, tmp_path, mode="x-high", policy="enforce"):
    monkeypatch.setenv("JACK_REASONING_LEVEL", mode)
    monkeypatch.setenv("JACK_TOOL_CYCLE_MODE", policy)
    monkeypatch.setenv("JACK_LOOP_DETECTOR", "1")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_universal_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


def call(i, name, args):
    return {"id": f"universal-{i}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


def history(k, stage, compact):
    h = [{"role": "user", "content": "Build a model and verify it."}]
    for i in range(1, 4):
        for j, (name, args, result) in enumerate([
            ("write", {"path": "resort_model.py", "content": "print(1)"}, "wrote bytes"),
            ("bash", {"command": "python resort_model.py"}, "(no output)")], start=1):
            if i == 3 and j == 2:
                break
            item = call(i * 2 + j, name, args)
            h.append({"role": "assistant", "content": "", "tool_calls": [item],
                      "_jack_internal_tool_exchange": True, "_jack_stage_key": stage})
            h.append({"role": "tool", "tool_call_id": item["id"],
                      "content": result, "_jack_internal_tool_exchange": True})
        if compact:
            h, _, _ = k.KERNEL._roll_tool_frontier(h)
    return h


STAGES = [
    ("x-high", "thesis"),
    ("agentic", "extended_initial"),
    ("deep-research", "extended_synthesis"),
    ("deep-reasoning", "deep_reasoning_synthesis"),
    ("code-debugging", "debug_pass_1"),
]


@pytest.mark.parametrize("mode,stage", STAGES)
@pytest.mark.parametrize("compact", [False, True])
def test_cycle_spans_compacted_and_native_tool_evidence(monkeypatch, tmp_path, mode, stage, compact):
    k = load(monkeypatch, tmp_path, mode)
    h = history(k, stage, compact)
    proposed = call(90, "bash", {"command": "python resort_model.py"})
    assert k._agentic_exact_tool_cycle(h, [proposed], stage_key=stage) == (2, 3)
    assert k._agentic_exact_tool_cycle(h, [proposed], stage_key="different-stage") is None
    changed = call(91, "bash", {"command": "python verify_model.py"})
    assert k._agentic_exact_tool_cycle(h, [changed], stage_key=stage) is None


@pytest.mark.parametrize("mode,stage", STAGES)
def test_all_tool_modes_block_unrecovered_cycle_at_release(monkeypatch, tmp_path, mode, stage):
    k = load(monkeypatch, tmp_path, mode)
    h = history(k, stage, compact=(mode != "agentic"))
    proposed = call(90, "bash", {"command": "python resort_model.py"})
    answer = {"choices": [{"message": {"role": "assistant", "content": "",
                                    "tool_calls": [proposed]}, "finish_reason": "tool_calls"}]}
    async def run():
        with pytest.raises(k.RepeatedToolCycleInterrupt):
            await k.KERNEL._register_stage_tool_resume(
                stage_key=stage, history=h, secondary_system="", usage={},
                tools=[], tool_choice="auto", data=answer)
        assert proposed["id"] not in k.KERNEL._pending_tool_resumes
    asyncio.run(run())


@pytest.mark.parametrize("mode,stage", [("x-high", "thesis"), ("agentic", "extended_initial")])
def test_reasoning_only_tool_syntax_gets_one_structured_streaming_recovery(monkeypatch, tmp_path, mode, stage):
    k = load(monkeypatch, tmp_path, mode)
    h = [{"role": "user", "content": "Finish the Python project."}]
    requests = []

    class Backend:
        async def chat_stream(self, **kwargs):
            requests.append(kwargs)
            if len(requests) == 1:
                yield {"choices": [{"delta": {"reasoning_content": "<|tool_call>call:bash"},
                                   "finish_reason": None}]}
                yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}
            else:
                assert any(msg.get("_jack_internal_protocol_recovery")
                           for msg in kwargs["messages"])
                yield {"choices": [{"delta": {"tool_calls": [
                    dict(call(50, "bash", {"command": "python resort_model.py"}), index=0)
                ]}, "finish_reason": None}]}
                yield {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}
    k.KERNEL.backend = Backend()

    async def run():
        packets = [x async for x in k.KERNEL._run_stage_streamed(
            h, "", stage, {}, tools=[{"type": "function", "function": {
                "name": "bash", "parameters": {"type": "object",
                  "properties": {"command": {"type": "string"}}}}}], tool_choice="auto")]
        result = next(x["data"] for x in packets if x.get("kind") == "result")
        assert result["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "bash"
        assert len(requests) == 2
        assert requests[1]["tools"] is not None
    asyncio.run(run())


def test_malformed_recovery_is_bounded(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    attempts = []
    class Backend:
        async def chat_stream(self, **kwargs):
            attempts.append(kwargs)
            yield {"choices": [{"delta": {"reasoning_content": "thinking only"},
                                "finish_reason": None}]}
            yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}
    k.KERNEL.backend = Backend()
    async def run():
        with pytest.raises(k.HTTPException, match="after one same-stage recovery"):
            async for _ in k.KERNEL._run_stage_streamed(
                [{"role": "user", "content": "Build project"}], "", "thesis", {}):
                pass
    asyncio.run(run())
    assert len(attempts) == 2


def test_shared_stream_guard_recovers_by_changing_action(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = history(k, "thesis", compact=True)
    requests = []
    class Backend:
        async def chat_stream(self, **kwargs):
            requests.append(kwargs)
            cmd = "python resort_model.py" if len(requests) == 1 else "python verify_model.py"
            yield {"choices": [{"delta": {"tool_calls": [
                dict(call(120 + len(requests), "bash", {"command": cmd}), index=0)
            ]}, "finish_reason": None}]}
            yield {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}
    k.KERNEL.backend = Backend()
    async def run():
        packets = [p async for p in k.KERNEL._run_stage_streamed(
            h, "", "thesis", {}, tools=[{"type": "function", "function": {
                "name": "bash", "parameters": {"type": "object",
                "properties": {"command": {"type": "string"}}}}}], tool_choice="auto")]
        result = next(p["data"] for p in packets if p.get("kind") == "result")
        assert "verify_model.py" in result["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
        assert len(requests) == 2
        assert any(x.get("_jack_internal_tool_validation_rejection")
                   for x in requests[1]["messages"])
        assert not any(x.get("_jack_internal_tool_validation_rejection") for x in h)
    asyncio.run(run())
