"""Local-only opt-in TAS R3 session binding tests (no live model)."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import pytest

from jack_deep_reasoning_bridge import OneHopSynthesisBridge
from jack_tas_r3_owner import (
    current_owner, parse_session_capability, reset_current_owner, set_current_owner,
)

A = 'a' * 64
B = 'b' * 64


def history():
    return [{'role': 'user', 'content': 'same request'},
            {'role': 'assistant', 'content': 'same answer'}]


def test_strict_r3_needs_matching_private_owner_even_if_text_matches():
    bridge = OneHopSynthesisBridge(require_owner=True)
    assert bridge.publish(user_request='same request', answer='same answer',
                          reasoning='PRIVATE_A', owner_key=A)
    assert bridge.reserve(history(), owner_key=None)[1:] == (None, None)
    assert bridge.reserve(history(), owner_key=B)[1:] == (None, None)
    visible, record, token = bridge.reserve(history(), owner_key=A)
    assert visible == [] and record.reasoning == 'PRIVATE_A'
    assert token and bridge.retire(token)
    assert bridge.reserve(history(), owner_key=A)[1:] == (None, None)


def test_identical_text_two_sessions_select_only_their_own_r3():
    bridge = OneHopSynthesisBridge(require_owner=True)
    bridge.publish(user_request='same request', answer='same answer',
                   reasoning='PRIVATE_A', owner_key=A)
    bridge.publish(user_request='same request', answer='same answer',
                   reasoning='PRIVATE_B', owner_key=B)
    _, ra, ta = bridge.reserve(history(), owner_key=A)
    _, rb, tb = bridge.reserve(history(), owner_key=B)
    assert ra.reasoning == 'PRIVATE_A' and rb.reasoning == 'PRIVATE_B'
    assert ta != tb
    assert bridge.retire(ta) and bridge.retire(tb)


def test_strict_missing_owner_does_not_create_r3_frontier():
    bridge = OneHopSynthesisBridge(require_owner=True)
    assert bridge.publish(user_request='same request', answer='same answer',
                          reasoning='PRIVATE', owner_key=None) is False
    assert bridge.reserve(history(), owner_key=A)[1:] == (None, None)


def test_same_session_failed_thesis_lease_can_retry_then_retire():
    bridge = OneHopSynthesisBridge(require_owner=True)
    bridge.publish(user_request='same request', answer='same answer',
                   reasoning='PRIVATE_A', owner_key=A)
    _, record, token = bridge.reserve(history(), owner_key=A)
    assert record.reasoning == 'PRIVATE_A'
    assert bridge.reserve(history(), owner_key=A)[1:] == (None, None)
    bridge.release(token)
    _, retry, retry_token = bridge.reserve(history(), owner_key=A)
    assert retry.reasoning == 'PRIVATE_A' and retry_token == token
    assert bridge.retire(token)


def test_strict_lease_expires_closed():
    bridge = OneHopSynthesisBridge(require_owner=True, ttl_seconds=1)
    bridge.publish(user_request='same request', answer='same answer',
                   reasoning='PRIVATE_A', owner_key=A)
    bridge._frontiers[0] = replace(bridge._frontiers[0], created=bridge._frontiers[0].created - 30)
    assert bridge.reserve(history(), owner_key=A)[1:] == (None, None)


def test_invalid_transport_capabilities_fail_closed_and_are_never_logged():
    assert parse_session_capability({}) is None
    assert parse_session_capability({'x-jack-tas-session-capability': A.upper()}) == A
    for bad in ['x' * 64, 'a' * 63, 'a' * 65, 'session-123', 'a\nb', '']:
        with pytest.raises(ValueError):
            parse_session_capability({'x-jack-tas-session-capability': bad})


def test_async_context_owner_isolated_between_concurrent_tasks():
    async def worker(owner):
        token = set_current_owner(owner)
        try:
            await asyncio.sleep(0)
            assert current_owner() == owner
            return current_owner()
        finally:
            reset_current_owner(token)
    async def run():
        return await asyncio.gather(worker(A), worker(B))
    assert asyncio.run(run()) == [A, B]


def test_pi_extension_constructs_private_capability_and_not_plain_session_id():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / 'Pi' / 'jack-kernel.ts').read_text(encoding='utf-8')
    assert 'crypto.randomBytes(32).toString("hex")' in source
    assert 'X-Jack-TAS-Session-Capability' in source
    assert 'getSessionId' in source


def test_integrated_strict_driver_blocks_cross_session_r3(monkeypatch):
    """The real TAS driver must not pass another session's R3 into Thesis."""
    from jack_deep_reasoning_kernel import install_deep_reasoning
    from test_deep_reasoning_r3_bridge import FakeKernel, namespace, tool_surface
    monkeypatch.setenv('JACK_TAS_R3_OWNER_ENFORCEMENT', '1')
    kernel = FakeKernel()
    install_deep_reasoning(kernel, namespace(True))

    async def turn(messages, owner):
        token = set_current_owner(owner)
        try:
            result = await kernel._prepare_commit({'messages': messages, 'tools': tool_surface()})
            assert result.finish_reason == 'tool_calls'
            callid = result.tool_calls[0]['id']
            pending = kernel._pending_tool_resumes[callid]
            return await kernel._resume_tool_stage_nonstream(
                pending, [{'role': 'tool', 'tool_call_id': callid, 'content': '17'}]
            )
        finally:
            reset_current_owner(token)

    async def check():
        first = await turn([{'role': 'user', 'content': 'same question'}], A)
        prior = [{'role': 'user', 'content': 'same question'},
                 {'role': 'assistant', 'content': first.content},
                 {'role': 'user', 'content': 'follow up'}]
        offset = len(kernel.calls)
        await turn(prior, B)
        b_calls = kernel.calls[offset:]
        assert 'R3_PRIVATE' not in repr(b_calls[0][1])
        offset = len(kernel.calls)
        await turn(prior, A)
        a_calls = kernel.calls[offset:]
        assert 'R3_PRIVATE' in repr(a_calls[0][1])
        assert 'R3_PRIVATE' not in repr(a_calls[1][1])
        assert 'R3_PRIVATE' not in repr(a_calls[-1][1])
    asyncio.run(check())


def test_integrated_strict_driver_rejects_cross_session_tool_resume(monkeypatch):
    """Checkpoint continuation cannot change owners mid-stage."""
    from jack_deep_reasoning_kernel import install_deep_reasoning
    from test_deep_reasoning_r3_bridge import FakeKernel, namespace, tool_surface
    monkeypatch.setenv('JACK_TAS_R3_OWNER_ENFORCEMENT', '1')
    kernel = FakeKernel()
    install_deep_reasoning(kernel, namespace(True))

    async def check():
        token = set_current_owner(A)
        try:
            result = await kernel._prepare_commit({
                'messages': [{'role': 'user', 'content': 'question'}],
                'tools': tool_surface(),
            })
            callid = result.tool_calls[0]['id']
            state = kernel._pending_tool_resumes[callid]
        finally:
            reset_current_owner(token)
        token = set_current_owner(B)
        try:
            with pytest.raises(Exception) as rejected:
                await kernel._resume_tool_stage_nonstream(
                    state, [{'role': 'tool', 'tool_call_id': callid, 'content': '17'}]
                )
            assert rejected.value.status_code == 409
            assert rejected.value.detail == 'Deep Reasoning tool checkpoint session owner mismatch'
        finally:
            reset_current_owner(token)
        token = set_current_owner(A)
        try:
            final = await kernel._resume_tool_stage_nonstream(
                state, [{'role': 'tool', 'tool_call_id': callid, 'content': '17'}]
            )
            assert final.content == 'A3_CURRENT'
        finally:
            reset_current_owner(token)
    asyncio.run(check())
