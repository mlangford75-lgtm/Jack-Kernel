"""Phase 9B experimental selected executable-identity primitive.

No security authority is conferred until a separately validated runtime installer
binds checks to real admission/release paths. This module does not claim hostile
same-interpreter tamper resistance or full dispatch-graph attestation.
"""
from __future__ import annotations

import hashlib
import sys
import threading
import types
from pathlib import Path
from dataclasses import dataclass
from typing import Any


SCHEMA = "jack.runtime-code-identity.v1"


class RuntimeCodeIntegrityUnavailable(RuntimeError):
    """Cannot establish a required current executable identity."""


class RuntimeCodeIntegrityCompromised(RuntimeCodeIntegrityUnavailable):
    """Protected executable identity differs from the startup baseline."""

    reason_code = "RUNTIME_INTEGRITY_COMPROMISED"


class _ProtectedSlotMissing(RuntimeCodeIntegrityUnavailable):
    """Confirmed absence of a previously captured executable binding."""


def _function_shape(fn: types.FunctionType) -> bytes:
    """Fingerprint code and selected executable delegates without invoking them.

    A limited closed type grammar avoids executing arbitrary __repr__, __hash__,
    attribute access or external objects while measuring. Unknown mutable
    dependencies are explicitly not represented as immutable executable state.
    """
    digest = hashlib.sha256()
    visited_functions: set[int] = set()
    nodes = 0

    def update_atom(tag: bytes, value: bytes = b"") -> None:
        digest.update(len(tag).to_bytes(2, "big"))
        digest.update(tag)
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)

    def walk(obj: Any, depth: int, *, keyword_defaults: bool = False) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > 4096 or depth > 20:
            raise RuntimeCodeIntegrityUnavailable("executable shape exceeds measurement limits")
        if isinstance(obj, types.CodeType):
            update_atom(b"code-bytecode", obj.co_code)
            update_atom(b"code-exceptions", obj.co_exceptiontable)
            for attribute in (
                "co_argcount", "co_posonlyargcount", "co_kwonlyargcount",
                "co_nlocals", "co_stacksize", "co_flags",
                "co_names", "co_varnames", "co_cellvars", "co_freevars",
                "co_consts",
            ):
                update_atom(b"code-attribute", attribute.encode("ascii"))
                walk(getattr(obj, attribute), depth + 1)
        elif isinstance(obj, types.MethodType):
            update_atom(b"method-owner", str(id(obj.__self__)).encode("ascii"))
            walk(obj.__func__, depth + 1)
        elif isinstance(obj, types.FunctionType):
            update_atom(b"function-id", str(id(obj)).encode("ascii"))
            # CPython 3.14 can produce different marshal code-object bytes
            # while the *same* function is executing / specializing. Fingerprint
            # explicit behavior-bearing attributes instead, recursively.
            # co_code is the stable, non-adaptive bytecode representation.
            walk(obj.__code__, depth + 1)
            if id(obj) in visited_functions:
                update_atom(b"function-cycle")
                return
            visited_functions.add(id(obj))
            walk(obj.__defaults__, depth + 1)
            walk(obj.__kwdefaults__, depth + 1, keyword_defaults=True)
            closure = obj.__closure__
            if closure is None:
                update_atom(b"no-closure")
            else:
                update_atom(b"closure-count", str(len(closure)).encode("ascii"))
                for cell in closure:
                    try:
                        walk(cell.cell_contents, depth + 1)
                    except ValueError:
                        update_atom(b"empty-cell")
        elif obj is None:
            update_atom(b"none")
        elif type(obj) is bool:
            update_atom(b"bool", b"1" if obj else b"0")
        elif type(obj) is int:
            update_atom(b"int", str(obj).encode("ascii"))
        elif type(obj) is str:
            update_atom(b"str", obj.encode("utf-8", "surrogatepass"))
        elif type(obj) is bytes:
            update_atom(b"bytes", obj)
        elif type(obj) is float:
            update_atom(b"float", repr(obj).encode("ascii"))
        elif obj is Ellipsis:
            update_atom(b"ellipsis")
        elif type(obj) is complex:
            update_atom(b"complex", repr(obj).encode("ascii"))
        elif type(obj) is tuple:
            update_atom(b"tuple-size", str(len(obj)).encode("ascii"))
            for item in obj:
                walk(item, depth + 1)
        elif type(obj) is frozenset:
            # A stable list of scalar values only; otherwise opaque state.
            parts: list[bytes] = []
            for item in obj:
                if type(item) not in (str, bytes, int, bool, float, type(None)):
                    update_atom(b"opaque-frozenset", str(id(obj)).encode("ascii"))
                    break
                parts.append(repr((type(item).__name__, item)).encode("utf-8", "surrogatepass"))
            else:
                for part in sorted(parts):
                    update_atom(b"frozenset-item", part)
        elif type(obj) is dict:
            # Function keyword-default assignments are executable inputs: a
            # scalar-only change can change behavior with identical bytecode.
            # Ordinary mutable state dictionaries captured in closures/defaults
            # are *not* treated as immutable policy (Phase 10 owns that).
            update_atom(b"dict-object", str(id(obj)).encode("ascii"))
            if keyword_defaults:
                update_atom(b"kwdefaults-size", str(len(obj)).encode("ascii"))
            for key in sorted((key for key in obj if type(key) is str), key=str):
                value = obj[key]
                if keyword_defaults or isinstance(value, (types.FunctionType, types.MethodType)):
                    update_atom(b"delegate-key", key.encode("utf-8", "surrogatepass"))
                    if keyword_defaults and type(value) not in (
                        bool, int, str, bytes, float, type(None), tuple,
                        types.FunctionType, types.MethodType,
                    ):
                        # Do not recursively digest arbitrary mutable payloads.
                        update_atom(b"opaque-default", str(id(value)).encode("ascii"))
                    else:
                        walk(value, depth + 1)
        else:
            update_atom(b"opaque-owner", (type(obj).__module__ + "." + type(obj).__qualname__).encode("utf-8", "replace"))
            update_atom(b"opaque-id", str(id(obj)).encode("ascii"))

    walk(fn, 0)
    return digest.digest()


def _resolve(owner: Any, name: str) -> tuple[Any, Any, bytes]:
    """Read the effective ordinary attribute; avoid invoking target itself."""
    try:
        value = getattr(owner, name)
    except AttributeError as exc:
        raise _ProtectedSlotMissing("protected executable binding is absent") from exc
    except Exception as exc:
        raise RuntimeCodeIntegrityUnavailable("protected executable is not measurable") from exc
    if isinstance(value, types.MethodType):
        receiver = value.__self__
        fn = value.__func__
    elif isinstance(value, types.FunctionType):
        receiver = None
        fn = value
    else:
        raise _ProtectedSlotMissing("protected executable is no longer a Python function/method")
    try:
        shape = _function_shape(fn)
    except RuntimeCodeIntegrityUnavailable:
        raise
    except Exception as exc:
        raise RuntimeCodeIntegrityUnavailable("protected executable shape not measurable") from exc
    return receiver, fn, shape


@dataclass(frozen=True)
class ExecutableSlot:
    name: str
    owner: Any
    attribute: str
    receiver: Any
    function: Any
    shape: bytes
    scope: str = "shared"


@dataclass(frozen=True)
class _ModuleIdentity:
    label: str
    module_name: str
    original: types.ModuleType
    scope: str = "shared"


@dataclass(frozen=True)
class _SourceIdentity:
    label: str
    path: Path
    canonical_path: str
    sha256: str
    scope: str = "shared"


@dataclass(frozen=True)
class _RouteIdentity:
    route: Any
    path: Any
    methods: frozenset[str]


@dataclass(frozen=True)
class _RouteTableIdentity:
    label: str
    app: Any
    routes: tuple[_RouteIdentity, ...]
    scope: str = "shared"


def _route_snapshot(app: Any) -> tuple[_RouteIdentity, ...]:
    """Record the actual registered router table, not lazy middleware state."""
    try:
        routes = tuple(app.routes)
        return tuple(
            _RouteIdentity(
                route=route,
                path=getattr(route, "path", None),
                methods=frozenset(str(x) for x in (getattr(route, "methods", None) or ())),
            )
            for route in routes
        )
    except Exception as exc:
        raise RuntimeCodeIntegrityUnavailable("route table identity unavailable") from exc


class RuntimeCodeAuthority:
    """Selected executable-identity validator with consequence-scoped containment.

    Scope labels are host-owned at installation. A model-path mismatch cannot
    revoke unrelated read-only diagnostics or pre-admitted independent work.
    Shared verifier/dispatch corruption still blocks all registered authority.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._slots: list[ExecutableSlot] = []
        self._modules: list[_ModuleIdentity] = []
        self._sources: list[_SourceIdentity] = []
        self._route_tables: list[_RouteTableIdentity] = []
        self._state = "INITIALIZING"
        # Pin the method that performs actual measurement. Checking it before
        # dispatch prevents straightforward descriptor rebinding from making
        # every subsequent verify() report a fabricated success. This is not
        # independent attestation against arbitrary same-interpreter mutation.
        self._check_method = type(self)._check_locked
        self._last_mismatches: tuple[str, ...] = ()
        self._invalidated_scopes: set[str] = set()
        self._unavailable_scopes: set[str] = set()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == "INVALIDATED" or self._invalidated_scopes:
                return "INVALIDATED"
            if self._state == "SUSPENDED_UNVERIFIED" or self._unavailable_scopes:
                return "SUSPENDED_UNVERIFIED"
            return self._state

    @property
    def mismatched_slots(self) -> tuple[str, ...]:
        with self._lock:
            return self._last_mismatches

    def register(self, *, name: str, owner: Any, attribute: str, scope: str = "shared") -> None:
        if not isinstance(name, str) or not name or not isinstance(attribute, str) or not attribute or not isinstance(scope, str) or not scope:
            raise ValueError("protected executable name and attribute must be non-empty strings")
        with self._lock:
            if self._state != "INITIALIZING":
                raise RuntimeError("protected executable manifest is sealed")
            if any(slot.name == name for slot in self._slots):
                raise ValueError("duplicate protected executable label")
            receiver, fn, shape = _resolve(owner, attribute)
            self._slots.append(ExecutableSlot(name, owner, attribute, receiver, fn, shape, scope))

    def register_module(self, *, name: str, module_name: str, scope: str = "shared") -> None:
        """Pin the imported-module identity used by dynamic import call sites."""
        if not name or not module_name or not scope:
            raise ValueError("module label, import name and scope must be non-empty")
        with self._lock:
            if self._state != "INITIALIZING":
                raise RuntimeError("protected module manifest is sealed")
            if any(x.label == name for x in self._modules):
                raise ValueError("duplicate protected module label")
            module = sys.modules.get(module_name)
            if not isinstance(module, types.ModuleType):
                raise RuntimeCodeIntegrityUnavailable("required module not loaded")
            self._modules.append(_ModuleIdentity(name, module_name, module, scope))

    def register_source(self, *, name: str, path: Path, scope: str = "shared") -> None:
        """Seal exact source bytes for new Phase 9 modules absent from Phase 8.

        Reuse Phase 8's already validated regular-file identity measurement
        without changing its historical required-source manifest.
        """
        if not isinstance(name, str) or not name or not isinstance(scope, str) or not scope:
            raise ValueError("protected source label and scope must be nonempty")
        import jack_source_drift_guard as source
        with self._lock:
            if self._state != "INITIALIZING":
                raise RuntimeError("protected source manifest is sealed")
            if any(x.label == name for x in self._sources):
                raise ValueError("duplicate protected source label")
            try:
                p = Path(path)
                measured = source._measure_regular_file(p)
            except Exception as exc:
                raise RuntimeCodeIntegrityUnavailable(
                    "required protected source could not be sealed"
                ) from exc
            self._sources.append(_SourceIdentity(
                name, p, measured.canonical_path, measured.sha256, scope,
            ))

    def register_route_table(self, *, name: str, app: Any, scope: str = "shared") -> None:
        """Pin a completed HTTP route table; middleware warm-up is out-of-scope."""
        if not name or not scope:
            raise ValueError("route table label and scope must be non-empty")
        with self._lock:
            if self._state != "INITIALIZING":
                raise RuntimeError("protected route manifest is sealed")
            if any(x.label == name for x in self._route_tables):
                raise ValueError("duplicate route table label")
            self._route_tables.append(_RouteTableIdentity(name, app, _route_snapshot(app), scope))

    def seal(self) -> None:
        with self._lock:
            if self._state != "INITIALIZING" or not self._slots:
                raise RuntimeCodeIntegrityUnavailable("nonempty manifest required before sealing")
            # Current identities must still match their registration captures.
            self._check_method(self)
            self._state = "ACTIVE"

    def _check_locked(self, *, scopes: frozenset[str] | None = None) -> None:
        """Measure selected authority. Only proven affected scopes are revoked."""
        mismatches: list[str] = []
        mismatch_scopes: set[str] = set()
        unavailable_scopes: set[str] = set()
        measurement_error: RuntimeCodeIntegrityUnavailable | None = None

        def selected(scope: str) -> bool:
            return scopes is None or scope == "shared" or scope in scopes

        def record_unavailable(scope: str, exc: RuntimeCodeIntegrityUnavailable) -> None:
            nonlocal measurement_error
            unavailable_scopes.add(scope)
            measurement_error = measurement_error or exc

        for slot in self._slots:
            if not selected(slot.scope):
                continue
            try:
                receiver, fn, shape = _resolve(slot.owner, slot.attribute)
            except _ProtectedSlotMissing:
                mismatches.append(slot.name)
                mismatch_scopes.add(slot.scope)
                continue
            except RuntimeCodeIntegrityUnavailable as exc:
                record_unavailable(slot.scope, exc)
                continue
            if receiver is not slot.receiver or fn is not slot.function or shape != slot.shape:
                mismatches.append(slot.name)
                mismatch_scopes.add(slot.scope)
        for module in self._modules:
            if not selected(module.scope):
                continue
            if sys.modules.get(module.module_name) is not module.original:
                mismatches.append(module.label)
                mismatch_scopes.add(module.scope)
        if self._sources:
            import jack_source_drift_guard as source
        for item in self._sources:
            if not selected(item.scope):
                continue
            try:
                observed = source._measure_regular_file(item.path)
            except (source._SourceComponentMissing, source._SourceComponentKindChanged):
                mismatches.append(item.label)
                mismatch_scopes.add(item.scope)
                continue
            except source.SourceMeasurementUnavailable as exc:
                record_unavailable(
                    item.scope, RuntimeCodeIntegrityUnavailable(
                        "required protected source measurement unavailable"
                    ),
                )
                continue
            except Exception as exc:
                record_unavailable(
                    item.scope, RuntimeCodeIntegrityUnavailable(
                        "required protected source measurement unavailable"
                    ),
                )
                continue
            if (observed.canonical_path != item.canonical_path
                    or observed.sha256 != item.sha256):
                mismatches.append(item.label)
                mismatch_scopes.add(item.scope)
        for table in self._route_tables:
            if not selected(table.scope):
                continue
            try:
                observed = _route_snapshot(table.app)
            except RuntimeCodeIntegrityUnavailable as exc:
                record_unavailable(table.scope, exc)
                continue
            if len(observed) != len(table.routes) or any(
                current.route is not expected.route
                or current.path != expected.path
                or current.methods != expected.methods
                for current, expected in zip(observed, table.routes)
            ):
                mismatches.append(table.label)
                mismatch_scopes.add(table.scope)
        if mismatches:
            self._last_mismatches = tuple(mismatches)
            if scopes is None:
                self._state = "INVALIDATED"
            else:
                self._invalidated_scopes.update(mismatch_scopes)
            raise RuntimeCodeIntegrityCompromised("protected executable identity changed")
        if measurement_error is not None:
            if scopes is None:
                self._state = "SUSPENDED_UNVERIFIED"
            else:
                self._unavailable_scopes.update(unavailable_scopes)
            raise RuntimeCodeIntegrityUnavailable(
                "protected executable measurement unavailable"
            ) from measurement_error
        if scopes is not None:
            # Only previously uncertain measurements may recover. Confirmed
            # mismatches remain terminal; no in-place rebaseline is allowed.
            self._unavailable_scopes.difference_update(scopes)
            self._unavailable_scopes.discard("shared")

    def verify_for(self, *scopes: str) -> None:
        """Verify only authority needed by this real admission/release.

        All scopes include protected shared checker and route-table identity.
        A model-side compromise must not prevent healthy read-only diagnostic
        endpoints or independent Pi control from operating.
        """
        if not scopes or any(not isinstance(s, str) or not s for s in scopes):
            raise ValueError("at least one explicit authority scope is required")
        with self._lock:
            if type(self)._check_locked is not self._check_method:
                self._last_mismatches = ("p9-check",)
                self._invalidated_scopes.add("shared")
                raise RuntimeCodeIntegrityCompromised(
                    "runtime executable verifier binding changed"
                )
            if self._state == "INITIALIZING":
                raise RuntimeCodeIntegrityUnavailable("runtime executable authority not sealed")
            if self._state == "INVALIDATED" or "shared" in self._invalidated_scopes:
                raise RuntimeCodeIntegrityCompromised("shared runtime executable authority invalidated")
            if self._invalidated_scopes.intersection(scopes):
                raise RuntimeCodeIntegrityCompromised("affected executable authority invalidated")
            self._check_method(self, scopes=frozenset(scopes))

    def verify(self) -> None:
        with self._lock:
            if type(self)._check_locked is not self._check_method:
                self._last_mismatches = ("p9-check",)
                self._invalidated_scopes.add("shared")
                raise RuntimeCodeIntegrityCompromised(
                    "runtime executable verifier binding changed"
                )
            if self._state == "INVALIDATED":
                raise RuntimeCodeIntegrityCompromised("runtime executable authority invalidated")
            if self._state == "INITIALIZING":
                raise RuntimeCodeIntegrityUnavailable("runtime executable authority not sealed")
            self._check_method(self)
            self._state = "ACTIVE"
