"""Bounded Wire actions against deployed radio drones."""

from __future__ import annotations

from collections.abc import Mapping

from engine.events import Event
from game.components import IncidentKnowledge, Position
from game.drone_runtime import (
    drone_link_disruption_status,
    drone_sensor_suppression_status,
    drone_state_controlled_by_actor,
    drone_state_has_capability,
    set_drone_link_disruption,
    set_drone_sensor_suppression,
)
from game.incident_runtime import create_or_merge_incident
from game.wire_targets import resolve_wire_target, wire_target_has_live_radio


DRONE_WIRE_SENSOR_SUPPRESSION_TICKS = 12
DRONE_WIRE_LINK_DISRUPTION_TICKS = 18


def _text(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _scene_drone_target(sim, scene):
    if not isinstance(scene, Mapping) or str(scene.get("target_kind", "") or "").strip().lower() != "drone":
        return None
    target = resolve_wire_target(sim, scene.get("target_ref"))
    return target if isinstance(target, Mapping) and target.get("kind") == "drone" else None


def drone_wire_diagnostics(sim, actor_eid, target_ref):
    target = resolve_wire_target(sim, target_ref)
    if not isinstance(target, Mapping) or target.get("kind") != "drone":
        return {"ok": False, "reason": "target_unavailable", "lines": ()}
    state = target.get("drone_state")
    metadata = dict(target.get("metadata") or {})
    now = int(getattr(sim, "tick", 0) or 0)
    link = drone_link_disruption_status(state, tick=now)
    suppression = drone_sensor_suppression_status(state, tick=now)
    controlled = bool(drone_state_controlled_by_actor(state, actor_eid))
    routine = _text(metadata.get("procedure_program_id") or metadata.get("procedure_key"), "idle").replace("_", " ")
    modules = tuple(metadata.get("module_ids", ()) or ())
    sensors = [
        str(module_id).replace("drone_", "").replace("_module", "").replace("_", " ")
        for module_id in modules
        if any(token in str(module_id) for token in ("camera", "sensor", "radar", "lidar", "sonar", "thermal"))
    ]
    radio = "live" if wire_target_has_live_radio(target, tick=now) else "down"
    if link.get("active"):
        radio = f"handshake disrupted for {int(link.get('remaining', 0))} ticks"
    sensor_text = ", ".join(sensors) if sensors else "none exposed"
    suppression_text = (
        f"suppressed for {int(suppression.get('remaining', 0))} ticks"
        if suppression.get("active")
        else "online"
    )
    lines = (
        f"Handshake: {target.get('name', 'drone')} radio {radio}; {'authenticated controller' if controlled else 'unverified controller'}.",
        f"Power: {int(metadata.get('battery_charge', 0) or 0)}/{int(metadata.get('battery_charge_max', 0) or 0)}; routine {routine}.",
        f"Sensors: {sensor_text}; feed {suppression_text}.",
    )
    return {
        "ok": True,
        "reason": None,
        "target": target,
        "controlled": controlled,
        "link": link,
        "suppression": suppression,
        "lines": lines,
    }


def drone_wire_shell_rows(sim, actor_eid, target_ref):
    status = drone_wire_diagnostics(sim, actor_eid, target_ref)
    if not status.get("ok"):
        return ()
    rows = [{"action": "drone_diagnostics", "label": "Handshake diagnostics: inspect radio, power, routine, and sensors."}]
    target = status.get("target") or {}
    state = target.get("drone_state")
    if status.get("controlled") and drone_state_has_capability(state, "remote_control"):
        rows.append({"action": "drone_request_return", "label": "Authenticated route nudge: request Return Home."})
    if status.get("controlled") and (status.get("suppression") or {}).get("active"):
        rows.append({"action": "drone_restore_sensors", "label": "Authenticated repair: restore the suppressed sensor feed."})
    if status.get("controlled") and (status.get("link") or {}).get("active"):
        target = status.get("target") or {}
        actor_pos = sim.ecs.get(Position).get(actor_eid)
        adjacent = bool(
            actor_pos is not None
            and int(actor_pos.z) == int(target.get("z", 0) or 0)
            and abs(int(actor_pos.x) - int(target.get("x", 0) or 0))
            + abs(int(actor_pos.y) - int(target.get("y", 0) or 0)) <= 1
        )
        suffix = "" if adjacent else " [move adjacent to the drone]"
        rows.append({
            "action": "drone_restore_link",
            "label": f"Physical radio resync: restore the authenticated external link.{suffix}",
        })
    return tuple(rows)


def perform_drone_wire_shell_action(sim, actor_eid, target_ref, action):
    action = str(action or "").strip().lower()
    status = drone_wire_diagnostics(sim, actor_eid, target_ref)
    if not status.get("ok"):
        return status
    target = status.get("target") or {}
    state = target.get("drone_state")
    drone_eid = target.get("drone_eid")
    if action == "drone_diagnostics":
        return status
    if not status.get("controlled"):
        return {"ok": False, "reason": "not_controller", "lines": status.get("lines", ())}
    if action == "drone_request_return":
        if (status.get("link") or {}).get("active"):
            return {"ok": False, "reason": "link_disrupted", "lines": status.get("lines", ())}
        if not drone_state_has_capability(state, "remote_control"):
            return {"ok": False, "reason": "no_remote_control", "lines": status.get("lines", ())}
        sim.emit(Event(
            "drone_command_request",
            eid=actor_eid,
            controller_eid=actor_eid,
            drone_eid=drone_eid,
            command="return",
            source_kind="wire_authenticated_route",
            consume_turn=False,
        ))
        sim.turn_advance_requested = True
        sim.emit(Event(
            "drone_wire_route_nudged",
            eid=actor_eid,
            drone_eid=drone_eid,
            command="return",
        ))
        return {"ok": True, "reason": None, "feedback": "Authenticated route nudge requests Return Home."}
    if action == "drone_restore_sensors":
        if (status.get("link") or {}).get("active"):
            return {"ok": False, "reason": "link_disrupted", "lines": status.get("lines", ())}
        set_drone_sensor_suppression(state, until_tick=0)
        sim.turn_advance_requested = True
        sim.emit(Event(
            "drone_wire_sensor_restored",
            eid=actor_eid,
            drone_eid=drone_eid,
            source_kind="wire_authenticated_repair",
        ))
        return {"ok": True, "reason": None, "feedback": "Authenticated repair restores the drone sensor feed."}
    if action == "drone_restore_link":
        link = status.get("link") or {}
        if not link.get("active"):
            return {"ok": False, "reason": "link_not_disrupted", "lines": status.get("lines", ())}
        actor_pos = sim.ecs.get(Position).get(actor_eid)
        if (
            actor_pos is None
            or int(actor_pos.z) != int(target.get("z", 0) or 0)
            or abs(int(actor_pos.x) - int(target.get("x", 0) or 0))
            + abs(int(actor_pos.y) - int(target.get("y", 0) or 0)) > 1
        ):
            return {
                "ok": False,
                "reason": "physical_resync_requires_adjacency",
                "lines": status.get("lines", ()),
            }
        set_drone_link_disruption(state, until_tick=0)
        sim.turn_advance_requested = True
        sim.emit(Event(
            "drone_wire_link_restored",
            eid=actor_eid,
            controller_eid=getattr(state, "controller_eid", None),
            owner_eid=getattr(state, "owner_eid", None),
            drone_eid=drone_eid,
            reason="physical_resync",
            source_kind="wire_physical_resync",
        ))
        return {"ok": True, "reason": None, "feedback": "Physical radio resync restores the authenticated external link."}
    return {"ok": False, "reason": "unknown_drone_wire_action", "lines": status.get("lines", ())}


def drone_wire_camera_loop_preflight(sim, scene):
    target = _scene_drone_target(sim, scene)
    if not isinstance(target, Mapping):
        return {"ok": False, "reason": "missing_drone_target"}
    if not wire_target_has_live_radio(target, tick=int(getattr(sim, "tick", 0) or 0)):
        return {"ok": False, "reason": "target_radio_unavailable"}
    state = target.get("drone_state")
    has_sensor = any(
        drone_state_has_capability(state, capability)
        for capability in ("camera", "sensor", "linked_sensor", "mapping_sensor", "thermal", "radar")
    )
    if not has_sensor:
        return {"ok": False, "reason": "no_sensor_target"}
    return {"ok": True, "reason": None, "drone_eid": target.get("drone_eid"), "target": target}


def apply_drone_wire_camera_loop(sim, actor_eid, scene):
    preflight = drone_wire_camera_loop_preflight(sim, scene)
    if not preflight.get("ok"):
        return preflight
    target = preflight.get("target") or {}
    state = target.get("drone_state")
    now = int(getattr(sim, "tick", 0) or 0)
    existing = drone_sensor_suppression_status(state, tick=now)
    until_tick = max(
        int(existing.get("until_tick", 0) or 0),
        now + DRONE_WIRE_SENSOR_SUPPRESSION_TICKS,
    )
    set_drone_sensor_suppression(
        state,
        until_tick=until_tick,
        source_kind="wire_camera_loop",
        source_eid=actor_eid,
    )
    drone_eid = target.get("drone_eid")
    sim.emit(Event(
        "drone_wire_sensor_suppressed",
        eid=actor_eid,
        responsible_eid=actor_eid,
        drone_eid=drone_eid,
        target_eid=drone_eid,
        source_kind="wire_camera_loop",
        suppressed_until_tick=until_tick,
        scene_id=(scene or {}).get("scene_id"),
    ))
    return {
        "ok": True,
        "reason": None,
        "feedback": "Camera loop suppresses the drone sensor feed for a short window.",
        "target_id": drone_eid,
        "forced_disconnect": False,
        "suppressed_until_tick": until_tick,
    }


def drone_wire_handshake_breaker_preflight(sim, actor_eid, scene):
    target = _scene_drone_target(sim, scene)
    if not isinstance(target, Mapping):
        return {"ok": False, "reason": "missing_drone_target"}
    state = target.get("drone_state")
    if drone_state_controlled_by_actor(state, actor_eid):
        return {"ok": False, "reason": "target_already_controlled"}
    now = int(getattr(sim, "tick", 0) or 0)
    if drone_link_disruption_status(state, tick=now).get("active"):
        return {"ok": False, "reason": "link_already_disrupted"}
    if not wire_target_has_live_radio(target, tick=now):
        return {"ok": False, "reason": "target_radio_unavailable"}
    return {"ok": True, "reason": None, "drone_eid": target.get("drone_eid"), "target": target}


def _drone_report_recipients(state, *, exclude=()):
    excluded = {str(value) for value in tuple(exclude or ()) if value is not None}
    recipients = []
    for value in (getattr(state, "owner_eid", None), getattr(state, "controller_eid", None)):
        if value is None or str(value) in excluded:
            continue
        try:
            recipient = int(value)
        except (TypeError, ValueError):
            continue
        if recipient not in recipients:
            recipients.append(recipient)
    return tuple(recipients)


def promote_drone_wire_intrusion_report(sim, actor_eid, target, *, reason="handshake_breaker", confidence=0.78):
    if not isinstance(target, Mapping):
        return None
    state = target.get("drone_state")
    drone_eid = target.get("drone_eid")
    recipients = _drone_report_recipients(state, exclude=(actor_eid, drone_eid))
    if not recipients:
        return None
    incident, _merged = create_or_merge_incident(
        sim,
        kind="wire_intrusion",
        x=target.get("x"),
        y=target.get("y"),
        z=target.get("z", 0),
        tick=getattr(sim, "tick", 0),
        severity=46,
        primary_actor_eid=actor_eid,
        victim_eid=drone_eid,
        victim_name=_text(target.get("name"), "drone"),
        owner_eid=recipients[0],
        merge_subject=f"drone-wire:{target.get('identity', drone_eid)}:{actor_eid}",
        source_event="drone_wire_security_report",
        official_reportable=True,
        note="Technical security report from a false-controller drone handshake.",
        tags=("wire", "technical_security_report", "drone_radio", reason),
    )
    for recipient in recipients:
        knowledge = sim.ecs.get(IncidentKnowledge).get(recipient)
        if knowledge is None:
            sim.ecs.add(recipient, IncidentKnowledge())
            knowledge = sim.ecs.get(IncidentKnowledge).get(recipient)
        knowledge.remember(
            incident.get("id"),
            learned_tick=getattr(sim, "tick", 0),
            source_kind="drone_wire_security_report",
            source_eid=drone_eid,
            confidence=confidence,
            firsthand=False,
            propagation_depth=0,
            urgency=0.24,
            social_interest=0.08,
            category="official",
            kind=incident.get("kind"),
            tags=incident.get("tags", ()),
            severity=int(incident.get("severity", 0) or 0),
            x=incident.get("x"),
            y=incident.get("y"),
            z=incident.get("z"),
        )
    sim.emit(Event(
        "drone_wire_intrusion_reported",
        eid=actor_eid,
        responsible_eid=actor_eid,
        drone_eid=drone_eid,
        target_eid=drone_eid,
        owner_eid=recipients[0],
        recipient_eids=recipients,
        incident_id=incident.get("id"),
        reason=reason,
        source_kind="drone_wire_security_report",
        observation_channel="technical_security_report",
        firsthand=False,
        confidence=confidence,
    ))
    return incident


def apply_drone_wire_handshake_breaker(sim, actor_eid, scene):
    preflight = drone_wire_handshake_breaker_preflight(sim, actor_eid, scene)
    if not preflight.get("ok"):
        return preflight
    target = preflight.get("target") or {}
    state = target.get("drone_state")
    now = int(getattr(sim, "tick", 0) or 0)
    until_tick = now + DRONE_WIRE_LINK_DISRUPTION_TICKS
    promote_drone_wire_intrusion_report(sim, actor_eid, target)
    set_drone_link_disruption(
        state,
        until_tick=until_tick,
        source_kind="wire_handshake_breaker",
        source_eid=actor_eid,
    )
    drone_eid = target.get("drone_eid")
    sim.emit(Event(
        "drone_wire_link_disrupted",
        eid=actor_eid,
        responsible_eid=actor_eid,
        controller_eid=getattr(state, "controller_eid", None),
        owner_eid=getattr(state, "owner_eid", None),
        drone_eid=drone_eid,
        target_eid=drone_eid,
        source_kind="wire_handshake_breaker",
        disrupted_until_tick=until_tick,
        scene_id=(scene or {}).get("scene_id"),
    ))
    return {
        "ok": True,
        "reason": None,
        "feedback": "A noisy false-controller handshake makes the drone report the intrusion, then cuts its external link for a short window; onboard autonomy stays live.",
        "target_id": drone_eid,
        "forced_disconnect": True,
        "disconnect_reason": "drone_link_disrupted",
        "disrupted_until_tick": until_tick,
    }


__all__ = [
    "DRONE_WIRE_LINK_DISRUPTION_TICKS",
    "DRONE_WIRE_SENSOR_SUPPRESSION_TICKS",
    "apply_drone_wire_handshake_breaker",
    "apply_drone_wire_camera_loop",
    "drone_wire_handshake_breaker_preflight",
    "drone_wire_camera_loop_preflight",
    "drone_wire_diagnostics",
    "drone_wire_shell_rows",
    "perform_drone_wire_shell_action",
    "promote_drone_wire_intrusion_report",
]
