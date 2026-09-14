from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, Optional, Tuple


PROVENANCE_VERSION = 1
BLOCKED_MARKER = "[UNTRUSTED_MODEL_OUTPUT:JACK_TOOL_EVIDENCE_MARKER_BLOCKED]"
_RESERVED_MARKERS: Tuple[str, ...] = (
    "<jack_tool_evidence_receipt>",
    "</jack_tool_evidence_receipt>",
    "&lt;jack_tool_evidence_receipt&gt;",
    "&lt;/jack_tool_evidence_receipt&gt;",
    "<jack_tool_evidence_receipt",
    "</jack_tool_evidence_receipt",
    "&lt;jack_tool_evidence_receipt",
    "&lt;/jack_tool_evidence_receipt",
)
_RESERVED_MARKERS_LOWER = tuple(marker.lower() for marker in _RESERVED_MARKERS)


class ReservedEvidenceMarkerFilter:
    """Stateful filter for model-emitted text crossing a streaming boundary."""

    def __init__(self) -> None:
        self._carry = ""

    @staticmethod
    def _suffix_prefix_length(text: str) -> int:
        lower = text.lower()
        best = 0
        for marker in _RESERVED_MARKERS_LOWER:
            limit = min(len(marker) - 1, len(lower))
            for size in range(limit, best, -1):
                if lower.endswith(marker[:size]):
                    best = size
                    break
        return best

    def feed(self, text: Any) -> str:
        data = self._carry + ("" if text is None else str(text))
        self._carry = ""
        if not data:
            return ""

        lower = data.lower()
        out = []
        pos = 0
        while pos < len(data):
            hits = []
            for marker, marker_lower in zip(_RESERVED_MARKERS, _RESERVED_MARKERS_LOWER):
                index = lower.find(marker_lower, pos)
                if index >= 0:
                    hits.append((index, -len(marker), marker))
            if hits:
                index, _neg_len, marker = min(hits)
                out.append(data[pos:index])
                out.append(BLOCKED_MARKER)
                pos = index + len(marker)
                continue

            tail = data[pos:]
            keep = self._suffix_prefix_length(tail)
            if keep:
                out.append(tail[:-keep])
                self._carry = tail[-keep:]
            else:
                out.append(tail)
            break
        return "".join(out)

    def flush(self) -> str:
        tail = self._carry
        self._carry = ""
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
    return {
        key: obj[key]
        for key in ("id", "object", "created", "model")
        if key in obj
    }


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


def _install_receipt_provenance(jk: Any) -> None:
    original = getattr(jk, "_tool_evidence_receipts_from_group", None)
    if original is None or getattr(original, "_jack_provenance_guard", False):
        return

    def guarded(group: Any):
        receipts = original(group)
        if isinstance(receipts, list):
            for receipt in receipts:
                if isinstance(receipt, dict) and receipt.get("_jack_tool_evidence_receipt"):
                    receipt["_jack_evidence_source"] = "jack_kernel"
                    receipt["_jack_evidence_type"] = "tool_result_receipt"
                    receipt["_jack_evidence_host_generated"] = True
                    receipt["_jack_evidence_provenance_version"] = PROVENANCE_VERSION
        return receipts

    guarded._jack_provenance_guard = True
    jk._tool_evidence_receipts_from_group = guarded


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

    _install_receipt_provenance(jk)
    _install_recovery_provenance(jk)
