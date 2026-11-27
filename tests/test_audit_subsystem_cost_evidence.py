"""P-4 supporting-subsystem cost and lifecycle evidence, informational.

No changes to interruption thresholds, transaction authority, or security
quarantine. Record current behavior without encoding a defect as an invariant.
"""
from __future__ import annotations

import gc
import json
import statistics
import time
import tracemalloc
import weakref
from types import SimpleNamespace

import pytest

from jack_loop_detector import ReasoningLoopDetector
from jack_loop_shadow import LongCycleShadowDetector


@pytest.mark.parametrize("repetitions", [12, 128])
def test_p4_exact_detector_retained_words_and_allocations(repetitions):
    # Isolate retention, not suffix scanning: direct _record is the exact
    # append/trim path used by feed. Distinct words avoid interned-object bias.
    count = 270000

    def exercise():
        detector = ReasoningLoopDetector(repetitions=repetitions)
        high = 0
        for index in range(count):
            detector._record("synthetic-word-" + str(index))
            high = max(high, len(detector._words))
        assert len(detector._prefix) == len(detector._words) + 1
        assert detector._words[-1] == "synthetic-word-" + str(count - 1)
        return detector, high

    start = time.perf_counter()
    detector, high = exercise()
    elapsed = time.perf_counter() - start
    retained = len(detector._words)
    del detector
    tracemalloc.start()
    try:
        detector, _ = exercise()
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    print("P4_EXACT_BUFFER " + json.dumps({
        "repetitions": repetitions, "recorded_words": count,
        "max_cycle_words": detector.max_cycle_words,
        "retained_words": retained, "peak_retained_words": high,
        "minimum_exact_suffix_capacity": detector.max_cycle_words * repetitions,
        "elapsed_seconds": elapsed, "traced_retained_bytes": current,
        "traced_peak_bytes": peak,
        "measurement": "record-only; not end-to-end loop detection",
    }, sort_keys=True))


def test_p4_long_cycle_scan_cost():
    detector = LongCycleShadowDetector()
    # Distinct words are a known negative. This measures the normal anchor
    # rejection path, not the more expensive near-match similarity branch.
    original = detector._scan
    scans = []

    def measured():
        start = time.perf_counter_ns()
        try:
            return original()
        finally:
            scans.append((time.perf_counter_ns() - start) / 1e6)

    detector._scan = measured
    start = time.perf_counter()
    for start_index in range(0, 12288, 128):
        text = " ".join("word-" + str(i) for i in range(start_index, start_index + 128)) + " "
        assert detector.feed(text) is None
    elapsed = time.perf_counter() - start
    ordered = sorted(scans)
    print("P4_SHADOW_SCAN " + json.dumps({
        "words": detector._word_count, "scan_count": len(scans),
        "median_ms": statistics.median(scans),
        "p95_ms": ordered[int((len(ordered) - 1) * .95)],
        "max_ms": max(scans), "scan_total_ms": sum(scans),
        "feed_seconds": elapsed, "retained_word_ids": len(detector._words),
        "retained_symbols": len(detector._symbols),
        "measurement": "distinct-word negative case",
    }, sort_keys=True))


def test_p4_closed_ledger_registry_retention(monkeypatch, tmp_path):
    import jack_authority_ledger as authority
    import jack_credential_guard as credential
    import jack_phase7_ledger as phase7

    # Independent registry and no process-global logging mutation in this
    # measurement. Exact production registration still executes.
    monkeypatch.setattr(phase7, "_LEDGER_BY_POLICY_OBJECT", {})
    monkeypatch.setattr(phase7, "_install_log_hook", lambda host: None)
    refs = []
    policies = []
    for index in range(16):
        runtime_id = f"p4-registry-{index}"
        policy = credential.RuntimeCredentialPolicy(
            runtime_id=runtime_id, lane_id="lane", credentials=())
        ledger = authority.AuthorityLedger(
            runtime_id=runtime_id, lane_id="lane",
            projection_root=tmp_path / runtime_id, queue_capacity=8,
        )

        async def run(*args, **kwargs):
            return None

        async def stream(*args, **kwargs):
            if False:
                yield b""

        host = SimpleNamespace(KERNEL=SimpleNamespace(run=run, stream=stream))
        phase7.install(host, ledger=ledger, credential_policy=policy)
        refs.append(weakref.ref(ledger))
        policies.append(policy)  # Keep exact policy identities stable.
        ledger.close()
        del ledger, host
    gc.collect()
    assert not phase7._LEDGER_BY_POLICY_OBJECT
    assert all(ref() is None for ref in refs)
    print("P4_LEDGER_REGISTRY " + json.dumps({
        "closed_ledgers": len(refs),
        "registry_entries_after_close": len(phase7._LEDGER_BY_POLICY_OBJECT),
        "closed_ledgers_still_alive": sum(ref() is not None for ref in refs),
        "measurement": "isolated registration and close; no policy retirement",
    }, sort_keys=True))


def test_p4_pending_agentic_lifecycle_pressure(monkeypatch, tmp_path):
    from test_agentic_coder_planner_executor import load
    k = load(monkeypatch, tmp_path, profile="balanced")
    monkeypatch.setattr(k, "_AGENTIC_SHADOW_LIMIT", 3)
    first = [{"role": "user", "content": "First task awaiting tool evidence."}]
    pending = k._agentic_begin_turn(first, fresh=True)
    assert pending
    k._agentic_turn_status(first, "awaiting_tool")
    assert k._AGENTIC_TURN_LIFECYCLES[pending].status == "awaiting_tool"
    for index in range(3):
        history = [{"role": "user", "content": f"Independent work {index}."}]
        assert k._agentic_begin_turn(history, fresh=True)
        k._agentic_mark_stage1_failure("synthetic terminal settlement")
    present = pending in k._AGENTIC_TURN_LIFECYCLES
    owned = k._agentic_forensic_journal().get(pending)
    assert owned is not None
    assert present
    assert k._AGENTIC_TURN_LIFECYCLES[pending].status == "awaiting_tool"
    assert k._agentic_begin_turn(first, fresh=False) == pending
    assert k._AGENTIC_TURN_LIFECYCLES[pending].status == "stage1_active"
    print("P4_PENDING_LIFECYCLE " + json.dumps({
        "retention_limit": 3,
        "independent_turns": 3,
        "pending_owner_retained": present,
        "durable_pending_status": owned["status"],
        "resident_lifecycles": len(k._AGENTIC_TURN_LIFECYCLES),
        "measurement": "actual host-owned lifecycle registration under pressure",
    }, sort_keys=True))


def test_p4_live_owners_not_evicted_when_all_slots_are_live(monkeypatch, tmp_path):
    from test_agentic_coder_planner_executor import load
    k = load(monkeypatch, tmp_path, profile="balanced")
    monkeypatch.setattr(k, "_AGENTIC_SHADOW_LIMIT", 2)
    owners = []
    for index in range(4):
        history = [{"role": "user", "content": f"Independent pending work {index}."}]
        owner = k._agentic_begin_turn(history, fresh=True)
        k._agentic_turn_status(history, "awaiting_tool")
        owners.append(owner)
    assert set(k._AGENTIC_TURN_LIFECYCLES) == set(owners)


def test_p4_registry_weak_binding_preserves_live_identity(monkeypatch, tmp_path):
    import jack_authority_ledger as authority
    import jack_credential_guard as credential
    import jack_phase7_ledger as phase7
    monkeypatch.setattr(phase7, "_LEDGER_BY_POLICY_OBJECT", {})
    policy = credential.RuntimeCredentialPolicy(runtime_id="p4", lane_id="lane", credentials=())
    other = credential.RuntimeCredentialPolicy(runtime_id="p4", lane_id="lane", credentials=())
    def make():
        return authority.AuthorityLedger(runtime_id="p4", lane_id="lane",
                                         projection_root=tmp_path, queue_capacity=8)
    one, two = make(), make()
    try:
        phase7._bind_policy_ledger(policy, one)
        phase7._bind_policy_ledger(other, two)
        phase7._bind_policy_ledger(policy, one)
        assert phase7._ledger_for_policy(policy) is one
        assert phase7._ledger_for_policy(other) is two
        with pytest.raises(RuntimeError, match="cannot bind two ledgers"):
            phase7._bind_policy_ledger(policy, two)
    finally:
        one.close()
        two.close()
