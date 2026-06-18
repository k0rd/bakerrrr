"""Shared helpers for explicit vehicle quick-travel entrance ramps."""

from __future__ import annotations


QUICK_TRAVEL_RAMP_ARCHETYPE = "quick_travel_ramp"
QUICK_TRAVEL_RAMP_GLYPH = "R"
LOCAL_ROUTE_GLYPHS = {"=", ":"}
QUICK_TRAVEL_RAMP_INTERACT_RADIUS = 3


def map_mode_active(sim) -> bool:
    """Return True when local-mode player interactions should be suspended."""

    return str(getattr(sim, "zoom_mode", "city") or "city").strip().lower() == "overworld"


def local_interactions_suspended_for_actor(sim, eid) -> bool:
    """Return True when local-mode interactions should ignore this actor."""

    if eid is None or not map_mode_active(sim):
        return False
    player_eid = getattr(sim, "player_eid", None)
    try:
        return int(eid) == int(player_eid)
    except (TypeError, ValueError):
        return eid == player_eid


def _property_metadata(prop) -> dict:
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def property_allows_vehicle_route_access(prop) -> bool:
    metadata = _property_metadata(prop)
    return bool(metadata.get("quick_travel_access") or metadata.get("vehicle_route_access"))


def is_quick_travel_ramp_property(prop) -> bool:
    metadata = _property_metadata(prop)
    if not bool(metadata.get("quick_travel_access")):
        return False
    archetype = str(metadata.get("archetype", "") or "").strip().lower()
    fixture_type = str(metadata.get("fixture_type", "") or "").strip().lower()
    return QUICK_TRAVEL_RAMP_ARCHETYPE in {archetype, fixture_type}


def quick_travel_ramp_properties_at(sim, x, y, z=0):
    try:
        key = (int(x), int(y), int(z))
    except (TypeError, ValueError):
        return ()
    properties = getattr(sim, "properties", {})
    anchor_index = getattr(sim, "property_anchor_index", {})
    matched = []
    for property_id in tuple(anchor_index.get(key, ()) or ()):
        prop = properties.get(property_id)
        if is_quick_travel_ramp_property(prop):
            matched.append(prop)
    return tuple(matched)


def quick_travel_ramp_at(sim, x, y, z=0):
    ramps = quick_travel_ramp_properties_at(sim, x, y, z)
    return ramps[0] if ramps else None


def quick_travel_ramp_near(sim, x, y, z=0, *, radius=QUICK_TRAVEL_RAMP_INTERACT_RADIUS):
    try:
        px = int(x)
        py = int(y)
        pz = int(z)
        search_radius = max(0, int(radius))
    except (TypeError, ValueError):
        return None

    candidates = []
    seen_ids = set()
    for dy in range(-search_radius, search_radius + 1):
        max_dx = search_radius - abs(dy)
        for dx in range(-max_dx, max_dx + 1):
            rx = px + dx
            ry = py + dy
            for prop in quick_travel_ramp_properties_at(sim, rx, ry, pz):
                prop_id = str(prop.get("id", ""))
                if prop_id in seen_ids:
                    continue
                seen_ids.add(prop_id)
                distance = abs(int(prop.get("x", rx)) - px) + abs(int(prop.get("y", ry)) - py)
                candidates.append((distance, int(prop.get("y", ry)), int(prop.get("x", rx)), prop_id, prop))
    if not candidates:
        return None
    candidates.sort(key=lambda row: row[:4])
    return candidates[0][4]


def _route_tile_candidates(sim, origin_x, origin_y, chunk_size):
    candidates = []
    size = int(max(8, chunk_size))
    for y in range(int(origin_y), int(origin_y) + size):
        for x in range(int(origin_x), int(origin_x) + size):
            tile = sim.tilemap.tile_at(x, y, 0)
            glyph = str(getattr(tile, "glyph", "") or "")[:1]
            if glyph not in LOCAL_ROUTE_GLYPHS:
                continue
            if not bool(getattr(tile, "walkable", False)):
                continue
            if sim.structure_at(x, y, 0) is not None:
                continue
            if sim.property_at(x, y, 0) is not None:
                continue
            candidates.append((int(x), int(y), glyph))
    return candidates


def _edge_distance(x, y, origin_x, origin_y, chunk_size):
    left = int(x) - int(origin_x)
    top = int(y) - int(origin_y)
    right = int(origin_x) + int(chunk_size) - 1 - int(x)
    bottom = int(origin_y) + int(chunk_size) - 1 - int(y)
    return min(left, right, top, bottom)


def generate_quick_travel_ramp_records(sim, chunk, rng, origin_x, origin_y, chunk_size, *, max_count=2):
    """Generate deterministic nonblocking ramp asset records for a realized chunk."""

    del rng
    if not isinstance(chunk, dict):
        return []
    candidates = _route_tile_candidates(sim, origin_x, origin_y, chunk_size)
    if not candidates:
        return []

    cx = int(chunk.get("cx", 0) or 0)
    cy = int(chunk.get("cy", 0) or 0)
    seed = f"{getattr(sim, 'seed', 0)}:{cx}:{cy}:quick-travel-ramps"
    import random

    chooser = random.Random(seed)
    chooser.shuffle(candidates)
    candidates.sort(key=lambda row: (_edge_distance(row[0], row[1], origin_x, origin_y, chunk_size), row[1], row[0]))

    target_count = 1 if len(candidates) < max(12, int(chunk_size) // 2) else min(2, int(max_count))
    min_separation = max(5, int(chunk_size) // 3)
    selected = []
    for candidate in candidates:
        x, y, _glyph = candidate
        if any(abs(x - sx) + abs(y - sy) < min_separation for sx, sy, _sglyph in selected):
            continue
        selected.append(candidate)
        if len(selected) >= target_count:
            break
    if not selected and candidates:
        selected.append(candidates[0])

    records = []
    for index, (x, y, glyph) in enumerate(selected):
        route_kind = "trail" if glyph == ":" else "road"
        records.append(
            {
                "name": "Entrance Ramp",
                "kind": "asset",
                "x": int(x),
                "y": int(y),
                "z": 0,
                "owner_tag": "city",
                "metadata": {
                    "archetype": QUICK_TRAVEL_RAMP_ARCHETYPE,
                    "fixture_type": QUICK_TRAVEL_RAMP_ARCHETYPE,
                    "asset_type": QUICK_TRAVEL_RAMP_ARCHETYPE,
                    "display_glyph": QUICK_TRAVEL_RAMP_GLYPH,
                    "display_color": "transit" if route_kind == "trail" else "terrain_road",
                    "quick_travel_access": True,
                    "vehicle_route_access": True,
                    "route_kind": route_kind,
                    "chunk": (cx, cy),
                    "ramp_index": int(index),
                },
            }
        )
    return records
