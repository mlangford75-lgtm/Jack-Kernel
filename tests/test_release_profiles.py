import importlib.util
import os
import sys
import uuid
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "jack_kernel.py"
PI_EXTENSION = Path(__file__).resolve().parents[1] / "Pi" / "jack-kernel.ts"


def load(mode: str):
    os.environ["JACK_REASONING_LEVEL"] = mode
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "off"
    os.environ["JACK_BACKEND_MODEL"] = "test-model"
    os.environ["JACK_BACKEND_PROFILE"] = "lmstudio"
    name = f"jack_release_profile_{mode.replace('-', '_')}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def qwen_payload(mod, stage_key: str):
    backend = mod.OpenAICompatibleBackend(mod.CFG)
    payload = {}
    backend._apply_qwen_controls(payload, mod.STAGES[stage_key])
    return payload


def main():
    off = load("off")
    medium = load("medium")
    xhigh = load("x-high")
    deep = load("ultra")

    assert off.REASONING_PROFILES["low"]["disabled"] is True

    assert off.STAGES["thesis"].thinking is False
    assert off.STAGES["thesis"].reasoning_effort is None
    p = qwen_payload(off, "thesis")
    assert p["reasoning_effort"] == "none"
    assert p["chat_template_kwargs"]["enable_thinking"] is False
    assert p["chat_template_kwargs"]["preserve_thinking"] is False

    assert medium.STAGES["thesis"].thinking is True
    assert medium.STAGES["thesis"].reasoning_effort == "medium"
    p = qwen_payload(medium, "thesis")
    assert p["reasoning_effort"] == "medium"
    assert p["chat_template_kwargs"]["enable_thinking"] is True

    assert xhigh.STAGES["thesis"].thinking is True
    assert xhigh.STAGES["thesis"].reasoning_effort == "xhigh"
    p = qwen_payload(xhigh, "thesis")
    assert p["reasoning_effort"] == "xhigh"
    assert p["chat_template_kwargs"]["enable_thinking"] is True

    thesis = deep.STAGES["extended_initial"]
    anti = deep.STAGES["extended_reflection"]
    synth = deep.STAGES["extended_synthesis"]

    assert thesis.thinking is True and thesis.reasoning_effort == "xhigh"
    assert thesis.allow_tools is False and thesis.temperature == 0.85

    assert anti.thinking is True and anti.reasoning_effort == "medium"
    assert anti.allow_tools is False and anti.temperature == 0.70
    p = qwen_payload(deep, "extended_reflection")
    assert p["reasoning_effort"] == "medium"
    assert p["chat_template_kwargs"]["enable_thinking"] is True
    assert p["chat_template_kwargs"]["preserve_thinking"] is True

    assert synth.thinking is True and synth.reasoning_effort == "xhigh"
    assert synth.allow_tools is True and synth.temperature == 0.70

    pi_source = PI_EXTENSION.read_text(encoding="utf-8")
    assert "charCodeAt(0) === 0xfeff" in pi_source
    assert 'const DEFAULT_JACK_URL = "http://127.0.0.1:8001";' in pi_source

    kernel_source = SRC.read_text(encoding="utf-8")
    assert "Jack Kernel 2.x" not in kernel_source
    assert "Low is disabled in Jack Kernel v0.1.1" in kernel_source

    print("Jack Kernel release reasoning-profile and Pi BOM regression tests: PASS")


if __name__ == "__main__":
    main()
