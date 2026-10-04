from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import jack_credential_guard as guard
import jack_evidence_guard as evidence


class _FakeClient:
    def __init__(self) -> None:
        self.posts = []
        self.builds = []

    async def post(self, *args, **kwargs):
        self.posts.append((args, kwargs))
        return "posted"

    def build_request(self, *args, **kwargs):
        self.builds.append((args, kwargs))
        return "request"


class _FakeBackend:
    def __init__(self) -> None:
        self._client = _FakeClient()


def _cfg(**overrides):
    values = {
        "api_key": "jack-api-secret-123",
        "backend_api_key": "backend-bearer-secret-456",
        "backend_header_value": "named-header-secret-789",
        "backend_username": "jack-user",
        "backend_password": "basic-password-secret-321",
        "backend_authorization_value": "Custom auth-secret-654",
        "backend_extra_headers": {"X-Innocent": "extra-header-not-auto-secret"},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _jack(**cfg_overrides):
    bridge = {"configured": True, "token": "pi-control-secret-987"}
    return SimpleNamespace(
        RUNTIME_ID="runtime-phase7",
        LANE_ID="lane-phase7",
        CFG=_cfg(**cfg_overrides),
        BACKEND=_FakeBackend(),
        _load_pi_control_bridge=lambda: dict(bridge),
    )


def test_policy_registers_only_closed_known_sources_and_derived_basic_wire():
    policy = guard.build_runtime_credential_policy(_jack())
    classes = {item.credential_class for item in policy.credentials}
    assert classes == {
        guard.CredentialClass.JACK_API,
        guard.CredentialClass.BACKEND_BEARER,
        guard.CredentialClass.BACKEND_NAMED_HEADER,
        guard.CredentialClass.BACKEND_BASIC_PASSWORD,
        guard.CredentialClass.BACKEND_BASIC_WIRE,
        guard.CredentialClass.BACKEND_AUTHORIZATION,
        guard.CredentialClass.PI_CONTROL,
    }
    values = {item.value for item in policy.credentials}
    assert "extra-header-not-auto-secret" not in values
    assert any(item.value.startswith("Basic ") for item in policy.credentials)


def test_secret_values_do_not_appear_in_repr():
    policy = guard.build_runtime_credential_policy(_jack())
    rendered = repr(policy) + "\n" + "\n".join(repr(item) for item in policy.credentials)
    for item in policy.credentials:
        assert item.value not in rendered


def test_duplicate_exact_value_is_deduplicated_without_losing_alias_identity():
    shared = "shared-jack-pi-secret-12345"
    jack = _jack(api_key=shared)
    jack._load_pi_control_bridge = lambda: {"configured": True, "token": shared}
    policy = guard.build_runtime_credential_policy(jack)
    matching = [item for item in policy.credentials if item.value == shared]
    assert len(matching) == 1
    item = matching[0]
    assert item.credential_class is guard.CredentialClass.JACK_API
    assert guard.CredentialClass.PI_CONTROL in item.alias_classes
    assert "credential:pi-control" in item.aliases
    assert guard.DEST_JACK_PUBLIC_AUTH in item.authorized_destinations
    assert guard.DEST_PI_CONTROL_AUTH_HEADER in item.authorized_destinations


def test_exact_secret_in_model_bound_payload_hard_interrupts_without_echoing_secret():
    policy = guard.build_runtime_credential_policy(_jack())
    secret = next(
        item.value
        for item in policy.credentials
        if item.credential_class is guard.CredentialClass.BACKEND_BEARER
    )
    payload = {"messages": [{"role": "user", "content": f"please inspect {secret}"}]}
    with pytest.raises(guard.ProtectedCredentialInterrupt) as caught:
        policy.guard_model_payload(payload)
    assert caught.value.match.boundary == guard.BOUNDARY_MODEL_INPUT_DISPATCH
    assert caught.value.match.direction == guard.DIRECTION_MODEL_BOUND
    assert secret not in str(caught.value)
    assert secret not in repr(caught.value.match)


def test_unregistered_secret_looking_text_is_not_blocked():
    policy = guard.build_runtime_credential_policy(_jack())
    policy.guard_model_payload(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "sk-example-not-registered eyJ.fake.jwt highEntropyLooking1234567890",
                }
            ]
        }
    )


def test_authorized_transport_headers_are_not_misclassified_as_model_payload():
    jack = _jack()
    policy = guard.install(jack)
    secret = jack.CFG.backend_api_key

    async def exercise():
        result = await jack.BACKEND._client.post(
            "http://127.0.0.1:1234/v1/chat/completions",
            headers={"Authorization": f"Bearer {secret}"},
            json={"messages": [{"role": "user", "content": "safe"}]},
        )
        assert result == "posted"

    asyncio.run(exercise())
    assert len(jack.BACKEND._client.posts) == 1


def test_post_and_stream_request_seams_block_model_payload_before_transport():
    jack = _jack()
    policy = guard.install(jack)
    secret = jack.CFG.api_key

    async def post_attempt():
        with pytest.raises(guard.ProtectedCredentialInterrupt):
            await jack.BACKEND._client.post(
                "http://127.0.0.1:1234/v1/chat/completions",
                headers={},
                json={"messages": [{"role": "tool", "content": secret}]},
            )

    asyncio.run(post_attempt())
    assert not jack.BACKEND._client.posts

    with pytest.raises(guard.ProtectedCredentialInterrupt):
        jack.BACKEND._client.build_request(
            "POST",
            "http://127.0.0.1:1234/v1/chat/completions",
            headers={},
            json={"messages": [{"role": "user", "content": secret}]},
        )
    assert not jack.BACKEND._client.builds
    assert policy is jack._JACK_RUNTIME_CREDENTIAL_POLICY


def test_install_is_exact_once_and_environment_or_cfg_mutation_does_not_replace_policy():
    jack = _jack()
    first = guard.install(jack)
    post_wrapper = jack.BACKEND._client.post
    build_wrapper = jack.BACKEND._client.build_request
    jack.CFG.api_key = "replacement-secret-that-must-not-rebind"
    second = guard.install(jack)
    assert second is first
    assert jack.BACKEND._client.post is post_wrapper
    assert jack.BACKEND._client.build_request is build_wrapper
    assert all(item.value != jack.CFG.api_key for item in first.credentials)


def test_active_known_credential_outside_exact_match_bounds_fails_policy_installation():
    with pytest.raises(RuntimeError, match="too short"):
        guard.build_runtime_credential_policy(_jack(api_key="short"))

    too_long = "x" * (guard.CREDENTIAL_MAX_VALUE_LENGTH + 1)
    with pytest.raises(RuntimeError, match="bounded exact-match ceiling"):
        guard.build_runtime_credential_policy(_jack(api_key=too_long))


def test_credential_policy_merges_into_existing_canaries_without_replacing_them():
    jack = _jack()
    credentials = guard.build_runtime_credential_policy(jack)
    existing = evidence.RuntimeCanaryPolicy(
        runtime_id=jack.RUNTIME_ID,
        lane_id=jack.LANE_ID,
        canaries=evidence.DeterministicCanarySet(
            (
                evidence.CanaryPattern(
                    canary_id="existing:tier-b",
                    tier=evidence.CanaryTier.B,
                    value="existing-canary-secret",
                ),
            ),
            max_window=256,
        ),
    )
    merged = guard.merge_runtime_canary_policy(existing, credentials)
    assert merged.canaries.find("existing-canary-secret").canary_id == "existing:tier-b"
    match = merged.canaries.find(jack.CFG.backend_api_key)
    assert match is not None
    assert match.canary_id == "credential:backend-bearer"
    assert match.tier is evidence.CanaryTier.A


def test_canary_collision_fails_instead_of_silently_dropping_policy():
    jack = _jack()
    credentials = guard.build_runtime_credential_policy(jack)
    existing = evidence.RuntimeCanaryPolicy(
        runtime_id=jack.RUNTIME_ID,
        lane_id=jack.LANE_ID,
        canaries=evidence.DeterministicCanarySet(
            (
                evidence.CanaryPattern(
                    canary_id="other:id",
                    tier=evidence.CanaryTier.B,
                    value=jack.CFG.api_key,
                ),
            ),
            max_window=256,
        ),
    )
    with pytest.raises(RuntimeError, match="collision"):
        guard.merge_runtime_canary_policy(existing, credentials)
