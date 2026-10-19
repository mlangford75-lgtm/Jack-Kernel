from __future__ import annotations
import asyncio
import json
from types import SimpleNamespace
import pytest

from deep_reasoning_pi_stream import deep_reasoning_pi_stream


def ns():
    return SimpleNamespace(CFG=SimpleNamespace(virtual_model='jack-kernel'),normalize_usage=lambda u: u)


class FakeKernel:
    def __init__(self, result):
        self.result=result
        self.times_called=0

    async def _run_impl(self, request):
        self.times_called+=1
        return self.result


def decode(items):
    return [json.loads(frame.decode().removeprefix('data: ').strip()) for frame in items if frame.startswith(b'data: {')]


async def collect(kernel):
    return [p async for p in deep_reasoning_pi_stream(kernel,{'stream':True},ns(),heartbeat_seconds=0.002)]


def test_committed_synthesis_only():
    kernel=FakeKernel(SimpleNamespace(tool_calls=None,finish_reason='stop',content='Answer 493',reasoning_content='private R3',usage={'prompt_tokens':1}))
    frames=asyncio.run(collect(kernel))
    chunks=decode(frames)
    assert kernel.times_called == 1
    assert chunks[0]['choices'][0]['delta']=={'role':'assistant'}
    assert chunks[1]['choices'][0]['delta']=={'content':'Answer 493'}
    assert 'private R3' not in str(frames)
    assert chunks[2]['choices'][0]['finish_reason']=='stop'
    assert frames[-1]==b'data: [DONE]\n\n'


def test_tool_checkpoint_only():
    calls=[{'id':'call-1','type':'function','function':{'name':'bash','arguments':'{"command":"python -c \"print(17*29)\""}'}}]
    kernel=FakeKernel(SimpleNamespace(tool_calls=calls,finish_reason='tool_calls',content=None,reasoning_content=None,usage={}))
    frames=asyncio.run(collect(kernel))
    chunks=decode(frames)
    assert chunks[1]['choices'][0]['delta']['tool_calls'][0]['function']['name']=='bash'
    assert chunks[2]['choices'][0]['finish_reason']=='tool_calls'
    assert 'Answer' not in repr(frames)


def test_provisional_text_at_tool_boundary_fails_closed():
    calls=[{'id':'a','type':'function','function':{'name':'bash','arguments':'{}'}}]
    kernel=FakeKernel(SimpleNamespace(tool_calls=calls,finish_reason='tool_calls',content='LEAK',reasoning_content=None,usage={}))
    with pytest.raises(RuntimeError,match='leaked provisional'):
        asyncio.run(collect(kernel))


def test_missing_final_fails_closed():
    kernel=FakeKernel(SimpleNamespace(tool_calls=None,finish_reason='stop',content='',reasoning_content=None,usage={}))
    with pytest.raises(RuntimeError,match='no committed Synthesis'):
        asyncio.run(collect(kernel))


def test_progress_heartbeat_without_intermediate_content():
    class Slow:
        async def _run_impl(self, request):
            await asyncio.sleep(0.015)
            return SimpleNamespace(tool_calls=None,finish_reason='stop',content='done',reasoning_content=None,usage={})
    frames=asyncio.run(collect(Slow()))
    assert any(f.startswith(b': jack-keepalive') for f in frames)
    assert sum(b'"content": "done"' in f for f in frames)==1


def test_installed_pi_stream_dispatch_and_lane_accepts_mode():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    kernel = (root / "jack_kernel.py").read_text(encoding="utf-8")
    driver = (root / "jack_deep_reasoning_kernel.py").read_text(encoding="utf-8")
    lane = (root / "start-lane.ps1").read_text(encoding="utf-8")
    assert 'async for wire in self._deep_reasoning_pi_stream(request_body):' in kernel
    assert 'kernel._deep_reasoning_pi_stream = pi_stream' in driver
    assert '"deep-reasoning"' in lane
