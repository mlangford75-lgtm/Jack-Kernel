from __future__ import annotations

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

    # Stable ACTIVE verification is intentionally not a ledger event.
    assert authority.verify_now().verified is True
    assert recorded == []

    original_measure = source_guard._measure_regular_file

    def unavailable(_path):
        raise source_guard.SourceMeasurementUnavailable("sharing violation")

    monkeypatch.setattr(source_guard, "_measure_regular_file", unavailable)
    result = authority.verify_now()
    assert result.state is source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED
    assert len(recorded) == 1

    # Remaining suspended under the same fact does not spam the chain.
    authority.verify_now()
    assert len(recorded) == 1

    monkeypatch.setattr(source_guard, "_measure_regular_file", original_measure)
    result = authority.verify_now()
    assert result.state is source_guard.SourceAuthorityState.ACTIVE
    assert len(recorded) == 2

    target.write_bytes(b"changed")
    result = authority.verify_now()
    assert result.state is source_guard.SourceAuthorityState.INVALIDATED
    assert len(recorded) == 3

    # INVALIDATED is terminal; repeat checks do not duplicate the drift fact.
    authority.verify_now()
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
    assert len(recorded) == 1
    event = recorded[0]
    assert event["event_type"] is entrypoint.Phase8LedgerEventType.SOURCE_AUTHORITY_SUSPENDED
    assert event["payload"]["reason"] == "verification_operation_failed"
    assert event["payload"]["prior_state"] == "ACTIVE"
    assert event["payload"]["new_state"] == "SUSPENDED_UNVERIFIED"

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
    assert result.state is source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED
    assert ledger.authority_frozen is True

    # Ledger failure/freeze cannot become source recovery authority or block it.
    monkeypatch.setattr(source_guard, "_measure_regular_file", original_measure)
    result = authority.verify_now()
    assert result.state is source_guard.SourceAuthorityState.ACTIVE
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

    assert result.state is source_guard.SourceAuthorityState.INVALIDATED
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

    assert entrypoint._install_phase8_ledger_observer(jk, authority) is True
    assert authority.verify_now is verify
    assert authority._suspend_unverified is suspend

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
