"""Regression: stale tool checkpoints must not hijack a later Pi user prompt."""
import asyncio
from pathlib import Path
from types import SimpleNamespace

from jack_deep_reasoning_kernel import install_deep_reasoning

class FakeKernel:
    def __init__(self):
        self.seen = []
        self._prepare_commit = self._unused
        self._resume_tool_stage_nonstream = self._unused
        self._consume_pending_tool_resume = self.consume

    async def _unused(self, *args, **kwargs):
        raise AssertionError('unused')

    async def consume(self, messages):
        self.seen.append(messages)
        for msg in messages:
            if msg.get('role') == 'tool' and msg.get('tool_call_id') == 'old-pin-tool':
                return 'STALE_PIN_RESUMPTION'
        for msg in messages:
            if msg.get('role') == 'tool' and msg.get('tool_call_id') == 'new-triples-tool':
                return 'CORRECT_TRIPLES_RESUMPTION'
        return None


def install():
    k = FakeKernel()
    ns = SimpleNamespace(
        DEEP_REASONING_MODE=True,
        HTTPException=Exception,
        KernelResult=object,
        __file__=str(Path(__file__).resolve().parents[1] / 'jack_kernel.py'),
        CFG=SimpleNamespace(preserve_thinking=True),
        active_response_target=lambda msgs:next(
            ({'history_index':i,'content':m['content']}
             for i,m in reversed(list(enumerate(msgs))) if m.get('role') == 'user'), None
        ),
    )
    install_deep_reasoning(k,ns)
    return k


def test_old_tool_result_does_not_resume_failed_prior_user_turn():
    async def scenario():
        k = install()
        replay = [
            {'role':'user','content':'Count six-digit PINs summing to 9'},
            {'role':'assistant','tool_calls':[{'id':'old-pin-tool'}]},
            {'role':'tool','tool_call_id':'old-pin-tool','content':'2002'},
            {'role':'assistant','content':'[Jack Kernel internal stage failure]'},
            {'role':'user','content':'Count ordered triples summing to 30'},
        ]
        assert await k._consume_pending_tool_resume(replay) is None
        assert k.seen[-1][0]['content'] == 'Count ordered triples summing to 30'
        assert not any(m.get('tool_call_id') == 'old-pin-tool' for m in k.seen[-1])
    asyncio.run(scenario())


def test_current_turn_tool_result_still_resumes():
    async def scenario():
        k = install()
        replay = [
            {'role':'user','content':'PIN problem'},
            {'role':'tool','tool_call_id':'old-pin-tool','content':'2002'},
            {'role':'assistant','content':'Old final answer'},
            {'role':'user','content':'Count ordered triples summing to 30'},
            {'role':'assistant','tool_calls':[{'id':'new-triples-tool'}]},
            {'role':'tool','tool_call_id':'new-triples-tool','content':'496'},
        ]
        assert await k._consume_pending_tool_resume(replay) == 'CORRECT_TRIPLES_RESUMPTION'
        assert k.seen[-1][0]['content'] == 'Count ordered triples summing to 30'
    asyncio.run(scenario())


def test_retry_same_turn_after_backend_failure_remains_allowed():
    async def scenario():
        k = install()
        replay = [
            {'role':'user','content':'PIN problem'},
            {'role':'assistant','tool_calls':[{'id':'old-pin-tool'}]},
            {'role':'tool','tool_call_id':'old-pin-tool','content':'2002'},
        ]
        assert await k._consume_pending_tool_resume(replay) == 'STALE_PIN_RESUMPTION'
    asyncio.run(scenario())
