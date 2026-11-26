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

def test_irq_settings_persist_but_values_and_overrides_do_not(cfg, monkeypatch, capsys):
    long_value = "a" * 1024
    short_value = "b" * 128
    inputs = iter(["9", "custom", "9", "4096", "y",
                   "5", long_value, "5", short_value, "10", "1", "25",
                   "7", "s"])
    monkeypatch.setattr(jk, "_cli_input", lambda *a, **k: next(inputs))
    jk._run_transactional_editor(jk._edit_security_center, cfg)
    policy = jk._security_center_policies(cfg)[1]
    assert policy.sensitivity_percent == 9
    assert policy.canaries.required_window == 255
    by_length = {len(item.value): item for item in policy.canaries._patterns}
    assert by_length[1024].sensitivity_percent == 25
    assert by_length[128].sensitivity_percent == 9
    out = capsys.readouterr().out
    assert "Canary 1: 1024 characters / 25% / 256 consecutive characters" in out
    assert "Canary 2: 128 characters / 9% / 12 consecutive characters" in out
    saved = jk._config_paths()[0].read_text(encoding="utf-8")
    assert long_value not in out and long_value not in saved
    assert short_value not in out and short_value not in saved
    restored = jk._load_cli_config()
    assert restored["security_irq_settings"] == {"sensitivity_percent": 9, "max_window": 4096}
    assert jk._security_center_policies(restored)[1].canaries.count == 0


def test_irq_admin_override_keeps_resolved_settings_authoritative(cfg, monkeypatch):
    cfg["security_irq_settings"] = {"sensitivity_percent": 9, "max_window": 4096}
    admin = json.dumps({"version": 1, "patterns": [], "sensitivity_percent": 100, "max_window": 2048})
    monkeypatch.setenv("JACK_CANARY_POLICY_JSON", admin)
    policy = jk._security_center_policies(cfg)[1]
    assert policy.sensitivity_percent == 100
    assert jk._config_to_env(cfg)["JACK_CANARY_POLICY_JSON"] == admin


def test_adaptive_default_and_saved_exact_override(cfg, monkeypatch, capsys):
    policy = jk._security_center_policies(cfg)[1]
    assert policy.sensitivity_percent is None
    jk._security_center_summary(cfg)
    assert "Adaptive (25%, minimum 16; short values exact)" in capsys.readouterr().out
    cfg["security_irq_settings"] = {"sensitivity_percent": 100, "max_window": 4096}
    assert jk._security_center_policies(cfg)[1].sensitivity_percent == 100
    token = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz+-"
    inputs = iter(["9", "adaptive", "", "5", token, "7", "s"])
    monkeypatch.setattr(jk, "_cli_input", lambda *a, **k: next(inputs))
    jk._run_transactional_editor(jk._edit_security_center, cfg)
    assert cfg["security_irq_settings"] == {"max_window": 4096}
    policy = jk._security_center_policies(cfg)[1]
    assert policy.sensitivity_percent is None
    assert policy.canaries._patterns[0].match_chars == 16
    raw = json.loads(jk._config_to_env(cfg)["JACK_CANARY_POLICY_JSON"])
    assert "sensitivity_percent" not in raw
    out = capsys.readouterr().out
    assert "Canary 1: 64 characters / Adaptive / 16 consecutive characters" in out
    assert token not in out
    restored = jk._load_cli_config()
    assert restored["security_irq_settings"] == {"max_window": 4096}
    assert jk._security_center_policies(restored)[1].sensitivity_percent is None


def test_adaptive_and_individual_override_round_trip(cfg, monkeypatch):
    token = "ABCDEFGHIJKLMNOP"
    inputs = iter(["5", token, "10", "1", "25", "y", "s"])
    monkeypatch.setattr(jk, "_cli_input", lambda *a, **k: next(inputs))
    jk._run_transactional_editor(jk._edit_security_center, cfg)
    policy = jk._security_center_policies(cfg)[1]
    assert policy.sensitivity_percent is None
    assert policy.canaries._patterns[0].match_chars == 4
    inputs = iter(["10", "1", "inherit", "s"])
    monkeypatch.setattr(jk, "_cli_input", lambda *a, **k: next(inputs))
    jk._run_transactional_editor(jk._edit_security_center, cfg)
    assert jk._security_center_policies(cfg)[1].canaries._patterns[0].match_chars == 16
