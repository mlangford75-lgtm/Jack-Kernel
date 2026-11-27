"""Audit 2 model-neutral wire and represented-path regression cases."""
import json
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
