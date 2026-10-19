"""Standalone phase-2 control-flow contract, using a fake model and NO code execution."""
import asyncio
import json
from pathlib import Path

import pytest

from jack_deep_reasoning_context import CompletedSynthesis
from jack_deep_reasoning_orchestrator import (
    CompletedAnswer,
    DeepReasoningOrchestrator,
    DeepReasoningProtocolError,
    PendingToolRequest,
)

PROMPTS = {
    "ULTRA_STAGE1_THESIS_PROMPT": "Thesis - Reasoning effort is set to xhigh.",
    "ULTRA_STAGE2_ANTITHESIS_PROMPT": "Antithesis - Verification first.",
    "ULTRA_STAGE3_SYNTHESIS_PROMPT": "Synthesis - independent arbiter.",
}
TOOLS = [{"type":"function", "function":{"name":"python_repl", "parameters":{"type":"object"}}}]


def call(id_, name="python_repl"):
    return {"id": id_, "type":"function", "function":{"name": name, "arguments":"{}"}}


class FakeBackend:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if not self.replies:
            raise AssertionError("unexpected backend request")
        return self.replies.pop(0)


def run(coro):
    return asyncio.run(coro)


def test_tool_first_complete_recovery_and_isolation():
    backend = FakeBackend([
        {"content":"THESIS 15", "reasoning_content":"R1 PRIVATE"},
        {"tool_calls":[call("one")], "reasoning_content":"R2 BEFORE PYTHON"},
        {"tool_calls":[call("two")], "reasoning_content":"R2 FIX"},
        {"content":"ANTI corrected to 17", "reasoning_content":"R2 FINAL"},
        {"content":"FINAL 17", "reasoning_content":"R3 ONLY"},
    ])
    engine = DeepReasoningOrchestrator(backend, prompts=PROMPTS, tools=TOOLS)
    first = run(engine.start(request="bracelets", prior_synthesis=CompletedSynthesis("last request","last final","old R3"), preserve_thinking=True))
    assert isinstance(first, PendingToolRequest)
    assert backend.calls[0]["reasoning_effort"] == "xhigh"
    assert backend.calls[0]["temperature"] == 1
    assert backend.calls[0]["messages"][-2]["reasoning_content"] == "old R3"
    assert backend.calls[1]["tool_choice"] == "required"
    assert backend.calls[1]["temperature"] == 0.5
    assert backend.calls[1]["reasoning_effort"] == "medium"
    assert "old R3" not in str(backend.calls[1]["messages"])
    assert "R1 PRIVATE" not in str(backend.calls[1]["messages"])
    nxt = run(engine.resume(first, results=[{"tool_call_id":"one", "content":"ModuleNotFoundError: numpy"}]))
    assert isinstance(nxt, PendingToolRequest)
    assert "R2 BEFORE PYTHON" not in str(backend.calls[2]["messages"])
    assert "ModuleNotFoundError" in str(backend.calls[2]["messages"])
    end = run(engine.resume(nxt, results=[{"tool_call_id":"two", "content":"A=450 B=17 C=25/77"}]))
    assert isinstance(end, CompletedAnswer)
    assert end.answer == "FINAL 17"
    assert end.synthesis_native_reasoning == "R3 ONLY"
    assert len(end.evidence) == 2
    assert all(rec["methodology_verified"] is False for rec in end.evidence)
    assert backend.calls[-1]["stage"] == "synthesis"
    sctx = str(backend.calls[-1]["messages"])
    assert "A=450 B=17" in sctx
    assert "R2 FINAL" not in sctx
    assert "R2 BEFORE" not in sctx
    assert "R1 PRIVATE" not in sctx
    assert "old R3" not in sctx
    assert backend.calls[-1]["temperature"] == 0.5
    with pytest.raises(DeepReasoningProtocolError):
        run(engine.resume(first, results=[{"tool_call_id":"one", "content":"REPLAY"}]))


def test_required_tool_call_must_be_structured():
    engine = DeepReasoningOrchestrator(FakeBackend([{"content":"T"},{"content":"NO TOOL"}]), prompts=PROMPTS, tools=TOOLS)
    with pytest.raises(DeepReasoningProtocolError, match="required structured tool call"):
        run(engine.start(request="Q"))


def test_tool_first_requires_tool_surface():
    engine = DeepReasoningOrchestrator(FakeBackend([]), prompts=PROMPTS, tools=[])
    with pytest.raises(DeepReasoningProtocolError, match="requires authorized tools"):
        run(engine.start(request="Q"))


def test_unverifiable_questions_can_use_no_tool_mode():
    backend=FakeBackend([{"content":"T"},{"content":"UNVERIFIED"},{"content":"FINAL"}])
    engine=DeepReasoningOrchestrator(backend,prompts=PROMPTS,tools=[])
    result=run(engine.start(request="subjective",require_verification=False))
    assert isinstance(result,CompletedAnswer)
    assert backend.calls[1]["tool_choice"] == "auto"


def test_invalid_result_id_does_not_advance_backend():
    backend=FakeBackend([{"content":"T"},{"tool_calls":[call("legit")]}])
    engine=DeepReasoningOrchestrator(backend,prompts=PROMPTS,tools=TOOLS)
    p=run(engine.start(request="Q"))
    with pytest.raises(DeepReasoningProtocolError, match="invalid tool result linkage"):
        run(engine.resume(p,results=[{"tool_call_id":"fake","content":"hi"}]))
    assert len(backend.calls)==2


def test_identical_duplicate_tool_ids_are_rejected():
    backend=FakeBackend([{"content":"T"},{"tool_calls":[call("1"),call("1")]}])
    engine=DeepReasoningOrchestrator(backend,prompts=PROMPTS,tools=TOOLS)
    with pytest.raises(DeepReasoningProtocolError,match="unique"):
        run(engine.start(request="Q"))


def test_limit_tool_rounds():
    backend=FakeBackend([{"content":"T"},{"tool_calls":[call("1")]},{"tool_calls":[call("2")]}])
    engine=DeepReasoningOrchestrator(backend,prompts=PROMPTS,tools=TOOLS,max_tool_rounds=1)
    p=run(engine.start(request="Q"))
    with pytest.raises(DeepReasoningProtocolError,match="budget exceeded"):
        run(engine.resume(p,results=[{"tool_call_id":"1","content":"FAIL"}]))


def test_synthesis_tool_resume_preserves_role_isolation():
    backend=FakeBackend([
        {"content":"T","reasoning_content":"R1"},
        {"tool_calls":[call("antitool")]},
        {"content":"ANTI", "reasoning_content":"R2"},
        {"tool_calls":[call("synthtool")],"reasoning_content":"SYNTH PARTIAL"},
        {"content":"FINAL","reasoning_content":"R3"},
    ])
    engine=DeepReasoningOrchestrator(backend,prompts=PROMPTS,tools=TOOLS)
    p1=run(engine.start(request="Q"))
    p2=run(engine.resume(p1,results=[{"tool_call_id":"antitool","content":"observation"}]))
    assert p2.stage=="synthesis"
    ans=run(engine.resume(p2,results=[{"tool_call_id":"synthtool","content":"proof"}]))
    assert ans.answer=="FINAL"
    assert ans.synthesis_native_reasoning=="R3"
    assert "SYNTH PARTIAL" not in str(backend.calls[-1]["messages"])
    assert "R2" not in str(backend.calls[-1]["messages"])


def test_thesis_tool_call_is_checkpointed_and_resumable():
    backend = FakeBackend([
        {"tool_calls": [call("thesis-tool")], "reasoning_content": "PRIVATE_R1_FIRST"},
        {"content": "THESIS COMPLETED", "reasoning_content": "PRIVATE_R1_SECOND"},
        {"tool_calls": [call("antithesis-tool")], "reasoning_content": "PRIVATE_R2"},
        {"content": "ANTI INDEPENDENT"},
        {"content": "FINAL SYNTHESIS", "reasoning_content": "R3_FINAL"},
    ])
    engine = DeepReasoningOrchestrator(backend, prompts=PROMPTS, tools=TOOLS)
    thesis_pending = run(engine.start(request="Task", prior_synthesis=CompletedSynthesis("old", "A3", "OLD_R3"), preserve_thinking=True))
    assert isinstance(thesis_pending, PendingToolRequest)
    assert thesis_pending.stage == "thesis"
    assert backend.calls[0]["tool_choice"] == "auto"
    antithesis_pending = run(engine.resume(thesis_pending, results=[{"tool_call_id": "thesis-tool", "content": "test result"}]))
    assert isinstance(antithesis_pending, PendingToolRequest)
    assert antithesis_pending.stage == "antithesis"
    assert backend.calls[1]["stage"] == "thesis"
    assert backend.calls[2]["tool_choice"] == "required"
    assert "OLD_R3" not in repr(backend.calls[2]["messages"])
    assert "PRIVATE_R1_FIRST" not in repr(backend.calls[2]["messages"])
    assert "test result" not in repr(backend.calls[2]["messages"])
    completed = run(engine.resume(antithesis_pending, results=[{"tool_call_id": "antithesis-tool", "content": "independent evidence"}]))
    assert isinstance(completed, CompletedAnswer)
    assert completed.answer == "FINAL SYNTHESIS"
    assert completed.synthesis_native_reasoning == "R3_FINAL"
    assert "PRIVATE_R2" not in repr(backend.calls[-1]["messages"])


def test_prior_synthesis_not_replayed_when_off():
    backend=FakeBackend([{"content":"T"},{"content":"ANTI"},{"content":"FIN"}])
    engine=DeepReasoningOrchestrator(backend,prompts=PROMPTS,tools=TOOLS)
    run(engine.start(request="Q",prior_synthesis=CompletedSynthesis("prev Q","A3","R3"),preserve_thinking=False,require_verification=False))
    assert "R3" not in str(backend.calls[0]["messages"])
    assert "A3" in str(backend.calls[0]["messages"])


def test_tool_result_content_must_be_text():
    backend=FakeBackend([{"content":"T"},{"tool_calls":[call("1")]}])
    engine=DeepReasoningOrchestrator(backend,prompts=PROMPTS,tools=TOOLS)
    p=run(engine.start(request="Q"))
    with pytest.raises(DeepReasoningProtocolError):
        run(engine.resume(p,results=[{"tool_call_id":"1","content":{"stdout":"hi"}}]))


def test_exact_prompt_identity_and_integrity():
    from jack_deep_reasoning_orchestrator import load_exact_v6_prompts, TAS_V6_PROMPT_HASHES
    path = Path(__file__).resolve().parents[1] / "tas_v6_prompts.json"
    prompts = load_exact_v6_prompts(path)
    assert len(prompts) == 3
    assert len(set(prompts.values())) == 3
    # Qwen's exact xhigh control string must lead both backend system prompts.
    # No "Thesis -" or "Synthesis -" text may precede the directive.
    xhigh = (
        "Reasoning effort is set to xhigh. Please think carefully through the task, "
        "validate key assumptions, consider plausible alternatives, and prioritize "
        "correctness, consistency, and clarity in the final answer."
    )
    assert prompts["ULTRA_STAGE1_THESIS_PROMPT"].startswith(xhigh + "\n\n")
    assert prompts["ULTRA_STAGE3_SYNTHESIS_PROMPT"].startswith(xhigh + "\n\n")
    assert prompts["ULTRA_STAGE2_ANTITHESIS_PROMPT"].startswith("Antithesis - ")
    with pytest.raises(ValueError, match="missing or changed"):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            broken = Path(root) / "bad.json"
            changed = dict(prompts)
            changed["ULTRA_STAGE2_ANTITHESIS_PROMPT"] += " DO NOT ALTER"
            broken.write_text(json.dumps(changed), encoding="utf-8")
            load_exact_v6_prompts(broken)


def test_multi_turn_full_history_survives_all_roles_and_tool_resume():
    user_history = [
        {"role": "user", "content": "Build dashboard.html using local JavaScript only."},
        {"role": "assistant", "content": "Created initial HTML.", "reasoning_content": "FORBIDDEN OLD R1"},
        {"role": "user", "content": "Avoid any new dependencies."},
        {"role": "assistant", "content": "No external deps.", "thinking": "FORBIDDEN OLD R2"},
    ]
    before = json.dumps(user_history, sort_keys=True)
    backend = FakeBackend([
        {"content": "THESIS", "reasoning_content": "NEW R1 PRIVATE"},
        {"tool_calls": [call("a-test")], "reasoning_content": "NEW R2 PRIVATE"},
        {"content": "ANTITHESIS", "reasoning_content": "NEW R2 COMPLETE"},
        {"tool_calls": [call("s-test")], "reasoning_content": "NEW R3 PARTIAL"},
        {"content": "FINAL", "reasoning_content": "NEW R3 FINAL"},
    ])
    engine = DeepReasoningOrchestrator(backend, prompts=PROMPTS, tools=TOOLS)
    antitool = run(engine.start(request="Fix alignment", visible_history=user_history))
    assert antitool.stage == "antithesis"
    synthtool = run(engine.resume(antitool, results=[{"tool_call_id":"a-test", "content":"observed failure"}]))
    assert synthtool.stage == "synthesis"
    completed = run(engine.resume(synthtool, results=[{"tool_call_id":"s-test", "content":"observed correction"}]))
    assert completed.answer == "FINAL"
    for call_row in backend.calls:
        msgs = call_row["messages"]
        assert [msg["content"] for msg in msgs[:4]] == [
            "Build dashboard.html using local JavaScript only.",
            "Created initial HTML.", "Avoid any new dependencies.", "No external deps.",
        ]
        assert msgs[4]["content"] == "Fix alignment"
    for call_row in backend.calls[1:]:
        rendered = repr(call_row["messages"])
        assert "NEW R1 PRIVATE" not in rendered
        assert "FORBIDDEN OLD R1" not in rendered
        assert "FORBIDDEN OLD R2" not in rendered
    for call_row in backend.calls[3:]:
        assert "NEW R2 PRIVATE" not in repr(call_row["messages"])
    assert json.dumps(user_history, sort_keys=True) == before


def test_prior_r3_is_thesis_only_but_prior_user_pair_survives_review():
    history = [{"role":"user", "content":"Original constraint: no npm."}]
    prior = CompletedSynthesis("Previous question: create a widget", "Previous A3", "ONE HOP R3 PRIVATE")
    backend = FakeBackend([{"content":"THESIS"}, {"content":"A2"}, {"content":"FINAL"}])
    engine = DeepReasoningOrchestrator(backend, prompts=PROMPTS, tools=TOOLS)
    end = run(engine.start(request="Now refine it", visible_history=history, prior_synthesis=prior,
                           preserve_thinking=True, require_verification=False))
    assert end.answer == "FINAL"
    for stage_call in backend.calls:
        messages = stage_call["messages"]
        assert messages[0] == history[0]
        assert messages[1:3] == [
            {"role":"user", "content":"Previous question: create a widget"},
            {"role":"assistant", "content":"Previous A3", **({"reasoning_content":"ONE HOP R3 PRIVATE"} if stage_call["stage"] == "thesis" else {})},
        ]
        assert messages[3]["content"] == "Now refine it"
        if stage_call["stage"] != "thesis":
            assert "ONE HOP R3 PRIVATE" not in repr(messages)


def test_optional_verification_with_available_tools_does_not_require_a_tool_call():
    backend = FakeBackend([
        {"content":"THESIS: design idea"},
        {"content":"SUPPORTED: no fourth playable character"},
        {"content":"FINAL"},
    ])
    engine = DeepReasoningOrchestrator(backend, prompts=PROMPTS, tools=TOOLS)
    result = run(engine.start(
        request="Design a fourth non-playable character",
        visible_history=[{"role":"user","content":"There can only be three playable characters."}],
        require_verification=False,
    ))
    assert result.answer == "FINAL"
    assert backend.calls[1]["tool_choice"] == "auto"
    assert backend.calls[1]["tools"] == TOOLS
    assert backend.calls[1]["messages"][0]["content"] == "There can only be three playable characters."
    assert backend.calls[1]["messages"][1]["content"] == "Design a fourth non-playable character"
    assert backend.calls[2]["stage"] == "synthesis"


def test_synthesis_final_claim_review_prompt_integrity_and_stage_isolation():
    from jack_deep_reasoning_orchestrator import load_exact_v6_prompts
    actual = load_exact_v6_prompts(Path(__file__).resolve().parents[1] / "tas_v6_prompts.json")
    xhigh = (
        "Reasoning effort is set to xhigh. Please think carefully through the task, "
        "validate key assumptions, consider plausible alternatives, and prioritize "
        "correctness, consistency, and clarity in the final answer."
    )
    assert actual["ULTRA_STAGE1_THESIS_PROMPT"].startswith(xhigh)
    assert actual["ULTRA_STAGE3_SYNTHESIS_PROMPT"].startswith(xhigh)
    addition = "Before producing the final answer, perform an independent final verification review"
    assert actual["ULTRA_STAGE3_SYNTHESIS_PROMPT"].count(addition) == 1
    assert "any new or altered factual claims, numerical values, or assumptions introduced during Synthesis itself" in actual["ULTRA_STAGE3_SYNTHESIS_PROMPT"]
    assert addition not in actual["ULTRA_STAGE1_THESIS_PROMPT"]
    assert addition not in actual["ULTRA_STAGE2_ANTITHESIS_PROMPT"]
    backend = FakeBackend([
        {"content":"THESIS"},
        {"content":"ANTITHESIS"},
        {"content":"SYNTHESIS"},
    ])
    engine = DeepReasoningOrchestrator(backend, prompts=actual, tools=[])
    completed = run(engine.start(request="Check 1 + 1", require_verification=False))
    assert completed.answer == "SYNTHESIS"
    assert [call["stage"] for call in backend.calls] == ["thesis", "antithesis", "synthesis"]
    assert backend.calls[-1]["system_prompt"] == actual["ULTRA_STAGE3_SYNTHESIS_PROMPT"]
    assert backend.calls[-1]["tool_choice"] == "auto"
