"""Experimental Phase 10C path consequence gate; not activated at startup yet."""
from functools import wraps

from jack_policy_integrity import (
    RuntimePolicyAuthority, PolicyIntegrityCompromised, PolicyIntegrityUnavailable,
)

_LABEL = "path-consumer"


def install(jk):
    """Install before Phase 9B seals the final executable wrappers."""
    if getattr(jk, "_JACK_RUNTIME_CODE_AUTHORITY", None) is not None:
        raise PolicyIntegrityUnavailable("path gate must precede executable seal")
    if getattr(jk, "_JACK_PHASE10_PATH_AUTHORITY", None) is not None:
        raise PolicyIntegrityUnavailable("path gate already installed")
    policy = jk._runtime_path_policy()
    if policy.runtime_id != jk.RUNTIME_ID or policy.lane_id != jk.LANE_ID:
        raise PolicyIntegrityUnavailable("path policy ownership mismatch")
    guard = RuntimePolicyAuthority()
    guard.register_attribute(label=_LABEL, kind="path", holder=jk,
                             attribute="_RUNTIME_PATH_POLICY")
    guard.seal()
    partition = jk._phase4_partition_structured_tool_calls
    admission = jk._phase4_executor_admission_decision

    def verify():
        guard.verify_for(_LABEL)
        if jk.RUNTIME_ID != policy.runtime_id or jk.LANE_ID != policy.lane_id:
            raise PolicyIntegrityUnavailable("path policy ownership mismatch")

    @wraps(partition)
    def guarded_partition(calls):
        # No consequential proposal: preserve the predecessor's empty result.
        if not isinstance(calls, list) or not calls:
            return partition(calls)
        # Loss of policy authority is terminal, not a repairable model
        # proposal error. Preserve the typed exception for runtime recovery
        # and diagnostic guards instead of entering same-stage correction.
        verify()
        result = partition(calls)
        verify()
        return result

    @wraps(admission)
    def guarded_admission(payload, *, expected_call=None):
        try:
            verify()
            result = admission(payload, expected_call=expected_call)
            verify()
            return result
        except PolicyIntegrityCompromised:
            raise jk.HTTPException(status_code=503,
                detail="AUTHORITY_POLICY_INTEGRITY_COMPROMISED") from None
        except PolicyIntegrityUnavailable:
            raise jk.HTTPException(status_code=503,
                detail="Authority policy measurement unavailable") from None

    jk._phase4_partition_structured_tool_calls = guarded_partition
    jk._phase4_executor_admission_decision = guarded_admission
    jk._JACK_PHASE10_PATH_AUTHORITY = guard
    return guard
