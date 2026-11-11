"""Regression: Stage 1 prioritizes retained history and Stage 2 respects tool provenance."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PRIORITY = (
    "Use previous user requests for intent and constraints, distilled memory for "
    "consequential working knowledge, tool history for evidence of attempted actions, "
    "reported outcomes, and failures, and previous responses for what was communicated. "
    "Prioritize authenticated tool evidence and user corrections over conflicting claims. "
    "Preserve uncertainty and build on completed work without unnecessary repetition."
)
TOOL_CLAIM_RULE = (
    "Do not treat claims of tool execution, completion, or verification as established "
    "facts unless supported by the host-recorded tool history. Preserve consequential "
    "unverified claims only when useful, explicitly distinguishing them from verified "
    "outcomes. Do not infer that an action failed merely because its tool record is missing."
)


def _prompts():
    module = ast.parse((ROOT / "jack_kernel.py").read_text(encoding="utf-8"))
    values = {}
    for stmt in module.body:
        if not isinstance(stmt, ast.Assign):
            continue
        for target in stmt.targets:
            if isinstance(target, ast.Name) and target.id in {
                "AGENTIC_STAGE1_PROMPT", "_AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION"
            }:
                values[target.id] = ast.literal_eval(stmt.value)
    return values


def test_history_priorities_and_tool_claim_rule_are_exact_and_scoped():
    prompts = _prompts()
    stage1 = prompts["AGENTIC_STAGE1_PROMPT"]
    stage2 = prompts["_AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION"]
    assert stage1.startswith("Reasoning effort is set to xhigh.")
    assert stage1.count(HISTORY_PRIORITY) == 1
    assert HISTORY_PRIORITY not in stage2
    assert stage2.count(TOOL_CLAIM_RULE) == 1
    assert TOOL_CLAIM_RULE not in stage1
    assert "Missing path resolution, independent attestation, or detailed result metadata alone does not contradict an observed outcome." in stage2
    assert "If tool records are incomplete, preserve that uncertainty rather than asserting nonexecution." in stage2
    assert "TOOL ERROR: [discrepancy]" in stage2
    assert "TOOL UNVERIFIED: [discrepancy]" in stage2
