from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, FrozenSet, Optional, Tuple


CREDENTIAL_CANARY_MAX_WINDOW = 4096

BOUNDARY_MODEL_INPUT_DISPATCH = "model_input_dispatch"
DIRECTION_MODEL_BOUND = "model_bound"

DEST_JACK_PUBLIC_AUTH = "jack_public_auth"
DEST_BACKEND_AUTH_HEADER = "backend_auth_header"
DEST_BACKEND_NAMED_AUTH_HEADER = "backend_named_auth_header"
DEST_BACKEND_BASIC_DERIVATION = "backend_basic_derivation"
DEST_BACKEND_AUTHORIZATION_HEADER = "backend_authorization_header"
DEST_PI_CONTROL_AUTH_HEADER = "pi_control_authorization_header"


class CredentialClass(str, Enum):
    JACK_API = "JACK_API"
    BACKEND_BEARER = "BACKEND_BEARER"
    BACKEND_NAMED_HEADER = "BACKEND_NAMED_HEADER"
    BACKEND_BASIC_PASSWORD = "BACKEND_BASIC_PASSWORD"
    BACKEND_BASIC_WIRE = "BACKEND_BASIC_WIRE"
    BACKEND_AUTHORIZATION = "BACKEND_AUTHORIZATION"
    PI_CONTROL = "PI_CONTROL"


_CREDENTIAL_IDS = {
    CredentialClass.JACK_API: "credential:jack-api",
    CredentialClass.BACKEND_BEARER: "credential:backend-bearer",
    CredentialClass.BACKEND_NAMED_HEADER: "credential:backend-header",
    CredentialClass.BACKEND_BASIC_PASSWORD: "credential:backend-basic-password",
    CredentialClass.BACKEND_BASIC_WIRE: "credential:backend-basic-wire",
    CredentialClass.BACKEND_AUTHORIZATION: "credential:backend-authorization",
    CredentialClass.PI_CONTROL: "credential:pi-control",
}


@dataclass(frozen=True, repr=False)
class ProtectedCredential:
    credential_id: str
    credential_class: CredentialClass
    source_kind: str
    authorized_destinations: FrozenSet[str]
    aliases: Tuple[str, ...] = ()
    alias_classes: Tuple[CredentialClass, ...] = ()
    value: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.credential_id, str) or not self.credential_id:
            raise TypeError("credential_id must be a non-empty string")
        if not isinstance(self.credential_class, CredentialClass):
            raise TypeError("credential_class must be a CredentialClass")
        if not isinstance(self.source_kind, str) or not self.source_kind:
            raise TypeError("source_kind must be a non-empty string")
        if not isinstance(self.authorized_destinations, frozenset):
            raise TypeError("authorized_destinations must be a frozenset")
        if not isinstance(self.value, str):
            raise TypeError("credential value must be a string")
        if not self.value:
            raise ValueError("credential value must not be empty")

    def __repr__(self) -> str:
        return (
            "ProtectedCredential("
            f"credential_id={self.credential_id!r}, "
            f"credential_class={self.credential_class.value!r}, "
            f"source_kind={self.source_kind!r}, "
            f"authorized_destinations={sorted(self.authorized_destinations)!r}, "
            f"aliases={self.aliases!r}, "
            f"alias_classes={[item.value for item in self.alias_classes]!r}, "
            "value=<protected>)"
        )


@dataclass(frozen=True)
class CredentialMatch:
    credential_id: str
    credential_class: CredentialClass
    boundary: str
    direction: str
    aliases: Tuple[str, ...] = ()
    alias_classes: Tuple[CredentialClass, ...] = ()


class ProtectedCredentialInterrupt(RuntimeError):
    def __init__(self, match: CredentialMatch) -> None:
        if not isinstance(match, CredentialMatch):
            raise TypeError("match must be a CredentialMatch")
        self.match = match
        super().__init__("Phase-7 protected credential hard interrupt")


@dataclass(frozen=True, repr=False)
class RuntimeCredentialPolicy:
    runtime_id: str
    lane_id: str
    credentials: Tuple[ProtectedCredential, ...]
    protected_resources: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.runtime_id, str) or not self.runtime_id:
            raise ValueError("runtime_id must be a non-empty string")
        if not isinstance(self.lane_id, str) or not self.lane_id:
            raise ValueError("lane_id must be a non-empty string")
        if not isinstance(self.credentials, tuple):
            raise TypeError("credentials must be a tuple")
        if not isinstance(self.protected_resources, tuple):
            raise TypeError("protected_resources must be a tuple")

        ids = set()
        values = set()
        for item in self.credentials:
            if not isinstance(item, ProtectedCredential):
                raise TypeError("credentials must contain ProtectedCredential instances")
            if item.credential_id in ids:
                raise ValueError("duplicate credential_id")
            if item.value in values:
                raise ValueError("duplicate credential value")
            ids.add(item.credential_id)
            values.add(item.value)

    @property
    def count(self) -> int:
        return len(self.credentials)

    @property
    def required_window(self) -> int:
        return max((len(item.value) - 1 for item in self.credentials), default=0)

    def __repr__(self) -> str:
        return (
            "RuntimeCredentialPolicy("
            f"runtime_id={self.runtime_id!r}, "
            f"lane_id={self.lane_id!r}, "
            f"credential_count={len(self.credentials)}, "
            f"protected_resource_count={len(self.protected_resources)})"
        )

    def find(self, value: Any, *, boundary: str, direction: str) -> Optional[CredentialMatch]:
        def scan(node: Any) -> Optional[ProtectedCredential]:
            if isinstance(node, str):
                best = None
                for credential in self.credentials:
                    index = node.find(credential.value)
                    if index < 0:
                        continue
                    key = (index, len(credential.value), credential.credential_id)
                    if best is None or key < best[0]:
                        best = (key, credential)
                return None if best is None else best[1]
            if isinstance(node, dict):
                for item in node.values():
                    found = scan(item)
                    if found is not None:
                        return found
                return None
            if isinstance(node, (list, tuple)):
                for item in node:
                    found = scan(item)
                    if found is not None:
                        return found
                return None
            return None

        found = scan(value)
        if found is None:
            return None
        return CredentialMatch(
            credential_id=found.credential_id,
            credential_class=found.credential_class,
            boundary=str(boundary),
            direction=str(direction),
            aliases=found.aliases,
            alias_classes=found.alias_classes,
        )

    def guard_model_payload(self, payload: Any) -> None:
        match = self.find(
            payload,
            boundary=BOUNDARY_MODEL_INPUT_DISPATCH,
            direction=DIRECTION_MODEL_BOUND,
        )
        if match is not None:
            raise ProtectedCredentialInterrupt(match)


def _validated_secret(value: Any, *, source_kind: str) -> Optional[str]:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise RuntimeError(f"Phase-7 credential source {source_kind} is not textual")
    return value


def _basic_wire(username: Any, password: Optional[str]) -> Optional[str]:
    if password is None:
        return None
    user = "" if username is None else str(username)
    encoded = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


def _credential_resource_paths() -> Tuple[str, ...]:
    home = Path.home()
    if os.name == "nt":
        appdata = os.getenv("APPDATA", "").strip()
        root = Path(appdata) if appdata else home / "AppData" / "Roaming"
        jack_config = root / "JackKernelLMStudio" / "config.json"
    else:
        jack_config = home / ".jack-kernel-lm-studio" / "config.json"
    pi_config = home / ".pi" / "agent" / "jack-kernel.json"
    return (str(jack_config), str(pi_config))


def _logical_sources(jk: Any) -> Tuple[tuple, ...]:
    cfg = getattr(jk, "CFG", None)
    if cfg is None:
        raise RuntimeError("Phase-7 credential policy requires Jack CFG")

    jack_api = _validated_secret(getattr(cfg, "api_key", ""), source_kind="CFG.api_key")
    backend_bearer = _validated_secret(getattr(cfg, "backend_api_key", ""), source_kind="CFG.backend_api_key")
    backend_header = _validated_secret(getattr(cfg, "backend_header_value", ""), source_kind="CFG.backend_header_value")
    backend_password = _validated_secret(getattr(cfg, "backend_password", ""), source_kind="CFG.backend_password")
    backend_authorization = _validated_secret(getattr(cfg, "backend_authorization_value", ""), source_kind="CFG.backend_authorization_value")

    basic_wire = _basic_wire(getattr(cfg, "backend_username", ""), backend_password)
    if basic_wire is not None:
        basic_wire = _validated_secret(basic_wire, source_kind="derived_backend_basic_wire")

    pi_control = None
    loader = getattr(jk, "_load_pi_control_bridge", None)
    if callable(loader):
        try:
            bridge = loader()
        except Exception:
            raise RuntimeError("Phase-7 Pi control credential resolution failed") from None
        if isinstance(bridge, dict):
            pi_control = _validated_secret(bridge.get("token", ""), source_kind="resolved_pi_control_token")

    return (
        (CredentialClass.JACK_API, "CFG.api_key", jack_api, frozenset({DEST_JACK_PUBLIC_AUTH})),
        (CredentialClass.BACKEND_BEARER, "CFG.backend_api_key", backend_bearer, frozenset({DEST_BACKEND_AUTH_HEADER})),
        (CredentialClass.BACKEND_NAMED_HEADER, "CFG.backend_header_value", backend_header, frozenset({DEST_BACKEND_NAMED_AUTH_HEADER})),
        (CredentialClass.BACKEND_BASIC_PASSWORD, "CFG.backend_password", backend_password, frozenset({DEST_BACKEND_BASIC_DERIVATION})),
        (CredentialClass.BACKEND_BASIC_WIRE, "derived_backend_basic_wire", basic_wire, frozenset({DEST_BACKEND_AUTHORIZATION_HEADER})),
        (CredentialClass.BACKEND_AUTHORIZATION, "CFG.backend_authorization_value", backend_authorization, frozenset({DEST_BACKEND_AUTHORIZATION_HEADER})),
        (CredentialClass.PI_CONTROL, "resolved_pi_control_token", pi_control, frozenset({DEST_PI_CONTROL_AUTH_HEADER})),
    )


def build_runtime_credential_policy(jk: Any) -> RuntimeCredentialPolicy:
    runtime_id = str(getattr(jk, "RUNTIME_ID", "") or "").strip()
    lane_id = str(getattr(jk, "LANE_ID", "") or "").strip()
    if not runtime_id:
        raise RuntimeError("Phase-7 runtime identity is unavailable")
    if not lane_id:
        raise RuntimeError("Phase-7 lane identity is unavailable")

    by_value = {}
    order = []
    for credential_class, source_kind, value, destinations in _logical_sources(jk):
        if value is None:
            continue
        credential_id = _CREDENTIAL_IDS[credential_class]
        if value not in by_value:
            by_value[value] = {
                "credential_id": credential_id,
                "credential_class": credential_class,
                "source_kind": source_kind,
                "authorized_destinations": set(destinations),
                "aliases": [],
                "alias_classes": [],
            }
            order.append(value)
            continue
        entry = by_value[value]
        entry["authorized_destinations"].update(destinations)
        if credential_id != entry["credential_id"] and credential_id not in entry["aliases"]:
            entry["aliases"].append(credential_id)
        if credential_class != entry["credential_class"] and credential_class not in entry["alias_classes"]:
            entry["alias_classes"].append(credential_class)

    credentials = []
    for value in order:
        entry = by_value[value]
        credentials.append(
            ProtectedCredential(
                credential_id=entry["credential_id"],
                credential_class=entry["credential_class"],
                source_kind=entry["source_kind"],
                authorized_destinations=frozenset(entry["authorized_destinations"]),
                aliases=tuple(entry["aliases"]),
                alias_classes=tuple(entry["alias_classes"]),
                value=value,
            )
        )

    return RuntimeCredentialPolicy(
        runtime_id=runtime_id,
        lane_id=lane_id,
        credentials=tuple(credentials),
        protected_resources=_credential_resource_paths(),
    )


def merge_runtime_canary_policy(canary_policy: Any, credential_policy: RuntimeCredentialPolicy):
    from jack_evidence_guard import CanaryPattern, CanaryTier, DeterministicCanarySet, RuntimeCanaryPolicy

    if not isinstance(credential_policy, RuntimeCredentialPolicy):
        raise TypeError("credential_policy must be a RuntimeCredentialPolicy")
    if not isinstance(canary_policy, RuntimeCanaryPolicy):
        raise TypeError("canary_policy must be a RuntimeCanaryPolicy")
    if canary_policy.runtime_id != credential_policy.runtime_id:
        raise RuntimeError("Phase-7 credential/Canary runtime ownership mismatch")
    if canary_policy.lane_id != credential_policy.lane_id:
        raise RuntimeError("Phase-7 credential/Canary lane ownership mismatch")
    if credential_policy.required_window > CREDENTIAL_CANARY_MAX_WINDOW:
        raise RuntimeError("Phase-7 credential Canary merge exceeds the bounded output-DLP ceiling")

    existing = tuple(getattr(canary_policy.canaries, "_patterns", ()))
    existing_ids = {item.canary_id for item in existing}
    existing_values = {item.value for item in existing}
    additions = []
    for credential in credential_policy.credentials:
        if credential.credential_id in existing_ids or credential.value in existing_values:
            raise RuntimeError("Phase-7 credential/Canary policy collision")
        additions.append(CanaryPattern(canary_id=credential.credential_id, tier=CanaryTier.A, value=credential.value))

    combined = existing + tuple(additions)
    max_window = max(int(getattr(canary_policy.canaries, "max_window", 0) or 0), credential_policy.required_window)
    return RuntimeCanaryPolicy(
        runtime_id=credential_policy.runtime_id,
        lane_id=credential_policy.lane_id,
        canaries=DeterministicCanarySet(combined, max_window=max_window),
    )


def _chat_completion_url(value: Any) -> bool:
    text = str(value or "").split("?", 1)[0].rstrip("/")
    return text.endswith("/chat/completions")


def _guard_post_call(policy: RuntimeCredentialPolicy, args: tuple, kwargs: dict) -> None:
    url = kwargs.get("url")
    if url is None and args:
        url = args[0]
    if not _chat_completion_url(url):
        return
    if "json" in kwargs:
        policy.guard_model_payload(kwargs.get("json"))


def _guard_build_request_call(policy: RuntimeCredentialPolicy, args: tuple, kwargs: dict) -> None:
    method = kwargs.get("method")
    url = kwargs.get("url")
    if method is None and args:
        method = args[0]
    if url is None and len(args) > 1:
        url = args[1]
    if str(method or "").upper() != "POST" or not _chat_completion_url(url):
        return
    if "json" in kwargs:
        policy.guard_model_payload(kwargs.get("json"))


def install(jk: Any, *, credential_policy: Optional[RuntimeCredentialPolicy] = None) -> RuntimeCredentialPolicy:
    existing = getattr(jk, "_JACK_RUNTIME_CREDENTIAL_POLICY", None)
    if getattr(jk, "_JACK_CREDENTIAL_GUARD_INSTALLED", False):
        if not isinstance(existing, RuntimeCredentialPolicy):
            raise RuntimeError("Phase-7 installed policy state is invalid")
        return existing

    if credential_policy is None:
        credential_policy = build_runtime_credential_policy(jk)
    elif not isinstance(credential_policy, RuntimeCredentialPolicy):
        raise TypeError("credential_policy must be a RuntimeCredentialPolicy")

    runtime_id = str(getattr(jk, "RUNTIME_ID", "") or "").strip()
    lane_id = str(getattr(jk, "LANE_ID", "") or "").strip()
    if credential_policy.runtime_id != runtime_id:
        raise RuntimeError("Phase-7 credential policy runtime ownership mismatch")
    if credential_policy.lane_id != lane_id:
        raise RuntimeError("Phase-7 credential policy lane ownership mismatch")

    backend = getattr(jk, "BACKEND", None)
    client = getattr(backend, "_client", None)
    if client is None:
        raise RuntimeError("Phase-7 backend transport is unavailable")

    original_post = getattr(client, "post", None)
    original_build_request = getattr(client, "build_request", None)
    if not callable(original_post) or not callable(original_build_request):
        raise RuntimeError("Phase-7 backend transport does not expose required dispatch seams")

    async def guarded_post(*args: Any, **kwargs: Any):
        _guard_post_call(credential_policy, args, kwargs)
        return await original_post(*args, **kwargs)

    def guarded_build_request(*args: Any, **kwargs: Any):
        _guard_build_request_call(credential_policy, args, kwargs)
        return original_build_request(*args, **kwargs)

    guarded_post._jack_phase7_credential_guard = True
    guarded_build_request._jack_phase7_credential_guard = True
    client.post = guarded_post
    client.build_request = guarded_build_request

    jk._JACK_RUNTIME_CREDENTIAL_POLICY = credential_policy
    jk._JACK_CREDENTIAL_GUARD_INSTALLED = True

    register = getattr(jk, "_register_runtime_manifest_components", None)
    if callable(register):
        register({"jack_credential_guard.py": Path(__file__).resolve()})

    return credential_policy
