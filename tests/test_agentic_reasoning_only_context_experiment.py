"""Experimental Agentic policy: only historical native reasoning retires.

Exercises all active mainline Agentic profiles, authenticated Stage-2 inputs,
historical tool fidelity, and fail-soft Stage-2 archive-before-retirement.
"""
from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "jack_kernel.py"


def load_kernel(profile: str):
    os.environ["JACK_REASONING_LEVEL"] = "agentic"
    os.environ["JACK_AGENTIC_PROFILE"] = profile
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "off"
    os.environ["JACK_BACKEND_MODEL"] = "test-model"
    os.environ["JACK_BACKEND_PROFILE"] = "lmstudio"
    name = f"jack_reasoning_only_{profile}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("profile", ["flash", "balanced", "thorough"])
def test_stage2_receives_same_turn_reasoning_and_exact_outcome(profile):
    k = load_kernel(profile)
    history = [
        {"role": "user", "content": "prior request"},
        {"role": "assistant", "content": "old answer", "reasoning_content": "old R1"},
        {"role": "user", "content": "current request"},
        {"role": "assistant", "content": "", "reasoning_content": "considered option A",
         "_jack_stage_key": "extended_initial", "_jack_internal_tool_exchange": True},
        {"role": "assistant", "content": "exact final answer", "reasoning_content": "selected option B",
         "_jack_extended_candidate_response": True},
    ]
    projected = k._agentic_stage2_test_history(history, k.STAGES["extended_reflection"])
    assert [item["role"] for item in projected] == ["user", "assistant"]
    assert projected[0]["content"] == "current request"
    assert projected[1]["content"] == "exact final answer"
    assert projected[1]["reasoning_content"] == "considered option A\n\nselected option B"
    assert "old R1" not in str(projected)
    assert not k.STAGES["extended_reflection"].allow_tools
    assert k.CFG.agentic_profile == profile
    assert not hasattr(k, "AGENTIC_REASONING_ONLY_RETIREMENT_TOGGLE")


@pytest.mark.parametrize("profile", ["flash", "balanced", "thorough"])
def test_prunes_only_historical_reasoning_not_tool_evidence(profile):
    k = load_kernel(profile)
    calls = [{
        "id": "tool-A", "type": "function",
        "function": {"name": "write", "arguments": json.dumps({"path": "notes.txt", "content": "EXACT"})},
    }]
    original = [
        {"role": "user", "content": "make notes"},
        {"role": "assistant", "content": "", "tool_calls": calls, "reasoning_content": "R1 before tool"},
        {"role": "tool", "tool_call_id": "tool-A", "name": "write", "content": "EXACT RESULT"},
        {"role": "assistant", "content": "M\n\nA1", "reasoning_content": "old R2"},
        {"role": "user", "content": "follow-up"},
    ]
    projected = k._compact_agentic_completed_capsules(original)
    assert projected is not None
    assert projected[0]["content"] == "make notes"
    assert projected[1]["tool_calls"] == calls
    assert projected[2]["content"] == "EXACT RESULT"
    assert projected[3]["content"] == "M\n\nA1"
    assert projected[4]["content"] == "follow-up"
    assert all("reasoning_content" not in m for m in projected)
    assert original[1]["reasoning_content"] == "R1 before tool"
    assert original[3]["reasoning_content"] == "old R2"


@pytest.mark.parametrize("profile", ["flash", "balanced", "thorough"])
def test_degraded_memory_archives_before_retiring_reasoning(profile, monkeypatch):
    k = load_kernel(profile)
    events = []

    def archive(history, answer, memory):
        events.append(("archive", answer, memory, history[1]["reasoning_content"]))

    monkeypatch.setattr(k, "_archive_agentic_stage1_forensic", archive)
    monkeypatch.setattr(k, "_agentic_forensic_fail_memory", lambda history, reason: events.append(("fail", reason)))
    monkeypatch.setattr(k, "_agentic_shadow_record_commit", lambda answer, memory, **kwargs: events.append(("shadow", answer, memory)))
    monkeypatch.setattr(k, "_agentic_finish_delayed_one_hop", lambda history: events.append(("retire",)))

    history = [
        {"role": "user", "content": "request"},
        {"role": "assistant", "content": "answer", "reasoning_content": "long reasoning"},
    ]
    kernel = object.__new__(k.JackQwenKernel)
    result = kernel._agentic_degraded_result(history, {}, "answer", "Stage 2 interrupted")
    assert result.content == "answer"
    assert result.finish_reason == "stop"
    assert history == []
    assert events[0] == ("archive", "answer", None, "long reasoning")
    assert events[1] == ("fail", "Stage 2 interrupted")
    assert events[2] == ("shadow", "answer", None)
    assert events[3] == ("retire",)


@pytest.mark.parametrize("profile", ["flash", "balanced", "thorough"])
def test_optional_failed_distillation_archive_marks_memory_absent(profile, monkeypatch, tmp_path):
    k = load_kernel(profile)
    monkeypatch.setattr(k, "CFG", replace(k.CFG, forensic_archive_mode="stage",
                                       forensic_archive_dir=str(tmp_path)))
    snapshot = {
        "schema": "jack.forensic.agentic.stage1.v2",
        "reasoning_trace": "original preserved R1",
        "tool_trajectory": [{"role": "tool", "content": "EXACT TOOL RESULT"}],
        "active_response_target": {"id": "user-turn-test"},
        "frozen_stage1_answer": "answer",
    }
    history = [{"role": "assistant", "content": "answer",
                "_jack_agentic_stage1_forensic_snapshot": snapshot}]
    path = k._archive_agentic_stage1_forensic(history, "answer", None)
    assert path is not None and path.exists()
    item = json.loads(path.read_text(encoding="utf-8"))
    assert item["stage2_memory_status"] == "ABSENT"
    assert item["jack_xml_sha256"] is None
    assert item["reasoning_trace"] == "original preserved R1"
    assert item["tool_trajectory"][0]["content"] == "EXACT TOOL RESULT"
    assert "_jack_agentic_stage1_forensic_snapshot" not in history[0]


def test_surgical_directive_retains_prime_directive():
    k = load_kernel("balanced")
    prompt = k.AGENTIC_36_STAGE2_PROMPT
    assert "Prime Directive" in prompt
    assert "current user request" in prompt
    assert "reasoning and completed response" in prompt
    assert "When a failed tool action is subsequently corrected" in prompt
    assert "verified" in prompt
    assert "Do not simply repeat" in prompt
    assert "Begin with one valid, single-line JSON object" in prompt
