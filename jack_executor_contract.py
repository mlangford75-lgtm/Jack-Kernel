"""Platform-independent filesystem enforcement contract.

No agent, shell, model, filesystem syntax, or operating system is required by
this module. The current native path policy is a represented-target adapter.
Full containment is a distinct capability, not a synonym for parsing.

Only trusted host integration may negotiate an executor binding. These types
are NOT a wire authorization token and must never be constructed from model
claims or a request header and treated as evidence of enforcement.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class FilesystemProtection(str, Enum):
    STANDARD = "standard"
    REPRESENTED = "represented"
    BOUNDED = "bounded"
    STRICT = "strict"


def effective_protection(workspace_configured: bool, workspace_mode: str) -> FilesystemProtection:
    if workspace_mode not in {"bounded", "represented", "strict"}:
        raise ValueError("unsupported workspace enforcement mode")
    if not workspace_configured:
        if workspace_mode != "bounded":
            raise ValueError("explicit workspace enforcement requires a workspace")
        return FilesystemProtection.STANDARD
    # Legacy configurations used "bounded" for ordinary Workspace Lock.
    # Do not require a finite command parser to certify arbitrary legitimate
    # work. Both persisted spellings now enforce represented path facts.
    # Strict remains a separate, explicitly qualified executor contract.
    if workspace_mode == "bounded":
        return FilesystemProtection.REPRESENTED
    return FilesystemProtection(workspace_mode)


class ExecutorCapability(str, Enum):
    OBJECT_ACCESS_ENFORCEMENT = "object_access_enforcement"
    WORKSPACE_CONTAINMENT = "workspace_containment"
    RESTRICTED_OBJECT_EXCLUSION = "restricted_object_exclusion"
    CHILD_PROCESS_CONTAINMENT = "child_process_containment"
    POLICY_BINDING = "policy_binding"
    AUTHENTICATED_RECEIPTS = "authenticated_receipts"
    CANCELLATION_AND_SETTLEMENT = "cancellation_and_settlement"


STRICT_CAPABILITIES = frozenset(ExecutorCapability)


@dataclass(frozen=True)
class ExecutorPolicyBinding:
    """Opaque host-owned policy identity; path semantics belong to the adapter."""
    runtime_id: str
    lane_id: str
    policy_identity: str
    mode: FilesystemProtection


@dataclass(frozen=True)
class ExecutorQualification:
    """Host-verified adapter capability record, not a self-reported declaration."""
    executor_id: str
    binding: ExecutorPolicyBinding
    capabilities: frozenset[ExecutorCapability]


class QualifiedExecutor(Protocol):
    """Interface implemented by independently qualified executor integrations.

    The host must establish trust, identity and immutable policy binding
    outside model-facing request data before invoking this interface.
    """
    def verify_binding(self, binding: ExecutorPolicyBinding) -> ExecutorQualification:
        ...


def require_strict_qualification(
    binding: ExecutorPolicyBinding,
    qualification: ExecutorQualification | None,
) -> None:
    """Validate a host-established qualification, never downgrade strict mode.

    This function does not attest an OS sandbox or authenticate a remote
    caller. Those duties belong to a trusted, qualified host integration.
    No existing native executor supplies such an integration.
    """
    if binding.mode is not FilesystemProtection.STRICT:
        raise ValueError("strict qualification requires strict policy")
    if (
        type(qualification) is not ExecutorQualification
        or not qualification.executor_id
        or qualification.binding != binding
        or type(qualification.capabilities) is not frozenset
        or not STRICT_CAPABILITIES.issubset(qualification.capabilities)
    ):
        raise RuntimeError("strict executor containment requires a qualified policy-bound executor")
