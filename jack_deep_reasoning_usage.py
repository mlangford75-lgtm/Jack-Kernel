"""Deep Reasoning's response-local Pi context projection.

The backend and inference stages remain authoritative for aggregate compute usage.
This module observes backend request usage in a ContextVar scoped to one _run_impl
call. It does not alter backend messages, model controls, tool authorization,
stage transitions, reasoning fields, or the R3 bridge.
"""
from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResponseUsage:
    """One caller-facing HTTP response, potentially many backend generations."""

    reports: list[dict[str, int]] = field(default_factory=list)
    incomplete: bool = False

    def observe(self, raw: Any) -> None:
        if not isinstance(raw, dict):
            self.incomplete = True
            return
        try:
            # Require all keys, including explicit zero values; do not turn an
            # incomplete usage report into a plausible low estimate.
            prompt = raw["prompt_tokens"]
            completion = raw["completion_tokens"]
            total = raw["total_tokens"]
            if any(isinstance(v, bool) or not isinstance(v, int) or v < 0
                   for v in (prompt, completion, total)):
                self.incomplete = True
                return
            if total == 0:
                total = prompt + completion
            if total < prompt + completion or total <= 0:
                self.incomplete = True
                return
            self.reports.append({
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": total,
            })
        except (KeyError, TypeError, ValueError, OverflowError):
            self.incomplete = True

    def projection(self, response_local: dict[str, int]) -> dict[str, int]:
        """Never project unless the observed requests reconcile exactly."""
        if self.incomplete or not self.reports:
            return response_local
        if not isinstance(response_local, dict):
            return response_local
        totals = {
            key: sum(r[key] for r in self.reports)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        }
        try:
            if any(isinstance(response_local.get(k), bool)
                   or int(response_local.get(k, -1)) != val
                   for k, val in totals.items()):
                return response_local
        except (TypeError, ValueError, OverflowError):
            return response_local
        peak = max(self.reports, key=lambda report: report["total_tokens"])
        return dict(peak)


_ACTIVE_USAGE: contextvars.ContextVar[ResponseUsage | None] = contextvars.ContextVar(
    "jack_deep_reasoning_http_response_usage", default=None,
)


def observe_usage(raw: Any) -> None:
    current = _ACTIVE_USAGE.get()
    if current is not None:
        current.observe(raw)


def install_deep_reasoning_usage(kernel: Any, namespace: Any) -> None:
    """Attach a mode-local observation boundary without rewriting kernel stages.

    _run_impl has *already* applied usage_delta at return, so projecting here
    cannot mistakenly subtract a prior tool-checkpoint baseline from a peak.
    The streaming Pi runner also calls _run_impl and uses the same boundary.
    """
    backend = getattr(kernel, "backend", None)
    original_run_impl = getattr(kernel, "_run_impl", None)
    if (backend is None or not callable(original_run_impl)
            or not callable(getattr(backend, "chat", None))
            or not callable(getattr(backend, "chat_stream", None))):
        # Lightweight external FakeKernel objects may not implement a backend.
        return

    original_chat = backend.chat
    original_chat_stream = backend.chat_stream

    async def observed_chat(*args: Any, **kwargs: Any) -> Any:
        data = await original_chat(*args, **kwargs)
        observe_usage(data.get("usage") if isinstance(data, dict) else None)
        return data

    async def observed_chat_stream(*args: Any, **kwargs: Any):
        # One backend stream is one generation. SSE usage records are not
        # assumed to be additive. Exactly one complete usage report is safe;
        # zero or multiple reports force the conservative aggregate fallback.
        reported: list[Any] = []
        complete = False
        try:
            async for chunk in original_chat_stream(*args, **kwargs):
                if isinstance(chunk, dict) and chunk.get("usage") is not None:
                    reported.append(chunk["usage"])
                yield chunk
            complete = True
        finally:
            observe_usage(reported[0] if complete and len(reported) == 1 else None)

    async def observed_run_impl(request_body: dict[str, Any]) -> Any:
        scope = ResponseUsage()
        token = _ACTIVE_USAGE.set(scope)
        try:
            result = await original_run_impl(request_body)
            current_executor = getattr(namespace, "_phase4_current_executor_context", None)
            context = current_executor() if callable(current_executor) else None
            if (context is not None and
                    str(getattr(context, "adapter", "")).casefold() == "pi" and
                    isinstance(getattr(result, "usage", None), dict)):
                # response-local delta has ALREADY been calculated by _run_impl.
                result.usage = scope.projection(result.usage)
            return result
        finally:
            _ACTIVE_USAGE.reset(token)

    backend.chat = observed_chat
    backend.chat_stream = observed_chat_stream
    kernel._run_impl = observed_run_impl
