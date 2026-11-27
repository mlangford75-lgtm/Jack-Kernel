"""Phase 11 candidate: exact protected-value redaction at diagnostic sinks.

Never rewrite model output, authenticated tool evidence, or authoritative state.
Optional archives containing protected data are withheld rather than falsified.
"""
import json
import logging
from dataclasses import dataclass


@dataclass(frozen=True, init=False, repr=False)
class PrivacyBoundary:
    _values: tuple
    _fragments: tuple

    def __init__(self, credential_policy, canary_policy):
        object.__setattr__(self, "_values", tuple(sorted({
            item.value for item in credential_policy.credentials
        } | {
            item.value for item in canary_policy.canaries._patterns
        }, key=lambda value: (-len(value), value))))
        object.__setattr__(self, "_fragments", tuple(
            (item.value, getattr(item, "match_chars", len(item.value)))
            for item in canary_policy.canaries._patterns
            if getattr(item, "match_chars", len(item.value)) < len(item.value)
        ))

    def _contains_fragment(self, text):
        # Match contiguous fragments without duplicating derived secrets.
        for value, width in self._fragments:
            if len(text) < width:
                continue
            if len(text) <= len(value):
                if any(text[i:i + width] in value for i in range(len(text) - width + 1)):
                    return True
            elif any(value[i:i + width] in text for i in range(len(value) - width + 1)):
                return True
        return False

    def _contains(self, text):
        return (any(value and value in text for value in self._values)
                or self._contains_fragment(text))

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
    from jack_policy_integrity_canary_enforcement import policy_cells
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
    """Inspect actual error responses; preserve established Phase 7 markers."""
    from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException as StarletteHTTPException

    from jack_policy_integrity import PolicyIntegrityUnavailable, PolicyIntegrityCompromised
    from jack_policy_integrity_dynamic_authority import DynamicAuthorityUnavailable

    async def authority_unavailable(request, exc):
        detail = ("AUTHORITY_POLICY_INTEGRITY_COMPROMISED"
                  if isinstance(exc, PolicyIntegrityCompromised)
                  else "Security authority unavailable")
        return JSONResponse(status_code=503, content={"detail": detail})

    jk.APP.add_exception_handler(PolicyIntegrityUnavailable, authority_unavailable)
    jk.APP.add_exception_handler(DynamicAuthorityUnavailable, authority_unavailable)

    for exception_type, default in (
        (jk.HTTPException, http_exception_handler),
        (StarletteHTTPException, http_exception_handler),
        (RequestValidationError, request_validation_exception_handler),
    ):
        previous = jk.APP.exception_handlers.get(exception_type, default)

        async def guarded(request, exc, _previous=previous):
            # The predecessor owns status, content and credential markers.
            # Examine its result before external release, including decoded
            # JSON (escaping must not hide a protected field).
            response = await _previous(request, exc)
            safe_headers = {}
            try:
                headers = response.raw_headers
                for key, value in headers:
                    if (key.lower() not in (b"content-type", b"content-length")
                            and boundary.permits_diagnostic((key, value))):
                        safe_headers[key.decode("latin-1")] = value.decode("latin-1")
                body = response.body
                safe = boundary.permits_diagnostic(body) and boundary.permits_diagnostic(headers)
                if safe and body:
                    try:
                        decoded = json.loads(body)
                    except (ValueError, UnicodeError):
                        pass
                    else:
                        safe = boundary.permits_diagnostic(decoded)
                if safe:
                    return response
            except Exception:
                pass
            return JSONResponse(
                status_code=response.status_code,
                content={"detail": "protected diagnostic withheld"},
                headers=safe_headers,
            )

        jk.APP.add_exception_handler(exception_type, guarded)
