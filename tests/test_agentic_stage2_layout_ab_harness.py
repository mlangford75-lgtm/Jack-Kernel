"""Structural regression for the fixed-evidence Stage-2 A/B harness.

No LM Studio, user tools, or model inference required.
"""
import asyncio
from pathlib import Path

import pytest

import agentic_stage2_layout_ab as ab

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("layout", [0, 1])
@pytest.mark.parametrize("case", list(ab.builtin_fixtures()))
def test_fixed_evidence_layout_and_preserve_thinking(layout, case):
    fixture = ab.builtin_fixtures()[case]
    model = ab.load_jack(ROOT, layout, "test-model")
    output = asyncio.run(ab.one_stage2(model, fixture, True, "test-model"))
    payload = output["mock_request"]

    assert payload["stream"] is True
    assert payload["messages"][0]["role"] == "system"
    expected = model.AGENTIC_STAGE1_PROMPT if layout else model.AGENTIC_36_STAGE2_PROMPT
    assert payload["messages"][0]["content"] == expected
    assert ab.BLOCK not in payload["messages"][0]["content"]
    assert payload["messages"][-2]["content"] == fixture["messages"][-1]["content"]
    assert payload["messages"][-2].get("reasoning_content") == fixture["messages"][-1].get("reasoning_content")
    assert payload["messages"][-1]["role"] == "user"
    assert payload["messages"][-1]["content"]
    assert payload.get("chat_template_kwargs", {}).get("preserve_thinking") is True
    assert "tools" not in payload
    assert output["tool_calls_attempted"] == 0
    assert output["memory"] == "mock M"
    assert output["native_r2"] == "mock R2"
