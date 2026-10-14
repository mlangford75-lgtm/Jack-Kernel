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


def test_stream_error_hides_internal_exception_and_rearms_pending_state():
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
    assert kernel.rearmed_tool == 1
    assert kernel.rearmed_debug == 1


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
