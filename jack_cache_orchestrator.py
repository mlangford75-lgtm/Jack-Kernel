"""Universal, optional, provider-aware KV-cache lane routing for Jack Kernel.

Cache identity is host-only: no prompt, tool history, or model-visible Work ID
is modified. Logical lanes express preferences, not a promise of physical KV
retention. Explicit slot control is opt-in and limited to configured providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import json
import os


POLICIES = frozenset({"auto", "shared", "prefer_isolated"})


@dataclass(frozen=True)
class CacheDecision:
    stage: str
    lane: str
    policy: str
    base_url: str
    primary_base_url: str
    slot_id: Optional[int]
    reason: str
    alternate_endpoint: bool = False


class CacheOrchestrator:
    """Bounded stage-aware routing: no cache content or private prompt stored.

    `auto` isolates the auxiliary lane when the preceding primary context is
    above the configured rough byte threshold. `prefer_isolated` does so
    whenever a capability is explicitly configured. `shared` sends no hints.

    The primary lane deliberately sticks to its configured slot even when the
    last tool returned an error. A tool outcome never selects a cache lane.
    """

    def __init__(self, cfg: Any):
        def setting(attr: str, env: str, default: Any) -> Any:
            return getattr(cfg, attr, os.getenv(env, default))

        self.primary = str(cfg.backend_base_url).rstrip("/")
        self.alternate = str(setting("cache_aux_base_url", "JACK_CACHE_AUX_BASE_URL", "") or "").strip().rstrip("/")
        self.policy = str(setting("cache_policy", "JACK_CACHE_POLICY", "auto") or "auto").strip().lower()
        if self.policy not in POLICIES:
            self.policy = "auto"
        self.slot_adapter = str(setting("cache_slot_adapter", "JACK_CACHE_SLOT_ADAPTER", "off") or "off").strip().lower()
        self.backend_profile = str(getattr(cfg, "backend_profile", "") or "").strip().lower()
        # Only the raw llama.cpp backend is eligible for explicitly requested
        # llama.cpp slot hints. Never send undocumented hints to LM Studio.
        self.slot_capable = (
            self.slot_adapter == "llamacpp"
            and self.backend_profile == "llamacpp"
            and int(getattr(cfg, "max_concurrent_requests", 1) or 1) == 1
        )
        self.primary_slot = self._slot(setting("cache_primary_slot", "JACK_CACHE_PRIMARY_SLOT", 0))
        self.aux_slot = self._slot(setting("cache_aux_slot", "JACK_CACHE_AUX_SLOT", 1))
        if self.primary_slot == self.aux_slot or self.primary_slot is None or self.aux_slot is None:
            self.slot_capable = False
        try:
            self.min_bytes = max(0, int(setting("cache_min_primary_bytes", "JACK_CACHE_MIN_PRIMARY_BYTES", 8192) or 0))
        except (TypeError, ValueError):
            self.min_bytes = 8192
        configured_stages = str(setting("cache_aux_stages", "JACK_CACHE_AUX_STAGES", "Agentic native pass 2") or "")
        self.aux_stages = frozenset(x.strip() for x in configured_stages.split(";") if x.strip())
        self._previous_primary_bytes: Dict[str, int] = {}
        self._unsupported_slot = False
        self._unavailable_aux = False

    @staticmethod
    def _slot(value: Any) -> Optional[int]:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if 0 <= number <= 65535 else None

    @staticmethod
    def _rough_message_bytes(messages: Any) -> int:
        try:
            return len(json.dumps(messages, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"))
        except (ValueError, TypeError):
            return 0

    def plan(self, stage: str, model: str, messages: Any) -> CacheDecision:
        lane = "auxiliary" if stage in self.aux_stages else "primary"
        if lane == "primary":
            self._previous_primary_bytes[model] = self._rough_message_bytes(messages)
        previous_size = self._previous_primary_bytes.get(model, 0)
        should_isolate = self.policy == "prefer_isolated" or (
            self.policy == "auto" and previous_size >= self.min_bytes
        )
        if self.policy == "shared":
            return CacheDecision(stage, lane, self.policy, self.primary, self.primary,
                                 None, "shared_backend_selection")
        if (lane == "auxiliary" and should_isolate and not self._unavailable_aux
                and self.alternate and self.alternate != self.primary):
            return CacheDecision(stage, lane, self.policy, self.alternate, self.primary,
                                 None, "separate_backend_endpoint", alternate_endpoint=True)
        if self.slot_capable and not self._unsupported_slot:
            # Stage 1 always uses the same pinned slot. Stage 2 remains on a
            # different slot only when isolation is worth the cost or requested.
            slot = self.primary_slot if lane == "primary" else (self.aux_slot if should_isolate else None)
            if slot is not None:
                return CacheDecision(stage, lane, self.policy, self.primary, self.primary,
                                     slot, "explicit_llamacpp_slot_requested")
        return CacheDecision(stage, lane, self.policy, self.primary, self.primary,
                             None, "backend_managed_fallback")

    @staticmethod
    def apply_hint(payload: Dict[str, Any], decision: CacheDecision) -> None:
        if decision.slot_id is not None:
            payload["id_slot"] = decision.slot_id

    def disable_unavailable_aux(self) -> None:
        """Stop routing to an optional unavailable auxiliary endpoint."""
        self._unavailable_aux = True

    def disable_unsupported_hint(self) -> None:
        """Stop requesting slots after an explicit unsupported-field rejection."""
        self._unsupported_slot = True

    @staticmethod
    def strip_hint(payload: Dict[str, Any]) -> Dict[str, Any]:
        cloned = dict(payload)
        cloned.pop("id_slot", None)
        return cloned

    @staticmethod
    def diagnostic(decision: CacheDecision) -> str:
        return json.dumps({
            "schema": "jack.cache.route.v1", "stage": decision.stage,
            "lane": decision.lane, "policy": decision.policy,
            "transport": decision.reason,
            "slot_requested": decision.slot_id,
            "alternate_endpoint": decision.alternate_endpoint,
            "kv_cache_hit": "unknown",
        }, sort_keys=True)
