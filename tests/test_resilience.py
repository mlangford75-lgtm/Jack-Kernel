import asyncio
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "jack_kernel.py"
TOOLS = [{
    "type": "function",
    "function": {
        "name": "bash",
        "parameters": {
            "type": "object",
            "required": ["command"],
            "properties": {"command": {"type": "string"}},
        },
        "strict": False,
    },
}]


def load(mode: str):
    os.environ["JACK_REASONING_LEVEL"] = mode
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "off"
    os.environ["JACK_BACKEND_MODEL"] = "test-model"
    name = f"jack_test_{mode.replace('-', '_')}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def response(content="", reasoning="", tool_calls=None):
    msg = {"role": "assistant", "content": content}
    if reasoning:
        msg["reasoning_content"] = reasoning
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
    return {
        "choices": [{"index": 0, "message": msg, "finish_reason": "tool_calls" if tool_calls else "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def call(call_id, args):
    return [{"id": call_id, "type": "function", "function": {"name": "bash", "arguments": json.dumps(args)}}]


class FakeBackend:
    def __init__(self, queue):
        self.queue = list(queue)
        self.calls = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        if not self.queue:
            raise AssertionError("fake backend queue exhausted")
        item = self.queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


async def agentic_nonstream_tests():
    m = load("agentic")

    # Malformed Stage-1 call is contained inside Jack and corrected before execution.
    b = FakeBackend([
        response(reasoning="use bash", tool_calls=call("bad", {})),
        response(reasoning="corrected", tool_calls=call("good", {"command": "echo ok"})),
    ])
    k = m.JackQwenKernel(b, m.CFG)
    out = await k._prepare_commit({"messages": [{"role": "user", "content": "Use bash."}], "tools": TOOLS})
    assert isinstance(out, m.KernelResult) and out.tool_calls
    assert json.loads(out.tool_calls[0]["function"]["arguments"])["command"] == "echo ok"
    assert len(b.calls) == 2

    # Tools-off Stage 2 gets one in-stage correction instead of destroying A1.
    b = FakeBackend([
        response(content="A1", reasoning="r1"),
        response(reasoning="oops", tool_calls=call("noauth", {"command": "echo no"})),
        response(content="<grounding>g</grounding>", reasoning="r2"),
    ])
    k = m.JackQwenKernel(b, m.CFG)
    out = await k._prepare_commit({"messages": [{"role": "user", "content": "Do work."}], "tools": TOOLS})
    assert isinstance(out, m.PreparedCommit)
    assert out.frozen_answer == "A1"
    assert "<grounding>" in out.frozen_xml

    # Zero-authority Stage 2 failure degrades to exact frozen A1 rather than losing it.
    b = FakeBackend([
        response(content="VALUABLE A1", reasoning="r1"),
        m.HTTPException(status_code=502, detail="synthetic Stage 2 backend failure"),
    ])
    k = m.JackQwenKernel(b, m.CFG)
    out = await k._prepare_commit({"messages": [{"role": "user", "content": "Do work."}], "tools": TOOLS})
    assert isinstance(out, m.KernelResult)
    assert out.content == "VALUABLE A1"
    assert "DEGRADED COMMIT" in (out.reasoning_content or "")

    # A failed tool-result resume leaves the original checkpoint recoverable and not in-flight.
    b = FakeBackend([response(reasoning="r", tool_calls=call("resume1", {"command": "echo one"}))])
    k = m.JackQwenKernel(b, m.CFG)
    first = await k._prepare_commit({"messages": [{"role": "user", "content": "Use bash."}], "tools": TOOLS})
    assert first.tool_calls and "resume1" in k._pending_tool_resumes
    b.queue.append(m.HTTPException(status_code=502, detail="resume backend failed"))
    try:
        await k.run({
            "messages": [
                {"role": "user", "content": "Use bash."},
                {"role": "tool", "tool_call_id": "resume1", "content": "ok"},
            ],
            "tools": TOOLS,
        })
    except m.HTTPException:
        pass
    else:
        raise AssertionError("resume failure should propagate")
    state = k._pending_tool_resumes["resume1"]
    assert state.in_flight is False

    # Successful resume retires the superseded checkpoint only after successor/commit succeeds.
    b = FakeBackend([response(reasoning="r", tool_calls=call("resume2", {"command": "echo two"}))])
    k = m.JackQwenKernel(b, m.CFG)
    first = await k._prepare_commit({"messages": [{"role": "user", "content": "Use bash."}], "tools": TOOLS})
    assert first.tool_calls and "resume2" in k._pending_tool_resumes
    b.queue.extend([response(content="A1 after tool", reasoning="r1"), response(content="<grounding>ok</grounding>", reasoning="r2")])
    out = await k.run({
        "messages": [
            {"role": "user", "content": "Use bash."},
            {"role": "tool", "tool_call_id": "resume2", "content": "ok"},
        ],
        "tools": TOOLS,
    })
    assert out.content and "A1 after tool" in out.content
    assert "resume2" not in k._pending_tool_resumes


async def deep_research_nonstream_tests():
    m = load("ultra")

    # Thesis has no tool authority: reject only the action, preserve/retry cognition, continue full program.
    b = FakeBackend([
        response(reasoning="thesis reasoning", tool_calls=call("t1", {"command": "echo forbidden"})),
        response(content="Thesis", reasoning="thesis corrected"),
        response(content="Antithesis", reasoning="anti"),
        response(content="Synthesis answer", reasoning="synth"),
    ])
    k = m.JackQwenKernel(b, m.CFG)
    out = await k._prepare_commit({"messages": [{"role": "user", "content": "Analyze."}], "tools": TOOLS})
    assert isinstance(out, m.KernelResult)
    assert out.content == "Synthesis answer"

    # Synthesis malformed executable call is corrected inside Synthesis before caller sees it.
    b = FakeBackend([
        response(content="Thesis", reasoning="t"),
        response(content="Antithesis", reasoning="a"),
        response(reasoning="need tool", tool_calls=call("sbad", {})),
        response(reasoning="fixed tool", tool_calls=call("sgood", {"command": "echo good"})),
    ])
    k = m.JackQwenKernel(b, m.CFG)
    out = await k._prepare_commit({"messages": [{"role": "user", "content": "Analyze with tools."}], "tools": TOOLS})
    assert isinstance(out, m.KernelResult) and out.tool_calls
    assert out.tool_calls[0]["id"] == "sgood"
    assert json.loads(out.tool_calls[0]["function"]["arguments"])["command"] == "echo good"


async def main():
    await agentic_nonstream_tests()
    await deep_research_nonstream_tests()
    print("Jack Kernel resilience tests: PASS")


if __name__ == "__main__":
    asyncio.run(main())

# Streaming-focused regression helpers are defined below and invoked by a second entrypoint
# when JACK_RUN_STREAM_TESTS=1 so the ordinary package smoke test remains quick.
class FakeStreamBackend(FakeBackend):
    async def chat_stream(self, **kwargs):
        self.calls.append(kwargs)
        if not self.queue:
            raise AssertionError("fake stream backend queue exhausted")
        item = self.queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        choice = (item.get("choices") or [{}])[0] or {}
        msg = choice.get("message") or {}
        delta = {}
        for key in ("reasoning_content", "reasoning", "content", "tool_calls"):
            if key in msg:
                delta[key] = msg[key]
        yield {
            "choices": [{"index": 0, "delta": delta, "finish_reason": choice.get("finish_reason")}],
            "usage": item.get("usage") or {},
        }


def sse_objects(chunks):
    out = []
    for raw in chunks:
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
        for line in text.splitlines():
            if not line.startswith("data: "):
                continue
            payload = line[6:].strip()
            if payload and payload != "[DONE]":
                out.append(json.loads(payload))
    return out


async def streaming_tests():
    # Agentic Stage-2 backend failure must return exact frozen A1, not a generic stage failure.
    m = load("agentic")
    b = FakeStreamBackend([
        response(content="STREAM A1", reasoning="r1"),
        m.HTTPException(status_code=502, detail="synthetic streamed Stage 2 failure"),
    ])
    k = m.JackQwenKernel(b, m.CFG)
    chunks = [chunk async for chunk in k.stream({"messages": [{"role": "user", "content": "Do work."}], "stream": True, "tools": TOOLS})]
    wire = b"".join(chunks).decode("utf-8", errors="replace")
    assert "STREAM A1" in wire
    assert "DEGRADED COMMIT" in wire
    assert "internal stage failure" not in wire

    # Deep Research buffers malformed Synthesis tool calls until corrected and only exposes the valid call.
    m = load("ultra")
    b = FakeStreamBackend([
        response(content="Thesis", reasoning="t"),
        response(content="Antithesis", reasoning="a"),
        response(reasoning="need", tool_calls=call("sbadstream", {})),
        response(reasoning="fixed", tool_calls=call("sgoodstream", {"command": "echo ok"})),
    ])
    k = m.JackQwenKernel(b, m.CFG)
    chunks = [chunk async for chunk in k.stream({"messages": [{"role": "user", "content": "Analyze."}], "stream": True, "tools": TOOLS})]
    objs = sse_objects(chunks)
    exposed_ids = []
    for obj in objs:
        for choice in obj.get("choices") or []:
            for tc in (choice.get("delta") or {}).get("tool_calls") or []:
                if isinstance(tc, dict) and tc.get("id"):
                    exposed_ids.append(tc["id"])
    assert "sgoodstream" in exposed_ids
    assert "sbadstream" not in exposed_ids

    # Streaming tool-result resume failure re-arms the original checkpoint.
    m = load("agentic")
    b = FakeStreamBackend([response(reasoning="r", tool_calls=call("streamresume", {"command": "echo one"}))])
    k = m.JackQwenKernel(b, m.CFG)
    m.KERNEL = k
    _ = [chunk async for chunk in k.stream({"messages": [{"role": "user", "content": "Use bash."}], "stream": True, "tools": TOOLS})]
    assert "streamresume" in k._pending_tool_resumes
    b.queue.append(m.HTTPException(status_code=502, detail="synthetic streamed resume failure"))
    body = {
        "messages": [
            {"role": "user", "content": "Use bash."},
            {"role": "tool", "tool_call_id": "streamresume", "content": "ok"},
        ],
        "stream": True,
        "tools": TOOLS,
    }
    _ = [chunk async for chunk in m._safe_public_stream(body)]
    assert k._pending_tool_resumes["streamresume"].in_flight is False
    print("Jack Kernel streaming resilience tests: PASS")


if __name__ == "__main__" and os.environ.get("JACK_RUN_STREAM_TESTS") == "1":
    asyncio.run(streaming_tests())
