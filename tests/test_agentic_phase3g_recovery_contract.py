"""Restore Phase-3G model-facing memory behavior without changing cache topology.

The forensic journal still enforces U / A1 ownership; labels/hashes stay
host-side by default and Stage 2 receives the historical short continuation.
"""
import importlib.util
from pathlib import Path
import sys
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_default(monkeypatch, tmp_path, *, labels=None):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT", "1")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / ("forensic-" + uuid.uuid4().hex + ".sqlite")))
    if labels is None:
        monkeypatch.delenv("JACK_AGENTIC_TASK_ANCHOR", raising=False)
    else:
        monkeypatch.setenv("JACK_AGENTIC_TASK_ANCHOR", "1" if labels else "0")
    name = "jack_phase3g_recovery_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


@pytest.mark.parametrize("labels", [None, False])
@pytest.mark.parametrize("structured", [False, True])
def test_phase3g_retrospective_restored_and_cached_prefix_preserved(monkeypatch, tmp_path, labels, structured):
    k = load_default(monkeypatch, tmp_path, labels=labels)
    request = [{"type": "text", "text": "Create a cuckoo clock SVG"}] if structured else "Create a cuckoo clock SVG"
    history = [{"role": "user", "content": request}]
    turn = k._agentic_begin_turn(history, fresh=True)
    first = k.BACKEND._stage_messages_for_profile(history, k.STAGES["extended_initial"])
    assert first[0]["content"] == request
    a1 = k.append_extended_candidate_response(
        history, {"content": "Created a cuckoo clock", "reasoning_content": "Decided on clock face, bird, and pendulum"}
    )
    k._agentic_forensic_start_stage2(history)
    second = k.BACKEND._stage_messages_for_profile(history, k.STAGES["extended_reflection"])
    assert second[:len(first)] == first
    assert second[-1]["content"] == a1
    assert second[-1]["reasoning_content"] == "Decided on clock face, bird, and pendulum"
    assert k._stage_continuation(k.STAGES["extended_reflection"], history) == k._AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION
    assert "[JACK LINK" not in str(second)
    assert "[JACK TASK SCOPE" not in k._stage_continuation(k.STAGES["extended_reflection"], history)
    assert k._agentic_cache_append_enabled(k.STAGES["extended_reflection"])
    assert k._agentic_forensic_journal().get(turn)["status"] == "stage2_active"


def test_opt_in_forensic_projection_keeps_regression_comparison_available(monkeypatch, tmp_path):
    k = load_default(monkeypatch, tmp_path, labels=True)
    k.AGENTIC_STAGE2_RETENTION_TEST = "baseline"  # must NOT alter canonical Stage 2
    history = [{"role": "user", "content": [{"type": "text", "text": "Make the bird blue"}]}]
    turn = k._agentic_begin_turn(history, fresh=True)
    first = k.BACKEND._stage_messages_for_profile(history, k.STAGES["extended_initial"])
    assert f"[JACK LINK turn={turn} | artifact=U]" in str(first)
    k.append_extended_candidate_response(history, {"content": "Bird is now blue"})
    k._agentic_forensic_start_stage2(history)
    continuation = k._stage_continuation(k.STAGES["extended_reflection"], history)
    assert "JACK TASK SCOPE" not in continuation
    assert continuation == k._AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION
    assert k._agentic_stage2_test_history(history, k.STAGES["extended_reflection"])[0]["role"] == "user"


def test_frozen_prompts_and_delayed_techniques_not_changed(monkeypatch, tmp_path):
    k = load_default(monkeypatch, tmp_path)
    assert k.AGENTIC_STAGE1_PROMPT.startswith("Reasoning effort is set to xhigh.")
    assert k.AGENTIC_STAGE1_PROMPT.endswith("Carefully reason on the task before using tools.")
    assert "Do not imitate the style, format, or structure of previous turns" in k.AGENTIC_STAGE1_PROMPT
    assert k.AGENTIC_36_STAGE2_PROMPT == k._AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION
    assert k._agentic_cache_append_enabled(k.STAGES["extended_reflection"])
    assert k.STAGES["extended_reflection"].allow_tools is False


def test_default_historical_memory_unlabeled_but_exact(monkeypatch, tmp_path):
    k = load_default(monkeypatch, tmp_path)
    # Host provenance metadata may be available for authenticated historical
    # artifacts, but model-facing labels must remain disabled by default.
    history = [
        {"role": "user", "content": "Old work", "_jack_forensic_turn_id": "jack-turn-abc"},
        {"role": "assistant", "content": "Prior memory", "_jack_forensic_turn_id": "jack-turn-abc", "_jack_forensic_role": "M"},
        {"role": "assistant", "content": "Prior answer", "_jack_forensic_turn_id": "jack-turn-abc", "_jack_forensic_role": "A1"},
        {"role": "user", "content": "New work"},
    ]
    view = k.BACKEND._stage_messages_for_profile(history, k.STAGES["extended_initial"])
    assert [entry["content"] for entry in view] == ["Old work", "Prior memory", "Prior answer", "New work"]
    assert not any(key.startswith("_jack_") for entry in view for key in entry)


def test_downturn_memory_and_answer_survive_pruning_without_model_labels(monkeypatch, tmp_path):
    import asyncio
    k = load_default(monkeypatch, tmp_path)
    historical = []
    for user_text, memory, a1 in (
        ("Generate cuckoo clock", "Created a wooden clock with a bird and pendulum", "Saved clock.svg"),
        ("Make the bird blue", "Changed the bird fill to blue without altering the clock face", "Bird is blue"),
    ):
        user = {"role": "user", "content": [{"type": "text", "text": user_text}]}
        active = [dict(user)]
        k._agentic_begin_turn(active, fresh=True)
        frozen = k.append_extended_candidate_response(active, {"content": a1, "reasoning_content": "Current Stage-1 native rationale"})
        k._agentic_forensic_start_stage2(active)
        committed = asyncio.run(k.KERNEL._complete_commit(
            active, "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, frozen, memory,
        ))
        historical.extend((user, {"role": "assistant", "content": k._format_agentic_completed_response(
            committed.frozen_xml, committed.frozen_answer,
        )}))
    historical.append({"role": "user", "content": [{"type": "text", "text": "What colors did we change?"}]})
    compact = k.compact_incoming_history(historical)
    rendered = k.BACKEND._stage_messages_for_profile(compact, k.STAGES["extended_initial"])
    assert [m["role"] for m in rendered] == [
        "user", "assistant", "assistant", "user", "assistant", "assistant", "user",
    ]
    assert "wooden clock with a bird" in rendered[1]["content"]
    assert rendered[2]["content"] == "Saved clock.svg"
    assert "bird fill to blue" in rendered[4]["content"]
    assert rendered[5]["content"] == "Bird is blue"
    assert not any("JACK LINK" in str(m) for m in rendered)
    assert not any(m.get("reasoning_content") for m in rendered)
