"""Phase 11 candidate: exact protected-value redaction at diagnostic sinks.

Never rewrite model output, authenticated tool evidence, or authoritative state.
Optional archives containing protected data are withheld rather than falsified.
"""
import logging
from dataclasses import dataclass


@dataclass(frozen=True, init=False, repr=False)
class PrivacyBoundary:
    _values: tuple

    def __init__(self, credential_policy, canary_policy):
        object.__setattr__(self, "_values", tuple(sorted({
            item.value for item in credential_policy.credentials
        } | {
            item.value for item in canary_policy.canaries._patterns
        }, key=lambda value: (-len(value), value))))

    def _contains(self, text):
        return any(value and value in text for value in self._values)

    def redact(self, text):
        if not self._contains(text):
            return text
        marker = next((candidate for candidate in ("[PROTECTED]", "[REDACTED]", "")
                       if not self._contains(candidate)), "")
        for value in self._values:
            if value:
                text = text.replace(value, marker)
        # A replacement may create a match across adjacent text boundaries.
        # Withhold the diagnostic rather than release any residual match.
        return "" if self._contains(text) else text

    def permits_diagnostic(self, value):
        """Inspect decoded diagnostic fields, including header names and values."""
        if isinstance(value, bytes):
            return not self._contains(value.decode("latin-1")) and not self._contains(
                value.decode("utf-8", "replace"))
        if isinstance(value, dict):
            return all(self.permits_diagnostic(k) and self.permits_diagnostic(v)
                       for k, v in value.items())
        if isinstance(value, (list, tuple)):
            return all(self.permits_diagnostic(item) for item in value)
        return self.permits_archive(value)

    def permits_archive(self, value):
        # JSON escaping must not disguise a protected string in a value/key.
        def safe(node):
            if isinstance(node, str):
                return not self._contains(node)
            if isinstance(node, dict):
                return all(safe(k) and safe(v) for k, v in node.items())
            if isinstance(node, (tuple, list)):
                return all(safe(v) for v in node)
            return node is None or type(node) in (bool, int, float)
        try:
            return safe(value)
        except Exception:
            return False


class ProtectedDiagnosticFormatter(logging.Formatter):
    def __init__(self, original, boundary):
        super().__init__()
        self.original = original or logging.Formatter()
        self.boundary = boundary

    def format(self, record):
        try:
            # After formatting: includes arguments and exception text.
            return self.boundary.redact(self.original.format(record))
        except Exception:
            return ""


def install(jk):
    from jack_phase10_canary_enforcement import policy_cells
    from jack_evidence_guard import RuntimeCanaryPolicy
    cells = policy_cells(jk.KERNEL.run, RuntimeCanaryPolicy)
    if not cells:
        raise RuntimeError("Required diagnostic privacy policy unavailable")
    boundary = PrivacyBoundary(jk._JACK_RUNTIME_CREDENTIAL_POLICY, cells[0].cell_contents)
    install_http_diagnostic_guard(jk, boundary)
    protect_logging_handlers(boundary)
    jk._JACK_DIAGNOSTIC_PRIVACY = boundary
    return boundary


def protect_logging_handlers(boundary):
    """Cover handlers added by the server after secure startup; idempotent."""
    handlers = set(logging.getLogger().handlers)
    for logger in tuple(logging.Logger.manager.loggerDict.values()):
        if isinstance(logger, logging.Logger):
            handlers.update(logger.handlers)
    for handler in handlers:
        original = handler.formatter
        if isinstance(original, ProtectedDiagnosticFormatter):
            if original.boundary is boundary:
                continue
            original = original.original
        handler.setFormatter(ProtectedDiagnosticFormatter(original, boundary))


def install_http_diagnostic_guard(jk, boundary):
    """Preserve predecessor HTTP exception handling; withhold unsafe diagnostics."""
    from fastapi.exception_handlers import http_exception_handler
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException as StarletteHTTPException

    for exception_type in {jk.HTTPException, StarletteHTTPException}:
        previous = jk.APP.exception_handlers.get(exception_type, http_exception_handler)

        async def guarded(request, exc, _previous=previous):
            try:
                detail_ok = boundary.permits_diagnostic(exc.detail)
                headers = exc.headers or {}
                safe_headers = {k: v for k, v in headers.items()
                                if boundary.permits_diagnostic((k, v))}
                if detail_ok and len(safe_headers) == len(headers):
                    return await _previous(request, exc)
            except Exception:
                safe_headers = {}
            # Preserve HTTP failure status and benign headers; do not echo
            # upstream content or invent a successful response.
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": "protected diagnostic withheld"},
                headers=safe_headers,
            )

        jk.APP.add_exception_handler(exception_type, guarded)
