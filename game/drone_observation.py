"""Honest onboard watching, pursuit, and radio handoff for deployed drones."""

from __future__ import annotations

from copy import deepcopy

from engine.events import Event
from game.components import AI, NPCMemory, NPCWill, Position
from game.drone_recon import autonomous_sensor_status, drone_has_radio_comms
from game.drone_runtime import drone_link_disruption_status
from game.purposeful_observation import (
    advance_purposeful_actor_observation,
    is_purposeful_observation,
    observation_context_purpose,
)


DRONE_WATCH_CONTEXT_PURPOSES = frozenset({"drone_person_watch", "drone_threat_watch"})


def _int_or_none(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _position_tuple(value):
    if not isinstance(value, (tuple, list)) or len(value) < 3:
        return None
    try:
        return (int(value[0]), int(value[1]), int(value[2]))
    except (TypeError, ValueError):
        return None


def _binding_entity_eid(state, slot_key):
    bindings = getattr(state, "procedure_bindings", None)
    binding = bindings.get(str(slot_key or "").strip().upper()) if isinstance(bindings, dict) else None
    if not isinstance(binding, dict):
        return None
    return _int_or_none(binding.get("eid", binding.get("person_eid")))


def _context_for_state(state, *, purpose=None, subject_eid=None):
    context = getattr(state, "observation_context", None)
    if not is_purposeful_observation(context, active_only=True):
        return None
    if purpose is not None and observation_context_purpose(context) != str(purpose):
        return None
    if subject_eid is not None and _int_or_none(context.get("subject_eid")) != _int_or_none(subject_eid):
        return None
    return context


def _program_kind(state):
    return str(getattr(state, "procedure_program_id", "") or getattr(state, "procedure_key", "") or "").strip().lower()


def _owner_target(sim, state):
    owner_eid = _int_or_none(getattr(state, "owner_eid", None) or getattr(state, "controller_eid", None))
    if owner_eid is None:
        return None
    for component_type in (NPCWill, AI):
        component = sim.ecs.get(component_type).get(owner_eid)
        target_eid = _int_or_none(getattr(component, "target_eid", None)) if component is not None else None
        if target_eid is not None:
            return target_eid
    return None


def _candidate_is_hostile(sim, candidate_eid, state, *, preferred_eid=None):
    candidate_eid = _int_or_none(candidate_eid)
    if candidate_eid is None:
        return False
    owner_eid = _int_or_none(getattr(state, "owner_eid", None))
    controller_eid = _int_or_none(getattr(state, "controller_eid", None))
    excluded = {value for value in (owner_eid, controller_eid) if value is not None}
    if candidate_eid in excluded:
        return False
    if preferred_eid is not None and candidate_eid == _int_or_none(preferred_eid):
        return True
    candidate_targets = set()
    for component_type in (NPCWill, AI):
        component = sim.ecs.get(component_type).get(candidate_eid)
        target_eid = _int_or_none(getattr(component, "target_eid", None)) if component is not None else None
        if target_eid is not None:
            candidate_targets.add(target_eid)
    if candidate_targets & excluded:
        return True
    return _owner_target(sim, state) == candidate_eid


def _sensor_hostile_near(sim, drone_eid, state, status, *, anchor=None, preferred_eid=None):
    drone_pos = sim.ecs.get(Position).get(drone_eid)
    if drone_pos is None or not status.get("ok"):
        return None
    visible = set(status.get("visible", ()) or ())
    radius = max(1, int(status.get("radius", 1) or 1))
    anchor = _position_tuple(anchor) or (int(drone_pos.x), int(drone_pos.y), int(drone_pos.z))
    query_radius = min(radius, 10)
    candidates = []
    for raw_eid in tuple(sim.entity_ids_in_radius(anchor[0], anchor[1], anchor[2], query_radius) or ()):
        candidate_eid = _int_or_none(raw_eid)
        if candidate_eid is None or candidate_eid == int(drone_eid):
            continue
        candidate_pos = sim.ecs.get(Position).get(candidate_eid)
        if candidate_pos is None:
            continue
        candidate_xyz = (int(candidate_pos.x), int(candidate_pos.y), int(candidate_pos.z))
        if candidate_xyz not in visible:
            continue
        if not _candidate_is_hostile(sim, candidate_eid, state, preferred_eid=preferred_eid):
            continue
        distance = abs(int(drone_pos.x) - candidate_xyz[0]) + abs(int(drone_pos.y) - candidate_xyz[1])
        candidates.append((distance, candidate_eid))
    candidates.sort(key=lambda row: (row[0], row[1]))
    return candidates[0][1] if candidates else None


def _watch_transition(sim, controller_eid, drone_eid, state, context, previous, phase):
    previous_active = is_purposeful_observation(previous, active_only=True)
    current_active = is_purposeful_observation(context, active_only=True)
    previous_subject = _int_or_none((previous or {}).get("subject_eid")) if isinstance(previous, dict) else None
    current_subject = _int_or_none((context or {}).get("subject_eid")) if isinstance(context, dict) else None
    previous_lost = (previous or {}).get("lost_contact_since_tick") if isinstance(previous, dict) else None
    current_lost = (context or {}).get("lost_contact_since_tick") if isinstance(context, dict) else None
    event_type = None
    if current_active and (not previous_active or previous_subject != current_subject):
        event_type = "drone_watch_acquired"
    elif current_active and previous_lost is None and current_lost is not None:
        event_type = "drone_watch_lost_contact"
    elif previous_active and not current_active:
        event_type = "drone_watch_abandoned"
    if event_type is None:
        return
    identity_resolved = bool((context or {}).get("identity_resolved"))
    sim.emit(Event(
        event_type,
        eid=controller_eid,
        controller_eid=controller_eid,
        owner_eid=getattr(state, "owner_eid", None),
        drone_eid=drone_eid,
        phase=phase,
        purpose=observation_context_purpose(context or previous),
        sensor_kind=str((context or previous or {}).get("sensor_kind", "") or ""),
        subject_eid=current_subject if identity_resolved else None,
        identity_resolved=identity_resolved,
        position=_position_tuple((context or previous or {}).get("last_seen_position")),
    ))


def advance_drone_watch(drone_system, controller_eid, drone_eid, state, *, slot_key, resolved=None):
    """Advance one WATCH instruction from genuine onboard sensor contact."""

    sim = drone_system.sim
    program_kind = _program_kind(state)
    threat_watch = program_kind in {"guard_zone", "protect_operator"}
    purpose = "drone_threat_watch" if threat_watch else "drone_person_watch"
    existing = _context_for_state(state, purpose=purpose)
    resolved = resolved if isinstance(resolved, dict) else {}
    preferred_eid = _owner_target(sim, state) if threat_watch else None
    anchor = resolved.get("target") if resolved.get("ok") else None

    sensor_purpose = "threat" if threat_watch else "visual"
    status = autonomous_sensor_status(sim, drone_eid, purpose=sensor_purpose)
    if threat_watch:
        if existing is not None:
            subject_eid = _int_or_none(existing.get("subject_eid"))
        else:
            subject_eid = _sensor_hostile_near(
                sim,
                drone_eid,
                state,
                status,
                anchor=anchor,
                preferred_eid=preferred_eid,
            )
    else:
        subject_eid = _binding_entity_eid(state, slot_key)
        if subject_eid is None and resolved.get("ok") and resolved.get("kind") == "entity":
            subject_eid = _int_or_none(resolved.get("eid"))
        if subject_eid is None and existing is not None:
            subject_eid = _int_or_none(existing.get("subject_eid"))

    if subject_eid is None:
        if status.get("ok"):
            state.observation_context = None
            metadata = getattr(state, "source_metadata", {})
            if isinstance(metadata, dict):
                metadata.pop("program_seen_hostile_eid", None)
            return {"ok": True, "reason": None, "action": "watch_clear", "phase": "clear"}
        return {"ok": False, "reason": status.get("reason", "missing_target")}
    if not status.get("ok") and existing is None:
        return {"ok": False, "reason": status.get("reason", "no_watch_sensor")}

    previous = deepcopy(existing) if isinstance(existing, dict) else None
    context, phase, movement_target = advance_purposeful_actor_observation(
        sim,
        drone_eid,
        subject_eid,
        purpose=purpose,
        existing=existing,
        sight_radius=max(1, int(status.get("radius", 1) or 1)),
        capture_subject_account=bool(status.get("visual_identity")),
        include_subject_account=bool(status.get("visual_identity")),
        sensor_visible_positions=status.get("visible", set()) if status.get("ok") else set(),
    )
    if isinstance(context, dict):
        context = dict(context)
        context["sensor_kind"] = str(status.get("sensor_kind") or (existing or {}).get("sensor_kind") or "sensor")
        context["sensor_label"] = str(status.get("sensor_label") or (existing or {}).get("sensor_label") or context["sensor_kind"])
        context["contact_kind"] = "identified_person" if not threat_watch else "hostile_contact"
        context["identity_resolved"] = bool(status.get("visual_identity"))
        context["radio_reportable"] = bool(drone_has_radio_comms(state))
        state.observation_context = context
    else:
        state.observation_context = None

    metadata = getattr(state, "source_metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
        state.source_metadata = metadata
    if threat_watch and is_purposeful_observation(context, active_only=True) and phase == "visible":
        metadata["program_seen_hostile_eid"] = int(subject_eid)
    elif threat_watch:
        metadata.pop("program_seen_hostile_eid", None)
    metadata["drone_watch_phase"] = str(phase)
    metadata["drone_watch_sensor_kind"] = str((context or {}).get("sensor_kind", "") or "")
    _watch_transition(sim, controller_eid, drone_eid, state, context, previous, phase)

    target = _position_tuple(movement_target)
    if target is not None:
        state.target = target
        result = drone_system.move_drone_toward(controller_eid, drone_eid, target)
        if not result.get("ok"):
            return result
        action = "watch_hold" if result.get("action") == "arrived" else "watch_pursue"
        return {"ok": True, "reason": None, "action": action, "phase": phase, "target": target}
    return {"ok": True, "reason": None, "action": f"watch_{phase}", "phase": phase}


def report_drone_watch(sim, controller_eid, drone_eid, state):
    """Transmit the latest bounded watch fact without upgrading its identity."""

    if drone_link_disruption_status(state, tick=int(getattr(sim, "tick", 0) or 0)).get("active"):
        return {"ok": True, "reason": "link_disrupted", "action": "report_unavailable", "reported": False}
    if not drone_has_radio_comms(state):
        return {"ok": True, "reason": "no_radio", "action": "report_unavailable", "reported": False}
    context = getattr(state, "observation_context", None)
    if not is_purposeful_observation(context):
        return {"ok": True, "reason": None, "action": "report_clear", "reported": False}
    position = _position_tuple(context.get("last_seen_position"))
    if position is None:
        return {"ok": True, "reason": None, "action": "report_clear", "reported": False}
    identity_resolved = bool(context.get("identity_resolved"))
    subject_eid = _int_or_none(context.get("subject_eid")) if identity_resolved else None
    report = {
        "tick": int(getattr(sim, "tick", 0) or 0),
        "observed_tick": int(context.get("last_seen_tick", 0) or 0),
        "position": position,
        "purpose": observation_context_purpose(context),
        "phase": "searching" if bool((context.get("search_state") or {}).get("active")) else "tracking" if context.get("active") else "lost",
        "sensor_kind": str(context.get("sensor_kind", "sensor") or "sensor"),
        "contact_kind": str(context.get("contact_kind", "contact") or "contact"),
        "identity_resolved": identity_resolved,
        "subject_eid": subject_eid,
        "subject_account": deepcopy(context.get("subject_account")) if identity_resolved and isinstance(context.get("subject_account"), dict) else {},
    }
    previous = getattr(state, "last_watch_report", None)
    signature = (report["observed_tick"], report["position"], report["phase"], report["sensor_kind"], report["subject_eid"])
    previous_signature = None
    if isinstance(previous, dict):
        previous_signature = (
            previous.get("observed_tick"),
            _position_tuple(previous.get("position")),
            previous.get("phase"),
            previous.get("sensor_kind"),
            previous.get("subject_eid"),
        )
    state.last_watch_report = report
    if signature == previous_signature:
        return {"ok": True, "reason": None, "action": "report_unchanged", "reported": False, "report": report}

    recipients = []
    for raw_eid in (controller_eid, getattr(state, "owner_eid", None)):
        recipient_eid = _int_or_none(raw_eid)
        if recipient_eid is not None and recipient_eid != int(drone_eid) and recipient_eid not in recipients:
            recipients.append(recipient_eid)
    for recipient_eid in recipients:
        memory = sim.ecs.get(NPCMemory).get(recipient_eid)
        if memory is not None:
            memory.remember(
                report["tick"],
                "drone_watch_report",
                strength=0.9 if identity_resolved else 0.68,
                drone_eid=int(drone_eid),
                position=position,
                observed_tick=report["observed_tick"],
                sensor_kind=report["sensor_kind"],
                contact_kind=report["contact_kind"],
                subject_eid=subject_eid,
            )
        sim.emit(Event(
            "drone_watch_reported",
            eid=recipient_eid,
            recipient_eid=recipient_eid,
            controller_eid=controller_eid,
            owner_eid=getattr(state, "owner_eid", None),
            drone_eid=drone_eid,
            position=position,
            observed_tick=report["observed_tick"],
            purpose=report["purpose"],
            phase=report["phase"],
            sensor_kind=report["sensor_kind"],
            contact_kind=report["contact_kind"],
            identity_resolved=identity_resolved,
            subject_eid=subject_eid,
        ))
    return {"ok": True, "reason": None, "action": "report", "reported": bool(recipients), "report": report}


__all__ = [
    "DRONE_WATCH_CONTEXT_PURPOSES",
    "advance_drone_watch",
    "report_drone_watch",
]
