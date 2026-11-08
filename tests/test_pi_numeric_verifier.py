"""Contract tests for the restricted Pi python_repl numerical executor."""
from pathlib import Path
import subprocess
import sys

VERIFIER = Path(__file__).resolve().parents[1] / "Pi" / "jack-numeric-verifier.py"


def run(code):
    return subprocess.run(
        [sys.executable, "-I", "-S", str(VERIFIER), code],
        capture_output=True,
        text=True,
        timeout=8,
    )


def test_noisy_labels_rate_after_random_deletion():
    result = run(
        "total=1000000\nwrong=100000\nremoved=total*0.1\n"
        "remaining_wrong=wrong-removed*0.1\n"
        "print(remaining_wrong/(total-removed)*100)"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "10.0"


def test_probability_and_combinatorics():
    result = run("print(comb(10,2))\nprint(1/3)")
    assert result.returncode == 0
    assert result.stdout.splitlines()[0] == "45"
    assert result.stdout.splitlines()[1].startswith("0.333")


def test_rejects_imports_and_command_execution():
    for code in (
        "import os",
        "__import__('os').system('echo forbidden')",
        "open('secrets.txt').read()",
        "print((1).__class__)",
        "[x for x in range(100)]",
        "while True: pass",
    ):
        result = run(code)
        assert result.returncode == 2, (code, result.stdout)
        assert "VERIFICATION_ERROR:" in result.stderr


def test_rejects_resource_abuse():
    for code in ("2**1000000", "factorial(1000)", "print('not a number')"):
        result = run(code)
        assert result.returncode == 2
        assert "VERIFICATION_ERROR:" in result.stderr
