"""Jack, not Pi, owns Agentic file mutation verification guidance."""
import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("profile", ["thorough", "balanced", "flash"])
def test_jack_stage1_requires_write_edit_readback_in_all_agentic_profiles(
    monkeypatch, tmp_path, profile
):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_file_verification_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)

    stage1 = k.STAGES["extended_initial"]
    prompt = k.build_stage_system_prompt("Caller system", stage1)
    assert "Whenever you use a write or edit tool" in prompt
    assert "read back the saved file" in prompt
    assert "Never claim a file was created or modified" in prompt

    # Stage 2 remains independently isolated; verification is not its job.
    stage2 = k.STAGES["extended_reflection"]
    retrospective = k.build_stage_system_prompt("Caller system", stage2)
    assert "Whenever you use a write or edit tool" not in retrospective
    assert "Begin with a brief description of the current task" in retrospective
    assert stage2.allow_tools is False

    # Flash still receives the rule despite disabling native thinking.
    if profile == "flash":
        assert stage1.thinking is False


def test_pi_extension_has_no_jack_file_verification_prompt_injection():
    source = (ROOT / "Pi" / "jack-kernel.ts").read_text(encoding="utf-8")
    assert "FILE_MUTATION_VERIFICATION_GUIDELINE" not in source
    assert "addFileMutationVerificationGuideline" not in source
