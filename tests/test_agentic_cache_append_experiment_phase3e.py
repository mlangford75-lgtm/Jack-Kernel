"""Phase 3E: default-on LM Studio backend payload with opt-out; no hardware required."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid
import httpx
import pytest

ROOT=Path(__file__).resolve().parents[1]
STAGE2="Generate a detailed summary of why you came to this conclusion."

def load(enabled):
    os.environ["JACK_REASONING_LEVEL"]="agentic"
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"]="off"
    os.environ["JACK_BACKEND_MODEL"]="test-model"
    os.environ["JACK_BACKEND_PROFILE"]="lmstudio"
    if enabled is None:
        os.environ.pop("JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT", None)
    else:
        os.environ["JACK_AGENTIC_STAGE2_CACHE_EXPERIMENT"]="1" if enabled else "0"
    name="jack_cache_test_"+uuid.uuid4().hex
    spec=importlib.util.spec_from_file_location(name,ROOT/"jack_kernel.py")
    k=importlib.util.module_from_spec(spec)
    sys.modules[name]=k
    spec.loader.exec_module(k)
    return k

def fixture(k):
    hist=[{"role":"user","content":"explain the clock"},
          {"role":"assistant","content":"A1 exact","reasoning_content":"Stage 1 native R1"}]
    tools=[{"type":"function","function":{"name":"read","description":"read", "parameters":{"type":"object","properties":{}}}}]
    return hist,tools

async def collect(k,enabled,stream=False,tool_choice="auto"):
    payloads=[]
    def responder(request):
        body=json.loads(request.content)
        payloads.append(body)
        if stream:
            message=json.dumps({"choices":[{"index":0,"delta":{"content":"M"},"finish_reason":None}]})
            stop=json.dumps({"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}})
            return httpx.Response(200,text="data: "+message+"\n\ndata: "+stop+"\n\ndata: [DONE]\n\n",headers={"content-type":"text/event-stream"})
        return httpx.Response(200,json={"choices":[{"message":{"role":"assistant","content":"M"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}})
    b=k.OpenAICompatibleBackend(k.CFG)
    await b._client.aclose()
    b._client=httpx.AsyncClient(transport=httpx.MockTransport(responder))
    async def model(): return "test-model"
    b.resolve_model=model
    hist,tools=fixture(k)
    profile=k.STAGES["extended_reflection"]
    if stream:
        async for _ in b.chat_stream(messages=hist,secondary_system="",profile=profile,tools=tools if enabled else None,tool_choice=tool_choice if enabled else None):pass
    else:
        await b.chat(messages=hist,secondary_system="",profile=profile,tools=tools if enabled else None,tool_choice=tool_choice if enabled else None)
    await b._client.aclose()
    assert len(payloads)==1
    return payloads[0]

@pytest.mark.parametrize("stream",[False,True])
def test_cache_route_exact_prompt_and_schema(stream):
    k=load(True)
    p=asyncio.run(collect(k,True,stream))
    assert p["messages"][0]["role"]=="system"
    assert p["messages"][0]["content"]==k.AGENTIC_STAGE1_PROMPT
    assert p["messages"][-1]["role"]=="user"
    assert p["messages"][-1]["content"].startswith(STAGE2+"\n\n")
    assert "retrospective memory pass" in p["messages"][-1]["content"]
    assert "Do not continue the task" in p["messages"][-1]["content"]
    assert p["messages"][-2]["content"]=="A1 exact"
    assert p["messages"][-2]["reasoning_content"]=="Stage 1 native R1"
    assert p["tools"][0]["function"]["name"]=="read"
    assert p["tool_choice"]=="auto"
    assert p["chat_template_kwargs"]["preserve_thinking"] is True

@pytest.mark.parametrize("stream",[False,True])
def test_default_stage2_unmodified(stream):
    k=load(False)
    p=asyncio.run(collect(k,False,stream))
    assert p["messages"][0]["content"]==STAGE2
    assert "tools" not in p
    assert p["messages"][-1]["role"]=="user"
    assert p["messages"][-1]["content"]!=STAGE2


def test_original_stage_profiles_immutable():
    k=load(True)
    assert k.STAGES["extended_initial"].prompt==k.AGENTIC_STAGE1_PROMPT
    assert k.STAGES["extended_reflection"].prompt==STAGE2
    assert k.STAGES["extended_reflection"].allow_tools is False
    assert k._agentic_cache_append_enabled(k.STAGES["extended_initial"]) is False
    assert k._agentic_cache_append_enabled(k.STAGES["extended_reflection"]) is True
    assert k._format_agentic_completed_response("M","A")=="M\n\nA"


def test_stage2_tool_request_not_authorized_for_execution():
    k=load(True)
    kernel=k.KERNEL
    count=[0]
    async def fake_chat(**kwargs):
        count[0]+=1
        assert kwargs["profile"].allow_tools is False
        # Simulate an unsolicited Stage-2 tool call. Jack must reject every try.
        return {"choices":[{"message":{"role":"assistant","content":"","tool_calls":[
            {"id":"not-authorized","type":"function","function":{"name":"read","arguments":"{}"}}
        ]},"finish_reason":"tool_calls"}],"usage":{}}
    kernel.backend.chat=fake_chat
    hist,_=fixture(k)
    with pytest.raises(k.HTTPException) as exc:
        asyncio.run(kernel._run_stage(hist,"","extended_reflection",{},tools=fixture(k)[1],tool_choice="auto",append=False))
    assert exc.value.status_code==502
    assert count[0]>=1


def test_cache_append_is_on_by_default_and_can_be_disabled():
    k=load(None)
    assert k.AGENTIC_CACHE_APPEND_EXPERIMENT
    assert k._agentic_cache_append_enabled(k.STAGES["extended_reflection"])
    assert not k._agentic_cache_append_enabled(k.STAGES["extended_reflection"], "required")
    assert not k._agentic_cache_append_enabled(k.STAGES["extended_reflection"], {"type":"function", "function":{"name":"read"}})
    k=load(False)
    assert not k.AGENTIC_CACHE_APPEND_EXPERIMENT
    assert not k._agentic_cache_append_enabled(k.STAGES["extended_reflection"])

@pytest.mark.parametrize("stream",[False,True])
def test_default_request_uses_cache_append(stream):
    k=load(None)
    p=asyncio.run(collect(k,True,stream))
    assert p["messages"][0]["content"]==k.AGENTIC_STAGE1_PROMPT
    assert p["messages"][-1]["content"].startswith(STAGE2)
    assert p["tools"][0]["function"]["name"]=="read"

@pytest.mark.parametrize("stream",[False,True])
def test_forced_tool_choice_falls_back_to_existing_stage2(stream):
    k=load(None)
    p=asyncio.run(collect(k,True,stream,tool_choice="required"))
    assert p["messages"][0]["content"]==STAGE2
    assert "tools" not in p

