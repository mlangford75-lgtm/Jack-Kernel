"""Telemetry must be optional, non-mutating, and content-blind."""
import copy
import json

from jack_tas_context_accounting import measure_tas_request, emit_tas_context_report


class Logger:
    def __init__(self):
        self.lines = []

    def info(self, fmt, *args):
        self.lines.append(fmt % args)

    def warning(self, fmt, *args):
        self.lines.append(fmt % args)


def test_tas_telemetry_inert_unless_opted_in(monkeypatch):
    monkeypatch.delenv("JACK_TAS_CONTEXT_ACCOUNTING", raising=False)
    logger = Logger()
    emit_tas_context_report([{"role": "user", "content": "PRIVATE"}],
                            {"model": "m"}, "Deep Reasoning Thesis pass 1", logger)
    assert logger.lines == []


def test_tas_telemetry_no_content_and_no_mutation(monkeypatch):
    monkeypatch.setenv("JACK_TAS_CONTEXT_ACCOUNTING", "1")
    messages = [
        {"role": "system", "content": "SECRET_SYSTEM_PROMPT"},
        {"role": "user", "content": "SECRET_USER_REQUEST"},
        {"role": "assistant", "content": "SECRET_ANSWER", "reasoning_content": "SECRET_NATIVE_REASONING"},
        {"role": "tool", "tool_call_id": "tool1", "content": "SECRET_TOOL_RESULT"},
    ]
    payload = {"model": "model-id", "messages": messages,
               "tools": [{"type": "function", "function": {"name": "python_repl"}}]}
    prior = copy.deepcopy(payload)
    logger = Logger()
    emit_tas_context_report(messages, payload, "Deep Reasoning Synthesis pass 3", logger)
    assert payload == prior
    assert len(logger.lines) == 1
    logged = logger.lines[0]
    for secret in ("SECRET_SYSTEM_PROMPT", "SECRET_USER_REQUEST", "SECRET_ANSWER",
                   "SECRET_NATIVE_REASONING", "SECRET_TOOL_RESULT", "python_repl", "model-id"):
        assert secret not in logged
    report = json.loads(logged.removeprefix("TAS context accounting: "))
    assert report == measure_tas_request(messages, payload, "Deep Reasoning Synthesis pass 3")
    assert report["stage"] == "synthesis"
    assert report["native_reasoning_messages"] == 1
    assert report["roles"]["tool"] == 1


def test_tas_telemetry_cannot_block_cognition(monkeypatch):
    monkeypatch.setenv("JACK_TAS_CONTEXT_ACCOUNTING", "1")

    class BrokenLogger:
        def info(self, *args):
            raise RuntimeError("broken telemetry sink")

        def warning(self, *args):
            raise RuntimeError("broken warning sink")

    emit_tas_context_report([{"role": "user", "content": "task"}],
                            {"messages": [{"role": "user", "content": "task"}]},
                            "Deep Reasoning Thesis pass 1", BrokenLogger())
