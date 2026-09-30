from __future__ import annotations

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


def test_bundled_extension_install_exposes_phase5_gate():
    kernel._install_bundled_runtime_extensions()

    assert kernel._JACK_CONSEQUENCE_GATE_INSTALLED is True
    assert kernel.evaluate_consequence is gate.evaluate_consequence
    assert kernel.ContainmentScope is gate.ContainmentScope


def _executor_payload(*, runtime_id=None, lane_id=None):
    return {
        "protocol_version": kernel.PHASE4_EXECUTOR_ADMISSION_PROTOCOL_VERSION,
        "runtime_id": runtime_id or kernel.RUNTIME_ID,
        "lane_id": lane_id or kernel.LANE_ID,
        "tool_call_id": "phase5-integration-call",
        "tool_name": "read",
        "arguments": {"path": r"src\\engine.py"},
        "executor_cwd": r"D:\\Projects\\Jack",
        "executor_platform": "win32",
    }


def test_executor_runtime_identity_mismatch_remains_admission_scoped():
    kernel._install_bundled_runtime_extensions()

    with pytest.raises(kernel.HTTPException) as caught:
        kernel._phase4_executor_admission_decision(
            _executor_payload(runtime_id="wrong-runtime")
        )

    assert caught.value.status_code == 409
    assert "runtime identity mismatch" in str(caught.value.detail)


def test_executor_lane_identity_mismatch_remains_admission_scoped():
    kernel._install_bundled_runtime_extensions()

    with pytest.raises(kernel.HTTPException) as caught:
        kernel._phase4_executor_admission_decision(
            _executor_payload(lane_id="wrong-lane")
        )

    assert caught.value.status_code == 409
    assert "lane identity mismatch" in str(caught.value.detail)
