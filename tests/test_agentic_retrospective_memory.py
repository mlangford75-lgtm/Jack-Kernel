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
    token = k._AGENTIC_SESSION_ID.set("test-runtime:test-lane:session-0000000000000001")
    try:
        rendered = k._format_agentic_completed_response(memory, answer)
    finally:
        k._AGENTIC_SESSION_ID.reset(token)
    assert rendered == answer
    assert "<Agentic Memory>" not in rendered
    assert "<Model Response>" not in rendered
    # Legacy stateless callers preserve their in-band semantic memory.
    legacy = k._format_agentic_completed_response(memory, answer)
    assert k._split_prior_jack_output(legacy) == (memory, answer)


def test_agentic_gc_retires_native_reasoning_and_tool_protocol():
    k = load_kernel()
    answer = "A1"
    token = k._AGENTIC_SESSION_ID.set("test-runtime:test-lane:session-0000000000000001")
    try:
        assert k._format_agentic_completed_response("Retained lesson", answer) == answer
    finally:
        k._AGENTIC_SESSION_ID.reset(token)
    messages = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": answer, "reasoning_content": "long raw reasoning"},
        *tool_exchange(1),
        {"role": "user", "content": "second question"},
    ]
    original = json.dumps(messages, sort_keys=True)
    projected = k._compact_agentic_completed_capsules(messages)
    assert projected is not None
    assert json.dumps(messages, sort_keys=True) == original
    assert [row["role"] for row in projected] == ["user", "assistant", "user"]
    assert projected[1]["content"] == answer
    assert not any("reasoning_content" in row for row in projected)
    assert projected[-1]["content"] == "second question"


def test_tag_free_replay_memory_and_isolation():
    # Simulate a bound Pi session for volatile replay testing.

    k = load_kernel()
    from types import SimpleNamespace
    kernel = k.JackQwenKernel(SimpleNamespace(), k.CFG)
    k._AGENTIC_SESSION_ID.set("test-runtime:test-lane:session-0000000000000001")
    system = "Stable caller instruction"
    previous = [
        {"role": "user", "content": "Initial task"},
        {"role": "assistant", "content": "Exactly A1  "},
    ]
    kernel._agentic_store_completed_memory(previous, system, "Important rejected approach", "")
    next_history = k._compact_agentic_completed_capsules(
        previous + [{"role": "user", "content": "Continue"}]
    )
    kernel._agentic_restore_completed_memory(next_history, system)
    assert next_history[1]["content"] == "Exactly A1  "
    assert next_history[1]["reasoning_content"] == "Important rejected approach"
    assert not any("Agentic Memory" in str(row["content"]) for row in next_history)
    # Model-facing Stage 1 sees recovered memory without answer scaffolding.
    # The model input projection must preserve the injected historical reasoning.
    stage = k.STAGES["extended_initial"]
    instance = object.__new__(k.OpenAICompatibleBackend)
    model_input = instance._stage_messages_for_profile(next_history, stage)
    assert model_input[1]["reasoning_content"] == "Important rejected approach"
    assert model_input[1]["content"] == "Exactly A1  "
    other_system = [dict(row) for row in next_history]
    for row in other_system:
        row.pop("reasoning_content", None)
        row.pop("_jack_agentic_retained_memory", None)
    kernel._agentic_restore_completed_memory(other_system, "Different caller instruction")
    assert "reasoning_content" not in other_system[1]
    different_session = [dict(row) for row in next_history]
    for row in different_session:
        row.pop("reasoning_content", None)
        row.pop("_jack_agentic_retained_memory", None)
    token = k._AGENTIC_SESSION_ID.set("test-runtime:test-lane:session-0000000000000002")
    try:
        kernel._agentic_restore_completed_memory(different_session, system)
    finally:
        k._AGENTIC_SESSION_ID.reset(token)
    assert "reasoning_content" not in different_session[1]


def test_tag_free_replay_collision_fails_closed():
    # Simulate a bound Pi session for volatile replay testing.

    k = load_kernel()
    from types import SimpleNamespace
    kernel = k.JackQwenKernel(SimpleNamespace(), k.CFG)
    k._AGENTIC_SESSION_ID.set("test-runtime:test-lane:session-0000000000000001")
    history = [
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": "same answer"},
    ]
    kernel._agentic_store_completed_memory(history, "", "one memory", "")
    kernel._agentic_store_completed_memory(history, "", "different memory", "")
    replay = history + [{"role": "user", "content": "next"}]
    kernel._agentic_restore_completed_memory(replay, "")
    assert "reasoning_content" not in replay[1]



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


def test_replay_receipt_budget_preserves_semantic_memory_and_a1():
    # Simulate a bound Pi session for volatile replay testing.

    k = load_kernel()
    from types import SimpleNamespace
    kernel = k.JackQwenKernel(SimpleNamespace(), k.CFG)
    k._AGENTIC_SESSION_ID.set("test-runtime:test-lane:session-0000000000000001")
    turns = []
    for i in range(10):
        turns.append({"role": "user", "content": f"request-{i}"})
        turns.append({"role": "assistant", "content": f"answer-{i}"})
        kernel._agentic_store_completed_memory(
            turns, "", f"lesson-{i}", k._agentic_tool_history_note(tool_exchange(6))
        )
        # Previous replay must be hydrated when preparing the next completed turn.
        if i < 9:
            next_history = [dict(item) for item in turns] + [{"role": "user", "content": "next"}]
            kernel._agentic_restore_completed_memory(next_history, "")
            for original, hydrated in zip(turns, next_history):
                if "_jack_agentic_retained_memory" in hydrated:
                    original["_jack_agentic_retained_memory"] = hydrated["_jack_agentic_retained_memory"]
    replay = k._compact_agentic_completed_capsules(turns + [{"role": "user", "content": "now"}])
    kernel._agentic_restore_completed_memory(replay, "")
    assistants = [row for row in replay if row["role"] == "assistant"]
    assert len(assistants) == 10
    assert all(assistants[i]["content"] == f"answer-{i}" for i in range(10))
    assert all(f"lesson-{i}" in assistants[i].get("reasoning_content", "") for i in range(10))
    assert sum(x.get("reasoning_content", "").count("result_sha256=") for x in assistants) <= 12
