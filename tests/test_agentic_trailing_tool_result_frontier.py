"""Agentic tool resume: historical replay is evidence, not current authority.

Reproduce the clock incident with a historical checkpoint still live while
a newer tool result is submitted; preserve all current-transaction guards.
No model output quality is involved in these tests.
"""
import asyncio
import copy
import importlib.util
import sys
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "balanced")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "frontier_regression_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def checkpoint(k, call_ids, *, suffix):
    history = [{"role": "user", "content": "Build and verify analog clock webpage."}]
    k._agentic_begin_turn(history, fresh=True)
    k._agentic_turn_status(history, "awaiting_tool")
    state = k.PendingToolResume(
        resume_id="resume-" + suffix,
        stage_key="extended_initial",
        history=copy.deepcopy(history),
        secondary_system="",
        usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        tools=None, tool_choice="auto",
        expected_tool_call_ids=tuple(call_ids),
        created_at=time.time(),
    )
    for call_id in call_ids:
        k.KERNEL._pending_tool_resumes[call_id] = state
    return state


def tool(call_id, content):
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def call(call_id):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": call_id, "type": "function",
         "function": {"name": "bash", "arguments": '{"command":"echo test"}'}}
    ]}


def test_historical_live_checkpoint_must_not_poison_trailing_current_result(monkeypatch, tmp_path):
    async def run():
        k = load(monkeypatch, tmp_path)
        old = checkpoint(k, ["clock-old"], suffix="old")
        current = checkpoint(k, ["clock-current"], suffix="current")
        replay = [
            {"role": "user", "content": "Build clock."},
            call("clock-old"),
            tool("clock-old", "older recorded result"),
            {"role": "assistant", "content": "Continuing the same user task."},
            call("clock-current"),
            tool("clock-current", "latest result"),
        ]
        original = copy.deepcopy(replay)
        resumed = await k.KERNEL._consume_pending_tool_resume(replay)
        assert resumed is not None
        assert resumed[0] is current
        assert [x["tool_call_id"] for x in resumed[1]] == ["clock-current"]
        assert current.accepted_tool_results[0]["content"] == "latest result"
        assert old.accepted_tool_results is None
        assert old.in_flight is False
        assert k.KERNEL._pending_tool_resumes["clock-old"] is old
        assert replay == original, "History preservation must be copy-on-write."
        continuation = k.KERNEL._pending_tool_resume_history(*resumed)
        assert continuation[-1]["tool_call_id"] == "clock-current"
        assert not any(
            m.get("role") == "tool" and m.get("tool_call_id") == "clock-old"
            for m in continuation
        )
        await k.KERNEL._retire_pending_tool_resume(current)
        assert "clock-current" not in k.KERNEL._pending_tool_resumes
        assert "clock-old" in k.KERNEL._pending_tool_resumes
    asyncio.run(run())


def test_genuinely_mixed_current_batch_still_rejected(monkeypatch, tmp_path):
    async def run():
        k = load(monkeypatch, tmp_path)
        first = checkpoint(k, ["live-a"], suffix="a")
        second = checkpoint(k, ["live-b"], suffix="b")
        replay = [{"role": "user", "content": "Task"}, call("live-a"),
                  tool("live-a", "a"), tool("live-b", "b")]
        with pytest.raises(k.HTTPException, match="multiple pending Jack stage transactions"):
            await k.KERNEL._consume_pending_tool_resume(replay)
        assert not first.in_flight and not second.in_flight
        assert first.accepted_tool_results is None
        assert second.accepted_tool_results is None
    asyncio.run(run())


def test_current_batch_rejects_missing_duplicate_and_altered_results(monkeypatch, tmp_path):
    async def run():
        k = load(monkeypatch, tmp_path)
        state = checkpoint(k, ["a", "b"], suffix="pair")
        prefix = [{"role": "user", "content": "Task"}, call("historical"),
                  tool("historical", "safe old evidence"), call("a")]
        with pytest.raises(k.HTTPException, match="Incomplete"):
            await k.KERNEL._consume_pending_tool_resume(prefix + [tool("a", "a")])
        with pytest.raises(k.HTTPException, match="Duplicate"):
            await k.KERNEL._consume_pending_tool_resume(
                prefix + [tool("a", "a"), tool("a", "a"), tool("b", "b")]
            )
        assert state.accepted_tool_results is None
        first = await k.KERNEL._consume_pending_tool_resume(
            prefix + [tool("a", "a"), tool("b", "b")]
        )
        assert first[0] is state
        await k.KERNEL._rearm_pending_tool_resume(state)
        with pytest.raises(k.HTTPException, match="differ from authenticated"):
            await k.KERNEL._consume_pending_tool_resume(
                prefix + [tool("a", "changed"), tool("b", "b")]
            )
        assert not state.in_flight
        assert [m["content"] for m in state.accepted_tool_results] == ["a", "b"]
    asyncio.run(run())


def test_withheld_call_in_current_batch_is_still_rejected(monkeypatch, tmp_path):
    async def run():
        k = load(monkeypatch, tmp_path)
        state = checkpoint(k, ["allowed"], suffix="allowed")
        state.withheld_tool_call_ids = ("denied",)
        request = [{"role": "user", "content": "Task"}, call("allowed"),
                   tool("allowed", "ok"), tool("denied", "untrusted")]
        with pytest.raises(k.HTTPException, match="Jack-withheld"):
            await k.KERNEL._consume_pending_tool_resume(request)
        assert state.accepted_tool_results is None
    asyncio.run(run())
