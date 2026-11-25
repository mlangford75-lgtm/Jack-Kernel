"""Local-only Security Center configuration; no model required."""
import copy
import json
import pytest
import jack_kernel as jk

@pytest.fixture
def cfg(monkeypatch, tmp_path):
    monkeypatch.delenv("JACK_PATH_POLICY_JSON", raising=False)
    monkeypatch.delenv("JACK_CANARY_POLICY_JSON", raising=False)
    monkeypatch.setattr(jk, "_config_paths", lambda: (tmp_path / "config.json", tmp_path / "old.txt"))
    monkeypatch.setattr(jk, "_legacy_config_dir", lambda: tmp_path / "legacy")
    return copy.deepcopy(jk.CLI_DEFAULTS)

def test_default_and_persisted_workspace(cfg):
    assert jk._security_center_policies(cfg)[0].workspace_root is None
    cfg["security_path_policy"] = {"version": 1, "workspace_root": "D:/Jack/work", "never_paths": ["D:/Jack/private"]}
    jk._save_cli_config(cfg)
    loaded = jk._load_cli_config()
    assert json.loads(jk._config_to_env(loaded)["JACK_PATH_POLICY_JSON"]) == cfg["security_path_policy"]

def test_admin_environment_precedence(cfg, monkeypatch):
    cfg["security_path_policy"] = {"version": 1, "workspace_root": "D:/Jack/saved", "never_paths": []}
    raw = json.dumps({"version": 1, "workspace_root": "D:/Jack/admin", "never_paths": []})
    monkeypatch.setenv("JACK_PATH_POLICY_JSON", raw)
    assert jk._config_to_env(cfg)["JACK_PATH_POLICY_JSON"] == raw

def test_invalid_policy_refuses_start(cfg, monkeypatch):
    cfg["security_path_policy"] = {"version": 1, "workspace_root": "relative", "never_paths": []}
    with pytest.raises(RuntimeError, match="Invalid security policy"):
        jk._config_to_env(cfg)
    calls = []
    monkeypatch.setattr(jk.subprocess, "run", lambda *a, **k: calls.append(1))
    jk._start_server_from_cli(cfg)
    assert calls == []

def test_session_canary_not_persisted_or_displayed(cfg, monkeypatch, capsys):
    token = "SESSION-CANARY-TEST-991"
    inputs = iter(["5", token, "7", "s"])
    flags = []
    def prompt(label, *, secret=False):
        flags.append(secret)
        return next(inputs)
    monkeypatch.setattr(jk, "_cli_input", prompt)
    jk._run_transactional_editor(jk._edit_security_center, cfg)
    assert True in flags
    assert token not in capsys.readouterr().out
    assert token not in jk._config_paths()[0].read_text(encoding="utf-8")
    assert json.loads(jk._config_to_env(cfg)["JACK_CANARY_POLICY_JSON"])["patterns"][0]["value"] == token

def test_cancelled_edits_leave_policy_unchanged(cfg, monkeypatch):
    before = copy.deepcopy(cfg)
    inputs = iter(["1", "D:/Jack/work", "m"])
    monkeypatch.setattr(jk, "_cli_input", lambda *a, **k: next(inputs))
    with pytest.raises(jk._ReturnToMainMenu):
        jk._run_transactional_editor(jk._edit_security_center, cfg)
    assert cfg == before

def test_invalid_settings_file_is_not_reset(cfg):
    path, _ = jk._config_paths()
    path.write_text("{", encoding="utf-8")
    with pytest.raises(RuntimeError):
        jk._load_cli_config()
    assert path.read_text(encoding="utf-8") == "{"

def test_current_config_resource_is_distinct():
    from jack_credential_resource_guard import _resource_id_for_path
    assert _resource_id_for_path(r"c:\users\test\appdata\roaming\jackkernel\config.json") == "resource:jack-current-config"
    assert _resource_id_for_path(r"c:\users\test\appdata\roaming\jackkernellmstudio\config.json") == "resource:jack-config"

def test_splash_menu_names_feature_not_build_phase(capsys):
    jk._print_main_menu_options()
    jk._print_compact_main_commands()
    out = capsys.readouterr().out
    assert "Security Center" in out and "K Security" in out
    assert "Phase" not in out
