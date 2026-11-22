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


def load(monkeypatch, tmp_path, profile="coder", planner="thorough"):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "Local Agentic (Preserve Thinking)")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    monkeypatch.setenv("JACK_CODER_PLANNER_PROFILE", planner)
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


def spec_text(objective="Build and verify the requested result"):
    return (f"Developer specification for: {objective}\n"
            "The finished work must satisfy every requirement in the request.\n"
            "Inspect existing files and prior checkpoints; preserve useful prior work.\n"
            "Verify saved output and actual behavior; distinguish tests from assumptions.")


def response(content=None, reasoning="PLANNER_R1"):
    if content is None:
        content = spec_text()
    return {"choices": [{"message": {"role": "assistant", "content": content,
                                     "reasoning_content": reasoning},
                         "finish_reason": "stop"}]}


def test_profile_isolated_and_reasoning_contract(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    assert k.AGENTIC_CODER_MODE and k.AGENTIC_MODE and not k.AGENTIC_THOROUGH_MODE
    assert k.STAGES["coder_planner"].thinking
    assert k.STAGES["coder_planner"].reasoning_effort == "xhigh"
    assert k.STAGES["coder_planner"].allow_tools
    assert k.STAGES["extended_initial"].thinking
    assert k.STAGES["extended_initial"].reasoning_effort == "xhigh"
    assert k.STAGES["extended_initial"].allow_tools
    assert k.STAGES["extended_reflection"].thinking
    assert not k.STAGES["extended_reflection"].allow_tools
    assert k.CODER_PLANNER_PROMPT.startswith(PREFIX)
    assert k.CODER_EXECUTOR_PROMPT.startswith(PREFIX)
    assert "read-only, non-mutating tools" in k.CODER_PLANNER_PROMPT
    assert "detailed natural-language developer specification" in k.CODER_PLANNER_PROMPT
    assert "You are Planner, the planning agent" in k.CODER_PLANNER_PROMPT
    assert "The workspace can be inspected when necessary" in k.CODER_PLANNER_PROMPT
    assert "for agentic work describe actions" in k.CODER_PLANNER_PROMPT
    assert "You've been provided a detailed, read-only developer specification prepared by Planner." in k.CODER_EXECUTOR_PROMPT
    assert "Do not implement artifacts" in k.CODER_PLANNER_PROMPT
    assert "read-only developer specification" in k.CODER_EXECUTOR_PROMPT
    assert "sole implementation and answer-authority" in k.CODER_EXECUTOR_PROMPT
    assert "Files in the workspace are previous checkpoints" in k.CODER_EXECUTOR_PROMPT
    assert k._runtime_identity_details()["flow"] == [
        "coder_planner", "extended_initial", "extended_reflection"
    ]


def test_coder_planner_flash_and_thorough_are_isolated(monkeypatch, tmp_path):
    thorough = load(monkeypatch, tmp_path, planner="thorough")
    flash = load(monkeypatch, tmp_path, planner="flash")
    a, b = thorough.STAGES["coder_planner"], flash.STAGES["coder_planner"]
    assert a.thinking is True and a.reasoning_effort == "xhigh"
    assert a.force_preserve_thinking is True
    assert a.prompt == thorough.CODER_PLANNER_PROMPT
    assert a.prompt.startswith(PREFIX)
    assert b.thinking is False and b.reasoning_effort is None
    assert b.force_preserve_thinking is False
    assert b.prompt == flash.CODER_PLANNER_FLASH_PROMPT
    assert b.prompt == a.prompt[len(flash.CODER_PLANNER_THOROUGH_PREFIX):]
    assert not b.prompt.startswith(PREFIX)
    assert b.prompt.startswith("You are Planner")
    assert "read-only, non-mutating tools" in b.prompt
    assert a.allow_tools and b.allow_tools
    assert thorough.CFG.coder_planner_profile == "thorough"
    assert flash.CFG.coder_planner_profile == "flash"
    assert flash._agentic_zero_reasoning(b) is True
    # Separate module loads create different StageProfile dataclass types.
    # Compare the actual stage configuration rather than Python type identity.
    assert vars(flash.STAGES["extended_initial"]) == vars(thorough.STAGES["extended_initial"])
    assert flash.STAGES["extended_reflection"].thinking is False
    assert thorough.STAGES["extended_reflection"].thinking is True
    assert flash.STAGES["extended_reflection"].allow_tools is False
    assert flash._agentic_zero_reasoning(flash.STAGES["extended_reflection"]) is True
    assert flash._coder_stage_sequence(None, [{"role": "user", "content": "Inspect workspace"}]) == [
        ("coder_planner", False), ("extended_initial", False), ("extended_reflection", False)
    ]
    assert flash._runtime_identity_details()["coder_planner_profile"] == "flash"
    assert flash._runtime_identity_details()["stage_controls"]["coder_planner"]["thinking"] is False
    assert thorough._runtime_identity_details()["stage_controls"]["coder_planner"]["thinking"] is True

    payload = {"model": "test-model"}
    backend = flash.OpenAICompatibleBackend(flash.CFG)
    backend._apply_qwen_controls(payload, b)
    assert payload["chat_template_kwargs"]["enable_thinking"] is False
    assert payload["chat_template_kwargs"]["preserve_thinking"] is False
    assert "reasoning_effort" not in payload["chat_template_kwargs"]
    assert payload["reasoning_effort"] == "none"
    assert payload["chat_template_kwargs"]["thinking_budget"] == 0
    assert "thinking_budget_tokens" not in payload

    # Coder Flash Stage 2 is also thinking-off; it must receive the same
    # generation budget while retaining its preserved R1 input.
    memory_payload = {"model": "test-model"}
    backend._apply_qwen_controls(memory_payload, flash.STAGES["extended_reflection"])
    assert memory_payload["chat_template_kwargs"]["thinking_budget"] == 0
    assert memory_payload["chat_template_kwargs"]["enable_thinking"] is False
    assert memory_payload["chat_template_kwargs"]["preserve_thinking"] is True

    payload_on = {"model": "test-model"}
    thorough.OpenAICompatibleBackend(thorough.CFG)._apply_qwen_controls(payload_on, a)
    assert payload_on["chat_template_kwargs"]["enable_thinking"] is True
    assert payload_on["chat_template_kwargs"]["reasoning_effort"] == "xhigh"
    assert payload_on["reasoning_effort"] == "xhigh"
    assert "thinking_budget" not in payload_on["chat_template_kwargs"]
    coder_payload = {"model": "test-model"}
    flash.OpenAICompatibleBackend(flash.CFG)._apply_qwen_controls(
        coder_payload, flash.STAGES["extended_initial"]
    )
    assert coder_payload["chat_template_kwargs"]["enable_thinking"] is True
    assert "thinking_budget" not in coder_payload["chat_template_kwargs"]

    with pytest.raises(RuntimeError, match="JACK_CODER_PLANNER_PROFILE"):
        load(monkeypatch, tmp_path, planner="invalid")


def test_coder_planner_actual_wire_prompt_and_memory_thinking(monkeypatch, tmp_path):
    async def run():
        for selected in ("flash", "thorough"):
            k = load(monkeypatch, tmp_path, planner=selected)
            payloads = []
            def reply(request):
                payloads.append(json.loads(request.content))
                return httpx.Response(200, json=response("Planner delivered specification"))
            backend = k.OpenAICompatibleBackend(k.CFG)
            await backend._client.aclose()
            backend._client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
            async def model():
                return "test-model"
            backend.resolve_model = model
            try:
                h = [{"role": "system", "content": "External Pi instructions"},
                     {"role": "user", "content": "Verify workspace is empty"}]
                await backend.chat(
                    messages=h, secondary_system="", profile=k.STAGES["coder_planner"],
                    tools=k._coder_planner_tools([
                        {"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}},
                        {"type": "function", "function": {"name": "write", "parameters": {"type": "object"}}},
                    ]),
                    tool_choice="auto",
                )
                assert len(payloads) == 1
                wire = payloads[0]
                assert wire["messages"][0]["role"] == "system"
                assert wire["messages"][0]["content"].startswith(k.STAGES["coder_planner"].prompt)
                assert wire["messages"][0]["content"] == k.STAGES["coder_planner"].prompt
                assert "read-only, non-mutating tools" in wire["messages"][0]["content"]
                assert wire["messages"][-1]["content"] == "Verify workspace is empty"
                assert sum(x["role"] == "user" for x in wire["messages"]) == 1
                assert "External Pi instructions" not in str(wire["messages"])
                assert [t["function"]["name"] for t in wire["tools"]] == ["read"]
                assert wire["chat_template_kwargs"]["enable_thinking"] is (selected == "thorough")
                assert wire["reasoning_effort"] == ("none" if selected == "flash" else "xhigh")
                if selected == "flash":
                    assert wire["chat_template_kwargs"]["thinking_budget"] == 0
                else:
                    assert "thinking_budget" not in wire["chat_template_kwargs"]
                if selected == "flash":
                    assert wire["messages"][0]["content"].startswith("You are Planner")
                    assert k.CODER_PLANNER_THOROUGH_PREFIX not in str(wire["messages"])
                    assert wire["chat_template_kwargs"]["preserve_thinking"] is False
                else:
                    assert wire["messages"][0]["content"].startswith(PREFIX)
                assert k.STAGES["extended_reflection"].thinking is (selected == "thorough")
                assert not k.STAGES["extended_reflection"].allow_tools
                assert k.STAGES["extended_initial"].thinking is True
                assert k.STAGES["extended_initial"].reasoning_effort == "xhigh"
                h2 = [{"role": "user", "content": "Verify workspace is empty"}]
                k._coder_append_plan(h2, response("Check the directory without modifications"))
                h2.append({"role": "assistant", "content": "Verified empty",
                           "_jack_extended_candidate_response": True,
                           "reasoning_content": "Executor confirmed the CWD via pwd and ls"})
                assert any(e.get("type") == "reasoning_segment"
                           and "Executor confirmed" in e.get("content", "")
                           for e in k._agentic_stage2_chronological_source(h2))
            finally:
                await backend._client.aclose()
    asyncio.run(run())



def test_planner_rejected_template_artifacts_are_not_replayed(monkeypatch, tmp_path):
    """Regression for the exact thinking-OFF checkpoint in LM Studio logs."""
    k = load(monkeypatch, tmp_path, planner="flash")
    original_text = "assistant\n\n<think>\n\n</think>"
    helpful_text = original_text + "\nInspect the directory; do not modify it."
    h = [{"role": "user", "content": "Verify the directory is empty"},
         {"role": "assistant", "content": original_text,
          "_jack_internal_tool_validation_checkpoint": True},
         {"role": "assistant", "content": helpful_text,
          "_jack_internal_tool_validation_checkpoint": True},
         k._tool_rejection_notice(["Planner tool call 0: tool is not read-only"],
                                  k.STAGES["coder_planner"].name)]
    original = json.dumps(h, sort_keys=True)
    backend = k.OpenAICompatibleBackend(k.CFG)
    prepared = backend._stage_messages_for_profile(h, k.STAGES["coder_planner"])
    request = k._coder_isolate_planner_request(prepared, k.STAGES["coder_planner"])
    assert request[0] == {"role": "system", "content": k.CODER_PLANNER_FLASH_PROMPT}
    assert sum(x["role"] == "system" for x in request) == 1
    assert sum(x["role"] == "user" for x in request) == 1
    assert request[-2]["content"] == "Inspect the directory; do not modify it."
    assert request[-1]["role"] == "assistant"
    assert all("<think>" not in str(m.get("content")) for m in request)
    assert all(m.get("content") != "assistant" for m in request)
    assert json.dumps(h, sort_keys=True) == original

    # Sanitizing is deliberately scoped: do not rewrite quoted examples,
    # substantive analysis, or the user-authorized developer memo.
    memo = "To: Coder\nFrom: Planner\nSubject: Workspace Verification"
    assert k._coder_planner_checkpoint_text(memo) == memo
    assert k._coder_planner_checkpoint_text("assistant\nRelevant spec") == "assistant\nRelevant spec"
    assert k._coder_planner_checkpoint_text("<think>real content</think>") == "<think>real content</think>"
    assert k._coder_unverified_observations(helpful_text) == "Inspect the directory; do not modify it."
    assert k._coder_unverified_observations(original_text) == ""
    handoff = k._coder_planner_host_handoff_result(h)
    assert "Inspect the directory; do not modify it." in handoff["choices"][0]["message"]["content"]
    assert original_text not in handoff["choices"][0]["message"]["content"]


def test_coder_force_preserve_thinking_with_global_setting_disabled(monkeypatch, tmp_path):
    async def run():
        monkeypatch.setenv("JACK_PRESERVE_THINKING", "0")
        for selected in ("flash", "thorough"):
            k = load(monkeypatch, tmp_path, planner=selected)
            assert k.CFG.preserve_thinking is False
            assert k.STAGES["extended_initial"].thinking is True
            assert k.STAGES["extended_initial"].force_preserve_thinking is True
            assert k.STAGES["coder_planner"].thinking is (selected == "thorough")
            assert k.STAGES["extended_reflection"].thinking is (selected == "thorough")
            payloads = []
            def reply(request):
                payloads.append(json.loads(request.content))
                return httpx.Response(200, json=response("Coder completed task"))
            backend = k.OpenAICompatibleBackend(k.CFG)
            await backend._client.aclose()
            backend._client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
            async def model():
                return "test-model"
            backend.resolve_model = model
            try:
                history = [{"role": "user", "content": "Verify the workspace is empty"}]
                k._coder_append_plan(history, response("Verify without modifying the workspace"))
                await backend.chat(
                    messages=history, secondary_system="", profile=k.STAGES["extended_initial"],
                    tools=[], tool_choice="none",
                )
                assert len(payloads) == 1
                flags = payloads[0]["chat_template_kwargs"]
                assert flags["enable_thinking"] is True
                assert flags["preserve_thinking"] is True
                assert flags["reasoning_effort"] == "xhigh"
                assert payloads[0]["reasoning_effort"] == "xhigh"
                assert any("JACK CODER DEVELOPER SPEC SHEET" in str(m.get("content"))
                           for m in payloads[0]["messages"])
            finally:
                await backend._client.aclose()
    asyncio.run(run())

def test_zero_reasoning_budget_llamacpp_and_nonflash_profiles(monkeypatch, tmp_path):
    from dataclasses import replace

    for chosen, selected_stages in (
        ("flash", ("coder_planner", "extended_reflection")),
        ("thorough", ()),
    ):
        k = load(monkeypatch, tmp_path, planner=chosen)
        backend = k.OpenAICompatibleBackend(replace(k.CFG, backend_profile="llamacpp"))
        for key in ("coder_planner", "extended_initial", "extended_reflection"):
            p = {"model": "gpt-oss-20b"}
            profile = k.STAGES[key]
            backend._apply_qwen_controls(p, profile)
            if key in selected_stages:
                assert p["thinking_budget_tokens"] == 0
                assert p.get("chat_template_kwargs", {}).get("thinking_budget") == 0
                assert p["chat_template_kwargs"]["enable_thinking"] is False
            else:
                assert "thinking_budget_tokens" not in p
                assert "thinking_budget" not in p.get("chat_template_kwargs", {})

    # A stage which enables thinking is never assigned a zero budget,
    # even if its display name is a flash-stage name.
    k = load(monkeypatch, tmp_path, planner="flash")
    p = {"model": "gpt-oss-20b"}
    k.OpenAICompatibleBackend(k.CFG)._apply_qwen_controls(
        p, replace(k.STAGES["coder_planner"], thinking=True)
    )
    assert "thinking_budget" not in p["chat_template_kwargs"]


def test_planner_internal_rejections_cannot_compete_with_user(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, planner="flash")
    internal = k._tool_rejection_notice(
        ["Planner tool call 0: shell command is outside the inspection-only grammar"],
        k.STAGES["coder_planner"].name,
    )
    assert "single read-only inspection command" in internal["content"]
    assert "'ls -la' or 'pwd'" in internal["content"]
    h = [
        {"role": "system", "content": "Pi caller system must be filtered"},
        {"role": "user", "content": "Verify the workspace is empty"},
        {"role": "assistant", "content": "The directory needs inspection",
         "_jack_internal_tool_validation_checkpoint": True},
        internal,
    ]
    original = json.dumps(h, sort_keys=True)
    backend = k.OpenAICompatibleBackend(k.CFG)
    prepared = backend._stage_messages_for_profile(h, k.STAGES["coder_planner"])
    projected = k._coder_isolate_planner_request(prepared, k.STAGES["coder_planner"])
    assert sum(item["role"] == "user" for item in projected) == 1
    assert projected[0]["content"] == k.CODER_PLANNER_FLASH_PROMPT
    assert projected[-1]["role"] == "assistant"
    assert "not a user request" in projected[-1]["content"]
    assert "single read-only inspection command" in projected[-1]["content"]
    assert "Pi caller system must be filtered" not in str(projected)
    assert projected[-2]["role"] == "assistant"
    assert json.dumps(h, sort_keys=True) == original
    # Model-visible validation instructions do not alter canonical role or evidence.
    assert internal["role"] == "user"
    assert k._coder_planner_safe_inspection_command("ls -la")
    assert k._coder_planner_safe_inspection_command("pwd")
    assert k._coder_planner_safe_inspection_command("pwd && ls -la")


def test_planner_protocol_recovery_is_host_owned_with_single_user(monkeypatch, tmp_path):
    for planner in ("flash", "thorough"):
        k = load(monkeypatch, tmp_path, planner=planner)
        note = {
            "role": "user",
            "content": (
                "Jack protocol continuation: The prior backend generation "
                "produced neither a final answer nor a structured executable "
                "tool call. Continue from the completed tool results."
            ),
            "_jack_internal_protocol_recovery": True,
        }
        h = [
            {"role": "system", "content": "External caller should be removed"},
            {"role": "user", "content": "Verify that the workspace is empty"},
            {"role": "assistant", "content": "", "_jack_internal_tool_validation_checkpoint": True},
            {"role": "tool", "tool_call_id": "r1", "content": "only . and .."},
            note,
        ]
        frozen = json.dumps(h, sort_keys=True)
        backend = k.OpenAICompatibleBackend(k.CFG)
        prepared = backend._stage_messages_for_profile(h, k.STAGES["coder_planner"])
        projected = k._coder_isolate_planner_request(prepared, k.STAGES["coder_planner"])
        assert projected[0]["content"] == k.STAGES["coder_planner"].prompt
        assert [x["role"] for x in projected].count("user") == 1
        assert [x["role"] for x in projected].count("tool") == 1
        assert "only . and .." in str(projected)
        assert any(
            x["role"] == "assistant" and
            "Jack internal recovery feedback (not a user request or Planner answer):" in str(x.get("content")) and
            "Jack protocol continuation:" in str(x.get("content"))
            for x in projected
        )
        assert "External caller should be removed" not in str(projected)
        assert all(not (x["role"] == "user" and "Jack protocol continuation" in str(x.get("content"))) for x in projected)
        assert json.dumps(h, sort_keys=True) == frozen


@pytest.mark.parametrize("planner", ["flash", "thorough"])
def test_planner_spec_streams_as_advisory_reasoning_without_answer_contamination(monkeypatch, tmp_path, planner):
    async def run():
        k = load(monkeypatch, tmp_path, planner=planner)
        calls = []
        parts = ["Planner developer specification: ", "verify the directory ", "is empty."]
        class Backend:
            async def chat_stream(self, *, messages, secondary_system, profile,
                                  tools=None, tool_choice=None):
                calls.append(profile.name)
                if profile.name == "Agentic Coder Planner":
                    assert profile.thinking is (planner == "thorough")
                    assert profile.prompt.startswith("You are Planner") if planner == "flash" else True
                    assert [t["function"]["name"] for t in tools] == ["read"]
                    if planner == "thorough":
                        yield {"choices": [{"index": 0, "delta": {
                            "reasoning_content": "PLANNER_NATIVE_REASONING_MARKER"}, "finish_reason": None}]}
                    for part in parts:
                        yield {"choices": [{"index": 0, "delta": {"content": part}, "finish_reason": None}]}
                elif profile.name == "Agentic native pass 1":
                    assert any(m.get("_jack_coder_plan") for m in messages)
                    yield {"choices": [{"index": 0, "delta": {"content": "Verified empty."}, "finish_reason": None}]}
                elif profile.name == "Agentic native pass 2":
                    assert not profile.allow_tools
                    yield {"choices": [{"index": 0, "delta": {"content": "Workspace check completed."}, "finish_reason": None}]}
                else:
                    raise AssertionError("Unexpected phase")
                yield {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                       "usage": {"prompt_tokens": 20, "completion_tokens": 15, "total_tokens": 35}}
        kernel = k.JackQwenKernel(Backend(), k.CFG)
        available = [{"type": "function", "function": {"name": "read",
                     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}]
        frames = [b.decode("utf-8") async for b in kernel.stream({
            "messages": [{"role": "user", "content": "Verify the workspace is empty"}],
            "tools": available, "stream": True,
        })]
        deltas = []
        for frame in frames:
            for line in frame.splitlines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    deltas.append((json.loads(line[6:]).get("choices") or [{}])[0].get("delta", {}))
        assert sum("[CODER PLANNER — SPEC SHEET]" in d.get("reasoning_content", "") for d in deltas) == 1
        assert all(any(part == d.get("reasoning_content") for d in deltas) for part in parts)
        assert all(not any(part in d.get("content", "") for part in parts) for d in deltas)
        if planner == "thorough":
            assert any(d.get("reasoning_content") == "PLANNER_NATIVE_REASONING_MARKER" for d in deltas)
            assert not any("PLANNER_NATIVE_REASONING_MARKER" in d.get("content", "") for d in deltas)
        else:
            assert not any("PLANNER_NATIVE_REASONING_MARKER" in str(d) for d in deltas)
        reasoning_chunks = [d.get("reasoning_content", "") for d in deltas]
        plan_idx = reasoning_chunks.index(parts[0])
        assert reasoning_chunks[plan_idx:plan_idx + len(parts)] == parts
        assert not any("Planner developer specification:" in d.get("content", "") for d in deltas)
        assert plan_idx < next(i for i, d in enumerate(deltas) if "Verified empty." in str(d))
        assert "Workspace check completed." in "".join(str(d) for d in deltas)
        assert calls == ["Agentic Coder Planner", "Agentic native pass 1", "Agentic native pass 2"]
        assert sum("data: [DONE]" in frame for frame in frames) == 1
    asyncio.run(run())


def test_planner_read_only_vision_and_explicit_actual_tool_contract(monkeypatch, tmp_path):
    for setting in ("flash", "thorough"):
        k = load(monkeypatch, tmp_path, planner=setting)
        offered = [
            {"type": "function", "function": {"name": "read"}},
            {"type": "function", "function": {"name": "describe_image"}},
            {"type": "function", "function": {"name": "pwsh-get-job"}},
            {"type": "function", "function": {"name": "write"}},
            {"type": "function", "function": {"name": "powershell"}},
            {"type": "function", "function": {"name": "pwsh-start-job"}},
        ]
        allowed = k._coder_planner_tools(offered)
        assert [x["function"]["name"] for x in allowed] == ["read", "describe_image", "pwsh-get-job"]
        assert [x["function"]["name"] for x in offered] == [
            "read", "describe_image", "pwsh-get-job", "write", "powershell", "pwsh-start-job"
        ]
        wire = k._coder_isolate_planner_request(
            [{"role": "system", "content": "Caller must not alter Planner"},
             {"role": "user", "content": "Create a text file about drifting"}],
            k.STAGES["coder_planner"], tools=allowed,
        )
        assert wire[0]["content"] == k.STAGES["coder_planner"].prompt
        assert [msg["role"] for msg in wire] == ["system", "user"]
        assert "read-only, non-mutating tools" in wire[0]["content"]
        assert "Do not implement artifacts" in wire[0]["content"]
        assert "Caller must not alter Planner" not in str(wire)
        assert sum(m["role"] == "user" for m in wire) == 1


def test_repeated_planner_shell_denials_do_not_abort_or_discard_coder_task(monkeypatch, tmp_path):
    async def run():
        for mode in ("flash", "thorough"):
            k = load(monkeypatch, tmp_path, planner=mode)
            sequence = []
            request = "Create drifting.txt describing the sport of drifting"
            class Backend:
                async def chat_stream(self, *, messages, secondary_system, profile,
                                      tools=None, tool_choice=None):
                    sequence.append(profile.name)
                    if profile.name == "Agentic Coder Planner":
                        n = sum(x == "Agentic Coder Planner" for x in sequence)
                        assert n <= 3
                        assert profile.thinking is (mode == "thorough")
                        if n <= 2:
                            assert [x["function"]["name"] for x in tools] == ["bash", "describe_image"]
                        else:
                            assert tools == []
                            assert tool_choice == "none"
                        yield {"choices": [{"index": 0, "delta": {
                            "tool_calls": [{"index": 0, "id": f"forbidden-{n}",
                                            "type": "function", "function": {
                                                "name": "bash",
                                                "arguments": '{"command":"cat > drifting.txt"}'}}]},
                             "finish_reason": None}]}
                        yield {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}
                        return
                    if profile.name == "Agentic native pass 1":
                        assert profile.thinking is True
                        assert any(m.get("_jack_coder_plan") for m in messages)
                        plan = next(m for m in messages if m.get("_jack_coder_plan"))
                        assert request in plan["content"]
                        assert "Jack host recovery handoff to Coder" in plan["content"]
                        assert plan["_jack_coder_goal_fallback"] is True
                        assert [x["function"]["name"] for x in tools] == ["bash", "describe_image", "write"]
                        yield {"choices": [{"index": 0, "delta": {"content": "Coder received the task."}, "finish_reason": None}]}
                        yield {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
                        return
                    if profile.name == "Agentic native pass 2":
                        assert profile.thinking is (mode == "thorough")
                        assert not profile.allow_tools
                        yield {"choices": [{"index": 0, "delta": {"content": "Coder handoff preserved."}, "finish_reason": None}]}
                        yield {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
                        return
                    raise AssertionError("Unexpected stage: " + profile.name)
            kernel = k.JackQwenKernel(Backend(), k.CFG)
            offered = [{"type": "function", "function": {"name": name,
                       "parameters": {"type": "object", "properties": {}}}}
                       for name in ("bash", "describe_image", "write")]
            frames = [x.decode("utf-8") async for x in kernel.stream({
                "messages": [{"role": "user", "content": request}],
                "tools": offered, "stream": True,
            })]
            output = "".join(frames)
            assert "Jack host recovery handoff to Coder" in output
            assert "Coder received the task." in output
            assert "[CODER PLANNER — SPEC CAPTURED AND DELIVERED TO CODER]" not in output
            assert "[CODER PLANNER — DEVELOPER SPECIFICATION]" not in output
            assert "[JACK TOOL ACTION REJECTED BEFORE EXECUTION" not in output
            assert "[JACK PLANNER TOOL REJECTED EARLY" not in output
            assert sequence == [
                "Agentic Coder Planner", "Agentic Coder Planner",
                "Agentic Coder Planner", "Agentic native pass 1",
                "Agentic native pass 2"
            ]
            assert "forbidden-1" not in output and "forbidden-2" not in output
    asyncio.run(run())


def test_planner_stable_prompt_and_preserved_flash_thorough_contract(monkeypatch, tmp_path):
    for selected in ("flash", "thorough"):
        k = load(monkeypatch, tmp_path, planner=selected)
        base = k.CODER_PLANNER_PROMPT[len(k.CODER_PLANNER_THOROUGH_PREFIX):]
        assert k.CODER_PLANNER_FLASH_PROMPT == base
        assert base.startswith("You are Planner, the planning agent")
        assert len(base) < 2400
        assert "Prior working knowledge" in base
        assert "read-only, non-mutating tools" in base
        assert k.STAGES["coder_planner"].thinking is (selected == "thorough")
        assert k.STAGES["extended_initial"].thinking is True
        assert k.STAGES["extended_reflection"].thinking is (selected == "thorough")
        source = [{"role": "user", "content": "Make a cuckoo SVG"}]
        first = k._coder_isolate_planner_request(source, k.STAGES["coder_planner"],
                    tools=[{"type":"function","function":{"name":"read"}}])
        second = k._coder_isolate_planner_request(source, k.STAGES["coder_planner"],
                    tools=[{"type":"function","function":{"name":"read"}},
                           {"type":"function","function":{"name":"describe_image"}}])
        assert first == second == [{"role":"system","content":k.STAGES["coder_planner"].prompt},
                                    {"role":"user","content":"Make a cuckoo SVG"}]
        note = k._tool_rejection_notice(
            ["Planner tool call 0: tool is not read-only"], k.STAGES["coder_planner"].name)
        backend = k.OpenAICompatibleBackend(k.CFG)
        prepared = backend._stage_messages_for_profile(source + [note], k.STAGES["coder_planner"])
        resumed = k._coder_isolate_planner_request(prepared, k.STAGES["coder_planner"])
        assert resumed[:len(first)] == first
        assert resumed[-1]["role"] == "assistant"


def test_planner_read_only_unchanged_evidence_cycle_detection(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role":"user","content":"Create SVG cuckoo clock"}]
    read = {"id":"new","type":"function","function":{
        "name":"read","arguments":'{"path":"cuckoo_clock.svg"}'}}
    listing = {"id":"new","type":"function","function":{
        "name":"bash","arguments":'{"command":"ls -la"}'}}
    def record(tool, ident, result, outcome):
        call = json.loads(json.dumps(tool))
        call["id"] = ident
        h.append({"role":"assistant","content":"","_jack_stage_key":"coder_planner",
                  "_jack_internal_tool_exchange":True,"tool_calls":[call]})
        h.append({"role":"tool","tool_call_id":ident,"content":result,
                  "_jack_tool_outcome":outcome,"_jack_stage_key":"coder_planner",
                  "_jack_internal_tool_exchange":True})
    # A single observation is not enough; repeated read and ls must return
    # *identical* evidence before the next repeat can be suppressed.
    record(read,"r1","ENOENT","FAILED")
    record(listing,"l1","only . and ..","SUCCESS")
    assert k._coder_planner_inspection_cycle(h,[read]) is None
    record(read,"r2","ENOENT","FAILED")
    record(listing,"l2","only . and ..","SUCCESS")
    assert k._coder_planner_inspection_cycle(h,[read]) == 2
    assert k._coder_planner_inspection_cycle(h,[listing]) is None
    assert k._coder_planner_inspection_cycle(h,[{"id":"x","type":"function",
        "function":{"name":"read","arguments":'{"path":"other.svg"}'}}]) is None
    record(read,"r3","FILE EXISTS","SUCCESS")
    assert k._coder_planner_inspection_cycle(h,[listing]) is None
    assert k._coder_planner_inspection_cycle(h,[{"id":"w","type":"function",
        "function":{"name":"write","arguments":'{"path":"x"}'}}]) is None
    duplicate = k._coder_planner_duplicate_inspection_history(h,{},2)
    assert duplicate[-1]["_jack_internal_coder_planner_repeated_inspection"]
    assert k._coder_planner_tools_for_attempt(duplicate,[{"type":"function",
        "function":{"name":"read"}}]) == []
    assert h[0]["content"] == "Create SVG cuckoo clock"


def test_planner_partial_output_survives_fallback(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role":"user","content":"Build nice cuckoo clock SVG"},
         {"role":"assistant","content":"Use an alpine roof and hanging weights",
          "_jack_internal_tool_validation_checkpoint":True},
         {"role":"assistant","content":"Use intricate wood grain",
          "_jack_internal_tool_validation_checkpoint":True}]
    result = k._coder_planner_host_handoff_result(h, "Include a carved bird and Roman numerals")
    text = result["choices"][0]["message"]["content"]
    assert "Build nice cuckoo clock SVG" in text
    assert "Use an alpine roof and hanging weights" in text
    assert "Use intricate wood grain" in text
    assert "Include a carved bird and Roman numerals" in text
    assert result["choices"][0]["message"]["_jack_coder_planner_host_fallback"]
    assert h[1]["content"] == "Use an alpine roof and hanging weights"


def test_early_planner_mutation_abort_preserves_partial_spec(monkeypatch, tmp_path):
    async def run():
        k=load(monkeypatch,tmp_path,planner="flash")
        calls=[]
        class Backend:
            async def chat_stream(self, *,messages,secondary_system,profile,tools=None,tool_choice=None):
                calls.append(profile.name)
                if profile.name == "Agentic Coder Planner":
                    n=calls.count(profile.name)
                    if n==1:
                        yield {"choices":[{"index":0,"delta":{"content":"Beautiful wooden roof"},"finish_reason":None}]}
                        yield {"choices":[{"index":0,"delta":{"tool_calls":[{
                            "index":0,"id":"blocked-write","type":"function",
                            "function":{"name":"write","arguments":'{"path":"cuckoo.svg","content":"'}}]},
                            "finish_reason":None}]}
                        raise AssertionError("Streaming must stop before more write content")
                    assert n==2
                    assert any(m.get("_jack_internal_tool_validation_rejection") for m in messages)
                    yield {"choices":[{"index":0,"delta":{"content":"Plan the SVG in Coder"},"finish_reason":None}]}
                elif profile.name == "Agentic native pass 1":
                    assert any(m.get("_jack_coder_plan") for m in messages)
                    yield {"choices":[{"index":0,"delta":{"content":"Created file"},"finish_reason":None}]}
                elif profile.name == "Agentic native pass 2":
                    yield {"choices":[{"index":0,"delta":{"content":"SVG created"},"finish_reason":None}]}
                else:
                    raise AssertionError(profile.name)
                yield {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}
        kernel=k.JackQwenKernel(Backend(),k.CFG)
        frames=[x.decode() async for x in kernel.stream({
            "messages":[{"role":"user","content":"Create cuckoo clock SVG"}],
            "tools":[{"type":"function","function":{"name":"read"}},
                     {"type":"function","function":{"name":"write"}}],"stream":True})]
        output="".join(frames)
        assert "Plan the SVG in Coder" in output
        assert "Created file" in output
        assert "[JACK PLANNER TOOL REJECTED EARLY" not in output
        assert "[JACK TOOL ACTION REJECTED BEFORE EXECUTION" not in output
        assert calls==["Agentic Coder Planner","Agentic Coder Planner",
                       "Agentic native pass 1","Agentic native pass 2"]
    asyncio.run(run())


def test_coder_planner_cli_selection_and_child_environment(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    cfg = dict(k.CLI_DEFAULTS)
    output = []
    monkeypatch.setattr(k, "_ansi_rgb", lambda text, *args, **kwargs: text)
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: output.append(" ".join(map(str, args))))
    answers = iter(["6", "5", "1"])
    monkeypatch.setattr(k, "_cli_input", lambda _: next(answers))
    k._edit_reasoning(cfg)
    assert "  1) Flash" in output and "  2) Thorough" in output
    assert not any("omit the xhigh reasoning instruction" in row for row in output)
    assert not any("retain the xhigh reasoning instruction" in row for row in output)
    assert cfg["agentic_profile"] == "coder"
    assert cfg["coder_planner_profile"] == "flash"
    assert k._config_to_env(cfg)["JACK_CODER_PLANNER_PROFILE"] == "flash"
    answers = iter(["6", "5", "2"])
    k._edit_reasoning(cfg)
    assert cfg["coder_planner_profile"] == "thorough"
    assert k._config_to_env(cfg)["JACK_CODER_PLANNER_PROFILE"] == "thorough"


def test_plan_owned_once_and_preserved_for_memory(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Build and test a website."}]
    initial = json.dumps(h)
    k._coder_append_plan(h, response())
    assert json.dumps(h[:1]) == initial
    assert k.active_response_target(h)["content"] == "Build and test a website."
    assert k._coder_has_plan(h)
    assert h[-1]["role"] == "assistant"
    assert "reasoning_content" not in h[-1]  # Planner R1 retired after capture
    assert h[-1]["content"] == spec_text()
    assert h[-1]["_jack_coder_goal_fallback"] is False
    with pytest.raises(k.ForensicConflict):
        k._coder_append_plan(h, response("Replayed"))
    h.append({"role": "assistant", "content": "Done",
              "_jack_extended_candidate_response": True,
              "reasoning_content": "EXECUTOR_R1"})
    events = k._agentic_stage2_chronological_source(h)
    assert not any(e.get("type") == "planner_plan" for e in events)
    assert not any(e.get("content") == "PLANNER_R1" for e in events)
    assert any(e.get("type") == "reasoning_segment" and
               e["content"] == "EXECUTOR_R1" and e["phase"] == "executor"
               for e in events)
    view = k._agentic_stage2_test_history(h, k.STAGES["extended_reflection"])
    assert "PLANNER_R1" not in str(view)


def test_imperfect_planner_prose_is_preserved_without_brittle_json_validation(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    for raw in ("{bad json}", "A detailed explanation of the desired end state."):
        h = [{"role": "user", "content": "Fix code"}]
        k._coder_append_plan(h, response(raw))
        assert h[-1]["content"] == raw
        assert h[-1]["_jack_coder_goal_fallback"] is False
    h = [{"role": "user", "content": "Fix code"}]
    k._coder_append_plan(h, response(""))
    assert h[-1]["content"] == "Fix code"
    assert h[-1]["_jack_coder_goal_fallback"] is True
    h = [{"role": "user", "content": "Fix code"}]
    k._coder_append_plan(h, {"choices": [{
        "finish_reason": "tool_calls",
        "message": {"content": "Important partial spec", "tool_calls": [{"id": "one"}]}
    }]})
    assert h[-1]["content"] == "Important partial spec"
    assert h[-1]["_jack_coder_planner_incomplete"] is True
    assert k._coder_stage_sequence("extended_initial", h)[0][0] == "extended_initial"


def test_imperfect_planner_output_retains_useful_observations(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    original = "User requests a saved SVG in the workspace"
    raw = ("Expected end state: an SVG saved in the specified workspace.\n"
           "<|tool_call>call:bash{command:'delete all'}<|tool_call|>\n"
           "Verify that the SVG file exists and is readable.")
    h = [{"role": "user", "content": original}]
    k._coder_append_plan(h, response(raw))
    assert h[-1]["_jack_coder_original_planner_output"] == raw
    assert h[-1]["_jack_coder_original_planner_output_sha256"] == k._sha256_text(raw)
    safe = h[-1]["content"]
    assert "Expected end state" in safe
    assert "exists and is readable" in safe
    assert "<|tool_call" not in safe
    assert "delete all" not in safe
    backend = k.OpenAICompatibleBackend(k.CFG)
    wire = backend._stage_messages_for_profile(h, k.STAGES["extended_initial"])
    assert all(raw not in str(item) for item in wire)
    assert any("Expected end state" in str(item) for item in wire)


def test_incomplete_planner_preserves_partial_work_as_unverified_data(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    request = "Make the clock work"
    raw = spec_text(request) + "\nFurther information required from workspace."
    h = [{"role": "user", "content": request}]
    k._coder_append_plan(h, {"choices": [{
        "finish_reason": "length",
        "message": {"role": "assistant", "content": raw, "reasoning_content": "WORK"}
    }]})
    entry = h[-1]
    assert entry["_jack_coder_planner_incomplete"] is True
    assert entry["_jack_coder_goal_fallback"] is False
    assert entry["_jack_coder_original_planner_output"] == raw
    assert entry["content"] == raw
    assert k._coder_has_plan(h)



@pytest.mark.parametrize("planner_profile", ["flash", "thorough"])
def test_planner_reasoning_retired_immediately_but_spec_and_tool_evidence_survive(monkeypatch, tmp_path, planner_profile):
    k = load(monkeypatch, tmp_path, planner=planner_profile)
    h = [{"role": "user", "content": "Inspect and implement"}]
    h.extend([
        {"role": "assistant", "content": "", "_jack_internal_tool_exchange": True,
         "_jack_stage_key": "coder_planner",
         "reasoning_content": "PLANNER_TOOL_R1",
         "tool_calls": [{"id": "plan-read", "type": "function",
                         "function": {"name": "read", "arguments": '{"path":"clock.html"}'}}]},
        {"role": "tool", "tool_call_id": "plan-read", "name": "read",
         "content": "original workspace evidence", "_jack_internal_tool_exchange": True},
    ])
    k._coder_append_plan(h, response("Implement a working clock.", "PLANNER_FINAL_R1"))
    plan = h[-1]
    assert plan["content"] == "Implement a working clock."
    assert plan["_jack_coder_original_planner_output"] == plan["content"]
    assert all("PLANNER_TOOL_R1" not in str(item) and "PLANNER_FINAL_R1" not in str(item)
               for item in h)
    assert h[1]["tool_calls"][0]["id"] == "plan-read"
    assert h[2]["content"] == "original workspace evidence"
    assert k._coder_has_plan(h)
    assert k._coder_retire_planner_reasoning(h) == 0  # idempotent
    backend = k.OpenAICompatibleBackend(k.CFG)
    wire = backend._stage_messages_for_profile(h, k.STAGES["extended_initial"])
    assert any("Implement a working clock." in str(item) for item in wire)
    assert all("PLANNER_TOOL_R1" not in str(item) for item in wire)


@pytest.mark.parametrize("planner_profile", ["flash", "thorough"])
def test_coder_stage2_uses_coder_outcome_without_planner_reasoning(monkeypatch, tmp_path, planner_profile):
    k = load(monkeypatch, tmp_path, planner=planner_profile)
    h = [{"role": "user", "content": "Build clock"}]
    k._coder_append_plan(h, response("SPEC_UNIQUE: verify saved clock.", "PLANNER_R1_UNIQUE"))
    assert k._coder_stage2_spec_source(h) == "SPEC_UNIQUE: verify saved clock."
    assert "reasoning_content" not in h[-1]
    assert "reasoning" not in h[-1]
    h.append({"role": "assistant", "content": "CODER_COMPLETED",
              "reasoning_content": "CODER_R1_UNIQUE",
              "_jack_extended_candidate_response": True})
    events = k._agentic_stage2_chronological_source(h)
    assert any(e.get("content") == "CODER_R1_UNIQUE" for e in events)
    assert all("PLANNER_R1_UNIQUE" not in str(e) for e in events)
    assert k._coder_stage2_spec_source(h) == "SPEC_UNIQUE: verify saved clock."
    # The source is read-only; no spec duplication into the canonical history.
    assert sum(bool(item.get("_jack_coder_plan")) for item in h) == 1


def test_goal_checkpoint_persists_after_commit_without_becoming_memory(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    monkeypatch.setattr(k, "_config_dir", lambda: tmp_path)
    h = [{"role": "user", "content": "Save the requested SVG",
          "_jack_agentic_turn_id": "jack-turn-test-goal-checkpoint"}]
    raw = "Expected result includes a saved, readable SVG."
    k._coder_append_plan(h, response(raw))
    target = k._coder_preserve_goal_artifact(h)
    assert target is not None and target.exists()
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["work_id"] == "jack-turn-test-goal-checkpoint"
    assert saved["schema"] == "jack.coder.spec_checkpoint.v2"
    assert saved["spec_text"] == raw
    assert saved["spec_sha256"] == k._sha256_text(raw)
    assert saved["original_planner_output"] == raw
    assert saved["used_request_fallback"] is False
    assert "PLANNER_R1" not in target.read_text(encoding="utf-8")
    h.clear()
    assert target.exists()
    assert k._coder_preserve_goal_artifact(h) is None


def test_goal_checkpoint_io_failure_is_fail_open(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    monkeypatch.setattr(k, "_config_dir", lambda: tmp_path / "does-not-matter")
    h = [{"role": "user", "content": "Make a working clock",
          "_jack_agentic_turn_id": "jack-turn-no-write"}]
    k._coder_append_plan(h, response())
    def cannot_write(*args, **kwargs):
        raise OSError("storage unavailable")
    monkeypatch.setattr(k.Path, "mkdir", cannot_write)
    assert k._coder_preserve_goal_artifact(h) is None
    assert k._coder_has_plan(h)
    assert h[-1]["content"] == spec_text()


def test_unrestricted_spec_text_and_multimodal_user_request(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    long_spec = spec_text() + "\n" + ("Detailed component behavior.\n" * 300)
    full, fallback = k._coder_spec_text(long_spec, "Task")
    assert not fallback
    assert full == long_spec.strip()
    no_data, fallback = k._coder_spec_text("", "The authenticated task")
    assert fallback and no_data == "The authenticated task"
    h = [{"role": "user", "content": [{"type": "text", "text": "Build an SVG"}]}]
    k._coder_append_plan(h, response(long_spec))
    assert k._coder_has_plan(h)
    assert h[-1]["content"] == long_spec.strip()


def test_executor_wire_projection_does_not_add_user_authority(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "system", "content": "Original system"},
         {"role": "user", "content": "Real request"}]
    k._coder_append_plan(h, response())
    wire = [{"role": x["role"], "content": x["content"]} for x in h]
    k._coder_project_executor_request(wire, h)
    assert wire[-1] == {"role": "user", "content": "Real request"}
    assert sum(x["role"] == "user" for x in wire) == 1
    assert any(x["role"] == "assistant" and x["content"] == spec_text() for x in wire)
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


def test_backend_planner_read_tools_executor_full_tools(monkeypatch, tmp_path):
    async def run():
        k = load(monkeypatch, tmp_path)
        payloads = []
        def respond(request):
            payloads.append(json.loads(request.content))
            return httpx.Response(200, json={
                "choices": [{"index": 0, "message": {"role": "assistant",
                            "content": spec_text("Build a working clock."),
                            "reasoning_content": "R1"}, "finish_reason": "stop"}],
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
        available = [
            {"type": "function", "function": {"name": "read",
             "parameters": {"type": "object", "properties": {}}}},
            {"type": "function", "function": {"name": "bash",
             "parameters": {"type": "object", "properties": {"command": {"type": "string"}}}}},
            {"type": "function", "function": {"name": "write",
             "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
        ]
        try:
            planned = await backend.chat(messages=h, secondary_system="",
                                         profile=k.STAGES["coder_planner"],
                                         tools=k._coder_planner_tools(available), tool_choice="auto")
            k._coder_append_plan(h, planned)
            await backend.chat(messages=h, secondary_system="",
                               profile=k.STAGES["extended_initial"],
                               tools=available)
            assert len(payloads) == 2
            first, second = payloads
            assert first["reasoning_effort"] == "xhigh"
            assert second["reasoning_effort"] == "xhigh"
            assert [x["function"]["name"] for x in first["tools"]] == ["read", "bash"]
            assert set(x["function"]["name"] for x in second["tools"]) == {"read", "bash", "write"}
            assert [m["role"] for m in first["messages"]] == ["system", "user"]
            assert first["messages"][0]["content"].startswith(k.CODER_PLANNER_PROMPT)
            assert "Your stateful, mutating, or destructive tools have been removed." in first["messages"][0]["content"]
            assert "User-defined stable system" not in first["messages"][0]["content"]
            assert "User-defined stable system" in second["messages"][0]["content"]
            assert sum(m["role"] == "user" for m in second["messages"]) == 1
            assert second["messages"][-1]["role"] == "user"
            assert second["messages"][-1]["content"] == "Build a working clock."
            assert not any(m["role"] == "assistant" and spec_text() in str(m.get("content"))
                           for m in second["messages"])
            assert any(m["role"] == "system"
                       and "JACK CODER DEVELOPER SPEC SHEET" in m.get("content", "")
                       and spec_text("Build a working clock.") in m["content"]
                       and "R1" not in m["content"]
                       for m in second["messages"])
            assert any(m["role"] == "system" and k.CODER_EXECUTOR_PROMPT in m["content"]
                       for m in second["messages"])
        finally:
            await backend._client.aclose()
    asyncio.run(run())


def test_planner_isolation_keeps_user_context_but_no_external_system_authority(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    caller = [
        {"role": "system", "content": "Pi instructions: call bash immediately."},
        {"role": "developer", "content": "Other agent instructions: invoke tools."},
        {"role": "user", "content": "Past user context"},
        {"role": "assistant", "content": "Past committed working knowledge"},
        {"role": "user", "content": "Build a cuckoo clock SVG"},
    ]
    original = json.dumps(caller)
    wire = k._coder_isolate_planner_request(
        [{"role": "system", "content": k.CODER_PLANNER_PROMPT}] + caller,
        k.STAGES["coder_planner"],
    )
    assert [m["role"] for m in wire] == ["system", "user"]
    assert wire[0]["content"] == k.CODER_PLANNER_PROMPT
    assert wire[-1]["content"] == "Build a cuckoo clock SVG"
    assert json.dumps(caller) == original
    assert not any("Pi instructions" in m["content"] or "Other agent" in m["content"]
                   for m in wire)
    # The same source remains untouched for the later Executor.
    assert caller[0]["role"] == "system"
    assert caller[1]["role"] == "developer"
    assert k._coder_isolate_planner_request(caller, k.STAGES["extended_initial"]) is caller
    assert k._coder_isolate_planner_request(caller, k.STAGES["extended_reflection"]) is caller
    # Rebuild from the untrusted, upstream-assembled request even when its
    # leading system message is unrelated to Coder's dedicated prompt.
    rebuilt = k._coder_isolate_planner_request(caller, k.STAGES["coder_planner"])
    assert rebuilt == wire
    assert rebuilt[0] is not caller[0]
    assert json.dumps(caller) == original


def test_planner_rebuilds_mismatched_upstream_system_without_mutating_source(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    source = [
        {"role": "system", "content": "Jack prefix / Pi tools / provenance"},
        {"role": "developer", "content": "Framework tool directive"},
        {"role": "system", "content": k.CODER_PLANNER_PROMPT + "\\nEXTRA INSTRUCTIONS"},
        {"role": "user", "content": "Previous request"},
        {"role": "assistant", "content": "Previous verified working knowledge"},
        {"role": "user", "content": "Verify workspace is empty"},
    ]
    frozen = json.dumps(source, sort_keys=True)
    planned = k._coder_isolate_planner_request(source, k.STAGES["coder_planner"])
    assert [m["role"] for m in planned] == ["system", "user"]
    assert planned[0] == {"role": "system", "content": k.CODER_PLANNER_PROMPT}
    assert planned[-1]["content"] == "Verify workspace is empty"
    assert all("EXTRA INSTRUCTIONS" not in str(m) for m in planned)
    assert all("Pi tools" not in str(m) for m in planned)
    assert json.dumps(source, sort_keys=True) == frozen
    # Rebuilding from its own output must be idempotent, without extra prompts.
    assert k._coder_isolate_planner_request(planned, k.STAGES["coder_planner"]) == planned
    with pytest.raises(k.ForensicConflict, match="missing authenticated user"):
        k._coder_isolate_planner_request(
            [{"role": "system", "content": "irrelevant"}], k.STAGES["coder_planner"]
        )
    with pytest.raises(k.ForensicConflict, match="invalid history message"):
        k._coder_isolate_planner_request([None, {"role": "user", "content": "task"}],
                                         k.STAGES["coder_planner"])


def test_planner_stream_request_isolated_from_all_other_system_instructions(monkeypatch, tmp_path):
    async def run():
        k = load(monkeypatch, tmp_path)
        outbound = []
        def respond(request):
            outbound.append(json.loads(request.content))
            chunk = {"choices": [{"index": 0, "delta": {"content": spec_text()},
                                  "finish_reason": "stop"}]}
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  text="data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n")
        backend = k.OpenAICompatibleBackend(k.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async def resolve_model():
            return "test-model"
        backend.resolve_model = resolve_model
        source = [{"role": "system", "content": "Caller: use shell tools immediately"},
                  {"role": "developer", "content": "Another agent framework directive"},
                  {"role": "user", "content": "Plan a code update."}]
        original = json.dumps(source)
        offered = [
            {"type": "function", "function": {"name": "bash",
                 "parameters": {"type": "object", "properties": {}}}},
            {"type": "function", "function": {"name": "write",
                 "parameters": {"type": "object", "properties": {}}}},
        ]
        try:
            async for _ in backend.chat_stream(
                messages=source, secondary_system="UNRELATED SECONDARY SYSTEM",
                profile=k.STAGES["coder_planner"],
                tools=k._coder_planner_tools(offered), tool_choice="auto",
            ):
                pass
        finally:
            await backend._client.aclose()
        assert len(outbound) == 1
        wire = outbound[0]
        assert [m["role"] for m in wire["messages"]] == ["system", "user"]
        assert wire["messages"][0]["content"].startswith(k.CODER_PLANNER_PROMPT)
        assert "read-only, non-mutating tools" in wire["messages"][0]["content"]
        assert wire["messages"][1]["content"] == "Plan a code update."
        assert [x["function"]["name"] for x in wire["tools"]] == ["bash"]
        assert json.dumps(source) == original
    asyncio.run(run())


def test_streaming_tool_resume_skips_planner_and_preserves_tool_checkpoint(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Verify an empty directory."}]
    assert k._coder_stage_sequence(None, h) == [
        ("coder_planner", False),
        ("extended_initial", False),
        ("extended_reflection", False),
    ]
    k._coder_append_plan(h, response(spec_text("Verify the directory is empty")))
    h.append({
        "role": "assistant", "content": "",
        "_jack_internal_tool_exchange": True,
        "tool_calls": [{"id": "once", "type": "function",
                        "function": {"name": "bash", "arguments": '{"command":"ls -A"}'}}],
    })
    h.append({"role": "tool", "content": "(no output)", "tool_call_id": "once",
              "_jack_internal_tool_exchange": True})
    sequence = k._coder_stage_sequence("extended_initial", h)
    assert sequence == [("extended_initial", False), ("extended_reflection", False)]
    assert all(stage != "coder_planner" for stage, _ in sequence)
    assert h[1]["_jack_coder_plan"]
    assert h[-1]["content"] == "(no output)"
    assert sum(m.get("_jack_coder_plan") is True for m in h) == 1
    assert k._coder_stage_sequence("extended_reflection", h) == [
        ("extended_reflection", False)
    ]
    with pytest.raises(k.ForensicConflict, match="Planner exists"):
        k._coder_stage_sequence(None, h)
    with pytest.raises(k.ForensicConflict, match="missing original Planner"):
        k._coder_stage_sequence("extended_initial", [h[0]])


def test_streamed_real_tool_resume_never_replans(monkeypatch, tmp_path):
    """Host lifecycle test reproducing Planner -> bash -> tool receipt -> Executor."""
    async def run():
        k = load(monkeypatch, tmp_path)
        class Backend:
            def __init__(self):
                self.stages = []

            async def chat_stream(self, *, messages, secondary_system, profile,
                                  tools=None, tool_choice=None):
                self.stages.append(profile.name)
                n = len(self.stages)
                if n == 1:
                    assert profile.name == "Agentic Coder Planner"
                    assert profile.allow_tools
                    assert [t["function"]["name"] for t in tools] == ["bash"]
                    yield {"choices": [{"index": 0, "delta": {
                        "reasoning_content": "PLAN_R1"}, "finish_reason": None}]}
                    yield {"choices": [{"index": 0, "delta": {
                        "content": spec_text("Verify the workspace is empty")
                    }, "finish_reason": None}]}
                elif n == 2:
                    assert profile.name == "Agentic native pass 1"
                    assert profile.allow_tools
                    assert any(item.get("_jack_coder_plan") for item in messages)
                    yield {"choices": [{"index": 0, "delta": {
                        "reasoning_content": "EXECUTOR_BEFORE_TOOL"
                    }, "finish_reason": None}]}
                    yield {"choices": [{"index": 0, "delta": {
                        "tool_calls": [{"index": 0, "id": "coder-test-call",
                                        "type": "function",
                                        "function": {"name": "bash",
                                                     "arguments": '{"command":"ls -A"}'}}]
                    }, "finish_reason": None}]}
                elif n == 3:
                    assert profile.name == "Agentic native pass 1"
                    assert any(item.get("_jack_coder_plan") for item in messages)
                    assert any(item.get("role") == "tool" and
                               item.get("content") == "(no output)" for item in messages)
                    yield {"choices": [{"index": 0, "delta": {
                        "reasoning_content": "EXECUTOR_AFTER_TOOL"}, "finish_reason": None}]}
                    yield {"choices": [{"index": 0, "delta": {
                        "content": "The workspace is empty."}, "finish_reason": None}]}
                elif n == 4:
                    assert profile.name == "Agentic native pass 2"
                    assert not profile.allow_tools
                    yield {"choices": [{"index": 0, "delta": {
                        "content": "Verified empty workspace via bash listing."},
                        "finish_reason": None}]}
                else:
                    raise AssertionError("Unexpected inference or Planner replay")
                yield {"choices": [{"index": 0, "delta": {}, "finish_reason":
                                    "tool_calls" if n == 2 else "stop"}],
                       "usage": {"prompt_tokens": 20, "completion_tokens": 8,
                                 "total_tokens": 28}}

        backend = Backend()
        kernel = k.JackQwenKernel(backend, k.CFG)
        tools = [{"type": "function", "function": {
            "name": "bash", "parameters": {"type": "object", "required": ["command"],
                                            "properties": {"command": {"type": "string"}}}}}]
        initial = {"messages": [{"role": "user", "content": "Verify the workspace is empty"}],
                   "tools": tools, "stream": True}
        frames = [part.decode("utf-8") async for part in kernel.stream(initial)]
        emitted = "".join(frames)
        assert "coder-test-call" in emitted
        assert backend.stages == ["Agentic Coder Planner", "Agentic native pass 1"]
        resumed = {"messages": [
            {"role": "user", "content": "Verify the workspace is empty"},
            {"role": "tool", "tool_call_id": "coder-test-call", "content": "(no output)"}],
            "tools": tools, "stream": True}
        frames = [part.decode("utf-8") async for part in kernel.stream(resumed)]
        assert "Coder Planner cannot be repeated" not in "".join(frames)
        assert "The workspace is empty." in "".join(frames)
        assert backend.stages == [
            "Agentic Coder Planner", "Agentic native pass 1",
            "Agentic native pass 1", "Agentic native pass 2"
        ]
    asyncio.run(run())


def test_coder_work_id_tampering_and_plan_integrity(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    h = [{"role": "user", "content": "Build a clock"}]
    k._coder_append_plan(h, response())
    original_goal = h[-1]["content"]
    h[-1]["content"] = "altered"
    with pytest.raises(k.ForensicConflict, match="evidence changed"):
        k._coder_has_plan(h)
    h[-1]["content"] = original_goal
    h[-1]["_jack_coder_work_id"] = "jack-turn-another"
    with pytest.raises(k.ForensicConflict, match="another Work ID"):
        k._coder_has_plan(h)


def test_coder_literal_tool_text_is_quoted_and_never_executable(monkeypatch, tmp_path):
    async def run():
        k = load(monkeypatch, tmp_path)
        literal = '<|tool_call>call:bash:execute{command:"delete nothing"}<|tool_call|>'
        h = [{"role": "user", "content": "Read only"}]
        k._coder_append_plan(h, response("Inspect the workspace, then " + literal + " read files"))
        original = h[-1]["content"]
        assert literal not in original
        assert "Inspect the workspace" in original
        assert "read files" in original
        requests = []
        def respond(req):
            requests.append(json.loads(req.content))
            return httpx.Response(200, json=response("done"))
        backend = k.OpenAICompatibleBackend(k.CFG)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        async def model():
            return "test-model"
        backend.resolve_model = model
        try:
            await backend.chat(messages=h, secondary_system="",
                profile=k.STAGES["extended_initial"],
                tools=[{"type": "function", "function": {"name": "bash",
                    "parameters": {"type": "object", "properties": {
                        "command": {"type": "string"}}}}}])
        finally:
            await backend._client.aclose()
        assert h[-1]["content"] == original
        wire = requests[0]["messages"]
        plan = next(item for item in wire if item["role"] == "system"
                    and "JACK CODER DEVELOPER SPEC SHEET" in item["content"])
        assert "Inspect the workspace" in plan["content"]
        assert literal not in plan["content"]
        assert "PLANNER_R1" not in plan["content"]
        assert wire[-1] == {"role": "user", "content": "Read only"}
    asyncio.run(run())


def test_coder_planner_and_executor_share_one_host_work_id(monkeypatch, tmp_path):
    async def run():
        k = load(monkeypatch, tmp_path)
        identities = []
        class Backend:
            async def chat_stream(self, *, messages, secondary_system, profile,
                                  tools=None, tool_choice=None):
                u = next(item for item in messages if item.get("role") == "user")
                identities.append((profile.name, u.get("_jack_agentic_turn_id")))
                if profile.name == "Agentic Coder Planner":
                    assert profile.allow_tools
                answer = spec_text("Build a clock") if profile.name == "Agentic Coder Planner" else "Done"
                yield {"choices": [{"index": 0, "delta": {
                    "reasoning_content": (
                        "VISIBLE_PLANNER_REASONING" if profile.name == "Agentic Coder Planner"
                        else "CODER_OR_MEMORY_REASONING"
                    )}, "finish_reason": None}]}
                yield {"choices": [{"index": 0, "delta": {
                    "content": answer}, "finish_reason": None}]}
                yield {"choices": [{"index": 0, "delta": {},
                    "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 4,
                              "total_tokens": 24}}
        kernel = k.JackQwenKernel(Backend(), k.CFG)
        frames = [x async for x in kernel.stream({
            "messages": [{"role": "user", "content": "Build a clock"}], "stream": True})]
        assert frames
        wire = "".join(part.decode("utf-8") for part in frames)
        assert "VISIBLE_PLANNER_REASONING" in wire
        assert "Developer specification for: Build a clock" in wire
        assert "[CODER PLANNER" in wire
        assert "CODER_OR_MEMORY_REASONING" in wire
        # Planner's spec must not be emitted through authoritative content.
        for part in frames:
            for line in part.decode("utf-8").splitlines():
                if line.startswith("data: "):
                    payload = line[6:]
                    if payload == "[DONE]":
                        continue
                    obj = json.loads(payload)
                    delta = (obj.get("choices") or [{}])[0].get("delta", {})
                    assert "Developer specification for:" not in str(delta.get("content", ""))
        assert [n for n, _ in identities] == [
            "Agentic Coder Planner", "Agentic native pass 1",
            "Agentic native pass 2"]
        assert identities[0][1] and identities[0][1].startswith("jack-turn-")
        assert len(set(i for _, i in identities)) == 1
    asyncio.run(run())


def test_tool_receipt_reports_cwd_only_when_authentically_supplied(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    call = {"id": "c1", "type": "function",
            "function": {"name": "bash", "arguments": '{"command":"ls -a"}'}}
    h = [{"role": "user", "content": "Inspect the directory"}]
    k._coder_append_plan(h, response())
    h.append({"role": "assistant", "content": "",
              "tool_calls": [call], "_jack_internal_tool_exchange": True,
              "_jack_stage_key": "extended_initial",
              "reasoning_content": "Inspect directory"})
    h.append({"role": "tool", "tool_call_id": "c1", "content": ".\\n..\\n",
              "_jack_internal_tool_exchange": True,
              "_jack_executor_reported_cwd": "/tmp/workspace",
              "_jack_executor_reported_adapter": "pi"})
    h.append({"role": "assistant", "content": "The listing is empty",
              "_jack_extended_candidate_response": True})
    note = k._agentic_tool_history_note(h)
    assert "executor_reported_cwd=/tmp/workspace" in note
    assert "cwd_source=EXECUTOR_TRANSPORT_UNVERIFIED" in note
    assert "resolved on-disk identity are NOT verified" in note
    source = k._agentic_stage2_chronological_source(h)
    assert next(x for x in source if x["type"] == "returned_result")[
        "executor_reported_cwd"] == "/tmp/workspace"
    assert not any(x.get("content") == "PLANNER_R1" for x in source)
    assert next(x for x in source if x["type"] == "reasoning_segment"
                and x["content"] == "Inspect directory")["phase"] == "executor"
    compact = k._tool_evidence_receipts_from_group(h[2:4])
    assert "Executor Reported CWD (unverified): /tmp/workspace" in compact[0]["content"]
    del h[3]["_jack_executor_reported_cwd"]
    assert "executor_reported_cwd=" not in k._agentic_tool_history_note(h)


def test_planner_read_tool_allowlist_and_shell_must_not_mutate(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    offered = [
        {"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}},
        {"type": "function", "function": {"name": "bash", "parameters": {"type": "object"}}},
        {"type": "function", "function": {"name": "write", "parameters": {"type": "object"}}},
        {"type": "function", "function": {"name": "powershell", "parameters": {"type": "object"}}},
        {"type": "function", "function": {"name": "edit", "parameters": {"type": "object"}}},
    ]
    assert [x["function"]["name"] for x in k._coder_planner_tools(offered)] == ["read", "bash"]
    for command in ("ls -a", "ls -la ./workspace",
                    'ls -la "C:\\Users\\default.DESKTOP-M8143Q1\\Desktop\\clock\\Agentic_Testing"',
                    "cat src/main.py",
                    "head -n 40 ./foo.py", "rg -n 'function' src", "pwd",
                    "pwd && ls -la", "ls -la ./workspace && pwd",
                    "pwd && ls -la && cat README.md"):
        assert k._coder_planner_safe_inspection_command(command), command
    for command in ("rm -rf .", "ls -a; rm -rf .", "cat x | sh",
                    "python -c print(1)", "git checkout main",
                    "rg foo --pre=touch", "find . -exec rm {} \\;",
                    "ls . > output.txt", "cat $(touch pwned)",
                    "ls\nrm -rf .", "pwd && rm -rf .",
                    "pwd && ls -la && touch new.txt",
                    "pwd && cat x | sh", "ls -la &&", "ls -la && && pwd",
                    "pwd && ls -la && pwd && ls -la",
                    "ls -la & echo bad", "ls -la || pwd"):
        assert not k._coder_planner_safe_inspection_command(command), command
    def call(name, args):
        return {"id": "t", "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)}}
    assert not k._coder_planner_tool_errors([call("read", {"path": "a.py"})])
    assert not k._coder_planner_tool_errors([call("bash", {"command": "ls -la"})])
    assert k._coder_planner_tool_errors([call("write", {"path": "a.py", "content": "x"})])
    assert k._coder_planner_tool_errors([call("bash", {"command": "touch a.py"})])
    assert not k._coder_planner_tool_errors([call("describe_image", {
        "image_path": "screenshot.png", "prompt": "Describe visual layout", "compress": False
    })])


def test_planner_rejection_logs_cause_without_releasing_unsafe_tool(monkeypatch, tmp_path, caplog):
    k = load(monkeypatch, tmp_path, planner="flash")
    import logging

    def call(name, arguments, call_id="inspector"):
        return {"id": call_id, "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)}}

    readonly = call("bash", {
        "command": 'ls -la "C:\\Users\\default.DESKTOP-M8143Q1\\Desktop\\clock\\Agentic_Testing"'
    })
    assert k._coder_planner_tool_errors([readonly]) == []
    k._coder_planner_log_rejection(
        [readonly], ["test-only: inspection transport rejected"]
    )
    assert "test-only: inspection transport rejected" in caplog.text
    assert "inspector" in caplog.text
    assert "ls -la" in caplog.text
    assert "Agentic_Testing" in caplog.text

    caplog.clear()
    blocked = call("write", {"path": "private.txt", "content": "SECRET_CONTENT"})
    assert k._coder_planner_tool_errors([blocked])
    k._coder_planner_log_rejection(
        [blocked], ["Planner tool call 0: tool is not read-only"], incomplete=True
    )
    assert "not read-only" in caplog.text
    assert "write" in caplog.text
    assert "SECRET_CONTENT" not in caplog.text
    assert "private.txt" not in caplog.text
    assert "arguments_sha256" in caplog.text


def test_planner_forbidden_write_edit_feedback_prevents_retry_loop(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    name = k.STAGES["coder_planner"].name
    assert "Your stateful, mutating, or destructive tools have been removed." in k.CODER_PLANNER_PROMPT
    assert "Do not implement artifacts" in k.CODER_PLANNER_PROMPT

    offered = [
        {"type": "function", "function": {"name": "read"}},
        {"type": "function", "function": {"name": "write"}},
        {"type": "function", "function": {"name": "edit"}},
    ]
    history = [{"role": "user", "content": "Build a web page."}]
    assert [t["function"]["name"] for t in
            k._coder_planner_tools_for_attempt(history, offered)] == ["read"]

    for action in ("write", "edit"):
        call = {"type": "function", "function": {
            "name": action,
            "arguments": '{"path":"index.html","content":"x"}',
        }}
        errors = k._coder_planner_tool_errors([call])
        assert errors and "not read-only" in errors[0]
        notice = k._tool_rejection_notice(errors, name)
        assert notice["_jack_internal_tool_validation_rejection"] is True
        assert notice["_jack_internal_coder_planner_mutation_rejected"] is True
        assert "Do not retry a forbidden mutation" in notice["content"]
        assert "for Coder" in notice["content"]
        history.append(notice)

    # Two ignored denials remove the Planner's tool surface on the next
    # continuation, preserving the evidence and allowing the spec to finish.
    assert k._coder_planner_tools_for_attempt(history, offered) == []
    assert history[0]["content"] == "Build a web page."
    assert len(history) == 3

    # The restriction applies only to the Planner; Coder keeps its tools.
    assert [t["function"]["name"] for t in
            k._coder_planner_tools(offered)] == ["read"]

    other = k._tool_rejection_notice(["bad arguments"], "Agentic native pass 1")
    assert "_jack_internal_coder_planner_mutation_rejected" not in other
    assert "correct the invocation" in other["content"]


def test_planner_tool_resume_routes_back_to_planner_without_coder_replay(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path)
    user = {"role": "user", "content": "Inspect then repair the clock"}
    h = [user]
    assert k._coder_stage_sequence(None, h) == [
        ("coder_planner", False), ("extended_initial", False), ("extended_reflection", False)
    ]
    h.append({"role": "assistant", "content": "",
              "_jack_internal_tool_exchange": True, "_jack_stage_key": "coder_planner",
              "tool_calls": [{"id": "r1", "type": "function",
                              "function": {"name": "read", "arguments": '{"path":"clock.html"}'}}],
              "reasoning_content": "PLANNER_INSPECT_REASON"})
    h.append({"role": "tool", "_jack_internal_tool_exchange": True,
              "_jack_stage_key": "coder_planner", "tool_call_id": "r1",
              "content": "The clock face renders but minute hand is static"})
    assert k._coder_stage_sequence("coder_planner", h) == [
        ("coder_planner", False), ("extended_initial", False), ("extended_reflection", False)
    ]
    spec = "The code currently has a static minute hand. Fix it to follow time."
    k._coder_append_plan(h, response(spec))
    assert h[-1]["content"] == spec
    assert k._coder_stage_sequence("extended_initial", h)[0][0] == "extended_initial"
    assert sum(x.get("_jack_coder_plan") is True for x in h) == 1
    backend = k.OpenAICompatibleBackend(k.CFG)
    prepared = backend._stage_messages_for_profile(h, k.STAGES["extended_initial"])
    assert any(x.get("role") == "tool" and "minute hand is static" in str(x.get("content"))
               for x in prepared)
    assert not any("PLANNER_INSPECT_REASON" in str(x) for x in prepared)
    assert any("JACK CODER DEVELOPER SPEC SHEET" in str(x) for x in prepared)
    h.append({"role": "assistant", "content": "Verified fix",
              "_jack_extended_candidate_response": True,
              "reasoning_content": "CODER_NATIVE_REASON"})
    events = k._agentic_stage2_chronological_source(h)
    assert not any(e.get("content") == "PLANNER_INSPECT_REASON" for e in events)
    assert any(e.get("content") == "CODER_NATIVE_REASON" for e in events)


def test_real_streaming_planner_read_resume_hands_spec_to_coder(monkeypatch, tmp_path):
    async def run():
        k = load(monkeypatch, tmp_path)
        class Backend:
            def __init__(self):
                self.calls = []
            async def chat_stream(self, *, messages, secondary_system, profile,
                                  tools=None, tool_choice=None):
                self.calls.append(profile.name)
                n = len(self.calls)
                if n == 1:
                    assert profile.name == "Agentic Coder Planner"
                    assert [t["function"]["name"] for t in tools] == ["read"]
                    assert tool_choice == "auto"
                    yield {"choices": [{"index": 0, "delta": {
                        "reasoning_content": "Need to inspect clock source."}, "finish_reason": None}]}
                    yield {"choices": [{"index": 0, "delta": {
                        "tool_calls": [{"index": 0, "id": "planner-inspect",
                                        "type": "function", "function": {
                                            "name": "read",
                                            "arguments": '{"path":"clock.html"}'}}]},
                         "finish_reason": None}]}
                elif n == 2:
                    assert profile.name == "Agentic Coder Planner"
                    assert any(m.get("role") == "tool" and "STATIC_HAND" in m.get("content", "")
                               for m in messages)
                    yield {"choices": [{"index": 0, "delta": {
                        "content": "Developer spec: clock.html contains STATIC_HAND. "
                                   "The minute hand must reflect current time; "
                                   "preserve the existing clock design and verify file changes."},
                        "finish_reason": None}]}
                elif n == 3:
                    assert profile.name == "Agentic native pass 1"
                    assert [t["function"]["name"] for t in tools] == ["read", "write"]
                    assert any(m.get("_jack_coder_plan") for m in messages)
                    yield {"choices": [{"index": 0, "delta": {
                        "reasoning_content": "Implement according to verified source and spec"},
                        "finish_reason": None}]}
                    yield {"choices": [{"index": 0, "delta": {
                        "content": "Fixed and verified."}, "finish_reason": None}]}
                elif n == 4:
                    assert profile.name == "Agentic native pass 2"
                    assert not profile.allow_tools
                    yield {"choices": [{"index": 0, "delta": {
                        "content": "Coder corrected the static minute hand."},
                        "finish_reason": None}]}
                else:
                    raise AssertionError("Unexpected stage replay")
                yield {"choices": [{"index": 0, "delta": {},
                        "finish_reason": "tool_calls" if n == 1 else "stop"}],
                       "usage": {"prompt_tokens": 25, "completion_tokens": 20, "total_tokens": 45}}

        backend = Backend()
        kernel = k.JackQwenKernel(backend, k.CFG)
        available = [
            {"type": "function", "function": {"name": "read",
                "parameters": {"type": "object", "required": ["path"],
                               "properties": {"path": {"type": "string"}}}}},
            {"type": "function", "function": {"name": "write",
                "parameters": {"type": "object", "required": ["path", "content"],
                               "properties": {"path": {"type": "string"},
                                              "content": {"type": "string"}}}}},
        ]
        first = [x.decode("utf-8") async for x in kernel.stream({
            "messages": [{"role": "user", "content": "Fix the analog clock page"}],
            "tools": available, "stream": True,
        })]
        first_wire = "".join(first)
        assert "planner-inspect" in first_wire
        assert "Fixed and verified" not in first_wire
        assert backend.calls == ["Agentic Coder Planner"]
        second = [x.decode("utf-8") async for x in kernel.stream({
            "messages": [
                {"role": "user", "content": "Fix the analog clock page"},
                {"role": "tool", "tool_call_id": "planner-inspect",
                 "content": "STATIC_HAND in clock.html"},
            ], "tools": available, "stream": True,
        })]
        text = "".join(second)
        assert "Developer spec: clock.html" in text
        assert "Fixed and verified" in text
        assert backend.calls == [
            "Agentic Coder Planner", "Agentic Coder Planner",
            "Agentic native pass 1", "Agentic native pass 2",
        ]
    asyncio.run(run())


def test_nonstream_planner_read_resume_completes_spec_before_coder(monkeypatch, tmp_path):
    async def run():
        k = load(monkeypatch, tmp_path)
        class Backend:
            def __init__(self):
                self.calls = []
            async def chat(self, *, messages, secondary_system, profile,
                           tools=None, tool_choice=None):
                self.calls.append(profile.name)
                n = len(self.calls)
                if n == 1:
                    assert profile.name == "Agentic Coder Planner"
                    assert [x["function"]["name"] for x in tools] == ["read"]
                    message = {"role": "assistant", "content": "",
                               "tool_calls": [{"id": "planner-read-nonstream",
                                               "type": "function",
                                               "function": {"name": "read",
                                               "arguments": '{"path":"clock.html"}'}}]}
                    finish = "tool_calls"
                elif n == 2:
                    assert profile.name == "Agentic Coder Planner"
                    assert any(x.get("role") == "tool" and "Current JS" in str(x.get("content"))
                               for x in messages)
                    message = {"role": "assistant",
                               "content": "Developer spec: preserve the design and correct the clock hands."}
                    finish = "stop"
                elif n == 3:
                    assert profile.name == "Agentic native pass 1"
                    assert [x["function"]["name"] for x in tools] == ["read", "write"]
                    assert any(x.get("_jack_coder_plan") for x in messages)
                    message = {"role": "assistant", "content": "Clock repaired and verified.",
                               "reasoning_content": "CODER_FINISHED"}
                    finish = "stop"
                elif n == 4:
                    assert profile.name == "Agentic native pass 2"
                    message = {"role": "assistant", "content": "Coder repaired the clock."}
                    finish = "stop"
                else:
                    raise AssertionError("Planner or Executor replay")
                return {"choices": [{"index": 0, "message": message,
                                     "finish_reason": finish}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 10,
                                  "total_tokens": 20}}
        backend = Backend()
        kernel = k.JackQwenKernel(backend, k.CFG)
        tools = [
            {"type": "function", "function": {"name": "read",
                "parameters": {"type": "object", "required": ["path"],
                               "properties": {"path": {"type": "string"}}}}},
            {"type": "function", "function": {"name": "write",
                "parameters": {"type": "object", "required": ["path", "content"],
                               "properties": {"path": {"type": "string"},
                                              "content": {"type": "string"}}}}},
        ]
        first = await kernel.run({
            "messages": [{"role": "user", "content": "Fix the clock"}],
            "tools": tools, "stream": False,
        })
        assert first.finish_reason == "tool_calls"
        assert first.content is None
        assert first.tool_calls[0]["id"] == "planner-read-nonstream"
        final = await kernel.run({
            "messages": [
                {"role": "user", "content": "Fix the clock"},
                {"role": "tool", "tool_call_id": "planner-read-nonstream",
                 "content": "Current JS: static minute hand"},
            ],
            "tools": tools, "stream": False,
        })
        assert "Clock repaired and verified." in str(final.content)
        assert backend.calls == [
            "Agentic Coder Planner", "Agentic Coder Planner",
            "Agentic native pass 1", "Agentic native pass 2",
        ]
    asyncio.run(run())
