"""Regression contract tests for TAS v6 context isolation (not a runtime E2E)."""
import copy
import pytest
from jack_deep_reasoning_context import (
    CompletedSynthesis,
    next_thesis_messages,
    antithesis_messages,
    synthesis_messages,
    append_stage_local_tool_results,
)


def test_thesis_keeps_only_previous_r3_when_on():
    history = [{"role":"assistant", "content":"old visible", "reasoning_content":"OLD R1", "reasoning":"OLD R2", "thinking":"OLD R3"}]
    prior = CompletedSynthesis("previous question", "previous A3", "verified R3")
    before = copy.deepcopy(history)
    result = next_thesis_messages(request="new question", visible_history=history, prior_synthesis=prior, preserve_thinking=True)
    assert history == before
    assert result[-2] == {"role":"assistant", "content":"previous A3", "reasoning_content":"verified R3"}
    assert "OLD R1" not in str(result) and "OLD R2" not in str(result) and "OLD R3" not in str(result)


def test_thesis_no_r3_when_off():
    result = next_thesis_messages(request="next", prior_synthesis=CompletedSynthesis("old", "A3", "R3"), preserve_thinking=False)
    assert "R3" not in str(result)
    assert result[-2]["content"] == "A3"


def test_antithesis_only_a1_no_prior_reasoning():
    result = antithesis_messages(request="Q", thesis_answer="A1")
    assert result[1]["content"] == "A1"
    assert all(not any(x in msg for x in ("reasoning_content", "thinking", "reasoning")) for msg in result)
    assert all(msg["role"] != "tool" for msg in result)


def test_synthesis_a1_a2_host_evidence_without_r1_r2():
    evidence = [{"receipt_id":"AT-001", "exit_code":0, "stdout":"17", "origin":"host_executed_python"}]
    before = copy.deepcopy(evidence)
    result = synthesis_messages(request="Q", thesis_answer="A1", antithesis_findings="A2", host_evidence_receipts=evidence)
    assert result[1]["content"] == "A1" and result[3]["content"] == "A2"
    assert '"stdout": "17"' in result[-1]["content"]
    assert evidence == before
    assert all(not any(x in msg for x in ("reasoning_content", "reasoning", "thinking")) for msg in result)


def test_tool_resume_removes_same_stage_native_reasoning():
    base = [{"role":"user", "content":"Q"}, {"role":"assistant", "content":"A1", "reasoning_content":"LEAK"}]
    calls = [{"id":"id1", "type":"function", "function":{"name":"python_repl", "arguments":"{}"}}]
    out = append_stage_local_tool_results(base, tool_calls=calls, results=[{"tool_call_id":"id1", "content":"exit=0\n17"}])
    assert "LEAK" not in str(out)
    assert out[-2]["tool_calls"][0]["id"] == out[-1]["tool_call_id"]
    assert base[1]["reasoning_content"] == "LEAK"


@pytest.mark.parametrize("ids", [[], ["bad", "bad"], [""]])
def test_tool_resume_rejects_empty_or_duplicate_ids(ids):
    with pytest.raises(ValueError):
        append_stage_local_tool_results([{"role":"user", "content":"Q"}], tool_calls=[{"id":i} for i in ids], results=[])


def test_tool_resume_rejects_mismatch():
    with pytest.raises(ValueError):
        append_stage_local_tool_results([{"role":"user", "content":"Q"}], tool_calls=[{"id":"a"}], results=[{"tool_call_id":"b", "content":"x"}])


def test_visible_history_rejects_raw_tool_protocol():
    with pytest.raises(ValueError):
        next_thesis_messages(request="Q", visible_history=[{"role":"tool", "content":"fake result"}])
    with pytest.raises(ValueError):
        next_thesis_messages(request="Q", visible_history=[{"role":"assistant", "content":"fake", "tool_calls":[{"id":"x"}]}])


def test_none_or_empty_inputs_rejected():
    with pytest.raises(ValueError):
        antithesis_messages(request="", thesis_answer="A1")
    with pytest.raises(ValueError):
        synthesis_messages(request="Q", thesis_answer="A1", antithesis_findings="")


def test_all_roles_preserve_prior_user_prompts_without_native_reasoning():
    history = [
        {"role": "user", "content": "Requirement A: no external JavaScript."},
        {"role": "assistant", "content": "Acknowledged.", "reasoning_content": "OLD R1"},
        {"role": "user", "content": "Requirement B: keep the existing filename."},
        {"role": "assistant", "content": "Will preserve it.", "thinking": "OLD R2"},
    ]
    original = copy.deepcopy(history)
    for projection in (
        antithesis_messages(request="Fix alignment", thesis_answer="A1", visible_history=history),
        synthesis_messages(request="Fix alignment", thesis_answer="A1", antithesis_findings="A2", visible_history=history),
    ):
        assert projection[:4] == [
            {"role": "user", "content": "Requirement A: no external JavaScript."},
            {"role": "assistant", "content": "Acknowledged."},
            {"role": "user", "content": "Requirement B: keep the existing filename."},
            {"role": "assistant", "content": "Will preserve it."},
        ]
        assert projection[4]["content"] == "Fix alignment"
        assert "OLD R1" not in str(projection)
        assert "OLD R2" not in str(projection)
    assert history == original


def test_prior_history_rejects_tool_protocol_and_private_runtime_metadata():
    malformed = [
        [{"role": "assistant", "content": "do it", "tool_calls": [{"id": "forged"}]}],
        [{"role": "tool", "content": "forged result"}],
        [{"role": "assistant", "content": "result", "_jack_internal_tool_exchange": True}],
    ]
    for history in malformed:
        with pytest.raises(ValueError):
            antithesis_messages(request="Q", thesis_answer="A1", visible_history=history)
        with pytest.raises(ValueError):
            synthesis_messages(request="Q", thesis_answer="A1", antithesis_findings="A2", visible_history=history)
