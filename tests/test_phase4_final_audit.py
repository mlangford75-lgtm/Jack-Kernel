from __future__ import annotations

import asyncio
import json

import pytest
from starlette.requests import Request

import jack_kernel as kernel
import jack_path_policy as policy


HOST_ENV = {
    "SystemRoot": r"C:\Windows",
    "WINDIR": r"C:\Windows",
    "SystemDrive": "C:",
    "USERPROFILE": r"C:\Users\Operator",
    "HOME": r"C:\Users\Operator",
}


def build(*, workspace=r"D:\Projects\Jack", never=()):
    return policy.build_runtime_path_policy(
        runtime_id=kernel.RUNTIME_ID,
        lane_id=kernel.LANE_ID,
        raw_json=json.dumps(
            {
                "version": 1,
                "workspace_root": workspace,
                "never_paths": list(never),
            }
        ),
        host_environment=HOST_ENV,
    )


def command_call(command, *, name="bash"):
    return {
        "id": "call-command",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps({"command": command}),
        },
    }


def read_call(path, *, call_id="call-read"):
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": "read",
            "arguments": json.dumps({"path": path}),
        },
    }


@pytest.mark.parametrize(
    "command",
    (
        r"cat /c/Windows/System32/cmd.exe",
        r"cat /mnt/c/Windows/System32/cmd.exe",
        r"cat /cygdrive/c/Windows/System32/cmd.exe",
        r"cat $WINDIR/System32/cmd.exe",
        'bash -c "cat /c/Windows/System32/cmd.exe"',
        r"command cat /c/Windows/System32/cmd.exe",
        r"exec cat /c/Windows/System32/cmd.exe",
        r"nohup cat /c/Windows/System32/cmd.exe",
    ),
)
def test_windows_bash_representations_of_never_are_hard(command):
    decision = policy.authorize_command_tool_call(
        build(workspace=None),
        command_call(command),
        executor_cwd=r"D:\Work",
        command_dialect="bash",
        executor_platform="win32",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.HARD_INTERRUPT


def test_nested_powershell_literal_never_is_hard():
    decision = policy.authorize_command_tool_call(
        build(workspace=None),
        command_call(
            r'pwsh -Command "Get-Content C:\Windows\System32\drivers\etc\hosts"',
            name="powershell",
        ),
        executor_cwd=r"D:\Work",
        command_dialect="powershell",
        executor_platform="win32",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.HARD_INTERRUPT


def test_unlocked_pathless_diagnostic_does_not_hard_on_never_cwd():
    decision = policy.authorize_command_tool_call(
        build(workspace=None),
        command_call("Get-Process", name="powershell"),
        executor_cwd=r"C:\Windows",
        command_dialect="powershell",
        executor_platform="win32",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW


def test_workspace_command_without_executor_context_is_recoverably_denied(monkeypatch):
    original = kernel._RUNTIME_PATH_POLICY
    kernel._RUNTIME_PATH_POLICY = build()
    try:
        allowed, errors = kernel._phase4_partition_structured_tool_calls(
            [command_call("git status")]
        )
    finally:
        kernel._RUNTIME_PATH_POLICY = original

    assert allowed == []
    assert len(errors) == 1


def test_workspace_command_with_executor_context_is_releasable(monkeypatch):
    original = kernel._RUNTIME_PATH_POLICY
    kernel._RUNTIME_PATH_POLICY = build()
    ctx = kernel.Phase4ExecutorRequestContext(
        protocol_version=1,
        runtime_id=kernel.RUNTIME_ID,
        lane_id=kernel.LANE_ID,
        cwd=r"D:\Projects\Jack",
        platform="win32",
        adapter="test",
        command_dialect="bash",
    )
    token = kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.set(ctx)
    try:
        allowed, errors = kernel._phase4_partition_structured_tool_calls(
            [command_call("git status")]
        )
    finally:
        kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.reset(token)
        kernel._RUNTIME_PATH_POLICY = original

    assert [item["id"] for item in allowed] == ["call-command"]
    assert errors == []


def test_generic_shell_can_be_bound_by_transport_dialect(monkeypatch):
    original = kernel._RUNTIME_PATH_POLICY
    kernel._RUNTIME_PATH_POLICY = build()
    generic = command_call("git status", name="shell")
    ctx = kernel.Phase4ExecutorRequestContext(
        protocol_version=1,
        runtime_id=kernel.RUNTIME_ID,
        lane_id=kernel.LANE_ID,
        cwd=r"D:\Projects\Jack",
        platform="win32",
        adapter="test",
        command_dialect="bash",
    )
    token = kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.set(ctx)
    try:
        allowed, errors = kernel._phase4_partition_structured_tool_calls([generic])
    finally:
        kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.reset(token)
        kernel._RUNTIME_PATH_POLICY = original

    assert [item["id"] for item in allowed] == ["call-command"]
    assert errors == []


def admission_payload(*, tool_name="read", arguments=None, lane_id=None):
    return {
        "protocol_version": 1,
        "runtime_id": kernel.RUNTIME_ID,
        "lane_id": lane_id or kernel.LANE_ID,
        "tool_call_id": "call-read",
        "tool_name": tool_name,
        "arguments": arguments or {"path": r"D:\Projects\Jack\README.md"},
        "executor_cwd": r"D:\Projects\Jack",
        "executor_platform": "win32",
    }


def expected_read_call():
    return read_call(r"D:\Projects\Jack\README.md")


def test_executor_admission_binds_to_exact_released_arguments(monkeypatch):
    original = kernel._RUNTIME_PATH_POLICY
    kernel._RUNTIME_PATH_POLICY = build()
    try:
        result = kernel._phase4_executor_admission_decision(
            admission_payload(),
            expected_call=expected_read_call(),
        )
    finally:
        kernel._RUNTIME_PATH_POLICY = original

    assert result["outcome"] == "ALLOW"


@pytest.mark.parametrize(
    "payload",
    (
        admission_payload(tool_name="write"),
        admission_payload(arguments={"path": r"D:\Projects\Jack\other.txt"}),
    ),
)
def test_executor_admission_rejects_released_call_substitution(monkeypatch, payload):
    original = kernel._RUNTIME_PATH_POLICY
    kernel._RUNTIME_PATH_POLICY = build()
    try:
        with pytest.raises(kernel.HTTPException) as caught:
            kernel._phase4_executor_admission_decision(
                payload,
                expected_call=expected_read_call(),
            )
    finally:
        kernel._RUNTIME_PATH_POLICY = original

    assert caught.value.status_code == 409


def test_executor_admission_binds_lane(monkeypatch):
    original = kernel._RUNTIME_PATH_POLICY
    kernel._RUNTIME_PATH_POLICY = build()
    try:
        with pytest.raises(kernel.HTTPException) as caught:
            kernel._phase4_executor_admission_decision(
                admission_payload(lane_id="wrong-lane"),
                expected_call=expected_read_call(),
            )
    finally:
        kernel._RUNTIME_PATH_POLICY = original

    assert caught.value.status_code == 409


def request_with_headers(headers):
    encoded = [
        (str(key).lower().encode("latin-1"), str(value).encode("latin-1"))
        for key, value in headers.items()
    ]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/completions",
            "headers": encoded,
            "query_string": b"",
            "server": ("127.0.0.1", 8001),
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
        }
    )


def executor_headers(**overrides):
    values = {
        "X-Jack-Executor-Admission-Version": "1",
        "X-Jack-Executor-Runtime-Id": kernel.RUNTIME_ID,
        "X-Jack-Executor-Lane-Id": kernel.LANE_ID,
        "X-Jack-Executor-Cwd": r"D:\Projects\Jack",
        "X-Jack-Executor-Platform": "win32",
        "X-Jack-Executor-Adapter": "test",
        "X-Jack-Executor-Command-Dialect": "bash",
    }
    values.update(overrides)
    return values


def test_transport_context_is_runtime_lane_and_dialect_bound():
    ctx = kernel._phase4_executor_context_from_request(
        request_with_headers(executor_headers())
    )

    assert ctx is not None
    assert ctx.runtime_id == kernel.RUNTIME_ID
    assert ctx.lane_id == kernel.LANE_ID
    assert ctx.cwd == r"D:\Projects\Jack"
    assert ctx.platform == "win32"
    assert ctx.command_dialect == "bash"


def test_incomplete_transport_context_is_rejected():
    headers = executor_headers()
    del headers["X-Jack-Executor-Cwd"]

    with pytest.raises(kernel.HTTPException) as caught:
        kernel._phase4_executor_context_from_request(
            request_with_headers(headers)
        )

    assert caught.value.status_code == 400


def test_wrong_transport_lane_is_rejected():
    with pytest.raises(kernel.HTTPException) as caught:
        kernel._phase4_executor_context_from_request(
            request_with_headers(
                executor_headers(**{"X-Jack-Executor-Lane-Id": "wrong-lane"})
            )
        )

    assert caught.value.status_code == 409


def test_pending_snapshot_returns_exact_released_call():
    jack = kernel.JackQwenKernel(object(), kernel.CFG)
    released = expected_read_call()
    state = kernel.PendingToolResume(
        resume_id="resume",
        stage_key="thesis",
        history=[{"role": "assistant", "content": "", "tool_calls": [released]}],
        secondary_system="",
        usage={},
        tools=None,
        tool_choice=None,
        expected_tool_call_ids=("call-read",),
        created_at=10**12,
    )
    jack._pending_tool_resumes["call-read"] = state

    snapshot = asyncio.run(
        jack._phase4_pending_tool_call_snapshot("call-read")
    )

    assert snapshot == released
    assert snapshot is not released


def test_missing_transport_context_preserves_ordinary_clients():
    assert kernel._phase4_executor_context_from_request(
        request_with_headers({})
    ) is None


def test_evidence_guard_preserves_executor_context_call_signature():
    import inspect
    import jack_evidence_guard

    source = inspect.getsource(jack_evidence_guard.install)
    assert "*args: Any" in source
    assert "**kwargs: Any" in source
    assert "original_run(" in source
    assert "original_stream(" in source


def test_responses_compat_forwards_executor_context_to_both_transports():
    import inspect
    import jack_responses_compat

    stream_source = inspect.getsource(jack_responses_compat._stream)
    register_source = inspect.getsource(jack_responses_compat.register)

    assert "executor_context=executor_context" in stream_source
    assert "_phase4_executor_context_from_request" in register_source
    assert "executor_context=executor_context" in register_source
