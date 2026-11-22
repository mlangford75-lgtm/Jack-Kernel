"""Regression tests for stage-boundary handling in Coder Agentic modes.

Extract small pure helpers with AST so this file has no runtime/server side effects.
The AST parse also rejects malformed jack_kernel.py before any assertions run.
"""
import ast
import re
from pathlib import Path

import pytest


SOURCE_PATH = Path(__file__).resolve().parents[1] / "jack_kernel.py"


def helpers(*names):
    tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"), filename=str(SOURCE_PATH))
    nodes = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert all(name in nodes for name in names), f"Missing helper(s): {set(names) - nodes.keys()}"
    module = ast.fix_missing_locations(ast.Module(body=[nodes[name] for name in names], type_ignores=[]))
    namespace = {
        "re": re,
        "_coder_planner_checkpoint_text": lambda value: value.strip(),
        "_AGENTIC_SOURCE_ONLY_WORKING_STATE_TRIGGER": (
            "Jack internal memory extraction, not a new user request. "
            "Distill durable working state from the frozen source only. "
            "Do not answer, resume reasoning, or describe the original task."
        ),
    }
    exec(compile(module, str(SOURCE_PATH), "exec"), namespace)
    return namespace


@pytest.mark.parametrize("output", [
    "<tool_call>\n<function=list_files>\n<parameter=path>\nx\n</parameter>\n</function>\n</tool_call>",
    "I'll inspect the folder.\n[shell_inspect]\nls -la",
    "<|tool_call>call:bash{command:\"ls -la\"}<|tool_call|>",
    " <function=write>\nfile\n",
])
def test_simulated_planner_tool_markup_is_detected(output):
    ns = helpers("_coder_planner_has_simulated_tool_markup")
    assert ns["_coder_planner_has_simulated_tool_markup"](output)


@pytest.mark.parametrize("output", [
    "Identify the file layout and describe acceptance criteria to Coder.",
    "Check the project layout using read-only inspection tools if needed.",
    "The design may require a shell inspection, but no execution is needed here.",
    "Use a component named tool_call_parser; it is ordinary project terminology.",
])
def test_normal_architect_text_is_not_rejected(output):
    ns = helpers("_coder_planner_has_simulated_tool_markup")
    assert not ns["_coder_planner_has_simulated_tool_markup"](output)


def test_xml_tool_markup_is_removed_but_real_prose_survives():
    ns = helpers("_coder_unverified_observations")
    output = (
        "Inspect the workspace before implementation.\n"
        "<tool_call>\n<function=list_files>\n<parameter=path>x</parameter>\n"
        "</function>\n</tool_call>\n"
        "Coder must verify that the directory is empty."
    )
    filtered = ns["_coder_unverified_observations"](output)
    assert "<tool_call>" not in filtered
    assert "<function=" not in filtered
    assert "Inspect the workspace" in filtered
    assert "Coder must verify" in filtered


def test_shell_inspect_markup_is_not_forwarded():
    ns = helpers("_coder_unverified_observations")
    output = "Inspect project.\n[shell_inspect]\nls -la\nCoder must verify."
    filtered = ns["_coder_unverified_observations"](output)
    assert "shell_inspect" not in filtered
    assert "ls -la" not in filtered
    assert "Inspect project." in filtered
    assert "Coder must verify." in filtered


def test_exact_stage2_instruction_echo_is_rejected():
    ns = helpers("_agentic_memory_is_instruction_echo")
    trigger = ns["_AGENTIC_SOURCE_ONLY_WORKING_STATE_TRIGGER"]
    assert ns["_agentic_memory_is_instruction_echo"](trigger)
    assert ns["_agentic_memory_is_instruction_echo"]("\n" + trigger + "  \n")
    assert ns["_agentic_memory_is_instruction_echo"](trigger + "\n" + "Jack internal memory extraction")


def test_real_memory_with_verified_observation_is_not_rejected():
    ns = helpers("_agentic_memory_is_instruction_echo")
    assert not ns["_agentic_memory_is_instruction_echo"](
        "C:/workspace verified empty: ls -la returned only . and ..; find returned 0."
    )
    assert not ns["_agentic_memory_is_instruction_echo"](
        "Retained data: Stage 2 uses a source-data trigger and the tool observation was verified."
    )


def test_both_stage2_commit_paths_use_echo_guard():
    source = SOURCE_PATH.read_text(encoding="utf-8")
    assert source.count("if _agentic_memory_is_instruction_echo(") == 2
    assert source.count("Agentic Stage 2 echoed its host instruction") == 2


def test_planner_handoff_retains_original_unmodified_output():
    source = SOURCE_PATH.read_text(encoding="utf-8")
    assert '"_jack_coder_original_planner_output": raw' in source
    assert '"_jack_coder_goal_fallback": fallback' in source
    assert '_coder_planner_host_handoff_result(' in source
