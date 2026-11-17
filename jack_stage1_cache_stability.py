"""Experimental, provider-neutral per-work Stage-1 system-prefix stabilization.

Never edits canonical history, prompts on the first inference, or Stage 2.
When a later Stage-1 tool continuation contains ONLY a pure insertion into its
system text, retain the originally-authorized system text for that same work ID.
Replacement/removal, changed message role, unrecognized work, or non-tool stages
are deliberately left alone. No system text is logged or persisted.
"""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import os
from typing import Any, Dict, List, Optional


class Stage1CacheStabilizer:
    def __init__(self, enabled: Optional[bool] = None, max_turns: int = 8):
        self.enabled = (os.getenv('JACK_STAGE1_CACHE_STABILITY', '1').strip().lower()
                        not in {'0', 'off', 'no', 'false'}) if enabled is None else bool(enabled)
        self.max_turns = max(1, min(int(max_turns), 32))
        self._first: 'OrderedDict[str, str]' = OrderedDict()

    @staticmethod
    def _insertion(old: str, new: str) -> Optional[Dict[str, int]]:
        """Only accept a single nonempty pure insertion, with no changed old bytes."""
        if len(new) <= len(old):
            return None
        i = 0
        limit = min(len(old), len(new))
        while i < limit and old[i] == new[i]:
            i += 1
        delta = len(new) - len(old)
        if new[i+delta:] != old[i:]:
            return None
        return {'character_offset': i, 'inserted_characters': delta}

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]

    def apply(self, *, stage: str, turn_id: Optional[str], messages: List[Dict[str, Any]],
              tool_continuation: bool, review_pending: bool = False) -> Dict[str, Any]:
        """In-place only on a private model-facing message list; never source messages."""
        decision: Dict[str, Any] = {
            'schema': 'jack.cache.stage1_stability.v1', 'stage': stage,
            'action': 'unchanged', 'reason': 'not_eligible',
        }
        if not self.enabled or stage != 'Agentic native pass 1' or not turn_id or review_pending:
            return decision
        if not isinstance(messages, list) or not messages or not isinstance(messages[0], dict):
            return decision
        first = messages[0]
        if first.get('role') != 'system' or not isinstance(first.get('content'), str):
            return decision
        value = first['content']
        old = self._first.get(turn_id)
        if old is None:
            if tool_continuation:
                decision['reason'] = 'no_original_stage1_snapshot'
                return decision
            self._first[turn_id] = value
            self._first.move_to_end(turn_id)
            while len(self._first) > self.max_turns:
                self._first.popitem(last=False)
            decision['action'] = 'snapshot'
            decision['reason'] = 'first_stage1_request'
            return decision
        self._first.move_to_end(turn_id)
        if not tool_continuation:
            decision['reason'] = 'not_tool_continuation'
            return decision
        if old == value:
            decision['reason'] = 'already_stable'
            return decision
        insertion = self._insertion(old, value)
        if insertion is None:
            decision['reason'] = 'non_insert_change_preserved'
            return decision
        # Protect original system authority from a continuation-specific insertion.
        # Caller and Jack controls on the FIRST request are retained byte-for-byte.
        # The added fragment is suppressed only in the model-facing copy.
        first['content'] = old
        decision.update({
            'action': 'stabilized', 'reason': 'pure_insertion_on_same_work_tool_resume',
            'original_sha256_prefix': self._hash(old),
            'changed_sha256_prefix': self._hash(value),
            'insertion': insertion,
        })
        return decision
