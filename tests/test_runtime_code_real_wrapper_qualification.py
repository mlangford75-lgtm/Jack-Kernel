"""Qualification against Jack's real Phase-8 wrapper installation.

Read-only Phase 9B snapshot tests: no production security guard is activated.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import jack_source_drift_guard as phase8
from jack_runtime_code_guard import RuntimeCodeAuthority, RuntimeCodeIntegrityCompromised


def _secured_host(tmp_path: Path):
    target = tmp_path / "authority.py"
    target.write_text("# stable source\n", encoding="utf-8")
    authority = phase8.RuntimeSourceAuthority(runtime_id="phase9-runtime", lane_id="phase9-lane")
    authority.register_component("authority.py", target)
    authority.seal()

    async def raw_run(_body):
        return {"content": "completed"}

    async def raw_stream(_body):
        yield b"safe-prefix"
        yield b"safe-suffix"

    def executor(_payload):
        return {"outcome": "ALLOW"}

    def tool_release(_calls):
        return [], []

    async def proxy(_request, method, path, *_args, **_kwargs):
        return method, path

    host = SimpleNamespace(
        _JACK_SOURCE_AUTHORITY=authority,
        _JACK_SOURCE_AUTHORITY_INSTALLED=True,
        KERNEL=SimpleNamespace(run=raw_run, stream=raw_stream),
        _phase4_partition_structured_tool_calls=tool_release,
        _phase4_executor_admission_decision=executor,
        _proxy_pi_control_request=proxy,
        APP=None,
        JSONResponse=None,
    )
    phase8.activate_runtime_enforcement(host, authority, start_periodic=False)
    return host, authority


def _snapshot(host, authority):
    guard = RuntimeCodeAuthority()
    for label, owner, name in (
        ("kernel:run", host.KERNEL, "run"),
        ("kernel:stream", host.KERNEL, "stream"),
        ("tool-release", host, "_phase4_partition_structured_tool_calls"),
        ("executor-admission", host, "_phase4_executor_admission_decision"),
        ("orchestration", host, "_proxy_pi_control_request"),
        ("source-verifier", authority, "verify_for_authority_boundary"),
        ("source-measure", phase8, "_measure_regular_file"),
    ):
        guard.register(name=label, owner=owner, attribute=name)
    guard.register_module(name="source-module", module_name="jack_source_drift_guard")
    guard.seal()
    return guard


def test_phase8_wrappers_remain_stable_during_benign_inference_and_control(tmp_path):
    host, authority = _secured_host(tmp_path)
    guard = _snapshot(host, authority)

    async def benign():
        assert await host.KERNEL.run({}) == {"content": "completed"}
        assert [chunk async for chunk in host.KERNEL.stream({})] == [
            b"safe-prefix", b"safe-suffix"
        ]
        assert host._phase4_partition_structured_tool_calls([]) == ([], [])
        assert host._phase4_executor_admission_decision({}) == {"outcome": "ALLOW"}
        assert await host._proxy_pi_control_request(None, "GET", "/v1/status") == (
            "GET", "/v1/status"
        )

    asyncio.run(benign())
    guard.verify()
    assert authority.state is phase8.SourceAuthorityState.ACTIVE


def test_effective_phase8_run_release_rebinding_is_visible(tmp_path):
    host, authority = _secured_host(tmp_path)
    guard = _snapshot(host, authority)

    async def bypass(_body):
        return {"untrusted": "unauthorized"}

    host.KERNEL.run = bypass
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify()
    assert guard.mismatched_slots == ("kernel:run",)
    assert authority.state is phase8.SourceAuthorityState.ACTIVE


def test_effective_phase8_executor_admission_rebinding_is_visible(tmp_path):
    host, authority = _secured_host(tmp_path)
    guard = _snapshot(host, authority)
    host._phase4_executor_admission_decision = lambda _body: {"outcome": "ALLOW_ANY"}
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify()
    assert guard.mismatched_slots == ("executor-admission",)


def test_phase8_verifier_measurement_rebinding_is_visible(tmp_path, monkeypatch):
    host, authority = _secured_host(tmp_path)
    guard = _snapshot(host, authority)
    monkeypatch.setattr(phase8, "_measure_regular_file", lambda _path: None)
    with pytest.raises(RuntimeCodeIntegrityCompromised):
        guard.verify()
    assert guard.mismatched_slots == ("source-measure",)
