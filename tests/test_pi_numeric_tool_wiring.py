"""The Pi extension must not register a restricted pseudo-Python interpreter.

Real Python is available through the caller's existing authorized command tools;
Jack only normalizes reported outcomes and validates command-tool admission.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "Pi" / "jack-kernel.ts"
INSTALLER = ROOT / "Pi" / "install-jack-kernel-extension.ps1"


def test_pi_extension_does_not_replace_python_with_restricted_interpreter():
    source = EXTENSION.read_text(encoding="utf-8")
    assert 'name: "python_repl"' not in source
    assert "jack-numeric-verifier.py" not in source
    assert 'pi.on("tool_execution_end"' in source
    assert 'pi.on("before_provider_request"' in source
    assert 'pi.on("tool_call"' in source
    assert 'new Map([' in source  # command tool dialects remain wired
    assert '["bash", "bash"]' in source
    assert '["powershell", "powershell"]' in source


def test_installer_only_installs_jack_extension():
    source = INSTALLER.read_text(encoding="utf-8")
    assert "jack-kernel.ts" in source
    assert "jack-numeric-verifier.py" not in source
    assert "Copy-Item -LiteralPath $source -Destination $dest -Force" in source
