"""Only test the projection: never infer behavioral success from mock results."""
import asyncio
import hashlib
import json
from pathlib import Path

import pytest

import agentic_stage2_layout_ab as base
import agentic_stage2_r1_boundary_ab as probe

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("case", ["conflicting_current_turn", "tool_receipt_grounding"])
@pytest.mark.parametrize("variant", probe.VARIANTS)
def test_r1_projection_is_experimental_and_keeps_a1_exact(case, variant):
    original = base.builtin_fixtures()[case]
    original_snapshot = json.dumps(original, ensure_ascii=False, sort_keys=True)
    fixture = probe.transform(original, variant)
    assert json.dumps(original, ensure_ascii=False, sort_keys=True) == original_snapshot
    assert fixture["messages"][-1]["content"] == original["messages"][-1]["content"]
    assert fixture["_host_raw_r1_sha256"] == hashlib.sha256(
        original["messages"][-1]["reasoning_content"].encode()
    ).hexdigest()

    jack = base.load_jack(ROOT, 0, "test-model")
    output = asyncio.run(probe.invoke(jack, fixture, True, "test-model"))
    request = output["mock_request"]
    assert request["messages"][0]["content"] == jack.AGENTIC_36_STAGE2_PROMPT
    assert request["messages"][-2]["content"] == original["messages"][-1]["content"]
    assert request["messages"][-1]["role"] == "user"
    assert request["stream"] is True
    assert request["chat_template_kwargs"]["preserve_thinking"] is True
    assert "tools" not in request
    rendered = json.dumps(request["messages"])
    if variant == "native":
        assert request["messages"][-2]["reasoning_content"] == original["messages"][-1]["reasoning_content"]
    elif variant == "without_r1":
        assert original["messages"][-1]["reasoning_content"] not in rendered
    elif variant == "documentary_r1":
        assert original["messages"][-1]["reasoning_content"] in request["messages"][-3]["content"]
        assert "reasoning_content" not in request["messages"][-2]
    assert output["native_r2"] == "mock R2"
    assert output["memory"] == "mock M"
