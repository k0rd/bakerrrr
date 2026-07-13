"""Wire interface/software stock pools and distribution metadata helpers."""

from __future__ import annotations

import random

from game.wire_runtime import (
    is_wire_interface_item,
    is_wire_item,
    normalize_wire_entry_metadata,
    normalize_wire_interface_metadata,
    wire_interface_profile_for_item,
    wire_profile_for_item,
)


WIRE_ITEM_BASE_VALUES = {
    "cheap_deck": 145,
    "wetwire_jack": 260,
    "skin_contact_rig": 120,
    "corp_interface_cable": 210,
    "cracked_service_dongle": 95,
    "drone_radio_bridge": 180,
    "wire_talk_program": 55,
    "wire_route_probe_program": 90,
    "wire_door_latch_program": 150,
    "wire_camera_loop_program": 140,
    "wire_data_siphon_shell_program": 175,
    "wire_spike_program": 130,
    "wire_ice_cutter_program": 165,
    "wire_trace_scrubber_program": 110,
    "wire_signal_cloak_program": 125,
    "wire_panic_eject_program": 105,
    "wire_checksum_ward_program": 120,
    "wire_sacrificial_shell_program": 65,
    "wire_data_cache": 50,
    "wire_access_key": 85,
    "wire_license_key": 60,
    "wire_backup_image": 95,
    "wire_trace_fragment": 30,
    "wire_corrupted_file": 22,
}

WIRE_STORE_POOL_EXTRAS = {
    "contractor_office": (
        ("cracked_service_dongle", 8),
        ("corp_interface_cable", 6),
        ("cheap_deck", 7),
        ("wetwire_jack", 5),
        ("wire_route_probe_program", 8),
        ("wire_talk_program", 6),
        ("wire_door_latch_program", 5),
        ("wire_camera_loop_program", 4),
        ("wire_trace_scrubber_program", 4),
        ("wire_checksum_ward_program", 3),
        ("wire_panic_eject_program", 3),
    ),
    "electronics_shop": (
        ("cheap_deck", 9),
        ("skin_contact_rig", 7),
        ("wetwire_jack", 5),
        ("corp_interface_cable", 4),
        ("wire_talk_program", 8),
        ("wire_route_probe_program", 8),
        ("wire_trace_scrubber_program", 5),
        ("wire_signal_cloak_program", 4),
        ("wire_checksum_ward_program", 4),
        ("wire_panic_eject_program", 4),
        ("wire_data_siphon_shell_program", 2),
        ("wire_backup_image", 3),
    ),
    "comms_shop": (
        ("cheap_deck", 7),
        ("skin_contact_rig", 5),
        ("wetwire_jack", 5),
        ("drone_radio_bridge", 5),
        ("wire_talk_program", 8),
        ("wire_route_probe_program", 6),
        ("wire_trace_scrubber_program", 4),
        ("wire_signal_cloak_program", 3),
        ("wire_camera_loop_program", 2),
        ("wire_license_key", 3),
    ),
    "drone_shop": (
        ("drone_radio_bridge", 6),
        ("cheap_deck", 6),
        ("skin_contact_rig", 4),
        ("wetwire_jack", 4),
        ("wire_talk_program", 5),
        ("wire_route_probe_program", 5),
        ("wire_door_latch_program", 2),
        ("wire_camera_loop_program", 3),
        ("wire_trace_scrubber_program", 3),
    ),
    "hardware_store": (
        ("cheap_deck", 3),
        ("cracked_service_dongle", 3),
        ("corp_interface_cable", 1),
        ("wire_talk_program", 2),
        ("wire_route_probe_program", 3),
        ("wire_door_latch_program", 1),
    ),
    "tool_depot": (
        ("cheap_deck", 3),
        ("cracked_service_dongle", 3),
        ("corp_interface_cable", 2),
        ("wire_talk_program", 2),
        ("wire_route_probe_program", 3),
        ("wire_door_latch_program", 2),
    ),
    "auto_garage": (
        ("cheap_deck", 2),
        ("cracked_service_dongle", 3),
        ("drone_radio_bridge", 1),
        ("wire_route_probe_program", 2),
        ("wire_door_latch_program", 2),
        ("wire_camera_loop_program", 1),
    ),
    "brokerage": (
        ("cheap_deck", 3),
        ("corp_interface_cable", 3),
        ("wetwire_jack", 1),
        ("wire_talk_program", 3),
        ("wire_route_probe_program", 3),
        ("wire_data_siphon_shell_program", 2),
        ("wire_trace_scrubber_program", 2),
        ("wire_license_key", 2),
    ),
    "data_center": (
        ("corp_interface_cable", 4),
        ("wetwire_jack", 2),
        ("wire_route_probe_program", 4),
        ("wire_data_siphon_shell_program", 3),
        ("wire_ice_cutter_program", 2),
        ("wire_checksum_ward_program", 2),
        ("wire_panic_eject_program", 2),
        ("wire_backup_image", 2),
    ),
    "media_lab": (
        ("cheap_deck", 3),
        ("skin_contact_rig", 3),
        ("wire_talk_program", 4),
        ("wire_route_probe_program", 3),
        ("wire_camera_loop_program", 2),
        ("wire_data_siphon_shell_program", 2),
        ("wire_trace_scrubber_program", 2),
    ),
    "office": (
        ("cheap_deck", 2),
        ("corp_interface_cable", 2),
        ("wire_talk_program", 3),
        ("wire_route_probe_program", 2),
        ("wire_data_siphon_shell_program", 1),
        ("wire_trace_scrubber_program", 1),
    ),
    "tower": (
        ("corp_interface_cable", 4),
        ("wetwire_jack", 2),
        ("wire_route_probe_program", 4),
        ("wire_data_siphon_shell_program", 3),
        ("wire_signal_cloak_program", 2),
        ("wire_ice_cutter_program", 2),
        ("wire_checksum_ward_program", 2),
    ),
    "pawn_shop": (
        ("cheap_deck", 5),
        ("skin_contact_rig", 4),
        ("wetwire_jack", 3),
        ("cracked_service_dongle", 5),
        ("wire_talk_program", 3),
        ("wire_route_probe_program", 3),
        ("wire_corrupted_file", 3),
        ("wire_trace_fragment", 2),
        ("wire_sacrificial_shell_program", 2),
    ),
    "junk_market": (
        ("cheap_deck", 4),
        ("wetwire_jack", 2),
        ("cracked_service_dongle", 5),
        ("wire_talk_program", 2),
        ("wire_route_probe_program", 3),
        ("wire_corrupted_file", 4),
        ("wire_trace_fragment", 3),
        ("wire_sacrificial_shell_program", 2),
        ("wire_spike_program", 2),
    ),
    "chop_shop": (
        ("cheap_deck", 3),
        ("cracked_service_dongle", 5),
        ("drone_radio_bridge", 4),
        ("wetwire_jack", 3),
        ("wire_route_probe_program", 4),
        ("wire_door_latch_program", 3),
        ("wire_camera_loop_program", 3),
        ("wire_spike_program", 2),
        ("wire_corrupted_file", 3),
    ),
    "backroom_market": (
        ("wetwire_jack", 3),
        ("cracked_service_dongle", 4),
        ("drone_radio_bridge", 2),
        ("wire_door_latch_program", 3),
        ("wire_camera_loop_program", 3),
        ("wire_trace_scrubber_program", 2),
        ("wire_data_siphon_shell_program", 2),
        ("wire_spike_program", 2),
        ("wire_ice_cutter_program", 2),
        ("wire_signal_cloak_program", 2),
        ("wire_checksum_ward_program", 2),
        ("wire_panic_eject_program", 1),
        ("wire_sacrificial_shell_program", 3),
        ("wire_access_key", 2),
        ("wire_corrupted_file", 2),
    ),
}

WIRE_STREET_VENDOR_POOL_EXTRAS = {
    "gang_fence": (
        "cracked_service_dongle",
        "wire_door_latch_program",
        "wire_camera_loop_program",
        "wire_spike_program",
        "wire_ice_cutter_program",
        "wire_sacrificial_shell_program",
        "wire_access_key",
        "wire_corrupted_file",
    ),
    "alley_market": (
        "cheap_deck",
        "wetwire_jack",
        "cracked_service_dongle",
        "wire_route_probe_program",
        "wire_signal_cloak_program",
        "wire_trace_fragment",
        "wire_corrupted_file",
    ),
    "vehicle_gun_vendor": (
        "drone_radio_bridge",
        "cracked_service_dongle",
        "wire_camera_loop_program",
        "wire_spike_program",
    ),
}


def wire_store_item_pool(archetype):
    return tuple(WIRE_STORE_POOL_EXTRAS.get(str(archetype or "").strip().lower(), ()))


def wire_street_vendor_item_pool(vendor_kind):
    return tuple(WIRE_STREET_VENDOR_POOL_EXTRAS.get(str(vendor_kind or "").strip().lower(), ()))


def wire_item_base_value(item_id, default=10):
    return int(WIRE_ITEM_BASE_VALUES.get(str(item_id or "").strip().lower(), int(default)))


def _quality_for_context(distribution_context, *, seed_token=""):
    context = str(distribution_context or "").strip().lower()
    if context in {"pawn_shop", "junk_market", "chop_shop", "gang_fence", "alley_market"}:
        choices = ("poor", "standard", "standard")
    elif context in {"backroom_market"}:
        choices = ("poor", "standard", "good")
    elif context in {"contractor_office", "electronics_shop", "comms_shop", "drone_shop", "brokerage", "data_center", "media_lab", "office", "tower"}:
        choices = ("standard", "standard", "good")
    else:
        choices = ("standard",)
    if not seed_token:
        return choices[0]
    return random.Random(f"wire-quality:{distribution_context}:{seed_token}").choice(choices)


def wire_distribution_metadata(
    item_id,
    base_metadata=None,
    *,
    source_context="wire_distribution",
    distribution_context="",
    seed_token="",
    item_catalog=None,
):
    item_key = str(item_id or "").strip().lower()
    metadata = dict(base_metadata or {})
    metadata.setdefault("source_context", source_context)
    metadata.setdefault("distribution_context", distribution_context)
    if seed_token:
        metadata.setdefault("distribution_seed", str(seed_token))
    metadata.setdefault("quality", _quality_for_context(distribution_context, seed_token=seed_token))

    if is_wire_interface_item(item_key, item_catalog=item_catalog):
        metadata.setdefault("manufacturer", wire_interface_profile_for_item(item_key, item_catalog=item_catalog).get("manufacturer", "unknown"))
        return normalize_wire_interface_metadata(
            metadata,
            item_id=item_key,
            profile=wire_interface_profile_for_item(item_key, item_catalog=item_catalog),
        )
    if is_wire_item(item_key, item_catalog=item_catalog):
        if item_key == "wire_corrupted_file":
            metadata.setdefault("corruption_tags", ("unstable", "market_burn"))
        if item_key == "wire_license_key" and str(distribution_context or "").strip().lower() in {"pawn_shop", "junk_market", "backroom_market"}:
            metadata.setdefault("license_source", "burned")
        return normalize_wire_entry_metadata(
            metadata,
            item_id=item_key,
            profile=wire_profile_for_item(item_key, item_catalog=item_catalog),
        )
    return metadata


def distributed_wire_item_ids():
    ids = set(WIRE_ITEM_BASE_VALUES)
    for rows in WIRE_STORE_POOL_EXTRAS.values():
        ids.update(str(item_id).strip().lower() for item_id, _weight in rows)
    for rows in WIRE_STREET_VENDOR_POOL_EXTRAS.values():
        ids.update(str(item_id).strip().lower() for item_id in rows)
    return tuple(sorted(item_id for item_id in ids if item_id))
