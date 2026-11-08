"""Static safeguards for the opt-in, provider-scoped Pi numeric verifier wiring."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "Pi" / "jack-kernel.ts"
INSTALLER = ROOT / "Pi" / "install-jack-kernel-extension.ps1"
HELPER = ROOT / "Pi" / "jack-numeric-verifier.py"


def test_numeric_tool_declared_and_backed_by_bounded_python_execution():
    source = EXTENSION.read_text(encoding="utf-8")
    assert 'name: "python_repl"' in source
    assert 'typeof pi.registerTool !== "function"' in source
    assert 'String(ctx?.model?.provider || "") !== PROVIDER_NAME' in source
    assert '"jack-numeric-verifier.py"' in source
    assert '["-I", "-S", NUMERIC_VERIFIER_PATH, source]' in source
    assert 'timeout: 5000, maxBuffer: 65536' in source
    assert 'await registerNumericVerifier()' in source


def test_installer_copies_exact_numeric_verifier_with_extension():
    source = INSTALLER.read_text(encoding="utf-8")
    assert "jack-numeric-verifier.py" in source
    assert "Copy-Item -LiteralPath $numericSource -Destination $numericDest -Force" in source
    assert HELPER.is_file()
