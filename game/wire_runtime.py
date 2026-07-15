"""Wire kit item/profile helpers for the staged hacking foundation."""

from __future__ import annotations

from collections.abc import Mapping


WIRE_SCHEMA_VERSION = 1
WIRE_DATA_SCHEMA_VERSION = 1
WIRE_PROFILE_KINDS = (
    "program",
    "data_packet",
    "credential",
    "license",
    "backup",
    "trace",
    "corrupted_file",
)
WIRE_QUALITY_TIERS = ("poor", "standard", "good", "excellent")
WIRE_INTERFACE_SCHEMA_VERSION = 1
WIRE_INTERFACE_KINDS = (
    "deck",
    "wetwire",
    "skin_rig",
    "interface_cable",
    "service_dongle",
    "drone_bridge",
)
WIRE_TARGET_CLASSES = (
    "access_panel",
    "service_terminal",
    "drone_radio",
    "generic_wire",
)


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


def _safe_float(value, default=0.0, *, minimum=None, maximum=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if minimum is not None:
        number = max(float(minimum), number)
    if maximum is not None:
        number = min(float(maximum), number)
    return float(number)


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


def _quality(value, default="standard"):
    text = _clean_text(value, default).lower()
    return text if text in WIRE_QUALITY_TIERS else default


def normalize_wire_profile(profile=None, *, item_id=None):
    """Normalize a catalog-level wire_profile block.

    Non-wire items return an empty dict. Invalid wire profile shapes normalize
    into safe inert data with an ``errors`` tuple so content load can report the
    problem without making the game unbootable.
    """

    if not isinstance(profile, dict):
        return {}
    errors = []
    item_key = _clean_item_id(item_id) or "item"
    kind = _clean_text(profile.get("kind")).lower()
    if kind not in WIRE_PROFILE_KINDS:
        errors.append(f"{item_key} has unknown wire profile kind {kind!r}")
        kind = kind or "unknown"

    normalized = {
        "kind": kind,
        "storage_points": _safe_int(profile.get("storage_points"), 1, minimum=0),
        "loadable": _safe_bool(profile.get("loadable"), default=True),
        "display_family": _clean_text(profile.get("display_family"), kind),
    }

    if kind == "program":
        program_key = _clean_text(profile.get("program_key")).lower()
        if not program_key:
            errors.append("program profile requires program_key")
        normalized.update({
            "program_key": program_key,
            "program_family": _clean_text(profile.get("program_family"), "utility").lower(),
            "program_mode": _clean_text(profile.get("program_mode"), "active").lower(),
            "ram_cost": _safe_int(profile.get("ram_cost"), 1, minimum=1),
            "reload_ticks": _safe_int(profile.get("reload_ticks"), 1, minimum=0),
            "noise": _safe_int(profile.get("noise"), 0, minimum=0),
            "trace_cost": _safe_int(profile.get("trace_cost"), 0, minimum=0),
            "durability_max": _safe_int(profile.get("durability_max"), 1, minimum=1),
            "runs_max": _safe_int(profile.get("runs_max"), 0, minimum=0),
            "dangerous": _safe_bool(profile.get("dangerous"), default=False),
            "capabilities": _string_tuple(profile.get("capabilities")),
        })
    elif kind == "data_packet":
        normalized.update({
            "data_family": _clean_text(profile.get("data_family"), "general").lower(),
            "sensitivity": _safe_int(profile.get("sensitivity"), 0, minimum=0),
            "freshness": _safe_int(profile.get("freshness"), 0, minimum=0),
            "heat_risk": _safe_int(profile.get("heat_risk"), 0, minimum=0),
            "legality": _clean_text(profile.get("legality"), "restricted").lower(),
            "buyer_tags": _string_tuple(profile.get("buyer_tags")),
        })
    elif kind == "credential":
        normalized.update({
            "credential_scope": _clean_text(profile.get("credential_scope"), "local").lower(),
            "burnable": _safe_bool(profile.get("burnable"), default=True),
            "runs_max": _safe_int(profile.get("runs_max"), 1, minimum=0),
        })
    elif kind == "license":
        normalized.update({
            "license_scope": _clean_text(profile.get("license_scope"), "program").lower(),
            "license_source": _clean_text(profile.get("license_source"), "unknown"),
        })
    elif kind == "backup":
        normalized.update({
            "backup_family": _clean_text(profile.get("backup_family"), "program").lower(),
            "restores_corruption": _safe_bool(profile.get("restores_corruption"), default=True),
        })
    elif kind == "trace":
        normalized.update({
            "trace_strength": _safe_int(profile.get("trace_strength"), 1, minimum=1),
            "source_context": _clean_text(profile.get("source_context"), "trace"),
        })
    elif kind == "corrupted_file":
        normalized.update({
            "corruption_tags": _string_tuple(profile.get("corruption_tags")),
            "source_context": _clean_text(profile.get("source_context"), "corruption"),
        })

    if errors:
        normalized["errors"] = tuple(errors)
    return normalized


def normalize_wire_interface_profile(profile=None, *, item_id=None):
    """Normalize a catalog-level wire_interface_profile block.

    Interface items are physical gear, so they stay in normal inventory. This
    profile describes what targets the interface can safely preflight/connect
    to and how much signal confidence its preview language should have.
    """

    if not isinstance(profile, dict):
        return {}
    errors = []
    item_key = _clean_item_id(item_id) or "item"
    kind = _clean_text(profile.get("kind")).lower()
    if kind not in WIRE_INTERFACE_KINDS:
        errors.append(f"{item_key} has unknown wire interface kind {kind!r}")
        kind = kind or "unknown"

    target_classes = _string_tuple(profile.get("supported_target_classes"))
    unknown_targets = [target for target in target_classes if target not in WIRE_TARGET_CLASSES]
    if unknown_targets:
        errors.append(f"{item_key} has unknown wire target class {unknown_targets[0]!r}")
        target_classes = tuple(target for target in target_classes if target in WIRE_TARGET_CLASSES)
    if not target_classes:
        errors.append("interface profile requires supported_target_classes")

    normalized = {
        "kind": kind,
        "manufacturer": _clean_text(profile.get("manufacturer"), "unknown"),
        "style": _clean_text(profile.get("style"), profile.get("manufacturer", "plain")).lower(),
        "supported_target_classes": target_classes,
        "program_slots": _safe_int(profile.get("program_slots"), 0, minimum=0),
        "buffer_size": _safe_int(profile.get("buffer_size"), 0, minimum=0),
        "memory_speed": _safe_int(profile.get("memory_speed"), 0, minimum=0),
        "warning_rating": _safe_int(profile.get("warning_rating"), 1, minimum=0, maximum=5),
        "trace_resistance": _safe_int(profile.get("trace_resistance"), 0, minimum=0, maximum=5),
        "signature_leakage": _safe_int(profile.get("signature_leakage"), 1, minimum=0, maximum=5),
        "range": _safe_int(profile.get("range"), 1, minimum=0),
        "safe_yank": _safe_bool(profile.get("safe_yank"), default=False),
        "panic_eject_delay": _safe_int(profile.get("panic_eject_delay"), 0, minimum=0),
        "recovery_delay": _safe_int(profile.get("recovery_delay"), 0, minimum=0),
        "shock_risk": _safe_float(profile.get("shock_risk"), 0.0, minimum=0.0),
        "noise_floor": _safe_int(profile.get("noise_floor"), 0, minimum=0, maximum=5),
        "default_quality": _quality(profile.get("default_quality"), default="standard"),
    }
    if errors:
        normalized["errors"] = tuple(errors)
    return normalized


def _catalog(item_catalog=None):
    if item_catalog is not None:
        return item_catalog
    from game.items import ITEM_CATALOG  # Local import avoids an items.py cycle.

    return ITEM_CATALOG


def wire_profile_for_item(item_id, item_catalog=None):
    item_key = _clean_item_id(item_id)
    if not item_key:
        return {}
    item_def = _catalog(item_catalog).get(item_key, {})
    profile = item_def.get("wire_profile") if isinstance(item_def, dict) else {}
    return dict(profile) if isinstance(profile, dict) else {}


def is_wire_item(item_id, item_catalog=None):
    return bool(wire_profile_for_item(item_id, item_catalog=item_catalog).get("kind"))


def wire_interface_profile_for_item(item_id, item_catalog=None):
    item_key = _clean_item_id(item_id)
    if not item_key:
        return {}
    item_def = _catalog(item_catalog).get(item_key, {})
    profile = item_def.get("wire_interface_profile") if isinstance(item_def, dict) else {}
    return dict(profile) if isinstance(profile, dict) else {}


def is_wire_interface_item(item_id, item_catalog=None):
    return bool(wire_interface_profile_for_item(item_id, item_catalog=item_catalog).get("kind"))


def normalize_wire_entry_metadata(metadata=None, *, item_id=None, profile=None):
    """Normalize per-instance metadata for wire-kit/backpack wire entries."""

    merged = dict(metadata or {})
    profile = dict(profile or wire_profile_for_item(item_id) or {})
    kind = _clean_text(profile.get("kind")).lower()
    if not kind:
        return merged

    default_quality = _quality(profile.get("default_quality"), default="standard")
    merged["wire_schema_version"] = WIRE_SCHEMA_VERSION
    merged["source_context"] = _clean_text(merged.get("source_context"), "unknown")
    merged["quality"] = _quality(merged.get("quality"), default=default_quality)
    merged["noise"] = _safe_int(merged.get("noise"), profile.get("noise", 0), minimum=0)
    merged["trace_cost"] = _safe_int(merged.get("trace_cost"), profile.get("trace_cost", 0), minimum=0)
    merged["display_name"] = _clean_text(merged.get("display_name"))
    merged["license_source"] = _clean_text(
        merged.get("license_source"),
        profile.get("license_source", ""),
    )
    merged["org_signature"] = _clean_text(merged.get("org_signature"))
    merged["corruption_tags"] = _string_tuple(
        merged.get("corruption_tags") or profile.get("corruption_tags")
    )
    merged["evidence_links"] = _string_tuple(merged.get("evidence_links"), lower=False)
    merged["storage_status"] = _clean_text(merged.get("storage_status"), "backpack")
    merged["loaded_tick"] = _safe_int(merged.get("loaded_tick"), -1, minimum=-1)
    merged["ram_reload_ticks_remaining"] = _safe_int(
        merged.get("ram_reload_ticks_remaining"),
        0,
        minimum=0,
    )
    merged["backing_instance_id"] = _clean_text(merged.get("backing_instance_id"))

    durability_max = _safe_int(
        merged.get("durability_max"),
        profile.get("durability_max", 1),
        minimum=1,
    )
    durability = _safe_int(merged.get("durability"), durability_max, minimum=0, maximum=durability_max)
    merged["durability_max"] = durability_max
    merged["durability"] = durability
    runs_max = _safe_int(merged.get("runs_max"), profile.get("runs_max", 0), minimum=0)
    runs = _safe_int(merged.get("runs"), runs_max, minimum=0)
    if runs_max:
        runs = min(runs, runs_max)
    merged["runs_max"] = runs_max
    merged["runs"] = runs
    if kind == "data_packet":
        merged["wire_data_schema_version"] = _safe_int(
            merged.get("wire_data_schema_version"),
            WIRE_DATA_SCHEMA_VERSION,
            minimum=1,
        )
        merged["data_family"] = _clean_text(
            merged.get("data_family"),
            profile.get("data_family", "general"),
        ).lower()
        merged["sensitivity"] = _safe_int(
            merged.get("sensitivity"),
            profile.get("sensitivity", 0),
            minimum=0,
        )
        merged["freshness"] = _safe_int(
            merged.get("freshness"),
            profile.get("freshness", 0),
            minimum=0,
        )
        merged["heat_risk"] = _safe_int(
            merged.get("heat_risk"),
            profile.get("heat_risk", 0),
            minimum=0,
        )
        merged["legality"] = _clean_text(
            merged.get("legality"),
            profile.get("legality", "restricted"),
        ).lower()
        merged["source_property_id"] = _clean_text(merged.get("source_property_id"))
        merged["source_property_name"] = _clean_text(merged.get("source_property_name"))
        merged["source_org_key"] = _clean_text(merged.get("source_org_key")).lower()
        merged["source_org_name"] = _clean_text(merged.get("source_org_name"))
        merged["source_archetype"] = _clean_text(merged.get("source_archetype")).lower()
        merged["captured_tick"] = _safe_int(merged.get("captured_tick"), 0, minimum=0)
        merged["buyer_tags"] = _string_tuple(merged.get("buyer_tags") or profile.get("buyer_tags"))
        if not merged["display_name"]:
            family = merged.get("data_family") or "general"
            source = merged.get("source_property_name") or "unknown source"
            merged["display_name"] = f"{family.replace('_', ' ').title()} cache: {source}"
    return merged


def normalize_wire_interface_metadata(metadata=None, *, item_id=None, profile=None):
    """Normalize per-instance metadata for physical wire-interface gear."""

    merged = dict(metadata or {})
    profile = dict(profile or wire_interface_profile_for_item(item_id) or {})
    kind = _clean_text(profile.get("kind")).lower()
    if not kind:
        return merged

    merged["wire_interface_schema_version"] = WIRE_INTERFACE_SCHEMA_VERSION
    merged["source_context"] = _clean_text(merged.get("source_context"), "unknown")
    merged["distribution_context"] = _clean_text(merged.get("distribution_context"))
    merged["quality"] = _quality(merged.get("quality"), default=profile.get("default_quality", "standard"))
    merged["interface_kind"] = kind
    merged["manufacturer"] = _clean_text(merged.get("manufacturer"), profile.get("manufacturer", "unknown"))
    merged["style"] = _clean_text(merged.get("style"), profile.get("style", "plain")).lower()
    merged["supported_target_classes"] = _string_tuple(
        merged.get("supported_target_classes") or profile.get("supported_target_classes")
    )
    merged["program_slots"] = _safe_int(merged.get("program_slots"), profile.get("program_slots", 0), minimum=0)
    merged["buffer_size"] = _safe_int(merged.get("buffer_size"), profile.get("buffer_size", 0), minimum=0)
    default_memory_speed = max(
        1,
        _safe_int(merged.get("program_slots"), profile.get("program_slots", 0), minimum=0)
        + _safe_int(merged.get("buffer_size"), profile.get("buffer_size", 0), minimum=0) // 4
        - _safe_int(merged.get("noise_floor"), profile.get("noise_floor", 0), minimum=0) // 2,
    )
    merged["memory_speed"] = _safe_int(
        merged.get("memory_speed"),
        profile.get("memory_speed", default_memory_speed),
        minimum=0,
    )
    merged["warning_rating"] = _safe_int(
        merged.get("warning_rating"),
        profile.get("warning_rating", 1),
        minimum=0,
        maximum=5,
    )
    merged["trace_resistance"] = _safe_int(
        merged.get("trace_resistance"),
        profile.get("trace_resistance", 0),
        minimum=0,
        maximum=5,
    )
    merged["signature_leakage"] = _safe_int(
        merged.get("signature_leakage"),
        profile.get("signature_leakage", 1),
        minimum=0,
        maximum=5,
    )
    merged["range"] = _safe_int(merged.get("range"), profile.get("range", 1), minimum=0)
    merged["safe_yank"] = _safe_bool(merged.get("safe_yank"), default=profile.get("safe_yank", False))
    merged["panic_eject_delay"] = _safe_int(
        merged.get("panic_eject_delay"),
        profile.get("panic_eject_delay", 0),
        minimum=0,
    )
    merged["recovery_delay"] = _safe_int(
        merged.get("recovery_delay"),
        profile.get("recovery_delay", 0),
        minimum=0,
    )
    merged["shock_risk"] = _safe_float(merged.get("shock_risk"), profile.get("shock_risk", 0.0), minimum=0.0)
    merged["noise_floor"] = _safe_int(merged.get("noise_floor"), profile.get("noise_floor", 0), minimum=0, maximum=5)
    merged["display_name"] = _clean_text(merged.get("display_name"))
    return merged


def wire_entry_storage_points(entry_or_item_id, *, item_catalog=None):
    if isinstance(entry_or_item_id, Mapping):
        item_id = entry_or_item_id.get("item_id")
    else:
        item_id = entry_or_item_id
    profile = wire_profile_for_item(item_id, item_catalog=item_catalog)
    return _safe_int(profile.get("storage_points"), 1, minimum=0)


def wire_entry_display_name(entry_or_item_id, *, item_catalog=None):
    if isinstance(entry_or_item_id, Mapping):
        item_id = entry_or_item_id.get("item_id")
        metadata = entry_or_item_id.get("metadata") if isinstance(entry_or_item_id.get("metadata"), dict) else {}
    else:
        item_id = entry_or_item_id
        metadata = {}
    display_name = _clean_text(metadata.get("display_name"))
    if display_name:
        return display_name
    from game.items import item_display_name

    return item_display_name(item_id, metadata=metadata, item_catalog=item_catalog or _catalog())
