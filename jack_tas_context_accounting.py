"""Read-only, opt-in model-facing request accounting for Deep Reasoning TAS.

No payload mutation, inference policy, tool admission, model text, native reasoning,
raw prompts, token IDs, or digests of user data are logged. UTF-8 byte counts are
not token counts or evidence of backend KV-cache reuse.
"""
from __future__ import annotations

import json
import os
from typing import Any, Mapping, Sequence

_STAGE_LABELS = {
    "Deep Reasoning Thesis pass 1": "thesis",
    "Deep Reasoning Antithesis pass 2": "antithesis",
    "Deep Reasoning Synthesis pass 3": "synthesis",
}


def _byte_len(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                          default=str).encode("utf-8"))


def _content_bytes(value: Any) -> int:
    return len(value.encode("utf-8")) if isinstance(value, str) else (
        _byte_len(value) if value is not None else 0
    )


def measure_tas_request(messages: Sequence[Mapping[str, Any]],
                        payload: Mapping[str, Any], stage_name: str) -> dict[str, Any]:
    """Measure the final serialized request without returning any content.

    Calling code must supply backend-ready messages and payload; this function
    never changes, retains, or logs the input objects.
    """
    if stage_name not in _STAGE_LABELS:
        raise ValueError("Not a TAS stage")
    roles = {r: 0 for r in ("system", "developer", "user", "assistant", "tool", "other")}
    content_bytes = {r: 0 for r in roles}
    reasoning_fields = ("reasoning_content", "reasoning", "thinking")
    native_reasoning_field_bytes = 0
    native_reasoning_messages = 0
    tool_call_field_bytes = 0
    for message in messages:
        if not isinstance(message, Mapping):
            roles["other"] += 1
            continue
        role = message.get("role")
        role = role if isinstance(role, str) and role in roles else "other"
        roles[role] += 1
        content_bytes[role] += _content_bytes(message.get("content"))
        live_fields = [message[field] for field in reasoning_fields
                       if isinstance(message.get(field), str)]
        if live_fields:
            native_reasoning_messages += 1
            native_reasoning_field_bytes += sum(_content_bytes(v) for v in live_fields)
        if "tool_calls" in message:
            tool_call_field_bytes += _byte_len(message["tool_calls"])
    return {
        "schema": "jack.tas.context.v1",
        "stage": _STAGE_LABELS[stage_name],
        "messages": len(messages),
        "roles": roles,
        "content_bytes_by_role": content_bytes,
        "native_reasoning_messages": native_reasoning_messages,
        "native_reasoning_field_bytes": native_reasoning_field_bytes,
        "tool_call_field_bytes": tool_call_field_bytes,
        "tool_schema_bytes": _byte_len(payload.get("tools")) if payload.get("tools") else 0,
        "messages_json_bytes": _byte_len(messages),
        "request_json_bytes": _byte_len(payload),
    }


def emit_tas_context_report(messages: Sequence[Mapping[str, Any]],
                            payload: Mapping[str, Any], stage_name: str, logger: Any) -> None:
    """Fail open. Logging failure cannot change, block, or repeat inference."""
    if os.environ.get("JACK_TAS_CONTEXT_ACCOUNTING", "").strip().lower() not in (
        "1", "true", "yes", "on"
    ):
        return
    if stage_name not in _STAGE_LABELS:
        return
    try:
        report = measure_tas_request(messages, payload, stage_name)
        logger.info("TAS context accounting: %s", json.dumps(report, sort_keys=True))
    except Exception as exc:
        try:
            logger.warning("TAS context accounting unavailable: %s", type(exc).__name__)
        except Exception:
            pass  # Observability must never block the backend request.
