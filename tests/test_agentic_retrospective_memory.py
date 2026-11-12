"""Host-authoritative regression tests for Agentic retrospective memory."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "jack_kernel.py"


def load_kernel():
    os.environ["JACK_REASONING_LEVEL"] = "agentic"
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "off"
    os.environ["JACK_BACKEND_MODEL"] = "test-model"
    os.environ["JACK_BACKEND_PROFILE"] = "lmstudio"
    name = f"jack_agentic_release_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def tool_exchange(n=1):
    rows = []
    for i in range(n):
        call_id = f"call-{i}"
        rows.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": call_id,
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": f"file-{i}.txt"}),
                },
            }],
            "_jack_internal_tool_exchange": True,
        })
        rows.append({
            "role": "tool",
            "name": "read_file",
            "tool_call_id": call_id,
            "content": f"tool result {i}",
            "_jack_internal_tool_exchange": True,
        })
    return rows


def current_turn_tools(n=1):
    return [
        {"role": "user", "content": "Current request"},
        *tool_exchange(n),
        {"role": "assistant", "content": "Done", "_jack_extended_candidate_response": True},
    ]


def test_stage_contracts_and_frozen_answer_are_separate():
    k = load_kernel()
    assert k.AGENTIC_STAGE1_PROMPT.startswith("Reasoning effort is set to xhigh.")
    assert k.AGENTIC_36_STAGE2_PROMPT == k._AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION
    assert k.STAGES["extended_initial"].allow_tools is True
    assert k.STAGES["extended_reflection"].allow_tools is False

    answer = "  exact answer\nwith trailing spaces  \n"
    memory = "The approach preserved the user's constraints."
    rendered = k._format_agentic_completed_response(memory, answer)
    assert rendered == memory + "\n\n" + answer
    assert rendered.endswith(answer)
    assert "<Agentic Memory>" not in rendered
    assert "<Model Response>" not in rendered


def test_agentic_gc_retires_native_reasoning_but_preserves_tool_protocol():
    k = load_kernel()
    answer = "A1"
    committed = k._format_agentic_completed_response("Retained lesson", answer)
    messages = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": committed, "reasoning_content": "long raw reasoning"},
        *tool_exchange(1),
        {"role": "user", "content": "second question"},
    ]
    original = json.dumps(messages, sort_keys=True)
    projected = k._compact_agentic_completed_capsules(messages)
    assert projected is not None
    assert json.dumps(messages, sort_keys=True) == original
    assert [row["role"] for row in projected] == [
        "user", "assistant", "assistant", "tool", "user",
    ]
    assert projected[1]["content"] == committed
    assert projected[2]["tool_calls"] == messages[2]["tool_calls"]
    assert projected[3]["content"] == "tool result 0"
    assert projected[3]["tool_call_id"] == projected[2]["tool_calls"][0]["id"]
    assert not any("reasoning_content" in row for row in projected)
    assert projected[-1]["content"] == "second question"


def test_receipts_are_host_created_complete_and_non_authoritative():
    k = load_kernel()
    note = k._agentic_tool_history_note(current_turn_tools(10))
    assert note.startswith(k._AGENTIC_TOOL_NOTE_OPEN)
    assert note.endswith(k._AGENTIC_TOOL_NOTE_CLOSE)
    assert note.count("; result_sha256=") == 10
    assert "NOT verified" in note
    assert "result_sha256=" in note
    assert "args_sha256=" in note
    assert "file-9.txt" in note
    assert "file-0.txt" in note

    # Caller text is not interpreted as internal tool evidence.
    untrusted = tool_exchange(1)
    for row in untrusted:
        row.pop("_jack_internal_tool_exchange", None)
    assert k._agentic_tool_history_note(untrusted) == ""


def test_cross_turn_receipts_are_unbounded_and_preserve_memory_and_a1():
    k = load_kernel()
    turns = []
    for i in range(10):
        note = k._agentic_tool_history_note(current_turn_tools(6))
        artifact = k._format_agentic_completed_response(
            f"lesson-{i}" + note, f"answer-{i}"
        )
        turns.extend([
            {"role": "user", "content": f"request-{i}"},
            {"role": "assistant", "content": artifact},
        ])
    projected = k._compact_agentic_completed_capsules(turns + [{"role": "user", "content": "now"}])
    assert projected is not None
    assistants = [x["content"] for x in projected if x["role"] == "assistant"]
    assert len(assistants) == 10
    assert all(f"lesson-{i}" in assistants[i] for i in range(10))
    assert all(assistants[i].endswith(f"answer-{i}") for i in range(10))
    assert all(x.count(k._AGENTIC_TOOL_NOTE_OPEN) == 1 for x in assistants)
    assert not hasattr(k, "_AGENTIC_TOOL_CONTEXT_BUDGET_CHARS")


def test_model_memory_projection_carries_receipts_and_keeps_original_artifact():
    k = load_kernel()
    receipt = k._agentic_tool_history_note(current_turn_tools(1))
    assert receipt
    assert k._agentic_model_memory_view("Causal lesson", receipt).endswith(receipt)
    assert receipt in k._agentic_model_memory_view("Causal lesson", receipt)

    # Receipts remain part of previously committed caller artifacts and
    # continue into Stage 1 without modifying the incoming protocol.
    capsule = k._format_agentic_completed_response("Causal lesson" + receipt, "A1 exact")
    raw = [{"role": "user", "content": "next task"},
           {"role": "assistant", "content": capsule}]
    import copy
    original = copy.deepcopy(raw)
    projected = k.BACKEND._stage_messages_for_profile(
        raw, k.STAGES["extended_initial"]
    )
    assert raw == original
    assert projected[1]["content"] == capsule
    assert receipt in projected[1]["content"]
    assert "result_sha256=" in str(projected)
    assert projected[1]["role"] == "assistant"


def test_receipt_projection_is_copy_on_write_and_stage_scoped():
    k = load_kernel()
    note = k._agentic_tool_history_note(current_turn_tools(1))
    old = {"role": "assistant", "content": "M" + note + chr(10) * 2 + "A1"}
    before = dict(old)
    stage1 = k.BACKEND._stage_messages_for_profile(
        [old], k.STAGES["extended_initial"]
    )
    assert note in stage1[0]["content"]
    assert stage1[0]["content"] == old["content"]
    assert old == before
    # Stage 2 still sees current frozen A1 byte-exact, not a rewritten answer.
    stage2 = k.BACKEND._stage_messages_for_profile(
        [old], k.STAGES["extended_reflection"]
    )
    assert stage2[0]["content"] == old["content"]


def test_receipt_scope_rejects_previous_turn_and_deduplicates_tool_results():
    k = load_kernel()
    old = tool_exchange(2)
    recent = tool_exchange(3)
    # Same IDs may occur in separate generations. Only the latest authentic
    # user boundary determines which transactions belong to this receipt.
    history = [
        {"role": "user", "content": "prior request"},
        *old,
        {"role": "assistant", "content": "Prior completed answer"},
        {"role": "user", "content": "current request"},
        *recent,
        dict(recent[-1]),
        {"role": "assistant", "content": "Current answer",
         "_jack_extended_candidate_response": True},
    ]
    receipt = k._agentic_tool_history_note(history)
    assert receipt.count("; result_sha256=") == 3
    assert "file-2.txt" in receipt
    assert receipt.count("id=call-2;") == 1


def test_receipt_scope_without_frozen_answer_is_empty():
    k = load_kernel()
    history = [
        {"role": "user", "content": "old request"}, *tool_exchange(1),
        {"role": "assistant", "content": "old answer",
         "_jack_extended_candidate_response": True},
        {"role": "user", "content": "new request"}, *tool_exchange(2),
    ]
    assert k._agentic_tool_history_note(history) == ""

def test_multi_turn_tool_protocol_keeps_exact_arguments_results_and_order():
    k = load_kernel()
    calls = tool_exchange(24)
    calls[0]["tool_calls"][0]["function"]["arguments"] = json.dumps({
        "path": "clock/index.html", "content": "<html>" + "t" * 10000 + "</html>"
    })
    calls[1]["content"] = "success:" + "Y" * 14000
    calls[3]["content"] = "failed: missing exact oldText"
    calls[3]["isError"] = True
    original = [
        {"role": "user", "content": "build clock"},
        *calls,
        {"role": "assistant", "content": "M\\n\\nA", "reasoning_content": "R1 to prune"},
        {"role": "user", "content": "continue the clock"},
    ]
    projected = k._compact_agentic_completed_capsules(original)
    assert projected is not None
    assert [m["role"] for m in projected[1:-2]] == [m["role"] for m in calls]
    for actual, expected in zip(projected[1:-2], calls):
        assert actual.get("tool_calls") == expected.get("tool_calls")
        assert actual.get("tool_call_id") == expected.get("tool_call_id")
        assert actual.get("content") == expected.get("content")
        assert actual.get("isError") == expected.get("isError")
    assert all("reasoning_content" not in m for m in projected)
    assert original[-2]["reasoning_content"] == "R1 to prune"


def test_stage2_extensions_are_removed_without_disabling_core_memory():
    k = load_kernel()
    source = SRC.read_text(encoding="utf-8")
    assert k.STAGES["extended_reflection"].allow_tools is False
    assert k.AGENTIC_36_STAGE2_PROMPT == k._AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION
    assert not hasattr(k, "AGENTIC_STAGE2_FINAL_PAPER_EXPERIMENT")
    assert not hasattr(k, "AGENTIC_DIFFERENTIAL_MEMORY_EXPERIMENT")
    assert "Verify your reasoning and verify anything else needed to fulfill the user request." not in k.AGENTIC_36_STAGE2_PROMPT
    assert "no Stage 2 extension" not in source
