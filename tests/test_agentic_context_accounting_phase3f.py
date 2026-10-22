"""Phase 3F: accounting-only portable Agentic projection and backend request tests."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(*, accounting: bool, cache: bool = False):
    os.environ['JACK_REASONING_LEVEL'] = 'agentic'
    os.environ['JACK_FORENSIC_ARCHIVE_MODE'] = 'off'
    os.environ['JACK_BACKEND_MODEL'] = 'test-model'
    os.environ['JACK_BACKEND_PROFILE'] = 'lmstudio'
    os.environ['JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT'] = '1' if cache else '0'
    os.environ['JACK_AGENTIC_CONTEXT_ACCOUNTING'] = '1' if accounting else '0'
    os.environ.pop('JACK_AGENTIC_CONTEXT_REPORT_BUDGET_BYTES', None)
    name = 'jack_phase3f_' + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / 'jack_kernel.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sample(k):
    memory = '[Agentic Memory associated with the preceding user request.]\nWhy A1 happened.'
    messages = [
        {'role': 'user', 'content': 'ORCHID-47 secret source'},
        {'role': 'assistant', 'content': memory, 'reasoning_content': 'native R2 private', 'reasoning': 'native R2 private'},
        {'role': 'assistant', 'content': 'Frozen A1 exact'},
        {'role': 'user', 'content': 'Another task'},
    ]
    payload = {'model': 'test-model', 'messages': messages, 'stream': True,
               'tools': [{'type': 'function', 'function': {'name': 'read'}}]}
    return messages, payload


def test_context_components_portable_and_no_mutations():
    k = load(accounting=True)
    messages, payload = sample(k)
    old = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    report = k._agentic_context_measure_request(messages, payload, k.STAGES['extended_initial'])
    assert json.dumps(payload, ensure_ascii=False, sort_keys=True) == old
    assert report['schema'] == 'jack.agentic.context.v1'
    assert report['backend_profile'] == 'lmstudio'
    assert report['roles']['user'] == 2
    assert report['memory_content_bytes'] > 0
    assert report['frozen_answer_content_bytes'] == len('Frozen A1 exact'.encode())
    assert report['native_reasoning_unique_bytes'] == len('native R2 private'.encode())
    assert report['native_reasoning_field_bytes'] == 2 * len('native R2 private'.encode())
    assert report['request_json_bytes'] == len(json.dumps(payload, ensure_ascii=False,
        separators=(',', ':')).encode('utf-8'))
    assert report['tool_schema_bytes'] > 0
    assert 'secret' not in json.dumps(report)
    assert 'R2 private' not in json.dumps(report)


def test_reporting_budget_is_not_an_admission_gate(monkeypatch):
    k = load(accounting=True)
    msgs, payload = sample(k)
    snap = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    output = []
    monkeypatch.setattr(k.LOG, 'info', lambda *args, **kwargs: output.append(args))
    monkeypatch.setenv('JACK_AGENTIC_CONTEXT_REPORT_BUDGET_BYTES', '25')
    result = k._agentic_context_report_request(msgs, payload, k.STAGES['extended_initial'])
    assert result is None
    assert len(output) == 1
    report = json.loads(output[0][1])
    assert report['budget_status'] == 'over_threshold'
    assert report['report_only_budget_bytes'] == 25
    assert json.dumps(payload, ensure_ascii=False, sort_keys=True) == snap
    assert 'ORCHID-47' not in str(output)
    monkeypatch.setenv('JACK_AGENTIC_CONTEXT_REPORT_BUDGET_BYTES', 'not-a-number')
    k._agentic_context_report_request(msgs, payload, k.STAGES['extended_initial'])
    assert json.loads(output[1][1])['budget_status'] == 'invalid_budget_ignored'


def test_telemetry_fails_open(monkeypatch):
    k = load(accounting=True)
    messages, payload = sample(k)
    monkeypatch.setattr(k, '_agentic_context_measure_request', lambda *args: (_ for _ in ()).throw(RuntimeError('fail')))
    warning = []
    monkeypatch.setattr(k.LOG, 'warning', lambda *a, **kw: warning.append(a))
    assert k._agentic_context_report_request(messages, payload, k.STAGES['extended_initial']) is None
    assert warning and warning[0][1] == 'RuntimeError'


def test_projection_fallback_is_observed_without_modification(monkeypatch):
    k = load(accounting=True)
    events = []
    original_info = k.LOG.info
    monkeypatch.setattr(k.LOG, 'info', lambda *args: events.append(args))
    capsule = k._format_agentic_completed_response('M', 'A')
    inp = [{'role': 'user', 'content': 'old U'},
           {'role': 'assistant', 'content': capsule},
           {'role': 'user', 'content': 'new U'}]
    old = json.dumps(inp, sort_keys=True)
    result = k._compact_agentic_completed_capsules(inp)
    assert json.dumps(inp, sort_keys=True) == old
    assert result[1]['content'] == capsule
    matching = [x for x in events if isinstance(x[0], str) and 'Phase 3F projection' in x[0]]
    assert len(matching) == 1
    # The current Phase 3D/3E public artifact is tag-free ("M\n\nA").
    # Projection still cannot authenticate it without the shadow ledger.
    # Therefore it is preserved as one *opaque* fallback, not split by guessing.
    assert matching[0][1:4] == (0, 1, 1)
    monkeypatch.setattr(k.LOG, 'info', original_info)


async def capture_backend(k, *, streaming: bool, cache: bool):
    payloads = []
    def handler(request):
        payloads.append(json.loads(request.content))
        if streaming:
            a = json.dumps({'choices': [{'index': 0, 'delta': {'content': 'M'}, 'finish_reason': None}]})
            b = json.dumps({'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})
            return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                                  text='data: ' + a + '\n\ndata: ' + b + '\n\ndata: [DONE]\n\n')
        return httpx.Response(200, json={'choices': [{'message': {'role': 'assistant', 'content': 'M'}, 'finish_reason': 'stop'}],
                                         'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}})
    backend = k.OpenAICompatibleBackend(k.CFG)
    await backend._client.aclose()
    backend._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async def name():
        return 'test-model'
    backend.resolve_model = name
    history = [{'role': 'user', 'content': 'create a clock'},
               {'role': 'assistant', 'content': 'Frozen A1', 'reasoning_content': 'R1 native'}]
    tools = [{'type': 'function', 'function': {'name': 'read', 'description': 'file reader',
             'parameters': {'type': 'object', 'properties': {}}}}] if cache else None
    args = dict(messages=history, secondary_system='', profile=k.STAGES['extended_reflection'],
                tools=tools, tool_choice='auto' if cache else None)
    if streaming:
        async for _ in backend.chat_stream(**args):
            pass
    else:
        await backend.chat(**args)
    await backend._client.aclose()
    assert len(payloads) == 1
    return payloads[0]


@pytest.mark.parametrize('streaming', [False, True])
@pytest.mark.parametrize('cache', [False, True])
def test_actual_backend_request_identical_with_and_without_accounting(streaming, cache):
    off = load(accounting=False, cache=cache)
    a = asyncio.run(capture_backend(off, streaming=streaming, cache=cache))
    on = load(accounting=True, cache=cache)
    b = asyncio.run(capture_backend(on, streaming=streaming, cache=cache))
    assert a == b
    assert off.AGENTIC_STAGE1_PROMPT == on.AGENTIC_STAGE1_PROMPT
    assert off.AGENTIC_36_STAGE2_PROMPT == on.AGENTIC_36_STAGE2_PROMPT
    assert on.STAGES['extended_reflection'].allow_tools is False


def test_disabled_flag_no_telemetry(monkeypatch):
    k = load(accounting=False)
    msgs, payload = sample(k)
    emitted = []
    monkeypatch.setattr(k.LOG, 'info', lambda *args: emitted.append(args))
    assert k._agentic_context_report_request(msgs, payload, k.STAGES['extended_initial']) is None
    assert emitted == []


def test_bounded_receipt_bytes_and_combined_artifact_are_accounted():
    k = load(accounting=True)
    note = '\n\n[Jack Tool History - Host-Recorded Receipt]\n- id=x; tool=read\n[/Jack Tool History - Host-Recorded Receipt]'
    combined = '<Agentic Memory>\n' + 'M' + note + '\n</Agentic Memory>\n\n<Model Response>\nOriginal A1'
    msgs = [{'role': 'user', 'content': 'U'}, {'role': 'assistant', 'content': combined}]
    payload = {'model': 'test-model', 'messages': msgs}
    report = k._agentic_context_measure_request(msgs, payload, k.STAGES['extended_initial'])
    assert report['host_receipt_blocks'] == 1
    assert report['host_receipt_content_bytes'] == len(note[note.index('[Jack'):].encode('utf-8'))
    assert report['memory_content_bytes'] == len(('M' + note).encode('utf-8'))
    assert report['frozen_answer_content_bytes'] == len('Original A1'.encode('utf-8'))


def test_malformed_host_artifact_is_not_attributed_as_verified_memory():
    k = load(accounting=True)
    malformed = '<Agentic Memory>\nM\n</Agentic Memory>\nnot a host divider\nA'
    report = k._agentic_context_measure_request(
        [{'role': 'assistant', 'content': malformed}], {'messages': []}, k.STAGES['extended_initial'])
    assert report['memory_content_bytes'] == 0
    assert report['frozen_answer_content_bytes'] == 0
    assert report['other_assistant_content_bytes'] == len(malformed.encode('utf-8'))


def test_host_delimiter_counts_exact_unicode_and_whitespace():
    k = load(accounting=True)
    memory = 'café\n  record  '
    frozen = '  exact A1 💡\n'
    combined = '<Agentic Memory>\n' + memory + '\n</Agentic Memory>\n\n<Model Response>\n' + frozen
    report = k._agentic_context_measure_request(
        [{'role': 'assistant', 'content': combined}], {'messages': []}, k.STAGES['extended_initial'])
    assert report['memory_content_bytes'] == len(memory.encode('utf-8'))
    assert report['frozen_answer_content_bytes'] == len(frozen.encode('utf-8'))



def test_canonical_tag_free_artifact_is_opaque_without_host_authentication():
    """Phase 3D/3E returns untagged public A1/M; its text cannot safely be split
    into memory/answer components unless the Phase 3C shadow check succeeds.
    """
    k = load(accounting=True)
    artifact = k._format_agentic_completed_response('M', 'A')
    assert artifact == 'M\n\nA'  # explicit existing Phase 3D contract
    report = k._agentic_context_measure_request(
        [{'role': 'assistant', 'content': artifact}],
        {'messages': [{'role': 'assistant', 'content': artifact}]},
        k.STAGES['extended_initial'])
    assert report['memory_content_bytes'] == 0
    assert report['frozen_answer_content_bytes'] == 0
    assert report['other_assistant_content_bytes'] == len(artifact.encode('utf-8'))


def test_authenticated_projection_accounts_M_and_A_without_tags():
    """Once Jack projects the validated historical pair, byte attribution is
    safe based on its own explicit separate model-facing message structure.
    """
    k = load(accounting=True)
    mem = '[Agentic Memory associated with the preceding user request and following frozen response]\nM'
    msgs = [
        {'role':'user','content':'U'},
        {'role':'assistant','content':mem},
        {'role':'assistant','content':'A'},
        {'role':'user','content':'next task'}]
    report = k._agentic_context_measure_request(msgs, {'messages':msgs}, k.STAGES['extended_initial'])
    assert report['memory_content_bytes'] == len(mem.encode('utf-8'))
    assert report['frozen_answer_content_bytes'] == 1
