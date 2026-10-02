from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

import pytest

import jack_authority_ledger as ledger


def make(tmp_path: Path, *, runtime_id="runtime-a", lane_id="lane-a", capacity=64, instance=None):
    return ledger.AuthorityLedger(
        runtime_id=runtime_id,
        lane_id=lane_id,
        projection_root=tmp_path,
        queue_capacity=capacity,
        ledger_instance_id=instance,
    )


def test_chain_is_process_local_canonical_and_predecessor_linked(tmp_path):
    active = make(tmp_path, instance="instance-a")
    first = active.record_canary_match(canary_id="kernel:test", tier="A")
    second = active.record_reserved_evidence_namespace_block()
    assert first.sequence == 1 and first.previous_record_digest is None
    assert second.sequence == 2 and second.previous_record_digest == first.record_digest
    assert active.active_head.record_digest == second.record_digest
    assert len(first.record_digest) == len(second.record_digest) == 64
    assert active.wait_for_projection()
    assert active.projection_head_path.name == "projection_head.json"
    projected = json.loads(active.projection_head_path.read_text(encoding="utf-8"))
    assert projected["ledger_instance_id"] == "instance-a"
    assert projected["last_projected_sequence"] == 2
    assert projected["projection_complete"] is True
    active.close()


def test_restart_never_promotes_old_projection_into_new_process_authority(tmp_path):
    first = make(tmp_path)
    first.record_reserved_evidence_namespace_block()
    assert first.wait_for_projection()
    old_instance = first.ledger_instance_id
    old_projection = first.projection_head_path
    first.close()
    second = make(tmp_path)
    assert second.runtime_id == first.runtime_id and second.lane_id == first.lane_id
    assert second.ledger_instance_id != old_instance
    assert second.active_head == ledger.LedgerHead(sequence=0, record_digest=None)
    assert second.instance_dir != first.instance_dir
    assert old_projection.exists()
    second.close()


def test_two_runtime_heads_advance_independently(tmp_path, monkeypatch):
    runtime_a = make(tmp_path, runtime_id="runtime-a", lane_id="lane-a", instance="instance-a")
    runtime_b = make(tmp_path, runtime_id="runtime-b", lane_id="lane-b", instance="instance-b")
    monkeypatch.setattr(runtime_a, "_enqueue_projection_locked", lambda _record: False)
    monkeypatch.setattr(runtime_b, "_enqueue_projection_locked", lambda _record: False)
    a1 = runtime_a.record_canary_match(canary_id="a:1", tier="A")
    b1 = runtime_b.record_canary_match(canary_id="b:1", tier="B")
    a2 = runtime_a.record_reserved_evidence_namespace_block()
    assert (a1.sequence, a2.sequence) == (1, 2) and b1.sequence == 1
    assert runtime_a.active_head.record_digest == a2.record_digest
    assert runtime_b.active_head.record_digest == b1.record_digest
    assert a2.previous_record_digest == a1.record_digest
    assert b1.previous_record_digest is None


def test_bounded_projection_queue_loses_projection_not_authority(tmp_path, monkeypatch):
    active = make(tmp_path, capacity=1, instance="bounded")
    monkeypatch.setattr(active, "_ensure_writer", lambda: None)
    active.record_reserved_evidence_namespace_block()
    second = active.record_canary_match(canary_id="kernel:two", tier="B")
    status = active.projection_status()
    assert second.sequence == 2 and active.active_head.sequence == 2
    assert status.queued_records == 1
    assert status.lost_projection_count == 1
    assert (status.first_lost_sequence, status.last_lost_sequence) == (2, 2)
    assert status.projection_complete is False


def test_active_head_corruption_freezes_only_ledger_advancement(tmp_path):
    active = make(tmp_path, instance="corrupt")
    active.record_reserved_evidence_namespace_block()
    before = active.active_head
    active._head = ledger.LedgerHead(sequence=99, record_digest="0" * 64)
    with pytest.raises(ledger.LedgerAuthorityFrozen):
        active.record_reserved_evidence_namespace_block()
    assert active.authority_frozen is True
    assert before.sequence == 1
    active.close()


def test_concurrent_writers_form_one_atomic_process_chain(tmp_path, monkeypatch):
    active = make(tmp_path, capacity=256, instance="concurrent")
    monkeypatch.setattr(active, "_enqueue_projection_locked", lambda _record: False)
    records = []
    records_lock = threading.Lock()
    def writer(index):
        record = active.record_canary_match(canary_id=f"c:{index}", tier="A")
        with records_lock:
            records.append(record)
    threads = [threading.Thread(target=writer, args=(i,)) for i in range(100)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    ordered = sorted(records, key=lambda item: item.sequence)
    assert [item.sequence for item in ordered] == list(range(1, 101))
    assert ordered[0].previous_record_digest is None
    for prior, successor in zip(ordered, ordered[1:]):
        assert successor.previous_record_digest == prior.record_digest
    assert active.active_head.sequence == 100
    active.close()


def test_concurrent_projection_enqueue_order_matches_authority_sequence(tmp_path, monkeypatch):
    active = make(tmp_path, capacity=128, instance="queue-order")
    monkeypatch.setattr(active, "_ensure_writer", lambda: None)
    threads = [threading.Thread(target=active.record_canary_match, kwargs={"canary_id": f"queue:{i}", "tier": "A"}) for i in range(100)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    queued = []
    while True:
        try: queued.append(active._projection_queue.get_nowait())
        except queue.Empty: break
    assert [record.sequence for record in queued] == list(range(1, 101))


def test_record_projection_failure_is_durability_only(tmp_path, monkeypatch):
    active = make(tmp_path, instance="io-fail")
    monkeypatch.setattr(active, "_atomic_write", lambda _path, _data: (_ for _ in ()).throw(OSError("synthetic disk failure")))
    record = active.record_reserved_evidence_namespace_block()
    assert record.sequence == 1 and active.wait_for_projection()
    status = active.projection_status()
    assert active.authority_frozen is False and active.active_head.sequence == 1
    assert status.lost_projection_count == 1 and status.first_lost_sequence == 1
    assert status.projection_complete is False and status.projection_metadata_degraded is True
    active.close()


def test_closed_event_schema_rejects_unsafe_metadata_and_loose_booleans(tmp_path):
    active = make(tmp_path, instance="closed-schema")
    with pytest.raises(ValueError): active.record_canary_match(canary_id="secret with spaces", tier="A")
    with pytest.raises(ValueError): active.record_canary_match(canary_id="safe:id", tier="Z")
    with pytest.raises(TypeError):
        active.record_executor_identity_decision(runtime_matches="yes", lane_matches=True, outcome="ALLOW", containment_scope="none")
    assert active.active_head.sequence == 0
    active.close()


def test_committed_projection_bytes_are_immutable_after_authority_transition(tmp_path, monkeypatch):
    active = make(tmp_path, instance="immutable-projection")
    monkeypatch.setattr(active, "_ensure_writer", lambda: None)

    record = active.record_canary_match(canary_id="kernel:original", tier="A")
    with pytest.raises(TypeError):
        record.payload["canary_id"] = "changed-after-digest"

    caller_copy = dict(record.payload)
    caller_copy["canary_id"] = "changed-copy"

    projection = active._projection_queue.get_nowait()
    try:
        assert isinstance(projection, ledger.ProjectionRequest)
        assert projection.sequence == record.sequence
        assert projection.record_digest == record.record_digest
        active._project_one(projection)
    finally:
        active._projection_queue.task_done()

    projected_files = list(active.records_dir.glob("*.json"))
    assert len(projected_files) == 1
    persisted = json.loads(projected_files[0].read_text(encoding="utf-8"))
    stored_digest = persisted.pop("record_digest")
    assert persisted["payload"]["canary_id"] == "kernel:original"
    assert ledger._digest_record_material(persisted) == stored_digest == record.record_digest
    active.close()
