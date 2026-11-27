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
        assert not kernel._immutable_path_denial(errors)
        assert "no forbidden target was established" in errors[0]
        assert "explicit authorized target" in errors[0]
        notice = kernel._tool_rejection_notice(errors, "Agentic native pass 1")
        assert "immutable host security denial" not in notice["content"]
        assert "correct the invocation" in notice["content"]

        # A new explicit proposal must independently pass the same gate.
        call["function"]["arguments"] = json.dumps({
            "command": "ls -la " + workspace.replace("\\", "/")
        })
        allowed, errors = kernel._phase4_partition_structured_tool_calls([call])
        assert allowed == [call] and not errors

        # A positive outside-workspace target is not a correctable contract error.
        call["function"]["arguments"] = json.dumps({
            "command": "ls -la C:/Outside"
        })
        allowed, errors = kernel._phase4_partition_structured_tool_calls([call])
        assert not allowed and kernel._immutable_path_denial(errors)
    finally:
        kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.reset(token)


def test_literal_bash_home_operand_is_bound_before_release_and_executor_admission(
    installed_path_gate, monkeypatch,
):
    workspace = r"C:\Users\Operator\Desktop\Project"
    active = path_policy.build_runtime_path_policy(
        runtime_id=kernel.RUNTIME_ID, lane_id=kernel.LANE_ID,
        raw_json=json.dumps({"version": 1, "workspace_root": workspace,
                             "never_paths": [workspace + r"\Private"]}),
        host_environment=HOST_ENV,
    )
    monkeypatch.setattr(kernel, "_RUNTIME_PATH_POLICY", active)
    context = kernel.Phase4ExecutorRequestContext(
        protocol_version=1, runtime_id=kernel.RUNTIME_ID, lane_id=kernel.LANE_ID,
        cwd=workspace, platform="win32", adapter="test",
    )
    token = kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.set(context)
    def command_call(command):
        return {"id": "listing", "type": "function", "function": {
            "name": "bash", "arguments": json.dumps({"command": command})}}
    try:
        original = command_call("ls -la ~/Desktop/Project/clock.html")
        allowed, errors = kernel._phase4_partition_structured_tool_calls([original])
        assert len(allowed) == 1 and not errors
        assert json.loads(original["function"]["arguments"])["command"].startswith("ls -la ~/")
        assert json.loads(allowed[0]["function"]["arguments"])["command"] == (
            "ls -la c:/users/operator/Desktop/Project/clock.html"
        )
        decision, applied = path_policy.authorize_executor_tool_call(
            active, allowed[0], executor_cwd=workspace,
            command_dialect="bash", executor_platform="win32",
        )
        assert applied and decision.outcome is path_policy.PathAuthorizationOutcome.ALLOW
        allowed, errors = kernel._phase4_partition_structured_tool_calls(
            [command_call("ls -la ~/Desktop/Other")]
        )
        assert not allowed and errors
        with pytest.raises(kernel.Phase4RestrictedPathInterrupt):
            kernel._phase4_partition_structured_tool_calls(
                [command_call("ls -la ~/Desktop/Project/Private")]
            )
        for unresolved in (
            "ls -la ~another/Desktop/Project",
            "ls -la '~/Desktop/Project'",
            "ls -la \\\\~/Desktop/Project",
            "ls -la ~/Desktop/Project/*",
            "env HOME=/other ls -la ~/Desktop/Project",
            "ls -la ~/Desktop/Project; pwd",
        ):
            call = command_call(unresolved)
            assert path_policy.rewrite_literal_bash_home_call_for_workspace_release(
                active, call, executor_platform="win32"
            ) == call
    finally:
        kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.reset(token)


@pytest.mark.parametrize("command", ["Get-Location", "gl", "pwd", "Get-Item clock.html", "gi clock.html"])
def test_powershell_ordinary_workspace_metadata_remains_usable(
    installed_path_gate, command,
):
    active = build()
    call = {"type": "function", "function": {"name": "powershell",
            "arguments": json.dumps({"command": command})}}
    decision, applied = path_policy.authorize_executor_tool_call(
        active, call, executor_cwd=r"D:\Projects\Jack", command_dialect="powershell",
    )
    assert applied and decision.outcome is path_policy.PathAuthorizationOutcome.ALLOW


@pytest.mark.parametrize("command, expected", [
    (r"Get-Item D:\Outside\file.txt", path_policy.PathAuthorizationOutcome.DENY_AND_CONTINUE),
    (r"Get-Item D:\Sensitive\file.txt", path_policy.PathAuthorizationOutcome.HARD_INTERRUPT),
])
def test_powershell_metadata_does_not_relax_path_policy(
    installed_path_gate, command, expected,
):
    call = {"type": "function", "function": {"name": "powershell",
            "arguments": json.dumps({"command": command})}}
    decision, applied = path_policy.authorize_executor_tool_call(
        build(), call, executor_cwd=r"D:\Projects\Jack", command_dialect="powershell",
    )
    assert applied and decision.outcome is expected


def test_malformed_ads_with_credential_authority_preserves_sibling(installed_path_gate, monkeypatch):
    import jack_credential_resource_guard as resources

    active = build()
    key = (active.runtime_id, active.lane_id)
    resource = resources.ProtectedCredentialResource(
        resources.RESOURCE_JACK_CONFIG, r"d:\projects\jack\config.json")
    monkeypatch.setitem(resources._RESOURCE_POLICIES, key,
        resources.RuntimeCredentialResourcePolicy(*key, (resource,)))
    malformed = r"D:\Projects\Jack\:stream"
    assert resources.fact_for_canonical_target(active, active.normalize(malformed)) is None
    assert path_policy.authorize_represented_path(active, malformed).outcome is path_policy.PathAuthorizationOutcome.DENY_AND_CONTINUE
    assert resources.fact_for_canonical_target(active, r"d:\projects\jack\config.json:$data").protected
    monkeypatch.setattr(kernel, "_RUNTIME_PATH_POLICY", active)
    def call(ident, path):
        return {"id": ident, "type": "function", "function": {
            "name": "read", "arguments": json.dumps({"path": path})}}
    allowed, errors = kernel._phase4_partition_structured_tool_calls([
        call("bad", malformed), call("good", "good.txt")])
    assert [item["id"] for item in allowed] == ["good"]
    assert len(errors) == 1


def test_unresolved_workspace_rewrite_routes_through_authority(installed_path_gate, monkeypatch):
    active = build()
    monkeypatch.setattr(kernel, "_RUNTIME_PATH_POLICY", active)
    observations = []
    monkeypatch.setattr(gate.authority_ledger, "record_represented_path_decision_failsoft",
                        lambda **facts: observations.append(facts))
    calls = [{"id": "bad", "type": "function", "function": {
        "name": "read", "arguments": json.dumps({"path": r"%UNKNOWN_ENV%\x.txt"})}},
        {"id": "good", "type": "function", "function": {
        "name": "read", "arguments": json.dumps({"path": "good.txt"})}}]
    allowed, errors = kernel._phase4_partition_structured_tool_calls(calls)
    assert [item["id"] for item in allowed] == ["good"]
    assert len(errors) == 1
    assert len(observations) == 2 and not observations[0]["deterministic"]
