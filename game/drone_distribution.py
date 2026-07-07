"""Drone distribution presets, stock metadata, and paint vocabulary."""

from __future__ import annotations

import random
from collections.abc import Mapping

from game.color_words import curated_color_words, normalize_color_word
from game.drone_runtime import (
    PACKED_DRONE_ITEM_ID,
    drone_loadout_summary,
    drone_profile_for_item,
    normalize_packed_drone_metadata,
)


DRONE_BASE_PAINT_WORDS = (
    "steel",
    "black",
    "white",
    "gray",
    "red",
    "orange",
    "yellow",
    "green",
    "blue",
    "purple",
)
DRONE_EXISTING_PAINT_WORDS = ("steel", "black", "white", "red", "orange", "yellow", "green", "blue", "purple")
DRONE_EXCLUDED_PAINT_WORDS = {"total_black"}

DRONE_ITEM_BASE_VALUES = {
    "drone_chassis_a": 90,
    "drone_chassis_b": 130,
    "drone_chassis_c": 185,
    "drone_chassis_d": 255,
    "drone_chassis_e": 340,
    "drone_power_core_mk1": 55,
    "drone_power_core_mk2": 78,
    "drone_power_core_mk3": 108,
    "drone_power_core_mk4": 148,
    "drone_power_core_mk5": 198,
    "drone_battery_light": 30,
    "drone_battery_standard": 46,
    "drone_battery_heavy": 74,
    "drone_battery_industrial": 116,
    "drone_camera_module": 82,
    "drone_radar_module": 118,
    "drone_ir_module": 104,
    "drone_sonar_module": 58,
    "drone_lidar_module": 96,
    "drone_radio_module": 64,
    "drone_remote_receiver_module": 72,
    "drone_cargo_clamp_module": 68,
    "drone_light_module": 32,
    "drone_speaker_module": 40,
    "drone_armor_shell_module": 94,
    "drone_alarm_probe_module": 96,
    "drone_mapping_procedure_module": 88,
    "drone_follow_procedure_module": 78,
    "drone_pistol_module": 150,
    "drone_ammo_rack_module": 76,
    "drone_fuel_tank_module": 86,
    "drone_flame_nozzle_module": 168,
    PACKED_DRONE_ITEM_ID: 280,
}

DRONE_PACKED_PRESET_LOADOUTS = {
    "utility_a": {
        "display_name": "Packed A-Class Utility Drone",
        "chassis_item_id": "drone_chassis_a",
        "power_center_item_id": "drone_power_core_mk1",
        "battery_item_id": "drone_battery_light",
        "modules": ("drone_sonar_module", "drone_remote_receiver_module"),
        "paint": {"primary_color": "steel", "secondary_color": "blue"},
    },
    "scout_b": {
        "display_name": "Packed B-Class Scout Drone",
        "chassis_item_id": "drone_chassis_b",
        "power_center_item_id": "drone_power_core_mk2",
        "battery_item_id": "drone_battery_standard",
        "modules": ("drone_radar_module", "drone_remote_receiver_module", "drone_mapping_procedure_module"),
        "paint": {"primary_color": "sage", "secondary_color": "white"},
    },
    "cargo_c": {
        "display_name": "Packed C-Class Cargo Drone",
        "chassis_item_id": "drone_chassis_c",
        "power_center_item_id": "drone_power_core_mk3",
        "battery_item_id": "drone_battery_standard",
        "modules": (
            "drone_camera_module",
            "drone_remote_receiver_module",
            "drone_cargo_clamp_module",
            "drone_light_module",
        ),
        "paint": {"primary_color": "orange", "secondary_color": "steel"},
    },
    "security_d_no_radio": {
        "display_name": "Packed D-Class Security Drone",
        "chassis_item_id": "drone_chassis_d",
        "power_center_item_id": "drone_power_core_mk4",
        "battery_item_id": "drone_battery_heavy",
        "modules": (
            "drone_camera_module",
            "drone_remote_receiver_module",
            "drone_pistol_module",
            {"item_id": "drone_ammo_rack_module", "metadata": {"ammo_count": 6, "ammo_count_max": 6}},
        ),
        "paint": {"primary_color": "charcoal", "secondary_color": "red"},
    },
    "rough_c": {
        "display_name": "Packed Rough C-Class Drone",
        "chassis_item_id": "drone_chassis_c",
        "power_center_item_id": "drone_power_core_mk4",
        "battery_item_id": "drone_battery_heavy",
        "modules": (
            "drone_remote_receiver_module",
            "drone_pistol_module",
            {"item_id": "drone_ammo_rack_module", "metadata": {"ammo_count": 4, "ammo_count_max": 6}},
        ),
        "paint": {"primary_color": "rust", "secondary_color": "black"},
    },
}

DRONE_STORE_POOL_EXTRAS = {
    "electronics_shop": (
        ("drone_battery_light", 8),
        ("drone_battery_standard", 7),
        ("drone_chassis_a", 4),
        ("drone_chassis_b", 3),
        ("drone_power_core_mk1", 5),
        ("drone_power_core_mk2", 4),
        ("drone_camera_module", 5),
        ("drone_radio_module", 5),
        ("drone_remote_receiver_module", 4),
        ("drone_sonar_module", 4),
        ("drone_lidar_module", 3),
        ("drone_radar_module", 1),
        ("drone_light_module", 4),
        ("drone_speaker_module", 3),
        ("drone_cargo_clamp_module", 2),
        (PACKED_DRONE_ITEM_ID, 1),
    ),
    "comms_shop": (
        ("drone_battery_light", 6),
        ("drone_battery_standard", 6),
        ("drone_chassis_a", 3),
        ("drone_power_core_mk1", 4),
        ("drone_power_core_mk2", 3),
        ("drone_camera_module", 4),
        ("drone_radio_module", 6),
        ("drone_remote_receiver_module", 5),
        ("drone_radar_module", 2),
        ("drone_ir_module", 1),
        ("drone_lidar_module", 3),
        ("drone_sonar_module", 3),
        ("drone_mapping_procedure_module", 3),
        (PACKED_DRONE_ITEM_ID, 1),
    ),
    "drone_shop": (
        ("drone_battery_light", 8),
        ("drone_battery_standard", 8),
        ("drone_battery_heavy", 5),
        ("drone_battery_industrial", 1),
        ("drone_chassis_a", 6),
        ("drone_chassis_b", 5),
        ("drone_chassis_c", 4),
        ("drone_chassis_d", 1),
        ("drone_power_core_mk1", 6),
        ("drone_power_core_mk2", 5),
        ("drone_power_core_mk3", 4),
        ("drone_power_core_mk4", 1),
        ("drone_camera_module", 6),
        ("drone_radio_module", 6),
        ("drone_remote_receiver_module", 6),
        ("drone_sonar_module", 5),
        ("drone_lidar_module", 4),
        ("drone_radar_module", 2),
        ("drone_ir_module", 2),
        ("drone_cargo_clamp_module", 4),
        ("drone_light_module", 4),
        ("drone_speaker_module", 3),
        ("drone_armor_shell_module", 2),
        ("drone_mapping_procedure_module", 4),
        ("drone_follow_procedure_module", 4),
        (PACKED_DRONE_ITEM_ID, 2),
    ),
    "hardware_store": (
        ("drone_battery_light", 8),
        ("drone_battery_standard", 7),
        ("drone_chassis_a", 4),
        ("drone_chassis_b", 3),
        ("drone_power_core_mk1", 5),
        ("drone_power_core_mk2", 4),
        ("drone_light_module", 5),
        ("drone_sonar_module", 4),
        ("drone_lidar_module", 1),
        ("drone_cargo_clamp_module", 3),
        ("drone_remote_receiver_module", 3),
        (PACKED_DRONE_ITEM_ID, 1),
    ),
    "tool_depot": (
        ("drone_battery_light", 8),
        ("drone_battery_standard", 7),
        ("drone_chassis_a", 4),
        ("drone_chassis_b", 4),
        ("drone_chassis_c", 2),
        ("drone_power_core_mk1", 5),
        ("drone_power_core_mk2", 5),
        ("drone_power_core_mk3", 3),
        ("drone_camera_module", 4),
        ("drone_sonar_module", 4),
        ("drone_lidar_module", 2),
        ("drone_radar_module", 1),
        ("drone_light_module", 5),
        ("drone_remote_receiver_module", 4),
        ("drone_cargo_clamp_module", 3),
        (PACKED_DRONE_ITEM_ID, 1),
    ),
    "auto_garage": (
        ("drone_battery_standard", 7),
        ("drone_battery_heavy", 3),
        ("drone_chassis_b", 4),
        ("drone_chassis_c", 3),
        ("drone_power_core_mk2", 5),
        ("drone_power_core_mk3", 3),
        ("drone_camera_module", 3),
        ("drone_sonar_module", 2),
        ("drone_lidar_module", 2),
        ("drone_radar_module", 1),
        ("drone_remote_receiver_module", 3),
        ("drone_cargo_clamp_module", 3),
        (PACKED_DRONE_ITEM_ID, 1),
    ),
    "service_station": (
        ("drone_battery_light", 4),
        ("drone_battery_standard", 4),
        ("drone_light_module", 2),
        ("drone_sonar_module", 1),
        ("drone_power_core_mk1", 2),
    ),
    "salvage_camp": (
        ("drone_battery_light", 8),
        ("drone_battery_standard", 6),
        ("drone_chassis_a", 5),
        ("drone_chassis_b", 4),
        ("drone_power_core_mk1", 5),
        ("drone_power_core_mk2", 4),
        ("drone_camera_module", 3),
        ("drone_sonar_module", 3),
        ("drone_lidar_module", 1),
        ("drone_radio_module", 3),
        ("drone_remote_receiver_module", 3),
        ("drone_cargo_clamp_module", 3),
        (PACKED_DRONE_ITEM_ID, 1),
    ),
    "breaker_yard": (
        ("drone_battery_standard", 6),
        ("drone_battery_heavy", 3),
        ("drone_chassis_b", 4),
        ("drone_chassis_c", 3),
        ("drone_power_core_mk2", 4),
        ("drone_power_core_mk3", 3),
        ("drone_camera_module", 3),
        ("drone_sonar_module", 2),
        ("drone_lidar_module", 2),
        ("drone_remote_receiver_module", 3),
        ("drone_cargo_clamp_module", 3),
        (PACKED_DRONE_ITEM_ID, 1),
    ),
    "drydock_yard": (
        ("drone_battery_light", 5),
        ("drone_battery_standard", 5),
        ("drone_chassis_a", 3),
        ("drone_chassis_b", 3),
        ("drone_power_core_mk1", 3),
        ("drone_power_core_mk2", 3),
        ("drone_radio_module", 2),
        ("drone_sonar_module", 2),
        ("drone_lidar_module", 1),
        ("drone_light_module", 3),
    ),
    "ranger_hut": (
        ("drone_battery_light", 6),
        ("drone_battery_standard", 5),
        ("drone_chassis_a", 3),
        ("drone_chassis_b", 3),
        ("drone_power_core_mk1", 3),
        ("drone_power_core_mk2", 3),
        ("drone_camera_module", 4),
        ("drone_radar_module", 2),
        ("drone_sonar_module", 3),
        ("drone_lidar_module", 2),
        ("drone_radio_module", 4),
        ("drone_mapping_procedure_module", 3),
        ("drone_light_module", 3),
        (PACKED_DRONE_ITEM_ID, 1),
    ),
    "bait_shop": (
        ("drone_battery_light", 4),
        ("drone_battery_standard", 3),
        ("drone_chassis_a", 2),
        ("drone_camera_module", 2),
        ("drone_sonar_module", 2),
        ("drone_lidar_module", 1),
        ("drone_mapping_procedure_module", 2),
    ),
    "pawn_shop": (
        ("drone_battery_light", 5),
        ("drone_battery_standard", 5),
        ("drone_chassis_a", 3),
        ("drone_chassis_b", 3),
        ("drone_power_core_mk1", 3),
        ("drone_power_core_mk2", 3),
        ("drone_camera_module", 3),
        ("drone_sonar_module", 2),
        ("drone_lidar_module", 1),
        ("drone_radio_module", 3),
        ("drone_remote_receiver_module", 3),
        ("drone_speaker_module", 2),
        (PACKED_DRONE_ITEM_ID, 1),
    ),
    "junk_market": (
        ("drone_battery_light", 5),
        ("drone_battery_standard", 4),
        ("drone_chassis_a", 3),
        ("drone_chassis_b", 2),
        ("drone_power_core_mk1", 3),
        ("drone_power_core_mk2", 2),
        ("drone_camera_module", 2),
        ("drone_sonar_module", 2),
        ("drone_radio_module", 2),
        ("drone_remote_receiver_module", 2),
        (PACKED_DRONE_ITEM_ID, 1),
    ),
    "backroom_market": (
        ("drone_battery_standard", 5),
        ("drone_battery_heavy", 4),
        ("drone_chassis_b", 3),
        ("drone_chassis_c", 3),
        ("drone_power_core_mk2", 3),
        ("drone_power_core_mk3", 3),
        ("drone_camera_module", 3),
        ("drone_radar_module", 2),
        ("drone_ir_module", 1),
        ("drone_lidar_module", 2),
        ("drone_radio_module", 3),
        ("drone_remote_receiver_module", 4),
        ("drone_alarm_probe_module", 2),
        ("drone_pistol_module", 1),
        ("drone_ammo_rack_module", 1),
        (PACKED_DRONE_ITEM_ID, 1),
    ),
    "chop_shop": (
        ("drone_battery_standard", 5),
        ("drone_battery_heavy", 3),
        ("drone_chassis_b", 3),
        ("drone_chassis_c", 3),
        ("drone_power_core_mk2", 3),
        ("drone_power_core_mk3", 3),
        ("drone_camera_module", 3),
        ("drone_radar_module", 1),
        ("drone_ir_module", 1),
        ("drone_lidar_module", 1),
        ("drone_remote_receiver_module", 3),
        ("drone_cargo_clamp_module", 2),
        ("drone_pistol_module", 1),
        ("drone_ammo_rack_module", 1),
        (PACKED_DRONE_ITEM_ID, 1),
    ),
    "surplus_store": (
        ("drone_battery_standard", 5),
        ("drone_battery_heavy", 5),
        ("drone_battery_industrial", 3),
        ("drone_chassis_c", 4),
        ("drone_chassis_d", 3),
        ("drone_chassis_e", 1),
        ("drone_power_core_mk3", 4),
        ("drone_power_core_mk4", 3),
        ("drone_power_core_mk5", 1),
        ("drone_camera_module", 4),
        ("drone_radar_module", 3),
        ("drone_ir_module", 2),
        ("drone_lidar_module", 3),
        ("drone_radio_module", 4),
        ("drone_remote_receiver_module", 4),
        ("drone_mapping_procedure_module", 3),
        ("drone_follow_procedure_module", 3),
        ("drone_armor_shell_module", 3),
        ("drone_pistol_module", 2),
        ("drone_ammo_rack_module", 2),
        ("drone_fuel_tank_module", 1),
        ("drone_flame_nozzle_module", 1),
        (PACKED_DRONE_ITEM_ID, 1),
    ),
    "outfitter": (
        ("drone_battery_standard", 4),
        ("drone_battery_heavy", 3),
        ("drone_chassis_b", 3),
        ("drone_chassis_c", 3),
        ("drone_chassis_d", 1),
        ("drone_power_core_mk2", 3),
        ("drone_power_core_mk3", 3),
        ("drone_power_core_mk4", 1),
        ("drone_camera_module", 3),
        ("drone_radar_module", 1),
        ("drone_ir_module", 1),
        ("drone_lidar_module", 2),
        ("drone_radio_module", 3),
        ("drone_remote_receiver_module", 3),
        ("drone_mapping_procedure_module", 2),
        ("drone_follow_procedure_module", 2),
        ("drone_armor_shell_module", 2),
        ("drone_pistol_module", 1),
        ("drone_ammo_rack_module", 1),
        (PACKED_DRONE_ITEM_ID, 1),
    ),
}

DRONE_STREET_VENDOR_POOL_EXTRAS = {
    "gang_fence": (
        "drone_remote_receiver_module",
        "drone_camera_module",
        "drone_radar_module",
        "drone_ir_module",
        "drone_pistol_module",
        "drone_ammo_rack_module",
        PACKED_DRONE_ITEM_ID,
    ),
    "alley_market": (
        "drone_battery_standard",
        "drone_camera_module",
        "drone_lidar_module",
        "drone_ir_module",
        "drone_remote_receiver_module",
        "drone_pistol_module",
        "drone_ammo_rack_module",
    ),
    "vehicle_gun_vendor": (
        "drone_radar_module",
        "drone_ir_module",
        "drone_pistol_module",
        "drone_ammo_rack_module",
        "drone_fuel_tank_module",
        "drone_flame_nozzle_module",
        PACKED_DRONE_ITEM_ID,
    ),
}


def _dedupe(values):
    out = []
    seen = set()
    for value in values:
        text = str(value or "").strip().lower()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return tuple(out)


def _catalog(item_catalog=None):
    if item_catalog is not None:
        return item_catalog
    from game.items import ITEM_CATALOG

    return ITEM_CATALOG


def flora_drone_paint_words():
    words = []
    try:
        from game.flora_genetics import COLOR_WORD_BY_RENDER_KEY

        words.extend(COLOR_WORD_BY_RENDER_KEY.values())
    except Exception:  # noqa: BLE001 - palette fallback should be harmless
        pass
    try:
        from game.flora_runtime import load_flora_catalog

        for row in load_flora_catalog().values():
            genetics = row.get("genetics") if isinstance(row, Mapping) else {}
            hue = genetics.get("hue_family") if isinstance(genetics, Mapping) else ""
            if hue:
                words.append(hue)
            color_word = row.get("color_word") if isinstance(row, Mapping) else ""
            if color_word:
                words.append(color_word)
    except Exception:  # noqa: BLE001 - palette fallback should be harmless
        pass
    return _dedupe(normalize_color_word(word) or word for word in words)


def gang_drone_paint_words():
    try:
        from game.gang_enterprise_runtime import GANG_STYLE_COLORS

        return _dedupe(normalize_color_word(word) or word for word in GANG_STYLE_COLORS)
    except Exception:  # noqa: BLE001 - palette fallback should be harmless
        return ()


def drone_paint_palette():
    native = [
        word
        for word in curated_color_words(include_reserved=True)
        if str(word or "").strip().lower() not in DRONE_EXCLUDED_PAINT_WORDS
    ]
    return _dedupe(
        tuple(DRONE_EXISTING_PAINT_WORDS)
        + tuple(DRONE_BASE_PAINT_WORDS)
        + tuple(native)
        + flora_drone_paint_words()
        + gang_drone_paint_words()
    )


def normalize_drone_paint_word(value):
    text = str(value or "").strip().lower()
    normalized = normalize_color_word(text) or text
    if normalized in set(drone_paint_palette()):
        return normalized
    return ""


def drone_store_item_pool(archetype):
    return tuple(DRONE_STORE_POOL_EXTRAS.get(str(archetype or "").strip().lower(), ()))


def drone_street_vendor_item_pool(vendor_kind):
    return tuple(DRONE_STREET_VENDOR_POOL_EXTRAS.get(str(vendor_kind or "").strip().lower(), ()))


def drone_item_base_value(item_id, default=10):
    return int(DRONE_ITEM_BASE_VALUES.get(str(item_id or "").strip().lower(), int(default)))


def _module_entry(entry):
    if isinstance(entry, str):
        item_id = str(entry or "").strip().lower()
        metadata = drone_distribution_metadata(item_id, source_context="drone_preset_module")
        return {"item_id": item_id, "metadata": metadata} if metadata else {"item_id": item_id}
    if not isinstance(entry, Mapping):
        return None
    item_id = str(entry.get("item_id") or entry.get("module_item_id") or "").strip().lower()
    if not item_id:
        return None
    metadata = dict(entry.get("metadata") or {})
    metadata = drone_distribution_metadata(item_id, metadata, source_context="drone_preset_module")
    return {"item_id": item_id, "metadata": metadata} if metadata else {"item_id": item_id}


def packed_drone_preset_metadata(preset_key, *, source_context="drone_distribution", distribution_context="", seed_token="", item_catalog=None):
    key = str(preset_key or "").strip().lower()
    raw = DRONE_PACKED_PRESET_LOADOUTS.get(key)
    if raw is None:
        key = "utility_a"
        raw = DRONE_PACKED_PRESET_LOADOUTS[key]
    metadata = dict(raw)
    metadata["modules"] = [module for module in (_module_entry(entry) for entry in tuple(raw.get("modules", ()))) if module]
    metadata["source_context"] = str(source_context or "drone_distribution")
    metadata["distribution_context"] = str(distribution_context or "")
    metadata["distribution_preset"] = key
    if seed_token:
        metadata["distribution_seed"] = str(seed_token)
    normalized = normalize_packed_drone_metadata(metadata, item_catalog=_catalog(item_catalog))
    summary = drone_loadout_summary(normalized, item_catalog=_catalog(item_catalog))
    normalized["loadout_errors"] = tuple(summary.get("errors", ()) or ())
    return normalized


def _preset_for_context(distribution_context, *, seed_token=""):
    context = str(distribution_context or "").strip().lower()
    if context in {"surplus_store", "armory", "checkpoint", "vehicle_gun_vendor"}:
        choices = ("security_d_no_radio", "cargo_c", "rough_c")
    elif context in {"drone_shop"}:
        choices = ("cargo_c", "scout_b", "utility_a")
    elif context in {"electronics_shop", "comms_shop"}:
        choices = ("scout_b", "utility_a", "cargo_c")
    elif context in {"gang_fence", "alley_market", "backroom_market", "chop_shop"}:
        choices = ("rough_c", "cargo_c", "scout_b")
    elif context in {"ranger_hut", "field_camp", "dock_shack", "ferry_post", "tide_station", "bait_shop"}:
        choices = ("scout_b", "utility_a")
    elif context in {"auto_garage", "tool_depot", "hardware_store", "salvage_camp", "breaker_yard"}:
        choices = ("utility_a", "cargo_c", "scout_b")
    else:
        choices = ("utility_a", "scout_b", "cargo_c")
    if not seed_token:
        return choices[0]
    return random.Random(f"drone-preset:{distribution_context}:{seed_token}").choice(choices)


def drone_distribution_metadata(
    item_id,
    base_metadata=None,
    *,
    source_context="drone_distribution",
    distribution_context="",
    seed_token="",
    preset_key="",
    item_catalog=None,
):
    catalog = _catalog(item_catalog)
    item_key = str(item_id or "").strip().lower()
    profile = drone_profile_for_item(item_key, item_catalog=catalog)
    if not profile.get("kind"):
        return dict(base_metadata or {})

    if item_key == PACKED_DRONE_ITEM_ID or profile.get("kind") == "assembly":
        chosen = preset_key or _preset_for_context(distribution_context, seed_token=seed_token)
        metadata = packed_drone_preset_metadata(
            chosen,
            source_context=source_context,
            distribution_context=distribution_context,
            seed_token=seed_token,
            item_catalog=catalog,
        )
        metadata.update(dict(base_metadata or {}))
        metadata.setdefault("source_context", source_context)
        metadata.setdefault("distribution_context", distribution_context)
        return normalize_packed_drone_metadata(metadata, item_catalog=catalog)

    metadata = dict(base_metadata or {})
    metadata.setdefault("source_context", source_context)
    metadata.setdefault("distribution_context", distribution_context)
    if seed_token:
        metadata.setdefault("distribution_seed", str(seed_token))
    kind = str(profile.get("kind") or "").strip().lower()
    if kind == "battery":
        charge_max = int(profile.get("charge_max", 0) or 0)
        metadata.setdefault("battery_charge_max", charge_max)
        metadata.setdefault("battery_charge", charge_max)
    elif kind == "module":
        module_kind = str(profile.get("module_kind", "") or "").strip().lower()
        if module_kind == "ammo_rack":
            metadata.setdefault("ammo_count_max", 6)
            metadata.setdefault("ammo_count", 6)
        elif module_kind == "fuel_tank":
            metadata.setdefault("fuel_charge_max", 3)
            metadata.setdefault("fuel_charge", 3)
    return metadata


def distributed_drone_item_ids():
    ids = set()
    for rows in DRONE_STORE_POOL_EXTRAS.values():
        ids.update(str(item_id).strip().lower() for item_id, _weight in rows)
    for rows in DRONE_STREET_VENDOR_POOL_EXTRAS.values():
        ids.update(str(item_id).strip().lower() for item_id in rows)
    ids.update(DRONE_ITEM_BASE_VALUES)
    return tuple(sorted(item_id for item_id in ids if item_id))
