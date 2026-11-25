"""Phase 9B-C experimental selected runtime-code enforcement.

Install ONLY in the secured --serve child after Phase 8 is active and before
the ASGI middleware stack is built. Phase 8 is not modified. This protects
consequential host-owned dispatch and HTTP release under a bounded capability
threat model; no in-process Python guard attests itself against an actor who
can rewrite all interpreter state or replace the outer ASGI call chain.
"""
from __future__ import annotations

from functools import wraps
from typing import Any

from jack_runtime_code_guard import (
    RuntimeCodeAuthority,
    RuntimeCodeIntegrityCompromised,
    RuntimeCodeIntegrityUnavailable,
)

DENIAL_BODY = b'{"error":"jack_runtime_code_integrity_unavailable"}'
_PHASE9B_MARKER = "_JACK_RUNTIME_CODE_ENFORCEMENT_INSTALLED"


class Phase9BASGIGuard:
    """Pure ASGI ingress/egress guard; never uses BaseHTTPMiddleware.

    A stream that loses integrity after emitting a safe prefix is drained with
    later body bytes withheld. A non-stream with already-sent headers aborts
    instead of faking a successful empty response. Once integrity fails the
    authority's own terminal/suspension state decides future admissions.
    """

    def __init__(self, app: Any, *, authority: RuntimeCodeAuthority) -> None:
        self.app = app
        self.authority = authority

    @staticmethod
    async def _denied(send: Any) -> None:
        await send({
            "type": "http.response.start",
            "status": 503,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(DENIAL_BODY)).encode("ascii")),
                (b"cache-control", b"no-store"),
            ],
        })
        await send({"type": "http.response.body", "body": DENIAL_BODY, "more_body": False})

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        # Check every HTTP route, including unknown/added paths: limiting this
        # to previously known URLs would allow bypass via a newly added route.
        try:
            self.authority.verify()
        except RuntimeCodeIntegrityUnavailable:
            await self._denied(send)
            return

        started = False
        is_sse = False
        blocked_stream = False

        async def guarded_send(event: Any) -> None:
            nonlocal started, is_sse, blocked_stream
            kind = event.get("type")
            if kind == "http.response.start":
                # Verify before irreversible headers. For a violation here,
                # raise and return a canonical 503 from the outer middleware.
                self.authority.verify()
                headers = event.get("headers") or ()
                is_sse = any(
                    bytes(k).lower() == b"content-type"
                    and b"text/event-stream" in bytes(v).lower()
                    for k, v in headers
                )
                await send(event)
                started = True
                return

            if kind == "http.response.body":
                if blocked_stream:
                    if not event.get("more_body", False):
                        await send({
                            "type": "http.response.body",
                            "body": b"",
                            "more_body": False,
                        })
                    return

                try:
                    self.authority.verify()
                except RuntimeCodeIntegrityUnavailable:
                    if is_sse:
                        blocked_stream = True
                        if not event.get("more_body", False):
                            await send({
                                "type": "http.response.body",
                                "body": b"",
                                "more_body": False,
                            })
                        return
                    # No unverified data may be emitted after headers, even
                    # though this may require terminating the HTTP connection.
                    raise

            await send(event)

        try:
            await self.app(scope, receive, guarded_send)
        except RuntimeCodeIntegrityUnavailable:
            if not started:
                await self._denied(send)
                return
            # For non-stream content whose headers are already sent, fail by
            # truncating/aborting rather than releasing an untrusted payload.
            raise


def _selected_required_routes(jk: Any) -> tuple[Any, ...]:
    base = str(getattr(jk, "ORCHESTRATION_BASE_PATH", "") or "")
    if not base or not base.startswith("/"):
        raise RuntimeCodeIntegrityUnavailable("required orchestration base path unavailable")

    required: dict[tuple[str, str], str] = {
        ("/v1/chat/completions", "POST"): "chat",
        ("/v1/responses", "POST"): "responses",
        ("/jack/security/path-admission", "POST"): "executor",
        (base + "/tasks", "POST"): "pi-tasks",
        (base + "/tasks/cancel", "POST"): "pi-cancel",
        (base + "/session/new", "POST"): "pi-session",
    }
    found: dict[str, Any] = {}
    for route in tuple(jk.APP.routes):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", ()) or ()
        for (needed_path, method), label in required.items():
            if path == needed_path and method in methods:
                if label in found:
                    raise RuntimeCodeIntegrityUnavailable("ambiguous protected route")
                found[label] = route
    if len(found) != len(required):
        raise RuntimeCodeIntegrityUnavailable("required protected HTTP route missing")
    return tuple((label, found[label]) for label in required.values())


def install(jk: Any) -> RuntimeCodeAuthority:
    """Seal selected, effective post-Phase-8 bindings before ASGI startup.

    Bootstrapping is strictly in the secure service, not interactive CLI.
    Refuse an already constructed ASGI middleware stack (no silent rebaseline).
    """
    existing = getattr(jk, "_JACK_RUNTIME_CODE_AUTHORITY", None)
    if getattr(jk, _PHASE9B_MARKER, False):
        if isinstance(existing, RuntimeCodeAuthority):
            return existing
        raise RuntimeCodeIntegrityUnavailable("Phase 9B installation marker inconsistent")
    if not getattr(jk, "_JACK_SOURCE_RUNTIME_ENFORCEMENT_INSTALLED", False):
        raise RuntimeCodeIntegrityUnavailable("Phase 9B requires active Phase 8")
    if getattr(jk.APP, "middleware_stack", None) is not None:
        raise RuntimeCodeIntegrityUnavailable("Phase 9B must install before ASGI startup")

    import jack_consequence_gate as consequence
    import jack_evidence_guard as evidence
    import jack_path_policy as path_policy
    import jack_responses_compat as responses
    import jack_source_drift_guard as source
    import jack_runtime_code_guard as code_guard
    import sys

    guard = RuntimeCodeAuthority()
    # Register the *effective* Phase-8 wrapped bindings first. These are
    # replaced below with Phase-9 wrappers; the final manifest is captured
    # only after the complete wrapping composition.
    original_run = jk.KERNEL.run
    original_stream = jk.KERNEL.stream
    original_tools = jk._phase4_partition_structured_tool_calls
    original_executor = jk._phase4_executor_admission_decision
    original_proxy = jk._proxy_pi_control_request
    if not all(callable(x) for x in (
        original_run, original_stream, original_tools, original_executor,
        original_proxy,
    )):
        raise RuntimeCodeIntegrityUnavailable("required P0 executable is not callable")

    @wraps(original_run)
    async def guarded_run(*args: Any, **kwargs: Any) -> Any:
        guard.verify()
        result = await original_run(*args, **kwargs)
        guard.verify()
        return result

    @wraps(original_stream)
    async def guarded_stream(*args: Any, **kwargs: Any):
        guard.verify()
        interrupted: RuntimeCodeIntegrityUnavailable | None = None
        try:
            async for chunk in original_stream(*args, **kwargs):
                if interrupted is not None:
                    # Already-produced safe bytes remain committed; drain
                    # cognition without releasing any subsequent bytes.
                    continue
                try:
                    guard.verify()
                except RuntimeCodeIntegrityUnavailable as exc:
                    interrupted = exc
                    continue
                yield chunk
        except Exception:
            if interrupted is not None:
                raise interrupted
            raise
        if interrupted is not None:
            # Preserve clean async-generator close/cancellation semantics.
            # Raise only after the predecessor has naturally finished.
            raise interrupted

    @wraps(original_tools)
    def guarded_tool_release(*args: Any, **kwargs: Any) -> Any:
        guard.verify()
        result = original_tools(*args, **kwargs)
        guard.verify()
        return result

    @wraps(original_executor)
    def guarded_executor(*args: Any, **kwargs: Any) -> Any:
        guard.verify()
        result = original_executor(*args, **kwargs)
        guard.verify()
        return result

    @wraps(original_proxy)
    async def guarded_proxy(request: Any, method: str, path: str, *args: Any, **kwargs: Any) -> Any:
        if str(method).upper() == "POST" and str(path) in (
            "/v1/tasks", "/v1/tasks/cancel", "/v1/session/new",
        ):
            guard.verify()
        # Do not retract an external action already admitted by the host.
        return await original_proxy(request, method, path, *args, **kwargs)

    jk.KERNEL.run = guarded_run
    jk.KERNEL.stream = guarded_stream
    jk._phase4_partition_structured_tool_calls = guarded_tool_release
    jk._phase4_executor_admission_decision = guarded_executor
    jk._proxy_pi_control_request = guarded_proxy

    for label, owner, attr in (
        ("kernel-run", jk.KERNEL, "run"),
        ("kernel-stream", jk.KERNEL, "stream"),
        ("tool-release", jk, "_phase4_partition_structured_tool_calls"),
        ("executor-admission", jk, "_phase4_executor_admission_decision"),
        ("pi-control", jk, "_proxy_pi_control_request"),
        ("source-measure", source, "_measure_regular_file"),
        ("source-verify", jk._JACK_SOURCE_AUTHORITY, "verify_for_authority_boundary"),
        ("source-observe", jk._JACK_SOURCE_AUTHORITY, "verify_now"),
        ("path-represented", path_policy, "authorize_represented_path"),
        ("path-structured", path_policy, "authorize_structured_tool_call"),
        ("path-executor", path_policy, "authorize_executor_tool_call"),
        ("consequence", consequence, "evaluate_consequence"),
        ("responses-stream", responses, "_stream"),
        ("responses-nonstream", responses, "_nonstream"),
        ("p9-verify", code_guard.RuntimeCodeAuthority, "verify"),
        ("p9-resolve", code_guard, "_resolve"),
        ("p9-measure", code_guard, "_function_shape"),
        ("p9-asgi", Phase9BASGIGuard, "__call__"),
    ):
        guard.register(name=label, owner=owner, attribute=attr)

    for label, module in (
        ("module-source", source),
        ("module-code-guard", code_guard),
        ("module-phase9b-enforcement", sys.modules[__name__]),
        ("module-path-policy", path_policy),
        ("module-consequence", consequence),
        ("module-evidence", evidence),
        ("module-responses", responses),
    ):
        guard.register_module(name=label, module_name=module.__name__)

    for label, route in _selected_required_routes(jk):
        for attribute in ("endpoint", "app"):
            guard.register(name=f"route-{label}-{attribute}", owner=route, attribute=attribute)
        dependency = getattr(route, "dependant", None)
        if dependency is None:
            raise RuntimeCodeIntegrityUnavailable("required FastAPI route dependency absent")
        guard.register(name=f"route-{label}-dependent", owner=dependency, attribute="call")

    guard.register_route_table(name="all-http-routes", app=jk.APP)
    guard.seal()

    # The *outer* HTTP guard makes it impossible to defeat request/response
    # checks just by swapping jk.KERNEL.run in an otherwise unchanged APP.
    # ASGI wrapping itself remains inside the same interpreter trust domain.
    jk.APP.add_middleware(Phase9BASGIGuard, authority=guard)
    jk._JACK_RUNTIME_CODE_AUTHORITY = guard
    setattr(jk, _PHASE9B_MARKER, True)
    return guard
