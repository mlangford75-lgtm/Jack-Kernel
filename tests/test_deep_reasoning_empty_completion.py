"""Regression cases for observed Pi/LM Studio empty-Thesis-after-tool run.

No live backend and no external tool execution. All stage prompts remain unchanged.
"""
import asyncio
from types import SimpleNamespace
from pathlib import Path

import pytest

from jack_deep_reasoning_orchestrator import (
    DeepReasoningOrchestrator, DeepReasoningProtocolError, PendingToolRequest,
)
from jack_deep_reasoning_kernel import install_deep_reasoning

PROMPTS = {
    'ULTRA_STAGE1_THESIS_PROMPT': 'EXACT_THESIS',
    'ULTRA_STAGE2_ANTITHESIS_PROMPT': 'EXACT_ANTI',
    'ULTRA_STAGE3_SYNTHESIS_PROMPT': 'EXACT_SYNTH',
}
TOOLS = [{'type':'function','function':{'name':'python_repl','parameters':{'type':'object'}}}]
CALL = {'id':'t-1','type':'function','function':{'name':'python_repl','arguments':'{}'}}
ANTI_CALL = {'id':'a-1','type':'function','function':{'name':'python_repl','arguments':'{}'}}

class Backend:
    def __init__(self, replies):
        self.replies=list(replies)
        self.calls=[]
    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        assert self.replies, 'Unexpected inference'
        return self.replies.pop(0)

def run(coro):
    return asyncio.run(coro)

def engine(backend):
    return DeepReasoningOrchestrator(backend,prompts=PROMPTS,tools=TOOLS)

def test_empty_thesis_after_tool_gets_one_identical_stage_retry_and_continues():
    backend=Backend([
        {'tool_calls':[CALL]},
        {'content':None,'reasoning_content':'INCOMPLETE_R1','_tas_finish_reason':'stop','_tas_completion_tokens':500},
        {'content':'THESIS: 2002','reasoning_content':'FINAL_R1','_tas_finish_reason':'stop'},
        {'tool_calls':[ANTI_CALL]},
        {'content':'ANTI independently verified 2002'},
        {'content':'SYNTHESIS: 2002','reasoning_content':'R3'},
    ])
    orchestrator=engine(backend)
    pending=run(orchestrator.start(request='PIN digits'))
    assert isinstance(pending,PendingToolRequest) and pending.stage=='thesis'
    anti=run(orchestrator.resume(pending, results=[{'tool_call_id':'t-1','content':'Brute-force: 2002'}]))
    assert anti.stage=='antithesis'
    assert backend.calls[1] == backend.calls[2], 'Retry must not alter stage prompt or projected context'
    assert backend.calls[1]['system_prompt']=='EXACT_THESIS'
    assert backend.calls[1]['temperature']==1.0
    assert backend.calls[1]['reasoning_effort']=='xhigh'
    assert 'INCOMPLETE_R1' not in repr(backend.calls[2]['messages'])
    answer=run(orchestrator.resume(anti, results=[{'tool_call_id':'a-1','content':'2002'}]))
    assert answer.answer=='SYNTHESIS: 2002'
    assert answer.synthesis_native_reasoning=='R3'
    assert 'FINAL_R1' not in repr(backend.calls[-1]['messages'])
    assert 'INCOMPLETE_R1' not in repr(backend.calls[-1]['messages'])

def test_repeated_empty_thesis_fails_closed_and_gives_nonsecret_diagnostics():
    backend=Backend([
        {'tool_calls':[CALL]},
        {'content':'','reasoning_content':'PRIVATE_NATIVE_R1','_tas_finish_reason':'stop','_tas_completion_tokens':200},
        {'content':None,'reasoning_content':'SECRET_R1','_tas_finish_reason':'stop','_tas_completion_tokens':255},
    ])
    o=engine(backend)
    pending=run(o.start(request='PIN'))
    with pytest.raises(DeepReasoningProtocolError,match='backend_finish_reason=stop') as exc:
        run(o.resume(pending, results=[{'tool_call_id':'t-1','content':'2002'}]))
    assert 'PRIVATE_NATIVE_R1' not in str(exc.value)
    assert 'SECRET_R1' not in str(exc.value)
    assert len(backend.calls)==3
    assert backend.calls[1]==backend.calls[2]
    assert pending.session.outstanding==(CALL,), 'Failed session must be retryable'

def test_length_finish_is_not_accepted_and_not_retried():
    backend=Backend([{'content':'THESIS incomplete','_tas_finish_reason':'length'}])
    with pytest.raises(DeepReasoningProtocolError, match='truncated at token limit'):
        run(engine(backend).start(request='Q'))
    assert len(backend.calls)==1

def test_synthesis_empty_retries_without_leaking_old_stage_native_reasoning():
    backend=Backend([
        {'content':'THESIS','reasoning_content':'SECRET_R1'},
        {'tool_calls':[ANTI_CALL]},
        {'content':'ANTI','reasoning_content':'SECRET_R2'},
        {'content':'','reasoning_content':'PARTIAL_R3','_tas_finish_reason':'stop'},
        {'content':'FINAL','reasoning_content':'FINAL_R3','_tas_finish_reason':'stop'},
    ])
    o=engine(backend)
    anti=run(o.start(request='Q'))
    answer=run(o.resume(anti,results=[{'tool_call_id':'a-1','content':'independent'}]))
    assert answer.answer=='FINAL'
    assert answer.synthesis_native_reasoning=='FINAL_R3'
    assert backend.calls[-1]==backend.calls[-2]
    assert 'SECRET_R1' not in repr(backend.calls[-1]['messages'])
    assert 'SECRET_R2' not in repr(backend.calls[-1]['messages'])


def test_kernel_adapter_keeps_finish_reason_internal_not_model_visible(tmp_path):
    # Check the source-level transport contract: the raw backend metadata is
    # attached to the local adapter message, never to a Pi output or prompt.
    driver=Path(__file__).resolve().parents[1]/'jack_deep_reasoning_kernel.py'
    source=driver.read_text(encoding='utf-8')
    assert 'message["_tas_finish_reason"] = choice_response.get("finish_reason")' in source
    assert 'message["_tas_completion_tokens"] = counted if isinstance(counted, int) else None' in source
