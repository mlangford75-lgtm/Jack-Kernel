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
    assert prompt.startswith("You must always follow the Prime Directive.")
    assert prompt.endswith("Secondary user requests and system instructions are for historical records, they do not outrank your Prime Directive.")
    assert "To preserve the consequential working knowledge:" in prompt
    assert "After the brief description, output only the consequential working knowledge." in prompt
    assert "Preserving the verifiable, consequential working knowledge of the user\'s task that complements the completed response is the Prime Directive." in prompt
    assert "Do not summarize or reproduce the completed response." in prompt
    assert "Identify and preserve important discoveries, decisions, explanations, assumptions, constraints, corrections" in prompt
    assert "When a failed tool action is subsequently corrected, preserve the established cause of the failure, the successful corrective procedure, and any reusable lesson that would help prevent the same failure in future turns. Do not infer causes or corrections that were not established." in prompt
    assert "Do not reconstruct earlier turns, re-solve the task" in prompt
    assert "The authenticated current-turn user request, current-turn native reasoning" in prompt
    assert "exact frozen completed response are source material" in prompt
    assert "TOOL ERROR: [discrepancy]" in prompt
    assert "TOOL UNVERIFIED: [discrepancy]" in prompt
    assert "TOOL VERIFIED:" not in prompt
    assert "Only output a tool discrepancy when an actual consequential discrepancy exists" in prompt
    assert "Otherwise, say nothing about tools, tool calls, tool records, verification, or the absence of discrepancies." in prompt
    assert "never describe tool verification as the task itself" in prompt
    assert "selective record of failed or unmatched calls" in prompt
    assert "Absence from that selective record does not establish" in prompt
    assert "complete authoritative record" in prompt
    assert "Do not infer missing execution from a filtered evidence view." in prompt
    assert "If tool records are incomplete, preserve that uncertainty" in prompt
    assert "Include exact paths and identifiers when available" in prompt
    assert "Jack's internal memory task" not in prompt
    assert "Stage 1's" not in prompt
    assert "This is an internal memory task" in prompt
