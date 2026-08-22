"""Cached compatibility presentation for inventory-style item rows.

Compatibility marks are deliberately separate from world glyphs.  A glyph says
what the object looks like on the map; a mark says what other object or slot it
fits.  The normalized profile is stored on the item definition at catalogue
load, so renderers only read prepared values.
"""

from __future__ import annotations


DRONE_CHASSIS_CLASSES = ("A", "B", "C", "D", "E")
DRONE_CLASS_BITS = {
    chassis_class: 1 << index
    for index, chassis_class in enumerate(DRONE_CHASSIS_CLASSES)
}


COMPATIBILITY_MARKS = {
    "drone.chassis": "(c",
    "drone.assembly": "(d",
    "drone.power": "(p",
    "drone.battery": "(b",
    "drone.sensor": "(s",
    "drone.weapon": "(w",
    "drone.routine": "(r",
    "drone.utility": "(u",
    "weapon.light": "<l",
    "weapon.shell": "<s",
    "weapon.rifle": "<r",
    "weapon.launcher": "<x",
    "body.base_top": "[u",
    "body.base_bottom": "[l",
    "body.hat": "[h",
    "body.earrings": "[e",
    "body.necklace": "[n",
    "body.bracelet": "[w",
    "body.ring": "[r",
    "body.top": "[t",
    "body.bottom": "[b",
    "body.full_body": "[f",
    "body.shoes": "[s",
    "body.outer": "[o",
}

COMPATIBILITY_COLORS = {
    "drone": "item_restricted",
    "weapon": "inventory_equipped_weapon",
    "body": "inventory_equipped_clothing",
}

BODY_SLOT_KEYS = {
    "base_top": "body.base_top",
    "base_bottom": "body.base_bottom",
    "hat": "body.hat",
    "earrings": "body.earrings",
    "necklace": "body.necklace",
    "bracelet": "body.bracelet",
    "ring_left": "body.ring",
    "ring_right": "body.ring",
    "top": "body.top",
    "bottom": "body.bottom",
    "full_body": "body.full_body",
    "shoes": "body.shoes",
    "outer": "body.outer",
}

DRONE_SENSOR_KINDS = frozenset({
    "alarm_probe",
    "camera",
    "ir",
    "lidar",
    "radar",
    "sonar",
})
DRONE_WEAPON_KINDS = frozenset({"flame_nozzle", "pistol"})


def _tokens(values):
    if isinstance(values, str):
        values = (values,)
    return {
        str(value or "").strip().lower()
        for value in tuple(values or ())
        if str(value or "").strip()
    }


def weapon_ammo_family(value):
    """Return the canonical ammunition family for weapon tags or a weapon row."""

    tags = value.get("tags", ()) if isinstance(value, dict) else value
    tags = _tokens(tags)
    if "melee" in tags:
        return ""
    if tags.intersection({"launcher", "explosive"}):
        return "launcher"
    if "shotgun" in tags:
        return "shell"
    if tags.intersection({"rifle", "carbine", "precision"}):
        return "rifle"
    if tags.intersection({"handgun", "smg", "burst"}):
        return "light"
    return ""


def item_ammo_family(item_def):
    """Return the ammunition family supplied by an item definition."""

    if not isinstance(item_def, dict):
        return ""
    for effect in tuple(item_def.get("effects", ()) or ()):
        if not isinstance(effect, dict) or str(effect.get("type", "")).strip().lower() != "add_ammo":
            continue
        family = weapon_ammo_family(effect.get("weapon_tags", ()))
        if family:
            return family
    return ""


def drone_class_mask(classes):
    if isinstance(classes, str):
        classes = (classes,)
    mask = 0
    for value in tuple(classes or ()):
        mask |= DRONE_CLASS_BITS.get(str(value or "").strip().upper(), 0)
    return int(mask)


def drone_class_band(mask):
    classes = [
        chassis_class
        for chassis_class in DRONE_CHASSIS_CLASSES
        if int(mask or 0) & DRONE_CLASS_BITS[chassis_class]
    ]
    if not classes:
        return ""
    indexes = [DRONE_CHASSIS_CLASSES.index(chassis_class) for chassis_class in classes]
    contiguous = indexes == list(range(indexes[0], indexes[-1] + 1))
    if len(classes) > 1 and contiguous:
        return f"{classes[0]}-{classes[-1]}"
    return "/".join(classes)


def _drone_key(profile):
    kind = str((profile or {}).get("kind", "") or "").strip().lower()
    if kind == "chassis":
        return "drone.chassis"
    if kind == "assembly":
        return "drone.assembly"
    if kind == "power_center":
        return "drone.power"
    if kind == "battery":
        return "drone.battery"
    if kind != "module":
        return ""
    module_kind = str(profile.get("module_kind", "") or "").strip().lower()
    capabilities = _tokens(profile.get("capabilities", ()))
    if module_kind.startswith("procedure_") or "procedure" in capabilities:
        return "drone.routine"
    if module_kind in DRONE_WEAPON_KINDS or capabilities.intersection({"weapon", "attack", "fire"}):
        return "drone.weapon"
    if profile.get("sensor_kind") or module_kind in DRONE_SENSOR_KINDS or capabilities.intersection({"camera", "mapping", "sensor"}):
        return "drone.sensor"
    return "drone.utility"


def _body_keys(item_def):
    keys = []
    for slot in tuple((item_def or {}).get("appearance_slots", ()) or ()):
        key = BODY_SLOT_KEYS.get(str(slot or "").strip().lower())
        if key and key not in keys:
            keys.append(key)
    return tuple(keys)


def _mark_color(keys):
    family = str((keys or ("",))[0] or "").split(".", 1)[0]
    return COMPATIBILITY_COLORS.get(family, "")


def normalize_item_compatibility(item_def, *, weapon_catalog=None):
    """Build the immutable catalogue-level compatibility presentation."""

    item_def = item_def if isinstance(item_def, dict) else {}
    keys = []
    class_mask = 0
    drone_profile = item_def.get("drone_profile") if isinstance(item_def.get("drone_profile"), dict) else {}
    drone_key = _drone_key(drone_profile)
    if drone_key:
        keys.append(drone_key)
        if drone_profile.get("kind") == "chassis":
            class_mask = drone_class_mask((drone_profile.get("chassis_class"),))
        else:
            class_mask = drone_class_mask(drone_profile.get("compatible_chassis", ()))

    weapon_id = str(item_def.get("weapon_id", "") or "").strip()
    if weapon_id and isinstance(weapon_catalog, dict):
        family = weapon_ammo_family(weapon_catalog.get(weapon_id, {}))
        if family:
            keys.append(f"weapon.{family}")
    ammo_family = item_ammo_family(item_def)
    if ammo_family:
        keys.append(f"weapon.{ammo_family}")

    keys.extend(key for key in _body_keys(item_def) if key not in keys)
    keys = tuple(dict.fromkeys(key for key in keys if key))
    marks = tuple(COMPATIBILITY_MARKS[key] for key in keys if key in COMPATIBILITY_MARKS)
    return {
        "keys": keys,
        "marks": marks,
        "mark_text": " ".join(marks),
        "mark_color": _mark_color(keys),
        "drone_class_mask": int(class_mask),
        "drone_class_band": drone_class_band(class_mask),
    }


def item_compatibility_profile(item_or_id, *, item_catalog=None):
    if isinstance(item_or_id, dict):
        item_def = item_or_id
    else:
        item_id = str(item_or_id or "").strip().lower()
        item_def = (item_catalog or {}).get(item_id, {}) if item_id else {}
    profile = item_def.get("compatibility") if isinstance(item_def, dict) else {}
    return dict(profile) if isinstance(profile, dict) else {}


def compatibility_match_state(profile, target_chassis_class=None):
    """Compare a cached item profile with one explicitly selected drone class."""

    profile = profile if isinstance(profile, dict) else {}
    class_mask = int(profile.get("drone_class_mask", 0) or 0)
    target_bit = DRONE_CLASS_BITS.get(str(target_chassis_class or "").strip().upper(), 0)
    if class_mask <= 0 or target_bit <= 0:
        return "neutral"
    return "compatible" if class_mask & target_bit else "incompatible"


def compatibility_mark_color(profile, target_chassis_class=None):
    match_state = compatibility_match_state(profile, target_chassis_class)
    if match_state == "compatible":
        return "property_service"
    if match_state == "incompatible":
        return "survival_meter_low"
    return str((profile or {}).get("mark_color", "") or "") or None


def compatibility_row_fields(item_or_id, *, item_catalog=None, target_chassis_class=None):
    profile = item_compatibility_profile(item_or_id, item_catalog=item_catalog)
    return {
        "compatibility_keys": tuple(profile.get("keys", ()) or ()),
        "compatibility_marks": tuple(profile.get("marks", ()) or ()),
        "compatibility_mark": str(profile.get("mark_text", "") or ""),
        "compatibility_color": compatibility_mark_color(profile, target_chassis_class),
        "drone_class_mask": int(profile.get("drone_class_mask", 0) or 0),
        "drone_class_band": str(profile.get("drone_class_band", "") or ""),
        "compatibility_match": compatibility_match_state(profile, target_chassis_class),
    }


def compatibility_context(sim):
    state = getattr(sim, "item_compatibility_context", None)
    if not isinstance(state, dict):
        state = {}
        sim.item_compatibility_context = state
    state.setdefault("drone_chassis_class", "")
    state.setdefault("drone_label", "")
    return state


def set_drone_compatibility_target(sim, chassis_class=None, *, label=""):
    state = compatibility_context(sim)
    normalized = str(chassis_class or "").strip().upper()
    state["drone_chassis_class"] = normalized if normalized in DRONE_CLASS_BITS else ""
    state["drone_label"] = str(label or "").strip()
    return dict(state)


def drone_compatibility_target(sim):
    state = compatibility_context(sim)
    return str(state.get("drone_chassis_class", "") or "").strip().upper()
