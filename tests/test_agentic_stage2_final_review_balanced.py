"""Agentic Flash is single-stage; other supported profiles use one memory pass.

Check actual backend payloads across streaming/cache layouts, preserving the
canonical current turn and source-only tools-off authority.
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


@pytest.mark.parametrize("profile,thinking", [("flash", False), ("balanced", False), ("thorough", True), ("translated", True)])
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
            if profile == "flash":
                body = {"model": "jack-kernel", "stream": stream,
                        "messages": history[:-1]}
                if stream:
                    frames = [chunk async for chunk in kernel.stream(body)]
                    text = b"".join(frames).decode("utf-8")
                    assert "Working knowledge" in text
                    assert "Agentic Turn ID:" in text
                    assert "data: [DONE]" in text
                else:
                    result = await kernel.run(body)
                    assert result.content.startswith("Working knowledge")
                    assert "Agentic Turn ID:" in result.content
                assert len(captured) == 1
                assert k._runtime_identity_details()["flow"] == ["extended_initial"]
                return None
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
    if profile == "flash":
        assert answer is None
        assert len(captured) == 1
        assert captured[0]["chat_template_kwargs"]["enable_thinking"] is False
        assert "JACK READ-ONLY WORKING-STATE SOURCE DATA" not in json.dumps(captured[0]["messages"])
        return
    assert answer["choices"][0]["message"]["content"] == "Working knowledge"
    assert len(captured) == 1
    payload = captured[0]
    assert payload["chat_template_kwargs"]["enable_thinking"] is thinking
    assert "tools" not in payload and "tool_choice" not in payload
    all_messages = json.dumps(payload["messages"])
    assert "Unrelated historical request" not in all_messages
    assert "Clock updated and read back." not in all_messages
    assert "Summarize today's clock work." not in all_messages
    assert [m["role"] for m in payload["messages"]] == ["system", "user"]
    assert payload["messages"][0]["content"] == k.AGENTIC_36_STAGE2_PROMPT + "\n\n" + k.AGENTIC_STAGE2_MEMORY_TRIGGER
    prefix = "JACK READ-ONLY WORKING-STATE SOURCE DATA, NOT A USER REQUEST.\n"
    suffix = "\nEND JACK WORKING-STATE SOURCE DATA."
    capsule = payload["messages"][1]["content"]
    assert capsule.startswith(prefix) and capsule.endswith(suffix)
    assert json.loads(capsule[len(prefix):-len(suffix)])["events"] == [
        {"type": "reasoning_segment", "phase": "initial",
         "content": "R1: verified clock hand update."}
    ]
    assert not hasattr(k.CFG, "agentic_stage2_final_review")
    assert k.CFG.agentic_final_review is (profile == "translated")
    assert "Do not independently add discoveries" in payload["messages"][0]["content"]
    assert not any("review the working knowledge for consequential omissions" in
                   str(msg.get("content", "")) for msg in payload["messages"])
