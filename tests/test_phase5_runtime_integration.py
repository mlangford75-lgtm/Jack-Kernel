from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

import jack_consequence_gate as gate
import jack_kernel as kernel
import jack_responses_compat as responses_compat


def test_responses_registration_installs_gate_before_route_idempotence(monkeypatch):
    events = []
    fake = SimpleNamespace(
        APP=SimpleNamespace(
            routes=[SimpleNamespace(path="/v1/responses")],
        )
    )
    monkeypatch.setattr(gate, "install", lambda module: events.append(module))

    responses_compat.register(fake)

    assert events == [fake]


def test_direct_kernel_bundled_path_converges_on_phase5_registration():
    bundled_source = inspect.getsource(kernel._install_bundled_runtime_extensions)
    register_source = inspect.getsource(responses_compat.register)

    assert "jack_responses_compat.register(module)" in bundled_source
    assert "jack_consequence_gate.install(jk)" in register_source
    assert register_source.index("jack_consequence_gate.install(jk)") < register_source.index(
        '"/v1/responses"'
    )


def _fake_kernel_namespace():
    class FakeHTTPException(RuntimeError):
        def __init__(self, *, status_code, detail):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class FakeKernel:
        HTTPException = FakeHTTPException
        PHASE4_EXECUTOR_ADMISSION_PROTOCOL_VERSION = 1
        RUNTIME_ID = "runtime-1"
        LANE_ID = "lane-1"

        @staticmethod
        def _phase4_executor_admission_decision(payload, *, expected_call=None):
            return {"outcome": "ALLOW", "payload": payload}

    return FakeKernel


def _executor_payload(*, runtime_id="runtime-1", lane_id="lane-1"):
    return {
        "protocol_version": 1,
        "runtime_id": runtime_id,
        "lane_id": lane_id,
        "tool_call_id": "phase5-integration-call",
        "tool_name": "read",
        "arguments": {"path": r"src\\engine.py"},
        "executor_cwd": r"D:\\Projects\\Jack",
        "executor_platform": "win32",
    }


def _install_admission_only(fake, monkeypatch):
    monkeypatch.setattr(gate, "_install_represented_path_gate", lambda: None)
    gate.install(fake)


def test_executor_runtime_identity_mismatch_remains_admission_scoped(monkeypatch):
    fake = _fake_kernel_namespace()
    _install_admission_only(fake, monkeypatch)

    with pytest.raises(fake.HTTPException) as caught:
        fake._phase4_executor_admission_decision(
            _executor_payload(runtime_id="wrong-runtime")
        )

    assert caught.value.status_code == 409
    assert "runtime identity mismatch" in str(caught.value.detail)


def test_executor_lane_identity_mismatch_remains_admission_scoped(monkeypatch):
    fake = _fake_kernel_namespace()
    _install_admission_only(fake, monkeypatch)

    with pytest.raises(fake.HTTPException) as caught:
        fake._phase4_executor_admission_decision(
            _executor_payload(lane_id="wrong-lane")
        )

    assert caught.value.status_code == 409
    assert "lane identity mismatch" in str(caught.value.detail)
