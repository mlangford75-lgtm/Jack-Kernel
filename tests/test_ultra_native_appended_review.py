"""Ultra: two X-High reasoning inferences, one final response, no Stage 2/pruning."""
import asyncio
import importlib.util
import json
import sys
import uuid
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(monkeypatch, tmp_path, mode="ultra"):
    monkeypatch.setenv("JACK_REASONING_LEVEL", mode)
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    monkeypatch.setenv("JACK_LOOP_DETECTOR", "0")
    name = "ultra_native_review_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def result(content, reasoning):
    return {
        "choices": [{"index": 0, "message": {
            "role": "assistant", "content": content, "reasoning_content": reasoning,
        }, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 40, "completion_tokens": 8, "total_tokens": 48},
    }


def test_mode_placement_and_reasoning_contract(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    assert k.ULTRA_REVIEW_MODE and not k.ULTRA_MODE and not k.AGENTIC_MODE
    assert list(k.REASONING_PROFILES).index("x-high") + 1 == list(k.REASONING_PROFILES).index("ultra")
    assert k.REASONING_PROFILES["ultra"]["label"] == "Ultra"
    assert k.STAGES["thesis"].reasoning_effort == "xhigh"
    assert k.STAGES["thesis"].thinking
    assert k.STAGES["thesis"].allow_tools
    assert k.STAGES["thesis"].force_preserve_thinking
    assert k._runtime_identity_details()["mode"] == "ultra"
    assert k._runtime_identity_details()["flow"] == ["thesis", "thesis"]
    assert k.AGENTIC_STAGE1_VERIFICATION_PROMPT in k.ULTRA_REVIEW_TRIGGER
    assert "re-verify the latest reasoning" in k.ULTRA_REVIEW_TRIGGER
    assert "alignment with the instructions and user request" in k.ULTRA_REVIEW_TRIGGER
    assert not k.AGENTIC_SOURCE_ONLY_WORKING_STATE


def test_ultra_review_is_host_owned_and_does_not_modify_history(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Original request"}]
    original = json.dumps(h)
    assert not k._ultra_review_pending(h)
    k._ultra_begin_review(h, result("Provisional draft", "FIRST_REASONING"))
    assert json.dumps(h[:1]) == original
    assert k.active_response_target(h)["content"] == "Original request"
    assert k._ultra_review_pending(h)
    assert h[-2]["content"] == ""
    assert h[-2]["_jack_ultra_provisional_answer"] == "Provisional draft"
    assert h[-2]["reasoning_content"] == "FIRST_REASONING"
    assert h[-1]["_jack_internal_ultra_review_trigger"]
    assert k.AGENTIC_STAGE1_VERIFICATION_PROMPT in h[-1]["content"]
    assert k._ultra_combined_reasoning(h, result("final", "SECOND_REASONING")["choices"][0]["message"]) == "FIRST_REASONING\n\nSECOND_REASONING"
    with pytest.raises(k.HTTPException):
        k._ultra_begin_review(h, result("again", "thinking"))


@pytest.mark.parametrize("streaming", [False, True])
def test_same_system_prefix_xhigh_and_final_only(monkeypatch, tmp_path, streaming):
    async def run():
        k = load(monkeypatch, tmp_path)
        observed = []

        def responder(request):
            payload = json.loads(request.content)
            observed.append(payload)
            first = len(observed) == 1
            content = "DO_NOT_SHOW_PROVISIONAL" if first else "Final verified answer."
            reasoning = "FIRST_NATIVE_REASONING" if first else "SECOND_NATIVE_REASONING"
            if streaming:
                packets = [
                    {"choices": [{"index": 0, "delta": {
                        "reasoning_content": reasoning,
                    }, "finish_reason": None}]},
                    {"choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}]},
                    {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                     "usage": {"prompt_tokens": 40, "completion_tokens": 8, "total_tokens": 48}},
                ]
                return httpx.Response(
                    200, text="".join("data: " + json.dumps(p) + "\n\n" for p in packets) + "data: [DONE]\n\n",
                    headers={"content-type": "text/event-stream"},
                )
            return httpx.Response(200, json=result(content, reasoning))

        backend = k.OpenAICompatibleBackend(k.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(responder))
        async def model():
            return "test-model"
        backend.resolve_model = model
        kernel = k.JackQwenKernel(backend, k.CFG)
        request = {"messages": [
            {"role": "system", "content": "Stable caller system contract"},
            {"role": "user", "content": "Answer the original user request."},
        ], "stream": streaming}
        try:
            if streaming:
                frames = [f.decode("utf-8") async for f in kernel.stream(request)]
                data = []
                for frame in frames:
                    for line in frame.splitlines():
                        if line.startswith("data: ") and line[6:] != "[DONE]":
                            data.append(json.loads(line[6:]))
                content = "".join(
                    chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    for chunk in data
                )
                reasoning = "".join(
                    chunk.get("choices", [{}])[0].get("delta", {}).get("reasoning_content", "")
                    for chunk in data
                )
            else:
                answer = await kernel._prepare_commit(request)
                content, reasoning = answer.content, answer.reasoning_content
            assert content == "Final verified answer."
            assert "DO_NOT_SHOW_PROVISIONAL" not in content
            assert "FIRST_NATIVE_REASONING" in reasoning
            assert "SECOND_NATIVE_REASONING" in reasoning
            assert len(observed) == 2  # NOT an Agentic memory or TAS third inference
            first, second = observed
            assert first["reasoning_effort"] == "xhigh"
            assert second["reasoning_effort"] == "xhigh"
            assert first["chat_template_kwargs"]["enable_thinking"]
            assert second["chat_template_kwargs"]["enable_thinking"]
            assert first["messages"] == second["messages"][:len(first["messages"])]
            assert second["messages"][-2]["role"] == "assistant"
            assert second["messages"][-2]["content"] == ""
            assert "DO_NOT_SHOW_PROVISIONAL" not in json.dumps(second["messages"])
            assert "FIRST_NATIVE_REASONING" in json.dumps(second["messages"][-2])
            assert second["messages"][-1]["role"] == "user"
            assert k.AGENTIC_STAGE1_VERIFICATION_PROMPT in second["messages"][-1]["content"]
            assert "Stable caller system contract" in second["messages"][0]["content"]
            assert first["messages"][0]["content"] == second["messages"][0]["content"]
        finally:
            await backend._client.aclose()
    asyncio.run(run())


def test_xhigh_and_legacy_deep_research_are_separate(monkeypatch, tmp_path):
    x = load(monkeypatch, tmp_path, "x-high")
    assert not x.ULTRA_REVIEW_MODE
    assert x.STAGES["thesis"].name == "Native answer"
    old = load(monkeypatch, tmp_path, "deep-research")
    assert old.ULTRA_MODE and not old.ULTRA_REVIEW_MODE
    assert old._runtime_identity_details()["mode"] == "deep-research"
    assert old._runtime_identity_details()["flow"] == [
        "extended_initial", "extended_reflection", "extended_synthesis",
    ]
