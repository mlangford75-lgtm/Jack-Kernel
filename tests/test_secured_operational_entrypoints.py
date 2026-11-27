from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_kernel(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "custom")
    monkeypatch.setenv("JACK_CANARY_POLICY_JSON", "")
    monkeypatch.setenv("JACK_AUTHORITY_LEDGER_DIR", str(tmp_path / "ledger"))
    name = "jack_entrypoint_test_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def test_normal_kernel_launch_and_direct_serve_delegate(monkeypatch, tmp_path):
    module = _load_kernel(monkeypatch, tmp_path)
    expected = str(ROOT / "jack_secure_entrypoint.py")
    assert module._server_command() == [sys.executable, expected, "--serve"]
    monkeypatch.setattr(sys, "argv", ["jack_kernel.py", "--serve"])
    monkeypatch.setattr(module, "_install_bundled_runtime_extensions",
                        lambda: pytest.fail("base server installed before delegation"))
    monkeypatch.setattr(module, "run_server", lambda: pytest.fail("unsealed server"))
    calls = []

    def child(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=17)

    monkeypatch.setattr(module.subprocess, "run", child)
    with pytest.raises(SystemExit) as exc:
        module.main()
    assert exc.value.code == 17
    assert calls == [([sys.executable, expected, "--serve"], {"check": False})]


def test_secure_composition_and_explicit_test_escape(monkeypatch, tmp_path, capsys):
    module = _load_kernel(monkeypatch, tmp_path)
    events = []
    monkeypatch.setattr(module, "_install_bundled_runtime_extensions",
                        lambda: events.append("install"))
    monkeypatch.setattr(module, "run_server", lambda: events.append("serve"))
    monkeypatch.setattr(module, "_delegate_secured_serving",
                        lambda: pytest.fail("unexpected delegation"))

    monkeypatch.setattr(sys, "argv", ["jack_kernel.py", "--serve", "--unsecured-test-serve"])
    module.main()
    assert events == ["install", "serve"]
    assert "UNSECURED TEST SERVER" in capsys.readouterr().err

    events.clear()
    monkeypatch.setattr(sys, "argv", ["jack_secure_entrypoint.py", "--serve"])
    monkeypatch.setattr(module, "_JACK_SOURCE_AUTHORITY_INSTALLED", True, raising=False)
    with pytest.raises(RuntimeError, match="composition is incomplete"):
        module.main()
    assert not events

    monkeypatch.setattr(module, "_JACK_SOURCE_RUNTIME_ENFORCEMENT_INSTALLED", True, raising=False)
    for name in (
        "_JACK_SOURCE_AUTHORITY", "_JACK_RUNTIME_CODE_AUTHORITY",
        "_JACK_PATH_POLICY_AUTHORITY", "_JACK_CANARY_POLICY_AUTHORITY",
        "_JACK_CREDENTIAL_POLICY_AUTHORITY", "_JACK_DIAGNOSTIC_PRIVACY",
    ):
        monkeypatch.setattr(module, name, object(), raising=False)
    module.main()
    assert events == ["install", "serve"]


def test_responses_entrypoint_uses_shared_secure_startup(monkeypatch):
    import jack_responses_compat
    calls = []
    monkeypatch.setitem(sys.modules, "jack_secure_entrypoint",
                        SimpleNamespace(main=lambda: calls.append("secure")))
    jack_responses_compat.main()
    assert calls == ["secure"]
