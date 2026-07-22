"""Delayed vehicle explosion runtime."""

from __future__ import annotations

from hashlib import blake2b

from engine.events import Event
from engine.systems import System

from game.components import Collider, Render, VehicleState, Vitality
from game.property_runtime import (
    property_is_vehicle,
    property_metadata,
    vehicle_label,
)
from game.system_support.actor_runtime import _apply_downed_actor_state


VEHICLE_EXPLOSION_FUSE_TICKS = 24
VEHICLE_EXPLOSION_FUSE_MIN_TICKS = 10
VEHICLE_EXPLOSION_FUSE_MAX_TICKS = 36
VEHICLE_EXPLOSION_FIRE_RADIUS = 3
VEHICLE_EXPLOSION_FIRE_INTENSITY = 5
VEHICLE_EXPLOSION_SMOKE_INTENSITY = 2
VEHICLE_EXPLOSION_OCCUPANT_DAMAGE = 110
VEHICLE_EXPLOSION_CLASS_FUSE_OFFSETS = {
    "micro": -4,
    "skiff": -3,
    "compact": -2,
    "hatchback": -2,
    "coupe": -1,
    "sedan": 0,
    "wagon": 1,
    "launch": 2,
    "suv": 2,
    "utility": 2,
    "pickup": 3,
    "van": 3,
    "cruiser": 4,
    "truck": 4,
    "bus": 5,
    "armored": 6,
    "military": 6,
}


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _text(value):
    return str(value or "").strip()


def _clamp(value, low, high):
    return max(int(low), min(int(high), int(value)))


def _stable_roll_int(*parts):
    text = "|".join(str(part) for part in parts)
    digest = blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def _vehicle_coord(prop):
    try:
        return int(prop.get("x", 0)), int(prop.get("y", 0)), int(prop.get("z", 0))
    except (TypeError, ValueError):
        return 0, 0, 0


def vehicle_explosion_radius_for_fuel(vehicle_prop):
    """Return blast/fire reach from the fuel actually aboard at cook-off."""

    metadata = property_metadata(vehicle_prop)
    fuel = max(0, _safe_int(metadata.get("fuel"), 0))
    if fuel <= 0:
        return 1
    if fuel < 15:
        return 2
    if fuel < 35:
        return 3
    if fuel < 70:
        return 4
    if fuel < 120:
        return 5
    return 6


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


def _vehicle_fuse_durability_basis(metadata):
    for key in (
        "vehicle_explosion_durability_before",
        "vehicle_max_durability",
        "durability_max",
        "max_durability",
        "durability",
    ):
        value = metadata.get(key)
        if value is None:
            continue
        return _clamp(_safe_int(value, 5), 1, 10)
    return 5


def _vehicle_explosion_fuse_bounds(metadata):
    vehicle_class = _text(metadata.get("vehicle_class")).lower()
    class_offset = VEHICLE_EXPLOSION_CLASS_FUSE_OFFSETS.get(vehicle_class, 0)
    durability = _vehicle_fuse_durability_basis(metadata)
    durability_offset = _clamp(round((durability - 5) * 0.35), -2, 2)
    offset = int(class_offset) + int(durability_offset)
    low = max(6, VEHICLE_EXPLOSION_FUSE_MIN_TICKS + offset)
    high = max(low + 8, VEHICLE_EXPLOSION_FUSE_MAX_TICKS + offset)
    return int(low), int(high), int(class_offset), int(durability_offset)


def _choose_vehicle_explosion_fuse(sim, vehicle_prop, metadata, cause):
    low, high, class_offset, durability_offset = _vehicle_explosion_fuse_bounds(metadata)
    roll = _stable_roll_int(
        getattr(sim, "seed", 0),
        "vehicle_explosion_fuse",
        vehicle_prop.get("id"),
        getattr(sim, "tick", 0),
        _text(cause) or "vehicle_destroyed",
        _text(metadata.get("vehicle_class")).lower(),
        _vehicle_fuse_durability_basis(metadata),
    )
    span = max(1, high - low + 1)
    fuse = low + (roll % span)
    metadata["vehicle_explosion_fuse_min_ticks"] = int(low)
    metadata["vehicle_explosion_fuse_max_ticks"] = int(high)
    metadata["vehicle_explosion_fuse_class_offset"] = int(class_offset)
    metadata["vehicle_explosion_fuse_durability_offset"] = int(durability_offset)
    metadata["vehicle_explosion_fuse_roll"] = int(roll % span)
    return int(fuse)


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


def _damage_vehicle_explosion_occupants(sim, occupant_eids, *, vehicle_id, vehicle_name, x, y, z):
    if sim is None or not occupant_eids:
        return 0
    damaged = 0
    vitalities = sim.ecs.get(Vitality)
    colliders = sim.ecs.get(Collider)
    renders = sim.ecs.get(Render)
    now = _safe_int(getattr(sim, "tick", 0), 0)
    for eid in tuple(occupant_eids):
        vitality = vitalities.get(eid)
        if vitality is None:
            continue
        max_hp = max(1, _safe_int(getattr(vitality, "max_hp", 1), 1))
        damage = max(VEHICLE_EXPLOSION_OCCUPANT_DAMAGE, int(round(max_hp * 0.75)))
        was_downed = bool(getattr(vitality, "downed", False))
        vitality.hp = max(0, _safe_int(getattr(vitality, "hp", 0), 0) - damage)
        sim.emit(Event(
            "entity_damaged",
            target_eid=eid,
            source_eid=None,
            source_property_id=vehicle_id,
            vehicle_id=vehicle_id,
            vehicle_name=vehicle_name,
            weapon_id="vehicle_explosion",
            damage_kind="vehicle_explosion",
            raw_damage=int(damage),
            damage=int(damage),
            cover_absorb=0.0,
            armor_absorb=0.0,
            armor_name=None,
            hp=vitality.hp,
            max_hp=max_hp,
            x=int(x),
            y=int(y),
            z=int(z),
        ))
        damaged += 1
        if int(vitality.hp) > 0 or was_downed:
            continue
        vitality.downed_count += 1
        vitality.downed = True
        vitality.downed_tick = now
        setattr(vitality, "last_attacker_eid", None)
        setattr(vitality, "death_reason", "vehicle_explosion")
        if eid == getattr(sim, "player_eid", None):
            sim.emit(Event(
                "player_downed",
                target_eid=eid,
                source_eid=None,
                source_name=vehicle_name,
                source_property_id=vehicle_id,
                vehicle_id=vehicle_id,
                weapon_id="vehicle_explosion",
                reason="vehicle_explosion",
                damage_kind="vehicle_explosion",
                x=int(x),
                y=int(y),
                z=int(z),
            ))
            continue
        _apply_downed_actor_state(sim, eid, tick=now)
        collider = colliders.get(eid)
        if collider:
            collider.blocks = False
        render = renders.get(eid)
        if render:
            render.glyph = "x"
        sim.emit(Event(
            "npc_downed",
            target_eid=eid,
            source_eid=None,
            source_property_id=vehicle_id,
            vehicle_id=vehicle_id,
            weapon_id="vehicle_explosion",
            reason="vehicle_explosion",
            damage_kind="vehicle_explosion",
            x=int(x),
            y=int(y),
            z=int(z),
        ))
    return int(damaged)


def arm_vehicle_explosion(
    sim,
    vehicle_prop,
    *,
    cause="vehicle_destroyed",
    source_eid=None,
    fuse_ticks=None,
):
    if sim is None or not property_is_vehicle(vehicle_prop):
        return False
    metadata = property_metadata(vehicle_prop)
    if bool(metadata.get("vehicle_exploded")) or metadata.get("vehicle_exploded_tick") is not None:
        return False
    if bool(metadata.get("vehicle_explosion_armed")):
        return False

    now = _safe_int(getattr(sim, "tick", 0), 0)
    if fuse_ticks is None:
        fuse = _choose_vehicle_explosion_fuse(sim, vehicle_prop, metadata, cause)
    else:
        fuse = max(1, _safe_int(fuse_ticks, VEHICLE_EXPLOSION_FUSE_TICKS))
        metadata["vehicle_explosion_fuse_min_ticks"] = int(fuse)
        metadata["vehicle_explosion_fuse_max_ticks"] = int(fuse)
        metadata["vehicle_explosion_fuse_class_offset"] = 0
        metadata["vehicle_explosion_fuse_durability_offset"] = 0
        metadata["vehicle_explosion_fuse_roll"] = 0
    x, y, z = _vehicle_coord(vehicle_prop)
    explosion_radius = vehicle_explosion_radius_for_fuel(vehicle_prop)
    metadata["vehicle_explosion_armed"] = True
    metadata["vehicle_explosion_armed_tick"] = now
    metadata["vehicle_explosion_due_tick"] = now + fuse
    metadata["vehicle_explosion_fuse_ticks"] = fuse
    metadata["vehicle_explosion_radius"] = int(explosion_radius)
    metadata["vehicle_explosion_fuel"] = max(0, _safe_int(metadata.get("fuel"), 0))
    metadata["vehicle_explosion_fire_intensity"] = VEHICLE_EXPLOSION_FIRE_INTENSITY
    metadata["vehicle_explosion_smoke_intensity"] = VEHICLE_EXPLOSION_SMOKE_INTENSITY
    metadata["vehicle_explosion_occupant_damage"] = VEHICLE_EXPLOSION_OCCUPANT_DAMAGE
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
        radius=int(explosion_radius),
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
    occupant_damage_count = _damage_vehicle_explosion_occupants(
        sim,
        occupant_eids,
        vehicle_id=vehicle_id,
        vehicle_name=vehicle_name,
        x=x,
        y=y,
        z=z,
    )

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
        occupant_damage=VEHICLE_EXPLOSION_OCCUPANT_DAMAGE,
        occupant_damage_count=occupant_damage_count,
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
    "VEHICLE_EXPLOSION_FUSE_MAX_TICKS",
    "VEHICLE_EXPLOSION_FUSE_MIN_TICKS",
    "VEHICLE_EXPLOSION_FUSE_TICKS",
    "VEHICLE_EXPLOSION_OCCUPANT_DAMAGE",
    "VehicleExplosionSystem",
    "arm_vehicle_explosion",
    "detonate_vehicle_explosion",
    "disarm_vehicle_explosion",
    "vehicle_explosion_radius_for_fuel",
]
