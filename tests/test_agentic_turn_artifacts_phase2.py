"""Phase 2: host-owned separate Agentic artifacts, shadow-only, no retrieval."""
from __future__ import annotations
import asyncio
import importlib.util
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]

def load():
    os.environ["JACK_REASONING_LEVEL"] = "agentic"
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "off"
    os.environ["JACK_BACKEND_MODEL"] = "test-model"
    os.environ["JACK_BACKEND_PROFILE"] = "lmstudio"
    name = "jack_agentic_phase2_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_shadow_writes_independent_artifacts_and_preserves_exact_bytes():
    k = load()
    hint = k.AgenticTurnTransportHint("session-a", "entry-1", 1)
    token = k._AGENTIC_TURN_HINT.set(hint)
    try:
        k._agentic_shadow_record_commit("  answer\n", "memory\n  ")
    finally:
        k._AGENTIC_TURN_HINT.reset(token)
    record = k._AGENTIC_SHADOW_LEDGER[("session-a", "entry-1", 1)]
    assert record.status == "complete"
    assert record.response.content == "  answer\n"
    assert record.memory.content == "memory\n  "
    assert record.response.sha256 == k._sha256_text("  answer\n")
    assert record.memory.sha256 == k._sha256_text("memory\n  ")
    assert record.response is not record.memory


def test_shadow_is_client_independent_and_never_holds_native_reasoning():
    k = load()
    k._agentic_shadow_record_commit("A", "M")
    assert len(k._AGENTIC_SHADOW_LEDGER) == 1
    unhinted = next(iter(k._AGENTIC_SHADOW_LEDGER.values()))
    assert unhinted.turn_id.startswith("jack-turn-")
    hint = k.AgenticTurnTransportHint("s", "u", 1)
    token = k._AGENTIC_TURN_HINT.set(hint)
    try:
        k._agentic_shadow_record_commit("A", "M")
    finally:
        k._AGENTIC_TURN_HINT.reset(token)
    assert len(k._AGENTIC_SHADOW_LEDGER) == 2
    record = k._AGENTIC_SHADOW_LEDGER[("s", "u", 1)]
    for result in (record, unhinted):
        assert not hasattr(result, "reasoning")
        assert not hasattr(result.response, "reasoning")
        assert not hasattr(result.memory, "reasoning")


def test_tool_receipt_is_not_part_of_agentic_memory_artifact():
    k = load()
    hint = k.AgenticTurnTransportHint("s", "u", 1)
    token = k._AGENTIC_TURN_HINT.set(hint)
    try:
        k._agentic_shadow_record_commit("A", "M", "host-only receipt")
    finally:
        k._AGENTIC_TURN_HINT.reset(token)
    record = next(iter(k._AGENTIC_SHADOW_LEDGER.values()))
    assert record.memory.content == "M"
    assert record.tool_receipt == "host-only receipt"


def test_same_idempotent_record_and_collision_does_not_replace_it():
    k = load()
    hint = k.AgenticTurnTransportHint("s", "u", 1)
    token = k._AGENTIC_TURN_HINT.set(hint)
    try:
        k._agentic_shadow_record_commit("A", "M")
        k._agentic_shadow_record_commit("A", "M")
        k._agentic_shadow_record_commit("different", "different")
    finally:
        k._AGENTIC_TURN_HINT.reset(token)
    assert len(k._AGENTIC_SHADOW_LEDGER) == 1
    record = next(iter(k._AGENTIC_SHADOW_LEDGER.values()))
    assert record.response.content == "A"
    assert record.memory.content == "M"


def test_degraded_stage2_keeps_frozen_a1_and_marks_memory_missing():
    k = load()
    hint = k.AgenticTurnTransportHint("s", "u", 1)
    token = k._AGENTIC_TURN_HINT.set(hint)
    try:
        hist = [{"role": "user", "content": "Question"}]
        result = k.KERNEL._agentic_degraded_result(hist, {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}, "exact A1", "failed")
        assert not hist
    finally:
        k._AGENTIC_TURN_HINT.reset(token)
    record = next(iter(k._AGENTIC_SHADOW_LEDGER.values()))
    assert result.content == "exact A1"
    assert record.response.content == "exact A1"
    assert record.memory is None
    assert record.status == "memory_failed"


def test_nonstream_complete_commit_records_same_artifacts_without_reformatting():
    k = load()
    hint = k.AgenticTurnTransportHint("s", "u", 1)
    token = k._AGENTIC_TURN_HINT.set(hint)
    try:
        hist = [{"role": "user", "content": "Question"}]
        result = asyncio.run(k.KERNEL._complete_commit(hist, "", {}, " A1 ", "M1"))
    finally:
        k._AGENTIC_TURN_HINT.reset(token)
    assert not hist
    assert result.frozen_answer == " A1 "
    assert result.frozen_xml == "M1"
    record = next(iter(k._AGENTIC_SHADOW_LEDGER.values()))
    assert record.response.content == result.frozen_answer
    assert record.memory.content == result.frozen_xml


def test_missing_memory_can_be_completed_but_frozen_answer_cannot_change():
    k = load()
    token = k._AGENTIC_TURN_HINT.set(k.AgenticTurnTransportHint("s", "u", 1))
    try:
        k._agentic_shadow_record_commit("A", None)
        k._agentic_shadow_record_commit("B", "wrong")
        assert next(iter(k._AGENTIC_SHADOW_LEDGER.values())).status == "memory_failed"
        k._agentic_shadow_record_commit("A", "recovered M")
    finally:
        k._AGENTIC_TURN_HINT.reset(token)
    record = next(iter(k._AGENTIC_SHADOW_LEDGER.values()))
    assert record.status == "complete"
    assert record.response.content == "A"
    assert record.memory.content == "recovered M"


def test_shadow_is_bounded_and_per_session_keyed():
    k = load()
    for i in range(k._AGENTIC_SHADOW_LIMIT + 2):
        token = k._AGENTIC_TURN_HINT.set(k.AgenticTurnTransportHint("s", f"user-{i}", i+1))
        try:
            k._agentic_shadow_record_commit(f"A{i}", f"M{i}")
        finally:
            k._AGENTIC_TURN_HINT.reset(token)
    assert len(k._AGENTIC_SHADOW_LEDGER) == k._AGENTIC_SHADOW_LIMIT
    assert ("s", "user-0", 1) not in k._AGENTIC_SHADOW_LEDGER
    assert ("s", f"user-{k._AGENTIC_SHADOW_LIMIT+1}", k._AGENTIC_SHADOW_LIMIT+2) in k._AGENTIC_SHADOW_LEDGER


def test_phase2_does_not_change_cognitive_prompts():
    k = load()
    assert k.AGENTIC_STAGE1_PROMPT == (
        "Reasoning effort is set to xhigh. Please think carefully through the task, "
        "validate key assumptions, consider plausible alternatives, and prioritize "
        "correctness, consistency, and clarity in the final answer."
    )
    assert k.AGENTIC_36_STAGE2_PROMPT == "Generate a detailed summary of why you came to this conclusion."
