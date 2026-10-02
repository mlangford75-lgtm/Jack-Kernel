from pathlib import Path

PATH = Path("jack_kernel.py")
text = PATH.read_text(encoding="utf-8")
original = text


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    text = text.replace(old, new, 1)


# 1. Make the base caller-contract helper truthful even before the bundled
# compatibility extension wraps it. Remove the obsolete persistent-file reader.
start = text.index("def extract_secondary_system_prompt(")
end = text.index("def strip_secondary_system_messages(", start)
text = text[:start] + '''def merged_secondary_system_prompt(messages: List[Dict[str, Any]]) -> str:\n    \"\"\"Return only the leading caller-owned system contract.\n\n    Pi projects the rendered caller/agent system contract as the first provider-\n    facing ``system`` message. Jack does not promote caller ``developer`` material\n    or later system messages into that contract. The bundled Responses\n    compatibility extension composes this stable caller prefix ahead of Jack's\n    unchanged stage-local contract.\n    \"\"\"\n    if not isinstance(messages, list) or not messages:\n        return \"\"\n    first = messages[0]\n    if not isinstance(first, dict) or first.get(\"role\") != \"system\":\n        return \"\"\n    content = first.get(\"content\")\n    if isinstance(content, str):\n        return content\n    return _content_to_text(content)\n\n\n''' + text[end:]

replace_once(
    "    # Preserve structured/multimodal content exactly enough for secondary\n"
    "    # prompt representation rather than silently dropping it.\n",
    "    # Preserve structured/multimodal content exactly enough for caller-system\n"
    "    # contract representation rather than silently dropping it.\n",
    "content comment",
)

# 2. Stop launcher saves from creating the obsolete prompt file.
replace_once(
    '''def _save_cli_config(cfg: Dict[str, Any]) -> None:\n    config_path, prompt_path = _config_paths()\n    config_path.parent.mkdir(parents=True, exist_ok=True)\n    safe = {k: cfg[k] for k in CLI_DEFAULTS if k in cfg}\n    config_path.write_text(\n        json.dumps(safe, indent=2, ensure_ascii=False) + "\\n",\n        encoding="utf-8",\n    )\n    if not prompt_path.exists():\n        prompt_path.write_text("", encoding="utf-8")\n\n\ndef _load_cli_secondary_prompt() -> str:\n    _, prompt_path = _config_paths()\n    source = prompt_path\n    if not source.exists():\n        legacy = _legacy_config_dir() / "secondary_system_prompt.txt"\n        if legacy.exists():\n            source = legacy\n    try:\n        return source.read_text(encoding="utf-8")\n    except FileNotFoundError:\n        return ""\n    except Exception as exc:\n        print(f"Warning: could not read {source}: {exc}")\n        return ""\n\n\ndef _save_cli_secondary_prompt(text: str) -> None:\n    _, prompt_path = _config_paths()\n    prompt_path.parent.mkdir(parents=True, exist_ok=True)\n    prompt_path.write_text(text.rstrip() + ("\\n" if text.strip() else ""), encoding="utf-8")\n''',
    '''def _save_cli_config(cfg: Dict[str, Any]) -> None:\n    config_path, _ = _config_paths()\n    config_path.parent.mkdir(parents=True, exist_ok=True)\n    safe = {k: cfg[k] for k in CLI_DEFAULTS if k in cfg}\n    config_path.write_text(\n        json.dumps(safe, indent=2, ensure_ascii=False) + "\\n",\n        encoding="utf-8",\n    )\n\n\ndef _legacy_secondary_prompt_path() -> Optional[Path]:\n    \"\"\"Locate a pre-caller-contract prompt artifact without consuming it.\n\n    Existing files are preserved as user-owned migration artifacts. Jack no\n    longer creates, reads, edits, deletes, or exports them into model context.\n    \"\"\"\n    _, current = _config_paths()\n    candidates = (\n        current,\n        _legacy_config_dir() / "secondary_system_prompt.txt",\n    )\n    for candidate in candidates:\n        try:\n            if candidate.is_file() and candidate.stat().st_size > 0:\n                return candidate\n        except OSError:\n            continue\n    return None\n''',
    "save/load legacy prompt block",
)

# 3. Make the launcher status surface truthful and remove the editor entirely.
replace_once(
    '''def _print_header(\n    cfg: Dict[str, Any], *, clear_screen: bool = True, include_brand: bool = True\n) -> None:\n    prompt = _load_cli_secondary_prompt()\n    model = _backend_model_status(cfg)\n''',
    '''def _print_header(\n    cfg: Dict[str, Any], *, clear_screen: bool = True, include_brand: bool = True\n) -> None:\n    model = _backend_model_status(cfg)\n''',
    "header prompt load",
)
replace_once(
    '''    prompt_state = f"SET  [{len(prompt)} chars]" if prompt.strip() else "NOT SET"\n    print(_status_value("Secondary prompt", prompt_state))\n''',
    '''    print(_status_value("Caller system contract", "AGENT / PI OWNED"))\n''',
    "header prompt status",
)
editor_start = text.index("def _edit_secondary_prompt() -> None:")
editor_end = text.index("def _edit_reasoning(", editor_start)
text = text[:editor_start] + text[editor_end:]

# 4. Stop exporting the obsolete environment variable.
replace_once(
    '''def _config_to_env(cfg: Dict[str, Any]) -> Dict[str, str]:\n    _, prompt_path = _config_paths()\n    env = os.environ.copy()\n''',
    '''def _config_to_env(cfg: Dict[str, Any]) -> Dict[str, str]:\n    env = os.environ.copy()\n''',
    "config env prompt path",
)
replace_once(
    '''        "JACK_FORENSIC_ARCHIVE_DIR": cfg.get("forensic_archive_dir", ""),\n        "JACK_SECONDARY_SYSTEM_PROMPT_FILE": str(prompt_path),\n        "JACK_THINKING_TEMPERATURE": cfg["thinking_temperature"],\n''',
    '''        "JACK_FORENSIC_ARCHIVE_DIR": cfg.get("forensic_archive_dir", ""),\n        "JACK_THINKING_TEMPERATURE": cfg["thinking_temperature"],\n''',
    "obsolete env export",
)

# 5. Renumber the launcher cleanly rather than leaving a dead menu slot.
replace_once(
    '''def _print_main_menu_options() -> None:\n    print(_ansi_rgb("  1", _JACK_ICE, bold=True) + "  Start Kernel")\n    print(_ansi_rgb("  2", _JACK_STEEL, bold=True) + "  Persistent secondary system prompt")\n    print(_ansi_rgb("  3", _JACK_STEEL, bold=True) + "  Model Selection")\n    print(_ansi_rgb("  4", _JACK_STEEL, bold=True) + "  Reasoning level")\n    print(_ansi_rgb("  5", _JACK_STEEL, bold=True) + "  Sampling settings")\n    print(_ansi_rgb("  6", _JACK_STEEL, bold=True) + "  Server / agent endpoint")\n    print(_ansi_rgb("  7", _JACK_STEEL, bold=True) + "  Advanced settings")\n    print(_ansi_rgb("  8", _JACK_STEEL, bold=True) + "  Test backend connection")\n    print(_ansi_rgb("  9", _JACK_STEEL, bold=True) + "  Reset Jack defaults")\n''',
    '''def _print_main_menu_options() -> None:\n    print(_ansi_rgb("  1", _JACK_ICE, bold=True) + "  Start Kernel")\n    print(_ansi_rgb("  2", _JACK_STEEL, bold=True) + "  Model Selection")\n    print(_ansi_rgb("  3", _JACK_STEEL, bold=True) + "  Reasoning level")\n    print(_ansi_rgb("  4", _JACK_STEEL, bold=True) + "  Sampling settings")\n    print(_ansi_rgb("  5", _JACK_STEEL, bold=True) + "  Server / agent endpoint")\n    print(_ansi_rgb("  6", _JACK_STEEL, bold=True) + "  Advanced settings")\n    print(_ansi_rgb("  7", _JACK_STEEL, bold=True) + "  Test backend connection")\n    print(_ansi_rgb("  8", _JACK_STEEL, bold=True) + "  Reset Jack defaults")\n''',
    "main menu",
)
replace_once(
    '''    print(_ansi_rgb("Main:", _JACK_MUTED) +\n          " 1 Start  2 Prompt  3 Models  4 Reasoning  5 Sampling  6 Endpoint")\n    print("      7 Advanced  8 Test  9 Reset  P Thinking  F Forensic  S Save  M Main screen  Q Quit")\n''',
    '''    print(_ansi_rgb("Main:", _JACK_MUTED) +\n          " 1 Start  2 Models  3 Reasoning  4 Sampling  5 Endpoint  6 Advanced")\n    print("      7 Test  8 Reset  P Thinking  F Forensic  S Save  M Main screen  Q Quit")\n''',
    "compact menu",
)
replace_once(
    '''            if choice == "1":\n                _start_server_from_cli(cfg)\n            elif choice == "2":\n                _edit_secondary_prompt()\n            elif choice == "3":\n                _run_transactional_editor(_edit_model_selection, cfg)\n            elif choice == "4":\n                _run_transactional_editor(_edit_reasoning, cfg)\n            elif choice == "5":\n                _run_transactional_editor(_edit_sampling, cfg)\n            elif choice == "6":\n                _run_transactional_editor(_edit_network, cfg)\n            elif choice == "7":\n                _run_transactional_editor(_edit_advanced, cfg)\n            elif choice == "8":\n                _test_backend(cfg)\n            elif choice == "9":\n                confirm = _cli_input("Reset all settings to Jack defaults? [y/N]: ").strip().lower()\n                if confirm in {"y", "yes"}:\n                    cfg = copy.deepcopy(CLI_DEFAULTS)\n                    print("Defaults restored. Secondary system prompt was preserved.")\n''',
    '''            if choice == "1":\n                _start_server_from_cli(cfg)\n            elif choice == "2":\n                _run_transactional_editor(_edit_model_selection, cfg)\n            elif choice == "3":\n                _run_transactional_editor(_edit_reasoning, cfg)\n            elif choice == "4":\n                _run_transactional_editor(_edit_sampling, cfg)\n            elif choice == "5":\n                _run_transactional_editor(_edit_network, cfg)\n            elif choice == "6":\n                _run_transactional_editor(_edit_advanced, cfg)\n            elif choice == "7":\n                _test_backend(cfg)\n            elif choice == "8":\n                confirm = _cli_input("Reset all settings to Jack defaults? [y/N]: ").strip().lower()\n                if confirm in {"y", "yes"}:\n                    cfg = copy.deepcopy(CLI_DEFAULTS)\n                    print("Defaults restored.")\n''',
    "menu dispatch",
)

# 6. Fix help text that referred to old numeric menu positions.
text = text.replace("Open option 3 and verify the backend authentication setting and secret.",
                    "Open option 2 and verify the backend authentication setting and secret.")
text = text.replace("enter the exact model ID manually in option 3.",
                    "enter the exact model ID manually in option 2.")
text = text.replace("Backend endpoint is not configured. Use option 3 first.",
                    "Backend endpoint is not configured. Use option 2 first.")

# 7. Clarify the public authority-boundary documentation without changing it.
replace_once(
    '''    The calling agent owns ordinary conversation content, tool definitions, bounded\n    tool choice, multimodal user/assistant/tool message content, and the decision\n    to request SSE streaming. Incoming calling-agent system/developer messages are\n    blocked at the Jack boundary and are never forwarded to backend model stages.\n    Jack owns reasoning profiles, native\n''',
    '''    The calling agent owns ordinary conversation content, tool definitions, bounded\n    tool choice, multimodal user/assistant/tool message content, the leading caller\n    system cognitive contract, and the decision to request SSE streaming. Only the\n    leading caller ``system`` message is promoted as that contract; caller\n    ``developer`` material and later system messages are not promoted. Stage history\n    still strips system/developer transport messages after the caller contract is\n    captured. Jack owns reasoning profiles, native\n''',
    "sanitize docstring",
)

# 8. Warn once in the launcher if an old non-empty artifact exists, but never
# read/delete/modify it. This preserves migration evidence without pretending it
# still controls Jack.
replace_once(
    '''    if _normalize_backend_profile(str(cfg.get("backend_profile") or "lmstudio")) == "lmstudio":\n        cfg["backend_model"] = ""\n    return cfg\n''',
    '''    if _normalize_backend_profile(str(cfg.get("backend_profile") or "lmstudio")) == "lmstudio":\n        cfg["backend_model"] = ""\n\n    legacy_prompt = _legacy_secondary_prompt_path()\n    if legacy_prompt is not None:\n        print(\n            "Note: legacy Jack secondary prompt file is preserved but ignored: "\n            f"{legacy_prompt}. Configure the agent system contract in Pi/the caller."\n        )\n    return cfg\n''',
    "legacy migration notice",
)

# Source-level acceptance assertions.
for forbidden in (
    "JACK_SECONDARY_SYSTEM_PROMPT_FILE",
    "Persistent secondary system prompt",
    "Secondary prompt\", prompt_state",
    "def _edit_secondary_prompt",
    "def _load_cli_secondary_prompt",
    "def _save_cli_secondary_prompt",
    "def configured_secondary_system_prompt",
    "def extract_secondary_system_prompt",
):
    if forbidden in text:
        raise SystemExit(f"obsolete surface remains: {forbidden}")

if text == original:
    raise SystemExit("cleanup produced no changes")

PATH.write_text(text, encoding="utf-8", newline="\n")
print("secondary-prompt launcher cleanup applied")
