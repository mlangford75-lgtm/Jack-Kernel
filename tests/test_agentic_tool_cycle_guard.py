"""Jack Agentic loop guard: id-neutral repetition of completed tool transactions.

This intentionally tests deterministic orchestration, not model output quality.
The incident fixture is an exact write/run cycle with stable tool results.
"""
import asyncio
import copy
import importlib.util
import json
import sys
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(monkeypatch, tmp_path, *, profile="balanced", mode="enforce"):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    monkeypatch.setenv("JACK_AGENTIC_TOOL_CYCLE_MODE", mode)
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_cycle_guard_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


def call(name, arguments, id):
    return {"id": id, "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments, ensure_ascii=False),
    }}


def write_call(n, body="print(1)"):
    return call("write", {"path": "resort_model.py", "content": body}, f"write-{n}")


def run_call(n, command="python resort_model.py"):
    return call("bash", {"command": command}, f"run-{n}")


def push(history, tool_call, result="(no output)", *, outcome=None):
    history.append({"role": "assistant", "content": "", "tool_calls": [tool_call],
                    "_jack_internal_tool_exchange": True, "_jack_stage_key": "extended_initial"})
    item = {"role": "tool", "tool_call_id": tool_call["id"], "content": result,
            "_jack_internal_tool_exchange": True}
    if outcome is not None:
        item["_jack_tool_outcome"] = outcome
    history.append(item)


def incident(history, *, runs=2, content="print(1)"):
    for i in range(1, runs + 1):
        push(history, write_call(i, content), "wrote 9 bytes")
        push(history, run_call(i), "(no output)")
    push(history, write_call(runs + 1, content), "wrote 9 bytes")


@pytest.mark.parametrize("profile", ["flash", "balanced", "thorough"])
def test_exact_stable_write_run_cycle_is_detected_without_ids(monkeypatch, tmp_path, profile):
    k = load(monkeypatch, tmp_path, profile=profile)
    h = [{"role": "user", "content": "Build and verify a model"}]
    k._agentic_begin_turn(h, fresh=True)
    incident(h)
    assert k._agentic_exact_tool_cycle(h, [run_call(3)]) == (2, 3)
    assert k._agentic_exact_tool_cycle(h, [write_call(4)]) is None


def test_no_detection_before_repetitions(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Build a model"}]
    k._agentic_begin_turn(h, fresh=True)
    push(h, write_call(1), "wrote 9 bytes")
    push(h, run_call(1), "(no output)")
    push(h, write_call(2), "wrote 9 bytes")
    assert k._agentic_exact_tool_cycle(h, [run_call(2)]) is None


def test_changed_content_breaks_cycle(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Build a model"}]
    k._agentic_begin_turn(h, fresh=True)
    push(h, write_call(1), "wrote 9 bytes")
    push(h, run_call(1), "(no output)")
    push(h, write_call(2, "print(2)"), "wrote 9 bytes")
    push(h, run_call(2), "(no output)")
    push(h, write_call(3), "wrote 9 bytes")
    assert k._agentic_exact_tool_cycle(h, [run_call(3)]) is None


def test_different_tool_results_break_cycle(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Build a model"}]
    k._agentic_begin_turn(h, fresh=True)
    push(h, write_call(1), "wrote 9 bytes")
    push(h, run_call(1), "(no output)")
    push(h, write_call(2), "wrote 9 bytes")
    push(h, run_call(2), "test result changed")
    push(h, write_call(3), "wrote 9 bytes")
    assert k._agentic_exact_tool_cycle(h, [run_call(3)]) is None


def test_no_guard_for_nonmutating_polling_or_confirmed_failure(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Monitor until a process completes"}]
    k._agentic_begin_turn(h, fresh=True)
    for i in range(2):
        push(h, run_call(i, "ls"), "(no output)")
    assert k._agentic_exact_tool_cycle(h, [run_call(3, "ls")]) is None
    h = [{"role": "user", "content": "Fix a failing program"}]
    k._agentic_begin_turn(h, fresh=True)
    push(h, write_call(1), "wrote 9 bytes")
    push(h, run_call(1), "failed", outcome=k.TOOL_FAILED)
    push(h, write_call(2), "wrote 9 bytes")
    push(h, run_call(2), "failed", outcome=k.TOOL_FAILED)
    push(h, write_call(3), "wrote 9 bytes")
    assert k._agentic_exact_tool_cycle(h, [run_call(3)]) is None


def test_missing_result_never_authorizes_interrupt(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Build a model"}]
    k._agentic_begin_turn(h, fresh=True)
    incident(h)
    h.pop()  # last call's result is not known
    assert k._agentic_exact_tool_cycle(h, [run_call(3)]) is None


def test_canonical_json_key_order(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Build a model"}]
    k._agentic_begin_turn(h, fresh=True)
    incident(h)
    assert k._agentic_exact_tool_cycle(h, [{"id": "new", "function": {"name": "bash", "arguments": '{"command":"python resort_model.py"}'}}]) == (2, 3)


def test_gate_prevents_checkpoint_and_executable_release(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Build and verify the model"}]
    k._agentic_begin_turn(h, fresh=True)
    incident(h)
    candidate = run_call(3)
    result = {"choices": [{"message": {"role": "assistant", "tool_calls": [candidate]}, "finish_reason": "tool_calls"}]}

    async def scenario():
        with pytest.raises(k.RepeatedToolCycleInterrupt, match="Repeated Tool Cycle Failure"):
            await k.KERNEL._register_stage_tool_resume(
                stage_key="extended_initial", history=h, secondary_system="", usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                tools=[], tool_choice="auto", data=result,
            )
        assert candidate["id"] not in k.KERNEL._pending_tool_resumes
        assert not k._agentic_forensic_turn(h).frozen_a1_sha256

    asyncio.run(scenario())


@pytest.mark.parametrize("mode,blocked", [("observe", False), ("off", False), ("enforce", True)])
def test_mode_switch(monkeypatch, tmp_path, mode, blocked):
    k = load(monkeypatch, tmp_path, mode=mode)
    h = [{"role": "user", "content": "Build and verify the model"}]
    k._agentic_begin_turn(h, fresh=True)
    incident(h)
    candidate = run_call(3)
    result = {"choices": [{"message": {"role": "assistant", "tool_calls": [candidate]}, "finish_reason": "tool_calls"}]}

    async def scenario():
        if blocked:
            with pytest.raises(k.RepeatedToolCycleInterrupt):
                await k.KERNEL._register_stage_tool_resume(
                    stage_key="extended_initial", history=h, secondary_system="", usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    tools=[], tool_choice="auto", data=result)
            assert candidate["id"] not in k.KERNEL._pending_tool_resumes
        else:
            await k.KERNEL._register_stage_tool_resume(
                stage_key="extended_initial", history=h, secondary_system="", usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                tools=[], tool_choice="auto", data=result)
            assert candidate["id"] in k.KERNEL._pending_tool_resumes

    asyncio.run(scenario())


def test_disabling_parent_loop_detector_disables_tool_cycle_guard(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_LOOP_DETECTOR", "0")
    k = load(monkeypatch, tmp_path, mode="enforce")
    h = [{"role": "user", "content": "Build and verify the model"}]
    k._agentic_begin_turn(h, fresh=True)
    incident(h)
    candidate = run_call(3)
    data = {"choices": [{"message": {"role": "assistant", "tool_calls": [candidate]}, "finish_reason": "tool_calls"}]}

    async def scenario():
        await k.KERNEL._register_stage_tool_resume(
            stage_key="extended_initial", history=h, secondary_system="",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            tools=[], tool_choice="auto", data=data)
        assert candidate["id"] in k.KERNEL._pending_tool_resumes

    asyncio.run(scenario())


@pytest.mark.parametrize("mode,should_interrupt", [("enforce", True), ("observe", False)])
def test_streamed_authenticated_tool_resume_is_terminal_only_on_enforced_cycle(
    monkeypatch, tmp_path, mode, should_interrupt
):
    """A detected loop must not rearm its already-consumed tool checkpoint."""
    async def scenario():
        k = load(monkeypatch, tmp_path, mode=mode)
        h = [{"role": "user", "content": "Build and verify the financial model"}]
        k._agentic_begin_turn(h, fresh=True)
        for i in (1, 2):
            push(h, write_call(i), "wrote 9 bytes")
            push(h, run_call(i), "(no output)")
        last = write_call(3)
        h.append({"role": "assistant", "content": "", "tool_calls": [last],
                  "_jack_internal_tool_exchange": True,
                  "_jack_stage_key": "extended_initial"})
        k._agentic_turn_status(h, "awaiting_tool")
        state = k.PendingToolResume(
            resume_id="resume-last-write", stage_key="extended_initial", history=h,
            secondary_system="", usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            tools=[{"type": "function", "function": {"name": "bash", "parameters": {
                "type": "object", "properties": {"command": {"type": "string"}}
            }}}],
            tool_choice="auto", expected_tool_call_ids=("write-3",),
            created_at=time.time(),
        )
        k.KERNEL._pending_tool_resumes["write-3"] = state

        class StreamedBackend:
            def __init__(self):
                self.calls = 0

            async def chat_stream(self, **kwargs):
                self.calls += 1
                proposed = run_call(3)
                yield {"choices": [{"index": 0, "delta": {
                    "tool_calls": [dict(proposed, index=0)]
                }, "finish_reason": None}], "usage": {}}
                yield {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                       "usage": {}}

        backend = StreamedBackend()
        k.KERNEL.backend = backend
        body = {"messages": [
            {"role": "user", "content": "Build and verify the financial model"},
            {"role": "tool", "tool_call_id": "write-3", "content": "wrote 9 bytes"},
        ], "stream": True, "tools": state.tools, "tool_choice": "auto"}
        wire = b"".join([frame async for frame in k._safe_public_stream(body)]).decode("utf-8")
        record = k._agentic_forensic_turn(state.history)
        # Enforced cycles get one same-stage correction; observe releases directly.
        assert backend.calls == (2 if should_interrupt else 1)
        assert "write-3" not in k.KERNEL._pending_tool_resumes
        if should_interrupt:
            assert "Repeated Tool Cycle Failure" in wire
            assert '"tool_calls"' not in wire
            assert "run-3" not in k.KERNEL._pending_tool_resumes
            assert record.status == "stage1_failed"
            assert not record.frozen_a1_sha256
        else:
            assert "Repeated Tool Cycle Failure" not in wire
            assert '"tool_calls"' in wire
            assert "run-3" in k.KERNEL._pending_tool_resumes
            assert record.status == "awaiting_tool"

    asyncio.run(scenario())
