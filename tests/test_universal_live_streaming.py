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
            # Verify each delimited stage body. "thesis" is a substring of
            # "antithesis" and "synthesis", so counting the full trace is wrong.
            marker = "[" + stage.upper() + " OUTPUT — PROVISIONAL]\n"
            section = view.split(marker, 1)[1].split("\n[", 1)[0]
            assert section == stage + "-body"
            assert view.count(marker) == 1
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


def test_pi_receives_generated_text_before_thesis_completes():
    """A real live stream must expose a text delta while backend stage 1 is blocked."""
    class PausedThesisKernel(StreamingFakeKernel):
        def __init__(self):
            super().__init__()
            self.paused = asyncio.Event()
            self.resume = asyncio.Event()

        async def _run_stage_streamed(
            self, messages, secondary_system, stage_key, usage, *,
            tools, tool_choice, append, same_stage_resume=False,
        ):
            if stage_key != "deep_reasoning_thesis":
                async for packet in super()._run_stage_streamed(
                    messages, secondary_system, stage_key, usage,
                    tools=tools, tool_choice=tool_choice, append=append,
                    same_stage_resume=same_stage_resume,
                ):
                    yield packet
                return
            self.calls.append((stage_key, messages, tool_choice, tools))
            yield {"kind": "reasoning", "text": "thesis-native"}
            yield {"kind": "content", "text": "FIRST_VISIBLE_FRAGMENT"}
            self.paused.set()
            await self.resume.wait()
            yield {"kind": "content", "text": "_TAIL"}
            usage["completion_tokens"] += 2
            yield {"kind": "result", "data": {
                "choices": [{"message": {
                    "role": "assistant", "content": "FIRST_VISIBLE_FRAGMENT_TAIL",
                    "reasoning_content": "thesis-native",
                }, "finish_reason": "stop"}],
                "usage": {"completion_tokens": 2},
            }}

    async def run():
        kernel = PausedThesisKernel()
        install_deep_reasoning(kernel, ns())
        kernel._run_impl = lambda body: kernel._prepare_commit(body)
        model_ns = SimpleNamespace(
            CFG=SimpleNamespace(virtual_model="jack-kernel"),
            normalize_usage=lambda u: dict(u),
        )
        stream = deep_reasoning_pi_stream(
            kernel, {"messages": [{"role": "user", "content": "Test live output"}]},
            model_ns, heartbeat_seconds=.005,
        )
        try:
            first = json.loads((await anext(stream))[6:])
            assert first["choices"][0]["delta"] == {"role": "assistant"}
            await asyncio.wait_for(kernel.paused.wait(), timeout=2)
            observed = []
            for _ in range(12):
                frame = await asyncio.wait_for(anext(stream), timeout=2)
                if frame.startswith(b"data: {"):
                    packet = json.loads(frame[6:])
                    if packet.get("choices"):
                        delta = packet["choices"][0]["delta"]
                        observed.append(delta)
                        if "FIRST_VISIBLE_FRAGMENT" in delta.get("reasoning_content", ""):
                            break
            assert any(
                "FIRST_VISIBLE_FRAGMENT" in d.get("reasoning_content", "")
                for d in observed
            ), "first stage text was buffered instead of streamed live"
            assert not kernel.resume.is_set(), "Thesis had already completed"
            assert all("content" not in d and "tool_calls" not in d for d in observed)
            kernel.resume.set()
            remainder = [frame async for frame in stream]
            published = [
                json.loads(frame[6:])["choices"][0]["delta"].get("content")
                for frame in remainder if frame.startswith(b"data: {")
                and json.loads(frame[6:]).get("choices")
            ]
            assert [x for x in published if x is not None] == ["synthesis-body"]
        finally:
            kernel.resume.set()
            await stream.aclose()

    asyncio.run(run())
