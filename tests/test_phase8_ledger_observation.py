from __future__ import annotations

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


def test_observer_records_only_meaningful_source_transitions_with_safe_payloads(
    tmp_path,
    monkeypatch,
):
    authority, target = _authority_for(tmp_path)
    ledger = _ledger_for(tmp_path)
    jk = SimpleNamespace(_JACK_AUTHORITY_LEDGER=ledger)
    recorded = []

    monkeypatch.setattr(ledger, "_advance", lambda **kwargs: recorded.append(kwargs))
    assert entrypoint._install_phase8_ledger_observer(jk, authority) is True

    result = authority.verify_now()
    assert result.prior_state is source_guard.SourceAuthorityState.ACTIVE
    assert result.state is source_guard.SourceAuthorityState.ACTIVE
    assert result.transition_sequence == 0
    assert result.verified is True
    assert recorded == []

    original_measure = source_guard._measure_regular_file

    def unavailable(_path):
        raise source_guard.SourceMeasurementUnavailable("sharing violation")

    monkeypatch.setattr(source_guard, "_measure_regular_file", unavailable)
    result = authority.verify_now()
    assert result.prior_state is source_guard.SourceAuthorityState.ACTIVE
    assert result.state is source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED
    assert result.transition_sequence == 1
    assert len(recorded) == 1

    result = authority.verify_now()
    assert result.prior_state is source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED
    assert result.state is source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED
    assert result.transition_sequence == 1
    assert len(recorded) == 1

    monkeypatch.setattr(source_guard, "_measure_regular_file", original_measure)
    result = authority.verify_now()
    assert result.prior_state is source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED
    assert result.state is source_guard.SourceAuthorityState.ACTIVE
    assert result.transition_sequence == 2
    assert len(recorded) == 2

    target.write_bytes(b"changed")
    result = authority.verify_now()
    assert result.prior_state is source_guard.SourceAuthorityState.ACTIVE
    assert result.state is source_guard.SourceAuthorityState.INVALIDATED
    assert result.transition_sequence == 3
    assert len(recorded) == 3

    result = authority.verify_now()
    assert result.prior_state is source_guard.SourceAuthorityState.INVALIDATED
    assert result.state is source_guard.SourceAuthorityState.INVALIDATED
    assert result.transition_sequence == 3
    assert len(recorded) == 3

    assert [item["event_type"] for item in recorded] == [
        entrypoint.Phase8LedgerEventType.SOURCE_AUTHORITY_SUSPENDED,
        entrypoint.Phase8LedgerEventType.SOURCE_AUTHORITY_RESTORED,
        entrypoint.Phase8LedgerEventType.SOURCE_DRIFT_DETECTED,
    ]
    assert [item["payload"]["reason"] for item in recorded] == [
        "measurement_unavailable",
        "exact_reverification",
        "confirmed_source_mismatch",
    ]
    assert recorded[0]["payload"]["unavailable_component_ids"] == ("authority.py",)
    assert recorded[2]["payload"]["mismatched_component_ids"] == ("authority.py",)
    assert str(target.resolve()) not in repr([item["payload"] for item in recorded])

    ledger.close()


def test_unexpected_required_verifier_failure_records_suspension_after_source_state_changes(
    tmp_path,
    monkeypatch,
):
    authority, _target = _authority_for(tmp_path)
    ledger = _ledger_for(tmp_path)
    jk = SimpleNamespace(_JACK_AUTHORITY_LEDGER=ledger)
    recorded = []

    monkeypatch.setattr(ledger, "_advance", lambda **kwargs: recorded.append(kwargs))
    assert entrypoint._install_phase8_ledger_observer(jk, authority) is True

    def explode(_path):
        raise RuntimeError("synthetic verifier failure")

    monkeypatch.setattr(source_guard, "_measure_regular_file", explode)

    with pytest.raises(source_guard.SourceAuthorityUnavailable):
        authority.verify_for_authority_boundary()

    assert authority.state is source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED
    assert authority.transition_sequence == 1
    assert len(recorded) == 1
    event = recorded[0]
    assert event["event_type"] is entrypoint.Phase8LedgerEventType.SOURCE_AUTHORITY_SUSPENDED
    assert event["payload"]["reason"] == "verification_operation_failed"
    assert event["payload"]["prior_state"] == "ACTIVE"
    assert event["payload"]["new_state"] == "SUSPENDED_UNVERIFIED"

    ledger.close()


def test_two_concurrent_unavailable_verifications_record_exactly_one_suspension(
    tmp_path,
    monkeypatch,
):
    authority, _target = _authority_for(tmp_path)
    ledger = _ledger_for(tmp_path)
    jk = SimpleNamespace(_JACK_AUTHORITY_LEDGER=ledger)
    recorded = []
    recorded_lock = threading.Lock()
    start = threading.Barrier(3)
    results = []

    def record(**kwargs):
        with recorded_lock:
            recorded.append(kwargs)

    def unavailable(_path):
        raise source_guard.SourceMeasurementUnavailable("sharing violation")

    monkeypatch.setattr(ledger, "_advance", record)
    monkeypatch.setattr(source_guard, "_measure_regular_file", unavailable)
    assert entrypoint._install_phase8_ledger_observer(jk, authority) is True

    def worker():
        start.wait(timeout=5)
        result = authority.verify_now()
        with recorded_lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    start.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert authority.state is source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED
    assert authority.transition_sequence == 1
    assert len(results) == 2
    transitions = [(item.prior_state, item.state) for item in results]
    assert transitions.count(
        (
            source_guard.SourceAuthorityState.ACTIVE,
            source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED,
        )
    ) == 1
    assert transitions.count(
        (
            source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED,
            source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED,
        )
    ) == 1
    assert {item.transition_sequence for item in results} == {1}
    assert len(recorded) == 1
    assert recorded[0]["event_type"] is entrypoint.Phase8LedgerEventType.SOURCE_AUTHORITY_SUSPENDED
    assert recorded[0]["payload"]["prior_state"] == "ACTIVE"
    assert recorded[0]["payload"]["new_state"] == "SUSPENDED_UNVERIFIED"

    ledger.close()


def test_competing_verifications_preserve_exact_suspend_restore_history(
    tmp_path,
    monkeypatch,
):
    authority, _target = _authority_for(tmp_path)
    ledger = _ledger_for(tmp_path)
    jk = SimpleNamespace(_JACK_AUTHORITY_LEDGER=ledger)
    recorded = []
    recorded_lock = threading.Lock()
    call_lock = threading.Lock()
    start = threading.Barrier(3)
    call_count = 0
    original_measure = source_guard._measure_regular_file

    def record(**kwargs):
        with recorded_lock:
            recorded.append(kwargs)

    def unavailable_then_measurable(path):
        nonlocal call_count
        with call_lock:
            call_count += 1
            number = call_count
        if number == 1:
            raise source_guard.SourceMeasurementUnavailable("sharing violation")
        return original_measure(path)

    monkeypatch.setattr(ledger, "_advance", record)
    monkeypatch.setattr(source_guard, "_measure_regular_file", unavailable_then_measurable)
    assert entrypoint._install_phase8_ledger_observer(jk, authority) is True

    results = []

    def worker():
        start.wait(timeout=5)
        result = authority.verify_now()
        with recorded_lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    start.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert call_count == 2
    assert authority.state is source_guard.SourceAuthorityState.ACTIVE
    assert authority.transition_sequence == 2
    transitions = {
        (item.prior_state, item.state, item.transition_sequence) for item in results
    }
    assert transitions == {
        (
            source_guard.SourceAuthorityState.ACTIVE,
            source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED,
            1,
        ),
        (
            source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED,
            source_guard.SourceAuthorityState.ACTIVE,
            2,
        ),
    }
    assert [item["event_type"] for item in recorded] == [
        entrypoint.Phase8LedgerEventType.SOURCE_AUTHORITY_SUSPENDED,
        entrypoint.Phase8LedgerEventType.SOURCE_AUTHORITY_RESTORED,
    ]
    assert [
        (item["payload"]["prior_state"], item["payload"]["new_state"])
        for item in recorded
    ] == [
        ("ACTIVE", "SUSPENDED_UNVERIFIED"),
        ("SUSPENDED_UNVERIFIED", "ACTIVE"),
    ]

    ledger.close()


def test_ordering_buffer_reorders_out_of_arrival_transition_facts(tmp_path, monkeypatch):
    authority, _target = _authority_for(tmp_path)
    ledger = _ledger_for(tmp_path)
    recorded = []
    monkeypatch.setattr(ledger, "_advance", lambda **kwargs: recorded.append(kwargs))

    recorder = entrypoint._Phase8OrderedLedgerObserver(
        ledger=ledger,
        authority=authority,
        next_transition_sequence=1,
    )

    recorder.observe(
        transition_sequence=2,
        event_type=entrypoint.Phase8LedgerEventType.SOURCE_AUTHORITY_RESTORED,
        prior_state="SUSPENDED_UNVERIFIED",
        new_state="ACTIVE",
        reason="exact_reverification",
    )
    assert recorded == []

    recorder.observe(
        transition_sequence=1,
        event_type=entrypoint.Phase8LedgerEventType.SOURCE_AUTHORITY_SUSPENDED,
        prior_state="ACTIVE",
        new_state="SUSPENDED_UNVERIFIED",
        reason="measurement_unavailable",
        unavailable_component_ids=("authority.py",),
    )

    assert [item["event_type"] for item in recorded] == [
        entrypoint.Phase8LedgerEventType.SOURCE_AUTHORITY_SUSPENDED,
        entrypoint.Phase8LedgerEventType.SOURCE_AUTHORITY_RESTORED,
    ]
    assert [
        (item["payload"]["prior_state"], item["payload"]["new_state"])
        for item in recorded
    ] == [
        ("ACTIVE", "SUSPENDED_UNVERIFIED"),
        ("SUSPENDED_UNVERIFIED", "ACTIVE"),
    ]

    ledger.close()


def test_ledger_failure_cannot_change_source_suspension_or_recovery(
    tmp_path,
    monkeypatch,
):
    authority, _target = _authority_for(tmp_path)
    ledger = _ledger_for(tmp_path)
    jk = SimpleNamespace(_JACK_AUTHORITY_LEDGER=ledger)
    assert entrypoint._install_phase8_ledger_observer(jk, authority) is True

    def ledger_failure(**_kwargs):
        raise RuntimeError("synthetic ledger failure")

    monkeypatch.setattr(ledger, "_advance", ledger_failure)
    original_measure = source_guard._measure_regular_file

    def unavailable(_path):
        raise source_guard.SourceMeasurementUnavailable("sharing violation")

    monkeypatch.setattr(source_guard, "_measure_regular_file", unavailable)
    result = authority.verify_now()
    assert result.prior_state is source_guard.SourceAuthorityState.ACTIVE
    assert result.state is source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED
    assert result.transition_sequence == 1
    assert ledger.authority_frozen is True

    monkeypatch.setattr(source_guard, "_measure_regular_file", original_measure)
    result = authority.verify_now()
    assert result.prior_state is source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED
    assert result.state is source_guard.SourceAuthorityState.ACTIVE
    assert result.transition_sequence == 2
    assert result.verified is True

    ledger.close()


def test_real_authority_ledger_accepts_phase8_transition_without_owning_source_state(tmp_path):
    authority, target = _authority_for(tmp_path)
    ledger = _ledger_for(tmp_path)
    jk = SimpleNamespace(_JACK_AUTHORITY_LEDGER=ledger)
    assert entrypoint._install_phase8_ledger_observer(jk, authority) is True

    assert ledger.active_head.sequence == 0
    target.write_bytes(b"changed")
    result = authority.verify_now()

    assert result.prior_state is source_guard.SourceAuthorityState.ACTIVE
    assert result.state is source_guard.SourceAuthorityState.INVALIDATED
    assert result.transition_sequence == 1
    assert ledger.active_head.sequence == 1
    assert authority.state is source_guard.SourceAuthorityState.INVALIDATED

    ledger.close()


def test_observer_install_is_idempotent_and_never_rewraps_source_lifecycle(tmp_path):
    authority, _target = _authority_for(tmp_path)
    ledger = _ledger_for(tmp_path)
    jk = SimpleNamespace(_JACK_AUTHORITY_LEDGER=ledger)

    assert entrypoint._install_phase8_ledger_observer(jk, authority) is True
    verify = authority.verify_now
    suspend = authority._suspend_unverified
    recorder = jk._JACK_PHASE8_LEDGER_TRANSITION_RECORDER

    assert entrypoint._install_phase8_ledger_observer(jk, authority) is True
    assert authority.verify_now is verify
    assert authority._suspend_unverified is suspend
    assert jk._JACK_PHASE8_LEDGER_TRANSITION_RECORDER is recorder

    ledger.close()


def test_missing_or_mismatched_ledger_does_not_block_source_enforcement(tmp_path):
    authority, _target = _authority_for(tmp_path)

    missing = SimpleNamespace()
    assert entrypoint._install_phase8_ledger_observer(missing, authority) is False
    assert authority.verify_now().verified is True

    other = authority_ledger.AuthorityLedger(
        runtime_id="other-runtime",
        lane_id="lane-a",
        projection_root=tmp_path / "other-ledger",
        queue_capacity=16,
    )
    mismatched = SimpleNamespace(_JACK_AUTHORITY_LEDGER=other)
    assert entrypoint._install_phase8_ledger_observer(mismatched, authority) is False
    assert authority.verify_now().verified is True

    other.close()
