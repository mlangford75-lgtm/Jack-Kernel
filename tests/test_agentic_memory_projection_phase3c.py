"""Phase 3C: client-independent, self-contained carried-memory projection."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]

def load():
    os.environ["JACK_REASONING_LEVEL"]="agentic"
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"]="off"
    os.environ["JACK_BACKEND_MODEL"]="test-model"
    os.environ["JACK_BACKEND_PROFILE"]="lmstudio"
    name="jack_agentic_3c_" + uuid.uuid4().hex
    spec=importlib.util.spec_from_file_location(name, ROOT/"jack_kernel.py")
    k=importlib.util.module_from_spec(spec)
    sys.modules[name]=k
    spec.loader.exec_module(k)
    return k

def commit(k, user, a, m):
    history=[{"role":"user","content":user}]
    result=asyncio.run(k.KERNEL._complete_commit(history,"",{},a,m))
    assert result.frozen_answer==a
    return k._format_agentic_completed_response(result.frozen_xml, result.frozen_answer)

def test_exact_u_m_a_separated_only_in_model_projection():
    k=load()
    a="  exact A1\n"
    m="Reasoned from the user's constraints and tool results."
    visible=commit(k, "original U", a, m)
    incoming=[{"role":"user","content":"original U"},
              {"role":"assistant","content":visible,"reasoning_content":"retire R1"},
              {"role":"user","content":"next U"}]
    before=json.dumps(incoming,sort_keys=True)
    out=k._compact_agentic_completed_capsules(incoming)
    assert [x["role"] for x in out]==["user","assistant","assistant","user"]
    assert out[1]["content"]=="[Agentic Memory associated with the preceding user request and following frozen response]\n"+m
    assert out[2]["content"]==a
    assert out[3]["content"]=="next U"
    assert all("reasoning_content" not in x for x in out)
    assert json.dumps(incoming,sort_keys=True)==before
    assert visible!=a  # Standard client still transports M and A together.

def test_no_hidden_memory_fetch_from_answer_only():
    k=load()
    commit(k,"U","A","SECRET MEMORY")
    out=k._compact_agentic_completed_capsules([
        {"role":"user","content":"U"},
        {"role":"assistant","content":"A"},
        {"role":"user","content":"next"},
    ])
    assert [x["role"] for x in out]==["user","assistant","user"]
    assert "SECRET MEMORY" not in json.dumps(out)

def test_tampered_combined_output_not_projected():
    k=load()
    visible=commit(k,"U","A","M")
    tampered=visible.replace("M","secret alteration",1)
    out=k._compact_agentic_completed_capsules([
        {"role":"user","content":"U"},
        {"role":"assistant","content":tampered},
        {"role":"user","content":"next"},
    ])
    assert len(out)==3 and out[1]["content"]==tampered

def test_wrong_original_user_never_matches():
    k=load()
    visible=commit(k,"private original U","A","M")
    out=k._compact_agentic_completed_capsules([
        {"role":"user","content":"another U"},
        {"role":"assistant","content":visible},
        {"role":"user","content":"next"},
    ])
    assert len(out)==3 and out[1]["content"]==visible

def test_no_projection_when_memory_failed():
    k=load()
    h=[{"role":"user","content":"U"}]
    usage={"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}
    failed=k.KERNEL._agentic_degraded_result(h,usage,"A","stage2 failed")
    out=k._compact_agentic_completed_capsules([
        {"role":"user","content":"U"},
        {"role":"assistant","content":failed.content},
        {"role":"user","content":"next"},
    ])
    assert len(out)==3 and out[1]["content"]=="A"

def test_restart_without_shadow_ledger_retains_all_caller_memory():
    k=load()
    visible=commit(k,"U","A","M")
    k._AGENTIC_SHADOW_LEDGER.clear()
    out=k._compact_agentic_completed_capsules([
        {"role":"user","content":"U"},
        {"role":"assistant","content":visible},
        {"role":"user","content":"next"},
    ])
    assert len(out)==3 and out[1]["content"]==visible

def test_identical_turns_only_represent_caller_supplied_content():
    k=load()
    v1=commit(k,"identical U","A","M")
    v2=commit(k,"identical U","A","M")
    assert v1==v2
    assert len(k._AGENTIC_SHADOW_LEDGER)==2
    out=k._compact_agentic_completed_capsules([
        {"role":"user","content":"identical U"},
        {"role":"assistant","content":v1},
        {"role":"user","content":"next"},
    ])
    assert len(out)==4 and out[1]["content"].endswith("M") and out[2]["content"]=="A"

def test_stage2_current_frozen_answer_remains_last_before_transition():
    k=load()
    visible=commit(k,"old U","old A","old M")
    h=k.compact_incoming_history([
        {"role":"user","content":"old U"},
        {"role":"assistant","content":visible},
        {"role":"user","content":"current U"},
    ])
    answer=k.append_extended_candidate_response(h,{"content":"current A"})
    assert answer=="current A"
    assert h[-1]["content"]=="current A"
    assert h[1]["content"].endswith("old M") and h[2]["content"]=="old A"

def test_other_modes_do_not_use_agentic_projection():
    k=load()
    k.AGENTIC_MODE=False
    assert k._agentic_project_committed_artifact_pair([{"role":"user","content":"U"}],"M\n\nA") is None
