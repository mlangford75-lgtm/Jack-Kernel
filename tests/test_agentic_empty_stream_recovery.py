"""Agentic empty SSE recovery never replays completed tools or changes the turn."""
import asyncio
import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "balanced")
    monkeypatch.setenv("JACK_AGENTIC_FINAL_REVIEW", "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE1_VERIFY_BEFORE_ALIGNMENT", "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_FINAL_REVIEW", "0")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_LOOP_DETECTOR", "0")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "agentic_empty_recovery_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


def response(text=None):
    return {"choices": [{"index": 0, "delta": ({"content": text} if text else {}),
             "finish_reason": "stop"}], "usage": {}}


@pytest.mark.parametrize("after_tools", [False, True])
def test_single_empty_retries_same_stream_without_replaying_tools(monkeypatch, tmp_path, after_tools):
    async def run():
        k = load(monkeypatch, tmp_path)
        class Backend:
            def __init__(self):
                self.calls = []
            async def chat_stream(self, **kwargs):
                self.calls.append(kwargs)
                yield response("Recovered answer" if len(self.calls) == 2 else None)
        b = Backend()
        kernel = k.JackQwenKernel(b, k.CFG)
        h = [{"role": "user", "content": "Inspect workspace"}]
        if after_tools:
            h.extend([
                {"role": "assistant", "content": "", "tool_calls": [
                    {"id": "already-ran", "type": "function",
                     "function": {"name": "bash", "arguments": '{"command":"ls"}'}}]},
                {"role": "tool", "tool_call_id": "already-ran", "content": "(no output)"},
            ])
        tools = [{"type": "function", "function": {"name": "bash", "parameters": {
            "type": "object", "properties": {"command": {"type": "string"}}}}}]
        packets = [p async for p in kernel._run_stage_streamed(
            h, "", "extended_initial", {}, tools=tools, tool_choice="auto",
            same_stage_resume=after_tools, append=False)]
        assert len(b.calls) == 2, "only one streaming retry is allowed"
        assert b.calls[0]["messages"] is h and b.calls[1]["messages"] is h
        if after_tools:
            assert b.calls[1]["tools"] is None
            assert b.calls[1]["tool_choice"] == "none"
        results = [p["data"] for p in packets if p["kind"] == "result"]
        assert len(results) == 1
        assert results[0]["choices"][0]["message"]["content"] == "Recovered answer"
        assert sum(x.get("role") == "tool" for x in h) == int(after_tools)
    asyncio.run(run())


def test_double_empty_fails_with_bounded_attempts(monkeypatch, tmp_path):
    async def run():
        k = load(monkeypatch, tmp_path)
        class Backend:
            def __init__(self):
                self.calls = 0
            async def chat_stream(self, **kwargs):
                self.calls += 1
                yield response()
        b = Backend()
        kernel = k.JackQwenKernel(b, k.CFG)
        with pytest.raises(k.HTTPException, match="after one same-stage streaming retry"):
            async for _ in kernel._run_stage_streamed(
                    [{"role": "user", "content": "Hello"}], "",
                    "extended_initial", {}, append=False):
                pass
        assert b.calls == 2
    asyncio.run(run())
