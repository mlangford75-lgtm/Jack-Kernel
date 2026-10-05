from __future__ import annotations

import logging
import threading
from typing import Any, Optional


BOUNDARY_HTTP_EXCEPTION_RELEASE = "diagnostic_http_exception_release"
BOUNDARY_STREAM_EXCEPTION_RELEASE = "diagnostic_stream_exception_release"
BOUNDARY_LOG_RELEASE = "diagnostic_log_release"
BOUNDARY_INTERNAL_DIAGNOSTIC_STATE = "diagnostic_internal_state"

DIRECTION_CALLER_BOUND = "caller_bound"
DIRECTION_OBSERVER_BOUND = "observer_bound"
DIRECTION_HOST_STATE = "host_state"

DIAGNOSTIC_BLOCK_ERROR = "protected_credential_diagnostic_withheld"
DIAGNOSTIC_LOG_MESSAGE = (
    "Jack diagnostic withheld because it contained a protected runtime credential"
)
DIAGNOSTIC_STATE_MESSAGE = "protected credential diagnostic withheld"


def _policy_match(
    policy: Any,
    value: Any,
    *,
    boundary: str,
    direction: str,
) -> Any:
    """Find exact protected values in complete diagnostic structure.

    RuntimeCredentialPolicy deliberately treats JSON/container keys as protocol
    structure for model payloads. Diagnostic material is different: arbitrary
    exception/detail dictionaries can place caller-visible text in either keys or
    values. This release guard therefore checks both without changing the global
    credential-policy semantics used by model dispatch.
    """
    finder = getattr(policy, "find", None)
    if not callable(finder):
        raise TypeError("diagnostic guard requires a runtime credential policy")

    if isinstance(value, (bytes, bytearray)):
        value = bytes(value).decode("utf-8", "replace")

    match = finder(value, boundary=boundary, direction=direction)
    if match is not None:
        return match

    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                match = finder(key, boundary=boundary, direction=direction)
                if match is not None:
                    return match
            match = _policy_match(
                policy,
                item,
                boundary=boundary,
                direction=direction,
            )
            if match is not None:
                return match
        return None

    if isinstance(value, (list, tuple)):
        for item in value:
            match = _policy_match(
                policy,
                item,
                boundary=boundary,
                direction=direction,
            )
            if match is not None:
                return match
    return None


def _blocked_payload(boundary: str) -> dict[str, str]:
    return {
        "error": DIAGNOSTIC_BLOCK_ERROR,
        "security_outcome": "HARD_INTERRUPT",
        "release_boundary": boundary,
    }


def _safe_headers(
    policy: Any,
    headers: Any,
    *,
    boundary: str,
    direction: str,
) -> tuple[Optional[dict[str, str]], bool]:
    """Preserve clean exception headers and omit only proven credential carriers."""
    if headers is None:
        return None, False
    if not isinstance(headers, dict):
        match = _policy_match(
            policy,
            headers,
            boundary=boundary,
            direction=direction,
        )
        return (None, match is not None)

    safe: dict[str, str] = {}
    violated = False
    for key, value in headers.items():
        pair = {str(key): str(value)}
        if _policy_match(
            policy,
            pair,
            boundary=boundary,
            direction=direction,
        ) is not None:
            violated = True
            continue
        safe[str(key)] = str(value)
    return (safe or None), violated


def _exception_material(exc: BaseException) -> str:
    """Collect exception-chain text without traceback locals or object repr dumps."""
    parts = []
    seen = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        try:
            parts.append(f"{type(current).__name__}: {current}")
        except Exception:
            parts.append(type(current).__name__)
        cause = getattr(current, "__cause__", None)
        if cause is not None:
            current = cause
            continue
        if getattr(current, "__suppress_context__", False):
            current = None
        else:
            context = getattr(current, "__context__", None)
            current = context if isinstance(context, BaseException) else None
    return "\n".join(parts)


def _exception_has_credential(
    policy: Any,
    exc: BaseException,
    *,
    boundary: str,
    direction: str,
) -> bool:
    detail = getattr(exc, "detail", None)
    if detail is not None and _policy_match(
        policy,
        detail,
        boundary=boundary,
        direction=direction,
    ) is not None:
        return True
    headers = getattr(exc, "headers", None)
    if headers is not None and _policy_match(
        policy,
        headers,
        boundary=boundary,
        direction=direction,
    ) is not None:
        return True
    return _policy_match(
        policy,
        _exception_material(exc),
        boundary=boundary,
        direction=direction,
    ) is not None


class _CredentialDiagnosticLogFilter(logging.Filter):
    """Process-local aggregate of immutable runtime credential policies.

    Jack's named logger is process-global even when tests or an embedding host load
    more than one runtime instance. No single runtime may monopolize that observer
    boundary. Registration is copy-on-write under a mutex; log filtering reads the
    immutable tuple without taking the authority-registration lock.
    """

    def __init__(self, policy: Any) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._policies = ()
        self.add_policy(policy)

    @staticmethod
    def _identity(policy: Any) -> tuple[str, str]:
        return (
            str(getattr(policy, "runtime_id", "") or ""),
            str(getattr(policy, "lane_id", "") or ""),
        )

    def add_policy(self, policy: Any) -> None:
        if not callable(getattr(policy, "find", None)):
            raise TypeError("diagnostic log guard requires a runtime credential policy")
        identity = self._identity(policy)
        if not all(identity):
            raise RuntimeError("diagnostic log policy requires runtime/lane identity")

        with self._lock:
            for existing in self._policies:
                if self._identity(existing) != identity:
                    continue
                if existing is policy:
                    return
                existing_credentials = tuple(getattr(existing, "credentials", ()))
                incoming_credentials = tuple(getattr(policy, "credentials", ()))
                if existing_credentials != incoming_credentials:
                    raise RuntimeError(
                        "diagnostic log policy identity cannot be rebound to different credentials"
                    )
                return
            self._policies = self._policies + (policy,)

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            material = record.getMessage()
        except Exception:
            material = str(getattr(record, "msg", ""))

        exc_info = getattr(record, "exc_info", None)
        if exc_info and len(exc_info) >= 2 and isinstance(exc_info[1], BaseException):
            material += "\n" + _exception_material(exc_info[1])

        for policy in self._policies:
            match = _policy_match(
                policy,
                material,
                boundary=BOUNDARY_LOG_RELEASE,
                direction=DIRECTION_OBSERVER_BOUND,
            )
            if match is None:
                continue
            record.msg = DIAGNOSTIC_LOG_MESSAGE
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
            break
        return True


def _install_http_exception_guard(jk: Any, policy: Any) -> bool:
    app = getattr(jk, "APP", None)
    http_exception_type = getattr(jk, "HTTPException", None)
    if app is None or http_exception_type is None:
        return False
    if getattr(app, "_jack_phase7_diagnostic_http_guard", False):
        return True

    from fastapi.exception_handlers import http_exception_handler as default_handler
    from fastapi.responses import JSONResponse

    previous = getattr(app, "exception_handlers", {}).get(http_exception_type)

    async def guarded_http_exception(request: Any, exc: Any):
        detail = getattr(exc, "detail", None)
        detail_match = _policy_match(
            policy,
            detail,
            boundary=BOUNDARY_HTTP_EXCEPTION_RELEASE,
            direction=DIRECTION_CALLER_BOUND,
        )
        safe_headers, header_violation = _safe_headers(
            policy,
            getattr(exc, "headers", None),
            boundary=BOUNDARY_HTTP_EXCEPTION_RELEASE,
            direction=DIRECTION_CALLER_BOUND,
        )
        if detail_match is not None or header_violation:
            return JSONResponse(
                status_code=int(getattr(exc, "status_code", 500) or 500),
                content={"detail": _blocked_payload(BOUNDARY_HTTP_EXCEPTION_RELEASE)},
                headers=safe_headers,
            )
        if previous is not None:
            return await previous(request, exc)
        return await default_handler(request, exc)

    app.add_exception_handler(http_exception_type, guarded_http_exception)
    app._jack_phase7_diagnostic_http_guard = True
    return True


def _install_stream_exception_guard(jk: Any, policy: Any) -> bool:
    kernel = getattr(jk, "KERNEL", None)
    http_exception_type = getattr(jk, "HTTPException", None)
    original_stream = getattr(kernel, "stream", None) if kernel is not None else None
    if not callable(original_stream) or http_exception_type is None:
        return False
    if getattr(original_stream, "_jack_phase7_diagnostic_stream_guard", False):
        return True

    async def guarded_stream(*args: Any, **kwargs: Any):
        try:
            async for chunk in original_stream(*args, **kwargs):
                yield chunk
        except Exception as exc:
            if not _exception_has_credential(
                policy,
                exc,
                boundary=BOUNDARY_STREAM_EXCEPTION_RELEASE,
                direction=DIRECTION_CALLER_BOUND,
            ):
                raise

            status_code = (
                int(getattr(exc, "status_code", 502) or 502)
                if isinstance(exc, http_exception_type)
                else 502
            )
            safe_headers, _ = _safe_headers(
                policy,
                getattr(exc, "headers", None) if isinstance(exc, http_exception_type) else None,
                boundary=BOUNDARY_STREAM_EXCEPTION_RELEASE,
                direction=DIRECTION_CALLER_BOUND,
            )
            raise http_exception_type(
                status_code=status_code,
                detail=_blocked_payload(BOUNDARY_STREAM_EXCEPTION_RELEASE),
                headers=safe_headers,
            ) from None

    guarded_stream._jack_phase7_diagnostic_stream_guard = True
    guarded_stream._jack_phase7_original_stream = original_stream
    kernel.stream = guarded_stream
    return True


def _install_log_guard(jk: Any, policy: Any) -> bool:
    logger = getattr(jk, "LOG", None)
    if not isinstance(logger, logging.Logger):
        return False

    existing = getattr(logger, "_jack_phase7_diagnostic_log_filter", None)
    if getattr(logger, "_jack_phase7_diagnostic_log_guard", False):
        if not isinstance(existing, _CredentialDiagnosticLogFilter):
            raise RuntimeError("installed diagnostic log guard state is invalid")
        existing.add_policy(policy)
        return True

    filt = _CredentialDiagnosticLogFilter(policy)
    logger.addFilter(filt)
    logger._jack_phase7_diagnostic_log_filter = filt
    logger._jack_phase7_diagnostic_log_guard = True
    return True


def _install_internal_state_guard(jk: Any, policy: Any) -> bool:
    hub_type = getattr(jk, "OrchestrationEventHub", None)
    if hub_type is None:
        return False
    original_setattr = getattr(hub_type, "__setattr__", None)
    if not callable(original_setattr):
        return False
    if getattr(original_setattr, "_jack_phase7_diagnostic_state_guard", False):
        return True

    def guarded_setattr(self: Any, name: str, value: Any) -> None:
        if name == "_last_error" and value is not None:
            match = _policy_match(
                policy,
                value,
                boundary=BOUNDARY_INTERNAL_DIAGNOSTIC_STATE,
                direction=DIRECTION_HOST_STATE,
            )
            if match is not None:
                value = DIAGNOSTIC_STATE_MESSAGE
        original_setattr(self, name, value)

    guarded_setattr._jack_phase7_diagnostic_state_guard = True
    guarded_setattr._jack_phase7_original_setattr = original_setattr
    hub_type.__setattr__ = guarded_setattr

    instance = getattr(jk, "ORCHESTRATION_EVENTS", None)
    if instance is not None:
        current = getattr(instance, "_last_error", None)
        if current is not None and _policy_match(
            policy,
            current,
            boundary=BOUNDARY_INTERNAL_DIAGNOSTIC_STATE,
            direction=DIRECTION_HOST_STATE,
        ) is not None:
            original_setattr(instance, "_last_error", DIAGNOSTIC_STATE_MESSAGE)
    return True


def install(jk: Any, *, credential_policy: Any) -> None:
    """Install exact credential protection on diagnostic/error release surfaces."""

    if getattr(jk, "_JACK_DIAGNOSTIC_CREDENTIAL_DLP_INSTALLED", False):
        return

    live_runtime = (
        callable(getattr(jk, "_install_bundled_runtime_extensions", None))
        and getattr(jk, "APP", None) is not None
        and getattr(jk, "KERNEL", None) is not None
    )
    if not live_runtime:
        return

    installed = (
        _install_http_exception_guard(jk, credential_policy),
        _install_stream_exception_guard(jk, credential_policy),
        _install_log_guard(jk, credential_policy),
        _install_internal_state_guard(jk, credential_policy),
    )
    if not all(installed):
        raise RuntimeError("Phase-7 diagnostic credential DLP could not bind all live surfaces")

    jk._JACK_DIAGNOSTIC_CREDENTIAL_DLP_INSTALLED = True

    register = getattr(jk, "_register_runtime_manifest_components", None)
    if callable(register):
        from pathlib import Path
        register({"jack_diagnostic_guard.py": Path(__file__).resolve()})
