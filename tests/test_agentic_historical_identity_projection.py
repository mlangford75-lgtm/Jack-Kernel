"""Historical Jack IDs are bookkeeping, not Stage-1 answer-format examples.

Model-facing projection only: never edit canonical history, current work,
user requests, tool results, or isolated Stage-2 input.
"""
import copy
import importlib.util
import sys
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PAST_WORK = "jack-turn-" + "a" * 32
PAST_ATTEMPT = "jack-attempt-" + "b" * 32


def load(monkeypatch, tmp_path, profile="thorough"):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_historical_ids_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


@pytest.mark.parametrize("profile", ["flash", "balanced", "thorough", "exhaustive"])
def test_stage1_hides_only_historical_id_lines_and_preserves_everything_else(monkeypatch, tmp_path, profile):
    k = load(monkeypatch, tmp_path, profile)
    original_memory = (
        "Task: Extend the ledger.\n\n"
        "Work ID: " + PAST_WORK + "\n"
        "Memory Attempt ID: " + PAST_ATTEMPT + "\n"
        "Consequential Working Knowledge:\n"
        "- Discount: 10%; verified total: 47.20.\n"
        "[Jack Tool History - Host-Recorded Receipt]\n"
        "- id=tool-123; outcome=RESULT_RETURNED\n"
        "[/Jack Tool History - Host-Recorded Receipt]\n"
    )
    original = [
        {"role": "user", "content": "First request"},
        {"role": "assistant", "content": original_memory},
        {"role": "assistant", "content": "Original final answer: 47.20"},
        {"role": "tool", "name": "read", "content": "Important tool result: " + PAST_WORK},
        {"role": "user", "content": "NEXT, and preserve " + PAST_WORK},
    ]
    before = copy.deepcopy(original)
    prepared = k.OpenAICompatibleBackend(k.CFG)._stage_messages_for_profile(
        original, k.STAGES["extended_initial"]
    )
    assert original == before
    assert prepared[0] == original[0]
    assert prepared[1]["content"] == (
        "Task: Extend the ledger.\n\n"
        "Consequential Working Knowledge:\n"
        "- Discount: 10%; verified total: 47.20.\n"
        "[Jack Tool History - Host-Recorded Receipt]\n"
        "- id=tool-123; outcome=RESULT_RETURNED\n"
        "[/Jack Tool History - Host-Recorded Receipt]\n"
    )
    assert prepared[2] == original[2]
    assert prepared[3] == original[3]
    assert prepared[4] == original[4]


def test_projection_is_stage_scoped_and_does_not_remove_ids_from_source(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    history = [
        {"role": "user", "content": "Old request"},
        {"role": "assistant", "content": "Work ID: " + PAST_WORK + "\nVerified output."},
        {"role": "user", "content": "Current request"},
        {"role": "assistant", "content": "Current answer\nWork ID: " + PAST_WORK,
         "reasoning_content": "Current reasoning",
         "_jack_extended_candidate_response": True},
    ]
    before = copy.deepcopy(history)
    answer = k.OpenAICompatibleBackend(k.CFG)
    s1 = answer._stage_messages_for_profile(history, k.STAGES["extended_initial"])
    assert "Work ID:" not in s1[1]["content"]
    assert s1[-1]["content"] == history[-1]["content"]
    s2 = k._agentic_stage2_test_history(history, k.STAGES["extended_reflection"])
    assert s2[-1]["content"] == history[-1]["content"]
    assert s2[0]["content"] == "Current request"
    assert history == before


def test_unrelated_ids_and_inline_reference_text_survive(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    value = (
        "Project ID: project-123\n"
        "Work ID: human-ticket-44\n"
        "The tool printed Work ID: " + PAST_WORK + " in a sentence.\n"
        "- Work ID: " + PAST_WORK + "\n"
        "* Memory Attempt ID: " + PAST_ATTEMPT + "\n"
        "Completed successfully."
    )
    projected = k._agentic_historical_stage1_text(value)
    assert "Project ID: project-123" in projected
    assert "Work ID: human-ticket-44" in projected
    assert "The tool printed Work ID: " + PAST_WORK in projected
    assert "- Work ID: " + PAST_WORK not in projected
    assert "* Memory Attempt ID: " + PAST_ATTEMPT not in projected
    assert projected.endswith("Completed successfully.")
