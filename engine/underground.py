"""Deterministic underground site planning for city chunks."""

from __future__ import annotations

import random

from engine.buildings import layout_chunk_building, world_building_id
from engine.sites import site_entry_front_cell


UNDERGROUND_ACCESS_SERVICE = "underground_access"
METRO_UNDERPASS_KIND = "metro_underpass"
UNDERGROUND_HAZARD_ROWS = (
    ("live_wire", "Live Wire", 4.0),
    ("steam_leak", "Steam Leak", 4.0),
    ("foul_drain", "Foul Drain", 3.0),
)


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


def _weighted_choice(rng, rows):
    total = 0.0
    normalized = []
    for row in rows:
        if not isinstance(row, tuple) or len(row) < 3:
            continue
        weight = float(row[2] or 0.0)
        if weight <= 0.0:
            continue
        total += weight
        normalized.append((row, total))
    if total <= 0.0 or not normalized:
        return None
    pick = rng.random() * total
    for row, ceiling in normalized:
        if pick <= ceiling:
            return row
    return normalized[-1][0]


def _axis_step(start_axis, end_axis):
    return 1 if int(end_axis) >= int(start_axis) else -1


def _advance_axis_value(start_axis, end_axis, steps):
    step = _axis_step(start_axis, end_axis)
    candidate = int(start_axis) + (step * int(max(0, steps)))
    axis_min = min(int(start_axis), int(end_axis))
    axis_max = max(int(start_axis), int(end_axis))
    return max(axis_min, min(axis_max, candidate))


def _corridor_cells_vertical(center_x, axis_min, axis_max):
    center_x = int(center_x)
    axis_min = int(axis_min)
    axis_max = int(axis_max)
    return {
        (center_x + offset_x, axis_value)
        for offset_x in (-1, 0, 1)
        for axis_value in range(axis_min, axis_max + 1)
    }


def _corridor_cells_horizontal(center_y, axis_min, axis_max):
    center_y = int(center_y)
    axis_min = int(axis_min)
    axis_max = int(axis_max)
    return {
        (axis_value, center_y + offset_y)
        for offset_y in (-1, 0, 1)
        for axis_value in range(axis_min, axis_max + 1)
    }


def _shape_bounds(cells):
    if not cells:
        return None
    xs = [int(cell[0]) for cell in cells]
    ys = [int(cell[1]) for cell in cells]
    return {
        "left": min(xs),
        "right": max(xs),
        "top": min(ys),
        "bottom": max(ys),
    }


def _shape_excluded_cells(cells):
    bounds = _shape_bounds(cells)
    if not bounds:
        return ()
    shape = {
        (int(cell_x), int(cell_y))
        for cell_x, cell_y in tuple(cells or ())
    }
    excluded = []
    for cell_y in range(int(bounds["top"]), int(bounds["bottom"]) + 1):
        for cell_x in range(int(bounds["left"]), int(bounds["right"]) + 1):
            if (int(cell_x), int(cell_y)) in shape:
                continue
            excluded.append({"x": int(cell_x), "y": int(cell_y)})
    return tuple(excluded)


def _underpass_hazard_specs(
    *,
    chunk_x,
    chunk_y,
    source_building_id,
    tunnel_z,
    orientation,
    fixed_axis,
    axis_min,
    axis_max,
    reserved_axes,
):
    candidates = [
        int(axis)
        for axis in range(int(axis_min) + 1, int(axis_max))
        if int(axis) not in {int(value) for value in tuple(reserved_axes or ())}
    ]
    if not candidates:
        return ()

    rng = random.Random(
        f"{int(chunk_x)}:{int(chunk_y)}:{str(source_building_id).strip() or 'metro'}:underpass_hazards"
    )
    hazard_count = 1 + int(len(candidates) >= 5 and rng.random() < 0.38)
    hazard_count = min(len(candidates), max(1, hazard_count))

    selected_axes = []
    pool = list(candidates)
    while pool and len(selected_axes) < hazard_count:
        picked_axis = int(rng.choice(pool))
        selected_axes.append(picked_axis)
        pool = [axis for axis in pool if abs(int(axis) - picked_axis) > 1]

    specs = []
    for axis in sorted(selected_axes):
        picked = _weighted_choice(rng, UNDERGROUND_HAZARD_ROWS)
        if not picked:
            continue
        profile_id, label, _weight = picked
        if str(orientation).strip().lower() == "vertical":
            x = int(fixed_axis)
            y = int(axis)
        else:
            x = int(axis)
            y = int(fixed_axis)
        specs.append({
            "name": str(label).strip() or "Hazard",
            "x": x,
            "y": y,
            "z": int(tunnel_z),
            "profile": str(profile_id).strip().lower() or "live_wire",
        })
    return tuple(specs)


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


def _surface_exit_aligned_vertical(surface_x, surface_y, *, origin_x, origin_y, chunk_size, occupied):
    for exit_y in _preferred_vertical_edges(origin_y, chunk_size, surface_y):
        candidate_x = int(surface_x)
        candidate_y = int(exit_y)
        if abs(int(surface_y) - candidate_y) < 4:
            continue
        if any(_point_in_footprint(footprint, candidate_x, candidate_y) for footprint in occupied):
            continue
        return candidate_x, candidate_y
    return _surface_exit_for_vertical(
        surface_x,
        surface_y,
        origin_x=origin_x,
        origin_y=origin_y,
        chunk_size=chunk_size,
        occupied=occupied,
    )


def _surface_exit_aligned_horizontal(surface_x, surface_y, *, origin_x, origin_y, chunk_size, occupied):
    for exit_x in _preferred_horizontal_edges(origin_x, chunk_size, surface_x):
        candidate_x = int(exit_x)
        candidate_y = int(surface_y)
        if abs(int(surface_x) - candidate_x) < 4:
            continue
        if any(_point_in_footprint(footprint, candidate_x, candidate_y) for footprint in occupied):
            continue
        return candidate_x, candidate_y
    return _surface_exit_for_horizontal(
        surface_x,
        surface_y,
        origin_x=origin_x,
        origin_y=origin_y,
        chunk_size=chunk_size,
        occupied=occupied,
    )


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
    # Keep station underpasses on the lowest station level so the metro stack
    # feels like one coherent place instead of "one more floor lower."
    tunnel_z = -max(2, int(building.get("basement_levels", 0) or 0))

    layout_variant = "straight_underpass"
    branch_return = None
    footprint_excluded_cells = ()
    service_sites = ()

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
        corridor_cells = _corridor_cells_vertical(int(tunnel_start[0]), axis_min, axis_max)
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
        hazard_sites = _underpass_hazard_specs(
            chunk_x=chunk_x,
            chunk_y=chunk_y,
            source_building_id=source_building_id,
            tunnel_z=tunnel_z,
            orientation="vertical",
            fixed_axis=int(tunnel_start[0]),
            axis_min=axis_min,
            axis_max=axis_max,
            reserved_axes={
                int(midpoint_axis),
                int(encounter_axis),
                int(axis_min + 1),
                int(axis_max - 1),
            },
        )
        branch_surface = _surface_exit_aligned_horizontal(
            int(tunnel_start[0]),
            int(midpoint_axis),
            origin_x=origin_x,
            origin_y=origin_y,
            chunk_size=chunk_size,
            occupied=occupied_footprints,
        )
        if branch_surface is not None:
            branch_end_x = int(branch_surface[0])
            branch_axis_min = min(int(tunnel_start[0]), branch_end_x)
            branch_axis_max = max(int(tunnel_start[0]), branch_end_x)
            branch_encounter_x = _advance_axis_value(int(tunnel_start[0]), branch_end_x, 2)
            branch_cache_x = _advance_axis_value(branch_end_x, int(tunnel_start[0]), 2)
            branch_wildlife_x = _advance_axis_value(int(tunnel_start[0]), branch_end_x, max(1, abs(branch_end_x - int(tunnel_start[0])) // 2))
            corridor_cells.update(_corridor_cells_horizontal(int(midpoint_axis), branch_axis_min, branch_axis_max))
            maybe_footprint = _shape_bounds(corridor_cells)
            if isinstance(maybe_footprint, dict):
                footprint = maybe_footprint
                footprint_excluded_cells = _shape_excluded_cells(corridor_cells)
            cache_sites = tuple(cache_sites) + (
                {
                    "name": "Signal Locker",
                    "x": int(branch_cache_x),
                    "y": int(midpoint_axis),
                    "z": int(tunnel_z),
                    "kind": "utility_cache",
                },
            )
            encounter_spawns = tuple(encounter_spawns) + (
                {
                    "x": int(branch_encounter_x),
                    "y": int(midpoint_axis),
                    "z": int(tunnel_z),
                    "profile": "underground_transient",
                },
            )
            wildlife_spawns = tuple(wildlife_spawns) + (
                {
                    "x": int(branch_wildlife_x),
                    "y": int(midpoint_axis),
                    "z": int(tunnel_z),
                    "profile": "underground_pests",
                },
            )
            branch_hazards = _underpass_hazard_specs(
                chunk_x=chunk_x,
                chunk_y=chunk_y,
                source_building_id=f"{source_building_id}:service_spur",
                tunnel_z=tunnel_z,
                orientation="horizontal",
                fixed_axis=int(midpoint_axis),
                axis_min=branch_axis_min,
                axis_max=branch_axis_max,
                reserved_axes={
                    int(tunnel_start[0]),
                    int(branch_end_x),
                    int(branch_cache_x),
                    int(branch_encounter_x),
                },
            )
            hazard_sites = tuple(hazard_sites) + tuple(branch_hazards)
            branch_return = {
                "name": "Service Hatch",
                "x": int(branch_end_x),
                "y": int(midpoint_axis),
                "z": int(tunnel_z),
                "destination": {
                    "x": int(branch_surface[0]),
                    "y": int(branch_surface[1]),
                    "z": 0,
                    "destination_name": "service hatch",
                    "travel_ticks": 1,
                },
            }
            service_sites = (
                {
                    "name": "Signal Relay",
                    "x": int(branch_encounter_x),
                    "y": int(midpoint_axis),
                    "z": int(tunnel_z),
                    "site_services": ("intel",),
                    "fixture_type": "service_terminal",
                    "lead_mode": "hidden_contact_note",
                },
            )
            layout_variant = "branched_service_spur"
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
        corridor_cells = _corridor_cells_horizontal(int(tunnel_start[1]), axis_min, axis_max)
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
        hazard_sites = _underpass_hazard_specs(
            chunk_x=chunk_x,
            chunk_y=chunk_y,
            source_building_id=source_building_id,
            tunnel_z=tunnel_z,
            orientation="horizontal",
            fixed_axis=int(tunnel_start[1]),
            axis_min=axis_min,
            axis_max=axis_max,
            reserved_axes={
                int(midpoint_axis),
                int(encounter_axis),
                int(axis_min + 1),
                int(axis_max - 1),
            },
        )
        branch_surface = _surface_exit_aligned_vertical(
            int(midpoint_axis),
            int(tunnel_start[1]),
            origin_x=origin_x,
            origin_y=origin_y,
            chunk_size=chunk_size,
            occupied=occupied_footprints,
        )
        if branch_surface is not None:
            branch_end_y = int(branch_surface[1])
            branch_axis_min = min(int(tunnel_start[1]), branch_end_y)
            branch_axis_max = max(int(tunnel_start[1]), branch_end_y)
            branch_encounter_y = _advance_axis_value(int(tunnel_start[1]), branch_end_y, 2)
            branch_cache_y = _advance_axis_value(branch_end_y, int(tunnel_start[1]), 2)
            branch_wildlife_y = _advance_axis_value(int(tunnel_start[1]), branch_end_y, max(1, abs(branch_end_y - int(tunnel_start[1])) // 2))
            corridor_cells.update(_corridor_cells_vertical(int(midpoint_axis), branch_axis_min, branch_axis_max))
            maybe_footprint = _shape_bounds(corridor_cells)
            if isinstance(maybe_footprint, dict):
                footprint = maybe_footprint
                footprint_excluded_cells = _shape_excluded_cells(corridor_cells)
            cache_sites = tuple(cache_sites) + (
                {
                    "name": "Signal Locker",
                    "x": int(midpoint_axis),
                    "y": int(branch_cache_y),
                    "z": int(tunnel_z),
                    "kind": "utility_cache",
                },
            )
            encounter_spawns = tuple(encounter_spawns) + (
                {
                    "x": int(midpoint_axis),
                    "y": int(branch_encounter_y),
                    "z": int(tunnel_z),
                    "profile": "underground_transient",
                },
            )
            wildlife_spawns = tuple(wildlife_spawns) + (
                {
                    "x": int(midpoint_axis),
                    "y": int(branch_wildlife_y),
                    "z": int(tunnel_z),
                    "profile": "underground_pests",
                },
            )
            branch_hazards = _underpass_hazard_specs(
                chunk_x=chunk_x,
                chunk_y=chunk_y,
                source_building_id=f"{source_building_id}:service_spur",
                tunnel_z=tunnel_z,
                orientation="vertical",
                fixed_axis=int(midpoint_axis),
                axis_min=branch_axis_min,
                axis_max=branch_axis_max,
                reserved_axes={
                    int(tunnel_start[1]),
                    int(branch_end_y),
                    int(branch_cache_y),
                    int(branch_encounter_y),
                },
            )
            hazard_sites = tuple(hazard_sites) + tuple(branch_hazards)
            branch_return = {
                "name": "Service Hatch",
                "x": int(midpoint_axis),
                "y": int(branch_end_y),
                "z": int(tunnel_z),
                "destination": {
                    "x": int(branch_surface[0]),
                    "y": int(branch_surface[1]),
                    "z": 0,
                    "destination_name": "service hatch",
                    "travel_ticks": 1,
                },
            }
            service_sites = (
                {
                    "name": "Signal Relay",
                    "x": int(midpoint_axis),
                    "y": int(branch_encounter_y),
                    "z": int(tunnel_z),
                    "site_services": ("intel",),
                    "fixture_type": "service_terminal",
                    "lead_mode": "hidden_contact_note",
                },
            )
            layout_variant = "branched_service_spur"

    anchor_x = (int(footprint["left"]) + int(footprint["right"])) // 2
    anchor_y = (int(footprint["top"]) + int(footprint["bottom"])) // 2

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
        "layout_variant": layout_variant,
        "name": site_name,
        "building_id": plan_building_id,
        "source_building_id": source_building_id,
        "source_building_name": building_name,
        "anchor": {"x": int(anchor_x), "y": int(anchor_y), "z": int(tunnel_z)},
        "z": int(tunnel_z),
        "floors": 1,
        "rooms": ("maintenance_tunnel",),
        "ambient_encounter_profile": "underground_transient",
        "ambient_encounter_spawns": encounter_spawns,
        "ambient_wildlife_profile": "underground_pests",
        "ambient_wildlife_spawns": wildlife_spawns,
        "ambient_hazard_profile": "transit_hazards" if hazard_sites else "",
        "ambient_hazard_spawns": hazard_sites,
        "cache_sites": cache_sites,
        "service_sites": service_sites,
        "footprint": footprint,
        "footprint_excluded_cells": footprint_excluded_cells,
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
        ] + (
            [
                {
                    "x": int(branch_return["x"]),
                    "y": int(branch_return["y"]),
                    "z": int(branch_return["z"]),
                    "kind": "door",
                    "ordinary": True,
                },
            ]
            if isinstance(branch_return, dict) else []
        ),
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
        ) + ((branch_return,) if isinstance(branch_return, dict) else ()),
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
