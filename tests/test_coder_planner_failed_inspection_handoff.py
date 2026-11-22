"""Regressions for failing Planner read-only inspections and Coder handoff.

Only host-authenticated returned tool evidence may trigger the guard. This
does not compare model prose and does not restrict Executor tool authority.
"""
import json

from test_agentic_coder_planner_executor import load


def _call(call_id, path):
    return {
        "id": call_id, "type": "function",
        "function": {"name": "read", "arguments": json.dumps({"path": path})},
    }


def _history(first_result, *, outcome=None):
    history = [{"role": "user", "content": "Build an analog clock webpage"}]
    history.append({
        "role": "assistant", "content": "",
        "_jack_internal_tool_exchange": True, "_jack_stage_key": "coder_planner",
        "tool_calls": [_call("initial", "index.html")],
    })
    result = {
        "role": "tool", "tool_call_id": "initial",
        "_jack_internal_tool_exchange": True, "_jack_stage_key": "coder_planner",
        "content": first_result,
    }
    if outcome is not None:
        result["_jack_tool_outcome"] = outcome
    history.append(result)
    return history


def test_repeated_enoent_read_blocked_before_second_execution(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, planner="flash")
    history = _history("ENOENT: no such file or directory, access 'index.html'")
    assert k._coder_planner_repeated_failed_inspection(
        history, [_call("another-id", "index.html")]
    )
    assert not k._coder_planner_repeated_failed_inspection(
        history, [_call("new-id", "style.css")]
    )


def test_repeated_failed_read_with_explicit_tool_outcome(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, planner="thorough")
    history = _history("tool failed", outcome=k.TOOL_FAILED)
    assert k._coder_planner_repeated_failed_inspection(
        history, [_call("different-id", "index.html")]
    )


def test_successful_inspection_and_unrelated_prose_cannot_trigger_guard(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, planner="flash")
    history = _history("file exists")
    history.append({"role": "assistant",
                    "content": "ENOENT: this phrase is not a tool result"})
    assert not k._coder_planner_repeated_failed_inspection(
        history, [_call("new-id", "index.html")]
    )


def test_compacted_failed_planner_receipt_still_prevents_exact_retry(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, planner="thorough")
    first = _call("old-id", "index.html")
    history = [{"role": "user", "content": "Build clock"}, {
        "role": "assistant", "content": "host evidence",
        "_jack_tool_evidence_receipt": True,
        "_jack_stage_key": "coder_planner",
        "_jack_tool_action_signature": k._agentic_tool_action_signature(first),
        "_jack_tool_outcome": k.TOOL_FAILED, "_jack_tool_status": "FAILED",
    }]
    assert k._coder_planner_repeated_failed_inspection(
        history, [_call("new-id", "index.html")]
    )
    history[-1]["_jack_stage_key"] = "extended_initial"
    assert not k._coder_planner_repeated_failed_inspection(
        history, [_call("new-id", "index.html")]
    )


def test_host_handoff_preserves_authentic_task_without_claiming_written_files(monkeypatch, tmp_path):
    k = load(monkeypatch, tmp_path, planner="flash")
    history = _history("ENOENT: no such file or directory, access 'index.html'")
    fallback = k._coder_planner_host_handoff_result(history)
    message = fallback["choices"][0]["message"]
    assert message["_jack_coder_planner_host_fallback"] is True
    assert "Build an analog clock webpage" in message["content"]
    assert "No mutation was executed" in message["content"]
    assert not message["tool_calls"] if "tool_calls" in message else True
