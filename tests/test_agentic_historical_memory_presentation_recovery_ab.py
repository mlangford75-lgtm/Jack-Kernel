"""A/B: authenticated historical M has a clearly marked Stage-1 backend view.

The recovery baseline remains default. Canonical artifacts, the current user
request, A1, tool evidence and isolated Stage-2 cognition are not rewritten.
"""
import copy
import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ("flash", "balanced", "thorough", "exhaustive")
OLD_ID = "jack-turn-" + "a" * 32


def kernel(monkeypatch, tmp_path, profile, enabled):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    monkeypatch.setenv("JACK_AGENTIC_HISTORICAL_MEMORY_LABELS", "1" if enabled else "0")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_historical_presentation_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("enabled", (False, True))
def test_authenticated_simple_memory_label_only_in_enabled_stage1(monkeypatch, tmp_path, profile, enabled):
    k = kernel(monkeypatch, tmp_path, profile, enabled)
    memory = "Completed report: discount 10%, total 47.20."
    answer = "The verified total is 47.20."
    history = [
        {"role": "user", "content": "Earlier request"},
        {"role": "assistant", "content": memory, "_jack_agentic_projected_kind": "M"},
        {"role": "assistant", "content": answer, "_jack_agentic_projected_kind": "A1"},
        {"role": "tool", "content": "Authenticated earlier tool output", "name": "read"},
        {"role": "user", "content": "Current request"},
    ]
    before = copy.deepcopy(history)
    adapter = k.OpenAICompatibleBackend(k.CFG)
    projected = adapter._stage_messages_for_profile(history, k.STAGES["extended_initial"])
    assert history == before
    header = k.AGENTIC_HISTORICAL_MEMORY_VIEW_HEADER
    assert k.AGENTIC_HISTORICAL_MEMORY_LABELS is enabled
    assert projected[1]["content"] == (header + memory if enabled else memory)
    assert projected[2]["content"] == answer
    assert projected[3] == history[3]
    assert projected[4] == history[4]
    assert all(not key.startswith("_jack_") for msg in projected if isinstance(msg, dict) for key in msg)


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("enabled", (False, True))
def test_opaque_or_unverified_assistant_never_relabelled(monkeypatch, tmp_path, profile, enabled):
    k = kernel(monkeypatch, tmp_path, profile, enabled)
    h = [
        {"role": "user", "content": "Earlier"},
        {"role": "assistant", "content": "Unverified imported content"},
        {"role": "user", "content": "Current"},
    ]
    out = k.OpenAICompatibleBackend(k.CFG)._stage_messages_for_profile(
        h, k.STAGES["extended_initial"])
    assert out == h


@pytest.mark.parametrize("profile", PROFILES)
def test_stage2_still_receives_only_current_user_and_frozen_answer(monkeypatch, tmp_path, profile):
    k = kernel(monkeypatch, tmp_path, profile, True)
    history = [
        {"role": "user", "content": "Prior request"},
        {"role": "assistant", "content": "Historical memory", "_jack_agentic_projected_kind": "M"},
        {"role": "assistant", "content": "Old frozen answer", "_jack_agentic_projected_kind": "A1"},
        {"role": "user", "content": "Current task"},
        {"role": "assistant", "content": "Current answer",
         "reasoning_content": "Current reasoning", "_jack_extended_candidate_response": True},
    ]
    before = copy.deepcopy(history)
    stage2 = k._agentic_stage2_test_history(history, k.STAGES["extended_reflection"])
    assert history == before
    assert [m["role"] for m in stage2] == ["user", "assistant"]
    assert stage2[0]["content"] == "Current task"
    assert stage2[1]["content"] == "Current answer"
    assert k.AGENTIC_HISTORICAL_MEMORY_VIEW_HEADER not in str(stage2)


@pytest.mark.parametrize("profile", PROFILES)
def test_existing_recovery_memory_transform_and_a1_still_preserved(monkeypatch, tmp_path, profile):
    k = kernel(monkeypatch, tmp_path, profile, True)
    memory = (
        "Task: Extend ledger.py\n"
        "Work ID: " + OLD_ID + "\n"
        "Consequential working knowledge: 47.20.\n"
        "[Jack Tool History - Host-Recorded Receipt]\n"
        "outcome=RESULT_RETURNED\n"
        "[/Jack Tool History - Host-Recorded Receipt]\n"
    )
    h = [
        {"role": "user", "content": "Old task"},
        {"role": "assistant", "content": memory, "_jack_agentic_projected_kind": "M"},
        {"role": "assistant", "content": "Final answer 47.20.", "_jack_agentic_projected_kind": "A1"},
        {"role": "user", "content": "Next task"},
    ]
    original = copy.deepcopy(h)
    p = k.OpenAICompatibleBackend(k.CFG)._stage_messages_for_profile(
        h, k.STAGES["extended_initial"])
    assert h == original
    assert p[1]["content"].startswith(k.AGENTIC_HISTORICAL_MEMORY_VIEW_HEADER)
    assert p[1]["content"].count(k.AGENTIC_HISTORICAL_MEMORY_VIEW_HEADER) == 1
    assert "47.20" in p[1]["content"]
    assert "outcome=RESULT_RETURNED" in p[1]["content"]
    assert "Recorded historical tool outcomes" in p[1]["content"]
    assert OLD_ID not in p[1]["content"]
    assert p[2]["content"] == "Final answer 47.20."


def test_other_reasoning_modes_never_label_agentic_history(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "off")
    monkeypatch.setenv("JACK_AGENTIC_HISTORICAL_MEMORY_LABELS", "1")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    name = "jack_nonagentic_history_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    assert not k.AGENTIC_HISTORICAL_MEMORY_LABELS
    h = [{"role": "assistant", "content": "Original memory",
          "_jack_agentic_projected_kind": "M"}]
    p = k.OpenAICompatibleBackend(k.CFG)._stage_messages_for_profile(h, k.STAGES["thesis"])
    assert p[0]["content"] == "Original memory"
