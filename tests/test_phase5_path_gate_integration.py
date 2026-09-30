from __future__ import annotations

import json

import pytest

import jack_consequence_gate as gate
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
        raw_json=json.dumps(
            {
                "version": 1,
                "workspace_root": workspace,
                "never_paths": [r"D:\Sensitive"],
            }
        ),
        host_environment=HOST_ENV,
    )


@pytest.fixture
def installed_path_gate():
    original = path_policy.authorize_represented_path
    gate._install_represented_path_gate()
    try:
        yield
    finally:
        path_policy.authorize_represented_path = original


def test_gate_preserves_never_hard_interrupt(installed_path_gate):
    decision = path_policy.authorize_represented_path(
        build(),
        r"D:\Sensitive\secret.txt",
    )
    assert decision.outcome is path_policy.PathAuthorizationOutcome.HARD_INTERRUPT


def test_gate_preserves_workspace_narrow_denial(installed_path_gate):
    decision = path_policy.authorize_represented_path(
        build(),
        r"D:\Other\artifact.txt",
    )
    assert decision.outcome is path_policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


def test_gate_preserves_inside_workspace_allow(installed_path_gate):
    decision = path_policy.authorize_represented_path(
        build(),
        r"D:\Projects\Jack\src\engine.py",
    )
    assert decision.outcome is path_policy.PathAuthorizationOutcome.ALLOW


def test_gate_preserves_no_workspace_fail_soft_ambiguity(installed_path_gate):
    decision = path_policy.authorize_represented_path(
        build(None),
        r"relative\target.txt",
    )
    assert decision.outcome is path_policy.PathAuthorizationOutcome.ALLOW
    assert decision.canonical_target is None


def test_gate_preserves_workspace_relative_cwd_requirement(installed_path_gate):
    decision = path_policy.authorize_represented_path(
        build(),
        r"relative\target.txt",
    )
    assert decision.outcome is path_policy.PathAuthorizationOutcome.DENY_AND_CONTINUE
    assert decision.canonical_target is None


def test_gate_preserves_deferred_executor_cwd_admission(installed_path_gate):
    decision = path_policy.authorize_represented_path(
        build(),
        r"relative\target.txt",
        defer_relative_without_executor=True,
    )
    assert decision.outcome is path_policy.PathAuthorizationOutcome.ALLOW
    assert decision.canonical_target is None
    assert "executor cwd admission" in decision.reason


def test_gate_preserves_invalid_path_rejection_without_workspace(installed_path_gate):
    decision = path_policy.authorize_represented_path(
        build(None),
        "",
    )
    assert decision.outcome is path_policy.PathAuthorizationOutcome.DENY_AND_CONTINUE
