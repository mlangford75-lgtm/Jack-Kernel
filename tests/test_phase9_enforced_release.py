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
        await Phase9BASGIGuard(backend, authority=authority)(
            {"type": "http"}, None, _async_send(events)
        )
    asyncio.run(execute())
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
        _proxy_pi_control_request=pi,
        _JACK_SOURCE_AUTHORITY=source,
        _JACK_SOURCE_RUNTIME_ENFORCEMENT_INSTALLED=True,
        ORCHESTRATION_BASE_PATH="/jack/orchestration",
    )
    calls = {"run": 0, "executor": 0, "control": 0}

    @app.post("/v1/chat/completions")
    async def chat():
        calls["run"] += 1
        return await host.KERNEL.run({})

    @app.post("/v1/responses")
    async def responses():
        return await host.KERNEL.run({})

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
