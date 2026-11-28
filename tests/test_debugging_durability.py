import asyncio
import importlib.util
import os
import sys
import tempfile
import uuid
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "jack_kernel.py"


def load():
    os.environ["JACK_REASONING_LEVEL"] = "code-debugging"
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "off"
    os.environ["JACK_BACKEND_MODEL"] = "test-model"

    name = f"jack_test_debugging_durability_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def response(content):
    return {
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": content,
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        },
    }


def test_debugging_pass_commit_survives_durability_failure():
    m = load()

    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)

        run = m._debugging_create_run("Audit the project.")
        m._debugging_freeze_intake(run)

        original_report = run.report_path.read_text(encoding="utf-8")
        assert 1 not in run.summaries

        original_fsync = m.os.fsync

        def failing_fsync(_fd):
            raise OSError("synthetic durability failure")

        m.os.fsync = failing_fsync

        try:
            try:
                m._debugging_commit_pass_summary(
                    run,
                    1,
                    response("Pass 1 confirmed finding."),
                )
            except OSError as exc:
                assert "synthetic durability failure" in str(exc)
            else:
                raise AssertionError("synthetic fsync failure should propagate")
        finally:
            m.os.fsync = original_fsync

        # A failed durability commit must not advance host-owned memory.
        assert 1 not in run.summaries

        # Nor may it alter the authoritative durable report.
        assert run.report_path.read_text(encoding="utf-8") == original_report

        # The same pass must remain retryable after the transient disk failure.
        summary = m._debugging_commit_pass_summary(
            run,
            1,
            response("Pass 1 confirmed finding."),
        )

        assert summary == "Pass 1 confirmed finding."
        assert run.summaries[1] == "Pass 1 confirmed finding."

        final_report = run.report_path.read_text(encoding="utf-8")
        assert final_report == m._debugging_render_report_through(run, 1)


def test_debugging_pass_cognition_remains_pending_after_persistent_durability_failure():
    m = load()

    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)

        run = m._debugging_create_run("Audit the project.")
        m._debugging_freeze_intake(run)

        original_report = run.report_path.read_text(encoding="utf-8")
        exact_summary = "Pass 1 confirmed finding."

        original_fsync = m.os.fsync

        def failing_fsync(_fd):
            raise OSError("synthetic persistent durability failure")

        m.os.fsync = failing_fsync

        try:
            try:
                m._debugging_commit_pass_summary(
                    run,
                    1,
                    response(exact_summary),
                )
            except OSError as exc:
                assert "synthetic persistent durability failure" in str(exc)
            else:
                raise AssertionError("persistent durability failure should propagate")
        finally:
            m.os.fsync = original_fsync

        # The pass is not durable, so it must not become authoritative.
        assert 1 not in run.summaries
        assert run.report_path.read_text(encoding="utf-8") == original_report

        # But Jack must not discard already-completed probabilistic cognition.
        assert run.pending_summaries[1] == exact_summary

        # Retry persistence only. No model regeneration is involved.
        summary = m._debugging_retry_pending_pass_summary(run, 1)

        assert summary == exact_summary
        assert run.summaries[1] == exact_summary
        assert 1 not in run.pending_summaries
        assert (
            run.report_path.read_text(encoding="utf-8")
            == m._debugging_render_report_through(run, 1)
        )


def test_debugging_final_report_survives_durability_failure():
    m = load()

    with tempfile.TemporaryDirectory() as td:
        m.DEBUGGING_REPORTS_ROOT = Path(td)

        run = m._debugging_create_run("Audit the project.")
        m._debugging_freeze_intake(run)

        for pass_number in range(1, m.DEBUGGING_PASS_COUNT + 1):
            m._debugging_commit_pass_summary(
                run,
                pass_number,
                response(f"Pass {pass_number} confirmed finding."),
            )

        original_report = run.report_path.read_text(encoding="utf-8")
        assert run.final_report_committed is False

        original_fsync = m.os.fsync

        def failing_fsync(_fd):
            raise OSError("synthetic final-report durability failure")

        m.os.fsync = failing_fsync

        try:
            try:
                m._debugging_commit_final_report(
                    run,
                    response("Final repair specification."),
                )
            except OSError as exc:
                assert "synthetic final-report durability failure" in str(exc)
            else:
                raise AssertionError("synthetic final-report fsync failure should propagate")
        finally:
            m.os.fsync = original_fsync

        # Failed persistence must not falsely advertise a committed final report.
        assert run.final_report_committed is False
        assert m._DEBUGGING_RUNS.get(run.run_id) is run

        # The authoritative Pass 0..5 report must remain byte-for-byte unchanged.
        assert run.report_path.read_text(encoding="utf-8") == original_report

        # A retry after the transient failure must succeed exactly once.
        final_report = m._debugging_commit_final_report(
            run,
            response("Final repair specification."),
        )

        assert final_report == "Final repair specification."
        assert run.final_report_committed is True
        assert run.run_id not in m._DEBUGGING_RUNS

        durable = run.report_path.read_text(encoding="utf-8")
        assert durable.startswith(original_report)
        assert durable.count(m._DEBUGGING_FINAL_REPORT_HEADING) == 1
        assert durable.count("Final repair specification.") == 1


def test_completed_debugging_index_exact_identity_and_failure_recovery():
    m = load()
    try:
        with tempfile.TemporaryDirectory() as td:
            m.DEBUGGING_REPORTS_ROOT = Path(td)

            def prepared():
                run = m._debugging_create_run("Audit the project.")
                m._debugging_freeze_intake(run)
                for n in range(1, m.DEBUGGING_PASS_COUNT + 1):
                    m._debugging_commit_pass_summary(run, n, response(f"Pass {n} finding."))
                return run

            older, newer = prepared(), prepared()
            # Completion order must not override the newest registered identity.
            m._debugging_commit_final_report(newer, response("Identical final report."))
            m._debugging_commit_final_report(older, response("Identical final report."))
            assert not m._DEBUGGING_RUNS
            history = [{"role": "assistant", "content": "Identical final report."},
                       {"role": "user", "content": "Where is the report saved?"}]
            matched = m._debugging_completed_run_for_history(history)
            assert matched.run_id == newer.run_id
            assert matched.report_path == newer.report_path
            assert m._debugging_completed_run_for_history([
                {"role": "assistant", "content": "Identical final report"},
                history[-1],
            ]) is None
            assert m._debugging_completed_run_for_history([
                history[0], {"role": "user", "content": "Start a new code debugging run"},
            ]) is None
            row = m._DEBUGGING_COMPLETED_INDEX.execute(
                "SELECT digest, run_id, report_path, registration_order FROM completed_debugging"
            ).fetchone()
            assert row[0] == m._sha256_text("Identical final report.")
            assert row[1] == newer.run_id

            failed_index = prepared()
            original_index = m._debugging_completed_index
            def unavailable():
                raise m.sqlite3.OperationalError("synthetic completion-index failure")
            m._debugging_completed_index = unavailable
            try:
                assert m._debugging_commit_final_report(
                    failed_index, response("Durable despite index failure.")
                ) == "Durable despite index failure."
                assert m._DEBUGGING_RUNS.get(failed_index.run_id) is failed_index
                assert failed_index.final_report_committed
                failed_history = [
                    {"role": "assistant", "content": failed_index.final_report}, history[-1]
                ]
                assert m._debugging_completed_run_for_history(failed_history).run_id == failed_index.run_id
            finally:
                m._debugging_completed_index = original_index
            assert m._debugging_completed_run_for_history(failed_history).run_id == failed_index.run_id
            assert not m._DEBUGGING_RUNS
    finally:
        m._debugging_close_completed_index()


def test_debugging_registry_retires_only_unowned_runs():
    m = load()

    async def scenario():
        with tempfile.TemporaryDirectory() as td:
            m.DEBUGGING_REPORTS_ROOT = Path(td)
            kernel = m.JackQwenKernel(None, m.CFG)
            unrelated = m._debugging_create_run("Independent audit.")
            async with kernel._request_resume_scope():
                active = m._debugging_create_run("Active audit.")
                assert m._DEBUGGING_RUNS.get(active.run_id) is active
                # An unrelated request's cleanup must never retire active work.
                kernel._debugging_retire_unreferenced_run(active.run_id)
                assert m._DEBUGGING_RUNS.get(active.run_id) is active
            assert active.run_id not in m._DEBUGGING_RUNS
            assert m._DEBUGGING_RUNS.get(unrelated.run_id) is unrelated

            async with kernel._request_resume_scope():
                resumable = m._debugging_create_run("Pending durable audit.")
                resumable.pending_summaries[1] = "Completed cognition awaiting persistence."
            assert m._DEBUGGING_RUNS.get(resumable.run_id) is resumable

            async with kernel._request_resume_scope():
                waiting = m._debugging_create_run("Waiting for intake.")
                state = m.PendingDebuggingIntakeResume(
                    resume_id="intake", run_id=waiting.run_id, history=[],
                    secondary_system="", usage={}, tools=None, tool_choice=None,
                    user_visible_response="Please clarify.", created_at=0,
                )
                kernel._pending_debugging_intake_resumes[state.resume_id] = state
            assert m._DEBUGGING_RUNS.get(waiting.run_id) is waiting
            state.in_flight = True
            async with kernel._pending_debugging_intake_resume_lock:
                await kernel._expire_pending_debugging_intake_resumes_locked(now=21601)
            assert m._DEBUGGING_RUNS.get(waiting.run_id) is waiting
            state.in_flight = False
            async with kernel._pending_debugging_intake_resume_lock:
                await kernel._expire_pending_debugging_intake_resumes_locked(now=21601)
            assert waiting.run_id not in m._DEBUGGING_RUNS
            assert m._DEBUGGING_RUNS.get(resumable.run_id) is resumable
            assert m._DEBUGGING_RUNS.get(unrelated.run_id) is unrelated

    asyncio.run(scenario())


if __name__ == "__main__":
    test_debugging_pass_commit_survives_durability_failure()
    test_debugging_pass_cognition_remains_pending_after_persistent_durability_failure()
    test_debugging_final_report_survives_durability_failure()
    test_completed_debugging_index_exact_identity_and_failure_recovery()
    test_debugging_registry_retires_only_unowned_runs()
    print("DEBUGGING_DURABILITY_REGRESSION: PASS")
