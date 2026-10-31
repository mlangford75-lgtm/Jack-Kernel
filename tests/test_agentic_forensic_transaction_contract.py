"""Agentic forensic transaction ownership, recovery and cache-prefix regression."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_kernel(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT", "1")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / "forensic.sqlite"))
    name = "jack_forensic_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


def test_transaction_commit_and_restart_recovery(monkeypatch, tmp_path):
    k = load_kernel(monkeypatch, tmp_path)
    original = {"role": "user", "content": "Create a simple clock"}
    history = [dict(original)]
    turn = k._agentic_begin_turn(history, fresh=True)
    record = k._AGENTIC_TURN_LIFECYCLES[turn]
    stage1_attempt = record.stage1_attempt_id
    assert stage1_attempt.startswith("jack-attempt-")
    assert k._agentic_forensic_journal().get(turn)["status"] == "stage1_active"

    original_request = json.dumps(original, sort_keys=True)
    answer = k.append_extended_candidate_response(
        history, {"content": "Exactly frozen clock A1", "reasoning_content": "current R1"}
    )
    assert record.frozen_a1_sha256 == k._sha256_text(answer)
    assert k._agentic_forensic_journal().get(turn)["status"] == "stage1_frozen"

    k._agentic_forensic_start_stage2(history)
    assert record.stage2_attempt_id.startswith("jack-attempt-")
    assert record.stage2_attempt_id != record.stage1_attempt_id
    suffix = k._stage_continuation(k.STAGES["extended_reflection"], history)
    assert f"turn={turn}" in suffix
    assert "frozen_A1=" in suffix
    assert original_request not in suffix
    assert answer not in suffix

    # Key cache invariant: the stage-1 message prefix is untouched by stage 2.
    p1 = k.BACKEND._stage_messages_for_profile(
        history[:-1], k.STAGES["extended_initial"]
    )
    p2 = k.BACKEND._stage_messages_for_profile(
        history, k.STAGES["extended_reflection"]
    )
    assert p2[:len(p1)] == p1
    assert p2[-1]["content"] == answer
    assert p2[-1]["reasoning_content"] == "current R1"

    committed = asyncio.run(k.KERNEL._complete_commit(
        history, "", {}, answer, "Retrospective for THIS clock",
    ))
    record_on_disk = k._agentic_forensic_journal().get(turn)
    assert record_on_disk["status"] == "complete"
    assert record_on_disk["a1_sha256"] == k._sha256_text(answer)
    assert record_on_disk["memory_sha256"] == k._sha256_text("Retrospective for THIS clock")
    assert record_on_disk["stage1_attempt"] == stage1_attempt
    assert record_on_disk["stage2_attempt"] == record.stage2_attempt_id
    assert not history

    visible = k._format_agentic_completed_response(
        committed.frozen_xml, committed.frozen_answer
    )
    caller = [dict(original), {"role": "assistant", "content": visible},
              {"role": "user", "content": "What happened?"}]

    # Clear process-local information, emulating fresh Jack after a restart.
    k._AGENTIC_SHADOW_LEDGER.clear()
    k._AGENTIC_TURN_LIFECYCLES.clear()
    k._AGENTIC_FORENSIC_JOURNAL = None
    projected = k.compact_incoming_history(caller)
    assert json.loads(json.dumps(caller)) == caller
    assert [item["role"] for item in projected] == [
        "user", "assistant", "assistant", "user"
    ]
    assert projected[0]["content"] == original["content"]
    assert projected[1]["content"].endswith("Retrospective for THIS clock")
    assert projected[2]["content"] == answer
    assert projected[1]["_jack_forensic_turn_id"] == turn
    assert projected[2]["_jack_forensic_turn_id"] == turn
    model = k.BACKEND._stage_messages_for_profile(
        projected, k.STAGES["extended_initial"]
    )
    assert f"[JACK LINK turn={turn} | artifact=M]" in model[1]["content"]
    assert f"[JACK LINK turn={turn} | artifact=A1]" in model[2]["content"]
    assert model[3]["content"] == "What happened?"
    assert not any("_jack_forensic_turn_id" in m for m in model)


def test_incomplete_attempt_never_freezes_or_commits(monkeypatch, tmp_path):
    k = load_kernel(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Generate until timeout"}]
    turn = k._agentic_begin_turn(h, fresh=True)
    rec = k._AGENTIC_TURN_LIFECYCLES[turn]
    old_attempt = rec.stage1_attempt_id
    with pytest.raises(k.HTTPException):
        k.KERNEL._agentic_require_completed_stage(
            {"choices": [{"finish_reason": "length"}]}, "Agentic Stage 1"
        )
    k._agentic_mark_stage1_failure("length")
    old = k._agentic_forensic_journal().get(turn)
    assert old["status"] == "stage1_failed"
    assert old["a1_sha256"] is None
    assert old["stage2_attempt"] is None
    assert old["memory_sha256"] is None
    with pytest.raises(k.ForensicConflict):
        k._agentic_forensic_journal().freeze(turn, old_attempt, "stale output")
    new_attempt = k._new_forensic_attempt_id()
    k._agentic_forensic_journal().retry_stage1(
        turn, rec.user_request.sha256, new_attempt
    )
    assert k._agentic_forensic_journal().get(turn)["stage1_attempt"] == new_attempt
    with pytest.raises(k.ForensicConflict):
        k._agentic_forensic_journal().freeze(turn, old_attempt, "late stale output")


def test_unfinished_stage2_and_wrong_attempt_rejected(monkeypatch, tmp_path):
    k = load_kernel(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Do work"}]
    turn = k._agentic_begin_turn(h, fresh=True)
    a = k.append_extended_candidate_response(h, {"content": "Frozen work"})
    k._agentic_forensic_start_stage2(h)
    rec = k._AGENTIC_TURN_LIFECYCLES[turn]
    with pytest.raises(k.ForensicConflict):
        k._agentic_forensic_journal().commit(
            turn, k._new_forensic_attempt_id(), a, "wrong attempt", ""
        )
    k._agentic_forensic_fail_memory(h, "model interrupted")
    state = k._agentic_forensic_journal().get(turn)
    assert state["status"] == "memory_failed"
    assert state["a1_sha256"] == k._sha256_text(a)
    assert state["memory_sha256"] is None
    retry = k._new_forensic_attempt_id()
    k._agentic_forensic_journal().stage2(
        turn, rec.stage1_attempt_id, retry, rec.frozen_a1_sha256
    )
    with pytest.raises(k.ForensicConflict):
        k._agentic_forensic_journal().commit(
            turn, rec.stage2_attempt_id, a, "late stale memory", ""
        )
    k._agentic_forensic_journal().commit(turn, retry, a, "valid retry", "")
    assert k._agentic_forensic_journal().get(turn)["status"] == "complete"


def test_journal_rejects_ambiguous_identical_requests(monkeypatch, tmp_path):
    k = load_kernel(monkeypatch, tmp_path)
    original = {"role": "user", "content": "same"}
    seen = []
    for _ in range(2):
        h = [dict(original)]
        turn = k._agentic_begin_turn(h, fresh=True)
        answer = k.append_extended_candidate_response(h, {"content": "same A"})
        k._agentic_forensic_start_stage2(h)
        completed = asyncio.run(k.KERNEL._complete_commit(h, "", {}, answer, "same M"))
        seen.append((turn, k._format_agentic_completed_response(
            completed.frozen_xml, completed.frozen_answer
        )))
    assert seen[0][0] != seen[1][0]
    assert seen[0][1] == seen[1][1]
    lookup = k._agentic_forensic_journal().match_visible(
        k._AGENTIC_SHADOW_LEDGER[next(iter(k._AGENTIC_SHADOW_LEDGER))].user_request.sha256,
        k._sha256_text(seen[0][1])
    )
    assert lookup is None


def test_metadata_does_not_modify_frozen_prompts_or_context_pruning(monkeypatch, tmp_path):
    k = load_kernel(monkeypatch, tmp_path)
    assert k.AGENTIC_STAGE1_PROMPT == (
        "Reasoning effort is set to xhigh. Please think carefully through the task, "
        "validate key assumptions, consider plausible alternatives, and prioritize "
        "correctness, consistency, and clarity in the final answer."
    )
    assert k.AGENTIC_36_STAGE2_PROMPT == (
        "Generate a detailed summary of why you came to this conclusion."
    )
    assert k.AGENTIC_CACHE_APPEND_EXPERIMENT
    assert k.STAGES["extended_reflection"].allow_tools is False
    assert k._STAGE_CONTINUATIONS["Agentic native pass 2"].startswith(
        "[JACK RUNTIME STAGE CONTINUATION"
    )
