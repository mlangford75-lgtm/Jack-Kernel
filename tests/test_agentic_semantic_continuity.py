from __future__ import annotations

import asyncio
import copy
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
        # Snapshot the exact provider-facing request at call time. Jack clears
        # completed transient Agentic history after the frozen commit, so storing
        # the live list by reference would make a post-commit test inspect an
        # intentionally emptied history rather than what Stage 2 actually saw.
        self.calls.append(copy.deepcopy(kwargs))
        if not self.items:
            raise AssertionError("FakeBackend ran out of responses")
        return self.items.pop(0)


def test_agentic_stage2_contract_is_selection_first_and_user_prompt_guided():
    mod = load_agentic()
    prompt = mod.AGENTIC_36_STAGE2_PROMPT

    assert "SELECTION COMES BEFORE TAGGING" in prompt
    assert "Use the exact user prompts to define the task scope, distinctions, constraints, and requested cardinality" in prompt
    assert "Do not decide importance in the abstract" in prompt
    assert "already adequately preserved by the exact user prompts or the exact frozen answer" in prompt
    assert "meaningful alternative" in prompt
    assert "Label any retained alternative explicitly as not selected" in prompt
    assert "semantic continuity, not semantic exhaustiveness" in prompt

    for tag in ("<workspace_state>", "<decision_state>", "<unresolved>", "<reevaluate>"):
        assert tag in prompt

    assert "NONE is a valid first-class result" in prompt
    assert "OUTPUT-SUPPRESSION BOUNDARY" in prompt
    assert "<anchor_fact ID=" in prompt
    assert "<deterministic_check>" in prompt

    # Audit/falsification schemas and the superseded free-form tags are not Agentic Stage 2.
    for old_tag in (
        "<continuity>", "<evidence>", "<grounding>", "<verification>",
        "<challenge>", "<audit>", "<grounded_source>", "<pitfall_check>",
    ):
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
        "<workspace_state>NONE</workspace_state>\n"
        "<decision_state>REJECTED: Approach B — violates the latency constraint.</decision_state>\n"
        "<unresolved>NONE</unresolved>\n"
        "<reevaluate>NONE</reevaluate>\n"
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
    assert result.frozen_xml == mod.freeze_agentic_xml_stage_output(xml)
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
        "<workspace_state>NONE</workspace_state>\n"
        "<decision_state>ALTERNATIVE: B becomes relevant only if the latency constraint is relaxed.</decision_state>\n"
        "<unresolved>Integration behavior has not been tested.</unresolved>\n"
        "<reevaluate>NONE</reevaluate>\n"
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


def test_agentic_contract_does_not_promote_surplus_brainstorming_into_durable_alternatives():
    mod = load_agentic()
    prompt = mod.AGENTIC_36_STAGE2_PROMPT

    assert "scope, distinctions, and cardinality define the default retention boundary" in prompt
    assert "surplus branches outside the user's requested scope/cardinality" in prompt
    assert "If the user asked for two candidate answers but Stage 1 brainstormed three or more" in prompt
    assert "do not automatically preserve every rejected branch" in prompt
    assert "contextual restatements used only to explain another retained item" in prompt
    assert "selected-answer recaps used only to frame an alternative" in prompt


def test_agentic_xml_canonicalizer_enforces_mandatory_skeleton_without_semantic_invention():
    mod = load_agentic()
    raw = (
        "<Jack XML>\n"
        "<decision_state>REJECTED: Redis-backed queue — external service conflicts with local-first.</decision_state>\n"
        "<anchor_fact ID=\"HEAD_SHA\">abc123</anchor_fact>\n"
        "<pitfall_check>must not survive Agentic canonicalization</pitfall_check>\n"
        "</Jack XML>"
    )

    frozen = mod.freeze_agentic_xml_stage_output(raw)

    assert frozen == (
        "<Jack XML>\n"
        "<workspace_state>\nNONE\n</workspace_state>\n"
        "<decision_state>\nREJECTED: Redis-backed queue — external service conflicts with local-first.\n</decision_state>\n"
        "<anchor_fact ID=\"HEAD_SHA\">abc123</anchor_fact>\n"
        "<unresolved>\nNONE\n</unresolved>\n"
        "<reevaluate>\nNONE\n</reevaluate>\n"
        "</Jack XML>"
    )
    assert "<pitfall_check>" not in frozen


def test_agentic_xml_canonicalizer_rejects_unrecognized_stage2_surface():
    mod = load_agentic()

    assert mod.freeze_agentic_xml_stage_output(
        "<Jack XML><pitfall_check>legacy-only content</pitfall_check></Jack XML>"
    ) == ""
