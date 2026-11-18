"""Flash-only deterministic Stage-2 contract; model memory is Turn N only."""
import asyncio
import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_flash(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "flash")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_flash_ordinal_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def frozen_history(kernel, prior_turns=0):
    history = []
    for i in range(prior_turns):
        history.extend([
            {"role": "user", "content": f"Prior user request {i + 1}"},
            {"role": "assistant", "content": f"Prior answer {i + 1}"},
        ])
    history.append({"role": "user", "content": "Current genuine request"})
    work_id = kernel._agentic_begin_turn(history, fresh=True)
    assert work_id and work_id.startswith("jack-turn-")
    # A tool exchange and synthetic Jack user-role control must not increment.
    history.extend([
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "call-one", "type": "function",
                         "function": {"name": "bash", "arguments": "{}"}}],
         "_jack_internal_tool_exchange": True},
        {"role": "tool", "tool_call_id": "call-one", "name": "bash",
         "content": "RESULT_RETURNED", "_jack_internal_tool_exchange": True},
        {"role": "user", "content": "Jack private retry",
         "_jack_internal_protocol_recovery": True},
    ])
    answer = kernel.append_extended_candidate_response(
        history, {"content": "Frozen answer: exact bytes"}
    )
    kernel._agentic_forensic_start_stage2(history)
    return history, answer, work_id


@pytest.mark.parametrize("prior_turns", [0, 1, 2, 9])
def test_flash_label_counts_real_user_turns_only(monkeypatch, tmp_path, prior_turns):
    k = load_flash(monkeypatch, tmp_path)
    h, answer, work_id = frozen_history(k, prior_turns)
    label = f"Turn {prior_turns + 1}"
    first = k._agentic_flash_stage2_result(h)
    second = k._agentic_flash_stage2_result(h)
    assert first == second
    assert first["choices"][0]["message"]["content"] == label
    assert first["choices"][0]["finish_reason"] == "stop"
    assert first["usage"]["total_tokens"] == 0
    assert k._agentic_forensic_turn(h).turn_id == work_id
    assert h[-1]["content"] == answer
    # The ordinary existing journal accepts the label as the committed memory.
    k._agentic_forensic_commit(h, answer, label, "")


@pytest.mark.parametrize("stream", [False, True])
def test_flash_stage2_bypasses_backend_but_retains_completed_stage(
    monkeypatch, tmp_path, stream
):
    k = load_flash(monkeypatch, tmp_path)
    h, answer, work_id = frozen_history(k, 2)

    class BackendMustNotRun:
        async def chat(self, **kwargs):
            raise AssertionError("Flash Stage 2 must not call model")

        async def chat_stream(self, **kwargs):
            raise AssertionError("Flash Stage 2 must not stream model")

    kernel = k.JackQwenKernel(BackendMustNotRun(), k.CFG)

    async def run():
        if stream:
            return [packet async for packet in kernel._run_stage_streamed(
                h, "", "extended_reflection", {}, tools=None, append=False
            )]
        return await kernel._run_stage(
            h, "", "extended_reflection", {}, tools=None, append=False
        )

    result = asyncio.run(run())
    if stream:
        assert [packet["kind"] for packet in result] == ["content", "result"]
        assert result[0]["text"] == "Turn 3"
        completed = result[-1]["data"]
    else:
        completed = result
    assert completed["choices"][0]["message"]["content"] == "Turn 3"
    assert completed["choices"][0]["finish_reason"] == "stop"
    assert k._agentic_forensic_turn(h).turn_id == work_id
    k._agentic_forensic_commit(h, answer, "Turn 3", "")


def test_non_flash_profiles_are_not_eligible_for_host_flash_label(monkeypatch, tmp_path):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "thorough")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / "other.sqlite"))
    name = "jack_thorough_flash_guard_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    with pytest.raises(k.ForensicConflict):
        k._agentic_flash_stage2_result([{"role": "user", "content": "X"}])
