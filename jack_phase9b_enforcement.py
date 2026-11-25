"""Phase 9B-C experimental selected runtime-code enforcement.

Install ONLY in the secured --serve child after Phase 8 is active and before
the ASGI middleware stack is built. Phase 8 is not modified. This protects
consequential host-owned dispatch and HTTP release under a bounded capability
threat model; no in-process Python guard attests itself against an actor who
can rewrite all interpreter state or replace the outer ASGI call chain.
"""
from __future__ import annotations

from functools import wraps
from pathlib import Path
from typing import Any

from jack_runtime_code_guard import (
    RuntimeCodeAuthority,
    RuntimeCodeIntegrityCompromised,
    RuntimeCodeIntegrityUnavailable,
)

DENIAL_BODY = b'{"error":"jack_runtime_code_integrity_unavailable"}'
_PHASE9B_MARKER = "_JACK_RUNTIME_CODE_ENFORCEMENT_INSTALLED"
# Read-only exception paths are deliberately small and proven not to run
# model inference, Pi transport, or executor-side effects. Never infer read-only
# authority from GET alone: /health, /v1/models and Pi events have dependencies.
OBSERVATION_PATHS = frozenset({"/", "/jack/runtime/status", "/jack/runtimes"})


def _http_authority_scopes(scope: Any) -> tuple[str, ...]:
    path = str(scope.get("path", ""))
    method = str(scope.get("method", "GET")).upper()
    # Keep this classification in the executable's own literal bytecode.
    # Do not consult a rebindable global exception set on the request path.
    if method == "GET" and path in (
        "/", "/jack/runtime/status", "/jack/runtimes",
    ):
        return ("observation",)
    if method == "POST" and path == "/jack/security/path-admission":
        return ("executor", "authority")
    if method == "POST" and path == "/jack/orchestration/tasks":
        # Creating a Pi task can cause model/tool execution. Its release
        # requires intact model, executor, Pi and common security authority.
        return ("orchestration", "model", "executor", "authority")
    if method == "POST" and path in (
        "/jack/orchestration/tasks/cancel",
        "/jack/orchestration/session/new",
    ):
        # Cancellation must remain available when model execution is blocked.
        # Its actual Pi proxy and shared auth must still be intact.
        return ("orchestration", "authority")
    if method == "GET" and path in (
        "/jack/orchestration/status", "/jack/orchestration/events",
    ):
        # Both depend on authenticated Pi transport, not just observation.
        return ("orchestration", "authority")
    if method == "POST" and path in (
        "/v1/chat/completions", "/v1/responses",
    ):
        # Model result is permitted only after the protected tool-release
        # gate has separately verified executor authority for tool calls.
        return ("model", "authority")
    if method == "GET" and path in ("/health", "/v1/models", "/api/v1/models"):
        return ("model", "authority")
    # Unknown routes are not automatically blessed as diagnostics. Since no
    # dependency graph has been qualified for them, require all consequential
    # authorities until explicitly mapped and independently validated.
    return ("model", "executor", "orchestration", "authority")


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

        # Shared checker and route-table identity are checked for EVERY HTTP
        # path. Only consequence-specific slots are scoped, so an unrelated
        # model failure cannot discard safe status/diagnostic work.
        scopes = _http_authority_scopes(scope)
        try:
            self.authority.verify_for(*scopes)
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
                self.authority.verify_for(*scopes)
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
                    self.authority.verify_for(*scopes)
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
        guard.verify_for("model", "authority")
        result = await original_run(*args, **kwargs)
        guard.verify_for("model", "authority")
        return result

    @wraps(original_stream)
    async def guarded_stream(*args: Any, **kwargs: Any):
        guard.verify_for("model", "authority")
        # A confirmed code-integrity violation can also affect hidden
        # inference-stage tool actions. Merely draining the predecessor would
        # keep executing code whose authority cannot be trusted. Preserve the
        # already-released safe prefix and interrupt *future* work instead.
        source_stream = original_stream(*args, **kwargs)
        try:
            async for chunk in source_stream:
                guard.verify_for("model", "authority")
                yield chunk
        finally:
            close = getattr(source_stream, "aclose", None)
            if callable(close):
                await close()

    @wraps(original_tools)
    def guarded_tool_release(*args: Any, **kwargs: Any) -> Any:
        # A model tool-call proposal is a future executor consequence; never
        # release it while the executor admission code cannot be trusted.
        guard.verify_for("model", "executor", "authority")
        result = original_tools(*args, **kwargs)
        guard.verify_for("model", "executor", "authority")
        return result

    @wraps(original_executor)
    def guarded_executor(*args: Any, **kwargs: Any) -> Any:
        guard.verify_for("executor", "authority")
        result = original_executor(*args, **kwargs)
        guard.verify_for("executor", "authority")
        return result

    @wraps(original_proxy)
    async def guarded_proxy(request: Any, method: str, path: str, *args: Any, **kwargs: Any) -> Any:
        # The Pi proxy is an actual shared delegate for both status reads and
        # mutating operations. A GET is not independent of a mutated proxy.
        if str(method).upper() == "POST" and str(path) == "/v1/tasks":
            guard.verify_for("orchestration", "model", "executor", "authority")
        else:
            guard.verify_for("orchestration", "authority")
        # Worker settlements already admitted before this call remain outside
        # Jack's ability to revoke. Do not claim retroactive cancellation.
        return await original_proxy(request, method, path, *args, **kwargs)

    jk.KERNEL.run = guarded_run
    jk.KERNEL.stream = guarded_stream
    jk._phase4_partition_structured_tool_calls = guarded_tool_release
    jk._phase4_executor_admission_decision = guarded_executor
    jk._proxy_pi_control_request = guarded_proxy

    # Declare the consequence owned by each executable slot. Shared checker
    # and ASGI identities protect every request; ordinary read-only status
    # paths do not depend on model execution or mutating Pi orchestration.
    for label, owner, attr, scope in (
        ("http-auth", jk, "enforce_kernel_auth", "shared"),
        ("agent-request-sanitizer", jk, "sanitize_agent_request", "model"),
        ("executor-context", jk, "_phase4_executor_context_from_request", "model"),
        ("stream-public-release", jk, "_safe_public_stream", "model"),
        ("completion-envelope", jk, "completion_envelope", "model"),
        ("kernel-run", jk.KERNEL, "run", "model"),
        ("kernel-stream", jk.KERNEL, "stream", "model"),
        ("tool-release", jk, "_phase4_partition_structured_tool_calls", "model"),
        ("executor-admission", jk, "_phase4_executor_admission_decision", "executor"),
        ("pi-control", jk, "_proxy_pi_control_request", "orchestration"),
        ("source-measure", source, "_measure_regular_file", "shared"),
        ("source-verify", jk._JACK_SOURCE_AUTHORITY, "verify_for_authority_boundary", "shared"),
        ("source-observe", jk._JACK_SOURCE_AUTHORITY, "verify_now", "shared"),
        ("path-represented", path_policy, "authorize_represented_path", "shared"),
        ("path-structured", path_policy, "authorize_structured_tool_call", "shared"),
        ("path-executor", path_policy, "authorize_executor_tool_call", "shared"),
        ("consequence", consequence, "evaluate_consequence", "shared"),
        ("responses-stream", responses, "_stream", "model"),
        ("responses-nonstream", responses, "_nonstream", "model"),
        ("p9-verify", code_guard.RuntimeCodeAuthority, "verify_for", "shared"),
        ("p9-check", code_guard.RuntimeCodeAuthority, "_check_locked", "shared"),
        ("p9-resolve", code_guard, "_resolve", "shared"),
        ("p9-measure", code_guard, "_function_shape", "shared"),
        ("p9-route-snapshot", code_guard, "_route_snapshot", "shared"),
        ("p9-route-classifier", sys.modules[__name__], "_http_authority_scopes", "shared"),
        ("p9-asgi", Phase9BASGIGuard, "__call__", "shared"),
    ):
        guard.register(name=label, owner=owner, attribute=attr, scope=scope)

    for label, module, scope in (
        ("module-source", source, "shared"),
        ("module-code-guard", code_guard, "shared"),
        ("module-phase9b-enforcement", sys.modules[__name__], "shared"),
        ("module-path-policy", path_policy, "shared"),
        ("module-consequence", consequence, "shared"),
        ("module-evidence", evidence, "shared"),
        ("module-responses", responses, "model"),
    ):
        guard.register_module(name=label, module_name=module.__name__, scope=scope)

    for label, route in _selected_required_routes(jk):
        scope = ("model" if label in ("chat", "responses") else
                 "executor" if label == "executor" else "orchestration")
        for attribute in ("endpoint", "app"):
            guard.register(name=f"route-{label}-{attribute}",
                           owner=route, attribute=attribute, scope=scope)
        dependency = getattr(route, "dependant", None)
        if dependency is None:
            raise RuntimeCodeIntegrityUnavailable("required FastAPI route dependency absent")
        guard.register(name=f"route-{label}-dependent", owner=dependency,
                       attribute="call", scope=scope)

    # Protect the observational routes themselves. They may continue serving
    # verified read-only state when a separate consequence path is compromised.
    # Optional observational routes are absent in isolated minimal ASGI tests.
    for route in tuple(jk.APP.routes):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", ()) or ()
        if path not in OBSERVATION_PATHS or "GET" not in methods:
            continue
        if not all(callable(getattr(route, attr, None)) for attr in ("endpoint", "app")):
            raise RuntimeCodeIntegrityUnavailable("required observational route not measurable")
        safe_name = path.replace("/", "_") or "_root"
        for attribute in ("endpoint", "app"):
            guard.register(name=f"route-observation-{safe_name}-{attribute}",
                           owner=route, attribute=attribute, scope="observation")
        dependency = getattr(route, "dependant", None)
        if dependency is not None and callable(getattr(dependency, "call", None)):
            guard.register(name=f"route-observation-{safe_name}-dependent",
                           owner=dependency, attribute="call", scope="observation")

    guard.register_source(name="source-phase9-code-guard",
                          path=Path(code_guard.__file__).resolve(), scope="shared")
    guard.register_source(name="source-phase9-enforcement",
                          path=Path(__file__).resolve(), scope="shared")
    # The experimental policy gates are composed before sealing. Keep the
    # historical Phase 8 manifest frozen and extend this selected manifest.
    if getattr(jk, "_JACK_PHASE10_PATH_AUTHORITY", None) is not None:
        import jack_policy_integrity as static
        import jack_phase10_path_enforcement as path_gate
        import jack_phase10_canary_enforcement as canary_gate
        import jack_phase10_credential_enforcement as credential_gate
        import jack_phase10_dynamic_authority as dynamic
        import jack_phase11_privacy as privacy
        import jack_credential_guard as credential
        for module, scope in (
            (static, "shared"), (path_gate, "shared"),
            (canary_gate, "model"), (credential_gate, "authority"),
            (dynamic, "authority"), (privacy, "shared"),
            (credential, "authority"),
        ):
            guard.register_module(name="module-" + module.__name__,
                                  module_name=module.__name__, scope=scope)
            guard.register_source(name="source-" + module.__name__,
                                  path=Path(module.__file__).resolve(), scope=scope)
        for label, owner, attr, scope in (
            ("policy-verify", static.RuntimePolicyAuthority, "verify_for", "shared"),
            ("policy-check", static.RuntimePolicyAuthority, "_check_locked", "shared"),
            ("policy-read", static.RuntimePolicyAuthority, "_read", "shared"),
            ("policy-digest", static, "_digest", "shared"),
            ("policy-material", static, "_canonical_material", "shared"),
            ("pending-verify", dynamic.PendingAuthority, "verify", "authority"),
            ("pending-digest", dynamic.PendingAuthority, "_digest", "authority"),
            ("pending-material", dynamic, "_material", "authority"),
            ("pending-register", dynamic.PendingAuthority, "register", "authority"),
            ("pending-transition", dynamic.PendingAuthority, "transition", "authority"),
            ("pending-retire", dynamic.PendingAuthority, "retire", "authority"),
            ("pending-admission", jk.KERNEL, "_phase4_pending_tool_call_snapshot", "executor"),
            ("pending-consume", jk.KERNEL, "_consume_pending_tool_resume", "model"),
            ("pending-create", jk.KERNEL, "_register_stage_tool_resume", "model"),
            ("credential-post", jk.BACKEND._client, "post", "model"),
            ("credential-build", jk.BACKEND._client, "build_request", "model"),
            ("credential-publish", jk.OrchestrationEventHub, "_publish", "orchestration"),
            ("privacy-redact", privacy.PrivacyBoundary, "redact", "shared"),
            ("privacy-match", privacy.PrivacyBoundary, "_contains", "shared"),
            ("privacy-archive", privacy.PrivacyBoundary, "permits_archive", "shared"),
            ("privacy-formatter", privacy.ProtectedDiagnosticFormatter, "format", "shared"),
        ):
            guard.register(name=label, owner=owner, attribute=attr, scope=scope)

    guard.register_route_table(name="all-http-routes", app=jk.APP)
    guard.seal()

    # The *outer* HTTP guard makes it impossible to defeat request/response
    # checks just by swapping jk.KERNEL.run in an otherwise unchanged APP.
    # ASGI wrapping itself remains inside the same interpreter trust domain.
    jk.APP.add_middleware(Phase9BASGIGuard, authority=guard)
    jk._JACK_RUNTIME_CODE_AUTHORITY = guard
    setattr(jk, _PHASE9B_MARKER, True)
    return guard
