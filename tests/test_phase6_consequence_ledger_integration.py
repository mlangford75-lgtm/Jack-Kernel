from __future__ import annotations

import json
from enum import Enum
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

import jack_authority_ledger as authority_ledger
import jack_consequence_gate as gate
import jack_path_policy as path_policy


class Outcome(str, Enum):
    ALLOW = "ALLOW"
    DENY_AND_CONTINUE = "DENY_AND_CONTINUE"
    REQUIRE_USER_DECISION = "REQUIRE_USER_DECISION"
    HARD_INTERRUPT = "HARD_INTERRUPT"


class NoopKernel:
    async def run(self, *_args, **_kwargs):
        return None

    async def stream(self, *_args, **_kwargs):
        if False:
            yield None


def build_policy():
    return path_policy.build_runtime_path_policy(
        runtime_id="runtime-gate",
        lane_id="lane-gate",
        raw_json=json.dumps(
            {
                "version": 1,
                "workspace_root": r"D:\\Projects\\Jack",
                "never_paths": [r"D:\\Sensitive"],
            }
        ),
        host_environment={
            "SystemRoot": r"C:\\Windows",
            "WINDIR": r"C:\\Windows",
            "SystemDrive": "C:",
            "USERPROFILE": r"C:\\Users\\Operator",
        },
    )


def read_records(active):
    assert active.wait_for_projection()
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(active.records_dir.glob("*.json"))
    ]


def test_gate_records_live_path_and_executor_identity_without_changing_disposition(tmp_path, monkeypatch):
    monkeypatch.setenv("JACK_AUTHORITY_LEDGER_DIR", str(tmp_path))
    original_authorizer = path_policy.authorize_represented_path
    policy = build_policy()

    fake = SimpleNamespace(
        SecurityOutcome=Outcome,
        RUNTIME_ID="runtime-gate",
        LANE_ID="lane-gate",
        CFG=SimpleNamespace(runtime_registry_dir=""),
        KERNEL=NoopKernel(),
        HTTPException=HTTPException,
        PHASE4_EXECUTOR_ADMISSION_PROTOCOL_VERSION=1,
        _install_bundled_runtime_extensions=lambda: None,
        _JACK_EVIDENCE_PROVENANCE_GUARD_INSTALLED=True,
    )

    # This test targets Gate integration. Evidence-release hooks are covered
    # separately and do not need to mutate the global evidence filter here.
    monkeypatch.setattr(authority_ledger, "_install_evidence_release_hooks", lambda *_args: None)

    def partition(_calls):
        decision = path_policy.authorize_represented_path(policy, r"D:\\Other\\artifact.txt")
        return [], [decision.outcome.value]

    def admission(_payload, *, expected_call=None):
        return {"outcome": "ALLOW", "expected": expected_call}

    fake._phase4_partition_structured_tool_calls = partition
    fake._phase4_executor_admission_decision = admission

    try:
        gate.install(fake)
        active = fake._JACK_AUTHORITY_LEDGER

        allowed, errors = fake._phase4_partition_structured_tool_calls([])
        assert allowed == []
        assert errors == ["DENY_AND_CONTINUE"]

        valid = {
            "protocol_version": 1,
            "runtime_id": "runtime-gate",
            "lane_id": "lane-gate",
            "tool_call_id": "call-1",
            "tool_name": "read",
            "arguments": {"path": r"D:\\Projects\\Jack\\x.txt"},
            "executor_cwd": r"D:\\Projects\\Jack",
            "executor_platform": "win32",
        }
        assert fake._phase4_executor_admission_decision(valid)["outcome"] == "ALLOW"

        bad = dict(valid)
        bad["runtime_id"] = "wrong-runtime"
        with pytest.raises(HTTPException) as caught:
            fake._phase4_executor_admission_decision(bad)
        assert caught.value.status_code == 409

        records = read_records(active)
        assert [item["event_type"] for item in records] == [
            "REPRESENTED_PATH_DECISION",
            "EXECUTOR_IDENTITY_DECISION",
            "EXECUTOR_IDENTITY_DECISION",
        ]
        path_record = records[0]
        assert path_record["outcome"] == "DENY_AND_CONTINUE"
        assert path_record["payload"]["workspace_configured"] is True
        assert path_record["payload"]["inside_workspace"] is False
        assert "canonical_target" not in path_record["payload"]
        assert "reason" not in path_record["payload"]

        assert records[1]["payload"] == {
            "runtime_matches": True,
            "lane_matches": True,
            "outcome": "ALLOW",
            "containment_scope": "none",
        }
        assert records[2]["payload"]["runtime_matches"] is False
        assert records[2]["outcome"] == "DENY_AND_CONTINUE"
        active.close()
    finally:
        path_policy.authorize_represented_path = original_authorizer


def test_gate_lightweight_policy_host_does_not_acquire_runtime_ledger(monkeypatch):
    fake = SimpleNamespace(SecurityOutcome=Outcome)
    monkeypatch.setattr(gate, "_install_represented_path_gate", lambda *_a, **_k: None)
    gate.install(fake)
    assert not hasattr(fake, "_JACK_AUTHORITY_LEDGER")
    decision = fake.evaluate_consequence((gate.StageToolAuthorityFact(False),))
    assert decision.outcome is Outcome.DENY_AND_CONTINUE
