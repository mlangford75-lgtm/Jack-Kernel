"""Universal observation-only lifecycle regression tests (no model behavior grading)."""
import asyncio
import importlib.util
import os
from pathlib import Path
import sys
import uuid
import pytest
from fastapi import HTTPException
from jack_tool_lifecycle import ToolLifecycleObserver

ROOT = Path(__file__).resolve().parents[1]


def load(monkeypatch):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "x-high")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    name = "jack_tool_lifecycle_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    kernel = importlib.util.module_from_spec(spec)
    sys.modules[name] = kernel
    spec.loader.exec_module(kernel)
    return kernel


def observer(max_records=512):
    clock = [100.]
    return ToolLifecycleObserver(clock=lambda: clock[0], max_records=max_records), clock


def event(o, call="one", action="START", owner="one-session", adapter="pi", **kw):
    return o.observe(adapter=adapter, owner=owner, call_id=call, event=action, **kw)


def test_short_success():
    o, t = observer()
    assert event(o)["state"] == "START_REPORTED"
    t[0] += .5
    assert event(o, action="END", outcome="SUCCESS_REPORTED")["state"] == "END_REPORTED"
    assert o.snapshot()["terminal_reports"]["SUCCESS_REPORTED"] == 1
    assert o.snapshot()["active_unconfirmed"] == 0


def test_silent_valid_work_and_persistent_server_are_not_failures():
    o, t = observer()
    event(o, "long-valid-compiler")
    event(o, "persistent-server")
    t[0] += 12000
    s = o.snapshot()
    assert s["active_unconfirmed"] == 2
    assert s["longest_unconfirmed_seconds"] == 12000
    assert s["terminal_reports"]["ERROR_REPORTED"] == 0
    assert s["observation_only"]


def test_progress_is_not_success_and_repeated_events_are_idempotent():
    o, t = observer()
    event(o)
    t[0] += 8
    event(o)
    event(o, action="PROGRESS")
    assert o.snapshot()["longest_unconfirmed_seconds"] == 8
    event(o, action="END", outcome="ERROR_REPORTED")
    assert event(o, action="END", outcome="SUCCESS_REPORTED")["state"] == "TERMINAL_ALREADY_RECORDED"
    assert o.snapshot()["terminal_reports"]["ERROR_REPORTED"] == 1


def test_missing_start_or_end_produces_unknown_provenance():
    o, t = observer()
    event(o, "unmatched-progress", "PROGRESS")
    event(o, "unmatched-end", "END", outcome="UNKNOWN")
    s = o.snapshot()
    assert s["unmatched_records"] == 2
    assert s["terminal_reports"]["UNKNOWN"] == 1
    assert s["longest_unconfirmed_seconds"] is None


def test_same_tool_id_multiple_owners_and_adapters_do_not_collide():
    o, _ = observer()
    event(o, "same", owner="s1", adapter="pi")
    event(o, "same", owner="s2", adapter="pi")
    event(o, "same", owner="s1", adapter="other")
    event(o, "same", "END", owner="s1", adapter="pi", outcome="SUCCESS_REPORTED")
    assert o.snapshot()["active_unconfirmed"] == 2


def test_capabilities_report_only_and_bounded_eviction_is_explicit():
    o, _ = observer(max_records=2)
    caps = dict(start_end=True, progress=True, bounded_return=False, cancellation=False, detached_jobs=False)
    event(o, "first", capabilities=caps)
    event(o, "second")
    event(o, "third")
    s = o.snapshot()
    assert s["reported_adapter_capabilities"]["pi"] == caps
    assert s["evicted_unfinished"] == 1
    assert s["complete_coverage"] is False


@pytest.mark.parametrize("invalid", [None, "", "\n", "x"*201])
def test_invalid_call_id_is_rejected(invalid):
    o, _ = observer()
    with pytest.raises(ValueError):
        event(o, invalid)
    assert o.snapshot()["retained_records"] == 0


def test_invalid_claims_cannot_change_state():
    o, _ = observer()
    with pytest.raises(ValueError):
        event(o, action="START", outcome="SUCCESS_REPORTED")
    with pytest.raises(ValueError):
        event(o, capabilities={"cancellation": "yes"})
    assert o.snapshot()["retained_records"] == 0


@pytest.mark.parametrize("mode", ["x-high", "agentic", "deep-research", "deep-reasoning", "code-debugging"])
def test_universal_api_is_not_profile_specific(monkeypatch, mode):
    monkeypatch.setenv("JACK_REASONING_LEVEL", mode)
    o, _ = observer()
    event(o, adapter="custom-executor", owner="owner", call="opaque")
    assert o.snapshot()["active_unconfirmed"] == 1
    assert o.snapshot()["observation_only"]


def test_kernel_endpoint_and_runtime_snapshot_are_passive(monkeypatch):
    k = load(monkeypatch)
    class Request:
        headers = {}
        async def json(self):
            return {
                "runtime_id": k.RUNTIME_ID, "lane_id": k.LANE_ID,
                "adapter": "test-executor", "owner": "session", "call_id": "opaque-tool",
                "event": "START", "capabilities": {"start_end": True},
            }
    result = asyncio.run(k.tool_lifecycle_observe(Request()))
    assert result["accepted"] is True
    snapshot = k.TOOL_LIFECYCLE_OBSERVER.snapshot()
    assert snapshot["active_unconfirmed"] == 1
    assert snapshot["reported_adapter_capabilities"]["test-executor"]["cancellation"] is False
    async def runtime():
        return await k.runtime_activity_status(Request())
    status = asyncio.run(runtime())
    assert status["tool_lifecycle"]["observation_only"] is True


def test_kernel_rejects_unrelated_runtime_without_state_change(monkeypatch):
    k = load(monkeypatch)
    class Request:
        headers = {}
        async def json(self):
            return {
                "runtime_id": "not-this-runtime", "lane_id": k.LANE_ID,
                "adapter": "test", "owner": "session", "call_id": "call", "event": "START",
            }
    with pytest.raises(HTTPException) as exc:
        asyncio.run(k.tool_lifecycle_observe(Request()))
    assert exc.value.status_code == 409
    assert k.TOOL_LIFECYCLE_OBSERVER.snapshot()["retained_records"] == 0
