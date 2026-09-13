import asyncio
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException

SRC = Path(__file__).resolve().parents[1] / "jack_kernel.py"


def load_module():
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "off"
    os.environ["JACK_BACKEND_MODEL"] = "test-model"
    name = f"jack_orch_v2_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_run_bound_task_attribution_sequence_and_raw_source_preservation():
    m = load_module()

    async def run():
        hub = m.OrchestrationEventHub(replay_limit=8)
        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        source = {
            "type": "message_end",
            "task_id": task_id,
            "run_id": run_id,
            "run_epoch": 1,
            "attribution": "pi_run_bound",
            "data": {"message": {"role": "assistant", "content": "Hi"}},
            "at": "2026-09-12T08:44:20.132Z",
        }
        await hub._publish("message_end", source)
        await hub._publish("message", {
            "type": "message",
            "task_id": task_id,
            "run_id": run_id,
            "run_epoch": 1,
            "attribution": "pi_run_bound",
            "data": {"delta": "x"},
            "at": "2026-09-12T08:44:20.133Z",
        })
        events = list(hub._buffer)
        assert [e["seq"] for e in events] == [1, 2]
        assert all(e["task_id"] == task_id for e in events)
        assert all(e["run_id"] == run_id for e in events)
        assert all(e["run_epoch"] == 1 for e in events)
        assert all(e["attribution"] == "pi_run_bound" for e in events)
        assert events[0]["source"] == "pi"
        assert events[0]["source_at"] == source["at"]
        assert events[0]["data"] == source["data"]
        assert events[0]["source_event"] == source
        assert events[0]["jack_received_at"].endswith("Z")
        frame = hub._encode_sse(events[0]).decode("utf-8")
        assert "id: 1\n" in frame
        assert "event: message_end\n" in frame
        payload = json.loads(next(line[6:] for line in frame.splitlines() if line.startswith("data: ")))
        assert payload["task_id"] == task_id
        assert payload["run_id"] == run_id

    asyncio.run(run())


def test_untagged_source_event_stays_unattributed():
    m = load_module()

    async def run():
        hub = m.OrchestrationEventHub(replay_limit=8)
        await hub._publish("message_end", {
            "type": "message_end",
            "data": {"message": {"role": "user", "content": "old"}},
            "at": "2026-09-12T08:44:20.000Z",
        })
        event = list(hub._buffer)[0]
        assert event["task_id"] is None
        assert event["run_id"] is None
        assert event["run_epoch"] is None
        assert event["attribution"] is None

    asyncio.run(run())


def test_task_state_can_carry_run_identity_without_message_attribution_guessing():
    m = load_module()

    async def run():
        hub = m.OrchestrationEventHub(replay_limit=8)
        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        await hub._publish("task", {
            "type": "task",
            "task_id": task_id,
            "run_id": run_id,
            "run_epoch": 2,
            "attribution": "task_state",
            "data": {
                "id": task_id,
                "status": "settling",
                "runId": run_id,
                "runEpoch": 2,
                "runOpen": True,
            },
            "at": "2026-09-12T08:44:20.150Z",
        })
        event = list(hub._buffer)[0]
        assert event["task_id"] == task_id
        assert event["run_id"] == run_id
        assert event["run_epoch"] == 2
        assert event["attribution"] == "task_state"

    asyncio.run(run())


def test_replay_and_explicit_gap_detection():
    m = load_module()

    async def run():
        hub = m.OrchestrationEventHub(replay_limit=3)
        for n in range(5):
            await hub._publish("task", {
                "type": "task",
                "task_id": f"task-{n}",
                "data": {"id": f"task-{n}", "status": "running"},
                "at": f"2026-09-12T08:44:2{n}.000Z",
            })
        assert [e["seq"] for e in hub._buffer] == [3, 4, 5]
        queue, replay = await hub.subscribe(3)
        try:
            replay_text = b"".join(replay).decode("utf-8")
            assert "id: 4\n" in replay_text
            assert "id: 5\n" in replay_text
        finally:
            await hub.unsubscribe(queue)

        with pytest.raises(HTTPException) as exc:
            await hub.subscribe(1)
        assert exc.value.status_code == 409
        assert exc.value.detail["error"] == "orchestration_replay_gap"
        assert exc.value.detail["oldest_available_seq"] == 3
        assert exc.value.detail["latest_seq"] == 5

    asyncio.run(run())
