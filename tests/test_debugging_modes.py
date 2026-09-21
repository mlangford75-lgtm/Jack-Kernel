import importlib.util
import os
import sys
import uuid
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "jack_kernel.py"


def load(mode: str):
    os.environ["JACK_REASONING_LEVEL"] = mode
    os.environ["JACK_FORENSIC_ARCHIVE_MODE"] = "off"
    os.environ["JACK_BACKEND_MODEL"] = "test-model"
    name = f"jack_test_debugging_{mode.replace('-', '_')}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def stage_signature(profile):
    return {
        "name": profile.name,
        "prompt": profile.prompt,
        "thinking": profile.thinking,
        "allow_tools": profile.allow_tools,
        "temperature": profile.temperature,
        "presence_penalty": profile.presence_penalty,
        "force_preserve_thinking": profile.force_preserve_thinking,
        "max_tokens": profile.max_tokens,
    }


def normalized_control_payload(payload):
    out = dict(payload)
    if "reasoning_effort" in out:
        out["reasoning_effort"] = "EFFORT"
    if isinstance(out.get("chat_template_kwargs"), dict):
        out["chat_template_kwargs"] = dict(out["chat_template_kwargs"])
        if "reasoning_effort" in out["chat_template_kwargs"]:
            out["chat_template_kwargs"]["reasoning_effort"] = "EFFORT"
    return out


def main():
    standard = load("code-debugging")
    deep = load("code-debugging-deep")

    assert standard.PUBLIC_VERSION == "v.0.1.1"
    assert standard.CONFIG_SCHEMA_VERSION == 1
    assert standard.CFG.port == 8001
    assert standard.CFG.agent_base_url == "http://127.0.0.1:8001/v1"
    assert standard.BACKEND_PRESETS["custom"]["base_url"] == "http://127.0.0.1:8000/v1"
    assert standard.CODE_DEBUGGING_MODE and deep.CODE_DEBUGGING_MODE
    assert standard.ACTIVE_REASONING_PROFILE["label"] == "Code Debugging"
    assert deep.ACTIVE_REASONING_PROFILE["label"] == "Code Debugging (Deep)"
    assert standard.DEBUGGING_REASONING_EFFORT == "medium"
    assert deep.DEBUGGING_REASONING_EFFORT == "xhigh"

    stage_keys = ["debug_intake"] + [f"debug_pass_{n}" for n in range(1, 6)] + ["debug_summary"]
    expected_temps = [0.70, 1.00, 0.80, 0.70, 0.60, 0.50, 1.00]
    ka = standard.OpenAICompatibleBackend(standard.CFG)
    kb = deep.OpenAICompatibleBackend(deep.CFG)

    for key, expected_temp in zip(stage_keys, expected_temps):
        a = standard.STAGES[key]
        b = deep.STAGES[key]
        assert a.reasoning_effort == "medium", (key, a.reasoning_effort)
        assert b.reasoning_effort == "xhigh", (key, b.reasoning_effort)
        assert stage_signature(a) == stage_signature(b), key
        assert a.temperature == expected_temp

        # The actual LM Studio control payloads must differ only in reasoning effort.
        pa, pb = {}, {}
        ka._apply_qwen_controls(pa, a)
        kb._apply_qwen_controls(pb, b)
        assert pa["reasoning_effort"] == "medium"
        assert pb["reasoning_effort"] == "xhigh"
        assert pa["chat_template_kwargs"]["reasoning_effort"] == "medium"
        assert pb["chat_template_kwargs"]["reasoning_effort"] == "xhigh"
        assert normalized_control_payload(pa) == normalized_control_payload(pb), key

    # Registry extraction accepts bold inline semantic fields and excludes repair guidance.
    pass2 = r'''
# Pass 2 Handoff — Single-Problem Forensic Audit

**Review Category:** Functional correctness and runtime behavior (required feature/output entirely absent)

**Finding ID:** JCK-ANALOG-002

**Primary Finding:** The required "current system date" display below the clock is completely missing — no element, no formatting logic, no update hook exists anywhere in the page.

**Severity:** MEDIUM

**Status:** CONFIRMED

**Exact Location:** `C:\Projects\analog-clock\index.html`

**Evidence:** Full file read proves there is no date node and no date formatting logic.

**Repair Direction:** Add a date element below the clock.

**Out-of-Scope / Residual Observations:** Luxury styling is absent.
'''
    record = standard._debugging_host_registry_record(2, pass2)
    assert "Finding ID: JCK-ANALOG-002" in record
    assert "Severity: MEDIUM" in record
    assert "Status: CONFIRMED" in record
    assert "current system date" in record
    assert "analog-clock\\index.html" in record
    assert "Luxury styling" not in record
    assert "Add a date element" not in record

    # Heading-form semantic fields remain extractable.
    heading_variant = r'''
## Review Category
State/lifecycle/concurrency
## Primary Finding
JCK-TEST-007 — A committed state transition is lost after timeout.
## Severity
HIGH
## Status
CONFIRMED
## Exact Location
src/runtime.py:120-150
## Evidence
- Deterministic timeout replay reproduces the state loss.
## Repair Direction
Change the commit sequence.
'''
    record2 = standard._debugging_host_registry_record(4, heading_variant)
    assert "Finding ID: JCK-TEST-007" in record2
    assert "Severity: HIGH" in record2
    assert "Status: CONFIRMED" in record2
    assert "committed state transition" in record2
    assert "Change the commit sequence" not in record2

    # Primary-Finding heading variants remain supported.
    older_heading_variant = r'''
## Primary Finding — ID `AC-P1-001`
**The hand geometry is wrong and the dial cannot display time correctly.**
## Severity
HIGH
## Status
CONFIRMED
## Exact Location
index.html lines 30-39
## Required Correction
Rewrite the hand geometry.
'''
    record3 = standard._debugging_host_registry_record(1, older_heading_variant)
    assert "Finding ID: AC-P1-001" in record3
    assert "hand geometry is wrong" in record3
    assert "Rewrite the hand geometry" not in record3


    # Exact live-run shape: semantic identity is under Observed Behavior.
    live_pass3_variant = r"""
# Pass 3 — Code Debugging Handoff

## Primary Finding
**Finding ID:** PASS3-001

## Review Category
Functional correctness and runtime behavior

## Severity
MEDIUM

## Status
CONFIRMED

## Exact Location
File: app.py
Function: mean(values)

## Observed Behavior
Calling mean([]) with an empty collection raises ZeroDivisionError: division by zero.

## Expected Behavior
mean([]) should return 0.0, not crash.

## Repair Direction
Add an empty-input guard.
"""
    record4 = standard._debugging_host_registry_record(3, live_pass3_variant)
    assert "Finding ID: PASS3-001" in record4
    assert "Severity: MEDIUM" in record4
    assert "Status: CONFIRMED" in record4
    assert "mean([])" in record4
    assert "ZeroDivisionError" in record4
    assert "Add an empty-input guard" not in record4

    print("Jack Kernel debugging mode, endpoint, brand, and registry tests: PASS")


if __name__ == "__main__":
    main()
