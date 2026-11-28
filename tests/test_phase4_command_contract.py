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
        call("bash", r'cat "C:\Boot\BCD"'),
        executor_cwd=r"D:\Projects\Jack",
        command_dialect="bash",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.HARD_INTERRUPT


def test_bash_unresolved_expression_is_not_a_workspace_violation():
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

    assert locked.outcome is policy.PathAuthorizationOutcome.ALLOW
    assert locked.canonical_target is None
    assert "unclassified" in locked.reason
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
            r'Get-Content -LiteralPath "C:\Boot\BCD"',
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

    assert decision.outcome is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


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

    assert decision.outcome is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


def test_pathless_diagnostic_does_not_hard_only_because_unlocked_cwd_is_restricted():
    decision = policy.authorize_command_tool_call(
        build(workspace=None),
        call("powershell", "Get-Process"),
        executor_cwd=r"C:\Windows",
        command_dialect="powershell",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW


def test_unknown_command_dialect_is_not_a_policy_violation(kernel_policy):
    decision = kernel._phase4_executor_admission_decision(
        admission("shell", "git status", "fish")
    )
    assert decision["outcome"] == "ALLOW"
    assert decision["contract_applied"] is False


@pytest.mark.parametrize("dialect", [4, {}, "invalid dialect", ""])
def test_malformed_command_dialect_metadata_is_rejected(kernel_policy, dialect):
    with pytest.raises(kernel.HTTPException) as caught:
        kernel._phase4_executor_admission_decision(admission("shell", "git status", dialect))
    assert caught.value.status_code == 400


def test_unknown_dialect_does_not_remove_exact_tool_path_authority(kernel_policy):
    decision = kernel._phase4_executor_admission_decision(
        admission("bash", "cat ../Outside/file.txt", "fish")
    )
    assert decision["outcome"] == "DENY_AND_CONTINUE"
    assert decision["contract_applied"] is True


@pytest.mark.parametrize(
    "command",
    (
        "env FOO=1 cat ../Outside/secret.txt",
        "echo ok & cat ../Outside/secret.txt",
        "echo ok\ncat ../Outside/secret.txt",
        "cat ~/secret.txt",
        "git clone https://example.invalid/repo ../Outside",
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

    assert decision.outcome is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


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


@pytest.mark.parametrize(
    "dialect, command",
    (
        ("bash", 'unknown-inspector "C:/Boot/BCD"'),
        ("bash", 'unknown-inspector --output="D:/Sensitive/file.txt"'),
        ("powershell", r'Unknown-Inspector -LiteralPath "C:\Boot\BCD"'),
        ("powershell", r'Unknown-Inspector "D:\Sensitive\file.txt"'),
    ),
)
def test_unknown_command_preserves_positive_never_targets_without_workspace_lock(dialect, command):
    active = build(workspace=None, never=(r"D:\Sensitive",))
    extraction = policy.extract_command_paths(dialect, {"command": command})
    assert extraction.applicable and extraction.ambiguous
    assert extraction.targets
    decision = policy.authorize_command_tool_call(
        active, call(dialect, command),
        executor_cwd=r"D:\Ordinary", command_dialect=dialect,
    )
    assert decision.outcome is policy.PathAuthorizationOutcome.HARD_INTERRUPT


@pytest.mark.parametrize("dialect", ("bash", "powershell"))
def test_unknown_command_keeps_workspace_and_ambiguity_contract(dialect):
    command = 'unknown-inspector "D:/Projects/Jack/file.txt" https://example.invalid/repo'
    extraction = policy.extract_command_paths(dialect, {"command": command})
    assert extraction.ambiguous
    assert extraction.targets == ("D:/Projects/Jack/file.txt",)
    for workspace, expected in (
        (None, policy.PathAuthorizationOutcome.ALLOW),
        (r"D:\Projects\Jack", policy.PathAuthorizationOutcome.ALLOW),
    ):
        decision = policy.authorize_command_tool_call(
            build(workspace=workspace), call(dialect, command),
            executor_cwd=r"D:\Projects\Jack", command_dialect=dialect,
        )
        assert decision.outcome is expected
        if workspace is not None:
            assert "unclassified" in decision.reason


@pytest.mark.parametrize("dialect", ("bash", "powershell"))
def test_unknown_command_with_no_visible_filesystem_operands_remains_usable_unlocked(dialect):
    command = "unknown-inspector https://example.invalid/repo --verbose"
    extraction = policy.extract_command_paths(dialect, {"command": command})
    assert extraction.ambiguous and not extraction.targets
    assert policy.authorize_command_tool_call(
        build(workspace=None), call(dialect, command), command_dialect=dialect,
    ).outcome is policy.PathAuthorizationOutcome.ALLOW

@pytest.mark.parametrize("command", [
    r'find "D:\Projects\Jack"',
    r'find "D:\Projects\Jack" -mindepth 1 -maxdepth 1 -print',
    "find . -maxdepth 1 -type f -print",
    "find -maxdepth 1 -empty",
])
def test_read_only_find_workspace_inspection(command):
    for workspace in (None, r"D:\Projects\Jack"):
        decision = policy.authorize_command_tool_call(
            build(workspace=workspace), call("bash", command),
            executor_cwd=r"D:\Projects\Jack", command_dialect="bash",
        )
        assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW


@pytest.mark.parametrize("command, expected", [
    (r'find "D:\Outside"', "DENY_AND_CONTINUE"),
    (r'find "D:\Projects\Jack" -delete', "ALLOW"),
    (r'find "D:\Projects\Jack" -exec echo {} +', "ALLOW"),
    (r'find -L "D:\Projects\Jack"', "ALLOW"),
    (r'find "D:\Projects\Jack" -fprint "D:\Projects\Jack\out.txt"', "ALLOW"),
])
def test_find_preserves_positive_targets_without_claiming_unclassified_effects(command, expected):
    decision = policy.authorize_command_tool_call(
        build(), call("bash", command),
        executor_cwd=r"D:\Projects\Jack", command_dialect="bash",
    )
    assert decision.outcome.value == expected
    if expected == "ALLOW":
        assert "unclassified" in decision.reason


def test_find_explicit_never_root_remains_hard_interrupt():
    for workspace in (None, r"D:\Projects\Jack"):
        decision = policy.authorize_command_tool_call(
            build(workspace=workspace, never=(r"D:\Projects\Jack\Private",)),
            call("bash", r'find "D:\Projects\Jack\Private" -maxdepth 1'),
            executor_cwd=r"D:\Projects\Jack", command_dialect="bash",
        )
        assert decision.outcome is policy.PathAuthorizationOutcome.HARD_INTERRUPT


@pytest.mark.parametrize("dialect, command", [
    ("bash", "ls -la .\ncat clock.html"),
    ("bash", "echo 'clock [ready] {literal}'\nls -la ."),
    ("bash", 'ls -la "clock[1].html"'),
    ("bash", 'cat "clock{1}.html"'),
    ("bash", "stat clock.html"),
    ("bash", "wc -l clock.html"),
    ("bash", "sha256sum clock.html"),
    ("powershell", "Write-Output 'clock [ready] {literal}'"),
    ("powershell", 'Get-Item -LiteralPath ".\\clock[1].html"'),
    ("powershell", 'Get-Item -LiteralPath ".\\clock.html"\nGet-Location'),
])
def test_literal_commands_are_not_rejected_for_harmless_syntax(dialect, command):
    facts = policy.extract_command_paths(dialect, {"command": command})
    assert facts.applicable and not facts.ambiguous and not facts.error
    decision, applied = policy.authorize_executor_tool_call(
        build(), call(dialect, command),
        executor_cwd=r"D:\Projects\Jack", command_dialect=dialect,
    )
    assert applied and decision.outcome is policy.PathAuthorizationOutcome.ALLOW


@pytest.mark.parametrize("dialect, command", [
    ("bash", 'ls -la .\ncat "../Outside/clock[1].html"'),
    ("bash", 'stat "../Outside/clock[1].html"'),
    ("bash", 'wc -l "../Outside/clock[1].html"'),
    ("bash", 'sha256sum "../Outside/clock[1].html"'),
    ("powershell", 'Get-Item -LiteralPath "..\\Outside\\clock[1].html"'),
])
def test_literal_command_contract_preserves_workspace_membership(dialect, command):
    result = policy.authorize_command_tool_call(
        build(), call(dialect, command),
        executor_cwd=r"D:\Projects\Jack", command_dialect=dialect,
    )
    assert result.outcome is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE


@pytest.mark.parametrize("dialect, command", [
    ("bash", 'ls -la .\ncat "D:/Sensitive/clock[1].html"'),
    ("bash", 'stat "D:/Sensitive/clock[1].html"'),
    ("powershell", 'Get-Item -LiteralPath "D:\\Sensitive\\clock[1].html"'),
])
def test_literal_command_contract_preserves_explicit_never_authority(dialect, command):
    result = policy.authorize_command_tool_call(
        build(never=(r"D:\Sensitive",)), call(dialect, command),
        executor_cwd=r"D:\Projects\Jack", command_dialect=dialect,
    )
    assert result.outcome is policy.PathAuthorizationOutcome.HARD_INTERRUPT


@pytest.mark.parametrize("dialect, command, expected", [
    ("bash", 'cat "clock[1].html"\ncd ..\ncat clock.html', "DENY_AND_CONTINUE"),
    ("bash", 'cat "$(pwd)/clock.html"', "ALLOW"),
    ("bash", "sha256sum -c checksums.txt", "ALLOW"),
    ("bash", "cat clock*.html", "ALLOW"),
    ("bash", "echo ready\nunknown-inspector clock.html", "ALLOW"),
    ("powershell", 'Get-Item -Path ".\\clock[1].html"', "ALLOW"),
    ("powershell", 'Get-Item -LiteralPath "$target"', "ALLOW"),
])
def test_literal_lane_does_not_confuse_unresolved_effects_with_positive_escapes(dialect, command, expected):
    facts = policy.extract_command_paths(dialect, {"command": command})
    assert facts.ambiguous
    result = policy.authorize_command_tool_call(
        build(), call(dialect, command),
        executor_cwd=r"D:\Projects\Jack", command_dialect=dialect,
    )
    assert result.outcome.value == expected
    if expected == "ALLOW":
        assert "unclassified" in result.reason


def test_executor_authorization_extracts_command_once(monkeypatch):
    original = policy.extract_command_paths
    count = 0
    def counted(*args, **kwargs):
        nonlocal count
        count += 1
        return original(*args, **kwargs)
    monkeypatch.setattr(policy, "extract_command_paths", counted)
    decision, applied = policy.authorize_executor_tool_call(
        build(), call("bash", "ls -la ."),
        executor_cwd=r"D:\Projects\Jack", command_dialect="bash",
    )
    assert applied and decision.outcome is policy.PathAuthorizationOutcome.ALLOW
    assert count == 1


def test_request_wide_shell_metadata_does_not_classify_unrelated_custom_tools(kernel_policy):
    context = kernel.Phase4ExecutorRequestContext(
        protocol_version=1, runtime_id=kernel.RUNTIME_ID, lane_id=kernel.LANE_ID,
        cwd=r"D:\Projects\Jack", platform="win32", adapter="independent-test",
        command_dialect="bash",
    )
    token = kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.set(context)
    try:
        custom = {"id": "vision", "type": "function", "function": {
            "name": "describe_image", "arguments": json.dumps({"image_path": "clock.png"}),
        }}
        allowed, errors = kernel._phase4_partition_structured_tool_calls([custom])
        assert allowed == [custom] and not errors
    finally:
        kernel._PHASE4_EXECUTOR_REQUEST_CONTEXT.reset(token)
