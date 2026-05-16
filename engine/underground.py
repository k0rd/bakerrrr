"""Deterministic underground site planning for city chunks."""

from __future__ import annotations

from engine.buildings import layout_chunk_building, world_building_id
from engine.sites import site_entry_front_cell


UNDERGROUND_ACCESS_SERVICE = "underground_access"
METRO_UNDERPASS_KIND = "metro_underpass"


def _text(value):
    return str(value or "").strip()


def _point_in_footprint(footprint, x, y):
    if not isinstance(footprint, dict):
        return False
    try:
        left = int(footprint.get("left"))
        right = int(footprint.get("right"))
        top = int(footprint.get("top"))
        bottom = int(footprint.get("bottom"))
        x = int(x)
        y = int(y)
    except (TypeError, ValueError):
        return False
    return left <= x <= right and top <= y <= bottom


def _building_footprints(chunk, *, origin_x, origin_y, chunk_size):
    footprints = []
    for block in chunk.get("blocks", ()):
        bx = int(block.get("grid_x", 0))
        by = int(block.get("grid_y", 0))
        buildings = tuple(block.get("buildings", ()) or ())
        for building_index, building in enumerate(buildings):
            layout = layout_chunk_building(
                origin_x=origin_x,
                origin_y=origin_y,
                chunk_size=chunk_size,
                block_grid_x=bx,
                block_grid_y=by,
                building_index=building_index,
                building=building,
                building_count=len(buildings),
            )
            if isinstance(layout, dict) and isinstance(layout.get("footprint"), dict):
                footprints.append(dict(layout["footprint"]))
    return tuple(footprints)


def _preferred_vertical_edges(origin_y, chunk_size, surface_y):
    top_y = int(origin_y) + 1
    bottom_y = int(origin_y) + int(chunk_size) - 2
    distances = (
        (abs(int(surface_y) - top_y), top_y),
        (abs(int(surface_y) - bottom_y), bottom_y),
    )
    ordered = sorted(distances, key=lambda row: (-int(row[0]), int(row[1])))
    return tuple(edge for _distance, edge in ordered)


def _preferred_horizontal_edges(origin_x, chunk_size, surface_x):
    left_x = int(origin_x) + 1
    right_x = int(origin_x) + int(chunk_size) - 2
    distances = (
        (abs(int(surface_x) - left_x), left_x),
        (abs(int(surface_x) - right_x), right_x),
    )
    ordered = sorted(distances, key=lambda row: (-int(row[0]), int(row[1])))
    return tuple(edge for _distance, edge in ordered)


def _surface_exit_for_vertical(surface_x, surface_y, *, origin_x, origin_y, chunk_size, occupied):
    offsets = (0, 1, -1, 2, -2, 3, -3, 4, -4)
    for exit_y in _preferred_vertical_edges(origin_y, chunk_size, surface_y):
        for offset in offsets:
            candidate_x = int(surface_x) + int(offset)
            candidate_y = int(exit_y)
            if not (int(origin_x) + 1 <= candidate_x <= int(origin_x) + int(chunk_size) - 2):
                continue
            if abs(int(surface_y) - candidate_y) < 6:
                continue
            if any(_point_in_footprint(footprint, candidate_x, candidate_y) for footprint in occupied):
                continue
            return candidate_x, candidate_y
    return None


def _surface_exit_for_horizontal(surface_x, surface_y, *, origin_x, origin_y, chunk_size, occupied):
    offsets = (0, 1, -1, 2, -2, 3, -3, 4, -4)
    for exit_x in _preferred_horizontal_edges(origin_x, chunk_size, surface_x):
        for offset in offsets:
            candidate_x = int(exit_x)
            candidate_y = int(surface_y) + int(offset)
            if not (int(origin_y) + 1 <= candidate_y <= int(origin_y) + int(chunk_size) - 2):
                continue
            if abs(int(surface_x) - candidate_x) < 6:
                continue
            if any(_point_in_footprint(footprint, candidate_x, candidate_y) for footprint in occupied):
                continue
            return candidate_x, candidate_y
    return None


def _metro_underpass_plan(
    chunk,
    building,
    layout,
    *,
    chunk_x,
    chunk_y,
    chunk_size,
    origin_x,
    origin_y,
    occupied_footprints,
):
    entry = dict(layout.get("entry", {}))
    surface_entry = site_entry_front_cell(entry)
    if surface_entry is None:
        return None

    surface_x, surface_y, _surface_z = surface_entry
    side = _text(entry.get("side") or "south").lower() or "south"
    tunnel_z = -max(2, int(building.get("basement_levels", 0) or 0) + 1)

    if side in {"north", "south"}:
        surface_exit = _surface_exit_for_vertical(
            surface_x,
            surface_y,
            origin_x=origin_x,
            origin_y=origin_y,
            chunk_size=chunk_size,
            occupied=occupied_footprints,
        )
        if surface_exit is None:
            return None
        tunnel_x = int(surface_exit[0])
        tunnel_start = (tunnel_x, int(surface_y), int(tunnel_z))
        tunnel_end = (tunnel_x, int(surface_exit[1]), int(tunnel_z))
        footprint = {
            "left": int(tunnel_x) - 1,
            "right": int(tunnel_x) + 1,
            "top": min(int(surface_y), int(surface_exit[1])),
            "bottom": max(int(surface_y), int(surface_exit[1])),
        }
    else:
        surface_exit = _surface_exit_for_horizontal(
            surface_x,
            surface_y,
            origin_x=origin_x,
            origin_y=origin_y,
            chunk_size=chunk_size,
            occupied=occupied_footprints,
        )
        if surface_exit is None:
            return None
        tunnel_y = int(surface_exit[1])
        tunnel_start = (int(surface_x), tunnel_y, int(tunnel_z))
        tunnel_end = (int(surface_exit[0]), tunnel_y, int(tunnel_z))
        footprint = {
            "left": min(int(surface_x), int(surface_exit[0])),
            "right": max(int(surface_x), int(surface_exit[0])),
            "top": int(tunnel_y) - 1,
            "bottom": int(tunnel_y) + 1,
        }

    building_name = _text(building.get("business_name")) or "Metro Exchange"
    source_building_id = world_building_id(chunk_x, chunk_y, building)
    site_name = f"{building_name} Underpass"
    street_name = f"{building_name} Street Stairwell"
    plan_building_id = f"{source_building_id}:underpass"
    anchor_x = (int(footprint["left"]) + int(footprint["right"])) // 2
    anchor_y = (int(footprint["top"]) + int(footprint["bottom"])) // 2

    if side in {"north", "south"}:
        start_axis = int(tunnel_start[1])
        end_axis = int(tunnel_end[1])
        axis_min = min(start_axis, end_axis)
        axis_max = max(start_axis, end_axis)
        midpoint_axis = (axis_min + axis_max) // 2
        encounter_axis = midpoint_axis + (2 if end_axis >= start_axis else -2)
        encounter_axis = max(axis_min + 1, min(axis_max - 1, encounter_axis))
        if encounter_axis == midpoint_axis:
            encounter_axis = max(axis_min + 1, min(axis_max - 1, midpoint_axis - 2))
        cache_sites = (
            {
                "name": "Maintenance Locker",
                "x": int(tunnel_start[0]),
                "y": int(midpoint_axis),
                "z": int(tunnel_z),
                "kind": "utility_cache",
            },
        )
        encounter_spawns = (
            {
                "x": int(tunnel_start[0]),
                "y": int(encounter_axis),
                "z": int(tunnel_z),
                "profile": "underground_transient",
            },
        )
        wildlife_spawns = tuple(
            {
                "x": int(tunnel_start[0]),
                "y": int(axis_value),
                "z": int(tunnel_z),
                "profile": "underground_pests",
            }
            for axis_value in sorted({int(axis_min + 1), int(axis_max - 1)})
        )
    else:
        start_axis = int(tunnel_start[0])
        end_axis = int(tunnel_end[0])
        axis_min = min(start_axis, end_axis)
        axis_max = max(start_axis, end_axis)
        midpoint_axis = (axis_min + axis_max) // 2
        encounter_axis = midpoint_axis + (2 if end_axis >= start_axis else -2)
        encounter_axis = max(axis_min + 1, min(axis_max - 1, encounter_axis))
        if encounter_axis == midpoint_axis:
            encounter_axis = max(axis_min + 1, min(axis_max - 1, midpoint_axis - 2))
        cache_sites = (
            {
                "name": "Maintenance Locker",
                "x": int(midpoint_axis),
                "y": int(tunnel_start[1]),
                "z": int(tunnel_z),
                "kind": "utility_cache",
            },
        )
        encounter_spawns = (
            {
                "x": int(encounter_axis),
                "y": int(tunnel_start[1]),
                "z": int(tunnel_z),
                "profile": "underground_transient",
            },
        )
        wildlife_spawns = tuple(
            {
                "x": int(axis_value),
                "y": int(tunnel_start[1]),
                "z": int(tunnel_z),
                "profile": "underground_pests",
            }
            for axis_value in sorted({int(axis_min + 1), int(axis_max - 1)})
        )

    station_destination = {
        "x": int(tunnel_start[0]),
        "y": int(tunnel_start[1]),
        "z": int(tunnel_start[2]),
        "destination_name": site_name,
        "travel_ticks": 2,
    }
    street_destination = {
        "x": int(tunnel_end[0]),
        "y": int(tunnel_end[1]),
        "z": int(tunnel_end[2]),
        "destination_name": site_name,
        "travel_ticks": 2,
    }

    return {
        "site_id": f"{chunk_x}:{chunk_y}:underpass:{_text(building.get('building_id')) or 'metro'}",
        "kind": METRO_UNDERPASS_KIND,
        "name": site_name,
        "building_id": plan_building_id,
        "source_building_id": source_building_id,
        "source_building_name": building_name,
        "anchor": {"x": int(anchor_x), "y": int(anchor_y), "z": int(tunnel_z)},
        "z": int(tunnel_z),
        "floors": 1,
        "rooms": ("maintenance_tunnel", "junction"),
        "ambient_encounter_profile": "underground_transient",
        "ambient_encounter_spawns": encounter_spawns,
        "ambient_wildlife_profile": "underground_pests",
        "ambient_wildlife_spawns": wildlife_spawns,
        "cache_sites": cache_sites,
        "footprint": footprint,
        "entry": {
            "x": int(tunnel_start[0]),
            "y": int(tunnel_start[1]),
            "z": int(tunnel_start[2]),
            "kind": "door",
            "ordinary": True,
            "side": side,
        },
        "apertures": [
            {
                "x": int(tunnel_start[0]),
                "y": int(tunnel_start[1]),
                "z": int(tunnel_start[2]),
                "kind": "door",
                "ordinary": True,
            },
            {
                "x": int(tunnel_end[0]),
                "y": int(tunnel_end[1]),
                "z": int(tunnel_end[2]),
                "kind": "door",
                "ordinary": True,
            },
        ],
        "station_surface": {
            "origin_x": int(surface_x),
            "origin_y": int(surface_y),
            "origin_z": 0,
            "destination": station_destination,
        },
        "street_surface": {
            "name": street_name,
            "x": int(surface_exit[0]),
            "y": int(surface_exit[1]),
            "z": 0,
            "destination": street_destination,
        },
        "underground_returns": (
            {
                "name": f"{building_name} Station Stairs",
                "x": int(tunnel_start[0]),
                "y": int(tunnel_start[1]),
                "z": int(tunnel_start[2]),
                "destination": {
                    "x": int(surface_x),
                    "y": int(surface_y),
                    "z": 0,
                    "destination_name": building_name,
                    "travel_ticks": 1,
                },
            },
            {
                "name": "Street Stairwell",
                "x": int(tunnel_end[0]),
                "y": int(tunnel_end[1]),
                "z": int(tunnel_end[2]),
                "destination": {
                    "x": int(surface_exit[0]),
                    "y": int(surface_exit[1]),
                    "z": 0,
                    "destination_name": "street level",
                    "travel_ticks": 1,
                },
            },
        ),
    }


def chunk_underground_site_plans(chunk, *, origin_x, origin_y, chunk_size):
    """Return deterministic underground site plans for a chunk."""

    if not isinstance(chunk, dict):
        return ()
    district = chunk.get("district", {}) if isinstance(chunk.get("district"), dict) else {}
    area_type = _text(district.get("area_type") or "city").lower() or "city"
    if area_type != "city":
        return ()

    occupied = _building_footprints(chunk, origin_x=origin_x, origin_y=origin_y, chunk_size=chunk_size)
    candidates = []
    chunk_x = int(chunk.get("cx", 0))
    chunk_y = int(chunk.get("cy", 0))
    for block in chunk.get("blocks", ()):
        bx = int(block.get("grid_x", 0))
        by = int(block.get("grid_y", 0))
        buildings = tuple(block.get("buildings", ()) or ())
        for building_index, building in enumerate(buildings):
            if _text((building or {}).get("archetype")).lower() != "metro_exchange":
                continue
            layout = layout_chunk_building(
                origin_x=origin_x,
                origin_y=origin_y,
                chunk_size=chunk_size,
                block_grid_x=bx,
                block_grid_y=by,
                building_index=building_index,
                building=building,
                building_count=len(buildings),
            )
            if not isinstance(layout, dict):
                continue
            plan = _metro_underpass_plan(
                chunk,
                building,
                layout,
                chunk_x=chunk_x,
                chunk_y=chunk_y,
                chunk_size=chunk_size,
                origin_x=origin_x,
                origin_y=origin_y,
                occupied_footprints=occupied,
            )
            if plan is not None:
                candidates.append(plan)

    if not candidates:
        return ()
    candidates.sort(key=lambda row: (_text(row.get("source_building_id")), _text(row.get("site_id"))))
    return (candidates[0],)
