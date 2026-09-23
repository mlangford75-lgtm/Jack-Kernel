import importlib.util
import json
import os
import socket
import sys
import uuid
from pathlib import Path

import pytest


SRC = Path(__file__).resolve().parents[1] / "jack_kernel.py"


def load_module(monkeypatch, tmp_path, *, port, fallback=True, runtime_id=None, lane_id=None):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "x-high")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_HOST", "127.0.0.1")
    monkeypatch.setenv("JACK_PORT", str(port))
    monkeypatch.setenv("JACK_PORT_FALLBACK", "1" if fallback else "0")
    monkeypatch.setenv("JACK_RUNTIME_REGISTRY_DIR", str(tmp_path / "runtime-registry"))
    monkeypatch.setenv("JACK_RUNTIME_ID", runtime_id or f"runtime-{uuid.uuid4().hex}")
    monkeypatch.setenv("JACK_LANE_ID", lane_id or f"lane-{uuid.uuid4().hex}")
    monkeypatch.delenv("JACK_AGENT_BASE_URL", raising=False)

    name = f"jack_multi_endpoint_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def occupied_loopback_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    return sock, int(sock.getsockname()[1])


def test_dynamic_port_zero_binds_and_updates_runtime_endpoint(monkeypatch, tmp_path):
    mod = load_module(monkeypatch, tmp_path, port=0, fallback=True)
    listener = mod._bind_runtime_listener()
    try:
        actual = listener.getsockname()[1]
        assert actual > 0
        assert mod.RUNTIME_ENDPOINT_STATE["preferred_port"] == 0
        assert mod.RUNTIME_ENDPOINT_STATE["actual_port"] == actual
        assert mod.RUNTIME_ENDPOINT_STATE["fallback_used"] is False
        assert mod._runtime_agent_base_url() == f"http://127.0.0.1:{actual}/v1"
    finally:
        listener.close()


def test_occupied_preferred_port_falls_back_atomically(monkeypatch, tmp_path):
    blocker, preferred = occupied_loopback_port()
    try:
        mod = load_module(monkeypatch, tmp_path, port=preferred, fallback=True)
        listener = mod._bind_runtime_listener()
        try:
            actual = int(listener.getsockname()[1])
            assert actual > 0
            assert actual != preferred
            assert mod.RUNTIME_ENDPOINT_STATE["preferred_port"] == preferred
            assert mod.RUNTIME_ENDPOINT_STATE["actual_port"] == actual
            assert mod.RUNTIME_ENDPOINT_STATE["fallback_used"] is True
            assert mod.RUNTIME_ENDPOINT_STATE["fallback_reason"] == "EADDRINUSE"
        finally:
            listener.close()
    finally:
        blocker.close()


def test_occupied_preferred_port_fails_when_fallback_disabled(monkeypatch, tmp_path):
    blocker, preferred = occupied_loopback_port()
    try:
        mod = load_module(monkeypatch, tmp_path, port=preferred, fallback=False)
        with pytest.raises(OSError):
            mod._bind_runtime_listener()
    finally:
        blocker.close()


def test_runtime_registry_uses_positive_runtime_identity(monkeypatch, tmp_path):
    runtime_id = f"runtime-{uuid.uuid4().hex}"
    lane_id = f"lane-{uuid.uuid4().hex}"
    mod = load_module(
        monkeypatch,
        tmp_path,
        port=0,
        fallback=True,
        runtime_id=runtime_id,
        lane_id=lane_id,
    )
    listener = mod._bind_runtime_listener()
    try:
        path = mod._write_runtime_manifest("ready", claim=True)
        payload = json.loads(path.read_text(encoding="utf-8"))

        assert payload["runtime_id"] == runtime_id
        assert payload["lane_id"] == lane_id
        assert payload["endpoint"]["actual_port"] == listener.getsockname()[1]
        assert payload["endpoint"]["preferred_port"] == 0
        assert payload["backend"]["concurrency_scope"] == "process_local"

        entries = mod._list_runtime_manifests()
        matching = [entry for entry in entries if entry["runtime_id"] == runtime_id]
        assert len(matching) == 1
        assert matching[0]["process_alive"] is True
    finally:
        mod._remove_runtime_manifest()
        listener.close()


def test_duplicate_live_runtime_id_is_rejected(monkeypatch, tmp_path):
    runtime_id = f"runtime-{uuid.uuid4().hex}"
    first = load_module(monkeypatch, tmp_path, port=0, runtime_id=runtime_id)
    first_listener = first._bind_runtime_listener()
    first_path = first._write_runtime_manifest("ready", claim=True)
    try:
        assert first_path.exists()
        second = load_module(monkeypatch, tmp_path, port=0, runtime_id=runtime_id)
        second_listener = second._bind_runtime_listener()
        try:
            existing = json.loads(first_path.read_text(encoding="utf-8"))
            existing["pid"] = os.getpid() + 100000
            first_path.write_text(json.dumps(existing), encoding="utf-8")
            second._pid_is_alive = lambda pid: True
            with pytest.raises(RuntimeError, match="already owned by live pid"):
                second._write_runtime_manifest("ready", claim=True)
        finally:
            second_listener.close()
    finally:
        first._remove_runtime_manifest()
        first_listener.close()


def test_pi_bridge_id_registry_resolution_preserves_legacy_when_unselected(monkeypatch, tmp_path):
    home = tmp_path / "home"
    config_dir = home / ".pi" / "agent"
    registry_dir = config_dir / "jack-kernel-bridges"
    config_dir.mkdir(parents=True)
    registry_dir.mkdir(parents=True)
    (config_dir / "jack-kernel.json").write_text(
        json.dumps({"controlPort": 8013, "controlToken": "secret"}),
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("JACK_PI_CONTROL_REGISTRY_DIR", str(registry_dir))
    monkeypatch.delenv("JACK_PI_CONTROL_URL", raising=False)
    monkeypatch.delenv("JACK_PI_CONTROL_PORT", raising=False)
    monkeypatch.delenv("JACK_PI_CONTROL_BRIDGE_ID", raising=False)

    legacy = load_module(monkeypatch, tmp_path, port=0)
    bridge = legacy._load_pi_control_bridge()
    assert bridge["url"] == "http://127.0.0.1:8013"
    assert bridge["source"] == "legacy_config"
    assert bridge["configured"] is True

    bridge_id = "debug-worker"
    manifest = {
        "bridge_id": bridge_id,
        "session_instance_id": "session-1",
        "pid": os.getpid(),
        "status": "ready",
        "host": "127.0.0.1",
        "preferred_port": 8014,
        "actual_port": 51337,
    }
    (registry_dir / "session-1.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("JACK_PI_CONTROL_BRIDGE_ID", bridge_id)

    selected = load_module(monkeypatch, tmp_path, port=0)
    bridge = selected._load_pi_control_bridge()
    assert bridge["url"] == "http://127.0.0.1:51337"
    assert bridge["source"] == "bridge_registry"
    assert bridge["bridge_id"] == bridge_id
    assert bridge["configured"] is True
