from __future__ import annotations

import json
from dataclasses import replace

import pytest

import jack_path_policy as path
from jack_executor_contract import (
    ExecutorCapability, ExecutorPolicyBinding, ExecutorQualification,
    FilesystemProtection, STRICT_CAPABILITIES, require_strict_qualification,
)


def policy(mode=None, workspace=r"D:\Projects\Jack"):
    payload = {"version": 1, "workspace_root": workspace,
               "never_paths": [r"D:\Sensitive"]}
    if mode is not None:
        payload.update(version=2, workspace_mode=mode)
    return path.build_runtime_path_policy(
        runtime_id="runtime", lane_id="lane", raw_json=json.dumps(payload),
        host_environment={"SystemRoot": r"C:\Windows", "SystemDrive": "C:"},
    )


def authorize(active, command):
    call = {"function": {"name": "bash", "arguments": {"command": command}}}
    return path.authorize_executor_tool_call(
        active, call, executor_cwd=r"D:\Projects\Jack",
        command_dialect="bash", executor_platform="win32",
    )[0].outcome


@pytest.mark.parametrize("command", [
    "unknown-developer-tool",
    "python -c 'print(42)'",
    "echo ready\nunknown-developer-tool",
    "git clone https://example.invalid/project project",
    "cat clock*.html",
])
def test_opt_in_represented_command_coverage(command):
    assert authorize(policy("represented"), command) is path.PathAuthorizationOutcome.ALLOW
    assert authorize(policy(), command) is path.PathAuthorizationOutcome.DENY_AND_CONTINUE
    assert authorize(policy(workspace=None), command) is path.PathAuthorizationOutcome.ALLOW


@pytest.mark.parametrize("command, expected", [
    ("unknown-developer-tool D:/Other/file.txt", path.PathAuthorizationOutcome.DENY_AND_CONTINUE),
    ("unknown-developer-tool D:/Sensitive/file.txt", path.PathAuthorizationOutcome.HARD_INTERRUPT),
    ("cat ../Other/file.txt", path.PathAuthorizationOutcome.DENY_AND_CONTINUE),
    ("rm C:/Boot/BCD", path.PathAuthorizationOutcome.HARD_INTERRUPT),
])
def test_represented_mode_keeps_positive_path_authority(command, expected):
    assert authorize(policy("represented"), command) is expected


def test_modes_are_explicit_and_strict_is_not_emulated():
    assert policy(workspace=None).filesystem_protection is FilesystemProtection.STANDARD
    assert policy().filesystem_protection is FilesystemProtection.BOUNDED
    assert policy("represented").filesystem_protection is FilesystemProtection.REPRESENTED
    with pytest.raises(RuntimeError, match="no qualified adapter"):
        policy("strict")
    with pytest.raises(RuntimeError, match="requires a workspace"):
        policy("represented", workspace=None)
    with pytest.raises(RuntimeError, match="unsupported workspace"):
        policy("invented")


def test_strict_negotiation_is_exact_and_platform_independent():
    binding = ExecutorPolicyBinding("rt", "lane", "policy-identity", FilesystemProtection.STRICT)
    record = ExecutorQualification("trusted-adapter", binding, STRICT_CAPABILITIES)
    require_strict_qualification(binding, record)
    for bad in (
        None, replace(record, binding=replace(binding, lane_id="other")),
        replace(record, binding=replace(binding, policy_identity="stale")),
        replace(record, capabilities=STRICT_CAPABILITIES - {ExecutorCapability.CHILD_PROCESS_CONTAINMENT}),
        replace(record, executor_id=""),
    ):
        with pytest.raises(RuntimeError):
            require_strict_qualification(binding, bad)


def test_policy_integrity_material_distinguishes_modes():
    from jack_policy_integrity import _canonical_material
    assert _canonical_material("path", policy(), b"x" * 32) != _canonical_material(
        "path", policy("represented"), b"x" * 32,
    )


def custom_policy(entries):
    return path.build_runtime_path_policy(
        runtime_id="runtime", lane_id="lane", raw_json=json.dumps({
            "version": 2, "workspace_mode": "represented",
            "workspace_root": "/work", "never_paths": ["/work/Private"],
        }), path_style="posix", host_environment={},
        tool_contracts_json=json.dumps({"version": 1, "tools": entries}),
    )


def custom_contract(name="inspect_format", operation="inspect"):
    return {"name": name, "operation": operation,
            "path_fields": ["filename"], "argument_types": {"filename": "string", "limit": "integer"},
            "required_fields": ["filename"]}


def test_custom_host_contract_applies_to_rewrite_and_admission():
    active = custom_policy([custom_contract()])
    for value, expected in (
        ("clock.html", path.PathAuthorizationOutcome.ALLOW),
        ("../other", path.PathAuthorizationOutcome.DENY_AND_CONTINUE),
        ("Private/file", path.PathAuthorizationOutcome.HARD_INTERRUPT),
    ):
        call = {"function": {"name": "inspect_format", "arguments": {"filename": value, "limit": 5}}}
        rewritten = path.rewrite_structured_tool_call_for_workspace_release(active, call)
        assert json.loads(rewritten["function"]["arguments"])["filename"].startswith("/")
        for candidate in (call, rewritten):
            decision, applied = path.authorize_executor_tool_call(active, candidate, executor_cwd="/work")
            assert applied and decision.outcome is expected


@pytest.mark.parametrize("arguments", [{}, {"filename": 4}, {"filename": "ok", "limit": True},
                                       {"filename": "ok", "alternate": "/work/Private"}])
def test_custom_contract_rejects_malformed_or_unknown_argument_fields(arguments):
    active = custom_policy([custom_contract()])
    decision, applied = path.authorize_executor_tool_call(active,
        {"function": {"name": "inspect_format", "arguments": arguments}}, executor_cwd="/work")
    assert applied and decision.outcome is path.PathAuthorizationOutcome.DENY_AND_CONTINUE


def test_unregistered_tool_does_not_claim_path_coverage():
    active = custom_policy([])
    decision, applied = path.authorize_executor_tool_call(active,
        {"function": {"name": "inspect_format", "arguments": {"filename": "/work/Private"}}})
    assert not applied


@pytest.mark.parametrize("entries", [
    [custom_contract("read")], [custom_contract("bash")],
    [custom_contract(), custom_contract("INSPECT_FORMAT")],
    [dict(custom_contract(), operation="self_declared")],
    [dict(custom_contract(), required_fields=[])],
    [dict(custom_contract(), argument_types={"filename": "object"})],
])
def test_custom_contract_registry_rejects_ambiguous_or_unsupported_schema(entries):
    with pytest.raises(RuntimeError, match="Invalid host-owned structured tool contract registry"):
        custom_policy(entries)


def test_custom_contract_is_sealed_and_drives_debugging_classification(monkeypatch):
    import jack_kernel as kernel
    from jack_policy_integrity import _canonical_material
    active = custom_policy([custom_contract(), custom_contract("perform_operation", "mutate")])
    monkeypatch.setattr(kernel, "_RUNTIME_PATH_POLICY", active)
    assert _canonical_material("path", active, b"x" * 32) != _canonical_material("path", custom_policy([]), b"x" * 32)
    assert kernel._debugging_tool_is_direct_mutator({"function": {"name": "inspect_format"}})
    declaration = {"function": {"name": "inspect_format", "parameters": {
        "type": "object", "properties": {"filename": {"type": "string"}, "limit": {"type": "integer"}},
        "required": ["filename"],
    }}}
    assert not kernel._debugging_tool_is_direct_mutator(declaration)
    declaration["function"]["parameters"]["properties"]["limit"]["type"] = "string"
    assert kernel._debugging_tool_is_direct_mutator(declaration)
    assert kernel._debugging_tool_is_direct_mutator({"function": {"name": "perform_operation"}})
    assert kernel._debugging_tool_is_direct_mutator({"function": {"name": "unregistered_format"}})
