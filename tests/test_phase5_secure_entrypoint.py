from __future__ import annotations

import jack_secure_entrypoint as entrypoint


def test_secure_entrypoint_uses_shared_bundled_extension_path(monkeypatch):
    events = []

    monkeypatch.setattr(
        entrypoint.jk,
        "_install_bundled_runtime_extensions",
        lambda: events.append("bundled"),
    )
    monkeypatch.setattr(
        entrypoint.jk,
        "main",
        lambda: events.append("kernel-main"),
    )

    entrypoint.main()

    assert events == ["bundled", "kernel-main"]
