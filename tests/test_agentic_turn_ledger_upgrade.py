"""Host-only Agentic turn ledger and derived profile contract."""
import importlib.util
import json
import re
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def kernel(monkeypatch, tmp_path, profile):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / "turns.sqlite3"))
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    name = "jack_ledger_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


def begin_frozen(k, history):
    turn_id = k._agentic_begin_turn(history, fresh=True)
    assert turn_id
    answer = k.append_extended_candidate_response(
        history, {"content": "A verified frozen answer."}
    )
    k._agentic_forensic_start_stage2(history)
    return turn_id, answer


def commit(k, history, turn_id, answer, memory):
    k._agentic_forensic_commit(history, answer, memory, "")
    return k._format_agentic_completed_response(memory, answer, turn_id=turn_id)


def test_journal_sequential_transactional_numbers_timestamps_and_failure(tmp_path):
    from jack_agentic_forensics import AgenticForensicJournal
    j = AgenticForensicJournal(tmp_path / "direct.sqlite3")
    ids = ["jack-turn-" + uuid.uuid4().hex for _ in range(3)]
    attempts = ["jack-attempt-" + uuid.uuid4().hex for _ in ids]
    for i in range(3):
        j.begin(ids[i], "a" * 64, attempts[i],
                conversation_key="same-verified-scope",
                initial_turn_number=1)
    ledgers = [j.ledger(key) for key in ids]
    assert [r["turn_number"] for r in ledgers] == [1, 2, 3]
    assert len({r["started_utc"] for r in ledgers}) >= 1
    assert all(re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z",
                            r["started_utc"]) for r in ledgers)
    j.begin(ids[1], "a" * 64, attempts[1],
            conversation_key="same-verified-scope", initial_turn_number=1)
    assert j.ledger(ids[1])["turn_number"] == 2
    j.fail(ids[2], attempts[2], "interrupted")
    assert j.ledger(ids[2])["status"] == "stage1_failed"
    assert j.ledger(ids[2])["completed_utc"] is not None
    assert j.ledger(ids[0])["completed_utc"] is None


def test_journal_evidence_pointer_is_only_attached_to_committed_turn(tmp_path):
    from jack_agentic_forensics import AgenticForensicJournal, ForensicConflict
    j = AgenticForensicJournal(tmp_path / "evidence.sqlite3")
    turn = "jack-turn-" + uuid.uuid4().hex
    a1 = "jack-attempt-" + uuid.uuid4().hex
    a2 = "jack-attempt-" + uuid.uuid4().hex
    j.begin(turn, "1" * 64, a1)
    with pytest.raises(ForensicConflict):
        j.attach_evidence(turn, str(tmp_path / "missing.json"), "a" * 64)
    fp = j.freeze(turn, a1, "answer")
    j.stage2(turn, a1, a2, fp)
    j.commit(turn, a2, "answer", "memory", "")
    archive = tmp_path / "proof.json"
    archive.write_text('{"record":"example"}', encoding="utf-8")
    j.attach_evidence(turn, str(archive), "b" * 64)
    assert j.ledger(turn)["evidence_ref"] == str(archive)
    assert j.ledger(turn)["evidence_sha256"] == "b" * 64
    j.attach_evidence(turn, str(archive), "b" * 64)
    with pytest.raises(ForensicConflict):
        j.attach_evidence(turn, str(tmp_path / "other.json"), "c" * 64)


def test_flash_turn_number_survives_verified_compaction_and_has_zero_inference(
    monkeypatch, tmp_path,
):
    k = kernel(monkeypatch, tmp_path, "flash")
    first = [{"role": "user", "content": "first"}]
    id1, answer1 = begin_frozen(k, first)
    assert k._agentic_flash_stage2_result(first)["choices"][0]["message"]["content"] == "Turn 1"
    wire1 = commit(k, first, id1, answer1, "Turn 1")
    # Previous visible pair is authentic and journal-verified; no need to
    # carry every earlier conversation turn to preserve the ordinal.
    next_history = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": wire1},
        {"role": "user", "content": "second"},
    ]
    id2, answer2 = begin_frozen(k, next_history)
    assert k._agentic_flash_stage2_result(next_history)["choices"][0]["message"]["content"] == "Turn 2"
    wire2 = commit(k, next_history, id2, answer2, "Turn 2")
    # Compact first turn away. The most recent authenticated predecessor
    # continues the same ledger even though only one older turn remains.
    compacted = [
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": wire2},
        {"role": "user", "content": "third"},
    ]
    id3, _ = begin_frozen(k, compacted)
    assert k._agentic_flash_stage2_result(compacted)["choices"][0]["message"]["content"] == "Turn 3"
    assert k._agentic_forensic_journal().ledger(id3)["turn_number"] == 3
    assert k._agentic_forensic_journal().ledger(id3)["scope_origin"] == "verified_predecessor"


def test_profiles_thorough_baseline_balanced_single_requested_prompt_difference(
    monkeypatch, tmp_path,
):
    t = kernel(monkeypatch, tmp_path / "t", "thorough")
    b = kernel(monkeypatch, tmp_path / "b", "balanced")
    e = kernel(monkeypatch, tmp_path / "e", "exhaustive")
    f = kernel(monkeypatch, tmp_path / "f", "flash")
    assert t.STAGES["extended_initial"].thinking
    assert t.STAGES["extended_reflection"].thinking
    assert b.STAGES["extended_initial"].thinking
    assert not b.STAGES["extended_reflection"].thinking
    assert b.AGENTIC_STAGE1_PROMPT == t.AGENTIC_STAGE1_PROMPT.removeprefix(
        "Reasoning effort is set to xhigh. "
    )
    assert "Reasoning effort is set to xhigh." in t.AGENTIC_STAGE1_PROMPT
    assert t.AGENTIC_36_STAGE2_PROMPT == b.AGENTIC_36_STAGE2_PROMPT
    assert t.AGENTIC_36_STAGE2_PROMPT == e.AGENTIC_36_STAGE2_PROMPT
    assert not t.CFG.agentic_final_review
    assert not b.CFG.agentic_final_review
    assert e.CFG.agentic_final_review
    assert not f.STAGES["extended_initial"].thinking


def test_exhaustive_unifies_initial_and_extension_reasoning_without_instruction(
    monkeypatch, tmp_path,
):
    k = kernel(monkeypatch, tmp_path, "exhaustive")
    instruction = k.AGENTIC_FINAL_REVIEW_TRIGGER
    h = [
        {"role": "user", "content": "Produce a verified result"},
        {"role": "assistant", "content": "before", "reasoning_content": "R1 initial observation",
         "_jack_internal_agentic_final_review_draft": True},
        {"role": "user", "content": instruction,
         "_jack_internal_agentic_final_review_trigger": True},
        {"role": "assistant", "content": "final", "reasoning_content": "R1 extension corrected prior error",
         "_jack_extended_candidate_response": True},
    ]
    events = k._agentic_stage2_chronological_source(h)
    assert [v["type"] for v in events] == ["reasoning_segment", "reasoning_segment"]
    assert [v["phase"] for v in events] == ["stage1", "stage1"]
    assert [v["content"] for v in events] == [
        "R1 initial observation", "R1 extension corrected prior error"
    ]
    assert instruction not in json.dumps(events, ensure_ascii=False)


def test_host_ledger_not_inserted_into_thorough_stage2_source(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path, "thorough")
    h = [
        {"role": "user", "content": "request"},
        {"role": "assistant", "content": "frozen answer",
         "reasoning_content": "reasoning stays intact",
         "_jack_extended_candidate_response": True},
    ]
    snapshot = json.dumps(h, sort_keys=True)
    source = k._agentic_stage2_chronological_source(h)
    assert json.dumps(h, sort_keys=True) == snapshot
    assert source == [{
        "type": "reasoning_segment", "phase": "initial",
        "content": "reasoning stays intact"
    }]
    assert not any("turn_number" in v or "started_utc" in v for v in source)
