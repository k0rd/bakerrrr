"""Shared local vehicle motion helpers."""

from __future__ import annotations

import math

from engine.events import Event

from game.components import Collider, Position, Render, VehicleState, Vitality
from game.movement_runtime import _entity_blocks, try_move_entity
from game.property_runtime import (
    property_aperture_at as _property_aperture_at,
    property_enclosing_structure as _property_enclosing_structure,
    property_is_vehicle as _property_is_vehicle,
    property_metadata as _property_metadata,
    vehicle_fuel_values as _vehicle_fuel_values,
    vehicle_label as _vehicle_label,
    vehicle_profile_from_property as _vehicle_profile_from_property,
)
from game.quick_travel_ramps import property_allows_vehicle_route_access
from game.system_support.actor_runtime import _apply_downed_actor_state
from game.system_support.entity_naming import _entity_display_name
from game.system_support.building_repair_runtime import record_building_damage as _record_building_damage
from game.system_support.fire_runtime import fire_cell_state
from game.system_support.offense_runtime import _emit_action_offense_event
from game.system_support.structure_damage_runtime import (
    STRUCTURE_MAX_HP,
    apply_structural_damage as _apply_structural_damage,
    structural_surface_kind as _structural_surface_kind,
    structure_is_broken as _structure_is_broken,
)
from game.vehicle_explosion_runtime import arm_vehicle_explosion


MAX_VEHICLE_SPEED = 4
VEHICLE_CLASS_TOP_SPEED = {
    "micro": 2,
    "skiff": 2,
    "compact": 3,
    "hatchback": 3,
    "sedan": 3,
    "wagon": 3,
    "van": 3,
    "launch": 3,
    "coupe": 4,
    "pickup": 4,
    "suv": 4,
    "utility": 4,
}

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
SOFT_VEHICLE_BLOCK_REASONS = {"out_of_bounds", "chunk_unready"}


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
    state.speed = max(0, min(MAX_VEHICLE_SPEED, speed))
    state.medium = str(getattr(state, "medium", "land") or "land").strip().lower() or "land"
    return state


def _int_or_default(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def vehicle_top_speed(vehicle_prop):
    profile = _vehicle_profile_from_property(vehicle_prop) or {}
    if not bool(profile.get("usable", True)):
        return 0
    vehicle_class = str(profile.get("vehicle_class", "sedan") or "sedan").strip().lower() or "sedan"
    top_speed = int(VEHICLE_CLASS_TOP_SPEED.get(vehicle_class, 3))
    power = max(1, min(10, _int_or_default(profile.get("power"), 5)))
    durability = max(0, min(10, _int_or_default(profile.get("durability"), 5)))
    if durability <= 0:
        return 0

    if power <= 2:
        top_speed -= 1
    elif power >= 8 and top_speed < MAX_VEHICLE_SPEED:
        top_speed += 1

    if durability <= 2:
        top_speed -= 2
    elif durability <= 4:
        top_speed -= 1
    elif durability >= 9 and power >= 7 and top_speed < MAX_VEHICLE_SPEED:
        top_speed += 1

    return max(1, min(MAX_VEHICLE_SPEED, int(top_speed)))


def clamp_vehicle_speed(vehicle_prop, speed):
    try:
        speed = int(speed or 0)
    except (TypeError, ValueError):
        speed = 0
    return max(0, min(vehicle_top_speed(vehicle_prop), speed))


def vehicle_heading_tuple(state):
    if isinstance(state, (tuple, list)) and len(state) >= 2:
        return normalize_vehicle_heading(state[0], state[1])
    state = ensure_vehicle_motion_state(state)
    if state is None:
        return 0, -1
    return normalize_vehicle_heading(getattr(state, "heading_dx", 0), getattr(state, "heading_dy", -1))


def vehicle_property_heading(vehicle_prop):
    if not _property_is_vehicle(vehicle_prop):
        return 0, -1
    metadata = _property_metadata(vehicle_prop)
    return normalize_vehicle_heading(
        metadata.get("vehicle_heading_dx", metadata.get("heading_dx", 0)),
        metadata.get("vehicle_heading_dy", metadata.get("heading_dy", -1)),
    )


def sync_vehicle_property_heading(vehicle_prop, state=None, *, dx=0, dy=-1):
    if not _property_is_vehicle(vehicle_prop):
        return 0, -1
    if state is not None:
        heading_dx, heading_dy = vehicle_heading_tuple(state)
    else:
        heading_dx, heading_dy = normalize_vehicle_heading(dx, dy)
    metadata = _property_metadata(vehicle_prop)
    metadata["vehicle_heading_dx"] = int(heading_dx)
    metadata["vehicle_heading_dy"] = int(heading_dy)
    metadata["vehicle_heading"] = VEHICLE_HEADING_LABELS.get((heading_dx, heading_dy), "N")
    return int(heading_dx), int(heading_dy)


def set_vehicle_heading(state, dx, dy, tick=0):
    state = ensure_vehicle_motion_state(state)
    if state is None:
        return 0, -1
    if hasattr(state, "set_heading"):
        return state.set_heading(dx, dy, tick=tick)
    state.heading_dx, state.heading_dy = normalize_vehicle_heading(dx, dy)
    state.last_changed_tick = int(tick)
    return int(state.heading_dx), int(state.heading_dy)


def set_vehicle_speed(state, speed, tick=0, vehicle_prop=None):
    state = ensure_vehicle_motion_state(state)
    if state is None:
        return 0
    try:
        speed = int(speed or 0)
    except (TypeError, ValueError):
        speed = 0
    if _property_is_vehicle(vehicle_prop):
        speed = clamp_vehicle_speed(vehicle_prop, speed)
    else:
        speed = max(0, min(MAX_VEHICLE_SPEED, speed))
    if hasattr(state, "set_speed"):
        return state.set_speed(speed, tick=tick)
    state.speed = speed
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


def vehicle_is_usable(vehicle_prop):
    if not _property_is_vehicle(vehicle_prop):
        return False
    profile = _vehicle_profile_from_property(vehicle_prop) or {}
    if not bool(profile.get("usable", True)):
        return False
    return max(0, min(10, _int_or_default(profile.get("durability"), 5))) > 0


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
        and not property_allows_vehicle_route_access(covering)
    ):
        return False
    return True


def _ensure_loaded_vehicle_target_terrain(sim, x, y):
    try:
        chunk_key = sim.chunk_coords(int(x), int(y))
    except (TypeError, ValueError, AttributeError):
        return False
    loaded_chunks = getattr(getattr(sim, "world", None), "loaded_chunks", {}) or {}
    if chunk_key not in loaded_chunks:
        return False
    if chunk_key in getattr(sim, "realized_chunks", set()):
        return True

    ensure = getattr(sim, "ensure_chunk_terrain", None)
    if not callable(ensure):
        return True
    changed = bool(ensure(chunk_key[0], chunk_key[1]))
    if changed:
        reapply = getattr(sim, "reapply_door_states", None)
        if callable(reapply):
            reapply(chunk=chunk_key)
    return True


def _vehicle_structural_surface(sim, x, y, z=0):
    prop = _property_enclosing_structure(sim, int(x), int(y), int(z))
    if not isinstance(prop, dict):
        return None, None, "", False
    aperture = _property_aperture_at(prop, int(x), int(y), int(z))
    kind = _structural_surface_kind(
        sim,
        prop,
        int(x),
        int(y),
        int(z),
        aperture=aperture,
    )
    broken = bool(kind) and _structure_is_broken(
        sim,
        prop,
        int(x),
        int(y),
        int(z),
        kind=kind,
    )
    return prop, aperture, str(kind or ""), bool(broken)


def vehicle_local_block_reason(sim, eid, vehicle_prop, x, y, z=0, *, medium=None):
    x = int(x)
    y = int(y)
    z = int(z)
    medium = str(medium or vehicle_medium_for_property(vehicle_prop)).strip().lower() or "land"
    if not sim.tilemap.in_bounds(x, y):
        return "out_of_bounds"
    if sim.detail_for_xy(x, y) == "unloaded":
        return "chunk_unready"
    tile = sim.tilemap.tile_at(x, y, z)
    if not tile and _ensure_loaded_vehicle_target_terrain(sim, x, y):
        tile = sim.tilemap.tile_at(x, y, z)
    glyph = str(getattr(tile, "glyph", "") or "")[:1]
    if not tile:
        return "chunk_unready"
    structure_prop, _aperture, structure_kind, structure_broken = _vehicle_structural_surface(sim, x, y, z)
    if medium == "water":
        if glyph not in WATER_TILE_GLYPHS:
            return "blocked_tile"
    elif not bool(getattr(tile, "walkable", False)):
        if structure_kind in {"window", "door", "wall"} and not structure_broken:
            return structure_kind
        return "blocked_tile"

    fire_cell = fire_cell_state(sim, x, y, z)
    if isinstance(fire_cell, dict) and int(fire_cell.get("fire_intensity", 0) or 0) > 0:
        return "active_fire"

    active_vehicle_id = str((vehicle_prop or {}).get("id", "")).strip()
    covering = sim.property_covering(x, y, z)
    broken_surface_owns_covering = bool(
        structure_broken
        and isinstance(structure_prop, dict)
        and isinstance(covering, dict)
        and str(structure_prop.get("id", "")).strip() == str(covering.get("id", "")).strip()
    )
    if (
        isinstance(covering, dict)
        and str(covering.get("id", "")).strip() != active_vehicle_id
        and not property_allows_vehicle_route_access(covering)
        and not broken_surface_owns_covering
    ):
        return "property_tile"
    if sim.structure_at(x, y, z) is not None and not structure_broken:
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
    speed = max(1, min(vehicle_top_speed(vehicle_prop), int(speed or 1)))
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


def _vehicle_durability(vehicle_prop):
    metadata = _property_metadata(vehicle_prop)
    return max(0, min(10, _int_or_default(metadata.get("durability"), 5)))


def apply_vehicle_durability_loss(sim, vehicle_prop, amount=1, *, cause="vehicle_crash"):
    if not _property_is_vehicle(vehicle_prop):
        return 0, 0, 0
    loss = max(0, int(amount or 0))
    before = _vehicle_durability(vehicle_prop)
    after = max(0, before - loss)
    metadata = _property_metadata(vehicle_prop)
    metadata["durability"] = int(after)
    metadata["last_vehicle_damage_cause"] = str(cause or "vehicle_crash")
    metadata["vehicle_usable"] = bool(after > 0)
    metadata["vehicle_broken"] = bool(after <= 0)
    if before > 0 and after <= 0:
        metadata["vehicle_explosion_durability_before"] = int(before)
        metadata["vehicle_explosion_durability_lost"] = int(before - after)
        arm_vehicle_explosion(sim, vehicle_prop, cause=cause)
    return int(before), int(after), max(0, int(before) - int(after))


def _driver_crash_damage_amount(vehicle_prop, speed, surface_kind="medium", *, durability_before=None, durability_after=None, durability_lost=0):
    speed = max(0, int(speed or 0))
    surface_kind = str(surface_kind or "medium").strip().lower()
    before = _vehicle_durability(vehicle_prop) if durability_before is None else max(0, int(durability_before or 0))
    after = _vehicle_durability(vehicle_prop) if durability_after is None else max(0, int(durability_after or 0))
    lost = max(0, int(durability_lost or 0))
    if speed < 3 and after > 0:
        return 0
    damage = max(0, speed - 2)
    if surface_kind == "hard":
        damage += 1
    elif surface_kind == "soft":
        damage -= 1
    if after <= 0:
        damage += 1
        overflow = max(0, lost - before)
        if overflow > 0:
            damage += min(2, overflow)
    elif before >= 7:
        damage -= 1
    return max(0, min(6, int(damage)))


def _apply_driver_crash_damage(
    sim,
    driver_eid,
    vehicle_prop,
    speed,
    x,
    y,
    z,
    *,
    surface_kind="medium",
    durability_before=None,
    durability_after=None,
    durability_lost=0,
):
    damage = _driver_crash_damage_amount(
        vehicle_prop,
        speed,
        surface_kind=surface_kind,
        durability_before=durability_before,
        durability_after=durability_after,
        durability_lost=durability_lost,
    )
    if damage <= 0 or driver_eid is None:
        return 0, False
    vitalities = sim.ecs.get(Vitality)
    vitality = vitalities.get(driver_eid)
    if vitality is None or bool(getattr(vitality, "downed", False)):
        return 0, bool(vitality and getattr(vitality, "downed", False))
    vitality.hp = max(0, int(vitality.hp) - int(damage))
    sim.emit(Event(
        "entity_damaged",
        target_eid=driver_eid,
        source_eid=driver_eid,
        weapon_id="vehicle_crash",
        damage_kind="vehicle_crash",
        raw_damage=int(damage),
        damage=int(damage),
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
        setattr(vitality, "death_reason", "vehicle_crash")
        if driver_eid == getattr(sim, "player_eid", None):
            sim.emit(Event(
                "player_downed",
                target_eid=driver_eid,
                source_eid=driver_eid,
                source_name="",
                weapon_id="vehicle_crash",
                reason="vehicle_crash",
                damage_kind="vehicle_crash",
                x=int(x),
                y=int(y),
                z=int(z),
            ))
        else:
            _apply_downed_actor_state(sim, driver_eid, tick=getattr(sim, "tick", 0))
    return int(damage), bool(downed)


def _vehicle_crash_repair_kind(block_reason):
    reason = str(block_reason or "").strip().lower()
    if "window" in reason:
        return "window"
    if "door" in reason:
        return "door"
    return "wall"


def _record_vehicle_infrastructure_damage(sim, driver_eid, x, y, z, block_reason):
    prop = _property_enclosing_structure(sim, int(x), int(y), int(z))
    if not isinstance(prop, dict):
        return None
    record = _record_building_damage(
        sim,
        prop,
        int(x),
        int(y),
        int(z),
        kind=_vehicle_crash_repair_kind(block_reason),
        cause="vehicle_crash",
        offender_eid=driver_eid,
    )
    if record is None:
        return None
    return prop


def _vehicle_crash_surface_kind(sim, x, y, z, block_reason):
    reason = str(block_reason or "").strip().lower()
    if reason in {"property_tile", "closed_property", "locked_property", "door_access_denied"}:
        return "hard"
    if reason in {"closed_door", "locked_door"}:
        return "medium"
    if reason == "active_fire":
        return "soft"

    tile = sim.tilemap.tile_at(int(x), int(y), int(z))
    glyph = str(getattr(tile, "glyph", "") or "")[:1]
    if sim.structure_at(int(x), int(y), int(z)) is not None:
        return "hard"
    if glyph in {"#", "B", "b"}:
        return "hard"
    if glyph in {"+", "/", "^"}:
        return "medium"
    if glyph in {"~", ",", "_"}:
        return "soft"
    return "medium"


def _vehicle_crash_durability_loss(speed, surface_kind):
    speed = max(1, int(speed or 1))
    surface_kind = str(surface_kind or "medium").strip().lower()
    base = speed + max(0, speed - 2)
    multiplier = {
        "soft": 0.55,
        "medium": 0.80,
        "hard": 1.00,
    }.get(surface_kind, 0.80)
    return max(1, min(10, int(math.ceil(float(base) * float(multiplier)))))


def _vehicle_structure_impact_damage(vehicle_prop, speed, surface_kind):
    profile = _vehicle_profile_from_property(vehicle_prop) or {}
    power = max(1, min(10, _int_or_default(profile.get("power"), 5)))
    durability = max(0, min(10, _int_or_default(profile.get("durability"), 5)))
    vehicle_class = str(profile.get("vehicle_class", "sedan") or "sedan").strip().lower()
    class_bonus = {
        "micro": -2,
        "compact": -1,
        "hatchback": -1,
        "coupe": -1,
        "sedan": 0,
        "wagon": 1,
        "suv": 2,
        "van": 2,
        "utility": 3,
        "pickup": 3,
        "truck": 4,
        "bus": 5,
        "armored": 6,
        "military": 7,
    }.get(vehicle_class, 0)
    impact_speed = max(1, min(vehicle_top_speed(vehicle_prop), int(speed or 1)))
    damage = (impact_speed * 8) + (power * 2) + (durability // 2) + class_bonus
    if str(surface_kind or "").strip().lower() == "window":
        damage = max(damage, STRUCTURE_MAX_HP["window"] + 1)
    return max(1, int(damage))


def _apply_vehicle_structural_impact(sim, driver_eid, vehicle_prop, speed, x, y, z):
    prop, aperture, surface_kind, already_broken = _vehicle_structural_surface(sim, x, y, z)
    if not isinstance(prop, dict) or not surface_kind or already_broken:
        return None
    damage = _vehicle_structure_impact_damage(vehicle_prop, speed, surface_kind)
    result = _apply_structural_damage(
        sim,
        prop,
        int(x),
        int(y),
        int(z),
        amount=damage,
        kind=surface_kind,
        aperture_kind=(aperture or {}).get("kind", surface_kind),
        cause="vehicle_impact",
        damage_kind="vehicle_collision",
        weapon_id="vehicle",
        offender_eid=driver_eid,
    )
    result["property_id"] = result.get("property_id") or prop.get("id")
    result["property_name"] = result.get("property_name") or prop.get("name")
    result["surface_kind"] = str(result.get("surface_kind") or surface_kind)
    owns_property = prop.get("owner_eid") == driver_eid or (
        driver_eid == getattr(sim, "player_eid", None)
        and str(prop.get("owner_tag", "") or "").strip().lower() == "player"
    )
    if bool(result.get("damaged")) and not owns_property:
        severity = {"window": 46, "door": 54, "wall": 62}.get(surface_kind, 48)
        _emit_action_offense_event(
            sim,
            driver_eid,
            "vehicle_structure_impact",
            int(x),
            int(y),
            int(z),
            context="tamper",
            score=severity,
            property_id=prop.get("id"),
            property_name=prop.get("name"),
            structure_kind=surface_kind,
            vehicle_id=(vehicle_prop or {}).get("id"),
            vehicle_name=_vehicle_label(vehicle_prop),
        )
    return result


def _apply_vehicle_structure_breakthrough(sim, driver_eid, vehicle_prop, speed, result, x, y, z):
    surface_kind = str((result or {}).get("surface_kind", "") or "").strip().lower()
    if surface_kind not in {"window", "door"} or not bool((result or {}).get("broken")):
        return False
    wear = 1 if surface_kind == "window" else max(1, int(math.ceil(max(1, int(speed or 1)) / 2.0)))
    before, after, lost = apply_vehicle_durability_loss(
        sim,
        vehicle_prop,
        wear,
        cause=f"vehicle_{surface_kind}_breakthrough",
    )
    state = vehicle_state_for(sim, driver_eid)
    if state is not None:
        set_vehicle_speed(
            state,
            max(0, int(getattr(state, "speed", speed) or speed) - 1),
            tick=getattr(sim, "tick", 0),
            vehicle_prop=vehicle_prop,
        )
    sim.emit(Event(
        "vehicle_structure_breached",
        eid=driver_eid,
        driver_eid=driver_eid,
        vehicle_id=(vehicle_prop or {}).get("id"),
        vehicle_name=_vehicle_label(vehicle_prop),
        property_id=(result or {}).get("property_id"),
        property_name=(result or {}).get("property_name"),
        surface_kind=surface_kind,
        speed=max(1, int(speed or 1)),
        structure_damage=int((result or {}).get("damage", 0) or 0),
        durability_before=int(before),
        durability_after=int(after),
        durability_lost=int(lost),
        vehicle_broken=bool(after <= 0),
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
        radius=7 + (2 * max(1, int(speed or 1))),
        cause=f"vehicle_{surface_kind}_breakthrough",
        property_id=(result or {}).get("property_id"),
        vehicle_id=(vehicle_prop or {}).get("id"),
    ))
    return after > 0


def apply_vehicle_crash(
    sim,
    driver_eid,
    vehicle_prop,
    speed,
    x,
    y,
    z,
    *,
    block_reason="blocked",
    structural_result=None,
):
    if not _property_is_vehicle(vehicle_prop):
        return None
    impact_speed = max(1, min(vehicle_top_speed(vehicle_prop), int(speed or 1)))
    surface_kind = _vehicle_crash_surface_kind(sim, x, y, z, block_reason)
    durability_loss = _vehicle_crash_durability_loss(impact_speed, surface_kind)
    before, after, lost = apply_vehicle_durability_loss(
        sim,
        vehicle_prop,
        durability_loss,
        cause="vehicle_crash",
    )
    driver_damage, driver_downed = _apply_driver_crash_damage(
        sim,
        driver_eid,
        vehicle_prop,
        impact_speed,
        x,
        y,
        z,
        surface_kind=surface_kind,
        durability_before=before,
        durability_after=after,
        durability_lost=lost,
    )
    if not isinstance(structural_result, dict):
        structural_result = _apply_vehicle_structural_impact(sim, driver_eid, vehicle_prop, speed, x, y, z)
    damaged_prop = None
    if isinstance(structural_result, dict):
        damaged_prop = getattr(sim, "properties", {}).get(str(structural_result.get("property_id") or ""))
    if not isinstance(damaged_prop, dict):
        damaged_prop = _record_vehicle_infrastructure_damage(
            sim,
            driver_eid,
            x,
            y,
            z,
            block_reason,
        )
    sim.emit(Event(
        "vehicle_crash",
        eid=driver_eid,
        driver_eid=driver_eid,
        vehicle_id=vehicle_prop.get("id"),
        vehicle_name=_vehicle_label(vehicle_prop),
        speed=int(impact_speed),
        top_speed=vehicle_top_speed(vehicle_prop),
        impact_kind=str(block_reason or "blocked"),
        impact_surface=str(surface_kind),
        durability_before=int(before),
        durability_after=int(after),
        durability_lost=int(lost),
        vehicle_broken=bool(after <= 0),
        driver_damage=int(driver_damage),
        driver_downed=bool(driver_downed),
        damaged_property_id=(damaged_prop or {}).get("id") if isinstance(damaged_prop, dict) else None,
        structure_kind=(structural_result or {}).get("surface_kind") if isinstance(structural_result, dict) else None,
        structure_damage=int((structural_result or {}).get("damage", 0) or 0) if isinstance(structural_result, dict) else 0,
        structure_broken=bool((structural_result or {}).get("broken", False)) if isinstance(structural_result, dict) else False,
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
        radius=6 + (2 * int(impact_speed)),
        cause="vehicle_crash",
    ))
    return {
        "speed": int(impact_speed),
        "durability_before": int(before),
        "durability_after": int(after),
        "durability_lost": int(lost),
        "vehicle_broken": bool(after <= 0),
        "impact_surface": str(surface_kind),
        "driver_damage": int(driver_damage),
        "driver_downed": bool(driver_downed),
        "damaged_property_id": (damaged_prop or {}).get("id") if isinstance(damaged_prop, dict) else None,
    }


def apply_vehicle_collision(sim, driver_eid, target_eid, vehicle_prop, speed, x, y, z):
    impact_speed = max(1, min(vehicle_top_speed(vehicle_prop), int(speed or 1)))
    wear_loss = 0 if impact_speed < 2 else 1 if impact_speed < 4 else 2
    durability_before, durability_after, durability_lost = apply_vehicle_durability_loss(
        sim,
        vehicle_prop,
        wear_loss,
        cause="vehicle_collision",
    )
    target_name = _entity_display_name(sim, target_eid, title_case=False) or "someone"
    damage, downed = _apply_vehicle_collision_damage(sim, driver_eid, target_eid, vehicle_prop, impact_speed, x, y, z)
    sim.emit(Event(
        "vehicle_collision",
        eid=driver_eid,
        driver_eid=driver_eid,
        target_eid=target_eid,
        target_name=target_name,
        vehicle_id=(vehicle_prop or {}).get("id") if isinstance(vehicle_prop, dict) else None,
        vehicle_name=_vehicle_label(vehicle_prop) if _property_is_vehicle(vehicle_prop) else "vehicle",
        speed=int(impact_speed),
        top_speed=vehicle_top_speed(vehicle_prop) if _property_is_vehicle(vehicle_prop) else MAX_VEHICLE_SPEED,
        durability_before=int(durability_before),
        durability_after=int(durability_after),
        durability_lost=int(durability_lost),
        vehicle_broken=bool(durability_after <= 0),
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
        radius=5 + (2 * int(impact_speed)),
        cause="vehicle_collision",
        target_eid=target_eid,
    ))
    if damage > 0:
        context = "unarmed_assault" if int(impact_speed) <= 1 else "melee_assault"
        score = 28 if int(impact_speed) <= 1 else 48
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
    structural_result = None
    if block_reason in {"window", "door", "wall"} and medium != "water":
        structural_result = _apply_vehicle_structural_impact(
            sim,
            eid,
            vehicle_prop,
            speed,
            target_x,
            target_y,
            target_z,
        )
        if block_reason in {"window", "door"} and _apply_vehicle_structure_breakthrough(
            sim,
            eid,
            vehicle_prop,
            speed,
            structural_result,
            target_x,
            target_y,
            target_z,
        ):
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
        elif int(speed or 0) > 0 and block_reason not in SOFT_VEHICLE_BLOCK_REASONS:
            apply_vehicle_crash(
                sim,
                eid,
                vehicle_prop,
                speed,
                target_x,
                target_y,
                target_z,
                block_reason=block_reason,
                structural_result=structural_result,
            )
            return False, "crash"
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
