"""Non-gating Phase 9B incremental source-verification cost evidence.

Always verifies integrity; reports timing rather than setting an arbitrary
performance threshold on hosted Windows runners.
"""
from __future__ import annotations

from pathlib import Path
import statistics
import time
from types import SimpleNamespace

from jack_runtime_code_guard import RuntimeCodeAuthority
import jack_phase9b_enforcement as phase9
import jack_runtime_code_guard as code_guard


def _guard(*, include_sources: bool):
    guard = RuntimeCodeAuthority()
    guard.register(
        name="protected", owner=SimpleNamespace(go=lambda: 1),
        attribute="go", scope="model",
    )
    if include_sources:
        guard.register_source(
            name="phase9-code", path=Path(code_guard.__file__).resolve(),
            scope="shared",
        )
        guard.register_source(
            name="phase9-enforcement", path=Path(phase9.__file__).resolve(),
            scope="shared",
        )
    guard.seal()
    return guard


def _samples(guard, n=200):
    timings = []
    for _ in range(n):
        start = time.perf_counter_ns()
        guard.verify_for("model")
        timings.append((time.perf_counter_ns() - start) / 1_000_000)
    return timings


def test_phase9_source_measurement_cost_is_reported_without_brittle_threshold():
    basic = _guard(include_sources=False)
    protected = _guard(include_sources=True)
    _samples(basic, 10)
    _samples(protected, 10)
    b = _samples(basic)
    p = _samples(protected)
    b_median = statistics.median(b)
    p_median = statistics.median(p)
    p_sorted = sorted(p)
    p95 = p_sorted[int((len(p_sorted) - 1) * 0.95)]
    print(
        "Phase9B source measurement (Windows runner): "
        f"baseline_median_ms={b_median:.5f} "
        f"source_median_ms={p_median:.5f} "
        f"source_p95_ms={p95:.5f} "
        f"increment_median_ms={p_median - b_median:.5f}"
    )
    assert protected.state == "ACTIVE"
    assert basic.state == "ACTIVE"
