from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "jack_responses_compat.py"
spec = importlib.util.spec_from_file_location("jack_responses_compat_rearm_test", MODULE)
compat = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(compat)


def test_responses_stream_failure_rearms_pending_resume_state():
    class StubCFG:
        virtual_model = "jack-kernel"

    class Kernel:
        def __init__(self):
            self.tool_rearms = []
            self.debug_rearms = []

        async def stream(self, _body):
            if False:
                yield b""
            raise RuntimeError("injected stream failure")

        async def _rearm_pending_tool_resume_for_messages(self, messages):
            self.tool_rearms.append(messages)

        async def _rearm_pending_debugging_resumes_for_messages(self, messages):
            self.debug_rearms.append(messages)

    kernel = Kernel()

    class JK:
        CFG = StubCFG()
        KERNEL = kernel

    messages = [{"role": "tool", "tool_call_id": "call-1", "content": "result"}]
    chat = {"messages": messages, "stream": True}

    async def collect():
        events = []
        async for chunk in compat._stream(JK, chat, {}):
            data = next(line[6:] for line in chunk.decode().splitlines() if line.startswith("data: "))
            events.append(json.loads(data))
        return events

    events = asyncio.run(collect())

    assert events[-1]["type"] == "response.failed"
    assert events[-1]["error"]["code"] == "jack_responses_stream_error"
    assert kernel.tool_rearms == [messages]
    assert kernel.debug_rearms == [messages]
