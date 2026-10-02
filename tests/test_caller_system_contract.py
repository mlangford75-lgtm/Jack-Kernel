from __future__ import annotations

import asyncio
import copy
import importlib.util
import os
import sys
import uuid
from pathlib import Path

import pytest

import jack_responses_compat as compat


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "jack_kernel.py"
CALLER = "You are Alice, a world-building Witch. Preserve this exact caller contract."
DELIMITER = "\n\n--- JACK RUNTIME STAGE CONTRACT ---\n"


def load_kernel(mode: str):
    os.environ["JACK_REASONING_LEVEL"] = mode
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "off"
    os.environ["JACK_BACKEND_MODEL"] = "test-model"
    os.environ["JACK_BACKEND_PROFILE"] = "lmstudio"
    name = f"jack_caller_contract_{mode.replace('-', '_')}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("mode", ["off", "medium", "x-high", "agentic", "deep-research", "code-debugging"])
def test_caller_contract_precedes_unchanged_stage_contract_in_every_mode(mode, monkeypatch):
    monkeypatch.delenv("JACK_SECONDARY_SYSTEM_PROMPT_FILE", raising=False)
    mod = load_kernel(mode)
    original = mod.build_stage_system_prompt
    expected_stage_contracts = {
        key: original("", profile, [])
        for key, profile in mod.STAGES.items()
    }

    compat.register(mod)

    assert mod.merged_secondary_system_prompt([
        {"role": "system", "content": CALLER},
        {"role": "user", "content": "Build a kingdom."},
    ]) == CALLER

    for key, profile in mod.STAGES.items():
        expected = expected_stage_contracts[key]
        actual = mod.build_stage_system_prompt(CALLER, profile, [])
        if expected:
            assert actual == CALLER + DELIMITER + expected
        else:
            assert actual == CALLER


def test_only_leading_system_message_becomes_caller_contract(monkeypatch):
    monkeypatch.delenv("JACK_SECONDARY_SYSTEM_PROMPT_FILE", raising=False)
    mod = load_kernel("off")
    compat.register(mod)

    assert mod.merged_secondary_system_prompt([
        {"role": "system", "content": CALLER},
        {"role": "developer", "content": "INTERNAL DEVELOPER SCAFFOLDING"},
        {"role": "system", "content": "LATE SYSTEM TEXT"},
        {"role": "user", "content": "hello"},
    ]) == CALLER

    # Jack does not promote arbitrary developer material or a non-leading system
    # message into the persistent caller cognitive contract.
    assert mod.merged_secondary_system_prompt([
        {"role": "developer", "content": "INTERNAL DEVELOPER SCAFFOLDING"},
        {"role": "system", "content": CALLER},
        {"role": "user", "content": "hello"},
    ]) == ""


def test_obsolete_secondary_prompt_file_no_longer_affects_model_context(tmp_path, monkeypatch):
    prompt_file = tmp_path / "secondary.txt"
    prompt_file.write_text("You are Bob. This must not reach the model.", encoding="utf-8")
    monkeypatch.setenv("JACK_SECONDARY_SYSTEM_PROMPT_FILE", str(prompt_file))
    mod = load_kernel("off")
    compat.register(mod)

    assert mod.merged_secondary_system_prompt([
        {"role": "system", "content": CALLER},
        {"role": "user", "content": "hello"},
    ]) == CALLER
    assert mod.merged_secondary_system_prompt([
        {"role": "user", "content": "hello"},
    ]) == ""


class _Response:
    status_code = 200
    text = ""

    @staticmethod
    def json():
        return {
            "choices": [{
                "message": {"role": "assistant", "content": "ok"},
                "finish_reason": "stop",
            }],
            "usage": {},
        }

    async def aclose(self):
        return None


class _CaptureClient:
    def __init__(self):
        self.payloads = []

    async def post(self, *args, **kwargs):
        self.payloads.append(copy.deepcopy(kwargs["json"]))
        return _Response()

    async def aclose(self):
        return None


def test_actual_backend_payload_begins_with_stable_caller_prefix(monkeypatch):
    monkeypatch.delenv("JACK_SECONDARY_SYSTEM_PROMPT_FILE", raising=False)
    mod = load_kernel("agentic")
    original = mod.build_stage_system_prompt
    compat.register(mod)

    backend = mod.OpenAICompatibleBackend(mod.CFG)
    client = _CaptureClient()
    backend._client = client
    backend._resolved_model = "test-model"
    backend._model_metadata_checked = True

    profile = mod.STAGES["extended_initial"]
    original_stage = original("", profile, [{"role": "user", "content": "x"}])

    asyncio.run(backend.chat(
        messages=[{"role": "user", "content": "x"}],
        secondary_system=CALLER,
        profile=profile,
    ))

    assert len(client.payloads) == 1
    outbound = client.payloads[0]["messages"]
    assert outbound[0]["role"] == "system"
    expected_system = CALLER if not original_stage else CALLER + DELIMITER + original_stage
    assert outbound[0]["content"] == expected_system
    assert outbound[0]["content"].startswith(CALLER)
    assert outbound[1] == {"role": "user", "content": "x"}


def test_caller_contract_does_not_change_kernel_authority_surfaces(monkeypatch):
    monkeypatch.delenv("JACK_SECONDARY_SYSTEM_PROMPT_FILE", raising=False)
    mod = load_kernel("agentic")

    before = {
        key: (
            profile.name,
            profile.enable_thinking,
            profile.reasoning_effort,
            profile.allow_tools,
            profile.temperature,
            profile.max_tokens,
        )
        for key, profile in mod.STAGES.items()
    }
    compat.register(mod)
    after = {
        key: (
            profile.name,
            profile.enable_thinking,
            profile.reasoning_effort,
            profile.allow_tools,
            profile.temperature,
            profile.max_tokens,
        )
        for key, profile in mod.STAGES.items()
    }

    assert after == before
    assert mod.SecurityOutcome.ALLOW.value == "ALLOW"
    assert mod.SecurityOutcome.DENY_AND_CONTINUE.value == "DENY_AND_CONTINUE"
    assert mod.SecurityOutcome.REQUIRE_USER_DECISION.value == "REQUIRE_USER_DECISION"
    assert mod.SecurityOutcome.HARD_INTERRUPT.value == "HARD_INTERRUPT"
