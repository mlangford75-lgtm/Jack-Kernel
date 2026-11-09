"""Universal Python capability selection in Deep Reasoning.

Deep Reasoning should use normal caller-authorized command tools rather than a
restricted numerical interpreter. No new executor authority is granted.
"""
from jack_deep_reasoning_kernel import _requires_antithesis_python_verification

def tool(name):
    return {"type":"function","function":{"name":name,"parameters":{"type":"object"}}}


def test_quantitative_request_can_verify_using_normal_shell_tool():
    for name in ("bash","powershell","pwsh"):
        assert _requires_antithesis_python_verification(
            "Calculate 10 percent of 1 million examples", [tool(name)]
        )


def test_caller_does_not_gain_tools_from_numeric_request():
    assert not _requires_antithesis_python_verification(
        "Calculate the probability", []
    )
    assert not _requires_antithesis_python_verification(
        "Calculate the probability", [tool("read"),tool("write")]
    )


def test_nonquantitative_request_not_forced_to_use_shell():
    assert not _requires_antithesis_python_verification(
        "Design a fictional character", [tool("bash")]
    )


def test_existing_external_python_tool_remains_supported():
    assert _requires_antithesis_python_verification(
        "Compute probability", [tool("python_repl")]
    )


def test_kernel_does_not_narrow_authorized_antithesis_tools_to_numeric_helper():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "jack_deep_reasoning_kernel.py").read_text(encoding="utf-8")
    assert "offered = python" not in src
    assert 'stage == "antithesis" and choice == "required"' not in src
