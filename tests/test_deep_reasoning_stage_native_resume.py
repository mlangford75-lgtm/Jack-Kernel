"""Host-free TAS continuity and stage-isolation contracts for all three roles."""
import asyncio
from jack_deep_reasoning_orchestrator import DeepReasoningOrchestrator, PendingToolRequest, CompletedAnswer
from jack_deep_reasoning_context import CompletedSynthesis

PROMPTS = {
    'ULTRA_STAGE1_THESIS_PROMPT': 'T',
    'ULTRA_STAGE2_ANTITHESIS_PROMPT': 'A',
    'ULTRA_STAGE3_SYNTHESIS_PROMPT': 'S',
}
TOOLS = [{'type':'function','function':{'name':'python_repl','parameters':{'type':'object'}}}]

def call(i):
    return {'type':'function','id':i,'function':{'name':'python_repl','arguments':'{}'}}

class Backend:
    def __init__(self, responses):
        self.responses=list(responses)
        self.requests=[]
    async def __call__(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)

async def resume(engine,pending):
    assert isinstance(pending,PendingToolRequest)
    return await engine.resume(pending,results=[{'tool_call_id':c['id'],'content':'host evidence'} for c in pending.calls])


def test_all_three_roles_keep_only_their_own_native_reasoning_through_tools():
    async def run():
        fake=Backend([
            {'tool_calls':[call('t1')], 'reasoning_content':'R1_T_1'},
            {'tool_calls':[call('t2')], 'reasoning_content':'R1_T_2'},
            {'content':'A1 final', 'reasoning_content':'R1_FINAL'},
            {'tool_calls':[call('a1')], 'reasoning_content':'R2_A_1'},
            {'tool_calls':[call('a2')], 'reasoning_content':'R2_A_2'},
            {'content':'A2 final', 'reasoning_content':'R2_FINAL'},
            {'tool_calls':[call('s1')], 'reasoning_content':'R3_S_1'},
            {'tool_calls':[call('s2')], 'reasoning_content':'R3_S_2'},
            {'content':'A3 final', 'reasoning_content':'R3_FINAL'},
        ])
        engine=DeepReasoningOrchestrator(fake,prompts=PROMPTS,tools=TOOLS,preserve_stage_tool_reasoning=True)
        state=await engine.start(request='Question', prior_synthesis=CompletedSynthesis('Old','Old A3','OLD_R3'), preserve_thinking=True)
        for _ in range(6):
            state=await resume(engine,state)
        assert isinstance(state, CompletedAnswer)
        assert state.answer=='A3 final' and state.synthesis_native_reasoning=='R3_FINAL'
        requests=fake.requests
        assert [r['stage'] for r in requests]==['thesis']*3+['antithesis']*3+['synthesis']*3
        for i,expected in [(1,['R1_T_1']), (2,['R1_T_1','R1_T_2']),
                           (4,['R2_A_1']), (5,['R2_A_1','R2_A_2']),
                           (7,['R3_S_1']), (8,['R3_S_1','R3_S_2'])]:
            msgs=requests[i]['messages']
            observed=[m['reasoning_content'] for m in msgs
                      if m.get('role')=='assistant' and m.get('tool_calls') and m.get('reasoning_content')]
            assert observed==expected
            assert all(m['tool_call_id'] for m in msgs if m['role']=='tool')
        assert 'OLD_R3' in repr(requests[0]['messages'])
        assert 'OLD_R3' not in repr(requests[1]['messages'])
        for i in (3,4,5):
            assert all(x not in repr(requests[i]['messages']) for x in ('R1_T_1','R1_T_2','R1_FINAL','OLD_R3'))
        for i in (6,7,8):
            assert all(x not in repr(requests[i]['messages']) for x in ('R1_T_1','R1_T_2','R2_A_1','R2_A_2','R2_FINAL'))
        assert 'A1 final' in repr(requests[3]['messages'])
        assert 'A2 final' in repr(requests[6]['messages'])
    asyncio.run(run())


def test_disabled_stage_native_does_not_replay_any_r1_r2_r3():
    async def run():
        fake=Backend([
            {'tool_calls':[call('t')],'reasoning_content':'PRIVATE_R1'},
            {'content':'A1'},
            {'tool_calls':[call('a')],'reasoning_content':'PRIVATE_R2'},
            {'content':'A2'},
            {'tool_calls':[call('s')],'reasoning_content':'PRIVATE_R3'},
            {'content':'A3','reasoning_content':'FINAL_R3'},
        ])
        engine=DeepReasoningOrchestrator(fake,prompts=PROMPTS,tools=TOOLS,preserve_stage_tool_reasoning=False)
        state=await engine.start(request='Q')
        for _ in range(3):state=await resume(engine,state)
        assert state.synthesis_native_reasoning=='FINAL_R3'
        for i,private in ((1,'PRIVATE_R1'),(3,'PRIVATE_R2'),(5,'PRIVATE_R3')):
            assert private not in repr(fake.requests[i]['messages'])
    asyncio.run(run())


def test_failed_same_stage_generation_does_not_corrupt_pending_state():
    class Flaky(Backend):
        def __init__(self):
            super().__init__([{'tool_calls':[call('t')],'reasoning_content':'R1_LEASE'}, {'content':'A1'}, {'content':'A2'}, {'content':'A3'}])
            self.fail=True
        async def __call__(self,**kwargs):
            if kwargs['stage']=='thesis' and any(m.get('role')=='tool' for m in kwargs['messages']) and self.fail:
                self.fail=False
                self.requests.append(kwargs)
                raise RuntimeError('backend transient')
            return await super().__call__(**kwargs)
    async def run():
        fake=Flaky()
        engine=DeepReasoningOrchestrator(fake,prompts=PROMPTS,tools=TOOLS,preserve_stage_tool_reasoning=True)
        state=await engine.start(request='Q',require_verification=False)
        try:
            await resume(engine,state)
        except RuntimeError as exc:
            assert str(exc)=='backend transient'
        else: raise AssertionError('expected failed generation')
        completed=await resume(engine,state)
        assert completed.answer=='A3'
        assert all('R1_LEASE' in repr(r['messages']) for r in fake.requests[1:3])
        assert 'R1_LEASE' not in repr(fake.requests[3]['messages'])
    asyncio.run(run())


def test_driver_marks_same_stage_tools_for_all_three_roles_and_honors_switch(monkeypatch):
    from types import SimpleNamespace
    from test_deep_reasoning_r3_bridge import FakeKernel, namespace, tool_surface
    from jack_deep_reasoning_kernel import install_deep_reasoning

    class AllStageKernel(FakeKernel):
        async def _run_stage(self, messages, secondary_system, stage_key, usage, *, tools, tool_choice, append, same_stage_resume=False):
            self.calls.append((stage_key,messages,tool_choice,same_stage_resume))
            step=stage_key.rsplit('_',1)[-1]
            if not any(m.get('role')=='tool' for m in messages):
                self.serial+=1
                cid='probe-'+str(self.serial)
                return {'choices':[{'message':{'tool_calls':[call(cid)],'reasoning_content':'PRIVATE_'+step}}]}
            return {'choices':[{'message':{'content':'ANSWER_'+step,'reasoning_content':'RESUMED_'+step}}]}

    async def run(preserve, switch):
        monkeypatch.setenv('JACK_TAS_STAGE_NATIVE_TOOL_CONTINUITY',switch)
        kernel=AllStageKernel()
        install_deep_reasoning(kernel,namespace(preserve))
        state=await kernel._prepare_commit({'messages':[{'role':'user','content':'Q'}],'tools':tool_surface()})
        for _ in range(3):
            cid=state.tool_calls[0]['id']
            state=await kernel._resume_tool_stage_nonstream(
                kernel._pending_tool_resumes[cid],[{'tool_call_id':cid,'content':'proof'}])
        assert state.content=='ANSWER_synthesis'
        assert len(kernel.calls)==6
        assert [r[0] for r in kernel.calls]==[
            'deep_reasoning_thesis','deep_reasoning_thesis',
            'deep_reasoning_antithesis','deep_reasoning_antithesis',
            'deep_reasoning_synthesis','deep_reasoning_synthesis']
        for i,stage in ((1,'thesis'),(3,'antithesis'),(5,'synthesis')):
            continuation=kernel.calls[i]
            assert continuation[3] is bool(preserve)
            if preserve and switch!='0':
                assert 'PRIVATE_'+stage in repr(continuation[1])
            else:
                assert 'PRIVATE_'+stage not in repr(continuation[1])
        assert 'PRIVATE_thesis' not in repr(kernel.calls[2][1])
        assert 'PRIVATE_antithesis' not in repr(kernel.calls[4][1])
        assert 'PRIVATE_synthesis' not in repr(kernel.calls[0][1])
    asyncio.run(run(True,'1'))
    asyncio.run(run(True,'0'))
    asyncio.run(run(False,'1'))
