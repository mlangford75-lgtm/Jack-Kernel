from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_kernel_owned_installer_activates_phase7b_model_input_isolation(tmp_path):
    """Prove live installation without contaminating the parent pytest process."""

    code = r'''
import asyncio
import os

import jack_credential_guard as credential_guard
import jack_kernel as kernel


class FakeClient:
    def __init__(self):
        self.posts = []
        self.builds = []

    async def post(self, *args, **kwargs):
        self.posts.append((args, kwargs))
        return "posted"

    def build_request(self, *args, **kwargs):
        self.builds.append((args, kwargs))
        return "request"

    async def aclose(self):
        return None


fake = FakeClient()
kernel.BACKEND._client = fake

kernel._install_bundled_runtime_extensions()

assert kernel._JACK_CREDENTIAL_GUARD_INSTALLED is True
policy = kernel._JACK_RUNTIME_CREDENTIAL_POLICY
assert policy.runtime_id == kernel.RUNTIME_ID
assert policy.lane_id == kernel.LANE_ID
assert getattr(kernel.BACKEND._client.post, "_jack_phase7_credential_guard", False) is True
assert getattr(kernel.BACKEND._client.build_request, "_jack_phase7_credential_guard", False) is True

jack_secret = kernel.CFG.api_key
backend_secret = kernel.CFG.backend_api_key
assert jack_secret
assert backend_secret


async def safe_authorized_transport():
    before = len(fake.posts)
    result = await kernel.BACKEND._client.post(
        "http://127.0.0.1:1234/v1/chat/completions",
        headers={"Authorization": f"Bearer {backend_secret}"},
        json={"messages": [{"role": "user", "content": "ordinary safe work"}]},
    )
    assert result == "posted"
    assert len(fake.posts) == before + 1


asyncio.run(safe_authorized_transport())

before = len(fake.posts)


async def blocked_model_payload():
    try:
        await kernel.BACKEND._client.post(
            "http://127.0.0.1:1234/v1/chat/completions",
            headers={"Authorization": f"Bearer {backend_secret}"},
            json={"messages": [{"role": "user", "content": "leak=" + jack_secret}]},
        )
    except credential_guard.ProtectedCredentialInterrupt as exc:
        assert jack_secret not in str(exc)
        assert jack_secret not in repr(exc.match)
        return
    raise AssertionError("configured credential reached backend dispatch")


asyncio.run(blocked_model_payload())
assert len(fake.posts) == before

# Pattern-looking but unregistered content remains ordinary useful work.
async def unregistered_content_survives():
    before = len(fake.posts)
    result = await kernel.BACKEND._client.post(
        "http://127.0.0.1:1234/v1/chat/completions",
        headers={"Authorization": f"Bearer {backend_secret}"},
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "sk-not-registered eyJ.fake.jwt highEntropyLooking1234567890",
                }
            ]
        },
    )
    assert result == "posted"
    assert len(fake.posts) == before + 1


asyncio.run(unregistered_content_survives())

# Later environment mutation cannot silently replace active policy or wrappers.
first_policy = kernel._JACK_RUNTIME_CREDENTIAL_POLICY
first_post = kernel.BACKEND._client.post
first_build = kernel.BACKEND._client.build_request
os.environ["JACK_API_KEY"] = "later-environment-value"
os.environ["JACK_BACKEND_API_KEY"] = "later-backend-value"
kernel._install_bundled_runtime_extensions()
assert kernel._JACK_RUNTIME_CREDENTIAL_POLICY is first_policy
assert kernel.BACKEND._client.post is first_post
assert kernel.BACKEND._client.build_request is first_build
assert all(item.value != "later-environment-value" for item in first_policy.credentials)
assert all(item.value != "later-backend-value" for item in first_policy.credentials)

ledger = getattr(kernel, "_JACK_AUTHORITY_LEDGER", None)
if ledger is not None:
    ledger.close()
'''

    env = dict(os.environ)
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "USERPROFILE": str(tmp_path / "home"),
            "JACK_API_KEY": "live-jack-key",
            "JACK_BACKEND_API_KEY": "live-backend-key",
            "JACK_BACKEND_AUTH_MODE": "bearer",
            "JACK_BACKEND_MODEL": "test-model",
            "JACK_BACKEND_PROFILE": "custom",
            "JACK_FORENSIC_ARCHIVE_MODE": "off",
            "JACK_AUTHORITY_LEDGER_DIR": str(tmp_path / "ledger"),
        }
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
