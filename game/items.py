import json
import random
from pathlib import Path

from game.content_warnings import warn_content_fallback


ITEMS_PATH = Path(__file__).resolve().parent / "items.json"
LOOT_TABLES_PATH = Path(__file__).resolve().parent / "loot_tables.json"
ITEM_QUALITY_TIERS = ("poor", "standard", "good", "excellent")
ITEM_QUALITY_SCORE_BONUS = {
    "poor": -0.35,
    "standard": 0.0,
    "good": 0.2,
    "excellent": 0.45,
}
ITEM_QUALITY_REQUIREMENT_DELTA = {
    "poor": 0.28,
    "standard": 0.0,
    "good": -0.18,
    "excellent": -0.4,
}


def _float_or_default(value, default=0.0):
    try:
        if value is None:
            raise TypeError
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _int_or_default(value, default=0):
    try:
        if value is None:
            raise TypeError
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _string_tuple(values):
    if not isinstance(values, (list, tuple)):
        values = [values]
    parsed = []
    for value in values:
        token = str(value or "").strip().lower()
        if token:
            parsed.append(token)
    return tuple(parsed)


def _normalize_tool_profiles(value):
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []

    parsed = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        contexts = _string_tuple(raw.get("contexts"))
        if not contexts:
            continue
        parsed.append({
            "contexts": contexts,
            "enable_contexts": _string_tuple(raw.get("enable_contexts")),
            "intrusion_bonus": _float_or_default(raw.get("intrusion_bonus"), 0.0),
            "mechanics_bonus": _float_or_default(raw.get("mechanics_bonus"), 0.0),
            "perception_bonus": _float_or_default(raw.get("perception_bonus"), 0.0),
            "score_bonus": _float_or_default(raw.get("score_bonus"), 0.0),
            "requirement_delta": _float_or_default(raw.get("requirement_delta"), 0.0),
        })
    return parsed


def _normalize_armor_profile(value):
    if not isinstance(value, dict):
        return None

    slot = str(value.get("slot", "body")).strip().lower() or "body"
    reduction = _float_or_default(value.get("damage_reduction"), 0.0)
    reduction = max(0.0, min(0.85, reduction))
    if reduction <= 0.0:
        return None
    return {
        "slot": slot,
        "damage_reduction": reduction,
    }


def normalize_item_quality(value, default="standard"):
    token = str(value or "").strip().lower()
    if token not in ITEM_QUALITY_TIERS:
        token = str(default or "standard").strip().lower()
    if token not in ITEM_QUALITY_TIERS:
        token = "standard"
    return token


def _normalize_condition_profile(value, *, tool_profiles=None, weapon_id=None, armor=None, stack_max=1):
    raw = value if isinstance(value, dict) else {}
    gear_default = bool(tool_profiles or weapon_id or armor)
    if _int_or_default(stack_max, 1) > 1 and "supports_quality" not in raw and "supports_durability" not in raw:
        gear_default = False

    supports_quality = bool(raw.get("supports_quality", gear_default))
    supports_durability = bool(raw.get("supports_durability", gear_default))
    default_quality = normalize_item_quality(raw.get("default_quality"), default="standard")

    if tool_profiles:
        default_max_durability = 4
    elif weapon_id:
        default_max_durability = 6
    elif armor:
        default_max_durability = 7
    else:
        default_max_durability = 0

    max_durability = max(
        0,
        _int_or_default(raw.get("max_durability"), default_max_durability if supports_durability else 0),
    )
    if supports_durability and max_durability <= 0:
        max_durability = max(1, default_max_durability or 4)

    return {
        "supports_quality": supports_quality,
        "supports_durability": supports_durability,
        "default_quality": default_quality,
        "max_durability": int(max_durability),
    }


DEFAULT_ITEM_CATALOG = {
    "street_ration": {
        "name": "Street Ration",
        "glyph": "%",
        "stack_max": 3,
        "tags": ["consumable", "energy", "food", "legal"],
        "legal_status": "legal",
        "effects": [
            {"type": "modify_need", "need": "energy", "delta": 18},
            {"type": "status", "status": "well_fed", "duration": 22, "modifiers": {"energy_tick_delta": 0.08}},
        ],
    },
    "caff_shot": {
        "name": "Caff Shot",
        "glyph": "!",
        "stack_max": 2,
        "tags": ["consumable", "energy", "stimulant", "restricted"],
        "legal_status": "restricted",
        "effects": [
            {"type": "modify_need", "need": "energy", "delta": 24},
            {"type": "status", "status": "wired", "duration": 16, "modifiers": {"energy_tick_delta": 0.1, "safety_tick_delta": -0.12, "move_speed_mult": 0.22}},
        ],
    },
    "calm_patch": {
        "name": "Calm Patch",
        "glyph": "!",
        "stack_max": 2,
        "tags": ["consumable", "safety", "medical", "legal"],
        "legal_status": "legal",
        "effects": [
            {"type": "modify_need", "need": "safety", "delta": 20},
            {"type": "status", "status": "calm", "duration": 24, "modifiers": {"safety_tick_delta": 0.09, "move_speed_mult": -0.1}},
        ],
    },
    "spark_brew": {
        "name": "Spark Brew",
        "glyph": "!",
        "stack_max": 2,
        "tags": ["consumable", "social", "drink", "legal"],
        "legal_status": "legal",
        "effects": [
            {"type": "modify_need", "need": "social", "delta": 16},
            {"type": "status", "status": "buzzed", "duration": 20, "modifiers": {"social_tick_delta": 0.08, "safety_tick_delta": -0.04, "move_speed_mult": 0.12}},
        ],
    },
    "med_gel": {
        "name": "Med Gel",
        "glyph": "!",
        "stack_max": 2,
        "tags": ["consumable", "medical", "safety", "legal"],
        "legal_status": "legal",
        "effects": [
            {"type": "restore_hp", "delta": 14},
            {"type": "modify_need", "need": "safety", "delta": 24},
        ],
    },
    "focus_inhaler": {
        "name": "Focus Inhaler",
        "glyph": "!",
        "stack_max": 1,
        "tags": ["consumable", "discipline", "restricted"],
        "legal_status": "restricted",
        "effects": [
            {"type": "status", "status": "focused", "duration": 28, "modifiers": {"energy_tick_delta": 0.06, "social_tick_delta": -0.05, "move_speed_mult": 0.08}},
        ],
    },
    "black_market_stim": {
        "name": "Black Market Stim",
        "glyph": "!",
        "stack_max": 1,
        "tags": ["consumable", "energy", "illegal", "stimulant"],
        "legal_status": "illegal",
        "effects": [
            {"type": "modify_need", "need": "energy", "delta": 30},
            {"type": "modify_need", "need": "safety", "delta": -10},
            {"type": "status", "status": "agitated", "duration": 20, "modifiers": {"safety_tick_delta": -0.12, "energy_tick_delta": -0.06, "move_speed_mult": 0.35}},
        ],
    },
    "protein_wrap": {
        "name": "Protein Wrap",
        "glyph": "%",
        "stack_max": 3,
        "tags": ["consumable", "energy", "food", "legal"],
        "legal_status": "legal",
        "effects": [
            {"type": "modify_need", "need": "energy", "delta": 14},
            {"type": "modify_need", "need": "safety", "delta": 4},
        ],
    },
    "noodle_cup": {
        "name": "Noodle Cup",
        "glyph": "%",
        "stack_max": 3,
        "tags": ["consumable", "energy", "food", "legal"],
        "legal_status": "legal",
        "effects": [
            {"type": "modify_need", "need": "energy", "delta": 16},
            {"type": "status", "status": "warm_meal", "duration": 16, "modifiers": {"energy_tick_delta": 0.05}},
        ],
    },
    "hydration_salts": {
        "name": "Hydration Salts",
        "glyph": "!",
        "stack_max": 2,
        "tags": ["consumable", "medical", "safety", "legal"],
        "legal_status": "legal",
        "effects": [
            {"type": "modify_need", "need": "safety", "delta": 12},
            {"type": "modify_need", "need": "energy", "delta": 8},
            {"type": "status", "status": "hydrated", "duration": 20, "modifiers": {"safety_tick_delta": 0.05, "energy_tick_delta": 0.04}},
        ],
    },
    "micro_medkit": {
        "name": "Micro Medkit",
        "glyph": "!",
        "stack_max": 1,
        "tags": ["consumable", "medical", "safety", "legal"],
        "legal_status": "legal",
        "effects": [
            {"type": "restore_hp", "delta": 22},
            {"type": "modify_need", "need": "safety", "delta": 18},
        ],
    },
    "trauma_foam": {
        "name": "Trauma Foam",
        "glyph": "!",
        "stack_max": 1,
        "tags": ["consumable", "medical", "safety", "restricted"],
        "legal_status": "restricted",
        "effects": [
            {"type": "restore_hp", "delta": 30},
            {"type": "modify_need", "need": "safety", "delta": 24},
            {"type": "status", "status": "patched_up", "duration": 18, "modifiers": {"safety_tick_delta": 0.08, "move_speed_mult": -0.08}},
        ],
    },
    "synth_focus_tabs": {
        "name": "Synth Focus Tabs",
        "glyph": "!",
        "stack_max": 2,
        "tags": ["consumable", "discipline", "restricted"],
        "legal_status": "restricted",
        "effects": [
            {"type": "status", "status": "steady_hands", "duration": 22, "modifiers": {"energy_tick_delta": 0.05, "move_speed_mult": 0.07}},
        ],
    },
    "smoke_tab": {
        "name": "Smoke Tab",
        "glyph": "!",
        "stack_max": 2,
        "tags": ["consumable", "social", "illegal"],
        "legal_status": "illegal",
        "effects": [
            {"type": "modify_need", "need": "social", "delta": 10},
            {"type": "modify_need", "need": "safety", "delta": -4},
            {"type": "status", "status": "hazy", "duration": 18, "modifiers": {"social_tick_delta": 0.07, "safety_tick_delta": -0.08}},
        ],
    },
    "credstick_chip": {
        "name": "Credstick Chip",
        "glyph": "=",
        "stack_max": 4,
        "tags": ["token", "legal"],
        "legal_status": "legal",
        "effects": [
            {"type": "credits", "delta": 20},
        ],
    },
    "transit_daypass": {
        "name": "Transit Daypass",
        "glyph": "=",
        "stack_max": 3,
        "tags": ["token", "legal"],
        "legal_status": "legal",
        "effects": [],
    },
    "forged_badge": {
        "name": "Forged Badge",
        "glyph": "=",
        "stack_max": 1,
        "tags": ["token", "illegal"],
        "legal_status": "illegal",
        "effects": [],
        "tool_profiles": [
            {
                "contexts": ["badge_controller"],
                "enable_contexts": ["badge_controller"],
                "intrusion_bonus": 0.9,
                "perception_bonus": 0.25,
                "requirement_delta": -1.15,
            },
        ],
    },
    "city_pass_token": {
        "name": "City Pass Token",
        "glyph": "=",
        "stack_max": 5,
        "tags": ["token", "legal"],
        "legal_status": "legal",
        "effects": [],
    },
    "property_key": {
        "name": "Property Key",
        "glyph": "=",
        "stack_max": 1,
        "tags": ["key", "tool", "legal"],
        "legal_status": "legal",
        "effects": [],
    },
    "access_badge": {
        "name": "Access Badge",
        "glyph": "=",
        "stack_max": 1,
        "tags": ["credential", "token", "legal"],
        "legal_status": "legal",
        "effects": [],
    },
    "manager_badge": {
        "name": "Manager Badge",
        "glyph": "=",
        "stack_max": 1,
        "tags": ["credential", "token", "legal"],
        "legal_status": "legal",
        "effects": [],
    },
    "lockpick_kit": {
        "name": "Lockpick Kit",
        "glyph": ")",
        "stack_max": 1,
        "tags": ["tool", "illegal"],
        "legal_status": "illegal",
        "effects": [],
        "tool_profiles": [
            {
                "contexts": ["mechanical_lock"],
                "enable_contexts": ["mechanical_lock"],
                "intrusion_bonus": 1.6,
                "mechanics_bonus": 0.45,
                "perception_bonus": 0.1,
                "requirement_delta": -1.75,
            },
            {
                "contexts": ["vehicle_ignition"],
                "enable_contexts": ["vehicle_ignition"],
                "intrusion_bonus": 1.2,
                "mechanics_bonus": 0.75,
                "requirement_delta": -1.5,
            },
            {
                "contexts": ["side_entry"],
                "enable_contexts": ["side_entry"],
                "intrusion_bonus": 1.0,
                "mechanics_bonus": 0.35,
                "requirement_delta": -1.2,
            },
        ],
    },
    "prybar": {
        "name": "Prybar",
        "glyph": ")",
        "stack_max": 1,
        "tags": ["tool", "illegal"],
        "legal_status": "illegal",
        "effects": [],
        "tool_profiles": [
            {
                "contexts": ["side_entry"],
                "enable_contexts": ["side_entry"],
                "intrusion_bonus": 0.45,
                "mechanics_bonus": 0.2,
                "requirement_delta": -0.9,
            },
        ],
    },
    "signal_jammer": {
        "name": "Signal Jammer",
        "glyph": ")",
        "stack_max": 1,
        "tags": ["tool", "restricted"],
        "legal_status": "restricted",
        "effects": [],
        "tool_profiles": [
            {
                "contexts": ["badge_controller"],
                "intrusion_bonus": 0.85,
                "mechanics_bonus": 0.4,
                "perception_bonus": 0.25,
                "requirement_delta": -1.1,
            },
            {
                "contexts": ["biometric_controller"],
                "intrusion_bonus": 0.55,
                "mechanics_bonus": 0.5,
                "perception_bonus": 0.35,
                "requirement_delta": -0.85,
            },
            {
                "contexts": ["schedule_controller"],
                "enable_contexts": ["schedule_controller"],
                "intrusion_bonus": 0.7,
                "mechanics_bonus": 0.45,
                "perception_bonus": 0.2,
                "requirement_delta": -0.9,
            },
            {
                "contexts": ["relay_controller"],
                "enable_contexts": ["relay_controller"],
                "intrusion_bonus": 0.8,
                "mechanics_bonus": 0.4,
                "perception_bonus": 0.25,
                "requirement_delta": -1.0,
            },
        ],
    },
    "rust_revolver": {
        "name": "Rust Revolver",
        "glyph": ")",
        "stack_max": 1,
        "tags": ["weapon", "handgun", "illegal"],
        "legal_status": "illegal",
        "effects": [],
        "weapon_id": "rust_revolver",
    },
    "alley_shotgun": {
        "name": "Alley Shotgun",
        "glyph": ")",
        "stack_max": 1,
        "tags": ["weapon", "shotgun", "illegal"],
        "legal_status": "illegal",
        "effects": [],
        "weapon_id": "alley_shotgun",
    },
    "compact_smg": {
        "name": "Compact SMG",
        "glyph": ")",
        "stack_max": 1,
        "tags": ["weapon", "smg", "illegal"],
        "legal_status": "illegal",
        "effects": [],
        "weapon_id": "compact_smg",
    },
    "improvised_launcher": {
        "name": "Improvised Launcher",
        "glyph": ")",
        "stack_max": 1,
        "tags": ["weapon", "launcher", "illegal"],
        "legal_status": "illegal",
        "effects": [],
        "weapon_id": "improvised_launcher",
    },
    "padded_jacket": {
        "name": "Padded Jacket",
        "glyph": "[",
        "stack_max": 1,
        "tags": ["armor", "wearable", "legal"],
        "legal_status": "legal",
        "effects": [],
        "armor": {
            "slot": "body",
            "damage_reduction": 0.12,
        },
    },
    "security_vest": {
        "name": "Security Vest",
        "glyph": "[",
        "stack_max": 1,
        "tags": ["armor", "wearable", "restricted"],
        "legal_status": "restricted",
        "effects": [],
        "armor": {
            "slot": "body",
            "damage_reduction": 0.22,
        },
    },
    "ceramic_plate_rig": {
        "name": "Ceramic Plate Rig",
        "glyph": "[",
        "stack_max": 1,
        "tags": ["armor", "wearable", "illegal"],
        "legal_status": "illegal",
        "effects": [],
        "armor": {
            "slot": "body",
            "damage_reduction": 0.34,
        },
    },
    "pocket_multitool": {
        "name": "Pocket Multitool",
        "glyph": ")",
        "stack_max": 1,
        "tags": ["tool", "restricted"],
        "legal_status": "restricted",
        "effects": [],
        "tool_profiles": [
            {
                "contexts": ["mechanical_lock"],
                "intrusion_bonus": 0.45,
                "mechanics_bonus": 0.55,
                "requirement_delta": -0.5,
            },
            {
                "contexts": ["vehicle_ignition"],
                "intrusion_bonus": 0.35,
                "mechanics_bonus": 0.9,
                "requirement_delta": -0.75,
            },
            {
                "contexts": ["badge_controller"],
                "intrusion_bonus": 0.4,
                "mechanics_bonus": 0.65,
                "perception_bonus": 0.2,
                "requirement_delta": -0.55,
            },
            {
                "contexts": ["biometric_controller"],
                "intrusion_bonus": 0.25,
                "mechanics_bonus": 0.75,
                "perception_bonus": 0.25,
                "requirement_delta": -0.45,
            },
            {
                "contexts": ["schedule_controller"],
                "intrusion_bonus": 0.25,
                "mechanics_bonus": 0.7,
                "perception_bonus": 0.15,
                "requirement_delta": -0.4,
            },
            {
                "contexts": ["relay_controller"],
                "intrusion_bonus": 0.3,
                "mechanics_bonus": 0.75,
                "perception_bonus": 0.15,
                "requirement_delta": -0.45,
            },
            {
                "contexts": ["side_entry"],
                "intrusion_bonus": 0.25,
                "mechanics_bonus": 0.5,
                "requirement_delta": -0.35,
            },
        ],
    },
}


DEFAULT_LOOT_TABLES = {
    "default": [
        {"item_id": "street_ration", "weight": 30},
        {"item_id": "protein_wrap", "weight": 18},
        {"item_id": "noodle_cup", "weight": 16},
        {"item_id": "spark_brew", "weight": 20},
        {"item_id": "calm_patch", "weight": 18},
        {"item_id": "hydration_salts", "weight": 12},
        {"item_id": "caff_shot", "weight": 16},
        {"item_id": "city_pass_token", "weight": 14},
        {"item_id": "transit_daypass", "weight": 10},
        {"item_id": "credstick_chip", "weight": 9},
        {"item_id": "med_gel", "weight": 10},
        {"item_id": "micro_medkit", "weight": 8},
        {"item_id": "focus_inhaler", "weight": 8},
        {"item_id": "synth_focus_tabs", "weight": 6},
        {"item_id": "lockpick_kit", "weight": 5},
        {"item_id": "prybar", "weight": 4},
        {"item_id": "signal_jammer", "weight": 3},
        {"item_id": "black_market_stim", "weight": 4},
    ],
    "kind:building": [
        {"item_id": "street_ration", "weight": 26},
        {"item_id": "protein_wrap", "weight": 14},
        {"item_id": "noodle_cup", "weight": 12},
        {"item_id": "city_pass_token", "weight": 18},
        {"item_id": "transit_daypass", "weight": 11},
        {"item_id": "spark_brew", "weight": 16},
        {"item_id": "calm_patch", "weight": 14},
        {"item_id": "hydration_salts", "weight": 11},
        {"item_id": "med_gel", "weight": 12},
        {"item_id": "micro_medkit", "weight": 8},
        {"item_id": "caff_shot", "weight": 11},
        {"item_id": "focus_inhaler", "weight": 8},
        {"item_id": "synth_focus_tabs", "weight": 6},
        {"item_id": "credstick_chip", "weight": 7},
        {"item_id": "lockpick_kit", "weight": 4},
        {"item_id": "prybar", "weight": 3},
        {"item_id": "forged_badge", "weight": 2},
        {"item_id": "black_market_stim", "weight": 3},
    ],
    "kind:fixture": [
        {"item_id": "city_pass_token", "weight": 18},
        {"item_id": "transit_daypass", "weight": 14},
        {"item_id": "credstick_chip", "weight": 10},
        {"item_id": "street_ration", "weight": 16},
        {"item_id": "protein_wrap", "weight": 12},
        {"item_id": "calm_patch", "weight": 10},
        {"item_id": "hydration_salts", "weight": 8},
        {"item_id": "caff_shot", "weight": 8},
    ],
    "kind:asset": [
        {"item_id": "city_pass_token", "weight": 16},
        {"item_id": "transit_daypass", "weight": 12},
        {"item_id": "credstick_chip", "weight": 10},
        {"item_id": "spark_brew", "weight": 14},
        {"item_id": "focus_inhaler", "weight": 8},
        {"item_id": "synth_focus_tabs", "weight": 7},
        {"item_id": "lockpick_kit", "weight": 6},
        {"item_id": "prybar", "weight": 7},
        {"item_id": "signal_jammer", "weight": 6},
        {"item_id": "forged_badge", "weight": 4},
    ],
    "archetype:checkpoint": [
        {"item_id": "med_gel", "weight": 20},
        {"item_id": "micro_medkit", "weight": 16},
        {"item_id": "trauma_foam", "weight": 12},
        {"item_id": "focus_inhaler", "weight": 16},
        {"item_id": "synth_focus_tabs", "weight": 10},
        {"item_id": "caff_shot", "weight": 14},
        {"item_id": "city_pass_token", "weight": 12},
        {"item_id": "transit_daypass", "weight": 8},
    ],
    "archetype:armory": [
        {"item_id": "med_gel", "weight": 18},
        {"item_id": "micro_medkit", "weight": 14},
        {"item_id": "trauma_foam", "weight": 14},
        {"item_id": "focus_inhaler", "weight": 16},
        {"item_id": "synth_focus_tabs", "weight": 11},
        {"item_id": "lockpick_kit", "weight": 9},
        {"item_id": "prybar", "weight": 8},
        {"item_id": "signal_jammer", "weight": 7},
        {"item_id": "black_market_stim", "weight": 7},
    ],
    "archetype:nightclub": [
        {"item_id": "spark_brew", "weight": 24},
        {"item_id": "smoke_tab", "weight": 16},
        {"item_id": "caff_shot", "weight": 14},
        {"item_id": "credstick_chip", "weight": 8},
        {"item_id": "black_market_stim", "weight": 8},
    ],
    "archetype:bar": [
        {"item_id": "spark_brew", "weight": 22},
        {"item_id": "smoke_tab", "weight": 14},
        {"item_id": "street_ration", "weight": 14},
        {"item_id": "protein_wrap", "weight": 10},
        {"item_id": "caff_shot", "weight": 10},
    ],
}


def _read_json(path, fallback_desc=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        if fallback_desc:
            warn_content_fallback(path, fallback_desc, exc=exc)
        return None


def load_item_catalog(path=ITEMS_PATH):
    raw = _read_json(path, fallback_desc="built-in item catalog defaults")
    if raw is not None and not isinstance(raw, dict):
        warn_content_fallback(path, "built-in item catalog defaults", problem="top-level JSON must be an object")
    source = raw if isinstance(raw, dict) else DEFAULT_ITEM_CATALOG
    parsed = {}

    for item_id, item in source.items():
        if not isinstance(item_id, str) or not isinstance(item, dict):
            continue

        name = item.get("name", item_id.replace("_", " ").title())
        glyph = item.get("glyph", "?")
        stack_max = max(1, int(item.get("stack_max", 1)))
        tags = item.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        tags = [str(tag).lower() for tag in tags if str(tag).strip()]

        legal_status = str(item.get("legal_status", "legal")).lower()
        if legal_status not in {"legal", "restricted", "illegal"}:
            legal_status = "legal"

        effects = item.get("effects", [])
        if not isinstance(effects, list):
            effects = []

        parsed[item_id] = {
            "id": item_id,
            "name": name,
            "glyph": str(glyph)[:1] or "?",
            "stack_max": stack_max,
            "tags": tags,
            "legal_status": legal_status,
            "effects": [effect for effect in effects if isinstance(effect, dict)],
            "tool_profiles": _normalize_tool_profiles(item.get("tool_profiles")),
            "weapon_id": str(item.get("weapon_id", "")).strip() or None,
            "armor": _normalize_armor_profile(item.get("armor")),
            "condition_profile": _normalize_condition_profile(
                item.get("condition_profile"),
                tool_profiles=item.get("tool_profiles"),
                weapon_id=item.get("weapon_id"),
                armor=item.get("armor"),
                stack_max=stack_max,
            ),
        }

    if not parsed:
        return {
            item_id: {**item, "id": item_id}
            for item_id, item in DEFAULT_ITEM_CATALOG.items()
        }
    return parsed


def load_loot_tables(path=LOOT_TABLES_PATH, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    raw = _read_json(path, fallback_desc="built-in loot table defaults")
    if raw is not None and not isinstance(raw, dict):
        warn_content_fallback(path, "built-in loot table defaults", problem="top-level JSON must be an object")
    source = raw if isinstance(raw, dict) else DEFAULT_LOOT_TABLES

    parsed = {}
    for table_key, entries in source.items():
        if not isinstance(table_key, str) or not isinstance(entries, list):
            continue

        parsed_entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            item_id = entry.get("item_id")
            if item_id not in item_catalog:
                continue
            weight = max(1, int(entry.get("weight", 1)))
            parsed_entries.append({
                "item_id": item_id,
                "weight": weight,
            })

        if parsed_entries:
            parsed[table_key] = parsed_entries

    if not parsed:
        return dict(DEFAULT_LOOT_TABLES)
    return parsed


def item_condition_profile(item_id, item_catalog=None):
    catalog = item_catalog or ITEM_CATALOG
    item_def = catalog.get(item_id, {})
    profile = item_def.get("condition_profile")
    if isinstance(profile, dict):
        return {
            "supports_quality": bool(profile.get("supports_quality", False)),
            "supports_durability": bool(profile.get("supports_durability", False)),
            "default_quality": normalize_item_quality(profile.get("default_quality"), default="standard"),
            "max_durability": max(0, _int_or_default(profile.get("max_durability"), 0)),
        }
    return _normalize_condition_profile(
        item_def.get("condition_profile"),
        tool_profiles=item_def.get("tool_profiles"),
        weapon_id=item_def.get("weapon_id"),
        armor=item_def.get("armor"),
        stack_max=item_def.get("stack_max", 1),
    )


def normalize_item_instance_metadata(item_id, metadata=None, item_catalog=None):
    catalog = item_catalog or ITEM_CATALOG
    merged = dict(metadata or {})
    profile = item_condition_profile(item_id, item_catalog=catalog)

    if profile.get("supports_quality"):
        merged["item_quality"] = normalize_item_quality(
            merged.get("item_quality"),
            default=profile.get("default_quality", "standard"),
        )
    if profile.get("supports_durability"):
        max_durability = max(1, _int_or_default(merged.get("item_max_durability"), profile.get("max_durability", 1)))
        durability = _int_or_default(merged.get("item_durability"), max_durability)
        merged["item_max_durability"] = int(max_durability)
        merged["item_durability"] = max(0, min(int(max_durability), int(durability)))
    return merged


def item_instance_condition(item_id, metadata=None, item_catalog=None):
    catalog = item_catalog or ITEM_CATALOG
    profile = item_condition_profile(item_id, item_catalog=catalog)
    normalized = normalize_item_instance_metadata(item_id, metadata=metadata, item_catalog=catalog)
    quality = normalize_item_quality(
        normalized.get("item_quality"),
        default=profile.get("default_quality", "standard"),
    )
    max_durability = max(0, _int_or_default(normalized.get("item_max_durability"), profile.get("max_durability", 0)))
    durability = max(0, _int_or_default(normalized.get("item_durability"), max_durability))
    if profile.get("supports_durability") and max_durability > 0:
        durability_ratio = max(0.0, min(1.0, float(durability) / float(max_durability)))
    else:
        durability_ratio = 1.0

    wear_penalty = 0.0 if durability_ratio >= 1.0 else (1.0 - durability_ratio) * 0.55
    wear_requirement = 0.0 if durability_ratio >= 1.0 else (1.0 - durability_ratio) * 0.45
    usable = (not profile.get("supports_durability")) or durability > 0
    return {
        "profile": profile,
        "quality": quality,
        "max_durability": max_durability,
        "durability": durability,
        "durability_ratio": durability_ratio,
        "usable": bool(usable),
        "score_bonus": float(ITEM_QUALITY_SCORE_BONUS.get(quality, 0.0)) - float(wear_penalty),
        "requirement_delta": float(ITEM_QUALITY_REQUIREMENT_DELTA.get(quality, 0.0)) + float(wear_requirement),
    }


def apply_item_durability_loss(item_id, metadata=None, amount=1, item_catalog=None):
    catalog = item_catalog or ITEM_CATALOG
    normalized = normalize_item_instance_metadata(item_id, metadata=metadata, item_catalog=catalog)
    condition = item_instance_condition(item_id, metadata=normalized, item_catalog=catalog)
    profile = condition.get("profile", {})
    loss = max(0, _int_or_default(amount, 0))
    before = max(0, _int_or_default(condition.get("durability"), 0))
    max_durability = max(0, _int_or_default(condition.get("max_durability"), 0))

    if not profile.get("supports_durability") or max_durability <= 0 or loss <= 0:
        return {
            "metadata": normalized,
            "before": before,
            "after": before,
            "lost": 0,
            "max_durability": max_durability,
            "broken": False,
        }

    after = max(0, before - loss)
    updated = dict(normalized)
    updated["item_max_durability"] = int(max_durability)
    updated["item_durability"] = int(after)
    return {
        "metadata": updated,
        "before": before,
        "after": after,
        "lost": max(0, before - after),
        "max_durability": max_durability,
        "broken": bool(before > 0 and after <= 0),
    }


def item_display_name(item_id, metadata=None, item_catalog=None):
    catalog = item_catalog or ITEM_CATALOG
    item_def = catalog.get(item_id, {})
    if isinstance(metadata, dict):
        custom = str(metadata.get("display_name", "")).strip()
        if custom:
            return custom
    base = str(item_def.get("name", item_id)).strip() or str(item_id or "item")
    condition = item_instance_condition(item_id, metadata=metadata, item_catalog=catalog)
    quality = str(condition.get("quality", "standard")).strip().lower()
    if quality and quality != "standard":
        return f"{quality.title()} {base}"
    return base


def loot_table_for_property(kind=None, archetype=None, loot_tables=None):
    loot_tables = loot_tables or LOOT_TABLES
    candidates = []
    if archetype:
        candidates.append(f"archetype:{archetype}")
    if kind:
        candidates.append(f"kind:{kind}")
    candidates.append("default")

    for key in candidates:
        if key in loot_tables:
            return key
    return "default"


def roll_loot(rng, table_key="default", count=1, loot_tables=None):
    loot_tables = loot_tables or LOOT_TABLES
    entries = loot_tables.get(table_key) or loot_tables.get("default", [])
    if not entries:
        return []

    rolls = []
    for _ in range(max(0, int(count))):
        total = sum(entry["weight"] for entry in entries)
        if total <= 0:
            break
        pick = rng.uniform(0, total)
        running = 0.0
        chosen = entries[-1]["item_id"]

        for entry in entries:
            running += entry["weight"]
            if pick <= running:
                chosen = entry["item_id"]
                break
        rolls.append(chosen)

    return rolls


ITEM_CATALOG = load_item_catalog()
LOOT_TABLES = load_loot_tables(item_catalog=ITEM_CATALOG)
