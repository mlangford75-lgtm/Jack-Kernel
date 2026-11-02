"""Stage-2 causal-paper experiment: only trailing suffix changes.

No model generation is used. Check both streaming and nonstreaming requests
against the baseline to prevent prefix, tool, or stage-control regression.
"""
import asyncio
import importlib.util
import json
import sys
import uuid
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


def kernel(monkeypatch, tmp_path, *, enabled):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_AGENTIC_TRANSACTION_LINKS", "1")
    monkeypatch.setenv("JACK_AGENTIC_TASK_ANCHOR", "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT", "1")
    monkeypatch.setenv("JACK_AGENTIC_DIFFERENTIAL_MEMORY", "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_FINAL_PAPER", "1" if enabled else "0")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_stage2_final_paper_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    obj = importlib.util.module_from_spec(spec)
    sys.modules[name] = obj
    spec.loader.exec_module(obj)
    return obj


def history():
    return [
        {"role": "user", "content": "Previous unrelated project"},
        {"role": "assistant", "content": "Historical memory"},
        {"role": "user", "content": "Make the clock face gold."},
        {
            "role": "assistant",
            "content": "Edited index.html with gold colors. Visual check unavailable.",
            "reasoning_content": "Reviewed CSS. Used edit; result reported success but no browser verification.",
        },
    ]


def tools():
    return [{"type": "function", "function": {
        "name": "edit", "description": "Edit a file",
        "parameters": {"type": "object", "properties": {}},
    }}]


async def capture(k, *, stream):
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        if stream:
            data = "\n\n".join([
                'data: {"choices":[{"index":0,"delta":{"content":"retrospective"},"finish_reason":null}]}',
                'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}',
                "data: [DONE]",
            ]) + "\n\n"
            return httpx.Response(200, text=data, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "retrospective"}, "finish_reason": "stop"}],
            "usage": {},
        })

    backend = k.OpenAICompatibleBackend(k.CFG)
    await backend._client.aclose()
    backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))

    async def model():
        return "test-model"

    backend.resolve_model = model
    try:
        args = {
            "messages": history(),
            "secondary_system": "",
            "profile": k.STAGES["extended_reflection"],
            "tools": tools(),
            "tool_choice": "auto",
        }
        if stream:
            async for _ in backend.chat_stream(**args):
                pass
        else:
            await backend.chat(**args)
    finally:
        await backend._client.aclose()
    assert len(calls) == 1
    return calls[0]


@pytest.mark.parametrize("stream", [True, False])
def test_only_trailing_suffix_changes(monkeypatch, tmp_path, stream):
    baseline = kernel(monkeypatch, tmp_path, enabled=False)
    original = asyncio.run(capture(baseline, stream=stream))
    candidate = kernel(monkeypatch, tmp_path, enabled=True)
    revised = asyncio.run(capture(candidate, stream=stream))

    assert original["messages"][:-1] == revised["messages"][:-1]
    original_tail = original["messages"].pop()
    revised_tail = revised["messages"].pop()
    assert original == revised
    assert original_tail["role"] == revised_tail["role"] == "user"
    assert original_tail["content"].startswith(baseline.AGENTIC_36_STAGE2_PROMPT)
    assert revised_tail["content"] == (
        candidate.AGENTIC_36_STAGE2_PROMPT + "\n\n" +
        candidate._AGENTIC_STAGE2_FINAL_PAPER_CONTINUATION
    )
    assert "most recent genuine user request" in revised_tail["content"]
    assert "everything generated AFTER that user" in revised_tail["content"]
    assert "tool-reported success alone does not verify on-disk state" in revised_tail["content"]
    assert "label unsupported causal" in revised_tail["content"]
    assert revised["messages"][-1]["reasoning_content"] == history()[-1]["reasoning_content"]
    assert revised["tools"] == tools()
    assert revised["chat_template_kwargs"]["preserve_thinking"] is True
    assert candidate.STAGES["extended_reflection"].allow_tools is False
    assert candidate.AGENTIC_36_STAGE2_PROMPT == "Generate a detailed summary of why you came to this conclusion."
    assert candidate.AGENTIC_STAGE1_PROMPT.startswith("Reasoning effort is set to xhigh.")


def test_baseline_default_off(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path, enabled=False)
    assert k._stage_continuation(k.STAGES["extended_reflection"], history()) == k._AGENTIC_STAGE2_LINKED_CONTINUATION
    assert k.AGENTIC_STAGE2_FINAL_PAPER_EXPERIMENT is False


def test_final_paper_overrides_differential_not_stacks(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path, enabled=True)
    assert k._stage_continuation(k.STAGES["extended_reflection"], history()) == k._AGENTIC_STAGE2_FINAL_PAPER_CONTINUATION
    assert k._AGENTIC_DIFFERENTIAL_MEMORY_SENTENCE not in k._stage_continuation(k.STAGES["extended_reflection"], history())


def test_refinement_is_evidence_bounded_without_changing_immutable_prompts(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path, enabled=True)
    instruction = k._stage_continuation(k.STAGES["extended_reflection"], history())
    assert "BEFORE the immediately preceding" in instruction
    assert "BEFORE this instruction" in instruction
    assert "current Stage-1 native reasoning" in instruction
    assert "tool calls, returned tool results" in instruction
    assert "Generated code is not a file write" in instruction
    assert "corresponding check appears in this turn's record" in instruction
    assert "do not attribute their tool actions" in instruction
    assert "internal motives" in instruction
    assert k.AGENTIC_STAGE1_PROMPT == (
        "Reasoning effort is set to xhigh. Please think carefully through the task, "
        "validate key assumptions, consider plausible alternatives, and prioritize "
        "correctness, consistency, and clarity in the final answer."
    )
    assert k.AGENTIC_36_STAGE2_PROMPT == "Generate a detailed summary of why you came to this conclusion."
