"""Independent generated-text budgets: streaming, cancellation, configuration and display."""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(monkeypatch, tmp_path, reasoning=100000, output=100000):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "off")
    monkeypatch.setenv("JACK_LOOP_DETECTOR", "0")
    monkeypatch.setenv("JACK_REASONING_BUDGET_TOKENS", str(reasoning))
    monkeypatch.setenv("JACK_OUTPUT_BUDGET_TOKENS", str(output))
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite3")))
    name = "jack_budgets_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class StreamingBackend:
    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = 0
        self.closed = 0

    async def chat_stream(self, **kwargs):
        self.calls += 1
        try:
            for delta in self.chunks:
                yield {"choices": [{"delta": delta, "finish_reason": None}]}
            yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}
        finally:
            self.closed += 1

    async def chat(self, **kwargs):
        raise AssertionError("No nonstream fallback or second generation permitted")


def generate(k, backend, *, reasoning=100000, output=100000):
    from dataclasses import replace
    cfg = replace(k.CFG, reasoning_budget_tokens=reasoning, output_budget_tokens=output)
    kernel = k.JackQwenKernel(backend, cfg)
    async def collect():
        return [packet async for packet in kernel._run_stage_streamed(
            [{"role": "user", "content": "Test"}], "", "thesis", {}, append=False
        )]
    return asyncio.run(collect())


def test_defaults_and_splash_and_environment(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    assert k.CFG.reasoning_budget_tokens == 100000
    assert k.CFG.output_budget_tokens == 100000
    assert k.CLI_DEFAULTS["reasoning_budget_tokens"] == 100000
    assert k.CLI_DEFAULTS["output_budget_tokens"] == 100000
    env = k._config_to_env(k.CLI_DEFAULTS)
    assert env["JACK_REASONING_BUDGET_TOKENS"] == "100000"
    assert env["JACK_OUTPUT_BUDGET_TOKENS"] == "100000"


@pytest.mark.parametrize("kind,delta,label", [
    ("reasoning", {"reasoning_content": "abcd" * 5}, "Jack Failure: Reasoning Budget"),
    ("reasoning", {"reasoning": "abcd" * 5}, "Jack Failure: Reasoning Budget"),
    ("output", {"content": "abcd" * 5}, "Jack Failure: Output Budget"),
    ("output", {"tool_calls": [{"index": 0, "function": {"name": "bash", "arguments": "abcd" * 5}}]}, "Jack Failure: Output Budget"),
])
def test_limit_is_terminal_closes_backend_no_retry(monkeypatch, tmp_path, kind, delta, label):
    k = load(monkeypatch, tmp_path, reasoning=5, output=5)
    backend = StreamingBackend([delta])
    with pytest.raises(k.GenerationBudgetExceeded, match=label):
        generate(k, backend, reasoning=5, output=5)
    assert backend.calls == 1
    assert backend.closed == 1


def test_stream_chunk_splitting_cannot_evade_budget(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, reasoning=5)
    backend = StreamingBackend([{"reasoning_content": "ab"}, {"reasoning_content": "cd"},
                                {"reasoning_content": "efghijklmnop"}, {"reasoning_content": "qrst"}])
    with pytest.raises(k.GenerationBudgetExceeded, match="Reasoning Budget"):
        generate(k, backend, reasoning=5)
    assert backend.closed == 1


def test_independent_budgets_do_not_include_prompt_or_each_other(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, reasoning=5, output=5)
    backend = StreamingBackend([{"reasoning_content": "abcd" * 4}, {"content": "abcd" * 4}])
    packets = generate(k, backend, reasoning=5, output=5)
    assert packets[-1]["kind"] == "result"
    assert backend.closed == 1


def test_zero_disables_individual_budget(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, reasoning=0, output=0)
    backend = StreamingBackend([{"reasoning_content": "abcd" * 100}, {"content": "efgh" * 100}])
    assert generate(k, backend, reasoning=0, output=0)[-1]["kind"] == "result"


def test_nonstream_budget_rejects_before_tool_authorization(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, reasoning=5, output=5)
    class NonstreamBackend:
        async def chat(self, **kwargs):
            return {"choices": [{"message": {"role": "assistant", "reasoning_content": "abcd" * 5,
                            "content": "", "tool_calls": [{"id": "forbidden",
                            "type": "function", "function": {"name": "bash", "arguments": "{}"}}]},
                            "finish_reason": "tool_calls"}], "usage": {}}
    kernel = k.JackQwenKernel(NonstreamBackend(), k.CFG)
    async def exercise():
        with pytest.raises(k.GenerationBudgetExceeded, match="Reasoning Budget"):
            await kernel._run_stage([{"role": "user", "content": "test"}], "", "thesis", {})
        assert not kernel._pending_tool_resumes
    asyncio.run(exercise())
