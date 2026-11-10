"""Universal tool-failure handoff: no tool authority after hard ceiling."""
import asyncio
import importlib.util
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(monkeypatch, tmp_path, mode):
    monkeypatch.setenv("JACK_REASONING_LEVEL", mode)
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "balanced")
    monkeypatch.setenv("JACK_AGENTIC_FINAL_REVIEW", "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE1_VERIFY_BEFORE_ALIGNMENT", "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_FINAL_REVIEW", "0")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_LOOP_DETECTOR", "0")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "tool_handoff_25_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_thresholds_success_reset_and_duplicate_outcomes():
    from jack_tool_recovery import ToolRecoveryState, SOFT_ATTEMPTS, STRONG_ATTEMPTS, HARD_ATTEMPTS
    assert (SOFT_ATTEMPTS, STRONG_ATTEMPTS, HARD_ATTEMPTS) == (5, 15, 25)
    state = ToolRecoveryState()
    for n in range(1, 25):
        assert state.fail("edit:file.py", "missing path") == n
        assert not state.exhausted
        assert bool(state.advice()) == (n in (5, 15))
    state.progress("read:file.py", call_id="success")
    assert state.consecutive_failures == 0 and not state.events
    for n in range(25):
        state.fail("bash:command:python", "exit 1", call_id=f"failed-{n}")
    assert state.exhausted
    assert "TASK INCOMPLETE" in state.host_report()
    assert "Do not issue ANY tool calls" in state.handoff_instruction()


@pytest.mark.parametrize("mode", ["agentic", "off"])
def test_streamed_malformed_calls_then_terminal_tools_off_handoff(monkeypatch, tmp_path, mode):
    async def run():
        k = load(monkeypatch, tmp_path, mode)
        class Backend:
            def __init__(self):
                self.calls = []
            async def chat_stream(self, **kwargs):
                self.calls.append(kwargs)
                if kwargs.get("tools") is None:
                    yield {"choices": [{"index": 0, "delta": {
                        "content": "Finished work: file setup. Failed: invalid edit. Continue with an alternate tool."
                    }, "finish_reason": "stop"}],
                           "usage": {"prompt_tokens": 100, "completion_tokens": 17, "total_tokens": 117}}
                    return
                n = len(self.calls)
                yield {"choices": [{"index": 0, "delta": {"tool_calls": [{
                    "index": 0, "id": f"bad-{n}", "type": "function",
                    "function": {"name": "edit", "arguments": '{"edits":[]}'},
                }]}, "finish_reason": "tool_calls"}],
                       "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}}
        backend = Backend()
        kernel = k.JackQwenKernel(backend, k.CFG)
        tools = [{"type": "function", "function": {"name": "edit", "parameters": {
            "type": "object", "required": ["path", "edits"],
            "properties": {"path": {"type": "string"}, "edits": {"type": "array"}},
        }}}]
        request = {"messages": [{"role": "user", "content": "Edit the financial model"}],
                   "tools": tools, "tool_choice": "auto"}
        wire = b"".join([part async for part in kernel.stream(request)]).decode("utf-8")
        assert len(backend.calls) == 26
        assert all(call["tools"] == tools for call in backend.calls[:25])
        assert backend.calls[-1]["tools"] is None
        assert "TASK INCOMPLETE" in wire
        assert "25 consecutive unsuccessful attempts" in wire
        assert "Finished work: file setup" in wire
        assert "data: [DONE]" in wire
        assert '"tool_calls":' not in wire
    asyncio.run(run())


def test_explicit_tool_failures_and_duplicate_replays(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, "agentic")
    tracker = k.ToolRecoveryState()
    calls = [{"id": "test-call", "function": {
        "name": "bash", "arguments": '{"command":"python verify.py"}'}}]
    pending = SimpleNamespace(tool_recovery=tracker, history=[{"role": "assistant", "tool_calls": calls}])
    error = [{"role": "tool", "tool_call_id": "test-call",
              "_jack_tool_outcome": k.TOOL_FAILED, "content": "exit 1"}]
    k._tool_recovery_record_results(pending, error)
    k._tool_recovery_record_results(pending, error)
    assert tracker.consecutive_failures == 1, "Retried transport cannot double count"
    k._tool_recovery_record_results(pending, [{
        "role": "tool", "tool_call_id": "done",
        "_jack_tool_outcome": k.TOOL_SUCCESS, "content": "ok",
    }])
    assert tracker.consecutive_failures == 0
