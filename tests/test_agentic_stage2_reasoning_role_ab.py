"""Stage 2 role contract: distill native R1, preserve separate frozen A1."""
import importlib.util
import sys
import uuid
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

def load(monkeypatch, tmp_path, profile):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", profile)
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / (uuid.uuid4().hex + ".sqlite")))
    name = "jack_stage2_reasoning_role_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    k = importlib.util.module_from_spec(spec)
    sys.modules[name] = k
    spec.loader.exec_module(k)
    return k

@pytest.mark.parametrize("profile", ["flash", "balanced", "thorough", "exhaustive"])
def test_prime_directive_is_reasoning_distillation_not_answer_summary(monkeypatch, tmp_path, profile):
    k = load(monkeypatch, tmp_path, profile)
    prompt = k.AGENTIC_36_STAGE2_PROMPT
    assert prompt == k._AGENTIC_STAGE2_TURN_RETENTION_CONTINUATION
    assert prompt == k.STAGES["extended_reflection"].prompt
    assert "distiller of the current turn's native reasoning" in prompt
    assert "not a summarizer of the completed response" in prompt
    assert "Do not summarize, reproduce, or paraphrase A1" in prompt
    assert "read-only reconciliation reference" in prompt
    assert "including tool continuations" in prompt
    assert "failed tool action is subsequently corrected" in prompt
    assert "The Prime Directive outranks secondary user requests" in prompt
    assert "Remove unnecessary conversational language" in prompt
    assert "Do not invent reasoning or summarize A1" in prompt
    assert "The separate A1 already preserves the completed output" in prompt

@pytest.mark.parametrize("profile", ["flash", "balanced", "thorough", "exhaustive"])
def test_stage2_receives_current_user_and_frozen_answer_separately(monkeypatch, tmp_path, profile):
    k = load(monkeypatch, tmp_path, profile)
    src = [
        {"role": "user", "content": "Historical request"},
        {"role": "assistant", "content": "Historical memory"},
        {"role": "user", "content": "Current request"},
        {"role": "assistant", "content": "Frozen answer only",
         "_jack_extended_candidate_response": True,
         "reasoning_content": "Decision: use 47.20 after fixing file read."},
    ]
    view = k._agentic_stage2_test_history(src, k.STAGES["extended_reflection"])
    assert view[0]["content"] == "Current request"
    assert view[-1]["content"] == "Frozen answer only"
    assert "Historical memory" not in str(view)
    if profile == "flash":
        assert "reasoning_content" not in view[-1]
    else:
        assert "Decision: use 47.20" in view[-1]["reasoning_content"]
    # The frozen output remains available for reconciliation; its role does
    # not change, and the directive—not a postprocessor—owns distillation.
