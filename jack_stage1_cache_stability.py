"""Provider-neutral, observational per-work tool-stage system-prefix monitor.

Never edits canonical history or model-facing prompts. Records the initial
system-contract digest per work/stage and detects subsequent changes. All new
instructions, including pure insertions, must reach the model unchanged.
The shared backend installs authenticated tool provenance on the first request.
No system text is logged or persisted.
"""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import os
from typing import Any, Dict, List, Optional


class Stage1CacheStabilizer:
    """Shared inference-layer prefix observer for every tool-capable stage.

    Retains historical class name and method signature for compatibility.
    Eligibility follows Jack's stage profile, not a mode or provider name.
    """
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
              tool_continuation: bool, review_pending: bool = False,
              eligible: Optional[bool] = None) -> Dict[str, Any]:
        """In-place only on a private model-facing message list; never source messages."""
        decision: Dict[str, Any] = {
            'schema': 'jack.cache.stage1_stability.v1', 'stage': stage,
            'action': 'unchanged', 'reason': 'not_eligible',
        }
        # Legacy direct callers keep original Agentic Stage-1 eligibility.
        # The shared backend supplies profile.allow_tools for all modes.
        permitted = (stage == 'Agentic native pass 1') if eligible is None else bool(eligible)
        if not self.enabled or not permitted or not turn_id or review_pending:
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
        # No cache optimization may remove a host or caller instruction.
        # A pure insertion is reported but MUST be preserved on the wire.
        decision.update({
            'action': 'preserved_change',
            'reason': 'pure_insertion_preserved_on_same_work_tool_resume',
            'original_sha256_prefix': self._hash(old),
            'changed_sha256_prefix': self._hash(value),
            'insertion': insertion,
        })
        return decision
