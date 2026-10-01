from __future__ import annotations

import inspect
from enum import Enum
from types import SimpleNamespace

import pytest

import jack_consequence_gate as gate
import jack_kernel as kernel
import jack_responses_compat as responses_compat


def test_kernel_installer_explicitly_owns_phase5_installation():
    source = inspect.getsource(kernel._install_bundled_runtime_extensions)
    assert "import jack_consequence_gate" in source
    assert "jack_consequence_gate.install(module)" in source
    assert source.index("jack_consequence_gate.install(module)") < source.index("jack_responses_compat.register(module)")


def test_responses_compatibility_is_not_security_root():
    source = inspect.getsource(responses_compat.register)
    assert "jack_consequence_gate" not in source
    assert "Consequence Gate" not in source


def test_gate_does_not_reconstruct_kernel_identity():
    source = inspect.getsource(gate)
    assert "_active_kernel_module" not in source
    assert 'sys.modules["jack_kernel"]' not in source
    assert "import jack_kernel" not in source


def test_install_rejects_incompatible_outcome_vocabulary(monkeypatch):
    class OtherOutcome(str, Enum):
        ALLOW = "ALLOW"
        HARD_INTERRUPT = "HARD_INTERRUPT"
    fake = SimpleNamespace(SecurityOutcome=OtherOutcome)
    monkeypatch.setattr(gate, "_install_represented_path_gate", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="SecurityOutcome vocabulary"):
        gate.install(fake)


def test_isolated_equivalent_kernel_receives_its_own_enum(monkeypatch):
    class OtherOutcome(str, Enum):
        ALLOW = "ALLOW"
        DENY_AND_CONTINUE = "DENY_AND_CONTINUE"
        REQUIRE_USER_DECISION = "REQUIRE_USER_DECISION"
        HARD_INTERRUPT = "HARD_INTERRUPT"
    fake = SimpleNamespace(SecurityOutcome=OtherOutcome)
    monkeypatch.setattr(gate, "_install_represented_path_gate", lambda *a, **k: None)
    gate.install(fake)
    d = fake.evaluate_consequence((gate.StageToolAuthorityFact(False),))
    assert d.outcome is OtherOutcome.DENY_AND_CONTINUE
