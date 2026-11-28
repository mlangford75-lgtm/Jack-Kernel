"""Audit 2 W5-01: isolated diagnostic region reuse, not model/KV performance.

Compare the former immediate-predecessor-only capture lookup with current
per-stage capture lookup using identical synthetic prompts and reports.
Run from a fresh checkout: python tests/benchmark_audit2_cache_regions.py
"""
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jack_cache_prefix_diagnostics import CacheBytePrefixProbe


class PreviousRegionCapture(CacheBytePrefixProbe):
    def capture_regions(self, *args):
        retained = self._last_by_stage
        try:
            self._last_by_stage = {}
            return super().capture_regions(*args)
        finally:
            self._last_by_stage = retained


def observation(probe, stage, size, step):
    directive = stage + ":" + ("a" if stage == "Architect" else "b") * size
    caller = {"role": "system", "content": "common caller"}
    user = {"role": "user", "content": "synthetic history " + str(step // 4)}
    prepared = [caller, user]
    messages = [{"role": "system", "content": directive}, caller, user]
    begin = time.perf_counter_ns()
    regions = probe.capture_regions(messages, prepared, directive)
    capture_ms = (time.perf_counter_ns() - begin) / 1e6
    folded = [{"role": "system", "content": directive + "\n\n" + caller["content"]}, user]
    report = probe.observe(folded, stage, regions)
    return report, capture_ms, (time.perf_counter_ns() - begin) / 1e6


def retained_bytes(probe):
    # Count unique retained digest arrays, not all Python object overhead.
    seen = {}
    for snapshot in probe._last_by_stage.values():
        signatures = list(snapshot["messages"]) + [r["sig"] for r in snapshot["regions"]]
        if snapshot["system"] is not None:
            signatures.append(snapshot["system"])
        for signature in signatures:
            array = signature["prefix_hashes"]
            seen[id(array)] = len(array) * array.itemsize
    return sum(seen.values())


def run(size):
    rows = {"previous": [], "candidate": []}
    reports = {}
    for label in ("previous", "candidate", "candidate", "previous"):
        cls = PreviousRegionCapture if label == "previous" else CacheBytePrefixProbe
        probe = cls(enabled=True, byte_cap=131072)
        trace = []
        measurements = []
        for step in range(12):
            stage = ("Architect", "Coder")[step % 2]
            report, capture, total = observation(probe, stage, size, step)
            trace.append(report)
            measurements.append((capture, total))
        if reports:
            assert trace == reports["reference"], "diagnostic equivalence changed"
        else:
            reports["reference"] = trace
        rows[label].append({
            "cold_capture_ms": statistics.median([v[0] for v in measurements[:2]]),
            "warm_capture_ms": statistics.median([v[0] for v in measurements[2:]]),
            "warm_total_ms": statistics.median([v[1] for v in measurements[2:]]),
            "retained_digest_array_bytes": retained_bytes(probe),
            "retained_stages": len(probe._last_by_stage),
        })
    return {"synthetic_region_bytes": size, "order": "ABBA",
            "exact_reports_equal": True, "runs": rows}


if __name__ == "__main__":
    for size in (65536, 131072):
        print("A2_W5_01_JSON " + json.dumps(run(size)), flush=True)
