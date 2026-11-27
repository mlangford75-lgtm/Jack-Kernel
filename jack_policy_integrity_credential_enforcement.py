"""Experimental Policy Integrity credential policy integrity at transport and Pi release."""
from functools import wraps

from jack_credential_guard import RuntimeCredentialPolicy
from jack_policy_integrity_canary_enforcement import policy_cells
from jack_policy_integrity import RuntimePolicyAuthority, PolicyIntegrityUnavailable


def install(jk):
    if getattr(jk, "_JACK_RUNTIME_CODE_AUTHORITY", None) is not None:
        raise PolicyIntegrityUnavailable("credential gate must precede executable seal")
    if getattr(jk, "_JACK_CREDENTIAL_POLICY_AUTHORITY", None) is not None:
        raise PolicyIntegrityUnavailable("credential gate already installed")
    policy = jk._JACK_RUNTIME_CREDENTIAL_POLICY
    if (type(policy) is not RuntimeCredentialPolicy or
            policy.runtime_id != jk.RUNTIME_ID or policy.lane_id != jk.LANE_ID):
        raise PolicyIntegrityUnavailable("credential policy ownership mismatch")
    client = jk.BACKEND._client
    hub = jk.OrchestrationEventHub
    post, build = client.post, client.build_request
    proxy, publish = jk._proxy_pi_control_request, hub._publish
    guard = RuntimePolicyAuthority()
    guard.register_attribute(label="credential-holder", kind="credential",
                             holder=jk, attribute="_JACK_RUNTIME_CREDENTIAL_POLICY")
    labels = ["credential-holder"]
    consumers = [("post", post), ("build", build), ("proxy", proxy), ("publish", publish)]
    evidence_release = getattr(jk, "_project_tool_evidence_release", None)
    if callable(evidence_release):
        consumers.append(("evidence", evidence_release))
    for name, target in consumers:
        cells = policy_cells(target, RuntimeCredentialPolicy)
        if not cells or any(c.cell_contents is not policy for c in cells):
            raise PolicyIntegrityUnavailable("required credential consumer unavailable")
        for index, cell in enumerate(cells):
            label = f"credential-{name}-{index}"
            guard.register_cell(label=label, kind="credential", cell=cell)
            labels.append(label)
    labels = tuple(labels)
    guard.seal()

    def verify():
        guard.verify_for(*labels)
        if (jk.BACKEND._client is not client or jk.RUNTIME_ID != policy.runtime_id
                or jk.LANE_ID != policy.lane_id):
            raise PolicyIntegrityUnavailable("credential authority ownership mismatch")

    @wraps(post)
    async def guarded_post(*args, **kwargs):
        verify()
        return await post(*args, **kwargs)

    @wraps(build)
    def guarded_build(*args, **kwargs):
        verify()
        request = build(*args, **kwargs)
        verify()
        return request

    @wraps(proxy)
    async def guarded_proxy(*args, **kwargs):
        # A new credential-dependent request must not cross the Pi boundary
        # under compromised authority. Already-admitted effects are not revoked.
        verify()
        response = await proxy(*args, **kwargs)
        verify()
        return response

    @wraps(publish)
    async def guarded_publish(*args, **kwargs):
        verify()
        return await publish(*args, **kwargs)

    if callable(evidence_release):
        @wraps(evidence_release)
        def guarded_evidence(*args, **kwargs):
            verify()
            result = evidence_release(*args, **kwargs)
            verify()
            return result
        jk._project_tool_evidence_release = guarded_evidence

    client.post = guarded_post
    client.build_request = guarded_build
    jk._proxy_pi_control_request = guarded_proxy
    hub._publish = guarded_publish
    jk._JACK_CREDENTIAL_POLICY_AUTHORITY = guard
    return guard
