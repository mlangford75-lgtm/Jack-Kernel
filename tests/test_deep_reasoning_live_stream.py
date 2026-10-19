"""Real SSE deltas, stage-observation separation, and per-request isolation."""
from __future__ import annotations
import asyncio
import json
from types import SimpleNamespace
import pytest
from deep_reasoning_pi_stream import deep_reasoning_pi_stream, current_reasoning_sink

NS = SimpleNamespace(CFG=SimpleNamespace(virtual_model='jack-kernel'), normalize_usage=lambda value: value)

def payload(frame):
    return json.loads(frame[6:])

class ObservedStageKernel:
    def __init__(self):
        self.release = asyncio.Event()
        self.started = asyncio.Event()
    async def _run_impl(self, _request):
        sink = current_reasoning_sink()
        assert sink is not None
        sink.offer('reasoning','native token 1')
        self.started.set()
        await self.release.wait()
        sink.offer('reasoning',' native token 2')
        # provisional output must never go to content until this result commits
        return SimpleNamespace(tool_calls=None, finish_reason='stop', content='committed A3',reasoning_content='R3',usage={})

def test_native_tokens_arrive_before_stage_completion_and_before_final_answer():
    async def run():
        k=ObservedStageKernel()
        stream=deep_reasoning_pi_stream(k,{'messages':[]},NS,heartbeat_seconds=.01)
        first=payload(await anext(stream))
        assert first['choices'][0]['delta']=={'role':'assistant'}
        await k.started.wait()
        reasoning=payload(await anext(stream))
        assert reasoning['choices'][0]['delta']['reasoning_content']=='native token 1'
        assert not k.release.is_set()
        k.release.set()
        final=[frame async for frame in stream]
        parsed=[payload(f) for f in final if f.startswith(b'data: {')]
        assert parsed[0]['choices'][0]['delta']['reasoning_content']==' native token 2'
        assert any(x['choices'] and x['choices'][0]['delta'].get('content')=='committed A3' for x in parsed)
        assert not any(x['choices'] and x['choices'][0]['delta'].get('content')=='R3' for x in parsed)
    asyncio.run(run())


def test_reasoning_context_is_request_local_and_does_not_leak_to_next_turn():
    async def run():
        class Echo:
            async def _run_impl(self, body):
                sink=current_reasoning_sink()
                sink.offer('reasoning',body['marker'])
                await asyncio.sleep(.001)
                return SimpleNamespace(tool_calls=None,finish_reason='stop',content=body['marker'],reasoning_content=None,usage={})
        async def collect(marker):
            frames=[f async for f in deep_reasoning_pi_stream(Echo(),{'marker':marker},NS,heartbeat_seconds=.001)]
            return b''.join(frames)
        x,y=await asyncio.gather(collect('first-private-trace'),collect('second-private-trace'))
        assert b'first-private-trace' in x and b'first-private-trace' not in y
        assert b'second-private-trace' in y and b'second-private-trace' not in x
        assert current_reasoning_sink() is None
    asyncio.run(run())


def test_backend_failure_never_sends_final_answer_or_done():
    async def run():
        class Failing:
            async def _run_impl(self, body):
                sink=current_reasoning_sink()
                sink.offer('reasoning','unfinished native thought')
                raise RuntimeError('backend failed')
        seen=[]
        with pytest.raises(RuntimeError,match='backend failed'):
            async for item in deep_reasoning_pi_stream(Failing(),{},NS,heartbeat_seconds=.01):
                seen.append(item)
        assert b'"content"' not in b''.join(seen)
        assert b'data: [DONE]' not in seen
    asyncio.run(run())
