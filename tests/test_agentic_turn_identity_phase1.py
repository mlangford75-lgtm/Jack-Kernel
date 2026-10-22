"""Phase 1 correlation-hint tests: local-only; no memory authority."""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import uuid
import pytest

ROOT = Path(__file__).resolve().parents[1]

def kernel():
    os.environ["JACK_REASONING_LEVEL"] = "agentic"
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "off"
    os.environ["JACK_BACKEND_MODEL"] = "test-model"
    os.environ["JACK_BACKEND_PROFILE"] = "lmstudio"
    name = f"jack_agentic_phase1_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def req(headers):
    return SimpleNamespace(headers=headers)


def test_no_transport_hint_keeps_normal_clients_compatible():
    k = kernel()
    assert k._agentic_turn_transport_hint_from_request(req({})) is None
    assert k._agentic_turn_transport_hint_from_request(SimpleNamespace()) is None


def test_valid_hint_preserves_session_user_entry_and_turn_ordinal():
    k = kernel()
    fields = {
        "x-jack-agentic-session-id": "session-23",
        "x-jack-agentic-user-entry-id": "user-entry-8",
        "x-jack-agentic-turn-ordinal": "8",
    }
    result = k._agentic_turn_transport_hint_from_request(req(fields))
    assert result == k.AgenticTurnTransportHint("session-23", "user-entry-8", 8)
    assert k._agentic_turn_transport_hint_from_request(req(fields)) == result


def test_partial_or_invalid_hint_fails_without_inference():
    k = kernel()
    base = {
        "x-jack-agentic-session-id": "session-23",
        "x-jack-agentic-user-entry-id": "user-entry-8",
        "x-jack-agentic-turn-ordinal": "8",
    }
    for changed in (
        {"x-jack-agentic-user-entry-id": ""},
        {"x-jack-agentic-session-id": "../wrong"},
        {"x-jack-agentic-turn-ordinal": "0"},
        {"x-jack-agentic-turn-ordinal": "-1"},
        {"x-jack-agentic-turn-ordinal": "1.0"},
    ):
        candidate = {**base, **changed}
        with pytest.raises(k.HTTPException) as caught:
            k._agentic_turn_transport_hint_from_request(req(candidate))
        assert caught.value.status_code == 400


def test_stage_prompts_are_not_replaced_by_phase1():
    k = kernel()
    assert k.AGENTIC_STAGE1_PROMPT == (
        "Reasoning effort is set to xhigh. Please think carefully through the task, "
        "validate key assumptions, consider plausible alternatives, and prioritize "
        "correctness, consistency, and clarity in the final answer."
    )
    assert k.AGENTIC_36_STAGE2_PROMPT == "Generate a detailed summary of why you came to this conclusion."
