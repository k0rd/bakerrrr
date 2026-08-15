"""Intent-scoped vertical routes for actors with known destinations.

The tilemap owns the physical links.  This module only chooses the next link
that advances an actor toward a destination and performs that one transition;
callers retain ownership of why the actor is travelling.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.events import Event
from game.components import Position
from game.movement_runtime import try_move_entity
from game.property_runtime import (
    building_id_from_property,
    building_id_from_structure,
    property_covering,
    property_power_cut_active,
)


@dataclass(frozen=True, slots=True)
class VerticalRouteSegment:
    source_x: int
    source_y: int
    source_z: int
    target_x: int
    target_y: int
    target_z: int
    kind: str
    building_id: str = ""

    @property
    def source(self):
        return (self.source_x, self.source_y, self.source_z)

    @property
    def target(self):
        return (self.target_x, self.target_y, self.target_z)


def _position_tuple(value):
    if isinstance(value, Position):
        return (int(value.x), int(value.y), int(value.z))
    try:
        return (int(value[0]), int(value[1]), int(value[2]))
    except (TypeError, ValueError, IndexError):
        return None


def building_id_at(sim, position):
    point = _position_tuple(position)
    if point is None:
        return ""
    x, y, z = point
    structure = sim.structure_at(x, y, z) if hasattr(sim, "structure_at") else None
    building_id = building_id_from_structure(structure)
    if building_id:
        return building_id
    return building_id_from_property(property_covering(sim, x, y, z))


def vertical_route_candidates(sim, origin, destination, *, destination_building_id=None):
    """Return authored links on this floor that advance toward destination z."""

    origin = _position_tuple(origin)
    destination = _position_tuple(destination)
    if origin is None or destination is None or origin[2] == destination[2]:
        return ()
    if destination_building_id is None:
        destination_building_id = building_id_at(sim, destination)
    destination_building_id = str(destination_building_id or "").strip()
    direction = 1 if destination[2] > origin[2] else -1
    current_gap = abs(destination[2] - origin[2])
    candidates = []
    indexed_links = getattr(sim.tilemap, "floor_links_from", None)
    link_rows = (
        indexed_links(origin[2], direction)
        if callable(indexed_links)
        else tuple(getattr(sim.tilemap, "floor_links", {}).items())
    )
    for key, link in link_rows:
        if not isinstance(key, tuple) or len(key) < 4 or not isinstance(link, dict):
            continue
        try:
            source_x, source_y, source_z, link_direction = (int(part) for part in key[:4])
            target_x = int(link.get("x"))
            target_y = int(link.get("y"))
            target_z = int(link.get("z"))
        except (TypeError, ValueError):
            continue
        if source_z != origin[2] or link_direction != direction:
            continue
        if abs(destination[2] - target_z) >= current_gap:
            continue
        source_building = building_id_at(sim, (source_x, source_y, source_z))
        target_building = building_id_at(sim, (target_x, target_y, target_z))
        if destination_building_id and destination_building_id not in {source_building, target_building}:
            continue
        segment = VerticalRouteSegment(
            source_x=source_x,
            source_y=source_y,
            source_z=source_z,
            target_x=target_x,
            target_y=target_y,
            target_z=target_z,
            kind=str(link.get("kind", "stairs") or "stairs").strip().lower(),
            building_id=destination_building_id or source_building or target_building,
        )
        approach = abs(origin[0] - source_x) + abs(origin[1] - source_y)
        onward = abs(destination[0] - target_x) + abs(destination[1] - target_y)
        candidates.append((approach + onward, approach, target_z, source_y, source_x, segment))
    candidates.sort(key=lambda row: row[:-1])
    return tuple(row[-1] for row in candidates)


def next_vertical_route_segment(sim, origin, destination, *, destination_building_id=None):
    candidates = vertical_route_candidates(
        sim,
        origin,
        destination,
        destination_building_id=destination_building_id,
    )
    return candidates[0] if candidates else None


def vertical_route_available(sim, origin, destination, *, destination_building_id=None):
    """Check structural reachability across every intervening authored floor."""

    origin = _position_tuple(origin)
    destination = _position_tuple(destination)
    if origin is None or destination is None:
        return False
    if origin[2] == destination[2]:
        return True
    if destination_building_id is None:
        destination_building_id = building_id_at(sim, destination)
    cursor = origin
    visited = set()
    max_steps = max(2, len(getattr(sim.tilemap, "tiles_by_floor", {})) + 2)
    for _ in range(max_steps):
        segment = next_vertical_route_segment(
            sim,
            cursor,
            destination,
            destination_building_id=destination_building_id,
        )
        if segment is None or segment in visited:
            return False
        visited.add(segment)
        cursor = segment.target
        if cursor[2] == destination[2]:
            return True
    return False


def _elevator_has_power(sim, segment):
    if segment.kind != "elevator":
        return True
    for point in (segment.source, segment.target):
        prop = None
        if hasattr(sim, "property_at"):
            prop = sim.property_at(*point)
        prop = prop or property_covering(sim, *point)
        if isinstance(prop, dict) and property_power_cut_active(sim, prop):
            return False
    return True


def try_vertical_transition(sim, eid, segment, *, reason="npc_floor_change"):
    """Use one physical floor link, preserving ordinary collision and events."""

    if not isinstance(segment, VerticalRouteSegment):
        return False, "missing_transition"
    pos = sim.ecs.get(Position).get(eid)
    if pos is None or (int(pos.x), int(pos.y), int(pos.z)) != segment.source:
        return False, "not_at_transition"
    direction = 1 if segment.target_z > segment.source_z else -1
    live_link = sim.tilemap.floor_transition(pos.x, pos.y, pos.z, direction)
    if not isinstance(live_link, dict):
        return False, "missing_transition"
    live_target = (int(live_link.get("x")), int(live_link.get("y")), int(live_link.get("z")))
    if live_target != segment.target:
        return False, "transition_changed"
    if not _elevator_has_power(sim, segment):
        return False, "power_cut"
    old_z = int(pos.z)
    moved, blocked_reason = try_move_entity(
        sim,
        eid,
        segment.target_x,
        segment.target_y,
        segment.target_z,
        reason=segment.kind or reason,
    )
    if not moved:
        return False, blocked_reason
    sim.emit(Event(
        "entity_changed_floor",
        eid=eid,
        x=int(pos.x),
        y=int(pos.y),
        from_z=old_z,
        to_z=int(pos.z),
        kind=segment.kind,
        reason=reason,
    ))
    return True, None


__all__ = [
    "VerticalRouteSegment",
    "building_id_at",
    "next_vertical_route_segment",
    "try_vertical_transition",
    "vertical_route_available",
    "vertical_route_candidates",
]
