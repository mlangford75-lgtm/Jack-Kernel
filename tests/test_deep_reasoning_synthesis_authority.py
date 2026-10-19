"""Synthesis finality / host-gated artifact correction, without source prompt edits."""
import asyncio
import json
from pathlib import Path

from jack_deep_reasoning_context import synthesis_messages
from jack_deep_reasoning_orchestrator import DeepReasoningOrchestrator, PendingToolRequest, CompletedAnswer, load_exact_v6_prompts

PROMPTS = {"ULTRA_STAGE1_THESIS_PROMPT": "thesis", "ULTRA_STAGE2_ANTITHESIS_PROMPT": "antithesis", "ULTRA_STAGE3_SYNTHESIS_PROMPT": "synthesis"}
TOOLS = [{"type": "function", "function": {"name": "write", "parameters": {"type": "object"}}}]

class SyntheticBackend:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)

def test_arbiter_handoff_authority_does_not_mutate_locked_prompts():
    p = Path(__file__).resolve().parents[1] / 'tas_v6_prompts.json'
    original = json.loads(p.read_text())
    assert load_exact_v6_prompts(p) == original
    projected = synthesis_messages(request='Update analog-clock.html', thesis_answer='T: finished', antithesis_findings='A: not finished')
    handoff = projected[-1]['content']
    assert 'sole final-answer author' in handoff
    assert 'replace either or both' in handoff
    assert 'host execution policy' in handoff
    assert 'grants no additional' in handoff
    assert projected[1]['content'] == 'T: finished'
    assert projected[3]['content'] == 'A: not finished'
    assert not any('reasoning_content' in m for m in projected)

def test_synthesis_can_propose_authorized_overwrite_then_commit_own_final():
    backend = SyntheticBackend([
        {'content': 'THESIS claimed done', 'reasoning_content': 'R1 PRIVATE'},
        {'tool_calls': [{'id': 'inspect', 'type': 'function', 'function': {'name': 'write', 'arguments': '{}'}}]},
        {'content': 'ANTITHESIS says artifact is wrong', 'reasoning_content': 'R2 PRIVATE'},
        {'tool_calls': [{'id': 'replace', 'type': 'function', 'function': {'name': 'write', 'arguments': '{"path":"analog-clock.html"}'}}], 'reasoning_content': 'R3 PRETOOL'},
        {'content': 'I corrected analog-clock.html and verified that the tool reported success.', 'reasoning_content': 'R3 FINAL'},
    ])
    run = lambda awaitable: asyncio.run(awaitable)
    engine = DeepReasoningOrchestrator(backend, prompts=PROMPTS, tools=TOOLS, preserve_stage_tool_reasoning=True)
    p = run(engine.start(request='Correct the analog clock file'))
    assert isinstance(p, PendingToolRequest) and p.stage == 'antithesis'
    p = run(engine.resume(p, results=[{'tool_call_id': 'inspect', 'content': 'record of observed file'}]))
    assert isinstance(p, PendingToolRequest) and p.stage == 'synthesis'
    assert backend.calls[-1]['tool_choice'] == 'auto'
    assert backend.calls[-1]['tools'] == TOOLS
    assert 'R1 PRIVATE' not in str(backend.calls[-1]['messages'])
    assert 'R2 PRIVATE' not in str(backend.calls[-1]['messages'])
    result = run(engine.resume(p, results=[{'tool_call_id': 'replace', 'content': 'host-authorized write succeeded'}]))
    assert isinstance(result, CompletedAnswer)
    assert result.answer.startswith('I corrected')
    assert result.answer != 'THESIS claimed done'
    assert result.answer != 'ANTITHESIS says artifact is wrong'
    assert result.synthesis_native_reasoning == 'R3 FINAL'
    assert 'R3 PRETOOL' in str(backend.calls[-1]['messages'])
    assert 'R2 PRIVATE' not in str(backend.calls[-1]['messages'])
