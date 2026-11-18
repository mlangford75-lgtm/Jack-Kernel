from types import SimpleNamespace
import pytest
from jack_cache_orchestrator import CacheOrchestrator


def config(**overrides):
    args = dict(backend_base_url='http://localhost:1234/v1', backend_profile='lmstudio',
                cache_policy='auto', cache_aux_base_url='', cache_slot_adapter='off',
                cache_primary_slot=0, cache_aux_slot=1, cache_min_primary_bytes=1024,
                cache_aux_stages='Agentic native pass 2', max_concurrent_requests=1)
    args.update(overrides)
    return SimpleNamespace(**args)


def test_default_is_wire_neutral_for_lmstudio():
    r = CacheOrchestrator(config())
    first = r.plan('Agentic native pass 1', 'model', [{'role':'user','content':'hello'}])
    second = r.plan('Agentic native pass 2', 'model', [{'role':'user','content':'memory'}])
    payload = {'messages': []}
    r.apply_hint(payload, first); r.apply_hint(payload, second)
    assert payload == {'messages': []}
    assert not first.alternate_endpoint and not second.alternate_endpoint


def test_same_stage_continuation_keeps_slot_even_after_tool_error():
    r = CacheOrchestrator(config(backend_profile='llamacpp', cache_slot_adapter='llamacpp', cache_policy='prefer_isolated'))
    before = r.plan('Agentic native pass 1','model',[{'role':'user','content':'task'}])
    after = r.plan('Agentic native pass 1','model',[{'role':'tool','content':'command exited with code 1'}])
    memory = r.plan('Agentic native pass 2','model',[{'role':'user','content':'memory'}])
    assert before.slot_id == after.slot_id == 0
    assert memory.slot_id == 1


def test_auto_isolates_long_prefix_with_two_endpoints():
    r=CacheOrchestrator(config(cache_aux_base_url='http://localhost:1337/v1'))
    r.plan('Agentic native pass 1','model',[{'role':'user','content':'X'*2000}])
    secondary=r.plan('Agentic native pass 2','model',[{'role':'user','content':'summary'}])
    assert secondary.base_url=='http://localhost:1337/v1' and secondary.alternate_endpoint


def test_auto_short_prefix_stays_shared():
    r=CacheOrchestrator(config(cache_aux_base_url='http://localhost:1337/v1'))
    r.plan('Agentic native pass 1','model',[{'role':'user','content':'short'}])
    assert r.plan('Agentic native pass 2','model',[]).base_url == r.primary


def test_shared_disables_all_hints():
    r=CacheOrchestrator(config(backend_profile='llamacpp', cache_slot_adapter='llamacpp',cache_policy='shared', cache_aux_base_url='http://localhost:1337/v1'))
    for stage in ('Agentic native pass 1','Agentic native pass 2'):
        d=r.plan(stage,'model',[{'role':'user','content':'X'*10000}]); assert d.slot_id is None and d.base_url == r.primary


def test_explicit_slot_is_provider_and_concurrency_guarded():
    assert CacheOrchestrator(config(cache_slot_adapter='llamacpp', cache_policy='prefer_isolated')).plan('Agentic native pass 1','m',[]).slot_id is None
    assert CacheOrchestrator(config(backend_profile='llamacpp',cache_slot_adapter='llamacpp', max_concurrent_requests=2, cache_policy='prefer_isolated')).plan('Agentic native pass 1','m',[]).slot_id is None


def test_unsupported_hint_fail_open_after_rejection():
    r=CacheOrchestrator(config(backend_profile='llamacpp',cache_slot_adapter='llamacpp',cache_policy='prefer_isolated'))
    d=r.plan('Agentic native pass 2','m',[])
    payload={'id_slot':1, 'messages':[{'role':'user','content':'abc'}]}
    assert d.slot_id==1
    assert r.strip_hint(payload)=={'messages':[{'role':'user','content':'abc'}]}
    assert payload['id_slot']==1
    r.disable_unsupported_hint()
    assert r.plan('Agentic native pass 2','m',[]).slot_id is None


def test_same_slot_invalid_falls_back():
    r=CacheOrchestrator(config(backend_profile='llamacpp',cache_slot_adapter='llamacpp',cache_policy='prefer_isolated',cache_aux_slot=0))
    assert r.plan('Agentic native pass 1','m',[]).slot_id is None


def test_configured_aux_stages_are_generic():
    r=CacheOrchestrator(config(cache_policy='prefer_isolated',cache_aux_base_url='http://localhost:1337/v1',cache_aux_stages='Agentic native pass 2;Deep Research Antithesis'))
    assert r.plan('Deep Research Antithesis','m',[]).lane == 'auxiliary'

def test_environment_can_set_policy_without_kernel_config_fields(monkeypatch):
    monkeypatch.setenv('JACK_CACHE_POLICY', 'prefer_isolated')
    monkeypatch.setenv('JACK_CACHE_AUX_BASE_URL', 'http://localhost:1444/v1')
    cfg=SimpleNamespace(backend_base_url='http://localhost:1234/v1',backend_profile='lmstudio',max_concurrent_requests=1)
    r=CacheOrchestrator(cfg)
    assert r.plan('Agentic native pass 2','model',[]).base_url == 'http://localhost:1444/v1'


def test_unavailable_aux_falls_back_without_changing_prompt():
    r=CacheOrchestrator(config(cache_policy='prefer_isolated', cache_aux_base_url='http://localhost:1337/v1'))
    assert r.plan('Agentic native pass 2','model',[]).alternate_endpoint
    r.disable_unavailable_aux()
    assert r.plan('Agentic native pass 2','model',[]).base_url == r.primary
