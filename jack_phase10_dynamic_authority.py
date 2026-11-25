"""Scoped pending-tool authority integrity. All transitions use the existing kernel lock."""
import hashlib
import hmac
import json
import secrets
from dataclasses import asdict, is_dataclass


class DynamicAuthorityUnavailable(RuntimeError):
    pass


def _material(state):
    # Only authorization-bearing data; ordinary cognition/usage is not frozen.
    expected = state.expected_tool_call_ids
    calls = {}
    for message in reversed(state.history):
        if isinstance(message, dict):
            for call in message.get("tool_calls") or ():
                if isinstance(call, dict) and call.get("id") in expected:
                    calls.setdefault(call["id"], call)
    if set(calls) != set(expected):
        raise DynamicAuthorityUnavailable("pending authority unavailable")
    context = state.accepted_executor_context
    return json.dumps({
        "resume": state.resume_id, "stage": state.stage_key,
        "expected": expected, "withheld": state.withheld_tool_call_ids,
        "calls": calls, "results": state.accepted_tool_results,
        "context": asdict(context) if context is not None and is_dataclass(context) else None,
        "in_flight": state.in_flight,
    }, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8", "surrogatepass")


class PendingAuthority:
    def __init__(self):
        self._key = secrets.token_bytes(32)
        self._entries = {}
        self._invalid = set()

    def _digest(self, state):
        try:
            return hmac.new(self._key, _material(state), hashlib.sha256).digest()
        except Exception:
            raise DynamicAuthorityUnavailable("pending authority unavailable") from None

    def register(self, state):
        if state.resume_id in self._entries or state.resume_id in self._invalid:
            raise DynamicAuthorityUnavailable("pending authority already registered")
        self._entries[state.resume_id] = (state, self._digest(state))

    def verify(self, state):
        entry = self._entries.get(state.resume_id)
        if (state.resume_id in self._invalid or entry is None or entry[0] is not state
                or not hmac.compare_digest(entry[1], self._digest(state))):
            self._invalid.add(state.resume_id)
            raise DynamicAuthorityUnavailable("pending authority integrity compromised")

    def transition(self, state, *, in_flight, accept=None, context=None):
        self.verify(state)
        if accept is not None:
            if state.accepted_tool_results is not None:
                raise DynamicAuthorityUnavailable("pending authority already accepted")
            state.accepted_tool_results = accept
            state.accepted_executor_context = context
        state.in_flight = in_flight
        self._entries[state.resume_id] = (state, self._digest(state))

    def retire(self, state):
        entry = self._entries.get(state.resume_id)
        if entry is not None and entry[0] is state:
            self._entries.pop(state.resume_id)
            self._invalid.discard(state.resume_id)
