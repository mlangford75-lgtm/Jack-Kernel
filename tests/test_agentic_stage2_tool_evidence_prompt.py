"""Guard Jack's Agentic Stage 2 memory directive against unintended rewrites."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "jack_kernel.py"

def _prompt():
    module = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "_AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION" for target in node.targets):
                return ast.literal_eval(node.value)
    raise AssertionError("Agentic Stage 2 prompt not found")

def test_memory_contract_and_tool_classifications():
    prompt = _prompt()
    boundary = "Begin with a brief description of the current task (a short sentence)"
    assert prompt.startswith(boundary + ".")
    assert prompt.endswith(boundary + " and then preserve the consequential working knowledge.")
    assert "Preserve the important working knowledge established for the current user request" in prompt
    assert "Do not reconstruct earlier turns, re-solve the task" in prompt
    assert "The user request, prior reasoning, and completed response are source material" in prompt
    assert "TOOL ERROR: [discrepancy]" in prompt
    assert "TOOL UNVERIFIED: [discrepancy]" in prompt
    assert "TOOL VERIFIED: Supported" in prompt
    assert "complete tool record" in prompt
    assert "If tool records are incomplete, preserve that uncertainty" in prompt
    assert "Include exact paths and identifiers when available" in prompt
    assert "Jack's internal memory task" not in prompt
    assert "Stage 1's" not in prompt
    assert "This is an internal memory task" in prompt
