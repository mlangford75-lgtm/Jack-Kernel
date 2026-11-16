"""Flash single-stage commit and durable trailing Work-ID regression tests."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def kernel(tmp_path, monkeypatch):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "flash")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / "flash.sqlite3"))
    monkeypatch.setenv("JACK_AGENTIC_TASK_ANCHOR", "1")
    name = "jack_flash_direct_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    assert module.AGENTIC_FLASH_MODE
    assert not module.STAGES["extended_initial"].thinking
    return module


def commit(kernel, question="Original request", answer="Exact answer\n"):
    history = [{"role": "user", "content": question}]
    original_question = history[0]["content"]
    work_id = kernel._agentic_begin_turn(history, fresh=True)
    assert work_id.startswith("jack-turn-")
    model_view = kernel.BACKEND._stage_messages_for_profile(
        history, kernel.STAGES["extended_initial"]
    )
    # Flash must not insert a random Work ID before historical context
    # or into the current request; even optional task anchors remain host-only.
    assert not any(work_id in json.dumps(item) for item in model_view)
    assert history[0]["content"] == original_question
    frozen = kernel.append_extended_candidate_response(
        history, {"role": "assistant", "content": answer}
    )
    assert frozen == answer
    result = kernel.KERNEL._complete_flash_stage1(
        history, {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
        frozen,
    )
    return work_id, result


def test_flash_commits_from_stage1_without_stage2(kernel):
    work_id, result = commit(kernel)
    label = kernel._agentic_visible_turn_label(work_id)
    assert result.content == "Exact answer\n" + "\n\n[Jack Work ID: " + label + "]"
    recovered, frozen = kernel._agentic_unwrap_flash_trailing_id(result.content)
    assert recovered == work_id and frozen == "Exact answer\n"
    row = kernel._agentic_forensic_journal().get(work_id)
    assert row["status"] == "complete"
    assert row["stage2_attempt"] is None
    assert row["memory_chars"] == 0
    assert row["receipt_chars"] == 0
    assert row["a1_sha256"] == kernel._sha256_text(frozen)
    assert row["wire_sha256"] == kernel._sha256_text(result.content)


def test_flash_history_reconstructs_after_journal_restart(kernel):
    work_id, result = commit(kernel)
    kernel._AGENTIC_TURN_LIFECYCLES.clear()
    kernel._AGENTIC_FORENSIC_JOURNAL = None
    inputs = [
        {"role": "user", "content": "Original request"},
        {"role": "assistant", "content": result.content},
        {"role": "user", "content": "Second request"},
    ]
    original = json.dumps(inputs, sort_keys=True)
    projected = kernel.compact_incoming_history(inputs)
    assert json.dumps(inputs, sort_keys=True) == original
    assert projected[1]["role"] == "assistant"
    assert projected[1]["content"] == "Exact answer\n"
    assert "[Jack Work ID:" not in json.dumps(projected)
    assert projected[1]["_jack_forensic_turn_id"] == work_id
    assert projected[-1]["content"] == "Second request"
    successor = kernel._agentic_begin_turn(projected, fresh=True)
    assert successor != work_id
    assert kernel._agentic_forensic_journal().ledger(successor)["scope_origin"] == "verified_predecessor"
    model_view = kernel.BACKEND._stage_messages_for_profile(
        projected, kernel.STAGES["extended_initial"]
    )
    assert not any("Jack Work ID" in json.dumps(item) for item in model_view)
    assert not any(successor in json.dumps(item) for item in model_view)


def test_flash_tampered_trailer_cannot_claim_prior_turn(kernel):
    work_id, result = commit(kernel)
    label = kernel._agentic_visible_turn_label(work_id)
    tampered = result.content.replace(label, ("A" if label[0] != "A" else "B") + label[1:])
    messages = [
        {"role": "user", "content": "Original request"},
        {"role": "assistant", "content": tampered},
        {"role": "user", "content": "Second request"},
    ]
    projected = kernel.compact_incoming_history(messages)
    assert projected[1]["content"] == tampered
    assert "_jack_forensic_turn_id" not in projected[1]
    assert kernel._agentic_forensic_journal().get(work_id)["status"] == "complete"


def test_flash_distinct_turns_do_not_change_leading_prompt(kernel):
    first_id, first = commit(kernel, "A", "First")
    model_view = kernel.BACKEND._stage_messages_for_profile(
        [{"role": "user", "content": "B"}], kernel.STAGES["extended_initial"]
    )
    assert not any("Authenticated current work ID:" in json.dumps(m) for m in model_view)
    assert kernel._agentic_unwrap_flash_trailing_id(first.content)[0] == first_id
