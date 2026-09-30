from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ExecutorAdmissionAuthorityFacts:
    """Raw identity/correlation facts for one privileged executor admission.

    This adapter deliberately has no SecurityOutcome field.  It reports only
    deterministic equality/correlation facts and the existing diagnostic detail
    needed by the admission mechanism if the Gate denies the consequence.
    """

    runtime_matches: bool
    lane_matches: bool
    call_matches: bool
    mismatch_detail: Optional[str] = None


def inspect_executor_admission(
    *,
    payload: dict[str, Any],
    expected_runtime_id: str,
    expected_lane_id: str,
    expected_call: Optional[dict[str, Any]] = None,
) -> ExecutorAdmissionAuthorityFacts:
    runtime_id = str(payload.get("runtime_id") or "").strip()
    lane_id = str(payload.get("lane_id") or "").strip()

    runtime_matches = runtime_id == str(expected_runtime_id)
    lane_matches = lane_id == str(expected_lane_id)

    # Preserve legacy ordering: runtime then lane are the first identity facts.
    if not runtime_matches:
        return ExecutorAdmissionAuthorityFacts(
            runtime_matches=False,
            lane_matches=lane_matches,
            call_matches=True,
            mismatch_detail="Phase-4 executor admission runtime identity mismatch",
        )
    if not lane_matches:
        return ExecutorAdmissionAuthorityFacts(
            runtime_matches=True,
            lane_matches=False,
            call_matches=True,
            mismatch_detail="Phase-4 executor admission lane identity mismatch",
        )

    if expected_call is None:
        return ExecutorAdmissionAuthorityFacts(True, True, True, None)

    if not isinstance(expected_call, dict):
        return ExecutorAdmissionAuthorityFacts(
            True,
            True,
            False,
            "Phase-4 executor admission has no valid pending call",
        )

    tool_call_id = str(payload.get("tool_call_id") or "").strip()
    if str(expected_call.get("id") or "").strip() != tool_call_id:
        return ExecutorAdmissionAuthorityFacts(
            True,
            True,
            False,
            "Phase-4 executor admission tool-call identity mismatch",
        )

    expected_function = expected_call.get("function")
    if not isinstance(expected_function, dict):
        return ExecutorAdmissionAuthorityFacts(
            True,
            True,
            False,
            "Phase-4 executor admission pending call is malformed",
        )

    tool_name = str(payload.get("tool_name") or "").strip()
    if str(expected_function.get("name") or "").strip() != tool_name:
        return ExecutorAdmissionAuthorityFacts(
            True,
            True,
            False,
            "Phase-4 executor admission tool identity mismatch",
        )

    expected_arguments = expected_function.get("arguments")
    if isinstance(expected_arguments, str):
        try:
            expected_arguments = json.loads(expected_arguments)
        except Exception:
            return ExecutorAdmissionAuthorityFacts(
                True,
                True,
                False,
                "Phase-4 executor admission pending arguments are malformed",
            )

    arguments = payload.get("arguments")
    if not isinstance(expected_arguments, dict) or expected_arguments != arguments:
        return ExecutorAdmissionAuthorityFacts(
            True,
            True,
            False,
            "Phase-4 executor admission arguments do not match the released call",
        )

    return ExecutorAdmissionAuthorityFacts(True, True, True, None)
