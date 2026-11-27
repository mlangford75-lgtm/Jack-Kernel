"""P-2/P-3 evidence: actual backend request construction, no model or network.

MockTransport captures the exact request after projection and serialization.
The tail projection is a comparison only, not an inference or authority change.
Timing is informational; no arbitrary performance threshold.
"""
from __future__ import annotations

import asyncio
import copy
import json
import statistics
import time
import tracemalloc

import httpx
import pytest

from test_agentic_coder_planner_executor import load, response, spec_text


def wire_bytes(message):
    return json.dumps(message, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def compare(left, right):
    matched = 0
    for a, b in zip(left, right):
        if a != b:
            break
        matched += 1
    return {
        "matched_messages": matched,
        "matched_message_json_bytes": sum(len(wire_bytes(m)) for m in left[:matched]),
        "first_changed_index": matched if matched < min(len(left), len(right)) else None,
    }


def hypothetical_tail(messages):
    """Offline candidate only; never dispatched to a provider."""
    result = copy.deepcopy(messages)
    prefix, separator, spec = result[0]["content"].partition(
        "JACK CODER DEVELOPER SPEC SHEET"
    )
    assert separator and result[-1]["role"] == "user"
    result[0]["content"] = prefix.rstrip()
    result.insert(-1, {"role": "assistant", "content": separator + spec})
    return result


async def mock_backend(k, received):
    backend = k.OpenAICompatibleBackend(k.CFG)
    await backend._client.aclose()

    def reply(request):
        received.append(json.loads(request.content))
        if received[-1]["stream"]:
            frames = [
                {"choices": [{"delta": {"content": "Completed."}, "finish_reason": None}]},
                {"choices": [{"delta": {}, "finish_reason": "stop"}]},
            ]
            body = "".join("data: " + json.dumps(item) + "\n\n" for item in frames)
            return httpx.Response(200, content=body + "data: [DONE]\n\n",
                                  headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json=response("Completed.", reasoning=""))

    backend._client = httpx.AsyncClient(transport=httpx.MockTransport(reply))

    async def model():
        return "test-model"

    backend.resolve_model = model
    return backend


async def dispatch(k, backend, history, streamed=False):
    kwargs = dict(messages=history, secondary_system="Stable caller instructions.",
                  profile=k.STAGES["extended_initial"], tools=None, tool_choice="none")
    if streamed:
        return [event async for event in backend.chat_stream(**kwargs)]
    return await backend.chat(**kwargs)


@pytest.mark.parametrize("mode", ["flash", "thorough"])
@pytest.mark.parametrize("streamed", [False, True])
def test_p2_three_turn_coder_wire_prefix_evidence(monkeypatch, tmp_path, mode, streamed):
    monkeypatch.setenv("JACK_CACHE_PREFIX_BYTE_DIAGNOSTICS", "1")
    k = load(monkeypatch, tmp_path, planner=mode)
    received, reports = [], []

    async def run():
        backend = await mock_backend(k, received)
        original = backend._cache_byte_probe.observe

        def observe(*args, **kwargs):
            report = original(*args, **kwargs)
            if report is not None:
                reports.append(report)
            return report

        backend._cache_byte_probe.observe = observe
        completed = []
        try:
            for index in range(1, 4):
                request = f"Authenticated user request {index}: verify task {index}."
                history = copy.deepcopy(completed) + [{"role": "user", "content": request}]
                plan = spec_text(f"distinct objective {index}")
                k._coder_append_plan(history, response(plan, reasoning=f"PRIVATE_PLANNER_R1_{index}"))
                frozen = copy.deepcopy(history)
                await dispatch(k, backend, history, streamed)
                assert history == frozen
                wire = received[-1]["messages"]
                assert wire[0]["role"] == "system"
                assert sum(m["role"] == "system" for m in wire) == 1
                assert plan in wire[0]["content"]
                assert wire[-1] == {"role": "user", "content": request}
                assert "PRIVATE_PLANNER_R1_" not in json.dumps(wire)
                assert [m for m in wire if m["role"] != "system"] == completed + [
                    {"role": "user", "content": request}
                ]
                completed += [{"role": "user", "content": request},
                              {"role": "assistant", "content": f"Completed task {index}."}]
        finally:
            await backend._client.aclose()

    asyncio.run(run())
    assert len(received) == len(reports) == 3
    wires = [item["messages"] for item in received]
    comparisons = []
    for i in (1, 2):
        actual = compare(wires[i - 1], wires[i])
        tail = compare(hypothetical_tail(wires[i - 1]), hypothetical_tail(wires[i]))
        probe = reports[i]["same_stage"]
        assert actual["first_changed_index"] == 0
        assert probe["relation"] == "first_message_changed"
        comparisons.append({
            "turn": i + 1, "actual": actual, "offline_tail_candidate": tail,
            "byte_probe": probe,
        })
    print("P2_WIRE_EVIDENCE " + json.dumps({
        "mode": mode, "streamed": streamed, "comparisons": comparisons,
        "measurement": "message-json-prefix-not-tokenized-KV-cache",
    }, sort_keys=True))


def _peak_working_set():
    # Windows process-wide high-water mark, not attributable allocation bytes.
    import os
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
            )
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    counter = Counters()
    counter.cb = ctypes.sizeof(counter)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),
                                    ctypes.byref(counter), counter.cb):
        return None
    return int(counter.PeakWorkingSetSize)


@pytest.mark.parametrize("size_kib", [64, 128])
def test_p3_request_diagnostic_cost_evidence(monkeypatch, tmp_path, size_kib):
    k = load(monkeypatch, tmp_path, profile="balanced")
    received = []
    history = []
    # Eight stable historical U/A pairs, then an active user. The size label
    # denotes content bytes; the actual serialized request size is reported.
    for i in range(8):
        history.extend([
            {"role": "user", "content": f"Historical question {i}."},
            {"role": "assistant", "content": ("abcd" * (size_kib * 1024 // 32))},
        ])
    history.append({"role": "user", "content": "Summarize the previous findings."})

    async def run():
        backend = await mock_backend(k, received)
        times = {}
        for owner, name, label in (
            (backend._cache_router, "plan", "cache_router"),
            (backend, "_agentic_cache_prefix_probe", "message_prefix"),
            (backend._cache_byte_probe, "capture_regions", "byte_regions"),
            (backend._cache_byte_probe, "observe", "byte_probe"),
            (backend, "_stabilize_stage1_tool_cache_system", "system_stability"),
        ):
            original = getattr(owner, name)

            def measured(*args, _original=original, _label=label, **kwargs):
                start = time.perf_counter_ns()
                try:
                    return _original(*args, **kwargs)
                finally:
                    times.setdefault(_label, []).append(
                        (time.perf_counter_ns() - start) / 1e6
                    )

            setattr(owner, name, measured)

        results = []
        reference = None
        try:
            for enabled in (False, True):
                backend._cache_byte_probe.enabled = enabled
                await dispatch(k, backend, history)
                times.clear()
                elapsed = []
                for _ in range(3):
                    start = time.perf_counter_ns()
                    await dispatch(k, backend, history)
                    elapsed.append((time.perf_counter_ns() - start) / 1e6)
                timing = {name: statistics.median(values) for name, values in times.items()}
                payload = received[-1]
                # Compare message projection, not optional cache-routing metadata.
                if reference is None:
                    reference = copy.deepcopy(payload["messages"])
                else:
                    assert payload["messages"] == reference
                # Trace allocations in a separate pass so tracing overhead
                # cannot pollute timing measurements.
                tracemalloc.start()
                try:
                    await dispatch(k, backend, history)
                    _, peak = tracemalloc.get_traced_memory()
                finally:
                    tracemalloc.stop()
                results.append({
                    "byte_probe_enabled": enabled,
                    "elapsed_median_ms": statistics.median(elapsed),
                    "component_median_ms": timing,
                    "request_json_bytes": len(wire_bytes(payload)),
                    "traced_peak_bytes": peak,
                    "process_peak_working_set_bytes": _peak_working_set(),
                })
        finally:
            await backend._client.aclose()
        print("P3_COST_EVIDENCE " + json.dumps({
            "historical_content_kib": size_kib, "runs": results,
            "measurement": "mock-transport synchronous request path; no inference",
            "rss_scope": "whole-process high-water, cumulative; not per-probe attribution",
        }, sort_keys=True))

    asyncio.run(run())
