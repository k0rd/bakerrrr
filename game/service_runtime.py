"""Shared casino and service runtime helpers.

This module holds the shared service-stack behavior that used to live inside
``game/systems.py`` so the extracted service systems can depend on a focused
runtime seam instead of reaching back into the monolith.
"""

import itertools
import random
from collections import Counter

from engine.buildings import layout_chunk_building, world_building_id
from engine.derived_facts import cached_derived_fact
from engine.sites import layout_chunk_site
from game.components import AI, NPCNeeds, Occupation, PlayerAssets, Position
from game.color_words import casino_color_word
from game.flora_runtime import load_flora_catalog
from game.organizations import occupation_targets_property, property_org_members
from game.population import work_shift_active
from game.property_runtime import (
    property_covering as _property_covering,
    property_focus_position as _property_focus_position,
    property_is_storefront as _property_is_storefront,
    storefront_service_mode as _storefront_service_mode,
)
from game.slot_machine import (
    SLOT_BONUS_WILD_WEIGHT_SCALE,
    normalize_slot_bonus_wild_weight_scale,
    resolve_bakerrrr_slot,
    slot_seed_contract,
)
from game.system_support.entity_naming import _entity_display_name
from game.vehicles import roll_vehicle_paint_key, roll_vehicle_profile
from ui.text_attrs import A_BOLD


def _int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _manhattan(ax, ay, bx, by):
    return abs(ax - bx) + abs(ay - by)


def _clamp(value, lo=0.0, hi=100.0):
    return max(lo, min(hi, value))


def _building_site_service_seed_token(chunk_x, chunk_y, building, *, building_index=0):
    local_building_id = ""
    if isinstance(building, dict):
        local_building_id = str(building.get("building_id", "") or "").strip()
    if not local_building_id:
        local_building_id = str(int(building_index))
    return f"{int(chunk_x)}:{int(chunk_y)}:building:{local_building_id}"


def _site_service_seed_token(chunk_x, chunk_y, site, *, site_index=0):
    site_kind = "site"
    site_id = ""
    if isinstance(site, dict):
        site_kind = str(site.get("kind", site_kind)).strip().lower() or "site"
        site_id = str(site.get("site_id", "") or "").strip()
    if not site_id:
        site_id = str(int(site_index))
    return f"{int(chunk_x)}:{int(chunk_y)}:site:{site_kind}:{site_id}"


def _line_text(line):
    if isinstance(line, dict):
        return str(line.get("text", ""))
    return str(line)


def _segment(text, *, color=None, attrs=0, **extras):
    segment = {
        "text": str(text),
        "color": color,
        "attrs": int(attrs or 0),
    }
    for key, value in extras.items():
        segment[str(key)] = value
    return segment


def _segments_text(segments):
    return "".join(str(segment.get("text", "")) for segment in segments or () if isinstance(segment, dict))


def _rich_line(segments, text=None):
    normalized = []
    for segment in segments or ():
        if not isinstance(segment, dict):
            continue
        seg_text = str(segment.get("text", ""))
        if not seg_text:
            continue
        extras = {
            key: value
            for key, value in segment.items()
            if key not in {"text", "color", "attrs"}
        }
        normalized.append(_segment(
            seg_text,
            color=segment.get("color"),
            attrs=segment.get("attrs", 0),
            **extras,
        ))
    plain = str(text) if text is not None else _segments_text(normalized)
    return {
        "text": plain,
        "segments": normalized,
    }


def _legend_line(text, glyph=None, color=None, prefix="", attrs=0):
    segments = []
    plain = ""
    prefix = str(prefix)
    if prefix:
        segments.append(_segment(prefix))
        plain += prefix
    glyph_text = str(glyph)[:1] if glyph not in (None, "") else ""
    if glyph_text:
        segments.append(_segment(glyph_text, color=color, attrs=attrs, inline_glyph=True))
        plain += glyph_text
        if text:
            segments.append(_segment(" "))
            plain += " "
    text = str(text)
    if text:
        segments.append(_segment(text))
        plain += text
    return _rich_line(segments, text=plain)


def _tick_duration_label(sim, ticks):
    try:
        total_ticks = int(ticks)
    except (TypeError, ValueError):
        total_ticks = 0
    total_ticks = max(0, total_ticks)
    if total_ticks <= 0:
        return "0t"

    world_traits = getattr(sim, "world_traits", {})
    clock = world_traits.get("clock", {}) if isinstance(world_traits, dict) else {}
    try:
        ticks_per_hour = int(clock.get("ticks_per_hour", 600))
    except (TypeError, ValueError, AttributeError):
        ticks_per_hour = 600
    ticks_per_hour = max(60, ticks_per_hour)

    hours = total_ticks / float(ticks_per_hour)
    if hours >= 1.0:
        rounded = round(hours, 1)
        if abs(rounded - int(rounded)) < 0.05:
            return f"{int(round(rounded))}h"
        return f"{rounded:.1f}h"
    return f"{total_ticks}t"


def _sentence_from_note(note):
    text = str(note or "").strip()
    if not text:
        return ""
    text = text[:1].upper() + text[1:]
    if text[-1] not in ".!?":
        text += "."
    return text


RAIL_TRANSIT_SEARCH_RADIUS = 12
RAIL_TRANSIT_MENU_LIMIT = 8
RAIL_TRANSIT_CITY_TOKEN_MAX_DISTANCE = 4
RAIL_TRANSIT_BASE_COST = 8
RAIL_TRANSIT_COST_PER_CHUNK = 3
BUS_TRANSIT_SEARCH_RADIUS = 6
BUS_TRANSIT_MENU_LIMIT = 8
BUS_TRANSIT_TOKEN_DISTANCE_STEP = 3
SHUTTLE_TRANSIT_SEARCH_RADIUS = 3
SHUTTLE_TRANSIT_MENU_LIMIT = 6
SHUTTLE_TRANSIT_TOKEN_DISTANCE_STEP = 1
FERRY_TRANSIT_SEARCH_RADIUS = 10
FERRY_TRANSIT_MENU_LIMIT = 6
FERRY_TRANSIT_TOKEN_DISTANCE_STEP = 2
COACH_TRANSIT_SEARCH_RADIUS = 18
COACH_TRANSIT_MENU_LIMIT = 8
COACH_TRANSIT_TOKEN_DISTANCE_STEP = 3
COACH_TRANSIT_FAR_PROBE_COUNT = 10
COACH_TRANSIT_FAR_PROBE_MIN_DISTANCE = 8

TRANSIT_SERVICE_PROFILES = {
    "rail_transit": {
        "title": "Rail",
        "service_label": "rail travel",
        "menu_label": "Take the train",
        "subtitle": "Station departures",
        "summary_lines": (
            "Travel is station to station only. You will arrive at the destination exchange, not at your final address.",
            "City pass tokens cover shorter hops. Transit daypasses cover any listed line.",
        ),
        "no_destinations_line": "No outbound rail stations are posted from {prop_name} right now.",
        "invalid_destination_lines": (
            "That destination board changed before you boarded.",
            "Pick a fresh station from the departures list.",
        ),
        "leave_vehicle_lines": (
            "Leave your vehicle before boarding rail.",
            "Transit is station to station, not car to station.",
        ),
        "blocked_no_fare_lines": (
            "Fare to {destination_name} is {fare_label}.",
            "You only have {inventory_label} on hand.",
        ),
        "success_lines": (
            "You ride out from {prop_name} and pull in at {destination_name}.",
            "{distance} chunks by rail.",
        ),
        "log_prefix": "Rail",
        "travel_mode": "rail",
        "node_archetypes": frozenset({"metro_exchange"}),
        "scan_buildings": True,
        "scan_sites": False,
        "search_radius": RAIL_TRANSIT_SEARCH_RADIUS,
        "menu_limit": RAIL_TRANSIT_MENU_LIMIT,
        "base_cost": RAIL_TRANSIT_BASE_COST,
        "cost_per_chunk": RAIL_TRANSIT_COST_PER_CHUNK,
        "city_token_max_distance": RAIL_TRANSIT_CITY_TOKEN_MAX_DISTANCE,
        "token_only": False,
        "allow_daypass": True,
        "prefer_tokens": False,
        "travel_base_hours": 0.35,
        "travel_hours_per_chunk": 0.25,
    },
    "bus_transit": {
        "title": "Bus",
        "service_label": "bus travel",
        "menu_label": "Catch the bus",
        "subtitle": "Posted routes",
        "summary_lines": (
            "Buses run stop to stop between posted transit nodes. You will arrive at the destination stop, not a private address.",
            "Local bus rides take city tokens. Transit daypasses still cover the line if you want to save your tokens.",
        ),
        "no_destinations_line": "No outbound bus routes are posted from {prop_name} right now.",
        "invalid_destination_lines": (
            "That bus route rolled off the board before departure.",
            "Pick a fresh stop from the posted routes.",
        ),
        "leave_vehicle_lines": (
            "Leave your vehicle before boarding the bus.",
            "Bus travel is stop to stop, not car to stop.",
        ),
        "blocked_no_fare_lines": (
            "Bus fare to {destination_name} is {fare_label}.",
            "You only have {inventory_label} on hand.",
        ),
        "success_lines": (
            "You catch the bus out from {prop_name} and step off at {destination_name}.",
            "{distance} chunks by bus.",
        ),
        "log_prefix": "Bus",
        "travel_mode": "bus",
        "node_archetypes": frozenset({"metro_exchange", "relay_post", "truck_stop"}),
        "scan_buildings": True,
        "scan_sites": True,
        "search_radius": BUS_TRANSIT_SEARCH_RADIUS,
        "menu_limit": BUS_TRANSIT_MENU_LIMIT,
        "token_only": True,
        "allow_daypass": True,
        "prefer_tokens": True,
        "token_distance_step": BUS_TRANSIT_TOKEN_DISTANCE_STEP,
        "max_token_cost": 3,
        "travel_base_hours": 0.25,
        "travel_hours_per_chunk": 0.18,
    },
    "shuttle_transit": {
        "title": "Shuttle",
        "service_label": "shuttle travel",
        "menu_label": "Book a shuttle",
        "subtitle": "Short-hop transfers",
        "summary_lines": (
            "Shuttles handle short transfers between posted support stops. They are for local hops, not for replacing your own wheels.",
            "Shuttle rides take city tokens. Transit daypasses cover the seat if you are already riding on one.",
        ),
        "no_destinations_line": "No shuttle transfers are posted from {prop_name} right now.",
        "invalid_destination_lines": (
            "That shuttle transfer cleared before you could take it.",
            "Pick a fresh short-hop stop from the board.",
        ),
        "leave_vehicle_lines": (
            "Leave your vehicle before taking a shuttle.",
            "Shuttles handle stop to stop transfers, not vehicle hauling.",
        ),
        "blocked_no_fare_lines": (
            "Shuttle fare to {destination_name} is {fare_label}.",
            "You only have {inventory_label} on hand.",
        ),
        "success_lines": (
            "A shuttle rolls out from {prop_name} and drops you at {destination_name}.",
            "{distance} chunks by shuttle.",
        ),
        "log_prefix": "Shuttle",
        "travel_mode": "shuttle",
        "node_archetypes": frozenset({"relay_post", "truck_stop", "roadhouse", "dock_shack"}),
        "scan_buildings": True,
        "scan_sites": True,
        "search_radius": SHUTTLE_TRANSIT_SEARCH_RADIUS,
        "menu_limit": SHUTTLE_TRANSIT_MENU_LIMIT,
        "token_only": True,
        "allow_daypass": True,
        "prefer_tokens": True,
        "token_distance_step": SHUTTLE_TRANSIT_TOKEN_DISTANCE_STEP,
        "max_token_cost": 2,
        "travel_base_hours": 0.18,
        "travel_hours_per_chunk": 0.14,
    },
    "ferry_transit": {
        "title": "Ferry",
        "service_label": "ferry travel",
        "menu_label": "Take the ferry",
        "subtitle": "Waterfront departures",
        "summary_lines": (
            "Ferries run landing to landing between posted waterfront stops. You will arrive at the destination landing, not a private berth.",
            "Longer crossings take city tokens. Transit daypasses cover the passage if you already have one.",
        ),
        "no_destinations_line": "No outbound ferry departures are posted from {prop_name} right now.",
        "invalid_destination_lines": (
            "That ferry departure cleared off the board before boarding.",
            "Pick a fresh landing from the posted crossings.",
        ),
        "leave_vehicle_lines": (
            "Leave your vehicle before boarding the ferry.",
            "Ferry travel is landing to landing, not vehicle hauling.",
        ),
        "blocked_no_fare_lines": (
            "Ferry fare to {destination_name} is {fare_label}.",
            "You only have {inventory_label} on hand.",
        ),
        "success_lines": (
            "You board at {prop_name} and come ashore at {destination_name}.",
            "{distance} chunks by ferry.",
        ),
        "log_prefix": "Ferry",
        "travel_mode": "ferry",
        "node_archetypes": frozenset({"dock_shack", "ferry_post", "tide_station"}),
        "scan_buildings": True,
        "scan_sites": True,
        "search_radius": FERRY_TRANSIT_SEARCH_RADIUS,
        "menu_limit": FERRY_TRANSIT_MENU_LIMIT,
        "token_only": True,
        "allow_daypass": True,
        "prefer_tokens": False,
        "token_distance_step": FERRY_TRANSIT_TOKEN_DISTANCE_STEP,
        "max_token_cost": 5,
        "travel_base_hours": 0.45,
        "travel_hours_per_chunk": 0.28,
    },
    "coach_transit": {
        "title": "Coach",
        "service_label": "regional coach travel",
        "menu_label": "Take the coach",
        "subtitle": "Regional departures",
        "summary_lines": (
            "Coaches run stop to stop between regional road hubs. You will arrive at the destination stop, not a private address.",
            "Long rides take city tokens. Transit daypasses cover the seat if you already have one.",
        ),
        "no_destinations_line": "No outbound coach departures are posted from {prop_name} right now.",
        "invalid_destination_lines": (
            "That coach departure cleared before boarding.",
            "Pick a fresh regional stop from the board.",
        ),
        "leave_vehicle_lines": (
            "Leave your vehicle before boarding the coach.",
            "Coaches carry passengers, not your car.",
        ),
        "blocked_no_fare_lines": (
            "Coach fare to {destination_name} is {fare_label}.",
            "You only have {inventory_label} on hand.",
        ),
        "success_lines": (
            "You ride the coach out from {prop_name} and step down at {destination_name}.",
            "{distance} chunks by coach.",
        ),
        "log_prefix": "Coach",
        "travel_mode": "coach",
        "node_archetypes": frozenset({"relay_post", "truck_stop", "roadhouse"}),
        "scan_buildings": True,
        "scan_sites": True,
        "search_radius": COACH_TRANSIT_SEARCH_RADIUS,
        "menu_limit": COACH_TRANSIT_MENU_LIMIT,
        "token_only": True,
        "allow_daypass": True,
        "prefer_tokens": False,
        "distance_sort": "far",
        "preferred_min_distance": COACH_TRANSIT_FAR_PROBE_MIN_DISTANCE,
        "require_preferred_distance": True,
        "far_probe_count": COACH_TRANSIT_FAR_PROBE_COUNT,
        "far_probe_min_distance": COACH_TRANSIT_FAR_PROBE_MIN_DISTANCE,
        "token_base_cost": 2,
        "token_distance_step": COACH_TRANSIT_TOKEN_DISTANCE_STEP,
        "max_token_cost": 8,
        "travel_base_hours": 0.9,
        "travel_hours_per_chunk": 0.42,
    },
}
TRANSIT_SERVICE_IDS = tuple(TRANSIT_SERVICE_PROFILES.keys())


def _building_property_id(sim, building_id):
    building_id = str(building_id or "").strip()
    if not building_id:
        return ""
    for prop in getattr(sim, "properties", {}).values():
        if not isinstance(prop, dict):
            continue
        metadata = prop.get("metadata")
        if not isinstance(metadata, dict):
            continue
        if str(metadata.get("building_id", "") or "").strip() == building_id:
            return str(prop.get("id", "") or "").strip()
    return ""


def _site_property_id(sim, chunk_x, chunk_y, site_kind, site_id):
    site_kind = str(site_kind or "").strip().lower()
    site_id = str(site_id or "").strip()
    if not site_kind or not site_id:
        return ""
    for prop in getattr(sim, "properties", {}).values():
        if not isinstance(prop, dict):
            continue
        metadata = prop.get("metadata")
        if not isinstance(metadata, dict):
            continue
        if str(metadata.get("site_kind", "") or "").strip().lower() != site_kind:
            continue
        if str(metadata.get("site_id", "") or "").strip() != site_id:
            continue
        chunk = metadata.get("chunk")
        if isinstance(chunk, (list, tuple)) and len(chunk) >= 2:
            try:
                if (int(chunk[0]), int(chunk[1])) != (int(chunk_x), int(chunk_y)):
                    continue
            except (TypeError, ValueError):
                continue
        return str(prop.get("id", "") or "").strip()
    return ""


def _property_chunk(sim, prop):
    if not isinstance(prop, dict):
        return (0, 0)
    metadata = prop.get("metadata")
    if isinstance(metadata, dict):
        chunk = metadata.get("chunk")
        if isinstance(chunk, (list, tuple)) and len(chunk) >= 2:
            try:
                return (int(chunk[0]), int(chunk[1]))
            except (TypeError, ValueError):
                pass
    return sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))


def _chunk_direction_label(origin_chunk, target_chunk):
    try:
        ox, oy = int(origin_chunk[0]), int(origin_chunk[1])
        tx, ty = int(target_chunk[0]), int(target_chunk[1])
    except (TypeError, ValueError, IndexError):
        return ""
    dx = tx - ox
    dy = ty - oy
    parts = []
    if dy < 0:
        parts.append(f"{abs(dy)}N")
    elif dy > 0:
        parts.append(f"{dy}S")
    if dx > 0:
        parts.append(f"{dx}E")
    elif dx < 0:
        parts.append(f"{abs(dx)}W")
    return " ".join(parts) or "HERE"


def _transit_service_profile(service):
    return TRANSIT_SERVICE_PROFILES.get(str(service or "").strip().lower())


def _transit_service_title(service):
    profile = _transit_service_profile(service)
    if profile:
        return str(profile.get("title", service)).strip() or str(service or "Transit").replace("_", " ").title()
    return str(service or "Transit").replace("_", " ").title()


def _transit_service_log_prefix(service):
    profile = _transit_service_profile(service)
    if profile:
        return str(profile.get("log_prefix", _transit_service_title(service))).strip() or _transit_service_title(service)
    return _transit_service_title(service)


def _transit_service_mode_label(service):
    profile = _transit_service_profile(service)
    if profile:
        return str(profile.get("travel_mode", "transit")).strip().lower() or "transit"
    return "transit"


def _transit_token_amount_label(amount):
    try:
        amount = max(0, int(amount))
    except (TypeError, ValueError):
        amount = 0
    unit = "city token" if amount == 1 else "city tokens"
    return f"{amount} {unit}"


def _transit_inventory_label(*, city_tokens=0, daypasses=0):
    try:
        city_tokens = max(0, int(city_tokens))
    except (TypeError, ValueError):
        city_tokens = 0
    try:
        daypasses = max(0, int(daypasses))
    except (TypeError, ValueError):
        daypasses = 0
    daypass_unit = "daypass" if daypasses == 1 else "daypasses"
    return f"{_transit_token_amount_label(city_tokens)} and {daypasses} {daypass_unit}"


def _transit_fare_label(service, *, fare_mode="", cost=0, token_cost=0):
    fare_mode = str(fare_mode or "").strip().lower()
    if fare_mode == "transit_daypass":
        return "daypass"
    if fare_mode == "city_pass_token" or bool((_transit_service_profile(service) or {}).get("token_only")):
        return _transit_token_amount_label(token_cost or cost or 1)
    return _credit_amount_label(cost)


def _transit_node_id_from_property(sim, prop):
    metadata = prop.get("metadata") or {} if isinstance(prop, dict) else {}
    site_kind = str(metadata.get("site_kind", "") or "").strip().lower()
    site_id = str(metadata.get("site_id", "") or "").strip()
    if site_kind and site_id:
        chunk = _property_chunk(sim, prop)
        return f"site:{int(chunk[0])}:{int(chunk[1])}:{site_kind}:{site_id}"

    building_id = str(metadata.get("building_id", "") or "").strip()
    if building_id:
        return f"building:{building_id}"

    prop_id = str((prop or {}).get("id", "") or "").strip()
    if prop_id:
        return f"property:{prop_id}"
    return ""


def _transit_stop_name(raw_name, fallback):
    name = str(raw_name or "").strip()
    if name:
        return name
    return str(fallback or "Transit Stop").strip() or "Transit Stop"


def _property_service_ids(prop):
    metadata = prop.get("metadata") if isinstance(prop, dict) else {}
    if not isinstance(metadata, dict):
        return frozenset()
    return frozenset(
        str(service or "").strip().lower()
        for service in tuple(metadata.get("site_services", ()) or ())
        if str(service or "").strip()
    )


def _property_transit_archetype(prop):
    metadata = prop.get("metadata") if isinstance(prop, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    return str(
        metadata.get("site_kind", "") or metadata.get("archetype", "") or prop.get("archetype", "") if isinstance(prop, dict) else ""
    ).strip().lower()


def _property_transit_node_index(sim):
    """Materialize property-backed transit facts once per infrastructure revision."""

    def build():
        indexed = {}
        transit_ids = set(TRANSIT_SERVICE_IDS)
        archetype_services = {}
        for service in TRANSIT_SERVICE_IDS:
            profile = _transit_service_profile(service) or {}
            for archetype in tuple(profile.get("node_archetypes", ()) or ()):
                key = str(archetype or "").strip().lower()
                if key:
                    archetype_services.setdefault(key, set()).add(str(service).strip().lower())

        for prop in tuple(getattr(sim, "properties", {}).values()):
            if not isinstance(prop, dict):
                continue
            services = set(_property_service_ids(prop)).intersection(transit_ids)
            services.update(archetype_services.get(_property_transit_archetype(prop), ()))
            if not services:
                continue
            chunk = _property_chunk(sim, prop)
            indexed.setdefault(chunk, set()).update(services)
        return {
            chunk: frozenset(services)
            for chunk, services in indexed.items()
        }

    return cached_derived_fact(
        sim,
        "transit.property_nodes",
        "all",
        build,
        domains=("transit_nodes",),
        max_entries=1,
    )


def _chunk_has_transit_service_node(sim, chunk, service):
    profile = _transit_service_profile(service)
    if not profile or getattr(sim, "world", None) is None:
        return False
    try:
        chunk = (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError, IndexError):
        return False
    node_archetypes = {
        str(archetype).strip().lower()
        for archetype in tuple(profile.get("node_archetypes", ()) or ())
        if str(archetype).strip()
    }
    if not node_archetypes:
        return False

    if service in _property_transit_node_index(sim).get(chunk, ()):
        return True

    world_chunk = sim.world.get_chunk(chunk[0], chunk[1])
    for block in tuple((world_chunk or {}).get("blocks", ()) or ()):
        if not isinstance(block, dict):
            continue
        for building in tuple(block.get("buildings", ()) or ()):
            if not isinstance(building, dict):
                continue
            if str(building.get("archetype", "") or "").strip().lower() in node_archetypes:
                return True
    for site in tuple((world_chunk or {}).get("sites", ()) or ()):
        if not isinstance(site, dict):
            continue
        if str(site.get("kind", "") or "").strip().lower() in node_archetypes:
            return True
    return False


def _transit_services_connecting_chunks(sim, origin_chunk, target_chunk, *, services=None):
    if getattr(sim, "world", None) is None:
        return ()
    try:
        origin_chunk = (int(origin_chunk[0]), int(origin_chunk[1]))
        target_chunk = (int(target_chunk[0]), int(target_chunk[1]))
    except (TypeError, ValueError, IndexError):
        return ()
    requested = tuple(services or TRANSIT_SERVICE_IDS)
    requested = tuple(str(service or "").strip().lower() for service in requested if str(service or "").strip())

    def build():
        distance = _manhattan(origin_chunk[0], origin_chunk[1], target_chunk[0], target_chunk[1])
        if distance <= 0:
            return ()
        connected = []
        for service in requested:
            profile = _transit_service_profile(service)
            if not profile:
                continue
            radius = max(1, int(profile.get("search_radius", 6) or 6))
            if distance > radius:
                continue
            if not _chunk_has_transit_service_node(sim, origin_chunk, service):
                continue
            if not _chunk_has_transit_service_node(sim, target_chunk, service):
                continue
            connected.append(service)
        return tuple(connected)

    return cached_derived_fact(
        sim,
        "transit.chunk_connections",
        (origin_chunk, target_chunk, requested),
        build,
        domains=("transit_nodes",),
        max_entries=8_192,
    )


def _chunk_data_has_transit_node(chunk, node_archetypes, profile):
    if not isinstance(chunk, dict):
        return False
    if bool((profile or {}).get("scan_buildings", True)):
        for block in tuple(chunk.get("blocks", ()) or ()):
            if not isinstance(block, dict):
                continue
            for building in tuple(block.get("buildings", ()) or ()):
                if not isinstance(building, dict):
                    continue
                if str(building.get("archetype", "") or "").strip().lower() in node_archetypes:
                    return True
    if bool((profile or {}).get("scan_sites", True)):
        for site in tuple(chunk.get("sites", ()) or ()):
            if not isinstance(site, dict):
                continue
            if str(site.get("kind", "") or "").strip().lower() in node_archetypes:
                return True
    return False


def _transit_offset_has_predicted_node(sim, cx, cy, profile, node_archetypes):
    world = getattr(sim, "world", None)
    if world is None:
        return False
    key = (int(cx), int(cy))
    loaded_chunks = getattr(world, "chunks", {})
    if isinstance(loaded_chunks, dict) and key in loaded_chunks:
        return _chunk_data_has_transit_node(loaded_chunks.get(key), node_archetypes, profile)

    if not bool((profile or {}).get("scan_sites", True)):
        return False
    try:
        desc = world.overworld_descriptor(cx, cy)
        area_type = str((desc or {}).get("area_type", "") or "").strip().lower()
    except (TypeError, ValueError, AttributeError):
        return False
    if area_type == "city":
        return False
    try:
        sites = tuple(world.predict_non_city_sites(cx, cy, descriptor=desc) or ())
    except (TypeError, ValueError, AttributeError):
        return False
    for site in sites:
        if not isinstance(site, dict):
            continue
        if str(site.get("kind", "") or "").strip().lower() in node_archetypes:
            return True
    return False


def _transit_scan_offsets(sim, origin_chunk, service, profile, radius, *, node_archetypes=(), target_count=None):
    offsets = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            distance = _manhattan(0, 0, dx, dy)
            if distance <= 0 or distance > radius:
                continue
            offsets.append((int(dx), int(dy), int(distance)))

    offsets.sort(key=lambda row: (row[2], row[1], row[0]))
    try:
        far_probe_count = max(0, int(profile.get("far_probe_count", 0) or 0))
    except (TypeError, ValueError):
        far_probe_count = 0
    if far_probe_count <= 0:
        return tuple(offsets)

    try:
        far_min = max(1, int(profile.get("far_probe_min_distance", max(1, radius // 2)) or max(1, radius // 2)))
    except (TypeError, ValueError):
        far_min = max(1, radius // 2)

    seed = getattr(sim, "seed", 0)
    service = str(service or "").strip().lower()
    try:
        ox, oy = int(origin_chunk[0]), int(origin_chunk[1])
    except (TypeError, ValueError, IndexError):
        ox, oy = 0, 0

    far_offsets = [
        row for row in offsets
        if int(row[2]) >= far_min
        and _transit_offset_has_predicted_node(
            sim,
            int(origin_chunk[0]) + int(row[0]),
            int(origin_chunk[1]) + int(row[1]),
            profile,
            node_archetypes,
        )
    ]
    far_offsets.sort(
        key=lambda row: (
            -int(row[2]),
            random.Random(f"{seed}:transit-far-probe:{service}:{ox}:{oy}:{row[0]}:{row[1]}").random(),
            int(row[1]),
            int(row[0]),
        )
    )
    try:
        target_count = max(1, int(target_count))
    except (TypeError, ValueError):
        target_count = far_probe_count
    selected_count = min(far_probe_count, target_count)
    selected_far = tuple(far_offsets[:selected_count])
    if bool((profile or {}).get("require_preferred_distance")):
        return selected_far
    selected = {(row[0], row[1]) for row in selected_far}
    return tuple(selected_far) + tuple(row for row in offsets if (row[0], row[1]) not in selected)


def _transit_candidate_sort_key(row, profile):
    try:
        distance = int(row.get("distance", 9999) or 9999)
    except (TypeError, ValueError):
        distance = 9999
    name = str(row.get("destination_name", "")).strip().lower()
    chunk = tuple(row.get("chunk", (0, 0)) or (0, 0))
    node_id = str(row.get("node_id", "")).strip().lower()
    if str((profile or {}).get("distance_sort", "near") or "near").strip().lower() == "far":
        try:
            preferred_min = max(1, int((profile or {}).get("preferred_min_distance", 1) or 1))
        except (TypeError, ValueError):
            preferred_min = 1
        preferred_rank = 0 if distance >= preferred_min else 1
        return (preferred_rank, -distance, name, chunk, node_id)
    return (distance, name, chunk, node_id)


def _transit_filter_distance_band(candidates, profile, limit):
    candidates = list(candidates or ())
    if str((profile or {}).get("distance_sort", "near") or "near").strip().lower() != "far":
        return candidates
    try:
        preferred_min = max(1, int((profile or {}).get("preferred_min_distance", 1) or 1))
    except (TypeError, ValueError):
        preferred_min = 1
    try:
        fallback_target = max(1, int((profile or {}).get("near_fallback_target", 1) or 1))
    except (TypeError, ValueError):
        fallback_target = 1
    try:
        limit = max(1, int(limit))
    except (TypeError, ValueError):
        limit = len(candidates) or 1

    far_candidates = [
        row for row in candidates
        if int(row.get("distance", 0) or 0) >= preferred_min
    ]
    if bool((profile or {}).get("require_preferred_distance")):
        return far_candidates
    if len(far_candidates) >= min(limit, fallback_target):
        return far_candidates
    far_keys = {str(row.get("node_id", "")).strip() for row in far_candidates}
    return far_candidates + [
        row for row in candidates
        if str(row.get("node_id", "")).strip() not in far_keys
    ]


def _transit_destinations(sim, origin_prop, service, *, radius=None, limit=None):
    profile = _transit_service_profile(service)
    if not profile or not isinstance(origin_prop, dict) or getattr(sim, "world", None) is None:
        return ()

    node_archetypes = {
        str(archetype).strip().lower()
        for archetype in tuple(profile.get("node_archetypes", ()) or ())
        if str(archetype).strip()
    }
    if not node_archetypes:
        return ()

    radius = max(1, int(profile.get("search_radius", 6) if radius is None else radius))
    limit = max(1, int(profile.get("menu_limit", 8) if limit is None else limit))
    origin_chunk = _property_chunk(sim, origin_prop)
    origin_node_id = _transit_node_id_from_property(sim, origin_prop)
    chunk_size = int(max(8, getattr(sim, "chunk_size", 16) or 16))

    seen = set()
    candidates = []
    for dx, dy, distance in _transit_scan_offsets(
        sim,
        origin_chunk,
        service,
        profile,
        radius,
        node_archetypes=node_archetypes,
        target_count=limit,
    ):
        cx = origin_chunk[0] + dx
        cy = origin_chunk[1] + dy
        chunk = sim.world.get_chunk(cx, cy)
        desc = sim.world.overworld_descriptor(cx, cy)
        district = chunk.get("district", {}) if isinstance(chunk, dict) else {}
        origin_x = int(cx) * chunk_size
        origin_y = int(cy) * chunk_size
        district_type = str((district or {}).get("district_type", "unknown") or "unknown").strip().lower() or "unknown"
        settlement_name = str((desc or {}).get("settlement_name", "") or "").strip()

        if bool(profile.get("scan_buildings", True)):
            blocks = tuple((chunk or {}).get("blocks", ()) or ())
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                buildings = tuple(block.get("buildings", ()) or ())
                building_count = len(buildings)
                for building_index, building in enumerate(buildings):
                    archetype = str((building or {}).get("archetype", "") or "").strip().lower()
                    if archetype not in node_archetypes:
                        continue
                    layout = layout_chunk_building(
                        origin_x=origin_x,
                        origin_y=origin_y,
                        chunk_size=chunk_size,
                        block_grid_x=int(block.get("grid_x", 0) or 0),
                        block_grid_y=int(block.get("grid_y", 0) or 0),
                        building_index=building_index,
                        building=building,
                        building_count=building_count,
                    )
                    if not isinstance(layout, dict):
                        continue
                    building_id = world_building_id(cx, cy, building)
                    node_id = f"building:{building_id}"
                    if origin_node_id and node_id == origin_node_id:
                        continue
                    if node_id in seen:
                        continue
                    seen.add(node_id)
                    entry = dict(layout.get("entry", {}) or {})
                    stop_name = _transit_stop_name(
                        (building or {}).get("business_name", ""),
                        archetype.replace("_", " ").title(),
                    )
                    candidates.append({
                        "node_id": node_id,
                        "building_id": building_id,
                        "property_id": _building_property_id(sim, building_id),
                        "destination_name": stop_name,
                        "station_name": stop_name,
                        "node_archetype": archetype,
                        "chunk": (int(cx), int(cy)),
                        "distance": int(distance),
                        "direction_label": _chunk_direction_label(origin_chunk, (cx, cy)),
                        "district_type": district_type,
                        "settlement_name": settlement_name,
                        "entry_x": int(entry.get("x", layout.get("anchor_x", origin_x))),
                        "entry_y": int(entry.get("y", layout.get("anchor_y", origin_y))),
                        "entry_z": int(entry.get("z", 0)),
                    })

        if bool(profile.get("scan_sites", True)):
            reserved_site_footprints = []
            for site_index, site in enumerate(tuple((chunk or {}).get("sites", ()) or ())):
                if not isinstance(site, dict):
                    continue
                site_kind = str(site.get("kind", "") or "").strip().lower()
                if site_kind not in node_archetypes:
                    continue
                layout = layout_chunk_site(
                    origin_x=origin_x,
                    origin_y=origin_y,
                    chunk_size=chunk_size,
                    site_index=site_index,
                    site=site,
                    reserved_footprints=reserved_site_footprints,
                )
                if not isinstance(layout, dict):
                    continue
                reserved_site_footprints.append(dict(layout.get("footprint", {})))
                site_id = str(site.get("site_id", site_index) or site_index).strip() or str(site_index)
                node_id = f"site:{int(cx)}:{int(cy)}:{site_kind}:{site_id}"
                if origin_node_id and node_id == origin_node_id:
                    continue
                if node_id in seen:
                    continue
                seen.add(node_id)
                entry = dict(layout.get("entry", {}) or {})
                stop_name = _transit_stop_name(
                    site.get("name", ""),
                    site_kind.replace("_", " ").title(),
                )
                candidates.append({
                    "node_id": node_id,
                    "building_id": "",
                    "property_id": _site_property_id(sim, cx, cy, site_kind, site_id),
                    "destination_name": stop_name,
                    "station_name": stop_name,
                    "node_archetype": site_kind,
                    "chunk": (int(cx), int(cy)),
                    "distance": int(distance),
                    "direction_label": _chunk_direction_label(origin_chunk, (cx, cy)),
                    "district_type": district_type,
                    "settlement_name": settlement_name,
                    "entry_x": int(entry.get("x", layout.get("anchor_x", origin_x))),
                    "entry_y": int(entry.get("y", layout.get("anchor_y", origin_y))),
                    "entry_z": int(entry.get("z", 0)),
                })

    candidates.sort(key=lambda row: _transit_candidate_sort_key(row, profile))
    candidates = _transit_filter_distance_band(candidates, profile, limit)
    return tuple(candidates[:limit])


def _transit_token_cost(service, distance):
    profile = _transit_service_profile(service) or {}
    try:
        distance = max(1, int(distance))
    except (TypeError, ValueError):
        distance = 1
    step = max(1, int(profile.get("token_distance_step", 99) or 99))
    base = max(1, int(profile.get("token_base_cost", 1) or 1))
    token_cost = int(base + ((distance - 1) // step))
    max_token_cost = profile.get("max_token_cost")
    if max_token_cost is not None:
        try:
            token_cost = min(token_cost, max(1, int(max_token_cost)))
        except (TypeError, ValueError):
            pass
    return max(1, token_cost)


def _transit_quote(service, distance, *, price_mult=1.0):
    profile = _transit_service_profile(service)
    if not profile:
        return {
            "base_cost": 0,
            "cost": 0,
            "distance": max(1, _int_or_default(distance, 1)),
            "city_pass_valid": False,
            "token_cost": 0,
            "token_only": False,
        }

    try:
        distance = max(1, int(distance))
    except (TypeError, ValueError):
        distance = 1
    try:
        price_mult = float(price_mult)
    except (TypeError, ValueError):
        price_mult = 1.0

    token_only = bool(profile.get("token_only"))
    token_cost = _transit_token_cost(service, distance) if token_only else 0
    city_pass_valid = bool(token_only)
    if not token_only:
        base_cost = int(profile.get("base_cost", 0) or 0) + (distance * int(profile.get("cost_per_chunk", 0) or 0))
        cost = max(4, int(round(float(base_cost) * max(0.45, price_mult))))
        city_pass_valid = bool(distance <= int(profile.get("city_token_max_distance", 0) or 0))
        if city_pass_valid:
            token_cost = _transit_token_cost(service, distance)
    else:
        base_cost = token_cost
        cost = token_cost

    return {
        "base_cost": int(base_cost),
        "cost": int(cost),
        "distance": int(distance),
        "city_pass_valid": bool(city_pass_valid),
        "token_cost": int(token_cost),
        "token_only": bool(token_only),
    }


def _transit_payment_profile(service, distance, *, price_mult=1.0, city_tokens=0, daypasses=0):
    profile = _transit_service_profile(service) or {}
    quote = _transit_quote(service, distance, price_mult=price_mult)
    allow_daypass = bool(profile.get("allow_daypass", True))
    prefer_tokens = bool(profile.get("prefer_tokens", False))
    token_cost = int(quote.get("token_cost", 0) or 0)
    available_tokens = max(0, _int_or_default(city_tokens, 0))
    available_daypasses = max(0, _int_or_default(daypasses, 0))

    if prefer_tokens:
        if token_cost > 0 and available_tokens >= token_cost:
            fare_mode = "city_pass_token"
        elif allow_daypass and available_daypasses > 0:
            fare_mode = "transit_daypass"
        elif bool(quote.get("token_only")):
            fare_mode = "city_pass_token"
        else:
            fare_mode = "credits"
    else:
        if allow_daypass and available_daypasses > 0:
            fare_mode = "transit_daypass"
        elif token_cost > 0 and available_tokens >= token_cost:
            fare_mode = "city_pass_token"
        elif bool(quote.get("token_only")):
            fare_mode = "city_pass_token"
        else:
            fare_mode = "credits"

    return {
        **quote,
        "fare_mode": fare_mode,
    }


def _transit_travel_ticks(sim, service, distance):
    profile = _transit_service_profile(service) or {}
    try:
        distance = max(1, int(distance))
    except (TypeError, ValueError):
        distance = 1
    world_traits = getattr(sim, "world_traits", {})
    clock = world_traits.get("clock", {}) if isinstance(world_traits, dict) else {}
    try:
        ticks_per_hour = int(clock.get("ticks_per_hour", 600))
    except (TypeError, ValueError, AttributeError):
        ticks_per_hour = 600
    ticks_per_hour = max(60, ticks_per_hour)
    hours = float(profile.get("travel_base_hours", 0.25) or 0.25) + (
        float(profile.get("travel_hours_per_chunk", 0.2) or 0.2) * float(distance)
    )
    return max(60, int(round(float(ticks_per_hour) * hours)))


def _rail_transit_destinations(sim, origin_prop, *, radius=None, limit=None):
    return _transit_destinations(sim, origin_prop, "rail_transit", radius=radius, limit=limit)


def _bus_transit_destinations(sim, origin_prop, *, radius=None, limit=None):
    return _transit_destinations(sim, origin_prop, "bus_transit", radius=radius, limit=limit)


def _shuttle_transit_destinations(sim, origin_prop, *, radius=None, limit=None):
    return _transit_destinations(sim, origin_prop, "shuttle_transit", radius=radius, limit=limit)


def _ferry_transit_destinations(sim, origin_prop, *, radius=None, limit=None):
    return _transit_destinations(sim, origin_prop, "ferry_transit", radius=radius, limit=limit)


def _coach_transit_destinations(sim, origin_prop, *, radius=None, limit=None):
    return _transit_destinations(sim, origin_prop, "coach_transit", radius=radius, limit=limit)


def _rail_transit_quote(distance, *, price_mult=1.0):
    return _transit_quote("rail_transit", distance, price_mult=price_mult)


def _bus_transit_quote(distance, *, price_mult=1.0):
    return _transit_quote("bus_transit", distance, price_mult=price_mult)


def _shuttle_transit_quote(distance, *, price_mult=1.0):
    return _transit_quote("shuttle_transit", distance, price_mult=price_mult)


def _ferry_transit_quote(distance, *, price_mult=1.0):
    return _transit_quote("ferry_transit", distance, price_mult=price_mult)


def _coach_transit_quote(distance, *, price_mult=1.0):
    return _transit_quote("coach_transit", distance, price_mult=price_mult)


def _rail_transit_payment_profile(distance, *, price_mult=1.0, city_tokens=0, daypasses=0):
    return _transit_payment_profile(
        "rail_transit",
        distance,
        price_mult=price_mult,
        city_tokens=city_tokens,
        daypasses=daypasses,
    )


def _bus_transit_payment_profile(distance, *, price_mult=1.0, city_tokens=0, daypasses=0):
    return _transit_payment_profile(
        "bus_transit",
        distance,
        price_mult=price_mult,
        city_tokens=city_tokens,
        daypasses=daypasses,
    )


def _shuttle_transit_payment_profile(distance, *, price_mult=1.0, city_tokens=0, daypasses=0):
    return _transit_payment_profile(
        "shuttle_transit",
        distance,
        price_mult=price_mult,
        city_tokens=city_tokens,
        daypasses=daypasses,
    )


def _ferry_transit_payment_profile(distance, *, price_mult=1.0, city_tokens=0, daypasses=0):
    return _transit_payment_profile(
        "ferry_transit",
        distance,
        price_mult=price_mult,
        city_tokens=city_tokens,
        daypasses=daypasses,
    )


def _coach_transit_payment_profile(distance, *, price_mult=1.0, city_tokens=0, daypasses=0):
    return _transit_payment_profile(
        "coach_transit",
        distance,
        price_mult=price_mult,
        city_tokens=city_tokens,
        daypasses=daypasses,
    )


def _rail_transit_travel_ticks(sim, distance):
    return _transit_travel_ticks(sim, "rail_transit", distance)


def _bus_transit_travel_ticks(sim, distance):
    return _transit_travel_ticks(sim, "bus_transit", distance)


def _shuttle_transit_travel_ticks(sim, distance):
    return _transit_travel_ticks(sim, "shuttle_transit", distance)


def _ferry_transit_travel_ticks(sim, distance):
    return _transit_travel_ticks(sim, "ferry_transit", distance)


def _coach_transit_travel_ticks(sim, distance):
    return _transit_travel_ticks(sim, "coach_transit", distance)


OVERWORLD_DISTRICT_GLYPHS = {
    "industrial": "I",
    "residential": "R",
    "downtown": "D",
    "slums": "S",
    "corporate": "C",
    "military": "M",
    "entertainment": "E",
}
OVERWORLD_AREA_GLYPHS = {
    "city": "X",
    "frontier": "F",
    "wilderness": "W",
    "coastal": "O",
}
OVERWORLD_DISTRICT_COLORS = {
    "industrial": "floor_industrial",
    "residential": "floor_residential",
    "downtown": "floor_downtown",
    "slums": "floor_slums",
    "corporate": "floor_corporate",
    "military": "floor_military",
    "entertainment": "floor_entertainment",
}
OVERWORLD_AREA_COLORS = {
    "city": "floor_downtown",
    "frontier": "floor_frontier",
    "wilderness": "floor_wilderness",
    "coastal": "floor_coastal",
}
OVERWORLD_TERRAIN_GLYPHS = {
    "urban": "u",
    "park": "p",
    "industrial_waste": "x",
    "scrub": "s",
    "plains": "p",
    "badlands": "b",
    "hills": "h",
    "forest": "f",
    "marsh": "m",
    "shore": "o",
    "shoals": "a",
    "dunes": "d",
    "cliffs": "c",
    "salt_flats": "t",
    "lake": "l",
    "ruins": "r",
}
OVERWORLD_TERRAIN_COLORS = {
    "urban": "floor_downtown",
    "park": "terrain_brush",
    "industrial_waste": "building_fill",
    "scrub": "floor_frontier",
    "plains": "floor_frontier",
    "badlands": "terrain_trail",
    "hills": "terrain_rock",
    "forest": "terrain_brush",
    "marsh": "floor_wilderness",
    "shore": "floor_coastal",
    "shoals": "terrain_water",
    "dunes": "terrain_salt",
    "cliffs": "terrain_rock",
    "salt_flats": "terrain_salt",
    "lake": "terrain_water",
    "ruins": "building_edge",
}
OVERWORLD_PATH_GLYPHS = {
    "freeway": "#",
    "road": "=",
    "trail": ":",
}
OVERWORLD_PATH_COLORS = {
    "freeway": "transit",
    "road": "terrain_road",
    "trail": "terrain_trail",
}


def _overworld_render_style(sim, cx, cy):
    desc = sim.world.overworld_descriptor(cx, cy)
    area_type = str(desc.get("area_type", "city")).strip().lower() or "city"
    district_type = str(desc.get("district_type", "unknown")).strip().lower() or "unknown"
    terrain_key = str(desc.get("terrain", "plain")).strip().lower() or "plain"
    landmark_here = desc.get("landmark")
    interest = sim.world.overworld_interest(cx, cy, descriptor=desc)
    loaded_chunks = getattr(sim.world, "loaded_chunks", {}) or {}

    if isinstance(landmark_here, dict) and landmark_here.get("glyph"):
        glyph = str(landmark_here.get("glyph", "*"))[:1] or "*"
        color = landmark_here.get("color", "human")
    elif interest.get("show_on_map") and interest.get("glyph"):
        glyph = str(interest.get("glyph", "?"))[:1] or "?"
        color = str(interest.get("color", "human") or "human")
    elif area_type == "city":
        glyph = OVERWORLD_DISTRICT_GLYPHS.get(
            district_type,
            OVERWORLD_AREA_GLYPHS.get("city", "X"),
        )
        color = OVERWORLD_DISTRICT_COLORS.get(
            district_type,
            OVERWORLD_AREA_COLORS.get("city", "human"),
        )
    else:
        glyph = OVERWORLD_TERRAIN_GLYPHS.get(
            terrain_key,
            OVERWORLD_AREA_GLYPHS.get(area_type, "?"),
        )
        color = OVERWORLD_TERRAIN_COLORS.get(
            terrain_key,
            OVERWORLD_AREA_COLORS.get(area_type, "human"),
        )

    if str(glyph).isalpha():
        glyph = str(glyph).upper() if (cx, cy) in loaded_chunks else str(glyph).lower()
    return glyph, color


def _overworld_legend_line(sim, cx, cy, text):
    glyph, color = _overworld_render_style(sim, cx, cy)
    return _legend_line(text, glyph=glyph, color=color, attrs=A_BOLD)


def _overworld_travel_profile(sim, cx, cy, desc=None, interest=None):
    return sim.world.overworld_travel_profile(cx, cy, descriptor=desc, interest=interest)


def _overworld_discovery_profile(sim, cx, cy, desc=None, interest=None, travel=None):
    return sim.world.overworld_discovery_profile(
        cx,
        cy,
        descriptor=desc,
        interest=interest,
        travel=travel,
    )


def _chunk_site_kinds(chunk, *extra_kinds):
    kinds = []
    seen = set()

    def _push(value):
        label = str(value or "").strip().lower()
        if not label or label in seen:
            return
        seen.add(label)
        kinds.append(label)

    if isinstance(chunk, dict):
        for site in tuple(chunk.get("sites", ()) or ()):
            if not isinstance(site, dict):
                continue
            _push(site.get("kind"))

    for values in extra_kinds:
        if isinstance(values, (list, tuple, set)):
            for value in values:
                _push(value)
        else:
            _push(values)
    return tuple(kinds)


def _overworld_identity_profile(sim, cx, cy, desc=None, interest=None, travel=None, discovery=None, site_kinds=None):
    return sim.world.overworld_identity_profile(
        cx,
        cy,
        descriptor=desc,
        interest=interest,
        travel=travel,
        discovery=discovery,
        site_kinds=site_kinds,
    )


def _overworld_travel_tax_text(profile):
    bits = []
    try:
        energy_cost = int(profile.get("energy_cost", 0))
    except (AttributeError, TypeError, ValueError):
        energy_cost = 0
    try:
        safety_cost = int(profile.get("safety_cost", 0))
    except (AttributeError, TypeError, ValueError):
        safety_cost = 0
    try:
        social_cost = int(profile.get("social_cost", 0))
    except (AttributeError, TypeError, ValueError):
        social_cost = 0

    if energy_cost > 0:
        bits.append(f"E{energy_cost}")
    if safety_cost > 0:
        bits.append(f"S{safety_cost}")
    if social_cost > 0:
        bits.append(f"So{social_cost}")
    return "/".join(bits) if bits else "light"


def _overworld_travel_summary_bits(profile):
    if not isinstance(profile, dict):
        return ()
    risk = str(profile.get("risk_label", "")).strip() or "low"
    support = str(profile.get("support_label", "")).strip() or "none"
    return (
        f"risk:{risk}",
        f"support:{support}",
        f"tax:{_overworld_travel_tax_text(profile)}",
    )


def _overworld_discovery_summary_bits(profile):
    if not isinstance(profile, dict):
        return ()
    label = str(profile.get("label", "")).strip()
    if not label:
        return ()
    return (f"opp:{label}",)
def _storefront_service_role_priority(role):
    role = str(role or "").strip().lower()
    return {
        "owner": 0,
        "manager": 1,
        "staff": 2,
    }.get(role, 3)


def _occupation_service_role(occupation):
    if not occupation:
        return "staff"

    workplace = getattr(occupation, "workplace", None)
    if isinstance(workplace, dict):
        configured = str(
            workplace.get("authority_role", workplace.get("access_role", ""))
            or ""
        ).strip().lower()
        if configured in {"owner", "manager", "staff"}:
            return configured

    career = str(getattr(occupation, "career", "") or "").strip().lower()
    if any(keyword in career for keyword in ("manager", "director", "lead", "supervisor", "chief", "controller")):
        return "manager"
    return "staff"


def _actor_in_storefront_service_zone(sim, actor_eid, prop):
    positions = sim.ecs.get(Position)
    actor_pos = positions.get(actor_eid)
    if not actor_pos:
        return False, 999999

    focus = _property_focus_position(prop)
    if not focus:
        return False, 999999

    if int(actor_pos.z) != int(focus[2]):
        return False, 999999

    dist = abs(int(actor_pos.x) - int(focus[0])) + abs(int(actor_pos.y) - int(focus[1]))
    if dist <= 2:
        return True, dist

    covered = _property_covering(sim, actor_pos.x, actor_pos.y, actor_pos.z)
    if covered and covered.get("id") == prop.get("id"):
        return True, dist
    return False, dist


def _actor_inside_property(sim, actor_eid, prop):
    positions = sim.ecs.get(Position)
    actor_pos = positions.get(actor_eid)
    if not actor_pos or not isinstance(prop, dict):
        return False
    covered = _property_covering(sim, actor_pos.x, actor_pos.y, actor_pos.z)
    return isinstance(covered, dict) and str(covered.get("id", "")).strip() == str(prop.get("id", "")).strip()


def _storefront_service_profile(sim, prop, actor_eid=None):
    profile = {
        "mode": "",
        "available": False,
        "blocked_reason": "",
        "service_eid": None,
        "service_name": "",
        "service_role": "",
        "service_note": "",
        "summary_label": "",
        "fallback_self_serve": False,
    }
    if not isinstance(prop, dict) or not _property_is_storefront(prop):
        return profile

    mode = _storefront_service_mode(prop)
    if mode == "automated":
        profile.update({
            "mode": "automated",
            "available": True,
            "service_note": "self-serve",
            "summary_label": "self-serve",
        })
        return profile

    ais = sim.ecs.get(AI)
    occupations = sim.ecs.get(Occupation)
    owner_eid = prop.get("owner_eid")
    candidates_by_eid = {}

    if owner_eid is not None:
        candidates_by_eid[owner_eid] = {
            "eid": owner_eid,
            "role": "owner",
            "occupation": occupations.get(owner_eid),
        }

    for member in property_org_members(sim, prop):
        member_eid = member.get("eid")
        occupation = member.get("occupation")
        existing = candidates_by_eid.get(member_eid)
        role = "owner" if member_eid == owner_eid else str(member.get("role", "") or "").strip().lower()
        if role not in {"owner", "manager", "staff"}:
            role = _occupation_service_role(occupation)
        if existing and existing.get("role") == "owner":
            continue
        candidates_by_eid[member_eid] = {
            "eid": member_eid,
            "role": role,
            "occupation": occupation,
            "source": member.get("source", "workplace"),
        }

    for worker_eid, occupation in occupations.items():
        if worker_eid in candidates_by_eid or not occupation_targets_property(prop, occupation):
            continue
        candidates_by_eid[worker_eid] = {
            "eid": worker_eid,
            "role": _occupation_service_role(occupation),
            "occupation": occupation,
            "source": "workplace",
        }

    available = []
    for info in candidates_by_eid.values():
        service_actor_eid = info["eid"]
        present, distance = _actor_in_storefront_service_zone(sim, service_actor_eid, prop)
        occupation = info.get("occupation")
        ai = ais.get(service_actor_eid)
        on_shift = False
        if occupation and (
            occupation_targets_property(prop, occupation)
            or str(info.get("source", "")).strip().lower() == "affiliation"
        ):
            on_shift = bool(
                work_shift_active(
                    sim,
                    occupation=occupation,
                    workplace_prop=prop,
                    role=getattr(ai, "role", None),
                )
            )
        if not present:
            continue
        if info["role"] != "owner" and occupation and not on_shift:
            continue
        available.append((info["role"], distance, service_actor_eid))

    if available:
        available.sort(key=lambda row: (_storefront_service_role_priority(row[0]), row[1], row[2]))
        service_role, _distance, service_eid = available[0]
        if actor_eid is not None and int(service_eid) == int(actor_eid):
            service_name = "you"
        else:
            service_name = _entity_display_name(sim, service_eid, title_case=True)
        profile.update({
            "mode": "staffed",
            "available": True,
            "service_eid": service_eid,
            "service_name": service_name,
            "service_role": service_role,
            "service_note": (
                "owner-run counter"
                if actor_eid is not None and int(service_eid) == int(actor_eid)
                else f"served by {service_name}" if service_name else "counter service"
            ),
            "summary_label": (
                "owner-run"
                if actor_eid is not None and int(service_eid) == int(actor_eid)
                else f"counter:{service_name}" if service_name else "counter"
            ),
        })
        return profile

    if (
        actor_eid is not None
        and owner_eid is not None
        and int(actor_eid) == int(owner_eid)
        and _actor_inside_property(sim, actor_eid, prop)
    ):
        profile.update({
            "mode": "staffed",
            "available": True,
            "service_eid": actor_eid,
            "service_name": "you",
            "service_role": "owner",
            "service_note": "owner-run counter",
            "summary_label": "owner-run",
        })
        return profile

    if candidates_by_eid:
        profile.update({
            "mode": "staffed",
            "available": False,
            "blocked_reason": "no_staff",
            "service_note": "counter service",
            "summary_label": "counter",
        })
        return profile

    profile.update({
        "mode": "automated",
        "available": True,
        "service_note": "unattended self-serve",
        "summary_label": "self-serve",
        "fallback_self_serve": True,
    })
    return profile


CASINO_CARD_RANKS = "23456789TJQKA"
CASINO_CARD_SUITS = ("S", "H", "D", "C")
CASINO_CARD_VALUE_BY_RANK = {
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "T": 10,
    "J": 11,
    "Q": 12,
    "K": 13,
    "A": 14,
}
CASINO_RANK_NAME_BY_VALUE = {
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "jack",
    12: "queen",
    13: "king",
    14: "ace",
}
CASINO_PLINKO_LANE_COUNT = 7
CASINO_PLINKO_ROWS = 8
CASINO_PLINKO_BUCKET_MULTIPLIERS = (0.0, 0.4, 0.8, 1.2, 3.0, 1.2, 0.8, 0.4, 0.0)
CASINO_POKER_CATEGORY_NAMES = {
    8: "straight flush",
    7: "four of a kind",
    6: "full house",
    5: "flush",
    4: "straight",
    3: "three of a kind",
    2: "two pair",
    1: "pair",
    0: "high card",
}
CASINO_HOLDEM_ANTE_BONUS_MULTIPLIERS = {
    "royal_flush": 100,
    8: 20,
    7: 10,
    6: 3,
    5: 2,
    4: 1,
}
CASINO_VIDEO_POKER_PAYOUT_MULTIPLIERS = {
    "royal_flush": 250,
    8: 50,
    7: 25,
    6: 9,
    5: 6,
    4: 4,
    3: 3,
    2: 2,
    "jacks_or_better": 1,
}
CASINO_THREE_CARD_POKER_ANTE_BONUS_MULTIPLIERS = {
    5: 5,
    4: 4,
    3: 1,
}
CASINO_KENO_NUMBER_COUNT = 40
CASINO_KENO_DRAW_COUNT = 20
CASINO_KENO_MAX_PICKS = 8
CASINO_KENO_PAYOUT_MULTIPLIERS = {
    1: {1: 1.8},
    2: {2: 3.6},
    3: {2: 1.0, 3: 4.0},
    4: {3: 2.0, 4: 8.0},
    5: {3: 0.5, 4: 3.0, 5: 12.0},
    6: {4: 1.0, 5: 5.0, 6: 30.0},
    7: {5: 2.0, 6: 8.0, 7: 50.0},
    8: {5: 0.5, 6: 3.0, 7: 18.0, 8: 120.0},
}
CASINO_CRAPS_MAX_POINT_ROLLS = 32
CASINO_ROULETTE_NUMBER_MAX = 36
CASINO_ROULETTE_RED_NUMBERS = frozenset({
    1, 3, 5, 7, 9,
    12, 14, 16, 18,
    19, 21, 23, 25, 27,
    30, 32, 34, 36,
})
CASINO_GAME_PROFILES = {
    "slots": {
        "title": "Cheeky Star Aster",
        "service_label": "slots",
        "menu_label": "Play Cheeky Star Aster",
        "bet_options": (10, 25, 50),
        "prompt": "Pick a stake for five reels and forty lines through the city.",
        "note": "Objects and flowers pay the low lines; Bakerrrr people pay the majors. Three wire signals open one of three deep features.",
        "social_gain": (1, 3),
    },
    "video_poker": {
        "title": "Video Poker",
        "service_label": "video poker",
        "menu_label": "Play video poker",
        "bet_options": (10, 25, 50),
        "prompt": "Post a wager, choose which cards to hold, then take one draw.",
        "note": "Classic jacks-or-better rules: hold what you like, draw once, and let the pay table decide.",
        "social_gain": (1, 4),
    },
    "keno": {
        "title": "Keno",
        "service_label": "keno",
        "menu_label": "Play keno",
        "bet_options": (5, 15, 30),
        "prompt": "Pick your spots, let the blower draw, and sweat the ticket.",
        "note": "Quick-draw house keno uses a 40-number board, a 20-ball reveal, and tickets up to 8 spots.",
        "social_gain": (1, 3),
    },
    "roulette": {
        "title": "Roulette",
        "service_label": "roulette",
        "menu_label": "Play roulette",
        "bet_options": (10, 25, 50),
        "prompt": "Pick a chip size, stage any mix of bets you like, and spin the wheel when the slip feels right.",
        "note": "Single-zero wheel with straight-up numbers, colors, parity, ranges, dozens, and columns on one shared slip.",
        "social_gain": (1, 4),
    },
    "craps": {
        "title": "Craps",
        "service_label": "craps",
        "menu_label": "Play craps",
        "bet_options": (10, 25, 50),
        "prompt": "Pick a base chip, stage the bets you want, and roll the shooter one throw at a time.",
        "note": "Pass line, dark side, odds, place, hardways, field, and props can share the felt while the point stays live.",
        "social_gain": (2, 5),
    },
    "baccarat": {
        "title": "Baccarat",
        "service_label": "baccarat",
        "menu_label": "Play baccarat",
        "bet_options": (20, 40, 100),
        "prompt": "Post a wager, back player, banker, or tie, and let the shoe run one hand.",
        "note": "Punto Banco rules with naturals and third-card draws handled automatically.",
        "social_gain": (1, 4),
    },
    "three_card_poker": {
        "title": "Three-Card Poker",
        "service_label": "three-card poker",
        "menu_label": "Play three-card poker",
        "bet_options": (15, 30, 75),
        "prompt": "Post an ante, read your three cards, then play or fold against the dealer.",
        "note": "Dealer qualifies with queen-high or better, and straights or better earn an ante bonus.",
        "social_gain": (2, 4),
    },
    "casino_holdem": {
        "title": "Casino Hold'em",
        "service_label": "casino hold'em",
        "menu_label": "Play casino hold'em",
        "bet_options": (25, 50, 100),
        "prompt": "Post an ante, read the flop, then decide whether to call or fold.",
        "note": "You get two hole cards, the flop comes out first, and calling adds a matching stake.",
        "social_gain": (2, 5),
    },
    "plinko": {
        "title": "Plinko",
        "service_label": "plinko",
        "menu_label": "Play plinko",
        "bet_options": (5, 15, 30),
        "prompt": "Choose a chip size and a drop lane.",
        "note": "The center buckets pay best if the pegs break your way.",
        "social_gain": (1, 3),
    },
    "crash": {
        "title": "Crash",
        "service_label": "crash",
        "menu_label": "Play crash",
        "bet_options": (5, 15, 30),
        "prompt": "Post a stake, ride the rising multiplier, and cash out before the graph breaks.",
        "note": "Each tick gets hotter. Cash out early for a smaller win, or ride too long and lose the stake.",
        "social_gain": (1, 4),
    },
    "twenty_one": {
        "title": "21",
        "service_label": "21",
        "menu_label": "Play 21",
        "bet_options": (10, 25, 50),
        "prompt": "Pick a wager and play a real hand against the dealer.",
        "note": "Hit, stand, and hope the house runs cold.",
        "social_gain": (2, 4),
    },
    "three_bright": {
        "title": "Three Bright",
        "service_label": "three bright",
        "menu_label": "Play Three Bright",
        "bet_options": (25, 100, 250),
        "prompt": "Choose a chip for the color dice.",
        "note": "Three colored dice pay singles by matching face, doubles on two or more, and triples when all three land together.",
        "social_gain": (2, 5),
    },
    "three_bones": {
        "title": "Three Bones",
        "service_label": "three bones",
        "menu_label": "Play Three Bones",
        "bet_options": (5, 15, 30),
        "prompt": "Choose a chip for the covered dice.",
        "note": "Three dice under a cup take small, big, exact total, double, triple, and any-triple action on one shared slip.",
        "social_gain": (2, 4),
    },
    "bloom_cards": {
        "title": "Bloom Cards",
        "service_label": "bloom cards",
        "menu_label": "Play Bloom Cards",
        "bet_options": (10, 25, 50),
        "prompt": "Choose a stake for a small flower-card garden.",
        "note": "Cash out for a safe return, or let the garden grow and risk withering before the better blooms pay.",
        "social_gain": (2, 5),
    },
}
CASINO_GAME_SERVICE_IDS = frozenset(CASINO_GAME_PROFILES)
CASINO_GAME_CAPABILITY_DEFAULTS = {
    "supports_table_context": False,
    "supports_custom_stakes": False,
    "supports_visual_accents": False,
    "supports_sponsor_read": False,
    "supports_backroom_access": True,
    "supports_multiplayer_seats": False,
    "supports_offscreen_resolution": False,
    "supports_social_heat": True,
    "supports_debt": False,
    "supports_house_play": True,
    "supports_player_vs_player": False,
    "available_for_public": True,
    "available_for_gang_favorite": True,
    "risk_band": "medium",
    "pace": "steady",
    "social_texture": "table",
    "style_tags": (),
}
CASINO_GAME_CAPABILITY_OVERRIDES = {
    "slots": {
        "supports_backroom_access": False,
        "risk_band": "medium",
        "pace": "fast",
        "social_texture": "machine",
        "style_tags": ("machine", "luck", "neon", "solitary"),
    },
    "video_poker": {
        "supports_backroom_access": False,
        "risk_band": "medium",
        "pace": "steady",
        "social_texture": "machine",
        "style_tags": ("cards", "machine", "quiet", "precision"),
    },
    "keno": {
        "supports_backroom_access": False,
        "risk_band": "low",
        "pace": "slow",
        "social_texture": "ticket",
        "style_tags": ("numbers", "ticket", "wait", "corner"),
    },
    "roulette": {
        "supports_table_context": False,
        "supports_custom_stakes": False,
        "supports_visual_accents": False,
        "risk_band": "high",
        "pace": "steady",
        "social_texture": "wheel",
        "style_tags": ("wheel", "color", "crowd", "ceremony"),
    },
    "craps": {
        "supports_table_context": False,
        "supports_custom_stakes": False,
        "supports_visual_accents": False,
        "risk_band": "high",
        "pace": "fast",
        "social_texture": "crowd",
        "style_tags": ("dice", "noise", "crowd", "street"),
    },
    "baccarat": {
        "supports_table_context": False,
        "supports_custom_stakes": False,
        "supports_visual_accents": False,
        "risk_band": "medium",
        "pace": "quiet",
        "social_texture": "formal",
        "style_tags": ("cards", "quiet", "formal", "high_limit"),
    },
    "three_card_poker": {
        "supports_table_context": False,
        "supports_custom_stakes": False,
        "supports_visual_accents": False,
        "risk_band": "medium",
        "pace": "steady",
        "social_texture": "cards",
        "style_tags": ("cards", "quick", "showdown"),
    },
    "casino_holdem": {
        "supports_table_context": False,
        "supports_custom_stakes": False,
        "supports_visual_accents": False,
        "supports_multiplayer_seats": True,
        "supports_player_vs_player": False,
        "supports_debt": True,
        "risk_band": "high",
        "pace": "tense",
        "social_texture": "poker",
        "style_tags": ("cards", "holdem", "showdown", "status"),
    },
    "plinko": {
        "supports_backroom_access": False,
        "risk_band": "medium",
        "pace": "fast",
        "social_texture": "machine",
        "style_tags": ("machine", "pegs", "spectacle"),
    },
    "crash": {
        "supports_backroom_access": True,
        "risk_band": "high",
        "pace": "fast",
        "social_texture": "screen",
        "style_tags": ("graph", "risk", "pressure", "quick"),
    },
    "twenty_one": {
        "supports_multiplayer_seats": True,
        "supports_debt": True,
        "risk_band": "medium",
        "pace": "steady",
        "social_texture": "cards",
        "style_tags": ("cards", "dealer", "counting", "steady"),
    },
    "three_bright": {
        "supports_table_context": True,
        "supports_custom_stakes": True,
        "supports_visual_accents": True,
        "supports_sponsor_read": True,
        "supports_debt": True,
        "available_for_public": False,
        "available_for_gang_favorite": True,
        "risk_band": "high",
        "pace": "fast",
        "social_texture": "house_dice",
        "style_tags": ("color", "dice", "gang", "backroom", "street"),
    },
    "three_bones": {
        "supports_table_context": True,
        "supports_custom_stakes": True,
        "supports_visual_accents": True,
        "supports_sponsor_read": True,
        "supports_debt": True,
        "risk_band": "high",
        "pace": "fast",
        "social_texture": "dice",
        "style_tags": ("dice", "cup", "street", "noise"),
    },
    "bloom_cards": {
        "supports_table_context": True,
        "supports_custom_stakes": True,
        "supports_visual_accents": True,
        "supports_sponsor_read": True,
        "risk_band": "medium",
        "pace": "press_your_luck",
        "social_texture": "cards",
        "style_tags": ("cards", "flora", "quiet", "ritual", "color"),
    },
}
for _casino_context_game_id in tuple(CASINO_GAME_PROFILES):
    CASINO_GAME_CAPABILITY_OVERRIDES.setdefault(_casino_context_game_id, {}).update({
        "supports_table_context": True,
        "supports_custom_stakes": True,
        "supports_visual_accents": True,
        "supports_sponsor_read": True,
    })
CASINO_TABLE_STAKE_PROFILES = {
    "street": (1, 5, 10),
    "standard": (10, 25, 50),
    "gang_street": (5, 15, 30),
    "gang_house": (25, 100, 250),
    "gang_high": (100, 500, 1000),
}
CASINO_THREE_BRIGHT_DEFAULT_COLORS = ("red", "green", "blue", "gold", "black", "white")
CASINO_THREE_BRIGHT_BRIGHT_COLORS = frozenset({"red", "green", "blue", "gold", "pink", "violet", "white", "coral"})
CASINO_THREE_BRIGHT_DARK_COLORS = frozenset({"black", "charcoal", "navy", "purple", "olive", "brown"})
CASINO_THREE_BONES_EXACT_TOTAL_GROSS_MULTIPLIERS = {
    4: 61,
    5: 31,
    6: 19,
    7: 13,
    8: 9,
    9: 8,
    10: 7,
    11: 7,
    12: 8,
    13: 9,
    14: 13,
    15: 19,
    16: 31,
    17: 61,
}
CASINO_BLOOM_CARD_MAX_GROW_STEPS = 3
CASINO_BLOOM_CARD_STARTING_HAND_SIZE = 3
CASINO_BLOOM_CARD_GROWTH_BASE_MULTIPLIERS = (1.00, 1.18, 1.58)
CASINO_BLOOM_CARD_GROWTH_MAX_MULTIPLIERS = (1.25, 1.55, 2.10)
CASINO_BLOOM_CARD_COMBO_POINT_VALUE = 0.05


def _casino_color_word(value):
    return casino_color_word(value)


def _casino_color_words_from_hint(raw):
    values = []
    if isinstance(raw, str):
        raw = raw.replace(";", ",").split(",")
    if isinstance(raw, dict):
        raw = raw.values()
    if not isinstance(raw, (list, tuple, set)):
        return ()
    for value in raw:
        color = _casino_color_word(value)
        if color and color not in values:
            values.append(color)
    return tuple(values)


def _casino_stake_profile_ladder(profile_name, fallback=()):
    profile_name = str(profile_name or "standard").strip().lower()
    ladder = CASINO_TABLE_STAKE_PROFILES.get(profile_name)
    if not ladder:
        ladder = CASINO_TABLE_STAKE_PROFILES["standard"]
    fallback_values = tuple(int(value) for value in tuple(fallback or ()) if int(value) > 0)
    if profile_name == "standard" and fallback_values:
        ladder = fallback_values
    return tuple(sorted(set(int(value) for value in ladder if int(value) > 0)))


def _casino_table_context(
    sim=None,
    prop=None,
    *,
    game="",
    stake_profile="",
    features=None,
    sponsor_kind="",
    sponsor_id=None,
    access_style="",
    table_tone="",
    presentation_accents=None,
):
    game = str(game or "").strip().lower()
    profile = _casino_game_profile(game) or {}
    metadata = prop.get("metadata") if isinstance(prop, dict) and isinstance(prop.get("metadata"), dict) else {}
    prop_context = metadata.get("casino_table_context") if isinstance(metadata, dict) else None
    if not isinstance(prop_context, dict):
        prop_context = {}
    game_contexts = metadata.get("casino_table_contexts") if isinstance(metadata, dict) else None
    if isinstance(game_contexts, dict) and isinstance(game_contexts.get(game), dict):
        prop_context = {**prop_context, **dict(game_contexts.get(game))}

    raw_features = {}
    ignored_features = []
    for source in (prop_context.get("features"), features):
        if isinstance(source, dict):
            raw_features.update(source)
    accepted_feature_keys = {
        "accent", "accent_colors", "accents", "allow_public",
        "bonus_wild_weight_scale", "colors", "debug_table", "house_edge", "math_profile",
        "palette", "stake_profile", "table_tone", "variance",
    }
    for key in sorted(raw_features):
        if str(key).strip().lower() not in accepted_feature_keys:
            ignored_features.append(str(key))

    gang_data = metadata.get("gang_enterprise") if isinstance(metadata, dict) else None
    if not isinstance(gang_data, dict):
        gang_data = {}
    resolved_sponsor_kind = str(
        sponsor_kind
        or prop_context.get("sponsor_kind")
        or ("gang" if gang_data.get("organization_eid") is not None else "")
        or ""
    ).strip().lower()
    resolved_sponsor_id = sponsor_id
    if resolved_sponsor_id is None:
        resolved_sponsor_id = prop_context.get("sponsor_id")
    if resolved_sponsor_id is None and gang_data.get("organization_eid") is not None:
        resolved_sponsor_id = gang_data.get("organization_eid")
    if not resolved_sponsor_kind:
        resolved_sponsor_kind = "house"

    resolved_access = str(
        access_style
        or prop_context.get("access_style")
        or ("gang_linked" if resolved_sponsor_kind == "gang" else "public")
    ).strip().lower() or "public"
    resolved_tone = str(
        table_tone
        or raw_features.get("table_tone")
        or prop_context.get("table_tone")
        or ("watched" if resolved_sponsor_kind == "gang" else "open")
    ).strip().lower() or "open"
    resolved_stake_profile = str(
        stake_profile
        or raw_features.get("stake_profile")
        or prop_context.get("stake_profile")
        or ("gang_house" if resolved_sponsor_kind == "gang" else "standard")
    ).strip().lower() or "standard"

    allowed = True
    access_reason = ""
    if game == "three_bright" and resolved_sponsor_kind != "gang":
        allow_public = bool(raw_features.get("allow_public") or raw_features.get("debug_table"))
        if not allow_public:
            allowed = False
            access_reason = "gang_link_required"

    fallback_bets = tuple(profile.get("bet_options", ()) or ())
    stake_ladder = _casino_stake_profile_ladder(resolved_stake_profile, fallback=fallback_bets)

    accents = []
    for source in (
        presentation_accents,
        prop_context.get("presentation_accents"),
        raw_features.get("colors"),
        raw_features.get("palette"),
        raw_features.get("accent_colors"),
        raw_features.get("accents"),
        raw_features.get("accent"),
    ):
        for color in _casino_color_words_from_hint(source):
            if color not in accents:
                accents.append(color)
    for color in CASINO_THREE_BRIGHT_DEFAULT_COLORS:
        if color not in accents:
            accents.append(color)
    accents = tuple(accents[:6])

    variance = raw_features.get("variance", prop_context.get("variance", 0.5))
    try:
        variance = max(0.0, min(1.0, float(variance)))
    except (TypeError, ValueError):
        variance = 0.5
    math_profile = str(raw_features.get("math_profile", prop_context.get("math_profile", "bounded")) or "bounded").strip().lower()
    if math_profile not in {"bounded", "swingy", "soft", "street"}:
        ignored_features.append(f"math_profile:{math_profile}")
        math_profile = "bounded"
    slot_bonus_wild_weight_scale = None
    if game == "slots":
        slot_bonus_wild_weight_scale = normalize_slot_bonus_wild_weight_scale(
            raw_features.get(
                "bonus_wild_weight_scale",
                prop_context.get("bonus_wild_weight_scale", SLOT_BONUS_WILD_WEIGHT_SCALE),
            )
        )

    sponsor_label = "gang house" if resolved_sponsor_kind == "gang" else "house"
    color_read = "/".join(accents[:2]) if accents else "standard"
    table_read = (
        f"Table read: {sponsor_label}, {resolved_tone}, {color_read} table colors, "
        f"{resolved_stake_profile.replace('_', ' ')} stakes."
    )
    context_id_parts = [
        game or "table",
        resolved_sponsor_kind,
        str(resolved_sponsor_id or "none"),
        resolved_stake_profile,
        resolved_tone,
    ]
    if slot_bonus_wild_weight_scale is not None:
        context_id_parts.append(f"wild-{slot_bonus_wild_weight_scale:.4f}")
    return {
        "game": game,
        "allowed": bool(allowed),
        "access_reason": access_reason,
        "stake_profile": resolved_stake_profile,
        "stake_ladder": tuple(int(value) for value in stake_ladder),
        "math_profile": math_profile,
        "variance": float(variance),
        "bonus_wild_weight_scale": slot_bonus_wild_weight_scale,
        "sponsor_kind": resolved_sponsor_kind,
        "sponsor_id": resolved_sponsor_id,
        "sponsor_summary": sponsor_label,
        "access_style": resolved_access,
        "table_tone": resolved_tone,
        "accent_colors": accents,
        "presentation_tags": tuple(tag for tag in (resolved_sponsor_kind, resolved_access, resolved_tone, math_profile) if tag),
        "table_read": table_read,
        "ignored_features": tuple(sorted(set(ignored_features))),
        "context_id": ":".join(context_id_parts),
    }


def _casino_table_context_summary(context):
    if not isinstance(context, dict):
        return {}
    summary = {
        "game": str(context.get("game", "")).strip().lower(),
        "stake_profile": str(context.get("stake_profile", "")).strip().lower(),
        "math_profile": str(context.get("math_profile", "")).strip().lower(),
        "sponsor_kind": str(context.get("sponsor_kind", "")).strip().lower(),
        "sponsor_id": context.get("sponsor_id"),
        "access_style": str(context.get("access_style", "")).strip().lower(),
        "table_tone": str(context.get("table_tone", "")).strip().lower(),
        "accent_colors": tuple(str(color) for color in tuple(context.get("accent_colors", ()) or ())),
        "presentation_tags": tuple(str(tag) for tag in tuple(context.get("presentation_tags", ()) or ())),
        "table_read": str(context.get("table_read", "")).strip(),
        "ignored_features": tuple(str(key) for key in tuple(context.get("ignored_features", ()) or ())),
    }
    if str(context.get("game", "")).strip().lower() == "slots":
        summary["bonus_wild_weight_scale"] = normalize_slot_bonus_wild_weight_scale(
            context.get("bonus_wild_weight_scale", SLOT_BONUS_WILD_WEIGHT_SCALE)
        )
    return summary


def _casino_preserved_table_context(session):
    if isinstance(session, dict) and isinstance(session.get("table_context"), dict):
        return dict(session.get("table_context") or {})
    return {}


def casino_game_capabilities():
    """Return public casino-game capability metadata for other systems."""

    rows = {}
    for game_id, profile in sorted(CASINO_GAME_PROFILES.items()):
        row = dict(CASINO_GAME_CAPABILITY_DEFAULTS)
        row.update(dict(CASINO_GAME_CAPABILITY_OVERRIDES.get(game_id, {}) or {}))
        row["game_id"] = str(game_id)
        row["public_label"] = str(profile.get("title") or game_id).strip() or str(game_id)
        row["service_label"] = str(profile.get("service_label") or profile.get("title") or game_id).strip() or str(game_id)
        row["menu_label"] = str(profile.get("menu_label") or profile.get("title") or game_id).strip() or str(game_id)
        row["default_stake_profiles"] = tuple(
            str(profile_name)
            for profile_name in ("street", "standard", "gang_street", "gang_house", "gang_high")
            if profile_name in CASINO_TABLE_STAKE_PROFILES
        )
        row["default_bet_options"] = tuple(int(value) for value in tuple(profile.get("bet_options", ()) or ()) if int(value) > 0)
        row["style_tags"] = tuple(
            str(tag).strip().lower()
            for tag in tuple(row.get("style_tags", ()) or ())
            if str(tag).strip()
        )
        rows[str(game_id)] = row
    return rows


def _site_service_state(sim):
    state = getattr(sim, "site_service_state", None)
    if not isinstance(state, dict):
        state = {"cooldowns": {}}
        sim.site_service_state = state
    cooldowns = state.get("cooldowns")
    if not isinstance(cooldowns, dict):
        cooldowns = {}
        state["cooldowns"] = cooldowns
    return state


def _vehicle_sale_quality(quality):
    quality = str(quality or "used").strip().lower()
    if quality not in {"new", "used"}:
        return "used"
    return quality


def _vehicle_sale_quality_title(quality):
    return "New" if _vehicle_sale_quality(quality) == "new" else "Used"


def _vehicle_sale_stock_count(quality):
    quality = _vehicle_sale_quality(quality)
    return 3 if quality == "new" else 5


def _vehicle_sale_inventory(sim):
    state = _site_service_state(sim)
    inventory = state.get("vehicle_sale_inventory")
    if not isinstance(inventory, dict):
        inventory = {}
        state["vehicle_sale_inventory"] = inventory
    return inventory


def _vehicle_sale_offer_record(profile, quality, cycle_index, slot_index):
    quality = _vehicle_sale_quality(quality)
    vehicle_name = f"{profile.get('make', 'Unknown')} {profile.get('model', 'Vehicle')}"
    return {
        "offering_id": f"{quality}-{int(cycle_index)}-{int(slot_index)}",
        "quality": quality,
        "vehicle_name": vehicle_name,
        "make": str(profile.get("make", "Unknown")).strip() or "Unknown",
        "model": str(profile.get("model", "Vehicle")).strip() or "Vehicle",
        "vehicle_class": str(profile.get("vehicle_class", "sedan")).strip().lower() or "sedan",
        "price": int(max(80, _int_or_default(profile.get("price"), 500))),
        "power": max(1, min(10, _int_or_default(profile.get("power"), 5))),
        "durability": max(1, min(10, _int_or_default(profile.get("durability"), 5))),
        "fuel_efficiency": max(1, min(10, _int_or_default(profile.get("fuel_efficiency"), 5))),
        "fuel": max(0, _int_or_default(profile.get("fuel"), _int_or_default(profile.get("fuel_capacity"), 60))),
        "fuel_capacity": max(10, _int_or_default(profile.get("fuel_capacity"), 60)),
        "glyph": str(profile.get("glyph", "&"))[:1] or "&",
        "paint": str(profile.get("paint", "")).strip(),
        "display_color": str(profile.get("paint", "")).strip() or "vehicle_parked",
    }


def _vehicle_sale_generate_offers(sim, prop_or_id, quality, cycle_index):
    prop_id = prop_or_id.get("id") if isinstance(prop_or_id, dict) else prop_or_id
    quality = _vehicle_sale_quality(quality)
    offers = []
    for slot_index in range(_vehicle_sale_stock_count(quality)):
        rng = random.Random(f"{sim.seed}:vehicle_sale_inventory:{prop_id}:{quality}:{int(cycle_index)}:{int(slot_index)}")
        profile = roll_vehicle_profile(rng, quality=quality)
        profile["paint"] = roll_vehicle_paint_key(rng, quality=quality)
        offers.append(_vehicle_sale_offer_record(profile, quality, cycle_index, slot_index))
    offers.sort(key=lambda offer: (int(offer.get("price", 0)), str(offer.get("vehicle_name", ""))))
    for slot_index, offer in enumerate(offers):
        offer["offering_id"] = f"{quality}-{int(cycle_index)}-{int(slot_index)}"
    return offers


def _vehicle_sale_listing(sim, prop_or_id, quality, *, create=True):
    inventory = _vehicle_sale_inventory(sim)
    prop_id = prop_or_id.get("id") if isinstance(prop_or_id, dict) else prop_or_id
    quality = _vehicle_sale_quality(quality)
    key = (str(prop_id), quality)
    listing = inventory.get(key)
    if not isinstance(listing, dict):
        listing = None
    if listing is not None:
        offers = listing.get("offers")
        if not isinstance(offers, list):
            offers = []
            listing["offers"] = offers
    if create and (listing is None or not list(listing.get("offers", ()) or ())):
        next_cycle = int(listing.get("cycle", -1)) + 1 if isinstance(listing, dict) else 0
        listing = {
            "property_id": str(prop_id),
            "quality": quality,
            "cycle": int(next_cycle),
            "offers": _vehicle_sale_generate_offers(sim, prop_id, quality, next_cycle),
        }
        inventory[key] = listing
    return listing


def _vehicle_sale_offers(sim, prop_or_id, quality):
    listing = _vehicle_sale_listing(sim, prop_or_id, quality, create=True)
    offers = list(listing.get("offers", ()) or []) if isinstance(listing, dict) else []
    return [dict(offer) for offer in offers if isinstance(offer, dict)]


def _vehicle_sale_lookup_offer(sim, prop_or_id, quality, offering_id=None):
    listing = _vehicle_sale_listing(sim, prop_or_id, quality, create=True)
    offers = list(listing.get("offers", ()) or []) if isinstance(listing, dict) else []
    if not offers:
        return None
    offering_id = str(offering_id or "").strip().lower()
    if offering_id:
        for offer in offers:
            if str(offer.get("offering_id", "")).strip().lower() == offering_id:
                return dict(offer)
    return dict(offers[0])


def _vehicle_sale_remove_offer(sim, prop_or_id, quality, offering_id):
    listing = _vehicle_sale_listing(sim, prop_or_id, quality, create=False)
    if not isinstance(listing, dict):
        return None
    offers = list(listing.get("offers", ()) or [])
    offering_id = str(offering_id or "").strip().lower()
    for idx, offer in enumerate(offers):
        if str(offer.get("offering_id", "")).strip().lower() != offering_id:
            continue
        removed = dict(offer)
        del offers[idx]
        listing["offers"] = offers
        return removed
    return None


def _vehicle_sale_stats_text(data):
    if not isinstance(data, dict):
        return ""
    vehicle_class = str(data.get("vehicle_class", "")).strip().replace("_", " ")
    power = max(1, min(10, _int_or_default(data.get("power"), 5)))
    durability = max(1, min(10, _int_or_default(data.get("durability"), 5)))
    fuel_efficiency = max(1, min(10, _int_or_default(data.get("fuel_efficiency"), 5)))
    fuel_capacity = max(0, _int_or_default(data.get("fuel_capacity"), 0))
    fuel = max(0, min(fuel_capacity if fuel_capacity > 0 else 9999, _int_or_default(data.get("fuel"), fuel_capacity)))
    bits = []
    if vehicle_class:
        bits.append(vehicle_class.title())
    if fuel_capacity > 0:
        bits.append(f"fuel {fuel}/{fuel_capacity}")
    bits.append(f"P{power}/D{durability}/E{fuel_efficiency}")
    return " | ".join(bits)


def _vehicle_sale_offer_label(offer):
    if not isinstance(offer, dict):
        return "Vehicle"
    vehicle_name = str(offer.get("vehicle_name", "Vehicle")).strip() or "Vehicle"
    price = _credit_amount_label(offer.get("price", 0))
    stats = _vehicle_sale_stats_text(offer)
    if stats:
        return f"{vehicle_name} {price} {stats}"
    return f"{vehicle_name} {price}"


def _site_service_roll_index(sim, eid, prop_or_id, service):
    state = _site_service_state(sim)
    rolls = state.get("roll_counts")
    if not isinstance(rolls, dict):
        rolls = {}
        state["roll_counts"] = rolls
    prop_id = prop_or_id.get("id") if isinstance(prop_or_id, dict) else prop_or_id
    key = (int(eid), str(prop_id), str(service or "").strip().lower())
    index = int(rolls.get(key, 0))
    rolls[key] = index + 1
    return index


def _casino_round_seed(sim, eid, prop_or_id, service, wager, round_index):
    prop_id = prop_or_id.get("id") if isinstance(prop_or_id, dict) else prop_or_id
    return (
        f"{sim.seed}:casino:{prop_id}:{int(eid)}:{str(service or '').strip().lower()}:"
        f"{int(sim.tick)}:{int(round_index)}:{int(wager)}"
    )


def _casino_slot_round_contract(sim, prop_or_id, round_index):
    prop_id = prop_or_id.get("id") if isinstance(prop_or_id, dict) else prop_or_id
    return slot_seed_contract(
        getattr(sim, "seed", 0),
        f"{str(prop_id or 'unplaced-cabinet')}:cheeky-star-aster",
        int(getattr(sim, "tick", 0) or 0),
        sequence=max(0, int(round_index)),
    )


def _casino_social_gain(service, seed_token):
    profile = _casino_game_profile(service)
    social_lo, social_hi = (1, 3)
    if profile:
        social_lo, social_hi = profile.get("social_gain", (1, 3))
    social_rng = random.Random(f"{seed_token}:social")
    social_lo = int(social_lo)
    social_hi = int(max(social_lo, social_hi))
    return social_rng.randint(social_lo, social_hi)


def _casino_card_rank(card):
    return CASINO_CARD_VALUE_BY_RANK.get(str(card or "??")[0].upper(), 0)


def _casino_card_suit(card):
    text = str(card or "??").strip().upper()
    return text[1:2] if len(text) >= 2 else "?"


def _casino_card_label(card):
    text = str(card or "??").strip().upper()
    if len(text) < 2:
        return "??"
    rank = text[0]
    suit = text[1]
    rank_label = "10" if rank == "T" else rank
    return f"{rank_label}{suit}"


def _casino_cards_text(cards):
    rendered = [_casino_card_label(card) for card in list(cards or ())]
    return " ".join(rendered) if rendered else "--"


_CASINO_DIE_ART = {
    1: (".---.", "|   |", "| o |", "|   |", "'---'"),
    2: (".---.", "|o  |", "|   |", "|  o|", "'---'"),
    3: (".---.", "|o  |", "| o |", "|  o|", "'---'"),
    4: (".---.", "|o o|", "|   |", "|o o|", "'---'"),
    5: (".---.", "|o o|", "| o |", "|o o|", "'---'"),
    6: (".---.", "|o o|", "|o o|", "|o o|", "'---'"),
}


def _casino_ascii_card_block(label, cards, *, hide_hole=False):
    shown = []
    for idx, card in enumerate(list(cards or ())):
        if hide_hole and idx == 1:
            shown.append("??")
        else:
            shown.append(_casino_card_label(card))
    if not shown:
        shown = ["??"]

    top = " ".join(".----." for _ in shown)
    middle = " ".join(f"|{str(face).strip()[:4].ljust(4)}|" for face in shown)
    bottom = " ".join("'----'" for _ in shown)
    heading_text = str(label or "Hand").strip() or "Hand"
    return [
        f"{heading_text}:",
        top,
        middle,
        bottom,
    ]


def _casino_ascii_keno_board(*, picks=(), drawn=(), hits=()):
    pick_set = {int(number) for number in list(picks or ())}
    drawn_set = {int(number) for number in list(drawn or ())}
    hit_set = {int(number) for number in list(hits or ())}
    if drawn_set or hit_set:
        lines = ["Keno board: [ticket] {hit} <draw>"]
    else:
        lines = ["Keno board: [ticket]"]
    for row_start in range(1, CASINO_KENO_NUMBER_COUNT + 1, 5):
        cells = []
        for number in range(row_start, min(row_start + 5, CASINO_KENO_NUMBER_COUNT + 1)):
            if number in hit_set:
                cell = f"{{{number:02d}}}"
            elif number in pick_set:
                cell = f"[{number:02d}]"
            elif number in drawn_set:
                cell = f"<{number:02d}>"
            else:
                cell = f" {number:02d} "
            cells.append(cell)
        lines.append(" ".join(cells))
    return lines


def _casino_number_group_lines(label, numbers, *, group_size=8, empty="none"):
    label_text = str(label or "Numbers").strip() or "Numbers"
    try:
        group_size = max(1, int(group_size))
    except (TypeError, ValueError):
        group_size = 8
    values = []
    for number in list(numbers or ()):
        try:
            values.append(int(number))
        except (TypeError, ValueError):
            continue
    if not values:
        return [f"{label_text}: {empty}."]
    prefix = f"{label_text}: "
    lines = []
    for index in range(0, len(values), group_size):
        chunk = " ".join(f"{number:02d}" for number in values[index:index + group_size])
        lines.append(f"{prefix}{chunk}")
    return lines


def _casino_ascii_roll_block(label, roll):
    if not isinstance(roll, dict):
        return []
    die_one = int(roll.get("die_one", 0) or 0)
    die_two = int(roll.get("die_two", 0) or 0)
    total = int(roll.get("total", die_one + die_two) or 0)
    left = _CASINO_DIE_ART.get(die_one, _CASINO_DIE_ART[1])
    right = _CASINO_DIE_ART.get(die_two, _CASINO_DIE_ART[1])
    prefix = f"{str(label or 'Roll').strip()}: "
    pad = " " * len(prefix)
    lines = []
    for idx in range(len(left)):
        leader = prefix if idx == 0 else pad
        lines.append(f"{leader}{left[idx]} {right[idx]}")
    lines.append(f"{pad}total {total}")
    return lines


def _casino_ascii_craps_layout(view="layout"):
    view = str(view or "layout").strip().lower() or "layout"
    if view == "pass_odds":
        return [
            "+-----------------------------+",
            "| PASS LINE | 1X | 2X | 3X    |",
            "| 4/10 2:1  5/9 3:2  6/8 6:5  |",
            "+-----------------------------+",
        ]
    if view == "dont_pass_odds":
        return [
            "+-----------------------------+",
            "| DONT PASS | 1X | 2X | 3X    |",
            "| 4/10 1:2  5/9 2:3  6/8 5:6  |",
            "+-----------------------------+",
        ]
    if view == "place":
        return [
            "+-----------------------------+",
            "| PLACE:  4   5   6   8   9 10|",
            "| PAY:   9:5 7:5 7:6 7:6 7:5 9:5|",
            "+-----------------------------+",
        ]
    if view == "hardways":
        return [
            "+-----------------------------+",
            "| HARDWAYS: 4 | 6 | 8 | 10    |",
            "| PAYS:     7:1 9:1 9:1 7:1   |",
            "+-----------------------------+",
        ]
    if view == "props":
        return [
            "+-----------------------------+",
            "| PROPS: 2  3  11 12  CRAPS 7 |",
            "| PAYS: 31 16 16 31   8    5  |",
            "+-----------------------------+",
        ]
    return [
        "+-----------------------------+",
        "| PASS | DONT | FIELD | ODDS  |",
        "| PLACE 4 5 6 8 9 10 | HARD   |",
        "| PROPS 2 3 11 12 | ANY 7    |",
        "+-----------------------------+",
    ]


def _casino_shuffled_deck(seed_token):
    deck = [f"{rank}{suit}" for suit in CASINO_CARD_SUITS for rank in CASINO_CARD_RANKS]
    rng = random.Random(f"{seed_token}:deck")
    rng.shuffle(deck)
    return deck


def _casino_blackjack_value(card):
    rank = str(card or "??").strip().upper()[:1]
    if rank == "A":
        return 11
    if rank in {"T", "J", "Q", "K"}:
        return 10
    try:
        return int(rank)
    except (TypeError, ValueError):
        return 0


def _casino_blackjack_total(cards):
    total = 0
    aces = 0
    for card in list(cards or ()):
        total += _casino_blackjack_value(card)
        if str(card or "??").strip().upper().startswith("A"):
            aces += 1
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total, aces > 0


def _casino_blackjack_line(label, cards, *, hide_hole=False):
    shown = []
    for idx, card in enumerate(list(cards or ())):
        if hide_hole and idx == 1:
            shown.append("??")
        else:
            shown.append(_casino_card_label(card))
    total, soft = _casino_blackjack_total(cards)
    suffix = ""
    if not hide_hole:
        suffix = f" ({total}"
        if soft and total <= 21:
            suffix += " soft"
        suffix += ")"
    return f"{label}: {' '.join(shown) if shown else '--'}{suffix}"


def _casino_straight_high(ranks):
    unique = sorted({int(rank) for rank in list(ranks or ()) if int(rank) > 0}, reverse=True)
    if 14 in unique:
        unique.append(1)
    streak = 1
    for idx in range(len(unique) - 1):
        if unique[idx] - 1 == unique[idx + 1]:
            streak += 1
            if streak >= 5:
                return unique[idx - 3]
        elif unique[idx] != unique[idx + 1]:
            streak = 1
    return 0


def _casino_rank_name(rank):
    return CASINO_RANK_NAME_BY_VALUE.get(int(rank), str(rank))


def _casino_poker_hand_name(score):
    category = int(score[0]) if score else 0
    primary = int(score[1]) if len(score) > 1 else 0
    secondary = int(score[2]) if len(score) > 2 else 0
    if category == 8 and primary == 14:
        return "royal flush"
    if category == 8:
        return f"{_casino_rank_name(primary)}-high straight flush"
    if category == 7:
        return f"four {_casino_rank_name(primary)}s"
    if category == 6:
        return f"{_casino_rank_name(primary)}s full of {_casino_rank_name(secondary)}s"
    if category == 5:
        return f"{_casino_rank_name(primary)}-high flush"
    if category == 4:
        return f"{_casino_rank_name(primary)}-high straight"
    if category == 3:
        return f"three {_casino_rank_name(primary)}s"
    if category == 2:
        return f"{_casino_rank_name(primary)}s and {_casino_rank_name(secondary)}s"
    if category == 1:
        return f"pair of {_casino_rank_name(primary)}s"
    return f"{_casino_rank_name(primary)}-high"


def _casino_evaluate_five_card_poker(cards):
    ranks = sorted((_casino_card_rank(card) for card in list(cards or ())), reverse=True)
    suits = [_casino_card_suit(card) for card in list(cards or ())]
    counts = Counter(ranks)
    ordered_counts = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    flush = len(set(suits)) == 1 if suits else False
    straight_high = _casino_straight_high(ranks)

    if flush and straight_high:
        return (8, straight_high)

    if ordered_counts and ordered_counts[0][1] == 4:
        quad_rank = ordered_counts[0][0]
        kicker = max(rank for rank in ranks if rank != quad_rank)
        return (7, quad_rank, kicker)

    if len(ordered_counts) >= 2 and ordered_counts[0][1] == 3 and ordered_counts[1][1] >= 2:
        return (6, ordered_counts[0][0], ordered_counts[1][0])

    if flush:
        return tuple([5] + sorted(ranks, reverse=True))

    if straight_high:
        return (4, straight_high)

    if ordered_counts and ordered_counts[0][1] == 3:
        trips = ordered_counts[0][0]
        kickers = sorted((rank for rank in ranks if rank != trips), reverse=True)
        return tuple([3, trips] + kickers)

    pair_ranks = [rank for rank, count in ordered_counts if count == 2]
    if len(pair_ranks) >= 2:
        high_pair, low_pair = sorted(pair_ranks, reverse=True)[:2]
        kicker = max(rank for rank in ranks if rank not in {high_pair, low_pair})
        return (2, high_pair, low_pair, kicker)

    if len(pair_ranks) == 1:
        pair_rank = pair_ranks[0]
        kickers = sorted((rank for rank in ranks if rank != pair_rank), reverse=True)
        return tuple([1, pair_rank] + kickers)

    return tuple([0] + sorted(ranks, reverse=True))


def _casino_best_poker_hand(cards):
    best_score = None
    best_cards = None
    for combo in itertools.combinations(list(cards or ()), 5):
        score = _casino_evaluate_five_card_poker(combo)
        if best_score is None or score > best_score:
            best_score = score
            best_cards = combo
    if best_score is None:
        best_score = (0, 0)
        best_cards = ()
    return {
        "score": best_score,
        "name": _casino_poker_hand_name(best_score),
        "category": CASINO_POKER_CATEGORY_NAMES.get(int(best_score[0]), "hand"),
        "cards": tuple(best_cards),
    }


def _casino_video_poker_normalize_session(session):
    if not isinstance(session, dict):
        return None
    cards = [
        str(card).strip().upper()
        for card in list(session.get("cards", ()) or ())[:5]
        if str(card).strip()
    ]
    holds_raw = list(session.get("holds", ()) or ())
    holds = []
    for idx in range(len(cards)):
        holds.append(bool(holds_raw[idx]) if idx < len(holds_raw) else False)
    return {
        "service": "video_poker",
        "seed_token": str(session.get("seed_token", "")).strip(),
        "wager": int(session.get("wager", 0)),
        "stake": int(session.get("stake", session.get("wager", 0))),
        "deck": list(session.get("deck", ()) or ()),
        "deck_index": int(session.get("deck_index", 0)),
        "cards": cards,
        "holds": holds,
        "property_id": session.get("property_id"),
        "property_name": str(session.get("property_name", "")).strip(),
        "table_context": _casino_preserved_table_context(session),
    }


def _casino_video_poker_start(seed_token, wager):
    deck = _casino_shuffled_deck(seed_token)
    return {
        "service": "video_poker",
        "seed_token": str(seed_token),
        "wager": int(wager),
        "stake": int(wager),
        "deck": list(deck),
        "deck_index": 5,
        "cards": list(deck[:5]),
        "holds": [False, False, False, False, False],
    }


def _casino_video_poker_toggle_hold(session, card_index):
    current = _casino_video_poker_normalize_session(session)
    if not current:
        return None
    try:
        idx = int(card_index)
    except (TypeError, ValueError):
        return current
    if 0 <= idx < len(current["holds"]):
        current["holds"][idx] = not bool(current["holds"][idx])
    return current


def _casino_video_poker_payout_profile(score):
    category = int(score[0]) if score else 0
    primary = int(score[1]) if len(score) > 1 else 0
    if category == 8 and primary == 14:
        return int(CASINO_VIDEO_POKER_PAYOUT_MULTIPLIERS.get("royal_flush", 0)), "royal_flush"
    if category >= 2:
        return int(CASINO_VIDEO_POKER_PAYOUT_MULTIPLIERS.get(category, 0)), {
            8: "straight_flush",
            7: "four_kind",
            6: "full_house",
            5: "flush",
            4: "straight",
            3: "three_kind",
            2: "two_pair",
        }.get(category, "blank")
    if category == 1 and primary >= 11:
        return int(CASINO_VIDEO_POKER_PAYOUT_MULTIPLIERS.get("jacks_or_better", 0)), "jacks_or_better"
    return 0, "blank"


def _casino_video_poker_outcome_text(outcome_key):
    mapping = {
        "royal_flush": (
            "Royal flush.",
            "The machine erupts as the top straight flush lands clean across the screen.",
        ),
        "straight_flush": (
            "Straight flush.",
            "Five perfect runners in one suit lock in a rare premium payout.",
        ),
        "four_kind": (
            "Four of a kind.",
            "The draw spikes trips into quads and the cabinet starts flashing.",
        ),
        "full_house": (
            "Full house.",
            "A made pair fills up behind the trips for one of the best routine pays on the board.",
        ),
        "flush": (
            "Flush.",
            "All five cards stay in one suit and the machine pays a healthy return.",
        ),
        "straight": (
            "Straight.",
            "The ranks line up edge to edge and the draw pays solidly.",
        ),
        "three_kind": (
            "Trips.",
            "A third copy lands and turns the hand into a paying set.",
        ),
        "two_pair": (
            "Two pair.",
            "The draw catches the second pair and nudges the hand into profit.",
        ),
        "jacks_or_better": (
            "Jacks or better.",
            "The high pair is enough to keep the credits cycling.",
        ),
        "blank": (
            "No paying hand.",
            "The one draw misses the pay table and the machine keeps the stake.",
        ),
    }
    return mapping.get(str(outcome_key or "blank").strip().lower(), mapping["blank"])


def _casino_video_poker_draw(session):
    current = _casino_video_poker_normalize_session(session)
    if not current:
        return None

    cards = list(current.get("cards", ()) or ())
    holds = list(current.get("holds", ()) or ())
    deck = list(current.get("deck", ()) or ())
    deck_index = int(current.get("deck_index", 0))
    held_slots = tuple(idx + 1 for idx, held in enumerate(holds) if held)
    drawn_slots = []
    for idx, held in enumerate(holds):
        if held:
            continue
        if deck_index < len(deck):
            cards[idx] = deck[deck_index]
            deck_index += 1
        drawn_slots.append(idx + 1)

    score = _casino_evaluate_five_card_poker(cards)
    payout_mult, outcome_key = _casino_video_poker_payout_profile(score)
    hand_name = _casino_poker_hand_name(score)
    payout = int(max(0, payout_mult) * int(current.get("wager", 0)))
    headline, detail = _casino_video_poker_outcome_text(outcome_key)
    if held_slots:
        hold_line = f"Held: {', '.join(str(slot) for slot in held_slots)}."
    else:
        hold_line = "Held: none."
    if drawn_slots:
        draw_line = f"Drawn: {', '.join(str(slot) for slot in drawn_slots)}."
    else:
        draw_line = "Drawn: none (stand pat)."
    result_lines = []
    result_lines.extend(_casino_ascii_card_block("Final hand", cards))
    result_lines.extend([
        f"Final hand: {_casino_cards_text(cards)}",
        hold_line,
        draw_line,
        f"Made: {hand_name}.",
        detail,
    ])

    return {
        "service": "video_poker",
        "wager": int(current["wager"]),
        "stake": int(current["stake"]),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": detail,
        "summary": f"Final hand {_casino_cards_text(cards)} ({hand_name}). {headline}",
        "result_lines": result_lines,
        "player_cards": tuple(cards),
        "player_hand_name": str(hand_name),
        "held_slots": tuple(int(slot) for slot in held_slots),
        "drawn_slots": tuple(int(slot) for slot in drawn_slots),
        "social_gain": _casino_social_gain("video_poker", f"{current['seed_token']}:{outcome_key}"),
        "stake_already_paid": True,
    }


def _casino_keno_normalize_session(session):
    if not isinstance(session, dict):
        return None
    picks = []
    seen = set()
    for raw in list(session.get("picks", ()) or ()):
        try:
            number = int(raw)
        except (TypeError, ValueError):
            continue
        if number < 1 or number > CASINO_KENO_NUMBER_COUNT or number in seen:
            continue
        seen.add(number)
        picks.append(number)
        if len(picks) >= CASINO_KENO_MAX_PICKS:
            break
    picks.sort()
    return {
        "service": "keno",
        "seed_token": str(session.get("seed_token", "")).strip(),
        "wager": int(session.get("wager", 0)),
        "stake": int(session.get("stake", session.get("wager", 0))),
        "picks": picks,
        "cursor": max(1, min(int(session.get("cursor", 1) or 1), CASINO_KENO_NUMBER_COUNT)),
        "property_id": session.get("property_id"),
        "property_name": str(session.get("property_name", "")).strip(),
        "table_context": _casino_preserved_table_context(session),
    }


def _casino_keno_start(seed_token, wager):
    return {
        "service": "keno",
        "seed_token": str(seed_token),
        "wager": int(wager),
        "stake": int(wager),
        "picks": [],
        "cursor": 1,
    }


def _casino_keno_toggle_pick(session, number):
    current = _casino_keno_normalize_session(session)
    if not current:
        return None
    try:
        ticket_number = int(number)
    except (TypeError, ValueError):
        return current
    if ticket_number < 1 or ticket_number > CASINO_KENO_NUMBER_COUNT:
        return current
    picks = list(current.get("picks", ()) or ())
    if ticket_number in picks:
        picks.remove(ticket_number)
    elif len(picks) < CASINO_KENO_MAX_PICKS:
        picks.append(ticket_number)
    picks.sort()
    current["picks"] = picks
    current["cursor"] = ticket_number
    return current


def _casino_keno_payout_multiplier(pick_count, hit_count):
    try:
        pick_count = int(pick_count)
        hit_count = int(hit_count)
    except (TypeError, ValueError):
        return 0.0
    return float(CASINO_KENO_PAYOUT_MULTIPLIERS.get(pick_count, {}).get(hit_count, 0.0) or 0.0)


def _casino_keno_multiplier_text(multiplier):
    try:
        value = float(multiplier)
    except (TypeError, ValueError):
        value = 0.0
    if value <= 0.0:
        return "x0"
    if abs(value - round(value)) < 0.001:
        return f"x{int(round(value))}"
    return f"x{value:.1f}".rstrip("0").rstrip(".")


def _casino_keno_outcome_text(pick_count, hit_count, payout_mult):
    try:
        payout_value = float(payout_mult)
    except (TypeError, ValueError):
        payout_value = 0.0
    if payout_value <= 0:
        return (
            "Blank board.",
            "The blower misses your ticket and the house keeps the wager.",
        )
    if int(hit_count) >= int(pick_count) and int(pick_count) > 0:
        return (
            "Perfect ticket.",
            "Every marked number comes out of the cage and the ticket pays hot.",
        )
    if int(hit_count) >= max(2, int(pick_count) - 1):
        return (
            "Hot ticket.",
            "Enough of your numbers land to turn the ticket into a real hit.",
        )
    return (
        "Small return.",
        "A couple of your spots sneak through for a modest keno payback.",
    )


def _casino_keno_draw(session):
    current = _casino_keno_normalize_session(session)
    if not current:
        return None
    picks = tuple(int(number) for number in list(current.get("picks", ()) or ()))
    if not picks:
        return None

    draw_rng = random.Random(f"{current['seed_token']}:keno")
    drawn_numbers = tuple(sorted(
        int(number)
        for number in draw_rng.sample(range(1, CASINO_KENO_NUMBER_COUNT + 1), CASINO_KENO_DRAW_COUNT)
    ))
    drawn_set = set(drawn_numbers)
    hit_numbers = tuple(number for number in picks if number in drawn_set)
    pick_count = len(picks)
    hit_count = len(hit_numbers)
    payout_mult = _casino_keno_payout_multiplier(pick_count, hit_count)
    payout = int(round(max(0.0, payout_mult) * int(current.get("wager", 0))))
    headline, detail = _casino_keno_outcome_text(pick_count, hit_count, payout_mult)
    result_lines = []
    result_lines.extend(_casino_ascii_keno_board(picks=picks, drawn=drawn_numbers, hits=hit_numbers))
    result_lines.extend(_casino_number_group_lines("Ticket", picks, group_size=8))
    result_lines.extend(_casino_number_group_lines("Draw", drawn_numbers, group_size=8))
    result_lines.extend([
        (
            f"{_casino_number_group_lines('Hits', hit_numbers, group_size=8)[0]} "
            f"({hit_count}/{pick_count})."
            if hit_numbers
            else f"Hits: none (0/{pick_count})."
        ),
        (
            f"Pay row {pick_count}: {_casino_keno_multiplier_text(payout_mult)} on {hit_count} hit{'s' if hit_count != 1 else ''}."
            if payout_mult > 0
            else f"Pay row {pick_count}: no return on this miss."
        ),
        detail,
    ])

    return {
        "service": "keno",
        "wager": int(current["wager"]),
        "stake": int(current["stake"]),
        "payout": int(payout),
        "outcome_key": "pay" if payout > 0 else "blank",
        "headline": headline,
        "detail": detail,
        "summary": (
            f"Ticket {' '.join(f'{number:02d}' for number in picks)} catches "
            f"{hit_count} of {pick_count}. {headline}"
        ),
        "result_lines": result_lines,
        "picked_numbers": picks,
        "drawn_numbers": drawn_numbers,
        "hit_numbers": hit_numbers,
        "pick_count": int(pick_count),
        "hit_count": int(hit_count),
        "payout_mult": float(payout_mult),
        "number_count": int(CASINO_KENO_NUMBER_COUNT),
        "draw_count": int(CASINO_KENO_DRAW_COUNT),
        "max_picks": int(CASINO_KENO_MAX_PICKS),
        "payout_table_key": f"{pick_count}:{hit_count}",
        "social_gain": _casino_social_gain("keno", f"{current['seed_token']}:{pick_count}:{hit_count}"),
        "stake_already_paid": True,
    }


def _casino_roulette_normalize_session(session):
    if not isinstance(session, dict):
        return None
    bets = {}
    for raw_key, raw_units in dict(session.get("bets", {}) or {}).items():
        market = _casino_roulette_market_from_key(raw_key)
        if not market:
            continue
        try:
            units = int(raw_units)
        except (TypeError, ValueError):
            continue
        if units > 0:
            bets[market["key"]] = units
    wager = int(session.get("wager", 0))
    cursor_key = str(session.get("cursor_key", "straight:0") or "straight:0").strip().lower() or "straight:0"
    if not _casino_roulette_market_from_key(cursor_key):
        cursor_key = "straight:0"
    return {
        "service": "roulette",
        "seed_token": str(session.get("seed_token", "")).strip(),
        "wager": wager,
        "stake": int(sum(int(units) for units in bets.values()) * max(0, wager)),
        "bets": bets,
        "spin_index": max(0, int(session.get("spin_index", 0) or 0)),
        "cursor_key": cursor_key,
        "property_id": session.get("property_id"),
        "property_name": str(session.get("property_name", "")).strip(),
        "table_context": _casino_preserved_table_context(session),
    }


def _casino_roulette_start(seed_token, wager):
    return {
        "service": "roulette",
        "seed_token": str(seed_token),
        "wager": int(wager),
        "stake": 0,
        "bets": {},
        "spin_index": 0,
        "cursor_key": "straight:0",
    }


def _casino_roulette_color(number):
    try:
        pocket = int(number)
    except (TypeError, ValueError):
        pocket = 0
    if pocket == 0:
        return "green"
    return "red" if pocket in CASINO_ROULETTE_RED_NUMBERS else "black"


def _casino_roulette_bet_label(bet_kind, bet_value=None):
    kind = str(bet_kind or "").strip().lower()
    if kind == "straight":
        try:
            number = int(bet_value)
        except (TypeError, ValueError):
            number = 0
        return f"Straight {number:02d}"
    if kind == "color":
        value = str(bet_value or "").strip().lower()
        return value.title() or "Color"
    if kind == "parity":
        value = str(bet_value or "").strip().lower()
        return "Odd" if value == "odd" else "Even"
    if kind == "range":
        value = str(bet_value or "").strip().lower()
        return "1-18" if value == "low" else "19-36"
    if kind == "dozen":
        try:
            dozen = int(bet_value)
        except (TypeError, ValueError):
            dozen = 1
        if dozen == 2:
            return "2nd Dozen (13-24)"
        if dozen == 3:
            return "3rd Dozen (25-36)"
        return "1st Dozen (1-12)"
    if kind == "column":
        try:
            column = int(bet_value)
        except (TypeError, ValueError):
            column = 1
        return f"Column {max(1, min(3, column))}"
    return "Roulette Bet"


def _casino_roulette_bet_key(bet_kind, bet_value=None):
    kind = str(bet_kind or "").strip().lower()
    if kind == "straight":
        try:
            return f"straight:{int(bet_value)}"
        except (TypeError, ValueError):
            return ""
    if kind in {"color", "parity", "range"}:
        value = str(bet_value or "").strip().lower()
        return f"{kind}:{value}" if value else ""
    if kind in {"dozen", "column"}:
        try:
            return f"{kind}:{int(bet_value)}"
        except (TypeError, ValueError):
            return ""
    return ""


def _casino_roulette_market_from_key(market_key):
    key = str(market_key or "").strip().lower()
    if not key:
        return None
    kind, _sep, raw_value = key.partition(":")
    if kind == "straight":
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None
        if value < 0 or value > CASINO_ROULETTE_NUMBER_MAX:
            return None
    elif kind == "color":
        value = str(raw_value or "").strip().lower()
        if value not in {"red", "black"}:
            return None
    elif kind == "parity":
        value = str(raw_value or "").strip().lower()
        if value not in {"odd", "even"}:
            return None
    elif kind == "range":
        value = str(raw_value or "").strip().lower()
        if value not in {"low", "high"}:
            return None
    elif kind == "dozen":
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None
        if value not in {1, 2, 3}:
            return None
    elif kind == "column":
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None
        if value not in {1, 2, 3}:
            return None
    else:
        return None
    normalized_key = _casino_roulette_bet_key(kind, value)
    return {
        "key": normalized_key,
        "kind": kind,
        "value": value,
        "label": _casino_roulette_bet_label(kind, value),
    }


def _casino_roulette_payout_multiplier(bet_kind):
    kind = str(bet_kind or "").strip().lower()
    if kind == "straight":
        return 36
    if kind in {"dozen", "column"}:
        return 3
    return 2


def _casino_roulette_bet_hits(spin_number, bet_kind, bet_value=None):
    kind = str(bet_kind or "").strip().lower()
    pocket = int(spin_number)
    if kind == "straight":
        try:
            return pocket == int(bet_value)
        except (TypeError, ValueError):
            return False
    if pocket == 0:
        return False
    if kind == "color":
        return _casino_roulette_color(pocket) == str(bet_value or "").strip().lower()
    if kind == "parity":
        value = str(bet_value or "").strip().lower()
        return (pocket % 2 == 1) if value == "odd" else (pocket % 2 == 0)
    if kind == "range":
        value = str(bet_value or "").strip().lower()
        if value == "low":
            return 1 <= pocket <= 18
        return 19 <= pocket <= CASINO_ROULETTE_NUMBER_MAX
    if kind == "dozen":
        try:
            dozen = int(bet_value)
        except (TypeError, ValueError):
            return False
        lo = ((dozen - 1) * 12) + 1
        hi = min(CASINO_ROULETTE_NUMBER_MAX, lo + 11)
        return lo <= pocket <= hi
    if kind == "column":
        try:
            column = int(bet_value)
        except (TypeError, ValueError):
            return False
        return ((pocket - 1) % 3) + 1 == max(1, min(3, column))
    return False


def _casino_roulette_stage_bet(session, market_key):
    current = _casino_roulette_normalize_session(session)
    market = _casino_roulette_market_from_key(market_key)
    if not current or not market:
        return None
    bets = dict(current.get("bets", {}) or {})
    bets[market["key"]] = int(bets.get(market["key"], 0) or 0) + 1
    current["bets"] = bets
    current["cursor_key"] = market["key"]
    current["stake"] = int(sum(int(units) for units in bets.values()) * int(current.get("wager", 0)))
    return current


def _casino_roulette_remove_bet(session, market_key):
    current = _casino_roulette_normalize_session(session)
    market = _casino_roulette_market_from_key(market_key)
    if not current or not market:
        return None
    bets = dict(current.get("bets", {}) or {})
    units = int(bets.get(market["key"], 0) or 0)
    if units <= 1:
        bets.pop(market["key"], None)
    else:
        bets[market["key"]] = units - 1
    current["bets"] = bets
    current["cursor_key"] = market["key"]
    current["stake"] = int(sum(int(raw_units) for raw_units in bets.values()) * int(current.get("wager", 0)))
    return current


def _casino_roulette_resolve(session):
    current = _casino_roulette_normalize_session(session)
    if not current:
        return None
    bets = dict(current.get("bets", {}) or {})
    if not bets:
        return None

    spin_rng = random.Random(f"{current['seed_token']}:roulette:{int(current.get('spin_index', 0))}")
    spin_number = spin_rng.randint(0, CASINO_ROULETTE_NUMBER_MAX)
    spin_color = _casino_roulette_color(spin_number)
    chip_value = int(current.get("wager", 0))
    payout = 0
    resolved_stake = 0
    bet_slip = []
    bet_outcomes = []
    hit_count = 0

    for key, units in sorted(bets.items()):
        market = _casino_roulette_market_from_key(key)
        if not market:
            continue
        unit_count = max(0, int(units))
        if unit_count <= 0:
            continue
        stake = int(unit_count * chip_value)
        hit = _casino_roulette_bet_hits(spin_number, market["kind"], market["value"])
        payout_mult = _casino_roulette_payout_multiplier(market["kind"]) if hit else 0
        bet_payout = int(max(0, payout_mult) * stake)
        payout += bet_payout
        resolved_stake += stake
        if hit:
            hit_count += 1
        bet_slip.append({
            "key": market["key"],
            "label": market["label"],
            "units": unit_count,
            "stake": stake,
        })
        bet_outcomes.append({
            "key": market["key"],
            "label": market["label"],
            "units": unit_count,
            "stake": stake,
            "hit": bool(hit),
            "payout": int(bet_payout),
            "profit": int(bet_payout - stake),
        })

    if hit_count > 0 and any(outcome["key"].startswith("straight:") and outcome["hit"] for outcome in bet_outcomes):
        headline = "Straight-up hit."
        detail = "The ball dives straight into one of your numbers and the croupier builds a tall payout."
        outcome_key = "straight"
    elif hit_count > 0:
        headline = "The wheel pays."
        detail = "One or more of your outside marks catch the winner and the felt starts flowing back your way."
        outcome_key = "hit"
    elif spin_number == 0:
        headline = "Zero sweeps the board."
        detail = "The ball settles on 0 green and wipes out the outside action."
        outcome_key = "zero"
    else:
        headline = "No hit."
        detail = "The ball lands away from your mark and the house keeps the chip."
        outcome_key = "miss"

    result_lines = [
        f"Spin: {spin_number:02d} {spin_color.title()}",
        f"Slip: {len(bet_outcomes)} market(s) at {_credit_amount_label(chip_value)} each.",
    ]
    for outcome in bet_outcomes:
        result_lines.append(
            f"{outcome['label']}: {outcome['units']} chip(s) | "
            f"{'hit' if outcome['hit'] else 'miss'} | "
            f"{outcome['profit']:+d}c."
        )
    result_lines.append(detail)

    return {
        "service": "roulette",
        "wager": int(chip_value),
        "stake": int(resolved_stake),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": detail,
        "summary": f"Spin {spin_number:02d} {spin_color}. Slip {len(bet_outcomes)} market(s). {headline}",
        "result_lines": result_lines,
        "spin_number": int(spin_number),
        "spin_color": str(spin_color),
        "bet_slip": tuple(bet_slip),
        "bet_outcomes": tuple(bet_outcomes),
        "social_gain": _casino_social_gain("roulette", f"{current['seed_token']}:{spin_number}:{outcome_key}:{len(bet_outcomes)}"),
        "stake_already_paid": True,
    }


def _casino_craps_normalize_session(session):
    if not isinstance(session, dict):
        return None
    bets = {}
    for raw_key, raw_units in dict(session.get("bets", {}) or {}).items():
        market = _casino_craps_market_from_key(raw_key)
        if not market:
            continue
        try:
            units = int(raw_units)
        except (TypeError, ValueError):
            continue
        if units > 0:
            bets[market["key"]] = units
    wager = int(session.get("wager", 0))
    roll_history = []
    for raw in list(session.get("roll_history", ()) or ()):
        if not isinstance(raw, dict):
            continue
        roll_history.append({
            "die_one": int(raw.get("die_one", 0) or 0),
            "die_two": int(raw.get("die_two", 0) or 0),
            "total": int(raw.get("total", 0) or 0),
        })
    phase = str(session.get("phase", "come_out") or "come_out").strip().lower()
    if phase not in {"come_out", "point"}:
        phase = "come_out"
    cursor_key = str(session.get("cursor_key", "pass") or "pass").strip().lower() or "pass"
    if not _casino_craps_market_from_key(cursor_key):
        cursor_key = "pass"
    return {
        "service": "craps",
        "seed_token": str(session.get("seed_token", "")).strip(),
        "wager": wager,
        "stake": int(sum(int(units) for units in bets.values()) * max(0, wager)),
        "bets": bets,
        "phase": phase,
        "point_number": max(0, int(session.get("point_number", 0) or 0)),
        "roll_index": max(0, int(session.get("roll_index", 0) or 0)),
        "roll_history": roll_history,
        "cursor_key": cursor_key,
        "property_id": session.get("property_id"),
        "property_name": str(session.get("property_name", "")).strip(),
        "table_context": _casino_preserved_table_context(session),
    }


def _casino_craps_start(seed_token, wager):
    return {
        "service": "craps",
        "seed_token": str(seed_token),
        "wager": int(wager),
        "stake": 0,
        "bets": {},
        "phase": "come_out",
        "point_number": 0,
        "roll_index": 0,
        "roll_history": [],
        "cursor_key": "pass",
    }


def _casino_craps_bet_label(bet_kind, bet_value=None):
    kind = str(bet_kind or "").strip().lower()
    if kind == "pass_odds":
        try:
            mult = int(bet_value)
        except (TypeError, ValueError):
            mult = 1
        return f"Pass Line + {max(1, mult)}x Odds"
    if kind == "dont_pass":
        return "Don't Pass"
    if kind == "dont_pass_odds":
        try:
            mult = int(bet_value)
        except (TypeError, ValueError):
            mult = 1
        return f"Don't Pass + {max(1, mult)}x Odds"
    if kind == "field":
        return "Field"
    if kind == "place":
        try:
            number = int(bet_value)
        except (TypeError, ValueError):
            number = 0
        return f"Place {number}"
    if kind == "hardway":
        try:
            number = int(bet_value)
        except (TypeError, ValueError):
            number = 0
        return f"Hard {number}"
    if kind == "prop":
        value = str(bet_value or "").strip().lower()
        labels = {
            "2": "Snake Eyes (2)",
            "3": "Ace-Deuce (3)",
            "11": "Yo (11)",
            "12": "Boxcars (12)",
            "any_craps": "Any Craps",
            "any_seven": "Any Seven",
        }
        return labels.get(value, "Proposition Bet")
    return "Pass Line"


def _casino_craps_bet_key(bet_kind, bet_value=None):
    kind = str(bet_kind or "").strip().lower()
    if kind in {"pass", "dont_pass", "field", "pass_odds", "dont_pass_odds"}:
        return kind
    if kind == "place":
        try:
            return f"place:{int(bet_value)}"
        except (TypeError, ValueError):
            return ""
    if kind == "hardway":
        try:
            return f"hardway:{int(bet_value)}"
        except (TypeError, ValueError):
            return ""
    if kind == "prop":
        value = str(bet_value or "").strip().lower()
        return f"prop:{value}" if value else ""
    return ""


def _casino_craps_market_from_key(market_key):
    key = str(market_key or "").strip().lower()
    if not key:
        return None
    kind, _sep, raw_value = key.partition(":")
    if kind in {"pass", "dont_pass", "field", "pass_odds", "dont_pass_odds"}:
        value = None
        normalized_kind = kind
    elif kind == "place":
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None
        if value not in {4, 5, 6, 8, 9, 10}:
            return None
        normalized_kind = "place"
    elif kind == "hardway":
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None
        if value not in {4, 6, 8, 10}:
            return None
        normalized_kind = "hardway"
    elif kind == "prop":
        value = str(raw_value or "").strip().lower()
        if value not in {"2", "3", "11", "12", "any_craps", "any_seven"}:
            return None
        normalized_kind = "prop"
    else:
        return None
    normalized_key = _casino_craps_bet_key(normalized_kind, value)
    return {
        "key": normalized_key,
        "kind": normalized_kind,
        "value": value,
        "label": _casino_craps_bet_label(normalized_kind, value),
    }


def _casino_craps_roll_pair(rng):
    die_one = rng.randint(1, 6)
    die_two = rng.randint(1, 6)
    return die_one, die_two, die_one + die_two


def _casino_craps_roll_text(roll):
    die_one = int(roll.get("die_one", 0))
    die_two = int(roll.get("die_two", 0))
    total = int(roll.get("total", die_one + die_two))
    return f"{die_one}+{die_two}={total}"


def _casino_craps_profit_ratio(stake, numerator, denominator):
    stake = max(0, int(stake))
    denominator = max(1, int(denominator))
    return int(round(float(stake) * float(int(numerator)) / float(denominator)))


def _casino_craps_odds_profit(point_number, odds_stake, *, lay=False):
    point = int(point_number)
    if point in {4, 10}:
        ratio = (1, 2) if lay else (2, 1)
    elif point in {5, 9}:
        ratio = (2, 3) if lay else (3, 2)
    else:
        ratio = (5, 6) if lay else (6, 5)
    return _casino_craps_profit_ratio(odds_stake, ratio[0], ratio[1])


def _casino_craps_place_profit(number, stake):
    number = int(number)
    ratios = {
        4: (9, 5),
        5: (7, 5),
        6: (7, 6),
        8: (7, 6),
        9: (7, 5),
        10: (9, 5),
    }
    ratio = ratios.get(number)
    if not ratio:
        return 0
    return _casino_craps_profit_ratio(stake, ratio[0], ratio[1])


def _casino_craps_stage_bet(session, market_key):
    current = _casino_craps_normalize_session(session)
    market = _casino_craps_market_from_key(market_key)
    if not current or not market:
        return None
    kind = market["kind"]
    bets = dict(current.get("bets", {}) or {})
    if kind in {"pass_odds", "dont_pass_odds"}:
        if str(current.get("phase", "come_out")) != "point" or int(current.get("point_number", 0)) <= 0:
            return None
        line_key = "pass" if kind == "pass_odds" else "dont_pass"
        line_units = int(bets.get(line_key, 0) or 0)
        if line_units <= 0:
            return None
        if int(bets.get(market["key"], 0) or 0) >= (line_units * 3):
            return None
    bets[market["key"]] = int(bets.get(market["key"], 0) or 0) + 1
    current["bets"] = bets
    current["cursor_key"] = market["key"]
    current["stake"] = int(sum(int(units) for units in bets.values()) * int(current.get("wager", 0)))
    return current


def _casino_craps_remove_bet(session, market_key):
    current = _casino_craps_normalize_session(session)
    market = _casino_craps_market_from_key(market_key)
    if not current or not market:
        return None
    bets = dict(current.get("bets", {}) or {})
    units = int(bets.get(market["key"], 0) or 0)
    if units <= 1:
        bets.pop(market["key"], None)
    else:
        bets[market["key"]] = units - 1
    current["bets"] = bets
    current["cursor_key"] = market["key"]
    current["stake"] = int(sum(int(raw_units) for raw_units in bets.values()) * int(current.get("wager", 0)))
    return current


def _casino_craps_resolve(session):
    current = _casino_craps_normalize_session(session)
    if not current:
        return None, None
    bets = dict(current.get("bets", {}) or {})
    if not bets:
        return current, None

    roll_rng = random.Random(f"{current['seed_token']}:craps:{int(current.get('roll_index', 0))}")
    die_one, die_two, total = _casino_craps_roll_pair(roll_rng)
    roll = {
        "die_one": int(die_one),
        "die_two": int(die_two),
        "total": int(total),
    }
    current["roll_index"] = int(current.get("roll_index", 0)) + 1
    current["roll_history"] = list(current.get("roll_history", ()) or ()) + [roll]

    phase_before = str(current.get("phase", "come_out"))
    point_before = int(current.get("point_number", 0) or 0)
    point_after = int(point_before)
    phase_after = phase_before
    if phase_before == "come_out" and total in {4, 5, 6, 8, 9, 10}:
        phase_after = "point"
        point_after = int(total)
    elif phase_before == "point" and total in {7, point_before}:
        phase_after = "come_out"
        point_after = 0

    resolved_keys = set()
    payout = 0
    resolved_stake = 0
    messages = []
    bet_outcomes = []

    def _resolve_market(market, units, *, hit, payout_amount, message, outcome_key):
        nonlocal payout, resolved_stake
        stake_amount = int(max(0, units) * int(current.get("wager", 0)))
        resolved_stake += stake_amount
        payout += int(max(0, payout_amount))
        resolved_keys.add(market["key"])
        messages.append(str(message).strip())
        bet_outcomes.append({
            "key": market["key"],
            "label": market["label"],
            "units": int(units),
            "stake": int(stake_amount),
            "hit": bool(hit),
            "payout": int(max(0, payout_amount)),
            "profit": int(max(0, payout_amount) - stake_amount),
            "outcome_key": str(outcome_key or "table"),
        })

    prop_totals = {
        "2": {2},
        "3": {3},
        "11": {11},
        "12": {12},
        "any_craps": {2, 3, 12},
        "any_seven": {7},
    }
    prop_gross = {
        "2": 31,
        "3": 16,
        "11": 16,
        "12": 31,
        "any_craps": 8,
        "any_seven": 5,
    }

    for key, units in sorted(bets.items()):
        market = _casino_craps_market_from_key(key)
        if not market:
            continue
        unit_count = max(0, int(units))
        if unit_count <= 0:
            continue
        stake = int(unit_count * int(current.get("wager", 0)))
        kind = market["kind"]
        value = market["value"]
        if kind == "field":
            if total in {2, 12}:
                _resolve_market(market, unit_count, hit=True, payout_amount=stake * 3, message="Field double pays.", outcome_key="field_double")
            elif total in {3, 4, 9, 10, 11}:
                _resolve_market(market, unit_count, hit=True, payout_amount=stake * 2, message="Field wins even money.", outcome_key="field_win")
            else:
                _resolve_market(market, unit_count, hit=False, payout_amount=0, message="Field misses.", outcome_key="field_miss")
            continue
        if kind == "prop":
            winning_totals = prop_totals.get(str(value), set())
            if total in winning_totals:
                _resolve_market(
                    market,
                    unit_count,
                    hit=True,
                    payout_amount=stake * int(prop_gross.get(str(value), 0)),
                    message=f"{market['label']} hits.",
                    outcome_key=f"prop_{value}_hit",
                )
            else:
                _resolve_market(market, unit_count, hit=False, payout_amount=0, message=f"{market['label']} misses.", outcome_key=f"prop_{value}_miss")
            continue
        if kind == "pass":
            if phase_before == "come_out":
                if total in {7, 11}:
                    _resolve_market(market, unit_count, hit=True, payout_amount=stake * 2, message="Pass line wins on the natural.", outcome_key="pass_natural")
                elif total in {2, 3, 12}:
                    _resolve_market(market, unit_count, hit=False, payout_amount=0, message="Pass line loses on craps.", outcome_key="pass_craps")
            else:
                if total == point_before:
                    _resolve_market(market, unit_count, hit=True, payout_amount=stake * 2, message=f"Pass line makes the point {point_before}.", outcome_key="pass_point")
                elif total == 7:
                    _resolve_market(market, unit_count, hit=False, payout_amount=0, message="Pass line drops on the seven out.", outcome_key="seven_out")
            continue
        if kind == "dont_pass":
            if phase_before == "come_out":
                if total in {2, 3}:
                    _resolve_market(market, unit_count, hit=True, payout_amount=stake * 2, message="Don't pass wins on craps.", outcome_key="dont_pass_win")
                elif total in {7, 11}:
                    _resolve_market(market, unit_count, hit=False, payout_amount=0, message="Don't pass loses on the natural.", outcome_key="dont_pass_lose")
                elif total == 12:
                    _resolve_market(market, unit_count, hit=False, payout_amount=stake, message="Bar twelve pushes the don't pass.", outcome_key="dont_pass_push")
            else:
                if total == 7:
                    _resolve_market(market, unit_count, hit=True, payout_amount=stake * 2, message="Don't pass wins on the seven out.", outcome_key="dont_pass_seven")
                elif total == point_before:
                    _resolve_market(market, unit_count, hit=False, payout_amount=0, message=f"Don't pass loses when {point_before} repeats.", outcome_key="dont_pass_point")
            continue
        if kind == "pass_odds":
            if phase_before == "point" and point_before > 0:
                if total == point_before:
                    profit = _casino_craps_odds_profit(point_before, stake, lay=False)
                    _resolve_market(market, unit_count, hit=True, payout_amount=stake + profit, message="Pass odds cash at true odds.", outcome_key="pass_point_odds")
                elif total == 7:
                    _resolve_market(market, unit_count, hit=False, payout_amount=0, message="Pass odds fall with the seven out.", outcome_key="seven_out_odds")
            continue
        if kind == "dont_pass_odds":
            if phase_before == "point" and point_before > 0:
                if total == 7:
                    profit = _casino_craps_odds_profit(point_before, stake, lay=True)
                    _resolve_market(market, unit_count, hit=True, payout_amount=stake + profit, message="Lay odds cash at true odds.", outcome_key="dont_pass_seven_odds")
                elif total == point_before:
                    _resolve_market(market, unit_count, hit=False, payout_amount=0, message="Lay odds lose when the point repeats.", outcome_key="dont_pass_point_odds")
            continue
        if kind == "place":
            if total == int(value):
                profit = _casino_craps_place_profit(int(value), stake)
                _resolve_market(market, unit_count, hit=True, payout_amount=stake + profit, message=f"Place {value} hits before seven.", outcome_key=f"place_{value}_hit")
            elif total == 7:
                _resolve_market(market, unit_count, hit=False, payout_amount=0, message=f"Seven sweeps place {value}.", outcome_key="place_seven_out")
            continue
        if kind == "hardway":
            target = int(value)
            target_face = target // 2
            if total == 7:
                _resolve_market(market, unit_count, hit=False, payout_amount=0, message=f"Seven kills hard {target}.", outcome_key="hardway_seven_out")
            elif total == target and die_one == target_face and die_two == target_face:
                gross_mult = 10 if target in {6, 8} else 8
                _resolve_market(market, unit_count, hit=True, payout_amount=stake * gross_mult, message=f"Hard {target} lands clean.", outcome_key=f"hard_{target}_hit")
            elif total == target:
                _resolve_market(market, unit_count, hit=False, payout_amount=0, message=f"Easy {target} breaks the hardway.", outcome_key=f"easy_{target}")

    remaining_bets = {
        key: int(units)
        for key, units in bets.items()
        if int(units or 0) > 0 and key not in resolved_keys
    }
    current["bets"] = remaining_bets
    current["phase"] = phase_after
    current["point_number"] = int(point_after)
    current["stake"] = int(sum(int(units) for units in remaining_bets.values()) * int(current.get("wager", 0)))

    if phase_before == "come_out" and phase_after == "point":
        headline = f"Point {point_after} is live."
        detail = f"The come-out settles on {point_after}, so the table moves into the point cycle."
        outcome_key = "point_on"
    elif phase_before == "point" and total == 7:
        headline = "Seven out."
        detail = "The shooter sevens out and the table clears back to the come-out."
        outcome_key = "seven_out"
    elif phase_before == "point" and point_before > 0 and total == point_before:
        headline = f"Point {point_before} made."
        detail = "The point comes back before seven and the table resets for a fresh come-out."
        outcome_key = "point_made"
    elif total in {7, 11} and phase_before == "come_out":
        headline = "Natural."
        detail = "The shooter opens with a natural and the table pays the line side."
        outcome_key = "natural"
    elif total in {2, 3, 12} and phase_before == "come_out":
        headline = "Craps on the come-out."
        detail = "The shooter throws craps before a point can settle in."
        outcome_key = "come_out_craps"
    else:
        headline = f"Roll {total}."
        detail = "The dice keep moving and the working bets stay on the felt."
        outcome_key = "table_roll"
    if messages:
        detail = " ".join(messages[:3])

    active_slip = []
    for key, units in sorted(remaining_bets.items()):
        market = _casino_craps_market_from_key(key)
        if not market:
            continue
        active_slip.append({
            "key": market["key"],
            "label": market["label"],
            "units": int(units),
            "stake": int(int(units) * int(current.get("wager", 0))),
        })

    result_lines = []
    result_lines.extend(_casino_ascii_roll_block("Roll", roll))
    result_lines.extend([
        f"Phase: {'Point' if phase_after == 'point' else 'Come-out'}",
        f"Point: {point_after if point_after > 0 else '--'}",
    ])
    for message in messages:
        if message:
            result_lines.append(message)
    if active_slip:
        result_lines.append(
            "Still working: "
            + ", ".join(f"{row['label']} x{row['units']}" for row in active_slip[:6])
            + ("." if len(active_slip) <= 6 else " ...")
        )
    else:
        result_lines.append("Still working: no active chips on the felt.")
    if payout > 0:
        result_lines.append(f"Payout returned: {_credit_amount_label(payout)}.")
    elif resolved_stake > 0:
        result_lines.append("Payout returned: no credits on this roll.")
    else:
        result_lines.append("Payout returned: no settled chips on this roll.")

    round_result = {
        "service": "craps",
        "wager": int(current.get("wager", 0)),
        "stake": int(resolved_stake),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": detail,
        "summary": f"{headline} {_casino_craps_roll_text(roll)}",
        "result_lines": result_lines,
        "phase": str(phase_after),
        "point_number": int(point_after),
        "roll_history": tuple(dict(entry) for entry in current.get("roll_history", ()) or ()),
        "bet_slip": tuple(active_slip),
        "bet_outcomes": tuple(bet_outcomes),
        "come_out_total": int(current["roll_history"][0]["total"]) if current.get("roll_history") else int(total),
        "roll_totals": tuple(int(entry.get("total", 0)) for entry in current.get("roll_history", ()) or ()),
        "roll_pairs": tuple(
            (int(entry.get("die_one", 0)), int(entry.get("die_two", 0)))
            for entry in current.get("roll_history", ()) or ()
        ),
        "social_gain": _casino_social_gain("craps", f"{current['seed_token']}:{current['roll_index']}:{outcome_key}:{len(bet_outcomes)}"),
        "stake_already_paid": True,
    }
    return current, round_result


def _casino_three_bright_color_words(context=None):
    colors = []
    if isinstance(context, dict):
        for color in _casino_color_words_from_hint(context.get("accent_colors")):
            if color not in colors:
                colors.append(color)
    for color in CASINO_THREE_BRIGHT_DEFAULT_COLORS:
        if color not in colors:
            colors.append(color)
    return tuple(colors[:6])


def _casino_three_bright_rainbow_targets(colors):
    colors = tuple(str(color) for color in tuple(colors or ()) if str(color).strip())
    preferred = tuple(color for color in ("red", "green", "blue") if color in colors)
    if len(preferred) == 3:
        return preferred
    return tuple(colors[:3])


def _casino_three_bright_market_order(context=None):
    colors = _casino_three_bright_color_words(context)
    order = []
    for color in colors:
        order.extend((f"single:{color}", f"double:{color}", f"triple:{color}"))
    order.extend(("special:rainbow", "special:all_bright", "special:all_dark"))
    return tuple(order)


def _casino_three_bright_bet_label(bet_kind, bet_value=None, context=None):
    kind = str(bet_kind or "").strip().lower()
    value = _casino_color_word(bet_value)
    if kind == "single" and value:
        return f"Single {value}"
    if kind == "double" and value:
        return f"Double {value}"
    if kind == "triple" and value:
        return f"Triple {value}"
    if kind == "special":
        special = str(bet_value or "").strip().lower()
        if special == "rainbow":
            targets = _casino_three_bright_rainbow_targets(_casino_three_bright_color_words(context))
            return "Rainbow trio " + "/".join(targets)
        if special == "all_bright":
            return "All bright"
        if special == "all_dark":
            return "All dark"
    return str(bet_value or bet_kind or "market").replace("_", " ").title()


def _casino_three_bright_market_from_key(market_key, context=None):
    key = str(market_key or "").strip().lower()
    if not key:
        return None
    kind, _sep, raw_value = key.partition(":")
    colors = set(_casino_three_bright_color_words(context))
    if kind in {"single", "double", "triple"}:
        value = _casino_color_word(raw_value)
        if not value or value not in colors:
            return None
        normalized_key = f"{kind}:{value}"
        return {
            "key": normalized_key,
            "kind": kind,
            "value": value,
            "label": _casino_three_bright_bet_label(kind, value, context=context),
        }
    if kind == "special":
        value = str(raw_value or "").strip().lower()
        if value not in {"rainbow", "all_bright", "all_dark"}:
            return None
        normalized_key = f"special:{value}"
        return {
            "key": normalized_key,
            "kind": "special",
            "value": value,
            "label": _casino_three_bright_bet_label("special", value, context=context),
        }
    return None


def _casino_three_bright_normalize_session(session):
    if not isinstance(session, dict):
        return None
    context = session.get("table_context") if isinstance(session.get("table_context"), dict) else {}
    normalized_context = dict(context)
    if not normalized_context.get("game"):
        normalized_context["game"] = "three_bright"
    colors = _casino_three_bright_color_words(normalized_context)
    bets = {}
    for key, units in dict(session.get("bets", {}) or {}).items():
        market = _casino_three_bright_market_from_key(key, normalized_context)
        if not market:
            continue
        try:
            unit_count = max(0, int(units))
        except (TypeError, ValueError):
            unit_count = 0
        if unit_count > 0:
            bets[market["key"]] = unit_count
    cursor_key = str(session.get("cursor_key", "") or "").strip().lower()
    if not _casino_three_bright_market_from_key(cursor_key, normalized_context):
        cursor_key = _casino_three_bright_market_order(normalized_context)[0]
    wager = max(0, int(session.get("wager", 0) or 0))
    return {
        "service": "three_bright",
        "seed_token": str(session.get("seed_token", "")).strip(),
        "wager": int(wager),
        "stake": int(sum(int(units) for units in bets.values()) * wager),
        "bets": bets,
        "cursor_key": cursor_key,
        "roll_index": int(session.get("roll_index", 0) or 0),
        "dice_colors": tuple(_casino_color_word(color) or str(color) for color in tuple(session.get("dice_colors", ()) or ())[:3]),
        "table_context": normalized_context,
        "color_words": colors,
        "property_id": session.get("property_id"),
        "property_name": str(session.get("property_name", "")).strip(),
    }


def _casino_three_bright_start(seed_token, wager, table_context=None):
    context = dict(table_context) if isinstance(table_context, dict) else {}
    context["game"] = "three_bright"
    color_words = _casino_three_bright_color_words(context)
    return {
        "service": "three_bright",
        "seed_token": str(seed_token),
        "wager": int(wager),
        "stake": 0,
        "bets": {},
        "cursor_key": _casino_three_bright_market_order(context)[0],
        "roll_index": 0,
        "dice_colors": (),
        "table_context": context,
        "color_words": color_words,
    }


def _casino_three_bright_stage_bet(session, market_key):
    current = _casino_three_bright_normalize_session(session)
    if not current:
        return None
    market = _casino_three_bright_market_from_key(market_key, current.get("table_context"))
    if not market:
        return None
    bets = dict(current.get("bets", {}) or {})
    bets[market["key"]] = int(bets.get(market["key"], 0) or 0) + 1
    current["bets"] = bets
    current["cursor_key"] = market["key"]
    current["stake"] = int(sum(int(units) for units in bets.values()) * int(current.get("wager", 0)))
    return current


def _casino_three_bright_remove_bet(session, market_key):
    current = _casino_three_bright_normalize_session(session)
    if not current:
        return None
    market = _casino_three_bright_market_from_key(market_key, current.get("table_context"))
    if not market:
        return None
    bets = dict(current.get("bets", {}) or {})
    units = int(bets.get(market["key"], 0) or 0)
    if units <= 1:
        bets.pop(market["key"], None)
    else:
        bets[market["key"]] = units - 1
    current["bets"] = bets
    current["cursor_key"] = market["key"]
    current["stake"] = int(sum(int(raw_units) for raw_units in bets.values()) * int(current.get("wager", 0)))
    return current


def _casino_three_bright_resolve(session):
    current = _casino_three_bright_normalize_session(session)
    if not current:
        return None
    bets = dict(current.get("bets", {}) or {})
    if not bets:
        return None
    context = dict(current.get("table_context", {}) or {})
    colors = _casino_three_bright_color_words(context)
    roll_rng = random.Random(f"{current['seed_token']}:three_bright:{int(current.get('roll_index', 0))}")
    dice_colors = tuple(roll_rng.choice(colors) for _idx in range(3))
    counts = Counter(dice_colors)
    current["roll_index"] = int(current.get("roll_index", 0)) + 1
    current["dice_colors"] = dice_colors

    payout = 0
    resolved_stake = 0
    messages = []
    bet_outcomes = []
    rainbow_targets = set(_casino_three_bright_rainbow_targets(colors))
    bright_set = CASINO_THREE_BRIGHT_BRIGHT_COLORS
    dark_set = CASINO_THREE_BRIGHT_DARK_COLORS

    for key, units in sorted(bets.items()):
        market = _casino_three_bright_market_from_key(key, context)
        if not market:
            continue
        unit_count = max(0, int(units))
        if unit_count <= 0:
            continue
        stake = int(unit_count * int(current.get("wager", 0)))
        resolved_stake += stake
        kind = market["kind"]
        value = market["value"]
        hit = False
        gross_multiplier = 0
        if kind == "single":
            match_count = int(counts.get(value, 0))
            hit = match_count > 0
            gross_multiplier = match_count
        elif kind == "double":
            hit = int(counts.get(value, 0)) >= 2
            gross_multiplier = 9 if hit else 0
        elif kind == "triple":
            hit = int(counts.get(value, 0)) == 3
            gross_multiplier = 150 if hit else 0
        elif kind == "special" and value == "rainbow":
            hit = len(rainbow_targets) == 3 and set(dice_colors) == rainbow_targets
            gross_multiplier = 24 if hit else 0
        elif kind == "special" and value == "all_bright":
            hit = all(color in bright_set for color in dice_colors)
            gross_multiplier = 6 if hit else 0
        elif kind == "special" and value == "all_dark":
            hit = all(color in dark_set for color in dice_colors)
            gross_multiplier = 6 if hit else 0
        market_payout = int(stake * gross_multiplier)
        payout += max(0, market_payout)
        if hit:
            messages.append(f"{market['label']} catches.")
        else:
            messages.append(f"{market['label']} misses.")
        bet_outcomes.append({
            "key": market["key"],
            "label": market["label"],
            "units": int(unit_count),
            "stake": int(stake),
            "hit": bool(hit),
            "payout": int(max(0, market_payout)),
            "profit": int(max(0, market_payout) - stake),
            "outcome_key": f"{kind}_{value}_{'hit' if hit else 'miss'}",
        })

    if payout > resolved_stake:
        headline = "The color dice pay."
        outcome_key = "win"
    elif payout == resolved_stake and payout > 0:
        headline = "The table pushes back."
        outcome_key = "push"
    else:
        headline = "The colors run cold."
        outcome_key = "lose"
    dice_text = ", ".join(str(color).replace("_", " ") for color in dice_colors)
    result_lines = [
        str(context.get("table_read", "Table read: color dice.")).strip() or "Table read: color dice.",
        f"Dice: {dice_text}.",
    ]
    result_lines.extend(messages[:10])
    if len(messages) > 10:
        result_lines.append(f"...and {len(messages) - 10} more slip rows settle.")
    result_lines.append(f"Payout returned: {_credit_amount_label(payout)}." if payout > 0 else "Payout returned: no credits.")
    return {
        "service": "three_bright",
        "wager": int(current.get("wager", 0)),
        "stake": int(resolved_stake),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": "Three colored dice tumble across the rail and every posted color market resolves at once.",
        "summary": f"Three Bright rolls {dice_text}. {headline}",
        "result_lines": result_lines,
        "dice_colors": dice_colors,
        "color_words": colors,
        "bet_slip": tuple({
            "key": key,
            "label": (_casino_three_bright_market_from_key(key, context) or {"label": key})["label"],
            "units": int(units),
            "stake": int(int(units) * int(current.get("wager", 0))),
        } for key, units in sorted(bets.items())),
        "bet_outcomes": tuple(bet_outcomes),
        "table_context": _casino_table_context_summary(context),
        "table_context_summary": _casino_table_context_summary(context),
        "social_gain": _casino_social_gain("three_bright", f"{current['seed_token']}:{current['roll_index']}:{outcome_key}:{len(bet_outcomes)}"),
        "stake_already_paid": True,
    }


def _casino_three_bones_market_order(_context=None):
    return tuple([
        "small",
        "big",
        *(f"exact:{total}" for total in range(4, 18)),
        *(f"double:{face}" for face in range(1, 7)),
        *(f"triple:{face}" for face in range(1, 7)),
        "any_triple",
    ])


def _casino_three_bones_bet_label(bet_kind, bet_value=None):
    kind = str(bet_kind or "").strip().lower()
    if kind == "small":
        return "Small 4-10"
    if kind == "big":
        return "Big 11-17"
    if kind == "exact":
        return f"Total {int(bet_value)}"
    if kind == "double":
        return f"Double {int(bet_value)}"
    if kind == "triple":
        return f"Triple {int(bet_value)}"
    if kind == "any_triple":
        return "Any triple"
    return str(bet_value or bet_kind or "market").replace("_", " ").title()


def _casino_three_bones_market_from_key(market_key, _context=None):
    key = str(market_key or "").strip().lower()
    if key in {"small", "big", "any_triple"}:
        return {
            "key": key,
            "kind": key,
            "value": None,
            "label": _casino_three_bones_bet_label(key),
        }
    kind, _sep, raw_value = key.partition(":")
    if kind == "exact":
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None
        if value < 4 or value > 17:
            return None
        return {
            "key": f"exact:{value}",
            "kind": "exact",
            "value": int(value),
            "label": _casino_three_bones_bet_label("exact", value),
        }
    if kind in {"double", "triple"}:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None
        if value < 1 or value > 6:
            return None
        return {
            "key": f"{kind}:{value}",
            "kind": kind,
            "value": int(value),
            "label": _casino_three_bones_bet_label(kind, value),
        }
    return None


def _casino_three_bones_normalize_session(session):
    if not isinstance(session, dict):
        return None
    context = session.get("table_context") if isinstance(session.get("table_context"), dict) else {}
    normalized_context = dict(context)
    if not normalized_context.get("game"):
        normalized_context["game"] = "three_bones"
    bets = {}
    for key, units in dict(session.get("bets", {}) or {}).items():
        market = _casino_three_bones_market_from_key(key, normalized_context)
        if not market:
            continue
        try:
            unit_count = max(0, int(units))
        except (TypeError, ValueError):
            unit_count = 0
        if unit_count > 0:
            bets[market["key"]] = unit_count
    cursor_key = str(session.get("cursor_key", "") or "").strip().lower()
    if not _casino_three_bones_market_from_key(cursor_key, normalized_context):
        cursor_key = "small"
    wager = max(0, int(session.get("wager", 0) or 0))
    dice = tuple(max(1, min(6, int(value))) for value in tuple(session.get("dice", ()) or ())[:3] if str(value).strip())
    return {
        "service": "three_bones",
        "seed_token": str(session.get("seed_token", "")).strip(),
        "wager": int(wager),
        "stake": int(sum(int(units) for units in bets.values()) * wager),
        "bets": bets,
        "cursor_key": cursor_key,
        "roll_index": int(session.get("roll_index", 0) or 0),
        "dice": dice,
        "table_context": normalized_context,
        "property_id": session.get("property_id"),
        "property_name": str(session.get("property_name", "")).strip(),
    }


def _casino_three_bones_start(seed_token, wager, table_context=None):
    context = dict(table_context) if isinstance(table_context, dict) else {}
    context["game"] = "three_bones"
    return {
        "service": "three_bones",
        "seed_token": str(seed_token),
        "wager": int(wager),
        "stake": 0,
        "bets": {},
        "cursor_key": "small",
        "roll_index": 0,
        "dice": (),
        "table_context": context,
    }


def _casino_three_bones_stage_bet(session, market_key):
    current = _casino_three_bones_normalize_session(session)
    if not current:
        return None
    market = _casino_three_bones_market_from_key(market_key, current.get("table_context"))
    if not market:
        return None
    bets = dict(current.get("bets", {}) or {})
    bets[market["key"]] = int(bets.get(market["key"], 0) or 0) + 1
    current["bets"] = bets
    current["cursor_key"] = market["key"]
    current["stake"] = int(sum(int(units) for units in bets.values()) * int(current.get("wager", 0)))
    return current


def _casino_three_bones_remove_bet(session, market_key):
    current = _casino_three_bones_normalize_session(session)
    if not current:
        return None
    market = _casino_three_bones_market_from_key(market_key, current.get("table_context"))
    if not market:
        return None
    bets = dict(current.get("bets", {}) or {})
    units = int(bets.get(market["key"], 0) or 0)
    if units <= 1:
        bets.pop(market["key"], None)
    else:
        bets[market["key"]] = units - 1
    current["bets"] = bets
    current["cursor_key"] = market["key"]
    current["stake"] = int(sum(int(raw_units) for raw_units in bets.values()) * int(current.get("wager", 0)))
    return current


def _casino_three_bones_resolve(session):
    current = _casino_three_bones_normalize_session(session)
    if not current:
        return None
    bets = dict(current.get("bets", {}) or {})
    if not bets:
        return None
    context = dict(current.get("table_context", {}) or {})
    roll_rng = random.Random(f"{current['seed_token']}:three_bones:{int(current.get('roll_index', 0))}")
    dice = tuple(roll_rng.randint(1, 6) for _idx in range(3))
    counts = Counter(dice)
    total = int(sum(dice))
    is_triple = any(count >= 3 for count in counts.values())
    current["roll_index"] = int(current.get("roll_index", 0)) + 1
    current["dice"] = dice

    payout = 0
    resolved_stake = 0
    messages = []
    bet_outcomes = []
    for key, units in sorted(bets.items()):
        market = _casino_three_bones_market_from_key(key, context)
        if not market:
            continue
        unit_count = max(0, int(units))
        if unit_count <= 0:
            continue
        stake = int(unit_count * int(current.get("wager", 0)))
        resolved_stake += stake
        kind = market["kind"]
        value = market["value"]
        hit = False
        gross_multiplier = 0
        if kind == "small":
            hit = (4 <= total <= 10) and not is_triple
            gross_multiplier = 2 if hit else 0
        elif kind == "big":
            hit = (11 <= total <= 17) and not is_triple
            gross_multiplier = 2 if hit else 0
        elif kind == "exact":
            hit = total == int(value)
            gross_multiplier = int(CASINO_THREE_BONES_EXACT_TOTAL_GROSS_MULTIPLIERS.get(int(value), 0)) if hit else 0
        elif kind == "double":
            hit = int(counts.get(int(value), 0)) >= 2
            gross_multiplier = 12 if hit else 0
        elif kind == "triple":
            hit = int(counts.get(int(value), 0)) == 3
            gross_multiplier = 181 if hit else 0
        elif kind == "any_triple":
            hit = bool(is_triple)
            gross_multiplier = 31 if hit else 0
        market_payout = int(stake * gross_multiplier)
        payout += max(0, market_payout)
        messages.append(f"{market['label']} {'hits' if hit else 'misses'}.")
        bet_outcomes.append({
            "key": market["key"],
            "label": market["label"],
            "units": int(unit_count),
            "stake": int(stake),
            "hit": bool(hit),
            "payout": int(max(0, market_payout)),
            "profit": int(max(0, market_payout) - stake),
            "outcome_key": f"{kind}_{value if value is not None else 'table'}_{'hit' if hit else 'miss'}",
        })

    if payout > resolved_stake:
        headline = "The bones pay."
        outcome_key = "win"
    elif payout == resolved_stake and payout > 0:
        headline = "The cup gives it back."
        outcome_key = "push"
    else:
        headline = "The bones go quiet."
        outcome_key = "lose"
    dice_text = "-".join(str(value) for value in dice)
    result_lines = [
        str(context.get("table_read", "Table read: public dice table.")).strip() or "Table read: public dice table.",
        f"Dice: {dice_text} (total {total}).",
    ]
    result_lines.extend(messages[:10])
    if len(messages) > 10:
        result_lines.append(f"...and {len(messages) - 10} more slip rows settle.")
    result_lines.append(f"Payout returned: {_credit_amount_label(payout)}." if payout > 0 else "Payout returned: no credits.")
    return {
        "service": "three_bones",
        "wager": int(current.get("wager", 0)),
        "stake": int(resolved_stake),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": "The cup lifts and three dice settle the whole slip.",
        "summary": f"Three Bones rolls {dice_text} for {total}. {headline}",
        "result_lines": result_lines,
        "dice": dice,
        "dice_total": int(total),
        "is_triple": bool(is_triple),
        "bet_slip": tuple({
            "key": key,
            "label": (_casino_three_bones_market_from_key(key, context) or {"label": key})["label"],
            "units": int(units),
            "stake": int(int(units) * int(current.get("wager", 0))),
        } for key, units in sorted(bets.items())),
        "bet_outcomes": tuple(bet_outcomes),
        "table_context": _casino_table_context_summary(context),
        "table_context_summary": _casino_table_context_summary(context),
        "social_gain": _casino_social_gain("three_bones", f"{current['seed_token']}:{current['roll_index']}:{outcome_key}:{len(bet_outcomes)}"),
        "stake_already_paid": True,
    }


def _casino_bloom_card_hue_from_row(row):
    genetics = row.get("genetics") if isinstance(row, dict) else {}
    hue = str((genetics or {}).get("hue_family", "") or "").strip().lower()
    if hue:
        return hue
    colors = row.get("colors") if isinstance(row, dict) else ()
    for color in tuple(colors or ()):
        text = str(color or "").strip().lower()
        for prefix in ("flora_flower_", "flora_"):
            if text.startswith(prefix):
                return text[len(prefix):]
        if text:
            return text
    return "green"


def _casino_bloom_card_from_catalog_row(plant_id, row):
    if not isinstance(row, dict):
        row = {}
    plant_id = str(plant_id or "").strip().lower()
    name = str(row.get("name", plant_id.replace("_", " "))).strip() or plant_id.replace("_", " ")
    growth_form = str(row.get("growth_form", "flower") or "flower").strip().lower() or "flower"
    rarity = str(row.get("rarity", "common") or "common").strip().lower() or "common"
    return {
        "plant_id": plant_id,
        "name": name,
        "family": growth_form,
        "hue": _casino_bloom_card_hue_from_row(row),
        "rarity": rarity,
        "glyph": str(row.get("glyph", "'") or "'")[:1] or "'",
    }


def _casino_bloom_cards_deck(seed_token):
    catalog = load_flora_catalog()
    cards = []
    for plant_id, row in sorted(catalog.items()):
        if not isinstance(row, dict):
            continue
        cards.append(_casino_bloom_card_from_catalog_row(plant_id, row))
    if not cards:
        fallback = {
            "name": "blush aster",
            "growth_form": "flower",
            "rarity": "common",
            "glyph": "'",
            "genetics": {"hue_family": "pink"},
        }
        cards.append(_casino_bloom_card_from_catalog_row("blush_aster", fallback))
    rng = random.Random(f"{seed_token}:bloom_cards:deck")
    rng.shuffle(cards)
    return cards


def _casino_bloom_card_label(card):
    if not isinstance(card, dict):
        return str(card or "unknown bloom").strip() or "unknown bloom"
    name = str(card.get("name", "") or "").strip()
    if name:
        return name
    plant_id = str(card.get("plant_id", "") or "").strip()
    return plant_id.replace("_", " ") if plant_id else "unknown bloom"


def _casino_bloom_cards_normalize_session(session):
    if not isinstance(session, dict):
        return None
    context = session.get("table_context") if isinstance(session.get("table_context"), dict) else {}
    normalized_context = dict(context)
    if not normalized_context.get("game"):
        normalized_context["game"] = "bloom_cards"
    deck = [dict(card) for card in list(session.get("deck", ()) or ()) if isinstance(card, dict)]
    player_cards = [dict(card) for card in list(session.get("player_cards", session.get("garden_cards", ())) or ()) if isinstance(card, dict)]
    house_cards = [dict(card) for card in list(session.get("house_cards", ()) or ())[:2] if isinstance(card, dict)]
    return {
        "service": "bloom_cards",
        "seed_token": str(session.get("seed_token", "")).strip(),
        "wager": int(session.get("wager", 0)),
        "stake": int(session.get("stake", session.get("wager", 0))),
        "deck": deck,
        "deck_index": int(session.get("deck_index", 0) or 0),
        "player_cards": player_cards,
        "garden_cards": player_cards,
        "house_cards": house_cards,
        "growth_steps": max(0, int(session.get("growth_steps", 0) or 0)),
        "withered": bool(session.get("withered", False)),
        "table_context": normalized_context,
        "property_id": session.get("property_id"),
        "property_name": str(session.get("property_name", "")).strip(),
    }


def _casino_bloom_cards_score(cards, growth_steps=0):
    cards = [dict(card) for card in list(cards or ()) if isinstance(card, dict)]
    family_counts = Counter(str(card.get("family", "flower")) for card in cards)
    hue_counts = Counter(str(card.get("hue", "green")) for card in cards)
    rarity_counts = Counter(str(card.get("rarity", "common")) for card in cards)
    points = 1.0
    reasons = []
    for family, count in sorted(family_counts.items()):
        if count >= 2:
            bonus = 0.45 * (count - 1)
            points += bonus
            reasons.append(f"{count} {family} cards")
    for hue, count in sorted(hue_counts.items()):
        if count >= 2:
            bonus = 0.30 * (count - 1)
            points += bonus
            reasons.append(f"{count} {hue} hues")
    if rarity_counts.get("uncommon", 0):
        points += 0.12 * int(rarity_counts["uncommon"])
    if rarity_counts.get("rare", 0):
        points += 0.32 * int(rarity_counts["rare"])
        reasons.append("rare bloom")
    families = set(family_counts)
    if {"flower", "vine"} <= families:
        points += 0.35
        reasons.append("garland match")
    if families.intersection({"moss", "lichen"}) and families.intersection({"shrub", "fern"}):
        points += 0.25
        reasons.append("ground cover")
    growth_steps = max(0, int(growth_steps))
    if growth_steps <= 0:
        multiplier = 1.0
        growth_base = 1.0
        growth_cap = 1.0
        combo_bonus = 0.0
    else:
        tier_index = min(growth_steps, CASINO_BLOOM_CARD_MAX_GROW_STEPS) - 1
        growth_base = float(CASINO_BLOOM_CARD_GROWTH_BASE_MULTIPLIERS[tier_index])
        growth_cap = float(CASINO_BLOOM_CARD_GROWTH_MAX_MULTIPLIERS[tier_index])
        combo_bonus = max(0.0, float(points) - 1.0) * CASINO_BLOOM_CARD_COMBO_POINT_VALUE
        multiplier = round(max(1.0, min(growth_cap, growth_base + combo_bonus)), 2)
    if not reasons:
        reasons.append("ordinary garden")
    return {
        "multiplier": float(multiplier),
        "points": round(float(points), 2),
        "growth_base_multiplier": float(growth_base),
        "growth_cap_multiplier": float(growth_cap),
        "combo_bonus": round(float(combo_bonus), 3),
        "reasons": tuple(reasons[:4]),
        "family_counts": dict(family_counts),
        "hue_counts": dict(hue_counts),
        "rarity_counts": dict(rarity_counts),
    }


def _casino_bloom_cards_start(seed_token, wager, table_context=None):
    context = dict(table_context) if isinstance(table_context, dict) else {}
    context["game"] = "bloom_cards"
    deck = _casino_bloom_cards_deck(seed_token)
    house_cards = list(deck[:2])
    player_cards = list(deck[2:2 + CASINO_BLOOM_CARD_STARTING_HAND_SIZE])
    deck_index = 2 + len(player_cards)
    return {
        "service": "bloom_cards",
        "seed_token": str(seed_token),
        "wager": int(wager),
        "stake": int(wager),
        "deck": list(deck),
        "deck_index": int(deck_index),
        "player_cards": player_cards,
        "garden_cards": player_cards,
        "house_cards": house_cards,
        "growth_steps": 0,
        "withered": False,
        "table_context": context,
    }


def _casino_bloom_cards_wither_chance(current, next_card):
    player_cards = list(current.get("player_cards", ()) or ())
    house_cards = list(current.get("house_cards", ()) or ())
    growth_steps = max(0, int(current.get("growth_steps", 0) or 0))
    family_counts = Counter(str(card.get("family", "")) for card in player_cards if isinstance(card, dict))
    hue_counts = Counter(str(card.get("hue", "")) for card in player_cards if isinstance(card, dict))
    house_families = {str(card.get("family", "")) for card in house_cards if isinstance(card, dict)}
    house_hues = {str(card.get("hue", "")) for card in house_cards if isinstance(card, dict)}
    family = str(next_card.get("family", "")) if isinstance(next_card, dict) else ""
    hue = str(next_card.get("hue", "")) if isinstance(next_card, dict) else ""
    chance = 0.08 + (0.08 * growth_steps)
    if family and family_counts.get(family, 0) > 0:
        chance -= 0.04
    if hue and hue_counts.get(hue, 0) > 0:
        chance -= 0.03
    if family and family in house_families:
        chance += 0.07
    if hue and hue in house_hues:
        chance += 0.05
    if str(next_card.get("rarity", "")) == "rare":
        chance += 0.02
    return max(0.04, min(0.36, float(chance)))


def _casino_bloom_cards_cashout(session):
    current = _casino_bloom_cards_normalize_session(session)
    if not current:
        return None
    score = _casino_bloom_cards_score(current.get("player_cards", ()), current.get("growth_steps", 0))
    multiplier = float(score.get("multiplier", 1.0))
    payout = int(round(int(current.get("wager", 0)) * multiplier))
    growth_steps = max(0, int(current.get("growth_steps", 0) or 0))
    headline = "You press the blooms." if payout > int(current.get("stake", 0)) else "You keep the stake alive."
    if growth_steps <= 0:
        headline = "You take the safe push."
    result_lines = [
        str(current.get("table_context", {}).get("table_read", "Table read: flower-card garden.")).strip() or "Table read: flower-card garden.",
        "Garden: " + ", ".join(_casino_bloom_card_label(card) for card in current.get("player_cards", ())[:8]),
        "House weather: " + ", ".join(_casino_bloom_card_label(card) for card in current.get("house_cards", ())[:2]),
        "Bloom read: " + ", ".join(score.get("reasons", ()) or ("ordinary garden",)),
        f"Cash-out multiplier: x{multiplier:.2f}.",
        f"Payout returned: {_credit_amount_label(payout)}.",
    ]
    return {
        "service": "bloom_cards",
        "wager": int(current.get("wager", 0)),
        "stake": int(current.get("stake", current.get("wager", 0))),
        "payout": int(max(0, payout)),
        "outcome_key": "cashout",
        "headline": headline,
        "detail": "You stop before the garden withers and the dealer counts out the bloom-card return.",
        "summary": f"Bloom Cards cashes at x{multiplier:.2f}.",
        "result_lines": result_lines,
        "player_cards": tuple(dict(card) for card in current.get("player_cards", ()) or ()),
        "garden_cards": tuple(dict(card) for card in current.get("player_cards", ()) or ()),
        "house_cards": tuple(dict(card) for card in current.get("house_cards", ()) or ()),
        "growth_steps": int(growth_steps),
        "cashout_multiplier": float(multiplier),
        "score_reasons": tuple(score.get("reasons", ()) or ()),
        "table_context": _casino_table_context_summary(current.get("table_context")),
        "table_context_summary": _casino_table_context_summary(current.get("table_context")),
        "social_gain": _casino_social_gain("bloom_cards", f"{current['seed_token']}:{growth_steps}:cashout:{multiplier:.2f}"),
        "stake_already_paid": True,
    }


def _casino_bloom_cards_grow(session):
    current = _casino_bloom_cards_normalize_session(session)
    if not current:
        return None, None
    growth_steps = max(0, int(current.get("growth_steps", 0) or 0))
    if growth_steps >= CASINO_BLOOM_CARD_MAX_GROW_STEPS:
        return current, _casino_bloom_cards_cashout(current)
    deck = list(current.get("deck", ()) or ())
    deck_index = max(0, int(current.get("deck_index", 0) or 0))
    if deck_index >= len(deck):
        return current, _casino_bloom_cards_cashout(current)
    next_card = dict(deck[deck_index])
    chance = _casino_bloom_cards_wither_chance(current, next_card)
    risk_rng = random.Random(f"{current['seed_token']}:bloom_cards:wither:{growth_steps}:{next_card.get('plant_id', deck_index)}")
    if risk_rng.random() < chance:
        current["withered"] = True
        result_lines = [
            str(current.get("table_context", {}).get("table_read", "Table read: flower-card garden.")).strip() or "Table read: flower-card garden.",
            f"Next card: {_casino_bloom_card_label(next_card)}.",
            "The garden withers before the new bloom takes.",
            "Payout returned: no credits.",
        ]
        return None, {
            "service": "bloom_cards",
            "wager": int(current.get("wager", 0)),
            "stake": int(current.get("stake", current.get("wager", 0))),
            "payout": 0,
            "outcome_key": "wither",
            "headline": "The garden withers.",
            "detail": "You let the cards grow one step too far and the house takes the posted stake.",
            "summary": f"Bloom Cards withers on {_casino_bloom_card_label(next_card)}.",
            "result_lines": result_lines,
            "player_cards": tuple(dict(card) for card in current.get("player_cards", ()) or ()),
            "garden_cards": tuple(dict(card) for card in current.get("player_cards", ()) or ()),
            "house_cards": tuple(dict(card) for card in current.get("house_cards", ()) or ()),
            "drawn_card": dict(next_card),
            "growth_steps": int(growth_steps),
            "wither_chance": float(chance),
            "table_context": _casino_table_context_summary(current.get("table_context")),
            "table_context_summary": _casino_table_context_summary(current.get("table_context")),
            "social_gain": 0,
            "stake_already_paid": True,
        }
    player_cards = list(current.get("player_cards", ()) or ())
    player_cards.append(next_card)
    current["player_cards"] = player_cards
    current["garden_cards"] = player_cards
    current["deck_index"] = int(deck_index + 1)
    current["growth_steps"] = int(growth_steps + 1)
    current["withered"] = False
    return current, None


def _casino_baccarat_normalize_session(session):
    if not isinstance(session, dict):
        return None
    player_cards = [
        str(card).strip().upper()
        for card in list(session.get("player_cards", ()) or ())[:3]
        if str(card).strip()
    ]
    banker_cards = [
        str(card).strip().upper()
        for card in list(session.get("banker_cards", ()) or ())[:3]
        if str(card).strip()
    ]
    return {
        "service": "baccarat",
        "seed_token": str(session.get("seed_token", "")).strip(),
        "wager": int(session.get("wager", 0)),
        "stake": int(session.get("stake", session.get("wager", 0))),
        "deck": list(session.get("deck", ()) or ()),
        "deck_index": int(session.get("deck_index", 0)),
        "player_cards": player_cards,
        "banker_cards": banker_cards,
        "property_id": session.get("property_id"),
        "property_name": str(session.get("property_name", "")).strip(),
        "table_context": _casino_preserved_table_context(session),
    }


def _casino_baccarat_start(seed_token, wager):
    deck = _casino_shuffled_deck(seed_token)
    return {
        "service": "baccarat",
        "seed_token": str(seed_token),
        "wager": int(wager),
        "stake": int(wager),
        "deck": list(deck),
        "deck_index": 4,
        "player_cards": [deck[0], deck[2]],
        "banker_cards": [deck[1], deck[3]],
    }


def _casino_baccarat_card_value(card):
    rank = str(card or "??").strip().upper()[:1]
    if rank == "A":
        return 1
    if rank in {"T", "J", "Q", "K"}:
        return 0
    try:
        return int(rank)
    except (TypeError, ValueError):
        return 0


def _casino_baccarat_total(cards):
    return sum(_casino_baccarat_card_value(card) for card in list(cards or ())) % 10


def _casino_baccarat_should_banker_draw(banker_total, player_third_card):
    total = int(banker_total)
    if total <= 2:
        return True
    if total >= 7:
        return False

    player_value = _casino_baccarat_card_value(player_third_card)
    if total == 3:
        return player_value != 8
    if total == 4:
        return 2 <= player_value <= 7
    if total == 5:
        return 4 <= player_value <= 7
    if total == 6:
        return 6 <= player_value <= 7
    return False


def _casino_baccarat_bet_label(bet_side):
    side = str(bet_side or "").strip().lower()
    if side == "banker":
        return "Banker"
    if side == "tie":
        return "Tie"
    return "Player"


def _casino_baccarat_payout(wager, winning_side, bet_side):
    wager = max(0, int(wager))
    winner = str(winning_side or "").strip().lower()
    side = str(bet_side or "").strip().lower()
    if winner != side:
        return 0, 0, ""
    if side == "player":
        return wager * 2, 0, "Player pays even money."
    if side == "banker":
        commission = max(0, int(round(float(wager) * 0.05)))
        return max(0, (wager * 2) - commission), commission, "Banker pays even money minus the 5% commission."
    if side == "tie":
        return wager * 9, 0, "Tie pays 8 to 1 plus the posted wager back."
    return 0, 0, ""


def _casino_baccarat_resolve(session, bet_side):
    current = _casino_baccarat_normalize_session(session)
    if not current:
        return None

    side = str(bet_side or "").strip().lower()
    if side not in {"player", "banker", "tie"}:
        return None

    deck = list(current.get("deck", ()) or ())
    deck_index = int(current.get("deck_index", 0))
    player_cards = list(current.get("player_cards", ()) or ())
    banker_cards = list(current.get("banker_cards", ()) or ())
    if len(player_cards) < 2 or len(banker_cards) < 2:
        return None

    player_total = _casino_baccarat_total(player_cards)
    banker_total = _casino_baccarat_total(banker_cards)
    player_natural = player_total >= 8
    banker_natural = banker_total >= 8
    player_third_card = ""
    banker_third_card = ""

    if not player_natural and not banker_natural:
        if player_total <= 5 and deck_index < len(deck):
            player_third_card = str(deck[deck_index]).strip().upper()
            deck_index += 1
            if player_third_card:
                player_cards.append(player_third_card)
                player_total = _casino_baccarat_total(player_cards)

        if player_third_card:
            if _casino_baccarat_should_banker_draw(banker_total, player_third_card) and deck_index < len(deck):
                banker_third_card = str(deck[deck_index]).strip().upper()
                deck_index += 1
                if banker_third_card:
                    banker_cards.append(banker_third_card)
                    banker_total = _casino_baccarat_total(banker_cards)
        elif banker_total <= 5 and deck_index < len(deck):
            banker_third_card = str(deck[deck_index]).strip().upper()
            deck_index += 1
            if banker_third_card:
                banker_cards.append(banker_third_card)
                banker_total = _casino_baccarat_total(banker_cards)

    if player_total > banker_total:
        winning_side = "player"
    elif banker_total > player_total:
        winning_side = "banker"
    else:
        winning_side = "tie"

    payout, commission, payout_line = _casino_baccarat_payout(current.get("wager", 0), winning_side, side)
    bet_label = _casino_baccarat_bet_label(side)
    winner_label = _casino_baccarat_bet_label(winning_side)

    if winning_side == side and side == "banker":
        headline = "Banker hand wins."
        detail = "The banker side edges ahead and the payout clears after commission."
        outcome_key = "banker_win"
    elif winning_side == side and side == "player":
        headline = "Player hand wins."
        detail = "Player finishes with the higher point total and the bet pays even money."
        outcome_key = "player_win"
    elif winning_side == side and side == "tie":
        headline = "Tie hits."
        detail = "Both hands stop on the same point total and the tie bet pays the premium."
        outcome_key = "tie_hit"
    elif winning_side == "tie":
        headline = "Table lands on a tie."
        detail = "The hands deadlock, so the player and banker sides both go down."
        outcome_key = "tie"
    else:
        headline = "Wrong side."
        detail = f"The {winner_label.lower()} hand takes the point and the house keeps the wager."
        outcome_key = f"{winning_side}_miss"

    result_lines = []
    result_lines.append("")
    result_lines.extend(_casino_ascii_card_block("Player", player_cards))
    result_lines.extend(_casino_ascii_card_block("Banker", banker_cards))
    result_lines.extend([
        f"Bet: {bet_label}",
        f"Player: {_casino_cards_text(player_cards)} ({player_total})",
        f"Banker: {_casino_cards_text(banker_cards)} ({banker_total})",
        f"Winner: {winner_label}",
        payout_line if payout_line else "Payout: no return on this hand.",
    ])
    if player_natural or banker_natural:
        result_lines.append("Natural hand: the third-card rules never come into play.")
    elif player_third_card or banker_third_card:
        draw_bits = []
        if player_third_card:
            draw_bits.append(f"Player draws {_casino_card_label(player_third_card)}.")
        if banker_third_card:
            draw_bits.append(f"Banker draws {_casino_card_label(banker_third_card)}.")
        result_lines.append(" ".join(draw_bits))
    else:
        result_lines.append("Both hands stand on the opening two cards.")
    if commission > 0:
        result_lines.append(f"Commission: {commission}c comes off the banker win.")
    result_lines.append(detail)

    return {
        "service": "baccarat",
        "wager": int(current["wager"]),
        "stake": int(current["stake"]),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": detail,
        "summary": f"Bet {bet_label}. Player {player_total}, banker {banker_total}. {headline}",
        "result_lines": result_lines,
        "bet_side": side,
        "winning_side": winning_side,
        "player_cards": tuple(player_cards),
        "banker_cards": tuple(banker_cards),
        "player_total": int(player_total),
        "banker_total": int(banker_total),
        "player_natural": bool(player_natural),
        "banker_natural": bool(banker_natural),
        "player_third_card": player_third_card,
        "banker_third_card": banker_third_card,
        "commission": int(commission),
        "social_gain": _casino_social_gain("baccarat", f"{current['seed_token']}:{side}:{winning_side}"),
        "stake_already_paid": True,
    }


def _casino_three_card_straight_high(ranks):
    unique = sorted({int(rank) for rank in list(ranks or ()) if int(rank) > 0})
    if len(unique) != 3:
        return 0
    if unique == [2, 3, 14]:
        return 3
    if unique[0] + 1 == unique[1] and unique[1] + 1 == unique[2]:
        return unique[2]
    return 0


def _casino_three_card_poker_hand_name(score):
    category = int(score[0]) if score else 0
    primary = int(score[1]) if len(score) > 1 else 0
    if category == 5:
        return f"{_casino_rank_name(primary)}-high straight flush"
    if category == 4:
        return f"three {_casino_rank_name(primary)}s"
    if category == 3:
        return f"{_casino_rank_name(primary)}-high straight"
    if category == 2:
        return f"{_casino_rank_name(primary)}-high flush"
    if category == 1:
        return f"pair of {_casino_rank_name(primary)}s"
    return f"{_casino_rank_name(primary)}-high"


def _casino_evaluate_three_card_poker(cards):
    ranks = sorted((_casino_card_rank(card) for card in list(cards or ())), reverse=True)
    suits = [_casino_card_suit(card) for card in list(cards or ())]
    counts = Counter(ranks)
    ordered_counts = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    flush = len(set(suits)) == 1 if suits else False
    straight_high = _casino_three_card_straight_high(ranks)

    if flush and straight_high:
        return (5, straight_high)
    if ordered_counts and ordered_counts[0][1] == 3:
        return (4, ordered_counts[0][0])
    if straight_high:
        return (3, straight_high)
    if flush:
        return tuple([2] + sorted(ranks, reverse=True))
    if ordered_counts and ordered_counts[0][1] == 2:
        pair_rank = ordered_counts[0][0]
        kicker = max(rank for rank in ranks if rank != pair_rank)
        return (1, pair_rank, kicker)
    return tuple([0] + sorted(ranks, reverse=True))


def _casino_three_card_poker_dealer_qualifies(score):
    if not score:
        return False
    category = int(score[0])
    if category >= 1:
        return True
    return int(score[1]) >= 12 if len(score) > 1 else False


def _casino_three_card_poker_ante_bonus_multiplier(score):
    if not score:
        return 0
    return int(CASINO_THREE_CARD_POKER_ANTE_BONUS_MULTIPLIERS.get(int(score[0]), 0))


def _casino_three_card_poker_start(seed_token, wager):
    deck = _casino_shuffled_deck(seed_token)
    return {
        "service": "three_card_poker",
        "seed_token": str(seed_token),
        "wager": int(wager),
        "stake": int(wager),
        "player_cards": [deck[0], deck[2], deck[4]],
        "dealer_cards": [deck[1], deck[3], deck[5]],
    }


def _casino_three_card_poker_normalize_session(session):
    if not isinstance(session, dict):
        return None
    return {
        "service": "three_card_poker",
        "seed_token": str(session.get("seed_token", "")).strip(),
        "wager": int(session.get("wager", 0)),
        "stake": int(session.get("stake", session.get("wager", 0))),
        "player_cards": [
            str(card).strip().upper()
            for card in list(session.get("player_cards", ()) or ())[:3]
            if str(card).strip()
        ],
        "dealer_cards": [
            str(card).strip().upper()
            for card in list(session.get("dealer_cards", ()) or ())[:3]
            if str(card).strip()
        ],
        "property_id": session.get("property_id"),
        "property_name": str(session.get("property_name", "")).strip(),
        "table_context": _casino_preserved_table_context(session),
    }


def _casino_three_card_poker_resolve(session, action):
    current = _casino_three_card_poker_normalize_session(session)
    if not current:
        return None
    action = str(action or "").strip().lower()
    if action not in {"play", "fold"}:
        return None

    wager = int(current.get("wager", 0))
    stake = int(current.get("stake", wager))
    player_cards = list(current.get("player_cards", ()) or ())
    dealer_cards = list(current.get("dealer_cards", ()) or ())
    player_score = _casino_evaluate_three_card_poker(player_cards)
    player_hand_name = _casino_three_card_poker_hand_name(player_score)

    if action == "fold":
        result_lines = []
        result_lines.append("")
        result_lines.extend(_casino_ascii_card_block("You", player_cards))
        return {
            "service": "three_card_poker",
            "wager": int(wager),
            "stake": int(stake),
            "payout": 0,
            "outcome_key": "fold",
            "headline": "You fold the ante.",
            "detail": "The hand looks thin, so you slide the ante away and let the dealer keep it.",
            "summary": f"You fold {_casino_cards_text(player_cards)} ({player_hand_name}) and give up the ante.",
            "result_lines": result_lines + [
                f"Your hand: {_casino_cards_text(player_cards)} ({player_hand_name})",
                "You fold before the dealer turns the hand over.",
            ],
            "player_cards": tuple(player_cards),
            "player_hand_name": str(player_hand_name),
            "social_gain": _casino_social_gain("three_card_poker", f"{current.get('seed_token', '')}:fold"),
            "stake_already_paid": True,
        }

    ante_stake = int(wager)
    play_stake = max(0, int(stake) - int(ante_stake))
    dealer_score = _casino_evaluate_three_card_poker(dealer_cards)
    dealer_hand_name = _casino_three_card_poker_hand_name(dealer_score)
    dealer_qualifies = _casino_three_card_poker_dealer_qualifies(dealer_score)
    ante_bonus_mult = _casino_three_card_poker_ante_bonus_multiplier(player_score)
    ante_bonus = int(max(0, ante_bonus_mult) * ante_stake)

    if not dealer_qualifies:
        outcome_key = "dealer_not_qualify"
        payout = int((ante_stake * 2) + play_stake + ante_bonus)
        headline = "Dealer doesn't qualify."
        detail = "The dealer misses queen-high, so the ante wins and the play wager pushes."
    elif player_score > dealer_score:
        outcome_key = "player_win"
        payout = int((stake * 2) + ante_bonus)
        headline = "You beat the dealer."
        detail = "Your three-card hand outruns the dealer, so both wagers pay even money."
    elif player_score == dealer_score:
        outcome_key = "push"
        payout = int(stake + ante_bonus)
        headline = "Push."
        detail = "The hands tie exactly, so the ante and play both push."
    else:
        outcome_key = "dealer_win"
        payout = int(ante_bonus)
        headline = "Dealer wins."
        detail = "The dealer turns over the better hand and sweeps the main action."

    result_lines = []
    result_lines.extend(_casino_ascii_card_block("You", player_cards))
    result_lines.extend(_casino_ascii_card_block("Dealer", dealer_cards))
    result_lines.extend([
        f"You: {_casino_cards_text(player_cards)} ({player_hand_name})",
        f"Dealer: {_casino_cards_text(dealer_cards)} ({dealer_hand_name})",
        "Dealer qualifies." if dealer_qualifies else "Dealer does not qualify (needs queen-high or better).",
    ])
    if ante_bonus > 0:
        result_lines.append(f"Ante bonus pays x{ante_bonus_mult} for your {player_hand_name}.")
    result_lines.append(detail)
    return {
        "service": "three_card_poker",
        "wager": int(wager),
        "stake": int(stake),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": detail,
        "summary": (
            f"You show {player_hand_name} against dealer {dealer_hand_name}. {headline}"
        ),
        "result_lines": result_lines,
        "player_cards": tuple(player_cards),
        "dealer_cards": tuple(dealer_cards),
        "player_hand_name": str(player_hand_name),
        "dealer_hand_name": str(dealer_hand_name),
        "dealer_qualifies": bool(dealer_qualifies),
        "ante_bonus": int(ante_bonus),
        "ante_bonus_mult": int(ante_bonus_mult),
        "social_gain": _casino_social_gain("three_card_poker", f"{current.get('seed_token', '')}:{outcome_key}"),
        "stake_already_paid": True,
    }


def _casino_slots_resolve(
    seed_contract,
    wager,
    *,
    bonus_wild_weight_scale=SLOT_BONUS_WILD_WEIGHT_SCALE,
):
    result = resolve_bakerrrr_slot(
        seed_contract,
        wager,
        bonus_wild_weight_scale=bonus_wild_weight_scale,
    )
    token = str((seed_contract or {}).get("token", seed_contract)) if isinstance(seed_contract, dict) else str(seed_contract)
    result.update({
        "service": "slots",
        "social_gain": _casino_social_gain("slots", token),
    })
    return result


def _casino_plinko_multiplier_label(multiplier):
    try:
        value = float(multiplier)
    except (TypeError, ValueError):
        value = 0.0
    if abs(value - int(value)) < 0.001:
        return f"{int(value)}x"
    return f"{value:.1f}x"


def _casino_ascii_plinko_board(*, drop_lane=None, path=(), bucket_index=None):
    bucket_count = len(CASINO_PLINKO_BUCKET_MULTIPLIERS)
    lane_labels = {
        lane + 1: str(lane + 1)
        for lane in range(CASINO_PLINKO_LANE_COUNT)
    }

    def _cell_line(label, markers=None, default=" "):
        markers = markers if isinstance(markers, dict) else {}
        cells = []
        for index in range(bucket_count):
            value = markers.get(index, default)
            cells.append(f"{str(value)[:3]:^3}")
        return f"{str(label)[:5]:<5}" + " ".join(cells).rstrip()

    try:
        lane = max(0, min(int(drop_lane), CASINO_PLINKO_LANE_COUNT - 1))
    except (TypeError, ValueError):
        lane = None

    current = (lane + 1) if lane is not None else None
    positions = [current] if current is not None else []
    normalized_path = []
    for raw_step in tuple(path or ())[:CASINO_PLINKO_ROWS]:
        step_text = str(raw_step or "").strip().upper()
        if step_text not in {"L", "R"} or current is None:
            continue
        normalized_path.append(step_text)
        current = max(0, min(current + (-1 if step_text == "L" else 1), bucket_count - 1))
        positions.append(current)

    lines = [
        ".---------------- plinko ----------------.",
        _cell_line("Lane", lane_labels, " "),
    ]
    if positions:
        lines.append(_cell_line("Drop", {positions[0]: "v"}, " "))
    for row_index in range(CASINO_PLINKO_ROWS):
        marker = {}
        if row_index + 1 < len(positions):
            marker[positions[row_index + 1]] = "o"
        direction = normalized_path[row_index] if row_index < len(normalized_path) else ""
        label = f"{row_index + 1}{direction}"
        lines.append(_cell_line(label, marker, "."))

    if bucket_index is not None:
        try:
            bucket = max(0, min(int(bucket_index), bucket_count - 1))
        except (TypeError, ValueError):
            bucket = None
        if bucket is not None:
            lines.append(_cell_line("Hit", {bucket: "^"}, " "))
    payout_markers = {
        index: _casino_plinko_multiplier_label(multiplier)
        for index, multiplier in enumerate(CASINO_PLINKO_BUCKET_MULTIPLIERS)
    }
    lines.extend([
        _cell_line("Pay", payout_markers, ""),
        "'-----------------------------------------'",
    ])
    return lines


def _casino_plinko_resolve(seed_token, wager, drop_lane):
    lane = max(0, min(int(drop_lane), CASINO_PLINKO_LANE_COUNT - 1))
    bounce_rng = random.Random(f"{seed_token}:plinko:{lane}")
    position = lane + 1
    path = []
    for _ in range(CASINO_PLINKO_ROWS):
        step = -1 if bounce_rng.random() < 0.5 else 1
        path.append("L" if step < 0 else "R")
        position = max(0, min(position + step, len(CASINO_PLINKO_BUCKET_MULTIPLIERS) - 1))
    payout_mult = float(CASINO_PLINKO_BUCKET_MULTIPLIERS[position])
    payout = max(0, int(round(float(wager) * payout_mult)))
    if payout_mult <= 0.0:
        headline = "Edge bucket."
        detail = "The disc chatters off the pegs and dies in a zero lane."
        outcome_key = "rim"
    elif payout_mult < 1.0:
        headline = "Shallow bucket."
        detail = "The board gives a little back, but not enough to cover the full drop."
        outcome_key = "low"
    elif payout_mult < 2.0:
        headline = "Middle bucket."
        detail = "The disc settles into a fair-paying lane and the crowd gives a polite murmur."
        outcome_key = "mid"
    else:
        headline = "Center bucket."
        detail = "The disc fights through the pegs and snaps into the hot center pocket."
        outcome_key = "center"
    result_lines = []
    result_lines.extend(_casino_ascii_plinko_board(drop_lane=lane, path=path, bucket_index=position))
    result_lines.extend([
        f"Drop lane {lane + 1}: {' '.join(path)}",
        f"Bucket {position + 1} pays x{payout_mult:.1f}.",
        detail,
    ])
    return {
        "service": "plinko",
        "wager": int(wager),
        "stake": int(wager),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": detail,
        "summary": f"Lane {lane + 1} rides {' '.join(path)} into bucket {position + 1}. {headline}",
        "result_lines": result_lines,
        "drop_lane": int(lane),
        "bucket_index": int(position),
        "path": tuple(path),
        "social_gain": _casino_social_gain("plinko", seed_token),
    }


CASINO_CRASH_MAX_MULTIPLIER = 30.0
CASINO_CRASH_STEP_TICKS = 1
CASINO_CRASH_BASE_TICK_GAIN = 0.01
CASINO_CRASH_ACCELERATION_GAIN = 0.00035
CASINO_CRASH_AUTO_STEPS = (0.01, 0.10, 1.00)
CASINO_CRASH_AUTO_MIN_MULTIPLIER = 1.01


def _casino_crash_target_multiplier(seed_token):
    rng = random.Random(f"{seed_token}:crash:point")
    roll = rng.random()
    if roll < 0.045:
        return 1.0 + rng.random() * 0.12
    if roll < 0.62:
        return 1.18 + rng.random() * 1.15
    if roll < 0.88:
        return 2.35 + rng.random() * 2.35
    if roll < 0.975:
        return 4.8 + rng.random() * 5.8
    return 10.8 + rng.random() * 19.2


def _casino_crash_multiplier_for_step(step):
    try:
        step = int(step)
    except (TypeError, ValueError):
        step = 0
    step = max(0, step)
    return round(
        1.0
        + (step * CASINO_CRASH_BASE_TICK_GAIN)
        + ((step * step) * CASINO_CRASH_ACCELERATION_GAIN),
        2,
    )


def _casino_crash_auto_step_value(value):
    try:
        value = round(float(value), 2)
    except (TypeError, ValueError):
        value = 0.10
    for option in CASINO_CRASH_AUTO_STEPS:
        if abs(value - float(option)) < 0.001:
            return float(option)
    return 0.10


def _casino_crash_normalize_auto_multiplier(value):
    try:
        value = round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0
    if value <= 0.0:
        return 0.0
    return round(max(CASINO_CRASH_AUTO_MIN_MULTIPLIER, min(CASINO_CRASH_MAX_MULTIPLIER, value)), 2)


def _casino_crash_setup(seed_token, wager, *, table_context=None):
    crash_point = round(float(_casino_crash_target_multiplier(seed_token)), 2)
    return {
        "service": "crash",
        "phase": "setup",
        "seed_token": str(seed_token),
        "wager": int(wager),
        "stake": int(wager),
        "step": 0,
        "current_multiplier": 1.0,
        "crash_point": crash_point,
        "auto_cashout_multiplier": 0.0,
        "auto_step": 0.10,
        "launched_tick": None,
        "last_step_tick": None,
        "history": (1.0,),
        "table_context": dict(table_context) if isinstance(table_context, dict) else {},
    }


def _casino_crash_start(seed_token, wager):
    session = _casino_crash_setup(seed_token, wager)
    session["phase"] = "live"
    session["launched_tick"] = 0
    session["last_step_tick"] = 0
    return session


def _casino_crash_normalize_session(session):
    if not isinstance(session, dict):
        return None
    try:
        step = max(0, int(session.get("step", 0) or 0))
    except (TypeError, ValueError):
        step = 0
    seed_token = str(session.get("seed_token", "")).strip()
    try:
        crash_point = round(float(session.get("crash_point", 0.0) or 0.0), 2)
    except (TypeError, ValueError):
        crash_point = 0.0
    if crash_point <= 0.0:
        crash_point = round(float(_casino_crash_target_multiplier(seed_token)), 2)
    history = []
    for value in list(session.get("history", ()) or ()):
        try:
            history.append(round(max(1.0, float(value)), 2))
        except (TypeError, ValueError):
            continue
    current_multiplier = round(float(session.get("current_multiplier", _casino_crash_multiplier_for_step(step)) or 1.0), 2)
    if not history:
        history = [1.0]
    if history[-1] != current_multiplier:
        history.append(current_multiplier)
    phase = str(session.get("phase", "live") or "live").strip().lower()
    if phase not in {"setup", "live"}:
        phase = "live"
    try:
        launched_tick = session.get("launched_tick")
        launched_tick = None if launched_tick is None else int(launched_tick)
    except (TypeError, ValueError):
        launched_tick = None
    try:
        last_step_tick = session.get("last_step_tick")
        last_step_tick = None if last_step_tick is None else int(last_step_tick)
    except (TypeError, ValueError):
        last_step_tick = None
    return {
        "service": "crash",
        "phase": phase,
        "seed_token": seed_token,
        "wager": int(session.get("wager", 0)),
        "stake": int(session.get("stake", session.get("wager", 0))),
        "step": int(step),
        "current_multiplier": float(current_multiplier),
        "crash_point": float(crash_point),
        "auto_cashout_multiplier": _casino_crash_normalize_auto_multiplier(session.get("auto_cashout_multiplier", 0.0)),
        "auto_step": _casino_crash_auto_step_value(session.get("auto_step", 0.10)),
        "launched_tick": launched_tick,
        "last_step_tick": last_step_tick,
        "history": tuple(history[-18:]),
        "property_id": session.get("property_id"),
        "property_name": str(session.get("property_name", "")).strip(),
        "table_context": _casino_preserved_table_context(session),
    }


def _casino_crash_adjust_auto(session, direction):
    current = _casino_crash_normalize_session(session)
    if not current:
        return None
    try:
        direction = int(direction or 0)
    except (TypeError, ValueError):
        direction = 0
    direction = -1 if direction < 0 else (1 if direction > 0 else 0)
    if direction == 0:
        return current
    value = _casino_crash_normalize_auto_multiplier(current.get("auto_cashout_multiplier", 0.0))
    step = _casino_crash_auto_step_value(current.get("auto_step", 0.10))
    if value <= 0.0:
        value = CASINO_CRASH_AUTO_MIN_MULTIPLIER if direction > 0 else 0.0
    else:
        value = _casino_crash_normalize_auto_multiplier(value + (step * direction))
        if direction < 0 and value <= CASINO_CRASH_AUTO_MIN_MULTIPLIER:
            value = 0.0
    current["auto_cashout_multiplier"] = float(value)
    return current


def _casino_crash_cycle_auto_step(session, direction=1):
    current = _casino_crash_normalize_session(session)
    if not current:
        return None
    steps = list(CASINO_CRASH_AUTO_STEPS)
    current_step = _casino_crash_auto_step_value(current.get("auto_step", 0.10))
    try:
        index = steps.index(current_step)
    except ValueError:
        index = 1
    try:
        direction = int(direction or 0)
    except (TypeError, ValueError):
        direction = 1
    delta = -1 if direction < 0 else 1
    current["auto_step"] = float(steps[(index + delta) % len(steps)])
    return current


def _casino_crash_toggle_auto(session):
    current = _casino_crash_normalize_session(session)
    if not current:
        return None
    value = _casino_crash_normalize_auto_multiplier(current.get("auto_cashout_multiplier", 0.0))
    current["auto_cashout_multiplier"] = 0.0 if value > 0.0 else 2.0
    return current


def _casino_crash_launch(session, now_tick=0):
    current = _casino_crash_normalize_session(session)
    if not current:
        return None
    try:
        now_tick = int(now_tick)
    except (TypeError, ValueError):
        now_tick = 0
    current["phase"] = "live"
    current["step"] = 0
    current["current_multiplier"] = 1.0
    current["history"] = (1.0,)
    current["launched_tick"] = int(now_tick)
    current["last_step_tick"] = int(now_tick)
    return current


def _casino_crash_cashout(session, *, reason="manual"):
    current = _casino_crash_normalize_session(session)
    if not current:
        return None, None
    multiplier = float(current.get("current_multiplier", 1.0) or 1.0)
    crash_point = float(current.get("crash_point", 1.0) or 1.0)
    wager = int(current.get("wager", 0))
    reason = str(reason or "manual").strip().lower()
    auto = reason == "auto"
    payout = int(round(float(wager) * multiplier))
    result_lines = [
        f"{'Auto cash out' if auto else 'Cash out'}: x{multiplier:.2f}.",
        f"Crash point: x{crash_point:.2f}.",
        "The credits are already off the table when the graph keeps climbing." if auto else "You step off the graph before it breaks.",
    ]
    return None, {
        "service": "crash",
        "wager": int(wager),
        "stake": int(current.get("stake", wager)),
        "payout": int(payout),
        "outcome_key": "auto_cashout" if auto else "cashout",
        "headline": f"{'Auto cash out' if auto else 'Cash out'} at x{multiplier:.2f}.",
        "detail": "The line keeps screaming, but your credits are already off the table.",
        "summary": f"Crash {'auto ' if auto else ''}cashout x{multiplier:.2f} before x{crash_point:.2f}.",
        "result_lines": result_lines,
        "cashout_multiplier": float(multiplier),
        "auto_cashout_multiplier": float(current.get("auto_cashout_multiplier", 0.0) or 0.0),
        "crash_point": float(crash_point),
        "history": tuple(current.get("history", ()) or ()),
        "social_gain": _casino_social_gain("crash", f"{current.get('seed_token', '')}:cashout:{multiplier:.2f}"),
        "stake_already_paid": True,
    }


def _casino_crash_crash_result(current, next_multiplier):
    crash_point = float(current.get("crash_point", 1.0) or 1.0)
    wager = int(current.get("wager", 0))
    history = list(current.get("history", ()) or ())
    if not history or round(float(history[-1]), 2) != round(float(next_multiplier), 2):
        history.append(round(float(next_multiplier), 2))
    result_lines = [
        f"Crash: x{crash_point:.2f}.",
        f"You were riding x{next_multiplier:.2f}.",
        "The graph snaps vertical, then drops dead.",
    ]
    return {
        "service": "crash",
        "wager": int(wager),
        "stake": int(current.get("stake", wager)),
        "payout": 0,
        "outcome_key": "crash",
        "headline": f"Crash at x{crash_point:.2f}.",
        "detail": "The multiplier breaks before you can pull the stake off the glass.",
        "summary": f"Crash point x{crash_point:.2f}; ride reached x{next_multiplier:.2f}.",
        "result_lines": result_lines,
        "cashout_multiplier": 0.0,
        "auto_cashout_multiplier": float(current.get("auto_cashout_multiplier", 0.0) or 0.0),
        "crash_point": float(crash_point),
        "history": tuple(history[-18:]),
        "social_gain": _casino_social_gain("crash", f"{current.get('seed_token', '')}:crash:{crash_point:.2f}"),
        "stake_already_paid": True,
    }


def _casino_crash_advance(session, now_tick):
    current = _casino_crash_normalize_session(session)
    if not current:
        return None, None
    if current.get("phase") != "live":
        return current, None
    try:
        now_tick = int(now_tick)
    except (TypeError, ValueError):
        now_tick = int(current.get("last_step_tick", 0) or 0)
    last_tick = current.get("last_step_tick")
    if last_tick is None:
        last_tick = current.get("launched_tick")
    try:
        last_tick = int(last_tick)
    except (TypeError, ValueError):
        last_tick = int(now_tick)
    if now_tick - last_tick < CASINO_CRASH_STEP_TICKS:
        return current, None

    due_steps = max(1, (now_tick - last_tick) // CASINO_CRASH_STEP_TICKS)
    auto_target = _casino_crash_normalize_auto_multiplier(current.get("auto_cashout_multiplier", 0.0))
    crash_point = float(current.get("crash_point", 1.0) or 1.0)
    for _ in range(due_steps):
        next_step = int(current.get("step", 0)) + 1
        next_multiplier = float(_casino_crash_multiplier_for_step(next_step))
        current["last_step_tick"] = int(current.get("last_step_tick", last_tick) or last_tick) + CASINO_CRASH_STEP_TICKS
        if auto_target > 0.0 and auto_target <= next_multiplier and auto_target < crash_point:
            current["step"] = int(next_step)
            current["current_multiplier"] = float(auto_target)
            history = list(current.get("history", ()) or ())
            history.append(round(float(auto_target), 2))
            current["history"] = tuple(history[-18:])
            return None, _casino_crash_cashout(current, reason="auto")[1]
        history = list(current.get("history", ()) or ())
        history.append(round(next_multiplier, 2))
        if next_multiplier >= crash_point:
            current["step"] = int(next_step)
            current["current_multiplier"] = round(next_multiplier, 2)
            current["history"] = tuple(history[-18:])
            return None, _casino_crash_crash_result(current, next_multiplier)
        current["step"] = int(next_step)
        current["current_multiplier"] = round(next_multiplier, 2)
        current["history"] = tuple(history[-18:])
    return current, None


def _casino_crash_resolve(session, action):
    current = _casino_crash_normalize_session(session)
    if not current:
        return None, None
    action = str(action or "").strip().lower()
    if action == "cashout":
        return _casino_crash_cashout(current)
    if action != "ride":
        return current, None

    next_step = int(current.get("step", 0)) + 1
    next_multiplier = float(_casino_crash_multiplier_for_step(next_step))
    history = list(current.get("history", ()) or ())
    history.append(round(next_multiplier, 2))
    if next_multiplier >= float(current.get("crash_point", 1.0) or 1.0):
        current["history"] = tuple(history[-18:])
        return None, _casino_crash_crash_result(current, next_multiplier)
    current["step"] = int(next_step)
    current["current_multiplier"] = round(next_multiplier, 2)
    current["history"] = tuple(history[-18:])
    return current, None


def _casino_blackjack_can_split(cards):
    cards = list(cards or ())
    if len(cards) != 2:
        return False
    return _casino_blackjack_value(cards[0]) == _casino_blackjack_value(cards[1])


def _casino_twenty_one_hand(cards, stake, *, state="pending", doubled=False, natural_eligible=True, split_origin=False):
    return {
        "cards": list(cards or ()),
        "stake": int(stake),
        "state": str(state or "pending").strip().lower() or "pending",
        "doubled": bool(doubled),
        "natural_eligible": bool(natural_eligible),
        "split_origin": bool(split_origin),
    }


def _casino_twenty_one_normalize_session(session):
    if not isinstance(session, dict):
        return None
    current = {
        "service": "twenty_one",
        "seed_token": str(session.get("seed_token", "")).strip(),
        "wager": int(session.get("wager", 0)),
        "stake": int(session.get("stake", session.get("wager", 0))),
        "deck": list(session.get("deck", ()) or ()),
        "deck_index": int(session.get("deck_index", 0)),
        "dealer_cards": list(session.get("dealer_cards", ()) or ()),
        "property_id": session.get("property_id"),
        "property_name": str(session.get("property_name", "")).strip(),
        "split_used": bool(session.get("split_used", False)),
        "table_context": _casino_preserved_table_context(session),
    }
    raw_hands = list(session.get("hands", ()) or ())
    hands = []
    if raw_hands:
        for idx, raw in enumerate(raw_hands):
            raw = raw if isinstance(raw, dict) else {}
            hands.append(_casino_twenty_one_hand(
                raw.get("cards", ()),
                raw.get("stake", current["wager"]),
                state=raw.get("state", "active" if idx == 0 else "pending"),
                doubled=raw.get("doubled", False),
                natural_eligible=raw.get("natural_eligible", True),
                split_origin=raw.get("split_origin", False),
            ))
    else:
        hands.append(_casino_twenty_one_hand(
            session.get("player_cards", ()),
            current["stake"],
            state="active",
            natural_eligible=True,
        ))
    current["hands"] = hands
    current["split_used"] = bool(current["split_used"] or len(hands) > 1)
    active_hand_index = int(session.get("active_hand_index", 0))
    active_found = False
    for idx, hand in enumerate(current["hands"]):
        state = str(hand.get("state", "pending")).strip().lower()
        if state == "active":
            current["active_hand_index"] = idx
            active_found = True
            break
    if not active_found:
        if current["hands"]:
            active_hand_index = max(0, min(active_hand_index, len(current["hands"]) - 1))
            if str(current["hands"][active_hand_index].get("state", "pending")).strip().lower() == "pending":
                current["hands"][active_hand_index]["state"] = "active"
                current["active_hand_index"] = active_hand_index
                active_found = True
        if not active_found:
            for idx, hand in enumerate(current["hands"]):
                if str(hand.get("state", "pending")).strip().lower() == "pending":
                    hand["state"] = "active"
                    current["active_hand_index"] = idx
                    active_found = True
                    break
    if not active_found:
        current["active_hand_index"] = -1
    current["stake"] = sum(max(0, int(hand.get("stake", 0))) for hand in current["hands"])
    return current


def _casino_twenty_one_active_hand(session):
    if not isinstance(session, dict):
        return None
    hands = list(session.get("hands", ()) or ())
    idx = int(session.get("active_hand_index", -1))
    if 0 <= idx < len(hands):
        return hands[idx]
    return None


def _casino_twenty_one_draw_card(session):
    if not isinstance(session, dict):
        return None
    deck = list(session.get("deck", ()) or ())
    deck_index = int(session.get("deck_index", 0))
    if deck_index >= len(deck):
        return None
    card = deck[deck_index]
    session["deck_index"] = deck_index + 1
    return card


def _casino_twenty_one_activate_next_hand(session):
    if not isinstance(session, dict):
        return False
    for idx, hand in enumerate(list(session.get("hands", ()) or ())):
        if str(hand.get("state", "pending")).strip().lower() == "pending":
            hand["state"] = "active"
            session["active_hand_index"] = idx
            return True
    session["active_hand_index"] = -1
    return False


def _casino_twenty_one_auto_progress(session):
    if not isinstance(session, dict):
        return False
    while True:
        hand = _casino_twenty_one_active_hand(session)
        if not isinstance(hand, dict):
            return False
        total, _soft = _casino_blackjack_total(hand.get("cards", ()))
        if total > 21:
            hand["state"] = "bust"
        elif total == 21:
            hand["state"] = "stood"
        else:
            return True
        if not _casino_twenty_one_activate_next_hand(session):
            return False


def _casino_twenty_one_action_ids(session, wallet_credits=0):
    current = _casino_twenty_one_normalize_session(session)
    hand = _casino_twenty_one_active_hand(current)
    if not current or not isinstance(hand, dict):
        return ()
    action_ids = ["twenty_one:hit", "twenty_one:stand"]
    wager = int(current.get("wager", 0))
    if len(list(hand.get("cards", ()) or ())) == 2 and wallet_credits >= wager:
        action_ids.append("twenty_one:double")
        if (
            len(list(current.get("hands", ()) or ())) == 1
            and not bool(current.get("split_used", False))
            and _casino_blackjack_can_split(hand.get("cards", ()))
        ):
            action_ids.append("twenty_one:split")
    return tuple(action_ids)


def _casino_twenty_one_finalize(session):
    current = _casino_twenty_one_normalize_session(session)
    if not current:
        return None
    while True:
        dealer_total, dealer_soft = _casino_blackjack_total(current["dealer_cards"])
        if dealer_total > 17:
            break
        if dealer_total == 17 and not dealer_soft:
            break
        card = _casino_twenty_one_draw_card(current)
        if not card:
            break
        current["dealer_cards"].append(card)

    dealer_total, _dealer_soft = _casino_blackjack_total(current["dealer_cards"])
    hand_results = []
    payout = 0
    for idx, hand in enumerate(current["hands"]):
        cards = list(hand.get("cards", ()) or ())
        total, _soft = _casino_blackjack_total(cards)
        hand_stake = int(hand.get("stake", current["wager"]))
        if total > 21 or str(hand.get("state", "")).strip().lower() == "bust":
            result_key = "bust"
            hand_payout = 0
        elif dealer_total > 21 or total > dealer_total:
            result_key = "win"
            hand_payout = hand_stake * 2
        elif dealer_total == total:
            result_key = "push"
            hand_payout = hand_stake
        else:
            result_key = "lose"
            hand_payout = 0
        hand_results.append({
            "index": idx,
            "cards": tuple(cards),
            "total": int(total),
            "stake": int(hand_stake),
            "result": result_key,
            "doubled": bool(hand.get("doubled", False)),
            "split_origin": bool(hand.get("split_origin", False)),
        })
        payout += int(hand_payout)

    result_counter = Counter(row["result"] for row in hand_results)
    if result_counter.get("win", 0) > 0 and result_counter.get("lose", 0) == 0 and result_counter.get("bust", 0) == 0:
        outcome_key = "player_win"
        headline = "You beat the dealer."
    elif result_counter.get("win", 0) > 0 and (result_counter.get("lose", 0) > 0 or result_counter.get("bust", 0) > 0):
        outcome_key = "mixed"
        headline = "The split goes both ways."
    elif result_counter.get("push", 0) == len(hand_results):
        outcome_key = "push"
        headline = "Push."
    elif dealer_total > 21 and result_counter.get("bust", 0) == len(hand_results):
        outcome_key = "player_bust"
        headline = "Every hand busts."
    elif dealer_total > 21:
        outcome_key = "dealer_bust"
        headline = "Dealer busts."
    elif result_counter.get("bust", 0) == len(hand_results):
        outcome_key = "player_bust"
        headline = "Every hand busts."
    else:
        outcome_key = "dealer_win"
        headline = "Dealer takes it."

    detail_bits = []
    for row in hand_results:
        label = f"Hand {row['index'] + 1}"
        status = row["result"]
        if status == "win":
            status_text = "wins"
        elif status == "push":
            status_text = "pushes"
        elif status == "bust":
            status_text = "busts"
        else:
            status_text = "loses"
        detail_bits.append(f"{label} {status_text}")
    detail = ", ".join(detail_bits) + "."

    result_lines = []
    result_lines.extend(_casino_ascii_card_block("Dealer", current["dealer_cards"]))
    result_lines.append(_casino_blackjack_line("Dealer", current["dealer_cards"]))
    for row in hand_results:
        tags = []
        if row["split_origin"]:
            tags.append("split")
        if row["doubled"]:
            tags.append("double")
        suffix = f" [{', '.join(tags)}]" if tags else ""
        hand_label = f"Hand {row['index'] + 1}"
        result_lines.extend(_casino_ascii_card_block(hand_label, row["cards"]))
        result_lines.append(f"{_casino_blackjack_line(hand_label, row['cards'])}{suffix} -> {row['result']}.")
    result_lines.append(detail)

    return {
        "service": "twenty_one",
        "wager": int(current["wager"]),
        "stake": int(current["stake"]),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": detail,
        "summary": (
            f"Dealer {_casino_cards_text(current['dealer_cards'])} ({dealer_total}). "
            f"{detail}"
        ),
        "result_lines": result_lines,
        "player_cards": tuple(hand_results[0]["cards"]) if hand_results else (),
        "player_hands": tuple(row["cards"] for row in hand_results),
        "player_total": int(hand_results[0]["total"]) if hand_results else 0,
        "player_totals": tuple(int(row["total"]) for row in hand_results),
        "dealer_cards": tuple(current["dealer_cards"]),
        "dealer_total": int(dealer_total),
        "hand_results": tuple(
            {
                "index": int(row["index"]),
                "total": int(row["total"]),
                "stake": int(row["stake"]),
                "result": str(row["result"]),
                "doubled": bool(row["doubled"]),
                "split_origin": bool(row["split_origin"]),
            }
            for row in hand_results
        ),
        "social_gain": _casino_social_gain("twenty_one", f"{current['seed_token']}:{outcome_key}"),
        "stake_already_paid": True,
    }


def _casino_twenty_one_start(seed_token, wager):
    deck = _casino_shuffled_deck(seed_token)
    return {
        "service": "twenty_one",
        "seed_token": str(seed_token),
        "wager": int(wager),
        "stake": int(wager),
        "deck": list(deck),
        "deck_index": 4,
        "dealer_cards": [deck[1], deck[3]],
        "hands": [
            _casino_twenty_one_hand([deck[0], deck[2]], int(wager), state="active", natural_eligible=True),
        ],
        "active_hand_index": 0,
        "split_used": False,
    }


def _casino_twenty_one_resolve(session, action):
    current = _casino_twenty_one_normalize_session(session)
    if not current:
        return None, None
    action = str(action or "").strip().lower()
    active_hand = _casino_twenty_one_active_hand(current)
    dealer_total, _dealer_soft = _casino_blackjack_total(current["dealer_cards"])

    if action == "start" and isinstance(active_hand, dict):
        player_total, _player_soft = _casino_blackjack_total(active_hand.get("cards", ()))
        player_natural = len(list(active_hand.get("cards", ()) or ())) == 2 and player_total == 21 and bool(active_hand.get("natural_eligible", True))
        dealer_natural = len(current["dealer_cards"]) == 2 and dealer_total == 21
        if player_natural or dealer_natural:
            if player_natural and dealer_natural:
                outcome_key = "push_blackjack"
                payout = int(active_hand.get("stake", current["wager"]))
                headline = "Both hands open hot."
                detail = "You and the dealer both flip blackjack, so the bet pushes."
            elif player_natural:
                outcome_key = "player_blackjack"
                payout = int(round(float(active_hand.get("stake", current["wager"])) * 2.5))
                headline = "Natural 21."
                detail = "You peel blackjack off the deal and the table pays 3 to 2."
            else:
                outcome_key = "dealer_blackjack"
                payout = 0
                headline = "Dealer blackjack."
                detail = "The dealer turns over a natural and sweeps the felt clean."
            result_lines = []
            result_lines.extend(_casino_ascii_card_block("Dealer", current["dealer_cards"]))
            result_lines.extend(_casino_ascii_card_block("You", active_hand.get("cards", ())))
            return None, {
                "service": "twenty_one",
                "wager": int(current["wager"]),
                "stake": int(current["stake"]),
                "payout": int(payout),
                "outcome_key": outcome_key,
                "headline": headline,
                "detail": detail,
                "summary": (
                    f"Dealer {_casino_cards_text(current['dealer_cards'])} against "
                    f"{_casino_cards_text(active_hand.get('cards', ())) }. {headline}"
                ).replace("  ", " "),
                "result_lines": result_lines + [
                    _casino_blackjack_line("Dealer", current["dealer_cards"]),
                    _casino_blackjack_line("You", active_hand.get("cards", ())),
                    detail,
                ],
                "player_cards": tuple(active_hand.get("cards", ()) or ()),
                "player_hands": (tuple(active_hand.get("cards", ()) or ()),),
                "player_total": int(player_total),
                "player_totals": (int(player_total),),
                "dealer_cards": tuple(current["dealer_cards"]),
                "dealer_total": int(dealer_total),
                "social_gain": _casino_social_gain("twenty_one", current["seed_token"]),
                "stake_already_paid": True,
            }
        return current, None

    if not isinstance(active_hand, dict):
        return None, _casino_twenty_one_finalize(current)

    if action == "split" and _casino_blackjack_can_split(active_hand.get("cards", ())):
        cards = list(active_hand.get("cards", ()) or ())
        card_a = _casino_twenty_one_draw_card(current)
        card_b = _casino_twenty_one_draw_card(current)
        if card_a:
            current["hands"][0] = _casino_twenty_one_hand(
                [cards[0], card_a],
                current["wager"],
                state="active",
                natural_eligible=False,
                split_origin=True,
            )
        if card_b:
            current["hands"].append(_casino_twenty_one_hand(
                [cards[1], card_b],
                current["wager"],
                state="pending",
                natural_eligible=False,
                split_origin=True,
            ))
        current["active_hand_index"] = 0
        current["split_used"] = True
        current["stake"] = sum(int(hand.get("stake", 0)) for hand in current["hands"])
        if _casino_twenty_one_auto_progress(current):
            return current, None
        return None, _casino_twenty_one_finalize(current)

    if action == "double":
        active_hand["stake"] = int(active_hand.get("stake", current["wager"])) + int(current["wager"])
        active_hand["doubled"] = True
        current["stake"] = sum(int(hand.get("stake", 0)) for hand in current["hands"])
        card = _casino_twenty_one_draw_card(current)
        if card:
            active_hand["cards"].append(card)
        total, _soft = _casino_blackjack_total(active_hand.get("cards", ()))
        active_hand["state"] = "bust" if total > 21 else "stood"
        if _casino_twenty_one_activate_next_hand(current) and _casino_twenty_one_auto_progress(current):
            return current, None
        return None, _casino_twenty_one_finalize(current)

    if action == "hit":
        card = _casino_twenty_one_draw_card(current)
        if card:
            active_hand["cards"].append(card)
        total, _soft = _casino_blackjack_total(active_hand.get("cards", ()))
        if total > 21:
            active_hand["state"] = "bust"
            if _casino_twenty_one_activate_next_hand(current) and _casino_twenty_one_auto_progress(current):
                return current, None
            return None, _casino_twenty_one_finalize(current)
        if total == 21:
            active_hand["state"] = "stood"
            if _casino_twenty_one_activate_next_hand(current) and _casino_twenty_one_auto_progress(current):
                return current, None
            return None, _casino_twenty_one_finalize(current)
        return current, None

    if action == "stand":
        active_hand["state"] = "stood"
        if _casino_twenty_one_activate_next_hand(current) and _casino_twenty_one_auto_progress(current):
            return current, None
        return None, _casino_twenty_one_finalize(current)

    return current, None


def _casino_holdem_dealer_qualifies(score):
    if not score:
        return False
    category = int(score[0])
    if category >= 2:
        return True
    if category == 1:
        return int(score[1]) >= 4
    return False


def _casino_holdem_ante_bonus_multiplier(score):
    if not score:
        return 0
    if int(score[0]) == 8 and len(score) > 1 and int(score[1]) == 14:
        return int(CASINO_HOLDEM_ANTE_BONUS_MULTIPLIERS.get("royal_flush", 0))
    return int(CASINO_HOLDEM_ANTE_BONUS_MULTIPLIERS.get(int(score[0]), 0))


def _casino_holdem_start(seed_token, wager):
    deck = _casino_shuffled_deck(seed_token)
    return {
        "service": "casino_holdem",
        "seed_token": str(seed_token),
        "wager": int(wager),
        "stake": int(wager),
        "player_cards": [deck[0], deck[2]],
        "dealer_cards": [deck[1], deck[3]],
        "flop": [deck[4], deck[5], deck[6]],
        "turn": deck[7],
        "river": deck[8],
    }


def _casino_holdem_resolve(session, action):
    if not isinstance(session, dict):
        return None
    wager = int(session.get("wager", 0))
    stake = int(session.get("stake", wager))
    action = str(action or "").strip().lower()
    player_cards = list(session.get("player_cards", ()) or ())
    dealer_cards = list(session.get("dealer_cards", ()) or ())
    flop = list(session.get("flop", ()) or ())
    turn = str(session.get("turn", "")).strip().upper()
    river = str(session.get("river", "")).strip().upper()
    board = flop + ([turn] if turn else []) + ([river] if river else [])
    board_text = _casino_cards_text(board)
    if action == "fold":
        result_lines = []
        result_lines.extend(_casino_ascii_card_block("You", player_cards))
        result_lines.extend(_casino_ascii_card_block("Flop", flop))
        return {
            "service": "casino_holdem",
            "wager": int(wager),
            "stake": int(stake),
            "payout": 0,
            "outcome_key": "fold",
            "headline": "You fold the ante.",
            "detail": "The flop looks wrong, so you release the hand and leave the ante in the circle.",
            "summary": f"You fold after the flop and forfeit the {wager}c ante.",
            "result_lines": result_lines + [
                f"Your hand: {_casino_cards_text(player_cards)}",
                f"Flop: {_casino_cards_text(flop)}",
                "You fold and let the ante go.",
            ],
            "player_cards": tuple(player_cards),
            "dealer_cards": tuple(dealer_cards),
            "board": tuple(flop),
            "social_gain": _casino_social_gain("casino_holdem", f"{session.get('seed_token', '')}:fold"),
            "stake_already_paid": True,
        }

    ante_stake = int(wager)
    call_stake = max(0, int(stake) - int(ante_stake))
    player_best = _casino_best_poker_hand(player_cards + board)
    dealer_best = _casino_best_poker_hand(dealer_cards + board)
    dealer_qualifies = _casino_holdem_dealer_qualifies(dealer_best["score"])
    ante_bonus_mult = _casino_holdem_ante_bonus_multiplier(player_best["score"])
    ante_bonus = int(max(0, ante_bonus_mult) * ante_stake)

    if not dealer_qualifies:
        outcome_key = "dealer_not_qualify"
        payout = int((ante_stake * 2) + call_stake + ante_bonus)
        headline = "Dealer doesn't qualify."
        detail = "The dealer misses pair of fours, so the ante wins and the call pushes."
    elif player_best["score"] > dealer_best["score"]:
        outcome_key = "player_win"
        payout = int((stake * 2) + ante_bonus)
        headline = "You drag the pot."
        detail = "Your made hand holds up, so both circles win even money."
    elif player_best["score"] == dealer_best["score"]:
        outcome_key = "push"
        payout = int(stake + ante_bonus)
        headline = "Split pot."
        detail = "The board runs out into a tie, so the ante and call both push."
    else:
        outcome_key = "dealer_win"
        payout = int(ante_bonus)
        headline = "Dealer takes it."
        detail = "The house makes the better hand and sweeps the ante and call."

    result_lines = []
    result_lines.extend(_casino_ascii_card_block("Board", board))
    result_lines.extend(_casino_ascii_card_block("You", player_cards))
    result_lines.extend(_casino_ascii_card_block("Dealer", dealer_cards))
    result_lines.extend([
        f"Board: {board_text}",
        f"You: {_casino_cards_text(player_cards)} ({player_best['name']})",
        f"Dealer: {_casino_cards_text(dealer_cards)} ({dealer_best['name']})",
        "Dealer qualifies." if dealer_qualifies else "Dealer does not qualify (needs pair of 4s+).",
    ])
    if ante_bonus > 0:
        result_lines.append(f"Ante bonus pays x{ante_bonus_mult} for your {player_best['name']}.")
    result_lines.append(detail)
    return {
        "service": "casino_holdem",
        "wager": int(wager),
        "stake": int(stake),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": detail,
        "summary": (
            f"Board {board_text}. You show {player_best['name']}; dealer shows {dealer_best['name']}. {headline}"
        ),
        "result_lines": result_lines,
        "player_cards": tuple(player_cards),
        "dealer_cards": tuple(dealer_cards),
        "board": tuple(board),
        "player_hand_name": str(player_best["name"]),
        "dealer_hand_name": str(dealer_best["name"]),
        "dealer_qualifies": bool(dealer_qualifies),
        "ante_bonus": int(ante_bonus),
        "ante_bonus_mult": int(ante_bonus_mult),
        "social_gain": _casino_social_gain("casino_holdem", f"{session.get('seed_token', '')}:{outcome_key}"),
        "stake_already_paid": True,
    }


def _casino_apply_round_result(sim, eid, prop, service, round_result):
    service = str(service or "").strip().lower()
    profile = _casino_game_profile(service)
    if not profile or not isinstance(round_result, dict):
        return None, {
            "eid": eid,
            "property_id": prop.get("id") if isinstance(prop, dict) else None,
            "property_name": prop.get("name", prop.get("id")) if isinstance(prop, dict) else str(prop or "Casino"),
            "service": service,
            "reason": "invalid_round",
        }

    wager = max(0, int(round_result.get("wager", 0)))
    stake = max(0, int(round_result.get("stake", wager)))
    payout = max(0, int(round_result.get("payout", 0)))
    stake_already_paid = bool(round_result.get("stake_already_paid", False))
    assets = sim.ecs.get(PlayerAssets).get(eid)
    credits_before = int(getattr(assets, "credits", 0)) if assets else 0
    if not stake_already_paid:
        if credits_before < stake:
            return None, {
                "eid": eid,
                "property_id": prop.get("id") if isinstance(prop, dict) else None,
                "property_name": prop.get("name", prop.get("id")) if isinstance(prop, dict) else str(prop or "Casino"),
                "service": service,
                "reason": "no_credits",
                "cost": int(stake),
                "credits": int(credits_before),
            }
        if assets:
            assets.credits = max(0, int(assets.credits) - int(stake))
            assets.credits = int(assets.credits) + int(payout)
            credits_after = int(assets.credits)
        else:
            credits_after = max(0, int(credits_before) - int(stake) + int(payout))
    else:
        if assets:
            assets.credits = int(assets.credits) + int(payout)
            credits_after = int(assets.credits)
        else:
            credits_after = int(credits_before) + int(payout)

    social_gain = max(0, int(round_result.get("social_gain", 0)))
    needs = sim.ecs.get(NPCNeeds).get(eid)
    if needs and social_gain > 0:
        needs.social = _clamp(float(needs.social) + float(social_gain))

    payload = dict(round_result)
    context = payload.get("table_context_summary")
    if not isinstance(context, dict) or not context:
        context = payload.get("table_context")
    if not isinstance(context, dict) or not context:
        context = _casino_table_context(sim, prop, game=service)
    context_summary = _casino_table_context_summary(context)
    if context_summary:
        payload["table_context"] = dict(context_summary)
        payload["table_context_summary"] = dict(context_summary)
    payload.update({
        "eid": eid,
        "property_id": prop.get("id") if isinstance(prop, dict) else None,
        "property_name": (
            str(prop.get("name", prop.get("id", "Casino"))).strip()
            if isinstance(prop, dict)
            else str(prop or "Casino").strip()
        ) or "Casino",
        "service": service,
        "wager": int(wager),
        "stake": int(stake),
        "payout": int(payout),
        "net_credits": int(payout - stake),
        "credits_after": int(credits_after),
        "social_gain": int(social_gain),
    })
    return payload, None


def _casino_game_profile(service):
    return CASINO_GAME_PROFILES.get(str(service or "").strip().lower())


def _casino_game_title(service):
    profile = _casino_game_profile(service)
    if profile:
        return str(profile.get("title", service)).strip() or str(service or "Casino game").strip()
    return str(service or "Casino game").replace("_", " ").title()


def _site_service_label(service):
    service = str(service or "").strip().lower()
    casino_profile = CASINO_GAME_PROFILES.get(service)
    if casino_profile:
        return str(casino_profile.get("service_label", casino_profile.get("title", service))).strip().lower()
    transit_profile = _transit_service_profile(service)
    if transit_profile:
        return str(transit_profile.get("service_label", service)).strip().lower() or service.replace("_", " ")
    mapping = {
        "building_repair": "building repair",
        "appearance_style": "styling",
        "business_management": "business desk",
        "business_remodel": "business refit",
        "butcher_prepare": "butcher prep",
        "civic_records": "civic records",
        "fauna_registry": "fauna registry",
        "campfire_cook": "campfire cooking",
        "campfire_herb_cache": "campfire herb cache",
        "campfire_herbal_mix": "campfire herb mixing",
        "campfire_herbal_recipe": "campfire herbal recipe",
        "cult_contact": "circle contact",
        "cult_conversion": "circle membership",
        "cult_donation": "circle donation",
        "cult_uniform_replacement": "circle clothing",
        "cult_meeting_info": "circle meeting",
        "cult_leader_audience": "circle audience",
        "cult_leave": "leave circle",
        "herbal_care": "herbal care",
        "herbal_compound": "herbal compounding",
        "herbal_prepare": "herbal preparation",
        "flora_registry": "flora registry",
        "herbal_recipe_sales": "herbal recipes",
        "intel": "intel",
        "underground_access": "passage",
        "shelter": "shelter",
        "rest": "lodging",
        "vending": "snacks",
        "fuel": "fuel",
        "fuel_fill_bottle": "fuel bottle filling",
        "repair": "repair",
        "courier_jobs": "courier jobs",
        "agency_jobs": "agency jobs",
        "bounty_jobs": "bounty board",
        "vehicle_sales_new": "new vehicles",
        "vehicle_sales_used": "used vehicles",
        "vehicle_fetch": "vehicle retrieval",
    }
    return mapping.get(service, service.replace("_", " "))


def _service_menu_option_label(option_id):
    option_id = str(option_id or "").strip().lower()
    casino_profile = _casino_game_profile(option_id)
    if casino_profile:
        return str(casino_profile.get("menu_label", _casino_game_title(option_id))).strip()
    transit_profile = _transit_service_profile(option_id)
    if transit_profile:
        return str(transit_profile.get("menu_label", _transit_service_title(option_id))).strip() or _transit_service_title(option_id)
    mapping = {
        "trade_buy": "Browse goods",
        "trade_sell": "Sell goods",
        "banking": "Manage bank funds",
        "insurance": "Review coverage",
        "justice_dispatch": "Call for an officer",
        "building_repair": "Repair a building",
        "appearance_style": "Change appearance",
        "business_management": "Business desk",
        "business_remodel": "Change business type",
        "bodyguard_contract": "Hire bodyguards",
        "butcher_prepare": "Prepare meat",
        "civic_records": "Inspect civic records",
        "fauna_registry": "Review fauna registry",
        "campfire_cook": "Cook meat",
        "campfire_herb_cache": "Open herb cache",
        "campfire_herbal_mix": "Free-mix cached herbs",
        "campfire_herbal_recipe": "Make cached recipe",
        "cult_contact": "Speak to contact",
        "cult_conversion": "Hear the circle out",
        "cult_donation": "Make a donation",
        "cult_uniform_replacement": "Replace circle clothing",
        "cult_meeting_info": "Ask meeting place",
        "cult_leader_audience": "Request leader audience",
        "cult_leave": "Leave the circle",
        "herbal_care": "Get herbal care",
        "herbal_compound": "Compound herbs",
        "herbal_prepare": "Prepare herbs",
        "herbal_recipe_sales": "Learn herbal recipe",
        "flora_registry": "Review flora registry",
        "underground_access": "Use passage",
        "vending": "Buy a snack",
        "fuel": "Refuel vehicle",
        "fuel_fill_bottle": "Fill bottle with fuel",
        "repair": "Repair vehicle",
        "courier_jobs": "Check courier jobs",
        "agency_jobs": "Check agency jobs",
        "bounty_jobs": "Check bounty board",
        "shelter": "Use shelter",
        "rest": "Rent a room",
        "intel": "Ask for local intel",
        "vehicle_sales_new": "Browse new vehicles",
        "vehicle_sales_used": "Browse used vehicles",
        "vehicle_fetch": "Have a vehicle delivered",
    }
    if option_id in mapping:
        return mapping[option_id]
    if option_id.startswith("vehicle_sales_"):
        return _site_service_label(option_id).title()
    return option_id.replace("_", " ").title()


def _credit_amount_label(amount):
    try:
        value = int(amount)
    except (TypeError, ValueError):
        value = 0
    return f"{max(0, value)}c"


__all__ = [
    "CASINO_GAME_SERVICE_IDS",
    "CASINO_CRASH_AUTO_STEPS",
    "CASINO_CRASH_MAX_MULTIPLIER",
    "CASINO_CRASH_STEP_TICKS",
    "CASINO_PLINKO_LANE_COUNT",
    "TRANSIT_SERVICE_IDS",
    "_casino_apply_round_result",
    "_casino_ascii_plinko_board",
    "_casino_baccarat_normalize_session",
    "_casino_baccarat_resolve",
    "_casino_baccarat_start",
    "_casino_blackjack_line",
    "_casino_blackjack_total",
    "casino_game_capabilities",
    "_casino_cards_text",
    "_casino_craps_normalize_session",
    "_casino_craps_resolve",
    "_casino_craps_start",
    "_casino_crash_adjust_auto",
    "_casino_crash_advance",
    "_casino_crash_cashout",
    "_casino_crash_cycle_auto_step",
    "_casino_crash_launch",
    "_casino_crash_normalize_session",
    "_casino_crash_multiplier_for_step",
    "_casino_crash_resolve",
    "_casino_crash_setup",
    "_casino_crash_start",
    "_casino_crash_toggle_auto",
    "_casino_game_profile",
    "_casino_game_title",
    "_casino_keno_draw",
    "_casino_keno_multiplier_text",
    "_casino_keno_normalize_session",
    "_casino_keno_payout_multiplier",
    "_casino_keno_start",
    "_casino_keno_toggle_pick",
    "_casino_holdem_resolve",
    "_casino_holdem_start",
    "_casino_plinko_resolve",
    "_casino_roulette_normalize_session",
    "_casino_roulette_resolve",
    "_casino_roulette_start",
    "_casino_round_seed",
    "_casino_slot_round_contract",
    "_casino_slots_resolve",
    "_casino_table_context",
    "_casino_table_context_summary",
    "_casino_three_bones_market_from_key",
    "_casino_three_bones_market_order",
    "_casino_three_bones_normalize_session",
    "_casino_three_bones_remove_bet",
    "_casino_three_bones_resolve",
    "_casino_three_bones_stage_bet",
    "_casino_three_bones_start",
    "_casino_three_bright_market_from_key",
    "_casino_three_bright_market_order",
    "_casino_three_bright_normalize_session",
    "_casino_three_bright_remove_bet",
    "_casino_three_bright_resolve",
    "_casino_three_bright_stage_bet",
    "_casino_three_bright_start",
    "_casino_bloom_cards_cashout",
    "_casino_bloom_cards_grow",
    "_casino_bloom_cards_normalize_session",
    "_casino_bloom_cards_score",
    "_casino_bloom_cards_start",
    "_casino_three_card_poker_normalize_session",
    "_casino_three_card_poker_resolve",
    "_casino_three_card_poker_start",
    "_casino_twenty_one_action_ids",
    "_casino_twenty_one_normalize_session",
    "_casino_twenty_one_resolve",
    "_casino_twenty_one_start",
    "_casino_video_poker_draw",
    "_casino_video_poker_normalize_session",
    "_casino_video_poker_start",
    "_casino_video_poker_toggle_hold",
    "_chunk_site_kinds",
    "_coach_transit_destinations",
    "_coach_transit_payment_profile",
    "_coach_transit_quote",
    "_coach_transit_travel_ticks",
    "_clamp",
    "_credit_amount_label",
    "_int_or_default",
    "_line_text",
    "_manhattan",
    "_overworld_discovery_profile",
    "_overworld_discovery_summary_bits",
    "_overworld_legend_line",
    "_overworld_render_style",
    "_bus_transit_destinations",
    "_bus_transit_payment_profile",
    "_bus_transit_quote",
    "_bus_transit_travel_ticks",
    "_ferry_transit_destinations",
    "_ferry_transit_payment_profile",
    "_ferry_transit_quote",
    "_ferry_transit_travel_ticks",
    "_rail_transit_destinations",
    "_rail_transit_payment_profile",
    "_rail_transit_quote",
    "_rail_transit_travel_ticks",
    "_shuttle_transit_destinations",
    "_shuttle_transit_payment_profile",
    "_shuttle_transit_quote",
    "_shuttle_transit_travel_ticks",
    "_transit_fare_label",
    "_transit_inventory_label",
    "_transit_services_connecting_chunks",
    "_transit_payment_profile",
    "_transit_quote",
    "_transit_service_log_prefix",
    "_transit_service_mode_label",
    "_transit_service_profile",
    "_transit_service_title",
    "_transit_token_amount_label",
    "_transit_travel_ticks",
    "_overworld_travel_profile",
    "_overworld_travel_summary_bits",
    "_sentence_from_note",
    "_service_menu_option_label",
    "_site_service_label",
    "_site_service_roll_index",
    "_site_service_state",
    "_storefront_service_profile",
    "_tick_duration_label",
    "_vehicle_sale_lookup_offer",
    "_vehicle_sale_offer_label",
    "_vehicle_sale_offers",
    "_vehicle_sale_quality",
    "_vehicle_sale_quality_title",
    "_vehicle_sale_remove_offer",
    "_vehicle_sale_stats_text",
]
