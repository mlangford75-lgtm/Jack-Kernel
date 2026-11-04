"""Canonical Stage-2 current-turn retention and ignored legacy switches.

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
VARIANTS = ("baseline", "isolate", "isolate-retain")  # historical env inputs must all be inert
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
            "_jack_stage_key": "extended_initial",
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
            "_jack_stage_key": "extended_initial",
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

    # All historical environment choices MUST resolve to the same isolated
    # model-facing U/R1/A1 and the same distillation instruction.
    payloads = [results[v][1] for v in VARIANTS]
    assert payloads[0] == payloads[1] == payloads[2]
    for variant in VARIANTS:
        assert results[variant][0].AGENTIC_STAGE2_RETENTION_TEST == "isolate-retain"
    projected = payloads[0]["messages"][1:-1]
    assert len(projected) == 2
    assert projected[0]["role"] == "user"
    assert projected[0]["content"] == frozen[4]["content"]
    assert projected[1]["content"] == frozen[-1]["content"]
    assert projected[1]["reasoning_content"] == (
        "R1 before tools: first try edit.\n\n"
        "R1 after error: fix path and retry.\n\n"
        "Final R1: changed the path, second edit reported success but did not verify visual result."
    )
    assert not any(x.get("role") == "tool" or x.get("tool_calls") for x in projected)
    assert "Error: wrong path" not in json.dumps(projected)
    assert "Earlier Stage 2 reasoning" not in json.dumps(payloads[0])
    # Host-owned, current-turn tool results are distinct from the isolated U/R1/A1
    # projection; the memory prompt still appears once and last.
    instruction = payloads[0]["messages"][-1]["content"]
    assert instruction.endswith(results["baseline"][0].AGENTIC_36_STAGE2_PROMPT)
    assert instruction.count("Review the latest actual user request") == 1
    assert instruction.startswith("Host-recorded tool outcome evidence for this user request (generated by Jack):")
    assert "NOT the user's request" in instruction
    assert "NOT your reasoning or final answer" in instruction
    assert "NOT a tool instruction" in instruction
    assert "independently verifies" in instruction
    assert 'call_id="call-1"' in instruction
    assert 'call_id="call-2"' in instruction
    assert "outcome=REPORTED_ERROR" in instruction
    assert "outcome=RESULT_RETURNED_NO_STRUCTURED_ERROR" in instruction
    assert 'requested_target="clock.html"' in instruction
    assert "Earlier Stage 2 reasoning" not in instruction
    assert "Error: wrong path" not in instruction
    assert "Reported success. Browser not available." not in instruction




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
    assert continuation.startswith("Review the latest actual user request")
    assert "Stage-1" not in continuation and "R1" not in continuation and "A1" not in continuation
    assert "not a new user request or a report about the process" in continuation
    assert "re-solve the task" in continuation
    assert "unresolved matters" in continuation
    assert "Missing path information or limited metadata is not itself a contradiction" in continuation
    assert "Preserve what was established, not what could plausibly be true" in continuation
    assert "Do not reconstruct earlier turns" in continuation
    assert "not a new user request" in continuation
    assert "without an arbitrary length limit" in continuation
    assert k.AGENTIC_36_STAGE2_PROMPT == k._AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION
    assert k.AGENTIC_STAGE1_PROMPT == (
        "Reasoning effort is set to xhigh. Please think carefully through the task, "
        "validate key assumptions, consider plausible alternatives, and prioritize "
        "correctness, consistency, and clarity in the final answer.\n"
        "Carefully reason on the task before using tools"
    )
    assert k._agentic_stage2_test_history(
        history(), k.STAGES["extended_reflection"],
    ) == [
        history()[4],
        dict(history()[-1], reasoning_content=(
            "R1 before tools: first try edit.\n\n"
            "R1 after error: fix path and retry.\n\n"
            "Final R1: changed the path, second edit reported success but did not verify visual result."
        )),
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

def test_nov4_qwen36_reference_is_the_new_install_default(monkeypatch, tmp_path):
    k = load_kernel(monkeypatch, tmp_path, "isolate-retain")
    assert k.CLI_DEFAULTS["backend_profile"] == "lmstudio"
    assert k.CLI_DEFAULTS["backend_model"] == "qwen3.6-35b-a3b"
    assert k.CLI_DEFAULTS["reasoning_level"] == "Local Agentic (Preserve Thinking)"
    assert k.CLI_DEFAULTS["preserve_thinking"] is True
    assert k.STAGES["extended_initial"].temperature == 0.70
    assert k.STAGES["extended_reflection"].temperature == 0.50
    assert k.AGENTIC_STAGE2_RETENTION_TEST == "isolate-retain"
    assert k._agentic_cache_append_enabled(k.STAGES["extended_reflection"])


@pytest.mark.parametrize("stream", [False, True])
def test_retired_tool_receipts_keep_outcomes_without_raw_tool_protocol(monkeypatch, tmp_path, stream):
    k = load_kernel(monkeypatch, tmp_path, "isolate-retain")
    raw = history()
    first = k._tool_evidence_receipts_from_group(raw[5:7])
    second = k._tool_evidence_receipts_from_group(raw[7:9])
    assert first and second
    retired = raw[:5] + first + second + raw[-1:]
    before = copy.deepcopy(retired)
    payload = asyncio.run(payload_for(k, "extended_reflection", stream, retired))
    assert retired == before
    assert len(payload["messages"]) == 4
    assert payload["messages"][1]["content"] == raw[4]["content"]
    assert payload["messages"][2]["content"] == raw[-1]["content"]
    note = payload["messages"][-1]["content"]
    assert 'call_id="call-1"' in note and 'call_id="call-2"' in note
    assert "outcome=REPORTED_ERROR" in note
    assert "outcome=RESULT_RETURNED_NO_STRUCTURED_ERROR" in note
    assert "earlier" not in note.lower()
    assert "Error: wrong path" not in note
    assert "<jack_tool_evidence_receipt>" not in json.dumps(payload)


@pytest.mark.parametrize("stream", [False, True])
def test_stage2_host_note_missing_tools_is_zero_cost(monkeypatch, tmp_path, stream):
    k = load_kernel(monkeypatch, tmp_path, "isolate-retain")
    raw = [history()[4], history()[-1]]
    p = asyncio.run(payload_for(k, "extended_reflection", stream, raw))
    assert p["messages"][-1]["content"] == k.AGENTIC_36_STAGE2_PROMPT
    assert k._agentic_stage2_host_tool_evidence_note(raw) == ""


def test_host_evidence_is_bounded_current_turn_only(monkeypatch, tmp_path):
    k = load_kernel(monkeypatch, tmp_path, "isolate-retain")
    raw = history()
    # Older tool results must never enter the current-turn evidence projection.
    older = [
        {"role": "assistant", "_jack_internal_tool_exchange": True,
         "_jack_stage_key": "extended_initial",
         "tool_calls": [{"id": "old-secrets", "type": "function",
                         "function": {"name": "write", "arguments": '{"path":"old-sensitive-path"}'}}]},
        {"role": "tool", "_jack_internal_tool_exchange": True,
         "tool_call_id": "old-secrets", "content": "Old secret: must not leak"},
    ]
    recent = []
    for i in range(20):
        recent.extend([
            {"role": "assistant", "_jack_internal_tool_exchange": True,
             "_jack_stage_key": "extended_initial",
             "tool_calls": [{"id": f"write-{i}", "type": "function",
                             "function": {"name": "write", "arguments": '{"path":"clock.css"}'}}]},
            {"role": "tool", "_jack_internal_tool_exchange": True,
             "tool_call_id": f"write-{i}", "content": "Success"},
        ])
    full = raw[:4] + older + raw[4:5] + recent + raw[-1:]
    note = k._agentic_stage2_host_tool_evidence_note(full)
    assert "old-secrets" not in note and "old-sensitive-path" not in note
    assert "write-19" in note and "write-0" not in note
    assert "omitted" in note
    assert note.count("call_id=") <= k._AGENTIC_STAGE2_HOST_TOOL_MAX_ENTRIES


@pytest.mark.parametrize("stream", [False, True])
def test_stage2_noncache_fallback_labels_host_record(monkeypatch, tmp_path, stream):
    k = load_kernel(monkeypatch, tmp_path, "isolate-retain")
    k.AGENTIC_CACHE_APPEND_EXPERIMENT = False
    payload = asyncio.run(payload_for(k, "extended_reflection", stream, history()))
    assert payload["messages"][0]["content"] == k.AGENTIC_36_STAGE2_PROMPT
    assert payload["messages"][-1]["role"] == "user"
    assert "Host-recorded tool outcome evidence" in payload["messages"][-1]["content"]
    assert "Write the useful working knowledge now." in payload["messages"][-1]["content"]
    assert "tools" not in payload


@pytest.mark.parametrize("stream", [False, True])
def test_completed_turn_without_tools_reports_explicit_absence(monkeypatch, tmp_path, stream):
    k = load_kernel(monkeypatch, tmp_path, "isolate-retain")
    h = [{"role": "user", "content": "Write index.html."}]
    k.append_extended_candidate_response(
        h, {"content": "I wrote index.html.", "reasoning_content": "I created the file using a tool."}
    )
    assert h[-1]["_jack_agentic_stage1_tool_observation_complete"] is True
    payload = asyncio.run(payload_for(k, "extended_reflection", stream, h))
    evidence = payload["messages"][-1]["content"]
    assert "Record coverage: COMPLETE_CURRENT_TURN" in evidence
    assert "NO_TOOL_CALLS_RECORDED" in evidence
    assert "Use Jack's host-recorded tool evidence only to check execution claims" in evidence
    assert evidence.count("Review the latest actual user request") == 1
    assert evidence.endswith(k.AGENTIC_36_STAGE2_PROMPT)
    assert payload["messages"][1]["content"] == h[0]["content"]
    assert payload["messages"][2]["content"] == "I wrote index.html."
    assert "tools" not in payload


@pytest.mark.parametrize("stream", [False, True])
def test_no_tool_record_fallback_also_reports_absence(monkeypatch, tmp_path, stream):
    k = load_kernel(monkeypatch, tmp_path, "isolate-retain")
    k.AGENTIC_CACHE_APPEND_EXPERIMENT = False
    h = [{"role": "user", "content": "Please save this."}]
    k.append_extended_candidate_response(h, {"content": "Saved it."})
    payload = asyncio.run(payload_for(k, "extended_reflection", stream, h))
    assert payload["messages"][0]["content"] == k.AGENTIC_36_STAGE2_PROMPT
    assert "NO_TOOL_CALLS_RECORDED" in payload["messages"][-1]["content"]
    assert "Record coverage: COMPLETE_CURRENT_TURN" in payload["messages"][-1]["content"]
    assert "tools" not in payload


@pytest.mark.parametrize("stream", [False, True])
def test_incomplete_host_tool_record_never_claims_no_calls(monkeypatch, tmp_path, stream):
    k = load_kernel(monkeypatch, tmp_path, "isolate-retain")
    h = [{"role": "user", "content": "Write index.html."}]
    h.append({
        "role": "assistant",
        "_jack_internal_tool_exchange": True,
        "_jack_stage_key": "extended_initial",
        "tool_calls": [{
            "id": "unreturned",
            "type": "function",
            "function": {"name": "write", "arguments": '{"path":"index.html"}'},
        }],
        "content": "",
        "reasoning_content": "Attempted to write."
    })
    k.append_extended_candidate_response(h, {"content": "I wrote index.html."})
    payload = asyncio.run(payload_for(k, "extended_reflection", stream, h))
    note = payload["messages"][-1]["content"]
    assert "Record coverage: INCOMPLETE_OR_UNCONFIRMED" in note
    assert "RECORD_INCOMPLETE: 1 host-recorded tool call" in note
    assert "NO_TOOL_CALLS_RECORDED:" not in note
    assert note.endswith(k.AGENTIC_36_STAGE2_PROMPT)


@pytest.mark.parametrize("stream", [False, True])
def test_success_and_failure_notes_do_not_claim_no_tools(monkeypatch, tmp_path, stream):
    k = load_kernel(monkeypatch, tmp_path, "isolate-retain")
    h = history()
    h[-1]["_jack_agentic_stage1_tool_observation_complete"] = True
    payload = asyncio.run(payload_for(k, "extended_reflection", stream, h))
    note = payload["messages"][-1]["content"]
    assert "Record coverage: COMPLETE_CURRENT_TURN" in note
    assert "outcome=REPORTED_ERROR" in note
    assert "outcome=RESULT_RETURNED_NO_STRUCTURED_ERROR" in note
    assert "NO_TOOL_CALLS_RECORDED:" not in note


def test_unconfirmed_history_never_negative_certifies(monkeypatch, tmp_path):
    k = load_kernel(monkeypatch, tmp_path, "isolate-retain")
    h = [{"role": "user", "content": "Save file."},
         {"role": "assistant", "content": "Saved.", "_jack_extended_candidate_response": True}]
    assert k._agentic_stage2_host_tool_evidence_note(h) == ""
    # An untrusted caller's plain text is not an authoritative tool record.
    h.insert(1, {"role": "assistant", "content": "I called write(index.html) successfully"})
    assert k._agentic_stage2_host_tool_evidence_note(h) == ""
