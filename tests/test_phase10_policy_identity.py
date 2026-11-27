"""Phase 10-B static-policy identity controls, measurement only.

No production policy hook is installed in this experiment.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from jack_policy_integrity import (
    RuntimePolicyAuthority, PolicyIntegrityCompromised, PolicyIntegrityUnavailable,
)
from jack_path_policy import RuntimePathPolicy
from jack_credential_guard import (
    RuntimeCredentialPolicy, ProtectedCredential, CredentialClass,
)
from jack_evidence_guard import (
    CanaryPattern, CanaryTier, DeterministicCanarySet, RuntimeCanaryPolicy,
)


def path_policy():
    return RuntimePathPolicy(
        runtime_id="rt-10", lane_id="lane-10", workspace_root=None,
        never_roots=(), _path_environment=(("HOME", "C:/Users/example"),),
    )


def canary_policy():
    return RuntimeCanaryPolicy(
        runtime_id="rt-10", lane_id="lane-10",
        canaries=DeterministicCanarySet(
            (CanaryPattern("protected-canary", CanaryTier.B, "very-secret-value"),),
            max_window=64,
        ),
    )


def credential_policy():
    return RuntimeCredentialPolicy(
        runtime_id="rt-10", lane_id="lane-10",
        credentials=(ProtectedCredential(
            credential_id="credential:api",
            credential_class=CredentialClass.JACK_API,
            source_kind="test",
            authorized_destinations=frozenset({"model", "pi"}),
            value="private-credential-value",
        ),),
        protected_resources=(),
    )


def attach(label, kind, policy):
    owner = SimpleNamespace(policy=policy)
    guard = RuntimePolicyAuthority()
    guard.register_attribute(label=label, kind=kind,
                             holder=owner, attribute="policy")
    guard.seal()
    return guard, owner


@pytest.mark.parametrize("kind,factory", [
    ("path", path_policy),
    ("canary", canary_policy),
    ("credential", credential_policy),
])
def test_sealed_known_policies_are_stable(kind, factory):
    guard, _ = attach(kind, kind, factory())
    guard.verify_for(kind)
    assert guard.state == "ACTIVE"
    assert guard.invalidated_labels == ()


@pytest.mark.parametrize("kind,factory", [
    ("path", path_policy),
    ("canary", canary_policy),
    ("credential", credential_policy),
])
def test_replacement_with_identical_new_immutable_object_is_detected(kind, factory):
    guard, owner = attach(kind, kind, factory())
    original = owner.policy
    owner.policy = factory()
    assert owner.policy is not original
    with pytest.raises(PolicyIntegrityCompromised):
        guard.verify_for(kind)
    owner.policy = original
    with pytest.raises(PolicyIntegrityCompromised):
        guard.verify_for(kind)


def test_mutation_of_frozen_path_policy_is_detected():
    policy = path_policy()
    guard, _owner = attach("path", "path", policy)
    object.__setattr__(policy, "never_roots", ("C:/sensitive",))
    with pytest.raises(PolicyIntegrityCompromised):
        guard.verify_for("path")


def test_mutation_of_nested_canary_value_is_detected_without_secret_release():
    policy = canary_policy()
    guard, _owner = attach("canary", "canary", policy)
    canary = policy.canaries._patterns[0]
    object.__setattr__(canary, "value", "different-secret-value")
    with pytest.raises(PolicyIntegrityCompromised) as exc:
        guard.verify_for("canary")
    assert "different-secret-value" not in str(exc.value)
    assert "very-secret-value" not in str(exc.value)


def test_mutation_of_credential_destination_is_detected():
    policy = credential_policy()
    guard, _owner = attach("credential", "credential", policy)
    credential = policy.credentials[0]
    object.__setattr__(
        credential, "authorized_destinations", frozenset({"arbitrary-destination"}),
    )
    with pytest.raises(PolicyIntegrityCompromised):
        guard.verify_for("credential")


def test_secret_changed_without_holder_replacement_is_detected_and_not_leaked():
    policy = credential_policy()
    guard, _owner = attach("credential", "credential", policy)
    object.__setattr__(policy.credentials[0], "value", "altered-private-value")
    with pytest.raises(PolicyIntegrityCompromised) as exc:
        guard.verify_for("credential")
    assert "altered-private-value" not in str(exc.value)


def test_closure_cell_replacement_is_detected_as_policy_identity_change():
    policy = canary_policy()

    def consumer():
        return policy

    cell, = consumer.__closure__
    guard = RuntimePolicyAuthority()
    guard.register_cell(label="real-output-closure", kind="canary", cell=cell)
    guard.seal()
    guard.verify_for("real-output-closure")
    cell.cell_contents = canary_policy()
    with pytest.raises(PolicyIntegrityCompromised):
        guard.verify_for("real-output-closure")


def test_independent_healthy_policy_remains_valid_after_other_compromise():
    owner_a = SimpleNamespace(policy=path_policy())
    owner_b = SimpleNamespace(policy=credential_policy())
    guard = RuntimePolicyAuthority()
    guard.register_attribute(label="path", kind="path",
                             holder=owner_a, attribute="policy")
    guard.register_attribute(label="credential", kind="credential",
                             holder=owner_b, attribute="policy")
    guard.seal()
    owner_a.policy = path_policy()
    with pytest.raises(PolicyIntegrityCompromised):
        guard.verify_for("path")
    guard.verify_for("credential")
    assert guard.invalidated_labels == ("path",)


def test_missing_binding_is_confirmed_not_measurement_uncertainty():
    guard, owner = attach("path", "path", path_policy())
    del owner.policy
    with pytest.raises(PolicyIntegrityCompromised):
        guard.verify_for("path")


def test_measurement_unavailable_can_recover_when_policy_identity_is_exact():
    class Flaky:
        def __init__(self, policy):
            self.policy = policy
            self.blocked = False

        def __getattribute__(self, name):
            if name == "policy" and object.__getattribute__(self, "blocked"):
                raise OSError("synthetic temporary holder failure")
            return object.__getattribute__(self, name)

    holder = Flaky(path_policy())
    guard = RuntimePolicyAuthority()
    guard.register_attribute(label="path", kind="path",
                             holder=holder, attribute="policy")
    guard.seal()
    holder.blocked = True
    with pytest.raises(PolicyIntegrityUnavailable):
        guard.verify_for("path")
    assert guard.state == "SUSPENDED_UNVERIFIED"
    holder.blocked = False
    guard.verify_for("path")
    assert guard.state == "ACTIVE"


def test_later_environment_changes_do_not_mutate_sealed_policy(monkeypatch):
    guard, owner = attach("path", "path", path_policy())
    monkeypatch.setenv("JACK_PATH_POLICY_JSON", '{"never_roots":["unsafe"]}')
    guard.verify_for("path")
    assert owner.policy.never_roots == ()


def test_unsupported_policy_schema_is_never_assumed_safe():
    owner = SimpleNamespace(policy=object())
    guard = RuntimePolicyAuthority()
    with pytest.raises(PolicyIntegrityUnavailable):
        guard.register_attribute(label="path", kind="path",
                                 holder=owner, attribute="policy")


def test_manifest_cannot_be_resealed_and_labels_are_explicit():
    guard, owner = attach("path", "path", path_policy())
    with pytest.raises(RuntimeError):
        guard.register_attribute(label="second", kind="path",
                                 holder=owner, attribute="policy")
    with pytest.raises(PolicyIntegrityUnavailable):
        guard.verify_for("unregistered")
