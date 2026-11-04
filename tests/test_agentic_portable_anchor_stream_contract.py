"""Universal Agentic task targeting and streamed-completion release regressions.

No inference backend, chat-template assumption, or hardware required.
"""
import asyncio
import copy
import json

import pytest

from test_agentic_task_anchor_release_contract import load


@pytest.mark.parametrize("content", [
    [{"type": "text", "text": "Create the SVG"}],
    [{"type": "input_text", "text": "Create the SVG"}],
    [{"type": "text", "text": "Fix the SVG"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}}],
])
def test_pi_style_structured_user_gets_matching_task_anchor_without_mutation(monkeypatch, tmp_path, content):
    k = load(monkeypatch, tmp_path)
    original = {"role": "user", "content": copy.deepcopy(content)}
    history = [copy.deepcopy(original)]
    turn = k._agentic_begin_turn(history, fresh=True)
    marker = f"[JACK LINK turn={turn} | artifact=U]"
    p1 = k.BACKEND._stage_messages_for_profile(history, k.STAGES["extended_initial"])
    assert isinstance(p1[0]["content"], list)
    assert p1[0]["content"][:-1] == content
    assert p1[0]["content"][-1] == {"type": "text", "text": "\n" + marker}
    assert history[0]["content"] == content
    assert original["content"] == content
    answer = k.append_extended_candidate_response(history, {"content": "Frozen result", "reasoning_content": "current R1"})
    k._agentic_forensic_start_stage2(history)
    p2 = k.BACKEND._stage_messages_for_profile(history, k.STAGES["extended_reflection"])
    assert p2[:len(p1)] == p1
    assert p2[-1]["content"] == answer
    assert p2[-1]["reasoning_content"] == "current R1"
    suffix = k._stage_continuation(k.STAGES["extended_reflection"], history)
    assert marker not in suffix
    assert suffix == k._AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION
    assert len(suffix) < 2400


def test_unprojectable_user_does_not_produce_dangling_model_reference(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    content = [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}}]
    history = [{"role": "user", "content": copy.deepcopy(content)}]
    k._agentic_begin_turn(history, fresh=True)
    p = k.BACKEND._stage_messages_for_profile(history, k.STAGES["extended_initial"])
    assert p[0]["content"] == content
    k.append_extended_candidate_response(history, {"content": "Frozen answer"})
    k._agentic_forensic_start_stage2(history)
    suffix = k._stage_continuation(k.STAGES["extended_reflection"], history)
    assert "JACK TASK SCOPE" not in suffix
    assert "JACK FORENSIC TARGET" not in suffix
    assert suffix == k._AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION


def test_structured_user_anchor_can_be_disabled_without_touching_content(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, anchor="0")
    content = [{"type": "text", "text": "Create the SVG"}]
    h = [{"role": "user", "content": copy.deepcopy(content)}]
    k._agentic_begin_turn(h, fresh=True)
    assert k.BACKEND._stage_messages_for_profile(h, k.STAGES["extended_initial"])[0]["content"] == content


def test_stage_completion_requires_explicit_backend_stop(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    for choices in ([], [{"message": {"content": "partial"}}], [{"finish_reason": None, "message": {"content": "partial"}}]):
        with pytest.raises(k.HTTPException):
            k.KERNEL._agentic_require_completed_stage({"choices": choices}, "Agentic Stage 2")
    k.KERNEL._agentic_require_completed_stage({"choices": [{"finish_reason": "stop"}]}, "Agentic Stage 2")


@pytest.mark.parametrize("stage", ["extended_initial", "extended_reflection"])
def test_stream_without_terminal_finish_is_rejected(monkeypatch, tmp_path, stage):
    k = load(monkeypatch, tmp_path)
    history = [{"role": "user", "content": "Task"}]
    if stage == "extended_reflection":
        k._agentic_begin_turn(history, fresh=True)
        k.append_extended_candidate_response(history, {"content": "Frozen A1"})
    async def incomplete(**kwargs):
        yield {"choices": [{"delta": {"content": "Partial text"}, "finish_reason": None}]}
    monkeypatch.setattr(k.KERNEL.backend, "chat_stream", incomplete)
    async def consume():
        async for _ in k.KERNEL._run_stage_streamed(history, "", stage, {}, append=False):
            pass
    with pytest.raises(k.HTTPException, match="without a backend terminal finish reason"):
        asyncio.run(consume())


def test_empty_agentic_stream_cannot_fallback_to_nonstream(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    history = [{"role": "user", "content": "Task"}]
    async def empty(**kwargs):
        if False:
            yield {}
    async def forbidden(**kwargs):
        raise AssertionError("non-stream fallback must never run")
    monkeypatch.setattr(k.KERNEL.backend, "chat_stream", empty)
    monkeypatch.setattr(k.KERNEL.backend, "chat", forbidden)
    async def consume():
        async for _ in k.KERNEL._run_stage_streamed(history, "", "extended_initial", {}, append=False):
            pass
    with pytest.raises(k.HTTPException, match="refusing non-streaming fallback"):
        asyncio.run(consume())


def test_degraded_frozen_answer_survives_shadow_write_error(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    history = [{"role": "user", "content": "Task"}]
    turn = k._agentic_begin_turn(history, fresh=True)
    answer = k.append_extended_candidate_response(history, {"content": "Exact A1"})
    k._agentic_forensic_start_stage2(history)
    def fail(*args, **kwargs):
        raise RuntimeError("shadow unavailable")
    monkeypatch.setattr(k, "_agentic_shadow_record_commit", fail)
    result = k.KERNEL._agentic_degraded_result(history, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, answer, "stream interrupted")
    assert result.content == "Exact A1"
    assert k._agentic_forensic_journal().get(turn)["status"] == "memory_failed"


def test_agentic_streaming_sse_decoder_rejects_malformed_data(monkeypatch, tmp_path):
    import httpx
    k = load(monkeypatch, tmp_path)
    b = k.OpenAICompatibleBackend(k.CFG)
    async def model():
        return "test-model"
    b.resolve_model = model
    def respond(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text="data: {broken\n\ndata: [DONE]\n\n",
        )
    async def run():
        await b._client.aclose()
        b._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            async for _ in b.chat_stream(
                messages=[{"role":"user","content":"Task"}],
                secondary_system="",
                profile=k.STAGES["extended_initial"],
                tools=None,
            ):
                pass
        finally:
            await b._client.aclose()
    with pytest.raises(k.HTTPException, match="Malformed backend SSE chunk"):
        asyncio.run(run())
