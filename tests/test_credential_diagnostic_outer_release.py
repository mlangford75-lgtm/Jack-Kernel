from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import uuid
from pathlib import Path

import jack_responses_compat as responses_compat

SRC = Path(__file__).resolve().parents[1] / "jack_kernel.py"


class FakeBackendClient:
    async def post(self, *args, **kwargs):
        return "posted"

    def build_request(self, *args, **kwargs):
        return "request"

    async def aclose(self):
        return None


def load_module(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_RUNTIME_ID", "phase7-diagnostic-outer-runtime")
    monkeypatch.setenv("JACK_LANE_ID", "phase7-diagnostic-outer-lane")
    monkeypatch.setenv("JACK_API_KEY", "phase7-diagnostic-outer-secret-12345")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "custom")
    monkeypatch.setenv("JACK_CANARY_POLICY_JSON", "")
    monkeypatch.setenv("JACK_AUTHORITY_LEDGER_DIR", str(tmp_path / "ledger"))
    name = f"jack_phase7_diag_outer_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def close_ledger(m):
    ledger = getattr(m, "_JACK_AUTHORITY_LEDGER", None)
    if ledger is not None:
        ledger.close()


def install_with_secret_stream(m):
    secret = m.CFG.api_key

    async def secret_stream(_body, *args, **kwargs):
        if False:
            yield b""
        raise m.HTTPException(
            status_code=502,
            detail="raw backend stream diagnostic " + secret,
        )

    m.KERNEL.stream = secret_stream
    m.BACKEND._client = FakeBackendClient()
    m._install_bundled_runtime_extensions()
    assert m._JACK_DIAGNOSTIC_CREDENTIAL_DLP_INSTALLED is True
    return secret


def test_chat_completions_public_sse_sees_only_sanitized_stream_exception(monkeypatch, tmp_path):
    m = load_module(monkeypatch, tmp_path)
    secret = install_with_secret_stream(m)

    async def run():
        chunks = [chunk async for chunk in m._safe_public_stream({"messages": []})]
        released = b"".join(chunks).decode("utf-8")
        assert secret not in released
        assert "raw backend stream diagnostic" not in released
        assert "protected_credential_diagnostic_withheld" in released
        assert "diagnostic_stream_exception_release" in released
        assert released.endswith("data: [DONE]\n\n")

    asyncio.run(run())
    close_ledger(m)


def test_responses_stream_failure_sees_only_sanitized_kernel_exception(monkeypatch, tmp_path):
    m = load_module(monkeypatch, tmp_path)
    secret = install_with_secret_stream(m)

    async def run():
        frames = [
            frame
            async for frame in responses_compat._stream(
                m,
                {"messages": [], "stream": True},
                {},
            )
        ]
        released = b"".join(frames).decode("utf-8")
        assert secret not in released
        assert "raw backend stream diagnostic" not in released
        assert "protected_credential_diagnostic_withheld" in released
        assert "diagnostic_stream_exception_release" in released

        payloads = [
            json.loads(line[6:])
            for line in released.splitlines()
            if line.startswith("data: ")
        ]
        failed = [payload for payload in payloads if payload.get("type") == "response.failed"]
        assert len(failed) == 1
        message = failed[0]["error"]["message"]
        assert secret not in message
        assert "protected_credential_diagnostic_withheld" in message

    asyncio.run(run())
    close_ledger(m)
