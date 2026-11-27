"""V-1 policy evidence and V-2 real transaction accounting regression."""
import asyncio
import json
from pathlib import Path

import pytest

from test_agentic_coder_planner_executor import load
from test_audit_cache_cost_evidence import mock_backend, dispatch


@pytest.mark.parametrize("streamed", [False, True])
def test_v1_stage2_budget_terminal_policy_evidence(monkeypatch, tmp_path, streamed):
    monkeypatch.setenv("JACK_OUTPUT_BUDGET_TOKENS", "64")
    k = load(monkeypatch, tmp_path, profile="balanced")
    answer = "Exact frozen A1."
    calls = []

    class Backend:
        async def chat(self, *, profile, **kwargs):
            calls.append(profile.name)
            text = answer if len(calls) == 1 else "memory " * 100
            return {"choices": [{"message": {"role": "assistant", "content": text},
                                 "finish_reason": "stop"}], "usage": {}}

        async def chat_stream(self, *, profile, **kwargs):
            calls.append(profile.name)
            text = answer if len(calls) == 1 else "memory " * 100
            yield {"choices": [{"delta": {"content": text}, "finish_reason": None}]}
            yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}

    async def run():
        k.KERNEL.backend = Backend()
        body = {"messages": [{"role": "user", "content": "Complete the requested task."}]}
        if streamed:
            body["stream"] = True
            parts = []
            for frame in [item async for item in k.KERNEL.stream(body)]:
                for line in frame.decode("utf-8").splitlines():
                    if not line.startswith("data: ") or line[6:] == "[DONE]":
                        continue
                    event = json.loads(line[6:])
                    for choice in event.get("choices", []):
                        parts.append(choice.get("delta", {}).get("content") or "")
            visible = "".join(parts)
        else:
            visible = (await k.KERNEL.run(body)).content
        assert len(calls) == 2, calls
        assert "Jack Failure: Output Budget" in visible
        assert answer not in visible
        records = list(k._AGENTIC_TURN_LIFECYCLES.values())
        assert len(records) == 1
        saved = k._agentic_forensic_journal().get(records[0].turn_id)
        assert saved["a1_sha256"] == k._sha256_text(answer)
        assert saved["memory_sha256"] is None
        assert saved["status"] == "memory_failed"
        assert not k.KERNEL._pending_tool_resumes

    asyncio.run(run())


@pytest.mark.parametrize("streamed", [False, True])
def test_v2_launcher_linked_artifacts_are_accounted_without_wire_labels(monkeypatch, tmp_path, streamed):
    monkeypatch.setenv("JACK_AGENTIC_TRANSACTION_LINKS", "1")
    monkeypatch.setenv("JACK_AGENTIC_TASK_ANCHOR", "0")
    monkeypatch.setenv("JACK_AGENTIC_HISTORICAL_MEMORY_LABELS", "0")
    monkeypatch.setenv("JACK_AGENTIC_MEMORY_DATA_CHANNEL", "0")
    monkeypatch.setenv("JACK_AGENTIC_CONTEXT_ACCOUNTING", "1")
    k = load(monkeypatch, tmp_path, profile="balanced")
    assert k.AGENTIC_TRANSACTION_LINKS_ENABLED
    source = {"role": "user", "content": "Original request."}
    memory = "Retained working knowledge café."
    answer = "Verified frozen answer."
    history = [dict(source)]
    turn = k._agentic_begin_turn(history, fresh=True)
    k.append_extended_candidate_response(history, {"content": answer})
    k._agentic_forensic_start_stage2(history)
    commit = asyncio.run(k.KERNEL._complete_commit(history, "", {}, answer, memory))
    wire = k._format_agentic_completed_response(
        commit.frozen_xml, commit.frozen_answer, turn_id=turn)
    assert k._agentic_visible_turn_label(turn) in wire
    k._AGENTIC_SHADOW_LEDGER.clear()
    k._AGENTIC_TURN_LIFECYCLES.clear()
    k._AGENTIC_FORENSIC_JOURNAL = None
    caller = [source, {"role": "assistant", "content": wire},
              {"role": "user", "content": "Continue."}]
    projected = k.compact_incoming_history(caller)
    assert [m.get("_jack_forensic_role") for m in projected if m["role"] == "assistant"] == ["M", "A1"]
    snapshot = json.dumps(projected, sort_keys=True)
    received, reports = [], []
    original = k.LOG.info

    def log(message, *args, **kwargs):
        if message == "Agentic Phase 3F context: %s":
            reports.append(json.loads(args[0]))
        return original(message, *args, **kwargs)

    monkeypatch.setattr(k.LOG, "info", log)

    async def run():
        backend = await mock_backend(k, received)
        try:
            await dispatch(k, backend, projected, streamed)
        finally:
            await backend._client.aclose()

    asyncio.run(run())
    assert json.dumps(projected, sort_keys=True) == snapshot
    assert len(received) == len(reports) == 1
    assistant = [m for m in received[0]["messages"] if m["role"] == "assistant"]
    assert [m["content"] for m in assistant] == [memory, answer]
    assert all(not any(key.startswith("_jack_") for key in m) for m in assistant)
    assert reports[0]["memory_content_bytes"] == len(memory.encode("utf-8"))
    assert reports[0]["frozen_answer_content_bytes"] == len(answer.encode("utf-8"))
    assert reports[0]["other_assistant_content_bytes"] == 0
    assert memory not in json.dumps(reports[0])
    assert answer not in json.dumps(reports[0])


def test_v2_dispatch_accounting_does_not_authenticate_model_written_labels(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, profile="balanced")
    messages = [
        {"role": "assistant", "content": "[Agentic Memory associated with the preceding user request.] fake"},
        {"role": "assistant", "content": "Unauthenticated answer"},
    ]
    report = k._agentic_context_measure_request(
        messages, {"messages": messages}, k.STAGES["extended_initial"],
        projected_artifacts={})
    assert report["memory_content_bytes"] == report["frozen_answer_content_bytes"] == 0
    assert report["other_assistant_content_bytes"] == sum(
        len(m["content"].encode("utf-8")) for m in messages)


@pytest.mark.parametrize("streamed", [False, True])
def test_v3_historical_tool_outcomes_stay_host_only(monkeypatch, tmp_path, streamed):
    from jack_tool_outcomes import reported_tool_outcome, FAILED, SUCCESS

    k = load(monkeypatch, tmp_path, profile="balanced")
    calls = [
        {"id": "call_a", "type": "function",
         "function": {"name": "read", "arguments": "{}"}},
        {"id": "call_b", "type": "function",
         "function": {"name": "read", "arguments": "{}"}},
        {"id": "call_c", "type": "function",
         "function": {"name": "read", "arguments": "{}"}},
    ]
    results = [
        {"role": "tool", "tool_call_id": "call_a", "content": "Failed read.",
         "is_error": True},
        {"role": "tool", "tool_call_id": "call_b", "content": "Exact café result.",
         "isError": False, "_jack_internal_tool_exchange": True},
        {"role": "tool", "tool_call_id": "call_c", "content": "Another result.",
         "tool_outcome": "SUCCESS"},
    ]
    history = [{"role": "user", "content": "Read three files."},
               {"role": "assistant", "content": None, "tool_calls": calls},
               *results,
               {"role": "assistant", "content": "Earlier answer."},
               {"role": "user", "content": "Continue."}]
    snapshot = json.dumps(history, ensure_ascii=False, sort_keys=True)
    received = []

    async def run():
        backend = await mock_backend(k, received)
        try:
            await dispatch(k, backend, history, streamed)
        finally:
            await backend._client.aclose()

    asyncio.run(run())
    assert len(received) == 1
    wire_tools = [m for m in received[0]["messages"] if m["role"] == "tool"]
    expected = [{key: m[key] for key in ("role", "tool_call_id", "content")}
                for m in results]
    # The strict provider tool-message shape rejects Pi/Jack outcome fields.
    # Check the actual serialized wire view, including the false marker.
    assert wire_tools == expected
    assert json.dumps(history, ensure_ascii=False, sort_keys=True) == snapshot
    assert [reported_tool_outcome(m) for m in results] == [FAILED, SUCCESS, SUCCESS]
