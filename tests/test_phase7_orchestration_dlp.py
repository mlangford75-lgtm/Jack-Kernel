from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

SRC = Path(__file__).resolve().parents[1] / "jack_kernel.py"


def load_module(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_API_KEY", "phase7-orch-jack-secret-12345")
    monkeypatch.setenv("JACK_BACKEND_API_KEY", "phase7-orch-backend-secret-67890")
    monkeypatch.setenv("JACK_BACKEND_AUTH_MODE", "bearer")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "custom")
    monkeypatch.setenv("JACK_CANARY_POLICY_JSON", "")
    monkeypatch.setenv("JACK_AUTHORITY_LEDGER_DIR", str(tmp_path / "ledger"))
    name = f"jack_phase7_orch_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeBackendClient:
    async def post(self, *args, **kwargs):
        return "posted"

    def build_request(self, *args, **kwargs):
        return "request"

    async def aclose(self):
        return None


def install_phase7(m):
    m.BACKEND._client = FakeBackendClient()
    m._install_bundled_runtime_extensions()
    assert m._JACK_CREDENTIAL_GUARD_INSTALLED is True
    assert m._JACK_ORCHESTRATION_CREDENTIAL_DLP_INSTALLED is True


def close_ledger(m):
    ledger = getattr(m, "_JACK_AUTHORITY_LEDGER", None)
    if ledger is not None:
        ledger.close()


def test_orchestration_http_release_blocks_exact_credential_without_worker_side_effect(monkeypatch, tmp_path):
    m = load_module(monkeypatch, tmp_path)
    secret = m.CFG.api_key
    calls = {"count": 0}

    async def original_proxy(*args, **kwargs):
        calls["count"] += 1
        return m.Response(
            content=json.dumps({"status": "running", "message": "safe-" + secret}),
            status_code=200,
            media_type="application/json",
        )

    m._proxy_pi_control_request = original_proxy
    install_phase7(m)

    async def run():
        response = await m._proxy_pi_control_request(None, "GET", "/v1/status")
        assert response.status_code == 502
        body = json.loads(response.body.decode("utf-8"))
        assert body == {
            "error": "orchestration_credential_release_blocked",
            "security_outcome": "HARD_INTERRUPT",
            "release_boundary": "orchestration_http_release",
        }
        assert secret not in response.body.decode("utf-8")
        # The downstream orchestration operation completed once. Release blocking
        # does not manufacture worker cancellation, failure, or settlement.
        assert calls["count"] == 1

    asyncio.run(run())
    close_ledger(m)


def test_orchestration_http_clean_response_is_preserved(monkeypatch, tmp_path):
    m = load_module(monkeypatch, tmp_path)

    async def original_proxy(*args, **kwargs):
        return m.Response(
            content=json.dumps({"status": "running", "runOpen": True}),
            status_code=200,
            media_type="application/json",
        )

    m._proxy_pi_control_request = original_proxy
    install_phase7(m)

    async def run():
        response = await m._proxy_pi_control_request(None, "GET", "/v1/status")
        assert response.status_code == 200
        assert json.loads(response.body.decode("utf-8")) == {
            "status": "running",
            "runOpen": True,
        }

    asyncio.run(run())
    close_ledger(m)


def test_orchestration_sse_leak_is_replaced_before_replay_and_later_events_continue(monkeypatch, tmp_path):
    m = load_module(monkeypatch, tmp_path)
    install_phase7(m)
    secret = m.CFG.api_key

    async def run():
        hub = m.OrchestrationEventHub(replay_limit=8)
        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        await hub._publish(
            "message_end",
            {
                "type": "message_end",
                "task_id": task_id,
                "run_id": run_id,
                "run_epoch": 1,
                "attribution": "pi_run_bound",
                "data": {
                    "message": {
                        "role": "assistant",
                        "content": "safe-prefix-" + secret + "-unsafe-tail",
                    }
                },
                "at": "2026-10-04T19:05:00.000Z",
            },
        )
        await hub._publish(
            "task",
            {
                "type": "task",
                "task_id": task_id,
                "run_id": run_id,
                "run_epoch": 1,
                "attribution": "task_state",
                "data": {
                    "id": task_id,
                    "status": "running",
                    "runId": run_id,
                    "runEpoch": 1,
                    "runOpen": True,
                },
                "at": "2026-10-04T19:05:00.100Z",
            },
        )

        events = list(hub._buffer)
        assert len(events) == 2
        blocked, later = events
        assert blocked["seq"] == 1
        assert blocked["type"] == "orchestration_credential_release_blocked"
        assert blocked["task_id"] == task_id
        assert blocked["run_id"] == run_id
        assert blocked["run_epoch"] == 1
        assert blocked["attribution"] == "pi_run_bound"
        assert blocked["data"] == {
            "error": "orchestration_credential_release_blocked",
            "security_outcome": "HARD_INTERRUPT",
            "release_boundary": "orchestration_event_release",
        }
        encoded = hub._encode_sse(blocked)
        assert secret.encode("utf-8") not in encoded
        assert secret not in json.dumps(blocked)

        # The worker's next independently safe lifecycle event still enters the
        # observer stream. The release violation did not cancel or settle it.
        assert later["seq"] == 2
        assert later["type"] == "task"
        assert later["data"]["status"] == "running"
        assert later["data"]["runOpen"] is True

        queue, replay = await hub.subscribe(0)
        try:
            replay_bytes = b"".join(replay)
            assert secret.encode("utf-8") not in replay_bytes
            assert b"orchestration_credential_release_blocked" in replay_bytes
            assert b'"status": "running"' in replay_bytes
        finally:
            await hub.unsubscribe(queue)

    asyncio.run(run())
    close_ledger(m)


def test_orchestration_sse_safe_identity_is_not_preserved_when_identity_itself_contains_secret(monkeypatch, tmp_path):
    m = load_module(monkeypatch, tmp_path)
    install_phase7(m)
    secret = m.CFG.api_key

    async def run():
        hub = m.OrchestrationEventHub(replay_limit=8)
        await hub._publish(
            "message",
            {
                "type": "message",
                "task_id": "task-" + secret,
                "run_id": "run-safe",
                "run_epoch": 3,
                "attribution": "pi_run_bound",
                "data": {"delta": secret},
                "at": "2026-10-04T19:05:01.000Z",
            },
        )
        event = list(hub._buffer)[0]
        assert event["task_id"] is None
        assert event["run_id"] == "run-safe"
        assert event["run_epoch"] == 3
        assert secret not in json.dumps(event)

    asyncio.run(run())
    close_ledger(m)


def test_orchestration_unregistered_secret_like_text_remains_usable(monkeypatch, tmp_path):
    m = load_module(monkeypatch, tmp_path)
    install_phase7(m)
    benign = "sk-not-registered eyJ.fake.jwt highEntropyLooking1234567890"

    async def run():
        hub = m.OrchestrationEventHub(replay_limit=8)
        await hub._publish(
            "message",
            {
                "type": "message",
                "task_id": "task-safe",
                "run_id": "run-safe",
                "run_epoch": 1,
                "attribution": "pi_run_bound",
                "data": {"delta": benign},
                "at": "2026-10-04T19:05:02.000Z",
            },
        )
        event = list(hub._buffer)[0]
        assert event["type"] == "message"
        assert event["data"]["delta"] == benign

    asyncio.run(run())
    close_ledger(m)
