"""Shared targeting and damage rules for anchored physical objects.

Actors and deployed drones remain ECS entities.  Vehicles and durable fixtures
are properties, so weapon code needs one narrow seam that can find and damage
those records without making them movement blockers or pretending that every
building/property is a combat target.
"""

from __future__ import annotations

import math

from engine.events import Event
from game.property_access import property_access_level
from game.property_runtime import (
    property_infrastructure_role,
    property_is_vehicle,
    property_metadata,
    vehicle_label,
)
from game.vehicle_motion import apply_vehicle_durability_loss
from game.weapons import weapon_by_id
from game.system_support.awareness_runtime import observation_payload_for_position
from game.system_support.intrusion_runtime import _trespass_label_from_score


ATTACKABLE_INFRASTRUCTURE_ROLES = frozenset({
    "access_panel",
    "security_post",
    "service_terminal",
})

FIXTURE_INTEGRITY_DEFAULTS = {
    "access_panel": (18, 2),
    "service_terminal": (20, 2),
    "security_post": (30, 4),
    "mechanical_device": (8, 0),
    "fixture": (14, 1),
}


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _clean(value):
    return str(value or "").strip()


def _property_kind(prop):
    return _clean((prop or {}).get("kind")).lower()


def _fixture_damage_key(prop):
    metadata = property_metadata(prop)
    if bool(metadata.get("mechanical_device")):
        return "mechanical_device"
    role = property_infrastructure_role(prop)
    if role in ATTACKABLE_INFRASTRUCTURE_ROLES:
        return role
    return "fixture"


def property_is_weapon_targetable(prop):
    if not isinstance(prop, dict):
        return False
    if property_is_vehicle(prop):
        return True
    metadata = property_metadata(prop)
    if metadata.get("attackable") is False or metadata.get("damageable") is False:
        return False
    if bool(metadata.get("attackable")) or bool(metadata.get("damageable")):
        return True
    if bool(metadata.get("mechanical_device")):
        return True
    return property_infrastructure_role(prop) in ATTACKABLE_INFRASTRUCTURE_ROLES


def _property_target_priority(prop):
    if property_is_vehicle(prop):
        return 0
    metadata = property_metadata(prop)
    if bool(metadata.get("mechanical_device")):
        return 1
    role = property_infrastructure_role(prop)
    if role == "access_panel":
        return 2
    if role == "service_terminal":
        return 3
    if role == "security_post":
        return 4
    return 5


def weapon_targetable_property_at(sim, x, y, z=0):
    """Return an attackable property anchored on one exact map cell.

    Deliberately do not use ``property_covering`` here: aiming at a room floor
    must not turn the whole enclosing building into a target.
    """

    if sim is None:
        return None
    try:
        key = (int(x), int(y), int(z))
    except (TypeError, ValueError):
        return None
    candidates = []
    anchor_index = getattr(sim, "property_anchor_index", {})
    properties = getattr(sim, "properties", {})
    for property_id in tuple(anchor_index.get(key, ()) or ()):
        prop = properties.get(property_id)
        if property_is_weapon_targetable(prop):
            candidates.append(prop)
    if not candidates:
        # Small regression/test simulations may not expose the optimized index.
        for prop in tuple(properties.values()):
            if not property_is_weapon_targetable(prop):
                continue
            if (
                _int(prop.get("x"), 0),
                _int(prop.get("y"), 0),
                _int(prop.get("z"), 0),
            ) == key:
                candidates.append(prop)
    if not candidates:
        return None
    candidates.sort(key=lambda prop: (_property_target_priority(prop), _clean(prop.get("id"))))
    return candidates[0]


def physical_property_profile(prop):
    if not property_is_weapon_targetable(prop):
        return {}
    metadata = property_metadata(prop)
    if property_is_vehicle(prop):
        maximum = max(1, _int(metadata.get("vehicle_max_durability", 10), 10))
        current = max(0, min(maximum, _int(metadata.get("durability", 5), 5)))
        return {
            "kind": "vehicle",
            "label": vehicle_label(prop),
            "integrity": current,
            "max_integrity": maximum,
            "armor": max(0, _int(metadata.get("physical_armor", 0), 0)),
            "broken": current <= 0 or bool(metadata.get("vehicle_broken")),
        }

    key = _fixture_damage_key(prop)
    default_maximum, default_armor = FIXTURE_INTEGRITY_DEFAULTS.get(key, FIXTURE_INTEGRITY_DEFAULTS["fixture"])
    source_metadata = metadata.get("source_item_metadata") if isinstance(metadata.get("source_item_metadata"), dict) else {}
    source_maximum = _int(source_metadata.get("item_max_durability"), 0)
    maximum = max(1, _int(metadata.get("fixture_integrity_max"), source_maximum or default_maximum))
    source_current = _int(source_metadata.get("item_durability"), maximum)
    current = max(0, min(maximum, _int(metadata.get("fixture_integrity"), source_current)))
    return {
        "kind": key,
        "label": _clean(prop.get("name")) or key.replace("_", " "),
        "integrity": current,
        "max_integrity": maximum,
        "armor": max(0, _int(metadata.get("fixture_armor"), default_armor)),
        "broken": current <= 0 or bool(metadata.get("fixture_broken")),
    }


def _vehicle_durability_loss(raw_damage, damage_kind, weapon_id):
    raw_damage = max(0, _int(raw_damage, 0))
    weapon = weapon_by_id(weapon_id)
    tags = {_clean(tag).lower() for tag in tuple(weapon.get("tags", ()) or ()) if _clean(tag)}
    kind = _clean(damage_kind).lower()
    if "explosive" in tags or kind in {"explosive", "explosion", "vehicle_explosion"}:
        return max(3, int(math.ceil(raw_damage / 8.0)))
    if "demolition" in tags:
        return max(2, int(math.ceil(raw_damage / 8.0)))
    if "melee" in tags or kind == "melee":
        if not (tags & {"axe", "blunt", "club", "hammer", "pry", "utility"}):
            return 0
        return max(1, int(math.ceil(raw_damage / 10.0)))
    if raw_damage <= 0:
        return 0
    return max(1, int(math.ceil(raw_damage / 14.0)))


def _remove_destroyed_mechanical_device(sim, prop):
    property_id = _clean(prop.get("id"))
    index = getattr(sim, "mechanical_device_property_ids", None)
    if hasattr(index, "discard"):
        index.discard(property_id)
    system = getattr(sim, "mechanical_device_system", None)
    remove_device = getattr(system, "_remove_device", None)
    if callable(remove_device):
        remove_device(prop)
        return
    if hasattr(sim, "remove_property"):
        sim.remove_property(property_id)


def apply_physical_property_damage(
    sim,
    prop,
    raw_damage,
    *,
    damage_kind="impact",
    weapon_id="",
    source_eid=None,
    x=None,
    y=None,
    z=None,
):
    """Damage one anchored object and return a stable result payload."""

    profile = physical_property_profile(prop)
    if not profile:
        return {"damaged": False, "reason": "not_attackable"}
    property_id = _clean(prop.get("id"))
    px = _int(prop.get("x") if x is None else x, 0)
    py = _int(prop.get("y") if y is None else y, 0)
    pz = _int(prop.get("z") if z is None else z, 0)
    raw_damage = max(0, _int(raw_damage, 0))
    before = int(profile["integrity"])
    maximum = int(profile["max_integrity"])
    metadata = property_metadata(prop)

    if profile["kind"] == "vehicle":
        requested_loss = _vehicle_durability_loss(raw_damage, damage_kind, weapon_id)
        durability_before, after, applied = apply_vehicle_durability_loss(
            sim,
            prop,
            amount=requested_loss,
            cause=_clean(damage_kind) or "weapon_impact",
        )
        before = int(durability_before)
        broken = after <= 0
    else:
        armor = max(0, int(profile.get("armor", 0)))
        applied = max(0, raw_damage - armor)
        after = max(0, before - applied)
        metadata["fixture_integrity_max"] = maximum
        metadata["fixture_integrity"] = int(after)
        metadata["fixture_armor"] = armor
        metadata["fixture_broken"] = bool(after <= 0)
        metadata["fixture_usable"] = bool(after > 0)
        broken = after <= 0
        source_metadata = metadata.get("source_item_metadata") if isinstance(metadata.get("source_item_metadata"), dict) else None
        if source_metadata is not None:
            source_metadata["item_max_durability"] = maximum
            source_metadata["item_durability"] = int(after)

    metadata["last_fixture_damage_tick"] = _int(getattr(sim, "tick", 0), 0)
    metadata["last_fixture_damage_kind"] = _clean(damage_kind) or "impact"
    metadata["last_fixture_damage_weapon_id"] = _clean(weapon_id)
    metadata["last_fixture_damage_source_eid"] = source_eid
    if broken:
        metadata["fixture_broken_tick"] = _int(getattr(sim, "tick", 0), 0)

    event_payload = {
        "source_eid": source_eid,
        "property_id": property_id,
        "property_name": profile["label"],
        "physical_kind": profile["kind"],
        "weapon_id": _clean(weapon_id),
        "damage_kind": _clean(damage_kind) or "impact",
        "raw_damage": raw_damage,
        "damage": int(applied),
        "integrity_before": int(before),
        "integrity": int(after),
        "max_integrity": maximum,
        "broken": bool(broken),
        "x": px,
        "y": py,
        "z": pz,
    }
    sim.emit(Event("physical_object_damaged", **event_payload))
    if int(applied) > 0 and source_eid is not None and prop.get("owner_eid") != source_eid:
        severity = min(100, 34 + (14 if broken else 0) + (8 if profile["kind"] == "vehicle" else 0))
        observation = observation_payload_for_position(
            sim,
            px,
            py,
            pz,
            exclude_eid=source_eid,
            offender_eid=source_eid,
            observation_channels=("actor_witness",),
        )
        sim.emit(Event(
            "property_tamper",
            offender_eid=source_eid,
            property_id=property_id,
            owner_eid=prop.get("owner_eid"),
            x=px,
            y=py,
            z=pz,
            access_level=property_access_level(prop),
            severity_score=severity,
            severity_label=_trespass_label_from_score(severity),
            standing_reason="none",
            ingress_kind="physical_damage",
            ingress_method=_clean(damage_kind) or "impact",
            breach_severity=min(1.0, float(applied) / float(maximum)),
            defender_witnesses_only=True,
            require_witnessed_identity=True,
            **observation,
        ))
    if broken and before > 0:
        sim.emit(Event("physical_object_broken", **event_payload))
        if profile["kind"] == "mechanical_device":
            _remove_destroyed_mechanical_device(sim, prop)

    return {
        "damaged": True,
        "property_id": property_id,
        "property_name": profile["label"],
        "physical_kind": profile["kind"],
        "damage": int(applied),
        "integrity_before": int(before),
        "integrity": int(after),
        "max_integrity": maximum,
        "broken": bool(broken),
    }
