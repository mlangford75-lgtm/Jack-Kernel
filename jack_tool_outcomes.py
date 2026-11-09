"""Mode-independent normalization of *reported* tool execution outcomes.

Jack does not execute agent tools. These signals originate from the caller/executor
and are not authenticated proof that a task succeeded or a claim is correct.
Do not infer execution failure from natural-language tool-result text.
Every future Jack-mediated mode can use this contract without special cases.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SUCCESS = "SUCCESS"
FAILED = "FAILED"
UNKNOWN = "UNKNOWN"


def reported_tool_outcome(message: Any) -> str:
    """Return SUCCESS, FAILED, or UNKNOWN from explicit structured signals.

    A contradictory report is FAILED (conservative precedence). Ordinary text
    including error-looking words must not be interpreted as a status.
    """
    if not isinstance(message, Mapping):
        return UNKNOWN
    reported = str(message.get("tool_outcome") or "").strip().upper()
    status = str(message.get("status") or "").strip().lower()
    failure = (
        message.get("is_error") is True
        or message.get("isError") is True
        or message.get("success") is False
        or reported == FAILED
        or status in {"error", "failed", "failure"}
        or message.get("error") not in (None, False, "", {}, [])
    )
    exit_codes = []
    for item in (message, message.get("details")):
        if isinstance(item, Mapping):
            for key in ("exit_code", "exitCode"):
                value = item.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    exit_codes.append(value)
    if any(code != 0 for code in exit_codes):
        failure = True
    if failure:
        return FAILED
    success = (
        message.get("is_error") is False
        or message.get("isError") is False
        or message.get("success") is True
        or reported == SUCCESS
        or status in {"ok", "success", "succeeded", "completed"}
        or any(code == 0 for code in exit_codes)
    )
    return SUCCESS if success else UNKNOWN
