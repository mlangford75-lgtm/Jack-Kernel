"""Live adversarial HTTP test: tamper with code inside the actual secured child.

This launches the normal secure entrypoint and serves real loopback HTTP.
A *test-only* watcher in that same process replaces protected callables AFTER
the server has served healthy requests. No security bypass endpoint, runtime
toggle, or production module is installed to perform the attack. The watcher
accepts only test-owned file signals created under pytest's temp directory.
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
import pytest


_CHILD = r'''
import json
import os
import sys
import threading
import time
from pathlib import Path

import jack_secure_entrypoint as secure_entrypoint
import jack_kernel as jk

signals = Path(os.environ["JACK_PHASE9B_TEST_SIGNALS"])

# Install a single synthetic, already released safe tool call before the
# server starts. No production hook or post-seal mutation creates authority.
arguments = {"path": "D:/Projects/Jack/safe.txt"}
call = {"id": "qualified-safe-read", "type": "function", "function": {
    "name": "read", "arguments": json.dumps(arguments)}}
pending = jk.PendingToolResume(
    resume_id="qualified-resume", stage_key="thesis",
    history=[{"role": "assistant", "tool_calls": [call]}],
    secondary_system="", usage={}, tools=None, tool_choice=None,
    expected_tool_call_ids=("qualified-safe-read",), created_at=time.time(),
)
jk.KERNEL._pending_authority.register(pending)
jk.KERNEL._pending_tool_resumes["qualified-safe-read"] = pending


def adversarial_watcher():
    while True:
        for target in ("model", "canary-matcher", "authentication", "path-policy"):
            request = signals / (target + ".request")
            receipt = signals / (target + ".ack")
            if not request.exists() or receipt.exists():
                continue
            if target == "model":
                async def unauthorized_model(*_args, **_kwargs):
                    (signals / "unauthorized_model_executed").write_text(
                        "EXECUTED", encoding="utf-8"
                    )
                    return {"unauthorized": True}
                jk.KERNEL.run = unauthorized_model
            elif target == "canary-matcher":
                import jack_evidence_guard as evidence
                def unauthorized_match(*_args, **_kwargs):
                    (signals / "unauthorized_model_executed").write_text(
                        "EXECUTED", encoding="utf-8"
                    )
                    return None
                evidence.DeterministicCanarySet._find_with_position = unauthorized_match
            elif target == "path-policy":
                jk._RUNTIME_PATH_POLICY = None
            else:
                async def unauthorized_auth(*_args, **_kwargs):
                    (signals / "unauthorized_auth_executed").write_text(
                        "EXECUTED", encoding="utf-8"
                    )
                    return None
                jk.enforce_kernel_auth = unauthorized_auth
            receipt.write_text("MUTATED", encoding="utf-8")
        time.sleep(0.02)


threading.Thread(
    target=adversarial_watcher,
    name="phase9b-test-only-tamper",
    daemon=True,
).start()
sys.argv = ["jack_secure_entrypoint.py", "--serve"]
secure_entrypoint.main()
'''


def _http(base: str, path: str, *, post: bool = False, payload=None) -> tuple[int, bytes]:
    request = urllib.request.Request(
        base + path,
        method="POST" if post else "GET",
        data=json.dumps(payload if payload is not None else {}).encode("utf-8") if post else None,
        headers={"Content-Type": "application/json"} if post else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=4.0) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _signal(signals: Path, name: str, process: subprocess.Popen, log: Path) -> None:
    (signals / (name + ".request")).write_text("TAMPER", encoding="utf-8")
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        if (signals / (name + ".ack")).exists():
            return
        if process.poll() is not None:
            break
        time.sleep(0.05)
    raise AssertionError(
        f"live test did not receive {name} tamper acknowledgement: "
        f"exit={process.poll()}\n" + log.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize("model_target", ["model", "canary-matcher"])
def test_live_secure_http_detects_post_start_model_and_shared_auth_tamper(tmp_path, model_target):
    """Attack actual loaded callables, then assert consequence non-execution."""
    root = Path(__file__).resolve().parents[1]
    signals = tmp_path / "signals"
    signals.mkdir()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    env = dict(os.environ)
    env.update({
        "JACK_PHASE9B_TEST_SIGNALS": str(signals),
        "JACK_HOST": "127.0.0.1",
        "JACK_PORT": str(port),
        "JACK_PORT_FALLBACK": "0",
        "JACK_RUNTIME_ID": "phase9b-live-tamper",
        "JACK_LANE_ID": "phase9b-live-tamper",
        "JACK_RUNTIME_REGISTRY_DIR": str(tmp_path / "registry"),
        "JACK_AUTHORITY_LEDGER_DIR": str(tmp_path / "ledger"),
        "JACK_CONTEXT_MONITOR": "0",
        "JACK_PATH_POLICY_JSON": '{"version":1,"workspace_root":"D:/Projects/Jack","never_paths":[]}',
        "JACK_FORENSIC_ARCHIVE_MODE": "off",
        "JACK_BACKEND_PROFILE": "lmstudio",
        "JACK_BACKEND_MODEL": "test-model",
        "JACK_BACKEND_BASE_URL": "http://127.0.0.1:9/v1",
    })
    base = f"http://127.0.0.1:{port}"
    output = tmp_path / "live-secured-child.log"
    with output.open("w", encoding="utf-8") as log:
        child = subprocess.Popen(
            [sys.executable, "-c", _CHILD],
            cwd=root,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            ready = False
            deadline = time.monotonic() + 28.0
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    break
                try:
                    code, data = _http(base, "/")
                except (urllib.error.URLError, TimeoutError, OSError):
                    time.sleep(0.15)
                    continue
                if code == 200:
                    ready = True
                    break
                time.sleep(0.15)
            assert ready, (
                f"secured child not ready (exit={child.poll()}):\n"
                + output.read_text(encoding="utf-8")
            )

            # Normal operation before the tampering starts.
            code, _ = _http(base, "/")
            assert code == 200

            # Remove the active policy after successful startup. The real
            # executor route must reject this without disabling status.
            payload = {
                "protocol_version": 1,
                "runtime_id": "phase9b-live-tamper", "lane_id": "phase9b-live-tamper",
                "tool_call_id": "qualified-safe-read", "tool_name": "read",
                "arguments": {"path": "D:/Projects/Jack/safe.txt"},
                "executor_cwd": "D:/Projects/Jack", "executor_platform": "win32",
                "command_dialect": "powershell",
            }
            code, response = _http(base, "/jack/security/path-admission", post=True, payload=payload)
            assert code == 200 and json.loads(response)["outcome"] == "ALLOW", (code, response)
            _signal(signals, "path-policy", child, output)
            code, response = _http(base, "/jack/security/path-admission", post=True, payload=payload)
            assert code == 503, (code, response)
            assert b"AUTHORITY_POLICY_INTEGRITY_COMPROMISED" in response
            code, _ = _http(base, "/")
            assert code == 200

            # First executable attack: replace the actual effective run binding while
            # Phase 8 has verified unchanged source files. Phase 9B must
            # prevent any HTTP dispatch to this unauthorized function.
            _signal(signals, model_target, child, output)
            code, response = _http(base, "/v1/chat/completions", post=True)
            assert code == 503, (code, response)
            assert b"jack_runtime_code_integrity_unavailable" in response
            assert b"unauthorized" not in response
            assert not (signals / "unauthorized_model_executed").exists()

            # A model-specific violation should not silently disable
            # an independently verified host-only status endpoint.
            code, _ = _http(base, "/")
            assert code == 200

            # Second attack in the SAME live child: replace shared API
            # authentication authority. Shared trust loss must block even
            # the observational HTTP surface: preserving uptime cannot
            # override the common security boundary.
            _signal(signals, "authentication", child, output)
            code, response = _http(base, "/")
            assert code == 503, (code, response)
            assert b"jack_runtime_code_integrity_unavailable" in response
            code, _ = _http(base, "/jack/security/path-admission", post=True)
            assert code == 503
            assert not (signals / "unauthorized_auth_executed").exists()
            assert child.poll() is None, (
                "service crashed instead of coherently withholding authority"
            )
        finally:
            child.terminate()
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=8)
