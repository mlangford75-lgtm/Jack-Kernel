"""A/B contract for the one-sentence differential Agentic memory experiment.

A/B must change only the final Stage-2 user continuation text. All frozen
prompts, stage history, native reasoning, tool schemas, streaming policy,
source user messages and cache prefix must be byte-identical.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import uuid

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
SENTENCE = (
    "Prioritize important reasoning, decisions, tool evidence, and unresolved "
    "details that are not already clear from the completed answer."
)


def load_kernel(monkeypatch, tmp_path, *, experiment):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_AGENTIC_TRANSACTION_LINKS", "1")
    monkeypatch.setenv("JACK_AGENTIC_TASK_ANCHOR", "0")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT", "1")
    monkeypatch.setenv("JACK_AGENTIC_DIFFERENTIAL_MEMORY", "1" if experiment else "0")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    module_name = "jack_differential_memory_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "jack_kernel.py")
    kernel = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = kernel
    spec.loader.exec_module(kernel)
    return kernel


def history():
    return [
        {"role": "user", "content": "Prior work"},
        {"role": "assistant", "content": "Retained prior memory"},
        {"role": "assistant", "content": "Prior answer"},
        {"role": "user", "content": "Make the clock gold and verify the HTML"},
        {
            "role": "assistant",
            "content": "Updated clock.html with a gold face.",
            "reasoning_content": "Used gold CSS gradients; write returned success; browser rendering unverified.",
        },
    ]


def tools():
    return [
        {"type": "function", "function": {
            "name": "write",
            "description": "Write contents to a file.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
        }},
    ]


async def capture_payload(kernel, *, stream):
    payloads = []

    def respond(request):
        data = json.loads(request.content)
        payloads.append(data)
        if stream:
            body = (
                'data: {"choices":[{"index":0,"delta":{"content":"Memory"},"finish_reason":null}]}\\n\\n'
                'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\\n\\n'
                'data: [DONE]\\n\\n'
            )
            return httpx.Response(200, text=body.replace("\\\\n", "\\n"),
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "Memory"}, "finish_reason": "stop"}],
            "usage": {},
        })

    backend = kernel.OpenAICompatibleBackend(kernel.CFG)
    await backend._client.aclose()
    backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))

    async def resolve_model():
        return "test-model"

    backend.resolve_model = resolve_model
    kwargs = {
        "messages": history(), "secondary_system": "",
        "profile": kernel.STAGES["extended_reflection"],
        "tools": tools(), "tool_choice": "auto",
    }
    try:
        if stream:
            async for _ in backend.chat_stream(**kwargs):
                pass
        else:
            await backend.chat(**kwargs)
    finally:
        await backend._client.aclose()
    assert len(payloads) == 1
    return payloads[0]


@pytest.mark.parametrize("stream", [False, True])
def test_only_trailing_stage2_instruction_differs(monkeypatch, tmp_path, stream):
    control = load_kernel(monkeypatch, tmp_path, experiment=False)
    a = asyncio.run(capture_payload(control, stream=stream))
    candidate = load_kernel(monkeypatch, tmp_path, experiment=True)
    b = asyncio.run(capture_payload(candidate, stream=stream))

    assert a["stream"] is b["stream"] is stream
    assert a["messages"][:-1] == b["messages"][:-1]
    assert a["messages"][-1]["role"] == b["messages"][-1]["role"] == "user"
    assert b["messages"][-1]["content"] == a["messages"][-1]["content"] + " " + SENTENCE

    a_tail = a["messages"].pop()
    b_tail = b["messages"].pop()
    assert a == b  # Exactly same model, sampling, tools, thinking, messages and flags.
    assert a_tail["role"] == b_tail["role"]
    assert a["messages"][0]["content"] == control.AGENTIC_STAGE1_PROMPT
    assert a["messages"][-1]["reasoning_content"] == history()[-1]["reasoning_content"]
    assert a["tools"] == tools()
    assert a["chat_template_kwargs"]["preserve_thinking"] is True
    assert control.STAGES["extended_reflection"].allow_tools is False
    assert candidate.STAGES["extended_reflection"].allow_tools is False


def test_baseline_default_and_frozen_prompts_unchanged(monkeypatch, tmp_path):
    monkeypatch.delenv("JACK_AGENTIC_DIFFERENTIAL_MEMORY", raising=False)
    k = load_kernel(monkeypatch, tmp_path, experiment=False)
    assert k._AGENTIC_STAGE2_LINKED_CONTINUATION.endswith("Write the retained details directly.")
    assert k._stage_continuation(k.STAGES["extended_reflection"], history()) == (
        k._AGENTIC_STAGE2_LINKED_CONTINUATION
    )
    assert k.AGENTIC_36_STAGE2_PROMPT == "Generate a detailed summary of why you came to this conclusion."
    assert k.AGENTIC_STAGE1_PROMPT.startswith("Reasoning effort is set to xhigh.")
    assert k._agentic_cache_append_enabled(k.STAGES["extended_reflection"])
    assert not k.AGENTIC_DIFFERENTIAL_MEMORY_EXPERIMENT


def test_one_sentence_no_model_facing_ids_and_no_stage1_mutation(monkeypatch, tmp_path):
    k = load_kernel(monkeypatch, tmp_path, experiment=True)
    h = history()
    before = json.loads(json.dumps(h))
    stage1 = k.BACKEND._stage_messages_for_profile(h[:-1], k.STAGES["extended_initial"])
    stage2 = k.BACKEND._stage_messages_for_profile(h, k.STAGES["extended_reflection"])
    assert stage2[:len(stage1)] == stage1
    assert h == before
    suffix = k._stage_continuation(k.STAGES["extended_reflection"], h)
    assert suffix == k._AGENTIC_STAGE2_LINKED_CONTINUATION + " " + SENTENCE
    assert "jack-turn" not in suffix and "[JACK LINK" not in suffix
    assert k.STAGES["extended_reflection"].allow_tools is False
