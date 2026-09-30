from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import jack_path_policy as path_policy


@dataclass(frozen=True)
class RepresentedPathAuthorityFacts:
    """Deterministic represented-target facts produced from Phase-4 primitives.

    This adapter deliberately owns no SecurityOutcome mapping. It only exposes
    the path facts Jack can deterministically know without claiming final-object
    filesystem resolution.
    """

    canonical_target: Optional[str]
    never_match: bool
    workspace_configured: bool
    deterministic: bool
    inside_workspace: Optional[bool]
    invalid: bool
    deferred_to_executor: bool
    reason: str


def inspect_represented_path(
    policy: path_policy.RuntimePathPolicy,
    represented_path: Any,
    *,
    executor_cwd: Optional[str] = None,
    defer_relative_without_executor: bool = False,
) -> RepresentedPathAuthorityFacts:
    if not isinstance(policy, path_policy.RuntimePathPolicy):
        raise TypeError("policy must be a RuntimePathPolicy")

    environment = policy.path_environment()
    canonical_cwd = None

    if executor_cwd is not None:
        try:
            canonical_cwd = path_policy.normalize_represented_windows_path(
                executor_cwd,
                environment=environment,
            )
        except path_policy.RepresentedPathError as exc:
            return RepresentedPathAuthorityFacts(
                canonical_target=None,
                never_match=False,
                workspace_configured=policy.workspace_enabled,
                deterministic=False,
                inside_workspace=None,
                invalid=True,
                deferred_to_executor=False,
                reason=(
                    "executor cwd is not a deterministic absolute Windows path: "
                    f"{exc}"
                ),
            )

    try:
        canonical = path_policy.normalize_represented_windows_path(
            represented_path,
            base_root=canonical_cwd,
            environment=environment,
        )
    except path_policy.RepresentedPathNeedsExecutorCwd as exc:
        if defer_relative_without_executor:
            return RepresentedPathAuthorityFacts(
                canonical_target=None,
                never_match=False,
                workspace_configured=policy.workspace_enabled,
                deterministic=False,
                inside_workspace=None,
                invalid=False,
                deferred_to_executor=True,
                reason=f"executor cwd admission is required before execution: {exc}",
            )
        return RepresentedPathAuthorityFacts(
            canonical_target=None,
            never_match=False,
            workspace_configured=policy.workspace_enabled,
            deterministic=False,
            inside_workspace=None,
            invalid=False,
            deferred_to_executor=False,
            reason=(
                f"workspace membership cannot be established: {exc}"
                if policy.workspace_enabled
                else f"no workspace lock; represented target unresolved: {exc}"
            ),
        )
    except path_policy.RepresentedPathInvalid as exc:
        return RepresentedPathAuthorityFacts(
            canonical_target=None,
            never_match=False,
            workspace_configured=policy.workspace_enabled,
            deterministic=False,
            inside_workspace=None,
            invalid=True,
            deferred_to_executor=False,
            reason=f"invalid represented path: {exc}",
        )
    except path_policy.RepresentedPathAmbiguous as exc:
        return RepresentedPathAuthorityFacts(
            canonical_target=None,
            never_match=False,
            workspace_configured=policy.workspace_enabled,
            deterministic=False,
            inside_workspace=None,
            invalid=False,
            deferred_to_executor=False,
            reason=(
                f"workspace membership cannot be established: {exc}"
                if policy.workspace_enabled
                else f"no workspace lock; represented target unresolved: {exc}"
            ),
        )

    try:
        comparison_target = path_policy._policy_object_windows_path(canonical)
    except path_policy.RepresentedPathAmbiguous as exc:
        return RepresentedPathAuthorityFacts(
            canonical_target=canonical,
            never_match=False,
            workspace_configured=policy.workspace_enabled,
            deterministic=False,
            inside_workspace=None,
            invalid=False,
            deferred_to_executor=False,
            reason=(
                f"workspace membership cannot be established: {exc}"
                if policy.workspace_enabled
                else f"no workspace lock; represented target unresolved: {exc}"
            ),
        )

    never_match = any(
        path_policy.path_is_within_or_equal(comparison_target, never_root)
        for never_root in policy.never_roots
    )
    inside_workspace = (
        None
        if policy.workspace_root is None
        else path_policy.path_is_within_or_equal(
            comparison_target,
            policy.workspace_root,
        )
    )

    if never_match:
        reason = "represented target positively matches a NEVER root"
    elif inside_workspace is False:
        reason = "represented target is outside the configured workspace"
    else:
        reason = "represented target is authorized by Phase-4 path policy"

    return RepresentedPathAuthorityFacts(
        canonical_target=canonical,
        never_match=never_match,
        workspace_configured=policy.workspace_enabled,
        deterministic=True,
        inside_workspace=inside_workspace,
        invalid=False,
        deferred_to_executor=False,
        reason=reason,
    )
