from __future__ import annotations

import json

import pytest

import jack_kernel as kernel
import jack_path_policy as policy


HOST_ENV = {
    "SystemRoot": r"C:\Windows",
    "WINDIR": r"C:\Windows",
    "SystemDrive": "C:",
    "USERPROFILE": r"C:\Users\Operator",
}


def build(*, workspace=r"D:\Projects\Jack", never=()):
    return policy.build_runtime_path_policy(
        runtime_id="runtime",
        lane_id="lane",
        raw_json=json.dumps(
            {
                "version": 1,
                "workspace_root": workspace,
                "never_paths": list(never),
            }
        ),
        host_environment=HOST_ENV,
    )


def call(name, command):
    return {
        "id": "call-command",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps({"command": command}),
        },
    }


@pytest.mark.parametrize(
    "command",
    (
        "git status",
        "git diff",
        "git diff -- jack_kernel.py",
        "pytest",
        "python -m pytest",
        "dotnet test",
    ),
)
def test_bash_common_workspace_scoped_developer_commands_remain_usable(command):
    decision = policy.authorize_command_tool_call(
        build(),
        call("bash", command),
        executor_cwd=r"D:\Projects\Jack",
        command_dialect="bash",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW


def test_bash_explicit_escape_is_recoverably_denied_under_workspace_lock():
    decision = policy.authorize_command_tool_call(
        build(),
        call("bash", "cat ../Outside/secret.txt"),
        executor_cwd=r"D:\Projects\Jack",
        command_dialect="bash",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


def test_bash_positive_never_target_is_hard():
    decision = policy.authorize_command_tool_call(
        build(workspace=None),
        call("bash", r'cat "C:\Windows\System32\drivers\etc\hosts"'),
        executor_cwd=r"D:\Projects\Jack",
        command_dialect="bash",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.HARD_INTERRUPT


def test_bash_dynamic_command_is_denied_only_when_workspace_lock_is_active():
    locked = policy.authorize_command_tool_call(
        build(),
        call("bash", 'cat "$(pwd)/file.txt"'),
        executor_cwd=r"D:\Projects\Jack",
        command_dialect="bash",
    )
    unlocked = policy.authorize_command_tool_call(
        build(workspace=None),
        call("bash", 'cat "$(pwd)/file.txt"'),
        executor_cwd=r"D:\Projects\Jack",
        command_dialect="bash",
    )

    assert locked.outcome is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE
    assert unlocked.outcome is policy.PathAuthorizationOutcome.ALLOW


@pytest.mark.parametrize(
    "command",
    (
        "Get-Process",
        "Get-Service",
        "Get-CimInstance Win32_OperatingSystem",
        "Get-Date",
    ),
)
def test_powershell_pathless_diagnostics_remain_usable_under_workspace_lock(command):
    decision = policy.authorize_command_tool_call(
        build(),
        call("powershell", command),
        executor_cwd=r"D:\Projects\Jack",
        command_dialect="powershell",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW


def test_powershell_relative_path_inside_workspace_is_allowed():
    decision = policy.authorize_command_tool_call(
        build(),
        call("powershell", r"Get-Content -LiteralPath .\README.md"),
        executor_cwd=r"D:\Projects\Jack",
        command_dialect="powershell",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW


def test_powershell_relative_escape_is_denied():
    decision = policy.authorize_command_tool_call(
        build(),
        call("powershell", r"Get-Content -LiteralPath ..\Outside\secret.txt"),
        executor_cwd=r"D:\Projects\Jack",
        command_dialect="powershell",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


def test_powershell_positive_never_target_is_hard():
    decision = policy.authorize_command_tool_call(
        build(workspace=None),
        call(
            "powershell",
            r'Get-Content -LiteralPath "C:\Windows\System32\drivers\etc\hosts"',
        ),
        executor_cwd=r"D:\Projects\Jack",
        command_dialect="powershell",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.HARD_INTERRUPT


def test_powershell_dynamic_variable_is_not_claimed_safe_under_workspace_lock():
    locked = policy.authorize_command_tool_call(
        build(),
        call("powershell", r"$p = '..\Outside\x'; Get-Content $p"),
        executor_cwd=r"D:\Projects\Jack",
        command_dialect="powershell",
    )
    unlocked = policy.authorize_command_tool_call(
        build(workspace=None),
        call("powershell", r"$p = '..\Outside\x'; Get-Content $p"),
        executor_cwd=r"D:\Projects\Jack",
        command_dialect="powershell",
    )

    assert locked.outcome is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE
    assert unlocked.outcome is policy.PathAuthorizationOutcome.ALLOW


def test_generic_command_tool_requires_explicit_executor_dialect():
    unknown = policy.extract_command_paths(
        "shell",
        {"command": "git status"},
    )
    bound = policy.extract_command_paths(
        "shell",
        {"command": "git status"},
        command_dialect="bash",
    )

    assert not unknown.applicable
    assert bound.applicable
    assert bound.dialect == "bash"


@pytest.fixture
def kernel_policy(monkeypatch):
    original = kernel._RUNTIME_PATH_POLICY
    kernel._RUNTIME_PATH_POLICY = policy.build_runtime_path_policy(
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


def admission(tool_name, command, dialect):
    return {
        "protocol_version": 1,
        "runtime_id": kernel.RUNTIME_ID,
        "lane_id": kernel.LANE_ID,
        "tool_call_id": "call-command-admission",
        "tool_name": tool_name,
        "arguments": {"command": command},
        "executor_cwd": r"D:\Projects\Jack",
        "executor_platform": "win32",
        "command_dialect": dialect,
    }


def test_executor_admission_applies_bash_contract(kernel_policy):
    decision = kernel._phase4_executor_admission_decision(
        admission("bash", "git status", "bash")
    )

    assert decision["outcome"] == "ALLOW"
    assert decision["contract_applied"] is True


def test_executor_admission_applies_powershell_contract(kernel_policy):
    decision = kernel._phase4_executor_admission_decision(
        admission("powershell", "Get-Process", "powershell")
    )

    assert decision["outcome"] == "ALLOW"
    assert decision["contract_applied"] is True


def test_command_dialect_is_executor_fact_not_policy_override(kernel_policy):
    forged = admission("bash", "git status", "bash")
    forged["workspace_root"] = None

    with pytest.raises(kernel.HTTPException) as caught:
        kernel._phase4_executor_admission_decision(forged)

    assert caught.value.status_code == 400


def test_static_never_target_wins_even_when_rest_of_bash_command_is_dynamic():
    decision = policy.authorize_command_tool_call(
        build(workspace=None),
        call(
            "bash",
            r'cat "C:\Windows\System32\cmd.exe" && echo "$HOME"',
        ),
        executor_cwd=r"D:\Ordinary",
        command_dialect="bash",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.HARD_INTERRUPT


def test_static_never_target_wins_even_when_rest_of_powershell_command_is_dynamic():
    decision = policy.authorize_command_tool_call(
        build(workspace=None),
        call(
            "powershell",
            r'Get-Content -LiteralPath "C:\Windows\System32\cmd.exe"; Write-Output $p',
        ),
        executor_cwd=r"D:\Ordinary",
        command_dialect="powershell",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.HARD_INTERRUPT


def test_pathless_diagnostic_does_not_hard_only_because_unlocked_cwd_is_restricted():
    decision = policy.authorize_command_tool_call(
        build(workspace=None),
        call("powershell", "Get-Process"),
        executor_cwd=r"C:\Windows",
        command_dialect="powershell",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW


def test_unsupported_command_dialect_is_rejected_by_executor_endpoint(kernel_policy):
    forged = admission("shell", "git status", "fish")

    with pytest.raises(kernel.HTTPException) as caught:
        kernel._phase4_executor_admission_decision(forged)

    assert caught.value.status_code == 400


@pytest.mark.parametrize(
    "command",
    (
        "env FOO=1 cat ../Outside/secret.txt",
        "echo ok & cat ../Outside/secret.txt",
        "echo ok\ncat ../Outside/secret.txt",
        "cat ~/secret.txt",
        "cat {../Outside,foo}/secret.txt",
        "git clone https://example.invalid/repo ../Outside",
        "git config --global user.name Jack",
        "pytest --basetemp=../Outside",
        "python -m pytest --basetemp=../Outside",
        "dotnet test --results-directory=../Outside",
        "dotnet test --output=../Outside",
        "cp --target-directory=../Outside README.md",
    ),
)
def test_bash_adversarial_forms_do_not_bypass_workspace_lock(command):
    decision = policy.authorize_command_tool_call(
        build(),
        call("bash", command),
        executor_cwd=r"D:\Projects\Jack",
        command_dialect="bash",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


@pytest.mark.parametrize(
    "command",
    (
        "echo ok\nprintenv",
        "cat ~/secret.txt",
        "cat {../Outside,foo}/secret.txt",
        "git clone https://example.invalid/repo ../Outside",
        "git config --global user.name Jack",
    ),
)
def test_bash_ambiguous_forms_remain_usable_when_workspace_lock_is_off(command):
    decision = policy.authorize_command_tool_call(
        build(workspace=None),
        call("bash", command),
        executor_cwd=r"D:\Ordinary",
        command_dialect="bash",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW


def test_bash_env_wrapper_is_evaluated_not_treated_as_pathless():
    decision = policy.authorize_command_tool_call(
        build(),
        call("bash", "env FOO=1 cat ../Outside/secret.txt"),
        executor_cwd=r"D:\Projects\Jack",
        command_dialect="bash",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


def test_bash_env_wrapper_with_inside_target_remains_usable():
    decision = policy.authorize_command_tool_call(
        build(),
        call("bash", "env FOO=1 cat README.md"),
        executor_cwd=r"D:\Projects\Jack",
        command_dialect="bash",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW


def test_bash_background_operator_preserves_positive_never_detection():
    decision = policy.authorize_command_tool_call(
        build(workspace=None),
        call(
            "bash",
            r'echo ok & cat "C:\Windows\System32\drivers\etc\hosts"',
        ),
        executor_cwd=r"D:\Ordinary",
        command_dialect="bash",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.HARD_INTERRUPT


def test_bash_cwd_mutation_sequence_is_not_authorized_against_stale_cwd():
    decision = policy.authorize_command_tool_call(
        build(),
        call("bash", r"cd ..; cat ..\Outside\secret.txt"),
        executor_cwd=r"D:\Projects\Jack\subdir",
        command_dialect="bash",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


@pytest.mark.parametrize(
    "command",
    (
        r'Get-Content ("..\Out" + "side\secret.txt")',
        r'Get-Content ([IO.Path]::Combine("..","Outside","secret.txt"))',
        r'Get-Content ~\secret.txt',
        r'Get-Content @args',
        "Write-Output ok && Get-Content ..\\Outside\\secret.txt",
    ),
)
def test_powershell_expression_forms_do_not_bypass_workspace_lock(command):
    decision = policy.authorize_command_tool_call(
        build(),
        call("powershell", command),
        executor_cwd=r"D:\Projects\Jack",
        command_dialect="powershell",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


def test_powershell_cwd_mutation_sequence_is_not_authorized_against_stale_cwd():
    decision = policy.authorize_command_tool_call(
        build(),
        call(
            "powershell",
            r"Set-Location ..; Get-Content ..\Outside\secret.txt",
        ),
        executor_cwd=r"D:\Projects\Jack\subdir",
        command_dialect="powershell",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


@pytest.mark.parametrize(
    "command",
    (
        r'Get-Content ("..\Out" + "side\secret.txt")',
        r'Get-Content ([IO.Path]::Combine("..","Outside","secret.txt"))',
        r'Get-Content ~\secret.txt',
        r'Get-Content @args',
    ),
)
def test_powershell_ambiguous_forms_remain_usable_without_workspace_lock(command):
    decision = policy.authorize_command_tool_call(
        build(workspace=None),
        call("powershell", command),
        executor_cwd=r"D:\Ordinary",
        command_dialect="powershell",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW


def test_quoted_literal_parentheses_are_not_misclassified_as_expression_syntax():
    decision = policy.authorize_command_tool_call(
        build(),
        call(
            "powershell",
            r'Get-Content -LiteralPath ".\file(1).txt"',
        ),
        executor_cwd=r"D:\Projects\Jack",
        command_dialect="powershell",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW
