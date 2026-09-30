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


def call(call_id, name, arguments):
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments),
        },
    }


def active_tool_stage():
    if kernel.ULTRA_MODE:
        return "extended_synthesis"
    if kernel.AGENTIC_MODE:
        return "extended_initial"
    if kernel.CODE_DEBUGGING_MODE:
        return kernel._debugging_stage_key(1)
    return "thesis"


def stage_data(calls, *, reasoning="useful batch reasoning"):
    return {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": reasoning,
                    "tool_calls": copy.deepcopy(calls),
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
                "description": "Run a command",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
        },
    ]




def executor_context():
    return kernel.Phase4ExecutorRequestContext(
        protocol_version=1,
        runtime_id=kernel.RUNTIME_ID,
        lane_id=kernel.LANE_ID,
        cwd=r"D:\Projects\Jack",
        platform="win32",
        adapter="test",
    )


def test_partition_preserves_safe_sibling_order_and_ids():
    calls = [
        call("call-safe-a", "read", {"path": r"D:\Projects\Jack\a.txt"}),
        call("call-denied", "read", {"path": r"D:\Outside\secret.txt"}),
        call("call-safe-b", "bash", {"command": "git status"}),
    ]

    token = kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.set(executor_context())
    try:
        allowed, errors = kernel._phase4_partition_structured_tool_calls(calls)
    finally:
        kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.reset(token)

    assert [item["id"] for item in allowed] == [
        "call-safe-a",
        "call-safe-b",
    ]
    assert len(errors) == 1
    assert r"D:\Outside" not in errors[0]


def test_positive_never_sibling_hard_interrupts_before_subset_release():
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
    calls = [
        call("call-safe", "read", {"path": r"D:\Ordinary\a.txt"}),
        call(
            "call-never",
            "read",
            {"path": r"C:\Windows\System32\drivers\etc\hosts"},
        ),
    ]

    try:
        with pytest.raises(kernel.Phase4RestrictedPathInterrupt):
            kernel._phase4_partition_structured_tool_calls(calls)
    finally:
        kernel._RUNTIME_PATH_POLICY = original


class FakeBackend:
    def __init__(self, *responses):
        self.responses = list(responses)

    async def chat(self, **kwargs):
        if not self.responses:
            raise AssertionError("FakeBackend ran out of responses")
        return copy.deepcopy(self.responses.pop(0))


def test_nonstream_stage_keeps_safe_sibling_and_defers_denied_notice():
    calls = [
        call(
            "call-safe",
            "read",
            {"path": r"D:\Projects\Jack\README.md"},
        ),
        call(
            "call-denied",
            "read",
            {"path": r"D:\Outside\secret.txt"},
        ),
    ]
    jack = kernel.JackQwenKernel(
        FakeBackend(stage_data(calls)),
        kernel.CFG,
    )
    usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    result = asyncio.run(
        jack._run_stage(
            [{"role": "user", "content": "Read both."}],
            "",
            active_tool_stage(),
            usage,
            tools=tools(),
            tool_choice="auto",
            append=False,
        )
    )
    message = result["choices"][0]["message"]

    assert [item["id"] for item in message["tool_calls"]] == ["call-safe"]
    deferred = message["_jack_phase4_deferred_tool_rejection_errors"]
    assert len(deferred) == 1
    assert r"D:\Outside" not in deferred[0]


def test_checkpoint_tracks_only_authorized_ids_and_deferred_denial():
    data = stage_data(
        [
            call(
                "call-safe",
                "read",
                {"path": r"D:\Projects\Jack\README.md"},
            )
        ]
    )
    data["choices"][0]["message"][
        "_jack_phase4_deferred_tool_rejection_errors"
    ] = [
        "tool call 1: host-owned Phase-4 path policy denied "
        "the represented filesystem target"
    ]

    jack = kernel.JackQwenKernel(FakeBackend(), kernel.CFG)
    result = asyncio.run(
        jack._register_stage_tool_resume(
            stage_key=active_tool_stage(),
            history=[{"role": "user", "content": "Read both."}],
            secondary_system="",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            tools=tools(),
            tool_choice="auto",
            data=data,
        )
    )

    assert [item["id"] for item in result.tool_calls] == ["call-safe"]

    state = jack._pending_tool_resumes["call-safe"]
    assert state.expected_tool_call_ids == ("call-safe",)
    assert len(state.deferred_tool_rejection_errors) == 1
    assert set(jack._pending_tool_resumes) == {"call-safe"}


def test_resume_history_orders_safe_result_before_host_denial_notice():
    jack = kernel.JackQwenKernel(FakeBackend(), kernel.CFG)
    state = kernel.PendingToolResume(
        resume_id="resume",
        stage_key=active_tool_stage(),
        history=[
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    call(
                        "call-safe",
                        "read",
                        {"path": r"D:\Projects\Jack\README.md"},
                    )
                ],
            }
        ],
        secondary_system="",
        usage={},
        tools=tools(),
        tool_choice="auto",
        expected_tool_call_ids=("call-safe",),
        created_at=0.0,
        deferred_tool_rejection_errors=(
            "tool call 1: host-owned Phase-4 path policy denied "
            "the represented filesystem target",
        ),
    )

    history = jack._pending_tool_resume_history(
        state,
        [
            {
                "role": "tool",
                "tool_call_id": "call-safe",
                "content": "safe-result",
            }
        ],
    )

    assert history[-2]["role"] == "tool"
    assert history[-2]["tool_call_id"] == "call-safe"
    assert history[-1]["role"] == "user"
    assert history[-1]["_jack_internal_tool_validation_rejection"] is True
    assert "Execution evidence: NONE" in history[-1]["content"]


def test_resume_rejects_extra_result_for_withheld_sibling():
    jack = kernel.JackQwenKernel(FakeBackend(), kernel.CFG)
    state = kernel.PendingToolResume(
        resume_id="resume",
        stage_key=active_tool_stage(),
        history=[],
        secondary_system="",
        usage={},
        tools=tools(),
        tool_choice="auto",
        expected_tool_call_ids=("call-safe",),
        created_at=10**12,
    )
    jack._pending_tool_resumes["call-safe"] = state

    messages = [
        {
            "role": "tool",
            "tool_call_id": "call-safe",
            "content": "ok",
        },
        {
            "role": "tool",
            "tool_call_id": "call-denied",
            "content": "should never exist",
        },
    ]

    with pytest.raises(kernel.HTTPException) as caught:
        asyncio.run(jack._consume_pending_tool_resume(messages))

    assert caught.value.status_code == 409
    assert "Unexpected" in str(caught.value.detail)


def test_complete_mixed_checkpoint_exposes_only_releasable_calls():
    calls = [
        call(
            "call-safe",
            "read",
            {"path": r"D:\Projects\Jack\README.md"},
        ),
        call(
            "call-denied",
            "read",
            {"path": r"D:\Outside\secret.txt"},
        ),
        call(
            "call-shell",
            "bash",
            {"command": "git status"},
        ),
    ]
    jack = kernel.JackQwenKernel(
        FakeBackend(stage_data(calls)),
        kernel.CFG,
    )
    usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    token = kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.set(executor_context())
    try:
        data = asyncio.run(
            jack._run_stage(
                [{"role": "user", "content": "Do the independent checks."}],
                "",
                active_tool_stage(),
                usage,
                tools=tools(),
                tool_choice="auto",
                append=False,
            )
        )
    finally:
        kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.reset(token)
    result = asyncio.run(
        jack._register_stage_tool_resume(
            stage_key=active_tool_stage(),
            history=[{"role": "user", "content": "Do the independent checks."}],
            secondary_system="",
            usage=usage,
            tools=tools(),
            tool_choice="auto",
            data=data,
        )
    )

    released_ids = [item["id"] for item in result.tool_calls]

    assert released_ids == ["call-safe", "call-shell"]
    assert "call-denied" not in released_ids
    assert set(jack._pending_tool_resumes) == {
        "call-safe",
        "call-shell",
    }


def test_partition_rewrites_relative_structured_call_before_release():
    calls = [
        call(
            "call-relative",
            "read",
            {"path": r"src\engine.py"},
        ),
    ]

    allowed, errors = kernel._phase4_partition_structured_tool_calls(calls)

    assert errors == []
    assert len(allowed) == 1
    args = json.loads(
        allowed[0]["function"]["arguments"]
    )
    assert args["path"] == r"d:\projects\jack\src\engine.py"


def test_partition_materializes_workspace_for_pathless_ls_before_release():
    calls = [
        call(
            "call-ls",
            "ls",
            {},
        ),
    ]

    allowed, errors = kernel._phase4_partition_structured_tool_calls(calls)

    assert errors == []
    args = json.loads(
        allowed[0]["function"]["arguments"]
    )
    assert args["path"] == r"d:\projects\jack"
