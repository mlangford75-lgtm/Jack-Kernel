"""Regressions for Coder Planner host recovery and Flash reasoning controls."""
import ast
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "jack_kernel.py"


def _load_isolated(*names):
    """Exercise real source functions without starting a serving Jack kernel."""
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    selected = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in selected} == set(names)
    namespace = {"Any": Any, "Dict": Dict, "List": List}
    exec(compile(ast.fix_missing_locations(ast.Module(
        body=selected, type_ignores=[])), str(SOURCE), "exec"), namespace)
    return namespace


def test_planner_fallback_extracts_plain_authenticated_request_and_retains_findings():
    functions = _load_isolated(
        "_coder_planner_is_host_continuation", "_coder_planner_host_handoff_result"
    )
    functions.update({
        "ForensicConflict": RuntimeError,
        "_content_to_text": lambda value: (
            "\n".join(part.get("text", "") for part in value if part.get("type") == "text")
            if isinstance(value, list) else str(value or "")
        ),
        "_coder_unverified_observations": lambda value: value.strip(),
        "active_response_target": lambda h: {
            "content": h[0]["content"], "history_index": 0
        },
    })
    request = 'C:/Example/clock is the workspace. verify its empty'
    history = [
        {"role": "user", "content": [{"type": "text", "text": request}]},
        {"role": "assistant", "content": "Read-only inspection confirmed that it contains no files.",
         "_jack_internal_tool_validation_checkpoint": True},
        {"role": "assistant",
         "content": "If the task is complete, output the final answer.",
         "_jack_internal_tool_validation_checkpoint": True},
    ]
    output = functions["_coder_planner_host_handoff_result"](
        history, "If the task is complete, output the final answer."
    )["choices"][0]["message"]["content"]
    assert request in output
    assert '[{"type": "text"' not in output
    assert "Read-only inspection confirmed" in output
    assert "Unfinished Planner observations" in output
    assert "If the task is complete" not in output


def test_planner_recovery_isolated_without_promoting_host_message_to_user():
    functions = _load_isolated("_coder_isolate_planner_request")
    functions.update({
        "AGENTIC_CODER_MODE": True,
        "ForensicConflict": RuntimeError,
        "_content_to_text": str,
    })
    class Profile:
        name = "Agentic Coder Planner"
        prompt = "You are Planner."
    entries = [
        {"role": "system", "content": "Caller-owned system"},
        {"role": "user", "content": "Inspect a workspace"},
        {"role": "system", "content": "Tool rejected",
         "_jack_planner_recovery_message": True},
        {"role": "assistant", "content": "Valid observation"},
    ]
    isolated = functions["_coder_isolate_planner_request"](entries, Profile())
    assert isolated[0] == {"role": "system", "content": "You are Planner."}
    assert sum(x["role"] == "user" for x in isolated) == 1
    assert len([x for x in isolated if "Tool rejected" in x["content"]]) == 1
    assert all(x["role"] != "system" for x in isolated[1:])


def test_flash_budget_is_zero_reasoning_not_zero_output():
    source = SOURCE.read_text(encoding="utf-8")
    assert 'kwargs["thinking_budget"] = 0' in source
    assert 'payload["thinking_budget_tokens"] = 0' in source
    assert 'payload["reasoning_effort"] = "none"' in source
    assert "CODER_PLANNER_FLASH_MODE and profile.name" in source
    assert 'None if CODER_PLANNER_FLASH_MODE else "xhigh"' in source
    assert '"output_budget_tokens": 100000' in source
    assert 'output_budget_tokens: int = max(0' in source
