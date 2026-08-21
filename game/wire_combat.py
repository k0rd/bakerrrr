"""Executable WireScene programs, ICE, trace, and corruption helpers."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from hashlib import blake2b

from engine.events import Event
from game.components import Inventory
from game.items import ITEM_CATALOG, item_display_name
from game.wire_kit import refresh_wire_state_interface_capacity, wire_state_for_actor
from game.wire_runtime import (
    normalize_wire_entry_metadata,
    normalize_wire_interface_metadata,
    wire_interface_profile_for_item,
    wire_profile_for_item,
)
from game.wire_security_runtime import (
    normalize_wire_session_security,
    resolve_wire_action_security,
    wire_acquire_avatar,
    wire_alert_rank,
    wire_reveal_all_security_edges,
    wire_session_alert,
)
from game.wire_visuals import wire_visual_for_kind


WIRE_COMBAT_SCHEMA_VERSION = 2

PROGRAM_ITEM_ID_BY_KEY = {
    "talk": "wire_talk_program",
    "route_probe": "wire_route_probe_program",
    "handshake_breaker": "wire_handshake_breaker_program",
    "door_latch": "wire_door_latch_program",
    "camera_loop": "wire_camera_loop_program",
    "data_siphon_shell": "wire_data_siphon_shell_program",
    "spike": "wire_spike_program",
    "ice_cutter": "wire_ice_cutter_program",
    "trace_scrubber": "wire_trace_scrubber_program",
    "signal_cloak": "wire_signal_cloak_program",
    "proxy_route": "wire_proxy_route_program",
    "tunnel_route": "wire_tunnel_route_program",
    "panic_eject": "wire_panic_eject_program",
    "checksum_ward": "wire_checksum_ward_program",
    "sacrificial_shell": "wire_sacrificial_shell_program",
}

PROGRAM_SPECS = {
    "talk": {"target": "user", "label": "Talk", "range": 4, "mode": "active"},
    "route_probe": {"target": "scene", "label": "Route Probe", "range": 0, "mode": "active"},
    "handshake_breaker": {"target": "node", "label": "Handshake Breaker", "node_kinds": {"controller", "sensor_relay"}, "mode": "active"},
    "door_latch": {"target": "node", "label": "Door Latch", "node_kinds": {"door_alarm_relay", "controller"}, "mode": "active"},
    "camera_loop": {"target": "node", "label": "Camera Loop", "node_kinds": {"controller", "diagnostic", "sensor_relay"}, "mode": "active"},
    "data_siphon_shell": {"target": "node", "label": "Decryptor Shell", "node_kinds": {"records"}, "mode": "active"},
    "spike": {"target": "ice", "label": "Spike", "range": 10, "damage": 3, "mode": "active"},
    "ice_cutter": {"target": "ice", "label": "ICE Cutter", "range": 8, "damage": 5, "mode": "active"},
    "trace_scrubber": {"target": "self", "label": "Trace Scrubber", "trace_delta": -5, "mode": "active"},
    "signal_cloak": {"target": "self", "label": "Signal Cloak", "effect_turns": 4, "mode": "passive"},
    "proxy_route": {"target": "self", "label": "Proxy Route", "effect_turns": 999, "trace_absorb": 6, "mode": "passive"},
    "tunnel_route": {"target": "self", "label": "Tunnel Route", "effect_turns": 6, "trace_reduction": 1, "mode": "passive"},
    "panic_eject": {"target": "self", "label": "Panic Eject", "mode": "active"},
    "checksum_ward": {"target": "self", "label": "Checksum Ward", "mode": "passive"},
    "sacrificial_shell": {"target": "self", "label": "Sacrificial Shell", "mode": "passive"},
}

ICE_SPECS = {
    "camera_watchdog": {"label": "Camera Watchdog", "hp": 4, "trace": 2, "visual": "ice_camera_watchdog", "mobile": True},
    "door_arbiter": {"label": "Door Arbiter", "hp": 7, "buffer": 1, "visual": "ice_door_arbiter", "blocks_route": True},
    "trace_sentinel": {"label": "Trace Sentinel", "hp": 5, "trace": 3, "visual": "ice_trace_sentinel"},
    "compliance_daemon": {"label": "Compliance Daemon", "hp": 6, "trace": 1, "visual": "ice_compliance_daemon"},
    "quarantine_gate": {"label": "Quarantine Gate", "hp": 8, "trace": 1, "visual": "ice_quarantine_gate", "blocks_route": True},
    "corruptor": {"label": "Corruptor", "hp": 6, "buffer": 1, "visual": "ice_corruptor", "mobile": True, "blocks_route": True},
}

OFFENSIVE_PROGRAMS = {"handshake_breaker", "door_latch", "camera_loop", "data_siphon_shell", "spike", "ice_cutter"}
PASSIVE_EFFECT_BY_PROGRAM = {
    "signal_cloak": "signal_cloak",
    "proxy_route": "proxy_route",
    "tunnel_route": "tunnel_route",
    "checksum_ward": "checksum_ward",
    "sacrificial_shell": "sacrificial_shell",
}

PROGRAM_VISUAL_BY_KEY = {
    key: f"program_{key}"
    for key in PROGRAM_SPECS
}
PROGRAM_VISUAL_BY_KEY["data_siphon_shell"] = "program_data_siphon"


def _clean_text(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _clean_key(value, default=""):
    return _clean_text(value, default).lower()


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


def _hash_int(*parts):
    data = ":".join(str(part or "") for part in parts).encode("utf-8", errors="replace")
    return int.from_bytes(blake2b(data, digest_size=8).digest(), "big")


def _program_profile(item_id, *, item_catalog=None):
    return wire_profile_for_item(item_id, item_catalog=item_catalog or ITEM_CATALOG)


def _program_key_for_item(item_id, *, item_catalog=None):
    return _clean_key(_program_profile(item_id, item_catalog=item_catalog).get("program_key"))


def _is_program_entry(entry, *, item_catalog=None):
    if not isinstance(entry, Mapping):
        return False
    profile = _program_profile(entry.get("item_id"), item_catalog=item_catalog)
    return profile.get("kind") == "program" and bool(profile.get("program_key"))


def _normalized_program_entry(entry, *, item_catalog=None, storage_status=None):
    if not isinstance(entry, Mapping):
        return None
    item_id = _clean_key(entry.get("item_id"))
    if not item_id:
        return None
    profile = _program_profile(item_id, item_catalog=item_catalog)
    if profile.get("kind") != "program":
        return None
    metadata = normalize_wire_entry_metadata(
        dict(entry.get("metadata") or {}),
        item_id=item_id,
        profile=profile,
    )
    if storage_status:
        metadata["storage_status"] = str(storage_status)
    return {
        "slot": _int(entry.get("slot"), 0, minimum=0),
        "instance_id": _clean_text(entry.get("instance_id")),
        "item_id": item_id,
        "quantity": max(1, _int(entry.get("quantity"), 1)),
        "owner_eid": entry.get("owner_eid"),
        "owner_tag": entry.get("owner_tag"),
        "metadata": metadata,
    }


def _interface_metadata(sim, actor_eid, scene=None, *, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    state = wire_state_for_actor(sim, actor_eid, create=False)
    instance_id = _clean_text((scene or {}).get("interface_instance_id"))
    if not instance_id and state is not None:
        active = getattr(state, "active_connection", None)
        if isinstance(active, Mapping):
            instance_id = _clean_text(active.get("interface_instance_id"))
    entry = None
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if inventory is not None and instance_id:
        entry = inventory.find(instance_id=instance_id)
    item_id = _clean_key((entry or {}).get("item_id") or (scene or {}).get("interface_item_id"))
    profile = wire_interface_profile_for_item(item_id, item_catalog=item_catalog)
    metadata = normalize_wire_interface_metadata(
        dict((entry or {}).get("metadata") or {}),
        item_id=item_id,
        profile=profile,
    ) if item_id else {}
    return item_id, metadata


def _memory_speed(metadata):
    slots = _int(metadata.get("program_slots"), 0, minimum=0)
    buffer_size = _int(metadata.get("buffer_size"), 0, minimum=0)
    noise = _int(metadata.get("noise_floor"), 0, minimum=0)
    default = max(1, slots + buffer_size // 4 - noise // 2)
    return _int(metadata.get("memory_speed"), default, minimum=0)


def _ram_cost(entry, *, item_catalog=None):
    profile = _program_profile((entry or {}).get("item_id"), item_catalog=item_catalog)
    return _int(profile.get("ram_cost"), 1, minimum=1)


def wire_ram_used_points(state, *, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    return sum(
        _ram_cost(entry, item_catalog=item_catalog)
        for entry in getattr(state, "ram_slots", ()) or ()
        if isinstance(entry, Mapping)
    )


def normalize_wire_ram_slots(state, *, item_catalog=None):
    if state is None:
        return []
    item_catalog = item_catalog or ITEM_CATALOG
    slots = []
    for entry in getattr(state, "ram_slots", ()) or ():
        clean = _normalized_program_entry(entry, item_catalog=item_catalog, storage_status="ram")
        if clean is not None and clean.get("instance_id"):
            clean["slot"] = len(slots)
            slots.append(clean)
    state.ram_slots = slots
    return slots


def _find_kit_entry(state, instance_id):
    needle = _clean_text(instance_id)
    if not needle:
        return None
    for entry in getattr(state, "kit_entries", ()) or ():
        if isinstance(entry, Mapping) and _clean_text(entry.get("instance_id")) == needle:
            return dict(entry)
    return None


def _update_kit_metadata(state, instance_id, metadata, *, item_catalog=None):
    if state is None:
        return False
    needle = _clean_text(instance_id)
    item_catalog = item_catalog or ITEM_CATALOG
    entries = []
    changed = False
    for entry in getattr(state, "kit_entries", ()) or ():
        row = dict(entry)
        if _clean_text(row.get("instance_id")) == needle:
            item_id = _clean_key(row.get("item_id"))
            normalized = normalize_wire_entry_metadata(
                dict(metadata or {}),
                item_id=item_id,
                profile=_program_profile(item_id, item_catalog=item_catalog),
            )
            normalized["storage_status"] = "wire_kit"
            row["metadata"] = normalized
            changed = True
        entries.append(row)
    state.kit_entries = entries
    return changed


def _program_name(entry, *, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    metadata = dict((entry or {}).get("metadata") or {})
    return item_display_name((entry or {}).get("item_id"), metadata=metadata, item_catalog=item_catalog)


def _node_at(scene, x, y):
    for node in scene.get("nodes", ()) or ():
        if not isinstance(node, Mapping):
            continue
        if _int(node.get("x"), -999) == int(x) and _int(node.get("y"), -999) == int(y):
            return dict(node)
    return None


def _current_node(scene):
    avatar = scene.get("avatar") if isinstance(scene.get("avatar"), Mapping) else {}
    return _node_at(scene, _int(avatar.get("x"), 0), _int(avatar.get("y"), 0))


def _entity_label(entity):
    kind = _clean_key((entity or {}).get("kind"))
    return _clean_text((entity or {}).get("label"), ICE_SPECS.get(kind, {}).get("label", kind.replace("_", " ") or "ICE"))


def _live_ice_entities(scene):
    return [
        dict(entity)
        for entity in scene.get("wire_entities", ()) or ()
        if isinstance(entity, Mapping)
        and _clean_key(entity.get("source")) == "ice"
        and not bool(entity.get("destroyed"))
        and _int(entity.get("hp"), 0) > 0
    ]


def _set_entity(scene, updated):
    entity_id = _clean_text((updated or {}).get("entity_id"))
    entities = []
    replaced = False
    for entity in scene.get("wire_entities", ()) or ():
        row = dict(entity)
        if entity_id and _clean_text(row.get("entity_id")) == entity_id:
            row.update(dict(updated))
            replaced = True
        entities.append(row)
    if not replaced and entity_id:
        entities.append(dict(updated))
    scene["wire_entities"] = entities


def _scene_security(scene):
    return _int((scene or {}).get("security_tier"), 1, minimum=0)


def _entity_at_node(nodes, node_kind):
    for node in nodes:
        if isinstance(node, Mapping) and _clean_key(node.get("kind")) == _clean_key(node_kind):
            return int(node.get("x", 0)), int(node.get("y", 0))
    return 1, 1


def _entity_at_first_node(nodes, *node_kinds):
    wanted = tuple(_clean_key(kind) for kind in node_kinds if _clean_key(kind))
    for kind in wanted:
        for node in nodes:
            if isinstance(node, Mapping) and _clean_key(node.get("kind")) == kind:
                return int(node.get("x", 0)), int(node.get("y", 0))
    return 1, 1


def _ice_entity(scene, kind, entity_id, x, y, *, traits=()):
    spec = ICE_SPECS[kind]
    visual = wire_visual_for_kind(spec["visual"])
    return {
        "entity_id": str(entity_id),
        "source": "ice",
        "kind": kind,
        "label": spec["label"],
        "x": int(x),
        "y": int(y),
        "hp": int(spec["hp"]),
        "hp_max": int(spec["hp"]),
        "cooldown": 0,
        "traits": tuple(dict.fromkeys(str(trait).strip().lower() for trait in traits if str(trait).strip())),
        "visual_kind": spec["visual"],
        "glyph": visual["glyph"],
        "color": visual["color"],
        "semantic_id": visual["semantic_id"],
        "installed": True,
        "state": "dormant",
        "last_known_target": None,
        "revealed": False,
    }


def _initial_ice_entities(scene, *, security=1):
    nodes = list(scene.get("nodes", ()) or ())
    target_class = _clean_key(scene.get("target_class"))
    target_kind = _clean_key(scene.get("target_kind"))
    scene_id = _clean_text(scene.get("scene_id"))
    security = _int(security, 1, minimum=0)
    rows = []
    dx, dy = _entity_at_node(nodes, "diagnostic")
    rows.append(_ice_entity(scene, "camera_watchdog", "ice-watchdog-1", dx, dy))
    if target_class == "access_panel":
        rx, ry = _entity_at_node(nodes, "door_alarm_relay")
        rows.append(_ice_entity(scene, "door_arbiter", "ice-arbiter-1", rx, ry))
    else:
        preferred_anchor = "sensor_relay" if target_kind == "drone" else "vehicle_lock_bus" if target_kind == "vehicle" else "service_index"
        sx, sy = _entity_at_first_node(nodes, preferred_anchor, "controller", "diagnostic")
        rows.append(_ice_entity(scene, "compliance_daemon", "ice-daemon-1", sx, sy))
    if security >= 2:
        tx, ty = _entity_at_node(nodes, "records")
        rows.append(_ice_entity(scene, "trace_sentinel", "ice-sentinel-1", tx, ty))
    if security >= 3:
        cx, cy = _entity_at_node(nodes, "controller")
        traits = ("quarantine_anchor",) if security >= 4 else ()
        rows.append(_ice_entity(scene, "quarantine_gate", "ice-quarantine-1", cx, cy, traits=traits))
    if security >= 4:
        rx, ry = _entity_at_node(nodes, "records")
        traits = ("corruptor_precision", "blackbox_auditor")
        if _hash_int(scene_id, "elite") % 2 == 0:
            traits = traits + ("memory_speed_trace",)
        else:
            traits = traits + ("ram_reset_attack",)
        rows.append(_ice_entity(scene, "corruptor", "ice-corruptor-1", rx, ry, traits=traits))
    return rows[:5]


def initialize_wire_combat_scene(scene, *, interface_metadata=None, security=1, persistent_security=None):
    if not isinstance(scene, dict):
        return scene
    interface_metadata = dict(interface_metadata or {})
    security = _int(security or scene.get("security_tier"), 1, minimum=0)
    trace_resistance = _int(interface_metadata.get("trace_resistance"), 0, minimum=0)
    buffer_max = max(1, _int(interface_metadata.get("buffer_size"), 4, minimum=1))
    trace_noise_floor = max(0, _int(interface_metadata.get("noise_floor"), 0, minimum=0) + max(0, security - 1))
    scene.setdefault("wire_combat_schema_version", WIRE_COMBAT_SCHEMA_VERSION)
    scene["security_tier"] = security
    scene.setdefault("buffer_max", buffer_max)
    scene.setdefault("buffer_current", _int(scene.get("buffer_current"), scene["buffer_max"], minimum=0))
    scene.setdefault("trace_limit", 12 + trace_resistance * 4)
    scene.setdefault("trace_noise_floor", trace_noise_floor)
    scene.setdefault("trace_current", 0)
    if "trace_awake" not in scene:
        scene["trace_awake"] = _int(scene.get("trace_current"), 0, minimum=0) > 0
    scene.setdefault("trace_awake_reason", "")
    scene.setdefault("trace_alert_level", "quiet")
    scene.setdefault("active_effects", [])
    scene.setdefault("program_cooldowns", {})
    scene.setdefault("last_program_result", {})
    scene.setdefault("combat_log", [])
    scene.setdefault("clean_exit_blocked", False)
    scene.setdefault("ejection_state", {})
    scene.setdefault("wire_turn_index", 0)
    scene.setdefault("last_hostile_program_instance_id", "")
    scene.setdefault("wire_action_frame", 0)
    scene.setdefault("wire_action_cause", "")
    scene.setdefault("wire_action_effects", [])
    scene.setdefault("last_wire_action", "")
    scene["interface_memory_speed"] = _memory_speed(interface_metadata)
    normalize_wire_session_security(
        scene,
        interface_metadata=interface_metadata,
        persistent_security=persistent_security,
    )
    if not scene.get("wire_entities_initialized"):
        scene["wire_entities"] = _initial_ice_entities(scene, security=security)
        scene["wire_entities_initialized"] = True
    else:
        scene.setdefault("wire_entities", [])
    warning_rating = _int(scene.get("interface_warning_rating"), 1, minimum=0, maximum=5)
    normalized_entities = []
    for raw in scene.get("wire_entities", ()) or ():
        if not isinstance(raw, Mapping):
            continue
        entity = dict(raw)
        entity.setdefault("installed", True)
        entity.setdefault("state", "dormant")
        entity.setdefault("last_known_target", None)
        if warning_rating >= 4:
            entity["revealed"] = True
        normalized_entities.append(entity)
    scene["wire_entities"] = normalized_entities
    _sync_ice_states(scene)
    _refresh_clean_exit_block(scene)
    _refresh_trace_alert(scene)
    return scene


def ensure_wire_combat_state(sim, actor_eid, *, item_catalog=None):
    state = wire_state_for_actor(sim, actor_eid, create=False)
    if state is None or not isinstance(getattr(state, "active_scene", None), Mapping):
        return None
    scene = dict(state.active_scene)
    _item_id, interface_metadata = _interface_metadata(sim, actor_eid, scene, item_catalog=item_catalog)
    if not scene.get("security_edges") and scene.get("nodes") and scene.get("edges"):
        from game.wire_scene import _apply_wire_security_topology

        scene["security_edges"] = _apply_wire_security_topology(
            scene["nodes"],
            [tuple(edge) for edge in scene.get("edges", ()) or () if isinstance(edge, (list, tuple)) and len(edge) >= 2],
            security=_scene_security(scene),
            network_family=scene.get("network_family", "local_controller"),
            warning_rating=_int(interface_metadata.get("warning_rating"), 1, minimum=0, maximum=5),
        )
        scene["schema_version"] = max(2, _int(scene.get("schema_version"), 1, minimum=1))
    if not isinstance(scene.get("objective"), Mapping):
        from game.wire_consequences import wire_network_property
        from game.wire_scene import _wire_objective_summary

        scene["objective"] = _wire_objective_summary(scene, wire_network_property(sim, scene) or {})
    program_slots = _int(interface_metadata.get("program_slots"), getattr(state, "program_slots", 2), minimum=0)
    state.program_slots = program_slots
    normalize_wire_ram_slots(state, item_catalog=item_catalog)
    if len(getattr(state, "ram_slots", ()) or ()) > 0 and wire_ram_used_points(state, item_catalog=item_catalog) > program_slots:
        while state.ram_slots and wire_ram_used_points(state, item_catalog=item_catalog) > program_slots:
            state.ram_slots.pop()
    from game.wire_consequences import wire_security_state

    persistent_security = wire_security_state(sim, scene, create=False)
    initialize_wire_combat_scene(
        scene,
        interface_metadata=interface_metadata,
        security=scene.get("security_tier", 1),
        persistent_security=persistent_security,
    )
    state.active_scene = scene
    return scene


def reveal_wire_ice(scene, entity_id, *, state=None):
    """Reveal one installed countermeasure after contact or a successful scan."""

    if not isinstance(scene, dict):
        return None
    wanted = _clean_text(entity_id)
    for entity in _live_ice_entities(scene):
        if _clean_text(entity.get("entity_id")) != wanted:
            continue
        entity["revealed"] = True
        if state:
            entity["state"] = _clean_key(state)
        _set_entity(scene, entity)
        return dict(entity)
    return None


def _ice_state_active(entity):
    return _clean_key((entity or {}).get("state")) not in {"", "dormant", "disabled"}


def _active_ice_entities(scene):
    return [entity for entity in _live_ice_entities(scene) if _ice_state_active(entity)]


def _sync_ice_states(scene):
    """Turn installed ICE roles on from local alert state, not from trace."""

    rank = wire_alert_rank(scene)
    known_avatar = wire_session_alert(scene).get("known_avatar")
    hostile = bool(_clean_text(scene.get("last_hostile_program_instance_id")))
    for entity in _live_ice_entities(scene):
        kind = _clean_key(entity.get("kind"))
        if kind == "camera_watchdog":
            state = "pursuing" if rank >= 1 and known_avatar else "investigating" if rank >= 1 else "watching"
        elif kind == "door_arbiter":
            state = "engaged" if rank >= 1 and known_avatar else "watching"
        elif kind == "trace_sentinel":
            state = "tracing" if rank >= 2 else "dormant"
        elif kind == "compliance_daemon":
            state = "supporting" if rank >= 1 else "dormant"
        elif kind == "quarantine_gate":
            state = "quarantining" if rank >= 3 else "dormant"
        elif kind == "corruptor":
            state = "pursuing" if rank >= 3 or (rank >= 2 and hostile) else "dormant"
        else:
            state = "dormant"
        entity["state"] = state
        if known_avatar is not None and state in {"pursuing", "engaged", "tracing", "quarantining"}:
            entity["last_known_target"] = list(_wire_point(known_avatar))
        _set_entity(scene, entity)


def load_wire_program_to_ram(sim, actor_eid, instance_id=None, *, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    state = wire_state_for_actor(sim, actor_eid, create=True)
    scene = ensure_wire_combat_state(sim, actor_eid, item_catalog=item_catalog)
    if scene is None:
        refresh_wire_state_interface_capacity(sim, actor_eid, state, item_catalog=item_catalog)
        normalize_wire_ram_slots(state, item_catalog=item_catalog)
    program_slots = int(getattr(state, "program_slots", 0))
    loaded_ids = {_clean_text(entry.get("instance_id")) for entry in getattr(state, "ram_slots", ()) or () if isinstance(entry, Mapping)}
    candidates = []
    if instance_id:
        entry = _find_kit_entry(state, instance_id)
        if entry is not None:
            candidates.append(entry)
    else:
        candidates = [dict(entry) for entry in getattr(state, "kit_entries", ()) or () if isinstance(entry, Mapping)]
    program_candidates = [
        entry
        for entry in candidates
        if _is_program_entry(entry, item_catalog=item_catalog)
    ]
    if program_slots <= 0 and program_candidates:
        sim.emit(Event("wire_program_blocked", eid=actor_eid, reason="wire_interface_missing"))
        return {"ok": False, "reason": "wire_interface_missing"}
    for entry in program_candidates:
        iid = _clean_text(entry.get("instance_id"))
        if not iid or iid in loaded_ids:
            continue
        clean = _normalized_program_entry(entry, item_catalog=item_catalog, storage_status="ram")
        if clean is None:
            continue
        cost = _ram_cost(clean, item_catalog=item_catalog)
        if wire_ram_used_points(state, item_catalog=item_catalog) + cost > program_slots:
            continue
        clean["slot"] = len(getattr(state, "ram_slots", ()) or ())
        state.ram_slots.append(clean)
        state.last_wire_feedback = f"Loaded {_program_name(clean, item_catalog=item_catalog)} into RAM."
        if isinstance(scene, dict):
            scene["last_feedback"] = state.last_wire_feedback
            state.active_scene = dict(scene)
        sim.emit(Event(
            "wire_program_loaded",
            eid=actor_eid,
            item_id=clean.get("item_id"),
            instance_id=clean.get("instance_id"),
            program_key=_program_key_for_item(clean.get("item_id"), item_catalog=item_catalog),
            program_name=_program_name(clean, item_catalog=item_catalog),
        ))
        return {"ok": True, "reason": None, "entry": dict(clean)}
    reason = "ram_full" if program_candidates else "no_program_available"
    sim.emit(Event("wire_program_blocked", eid=actor_eid, reason=reason))
    return {"ok": False, "reason": reason}


def unload_wire_ram_slot(sim, actor_eid, *, index=None, instance_id=None, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    state = wire_state_for_actor(sim, actor_eid, create=False)
    if state is None:
        return {"ok": False, "reason": "missing_wire_state"}
    scene = ensure_wire_combat_state(sim, actor_eid, item_catalog=item_catalog)
    normalize_wire_ram_slots(state, item_catalog=item_catalog)
    slots = list(getattr(state, "ram_slots", ()) or ())
    target_index = None
    if instance_id:
        for idx, entry in enumerate(slots):
            if _clean_text(entry.get("instance_id")) == _clean_text(instance_id):
                target_index = idx
                break
    elif index is not None and 0 <= int(index) < len(slots):
        target_index = int(index)
    if target_index is None:
        return {"ok": False, "reason": "ram_entry_unavailable"}
    entry = dict(slots.pop(target_index))
    _update_kit_metadata(state, entry.get("instance_id"), entry.get("metadata"), item_catalog=item_catalog)
    for idx, row in enumerate(slots):
        row["slot"] = idx
    state.ram_slots = slots
    if isinstance(scene, dict):
        if _remove_effects_for_instance(scene, entry.get("instance_id")):
            scene["last_feedback"] = f"{_program_name(entry, item_catalog=item_catalog)} stops running."
        state.active_scene = dict(scene)
    state.last_wire_feedback = f"Unloaded {_program_name(entry, item_catalog=item_catalog)} from RAM."
    sim.emit(Event(
        "wire_program_unloaded",
        eid=actor_eid,
        instance_id=entry.get("instance_id"),
        program_name=_program_name(entry, item_catalog=item_catalog),
    ))
    return {"ok": True, "reason": None, "entry": entry}


def wire_program_rows(sim, actor_eid, *, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    state = wire_state_for_actor(sim, actor_eid, create=True)
    scene = ensure_wire_combat_state(sim, actor_eid, item_catalog=item_catalog)
    rows = []
    for idx, entry in enumerate(getattr(state, "ram_slots", ()) or ()):
        if not isinstance(entry, Mapping):
            continue
        key = _program_key_for_item(entry.get("item_id"), item_catalog=item_catalog)
        profile = _program_profile(entry.get("item_id"), item_catalog=item_catalog)
        metadata = dict(entry.get("metadata") or {})
        cooldown = _int(metadata.get("ram_reload_ticks_remaining"), 0, minimum=0)
        durability = _int(metadata.get("durability"), profile.get("durability_max", 1), minimum=0)
        runs = _int(metadata.get("runs"), profile.get("runs_max", 0), minimum=0)
        runs_max = _int(metadata.get("runs_max"), profile.get("runs_max", 0), minimum=0)
        mode = str(PROGRAM_SPECS.get(key, {}).get("mode", "active") or "active").strip().lower()
        suffix = f"{mode}, cd {cooldown}, dur {durability}"
        if bool(profile.get("dangerous")):
            suffix += ", hostile"
        if runs_max:
            suffix += f", runs {runs}/{runs_max}"
        effect_kind = PASSIVE_EFFECT_BY_PROGRAM.get(key)
        if effect_kind and isinstance(scene, Mapping) and _effect_active(scene, effect_kind):
            suffix += ", running"
        rows.append({
            "index": idx,
            "instance_id": _clean_text(entry.get("instance_id")),
            "item_id": _clean_key(entry.get("item_id")),
            "program_key": key,
            "mode": mode,
            "entry": dict(entry),
            "label": f"{_program_name(entry, item_catalog=item_catalog)} [{suffix}]",
        })
    return rows


def wire_blocking_ice_at(scene, x, y):
    point = (int(x), int(y))
    for entity in _active_ice_entities(scene):
        spec = ICE_SPECS.get(_clean_key(entity.get("kind")), {})
        if not bool(spec.get("blocks_route")):
            continue
        if _wire_point(entity) == point:
            return dict(entity)
    return None


def wire_program_load_rows(sim, actor_eid, *, item_catalog=None):
    """Return the exact kit programs the player may choose to load into RAM."""

    item_catalog = item_catalog or ITEM_CATALOG
    state = wire_state_for_actor(sim, actor_eid, create=True)
    scene = ensure_wire_combat_state(sim, actor_eid, item_catalog=item_catalog)
    if scene is None:
        refresh_wire_state_interface_capacity(sim, actor_eid, state, item_catalog=item_catalog)
        normalize_wire_ram_slots(state, item_catalog=item_catalog)
    loaded_ids = {
        _clean_text(entry.get("instance_id"))
        for entry in getattr(state, "ram_slots", ()) or ()
        if isinstance(entry, Mapping)
    }
    used_points = wire_ram_used_points(state, item_catalog=item_catalog)
    capacity = _int(getattr(state, "program_slots", 0), 0, minimum=0)
    rows = []
    for entry in getattr(state, "kit_entries", ()) or ():
        if not isinstance(entry, Mapping) or not _is_program_entry(entry, item_catalog=item_catalog):
            continue
        clean = _normalized_program_entry(entry, item_catalog=item_catalog, storage_status="wire_kit")
        if clean is None:
            continue
        instance_id = _clean_text(clean.get("instance_id"))
        if not instance_id or instance_id in loaded_ids:
            continue
        profile = _program_profile(clean.get("item_id"), item_catalog=item_catalog)
        metadata = dict(clean.get("metadata") or {})
        program_key = _program_key_for_item(clean.get("item_id"), item_catalog=item_catalog)
        cost = _ram_cost(clean, item_catalog=item_catalog)
        durability = _int(metadata.get("durability"), profile.get("durability_max", 1), minimum=0)
        runs = _int(metadata.get("runs"), profile.get("runs_max", 0), minimum=0)
        runs_max = _int(metadata.get("runs_max"), profile.get("runs_max", 0), minimum=0)
        mode = str(PROGRAM_SPECS.get(program_key, {}).get("mode", "active") or "active").strip().lower()
        fits = capacity > 0 and used_points + cost <= capacity
        condition = f"{mode}, RAM {cost}, dur {durability}"
        if runs_max:
            condition += f", runs {runs}/{runs_max}"
        condition += ", fits" if fits else ", no room"
        rows.append({
            "instance_id": instance_id,
            "item_id": _clean_key(clean.get("item_id")),
            "program_key": program_key,
            "mode": mode,
            "ram_cost": cost,
            "fits": bool(fits),
            "entry": dict(clean),
            "label": f"{_program_name(clean, item_catalog=item_catalog)} [{condition}]",
        })
    return rows


def wire_program_target_rows(sim, actor_eid):
    scene = ensure_wire_combat_state(sim, actor_eid)
    if not isinstance(scene, Mapping):
        return []
    rows = [{"kind": "self", "target_id": "self", "label": "Link self"}]
    node = _current_node(scene)
    if node:
        rows.append({
            "kind": "node",
            "target_id": str(node.get("node_id", "")),
            "node_kind": str(node.get("kind", "")),
            "label": f"Node: {node.get('label', 'node')}",
        })
    for entity in _live_ice_entities(scene):
        if not bool(entity.get("revealed")):
            continue
        rows.append({
            "kind": "ice",
            "target_id": str(entity.get("entity_id")),
            "label": f"ICE: {_entity_label(entity)} {entity.get('hp')}/{entity.get('hp_max')}",
            "entity": dict(entity),
        })
    from game.wire_users import wire_user_target_rows

    rows.extend(wire_user_target_rows(sim, scene, range_limit=PROGRAM_SPECS["talk"]["range"]))
    return rows


def _target_from_row(sim, scene, target=None, *, program_key=""):
    if isinstance(target, Mapping):
        kind = _clean_key(target.get("kind"))
        if kind == "node":
            node_id = _clean_text(target.get("target_id"))
            for node in scene.get("nodes", ()) or ():
                if isinstance(node, Mapping) and _clean_text(node.get("node_id")) == node_id:
                    return {"kind": "node", "node": dict(node), "label": str(node.get("label", "node"))}
        if kind == "ice":
            entity_id = _clean_text(target.get("target_id"))
            for entity in _live_ice_entities(scene):
                if not bool(entity.get("revealed")):
                    continue
                if _clean_text(entity.get("entity_id")) == entity_id:
                    return {"kind": "ice", "entity": dict(entity), "label": _entity_label(entity)}
        if kind == "self":
            return {"kind": "self", "label": "link self"}
        if kind == "user":
            from game.wire_users import resolve_wire_user_target

            return resolve_wire_user_target(sim, scene, target)
    spec = PROGRAM_SPECS.get(program_key, {})
    target_kind = spec.get("target")
    if target_kind == "ice":
        entities = [entity for entity in _live_ice_entities(scene) if bool(entity.get("revealed"))]
        if entities:
            return {"kind": "ice", "entity": entities[0], "label": _entity_label(entities[0])}
    if target_kind == "node":
        node = _current_node(scene)
        if node:
            return {"kind": "node", "node": node, "label": node.get("label", "node")}
    if target_kind == "self":
        return {"kind": "self", "label": "link self"}
    if target_kind == "user":
        from game.wire_users import resolve_wire_user_target

        return resolve_wire_user_target(sim, scene, None)
    return {"kind": "scene", "label": "local layer"}


def _grid_distance(scene, entity):
    avatar = scene.get("avatar") if isinstance(scene.get("avatar"), Mapping) else {}
    return abs(_int(avatar.get("x"), 0) - _int(entity.get("x"), 0)) + abs(_int(avatar.get("y"), 0) - _int(entity.get("y"), 0))


def _wire_point(value, default=(0, 0)):
    if isinstance(value, Mapping):
        return (_int(value.get("x"), default[0]), _int(value.get("y"), default[1]))
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return (_int(value[0], default[0]), _int(value[1], default[1]))
    return (int(default[0]), int(default[1]))


def _wire_route_path(scene, source, target):
    """Resolve an action through the scene's actual signal routes."""

    start = _wire_point(source)
    goal = _wire_point(target, start)
    if start == goal:
        return [list(start)]
    walkable = {
        _wire_point(point)
        for point in (scene.get("walkable", ()) or ())
        if isinstance(point, (list, tuple)) and len(point) >= 2
    }
    walkable.update((start, goal))
    frontier = deque((start,))
    previous = {start: None}
    while frontier:
        current = frontier.popleft()
        if current == goal:
            break
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            neighbor = (current[0] + dx, current[1] + dy)
            if neighbor not in walkable or neighbor in previous:
                continue
            previous[neighbor] = current
            frontier.append(neighbor)
    if goal not in previous:
        return [list(start), list(goal)]
    path = []
    current = goal
    while current is not None:
        path.append([int(current[0]), int(current[1])])
        current = previous[current]
    path.reverse()
    return path


def _begin_wire_action_frame(scene, *, cause="action"):
    scene["wire_action_frame"] = _int(scene.get("wire_action_frame"), 0, minimum=0) + 1
    scene["wire_action_cause"] = _clean_key(cause, "action")
    scene["wire_action_effects"] = []


def _record_wire_action(scene, *, source, target, visual_kind, label, source_kind="wire"):
    if not isinstance(scene, dict):
        return None
    source_point = _wire_point(source)
    target_point = _wire_point(target, source_point)
    visual = wire_visual_for_kind(visual_kind)
    row = {
        "source": [int(source_point[0]), int(source_point[1])],
        "target": [int(target_point[0]), int(target_point[1])],
        "path": _wire_route_path(scene, source_point, target_point),
        "visual_kind": str(visual.get("kind", visual_kind) or visual_kind),
        "glyph": str(visual.get("glyph", "*") or "*")[:1],
        "color": str(visual.get("color", "objective") or "objective"),
        "semantic_id": str(visual.get("semantic_id", f"wire_{visual_kind}") or f"wire_{visual_kind}"),
        "label": _clean_text(label, "Wire activity resolves."),
        "source_kind": _clean_key(source_kind, "wire"),
    }
    effects = [dict(effect) for effect in scene.get("wire_action_effects", ()) or () if isinstance(effect, Mapping)]
    effects.append(row)
    scene["wire_action_effects"] = effects[-12:]
    scene["last_wire_action"] = row["label"]
    return row


def _resolved_target_point(scene, target):
    if isinstance(target, Mapping):
        for key in ("entity", "user", "node"):
            value = target.get(key)
            if isinstance(value, Mapping):
                return _wire_point(value)
    return _wire_point(scene.get("avatar") if isinstance(scene, Mapping) else None)


def _scene_node_point(scene, kind, default=None):
    needle = _clean_key(kind)
    for node in scene.get("nodes", ()) or ():
        if isinstance(node, Mapping) and _clean_key(node.get("kind")) == needle:
            return _wire_point(node)
    return _wire_point(default or scene.get("avatar"))


def _advance_mobile_ice(scene, entity, goal=None):
    kind = _clean_key((entity or {}).get("kind"))
    spec = ICE_SPECS.get(kind, {})
    if not bool(spec.get("mobile")):
        return None
    if "ram_reset_attack" in tuple((entity or {}).get("traits", ()) or ()):
        return None
    if kind == "corruptor" and not _clean_text(scene.get("last_hostile_program_instance_id")):
        return None
    start = _wire_point(entity)
    if goal is None:
        goal = (entity or {}).get("last_known_target")
    if goal is None:
        goal = wire_session_alert(scene).get("last_anomaly")
    if goal is None:
        return None
    goal = _wire_point(goal, start)
    path = _wire_route_path(scene, start, goal)
    if len(path) <= 2:
        return None
    next_point = _wire_point(path[1], start)
    occupied = {
        _wire_point(other)
        for other in _live_ice_entities(scene)
        if _clean_text(other.get("entity_id")) != _clean_text(entity.get("entity_id"))
    }
    if next_point in occupied or next_point == goal:
        return None
    updated = dict(entity)
    updated["x"] = int(next_point[0])
    updated["y"] = int(next_point[1])
    updated["last_move_from"] = [int(start[0]), int(start[1])]
    _set_entity(scene, updated)
    return {"entity": updated, "from": start, "to": next_point}


def _validate_target(scene, program_key, target):
    spec = PROGRAM_SPECS.get(program_key)
    if not spec:
        return False, "unknown_program"
    expected = spec.get("target")
    if expected in {"self", "scene"}:
        return True, None
    if expected == "node":
        node = target.get("node") if isinstance(target, Mapping) else None
        if not isinstance(node, Mapping):
            return False, "missing_node_target"
        allowed = set(spec.get("node_kinds") or ())
        if allowed and _clean_key(node.get("kind")) not in allowed:
            return False, "wrong_node_type"
        return True, None
    if expected == "ice":
        entity = target.get("entity") if isinstance(target, Mapping) else None
        if not isinstance(entity, Mapping):
            return False, "missing_ice_target"
        if not bool(entity.get("revealed")):
            return False, "unresolved_ice_target"
        if _grid_distance(scene, entity) > _int(spec.get("range"), 1, minimum=0):
            return False, "target_out_of_range"
        return True, None
    if expected == "user":
        from game.wire_users import validate_wire_user_target

        return validate_wire_user_target(scene, target, range_limit=_int(spec.get("range"), 4, minimum=0))
    return True, None


def _refresh_trace_alert(scene):
    trace = _int(scene.get("trace_current"), 0, minimum=0)
    limit = max(1, _int(scene.get("trace_limit"), 12, minimum=1))
    awake = bool(scene.get("trace_awake")) or trace > 0
    if trace >= limit:
        level = "forced"
    elif trace >= int(limit * 0.75):
        level = "hot"
    elif trace >= int(limit * 0.45):
        level = "rising"
    elif awake:
        level = "watching"
    else:
        level = "quiet"
    scene["trace_alert_level"] = level
    scene["trace"] = f"{trace}/{limit} {level}"
    scene["buffer"] = f"{_int(scene.get('buffer_current'), 0)}/{_int(scene.get('buffer_max'), 1)}"


def _trace_awake(scene):
    return bool(scene.get("trace_awake")) or _int(scene.get("trace_current"), 0, minimum=0) > 0


def _wake_trace(sim, actor_eid, scene, *, reason="wire_action"):
    if _trace_awake(scene):
        return False
    scene["trace_awake"] = True
    scene["trace_awake_reason"] = _clean_text(reason, "wire_action")
    _refresh_trace_alert(scene)
    sim.emit(Event("wire_trace_awakened", eid=actor_eid, reason=reason))
    return True


def _add_trace(sim, actor_eid, scene, amount, *, reason="wire_action"):
    amount = int(amount)
    if amount == 0:
        return 0
    if amount > 0:
        _wake_trace(sim, actor_eid, scene, reason=reason)
        mitigation = 0
        if _effect_active(scene, "signal_cloak"):
            mitigation += 1
        if _effect_active(scene, "tunnel_route"):
            mitigation += max(1, _active_effect_strength(scene, "tunnel_route", default=1))
        proxy = _consume_effect(scene, "proxy_route")
        if proxy:
            mitigation += max(1, _int(proxy.get("strength"), 6, minimum=1))
        if mitigation > 0:
            before_amount = amount
            amount = max(0, amount - mitigation)
            sim.emit(Event(
                "wire_trace_deflected",
                eid=actor_eid,
                reason=reason,
                before=before_amount,
                after=amount,
                mitigation=before_amount - amount,
                proxy_burned=bool(proxy),
            ))
            if amount == 0:
                _refresh_trace_alert(scene)
                return 0
    before = _int(scene.get("trace_current"), 0, minimum=0)
    after = max(0, before + amount)
    scene["trace_current"] = after
    _refresh_trace_alert(scene)
    sim.emit(Event("wire_trace_changed", eid=actor_eid, before=before, after=after, delta=after - before, reason=reason))
    return after - before


def _add_buffer_damage(sim, actor_eid, scene, amount, *, reason="ice"):
    amount = max(0, int(amount))
    if amount <= 0:
        return 0
    before = _int(scene.get("buffer_current"), scene.get("buffer_max", 1), minimum=0)
    after = max(0, before - amount)
    scene["buffer_current"] = after
    _refresh_trace_alert(scene)
    sim.emit(Event("wire_buffer_changed", eid=actor_eid, before=before, after=after, delta=after - before, reason=reason))
    return before - after


def _effect_active(scene, kind):
    key = _clean_key(kind)
    return any(isinstance(effect, Mapping) and _clean_key(effect.get("kind")) == key and _int(effect.get("turns"), 0) > 0 for effect in scene.get("active_effects", ()) or ())


def _active_effect_strength(scene, kind, *, default=0):
    key = _clean_key(kind)
    for effect in scene.get("active_effects", ()) or ():
        if isinstance(effect, Mapping) and _clean_key(effect.get("kind")) == key and _int(effect.get("turns"), 0) > 0:
            return _int(effect.get("strength"), default, minimum=0)
    return int(default)


def _consume_effect(scene, kind):
    key = _clean_key(kind)
    effects = []
    consumed = None
    for effect in scene.get("active_effects", ()) or ():
        row = dict(effect) if isinstance(effect, Mapping) else {}
        if consumed is None and _clean_key(row.get("kind")) == key and _int(row.get("turns"), 0) > 0:
            consumed = row
            continue
        if row:
            effects.append(row)
    scene["active_effects"] = effects
    return consumed


def _append_effect(scene, kind, *, turns=1, instance_id="", strength=0):
    effects = [dict(effect) for effect in scene.get("active_effects", ()) or () if isinstance(effect, Mapping)]
    row = {"kind": _clean_key(kind), "turns": max(1, int(turns)), "instance_id": _clean_text(instance_id)}
    strength_value = _int(strength, 0, minimum=0)
    if strength_value > 0:
        row["strength"] = strength_value
    effects.append(row)
    scene["active_effects"] = effects


def _remove_effects_for_instance(scene, instance_id):
    iid = _clean_text(instance_id)
    if not iid:
        return 0
    kept = []
    removed = 0
    for effect in scene.get("active_effects", ()) or ():
        if not isinstance(effect, Mapping):
            continue
        row = dict(effect)
        if _clean_text(row.get("instance_id")) == iid:
            removed += 1
            continue
        kept.append(row)
    scene["active_effects"] = kept
    return removed


def _decrement_effects(scene):
    kept = []
    for effect in scene.get("active_effects", ()) or ():
        if not isinstance(effect, Mapping):
            continue
        row = dict(effect)
        row["turns"] = _int(row.get("turns"), 0) - 1
        if row["turns"] > 0:
            kept.append(row)
    scene["active_effects"] = kept


def _decrement_ram_cooldowns(state, *, skip_instance_id="", item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    skip = _clean_text(skip_instance_id)
    slots = []
    for entry in getattr(state, "ram_slots", ()) or ():
        row = _normalized_program_entry(entry, item_catalog=item_catalog, storage_status="ram")
        if row is None:
            continue
        metadata = dict(row.get("metadata") or {})
        if _clean_text(row.get("instance_id")) != skip:
            remaining = max(0, _int(metadata.get("ram_reload_ticks_remaining"), 0) - 1)
            metadata["ram_reload_ticks_remaining"] = remaining
        row["metadata"] = metadata
        slots.append(row)
        _update_kit_metadata(state, row.get("instance_id"), metadata, item_catalog=item_catalog)
    state.ram_slots = slots


def _damage_ice(sim, actor_eid, scene, entity, amount, *, program_key=""):
    updated = dict(entity)
    before = _int(updated.get("hp"), 0, minimum=0)
    after = max(0, before - max(0, int(amount)))
    updated["hp"] = after
    if after <= 0:
        updated["destroyed"] = True
    _set_entity(scene, updated)
    sim.emit(Event(
        "wire_ice_damaged",
        eid=actor_eid,
        entity_id=updated.get("entity_id"),
        ice_kind=updated.get("kind"),
        ice_label=_entity_label(updated),
        damage=max(0, before - after),
        hp=after,
        program_key=program_key,
    ))
    if after <= 0:
        sim.emit(Event(
            "wire_ice_destroyed",
            eid=actor_eid,
            entity_id=updated.get("entity_id"),
            ice_kind=updated.get("kind"),
            ice_label=_entity_label(updated),
        ))
    _refresh_clean_exit_block(scene)
    return updated


def _refresh_clean_exit_block(scene):
    blocked = False
    for entity in _live_ice_entities(scene):
        if _clean_key(entity.get("kind")) == "quarantine_gate" and _clean_key(entity.get("state")) == "quarantining":
            blocked = True
    scene["clean_exit_blocked"] = bool(blocked)
    return bool(blocked)


def _last_ram_entry(state, instance_id, *, item_catalog=None):
    iid = _clean_text(instance_id)
    for entry in getattr(state, "ram_slots", ()) or ():
        if isinstance(entry, Mapping) and _clean_text(entry.get("instance_id")) == iid:
            return _normalized_program_entry(entry, item_catalog=item_catalog, storage_status="ram")
    return None


def _set_ram_entry(state, updated, *, item_catalog=None):
    iid = _clean_text((updated or {}).get("instance_id"))
    slots = []
    for entry in getattr(state, "ram_slots", ()) or ():
        row = _normalized_program_entry(entry, item_catalog=item_catalog, storage_status="ram")
        if row is None:
            continue
        if iid and _clean_text(row.get("instance_id")) == iid:
            row.update(dict(updated))
        slots.append(row)
    for idx, row in enumerate(slots):
        row["slot"] = idx
    state.ram_slots = slots
    if updated:
        _update_kit_metadata(state, updated.get("instance_id"), updated.get("metadata"), item_catalog=item_catalog)


def _damage_program(sim, actor_eid, state, scene, instance_id, *, reason="corruption", item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    if _consume_effect(scene, "checksum_ward"):
        sim.emit(Event("wire_program_corrupted", eid=actor_eid, instance_id=instance_id, reason="checksum_ward_absorbed", absorbed=True))
        return {"ok": True, "absorbed": True}
    shell = _consume_effect(scene, "sacrificial_shell")
    if shell and _clean_text(shell.get("instance_id")):
        instance_id = shell.get("instance_id")
    entry = _last_ram_entry(state, instance_id, item_catalog=item_catalog)
    if entry is None:
        return {"ok": False, "reason": "program_unavailable"}
    metadata = dict(entry.get("metadata") or {})
    before = _int(metadata.get("durability"), metadata.get("durability_max", 1), minimum=0)
    metadata["durability"] = max(0, before - 1)
    metadata.setdefault("corruption_tags", ())
    tags = list(metadata.get("corruption_tags") or ())
    if "ice_touched" not in tags:
        tags.append("ice_touched")
    metadata["corruption_tags"] = tuple(tags)
    entry["metadata"] = metadata
    _set_ram_entry(state, entry, item_catalog=item_catalog)
    sim.emit(Event(
        "wire_program_corrupted",
        eid=actor_eid,
        instance_id=entry.get("instance_id"),
        program_key=_program_key_for_item(entry.get("item_id"), item_catalog=item_catalog),
        program_name=_program_name(entry, item_catalog=item_catalog),
        reason=reason,
        durability=metadata["durability"],
        absorbed=False,
    ))
    return {"ok": True, "entry": entry}


def _reset_ram(sim, actor_eid, state, scene, *, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    if _consume_effect(scene, "checksum_ward"):
        sim.emit(Event("wire_ram_reset", eid=actor_eid, absorbed=True, reason="checksum_ward_absorbed"))
        return {"ok": True, "absorbed": True}
    slots = list(getattr(state, "ram_slots", ()) or ())
    if not slots:
        return {"ok": False, "reason": "no_ram"}
    target = None
    hostile_iid = _clean_text(scene.get("last_hostile_program_instance_id"))
    if hostile_iid:
        for slot in slots:
            if isinstance(slot, Mapping) and _clean_text(slot.get("instance_id")) == hostile_iid:
                target = _normalized_program_entry(slot, item_catalog=item_catalog, storage_status="ram")
                break
    if target is None:
        target = _normalized_program_entry(slots[-1], item_catalog=item_catalog, storage_status="ram")
    metadata = dict(target.get("metadata") or {})
    metadata["ram_reload_ticks_remaining"] = max(_int(metadata.get("ram_reload_ticks_remaining"), 0), 3 + _scene_security(scene))
    target["metadata"] = metadata
    _set_ram_entry(state, target, item_catalog=item_catalog)
    sim.emit(Event(
        "wire_ram_reset",
        eid=actor_eid,
        instance_id=target.get("instance_id"),
        program_name=_program_name(target, item_catalog=item_catalog),
        cooldown=metadata["ram_reload_ticks_remaining"],
        absorbed=False,
    ))
    return {"ok": True, "entry": target}


def _check_forced_eject(sim, actor_eid, state, scene, *, reason="trace"):
    trace = _int(scene.get("trace_current"), 0, minimum=0)
    limit = _int(scene.get("trace_limit"), 12, minimum=1)
    buffer_current = _int(scene.get("buffer_current"), scene.get("buffer_max", 1), minimum=0)
    if trace < limit and buffer_current > 0:
        return False
    eject_reason = "trace" if trace >= limit else "buffer"
    scene["ejection_state"] = {
        "kind": "forced",
        "reason": eject_reason,
        "trace": trace,
        "trace_limit": limit,
        "buffer": buffer_current,
        "tick": int(getattr(sim, "tick", 0)),
    }
    state.last_ejection_state = dict(scene["ejection_state"])
    state.active_scene = dict(scene)
    sim.emit(Event("wire_forced_eject", eid=actor_eid, reason=eject_reason, trace=trace, trace_limit=limit, buffer=buffer_current))
    from game.wire_scene import close_wire_scene

    close_wire_scene(sim, actor_eid, reason=f"forced_{eject_reason}", disconnect=True)
    return True


def advance_wire_combat_turn(
    sim,
    actor_eid,
    *,
    cause="action",
    skip_cooldown_instance_id="",
    preserve_action_effects=False,
    item_catalog=None,
):
    item_catalog = item_catalog or ITEM_CATALOG
    state = wire_state_for_actor(sim, actor_eid, create=False)
    if state is None or not isinstance(getattr(state, "active_scene", None), Mapping):
        return {"ok": False, "reason": "missing_scene"}
    scene = ensure_wire_combat_state(sim, actor_eid, item_catalog=item_catalog)
    if scene is None:
        return {"ok": False, "reason": "missing_scene"}
    if not preserve_action_effects:
        _begin_wire_action_frame(scene, cause=cause)
    scene["wire_turn_index"] = _int(scene.get("wire_turn_index"), 0, minimum=0) + 1
    _decrement_ram_cooldowns(state, skip_instance_id=skip_cooldown_instance_id, item_catalog=item_catalog)
    _decrement_effects(scene)
    if _check_forced_eject(sim, actor_eid, state, scene, reason=cause):
        return {"ok": True, "reason": "forced_eject", "scene": None}
    normalize_wire_session_security(scene)
    _sync_ice_states(scene)
    memory_speed = _int(scene.get("interface_memory_speed"), 1, minimum=0)
    avatar_point = _wire_point(scene.get("avatar"))
    for entity in _active_ice_entities(scene):
        kind = _clean_key(entity.get("kind"))
        ice_state = _clean_key(entity.get("state"))
        spec = ICE_SPECS.get(kind, {})
        alert = wire_session_alert(scene)
        known_avatar = alert.get("known_avatar")
        known_point = _wire_point(known_avatar) if known_avatar is not None else None
        goal = known_point if ice_state in {"pursuing", "engaged"} else alert.get("last_anomaly")
        pursuit = _advance_mobile_ice(scene, entity, goal=goal)
        if pursuit:
            entity = dict(pursuit["entity"])
            if ice_state == "investigating":
                action_label = f"{_entity_label(entity)} searches the route around the last anomaly."
            else:
                action_label = f"{_entity_label(entity)} advances on its last fix for your process."
            reveal_wire_ice(scene, entity.get("entity_id"), state=ice_state)
            _record_wire_action(
                scene,
                source=pursuit["from"],
                target=pursuit["to"],
                visual_kind=spec.get("visual", "effect_trace_sweep"),
                label=action_label,
                source_kind="ice_move",
            )
            sim.emit(Event(
                "wire_ice_acted",
                eid=actor_eid,
                ice_kind=kind,
                ice_label=_entity_label(entity),
                cause=cause,
                action="advance",
                x=entity.get("x"),
                y=entity.get("y"),
            ))
            if kind == "camera_watchdog" and abs(_int(entity.get("x")) - avatar_point[0]) + abs(_int(entity.get("y")) - avatar_point[1]) <= 1:
                wire_acquire_avatar(
                    sim,
                    actor_eid,
                    scene,
                    reason="watchdog_contact",
                    position=avatar_point,
                    alert_amount=18,
                )
            continue
        if ice_state == "watching":
            continue
        trace = _int(spec.get("trace"), 0, minimum=0)
        buffer_damage = _int(spec.get("buffer"), 0, minimum=0)
        action_target = avatar_point
        action_visual = "effect_trace_sweep" if trace else "effect_packet_pulse"
        action_label = f"{_entity_label(entity)} sends pressure toward your process."
        if _effect_active(scene, "signal_cloak"):
            buffer_damage = max(0, buffer_damage - 1)
        traits = tuple(entity.get("traits", ()) or ())
        if "memory_speed_trace" in traits:
            trace += max(1, memory_speed // 2)
        if kind == "camera_watchdog":
            distance = abs(_int(entity.get("x")) - avatar_point[0]) + abs(_int(entity.get("y")) - avatar_point[1])
            if distance <= 1 and known_point != avatar_point:
                wire_acquire_avatar(
                    sim,
                    actor_eid,
                    scene,
                    reason="watchdog_contact",
                    position=avatar_point,
                    alert_amount=18,
                )
                entity = reveal_wire_ice(scene, entity.get("entity_id"), state="pursuing") or entity
                known_point = avatar_point
            elif ice_state == "investigating":
                continue
        has_current_fix = known_point is not None and known_point == avatar_point
        if "ram_reset_attack" in traits and has_current_fix:
            _reset_ram(sim, actor_eid, state, scene, item_catalog=item_catalog)
            entity = reveal_wire_ice(scene, entity.get("entity_id"), state=ice_state) or entity
            action_label = f"{_entity_label(entity)} drives a reset pulse into loaded RAM."
            _record_wire_action(
                scene,
                source=entity,
                target=avatar_point,
                visual_kind="effect_corruption_flecks",
                label=action_label,
                source_kind="ice",
            )
            sim.emit(Event("wire_ice_acted", eid=actor_eid, ice_kind=kind, ice_label=_entity_label(entity), cause=cause, action="ram_reset"))
            continue
        if kind in {"camera_watchdog", "door_arbiter"} and not has_current_fix:
            continue
        if kind in {"camera_watchdog", "door_arbiter"} and _grid_distance(scene, entity) > 1:
            continue
        if kind == "trace_sentinel" and ice_state != "tracing":
            continue
        if kind == "compliance_daemon":
            healed = False
            for other in _live_ice_entities(scene):
                if other.get("entity_id") == entity.get("entity_id"):
                    continue
                hp = _int(other.get("hp"), 0)
                hp_max = _int(other.get("hp_max"), hp)
                if hp < hp_max:
                    other["hp"] = min(hp_max, hp + 2)
                    _set_entity(scene, other)
                    healed = True
                    action_target = _wire_point(other)
                    action_visual = "effect_buffer_shield"
                    action_label = f"{_entity_label(entity)} sends a repair packet to {_entity_label(other)}."
                    break
            if healed:
                trace = 0
            else:
                continue
        if kind == "quarantine_gate":
            if ice_state != "quarantining":
                continue
            scene["clean_exit_blocked"] = True
            action_target = _scene_node_point(scene, "exit", scene.get("avatar"))
            action_visual = "effect_lock_bars"
            action_label = f"{_entity_label(entity)} holds lock bars across the exit route."
        if kind == "corruptor":
            if ice_state != "pursuing":
                continue
            target_iid = _clean_text(scene.get("last_hostile_program_instance_id"))
            if target_iid:
                corrupt_target = _last_ram_entry(state, target_iid, item_catalog=item_catalog)
                _damage_program(sim, actor_eid, state, scene, target_iid, reason="corruptor", item_catalog=item_catalog)
                buffer_damage = 0
                action_visual = "effect_corruption_flecks"
                action_label = (
                    f"{_entity_label(entity)} throws corruption into "
                    f"{_program_name(corrupt_target, item_catalog=item_catalog) if corrupt_target else 'the attacking program'}."
                )
            elif not has_current_fix or _grid_distance(scene, entity) > 1:
                continue
        entity = reveal_wire_ice(scene, entity.get("entity_id"), state=ice_state) or entity
        if trace:
            _add_trace(sim, actor_eid, scene, trace, reason=f"ice_{kind}")
        if buffer_damage:
            _add_buffer_damage(sim, actor_eid, scene, buffer_damage, reason=f"ice_{kind}")
            if action_visual == "effect_packet_pulse":
                action_label = f"{_entity_label(entity)} strikes your buffer along the signal route."
        _record_wire_action(
            scene,
            source=entity,
            target=action_target,
            visual_kind=action_visual,
            label=action_label,
            source_kind="ice",
        )
        sim.emit(Event("wire_ice_acted", eid=actor_eid, ice_kind=kind, ice_label=_entity_label(entity), cause=cause))
    _refresh_clean_exit_block(scene)
    _refresh_trace_alert(scene)
    state.active_scene = dict(scene)
    if _check_forced_eject(sim, actor_eid, state, scene, reason=cause):
        return {"ok": True, "reason": "forced_eject", "scene": None}
    return {"ok": True, "reason": None, "scene": dict(scene)}


def _mark_program_use(state, entry, *, program_key, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    profile = _program_profile(entry.get("item_id"), item_catalog=item_catalog)
    metadata = dict(entry.get("metadata") or {})
    metadata["ram_reload_ticks_remaining"] = _int(
        metadata.get("reload_ticks"),
        profile.get("reload_ticks", 0),
        minimum=0,
    )
    durability = _int(metadata.get("durability"), profile.get("durability_max", 1), minimum=0)
    metadata["durability"] = max(0, durability - 1)
    runs_max = _int(metadata.get("runs_max"), profile.get("runs_max", 0), minimum=0)
    if runs_max:
        metadata["runs"] = max(0, _int(metadata.get("runs"), runs_max, minimum=0) - 1)
    entry["metadata"] = metadata
    _set_ram_entry(state, entry, item_catalog=item_catalog)


def _active_trait(scene, trait):
    needle = _clean_key(trait)
    for entity in _active_ice_entities(scene):
        if needle in tuple(entity.get("traits", ()) or ()):
            return True
    return False


def run_wire_program(sim, actor_eid, *, program_instance_id=None, program_index=None, target=None, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    state = wire_state_for_actor(sim, actor_eid, create=False)
    if state is None or not isinstance(getattr(state, "active_scene", None), Mapping):
        return {"ok": False, "reason": "missing_scene"}
    scene = ensure_wire_combat_state(sim, actor_eid, item_catalog=item_catalog)
    slots = list(getattr(state, "ram_slots", ()) or ())
    entry = None
    if program_instance_id:
        for row in slots:
            if _clean_text(row.get("instance_id")) == _clean_text(program_instance_id):
                entry = dict(row)
                break
    elif program_index is not None and 0 <= int(program_index) < len(slots):
        entry = dict(slots[int(program_index)])
    elif slots:
        entry = dict(slots[0])
    if entry is None:
        reason = "no_loaded_program"
        sim.emit(Event("wire_program_blocked", eid=actor_eid, reason=reason))
        return {"ok": False, "reason": reason}
    program_key = _program_key_for_item(entry.get("item_id"), item_catalog=item_catalog)
    metadata = dict(entry.get("metadata") or {})
    profile = _program_profile(entry.get("item_id"), item_catalog=item_catalog)
    if _int(metadata.get("ram_reload_ticks_remaining"), 0, minimum=0) > 0:
        reason = "program_reloading"
        sim.emit(Event("wire_program_blocked", eid=actor_eid, reason=reason, program_key=program_key))
        return {"ok": False, "reason": reason}
    if _int(metadata.get("durability"), profile.get("durability_max", 1), minimum=0) <= 0:
        reason = "program_corrupted"
        sim.emit(Event("wire_program_blocked", eid=actor_eid, reason=reason, program_key=program_key))
        return {"ok": False, "reason": reason}
    if _int(metadata.get("runs_max"), profile.get("runs_max", 0), minimum=0) and _int(metadata.get("runs"), 0, minimum=0) <= 0:
        reason = "program_spent"
        sim.emit(Event("wire_program_blocked", eid=actor_eid, reason=reason, program_key=program_key))
        return {"ok": False, "reason": reason}
    resolved_target = _target_from_row(sim, scene, target, program_key=program_key)
    ok, reason = _validate_target(scene, program_key, resolved_target)
    if not ok:
        sim.emit(Event("wire_program_blocked", eid=actor_eid, reason=reason, program_key=program_key))
        return {"ok": False, "reason": reason}
    if program_key in {"handshake_breaker", "door_latch", "camera_loop", "data_siphon_shell"}:
        from game.wire_consequences import wire_physical_effect_preflight

        preflight = wire_physical_effect_preflight(sim, scene, program_key, actor_eid=actor_eid)
        if not preflight.get("ok"):
            reason = str(preflight.get("reason", "blocked") or "blocked")
            sim.emit(Event("wire_program_blocked", eid=actor_eid, reason=reason, program_key=program_key))
            return {"ok": False, "reason": reason}
        if program_key == "data_siphon_shell":
            from game.wire_data_market import wire_data_siphon_preflight

            data_preflight = wire_data_siphon_preflight(
                sim,
                actor_eid,
                scene,
                target=resolved_target,
                extraction_mode="decryptor",
                item_catalog=item_catalog,
            )
            if not data_preflight.get("ok"):
                reason = str(data_preflight.get("reason", "blocked") or "blocked")
                sim.emit(Event("wire_program_blocked", eid=actor_eid, reason=reason, program_key=program_key))
                return {"ok": False, "reason": reason}

    _begin_wire_action_frame(scene, cause=f"program_{program_key}")
    program_source = _wire_point(scene.get("avatar"))
    program_target = _resolved_target_point(scene, resolved_target)
    trace_add = _int(metadata.get("trace_cost"), profile.get("trace_cost", 0), minimum=0)
    action_noise = _int(metadata.get("noise"), profile.get("noise", 0), minimum=0)
    if _active_trait(scene, "blackbox_auditor") and program_key in OFFENSIVE_PROGRAMS:
        trace_add += 1
    _add_trace(sim, actor_eid, scene, trace_add, reason=f"program_{program_key}")
    security_result = resolve_wire_action_security(
        sim,
        actor_eid,
        scene,
        kind=f"program_{program_key}",
        source=program_source,
        target=program_target,
        base_signature=action_noise + (3 if program_key == "route_probe" else 0),
        hostile=program_key in OFFENSIVE_PROGRAMS,
        cloak_strength=_active_effect_strength(scene, "signal_cloak", default=1) if _effect_active(scene, "signal_cloak") else 0,
        acquire_avatar=program_key in OFFENSIVE_PROGRAMS,
    )
    feedback = f"{PROGRAM_SPECS.get(program_key, {}).get('label', program_key)} runs."
    forced_disconnect_after_run = False
    forced_disconnect_reason = "wire_network_locked"
    if program_key == "route_probe":
        revealed_edges = wire_reveal_all_security_edges(scene)
        entities = []
        for entity in _live_ice_entities(scene):
            entity["revealed"] = True
            _set_entity(scene, entity)
            traits = ", ".join(entity.get("traits", ()) or ()) or "standard"
            entities.append(f"{_entity_label(entity)} [{traits}]")
        feedback = "Route probe reveals " + (", ".join(entities) if entities else "no installed ICE") + f" and {revealed_edges} protected route(s)."
    elif program_key in {"spike", "ice_cutter"}:
        entity = dict(resolved_target.get("entity") or {})
        damage = _int(PROGRAM_SPECS[program_key].get("damage"), 1)
        if program_key == "ice_cutter" and _clean_key(entity.get("kind")) not in {"quarantine_gate", "door_arbiter"}:
            damage = max(2, damage - 1)
        damaged = _damage_ice(sim, actor_eid, scene, entity, damage, program_key=program_key)
        if bool(damaged.get("destroyed")) and _clean_key(damaged.get("kind")) == "trace_sentinel":
            _add_trace(sim, actor_eid, scene, -4, reason="trace_sentinel_destroyed")
        scene["last_hostile_program_instance_id"] = _clean_text(entry.get("instance_id"))
        feedback = f"{PROGRAM_SPECS[program_key]['label']} hits {_entity_label(entity)} for {damage}."
    elif program_key == "trace_scrubber":
        _add_trace(sim, actor_eid, scene, _int(PROGRAM_SPECS[program_key].get("trace_delta"), -5), reason="trace_scrubber")
        feedback = "Trace scrubber drags the trace back."
    elif program_key == "signal_cloak":
        _append_effect(scene, "signal_cloak", turns=PROGRAM_SPECS[program_key].get("effect_turns", 4), instance_id=entry.get("instance_id"))
        feedback = "Signal cloak softens the link signature."
    elif program_key == "proxy_route":
        _append_effect(
            scene,
            "proxy_route",
            turns=PROGRAM_SPECS[program_key].get("effect_turns", 999),
            instance_id=entry.get("instance_id"),
            strength=PROGRAM_SPECS[program_key].get("trace_absorb", 6),
        )
        feedback = "Proxy route waits to burn against the next trace spike."
    elif program_key == "tunnel_route":
        _append_effect(
            scene,
            "tunnel_route",
            turns=PROGRAM_SPECS[program_key].get("effect_turns", 6),
            instance_id=entry.get("instance_id"),
            strength=PROGRAM_SPECS[program_key].get("trace_reduction", 1),
        )
        feedback = "Tunnel route bleeds trace pressure off the link."
    elif program_key == "checksum_ward":
        _append_effect(scene, "checksum_ward", turns=999, instance_id=entry.get("instance_id"))
        feedback = "Checksum ward waits for the next corrupting hit."
    elif program_key == "sacrificial_shell":
        _append_effect(scene, "sacrificial_shell", turns=999, instance_id=entry.get("instance_id"))
        feedback = "Sacrificial shell takes point against corruptors."
    elif program_key == "panic_eject":
        scene["ejection_state"] = {"kind": "program", "reason": "panic_eject", "tick": int(getattr(sim, "tick", 0))}
        state.last_ejection_state = dict(scene["ejection_state"])
        state.active_scene = dict(scene)
        _mark_program_use(state, entry, program_key=program_key, item_catalog=item_catalog)
        sim.emit(Event("wire_panic_eject", eid=actor_eid, program_key=program_key, clean=True))
        from game.wire_scene import close_wire_scene

        close_wire_scene(sim, actor_eid, reason="program_panic", disconnect=True)
        return {"ok": True, "reason": None, "closed": True, "program_key": program_key, "feedback": "Program eject completes."}
    elif program_key == "door_latch":
        from game.wire_consequences import apply_wire_physical_effect

        effect = apply_wire_physical_effect(sim, actor_eid, scene, program_key, target=resolved_target)
        scene["door_latch_primed"] = True
        scene["last_hostile_program_instance_id"] = _clean_text(entry.get("instance_id"))
        forced_disconnect_after_run = bool(effect.get("forced_disconnect"))
        feedback = str(effect.get("feedback", "Door latch opens a short controller window.") or "")
    elif program_key == "camera_loop":
        from game.wire_consequences import apply_wire_physical_effect

        effect = apply_wire_physical_effect(sim, actor_eid, scene, program_key, target=resolved_target)
        scene["camera_loop_primed"] = True
        scene["last_hostile_program_instance_id"] = _clean_text(entry.get("instance_id"))
        forced_disconnect_after_run = bool(effect.get("forced_disconnect"))
        feedback = str(effect.get("feedback", "Camera loop blinds one linked feed for a short window.") or "")
    elif program_key == "handshake_breaker":
        from game.wire_consequences import apply_wire_physical_effect

        effect = apply_wire_physical_effect(sim, actor_eid, scene, program_key, target=resolved_target)
        scene["handshake_breaker_primed"] = True
        scene["last_hostile_program_instance_id"] = _clean_text(entry.get("instance_id"))
        forced_disconnect_after_run = bool(effect.get("forced_disconnect"))
        forced_disconnect_reason = str(effect.get("disconnect_reason", forced_disconnect_reason) or forced_disconnect_reason)
        feedback = str(effect.get("feedback", "Handshake breaker noisily disrupts the external drone link.") or "")
    elif program_key == "data_siphon_shell":
        from game.wire_consequences import apply_wire_physical_effect
        from game.wire_data_market import extract_wire_data_cache

        effect = apply_wire_physical_effect(sim, actor_eid, scene, program_key, target=resolved_target)
        extraction = extract_wire_data_cache(
            sim,
            actor_eid,
            scene,
            target=resolved_target,
            extraction_mode="decryptor",
            item_catalog=item_catalog,
        )
        scene["data_siphon_primed"] = True
        scene["last_hostile_program_instance_id"] = _clean_text(entry.get("instance_id"))
        forced_disconnect_after_run = bool(effect.get("forced_disconnect"))
        if extraction.get("ok"):
            extracted = extraction.get("entry") if isinstance(extraction.get("entry"), Mapping) else {}
            display_name = str((extracted.get("metadata") or {}).get("display_name", "data cache") or "data cache")
            scene["last_data_cache_instance_id"] = extracted.get("instance_id")
            feedback = (
                f"Decryptor Shell finishes {display_name}."
                if extraction.get("upgraded")
                else f"Decryptor Shell pulls and fully decodes {display_name}."
            )
            objective = dict(scene.get("objective") or {})
            objective.update({"completed": True, "completed_kind": "decrypted_download"})
            scene["objective"] = objective
        else:
            feedback = str(effect.get("feedback", "Decryptor Shell dirties the records surface.") or "")
    elif program_key == "talk":
        from game.wire_users import open_wire_dialogue

        dialogue = open_wire_dialogue(sim, actor_eid, scene, resolved_target)
        if not dialogue.get("ok"):
            reason = str(dialogue.get("reason", "wire_user_refused") or "wire_user_refused")
            sim.emit(Event("wire_program_blocked", eid=actor_eid, reason=reason, program_key=program_key))
            return {"ok": False, "reason": reason}
        feedback = str(dialogue.get("feedback", "Talk channel open.") or "Talk channel open.")

    _record_wire_action(
        scene,
        source=program_source,
        target=program_target,
        visual_kind=PROGRAM_VISUAL_BY_KEY.get(program_key, "effect_packet_pulse"),
        label=feedback,
        source_kind="program",
    )
    _mark_program_use(state, entry, program_key=program_key, item_catalog=item_catalog)
    scene["last_program_result"] = {
        "program_key": program_key,
        "program_name": _program_name(entry, item_catalog=item_catalog),
        "target": resolved_target.get("label", ""),
        "feedback": feedback,
    }
    scene["last_feedback"] = feedback
    scene["running_program"] = f"{PROGRAM_SPECS.get(program_key, {}).get('label', program_key)}: {resolved_target.get('label', '')}"
    log = list(scene.get("combat_log", ()) or ())
    log.append(feedback)
    scene["combat_log"] = log[-8:]
    _refresh_clean_exit_block(scene)
    _refresh_trace_alert(scene)
    state.active_scene = dict(scene)
    sim.emit(Event(
        "wire_program_run",
        eid=actor_eid,
        program_key=program_key,
        program_name=_program_name(entry, item_catalog=item_catalog),
        target_label=resolved_target.get("label", ""),
        feedback=feedback,
        trace=scene.get("trace_current"),
        buffer=scene.get("buffer_current"),
        alert=(scene.get("session_alert") or {}).get("level", "quiet"),
        detected=bool(security_result.get("detected")),
    ))
    if forced_disconnect_after_run:
        scene["ejection_state"] = {
            "kind": "forced",
            "reason": forced_disconnect_reason,
            "trace": scene.get("trace_current"),
            "trace_limit": scene.get("trace_limit"),
            "buffer": scene.get("buffer_current"),
            "tick": int(getattr(sim, "tick", 0)),
        }
        state.last_ejection_state = dict(scene["ejection_state"])
        from game.wire_scene import close_wire_scene

        close_wire_scene(sim, actor_eid, reason=forced_disconnect_reason, disconnect=True)
        return {
            "ok": True,
            "reason": None,
            "closed": True,
            "program_key": program_key,
            "feedback": feedback,
            "scene": {},
        }
    advance_wire_combat_turn(
        sim,
        actor_eid,
        cause=f"program_{program_key}",
        skip_cooldown_instance_id=entry.get("instance_id"),
        preserve_action_effects=True,
        item_catalog=item_catalog,
    )
    state = wire_state_for_actor(sim, actor_eid, create=False)
    return {
        "ok": True,
        "reason": None,
        "program_key": program_key,
        "feedback": feedback,
        "scene": dict(getattr(state, "active_scene", {}) or {}),
    }


def request_clean_wire_exit(sim, actor_eid):
    state = wire_state_for_actor(sim, actor_eid, create=False)
    if state is None or not isinstance(getattr(state, "active_scene", None), Mapping):
        return {"ok": False, "reason": "missing_scene"}
    scene = ensure_wire_combat_state(sim, actor_eid)
    current = _current_node(scene)
    if not isinstance(current, Mapping) or _clean_key(current.get("kind")) != "exit":
        reason = "exit_node_required"
        scene["last_feedback"] = "Reach the exit node for a clean disconnect, or use panic exit now."
        state.active_scene = dict(scene)
        sim.emit(Event("wire_program_blocked", eid=actor_eid, reason=reason))
        return {"ok": False, "reason": reason}
    _sync_ice_states(scene)
    if _refresh_clean_exit_block(scene):
        reason = "clean_exit_blocked"
        scene["last_feedback"] = "Quarantine ICE blocks a clean disconnect."
        state.active_scene = dict(scene)
        sim.emit(Event("wire_program_blocked", eid=actor_eid, reason=reason))
        return {"ok": False, "reason": reason}
    from game.wire_scene import close_wire_scene

    exit_kind = "dirty" if wire_alert_rank(scene) >= 2 else "clean"
    reason = "dirty_exit" if exit_kind == "dirty" else "clean_exit"
    return close_wire_scene(sim, actor_eid, reason=reason, disconnect=True, exit_kind=exit_kind)
