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


async def pending_pass_durability_retry_does_not_regenerate_cognition():
    m = load("code-debugging")

    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)

        run = m._debugging_create_run("Audit persistence retry.")
        m._debugging_freeze_intake(run)

        original_pass_1 = "Pass 1 original confirmed finding."

        backend = FakeBackend([
            response(original_pass_1),
            response("Pass 2 completed with no additional material finding."),
            response("Pass 3 completed with no additional material finding."),
            response("Pass 4 completed with no additional material finding."),
            response("Pass 5 completed with no additional material finding."),
            response("Final repair specification."),
        ])
        kernel = m.JackQwenKernel(backend, m.CFG)

        original_fsync = m.os.fsync
        failed_once = False

        def fail_first_fsync(fd):
            nonlocal failed_once
            if not failed_once:
                failed_once = True
                raise OSError("synthetic pass durability interruption")
            return original_fsync(fd)

        m.os.fsync = fail_first_fsync

        try:
            try:
                await kernel._run_code_debugging_nonstream(
                    run=run,
                    secondary_system="",
                    usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    tools=TOOLS,
                    tool_choice="auto",
                    start_pass=1,
                )
            except OSError as exc:
                assert "synthetic pass durability interruption" in str(exc)
            else:
                raise AssertionError("first durability failure should propagate")
        finally:
            m.os.fsync = original_fsync

        # Pass 1 cognition completed, but durability did not.
        assert 1 not in run.summaries
        assert run.pending_summaries[1] == original_pass_1

        # Only Pass 1 inference should have been consumed.
        assert len(backend.queue) == 5

        # Retry the same transaction boundary. Jack must persist the already
        # completed Pass 1 summary instead of invoking Pass 1 again.
        result = await kernel._run_code_debugging_nonstream(
            run=run,
            secondary_system="",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            tools=TOOLS,
            tool_choice="auto",
            start_pass=1,
        )

        assert run.summaries[1] == original_pass_1
        assert 1 not in run.pending_summaries

        # Exactly the remaining Passes 2-5 plus the final reporter are consumed.
        assert backend.queue == []

        assert run.final_report_committed is True
        assert result.content == "Final repair specification."


async def public_run_retry_recovers_pending_pass_without_starting_new_run():
    m = load("code-debugging")

    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)

        original_pass_1 = "Pass 1 original public-run finding."

        backend = FakeBackend([
            response("DEBUGGING_INTAKE_COMPLETE: Intake complete."),
            response(original_pass_1),
            response("Pass 2 completed with no additional material finding."),
            response("Pass 3 completed with no additional material finding."),
            response("Pass 4 completed with no additional material finding."),
            response("Pass 5 completed with no additional material finding."),
            response("Final repair specification."),
        ])
        kernel = m.JackQwenKernel(backend, m.CFG)

        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": "Audit persistence retry through public run.",
                }
            ],
            "tools": TOOLS,
            "tool_choice": "auto",
        }

        original_atomic_replace = m._debugging_atomic_replace_report
        failed_once = False

        def fail_pass_1_persistence(report_path, report_text):
            nonlocal failed_once

            if not failed_once and original_pass_1 in report_text:
                failed_once = True
                raise OSError("synthetic public-run durability interruption")

            return original_atomic_replace(report_path, report_text)

        m._debugging_atomic_replace_report = fail_pass_1_persistence

        try:
            try:
                await kernel.run(request_body)
            except OSError as exc:
                assert "synthetic public-run durability interruption" in str(exc)
            else:
                raise AssertionError(
                    "public run should propagate the first durability failure"
                )
        finally:
            m._debugging_atomic_replace_report = original_atomic_replace

        # One debugging transaction exists and its completed Pass 1 cognition
        # survived without becoming committed authority.
        assert len(m._DEBUGGING_RUNS) == 1

        run = next(iter(m._DEBUGGING_RUNS.values()))

        assert 1 not in run.summaries
        assert run.pending_summaries[1] == original_pass_1

        # Intake + Pass 1 were the only inference calls consumed.
        assert len(backend.queue) == 5

        # The caller retries the same public request after the transient
        # persistence failure. Jack must recover the existing transaction,
        # persist Pass 1, and continue at Pass 2. It must not create a new run,
        # rerun intake, or regenerate Pass 1.
        result = await kernel.run(request_body)

        assert len(m._DEBUGGING_RUNS) == 1
        assert next(iter(m._DEBUGGING_RUNS.values())) is run

        assert run.summaries[1] == original_pass_1
        assert 1 not in run.pending_summaries

        assert run.final_report_committed is True
        assert result.content == "Final repair specification."

        # Exactly Passes 2-5 plus the final reporter were consumed.
        assert backend.queue == []


async def different_request_does_not_capture_pending_durability_transaction():
    m = load("code-debugging")

    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)

        original_pass_1 = "Pass 1 request-A finding."

        request_a = {
            "messages": [
                {
                    "role": "user",
                    "content": "Audit durability transaction A.",
                }
            ],
            "tools": TOOLS,
            "tool_choice": "auto",
        }

        request_b = {
            "messages": [
                {
                    "role": "user",
                    "content": "Audit unrelated durability transaction B.",
                }
            ],
            "tools": TOOLS,
            "tool_choice": "auto",
        }

        backend = FakeBackend([
            response("DEBUGGING_INTAKE_COMPLETE: Intake A complete."),
            response(original_pass_1),
            response("What symptoms have you seen in request B?"),
        ])
        kernel = m.JackQwenKernel(backend, m.CFG)

        original_atomic_replace = m._debugging_atomic_replace_report
        failed_once = False

        def fail_request_a_pass_1(report_path, report_text):
            nonlocal failed_once

            if not failed_once and original_pass_1 in report_text:
                failed_once = True
                raise OSError("synthetic request-A durability interruption")

            return original_atomic_replace(report_path, report_text)

        m._debugging_atomic_replace_report = fail_request_a_pass_1

        try:
            try:
                await kernel.run(request_a)
            except OSError as exc:
                assert "synthetic request-A durability interruption" in str(exc)
            else:
                raise AssertionError(
                    "request A should fail at the synthetic durability boundary"
                )
        finally:
            m._debugging_atomic_replace_report = original_atomic_replace

        assert len(m._DEBUGGING_RUNS) == 1

        run_a = next(iter(m._DEBUGGING_RUNS.values()))
        assert 1 not in run_a.summaries
        assert run_a.pending_summaries[1] == original_pass_1

        result_b = await kernel.run(request_b)

        # Request B is not an exact owner match, so it must start independently.
        assert len(m._DEBUGGING_RUNS) == 2

        assert 1 not in run_a.summaries
        assert run_a.pending_summaries[1] == original_pass_1
        assert run_a.final_report_committed is False

        run_b_candidates = [
            run
            for run in m._DEBUGGING_RUNS.values()
            if run is not run_a
        ]
        assert len(run_b_candidates) == 1

        run_b = run_b_candidates[0]

        assert run_b.request_fingerprint == m._debugging_request_fingerprint(
            m.sanitize_agent_request(request_b)
        )
        assert run_b.request_fingerprint != run_a.request_fingerprint

        assert "request B" in (result_b.content or "")
        assert backend.queue == []


async def ambiguous_exact_durability_ownership_fails_closed():
    m = load("code-debugging")

    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)

        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": "Audit ambiguous durability ownership.",
                }
            ],
            "tools": TOOLS,
            "tool_choice": "auto",
        }

        sanitized = m.sanitize_agent_request(request_body)
        fingerprint = m._debugging_request_fingerprint(sanitized)

        run_a = m._debugging_create_run(
            "Audit ambiguous durability ownership.",
            request_fingerprint=fingerprint,
        )
        m._debugging_freeze_intake(run_a)
        run_a.pending_summaries[1] = "Candidate A completed cognition."

        run_b = m._debugging_create_run(
            "Audit ambiguous durability ownership.",
            request_fingerprint=fingerprint,
        )
        m._debugging_freeze_intake(run_b)
        run_b.pending_summaries[1] = "Candidate B completed cognition."

        run_a_summaries_before = dict(run_a.summaries)
        run_b_summaries_before = dict(run_b.summaries)
        run_a_pending_before = dict(run_a.pending_summaries)
        run_b_pending_before = dict(run_b.pending_summaries)

        kernel = m.JackQwenKernel(FakeBackend([]), m.CFG)

        try:
            await kernel.run(request_body)
        except m.HTTPException as exc:
            assert exc.status_code == 409
            assert "will not guess" in str(exc.detail)
        else:
            raise AssertionError(
                "ambiguous exact durability ownership must fail closed"
            )

        # Neither candidate may be promoted, erased, mutated, or selected.
        assert run_a.summaries == run_a_summaries_before
        assert run_b.summaries == run_b_summaries_before
        assert run_a.pending_summaries == run_a_pending_before
        assert run_b.pending_summaries == run_b_pending_before

        assert 1 not in run_a.summaries
        assert 1 not in run_b.summaries
        assert run_a.pending_summaries[1] == "Candidate A completed cognition."
        assert run_b.pending_summaries[1] == "Candidate B completed cognition."


async def clarification_durability_retry_does_not_regenerate_cognition():
    m = load("code-debugging")

    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)

        run = m._debugging_create_run("Audit clarification durability.")
        m._debugging_freeze_intake(run)

        original_pass_1 = "Pass 1 clarification-confirmed finding."

        backend = FakeBackend([
            response(original_pass_1),
            response("Pass 2 completed with no additional material finding."),
            response("Pass 3 completed with no additional material finding."),
            response("Pass 4 completed with no additional material finding."),
            response("Pass 5 completed with no additional material finding."),
            response("Final repair specification."),
        ])
        kernel = m.JackQwenKernel(backend, m.CFG)

        await kernel._register_debugging_user_resume(
            stage_key="debug_pass_1",
            history=m._debugging_fresh_pass_history(run, 1),
            secondary_system="",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            tools=TOOLS,
            tool_choice="auto",
            data=response(""),
            question="What exact error appears?",
            debugging_run_id=run.run_id,
        )

        state = next(iter(kernel._pending_debugging_user_resumes.values()))

        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": "Audit clarification durability.",
                },
                {
                    "role": "assistant",
                    "content": state.user_visible_question,
                },
                {
                    "role": "user",
                    "content": "The exact error is E42.",
                },
            ],
            "tools": TOOLS,
            "tool_choice": "auto",
        }

        original_atomic_replace = m._debugging_atomic_replace_report
        failed_once = False

        def fail_pass_1_persistence(report_path, report_text):
            nonlocal failed_once

            if not failed_once and original_pass_1 in report_text:
                failed_once = True
                raise OSError("synthetic clarification durability interruption")

            return original_atomic_replace(report_path, report_text)

        m._debugging_atomic_replace_report = fail_pass_1_persistence

        try:
            try:
                await kernel.run(request_body)
            except OSError as exc:
                assert "synthetic clarification durability interruption" in str(exc)
            else:
                raise AssertionError(
                    "clarification completion should fail at durability boundary"
                )
        finally:
            m._debugging_atomic_replace_report = original_atomic_replace

        assert 1 not in run.summaries
        assert run.pending_summaries[1] == original_pass_1

        assert kernel._pending_debugging_user_resumes.get(state.resume_id) is state
        assert state.in_flight is False

        # Only the completed Pass 1 inference was consumed.
        assert len(backend.queue) == 5

        # Retrying the same clarification transaction must commit the already
        # completed Pass 1 cognition, not invoke Pass 1 again.
        result = await kernel.run(request_body)

        assert run.summaries[1] == original_pass_1
        assert 1 not in run.pending_summaries

        assert state.resume_id not in kernel._pending_debugging_user_resumes

        assert run.final_report_committed is True
        assert result.content == "Final repair specification."

        # Only Passes 2-5 and the final reporter should remain after recovery.
        assert backend.queue == []


async def tool_resume_durability_retry_does_not_regenerate_cognition():
    m = load("code-debugging")

    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)

        run = m._debugging_create_run("Audit tool-resume durability.")
        m._debugging_freeze_intake(run)

        call_id = "call-debug-durability-1"
        original_pass_1 = "Pass 1 tool-confirmed finding."

        backend = FakeBackend([
            response(original_pass_1),
            response("Pass 2 completed with no additional material finding."),
            response("Pass 3 completed with no additional material finding."),
            response("Pass 4 completed with no additional material finding."),
            response("Pass 5 completed with no additional material finding."),
            response("Final repair specification."),
        ])
        kernel = m.JackQwenKernel(backend, m.CFG)

        tool_call_stage = {
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command":"echo diagnostic"}',
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        }

        await kernel._register_stage_tool_resume(
            stage_key="debug_pass_1",
            history=m._debugging_fresh_pass_history(run, 1),
            secondary_system="",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            tools=TOOLS,
            tool_choice="auto",
            data=tool_call_stage,
            debugging_run_id=run.run_id,
        )

        state = kernel._pending_tool_resumes[call_id]

        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": "Audit tool-resume durability.",
                },
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": '{"command":"echo diagnostic"}',
                        },
                    }],
                },
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": "bash",
                    "content": "diagnostic output",
                },
            ],
            "tools": TOOLS,
            "tool_choice": "auto",
        }

        original_atomic_replace = m._debugging_atomic_replace_report
        failed_once = False

        def fail_pass_1_persistence(report_path, report_text):
            nonlocal failed_once

            if not failed_once and original_pass_1 in report_text:
                failed_once = True
                raise OSError("synthetic tool-resume durability interruption")

            return original_atomic_replace(report_path, report_text)

        m._debugging_atomic_replace_report = fail_pass_1_persistence

        try:
            try:
                await kernel.run(request_body)
            except OSError as exc:
                assert "synthetic tool-resume durability interruption" in str(exc)
            else:
                raise AssertionError(
                    "tool-resume completion should fail at durability boundary"
                )
        finally:
            m._debugging_atomic_replace_report = original_atomic_replace

        # Post-tool Pass 1 cognition completed but is not yet authoritative.
        assert 1 not in run.summaries
        assert run.pending_summaries[1] == original_pass_1

        # The tool checkpoint remains live and retryable.
        assert kernel._pending_tool_resumes.get(call_id) is state
        assert state.in_flight is False

        # Only the completed post-tool Pass 1 inference was consumed.
        assert len(backend.queue) == 5

        # Retry the identical tool-result transaction. Jack must persist the
        # already-completed Pass 1 cognition rather than invoke Pass 1 again.
        result = await kernel.run(request_body)

        assert run.summaries[1] == original_pass_1
        assert 1 not in run.pending_summaries

        assert call_id not in kernel._pending_tool_resumes

        assert run.final_report_committed is True
        assert result.content == "Final repair specification."

        # Exactly Passes 2-5 plus the final reporter were consumed.
        assert backend.queue == []


async def streaming_public_retry_recovers_pending_pass_without_regeneration():
    m = load("code-debugging")

    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)

        original_pass_1 = "Pass 1 original streamed finding."

        backend = FakeStreamBackend([
            response("DEBUGGING_INTAKE_COMPLETE: Stream intake complete."),
            response(original_pass_1),
            response("Pass 2 completed with no additional material finding."),
            response("Pass 3 completed with no additional material finding."),
            response("Pass 4 completed with no additional material finding."),
            response("Pass 5 completed with no additional material finding."),
            response("Final streamed repair specification."),
        ])
        kernel = m.JackQwenKernel(backend, m.CFG)

        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": "Audit streaming persistence retry.",
                }
            ],
            "tools": TOOLS,
            "tool_choice": "auto",
        }

        original_atomic_replace = m._debugging_atomic_replace_report
        failed_once = False

        def fail_pass_1_persistence(report_path, report_text):
            nonlocal failed_once

            if not failed_once and original_pass_1 in report_text:
                failed_once = True
                raise OSError("synthetic streamed durability interruption")

            return original_atomic_replace(report_path, report_text)

        m._debugging_atomic_replace_report = fail_pass_1_persistence

        try:
            try:
                async for _chunk in kernel.stream(request_body):
                    pass
            except OSError as exc:
                assert "synthetic streamed durability interruption" in str(exc)
            else:
                raise AssertionError(
                    "streaming request should fail at the first durability boundary"
                )
        finally:
            m._debugging_atomic_replace_report = original_atomic_replace

        assert len(m._DEBUGGING_RUNS) == 1

        run = next(iter(m._DEBUGGING_RUNS.values()))

        assert 1 not in run.summaries
        assert run.pending_summaries[1] == original_pass_1
        assert run.final_report_committed is False

        # Intake + Pass 1 were the only streamed inference calls consumed.
        assert len(backend.queue) == 5

        # Retry the identical public streaming request. Jack must recover the
        # original run, persist Pass 1 without inference, and begin at Pass 2.
        chunks = []
        async for chunk in kernel.stream(request_body):
            chunks.append(chunk)

        assert len(m._DEBUGGING_RUNS) == 1
        assert next(iter(m._DEBUGGING_RUNS.values())) is run

        assert run.summaries[1] == original_pass_1
        assert 1 not in run.pending_summaries

        assert run.final_report_committed is True
        assert run.final_report == "Final streamed repair specification."

        # Exactly Passes 2-5 plus the final reporter were consumed.
        assert backend.queue == []

        wire = b"".join(chunks)
        assert b"Final streamed repair specification." in wire
        assert wire.endswith(b"data: [DONE]\n\n")


async def final_report_durability_retry_does_not_regenerate_report():
    m = load("code-debugging")

    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)

        run = m._debugging_create_run("Audit final-report durability.")
        m._debugging_freeze_intake(run)

        for pass_number in range(1, m.DEBUGGING_PASS_COUNT + 1):
            m._debugging_commit_pass_summary(
                run,
                pass_number,
                response(
                    f"Pass {pass_number} completed with no additional material finding."
                ),
            )

        original_final = "Original final repair specification."
        regenerated_final = "Regenerated final repair specification."

        backend = FakeBackend([
            response(original_final),
            response(regenerated_final),
        ])
        kernel = m.JackQwenKernel(backend, m.CFG)

        original_atomic_replace = m._debugging_atomic_replace_report
        failed_once = False

        def fail_original_final_persistence(report_path, report_text):
            nonlocal failed_once

            if not failed_once and original_final in report_text:
                failed_once = True
                raise OSError("synthetic final-report durability interruption")

            return original_atomic_replace(report_path, report_text)

        m._debugging_atomic_replace_report = fail_original_final_persistence

        try:
            try:
                await kernel._run_code_debugging_nonstream(
                    run=run,
                    secondary_system="",
                    usage={
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                    },
                    tools=TOOLS,
                    tool_choice="auto",
                    start_pass=m.DEBUGGING_PASS_COUNT + 1,
                )
            except OSError as exc:
                assert "synthetic final-report durability interruption" in str(exc)
            else:
                raise AssertionError(
                    "final report should fail at the synthetic durability boundary"
                )
        finally:
            m._debugging_atomic_replace_report = original_atomic_replace

        assert run.final_report_committed is False
        assert run.final_report == ""

        # The original final reporter inference was consumed.
        assert len(backend.queue) == 1

        # Retry. Jack should eventually preserve the already-generated report
        # rather than invoke the reporter again.
        result = await kernel._run_code_debugging_nonstream(
            run=run,
            secondary_system="",
            usage={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
            tools=TOOLS,
            tool_choice="auto",
            start_pass=m.DEBUGGING_PASS_COUNT + 1,
        )

        assert run.final_report_committed is True
        assert run.final_report == original_final
        assert result.content == original_final

        # The alternate reporter response must remain unused.
        assert len(backend.queue) == 1
        assert (
            ((backend.queue[0].get("choices") or [{}])[0].get("message") or {})
            .get("content")
            == regenerated_final
        )



async def public_retry_recovers_pending_final_report_without_regeneration():
    m = load("code-debugging")

    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)

        original_final = "Original public final repair specification."
        unexpected_retry_inference = "What symptoms have you seen on retry?"

        backend = FakeBackend([
            response("DEBUGGING_INTAKE_COMPLETE: Intake complete."),
            response("Pass 1 finding."),
            response("Pass 2 finding."),
            response("Pass 3 finding."),
            response("Pass 4 finding."),
            response("Pass 5 finding."),
            response(original_final),

            # This must remain unused if public durability recovery is correct.
            response(unexpected_retry_inference),
        ])
        kernel = m.JackQwenKernel(backend, m.CFG)

        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": "Audit public final-report durability.",
                }
            ],
            "tools": TOOLS,
            "tool_choice": "auto",
        }

        original_atomic_replace = m._debugging_atomic_replace_report
        failed_once = False

        def fail_final_persistence(report_path, report_text):
            nonlocal failed_once

            if not failed_once and original_final in report_text:
                failed_once = True
                raise OSError(
                    "synthetic public final-report durability interruption"
                )

            return original_atomic_replace(report_path, report_text)

        m._debugging_atomic_replace_report = fail_final_persistence

        try:
            try:
                await kernel.run(request_body)
            except OSError as exc:
                assert (
                    "synthetic public final-report durability interruption"
                    in str(exc)
                )
            else:
                raise AssertionError(
                    "public final report should fail at durability boundary"
                )
        finally:
            m._debugging_atomic_replace_report = original_atomic_replace

        assert len(m._DEBUGGING_RUNS) == 1

        run = next(iter(m._DEBUGGING_RUNS.values()))

        assert run.final_report_committed is False
        assert run.final_report == ""
        assert run.pending_final_report == original_final
        assert set(run.summaries) == set(
            range(0, m.DEBUGGING_PASS_COUNT + 1)
        )

        # Only the deliberately unused retry inference remains.
        assert len(backend.queue) == 1

        # Retry the exact public request. Jack must recover this run and persist
        # the already-completed final report without starting another run or
        # invoking any model stage.
        result = await kernel.run(request_body)

        assert len(m._DEBUGGING_RUNS) == 1
        assert next(iter(m._DEBUGGING_RUNS.values())) is run

        assert run.final_report_committed is True
        assert run.final_report == original_final
        assert run.pending_final_report == ""

        assert result.content == original_final

        # Proof that no intake, pass, or final-reporter inference ran on retry.
        assert len(backend.queue) == 1
        assert (
            ((backend.queue[0].get("choices") or [{}])[0].get("message") or {})
            .get("content")
            == unexpected_retry_inference
        )


async def streaming_retry_recovers_pending_final_report_without_regeneration():
    m = load("code-debugging")

    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)

        original_final = "Original streamed final repair specification."
        unexpected_retry_inference = "Unexpected streamed retry inference."

        backend = FakeStreamBackend([
            response("DEBUGGING_INTAKE_COMPLETE: Intake complete."),
            response("Pass 1 finding."),
            response("Pass 2 finding."),
            response("Pass 3 finding."),
            response("Pass 4 finding."),
            response("Pass 5 finding."),
            response(original_final),

            # Must remain unused if recovery is persistence-only.
            response(unexpected_retry_inference),
        ])
        kernel = m.JackQwenKernel(backend, m.CFG)

        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": "Audit streamed final-report durability.",
                }
            ],
            "tools": TOOLS,
            "tool_choice": "auto",
        }

        original_atomic_replace = m._debugging_atomic_replace_report
        failed_once = False

        def fail_final_persistence(report_path, report_text):
            nonlocal failed_once

            if not failed_once and original_final in report_text:
                failed_once = True
                raise OSError(
                    "synthetic streamed final-report durability interruption"
                )

            return original_atomic_replace(report_path, report_text)

        m._debugging_atomic_replace_report = fail_final_persistence

        first_chunks = []

        try:
            try:
                async for chunk in kernel.stream(request_body):
                    first_chunks.append(chunk)
            except OSError as exc:
                assert (
                    "synthetic streamed final-report durability interruption"
                    in str(exc)
                )
            else:
                raise AssertionError(
                    "streamed final report should fail at durability boundary"
                )
        finally:
            m._debugging_atomic_replace_report = original_atomic_replace

        assert len(m._DEBUGGING_RUNS) == 1

        run = next(iter(m._DEBUGGING_RUNS.values()))

        assert run.final_report_committed is False
        assert run.final_report == ""
        assert run.pending_final_report == original_final

        assert set(run.summaries) == set(
            range(0, m.DEBUGGING_PASS_COUNT + 1)
        )

        # The completed report was already observable on the first stream,
        # but it did not become durable authority.
        assert original_final.encode("utf-8") in b"".join(first_chunks)

        # Only the deliberately unused retry inference remains.
        assert len(backend.queue) == 1

        retry_chunks = []
        async for chunk in kernel.stream(request_body):
            retry_chunks.append(chunk)

        # Exact public streaming retry must recover the original transaction,
        # not create another debugging run.
        assert len(m._DEBUGGING_RUNS) == 1
        assert next(iter(m._DEBUGGING_RUNS.values())) is run

        assert run.final_report_committed is True
        assert run.final_report == original_final
        assert run.pending_final_report == ""

        # Retry must emit the retained final report and complete normally.
        retry_wire = b"".join(retry_chunks)
        assert original_final.encode("utf-8") in retry_wire
        assert retry_wire.endswith(b"data: [DONE]\n\n")

        # No model stage may run during durability-only recovery.
        assert len(backend.queue) == 1
        assert (
            ((backend.queue[0].get("choices") or [{}])[0].get("message") or {})
            .get("content")
            == unexpected_retry_inference
        )

async def main():
    await streaming_retry_recovers_pending_final_report_without_regeneration()
    await public_retry_recovers_pending_final_report_without_regeneration()
    await final_report_durability_retry_does_not_regenerate_report()
    await streaming_public_retry_recovers_pending_pass_without_regeneration()
    await tool_resume_durability_retry_does_not_regenerate_cognition()
    await clarification_durability_retry_does_not_regenerate_cognition()
    await different_request_does_not_capture_pending_durability_transaction()
    await ambiguous_exact_durability_ownership_fails_closed()
    await public_run_retry_recovers_pending_pass_without_starting_new_run()
    await pending_pass_durability_retry_does_not_regenerate_cognition()
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
