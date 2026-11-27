from __future__ import annotations

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
                "never_paths": [r"D:\Sensitive"],
            }
        ),
        host_environment=HOST_ENV,
    )
    yield
    kernel._RUNTIME_PATH_POLICY = original


def payload(
    tool_name,
    arguments,
    *,
    cwd=r"D:\Projects\Jack",
    runtime_id=None,
    lane_id=None,
    platform="win32",
):
    return {
        "protocol_version": 1,
        "runtime_id": runtime_id or kernel.RUNTIME_ID,
        "lane_id": lane_id or kernel.LANE_ID,
        "tool_call_id": "call-executor-admission",
        "tool_name": tool_name,
        "arguments": arguments,
        "executor_cwd": cwd,
        "executor_platform": platform,
    }


def test_executor_admission_allows_relative_read_inside_workspace():
    decision = kernel._phase4_executor_admission_decision(
        payload("read", {"path": r"src\engine.py"})
    )
    assert decision["outcome"] == "ALLOW"
    assert decision["runtime_id"] == kernel.RUNTIME_ID
    assert decision["lane_id"] == kernel.LANE_ID
    assert decision["contract_applied"] is True


def test_executor_admission_denies_relative_read_from_outside_cwd():
    decision = kernel._phase4_executor_admission_decision(
        payload(
            "read",
            {"path": r"src\engine.py"},
            cwd=r"D:\OtherProject",
        )
    )
    assert decision["outcome"] == "DENY_AND_CONTINUE"


def test_executor_admission_hard_interrupts_relative_never_target():
    decision = kernel._phase4_executor_admission_decision(
        payload(
            "read",
            {"path": r"..\Sensitive\secret.txt"},
            cwd=r"D:\Work",
        )
    )
    assert decision["outcome"] == "HARD_INTERRUPT"


def test_executor_admission_pathless_ls_is_bound_to_actual_cwd():
    decision = kernel._phase4_executor_admission_decision(
        payload("ls", {}, cwd=r"D:\OtherProject")
    )
    assert decision["outcome"] == "DENY_AND_CONTINUE"


def test_executor_admission_rejects_policy_injection_fields():
    forged = payload("read", {"path": r"src\engine.py"})
    forged["workspace_root"] = r"C:\\"

    with pytest.raises(kernel.HTTPException) as caught:
        kernel._phase4_executor_admission_decision(forged)

    assert caught.value.status_code == 400
    assert "unsupported fields" in str(caught.value.detail)


def test_executor_admission_rejects_wrong_runtime_identity():
    with pytest.raises(kernel.HTTPException) as caught:
        kernel._phase4_executor_admission_decision(
            payload(
                "read",
                {"path": r"src\engine.py"},
                runtime_id="wrong-runtime",
            )
        )
    assert caught.value.status_code == 409


def test_bash_command_tool_is_governed_by_the_command_contract():
    decision = kernel._phase4_executor_admission_decision(
        payload("bash", {"command": "git status"})
    )
    assert decision["outcome"] == "ALLOW"
    assert decision["contract_applied"] is True


def test_pre_release_phase4_defers_relative_structured_target_to_executor():
    call = {
        "id": "call-relative",
        "type": "function",
        "function": {
            "name": "read",
            "arguments": json.dumps({"path": r"src\engine.py"}),
        },
    }
    assert kernel._phase4_structured_tool_authorization_errors([call]) == []
