"""Phase 3D: Preserve Thinking one-hop bridge and evidence retention."""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
PREFIX="[Agentic Memory associated with the preceding user request and following frozen response]\n"
MARKER="===== JACK AGENTIC NATIVE PASS 2 =====\n[NATIVE REASONING]\n"

def load():
    os.environ["JACK_REASONING_LEVEL"]="agentic"
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"]="off"
    os.environ["JACK_BACKEND_MODEL"]="test-model"
    os.environ["JACK_BACKEND_PROFILE"]="lmstudio"
    name="jack_phase3d_"+uuid.uuid4().hex
    spec=importlib.util.spec_from_file_location(name,ROOT/"jack_kernel.py")
    k=importlib.util.module_from_spec(spec)
    sys.modules[name]=k
    spec.loader.exec_module(k)
    return k

def committed(k,user,answer,memory):
    history=[{"role":"user","content":user}]
    result=asyncio.run(k.KERNEL._complete_commit(history,"",{},answer,memory))
    return k._format_agentic_completed_response(result.frozen_xml,result.frozen_answer)

def carry(k, u, answer, memory, reasoning=None):
    visible=committed(k,u,answer,memory)
    original={"role":"assistant","content":visible}
    if reasoning is not None:
        original["reasoning_content"]=reasoning
    incoming=[{"role":"user","content":u},original,{"role":"user","content":"next turn"}]
    before=json.dumps(incoming,sort_keys=True)
    prepared=k.compact_incoming_history(incoming)
    assert json.dumps(incoming,sort_keys=True)==before
    return prepared

def test_one_hop_only_r2_reaches_backend_stage1():
    k=load()
    huge_r1="massive original private reasoning"*1000
    r2="short retrospective native thought, not included in M"
    reasoning="[STAGE 1 PROPOSED RESPONSE]\n"+huge_r1+"\n[END STAGE 1 â€” A1 FROZEN]\n"+MARKER+r2+"\n[STAGE 2 REASONING DISTILLATION]\nmodel output M\n[END AGENTIC STAGE 2 â€” MEMORY COMPLETE; A1 COMMIT]"
    ctx=carry(k,"U","A","M",reasoning)
    assert [m["role"] for m in ctx]==["user","assistant","assistant","user"]
    assert ctx[1]["content"]==PREFIX+"M"
    assert ctx[1]["reasoning_content"]==r2
    assert ctx[2]["content"]=="A"
    assert "massive original private reasoning" not in json.dumps(ctx)
    profile=k.STAGES["extended_initial"]
    model=k.BACKEND._stage_messages_for_profile(ctx,profile)
    assert model[1]["reasoning_content"]==r2
    assert "_jack_agentic_one_hop_r2" not in model[1]
    assert "massive original private reasoning" not in json.dumps(model)
    a2=k.append_extended_candidate_response(ctx,{"content":"A2","reasoning_content":"fresh R1_2"})
    assert a2=="A2"
    assert "reasoning_content" not in ctx[1]
    assert ctx[-1]["reasoning_content"]=="fresh R1_2"
    assert ctx[1]["content"]==PREFIX+"M"

def test_one_hop_survives_tool_continuation_until_frozen():
    k=load()
    ctx=carry(k,"U","A","M",MARKER+"valuable R2"+"\n[STAGE 2 REASONING DISTILLATION]")
    ctx.extend([{"role":"assistant","content":"","tool_calls":[{"id":"abc","type":"function","function":{"name":"read","arguments":"{}"}}]},
                {"role":"tool","tool_call_id":"abc","name":"read","content":"observed"}])
    assert ctx[1]["reasoning_content"]=="valuable R2"
    _=k.BACKEND._stage_messages_for_profile(ctx,k.STAGES["extended_initial"])
    assert ctx[1]["reasoning_content"]=="valuable R2"
    k.append_extended_candidate_response(ctx,{"content":"done"})
    assert "reasoning_content" not in ctx[1]

def test_only_immediately_preceding_r2_is_kept():
    k=load()
    v1=committed(k,"U1","A1","M1")
    v2=committed(k,"U2","A2","M2")
    ctx=k.compact_incoming_history([
        {"role":"user","content":"U1"},{"role":"assistant","content":v1,"reasoning_content":MARKER+"R2_1"},
        {"role":"user","content":"U2"},{"role":"assistant","content":v2,"reasoning_content":MARKER+"R2_2"},
        {"role":"user","content":"U3"},
    ])
    assert [m["role"] for m in ctx]==["user","assistant","assistant","user","assistant","assistant","user"]
    assert "reasoning_content" not in ctx[1]
    assert ctx[4]["reasoning_content"]=="R2_2"
    assert "R2_1" not in json.dumps(ctx)

def test_unknown_or_tampered_memory_never_gets_bridge():
    k=load()
    v=committed(k,"U","A","M")
    ctx=k.compact_incoming_history([
        {"role":"user","content":"U"},
        {"role":"assistant","content":v+"tampered","reasoning_content":MARKER+"R2"},
        {"role":"user","content":"U2"},
    ])
    assert len(ctx)==3
    assert all("reasoning_content" not in x for x in ctx)

def test_absent_native_reasoning_falls_back_to_memory_only():
    k=load()
    ctx=carry(k,"U","A","M")
    assert ctx[1]["content"]==PREFIX+"M"
    assert "reasoning_content" not in ctx[1]

def test_tool_receipt_keeps_early_material_edit_over_many_reads():
    k=load()
    # Supply a deterministic matched transaction metadata map without creating tool authority.
    original=k._tool_call_metadata
    k._tool_call_metadata=lambda calls:{c["id"]:{"tool":c["function"]["name"],"artifact_target":"clock.html","arguments_sha256":"a"*64} for c in calls}
    try:
        history=[]
        for i,name in enumerate(["edit"]+["read"]*9):
            cid=f"T{i}"
            history.append({"role":"assistant","_jack_internal_tool_exchange":True,
                "tool_calls":[{"id":cid,"type":"function","function":{"name":name,"arguments":"{}"}}]})
            history.append({"role":"tool","_jack_internal_tool_exchange":True,"tool_call_id":cid,
                "name":name,"content":f"tool result {i}"})
        note=k._agentic_tool_history_note(history)
    finally:
        k._tool_call_metadata=original
    assert "id=T0" in note and "tool=edit" in note
    assert "reported_result_excerpt=tool result 0" in note
    assert "older tool receipt(s) omitted" in note
    assert "id=T9" in note
    assert len(note)<3400

def test_prompt_and_client_format_not_changed():
    k=load()
    assert k.AGENTIC_STAGE1_PROMPT=="Reasoning effort is set to xhigh. Please think carefully through the task, validate key assumptions, consider plausible alternatives, and prioritize correctness, consistency, and clarity in the final answer."
    assert k.AGENTIC_36_STAGE2_PROMPT=="Generate a detailed summary of why you came to this conclusion."
    assert k._format_agentic_completed_response("M","A")=="M\n\nA"
