"""Universal, passive executor-attested tool lifecycle observation.

No tool dispatch, timeout, cancellation, recovery, or model-facing side effects.
Neither silent execution nor missing events are interpreted as failure.
"""
from __future__ import annotations

from collections import OrderedDict
from threading import Lock
import time
from typing import Any, Callable, Dict, Optional, Tuple

EVENTS = frozenset({"START", "PROGRESS", "END"})
OUTCOMES = frozenset({"SUCCESS_REPORTED", "ERROR_REPORTED", "UNKNOWN"})
CAPABILITIES = ("start_end", "progress", "bounded_return", "cancellation", "detached_jobs")


class ToolLifecycleObserver:
    """Bounded, out-of-band observation for any cooperating agent adapter."""

    def __init__(self, *, max_records: int = 512, clock: Callable[[], float] = time.monotonic):
        if max_records < 1:
            raise ValueError("max_records must be positive")
        self._clock = clock
        self._max_records = max_records
        self._lock = Lock()
        self._records: OrderedDict[Tuple[str, str, str], Dict[str, Any]] = OrderedDict()
        self._capabilities: Dict[str, Dict[str, bool]] = {}
        self._evicted_records = 0
        self._evicted_unfinished = 0

    @staticmethod
    def _identifier(value: Any, name: str) -> str:
        if not isinstance(value, str) or not (1 <= len(value) <= 200):
            raise ValueError(f"{name} must be a nonempty string of at most 200 characters")
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError(f"{name} contains invalid characters")
        return value

    def _make_room(self) -> None:
        if len(self._records) < self._max_records:
            return
        key = next((k for k, v in self._records.items() if v["closed"]), None)
        if key is None:
            key = next(iter(self._records))
            self._evicted_unfinished += 1
        self._records.pop(key)
        self._evicted_records += 1

    def observe(
        self, *, adapter: str, owner: str, call_id: str,
        event: str, outcome: Optional[str] = None,
        capabilities: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        adapter = self._identifier(adapter, "adapter")
        owner = self._identifier(owner, "owner")
        call_id = self._identifier(call_id, "call_id")
        if event not in EVENTS:
            raise ValueError("unsupported lifecycle event")
        if outcome is not None and (event != "END" or outcome not in OUTCOMES):
            raise ValueError("outcome is only valid on END")
        if capabilities is not None:
            if event != "START" or not isinstance(capabilities, dict):
                raise ValueError("adapter capabilities must accompany START")
            if set(capabilities) - set(CAPABILITIES) or any(type(v) is not bool for v in capabilities.values()):
                raise ValueError("invalid adapter capability declaration")
        now = self._clock()
        key = (adapter, owner, call_id)
        with self._lock:
            if capabilities is not None:
                self._capabilities[adapter] = {k: capabilities.get(k, False) for k in CAPABILITIES}
            record = self._records.get(key)
            if record is None:
                self._make_room()
                record = {
                    "started_at": now if event == "START" else None,
                    "last_report_at": now,
                    "progress_reports": 0,
                    "closed": False,
                    "terminal_outcome": None,
                    "unmatched": event != "START",
                }
                self._records[key] = record
            if record["closed"]:
                return {"accepted": True, "state": "TERMINAL_ALREADY_RECORDED"}
            if event == "START":
                if record["started_at"] is None:
                    record["unmatched"] = True
            elif event == "PROGRESS":
                record["progress_reports"] += 1
                record["last_report_at"] = now
            elif event == "END":
                record["closed"] = True
                record["last_report_at"] = now
                record["terminal_outcome"] = outcome or "UNKNOWN"
            state = ("END_REPORTED" if record["closed"] else
                     "START_REPORTED" if record["started_at"] is not None else "UNMATCHED_EVENT")
            return {"accepted": True, "state": state}

    def snapshot(self) -> Dict[str, Any]:
        now = self._clock()
        with self._lock:
            unfinished = [v for v in self._records.values() if not v["closed"]]
            start_ages = [max(0.0, now - v["started_at"])
                          for v in unfinished if v["started_at"] is not None]
            outcomes = {name: 0 for name in sorted(OUTCOMES)}
            for record in self._records.values():
                if record["closed"]:
                    outcomes[record["terminal_outcome"]] += 1
            return {
                "observation_only": True,
                "active_unconfirmed": len(unfinished),
                "longest_unconfirmed_seconds": round(max(start_ages), 2) if start_ages else None,
                "unmatched_records": sum(1 for v in self._records.values() if v["unmatched"]),
                "retained_records": len(self._records),
                "evicted_records": self._evicted_records,
                "evicted_unfinished": self._evicted_unfinished,
                "complete_coverage": self._evicted_records == 0,
                "terminal_reports": outcomes,
                "reported_adapter_capabilities": {k: dict(v) for k, v in self._capabilities.items()},
            }
