from pathlib import Path

kernel = Path("jack_kernel.py")
text = kernel.read_text(encoding="utf-8")
old = '''def _config_to_env(cfg: Dict[str, Any]) -> Dict[str, str]:\n    env = os.environ.copy()\n    values = {\n'''
new = '''def _config_to_env(cfg: Dict[str, Any]) -> Dict[str, str]:\n    env = os.environ.copy()\n    # A stale parent-process value from an older Jack launcher must not leak into\n    # the server child. The legacy secondary-prompt channel is retired.\n    env.pop("JACK_SECONDARY_SYSTEM_PROMPT_FILE", None)\n    values = {\n'''
if text.count(old) != 1:
    raise SystemExit(f"expected one _config_to_env anchor, found {text.count(old)}")
text = text.replace(old, new, 1)
kernel.write_text(text, encoding="utf-8", newline="\n")

Path("tests/test_secondary_prompt_launcher_retirement.py").write_text(r'''from __future__ import annotations

import copy
from pathlib import Path

import jack_kernel as jk


OBSOLETE_ENV = "JACK_SECONDARY_SYSTEM_PROMPT_FILE"


def _isolated_config(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    current = tmp_path / "current"
    legacy = tmp_path / "legacy"
    monkeypatch.setattr(jk, "_config_dir", lambda: current)
    monkeypatch.setattr(jk, "_legacy_config_dir", lambda: legacy)
    return current, legacy


def test_launcher_source_has_no_obsolete_secondary_prompt_surface() -> None:
    source = Path(jk.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "Persistent secondary system prompt",
        "def _edit_secondary_prompt",
        "def _load_cli_secondary_prompt",
        "def _save_cli_secondary_prompt",
        "def configured_secondary_system_prompt",
        "def extract_secondary_system_prompt",
    ):
        assert forbidden not in source


def test_config_to_env_strips_stale_secondary_prompt_parent_env(monkeypatch) -> None:
    monkeypatch.setenv(OBSOLETE_ENV, "C:/stale/secondary_system_prompt.txt")
    cfg = copy.deepcopy(jk.CLI_DEFAULTS)
    env = jk._config_to_env(cfg)
    assert OBSOLETE_ENV not in env


def test_save_cli_config_does_not_create_secondary_prompt_file(monkeypatch, tmp_path) -> None:
    _isolated_config(monkeypatch, tmp_path)
    cfg = copy.deepcopy(jk.CLI_DEFAULTS)
    jk._save_cli_config(cfg)
    config_path, prompt_path = jk._config_paths()
    assert config_path.is_file()
    assert not prompt_path.exists()


def test_existing_legacy_prompt_is_preserved_but_ignored(monkeypatch, tmp_path, capsys) -> None:
    current, _ = _isolated_config(monkeypatch, tmp_path)
    current.mkdir(parents=True)
    _, prompt_path = jk._config_paths()
    original = b"legacy prompt must remain byte-identical\r\nsecond line\r\n"
    prompt_path.write_bytes(original)

    cfg = jk._load_cli_config()
    output = capsys.readouterr().out

    assert cfg["reasoning_level"] == "x-high"
    assert prompt_path.read_bytes() == original
    assert "preserved but ignored" in output
    assert "Pi/the caller" in output


def test_launcher_menu_has_no_secondary_prompt_control(capsys) -> None:
    jk._print_main_menu_options()
    output = capsys.readouterr().out
    assert "secondary system prompt" not in output.casefold()
    assert "  Model Selection" in output
    assert "  Reasoning level" in output
    assert "  Reset Jack defaults" in output


def test_status_reports_caller_contract_ownership(monkeypatch, capsys) -> None:
    monkeypatch.setattr(jk, "_backend_model_status", lambda cfg: "TEST MODEL")
    jk._print_header(copy.deepcopy(jk.CLI_DEFAULTS), clear_screen=False, include_brand=False)
    output = capsys.readouterr().out
    assert "Caller system contract" in output
    assert "AGENT / PI OWNED" in output
    assert "Secondary prompt" not in output


def test_base_caller_contract_accepts_only_leading_system() -> None:
    assert jk.merged_secondary_system_prompt([
        {"role": "system", "content": "You are Alice."},
        {"role": "developer", "content": "internal scaffolding"},
        {"role": "user", "content": "Build."},
    ]) == "You are Alice."

    assert jk.merged_secondary_system_prompt([
        {"role": "developer", "content": "do not promote"},
        {"role": "system", "content": "late system"},
        {"role": "user", "content": "Build."},
    ]) == ""


def test_config_paths_retains_legacy_location_only_for_migration_detection(monkeypatch, tmp_path) -> None:
    current, _ = _isolated_config(monkeypatch, tmp_path)
    config_path, prompt_path = jk._config_paths()
    assert config_path == current / "config.json"
    assert prompt_path == current / "secondary_system_prompt.txt"
    assert not prompt_path.exists()
''', encoding="utf-8", newline="\n")

print("final secondary-prompt cleanup and regressions prepared")
