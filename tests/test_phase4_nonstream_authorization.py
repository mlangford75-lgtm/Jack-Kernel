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


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "Write a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "custom_tool",
            "description": "An unrelated custom tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
]


def tool_response(
    name: str,
    arguments: dict,
    *,
    call_id: str = "call-phase4",
    reasoning: str = "useful analysis before tool selection",
):
    return {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": reasoning,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        },
    }


def content_response(text: str):
    return {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": text,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        },
    }


class FakeBackend:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def chat(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))

        if not self.responses:
            raise AssertionError("FakeBackend ran out of responses")

        return copy.deepcopy(self.responses.pop(0))


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


def request():
    return {
        "messages": [
            {
                "role": "user",
                "content": "Perform the requested file task.",
            }
        ],
        "tools": copy.deepcopy(TOOLS),
        "tool_choice": "auto",
        "stream": False,
    }


def test_nonstream_allowed_structured_call_reaches_checkpoint():
    backend = FakeBackend(
        tool_response(
            "write",
            {
                "path": r"D:\Projects\Jack\result.txt",
                "content": "safe",
            },
        )
    )
    jack = kernel.JackQwenKernel(backend, kernel.CFG)

    result = asyncio.run(jack.run(request()))

    assert result.tool_calls
    assert result.tool_calls[0]["function"]["name"] == "write"
    assert len(jack._pending_tool_resumes) == 1


def test_nonstream_workspace_denial_preserves_cognition_and_corrects_same_stage():
    repaired_answer = "continued safely without the denied tool"
    responses = [
        tool_response(
            "write",
            {
                "path": r"D:\Outside\result.txt",
                "content": "unsafe target",
            },
            reasoning="valuable reasoning that must survive",
        ),
        content_response(repaired_answer),
    ]

    # Agentic Stage 1 remains the sole answer-generating stage. Once the
    # denied tool action is corrected in that same stage, the normal mandatory
    # Stage-2 Jack XML consolidation must still run. The Phase-4 denial must not
    # accidentally degrade or truncate the Agentic lifecycle.
    if kernel.AGENTIC_MODE:
        responses.append(
            content_response(
                "<Jack XML>\n"
                "<workspace_state>Phase-4 denial recovered without execution.</workspace_state>\n"
                "</Jack XML>"
            )
        )

    backend = FakeBackend(*responses)
    jack = kernel.JackQwenKernel(backend, kernel.CFG)

    result = asyncio.run(jack.run(request()))

    if kernel.AGENTIC_MODE:
        assert result.content is not None
        assert "<Jack XML>" in result.content
        assert result.content.endswith(repaired_answer)
        assert len(backend.requests) == 3
    else:
        assert result.content == repaired_answer
        assert len(backend.requests) == 2

    assert result.tool_calls is None
    assert jack._pending_tool_resumes == {}

    repair_history = backend.requests[1]["messages"]

    checkpoints = [
        item
        for item in repair_history
        if isinstance(item, dict)
        and item.get("_jack_internal_tool_validation_checkpoint")
    ]

    rejections = [
        item
        for item in repair_history
        if isinstance(item, dict)
        and item.get("_jack_internal_tool_validation_rejection")
    ]

    assert len(checkpoints) == 1
    assert len(rejections) == 1

    assert (
        checkpoints[0].get("reasoning_content")
        == "valuable reasoning that must survive"
    )

    rejection_text = str(rejections[0].get("content") or "")
    assert "rejected before execution" in rejection_text
    assert "Execution evidence: NONE" in rejection_text
    assert r"D:\Outside" not in rejection_text


def test_nonstream_never_target_hard_interrupts_without_model_retry_or_checkpoint():
    backend = FakeBackend(
        tool_response(
            "read",
            {
                "path": r"C:\Windows\System32\drivers\etc\hosts",
            },
        ),
        content_response("must never be reached"),
    )
    jack = kernel.JackQwenKernel(backend, kernel.CFG)

    with pytest.raises(
        kernel.Phase4RestrictedPathInterrupt,
    ) as caught:
        asyncio.run(jack.run(request()))

    assert caught.value.security_outcome is kernel.SecurityOutcome.HARD_INTERRUPT
    assert str(caught.value) == "Phase-4 restricted-path hard interrupt"
    assert "Windows" not in str(caught.value)
    assert "System32" not in str(caught.value)

    assert len(backend.requests) == 1
    assert jack._pending_tool_resumes == {}


def test_nonstream_custom_tool_is_not_falsely_reclassified_from_path_argument():
    backend = FakeBackend(
        tool_response(
            "custom_tool",
            {
                "path": r"D:\Outside\not-a-host-contracted-filesystem-target",
            },
        )
    )
    jack = kernel.JackQwenKernel(backend, kernel.CFG)

    result = asyncio.run(jack.run(request()))

    assert result.tool_calls
    assert result.tool_calls[0]["function"]["name"] == "custom_tool"
    assert len(jack._pending_tool_resumes) == 1


def test_phase4_structured_enforcement_is_installed_in_streamed_stage():
    import inspect

    source = inspect.getsource(
        kernel.JackQwenKernel._run_stage_streamed
    )

    assert "_phase4_partition_structured_tool_calls" in source
    assert 'yield {"kind": "tool_calls"' not in source
