"""Shared environmental hazard definitions and metadata helpers."""

from __future__ import annotations


ENVIRONMENT_HAZARD_PROFILES = {
    "open_flame": {
        "name": "Open Flame",
        "fixture_type": "fire_hazard",
        "glyph": "*",
        "color": "warning",
        "damage": 2,
        "damage_kind": "condition",
        "status": "burning",
        "duration": 10,
        "cooldown_ticks": 4,
        "modifiers": {
            "move_speed_mult": -0.18,
            "incoming_damage_mult": 0.1,
            "safety_tick_delta": -0.22,
        },
        "immediate_needs": {
            "safety": -4.2,
            "energy": -0.8,
        },
        "player_note": "Open flame licks up around your feet.",
    },
    "smoke_choke": {
        "name": "Smoke Choke",
        "fixture_type": "smoke_hazard",
        "glyph": "~",
        "color": "shadow",
        "damage": 1,
        "damage_kind": "condition",
        "status": "smoke_choked",
        "duration": 12,
        "cooldown_ticks": 6,
        "modifiers": {
            "move_speed_mult": -0.1,
            "ranged_accuracy_mult": -0.12,
            "energy_tick_delta": -0.05,
            "safety_tick_delta": -0.14,
        },
        "immediate_needs": {
            "safety": -2.8,
            "energy": -1.2,
        },
        "player_note": "Smoke catches in your throat and eyes.",
    },
    "live_wire": {
        "name": "Live Wire",
        "fixture_type": "live_wire_hazard",
        "glyph": "!",
        "color": "property_asset",
        "damage": 2,
        "damage_kind": "condition",
        "status": "shock_exposure",
        "duration": 14,
        "cooldown_ticks": 9,
        "modifiers": {
            "move_speed_mult": -0.18,
            "ranged_accuracy_mult": -0.08,
            "safety_tick_delta": -0.12,
        },
        "immediate_needs": {
            "safety": -3.4,
            "energy": -0.7,
        },
        "player_note": "A live wire snaps through the standing water.",
    },
    "steam_leak": {
        "name": "Steam Leak",
        "fixture_type": "steam_leak_hazard",
        "glyph": "~",
        "color": "property_fixture",
        "damage": 1,
        "damage_kind": "condition",
        "status": "steam_scorched",
        "duration": 16,
        "cooldown_ticks": 11,
        "modifiers": {
            "move_speed_mult": -0.12,
            "incoming_damage_mult": 0.08,
            "safety_tick_delta": -0.09,
        },
        "immediate_needs": {
            "safety": -2.6,
        },
        "player_note": "A steam leak catches you with a scalding burst.",
    },
    "foul_drain": {
        "name": "Foul Drain",
        "fixture_type": "foul_drain_hazard",
        "glyph": "=",
        "color": "terrain_water",
        "damage": 1,
        "damage_kind": "condition",
        "status": "foul_air",
        "duration": 18,
        "cooldown_ticks": 13,
        "modifiers": {
            "move_speed_mult": -0.08,
            "energy_tick_delta": -0.06,
            "safety_tick_delta": -0.1,
        },
        "immediate_needs": {
            "safety": -2.1,
            "energy": -1.1,
        },
        "player_note": "Foul drain vapor turns your stomach.",
    },
    "spent_cell_blackwash": {
        "name": "Spent-cell Blackwash",
        "fixture_type": "electrochemical_waste_hazard",
        "glyph": "=",
        "color": "contaminant_electrochemical",
        "damage": 3,
        "damage_kind": "toxic_exposure",
        "status": "electrochemical_exposure",
        "duration": 28,
        "cooldown_ticks": 15,
        "modifiers": {
            "move_speed_mult": -0.12,
            "ranged_accuracy_mult": -0.1,
            "energy_tick_delta": -0.1,
            "safety_tick_delta": -0.16,
            "toxicity_tick_delta": 0.12,
        },
        "immediate_needs": {
            "safety": -5.2,
            "energy": -2.2,
        },
        "contaminant": {
            "class": "heavy_metals",
            "family": "electrochemical_waste",
            "signature": "spent_drone_cell_blackwash",
            "source_process": "drone_battery_refining_and_recovery",
            "persistence": "sediment_bound",
            "mobility": "waterborne",
            "bioreactive": True,
        },
        "display_description": (
            "Black slurry seeps through split, serial-marked drone-cell shells, "
            "leaving an oily green-gold edge along the low concrete."
        ),
        "player_note": "Oily blackwash bites at your skin and leaves a metallic taste.",
    },
}


def _int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _float_or_default(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def environment_hazard_profile(profile_id):
    profile_key = str(profile_id or "").strip().lower()
    profile = ENVIRONMENT_HAZARD_PROFILES.get(profile_key)
    if not isinstance(profile, dict):
        return {}
    return dict(profile)


def environment_hazard_player_note(profile_id, *, name=""):
    profile = environment_hazard_profile(profile_id)
    text = str(profile.get("player_note", "")).strip()
    if text:
        return text
    label = str(name or profile.get("name", "Hazard")).strip() or "Hazard"
    return f"{label} catches you off guard."


def normalize_environment_hazard_specs(source, *, fallback_z=0):
    if isinstance(source, dict):
        raw_specs = source.get("ambient_hazard_spawns", ())
    else:
        raw_specs = source

    normalized = []
    for spec in tuple(raw_specs or ()):
        if not isinstance(spec, dict):
            continue
        try:
            x = int(spec.get("x"))
            y = int(spec.get("y"))
            z = int(spec.get("z", fallback_z))
        except (TypeError, ValueError):
            continue
        profile_id = str(spec.get("profile", spec.get("hazard_profile", "")) or "").strip().lower()
        profile = environment_hazard_profile(profile_id)
        if not profile:
            continue
        normalized.append({
            "x": x,
            "y": y,
            "z": z,
            "profile": profile_id,
            "name": str(spec.get("name", profile.get("name", "Hazard"))).strip() or str(profile.get("name", "Hazard")).strip() or "Hazard",
            **{
                key: spec.get(key)
                for key in (
                    "contamination_origin",
                    "contamination_origin_name",
                    "contamination_source_archetype",
                    "contamination_source_context",
                    "contamination_load",
                    "technology_grade",
                    "manufacturing_efficiency",
                    "release_reason",
                    "release_id",
                    "source_eid",
                    "resident_remediation_eligible",
                )
                if spec.get(key) not in (None, "")
            },
        })
    return tuple(normalized)


def environment_hazard_asset_metadata(spec, *, key, linked_property_id=None):
    if not isinstance(spec, dict):
        return {}
    profile = environment_hazard_profile(spec.get("profile"))
    if not profile:
        return {}
    metadata = {
        "archetype": str(profile.get("fixture_type", "environment_hazard")).strip().lower() or "environment_hazard",
        "fixture_type": str(profile.get("fixture_type", "environment_hazard")).strip().lower() or "environment_hazard",
        "display_glyph": str(profile.get("glyph", "!"))[:1] or "!",
        "display_color": str(profile.get("color", "property_asset")).strip() or "property_asset",
        "cover_kind": "low",
        "cover_value": 0.0,
        "public": True,
        "hazard_profile": str(spec.get("profile", "")).strip().lower(),
        "hazard_label": str(spec.get("name", profile.get("name", "Hazard"))).strip() or str(profile.get("name", "Hazard")).strip() or "Hazard",
        "hazard_damage": _int_or_default(profile.get("damage", 0), 0),
        "hazard_damage_kind": str(profile.get("damage_kind", "condition")).strip().lower() or "condition",
        "hazard_status": str(profile.get("status", "")).strip().lower() or None,
        "hazard_duration": _int_or_default(profile.get("duration", 0), 0),
        "hazard_cooldown_ticks": _int_or_default(profile.get("cooldown_ticks", 10), 10),
        "hazard_immediate_needs": {
            str(need).strip().lower(): _float_or_default(delta, 0.0)
            for need, delta in dict(profile.get("immediate_needs", {}) or {}).items()
            if str(need).strip()
        },
        "chunk": key,
    }
    description = str(profile.get("display_description", "") or "").strip()
    if description:
        metadata["display_description"] = description
    contaminant = profile.get("contaminant")
    if isinstance(contaminant, dict) and contaminant:
        metadata["contaminant"] = dict(contaminant)
        metadata["contaminant_class"] = str(contaminant.get("class", "") or "").strip().lower() or None
        metadata["contaminant_family"] = str(contaminant.get("family", "") or "").strip().lower() or None
        metadata["contaminant_signature"] = str(contaminant.get("signature", "") or "").strip().lower() or None
        metadata["contaminant_bioreactive"] = bool(contaminant.get("bioreactive"))
    for field in (
        "contamination_origin",
        "contamination_origin_name",
        "contamination_source_archetype",
        "contamination_source_context",
        "contamination_load",
        "technology_grade",
        "manufacturing_efficiency",
        "release_reason",
        "release_id",
        "source_eid",
        "resident_remediation_eligible",
    ):
        if spec.get(field) not in (None, ""):
            metadata[field] = spec.get(field)
    if linked_property_id:
        metadata["linked_property_id"] = str(linked_property_id)
    return metadata
