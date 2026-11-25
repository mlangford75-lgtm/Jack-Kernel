"""Phase 9B source-file close-out for newly introduced security modules.

The historical Phase 8 source manifest is intentionally unchanged.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import jack_source_drift_guard as source
from jack_runtime_code_guard import (
    RuntimeCodeAuthority,
    RuntimeCodeIntegrityCompromised,
    RuntimeCodeIntegrityUnavailable,
)


def _guard(path):
    owner = SimpleNamespace(go=lambda: "authorized")
    guard = RuntimeCodeAuthority()
    guard.register(name="executor", owner=owner, attribute="go", scope="executor")
    guard.register_source(name="phase9-file", path=path, scope="shared")
    guard.seal()
    return guard


def test_phase9_source_stability_and_benign_read(tmp_path):
    path = tmp_path / "security_module.py"
    path.write_text("def safe(): return 1\n", encoding="utf-8")
    guard = _guard(path)
    guard.verify_for("executor")
    guard.verify_for("observation")
    assert guard.state == "ACTIVE"


def test_phase9_source_content_change_blocks_every_scoped_authority(tmp_path):
    path = tmp_path / "security_module.py"
    path.write_text("def safe(): return 1\n", encoding="utf-8")
    guard = _guard(path)
    path.write_text("def safe(): return 2\n", encoding="utf-8")
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify_for("observation")
    assert "phase9-file" in guard.mismatched_slots
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify_for("executor")
    assert guard.state == "INVALIDATED"


def test_phase9_source_restoration_does_not_silently_rebaseline(tmp_path):
    path = tmp_path / "security_module.py"
    original = "def safe(): return 1\n"
    path.write_text(original, encoding="utf-8")
    guard = _guard(path)
    path.write_text("def safe(): return 2\n", encoding="utf-8")
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify_for("executor")
    path.write_text(original, encoding="utf-8")
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify_for("executor")


def test_phase9_source_deletion_is_confirmed_compromise(tmp_path):
    path = tmp_path / "security_module.py"
    path.write_text("# trusted\n", encoding="utf-8")
    guard = _guard(path)
    path.unlink()
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify_for("model")
    assert guard.mismatched_slots == ("phase9-file",)


def test_phase9_source_directory_substitution_is_confirmed_compromise(tmp_path):
    path = tmp_path / "security_module.py"
    path.write_text("# trusted\n", encoding="utf-8")
    guard = _guard(path)
    path.unlink()
    path.mkdir()
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify_for("executor")


def test_source_measurement_unavailability_suspends_and_exactly_recovers(tmp_path, monkeypatch):
    path = tmp_path / "security_module.py"
    path.write_text("# trusted\n", encoding="utf-8")
    guard = _guard(path)
    original = source._measure_regular_file

    def unavailable(*args, **kwargs):
        raise source.SourceMeasurementUnavailable("synthetic I/O uncertainty")

    monkeypatch.setattr(source, "_measure_regular_file", unavailable)
    with pytest.raises(RuntimeCodeIntegrityUnavailable):
        guard.verify_for("executor")
    assert guard.state == "SUSPENDED_UNVERIFIED"
    monkeypatch.setattr(source, "_measure_regular_file", original)
    guard.verify_for("executor")
    assert guard.state == "ACTIVE"


def test_required_source_missing_at_seal_is_never_accepted(tmp_path):
    path = tmp_path / "missing.py"
    guard = RuntimeCodeAuthority()
    guard.register(name="executor", owner=SimpleNamespace(go=lambda: 1),
                   attribute="go")
    with pytest.raises(RuntimeCodeIntegrityUnavailable):
        guard.register_source(name="missing", path=path)


def test_source_manifest_is_sealed_and_does_not_accept_late_components(tmp_path):
    path = tmp_path / "module.py"
    path.write_text("# trusted\n", encoding="utf-8")
    guard = _guard(path)
    with pytest.raises(RuntimeError):
        guard.register_source(name="late", path=path)


