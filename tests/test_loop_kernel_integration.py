"""Kernel-level loop retry, fresh-turn ownership, and cancellation regressions."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import importlib.util
import os
from pathlib import Path
import sys
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(monkeypatch, tmp_path, *, mode="off", enabled=True, repetitions=16):
    monkeypatch.setenv("JACK_REASONING_LEVEL", mode)
    monkeypatch.setenv("JACK_LOOP_DETECTOR", "1" if enabled else "0")
    monkeypatch.setenv("JACK_LOOP_REPETITIONS", str(repetitions))
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / ("forensic-" + uuid.uuid4().hex + ".sqlite3")))
    name = "jack_loop_integration_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def repeated_reasoning(repetitions=16):
    cycle = [f"unique_word_{i}" for i in range(128)]
    return " ".join(cycle * repetitions) + " "


class FakeBackend:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = 0
        self.closed = 0

    async def chat_stream(self, **kwargs):
        call = self.calls
        self.calls += 1
        item = self.payloads[call]
        try:
            yield {
                "choices": [{"index": 0, "delta": {"reasoning_content": item},
                             "finish_reason": None}],
                "usage": {},
            }
            yield {
                "choices": [{"index": 0, "delta": {"content": "completed"},
                             "finish_reason": "stop"}],
                "usage": {},
            }
        finally:
            self.closed += 1

    async def chat(self, **kwargs):
        raise AssertionError("nonstream fallback must not run")


def run_stage(k, kernel, name="thesis", history=None):
    async def go():
        return [
            packet async for packet in kernel._run_stage_streamed(
                history if history is not None else [{"role": "user", "content": "Do it"}],
                "", name, {}, append=False,
            )
        ]
    return asyncio.run(go())


def test_first_loop_retries_once_then_completes(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    backend = FakeBackend([repeated_reasoning(), "new healthy reasoning"])
    kernel = k.JackQwenKernel(backend, k.CFG)
    packets = run_stage(k, kernel)
    assert backend.calls == 2
    assert backend.closed == 2
    assert "retrying once" in " ".join(p.get("text", "") for p in packets)
    assert packets[-1]["kind"] == "result"
    assert packets[-1]["data"]["choices"][0]["message"]["content"] == "completed"


def test_second_loop_is_terminal_and_closes_backend(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    backend = FakeBackend([repeated_reasoning(), repeated_reasoning()])
    kernel = k.JackQwenKernel(backend, k.CFG)
    with pytest.raises(k.RepeatedLoopInterrupt):
        run_stage(k, kernel)
    assert backend.calls == 2
    assert backend.closed == 2


def test_disabled_loop_detector_does_not_trigger(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, enabled=False)
    backend = FakeBackend([repeated_reasoning()])
    kernel = k.JackQwenKernel(backend, k.CFG)
    packets = run_stage(k, kernel)
    assert backend.calls == 1
    assert packets[-1]["kind"] == "result"


def test_fresh_user_turn_ignores_old_tool_result(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, mode="Local Agentic (Preserve Thinking)")
    async def go():
        kernel = k.KERNEL
        state = k.PendingToolResume(
            resume_id="aborted-session", stage_key="extended_initial",
            history=[{"role": "user", "content": "original work"}],
            secondary_system="", usage={}, tools=None, tool_choice=None,
            expected_tool_call_ids=("old-tool-123",), created_at=__import__("time").time(),
        )
        kernel._pending_tool_resumes["old-tool-123"] = state
        incoming = [
            {"role": "user", "content": "original work"},
            {"role": "assistant", "content": "", "tool_calls": []},
            {"role": "tool", "tool_call_id": "old-tool-123", "content": "done"},
            {"role": "user", "content": "new real user request"},
        ]
        assert await kernel._consume_pending_tool_resume(incoming) is None
        assert state.in_flight is False
    asyncio.run(go())


def test_cancelled_resumed_checkpoint_is_retired(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, mode="Local Agentic (Preserve Thinking)")
    async def go():
        kernel = k.KERNEL
        state = k.PendingToolResume(
            resume_id="interrupted", stage_key="extended_initial",
            history=[{"role": "user", "content": "ongoing"}],
            secondary_system="", usage={}, tools=None, tool_choice=None,
            expected_tool_call_ids=("tool-interrupted",), created_at=0.0,
        )
        kernel._pending_tool_resumes["tool-interrupted"] = state
        scope = {"stage1_frozen": False, "bridge_messages": [], "pending_state": state}
        token = k._AGENTIC_DELAY_R2_SCOPE.set(scope)
        await kernel._agentic_phase3g_close_scope(token)
        assert "tool-interrupted" not in kernel._pending_tool_resumes
    asyncio.run(go())


def test_agentic_stage1_retry_changes_attempt_not_turn(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, mode="Local Agentic (Preserve Thinking)")
    backend = FakeBackend([repeated_reasoning(), "useful reasoning"])
    kernel = k.JackQwenKernel(backend, k.CFG)
    h = [{"role": "user", "content": "Make this clock work"}]
    packets = run_stage(k, kernel, name="extended_initial", history=h)
    assert packets[-1]["kind"] == "result"
    assert backend.calls == 2
    record = k._agentic_forensic_turn(h)
    assert record is not None
    assert record.status == "stage1_active"
    events = k._agentic_forensic_journal().events(record.turn_id)
    statuses = [e["status"] for e in events]
    assert statuses.count("stage1_active") == 2
    assert "stage1_failed" in statuses
