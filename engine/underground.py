"""Deterministic underground site planning for city chunks."""

from __future__ import annotations

import heapq
import random

from engine.buildings import layout_chunk_building, world_building_id
from engine.sites import site_entry_front_cell
from engine.world import normalize_building_levels


UNDERGROUND_ACCESS_SERVICE = "underground_access"
METRO_UNDERPASS_KIND = "metro_underpass"
UTILITY_CORRIDOR_KIND = "utility_corridor"
STORM_DRAIN_KIND = "storm_drain"
SERVICE_BASEMENT_KIND = "service_basement"
ACCESS_TUNNEL_NETWORK_KIND = "access_tunnel_network"
UNDERGROUND_NETWORK_Z = -1
CANONICAL_UNDERGROUND_KINDS = (
    METRO_UNDERPASS_KIND,
    UTILITY_CORRIDOR_KIND,
    STORM_DRAIN_KIND,
    SERVICE_BASEMENT_KIND,
)
MAX_UNDERGROUND_PLANS_PER_CHUNK = 3
UNDERGROUND_HAZARD_ROWS = (
    ("live_wire", "Live Wire", 4.0),
    ("steam_leak", "Steam Leak", 4.0),
    ("foul_drain", "Foul Drain", 3.0),
)

UTILITY_CORRIDOR_ARCHETYPES = {
    "bank",
    "brokerage",
    "cold_storage",
    "co_working_hub",
    "courier_office",
    "data_center",
    "factory",
    "freight_depot",
    "lab",
    "machine_shop",
    "office",
    "pump_house",
    "recycling_plant",
    "relay_post",
    "server_hub",
    "service_station",
    "tower",
    "warehouse",
}
STORM_DRAIN_ARCHETYPES = {
    "bar",
    "factory",
    "flophouse",
    "junk_market",
    "laundromat",
    "pawn_shop",
    "recycling_plant",
    "soup_kitchen",
    "tenement",
    "warehouse",
}


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


def _plan_shape_cells(plan):
    """Return the realized horizontal cells for a shaped underground plan."""

    if not isinstance(plan, dict) or not isinstance(plan.get("footprint"), dict):
        return frozenset()
    footprint = plan["footprint"]
    try:
        left = int(footprint.get("left"))
        right = int(footprint.get("right"))
        top = int(footprint.get("top"))
        bottom = int(footprint.get("bottom"))
    except (TypeError, ValueError):
        return frozenset()
    excluded = set()
    for cell in tuple(plan.get("footprint_excluded_cells", ()) or ()):
        try:
            if isinstance(cell, dict):
                excluded.add((int(cell.get("x")), int(cell.get("y"))))
            elif isinstance(cell, (list, tuple)) and len(cell) >= 2:
                excluded.add((int(cell[0]), int(cell[1])))
        except (TypeError, ValueError):
            continue
    return frozenset(
        (x, y)
        for y in range(top, bottom + 1)
        for x in range(left, right + 1)
        if (x, y) not in excluded
    )


def _network_path(start, goals, *, bounds, blocked=(), preferred_axis=None):
    """Find a short deterministic tunnel path while favoring an existing lane."""

    start = (int(start[0]), int(start[1]))
    goals = {(int(cell[0]), int(cell[1])) for cell in tuple(goals or ())}
    if not goals:
        return ()
    left, right, top, bottom = (int(value) for value in bounds)
    blocked = {(int(cell[0]), int(cell[1])) for cell in tuple(blocked or ())}
    blocked.discard(start)
    blocked.difference_update(goals)
    if start in goals:
        return (start,)

    frontier = [(0.0, 0, start[1], start[0], start)]
    costs = {start: 0.0}
    previous = {}
    preferred_kind = ""
    preferred_value = 0
    if isinstance(preferred_axis, (list, tuple)) and len(preferred_axis) >= 2:
        preferred_kind = str(preferred_axis[0] or "").strip().lower()
        try:
            preferred_value = int(preferred_axis[1])
        except (TypeError, ValueError):
            preferred_kind = ""

    while frontier:
        cost, steps, _sort_y, _sort_x, current = heapq.heappop(frontier)
        if cost > costs.get(current, float("inf")) + 0.0001:
            continue
        if current in goals:
            path = [current]
            while current in previous:
                current = previous[current]
                path.append(current)
            path.reverse()
            return tuple(path)

        x, y = current
        for nx, ny in ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)):
            neighbor = (int(nx), int(ny))
            if nx < left or nx > right or ny < top or ny > bottom or neighbor in blocked:
                continue
            deviation = 0
            if preferred_kind == "x":
                deviation = abs(int(nx) - preferred_value)
            elif preferred_kind == "y":
                deviation = abs(int(ny) - preferred_value)
            next_cost = float(cost) + 1.0 + (0.035 * float(deviation))
            if next_cost + 0.0001 >= costs.get(neighbor, float("inf")):
                continue
            costs[neighbor] = next_cost
            previous[neighbor] = current
            heapq.heappush(frontier, (next_cost, int(steps) + 1, int(ny), int(nx), neighbor))
    return ()


def _nearest_open_network_cell(cells, point, *, blocked=()):
    blocked = set(blocked or ())
    candidates = [cell for cell in tuple(cells or ()) if cell not in blocked]
    if not candidates:
        return None
    px, py = int(point[0]), int(point[1])
    return min(
        candidates,
        key=lambda cell: (
            abs(int(cell[0]) - px) + abs(int(cell[1]) - py),
            int(cell[1]),
            int(cell[0]),
        ),
    )


def _network_site_portal(plan):
    """Pick a clear site cell for a network connection without occupying content."""

    cells = set(_plan_shape_cells(plan))
    if not cells:
        return None
    reserved = set()
    for key in (
        "cache_sites",
        "service_sites",
        "ambient_encounter_spawns",
        "ambient_wildlife_spawns",
        "ambient_hazard_spawns",
        "underground_returns",
    ):
        for spec in tuple(plan.get(key, ()) or ()):
            if not isinstance(spec, dict):
                continue
            try:
                reserved.add((int(spec.get("x")), int(spec.get("y"))))
            except (TypeError, ValueError):
                continue
    anchor = plan.get("anchor", {}) if isinstance(plan.get("anchor"), dict) else {}
    try:
        anchor_point = (int(anchor.get("x")), int(anchor.get("y")))
    except (TypeError, ValueError):
        anchor_point = next(iter(cells))
    candidates = []
    for cell in cells:
        if cell in reserved:
            continue
        neighbor_count = sum(
            (cell[0] + dx, cell[1] + dy) in cells
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        )
        candidates.append((
            -int(neighbor_count),
            abs(cell[0] - anchor_point[0]) + abs(cell[1] - anchor_point[1]),
            cell[1],
            cell[0],
            cell,
        ))
    if not candidates:
        candidates = [(0, 0, cell[1], cell[0], cell) for cell in cells if cell not in reserved]
    return min(candidates)[-1] if candidates else None


def _underground_network_profile(district):
    district = district if isinstance(district, dict) else {}
    district_type = _text(district.get("district_type")).lower() or "city"
    if district_type in {"industrial", "military", "corporate"}:
        return {
            "variant": "service_grid",
            "label": "Service Grid",
            "rooms": ("access_tunnel", "utility_spine", "conduit_junction", "service_alcove"),
            "encounter": "underground_maintenance",
            "wildlife": "basement_pests",
            "cache": "maintenance",
            "floor_glyph": "=",
        }
    if district_type in {"slums", "entertainment"}:
        return {
            "variant": "understreet_sprawl",
            "label": "Understreet Sprawl",
            "rooms": ("access_tunnel", "old_service_way", "handoff_nook", "shelter_alcove"),
            "encounter": "underground_shady",
            "wildlife": "drain_wildlife",
            "cache": "contraband_light",
            "floor_glyph": ",",
        }
    if district_type in {"downtown", "transport"}:
        return {
            "variant": "old_transit_cut",
            "label": "Old Transit Cut",
            "rooms": ("access_tunnel", "abandoned_platform", "service_junction", "waiting_nook"),
            "encounter": "underground_transient",
            "wildlife": "underground_pests",
            "cache": "survival",
            "floor_glyph": ".",
        }
    return {
        "variant": "shelter_ways",
        "label": "Shelter Ways",
        "rooms": ("access_tunnel", "service_passage", "shelter_alcove", "drain_crossing"),
        "encounter": "underground_shelter",
        "wildlife": "basement_pests",
        "cache": "survival",
        "floor_glyph": ".",
    }


def _footprints_overlap(left, right, top, bottom, other, *, buffer=0):
    if not isinstance(other, dict):
        return False
    try:
        other_left = int(other.get("left")) - int(buffer)
        other_right = int(other.get("right")) + int(buffer)
        other_top = int(other.get("top")) - int(buffer)
        other_bottom = int(other.get("bottom")) + int(buffer)
    except (TypeError, ValueError):
        return False
    return not (
        int(right) < other_left
        or int(left) > other_right
        or int(bottom) < other_top
        or int(top) > other_bottom
    )


def _plan_overlaps_existing(plan, accepted):
    if not isinstance(plan, dict):
        return True
    footprint = plan.get("footprint")
    if not isinstance(footprint, dict):
        return True
    try:
        z = int(plan.get("z", 0))
        left = int(footprint.get("left"))
        right = int(footprint.get("right"))
        top = int(footprint.get("top"))
        bottom = int(footprint.get("bottom"))
    except (TypeError, ValueError):
        return True
    for other in tuple(accepted or ()):
        try:
            other_z = int(other.get("z", 0))
        except (TypeError, ValueError, AttributeError):
            continue
        if other_z != z:
            continue
        if _footprints_overlap(left, right, top, bottom, other.get("footprint"), buffer=1):
            return True
    return False


def _edge_buffer_axes(axis_min, axis_max, *, buffer=2):
    axis_min = int(axis_min)
    axis_max = int(axis_max)
    interior_min = axis_min + int(max(1, buffer))
    interior_max = axis_max - int(max(1, buffer))
    if interior_min > interior_max:
        interior_min = axis_min + 1
        interior_max = axis_max - 1
    if interior_min > interior_max:
        return ()
    return tuple(sorted({int(interior_min), int(interior_max)}))


def _interior_axis_value(axis_min, axis_max, preferred):
    axis_min = int(axis_min)
    axis_max = int(axis_max)
    if axis_max - axis_min <= 1:
        return int(preferred)
    return max(axis_min + 1, min(axis_max - 1, int(preferred)))


def _is_drain_friendly_district(district):
    if not isinstance(district, dict):
        return False
    district_type = _text(district.get("district_type")).lower()
    if district_type in {"industrial", "slums"}:
        return True
    terrain = _text(district.get("terrain")).lower()
    return terrain in {"shore", "industrial_waste", "waterfront"}


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


def _building_basement_cells(chunk, *, origin_x, origin_y, chunk_size):
    cells = set()
    for block in chunk.get("blocks", ()):
        bx = int(block.get("grid_x", 0))
        by = int(block.get("grid_y", 0))
        buildings = tuple(block.get("buildings", ()) or ())
        for building_index, building in enumerate(buildings):
            if not isinstance(building, dict):
                continue
            _floors, basement_levels = normalize_building_levels(
                building.get("archetype"),
                building.get("floors", 1),
                building.get("basement_levels", 0),
            )
            if int(basement_levels) <= 0:
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
            footprint = layout.get("footprint") if isinstance(layout, dict) else None
            if not isinstance(footprint, dict):
                continue
            try:
                left = int(footprint.get("left"))
                right = int(footprint.get("right"))
                top = int(footprint.get("top"))
                bottom = int(footprint.get("bottom"))
            except (TypeError, ValueError):
                continue
            excluded = set(layout.get("excluded", ()) or ())
            cells.update(
                (x, y)
                for y in range(top, bottom + 1)
                for x in range(left, right + 1)
                if (x, y) not in excluded
            )
    return frozenset(cells)


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
                "cache_profile": "maintenance",
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
        wildlife_axes = _edge_buffer_axes(axis_min, axis_max, buffer=2)
        wildlife_spawns = tuple(
            {
                "x": int(tunnel_start[0]),
                "y": int(axis_value),
                "z": int(tunnel_z),
                "profile": "underground_pests",
            }
            for axis_value in wildlife_axes
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
                *(int(axis_value) for axis_value in wildlife_axes),
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
                    "cache_profile": "maintenance",
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
                "cache_profile": "maintenance",
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
        wildlife_axes = _edge_buffer_axes(axis_min, axis_max, buffer=2)
        wildlife_spawns = tuple(
            {
                "x": int(axis_value),
                "y": int(tunnel_start[1]),
                "z": int(tunnel_z),
                "profile": "underground_pests",
            }
            for axis_value in wildlife_axes
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
                *(int(axis_value) for axis_value in wildlife_axes),
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
                    "cache_profile": "maintenance",
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


def _generic_corridor_plan(
    chunk,
    building,
    layout,
    *,
    kind,
    chunk_x,
    chunk_y,
    chunk_size,
    origin_x,
    origin_y,
    occupied_footprints,
    tunnel_z,
):
    entry = dict(layout.get("entry", {}))
    surface_entry = site_entry_front_cell(entry)
    if surface_entry is None:
        return None

    surface_x, surface_y, _surface_z = surface_entry
    side = _text(entry.get("side") or "south").lower() or "south"
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

    kind = _text(kind).lower()
    building_name = _text(building.get("business_name")) or _text(building.get("archetype")).replace("_", " ").title() or "Building"
    source_building_id = world_building_id(chunk_x, chunk_y, building)
    local_building_id = _text(building.get("building_id")) or _text(building.get("archetype")) or "site"

    if kind == UTILITY_CORRIDOR_KIND:
        site_label = "Utility Corridor"
        site_suffix = "utility"
        rooms = ("utility_corridor", "maintenance_tunnel", "service_room")
        cache_profile = "maintenance"
        encounter_profile = "underground_maintenance"
        wildlife_profile = "basement_pests"
        source_return_name = f"{building_name} Service Stairs"
        street_return_name = "Utility Hatch"
        street_surface_name = f"{building_name} Utility Hatch"
    elif kind == STORM_DRAIN_KIND:
        site_label = "Storm Drain"
        site_suffix = "storm_drain"
        rooms = ("storm_drain", "drain_junction", "overflow_channel")
        cache_profile = "drain"
        encounter_profile = "underground_scavengers"
        wildlife_profile = "drain_wildlife"
        source_return_name = f"{building_name} Drain Ladder"
        street_return_name = "Drain Grate"
        street_surface_name = "Street Drain Grate"
    elif kind == SERVICE_BASEMENT_KIND:
        site_label = "Service Basement"
        site_suffix = "service_basement"
        rooms = ("service_basement", "utility_room", "storage")
        cache_profile = "survival"
        encounter_profile = "underground_shelter"
        wildlife_profile = "basement_pests"
        source_return_name = f"{building_name} Basement Stairs"
        street_return_name = "Service Hatch"
        street_surface_name = f"{building_name} Service Hatch"
    else:
        return None

    site_name = f"{building_name} {site_label}"
    plan_building_id = f"{source_building_id}:{site_suffix}"
    footprint_excluded_cells = ()
    branch_return = None
    service_sites = ()
    layout_variant = "straight_corridor"

    if side in {"north", "south"}:
        start_axis = int(tunnel_start[1])
        end_axis = int(tunnel_end[1])
        axis_min = min(start_axis, end_axis)
        axis_max = max(start_axis, end_axis)
        midpoint_axis = (axis_min + axis_max) // 2
        encounter_axis = _interior_axis_value(axis_min, axis_max, midpoint_axis + (2 if end_axis >= start_axis else -2))
        cache_axis = _interior_axis_value(axis_min, axis_max, midpoint_axis)
        corridor_cells = _corridor_cells_vertical(int(tunnel_start[0]), axis_min, axis_max)
        wildlife_axes = _edge_buffer_axes(axis_min, axis_max, buffer=2)
        cache_sites = (
            {
                "name": "Maintenance Locker" if cache_profile == "maintenance" else "Stashed Pack",
                "x": int(tunnel_start[0]),
                "y": int(cache_axis),
                "z": int(tunnel_z),
                "kind": "utility_cache",
                "cache_profile": cache_profile,
            },
        )
        encounter_spawns = (
            {
                "x": int(tunnel_start[0]),
                "y": int(encounter_axis),
                "z": int(tunnel_z),
                "profile": encounter_profile,
            },
        )
        wildlife_spawns = tuple(
            {
                "x": int(tunnel_start[0]),
                "y": int(axis_value),
                "z": int(tunnel_z),
                "profile": wildlife_profile,
            }
            for axis_value in wildlife_axes
        )
        hazard_sites = _underpass_hazard_specs(
            chunk_x=chunk_x,
            chunk_y=chunk_y,
            source_building_id=f"{source_building_id}:{site_suffix}",
            tunnel_z=tunnel_z,
            orientation="vertical",
            fixed_axis=int(tunnel_start[0]),
            axis_min=axis_min,
            axis_max=axis_max,
            reserved_axes={
                int(cache_axis),
                int(encounter_axis),
                *(int(axis_value) for axis_value in wildlife_axes),
            },
        )
        branch_surface = _surface_exit_aligned_horizontal(
            int(tunnel_start[0]),
            int(cache_axis),
            origin_x=origin_x,
            origin_y=origin_y,
            chunk_size=chunk_size,
            occupied=occupied_footprints,
        )
        if branch_surface is not None:
            branch_end_x = int(branch_surface[0])
            branch_axis_min = min(int(tunnel_start[0]), branch_end_x)
            branch_axis_max = max(int(tunnel_start[0]), branch_end_x)
            branch_cache_x = _advance_axis_value(branch_end_x, int(tunnel_start[0]), 2)
            branch_encounter_x = _advance_axis_value(int(tunnel_start[0]), branch_end_x, 2)
            branch_wildlife_x = _advance_axis_value(int(tunnel_start[0]), branch_end_x, max(1, abs(branch_end_x - int(tunnel_start[0])) // 2))
            corridor_cells.update(_corridor_cells_horizontal(int(cache_axis), branch_axis_min, branch_axis_max))
            maybe_footprint = _shape_bounds(corridor_cells)
            if isinstance(maybe_footprint, dict):
                footprint = maybe_footprint
                footprint_excluded_cells = _shape_excluded_cells(corridor_cells)
            cache_sites = tuple(cache_sites) + (
                {
                    "name": "Hidden Cache" if kind == STORM_DRAIN_KIND else "Service Locker",
                    "x": int(branch_cache_x),
                    "y": int(cache_axis),
                    "z": int(tunnel_z),
                    "kind": "utility_cache",
                    "cache_profile": "contraband_light" if kind == STORM_DRAIN_KIND else cache_profile,
                },
            )
            encounter_spawns = tuple(encounter_spawns) + (
                {
                    "x": int(branch_encounter_x),
                    "y": int(cache_axis),
                    "z": int(tunnel_z),
                    "profile": "underground_shady" if kind == STORM_DRAIN_KIND else encounter_profile,
                },
            )
            wildlife_spawns = tuple(wildlife_spawns) + (
                {
                    "x": int(branch_wildlife_x),
                    "y": int(cache_axis),
                    "z": int(tunnel_z),
                    "profile": wildlife_profile,
                },
            )
            hazard_sites = tuple(hazard_sites) + tuple(_underpass_hazard_specs(
                chunk_x=chunk_x,
                chunk_y=chunk_y,
                source_building_id=f"{source_building_id}:{site_suffix}:branch",
                tunnel_z=tunnel_z,
                orientation="horizontal",
                fixed_axis=int(cache_axis),
                axis_min=branch_axis_min,
                axis_max=branch_axis_max,
                reserved_axes={
                    int(tunnel_start[0]),
                    int(branch_end_x),
                    int(branch_cache_x),
                    int(branch_encounter_x),
                },
            ))
            branch_return = {
                "name": "Service Hatch",
                "x": int(branch_end_x),
                "y": int(cache_axis),
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
                    "y": int(cache_axis),
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
        encounter_axis = _interior_axis_value(axis_min, axis_max, midpoint_axis + (2 if end_axis >= start_axis else -2))
        cache_axis = _interior_axis_value(axis_min, axis_max, midpoint_axis)
        corridor_cells = _corridor_cells_horizontal(int(tunnel_start[1]), axis_min, axis_max)
        wildlife_axes = _edge_buffer_axes(axis_min, axis_max, buffer=2)
        cache_sites = (
            {
                "name": "Maintenance Locker" if cache_profile == "maintenance" else "Stashed Pack",
                "x": int(cache_axis),
                "y": int(tunnel_start[1]),
                "z": int(tunnel_z),
                "kind": "utility_cache",
                "cache_profile": cache_profile,
            },
        )
        encounter_spawns = (
            {
                "x": int(encounter_axis),
                "y": int(tunnel_start[1]),
                "z": int(tunnel_z),
                "profile": encounter_profile,
            },
        )
        wildlife_spawns = tuple(
            {
                "x": int(axis_value),
                "y": int(tunnel_start[1]),
                "z": int(tunnel_z),
                "profile": wildlife_profile,
            }
            for axis_value in wildlife_axes
        )
        hazard_sites = _underpass_hazard_specs(
            chunk_x=chunk_x,
            chunk_y=chunk_y,
            source_building_id=f"{source_building_id}:{site_suffix}",
            tunnel_z=tunnel_z,
            orientation="horizontal",
            fixed_axis=int(tunnel_start[1]),
            axis_min=axis_min,
            axis_max=axis_max,
            reserved_axes={
                int(cache_axis),
                int(encounter_axis),
                *(int(axis_value) for axis_value in wildlife_axes),
            },
        )
        branch_surface = _surface_exit_aligned_vertical(
            int(cache_axis),
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
            branch_cache_y = _advance_axis_value(branch_end_y, int(tunnel_start[1]), 2)
            branch_encounter_y = _advance_axis_value(int(tunnel_start[1]), branch_end_y, 2)
            branch_wildlife_y = _advance_axis_value(int(tunnel_start[1]), branch_end_y, max(1, abs(branch_end_y - int(tunnel_start[1])) // 2))
            corridor_cells.update(_corridor_cells_vertical(int(cache_axis), branch_axis_min, branch_axis_max))
            maybe_footprint = _shape_bounds(corridor_cells)
            if isinstance(maybe_footprint, dict):
                footprint = maybe_footprint
                footprint_excluded_cells = _shape_excluded_cells(corridor_cells)
            cache_sites = tuple(cache_sites) + (
                {
                    "name": "Hidden Cache" if kind == STORM_DRAIN_KIND else "Service Locker",
                    "x": int(cache_axis),
                    "y": int(branch_cache_y),
                    "z": int(tunnel_z),
                    "kind": "utility_cache",
                    "cache_profile": "contraband_light" if kind == STORM_DRAIN_KIND else cache_profile,
                },
            )
            encounter_spawns = tuple(encounter_spawns) + (
                {
                    "x": int(cache_axis),
                    "y": int(branch_encounter_y),
                    "z": int(tunnel_z),
                    "profile": "underground_shady" if kind == STORM_DRAIN_KIND else encounter_profile,
                },
            )
            wildlife_spawns = tuple(wildlife_spawns) + (
                {
                    "x": int(cache_axis),
                    "y": int(branch_wildlife_y),
                    "z": int(tunnel_z),
                    "profile": wildlife_profile,
                },
            )
            hazard_sites = tuple(hazard_sites) + tuple(_underpass_hazard_specs(
                chunk_x=chunk_x,
                chunk_y=chunk_y,
                source_building_id=f"{source_building_id}:{site_suffix}:branch",
                tunnel_z=tunnel_z,
                orientation="vertical",
                fixed_axis=int(cache_axis),
                axis_min=branch_axis_min,
                axis_max=branch_axis_max,
                reserved_axes={
                    int(tunnel_start[1]),
                    int(branch_end_y),
                    int(branch_cache_y),
                    int(branch_encounter_y),
                },
            ))
            branch_return = {
                "name": "Service Hatch",
                "x": int(cache_axis),
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
                    "x": int(cache_axis),
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
        "site_id": f"{chunk_x}:{chunk_y}:{site_suffix}:{local_building_id}",
        "kind": kind,
        "layout_variant": layout_variant,
        "name": site_name,
        "building_id": plan_building_id,
        "source_building_id": source_building_id,
        "source_building_name": building_name,
        "anchor": {"x": int(anchor_x), "y": int(anchor_y), "z": int(tunnel_z)},
        "z": int(tunnel_z),
        "floors": 1,
        "rooms": rooms,
        "ambient_encounter_profile": encounter_profile,
        "ambient_encounter_spawns": encounter_spawns,
        "ambient_wildlife_profile": wildlife_profile,
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
            "name": street_surface_name,
            "x": int(surface_exit[0]),
            "y": int(surface_exit[1]),
            "z": 0,
            "destination": street_destination,
        },
        "underground_returns": (
            {
                "name": source_return_name,
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
                "name": street_return_name,
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
    accepted = []
    used_sources = set()
    chunk_x = int(chunk.get("cx", 0))
    chunk_y = int(chunk.get("cy", 0))
    building_rows = []
    for block in chunk.get("blocks", ()):
        bx = int(block.get("grid_x", 0))
        by = int(block.get("grid_y", 0))
        buildings = tuple(block.get("buildings", ()) or ())
        for building_index, building in enumerate(buildings):
            if not isinstance(building, dict):
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
            source_id = world_building_id(chunk_x, chunk_y, building)
            archetype = _text((building or {}).get("archetype")).lower()
            building_rows.append((source_id, archetype, building, layout))

    def append_plan(plan):
        if not isinstance(plan, dict):
            return False
        if len(accepted) >= MAX_UNDERGROUND_PLANS_PER_CHUNK:
            return False
        source_id = _text(plan.get("source_building_id"))
        if source_id and source_id in used_sources:
            return False
        if _plan_overlaps_existing(plan, accepted):
            return False
        accepted.append(plan)
        if source_id:
            used_sources.add(source_id)
        return True

    def ranked(kind, rows):
        def rank(row):
            source_id = str(row[0])
            rng = random.Random(f"{chunk_x}:{chunk_y}:{kind}:{source_id}")
            return (rng.random(), source_id)
        return tuple(sorted(rows, key=rank))

    metro_rows = tuple(
        row for row in building_rows
        if str(row[1]) == "metro_exchange"
    )
    for source_id, _archetype, building, layout in ranked(METRO_UNDERPASS_KIND, metro_rows):
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
        if append_plan(plan):
            break

    utility_rows = tuple(
        row for row in building_rows
        if row[0] not in used_sources and str(row[1]) in UTILITY_CORRIDOR_ARCHETYPES
    )
    for source_id, _archetype, building, layout in ranked(UTILITY_CORRIDOR_KIND, utility_rows):
        tunnel_z = -max(1, int((building or {}).get("basement_levels", 0) or 0))
        plan = _generic_corridor_plan(
            chunk,
            building,
            layout,
            kind=UTILITY_CORRIDOR_KIND,
            chunk_x=chunk_x,
            chunk_y=chunk_y,
            chunk_size=chunk_size,
            origin_x=origin_x,
            origin_y=origin_y,
            occupied_footprints=occupied,
            tunnel_z=tunnel_z,
        )
        if append_plan(plan):
            break

    storm_rows = ()
    if _is_drain_friendly_district(district):
        storm_rows = tuple(
            row for row in building_rows
            if row[0] not in used_sources and str(row[1]) in STORM_DRAIN_ARCHETYPES
        )
        if not storm_rows:
            storm_rows = tuple(row for row in building_rows if row[0] not in used_sources)
    for source_id, _archetype, building, layout in ranked(STORM_DRAIN_KIND, storm_rows):
        plan = _generic_corridor_plan(
            chunk,
            building,
            layout,
            kind=STORM_DRAIN_KIND,
            chunk_x=chunk_x,
            chunk_y=chunk_y,
            chunk_size=chunk_size,
            origin_x=origin_x,
            origin_y=origin_y,
            occupied_footprints=occupied,
            tunnel_z=-1,
        )
        if append_plan(plan):
            break

    basement_rows = tuple(
        row for row in building_rows
        if row[0] not in used_sources
        and int((row[2] or {}).get("basement_levels", 0) or 0) > 0
        and str(row[1]) != "metro_exchange"
    )
    for source_id, _archetype, building, layout in ranked(SERVICE_BASEMENT_KIND, basement_rows):
        basement_levels = int((building or {}).get("basement_levels", 0) or 0)
        plan = _generic_corridor_plan(
            chunk,
            building,
            layout,
            kind=SERVICE_BASEMENT_KIND,
            chunk_x=chunk_x,
            chunk_y=chunk_y,
            chunk_size=chunk_size,
            origin_x=origin_x,
            origin_y=origin_y,
            occupied_footprints=occupied,
            tunnel_z=-max(2, basement_levels + 1),
        )
        if append_plan(plan):
            break

    if not accepted:
        return ()
    accepted.sort(key=lambda row: (
        0 if _text(row.get("kind")).lower() == METRO_UNDERPASS_KIND else 1,
        _text(row.get("source_building_id")),
        _text(row.get("site_id")),
    ))
    return tuple(accepted[:MAX_UNDERGROUND_PLANS_PER_CHUNK])


def chunk_underground_network_plan(
    chunk,
    *,
    origin_x,
    origin_y,
    chunk_size,
    site_plans=(),
    world_seed=0,
):
    """Plan the shared z=-1 underworld carried continuously between city chunks."""

    if not isinstance(chunk, dict):
        return None
    district = chunk.get("district", {}) if isinstance(chunk.get("district"), dict) else {}
    if (_text(district.get("area_type") or "city").lower() or "city") != "city":
        return None

    size = int(max(8, chunk_size))
    left = int(origin_x)
    right = left + size - 1
    top = int(origin_y)
    bottom = top + size - 1
    chunk_x = int(chunk.get("cx", 0))
    chunk_y = int(chunk.get("cy", 0))
    margin = max(2, min(4, size // 5))
    lane_span = max(1, size - (margin * 2))
    lane_x = left + margin + random.Random(
        f"{int(world_seed)}:underground_network:column:{chunk_x}"
    ).randrange(lane_span)
    lane_y = top + margin + random.Random(
        f"{int(world_seed)}:underground_network:row:{chunk_y}"
    ).randrange(lane_span)

    site_plans = tuple(plan for plan in tuple(site_plans or ()) if isinstance(plan, dict))
    z1_site_cells = set()
    for plan in site_plans:
        try:
            plan_z = int(plan.get("z", 0))
        except (TypeError, ValueError):
            continue
        if plan_z == UNDERGROUND_NETWORK_Z:
            z1_site_cells.update(_plan_shape_cells(plan))

    basement_cells = set(_building_basement_cells(
        chunk,
        origin_x=origin_x,
        origin_y=origin_y,
        chunk_size=size,
    ))
    basement_cells.difference_update(z1_site_cells)

    edge_points = {
        (left, lane_y),
        (right, lane_y),
        (lane_x, top),
        (lane_x, bottom),
    }
    blocked = (set(z1_site_cells) | basement_cells) - edge_points
    bounds = (left, right, top, bottom)
    horizontal = _network_path(
        (left, lane_y),
        {(right, lane_y)},
        bounds=bounds,
        blocked=blocked,
        preferred_axis=("y", lane_y),
    )
    if not horizontal:
        horizontal = tuple((x, lane_y) for x in range(left, right + 1))
    centerline = set(horizontal)
    centerline.update(_network_path(
        (lane_x, top),
        centerline,
        bounds=bounds,
        blocked=blocked,
        preferred_axis=("x", lane_x),
    ))
    centerline.update(_network_path(
        (lane_x, bottom),
        centerline,
        bounds=bounds,
        blocked=blocked,
        preferred_axis=("x", lane_x),
    ))

    floor_cells = set(centerline)
    for x, y in tuple(centerline):
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if left <= nx <= right and top <= ny <= bottom and (nx, ny) not in blocked:
                floor_cells.add((nx, ny))

    rng = random.Random(f"{int(world_seed)}:{chunk_x}:{chunk_y}:underground_network:sprawl")
    pocket_centers = []
    pocket_candidates = [
        (left + max(2, size // 4), top + max(2, size // 4)),
        (right - max(2, size // 4), top + max(2, size // 4)),
        (left + max(2, size // 4), bottom - max(2, size // 4)),
        (right - max(2, size // 4), bottom - max(2, size // 4)),
    ]
    rng.shuffle(pocket_candidates)
    pocket_target = 1 + int(size >= 24)
    for center in pocket_candidates:
        if len(pocket_centers) >= pocket_target:
            break
        cx, cy = int(center[0]), int(center[1])
        chamber = {
            (x, y)
            for y in range(cy - 1, cy + 2)
            for x in range(cx - 1, cx + 2)
        }
        if chamber & blocked or chamber & floor_cells:
            continue
        destination = _nearest_open_network_cell(floor_cells, center)
        if destination is None:
            continue
        spur = _network_path(center, {destination}, bounds=bounds, blocked=blocked)
        if not spur:
            continue
        floor_cells.update(spur)
        floor_cells.update(chamber)
        pocket_centers.append(center)

    site_connections = []
    direct_portals = set()
    for plan in site_plans:
        try:
            plan_z = int(plan.get("z", 0))
        except (TypeError, ValueError):
            continue
        if plan_z >= 0:
            continue
        if plan_z == UNDERGROUND_NETWORK_Z:
            entry = plan.get("entry", {}) if isinstance(plan.get("entry"), dict) else {}
            try:
                portal = (int(entry.get("x")), int(entry.get("y")))
            except (TypeError, ValueError):
                portal = _network_site_portal(plan)
            direct = True
            site_shape = set(_plan_shape_cells(plan))
            route_starts = ()
            if portal is not None:
                route_starts = tuple(
                    (int(nx), int(ny))
                    for nx, ny in (
                        (portal[0] - 1, portal[1]),
                        (portal[0] + 1, portal[1]),
                        (portal[0], portal[1] - 1),
                        (portal[0], portal[1] + 1),
                    )
                    if left <= nx <= right
                    and top <= ny <= bottom
                    and (int(nx), int(ny)) not in site_shape
                )
            if not route_starts:
                route_starts = (portal,)
        else:
            portal = _network_site_portal(plan)
            direct = False
            open_cells = (
                (x, y)
                for y in range(top, bottom + 1)
                for x in range(left, right + 1)
            )
            network_landing = _nearest_open_network_cell(open_cells, portal, blocked=blocked) if portal is not None else None
            route_starts = (network_landing,)
        if portal is None:
            continue
        destinations = set(floor_cells) - set(blocked)
        if not destinations:
            continue
        route_blocked = set(blocked)
        if direct:
            route_blocked.difference_update(route_starts)
        spur_options = tuple(
            path
            for path in (
                _network_path(route_start, destinations, bounds=bounds, blocked=route_blocked)
                for route_start in route_starts
                if route_start is not None
            )
            if path
        )
        spur = min(spur_options, key=lambda path: (len(path), path)) if spur_options else ()
        if not spur:
            continue
        if direct and portal not in spur:
            spur = (portal,) + tuple(spur)
        if direct:
            direct_portals.add(portal)
            network_landing = portal
        elif network_landing is None:
            continue
        floor_cells.update(spur)
        site_connections.append({
            "site_id": _text(plan.get("site_id")) or None,
            "building_id": _text(plan.get("building_id")) or None,
            "source_building_id": _text(plan.get("source_building_id")) or None,
            "source_building_name": _text(plan.get("source_building_name")) or _text(plan.get("name")) or "connected site",
            "x": int(portal[0]),
            "y": int(portal[1]),
            "z": int(plan_z),
            "network_x": int(network_landing[0]),
            "network_y": int(network_landing[1]),
            "network_z": UNDERGROUND_NETWORK_Z,
            "direct": bool(direct),
        })

    floor_cells.difference_update(blocked - direct_portals)
    if not floor_cells:
        return None
    profile = _underground_network_profile(district)
    route_token = random.Random(
        f"{int(world_seed)}:{chunk_x}:{chunk_y}:underground_network:route"
    ).randrange(100, 1000)
    route_code = f"U{abs(chunk_y) % 10}{abs(chunk_x) % 10}-{route_token}"
    place_name = _text(district.get("settlement_name")) or _text(district.get("region_name")) or "City"
    site_name = f"{place_name} {profile['label']} {route_code}"

    hub = _nearest_open_network_cell(
        floor_cells,
        (lane_x, lane_y),
        blocked=z1_site_cells,
    ) or min(floor_cells, key=lambda cell: (cell[1], cell[0]))
    reserved = {hub, *edge_points, *(tuple(center) for center in pocket_centers)}
    content_pool = sorted(
        (
            cell for cell in floor_cells
            if cell not in reserved
            and cell not in z1_site_cells
            and left < cell[0] < right
            and top < cell[1] < bottom
        ),
        key=lambda cell: (
            -(abs(cell[0] - hub[0]) + abs(cell[1] - hub[1])),
            cell[1],
            cell[0],
        ),
    )
    cache_point = pocket_centers[0] if pocket_centers else (content_pool[0] if content_pool else hub)
    reserved.add(cache_point)
    encounter_point = (
        pocket_centers[-1]
        if len(pocket_centers) > 1
        else next((cell for cell in content_pool if cell not in reserved), hub)
    )
    reserved.add(encounter_point)
    wildlife_points = tuple(cell for cell in content_pool if cell not in reserved)[:2]
    reserved.update(wildlife_points)
    hazard_point = next((cell for cell in content_pool if cell not in reserved), None)
    hazard_sites = ()
    if hazard_point is not None:
        hazard_row = _weighted_choice(rng, UNDERGROUND_HAZARD_ROWS)
        if hazard_row:
            hazard_sites = ({
                "name": str(hazard_row[1]),
                "x": int(hazard_point[0]),
                "y": int(hazard_point[1]),
                "z": UNDERGROUND_NETWORK_Z,
                "profile": str(hazard_row[0]),
            },)

    destination_labels = ["west service way", "east service way", "north access tunnel", "south access tunnel"]
    destination_labels.extend(
        str(row.get("source_building_name", "connected site"))
        for row in site_connections
        if str(row.get("source_building_name", "")).strip()
    )
    property_cells = sorted(set(floor_cells) - z1_site_cells)
    shape = _shape_bounds(property_cells) or {
        "left": int(hub[0]), "right": int(hub[0]), "top": int(hub[1]), "bottom": int(hub[1]),
    }
    return {
        "site_id": f"{chunk_x}:{chunk_y}:underground_network",
        "kind": ACCESS_TUNNEL_NETWORK_KIND,
        "layout_variant": str(profile["variant"]),
        "name": site_name,
        "route_code": route_code,
        "route_destinations": tuple(dict.fromkeys(destination_labels)),
        "building_id": f"{chunk_x}:{chunk_y}:underground_network",
        "anchor": {"x": int(hub[0]), "y": int(hub[1]), "z": UNDERGROUND_NETWORK_Z},
        "z": UNDERGROUND_NETWORK_Z,
        "floors": 1,
        "rooms": tuple(profile["rooms"]),
        "common_area_kind": "access_tunnel",
        "control_mode": "shared_infrastructure",
        "floor_glyph": str(profile["floor_glyph"]),
        "floor_cells": tuple({"x": int(x), "y": int(y)} for x, y in sorted(floor_cells)),
        "property_cells": tuple({"x": int(x), "y": int(y)} for x, y in property_cells),
        "footprint": shape,
        "site_connections": tuple(site_connections),
        "ambient_encounter_profile": str(profile["encounter"]),
        "ambient_encounter_spawns": ({
            "x": int(encounter_point[0]),
            "y": int(encounter_point[1]),
            "z": UNDERGROUND_NETWORK_Z,
            "profile": str(profile["encounter"]),
        },),
        "ambient_wildlife_profile": str(profile["wildlife"]),
        "ambient_wildlife_spawns": tuple({
            "x": int(point[0]),
            "y": int(point[1]),
            "z": UNDERGROUND_NETWORK_Z,
            "profile": str(profile["wildlife"]),
        } for point in wildlife_points),
        "ambient_hazard_profile": "network_hazards" if hazard_sites else "",
        "ambient_hazard_spawns": hazard_sites,
        "cache_sites": ({
            "name": "Tunnel Cache" if profile["cache"] != "contraband_light" else "Wrapped Handoff Cache",
            "x": int(cache_point[0]),
            "y": int(cache_point[1]),
            "z": UNDERGROUND_NETWORK_Z,
            "kind": "utility_cache",
            "cache_profile": str(profile["cache"]),
        },),
        "service_sites": ({
            "name": f"{route_code} Junction Marker",
            "x": int(hub[0]),
            "y": int(hub[1]),
            "z": UNDERGROUND_NETWORK_Z,
            "site_services": (),
            "fixture_type": "underground_route_marker",
            "glyph": "j",
            "display_description": "Routes: " + "; ".join(destination_labels),
        },),
    }
