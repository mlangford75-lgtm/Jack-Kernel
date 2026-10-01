from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import os
import queue
import re
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Optional, Tuple


LOG = logging.getLogger("jack-kernel.phase6-ledger")

LEDGER_SCHEMA = "jack.authority.security.ledger.v1"
RECORD_VERSION = 1
DEFAULT_PROJECTION_QUEUE_CAPACITY = 256
MAX_PROJECTION_QUEUE_CAPACITY = 4096

_EXPECTED_SECURITY_OUTCOMES = frozenset(
    {"ALLOW", "DENY_AND_CONTINUE", "REQUIRE_USER_DECISION", "HARD_INTERRUPT"}
)
_EXPECTED_GATE_BOUNDARIES = frozenset(
    {
        "tool_call",
        "tool_release_batch",
        "executor_admission",
        "overlap_admission",
        "evidence_fragment",
        "consequence",
    }
)
_EXPECTED_GATE_CONTAINMENT = frozenset(
    {
        "none",
        "tool_call",
        "tool_batch",
        "executor_admission",
        "overlap_admission",
        "evidence_fragment",
        "consequence",
    }
)
_CANARY_TIERS = frozenset({"A", "B", "C"})
_SAFE_CANARY_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9._-]+")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class LedgerEventType(str, Enum):
    REPRESENTED_PATH_DECISION = "REPRESENTED_PATH_DECISION"
    EXECUTOR_IDENTITY_DECISION = "EXECUTOR_IDENTITY_DECISION"
    CANARY_MATCH = "CANARY_MATCH"
    RESERVED_EVIDENCE_NAMESPACE_BLOCKED = "RESERVED_EVIDENCE_NAMESPACE_BLOCKED"


class LedgerAuthorityFrozen(RuntimeError):
    """Phase-6 ledger advancement is frozen; underlying Jack authority is separate."""


@dataclass(frozen=True)
class RepresentedPathDecisionPayload:
    deterministic: bool
    never_match: bool
    workspace_configured: bool
    inside_workspace: Optional[bool]
    invalid: bool
    deferred_to_executor: bool
    outcome: str
    containment_scope: str


@dataclass(frozen=True)
class ExecutorIdentityDecisionPayload:
    runtime_matches: bool
    lane_matches: bool
    outcome: str
    containment_scope: str


@dataclass(frozen=True)
class CanaryMatchPayload:
    canary_id: str
    tier: str


@dataclass(frozen=True)
class ReservedEvidenceNamespaceBlockedPayload:
    """Closed payload. Event identity itself is the authoritative fact."""


@dataclass(frozen=True)
class LedgerHead:
    sequence: int
    record_digest: Optional[str]


@dataclass(frozen=True)
class AuthorityRecord:
    schema: str
    record_version: int
    ledger_instance_id: str
    sequence: int
    runtime_id: str
    lane_id: str
    event_type: str
    producer_code: str
    occurred_at_utc: str
    task_id: Optional[str]
    run_id: Optional[str]
    run_epoch: Optional[int]
    boundary: str
    outcome: str
    containment_scope: str
    fact_type: str
    payload: Mapping[str, Any]
    previous_record_digest: Optional[str]
    record_digest: str


@dataclass(frozen=True)
class ProjectionStatus:
    active_sequence: int
    active_digest: Optional[str]
    last_projected_sequence: int
    last_projected_digest: Optional[str]
    projection_complete: bool
    complete_through_sequence: int
    first_lost_sequence: Optional[int]
    last_lost_sequence: Optional[int]
    lost_projection_count: int
    projection_metadata_degraded: bool
    queued_records: int
    queue_capacity: int


_ACTIVE_LEDGER: contextvars.ContextVar[Optional["AuthorityLedger"]] = contextvars.ContextVar(
    "jack_phase6_active_ledger",
    default=None,
)
_FILTER_HOOK_LOCK = threading.Lock()


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw)


def _require_bool(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be bool")
    return value


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest_record_material(material: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(material)).hexdigest()


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe_component(value: str, fallback: str) -> str:
    cleaned = _SAFE_COMPONENT.sub("-", str(value or "").strip()).strip("-._")
    return (cleaned or fallback)[:128]


def _queue_capacity_from_environment() -> int:
    raw = str(os.getenv("JACK_AUTHORITY_LEDGER_QUEUE_CAPACITY", "") or "").strip()
    if not raw:
        return DEFAULT_PROJECTION_QUEUE_CAPACITY
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise RuntimeError("JACK_AUTHORITY_LEDGER_QUEUE_CAPACITY must be an integer") from exc
    if parsed < 1 or parsed > MAX_PROJECTION_QUEUE_CAPACITY:
        raise RuntimeError(
            f"JACK_AUTHORITY_LEDGER_QUEUE_CAPACITY must be between 1 and {MAX_PROJECTION_QUEUE_CAPACITY}"
        )
    return parsed


def _projection_root(jk: Any) -> Path:
    explicit = str(os.getenv("JACK_AUTHORITY_LEDGER_DIR", "") or "").strip()
    if explicit:
        return Path(explicit).expanduser()

    cfg = getattr(jk, "CFG", None)
    registry_dir = str(getattr(cfg, "runtime_registry_dir", "") or "").strip()
    if registry_dir:
        return Path(registry_dir).expanduser().parent / "authority-ledger"

    return Path.home() / ".jack-kernel" / "authority-ledger"


def current_ledger() -> Optional["AuthorityLedger"]:
    return _ACTIVE_LEDGER.get()


@contextmanager
def live_ledger_scope(ledger: "AuthorityLedger") -> Iterator[None]:
    token = _ACTIVE_LEDGER.set(ledger)
    try:
        yield
    finally:
        _ACTIVE_LEDGER.reset(token)


class AuthorityLedger:
    """One process-local authoritative Phase-6 chain plus fail-soft disk projection.

    The in-memory head is the only active Phase-6 authority state. Durable files are
    forensic projections and are never promoted into active authority on restart.

    SHA-256 predecessor chaining proves internal chain consistency under this
    Phase-6 trust model. It is not hostile in-process tamper resistance or
    cryptographic authenticity against an actor able to rewrite records and the
    projected head. Later integrity phases own those stronger properties.
    """

    def __init__(
        self,
        *,
        runtime_id: str,
        lane_id: str,
        projection_root: Path,
        queue_capacity: int,
        ledger_instance_id: Optional[str] = None,
    ) -> None:
        self.runtime_id = str(runtime_id or "").strip()
        self.lane_id = str(lane_id or "").strip()
        if not self.runtime_id:
            raise ValueError("runtime_id must not be empty")
        if not self.lane_id:
            raise ValueError("lane_id must not be empty")
        if queue_capacity < 1 or queue_capacity > MAX_PROJECTION_QUEUE_CAPACITY:
            raise ValueError("queue_capacity is outside Phase-6 bounds")

        self.ledger_instance_id = str(ledger_instance_id or uuid.uuid4())
        self.projection_root = Path(projection_root)
        self.queue_capacity = int(queue_capacity)

        self._authority_lock = threading.Lock()
        self._head = LedgerHead(sequence=0, record_digest=None)
        self._head_guard = self._head_guard_digest(self._head)
        self._authority_frozen = False
        self._authority_frozen_reason: Optional[str] = None

        self._projection_queue: queue.Queue[Optional[AuthorityRecord]] = queue.Queue(
            maxsize=self.queue_capacity
        )
        self._durability_lock = threading.Lock()
        self._writer_start_lock = threading.Lock()
        self._writer: Optional[threading.Thread] = None
        self._closed = False

        self._last_projected_sequence = 0
        self._last_projected_digest: Optional[str] = None
        self._projection_complete = True
        self._complete_through_sequence = 0
        self._first_lost_sequence: Optional[int] = None
        self._last_lost_sequence: Optional[int] = None
        self._lost_projection_count = 0
        self._projection_metadata_degraded = False

    @property
    def instance_dir(self) -> Path:
        return (
            self.projection_root
            / _safe_component(self.runtime_id, "runtime")
            / _safe_component(self.lane_id, "lane")
            / _safe_component(self.ledger_instance_id, "instance")
        )

    @property
    def records_dir(self) -> Path:
        return self.instance_dir / "records"

    @property
    def projection_head_path(self) -> Path:
        return self.instance_dir / "projection_head.json"

    @property
    def authority_frozen(self) -> bool:
        with self._authority_lock:
            return self._authority_frozen

    @property
    def authority_frozen_reason(self) -> Optional[str]:
        with self._authority_lock:
            return self._authority_frozen_reason

    @property
    def active_head(self) -> LedgerHead:
        with self._authority_lock:
            return self._head

    def _head_guard_digest(self, head: LedgerHead) -> str:
        material = {
            "ledger_instance_id": self.ledger_instance_id,
            "sequence": head.sequence,
            "record_digest": head.record_digest,
            "guard_domain": "jack.phase6.active-head.v1",
        }
        return _digest_record_material(material)

    def _freeze_locked(self, reason: str) -> None:
        self._authority_frozen = True
        if self._authority_frozen_reason is None:
            self._authority_frozen_reason = str(reason or "ledger authority state invalid")

    def freeze_authority(self, reason: str) -> None:
        with self._authority_lock:
            self._freeze_locked(reason)

    def _validate_head_locked(self) -> None:
        head = self._head
        structurally_valid = (
            isinstance(head, LedgerHead)
            and isinstance(head.sequence, int)
            and head.sequence >= 0
            and (
                (head.sequence == 0 and head.record_digest is None)
                or (
                    head.sequence > 0
                    and isinstance(head.record_digest, str)
                    and _DIGEST_RE.fullmatch(head.record_digest) is not None
                )
            )
        )
        guard_valid = structurally_valid and self._head_guard == self._head_guard_digest(head)
        if not guard_valid:
            self._freeze_locked("active ledger head failed process-local consistency validation")
            raise LedgerAuthorityFrozen(self._authority_frozen_reason or "ledger authority frozen")

    def _record_material(
        self,
        *,
        sequence: int,
        previous_record_digest: Optional[str],
        event_type: LedgerEventType,
        producer_code: str,
        boundary: str,
        outcome: str,
        containment_scope: str,
        fact_type: str,
        payload: Mapping[str, Any],
    ) -> Dict[str, Any]:
        return {
            "schema": LEDGER_SCHEMA,
            "record_version": RECORD_VERSION,
            "ledger_instance_id": self.ledger_instance_id,
            "sequence": sequence,
            "runtime_id": self.runtime_id,
            "lane_id": self.lane_id,
            "event_type": event_type.value,
            "producer_code": producer_code,
            "occurred_at_utc": _utc_now(),
            "task_id": None,
            "run_id": None,
            "run_epoch": None,
            "boundary": boundary,
            "outcome": outcome,
            "containment_scope": containment_scope,
            "fact_type": fact_type,
            "payload": dict(payload),
            "previous_record_digest": previous_record_digest,
        }

    def _advance(
        self,
        *,
        event_type: LedgerEventType,
        producer_code: str,
        boundary: str,
        outcome: str,
        containment_scope: str,
        fact_type: str,
        payload: Mapping[str, Any],
    ) -> AuthorityRecord:
        # No filesystem operation is permitted while this authority lock is held.
        with self._authority_lock:
            if self._authority_frozen:
                raise LedgerAuthorityFrozen(self._authority_frozen_reason or "ledger authority frozen")
            self._validate_head_locked()

            previous = self._head
            sequence = previous.sequence + 1
            material = self._record_material(
                sequence=sequence,
                previous_record_digest=previous.record_digest,
                event_type=event_type,
                producer_code=producer_code,
                boundary=boundary,
                outcome=outcome,
                containment_scope=containment_scope,
                fact_type=fact_type,
                payload=payload,
            )
            digest = _digest_record_material(material)
            record = AuthorityRecord(**material, record_digest=digest)
            self._head = LedgerHead(sequence=sequence, record_digest=digest)
            self._head_guard = self._head_guard_digest(self._head)

            # Queue insertion is an in-memory part of the serialized authority
            # transition so concurrent writers cannot reorder sequence N/N+1.
            # It performs no filesystem I/O. Writer startup remains outside.
            projection_queued = self._enqueue_projection_locked(record)

        if projection_queued:
            self._ensure_writer()
        return record

    def record_represented_path_decision(
        self,
        *,
        deterministic: bool,
        never_match: bool,
        workspace_configured: bool,
        inside_workspace: Optional[bool],
        invalid: bool,
        deferred_to_executor: bool,
        outcome: Any,
        containment_scope: Any,
        boundary: Any,
    ) -> AuthorityRecord:
        outcome_value = _enum_value(outcome)
        scope_value = _enum_value(containment_scope)
        boundary_value = _enum_value(boundary)
        if outcome_value not in _EXPECTED_SECURITY_OUTCOMES:
            raise ValueError("unsupported security outcome for represented-path ledger record")
        if scope_value not in _EXPECTED_GATE_CONTAINMENT:
            raise ValueError("unsupported containment scope for represented-path ledger record")
        if boundary_value not in _EXPECTED_GATE_BOUNDARIES:
            raise ValueError("unsupported consequence boundary for represented-path ledger record")
        if inside_workspace is not None and not isinstance(inside_workspace, bool):
            raise TypeError("inside_workspace must be bool or None")

        payload = RepresentedPathDecisionPayload(
            deterministic=_require_bool("deterministic", deterministic),
            never_match=_require_bool("never_match", never_match),
            workspace_configured=_require_bool("workspace_configured", workspace_configured),
            inside_workspace=inside_workspace,
            invalid=_require_bool("invalid", invalid),
            deferred_to_executor=_require_bool("deferred_to_executor", deferred_to_executor),
            outcome=outcome_value,
            containment_scope=scope_value,
        )
        return self._advance(
            event_type=LedgerEventType.REPRESENTED_PATH_DECISION,
            producer_code="phase5.represented_path_gate",
            boundary=boundary_value,
            outcome=outcome_value,
            containment_scope=scope_value,
            fact_type="RepresentedPathAuthorityFacts",
            payload=asdict(payload),
        )

    def record_executor_identity_decision(
        self,
        *,
        runtime_matches: bool,
        lane_matches: bool,
        outcome: Any,
        containment_scope: Any,
    ) -> AuthorityRecord:
        outcome_value = _enum_value(outcome)
        scope_value = _enum_value(containment_scope)
        if outcome_value not in _EXPECTED_SECURITY_OUTCOMES:
            raise ValueError("unsupported security outcome for executor-identity ledger record")
        if scope_value not in _EXPECTED_GATE_CONTAINMENT:
            raise ValueError("unsupported containment scope for executor-identity ledger record")
        payload = ExecutorIdentityDecisionPayload(
            runtime_matches=_require_bool("runtime_matches", runtime_matches),
            lane_matches=_require_bool("lane_matches", lane_matches),
            outcome=outcome_value,
            containment_scope=scope_value,
        )
        return self._advance(
            event_type=LedgerEventType.EXECUTOR_IDENTITY_DECISION,
            producer_code="phase5.executor_identity_gate",
            boundary="executor_admission",
            outcome=outcome_value,
            containment_scope=scope_value,
            fact_type="ExecutorAdmissionIdentityFact",
            payload=asdict(payload),
        )

    def record_canary_match(self, *, canary_id: str, tier: Any) -> AuthorityRecord:
        safe_id = str(canary_id or "")
        tier_value = _enum_value(tier)
        if _SAFE_CANARY_ID.fullmatch(safe_id) is None:
            raise ValueError("canary_id is not safe Phase-6 metadata")
        if tier_value not in _CANARY_TIERS:
            raise ValueError("unsupported Canary tier")
        payload = CanaryMatchPayload(canary_id=safe_id, tier=tier_value)
        return self._advance(
            event_type=LedgerEventType.CANARY_MATCH,
            producer_code="streaming_irq.canary",
            boundary="model_output_release",
            outcome="HARD_INTERRUPT",
            containment_scope="model_output_release",
            fact_type="CanaryMatch",
            payload=asdict(payload),
        )

    def record_reserved_evidence_namespace_block(self) -> AuthorityRecord:
        payload = ReservedEvidenceNamespaceBlockedPayload()
        return self._advance(
            event_type=LedgerEventType.RESERVED_EVIDENCE_NAMESPACE_BLOCKED,
            producer_code="evidence_guard.reserved_namespace",
            boundary="model_output_release",
            outcome="DENY_AND_CONTINUE",
            containment_scope="evidence_fragment",
            fact_type="ReservedEvidenceNamespaceFact",
            payload=asdict(payload),
        )

    def _ensure_writer(self) -> None:
        if self._closed:
            return
        with self._writer_start_lock:
            if self._writer is not None and self._writer.is_alive():
                return
            self._writer = threading.Thread(
                target=self._writer_loop,
                name=f"jack-phase6-ledger-{_safe_component(self.ledger_instance_id, 'instance')[:24]}",
                daemon=True,
            )
            self._writer.start()

    def _enqueue_projection_locked(self, record: AuthorityRecord) -> bool:
        """Queue one immutable projection while the authority transition is serialized.

        This method performs memory-only bounded queue operations. It never starts
        the writer and never performs filesystem I/O.
        """
        if self._closed:
            self._mark_projection_lost(record.sequence)
            return False
        try:
            self._projection_queue.put_nowait(record)
        except queue.Full:
            self._mark_projection_lost(record.sequence)
            return False
        return True

    def _mark_projection_lost(self, sequence: int) -> None:
        with self._durability_lock:
            self._projection_complete = False
            if self._first_lost_sequence is None:
                self._first_lost_sequence = int(sequence)
                self._complete_through_sequence = min(
                    self._complete_through_sequence,
                    max(0, int(sequence) - 1),
                )
            self._last_lost_sequence = int(sequence)
            self._lost_projection_count += 1

    def _writer_loop(self) -> None:
        while True:
            item = self._projection_queue.get()
            try:
                if item is None:
                    return
                self._project_one(item)
            finally:
                self._projection_queue.task_done()

    def _atomic_write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            with temp.open("wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        except Exception:
            try:
                temp.unlink()
            except OSError:
                pass
            raise

    def _projection_head_document(self) -> Dict[str, Any]:
        with self._durability_lock:
            return {
                "schema": "jack.authority.security.ledger.projection-head.v1",
                "ledger_instance_id": self.ledger_instance_id,
                "runtime_id": self.runtime_id,
                "lane_id": self.lane_id,
                "last_projected_sequence": self._last_projected_sequence,
                "last_projected_digest": self._last_projected_digest,
                "projection_complete": self._projection_complete,
                "complete_through_sequence": self._complete_through_sequence,
                "first_lost_sequence": self._first_lost_sequence,
                "last_lost_sequence": self._last_lost_sequence,
                "lost_projection_count": self._lost_projection_count,
                "projection_metadata_degraded": self._projection_metadata_degraded,
            }

    def _project_one(self, record: AuthorityRecord) -> None:
        record_data = asdict(record)
        file_name = f"{record.sequence:012d}_{record.record_digest}.json"
        target = self.records_dir / file_name
        encoded = _canonical_bytes(record_data) + b"\n"

        try:
            self._atomic_write(target, encoded)
        except Exception:
            self._mark_projection_lost(record.sequence)
            LOG.exception("Phase-6 authority-ledger record projection failed; Jack authority remains active")
            # A record-file failure may still permit projection metadata to be
            # written. Attempt it so durable history can truthfully advertise
            # the known gap when the storage failure is partial rather than total.
            self._write_projection_head_best_effort()
            return

        with self._durability_lock:
            self._last_projected_sequence = record.sequence
            self._last_projected_digest = record.record_digest
            if self._first_lost_sequence is None:
                self._complete_through_sequence = record.sequence
            elif (
                record.sequence < self._first_lost_sequence
                and record.sequence == self._complete_through_sequence + 1
            ):
                self._complete_through_sequence = record.sequence
            # Once any record is lost, completeness stays false for this process projection.
            self._projection_complete = self._first_lost_sequence is None
            # The head document being attempted below describes the result of this
            # attempt; a successful replacement clears prior metadata degradation.
            self._projection_metadata_degraded = False

        self._write_projection_head_best_effort()

    def _write_projection_head_best_effort(self) -> None:
        try:
            head_doc = self._projection_head_document()
            self._atomic_write(
                self.projection_head_path,
                json.dumps(
                    head_doc,
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                    allow_nan=False,
                ).encode("utf-8") + b"\n",
            )
            with self._durability_lock:
                self._projection_metadata_degraded = False
        except Exception:
            with self._durability_lock:
                self._projection_metadata_degraded = True
            LOG.exception(
                "Phase-6 projection-head update failed; projected records remain forensic and active authority is unchanged"
            )

    def projection_status(self) -> ProjectionStatus:
        head = self.active_head
        with self._durability_lock:
            return ProjectionStatus(
                active_sequence=head.sequence,
                active_digest=head.record_digest,
                last_projected_sequence=self._last_projected_sequence,
                last_projected_digest=self._last_projected_digest,
                projection_complete=self._projection_complete,
                complete_through_sequence=self._complete_through_sequence,
                first_lost_sequence=self._first_lost_sequence,
                last_lost_sequence=self._last_lost_sequence,
                lost_projection_count=self._lost_projection_count,
                projection_metadata_degraded=self._projection_metadata_degraded,
                queued_records=self._projection_queue.qsize(),
                queue_capacity=self.queue_capacity,
            )

    def wait_for_projection(self, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + max(0.0, float(timeout))
        while time.monotonic() <= deadline:
            if self._projection_queue.unfinished_tasks == 0:
                return True
            time.sleep(0.01)
        return self._projection_queue.unfinished_tasks == 0

    def close(self, timeout: float = 5.0) -> None:
        self.wait_for_projection(timeout=timeout)
        with self._writer_start_lock:
            self._closed = True
            writer = self._writer
            if writer is None or not writer.is_alive():
                return
            try:
                self._projection_queue.put_nowait(None)
            except queue.Full:
                return
        writer.join(timeout=max(0.0, float(timeout)))


def _safe_record(ledger: AuthorityLedger, method_name: str, /, **kwargs: Any) -> bool:
    """Keep Phase-6 failure contained to Phase 6, never rewrite predecessor authority."""
    try:
        method = getattr(ledger, method_name)
        method(**kwargs)
        return True
    except LedgerAuthorityFrozen:
        return False
    except Exception as exc:
        # A ledger implementation failure freezes only further ledger advancement.
        # Existing Gate/evidence decisions remain authoritative and continue.
        try:
            ledger.freeze_authority(f"Phase-6 ledger recording failure: {type(exc).__name__}")
        except Exception:
            pass
        LOG.exception("Phase-6 ledger recording failed; ledger advancement frozen without changing predecessor authority")
        return False


def record_represented_path_decision_failsoft(
    *,
    deterministic: bool,
    never_match: bool,
    workspace_configured: bool,
    inside_workspace: Optional[bool],
    invalid: bool,
    deferred_to_executor: bool,
    outcome: Any,
    containment_scope: Any,
    boundary: Any,
) -> bool:
    ledger = current_ledger()
    if ledger is None:
        return False
    return _safe_record(
        ledger,
        "record_represented_path_decision",
        deterministic=deterministic,
        never_match=never_match,
        workspace_configured=workspace_configured,
        inside_workspace=inside_workspace,
        invalid=invalid,
        deferred_to_executor=deferred_to_executor,
        outcome=outcome,
        containment_scope=containment_scope,
        boundary=boundary,
    )


def record_executor_identity_decision_failsoft(
    ledger: AuthorityLedger,
    *,
    runtime_matches: bool,
    lane_matches: bool,
    outcome: Any,
    containment_scope: Any,
) -> bool:
    return _safe_record(
        ledger,
        "record_executor_identity_decision",
        runtime_matches=runtime_matches,
        lane_matches=lane_matches,
        outcome=outcome,
        containment_scope=containment_scope,
    )


def _record_canary_failsoft(ledger: AuthorityLedger, match: Any) -> None:
    canary_id = str(getattr(match, "canary_id", "") or "")
    tier = getattr(match, "tier", "")
    _safe_record(ledger, "record_canary_match", canary_id=canary_id, tier=tier)


def _record_reserved_block_from_filter() -> None:
    ledger = current_ledger()
    if ledger is None:
        return
    _safe_record(ledger, "record_reserved_evidence_namespace_block")


def _install_reserved_filter_hook() -> None:
    import jack_evidence_guard as guard

    global _FILTER_HOOK_LOCK
    with _FILTER_HOOK_LOCK:
        current = guard.ReservedEvidenceMarkerFilter
        if getattr(current, "_jack_phase6_ledger_filter", False):
            return

        original = current

        class LedgerAwareReservedEvidenceMarkerFilter(original):
            _jack_phase6_ledger_filter = True
            _jack_phase6_original_filter = original

            @classmethod
            def _classify_candidate(cls, fragment: str, *, final: bool) -> Tuple[str, int]:
                status, consumed = super()._classify_candidate(fragment, final=final)
                if status == "block":
                    _record_reserved_block_from_filter()
                return status, consumed

        guard.ReservedEvidenceMarkerFilter = LedgerAwareReservedEvidenceMarkerFilter


def _install_evidence_release_hooks(jk: Any, ledger: AuthorityLedger) -> None:
    import jack_evidence_guard as guard

    _install_reserved_filter_hook()

    kernel = getattr(jk, "KERNEL", None)
    if kernel is None:
        raise RuntimeError("Jack KERNEL instance is unavailable for Phase-6 evidence integration")

    current_run = getattr(kernel, "run", None)
    current_stream = getattr(kernel, "stream", None)
    if not callable(current_run) or not callable(current_stream):
        raise RuntimeError("Jack KERNEL release seams are unavailable for Phase-6 evidence integration")

    if not getattr(current_run, "_jack_phase6_authority_ledger", False):
        original_run = current_run

        @wraps(original_run)
        async def ledger_run(*args: Any, **kwargs: Any):
            with live_ledger_scope(ledger):
                try:
                    return await original_run(*args, **kwargs)
                except guard.StreamingIRQCanaryInterrupt as exc:
                    _record_canary_failsoft(ledger, exc.match)
                    raise

        ledger_run._jack_phase6_authority_ledger = True
        ledger_run._jack_phase6_original = original_run
        kernel.run = ledger_run

    if not getattr(current_stream, "_jack_phase6_authority_ledger", False):
        original_stream = current_stream

        @wraps(original_stream)
        async def ledger_stream(*args: Any, **kwargs: Any):
            with live_ledger_scope(ledger):
                try:
                    async for chunk in original_stream(*args, **kwargs):
                        yield chunk
                except guard.StreamingIRQCanaryInterrupt as exc:
                    _record_canary_failsoft(ledger, exc.match)
                    raise

        ledger_stream._jack_phase6_authority_ledger = True
        ledger_stream._jack_phase6_original = original_stream
        kernel.stream = ledger_stream


def install(jk: Any) -> AuthorityLedger:
    """Install one process-local Phase-6 ledger through the Kernel-owned Gate seam."""
    existing = getattr(jk, "_JACK_AUTHORITY_LEDGER", None)
    if getattr(jk, "_JACK_AUTHORITY_LEDGER_INSTALLED", False):
        if not isinstance(existing, AuthorityLedger):
            raise RuntimeError("Phase-6 installation marker exists without an AuthorityLedger")
        return existing

    runtime_id = str(getattr(jk, "RUNTIME_ID", "") or "").strip()
    lane_id = str(getattr(jk, "LANE_ID", "") or "").strip()
    if not runtime_id:
        raise RuntimeError("Jack runtime identity is unavailable for Phase-6 ledger")
    if not lane_id:
        raise RuntimeError("Jack lane identity is unavailable for Phase-6 ledger")

    if not getattr(jk, "_JACK_EVIDENCE_PROVENANCE_GUARD_INSTALLED", False):
        raise RuntimeError(
            "Phase-6 ledger requires the predecessor evidence/Canary guard to be installed first"
        )

    ledger = AuthorityLedger(
        runtime_id=runtime_id,
        lane_id=lane_id,
        projection_root=_projection_root(jk),
        queue_capacity=_queue_capacity_from_environment(),
    )

    # Evidence hooks are installed only after predecessor evidence security is
    # already active; jack_consequence_gate.install() is invoked by Jack's shared
    # bundled-extension convergence seam after that predecessor installation.
    _install_evidence_release_hooks(jk, ledger)

    jk._JACK_AUTHORITY_LEDGER = ledger
    jk._JACK_AUTHORITY_LEDGER_INSTALLED = True
    jk.AuthorityLedger = AuthorityLedger
    jk.LedgerAuthorityFrozen = LedgerAuthorityFrozen
    jk.LedgerEventType = LedgerEventType
    return ledger
