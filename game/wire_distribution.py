"""Wire interface/software stock pools and distribution metadata helpers."""

from __future__ import annotations

import random

from game.organization_production import (
    organization_manufacturing_identity,
    organization_manufacturing_modifiers,
)
from game.organization_supply import manufacturing_organization_for_property

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
    "vehicle_bus_coupler": 165,
    "wire_talk_program": 55,
    "wire_route_probe_program": 90,
    "wire_handshake_breaker_program": 185,
    "wire_door_latch_program": 150,
    "wire_camera_loop_program": 140,
    "wire_data_siphon_shell_program": 175,
    "wire_spike_program": 130,
    "wire_ice_cutter_program": 165,
    "wire_trace_scrubber_program": 110,
    "wire_signal_cloak_program": 125,
    "wire_proxy_route_program": 105,
    "wire_tunnel_route_program": 145,
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
    "wire_shop": (
        ("cheap_deck", 18),
        ("skin_contact_rig", 10),
        ("wetwire_jack", 8),
        ("corp_interface_cable", 7),
        ("cracked_service_dongle", 8),
        ("drone_radio_bridge", 5),
        ("vehicle_bus_coupler", 5),
        ("wire_talk_program", 18),
        ("wire_route_probe_program", 16),
        ("wire_trace_scrubber_program", 10),
        ("wire_signal_cloak_program", 8),
        ("wire_proxy_route_program", 8),
        ("wire_tunnel_route_program", 6),
        ("wire_checksum_ward_program", 8),
        ("wire_panic_eject_program", 8),
        ("wire_sacrificial_shell_program", 6),
        ("wire_door_latch_program", 7),
        ("wire_camera_loop_program", 6),
        ("wire_data_siphon_shell_program", 5),
        ("wire_handshake_breaker_program", 4),
        ("wire_spike_program", 3),
        ("wire_ice_cutter_program", 3),
        ("wire_backup_image", 5),
        ("wire_license_key", 4),
        ("wire_access_key", 3),
    ),
    "contractor_office": (
        ("cracked_service_dongle", 8),
        ("corp_interface_cable", 6),
        ("cheap_deck", 7),
        ("wetwire_jack", 5),
        ("vehicle_bus_coupler", 3),
        ("wire_route_probe_program", 8),
        ("wire_talk_program", 6),
        ("wire_door_latch_program", 5),
        ("wire_camera_loop_program", 4),
        ("wire_trace_scrubber_program", 4),
        ("wire_proxy_route_program", 3),
        ("wire_tunnel_route_program", 2),
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
        ("wire_proxy_route_program", 4),
        ("wire_tunnel_route_program", 3),
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
        ("wire_proxy_route_program", 4),
        ("wire_tunnel_route_program", 2),
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
        ("wire_proxy_route_program", 2),
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
        ("vehicle_bus_coupler", 5),
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
        ("wire_proxy_route_program", 2),
        ("wire_license_key", 2),
    ),
    "data_center": (
        ("corp_interface_cable", 4),
        ("wetwire_jack", 2),
        ("wire_route_probe_program", 4),
        ("wire_data_siphon_shell_program", 3),
        ("wire_ice_cutter_program", 2),
        ("wire_tunnel_route_program", 2),
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
        ("wire_proxy_route_program", 2),
    ),
    "office": (
        ("cheap_deck", 2),
        ("corp_interface_cable", 2),
        ("wire_talk_program", 3),
        ("wire_route_probe_program", 2),
        ("wire_data_siphon_shell_program", 1),
        ("wire_trace_scrubber_program", 1),
        ("wire_proxy_route_program", 1),
    ),
    "tower": (
        ("corp_interface_cable", 4),
        ("wetwire_jack", 2),
        ("wire_route_probe_program", 4),
        ("wire_data_siphon_shell_program", 3),
        ("wire_signal_cloak_program", 2),
        ("wire_tunnel_route_program", 2),
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
        ("wire_proxy_route_program", 2),
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
        ("wire_proxy_route_program", 2),
        ("wire_sacrificial_shell_program", 2),
        ("wire_spike_program", 2),
    ),
    "chop_shop": (
        ("cheap_deck", 3),
        ("cracked_service_dongle", 5),
        ("drone_radio_bridge", 4),
        ("vehicle_bus_coupler", 5),
        ("wetwire_jack", 3),
        ("wire_route_probe_program", 4),
        ("wire_door_latch_program", 3),
        ("wire_camera_loop_program", 3),
        ("wire_handshake_breaker_program", 3),
        ("wire_spike_program", 2),
        ("wire_corrupted_file", 3),
    ),
    "backroom_market": (
        ("wetwire_jack", 3),
        ("cracked_service_dongle", 4),
        ("drone_radio_bridge", 2),
        ("vehicle_bus_coupler", 2),
        ("wire_door_latch_program", 3),
        ("wire_camera_loop_program", 3),
        ("wire_handshake_breaker_program", 3),
        ("wire_trace_scrubber_program", 2),
        ("wire_data_siphon_shell_program", 2),
        ("wire_spike_program", 2),
        ("wire_ice_cutter_program", 2),
        ("wire_signal_cloak_program", 2),
        ("wire_proxy_route_program", 3),
        ("wire_tunnel_route_program", 2),
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
        "wire_handshake_breaker_program",
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
        "wire_proxy_route_program",
        "wire_trace_fragment",
        "wire_corrupted_file",
    ),
    "vehicle_gun_vendor": (
        "drone_radio_bridge",
        "vehicle_bus_coupler",
        "cracked_service_dongle",
        "wire_camera_loop_program",
        "wire_handshake_breaker_program",
        "wire_spike_program",
        "wire_proxy_route_program",
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
    elif context in {"wire_shop", "contractor_office", "electronics_shop", "comms_shop", "drone_shop", "brokerage", "data_center", "media_lab", "office", "tower"}:
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
    sim=None,
    source_property=None,
    source_organization_eid=None,
):
    item_key = str(item_id or "").strip().lower()
    metadata = dict(base_metadata or {})
    metadata.setdefault("source_context", source_context)
    metadata.setdefault("distribution_context", distribution_context)
    if seed_token:
        metadata.setdefault("distribution_seed", str(seed_token))
    metadata.setdefault("quality", _quality_for_context(distribution_context, seed_token=seed_token))

    if is_wire_interface_item(item_key, item_catalog=item_catalog):
        interface_profile = wire_interface_profile_for_item(item_key, item_catalog=item_catalog)
        manufacturer_org_eid = source_organization_eid
        if manufacturer_org_eid is None and sim is not None and isinstance(source_property, dict):
            manufacturer_org_eid = manufacturing_organization_for_property(sim, source_property, commodity="wire")
        identity = (
            organization_manufacturing_identity(sim, manufacturer_org_eid)
            if sim is not None and manufacturer_org_eid is not None
            else {}
        )
        modifiers = (
            organization_manufacturing_modifiers(sim, manufacturer_org_eid)
            if sim is not None and manufacturer_org_eid is not None
            else {}
        )
        if identity:
            base_quality_rank = {"poor": -1, "standard": 0, "good": 1, "excellent": 2}.get(str(metadata.get("quality", "standard")).lower(), 0)
            quality_rank = max(-1, min(2, base_quality_rank + int(modifiers.get("quality_bias", 0))))
            metadata["quality"] = {-1: "poor", 0: "standard", 1: "good", 2: "excellent"}[quality_rank]
            metadata["manufacturer"] = identity.get("manufacturer") or identity.get("organization_name") or "unknown"
            metadata["manufacturer_organization_eid"] = int(manufacturer_org_eid)
            metadata["manufacturer_organization_key"] = identity.get("organization_key")
            metadata["manufacturer_organization_name"] = identity.get("organization_name")
            metadata["manufacturing_signature"] = identity.get("manufacturing_signature")
            metadata["product_motif"] = identity.get("product_motif")
            metadata["product_finish"] = identity.get("product_finish")
            metadata["style"] = identity.get("interface_style") or interface_profile.get("style", "plain")
            metadata["diagnostic_voice"] = dict(identity.get("diagnostic_voice") or {})
            metadata["organization_theme"] = {
                "id": f"organization:{identity.get('organization_key') or manufacturer_org_eid}",
                "label": identity.get("manufacturer") or identity.get("organization_name") or "organization line",
                "biome_style": identity.get("wire_biome_style") or "quiet_machine",
                "motif": identity.get("product_motif"),
                "tokens": {
                    "surface": "building_fill_dark",
                    "surface_alt": identity.get("secondary_render_key") or "building_fill",
                    "border": identity.get("primary_render_key") or "human_slate",
                    "accent": identity.get("accent_render_key") or "property_service",
                    "title": identity.get("primary_render_key") or "property_service",
                    "body": "default",
                    "muted": identity.get("secondary_render_key") or "human_slate",
                    "divider": identity.get("accent_render_key") or "property_service",
                    "selection": identity.get("accent_render_key") or "property_service",
                    "warning": "survival_meter_low",
                    "footer": identity.get("secondary_render_key") or "human_slate",
                },
            }
            metadata["warning_rating"] = max(0, min(5, int(interface_profile.get("warning_rating", 1)) + int(modifiers.get("signal_integrity", 0))))
            metadata["trace_resistance"] = max(0, min(5, int(interface_profile.get("trace_resistance", 0)) + int(modifiers.get("concealment", 0))))
            leakage_delta = int(round((int(modifiers.get("signal_integrity", 0)) + int(modifiers.get("consistency", 0))) / 2.0))
            metadata["signature_leakage"] = max(0, min(5, int(interface_profile.get("signature_leakage", 1)) - leakage_delta))
            metadata["range"] = max(0, int(interface_profile.get("range", 1)) + int(modifiers.get("signal_integrity", 0)))
            metadata["noise_floor"] = max(0, min(5, int(interface_profile.get("noise_floor", 0)) - int(modifiers.get("consistency", 0))))
            metadata["memory_speed"] = max(1, int(interface_profile.get("memory_speed", 1)) + int(modifiers.get("quality_bias", 0)) + int(modifiers.get("power_efficiency", 0)))
        else:
            metadata.setdefault("manufacturer", interface_profile.get("manufacturer", "unknown"))
        return normalize_wire_interface_metadata(
            metadata,
            item_id=item_key,
            profile=interface_profile,
        )
    if is_wire_item(item_key, item_catalog=item_catalog):
        manufacturer_org_eid = source_organization_eid
        if manufacturer_org_eid is None and sim is not None and isinstance(source_property, dict):
            manufacturer_org_eid = manufacturing_organization_for_property(sim, source_property, commodity="wire")
        identity = (
            organization_manufacturing_identity(sim, manufacturer_org_eid)
            if sim is not None and manufacturer_org_eid is not None
            else {}
        )
        if identity:
            metadata.setdefault("manufacturer", identity.get("manufacturer") or identity.get("organization_name"))
            metadata.setdefault("manufacturer_organization_eid", int(manufacturer_org_eid))
            metadata.setdefault("manufacturer_organization_key", identity.get("organization_key"))
            metadata.setdefault("manufacturer_organization_name", identity.get("organization_name"))
            metadata.setdefault("manufacturing_signature", identity.get("manufacturing_signature"))
            metadata.setdefault("product_motif", identity.get("product_motif"))
            metadata.setdefault("product_finish", identity.get("product_finish"))
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
