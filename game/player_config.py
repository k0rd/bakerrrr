from __future__ import annotations

import json
from pathlib import Path

from engine.persistence import SAVE_DIR
from engine.persistence import normalize_character_name
from game.action_bindings import default_control_bindings, sanitize_control_bindings


PLAYER_CONFIG_VERSION = 4
PLAYER_CONFIG_PATH = SAVE_DIR / "player_config.json"


def normalize_world_magnification(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 1
    return 2 if value == 2 else 1


def normalize_accessibility_config(raw):
    source = raw if isinstance(raw, dict) else {}
    return {
        "world_magnification": normalize_world_magnification(
            source.get("world_magnification", 1)
        ),
    }


def default_player_config():
    return {
        "version": PLAYER_CONFIG_VERSION,
        "last_character_name": "",
        "control_bindings": default_control_bindings(),
        "accessibility": normalize_accessibility_config({}),
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
        config["last_character_name"] = payload.get("last_character_name", "")
        config["control_bindings"] = payload.get("control_bindings")
        config["accessibility"] = payload.get("accessibility")
    config["version"] = PLAYER_CONFIG_VERSION
    config["last_character_name"] = normalize_character_name(config.get("last_character_name")) or ""
    config["control_bindings"] = sanitize_control_bindings(config.get("control_bindings"))
    config["accessibility"] = normalize_accessibility_config(config.get("accessibility"))
    return config


def save_player_config(config, config_path=None):
    path = Path(config_path) if config_path else PLAYER_CONFIG_PATH
    clean = default_player_config()
    if isinstance(config, dict):
        clean["last_character_name"] = config.get("last_character_name", "")
        clean["control_bindings"] = config.get("control_bindings")
        clean["accessibility"] = config.get("accessibility")
    clean["version"] = PLAYER_CONFIG_VERSION
    clean["last_character_name"] = normalize_character_name(clean.get("last_character_name")) or ""
    clean["control_bindings"] = sanitize_control_bindings(clean.get("control_bindings"))
    clean["accessibility"] = normalize_accessibility_config(clean.get("accessibility"))
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
