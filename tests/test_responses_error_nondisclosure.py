"""Fail-closed /v1/responses error-detail regression tests."""
from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException

SOURCE = Path(__file__).resolve().parents[1] / "jack_responses_compat.py"
spec = importlib.util.spec_from_file_location("jack_responses_error_hardening_test", SOURCE)
assert spec is not None and spec.loader is not None
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)

CANARY = "confidential-internal-exception-canary-734a"


def test_stream_error_hides_internal_exception_without_message_based_rearming():
    class Kernel:
        def __init__(self):
            self.rearmed_tool = 0
            self.rearmed_debug = 0

        async def stream(self, _body):
            if False:  # Async generator, not coroutine.
                yield b""
            raise RuntimeError("backend private detail: " + CANARY)

        async def _rearm_pending_tool_resume_for_messages(self, _messages):
            self.rearmed_tool += 1

        async def _rearm_pending_debugging_resumes_for_messages(self, _messages):
            self.rearmed_debug += 1

    kernel = Kernel()
    jk = SimpleNamespace(KERNEL=kernel, CFG=SimpleNamespace(virtual_model="jack-kernel"))

    async def collect():
        return [chunk async for chunk in compat._stream(jk, {"messages": []}, {})]

    chunks = asyncio.run(collect())
    raw = b"".join(chunks).decode("utf-8")
    assert CANARY not in raw
    payloads = [
        json.loads(line[6:])
        for chunk in chunks
        for line in chunk.decode("utf-8").splitlines()
        if line.startswith("data: ")
    ]
    assert payloads[-1]["type"] == "response.failed"
    assert payloads[-1]["error"] == {
        "code": "jack_responses_stream_error",
        "message": "Jack Responses stream failed",
    }
    assert payloads[-1]["response"]["error"] == payloads[-1]["error"]
    assert kernel.rearmed_tool == 0
    assert kernel.rearmed_debug == 0


async def _no_auth(_request):
    return None


class Request:
    async def json(self):
        return {"input": "hello"}


def make_endpoint(exception):
    class Kernel:
        async def run(self, _chat):
            raise exception

    jk = SimpleNamespace(
        APP=FastAPI(),
        KERNEL=Kernel(),
        enforce_kernel_auth=_no_auth,
        sanitize_agent_request=lambda chat: chat,
        _phase4_executor_context_from_request=lambda _request: None,
        build_stage_system_prompt=lambda caller_system, profile, messages=None: "stage",
        LOG=SimpleNamespace(exception=lambda *_args, **_kwargs: None),
    )
    compat.register(jk)
    return next(route.endpoint for route in jk.APP.routes if route.path == "/v1/responses")


def test_nonstream_internal_exception_not_reflected_as_http_500_detail():
    endpoint = make_endpoint(RuntimeError("backend private detail: " + CANARY))
    with pytest.raises(HTTPException) as caught:
        asyncio.run(endpoint(Request()))
    assert caught.value.status_code == 500
    assert caught.value.detail == "Jack Responses compatibility failure"
    assert CANARY not in caught.value.detail


def test_nonstream_explicit_http_policy_exception_retained():
    endpoint = make_endpoint(HTTPException(status_code=409, detail="withheld sibling result"))
    with pytest.raises(HTTPException) as caught:
        asyncio.run(endpoint(Request()))
    assert caught.value.status_code == 409
    assert caught.value.detail == "withheld sibling result"


def test_stream_phase7_canonical_diagnostic_is_preserved_without_raw_secret():
    class Kernel:
        async def stream(self, _body):
            if False:
                yield b""
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "protected_credential_diagnostic_withheld",
                    "security_outcome": "HARD_INTERRUPT",
                    "release_boundary": "diagnostic_stream_exception_release",
                },
            )

        async def _rearm_pending_tool_resume_for_messages(self, _messages):
            return None

        async def _rearm_pending_debugging_resumes_for_messages(self, _messages):
            return None

    jk = SimpleNamespace(KERNEL=Kernel(), CFG=SimpleNamespace(virtual_model="jack-kernel"))

    async def collect():
        return b"".join([chunk async for chunk in compat._stream(jk, {"messages": []}, {})]).decode()

    output = asyncio.run(collect())
    assert "protected_credential_diagnostic_withheld" in output
    assert "diagnostic_stream_exception_release" in output
    assert CANARY not in output


@pytest.mark.parametrize("kind,status,code,marker", [
    ("path", 403, "jack_restricted_path_hard_interrupt", "RESTRICTED PATHS: HARD INTERRUPT"),
    ("canary", 403, "jack_canary_hard_interrupt", "STREAMINGIRQ: CANARY HARD INTERRUPT"),
    ("credential", 403, "jack_credential_hard_interrupt", "PROTECTED CREDENTIAL: HARD INTERRUPT"),
    ("policy", 503, "jack_static_policy_unavailable", "STATIC POLICY INTEGRITY: AUTHORITY UNAVAILABLE"),
])
def test_typed_security_failure_preserves_public_disposition(kind, status, code, marker):
    from jack_evidence_guard import CanaryMatch, CanaryTier, StreamingIRQCanaryInterrupt
    from jack_credential_guard import CredentialMatch, CredentialClass, ProtectedCredentialInterrupt
    from jack_policy_integrity import PolicyIntegrityUnavailable

    class RestrictedPath(RuntimeError):
        security_outcome = "HARD_INTERRUPT"

    exceptions = {
        "path": lambda: RestrictedPath(CANARY),
        "canary": lambda: StreamingIRQCanaryInterrupt(CanaryMatch("test", CanaryTier.A)),
        "credential": lambda: ProtectedCredentialInterrupt(CredentialMatch(
            "test", next(iter(CredentialClass)), "model_ingress", "model_bound",
        )),
        "policy": lambda: PolicyIntegrityUnavailable(CANARY),
    }

    endpoint = make_endpoint(exceptions[kind]())
    with pytest.raises(HTTPException) as caught:
        asyncio.run(endpoint(Request()))
    assert caught.value.status_code == status
    assert caught.value.detail["error"] == code
    assert caught.value.detail["security_outcome"] == "HARD_INTERRUPT"
    assert marker in caught.value.detail["message"]
    assert CANARY not in json.dumps(caught.value.detail)

    class Kernel:
        async def stream(self, _body):
            if False:
                yield b""
            raise exceptions[kind]()

    jk = SimpleNamespace(KERNEL=Kernel(), CFG=SimpleNamespace(virtual_model="jack-kernel"))

    async def collect():
        return b"".join([chunk async for chunk in compat._stream(jk, {"messages": []}, {})]).decode()

    raw = asyncio.run(collect())
    assert CANARY not in raw
    frames = [json.loads(line[6:]) for line in raw.splitlines() if line.startswith("data: ")]
    assert frames[-1]["type"] == "response.failed"
    assert frames[-1]["error"]["code"] == code
    assert marker in frames[-1]["error"]["message"]
    assert not any(frame["type"] == "response.completed" for frame in frames)
