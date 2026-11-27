"""Pi/Jack Agentic usage boundary: stage-summed compute vs single-request context.

These tests use synthetic backend replies. They do NOT claim a real backend
context budget was measured. Live Pi/LM Studio must validate after unit PASS.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]

FIRST = {"prompt_tokens": 32000, "completion_tokens": 5000, "total_tokens": 37000}
SECOND = {"prompt_tokens": 34201, "completion_tokens": 1715, "total_tokens": 35916}
AGGREGATE = {"prompt_tokens": 66201, "completion_tokens": 6715, "total_tokens": 72916}


def load(mode="agentic"):
    os.environ["JACK_REASONING_LEVEL"] = mode
    os.environ["JACK_BACKEND_PROFILE"] = "lmstudio"
    os.environ["JACK_BACKEND_MODEL"] = "test-model"
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "off"
    name = "jack_pi_usage_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def executor(k, adapter="pi"):
    return k.Phase4ExecutorRequestContext(
        protocol_version=1,
        runtime_id=k.RUNTIME_ID,
        lane_id=k.LANE_ID,
        cwd=str(ROOT),
        platform="win32",
        adapter=adapter,
    )


def test_peak_is_not_the_sum_of_two_stages():
    k = load()
    assert k._agentic_peak_stage_usage(FIRST, SECOND) == FIRST
    assert k._agentic_peak_stage_usage(SECOND, FIRST) == FIRST
    assert FIRST["total_tokens"] < 48128
    assert AGGREGATE["total_tokens"] > 48128


@pytest.mark.parametrize("bad", [
    None, {}, {"prompt_tokens": "invalid"},
    {"prompt_tokens": -1, "completion_tokens": 1, "total_tokens": 1},
    {"prompt_tokens": 15, "completion_tokens": 10, "total_tokens": 12},
])
def test_partial_and_invalid_stage_telemetry_fails_conservatively(bad):
    k = load()
    assert k._agentic_peak_stage_usage(FIRST, bad) is None
    assert k._agentic_peak_stage_usage(FIRST) is None
    t = k._PHASE4_EXECUTOR_REQUEST_CONTEXT.set(executor(k))
    try:
        assert k._agentic_usage_for_pi(AGGREGATE, None) == AGGREGATE
    finally:
        k._PHASE4_EXECUTOR_REQUEST_CONTEXT.reset(t)


def test_spoofed_or_unbound_adapter_does_not_change_aggregate():
    k = load()
    peak = k._agentic_peak_stage_usage(FIRST, SECOND)
    assert k._agentic_usage_for_pi(AGGREGATE, peak) == AGGREGATE
    token = k._PHASE4_EXECUTOR_REQUEST_CONTEXT.set(executor(k, adapter="other"))
    try:
        assert k._agentic_usage_for_pi(AGGREGATE, peak) == AGGREGATE
    finally:
        k._PHASE4_EXECUTOR_REQUEST_CONTEXT.reset(token)


def test_pi_adapter_projects_conservative_single_stage_peak():
    k = load()
    peak = k._agentic_peak_stage_usage(FIRST, SECOND)
    token = k._PHASE4_EXECUTOR_REQUEST_CONTEXT.set(executor(k))
    try:
        projected = k._agentic_usage_for_pi(AGGREGATE, peak)
        assert projected == FIRST
        assert AGGREGATE == {"prompt_tokens": 66201, "completion_tokens": 6715, "total_tokens": 72916}
        assert FIRST == {"prompt_tokens": 32000, "completion_tokens": 5000, "total_tokens": 37000}
    finally:
        k._PHASE4_EXECUTOR_REQUEST_CONTEXT.reset(token)


def test_projection_never_upgrades_non_agentic_mode():
    k = load(mode="off")
    token = k._PHASE4_EXECUTOR_REQUEST_CONTEXT.set(executor(k))
    try:
        assert k._agentic_usage_for_pi(AGGREGATE, FIRST) == AGGREGATE
    finally:
        k._PHASE4_EXECUTOR_REQUEST_CONTEXT.reset(token)


async def run_nonstream(k, context):
    async def fake_stage(history, secondary_system, stage_key, usage, **kwargs):
        record = FIRST if stage_key == "extended_initial" else SECOND
        content = "Exact A1" if stage_key == "extended_initial" else "Why A1 was produced"
        k.aggregate_usage(usage, record)
        return {
            "choices": [{"message": {"role": "assistant", "content": content},
                         "finish_reason": "stop"}],
            "usage": dict(record),
        }

    k.KERNEL._run_stage = fake_stage
    return await k.KERNEL.run(
        {"messages": [{"role": "user", "content": "Original user task"}]},
        executor_context=context,
    )


@pytest.mark.parametrize("adapter,expected", [("pi", FIRST), ("other", AGGREGATE), (None, AGGREGATE)])
def test_real_nonstream_agentic_commit_preserves_output_and_projects_only_for_pi(adapter, expected):
    k = load()
    context = executor(k, adapter=adapter) if adapter is not None else None
    result = asyncio.run(run_nonstream(k, context))
    assert result.content == "Why A1 was produced\n\nExact A1"
    assert result.usage == expected
    assert result.finish_reason == "stop"
    assert next(iter(k._AGENTIC_SHADOW_LEDGER.values())).response.content == "Exact A1"


async def run_stream(k, context):
    async def fake_stream(history, secondary_system, stage_key, usage, **kwargs):
        record = FIRST if stage_key == "extended_initial" else SECOND
        content = "Exact A1" if stage_key == "extended_initial" else "Why A1 was produced"
        k.aggregate_usage(usage, record)
        yield {"kind": "content", "text": content}
        yield {"kind": "result", "data": {
            "choices": [{"message": {"role": "assistant", "content": content},
                         "finish_reason": "stop"}],
            "usage": dict(record),
        }}

    k.KERNEL._run_stage_streamed = fake_stream
    chunks = []
    async for wire in k.KERNEL.stream(
        {"messages": [{"role": "user", "content": "Original user task"}], "stream": True},
        executor_context=context,
    ):
        chunks.append(wire)
    events = []
    for line in b"".join(chunks).decode("utf-8").splitlines():
        if line.startswith("data: ") and line != "data: [DONE]":
            events.append(json.loads(line[6:]))
    usage_events = [item["usage"] for item in events if "usage" in item]
    finals = [choice for event in events for choice in event.get("choices", [])
              if choice.get("finish_reason") == "stop"]
    return usage_events, finals, events


@pytest.mark.parametrize("adapter,expected", [("pi", FIRST), ("other", AGGREGATE), (None, AGGREGATE)])
def test_real_streaming_agentic_transaction_usage_event(adapter, expected):
    k = load()
    context = executor(k, adapter=adapter) if adapter is not None else None
    usages, finals, events = asyncio.run(run_stream(k, context))
    assert usages == [expected]
    assert len(finals) == 1
    text = "".join(choice["delta"].get("content", "")
                   for event in events for choice in event.get("choices", []))
    assert text == "Why A1 was produced\n\nExact A1"


def test_candidate_exceeding_aggregate_fails_closed():
    k = load()
    impossible = {"prompt_tokens": 85000, "completion_tokens": 200, "total_tokens": 85200}
    token = k._PHASE4_EXECUTOR_REQUEST_CONTEXT.set(executor(k))
    try:
        assert k._agentic_usage_for_pi(AGGREGATE, impossible) == AGGREGATE
    finally:
        k._PHASE4_EXECUTOR_REQUEST_CONTEXT.reset(token)
