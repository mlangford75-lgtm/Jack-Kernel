from __future__ import annotations

import jack_secure_entrypoint as entrypoint
import jack_source_drift_guard as source_guard
import jack_phase9b_enforcement as runtime_guard
from jack_runtime_code_guard import RuntimeCodeIntegrityUnavailable


def test_secure_entrypoint_launcher_uses_predecessor_extensions_without_source_activation(monkeypatch):
    events = []

    monkeypatch.setattr(entrypoint.sys, "argv", ["jack_secure_entrypoint.py"])
    monkeypatch.setattr(
        entrypoint.jk,
        "_install_bundled_runtime_extensions",
        lambda: events.append("bundled"),
    )
    monkeypatch.setattr(
        source_guard,
        "install",
        lambda jk, *, launch_entrypoint_path=None: events.append("source-baseline"),
    )
    monkeypatch.setattr(
        entrypoint,
        "_install_phase8_ledger_observer",
        lambda jk, authority: events.append("source-ledger-observer"),
    )
    monkeypatch.setattr(
        source_guard,
        "activate_runtime_enforcement",
        lambda jk, authority: events.append("source-enforcement"),
    )
    monkeypatch.setattr(
        entrypoint.jk,
        "main",
        lambda: events.append("kernel-main"),
    )

    entrypoint.main()

    assert events == ["bundled", "kernel-main"]


def test_secure_entrypoint_serving_process_seals_observes_then_activates_before_kernel_main(monkeypatch):
    events = []
    authority = object()

    monkeypatch.setattr(entrypoint.sys, "argv", ["jack_secure_entrypoint.py", "--serve"])
    monkeypatch.setattr(
        entrypoint.jk,
        "_install_bundled_runtime_extensions",
        lambda: events.append("bundled"),
    )

    def install(jk, *, launch_entrypoint_path=None):
        events.append("source-baseline")
        return authority

    def observe(jk, received):
        assert received is authority
        events.append("source-ledger-observer")
        return True

    def activate(jk, received):
        assert received is authority
        events.append("source-enforcement")
        return received

    monkeypatch.setattr(source_guard, "install", install)
    monkeypatch.setattr(entrypoint, "_install_phase8_ledger_observer", observe)
    monkeypatch.setattr(source_guard, "activate_runtime_enforcement", activate)

    def phase9b_install(received):
        assert received is entrypoint.jk
        # Phase 9B is mandatory and cannot precede a successfully activated
        # Phase 8. This mock isolates ordering only; separate serving-child
        # tests prove the real manifest and HTTP release behavior.
        assert events[-1] == "source-enforcement"
        events.append("runtime-code-enforcement")
        return object()

    monkeypatch.setattr(runtime_guard, "install", phase9b_install)
    monkeypatch.setattr(
        entrypoint.jk,
        "main",
        lambda: events.append("kernel-main"),
    )

    entrypoint.main()

    assert events == [
        "bundled",
        "source-baseline",
        "source-ledger-observer",
        "source-enforcement",
        "runtime-code-enforcement",
        "kernel-main",
    ]


def test_secure_serving_child_aborts_before_kernel_main_when_phase9b_cannot_seal(monkeypatch):
    events = []
    authority = object()
    monkeypatch.setattr(entrypoint.sys, "argv", ["jack_secure_entrypoint.py", "--serve"])
    monkeypatch.setattr(
        entrypoint.jk,
        "_install_bundled_runtime_extensions",
        lambda: events.append("bundled"),
    )
    monkeypatch.setattr(
        source_guard,
        "install",
        lambda jk, *, launch_entrypoint_path=None: authority,
    )
    monkeypatch.setattr(
        entrypoint,
        "_install_phase8_ledger_observer",
        lambda jk, received: events.append("source-ledger-observer"),
    )
    monkeypatch.setattr(
        source_guard,
        "activate_runtime_enforcement",
        lambda jk, received: events.append("source-enforcement"),
    )

    def reject_seal(jk):
        events.append("runtime-code-enforcement")
        raise RuntimeCodeIntegrityUnavailable("test: unable to seal P0 manifest")

    monkeypatch.setattr(runtime_guard, "install", reject_seal)
    monkeypatch.setattr(entrypoint.jk, "main", lambda: events.append("kernel-main"))

    import pytest

    with pytest.raises(RuntimeCodeIntegrityUnavailable, match="unable to seal"):
        entrypoint.main()
    assert events == [
        "bundled",
        "source-ledger-observer",
        "source-enforcement",
        "runtime-code-enforcement",
    ]
