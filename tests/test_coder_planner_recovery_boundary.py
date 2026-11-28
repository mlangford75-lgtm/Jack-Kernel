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


def test_planner_fallback_decodes_active_response_target_serialized_text_blocks():
    """Regression: active_response_target returns JSON for structured user text."""
    functions = _load_isolated(
        "_coder_authenticated_request_text", "_coder_planner_is_host_continuation",
        "_coder_planner_host_handoff_result"
    )
    functions.update({
        "ForensicConflict": RuntimeError,
        "_content_to_text": lambda content: (
            json.dumps(content, ensure_ascii=False, separators=(",", ":"))
            if isinstance(content, list) else str(content or "")
        ),
        "_coder_unverified_observations": lambda value: value.strip(),
        "active_response_target": lambda h: {
            "history_index": 0,
            "content": json.dumps(h[0]["content"], ensure_ascii=False, separators=(",", ":"))
        },
    })
    user_text = '"C:\\\\Users\\\\example\\\\Desktop\\\\clock\\\\Agentic_Testing" is the workspace. verify its empty'
    history = [{"role": "user", "content": [{"type": "text", "text": user_text}]}]
    result = functions["_coder_planner_host_handoff_result"](history)
    spec = result["choices"][0]["message"]["content"]
    assert user_text in spec
    assert '[{"type":"text"' not in spec
    assert "Jack host recovery handoff" in spec


def test_planner_helper_leaves_literal_json_and_nontext_unchanged():
    fn = _load_isolated("_coder_authenticated_request_text")["_coder_authenticated_request_text"]
    assert fn("literal [1, 2]") == "literal [1, 2]"
    assert fn('[{"foo":"bar"}]') == '[{"foo":"bar"}]'
    visual = fn([{"type": "text", "text": "Describe image"}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;..."}}])
    assert visual.startswith("Describe image")
    assert '"type": "image_url"' in visual


def test_planner_recovery_isolated_without_promoting_host_message_to_user():
    functions = _load_isolated("_coder_isolate_planner_request", "_coder_architect_task_source")
    # Load the real framing constants alongside the isolated functions.
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in {
                "_CODER_ARCHITECT_TASK_SOURCE_HEADER", "_CODER_ARCHITECT_TASK_SOURCE_FOOTER"
            } for target in node.targets
        ):
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), functions)
    functions.update({
        "AGENTIC_CODER_MODE": True,
        "ForensicConflict": RuntimeError,
        "_content_to_text": str,
    })
    class Profile:
        name = "Agentic Coder Planner"
        prompt = "You are Planner."
        allow_tools = False
    entries = [
        {"role": "system", "content": "Caller-owned system"},
        {"role": "user", "content": "Inspect a workspace"},
        {"role": "assistant", "content": "Valid observation"},
        {"role": "assistant", "content": "Planner invalid tool proposal",
         "_jack_internal_tool_validation_checkpoint": True},
        {"role": "user", "content": "Rejected tool; try again",
         "_jack_internal_tool_validation_rejection": True},
        {"role": "user", "content": "Jack empty stream recovery",
         "_jack_internal_protocol_recovery": True},
        {"role": "system", "content": "Tool rejected",
         "_jack_planner_recovery_message": True},
    ]
    original = json.loads(json.dumps(entries))
    isolated = functions["_coder_isolate_planner_request"](entries, Profile())
    assert entries == original
    assert isolated[0] == {"role": "system", "content": "You are Planner."}
    assert isolated[1:] == [
        {"role": "user", "content": (
            functions["_CODER_ARCHITECT_TASK_SOURCE_HEADER"] + "Inspect a workspace"
            + functions["_CODER_ARCHITECT_TASK_SOURCE_FOOTER"]
        )},
        {"role": "assistant", "content": "Valid observation"},
    ]


def test_flash_disables_thinking_without_forcing_zero_budget_or_output_limit():
    source = SOURCE.read_text(encoding="utf-8")
    assert 'kwargs["thinking_budget"] = 0' not in source
    assert 'payload["thinking_budget_tokens"] = 0' not in source
    assert 'payload["reasoning_effort"] = "none"' in source
    assert '"enable_thinking": profile.thinking' in source
    assert '"preserve_thinking": effective_preserve' in source
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


def test_rejected_inspection_stops_tool_retries_but_preserves_evidence():
    functions = _load_isolated(
        "_coder_planner_mutation_rejected", "_coder_planner_tools_for_attempt"
    )
    functions.update({
        "_coder_planner_rejection_count": lambda h: sum(
            bool(item.get("_jack_internal_coder_planner_rejection")) for item in h
        ),
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
    assert functions["_coder_planner_tools_for_attempt"](history, offered) == []
    # This retained helper alone can select inspection tools; the current
    # Architect profile is independently required to be tool-free.
    assert functions["_coder_planner_tools_for_attempt"](
        [{"role": "user", "content": "Inspect"}], offered
    ) == offered


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


def test_flash_and_thorough_planner_profiles_keep_independent_output():
    source = SOURCE.read_text(encoding="utf-8")
    assert 'not CODER_PLANNER_FLASH_MODE,' in source
    assert 'None if CODER_PLANNER_FLASH_MODE else "xhigh"' in source
    assert 'output_budget_tokens: int = max(0' in source
    assert 'kwargs["thinking_budget"] = 0' not in source
    assert 'payload["thinking_budget_tokens"] = 0' not in source


def test_empty_planner_recovery_hands_off_instead_of_terminal_failure():
    source = SOURCE.read_text(encoding="utf-8")
    marker = 'detail=(f"Stage {profile.name} produced neither a final answer nor a "'
    index = source.index(marker)
    prior = source[index - 1000:index]
    assert 'if AGENTIC_CODER_MODE and stage_key == "coder_planner":' in prior
    assert '_coder_planner_host_handoff_result(history, message["content"])' in prior
    assert 'yield {"kind": "result", "data": fallback}' in prior
