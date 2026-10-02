from __future__ import annotations

import inspect
import os
from pathlib import Path
import subprocess
import sys

import jack_authority_ledger as ledger
import jack_consequence_gate as gate
import jack_kernel as kernel


def test_kernel_owned_convergence_orders_evidence_before_gate_and_responses_after_gate():
    source = inspect.getsource(kernel._install_bundled_runtime_extensions)
    assert source.index("jack_evidence_guard.install") < source.index("jack_consequence_gate.install(module)")
    assert source.index("jack_consequence_gate.install(module)") < source.index("jack_responses_compat.register(module)")


def test_phase6_is_installed_only_from_kernel_invoked_phase5_path():
    source = inspect.getsource(gate.install)
    assert "authority_ledger.install(jk)" in source
    assert "_install_bundled_runtime_extensions" in source
    assert "import jack_kernel" not in inspect.getsource(ledger.install)


def test_phase6_event_vocabulary_is_exactly_the_accepted_first_scope():
    assert {item.value for item in ledger.LedgerEventType} == {
        "REPRESENTED_PATH_DECISION",
        "EXECUTOR_IDENTITY_DECISION",
        "CANARY_MATCH",
        "RESERVED_EVIDENCE_NAMESPACE_BLOCKED",
    }


def test_repeated_kernel_extension_install_preserves_one_phase6_instance_in_isolated_process(tmp_path):
    # The real bundled installer intentionally mutates process-global security
    # bindings. Exercise that contract in a child process so this idempotence
    # test cannot contaminate unrelated regression tests in the parent pytest run.
    code = r'''
import jack_kernel as kernel

kernel._install_bundled_runtime_extensions()
first = kernel._JACK_AUTHORITY_LEDGER
first_id = first.ledger_instance_id
first_sequence = first.active_head.sequence
run_wrapper = kernel.KERNEL.run
stream_wrapper = kernel.KERNEL.stream

kernel._install_bundled_runtime_extensions()

assert kernel._JACK_AUTHORITY_LEDGER is first
assert kernel._JACK_AUTHORITY_LEDGER.ledger_instance_id == first_id
assert kernel._JACK_AUTHORITY_LEDGER.active_head.sequence == first_sequence
assert kernel.KERNEL.run is run_wrapper
assert kernel.KERNEL.stream is stream_wrapper
first.close()
'''
    env = dict(os.environ)
    env.update(
        {
            "JACK_AUTHORITY_LEDGER_DIR": str(tmp_path / "ledger"),
            "JACK_FORENSIC_ARCHIVE_MODE": "off",
            "JACK_BACKEND_MODEL": "test-model",
            "JACK_BACKEND_PROFILE": "lmstudio",
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
