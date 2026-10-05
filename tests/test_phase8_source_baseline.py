from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import jack_source_drift_guard as source_guard


def _authority_for(tmp_path: Path, content: bytes = b"alpha"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "authority.py"
    target.write_bytes(content)
    authority = source_guard.RuntimeSourceAuthority(
        runtime_id="runtime-a",
        lane_id="lane-a",
    )
    authority.register_component("authority.py", target)
    baseline = authority.seal()
    return authority, baseline, target


def test_baseline_uses_exact_bytes_and_seals_component_set(tmp_path):
    authority, baseline, target = _authority_for(tmp_path, b"exact-bytes")

    assert authority.state is source_guard.SourceAuthorityState.ACTIVE
    assert baseline.component_ids == ("authority.py",)
    assert baseline.components[0].canonical_path == str(target.resolve())
    assert baseline.components[0].expected_kind == "regular_file"
    assert len(baseline.components[0].sha256) == 64
    assert len(baseline.aggregate_sha256) == 64

    with pytest.raises(source_guard.SourceComponentSetSealed):
        authority.register_component("late.py", tmp_path / "late.py")


def test_confirmed_content_drift_is_terminal_even_if_original_bytes_return(tmp_path):
    authority, _baseline, target = _authority_for(tmp_path, b"alpha")

    target.write_bytes(b"bravo")
    result = authority.verify_now()
    assert result.state is source_guard.SourceAuthorityState.INVALIDATED
    assert result.mismatched_component_ids == ("authority.py",)

    target.write_bytes(b"alpha")
    result = authority.verify_now()
    assert result.state is source_guard.SourceAuthorityState.INVALIDATED
    assert result.verified is False

    with pytest.raises(source_guard.SourceAuthorityInvalidated):
        with authority.admit():
            pass


def test_measurement_unavailable_suspends_and_exact_reverification_restores_active(
    tmp_path,
    monkeypatch,
):
    authority, baseline, _target = _authority_for(tmp_path, b"alpha")
    original_measure = source_guard._measure_regular_file

    def unavailable(_path):
        raise source_guard.SourceMeasurementUnavailable("sharing violation")

    monkeypatch.setattr(source_guard, "_measure_regular_file", unavailable)
    result = authority.verify_now()
    assert result.state is source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED
    assert result.unavailable_component_ids == ("authority.py",)

    with pytest.raises(source_guard.SourceAuthorityUnavailable):
        with authority.admit():
            pass

    monkeypatch.setattr(source_guard, "_measure_regular_file", original_measure)
    result = authority.verify_now()
    assert result.state is source_guard.SourceAuthorityState.ACTIVE
    assert result.verified is True
    assert authority.baseline is baseline


def test_invalidation_and_final_admission_share_one_serialization_boundary(tmp_path):
    authority, _baseline, target = _authority_for(tmp_path, b"alpha")
    admitted = threading.Event()
    release = threading.Event()
    verification_finished = threading.Event()
    verification_result = []

    def consequence():
        with authority.admit():
            admitted.set()
            assert release.wait(timeout=5)

    def verifier():
        verification_result.append(authority.verify_now())
        verification_finished.set()

    consequence_thread = threading.Thread(target=consequence)
    consequence_thread.start()
    assert admitted.wait(timeout=5)

    target.write_bytes(b"changed")
    verifier_thread = threading.Thread(target=verifier)
    verifier_thread.start()

    # verify_now() must not transition authority while an admitted final
    # consequence owns the same narrow synchronization boundary.
    assert verification_finished.wait(timeout=0.1) is False

    release.set()
    consequence_thread.join(timeout=5)
    verifier_thread.join(timeout=5)

    assert verification_finished.is_set()
    assert verification_result[0].state is source_guard.SourceAuthorityState.INVALIDATED
    with pytest.raises(source_guard.SourceAuthorityInvalidated):
        with authority.admit():
            pass


def test_missing_or_type_changed_component_is_confirmed_drift(tmp_path):
    authority, _baseline, target = _authority_for(tmp_path, b"alpha")
    target.unlink()
    result = authority.verify_now()
    assert result.state is source_guard.SourceAuthorityState.INVALIDATED

    authority2, _baseline2, target2 = _authority_for(tmp_path / "second", b"alpha")
    target2.unlink()
    target2.mkdir()
    result = authority2.verify_now()
    assert result.state is source_guard.SourceAuthorityState.INVALIDATED


def test_mtime_only_change_with_identical_bytes_is_not_drift(tmp_path):
    authority, baseline, target = _authority_for(tmp_path, b"alpha")
    stat_before = target.stat()
    target.touch()
    stat_after = target.stat()

    assert stat_after.st_mtime_ns >= stat_before.st_mtime_ns
    result = authority.verify_now()
    assert result.state is source_guard.SourceAuthorityState.ACTIVE
    assert result.verified is True
    assert authority.baseline.aggregate_sha256 == baseline.aggregate_sha256


def test_install_requires_predecessor_authority_before_sealing(tmp_path):
    kernel_file = tmp_path / "jack_kernel.py"
    kernel_file.write_bytes(b"kernel")
    jk = SimpleNamespace(
        RUNTIME_ID="runtime-a",
        LANE_ID="lane-a",
        __file__=str(kernel_file),
    )

    with pytest.raises(source_guard.SourceBaselineCreationError):
        source_guard.install(jk)


def test_invalidated_state_is_not_reactivated_by_register_or_seal(tmp_path):
    authority, baseline, target = _authority_for(tmp_path, b"alpha")
    target.write_bytes(b"changed")
    authority.verify_now()

    with pytest.raises(source_guard.SourceComponentSetSealed):
        authority.register_component("new.py", tmp_path / "new.py")
    assert authority.seal() is baseline
    assert authority.state is source_guard.SourceAuthorityState.INVALIDATED
