from __future__ import annotations

import jack_secure_entrypoint as entrypoint


def test_secure_entrypoint_installs_consequence_gate_before_kernel_main(monkeypatch):
    events = []

    monkeypatch.setattr(
        entrypoint.jk,
        "_install_bundled_runtime_extensions",
        lambda: events.append("bundled"),
    )
    monkeypatch.setattr(
        entrypoint.jack_consequence_gate,
        "install",
        lambda module: events.append(("gate", module is entrypoint.jk)),
    )
    monkeypatch.setattr(
        entrypoint.jk,
        "main",
        lambda: events.append("kernel-main"),
    )

    entrypoint.main()

    assert events == [
        "bundled",
        ("gate", True),
        "kernel-main",
    ]
