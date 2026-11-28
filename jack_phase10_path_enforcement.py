"""Experimental Phase 10C path consequence gate; not activated at startup yet."""
from functools import wraps

from jack_policy_integrity import (
    RuntimePolicyAuthority, PolicyIntegrityCompromised, PolicyIntegrityUnavailable,
)

_LABEL = "path-consumer"


def _resource_policy_snapshot(jk, key, expected):
    """Measure the registry binding actually used by the represented-path gate."""
    import jack_credential_resource_guard as resource
    if type(expected) is not resource.RuntimeCredentialResourcePolicy:
        raise PolicyIntegrityUnavailable("credential resource policy unavailable")
    with resource._REGISTRY_LOCK:
        if (getattr(jk, "_JACK_CREDENTIAL_RESOURCE_POLICY", None) is not expected
                or resource._RESOURCE_POLICIES.get(key) is not expected):
            raise PolicyIntegrityCompromised("credential resource authority changed")
        if (expected.runtime_id, expected.lane_id) != key:
            raise PolicyIntegrityCompromised("credential resource ownership changed")
        entries = expected.resources
        if type(entries) is not tuple or any(
            type(item) is not resource.ProtectedCredentialResource
            or type(item.resource_id) is not str
            or type(item.canonical_path) is not str
            for item in entries
        ):
            raise PolicyIntegrityCompromised("credential resource policy schema changed")
        return tuple((item.resource_id, item.canonical_path) for item in entries)


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
    resource_policy = getattr(jk, "_JACK_CREDENTIAL_RESOURCE_POLICY", None)
    resource_key = (policy.runtime_id, policy.lane_id)
    resource_snapshot = None
    resource_invalid = False
    if resource_policy is not None or getattr(jk, "_JACK_RUNTIME_CREDENTIAL_POLICY", None) is not None:
        resource_snapshot = _resource_policy_snapshot(jk, resource_key, resource_policy)
    partition = jk._phase4_partition_structured_tool_calls
    admission = jk._phase4_executor_admission_decision
    debugging_surface = jk._debugging_report_only_tool_surface

    def verify():
        nonlocal resource_invalid
        guard.verify_for(_LABEL)
        if jk.RUNTIME_ID != policy.runtime_id or jk.LANE_ID != policy.lane_id:
            raise PolicyIntegrityUnavailable("path policy ownership mismatch")
        if resource_invalid:
            raise PolicyIntegrityCompromised("credential resource authority invalidated")
        if resource_snapshot is not None:
            try:
                if _resource_policy_snapshot(jk, resource_key, resource_policy) != resource_snapshot:
                    raise PolicyIntegrityCompromised("credential resource policy changed")
            except PolicyIntegrityCompromised:
                resource_invalid = True
                raise
            except PolicyIntegrityUnavailable:
                raise
            except Exception:
                raise PolicyIntegrityUnavailable("credential resource measurement unavailable") from None

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

    @wraps(debugging_surface)
    def guarded_debugging_surface(*args, **kwargs):
        verify()
        result = debugging_surface(*args, **kwargs)
        verify()
        return result

    jk._debugging_report_only_tool_surface = guarded_debugging_surface
    jk._phase4_partition_structured_tool_calls = guarded_partition
    jk._phase4_executor_admission_decision = guarded_admission
    jk._JACK_PHASE10_PATH_AUTHORITY = guard
    return guard
