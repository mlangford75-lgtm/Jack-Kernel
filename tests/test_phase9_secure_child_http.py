"""Real secured --serve child smoke: mandatory Phase 9B.

One isolated loopback-only Windows subprocess, no backend inference. Confirms
the actual Jack secure entrypoint installs Phase 8 + Phase 9B before Uvicorn
starts, and ordinary HTTP can proceed without framework warm-up false alarms.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


def test_real_secure_serve_child_phase9b_optin_http_startup(tmp_path):
    root = Path(__file__).resolve().parents[1]

    # Reserve a loopback port only long enough to select an unused candidate.
    # Disable fallback to ensure a different runner process cannot hijack the
    # test by moving Jack to another endpoint.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    env = dict(os.environ)
    # An explicit obsolete off value must not be interpreted as authority.
    env.update({
        "JACK_PHASE9B_EXPERIMENTAL": "0",
        "JACK_HOST": "127.0.0.1",
        "JACK_PORT": str(port),
        "JACK_PORT_FALLBACK": "0",
        "JACK_RUNTIME_ID": "phase9b-child-smoke",
        "JACK_LANE_ID": "phase9b-child-smoke",
        "JACK_RUNTIME_REGISTRY_DIR": str(tmp_path / "registry"),
        "JACK_AUTHORITY_LEDGER_DIR": str(tmp_path / "ledger"),
        "JACK_CONTEXT_MONITOR": "0",
        "JACK_FORENSIC_ARCHIVE_MODE": "off",
        "JACK_BACKEND_PROFILE": "lmstudio",
        "JACK_BACKEND_MODEL": "test-model",
        "JACK_BACKEND_BASE_URL": "http://127.0.0.1:9/v1",
    })
    output = tmp_path / "secured-child.log"
    base = f"http://127.0.0.1:{port}"
    with output.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "jack_secure_entrypoint.py", "--serve"],
            cwd=root,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            ready = False
            deadline = time.monotonic() + 24.0
            last = ""
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    with urllib.request.urlopen(base + "/", timeout=1.0) as response:
                        data = json.loads(response.read())
                        assert response.status == 200, data
                        ready = True
                        break
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    last = type(exc).__name__
                    time.sleep(0.20)

            assert ready, (
                f"secured child failed startup: exit={process.poll()} "
                f"last_probe={last}\n" + output.read_text(encoding="utf-8")
            )

            # Warm HTTP lifecycle must remain stable after middleware creation.
            for _ in range(3):
                with urllib.request.urlopen(base + "/", timeout=3.0) as response:
                    assert response.status == 200
                    body = json.loads(response.read())
                    assert isinstance(body, dict)

            # This is the actual registered path-admission endpoint: a missing
            # tool_call_id must yield the expected user input error, not a
            # spurious integrity failure.
            request = urllib.request.Request(
                base + "/jack/security/path-admission",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                urllib.request.urlopen(request, timeout=3.0)
            except urllib.error.HTTPError as exc:
                assert exc.code == 400, (
                    exc.code, exc.read().decode("utf-8", "replace"),
                    output.read_text(encoding="utf-8"),
                )
            else:
                raise AssertionError("missing tool_call_id was unexpectedly admitted")
        finally:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=8)
