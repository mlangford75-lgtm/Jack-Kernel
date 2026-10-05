from __future__ import annotations

import jack_secure_entrypoint as entrypoint
import jack_source_drift_guard as source_guard


def test_secure_entrypoint_uses_shared_bundled_extension_path(monkeypatch):
    events = []

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
        entrypoint.jk,
        "main",
        lambda: events.append("kernel-main"),
    )

    entrypoint.main()

    assert events == ["bundled", "source-baseline", "kernel-main"]
