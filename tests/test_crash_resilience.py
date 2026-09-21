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


async def pending_debugging_resumes_require_positive_identity():
    for mode in ("code-debugging", "code-debugging-deep"):
        m = load(mode)
        with tempfile.TemporaryDirectory() as td:
            m.DEBUGGING_REPORTS_ROOT = Path(td)
            kernel = m.JackQwenKernel(FakeBackend([]), m.CFG)

            intake_run = m._debugging_create_run("Audit project A.")
            await kernel._register_debugging_intake_resume(
                run=intake_run,
                history=[{"role": "user", "content": "Audit project A."}],
                secondary_system="",
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                tools=TOOLS,
                tool_choice="auto",
                data=response("Any symptoms for project A?"),
            )
            intake_state = next(iter(kernel._pending_debugging_intake_resumes.values()))

            unrelated = [{"role": "user", "content": "Audit unrelated project B."}]
            unmatched = await kernel._consume_pending_debugging_intake_resume(unrelated)
            assert unmatched is None
            assert kernel._pending_debugging_intake_resumes.get(intake_state.resume_id) is intake_state
            assert intake_state.in_flight is False

            intake_reply = [
                {"role": "user", "content": "Audit project A."},
                {"role": "assistant", "content": intake_state.user_visible_response},
                {"role": "user", "content": "No additional symptoms."},
            ]
            matched = await kernel._consume_pending_debugging_intake_resume(intake_reply)
            assert matched is not None
            assert matched[0] is intake_state
            assert intake_state.in_flight is True

            await kernel._rearm_pending_debugging_resumes_for_messages(unrelated)
            assert intake_state.in_flight is True
            await kernel._rearm_pending_debugging_resumes_for_messages(intake_reply)
            assert intake_state.in_flight is False

            clarification_run = m._debugging_create_run("Audit project C.")
            m._debugging_freeze_intake(clarification_run)
            await kernel._register_debugging_user_resume(
                stage_key="debug_pass_1",
                history=m._debugging_fresh_pass_history(clarification_run, 1),
                secondary_system="",
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                tools=TOOLS,
                tool_choice="auto",
                data=response(""),
                question="What exact error appears in project C?",
                debugging_run_id=clarification_run.run_id,
            )
            clarification_state = next(iter(kernel._pending_debugging_user_resumes.values()))

            unmatched = await kernel._consume_pending_debugging_user_resume(unrelated)
            assert unmatched is None
            assert kernel._pending_debugging_user_resumes.get(clarification_state.resume_id) is clarification_state
            assert clarification_state.in_flight is False

            clarification_reply = [
                {"role": "user", "content": "Audit project C."},
                {"role": "assistant", "content": clarification_state.user_visible_question},
                {"role": "user", "content": "The exact error is E42."},
            ]
            matched = await kernel._consume_pending_debugging_user_resume(clarification_reply)
            assert matched is not None
            assert matched[0] is clarification_state
            assert clarification_state.in_flight is True

            await kernel._rearm_pending_debugging_resumes_for_messages(unrelated)
            assert clarification_state.in_flight is True
            await kernel._rearm_pending_debugging_resumes_for_messages(clarification_reply)
            assert clarification_state.in_flight is False


async def unrelated_request_starts_its_own_debugging_run():
    for mode in ("code-debugging", "code-debugging-deep"):
        m = load(mode)
        with tempfile.TemporaryDirectory() as td:
            m.DEBUGGING_REPORTS_ROOT = Path(td)
            backend = FakeBackend([response("What symptoms have you seen in project B?")])
            kernel = m.JackQwenKernel(backend, m.CFG)

            run_a = m._debugging_create_run("Audit project A.")
            await kernel._register_debugging_intake_resume(
                run=run_a,
                history=[{"role": "user", "content": "Audit project A."}],
                secondary_system="",
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                tools=TOOLS,
                tool_choice="auto",
                data=response("Any symptoms for project A?"),
            )
            state_a = next(iter(kernel._pending_debugging_intake_resumes.values()))

            result = await kernel.run({
                "messages": [{"role": "user", "content": "Audit unrelated project B."}],
                "tools": TOOLS,
                "tool_choice": "auto",
            })

            assert "project B" in (result.content or "")
            assert kernel._pending_debugging_intake_resumes.get(state_a.resume_id) is state_a
            assert state_a.in_flight is False
            assert len(m._DEBUGGING_RUNS) == 2
            assert len(kernel._pending_debugging_intake_resumes) == 2
            assert any(
                state.run_id != run_a.run_id
                for state in kernel._pending_debugging_intake_resumes.values()
            )


async def interleaved_a_b_a_resumes_original_transaction():
    # One focused end-to-end routing regression in standard Code Debugging mode:
    # A pauses -> unrelated B starts independently -> A resumes A.
    m = load("code-debugging")

    # Intake resume lifecycle.
    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)
        backend = FakeBackend([
            response("What symptoms have you seen in project B?"),
            response("Do you have any logs for project A?"),
        ])
        kernel = m.JackQwenKernel(backend, m.CFG)

        run_a = m._debugging_create_run("Audit project A.")
        await kernel._register_debugging_intake_resume(
            run=run_a,
            history=[{"role": "user", "content": "Audit project A."}],
            secondary_system="",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            tools=TOOLS,
            tool_choice="auto",
            data=response("Any symptoms for project A?"),
        )
        state_a = next(iter(kernel._pending_debugging_intake_resumes.values()))
        original_a_resume_id = state_a.resume_id

        result_b = await kernel.run({
            "messages": [{"role": "user", "content": "Audit unrelated project B."}],
            "tools": TOOLS,
            "tool_choice": "auto",
        })
        assert "project B" in (result_b.content or "")
        assert kernel._pending_debugging_intake_resumes.get(original_a_resume_id) is state_a
        assert state_a.in_flight is False

        run_ids_after_b = set(m._DEBUGGING_RUNS)
        assert run_a.run_id in run_ids_after_b
        assert len(run_ids_after_b) == 2
        run_b_id = next(run_id for run_id in run_ids_after_b if run_id != run_a.run_id)

        result_a = await kernel.run({
            "messages": [
                {"role": "user", "content": "Audit project A."},
                {"role": "assistant", "content": state_a.user_visible_response},
                {"role": "user", "content": "No additional symptoms for A."},
            ],
            "tools": TOOLS,
            "tool_choice": "auto",
        })
        assert "logs for project A" in (result_a.content or "")
        assert original_a_resume_id not in kernel._pending_debugging_intake_resumes
        assert run_a.run_id in m._DEBUGGING_RUNS
        assert run_b_id in m._DEBUGGING_RUNS

        a_successors = [
            state for state in kernel._pending_debugging_intake_resumes.values()
            if state.run_id == run_a.run_id
        ]
        b_pending = [
            state for state in kernel._pending_debugging_intake_resumes.values()
            if state.run_id == run_b_id
        ]
        assert len(a_successors) == 1
        assert len(b_pending) == 1
        assert a_successors[0].resume_id != original_a_resume_id
        assert a_successors[0].in_flight is False
        assert b_pending[0].in_flight is False

    # In-pass clarification resume lifecycle.
    m = load("code-debugging")
    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)
        backend = FakeBackend([
            response("What symptoms have you seen in project B?"),
            response("DEBUGGING_USER_QUESTION: Does E42 occur before any file write?"),
        ])
        kernel = m.JackQwenKernel(backend, m.CFG)

        run_a = m._debugging_create_run("Audit project A clarification.")
        m._debugging_freeze_intake(run_a)
        await kernel._register_debugging_user_resume(
            stage_key="debug_pass_1",
            history=m._debugging_fresh_pass_history(run_a, 1),
            secondary_system="",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            tools=TOOLS,
            tool_choice="auto",
            data=response(""),
            question="What exact error appears in project A?",
            debugging_run_id=run_a.run_id,
        )
        state_a = next(iter(kernel._pending_debugging_user_resumes.values()))
        original_a_resume_id = state_a.resume_id

        result_b = await kernel.run({
            "messages": [{"role": "user", "content": "Audit unrelated project B."}],
            "tools": TOOLS,
            "tool_choice": "auto",
        })
        assert "project B" in (result_b.content or "")
        assert kernel._pending_debugging_user_resumes.get(original_a_resume_id) is state_a
        assert state_a.in_flight is False

        run_ids_after_b = set(m._DEBUGGING_RUNS)
        assert run_a.run_id in run_ids_after_b
        assert len(run_ids_after_b) == 2
        run_b_id = next(run_id for run_id in run_ids_after_b if run_id != run_a.run_id)

        result_a = await kernel.run({
            "messages": [
                {"role": "user", "content": "Audit project A clarification."},
                {"role": "assistant", "content": state_a.user_visible_question},
                {"role": "user", "content": "The exact error is E42."},
            ],
            "tools": TOOLS,
            "tool_choice": "auto",
        })
        assert "Does E42 occur" in (result_a.content or "")
        assert original_a_resume_id not in kernel._pending_debugging_user_resumes
        assert run_a.run_id in m._DEBUGGING_RUNS
        assert run_b_id in m._DEBUGGING_RUNS

        a_successors = [
            state for state in kernel._pending_debugging_user_resumes.values()
            if state.debugging_run_id == run_a.run_id
        ]
        assert len(a_successors) == 1
        assert a_successors[0].resume_id != original_a_resume_id
        assert a_successors[0].stage_key == "debug_pass_1"
        assert a_successors[0].in_flight is False


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
        assert run.run_id in m._DEBUGGING_RUNS
        assert run.final_report_committed is True
        assert run.final_report == (result.content or "")

        followup_messages = [
            {"role": "user", "content": "Audit a completed project."},
            {"role": "assistant", "content": result.content or ""},
            {"role": "user", "content": "Where is the report saved?"},
        ]
        matched = m._debugging_completed_run_for_history(followup_messages)
        assert matched is run
        projected = m._debugging_followup_history(run, followup_messages)
        assert str(run.report_path) in projected[-1]["content"]
        assert "Where is the report saved?" in projected[-1]["content"]

        backend.queue.append(response("The completed report is still available for follow-up discussion."))
        followup = await kernel.run({
            "messages": followup_messages,
            "tools": TOOLS,
            "tool_choice": "auto",
        })
        assert "still available" in (followup.content or "")
        assert set(m._DEBUGGING_RUNS) == {run.run_id}


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
    await pending_debugging_resumes_require_positive_identity()
    await unrelated_request_starts_its_own_debugging_run()
    await interleaved_a_b_a_resumes_original_transaction()
    await no_tool_intake_behavior_is_unchanged()
    await completed_runs_leave_live_memory()
    await evidence_scan_runs_off_event_loop()
    await safe_stream_rearms_failed_debugging_resume()
    await stream_rearm_helper_restores_retryability()
    print("crash-resilience tests: PASS")


if __name__ == "__main__":
    asyncio.run(main())
