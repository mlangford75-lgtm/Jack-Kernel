"""Regression checks for Coder Planner read-only tool admission.

The model may propose varied valid inspection syntax; Jack must admit those
without weakening the authority boundary or executing shell mutations.
"""
import ast
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "jack_kernel.py"


def _guard():
    # Compile only the validator, avoiding live-server import side effects.
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef)
                and n.name == "_coder_planner_safe_inspection_command")
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    import re
    from typing import Any
    scope = {
        "Any": Any,
        "re": re,
        "_CODER_PLANNER_SHELL_BAD": frozenset(";\\n\\r|&><$(){}!" + chr(96)),
    }
    exec(compile(module, str(SOURCE), "exec"), scope)
    return scope[node.name]


@pytest.mark.parametrize("command", [
    "pwd",
    "ls -la",
    'ls -la "C:/Users/example/Desktop/clock/Agentic_Testing"',
    "pwd && ls -la",
    'find "C:/Users/example/Desktop/clock/Agentic_Testing" -mindepth 1 | wc -l',
    'find . -type f -name "*.py" -print',
    'find . -maxdepth 2 -type d',
    "rg --files",
    'rg -n "class Planner" .',
    'grep -R -n "TODO" .',
    "ls -la | wc -l",
    "git --no-optional-locks status --short",
    "git diff --stat",
    "git log --oneline -5",
    "git rev-parse --show-toplevel",
    "git ls-files",
    "command -v python",
    "stat -c %s file.txt",
])
def test_read_only_inspections_admitted(command):
    assert _guard()(command), command


@pytest.mark.parametrize("command", [
    "touch changed.txt",
    "rm -rf .",
    "mkdir new",
    "git add .",
    "git checkout main",
    "git reset --hard",
    "git config core.hooksPath .",
    "python -c 'open(\"file\",\"w\").write(\"bad\")'",
    'find . -exec touch pwned \\;',
    'find . -delete',
    'find . -fprint output.txt',
    "ls -la > output.txt",
    "ls -la | tee output.txt",
    "ls -la || touch bad",
    "ls -la && rm -rf .",
    "ls -la; echo bad",
    "ls -la $(touch bad)",
    "ls -la `touch bad`",
    "git -c core.pager=sh status",
    "git diff --ext-diff",
    "git status --untracked-files=all",
    "command -v python && python -c 'print(1)'",
])
def test_mutating_or_ambiguous_commands_denied(command):
    assert not _guard()(command), command
