"""Physical consequence adapter for wire-layer actions and failures."""

from __future__ import annotations

from collections.abc import Mapping

from engine.events import Event
from engine.systems import System
from game.components import DroneState, IncidentKnowledge, Inventory, Position, StatusEffects, Vitality
from game.incident_runtime import create_or_merge_incident
from game.property_access import apply_controller_intrusion
from game.property_runtime import property_linked_property_id
from game.wire_kit import wire_state_for_actor
from game.wire_runtime import normalize_wire_interface_metadata, wire_interface_profile_for_item
from game.drone_runtime import drone_state_controlled_by_actor, drone_state_has_capability


WIRE_SECURITY_LABELS = {
    1: "quiet",
    2: "logged",
    3: "investigating",
    4: "alert",
    5: "locked",
}
WIRE_SECURITY_SMALL_RESET_TICKS = 600
WIRE_SECURITY_ORG_RESET_TICKS = 1800
WIRE_SECURITY_HARDENED_RESET_TICKS = 3600
WIRE_RECOVERY_MIN_TICKS = 3

_ORG_OWNER_TAGS = {
    "corp",
    "corporate",
    "security",
    "gang",
    "cult",
    "civic",
    "organization",
    "org",
}
_HARDENED_OWNER_TAGS = {"justice", "police", "military", "objective"}
_HARDENED_ARCHETYPES = {
    "armory",
    "barracks",
    "checkpoint",
    "command_center",
    "courthouse",
    "data_center",
    "jail",
    "prison",
    "server_hub",
}


def _text(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _key(value, default=""):
    return _text(value, default).lower()


def _int(value, default=0, *, minimum=None, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(default)
    if minimum is not None:
        number = max(int(minimum), number)
    if maximum is not None:
        number = min(int(maximum), number)
    return int(number)


def _prop_metadata(prop, *, create=False):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    if not isinstance(metadata, dict):
        if not create:
            return {}
        metadata = {}
        prop["metadata"] = metadata
    return metadata


def _scene_or_connection(mapping):
    return mapping if isinstance(mapping, Mapping) else {}


def wire_network_key(scene_or_connection, prop=None):
    row = _scene_or_connection(scene_or_connection)
    linked_id = _text(row.get("linked_property_id"))
    target_id = _text(row.get("target_property_id") or (prop or {}).get("id"))
    target_class = _key(row.get("target_class"))
    if linked_id:
        return f"property:{linked_id}"
    if target_id:
        return f"{target_class or 'target'}:{target_id}"
    return _text(row.get("scene_id"), "wire:unknown")


def wire_network_property(sim, scene_or_connection=None, prop=None):
    if isinstance(prop, dict):
        return prop
    row = _scene_or_connection(scene_or_connection)
    linked_id = _text(row.get("linked_property_id"))
    target_id = _text(row.get("target_property_id"))
    properties = getattr(sim, "properties", {}) if sim is not None else {}
    if linked_id and isinstance(properties.get(linked_id), dict):
        return properties[linked_id]
    if target_id and isinstance(properties.get(target_id), dict):
        return properties[target_id]
    return None


def wire_security_reset_delay(prop):
    metadata = _prop_metadata(prop)
    owner_tag = _key((prop or {}).get("owner_tag") or metadata.get("owner_tag"))
    archetype = _key(metadata.get("archetype") or metadata.get("service_archetype"))
    security = _int(metadata.get("security_tier") or metadata.get("security"), 1, minimum=0)
    if owner_tag in _HARDENED_OWNER_TAGS or archetype in _HARDENED_ARCHETYPES or security >= 4:
        return WIRE_SECURITY_HARDENED_RESET_TICKS
    if owner_tag in _ORG_OWNER_TAGS or security >= 3:
        return WIRE_SECURITY_ORG_RESET_TICKS
    return WIRE_SECURITY_SMALL_RESET_TICKS


def _wire_security_store(prop, *, create=False):
    metadata = _prop_metadata(prop, create=create)
    store = metadata.get("wire_security")
    if not isinstance(store, dict):
        if not create:
            return {}
        store = {}
        metadata["wire_security"] = store
    return store


def _normalize_security_state(sim, prop, key, *, create=False):
    store = _wire_security_store(prop, create=create)
    if not isinstance(store, dict):
        return None
    row = store.get(key)
    if not isinstance(row, dict):
        if not create:
            return None
        row = {}
        store[key] = row
    now = _int(getattr(sim, "tick", 0), 0)
    level = _int(row.get("level"), 1, minimum=1, maximum=5)
    locked_until = _int(row.get("locked_until_tick"), 0, minimum=0)
    if locked_until and locked_until <= now:
        level = min(3, max(1, _int(row.get("post_lock_reset_level"), 3, minimum=1, maximum=5)))
        locked_until = 0
        row["last_reset_tick"] = now
    row["level"] = level
    row["label"] = WIRE_SECURITY_LABELS.get(level, "quiet")
    row["locked_until_tick"] = locked_until
    row.setdefault("logs", [])
    row.setdefault("last_event_tick", now)
    return row


def wire_security_state(sim, scene_or_connection=None, prop=None, *, create=True):
    target_prop = wire_network_property(sim, scene_or_connection, prop=prop)
    if not isinstance(target_prop, dict):
        return None
    key = wire_network_key(scene_or_connection, target_prop)
    return _normalize_security_state(sim, target_prop, key, create=create)


def wire_security_lockout_status(sim, scene_or_connection=None, prop=None):
    target_prop = wire_network_property(sim, scene_or_connection, prop=prop)
    if not isinstance(target_prop, dict):
        return {"locked": False, "state": None, "remaining": 0}
    key = wire_network_key(scene_or_connection, target_prop)
    state = _normalize_security_state(sim, target_prop, key, create=False)
    if not isinstance(state, dict):
        return {"locked": False, "state": None, "remaining": 0}
    now = _int(getattr(sim, "tick", 0), 0)
    locked_until = _int(state.get("locked_until_tick"), 0, minimum=0)
    locked = bool(_int(state.get("level"), 1, minimum=1, maximum=5) >= 5 and locked_until > now)
    return {
        "locked": locked,
        "state": state,
        "remaining": max(0, locked_until - now),
    }


def wire_recovery_status(sim, actor_eid):
    state = wire_state_for_actor(sim, actor_eid, create=False)
    last = getattr(state, "last_ejection_state", None) if state is not None else None
    if not isinstance(last, Mapping):
        return {"active": False, "remaining": 0, "state": None}
    now = _int(getattr(sim, "tick", 0), 0)
    until = _int(last.get("recovery_until_tick"), 0, minimum=0)
    return {"active": until > now, "remaining": max(0, until - now), "state": dict(last)}


def wire_connection_blockers(sim, actor_eid, scene_or_connection=None, prop=None):
    blockers = []
    recovery = wire_recovery_status(sim, actor_eid)
    if recovery.get("active"):
        blockers.append("wire_recovery")
    lockout = wire_security_lockout_status(sim, scene_or_connection, prop=prop)
    if lockout.get("locked"):
        blockers.append("wire_network_locked")
    return tuple(blockers)


def _interface_metadata_for_scene(sim, actor_eid, scene=None):
    state = wire_state_for_actor(sim, actor_eid, create=False)
    instance_id = _text((scene or {}).get("interface_instance_id"))
    if not instance_id and state is not None and isinstance(getattr(state, "active_connection", None), Mapping):
        instance_id = _text(state.active_connection.get("interface_instance_id"))
    item_id = _key((scene or {}).get("interface_item_id"))
    entry = None
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if inventory is not None and instance_id:
        entry = inventory.find(instance_id=instance_id)
        item_id = _key((entry or {}).get("item_id") or item_id)
    profile = wire_interface_profile_for_item(item_id)
    if not item_id:
        return {}
    return normalize_wire_interface_metadata(dict((entry or {}).get("metadata") or {}), item_id=item_id, profile=profile)


def _start_wire_recovery(sim, actor_eid, *, kind, reason="", scene=None, interface_metadata=None, base_delay=None):
    metadata = dict(interface_metadata or {})
    delay = base_delay if base_delay is not None else _int(metadata.get("recovery_delay"), WIRE_RECOVERY_MIN_TICKS, minimum=0)
    delay = max(WIRE_RECOVERY_MIN_TICKS, _int(delay, WIRE_RECOVERY_MIN_TICKS, minimum=0))
    now = _int(getattr(sim, "tick", 0), 0)
    state = wire_state_for_actor(sim, actor_eid, create=True)
    existing = dict(getattr(state, "last_ejection_state", None) or {})
    existing.update({
        "kind": _key(kind) or _key(existing.get("kind"), "wire_disrupted"),
        "reason": _key(reason) or _key(existing.get("reason"), "wire_disruption"),
        "scene_id": _text((scene or {}).get("scene_id") or existing.get("scene_id")),
        "tick": now,
        "recovery_delay": delay,
        "recovery_until_tick": now + delay,
    })
    state.last_ejection_state = existing
    statuses = sim.ecs.get(StatusEffects).get(actor_eid)
    if statuses is None:
        sim.ecs.add(actor_eid, StatusEffects())
        statuses = sim.ecs.get(StatusEffects).get(actor_eid)
    statuses.add(
        "wire_disrupted",
        delay,
        {
            "move_speed_mult": -0.25,
            "ranged_accuracy_mult": -0.25,
            "melee_accuracy_mult": -0.15,
            "intrusion_action_mult": -0.35,
        },
    )
    sim.emit(Event(
        "wire_recovery_started",
        eid=actor_eid,
        kind=existing["kind"],
        reason=existing["reason"],
        recovery_until_tick=existing["recovery_until_tick"],
        delay=delay,
    ))
    return existing


def _is_hardened_context(prop):
    metadata = _prop_metadata(prop)
    owner_tag = _key((prop or {}).get("owner_tag") or metadata.get("owner_tag"))
    archetype = _key(metadata.get("archetype") or metadata.get("service_archetype"))
    security = _int(metadata.get("security_tier") or metadata.get("security"), 1, minimum=0)
    return bool(owner_tag in _ORG_OWNER_TAGS or owner_tag in _HARDENED_OWNER_TAGS or archetype in _HARDENED_ARCHETYPES or security >= 3)


def raise_wire_security(sim, actor_eid, scene_or_connection=None, *, amount=1, reason="wire_event", prop=None):
    target_prop = wire_network_property(sim, scene_or_connection, prop=prop)
    if not isinstance(target_prop, dict):
        return {"ok": False, "reason": "missing_network"}
    key = wire_network_key(scene_or_connection, target_prop)
    state = _normalize_security_state(sim, target_prop, key, create=True)
    now = _int(getattr(sim, "tick", 0), 0)
    before = _int(state.get("level"), 1, minimum=1, maximum=5)
    locked_until = _int(state.get("locked_until_tick"), 0, minimum=0)
    if before >= 5 and locked_until > now:
        sim.emit(Event(
            "wire_network_locked",
            eid=actor_eid,
            property_id=target_prop.get("id"),
            network_key=key,
            reason=reason,
            locked_until_tick=locked_until,
            remaining=max(0, locked_until - now),
        ))
        return {"ok": False, "reason": "wire_network_locked", "state": dict(state), "forced_disconnect": True}
    increment = max(0, _int(amount, 1, minimum=0))
    requested = before + increment
    after = min(5, requested)
    forced = requested > 5
    if after >= 5:
        locked_until = now + wire_security_reset_delay(target_prop)
        state["locked_until_tick"] = locked_until
        state["post_lock_reset_level"] = 3 if _is_hardened_context(target_prop) else 2
    state["level"] = after
    state["label"] = WIRE_SECURITY_LABELS.get(after, "quiet")
    state["last_event_tick"] = now
    log = {
        "tick": now,
        "reason": _key(reason) or "wire_event",
        "before": before,
        "after": after,
        "actor_eid": actor_eid,
        "scene_id": _text(_scene_or_connection(scene_or_connection).get("scene_id")),
    }
    logs = list(state.get("logs") or [])
    logs.append(log)
    state["logs"] = logs[-16:]
    sim.emit(Event(
        "wire_security_logged",
        eid=actor_eid,
        property_id=target_prop.get("id"),
        property_name=target_prop.get("name", ""),
        network_key=key,
        reason=log["reason"],
        before=before,
        after=after,
        label=state["label"],
        locked_until_tick=state.get("locked_until_tick", 0),
    ))
    if forced:
        sim.emit(Event(
            "wire_network_locked",
            eid=actor_eid,
            property_id=target_prop.get("id"),
            network_key=key,
            reason=log["reason"],
            locked_until_tick=state.get("locked_until_tick", 0),
            remaining=max(0, _int(state.get("locked_until_tick"), 0) - now),
        ))
    return {"ok": True, "reason": None, "state": dict(state), "forced_disconnect": forced}


def _effect_target_property(sim, scene):
    return wire_network_property(sim, scene)


def _find_linked_camera_id(sim, scene):
    linked_id = _text((scene or {}).get("linked_property_id"))
    target_id = _text((scene or {}).get("target_property_id"))
    candidates = []
    for prop_id, prop in getattr(sim, "properties", {}).items():
        if not isinstance(prop, dict):
            continue
        metadata = _prop_metadata(prop)
        role = _key(metadata.get("interaction_role") or metadata.get("fixture_type") or metadata.get("role"))
        if role not in {"camera", "surveillance_camera", "security_camera", "camera_node"}:
            continue
        if linked_id and _text(metadata.get("linked_property_id") or property_linked_property_id(prop)) == linked_id:
            candidates.append(str(prop_id))
    candidates.sort()
    return candidates[0] if candidates else (target_id or linked_id)


def apply_wire_physical_effect(sim, actor_eid, scene, program_key, *, target=None):
    program_key = _key(program_key)
    if program_key not in {"handshake_breaker", "door_latch", "camera_loop", "data_siphon_shell"}:
        return {"ok": False, "reason": "no_physical_effect"}
    if _key((scene or {}).get("target_kind")) == "drone":
        if program_key not in {"camera_loop", "handshake_breaker"}:
            return {"ok": False, "reason": "unsupported_drone_wire_effect"}
        from game.wire_drone_bridge import apply_drone_wire_camera_loop, apply_drone_wire_handshake_breaker

        effect = (
            apply_drone_wire_handshake_breaker(sim, actor_eid, scene)
            if program_key == "handshake_breaker"
            else apply_drone_wire_camera_loop(sim, actor_eid, scene)
        )
        if effect.get("ok"):
            sim.emit(Event(
                "wire_physical_effect_applied",
                eid=actor_eid,
                program_key=program_key,
                target_id=effect.get("target_id"),
                target_entity_id=effect.get("target_id"),
                scene_id=(scene or {}).get("scene_id"),
                feedback=effect.get("feedback"),
            ))
        return effect
    if _key((scene or {}).get("target_kind")) == "vehicle":
        return {"ok": False, "reason": "unsupported_vehicle_wire_effect"}
    if program_key == "handshake_breaker":
        return {"ok": False, "reason": "requires_drone_radio_target"}
    target_prop = _effect_target_property(sim, scene)
    if not isinstance(target_prop, dict):
        return {"ok": False, "reason": "missing_physical_target"}
    now = _int(getattr(sim, "tick", 0), 0)
    if program_key == "door_latch":
        mode = "relay_latch"
        metadata = _prop_metadata(target_prop)
        controller_mode = _key(metadata.get("controller_credential_mode") or metadata.get("credential_mode"))
        if controller_mode == "badge":
            mode = "badge_spoof"
        elif controller_mode == "biometric":
            mode = "biometric_jam"
        applied = apply_controller_intrusion(
            target_prop,
            mode=mode,
            tick=now,
            duration=90,
            actor_eid=actor_eid if mode == "badge_spoof" else None,
            source_item_id=_text((scene or {}).get("interface_item_id")),
            method="wire_door_latch",
        )
        if not applied:
            return {"ok": False, "reason": "door_latch_failed"}
        metadata = _prop_metadata(target_prop, create=True)
        metadata["wire_last_physical_effect"] = {"program": program_key, "tick": now, "mode": mode}
        raise_result = raise_wire_security(sim, actor_eid, scene, amount=1, reason="door_latch")
        feedback = "Door latch opens a short controller window."
        effect_target = target_prop.get("id")
    elif program_key == "camera_loop":
        camera_id = _find_linked_camera_id(sim, scene)
        if not camera_id:
            return {"ok": False, "reason": "no_camera_target"}
        disabled_until = now + 120
        if not isinstance(getattr(sim, "camera_disabled", None), dict):
            sim.camera_disabled = {}
        sim.camera_disabled[str(camera_id)] = disabled_until
        raise_result = raise_wire_security(sim, actor_eid, scene, amount=1, reason="camera_loop")
        sim.emit(Event(
            "camera_disabled",
            eid=actor_eid,
            property_id=str(camera_id),
            disabled_until=disabled_until,
            source_kind="wire_camera_loop",
        ))
        feedback = "Camera loop blinds one linked feed for a short window."
        effect_target = str(camera_id)
    else:
        metadata = _prop_metadata(target_prop, create=True)
        dirty = list(metadata.get("wire_records_dirty") or [])
        dirty.append({
            "tick": now,
            "actor_eid": actor_eid,
            "scene_id": _text((scene or {}).get("scene_id")),
            "program": program_key,
        })
        metadata["wire_records_dirty"] = dirty[-12:]
        raise_result = raise_wire_security(sim, actor_eid, scene, amount=1, reason="data_siphon_shell")
        feedback = "Data siphon shell dirties the records surface."
        effect_target = target_prop.get("id")
    sim.emit(Event(
        "wire_physical_effect_applied",
        eid=actor_eid,
        program_key=program_key,
        target_id=effect_target,
        property_id=target_prop.get("id"),
        scene_id=(scene or {}).get("scene_id"),
        feedback=feedback,
    ))
    return {
        "ok": True,
        "reason": None,
        "feedback": feedback,
        "target_id": effect_target,
        "forced_disconnect": bool(raise_result.get("forced_disconnect")),
    }


def wire_physical_effect_preflight(sim, scene, program_key, *, actor_eid=None):
    program_key = _key(program_key)
    if program_key not in {"handshake_breaker", "door_latch", "camera_loop", "data_siphon_shell"}:
        return {"ok": True, "reason": None}
    if _key((scene or {}).get("target_kind")) == "drone":
        if program_key not in {"camera_loop", "handshake_breaker"}:
            return {"ok": False, "reason": "unsupported_drone_wire_effect"}
        from game.wire_drone_bridge import drone_wire_camera_loop_preflight, drone_wire_handshake_breaker_preflight

        if program_key == "handshake_breaker":
            return drone_wire_handshake_breaker_preflight(sim, actor_eid, scene)
        return drone_wire_camera_loop_preflight(sim, scene)
    if _key((scene or {}).get("target_kind")) == "vehicle":
        return {"ok": False, "reason": "unsupported_vehicle_wire_effect"}
    if program_key == "handshake_breaker":
        return {"ok": False, "reason": "requires_drone_radio_target"}
    target_prop = _effect_target_property(sim, scene)
    if not isinstance(target_prop, dict):
        return {"ok": False, "reason": "missing_physical_target"}
    if program_key == "camera_loop" and not _find_linked_camera_id(sim, scene):
        return {"ok": False, "reason": "no_camera_target"}
    return {"ok": True, "reason": None, "property_id": target_prop.get("id")}


def _actor_position_tuple(sim, actor_eid, fallback_prop=None):
    pos = sim.ecs.get(Position).get(actor_eid)
    if pos is not None:
        return int(pos.x), int(pos.y), int(pos.z)
    if isinstance(fallback_prop, Mapping):
        return (
            _int(fallback_prop.get("x"), 0),
            _int(fallback_prop.get("y"), 0),
            _int(fallback_prop.get("z"), 0),
        )
    return None, None, 0


def promote_wire_security_report(sim, actor_eid, scene, *, reason="trace", confidence=0.82):
    prop = wire_network_property(sim, scene)
    if not isinstance(prop, dict):
        return None
    owner_eid = prop.get("owner_eid")
    if owner_eid is None:
        return None
    x, y, z = _actor_position_tuple(sim, actor_eid, prop)
    incident, _merged = create_or_merge_incident(
        sim,
        kind="wire_intrusion",
        x=x,
        y=y,
        z=z,
        tick=getattr(sim, "tick", 0),
        severity=42,
        primary_actor_eid=actor_eid,
        owner_eid=owner_eid,
        property_id=_text(prop.get("id")),
        property_name=_text(prop.get("name"), "wire target"),
        merge_subject=f"wire:{wire_network_key(scene, prop)}:{actor_eid}",
        source_event="wire_security_report",
        official_reportable=True,
        note="Technical security report from traced wire intrusion.",
        tags=("wire", "technical_security_report", reason),
    )
    try:
        owner = int(owner_eid)
    except (TypeError, ValueError):
        return incident
    knowledge = sim.ecs.get(IncidentKnowledge).get(owner)
    if knowledge is None:
        sim.ecs.add(owner, IncidentKnowledge())
        knowledge = sim.ecs.get(IncidentKnowledge).get(owner)
    record = knowledge.remember(
        incident.get("id"),
        learned_tick=getattr(sim, "tick", 0),
        source_kind="wire_security_report",
        source_eid=None,
        confidence=confidence,
        firsthand=False,
        propagation_depth=0,
        urgency=0.32 if _is_hardened_context(prop) else 0.18,
        social_interest=0.1,
        category="official",
        kind=incident.get("kind"),
        tags=incident.get("tags", ()),
        severity=int(incident.get("severity", 0) or 0),
        x=incident.get("x"),
        y=incident.get("y"),
        z=incident.get("z"),
    )
    sim.emit(Event(
        "wire_security_reported",
        eid=actor_eid,
        owner_eid=owner,
        incident_id=incident.get("id"),
        property_id=prop.get("id"),
        reason=reason,
        source_kind="wire_security_report",
        observation_channel="technical_security_report",
        firsthand=False,
        confidence=confidence,
    ))
    return record


def eligible_drone_wakeup_sources(sim, actor_eid):
    rows = []
    for drone_eid, drone_state in sim.ecs.get(DroneState).items():
        if not drone_state_controlled_by_actor(drone_state, actor_eid):
            continue
        if not (
            drone_state_has_capability(drone_state, "camera")
            or drone_state_has_capability(drone_state, "sensor")
            or drone_state_has_capability(drone_state, "thermal")
            or drone_state_has_capability(drone_state, "radar")
        ):
            continue
        if not (drone_state_has_capability(drone_state, "radio") or drone_state_has_capability(drone_state, "comms")):
            continue
        battery = getattr(drone_state, "battery", None)
        if isinstance(battery, Mapping):
            charge = _int((battery or {}).get("charge"), _int((battery or {}).get("charge_max"), 0), minimum=0)
        else:
            charge = _int(getattr(drone_state, "battery_charge", 0), 0, minimum=0)
        if charge <= 0:
            continue
        procedure = _key(getattr(drone_state, "procedure_key", "") or getattr(drone_state, "program_status", ""))
        last_command = _key(getattr(drone_state, "last_command", ""))
        if procedure not in {"watch", "guard_zone", "protect_operator", "protect", "report", "follow"} and last_command not in {"follow", "hold", "return"}:
            continue
        rows.append({"drone_eid": drone_eid, "procedure_key": procedure, "last_command": last_command})
    rows.sort(key=lambda row: int(row["drone_eid"]))
    return tuple(rows)


def wake_wired_actor(sim, actor_eid, *, source_kind, source_eid=None, reason="wake", damage=0):
    state = wire_state_for_actor(sim, actor_eid, create=False)
    scene = getattr(state, "active_scene", None) if state is not None else None
    if not isinstance(scene, Mapping):
        return {"ok": False, "reason": "not_wired"}
    source = _key(source_kind)
    if source == "drone":
        eligible = eligible_drone_wakeup_sources(sim, actor_eid)
        if source_eid is not None and not any(int(row["drone_eid"]) == int(source_eid) for row in eligible):
            return {"ok": False, "reason": "drone_ineligible"}
        if not eligible:
            return {"ok": False, "reason": "no_eligible_drone"}
        if source_eid is None:
            source_eid = eligible[0]["drone_eid"]
        kind = "drone_watch_wakeup"
    elif source == "bodyguard":
        kind = "bodyguard_physical_wakeup"
        damage = max(1, _int(damage, 1, minimum=0))
    else:
        return {"ok": False, "reason": "unknown_wakeup_source"}
    state.last_ejection_state = {
        "kind": kind,
        "reason": _key(reason) or "wake",
        "scene_id": scene.get("scene_id"),
        "source_kind": source,
        "source_eid": source_eid,
        "tick": _int(getattr(sim, "tick", 0), 0),
    }
    from game.wire_scene import close_wire_scene

    close_wire_scene(sim, actor_eid, reason=kind, disconnect=True)
    if damage:
        vitality = sim.ecs.get(Vitality).get(actor_eid)
        if vitality is not None:
            vitality.hp = max(0, int(vitality.hp) - int(damage))
        sim.emit(Event(
            "entity_damaged",
            target_eid=actor_eid,
            source_eid=source_eid,
            damage=damage,
            hp=getattr(vitality, "hp", None) if vitality is not None else None,
            damage_kind="wire_wakeup",
            wire_interrupt_extra=True,
        ))
        _start_wire_recovery(sim, actor_eid, kind=kind, reason=reason, scene=scene, base_delay=WIRE_RECOVERY_MIN_TICKS)
    sim.emit(Event(
        "wire_player_woke",
        eid=actor_eid,
        source_kind=source,
        source_eid=source_eid,
        reason=reason,
        damage=damage,
    ))
    return {"ok": True, "reason": None, "source_kind": source, "source_eid": source_eid, "damage": damage}


class WireConsequenceSystem(System):
    def __init__(self, sim, player_eid=None):
        super().__init__(sim)
        self.player_eid = player_eid
        sim.events.subscribe("wire_forced_eject", self.on_wire_forced_eject)
        sim.events.subscribe("wire_scene_panic_exit", self.on_wire_scene_panic_exit)
        sim.events.subscribe("wire_panic_eject", self.on_wire_panic_eject)
        sim.events.subscribe("entity_damaged", self.on_entity_damaged)
        sim.events.subscribe("wire_wakeup_request", self.on_wire_wakeup_request)

    def _scene_for_actor(self, actor_eid):
        state = wire_state_for_actor(self.sim, actor_eid, create=False)
        scene = getattr(state, "active_scene", None) if state is not None else None
        return dict(scene) if isinstance(scene, Mapping) else None

    def on_wire_forced_eject(self, event):
        actor_eid = event.data.get("eid")
        scene = self._scene_for_actor(actor_eid)
        if not scene:
            return
        reason = _key(event.data.get("reason"), "trace")
        if reason == "trace":
            raise_wire_security(self.sim, actor_eid, scene, amount=2, reason="trace")
            promote_wire_security_report(self.sim, actor_eid, scene, reason="trace", confidence=0.86)
        else:
            raise_wire_security(self.sim, actor_eid, scene, amount=1, reason=f"{reason}_eject")
        metadata = _interface_metadata_for_scene(self.sim, actor_eid, scene)
        _start_wire_recovery(self.sim, actor_eid, kind="forced", reason=reason, scene=scene, interface_metadata=metadata)

    def on_wire_scene_panic_exit(self, event):
        actor_eid = event.data.get("eid")
        scene = self._scene_for_actor(actor_eid)
        metadata = _interface_metadata_for_scene(self.sim, actor_eid, scene)
        _start_wire_recovery(self.sim, actor_eid, kind="hard_panic", reason="manual", scene=scene, interface_metadata=metadata)

    def on_wire_panic_eject(self, event):
        actor_eid = event.data.get("eid")
        scene = self._scene_for_actor(actor_eid)
        metadata = _interface_metadata_for_scene(self.sim, actor_eid, scene)
        _start_wire_recovery(self.sim, actor_eid, kind="program", reason="panic_eject", scene=scene, interface_metadata=metadata, base_delay=WIRE_RECOVERY_MIN_TICKS)

    def on_entity_damaged(self, event):
        actor_eid = event.data.get("target_eid")
        if actor_eid is None:
            actor_eid = event.data.get("eid")
        if self.player_eid is not None and actor_eid != self.player_eid:
            return
        if bool(event.data.get("wire_interrupt_extra")):
            return
        scene = self._scene_for_actor(actor_eid)
        if not scene:
            return
        damage = _int(event.data.get("damage") or event.data.get("amount"), 0, minimum=0)
        if damage <= 0:
            return
        metadata = _interface_metadata_for_scene(self.sim, actor_eid, scene)
        multiplier = 3 if not bool(metadata.get("safe_yank", True)) and _int(metadata.get("shock_risk"), 0, minimum=0) >= 2 else 2
        extra = damage * (multiplier - 1)
        state = wire_state_for_actor(self.sim, actor_eid, create=True)
        state.last_ejection_state = {
            "kind": "body_damage_interrupt",
            "reason": "physical_damage",
            "scene_id": scene.get("scene_id"),
            "tick": _int(getattr(self.sim, "tick", 0), 0),
            "base_damage": damage,
            "extra_damage": extra,
            "damage_multiplier": multiplier,
        }
        from game.wire_scene import close_wire_scene

        close_wire_scene(self.sim, actor_eid, reason="body_damage_interrupt", disconnect=True)
        vitality = self.sim.ecs.get(Vitality).get(actor_eid)
        before = getattr(vitality, "hp", None) if vitality is not None else None
        after = None
        if vitality is not None and extra > 0:
            vitality.hp = max(0, int(vitality.hp) - int(extra))
            after = int(vitality.hp)
            if vitality.hp <= 0 and not getattr(vitality, "downed", False):
                vitality.downed = True
                vitality.downed_tick = _int(getattr(self.sim, "tick", 0), 0)
            self.sim.emit(Event(
                "entity_damaged",
                eid=actor_eid,
                target_eid=actor_eid,
                damage=extra,
                hp=after,
                damage_kind="wire_disruption",
                wire_interrupt_extra=True,
            ))
        recovery = _start_wire_recovery(
            self.sim,
            actor_eid,
            kind="body_damage_interrupt",
            reason="physical_damage",
            scene=scene,
            interface_metadata=metadata,
        )
        self.sim.emit(Event(
            "wire_body_damage_interrupt",
            eid=actor_eid,
            scene_id=scene.get("scene_id"),
            base_damage=damage,
            extra_damage=extra,
            damage_multiplier=multiplier,
            hp_before=before,
            hp_after=after,
            recovery_until_tick=recovery.get("recovery_until_tick"),
        ))

    def on_wire_wakeup_request(self, event):
        actor_eid = event.data.get("eid") or self.player_eid
        if actor_eid is None:
            return
        wake_wired_actor(
            self.sim,
            actor_eid,
            source_kind=event.data.get("source_kind"),
            source_eid=event.data.get("source_eid"),
            reason=event.data.get("reason", "wake"),
            damage=event.data.get("damage", 0),
        )
