"""Regression for Pi content-part history and owner-bound one-hop R3.

Exercises real Jack active_response_target normalization with a mocked TAS model.
No live backend or external tools.
"""
from __future__ import annotations

import asyncio

import jack_kernel as jk
from jack_deep_reasoning_kernel import install_deep_reasoning
from jack_tas_r3_owner import reset_current_owner, set_current_owner
from test_deep_reasoning_r3_bridge import FakeKernel, namespace, tool_surface


OWNER_A = 'a' * 64
OWNER_B = 'b' * 64


def text_parts(value):
    return [{'type': 'text', 'text': value}]


async def complete_turn(kernel, conversation):
    first = await kernel._prepare_commit({'messages': conversation, 'tools': tool_surface()})
    assert first.finish_reason == 'tool_calls'
    call_id = first.tool_calls[0]['id']
    state = kernel._pending_tool_resumes[call_id]
    result = await kernel._resume_tool_stage_nonstream(
        state,
        [{'role': 'tool', 'tool_call_id': call_id, 'content': '17'}],
    )
    assert result.content == 'A3_CURRENT'
    return result


def test_pi_structured_user_history_restored_for_one_hop_r3(monkeypatch):
    monkeypatch.setenv('JACK_TAS_R3_OWNER_ENFORCEMENT', '1')
    kernel = FakeKernel()
    ns = namespace(True)
    ns.active_response_target = jk.active_response_target
    install_deep_reasoning(kernel, ns)
    first_user = {'role': 'user', 'content': text_parts('calculate 1 to 100')}
    next_user = {'role': 'user', 'content': text_parts('explain verification')}

    async def run():
        lease = set_current_owner(OWNER_A)
        try:
            first = await complete_turn(kernel, [first_user])
            assert first.reasoning_content == 'R3_PRIVATE'
            before = len(kernel.calls)
            await complete_turn(kernel, [first_user, {'role': 'assistant', 'content': first.content}, next_user])
        finally:
            reset_current_owner(lease)
        calls = kernel.calls[before:]
        thesis, antithesis, synthesis = calls[0], calls[1], calls[-1]
        canonical_user = jk._content_to_text(first_user['content'])
        assert canonical_user in repr(thesis[1])
        assert 'R3_PRIVATE' in repr(thesis[1]), 'Only the authorized next Thesis may receive R3'
        assert canonical_user in repr(antithesis[1])
        assert canonical_user in repr(synthesis[1])
        # The preceding committed answer and original user request must remain
        # in both evaluator contexts even when Thesis consumes the R3 lease.
        assert first.content in repr(antithesis[1])
        assert first.content in repr(synthesis[1])
        thesis_msgs = thesis[1]
        assert sum(m.get('role') == 'user' and m.get('content') == canonical_user
                   for m in thesis_msgs) == 1, 'Prior user must not be duplicated'
        for later in (antithesis, synthesis):
            assert 'R3_PRIVATE' not in repr(later[1])
        assert 'R1_CURRENT' not in repr(antithesis[1])
        assert 'R2_CURRENT' not in repr(synthesis[1])
    asyncio.run(run())


def test_identical_pi_structured_text_cannot_cross_session(monkeypatch):
    monkeypatch.setenv('JACK_TAS_R3_OWNER_ENFORCEMENT', '1')
    kernel = FakeKernel()
    ns = namespace(True)
    ns.active_response_target = jk.active_response_target
    install_deep_reasoning(kernel, ns)
    first_user = {'role': 'user', 'content': text_parts('same question')}
    next_user = {'role': 'user', 'content': text_parts('same follow-up')}

    async def run():
        lease = set_current_owner(OWNER_A)
        try:
            first = await complete_turn(kernel, [first_user])
        finally:
            reset_current_owner(lease)
        dialogue = [first_user, {'role': 'assistant', 'content': first.content}, next_user]
        before = len(kernel.calls)
        lease = set_current_owner(OWNER_B)
        try:
            await complete_turn(kernel, dialogue)
        finally:
            reset_current_owner(lease)
        assert 'R3_PRIVATE' not in repr(kernel.calls[before][1]), 'Owner B cannot borrow owner A R3'
        # Owner B's identical completion may now also be published. The original
        # owner must still be able to select its own matching record unambiguously.
        before = len(kernel.calls)
        lease = set_current_owner(OWNER_A)
        try:
            await complete_turn(kernel, dialogue)
        finally:
            reset_current_owner(lease)
        assert 'R3_PRIVATE' in repr(kernel.calls[before][1]), 'Owner A should retain its own R3'
    asyncio.run(run())
