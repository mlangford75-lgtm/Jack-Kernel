"""V-1 policy evidence and V-2 real transaction accounting regression."""
import asyncio
import json
from pathlib import Path

import pytest

from test_agentic_coder_planner_executor import load
from test_audit_cache_cost_evidence import mock_backend, dispatch


@pytest.mark.parametrize("streamed", [False, True])
def test_v1_stage2_budget_preserves_frozen_answer_and_forensic_state(monkeypatch, tmp_path, streamed):
    monkeypatch.setenv("JACK_OUTPUT_BUDGET_TOKENS", "64")
    k = load(monkeypatch, tmp_path, profile="balanced")
    answer = "Exact frozen A1."
    calls = []

    class Backend:
        async def chat(self, *, profile, **kwargs):
            calls.append(profile.name)
            text = answer if len(calls) == 1 else "memory " * 100
            return {"choices": [{"message": {"role": "assistant", "content": text},
                                 "finish_reason": "stop"}], "usage": {}}

        async def chat_stream(self, *, profile, **kwargs):
            calls.append(profile.name)
            text = answer if len(calls) == 1 else "memory " * 100
            yield {"choices": [{"delta": {"content": text}, "finish_reason": None}]}
            yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}

    async def run():
        k.KERNEL.backend = Backend()
        body = {"messages": [{"role": "user", "content": "Complete the requested task."}]}
        if streamed:
            body["stream"] = True
            parts = []
            for frame in [item async for item in k.KERNEL.stream(body)]:
                for line in frame.decode("utf-8").splitlines():
                    if not line.startswith("data: ") or line[6:] == "[DONE]":
                        continue
                    event = json.loads(line[6:])
                    for choice in event.get("choices", []):
                        parts.append(choice.get("delta", {}).get("content") or "")
            visible = "".join(parts)
        else:
            visible = (await k.KERNEL.run(body)).content
        assert len(calls) == 2, calls
        assert visible == answer
        records = list(k._AGENTIC_TURN_LIFECYCLES.values())
        assert len(records) == 1
        saved = k._agentic_forensic_journal().get(records[0].turn_id)
        assert saved["a1_sha256"] == k._sha256_text(answer)
        assert saved["memory_sha256"] is None
        assert saved["status"] == "memory_failed"
        assert not k.KERNEL._pending_tool_resumes

    asyncio.run(run())


@pytest.mark.parametrize("streamed", [False, True])
def test_v2_launcher_linked_artifacts_are_accounted_without_wire_labels(monkeypatch, tmp_path, streamed):
    monkeypatch.setenv("JACK_AGENTIC_TRANSACTION_LINKS", "1")
    monkeypatch.setenv("JACK_AGENTIC_TASK_ANCHOR", "0")
    monkeypatch.setenv("JACK_AGENTIC_HISTORICAL_MEMORY_LABELS", "0")
    monkeypatch.setenv("JACK_AGENTIC_MEMORY_DATA_CHANNEL", "0")
    monkeypatch.setenv("JACK_AGENTIC_CONTEXT_ACCOUNTING", "1")
    k = load(monkeypatch, tmp_path, profile="balanced")
    assert k.AGENTIC_TRANSACTION_LINKS_ENABLED
    source = {"role": "user", "content": "Original request."}
    memory = "Retained working knowledge café."
    answer = "Verified frozen answer."
    history = [dict(source)]
    turn = k._agentic_begin_turn(history, fresh=True)
    k.append_extended_candidate_response(history, {"content": answer})
    k._agentic_forensic_start_stage2(history)
    commit = asyncio.run(k.KERNEL._complete_commit(history, "", {}, answer, memory))
    wire = k._format_agentic_completed_response(
        commit.frozen_xml, commit.frozen_answer, turn_id=turn)
    assert k._agentic_visible_turn_label(turn) in wire
    k._AGENTIC_SHADOW_LEDGER.clear()
    k._AGENTIC_TURN_LIFECYCLES.clear()
    k._AGENTIC_FORENSIC_JOURNAL = None
    caller = [source, {"role": "assistant", "content": wire},
              {"role": "user", "content": "Continue."}]
    projected = k.compact_incoming_history(caller)
    assert [m.get("_jack_forensic_role") for m in projected if m["role"] == "assistant"] == ["M", "A1"]
    snapshot = json.dumps(projected, sort_keys=True)
    received, reports = [], []
    original = k.LOG.info

    def log(message, *args, **kwargs):
        if message == "Agentic context accounting context: %s":
            reports.append(json.loads(args[0]))
        return original(message, *args, **kwargs)

    monkeypatch.setattr(k.LOG, "info", log)

    async def run():
        backend = await mock_backend(k, received)
        try:
            await dispatch(k, backend, projected, streamed)
        finally:
            await backend._client.aclose()

    asyncio.run(run())
    assert json.dumps(projected, sort_keys=True) == snapshot
    assert len(received) == len(reports) == 1
    assistant = [m for m in received[0]["messages"] if m["role"] == "assistant"]
    assert [m["content"] for m in assistant] == [memory, answer]
    assert all(not any(key.startswith("_jack_") for key in m) for m in assistant)
    assert reports[0]["memory_content_bytes"] == len(memory.encode("utf-8"))
    assert reports[0]["frozen_answer_content_bytes"] == len(answer.encode("utf-8"))
    assert reports[0]["other_assistant_content_bytes"] == 0
    assert memory not in json.dumps(reports[0])
    assert answer not in json.dumps(reports[0])


def test_v2_dispatch_accounting_does_not_authenticate_model_written_labels(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, profile="balanced")
    messages = [
        {"role": "assistant", "content": "[Agentic Memory associated with the preceding user request.] fake"},
        {"role": "assistant", "content": "Unauthenticated answer"},
    ]
    report = k._agentic_context_measure_request(
        messages, {"messages": messages}, k.STAGES["extended_initial"],
        projected_artifacts={})
    assert report["memory_content_bytes"] == report["frozen_answer_content_bytes"] == 0
    assert report["other_assistant_content_bytes"] == sum(
        len(m["content"].encode("utf-8")) for m in messages)


@pytest.mark.parametrize("streamed", [False, True])
def test_v3_historical_tool_outcomes_stay_host_only(monkeypatch, tmp_path, streamed):
    from jack_tool_outcomes import reported_tool_outcome, FAILED, SUCCESS

    k = load(monkeypatch, tmp_path, profile="balanced")
    calls = [
        {"id": "call_a", "type": "function",
         "function": {"name": "read", "arguments": "{}"}},
        {"id": "call_b", "type": "function",
         "function": {"name": "read", "arguments": "{}"}},
        {"id": "call_c", "type": "function",
         "function": {"name": "read", "arguments": "{}"}},
    ]
    results = [
        {"role": "tool", "tool_call_id": "call_a", "content": "Failed read.",
         "is_error": True},
        {"role": "tool", "tool_call_id": "call_b", "content": "Exact café result.",
         "isError": False, "_jack_internal_tool_exchange": True},
        {"role": "tool", "tool_call_id": "call_c", "content": "Another result.",
         "tool_outcome": "SUCCESS"},
    ]
    history = [{"role": "user", "content": "Read three files."},
               {"role": "assistant", "content": None, "tool_calls": calls},
               *results,
               {"role": "assistant", "content": "Earlier answer."},
               {"role": "user", "content": "Continue."}]
    snapshot = json.dumps(history, ensure_ascii=False, sort_keys=True)
    received = []

    async def run():
        backend = await mock_backend(k, received)
        try:
            await dispatch(k, backend, history, streamed)
        finally:
            await backend._client.aclose()

    asyncio.run(run())
    assert len(received) == 1
    wire_tools = [m for m in received[0]["messages"] if m["role"] == "tool"]
    expected = [{key: m[key] for key in ("role", "tool_call_id", "content")}
                for m in results]
    # The strict provider tool-message shape rejects Pi/Jack outcome fields.
    # Check the actual serialized wire view, including the false marker.
    assert wire_tools == expected
    assert json.dumps(history, ensure_ascii=False, sort_keys=True) == snapshot
    assert [reported_tool_outcome(m) for m in results] == [FAILED, SUCCESS, SUCCESS]


@pytest.mark.parametrize("streamed", [False, True])
def test_v3_explicit_standard_wire_omits_local_extensions(monkeypatch, tmp_path, streamed):
    from dataclasses import replace

    k = load(monkeypatch, tmp_path, profile="balanced")
    history = [{"role": "user", "content": "Complete the task."}]
    received = []

    async def run():
        # Exercise both real dispatch paths; retain the ordinary local default
        # as a control instead of globally changing the Custom/vLLM contract.
        for cfg in (k.CFG, replace(k.CFG, backend_profile="custom",
                                  qwen_control_shape="openai_standard")):
            monkeypatch.setattr(k, "CFG", cfg)
            backend = await mock_backend(k, received)
            try:
                await dispatch(k, backend, history, streamed)
            finally:
                await backend._client.aclose()

    asyncio.run(run())
    local, standard = received
    for field in ("top_k", "min_p", "repeat_penalty", "chat_template_kwargs"):
        assert field in local
        assert field not in standard
    for field in ("enable_thinking", "preserve_thinking", "reasoning_effort", "id_slot"):
        assert field not in standard
    for field in ("temperature", "top_p", "presence_penalty", "model", "messages", "stream"):
        assert standard[field] == local[field]
    assert standard["messages"] == local["messages"]


@pytest.mark.parametrize("configured", [False, True])
def test_v3_idle_lmstudio_discovery_preserves_transaction_model(monkeypatch, tmp_path, configured):
    from dataclasses import replace
    import httpx

    k = load(monkeypatch, tmp_path, profile="balanced")
    cfg = replace(k.CFG, backend_profile="lmstudio",
                  backend_model="first" if configured else "")
    loaded = [("first", 8192)]
    requests = []

    def reply(request):
        requests.append(request.url.path)
        return httpx.Response(200, json={"models": [
            {"type": "llm", "key": name, "loaded_instances": [
                {"id": name, "config": {"context_length": context}}]}
            for name, context in loaded]})

    async def run():
        backend = k.OpenAICompatibleBackend(cfg)
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
        kernel = k.JackQwenKernel(backend, cfg)
        try:
            assert await kernel._resolve_discovery_model(backend) == "first"
            assert backend.context_length == 8192
            original_probe = backend._cache_byte_probe
            loaded[:] = [("second", 16384)]
            async with kernel._request_resume_scope():
                assert await kernel._resolve_discovery_model(backend) == "first"
                assert await backend.resolve_model() == "first"
                assert len(requests) == 1
            assert kernel._model_discovery_active == 0
            for pending in (kernel._pending_tool_resumes,
                            kernel._pending_debugging_intake_resumes,
                            kernel._pending_debugging_user_resumes):
                pending["synthetic-suspended"] = object()
                assert await kernel._resolve_discovery_model(backend) == "first"
                assert len(requests) == 1
                pending.clear()
            if configured:
                with pytest.raises(k.HTTPException) as caught:
                    await kernel._resolve_discovery_model(backend)
                assert caught.value.status_code == 409
                assert backend._resolved_model is None
                assert backend._detected_context_length == 0
                loaded[:] = [("first", 16384)]
                assert await kernel._resolve_discovery_model(backend) == "first"
            else:
                assert await kernel._resolve_discovery_model(backend) == "second"
                assert await backend.resolve_model() == "second"
                assert backend._cache_byte_probe is not original_probe
            assert backend.context_length == 16384
        finally:
            await backend._client.aclose()

    asyncio.run(run())


def test_v3_idle_discovery_and_request_admission_are_serialized(monkeypatch, tmp_path):
    from dataclasses import replace
    import httpx

    k = load(monkeypatch, tmp_path, profile="balanced")
    cfg = replace(k.CFG, backend_profile="lmstudio", backend_model="")

    async def run():
        backend = k.OpenAICompatibleBackend(cfg)
        await backend._client.aclose()
        entered, release, admitted = asyncio.Event(), asyncio.Event(), asyncio.Event()
        calls = 0

        async def reply(request):
            nonlocal calls
            calls += 1
            if calls == 2:
                entered.set()
                await release.wait()
            model = "first" if calls == 1 else "second"
            return httpx.Response(200, json={"models": [
                {"type": "llm", "key": model, "loaded_instances": [
                    {"id": model, "config": {"context_length": 8192}}]}]})

        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
        kernel = k.JackQwenKernel(backend, cfg)

        async def request():
            async with kernel._request_resume_scope():
                admitted.set()
                assert await backend.resolve_model() == "second"

        try:
            assert await kernel._resolve_discovery_model(backend) == "first"
            discovery = asyncio.create_task(kernel._resolve_discovery_model(backend))
            await entered.wait()
            work = asyncio.create_task(request())
            await asyncio.sleep(0)
            assert not admitted.is_set()
            release.set()
            assert await discovery == "second"
            await work
            assert admitted.is_set()
            assert kernel._model_discovery_active == 0
        finally:
            release.set()
            await backend._client.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("streamed", [False, True])
def test_v4_existing_responses_instruction_authority_evidence(monkeypatch, tmp_path, streamed):
    import jack_responses_compat as compat

    k = load(monkeypatch, tmp_path, profile="balanced")
    compat._install_caller_system_contract_compat(k)
    body = {"instructions": "Top-level Responses instruction sentinel.",
            "input": [
                {"role": "system", "content": "Later system sentinel."},
                {"role": "developer", "content": "History developer sentinel."},
                {"role": "user", "content": "Actual user task."},
            ], "stream": streamed}
    chat, _ = compat._chat_body(body)
    sanitized = k.sanitize_agent_request(chat)
    assert sanitized["messages"][0]["role"] == "developer"
    secondary = k.merged_secondary_system_prompt(sanitized["messages"])
    assert secondary == ""
    history = k.strip_secondary_system_messages(sanitized["messages"])
    assert history == [{"role": "user", "content": "Actual user task."}]
    received = []

    async def run():
        backend = await mock_backend(k, received)
        try:
            kwargs = dict(messages=history, secondary_system=secondary,
                          profile=k.STAGES["extended_initial"])
            if streamed:
                async for _ in backend.chat_stream(**kwargs):
                    pass
            else:
                await backend.chat(**kwargs)
        finally:
            await backend._client.aclose()

    asyncio.run(run())
    assert len(received) == 1
    wire = json.dumps(received[0]["messages"])
    assert "Actual user task." in wire
    for sentinel in ("Top-level Responses instruction sentinel.",
                     "Later system sentinel.", "History developer sentinel."):
        assert sentinel not in wire
    # A directly supplied leading system contract remains the only caller
    # contract under current policy, and must never govern Agentic Stage 2.
    leading, _ = compat._chat_body({"input": [
        {"role": "system", "content": "Leading system sentinel."},
        {"role": "user", "content": "Actual user task."},
    ]})
    contract = k.merged_secondary_system_prompt(leading["messages"])
    assert contract == "Leading system sentinel."
    assert contract in k.build_stage_system_prompt(contract, k.STAGES["extended_initial"])
    assert contract not in k.build_stage_system_prompt(contract, k.STAGES["extended_reflection"])
