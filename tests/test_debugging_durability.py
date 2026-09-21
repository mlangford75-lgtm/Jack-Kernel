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

        # The authoritative Pass 0..5 report must remain byte-for-byte unchanged.
        assert run.report_path.read_text(encoding="utf-8") == original_report

        # A retry after the transient failure must succeed exactly once.
        final_report = m._debugging_commit_final_report(
            run,
            response("Final repair specification."),
        )

        assert final_report == "Final repair specification."
        assert run.final_report_committed is True

        durable = run.report_path.read_text(encoding="utf-8")
        assert durable.startswith(original_report)
        assert durable.count(m._DEBUGGING_FINAL_REPORT_HEADING) == 1
        assert durable.count("Final repair specification.") == 1


if __name__ == "__main__":
    test_debugging_pass_commit_survives_durability_failure()
    test_debugging_final_report_survives_durability_failure()
    print("DEBUGGING_DURABILITY_REGRESSION: PASS")
