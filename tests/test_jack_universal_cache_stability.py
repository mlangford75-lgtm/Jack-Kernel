"""Mode-independent tool-stage cache prefix safety checks."""
from jack_stage1_cache_stability import Stage1CacheStabilizer
import pytest

TOOL_MODES = [
    "Native answer",
    "Agentic native pass 1",
    "Deep Research Synthesis pass 3",
    "Deep Reasoning Thesis pass 1",
    "Deep Reasoning Antithesis pass 2",
    "Deep Reasoning Synthesis pass 3",
    "Code Debugging Pass 1",
    "Code Debugging Pass 5",
]

@pytest.mark.parametrize("stage", TOOL_MODES)
def test_tool_stages_preserve_new_system_instructions_on_confirmed_resume(stage):
    helper = Stage1CacheStabilizer()
    original = [{"role":"system","content":"caller\n\n--- JACK STAGE ---\nOriginal"}, {"role":"user","content":"task"}]
    result = helper.apply(stage=stage,turn_id="work::"+stage,messages=original,
                          tool_continuation=False,eligible=True)
    assert result["action"] == "snapshot"
    continued = [{"role":"system","content":"caller\nTRANSIENT\n\n--- JACK STAGE ---\nOriginal"},
                 {"role":"user","content":"task"},
                 {"role":"assistant","tool_calls":[{"id":"a"}]},
                 {"role":"tool","tool_call_id":"a","content":"done"}]
    result = helper.apply(stage=stage,turn_id="work::"+stage,messages=continued,
                          tool_continuation=True,eligible=True)
    assert result["action"] == "preserved_change"
    assert continued[0]["content"] == "caller\nTRANSIENT\n\n--- JACK STAGE ---\nOriginal"
    assert original[0]["content"] == "caller\n\n--- JACK STAGE ---\nOriginal"
    assert len(continued) == 4

@pytest.mark.parametrize("stage", [
    "Agentic native pass 2", "Deep Research Antithesis pass 2",
    "Code Debugging Summary"
])
def test_tool_free_stages_preserve_their_distinct_instructions(stage):
    helper = Stage1CacheStabilizer()
    system = [{"role":"system","content":"Different authoritative stage instructions"}]
    assert helper.apply(stage=stage,turn_id="work",messages=system,
                        tool_continuation=False,eligible=False)["action"] == "unchanged"
    assert system[0]["content"] == "Different authoritative stage instructions"

def test_new_turn_cannot_inherit_old_system():
    helper = Stage1CacheStabilizer()
    helper.apply(stage="Native answer",turn_id="work-1",
                 messages=[{"role":"system","content":"Original"}],
                 tool_continuation=False,eligible=True)
    next_work = [{"role":"system","content":"Original plus new instruction"}]
    assert helper.apply(stage="Native answer",turn_id="work-2",
                        messages=next_work,tool_continuation=False,
                        eligible=True)["action"] == "snapshot"
    assert next_work[0]["content"] == "Original plus new instruction"

def test_replacement_not_suppressed():
    helper = Stage1CacheStabilizer()
    helper.apply(stage="Native answer",turn_id="work",
                 messages=[{"role":"system","content":"Original"}],
                 tool_continuation=False,eligible=True)
    changed = [{"role":"system","content":"Modified"}]
    assert helper.apply(stage="Native answer",turn_id="work",
                        messages=changed,tool_continuation=True,
                        eligible=True)["reason"] == "non_insert_change_preserved"

def test_missing_original_is_fail_open():
    helper = Stage1CacheStabilizer()
    system = [{"role":"system","content":"Original"}]
    assert helper.apply(stage="Native answer",turn_id="work",
                        messages=system,tool_continuation=True,
                        eligible=True)["reason"] == "no_original_stage1_snapshot"

def test_cross_mode_key_isolation():
    helper = Stage1CacheStabilizer()
    helper.apply(stage="Native answer",turn_id="Native answer::work",
                 messages=[{"role":"system","content":"Native"}],
                 tool_continuation=False,eligible=True)
    next_mode = [{"role":"system","content":"Deep"}]
    assert helper.apply(stage="Deep Reasoning Thesis pass 1",
                        turn_id="Deep Reasoning Thesis pass 1::work",
                        messages=next_mode,tool_continuation=True,
                        eligible=True)["reason"] == "no_original_stage1_snapshot"
