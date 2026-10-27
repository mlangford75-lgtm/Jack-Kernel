"""Live stage-aware TAS reasoning SSE for Pi, with tool-call release barriers.

Model-native reasoning and provisional stage-generated text are OBSERVATIONS
on Pi's reasoning channel; they never become the next stage's model input.
Provisional text never enters the authoritative assistant content channel.
Unvalidated tool arguments never stream to Pi. Tool calls only leave Jack
through its existing authorization + pending-resume checkpoint.
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


# A new context is copied into the kernel run task; each Pi request gets an
# independent sink, even across resumed tool rounds and concurrent requests.
_ACTIVE_REASONING_SINK: contextvars.ContextVar["ReasoningSink | None"] = contextvars.ContextVar(
    "jack_tas_active_reasoning_observer", default=None
)


@dataclass
class ReasoningSink:
    queue: asyncio.Queue[tuple[str, str]] = field(default_factory=lambda: asyncio.Queue(maxsize=16384))
    active: bool = True
    dropped: int = 0

    def offer(self, kind: str, text: str) -> None:
        if not self.active or not text:
            return
        try:
            self.queue.put_nowait((kind, text))
        except asyncio.QueueFull:
            # Observability must not block computation, stall tools, or gain
            # answer authority when a slow/disconnected client stops reading.
            self.dropped += 1


def current_reasoning_sink() -> ReasoningSink | None:
    return _ACTIVE_REASONING_SINK.get()


def _sse_chunk(model: str, response_id: str, created: int,
               delta: dict[str, Any], finish_reason: str | None = None) -> bytes:
    payload = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8")


async def deep_reasoning_pi_stream(kernel: Any, request_body: dict[str, Any],
                                    namespace: Any, *, heartbeat_seconds: float = 3.0
                                    ) -> AsyncIterator[bytes]:
    """Stream native reasoning live, but release content only after Synthesis commits.

    A client disconnect does not cancel Jack's already-running authoritative
    transaction. All actual tool calls pass through the existing kernel path.
    """
    rid = "chatcmpl-jack-dr-" + uuid.uuid4().hex
    created = int(time.time())
    model = namespace.CFG.virtual_model
    sink = ReasoningSink()
    token = _ACTIVE_REASONING_SINK.set(sink)
    # start a NEW task while this context var is set
    run_task = asyncio.create_task(kernel._run_impl(request_body))
    _ACTIVE_REASONING_SINK.reset(token)

    def evt(delta: dict[str, Any], finish: str | None = None) -> bytes:
        return _sse_chunk(model, rid, created, delta, finish)

    try:
        yield evt({"role": "assistant"})
        while not run_task.done() or not sink.queue.empty():
            try:
                kind, txt = await asyncio.wait_for(sink.queue.get(), timeout=heartbeat_seconds)
            except asyncio.TimeoutError:
                if not run_task.done():
                    yield b": jack-keepalive deep-reasoning.wait\n\n"
                continue
            if kind == "reasoning":
                # Pi's reasoning-capable OpenAI adapter recognizes this field.
                # Trace visibility is NOT authorization to reuse R1/R2 as context.
                yield evt({"reasoning_content": txt})
            elif kind == "keepalive":
                yield b": jack-keepalive deep-reasoning.stage\n\n"

        # Do not construct a successful final message if the TAS transaction failed.
        result = run_task.result()
        if sink.dropped:
            yield evt({"reasoning_content": f"\n[Jack: {sink.dropped} reasoning stream fragments omitted by slow client]\n"})
        calls = result.tool_calls
        if calls:
            if (result.finish_reason != "tool_calls" or result.content is not None
                    or result.reasoning_content is not None):
                raise RuntimeError("Deep Reasoning tool checkpoint leaked provisional output")
        elif (result.finish_reason != "stop" or not isinstance(result.content, str)
              or not result.content.strip()):
            raise RuntimeError("Deep Reasoning produced no committed Synthesis response")

        if calls:
            outbound = []
            for index, raw in enumerate(calls):
                fn = raw.get("function") if isinstance(raw, dict) else None
                if not isinstance(fn, dict):
                    raise RuntimeError("Malformed released tool call")
                outbound.append({
                    "index": index,
                    "id": str(raw["id"]),
                    "type": "function",
                    "function": {"name": str(fn["name"]), "arguments": str(fn["arguments"])},
                })
            yield evt({"tool_calls": outbound})
            yield evt({}, "tool_calls")
        else:
            yield evt({"content": result.content})
            yield evt({}, "stop")
        usage = result.usage or {}
        yield ("data: " + json.dumps({
            "id": rid, "object": "chat.completion.chunk", "created": created,
            "model": model, "choices": [], "usage": namespace.normalize_usage(dict(usage)),
        }, ensure_ascii=False) + "\n\n").encode("utf-8")
        yield b"data: [DONE]\n\n"
    finally:
        sink.active = False
        if not run_task.done():
            def _consume_background_failure(t: asyncio.Task) -> None:
                if not t.cancelled():
                    try:
                        t.exception()
                    except BaseException:
                        pass
            run_task.add_done_callback(_consume_background_failure)
