"""Phase 3A regression tests: Jack-owned original U, A, M; no modified client needed."""
from __future__ import annotations
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]

def load():
    os.environ["JACK_REASONING_LEVEL"] = "agentic"
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "off"
    os.environ["JACK_BACKEND_MODEL"] = "test-model"
    os.environ["JACK_BACKEND_PROFILE"] = "lmstudio"
    name = "jack_agentic_phase3a_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_client_independent_complete_commit_records_exact_U_A_M():
    k = load()
    user = {"role": "user", "content": "  user request\nwith whitespace  "}
    history = [user, {"role": "assistant", "content": "earlier stage"}]
    out = asyncio.run(k.KERNEL._complete_commit(history, "", {}, "  frozen A1\n", "why M1"))
    assert out.frozen_answer == "  frozen A1\n"
    assert not history
    assert len(k._AGENTIC_SHADOW_LEDGER) == 1
    (key, record), = k._AGENTIC_SHADOW_LEDGER.items()
    assert key[0] == "jack-owned" and key[2] == 0
    assert record.turn_id.startswith("jack-turn-")
    assert json.loads(record.user_request.message_json) == user
    assert record.response.content == "  frozen A1\n"
    assert record.memory.content == "why M1"
    assert record.user_request.sha256 == k._sha256_text(record.user_request.message_json)
    assert record.response.sha256 == k._sha256_text("  frozen A1\n")


def test_request_from_latest_authentic_user_not_previous_or_stage_control():
    k = load()
    user = {"role": "user", "content": [{"type": "text", "text": "What about this?"},
                                      {"type": "image_url", "image_url": {"url": "data:image/png;base64,ABCD"}}],
            "name": "requester"}
    history = [
        {"role": "user", "content": "old request"},
        {"role": "assistant", "content": "old answer"},
        user,
        {"role": "assistant", "content": "stage thinking output", "_jack_stage_key": "extended_initial"},
        {"role": "tool", "content": "tool result", "tool_call_id": "call1"},
    ]
    req = k._agentic_shadow_capture_user_request(history)
    assert json.loads(req.message_json) == user
    assert "old request" not in req.message_json
    assert req.sha256 == k._sha256_text(req.message_json)


def test_two_identical_user_requests_receive_distinct_host_turns():
    k = load()
    for i in range(2):
        history = [{"role": "user", "content": "identical"}]
        asyncio.run(k.KERNEL._complete_commit(history, "", {}, "same answer", "same memory"))
    assert len(k._AGENTIC_SHADOW_LEDGER) == 2
    ids = {r.turn_id for r in k._AGENTIC_SHADOW_LEDGER.values()}
    assert len(ids) == 2
    assert len({r.user_request.sha256 for r in k._AGENTIC_SHADOW_LEDGER.values()}) == 1


def test_degraded_stage2_keeps_exact_original_request_without_fake_memory():
    k = load()
    user = {"role": "user", "content": " original "}
    history = [user]
    result = k.KERNEL._agentic_degraded_result(history, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "valid frozen answer", "stage2 failed")
    assert result.content == "valid frozen answer"
    record = next(iter(k._AGENTIC_SHADOW_LEDGER.values()))
    assert json.loads(record.user_request.message_json) == user
    assert record.response.content == "valid frozen answer"
    assert record.memory is None
    assert record.status == "memory_failed"
    assert not history


def test_client_hint_remains_optional_correlation_not_memory_authority():
    k = load()
    token = k._AGENTIC_TURN_HINT.set(k.AgenticTurnTransportHint("client", "entry", 2))
    try:
        hist = [{"role": "user", "content": "request"}]
        asyncio.run(k.KERNEL._complete_commit(hist, "", {}, "A", "M"))
    finally:
        k._AGENTIC_TURN_HINT.reset(token)
    r = k._AGENTIC_SHADOW_LEDGER[("client", "entry", 2)]
    assert r.turn_id.startswith("jack-turn-")
    assert json.loads(r.user_request.message_json)["content"] == "request"
    assert not hasattr(k, "_agentic_shadow_lookup_memory")


def test_preserve_both_cognitive_prompts_byte_exact():
    k = load()
    assert k.AGENTIC_STAGE1_PROMPT == (
        "Reasoning effort is set to xhigh. Please think carefully through the task, "
        "validate key assumptions, consider plausible alternatives, and prioritize "
        "correctness, consistency, and clarity in the final answer."
    )
    assert k.AGENTIC_36_STAGE2_PROMPT == "Generate a detailed summary of why you came to this conclusion."
