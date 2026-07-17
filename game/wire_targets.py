"""Source-neutral target references for Wire connections and scenes."""

from __future__ import annotations

from collections.abc import Mapping

from game.components import CreatureIdentity, DroneState, Position
from game.drone_runtime import drone_link_disruption_status, drone_state_has_capability
from game.property_runtime import property_linked_property_id


WIRE_TARGET_REF_SCHEMA_VERSION = 2
WIRE_TARGET_KINDS = ("property", "drone", "vehicle")


def _text(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _key(value, default=""):
    return _text(value, default).lower()


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def normalize_wire_target_ref(target_ref=None):
    if not isinstance(target_ref, Mapping):
        return {}
    kind = _key(target_ref.get("kind"))
    if kind not in WIRE_TARGET_KINDS:
        return {}
    normalized = {
        "schema_version": WIRE_TARGET_REF_SCHEMA_VERSION,
        "kind": kind,
        "target_class": _key(target_ref.get("target_class")),
    }
    if kind in {"property", "vehicle"}:
        property_id = _text(target_ref.get("property_id") or target_ref.get("target_property_id"))
        if not property_id:
            return {}
        normalized["property_id"] = property_id
    elif kind == "drone":
        entity_id = target_ref.get("entity_id", target_ref.get("target_entity_id"))
        if entity_id is not None:
            try:
                normalized["entity_id"] = int(entity_id)
            except (TypeError, ValueError):
                pass
        stable_id = _text(target_ref.get("stable_id") or target_ref.get("source_item_instance_id"))
        if stable_id:
            normalized["stable_id"] = stable_id
        if "entity_id" not in normalized and not stable_id:
            return {}
    return normalized


def property_wire_target_ref(prop, *, target_class=""):
    if not isinstance(prop, Mapping):
        return {}
    property_id = _text(prop.get("id"))
    if not property_id:
        return {}
    return normalize_wire_target_ref({
        "kind": "property",
        "property_id": property_id,
        "target_class": target_class,
    })


def drone_wire_target_ref(sim, drone_eid, *, target_class="drone_radio"):
    state = sim.ecs.get(DroneState).get(drone_eid) if sim is not None else None
    if state is None:
        return {}
    return normalize_wire_target_ref({
        "kind": "drone",
        "entity_id": drone_eid,
        "stable_id": getattr(state, "source_item_instance_id", None),
        "target_class": target_class,
    })


def vehicle_wire_target_ref(prop, *, target_class="vehicle_controller"):
    if not isinstance(prop, Mapping) or _key(prop.get("kind")) != "vehicle":
        return {}
    property_id = _text(prop.get("id"))
    if not property_id:
        return {}
    return normalize_wire_target_ref({
        "kind": "vehicle",
        "property_id": property_id,
        "target_class": target_class,
    })


def wire_target_ref_from_connection(connection=None):
    if not isinstance(connection, Mapping):
        return {}
    current = normalize_wire_target_ref(connection.get("target_ref"))
    if current:
        return current
    target_class = _key(connection.get("target_class"))
    property_id = _text(connection.get("target_property_id"))
    if property_id:
        return normalize_wire_target_ref({
            "kind": "vehicle" if target_class == "vehicle_controller" else "property",
            "property_id": property_id,
            "target_class": target_class,
        })
    entity_id = connection.get("target_entity_id")
    stable_id = _text(connection.get("target_stable_id"))
    if entity_id is not None or stable_id:
        return normalize_wire_target_ref({
            "kind": "drone",
            "entity_id": entity_id,
            "stable_id": stable_id,
            "target_class": target_class or "drone_radio",
        })
    return {}


def wire_target_identity(target_ref=None):
    ref = normalize_wire_target_ref(target_ref)
    kind = ref.get("kind")
    if kind == "property":
        return f"property:{ref.get('property_id', '')}"
    if kind == "vehicle":
        return f"vehicle:{ref.get('property_id', '')}"
    if kind == "drone":
        stable = _text(ref.get("stable_id"))
        if stable:
            return f"drone:{stable}"
        if ref.get("entity_id") is not None:
            return f"drone-eid:{int(ref['entity_id'])}"
    return ""


def _resolve_drone_eid(sim, ref):
    states = sim.ecs.get(DroneState)
    entity_id = ref.get("entity_id")
    if entity_id is not None and states.get(entity_id) is not None:
        return entity_id
    stable_id = _text(ref.get("stable_id"))
    if not stable_id:
        return None
    for eid, state in states.items():
        if _text(getattr(state, "source_item_instance_id", None)) == stable_id:
            return eid
    return None


def _drone_name(sim, drone_eid, state):
    identity = sim.ecs.get(CreatureIdentity).get(drone_eid)
    for value in (
        getattr(identity, "common_name", None),
        getattr(identity, "name", None),
    ):
        if _text(value):
            return _text(value)
    chassis_class = _text(getattr(state, "chassis_class", None), "?").upper()
    return f"Class {chassis_class} drone"


def _drone_security_tier(state):
    chassis = _text(getattr(state, "chassis_class", None)).upper()
    tier = {"A": 1, "B": 1, "C": 2, "D": 3, "E": 4}.get(chassis, 2)
    if drone_state_has_capability(state, "armor"):
        tier += 1
    return max(1, min(5, int(tier)))


def resolve_wire_target(sim, target_ref=None):
    ref = normalize_wire_target_ref(target_ref)
    if not ref or sim is None:
        return None
    kind = ref.get("kind")
    if kind == "property":
        prop = getattr(sim, "properties", {}).get(str(ref.get("property_id", "") or ""))
        if not isinstance(prop, Mapping):
            return None
        metadata = dict(prop.get("metadata") or {}) if isinstance(prop.get("metadata"), Mapping) else {}
        linked_id = _text(property_linked_property_id(prop))
        return {
            "ref": dict(ref),
            "identity": wire_target_identity(ref),
            "kind": "property",
            "target_class": _key(ref.get("target_class")),
            "name": _text(prop.get("name"), _key(ref.get("target_class"), "wire target").replace("_", " ")),
            "x": _int(prop.get("x"), 0),
            "y": _int(prop.get("y"), 0),
            "z": _int(prop.get("z"), 0),
            "metadata": metadata,
            "property": prop,
            "linked_property_id": linked_id,
            "source": prop,
        }
    if kind == "vehicle":
        prop = getattr(sim, "properties", {}).get(str(ref.get("property_id", "") or ""))
        if not isinstance(prop, Mapping) or _key(prop.get("kind")) != "vehicle":
            return None
        metadata = dict(prop.get("metadata") or {}) if isinstance(prop.get("metadata"), Mapping) else {}
        resolved_ref = vehicle_wire_target_ref(prop, target_class="vehicle_controller")
        lock_tier = _int(metadata.get("property_lock_tier"), 1)
        quality = _key(metadata.get("vehicle_quality"), "used")
        security_tier = max(1, min(5, lock_tier + (1 if quality == "new" else 0)))
        metadata["security_tier"] = security_tier
        metadata["owner_tag"] = _text(prop.get("owner_tag") or metadata.get("vehicle_owner_tag"))
        return {
            "ref": resolved_ref,
            "identity": wire_target_identity(resolved_ref),
            "kind": "vehicle",
            "target_class": "vehicle_controller",
            "name": _text(prop.get("name"), "vehicle controller"),
            "x": _int(prop.get("x"), 0),
            "y": _int(prop.get("y"), 0),
            "z": _int(prop.get("z"), 0),
            "metadata": metadata,
            "vehicle_id": _text(prop.get("id")),
            "vehicle": prop,
            "property": prop,
            "linked_property_id": "",
            "source": prop,
        }
    if kind == "drone":
        drone_eid = _resolve_drone_eid(sim, ref)
        if drone_eid is None:
            return None
        state = sim.ecs.get(DroneState).get(drone_eid)
        pos = sim.ecs.get(Position).get(drone_eid)
        if state is None or pos is None or _key(getattr(state, "mode", None)) != "deployed":
            return None
        resolved_ref = dict(ref)
        resolved_ref["entity_id"] = int(drone_eid)
        stable_id = _text(getattr(state, "source_item_instance_id", None))
        if stable_id:
            resolved_ref["stable_id"] = stable_id
        owner_tag = _text(getattr(state, "legal_owner_tag", None) or getattr(state, "owner_tag", None))
        faction_id = _text(getattr(state, "faction_id", None))
        modules = tuple(
            _key(module.get("item_id"))
            for module in tuple(getattr(state, "modules", ()) or ())
            if isinstance(module, Mapping) and _key(module.get("item_id"))
        )
        metadata = {
            "archetype": "deployed_drone",
            "security_tier": _drone_security_tier(state),
            "organization_key": faction_id or owner_tag,
            "organization_name": faction_id or owner_tag,
            "chassis_class": _text(getattr(state, "chassis_class", None)).upper(),
            "module_ids": modules,
            "owner_tag": owner_tag,
            "faction_id": faction_id,
            "battery_charge": _int(getattr(state, "battery_charge", 0), 0),
            "battery_charge_max": _int(getattr(state, "battery_charge_max", 0), 0),
            "procedure_key": _key(getattr(state, "procedure_key", None)),
            "procedure_program_id": _key(getattr(state, "procedure_program_id", None)),
        }
        return {
            "ref": normalize_wire_target_ref(resolved_ref),
            "identity": wire_target_identity(resolved_ref),
            "kind": "drone",
            "target_class": "drone_radio",
            "name": _drone_name(sim, drone_eid, state),
            "x": int(pos.x),
            "y": int(pos.y),
            "z": int(pos.z),
            "metadata": metadata,
            "drone_eid": int(drone_eid),
            "drone_state": state,
            "linked_property_id": "",
            "source": state,
        }
    return None


def wire_target_has_live_radio(target, *, tick=0):
    if not isinstance(target, Mapping) or target.get("kind") != "drone":
        return True
    state = target.get("drone_state")
    if state is None:
        return False
    if drone_link_disruption_status(state, tick=tick).get("active"):
        return False
    has_radio = bool(
        drone_state_has_capability(state, "radio")
        or drone_state_has_capability(state, "comms")
    )
    return bool(has_radio and _int(getattr(state, "battery_charge", 0), 0) > 0)


__all__ = [
    "WIRE_TARGET_KINDS",
    "WIRE_TARGET_REF_SCHEMA_VERSION",
    "drone_wire_target_ref",
    "normalize_wire_target_ref",
    "property_wire_target_ref",
    "resolve_wire_target",
    "vehicle_wire_target_ref",
    "wire_target_has_live_radio",
    "wire_target_identity",
    "wire_target_ref_from_connection",
]
