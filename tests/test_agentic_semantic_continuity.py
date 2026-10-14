from __future__ import annotations

import asyncio
import copy
import importlib.util
import os
import re
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


def test_agentic_stage2_contract_exposes_fixed_semantic_schema():
    mod = load_agentic()
    prompt = mod.AGENTIC_36_STAGE2_PROMPT

    assert mod._AGENTIC_REQUIRED_XML_TAGS == (
        "workspace_state",
        "decision_state",
        "unresolved",
        "reevaluate",
    )
    for tag in mod._AGENTIC_REQUIRED_XML_TAGS:
        assert f"<{tag}>" in prompt
        assert f"</{tag}>" in prompt

    # Optional cards are part of the schema, but are not required on every turn.
    assert "<anchor_fact" in prompt
    assert "<deterministic_check>" in prompt
    assert "NONE" in prompt


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


def _tag_value(xml: str, tag: str) -> str:
    match = re.search(
        rf"<{tag}>\s*(.*?)\s*</{tag}>",
        xml,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group(1).strip()


def test_agentic_xml_canonicalizer_enforces_mandatory_skeleton_without_semantic_invention():
    mod = load_agentic()
    raw = (
        "<Jack XML>\n"
        "<continuity>legacy continuity</continuity>\n"
        "<evidence>legacy evidence</evidence>\n"
        "<grounding>legacy grounding</grounding>\n"
        "<verification>legacy verification</verification>\n"
        "<challenge>legacy challenge</challenge>\n"
        "<audit>legacy audit</audit>\n"
        "<grounded_source>legacy grounded source</grounded_source>\n"
        "<pitfall_check>legacy pitfall</pitfall_check>\n"
        "<decision_state>REJECTED: Redis-backed queue — external service conflicts with local-first.</decision_state>\n"
        "<anchor_fact ID=\"HEAD_SHA\">abc123</anchor_fact>\n"
        "</Jack XML>"
    )

    frozen = mod.freeze_agentic_xml_stage_output(raw)

    assert frozen.startswith("<Jack XML>")
    assert frozen.endswith("</Jack XML>")
    assert _tag_value(frozen, "workspace_state") == "NONE"
    assert _tag_value(frozen, "decision_state") == (
        "REJECTED: Redis-backed queue — external service conflicts with local-first."
    )
    assert _tag_value(frozen, "unresolved") == "NONE"
    assert _tag_value(frozen, "reevaluate") == "NONE"
    assert '<anchor_fact ID="HEAD_SHA">abc123</anchor_fact>' in frozen

    positions = [frozen.index(f"<{tag}>") for tag in mod._AGENTIC_REQUIRED_XML_TAGS]
    assert positions == sorted(positions)

    for legacy_tag in (
        "continuity",
        "evidence",
        "grounding",
        "verification",
        "challenge",
        "audit",
        "grounded_source",
        "pitfall_check",
    ):
        assert f"<{legacy_tag}" not in frozen


def test_agentic_xml_canonicalizer_preserves_optional_cards_and_normalizes_required_order():
    mod = load_agentic()
    raw = (
        "<Jack XML>\n"
        "<reevaluate>NONE</reevaluate>\n"
        "<anchor_fact ID=\"PORT\">8001</anchor_fact>\n"
        "<deterministic_check>Tool: unit-test\nResult: PASS\nStatus: VERIFIED\nScope: parser only</deterministic_check>\n"
        "<workspace_state>Milestone: validate parser.</workspace_state>\n"
        "<unresolved></unresolved>\n"
        "<decision_state>NONE</decision_state>\n"
        "</Jack XML>"
    )

    frozen = mod.freeze_agentic_xml_stage_output(raw)

    assert _tag_value(frozen, "workspace_state") == "Milestone: validate parser."
    assert _tag_value(frozen, "decision_state") == "NONE"
    assert _tag_value(frozen, "unresolved") == "NONE"
    assert _tag_value(frozen, "reevaluate") == "NONE"
    assert '<anchor_fact ID="PORT">8001</anchor_fact>' in frozen
    assert "<deterministic_check>" in frozen
    assert "Status: VERIFIED" in frozen

    required_positions = [frozen.index(f"<{tag}>") for tag in mod._AGENTIC_REQUIRED_XML_TAGS]
    assert required_positions == sorted(required_positions)
    assert frozen.index("<decision_state>") < frozen.index("<anchor_fact")
    assert frozen.index("<anchor_fact") < frozen.index("<deterministic_check>")
    assert frozen.index("<deterministic_check>") < frozen.index("<unresolved>")


def test_agentic_xml_canonicalizer_rejects_unrecognized_stage2_surface():
    mod = load_agentic()

    assert mod.freeze_agentic_xml_stage_output(
        "<Jack XML><pitfall_check>legacy-only content</pitfall_check></Jack XML>"
    ) == ""
