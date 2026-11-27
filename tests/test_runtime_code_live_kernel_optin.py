"""Phase 9B-C experimental secured Kernel + Phase 8 + ASGI integration.

Launches a fresh process to avoid cached module/router state from test order.
This qualifies the real loaded Kernel and secured composition without needing
a live backend or launching the interactive CLI. It is not yet a network
--serve child/production release qualification.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


_ROOT = Path(__file__).resolve().parents[1]


def _check_real_kernel(tmp_path, scenario: str) -> None:
    script = r'''
import asyncio
from pathlib import Path

import httpx
import jack_kernel as jk
import jack_source_drift_guard as source
import jack_runtime_code_enforcement as phase9

jk._install_bundled_runtime_extensions()
src = source.install(
    jk, launch_entrypoint_path=Path("jack_secure_entrypoint.py").resolve()
)
source.activate_runtime_enforcement(jk, src, start_periodic=False)
guard = phase9.install(jk)
assert guard is jk._JACK_RUNTIME_CODE_AUTHORITY
assert guard.state == "ACTIVE"
assert phase9.install(jk) is guard

async def probe():
    transport = httpx.ASGITransport(app=jk.APP)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://phase9-test.local"
    ) as client:
        normal = await client.get("/")
        assert normal.status_code == 200, (
            normal.status_code, normal.text, guard.mismatched_slots
        )
        admission = await client.post("/jack/security/path-admission", json={})
        # Missing tool_call_id is legitimately a client error, *not* an integrity
        # error; the request reaches Jack's real authenticated route handler.
        assert admission.status_code == 400, (
            admission.status_code, admission.text, guard.mismatched_slots
        )
        assert guard.state == "ACTIVE"
        if SCENARIO == "run_binding":
            async def bypass(_body):
                return "untrusted"
            jk.KERNEL.run = bypass
        elif SCENARIO == "executor_binding":
            jk._phase4_executor_admission_decision = lambda *_a, **_k: {
                "outcome": "ALLOW_ANY"
            }
        elif SCENARIO == "route_dispatch":
            route = next(
                r for r in jk.APP.routes
                if getattr(r, "path", None) == "/v1/chat/completions"
            )
            async def bypass_route(_request):
                return {"untrusted": True}
            route.dependant.call = bypass_route
        else:
            raise AssertionError("Unknown test scenario")
        # The affected consequence must be denied, while unrelated
        # read-only observation remains independently available.
        if SCENARIO == "executor_binding":
            rejected = await client.post("/jack/security/path-admission", json={})
        else:
            rejected = await client.post("/v1/chat/completions", json={})
        assert rejected.status_code == 503, (
            rejected.status_code, rejected.text, guard.mismatched_slots
        )
        assert rejected.json() == {
            "error": "jack_runtime_code_integrity_unavailable"
        }
        assert guard.state == "INVALIDATED"
        assert guard.mismatched_slots
        healthy = await client.get("/")
        assert healthy.status_code == 200, (
            healthy.status_code, healthy.text, guard.mismatched_slots
        )
        assert src.state is source.SourceAuthorityState.ACTIVE

SCENARIO = "__SCENARIO__"
try:
    asyncio.run(probe())
finally:
    jk._JACK_AUTHORITY_LEDGER.close()
'''
    script = script.replace("__SCENARIO__", scenario)
    env = dict(os.environ)
    env.update({
        "JACK_AUTHORITY_LEDGER_DIR": str(tmp_path / "ledger"),
        "JACK_FORENSIC_ARCHIVE_MODE": "off",
        "JACK_BACKEND_MODEL": "test-model",
        "JACK_BACKEND_PROFILE": "lmstudio",
    })
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=50,
        check=False,
    )
    assert result.returncode == 0, (
        f"scenario {scenario} returned {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_real_loaded_kernel_p9_blocks_run_rebinding(tmp_path):
    _check_real_kernel(tmp_path, "run_binding")


def test_real_loaded_kernel_p9_blocks_executor_rebinding(tmp_path):
    _check_real_kernel(tmp_path, "executor_binding")


def test_real_loaded_kernel_p9_blocks_route_dependency_dispatch_replacement(tmp_path):
    _check_real_kernel(tmp_path, "route_dispatch")
