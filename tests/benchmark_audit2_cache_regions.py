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


async def cold_digest_latency(size):
    """Audit 3 6.6: exact cold trajectory and event-loop scheduling delay.

    Synthetic bytes only; no backend, prompt contents, or KV claims.
    Report timing rather than imposing a host-dependent performance gate.
    """
    import asyncio
    from array import array
    import hashlib

    probe = CacheBytePrefixProbe(enabled=True, byte_cap=131072)
    wire = (bytes(range(256)) * ((size + 255) // 256))[:size]

    def previous():
        h = hashlib.blake2b(digest_size=8, key=probe._key)
        sigs = array("Q")
        for item in wire:
            h.update(bytes((item,)))
            sigs.append(int.from_bytes(h.copy().digest(), "little"))
        return {"byte_length": len(wire), "sha256": hashlib.sha256(wire).hexdigest(),
                "prefix_hashes": sigs}

    def candidate():
        return probe._signature(wire)

    reference = previous()
    loop = asyncio.get_running_loop()
    rows = {"previous": [], "candidate": []}
    for label in ("previous", "candidate", "candidate", "previous") * 4:
        fn = previous if label == "previous" else candidate
        scheduled = loop.create_future()
        begin = time.perf_counter_ns()
        loop.call_soon(lambda f=scheduled, t=begin:
                       f.set_result((time.perf_counter_ns() - t) / 1e6))
        actual = fn()
        elapsed = (time.perf_counter_ns() - begin) / 1e6
        delay = await scheduled
        assert actual == reference, "exact digest trajectory changed"
        rows[label].append((elapsed, delay))
    return {"synthetic_bytes": size, "exact_signatures_equal": True,
            "trials_per_algorithm": 8, "order": "ABBA x 4",
            "measurement": "synchronous signature and ready callback latency, not inference",
            "results": {label: {
                "signature_median_ms": statistics.median(v[0] for v in values),
                "event_loop_callback_median_ms": statistics.median(v[1] for v in values),
            } for label, values in rows.items()}}


if __name__ == "__main__":
    for size in (65536, 131072):
        print("A2_W5_01_JSON " + json.dumps(run(size)), flush=True)
    import asyncio
    for size in (65536, 131072):
        print("A3_6_6_JSON " + json.dumps(asyncio.run(cold_digest_latency(size))), flush=True)
