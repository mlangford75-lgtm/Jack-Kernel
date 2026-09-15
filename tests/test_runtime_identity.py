import asyncio
import hashlib
import importlib.util
import os
import sys
import uuid
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "jack_kernel.py"


def load():
    os.environ["JACK_REASONING_LEVEL"] = "x-high"
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
