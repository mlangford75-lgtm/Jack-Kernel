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
    if structured:
        assert request_view[0]["content"][0]["text"] == "[" + label + "] Request\n"
        assert request_view[0]["content"][1:] == raw
    else:
        assert request_view[0]["content"].startswith("[" + label + "] Request\n")
        assert request_view[0]["content"].endswith("Create a clock SVG")
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
    assert continuation.count(label) == 1
    assert "Current transaction: [" + label + "]" in continuation
    assert "Earlier transactions are context, not work performed" in continuation
    assert "Do not re-solve the task" in continuation
    assert "Stage 1 native reasoning and frozen response" in continuation
    assert "current-turn tool evidence" in continuation
    assert "Do not generate transaction identifiers" in continuation
    assert "Stage 1 native reasoning" in continuation and "Stage-1" not in continuation
    assert k.AGENTIC_36_STAGE2_PROMPT == "Generate a detailed summary of why you came to this conclusion."
    assert k.AGENTIC_STAGE1_PROMPT.startswith("Reasoning effort is set to xhigh.")


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


def _commit_owned(k, user_text, answer, memory):
    import asyncio
    original_user = {"role": "user", "content": user_text}
    history = [dict(original_user)]
    turn = k._agentic_begin_turn(history, fresh=True)
    frozen = k.append_extended_candidate_response(
        history, {"content": answer, "reasoning_content": "Reasoned about this turn."}
    )
    k._agentic_forensic_start_stage2(history)
    committed = asyncio.run(k.KERNEL._complete_commit(
        history, "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        frozen, memory,
    ))
    assert committed.agentic_turn_id == turn
    wire = k._format_agentic_completed_response(
        committed.frozen_xml, committed.frozen_answer, turn_id=committed.agentic_turn_id
    )
    assert wire.endswith("\n\n" + answer)
    return turn, original_user, wire


def test_identical_completed_turns_recover_distinct_ids_after_restart(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path)
    identical_user = "Generate the SVG"
    identical_answer = "Created clock.svg"
    identical_memory = "Generated requested clock graphic."
    a, user_a, wire_a = _commit_owned(k, identical_user, identical_answer, identical_memory)
    b, user_b, wire_b = _commit_owned(k, identical_user, identical_answer, identical_memory)
    assert a != b
    assert wire_a != wire_b
    assert k._agentic_unwrap_visible_memory(wire_a) == (
        a, identical_memory + "\n\n" + identical_answer
    )
    assert k._agentic_unwrap_visible_memory(wire_b) == (
        b, identical_memory + "\n\n" + identical_answer
    )

    # Simulate restart: no process-local shadow records/lifecycles remain.
    k._AGENTIC_SHADOW_LEDGER.clear()
    k._AGENTIC_TURN_LIFECYCLES.clear()
    history = [
        user_a, {"role": "assistant", "content": wire_a},
        user_b, {"role": "assistant", "content": wire_b},
        {"role": "user", "content": "What did you do in each turn?"},
    ]
    projected = k.compact_incoming_history(history)
    assert [item.get("_jack_forensic_turn_id") for item in projected[:6]] == [
        a, a, a, b, b, b
    ]
    rendered = k.BACKEND._stage_messages_for_profile(projected, k.STAGES["extended_initial"])
    label_a, label_b = k._agentic_visible_turn_label(a), k._agentic_visible_turn_label(b)
    assert rendered[0]["content"].startswith("[" + label_a + "] Request\n")
    assert rendered[1]["content"].startswith("[" + label_a + "] Memory\n")
    assert rendered[2]["content"].endswith("\n[" + label_a + "] Response")
    assert rendered[3]["content"].startswith("[" + label_b + "] Request\n")
    assert rendered[4]["content"].startswith("[" + label_b + "] Memory\n")
    assert rendered[5]["content"].endswith("\n[" + label_b + "] Response")
    assert not any("Reasoned about this turn." in str(item) for item in rendered)
    assert rendered[2]["content"].startswith(identical_answer)
    assert rendered[5]["content"].startswith(identical_answer)


def test_forged_or_wrong_owner_does_not_rebind_history(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path)
    turn, user, wire = _commit_owned(k, "Task", "Final answer", "Reasoned memory")
    label = k._agentic_visible_turn_label(turn)
    forged = "x" * 22
    if forged == label:
        forged = "y" * 22
    swapped = wire.replace("[" + label + "] Memory", "[" + forged + "] Memory", 1)
    history = [user, {"role": "assistant", "content": swapped}, {"role": "user", "content": "Next"}]
    view = k.compact_incoming_history(history)
    assert len(view) == 3
    assert not any(item.get("_jack_forensic_turn_id") for item in view)
    wrong_user = [
        {"role": "user", "content": "Different request"},
        {"role": "assistant", "content": wire},
        {"role": "user", "content": "Next"},
    ]
    view = k.compact_incoming_history(wrong_user)
    assert len(view) == 3
    assert not any(item.get("_jack_forensic_turn_id") for item in view)


def test_legacy_visible_capsule_remains_unmarked_and_compatible(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path)
    k.AGENTIC_TRANSACTION_LINKS_ENABLED = False
    turn, user, wire = _commit_owned(k, "Legacy work", "Legacy answer", "Legacy memory")
    assert not wire.startswith("[")
    k._AGENTIC_SHADOW_LEDGER.clear()
    history = [user, {"role": "assistant", "content": wire}, {"role": "user", "content": "Next"}]
    view = k.compact_incoming_history(history)
    assert [m["role"] for m in view] == ["user", "assistant", "assistant", "user"]
    assert view[2]["content"] == "Legacy answer"
    assert k._agentic_forensic_journal().get(turn)["status"] == "complete"
