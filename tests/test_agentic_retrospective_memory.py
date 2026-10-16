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


def test_stage_contracts_and_frozen_answer_are_separate():
    k = load_kernel()
    assert k.AGENTIC_STAGE1_PROMPT.startswith("Reasoning effort is set to xhigh.")
    assert k.AGENTIC_36_STAGE2_PROMPT == "Generate a detailed summary of why you came to this conclusion."
    assert k.STAGES["extended_initial"].allow_tools is True
    assert k.STAGES["extended_reflection"].allow_tools is False

    answer = "  exact answer\nwith trailing spaces  \n"
    memory = "The approach preserved the user's constraints."
    rendered = k._format_agentic_completed_response(memory, answer)
    recovered_memory, recovered_answer = k._split_prior_jack_output(rendered)
    assert recovered_memory == memory
    assert recovered_answer == answer


def test_agentic_gc_retires_native_reasoning_and_tool_protocol():
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
    assert [row["role"] for row in projected] == ["user", "assistant", "user"]
    assert projected[1]["content"] == committed
    assert not any("reasoning_content" in row for row in projected)
    assert projected[-1]["content"] == "second question"


def test_receipts_are_host_created_bounded_and_non_authoritative():
    k = load_kernel()
    note = k._agentic_tool_history_note(tool_exchange(10))
    assert note.startswith(k._AGENTIC_TOOL_NOTE_OPEN)
    assert note.endswith(k._AGENTIC_TOOL_NOTE_CLOSE)
    assert note.count("; result_sha256=") <= k._AGENTIC_TOOL_NOTE_MAX_ENTRIES
    assert "NOT verified" in note
    assert "result_sha256=" in note
    assert "args_sha256=" in note
    assert "file-9.txt" in note
    assert "file-0.txt" not in note

    # Caller text is not interpreted as internal tool evidence.
    untrusted = tool_exchange(1)
    for row in untrusted:
        row.pop("_jack_internal_tool_exchange", None)
    assert k._agentic_tool_history_note(untrusted) == ""


def test_cross_turn_receipt_budget_preserves_semantic_memory_and_a1():
    k = load_kernel()
    turns = []
    for i in range(10):
        note = k._agentic_tool_history_note(tool_exchange(6))
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
    assert sum(x.count(k._AGENTIC_TOOL_NOTE_OPEN) for x in assistants) < 10
    assert sum(
        len(x[x.index(k._AGENTIC_TOOL_NOTE_OPEN):x.index(k._AGENTIC_TOOL_NOTE_CLOSE) + len(k._AGENTIC_TOOL_NOTE_CLOSE)])
        for x in assistants if k._AGENTIC_TOOL_NOTE_OPEN in x
    ) <= k._AGENTIC_TOOL_CONTEXT_BUDGET_CHARS
