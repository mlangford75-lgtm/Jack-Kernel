"""Kernel-wide streaming semantics: provisional text never acquires answer/tool authority."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from deep_reasoning_pi_stream import (
    _ACTIVE_REASONING_SINK, ReasoningSink, deep_reasoning_pi_stream,
)
from jack_deep_reasoning_kernel import install_deep_reasoning
from test_deep_reasoning_kernel import FakeKernel, ns


class StreamingFakeKernel(FakeKernel):
    async def _run_stage_streamed(
        self, messages, secondary_system, stage_key, usage, *,
        tools, tool_choice, append, same_stage_resume=False,
    ):
        self.calls.append((stage_key, messages, tool_choice, tools))
        stage = stage_key.removeprefix("deep_reasoning_")
        yield {"kind": "reasoning", "text": stage + "-native"}
        yield {"kind": "content", "text": stage + "-"}
        await asyncio.sleep(0)
        yield {"kind": "content", "text": "body"}
        usage["completion_tokens"] += 2
        yield {
            "kind": "result",
            "data": {"choices": [{"message": {
                "role": "assistant", "content": stage + "-body",
                "reasoning_content": stage + "-native",
            }, "finish_reason": "stop"}], "usage": {"completion_tokens": 2}},
        }


def test_all_deep_reasoning_stages_stream_generated_text_without_premature_commit():
    async def run():
        kernel = StreamingFakeKernel()
        install_deep_reasoning(kernel, ns())
        sink = ReasoningSink()
        token = _ACTIVE_REASONING_SINK.set(sink)
        try:
            completed = await kernel._prepare_commit({
                "messages": [{"role": "user", "content": "Describe the clock"}],
            })
        finally:
            _ACTIVE_REASONING_SINK.reset(token)
        observed = list(sink.queue._queue)
        assert all(kind in {"reasoning", "keepalive"} for kind, _ in observed)
        view = "".join(text for kind, text in observed if kind == "reasoning")
        for stage in ("thesis", "antithesis", "synthesis"):
            assert stage + "-native" in view
            assert ("[" + stage.upper() + " OUTPUT — PROVISIONAL]") in view
            assert view.count(stage + "-body") == 0  # split token observations, not replayed at EOS
            assert view.count(stage + "-") >= 2
        assert view.count("OUTPUT — PROVISIONAL") == 3
        assert completed.content == "synthesis-body"
        assert completed.finish_reason == "stop"
        assert all("thesis-native" not in str(c[1]) for c in kernel.calls[1:])
        assert "antithesis-native" not in str(kernel.calls[2][1])
    asyncio.run(run())


def test_pi_stream_releases_only_final_committed_content_after_observations():
    async def run():
        kernel = StreamingFakeKernel()
        install_deep_reasoning(kernel, ns())
        async def invoke(body):
            return await kernel._run_impl(body)
        kernel._run_impl = lambda body: kernel._prepare_commit(body)
        model_ns = SimpleNamespace(CFG=SimpleNamespace(virtual_model="jack-kernel"),
                                   normalize_usage=lambda u: dict(u))
        frames = [item async for item in deep_reasoning_pi_stream(
            kernel, {"messages": [{"role": "user", "content": "Clock"}]}, model_ns,
            heartbeat_seconds=.001,
        )]
        deltas = [
            json.loads(f[6:])["choices"][0]["delta"]
            for f in frames if f.startswith(b"data: {")
            and json.loads(f[6:]).get("choices")
        ]
        observed = "".join(d.get("reasoning_content", "") for d in deltas)
        assert "thesis-body" in observed
        assert "antithesis-body" in observed
        assert "synthesis-body" in observed
        content = [d["content"] for d in deltas if "content" in d]
        assert content == ["synthesis-body"]
        assert frames[-1] == b"data: [DONE]\n\n"
    asyncio.run(run())
