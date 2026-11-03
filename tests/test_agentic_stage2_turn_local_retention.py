"""A/B/C Stage-2 turn-local cognitive retention: request-only opt-in experiment.

No live model is used. Capture streaming/nonstreaming backend requests and
assert that host-owned history, exact Stage-1 R1/A1, complete tool chronology,
cache-append schemas and stage authority are preserved.
"""
import asyncio
import copy
import importlib.util
import json
import sys
import uuid
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ("baseline", "isolate", "isolate-retain")
CALLER_SYSTEM = "CUSTOM_SYSTEM_SENTINEL: historical instruction must not govern Stage 2"


def load_kernel(monkeypatch, tmp_path, variant):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_AGENTIC_TRANSACTION_LINKS", "1")
    monkeypatch.setenv("JACK_AGENTIC_TASK_ANCHOR", "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT", "1")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_FINAL_PAPER", "0")
    monkeypatch.setenv("JACK_AGENTIC_DIFFERENTIAL_MEMORY", "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_RETENTION_TEST", variant)
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv(
        "JACK_AGENTIC_FORENSIC_DB",
        str(tmp_path / (uuid.uuid4().hex + ".sqlite")),
    )
    name = "jack_stage2_turn_local_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def history():
    return [
        {"role": "user", "content": "Old request from another turn"},
        {"role": "assistant", "content": "Old memory: do not edit clocks."},
        {"role": "assistant", "content": "Old frozen answer"},
        {
            "role": "assistant",
            "content": "Older R2",
            "reasoning_content": "Earlier Stage 2 reasoning.",
            "_jack_agentic_one_hop_r2": True,
        },
        {"role": "user", "content": "Change clock color to gold, verify and report."},
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "R1 before tools: first try edit.",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "edit", "arguments": '{"color":"gold"}'},
                }
            ],
            "_jack_internal_tool_exchange": True,
        },
        {
            "role": "tool",
            "name": "edit",
            "tool_call_id": "call-1",
            "content": "Error: wrong path",
            "_jack_internal_tool_exchange": True,
            "_jack_internal_tool_failed": True,
        },
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "R1 after error: fix path and retry.",
            "tool_calls": [
                {
                    "id": "call-2",
                    "type": "function",
                    "function": {"name": "edit", "arguments": '{"path":"clock.html","color":"gold"}'},
                }
            ],
            "_jack_internal_tool_exchange": True,
        },
        {
            "role": "tool",
            "name": "edit",
            "tool_call_id": "call-2",
            "content": "Reported success. Browser not available.",
            "_jack_internal_tool_exchange": True,
        },
        {
            "role": "assistant",
            "content": "Set clock to gold; visual verification unavailable.",
            "reasoning_content": "Final R1: changed the path, second edit reported success but did not verify visual result.",
            "_jack_extended_candidate_response": True,
        },
    ]


def tools():
    return [{"type": "function", "function": {
        "name": "edit",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
    }}]


async def payload_for(k, stage, stream, h):
    captured = []

    def reply(request):
        captured.append(json.loads(request.content))
        if stream:
            data = "\n\n".join([
                'data: {"choices":[{"index":0,"delta":{"reasoning_content":"why"},"finish_reason":null}]}',
                'data: {"choices":[{"index":0,"delta":{"content":"Useful memory"},"finish_reason":null}]}',
                'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}',
                "data: [DONE]",
            ]) + "\n\n"
            return httpx.Response(
                200, text=data, headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json={
            "choices": [{
                "message": {"role": "assistant", "content": "Useful memory"},
                "finish_reason": "stop",
            }],
            "usage": {},
        })

    backend = k.OpenAICompatibleBackend(k.CFG)
    await backend._client.aclose()
    backend._client = httpx.AsyncClient(transport=httpx.MockTransport(reply))

    async def resolve_model():
        return "test-model"

    backend.resolve_model = resolve_model
    try:
        args = dict(
            messages=h,
            secondary_system=CALLER_SYSTEM,
            profile=k.STAGES[stage],
            tools=tools(),
            tool_choice="auto",
        )
        if stream:
            async for _ in backend.chat_stream(**args):
                pass
        else:
            await backend.chat(**args)
    finally:
        await backend._client.aclose()
    assert len(captured) == 1
    return captured[0]


@pytest.mark.parametrize("stream", [False, True])
def test_abc_current_turn_projection_and_original_history_unchanged(monkeypatch, tmp_path, stream):
    results = {}
    raw = history()
    frozen = copy.deepcopy(raw)
    for variant in VARIANTS:
        k = load_kernel(monkeypatch, tmp_path, variant)
        payload = asyncio.run(payload_for(k, "extended_reflection", stream, raw))
        results[variant] = (k, payload)
        assert raw == frozen
        assert payload["stream"] is stream
        assert payload["messages"][0]["content"] == k.AGENTIC_STAGE1_PROMPT
        assert CALLER_SYSTEM not in json.dumps(payload)
        assert payload["chat_template_kwargs"]["preserve_thinking"] is True
        assert "tools" not in payload
        assert k.STAGES["extended_reflection"].allow_tools is False

    base = results["baseline"][1]
    isolated = results["isolate"][1]
    retention = results["isolate-retain"][1]
    old = base["messages"][1:-1]
    current = isolated["messages"][1:-1]
    assert len(old) == len(frozen)
    assert len(current) == 4  # current U, two R1 fragments, frozen A1/R1
    assert isolated["messages"][:-1] == retention["messages"][:-1]
    assert isolated["messages"][-1] == base["messages"][-1]
    assert retention["messages"][-1]["content"].startswith(
        results["isolate-retain"][0].AGENTIC_36_STAGE2_PROMPT
    )
    assert "Treat this turn's Stage-1 native reasoning as a draft" in (
        retention["messages"][-1]["content"]
    )
    assert "Earlier Stage 2 reasoning" not in json.dumps(isolated["messages"])
    assert current[0]["role"] == "user"
    assert current[0]["content"] == frozen[4]["content"]
    assert current[1]["reasoning_content"] == "R1 before tools: first try edit."
    assert current[2]["reasoning_content"] == "R1 after error: fix path and retry."
    assert current[3]["reasoning_content"].startswith("Final R1:")
    assert current[-1]["content"] == frozen[-1]["content"]
    assert not any(m.get("tool_calls") or m.get("role") == "tool" for m in current)
    assert "Error: wrong path" not in json.dumps(current)
    assert "Reported success. Browser not available." not in json.dumps(current)
    assert all(
        not any(key.startswith("_jack_") for key in m)
        for m in current if isinstance(m, dict)
    )


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("variant", VARIANTS)
def test_stage1_backend_payload_is_unmodified_by_experiment(monkeypatch, tmp_path, stream, variant):
    k = load_kernel(monkeypatch, tmp_path, variant)
    raw = history()
    request = raw[:5]
    original = copy.deepcopy(request)
    payload = asyncio.run(payload_for(k, "extended_initial", stream, request))
    assert request == original
    assert payload["messages"][1:] == k.BACKEND._stage_messages_for_profile(
        request, k.STAGES["extended_initial"]
    )
    assert payload["messages"][0]["content"] == k.AGENTIC_STAGE1_PROMPT


@pytest.mark.parametrize("variant", ("isolate", "isolate-retain"))
def test_isolation_fails_closed_without_frozen_a1(monkeypatch, tmp_path, variant):
    k = load_kernel(monkeypatch, tmp_path, variant)
    with pytest.raises(k.HTTPException) as exc:
        k._agentic_stage2_test_history(history()[:-1], k.STAGES["extended_reflection"])
    assert exc.value.status_code == 409


def test_default_isolated_retention_and_immutable_prompts(monkeypatch, tmp_path):
    # Loader sets the A/B variant explicitly. Remove that override and
    # reimport to check the deployed default.
    load_kernel(monkeypatch, tmp_path, "baseline")
    monkeypatch.delenv("JACK_AGENTIC_STAGE2_RETENTION_TEST", raising=False)
    name = "jack_default_retention_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    assert k.AGENTIC_STAGE2_RETENTION_TEST == "isolate-retain"
    continuation = k._stage_continuation(k.STAGES["extended_reflection"])
    assert "Treat this turn\'s Stage-1 native reasoning as a draft" in continuation
    assert "without retrospective headings" in continuation
    assert "Do not independently" in continuation
    assert "unresolved matters" in continuation
    assert k.AGENTIC_36_STAGE2_PROMPT == "Preserve useful working knowledge from the completed task for future work, not a retrospective report."
    assert k.AGENTIC_STAGE1_PROMPT == (
        "Reasoning effort is set to xhigh. Please think carefully through the task, "
        "validate key assumptions, consider plausible alternatives, and prioritize "
        "correctness, consistency, and clarity in the final answer."
    )
    assert k._agentic_stage2_test_history(
        history(), k.STAGES["extended_reflection"],
    ) == [
        history()[4],
        {"role": "assistant", "content": "", "reasoning_content": "R1 before tools: first try edit."},
        {"role": "assistant", "content": "", "reasoning_content": "R1 after error: fix path and retry."},
        history()[-1],
    ]


@pytest.mark.parametrize("variant", ("isolate", "isolate-retain"))
def test_stage2_tool_rejection_retries_without_losing_frozen_answer(monkeypatch, tmp_path, variant):
    k = load_kernel(monkeypatch, tmp_path, variant)
    original = history()
    frozen = original[-1]
    assert frozen["_jack_extended_candidate_response"] is True
    proposed = {"role": "assistant", "content": "I need a tool", "reasoning_content": "Must read file."}
    corrected = k._tool_rejection_history(
        original, proposed, ["Agentic native pass 2: this stage has no tool authority"],
        k.STAGES["extended_reflection"].name,
    )
    projected = k._agentic_stage2_test_history(corrected, k.STAGES["extended_reflection"])
    assert projected[0]["content"] == original[4]["content"]
    assert projected[-2]["content"] == frozen["content"]
    assert not any(p.get("_jack_internal_tool_validation_checkpoint") for p in projected)
    assert not any(p.get("role") == "tool" or p.get("tool_calls") for p in projected)
    assert projected[-1]["_jack_internal_tool_validation_rejection"] is True
    assert "Earlier Stage 2 reasoning" not in str(projected)
    # A second rejected proposal must remain in the same authentic turn.
    retried = k._tool_rejection_history(
        corrected, proposed, ["Agentic native pass 2: this stage has no tool authority"],
        k.STAGES["extended_reflection"].name,
    )
    assert k._agentic_stage2_test_history(retried, k.STAGES["extended_reflection"])[-1][
        "_jack_internal_tool_validation_rejection"
    ] is True


def test_stage2_rejects_unowned_suffix_after_frozen_answer(monkeypatch, tmp_path):
    k = load_kernel(monkeypatch, tmp_path, "isolate-retain")
    unowned = history() + [{"role": "user", "content": "Different actual request"}]
    with pytest.raises(k.HTTPException) as exc:
        k._agentic_stage2_test_history(unowned, k.STAGES["extended_reflection"])
    assert exc.value.status_code == 409
