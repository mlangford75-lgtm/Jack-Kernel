"""Stage-2 pre-commit native reflection: feature gate and transport contract.

No fake claim of hardware/backend sampler interception: the capable backend
below simulates the contract, and unsupported backends retain the original
single-request, streaming semantics.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from jack_stage2_native_reflection import (
    INSTRUCTION, PROTOCOL, NativeReflectionContractError,
    select_stream, verify_native_reflection_stream,
)


class StreamingBackend:
    def __init__(self, chunks=None):
        self.calls = 0
        self.extension_calls = 0
        self.closed = 0
        self.kwargs = None
        self.chunks = chunks or [
            {"choices": [{"delta": {"reasoning_content": "Review complete."}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": "Memory."}, "finish_reason": "stop"}]},
        ]

    async def chat_stream(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        try:
            for chunk in self.chunks:
                yield chunk
        finally:
            self.closed += 1


class SimulatedCapableBackend(StreamingBackend):
    def native_reflection_capability(self):
        return PROTOCOL

    async def chat_stream_with_native_reflection(self, **kwargs):
        self.extension_calls += 1
        self.kwargs = kwargs
        try:
            yield {"choices": [{"delta": {"reasoning_content": "First thought."}, "finish_reason": None}]}
            yield {"_jack_native_reflection_receipt": {
                "protocol": PROTOCOL, "event": "injected", "text": INSTRUCTION,
            }}
            yield {"choices": [{"delta": {"reasoning_content": "I should retain the failed edit."}, "finish_reason": None}]}
            yield {"choices": [{"delta": {"content": "Memory includes failed edit."}, "finish_reason": "stop"}]}
        finally:
            self.closed += 1


class BadCapableBackend(SimulatedCapableBackend):
    async def chat_stream_with_native_reflection(self, **kwargs):
        self.extension_calls += 1
        yield {"choices": [{"delta": {"reasoning_content": "Reasoning."}, "finish_reason": None}]}
        yield {"choices": [{"delta": {"content": "Memory."}, "finish_reason": "stop"}]}


async def collect(backend, *, enabled=True, stage="extended_reflection", agentic=True):
    kwargs = {
        "messages": [{"role": "user", "content": "Request"}],
        "secondary_system": "",
        "profile": "untouched profile",
        "tools": None,
        "tool_choice": None,
    }
    stream, selected = select_stream(
        backend, enabled=enabled, stage_key=stage,
        agentic_mode=agentic, stream_kwargs=kwargs,
    )
    packets = [packet async for packet in stream]
    return selected, packets, kwargs


@pytest.mark.parametrize("enabled,stage,agentic", [
    (False, "extended_reflection", True),
    (True, "extended_initial", True),
    (True, "extended_reflection", False),
])
def test_disabled_and_unrelated_stages_keep_original_stream(enabled, stage, agentic):
    backend = SimulatedCapableBackend()
    selected, chunks, request = asyncio.run(
        collect(backend, enabled=enabled, stage=stage, agentic=agentic)
    )
    assert selected is False
    assert backend.calls == 1
    assert backend.extension_calls == 0
    assert backend.closed == 1
    assert backend.kwargs == request
    assert chunks == backend.chunks


def test_unsupported_backend_runs_normal_stage2_without_extra_request():
    backend = StreamingBackend()
    selected, chunks, request = asyncio.run(collect(backend))
    assert selected is False
    assert backend.calls == 1
    assert backend.extension_calls == 0
    assert backend.closed == 1
    assert backend.kwargs == request
    assert chunks == backend.chunks


def test_supported_simulated_precommit_adapter_extends_once():
    backend = SimulatedCapableBackend()
    selected, chunks, request = asyncio.run(collect(backend))
    assert selected is True
    assert backend.calls == 0
    assert backend.extension_calls == 1
    assert backend.closed == 1
    assert backend.kwargs == {
        **request, "reflection_instruction": INSTRUCTION, "max_reflections": 1,
    }
    assert [next(iter(x["choices"][0]["delta"])) for x in chunks] == [
        "reasoning_content", "reasoning_content", "content",
    ]
    assert INSTRUCTION not in str(chunks)


def test_claimed_support_without_intervention_fails_closed():
    backend = BadCapableBackend()
    with pytest.raises(NativeReflectionContractError, match="without verified native reflection"):
        asyncio.run(collect(backend))


@pytest.mark.parametrize("streamed", [
    [
        {"_jack_native_reflection_receipt": {"protocol": PROTOCOL, "event": "injected", "text": INSTRUCTION}},
        {"choices": [{"delta": {"content": "Memory"}, "finish_reason": "stop"}]},
    ],
    [
        {"choices": [{"delta": {"reasoning_content": "A"}}]},
        {"_jack_native_reflection_receipt": {"protocol": PROTOCOL, "event": "injected", "text": INSTRUCTION}},
        {"_jack_native_reflection_receipt": {"protocol": PROTOCOL, "event": "injected", "text": INSTRUCTION}},
    ],
    [
        {"choices": [{"delta": {"reasoning_content": "A"}}]},
        {"_jack_native_reflection_receipt": {"protocol": PROTOCOL, "event": "injected", "text": INSTRUCTION}},
        {"choices": [{"delta": {"content": "Memory"}, "finish_reason": "stop"}]},
    ],
])
def test_invalid_receipts_raise(streamed):
    async def go():
        async def generator():
            for chunk in streamed:
                yield chunk
        return [x async for x in verify_native_reflection_stream(generator())]
    with pytest.raises(NativeReflectionContractError):
        asyncio.run(go())


def test_real_kernel_default_switch_disabled_and_prompts_unchanged(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.delenv("JACK_AGENTIC_STAGE2_NATIVE_REFLECTION", raising=False)
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / ("forensic-" + uuid.uuid4().hex + ".sqlite")))
    name = "jack_native_reflection_test_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    assert k.AGENTIC_36_STAGE2_PROMPT == "Generate a detailed summary of why you came to this conclusion."
    assert k.AGENTIC_STAGE1_PROMPT == (
        "Reasoning effort is set to xhigh. Please think carefully through the task, "
        "validate key assumptions, consider plausible alternatives, and prioritize "
        "correctness, consistency, and clarity in the final answer."
    )
    assert k.STAGES["extended_reflection"].allow_tools is False
    assert not hasattr(k.OpenAICompatibleBackend, "native_reflection_capability")
