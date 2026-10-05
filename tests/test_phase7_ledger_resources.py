from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_phase7_live_ledger_and_exact_credential_resource_containment(tmp_path):
    """Exercise the final Phase-7 authority surfaces in a fresh runtime process."""

    code = r'''
import asyncio
import json
import ntpath

import httpx
import jack_authority_ledger as authority_ledger
import jack_path_policy as path_policy
import jack_kernel as kernel


class FakeClient:
    def __init__(self):
        self.posts = []

    async def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "safe answer"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {},
            },
        )

    def build_request(self, method, url, **kwargs):
        return httpx.Request(method, url, **kwargs)

    async def send(self, request, *, stream=False):
        return httpx.Response(
            200,
            request=request,
            content=(
                b'data: {"choices":[{"index":0,"delta":{"content":"safe"},'
                b'"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
            ),
        )

    async def get(self, url, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={"data": [{"id": "test-model"}]},
        )

    async def aclose(self):
        return None


fake = FakeClient()
kernel.BACKEND._client = fake
kernel.BACKEND._resolved_model = "test-model"
kernel.BACKEND._model_metadata_checked = True
kernel._install_bundled_runtime_extensions()

assert kernel._JACK_PHASE7_LEDGER_INSTALLED is True
assert kernel._JACK_CREDENTIAL_RESOURCE_GUARD_INSTALLED is True
assert "jack_phase7_ledger.py" in kernel.RUNTIME_MANIFEST_COMPONENTS
assert "jack_credential_resource_guard.py" in kernel.RUNTIME_MANIFEST_COMPONENTS

ledger = kernel._JACK_AUTHORITY_LEDGER
credential_policy = kernel._JACK_RUNTIME_CREDENTIAL_POLICY
resource_policy = kernel._JACK_CREDENTIAL_RESOURCE_POLICY
runtime_path_policy = kernel._runtime_path_policy()

# Exact credential-resource protection is narrow. It is not a NEVER-root rule,
# and it must not swallow the parent directory or an adjacent harmless file.
jack_resource = next(
    item for item in resource_policy.resources
    if item.resource_id == "resource:jack-config"
)
protected = jack_resource.canonical_path
parent = ntpath.dirname(protected)
adjacent = ntpath.join(parent, "harmless-neighbor.json")

with authority_ledger.live_ledger_scope(ledger):
    protected_decision = path_policy.authorize_represented_path(
        runtime_path_policy,
        protected,
    )
    parent_decision = path_policy.authorize_represented_path(
        runtime_path_policy,
        parent,
    )
    adjacent_decision = path_policy.authorize_represented_path(
        runtime_path_policy,
        adjacent,
    )

assert protected_decision.outcome.value == "DENY_AND_CONTINUE"
assert "exact protected credential resource" in protected_decision.reason
assert parent_decision.outcome.value == "ALLOW"
assert adjacent_decision.outcome.value == "ALLOW"

# Model-input isolation owns disposition at the client transport seam. The
# backend intentionally translates that internal interrupt into a generic
# HTTPException, while the Phase-7 ledger records the original transport fact.
secret = kernel.CFG.api_key
before_posts = len(fake.posts)

async def blocked_model_input():
    try:
        await kernel.KERNEL.run(
            {
                "messages": [
                    {"role": "user", "content": "credential=" + secret}
                ],
                "stream": False,
            }
        )
    except kernel.HTTPException as exc:
        assert secret not in str(exc.detail)
        return
    raise AssertionError("expected backend translation of Phase-7 input interrupt")

asyncio.run(blocked_model_input())
assert len(fake.posts) == before_posts

assert ledger.wait_for_projection(timeout=5.0)
records = []
for path in sorted(ledger.records_dir.glob("*.json")):
    records.append(json.loads(path.read_text(encoding="utf-8")))

# The predecessor Phase-6 represented-path record keeps its original meaning:
# the exact config path is otherwise allowed by Phase-4 facts. Phase 7 adds a
# separate deny record rather than rewriting predecessor authority history.
resource_index = next(
    index for index, record in enumerate(records)
    if record["event_type"] == "PROTECTED_CREDENTIAL_RESOURCE_BLOCKED"
)
assert resource_index > 0
predecessor_path = records[resource_index - 1]
assert predecessor_path["event_type"] == "REPRESENTED_PATH_DECISION"
assert predecessor_path["outcome"] == "ALLOW"
resource_record = records[resource_index]
assert resource_record["outcome"] == "DENY_AND_CONTINUE"
assert resource_record["payload"] == {"resource_id": "resource:jack-config"}

credential_records = [
    record for record in records
    if record["event_type"] == "PROTECTED_CREDENTIAL_MATCH"
    and record["boundary"] == "model_input_dispatch"
]
assert credential_records
assert credential_records[-1]["outcome"] == "HARD_INTERRUPT"
assert credential_records[-1]["payload"]["boundary"] == "model_input_dispatch"
assert credential_records[-1]["payload"]["direction"] == "model_bound"

# Neither credential bytes nor protected absolute resource paths belong in the
# Phase-7 ledger payload/projection.
serialized = "\n".join(json.dumps(record, sort_keys=True) for record in records)
for item in credential_policy.credentials:
    assert item.value not in serialized
assert protected not in serialized

ledger.close()
'''

    env = dict(os.environ)
    home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "APPDATA": str(appdata),
            "JACK_RUNTIME_ID": "phase7-final-runtime",
            "JACK_LANE_ID": "phase7-final-lane",
            "JACK_API_KEY": "phase7-final-jack-secret-12345",
            "JACK_BACKEND_API_KEY": "phase7-final-backend-secret-67890",
            "JACK_BACKEND_AUTH_MODE": "bearer",
            "JACK_BACKEND_MODEL": "test-model",
            "JACK_BACKEND_PROFILE": "custom",
            "JACK_REASONING_LEVEL": "off",
            "JACK_FORENSIC_ARCHIVE_MODE": "off",
            "JACK_CANARY_POLICY_JSON": "",
            "JACK_PATH_POLICY_JSON": "",
            "JACK_AUTHORITY_LEDGER_DIR": str(tmp_path / "ledger"),
        }
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
