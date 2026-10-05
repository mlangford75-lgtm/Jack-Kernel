from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, Optional

import jack_authority_ledger as authority_ledger


LOG = logging.getLogger("jack-kernel.phase7-ledger")


class Phase7LedgerEventType(str, Enum):
    PROTECTED_CREDENTIAL_MATCH = "PROTECTED_CREDENTIAL_MATCH"
    PROTECTED_CREDENTIAL_RESOURCE_BLOCKED = "PROTECTED_CREDENTIAL_RESOURCE_BLOCKED"


_CREDENTIAL_BOUNDARIES = frozenset(
    {
        "model_input_dispatch",
        "model_output_release",
        "orchestration_http_release",
        "orchestration_event_release",
        "diagnostic_http_exception_release",
        "diagnostic_stream_exception_release",
        "diagnostic_log_release",
        "diagnostic_internal_state",
    }
)
_CREDENTIAL_DIRECTIONS = frozenset(
    {"model_bound", "caller_bound", "observer_bound", "host_state"}
)


@dataclass(frozen=True)
class ProtectedCredentialMatchPayload:
    boundary: str
    direction: str
    credential_id: Optional[str]
    credential_class: Optional[str]


@dataclass(frozen=True)
class ProtectedCredentialResourceBlockedPayload:
    resource_id: str


# Process-global logging is the only Phase-7 observer that needs cross-runtime
# lookup. Key by the exact immutable credential-policy object, not merely the
# configured runtime/lane strings: isolated runtime instances may legitimately
# reuse the same configured identity in one embedding/test process.
_LEDGER_BY_POLICY_OBJECT: dict[int, authority_ledger.AuthorityLedger] = {}
_REGISTRY_LOCK = threading.Lock()
_LOG_HOOK_LOCK = threading.Lock()


def _identity(value: Any) -> tuple[str, str]:
    return (
        str(getattr(value, "runtime_id", "") or "").strip(),
        str(getattr(value, "lane_id", "") or "").strip(),
    )


def _safe_credential_id(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) > 128 or any(
        ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-"
        for ch in text
    ):
        return None
    return text


def _safe_class(value: Any) -> Optional[str]:
    raw = getattr(value, "value", value)
    text = str(raw or "").strip()
    if not text:
        return None
    if len(text) > 64 or not text.replace("_", "").isalnum():
        return None
    return text


def _record_failsoft(
    ledger: authority_ledger.AuthorityLedger,
    *,
    event_type: Phase7LedgerEventType,
    producer_code: str,
    boundary: str,
    outcome: str,
    containment_scope: str,
    fact_type: str,
    payload: dict[str, Any],
) -> bool:
    """Append to the existing Phase-6 chain without gaining authority over it."""
    try:
        ledger._advance(
            event_type=event_type,
            producer_code=producer_code,
            boundary=boundary,
            outcome=outcome,
            containment_scope=containment_scope,
            fact_type=fact_type,
            payload=payload,
        )
        return True
    except authority_ledger.LedgerAuthorityFrozen:
        return False
    except Exception as exc:
        try:
            ledger.freeze_authority(
                f"Phase-7 ledger recording failure: {type(exc).__name__}"
            )
        except Exception:
            pass
        LOG.exception(
            "Phase-7 ledger recording failed; ledger advancement frozen without changing security disposition"
        )
        return False


def record_credential_match_failsoft(
    ledger: authority_ledger.AuthorityLedger,
    *,
    boundary: str,
    direction: str,
    credential_id: Any = None,
    credential_class: Any = None,
    producer_code: str,
) -> bool:
    boundary_value = str(boundary or "")
    direction_value = str(direction or "")
    if boundary_value not in _CREDENTIAL_BOUNDARIES:
        raise ValueError("unsupported Phase-7 credential boundary")
    if direction_value not in _CREDENTIAL_DIRECTIONS:
        raise ValueError("unsupported Phase-7 credential direction")
    payload = ProtectedCredentialMatchPayload(
        boundary=boundary_value,
        direction=direction_value,
        credential_id=_safe_credential_id(credential_id),
        credential_class=_safe_class(credential_class),
    )
    return _record_failsoft(
        ledger,
        event_type=Phase7LedgerEventType.PROTECTED_CREDENTIAL_MATCH,
        producer_code=producer_code,
        boundary=boundary_value,
        outcome="HARD_INTERRUPT",
        containment_scope=boundary_value,
        fact_type="ProtectedCredentialMatch",
        payload=asdict(payload),
    )


def record_resource_block_failsoft(
    ledger: authority_ledger.AuthorityLedger,
    *,
    resource_id: str,
    containment_scope: str,
) -> bool:
    safe_id = _safe_credential_id(resource_id)
    if safe_id is None:
        raise ValueError("invalid credential resource_id")
    payload = ProtectedCredentialResourceBlockedPayload(resource_id=safe_id)
    return _record_failsoft(
        ledger,
        event_type=Phase7LedgerEventType.PROTECTED_CREDENTIAL_RESOURCE_BLOCKED,
        producer_code="phase7.credential_resource_gate",
        boundary="credential_resource_path",
        outcome="DENY_AND_CONTINUE",
        containment_scope=str(containment_scope or "tool_call"),
        fact_type="CredentialResourceAuthorityFact",
        payload=asdict(payload),
    )


def _detail_is_diagnostic_block(detail: Any) -> bool:
    if not isinstance(detail, dict):
        return False
    return detail.get("error") == "protected_credential_diagnostic_withheld"


def _response_is_orchestration_block(response: Any) -> bool:
    body = getattr(response, "body", None)
    if not isinstance(body, (bytes, bytearray)):
        return False
    try:
        payload = json.loads(bytes(body).decode("utf-8", "replace"))
    except Exception:
        return False
    return isinstance(payload, dict) and payload.get("error") == "orchestration_credential_release_blocked"


def _install_transport_hooks(
    jk: Any,
    ledger: authority_ledger.AuthorityLedger,
) -> None:
    """Observe model-input violations at the transport seam that owns the fact."""
    import jack_credential_guard as credential_guard

    backend = getattr(jk, "BACKEND", None)
    client = getattr(backend, "_client", None)
    if client is None:
        return

    current_post = getattr(client, "post", None)
    if callable(current_post) and not getattr(current_post, "_jack_phase7_ledger", False):
        original_post = current_post

        @wraps(original_post)
        async def recorded_post(*args: Any, **kwargs: Any):
            try:
                return await original_post(*args, **kwargs)
            except credential_guard.ProtectedCredentialInterrupt as exc:
                record_credential_match_failsoft(
                    ledger,
                    boundary=exc.match.boundary,
                    direction=exc.match.direction,
                    credential_id=exc.match.credential_id,
                    credential_class=exc.match.credential_class,
                    producer_code="phase7.model_input",
                )
                raise

        recorded_post._jack_phase7_ledger = True
        recorded_post._jack_phase7_original = original_post
        client.post = recorded_post

    current_build = getattr(client, "build_request", None)
    if callable(current_build) and not getattr(current_build, "_jack_phase7_ledger", False):
        original_build = current_build

        @wraps(original_build)
        def recorded_build_request(*args: Any, **kwargs: Any):
            try:
                return original_build(*args, **kwargs)
            except credential_guard.ProtectedCredentialInterrupt as exc:
                record_credential_match_failsoft(
                    ledger,
                    boundary=exc.match.boundary,
                    direction=exc.match.direction,
                    credential_id=exc.match.credential_id,
                    credential_class=exc.match.credential_class,
                    producer_code="phase7.model_input",
                )
                raise

        recorded_build_request._jack_phase7_ledger = True
        recorded_build_request._jack_phase7_original = original_build
        client.build_request = recorded_build_request


def _install_kernel_exception_hooks(
    jk: Any,
    ledger: authority_ledger.AuthorityLedger,
) -> None:
    import jack_evidence_guard as evidence_guard

    kernel = getattr(jk, "KERNEL", None)
    if kernel is None:
        raise RuntimeError("Phase-7 ledger requires Jack KERNEL")

    current_run = getattr(kernel, "run", None)
    current_stream = getattr(kernel, "stream", None)
    if not callable(current_run) or not callable(current_stream):
        raise RuntimeError("Phase-7 ledger requires Kernel release seams")

    if not getattr(current_run, "_jack_phase7_authority_ledger", False):
        original_run = current_run

        @wraps(original_run)
        async def phase7_run(*args: Any, **kwargs: Any):
            try:
                return await original_run(*args, **kwargs)
            except evidence_guard.StreamingIRQCanaryInterrupt as exc:
                canary_id = str(getattr(exc.match, "canary_id", "") or "")
                if canary_id.startswith("credential:"):
                    record_credential_match_failsoft(
                        ledger,
                        boundary="model_output_release",
                        direction="caller_bound",
                        credential_id=canary_id,
                        producer_code="phase7.model_output",
                    )
                raise

        phase7_run._jack_phase7_authority_ledger = True
        phase7_run._jack_phase7_original = original_run
        kernel.run = phase7_run

    if not getattr(current_stream, "_jack_phase7_authority_ledger", False):
        original_stream = current_stream

        @wraps(original_stream)
        async def phase7_stream(*args: Any, **kwargs: Any):
            try:
                async for chunk in original_stream(*args, **kwargs):
                    yield chunk
            except evidence_guard.StreamingIRQCanaryInterrupt as exc:
                canary_id = str(getattr(exc.match, "canary_id", "") or "")
                if canary_id.startswith("credential:"):
                    record_credential_match_failsoft(
                        ledger,
                        boundary="model_output_release",
                        direction="caller_bound",
                        credential_id=canary_id,
                        producer_code="phase7.model_output",
                    )
                raise
            except Exception as exc:
                detail = getattr(exc, "detail", None)
                if _detail_is_diagnostic_block(detail):
                    record_credential_match_failsoft(
                        ledger,
                        boundary="diagnostic_stream_exception_release",
                        direction="caller_bound",
                        producer_code="phase7.diagnostic_stream",
                    )
                raise

        phase7_stream._jack_phase7_authority_ledger = True
        phase7_stream._jack_phase7_original = original_stream
        kernel.stream = phase7_stream


def _install_http_diagnostic_hook(
    jk: Any,
    ledger: authority_ledger.AuthorityLedger,
) -> None:
    app = getattr(jk, "APP", None)
    http_exception_type = getattr(jk, "HTTPException", None)
    if app is None or http_exception_type is None:
        return
    current = getattr(app, "exception_handlers", {}).get(http_exception_type)
    if not callable(current) or getattr(current, "_jack_phase7_ledger", False):
        return

    @wraps(current)
    async def recorded_handler(request: Any, exc: Any):
        response = await current(request, exc)
        try:
            payload = json.loads(response.body.decode("utf-8", "replace"))
        except Exception:
            payload = None
        detail = payload.get("detail") if isinstance(payload, dict) else None
        if _detail_is_diagnostic_block(detail):
            record_credential_match_failsoft(
                ledger,
                boundary="diagnostic_http_exception_release",
                direction="caller_bound",
                producer_code="phase7.diagnostic_http",
            )
        return response

    recorded_handler._jack_phase7_ledger = True
    recorded_handler._jack_phase7_original = current
    app.add_exception_handler(http_exception_type, recorded_handler)


def _install_orchestration_hooks(
    jk: Any,
    ledger: authority_ledger.AuthorityLedger,
) -> None:
    current_proxy = getattr(jk, "_proxy_pi_control_request", None)
    if callable(current_proxy) and not getattr(current_proxy, "_jack_phase7_ledger", False):
        @wraps(current_proxy)
        async def recorded_proxy(*args: Any, **kwargs: Any):
            response = await current_proxy(*args, **kwargs)
            if _response_is_orchestration_block(response):
                record_credential_match_failsoft(
                    ledger,
                    boundary="orchestration_http_release",
                    direction="caller_bound",
                    producer_code="phase7.orchestration_http",
                )
            return response

        recorded_proxy._jack_phase7_ledger = True
        recorded_proxy._jack_phase7_original = current_proxy
        jk._proxy_pi_control_request = recorded_proxy

    hub_type = getattr(jk, "OrchestrationEventHub", None)
    current_publish = getattr(hub_type, "_publish", None) if hub_type is not None else None
    if callable(current_publish) and not getattr(current_publish, "_jack_phase7_ledger", False):
        @wraps(current_publish)
        async def recorded_publish(self: Any, *args: Any, **kwargs: Any):
            await current_publish(self, *args, **kwargs)
            lock = getattr(self, "_lock", None)
            if lock is None:
                return
            async with lock:
                last_recorded = int(
                    getattr(self, "_jack_phase7_ledger_recorded_seq", 0) or 0
                )
                events = [
                    event for event in getattr(self, "_buffer", ())
                    if int(event.get("seq") or 0) > last_recorded
                ]
                if events:
                    setattr(
                        self,
                        "_jack_phase7_ledger_recorded_seq",
                        max(int(event.get("seq") or 0) for event in events),
                    )
            for event in events:
                if event.get("type") == "orchestration_credential_release_blocked":
                    record_credential_match_failsoft(
                        ledger,
                        boundary="orchestration_event_release",
                        direction="caller_bound",
                        producer_code="phase7.orchestration_event",
                    )

        recorded_publish._jack_phase7_ledger = True
        recorded_publish._jack_phase7_original = current_publish
        hub_type._publish = recorded_publish


def _install_retained_diagnostic_hook(
    jk: Any,
    ledger: authority_ledger.AuthorityLedger,
    credential_policy: Any,
) -> None:
    hub_type = getattr(jk, "OrchestrationEventHub", None)
    current = getattr(hub_type, "__setattr__", None) if hub_type is not None else None
    if not callable(current) or getattr(current, "_jack_phase7_ledger", False):
        return

    def recorded_setattr(self: Any, name: str, value: Any) -> None:
        if name == "_last_error" and value is not None:
            match = credential_policy.find(
                value,
                boundary="diagnostic_internal_state",
                direction="host_state",
            )
            if match is not None:
                record_credential_match_failsoft(
                    ledger,
                    boundary="diagnostic_internal_state",
                    direction="host_state",
                    credential_id=match.credential_id,
                    credential_class=match.credential_class,
                    producer_code="phase7.diagnostic_state",
                )
        current(self, name, value)

    recorded_setattr._jack_phase7_ledger = True
    recorded_setattr._jack_phase7_original = current
    hub_type.__setattr__ = recorded_setattr


def _install_log_hook(jk: Any) -> None:
    """Augment the process-global diagnostic filter with exact-policy recording."""
    import jack_diagnostic_guard as diagnostic_guard

    filter_type = diagnostic_guard._CredentialDiagnosticLogFilter
    global _LOG_HOOK_LOCK
    with _LOG_HOOK_LOCK:
        current = filter_type.filter
        if getattr(current, "_jack_phase7_ledger", False):
            return
        original = current

        def ledger_filter(self: Any, record: logging.LogRecord) -> bool:
            try:
                material = record.getMessage()
            except Exception:
                material = str(getattr(record, "msg", ""))
            exc_info = getattr(record, "exc_info", None)
            if exc_info and len(exc_info) >= 2 and isinstance(exc_info[1], BaseException):
                material += "\n" + diagnostic_guard._exception_material(exc_info[1])

            matched_policy = None
            for policy in tuple(getattr(self, "_policies", ())):
                if diagnostic_guard._policy_match(
                    policy,
                    material,
                    boundary="diagnostic_log_release",
                    direction="observer_bound",
                ) is not None:
                    matched_policy = policy
                    break

            result = original(self, record)
            if matched_policy is not None:
                with _REGISTRY_LOCK:
                    ledger = _LEDGER_BY_POLICY_OBJECT.get(id(matched_policy))
                if ledger is not None:
                    record_credential_match_failsoft(
                        ledger,
                        boundary="diagnostic_log_release",
                        direction="observer_bound",
                        producer_code="phase7.diagnostic_log",
                    )
            return result

        ledger_filter._jack_phase7_ledger = True
        ledger_filter._jack_phase7_original = original
        filter_type.filter = ledger_filter


def install(
    jk: Any,
    *,
    ledger: authority_ledger.AuthorityLedger,
    credential_policy: Any,
) -> None:
    if getattr(jk, "_JACK_PHASE7_LEDGER_INSTALLED", False):
        return
    if not isinstance(ledger, authority_ledger.AuthorityLedger):
        raise TypeError("Phase-7 ledger extension requires AuthorityLedger")
    if _identity(ledger) != _identity(credential_policy):
        raise RuntimeError("Phase-7 ledger/credential policy ownership mismatch")

    with _REGISTRY_LOCK:
        policy_key = id(credential_policy)
        prior = _LEDGER_BY_POLICY_OBJECT.get(policy_key)
        if prior is not None and prior is not ledger:
            raise RuntimeError("Phase-7 credential policy cannot bind two ledgers")
        _LEDGER_BY_POLICY_OBJECT[policy_key] = ledger

    _install_transport_hooks(jk, ledger)
    _install_kernel_exception_hooks(jk, ledger)
    _install_http_diagnostic_hook(jk, ledger)
    _install_orchestration_hooks(jk, ledger)
    _install_retained_diagnostic_hook(jk, ledger, credential_policy)
    _install_log_hook(jk)

    jk.Phase7LedgerEventType = Phase7LedgerEventType
    jk._JACK_PHASE7_LEDGER_INSTALLED = True

    register = getattr(jk, "_register_runtime_manifest_components", None)
    if callable(register):
        register({"jack_phase7_ledger.py": Path(__file__).resolve()})
