from __future__ import annotations

import asyncio
import hashlib
import json

import pytest

import jack_kernel as kernel


def _tool_group(result: str = "created artifact"):
    arguments = json.dumps({"path": "artifact.txt", "content": "hello"})
    return [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call-1",
                "type": "function",
                "function": {"name": "create_file", "arguments": arguments},
            }],
            "_jack_internal_tool_exchange": True,
            "_jack_stage_key": "thesis",
        },
        {
            "role": "tool",
            "tool_call_id": "call-1",
            "name": "create_file",
            "content": result,
            "_jack_internal_tool_exchange": True,
        },
    ]


def _receipt(result: str = "created artifact"):
    return kernel._tool_evidence_receipts_from_group(_tool_group(result))[0]


def test_authoritative_receipt_remains_internal_without_false_pi_recovery():
    receipt = _receipt()

    assert receipt["content"].startswith("<jack_tool_evidence_receipt>\n")
    assert receipt["content"].endswith("\n</jack_tool_evidence_receipt>")
    assert receipt["_jack_tool_evidence_receipt"] is True
    assert "PI_SESSION_JSONL_BY_TOOL_CALL_ID" not in receipt["content"]


def test_backend_projection_removes_reserved_wrapper_and_preserves_evidence_facts():
    result = "created artifact"
    receipt = _receipt(result)
    projected = kernel.BACKEND._stage_messages_for_profile(
        [receipt], kernel.STAGES["thesis"]
    )[0]
    content = projected["content"]

    assert sorted(projected) == ["content", "role"]
    assert "jack_tool_evidence_receipt" not in content.lower()
    assert content.startswith("[TOOL EVIDENCE FACTS]\n")
    assert content.endswith("\n[END TOOL EVIDENCE FACTS]")
    assert "Tool Call ID: call-1" in content
    assert "Stage: THESIS" in content
    assert "Tool: create_file" in content
    assert "Status: SUCCESS" in content
    assert "Artifact Effect: MUTATION" in content
    assert "Artifact Target: artifact.txt" in content
    assert "Artifact Targets: artifact.txt" in content
    assert "Arguments SHA256:" in content
    assert f"Result SHA256: {hashlib.sha256(result.encode('utf-8')).hexdigest()}" in content
    assert f"Result Bytes: {len(result.encode('utf-8'))}" in content
    assert "Result Truncated: NO" in content
    assert "Result Excerpt:\ncreated artifact" in content


def test_multi_tool_frontier_rolling_keeps_safe_evidence_available_to_backend():
    group = _tool_group("first frontier result")
    group[0]["tool_calls"].append({
        "id": "call-2",
        "type": "function",
        "function": {"name": "read", "arguments": json.dumps({"path": "artifact.txt"})},
    })
    group.append({
        "role": "tool",
        "tool_call_id": "call-2",
        "name": "read",
        "content": "second frontier result",
        "_jack_internal_tool_exchange": True,
    })

    rolled, removed, carried_failures = kernel.JackQwenKernel._roll_tool_frontier(group)

    assert removed == 3
    assert carried_failures == 0
    assert len(rolled) == 2
    assert all("<jack_tool_evidence_receipt>" in item["content"] for item in rolled)

    projected = kernel.BACKEND._stage_messages_for_profile(rolled, kernel.STAGES["thesis"])
    contents = "\n".join(item["content"] for item in projected)
    assert "jack_tool_evidence_receipt" not in contents.lower()
    assert "first frontier result" in contents
    assert "second frontier result" in contents
    assert contents.count("Result SHA256:") == 2


def test_streaming_and_nonstreaming_backend_paths_use_the_projection(monkeypatch):
    backend = kernel.OpenAICompatibleBackend(kernel.CFG)
    calls = []

    async def resolved_model():
        return "test-model"

    def projection(messages, profile):
        calls.append((messages, profile))
        raise RuntimeError("projection reached")

    monkeypatch.setattr(backend, "resolve_model", resolved_model)
    monkeypatch.setattr(backend, "_stage_messages_for_profile", projection)

    async def exercise():
        with pytest.raises(RuntimeError, match="projection reached"):
            await backend.chat(
                messages=[_receipt()],
                secondary_system="",
                profile=kernel.STAGES["thesis"],
            )
        with pytest.raises(RuntimeError, match="projection reached"):
            await anext(backend.chat_stream(
                messages=[_receipt()],
                secondary_system="",
                profile=kernel.STAGES["thesis"],
            ))

    asyncio.run(exercise())
    assert len(calls) == 2
