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

def test_memory_contract_and_user_approved_tool_flags():
    prompt = _prompt()
    boundary = "Begin with a brief description of the current task and how it relates to the user request."
    assert prompt.startswith(boundary)
    assert prompt.endswith(boundary)
    assert "To preserve the consequential working knowledge:" in prompt
    assert "After the brief description, preserve the consequential working knowledge." in prompt
    assert "Preserving the verifiable working knowledge of the user\'s task is the prime directive." in prompt
    assert "Do not simply repeat what has been stated. Capture the meaningful information that will help an agentic system extract the important information related to this user request." in prompt
    assert "Preserve the important working knowledge established for the current user request" in prompt
    assert "Do not reconstruct earlier turns, re-solve the task" in prompt
    assert "The user request, prior reasoning, and completed response are source material" in prompt
    assert "TOOL ERROR: [discrepancy]" in prompt
    assert "TOOL UNVERIFIED: [discrepancy]" in prompt
    assert "TOOL VERIFIED:" not in prompt
    assert "Only output a tool discrepancy when an actual consequential discrepancy exists" in prompt
    assert "Otherwise, say nothing about tools, tool calls, tool records, verification, or the absence of discrepancies." in prompt
    assert "never describe tool verification as the task itself" in prompt
    assert "between what the output says and what can be verified" in prompt
    assert "complete tool record" in prompt
    assert "If tool records are incomplete, preserve that uncertainty" in prompt
    assert "Include exact paths and identifiers when available" in prompt
    assert "Jack's internal memory task" not in prompt
    assert "Stage 1's" not in prompt
    assert "This is an internal memory task" in prompt
