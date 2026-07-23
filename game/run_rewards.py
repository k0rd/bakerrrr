"""Successful-run reward file exporter.

The exporter writes ordinary custom-content examples into ``saves/rewards`` and
records a signed first-party receipt. The exported JSON stays optional: loading
it still goes through the public custom-content validator.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Any

from engine.persistence import SAVE_DIR
from game.json_metadata import SCHEMA_VERSION, wrap_object_document
from game.meaningful_objects_runtime import reward_object_profile
from game.public_content import public_area_types, public_building_archetype_ids, public_district_types


RUN_REWARD_GENERATOR_VERSION = "run_rewards_v2_world_culture"
RUN_REWARD_SCHEMA_VERSION = 2
RUN_REWARD_SIGNATURE_SALT = b"bakerrrr-earned-run-reward-v1"
REWARD_ROOT = SAVE_DIR / "rewards"
LEDGER_FILENAME = "earned_rewards.json"

_IDENTIFIER_RE = re.compile(r"[^a-z0-9_]+")


_ITEM_FAMILIES = (
    {
        "kind": "steady_charm",
        "label": "steady charm",
        "glyph": "*",
        "tags": ("consumable", "keepsake", "earned", "focus"),
        "effects": ({"type": "modify_need", "need": "safety", "delta": 14},),
    },
    {
        "kind": "runner_patch",
        "label": "runner patch",
        "glyph": "=",
        "tags": ("consumable", "keepsake", "earned", "energy"),
        "effects": ({"type": "modify_need", "need": "energy", "delta": 12},),
    },
    {
        "kind": "pocket_ration",
        "label": "pocket ration",
        "glyph": "%",
        "tags": ("consumable", "keepsake", "earned", "food"),
        "effects": ({"type": "modify_need", "need": "hunger", "delta": -16},),
    },
    {
        "kind": "rain_token",
        "label": "rain token",
        "glyph": "!",
        "tags": ("consumable", "keepsake", "earned", "drink"),
        "effects": ({"type": "modify_need", "need": "thirst", "delta": -16},),
    },
    {
        "kind": "soft_wrap",
        "label": "soft wrap",
        "glyph": "+",
        "tags": ("consumable", "keepsake", "earned", "medical"),
        "effects": ({"type": "restore_hp", "delta": 7},),
    },
    {
        "kind": "calling_card",
        "label": "calling card",
        "glyph": "?",
        "tags": ("consumable", "keepsake", "earned", "social"),
        "effects": ({"type": "modify_need", "need": "social", "delta": 12},),
    },
)

_PROFILE_FAMILIES = (
    {
        "kind": "market_afterglow",
        "label_words": ("After-Hours Market", "Back-Aisle Market", "Bright Counter"),
        "area_types": ("city",),
        "district_types": ("downtown", "entertainment", "residential"),
        "population_density": "high",
        "building_density": "medium",
        "water": "low",
        "building_weights": {
            "clothing_superstore": 1.8,
            "corner_store": 1.4,
            "restaurant": 1.3,
            "arcade": 1.2,
            "salon": 1.1,
            "tattoo_parlor": 1.0,
        },
        "service_building_weights": {
            "courier_office": 1.4,
            "employment_agency": 1.2,
            "restaurant": 1.2,
        },
    },
    {
        "kind": "canal_work",
        "label_words": ("Canal Work Blocks", "Wet Freight Row", "Low Bridge"),
        "area_types": ("city", "coastal"),
        "district_types": ("industrial", "slums", "downtown"),
        "population_density": "medium",
        "building_density": "high",
        "water": "medium",
        "building_weights": {
            "warehouse": 1.7,
            "freight_depot": 1.5,
            "machine_shop": 1.3,
            "laundromat": 1.1,
            "pawn_shop": 1.1,
        },
        "service_building_weights": {
            "tool_depot": 1.5,
            "courier_office": 1.3,
            "service_station": 1.2,
        },
    },
    {
        "kind": "quiet_residential",
        "label_words": ("Quiet Porch Grid", "Warm Window Blocks", "Close Stair"),
        "area_types": ("city", "frontier"),
        "district_types": ("residential", "downtown", "corporate"),
        "population_density": "medium",
        "building_density": "medium",
        "water": "low",
        "building_weights": {
            "apartment": 1.6,
            "house": 1.4,
            "bookshop": 1.1,
            "pharmacy": 1.2,
            "barbershop": 1.1,
        },
        "service_building_weights": {
            "recruitment_office": 1.2,
            "courier_office": 1.1,
            "pharmacy": 1.2,
        },
    },
    {
        "kind": "security_shadow",
        "label_words": ("Guarded Row", "Checkpoint Weather", "Clean Badge"),
        "area_types": ("city", "frontier"),
        "district_types": ("corporate", "military", "industrial"),
        "population_density": "medium",
        "building_density": "high",
        "water": "none",
        "building_weights": {
            "checkpoint": 1.5,
            "office": 1.4,
            "bank": 1.2,
            "courthouse": 1.1,
            "data_center": 1.1,
        },
        "service_building_weights": {
            "bounty_office": 1.4,
            "contractor_office": 1.2,
            "employment_agency": 1.1,
        },
    },
    {
        "kind": "roadside_favor",
        "label_words": ("Roadside Favor", "Relay Dust", "Truck-Stop Mercy"),
        "area_types": ("frontier", "wilderness", "coastal"),
        "district_types": ("industrial", "residential", "slums"),
        "population_density": "low",
        "building_density": "low",
        "water": "low",
        "building_weights": {
            "service_station": 1.8,
            "outfitter": 1.4,
            "surplus_store": 1.3,
            "tool_depot": 1.2,
            "street_kitchen": 1.1,
        },
        "service_building_weights": {
            "courier_office": 1.4,
            "employment_agency": 1.2,
            "service_station": 1.3,
        },
    },
    {
        "kind": "night_lights",
        "label_words": ("Night Lights", "Music Block", "Cheap Sign Glow"),
        "area_types": ("city",),
        "district_types": ("entertainment", "downtown", "slums"),
        "population_density": "high",
        "building_density": "medium",
        "water": "none",
        "building_weights": {
            "tavern": 1.5,
            "casino": 1.3,
            "music_venue": 1.4,
            "karaoke_box": 1.2,
            "restaurant": 1.2,
            "arcade": 1.2,
        },
        "service_building_weights": {
            "tavern": 1.4,
            "casino": 1.2,
            "courier_office": 1.1,
        },
    },
)

_ITEM_FAMILY_BY_KIND = {str(row["kind"]): row for row in _ITEM_FAMILIES}
_PROFILE_FAMILY_BY_KIND = {str(row["kind"]): row for row in _PROFILE_FAMILIES}


# A successful run currently does not know enough about every mastery domain to
# extract one exact achievement honestly.  Until that seam is ready, the run's
# visible facts choose a coherent culture family.  Every row below produces
# objects, a region bias, interior encounters, and a restrained visual dialect
# that can all circulate as ordinary future-world material.
_CULTURE_FAMILIES = (
    {
        "kind": "care_network",
        "label": "Care Network",
        "keywords": ("medic", "clinic", "medical", "hospital", "herbal", "botany", "rescue", "relief"),
        "item_kinds": ("soft_wrap", "rain_token", "steady_charm"),
        "profile_kinds": ("quiet_residential", "roadside_favor"),
        "provision_names": ("Ward Tea", "Night-Shift Wrap", "Relief Tin", "Clean-Counter Tonic"),
        "token_names": ("Blue Ward Token", "Quiet Queue Chit", "Relief Route Mark"),
        "curio_names": ("Mended Clinic Ribbon", "Little Mercy Ledger", "After-Hours Herb Tin"),
        "object_families": ("medical_herbal", "tokens_charms", "paper_books"),
        "distribution": {
            "store_archetypes": ("pharmacy", "biotech_clinic", "herbalist_shop", "soup_kitchen"),
            "loot_archetypes": ("pharmacy", "biotech_clinic", "field_hospital", "herbalist_shop"),
            "carrier_archetypes": ("pharmacy", "biotech_clinic", "field_hospital", "herbalist_shop", "soup_kitchen"),
        },
        "curiosities": (
            ("backroom_doctor", ("pharmacy", "biotech_clinic", "field_hospital"), ("back_office", "service_office", "storage"), "Clean wrapping and a handwritten queue mark a care shift that does not appear on the public hours."),
            ("quiet_contact", ("herbalist_shop", "soup_kitchen", "pharmacy"), ("back_office", "quiet_room", "stock_room"), "A tiny relief mark repeats on cups, parcels, and one carefully folded note."),
        ),
        "theme_tokens": {"accent": "flora_flower_white", "title": "human_accent", "divider": "flora_leaf", "footer": "human_olive"},
    },
    {
        "kind": "wire_archive",
        "label": "Wire Archive",
        "keywords": ("wire", "hack", "data", "records", "server", "surveillance", "software", "network"),
        "item_kinds": ("runner_patch", "steady_charm", "calling_card"),
        "profile_kinds": ("security_shadow", "canal_work"),
        "provision_names": ("Cold Rack Patch", "Archive Wake Strip", "Night Console Sachet"),
        "token_names": ("Dead Port Token", "Blue-Glass Access Chit", "Relay Route Mark"),
        "curio_names": ("Folded Audit Ribbon", "Burned Contact Ledger", "Pocket Cable Rosary"),
        "object_families": ("tools_parts", "tokens_charms", "paper_books"),
        "distribution": {
            "store_archetypes": ("wire_shop", "electronics_shop", "comms_shop"),
            "loot_archetypes": ("wire_shop", "data_center", "server_hub", "comms_shop"),
            "carrier_archetypes": ("wire_shop", "data_center", "server_hub", "comms_shop"),
        },
        "curiosities": (
            ("records_keeper", ("data_center", "server_hub", "wire_shop"), ("records_room", "server_room", "surveillance_room"), "A second index shadows the official archive, with route marks where names should be."),
            ("stash_ledger", ("electronics_shop", "comms_shop", "office"), ("back_office", "storage", "service_office"), "Someone has kept the obsolete part numbers and the doors they still open."),
        ),
        "theme_tokens": {"accent": "vehicle_glass", "title": "player", "divider": "item_metal", "footer": "human_denim"},
    },
    {
        "kind": "route_exchange",
        "label": "Route Exchange",
        "keywords": ("courier", "route", "delivery", "transit", "travel", "freight", "transport", "road"),
        "item_kinds": ("runner_patch", "pocket_ration", "rain_token"),
        "profile_kinds": ("roadside_favor", "canal_work"),
        "provision_names": ("Relay Supper", "Last-Stop Water", "Long Route Patch"),
        "token_names": ("Spare Platform Chit", "Low Bridge Token", "Third-Shift Fare Mark"),
        "curio_names": ("Folded Route Cloth", "Rain-Smudged Timetable", "Freight Desk Keepsake"),
        "object_families": ("containers", "tokens_charms", "paper_books"),
        "distribution": {
            "store_archetypes": ("courier_office", "metro_exchange", "service_station", "outfitter"),
            "loot_archetypes": ("courier_office", "freight_depot", "metro_exchange", "service_station"),
            "carrier_archetypes": ("courier_office", "freight_depot", "metro_exchange", "service_station"),
        },
        "curiosities": (
            ("transit_staff_roamer", ("metro_exchange", "freight_depot", "courier_office"), ("platform", "ticketing", "service_office"), "A hand-corrected route board preserves stops that the printed system has forgotten."),
            ("stash_ledger", ("service_station", "warehouse", "courier_office"), ("stock_room", "storage", "back_office"), "Old fare marks have been sorted by destination instead of value."),
        ),
        "theme_tokens": {"accent": "flora_flower_gold", "title": "human_rust", "divider": "terrain_trail", "footer": "human_olive"},
    },
    {
        "kind": "night_market",
        "label": "Night Market",
        "keywords": ("gang", "cult", "smuggl", "theft", "thief", "casino", "night", "covert"),
        "item_kinds": ("calling_card", "steady_charm", "pocket_ration"),
        "profile_kinds": ("night_lights", "market_afterglow"),
        "provision_names": ("Back-Aisle Supper", "Closing-Time Calm", "Lucky Counter Sweet"),
        "token_names": ("Red Table Chit", "Known Door Token", "After-Hours Favor Mark"),
        "curio_names": ("Velvet Pocket Ledger", "Cheap Sign Rosary", "Folded Market Ribbon"),
        "object_families": ("containers", "tokens_charms", "paper_books"),
        "distribution": {
            "store_archetypes": ("pawn_shop", "junk_market", "casino", "nightclub", "thrift_store"),
            "loot_archetypes": ("pawn_shop", "casino", "nightclub", "tavern", "pool_hall"),
            "carrier_archetypes": ("pawn_shop", "casino", "nightclub", "tavern", "pool_hall"),
        },
        "curiosities": (
            ("afterhours_pusher", ("nightclub", "casino", "tavern"), ("vip_lounge", "back_office", "service_corridor"), "A familiar little table mark appears only after the public counters close."),
            ("backroom_entrepreneur", ("pawn_shop", "junk_market", "pool_hall"), ("back_office", "stock_room", "storage"), "Bundles are counted by favor and neighborhood, not by price."),
        ),
        "theme_tokens": {"accent": "casino_chip", "title": "casino_gold", "divider": "casino_red", "footer": "human_wine"},
    },
    {
        "kind": "civic_memory",
        "label": "Civic Memory",
        "keywords": ("civic", "justice", "community", "investigat", "public", "neighborhood", "witness", "bureau"),
        "item_kinds": ("calling_card", "steady_charm", "soft_wrap"),
        "profile_kinds": ("quiet_residential", "security_shadow"),
        "provision_names": ("Long Meeting Tea", "Watch Desk Wrap", "Public Counter Mint"),
        "token_names": ("Open Session Chit", "Block Watch Token", "Stamped Queue Mark"),
        "curio_names": ("Dog-Eared Census Leaf", "Mended Notice Ribbon", "Little Public Ledger"),
        "object_families": ("paper_books", "tokens_charms", "paper_books"),
        "distribution": {
            "store_archetypes": ("courthouse", "office", "bookshop", "soup_kitchen"),
            "loot_archetypes": ("courthouse", "office", "checkpoint", "bookshop"),
            "carrier_archetypes": ("courthouse", "office", "checkpoint", "soup_kitchen"),
        },
        "curiosities": (
            ("records_keeper", ("courthouse", "office", "checkpoint"), ("records_office", "archive", "clerk_office"), "Corrections in three inks show where the public record and the lived block finally agreed."),
            ("quiet_contact", ("bookshop", "soup_kitchen", "office"), ("back_office", "meeting_room", "quiet_room"), "A neighborhood mark has been added beside names that still answer their doors."),
        ),
        "theme_tokens": {"accent": "actor_role_accent", "title": "objective", "divider": "building_edge_painted", "footer": "human_slate"},
    },
    {
        "kind": "workshop_line",
        "label": "Workshop Line",
        "keywords": ("drone", "tool", "mechanic", "repair", "salvage", "tinker", "manufactur", "workshop"),
        "item_kinds": ("runner_patch", "pocket_ration", "steady_charm"),
        "profile_kinds": ("canal_work", "roadside_favor"),
        "provision_names": ("Bench Tea", "Late Shift Ration", "Grease-Paper Patch"),
        "token_names": ("Tool Crib Chit", "Repaired Brass Token", "Third Bench Mark"),
        "curio_names": ("Matched Washer String", "Pocket Parts Ledger", "Mended Shop Ribbon"),
        "object_families": ("containers", "tokens_charms", "tools_parts"),
        "distribution": {
            "store_archetypes": ("tool_depot", "hardware_store", "machine_shop", "drone_shop", "junk_market"),
            "loot_archetypes": ("tool_depot", "machine_shop", "factory", "drone_shop", "recycling_plant"),
            "carrier_archetypes": ("tool_depot", "machine_shop", "factory", "drone_shop", "recycling_plant"),
        },
        "curiosities": (
            ("backroom_entrepreneur", ("machine_shop", "drone_shop", "tool_depot"), ("back_office", "service_office", "stock_room"), "A repaired-parts exchange is being run from the edge of the official work orders."),
            ("stash_ledger", ("factory", "recycling_plant", "junk_market"), ("storage", "locker_wall", "service_corridor"), "Discarded serials have been paired into working families in a grease-soft ledger."),
        ),
        "theme_tokens": {"accent": "item_metal", "title": "human_accent", "divider": "building_edge_gray_c", "footer": "human_charcoal"},
    },
)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _pretty_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clean_identifier(value: str, *, fallback: str = "reward") -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    text = _IDENTIFIER_RE.sub("_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or fallback


def _short_hash(value: Any, length: int = 16) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()[: int(length)]


def _path_display(path: Path) -> str:
    try:
        return path.resolve().relative_to(SAVE_DIR.parent.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def _json_write(path: Path, value: Any) -> str:
    data = _pretty_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _sha256_bytes(data)


def _text(value: Any, fallback: str = "") -> str:
    text = str(value if value is not None else fallback).strip()
    return text or fallback


def _safe_facilitator_context(*sources: Any) -> dict[str, Any]:
    allowed_text = ("role", "role_id", "career", "domain", "archetype", "service", "area_type", "district_type")
    allowed_lists = ("style_tags", "tags")
    safe: dict[str, Any] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in allowed_text:
            value = _text(source.get(key))
            if value:
                safe[key] = value[:64]
        for key in allowed_lists:
            values = source.get(key)
            if not isinstance(values, (list, tuple, set)):
                continue
            clean = []
            for value in values:
                text = _clean_identifier(value)
                if text and text not in clean:
                    clean.append(text)
                if len(clean) >= 6:
                    break
            if clean:
                safe[key] = clean
    return safe


def _source_payload(sim, player_eid, event_data: dict[str, Any]) -> dict[str, Any]:
    traits = getattr(sim, "world_traits", None)
    run_end = traits.get("run_end", {}) if isinstance(traits, dict) else {}
    stats = getattr(sim, "run_epilogue_stats", None)
    player_pos = None
    if player_eid is not None:
        try:
            from game.components import Position

            pos = sim.ecs.get(Position).get(player_eid)
            if pos is not None:
                player_pos = {"x": int(pos.x), "y": int(pos.y), "z": int(getattr(pos, "z", 0))}
        except Exception:
            player_pos = None
    objective_title = _text(event_data.get("objective_title"), _text(run_end.get("objective_title"), "Run Objective"))
    payload = {
        "seed": int(getattr(sim, "seed", 0) or 0),
        "outcome": _text(event_data.get("outcome"), _text(run_end.get("outcome"), "")).lower(),
        "reason": _text(event_data.get("reason"), _text(run_end.get("reason"), "")),
        "objective_title": objective_title,
        "tick": int(event_data.get("tick", getattr(sim, "tick", 0) or 0) or 0),
        "player_eid": int(player_eid) if player_eid is not None else None,
        "player_position": player_pos,
        "stats": {
            "facts": int((stats or {}).get("facts", 0) or 0) if isinstance(stats, dict) else 0,
            "visited_chunks": int((stats or {}).get("visited_chunks", 0) or 0) if isinstance(stats, dict) else 0,
            "casino_net": int((stats or {}).get("casino_net", 0) or 0) if isinstance(stats, dict) else 0,
        },
    }
    facilitator = _safe_facilitator_context(
        event_data.get("facilitator_context"),
        run_end.get("facilitator_context") if isinstance(run_end, dict) else None,
    )
    if facilitator:
        payload["facilitator_context"] = facilitator
    return payload


def _variant_index(seed_payload: Any, count: int, *, salt: str = "") -> int:
    if count <= 0:
        return 0
    digest = _short_hash({"salt": salt, "payload": seed_payload}, 12)
    return int(digest, 16) % int(count)


def _valid_subset(values, valid_values, fallback):
    valid = {str(value) for value in valid_values}
    result = [str(value) for value in values if str(value) in valid]
    if result:
        return result
    return [str(fallback)] if str(fallback) in valid else []


def _valid_weight_map(weights: dict[str, float], valid_ids) -> dict[str, float]:
    valid = {str(value) for value in valid_ids}
    return {
        str(key): float(value)
        for key, value in sorted((weights or {}).items())
        if str(key) in valid and float(value) > 0.0
    }


def _culture_source_text(source_payload: dict[str, Any]) -> str:
    chunks = [
        source_payload.get("objective_title", ""),
        source_payload.get("reason", ""),
    ]
    facilitator = source_payload.get("facilitator_context")
    if isinstance(facilitator, dict):
        for value in facilitator.values():
            if isinstance(value, (list, tuple, set)):
                chunks.extend(value)
            else:
                chunks.append(value)
    return " ".join(str(value or "").strip().lower() for value in chunks if str(value or "").strip())


def _select_culture_family(source_payload: dict[str, Any]) -> dict[str, Any]:
    source_text = _culture_source_text(source_payload)
    scored = []
    for row in _CULTURE_FAMILIES:
        score = sum(1 for keyword in row.get("keywords", ()) if str(keyword) in source_text)
        if score:
            scored.append((score, str(row["kind"]), row))
    if scored:
        best_score = max(row[0] for row in scored)
        finalists = [row[2] for row in scored if row[0] == best_score]
        return finalists[_variant_index(source_payload, len(finalists), salt="culture-semantic-tie")]
    return _CULTURE_FAMILIES[_variant_index(source_payload, len(_CULTURE_FAMILIES), salt="culture-fallback")]


def _distribution_profile(culture: dict[str, Any], slot: int) -> dict[str, Any]:
    source = culture.get("distribution") if isinstance(culture.get("distribution"), dict) else {}
    # Slots are all visible but not ubiquitous. Provisions circulate more
    # readily than tokens, and curios remain the rarest part of the dialect.
    weights = (18, 11, 7)
    profile = {
        key: list(values)
        for key, values in source.items()
        if key in {"store_archetypes", "loot_archetypes", "carrier_archetypes"}
    }
    profile["weight"] = weights[max(0, min(len(weights) - 1, int(slot)))]
    return profile


def _build_item_definitions(
    reward_id: str,
    source_payload: dict[str, Any],
    culture: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str], str]:
    provision_kind = culture["item_kinds"][
        _variant_index(source_payload, len(culture["item_kinds"]), salt=f"{culture['kind']}:provision-kind")
    ]
    provision_family = _ITEM_FAMILY_BY_KIND[str(provision_kind)]
    name_groups = (
        culture["provision_names"],
        culture["token_names"],
        culture["curio_names"],
    )
    suffixes = ("provision", "token", "curio")
    glyphs = (str(provision_family["glyph"]), "*", "?")
    tag_groups = (
        tuple(provision_family["tags"]) + ("world_culture",),
        ("token", "social", "keepsake", "earned", "world_culture"),
        ("junk", "token", "social", "keepsake", "earned", "world_culture"),
    )
    effect_groups = (
        [dict(effect) for effect in provision_family["effects"]],
        [],
        [],
    )
    items: dict[str, dict[str, Any]] = {}
    labels: list[str] = []
    for slot, suffix in enumerate(suffixes):
        item_id = f"{reward_id}_{slot + 1:02d}_{suffix}"
        names = name_groups[slot]
        name = str(names[_variant_index(source_payload, len(names), salt=f"{culture['kind']}:{suffix}:name")])
        family_hint = str(culture["object_families"][slot])
        item = {
            "name": name,
            "glyph": glyphs[slot],
            "stack_max": 1,
            "tags": list(dict.fromkeys(tag_groups[slot])),
            "category": "consumable" if slot == 0 else "misc",
            "legal_status": "legal",
            "object_profile": reward_object_profile(
                source_payload,
                f"{reward_id}:{suffix}",
                family_hint=family_hint,
            ),
            "effects": effect_groups[slot],
            "world_distribution": _distribution_profile(culture, slot),
        }
        items[item_id] = item
        labels.append(name)
    return items, labels, str(provision_family["label"])


def _build_world_profile(
    reward_id: str,
    source_payload: dict[str, Any],
    culture: dict[str, Any],
) -> tuple[str, dict[str, Any], str]:
    profile_kinds = tuple(culture.get("profile_kinds", ()))
    family_kind = profile_kinds[_variant_index(source_payload, len(profile_kinds), salt=f"{culture['kind']}:profile-family")]
    family = _PROFILE_FAMILY_BY_KIND[str(family_kind)]
    label_word = family["label_words"][_variant_index(source_payload, len(family["label_words"]), salt="profile-label")]
    profile_id = f"{reward_id}_area"
    valid_buildings = public_building_archetype_ids()
    profile = {
        "label": f"{label_word} Area Profile",
        "selection_weight": 1.25,
        "area_types": _valid_subset(family["area_types"], public_area_types(), "city"),
        "district_types": _valid_subset(family["district_types"], public_district_types(), "downtown"),
        "population_density": str(family["population_density"]),
        "building_density": str(family["building_density"]),
        "water": str(family["water"]),
        "building_weights": _valid_weight_map(family["building_weights"], valid_buildings),
        "service_building_weights": _valid_weight_map(family["service_building_weights"], valid_buildings),
    }
    return profile_id, profile, str(family["kind"])


def _build_room_curiosity_flavors(
    reward_id: str,
    culture: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    flavors = {}
    base_profiles = []
    for index, row in enumerate(culture.get("curiosities", ())):
        base_profile, archetypes, room_kinds, signal = row
        flavor_id = f"{reward_id}_{index + 1:02d}_room"
        flavors[flavor_id] = {
            "label": f"{culture['label']} {str(base_profile).replace('_', ' ').title()}",
            "base_profile": str(base_profile),
            "selection_weight": 1.35 if index == 0 else 0.9,
            "archetypes": list(archetypes),
            "room_kinds": list(room_kinds),
            "room_curiosity_signal": str(signal),
        }
        base_profiles.append(str(base_profile))
    return flavors, base_profiles


def _build_ui_theme(
    reward_id: str,
    culture: dict[str, Any],
    world_profile: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    theme_id = f"{reward_id}_theme"
    return theme_id, {
        "label": f"{culture['label']} Glass",
        "selection_weight": 1.0,
        "area_types": list(world_profile.get("area_types", ())),
        "district_types": list(world_profile.get("district_types", ())),
        "context_tags": [],
        "tokens": dict(culture.get("theme_tokens", {})),
    }


def _read_ledger(ledger_path: Path) -> dict[str, Any]:
    if not ledger_path.exists():
        return {"schema_version": RUN_REWARD_SCHEMA_VERSION, "rewards": []}
    try:
        raw = json.loads(ledger_path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": RUN_REWARD_SCHEMA_VERSION, "rewards": []}
    if not isinstance(raw, dict):
        return {"schema_version": RUN_REWARD_SCHEMA_VERSION, "rewards": []}
    rewards = raw.get("rewards")
    if not isinstance(rewards, list):
        rewards = []
    return {
        "schema_version": int(raw.get("schema_version", RUN_REWARD_SCHEMA_VERSION) or RUN_REWARD_SCHEMA_VERSION),
        "rewards": [row for row in rewards if isinstance(row, dict)],
    }


def load_reward_ledger(*, export_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(export_root) if export_root is not None else REWARD_ROOT
    return _read_ledger(root / LEDGER_FILENAME)


def _receipt_signature_payload(receipt: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(receipt)
    payload.pop("signature", None)
    return payload


def sign_reward_receipt(receipt: dict[str, Any]) -> str:
    return hmac.new(
        RUN_REWARD_SIGNATURE_SALT,
        _canonical_json_bytes(_receipt_signature_payload(receipt)),
        hashlib.sha256,
    ).hexdigest()


def _ledger_row_from_receipt(receipt: dict[str, Any], *, receipt_path: Path, readme_path: Path) -> dict[str, Any]:
    row = copy.deepcopy(receipt)
    row["receipt_path"] = _path_display(receipt_path)
    row["readme_path"] = _path_display(readme_path)
    return row


def _existing_row_for_source(ledger: dict[str, Any], source_run_id: str) -> dict[str, Any] | None:
    for row in ledger.get("rewards", ()) or ():
        if isinstance(row, dict) and str(row.get("source_run_id", "")) == str(source_run_id):
            return row
    return None


_DOMAIN_LABELS = {
    "items": "Circulating objects",
    "world_profiles": "Area profile",
    "room_curiosity_flavors": "Interior flavors",
    "ui_themes": "Local visual dialect",
}


def _summary_lines(
    label: str,
    files: list[dict[str, Any]],
    receipt_path: Path,
    readme_path: Path,
) -> list[str]:
    lines = [
        "Generated world-growth reward:",
        f"  {label} exported as optional custom content.",
    ]
    for record in files:
        domain = str(record.get("domain", "") or "")
        path = Path(str(record.get("path", "") or ""))
        lines.append(f"  {_DOMAIN_LABELS.get(domain, domain.replace('_', ' ').title())}: {_path_display(path)}")
    lines.extend((
        f"  Receipt: {_path_display(receipt_path)}",
        f"  Install note: {_path_display(readme_path)}",
    ))
    return lines


def _readme_text(label: str, files: list[dict[str, Any]], receipt_path: Path) -> str:
    lines = [
        f"Generated world-growth reward: {label}",
        "",
        "These files are optional. They are not enabled automatically.",
        "Together they add one coherent bit of culture to later worlds; they do not grant a starting bonus.",
        "",
    ]
    for record in files:
        domain = str(record.get("domain", "") or "")
        path = Path(str(record.get("path", "") or ""))
        lines.extend((
            f"To install {_DOMAIN_LABELS.get(domain, domain.replace('_', ' ')).lower()}, copy:",
            f"  {_path_display(path)}",
            "to:",
            f"  config/custom_content/{domain}/",
            "",
        ))
    lines.extend((
        "The receipt proves this bundle was generated by BAKERRRR:",
        f"  {_path_display(receipt_path)}",
        "",
        "The objects enter matching shops, loose interior loot, and resident inventories through",
        "their world_distribution profiles. The area, room, and visual files use the same public",
        "custom-content schemas. You can install the bundle, inspect it as an example, or leave it unused.",
        "",
    ))
    return "\n".join(lines)


def _result_from_row(row: dict[str, Any], *, export_root: Path) -> dict[str, Any]:
    reward_id = str(row.get("reward_id", "") or "")
    artifacts = list(row.get("artifacts", ()) or ())
    files = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        domain = str(artifact.get("domain", "") or "")
        rel_path = str(artifact.get("path", f"{domain}/{reward_id}.json") or f"{domain}/{reward_id}.json")
        files.append({
            "domain": domain,
            "path": str(export_root / rel_path),
            "loaded_ids": list(artifact.get("loaded_ids", ()) or ()),
        })
    receipt_path = export_root / "receipts" / f"{reward_id}.json"
    readme_path = Path(str(row.get("readme_path", export_root / f"{reward_id}_README.txt")))
    label = str(row.get("reward_label", reward_id.replace("_", " ").title()) or reward_id)
    return {
        "exported": False,
        "reward_id": reward_id,
        "reward_label": label,
        "files": files,
        "receipt": copy.deepcopy(row),
        "receipt_path": str(receipt_path),
        "ledger_path": str(export_root / LEDGER_FILENAME),
        "readme_path": str(readme_path),
        "summary_lines": _summary_lines(label, files, receipt_path, readme_path),
    }


def export_success_reward_bundle(sim, player_eid=None, event_data=None, *, export_root: Path | str | None = None) -> dict[str, Any]:
    """Export one optional reward bundle for a successful run.

    This function refuses non-success outcomes so tests and duplicate
    conclusion paths stay harmless.
    """

    event_data = dict(event_data or {})
    outcome = _text(event_data.get("outcome")).lower()
    if outcome != "success":
        return {"exported": False, "reason": "not_success", "summary_lines": []}
    from game.custom_content import custom_content_allows_post_game_traces, custom_content_post_game_block_lines

    if not custom_content_allows_post_game_traces(sim):
        return {
            "exported": False,
            "reason": "unreceipted_custom_content",
            "summary_lines": custom_content_post_game_block_lines(sim),
        }
    root = Path(export_root or getattr(sim, "run_reward_export_root", None) or REWARD_ROOT)
    source_payload = _source_payload(sim, player_eid, event_data)
    source_payload["outcome"] = "success"
    source_run_id = f"run_{_short_hash({'source': source_payload, 'version': RUN_REWARD_GENERATOR_VERSION}, 20)}"
    reward_id = f"earned_{_short_hash({'source_run_id': source_run_id, 'domain': 'reward_bundle'}, 16)}"

    ledger_path = root / LEDGER_FILENAME
    ledger = _read_ledger(ledger_path)
    existing = _existing_row_for_source(ledger, source_run_id)
    if existing is not None:
        return _result_from_row(existing, export_root=root)

    culture = _select_culture_family(source_payload)
    item_defs, item_labels, provision_label = _build_item_definitions(reward_id, source_payload, culture)
    profile_id, profile_def, profile_kind = _build_world_profile(reward_id, source_payload, culture)
    flavor_defs, flavor_kinds = _build_room_curiosity_flavors(reward_id, culture)
    theme_id, theme_def = _build_ui_theme(reward_id, culture, profile_def)
    reward_label = f"{culture['label']} World Legacy"

    item_doc = wrap_object_document(item_defs, schema_version=SCHEMA_VERSION)
    profile_doc = wrap_object_document({profile_id: profile_def}, schema_version=SCHEMA_VERSION)
    flavor_doc = wrap_object_document(flavor_defs, schema_version=SCHEMA_VERSION)
    theme_doc = wrap_object_document({theme_id: theme_def}, schema_version=SCHEMA_VERSION)

    item_path = root / "items" / f"{reward_id}.json"
    profile_path = root / "world_profiles" / f"{reward_id}.json"
    flavor_path = root / "room_curiosity_flavors" / f"{reward_id}.json"
    theme_path = root / "ui_themes" / f"{reward_id}.json"
    receipt_path = root / "receipts" / f"{reward_id}.json"
    readme_path = root / f"{reward_id}_README.txt"

    item_hash = _json_write(item_path, item_doc)
    profile_hash = _json_write(profile_path, profile_doc)
    flavor_hash = _json_write(flavor_path, flavor_doc)
    theme_hash = _json_write(theme_path, theme_doc)

    item_ids = list(item_defs)
    flavor_ids = list(flavor_defs)
    files = [
        {"domain": "items", "path": str(item_path), "loaded_ids": item_ids},
        {"domain": "world_profiles", "path": str(profile_path), "loaded_ids": [profile_id]},
        {"domain": "room_curiosity_flavors", "path": str(flavor_path), "loaded_ids": flavor_ids},
        {"domain": "ui_themes", "path": str(theme_path), "loaded_ids": [theme_id]},
    ]

    receipt = {
        "schema_version": RUN_REWARD_SCHEMA_VERSION,
        "reward_id": reward_id,
        "reward_label": reward_label,
        "source_run_id": source_run_id,
        "generator_version": RUN_REWARD_GENERATOR_VERSION,
        "content_domain": "custom_content",
        "custom_content_schema_version": SCHEMA_VERSION,
        "reward_family": {
            "culture": str(culture["kind"]),
            "item": provision_label,
            "items": item_labels,
            "world_profile": profile_kind,
            "room_curiosity_flavors": flavor_kinds,
            "ui_theme": str(culture["kind"]),
        },
        "source": source_payload,
        "artifacts": [
            {
                "domain": "items",
                "path": f"items/{reward_id}.json",
                "loaded_ids": item_ids,
                "sha256": item_hash,
            },
            {
                "domain": "world_profiles",
                "path": f"world_profiles/{reward_id}.json",
                "loaded_ids": [profile_id],
                "sha256": profile_hash,
            },
            {
                "domain": "room_curiosity_flavors",
                "path": f"room_curiosity_flavors/{reward_id}.json",
                "loaded_ids": flavor_ids,
                "sha256": flavor_hash,
            },
            {
                "domain": "ui_themes",
                "path": f"ui_themes/{reward_id}.json",
                "loaded_ids": [theme_id],
                "sha256": theme_hash,
            },
        ],
    }
    receipt["signature"] = sign_reward_receipt(receipt)
    _json_write(receipt_path, receipt)
    readme_path.write_text(_readme_text(reward_label, files, receipt_path), encoding="utf-8")

    ledger["schema_version"] = RUN_REWARD_SCHEMA_VERSION
    ledger["rewards"] = [row for row in ledger.get("rewards", ()) or () if str(row.get("source_run_id", "")) != source_run_id]
    ledger["rewards"].append(_ledger_row_from_receipt(receipt, receipt_path=receipt_path, readme_path=readme_path))
    _json_write(ledger_path, ledger)

    return {
        "exported": True,
        "reward_id": reward_id,
        "reward_label": reward_label,
        "item_id": item_ids[0],
        "item_ids": item_ids,
        "profile_id": profile_id,
        "room_curiosity_ids": flavor_ids,
        "ui_theme_id": theme_id,
        "files": files,
        "receipt": copy.deepcopy(receipt),
        "receipt_path": str(receipt_path),
        "ledger_path": str(ledger_path),
        "readme_path": str(readme_path),
        "summary_lines": _summary_lines(reward_label, files, receipt_path, readme_path),
    }


def verify_reward_receipt(receipt: dict[str, Any] | str | Path, *, export_root: Path | str | None = None) -> bool:
    """Return True when a receipt signature and artifact hashes still match."""

    root = Path(export_root) if export_root is not None else REWARD_ROOT
    if isinstance(receipt, (str, Path)):
        try:
            receipt = json.loads(Path(receipt).read_text(encoding="utf-8"))
        except Exception:
            return False
    if not isinstance(receipt, dict):
        return False
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return False
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            return False
        rel_path = Path(str(artifact.get("path", "") or ""))
        if rel_path.is_absolute() or ".." in rel_path.parts:
            return False
        path = root / rel_path
        if not path.exists():
            return False
        actual_hash = _sha256_bytes(path.read_bytes())
        if not hmac.compare_digest(actual_hash, str(artifact.get("sha256", "") or "")):
            return False
    signature = str(receipt.get("signature", "") or "")
    if not signature:
        return False
    return hmac.compare_digest(signature, sign_reward_receipt(receipt))
