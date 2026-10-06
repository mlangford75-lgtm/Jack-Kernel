from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import jack_authority_ledger as authority_ledger
import jack_secure_entrypoint as entrypoint
import jack_source_drift_guard as source_guard


def _authority_for(tmp_path: Path, content: bytes = b"alpha"):
    target = tmp_path / "authority.py"
    target.write_bytes(content)
    authority = source_guard.RuntimeSourceAuthority(
        runtime_id="runtime-a",
        lane_id="lane-a",
    )
    authority.register_component("authority.py", target)
    authority.seal()
    return authority, target


def _ledger_for(tmp_path: Path):
    return authority_ledger.AuthorityLedger(
        runtime_id="runtime-a",
        lane_id="lane-a",
        projection_root=tmp_path / "ledger",
        queue_capacity=16,
    )


def _runtime_host(authority, *, run=None, proxy=None):
    async def default_run(*_args, **_kwargs):
        return "ok"

    async def default_stream(*_args, **_kwargs):
        yield b"one"

    def default_executor(*_args, **_kwargs):
        return "admitted"

    async def default_proxy(_request, method, path, *_args, **_kwargs):
        return (method, path)

    return SimpleNamespace(
        _JACK_SOURCE_AUTHORITY=authority,
        _JACK_SOURCE_AUTHORITY_INSTALLED=True,
        KERNEL=SimpleNamespace(
            run=run or default_run,
            stream=default_stream,
        ),
        _phase4_executor_admission_decision=default_executor,
        _proxy_pi_control_request=proxy or default_proxy,
        APP=None,
        JSONResponse=None,
    )


def test_observer_processing_bug_cannot_become_verifier_failure(
    tmp_path,
    monkeypatch,
):
    """A broken forensic observer must not suspend otherwise-valid source authority."""

    authority, _target = _authority_for(tmp_path)
    ledger = _ledger_for(tmp_path)
    jk_observer = SimpleNamespace(_JACK_AUTHORITY_LEDGER=ledger)
    assert entrypoint._install_phase8_ledger_observer(jk_observer, authority) is True

    def observer_bug(_value):
        raise RuntimeError("synthetic observer bug")

    monkeypatch.setattr(entrypoint, "_state_value", observer_bug)

    # The source verification itself is exact and ACTIVE. The observer failure
    # occurs only after that fact has already been established.
    authority.verify_for_authority_boundary()
    assert authority.state is source_guard.SourceAuthorityState.ACTIVE
    with authority.admit():
        pass

    ledger.close()


def test_observer_failure_during_suspension_cannot_block_later_exact_recovery(
    tmp_path,
    monkeypatch,
):
    authority, _target = _authority_for(tmp_path)
    ledger = _ledger_for(tmp_path)
    jk_observer = SimpleNamespace(_JACK_AUTHORITY_LEDGER=ledger)
    assert entrypoint._install_phase8_ledger_observer(jk_observer, authority) is True
    recorder = jk_observer._JACK_PHASE8_LEDGER_TRANSITION_RECORDER

    def broken_observe(**_kwargs):
        raise RuntimeError("synthetic ordering observer failure")

    monkeypatch.setattr(recorder, "observe", broken_observe)
    original_measure = source_guard._measure_regular_file

    def unavailable(_path):
        raise source_guard.SourceMeasurementUnavailable("sharing violation")

    monkeypatch.setattr(source_guard, "_measure_regular_file", unavailable)
    result = authority.verify_now()
    assert result.state is source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED

    # Restoration is source-owned and must not require a healthy observer.
    monkeypatch.setattr(source_guard, "_measure_regular_file", original_measure)
    result = authority.verify_now()
    assert result.state is source_guard.SourceAuthorityState.ACTIVE
    assert result.verified is True
    with authority.admit():
        pass

    ledger.close()


def test_forensic_ordering_gap_never_becomes_source_admission_backpressure(tmp_path):
    authority, _target = _authority_for(tmp_path)
    ledger = _ledger_for(tmp_path)
    recorder = entrypoint._Phase8OrderedLedgerObserver(
        ledger=ledger,
        authority=authority,
        next_transition_sequence=1,
    )

    # A later forensic fact arrives while #1 is absent. It must remain only an
    # observation-layer gap; source authority stays independently usable.
    recorder.observe(
        transition_sequence=2,
        event_type=entrypoint.Phase8LedgerEventType.SOURCE_AUTHORITY_RESTORED,
        prior_state="SUSPENDED_UNVERIFIED",
        new_state="ACTIVE",
        reason="exact_reverification",
    )

    assert authority.state is source_guard.SourceAuthorityState.ACTIVE
    with authority.admit():
        pass

    ledger.close()


def test_same_path_same_bytes_replacement_does_not_create_false_drift(tmp_path):
    authority, target = _authority_for(tmp_path, b"same-authority-bytes")
    original_baseline = authority.baseline

    # Phase 8 claims exact source-byte identity at the canonical path, not inode
    # identity or filesystem-object continuity.
    target.unlink()
    target.write_bytes(b"same-authority-bytes")

    result = authority.verify_now()
    assert result.state is source_guard.SourceAuthorityState.ACTIVE
    assert result.verified is True
    assert result.mismatched_component_ids == ()
    assert authority.baseline is original_baseline


def test_confirmed_mismatch_outranks_simultaneous_measurement_unavailability(
    tmp_path,
    monkeypatch,
):
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_bytes(b"one")
    second.write_bytes(b"two")

    authority = source_guard.RuntimeSourceAuthority(
        runtime_id="runtime-a",
        lane_id="lane-a",
    )
    authority.register_component("first.py", first)
    authority.register_component("second.py", second)
    authority.seal()

    second.write_bytes(b"changed")
    original_measure = source_guard._measure_regular_file

    def mixed_measure(path):
        if Path(path).resolve() == first.resolve():
            raise source_guard.SourceMeasurementUnavailable("sharing violation")
        return original_measure(path)

    monkeypatch.setattr(source_guard, "_measure_regular_file", mixed_measure)
    result = authority.verify_now()

    assert result.state is source_guard.SourceAuthorityState.INVALIDATED
    assert result.mismatched_component_ids == ("second.py",)
    assert result.unavailable_component_ids == ("first.py",)
    with pytest.raises(source_guard.SourceAuthorityInvalidated):
        with authority.admit():
            pass


def test_suspension_blocks_new_mutation_but_preserves_read_only_observation(
    tmp_path,
    monkeypatch,
):
    authority, _target = _authority_for(tmp_path)
    calls = []

    async def proxy(_request, method, path, *_args, **_kwargs):
        calls.append((method, path))
        return {"method": method, "path": path}

    jk = _runtime_host(authority, proxy=proxy)
    source_guard.activate_runtime_enforcement(jk, authority, start_periodic=False)

    def unavailable(_path):
        raise source_guard.SourceMeasurementUnavailable("sharing violation")

    monkeypatch.setattr(source_guard, "_measure_regular_file", unavailable)
    assert authority.verify_now().state is source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED

    status = asyncio.run(jk._proxy_pi_control_request(None, "GET", "/v1/status"))
    assert status == {"method": "GET", "path": "/v1/status"}

    with pytest.raises(source_guard.SourceAuthorityUnavailable):
        asyncio.run(jk._proxy_pi_control_request(None, "POST", "/v1/tasks"))

    assert calls == [("GET", "/v1/status")]


def test_already_admitted_external_effect_may_settle_after_source_invalidation(tmp_path):
    authority, target = _authority_for(tmp_path)
    started = asyncio.Event()
    finish = asyncio.Event()

    async def proxy(_request, method, path, *_args, **_kwargs):
        assert (method, path) == ("POST", "/v1/tasks")
        started.set()
        await finish.wait()
        return "physical-settlement"

    jk = _runtime_host(authority, proxy=proxy)
    source_guard.activate_runtime_enforcement(jk, authority, start_periodic=False)

    async def exercise():
        admitted = asyncio.create_task(
            jk._proxy_pi_control_request(None, "POST", "/v1/tasks")
        )
        await started.wait()

        target.write_bytes(b"changed")
        assert authority.verify_now().state is source_guard.SourceAuthorityState.INVALIDATED

        finish.set()
        assert await admitted == "physical-settlement"

        with pytest.raises(source_guard.SourceAuthorityInvalidated):
            await jk._proxy_pi_control_request(None, "POST", "/v1/tasks")

    asyncio.run(exercise())


def test_admission_serialization_never_revokes_a_consequence_already_inside_boundary(tmp_path):
    authority, target = _authority_for(tmp_path)
    admitted = threading.Event()
    release = threading.Event()
    verifier_done = threading.Event()
    completed = []

    def admitted_effect():
        with authority.admit():
            admitted.set()
            assert release.wait(timeout=5)
            completed.append("already-admitted")

    def detect_drift():
        authority.verify_now()
        verifier_done.set()

    effect_thread = threading.Thread(target=admitted_effect)
    effect_thread.start()
    assert admitted.wait(timeout=5)

    target.write_bytes(b"changed")
    verifier_thread = threading.Thread(target=detect_drift)
    verifier_thread.start()

    # Verification waits for the narrow admission critical section. Phase 8
    # does not retroactively revoke physical work already admitted inside it.
    assert verifier_done.wait(timeout=0.1) is False
    release.set()

    effect_thread.join(timeout=5)
    verifier_thread.join(timeout=5)
    assert not effect_thread.is_alive()
    assert not verifier_thread.is_alive()
    assert completed == ["already-admitted"]
    assert authority.state is source_guard.SourceAuthorityState.INVALIDATED

    with pytest.raises(source_guard.SourceAuthorityInvalidated):
        with authority.admit():
            pass
