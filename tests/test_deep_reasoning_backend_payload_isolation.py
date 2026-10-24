"""Regression: real backend payload must enforce TAS role-native context isolation.

Uses a fake HTTP client. No network requests, model inference or tool execution.
"""
from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import sys
import uuid
from pathlib import Path

from jack_deep_reasoning_context import (
    CompletedSynthesis,
    antithesis_messages,
    append_stage_local_tool_results,
    next_thesis_messages,
    synthesis_messages,
)

ROOT = Path(__file__).resolve().parents[1]
STAGES = (
    "deep_reasoning_thesis",
    "deep_reasoning_antithesis",
    "deep_reasoning_synthesis",
)


class _Response:
    status_code = 200
    text = ""

    def json(self):
        return {"choices": [{"message": {"role": "assistant", "content": "ok"},
                             "finish_reason": "stop"}], "usage": {}}


class _CaptureClient:
    def __init__(self):
        self.payloads = []

    async def post(self, *args, **kwargs):
        self.payloads.append(copy.deepcopy(kwargs["json"]))
        return _Response()



def _load_kernel(monkeypatch):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "deep-reasoning")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    name = f"jack_tas_payload_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    import jack_responses_compat
    jack_responses_compat.register(module)
    return module


def _backend(jk):
    b = jk.OpenAICompatibleBackend(jk.CFG)
    capture = _CaptureClient()
    b._client = capture
    b._resolved_model = "test-model"
    b._model_metadata_checked = True
    return b, capture


def _model_payload(backend, capture, jk, stage, messages):
    asyncio.run(backend.chat(
        messages=messages,
        secondary_system="CALLER_SYSTEM_KEPT_EXACT",
        profile=jk.STAGES[stage],
        tools=[{"type": "function", "function": {"name": "python_repl", "parameters": {"type": "object"}}}],
        tool_choice="auto",
    ))
    assert len(capture.payloads) >= 1
    return capture.payloads[-1]


def test_complete_serialized_backend_payloads_keep_roles_independent(monkeypatch):
    jk = _load_kernel(monkeypatch)
    backend, capture = _backend(jk)
    history = [
        {"role": "user", "content": "EARLIER_REQUIREMENT_KEEP"},
        {"role": "assistant", "content": "EARLIER_VISIBLE_ANSWER",
         "reasoning_content": "OLDER_R1_MUST_NOT_REPLAY",
         "reasoning": "OLDER_R2_MUST_NOT_REPLAY",
         "thinking": "OLDER_R3_MUST_NOT_REPLAY"},
    ]
    stage_views = {
        "deep_reasoning_thesis": next_thesis_messages(
            request="CURRENT_USER_REQUEST", visible_history=history,
            prior_synthesis=CompletedSynthesis("PRIOR_USER", "PRIOR_A3", "BRIDGED_R3_ONE_HOP"),
            preserve_thinking=True,
        ),
        "deep_reasoning_antithesis": antithesis_messages(
            request="CURRENT_USER_REQUEST", thesis_answer="UNTRUSTED_A1_VISIBLE",
            visible_history=history,
        ),
        "deep_reasoning_synthesis": synthesis_messages(
            request="CURRENT_USER_REQUEST", thesis_answer="UNTRUSTED_A1_VISIBLE",
            antithesis_findings="UNTRUSTED_A2_VISIBLE", visible_history=history,
            host_evidence_receipts=[{"origin": "host", "raw_result": "INDEPENDENT_TEST_EVIDENCE"}],
        ),
    }
    for stage in STAGES:
        payload = _model_payload(backend, capture, jk, stage, stage_views[stage])
        serialized = json.dumps(payload, ensure_ascii=False)
        system = payload["messages"][0]["content"]
        assert system.startswith("CALLER_SYSTEM_KEPT_EXACT")
        assert system.endswith(jk.STAGES[stage].prompt)
        for other in STAGES:
            if other != stage:
                assert jk.STAGES[other].prompt not in system
        assert "EARLIER_REQUIREMENT_KEEP" in serialized
        assert "CURRENT_USER_REQUEST" in serialized
        assert "OLDER_R1_MUST_NOT_REPLAY" not in serialized
        assert "OLDER_R2_MUST_NOT_REPLAY" not in serialized
        assert "OLDER_R3_MUST_NOT_REPLAY" not in serialized
        assert ("BRIDGED_R3_ONE_HOP" in serialized) == (stage == "deep_reasoning_thesis")
        assert ("UNTRUSTED_A1_VISIBLE" in serialized) == (stage != "deep_reasoning_thesis")
        assert ("UNTRUSTED_A2_VISIBLE" in serialized) == (stage == "deep_reasoning_synthesis")
        assert ("INDEPENDENT_TEST_EVIDENCE" in serialized) == (stage == "deep_reasoning_synthesis")
        assert not any(k.startswith("_jack_") for m in payload["messages"] for k in m)


def test_own_native_tool_reasoning_remains_only_within_its_stage(monkeypatch):
    jk = _load_kernel(monkeypatch)
    backend, capture = _backend(jk)
    for stage in STAGES:
        calls = [{"type": "function", "id": "call-1", "function": {
            "name": "python_repl", "arguments": "{}"}}]
        own_reasoning = f"STAGE_LOCAL_NATIVE_ONLY_{stage.upper()}"
        active = append_stage_local_tool_results(
            [{"role": "user", "content": "CURRENT_TASK"}],
            tool_calls=calls,
            results=[{"tool_call_id": "call-1", "content": "HOST_TOOL_RESULT"}],
            native_reasoning=own_reasoning,
            preserve_same_stage_native=True,
        )
        payload = _model_payload(backend, capture, jk, stage, active)
        wire = json.dumps(payload, ensure_ascii=False)
        assert own_reasoning in wire
        for other in STAGES:
            if other != stage:
                assert f"STAGE_LOCAL_NATIVE_ONLY_{other.upper()}" not in wire
        assert "HOST_TOOL_RESULT" in wire
        assert payload["messages"][0]["content"].endswith(jk.STAGES[stage].prompt)


def test_actual_backend_dispatch_emits_only_opt_in_counts(monkeypatch, caplog):
    monkeypatch.setenv("JACK_TAS_CONTEXT_ACCOUNTING", "1")
    jk = _load_kernel(monkeypatch)
    backend, capture = _backend(jk)
    with caplog.at_level("INFO"):
        payload = _model_payload(
            backend, capture, jk, "deep_reasoning_thesis",
            [{"role": "user", "content": "PRIVATE_TAS_TASK_SENTINEL"}],
        )
    records = [r.getMessage() for r in caplog.records
               if r.getMessage().startswith("TAS context accounting:")]
    assert len(records) == 1
    from jack_tas_context_accounting import measure_tas_request
    expected = measure_tas_request(payload["messages"], payload,
                                   "Deep Reasoning Thesis pass 1")
    observed = json.loads(records[0].removeprefix("TAS context accounting: "))
    assert observed == expected
    assert "PRIVATE_TAS_TASK_SENTINEL" not in records[0]
