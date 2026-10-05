from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple


SOURCE_BASELINE_SCHEMA = "jack.source-authority.baseline.v1"
SOURCE_BASELINE_VERSION = 1
_COMPONENT_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class SourceAuthorityState(str, Enum):
    INITIALIZING = "INITIALIZING"
    ACTIVE = "ACTIVE"
    SUSPENDED_UNVERIFIED = "SUSPENDED_UNVERIFIED"
    INVALIDATED = "INVALIDATED"


class SourceAuthorityError(RuntimeError):
    """Base Phase-8 source-authority error."""


class SourceBaselineCreationError(SourceAuthorityError):
    """The serving runtime could not establish its initial exact source identity."""


class SourceComponentSetSealed(SourceAuthorityError):
    """An authority-bearing source component attempted to join after activation."""


class SourceAuthorityUnavailable(SourceAuthorityError):
    """Kernel authority is not currently available from the source baseline."""


class SourceAuthorityInvalidated(SourceAuthorityUnavailable):
    """Confirmed source drift terminally invalidated this runtime's authority."""


class SourceMeasurementUnavailable(SourceAuthorityError):
    """Current source identity could not be deterministically measured."""


class _SourceComponentMissing(SourceAuthorityError):
    pass


class _SourceComponentKindChanged(SourceAuthorityError):
    pass


@dataclass(frozen=True)
class SourceComponentBaseline:
    component_id: str
    canonical_path: str
    expected_kind: str
    sha256: str


@dataclass(frozen=True)
class RuntimeSourceBaseline:
    schema: str
    version: int
    baseline_instance_id: str
    runtime_id: str
    lane_id: str
    components: Tuple[SourceComponentBaseline, ...]
    aggregate_sha256: str

    @property
    def component_ids(self) -> Tuple[str, ...]:
        return tuple(item.component_id for item in self.components)


@dataclass(frozen=True)
class SourceVerificationResult:
    state: SourceAuthorityState
    baseline_instance_id: str
    verified: bool
    mismatched_component_ids: Tuple[str, ...] = ()
    unavailable_component_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class _MeasuredSource:
    canonical_path: str
    sha256: str


def _sha256_stream(handle: Any) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = handle.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def _measure_regular_file(path: Path) -> _MeasuredSource:
    """Measure one source file from exact bytes and explicit object kind.

    Missing paths and deterministic file-kind transitions are source mismatches.
    Other OS read failures are epistemically different: Jack cannot establish
    current identity and Phase 8 must suspend rather than falsely claim drift.
    Metadata such as mtime and size is never used as source identity.
    """

    raw = Path(path).expanduser()
    try:
        canonical = raw.resolve(strict=True)
    except FileNotFoundError as exc:
        raise _SourceComponentMissing(str(raw)) from exc
    except OSError as exc:
        raise SourceMeasurementUnavailable(type(exc).__name__) from exc

    # Classify path kind before opening. On Windows, opening a directory can
    # surface as PermissionError rather than IsADirectoryError; object kind is
    # nevertheless a deterministic fact and must not be mislabeled unavailable.
    try:
        path_mode = canonical.stat().st_mode
    except FileNotFoundError as exc:
        raise _SourceComponentMissing(str(canonical)) from exc
    except OSError as exc:
        raise SourceMeasurementUnavailable(type(exc).__name__) from exc
    if not stat.S_ISREG(path_mode):
        raise _SourceComponentKindChanged(str(canonical))

    try:
        with canonical.open("rb") as handle:
            handle_mode = os.fstat(handle.fileno()).st_mode
            if not stat.S_ISREG(handle_mode):
                raise _SourceComponentKindChanged(str(canonical))
            digest = _sha256_stream(handle)
    except FileNotFoundError as exc:
        raise _SourceComponentMissing(str(canonical)) from exc
    except _SourceComponentKindChanged:
        raise
    except OSError as exc:
        raise SourceMeasurementUnavailable(type(exc).__name__) from exc

    return _MeasuredSource(
        canonical_path=str(canonical),
        sha256=digest,
    )


def _baseline_digest(
    runtime_id: str,
    lane_id: str,
    components: Tuple[SourceComponentBaseline, ...],
) -> str:
    material = {
        "schema": SOURCE_BASELINE_SCHEMA,
        "version": SOURCE_BASELINE_VERSION,
        "runtime_id": runtime_id,
        "lane_id": lane_id,
        "components": [
            {
                "component_id": item.component_id,
                "canonical_path": item.canonical_path,
                "expected_kind": item.expected_kind,
                "sha256": item.sha256,
            }
            for item in components
        ],
    }
    encoded = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class RuntimeSourceAuthority:
    """Process-local Phase-8 source authority and immutable active baseline.

    The lock is the synchronization boundary shared by source-state transition
    and future final consequence/release admission. Callers must never hold an
    admission across model cognition; it is intentionally for the narrow final
    authority transition only.
    """

    def __init__(self, *, runtime_id: str, lane_id: str) -> None:
        self.runtime_id = str(runtime_id or "").strip()
        self.lane_id = str(lane_id or "").strip()
        if not self.runtime_id:
            raise ValueError("runtime_id must not be empty")
        if not self.lane_id:
            raise ValueError("lane_id must not be empty")

        self._lock = threading.RLock()
        self._state = SourceAuthorityState.INITIALIZING
        self._pending_components: Dict[str, Path] = {}
        self._baseline: Optional[RuntimeSourceBaseline] = None

    @property
    def state(self) -> SourceAuthorityState:
        with self._lock:
            return self._state

    @property
    def baseline(self) -> RuntimeSourceBaseline:
        with self._lock:
            if self._baseline is None:
                raise SourceBaselineCreationError("source baseline is not sealed")
            return self._baseline

    def register_component(self, component_id: str, path: Path) -> None:
        """Register authority source only while INITIALIZING."""

        cid = str(component_id or "").strip()
        if _COMPONENT_ID_RE.fullmatch(cid) is None:
            raise ValueError("invalid Phase-8 source component_id")
        candidate = Path(path).expanduser()

        with self._lock:
            if self._state is not SourceAuthorityState.INITIALIZING:
                raise SourceComponentSetSealed(
                    "Phase-8 protected source set is sealed; restart is required"
                )
            prior = self._pending_components.get(cid)
            if prior is not None:
                if prior != candidate:
                    raise SourceBaselineCreationError(
                        f"source component {cid!r} cannot be rebound"
                    )
                return
            self._pending_components[cid] = candidate

    def seal(self) -> RuntimeSourceBaseline:
        with self._lock:
            if self._state is not SourceAuthorityState.INITIALIZING:
                if self._baseline is None:
                    raise SourceBaselineCreationError("source baseline state is invalid")
                return self._baseline
            if not self._pending_components:
                raise SourceBaselineCreationError("protected source set is empty")

            measured = []
            seen_paths = set()
            try:
                for component_id in sorted(self._pending_components):
                    current = _measure_regular_file(
                        self._pending_components[component_id]
                    )
                    if current.canonical_path in seen_paths:
                        raise SourceBaselineCreationError(
                            "multiple source component identities resolve to one canonical path"
                        )
                    seen_paths.add(current.canonical_path)
                    measured.append(
                        SourceComponentBaseline(
                            component_id=component_id,
                            canonical_path=current.canonical_path,
                            expected_kind="regular_file",
                            sha256=current.sha256,
                        )
                    )
            except (_SourceComponentMissing, _SourceComponentKindChanged) as exc:
                raise SourceBaselineCreationError(
                    "protected source component is missing or not a regular file"
                ) from exc
            except SourceMeasurementUnavailable as exc:
                raise SourceBaselineCreationError(
                    "protected source identity could not be measured before activation"
                ) from exc

            components = tuple(measured)
            baseline = RuntimeSourceBaseline(
                schema=SOURCE_BASELINE_SCHEMA,
                version=SOURCE_BASELINE_VERSION,
                baseline_instance_id=str(uuid.uuid4()),
                runtime_id=self.runtime_id,
                lane_id=self.lane_id,
                components=components,
                aggregate_sha256=_baseline_digest(
                    self.runtime_id,
                    self.lane_id,
                    components,
                ),
            )
            self._baseline = baseline
            self._pending_components.clear()
            self._state = SourceAuthorityState.ACTIVE
            return baseline

    @contextmanager
    def admit(self) -> Iterator[RuntimeSourceBaseline]:
        """Serialize final authority admission against suspension/invalidation."""

        self._lock.acquire()
        try:
            if self._state is SourceAuthorityState.INVALIDATED:
                raise SourceAuthorityInvalidated(
                    "Phase-8 source authority is terminally invalidated"
                )
            if self._state is not SourceAuthorityState.ACTIVE:
                raise SourceAuthorityUnavailable(
                    "Phase-8 source authority is not currently verified"
                )
            if self._baseline is None:
                raise SourceAuthorityUnavailable("Phase-8 source baseline is unavailable")
            yield self._baseline
        finally:
            self._lock.release()

    def verify_now(self) -> SourceVerificationResult:
        """Perform one bounded deterministic verification against the baseline.

        This does not claim continuous historical attestation. A mismatch found
        here terminally invalidates this runtime. An inability to measure moves
        authority to SUSPENDED_UNVERIFIED until a later exact verification
        succeeds. INVALIDATED is terminal and cannot be repaired in place.
        """

        with self._lock:
            baseline = self._baseline
            if baseline is None:
                raise SourceBaselineCreationError("source baseline is not sealed")
            if self._state is SourceAuthorityState.INVALIDATED:
                return SourceVerificationResult(
                    state=self._state,
                    baseline_instance_id=baseline.baseline_instance_id,
                    verified=False,
                )

            mismatched = []
            unavailable = []
            for expected in baseline.components:
                try:
                    observed = _measure_regular_file(Path(expected.canonical_path))
                except (_SourceComponentMissing, _SourceComponentKindChanged):
                    mismatched.append(expected.component_id)
                    continue
                except SourceMeasurementUnavailable:
                    unavailable.append(expected.component_id)
                    continue

                if (
                    observed.canonical_path != expected.canonical_path
                    or observed.sha256 != expected.sha256
                ):
                    mismatched.append(expected.component_id)

            if mismatched:
                self._state = SourceAuthorityState.INVALIDATED
            elif unavailable:
                self._state = SourceAuthorityState.SUSPENDED_UNVERIFIED
            else:
                self._state = SourceAuthorityState.ACTIVE

            return SourceVerificationResult(
                state=self._state,
                baseline_instance_id=baseline.baseline_instance_id,
                verified=self._state is SourceAuthorityState.ACTIVE,
                mismatched_component_ids=tuple(sorted(mismatched)),
                unavailable_component_ids=tuple(sorted(unavailable)),
            )


_REQUIRED_AUTHORITY_MODULES: Tuple[Tuple[str, str], ...] = (
    ("jack_evidence_guard.py", "jack_evidence_guard"),
    ("jack_path_policy.py", "jack_path_policy"),
    ("jack_consequence_gate.py", "jack_consequence_gate"),
    ("jack_authority_ledger.py", "jack_authority_ledger"),
    ("jack_responses_compat.py", "jack_responses_compat"),
    ("jack_credential_guard.py", "jack_credential_guard"),
    ("jack_diagnostic_guard.py", "jack_diagnostic_guard"),
    ("jack_credential_resource_guard.py", "jack_credential_resource_guard"),
    ("jack_phase7_ledger.py", "jack_phase7_ledger"),
)

_REQUIRED_PREDECESSOR_MARKERS = (
    "_JACK_EVIDENCE_PROVENANCE_GUARD_INSTALLED",
    "_JACK_CONSEQUENCE_GATE_INSTALLED",
    "_JACK_AUTHORITY_LEDGER_INSTALLED",
    "_JACK_CREDENTIAL_GUARD_INSTALLED",
    "_JACK_DIAGNOSTIC_CREDENTIAL_DLP_INSTALLED",
    "_JACK_CREDENTIAL_RESOURCE_GUARD_INSTALLED",
    "_JACK_PHASE7_LEDGER_INSTALLED",
)


def _loaded_module_source(module_name: str) -> Path:
    module = sys.modules.get(module_name)
    path = getattr(module, "__file__", None) if module is not None else None
    if not path:
        raise SourceBaselineCreationError(
            f"required authority module {module_name!r} was not loaded before Phase-8 sealing"
        )
    return Path(path)


def _default_component_paths(
    jk: Any,
    *,
    launch_entrypoint_path: Optional[Path],
) -> Tuple[Tuple[str, Path], ...]:
    kernel_path = getattr(jk, "__file__", None)
    if not kernel_path:
        raise SourceBaselineCreationError("Jack Kernel source path is unavailable")

    items = [("jack_kernel.py", Path(kernel_path))]
    items.extend(
        (component_id, _loaded_module_source(module_name))
        for component_id, module_name in _REQUIRED_AUTHORITY_MODULES
    )
    items.append(("jack_source_drift_guard.py", Path(__file__)))
    if launch_entrypoint_path is not None:
        items.append(("jack_secure_entrypoint.py", Path(launch_entrypoint_path)))
    return tuple(items)


def install(
    jk: Any,
    *,
    launch_entrypoint_path: Optional[Path] = None,
) -> RuntimeSourceAuthority:
    """Seal one process-local Phase-8B active-source baseline exactly once."""

    requested = _default_component_paths(
        jk,
        launch_entrypoint_path=launch_entrypoint_path,
    )
    requested_ids = frozenset(component_id for component_id, _path in requested)

    existing = getattr(jk, "_JACK_SOURCE_AUTHORITY", None)
    if getattr(jk, "_JACK_SOURCE_AUTHORITY_INSTALLED", False):
        if not isinstance(existing, RuntimeSourceAuthority):
            raise RuntimeError("Phase-8 source-authority marker exists without valid state")
        if frozenset(existing.baseline.component_ids) != requested_ids:
            raise SourceComponentSetSealed(
                "Phase-8 protected source set is sealed; restart is required"
            )
        return existing

    missing = [
        name
        for name in _REQUIRED_PREDECESSOR_MARKERS
        if not getattr(jk, name, False)
    ]
    if missing:
        raise SourceBaselineCreationError(
            "Phase-8 baseline requires all predecessor authority extensions before sealing"
        )

    runtime_id = str(getattr(jk, "RUNTIME_ID", "") or "").strip()
    lane_id = str(getattr(jk, "LANE_ID", "") or "").strip()
    authority = RuntimeSourceAuthority(runtime_id=runtime_id, lane_id=lane_id)

    for component_id, path in requested:
        authority.register_component(component_id, path)

    baseline = authority.seal()

    jk._JACK_SOURCE_AUTHORITY = authority
    jk._JACK_SOURCE_AUTHORITY_INSTALLED = True
    jk.SourceAuthorityState = SourceAuthorityState
    jk.SourceAuthorityUnavailable = SourceAuthorityUnavailable
    jk.SourceAuthorityInvalidated = SourceAuthorityInvalidated
    jk.RUNTIME_SOURCE_BASELINE_SHA256 = baseline.aggregate_sha256
    jk.RUNTIME_SOURCE_BASELINE_COMPONENTS = tuple(baseline.component_ids)

    register = getattr(jk, "_register_runtime_manifest_components", None)
    if callable(register):
        register({"jack_source_drift_guard.py": Path(__file__).resolve()})

    return authority
