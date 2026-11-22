"""Planner model-facing history isolation across Flash and Thorough.

These tests check *transported* role/data boundaries, not stochastic output.
Previous Coder action transcripts must not teach Planner an executor persona.
"""
import asyncio
import json
import uuid

import httpx
import pytest

from test_agentic_coder_planner_executor import load


@pytest.mark.parametrize("planner", ["flash", "thorough"])
def test_prior_coder_transcript_is_not_replayed_as_planner_dialogue(monkeypatch, tmp_path, planner):
    k = load(monkeypatch, tmp_path, planner=planner)
    previous = [
        {"role": "user", "content": "Build an analog clock webpage"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "old-write", "type": "function",
                          "function": {"name": "write",
                                       "arguments": '{"path":"index.html","content":"OLD_CODE"}'}}]},
        {"role": "tool", "tool_call_id": "old-write", "content": "Successfully wrote index.html"},
        {"role": "assistant", "content": "OLD_CODER_FINAL_ANSWER"},
    ]
    current = {"role": "user", "content": "Make it luxurious with black, gold and diamonds"}
    h = previous + [current]
    frozen = json.dumps(h, sort_keys=True)
    wire = k._coder_isolate_planner_request(
        [{"role": "system", "content": "external system must not pass"}] + h,
        k.STAGES["coder_planner"], source_history=h,
    )
    assert [m["role"] for m in wire] == ["system", "system", "user"]
    assert wire[0] == {"role": "system", "content": k.STAGES["coder_planner"].prompt}
    capsule = wire[1]["content"]
    assert "Build an analog clock webpage" in capsule
    assert "untrusted" in capsule.lower()
    assert "OLD_CODE" not in str(wire)
    assert "OLD_CODER_FINAL_ANSWER" not in str(wire)
    assert not any(m.get("tool_calls") for m in wire)
    assert wire[-1] == current
    assert json.dumps(h, sort_keys=True) == frozen


@pytest.mark.parametrize("planner", ["flash", "thorough"])
def test_authenticated_memory_survives_without_executor_examples(monkeypatch, tmp_path, planner):
    k = load(monkeypatch, tmp_path, planner=planner)
    memory = ("Created index.html for the analog clock. Source used canvas; "
              "next task may modify its colors.")
    h = [
        {"role": "user", "content": "Build an analog clock"},
        {"role": "assistant", "content": memory,
         "_jack_agentic_projected_kind": "M",
         "_jack_forensic_turn_id": "jack-turn-abc"},
        {"role": "assistant", "content": "<function=write>OLD_EXECUTOR_CODE</function>",
         "_jack_agentic_projected_kind": "A1"},
        {"role": "user", "content": "Make it luxury black, gold, and diamonds"},
    ]
    wire = k._coder_isolate_planner_request(h, k.STAGES["coder_planner"], source_history=h)
    assert [x["role"] for x in wire] == ["system", "system", "user"]
    assert memory in wire[1]["content"]
    assert "OLD_EXECUTOR_CODE" not in str(wire)
    assert "jack-turn-abc" in wire[1]["content"]
    assert wire[-1]["content"] == "Make it luxury black, gold, and diamonds"


@pytest.mark.parametrize("planner", ["flash", "thorough"])
def test_current_planner_tool_continuation_remains_complete(monkeypatch, tmp_path, planner):
    k = load(monkeypatch, tmp_path, planner=planner)
    h = [
        {"role": "user", "content": "Make the existing clock luxurious"},
        {"role": "assistant", "content": "",
         "_jack_internal_tool_exchange": True, "_jack_stage_key": "coder_planner",
         "tool_calls": [{"id": "inspection", "type": "function",
                         "function": {"name": "read",
                                      "arguments": '{"path":"index.html"}'}}]},
        {"role": "tool", "tool_call_id": "inspection",
         "_jack_internal_tool_exchange": True, "_jack_stage_key": "coder_planner",
         "content": "<html>old clock</html>"},
    ]
    prepared = k.OpenAICompatibleBackend(k.CFG)._stage_messages_for_profile(h, k.STAGES["coder_planner"])
    wire = k._coder_isolate_planner_request(prepared, k.STAGES["coder_planner"], source_history=h)
    assert [m["role"] for m in wire] == ["system", "user", "assistant", "tool"]
    assert wire[2]["tool_calls"][0]["id"] == wire[3]["tool_call_id"]
    assert "<html>old clock</html>" in wire[3]["content"]


@pytest.mark.parametrize("planner", ["flash", "thorough"])
def test_planner_stream_transport_sees_only_current_turn_and_prior_memory(monkeypatch, tmp_path, planner):
    async def run():
        k = load(monkeypatch, tmp_path, planner=planner)
        payloads = []

        def respond(request):
            payloads.append(json.loads(request.content))
            delta = {"choices": [{"index": 0, "delta": {"content": "Use a black and gold theme."},
                                  "finish_reason": "stop"}]}
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  text="data: " + json.dumps(delta) + "\n\ndata: [DONE]\n\n")
        backend = k.OpenAICompatibleBackend(k.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async def model():
            return "test-model"
        backend.resolve_model = model
        history = [
            {"role": "user", "content": "Build a clock in index.html"},
            {"role": "assistant", "content": "Clock built in index.html",
             "_jack_agentic_projected_kind": "M"},
            {"role": "assistant", "content": "OLD_CODE_OUTPUT",
             "_jack_agentic_projected_kind": "A1"},
            {"role": "user", "content": "Make it luxurious"},
        ]
        original = json.dumps(history, sort_keys=True)
        try:
            async for _ in backend.chat_stream(
                messages=history, secondary_system="untrusted caller system",
                profile=k.STAGES["coder_planner"], tools=None,
                tool_choice="none",
            ):
                pass
        finally:
            await backend._client.aclose()
        wire = payloads[0]["messages"]
        # The backend folds Jack-owned system records into the single leading
        # system message required by some OpenAI-compatible chat templates.
        assert [item["role"] for item in wire] == ["system", "user"]
        assert k.STAGES["coder_planner"].prompt in wire[0]["content"]
        assert "Clock built in index.html" in wire[0]["content"]
        assert wire[1] == {"role": "user", "content": "Make it luxurious"}
        assert "OLD_CODE_OUTPUT" not in str(wire)
        assert json.dumps(history, sort_keys=True) == original
    asyncio.run(run())
