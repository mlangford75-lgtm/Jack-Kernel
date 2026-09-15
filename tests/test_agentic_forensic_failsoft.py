import importlib.util
import os
import sys
import tempfile
import uuid
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "jack_kernel.py"


def load():
    os.environ["JACK_REASONING_LEVEL"] = "agentic"
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "stage"
    os.environ["JACK_BACKEND_MODEL"] = "test-model"
    os.environ["JACK_BACKEND_PROFILE"] = "lmstudio"

    name = f"jack_agentic_forensic_failsoft_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_agentic_archive_missing_snapshot_fails_soft():
    mod = load()
    history = []

    result = mod._archive_agentic_stage1_forensic(
        history,
        "FROZEN_A1",
        "<jack>XML</jack>",
    )

    assert result is None


def test_agentic_archive_io_failure_fails_soft_and_discards_snapshot():
    mod = load()

    with tempfile.TemporaryDirectory() as tmp:
        blocker = Path(tmp) / "not-a-directory"
        blocker.write_text("block", encoding="utf-8")

        mod._forensic_archive_root = lambda: blocker

        history = [
            {
                "_jack_agentic_stage1_forensic_snapshot": {
                    "schema": "jack.forensic.agentic.stage1.v2",
                    "active_response_target": {"id": "test-target"},
                    "reasoning_trace": "native reasoning",
                    "tool_trajectory": [],
                }
            }
        ]

        result = mod._archive_agentic_stage1_forensic(
            history,
            "FROZEN_A1",
            "<jack>XML</jack>",
        )

        assert result is None
        assert all(
            "_jack_agentic_stage1_forensic_snapshot" not in item
            for item in history
        )
