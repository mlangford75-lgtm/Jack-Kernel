from __future__ import annotations

import json

import pytest

import jack_path_policy as paths
import jack_credential_resource_guard as credentials


def build(workspace=None, never=(), mode=None):
    payload = {"version": 1, "workspace_root": workspace, "never_paths": list(never)}
    if mode:
        payload.update(version=2, workspace_mode=mode)
    return paths.build_runtime_path_policy(
        runtime_id="posix-test", lane_id="posix-lane",
        raw_json=json.dumps(payload), host_environment={"HOME": "/home/operator"},
        path_style="posix",
    )


def test_posix_factory_allows_ordinary_development_and_temporary_paths():
    policy = build()
    assert policy.path_style == "posix" and policy.never_roots == ()
    for value in ("/tmp/clock.html", "/home/operator/project/clock.html", "/usr/bin/python"):
        assert paths.authorize_represented_path(policy, value).outcome is paths.PathAuthorizationOutcome.ALLOW


def test_posix_explicit_workspace_and_never_rules():
    policy = build("/home/operator/project", ["/home/operator/project/Private"])
    for value, expected in (
        ("clock.html", paths.PathAuthorizationOutcome.ALLOW),
        ("../project-other/clock.html", paths.PathAuthorizationOutcome.DENY_AND_CONTINUE),
        ("Private/file", paths.PathAuthorizationOutcome.HARD_INTERRUPT),
        ("private/file", paths.PathAuthorizationOutcome.ALLOW),
    ):
        assert paths.authorize_represented_path(
            policy, value, executor_cwd="/home/operator/project",
        ).outcome is expected


def test_posix_structured_release_keeps_literal_path_spelling():
    active = build("/home/operator/project")
    call = {"function": {"name": "write", "arguments": {"path": "a: b ", "content": "x"}}}
    actual = paths.rewrite_structured_tool_call_for_workspace_release(active, call)
    assert json.loads(actual["function"]["arguments"])["path"] == "/home/operator/project/a: b "


def test_posix_credential_resource_identity_preserves_case(monkeypatch):
    active = build()
    canonical = credentials._canonical_resource_path("/home/Operator/.jack-kernel/config.json")
    assert canonical == "/home/Operator/.jack-kernel/config.json"
    resource = credentials.ProtectedCredentialResource(credentials.RESOURCE_JACK_CURRENT_CONFIG, canonical)
    key = (active.runtime_id, active.lane_id)
    monkeypatch.setitem(credentials._RESOURCE_POLICIES, key,
        credentials.RuntimeCredentialResourcePolicy(*key, (resource,)))
    assert credentials.fact_for_canonical_target(active, canonical).protected
    assert not credentials.fact_for_canonical_target(active, canonical.replace("Operator", "operator")).protected


@pytest.mark.parametrize("command", ["ls -la .", "python -c 'print(42)'", "unknown-developer-tool", "ls -la /tmp"])
def test_posix_standard_does_not_require_parser_completeness(command):
    active = build()
    call = {"function": {"name": "bash", "arguments": {"command": command}}}
    result, applied = paths.authorize_executor_tool_call(
        active, call, executor_cwd="/home/operator/project", executor_platform="linux",
    )
    assert applied and result.outcome is paths.PathAuthorizationOutcome.ALLOW


def test_standard_structured_optional_path_defers_missing_executor_context(monkeypatch):
    import jack_kernel as kernel
    active = build()
    monkeypatch.setattr(kernel, "_RUNTIME_PATH_POLICY", active)
    token = kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.set(None)
    try:
        call = {"id": "ls", "function": {"name": "ls", "arguments": "{}"}}
        allowed, errors = kernel._phase4_partition_structured_tool_calls([call])
        assert allowed == [call] and not errors
    finally:
        kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.reset(token)


def test_native_host_workspace_release_and_executor_admission(tmp_path, monkeypatch):
    """Exercise both Jack boundaries with native path spelling and no model."""
    import os
    import sys
    import jack_kernel as kernel

    workspace = tmp_path / "Agentic_Testing"
    workspace.mkdir()
    private = workspace / "Private"
    other = tmp_path / "Agentic_Testing-other"
    active = paths.build_runtime_path_policy(
        runtime_id=kernel.RUNTIME_ID, lane_id=kernel.LANE_ID,
        raw_json=json.dumps({
            "version": 2, "workspace_mode": "represented",
            "workspace_root": str(workspace), "never_paths": [str(private)],
        }),
    )
    assert active.path_style == ("windows" if os.name == "nt" else "posix")
    monkeypatch.setattr(kernel, "_RUNTIME_PATH_POLICY", active)
    context = kernel.Phase4ExecutorRequestContext(
        protocol_version=1, runtime_id=kernel.RUNTIME_ID, lane_id=kernel.LANE_ID,
        cwd=str(workspace), platform=sys.platform, adapter="native-test",
    )
    token = kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.set(context)
    try:
        def command_call(command):
            return {"id": "native", "type": "function", "function": {
                "name": "bash", "arguments": json.dumps({"command": command})}}
        for command in ("ls -la .", "python -c 'print(42)'", "unknown-developer-tool"):
            call = command_call(command)
            allowed, errors = kernel._phase4_partition_structured_tool_calls([call])
            assert allowed == [call] and not errors
            result, applied = paths.authorize_executor_tool_call(
                active, allowed[0], executor_cwd=str(workspace),
                executor_platform=sys.platform, command_dialect="bash",
            )
            assert applied and result.outcome is paths.PathAuthorizationOutcome.ALLOW

        write = {"id": "write", "type": "function", "function": {
            "name": "write", "arguments": json.dumps({"path": "clock.html", "content": "clock"})}}
        allowed, errors = kernel._phase4_partition_structured_tool_calls([write])
        assert len(allowed) == 1 and not errors
        assert json.loads(allowed[0]["function"]["arguments"])["path"] == active.normalize(str(workspace / "clock.html"))
        result, applied = paths.authorize_executor_tool_call(
            active, allowed[0], executor_cwd=str(workspace),
            executor_platform=sys.platform,
        )
        assert applied and result.outcome is paths.PathAuthorizationOutcome.ALLOW
        for target in (other, private):
            call = command_call('ls -la "' + target.as_posix() + '"')
            if target == private:
                with pytest.raises(kernel.Phase4RestrictedPathInterrupt):
                    kernel._phase4_partition_structured_tool_calls([call])
            else:
                allowed, errors = kernel._phase4_partition_structured_tool_calls([call])
                assert not allowed and errors
    finally:
        kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.reset(token)


@pytest.mark.parametrize("field", ["Private ", " Private", " "])
def test_posix_structured_literal_spaces_preserve_never_identity(field):
    root = "/home/operator/project"
    active = build(root, [root + "/" + field])
    call = {"function": {"name": "read", "arguments": {"path": field}}}
    rewritten = paths.rewrite_structured_tool_call_for_workspace_release(active, call)
    assert json.loads(rewritten["function"]["arguments"])["path"] == root + "/" + field
    for candidate in (call, rewritten):
        decision, applied = paths.authorize_executor_tool_call(active, candidate, executor_cwd=root)
        assert applied and decision.outcome is paths.PathAuthorizationOutcome.HARD_INTERRUPT


@pytest.mark.parametrize("invalid", ["", None, 5, []])
def test_optional_explicit_invalid_path_does_not_become_workspace_default(invalid):
    active = build("/home/operator/project")
    call = {"function": {"name": "ls", "arguments": {"path": invalid}}}
    rewritten = paths.rewrite_structured_tool_call_for_workspace_release(active, call)
    assert json.loads(rewritten["function"]["arguments"])["path"] == invalid
    assert paths.authorize_structured_tool_call(active, rewritten).outcome is paths.PathAuthorizationOutcome.DENY_AND_CONTINUE
