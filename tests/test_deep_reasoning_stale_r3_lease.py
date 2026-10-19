"""R3 one-hop recovery when host tool checkpoint expires or registration fails.

Uses an inert backend and faked Jack checkpoint registry. It does not call LM
Studio or execute tools. The experiment's prompts/context are never changed.
"""
from __future__ import annotations

import asyncio
import pytest

from jack_deep_reasoning_kernel import install_deep_reasoning
from test_deep_reasoning_r3_bridge import FakeKernel, namespace, tool_surface


class ThesisToolKernel(FakeKernel):
    def __init__(self):
        super().__init__()
        self.interrupt_registration = False

    async def _run_stage(self, messages, secondary_system, stage_key, usage, *,
                         tools, tool_choice, append, same_stage_resume=False):
        if (stage_key == 'deep_reasoning_thesis'
                and any(m.get('reasoning_content') == 'R3_PRIVATE' for m in messages)
                and not any(m.get('role') == 'tool' for m in messages)):
            self.calls.append((stage_key, messages, tool_choice, same_stage_resume))
            self.serial += 1
            return {'choices': [{'message': {
                'tool_calls': [{'id': f'thesis-check-{self.serial}', 'type': 'function',
                                'function': {'name': 'python_repl', 'arguments': '{"code":"print(1)"}'}}]
            }}]}
        return await super()._run_stage(
            messages, secondary_system, stage_key, usage, tools=tools,
            tool_choice=tool_choice, append=append, same_stage_resume=same_stage_resume,
        )

    async def _register_stage_tool_resume(self, **kw):
        if self.interrupt_registration and kw['stage_key'] == 'deep_reasoning_thesis':
            raise OSError('simulated checkpoint registration interruption')
        return await super()._register_stage_tool_resume(**kw)


async def run_turn_one(kernel):
    first = await kernel._prepare_commit({
        'messages': [{'role': 'user', 'content': 'turn one'}], 'tools': tool_surface(),
    })
    assert first.finish_reason == 'tool_calls'
    call_id = first.tool_calls[0]['id']
    result = await kernel._resume_tool_stage_nonstream(
        kernel._pending_tool_resumes[call_id],
        [{'role':'tool', 'tool_call_id': call_id, 'content': '17'}],
    )
    assert result.content == 'A3_CURRENT'
    return result


def followup(prior):
    return {'messages': [
        {'role':'user', 'content':'turn one'},
        {'role':'assistant', 'content':prior.content},
        {'role':'user', 'content':'turn two'},
    ], 'tools': tool_surface()}


def test_expired_checkpoint_releases_r3_lease_for_retry():
    async def run():
        kernel = ThesisToolKernel()
        install_deep_reasoning(kernel, namespace(True))
        prior = await run_turn_one(kernel)
        body = followup(prior)
        pending = await kernel._prepare_commit(body)
        assert pending.finish_reason == 'tool_calls'
        assert pending.tool_calls[0]['id'].startswith('thesis-check-')

        # Simulate existing Jack ownership expiration: checkpoint removed.
        kernel._pending_tool_resumes.clear()
        mark = len(kernel.calls)
        retry = await kernel._prepare_commit(body)
        assert retry.finish_reason == 'tool_calls', 'prior R3 must remain retryable'
        assert 'R3_PRIVATE' in repr(kernel.calls[mark][1])
    asyncio.run(run())


def test_failed_checkpoint_registration_does_not_strand_r3_lease():
    async def run():
        kernel = ThesisToolKernel()
        install_deep_reasoning(kernel, namespace(True))
        prior = await run_turn_one(kernel)
        body = followup(prior)
        kernel.interrupt_registration = True
        with pytest.raises(OSError, match='registration interruption'):
            await kernel._prepare_commit(body)
        kernel.interrupt_registration = False
        mark = len(kernel.calls)
        again = await kernel._prepare_commit(body)
        assert again.finish_reason == 'tool_calls'
        assert 'R3_PRIVATE' in repr(kernel.calls[mark][1])
    asyncio.run(run())


def test_truncated_thesis_does_not_retire_previous_r3():
    class TruncatedThesisKernel(FakeKernel):
        def __init__(self):
            super().__init__()
            self.truncate_once = True

        async def _run_stage(self, messages, secondary_system, stage_key, usage, *,
                             tools, tool_choice, append, same_stage_resume=False):
            if (stage_key == 'deep_reasoning_thesis' and self.truncate_once
                    and any(m.get('reasoning_content') == 'R3_PRIVATE' for m in messages)):
                self.truncate_once = False
                self.calls.append((stage_key, messages, tool_choice, same_stage_resume))
                return {'choices': [{'message': {'content': 'PARTIAL_THESIS'},
                                     'finish_reason': 'length'}]}
            return await super()._run_stage(
                messages, secondary_system, stage_key, usage, tools=tools,
                tool_choice=tool_choice, append=append, same_stage_resume=same_stage_resume,
            )

    async def run():
        kernel = TruncatedThesisKernel()
        install_deep_reasoning(kernel, namespace(True))
        prior = await run_turn_one(kernel)
        body = followup(prior)
        with pytest.raises(Exception) as err:
            await kernel._prepare_commit(body)
        assert 'truncated' in str(getattr(err.value, 'detail', err.value))
        mark = len(kernel.calls)
        result = await kernel._prepare_commit(body)
        assert result.finish_reason == 'tool_calls'
        assert 'R3_PRIVATE' in repr(kernel.calls[mark][1])
        # The completed receiving Thesis, not the interrupted one, consumes it.
        assert 'R3_PRIVATE' not in repr(kernel.calls[mark + 1][1])
    asyncio.run(run())
