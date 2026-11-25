"""Phase 11 candidate: exact protected-value redaction at diagnostic sinks.

Never rewrite model output, authenticated tool evidence, or authoritative state.
Optional archives containing protected data are withheld rather than falsified.
"""
import logging
import json


class PrivacyBoundary:
    def __init__(self, credential_policy, canary_policy):
        self._values = tuple(sorted({
            item.value for item in credential_policy.credentials
        } | {
            item.value for item in canary_policy.canaries._patterns
        }, key=lambda value: (-len(value), value)))

    def redact(self, text):
        for value in self._values:
            if value:
                text = text.replace(value, "[PROTECTED]")
        return text

    def permits_archive(self, value):
        # JSON escaping must not disguise a protected string in a value/key.
        def safe(node):
            if isinstance(node, str):
                return self.redact(node) == node
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
            return "Diagnostic unavailable (privacy boundary)"


def install(jk):
    from jack_phase10_canary_enforcement import policy_cells
    from jack_evidence_guard import RuntimeCanaryPolicy
    cells = policy_cells(jk.KERNEL.run, RuntimeCanaryPolicy)
    if not cells:
        raise RuntimeError("Required diagnostic privacy policy unavailable")
    boundary = PrivacyBoundary(jk._JACK_RUNTIME_CREDENTIAL_POLICY, cells[0].cell_contents)
    handlers = set(logging.getLogger().handlers)
    for logger in logging.Logger.manager.loggerDict.values():
        if isinstance(logger, logging.Logger):
            handlers.update(logger.handlers)
    for handler in handlers:
        handler.setFormatter(ProtectedDiagnosticFormatter(handler.formatter, boundary))
    jk._JACK_DIAGNOSTIC_PRIVACY = boundary
    return boundary
