from __future__ import annotations

import json
from pathlib import Path

from engine.persistence import SAVE_DIR
from engine.persistence import normalize_character_name
from game.action_bindings import default_control_bindings, sanitize_control_bindings


PLAYER_CONFIG_VERSION = 2
PLAYER_CONFIG_PATH = SAVE_DIR / "player_config.json"


def default_player_config():
    return {
        "version": PLAYER_CONFIG_VERSION,
        "tutorial_seen": False,
        "tutorial_completed": False,
        "last_character_name": "",
        "control_bindings": default_control_bindings(),
    }


def load_player_config(config_path=None):
    path = Path(config_path) if config_path else PLAYER_CONFIG_PATH
    config = default_player_config()
    if not path.exists():
        return config
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return config
    if isinstance(payload, dict):
        config.update(payload)
    config["version"] = PLAYER_CONFIG_VERSION
    config["tutorial_seen"] = bool(config.get("tutorial_seen"))
    config["tutorial_completed"] = bool(config.get("tutorial_completed"))
    config["last_character_name"] = normalize_character_name(config.get("last_character_name")) or ""
    config["control_bindings"] = sanitize_control_bindings(config.get("control_bindings"))
    return config


def save_player_config(config, config_path=None):
    path = Path(config_path) if config_path else PLAYER_CONFIG_PATH
    clean = default_player_config()
    if isinstance(config, dict):
        clean.update(config)
    clean["version"] = PLAYER_CONFIG_VERSION
    clean["tutorial_seen"] = bool(clean.get("tutorial_seen"))
    clean["tutorial_completed"] = bool(clean.get("tutorial_completed"))
    clean["last_character_name"] = normalize_character_name(clean.get("last_character_name")) or ""
    clean["control_bindings"] = sanitize_control_bindings(clean.get("control_bindings"))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(clean, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
    return path


def last_character_name(config_path=None):
    return normalize_character_name(load_player_config(config_path=config_path).get("last_character_name")) or ""


def remember_character_name(name, config_path=None):
    resolved = normalize_character_name(name)
    if not resolved:
        return None
    config = load_player_config(config_path=config_path)
    config["last_character_name"] = resolved
    save_player_config(config, config_path=config_path)
    return resolved


def mark_tutorial_run_seen(*, completed=False, run_end=None, config_path=None):
    config = load_player_config(config_path=config_path)
    config["tutorial_seen"] = True
    if completed:
        config["tutorial_completed"] = True
    if isinstance(run_end, dict):
        outcome = str(run_end.get("outcome", "") or "").strip().lower()
        reason = str(run_end.get("reason", "") or "").strip().lower()
        if outcome:
            config["tutorial_last_outcome"] = outcome
        if reason:
            config["tutorial_last_reason"] = reason
    return save_player_config(config, config_path=config_path)


def tutorial_requested_from_options(*, tutorial_flag=False, config=None, explicit=False):
    """Read startup tutorial intent from the explicit startup flag.

    The player config still records tutorial seen/completed outcomes, but it no
    longer auto-starts the tutorial on fresh installs while onboarding is being
    playtested.
    """
    del config, explicit
    return bool(tutorial_flag)
