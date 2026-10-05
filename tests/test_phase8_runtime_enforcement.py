from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

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


def _runtime_host(authority, *, run=None, stream=None, executor=None, proxy=None):
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
            stream=stream or default_stream,
        ),
        _phase4_executor_admission_decision=executor or default_executor,
        _proxy_pi_control_request=proxy or default_proxy,
        APP=None,
        JSONResponse=None,
    )


def test_nonstream_result_is_withheld_when_source_drifts_during_cognition(tmp_path):
    authority, target = _authority_for(tmp_path)

    async def raw_run(*_args, **_kwargs):
        target.write_bytes(b"changed")
        return "completed-cognition"

    jk = _runtime_host(authority, run=raw_run)
    source_guard.activate_runtime_enforcement(jk, authority, start_periodic=False)

    with pytest.raises(source_guard.SourceAuthorityInvalidated):
        asyncio.run(jk.KERNEL.run({}))

    assert authority.state is source_guard.SourceAuthorityState.INVALIDATED


def test_stream_preserves_released_prefix_but_blocks_future_chunks_after_invalidation(tmp_path):
    authority, target = _authority_for(tmp_path)

    async def raw_stream(*_args, **_kwargs):
        yield b"first"
        yield b"second"

    jk = _runtime_host(authority, stream=raw_stream)
    source_guard.activate_runtime_enforcement(jk, authority, start_periodic=False)

    async def exercise():
        stream = jk.KERNEL.stream({})
        first = await stream.__anext__()
        assert first == b"first"

        target.write_bytes(b"changed")
        assert authority.verify_now().state is source_guard.SourceAuthorityState.INVALIDATED

        with pytest.raises(source_guard.SourceAuthorityInvalidated):
            await stream.__anext__()

    asyncio.run(exercise())


def test_suspended_runtime_blocks_new_cognition_and_exact_reverification_restores_it(
    tmp_path,
    monkeypatch,
):
    authority, _target = _authority_for(tmp_path)
    jk = _runtime_host(authority)
    source_guard.activate_runtime_enforcement(jk, authority, start_periodic=False)
    original_measure = source_guard._measure_regular_file

    def unavailable(_path):
        raise source_guard.SourceMeasurementUnavailable("sharing violation")

    monkeypatch.setattr(source_guard, "_measure_regular_file", unavailable)
    with pytest.raises(source_guard.SourceAuthorityUnavailable):
        asyncio.run(jk.KERNEL.run({}))
    assert authority.state is source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED

    monkeypatch.setattr(source_guard, "_measure_regular_file", original_measure)
    assert asyncio.run(jk.KERNEL.run({})) == "ok"
    assert authority.state is source_guard.SourceAuthorityState.ACTIVE


def test_executor_and_mutating_orchestration_are_blocked_but_read_only_status_survives(
    tmp_path,
):
    authority, target = _authority_for(tmp_path)
    calls = []

    def executor(*_args, **_kwargs):
        calls.append("executor")
        return "admitted"

    async def proxy(_request, method, path, *_args, **_kwargs):
        calls.append((method, path))
        return {"method": method, "path": path}

    jk = _runtime_host(authority, executor=executor, proxy=proxy)
    source_guard.activate_runtime_enforcement(jk, authority, start_periodic=False)

    target.write_bytes(b"changed")
    assert authority.verify_now().state is source_guard.SourceAuthorityState.INVALIDATED

    with pytest.raises(source_guard.SourceAuthorityInvalidated):
        jk._phase4_executor_admission_decision({})
    assert "executor" not in calls

    status = asyncio.run(jk._proxy_pi_control_request(None, "GET", "/v1/status"))
    assert status == {"method": "GET", "path": "/v1/status"}

    with pytest.raises(source_guard.SourceAuthorityInvalidated):
        asyncio.run(jk._proxy_pi_control_request(None, "POST", "/v1/tasks"))
    assert ("POST", "/v1/tasks") not in calls


def test_already_admitted_control_action_may_settle_without_new_jack_admission(tmp_path):
    authority, target = _authority_for(tmp_path)
    started = asyncio.Event()
    release = asyncio.Event()

    async def proxy(_request, method, path, *_args, **_kwargs):
        assert (method, path) == ("POST", "/v1/tasks")
        started.set()
        await release.wait()
        return "worker-settled"

    jk = _runtime_host(authority, proxy=proxy)
    source_guard.activate_runtime_enforcement(jk, authority, start_periodic=False)

    async def exercise():
        admitted = asyncio.create_task(
            jk._proxy_pi_control_request(None, "POST", "/v1/tasks")
        )
        await started.wait()

        target.write_bytes(b"changed")
        assert authority.verify_now().state is source_guard.SourceAuthorityState.INVALIDATED
        release.set()
        assert await admitted == "worker-settled"

        with pytest.raises(source_guard.SourceAuthorityInvalidated):
            await jk._proxy_pi_control_request(None, "POST", "/v1/tasks")

    asyncio.run(exercise())


def test_periodic_verifier_detects_confirmed_drift_without_claiming_continuous_attestation(tmp_path):
    authority, target = _authority_for(tmp_path)
    authority.start_periodic_verification(interval_seconds=0.05)
    try:
        target.write_bytes(b"changed")
        deadline = time.monotonic() + 2.0
        while (
            authority.state is not source_guard.SourceAuthorityState.INVALIDATED
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert authority.state is source_guard.SourceAuthorityState.INVALIDATED
    finally:
        authority.stop_periodic_verification()


def test_runtime_enforcement_activation_is_idempotent_and_does_not_rewrap_seams(tmp_path):
    authority, _target = _authority_for(tmp_path)
    jk = _runtime_host(authority)

    source_guard.activate_runtime_enforcement(jk, authority, start_periodic=False)
    run = jk.KERNEL.run
    stream = jk.KERNEL.stream
    executor = jk._phase4_executor_admission_decision
    proxy = jk._proxy_pi_control_request

    source_guard.activate_runtime_enforcement(jk, authority, start_periodic=False)

    assert jk.KERNEL.run is run
    assert jk.KERNEL.stream is stream
    assert jk._phase4_executor_admission_decision is executor
    assert jk._proxy_pi_control_request is proxy
