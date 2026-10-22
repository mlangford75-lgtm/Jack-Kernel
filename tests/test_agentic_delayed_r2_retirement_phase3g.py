"""Phase 3G: opt-in full-turn one-hop R2 retirement.

Run with: python -m pytest -q tests/test_agentic_delayed_r2_retirement_phase3g.py
"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
MARKER = "===== JACK AGENTIC NATIVE PASS 2 =====\n[NATIVE REASONING]\n"


def load(enabled=True, cache_enabled=True):
    os.environ["JACK_REASONING_LEVEL"] = "Local Agentic (Preserve Thinking)"
    os.environ["JACK_BACKEND_PROFILE"] = "lmstudio"
    os.environ["JACK_BACKEND_MODEL"] = "test-model"
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "off"
    os.environ["JACK_AGENTIC_DELAY_R2_RETIREMENT"] = "1" if enabled else "0"
    os.environ["JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT"] = "1" if cache_enabled else "0"
    name = "jack_phase3g_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def bridge_history():
    return [
        {"role": "user", "content": "previous"},
        {"role": "assistant", "content": "previous memory",
         "reasoning_content": "previous R2", "_jack_agentic_one_hop_r2": True},
        {"role": "user", "content": "current"},
    ]


def freeze(k, history):
    return k.append_extended_candidate_response(
        history, {"content": " A1 exact \n", "reasoning_content": "current R1"}
    )


@pytest.mark.parametrize("enabled",[False, True])
def test_freeze_flag_and_answer_authority(enabled):
    k = load(enabled)
    history = bridge_history()
    scope = {"stage1_frozen": False, "bridge_messages": [], "pending_state": None}
    token = k._AGENTIC_DELAY_R2_SCOPE.set(scope)
    try:
        assert freeze(k, history) == " A1 exact \n"
        assert ("reasoning_content" in history[1]) is enabled
        assert history[-1]["content"] == " A1 exact \n"
        assert history[-1]["reasoning_content"] == "current R1"
        if enabled:
            assert scope["stage1_frozen"]
            k._agentic_finish_delayed_one_hop(history)
            assert "reasoning_content" not in history[1]
            assert "reasoning" not in history[1]
            assert "_jack_agentic_one_hop_r2" not in history[1]
    finally:
        k._AGENTIC_DELAY_R2_SCOPE.reset(token)


@pytest.mark.parametrize("cache_enabled",[False, True])
def test_previous_r2_reaches_backend_stage2_only_when_enabled(cache_enabled):
    async def exercise(enabled):
        k = load(enabled, cache_enabled)
        history = bridge_history()
        scope = {"stage1_frozen": False, "bridge_messages": [], "pending_state": None}
        token = k._AGENTIC_DELAY_R2_SCOPE.set(scope)
        backend = k.OpenAICompatibleBackend(k.CFG)
        payloads = []
        def respond(request):
            body = json.loads(request.content)
            payloads.append(body)
            return httpx.Response(200, json={
                "choices": [{"message": {"role": "assistant", "content": "M"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
            })
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async def model(): return "test-model"
        backend.resolve_model = model
        try:
            freeze(k, history)
            await backend.chat(messages=history, secondary_system="",
                               profile=k.STAGES["extended_reflection"],
                               tool_choice="auto")
            assert len(payloads) == 1
            model_messages = payloads[0]["messages"]
            bridge = next(m for m in model_messages if m.get("content") == "previous memory")
            assert ("reasoning_content" in bridge) is enabled
            if cache_enabled:
                assert model_messages[-1]["content"].startswith(k.AGENTIC_36_STAGE2_PROMPT)
            assert k.AGENTIC_STAGE1_PROMPT == (
                "Reasoning effort is set to xhigh. Please think carefully through the task, "
                "validate key assumptions, consider plausible alternatives, and prioritize "
                "correctness, consistency, and clarity in the final answer."
            )
            assert k.AGENTIC_36_STAGE2_PROMPT == "Generate a detailed summary of why you came to this conclusion."
        finally:
            await backend._client.aclose()
            k._AGENTIC_DELAY_R2_SCOPE.reset(token)

    asyncio.run(exercise(False))
    asyncio.run(exercise(True))


def test_terminal_cleanup_is_transaction_scoped():
    async def exercise():
        k = load(True)
        h1 = bridge_history()
        h2 = bridge_history()
        h2[1]["reasoning_content"] = "other transaction bridge"
        scope = {"stage1_frozen": False, "bridge_messages": [], "pending_state": None}
        token = k._AGENTIC_DELAY_R2_SCOPE.set(scope)
        try:
            freeze(k, h1)
            await k.KERNEL._agentic_phase3g_close_scope(token)
            assert "reasoning_content" not in h1[1]
            assert h2[1]["reasoning_content"] == "other transaction bridge"
        except BaseException:
            if k._AGENTIC_DELAY_R2_SCOPE.get() is scope:
                k._AGENTIC_DELAY_R2_SCOPE.reset(token)
            raise
    asyncio.run(exercise())


def test_stage1_suspension_does_not_retire_bridge():
    async def exercise():
        k = load(True)
        h = bridge_history()
        scope = {"stage1_frozen": False, "bridge_messages": [], "pending_state": None}
        token = k._AGENTIC_DELAY_R2_SCOPE.set(scope)
        await k.KERNEL._agentic_phase3g_close_scope(token)
        assert h[1]["reasoning_content"] == "previous R2"
    asyncio.run(exercise())


def test_pending_checkpoint_retired_on_terminal_scope():
    async def exercise():
        k = load(True)
        h = bridge_history()
        scope = {"stage1_frozen": False, "bridge_messages": [], "pending_state": None}
        token = k._AGENTIC_DELAY_R2_SCOPE.set(scope)
        freeze(k, h)
        checkpoint = k.PendingToolResume(
            resume_id="phase3g-test",
            stage_key="extended_initial",
            history=list(h),
            secondary_system="",
            usage={},
            tools=None,
            tool_choice="auto",
            expected_tool_call_ids=("tool-3g",),
            created_at=0.0,
        )
        k.KERNEL._pending_tool_resumes["tool-3g"] = checkpoint
        scope["pending_state"] = checkpoint
        await k.KERNEL._agentic_phase3g_close_scope(token)
        assert "tool-3g" not in k.KERNEL._pending_tool_resumes
        assert "reasoning_content" not in checkpoint.history[1]
    asyncio.run(exercise())


def test_successful_commit_retires_bridge_and_preserves_memory():
    async def exercise():
        k = load(True)
        history = bridge_history()
        scope = {"stage1_frozen": False, "bridge_messages": [], "pending_state": None}
        token = k._AGENTIC_DELAY_R2_SCOPE.set(scope)
        try:
            answer = freeze(k, history)
            committed = await k.KERNEL._complete_commit(
                history, "", {}, answer, "memory with unverified hypothesis labeled hypothetical"
            )
            assert committed.frozen_answer == answer
            assert "memory with unverified hypothesis" in committed.frozen_xml
            assert "reasoning_content" not in scope["bridge_messages"][0]
            assert history == []
        finally:
            k._AGENTIC_DELAY_R2_SCOPE.reset(token)
    asyncio.run(exercise())


def test_degraded_commit_retires_bridge_preserves_a1():
    k = load(True)
    history = bridge_history()
    scope = {"stage1_frozen": False, "bridge_messages": [], "pending_state": None}
    token = k._AGENTIC_DELAY_R2_SCOPE.set(scope)
    try:
        answer = freeze(k, history)
        result = k.KERNEL._agentic_degraded_result(history, {}, answer, "stage2 rejected")
        assert result.content == answer
        assert history == []
        assert "reasoning_content" not in scope["bridge_messages"][0]
    finally:
        k._AGENTIC_DELAY_R2_SCOPE.reset(token)


def test_no_historical_r2_accumulation():
    k = load(True)
    first = bridge_history()
    first[1]["reasoning_content"] = "R2 very old"
    first[1]["_jack_agentic_one_hop_r2"] = True
    k._agentic_retire_consumed_one_hop(first)
    assert "reasoning_content" not in first[1]
    assert not first[1].get("_jack_agentic_one_hop_r2")


def test_previous_speculation_is_not_authored_as_verified_memory_by_host():
    """Authority regression: Stage 2 output stays attributed to the model.

    Actual resistance to retrospective contamination requires a separate
    Qwen/LM Studio empirical evaluation; no deterministic test of an arbitrary
    generated M can prove its semantic fidelity.
    """
    async def exercise():
        k = load(True)
        history = bridge_history()
        history[1]["reasoning_content"] = "SPECULATION: output file exists (not checked)"
        scope = {"stage1_frozen": False, "bridge_messages": [], "pending_state": None}
        token = k._AGENTIC_DELAY_R2_SCOPE.set(scope)
        try:
            answer = freeze(k, history)
            completed = await k.KERNEL._complete_commit(
                history, "", {}, answer,
                "Earlier file-existence claim was speculative; no tool verified it."
            )
            assert "no tool verified it" in completed.frozen_xml
            assert "output file exists" not in completed.frozen_xml
            assert "reasoning_content" not in scope["bridge_messages"][0]
        finally:
            k._AGENTIC_DELAY_R2_SCOPE.reset(token)
    asyncio.run(exercise())
