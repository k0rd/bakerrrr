"""Delayed vehicle explosion runtime."""

from __future__ import annotations

from engine.events import Event
from engine.systems import System

from game.components import VehicleState
from game.property_runtime import (
    property_is_vehicle,
    property_metadata,
    vehicle_label,
)


VEHICLE_EXPLOSION_FUSE_TICKS = 24
VEHICLE_EXPLOSION_FIRE_RADIUS = 3
VEHICLE_EXPLOSION_FIRE_INTENSITY = 5
VEHICLE_EXPLOSION_SMOKE_INTENSITY = 2


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _text(value):
    return str(value or "").strip()


def _vehicle_coord(prop):
    try:
        return int(prop.get("x", 0)), int(prop.get("y", 0)), int(prop.get("z", 0))
    except (TypeError, ValueError):
        return 0, 0, 0


def _vehicle_chunk_loaded(sim, prop):
    if sim is None or not isinstance(prop, dict):
        return False
    x, y, _z = _vehicle_coord(prop)
    chunk = sim.chunk_coords(x, y) if hasattr(sim, "chunk_coords") else None
    if not isinstance(chunk, tuple):
        return True
    loaded = getattr(getattr(sim, "world", None), "loaded_chunks", {})
    if isinstance(loaded, dict) and loaded:
        return chunk in loaded
    detail = getattr(sim, "chunk_detail", {}).get(chunk)
    if str(detail or "").strip().lower() in {"active", "detail"}:
        return True
    realized = getattr(sim, "realized_chunks", set())
    if chunk in realized:
        return True
    return not bool(loaded)


def _clear_vehicle_occupants(sim, vehicle_id):
    inside = []
    cleared_any = False
    if sim is None or not vehicle_id:
        return inside
    vehicle_states = sim.ecs.get(VehicleState)
    now = _safe_int(getattr(sim, "tick", 0), 0)
    for eid, state in tuple(vehicle_states.items()):
        if _text(getattr(state, "active_vehicle_id", "")) != str(vehicle_id):
            continue
        was_inside = bool(getattr(state, "in_vehicle", False))
        if hasattr(state, "set_in_vehicle"):
            state.set_in_vehicle(False, tick=now)
        else:
            state.in_vehicle = False
            state.speed = 0
        if hasattr(state, "set_active_vehicle"):
            state.set_active_vehicle(None, tick=now)
        else:
            state.active_vehicle_id = None
            state.last_changed_tick = now
        cleared_any = True
        if was_inside:
            inside.append(eid)
    local_drive = getattr(sim, "local_drive_ui", None)
    if cleared_any and isinstance(local_drive, dict):
        local_drive["active"] = False
    return inside


def arm_vehicle_explosion(
    sim,
    vehicle_prop,
    *,
    cause="vehicle_destroyed",
    source_eid=None,
    fuse_ticks=VEHICLE_EXPLOSION_FUSE_TICKS,
):
    if sim is None or not property_is_vehicle(vehicle_prop):
        return False
    metadata = property_metadata(vehicle_prop)
    if bool(metadata.get("vehicle_exploded")) or metadata.get("vehicle_exploded_tick") is not None:
        return False
    if bool(metadata.get("vehicle_explosion_armed")):
        return False

    now = _safe_int(getattr(sim, "tick", 0), 0)
    fuse = max(1, _safe_int(fuse_ticks, VEHICLE_EXPLOSION_FUSE_TICKS))
    x, y, z = _vehicle_coord(vehicle_prop)
    metadata["vehicle_explosion_armed"] = True
    metadata["vehicle_explosion_armed_tick"] = now
    metadata["vehicle_explosion_due_tick"] = now + fuse
    metadata["vehicle_explosion_fuse_ticks"] = fuse
    metadata["vehicle_explosion_radius"] = VEHICLE_EXPLOSION_FIRE_RADIUS
    metadata["vehicle_explosion_fire_intensity"] = VEHICLE_EXPLOSION_FIRE_INTENSITY
    metadata["vehicle_explosion_smoke_intensity"] = VEHICLE_EXPLOSION_SMOKE_INTENSITY
    metadata["vehicle_explosion_cause"] = _text(cause) or "vehicle_destroyed"
    sim.emit(Event(
        "vehicle_explosion_armed",
        vehicle_id=vehicle_prop.get("id"),
        vehicle_name=vehicle_label(vehicle_prop),
        source_eid=source_eid,
        cause=metadata["vehicle_explosion_cause"],
        armed_tick=now,
        due_tick=now + fuse,
        fuse_ticks=fuse,
        radius=VEHICLE_EXPLOSION_FIRE_RADIUS,
        x=x,
        y=y,
        z=z,
    ))
    return True


def disarm_vehicle_explosion(vehicle_prop):
    if not property_is_vehicle(vehicle_prop):
        return False
    metadata = property_metadata(vehicle_prop)
    if not bool(metadata.get("vehicle_explosion_armed")):
        return False
    metadata["vehicle_explosion_armed"] = False
    return True


def detonate_vehicle_explosion(sim, vehicle_prop, *, force=False):
    if sim is None or not property_is_vehicle(vehicle_prop):
        return False
    metadata = property_metadata(vehicle_prop)
    if bool(metadata.get("vehicle_exploded")) or metadata.get("vehicle_exploded_tick") is not None:
        return False
    now = _safe_int(getattr(sim, "tick", 0), 0)
    due_tick = _safe_int(metadata.get("vehicle_explosion_due_tick"), now)
    if not force and now < due_tick:
        return False

    vehicle_id = _text(vehicle_prop.get("id"))
    vehicle_name = vehicle_label(vehicle_prop)
    vehicle_owner_eid = vehicle_prop.get("owner_eid")
    vehicle_owner_tag = _text(vehicle_prop.get("owner_tag"))
    x, y, z = _vehicle_coord(vehicle_prop)
    radius = max(1, _safe_int(metadata.get("vehicle_explosion_radius"), VEHICLE_EXPLOSION_FIRE_RADIUS))
    fire_intensity = max(1, _safe_int(metadata.get("vehicle_explosion_fire_intensity"), VEHICLE_EXPLOSION_FIRE_INTENSITY))
    smoke_intensity = max(0, _safe_int(metadata.get("vehicle_explosion_smoke_intensity"), VEHICLE_EXPLOSION_SMOKE_INTENSITY))
    occupant_eids = _clear_vehicle_occupants(sim, vehicle_id)

    metadata["vehicle_explosion_armed"] = False
    metadata["vehicle_exploded"] = True
    metadata["vehicle_exploded_tick"] = now
    metadata["vehicle_usable"] = False
    metadata["vehicle_broken"] = True

    removed = sim.remove_property(vehicle_id) if vehicle_id and hasattr(sim, "remove_property") else None
    sim.emit(Event(
        "vehicle_exploded",
        vehicle_id=vehicle_id,
        vehicle_name=vehicle_name,
        removed=bool(removed),
        occupant_eids=tuple(occupant_eids),
        occupant_count=len(occupant_eids),
        vehicle_owner_eid=vehicle_owner_eid,
        vehicle_owner_tag=vehicle_owner_tag,
        radius=radius,
        fire_intensity=fire_intensity,
        smoke_intensity=smoke_intensity,
        x=x,
        y=y,
        z=z,
    ))
    sim.emit(Event(
        "explosion_triggered",
        source_eid=None,
        weapon_id="vehicle_explosion",
        source_property_id=vehicle_id,
        vehicle_id=vehicle_id,
        vehicle_name=vehicle_name,
        vehicle_owner_eid=vehicle_owner_eid,
        vehicle_owner_tag=vehicle_owner_tag,
        x=x,
        y=y,
        z=z,
        radius=radius,
        hits=len(occupant_eids),
        fire_intensity=fire_intensity,
        smoke_intensity=smoke_intensity,
        force_fire=True,
    ))
    sim.emit(Event(
        "noise",
        source_eid=None,
        source_property_id=vehicle_id,
        vehicle_id=vehicle_id,
        vehicle_owner_eid=vehicle_owner_eid,
        vehicle_owner_tag=vehicle_owner_tag,
        x=x,
        y=y,
        z=z,
        radius=max(10, radius * 4),
        cause="vehicle_explosion",
    ))
    return True


class VehicleExplosionSystem(System):
    def __init__(self, sim):
        super().__init__(sim)
        self.runs_without_turn = True

    def update(self):
        now = _safe_int(getattr(self.sim, "tick", 0), 0)
        for prop in tuple(getattr(self.sim, "properties", {}).values()):
            if not property_is_vehicle(prop):
                continue
            metadata = property_metadata(prop)
            if not bool(metadata.get("vehicle_explosion_armed")):
                continue
            if _safe_int(metadata.get("durability"), 0) > 0:
                disarm_vehicle_explosion(prop)
                continue
            if now < _safe_int(metadata.get("vehicle_explosion_due_tick"), now):
                continue
            if not _vehicle_chunk_loaded(self.sim, prop):
                continue
            detonate_vehicle_explosion(self.sim, prop)


__all__ = [
    "VEHICLE_EXPLOSION_FIRE_RADIUS",
    "VEHICLE_EXPLOSION_FUSE_TICKS",
    "VehicleExplosionSystem",
    "arm_vehicle_explosion",
    "detonate_vehicle_explosion",
    "disarm_vehicle_explosion",
]
