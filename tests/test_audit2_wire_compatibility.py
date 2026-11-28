"""Audit 2 model-neutral wire and represented-path regression cases."""
import json
import asyncio
import pytest
import jack_kernel as jk
import jack_evidence_guard as guard
import jack_path_policy as paths


def test_parallel_calls_correlate_by_id_without_index():
    state = {}
    jk.JackQwenKernel._merge_tool_call_delta(state, [
        {"id": "a", "function": {"name": "read", "arguments": '{"path":'}},
        {"id": "b", "function": {"name": "read", "arguments": '{"path":'}},
    ])
    jk.JackQwenKernel._merge_tool_call_delta(state, [
        {"id": "b", "function": {"arguments": '"b"}'}},
        {"id": "a", "function": {"arguments": '"a"}'}},
    ])
    assert [json.loads(state[i]["function"]["arguments"])["path"] for i in (0, 1)] == ["a", "b"]


def test_identity_conflicts_and_anonymous_parallel_fragments_fail_closed():
    identities = {}
    assert guard.resolve_tool_fragment_index(identities, {"index": 0, "id": "a"}) == 0
    assert guard.resolve_tool_fragment_index(identities, {"index": 1, "id": "b"}) == 1
    for fragment in ({"index": 0, "id": "b"}, {"index": 2, "id": "a"}, {}, {"index": -1}):
        with pytest.raises(guard.StreamingIRQProtocolError):
            guard.resolve_tool_fragment_index(identities, fragment)


def test_single_anonymous_fragments_are_supported():
    identities = {}
    assert guard.resolve_tool_fragment_index(identities, {}) == 0
    assert guard.resolve_tool_fragment_index(identities, {}) == 0
    with pytest.raises(guard.StreamingIRQProtocolError):
        guard.resolve_tool_fragment_index(identities, {"id": "unassociated"})


def test_native_reasoning_alias_selection_preserves_precedence():
    assert guard.native_reasoning_delta({"thinking": "native"}) == ("thinking", "native")
    assert guard.native_reasoning_delta({"reasoning_content": "qwen", "thinking": "duplicate"}) == ("reasoning_content", "qwen")
    assert guard.native_reasoning_delta({"reasoning_content": "", "thinking": "native"}) == ("thinking", "native")


def test_only_fresh_completed_missing_ids_are_minted():
    raw = [{"type": "function", "function": {"name": "read", "arguments": "{}"}},
           {"id": "existing", "type": "function", "function": {"name": "read", "arguments": "{}"}}]
    calls = jk.normalize_tool_calls_for_distribution(raw)
    assert calls[0]["id"].startswith("jack-call-")
    assert calls[1]["id"] == "existing"
    assert "id" not in raw[0]
    assert jk.normalize_tool_calls_for_distribution(calls) == calls


@pytest.mark.parametrize("reason", ["stop", "STOP", "end_turn"])
def test_successful_completion_aliases(reason):
    jk.JackQwenKernel._agentic_require_completed_stage({"choices": [{"finish_reason": reason}]}, "test")


@pytest.mark.parametrize("reason", ["length", "content_filter", None])
def test_incomplete_completion_is_not_normalized(reason):
    with pytest.raises(jk.HTTPException):
        jk.JackQwenKernel._agentic_require_completed_stage({"choices": [{"finish_reason": reason}]}, "test")


def test_posix_case_distinct_targets_and_explicit_shells():
    for shell in ("sh", "zsh"):
        result = paths.extract_command_paths("shell", {"command": "cat /tmp/a /tmp/A | head -n 1"}, command_dialect=shell)
        assert result.applicable
        assert "/tmp/a" in result.targets and "/tmp/A" in result.targets


def test_authenticated_runtime_identity_needs_no_backend_discovery(monkeypatch):
    from types import SimpleNamespace
    async def unavailable(*args):
        raise AssertionError("runtime identity must not discover backend models")
    monkeypatch.setattr(jk.KERNEL, "_resolve_discovery_model", unavailable)
    monkeypatch.setattr(jk.CFG, "api_key", "synthetic-identity-key")
    with pytest.raises(jk.HTTPException) as exc:
        asyncio.run(jk.authenticated_runtime_identity(SimpleNamespace(headers={})))
    assert exc.value.status_code == 401
    result = asyncio.run(jk.authenticated_runtime_identity(
        SimpleNamespace(headers={"authorization": "Bearer synthetic-identity-key"})))
    assert result["runtime_id"] == jk.RUNTIME_ID
    assert result["lane_id"] == jk.LANE_ID
    assert "status" not in result  # identity is not a provider health claim


@pytest.mark.parametrize("advertised", [True, False, "true", None])
def test_lmstudio_vision_requires_positive_documented_capability(advertised):
    result = jk._parse_lmstudio_v1_loaded_llms({"models": [{
        "type": "llm", "key": "model", "capabilities": {"vision": advertised},
        "loaded_instances": [{"id": "loaded", "config": {"context_length": 8192}}],
    }]})
    assert result[0]["supports_vision"] is (advertised is True)


@pytest.mark.parametrize("models, expected", [
    ([{"name": "selected", "context_length": 8192}], 8192),
    ([{"name": "other", "context_length": 8192}], 0),
    ([{"name": "selected", "context_length": True}], 0),
    ([{"name": "selected", "context_length": 8192}, {"name": "selected", "context_length": 4096}], 0),
])
def test_ollama_optional_loaded_context_is_exact_and_not_fabricated(models, expected):
    from types import SimpleNamespace
    import httpx
    backend = object.__new__(jk.OpenAICompatibleBackend)
    backend.cfg = SimpleNamespace(backend_base_url="http://example.invalid/v1")
    backend._headers = lambda: {}
    def handle(request):
        assert request.method == "GET" and request.url.path == "/api/ps"
        return httpx.Response(200, json={"models": models})
    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            backend._client = client
            assert await backend._ollama_loaded_context("selected") == expected
    asyncio.run(check())


def test_rejection_archive_attribution_does_not_change_live_reasoning(monkeypatch):
    monkeypatch.setattr(jk, "active_response_target", lambda history: {"history_index": 1, "id": "synthetic"})
    earlier = {"role": "assistant", "_jack_stage_key": "extended_initial", "reasoning": "old turn"}
    current = {"role": "user", "content": "task"}
    accepted = {"role": "assistant", "_jack_stage_key": "extended_initial",
                "_jack_internal_tool_exchange": True, "reasoning": "executed cognition"}
    history = [earlier, current, accepted]
    history = jk._tool_rejection_history(history, {"reasoning": "rejected cognition"}, ["invalid"],
                                        jk.STAGES["extended_initial"].name,
                                        forensic_stage_key="extended_initial")
    history = jk._tool_rejection_history(history, {"reasoning": "architect only"}, ["invalid"],
                                        jk.STAGES["coder_planner"].name,
                                        forensic_stage_key="coder_planner")
    final = {"role": "assistant", "content": "done", "reasoning": "final cognition"}
    live_before = jk.extended_stage1_reasoning_trace(history, final)
    saved = jk._capture_agentic_stage1_forensic_snapshot(history, final)
    assert saved["reasoning_trace"] == "executed cognition\n\nrejected cognition\n\nfinal cognition"
    assert saved["rejected_action_checkpoints"] == [{
        "history_index": 3, "stage": "extended_initial", "executed": False,
        "reasoning": "rejected cognition",
    }]
    assert saved["tool_trajectory"] == [accepted]
    assert jk.extended_stage1_reasoning_trace(history, final) == live_before
    assert "rejected cognition" not in live_before
    assert "_jack_stage_key" not in history[3]
