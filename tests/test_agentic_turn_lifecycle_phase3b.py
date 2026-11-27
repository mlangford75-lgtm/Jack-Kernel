"""Phase 3B: host-owned Agentic lifecycle; no client changes or memory replay."""
from __future__ import annotations
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
    name="agentic_phase3b_"+uuid.uuid4().hex
    spec=importlib.util.spec_from_file_location(name,ROOT/"jack_kernel.py")
    k=importlib.util.module_from_spec(spec)
    sys.modules[name]=k
    spec.loader.exec_module(k)
    return k

def test_claim_before_response_and_exact_original_user():
    k=load()
    user={"role":"user","content":"  exact user request  "}
    history=[user]
    tid=k._agentic_begin_turn(history,fresh=True)
    assert tid.startswith("jack-turn-")
    lifecycle=k._AGENTIC_TURN_LIFECYCLES[tid]
    assert lifecycle.status=="stage1_active"
    assert json.loads(lifecycle.user_request.message_json)=={"role":"user","content":"  exact user request  "}
    assert history[0]["_jack_agentic_turn_id"]==tid
    assert user=={"role":"user","content":"  exact user request  "}
    assert history[0] is not user
    assert "_jack_agentic_turn_id" not in lifecycle.user_request.message_json
    assert k._agentic_begin_turn(history,fresh=False)==tid
    assert len(k._AGENTIC_TURN_LIFECYCLES)==1

def test_identical_requests_are_distinct_even_with_injected_identity():
    k=load()
    first=[{"role":"user","content":"same"}]
    t1=k._agentic_begin_turn(first,fresh=True)
    second=[{"role":"user","content":"same","_jack_agentic_turn_id":t1}]
    t2=k._agentic_begin_turn(second,fresh=True)
    assert t1!=t2
    assert json.loads(k._AGENTIC_TURN_LIFECYCLES[t2].user_request.message_json)=={"role":"user","content":"same"}

def test_tool_resume_preserves_identity_and_transitions():
    k=load()
    h=[{"role":"user","content":"write file"}]
    tid=k._agentic_begin_turn(h,fresh=True)
    k._agentic_turn_status(h,"awaiting_tool")
    resume=list(h)+[{"role":"assistant","tool_calls":[],"content":""},{"role":"tool","content":"ok"}]
    assert k._agentic_begin_turn(resume,fresh=False)==tid
    assert k._AGENTIC_TURN_LIFECYCLES[tid].status=="stage1_active"
    assert len(k._AGENTIC_TURN_LIFECYCLES)==1

def test_preanswer_failure_keeps_request_and_no_fake_artifacts():
    k=load()
    h=[{"role":"user","content":" incomplete request "}]
    tid=k._agentic_begin_turn(h,fresh=True)
    k._agentic_mark_stage1_failure("backend_abort")
    assert k._AGENTIC_TURN_LIFECYCLES[tid].status=="stage1_failed"
    assert k._AGENTIC_TURN_LIFECYCLES[tid].failure=="backend_abort"
    assert not k._AGENTIC_SHADOW_LEDGER

def test_complete_record_same_preallocated_identity_and_no_reasoning():
    k=load()
    original={"role":"user","content":" reason this "}
    h=[dict(original)]
    tid=k._agentic_begin_turn(h,fresh=True)
    committed=asyncio.run(k.KERNEL._complete_commit(h,"",{},"A","M"))
    assert committed.frozen_answer=="A"
    (key,record),=k._AGENTIC_SHADOW_LEDGER.items()
    assert record.turn_id==tid
    assert record.response.content=="A"
    assert record.memory.content=="M"
    assert json.loads(record.user_request.message_json)==original
    assert k._AGENTIC_TURN_LIFECYCLES[tid].status=="complete"
    assert not h

def test_memory_failure_keeps_frozen_a_and_owned_u():
    k=load()
    h=[{"role":"user","content":"original"}]
    tid=k._agentic_begin_turn(h,fresh=True)
    usage={"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}
    result=k.KERNEL._agentic_degraded_result(h,usage,"A", "stage2 failed")
    assert result.content=="A"
    rec=next(iter(k._AGENTIC_SHADOW_LEDGER.values()))
    assert rec.turn_id==tid and rec.memory is None
    assert k._AGENTIC_TURN_LIFECYCLES[tid].status=="memory_failed"
    assert json.loads(rec.user_request.message_json)["content"]=="original"
