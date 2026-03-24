import json
from pathlib import Path

WEAPONS_PATH = Path(__file__).resolve().parent / "weapons.json"

DEFAULT_WEAPON = {
    "id": "unarmed",
    "name": "Unarmed",
    "glyph": "!",
    "projectile_glyph": ".",
    "trajectory": "ballistic",
    "speed": 1.0,
    "range": 1,
    "pellets": 1,
    "spread": 0,
    "base_damage": 4,
    "cooldown_ticks": 2,
    "noise_radius": 3,
    "explosion_radius": 0,
    "aoe_falloff": 0.0,
    "cover_penetration": 0.0,
    "tags": ["melee"],
    "named_prefixes": [],
    "named_suffixes": [],
}


def _num(value, default, cast=float):
    try:
        return cast(value)
    except (TypeError, ValueError):
        return default


def _normalize_weapon(raw):
    if not isinstance(raw, dict):
        return None

    wid = str(raw.get("id", "")).strip()
    if not wid:
        return None

    name = str(raw.get("name", wid))
    glyph = str(raw.get("glyph", "!"))[:1] or "!"
    projectile_glyph = str(raw.get("projectile_glyph", "."))[:1] or "."

    trajectory = str(raw.get("trajectory", "ballistic")).lower()
    if trajectory not in {"ballistic", "lobbed", "beam"}:
        trajectory = "ballistic"

    speed = max(0.1, _num(raw.get("speed"), DEFAULT_WEAPON["speed"], float))
    range_ = max(1, _num(raw.get("range"), DEFAULT_WEAPON["range"], int))
    pellets = max(1, _num(raw.get("pellets"), DEFAULT_WEAPON["pellets"], int))
    spread = max(0, _num(raw.get("spread"), DEFAULT_WEAPON["spread"], int))
    base_damage = max(1, _num(raw.get("base_damage"), DEFAULT_WEAPON["base_damage"], int))
    cooldown_ticks = max(1, _num(raw.get("cooldown_ticks"), DEFAULT_WEAPON["cooldown_ticks"], int))
    noise_radius = max(1, _num(raw.get("noise_radius"), DEFAULT_WEAPON["noise_radius"], int))
    explosion_radius = max(0, _num(raw.get("explosion_radius"), DEFAULT_WEAPON["explosion_radius"], int))
    aoe_falloff = max(0.0, min(1.0, _num(raw.get("aoe_falloff"), DEFAULT_WEAPON["aoe_falloff"], float)))
    cover_penetration = max(0.0, min(1.0, _num(raw.get("cover_penetration"), DEFAULT_WEAPON["cover_penetration"], float)))
    tags = [str(tag).strip() for tag in raw.get("tags", []) if str(tag).strip()]

    named_prefixes = [
        str(prefix).strip()
        for prefix in raw.get("named_prefixes", [])
        if str(prefix).strip()
    ]
    named_suffixes = [
        str(suffix).strip()
        for suffix in raw.get("named_suffixes", [])
        if str(suffix).strip()
    ]

    return {
        "id": wid,
        "name": name,
        "glyph": glyph,
        "projectile_glyph": projectile_glyph,
        "trajectory": trajectory,
        "speed": speed,
        "range": range_,
        "pellets": pellets,
        "spread": spread,
        "base_damage": base_damage,
        "cooldown_ticks": cooldown_ticks,
        "noise_radius": noise_radius,
        "explosion_radius": explosion_radius,
        "aoe_falloff": aoe_falloff,
        "cover_penetration": cover_penetration,
        "tags": tags,
        "named_prefixes": named_prefixes,
        "named_suffixes": named_suffixes,
    }


def load_weapon_catalog(path=WEAPONS_PATH):
    catalog = {}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        raw = []

    if isinstance(raw, list):
        for row in raw:
            weapon = _normalize_weapon(row)
            if not weapon:
                continue
            catalog[weapon["id"]] = weapon

    if not catalog:
        catalog[DEFAULT_WEAPON["id"]] = dict(DEFAULT_WEAPON)
    return catalog


WEAPON_CATALOG = load_weapon_catalog()


def weapon_by_id(weapon_id):
    return WEAPON_CATALOG.get(weapon_id, DEFAULT_WEAPON)


def roll_weapon_instance(rng, weapon_id, named_chance=0.16):
    weapon = weapon_by_id(weapon_id)
    instance = {
        "weapon_id": weapon["id"],
        "custom_name": weapon["name"],
        "damage_mult": 1.0,
        "spread_mod": 0,
        "cooldown_mod": 0,
    }

    try:
        chance = float(named_chance)
    except (TypeError, ValueError):
        chance = 0.16
    chance = max(0.0, min(1.0, chance))

    if rng.random() > chance:
        return instance

    prefixes = weapon.get("named_prefixes", [])
    suffixes = weapon.get("named_suffixes", [])
    if not prefixes and not suffixes:
        return instance

    parts = []
    if prefixes:
        parts.append(rng.choice(prefixes))
    parts.append(weapon["name"])
    if suffixes:
        parts.append(rng.choice(suffixes))
    instance["custom_name"] = " ".join(parts)

    damage_boost = (rng.random() * 0.28) - 0.04
    instance["damage_mult"] = max(0.85, min(1.42, 1.0 + damage_boost))
    instance["spread_mod"] = rng.choice([-1, 0, 0, 1])
    instance["cooldown_mod"] = rng.choice([0, 0, 0, -1, 1])
    return instance
