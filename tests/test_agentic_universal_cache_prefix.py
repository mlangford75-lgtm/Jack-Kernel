"""Universal Agentic identity and cache-observability regression tests.

These check deterministic transport behavior, not model response quality.
No LM Studio, Pi, llama.cpp, or real model is required.
"""
import asyncio
import copy
import importlib.util
import json
import logging
import sys
import uuid
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
USER_SECRET = "ORIGINAL_PRIVATE_REQUEST_FOR_STAGED_WORK"
FROZEN_ANSWER = "FROZEN_COMPLETED_RESPONSE_NOT_MEMORY_INPUT"
R1 = "Found that first write failed, then recovered and verified with a readback."
TOOL_RESULT = "write returned failure: invalid path"


def load(monkeypatch, tmp_path, profile="thorough"):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_TASK_ANCHOR", "1")
    monkeypatch.setenv("JACK_AGENTIC_TRANSACTION_LINKS", "1")
    monkeypatch.setenv(
        "JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite3"))
    )
    name = "jack_universal_cache_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    kernel = importlib.util.module_from_spec(spec)
    sys.modules[name] = kernel
    spec.loader.exec_module(kernel)
    return kernel


def frozen_history(kernel):
    history = [{"role": "user", "content": USER_SECRET}]
    work_id = kernel._agentic_begin_turn(history, fresh=True)
    history += [
        {
            "role": "assistant", "content": "",
            "reasoning_content": "Initial reasoning before issuing write.",
            "_jack_internal_tool_exchange": True,
            "tool_calls": [{
                "id": "tool-1", "type": "function",
                "function": {"name": "write", "arguments": '{"path":"test.txt"}'},
            }],
        },
        {
            "role": "tool", "name": "write", "tool_call_id": "tool-1",
            "content": TOOL_RESULT, "_jack_internal_tool_exchange": True,
            "_jack_internal_tool_failed": True,
        },
    ]
    kernel.append_extended_candidate_response(history, {
        "role": "assistant", "content": FROZEN_ANSWER,
        "reasoning_content": R1,
    })
    kernel._agentic_forensic_start_stage2(history)
    return history, work_id


@pytest.mark.parametrize("profile,thinking", [("balanced", False), ("thorough", True)])
@pytest.mark.parametrize("stream", [False, True])
def test_stage2_id_stays_host_only_and_chronological_source_is_complete(
    monkeypatch, tmp_path, profile, thinking, stream,
):
    kernel = load(monkeypatch, tmp_path, profile)
    history, work_id = frozen_history(kernel)
    saved = copy.deepcopy(history)
    stage2 = kernel.STAGES["extended_reflection"]
    source = kernel._agentic_stage2_test_history(history, stage2)
    assert source[0]["role"] == "user"
    assert len(source) == 2
    assert not any(x["role"] == "system" for x in source)
    calls = []

    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if stream:
            return httpx.Response(
                200,
                text='data: {"choices":[{"index":0,"delta":{"content":"Memory"},"finish_reason":null}]}\n\n'
                     'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":321}}\n\n'
                     'data: [DONE]\n\n',
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "Memory"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 321},
        })

    async def exercise():
        backend = kernel.OpenAICompatibleBackend(kernel.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async def model():
            return "any-openai-compatible-model"
        backend.resolve_model = model
        try:
            options = dict(
                messages=history, secondary_system="caller custom prompt",
                profile=stage2, tools=None, tool_choice="auto",
            )
            if stream:
                return [item async for item in backend.chat_stream(**options)]
            return await backend.chat(**options)
        finally:
            await backend._client.aclose()

    asyncio.run(exercise())
    assert history == saved
    assert len(calls) == 1
    outgoing = calls[0]
    assert outgoing["chat_template_kwargs"]["enable_thinking"] is thinking
    assert "tools" not in outgoing and "tool_choice" not in outgoing
    wire = json.dumps(outgoing, ensure_ascii=False)
    assert USER_SECRET not in wire
    assert FROZEN_ANSWER not in wire
    assert work_id not in wire
    assert "Memory attempt ID" not in wire
    assert "Authenticated current work ID" not in wire
    assert "caller custom prompt" not in wire
    assert wire.count(R1) == 1
    assert wire.count(TOOL_RESULT) == 1
    assert wire.index(TOOL_RESULT) < wire.index(R1)
    assert sum(m["role"] == "system" for m in outgoing["messages"]) == 1
    assert sum(m["role"] == "user" for m in outgoing["messages"]) == 1
    assert all(m["role"] != "assistant" for m in outgoing["messages"])
    assert kernel._AGENTIC_STAGE2_THOROUGH_EXHAUSTIVE_DIRECTIVE in outgoing["messages"][0]["content"]


@pytest.mark.parametrize("stream", [False, True])
def test_cache_diagnostics_do_not_change_dispatch_and_report_missing_metrics(
    monkeypatch, tmp_path, caplog, stream,
):
    kernel = load(monkeypatch, tmp_path)
    calls = []
    def respond(request):
        calls.append(json.loads(request.content))
        if stream:
            return httpx.Response(
                200, text='data: {"choices":[{"index":0,"delta":{"content":"ok"},"finish_reason":null}]}\n\n'
                          'data: [DONE]\n\n',
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "ok"},
                         "finish_reason": "stop"}],
        })

    async def exercise():
        backend = kernel.OpenAICompatibleBackend(kernel.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async def model(): return "mock-model"
        backend.resolve_model = model
        try:
            options = dict(
                messages=[{"role": "user", "content": USER_SECRET}],
                secondary_system="", profile=kernel.STAGES["extended_initial"],
                tools=None, tool_choice="auto",
            )
            if stream:
                return [chunk async for chunk in backend.chat_stream(**options)]
            return await backend.chat(**options)
        finally:
            await backend._client.aclose()

    with caplog.at_level(logging.INFO):
        asyncio.run(exercise())
    assert len(calls) == 1
    wire = calls[0]
    assert wire["messages"][-1]["content"] == USER_SECRET
    assert not any(
        x in wire for x in ("cache_slot", "cache_key", "cache_prompt", "cache_affinity")
    )
    logs = "\n".join(record.message for record in caplog.records)
    assert "jack.agentic.transport_prefix.v1" in logs
    assert "cached_prompt_tokens: unavailable" in logs
    assert USER_SECRET not in logs


def test_prefix_diagnostics_identify_append_stage_switch_and_early_change_without_content(
    monkeypatch, tmp_path, caplog,
):
    kernel = load(monkeypatch, tmp_path)
    backend = kernel.OpenAICompatibleBackend(kernel.CFG)
    s1, s2 = kernel.STAGES["extended_initial"], kernel.STAGES["extended_reflection"]
    payload = {"model": "neutral-model", "messages": [], "chat_template_kwargs": {"enable_thinking": True}}
    messages = [
        {"role": "system", "content": "Stable instructions"},
        {"role": "user", "content": USER_SECRET},
    ]
    with caplog.at_level(logging.INFO):
        backend._agentic_cache_prefix_probe(messages, payload, s1)
        backend._agentic_cache_prefix_probe(
            messages + [{"role": "assistant", "content": "tool result"}], payload, s1
        )
        backend._agentic_cache_prefix_probe(
            [{"role": "system", "content": "Memory extraction"}, messages[1]], payload, s2
        )
        backend._agentic_cache_prefix_probe(
            [{"role": "system", "content": "Changed beginning"}, messages[1]], payload, s1
        )
    reports = [
        json.loads(record.message.split("Agentic transport-prefix diagnostic: ", 1)[1])
        for record in caplog.records
        if "Agentic transport-prefix diagnostic: " in record.message
    ]
    assert len(reports) == 4
    assert reports[1]["same_stage"]["relation"] == "append_only"
    assert reports[1]["same_stage"]["matched_messages"] == 2
    assert reports[2]["immediately_preceding"]["relation"] == "first_message_changed"
    assert reports[3]["same_stage"]["relation"] == "first_message_changed"
    assert reports[3]["same_stage"]["first_changed_message_index"] == 0
    assert USER_SECRET not in "\n".join(record.message for record in caplog.records)
    assert len(backend._agentic_previous_prompt_by_stage) == 2
    asyncio.run(backend.close())


def test_prefix_probe_failure_is_nonblocking(monkeypatch, tmp_path):
    kernel = load(monkeypatch, tmp_path)
    backend = kernel.OpenAICompatibleBackend(kernel.CFG)
    original = [{"role": "user", "content": USER_SECRET}]
    snapshot = copy.deepcopy(original)
    class Unserializable:
        def __str__(self):
            raise RuntimeError("telemetry broken")
    payload = {"model": "neutral-model", "tools": Unserializable()}
    # Neither inference payload nor user content may be mutated or rejected.
    backend._agentic_cache_prefix_probe(
        original, payload, kernel.STAGES["extended_initial"]
    )
    assert original == snapshot
    assert isinstance(payload["tools"], Unserializable)
    asyncio.run(backend.close())
