from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException

import jack_credential_guard as credential_guard
import jack_diagnostic_guard as diagnostic_guard


def policy(secret: str):
    return credential_guard.RuntimeCredentialPolicy(
        runtime_id="runtime-diagnostic-header-test",
        lane_id="lane-diagnostic-header-test",
        credentials=(
            credential_guard.ProtectedCredential(
                credential_id="credential:test-header",
                credential_class=credential_guard.CredentialClass.JACK_API,
                source_kind="test",
                authorized_destinations=frozenset(),
                value=secret,
            ),
        ),
    )


def test_http_exception_secret_header_is_omitted_while_clean_header_survives():
    secret = "phase7-header-secret-12345"
    app = FastAPI()
    jk = SimpleNamespace(APP=app, HTTPException=HTTPException)
    assert diagnostic_guard._install_http_exception_guard(jk, policy(secret)) is True

    async def run():
        handler = app.exception_handlers[HTTPException]
        exc = HTTPException(
            status_code=429,
            detail="ordinary rate-limit diagnostic",
            headers={
                "X-Safe-Diagnostic": "retry-later",
                "X-Private-Diagnostic": "credential=" + secret,
            },
        )
        response = await handler(None, exc)
        body = json.loads(response.body.decode("utf-8"))
        assert response.status_code == 429
        assert secret not in response.body.decode("utf-8")
        assert response.headers["x-safe-diagnostic"] == "retry-later"
        assert "x-private-diagnostic" not in response.headers
        assert body == {
            "detail": {
                "error": "protected_credential_diagnostic_withheld",
                "security_outcome": "HARD_INTERRUPT",
                "release_boundary": "diagnostic_http_exception_release",
            }
        }

    asyncio.run(run())


def test_clean_http_exception_headers_and_detail_are_preserved():
    app = FastAPI()
    jk = SimpleNamespace(APP=app, HTTPException=HTTPException)
    assert diagnostic_guard._install_http_exception_guard(
        jk,
        policy("phase7-other-secret-67890"),
    ) is True

    async def run():
        handler = app.exception_handlers[HTTPException]
        exc = HTTPException(
            status_code=409,
            detail="ordinary conflict",
            headers={"X-Safe-Diagnostic": "kept"},
        )
        response = await handler(None, exc)
        assert response.status_code == 409
        assert response.headers["x-safe-diagnostic"] == "kept"
        assert json.loads(response.body.decode("utf-8")) == {
            "detail": "ordinary conflict"
        }

    asyncio.run(run())
