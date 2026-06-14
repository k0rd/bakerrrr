"""Shared local vehicle motion helpers."""

from __future__ import annotations

from engine.events import Event

from game.components import Collider, Position, Render, VehicleState, Vitality
from game.movement_runtime import _entity_blocks, try_move_entity
from game.property_runtime import (
    property_is_vehicle as _property_is_vehicle,
    property_metadata as _property_metadata,
    vehicle_fuel_values as _vehicle_fuel_values,
    vehicle_label as _vehicle_label,
    vehicle_profile_from_property as _vehicle_profile_from_property,
)
from game.system_support.actor_runtime import _apply_downed_actor_state
from game.system_support.entity_naming import _entity_display_name
from game.system_support.fire_runtime import fire_cell_state
from game.system_support.offense_runtime import _emit_action_offense_event


VEHICLE_DIRECTIONS = (
    (0, -1),
    (1, -1),
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
)

VEHICLE_HEADING_GLYPHS = {
    (0, -1): "^",
    (1, -1): "7",
    (1, 0): ">",
    (1, 1): "J",
    (0, 1): "v",
    (-1, 1): "L",
    (-1, 0): "<",
    (-1, -1): "F",
}

VEHICLE_HEADING_LABELS = {
    (0, -1): "N",
    (1, -1): "NE",
    (1, 0): "E",
    (1, 1): "SE",
    (0, 1): "S",
    (-1, 1): "SW",
    (-1, 0): "W",
    (-1, -1): "NW",
}

LAND_ROUTE_GLYPHS = {"=", ":"}
WATER_TILE_GLYPHS = {"~"}


def normalize_vehicle_heading(dx, dy):
    step_x = 1 if dx > 0 else -1 if dx < 0 else 0
    step_y = 1 if dy > 0 else -1 if dy < 0 else 0
    if step_x == 0 and step_y == 0:
        return 0, -1
    return step_x, step_y


def ensure_vehicle_motion_state(state):
    if state is None:
        return None
    if hasattr(state, "ensure_motion_defaults"):
        return state.ensure_motion_defaults()
    state.heading_dx, state.heading_dy = normalize_vehicle_heading(
        getattr(state, "heading_dx", 0),
        getattr(state, "heading_dy", -1),
    )
    try:
        speed = int(getattr(state, "speed", 0) or 0)
    except (TypeError, ValueError):
        speed = 0
    state.speed = max(0, min(2, speed))
    state.medium = str(getattr(state, "medium", "land") or "land").strip().lower() or "land"
    return state


def vehicle_heading_tuple(state):
    state = ensure_vehicle_motion_state(state)
    if state is None:
        return 0, -1
    return normalize_vehicle_heading(getattr(state, "heading_dx", 0), getattr(state, "heading_dy", -1))


def set_vehicle_heading(state, dx, dy, tick=0):
    state = ensure_vehicle_motion_state(state)
    if state is None:
        return 0, -1
    if hasattr(state, "set_heading"):
        return state.set_heading(dx, dy, tick=tick)
    state.heading_dx, state.heading_dy = normalize_vehicle_heading(dx, dy)
    state.last_changed_tick = int(tick)
    return int(state.heading_dx), int(state.heading_dy)


def set_vehicle_speed(state, speed, tick=0):
    state = ensure_vehicle_motion_state(state)
    if state is None:
        return 0
    if hasattr(state, "set_speed"):
        return state.set_speed(speed, tick=tick)
    try:
        speed = int(speed or 0)
    except (TypeError, ValueError):
        speed = 0
    state.speed = max(0, min(2, speed))
    state.last_changed_tick = int(tick)
    return int(state.speed)


def rotate_vehicle_heading(state, turn, tick=0):
    state = ensure_vehicle_motion_state(state)
    if state is None:
        return 0, -1
    heading = vehicle_heading_tuple(state)
    try:
        idx = VEHICLE_DIRECTIONS.index(heading)
    except ValueError:
        idx = 0
    delta = -1 if int(turn) < 0 else 1
    return set_vehicle_heading(state, *VEHICLE_DIRECTIONS[(idx + delta) % len(VEHICLE_DIRECTIONS)], tick=tick)


def vehicle_heading_glyph(state):
    return VEHICLE_HEADING_GLYPHS.get(vehicle_heading_tuple(state), "^")


def vehicle_heading_label(state):
    return VEHICLE_HEADING_LABELS.get(vehicle_heading_tuple(state), "N")


def vehicle_medium_for_property(prop, default="land"):
    if not _property_is_vehicle(prop):
        return str(default or "land")
    metadata = _property_metadata(prop)
    for key in ("vehicle_medium", "medium"):
        value = str(metadata.get(key, "") or "").strip().lower()
        if value:
            return value
    profile = _vehicle_profile_from_property(prop) or {}
    value = str(profile.get("vehicle_medium", profile.get("medium", "")) or "").strip().lower()
    return value or str(default or "land")


def sync_vehicle_property_position(sim, prop, x, y, z=0):
    if not _property_is_vehicle(prop):
        return
    property_id = str(prop.get("id", "")).strip()
    if property_id:
        sim.move_property(property_id, int(x), int(y), int(z))
    metadata = _property_metadata(prop)
    metadata["chunk"] = sim.chunk_coords(int(x), int(y))


def local_route_accessible_at(sim, x, y, z=0, *, ignore_property_id=None, medium="land"):
    tile = sim.tilemap.tile_at(int(x), int(y), int(z))
    glyph = str(getattr(tile, "glyph", "") or "")[:1]
    medium = str(medium or "land").strip().lower() or "land"
    if medium == "water":
        if not tile or glyph not in WATER_TILE_GLYPHS:
            return False
        route_like = False
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                neighbor = sim.tilemap.tile_at(int(x) + dx, int(y) + dy, int(z))
                neighbor_glyph = str(getattr(neighbor, "glyph", "") or "")[:1]
                if neighbor and (bool(getattr(neighbor, "walkable", False)) or neighbor_glyph in LAND_ROUTE_GLYPHS or neighbor_glyph == "_"):
                    route_like = True
                    break
            if route_like:
                break
    else:
        route_like = glyph in LAND_ROUTE_GLYPHS
        if not tile or not bool(getattr(tile, "walkable", False)):
            return False
    if not route_like:
        return False
    if sim.structure_at(int(x), int(y), int(z)) is not None:
        return False
    covering = sim.property_covering(int(x), int(y), int(z))
    if (
        isinstance(covering, dict)
        and str(covering.get("id", "")).strip() != str(ignore_property_id or "").strip()
    ):
        return False
    return True


def vehicle_local_block_reason(sim, eid, vehicle_prop, x, y, z=0, *, medium=None):
    x = int(x)
    y = int(y)
    z = int(z)
    medium = str(medium or vehicle_medium_for_property(vehicle_prop)).strip().lower() or "land"
    if sim.detail_for_xy(x, y) == "unloaded":
        return "out_of_bounds"
    if not sim.tilemap.in_bounds(x, y):
        return "out_of_bounds"
    tile = sim.tilemap.tile_at(x, y, z)
    glyph = str(getattr(tile, "glyph", "") or "")[:1]
    if not tile:
        return "blocked_tile"
    if medium == "water":
        if glyph not in WATER_TILE_GLYPHS:
            return "blocked_tile"
    elif not bool(getattr(tile, "walkable", False)):
        return "blocked_tile"

    fire_cell = fire_cell_state(sim, x, y, z)
    if isinstance(fire_cell, dict) and int(fire_cell.get("fire_intensity", 0) or 0) > 0:
        return "active_fire"

    active_vehicle_id = str((vehicle_prop or {}).get("id", "")).strip()
    covering = sim.property_covering(x, y, z)
    if isinstance(covering, dict) and str(covering.get("id", "")).strip() != active_vehicle_id:
        return "property_tile"
    if sim.structure_at(x, y, z) is not None:
        return "property_tile"

    blocked, blocker_eid = _entity_blocks(sim, eid, x, y, z)
    if blocked:
        return f"blocked_entity:{blocker_eid}"
    return None


def emit_vehicle_blocked(sim, eid, vehicle_prop=None, *, reason="blocked", **extra):
    payload = {
        "eid": eid,
        "reason": str(reason or "blocked"),
    }
    if _property_is_vehicle(vehicle_prop):
        payload.update({
            "vehicle_id": vehicle_prop.get("id"),
            "vehicle_name": _vehicle_label(vehicle_prop),
        })
        fuel, fuel_capacity = _vehicle_fuel_values(vehicle_prop)
        payload.update({
            "fuel": fuel,
            "fuel_capacity": fuel_capacity,
        })
    payload.update(extra)
    sim.emit(Event("vehicle_action_blocked", **payload))


def _vehicle_collision_damage(vehicle_prop, speed):
    profile = _vehicle_profile_from_property(vehicle_prop) or {}
    try:
        power = int(profile.get("power", 5) or 5)
    except (TypeError, ValueError):
        power = 5
    try:
        durability = int(profile.get("durability", 5) or 5)
    except (TypeError, ValueError):
        durability = 5
    speed = max(1, min(2, int(speed or 1)))
    raw = (4 + max(1, min(10, power))) * speed
    if speed > 1:
        raw += max(0, min(10, durability)) // 2
    return max(1, int(raw))


def _apply_vehicle_collision_damage(sim, driver_eid, target_eid, vehicle_prop, speed, x, y, z):
    vitalities = sim.ecs.get(Vitality)
    colliders = sim.ecs.get(Collider)
    renders = sim.ecs.get(Render)
    vitality = vitalities.get(target_eid)
    if vitality is None:
        return 0, False
    if bool(getattr(vitality, "downed", False)):
        return 0, True

    raw_damage = _vehicle_collision_damage(vehicle_prop, speed)
    final_damage = max(1, int(raw_damage))
    vitality.hp = max(0, int(vitality.hp) - final_damage)
    sim.emit(Event(
        "entity_damaged",
        target_eid=target_eid,
        source_eid=driver_eid,
        weapon_id="vehicle",
        damage_kind="vehicle",
        raw_damage=raw_damage,
        damage=final_damage,
        cover_absorb=0.0,
        armor_absorb=0.0,
        armor_name=None,
        hp=vitality.hp,
        max_hp=vitality.max_hp,
        x=int(x),
        y=int(y),
        z=int(z),
    ))

    downed = int(vitality.hp) <= 0
    if downed:
        vitality.downed_count += 1
        vitality.downed = True
        vitality.downed_tick = int(getattr(sim, "tick", 0))
        setattr(vitality, "last_attacker_eid", driver_eid)
        setattr(vitality, "death_reason", "vehicle_collision")
        if target_eid == getattr(sim, "player_eid", None):
            sim.emit(Event(
                "player_downed",
                target_eid=target_eid,
                source_eid=driver_eid,
                source_name=_entity_display_name(sim, driver_eid, title_case=True) or "",
                weapon_id="vehicle",
                reason="vehicle_collision",
                damage_kind="vehicle",
                x=int(x),
                y=int(y),
                z=int(z),
            ))
        else:
            _apply_downed_actor_state(sim, target_eid, tick=getattr(sim, "tick", 0))
            collider = colliders.get(target_eid)
            if collider:
                collider.blocks = False
            render = renders.get(target_eid)
            if render:
                render.glyph = "x"
            sim.emit(Event(
                "npc_downed",
                target_eid=target_eid,
                source_eid=driver_eid,
                weapon_id="vehicle",
                x=int(x),
                y=int(y),
                z=int(z),
            ))
    return final_damage, downed


def apply_vehicle_collision(sim, driver_eid, target_eid, vehicle_prop, speed, x, y, z):
    target_name = _entity_display_name(sim, target_eid, title_case=False) or "someone"
    damage, downed = _apply_vehicle_collision_damage(sim, driver_eid, target_eid, vehicle_prop, speed, x, y, z)
    sim.emit(Event(
        "vehicle_collision",
        eid=driver_eid,
        driver_eid=driver_eid,
        target_eid=target_eid,
        target_name=target_name,
        vehicle_id=(vehicle_prop or {}).get("id") if isinstance(vehicle_prop, dict) else None,
        vehicle_name=_vehicle_label(vehicle_prop) if _property_is_vehicle(vehicle_prop) else "vehicle",
        speed=max(1, min(2, int(speed or 1))),
        damage=damage,
        target_downed=downed,
        x=int(x),
        y=int(y),
        z=int(z),
    ))
    sim.emit(Event(
        "noise",
        source_eid=driver_eid,
        x=int(x),
        y=int(y),
        z=int(z),
        radius=5 + (2 * max(1, min(2, int(speed or 1)))),
        cause="vehicle_collision",
        target_eid=target_eid,
    ))
    if damage > 0:
        context = "unarmed_assault" if int(speed or 1) <= 1 else "melee_assault"
        score = 28 if int(speed or 1) <= 1 else 48
        _emit_action_offense_event(
            sim,
            driver_eid,
            "vehicle_ram",
            int(x),
            int(y),
            int(z),
            context=context,
            score=score,
            target_eid=target_eid,
            victim_eid=target_eid,
            victim_name=target_name,
            target_name=target_name,
            target_x=int(x),
            target_y=int(y),
            target_z=int(z),
            vehicle_id=(vehicle_prop or {}).get("id") if isinstance(vehicle_prop, dict) else None,
            vehicle_name=_vehicle_label(vehicle_prop) if _property_is_vehicle(vehicle_prop) else "vehicle",
        )
    return damage, downed


def try_vehicle_step(sim, eid, vehicle_prop, target_x, target_y, target_z=0, *, speed=1, reason="vehicle_move"):
    target_x = int(target_x)
    target_y = int(target_y)
    target_z = int(target_z)
    medium = vehicle_medium_for_property(vehicle_prop)
    block_reason = vehicle_local_block_reason(
        sim,
        eid,
        vehicle_prop,
        target_x,
        target_y,
        target_z,
        medium=medium,
    )
    if block_reason:
        if block_reason.startswith("blocked_entity:"):
            try:
                blocker_eid = int(block_reason.split(":", 1)[1])
            except (TypeError, ValueError, IndexError):
                blocker_eid = None
            if blocker_eid is not None and int(speed or 0) > 0:
                apply_vehicle_collision(
                    sim,
                    eid,
                    blocker_eid,
                    vehicle_prop,
                    speed,
                    target_x,
                    target_y,
                    target_z,
                )
                return False, "collision"
        return False, block_reason

    if medium == "water":
        positions = sim.ecs.get(Position)
        pos = positions.get(eid)
        if not pos:
            return False, "missing_position"
        old_x = int(pos.x)
        old_y = int(pos.y)
        old_z = int(pos.z)
        sim.tilemap.move_entity(
            eid,
            oldx=old_x,
            oldy=old_y,
            oldz=old_z,
            newx=target_x,
            newy=target_y,
            newz=target_z,
        )
        pos.x = target_x
        pos.y = target_y
        pos.z = target_z
        sim.emit(Event(
            "entity_moved",
            eid=eid,
            old_x=old_x,
            old_y=old_y,
            old_z=old_z,
            x=target_x,
            y=target_y,
            z=target_z,
            reason=reason,
        ))
    else:
        moved, move_reason = try_move_entity(
            sim,
            eid,
            target_x,
            target_y,
            target_z,
            reason=reason,
        )
        if not moved:
            return False, move_reason or "blocked_tile"

    sync_vehicle_property_position(sim, vehicle_prop, target_x, target_y, target_z)
    return True, None


def active_vehicle_property(sim, state):
    state = ensure_vehicle_motion_state(state)
    if not state or not getattr(state, "active_vehicle_id", None):
        return None
    prop = sim.properties.get(state.active_vehicle_id)
    if not _property_is_vehicle(prop):
        return None
    return prop


def vehicle_state_for(sim, eid):
    return ensure_vehicle_motion_state(sim.ecs.get(VehicleState).get(eid))


def position_for(sim, eid):
    return sim.ecs.get(Position).get(eid)
