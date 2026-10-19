"""One-hop TAS R3 lifecycle: lease, rollback, consumption, evaluator isolation.

No live model and no arbitrary tool code execution. FakeKernel returns controlled
model output; these tests prove the host's protocol and context projections.
"""
from __future__ import annotations

import asyncio
import pytest

from jack_deep_reasoning_bridge import OneHopSynthesisBridge
from jack_deep_reasoning_kernel import install_deep_reasoning
from test_deep_reasoning_r3_bridge import FakeKernel, namespace, tool_surface


def hist(user='prior task', answer='prior final'):
    return [{'role': 'user', 'content': user}, {'role': 'assistant', 'content': answer}]


def test_lease_not_consumed_until_explicit_retirement():
    bridge = OneHopSynthesisBridge()
    assert bridge.publish(user_request='prior task', answer='prior final', reasoning='R3_ONLY')
    visible, completed, token = bridge.reserve(hist())
    assert visible == []
    assert completed.reasoning == 'R3_ONLY'
    assert token
    # Competing request cannot borrow the same host-owned native trace.
    _, duplicate, duplicate_token = bridge.reserve(hist())
    assert duplicate is None and duplicate_token is None
    bridge.release(token)
    _, retry, new_token = bridge.reserve(hist())
    assert retry.reasoning == 'R3_ONLY' and new_token == token
    assert bridge.retire(new_token)
    assert not bridge.retire(new_token)
    assert bridge.claim(hist())[1] is None


def test_lease_expiry_does_not_enable_replay():
    bridge = OneHopSynthesisBridge(ttl_seconds=1)
    bridge.publish(user_request='prior task', answer='prior final', reasoning='R3_ONLY')
    _, _, token = bridge.reserve(hist())
    # Simulate aging without sleeping.
    from dataclasses import replace
    bridge._frontiers[0] = replace(bridge._frontiers[0], created=bridge._frontiers[0].created - 30)
    assert not bridge.retire(token)
    bridge.release(token)
    assert bridge.reserve(hist())[1] is None


class FailOnceKernel(FakeKernel):
    def __init__(self, fail_stage: str):
        super().__init__()
        self.fail_stage = fail_stage
        self.failed = False

    async def _run_stage(self, messages, secondary_system, stage_key, usage, *, tools, tool_choice, append, same_stage_resume=False):
        if self.fail_stage == stage_key and not self.failed and any(m.get('reasoning_content') == 'R3_PRIVATE' for m in messages):
            self.failed = True
            raise ConnectionError('simulated LM Studio interruption during bridged Thesis')
        if self.fail_stage == 'deep_reasoning_antithesis' and stage_key == self.fail_stage and not self.failed and self.turn1_complete:
            self.failed = True
            raise ConnectionError('simulated LM Studio interruption after completed Thesis')
        return await super()._run_stage(messages, secondary_system, stage_key, usage,
                                        tools=tools, tool_choice=tool_choice, append=append,
                                        same_stage_resume=same_stage_resume)


async def run_turn(kernel, conversation):
    first = await kernel._prepare_commit({'messages': conversation, 'tools': tool_surface()})
    assert first.finish_reason == 'tool_calls'
    call_id = first.tool_calls[0]['id']
    final = await kernel._resume_tool_stage_nonstream(kernel._pending_tool_resumes[call_id],
                                                     [{'role': 'tool', 'tool_call_id': call_id, 'content': '17'}])
    assert final.content == 'A3_CURRENT'
    return final


def test_failed_next_thesis_leaves_prior_r3_retryable():
    async def run():
        kernel = FailOnceKernel('deep_reasoning_thesis')
        kernel.turn1_complete = False
        install_deep_reasoning(kernel, namespace(True))
        prior = await run_turn(kernel, [{'role': 'user', 'content': 'turn one'}])
        kernel.turn1_complete = True
        second = hist('turn one', prior.content) + [{'role': 'user', 'content': 'turn two'}]
        with pytest.raises(ConnectionError, match='simulated'):
            await kernel._prepare_commit({'messages': second, 'tools': tool_surface()})
        start = len(kernel.calls)
        await run_turn(kernel, second)
        new = kernel.calls[start:]
        assert 'R3_PRIVATE' in repr(new[0][1]), 'R3 must survive failed Thesis'
        assert 'R3_PRIVATE' not in repr(new[1][1]), 'Antithesis must remain independent'
        assert 'R3_PRIVATE' not in repr(new[-1][1]), 'Synthesis must remain independent'
    asyncio.run(run())


def test_completed_next_thesis_consumes_prior_r3_even_if_antithesis_fails():
    async def run():
        kernel = FailOnceKernel('deep_reasoning_antithesis')
        kernel.turn1_complete = False
        install_deep_reasoning(kernel, namespace(True))
        prior = await run_turn(kernel, [{'role': 'user', 'content': 'turn one'}])
        kernel.turn1_complete = True
        second = hist('turn one', prior.content) + [{'role': 'user', 'content': 'turn two'}]
        with pytest.raises(ConnectionError, match='after completed Thesis'):
            await kernel._prepare_commit({'messages': second, 'tools': tool_surface()})
        start = len(kernel.calls)
        await run_turn(kernel, second)
        new = kernel.calls[start:]
        assert 'R3_PRIVATE' not in repr(new[0][1]), 'Previous R3 must be single-use after successful Thesis'
    asyncio.run(run())
