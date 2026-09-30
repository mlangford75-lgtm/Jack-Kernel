from __future__ import annotations

import json
import pytest
import jack_path_policy as p


ENV = {
    "SystemRoot": r"C:\Windows",
    "WINDIR": r"C:\Windows",
    "SystemDrive": "C:",
    "USERPROFILE": r"C:\Users\Operator",
}


def build(workspace=r"D:\Projects\Jack"):
    return p.build_runtime_path_policy(
        runtime_id="r",
        lane_id="l",
        raw_json=json.dumps({
            "version": 1,
            "workspace_root": workspace,
            "never_paths": [],
        }),
        host_environment=ENV,
    )


def call(tool, command):
    return {
        "id": "c",
        "type": "function",
        "function": {
            "name": tool,
            "arguments": json.dumps({"command": command}),
        },
    }


def auth(
    command,
    *,
    tool="powershell",
    workspace=r"D:\Projects\Jack",
    cwd=r"D:\Outside",
    dialect="powershell",
):
    return p.authorize_command_tool_call(
        build(workspace),
        call(tool, command),
        executor_cwd=cwd,
        command_dialect=dialect,
        executor_platform="win32",
    ).outcome


@pytest.mark.parametrize(
    "target",
    (
        r"FileSystem::C:\Windows\System32\drivers\etc\hosts",
        r"Microsoft.PowerShell.Core\FileSystem::C:\Windows\System32\cmd.exe",
    ),
)
def test_filesystem_provider_never(target):
    assert auth(
        f"Get-Content -LiteralPath {target}",
        workspace=None,
        cwd=r"D:\Ordinary",
    ) is p.PathAuthorizationOutcome.HARD_INTERRUPT


@pytest.mark.parametrize(
    "target",
    (
        r"FileSystem::D:\Projects\Jack\README.md",
        r"Microsoft.PowerShell.Core\FileSystem::D:\Projects\Jack\README.md",
    ),
)
def test_filesystem_provider_inside_workspace(target):
    assert auth(
        f"Get-Content -LiteralPath {target}",
        cwd=r"D:\Projects\Jack",
    ) is p.PathAuthorizationOutcome.ALLOW


@pytest.mark.parametrize(
    "command",
    (
        r"Get-Content HKLM:\Software",
        r"Get-Content Registry::HKEY_LOCAL_MACHINE\Software",
        "Get-Process",
        "Get-Service",
        "Get-Date",
        "Write-Output ok",
    ),
)
def test_nonfilesystem_and_pathless_commands_remain_usable(command):
    assert auth(command) is p.PathAuthorizationOutcome.ALLOW


def test_absolute_inside_workspace_ignores_incidental_outside_cwd():
    assert auth(
        r"Get-Content -LiteralPath D:\Projects\Jack\README.md"
    ) is p.PathAuthorizationOutcome.ALLOW


def test_relative_target_from_outside_workspace_is_denied():
    assert auth(
        r"Get-Content -LiteralPath .\secret.txt"
    ) is p.PathAuthorizationOutcome.DENY_AND_CONTINUE


def test_git_status_outside_workspace_is_denied():
    assert auth(
        "git status",
        tool="bash",
        dialect="bash",
    ) is p.PathAuthorizationOutcome.DENY_AND_CONTINUE


def test_drive_rooted_powershell_never_uses_executor_drive():
    assert auth(
        r"Get-Content -LiteralPath \Windows\System32\drivers\etc\hosts",
        workspace=None,
        cwd=r"C:\Users\Operator",
    ) is p.PathAuthorizationOutcome.HARD_INTERRUPT


@pytest.mark.parametrize(
    "raw",
    (
        r"C:\Windows.\System32\cmd.exe",
        r"C:\Windows \System32\cmd.exe",
        r"C:\Windows...\System32\cmd.exe",
    ),
)
def test_standard_win32_aliases_hit_never(raw):
    assert (
        p.authorize_represented_path(build(None), raw).outcome
        is p.PathAuthorizationOutcome.HARD_INTERRUPT
    )


def test_extended_namespace_preserves_segment_semantics():
    assert (
        p.authorize_represented_path(
            build(None),
            r"\\?\C:\Windows.\System32\cmd.exe",
        ).outcome
        is p.PathAuthorizationOutcome.ALLOW
    )

    assert (
        p.authorize_represented_path(
            build(None),
            r"\\?\C:\Windows\System32\cmd.exe",
        ).outcome
        is p.PathAuthorizationOutcome.HARD_INTERRUPT
    )


@pytest.mark.parametrize(
    "raw",
    (
        r"C:\Windows::$INDEX_ALLOCATION",
        r"C:\Windows:$I30:$INDEX_ALLOCATION",
        r"C:\Windows:shadow:$DATA",
        r"C:\Windows::$DATA",
    ),
)
def test_ntfs_stream_owner_hits_never(raw):
    assert (
        p.authorize_represented_path(build(None), raw).outcome
        is p.PathAuthorizationOutcome.HARD_INTERRUPT
    )


def test_ntfs_stream_inside_workspace_allowed():
    assert (
        p.authorize_represented_path(
            build(),
            r"D:\Projects\Jack\artifact.txt:metadata:$DATA",
        ).outcome
        is p.PathAuthorizationOutcome.ALLOW
    )


def test_ntfs_stream_outside_workspace_denied():
    assert (
        p.authorize_represented_path(
            build(),
            r"D:\Outside\artifact.txt:metadata:$DATA",
        ).outcome
        is p.PathAuthorizationOutcome.DENY_AND_CONTINUE
    )


def test_drive_rooted_never_uses_executor_cwd_drive():
    assert (
        p.authorize_represented_path(
            build(None),
            r"\Windows\System32\cmd.exe",
            executor_cwd=r"C:\Users\Operator",
        ).outcome
        is p.PathAuthorizationOutcome.HARD_INTERRUPT
    )


def test_drive_rooted_outside_workspace_denied():
    assert (
        p.authorize_represented_path(
            build(),
            r"\Outside\secret.txt",
            executor_cwd=r"D:\Projects\Jack",
        ).outcome
        is p.PathAuthorizationOutcome.DENY_AND_CONTINUE
    )
