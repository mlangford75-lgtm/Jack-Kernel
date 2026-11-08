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


def test_bounded_numeric_loops_and_if_support_majority_vote_check():
    result = run(
        "total=0\n"
        "for correct in range(4):\n"
        "    if correct >= 2:\n"
        "        total += comb(3,correct)*(0.9**correct)*(0.1**(3-correct))\n"
        "print(round(total,3))"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0.972"


def test_rejects_unbounded_or_nonnumeric_control_flow():
    for code in (
        "while True: pass",
        "for x in range(1000000):\n    print(x)",
        "for x in range(3):\n    import os",
        "for x in range(3):\n    print(open('secret'))",
        "if True:\n    print(1)",
        "for x in range(3):\n    print((1).__class__)",
    ):
        result = run(code)
        assert result.returncode == 2, (code, result.stdout)
        assert "VERIFICATION_ERROR:" in result.stderr


def test_rejects_numeric_work_that_exceeds_execution_budget():
    result = run("total=0\nfor x in range(1000):\n    for y in range(1000):\n        total += 1")
    assert result.returncode == 2
    assert "execution budget exceeded" in result.stderr


def test_large_but_bounded_numeric_check_under_ast_limit():
    # A modest, finite number of numeric statements is valid.
    result = run("n=0\n" + "n+=1\n"*100 + "print(n)")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "100"
