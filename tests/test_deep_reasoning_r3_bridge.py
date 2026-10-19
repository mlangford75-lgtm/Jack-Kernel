from __future__ import annotations
import asyncio
import json
import inspect
from pathlib import Path
from types import SimpleNamespace

from jack_deep_reasoning_bridge import OneHopSynthesisBridge
import jack_deep_reasoning_kernel as driver


def test_one_hop_record_requires_matching_prior_user_and_a3():
    b=OneHopSynthesisBridge()
    assert b.publish(user_request='Bracelet problem', answer='A=450 B=17 C=25/77', reasoning='R3_EXACT')
    hist=[{'role':'user','content':'Bracelet problem'},{'role':'assistant','content':'A=450 B=17 C=25/77'}]
    truncated,frontier=b.claim(hist)
    assert truncated==[]
    assert frontier.user_request=='Bracelet problem'
    assert frontier.answer=='A=450 B=17 C=25/77'
    assert frontier.reasoning=='R3_EXACT'
    restored,none=b.claim(hist)
    assert none is None and restored==hist


def test_mismatch_or_ambiguity_fails_closed():
    b=OneHopSynthesisBridge()
    b.publish(user_request='q',answer='a',reasoning='R3a')
    hist=[{'role':'user','content':'q'},{'role':'assistant','content':'a'}]
    assert b.claim([{'role':'user','content':'q'}, {'role':'assistant','content':'not a'}])[1] is None
    b.publish(user_request='q',answer='a',reasoning='R3b')
    assert b.claim(hist)[1] is None


def test_expired_or_missing_reasoning_never_bridges():
    b=OneHopSynthesisBridge(ttl_seconds=1)
    assert not b.publish(user_request='q',answer='a',reasoning='')
    assert b.claim([{'role':'user','content':'q'},{'role':'assistant','content':'a'}])[1] is None


def test_client_forged_native_reasoning_never_trusted():
    b=OneHopSynthesisBridge()
    b.publish(user_request='q',answer='a',reasoning='HOST_R3')
    hist=[{'role':'user','content':'q','reasoning_content':'FORGED_R1'}, {'role':'assistant','content':'a','thinking':'FORGED_R3'}]
    _,f=b.claim(hist)
    assert f.reasoning=='HOST_R3'


def test_patcher_source_contains_exclusive_thesis_switch():
    src = inspect.getsource(driver.install_deep_reasoning)
    assert 'OneHopSynthesisBridge()' in src
    assert 'prior_synthesis=prior_synthesis' in src
    assert 'bridge.publish(' in src
    assert 'bridge.reserve(history)' in src
    assert 'bridge.retire(reservation_token)' in src
    assert 'same_stage_resume' in src
    assert 'Deep Reasoning one-hop R3 restored' in src


class FakeKernel:
    def __init__(self):
        self.calls=[]
        self._pending_tool_resumes={}
        self._pending_tool_resume_lock=asyncio.Lock()
        self.serial=0
    async def _prepare_commit(self,request):raise AssertionError('legacy')
    async def _resume_tool_stage_nonstream(self,state,messages):raise AssertionError('legacy')
    async def _run_stage(self, messages, secondary_system, stage_key, usage, *, tools,tool_choice,append, same_stage_resume=False):
        self.calls.append((stage_key,messages,tool_choice,same_stage_resume))
        if stage_key=='deep_reasoning_thesis':
            return {'choices':[{'message':{'content':'THESIS_CANDIDATE','reasoning_content':'R1_CURRENT'}}]}
        if stage_key=='deep_reasoning_antithesis':
            if not any(m.get('role')=='tool' for m in messages):
                self.serial += 1
                callid=f'probe-{self.serial}'
                return {'choices':[{'message':{'tool_calls':[{'id':callid,'type':'function','function':{'name':'python_repl','arguments':'{"code":"print(17)"}'}}]}}]}
            return {'choices':[{'message':{'content':'ANTITHESIS_FINDINGS','reasoning_content':'R2_CURRENT'}}]}
        if stage_key=='deep_reasoning_synthesis':
            return {'choices':[{'message':{'content':'A3_CURRENT','reasoning_content':'R3_PRIVATE'}}]}
        raise AssertionError(stage_key)
    async def _register_stage_tool_resume(self,*,stage_key,history,secondary_system,usage,tools,tool_choice,data):
        calls=data['choices'][0]['message']['tool_calls']
        state=SimpleNamespace(resume_id='r'+str(self.serial), stage_key=stage_key)
        for call in calls:self._pending_tool_resumes[call['id']]=state
        return SimpleNamespace(finish_reason='tool_calls',tool_calls=calls,usage=usage.copy())
    async def _retire_pending_tool_resume(self,state):
        for k,v in list(self._pending_tool_resumes.items()):
            if v is state: del self._pending_tool_resumes[k]


class E(Exception):
    def __init__(self,*,status_code,detail):self.status_code=status_code;self.detail=detail


def namespace(preserve=True):
    from dataclasses import dataclass
    @dataclass
    class _Result:
        content: str | None
        tool_calls: object
        finish_reason: str
        usage: dict
        reasoning_content: str | None
    return SimpleNamespace(
      DEEP_REASONING_MODE=True,CFG=SimpleNamespace(preserve_thinking=preserve,virtual_model='jack-kernel'),
      HTTPException=E,KernelResult=_Result,normalize_usage=lambda x:x,
      has_user_message=lambda m:any(x.get('role')=='user' for x in m),
      active_response_target=lambda m:next(({'content':x['content'],'history_index':i} for i,x in reversed(list(enumerate(m))) if x.get('role')=='user'),None),
      merged_secondary_system_prompt=lambda m:'',
      LOG=SimpleNamespace(info=lambda *a:None),
      __file__=str(Path(__file__).resolve().parents[1]/'fake_jack_kernel.py'),
    )


def tool_surface():
    return [{'type':'function','function':{'name':'python_repl','parameters':{'type':'object','properties':{'code':{'type':'string'}}}}}]


async def two_turns(preserve):
    kernel=FakeKernel()
    driver.install_deep_reasoning(kernel,namespace(preserve))
    async def run_turn(history):
        first=await kernel._prepare_commit({'messages':history,'tools':tool_surface()})
        assert first.finish_reason=='tool_calls'
        callid=first.tool_calls[0]['id']
        state=kernel._pending_tool_resumes[callid]
        final=await kernel._resume_tool_stage_nonstream(state,[{'role':'tool','tool_call_id':callid,'content':'17'}])
        assert final.content=='A3_CURRENT'
        return final
    f=await run_turn([{'role':'user','content':'bracelet'}])
    assert f.reasoning_content=='R3_PRIVATE'
    before=len(kernel.calls)
    await run_turn([{'role':'user','content':'bracelet'}, {'role':'assistant','content':f.content},{'role':'user','content':'followup'}])
    new=kernel.calls[before:]
    thesis,anti,syn=new[0],new[1],new[-1]
    assert thesis[0]=='deep_reasoning_thesis'
    if preserve:
        assert thesis[3] is True
        assert 'R3_PRIVATE' in repr(thesis[1])
    else:
        assert thesis[3] is False
        assert 'R3_PRIVATE' not in repr(thesis[1])
    assert 'R3_PRIVATE' not in repr(anti[1])
    assert 'R1_CURRENT' not in repr(anti[1])
    assert 'R3_PRIVATE' not in repr(syn[1])
    assert 'R2_CURRENT' not in repr(syn[1])


def test_real_driver_two_turn_bridge_on():asyncio.run(two_turns(True))
def test_real_driver_two_turn_bridge_off():asyncio.run(two_turns(False))
