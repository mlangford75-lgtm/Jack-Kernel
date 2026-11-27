"""Phase 10-B selected immutable security policy measurement (experimental).

This module is not activated in production. It measures *known* Jack policy
types, capturing actual holder or closure-cell identity and canonical
behavior-affecting fields. A later Phase 10-C integration must prove that
the measured references are the ones the consequence gate actually consumes.

Scope: runtime-process local; not independent same-interpreter attestation.
No policy, secret or path material is included in external error strings.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import secrets
import threading
import types
from typing import Any, Literal

PolicyKind = Literal["path", "canary", "credential"]


class PolicyIntegrityUnavailable(RuntimeError):
    """A required active policy could not be measured accurately."""


class PolicyIntegrityCompromised(PolicyIntegrityUnavailable):
    """A protected static security policy identity or value changed."""

    reason_code = "AUTHORITY_POLICY_INTEGRITY_COMPROMISED"


class _MissingBinding(PolicyIntegrityUnavailable):
    """A previously available protected policy holder is absent."""


def _safe_scalar(value: Any, *, allow_none: bool = False) -> str | None:
    if allow_none and value is None:
        return None
    if type(value) is not str:
        raise PolicyIntegrityUnavailable("policy schema is not measurable")
    return value


def _tuple_strings(value: Any) -> list[str]:
    if type(value) is not tuple or any(type(x) is not str for x in value):
        raise PolicyIntegrityUnavailable("policy schema is not measurable")
    return list(value)


def _canonical_material(kind: PolicyKind, policy: Any, key: bytes) -> bytes:
    """Exact known type grammar; no arbitrary repr(), callbacks or user JSON."""
    if kind == "path":
        from jack_path_policy import RuntimePathPolicy

        if type(policy) is not RuntimePathPolicy:
            raise PolicyIntegrityUnavailable("required path policy type unavailable")
        environment = policy._path_environment
        if type(environment) is not tuple or any(
            type(x) is not tuple or len(x) != 2 or
            type(x[0]) is not str or type(x[1]) is not str
            for x in environment
        ):
            raise PolicyIntegrityUnavailable("required path policy schema unavailable")
        data = {
            "runtime_id": _safe_scalar(policy.runtime_id),
            "lane_id": _safe_scalar(policy.lane_id),
            "workspace_root": _safe_scalar(policy.workspace_root, allow_none=True),
            "never_roots": _tuple_strings(policy.never_roots),
            "user_never_roots": _tuple_strings(policy.user_never_roots),
            "path_environment": [[k, v] for k, v in environment],
        }
    elif kind == "credential":
        from jack_credential_guard import (
            RuntimeCredentialPolicy, ProtectedCredential, CredentialClass,
        )

        if type(policy) is not RuntimeCredentialPolicy:
            raise PolicyIntegrityUnavailable("required credential policy type unavailable")
        if type(policy.credentials) is not tuple:
            raise PolicyIntegrityUnavailable("required credential policy schema unavailable")
        entries = []
        for item in policy.credentials:
            if (type(item) is not ProtectedCredential or
                type(item.credential_class) is not CredentialClass or
                type(item.authorized_destinations) is not frozenset or
                type(item.aliases) is not tuple or
                type(item.alias_classes) is not tuple or
                any(type(alias) is not CredentialClass for alias in item.alias_classes)):
                raise PolicyIntegrityUnavailable("required credential policy schema unavailable")
            destinations = sorted(item.authorized_destinations)
            if any(type(v) is not str for v in destinations):
                raise PolicyIntegrityUnavailable("required credential policy schema unavailable")
            value = _safe_scalar(item.value)
            entries.append({
                "id": _safe_scalar(item.credential_id),
                "class": item.credential_class.value,
                "source": _safe_scalar(item.source_kind),
                "destinations": destinations,
                "aliases": _tuple_strings(item.aliases),
                "alias_classes": [v.value for v in item.alias_classes],
                "secret_mac": hmac.new(key, value.encode("utf-8", "surrogatepass"),
                                       hashlib.sha256).hexdigest(),
            })
        data = {
            "runtime_id": _safe_scalar(policy.runtime_id),
            "lane_id": _safe_scalar(policy.lane_id),
            "resources": _tuple_strings(policy.protected_resources),
            "credentials": entries,
        }
    elif kind == "canary":
        from jack_evidence_guard import (
            RuntimeCanaryPolicy, DeterministicCanarySet, CanaryPattern, CanaryTier,
        )

        if type(policy) is not RuntimeCanaryPolicy or type(policy.canaries) is not DeterministicCanarySet:
            raise PolicyIntegrityUnavailable("required Canary policy type unavailable")
        patterns = policy.canaries._patterns
        if type(patterns) is not tuple:
            raise PolicyIntegrityUnavailable("required Canary schema unavailable")
        entries = []
        for item in patterns:
            if type(item) is not CanaryPattern or type(item.tier) is not CanaryTier:
                raise PolicyIntegrityUnavailable("required Canary schema unavailable")
            value = _safe_scalar(item.value)
            if item.sensitivity_percent is not None and (
                type(item.sensitivity_percent) is not int or not 1 <= item.sensitivity_percent <= 100
            ):
                raise PolicyIntegrityUnavailable("required Canary sensitivity schema unavailable")
            entries.append({
                "sensitivity_percent": item.sensitivity_percent,
                "match_chars": item.match_chars,
                "id": _safe_scalar(item.canary_id),
                "tier": item.tier.value,
                "value_mac": hmac.new(key, value.encode("utf-8", "surrogatepass"),
                                       hashlib.sha256).hexdigest(),
            })
        if policy.sensitivity_percent is not None and (
            type(policy.sensitivity_percent) is not int or not 1 <= policy.sensitivity_percent <= 100
        ):
            raise PolicyIntegrityUnavailable("required Canary sensitivity schema unavailable")
        for bound in (policy.canaries.max_window, policy.canaries.required_window):
            if type(bound) is not int:
                raise PolicyIntegrityUnavailable("required Canary window schema unavailable")
        data = {
            "runtime_id": _safe_scalar(policy.runtime_id),
            "lane_id": _safe_scalar(policy.lane_id),
            "sensitivity_percent": policy.sensitivity_percent,
            "max_window": policy.canaries.max_window,
            "required_window": policy.canaries.required_window,
            "patterns": entries,
        }
    else:
        raise ValueError("unknown protected policy kind")

    return json.dumps(
        {"schema": "jack.static-security-policy.v1", "kind": kind, "policy": data},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8", "surrogatepass")


def _digest(kind: PolicyKind, policy: Any, key: bytes) -> bytes:
    try:
        material = _canonical_material(kind, policy, key)
        return hmac.new(key, material, hashlib.sha256).digest()
    except PolicyIntegrityUnavailable:
        raise
    except Exception as exc:
        raise PolicyIntegrityUnavailable("required policy measurement unavailable") from exc


@dataclass(frozen=True)
class _PolicyEntry:
    label: str
    kind: PolicyKind
    holder: Any
    attribute: str | None
    cell: types.CellType | None
    policy: Any
    digest: bytes


class RuntimePolicyAuthority:
    """Opt-in policy measurement; no runtime admission/release hook yet."""

    def __init__(self) -> None:
        self._key = secrets.token_bytes(32)
        self._lock = threading.RLock()
        self._entries: dict[str, _PolicyEntry] = {}
        self._sealed = False
        self._invalid: set[str] = set()
        self._uncertain: set[str] = set()

    @staticmethod
    def _read(entry: _PolicyEntry) -> Any:
        if entry.cell is not None:
            try:
                return entry.cell.cell_contents
            except ValueError as exc:
                raise _MissingBinding("required active policy cell empty") from exc
        try:
            return getattr(entry.holder, entry.attribute)
        except AttributeError as exc:
            raise _MissingBinding("required active policy holder missing") from exc
        except Exception as exc:
            raise PolicyIntegrityUnavailable("required active policy reference unavailable") from exc

    def _register(self, label: str, kind: PolicyKind, holder: Any,
                  attribute: str | None, cell: types.CellType | None) -> None:
        if not isinstance(label, str) or not label or kind not in ("path", "canary", "credential"):
            raise ValueError("invalid protected policy label or kind")
        if cell is None and (not isinstance(attribute, str) or not attribute):
            raise ValueError("nonempty policy holder attribute required")
        with self._lock:
            if self._sealed or label in self._entries:
                raise RuntimeError("policy manifest sealed or duplicate label")
            provisional = _PolicyEntry(label, kind, holder, attribute, cell, None, b"")
            policy = self._read(provisional)
            digest = _digest(kind, policy, self._key)
            self._entries[label] = _PolicyEntry(
                label, kind, holder, attribute, cell, policy, digest,
            )

    def register_attribute(self, *, label: str, kind: PolicyKind,
                           holder: Any, attribute: str) -> None:
        self._register(label, kind, holder, attribute, None)

    def register_cell(self, *, label: str, kind: PolicyKind,
                      cell: types.CellType) -> None:
        if not isinstance(cell, types.CellType):
            raise TypeError("policy closure must be an actual Python cell")
        self._register(label, kind, None, None, cell)

    def seal(self) -> None:
        with self._lock:
            if self._sealed or not self._entries:
                raise PolicyIntegrityUnavailable("nonempty unsealed policy manifest required")
            self._check_locked(tuple(self._entries))
            self._sealed = True

    def _check_locked(self, labels: tuple[str, ...]) -> None:
        newly_invalid: set[str] = set()
        newly_uncertain: set[str] = set()
        for label in labels:
            entry = self._entries[label]
            try:
                policy = self._read(entry)
            except _MissingBinding:
                newly_invalid.add(label)
                continue
            except PolicyIntegrityUnavailable:
                newly_uncertain.add(label)
                continue
            if policy is not entry.policy:
                newly_invalid.add(label)
                continue
            try:
                current_digest = _digest(entry.kind, policy, self._key)
            except PolicyIntegrityUnavailable:
                newly_uncertain.add(label)
                continue
            if not hmac.compare_digest(current_digest, entry.digest):
                newly_invalid.add(label)
        if newly_invalid:
            self._invalid.update(newly_invalid)
            raise PolicyIntegrityCompromised("active security policy identity changed")
        if newly_uncertain:
            self._uncertain.update(newly_uncertain)
            raise PolicyIntegrityUnavailable("required active security policy cannot be measured")
        self._uncertain.difference_update(labels)

    def verify_for(self, *labels: str) -> None:
        if not labels or any(not isinstance(label, str) for label in labels):
            raise ValueError("policy label must be explicitly selected")
        with self._lock:
            if not self._sealed:
                raise PolicyIntegrityUnavailable("active policy manifest not sealed")
            if any(label not in self._entries for label in labels):
                raise PolicyIntegrityUnavailable("unknown required active policy label")
            if any(label in self._invalid for label in labels):
                raise PolicyIntegrityCompromised("active security policy invalidated")
            self._check_locked(tuple(dict.fromkeys(labels)))

    @property
    def invalidated_labels(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._invalid))

    @property
    def state(self) -> str:
        with self._lock:
            if self._invalid:
                return "INVALIDATED"
            if self._uncertain:
                return "SUSPENDED_UNVERIFIED"
            return "ACTIVE" if self._sealed else "INITIALIZING"
