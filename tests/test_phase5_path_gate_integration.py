from __future__ import annotations

import inspect
import json

import pytest

import jack_consequence_gate as gate
import jack_kernel as kernel
import jack_path_policy as path_policy

HOST_ENV = {
    "SystemRoot": r"C:\Windows",
    "WINDIR": r"C:\Windows",
    "SystemDrive": "C:",
    "USERPROFILE": r"C:\Users\Operator",
}


def build(workspace=r"D:\Projects\Jack"):
    return path_policy.build_runtime_path_policy(
        runtime_id="phase5-test-runtime",
        lane_id="phase5-test-lane",
        raw_json=json.dumps({"version": 1, "workspace_root": workspace, "never_paths": [r"D:\Sensitive"]}),
        host_environment=HOST_ENV,
    )


@pytest.fixture
def installed_path_gate():
    original = path_policy.authorize_represented_path
    gate._install_represented_path_gate(gate._bound_evaluator(kernel.SecurityOutcome))
    try:
        yield
    finally:
        path_policy.authorize_represented_path = original


def test_path_policy_owns_single_raw_fact_producer():
    assert "inspect_operation_path(" in inspect.getsource(path_policy.authorize_represented_path)
    assert "path_policy.inspect_operation_path(" in inspect.getsource(gate._install_represented_path_gate)
    assert "inspect_represented_path(" in inspect.getsource(path_policy.inspect_operation_path)


def test_raw_facts_have_no_outcome():
    f = path_policy.inspect_represented_path(build(), r"D:\Sensitive\secret.txt")
    assert f.never_match is True
    assert not hasattr(f, "outcome")


def test_raw_workspace_membership_is_fact_not_disposition():
    f = path_policy.inspect_represented_path(build(), r"D:\Other\artifact.txt")
    assert f.inside_workspace is False
    assert f.deterministic is True


def test_raw_no_workspace_ambiguity_remains_nonviolation_fact():
    f = path_policy.inspect_represented_path(build(None), r"relative\target.txt")
    assert f.workspace_configured is False
    assert f.deterministic is False
    assert f.invalid is False


def test_legacy_phase4_never_mapping_is_preserved():
    assert path_policy.authorize_represented_path(build(), r"D:\Sensitive\secret.txt").outcome is path_policy.PathAuthorizationOutcome.HARD_INTERRUPT


def test_legacy_phase4_workspace_mapping_is_preserved():
    assert path_policy.authorize_represented_path(build(), r"D:\Other\artifact.txt").outcome is path_policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


def test_gate_preserves_never_mapping(installed_path_gate):
    assert path_policy.authorize_represented_path(build(), r"D:\Sensitive\secret.txt").outcome is path_policy.PathAuthorizationOutcome.HARD_INTERRUPT


def test_gate_preserves_workspace_denial(installed_path_gate):
    assert path_policy.authorize_represented_path(build(), r"D:\Other\artifact.txt").outcome is path_policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


def test_gate_preserves_inside_workspace_allow(installed_path_gate):
    assert path_policy.authorize_represented_path(build(), r"D:\Projects\Jack\src\engine.py").outcome is path_policy.PathAuthorizationOutcome.ALLOW


def test_gate_preserves_fail_soft_no_workspace_ambiguity(installed_path_gate):
    d = path_policy.authorize_represented_path(build(None), r"relative\target.txt")
    assert d.outcome is path_policy.PathAuthorizationOutcome.ALLOW
    assert d.canonical_target is None


def test_gate_preserves_workspace_relative_denial(installed_path_gate):
    d = path_policy.authorize_represented_path(build(), r"relative\target.txt")
    assert d.outcome is path_policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


def test_gate_preserves_executor_cwd_deferral(installed_path_gate):
    d = path_policy.authorize_represented_path(build(), r"relative\target.txt", defer_relative_without_executor=True)
    assert d.outcome is path_policy.PathAuthorizationOutcome.ALLOW
    assert "executor cwd admission" in d.reason


@pytest.mark.parametrize("dialect, command", [
    ("bash", r'touch "C:\Windows\Temp\jack-test.txt"'),
    ("powershell", r'New-Item -ItemType File -Path "C:\Windows\Temp\jack-test.txt"'),
])
def test_factory_temp_allowed_at_consequence_and_executor_gates(installed_path_gate, dialect, command):
    policy = build(None)
    call = {"type": "function", "function": {"name": dialect,
            "arguments": json.dumps({"command": command})}}
    result, applied = path_policy.authorize_executor_tool_call(
        policy, call, executor_cwd=r"D:\Projects\Jack", command_dialect=dialect,
    )
    assert applied
    assert result.outcome is path_policy.PathAuthorizationOutcome.ALLOW
    # The same target remains governed by an opted-in workspace lock.
    locked, applied = path_policy.authorize_executor_tool_call(
        build(), call, executor_cwd=r"D:\Projects\Jack", command_dialect=dialect,
    )
    assert applied
    assert locked.outcome is path_policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


@pytest.mark.parametrize("explicit", [r"C:\Windows", r"C:\Windows\Temp"])
def test_explicit_duplicate_root_is_authoritative_at_consequence_gate(installed_path_gate, explicit):
    policy = path_policy.build_runtime_path_policy(
        runtime_id="phase5-test-runtime", lane_id="phase5-test-lane",
        raw_json=json.dumps({"version": 1, "workspace_root": None, "never_paths": [explicit]}),
        host_environment=HOST_ENV,
    )
    for read in (False, True):
        result = path_policy.authorize_represented_path(
            policy, r"C:\Windows\Temp\jack-test.txt", verified_default_windows_read=read,
        )
        assert result.outcome is path_policy.PathAuthorizationOutcome.HARD_INTERRUPT

@pytest.mark.parametrize("command", [
    "ls -la",
    "ls -la .",
    "ls -a C:/Users/Operator.DESKTOP-TEST/Desktop/clock/Agentic_Testing",
    "ls -la C:/Users/Operator.DESKTOP-TEST/Desktop/clock/Agentic_Testing/index.html",
])
def test_workspace_listing_with_nested_never_at_live_release_gate(
    installed_path_gate, monkeypatch, command,
):
    workspace = r"C:\Users\Operator.DESKTOP-TEST\Desktop\clock\Agentic_Testing"
    active = path_policy.build_runtime_path_policy(
        runtime_id=kernel.RUNTIME_ID, lane_id=kernel.LANE_ID,
        raw_json=json.dumps({"version": 1, "workspace_root": workspace,
                             "never_paths": [workspace + r"\JackSecurityTest\restricted"]}),
        host_environment=HOST_ENV,
    )
    monkeypatch.setattr(kernel, "_RUNTIME_PATH_POLICY", active)
    context = kernel.Phase4ExecutorRequestContext(
        protocol_version=1, runtime_id=kernel.RUNTIME_ID, lane_id=kernel.LANE_ID,
        cwd=workspace, platform="win32", adapter="test",
    )
    token = kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.set(context)
    try:
        call = {"id": "listing", "type": "function", "function": {
            "name": "bash", "arguments": json.dumps({"command": command})}}
        allowed, errors = kernel._phase4_partition_structured_tool_calls([call])
        assert allowed == [call]
        assert not errors
        # Preserve explicit nested NEVER authority.
        protected = {"id": "protected", "type": "function", "function": {
            "name": "bash", "arguments": json.dumps({
                "command": "ls -la " + (workspace + r"\JackSecurityTest\restricted").replace("\\", "/")
            })}}
        with pytest.raises(kernel.Phase4RestrictedPathInterrupt):
            kernel._phase4_partition_structured_tool_calls([protected])
    finally:
        kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.reset(token)


def test_missing_executor_cwd_denial_logs_only_safe_category(
    installed_path_gate, monkeypatch, caplog,
):
    workspace = r"C:\Users\Operator.DESKTOP-TEST\Desktop\clock\Agentic_Testing"
    active = path_policy.build_runtime_path_policy(
        runtime_id=kernel.RUNTIME_ID, lane_id=kernel.LANE_ID,
        raw_json=json.dumps({"version": 1, "workspace_root": workspace,
                             "never_paths": []}),
        host_environment=HOST_ENV,
    )
    monkeypatch.setattr(kernel, "_RUNTIME_PATH_POLICY", active)
    token = kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.set(None)
    try:
        call = {"id": "listing", "type": "function", "function": {
            "name": "bash", "arguments": json.dumps({"command": "ls -la"})}}
        allowed, errors = kernel._phase4_partition_structured_tool_calls([call])
        assert not allowed and errors
        assert "reason=EXECUTOR_CWD_MISSING" in caplog.text
        assert workspace not in caplog.text
    finally:
        kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.reset(token)
