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
            assert b.calls[1]["tools"] == tools
            assert b.calls[1]["tool_choice"] == "auto"
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


def _call(name, arguments, call_id):
    import json
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)}}


def test_recovery_duplicate_mutation_guard_is_surgical(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    prior = _call("write", {"path": "created.txt", "content": "done"}, "completed-id")
    duplicate = _call("write", {"content": "done", "path": "created.txt"}, "new-id")
    different = _call("write", {"path": "different.txt", "content": "new"}, "fresh-id")
    listing = _call("bash", {"command": "ls -R ."}, "read-id")
    history = [
        {"role": "user", "content": "Create files"},
        {"role": "assistant", "content": "", "tool_calls": [prior],
         "_jack_internal_tool_exchange": True, "_jack_stage_key": "extended_initial"},
        {"role": "tool", "tool_call_id": "completed-id", "content": "written",
         "_jack_internal_tool_exchange": True},
    ]
    assert k._recovery_repeats_completed_mutation(history, [duplicate])
    assert k._recovery_repeats_completed_mutation(history, [listing, duplicate])
    assert not k._recovery_repeats_completed_mutation(history, [different])
    assert not k._recovery_repeats_completed_mutation(history, [listing])
    # No earlier user turn may cause a duplicate suppression in this one.
    history.extend([{"role": "user", "content": "New independent request"}])
    assert not k._recovery_repeats_completed_mutation(history, [duplicate])


def test_runtime_activity_reports_only_backend_prompt_usage(monkeypatch, tmp_path):
    async def run():
        k = load(monkeypatch, tmp_path)
        tracker = k.RuntimeActivityTracker()
        async with tracker.request_scope("stream"):
            await tracker.update(stage_key="extended_initial", stage_name="Agentic Stage 1",
                                 backend_request_active=True)
            initial = await tracker.snapshot()
            assert initial["requests"][0]["backend_prompt_tokens"] is None
            await tracker.update(
                backend_stream_phase="tool_arguments",
                backend_stream_bytes={"reasoning": 24, "content": 7, "tool_arguments": 130},
                backend_prompt_tokens=12345,
                backend_last_recognized_at_unix=__import__("time").time(),
            )
            observed = (await tracker.snapshot())["requests"][0]
            assert observed["backend_prompt_tokens"] == 12345
            assert observed["backend_stream_phase"] == "tool_arguments"
            assert observed["backend_stream_bytes"]["tool_arguments"] == 130
            await tracker.update(backend_request_active=False)
            await tracker.update(backend_request_active=True)
            again = (await tracker.snapshot())["requests"][0]
            assert again["backend_prompt_tokens"] is None
            assert again["last_backend_prompt_tokens"] == 12345
    asyncio.run(run())
