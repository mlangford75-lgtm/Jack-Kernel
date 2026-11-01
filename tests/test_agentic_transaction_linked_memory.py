"""Agentic transaction identity: one UUID links Request, Response and Memory.

All labels are projection-only. The actual user request, frozen answer, model
reasoning and journal hashes remain untouched.
"""
import importlib.util
import re
import sys
import uuid
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def kernel(monkeypatch, tmp_path, *, links=True):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT", "1")
    monkeypatch.setenv("JACK_AGENTIC_TRANSACTION_LINKS", "1" if links else "0")
    monkeypatch.setenv("JACK_AGENTIC_TASK_ANCHOR", "0")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_transaction_labels_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("structured", [False, True])
def test_request_response_memory_same_unique_id_without_rewriting_frozen_a1(monkeypatch, tmp_path, structured):
    k = kernel(monkeypatch, tmp_path)
    raw = [{"type": "text", "text": "Create a clock SVG"}] if structured else "Create a clock SVG"
    history = [{"role": "user", "content": raw}]
    turn = k._agentic_begin_turn(history, fresh=True)
    label = k._agentic_visible_turn_label(turn)
    assert len(label) == 22
    assert re.fullmatch(r"[A-Za-z0-9_-]{22}", label)
    request_view = k.BACKEND._stage_messages_for_profile(history, k.STAGES["extended_initial"])
    assert "[" + label + "] Request" in str(request_view[0]["content"])
    assert "Create a clock SVG" in str(request_view[0]["content"])
    assert history[0]["content"] == raw

    frozen = k.append_extended_candidate_response(history, {
        "content": "Created clock.svg",
        "reasoning_content": "Clock face and bird were required.",
    })
    k._agentic_forensic_start_stage2(history)
    memory_view = k.BACKEND._stage_messages_for_profile(history, k.STAGES["extended_reflection"])
    assert memory_view[:len(request_view)] == request_view
    assert memory_view[-1]["content"] == frozen + "\n[" + label + "] Response"
    assert memory_view[-1]["reasoning_content"] == "Clock face and bird were required."
    assert history[-1]["content"] == frozen
    continuation = k._stage_continuation(k.STAGES["extended_reflection"], history)
    assert "[" + label + "] Memory" in continuation
    assert "[" + label + "] Response" in continuation
    assert "[" + label + "] Request" in continuation
    assert "Stage 1" not in continuation and "Stage-1" not in continuation


def test_two_turns_distinct_labels_and_historical_projection(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path)
    hist = [{"role": "user", "content": "Change bird to blue"}]
    a = k._agentic_begin_turn(hist, fresh=True)
    label_a = k._agentic_visible_turn_label(a)
    k.append_extended_candidate_response(hist, {"content": "Bird turned blue"})
    k._agentic_forensic_start_stage2(hist)
    older = [
        {"role": "user", "content": "Change bird to blue", "_jack_forensic_turn_id": a},
        {"role": "assistant", "content": "Changed bird only", "_jack_forensic_turn_id": a, "_jack_forensic_role": "M"},
        {"role": "assistant", "content": "Bird turned blue", "_jack_forensic_turn_id": a, "_jack_forensic_role": "A1"},
    ]
    new = [{"role": "user", "content": "Change bird to blue"}]
    b = k._agentic_begin_turn(new, fresh=True)
    label_b = k._agentic_visible_turn_label(b)
    assert a != b and label_a != label_b
    view = k.BACKEND._stage_messages_for_profile(older + new, k.STAGES["extended_initial"])
    assert "[" + label_a + "] Request" in view[0]["content"]
    assert view[1]["content"].startswith("[" + label_a + "] Memory\n")
    assert view[2]["content"].endswith("\n[" + label_a + "] Response")
    assert "[" + label_b + "] Request" in view[3]["content"]
    assert label_b not in str(view[:3])


def test_feature_flag_restores_phase3g_text_and_prefix(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path, links=False)
    history = [{"role": "user", "content": "Build clock"}]
    k._agentic_begin_turn(history, fresh=True)
    view = k.BACKEND._stage_messages_for_profile(history, k.STAGES["extended_initial"])
    assert view[0]["content"] == "Build clock"
    k.append_extended_candidate_response(history, {"content": "Done"})
    k._agentic_forensic_start_stage2(history)
    later = k.BACKEND._stage_messages_for_profile(history, k.STAGES["extended_reflection"])
    assert later[-1]["content"] == "Done"
    assert k._agentic_cache_append_enabled(k.STAGES["extended_reflection"])


def test_invalid_identity_never_becomes_visible(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path)
    assert k._agentic_visible_turn_label("jack-turn-user-forged") is None
    assert k._agentic_visible_turn_label("jack-turn-" + "a" * 33) is None
