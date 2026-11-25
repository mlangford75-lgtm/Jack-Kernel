"""Process-local pending-tool authority. Call only under the Kernel's existing resume lock.

This is not general interpreter attestation. The sealed call index detects a lost,
substituted or altered pending binding without trusting mutable state to find it.
"""
import copy
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass


class DynamicAuthorityUnavailable(RuntimeError):
    pass


def _ids(value):
    if type(value) is not tuple or any(type(x) is not str or not x or x != x.strip() for x in value):
        raise DynamicAuthorityUnavailable("pending authority unavailable")
    if len(set(value)) != len(value):
        raise DynamicAuthorityUnavailable("pending authority unavailable")
    return value


def _material(state, context_type):
    expected = _ids(state.expected_tool_call_ids)
    withheld = _ids(state.withheld_tool_call_ids)
    if not expected or set(expected).intersection(withheld):
        raise DynamicAuthorityUnavailable("pending authority unavailable")
    calls = {}
    for message in reversed(state.history):
        if isinstance(message, dict) and isinstance(message.get("tool_calls"), list):
            for call in message["tool_calls"]:
                if isinstance(call, dict):
                    call_id = str(call.get("id") or "").strip()
                    if call_id in expected:
                        calls.setdefault(call_id, call)
        if len(calls) == len(expected):
            break
    if set(calls) != set(expected):
        raise DynamicAuthorityUnavailable("pending authority unavailable")
    context = state.accepted_executor_context
    if context is not None:
        if context_type is None or type(context) is not context_type:
            raise DynamicAuthorityUnavailable("pending executor context unavailable")
        context = {name: getattr(context, name) for name in (
            "protocol_version", "runtime_id", "lane_id", "cwd", "platform",
            "adapter", "command_dialect",
        )}
        if (type(context["protocol_version"]) is not int or
                any(type(context[name]) is not str for name in (
                    "runtime_id", "lane_id", "cwd", "platform", "adapter")) or
                (context["command_dialect"] is not None and
                 type(context["command_dialect"]) is not str)):
            raise DynamicAuthorityUnavailable("pending executor context unavailable")
    if type(state.in_flight) is not bool:
        raise DynamicAuthorityUnavailable("pending authority unavailable")
    return json.dumps({
        "resume": state.resume_id, "stage": state.stage_key,
        "expected": expected, "withheld": withheld,
        "calls": calls, "results": state.accepted_tool_results,
        "context": context, "in_flight": state.in_flight,
        "created_at": state.created_at, "tools": state.tools,
        "tool_choice": state.tool_choice,
    }, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8", "surrogatepass")


@dataclass(frozen=True)
class _Entry:
    state: object
    resume_id: str
    expected: tuple
    withheld: tuple
    created_at: float
    in_flight: bool
    digest: bytes


class PendingAuthority:
    def __init__(self, context_type=None):
        self._context_type = context_type
        self._key = secrets.token_bytes(32)
        self._entries = {}
        self._invalid = set()

    def _digest(self, state):
        try:
            return hmac.new(self._key, _material(state, self._context_type), hashlib.sha256).digest()
        except Exception:
            raise DynamicAuthorityUnavailable("pending authority unavailable") from None

    def register(self, state):
        expected, withheld = _ids(state.expected_tool_call_ids), _ids(state.withheld_tool_call_ids)
        if id(state) in self._entries or any(e.resume_id == state.resume_id or
                set(e.expected).intersection(expected) for e in self._entries.values()):
            raise DynamicAuthorityUnavailable("pending authority already registered")
        self._entries[id(state)] = _Entry(state, state.resume_id, expected, withheld,
                                           state.created_at, state.in_flight, self._digest(state))

    def verify(self, state):
        key = id(state)
        entry = self._entries.get(key)
        if key in self._invalid or entry is None or entry.state is not state:
            raise DynamicAuthorityUnavailable("pending authority integrity unavailable")
        if not hmac.compare_digest(entry.digest, self._digest(state)):
            self._invalid.add(key)
            raise DynamicAuthorityUnavailable("pending authority integrity compromised")

    def verify_request(self, ids, live):
        """Check only transactions selected by the incoming IDs or their sealed IDs."""
        ids = set(ids)
        withheld = set()
        for entry in self._entries.values():
            if not ids.intersection(entry.expected + entry.withheld):
                continue
            self.verify(entry.state)
            if any(live.get(call_id) is not entry.state for call_id in entry.expected):
                self._invalid.add(id(entry.state))
                raise DynamicAuthorityUnavailable("pending binding integrity compromised")
            withheld.update(ids.intersection(entry.withheld))
        for call_id in ids:
            if call_id in live:
                state = live[call_id]
                self.verify(state)
                if call_id not in self._entries[id(state)].expected:
                    raise DynamicAuthorityUnavailable("pending binding integrity compromised")
        return withheld

    def transition(self, state, *, in_flight, accept=None, context=None):
        self.verify(state)
        entry = self._entries[id(state)]
        candidate = copy.copy(state)
        if accept is not None:
            if state.accepted_tool_results is not None:
                raise DynamicAuthorityUnavailable("pending authority already accepted")
            candidate.accepted_tool_results = copy.deepcopy(accept)
            candidate.accepted_executor_context = context
        candidate.in_flight = in_flight
        digest = self._digest(candidate)
        state.accepted_tool_results = candidate.accepted_tool_results
        state.accepted_executor_context = candidate.accepted_executor_context
        state.in_flight = candidate.in_flight
        self._entries[id(state)] = _Entry(state, entry.resume_id, entry.expected,
            entry.withheld, entry.created_at, in_flight, digest)

    def expire(self, cutoff, live):
        """Use sealed lifecycle facts rather than attacker-controlled expiry fields."""
        stale = [entry for entry in self._entries.values()
                 if entry.created_at < cutoff and not entry.in_flight]
        for entry in stale:
            for call_id in entry.expected:
                if live.get(call_id) is entry.state:
                    live.pop(call_id, None)
            self.retire(entry.state)
        return len(stale)

    def retire(self, state):
        entry = self._entries.get(id(state))
        if entry is not None and entry.state is state:
            self._entries.pop(id(state))
            self._invalid.discard(id(state))
            return entry.expected
        return ()
