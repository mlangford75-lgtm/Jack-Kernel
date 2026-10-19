"""Regression: transient backend failure cannot consume pending TAS tool state."""
import asyncio
import pytest
from jack_deep_reasoning_orchestrator import (
    DeepReasoningOrchestrator,
    PendingToolRequest,
    CompletedAnswer,
    load_exact_v6_prompts,
)
from pathlib import Path


def test_transient_antithesis_continuation_preserves_pending_identity():
    async def scenario():
        calls = []
        failed = False
        async def backend(**kwargs):
            nonlocal failed
            stage = kwargs['stage']
            calls.append((stage, kwargs['messages']))
            if stage == 'thesis':
                return {'content': 'Thesis believes B=15', 'reasoning_content': 'SECRET_R1'}
            if stage == 'antithesis':
                if not any(msg['role'] == 'tool' for msg in kwargs['messages']):
                    return {'tool_calls': [{'id': 'c1', 'type': 'function', 'function': {'name': 'python_repl', 'arguments': '{"code":"print(17)"}'}}]}
                if not failed:
                    failed = True
                    raise ConnectionError('simulated transient model backend error')
                return {'content': 'Antithesis verified B=17', 'reasoning_content': 'SECRET_R2'}
            if stage == 'synthesis':
                return {'content': 'B=17', 'reasoning_content': 'SECRET_R3'}
            raise AssertionError(stage)
        prompts = load_exact_v6_prompts(Path(__file__).resolve().parents[1] / 'tas_v6_prompts.json')
        orch = DeepReasoningOrchestrator(backend, prompts=prompts, tools=[{'type':'function','function':{'name':'python_repl'}}])
        pending = await orch.start(request='Count bracelets', require_verification=True)
        assert isinstance(pending, PendingToolRequest)
        token = pending.generation
        assert pending.session.outstanding == pending.calls
        first_messages = pending.session.messages
        with pytest.raises(ConnectionError):
            await orch.resume(pending, results=[{'tool_call_id':'c1','content':'17'}])
        assert pending.session.generation == token
        assert pending.session.outstanding == pending.calls
        assert pending.session.messages == first_messages
        assert pending.session.evidence == []
        assert pending.session.tool_rounds == 0
        answer = await orch.resume(pending, results=[{'tool_call_id':'c1','content':'17'}])
        assert isinstance(answer, CompletedAnswer)
        assert answer.answer == 'B=17'
        assert len(answer.evidence) == 1
        assert answer.evidence[0]['raw_result'] == '17'
        antithesis_request = [v for k,v in calls if k=='antithesis'][-1]
        synthesis_request = [v for k,v in calls if k=='synthesis'][-1]
        assert 'SECRET_R1' not in repr(antithesis_request)
        assert 'SECRET_R1' not in repr(synthesis_request)
        assert 'SECRET_R2' not in repr(synthesis_request)
    asyncio.run(scenario())


def test_transient_synthesis_failure_rolls_back_previous_stage_transition():
    async def scenario():
        calls=[]
        failed=False
        async def backend(**kwargs):
            nonlocal failed
            calls.append(kwargs['stage'])
            if kwargs['stage']=='thesis': return {'content':'candidate'}
            if kwargs['stage']=='antithesis':
                if any(m['role']=='tool' for m in kwargs['messages']): return {'content':'findings'}
                return {'tool_calls':[{'id':'c1','type':'function','function':{'name':'python_repl','arguments':'{}'}}]}
            if not failed:
                failed=True
                raise ConnectionError('synthesis unavailable')
            return {'content':'final','reasoning_content':'R3'}
        prompts=load_exact_v6_prompts(Path(__file__).resolve().parents[1]/'tas_v6_prompts.json')
        orch=DeepReasoningOrchestrator(backend,prompts=prompts,tools=[{'type':'function','function':{'name':'python_repl'}}])
        pending=await orch.start(request='task')
        with pytest.raises(ConnectionError):
            await orch.resume(pending,results=[{'tool_call_id':'c1','content':'verified'}])
        assert pending.session.stage == 'antithesis'
        assert pending.session.generation == pending.generation
        assert pending.session.outstanding == pending.calls
        assert pending.session.antithesis_findings == ''
        answer=await orch.resume(pending,results=[{'tool_call_id':'c1','content':'verified'}])
        assert isinstance(answer,CompletedAnswer) and answer.answer=='final'
    asyncio.run(scenario())
