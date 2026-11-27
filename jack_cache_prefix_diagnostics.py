"""Diagnostics-only, provider-neutral UTF-8 prompt-prefix probe.

No prompt content is logged or persisted. A process-local keyed prefix digest
allows exact byte-offset comparisons within a bounded capture window. Neither
inference payloads nor cache routing are changed by this module.
"""
from __future__ import annotations

from array import array
import hashlib
import json
import os
from typing import Any, Dict, Iterable, List, Optional, Sequence


class CacheBytePrefixProbe:
    SCHEMA = "jack.cache.byte_prefix.v1"

    def __init__(self, enabled: Optional[bool] = None, byte_cap: Optional[int] = None):
        if enabled is None:
            enabled = os.getenv("JACK_CACHE_PREFIX_BYTE_DIAGNOSTICS", "1").strip().lower() not in {
                "0", "false", "off", "no"
            }
        self.enabled = bool(enabled)
        if byte_cap is None:
            try:
                byte_cap = int(os.getenv("JACK_CACHE_PREFIX_BYTE_CAP", "131072"))
            except ValueError:
                byte_cap = 131072
        self.byte_cap = max(1024, min(int(byte_cap), 262144))
        # Key remains process-local; digest trajectories cannot reproduce text.
        self._key = os.urandom(24)
        self._last_by_stage: Dict[str, Dict[str, Any]] = {}
        self._last: Optional[Dict[str, Any]] = None

    @staticmethod
    def _signature_index(*snapshots: Optional[Dict[str, Any]]) -> Dict[tuple, Dict[str, Any]]:
        """Temporary lookup over already retained digest-only snapshots.

        Capture length is part of the identity: reusing a shorter trajectory
        must never reduce the diagnostic coverage of a subsequent observation.
        No new long-lived registry, raw prompt bytes, or cross-probe sharing.
        """
        index = {}
        for snapshot in snapshots:
            if snapshot is None:
                continue
            signatures = list(snapshot["messages"])
            if snapshot.get("system") is not None:
                signatures.append(snapshot["system"])
            signatures.extend(region["sig"] for region in snapshot.get("regions", ()))
            for signature in signatures:
                key = (signature["sha256"], signature["byte_length"],
                       len(signature["prefix_hashes"]))
                index.setdefault(key, signature)
        return index

    def _signature(self, wire: bytes, capture_limit: Optional[int] = None,
                   *, reuse: Optional[Dict[tuple, Dict[str, Any]]] = None) -> Dict[str, Any]:
        limit = self.byte_cap if capture_limit is None else max(0, min(self.byte_cap, int(capture_limit)))
        digest = hashlib.sha256(wire).hexdigest()
        key = (digest, len(wire), min(limit, len(wire)))
        if reuse is not None:
            existing = reuse.get(key)
            if existing is not None:
                return existing
        limited = wire[:limit]
        h = hashlib.blake2b(digest_size=8, key=self._key)
        sigs = array("Q")
        for item in limited:
            h.update(bytes((item,)))
            sigs.append(int.from_bytes(h.copy().digest(), "little"))
        signature = {
            "byte_length": len(wire),
            "sha256": digest,
            "prefix_hashes": sigs,
        }
        if reuse is not None:
            reuse[key] = signature
        return signature

    def capture_regions(
        self, stage_messages: Sequence[Dict[str, Any]],
        prepared_messages: Sequence[Dict[str, Any]], stage_system: str,
    ) -> List[Dict[str, Any]]:
        """Capture provenance BEFORE Jack consolidates model-facing system roles."""
        if not self.enabled:
            return []
        reuse = self._signature_index(self._last, *self._last_by_stage.values())
        source_ids = {id(item) for item in prepared_messages if isinstance(item, dict)}
        result = []
        stage_seen = False
        caller_ordinal = 0
        injected_ordinal = 0
        for entry in stage_messages:
            if not isinstance(entry, dict) or entry.get("role") != "system":
                continue
            content = entry.get("content")
            if not isinstance(content, str):
                continue
            if (not stage_seen and stage_system and content == stage_system
                    and id(entry) not in source_ids):
                label = "jack_stage_directive"
                stage_seen = True
            elif id(entry) in source_ids:
                caller_ordinal += 1
                label = f"caller_or_source_system_{caller_ordinal}"
            else:
                injected_ordinal += 1
                label = f"jack_injected_system_{injected_ordinal}"
            result.append({"label": label, "sig": self._signature(content.encode("utf-8"), reuse=reuse)})
        return result

    def _offset(self, before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
        old_hashes, new_hashes = before["prefix_hashes"], after["prefix_hashes"]
        n = min(len(old_hashes), len(new_hashes))
        i = 0
        while i < n and old_hashes[i] == new_hashes[i]:
            i += 1
        if i < n:
            return {"common_utf8_prefix_bytes": i, "first_differing_utf8_byte_offset": i,
                    "offset_status": "exact_within_capture_cap"}
        if before["sha256"] == after["sha256"] and before["byte_length"] == after["byte_length"]:
            return {"common_utf8_prefix_bytes": before["byte_length"],
                    "first_differing_utf8_byte_offset": None, "offset_status": "identical"}
        # One message may be an append-only extension of the other; lengths
        # alone do not establish a prefix match past the hashed cap.
        if i < self.byte_cap and (
            before["byte_length"] == i or after["byte_length"] == i
        ):
            return {"common_utf8_prefix_bytes": i,
                    "first_differing_utf8_byte_offset": i,
                    "offset_status": "one_message_ended_at_offset"}
        return {"common_utf8_prefix_bytes": i,
                "first_differing_utf8_byte_offset": None,
                "offset_status": "unknown_beyond_capture_cap"}

    def _regions_compare(self, old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
        before, after = old.get("regions", []), new.get("regions", [])
        a_labels = [x["label"] for x in before]
        b_labels = [x["label"] for x in after]
        count = min(len(before), len(after))
        for idx in range(count):
            a, b = before[idx], after[idx]
            if (a["label"], a["sig"]["sha256"], a["sig"]["byte_length"]) != (
                b["label"], b["sig"]["sha256"], b["sig"]["byte_length"]
            ):
                detail = self._offset(a["sig"], b["sig"])
                return {
                    "first_changed_pre_fold_region": b["label"],
                    "prior_region_label": a["label"],
                    "region_index": idx,
                    "region_byte_difference": detail,
                    "prior_region_bytes": a["sig"]["byte_length"],
                    "current_region_bytes": b["sig"]["byte_length"],
                }
        if len(before) != len(after):
            return {
                "first_changed_pre_fold_region": (
                    after[count]["label"] if count < len(after) else "removed_region"
                ),
                "region_index": count,
                "prior_region_count": len(before),
                "current_region_count": len(after),
                "prior_region_labels": a_labels,
                "current_region_labels": b_labels,
            }
        return {"first_changed_pre_fold_region": None, "region_count": len(after)}

    def _compare(self, previous: Optional[Dict[str, Any]], current: Dict[str, Any]) -> Dict[str, Any]:
        if previous is None:
            return {"relation": "no_prior_observation"}
        left, right = previous["messages"], current["messages"]
        matched = 0
        while (matched < len(left) and matched < len(right)
               and left[matched]["sha256"] == right[matched]["sha256"]
               and left[matched]["byte_length"] == right[matched]["byte_length"]):
            matched += 1
        if matched == len(left) == len(right):
            return {"relation": "identical_messages", "matched_messages": matched}
        if matched == len(left):
            return {"relation": "append_only", "matched_messages": matched}
        if matched == len(right):
            return {"relation": "shortened", "matched_messages": matched}
        relation = "first_message_changed" if matched == 0 else "middle_changed"
        first = self._offset(left[matched], right[matched])
        report = {
            "relation": relation,
            "matched_messages": matched,
            "first_changed_message_index": matched,
            "first_changed_message_json": first,
            "prior_message_json_bytes": left[matched]["byte_length"],
            "current_message_json_bytes": right[matched]["byte_length"],
        }
        if matched == 0 and previous.get("system") and current.get("system"):
            report["first_system_content_utf8"] = self._offset(previous["system"], current["system"])
            report["pre_fold_system_regions"] = self._regions_compare(previous, current)
        return report

    def observe(
        self, stage_messages: Sequence[Dict[str, Any]], stage: str,
        regions: Sequence[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Report offsets only; do not touch stage_messages or output prompt text."""
        if not self.enabled:
            return None
        reuse = self._signature_index(self._last_by_stage.get(str(stage)), self._last)
        for region in regions:
            signature = region["sig"]
            reuse.setdefault((signature["sha256"], signature["byte_length"],
                              len(signature["prefix_hashes"])), signature)
        first = stage_messages[0] if stage_messages else None
        system = None
        if isinstance(first, dict) and first.get("role") == "system" and isinstance(first.get("content"), str):
            system = self._signature(first["content"].encode("utf-8"), reuse=reuse)
        # Bound total retained digest trajectories even for very long histories.
        remaining = self.byte_cap * 2
        message_sigs = []
        for message in stage_messages:
            # Serialize one message at a time rather than retaining a duplicate
            # byte representation of the complete request alongside its hashes.
            m = json.dumps(message, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), default=str).encode("utf-8")
            capture = min(remaining, len(m))
            message_sigs.append(self._signature(m, capture, reuse=reuse))
            remaining -= capture
        current = {
            "messages": message_sigs,
            "system": system,
            "regions": list(regions),
            "stage": str(stage),
        }
        result = {
            "schema": self.SCHEMA,
            "stage": stage,
            "capture_cap_utf8_bytes_per_field": self.byte_cap,
            "data_retention": "process_local_keyed_prefix_digests_only",
            "same_stage": self._compare(self._last_by_stage.get(str(stage)), current),
            "immediately_preceding": self._compare(self._last, current),
            "measurement": "model_facing_message_json_and_system_utf8_not_backend_tokens_or_KV",
        }
        self._last_by_stage[str(stage)] = current
        self._last = current
        return result
