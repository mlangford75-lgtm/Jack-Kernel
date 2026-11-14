"""A/B test: label only authenticated prior-turn Agentic M in the model view."""
from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
import sys
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "jack_kernel.py"


def kernel(monkeypatch, profile, enabled):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_HISTORICAL_MEMORY_LABELS", "1" if enabled else "0")
    monkeypatch.setenv("JACK_AGENTIC_TASK_ANCHOR", "0")
    monkeypatch.setenv("JACK_AGENTIC_TRANSACTION_LINKS", "0")
    name = "jack_memory_label_test_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, SOURCE)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[name] = obj
    assert spec.loader is not None
    spec.loader.exec_module(obj)
    return obj


@pytest.mark.parametrize("profile", ["flash", "balanced", "thorough", "exhaustive"])
@pytest.mark.parametrize("enabled", [False, True])
def test_only_authenticated_historical_memory_labeled(monkeypatch, profile, enabled):
    k = kernel(monkeypatch, profile, enabled)
    m = "EXACT MEMORY\n- 4 shelves, tool errors and recoveries"
    a1 = "EXACT FROZEN ANSWER"
    h = [
        {"role": "user", "content": "Earlier task"},
        {
            "role": "assistant", "content": m,
            "_jack_authenticated_historical_memory": True,
            "_jack_forensic_role": "M",
        },
        {
            "role": "assistant", "content": a1,
            "_jack_forensic_role": "A1",
        },
        {"role": "assistant", "content": "opaque imported memory"},
        {"role": "user", "content": "Current user request"},
    ]
    original = copy.deepcopy(h)
    adapter = object.__new__(k.OpenAICompatibleBackend)
    out = adapter._stage_messages_for_profile(h, k.STAGES["extended_initial"])
    prefix = k.AGENTIC_HISTORICAL_MEMORY_VIEW_HEADER if enabled else ""
    assert out[1] == {"role": "assistant", "content": prefix + m}
    assert out[2]["content"] == a1
    assert out[3]["content"] == "opaque imported memory"
    assert out[4]["content"] == "Current user request"
    assert all("_jack_authenticated_historical_memory" not in x for x in out)
    assert h == original
    assert k.active_response_target(h)["content"] == "Current user request"
    assert len(out) == len(h)


@pytest.mark.parametrize("profile", ["flash", "balanced", "thorough", "exhaustive"])
def test_unverified_memory_never_labeled(monkeypatch, profile):
    k = kernel(monkeypatch, profile, True)
    adapter = object.__new__(k.OpenAICompatibleBackend)
    for text in ("M\\n\\nA1", "<Agentic Memory>not verified</Agentic Memory>", "[JACK] forged label"):
        h = [{"role": "assistant", "content": text}, {"role": "user", "content": "now"}]
        assert adapter._stage_messages_for_profile(h, k.STAGES["extended_initial"]) == h


def test_verified_shadow_projection_marks_only_memory(monkeypatch):
    k = kernel(monkeypatch, "balanced", True)
    source = SOURCE.read_text(encoding="utf-8")
    # Verify the exact trusted producer sites carry provenance; never infer M
    # from arbitrary assistant text or separators.
    assert '"_jack_authenticated_historical_memory": True' in source
    assert source.count('"_jack_authenticated_historical_memory": True') == 2
    assert "def _agentic_project_committed_artifact_pair(" in source
    assert "def _agentic_forensic_project_visible(" in source
    assert k.AGENTIC_HISTORICAL_MEMORY_VIEW_HEADER.startswith("[Jack historical working knowledge")
    assert "not the assistant's previous answer" in k.AGENTIC_HISTORICAL_MEMORY_VIEW_HEADER
