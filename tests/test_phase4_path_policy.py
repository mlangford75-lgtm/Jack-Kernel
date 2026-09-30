from __future__ import annotations

import dataclasses
import json

import pytest

import jack_path_policy as policy


HOST_ENV = {
    "SystemRoot": r"C:\Windows",
    "WINDIR": r"C:\Windows",
    "SystemDrive": "C:",
    "USERPROFILE": r"C:\Users\Operator",
    "TEMP": r"C:\Users\Operator\AppData\Local\Temp",
    "TMP": r"C:\Users\Operator\AppData\Local\Temp",
}


def build(
    *,
    workspace=r"D:\Projects\Jack",
    never=(),
):
    return policy.build_runtime_path_policy(
        runtime_id="runtime-phase4",
        lane_id="lane-phase4",
        raw_json=json.dumps(
            {
                "version": 1,
                "workspace_root": workspace,
                "never_paths": list(never),
            }
        ),
        host_environment=HOST_ENV,
    )


def test_runtime_path_policy_is_frozen_and_owner_bound():
    active = build()

    assert active.runtime_id == "runtime-phase4"
    assert active.lane_id == "lane-phase4"
    assert active.workspace_root == r"d:\projects\jack"

    with pytest.raises(dataclasses.FrozenInstanceError):
        active.workspace_root = r"d:\other"


@pytest.mark.parametrize(
    "runtime_id,lane_id",
    (
        ("", "lane"),
        ("runtime", ""),
    ),
)
def test_policy_rejects_empty_owner_identity(runtime_id, lane_id):
    with pytest.raises(ValueError):
        policy.RuntimePathPolicy(
            runtime_id=runtime_id,
            lane_id=lane_id,
            workspace_root=None,
            never_roots=(),
            _path_environment=(),
        )


def test_host_policy_json_has_strict_shape():
    raw = json.dumps(
        {
            "version": 1,
            "workspace_root": r"D:\Projects\Jack",
            "never_paths": [],
            "caller_override": r"C:\\",
        }
    )

    with pytest.raises(
        RuntimeError,
        match="unsupported top-level fields",
    ):
        policy.build_runtime_path_policy(
            runtime_id="runtime",
            lane_id="lane",
            raw_json=raw,
            host_environment=HOST_ENV,
        )


def test_default_never_roots_are_host_derived_and_cannot_be_removed():
    active = build(never=())

    assert r"c:\windows" in active.never_roots
    assert r"c:\boot" in active.never_roots
    assert r"c:\recovery" in active.never_roots
    assert r"c:\system volume information" in active.never_roots


def test_user_never_roots_are_cumulative():
    active = build(
        never=[r"E:\CrownJewels"],
    )

    assert r"c:\windows" in active.never_roots
    assert r"e:\crownjewels" in active.never_roots


def test_workspace_cannot_be_configured_inside_never_root():
    with pytest.raises(
        RuntimeError,
        match="workspace_root cannot be inside a NEVER root",
    ):
        build(workspace=r"C:\Windows\Temp")


@pytest.mark.parametrize(
    "raw",
    (
        r"D:\Projects\Jack\src\engine.py",
        r"d:/projects/jack/src/engine.py",
        r'"D:\Projects\Jack\src\engine.py"',
    ),
)
def test_inside_workspace_is_allowed_across_case_separator_and_quotes(raw):
    decision = policy.authorize_represented_path(
        build(),
        raw,
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW
    assert decision.canonical_target == r"d:\projects\jack\src\engine.py"


def test_relative_target_requires_executor_cwd_under_workspace_lock():
    active = build()

    without_executor = policy.authorize_represented_path(
        active,
        r"src\engine.py",
    )
    assert (
        without_executor.outcome
        is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE
    )

    with_executor = policy.authorize_represented_path(
        active,
        r"src\engine.py",
        executor_cwd=r"D:\Projects\Jack",
    )
    assert with_executor.outcome is policy.PathAuthorizationOutcome.ALLOW
    assert with_executor.canonical_target == r"d:\projects\jack\src\engine.py"


def test_relative_traversal_escape_is_denied_without_destroying_policy_state():
    active = build()

    decision = policy.authorize_represented_path(
        active,
        r"..\Outside\payload.ps1",
    )

    assert (
        decision.outcome
        is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE
    )
    assert active.workspace_root == r"d:\projects\jack"


def test_absolute_outside_workspace_is_denied():
    decision = policy.authorize_represented_path(
        build(),
        r"D:\OtherProject\file.txt",
    )

    assert (
        decision.outcome
        is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE
    )


def test_sibling_prefix_does_not_bypass_workspace_lock():
    decision = policy.authorize_represented_path(
        build(workspace=r"D:\Work"),
        r"D:\Workspace\payload.txt",
    )

    assert (
        decision.outcome
        is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE
    )


def test_positive_never_match_is_hard_even_when_workspace_would_otherwise_allow():
    active = build(
        workspace=r"D:\Projects",
        never=[r"D:\Projects\Forbidden"],
    )

    decision = policy.authorize_represented_path(
        active,
        r"D:\Projects\Forbidden\secret.txt",
    )

    assert (
        decision.outcome
        is policy.PathAuthorizationOutcome.HARD_INTERRUPT
    )
    assert decision.hard


@pytest.mark.parametrize(
    "raw",
    (
        r"C:\Windows\System32\drivers\etc\hosts",
        r"c:/windows/temp/../system32/cmd.exe",
        r"%WINDIR%\System32\cmd.exe",
        r"$env:WINDIR\System32\cmd.exe",
        r"${env:WINDIR}\System32\cmd.exe",
        r"\\?\C:\Windows\System32\cmd.exe",
    ),
)
def test_default_never_matching_resists_trivial_textual_bypasses(raw):
    active = build(workspace=None)

    decision = policy.authorize_represented_path(
        active,
        raw,
    )

    assert (
        decision.outcome
        is policy.PathAuthorizationOutcome.HARD_INTERRUPT
    )


def test_unknown_environment_variable_is_recoverably_denied_under_workspace_lock():
    decision = policy.authorize_represented_path(
        build(),
        r"%UNKNOWN_PROJECT_ROOT%\file.txt",
    )

    assert (
        decision.outcome
        is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE
    )
    assert decision.canonical_target is None


def test_ambiguity_without_workspace_does_not_invent_a_new_restriction():
    active = build(workspace=None)

    decision = policy.authorize_represented_path(
        active,
        r"%UNKNOWN_PROJECT_ROOT%\file.txt",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW
    assert decision.canonical_target is None
    assert "no workspace lock" in decision.reason


def test_relative_path_without_workspace_does_not_use_jack_process_cwd():
    active = build(workspace=None)

    decision = policy.authorize_represented_path(
        active,
        r"src\engine.py",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW
    assert decision.canonical_target is None


@pytest.mark.parametrize(
    "raw",
    (
        r"C:relative\file.txt",
        r"\current-drive-root\file.txt",
        r"\\.\C:",
    ),
)
def test_executor_dependent_windows_forms_are_not_claimed_as_resolved(raw):
    locked = policy.authorize_represented_path(
        build(),
        raw,
    )
    unlocked = policy.authorize_represented_path(
        build(workspace=None),
        raw,
    )

    assert (
        locked.outcome
        is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE
    )
    assert unlocked.outcome is policy.PathAuthorizationOutcome.ALLOW

    assert locked.canonical_target is None
    assert unlocked.canonical_target is None


def test_invalid_nul_path_is_recoverably_rejected_even_without_workspace():
    decision = policy.authorize_represented_path(
        build(workspace=None),
        "C:\\safe\x00tail",
    )

    assert (
        decision.outcome
        is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE
    )


def test_policy_environment_snapshot_is_not_mutable_through_returned_mapping():
    active = build()

    copy_of_env = active.path_environment()
    copy_of_env["windir"] = r"D:\AttackerControlled"

    decision = policy.authorize_represented_path(
        active,
        r"%WINDIR%\System32\cmd.exe",
    )

    assert (
        decision.outcome
        is policy.PathAuthorizationOutcome.HARD_INTERRUPT
    )
    assert decision.canonical_target == r"c:\windows\system32\cmd.exe"


def test_host_environment_changes_after_construction_do_not_redefine_policy():
    source = dict(HOST_ENV)

    active = policy.build_runtime_path_policy(
        runtime_id="runtime",
        lane_id="lane",
        raw_json=json.dumps(
            {
                "version": 1,
                "workspace_root": None,
                "never_paths": [],
            }
        ),
        host_environment=source,
    )

    source["WINDIR"] = r"D:\DifferentWindows"
    source["SystemRoot"] = r"D:\DifferentWindows"

    original = policy.authorize_represented_path(
        active,
        r"%WINDIR%\System32\cmd.exe",
    )

    changed = policy.authorize_represented_path(
        active,
        r"D:\DifferentWindows\System32\cmd.exe",
    )

    assert (
        original.outcome
        is policy.PathAuthorizationOutcome.HARD_INTERRUPT
    )
    assert changed.outcome is policy.PathAuthorizationOutcome.ALLOW


def test_empty_host_config_preserves_default_never_policy_without_workspace():
    active = policy.build_runtime_path_policy(
        runtime_id="runtime",
        lane_id="lane",
        raw_json="",
        host_environment=HOST_ENV,
    )

    assert active.workspace_root is None
    assert r"c:\windows" in active.never_roots

    ordinary = policy.authorize_represented_path(
        active,
        r"D:\Ordinary\file.txt",
    )
    restricted = policy.authorize_represented_path(
        active,
        r"C:\Windows\System32\cmd.exe",
    )

    assert ordinary.outcome is policy.PathAuthorizationOutcome.ALLOW
    assert (
        restricted.outcome
        is policy.PathAuthorizationOutcome.HARD_INTERRUPT
    )


def test_path_resolution_gap_is_structural_no_filesystem_resolution_api_is_used():
    source = (
        __import__("pathlib").Path(policy.__file__)
        .read_text(encoding="utf-8")
        .lower()
    )

    forbidden = (
        ".resolve(",
        "os.path.realpath",
        "pathlib.path.resolve",
        ".stat(",
        "samefile(",
    )

    assert not any(token in source for token in forbidden)


def structured_call(name, arguments):
    return {
        "id": "call-phase4",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments),
        },
    }


@pytest.mark.parametrize("tool_name", ("read", "edit", "write"))
def test_exact_pi_structured_filesystem_contracts_are_host_owned(tool_name):
    extraction = policy.extract_structured_tool_paths(
        tool_name,
        {"path": r"D:\Projects\Jack\file.txt"},
    )

    assert extraction.applicable
    assert extraction.error is None
    assert extraction.targets == (
        r"D:\Projects\Jack\file.txt",
    )


@pytest.mark.parametrize("tool_name", ("bash", "powershell", "custom_tool", "foo.read"))
def test_uncontracted_tools_are_not_reclassified_by_argument_name(tool_name):
    extraction = policy.extract_structured_tool_paths(
        tool_name,
        {"path": r"C:\Windows\System32\cmd.exe"},
    )

    assert not extraction.applicable
    assert extraction.targets == ()
    assert extraction.error is None


def test_structured_read_outside_workspace_is_denied():
    decision = policy.authorize_structured_tool_call(
        build(),
        structured_call(
            "read",
            {"path": r"D:\Outside\secret.txt"},
        ),
    )

    assert (
        decision.outcome
        is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE
    )


def test_structured_write_inside_workspace_is_allowed():
    decision = policy.authorize_structured_tool_call(
        build(),
        structured_call(
            "write",
            {
                "path": r"D:\Projects\Jack\out.txt",
                "content": "ok",
            },
        ),
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW


def test_structured_never_target_is_hard():
    decision = policy.authorize_structured_tool_call(
        build(workspace=None),
        structured_call(
            "read",
            {"path": r"C:\Windows\System32\drivers\etc\hosts"},
        ),
    )

    assert (
        decision.outcome
        is policy.PathAuthorizationOutcome.HARD_INTERRUPT
    )


def test_unadvertised_alias_does_not_gain_filesystem_authority():
    call = structured_call(
        "read",
        {
            "path": r"D:\Ordinary\file.txt",
            "file_path": r"C:\Windows\System32\cmd.exe",
        },
    )

    decision = policy.authorize_structured_tool_call(
        build(workspace=None),
        call,
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW


def test_structured_tool_missing_represented_path_is_recoverably_denied():
    decision = policy.authorize_structured_tool_call(
        build(),
        structured_call(
            "write",
            {"content": "missing path"},
        ),
    )

    assert (
        decision.outcome
        is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE
    )


def test_unknown_custom_tool_remains_unclassified_not_falsely_authorized_as_filesystem():
    decision = policy.authorize_structured_tool_call(
        build(),
        structured_call(
            "custom_tool",
            {"path": r"D:\Outside\secret.txt"},
        ),
    )

    # Slice 3 does not claim this is a safe filesystem operation. It only proves
    # that unknown/custom tool semantics are not invented from an argument name.
    assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW
    assert "no host-owned structured path contract" in decision.reason


@pytest.mark.parametrize("tool_name", ("grep", "find", "ls"))
def test_optional_path_structured_tools_default_to_executor_cwd(tool_name):
    extraction = policy.extract_structured_tool_paths(
        tool_name,
        {},
    )

    assert extraction.applicable
    assert extraction.uses_executor_cwd
    assert extraction.targets == ()


def test_structured_relative_path_is_deferred_before_executor_admission():
    decision = policy.authorize_structured_tool_call(
        build(),
        structured_call(
            "read",
            {"path": r"src\engine.py"},
        ),
        defer_relative_without_executor=True,
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW
    assert "executor cwd" in decision.reason


def test_executor_cwd_inside_workspace_authorizes_relative_structured_path():
    decision = policy.authorize_structured_tool_call(
        build(),
        structured_call(
            "read",
            {"path": r"src\engine.py"},
        ),
        executor_cwd=r"D:\Projects\Jack",
    )

    assert decision.outcome is policy.PathAuthorizationOutcome.ALLOW


def test_executor_cwd_outside_workspace_denies_relative_structured_path():
    decision = policy.authorize_structured_tool_call(
        build(),
        structured_call(
            "read",
            {"path": r"src\engine.py"},
        ),
        executor_cwd=r"D:\OtherProject",
    )

    assert (
        decision.outcome
        is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE
    )


def test_pathless_ls_outside_workspace_is_denied_by_actual_executor_cwd():
    decision = policy.authorize_structured_tool_call(
        build(),
        structured_call(
            "ls",
            {},
        ),
        executor_cwd=r"D:\OtherProject",
    )

    assert (
        decision.outcome
        is policy.PathAuthorizationOutcome.DENY_AND_CONTINUE
    )


def test_relative_target_can_hard_match_never_after_executor_cwd_resolution():
    active = build(
        workspace=None,
        never=[r"D:\Sensitive"],
    )
    decision = policy.authorize_structured_tool_call(
        active,
        structured_call(
            "read",
            {"path": r"..\Sensitive\secret.txt"},
        ),
        executor_cwd=r"D:\Work",
    )

    assert (
        decision.outcome
        is policy.PathAuthorizationOutcome.HARD_INTERRUPT
    )


def test_workspace_release_rewrites_relative_structured_path_to_absolute_workspace_target():
    active = build()
    original = structured_call(
        "read",
        {"path": r"src\engine.py"},
    )

    rewritten = policy.rewrite_structured_tool_call_for_workspace_release(
        active,
        original,
    )

    args = json.loads(
        rewritten["function"]["arguments"]
    )

    assert args["path"] == r"d:\projects\jack\src\engine.py"
    assert json.loads(original["function"]["arguments"])["path"] == r"src\engine.py"


@pytest.mark.parametrize("tool_name", ("grep", "find", "ls"))
def test_workspace_release_materializes_workspace_root_for_pathless_structured_tools(tool_name):
    active = build()
    rewritten = policy.rewrite_structured_tool_call_for_workspace_release(
        active,
        structured_call(tool_name, {}),
    )

    args = json.loads(
        rewritten["function"]["arguments"]
    )

    assert args["path"] == r"d:\projects\jack"


def test_workspace_release_leaves_relative_structured_target_unchanged_when_lock_disabled():
    active = build(workspace=None)
    original = structured_call(
        "read",
        {"path": r"src\engine.py"},
    )

    rewritten = policy.rewrite_structured_tool_call_for_workspace_release(
        active,
        original,
    )

    assert json.loads(rewritten["function"]["arguments"])["path"] == r"src\engine.py"
