"""Regressions for Coder Planner host recovery and Flash reasoning controls."""
import ast
import json
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
    namespace = {"Any": Any, "Dict": Dict, "List": List, "json": json}
    exec(compile(ast.fix_missing_locations(ast.Module(
        body=selected, type_ignores=[])), str(SOURCE), "exec"), namespace)
    return namespace


def test_planner_fallback_extracts_plain_authenticated_request_and_retains_findings():
    functions = _load_isolated(
        "_coder_authenticated_request_text", "_coder_planner_is_host_continuation",
        "_coder_planner_host_handoff_result"
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


def test_rejected_mutation_gets_one_tools_off_spec_chance():
    functions = _load_isolated(
        "_coder_planner_mutation_rejected", "_coder_planner_tools_for_attempt"
    )
    functions.update({
        "_coder_planner_rejection_count": lambda h: 1,
        "_coder_planner_repeated_inspection_pending": lambda h: False,
        "_coder_planner_tools": lambda available: available,
        "active_response_target": lambda h: {"history_index": 0},
    })
    history = [
        {"role": "user", "content": "Make an SVG"},
        {"role": "user", "content": "Planner write rejected",
         "_jack_internal_coder_planner_mutation_rejected": True},
    ]
    assert functions["_coder_planner_tools_for_attempt"](
        history, [{"type": "function", "function": {"name": "bash"}}]
    ) == []
    assert not functions["_coder_planner_mutation_rejected"](
        [{"role": "user", "content": "Make an SVG"}]
    )


def test_rejected_read_only_inspection_remains_correctable():
    functions = _load_isolated(
        "_coder_planner_mutation_rejected", "_coder_planner_tools_for_attempt"
    )
    functions.update({
        "_coder_planner_rejection_count": lambda h: 1,
        "_coder_planner_repeated_inspection_pending": lambda h: False,
        "_coder_planner_tools": lambda available: available,
        "active_response_target": lambda h: {"history_index": 0},
    })
    offered = [{"type": "function", "function": {"name": "bash"}}]
    history = [
        {"role": "user", "content": "Inspect"},
        {"role": "user", "content": "Inspection rejected",
         "_jack_internal_coder_planner_rejection": True},
    ]
    assert functions["_coder_planner_tools_for_attempt"](history, offered) == offered


def test_host_instruction_is_not_accepted_as_planner_spec():
    functions = _load_isolated(
        "_coder_planner_is_host_continuation", "_coder_spec_text"
    )
    functions.update({
        "_coder_unverified_observations": lambda text: text.strip(),
        "LOG": type("Quiet", (), {"warning": lambda *args: None})(),
    })
    spec, fallback = functions["_coder_spec_text"](
        "If the task is complete, output the final answer.", "Real user task"
    )
    assert fallback is True
    assert spec == "Real user task"
    spec, fallback = functions["_coder_spec_text"](
        "Inspect the project directory and deliver a report.", "Real user task"
    )
    assert fallback is False
    assert "Inspect" in spec


def test_flash_stage_runtime_zero_reasoning_without_output_limit():
    functions = _load_isolated("_agentic_zero_reasoning")
    from types import SimpleNamespace
    functions.update({
        "AGENTIC_MODE": True,
        "AGENTIC_FLASH_MODE": False,
        "AGENTIC_BALANCED_MODE": False,
        "AGENTIC_TRANSLATED_MODE": False,
        "CODER_PLANNER_FLASH_MODE": True,
    })
    planner = SimpleNamespace(name="Agentic Coder Planner", thinking=False)
    memory = SimpleNamespace(name="Agentic native pass 2", thinking=False)
    coder = SimpleNamespace(name="Agentic native pass 1", thinking=True)
    assert functions["_agentic_zero_reasoning"](planner) is True
    assert functions["_agentic_zero_reasoning"](memory) is True
    assert functions["_agentic_zero_reasoning"](coder) is False
    # Output is intentionally controlled independently of backend thinking.
    assert "max_tokens=0" not in SOURCE.read_text(encoding="utf-8")[
        SOURCE.read_text(encoding="utf-8").index("def _agentic_zero_reasoning"):
        SOURCE.read_text(encoding="utf-8").index("def _agentic_translated_generation_profile")
    ]
