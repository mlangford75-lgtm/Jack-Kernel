from __future__ import annotations

import asyncio
import os
from pathlib import Path
import subprocess
import sys
import time
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


def test_stream_preserves_released_prefix_and_drains_safe_cognition_after_invalidation(tmp_path):
    authority, target = _authority_for(tmp_path)
    drained = []

    async def raw_stream(*_args, **_kwargs):
        yield b"first"
        yield b"second"
        drained.append("completed")

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
    assert drained == ["completed"]


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


def test_unexpected_required_verifier_failure_suspends_instead_of_leaving_active(
    tmp_path,
    monkeypatch,
):
    authority, _target = _authority_for(tmp_path)

    def verifier_bug(_path):
        raise ValueError("synthetic verifier failure")

    monkeypatch.setattr(source_guard, "_measure_regular_file", verifier_bug)
    with pytest.raises(source_guard.SourceAuthorityUnavailable):
        authority.verify_for_authority_boundary()
    assert authority.state is source_guard.SourceAuthorityState.SUSPENDED_UNVERIFIED


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


def test_tool_release_is_withdrawn_after_invalidation(tmp_path):
    authority, target = _authority_for(tmp_path)
    calls = []
    jk = _runtime_host(authority)

    def tool_release(calls_in):
        calls.append(("tool-release", calls_in))
        return calls_in, []

    jk._phase4_partition_structured_tool_calls = tool_release
    source_guard.activate_runtime_enforcement(jk, authority, start_periodic=False)

    target.write_bytes(b"changed")
    assert authority.verify_now().state is source_guard.SourceAuthorityState.INVALIDATED

    with pytest.raises(source_guard.SourceAuthorityInvalidated):
        jk._phase4_partition_structured_tool_calls([{"id": "call-1"}])

    assert calls == []


def test_debugging_pending_cognition_survives_when_durable_write_is_withdrawn(tmp_path):
    authority, target = _authority_for(tmp_path)
    pending = []
    writes = []
    jk = _runtime_host(authority)

    def atomic_write(*args, **kwargs):
        writes.append((args, kwargs))
        return "durable"

    jk._debugging_atomic_replace_report = atomic_write
    source_guard.activate_runtime_enforcement(jk, authority, start_periodic=False)

    target.write_bytes(b"changed")
    assert authority.verify_now().state is source_guard.SourceAuthorityState.INVALIDATED

    def completed_cognition_then_durability():
        pending.append("completed-summary")
        return jk._debugging_atomic_replace_report("report", "summary")

    with pytest.raises(source_guard.SourceAuthorityInvalidated):
        completed_cognition_then_durability()

    assert pending == ["completed-summary"]
    assert writes == []


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


def test_live_kernel_activation_wraps_real_authority_seams_without_wrapping_worker_events(tmp_path):
    code = r'''
from pathlib import Path
import jack_kernel as kernel
import jack_source_drift_guard as source_guard

kernel._install_bundled_runtime_extensions()
authority = source_guard.install(
    kernel,
    launch_entrypoint_path=Path("jack_secure_entrypoint.py").resolve(),
)
source_guard.activate_runtime_enforcement(kernel, authority, start_periodic=False)

assert getattr(kernel.KERNEL.run, "_jack_phase8_source_authority", False)
assert getattr(kernel.KERNEL.stream, "_jack_phase8_source_authority", False)
assert getattr(kernel._phase4_partition_structured_tool_calls, "_jack_phase8_source_authority", False)
assert getattr(kernel._phase4_executor_admission_decision, "_jack_phase8_source_authority", False)
assert getattr(kernel._proxy_pi_control_request, "_jack_phase8_source_authority", False)
for name in (
    "_debugging_write_open_intake_report",
    "_debugging_freeze_intake",
    "_debugging_atomic_replace_report",
):
    assert getattr(getattr(kernel, name), "_jack_phase8_source_authority", False), name
for name in (
    "_debugging_commit_pass_summary",
    "_debugging_commit_final_report",
):
    assert not getattr(getattr(kernel, name), "_jack_phase8_source_authority", False), name

# Worker event publication remains predecessor-owned observation/settlement truth.
assert not getattr(type(kernel.ORCHESTRATION_EVENTS)._publish, "_jack_phase8_source_authority", False)
assert kernel._JACK_SOURCE_RUNTIME_ENFORCEMENT_INSTALLED is True
assert authority.state is source_guard.SourceAuthorityState.ACTIVE
kernel._JACK_AUTHORITY_LEDGER.close()
'''
    env = dict(os.environ)
    env.update(
        {
            "JACK_AUTHORITY_LEDGER_DIR": str(tmp_path / "ledger"),
            "JACK_FORENSIC_ARCHIVE_MODE": "off",
            "JACK_BACKEND_MODEL": "test-model",
            "JACK_BACKEND_PROFILE": "lmstudio",
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
