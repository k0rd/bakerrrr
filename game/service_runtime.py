"""Shared casino and service runtime helpers.

This module holds the shared service-stack behavior that used to live inside
``game/systems.py`` so the extracted service systems can depend on a focused
runtime seam instead of reaching back into the monolith.
"""

import curses
import itertools
import random
from collections import Counter

from engine.buildings import layout_chunk_building, world_building_id
from engine.sites import layout_chunk_site
from game.components import AI, CreatureIdentity, NPCNeeds, Occupation, PlayerAssets, Position
from game.organizations import occupation_targets_property, property_org_members
from game.population import work_shift_active
from game.property_runtime import (
    property_covering as _property_covering,
    property_focus_position as _property_focus_position,
    property_is_storefront as _property_is_storefront,
    storefront_service_mode as _storefront_service_mode,
)
from game.vehicles import roll_vehicle_paint_key, roll_vehicle_profile


def _int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _manhattan(ax, ay, bx, by):
    return abs(ax - bx) + abs(ay - by)


def _clamp(value, lo=0.0, hi=100.0):
    return max(lo, min(hi, value))


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
SHUTTLE_TRANSIT_TOKEN_DISTANCE_STEP = 2
FERRY_TRANSIT_SEARCH_RADIUS = 10
FERRY_TRANSIT_MENU_LIMIT = 6
FERRY_TRANSIT_TOKEN_DISTANCE_STEP = 2

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

    for prop in tuple(getattr(sim, "properties", {}).values()):
        if not isinstance(prop, dict):
            continue
        if _property_chunk(sim, prop) != chunk:
            continue
        if service in _property_service_ids(prop):
            return True
        if _property_transit_archetype(prop) in node_archetypes:
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
    distance = _manhattan(origin_chunk[0], origin_chunk[1], target_chunk[0], target_chunk[1])
    if distance <= 0:
        return ()
    requested = tuple(services or TRANSIT_SERVICE_IDS)
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
        connected.append(str(service).strip().lower())
    return tuple(connected)


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
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            distance = _manhattan(0, 0, dx, dy)
            if distance <= 0 or distance > radius:
                continue
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

    candidates.sort(
        key=lambda row: (
            int(row.get("distance", 9999)),
            str(row.get("destination_name", "")).strip().lower(),
            tuple(row.get("chunk", (0, 0))),
            str(row.get("node_id", "")).strip().lower(),
        )
    )
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


def _rail_transit_quote(distance, *, price_mult=1.0):
    return _transit_quote("rail_transit", distance, price_mult=price_mult)


def _bus_transit_quote(distance, *, price_mult=1.0):
    return _transit_quote("bus_transit", distance, price_mult=price_mult)


def _shuttle_transit_quote(distance, *, price_mult=1.0):
    return _transit_quote("shuttle_transit", distance, price_mult=price_mult)


def _ferry_transit_quote(distance, *, price_mult=1.0):
    return _transit_quote("ferry_transit", distance, price_mult=price_mult)


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


def _rail_transit_travel_ticks(sim, distance):
    return _transit_travel_ticks(sim, "rail_transit", distance)


def _bus_transit_travel_ticks(sim, distance):
    return _transit_travel_ticks(sim, "bus_transit", distance)


def _shuttle_transit_travel_ticks(sim, distance):
    return _transit_travel_ticks(sim, "shuttle_transit", distance)


def _ferry_transit_travel_ticks(sim, distance):
    return _transit_travel_ticks(sim, "ferry_transit", distance)


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
    "industrial": "guard",
    "residential": "human",
    "downtown": "player",
    "slums": "cat_purple",
    "corporate": "avian",
    "military": "guard",
    "entertainment": "cat_orange",
}
OVERWORLD_AREA_COLORS = {
    "city": "human",
    "frontier": "cat_tabby",
    "wilderness": "insect",
    "coastal": "avian",
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
    "urban": "human",
    "park": "insect",
    "industrial_waste": "guard",
    "scrub": "cat_tabby",
    "plains": "human",
    "badlands": "cat_orange",
    "hills": "guard",
    "forest": "insect",
    "marsh": "insect",
    "shore": "avian",
    "shoals": "avian",
    "dunes": "cat_orange",
    "cliffs": "guard",
    "salt_flats": "cat_gray",
    "lake": "avian",
    "ruins": "cat_purple",
}
OVERWORLD_PATH_GLYPHS = {
    "freeway": "#",
    "road": "=",
    "trail": ":",
}
OVERWORLD_PATH_COLORS = {
    "freeway": "player",
    "road": "human",
    "trail": "cat_tabby",
}


def _overworld_render_style(sim, cx, cy):
    desc = sim.world.overworld_descriptor(cx, cy)
    area_type = str(desc.get("area_type", "city")).strip().lower() or "city"
    district_type = str(desc.get("district_type", "unknown")).strip().lower() or "unknown"
    terrain_key = str(desc.get("terrain", "plain")).strip().lower() or "plain"
    path = str(desc.get("path", "")).strip().lower()
    landmark_here = desc.get("landmark")
    interest = sim.world.overworld_interest(cx, cy, descriptor=desc)

    if isinstance(landmark_here, dict) and landmark_here.get("glyph"):
        glyph = str(landmark_here.get("glyph", "*"))[:1] or "*"
        color = landmark_here.get("color", "human")
    elif interest.get("show_on_map") and interest.get("glyph"):
        glyph = str(interest.get("glyph", "?"))[:1] or "?"
        color = str(interest.get("color", "human") or "human")
    elif path:
        glyph = OVERWORLD_PATH_GLYPHS.get(path, "=")
        color = OVERWORLD_PATH_COLORS.get(path, "human")
    elif area_type == "city":
        if (cx, cy) in sim.world.loaded_chunks:
            glyph = OVERWORLD_DISTRICT_GLYPHS.get(district_type, "X")
            color = OVERWORLD_DISTRICT_COLORS.get(district_type, "human")
        else:
            glyph = OVERWORLD_AREA_GLYPHS.get("city", "X")
            color = OVERWORLD_AREA_COLORS.get("city", "human")
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
        glyph = str(glyph).upper() if (cx, cy) in sim.world.loaded_chunks else str(glyph).lower()
    return glyph, color


def _overworld_legend_line(sim, cx, cy, text):
    glyph, color = _overworld_render_style(sim, cx, cy)
    return _legend_line(text, glyph=glyph, color=color, attrs=getattr(curses, "A_BOLD", 0))


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


def _entity_display_name(sim, eid, title_case=False):
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    ai = sim.ecs.get(AI).get(eid)

    if identity:
        label = str(identity.display_name()).replace("_", " ").strip()
    elif ai:
        label = str(ai.role or "entity").replace("_", " ").strip()
    else:
        label = "entity"

    if not label:
        label = "entity"
    return label.title() if title_case else label


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
    if covered and covered.get("id") == prop.get("id") and dist <= 3:
        return True, dist
    return False, dist


def _storefront_service_profile(sim, prop):
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
        actor_eid = member.get("eid")
        occupation = member.get("occupation")
        existing = candidates_by_eid.get(actor_eid)
        role = "owner" if actor_eid == owner_eid else str(member.get("role", "") or "").strip().lower()
        if role not in {"owner", "manager", "staff"}:
            role = _occupation_service_role(occupation)
        if existing and existing.get("role") == "owner":
            continue
        candidates_by_eid[actor_eid] = {
            "eid": actor_eid,
            "role": role,
            "occupation": occupation,
            "source": member.get("source", "workplace"),
        }

    available = []
    for info in candidates_by_eid.values():
        actor_eid = info["eid"]
        present, distance = _actor_in_storefront_service_zone(sim, actor_eid, prop)
        occupation = info.get("occupation")
        ai = ais.get(actor_eid)
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
        available.append((info["role"], distance, actor_eid))

    if available:
        available.sort(key=lambda row: (_storefront_service_role_priority(row[0]), row[1], row[2]))
        service_role, _distance, service_eid = available[0]
        service_name = _entity_display_name(sim, service_eid, title_case=True)
        profile.update({
            "mode": "staffed",
            "available": True,
            "service_eid": service_eid,
            "service_name": service_name,
            "service_role": service_role,
            "service_note": f"served by {service_name}" if service_name else "counter service",
            "summary_label": f"counter:{service_name}" if service_name else "counter",
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
CASINO_SLOT_REELS = (
    ("CHERRY", "LEMON", "BAR", "HORSESHOE", "BELL", "CHERRY", "BAR", "SEVEN", "LEMON", "BAR", "BELL", "SEVEN"),
    ("BAR", "CHERRY", "BELL", "LEMON", "BAR", "HORSESHOE", "SEVEN", "CHERRY", "BAR", "BELL", "LEMON", "SEVEN"),
    ("LEMON", "BAR", "CHERRY", "SEVEN", "BAR", "BELL", "CHERRY", "HORSESHOE", "BAR", "SEVEN", "LEMON", "BELL"),
)
CASINO_SLOT_SYMBOL_LABELS = {
    "CHERRY": "Cherry",
    "LEMON": "Lemon",
    "BAR": "Bar",
    "HORSESHOE": "Horseshoe",
    "BELL": "Bell",
    "SEVEN": "Seven",
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
CASINO_KENO_NUMBER_COUNT = 20
CASINO_KENO_DRAW_COUNT = 8
CASINO_KENO_MAX_PICKS = 5
CASINO_KENO_PAYOUT_MULTIPLIERS = {
    1: {1: 2},
    2: {2: 5},
    3: {2: 1, 3: 8},
    4: {2: 1, 3: 4, 4: 15},
    5: {3: 2, 4: 8, 5: 30},
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
        "title": "Slots",
        "service_label": "slots",
        "menu_label": "Play slots",
        "bet_options": (10, 25, 50),
        "prompt": "Pick a stake and let the reels fly.",
        "note": "Three reels, classic symbols, and a loud machine when the sevens land.",
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
        "note": "Quick-draw house keno uses a 20-number board, one ticket, and one fast reveal.",
        "social_gain": (1, 3),
    },
    "roulette": {
        "title": "Roulette",
        "service_label": "roulette",
        "menu_label": "Play roulette",
        "bet_options": (10, 25, 50),
        "prompt": "Post a chip, pick a pocket or an outside section, and let the wheel spin.",
        "note": "Single-zero house wheel with straight-up numbers, colors, parity, ranges, dozens, and columns.",
        "social_gain": (1, 4),
    },
    "craps": {
        "title": "Craps",
        "service_label": "craps",
        "menu_label": "Play craps",
        "bet_options": (10, 25, 50),
        "prompt": "Post a chip, choose pass line, don't pass, or field, and let the dice run.",
        "note": "Pass line and don't pass auto-play through the point; field is a one-roll side action.",
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
    "twenty_one": {
        "title": "21",
        "service_label": "21",
        "menu_label": "Play 21",
        "bet_options": (10, 25, 50),
        "prompt": "Pick a wager and play a real hand against the dealer.",
        "note": "Hit, stand, and hope the house runs cold.",
        "social_gain": (2, 4),
    },
}
CASINO_GAME_SERVICE_IDS = frozenset(CASINO_GAME_PROFILES)


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

    return {
        "service": "video_poker",
        "wager": int(current["wager"]),
        "stake": int(current["stake"]),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": detail,
        "summary": f"Final hand {_casino_cards_text(cards)} ({hand_name}). {headline}",
        "result_lines": [
            f"Final hand: {_casino_cards_text(cards)}",
            hold_line,
            draw_line,
            f"Made: {hand_name}.",
            detail,
        ],
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
        "property_id": session.get("property_id"),
        "property_name": str(session.get("property_name", "")).strip(),
    }


def _casino_keno_start(seed_token, wager):
    return {
        "service": "keno",
        "seed_token": str(seed_token),
        "wager": int(wager),
        "stake": int(wager),
        "picks": [],
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
    return current


def _casino_keno_outcome_text(pick_count, hit_count, payout_mult):
    if int(payout_mult) <= 0:
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
    payout_mult = int(CASINO_KENO_PAYOUT_MULTIPLIERS.get(pick_count, {}).get(hit_count, 0))
    payout = int(max(0, payout_mult) * int(current.get("wager", 0)))
    headline, detail = _casino_keno_outcome_text(pick_count, hit_count, payout_mult)

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
        "result_lines": [
            f"Ticket: {' '.join(f'{number:02d}' for number in picks)}",
            f"Draw: {' '.join(f'{number:02d}' for number in drawn_numbers)}",
            (
                f"Hits: {' '.join(f'{number:02d}' for number in hit_numbers)} "
                f"({hit_count}/{pick_count})."
                if hit_numbers
                else f"Hits: none (0/{pick_count})."
            ),
            (
                f"Pay table: x{payout_mult} on {hit_count} hit{'s' if hit_count != 1 else ''}."
                if payout_mult > 0
                else "Pay table: no return on this miss."
            ),
            detail,
        ],
        "picked_numbers": picks,
        "drawn_numbers": drawn_numbers,
        "hit_numbers": hit_numbers,
        "pick_count": int(pick_count),
        "hit_count": int(hit_count),
        "payout_mult": int(payout_mult),
        "social_gain": _casino_social_gain("keno", f"{current['seed_token']}:{pick_count}:{hit_count}"),
        "stake_already_paid": True,
    }


def _casino_roulette_normalize_session(session):
    if not isinstance(session, dict):
        return None
    view = str(session.get("view", "board") or "board").strip().lower()
    if view not in {"board", "numbers"}:
        view = "board"
    return {
        "service": "roulette",
        "seed_token": str(session.get("seed_token", "")).strip(),
        "wager": int(session.get("wager", 0)),
        "stake": int(session.get("stake", session.get("wager", 0))),
        "view": view,
        "property_id": session.get("property_id"),
        "property_name": str(session.get("property_name", "")).strip(),
    }


def _casino_roulette_start(seed_token, wager):
    return {
        "service": "roulette",
        "seed_token": str(seed_token),
        "wager": int(wager),
        "stake": int(wager),
        "view": "board",
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


def _casino_roulette_resolve(session, bet_kind, bet_value=None):
    current = _casino_roulette_normalize_session(session)
    if not current:
        return None

    kind = str(bet_kind or "").strip().lower()
    label = _casino_roulette_bet_label(kind, bet_value)
    spin_rng = random.Random(f"{current['seed_token']}:roulette")
    spin_number = spin_rng.randint(0, CASINO_ROULETTE_NUMBER_MAX)
    spin_color = _casino_roulette_color(spin_number)
    hit = _casino_roulette_bet_hits(spin_number, kind, bet_value)
    payout_mult = _casino_roulette_payout_multiplier(kind) if hit else 0
    payout = int(max(0, payout_mult) * int(current.get("wager", 0)))

    if hit and kind == "straight":
        headline = "Straight-up hit."
        detail = "The ball dives straight into your pocket and the croupier builds a towering payout."
        outcome_key = "straight"
    elif hit and kind in {"dozen", "column"}:
        headline = "Section hit."
        detail = "Your section covers the winning pocket and the layout pays 2 to 1."
        outcome_key = kind
    elif hit:
        headline = "Even-money hit."
        detail = "Your outside bet catches the winner and the table pays even money."
        outcome_key = kind
    elif spin_number == 0 and kind != "straight":
        headline = "Zero sweeps the board."
        detail = "The ball settles on 0 green and wipes out the outside action."
        outcome_key = "zero"
    else:
        headline = "No hit."
        detail = "The ball lands away from your mark and the house keeps the chip."
        outcome_key = "miss"

    return {
        "service": "roulette",
        "wager": int(current["wager"]),
        "stake": int(current["stake"]),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": detail,
        "summary": f"Spin {spin_number:02d} {spin_color}. Bet {label}. {headline}",
        "result_lines": [
            f"Spin: {spin_number:02d} {spin_color.title()}",
            f"Bet: {label}",
            (
                f"Payout: x{payout_mult} gross return."
                if payout_mult > 0
                else "Payout: no return on this spin."
            ),
            detail,
        ],
        "spin_number": int(spin_number),
        "spin_color": str(spin_color),
        "bet_kind": kind,
        "bet_value": bet_value,
        "bet_label": label,
        "payout_mult": int(payout_mult),
        "social_gain": _casino_social_gain("roulette", f"{current['seed_token']}:{kind}:{spin_number}:{outcome_key}"),
        "stake_already_paid": True,
    }


def _casino_craps_normalize_session(session):
    if not isinstance(session, dict):
        return None
    view = str(session.get("view", "layout") or "layout").strip().lower()
    if view not in {"layout", "pass_odds", "dont_pass_odds", "place", "hardways", "props"}:
        view = "layout"
    return {
        "service": "craps",
        "seed_token": str(session.get("seed_token", "")).strip(),
        "wager": int(session.get("wager", 0)),
        "stake": int(session.get("stake", session.get("wager", 0))),
        "view": view,
        "property_id": session.get("property_id"),
        "property_name": str(session.get("property_name", "")).strip(),
    }


def _casino_craps_start(seed_token, wager):
    return {
        "service": "craps",
        "seed_token": str(seed_token),
        "wager": int(wager),
        "stake": int(wager),
        "view": "layout",
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


def _casino_craps_resolve(session, bet_kind, bet_value=None):
    current = _casino_craps_normalize_session(session)
    if not current:
        return None

    kind = str(bet_kind or "").strip().lower()
    if kind not in {"pass", "dont_pass", "field", "pass_odds", "dont_pass_odds", "place", "hardway", "prop"}:
        return None

    roll_rng = random.Random(f"{current['seed_token']}:craps")
    rolls = []

    def take_roll():
        die_one, die_two, total = _casino_craps_roll_pair(roll_rng)
        roll = {
            "die_one": int(die_one),
            "die_two": int(die_two),
            "total": int(total),
        }
        rolls.append(roll)
        return roll

    bet_label = _casino_craps_bet_label(kind, bet_value)
    wager = int(current.get("wager", 0))
    stake = int(current.get("stake", wager))
    odds_stake = max(0, stake - wager)
    point_number = 0
    payout = 0
    payout_mult = 0
    outcome_key = "miss"
    headline = "No hit."
    detail = "The table turns against you and the house keeps the chip."
    lines = [f"Bet: {bet_label}"]

    if kind in {"pass", "dont_pass", "field", "pass_odds", "dont_pass_odds"}:
        come_out = take_roll()
        come_out_total = int(come_out["total"])
        lines.append(f"Come-out: {_casino_craps_roll_text(come_out)}")

        if kind == "field":
            if come_out_total in {2, 12}:
                payout_mult = 3
                payout = int(payout_mult * wager)
                outcome_key = "field_double"
                headline = "Field cracks loud."
                detail = "The dice hit the rare edge of the field and the box pays double."
            elif come_out_total in {3, 4, 9, 10, 11}:
                payout_mult = 2
                payout = int(payout_mult * wager)
                outcome_key = "field_win"
                headline = "Field hit."
                detail = "The roll lands inside the field and the table pays even money."
            else:
                outcome_key = "field_miss"
                headline = "Field miss."
                detail = "The roll lands in the dead middle and the field bet goes dark."
            lines.append("Field pays even on 3, 4, 9, 10, and 11; 2 and 12 pay double.")
        else:
            pass_side = kind in {"pass", "pass_odds"}
            odds_kind = kind in {"pass_odds", "dont_pass_odds"}
            if odds_kind:
                try:
                    odds_mult = max(1, int(bet_value))
                except (TypeError, ValueError):
                    odds_mult = 1
                required_odds = wager * odds_mult
                if odds_stake < required_odds:
                    return None
                odds_stake = required_odds
                lines.append(
                    f"Odds: {odds_mult}x behind the line ({_credit_amount_label(odds_stake)} reserved)."
                )
                lines.append("True-odds pays are rounded to the nearest credit when the ratio lands off-grid.")

            if pass_side and come_out_total in {7, 11}:
                payout = int(wager * 2) + int(odds_stake)
                outcome_key = "pass_natural_odds" if odds_kind else "pass_natural"
                headline = "Natural winner."
                detail = (
                    "Seven or eleven on the come-out pays the pass line, and any reserved odds chips come right back."
                    if odds_kind
                    else "Seven or eleven on the come-out and the pass line pays instantly."
                )
            elif pass_side and come_out_total in {2, 3, 12}:
                payout = int(odds_stake)
                outcome_key = "pass_craps_odds" if odds_kind else "pass_craps"
                headline = "Craps on the come-out."
                detail = (
                    "The shooter throws craps, so the pass line loses and the reserved odds chips are returned untouched."
                    if odds_kind
                    else "The shooter throws craps and the pass line loses before a point is set."
                )
            elif (not pass_side) and come_out_total in {2, 3}:
                payout = int(wager * 2) + int(odds_stake)
                outcome_key = "dont_pass_win_odds" if odds_kind else "dont_pass_win"
                headline = "Don't pass connects."
                detail = (
                    "The shooter opens with craps, so the don't pass line wins and any reserved odds come back untouched."
                    if odds_kind
                    else "The shooter opens with craps and the don't pass side gets paid."
                )
            elif (not pass_side) and come_out_total in {7, 11}:
                payout = int(odds_stake)
                outcome_key = "dont_pass_lose_odds" if odds_kind else "dont_pass_lose"
                headline = "Natural against you."
                detail = (
                    "Seven or eleven on the come-out burns the don't pass line, but the reserved odds chips come back."
                    if odds_kind
                    else "Seven or eleven on the come-out burns the don't pass bet."
                )
            elif (not pass_side) and come_out_total == 12:
                payout = int(wager) + int(odds_stake)
                outcome_key = "dont_pass_push_odds" if odds_kind else "dont_pass_push"
                headline = "Bar twelve push."
                detail = (
                    "Twelve shows on the come-out, so the don't pass line pushes and the reserved odds chips are returned."
                    if odds_kind
                    else "Twelve shows on the come-out, so the don't pass bet pushes."
                )
            else:
                point_number = int(come_out_total)
                lines.append(f"Point: {point_number}")
                for _ in range(CASINO_CRAPS_MAX_POINT_ROLLS):
                    roll = take_roll()
                    total = int(roll["total"])
                    if pass_side and total == point_number:
                        payout = int(wager * 2)
                        if odds_kind and odds_stake > 0:
                            odds_profit = _casino_craps_odds_profit(point_number, odds_stake, lay=False)
                            payout += int(odds_stake + odds_profit)
                            outcome_key = "pass_point_odds"
                            headline = "Point made with odds."
                            detail = "The shooter hits the point, so both the line and the true-odds bet get paid."
                        else:
                            outcome_key = "pass_point"
                            headline = "Point made."
                            detail = "The shooter hits the point before sevening out and the pass line gets paid."
                        break
                    if total == 7:
                        if pass_side:
                            outcome_key = "seven_out_odds" if odds_kind else "seven_out"
                            headline = "Seven out."
                            detail = (
                                "A seven shows before the point comes back, so both the line and odds fall."
                                if odds_kind
                                else "A seven shows before the point comes back and the pass line goes down."
                            )
                        else:
                            payout = int(wager * 2)
                            if odds_kind and odds_stake > 0:
                                odds_profit = _casino_craps_odds_profit(point_number, odds_stake, lay=True)
                                payout += int(odds_stake + odds_profit)
                                outcome_key = "dont_pass_seven_odds"
                                headline = "Seven out pays the dark side."
                                detail = "The shooter sevens out before the point returns, so the don't pass line and odds both cash."
                            else:
                                outcome_key = "dont_pass_seven"
                                headline = "Seven out pays."
                                detail = "The shooter sevens out before the point returns and the don't pass side wins."
                        break
                    if (not pass_side) and total == point_number:
                        outcome_key = "dont_pass_point_odds" if odds_kind else "dont_pass_point"
                        headline = "Point repeats."
                        detail = (
                            "The point comes back first, so the don't pass line and odds both lose."
                            if odds_kind
                            else "The point comes back first, so the don't pass bet loses."
                        )
                        break
                else:
                    return None
                lines.append("After point: " + " -> ".join(_casino_craps_roll_text(roll) for roll in rolls[1:]))
    elif kind == "place":
        try:
            target_number = int(bet_value)
        except (TypeError, ValueError):
            target_number = 0
        if target_number not in {4, 5, 6, 8, 9, 10}:
            return None
        for _ in range(CASINO_CRAPS_MAX_POINT_ROLLS):
            roll = take_roll()
            total = int(roll["total"])
            if total == target_number:
                profit = _casino_craps_place_profit(target_number, wager)
                payout = int(wager + profit)
                outcome_key = f"place_{target_number}_hit"
                headline = "Place number hits."
                detail = f"Your place {target_number} lands before seven, so the box pays the bet."
                break
            if total == 7:
                outcome_key = "place_seven_out"
                headline = "Seven sweeps the place bet."
                detail = "A seven shows before your number and the place chip is gone."
                break
        else:
            return None
        lines.append("Rolls: " + " -> ".join(_casino_craps_roll_text(roll) for roll in rolls))
        lines.append("Place pays 9:5 on 4/10, 7:5 on 5/9, and 7:6 on 6/8, rounded to the nearest credit.")
    elif kind == "hardway":
        try:
            target_number = int(bet_value)
        except (TypeError, ValueError):
            target_number = 0
        if target_number not in {4, 6, 8, 10}:
            return None
        target_face = target_number // 2
        for _ in range(CASINO_CRAPS_MAX_POINT_ROLLS):
            roll = take_roll()
            total = int(roll["total"])
            die_one = int(roll["die_one"])
            die_two = int(roll["die_two"])
            if total == 7:
                outcome_key = "hardway_seven_out"
                headline = "Seven out kills the hardway."
                detail = "A seven shows before the doubles arrive, and the hardway chip disappears."
                break
            if total == target_number and die_one == target_face and die_two == target_face:
                payout_mult = 10 if target_number in {6, 8} else 8
                payout = int(wager * payout_mult)
                outcome_key = f"hard_{target_number}_hit"
                headline = "Hardway lands."
                detail = f"The dice pair up on hard {target_number} before an easy way or seven shows."
                break
            if total == target_number:
                outcome_key = f"easy_{target_number}"
                headline = "Easy way breaks it."
                detail = f"The number shows the easy way before the doubles, so the hardway loses."
                break
        else:
            return None
        lines.append("Rolls: " + " -> ".join(_casino_craps_roll_text(roll) for roll in rolls))
        lines.append("Hard 4/10 pays 7:1; hard 6/8 pays 9:1.")
    else:
        value = str(bet_value or "").strip().lower()
        prop_totals = {
            "2": {2},
            "3": {3},
            "11": {11},
            "12": {12},
            "any_craps": {2, 3, 12},
            "any_seven": {7},
        }
        gross_payouts = {
            "2": 31,
            "3": 16,
            "11": 16,
            "12": 31,
            "any_craps": 8,
            "any_seven": 5,
        }
        winning_totals = prop_totals.get(value)
        if not winning_totals:
            return None
        roll = take_roll()
        total = int(roll["total"])
        lines.append(f"Roll: {_casino_craps_roll_text(roll)}")
        if total in winning_totals:
            payout_mult = int(gross_payouts.get(value, 0))
            payout = int(wager * payout_mult)
            outcome_key = f"prop_{value}_hit"
            headline = "Center action hits."
            detail = "The one-roll proposition lands clean and the center of the table pays loud."
        else:
            outcome_key = f"prop_{value}_miss"
            headline = "Prop misses."
            detail = "The one-roll shot misses and the center action is gone."

    roll_totals = tuple(int(roll.get("total", 0)) for roll in rolls)
    roll_pairs = tuple((int(roll.get("die_one", 0)), int(roll.get("die_two", 0))) for roll in rolls)
    result_lines = list(lines)
    if payout_mult > 0:
        result_lines.append(f"Payout: x{payout_mult} gross return.")
    elif payout > 0:
        result_lines.append(f"Payout: {_credit_amount_label(payout)} returned.")
    else:
        result_lines.append("Payout: no return on this hand.")
    result_lines.append(detail)

    return {
        "service": "craps",
        "wager": int(wager),
        "stake": int(stake),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": detail,
        "summary": (
            f"{bet_label}"
            + (
                f" with come-out {roll_totals[0]}"
                if roll_totals and kind in {"pass", "dont_pass", "field", "pass_odds", "dont_pass_odds"}
                else ""
            )
            + (f", point {point_number}" if point_number > 0 else "")
            + f". {headline}"
        ),
        "result_lines": result_lines,
        "bet_kind": kind,
        "bet_value": bet_value,
        "bet_label": bet_label,
        "come_out_total": int(roll_totals[0]) if roll_totals else 0,
        "point_number": int(point_number),
        "roll_totals": roll_totals,
        "roll_pairs": roll_pairs,
        "payout_mult": int(payout_mult),
        "odds_stake": int(odds_stake),
        "social_gain": _casino_social_gain("craps", f"{current['seed_token']}:{kind}:{bet_value}:{outcome_key}:{point_number}"),
        "stake_already_paid": True,
    }


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

    result_lines = [
        f"Bet: {bet_label}",
        f"Player: {_casino_cards_text(player_cards)} ({player_total})",
        f"Banker: {_casino_cards_text(banker_cards)} ({banker_total})",
        f"Winner: {winner_label}",
        payout_line if payout_line else "Payout: no return on this hand.",
    ]
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
        return {
            "service": "three_card_poker",
            "wager": int(wager),
            "stake": int(stake),
            "payout": 0,
            "outcome_key": "fold",
            "headline": "You fold the ante.",
            "detail": "The hand looks thin, so you slide the ante away and let the dealer keep it.",
            "summary": f"You fold {_casino_cards_text(player_cards)} ({player_hand_name}) and give up the ante.",
            "result_lines": [
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

    result_lines = [
        f"You: {_casino_cards_text(player_cards)} ({player_hand_name})",
        f"Dealer: {_casino_cards_text(dealer_cards)} ({dealer_hand_name})",
        "Dealer qualifies." if dealer_qualifies else "Dealer does not qualify (needs queen-high or better).",
    ]
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


def _casino_slots_resolve(seed_token, wager):
    reels = []
    spin_rng = random.Random(f"{seed_token}:slots")
    for strip in CASINO_SLOT_REELS:
        reels.append(str(strip[spin_rng.randrange(len(strip))]).strip().upper() or "BAR")
    counts = Counter(reels)
    payout_mult = 0.0
    outcome_key = "blank"
    headline = "Cold reels."
    detail = "The machine clacks through a dead spin and the house keeps the bet."
    if len(counts) == 1:
        symbol = reels[0]
        if symbol == "SEVEN":
            payout_mult = 8.0
            outcome_key = "jackpot"
            headline = "Triple sevens."
            detail = "All three reels land on sevens and the cabinet starts screaming."
        elif symbol == "BAR":
            payout_mult = 5.0
            outcome_key = "triple_bar"
            headline = "Triple bars."
            detail = "The bars line up cleanly and the hopper rattles out a chunky win."
        elif symbol == "BELL":
            payout_mult = 4.0
            outcome_key = "triple_bell"
            headline = "Bell line."
            detail = "Three bells ring together and the machine pays with gusto."
        elif symbol == "CHERRY":
            payout_mult = 3.0
            outcome_key = "triple_cherry"
            headline = "Cherry line."
            detail = "Three cherries roll through and the house coughs up a bright little prize."
        else:
            payout_mult = 2.0
            outcome_key = "triple_match"
            headline = "Full match."
            detail = "All three reels match for a tidy line hit."
    elif counts.get("CHERRY", 0) == 2:
        payout_mult = 1.4
        outcome_key = "double_cherry"
        headline = "Two cherries."
        detail = "A pair of cherries catches the payline and softens the swing."
    elif counts.get("CHERRY", 0) == 1 and counts.get("SEVEN", 0) == 1:
        payout_mult = 1.1
        outcome_key = "mixed_line"
        headline = "Mixed line."
        detail = "A cherry and a seven clip the line for a tiny kickback."

    payout = max(0, int(round(float(payout_mult) * float(wager))))
    reel_text = " | ".join(CASINO_SLOT_SYMBOL_LABELS.get(symbol, symbol.title()) for symbol in reels)
    return {
        "service": "slots",
        "wager": int(wager),
        "stake": int(wager),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": detail,
        "summary": f"Reels {reel_text}. {headline}",
        "result_lines": [
            f"Reels: {reel_text}",
            detail,
        ],
        "reels": tuple(reels),
        "social_gain": _casino_social_gain("slots", seed_token),
    }


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
    return {
        "service": "plinko",
        "wager": int(wager),
        "stake": int(wager),
        "payout": int(payout),
        "outcome_key": outcome_key,
        "headline": headline,
        "detail": detail,
        "summary": f"Lane {lane + 1} rides {' '.join(path)} into bucket {position + 1}. {headline}",
        "result_lines": [
            f"Drop lane {lane + 1}: {' '.join(path)}",
            f"Bucket {position + 1} pays x{payout_mult:.1f}.",
            detail,
        ],
        "drop_lane": int(lane),
        "bucket_index": int(position),
        "path": tuple(path),
        "social_gain": _casino_social_gain("plinko", seed_token),
    }


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

    result_lines = [_casino_blackjack_line("Dealer", current["dealer_cards"])]
    for row in hand_results:
        tags = []
        if row["split_origin"]:
            tags.append("split")
        if row["doubled"]:
            tags.append("double")
        suffix = f" [{', '.join(tags)}]" if tags else ""
        hand_label = f"Hand {row['index'] + 1}"
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
                "result_lines": [
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
        return {
            "service": "casino_holdem",
            "wager": int(wager),
            "stake": int(stake),
            "payout": 0,
            "outcome_key": "fold",
            "headline": "You fold the ante.",
            "detail": "The flop looks wrong, so you release the hand and leave the ante in the circle.",
            "summary": f"You fold after the flop and forfeit the {wager}c ante.",
            "result_lines": [
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

    result_lines = [
        f"Board: {board_text}",
        f"You: {_casino_cards_text(player_cards)} ({player_best['name']})",
        f"Dealer: {_casino_cards_text(dealer_cards)} ({dealer_best['name']})",
        "Dealer qualifies." if dealer_qualifies else "Dealer does not qualify (needs pair of 4s+).",
    ]
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
        "intel": "intel",
        "shelter": "shelter",
        "rest": "lodging",
        "vending": "snacks",
        "fuel": "fuel",
        "repair": "repair",
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
        "vending": "Buy a snack",
        "fuel": "Refuel vehicle",
        "repair": "Repair vehicle",
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
    "CASINO_PLINKO_LANE_COUNT",
    "TRANSIT_SERVICE_IDS",
    "_casino_apply_round_result",
    "_casino_baccarat_normalize_session",
    "_casino_baccarat_resolve",
    "_casino_baccarat_start",
    "_casino_blackjack_line",
    "_casino_blackjack_total",
    "_casino_cards_text",
    "_casino_craps_normalize_session",
    "_casino_craps_resolve",
    "_casino_craps_start",
    "_casino_game_profile",
    "_casino_game_title",
    "_casino_keno_draw",
    "_casino_keno_normalize_session",
    "_casino_keno_start",
    "_casino_keno_toggle_pick",
    "_casino_holdem_resolve",
    "_casino_holdem_start",
    "_casino_plinko_resolve",
    "_casino_roulette_normalize_session",
    "_casino_roulette_resolve",
    "_casino_roulette_start",
    "_casino_round_seed",
    "_casino_slots_resolve",
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
