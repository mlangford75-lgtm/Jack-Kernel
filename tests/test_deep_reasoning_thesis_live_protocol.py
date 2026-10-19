"""Mock host/Pi cycle for the production-blocking Thesis tool continuation gap."""
import asyncio
from types import SimpleNamespace
from test_deep_reasoning_r3_bridge import FakeKernel, namespace, tool_surface
from jack_deep_reasoning_kernel import install_deep_reasoning


class ThesisToolKernel(FakeKernel):
    def __init__(self):
        super().__init__()
        self.phase = 0
        self.registrations = []
    async def _run_stage(self, messages, secondary_system, stage_key, usage, *, tools, tool_choice, append, same_stage_resume=False):
        self.calls.append((stage_key, messages, tool_choice, same_stage_resume))
        if stage_key == 'deep_reasoning_thesis':
            if not any(m.get('role') == 'tool' for m in messages):
                self.phase += 1
                return {'choices':[{'message':{
                  'tool_calls':[{'id':f'thesis-call-{self.phase}', 'type':'function',
                                  'function':{'name':'python_repl','arguments':'{"code":"print(5050)"}'}}],
                  'reasoning_content':'R1_PRIVATE'}}]}
            return {'choices':[{'message':{'content':'A1_VERIFIED 5050', 'reasoning_content':'R1_PRIVATE_RESUMED'}}]}
        if stage_key == 'deep_reasoning_antithesis':
            if not any(m.get('role') == 'tool' for m in messages):
                return {'choices':[{'message':{
                  'tool_calls':[{'id':f'antithesis-call-{self.phase}', 'type':'function',
                                  'function':{'name':'python_repl','arguments':'{"code":"sum(range(101))"}'}}],
                  'reasoning_content':'R2_PRIVATE'}}]}
            return {'choices':[{'message':{'content':'A2_CHECKED 5050','reasoning_content':'R2_PRIVATE_RESUMED'}}]}
        if stage_key == 'deep_reasoning_synthesis':
            return {'choices':[{'message':{'content':'A3_ANSWER 5050', 'reasoning_content':'R3_AVAILABLE'}}]}
        raise AssertionError(stage_key)

    async def _register_stage_tool_resume(self, **kwargs):
        self.registrations.append(kwargs)
        calls = kwargs['data']['choices'][0]['message']['tool_calls']
        state = SimpleNamespace(resume_id=f'resume-{self.phase}-{kwargs["stage_key"]}', stage_key=kwargs['stage_key'])
        for c in calls:
            self._pending_tool_resumes[c['id']] = state
        return SimpleNamespace(finish_reason='tool_calls', tool_calls=calls, usage={})


def test_pi_thesis_tool_then_anti_tool_then_synthesis():
    async def run():
        kernel = ThesisToolKernel()
        install_deep_reasoning(kernel, namespace(True))
        original = [{'role':'user','content':'1+100 sum'}]
        first = await kernel._prepare_commit({'messages':original, 'tools':tool_surface()})
        assert first.finish_reason == 'tool_calls' and first.content is None and first.reasoning_content is None
        assert first.tool_calls[0]['id'] == 'thesis-call-1'
        stage_after = await kernel._resume_tool_stage_nonstream(
            kernel._pending_tool_resumes['thesis-call-1'],
            [{'tool_call_id':'thesis-call-1', 'content':'5050'}])
        assert stage_after.finish_reason == 'tool_calls'
        assert stage_after.tool_calls[0]['id'] == 'antithesis-call-1'
        result = await kernel._resume_tool_stage_nonstream(
            kernel._pending_tool_resumes['antithesis-call-1'],
            [{'tool_call_id':'antithesis-call-1', 'content':'5050'}])
        assert result.finish_reason == 'stop' and result.content == 'A3_ANSWER 5050'
        assert result.reasoning_content == 'R3_AVAILABLE'
        assert [r['stage_key'] for r in kernel.registrations] == ['deep_reasoning_thesis','deep_reasoning_antithesis']
        assert 'R1_PRIVATE' not in repr(kernel.calls[2][1])
        assert 'R1_PRIVATE' not in repr(kernel.calls[3][1])
        # Same-stage Antithesis tool continuation now keeps its own R2, while
        # Synthesis remains isolated from it and from Thesis R1.
        assert 'R2_PRIVATE' in repr(kernel.calls[3][1])
        assert 'R2_PRIVATE' not in repr(kernel.calls[4][1])
        assert '5050' in repr(kernel.calls[-1][1])
        assert kernel.calls[1][3] is True   # resumed Thesis, same-stage scope
        assert kernel.calls[2][3] is False  # independent Antithesis
    asyncio.run(run())


def test_r3_survives_thesis_tool_checkpoint_and_retires_at_its_answer():
    async def run():
        kernel = ThesisToolKernel()
        install_deep_reasoning(kernel, namespace(True))
        first = await kernel._prepare_commit({'messages':[{'role':'user','content':'previous request'}], 'tools':tool_surface()})
        ant = await kernel._resume_tool_stage_nonstream(kernel._pending_tool_resumes['thesis-call-1'],[{'tool_call_id':'thesis-call-1','content':'5050'}])
        last = await kernel._resume_tool_stage_nonstream(kernel._pending_tool_resumes['antithesis-call-1'],[{'tool_call_id':'antithesis-call-1','content':'5050'}])
        assert last.content == 'A3_ANSWER 5050'
        before=len(kernel.calls)
        history=[{'role':'user','content':'previous request'},{'role':'assistant','content':last.content},{'role':'user','content':'next request'}]
        candidate = await kernel._prepare_commit({'messages':history, 'tools':tool_surface()})
        assert candidate.tool_calls[0]['id'] == 'thesis-call-2'
        assert 'R3_AVAILABLE' in repr(kernel.calls[before][1])
        assert 'R3_AVAILABLE' not in repr(kernel.registrations[-1]['history'])
        ant = await kernel._resume_tool_stage_nonstream(kernel._pending_tool_resumes['thesis-call-2'],[{'tool_call_id':'thesis-call-2','content':'5050'}])
        assert 'R3_AVAILABLE' not in repr(kernel.calls[-1][1])
        assert 'R1_PRIVATE' not in repr(kernel.calls[-1][1])
        await kernel._resume_tool_stage_nonstream(kernel._pending_tool_resumes['antithesis-call-2'],[{'tool_call_id':'antithesis-call-2','content':'5050'}])
        before=len(kernel.calls)
        third=[{'role':'user','content':'previous request'},{'role':'assistant','content':last.content},
               {'role':'user','content':'next request'},{'role':'assistant','content':'A3_ANSWER 5050'},
               {'role':'user','content':'third request'}]
        await kernel._prepare_commit({'messages':third,'tools':tool_surface()})
        # New R3 may appear, but the previous R3 must not be retained as a different
        # source -- identical textual reasoning makes this unobservable in this fake.
        assert kernel.calls[before][0]=='deep_reasoning_thesis'
    asyncio.run(run())


def test_pi_sse_transport_for_thesis_and_antithesis_tool_checkpoints():
    import json
    from deep_reasoning_pi_stream import deep_reasoning_pi_stream
    class WireKernel(ThesisToolKernel):
        async def _run_stage_streamed(self, *args, **kwargs):
            stage_key = args[2]
            yield {'kind':'reasoning','text':'STREAM_NATIVE_'+stage_key}
            yield {'kind':'result','data': await self._run_stage(*args, **kwargs)}
        async def _run_impl(self, request):
            if 'tool_result' in request:
                callid = request['tool_result']
                return await self._resume_tool_stage_nonstream(
                    self._pending_tool_resumes[callid],
                    [{'tool_call_id':callid,'content':'5050'}])
            return await self._prepare_commit(request)
    async def run():
        kernel=WireKernel()
        ns=namespace(True)
        install_deep_reasoning(kernel,ns)
        async def frames(body):
            return [b async for b in deep_reasoning_pi_stream(kernel,body,ns)]
        def parsed(frames):
            return [json.loads(f[6:]) for f in frames if f.startswith(b'data: {')]
        t=parsed(await frames({'messages':[{'role':'user','content':'sum'}], 'tools':tool_surface()}))
        assert any(e['choices'][0]['delta'].get('reasoning_content') == 'STREAM_NATIVE_deep_reasoning_thesis' for e in t if e['choices'])
        assert any(e['choices'][0]['delta'].get('tool_calls',[{}])[0].get('id')=='thesis-call-1' for e in t if e['choices'])
        assert any(e['choices'][0]['finish_reason']=='tool_calls' for e in t if e['choices'])
        a=parsed(await frames({'tool_result':'thesis-call-1'}))
        assert any(e['choices'][0]['delta'].get('reasoning_content') == 'STREAM_NATIVE_deep_reasoning_antithesis' for e in a if e['choices'])
        assert any(e['choices'][0]['delta'].get('tool_calls',[{}])[0].get('id')=='antithesis-call-1' for e in a if e['choices'])
        assert any(e['choices'][0]['finish_reason']=='tool_calls' for e in a if e['choices'])
        f=parsed(await frames({'tool_result':'antithesis-call-1'}))
        assert any(e['choices'][0]['delta'].get('reasoning_content') == 'STREAM_NATIVE_deep_reasoning_synthesis' for e in f if e['choices'])
        assert any(e['choices'][0]['delta'].get('content')=='A3_ANSWER 5050' for e in f if e['choices'])
        assert any(e['choices'][0]['finish_reason']=='stop' for e in f if e['choices'])
    asyncio.run(run())


def test_large_tool_receipt_is_explicitly_truncated_before_synthesis():
    from jack_deep_reasoning_orchestrator import DeepReasoningOrchestrator, MAX_TAS_EVIDENCE_CHARS
    from test_deep_reasoning_orchestrator import PROMPTS, TOOLS, FakeBackend, call
    async def run():
        fake=FakeBackend([{'content':'T'},{'tool_calls':[call('anti1')]},{'content':'ANTI'},{'content':'FINAL'}])
        engine=DeepReasoningOrchestrator(fake, prompts=PROMPTS, tools=TOOLS)
        pending=await engine.start(request='Task')
        big='X'*(MAX_TAS_EVIDENCE_CHARS+123)
        end=await engine.resume(pending,results=[{'tool_call_id':'anti1','content':big}])
        receipt=end.evidence[0]
        assert receipt['raw_result_truncated'] is True
        assert receipt['raw_result_total_chars']==len(big)
        assert len(receipt['raw_result'])==MAX_TAS_EVIDENCE_CHARS
        assert str(len(big)) in repr(fake.calls[-1]['messages'])
    asyncio.run(run())
