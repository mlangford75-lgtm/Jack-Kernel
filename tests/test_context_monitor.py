"""Nonintrusive Windows Context Monitor contract and real backend provenance."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import time
import types
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]


def monitor():
    name = "jack_monitor_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_context_monitor.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def kernel(monkeypatch, tmp_path, *, enabled=True):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "balanced")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_CONTEXT_MONITOR", "1" if enabled else "0")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_monitor_kernel_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k


def test_status_parses_only_authoritative_backend_numbers():
    m = monitor()
    s = m.interpret_status({
        "runtime_id": "agentic-x", "context_length": 262144,
        "context_length_source": "lmstudio_loaded_instance",
        "context_usage_source": "backend_stream_usage_only",
        "backend_model": "qwen3.6-35b-a3b",
        "telemetry_status": "ok",
        "requests": [{
            "backend_request_active": True, "stage": "Agentic native pass 1",
            "backend_stream_phase": "reasoning",
            "backend_prompt_tokens": 130000,
            "backend_total_tokens": 130321,
        }],
    }, observed_at=1000)
    assert s["tokens"] == 130321
    assert s["kind"] == "request total"
    assert s["origin"] == "this request"
    assert s["capacity"] == 262144
    assert s["model"] == "qwen3.6-35b-a3b"
    assert s["measured_at"] == 1000


def test_unknown_is_not_converted_into_fake_live_occupancy():
    m = monitor()
    s = m.interpret_status({
        "context_length": 262144, "requests": [{
            "backend_request_active": True, "backend_stream_phase": "waiting_backend",
            "backend_stream_bytes": {"reasoning": 9999999},
            "backend_prompt_tokens": None,
        }],
    })
    assert s["capacity"] == 262144
    assert s["tokens"] is None
    assert s["phase"] == "waiting on model"
    assert s["origin"] == "unknown"
    for bad in (True, "12000", -1, 0.25):
        assert m._nonnegative(bad) is None


def test_completed_usage_does_not_get_erased_by_fresh_request():
    m = monitor()
    previous = m.interpret_status({
        "context_length": 262144,
        "requests": [],
        "last_request": {"backend_total_tokens": 120000, "ended_at_unix": 500.0},
    }, observed_at=501.0)
    current = m.interpret_status({
        "context_length": 262144,
        "requests": [{
            "backend_request_active": True,
            "backend_stream_phase": "waiting_backend",
            "backend_total_tokens": None,
        }],
    }, previous, observed_at=550.0)
    assert current["tokens"] == 120000
    assert current["origin"] == "last confirmed reading"
    assert current["measured_at"] == 500.0


def test_old_backend_request_usage_is_not_labeled_live():
    m = monitor()
    previous = {"kind": "request total", "tokens": 10, "measured_at": 12.0}
    out = m.interpret_status({
        "context_length": 262144,
        "requests": [{
            "backend_request_active": True,
            "last_backend_total_tokens": 105000,
            "backend_total_tokens": None,
        }],
    }, previous, observed_at=22.0)
    assert out["tokens"] == 105000
    assert out["origin"] == "previous backend request"
    assert out["measured_at"] == 12.0


def test_read_status_enforces_exact_runtime_and_authorization(monkeypatch):
    m = monitor()
    calls = []

    class FakeResponse:
        def __init__(self, response):
            self.response = response
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return None
        def read(self, amount):
            assert amount == m.MAX_STATUS_BYTES + 1
            return json.dumps(self.response).encode("utf-8")

    class FakeOpener:
        def __init__(self, response):
            self.response = response
        def open(self, request, *, timeout):
            calls.append((request, timeout))
            return FakeResponse(self.response)

    monkeypatch.setattr(m.urllib.request, "build_opener",
                        lambda *_a: FakeOpener({"runtime_id": "right", "context_length": 100}))
    good = m.read_status("http://127.0.0.1:9999/jack/runtime/status", "private", "right")
    assert good["context_length"] == 100
    assert calls[-1][0].get_header("Authorization") == "Bearer private"
    with pytest.raises(ValueError, match="identity mismatch"):
        m.read_status("http://127.0.0.1:9999/jack/runtime/status", "private", "wrong")


def test_monitor_url_rejects_invalid_ports_and_missing_runtime():
    m = monitor()
    with pytest.raises(ValueError, match="numeric"):
        m._status_url_and_token({"JACK_CONTEXT_MONITOR_PORT": "abc"})
    with pytest.raises(ValueError, match="outside"):
        m._status_url_and_token({"JACK_CONTEXT_MONITOR_PORT": "65536"})
    with pytest.raises(ValueError, match="identity"):
        m._status_url_and_token({"JACK_CONTEXT_MONITOR_PORT": "8100"})
    assert m._status_url_and_token({
        "JACK_CONTEXT_MONITOR_PORT": "8100",
        "JACK_CONTEXT_MONITOR_RUNTIME_ID": "jack-one",
        "JACK_CONTEXT_MONITOR_TOKEN": "secret",
    }) == ("http://127.0.0.1:8100/jack/runtime/status", "secret", "jack-one")


def test_startup_config_switch_preserves_default_and_env(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path)
    assert k.CFG.context_monitor_enabled is True
    assert k.CLI_DEFAULTS["context_monitor_enabled"] is True
    cfg = dict(k.CLI_DEFAULTS)
    assert k._config_to_env(cfg)["JACK_CONTEXT_MONITOR"] == "1"
    cfg["context_monitor_enabled"] = False
    assert k._config_to_env(cfg)["JACK_CONTEXT_MONITOR"] == "0"
    k2 = kernel(monkeypatch, tmp_path, enabled=False)
    assert k2.CFG.context_monitor_enabled is False
    assert k2._launch_context_monitor_failsoft(8001) is False  # Never spawn GUI in CI


def test_windows_monitor_is_detached_and_does_not_inherit_backend_credentials(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path)
    gui = tmp_path / "jack_context_monitor.py"
    gui.write_text("# dummy monitor", encoding="utf-8")
    launched = []
    def spawn(cmd, **kw):
        launched.append((cmd, kw))
        return types.SimpleNamespace(pid=1234)
    monkeypatch.setattr(k.subprocess, "Popen", spawn)
    monkeypatch.setattr(k, "os", types.SimpleNamespace(
        name="nt", environ={"PATH": "C:/Windows", "JACK_BACKEND_API_KEY": "never-forward"},
    ))
    monkeypatch.setattr(k, "Path", lambda v: Path(gui) if str(v) == k.__file__ else Path(v))
    assert k._launch_context_monitor_failsoft(8123) is True
    cmd, kwargs = launched[0]
    assert cmd[1] == str(gui)
    assert kwargs["env"]["JACK_CONTEXT_MONITOR_PORT"] == "8123"
    assert kwargs["env"]["JACK_CONTEXT_MONITOR_RUNTIME_ID"] == k.RUNTIME_ID
    assert "JACK_BACKEND_API_KEY" not in kwargs["env"]
    assert kwargs["stdin"] == k.subprocess.DEVNULL
    assert kwargs["stdout"] == k.subprocess.DEVNULL


def test_monitor_start_failure_cannot_stop_jack(monkeypatch, tmp_path):
    k = kernel(monkeypatch, tmp_path)
    # Must safely fail if GUI cannot start on a Windows host.
    monkeypatch.setattr(k, "os", types.SimpleNamespace(name="nt", environ={}))
    monkeypatch.setattr(k, "Path", lambda v: Path("/nonexistent/context_monitor.py"))
    assert k._launch_context_monitor_failsoft(8101) is False
