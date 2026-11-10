"""Agentic authenticated tool-result recovery is independent of SSE transport."""
import asyncio
import copy
import importlib.util
import os
from pathlib import Path
import sys
import time
import types
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "balanced")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_recovery_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


async def install_pending(k, call_id):
    history = [{"role": "user", "content": "Read the clock source."}]
    k._agentic_begin_turn(history, fresh=True)
    k._agentic_turn_status(history, "awaiting_tool")
    state = k.PendingToolResume(
        resume_id="resume-" + call_id,
        stage_key="extended_initial",
        history=copy.deepcopy(history),
        secondary_system="",
        usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        tools=None,
        tool_choice="auto",
        expected_tool_call_ids=(call_id,),
        created_at=time.time(),
    )
    k.KERNEL._pending_tool_resumes[call_id] = state
    return state


@pytest.mark.parametrize("disconnect", ["cancel", "transport_error"])
def test_interrupted_accepted_tool_evidence_is_retryable_and_immutable(
    monkeypatch, tmp_path, disconnect
):
    async def run():
        k = load(monkeypatch, tmp_path)
        call_id = "tool-proof-" + disconnect
        state = await install_pending(k, call_id)
        messages = [
            {"role": "user", "content": "Read the clock source."},
            {"role": "tool", "tool_call_id": call_id, "content": "actual observed source"},
        ]
        original = await k.KERNEL._consume_pending_tool_resume(messages)
        assert original is not None and state.in_flight
        assert len(state.accepted_tool_results) == 1
        assert state.accepted_tool_results[0]["content"] == "actual observed source"
        # A real resumed Stage 1 updates the same host-owned turn.
        k._agentic_begin_turn(state.history, fresh=False)
        scope = {
            "stage1_frozen": False, "bridge_messages": [], "pending_state": state
        }
        token = k._AGENTIC_DELAY_R2_SCOPE.set(scope)
        await k.KERNEL._agentic_phase3g_close_scope(token)
        assert k.KERNEL._pending_tool_resumes[call_id] is state
        assert not state.in_flight
        assert k._agentic_forensic_turn(state.history).status == "awaiting_tool"
        if disconnect == "transport_error":
            # The public SSE wrapper must not convert a retryable transport
            # failure into a terminal forensic failure.
            k._agentic_mark_stage1_failure("SyntheticTransportError")
            assert k._agentic_forensic_turn(state.history).status == "awaiting_tool"

        tampered = copy.deepcopy(messages)
        tampered[-1]["content"] = "substituted output"
        with pytest.raises(k.HTTPException, match="differ from authenticated"):
            await k.KERNEL._consume_pending_tool_resume(tampered)
        assert state.in_flight is False

        unknown = copy.deepcopy(messages)
        unknown[-1]["tool_call_id"] = "not-a-real-checkpoint"
        assert await k.KERNEL._consume_pending_tool_resume(unknown) is None
        assert state.in_flight is False

        second = await k.KERNEL._consume_pending_tool_resume(messages)
        assert second is not None and second[0] is state
        assert second[1][0]["content"] == "actual observed source"
        assert state.in_flight is True
        with pytest.raises(k.HTTPException, match="already being resumed"):
            await k.KERNEL._consume_pending_tool_resume(messages)
        await k.KERNEL._retire_pending_tool_resume(state)
        assert call_id not in k.KERNEL._pending_tool_resumes
    asyncio.run(run())


def test_busy_withheld_tool_fragments_emit_heartbeat(monkeypatch, tmp_path):
    async def run():
        k = load(monkeypatch, tmp_path)
        monkeypatch.setenv("JACK_LOOP_DETECTOR", "0")

        class Backend:
            async def chat_stream(self, **kwargs):
                for segment in ('{"command":"', 'hello', '"}'):
                    yield {
                        "choices": [{"index": 0, "delta": {
                            "tool_calls": [{"index": 0, "id": "call-1", "type": "function",
                                            "function": {"name": "bash", "arguments": segment}}]
                        }, "finish_reason": None}],
                        "usage": {},
                    }
                yield {
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                    "usage": {},
                }

        real_time = time.time
        ticks = iter([0.0, 3.2, 6.4, 9.6, 12.8, 16.0, 19.2, 22.4, 25.6])
        clock = types.SimpleNamespace(time=real_time, monotonic=lambda: next(ticks))
        monkeypatch.setattr(k, "time", clock)
        kernel = k.JackQwenKernel(Backend(), k.CFG)
        packets = []
        stream = kernel._run_stage_streamed(
            [{"role": "user", "content": "Use tool"}], "",
            "extended_initial", {}, tools=None, append=False,
        )
        try:
            async for packet in stream:
                packets.append(packet)
                # Stop before tool-call completion: no executable bytes should
                # have been released while the arguments were still incomplete.
                if packet.get("kind") == "keepalive" and packet.get("event", "").endswith(".busy"):
                    break
        finally:
            await stream.aclose()
        assert any(p.get("kind") == "keepalive" and p.get("event", "").endswith(".busy")
                   for p in packets), packets
        assert all(p.get("kind") != "tool_calls" for p in packets)
    asyncio.run(run())


def test_real_stream_disconnect_retries_same_tool_result_without_reexecuting_tool(
    monkeypatch, tmp_path
):
    async def run():
        k = load(monkeypatch, tmp_path)
        call_id = "streamed-tool-accepted"
        state = await install_pending(k, call_id)
        messages = [
            {"role": "user", "content": "Read the clock source."},
            {"role": "tool", "tool_call_id": call_id, "content": "verified file contents"},
        ]
        started = asyncio.Event()

        class Backend:
            def __init__(self):
                self.calls = 0
                self.closed = 0

            async def chat_stream(self, **kwargs):
                self.calls += 1
                number = self.calls
                try:
                    if number == 1:
                        started.set()
                        yield {"choices": [{"index": 0, "delta": {
                            "reasoning_content": "Resumed model is working."
                        }, "finish_reason": None}], "usage": {}}
                        await asyncio.sleep(3600)
                    else:
                        text = "Frozen useful answer" if number == 2 else "Consequential memory"
                        yield {"choices": [{"index": 0, "delta": {
                            "content": text
                        }, "finish_reason": "stop"}], "usage": {}}
                finally:
                    self.closed += 1

        backend = Backend()
        k.KERNEL.backend = backend
        body = {"messages": messages, "stream": True}
        stream = k.KERNEL.stream(body)
        try:
            # Consume through the first real generated token, then detach
            # the Pi transport while LM Studio's work is unfinished.
            frames = []
            while not started.is_set():
                frames.append(await asyncio.wait_for(anext(stream), timeout=3))
            assert backend.calls == 1
        finally:
            await stream.aclose()
        assert backend.closed == 1
        assert call_id in k.KERNEL._pending_tool_resumes
        assert state.in_flight is False
        assert state.accepted_tool_results[0]["content"] == "verified file contents"
        assert k._agentic_forensic_turn(state.history).status == "awaiting_tool"

        # Identical Pi history reenters the same checkpoint. The agent must
        # not re-execute its completed tool or restart at a fresh user turn.
        frames = [frame async for frame in k.KERNEL.stream(body)]
        rendered = b"".join(frames).decode("utf-8")
        assert backend.calls == 3  # interrupted R1, resumed R1, single Balanced R2
        assert "Frozen useful answer" in rendered
        assert call_id not in k.KERNEL._pending_tool_resumes
        assert state.accepted_tool_results[0]["content"] == "verified file contents"
    asyncio.run(run())


def test_stage2_disconnect_reuses_frozen_stage1_without_regeneration(monkeypatch, tmp_path):
    async def run():
        k = load(monkeypatch, tmp_path)
        call_id = "stage2-tool-result"
        state = await install_pending(k, call_id)
        messages = [
            {"role": "user", "content": "Read the clock source."},
            {"role": "tool", "tool_call_id": call_id, "content": "actual checked source"},
        ]

        class Backend:
            def __init__(self):
                self.calls = 0
                self.closed = 0

            async def chat_stream(self, **kwargs):
                self.calls += 1
                n = self.calls
                try:
                    if n == 1:
                        yield {"choices": [{"index": 0, "delta": {"content": "EXACT A1"},
                                            "finish_reason": "stop"}], "usage": {}}
                    elif n == 2:
                        yield {"choices": [{"index": 0, "delta": {
                            "content": "partial, uncommitted memory"
                        }, "finish_reason": None}], "usage": {}}
                        await asyncio.sleep(3600)
                    else:
                        yield {"choices": [{"index": 0, "delta": {
                            "content": "completed, useful working memory"
                        }, "finish_reason": "stop"}], "usage": {}}
                finally:
                    self.closed += 1

        backend = Backend()
        k.KERNEL.backend = backend
        body = {"messages": messages, "stream": True}
        stream = k.KERNEL.stream(body)
        try:
            while True:
                chunk = await asyncio.wait_for(anext(stream), timeout=3)
                if b"partial, uncommitted memory" in chunk:
                    break
        finally:
            await stream.aclose()

        assert backend.calls == 2
        assert backend.closed == 2
        assert state.frozen_stage1_answer == "EXACT A1"
        assert state.frozen_stage1_history is not None
        assert call_id in k.KERNEL._pending_tool_resumes
        assert not state.in_flight
        assert k._agentic_forensic_turn(state.frozen_stage1_history).status == "stage2_active"

        chunks = [c async for c in k.KERNEL.stream(body)]
        wire = b"".join(chunks).decode("utf-8")
        assert backend.calls == 3, "Stage 1 must never be regenerated after A1 freezes"
        assert "EXACT A1" in wire
        assert "completed, useful working memory" in wire
        assert call_id not in k.KERNEL._pending_tool_resumes
    asyncio.run(run())
