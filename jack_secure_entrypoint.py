from __future__ import annotations

import logging
import sys
import threading
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, Optional

import jack_authority_ledger as authority_ledger
import jack_kernel as jk


LOG = logging.getLogger("jack-kernel.phase8-ledger")


class Phase8LedgerEventType(str, Enum):
    SOURCE_AUTHORITY_SUSPENDED = "SOURCE_AUTHORITY_SUSPENDED"
    SOURCE_AUTHORITY_RESTORED = "SOURCE_AUTHORITY_RESTORED"
    SOURCE_DRIFT_DETECTED = "SOURCE_DRIFT_DETECTED"


def _record_phase8_source_event_failsoft(
    ledger: authority_ledger.AuthorityLedger,
    *,
    event_type: Phase8LedgerEventType,
    authority: Any,
    prior_state: str,
    new_state: str,
    reason: str,
    mismatched_component_ids: tuple[str, ...] = (),
    unavailable_component_ids: tuple[str, ...] = (),
) -> bool:
    """Append an already-established source fact without gaining authority over it."""

    try:
        baseline = authority.baseline
        ledger._advance(
            event_type=event_type,
            producer_code="phase8.source_authority",
            boundary="source_authority_lifecycle",
            outcome=new_state,
            containment_scope="source_authority",
            fact_type="SourceAuthorityTransitionFact",
            payload={
                "baseline_instance_id": baseline.baseline_instance_id,
                "baseline_sha256": baseline.aggregate_sha256,
                "prior_state": prior_state,
                "new_state": new_state,
                "reason": reason,
                "mismatched_component_ids": tuple(mismatched_component_ids),
                "unavailable_component_ids": tuple(unavailable_component_ids),
            },
        )
        return True
    except authority_ledger.LedgerAuthorityFrozen:
        return False
    except Exception as exc:
        try:
            ledger.freeze_authority(
                f"Phase-8D source-event recording failure: {type(exc).__name__}"
            )
        except Exception:
            pass
        LOG.exception(
            "Phase-8D source-event recording failed; source authority remains unchanged"
        )
        return False


class _Phase8OrderedLedgerObserver:
    """Append immutable source transition facts in source-established order.

    Source authority owns transition identity and sequencing. This observer owns
    only a small post-transition ordering buffer so thread scheduling after the
    source lock is released cannot invert the forensic ledger history.

    Observation is deliberately fail-soft. Unexpected observer failures may lose
    forensic records, but they must never become source-verification, recovery,
    or admission failures.
    """

    def __init__(
        self,
        *,
        ledger: authority_ledger.AuthorityLedger,
        authority: Any,
        next_transition_sequence: int,
    ) -> None:
        self._ledger = ledger
        self._authority = authority
        self._lock = threading.RLock()
        self._next_sequence = int(next_transition_sequence)
        self._pending: dict[int, dict[str, Any]] = {}
        self._disabled = False

    def disable(self) -> None:
        """Disable forensic observation without changing source authority."""

        with self._lock:
            self._disabled = True
            self._pending.clear()

    def observe(
        self,
        *,
        transition_sequence: int,
        event_type: Phase8LedgerEventType,
        prior_state: str,
        new_state: str,
        reason: str,
        mismatched_component_ids: tuple[str, ...] = (),
        unavailable_component_ids: tuple[str, ...] = (),
    ) -> None:
        try:
            sequence = int(transition_sequence)
            if sequence < 1:
                return
            event = {
                "event_type": event_type,
                "prior_state": prior_state,
                "new_state": new_state,
                "reason": reason,
                "mismatched_component_ids": tuple(mismatched_component_ids),
                "unavailable_component_ids": tuple(unavailable_component_ids),
            }

            with self._lock:
                if self._disabled or sequence < self._next_sequence:
                    return
                self._pending.setdefault(sequence, event)
                while self._next_sequence in self._pending:
                    current = self._pending.pop(self._next_sequence)
                    try:
                        _record_phase8_source_event_failsoft(
                            self._ledger,
                            authority=self._authority,
                            **current,
                        )
                    except Exception:
                        # The normal recorder is already fail-soft. This outer
                        # containment prevents even an unexpected observer bug
                        # from becoming backpressure on source authority.
                        LOG.exception(
                            "Phase-8D observer append failed unexpectedly; "
                            "source authority remains unchanged"
                        )
                    finally:
                        # Forensic failure must not stall later source chronology
                        # or turn a lost record into unbounded observer backlog.
                        self._next_sequence += 1
        except Exception:
            # A malformed/unexpected observer-local condition degrades only the
            # forensic observer. Source lifecycle and enforcement remain usable.
            try:
                self.disable()
            except Exception:
                pass
            LOG.exception(
                "Phase-8D observer processing failed and was disabled; "
                "source authority remains unchanged"
            )


def _state_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "")


def _install_phase8_ledger_observer(jk_module: Any, authority: Any) -> bool:
    """Observe immutable source transition facts after the source guard establishes them.

    The source guard remains the sole verifier/lifecycle owner. The observer never
    samples source state to reconstruct a transition and never acquires the source
    authority lock. Ledger recording happens only after the source transition fact
    has been returned and is fail-soft with respect to enforcement and recovery.
    """

    if getattr(jk_module, "_JACK_PHASE8_LEDGER_OBSERVER_INSTALLED", False):
        return True

    ledger = getattr(jk_module, "_JACK_AUTHORITY_LEDGER", None)
    if not isinstance(ledger, authority_ledger.AuthorityLedger):
        LOG.warning(
            "Phase-8D ledger observer unavailable: active AuthorityLedger not found"
        )
        return False

    if (
        str(getattr(ledger, "runtime_id", "") or "").strip()
        != str(getattr(authority, "runtime_id", "") or "").strip()
        or str(getattr(ledger, "lane_id", "") or "").strip()
        != str(getattr(authority, "lane_id", "") or "").strip()
    ):
        LOG.warning(
            "Phase-8D ledger observer unavailable: ledger/source ownership mismatch"
        )
        return False

    current_verify = getattr(authority, "verify_now", None)
    current_suspend = getattr(authority, "_suspend_unverified", None)
    if not callable(current_verify) or not callable(current_suspend):
        LOG.warning(
            "Phase-8D ledger observer unavailable: source lifecycle seams not callable"
        )
        return False

    try:
        next_transition_sequence = int(getattr(authority, "transition_sequence")) + 1
    except Exception:
        LOG.warning(
            "Phase-8D ledger observer unavailable: source transition sequence unavailable"
        )
        return False

    recorder = _Phase8OrderedLedgerObserver(
        ledger=ledger,
        authority=authority,
        next_transition_sequence=next_transition_sequence,
    )

    if not getattr(current_verify, "_jack_phase8_ledger_observer", False):
        original_verify = current_verify

        @wraps(original_verify)
        def observed_verify_now(*args: Any, **kwargs: Any):
            result = original_verify(*args, **kwargs)
            try:
                prior_state = _state_value(getattr(result, "prior_state", ""))
                new_state = _state_value(getattr(result, "state", ""))
                if not prior_state or prior_state == new_state:
                    return result

                transition_sequence = int(
                    getattr(result, "transition_sequence", 0) or 0
                )
                mismatched = tuple(
                    str(item)
                    for item in getattr(result, "mismatched_component_ids", ()) or ()
                )
                unavailable = tuple(
                    str(item)
                    for item in getattr(result, "unavailable_component_ids", ()) or ()
                )

                if new_state == "INVALIDATED":
                    recorder.observe(
                        transition_sequence=transition_sequence,
                        event_type=Phase8LedgerEventType.SOURCE_DRIFT_DETECTED,
                        prior_state=prior_state,
                        new_state=new_state,
                        reason="confirmed_source_mismatch",
                        mismatched_component_ids=mismatched,
                        unavailable_component_ids=unavailable,
                    )
                elif new_state == "SUSPENDED_UNVERIFIED":
                    recorder.observe(
                        transition_sequence=transition_sequence,
                        event_type=Phase8LedgerEventType.SOURCE_AUTHORITY_SUSPENDED,
                        prior_state=prior_state,
                        new_state=new_state,
                        reason="measurement_unavailable",
                        mismatched_component_ids=mismatched,
                        unavailable_component_ids=unavailable,
                    )
                elif prior_state == "SUSPENDED_UNVERIFIED" and new_state == "ACTIVE":
                    recorder.observe(
                        transition_sequence=transition_sequence,
                        event_type=Phase8LedgerEventType.SOURCE_AUTHORITY_RESTORED,
                        prior_state=prior_state,
                        new_state=new_state,
                        reason="exact_reverification",
                        mismatched_component_ids=mismatched,
                        unavailable_component_ids=unavailable,
                    )
            except Exception:
                try:
                    recorder.disable()
                except Exception:
                    pass
                LOG.exception(
                    "Phase-8D verify observer failed; source result remains authoritative"
                )
            return result

        observed_verify_now._jack_phase8_ledger_observer = True
        observed_verify_now._jack_phase8_original = original_verify
        authority.verify_now = observed_verify_now

    if not getattr(current_suspend, "_jack_phase8_ledger_observer", False):
        original_suspend = current_suspend

        @wraps(original_suspend)
        def observed_suspend(*args: Any, **kwargs: Any):
            transition = original_suspend(*args, **kwargs)
            try:
                prior_state = _state_value(getattr(transition, "prior_state", ""))
                new_state = _state_value(getattr(transition, "state", ""))
                changed = bool(getattr(transition, "changed", False))
                if changed and new_state == "SUSPENDED_UNVERIFIED":
                    recorder.observe(
                        transition_sequence=int(
                            getattr(transition, "transition_sequence", 0) or 0
                        ),
                        event_type=Phase8LedgerEventType.SOURCE_AUTHORITY_SUSPENDED,
                        prior_state=prior_state,
                        new_state=new_state,
                        reason="verification_operation_failed",
                    )
            except Exception:
                try:
                    recorder.disable()
                except Exception:
                    pass
                LOG.exception(
                    "Phase-8D suspension observer failed; source transition remains authoritative"
                )
            return transition

        observed_suspend._jack_phase8_ledger_observer = True
        observed_suspend._jack_phase8_original = original_suspend
        authority._suspend_unverified = observed_suspend

    jk_module.Phase8LedgerEventType = Phase8LedgerEventType
    jk_module._JACK_PHASE8_LEDGER_TRANSITION_RECORDER = recorder
    jk_module._JACK_PHASE8_LEDGER_OBSERVER_INSTALLED = True
    return True


def main() -> None:
    # All bundled predecessor authority/security extensions converge through
    # this shared Kernel installer before Phase 8 establishes source authority.
    jk._install_bundled_runtime_extensions()

    # The interactive launcher process is not itself the serving Kernel. Seal
    # Phase-8B source authority only in the --serve process, after predecessor
    # extensions are installed and before Jack enters the serving lifecycle.
    if "--serve" in sys.argv[1:]:
        import jack_source_drift_guard

        authority = jack_source_drift_guard.install(
            jk,
            launch_entrypoint_path=Path(__file__).resolve(),
        )
        # Phase 8D observes lifecycle facts only after Phase 8B has established
        # the immutable baseline. Observer failure never blocks Phase 8C.
        _install_phase8_ledger_observer(jk, authority)
        # Phase 8C is a distinct activation step. This preserves the accepted
        # Phase-8B install contract while wiring live enforcement only in the
        # actual serving child.
        jack_source_drift_guard.activate_runtime_enforcement(jk, authority)

    # The interactive launcher spawns a fresh serving child. Keep the bundled
    # runtime-extension path active in that child rather than falling back to a
    # different authority surface.
    jk._server_command = lambda: [
        sys.executable,
        str(Path(__file__).resolve()),
        "--serve",
    ]
    jk.main()


if __name__ == "__main__":
    main()
