from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "jack_kernel.py"


def load_agentic():
    os.environ["JACK_REASONING_LEVEL"] = "agentic"
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "off"
    os.environ["JACK_BACKEND_MODEL"] = "test-model"
    os.environ["JACK_BACKEND_PROFILE"] = "lmstudio"
    name = f"jack_agentic_continuity_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def response(*, content="", reasoning=""):
    message = {"role": "assistant", "content": content}
    if reasoning:
        message["reasoning_content"] = reasoning
    return {
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        },
    }


class FakeBackend:
    def __init__(self, *items):
        self.items = list(items)
        self.calls = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        if not self.items:
            raise AssertionError("FakeBackend ran out of responses")
        return self.items.pop(0)


def test_agentic_stage2_contract_is_selection_first_and_user_prompt_guided():
    mod = load_agentic()
    prompt = mod.AGENTIC_36_STAGE2_PROMPT

    assert "SELECTION COMES BEFORE TAGGING" in prompt
    assert "Use those exact user prompts to decide what matters moving forward" in prompt
    assert "Do not decide importance in the abstract" in prompt
    assert "already adequately preserved by the exact user prompts or the exact frozen answer" in prompt
    assert "meaningful alternative" in prompt
    assert "label it explicitly as an alternative" in prompt
    assert "semantic continuity, not semantic exhaustiveness" in prompt

    for tag in ("<continuity>", "<evidence>", "<unresolved>", "<reevaluate>"):
        assert tag in prompt

    # The previous rigid audit-form schema must not remain the Stage-2 contract.
    for old_tag in ("<grounding>", "<verification>", "<challenge>", "<audit>"):
        assert old_tag not in prompt


def test_agentic_stage2_receives_exact_user_prompt_and_stage1_reasoning():
    mod = load_agentic()
    exact_user = "Develop two approaches, choose one, output only the winner.\n  Keep this spacing exact."
    stage1_reasoning = (
        "Approach A is preferable. Approach B was fully developed but not selected "
        "because it violates the user's latency constraint."
    )
    frozen_a1 = "Selected answer: Approach A."
    xml = (
        "<Jack XML>\n"
        "<continuity>Selected A. Alternative B was developed but not selected "
        "because it violates the latency constraint.</continuity>\n"
        "</Jack XML>"
    )

    backend = FakeBackend(
        response(content=frozen_a1, reasoning=stage1_reasoning),
        response(content=xml, reasoning="selection-first semantic consolidation"),
    )
    jack = mod.JackQwenKernel(backend, mod.CFG)

    result = asyncio.run(jack._prepare_commit({
        "messages": [{"role": "user", "content": exact_user}],
    }))

    assert isinstance(result, mod.PreparedCommit)
    assert result.frozen_answer == frozen_a1
    assert result.frozen_xml == xml
    assert len(backend.calls) == 2

    stage2_call = backend.calls[1]
    assert stage2_call["tools"] is None
    assert stage2_call["tool_choice"] is None
    assert stage2_call["profile"].name == "Agentic native pass 2"
    assert "SELECTION COMES BEFORE TAGGING" in stage2_call["profile"].prompt

    stage2_messages = stage2_call["messages"]
    user_messages = [
        item for item in stage2_messages
        if isinstance(item, dict) and item.get("role") == "user"
    ]
    assert any(item.get("content") == exact_user for item in user_messages)

    candidate_messages = [
        item for item in stage2_messages
        if isinstance(item, dict)
        and item.get("role") == "assistant"
        and item.get("_jack_extended_candidate_response")
    ]
    assert len(candidate_messages) == 1
    candidate = candidate_messages[0]
    assert candidate["content"] == frozen_a1
    assert candidate["reasoning_content"] == stage1_reasoning


def test_agentic_completed_turn_gc_preserves_exact_user_and_semantic_delta():
    mod = load_agentic()

    exact_user = "First request\n  preserve my exact formatting."
    frozen_a1 = "Visible answer for the user."
    xml = (
        "<Jack XML>\n"
        "<continuity>Alternative B remains relevant only if the user relaxes "
        "the latency constraint.</continuity>\n"
        "<unresolved>Integration behavior has not been tested.</unresolved>\n"
        "</Jack XML>"
    )
    committed = f"{xml}\n\n{frozen_a1}"

    messages = [
        {"role": "user", "content": exact_user},
        {
            "role": "assistant",
            "content": committed,
            "reasoning_content": "raw reasoning that must be retired",
        },
        {"role": "user", "content": "Now continue from that work."},
    ]

    compact = mod._compact_agentic_completed_capsules(messages)

    assert compact is not None
    assert compact[0]["role"] == "user"
    assert compact[0]["content"] == exact_user
    assert compact[1]["role"] == "assistant"
    assert compact[1]["content"] == committed
    assert "reasoning_content" not in compact[1]
    assert compact[-1]["content"] == "Now continue from that work."
