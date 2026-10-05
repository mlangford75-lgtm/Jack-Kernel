from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_live_release_barrier_uses_credential_tier_a_and_preserves_safe_work(tmp_path):
    code = r'''
import asyncio
import json
import os
from types import SimpleNamespace

import jack_evidence_guard as evidence
import jack_kernel as kernel


class FakeClient:
    async def post(self, *args, **kwargs):
        return "posted"

    def build_request(self, *args, **kwargs):
        return "request"

    async def aclose(self):
        return None


kernel.BACKEND._client = FakeClient()
state = {
    "run_completed": 0,
    "result": None,
    "events": [],
}


async def raw_run(request_body, *args, **kwargs):
    state["run_completed"] += 1
    return state["result"]


async def raw_stream(request_body, *args, **kwargs):
    for event in tuple(state["events"]):
        yield event


kernel.KERNEL.run = raw_run
kernel.KERNEL.stream = raw_stream
kernel._install_bundled_runtime_extensions()

assert kernel._JACK_CREDENTIAL_GUARD_INSTALLED is True
assert kernel._JACK_EVIDENCE_PROVENANCE_GUARD_INSTALLED is True
secret = kernel.CFG.api_key
assert secret


def blank_result():
    return SimpleNamespace(
        content=None,
        reasoning_content=None,
        reasoning=None,
        thinking=None,
        tool_calls=None,
    )


async def expect_nonstream_block(field, value):
    result = blank_result()
    setattr(result, field, value)
    state["result"] = result
    before = state["run_completed"]
    try:
        await kernel.KERNEL.run({"model": "jack-kernel"})
    except evidence.StreamingIRQCanaryInterrupt as exc:
        assert exc.match.tier is evidence.CanaryTier.A
        assert exc.match.canary_id == "credential:jack-api"
        assert secret not in str(exc)
    else:
        raise AssertionError(f"credential escaped non-stream {field}")
    # The underlying cognition completed before release was withheld.
    assert state["run_completed"] == before + 1


async def exercise_nonstream():
    for field in ("content", "reasoning_content", "reasoning", "thinking"):
        await expect_nonstream_block(field, "safe-context-" + secret + "-unsafe")

    await expect_nonstream_block(
        "tool_calls",
        [
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "inspect",
                    "arguments": '{"value":"' + secret + '"}',
                },
            }
        ],
    )

    safe = blank_result()
    safe.content = "sk-not-registered eyJ.fake.jwt highEntropyLooking1234567890"
    state["result"] = safe
    before = state["run_completed"]
    returned = await kernel.KERNEL.run({"model": "jack-kernel"})
    assert returned is safe
    assert returned.content == safe.content
    assert state["run_completed"] == before + 1


asyncio.run(exercise_nonstream())


def frame(field, text, *, finish_reason=None):
    return (
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-phase7c",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "jack-kernel",
                "choices": [
                    {
                        "index": 0,
                        "delta": {field: text},
                        "finish_reason": finish_reason,
                    }
                ],
            }
        )
        + "\n\n"
    ).encode("utf-8")


def tool_frame(arguments):
    return (
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-phase7c",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "jack-kernel",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {
                                        "arguments": arguments,
                                    },
                                }
                            ]
                        },
                        "finish_reason": None,
                    }
                ],
            }
        )
        + "\n\n"
    ).encode("utf-8")


async def collect_until_interrupt():
    released = []
    try:
        async for chunk in kernel.KERNEL.stream({"model": "jack-kernel"}):
            released.append(chunk)
    except evidence.StreamingIRQCanaryInterrupt as exc:
        assert exc.match.tier is evidence.CanaryTier.A
        assert exc.match.canary_id == "credential:jack-api"
        return b"".join(released)
    raise AssertionError("credential stream was not interrupted")


async def exercise_streams():
    split = max(1, len(secret) // 2)
    for field in ("content", "reasoning_content", "reasoning", "thinking"):
        state["events"] = [
            frame(field, "safe-prefix-" + secret[:split]),
            frame(field, secret[split:] + "-unsafe-tail"),
        ]
        released = await collect_until_interrupt()
        assert secret.encode() not in released
        assert b"safe-prefix-" in released

    state["events"] = [
        tool_frame('{"value":"safe-prefix-' + secret[:split]),
        tool_frame(secret[split:] + '-unsafe-tail"}'),
    ]
    released = await collect_until_interrupt()
    assert secret.encode() not in released
    assert b"safe-prefix-" in released

    # Unregistered secret-looking text remains useful ordinary model output.
    benign = "sk-not-registered eyJ.fake.jwt highEntropyLooking1234567890"
    state["events"] = [
        frame("content", benign, finish_reason="stop"),
        b"data: [DONE]\n\n",
    ]
    released = []
    async for chunk in kernel.KERNEL.stream({"model": "jack-kernel"}):
        released.append(chunk)
    joined = b"".join(released)
    assert benign.encode() in joined


asyncio.run(exercise_streams())

# Later environment mutation cannot replace the immutable active output policy.
old_secret = secret
os.environ["JACK_API_KEY"] = "later-phase7c-env-secret"
kernel._install_bundled_runtime_extensions()

async def prove_no_rebind():
    safe = blank_result()
    safe.content = "later-phase7c-env-secret"
    state["result"] = safe
    returned = await kernel.KERNEL.run({"model": "jack-kernel"})
    assert returned.content == "later-phase7c-env-secret"

    blocked = blank_result()
    blocked.content = old_secret
    state["result"] = blocked
    try:
        await kernel.KERNEL.run({"model": "jack-kernel"})
    except evidence.StreamingIRQCanaryInterrupt:
        return
    raise AssertionError("original output policy was silently replaced")


asyncio.run(prove_no_rebind())

ledger = getattr(kernel, "_JACK_AUTHORITY_LEDGER", None)
if ledger is not None:
    ledger.close()
'''

    env = dict(os.environ)
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "USERPROFILE": str(tmp_path / "home"),
            "JACK_API_KEY": "phase7c-jack-secret-12345",
            "JACK_BACKEND_API_KEY": "phase7c-backend-secret-67890",
            "JACK_BACKEND_AUTH_MODE": "bearer",
            "JACK_BACKEND_MODEL": "test-model",
            "JACK_BACKEND_PROFILE": "custom",
            "JACK_CANARY_POLICY_JSON": "",
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
