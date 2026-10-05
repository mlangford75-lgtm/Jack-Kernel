from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_phase7_live_ledger_hooks_cover_enforcement_domains(tmp_path):
    code = r'''
import asyncio
import json
import logging

import httpx
import jack_kernel as kernel


SECRET = kernel.CFG.api_key


class FakeClient:
    async def post(self, url, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": "safe"}}], "usage": {}},
        )

    def build_request(self, method, url, **kwargs):
        return httpx.Request(method, url, **kwargs)

    async def send(self, request, *, stream=False):
        return httpx.Response(200, request=request, content=b"data: [DONE]\n\n")

    async def get(self, url, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={"data": [{"id": "test-model"}]},
        )

    async def aclose(self):
        return None


async def secret_result(*args, **kwargs):
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "safe-prefix-" + SECRET + "-unsafe-tail",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {},
    }


async def leaking_proxy(*args, **kwargs):
    return kernel.Response(
        content=json.dumps({"status": "running", "message": "observer-" + SECRET}),
        status_code=200,
        media_type="application/json",
    )


kernel.BACKEND._client = FakeClient()
kernel.BACKEND._resolved_model = "test-model"
kernel.BACKEND._model_metadata_checked = True
kernel.KERNEL.run = secret_result
kernel._proxy_pi_control_request = leaking_proxy
kernel._install_bundled_runtime_extensions()

ledger = kernel._JACK_AUTHORITY_LEDGER
assert kernel._JACK_PHASE7_LEDGER_INSTALLED is True


async def exercise():
    # Model-output release: existing StreamingIRQ owns disposition; the Phase-7
    # ledger extension observes the credential-derived Tier-A interrupt.
    try:
        await kernel.KERNEL.run({"messages": [{"role": "user", "content": "hello"}]})
    except Exception:
        pass
    else:
        raise AssertionError("expected credential-derived output release interrupt")

    # Public orchestration HTTP release.
    response = await kernel._proxy_pi_control_request(None, "GET", "/v1/status")
    assert response.status_code == 502
    assert SECRET not in response.body.decode("utf-8")

    # Replayable orchestration event release.
    hub = kernel.OrchestrationEventHub(replay_limit=8)
    await hub._publish(
        "message_end",
        {
            "type": "message_end",
            "task_id": "task-ledger",
            "run_id": "run-ledger",
            "run_epoch": 1,
            "attribution": "pi_run_bound",
            "data": {"message": {"content": "event-" + SECRET}},
            "at": "2026-10-05T00:00:00Z",
        },
    )
    assert list(hub._buffer)[-1]["type"] == "orchestration_credential_release_blocked"

    # HTTP diagnostic release. The original exception truth can contain the
    # credential, but the installed handler emits structural safe output.
    handler = kernel.APP.exception_handlers[kernel.HTTPException]
    released = await handler(
        None,
        kernel.HTTPException(status_code=502, detail="diagnostic-" + SECRET),
    )
    assert SECRET not in released.body.decode("utf-8")

    # Retained diagnostic state records the raw match before the diagnostic
    # guard stores only its structural placeholder.
    hub._last_error = "retained-" + SECRET
    assert hub._last_error == "protected credential diagnostic withheld"


asyncio.run(exercise())

# Jack-owned process-global logging is a separate observer boundary.
old_level = kernel.LOG.level
kernel.LOG.setLevel(logging.INFO)
try:
    kernel.LOG.error("phase7 ledger log probe %s", SECRET)
finally:
    kernel.LOG.setLevel(old_level)

assert ledger.wait_for_projection(timeout=5.0)
records = [
    json.loads(path.read_text(encoding="utf-8"))
    for path in sorted(ledger.records_dir.glob("*.json"))
]
phase7 = [record for record in records if record["event_type"] == "PROTECTED_CREDENTIAL_MATCH"]
boundaries = {record["boundary"] for record in phase7}
required = {
    "model_output_release",
    "orchestration_http_release",
    "orchestration_event_release",
    "diagnostic_http_exception_release",
    "diagnostic_log_release",
    "diagnostic_internal_state",
}
assert required.issubset(boundaries), (required - boundaries, phase7)

serialized = "\n".join(json.dumps(record, sort_keys=True) for record in records)
for credential in kernel._JACK_RUNTIME_CREDENTIAL_POLICY.credentials:
    assert credential.value not in serialized

# Ledger observation never changes the underlying dispositions: each event
# remains an observation of a boundary that already blocked or sanitized release.
assert all(record["outcome"] == "HARD_INTERRUPT" for record in phase7)

ledger.close()
'''

    env = dict(os.environ)
    home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "APPDATA": str(appdata),
            "JACK_RUNTIME_ID": "phase7-ledger-hooks-runtime",
            "JACK_LANE_ID": "phase7-ledger-hooks-lane",
            "JACK_API_KEY": "phase7-ledger-hooks-jack-secret-12345",
            "JACK_BACKEND_API_KEY": "phase7-ledger-hooks-backend-secret-67890",
            "JACK_BACKEND_AUTH_MODE": "bearer",
            "JACK_BACKEND_MODEL": "test-model",
            "JACK_BACKEND_PROFILE": "custom",
            "JACK_REASONING_LEVEL": "off",
            "JACK_FORENSIC_ARCHIVE_MODE": "off",
            "JACK_CANARY_POLICY_JSON": "",
            "JACK_PATH_POLICY_JSON": "",
            "JACK_AUTHORITY_LEDGER_DIR": str(tmp_path / "ledger"),
        }
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
