"""Jack-owned, bounded one-hop Synthesis R3 -> next Thesis frontier.

Never infer R3 from model/client-supplied history. Retain exact host-generated
completed Synthesis traces for one hop, in memory, with a short lifetime.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import deque
from typing import Sequence, Mapping, Any
import time
import uuid

from jack_deep_reasoning_context import CompletedSynthesis


@dataclass(frozen=True)
class _Frontier:
    user: str
    answer: str
    reasoning: str
    created: float
    token: str


class OneHopSynthesisBridge:
    def __init__(self, *, max_entries: int = 24, ttl_seconds: int = 3600):
        if max_entries < 1 or ttl_seconds < 1:
            raise ValueError('Invalid R3 bridge bounds')
        self._frontiers: deque[_Frontier] = deque(maxlen=max_entries)
        self.ttl_seconds = ttl_seconds
        # A reservation prevents competing next-turn Thesis starts from reusing
        # the same R3 while an eligible Thesis is still generating.
        self._reserved: set[str] = set()

    def _expire(self) -> None:
        now = time.monotonic()
        self._frontiers = deque((r for r in self._frontiers if now - r.created < self.ttl_seconds), maxlen=self._frontiers.maxlen)
        self._reserved.intersection_update(r.token for r in self._frontiers)

    def publish(self, *, user_request: str, answer: str, reasoning: str) -> bool:
        self._expire()
        if not all(isinstance(v, str) and v.strip() for v in (user_request, answer, reasoning)):
            return False
        self._frontiers.append(_Frontier(user_request, answer, reasoning, time.monotonic(), uuid.uuid4().hex))
        return True

    def _matching_frontier(self, visible_history: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, str]], _Frontier | None]:
        self._expire()
        visible: list[dict[str, str]] = []
        for msg in visible_history:
            if (not isinstance(msg, Mapping) or msg.get('role') not in ('user', 'assistant')
                    or not isinstance(msg.get('content'), str)):
                raise ValueError('Bridge requires filtered visible user/assistant history')
            visible.append({'role': msg['role'], 'content': msg['content']})
        if len(visible) < 2 or [visible[-2]['role'], visible[-1]['role']] != ['user', 'assistant']:
            return visible, None
        user, answer = visible[-2]['content'], visible[-1]['content']
        matched = [r for r in self._frontiers if r.user == user and r.answer == answer]
        # Never choose a frontier under ambiguity or concurrent reservation.
        if len(matched) != 1 or matched[0].token in self._reserved:
            return visible, None
        return visible, matched[0]

    @staticmethod
    def _completed(record: _Frontier) -> CompletedSynthesis:
        return CompletedSynthesis(user_request=record.user, answer=record.answer, reasoning=record.reasoning)

    def reserve(self, visible_history: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, str]], CompletedSynthesis | None, str | None]:
        """Lease the latest matching R3 without consuming it before Thesis succeeds.

        The caller must retire(token) after a *successful* next Thesis, or
        release(token) on failed/cancelled generation. A reserved record is
        unavailable to any competing claimant and expires under the same TTL.
        """
        visible, record = self._matching_frontier(visible_history)
        if record is None:
            return visible, None, None
        self._reserved.add(record.token)
        return visible[:-2], self._completed(record), record.token

    def retire(self, token: str) -> bool:
        """Single-use deletion after the receiving Thesis finishes successfully."""
        self._expire()
        if token not in self._reserved:
            return False
        record = next((r for r in self._frontiers if r.token == token), None)
        if record is None:
            self._reserved.discard(token)
            return False
        self._frontiers.remove(record)
        self._reserved.discard(token)
        return True

    def release(self, token: str) -> None:
        """A failed Thesis may retry the same one-hop frontier before TTL."""
        self._reserved.discard(token)

    def claim(self, visible_history: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, str]], CompletedSynthesis | None]:
        """Legacy immediate single-use claim kept for existing API callers.

        The integrated Deep Reasoning driver uses reserve/retire instead.
        """
        visible, record = self._matching_frontier(visible_history)
        if record is None:
            return visible, None
        self._frontiers.remove(record)
        return visible[:-2], self._completed(record)
