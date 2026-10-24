"""Cognition-neutral terminal cleanup: release only completed session buffers."""

import asyncio
from jack_deep_reasoning_context import CompletedSynthesis
from jack_deep_reasoning_orchestrator import (
    CompletedAnswer, DeepReasoningOrchestrator, PendingToolRequest,
)


def test_tas_terminal_cleanup_keeps_completed_result_and_caller_request():
    asyncio.run(_test_tas_terminal_cleanup_keeps_completed_result_and_caller_request_async())


async def _test_tas_terminal_cleanup_keeps_completed_result_and_caller_request_async():
    seen = []
    def call(stage):
        return {'id': stage + '-call', 'type': 'function',
                'function': {'name': 'python_repl', 'arguments': '{"code":"print(5050)"}'}}
    counter = {}
    async def backend(**kwargs):
        seen.append(kwargs)
        stage = kwargs['stage']
        count = counter.get(stage, 0)
        counter[stage] = count + 1
        if count == 0:
            return {'content': '', 'tool_calls': [call(stage)], 'reasoning_content': 'R ' + stage}
        return {'content': stage + ' response', 'reasoning_content': 'R ' + stage}

    prompts = {x: x for x in (
        'ULTRA_STAGE1_THESIS_PROMPT', 'ULTRA_STAGE2_ANTITHESIS_PROMPT',
        'ULTRA_STAGE3_SYNTHESIS_PROMPT'
    )}
    t = {'type': 'function', 'function': {'name': 'python_repl', 'parameters': {}}}
    orch = DeepReasoningOrchestrator(backend, prompts=prompts, tools=[t],
                                    preserve_stage_tool_reasoning=True)
    pair = [
        {'role': 'user', 'content': 'prior question'},
        {'role': 'assistant', 'content': 'prior answer'},
    ]
    v = await orch.start(request='current request', visible_history=pair,
                         prior_synthesis=CompletedSynthesis('prior question', 'prior answer', 'R3'),
                         preserve_thinking=True, require_verification=True)
    n = 0
    session = None
    while isinstance(v, PendingToolRequest):
        n += 1
        assert n <= 3
        session = v.session
        v = await orch.resume(v, results=[{'tool_call_id': v.calls[0]['id'], 'content': 'evidence 5050'}])
    assert isinstance(v, CompletedAnswer)
    assert v.answer == 'synthesis response'
    assert v.synthesis_native_reasoning == 'R synthesis'
    assert v.thesis_answer == 'thesis response'
    assert v.antithesis_findings == 'antithesis response'
    assert len(v.evidence) == 3
    assert session is not None and session.closed
    # Still read by the wrapper _finish() on the completed resumed transaction.
    assert session.request == 'current request'
    assert session.messages == []
    assert session.conversation_history == ()
    assert session.evidence == []
    assert session.artifact_references == []
    assert len(seen) == 6
    assert any(m.get('reasoning_content') == 'R3' for m in seen[0]['messages'])
    assert all('R3' not in str(x['messages']) for x in seen[2:])


def test_terminal_cleanup_preserves_a3_r3_for_next_authorized_thesis():
    asyncio.run(_test_terminal_cleanup_preserves_a3_r3_for_next_authorized_thesis_async())


async def _test_terminal_cleanup_preserves_a3_r3_for_next_authorized_thesis_async():
    """Host bridge survives completed-session cleanup, including a tool resume.

    This is a deterministic kernel protocol test, not a language-model quality
    test. The first turn has tool continuations to exercise the cleanup path.
    """
    import copy
    from jack_deep_reasoning_bridge import OneHopSynthesisBridge

    owner = 'ab' * 32
    other_owner = 'cd' * 32
    bridge = OneHopSynthesisBridge(require_owner=True)
    prompts = {x: x for x in (
        'ULTRA_STAGE1_THESIS_PROMPT', 'ULTRA_STAGE2_ANTITHESIS_PROMPT',
        'ULTRA_STAGE3_SYNTHESIS_PROMPT'
    )}
    tool = {'type': 'function', 'function': {
        'name': 'python_repl', 'parameters': {}}}
    first_seen = []
    first_counts = {}

    async def first_backend(**kwargs):
        first_seen.append(copy.deepcopy(kwargs))
        stage = kwargs['stage']
        round_num = first_counts.get(stage, 0)
        first_counts[stage] = round_num + 1
        if round_num == 0:
            return {'content': '', 'reasoning_content': 'TOOL ' + stage,
                    'tool_calls': [{'id': stage + '-first', 'type': 'function',
                                    'function': {'name': 'python_repl',
                                                 'arguments': '{"code":"print(5050)"}'}}]}
        return {'content': 'A ' + stage, 'reasoning_content': 'NATIVE ' + stage}

    first = DeepReasoningOrchestrator(first_backend, prompts=prompts, tools=[tool],
                                     preserve_stage_tool_reasoning=True)
    completed = await first.start(request='FIRST REQUEST', require_verification=True)
    old_session = None
    while isinstance(completed, PendingToolRequest):
        old_session = completed.session
        completed = await first.resume(completed, results=[{
            'tool_call_id': completed.calls[0]['id'], 'content': '5050'}])
    assert isinstance(completed, CompletedAnswer)
    assert old_session is not None and old_session.closed
    assert old_session.messages == []
    assert old_session.evidence == []
    assert completed.answer == 'A synthesis'
    assert completed.synthesis_native_reasoning == 'NATIVE synthesis'

    # The driver publishes from CompletedAnswer, never from cleared session.
    assert bridge.publish(user_request='FIRST REQUEST', answer=completed.answer,
                          reasoning=completed.synthesis_native_reasoning,
                          owner_key=owner)
    history = [{'role': 'user', 'content': 'FIRST REQUEST'},
               {'role': 'assistant', 'content': completed.answer}]
    _, unauthorized, unauthorized_lease = bridge.reserve(history, owner_key=other_owner)
    assert unauthorized is None and unauthorized_lease is None

    _, prior, lease = bridge.reserve(history, owner_key=owner)
    assert prior is not None and lease
    assert prior.answer == completed.answer
    assert prior.reasoning == completed.synthesis_native_reasoning

    next_seen = []

    async def next_backend(**kwargs):
        next_seen.append(copy.deepcopy(kwargs))
        return {'content': 'NEXT ' + kwargs['stage'],
                'reasoning_content': 'NEW ' + kwargs['stage']}

    nxt = DeepReasoningOrchestrator(next_backend, prompts=prompts, tools=[tool])
    second = await nxt.start(request='SECOND REQUEST', visible_history=history,
                             prior_synthesis=prior, preserve_thinking=True,
                             require_verification=False)
    assert isinstance(second, CompletedAnswer)
    assert [call['stage'] for call in next_seen] == ['thesis', 'antithesis', 'synthesis']
    thesis_messages = next_seen[0]['messages']
    matching = [m for m in thesis_messages
                if m.get('role') == 'assistant' and m.get('content') == completed.answer]
    assert len(matching) == 1
    assert matching[0].get('reasoning_content') == completed.synthesis_native_reasoning
    for call in next_seen[1:]:
        assert not any(m.get('reasoning_content') == completed.synthesis_native_reasoning
                       for m in call['messages'])
        assert {'role': 'assistant', 'content': completed.answer} in call['messages']
    assert bridge.retire(lease)
    _, spent, spent_lease = bridge.reserve(history, owner_key=owner)
    assert spent is None and spent_lease is None
