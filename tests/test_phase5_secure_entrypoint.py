from __future__ import annotations

import jack_secure_entrypoint as entrypoint
import jack_source_drift_guard as source_guard


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
        "kernel-main",
    ]
