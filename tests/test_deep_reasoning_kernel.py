"""Mocked Kernel-facing wiring tests; not a live LM Studio test."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from dataclasses import dataclass

import pytest

from jack_deep_reasoning_kernel import install_deep_reasoning


class FakeHTTPException(Exception):
    def __init__(self, *, status_code, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


@dataclass
class FakeResult:
    content: str | None
    tool_calls: object
    finish_reason: str
    usage: dict
    reasoning_content: str | None


class FakeKernel:
    def __init__(self, script=None):
        self.script = script
        self.calls = []
        self._pending_tool_resumes = {}
        self._pending_tool_resume_lock = asyncio.Lock()
        self.deleted = []

    async def _prepare_commit(self, request_body):
        raise RuntimeError('legacy path should not run')

    async def _resume_tool_stage_nonstream(self, state, tool_messages):
        raise RuntimeError('legacy resume should not run')

    async def _run_stage(self, messages, secondary_system, stage_key, usage, *, tools, tool_choice, append):
        self.calls.append((stage_key, messages, tool_choice, tools))
        usage['prompt_tokens'] += 3
        usage['completion_tokens'] += 7
        usage['total_tokens'] += 10
        if stage_key == 'deep_reasoning_thesis':
            msg = {'content':'Thesis: Part B=15','reasoning_content':'SECRET_R1'}
        elif stage_key == 'deep_reasoning_antithesis':
            if not any(m['role'] == 'tool' for m in messages):
                msg = {'tool_calls':[{'id':'call-7', 'type':'function', 'function':{'name':'python_repl','arguments':json.dumps({'code':'print(17)'})}}], 'reasoning_content':'SECRET_R2'}
            else:
                msg = {'content':'Antithesis: Part B=17 verified', 'reasoning_content':'SECRET_R2'}
        elif stage_key == 'deep_reasoning_synthesis':
            msg = {'content':'Synthesis: Part B=17', 'reasoning_content':'ONLY_R3'}
        else:
            raise AssertionError(stage_key)
        return {'choices':[{'message':msg}]}

    async def _register_stage_tool_resume(self, *, stage_key, history, secondary_system, usage, tools, tool_choice, data):
        calls = data['choices'][0]['message']['tool_calls']
        state = SimpleNamespace(resume_id='resume-7', stage_key=stage_key, expected_tool_call_ids=tuple(c['id'] for c in calls))
        for call in calls:
            self._pending_tool_resumes[call['id']] = state
        return FakeResult(None, calls, 'tool_calls', usage.copy(), None)

    async def _retire_pending_tool_resume(self, state):
        self.deleted.append(state.resume_id)
        for key in list(self._pending_tool_resumes):
            if self._pending_tool_resumes[key] is state:
                del self._pending_tool_resumes[key]


def ns():
    return SimpleNamespace(
        DEEP_REASONING_MODE=True,
        HTTPException=FakeHTTPException,
        KernelResult=FakeResult,
        normalize_usage=lambda x: dict(x),
        has_user_message=lambda msgs:any(m.get('role')=='user' for m in msgs),
        active_response_target=lambda msgs:next(({'content':m['content'], 'history_index':i} for i,m in reversed(list(enumerate(msgs))) if m.get('role')=='user'),None),
        merged_secondary_system_prompt=lambda msgs:'caller-system',
        __file__=str(Path(__file__).resolve().parents[1]/'fake_jack_kernel.py'),
    )


def tools():
    return [{'type':'function','function':{'name':'python_repl','parameters':{'type':'object','properties':{'code':{'type':'string'}}}}}]


def test_full_nonstream_toolfirst_and_isolation():
    asyncio.run(_test_full_nonstream_toolfirst_and_isolation_async())


async def _test_full_nonstream_toolfirst_and_isolation_async():
    kernel = FakeKernel()
    install_deep_reasoning(kernel,ns())
    result = await kernel._prepare_commit({'messages':[{'role':'user','content':'Solve circle'}], 'tools':tools()})
    assert result.finish_reason == 'tool_calls'
    assert result.tool_calls[0]['function']['name'] == 'python_repl'
    assert kernel.calls[1][2] == 'required'
    assert [t['function']['name'] for t in kernel.calls[1][3]] == ['python_repl']
    assert 'SECRET_R1' not in repr(kernel.calls[1][1])
    active=kernel._pending_tool_resumes['call-7']
    result=await kernel._resume_tool_stage_nonstream(active,[{'tool_call_id':'call-7','content':'17'}])
    assert result.content == 'Synthesis: Part B=17'
    assert result.reasoning_content == 'ONLY_R3'
    assert 'SECRET_R1' not in repr(kernel.calls[2][1])
    assert 'SECRET_R2' not in repr(kernel.calls[2][1])
    assert 'call-7' in repr(kernel.calls[2][1])
    assert '17' in repr(kernel.calls[2][1])
    assert kernel.deleted == ['resume-7']


def test_missing_tools_allows_unverified_reasoning():
    async def run():
        class NoToolFakeKernel(FakeKernel):
            async def _run_stage(self, messages, secondary_system, stage_key, usage, *, tools, tool_choice, append, same_stage_resume=False):
                if stage_key == "deep_reasoning_antithesis":
                    self.calls.append((stage_key, messages, tool_choice, tools))
                    return {"choices": [{"message": {"content": "UNVERIFIED - no tool supplied"}}]}
                return await super()._run_stage(messages, secondary_system, stage_key, usage,
                                                tools=tools, tool_choice=tool_choice, append=append)
        kernel = NoToolFakeKernel()
        install_deep_reasoning(kernel, ns())
        response = await kernel._prepare_commit({"messages": [{"role": "user", "content": "Subjective question"}]})
        assert response.finish_reason == "stop"
        assert kernel.calls[1][2] == "auto"
        assert response.content == "Synthesis: Part B=17"
    asyncio.run(run())


def test_resume_unknown_fails_closed():
    asyncio.run(_test_resume_unknown_fails_closed_async())


async def _test_resume_unknown_fails_closed_async():
    kernel=FakeKernel()
    install_deep_reasoning(kernel,ns())
    with pytest.raises(FakeHTTPException) as e:
        await kernel._resume_tool_stage_nonstream(SimpleNamespace(stage_key='deep_reasoning_antithesis',resume_id='unknown'), [])
    assert e.value.status_code==409


def test_installed_kernel_dispatch_compiles_and_is_gated():
    import ast
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "jack_kernel.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert 'DEEP_REASONING_MODE = ACTIVE_REASONING_PROFILE["mode"] == "deep_reasoning"' in source
    assert 'if DEEP_REASONING_MODE:' in source
    assert 'install_deep_reasoning(KERNEL, _dr_sys.modules[__name__])' in source
    assert 'allowed_tool_stages = {"deep_reasoning_antithesis", "deep_reasoning_synthesis", "deep_reasoning_thesis"}' in source


def test_kernel_preserves_historical_user_constraints_in_each_stage():
    async def run():
        kernel = FakeKernel()
        install_deep_reasoning(kernel, ns())
        previous = [
            {"role": "user", "content": "No external dependencies"},
            {"role": "assistant", "content": "Acknowledged", "reasoning_content": "OLD_THINKING_SECRET"},
            {"role": "user", "content": "Keep the filename unchanged"},
            {"role": "assistant", "content": "Will comply"},
            {"role": "user", "content": "Improve alignment"},
        ]
        response = await kernel._prepare_commit({"messages": previous, "tools": tools()})
        assert response.finish_reason == "tool_calls"
        state = kernel._pending_tool_resumes['call-7']
        completed = await kernel._resume_tool_stage_nonstream(state,[{'tool_call_id':'call-7','content':'17'}])
        assert completed.content == 'Synthesis: Part B=17'
        for stage_key, messages, _choice, _tools in kernel.calls:
            assert [m['content'] for m in messages[:5]] == [
                "No external dependencies", "Acknowledged",
                "Keep the filename unchanged", "Will comply", "Improve alignment",
            ]
            assert "OLD_THINKING_SECRET" not in repr(messages)
            if stage_key == 'deep_reasoning_synthesis':
                assert "SECRET_R1" not in repr(messages)
                assert "SECRET_R2" not in repr(messages)
    asyncio.run(run())
