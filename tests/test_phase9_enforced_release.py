"""Phase 9B-C release prevention and protected route admission tests.

This is an experimental test suite: uses real FastAPI/ASGI event dispatch and
the post-Phase-8 installation function without changing Phase 8 production code.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import jack_source_drift_guard as phase8
from jack_runtime_code_guard import RuntimeCodeAuthority, RuntimeCodeIntegrityCompromised
from jack_phase9b_enforcement import Phase9BASGIGuard, install, DENIAL_BODY


def _async_send(events):
    async def send(event):
        events.append(event)
    return send


def _authority():
    def approved():
        return "permitted"
    owner = SimpleNamespace(action=approved)
    guard = RuntimeCodeAuthority()
    guard.register(name="executor", owner=owner, attribute="action")
    guard.seal()
    return guard, owner


def test_asgi_request_admission_blocks_swapped_binding_before_handler():
    authority, owner = _authority()
    calls = []

    async def backend(scope, receive, send):
        calls.append("called")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"unsafe", "more_body": False})

    app = Phase9BASGIGuard(backend, authority=authority)
    owner.action = lambda: "bypass"
    async def execute():
        outbound = []
        await app({"type": "http", "path": "/v1/chat/completions"}, None, _async_send(outbound))
        return outbound
    messages = asyncio.run(execute())
    assert calls == []
    assert messages[0]["status"] == 503
    assert messages[1]["body"] == DENIAL_BODY
    assert authority.state == "INVALIDATED"


def test_asgi_benign_nonstream_returns_unaltered_bytes():
    authority, _owner = _authority()

    async def backend(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b'{"safe":true}', "more_body": False})

    events = []
    async def execute():
        await Phase9BASGIGuard(backend, authority=authority)(
            {"type": "http"}, None, _async_send(events)
        )
    asyncio.run(execute())
    assert events == [
        {"type": "http.response.start", "status": 200, "headers": []},
        {"type": "http.response.body", "body": b'{"safe":true}', "more_body": False},
    ]


def test_asgi_response_start_mutation_returns_503_without_leaking():
    authority, owner = _authority()

    async def backend(scope, receive, send):
        owner.action = lambda: "bypass"
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"unsafe", "more_body": False})

    events = []
    async def execute():
        await Phase9BASGIGuard(backend, authority=authority)(
            {"type": "http"}, None, _async_send(events)
        )
    asyncio.run(execute())
    assert events[0]["status"] == 503
    assert events[1]["body"] == DENIAL_BODY


def test_asgi_nonstream_after_headers_never_releases_unverified_body():
    authority, owner = _authority()
    events = []

    async def backend(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        owner.action = lambda: "bypass"
        await send({"type": "http.response.body", "body": b"not-authorized", "more_body": False})

    async def execute():
        await Phase9BASGIGuard(backend, authority=authority)(
            {"type": "http"}, None, _async_send(events)
        )
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        asyncio.run(execute())
    assert [event["type"] for event in events] == ["http.response.start"]


def test_asgi_stream_preserves_prefix_and_withholds_future_chunks():
    authority, owner = _authority()
    events = []
    failures = []

    async def backend(scope, receive, send):
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/event-stream; charset=utf-8")],
        })
        await send({"type": "http.response.body", "body": b"data: safe\n\n", "more_body": True})
        owner.action = lambda: "tampered"
        await send({"type": "http.response.body", "body": b"data: unsafe\n\n", "more_body": True})
        await send({"type": "http.response.body", "body": b"data: [DONE]\n\n", "more_body": False})

    async def execute():
        await Phase9BASGIGuard(
            backend, authority=authority, note_stream_failure=failures.append,
        )(
            {"type": "http"}, None, _async_send(events)
        )
    asyncio.run(execute())
    assert len(failures) == 1
    assert isinstance(failures[0], RuntimeCodeIntegrityCompromised)
    bodies = [event["body"] for event in events if event["type"] == "http.response.body"]
    assert bodies == [b"data: safe\n\n", b""]
    assert b"unsafe" not in b"".join(bodies)
    assert authority.state == "INVALIDATED"


def test_asgi_stream_does_not_emit_fake_success_after_tampering():
    authority, owner = _authority()
    events = []

    async def backend(scope, receive, send):
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/event-stream")],
        })
        owner.action = lambda: 1
        await send({"type": "http.response.body", "body": b"data: [DONE]\n\n", "more_body": False})

    async def execute():
        await Phase9BASGIGuard(backend, authority=authority)(
            {"type": "http"}, None, _async_send(events)
        )
    asyncio.run(execute())
    assert events[-1]["body"] == b""
    assert b"[DONE]" not in b"".join(e.get("body", b"") for e in events)


def test_asgi_non_http_passes_through():
    authority, owner = _authority()
    events = []

    async def backend(scope, receive, send):
        await send({"type": "websocket.close", "code": 1000})

    owner.action = lambda: "tampered"
    async def execute():
        await Phase9BASGIGuard(backend, authority=authority)(
            {"type": "websocket"}, None, _async_send(events)
        )
    asyncio.run(execute())
    assert events == [{"type": "websocket.close", "code": 1000}]


def _integrated_host(tmp_path: Path):
    target = tmp_path / "host_authority.py"
    target.write_text("# selected host source\n", encoding="utf-8")
    source = phase8.RuntimeSourceAuthority(runtime_id="p9-real", lane_id="lane-one")
    source.register_component("host_authority.py", target)
    source.seal()

    async def run(_body):
        return {"verified": True}

    async def stream(_body):
        yield b"data: safe\n\n"

    def release(_calls):
        return [], []

    def admit(_payload, **_kwargs):
        return {"allowed": True}

    async def pi(_request, _method, _path, **_kwargs):
        return {"ok": True}

    app = FastAPI()
    host = SimpleNamespace(
        APP=app, KERNEL=SimpleNamespace(run=run, stream=stream),
        _phase4_partition_structured_tool_calls=release,
        _phase4_executor_admission_decision=admit,
        _debugging_report_only_tool_surface=lambda tools, choice: (tools, choice),
        _debugging_tool_is_direct_mutator=lambda _tool: False,
        _proxy_pi_control_request=pi,
        _JACK_SOURCE_AUTHORITY=source,
        _JACK_SOURCE_RUNTIME_ENFORCEMENT_INSTALLED=True,
        ORCHESTRATION_BASE_PATH="/jack/orchestration",
        enforce_kernel_auth=lambda _request: True,
        sanitize_agent_request=lambda body: body,
        _phase4_executor_context_from_request=lambda _request: None,
        _safe_public_stream=lambda _body: None,
        completion_envelope=lambda value: value,
        recover_pi_tool_evidence=lambda call_id, _sha=None: {"result": call_id},
        _project_tool_evidence_release=lambda evidence: evidence,
    )
    calls = {"run": 0, "executor": 0, "control": 0}

    @app.get("/")
    async def status():
        return {"ready": True}

    @app.post("/v1/chat/completions")
    async def chat():
        calls["run"] += 1
        return await host.KERNEL.run({})

    @app.post("/v1/responses")
    async def responses():
        return await host.KERNEL.run({})

    @app.get("/jack/tool-evidence/{tool_call_id}")
    async def evidence(tool_call_id: str):
        return host._project_tool_evidence_release(host.recover_pi_tool_evidence(tool_call_id))

    @app.post("/jack/security/path-admission")
    async def executor():
        calls["executor"] += 1
        return host._phase4_executor_admission_decision({})

    @app.post("/jack/orchestration/tasks")
    async def tasks():
        calls["control"] += 1
        return await host._proxy_pi_control_request(None, "POST", "/v1/tasks")

    @app.post("/jack/orchestration/tasks/cancel")
    async def cancel():
        return await host._proxy_pi_control_request(None, "POST", "/v1/tasks/cancel")

    @app.post("/jack/orchestration/session/new")
    async def new():
        return await host._proxy_pi_control_request(None, "POST", "/v1/session/new")

    return host, calls


def test_integrated_fastapi_blocks_rebound_run_before_dispatch(tmp_path):
    host, calls = _integrated_host(tmp_path)
    authority = install(host)
    with TestClient(host.APP) as client:
        response = client.post("/v1/chat/completions")
        assert response.status_code == 200, authority.mismatched_slots
        assert response.json() == {"verified": True}
        async def bypass(_body):
            return {"untrusted": "bypass"}
        host.KERNEL.run = bypass
        response = client.post("/v1/chat/completions")
        assert response.status_code == 503
        assert response.json() == {"error": "jack_runtime_code_integrity_unavailable"}
    assert calls["run"] == 1
    assert authority.mismatched_slots == ("kernel-run",)


def test_integrated_fastapi_blocks_bypassed_executor_before_dispatch(tmp_path):
    host, calls = _integrated_host(tmp_path)
    install(host)
    with TestClient(host.APP) as client:
        assert client.post("/jack/security/path-admission").status_code == 200, host._JACK_RUNTIME_CODE_AUTHORITY.mismatched_slots
        host._phase4_executor_admission_decision = lambda _body: {"allowed": "ANY"}
        assert client.post("/jack/security/path-admission").status_code == 503
    assert calls["executor"] == 1


def test_integrated_fastapi_blocks_bypassed_pi_control_before_dispatch(tmp_path):
    host, calls = _integrated_host(tmp_path)
    install(host)
    with TestClient(host.APP) as client:
        assert client.post("/jack/orchestration/tasks").status_code == 200, host._JACK_RUNTIME_CODE_AUTHORITY.mismatched_slots
        async def bypass(*_args, **_kwargs):
            return {"unsafe": True}
        host._proxy_pi_control_request = bypass
        assert client.post("/jack/orchestration/tasks").status_code == 503
    assert calls["control"] == 1


def test_integrated_fastapi_route_endpoint_replacement_is_blocked(tmp_path):
    host, calls = _integrated_host(tmp_path)
    install(host)
    route = next(x for x in host.APP.routes if getattr(x, "path", None) == "/v1/chat/completions")
    route.endpoint = lambda: {"unsafe": True}
    with TestClient(host.APP) as client:
        assert client.post("/v1/chat/completions").status_code == 503
    assert calls["run"] == 0


def test_integrated_fastapi_route_table_extension_is_blocked(tmp_path):
    host, _calls = _integrated_host(tmp_path)
    install(host)

    @host.APP.get("/unprotected-extra")
    async def extra():
        return {"unsafe": True}

    with TestClient(host.APP) as client:
        assert client.get("/unprotected-extra").status_code == 503


def test_secure_install_requires_phase8_and_empty_middleware_stack(tmp_path):
    host, _calls = _integrated_host(tmp_path)
    host._JACK_SOURCE_RUNTIME_ENFORCEMENT_INSTALLED = False
    from jack_runtime_code_guard import RuntimeCodeIntegrityUnavailable
    with pytest.raises(RuntimeCodeIntegrityUnavailable):
        install(host)


def test_secure_install_refuses_required_route_absence(tmp_path):
    host, _calls = _integrated_host(tmp_path)
    host.APP.router.routes = [
        route for route in host.APP.router.routes
        if getattr(route, "path", None) != "/v1/responses"
    ]
    from jack_runtime_code_guard import RuntimeCodeIntegrityUnavailable
    with pytest.raises(RuntimeCodeIntegrityUnavailable):
        install(host)


def test_model_request_survives_independent_executor_integrity_failure(tmp_path):
    host, calls = _integrated_host(tmp_path)
    guard = install(host)
    with TestClient(host.APP) as client:
        host._phase4_executor_admission_decision = (
            lambda _body: {"allowed": "untrusted"}
        )
        assert client.post("/jack/security/path-admission").status_code == 503
        result = client.post("/v1/chat/completions")
        assert result.status_code == 200, (result.text, guard.mismatched_slots)
        assert result.json() == {"verified": True}
    assert calls["run"] == 1
    assert calls["executor"] == 0


def test_executor_and_pi_requests_survive_independent_model_compromise(tmp_path):
    host, calls = _integrated_host(tmp_path)
    guard = install(host)
    with TestClient(host.APP) as client:
        async def bypass(_body):
            return {"untrusted": "must not release"}
        host.KERNEL.run = bypass
        assert client.post("/v1/chat/completions").status_code == 503
        executor = client.post("/jack/security/path-admission")
        # Starting a new Pi task depends on the compromised model authority.
        # Cancelling a preexisting task should remain possible through the
        # intact authenticated Pi bridge; it does not create new model work.
        control = client.post("/jack/orchestration/tasks")
        cancel = client.post("/jack/orchestration/tasks/cancel")
        assert executor.status_code == 200, (executor.text, guard.mismatched_slots)
        assert executor.json() == {"allowed": True}
        assert control.status_code == 503
        assert cancel.status_code == 200, (cancel.text, guard.mismatched_slots)
        assert cancel.json() == {"ok": True}
    assert calls == {"run": 0, "executor": 1, "control": 0}


def test_compromised_executor_prevents_new_pi_task_but_preserves_cancellation(tmp_path):
    host, calls = _integrated_host(tmp_path)
    guard = install(host)
    with TestClient(host.APP) as client:
        host._phase4_executor_admission_decision = lambda _payload: {"allowed": "ANY"}
        assert client.post("/jack/security/path-admission").status_code == 503
        assert client.post("/jack/orchestration/tasks").status_code == 503
        cancel = client.post("/jack/orchestration/tasks/cancel")
        assert cancel.status_code == 200, (cancel.text, guard.mismatched_slots)
    assert calls["control"] == 0


def test_compromised_shared_path_authority_prevents_even_read_only_public_release(tmp_path, monkeypatch):
    import jack_path_policy
    host, _calls = _integrated_host(tmp_path)
    guard = install(host)
    monkeypatch.setattr(jack_path_policy, "authorize_executor_tool_call", lambda *_a, **_k: None)
    with TestClient(host.APP) as client:
        # Protecting a common authorization authority takes precedence over
        # ordinary status availability, unlike an isolated model failure.
        result = client.post("/jack/security/path-admission")
        assert result.status_code == 503, (result.text, guard.mismatched_slots)
        assert client.get("/").status_code == 503


def test_compromised_pi_proxy_blocks_pi_read_only_status(tmp_path):
    from jack_phase9b_enforcement import _http_authority_scopes
    host, _calls = _integrated_host(tmp_path)
    guard = install(host)
    assert _http_authority_scopes({
        "type": "http", "method": "GET", "path": "/jack/orchestration/status"
    }) == ("orchestration", "authority")
    async def bypass(*_a, **_k):
        return {"unsafe": True}
    host._proxy_pi_control_request = bypass
    async def read_pi_status():
        return await host._proxy_pi_control_request(None, "GET", "/v1/status")
    # This read depends on the Pi bridge; unlike independent status, it does
    # not gain a read-only exception once that bridge is compromised.
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify_for(*_http_authority_scopes({
            "type": "http", "method": "GET", "path": "/jack/orchestration/status"
        }))
    assert guard.state == "INVALIDATED"


def test_model_tool_release_requires_intact_executor_admission(tmp_path):
    host, _calls = _integrated_host(tmp_path)
    guard = install(host)
    host._phase4_executor_admission_decision = lambda _payload: {"allowed": "bypass"}
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        host._phase4_partition_structured_tool_calls([])
    assert guard.state == "INVALIDATED"


def test_stream_integrity_failure_closes_predecessor_without_draining(tmp_path):
    emitted = []
    terminated = []

    async def controlled_stream(_body):
        try:
            emitted.append("safe")
            yield b"safe"
            emitted.append("untrusted")
            yield b"not-safe"
            emitted.append("must-not-execute")
            yield b"untrusted-followup"
        finally:
            terminated.append("closed")

    # Install a fresh host with the controlled stream before the guard seals.
    host2, _ = _integrated_host(tmp_path)
    host2.KERNEL.stream = controlled_stream
    guard2 = install(host2)

    async def simulate():
        it = host2.KERNEL.stream({})
        first = await anext(it)
        assert first == b"safe"
        host2.KERNEL.run = lambda _body: {"untrusted": "code-rebound"}
        with pytest.raises(RuntimeCodeIntegrityCompromised):
            await anext(it)

    asyncio.run(simulate())
    assert emitted == ["safe", "untrusted"]
    assert terminated == ["closed"]
    assert guard2.state == "INVALIDATED"


def test_route_classification_monkeypatch_cannot_bypass_model_authority(tmp_path, monkeypatch):
    import jack_phase9b_enforcement as phase9
    host, calls = _integrated_host(tmp_path)
    guard = install(host)

    # Attacker attempts to bless a model endpoint as mere observation.
    monkeypatch.setattr(
        phase9, "_http_authority_scopes", lambda _scope: ("observation",)
    )
    with TestClient(host.APP) as client:
        rejected = client.post("/v1/chat/completions")
        assert rejected.status_code == 503, (rejected.text, guard.mismatched_slots)
    assert "p9-route-classifier" in guard.mismatched_slots
    assert calls["run"] == 0


def test_verifier_check_rebinding_is_a_shared_integrity_violation(tmp_path, monkeypatch):
    from jack_runtime_code_guard import RuntimeCodeAuthority
    host, calls = _integrated_host(tmp_path)
    guard = install(host)
    monkeypatch.setattr(
        RuntimeCodeAuthority, "_check_locked", lambda self, **_kw: None
    )
    with TestClient(host.APP) as client:
        rejected = client.post("/v1/chat/completions")
        assert rejected.status_code == 503, (rejected.text, guard.mismatched_slots)
    assert "p9-check" in guard.mismatched_slots
    assert calls["run"] == 0


def test_read_only_exception_set_cannot_be_expanded_after_sealing(monkeypatch):
    import jack_phase9b_enforcement as phase9
    monkeypatch.setattr(
        phase9, "OBSERVATION_PATHS",
        frozenset({"/jack/orchestration/events", "/v1/chat/completions"}),
    )
    assert phase9._http_authority_scopes({
        "type": "http", "method": "GET",
        "path": "/jack/orchestration/events",
    }) == ("orchestration", "authority")
    assert phase9._http_authority_scopes({
        "type": "http", "method": "POST",
        "path": "/v1/chat/completions",
    }) == ("model", "authority")


def test_monkeypatched_http_authentication_blocks_all_protected_http(tmp_path):
    host, calls = _integrated_host(tmp_path)
    guard = install(host)
    host.enforce_kernel_auth = lambda _request: None
    with TestClient(host.APP) as client:
        assert client.get("/").status_code == 503
        assert client.post("/v1/chat/completions").status_code == 503
    assert guard.state == "INVALIDATED"
    assert "http-auth" in guard.mismatched_slots
    assert calls["run"] == 0


def test_model_sanitizer_rebinding_denies_model_but_preserves_verified_observation(tmp_path):
    host, calls = _integrated_host(tmp_path)
    guard = install(host)
    host.sanitize_agent_request = lambda body: {"unsafe": True}
    with TestClient(host.APP) as client:
        assert client.post("/v1/chat/completions").status_code == 503
        result = client.get("/")
        assert result.status_code == 200
        assert result.json() == {"ready": True}
    assert guard.state == "INVALIDATED"
    assert calls["run"] == 0


def test_mandatory_phase9_install_seals_new_guard_and_enforcement_source(tmp_path):
    host, _calls = _integrated_host(tmp_path)
    authority = install(host)
    expected = {"source-phase9-code-guard", "source-phase9-enforcement"}
    observed = {entry.label for entry in authority._sources}
    assert expected.issubset(observed)
    authority.verify_for("model")
    authority.verify_for("observation")


def test_tool_evidence_route_and_release_authority_are_pinned(tmp_path):
    host, _ = _integrated_host(tmp_path)
    install(host)
    with TestClient(host.APP) as client:
        assert client.get("/jack/tool-evidence/call-1").json() == {"result": "call-1"}
        host._project_tool_evidence_release = lambda evidence: {"result": "untrusted"}
        blocked = client.get("/jack/tool-evidence/call-1")
        assert blocked.status_code == 503
        assert "untrusted" not in blocked.text
        assert client.get("/").status_code == 200

    host, _ = _integrated_host(tmp_path)
    install(host)
    route = next(r for r in host.APP.routes if r.path == "/jack/tool-evidence/{tool_call_id}")
    async def bypass(tool_call_id: str):
        return {"result": "untrusted"}
    route.dependant.call = bypass
    with TestClient(host.APP) as client:
        blocked = client.get("/jack/tool-evidence/call-1")
        assert blocked.status_code == 503
        assert "untrusted" not in blocked.text


@pytest.mark.parametrize("path", [
    "/jack/orchestration/status", "/jack/orchestration/events",
    "/health", "/v1/models", "/api/v1/models",
])
def test_authority_bearing_get_routes_are_pinned(tmp_path, path):
    host, _calls = _integrated_host(tmp_path)

    @host.APP.get(path)
    async def read():
        return {"verified": True}

    guard = install(host)
    route = next(r for r in host.APP.routes if getattr(r, "path", None) == path)
    with TestClient(host.APP) as client:
        assert client.get(path).status_code == 200, guard.mismatched_slots
        route.dependant.call = lambda: {"unverified": True}
        assert client.get(path).status_code == 503
        assert client.get("/").status_code == 200


def test_source_status_and_passive_lifecycle_do_not_depend_on_model_execution(tmp_path):
    import jack_phase9b_enforcement as phase9
    host, calls = _integrated_host(tmp_path)

    @host.APP.get("/jack/source-authority")
    async def source_status():
        return {"observed": True}

    @host.APP.post("/jack/tool-lifecycle/observe")
    async def lifecycle():
        return {"accepted": True}

    guard = install(host)
    assert phase9._http_authority_scopes({
        "method": "GET", "path": "/jack/source-authority",
    }) == ("observation",)
    assert phase9._http_authority_scopes({
        "method": "POST", "path": "/jack/tool-lifecycle/observe",
    }) == ("observation", "authority")
    host.sanitize_agent_request = lambda body: {"unsafe": True}
    with TestClient(host.APP) as client:
        assert client.post("/v1/chat/completions").status_code == 503
        assert client.get("/jack/source-authority").status_code == 200
        assert client.post("/jack/tool-lifecycle/observe").status_code == 200
        host.enforce_kernel_auth = lambda _request: None
        assert client.get("/jack/source-authority").status_code == 503
        assert client.post("/jack/tool-lifecycle/observe").status_code == 503
    assert calls["run"] == 0


@pytest.mark.parametrize("path,method", [
    ("/jack/source-authority", "GET"),
    ("/jack/tool-lifecycle/observe", "POST"),
])
def test_diagnostic_route_binding_remains_sealed(tmp_path, path, method):
    host, _calls = _integrated_host(tmp_path)

    async def original():
        return {"verified": True}

    host.APP.add_api_route(path, original, methods=[method])
    guard = install(host)
    route = next(r for r in host.APP.routes if getattr(r, "path", None) == path)
    route.endpoint = lambda: {"untrusted": True}
    with TestClient(host.APP) as client:
        assert client.request(method, path).status_code == 503
