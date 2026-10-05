from __future__ import annotations

import ntpath
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Tuple


RESOURCE_JACK_CONFIG = "resource:jack-config"
RESOURCE_PI_CONFIG = "resource:pi-config"


@dataclass(frozen=True, repr=False)
class ProtectedCredentialResource:
    """One exact host-owned credential resource identity.

    The canonical path is authority data but is intentionally repr-hidden so
    ordinary diagnostics do not disclose a user's profile/config location.
    """

    resource_id: str
    canonical_path: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.resource_id, str) or not self.resource_id:
            raise ValueError("resource_id must be a non-empty string")
        if not isinstance(self.canonical_path, str) or not self.canonical_path:
            raise ValueError("canonical_path must be a non-empty string")

    def __repr__(self) -> str:
        return (
            "ProtectedCredentialResource("
            f"resource_id={self.resource_id!r}, canonical_path=<protected-resource>)"
        )


@dataclass(frozen=True, repr=False)
class RuntimeCredentialResourcePolicy:
    runtime_id: str
    lane_id: str
    resources: Tuple[ProtectedCredentialResource, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.runtime_id, str) or not self.runtime_id:
            raise ValueError("runtime_id must be a non-empty string")
        if not isinstance(self.lane_id, str) or not self.lane_id:
            raise ValueError("lane_id must be a non-empty string")
        if not isinstance(self.resources, tuple):
            raise TypeError("resources must be a tuple")
        ids = set()
        paths = set()
        for item in self.resources:
            if not isinstance(item, ProtectedCredentialResource):
                raise TypeError("resources must contain ProtectedCredentialResource")
            if item.resource_id in ids:
                raise ValueError("duplicate credential resource_id")
            if item.canonical_path in paths:
                raise ValueError("duplicate credential resource path")
            ids.add(item.resource_id)
            paths.add(item.canonical_path)

    def __repr__(self) -> str:
        return (
            "RuntimeCredentialResourcePolicy("
            f"runtime_id={self.runtime_id!r}, lane_id={self.lane_id!r}, "
            f"resource_count={len(self.resources)})"
        )


@dataclass(frozen=True)
class CredentialResourceAuthorityFact:
    protected: bool
    resource_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.protected, bool):
            raise TypeError("protected must be bool")
        if self.protected and (not isinstance(self.resource_id, str) or not self.resource_id):
            raise ValueError("protected resource fact requires resource_id")
        if not self.protected and self.resource_id is not None:
            raise ValueError("unprotected resource fact must not carry resource_id")


_REGISTRY_LOCK = threading.Lock()
_RESOURCE_POLICIES: dict[tuple[str, str], RuntimeCredentialResourcePolicy] = {}


def _canonical_resource_path(value: Any) -> str:
    text = str(value or "").strip().replace("/", "\\")
    if not text:
        raise RuntimeError("Phase-7 credential resource path is empty")
    canonical = ntpath.normcase(ntpath.normpath(text))
    drive, tail = ntpath.splitdrive(canonical)
    if not drive or not (tail.startswith("\\") or drive.startswith("\\\\")):
        raise RuntimeError(
            "Phase-7 credential resource path is not an absolute Windows path"
        )
    return canonical


def _resource_id_for_path(canonical: str) -> str:
    lowered = canonical.casefold()
    if lowered.endswith(r"\jackkernellmstudio\config.json") or lowered.endswith(
        r"\.jack-kernel-lm-studio\config.json"
    ):
        return RESOURCE_JACK_CONFIG
    if lowered.endswith(r"\.pi\agent\jack-kernel.json"):
        return RESOURCE_PI_CONFIG
    raise RuntimeError("Phase-7 encountered an unknown protected credential resource")


def build_runtime_credential_resource_policy(
    credential_policy: Any,
) -> RuntimeCredentialResourcePolicy:
    runtime_id = str(getattr(credential_policy, "runtime_id", "") or "").strip()
    lane_id = str(getattr(credential_policy, "lane_id", "") or "").strip()
    raw_resources = tuple(getattr(credential_policy, "protected_resources", ()))
    resources = []
    for raw in raw_resources:
        canonical = _canonical_resource_path(raw)
        resources.append(
            ProtectedCredentialResource(
                resource_id=_resource_id_for_path(canonical),
                canonical_path=canonical,
            )
        )
    return RuntimeCredentialResourcePolicy(
        runtime_id=runtime_id,
        lane_id=lane_id,
        resources=tuple(resources),
    )


def install(
    jk: Any,
    *,
    credential_policy: Any,
) -> RuntimeCredentialResourcePolicy:
    existing = getattr(jk, "_JACK_CREDENTIAL_RESOURCE_POLICY", None)
    if getattr(jk, "_JACK_CREDENTIAL_RESOURCE_GUARD_INSTALLED", False):
        if not isinstance(existing, RuntimeCredentialResourcePolicy):
            raise RuntimeError("Phase-7 credential resource policy state is invalid")
        return existing

    policy = build_runtime_credential_resource_policy(credential_policy)
    runtime_id = str(getattr(jk, "RUNTIME_ID", "") or "").strip()
    lane_id = str(getattr(jk, "LANE_ID", "") or "").strip()
    if policy.runtime_id != runtime_id or policy.lane_id != lane_id:
        raise RuntimeError("Phase-7 credential resource ownership mismatch")

    key = (policy.runtime_id, policy.lane_id)
    with _REGISTRY_LOCK:
        prior = _RESOURCE_POLICIES.get(key)
        if prior is not None and prior != policy:
            raise RuntimeError(
                "Phase-7 credential resource identity cannot be rebound to a different policy"
            )
        _RESOURCE_POLICIES[key] = policy

    jk._JACK_CREDENTIAL_RESOURCE_POLICY = policy
    jk._JACK_CREDENTIAL_RESOURCE_GUARD_INSTALLED = True
    jk.CredentialResourceAuthorityFact = CredentialResourceAuthorityFact

    register = getattr(jk, "_register_runtime_manifest_components", None)
    if callable(register):
        register({"jack_credential_resource_guard.py": Path(__file__).resolve()})

    return policy


def fact_for_canonical_target(
    path_policy: Any,
    canonical_target: Optional[str],
) -> Optional[CredentialResourceAuthorityFact]:
    """Return a Phase-7 fact only when this runtime has resource authority installed."""

    if not isinstance(canonical_target, str) or not canonical_target:
        return None
    key = (
        str(getattr(path_policy, "runtime_id", "") or ""),
        str(getattr(path_policy, "lane_id", "") or ""),
    )
    with _REGISTRY_LOCK:
        policy = _RESOURCE_POLICIES.get(key)
    if policy is None:
        return None

    canonical = ntpath.normcase(ntpath.normpath(canonical_target))
    for resource in policy.resources:
        if canonical == resource.canonical_path:
            return CredentialResourceAuthorityFact(
                protected=True,
                resource_id=resource.resource_id,
            )
    return CredentialResourceAuthorityFact(protected=False)
