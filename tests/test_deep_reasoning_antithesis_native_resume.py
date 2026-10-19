"""Opt-in native R2 lives only in Antithesis' own tool continuation."""
import asyncio

from jack_deep_reasoning_orchestrator import (
    DeepReasoningOrchestrator, PendingToolRequest, CompletedAnswer,
)
from jack_deep_reasoning_context import append_stage_local_tool_results

PROMPTS = {
    "ULTRA_STAGE1_THESIS_PROMPT": "Thesis exact",
    "ULTRA_STAGE2_ANTITHESIS_PROMPT": "Antithesis exact",
    "ULTRA_STAGE3_SYNTHESIS_PROMPT": "Synthesis exact",
}
TOOLS = [{"type":"function","function":{"name":"python_repl","parameters":{"type":"object"}}}]

def toolcall(tool_id):
    return {"id":tool_id, "type":"function", "function":{"name":"python_repl","arguments":"{}"}}

class Model:
    def __init__(self, *results):
        self.results=list(results)
        self.calls=[]
    async def __call__(self, **k):
        self.calls.append(k)
        return self.results.pop(0)

def start(engine):
    return asyncio.run(engine.start(request="Analyze the clock", require_verification=True))

def resume(engine, pending, output="proof"):
    return asyncio.run(engine.resume(pending, results=[{"tool_call_id":pending.calls[0]["id"],"content":output}]))

def test_optin_antithesis_r2_survives_one_tool_and_not_synthesis():
    model=Model(
        {"content":"THESIS A1", "reasoning_content":"R1 SECRET"},
        {"tool_calls":[toolcall("id1")],"reasoning_content":"R2 CLOCK_NUMERALS_OVERLAP_AT_CENTER"},
        {"content":"ANTITHESIS FOUND OVERLAP", "reasoning_content":"R2 PRIVATE FINAL"},
        {"content":"FINAL FIX CLOCK", "reasoning_content":"R3 FINAL"},
    )
    engine=DeepReasoningOrchestrator(model,prompts=PROMPTS,tools=TOOLS,preserve_stage_tool_reasoning=True)
    pending=start(engine)
    assert isinstance(pending,PendingToolRequest)
    final=resume(engine,pending)
    assert isinstance(final,CompletedAnswer)
    anti_resume=model.calls[2]["messages"]
    assert anti_resume[-2]["role"] == "assistant"
    assert anti_resume[-2]["reasoning_content"] == "R2 CLOCK_NUMERALS_OVERLAP_AT_CENTER"
    assert anti_resume[-2]["tool_calls"][0]["id"] == anti_resume[-1]["tool_call_id"]
    assert "R1 SECRET" not in str(anti_resume)
    synthesis=model.calls[3]["messages"]
    assert "R2 CLOCK_NUMERALS_OVERLAP_AT_CENTER" not in str(synthesis)
    assert "R2 PRIVATE FINAL" not in str(synthesis)
    assert "R1 SECRET" not in str(synthesis)
    assert "ANTITHESIS FOUND OVERLAP" in str(synthesis)
    assert final.synthesis_native_reasoning == "R3 FINAL"


def test_disabled_no_r2_restoration():
    model=Model(
        {"content":"A1"},
        {"tool_calls":[toolcall("id1")],"reasoning_content":"R2 SHOULD NOT APPEAR"},
        {"content":"A2"},
        {"content":"A3"},
    )
    engine=DeepReasoningOrchestrator(model,prompts=PROMPTS,tools=TOOLS)
    p=start(engine)
    resume(engine,p)
    assert "R2 SHOULD NOT APPEAR" not in str(model.calls[2]["messages"])


def test_same_stage_second_tool_keeps_prior_r2_but_stage_transition_doesnt():
    model=Model(
        {"content":"A1"},
        {"tool_calls":[toolcall("id1")],"reasoning_content":"R2 ROUND ONE"},
        {"tool_calls":[toolcall("id2")],"reasoning_content":"R2 ROUND TWO"},
        {"content":"A2"},
        {"content":"A3"},
    )
    engine=DeepReasoningOrchestrator(model,prompts=PROMPTS,tools=TOOLS,preserve_stage_tool_reasoning=True)
    p=start(engine)
    p2=resume(engine,p)
    assert isinstance(p2,PendingToolRequest)
    final=resume(engine,p2)
    assert isinstance(final,CompletedAnswer)
    messages=model.calls[3]["messages"]
    assert [m.get("reasoning_content") for m in messages if m.get("reasoning_content")] == ["R2 ROUND ONE", "R2 ROUND TWO"]
    synthesis=str(model.calls[4]["messages"])
    assert "R2 ROUND ONE" not in synthesis
    assert "R2 ROUND TWO" not in synthesis


def test_old_role_reasoning_aliases_always_stripped_in_optin_mode():
    history=[
        {"role":"assistant","content":"A1","reasoning_content":"R1 LEAK","thinking":"R1 ALIAS"},
        {"role":"user","content":"Check"},
    ]
    result=append_stage_local_tool_results(
        history, tool_calls=[toolcall("id1")],
        results=[{"tool_call_id":"id1","content":"done"}],
        native_reasoning="R2 OK", preserve_same_stage_native=True,
    )
    assert result[0] == {"role":"assistant","content":"A1"}
    assert result[-2].get("reasoning_content") == "R2 OK"
    assert "R1 LEAK" not in str(result)
    assert "R1 ALIAS" not in str(result)


def test_failed_backend_resume_rolls_back_and_replay_keeps_r2():
    class RetryModel(Model):
        def __init__(self):
            super().__init__({"content":"A1"},{"tool_calls":[toolcall("id1")],"reasoning_content":"R2 RETRY PROOF"})
            self.fail=True
        async def __call__(self,**k):
            self.calls.append(k)
            if not self.results and self.fail:
                self.fail=False
                raise RuntimeError("backend retry")
            if not self.results:
                if k["stage"]=="antithesis":
                    return {"content":"A2"}
                return {"content":"A3"}
            return self.results.pop(0)
    model=RetryModel()
    engine=DeepReasoningOrchestrator(model,prompts=PROMPTS,tools=TOOLS,preserve_stage_tool_reasoning=True)
    p=start(engine)
    import pytest
    with pytest.raises(RuntimeError,match="backend retry"):
        resume(engine,p)
    final=resume(engine,p)
    assert final.answer=="A3"
    assert all("R2 RETRY PROOF" in str(c["messages"]) for c in model.calls[2:4])
    assert "R2 RETRY PROOF" not in str(model.calls[4]["messages"])
