"""Bounded Wire diagnostics and authenticated service for live vehicles."""

from __future__ import annotations

from collections.abc import Mapping

from engine.events import Event
from game.components import Inventory
from game.property_doors import _set_property_locked_override
from game.property_keys import inventory_matching_property_credential, property_lock_state
from game.property_runtime import vehicle_profile_from_property
from game.wire_targets import resolve_wire_target


VEHICLE_WIRE_IGNITION_AUTH_TICKS = 30


def _text(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _vehicle_target(sim, target_ref):
    target = resolve_wire_target(sim, target_ref)
    return target if isinstance(target, Mapping) and target.get("kind") == "vehicle" else None


def _actor_matches(value, actor_eid):
    try:
        return int(value) == int(actor_eid)
    except (TypeError, ValueError):
        return value == actor_eid


def vehicle_wire_actor_authenticated(sim, actor_eid, vehicle):
    if not isinstance(vehicle, Mapping):
        return False
    if _actor_matches(vehicle.get("owner_eid"), actor_eid):
        return True
    if (
        str(vehicle.get("owner_tag", "") or "").strip().lower() == "player"
        and _actor_matches(getattr(sim, "player_eid", None), actor_eid)
    ):
        return True
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    lock = property_lock_state(vehicle)
    return bool(inventory_matching_property_credential(
        inventory,
        property_id=vehicle.get("id"),
        key_id=lock.get("key_id"),
    ))


def vehicle_wire_diagnostics(sim, actor_eid, target_ref):
    target = _vehicle_target(sim, target_ref)
    if not isinstance(target, Mapping):
        return {"ok": False, "reason": "target_unavailable", "lines": ()}
    vehicle = target.get("vehicle")
    metadata = vehicle.get("metadata") if isinstance((vehicle or {}).get("metadata"), dict) else {}
    profile = vehicle_profile_from_property(vehicle)
    lock = property_lock_state(vehicle)
    authenticated = vehicle_wire_actor_authenticated(sim, actor_eid, vehicle)
    tracker_installed = bool(metadata.get("vehicle_tracker_installed", False))
    tracker_enabled = bool(metadata.get("vehicle_tracker_enabled", False)) if tracker_installed else False
    usable = bool(profile.get("usable"))
    fuel = int(profile.get("fuel", 0) or 0)
    fuel_capacity = int(profile.get("fuel_capacity", 0) or 0)
    now = int(getattr(sim, "tick", 0) or 0)
    ignition_authorized = bool(
        _actor_matches(metadata.get("vehicle_wire_ignition_actor_eid"), actor_eid)
        and int(metadata.get("vehicle_wire_ignition_until_tick", 0) or 0) > now
    )
    if not usable:
        ignition = "disabled by vehicle condition"
    elif fuel <= 0:
        ignition = "ready but fuel-starved"
    elif ignition_authorized:
        ignition = "authenticated service authorization primed"
    elif metadata.get("vehicle_hotwired"):
        ignition = "nonstandard override present"
    else:
        ignition = "credential handshake required"
    tracker = "not installed"
    if tracker_installed:
        tracker = "active" if tracker_enabled else "standby"
    lines = (
        f"Controller: {target.get('name', 'vehicle')}; {'authenticated service credential' if authenticated else 'unverified service session'}.",
        f"Powertrain: {profile.get('vehicle_class', 'vehicle')} / {profile.get('quality', 'used')}; fuel {fuel}/{fuel_capacity}; condition {int(profile.get('durability', 0) or 0)}/10.",
        f"Access: {'locked' if lock.get('locked') else 'unlocked'} tier {int(lock.get('lock_tier', 1) or 1)}; ignition {ignition}.",
        f"Tracker: {tracker}; no location history or remote coordinates are exposed by this local bus read.",
    )
    return {
        "ok": True,
        "reason": None,
        "target": target,
        "vehicle": vehicle,
        "authenticated": authenticated,
        "tracker_installed": tracker_installed,
        "tracker_enabled": tracker_enabled,
        "ignition_authorized": ignition_authorized,
        "lines": lines,
    }


def vehicle_wire_shell_rows(sim, actor_eid, target_ref):
    status = vehicle_wire_diagnostics(sim, actor_eid, target_ref)
    if not status.get("ok"):
        return ()
    rows = [{"action": "vehicle_diagnostics", "label": "Controller diagnostics: inspect powertrain, lock, ignition, and tracker."}]
    if not status.get("authenticated"):
        return tuple(rows)
    vehicle = status.get("vehicle") or {}
    lock = property_lock_state(vehicle)
    rows.append({
        "action": "vehicle_toggle_lock",
        "label": f"Authenticated access service: {'unlock' if lock.get('locked') else 'lock'} vehicle.",
    })
    rows.append({
        "action": "vehicle_prime_ignition",
        "label": "Authenticated ignition service: prime a short local start authorization.",
    })
    if status.get("tracker_installed"):
        rows.append({
            "action": "vehicle_toggle_tracker",
            "label": f"Authenticated tracker service: {'stand by' if status.get('tracker_enabled') else 'activate'} local tracker.",
        })
    return tuple(rows)


def perform_vehicle_wire_shell_action(sim, actor_eid, target_ref, action):
    action = str(action or "").strip().lower()
    status = vehicle_wire_diagnostics(sim, actor_eid, target_ref)
    if not status.get("ok"):
        return status
    if action == "vehicle_diagnostics":
        return status
    if not status.get("authenticated"):
        return {"ok": False, "reason": "vehicle_credential_required", "lines": status.get("lines", ())}
    vehicle = status.get("vehicle") or {}
    metadata = vehicle.get("metadata") if isinstance(vehicle.get("metadata"), dict) else None
    if metadata is None:
        metadata = {}
        vehicle["metadata"] = metadata
    vehicle_id = vehicle.get("id")
    now = int(getattr(sim, "tick", 0) or 0)
    if action == "vehicle_toggle_lock":
        lock = property_lock_state(vehicle)
        locked = not bool(lock.get("locked"))
        if not _set_property_locked_override(
            vehicle,
            locked=locked,
            tick=now,
            method="wire_authenticated_vehicle_lock",
        ):
            return {"ok": False, "reason": "vehicle_lock_service_failed", "lines": status.get("lines", ())}
        sim.turn_advance_requested = True
        sim.emit(Event(
            "vehicle_wire_lock_changed",
            eid=actor_eid,
            vehicle_id=vehicle_id,
            vehicle_name=_text(vehicle.get("name"), "vehicle"),
            locked=locked,
            source_kind="wire_authenticated_vehicle_service",
        ))
        return {"ok": True, "reason": None, "feedback": f"Authenticated bus service {'locks' if locked else 'unlocks'} the vehicle."}
    if action == "vehicle_prime_ignition":
        if not bool(vehicle_profile_from_property(vehicle).get("usable")):
            return {"ok": False, "reason": "vehicle_broken", "lines": status.get("lines", ())}
        until_tick = now + VEHICLE_WIRE_IGNITION_AUTH_TICKS
        metadata["vehicle_wire_ignition_actor_eid"] = actor_eid
        metadata["vehicle_wire_ignition_until_tick"] = until_tick
        sim.turn_advance_requested = True
        sim.emit(Event(
            "vehicle_wire_ignition_primed",
            eid=actor_eid,
            vehicle_id=vehicle_id,
            vehicle_name=_text(vehicle.get("name"), "vehicle"),
            authorized_until_tick=until_tick,
            source_kind="wire_authenticated_vehicle_service",
        ))
        return {"ok": True, "reason": None, "feedback": "Authenticated ignition service primes a short local start authorization."}
    if action == "vehicle_toggle_tracker":
        if not status.get("tracker_installed"):
            return {"ok": False, "reason": "vehicle_tracker_not_installed", "lines": status.get("lines", ())}
        enabled = not bool(metadata.get("vehicle_tracker_enabled", False))
        metadata["vehicle_tracker_enabled"] = enabled
        metadata["vehicle_tracker_changed_tick"] = now
        sim.turn_advance_requested = True
        sim.emit(Event(
            "vehicle_wire_tracker_changed",
            eid=actor_eid,
            vehicle_id=vehicle_id,
            vehicle_name=_text(vehicle.get("name"), "vehicle"),
            enabled=enabled,
            source_kind="wire_authenticated_vehicle_service",
        ))
        return {"ok": True, "reason": None, "feedback": f"Authenticated tracker service sets the local tracker to {'active' if enabled else 'standby'}."}
    return {"ok": False, "reason": "unknown_vehicle_wire_action", "lines": status.get("lines", ())}


__all__ = [
    "VEHICLE_WIRE_IGNITION_AUTH_TICKS",
    "perform_vehicle_wire_shell_action",
    "vehicle_wire_actor_authenticated",
    "vehicle_wire_diagnostics",
    "vehicle_wire_shell_rows",
]
