"""Cache-prefix authority: never trade provenance or new instructions for KV reuse.

These tests exercise the same shared helper used by streamed and buffered
backend paths. No inference server or agent implementation is required.
"""
import importlib.util
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from jack_evidence_guard import (
    EVIDENCE_ORIGIN_CALLER_TOOL_RESULT,
    TOOL_RESUME_PROVENANCE_NOTE,
)
from jack_stage1_cache_stability import Stage1CacheStabilizer


def _kernel(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "x-high")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    name = "jack_cache_provenance_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parents[1] / "jack_kernel.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


TOOL_STAGES = (
    "Native answer",
    "Agentic native pass 1",
    "Deep Research Synthesis pass 3",
    "Deep Reasoning Thesis pass 1",
    "Deep Reasoning Antithesis pass 2",
    "Deep Reasoning Synthesis pass 3",
    "Code Debugging Pass 1",
    "Code Debugging Pass 5",
)


@pytest.mark.parametrize("stage", TOOL_STAGES)
def test_provenance_note_in_initial_and_resume_system_prefix(monkeypatch, tmp_path, stage):
    kernel = _kernel(monkeypatch, tmp_path)
    profile = SimpleNamespace(name=stage, allow_tools=True)
    original = "ORIGINAL SYSTEM INSTRUCTIONS"
    initial = kernel._tool_stage_system_with_provenance(original, profile)
    resumed = kernel._tool_stage_system_with_provenance(original, profile)
    assert initial == resumed
    assert initial.startswith(original)
    assert initial.endswith(TOOL_RESUME_PROVENANCE_NOTE)
    assert initial.count("[JACK HOST TOOL-RESULT PROVENANCE]") == 1
    assert EVIDENCE_ORIGIN_CALLER_TOOL_RESULT in initial
    # Calling twice should not duplicate any host-owned instruction.
    assert kernel._tool_stage_system_with_provenance(initial, profile) == initial


@pytest.mark.parametrize("stage", (
    "Agentic native pass 2",
    "Deep Research Thesis pass 1",
    "Deep Research Antithesis pass 2",
    "Code Debugging Summary",
))
def test_tool_free_stage_receives_no_tool_provenance(monkeypatch, tmp_path, stage):
    kernel = _kernel(monkeypatch, tmp_path)
    original = "SEPARATE STAGE CONTRACT"
    assert kernel._tool_stage_system_with_provenance(
        original, SimpleNamespace(name=stage, allow_tools=False)
    ) == original


def test_new_authoritative_insertion_is_not_removed():
    observer = Stage1CacheStabilizer(enabled=True)
    first = [{"role":"system","content":"ORIGINAL SYSTEM"}]
    observer.apply(stage="Agentic native pass 1",turn_id="stage::work",
                   messages=first,tool_continuation=False,eligible=True)
    second = [{"role":"system","content":"ORIGINAL SYSTEM\nSECURITY NOTICE"}]
    result = observer.apply(stage="Agentic native pass 1",turn_id="stage::work",
                            messages=second,tool_continuation=True,eligible=True)
    assert result["action"] == "preserved_change"
    assert result["reason"] == "pure_insertion_preserved_on_same_work_tool_resume"
    assert second[0]["content"] == "ORIGINAL SYSTEM\nSECURITY NOTICE"


def test_stabilizer_cannot_silently_remove_provenance_or_change_existing_text():
    observer = Stage1CacheStabilizer(enabled=True)
    original = "CALLER" + TOOL_RESUME_PROVENANCE_NOTE
    observer.apply(stage="Native answer",turn_id="work",messages=[
        {"role":"system","content":original},
    ],tool_continuation=False,eligible=True)
    extra = [{"role":"system","content":original+"\nnew critical instruction"}]
    observer.apply(stage="Native answer",turn_id="work",messages=extra,
                   tool_continuation=True,eligible=True)
    assert extra[0]["content"] == original+"\nnew critical instruction"


def test_the_shared_entrypoint_is_called_by_both_transports(monkeypatch, tmp_path):
    kernel = _kernel(monkeypatch, tmp_path)
    import inspect
    source_a = inspect.getsource(kernel.OpenAICompatibleBackend.chat)
    source_b = inspect.getsource(kernel.OpenAICompatibleBackend.chat_stream)
    assert "_tool_stage_system_with_provenance(stage_system, profile)" in source_a
    assert "_tool_stage_system_with_provenance(stage_system, profile)" in source_b
