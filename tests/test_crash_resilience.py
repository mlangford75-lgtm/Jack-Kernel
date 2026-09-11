import asyncio
import importlib.util
import os
import sys
import tempfile
import threading
import uuid
from pathlib import Path

from starlette.requests import Request

SRC = Path(__file__).resolve().parents[1] / "jack_kernel.py"
TOOLS = [{
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Run diagnostic commands.",
        "parameters": {
            "type": "object",
            "required": ["command"],
            "properties": {"command": {"type": "string"}},
        },
        "strict": False,
    },
}]


def load(mode: str):
    os.environ["JACK_REASONING_LEVEL"] = mode
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "off"
    os.environ["JACK_BACKEND_MODEL"] = "test-model"
    name = f"jack_test_crash_{mode.replace('-', '_')}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def response(content="", reasoning=""):
    msg = {"role": "assistant", "content": content}
    if reasoning:
        msg["reasoning_content"] = reasoning
    return {
        "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


class FakeBackend:
    def __init__(self, queue):
        self.queue = list(queue)

    async def chat(self, **kwargs):
        if not self.queue:
            raise AssertionError("fake backend queue exhausted")
        item = self.queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class FakeStreamBackend(FakeBackend):
    async def chat_stream(self, **kwargs):
        if not self.queue:
            raise AssertionError("fake stream backend queue exhausted")
        item = self.queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        choice = (item.get("choices") or [{}])[0] or {}
        msg = choice.get("message") or {}
        delta = {}
        for key in ("reasoning_content", "reasoning", "content", "tool_calls"):
            if key in msg:
                delta[key] = msg[key]
        yield {
            "choices": [{"index": 0, "delta": delta, "finish_reason": choice.get("finish_reason")}],
            "usage": item.get("usage") or {},
        }


async def intake_resume_survives_failure():
    m = load("code-debugging")
    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)
        backend = FakeBackend([])
        kernel = m.JackQwenKernel(backend, m.CFG)
        run = m._debugging_create_run("Audit the project.")
        await kernel._register_debugging_intake_resume(
            run=run,
            history=[{"role": "user", "content": "Audit the project."}],
            secondary_system="",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            tools=TOOLS,
            tool_choice="auto",
            data=response("What runtime symptom did you observe?"),
        )
        state = next(iter(kernel._pending_debugging_intake_resumes.values()))
        messages = [
            {"role": "user", "content": "Audit the project."},
            {"role": "assistant", "content": state.user_visible_response},
            {"role": "user", "content": "It fails after startup."},
        ]

        backend.queue.append(m.HTTPException(status_code=502, detail="synthetic backend failure"))
        try:
            await kernel.run({"messages": messages, "tools": TOOLS, "tool_choice": "auto"})
        except m.HTTPException:
            pass
        else:
            raise AssertionError("resume failure should propagate")

        assert kernel._pending_debugging_intake_resumes.get(state.resume_id) is state
        assert state.in_flight is False
        assert not any(item.get("content") == "It fails after startup." for item in run.intake_history)

        backend.queue.append(response("Can you reproduce it consistently?"))
        result = await kernel.run({"messages": messages, "tools": TOOLS, "tool_choice": "auto"})
        assert "Can you reproduce" in (result.content or "")
        assert state.resume_id not in kernel._pending_debugging_intake_resumes
        assert sum(item.get("content") == "It fails after startup." for item in run.intake_history) == 1


async def clarification_resume_survives_failure():
    m = load("code-debugging")
    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)
        backend = FakeBackend([])
        kernel = m.JackQwenKernel(backend, m.CFG)
        run = m._debugging_create_run("Audit another project.")
        m._debugging_freeze_intake(run)
        await kernel._register_debugging_user_resume(
            stage_key="debug_pass_1",
            history=m._debugging_fresh_pass_history(run, 1),
            secondary_system="",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            tools=TOOLS,
            tool_choice="auto",
            data=response(""),
            question="What exact error text appears?",
            debugging_run_id=run.run_id,
        )
        state = next(iter(kernel._pending_debugging_user_resumes.values()))
        messages = [
            {"role": "user", "content": "Audit another project."},
            {"role": "assistant", "content": state.user_visible_question},
            {"role": "user", "content": "The error is E42."},
        ]

        backend.queue.append(m.HTTPException(status_code=502, detail="synthetic backend failure"))
        try:
            await kernel.run({"messages": messages, "tools": TOOLS, "tool_choice": "auto"})
        except m.HTTPException:
            pass
        else:
            raise AssertionError("clarification failure should propagate")

        assert kernel._pending_debugging_user_resumes.get(state.resume_id) is state
        assert state.in_flight is False

        backend.queue.append(response("DEBUGGING_USER_QUESTION: Does E42 occur before any file write?"))
        result = await kernel.run({"messages": messages, "tools": TOOLS, "tool_choice": "auto"})
        assert "Does E42 occur" in (result.content or "")
        assert state.resume_id not in kernel._pending_debugging_user_resumes


async def permissive_single_pending_fallback_is_preserved():
    m = load("code-debugging")
    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)
        kernel = m.JackQwenKernel(FakeBackend([]), m.CFG)
        run = m._debugging_create_run("Audit the project.")
        await kernel._register_debugging_intake_resume(
            run=run,
            history=[{"role": "user", "content": "Audit the project."}],
            secondary_system="",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            tools=TOOLS,
            tool_choice="auto",
            data=response("Any symptoms?"),
        )
        state = next(iter(kernel._pending_debugging_intake_resumes.values()))
        matched = await kernel._consume_pending_debugging_intake_resume([
            {"role": "user", "content": "Audit the project."},
            {"role": "user", "content": "No additional symptoms."},
        ])
        assert matched is not None
        assert matched[0] is state
        await kernel._rearm_pending_debugging_intake_resume(state)


async def no_tool_intake_behavior_is_unchanged():
    m = load("code-debugging")
    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)
        backend = FakeBackend([response("What symptoms have you seen?")])
        kernel = m.JackQwenKernel(backend, m.CFG)
        result = await kernel.run({"messages": [{"role": "user", "content": "Audit this."}]})
        assert "What symptoms" in (result.content or "")


async def completed_runs_leave_live_memory():
    m = load("code-debugging")
    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)
        run = m._debugging_create_run("Audit a completed project.")
        m._debugging_freeze_intake(run)
        backend = FakeBackend(
            [response(f"Pass {n} completed with no material finding.") for n in range(1, 6)]
            + [response("Final repair report: no material findings.")]
        )
        kernel = m.JackQwenKernel(backend, m.CFG)
        result = await kernel._run_code_debugging_nonstream(
            run=run,
            secondary_system="",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            tools=TOOLS,
            tool_choice="auto",
            start_pass=1,
        )
        assert "no material findings" in (result.content or "").lower()
        assert run.run_id not in m._DEBUGGING_RUNS


async def evidence_scan_runs_off_event_loop():
    m = load("off")
    main_thread = threading.get_ident()
    observed = {}

    async def no_auth(_request):
        return None

    def fake_recover(tool_call_id, expected_sha256):
        observed["thread"] = threading.get_ident()
        return {"tool_call_id": tool_call_id, "sha256": expected_sha256 or "none", "content": "ok"}

    m.enforce_kernel_auth = no_auth
    m.recover_pi_tool_evidence = fake_recover
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""})
    result = await m.jack_tool_evidence("call-1", request)
    assert result["content"] == "ok"
    assert observed["thread"] != main_thread


async def safe_stream_rearms_failed_debugging_resume():
    m = load("code-debugging")
    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)
        backend = FakeStreamBackend([])
        kernel = m.JackQwenKernel(backend, m.CFG)
        m.KERNEL = kernel
        run = m._debugging_create_run("Audit streamed resume.")
        await kernel._register_debugging_intake_resume(
            run=run,
            history=[{"role": "user", "content": "Audit streamed resume."}],
            secondary_system="",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            tools=TOOLS,
            tool_choice="auto",
            data=response("What happened?"),
        )
        state = next(iter(kernel._pending_debugging_intake_resumes.values()))
        body = {
            "stream": True,
            "messages": [
                {"role": "user", "content": "Audit streamed resume."},
                {"role": "assistant", "content": state.user_visible_response},
                {"role": "user", "content": "The connection failed."},
            ],
            "tools": TOOLS,
            "tool_choice": "auto",
        }
        backend.queue.append(m.HTTPException(status_code=502, detail="synthetic streamed intake failure"))
        chunks = []
        async for chunk in m._safe_public_stream(body):
            chunks.append(chunk)
        assert state.in_flight is False
        assert kernel._pending_debugging_intake_resumes.get(state.resume_id) is state
        assert any(b"internal stage failure" in chunk for chunk in chunks)


async def stream_rearm_helper_restores_retryability():
    m = load("code-debugging")
    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)
        kernel = m.JackQwenKernel(FakeBackend([]), m.CFG)
        run = m._debugging_create_run("Audit stream failure.")
        await kernel._register_debugging_intake_resume(
            run=run,
            history=[{"role": "user", "content": "Audit stream failure."}],
            secondary_system="",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            tools=TOOLS,
            tool_choice="auto",
            data=response("What happened?"),
        )
        state = next(iter(kernel._pending_debugging_intake_resumes.values()))
        matched = await kernel._consume_pending_debugging_intake_resume([
            {"role": "assistant", "content": state.user_visible_response},
            {"role": "user", "content": "It disconnected."},
        ])
        assert matched is not None and state.in_flight
        await kernel._rearm_pending_debugging_resumes_for_messages([
            {"role": "assistant", "content": state.user_visible_response},
            {"role": "user", "content": "It disconnected."},
        ])
        assert state.in_flight is False


async def main():
    await intake_resume_survives_failure()
    await clarification_resume_survives_failure()
    await permissive_single_pending_fallback_is_preserved()
    await no_tool_intake_behavior_is_unchanged()
    await completed_runs_leave_live_memory()
    await evidence_scan_runs_off_event_loop()
    await safe_stream_rearms_failed_debugging_resume()
    await stream_rearm_helper_restores_retryability()
    print("crash-resilience tests: PASS")


if __name__ == "__main__":
    asyncio.run(main())
