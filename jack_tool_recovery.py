"""Universal, turn-local tool recovery. Never grants tool execution authority.

All counters are host-owned. A failed external tool counts only when Pi supplies
an explicit FAILED outcome; unknown results are not guessed to be successes.
The same object is checkpointed across tool-result API requests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Dict, List, Optional

SOFT_ATTEMPTS = 5
STRONG_ATTEMPTS = 15
HARD_ATTEMPTS = 25


def operation_key(call: Any) -> str:
    if not isinstance(call, dict):
        return "unknown"
    func = call.get("function") if isinstance(call.get("function"), dict) else {}
    name = str(func.get("name") or call.get("name") or "unknown").strip().lower()[:64] or "unknown"
    arguments = func.get("arguments")
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
    except (ValueError, TypeError):
        args = None
    if not isinstance(args, dict):
        return name
    for key in ("path", "file_path", "file", "target", "url"):
        if isinstance(args.get(key), str) and args[key].strip():
            return name + ":" + args[key].strip().replace("\\", "/").lower()[:180]
    command = next((args.get(k) for k in ("command", "cmd", "script")
                    if isinstance(args.get(k), str) and args[k].strip()), None)
    if command:
        # A shell method may change arguments while still targeting one script.
        script = re.search(r"(?i)([^\s'\";|]+\.py)(?:\s|$)", command)
        if script:
            return name + ":script:" + script.group(1).lower()[:180]
        parts = str(command).split()
        return name + ":command:" + " ".join(parts[:2]).lower()[:180]
    return name


@dataclass
class ToolRecoveryState:
    consecutive_failures: int = 0
    same_operation_failures: int = 0
    current_operation: str = ""
    last_error: str = ""
    exhausted: bool = False
    events: List[Dict[str, str]] = field(default_factory=list)
    successful_calls: List[Dict[str, str]] = field(default_factory=list)
    seen_tool_ids: set[str] = field(default_factory=set)

    def fail(self, operation: str, error: str, *, call_id: str = "") -> int:
        """Count an actual unsuccessful attempt, never a generated reasoning thought."""
        if call_id and call_id in self.seen_tool_ids:
            return self.consecutive_failures
        if call_id:
            self.seen_tool_ids.add(call_id)
        operation = str(operation or "unknown")[:240]
        if operation == self.current_operation:
            self.same_operation_failures += 1
        else:
            self.current_operation = operation
            self.same_operation_failures = 1
        self.consecutive_failures += 1
        self.last_error = str(error or "unspecified failure").strip()[:500]
        self.events.append({
            "attempt": str(self.consecutive_failures),
            "operation": operation,
            "error": self.last_error,
            "call_id": call_id[:96],
        })
        self.events = self.events[-HARD_ATTEMPTS:]
        self.exhausted = self.consecutive_failures >= HARD_ATTEMPTS
        return self.consecutive_failures

    def progress(self, operation: str, *, call_id: str = "") -> None:
        """Only a host-reported successful tool result resets the failed streak."""
        if call_id and call_id in self.seen_tool_ids:
            return
        if call_id:
            self.seen_tool_ids.add(call_id)
        self.successful_calls.append({
            "operation": str(operation or "unknown")[:240],
            "call_id": call_id[:96],
            "evidence": "host-reported tool success; inspect output for substantive verification",
        })
        self.successful_calls = self.successful_calls[-20:]
        self.consecutive_failures = 0
        self.same_operation_failures = 0
        self.current_operation = ""
        self.last_error = ""
        self.events.clear()
        self.exhausted = False

    def advice(self) -> str:
        n = self.consecutive_failures
        if n == SOFT_ATTEMPTS:
            return (
                "This operation has failed repeatedly. Consider a different "
                "authorized method or a corrected use of the current tool. "
                "Preserve completed work and continue toward the user request."
            )
        if n == STRONG_ATTEMPTS:
            return (
                "Repeated recovery has not produced progress. Strongly reconsider "
                "the method, inspect the last real tool errors, and try a different "
                "authorized approach where appropriate. Preserve all successful "
                "results. Never bypass a security denial."
            )
        return ""

    def host_report(self) -> str:
        lines = [
            "[JACK RECOVERY_EXHAUSTED_WITH_HANDOFF — TASK INCOMPLETE]",
            "The tool recovery hard ceiling was reached after "
            f"{self.consecutive_failures} consecutive unsuccessful attempts.",
            "No more tool execution is authorized for this turn.",
            "Most recent failed operation: " + (self.current_operation or "unknown"),
            "Last error: " + (self.last_error or "unknown"),
            "The following records come from host-observed tool outcomes. "
            "A reported success is not proof that a requested deliverable is correct.",
            "Last failed attempts:",
        ]
        for event in self.events[-10:]:
            lines.append(
                "  - #" + event["attempt"] + " " + event["operation"]
                + ": " + event["error"]
                + (" [call " + event["call_id"] + "]" if event["call_id"] else "")
            )
        lines.append("Reported successful tool calls:")
        if self.successful_calls:
            for event in self.successful_calls[-12:]:
                lines.append("  - " + event["operation"] + " [call "
                             + (event["call_id"] or "unknown") + "]")
        else:
            lines.append("  - None recorded by this recovery tracker.")
        return "\n".join(lines) + "\n\n"

    def handoff_instruction(self) -> str:
        return (
            "[JACK INTERNAL RECOVERY HANDOFF — NOT A NEW USER REQUEST]\n"
            "The kernel has exhausted its authorized tool-recovery attempts. "
            "Do not issue ANY tool calls. Produce a concise, usable handoff "
            "based on the user request, successful tool evidence, and the "
            "recorded failures. Clearly separate completed and verified work, "
            "attempted but unverified work, the exact blocker and failed "
            "approaches, files/artifacts still present, remaining work, and "
            "a practical next action for the next turn. Never claim success "
            "without tool evidence, and never invent results. Report the task "
            "as INCOMPLETE.\n"
            + self.host_report()
        )


class ToolRecoveryExhausted(Exception):
    """Internal control outcome: a terminal, useful handoff rather than HTTP 502."""

    def __init__(
        self, *, state: ToolRecoveryState,
        history: List[Dict[str, Any]], stage_key: str,
        secondary_system: str, usage: Dict[str, int],
    ) -> None:
        super().__init__("tool recovery exhausted; produce incomplete-turn handoff")
        self.state = state
        self.history = list(history)
        self.stage_key = stage_key
        self.secondary_system = secondary_system
        self.usage = dict(usage)
