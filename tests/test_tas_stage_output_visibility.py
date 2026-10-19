"""Stage outputs must be observable without changing TAS answer authority."""
from __future__ import annotations
import asyncio
import json
from test_deep_reasoning_thesis_live_protocol import ThesisToolKernel
from test_deep_reasoning_r3_bridge import namespace, tool_surface
from jack_deep_reasoning_kernel import install_deep_reasoning
from deep_reasoning_pi_stream import deep_reasoning_pi_stream

class WireKernel(ThesisToolKernel):
    async def _run_stage_streamed(self, *args, **kwargs):
        key=args[2]
        yield {'kind':'reasoning','text':'NATIVE_'+key}
        yield {'kind':'result','data':await self._run_stage(*args,**kwargs)}
    async def _run_impl(self,request):
        if 'tool_result' in request:
            callid=request['tool_result']
            return await self._resume_tool_stage_nonstream(
                self._pending_tool_resumes[callid],[{'tool_call_id':callid,'content':'5050'}])
        return await self._prepare_commit(request)

def parsed(frames):
    return [json.loads(f[6:]) for f in frames if f.startswith(b'data: {')]

def reasoning(events):
    return ''.join(e['choices'][0]['delta'].get('reasoning_content','') for e in events if e.get('choices'))

def final_content(events):
    return ''.join(e['choices'][0]['delta'].get('content','') for e in events if e.get('choices'))

def test_a1_a2_visible_in_reasoning_observer_not_as_final_answer():
    async def run():
        k=WireKernel();ns=namespace(True);install_deep_reasoning(k,ns)
        async def transaction(req):
            return parsed([f async for f in deep_reasoning_pi_stream(k,req,ns)])
        first=await transaction({'messages':[{'role':'user','content':'sum'}], 'tools':tool_surface()})
        assert '[THESIS]' in reasoning(first)
        assert 'A1_VERIFIED 5050' not in reasoning(first)
        assert 'A1_VERIFIED 5050' not in final_content(first)
        assert final_content(first)==''
        second=await transaction({'tool_result':'thesis-call-1'})
        rs=reasoning(second)
        assert '[THESIS]' in rs and '[THESIS OUTPUT]\nA1_VERIFIED 5050' in rs
        assert '[ANTITHESIS]' in rs
        assert rs.index('[THESIS OUTPUT]') < rs.index('[ANTITHESIS]')
        assert 'A1_VERIFIED 5050' not in final_content(second)
        last=await transaction({'tool_result':'antithesis-call-1'})
        rl=reasoning(last)
        assert '[ANTITHESIS OUTPUT]\nA2_CHECKED 5050' in rl
        assert '[SYNTHESIS]' in rl
        assert rl.index('[ANTITHESIS OUTPUT]') < rl.index('[SYNTHESIS]')
        assert 'A2_CHECKED 5050' not in final_content(last)
        assert final_content(last)=='A3_ANSWER 5050'
        assert all('[Deep Reasoning:' not in reasoning(x) for x in (first,second,last))
        assert 'R1_PRIVATE' not in repr(k.calls[2][1])
        assert 'R2_PRIVATE' not in repr(k.calls[-1][1])
    asyncio.run(run())
