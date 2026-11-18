import copy
from jack_stage1_cache_stability import Stage1CacheStabilizer


def first(s, turn='jack-turn-abc', **kw):
    x = Stage1CacheStabilizer()
    a = [{'role': 'system', 'content': s}, {'role': 'user', 'content': 'task'}]
    r = x.apply(stage='Agentic native pass 1', turn_id=turn, messages=a,
                tool_continuation=False, **kw)
    assert r['action'] == 'snapshot'
    return x, a


def test_same_work_insertion_preserved_on_wire():
    stab, original = first('Caller contract\n-- stage --\nInstruction')
    canonical = [{'role':'assistant', 'content':'tool call'}, {'role':'tool','content':'ok'}]
    wire = [{'role':'system', 'content':'Caller contract\nTRANSIENT\n-- stage --\nInstruction'},
            {'role':'user', 'content':'task'}, *copy.deepcopy(canonical)]
    r = stab.apply(stage='Agentic native pass 1', turn_id='jack-turn-abc',
                   messages=wire, tool_continuation=True)
    assert r['action'] == 'preserved_change'
    assert wire[0]['content'] == 'Caller contract\nTRANSIENT\n-- stage --\nInstruction'
    assert original[0]['content'] == 'Caller contract\n-- stage --\nInstruction'
    assert wire[1:] == [{'role':'user','content':'task'}, *canonical]


def test_no_change_remains_stable():
    stab, first_wire = first('initial')
    wire = copy.deepcopy(first_wire)
    r = stab.apply(stage='Agentic native pass 1', turn_id='jack-turn-abc',
                   messages=wire, tool_continuation=True)
    assert r['reason'] == 'already_stable'


def test_changed_original_bytes_do_not_get_overwritten():
    stab, _ = first('Caller contract\n-- stage --\nInstructions')
    wire = [{'role':'system','content':'Caller contract\n-- stage --\nChanged instructions'}]
    r = stab.apply(stage='Agentic native pass 1', turn_id='jack-turn-abc',
                   messages=wire, tool_continuation=True)
    assert r['reason'] == 'non_insert_change_preserved'
    assert 'Changed' in wire[0]['content']


def test_removal_not_suppressed():
    stab, _ = first('One two three')
    wire = [{'role':'system','content':'One three'}]
    r = stab.apply(stage='Agentic native pass 1', turn_id='jack-turn-abc',
                   messages=wire, tool_continuation=True)
    assert r['reason'] == 'non_insert_change_preserved'


def test_cross_turn_never_inherits_original():
    stab, _ = first('First turn')
    wire = [{'role':'system','content':'Different turn with insertion'}]
    r = stab.apply(stage='Agentic native pass 1', turn_id='jack-turn-other',
                   messages=wire, tool_continuation=False)
    assert r['action'] == 'snapshot'
    assert wire[0]['content'] == 'Different turn with insertion'


def test_stage2_never_changes():
    stab, _ = first('Stage1')
    wire = [{'role':'system','content':'Stage2'}]
    r = stab.apply(stage='Agentic native pass 2', turn_id='jack-turn-abc',
                   messages=wire, tool_continuation=True)
    assert r['action'] == 'unchanged'
    assert wire[0]['content'] == 'Stage2'


def test_review_never_changes():
    stab, _ = first('Initial')
    wire = [{'role':'system','content':'Initial plus more'}]
    r = stab.apply(stage='Agentic native pass 1', turn_id='jack-turn-abc',
                   messages=wire, tool_continuation=True, review_pending=True)
    assert r['action'] == 'unchanged'


def test_no_known_first_snapshot_never_changes_resume():
    stab = Stage1CacheStabilizer()
    wire = [{'role':'system','content':'Unknown original'}]
    r = stab.apply(stage='Agentic native pass 1', turn_id='jack-turn-abc',
                   messages=wire, tool_continuation=True)
    assert r['reason'] == 'no_original_stage1_snapshot'


def test_disabled_never_changes():
    stab = Stage1CacheStabilizer(enabled=False)
    wire = [{'role':'system','content':'Text'}]
    r = stab.apply(stage='Agentic native pass 1', turn_id='jack-turn-abc',
                   messages=wire, tool_continuation=False)
    assert r['action'] == 'unchanged'


def test_only_single_insertion_accepted():
    assert Stage1CacheStabilizer._insertion('abcXYZ', 'abc++XYZ') == {'character_offset':3,'inserted_characters':2}
    assert Stage1CacheStabilizer._insertion('abcXYZ', 'abXcYZ!') is None
    assert Stage1CacheStabilizer._insertion('abcXYZ', 'abcXYZ') is None


def test_bounded_turn_history():
    stab = Stage1CacheStabilizer(max_turns=2)
    for i in range(3):
        stab.apply(stage='Agentic native pass 1', turn_id=str(i),
                   messages=[{'role':'system','content':str(i)}], tool_continuation=False)
    assert list(stab._first) == ['1','2']


def test_does_not_touch_empty_or_non_system():
    stab = Stage1CacheStabilizer()
    assert stab.apply(stage='Agentic native pass 1',turn_id='x',messages=[],tool_continuation=False)['action']=='unchanged'
    wire=[{'role':'user','content':'hello'}]
    stab.apply(stage='Agentic native pass 1',turn_id='x',messages=wire,tool_continuation=False)
    assert wire[0]['content']=='hello'
