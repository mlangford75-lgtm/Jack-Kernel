"""Focused deterministic Coder profile and phase-authority regression tests."""
import importlib.util
import asyncio
import httpx
import json
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PREFIX = ("Reasoning effort is set to xhigh. Please think carefully through the task, "
          "validate key assumptions, consider plausible alternatives, and prioritize "
          "correctness, consistency, and clarity in the final answer.")


def load(monkeypatch, tmp_path, profile="coder"):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "Local Agentic (Preserve Thinking)")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    monkeypatch.setenv("JACK_LOOP_DETECTOR", "0")
    name = "agentic_coder_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def response(content="Implementation plan", reasoning="PLANNER_R1"):
    return {"choices": [{"message": {"role": "assistant", "content": content,
                                     "reasoning_content": reasoning},
                         "finish_reason": "stop"}]}


def test_profile_isolated_and_reasoning_contract(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    assert k.AGENTIC_CODER_MODE and k.AGENTIC_MODE and not k.AGENTIC_THOROUGH_MODE
    assert k.STAGES["coder_planner"].thinking
    assert k.STAGES["coder_planner"].reasoning_effort == "xhigh"
    assert not k.STAGES["coder_planner"].allow_tools
    assert k.STAGES["extended_initial"].thinking
    assert k.STAGES["extended_initial"].reasoning_effort == "xhigh"
    assert k.STAGES["extended_initial"].allow_tools
    assert k.STAGES["extended_reflection"].thinking
    assert k.AGENTIC_36_STAGE2_PROMPT == k._AGENTIC_STAGE2_THOROUGH_EXHAUSTIVE_DIRECTIVE
    assert not k.STAGES["extended_reflection"].allow_tools
    assert k.CODER_PLANNER_PROMPT.startswith(PREFIX)
    assert k.CODER_EXECUTOR_PROMPT.startswith(PREFIX)
    assert "Who, What, Where, When, Why and How" in k.CODER_PLANNER_PROMPT
    assert k._runtime_identity_details()["flow"] == [
        "coder_planner", "extended_initial", "extended_reflection"
    ]


def test_plan_owned_once_and_preserved_for_memory(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Build and test a website."}]
    initial = json.dumps(h)
    k._coder_append_plan(h, response())
    assert json.dumps(h[:1]) == initial
    assert k.active_response_target(h)["content"] == "Build and test a website."
    assert k._coder_has_plan(h)
    assert h[-1]["role"] == "assistant"
    assert h[-1]["reasoning_content"] == "PLANNER_R1"
    assert h[-1]["content"] == "Implementation plan"
    with pytest.raises(k.ForensicConflict):
        k._coder_append_plan(h, response("Replayed"))
    # Memory must retain both the reasoning and the concrete plan.
    h.append({"role": "assistant", "content": "Done",
              "_jack_extended_candidate_response": True,
              "reasoning_content": "EXECUTOR_R1"})
    events = k._agentic_stage2_chronological_source(h)
    assert any(e.get("type") == "planner_plan" and
               e["content"] == "Implementation plan" for e in events)
    assert any(e.get("type") == "reasoning_segment" and
               e["content"] == "PLANNER_R1" for e in events)
    assert any(e.get("type") == "reasoning_segment" and
               e["content"] == "EXECUTOR_R1" for e in events)


def test_no_tools_and_no_empty_or_synthetic_planning(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Fix code"}]
    with pytest.raises(k.HTTPException):
        k._coder_append_plan(h, response(""))
    with pytest.raises(k.HTTPException):
        k._coder_append_plan(h, {"choices": [{
            "finish_reason": "tool_calls",
            "message": {"content": "Plan", "tool_calls": [{"id": "one"}]}
        }]})
    assert len(h) == 1


def test_executor_wire_projection_does_not_add_user_authority(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "system", "content": "Original system"},
         {"role": "user", "content": "Real request"}]
    k._coder_append_plan(h, response())
    wire = [{"role": x["role"], "content": x["content"]} for x in h]
    k._coder_project_executor_request(wire, h)
    assert wire[-1] == {"role": "user", "content": "Real request"}
    assert sum(x["role"] == "user" for x in wire) == 1
    assert any(x["role"] == "assistant" and x["content"] == "Implementation plan" for x in wire)
    h.append({"role": "tool", "content": "Tool result", "tool_call_id": "one"})
    wire2 = [{"role": x["role"], "content": x["content"]} for x in h]
    k._coder_project_executor_request(wire2, h)
    assert wire2[-1]["role"] == "tool"


def test_thorough_is_unchanged(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, "thorough")
    assert not k.AGENTIC_CODER_MODE
    assert not k._coder_has_plan([{"role": "user", "content": "Task"}])
    assert k.STAGES["extended_initial"].prompt == k.AGENTIC_STAGE1_PROMPT
    assert k.STAGES["extended_reflection"].thinking
    assert k._runtime_identity_details()["flow"] == [
        "extended_initial", "extended_reflection"
    ]


def test_backend_planner_tools_off_executor_tools_on(monkeypatch, tmp_path):
    async def run():
        k = load(monkeypatch, tmp_path)
        payloads = []
        def respond(request):
            payloads.append(json.loads(request.content))
            return httpx.Response(200, json={
                "choices": [{"index": 0, "message": {"role": "assistant",
                            "content": "Planned response", "reasoning_content": "R1"},
                            "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
            })
        backend = k.OpenAICompatibleBackend(k.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async def model():
            return "test-model"
        backend.resolve_model = model
        h = [{"role": "system", "content": "User-defined stable system"},
             {"role": "user", "content": "Build a working clock."}]
        available = [{"type": "function", "function": {"name": "read",
                     "parameters": {"type": "object", "properties": {}}}}]
        try:
            planned = await backend.chat(messages=h, secondary_system="",
                                         profile=k.STAGES["coder_planner"],
                                         tools=available)
            k._coder_append_plan(h, planned)
            await backend.chat(messages=h, secondary_system="",
                               profile=k.STAGES["extended_initial"],
                               tools=available)
            assert len(payloads) == 2
            first, second = payloads
            assert first["reasoning_effort"] == "xhigh"
            assert second["reasoning_effort"] == "xhigh"
            assert "tools" not in first or not first["tools"]
            assert second["tools"][0]["function"]["name"] == "read"
            assert sum(m["role"] == "user" for m in second["messages"]) == 1
            assert second["messages"][-1]["role"] == "user"
            assert second["messages"][-1]["content"] == "Build a working clock."
            assert any(m["role"] == "assistant" and m["content"] == "Planned response"
                       and m.get("reasoning_content") == "R1"
                       for m in second["messages"])
            assert any(m["role"] == "system" and k.CODER_EXECUTOR_PROMPT in m["content"]
                       for m in second["messages"])
        finally:
            await backend._client.aclose()
    asyncio.run(run())
