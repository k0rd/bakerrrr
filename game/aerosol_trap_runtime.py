"""Runtime support for homemade aerosol floor traps."""

from __future__ import annotations

import copy
from collections.abc import Mapping

from engine.events import Event
from engine.systems import System

from game.components import CreatureIdentity, NPCMemory
from game.items import ITEM_CATALOG, item_display_name
from game.system_support.awareness_runtime import observation_payload_for_position


AEROSOL_TRAP_MEMORY_KIND = "placed_aerosol_trap"
AEROSOL_TRAP_FIXTURE_TYPE = "aerosol_floor_trap"


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _coord(x, y, z=0):
    return (_int(x), _int(y), _int(z))


def _item_def(item_catalog, item_id):
    catalog = item_catalog or ITEM_CATALOG
    return catalog.get(str(item_id or "").strip().lower(), {})


def item_is_aerosol_floor_trap(item_def):
    return isinstance((item_def or {}).get("trap_profile"), Mapping) and bool((item_def or {}).get("trap_profile"))


def _entity_name(sim, eid, default="someone"):
    identity = sim.ecs.get(CreatureIdentity).get(eid) if sim is not None and eid is not None else None
    if identity is not None:
        return identity.display_name()
    return default


def _trap_metadata(prop):
    metadata = (prop or {}).get("metadata") if isinstance((prop or {}).get("metadata"), Mapping) else {}
    if not bool(metadata.get("aerosol_floor_trap")):
        return {}
    return metadata


def property_is_armed_aerosol_trap(prop):
    metadata = _trap_metadata(prop)
    return bool(metadata.get("armed", False))


def _properties_at(sim, x, y, z):
    if sim is None:
        return ()
    if hasattr(sim, "properties_in_radius"):
        return tuple(sim.properties_in_radius(int(x), int(y), int(z), r=0) or ())
    prop = sim.property_at(int(x), int(y), int(z)) if hasattr(sim, "property_at") else None
    return (prop,) if prop else ()


def armed_aerosol_traps_at(sim, x, y, z):
    return tuple(
        prop
        for prop in _properties_at(sim, x, y, z)
        if property_is_armed_aerosol_trap(prop)
    )


def actor_knows_armed_aerosol_trap_at(sim, eid, x, y, z):
    if sim is None or eid is None:
        return False
    memory = sim.ecs.get(NPCMemory).get(eid)
    if memory is None:
        return False
    target = _coord(x, y, z)
    for entry in tuple(getattr(memory, "entries", ()) or ()):
        if str(entry.get("kind", "") or "").strip().lower() != AEROSOL_TRAP_MEMORY_KIND:
            continue
        if float(entry.get("strength", 0.0) or 0.0) <= 0.05:
            continue
        data = entry.get("data") if isinstance(entry.get("data"), Mapping) else {}
        property_id = str(data.get("property_id", "") or "").strip()
        prop = getattr(sim, "properties", {}).get(property_id) if property_id else None
        if not property_is_armed_aerosol_trap(prop):
            continue
        if _coord(prop.get("x"), prop.get("y"), prop.get("z", 0)) == target:
            return True
    return False


def _remember_trap_placement(sim, observer_eid, *, trap_property_id, placer_eid, x, y, z, item_id, item_name):
    memory = sim.ecs.get(NPCMemory).get(observer_eid)
    if memory is None:
        return False
    memory.remember(
        getattr(sim, "tick", 0),
        AEROSOL_TRAP_MEMORY_KIND,
        strength=0.84,
        property_id=trap_property_id,
        placer_eid=placer_eid,
        x=int(x),
        y=int(y),
        z=int(z),
        item_id=item_id,
        item_name=item_name,
    )
    return True


def _trap_observation(sim, placer_eid, x, y, z):
    return observation_payload_for_position(
        sim,
        int(x),
        int(y),
        int(z),
        exclude_eid=placer_eid,
        offender_eid=placer_eid,
        observation_channels=("actor_witness",),
    )


def place_aerosol_floor_trap(sim, eid, inventory, item_entry, x, y, z=0, *, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    item_id = str((item_entry or {}).get("item_id", "") or "").strip().lower()
    item_def = _item_def(item_catalog, item_id)
    trap_profile = item_def.get("trap_profile") if isinstance(item_def.get("trap_profile"), Mapping) else {}
    if not trap_profile:
        return {"ok": False, "reason": "not_trap"}
    payload_item_id = str(trap_profile.get("payload_item_id", "") or "").strip().lower()
    payload_def = _item_def(item_catalog, payload_item_id)
    throw_profile = payload_def.get("throw_profile") if isinstance(payload_def.get("throw_profile"), Mapping) else {}
    if not throw_profile:
        return {"ok": False, "reason": "missing_payload"}
    tile = sim.tilemap.tile_at(int(x), int(y), int(z)) if hasattr(sim, "tilemap") else None
    if tile is None:
        return {"ok": False, "reason": "no_tile"}
    if not bool(getattr(tile, "walkable", False)):
        return {"ok": False, "reason": "blocked_tile"}
    if armed_aerosol_traps_at(sim, x, y, z):
        return {"ok": False, "reason": "trap_present"}
    if hasattr(sim, "ground_items_at") and sim.ground_items_at(int(x), int(y), z=int(z)):
        return {"ok": False, "reason": "ground_item_present"}

    removed = inventory.remove_item(instance_id=item_entry.get("instance_id"), quantity=1) if inventory else None
    if not removed:
        return {"ok": False, "reason": "remove_failed"}
    owner_tag = "player" if eid == getattr(sim, "player_eid", None) else "npc"
    item_name = item_display_name(item_id, metadata=removed.get("metadata"), item_catalog=item_catalog)
    payload_name = item_display_name(payload_item_id, item_catalog=item_catalog)
    metadata = {
        "archetype": AEROSOL_TRAP_FIXTURE_TYPE,
        "fixture_type": AEROSOL_TRAP_FIXTURE_TYPE,
        "aerosol_floor_trap": True,
        "armed": True,
        "armed_by_eid": eid,
        "armed_by_name": _entity_name(sim, eid, default="the placer"),
        "armed_tick": _int(getattr(sim, "tick", 0)),
        "ignored_until_vacated_eids": [eid],
        "source_item_id": item_id,
        "source_item_name": item_name,
        "source_item_metadata": copy.deepcopy(removed.get("metadata") if isinstance(removed.get("metadata"), Mapping) else {}),
        "payload_item_id": payload_item_id,
        "payload_item_name": payload_name,
        "payload_throw_profile": copy.deepcopy(dict(throw_profile)),
        "display_glyph": str(trap_profile.get("armed_glyph", "^") or "^")[:1] or "^",
        "display_color": str(trap_profile.get("armed_color", "item_illegal") or "item_illegal").strip() or "item_illegal",
        "pickup_allowed": False,
        "homemade": bool(trap_profile.get("homemade", True)),
        "legal_status": str(item_def.get("legal_status", "restricted") or "restricted").strip().lower(),
    }
    property_id = sim.register_property(
        name=item_name,
        kind="fixture",
        x=int(x),
        y=int(y),
        z=int(z),
        owner_eid=eid,
        owner_tag=owner_tag,
        metadata=metadata,
    )
    observation = _trap_observation(sim, eid, x, y, z)
    observer_ids = set()
    for key in ("observer_eids", "accountable_observer_eids"):
        for observer_eid in tuple(observation.get(key, ()) or ()):
            if observer_eid != eid:
                observer_ids.add(observer_eid)
    remembered = []
    for observer_eid in sorted(observer_ids):
        if _remember_trap_placement(
            sim,
            observer_eid,
            trap_property_id=property_id,
            placer_eid=eid,
            x=x,
            y=y,
            z=z,
            item_id=item_id,
            item_name=item_name,
        ):
            remembered.append(observer_eid)
    payload = {
        "eid": eid,
        "property_id": property_id,
        "item_id": item_id,
        "item_name": item_name,
        "payload_item_id": payload_item_id,
        "payload_item_name": payload_name,
        "x": int(x),
        "y": int(y),
        "z": int(z),
        "remembered_eids": tuple(remembered),
    }
    payload.update(observation)
    sim.emit(Event("aerosol_trap_placed", **payload))
    return {"ok": True, "property_id": property_id, "item": removed, "metadata": metadata}


class AerosolTrapSystem(System):
    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("entity_moved", self.on_entity_moved)

    def on_entity_moved(self, event):
        eid = event.data.get("eid")
        if eid is None:
            return
        old_x = event.data.get("old_x")
        old_y = event.data.get("old_y")
        old_z = event.data.get("old_z", event.data.get("z", 0))
        if old_x is not None and old_y is not None:
            self._release_ignored_actor(eid, old_x, old_y, old_z)
        x = event.data.get("x")
        y = event.data.get("y")
        z = event.data.get("z", 0)
        if x is None or y is None:
            return
        for prop in armed_aerosol_traps_at(self.sim, x, y, z):
            if self._actor_is_temporarily_ignored(prop, eid):
                continue
            self._trigger(prop, eid)
            break

    def _release_ignored_actor(self, eid, x, y, z):
        for prop in armed_aerosol_traps_at(self.sim, x, y, z):
            metadata = _trap_metadata(prop)
            ignored = list(metadata.get("ignored_until_vacated_eids", ()) or ())
            if eid in ignored:
                metadata["ignored_until_vacated_eids"] = [value for value in ignored if value != eid]

    def _actor_is_temporarily_ignored(self, prop, eid):
        metadata = _trap_metadata(prop)
        return eid in set(metadata.get("ignored_until_vacated_eids", ()) or ())

    def _trigger(self, prop, target_eid):
        metadata = _trap_metadata(prop)
        if not metadata:
            return False
        property_id = str(prop.get("id", "") or "").strip()
        x, y, z = _coord(prop.get("x"), prop.get("y"), prop.get("z", 0))
        source_eid = metadata.get("armed_by_eid")
        throw_profile = metadata.get("payload_throw_profile") if isinstance(metadata.get("payload_throw_profile"), Mapping) else {}
        aerosol_status = str(throw_profile.get("aerosol_status", "") or "").strip().lower()
        smoke_intensity = max(1, _int(throw_profile.get("smoke_intensity"), 1))
        radius = max(0, _int(throw_profile.get("cloud_radius"), 0))
        cloud_duration = max(0, _int(throw_profile.get("cloud_duration"), 0))
        smoke_payload = {
            "source_eid": source_eid,
            "weapon_id": metadata.get("source_item_id"),
            "x": x,
            "y": y,
            "z": z,
            "radius": radius,
            "smoke_intensity": smoke_intensity,
            "cloud_duration": cloud_duration,
            "thrown_item_id": metadata.get("source_item_id"),
            "thrown_item_name": metadata.get("source_item_name"),
        }
        if aerosol_status:
            smoke_payload.update({
                "aerosol_status": aerosol_status,
                "aerosol_duration": max(1, _int(throw_profile.get("aerosol_duration"), 1)),
                "aerosol_modifiers": dict(throw_profile.get("aerosol_modifiers", {}) or {}),
                "aerosol_exposure_cooldown": max(1, _int(throw_profile.get("aerosol_exposure_cooldown"), 6)),
                "aerosol_label": str(throw_profile.get("aerosol_label", "") or "").strip(),
            })
        self.sim.emit(Event("smoke_cloud_released", **smoke_payload))
        if aerosol_status:
            self.sim.emit(Event("aerosol_cloud_released", **smoke_payload))
        observation = observation_payload_for_position(
            self.sim,
            x,
            y,
            z,
            exclude_eid=source_eid,
            offender_eid=source_eid,
            observation_channels=("actor_witness",),
        )
        trigger_payload = {
            "property_id": property_id,
            "source_eid": source_eid,
            "target_eid": target_eid,
            "target_name": _entity_name(self.sim, target_eid, default="someone"),
            "item_id": metadata.get("source_item_id"),
            "item_name": metadata.get("source_item_name"),
            "payload_item_id": metadata.get("payload_item_id"),
            "payload_item_name": metadata.get("payload_item_name"),
            "x": x,
            "y": y,
            "z": z,
            "aerosol_status": aerosol_status,
        }
        trigger_payload.update(observation)
        self.sim.emit(Event("aerosol_trap_triggered", **trigger_payload))
        if source_eid is not None:
            self.sim.emit(Event(
                "action_offense",
                offender_eid=source_eid,
                action="aerosol_trap",
                context="aerosol_trap",
                offense_score=48,
                offense_tier="serious",
                victim_eid=target_eid,
                target_eid=target_eid,
                target_name=trigger_payload["target_name"],
                item_id=metadata.get("source_item_id"),
                item_name=metadata.get("source_item_name"),
                property_id=property_id,
                property_name=prop.get("name"),
                x=x,
                y=y,
                z=z,
                **observation,
            ))
        metadata["armed"] = False
        metadata["triggered_tick"] = _int(getattr(self.sim, "tick", 0))
        self.sim.remove_property(property_id)
        return True
