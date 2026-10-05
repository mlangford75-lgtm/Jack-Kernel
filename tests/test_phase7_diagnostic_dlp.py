from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import logging
import sys
import uuid
from pathlib import Path

import httpx

SRC = Path(__file__).resolve().parents[1] / "jack_kernel.py"


def load_module(
    monkeypatch,
    tmp_path,
    *,
    runtime_id="phase7-diagnostic-runtime-default",
    lane_id="phase7-diagnostic-lane-default",
    jack_secret="phase7-diagnostic-jack-secret-12345",
    backend_secret="phase7-diagnostic-backend-secret-67890",
):
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_RUNTIME_ID", runtime_id)
    monkeypatch.setenv("JACK_LANE_ID", lane_id)
    monkeypatch.setenv("JACK_API_KEY", jack_secret)
    monkeypatch.setenv("JACK_BACKEND_API_KEY", backend_secret)
    monkeypatch.setenv("JACK_BACKEND_AUTH_MODE", "bearer")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "custom")
    monkeypatch.setenv("JACK_CANARY_POLICY_JSON", "")
    monkeypatch.setenv("JACK_AUTHORITY_LEDGER_DIR", str(tmp_path / runtime_id / "ledger"))
    name = f"jack_phase7_diag_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeBackendClient:
    def __init__(self, *, post_response=None):
        self.post_response = post_response
        self.post_calls = 0

    async def post(self, *args, **kwargs):
        self.post_calls += 1
        if isinstance(self.post_response, BaseException):
            raise self.post_response
        if self.post_response is not None:
            return self.post_response
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "usage": {}})

    def build_request(self, method, url, **kwargs):
        return httpx.Request(method, url, **kwargs)

    async def send(self, request, *, stream=False):
        if isinstance(self.post_response, BaseException):
            raise self.post_response
        if self.post_response is not None:
            return self.post_response
        return httpx.Response(
            200,
            request=request,
            content=b'data: {"choices":[{"index":0,"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
        )

    async def get(self, *args, **kwargs):
        return httpx.Response(200, json={"data": [{"id": "test-model"}]})

    async def aclose(self):
        return None


def install_phase7(m, *, client=None):
    m.BACKEND._client = client or FakeBackendClient()
    m.BACKEND._resolved_model = "test-model"
    m.BACKEND._model_metadata_checked = True
    m._install_bundled_runtime_extensions()
    assert m._JACK_CREDENTIAL_GUARD_INSTALLED is True
    assert m._JACK_DIAGNOSTIC_CREDENTIAL_DLP_INSTALLED is True
    assert "jack_diagnostic_guard.py" in m.RUNTIME_MANIFEST_COMPONENTS


def close_ledger(m):
    ledger = getattr(m, "_JACK_AUTHORITY_LEDGER", None)
    if ledger is not None:
        ledger.close()


def test_backend_error_truth_is_preserved_internally_but_http_release_is_structural(monkeypatch, tmp_path):
    m = load_module(monkeypatch, tmp_path)
    secret = m.CFG.backend_api_key
    response = httpx.Response(
        400,
        text="backend diagnostic carries " + secret + " and ordinary context",
        request=httpx.Request("POST", "http://backend.invalid/v1/chat/completions"),
    )
    install_phase7(m, client=FakeBackendClient(post_response=response))

    async def run():
        try:
            await m.BACKEND.chat(
                messages=[{"role": "user", "content": "hello"}],
                secondary_system="",
                profile=m.STAGES["thesis"],
            )
        except m.HTTPException as exc:
            # Backend truth is still precise inside the Kernel. Release authority
            # is exercised later by the installed HTTP exception handler.
            assert secret in str(exc.detail)
            handler = m.APP.exception_handlers[m.HTTPException]
            released = await handler(None, exc)
            body = json.loads(released.body.decode("utf-8"))
            assert released.status_code == 502
            assert secret not in released.body.decode("utf-8")
            assert body == {
                "detail": {
                    "error": "protected_credential_diagnostic_withheld",
                    "security_outcome": "HARD_INTERRUPT",
                    "release_boundary": "diagnostic_http_exception_release",
                }
            }
        else:
            raise AssertionError("expected backend rejection")

    asyncio.run(run())
    close_ledger(m)


def test_stream_exception_is_replaced_before_outer_public_stream_can_render_it(monkeypatch, tmp_path):
    m = load_module(monkeypatch, tmp_path)
    secret = m.CFG.api_key

    async def secret_stream(_body, *args, **kwargs):
        if False:
            yield b""
        raise m.HTTPException(status_code=502, detail="stream backend error " + secret)

    m.KERNEL.stream = secret_stream
    install_phase7(m)

    async def run():
        try:
            async for _ in m.KERNEL.stream({"messages": []}):
                pass
        except m.HTTPException as exc:
            text = str(exc.detail)
            assert secret not in text
            assert exc.detail == {
                "error": "protected_credential_diagnostic_withheld",
                "security_outcome": "HARD_INTERRUPT",
                "release_boundary": "diagnostic_stream_exception_release",
            }
            assert exc.__cause__ is None
        else:
            raise AssertionError("expected guarded stream failure")

    asyncio.run(run())
    close_ledger(m)


def test_log_guard_replaces_only_proven_credential_diagnostics(monkeypatch, tmp_path):
    m = load_module(monkeypatch, tmp_path)
    install_phase7(m)
    secret = m.CFG.api_key

    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
    m.LOG.addHandler(handler)
    old_level = m.LOG.level
    m.LOG.setLevel(logging.INFO)
    try:
        m.LOG.error("backend diagnostic safe-before %s unsafe-after", secret)
        first = buf.getvalue()
        assert secret not in first
        assert "Jack diagnostic withheld because it contained a protected runtime credential" in first
        assert "safe-before" not in first

        buf.seek(0)
        buf.truncate(0)
        benign = "sk-not-registered eyJ.fake.jwt highEntropyLooking1234567890"
        m.LOG.error("ordinary diagnostic %s", benign)
        second = buf.getvalue()
        assert "ordinary diagnostic " + benign in second
    finally:
        m.LOG.removeHandler(handler)
        m.LOG.setLevel(old_level)

    close_ledger(m)


def test_log_guard_discards_secret_bearing_exception_traceback(monkeypatch, tmp_path):
    m = load_module(monkeypatch, tmp_path)
    install_phase7(m)
    secret = m.CFG.backend_api_key

    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    m.LOG.addHandler(handler)
    old_level = m.LOG.level
    m.LOG.setLevel(logging.INFO)
    try:
        try:
            raise RuntimeError("transport exploded with " + secret)
        except RuntimeError:
            m.LOG.exception("backend transport failure")
        output = buf.getvalue()
        assert secret not in output
        assert "Traceback" not in output
        assert "Jack diagnostic withheld because it contained a protected runtime credential" in output
    finally:
        m.LOG.removeHandler(handler)
        m.LOG.setLevel(old_level)

    close_ledger(m)


def test_process_global_logger_aggregates_distinct_runtime_policies(monkeypatch, tmp_path):
    runtime_a = load_module(
        monkeypatch,
        tmp_path,
        runtime_id="phase7-diagnostic-runtime-a",
        lane_id="phase7-diagnostic-lane-a",
        jack_secret="phase7-runtime-a-secret-11111",
        backend_secret="phase7-runtime-a-backend-11111",
    )
    install_phase7(runtime_a)

    runtime_b = load_module(
        monkeypatch,
        tmp_path,
        runtime_id="phase7-diagnostic-runtime-b",
        lane_id="phase7-diagnostic-lane-b",
        jack_secret="phase7-runtime-b-secret-22222",
        backend_secret="phase7-runtime-b-backend-22222",
    )
    install_phase7(runtime_b)

    # Both modules resolve the same process-global named logger. Its observer DLP
    # must protect both immutable runtime policies without letting either runtime
    # replace or veto the other.
    assert runtime_a.LOG is runtime_b.LOG
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    runtime_a.LOG.addHandler(handler)
    old_level = runtime_a.LOG.level
    runtime_a.LOG.setLevel(logging.INFO)
    try:
        runtime_a.LOG.error("A diagnostic %s", runtime_a.CFG.api_key)
        runtime_b.LOG.error("B diagnostic %s", runtime_b.CFG.api_key)
        output = buf.getvalue()
        assert runtime_a.CFG.api_key not in output
        assert runtime_b.CFG.api_key not in output
        assert output.count(
            "Jack diagnostic withheld because it contained a protected runtime credential"
        ) == 2
    finally:
        runtime_a.LOG.removeHandler(handler)
        runtime_a.LOG.setLevel(old_level)

    close_ledger(runtime_a)
    close_ledger(runtime_b)


def test_retained_orchestration_error_state_never_keeps_registered_credential(monkeypatch, tmp_path):
    m = load_module(monkeypatch, tmp_path)
    install_phase7(m)
    secret = m.CFG.api_key
    hub = m.OrchestrationEventHub(replay_limit=8)

    hub._last_error = "Pi SSE diagnostic " + secret
    assert hub._last_error == "protected credential diagnostic withheld"

    benign = "ordinary connection reset by peer"
    hub._last_error = benign
    assert hub._last_error == benign
    close_ledger(m)


def test_safe_http_exception_detail_is_preserved_exactly(monkeypatch, tmp_path):
    m = load_module(monkeypatch, tmp_path)
    install_phase7(m)
    detail = {
        "error": "ordinary_backend_failure",
        "message": "backend unavailable but no registered credential",
    }

    async def run():
        handler = m.APP.exception_handlers[m.HTTPException]
        exc = m.HTTPException(status_code=503, detail=detail)
        released = await handler(None, exc)
        assert released.status_code == 503
        assert json.loads(released.body.decode("utf-8")) == {"detail": detail}

    asyncio.run(run())
    close_ledger(m)


def test_http_exception_diagnostic_key_containing_credential_is_withheld(monkeypatch, tmp_path):
    m = load_module(monkeypatch, tmp_path)
    install_phase7(m)
    secret = m.CFG.api_key

    async def run():
        handler = m.APP.exception_handlers[m.HTTPException]
        exc = m.HTTPException(
            status_code=502,
            detail={"diagnostic-" + secret: "ordinary-value"},
        )
        released = await handler(None, exc)
        text = released.body.decode("utf-8")
        assert secret not in text
        assert json.loads(text) == {
            "detail": {
                "error": "protected_credential_diagnostic_withheld",
                "security_outcome": "HARD_INTERRUPT",
                "release_boundary": "diagnostic_http_exception_release",
            }
        }

    asyncio.run(run())
    close_ledger(m)
