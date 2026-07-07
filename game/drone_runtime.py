"""Drone item/profile helpers for the staged drone foundation."""

from __future__ import annotations


DRONE_SCHEMA_VERSION = 1
DRONE_CHASSIS_CLASSES = ("A", "B", "C", "D", "E")
DRONE_PROFILE_KINDS = ("chassis", "power_center", "battery", "module", "assembly")
PACKED_DRONE_ITEM_ID = "packed_drone"
DRONE_DESTROYED_SALVAGE_ITEM_ID = "scrap_circuit"
DRONE_DEPLOY_TILE_OFFSETS = (
    (0, -1),
    (1, 0),
    (0, 1),
    (-1, 0),
    (1, -1),
    (1, 1),
    (-1, 1),
    (-1, -1),
)
DRONE_HULL_ABSORB_BY_CLASS = {
    "A": 0.10,
    "B": 0.20,
    "C": 0.34,
    "D": 0.55,
    "E": 0.70,
}
DRONE_UNARMED_ABSORB_BY_CLASS = {
    "A": 0.30,
    "B": 0.45,
    "C": 0.62,
    "D": 0.78,
    "E": 0.86,
}
DRONE_ARMOR_SHELL_ABSORB_BONUS = 0.12

DEFAULT_PACKED_DRONE_LOADOUT = {
    "chassis_item_id": "drone_chassis_c",
    "power_center_item_id": "drone_power_core_mk3",
    "battery_item_id": "drone_battery_standard",
    "modules": (
        "drone_camera_module",
        "drone_radio_module",
        "drone_remote_receiver_module",
        "drone_light_module",
    ),
}


def _clean_text(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _clean_item_id(value):
    return _clean_text(value).lower()


def _safe_int(value, default=0, *, minimum=None, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(default)
    if minimum is not None:
        number = max(int(minimum), number)
    if maximum is not None:
        number = min(int(maximum), number)
    return int(number)


def _safe_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _string_tuple(values, *, lower=True):
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)):
        return ()
    parsed = []
    for value in values:
        text = _clean_text(value)
        if not text:
            continue
        parsed.append(text.lower() if lower else text)
    return tuple(dict.fromkeys(parsed))


def _chassis_tuple(values):
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)):
        return DRONE_CHASSIS_CLASSES
    parsed = []
    for value in values:
        text = _clean_text(value).upper()
        if text in DRONE_CHASSIS_CLASSES:
            parsed.append(text)
    return tuple(dict.fromkeys(parsed)) or DRONE_CHASSIS_CLASSES


def _visible_overlay(value):
    if not isinstance(value, dict):
        return {}
    overlay = {}
    glyph = _clean_text(value.get("glyph"))
    color = _clean_text(value.get("color"))
    label = _clean_text(value.get("label"))
    if glyph:
        overlay["glyph"] = glyph[:1]
    if color:
        overlay["color"] = color
    if label:
        overlay["label"] = label
    return overlay


def normalize_drone_profile(profile=None, *, item_id=None):
    """Normalize a catalog-level drone_profile block.

    Returns an empty dict for non-drone items. Invalid profile shapes normalize
    to safe values and include an ``errors`` tuple for callers/tests that want
    to inspect the problem without crashing content load.
    """

    if not isinstance(profile, dict):
        return {}
    errors = []
    kind = _clean_text(profile.get("kind")).lower()
    if kind not in DRONE_PROFILE_KINDS:
        kind = kind or "unknown"
        errors.append(f"{_clean_item_id(item_id) or 'item'} has unknown drone profile kind {kind!r}")

    normalized = {"kind": kind}
    if kind == "chassis":
        chassis_class = _clean_text(profile.get("chassis_class")).upper()
        if chassis_class not in DRONE_CHASSIS_CLASSES:
            errors.append("chassis profile requires chassis_class A-E")
            chassis_class = chassis_class if chassis_class else ""
        normalized.update({
            "chassis_class": chassis_class,
            "slot_limit": _safe_int(profile.get("slot_limit"), 1, minimum=1),
            "weight_limit": _safe_int(profile.get("weight_limit"), 1, minimum=1),
            "base_hp": _safe_int(profile.get("base_hp"), 1, minimum=1),
            "base_range": _safe_int(profile.get("base_range"), 1, minimum=1),
            "base_glyph": (_clean_text(profile.get("base_glyph"), "d") or "d")[:1],
            "base_color": _clean_text(profile.get("base_color"), "item_restricted"),
        })
    elif kind == "power_center":
        normalized.update({
            "mark": _safe_int(profile.get("mark"), 1, minimum=1),
            "power_output": _safe_int(profile.get("power_output"), 1, minimum=1),
            "idle_overhead": _safe_int(profile.get("idle_overhead"), 0, minimum=0),
            "compatible_chassis": _chassis_tuple(profile.get("compatible_chassis")),
        })
    elif kind == "battery":
        normalized.update({
            "charge_max": _safe_int(profile.get("charge_max"), 1, minimum=1),
            "weight": _safe_int(profile.get("weight"), 0, minimum=0),
            "disposable": _safe_bool(profile.get("disposable"), default=True),
            "compatible_chassis": _chassis_tuple(profile.get("compatible_chassis")),
        })
    elif kind == "module":
        module_kind = _clean_text(profile.get("module_kind")).lower()
        if not module_kind:
            errors.append("module profile requires module_kind")
        active_draw = _safe_int(profile.get("active_draw"), 0, minimum=0)
        normalized.update({
            "module_kind": module_kind,
            "slot_cost": _safe_int(profile.get("slot_cost"), 1, minimum=1),
            "weight": _safe_int(profile.get("weight"), 0, minimum=0),
            "standby_draw": _safe_int(profile.get("standby_draw"), 0, minimum=0),
            "active_draw": active_draw,
            "capabilities": _string_tuple(profile.get("capabilities")),
            "visible_overlay": _visible_overlay(profile.get("visible_overlay")),
            "compatible_chassis": _chassis_tuple(profile.get("compatible_chassis")),
            "sensor_kind": _clean_text(profile.get("sensor_kind")).lower(),
            "sensor_range": _safe_int(profile.get("sensor_range"), 0, minimum=0),
            "sensor_power_cost": _safe_int(profile.get("sensor_power_cost"), active_draw, minimum=0),
            "sensor_occlusion_depth": _safe_int(profile.get("sensor_occlusion_depth"), 0, minimum=0),
        })
    elif kind == "assembly":
        normalized.update({
            "packed": True,
        })

    if errors:
        normalized["errors"] = tuple(errors)
    return normalized


def _catalog(item_catalog=None):
    if item_catalog is not None:
        return item_catalog
    from game.items import ITEM_CATALOG  # Local import avoids an items.py cycle.

    return ITEM_CATALOG


def drone_profile_for_item(item_id, item_catalog=None):
    item_key = _clean_item_id(item_id)
    if not item_key:
        return {}
    item_def = _catalog(item_catalog).get(item_key, {})
    profile = item_def.get("drone_profile") if isinstance(item_def, dict) else {}
    return dict(profile) if isinstance(profile, dict) else {}


def is_drone_item(item_id, item_catalog=None):
    return bool(drone_profile_for_item(item_id, item_catalog=item_catalog).get("kind"))


def is_packed_drone_entry(entry, item_catalog=None):
    if not isinstance(entry, dict):
        return False
    item_id = _clean_item_id(entry.get("item_id"))
    if item_id == PACKED_DRONE_ITEM_ID:
        return True
    return drone_profile_for_item(item_id, item_catalog=item_catalog).get("kind") == "assembly"


def _normalize_module_entry(entry):
    if isinstance(entry, str):
        item_id = _clean_item_id(entry)
        return {"item_id": item_id} if item_id else None
    if not isinstance(entry, dict):
        return None
    item_id = _clean_item_id(entry.get("item_id") or entry.get("module_item_id"))
    if not item_id:
        return None
    normalized = dict(entry)
    normalized["item_id"] = item_id
    normalized.pop("module_item_id", None)
    if "condition" in normalized:
        normalized["condition"] = _clean_text(normalized.get("condition")).lower()
    if isinstance(normalized.get("metadata"), dict):
        normalized["metadata"] = dict(normalized["metadata"])
    return normalized


def _normalize_cargo_entry(entry):
    if isinstance(entry, dict):
        return dict(entry)
    item_id = _clean_item_id(entry)
    return {"item_id": item_id} if item_id else None


def _has_explicit_loadout(metadata):
    return any(
        key in metadata
        for key in (
            "chassis_item_id",
            "chassis_id",
            "power_center_item_id",
            "power_core_item_id",
            "battery_item_id",
            "modules",
        )
    )


def _battery_charge_max(battery_item_id, item_catalog=None):
    profile = drone_profile_for_item(battery_item_id, item_catalog=item_catalog)
    if profile.get("kind") != "battery":
        return 0
    return _safe_int(profile.get("charge_max"), 0, minimum=0)


def _chassis_class_for_item(chassis_item_id, item_catalog=None):
    profile = drone_profile_for_item(chassis_item_id, item_catalog=item_catalog)
    if profile.get("kind") != "chassis":
        return ""
    return _clean_text(profile.get("chassis_class")).upper()


def _chassis_base_hp(chassis_item_id, item_catalog=None):
    profile = drone_profile_for_item(chassis_item_id, item_catalog=item_catalog)
    if profile.get("kind") != "chassis":
        return 0
    return _safe_int(profile.get("base_hp"), 0, minimum=0)


def normalize_packed_drone_metadata(metadata=None, *, item_catalog=None):
    """Normalize inventory metadata for a packed drone assembly.

    Unknown metadata keys are preserved. A completely blank loadout becomes the
    default C-class starter; a partial explicit loadout keeps missing fields
    missing so drone_loadout_summary can report useful errors.
    """

    source = dict(metadata or {})
    explicit = _has_explicit_loadout(source)
    defaults = {} if explicit else dict(DEFAULT_PACKED_DRONE_LOADOUT)
    normalized = dict(source)
    normalized["drone_schema_version"] = DRONE_SCHEMA_VERSION

    chassis_item_id = _clean_item_id(
        source.get("chassis_item_id")
        or source.get("chassis_id")
        or defaults.get("chassis_item_id")
    )
    power_center_item_id = _clean_item_id(
        source.get("power_center_item_id")
        or source.get("power_core_item_id")
        or defaults.get("power_center_item_id")
    )
    battery_item_id = _clean_item_id(
        source.get("battery_item_id")
        or defaults.get("battery_item_id")
    )

    normalized["chassis_item_id"] = chassis_item_id
    normalized["power_center_item_id"] = power_center_item_id
    normalized["battery_item_id"] = battery_item_id
    normalized.pop("chassis_id", None)
    normalized.pop("power_core_item_id", None)

    raw_modules = source.get("modules", defaults.get("modules", ()))
    modules = []
    if isinstance(raw_modules, (list, tuple)):
        for entry in raw_modules:
            module = _normalize_module_entry(entry)
            if module:
                modules.append(module)
    normalized["modules"] = modules

    raw_cargo = source.get("cargo", ())
    cargo = []
    if isinstance(raw_cargo, (list, tuple)):
        for entry in raw_cargo:
            cargo_entry = _normalize_cargo_entry(entry)
            if cargo_entry:
                cargo.append(cargo_entry)
    normalized["cargo"] = cargo

    paint = source.get("paint") if isinstance(source.get("paint"), dict) else {}
    secondary_color = _clean_text(paint.get("secondary_color") or paint.get("accent_color"), "blue")
    normalized["paint"] = {
        "primary_color": _clean_text(paint.get("primary_color"), "steel"),
        "secondary_color": secondary_color,
        "accent_color": secondary_color,
    }

    charge_max = _battery_charge_max(battery_item_id, item_catalog=item_catalog)
    if "battery_charge" in source:
        charge = _safe_int(source.get("battery_charge"), charge_max, minimum=0)
        if charge_max > 0:
            charge = min(charge, charge_max)
    else:
        charge = charge_max
    normalized["battery_charge"] = int(charge)
    normalized["battery_charge_max"] = int(charge_max)

    base_hp = _chassis_base_hp(chassis_item_id, item_catalog=item_catalog)
    hull_max_default = base_hp if base_hp > 0 else _safe_int(source.get("hull_hp_max"), 1, minimum=1)
    hull_max = _safe_int(source.get("hull_hp_max"), hull_max_default, minimum=1)
    if base_hp > 0:
        hull_max = min(hull_max, base_hp)
    hull_hp = _safe_int(source.get("hull_hp"), hull_max, minimum=0)
    hull_hp = min(hull_hp, hull_max)
    normalized["hull_hp"] = int(hull_hp)
    normalized["hull_hp_max"] = int(hull_max)

    chassis_class = _chassis_class_for_item(chassis_item_id, item_catalog=item_catalog)
    if chassis_class:
        normalized["chassis_class"] = chassis_class
    else:
        normalized["chassis_class"] = _clean_text(source.get("chassis_class")).upper()

    if not _clean_text(normalized.get("display_name")):
        if normalized.get("chassis_class") in DRONE_CHASSIS_CLASSES:
            normalized["display_name"] = f"Packed {normalized['chassis_class']}-Class Drone"
        else:
            normalized["display_name"] = "Packed Drone"
    return normalized


def _compatible(profile, chassis_class):
    if not chassis_class:
        return True
    compatible = profile.get("compatible_chassis")
    if not compatible:
        return True
    return _clean_text(chassis_class).upper() in {
        _clean_text(item).upper()
        for item in compatible
        if _clean_text(item)
    }


def drone_loadout_summary(metadata=None, *, item_catalog=None):
    catalog = _catalog(item_catalog)
    normalized = normalize_packed_drone_metadata(metadata, item_catalog=catalog)
    errors = []

    chassis_item_id = _clean_item_id(normalized.get("chassis_item_id"))
    power_center_item_id = _clean_item_id(normalized.get("power_center_item_id"))
    battery_item_id = _clean_item_id(normalized.get("battery_item_id"))

    chassis = drone_profile_for_item(chassis_item_id, item_catalog=catalog)
    if not chassis_item_id:
        errors.append("missing chassis")
    elif chassis.get("kind") != "chassis":
        errors.append(f"{chassis_item_id} is not a drone chassis")

    chassis_class = _clean_text(chassis.get("chassis_class") or normalized.get("chassis_class")).upper()
    slot_limit = _safe_int(chassis.get("slot_limit"), 0, minimum=0)
    weight_limit = _safe_int(chassis.get("weight_limit"), 0, minimum=0)

    power = drone_profile_for_item(power_center_item_id, item_catalog=catalog)
    if not power_center_item_id:
        errors.append("missing power center")
    elif power.get("kind") != "power_center":
        errors.append(f"{power_center_item_id} is not a drone power center")
    elif not _compatible(power, chassis_class):
        errors.append(f"{power_center_item_id} is incompatible with chassis {chassis_class or '?'}")

    battery = drone_profile_for_item(battery_item_id, item_catalog=catalog)
    if not battery_item_id:
        errors.append("missing battery")
    elif battery.get("kind") != "battery":
        errors.append(f"{battery_item_id} is not a drone battery")
    elif not _compatible(battery, chassis_class):
        errors.append(f"{battery_item_id} is incompatible with chassis {chassis_class or '?'}")

    power_output = _safe_int(power.get("power_output"), 0, minimum=0)
    idle_overhead = _safe_int(power.get("idle_overhead"), 0, minimum=0)
    slot_used = 0
    weight_used = _safe_int(battery.get("weight"), 0, minimum=0)
    standby_draw = idle_overhead
    active_draw = idle_overhead
    capabilities = []

    module_rows = []
    for module in normalized.get("modules", ()):
        if not isinstance(module, dict):
            continue
        module_item_id = _clean_item_id(module.get("item_id"))
        profile = drone_profile_for_item(module_item_id, item_catalog=catalog)
        module_rows.append({"item_id": module_item_id, "profile": profile})
        if not module_item_id:
            errors.append("module entry is missing item_id")
            continue
        if profile.get("kind") != "module":
            errors.append(f"{module_item_id} is not a drone module")
            continue
        if not _compatible(profile, chassis_class):
            errors.append(f"{module_item_id} is incompatible with chassis {chassis_class or '?'}")
        slot_used += _safe_int(profile.get("slot_cost"), 0, minimum=0)
        weight_used += _safe_int(profile.get("weight"), 0, minimum=0)
        standby_draw += _safe_int(profile.get("standby_draw"), 0, minimum=0)
        active_draw += _safe_int(profile.get("active_draw"), 0, minimum=0)
        capabilities.extend(profile.get("capabilities", ()) or ())

    if slot_limit > 0 and slot_used > slot_limit:
        errors.append(f"module slots {slot_used}/{slot_limit} exceed chassis limit")
    if weight_limit > 0 and weight_used > weight_limit:
        errors.append(f"loadout weight {weight_used}/{weight_limit} exceeds chassis limit")
    if power_output > 0 and standby_draw > power_output:
        errors.append(f"standby draw {standby_draw}/{power_output} exceeds power output")
    if power_output > 0 and active_draw > power_output:
        errors.append(f"active draw {active_draw}/{power_output} exceeds power output")

    charge_max = _safe_int(battery.get("charge_max"), normalized.get("battery_charge_max", 0), minimum=0)
    charge = _safe_int(normalized.get("battery_charge"), charge_max, minimum=0)
    if charge_max > 0:
        charge = min(charge, charge_max)

    return {
        "metadata": normalized,
        "errors": tuple(errors),
        "chassis_class": chassis_class,
        "slot_limit": int(slot_limit),
        "slot_used": int(slot_used),
        "weight_limit": int(weight_limit),
        "weight_used": int(weight_used),
        "power_output": int(power_output),
        "standby_draw": int(standby_draw),
        "active_draw": int(active_draw),
        "battery_charge": int(charge),
        "battery_charge_max": int(charge_max),
        "hull_hp": int(normalized.get("hull_hp", 0) or 0),
        "hull_hp_max": int(normalized.get("hull_hp_max", 0) or 0),
        "capabilities": tuple(dict.fromkeys(capabilities)),
        "modules": tuple(module_rows),
    }


def drone_state_capabilities(state, *, item_catalog=None):
    metadata = packed_drone_metadata_from_state(state, item_catalog=item_catalog)
    summary = drone_loadout_summary(metadata, item_catalog=item_catalog)
    return tuple(str(capability or "").strip().lower() for capability in summary.get("capabilities", ()) if str(capability or "").strip())


def drone_state_has_capability(state, capability, *, item_catalog=None):
    needle = _clean_text(capability).lower()
    if not needle:
        return False
    return needle in set(drone_state_capabilities(state, item_catalog=item_catalog))


def drone_hull_damage_absorb(state, *, weapon_id="", damage_kind=""):
    if state is None:
        return 0.0
    kind = _clean_text(damage_kind).lower()
    if any(token in kind for token in ("emp", "electric", "shock")):
        return 0.0
    chassis_class = _clean_text(getattr(state, "chassis_class", "")).upper()
    absorb = float(DRONE_HULL_ABSORB_BY_CLASS.get(chassis_class, 0.0))
    if _clean_text(weapon_id).lower() == "unarmed" and "melee" in kind:
        absorb = max(absorb, float(DRONE_UNARMED_ABSORB_BY_CLASS.get(chassis_class, absorb)))
    modules = tuple(getattr(state, "modules", ()) or ())
    if any(
        isinstance(module, dict)
        and _clean_item_id(module.get("item_id") or module.get("module_item_id")) == "drone_armor_shell_module"
        for module in modules
    ):
        absorb += DRONE_ARMOR_SHELL_ABSORB_BONUS
    return max(0.0, min(0.88, absorb))


def validate_packed_drone_deploy_entry(entry, *, item_catalog=None):
    """Return normalized deploy data for a packed drone inventory entry."""

    errors = []
    if not is_packed_drone_entry(entry, item_catalog=item_catalog):
        errors.append("item is not a packed drone")
        return {
            "ok": False,
            "item_id": _clean_item_id((entry or {}).get("item_id") if isinstance(entry, dict) else ""),
            "instance_id": None,
            "metadata": {},
            "summary": {},
            "errors": tuple(errors),
        }

    item_id = _clean_item_id(entry.get("item_id")) or PACKED_DRONE_ITEM_ID
    instance_id = _clean_text(entry.get("instance_id"))
    if not instance_id:
        errors.append("packed drone is missing an instance id")
    metadata = normalize_packed_drone_metadata(entry.get("metadata"), item_catalog=item_catalog)
    summary = drone_loadout_summary(metadata, item_catalog=item_catalog)
    errors.extend(str(error) for error in summary.get("errors", ()) if str(error).strip())
    return {
        "ok": not errors,
        "item_id": item_id,
        "instance_id": instance_id or None,
        "metadata": metadata,
        "summary": summary,
        "errors": tuple(errors),
    }


def packed_drone_metadata_from_state(state, *, item_catalog=None):
    """Rebuild packed-drone inventory metadata from a deployed DroneState-like object."""

    metadata = dict(getattr(state, "source_metadata", {}) or {})
    for key, attr in (
        ("chassis_item_id", "chassis_item_id"),
        ("power_center_item_id", "power_center_item_id"),
        ("battery_item_id", "battery_item_id"),
        ("chassis_class", "chassis_class"),
        ("battery_charge", "battery_charge"),
        ("battery_charge_max", "battery_charge_max"),
        ("hull_hp", "hull_hp"),
        ("hull_hp_max", "hull_hp_max"),
        ("owner_eid", "owner_eid"),
        ("owner_tag", "owner_tag"),
        ("controller_eid", "controller_eid"),
        ("controller_tag", "controller_tag"),
        ("faction_id", "faction_id"),
        ("legal_owner_tag", "legal_owner_tag"),
        ("procedure_key", "procedure_key"),
        ("last_command", "last_command"),
        ("target_eid", "target_eid"),
    ):
        value = getattr(state, attr, None)
        if value is not None:
            metadata[key] = value
    metadata["modules"] = [
        dict(module)
        for module in (getattr(state, "modules", None) or ())
        if isinstance(module, dict)
    ]
    metadata["cargo"] = [
        dict(entry)
        for entry in (getattr(state, "cargo", None) or ())
        if isinstance(entry, dict)
    ]
    metadata["paint"] = dict(getattr(state, "paint", {}) or {})
    metadata["mode"] = "packed"
    metadata["source_item_instance_id"] = getattr(state, "source_item_instance_id", None)
    target = getattr(state, "target", None)
    if isinstance(target, (list, tuple)):
        metadata["target"] = tuple(target)
    else:
        metadata.pop("target", None)
    metadata.pop("deployed_entity_id", None)
    return normalize_packed_drone_metadata(metadata, item_catalog=item_catalog)


def deployed_drone_render_spec(metadata=None, *, item_catalog=None):
    summary = drone_loadout_summary(metadata, item_catalog=item_catalog)
    chassis_item_id = _clean_item_id(summary.get("metadata", {}).get("chassis_item_id"))
    profile = drone_profile_for_item(chassis_item_id, item_catalog=item_catalog)
    return {
        "glyph": (_clean_text(profile.get("base_glyph"), "d") or "d")[:1],
        "color": _clean_text(profile.get("base_color"), "item_restricted"),
        "chassis_class": _clean_text(summary.get("chassis_class") or summary.get("metadata", {}).get("chassis_class")).upper(),
        "errors": tuple(summary.get("errors", ())),
    }


def deployed_drone_common_name(metadata=None, *, item_catalog=None):
    spec = deployed_drone_render_spec(metadata, item_catalog=item_catalog)
    chassis_class = _clean_text(spec.get("chassis_class")).upper()
    if chassis_class in DRONE_CHASSIS_CLASSES:
        return f"{chassis_class}-class drone"
    return "deployed drone"


def _component_bucket(sim, component_type=None, component_name=""):
    ecs = getattr(sim, "ecs", None)
    if ecs is None:
        return {}
    if component_type is not None:
        return ecs.get(component_type)
    components = getattr(ecs, "components", {})
    if not isinstance(components, dict):
        return {}
    for candidate_type, bucket in components.items():
        if str(getattr(candidate_type, "__name__", "") or "") == component_name:
            return bucket if isinstance(bucket, dict) else {}
    return {}


def _entity_bucket_at(sim, x, y, z):
    tilemap = getattr(sim, "tilemap", None)
    entities_at = getattr(tilemap, "entities_at", None)
    if not callable(entities_at):
        return set()
    return set(entities_at(int(x), int(y), int(z)) or ())


def drone_deploy_tile_open(sim, x, y, z=0):
    tilemap = getattr(sim, "tilemap", None)
    if tilemap is None or not bool(tilemap.is_walkable(int(x), int(y), int(z))):
        return False
    if _entity_bucket_at(sim, x, y, z):
        return False
    ground_items_at = getattr(sim, "ground_items_at", None)
    if callable(ground_items_at) and ground_items_at(int(x), int(y), z=int(z)):
        return False
    return True


def drone_deploy_tile_is_threshold(sim, x, y, z=0):
    tilemap = getattr(sim, "tilemap", None)
    tile_at = getattr(tilemap, "tile_at", None)
    tile = tile_at(int(x), int(y), int(z)) if callable(tile_at) else None
    if tile is None:
        return False
    semantic = _clean_text(getattr(tile, "semantic_id", "")).lower()
    glyph = _clean_text(getattr(tile, "glyph", ""))
    if "door" in semantic or "threshold" in semantic:
        return True
    door_state_at = getattr(sim, "door_state_at", None)
    door_state = door_state_at(int(x), int(y), int(z)) if callable(door_state_at) else None
    if isinstance(door_state, dict):
        kind = _clean_text(door_state.get("kind"), "door").lower()
        if kind in {"door", "side_door", "service_door", "employee_door"}:
            return True
    return glyph in {"+", "'"}


def first_open_drone_deploy_tile(sim, x, y, z=0):
    threshold_fallback = None
    for dx, dy in DRONE_DEPLOY_TILE_OFFSETS:
        nx = int(x) + int(dx)
        ny = int(y) + int(dy)
        if drone_deploy_tile_open(sim, nx, ny, z):
            candidate = (nx, ny, int(z))
            if drone_deploy_tile_is_threshold(sim, nx, ny, z):
                if threshold_fallback is None:
                    threshold_fallback = candidate
                continue
            return candidate
    return threshold_fallback


def _same_entity_id(left, right):
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return left == right


def _drone_controlled_by_actor(state, actor_eid):
    return (
        _same_entity_id(getattr(state, "owner_eid", None), actor_eid)
        or _same_entity_id(getattr(state, "controller_eid", None), actor_eid)
    )


def drone_state_controlled_by_actor(state, actor_eid):
    return _drone_controlled_by_actor(state, actor_eid)


def find_deployed_drone_for_pickup(
    sim,
    actor_eid,
    x,
    y,
    z=0,
    *,
    radius=1,
    drone_state_type=None,
    position_type=None,
):
    states = _component_bucket(sim, drone_state_type, "DroneState")
    positions = _component_bucket(sim, position_type, "Position")
    matches = []
    for eid, state in states.items():
        if str(getattr(state, "mode", "") or "").strip().lower() != "deployed":
            continue
        if not _drone_controlled_by_actor(state, actor_eid):
            continue
        pos = positions.get(eid)
        if pos is None:
            continue
        try:
            px = int(pos.x)
            py = int(pos.y)
            pz = int(pos.z)
        except (TypeError, ValueError):
            continue
        distance = abs(px - int(x)) + abs(py - int(y))
        if pz == int(z) and distance <= int(radius):
            matches.append((distance, int(eid), eid, state, pos))
    if not matches:
        return None
    _distance, _sort_eid, eid, state, pos = sorted(matches, key=lambda row: (row[0], row[1]))[0]
    return {
        "eid": eid,
        "state": state,
        "position": pos,
    }


def _drop_entry_from_module(module):
    if not isinstance(module, dict):
        return None
    item_id = _clean_item_id(module.get("item_id") or module.get("module_item_id"))
    if not item_id:
        return None
    metadata = dict(module.get("metadata") or {}) if isinstance(module.get("metadata"), dict) else {}
    for key, value in module.items():
        if key in {"item_id", "module_item_id", "metadata"}:
            continue
        if key not in metadata:
            metadata[key] = value
    metadata.setdefault("source_context", "drone_destroyed")
    return {
        "item_id": item_id,
        "quantity": 1,
        "metadata": metadata,
        "drop_kind": "module",
    }


def _drop_entry_from_cargo(cargo):
    if not isinstance(cargo, dict):
        item_id = _clean_item_id(cargo)
        return {"item_id": item_id, "quantity": 1, "metadata": {}, "drop_kind": "cargo"} if item_id else None
    item_id = _clean_item_id(cargo.get("item_id"))
    if not item_id:
        return None
    quantity = _safe_int(cargo.get("quantity"), 1, minimum=1)
    metadata = dict(cargo.get("metadata") or {}) if isinstance(cargo.get("metadata"), dict) else {}
    metadata.setdefault("source_context", "drone_destroyed")
    return {
        "item_id": item_id,
        "quantity": int(quantity),
        "metadata": metadata,
        "drop_kind": "cargo",
    }


def _drop_entry_from_physical_part(state, item_id, drop_kind, *, metadata=None):
    item_id = _clean_item_id(item_id)
    if not item_id:
        return None
    drop_kind = _clean_text(drop_kind, "drone_part").lower()
    entry_metadata = dict(metadata or {})
    entry_metadata.setdefault("source_context", "drone_destroyed")
    entry_metadata.setdefault("drop_kind", drop_kind)
    chassis_class = _clean_text(getattr(state, "chassis_class", "")).upper()
    if chassis_class:
        entry_metadata.setdefault("chassis_class", chassis_class)
    source_instance_id = _clean_text(getattr(state, "source_item_instance_id", ""))
    if source_instance_id:
        entry_metadata.setdefault("source_item_instance_id", source_instance_id)
    return {
        "item_id": item_id,
        "quantity": 1,
        "metadata": entry_metadata,
        "drop_kind": drop_kind,
    }


def _stable_score(*parts):
    token = "|".join(str(part) for part in parts)
    total = 0
    for idx, char in enumerate(token):
        total += (idx + 1) * ord(char)
    return total


def _destroyed_candidate_count(state, candidate_count, *, damage_amount=None, overkill_amount=0, damage_kind=""):
    candidate_count = _safe_int(candidate_count, 0, minimum=0)
    if candidate_count <= 0:
        return 0

    kind = _clean_text(damage_kind).lower()
    if any(token in kind for token in ("emp", "electrical", "shock", "stun", "disable")):
        return 1

    hull_hp_max = _safe_int(getattr(state, "hull_hp_max", 1), 1, minimum=1)
    damage_amount = _safe_int(damage_amount, hull_hp_max, minimum=0)
    overkill_amount = _safe_int(overkill_amount, 0, minimum=0)
    overkill_step = max(1, (hull_hp_max + 2) // 3)
    count = 1 + (overkill_amount // overkill_step)
    if any(token in kind for token in ("explosion", "explosive", "blast", "fire", "flame")):
        count += 1
    elif any(token in kind for token in ("crush", "vehicle", "impact")) and damage_amount >= max(1, hull_hp_max // 2):
        count += 1
    return min(candidate_count, max(1, int(count)))


def _destroyed_candidate_indexes(state, candidates, *, damage_amount=None, overkill_amount=0, damage_kind=""):
    count = _destroyed_candidate_count(
        state,
        len(candidates),
        damage_amount=damage_amount,
        overkill_amount=overkill_amount,
        damage_kind=damage_kind,
    )
    if count <= 0:
        return set()
    source_instance_id = _clean_text(getattr(state, "source_item_instance_id", ""))
    scored = []
    for idx, entry in enumerate(tuple(candidates or ())):
        scored.append((
            _stable_score(
                source_instance_id,
                getattr(state, "chassis_item_id", ""),
                getattr(state, "power_center_item_id", ""),
                getattr(state, "battery_item_id", ""),
                entry.get("item_id"),
                entry.get("drop_kind"),
                idx,
                damage_amount,
                overkill_amount,
                damage_kind,
            ),
            idx,
        ))
    scored.sort()
    return {idx for _score, idx in scored[:count]}


def drone_destroyed_drop_resolution(state, *, damage_amount=None, overkill_amount=0, damage_kind=""):
    candidates = []
    for cargo in tuple(getattr(state, "cargo", ()) or ()):
        entry = _drop_entry_from_cargo(cargo)
        if entry:
            candidates.append(entry)

    for item_id, drop_kind, metadata in (
        (getattr(state, "chassis_item_id", None), "chassis", {}),
        (getattr(state, "power_center_item_id", None), "power_center", {}),
        (
            getattr(state, "battery_item_id", None),
            "battery",
            {
                "battery_charge": int(max(0, _safe_int(getattr(state, "battery_charge", 0), 0))),
                "battery_charge_max": int(max(0, _safe_int(getattr(state, "battery_charge_max", 0), 0))),
            },
        ),
    ):
        entry = _drop_entry_from_physical_part(state, item_id, drop_kind, metadata=metadata)
        if entry:
            candidates.append(entry)
    for module in tuple(getattr(state, "modules", ()) or ()):
        entry = _drop_entry_from_module(module)
        if entry:
            candidates.append(entry)

    drops = []
    destroyed_items = []
    destroyed_indexes = _destroyed_candidate_indexes(
        state,
        candidates,
        damage_amount=damage_amount,
        overkill_amount=overkill_amount,
        damage_kind=damage_kind,
    )
    for idx, entry in enumerate(candidates):
        if idx in destroyed_indexes:
            destroyed_items.append(dict(entry))
            continue
        drops.append(entry)

    salvage_metadata = {
        "source_context": "drone_destroyed",
        "drop_kind": "debris_salvage",
    }
    chassis_class = _clean_text(getattr(state, "chassis_class", "")).upper()
    if chassis_class:
        salvage_metadata["chassis_class"] = chassis_class
    source_instance_id = _clean_text(getattr(state, "source_item_instance_id", ""))
    if source_instance_id:
        salvage_metadata["source_item_instance_id"] = source_instance_id
    drops.append({
        "item_id": DRONE_DESTROYED_SALVAGE_ITEM_ID,
        "quantity": 1,
        "metadata": salvage_metadata,
        "drop_kind": "debris_salvage",
    })
    return {
        "drops": tuple(drops),
        "destroyed_items": tuple(destroyed_items),
    }


def drone_destroyed_drop_entries(state):
    return tuple(drone_destroyed_drop_resolution(state).get("drops", ()))
