from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, Optional, Tuple


PROVENANCE_VERSION = 1
BLOCKED_MARKER = "[UNTRUSTED_MODEL_OUTPUT:JACK_TOOL_EVIDENCE_MARKER_BLOCKED]"
EVIDENCE_ORIGIN_CALLER_TOOL_RESULT = "caller_supplied_tool_result"
EVIDENCE_ORIGIN_PI_SESSION_RECOVERY = "pi_session_recovery"
EVIDENCE_ORIGIN_HOST_INTERNAL = "host_internal"
EVIDENCE_ORIGIN_UNKNOWN = "unknown"

# Model-originated text may never claim Jack's host-owned evidence namespace.
# Recognition is structural rather than literal so transport chunking and
# whitespace inserted inside the reserved identifier cannot bypass it.
_RESERVED_TAG_NAME = "jack_tool_evidence_receipt"
_PARTIAL_RESERVED_PREFIX = "jack_tool_evidence"


class ReservedEvidenceMarkerFilter:
    """Stateful structural filter for model-emitted reserved Jack evidence tags."""

    def __init__(self) -> None:
        self._carry = ""

    @staticmethod
    def _skip_whitespace(fragment: str, index: int) -> int:
        while index < len(fragment) and fragment[index].isspace():
            index += 1
        return index

    @classmethod
    def _classify_candidate(
        cls,
        fragment: str,
        *,
        final: bool,
    ) -> Tuple[str, int]:
        """Classify a possible raw or HTML-escaped reserved tag."""
        if not fragment:
            return "safe", 0

        lower = fragment.lower()

        if fragment.startswith("<"):
            index = 1
            safe_delimiter_length = 1
        elif lower.startswith("&lt;"):
            index = 4
            safe_delimiter_length = 4
        elif "&lt;".startswith(lower):
            if not final:
                return "hold", 0
            return "safe", len(fragment)
        else:
            return "safe", 1

        index = cls._skip_whitespace(fragment, index)
        if index >= len(fragment):
            return ("hold", 0) if not final else ("safe", len(fragment))

        if fragment[index] == "/":
            index += 1
            index = cls._skip_whitespace(fragment, index)
            if index >= len(fragment):
                return ("hold", 0) if not final else ("safe", len(fragment))

        matched = 0
        while matched < len(_RESERVED_TAG_NAME):
            index = cls._skip_whitespace(fragment, index)
            if index >= len(fragment):
                if not final:
                    return "hold", 0
                if matched >= len(_PARTIAL_RESERVED_PREFIX):
                    return "block", len(fragment)
                return "safe", len(fragment)
            if fragment[index].lower() != _RESERVED_TAG_NAME[matched]:
                return "safe", safe_delimiter_length
            matched += 1
            index += 1

        scan = index
        lower = fragment.lower()
        while scan < len(fragment):
            if fragment[scan] == ">":
                return "block", scan + 1
            if lower.startswith("&gt;", scan):
                return "block", scan + 4
            tail_lower = lower[scan:]
            if "&gt;".startswith(tail_lower) and not final:
                return "hold", 0
            scan += 1

        if final:
            return "block", len(fragment)
        return "hold", 0

    def feed(self, text: Any) -> str:
        data = self._carry + ("" if text is None else str(text))
        self._carry = ""
        if not data:
            return ""

        out = []
        pos = 0
        while pos < len(data):
            raw_index = data.find("<", pos)
            escaped_index = data.find("&", pos)
            candidates = [index for index in (raw_index, escaped_index) if index >= 0]
            if not candidates:
                out.append(data[pos:])
                break

            index = min(candidates)
            out.append(data[pos:index])
            status, consumed = self._classify_candidate(data[index:], final=False)
            if status == "hold":
                self._carry = data[index:]
                break
            if status == "block":
                out.append(BLOCKED_MARKER)
                pos = index + consumed
                continue

            release = max(1, consumed)
            out.append(data[index:index + release])
            pos = index + release

        return "".join(out)

    def flush(self) -> str:
        tail = self._carry
        self._carry = ""
        if not tail:
            return ""
        status, consumed = self._classify_candidate(tail, final=True)
        if status == "block":
            return BLOCKED_MARKER + tail[consumed:]
        return tail


def sanitize_model_text(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    filt = ReservedEvidenceMarkerFilter()
    return filt.feed(value) + filt.flush()


def _encode_sse_object(obj: Dict[str, Any]) -> bytes:
    return ("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8")


def _parse_sse_object(chunk: Any) -> Optional[Dict[str, Any]]:
    text = chunk.decode("utf-8", "replace") if isinstance(chunk, (bytes, bytearray)) else str(chunk)
    stripped = text.strip()
    if not stripped.startswith("data:") or stripped == "data: [DONE]":
        return None
    raw = stripped[5:].strip()
    try:
        obj = json.loads(raw)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _chat_chunk_template(obj: Dict[str, Any]) -> Dict[str, Any]:
    return {key: obj[key] for key in ("id", "object", "created", "model") if key in obj}


def _flush_event(
    template: Optional[Dict[str, Any]],
    filters: Dict[Tuple[int, str], ReservedEvidenceMarkerFilter],
) -> Optional[bytes]:
    if not template:
        for filt in filters.values():
            filt.flush()
        return None

    by_choice: Dict[int, Dict[str, str]] = {}
    for (choice_index, field), filt in filters.items():
        tail = filt.flush()
        if tail:
            by_choice.setdefault(choice_index, {})[field] = tail
    if not by_choice:
        return None

    choices = [
        {"index": index, "delta": delta, "finish_reason": None}
        for index, delta in sorted(by_choice.items())
    ]
    return _encode_sse_object({**template, "choices": choices})


async def _guarded_stream(original_stream: Any, request_body: Dict[str, Any]) -> AsyncIterator[bytes]:
    filters: Dict[Tuple[int, str], ReservedEvidenceMarkerFilter] = {}
    last_template: Optional[Dict[str, Any]] = None
    done_seen = False

    async for chunk in original_stream(request_body):
        text = chunk.decode("utf-8", "replace") if isinstance(chunk, (bytes, bytearray)) else str(chunk)
        if text.strip() == "data: [DONE]":
            flushed = _flush_event(last_template, filters)
            if flushed is not None:
                yield flushed
            done_seen = True
            yield chunk
            continue

        obj = _parse_sse_object(chunk)
        if obj is None:
            yield chunk
            continue

        choices = obj.get("choices")
        if not isinstance(choices, list) or not choices:
            yield chunk
            continue

        last_template = _chat_chunk_template(obj)
        changed = False
        for ordinal, choice in enumerate(choices):
            if not isinstance(choice, dict):
                continue
            raw_index = choice.get("index", ordinal)
            try:
                choice_index = int(raw_index)
            except (TypeError, ValueError):
                choice_index = ordinal

            delta = choice.get("delta")
            if not isinstance(delta, dict):
                continue

            for field in ("content", "reasoning_content", "reasoning", "thinking"):
                if field not in delta or delta.get(field) is None:
                    continue
                key = (choice_index, field)
                filt = filters.setdefault(key, ReservedEvidenceMarkerFilter())
                filtered = filt.feed(delta.get(field))
                if filtered != delta.get(field):
                    changed = True
                delta[field] = filtered

            if choice.get("finish_reason") is not None:
                for field in ("content", "reasoning_content", "reasoning", "thinking"):
                    key = (choice_index, field)
                    filt = filters.get(key)
                    if filt is None:
                        continue
                    tail = filt.flush()
                    if tail:
                        delta[field] = str(delta.get(field) or "") + tail
                        changed = True

        yield _encode_sse_object(obj) if changed else chunk

    if not done_seen:
        flushed = _flush_event(last_template, filters)
        if flushed is not None:
            yield flushed


def _normalized_evidence_origin(value: Any) -> str:
    origin = str(value or "").strip().lower()
    if origin in {
        EVIDENCE_ORIGIN_CALLER_TOOL_RESULT,
        EVIDENCE_ORIGIN_PI_SESSION_RECOVERY,
        EVIDENCE_ORIGIN_HOST_INTERNAL,
    }:
        return origin
    return EVIDENCE_ORIGIN_UNKNOWN


def _receipt_group_origin(group: Any, call_id: str) -> str:
    if not isinstance(group, list):
        return EVIDENCE_ORIGIN_UNKNOWN
    matched = []
    for item in group:
        if not isinstance(item, dict) or item.get("role") != "tool":
            continue
        if str(item.get("tool_call_id") or "").strip() != call_id:
            continue
        matched.append(_normalized_evidence_origin(item.get("_jack_evidence_origin")))
    if not matched:
        return EVIDENCE_ORIGIN_UNKNOWN
    unique = set(matched)
    return matched[0] if len(unique) == 1 else EVIDENCE_ORIGIN_UNKNOWN


def _receipt_with_origin(content: Any, origin: str) -> str:
    text = "" if content is None else str(content)
    if "Evidence Origin:" in text:
        return text
    line = f"Evidence Origin: {origin}"
    rows = text.splitlines()
    if rows and rows[0].strip().lower() == "<jack_tool_evidence_receipt>":
        rows.insert(1, line)
        return "\n".join(rows)
    return line + ("\n" + text if text else "")


def _install_receipt_provenance(jk: Any) -> None:
    original = getattr(jk, "_tool_evidence_receipts_from_group", None)
    if original is None or getattr(original, "_jack_provenance_guard", False):
        return

    def guarded(group: Any):
        receipts = original(group)
        if isinstance(receipts, list):
            for receipt in receipts:
                if isinstance(receipt, dict) and receipt.get("_jack_tool_evidence_receipt"):
                    call_id = str(receipt.get("_jack_tool_call_id") or "").strip()
                    origin = _receipt_group_origin(group, call_id)
                    receipt["content"] = _receipt_with_origin(receipt.get("content"), origin)
                    receipt["_jack_evidence_source"] = "jack_kernel"
                    receipt["_jack_evidence_type"] = "tool_result_receipt"
                    receipt["_jack_evidence_host_generated"] = True
                    receipt["_jack_evidence_provenance_version"] = PROVENANCE_VERSION
                    receipt["_jack_evidence_origin"] = origin
        return receipts

    guarded._jack_provenance_guard = True
    jk._tool_evidence_receipts_from_group = guarded


def _install_tool_result_origin(jk: Any) -> None:
    kernel = getattr(jk, "KERNEL", None)
    original = getattr(kernel, "_consume_pending_tool_resume", None)
    if original is None or getattr(original, "_jack_provenance_guard", False):
        return

    async def guarded(messages: Any):
        result = await original(messages)
        if not result:
            return result
        state, tool_messages = result
        if isinstance(tool_messages, list):
            for item in tool_messages:
                if isinstance(item, dict) and item.get("role") == "tool":
                    item["_jack_evidence_origin"] = EVIDENCE_ORIGIN_CALLER_TOOL_RESULT
        return state, tool_messages

    guarded._jack_provenance_guard = True
    kernel._consume_pending_tool_resume = guarded


def _install_recovery_provenance(jk: Any) -> None:
    original = getattr(jk, "recover_pi_tool_evidence", None)
    if original is None or getattr(original, "_jack_provenance_guard", False):
        return

    def guarded(tool_call_id: str, expected_sha256: Optional[str] = None):
        evidence = original(tool_call_id, expected_sha256)
        if not isinstance(evidence, dict):
            return evidence
        return {
            **evidence,
            "evidence_source": "jack_kernel",
            "evidence_type": "recovered_tool_result",
            "host_generated": True,
            "provenance_version": PROVENANCE_VERSION,
            "evidence_origin": EVIDENCE_ORIGIN_PI_SESSION_RECOVERY,
        }

    guarded._jack_provenance_guard = True
    jk.recover_pi_tool_evidence = guarded


def install(jk: Any) -> None:
    """Install Jack's model-output/evidence provenance boundary exactly once."""
    if getattr(jk, "_JACK_EVIDENCE_PROVENANCE_GUARD_INSTALLED", False):
        return
    jk._JACK_EVIDENCE_PROVENANCE_GUARD_INSTALLED = True

    kernel = jk.KERNEL
    original_run = kernel.run
    original_stream = kernel.stream

    async def guarded_run(request_body: Dict[str, Any]):
        result = await original_run(request_body)
        if getattr(result, "content", None) is not None:
            result.content = sanitize_model_text(result.content)
        if getattr(result, "reasoning_content", None) is not None:
            result.reasoning_content = sanitize_model_text(result.reasoning_content)
        return result

    async def guarded_stream(request_body: Dict[str, Any]):
        async for chunk in _guarded_stream(original_stream, request_body):
            yield chunk

    kernel.run = guarded_run
    kernel.stream = guarded_stream

    _install_tool_result_origin(jk)
    _install_receipt_provenance(jk)
    _install_recovery_provenance(jk)
