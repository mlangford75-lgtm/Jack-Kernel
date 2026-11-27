"""P-1: isolated Windows release-path benchmark, not a model throughput test.

Run from repo root: python tests/benchmark_secured_stream.py
Uses actual Jack HTTP routes, actual bundled and secured release wrappers, and
a deterministic synthetic SSE producer installed before any authority is sealed.
No listening socket, real credentials, provider calls or production guard bypass.
Timing is informational; exact logical response and authority state are asserted.
"""
from __future__ import annotations

import asyncio
import cProfile
import json
import os
from pathlib import Path
import platform
import pstats
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SYNTHETIC_KEY = "benchmark-test-only-77c9d0ce6e2a4da18d1b"
MARKER = "P1_BENCHMARK_JSON "
FRAMES = 1000
REPEATS = 3


def summary(values):
    ordered = sorted(values)
    return {
        "median": statistics.median(ordered),
        "p95": ordered[int((len(ordered) - 1) * .95)],
        "max": ordered[-1],
    }


def profile_summary(profiler):
    """Report aggregate call timing only; no inputs, locals or source text.

    Inclusive times overlap; exclusive totals are additive. Strip host paths
    and restrict rows to known repository modules plus aggregate total.
    """
    stats = pstats.Stats(profiler)
    selected = {
        "jack_runtime_code_guard.py", "jack_source_drift_guard.py",
        "jack_runtime_code_enforcement.py", "jack_policy_integrity_canary_enforcement.py",
        "jack_policy_integrity_credential_enforcement.py", "jack_policy_integrity_dynamic_authority.py",
        "jack_policy_integrity_path_enforcement.py", "jack_evidence_guard.py",
        "jack_credential_guard.py", "jack_diagnostic_privacy.py",
    }
    rows = []
    modules = {}
    for (filename, line, name), (primitive, calls, own, cumulative, _) in stats.stats.items():
        module = Path(filename).name
        if module not in selected:
            continue
        modules[module] = modules.get(module, 0.0) + own
        rows.append({"module": module, "line": line, "function": name,
                     "primitive_calls": primitive, "calls": calls,
                     "exclusive_seconds": own, "inclusive_seconds": cumulative})
    rows.sort(key=lambda row: row["inclusive_seconds"], reverse=True)
    return {"profile_total_seconds": stats.total_tt,
            "module_exclusive_seconds": modules, "top_inclusive": rows[:40]}


def child(mode):
    import httpx
    import jack_kernel as jk

    # Fixed before authority sealing: changing the captured scalar is executable drift.
    count = FRAMES
    content = " synthetic."
    def frame(delta, finish=None):
        return ("data: " + json.dumps({
            "id": "chatcmpl-p1-benchmark", "object": "chat.completion.chunk",
            "created": 1, "model": jk.CFG.virtual_model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }) + "\n\n").encode("utf-8")

    first = frame({"role": "assistant"})
    token = frame({"content": content})
    final = frame({}, "stop")

    async def synthetic_stream(*args, **kwargs):
        yield first
        for _ in range(count):
            # Provide a scheduler opportunity just as a ready upstream
            # transport may; ticker gaps then expose synchronous release work.
            await asyncio.sleep(0)
            yield token
        yield final
        yield b"data: [DONE]\n\n"

    jk.KERNEL.stream = synthetic_stream
    jk._install_bundled_runtime_extensions()
    if mode == "secured":
        import jack_secure_entrypoint as secure
        import jack_source_drift_guard as phase8
        import jack_policy_integrity_path_enforcement as path
        import jack_policy_integrity_canary_enforcement as canary
        import jack_policy_integrity_credential_enforcement as credential
        import jack_diagnostic_privacy as privacy
        import jack_runtime_code_enforcement as phase9

        source = phase8.install(jk, launch_entrypoint_path=Path(secure.__file__).resolve())
        secure._install_phase8_ledger_observer(jk, source)
        phase8.activate_runtime_enforcement(jk, source)
        path.install(jk)
        canary.install(jk)
        credential.install(jk)
        privacy.install(jk)
        guard = phase9.install(jk)
        assert jk._secured_serving_ready()
        assert guard.state == "ACTIVE"
    else:
        assert not jk._secured_serving_ready()

    async def exercise():
        transport = httpx.ASGITransport(app=jk.APP)
        async with jk.APP.router.lifespan_context(jk.APP):
            async with httpx.AsyncClient(
                transport=transport, base_url="http://isolated-p1.test",
                headers={"Authorization": "Bearer " + SYNTHETIC_KEY},
                timeout=None,
            ) as client:
                async def request():
                    response = await client.post("/v1/chat/completions", json={
                        "model": jk.CFG.virtual_model,
                        "messages": [{"role": "user", "content": "Benchmark synthetic stream."}],
                        "stream": True,
                    })
                    assert response.status_code == 200, (
                        response.status_code, response.text[:500],
                        guard.mismatched_slots if mode == "secured" else (),
                    )
                    chunks = []
                    finishes = []
                    done = 0
                    for line in response.text.splitlines():
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:]
                        if raw == "[DONE]":
                            done += 1
                            continue
                        for choice in json.loads(raw).get("choices", []):
                            chunks.append(choice.get("delta", {}).get("content") or "")
                            if choice.get("finish_reason"):
                                finishes.append(choice["finish_reason"])
                    assert "".join(chunks) == content * count, "logical stream mismatch"
                    assert finishes == ["stop"] and done == 1
                    return len(response.content)

                await request()
                elapsed = []
                gaps = []
                sizes = []
                for _ in range(REPEATS):
                    sample = []
                    stop = False
                    async def ticker():
                        previous = time.perf_counter()
                        while not stop:
                            await asyncio.sleep(0)
                            now = time.perf_counter()
                            sample.append((now - previous) * 1000)
                            previous = now
                    task = asyncio.create_task(ticker())
                    await asyncio.sleep(0)
                    start = time.perf_counter()
                    try:
                        sizes.append(await request())
                        elapsed.append(time.perf_counter() - start)
                    finally:
                        stop = True
                        await task
                    gaps.append(summary(sample))
                attribution = None
                if mode == "secured":
                    # Separate profiling request: do not contaminate wall-clock
                    # samples or replace any sealed callable. cProfile records
                    # call/time metadata, not credentials or message contents.
                    profiler = cProfile.Profile()
                    profiler.enable()
                    try:
                        profiled_size = await request()
                    finally:
                        profiler.disable()
                    assert profiled_size == sizes[0]
                    attribution = profile_summary(profiler)
                    assert guard.state == "ACTIVE", guard.mismatched_slots
                    assert source.state is phase8.SourceAuthorityState.ACTIVE
                print(MARKER + json.dumps({
                    "mode": mode, "frames": FRAMES, "repeats": REPEATS,
                    "seconds": elapsed,
                    "frames_per_second": [FRAMES / item for item in elapsed],
                    "scheduler_gap_ms": gaps,
                    "released_bytes": sizes,
                    "profile_attribution": attribution,
                    "platform": platform.platform(),
                    "python": platform.python_version(),
                }), flush=True)

    asyncio.run(exercise())


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        child(sys.argv[2])
        return
    if os.name != "nt":
        raise SystemExit("This benchmark requires the Windows-qualified path authority.")
    results = []
    with tempfile.TemporaryDirectory(prefix="jack-p1-") as temporary:
        root = Path(temporary)
        for mode in ("bundled", "secured"):
            folder = root / mode
            folder.mkdir()
            home = folder / "home"
            appdata = folder / "appdata"
            home.mkdir()
            appdata.mkdir()
            env = {key: value for key, value in os.environ.items()
                   if not key.upper().startswith("JACK_")}
            env.update({
                "HOME": str(home), "USERPROFILE": str(home), "APPDATA": str(appdata),
                "JACK_RUNTIME_ID": "p1-" + mode, "JACK_LANE_ID": "p1-" + mode,
                "JACK_RUNTIME_REGISTRY_DIR": str(folder / "registry"),
                "JACK_AUTHORITY_LEDGER_DIR": str(folder / "ledger"),
                "JACK_API_KEY": SYNTHETIC_KEY,
                "JACK_BACKEND_PROFILE": "custom", "JACK_BACKEND_MODEL": "test-model",
                "JACK_BACKEND_BASE_URL": "http://127.0.0.1:9/v1",
                "JACK_REASONING_LEVEL": "off", "JACK_FORENSIC_ARCHIVE_MODE": "off",
                "JACK_CONTEXT_MONITOR": "0", "JACK_CANARY_POLICY_JSON": "",
                "JACK_PATH_POLICY_JSON": "",
            })
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--child", mode],
                cwd=ROOT, env=env, text=True, capture_output=True, timeout=900,
            )
            if result.returncode:
                raise RuntimeError(f"{mode} benchmark failed:\n{result.stdout}\n{result.stderr}")
            lines = [line for line in result.stdout.splitlines() if line.startswith(MARKER)]
            assert len(lines) == 1, result.stdout
            measured = json.loads(lines[0][len(MARKER):])
            results.append(measured)
            print(lines[0], flush=True)
    base, secured = results
    b = statistics.median(base["seconds"])
    s = statistics.median(secured["seconds"])
    print(MARKER + json.dumps({
        "median_bundled_seconds": b, "median_secured_seconds": s,
        "increment_ms_per_source_frame": (s - b) * 1000 / FRAMES,
        "secured_to_bundled_time_ratio": s / b,
    }), flush=True)


if __name__ == "__main__":
    main()
