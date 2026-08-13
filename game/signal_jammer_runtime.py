"""Area interference effects produced by the handheld signal jammer."""

from __future__ import annotations

import random

from engine.events import Event
from game.components import CreatureIdentity, DroneState, Position, Vitality
from game.drone_runtime import (
    set_drone_link_disruption,
    set_drone_sensor_suppression,
)
from game.property_runtime import property_distance, property_infrastructure_role


SIGNAL_JAMMER_RADIUS = 10
SIGNAL_JAMMER_COOLDOWN_TICKS = 75
SIGNAL_JAMMER_IFF_TARGET_RADIUS = 10

SIGNAL_JAMMER_EFFECTS = {
    "signal_blackout": {
        "label": "signal blackout",
        "weight": 30,
        "duration": 105,
        "electronic_duration": 70,
    },
    "hard_shutdown": {
        "label": "hard shutdown",
        "weight": 25,
        "duration": 90,
        "electronic_duration": 55,
    },
    "iff_frenzy": {
        "label": "IFF frenzy",
        "weight": 30,
        "duration": 100,
        "electronic_duration": 45,
    },
    "player_lock": {
        "label": "hostile feedback lock",
        "weight": 15,
        "duration": 100,
        "electronic_duration": 45,
        "adverse": True,
    },
}

JAMMABLE_ELECTRONIC_ROLES = frozenset({
    "access_panel",
    "alarm_target",
    "camera_target",
    "security_post",
    "service_terminal",
})


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _metadata(state):
    metadata = getattr(state, "source_metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
        state.source_metadata = metadata
    return metadata


def _timed_status(metadata, key, *, tick=0, **extra):
    until_tick = max(0, _int(metadata.get(key), 0))
    active = until_tick > int(tick)
    result = {
        "active": bool(active),
        "until_tick": int(until_tick),
        "remaining": max(0, int(until_tick) - int(tick)),
    }
    result.update(extra)
    return result


def drone_shutdown_status(state, *, tick=0):
    metadata = _metadata(state)
    return _timed_status(
        metadata,
        "jammer_shutdown_until_tick",
        tick=tick,
        source_eid=metadata.get("jammer_shutdown_source_eid"),
    )


def set_drone_shutdown(state, *, until_tick, source_eid=None):
    metadata = _metadata(state)
    until_tick = max(0, _int(until_tick, 0))
    if until_tick <= 0:
        metadata.pop("jammer_shutdown_until_tick", None)
        metadata.pop("jammer_shutdown_source_eid", None)
    else:
        metadata["jammer_shutdown_until_tick"] = int(until_tick)
        metadata["jammer_shutdown_source_eid"] = source_eid
    return drone_shutdown_status(state, tick=0)


def drone_iff_disruption_status(state, *, tick=0):
    metadata = _metadata(state)
    mode = str(metadata.get("jammer_iff_mode", "") or "").strip().lower()
    return _timed_status(
        metadata,
        "jammer_iff_until_tick",
        tick=tick,
        mode=mode,
        source_eid=metadata.get("jammer_iff_source_eid"),
    )


def set_drone_iff_disruption(state, *, mode="", until_tick=0, source_eid=None):
    metadata = _metadata(state)
    mode = str(mode or "").strip().lower()
    until_tick = max(0, _int(until_tick, 0))
    if not mode or until_tick <= 0:
        if "jammer_iff_saved_target_eid" in metadata:
            state.target_eid = metadata.pop("jammer_iff_saved_target_eid", None)
        if "jammer_iff_saved_target" in metadata:
            saved_target = metadata.pop("jammer_iff_saved_target", None)
            state.target = tuple(saved_target) if isinstance(saved_target, (tuple, list)) else None
        metadata.pop("jammer_iff_until_tick", None)
        metadata.pop("jammer_iff_mode", None)
        metadata.pop("jammer_iff_source_eid", None)
    else:
        if "jammer_iff_until_tick" not in metadata:
            metadata["jammer_iff_saved_target_eid"] = getattr(state, "target_eid", None)
            metadata["jammer_iff_saved_target"] = getattr(state, "target", None)
        metadata["jammer_iff_until_tick"] = int(until_tick)
        metadata["jammer_iff_mode"] = mode
        metadata["jammer_iff_source_eid"] = source_eid
    return drone_iff_disruption_status(state, tick=0)


def clear_expired_drone_jammer_effects(state, *, tick=0):
    """Remove expired jammer state and restore the pre-scramble target."""

    metadata = _metadata(state)
    expired = []
    shutdown_until = _int(metadata.get("jammer_shutdown_until_tick"), 0)
    if shutdown_until > 0 and shutdown_until <= int(tick):
        set_drone_shutdown(state, until_tick=0)
        expired.append("hard_shutdown")
    iff_until = _int(metadata.get("jammer_iff_until_tick"), 0)
    if iff_until > 0 and iff_until <= int(tick):
        expired.append(str(metadata.get("jammer_iff_mode", "iff_frenzy") or "iff_frenzy"))
        set_drone_iff_disruption(state, until_tick=0)
    return tuple(expired)


def electronic_fixture_interference_status(sim, prop, *, tick=None):
    if not isinstance(prop, dict):
        return {"active": False, "until_tick": 0, "remaining": 0}
    if tick is None:
        tick = int(getattr(sim, "tick", 0) or 0)
    disabled = getattr(sim, "camera_disabled", {})
    until_tick = _int(disabled.get(str(prop.get("id", "") or "")), 0) if isinstance(disabled, dict) else 0
    return {
        "active": bool(until_tick > int(tick)),
        "until_tick": int(until_tick),
        "remaining": max(0, int(until_tick) - int(tick)),
    }


def choose_signal_jammer_effect(sim, *, source_eid, source_instance_id="", activation_index=0):
    effect_ids = tuple(SIGNAL_JAMMER_EFFECTS)
    weights = tuple(max(0, _int(SIGNAL_JAMMER_EFFECTS[key].get("weight"), 0)) for key in effect_ids)
    chooser = random.Random(
        f"{getattr(sim, 'seed', 0)}:{getattr(sim, 'tick', 0)}:{source_eid}:"
        f"{source_instance_id}:{int(activation_index)}:signal-jammer-pulse"
    )
    return chooser.choices(effect_ids, weights=weights, k=1)[0]


def _nearby_deployed_drones(sim, x, y, z, *, radius):
    states = sim.ecs.get(DroneState)
    positions = sim.ecs.get(Position)
    rows = []
    for drone_eid in tuple(sim.entity_ids_in_radius(int(x), int(y), int(z), int(radius)) or ()):
        state = states.get(drone_eid)
        pos = positions.get(drone_eid)
        if state is None or pos is None:
            continue
        if str(getattr(state, "mode", "") or "").strip().lower() != "deployed":
            continue
        distance = abs(int(pos.x) - int(x)) + abs(int(pos.y) - int(y))
        rows.append((distance, int(drone_eid), state))
    rows.sort(key=lambda row: (row[0], row[1]))
    return rows


def _nearby_electronic_fixtures(sim, x, y, z, *, radius):
    rows = []
    seen = set()
    for prop in tuple(sim.properties_in_radius(int(x), int(y), int(z), r=int(radius)) or ()):
        if not isinstance(prop, dict):
            continue
        prop_id = str(prop.get("id", "") or "").strip()
        role = str(property_infrastructure_role(prop) or "").strip().lower()
        if not prop_id or prop_id in seen or role not in JAMMABLE_ELECTRONIC_ROLES:
            continue
        seen.add(prop_id)
        rows.append((property_distance(int(x), int(y), prop), prop_id, role, prop))
    rows.sort(key=lambda row: (row[0], row[1]))
    return rows


def activate_signal_jammer_pulse(
    sim,
    source_eid,
    x,
    y,
    z,
    *,
    source_instance_id="",
    activation_index=0,
    effect_id=None,
    radius=SIGNAL_JAMMER_RADIUS,
):
    """Roll and apply one broad jammer pattern to drones and electronics."""

    radius = max(1, _int(radius, SIGNAL_JAMMER_RADIUS))
    effect_id = str(effect_id or "").strip().lower()
    if effect_id not in SIGNAL_JAMMER_EFFECTS:
        effect_id = choose_signal_jammer_effect(
            sim,
            source_eid=source_eid,
            source_instance_id=source_instance_id,
            activation_index=activation_index,
        )
    profile = SIGNAL_JAMMER_EFFECTS[effect_id]
    now = int(getattr(sim, "tick", 0) or 0)
    until_tick = now + max(1, _int(profile.get("duration"), 1))
    affected_drones = _nearby_deployed_drones(sim, x, y, z, radius=radius)

    for _distance, _drone_eid, state in affected_drones:
        if effect_id == "signal_blackout":
            set_drone_link_disruption(
                state,
                until_tick=until_tick,
                source_kind="signal_jammer",
                source_eid=source_eid,
            )
            set_drone_sensor_suppression(
                state,
                until_tick=until_tick,
                source_kind="signal_jammer",
                source_eid=source_eid,
            )
        elif effect_id == "hard_shutdown":
            set_drone_shutdown(state, until_tick=until_tick, source_eid=source_eid)
            set_drone_link_disruption(
                state,
                until_tick=until_tick,
                source_kind="signal_jammer",
                source_eid=source_eid,
            )
            set_drone_sensor_suppression(
                state,
                until_tick=until_tick,
                source_kind="signal_jammer",
                source_eid=source_eid,
            )
        elif effect_id == "iff_frenzy":
            set_drone_iff_disruption(
                state,
                mode="everyone_hostile",
                until_tick=until_tick,
                source_eid=source_eid,
            )
        elif effect_id == "player_lock":
            set_drone_iff_disruption(
                state,
                mode="player_hostile",
                until_tick=until_tick,
                source_eid=source_eid,
            )

    electronic_duration = max(1, _int(profile.get("electronic_duration"), 1))
    electronic_until = now + electronic_duration
    affected_electronics = _nearby_electronic_fixtures(sim, x, y, z, radius=radius)
    disabled = getattr(sim, "camera_disabled", None)
    if not isinstance(disabled, dict):
        sim.camera_disabled = {}
        disabled = sim.camera_disabled
    for _distance, prop_id, _role, _prop in affected_electronics:
        disabled[prop_id] = max(_int(disabled.get(prop_id), 0), int(electronic_until))
    for _distance, prop_id, role, prop in affected_electronics:
        event_type = {
            "alarm_target": "alarm_disabled",
            "camera_target": "camera_disabled",
        }.get(role, "electronic_fixture_jammed")
        sim.emit(Event(
            event_type,
            eid=source_eid,
            source_eid=source_eid,
            source_kind="signal_jammer",
            property_id=prop_id,
            property_name=str(prop.get("name", prop_id) or prop_id),
            infrastructure_role=role,
            disabled_until=int(electronic_until),
            duration=int(electronic_duration),
            x=_int(prop.get("x"), x),
            y=_int(prop.get("y"), y),
            z=_int(prop.get("z"), z),
        ))

    result = {
        "ok": True,
        "effect_id": effect_id,
        "effect_label": str(profile.get("label", effect_id) or effect_id),
        "adverse": bool(profile.get("adverse", False)),
        "radius": int(radius),
        "duration": max(1, _int(profile.get("duration"), 1)),
        "until_tick": int(until_tick),
        "electronic_duration": int(electronic_duration),
        "electronic_until_tick": int(electronic_until),
        "drone_eids": tuple(row[1] for row in affected_drones),
        "drone_count": len(affected_drones),
        "electronic_property_ids": tuple(row[1] for row in affected_electronics),
        "electronic_count": len(affected_electronics),
    }
    sim.emit(Event(
        "signal_jammer_pulse",
        eid=source_eid,
        source_eid=source_eid,
        source_item_instance_id=str(source_instance_id or "").strip() or None,
        x=int(x),
        y=int(y),
        z=int(z),
        **result,
    ))
    return result


def jammer_iff_target_for_drone(sim, drone_eid, state, *, radius=SIGNAL_JAMMER_IFF_TARGET_RADIUS):
    status = drone_iff_disruption_status(state, tick=int(getattr(sim, "tick", 0) or 0))
    if not status.get("active"):
        return None
    drone_pos = sim.ecs.get(Position).get(drone_eid)
    if drone_pos is None:
        return None
    if status.get("mode") == "player_hostile":
        player_eid = getattr(sim, "player_eid", None)
        player_pos = sim.ecs.get(Position).get(player_eid) if player_eid is not None else None
        vitality = sim.ecs.get(Vitality).get(player_eid) if player_eid is not None else None
        if player_pos is None or int(player_pos.z) != int(drone_pos.z):
            return None
        if vitality is not None and int(getattr(vitality, "hp", 0) or 0) <= 0:
            return None
        return player_eid

    candidates = []
    identities = sim.ecs.get(CreatureIdentity)
    positions = sim.ecs.get(Position)
    vitalities = sim.ecs.get(Vitality)
    for candidate_eid in tuple(
        sim.entity_ids_in_radius(
            int(drone_pos.x),
            int(drone_pos.y),
            int(drone_pos.z),
            max(1, _int(radius, SIGNAL_JAMMER_IFF_TARGET_RADIUS)),
        ) or ()
    ):
        if int(candidate_eid) == int(drone_eid):
            continue
        identity = identities.get(candidate_eid)
        candidate_pos = positions.get(candidate_eid)
        vitality = vitalities.get(candidate_eid)
        if identity is None or candidate_pos is None:
            continue
        if str(getattr(identity, "taxonomy_class", "") or "").strip().lower() != "hominid":
            continue
        if vitality is not None and int(getattr(vitality, "hp", 0) or 0) <= 0:
            continue
        distance = abs(int(candidate_pos.x) - int(drone_pos.x)) + abs(int(candidate_pos.y) - int(drone_pos.y))
        candidates.append((distance, int(candidate_eid)))
    candidates.sort(key=lambda row: (row[0], row[1]))
    return candidates[0][1] if candidates else None


__all__ = [
    "JAMMABLE_ELECTRONIC_ROLES",
    "SIGNAL_JAMMER_COOLDOWN_TICKS",
    "SIGNAL_JAMMER_EFFECTS",
    "SIGNAL_JAMMER_RADIUS",
    "activate_signal_jammer_pulse",
    "choose_signal_jammer_effect",
    "clear_expired_drone_jammer_effects",
    "drone_iff_disruption_status",
    "drone_shutdown_status",
    "electronic_fixture_interference_status",
    "jammer_iff_target_for_drone",
    "set_drone_iff_disruption",
    "set_drone_shutdown",
]
