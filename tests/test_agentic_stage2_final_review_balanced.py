"""Four Agentic profiles: Stage 2 is single-pass, including Thorough and Exhaustive.

Check actual backend payloads across streaming/cache layouts, preserving the
exact current-turn U/R1/A1 and tools-off authority.
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


def load(monkeypatch, tmp_path, profile, cache):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_FINAL_REVIEW", "1")
    monkeypatch.setenv("JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT", "1" if cache else "0")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "stage2_single_generation_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


@pytest.mark.parametrize("profile,thinking", [("flash", False), ("balanced", False), ("thorough", True), ("exhaustive", True)])
@pytest.mark.parametrize("cache", [False, True])
@pytest.mark.parametrize("stream", [False, True])
def test_stage2_review_scheduling_by_profile(monkeypatch, tmp_path, profile, thinking, cache, stream):
    k = load(monkeypatch, tmp_path, profile, cache)
    captured = []

    def respond(request):
        captured.append(json.loads(request.content))
        if stream:
            return httpx.Response(
                200,
                text='data: {"choices":[{"delta":{"content":"Working knowledge"},"finish_reason":null}]}\n\n'
                     'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json={"choices":[{"message":{"role":"assistant","content":"Working knowledge"},
                                "finish_reason":"stop"}],"usage":{}})

    async def run():
        backend = k.OpenAICompatibleBackend(k.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async def model():
            return "test-model"
        backend.resolve_model = model
        kernel = k.JackQwenKernel(backend, k.CFG)
        history = [
            {"role":"user","content":"Unrelated historical request"},
            {"role":"assistant","content":"Historical answer"},
            {"role":"user","content":"Summarize today's clock work."},
            {"role":"assistant","content":"Clock updated and read back.",
             "reasoning_content":"R1: verified clock hand update.",
             "_jack_extended_candidate_response":True,"_jack_stage_key":"extended_initial"},
        ]
        original = json.dumps(history, sort_keys=True)
        try:
            if stream:
                packets = [p async for p in kernel._run_stage_streamed(
                    history, "", "extended_reflection", {}, tools=None, tool_choice=None, append=False)]
                result = [p["data"] for p in packets if p["kind"] == "result"]
                assert len(result) == 1
                answer = result[0]
            else:
                answer = await kernel._run_stage(
                    history, "", "extended_reflection", {}, tools=None, tool_choice=None, append=False)
        finally:
            await backend._client.aclose()
        assert json.dumps(history, sort_keys=True) == original
        return answer

    answer = asyncio.run(run())
    assert answer["choices"][0]["message"]["content"] == "Working knowledge"
    assert len(captured) == 1
    payload = captured[0]
    assert payload["chat_template_kwargs"]["enable_thinking"] is thinking
    assert "tools" not in payload and "tool_choice" not in payload
    all_messages = json.dumps(payload["messages"])
    assert "Unrelated historical request" not in all_messages
    assert "Clock updated and read back." in all_messages
    assert not hasattr(k.CFG, "agentic_stage2_final_review")
    assert "Remove repetition, unnecessary deliberation, and conversational language." in all_messages
    assert not any("review the working knowledge for consequential omissions" in
                   str(msg.get("content", "")) for msg in payload["messages"])
