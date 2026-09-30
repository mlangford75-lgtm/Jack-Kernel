from __future__ import annotations

import asyncio
import copy
import json

import pytest

import jack_kernel as kernel
import jack_path_policy as path_policy


HOST_ENV = {
    "SystemRoot": r"C:\Windows",
    "WINDIR": r"C:\Windows",
    "SystemDrive": "C:",
    "USERPROFILE": r"C:\Users\Operator",
}


def tool_delta(*, index=0, call_id=None, name=None, arguments=None):
    function = {}
    if name is not None:
        function["name"] = name
    if arguments is not None:
        function["arguments"] = arguments

    call = {"index": index, "type": "function"}
    if call_id is not None:
        call["id"] = call_id
    if function:
        call["function"] = function

    return {
        "choices": [
            {
                "index": 0,
                "delta": {"tool_calls": [call]},
                "finish_reason": None,
            }
        ]
    }


def reasoning_delta(text):
    return {
        "choices": [
            {
                "index": 0,
                "delta": {"reasoning_content": text},
                "finish_reason": None,
            }
        ]
    }


def content_delta(text):
    return {
        "choices": [
            {
                "index": 0,
                "delta": {"content": text},
                "finish_reason": None,
            }
        ]
    }


def finish(reason="tool_calls"):
    return {
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": reason,
            }
        ],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        },
    }


class FakeBackend:
    def __init__(self, *streams):
        self.streams = [list(stream) for stream in streams]
        self.requests = []

    async def chat_stream(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        if not self.streams:
            raise AssertionError("FakeBackend ran out of streams")
        for chunk in self.streams.pop(0):
            yield copy.deepcopy(chunk)

    async def chat(self, **kwargs):
        raise AssertionError("non-stream recovery should not be used")


@pytest.fixture(autouse=True)
def phase4_policy():
    original = kernel._RUNTIME_PATH_POLICY
    kernel._RUNTIME_PATH_POLICY = path_policy.build_runtime_path_policy(
        runtime_id=kernel.RUNTIME_ID,
        lane_id=kernel.LANE_ID,
        raw_json=json.dumps(
            {
                "version": 1,
                "workspace_root": r"D:\Projects\Jack",
                "never_paths": [],
            }
        ),
        host_environment=HOST_ENV,
    )
    yield
    kernel._RUNTIME_PATH_POLICY = original


def tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "read",
                "description": "Read a file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "bash",
                "description": "Run a shell command",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
        },
    ]


async def collect_stage(jack):
    packets = []
    usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    async for packet in jack._run_stage_streamed(
        [{"role": "user", "content": "Perform the task."}],
        "",
        "thesis",
        usage,
        tools=tools(),
        tool_choice="auto",
        append=False,
    ):
        packets.append(packet)
    return packets


def test_streamed_reasoning_remains_live_but_tool_fragments_are_withheld():
    backend = FakeBackend(
        [
            reasoning_delta("useful reasoning"),
            tool_delta(
                call_id="call-read",
                name="read",
                arguments='{"path":"D:\\\\Projects\\\\Jack\\\\',
            ),
            tool_delta(arguments='README.md"}'),
            finish(),
        ]
    )
    jack = kernel.JackQwenKernel(backend, kernel.CFG)

    packets = asyncio.run(collect_stage(jack))

    assert any(
        packet.get("kind") == "reasoning"
        and packet.get("text") == "useful reasoning"
        for packet in packets
    )
    assert not any(packet.get("kind") == "tool_calls" for packet in packets)

    result = next(
        packet["data"]
        for packet in packets
        if packet.get("kind") == "result"
    )
    message = result["choices"][0]["message"]

    assert result["_jack_tool_call_fragments_streamed"] is False
    assert message["tool_calls"][0]["id"] == "call-read"
    assert json.loads(
        message["tool_calls"][0]["function"]["arguments"]
    ) == {"path": r"D:\Projects\Jack\README.md"}


def test_streamed_workspace_denial_preserves_cognition_and_corrects_same_stage():
    backend = FakeBackend(
        [
            reasoning_delta("valuable analysis survives"),
            tool_delta(
                call_id="call-outside",
                name="read",
                arguments='{"path":"D:\\\\Outside\\\\secret.txt"}',
            ),
            finish(),
        ],
        [
            content_delta("continued safely"),
            finish("stop"),
        ],
    )
    jack = kernel.JackQwenKernel(backend, kernel.CFG)

    packets = asyncio.run(collect_stage(jack))

    assert not any(packet.get("kind") == "tool_calls" for packet in packets)
    assert any(
        packet.get("kind") == "reasoning"
        and packet.get("text") == "valuable analysis survives"
        for packet in packets
    )
    assert any(
        packet.get("kind") == "reasoning"
        and "PHASE-4 FILESYSTEM ACTION REJECTED" in packet.get("text", "")
        for packet in packets
    )

    result = next(
        packet["data"]
        for packet in reversed(packets)
        if packet.get("kind") == "result"
    )
    message = result["choices"][0]["message"]

    assert message.get("tool_calls") is None
    assert message["content"] == "continued safely"
    assert len(backend.requests) == 2

    repair_history = backend.requests[1]["messages"]
    checkpoint = next(
        item
        for item in repair_history
        if isinstance(item, dict)
        and item.get("_jack_internal_tool_validation_checkpoint")
    )
    rejection = next(
        item
        for item in repair_history
        if isinstance(item, dict)
        and item.get("_jack_internal_tool_validation_rejection")
    )

    assert checkpoint.get("reasoning_content") == "valuable analysis survives"
    assert "Execution evidence: NONE" in rejection["content"]
    assert r"D:\Outside" not in rejection["content"]


def test_streamed_never_target_hard_interrupts_before_any_tool_release():
    original = kernel._RUNTIME_PATH_POLICY
    kernel._RUNTIME_PATH_POLICY = path_policy.build_runtime_path_policy(
        runtime_id=kernel.RUNTIME_ID,
        lane_id=kernel.LANE_ID,
        raw_json=json.dumps(
            {
                "version": 1,
                "workspace_root": None,
                "never_paths": [],
            }
        ),
        host_environment=HOST_ENV,
    )

    backend = FakeBackend(
        [
            reasoning_delta("safe prefix"),
            tool_delta(
                call_id="call-never",
                name="read",
                arguments=(
                    '{"path":"C:\\\\Windows\\\\System32\\\\drivers\\\\etc\\\\hosts"}'
                ),
            ),
            finish(),
        ]
    )
    jack = kernel.JackQwenKernel(backend, kernel.CFG)
    packets = []

    async def run():
        async for packet in jack._run_stage_streamed(
            [{"role": "user", "content": "Read it."}],
            "",
            "thesis",
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            tools=tools(),
            tool_choice="auto",
            append=False,
        ):
            packets.append(packet)

    try:
        with pytest.raises(kernel.Phase4RestrictedPathInterrupt):
            asyncio.run(run())
    finally:
        kernel._RUNTIME_PATH_POLICY = original

    assert any(
        packet.get("kind") == "reasoning"
        and packet.get("text") == "safe prefix"
        for packet in packets
    )
    assert not any(packet.get("kind") == "tool_calls" for packet in packets)


def test_streamed_command_arguments_are_not_emitted_as_reasoning_side_channel():
    command = 'git status'
    backend = FakeBackend(
        [
            tool_delta(
                call_id="call-bash",
                name="bash",
                arguments=json.dumps({"command": command}),
            ),
            finish(),
        ]
    )
    jack = kernel.JackQwenKernel(backend, kernel.CFG)

    executor_context = kernel.Phase4ExecutorRequestContext(
        protocol_version=1,
        runtime_id=kernel.RUNTIME_ID,
        lane_id=kernel.LANE_ID,
        cwd=r"D:\Projects\Jack",
        platform="win32",
        adapter="test",
    )
    token = kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.set(executor_context)
    try:
        packets = asyncio.run(collect_stage(jack))
    finally:
        kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.reset(token)

    visible_reasoning = "".join(
        str(packet.get("text") or "")
        for packet in packets
        if packet.get("kind") == "reasoning"
    )

    assert command not in visible_reasoning
    assert not any(packet.get("kind") == "tool_calls" for packet in packets)

    result = next(
        packet["data"]
        for packet in packets
        if packet.get("kind") == "result"
    )
    assert result["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "bash"


def test_stream_stage_source_contains_no_immediate_tool_call_fragment_yield():
    import inspect

    source = inspect.getsource(
        kernel.JackQwenKernel._run_stage_streamed
    )

    assert 'yield {"kind": "tool_calls"' not in source
    assert "executable tool-call fragments stay" in source
