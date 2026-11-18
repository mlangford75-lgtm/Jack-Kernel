"""Exercise Jack's actual shared backend and stage-owned cache lifetime."""
import importlib.util
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "x-high")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / "cache.sqlite"))
    name = "universal_cache_test_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "AGENTIC_MODE", False)
    return module


@pytest.mark.parametrize("stage_key,stage_name", [
    ("thesis", "Native answer"),
    ("extended_synthesis", "Deep Research Synthesis pass 3"),
    ("deep_reasoning_thesis", "Deep Reasoning Thesis pass 1"),
    ("deep_reasoning_synthesis", "Deep Reasoning Synthesis pass 3"),
    ("debug_pass_1", "Code Debugging Pass 1"),
])
def test_work_id_and_stabilization_use_shared_backend(monkeypatch, tmp_path, stage_key, stage_name):
    k = _load(monkeypatch, tmp_path)
    history = [{"role": "user", "content": "Check a command"}]
    original_caller_message = history[0]
    k.JackQwenKernel._cache_bind_stage_work(history, stage_key, False)
    assert history[0] is not original_caller_message
    owner = history[0]["_jack_cache_work_id"]
    assert owner.startswith("jack-cache-work-")
    assert history[0]["_jack_cache_work_stage"] == stage_key
    backend = k.OpenAICompatibleBackend.__new__(k.OpenAICompatibleBackend)
    backend._stage1_cache_stabilizer = k.Stage1CacheStabilizer()
    wire_view = backend._stage_messages_for_profile(
        history, SimpleNamespace(name=stage_name, thinking=True)
    )
    assert "_jack_cache_work_id" not in wire_view[0]
    profile = SimpleNamespace(name=stage_name, allow_tools=True)
    initial = [{"role": "system", "content": "Original"}, {"role": "user", "content": "Check a command"}]
    backend._stabilize_stage1_tool_cache_system(initial, history, profile)
    history.extend([
        {"role":"assistant", "tool_calls":[{"id":"a"}], "_jack_internal_tool_exchange":True},
        {"role":"tool", "tool_call_id":"a", "content":"done", "_jack_internal_tool_exchange":True},
    ])
    k.JackQwenKernel._cache_bind_stage_work(history, stage_key, True)
    assert history[0]["_jack_cache_work_id"] == owner
    continued = [{"role":"system","content":"Original plus extra"},{"role":"user","content":"Check a command"}]
    backend._stabilize_stage1_tool_cache_system(continued, history, profile)
    assert continued[0]["content"] == "Original plus extra"


def test_separate_stage_gets_a_new_work_identity(monkeypatch, tmp_path):
    k = _load(monkeypatch, tmp_path)
    history = [{"role":"user","content":"Task"}]
    k.JackQwenKernel._cache_bind_stage_work(history, "thesis", False)
    old = history[0]["_jack_cache_work_id"]
    k.JackQwenKernel._cache_bind_stage_work(history, "extended_synthesis", False)
    assert history[0]["_jack_cache_work_id"] != old


def test_unknown_resume_does_not_mint_authority(monkeypatch, tmp_path):
    k = _load(monkeypatch, tmp_path)
    history = [{"role":"user","content":"Task"}]
    k.JackQwenKernel._cache_bind_stage_work(history, "thesis", True)
    assert "_jack_cache_work_id" not in history[0]


def test_no_tools_means_no_system_rewrite(monkeypatch, tmp_path):
    k = _load(monkeypatch, tmp_path)
    history = [{"role":"user","content":"Task","_jack_cache_work_id":"host-identity"}]
    backend = k.OpenAICompatibleBackend.__new__(k.OpenAICompatibleBackend)
    backend._stage1_cache_stabilizer = k.Stage1CacheStabilizer()
    wire = [{"role":"system","content":"Stage 2 authority"}]
    backend._stabilize_stage1_tool_cache_system(
        wire, history, SimpleNamespace(name="Agentic native pass 2", allow_tools=False)
    )
    assert wire[0]["content"] == "Stage 2 authority"
