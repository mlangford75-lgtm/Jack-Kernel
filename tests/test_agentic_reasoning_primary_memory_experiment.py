"""Reasoning-primary retrospective is source-isolated and opt-in.

Only tests host projection / instruction selection; no live model is simulated.
"""
import copy
import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def kernel(monkeypatch, tmp_path, *, enabled=True, profile="thorough"):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    monkeypatch.setenv("JACK_REASONING_PRIMARY_DUMMY", "test")
    monkeypatch.setenv(
        "JACK_AGENTIC_REASONING_PRIMARY_EXPERIMENT", "1" if enabled else "0"
    )
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    name = "reasoning_primary_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def history(reasoning=True):
    h = [
        {"role": "user", "content": "PAST USER: make a recipe"},
        {"role": "assistant", "content": "PAST ANSWER"},
        {"role": "user", "content": "CURRENT REQUEST: create three customers; end with STATE CARD"},
        {"role": "assistant", "content": "", "reasoning_content": "Considered A; rejected for duplication.",
         "_jack_internal_tool_exchange": True},
        {"role": "assistant", "content": "FINAL USER-FACING ANSWER: three customers\\nSTATE CARD",
         "_jack_extended_candidate_response": True},
    ]
    if reasoning:
        h[-1]["reasoning_content"] = "Chose B. Exact reusable insight: preserve unique relationships."
    else:
        h[-2].pop("reasoning_content")
    return h


def test_reasoning_only_projection_does_not_leak_user_or_final(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path)
    original = history()
    before = copy.deepcopy(original)
    projected = k._agentic_stage2_test_history(original, k.STAGES["extended_reflection"])
    assert original == before
    assert len(projected) == 1
    assert projected[0]["role"] == "assistant"
    assert projected[0]["content"] == "Reasoning complete."
    assert projected[0]["_jack_reasoning_primary_source"] is True
    assert projected[0]["reasoning_content"] == (
        "Considered A; rejected for duplication.\\n\\n"
        "Chose B. Exact reusable insight: preserve unique relationships."
    )
    assert "STATE CARD" not in str(projected)
    assert "CURRENT REQUEST" not in str(projected)
    assert "FINAL USER-FACING ANSWER" not in str(projected)
    directive = k.AGENTIC_REASONING_PRIMARY_MEMORY_PROMPT
    assert "Stage 1" not in directive and "Stage 2" not in directive
    assert "Jack" not in directive and "R1" not in directive and "A1" not in directive
    assert "JSON" not in directive
    assert "preceding reasoning" in directive


def test_off_preserves_original_projection(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path, enabled=False)
    original = history()
    projected = k._agentic_stage2_test_history(original, k.STAGES["extended_reflection"])
    assert len(projected) == 2
    assert projected[0]["content"] == original[2]["content"]
    assert projected[1]["content"] == original[-1]["content"]
    assert "Chose B." in projected[1]["reasoning_content"]


def test_missing_reasoning_uses_legacy_view(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path)
    original = history(reasoning=False)
    projected = k._agentic_stage2_test_history(original, k.STAGES["extended_reflection"])
    assert len(projected) == 2
    assert projected[0]["content"] == original[2]["content"]
    assert projected[1]["content"] == original[-1]["content"]


def test_flash_keeps_legacy_view(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path, profile="flash")
    projected = k._agentic_stage2_test_history(history(), k.STAGES["extended_reflection"])
    assert len(projected) == 2


def test_missing_frozen_response_still_fails_closed(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path)
    with pytest.raises(k.HTTPException) as error:
        k._agentic_stage2_test_history(history()[:-1], k.STAGES["extended_reflection"])
    assert error.value.status_code == 409


def test_non_reflection_stage_is_unmodified(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path)
    original = history()
    assert k._agentic_stage2_test_history(
        original, k.STAGES["extended_initial"]
    ) is original
