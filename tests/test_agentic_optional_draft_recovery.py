"""Optional Agentic continuations preserve the last completed draft on empty SSE."""
import asyncio
import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(monkeypatch, tmp_path, *, stage2=False):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "exhaustive" if stage2 else "thorough")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_LOOP_DETECTOR", "0")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "agentic_optional_recovery_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


def response(text=None):
    return {"choices": [{"index": 0, "delta": ({"content": text} if text else {}),
             "finish_reason": "stop"}], "usage": {}}


@pytest.mark.parametrize("stage2", [False, True])
def test_optional_empty_followup_preserves_completed_draft(monkeypatch, tmp_path, stage2):
    async def run():
        k = load(monkeypatch, tmp_path, stage2=stage2)
        class Backend:
            def __init__(self):
                self.calls = 0
            async def chat_stream(self, **kwargs):
                self.calls += 1
                yield response("Original completed draft" if self.calls == 1 else None)
        b = Backend()
        kernel = k.JackQwenKernel(b, k.CFG)
        history = [{"role": "user", "content": "Check the clock"}]
        stage = "extended_reflection" if stage2 else "extended_initial"
        if stage2:
            history.append({"role": "assistant", "content": "Frozen answer",
                            "_jack_extended_candidate_response": True,
                            "_jack_stage_key": "extended_initial"})
        packets = [p async for p in kernel._run_stage_streamed(
            history, "", stage, {}, append=False)]
        results = [p["data"] for p in packets if p["kind"] == "result"]
        assert len(results) == 1
        assert results[0]["choices"][0]["message"]["content"] == "Original completed draft"
        assert b.calls == 3
        assert any("LAST COMPLETED DRAFT PRESERVED" in p.get("text", "")
                   for p in packets)
    asyncio.run(run())


def test_combined_review_preserves_initial_draft_on_empty_stream(monkeypatch, tmp_path):
    async def run():
        k = load(monkeypatch, tmp_path)
        class Backend:
            def __init__(self):
                self.calls = 0
            async def chat_stream(self, **kwargs):
                self.calls += 1
                yield response("Initial draft" if self.calls == 1 else None)
        b = Backend()
        kernel = k.JackQwenKernel(b, k.CFG)
        packets = [p async for p in kernel._run_stage_streamed(
            [{"role": "user", "content": "Build clock"}], "",
            "extended_initial", {}, append=False)]
        results = [p["data"] for p in packets if p["kind"] == "result"]
        assert len(results) == 1
        assert results[0]["choices"][0]["message"]["content"] == "Initial draft"
        assert b.calls == 3
    asyncio.run(run())
