import asyncio
import hashlib
import importlib.util
import os
import sys
import uuid
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "jack_kernel.py"


def load(mode="x-high"):
    os.environ["JACK_REASONING_LEVEL"] = mode
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "off"
    os.environ["JACK_BACKEND_MODEL"] = "test-model"
    os.environ["JACK_BACKEND_PROFILE"] = "lmstudio"

    name = f"jack_runtime_identity_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_runtime_artifact_sha256_matches_loaded_source():
    mod = load()
    expected = hashlib.sha256(SRC.read_bytes()).hexdigest()

    assert mod.RUNTIME_ARTIFACT_SHA256 == expected


def test_root_exposes_runtime_artifact_sha256():
    mod = load()

    payload = asyncio.run(mod.root())

    assert payload["runtime_artifact_sha256"] == mod.RUNTIME_ARTIFACT_SHA256


def test_health_exposes_runtime_artifact_sha256():
    mod = load()

    async def fake_resolve_model():
        return "test-model"

    mod.BACKEND.resolve_model = fake_resolve_model

    class RequestStub:
        headers = {}

    payload = asyncio.run(mod.health(RequestStub()))

    assert payload["runtime_artifact_sha256"] == mod.RUNTIME_ARTIFACT_SHA256


def test_root_exposes_forensic_archive_mode():
    mod = load()

    payload = asyncio.run(mod.root())

    assert payload["forensic_archive_mode"] == mod.CFG.forensic_archive_mode


def test_health_exposes_forensic_archive_mode():
    mod = load()

    async def fake_resolve_model():
        return "test-model"

    mod.BACKEND.resolve_model = fake_resolve_model

    class RequestStub:
        headers = {}

    payload = asyncio.run(mod.health(RequestStub()))

    assert payload["forensic_archive_mode"] == mod.CFG.forensic_archive_mode


def test_consolidated_runtime_identity_contract():
    native = load("x-high")
    native_identity = asyncio.run(native.root())["runtime_identity"]

    assert native_identity["reasoning_profile"] == "x-high"
    assert native_identity["mode"] == "native"
    assert native_identity["flow"] == ["thesis"]
    assert native_identity["authoritative_stage"] == "thesis"
    assert native_identity["preserve_thinking"] == native.CFG.preserve_thinking
    assert native_identity["context_policy"] == {
        "context_length": native.BACKEND.context_length,
        "context_length_source": native.BACKEND.context_length_source,
    }
    assert native_identity["stage_controls"]["thesis"]["reasoning_effort"] == native.STAGES["thesis"].reasoning_effort
    assert native_identity["stage_controls"]["thesis"]["allow_tools"] == native.STAGES["thesis"].allow_tools
    assert native_identity["stage_controls"]["thesis"]["temperature"] == native.STAGES["thesis"].temperature
    assert native_identity["retention_policy"]

    async def fake_resolve_model():
        return "test-model"

    native.BACKEND.resolve_model = fake_resolve_model

    class RequestStub:
        headers = {}

    health_identity = asyncio.run(native.health(RequestStub()))["runtime_identity"]
    assert health_identity == native_identity

    deep = load("deep-research")
    deep_identity = asyncio.run(deep.root())["runtime_identity"]
    assert deep_identity["reasoning_profile"] == "deep-research"
    assert deep_identity["mode"] == "deep-research"
    assert deep_identity["flow"] == [
        "extended_initial",
        "extended_reflection",
        "extended_synthesis",
    ]
    assert deep_identity["authoritative_stage"] == "extended_synthesis"
    assert deep_identity["stage_controls"]["extended_initial"]["allow_tools"] is False
    assert deep_identity["stage_controls"]["extended_reflection"]["allow_tools"] is False
    assert deep_identity["stage_controls"]["extended_synthesis"]["allow_tools"] is True

    agentic = load("agentic")
    agentic_identity = asyncio.run(agentic.root())["runtime_identity"]
    assert agentic_identity["reasoning_profile"] == "agentic"
    assert agentic_identity["mode"] == "agentic"
    assert agentic_identity["flow"] == [
        "extended_initial",
        "extended_reflection",
    ]
    assert agentic_identity["authoritative_stage"] == "extended_initial"
    assert agentic_identity["stage_controls"]["extended_initial"]["allow_tools"] is True
    assert agentic_identity["stage_controls"]["extended_reflection"]["allow_tools"] is False

    debugging = load("code-debugging")
    debugging_identity = asyncio.run(debugging.root())["runtime_identity"]
    debugging_flow = (
        ["debug_intake"]
        + [
            debugging._debugging_stage_key(i)
            for i in range(1, debugging.DEBUGGING_PASS_COUNT + 1)
        ]
        + ["debug_summary"]
    )
    assert debugging_identity["reasoning_profile"] == "code-debugging"
    assert debugging_identity["mode"] == "code-debugging"
    assert debugging_identity["flow"] == debugging_flow
    assert debugging_identity["authoritative_stage"] == "debug_summary"
    assert debugging_identity["stage_controls"]["debug_intake"]["allow_tools"] is False
    assert debugging_identity["stage_controls"]["debug_summary"]["allow_tools"] is False
    assert all(
        debugging_identity["stage_controls"][
            debugging._debugging_stage_key(i)
        ]["allow_tools"]
        for i in range(1, debugging.DEBUGGING_PASS_COUNT + 1)
    )
