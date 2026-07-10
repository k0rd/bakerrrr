"""Executable WireScene programs, ICE, trace, and corruption helpers."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import blake2b

from engine.events import Event
from game.components import Inventory
from game.items import ITEM_CATALOG, item_display_name
from game.wire_kit import wire_state_for_actor
from game.wire_runtime import (
    normalize_wire_entry_metadata,
    normalize_wire_interface_metadata,
    wire_interface_profile_for_item,
    wire_profile_for_item,
)
from game.wire_visuals import wire_visual_for_kind


WIRE_COMBAT_SCHEMA_VERSION = 1

PROGRAM_ITEM_ID_BY_KEY = {
    "talk": "wire_talk_program",
    "route_probe": "wire_route_probe_program",
    "door_latch": "wire_door_latch_program",
    "camera_loop": "wire_camera_loop_program",
    "data_siphon_shell": "wire_data_siphon_shell_program",
    "spike": "wire_spike_program",
    "ice_cutter": "wire_ice_cutter_program",
    "trace_scrubber": "wire_trace_scrubber_program",
    "signal_cloak": "wire_signal_cloak_program",
    "panic_eject": "wire_panic_eject_program",
    "checksum_ward": "wire_checksum_ward_program",
    "sacrificial_shell": "wire_sacrificial_shell_program",
}

PROGRAM_SPECS = {
    "talk": {"target": "user", "label": "Talk", "range": 4},
    "route_probe": {"target": "scene", "label": "Route Probe", "range": 0},
    "door_latch": {"target": "node", "label": "Door Latch", "node_kinds": {"door_alarm_relay", "controller"}},
    "camera_loop": {"target": "node", "label": "Camera Loop", "node_kinds": {"controller", "diagnostic"}},
    "data_siphon_shell": {"target": "node", "label": "Data Siphon Shell", "node_kinds": {"records"}},
    "spike": {"target": "ice", "label": "Spike", "range": 10, "damage": 3},
    "ice_cutter": {"target": "ice", "label": "ICE Cutter", "range": 8, "damage": 5},
    "trace_scrubber": {"target": "self", "label": "Trace Scrubber", "trace_delta": -5},
    "signal_cloak": {"target": "self", "label": "Signal Cloak", "effect_turns": 4},
    "panic_eject": {"target": "self", "label": "Panic Eject"},
    "checksum_ward": {"target": "self", "label": "Checksum Ward"},
    "sacrificial_shell": {"target": "self", "label": "Sacrificial Shell"},
}

ICE_SPECS = {
    "camera_watchdog": {"label": "Camera Watchdog", "hp": 4, "trace": 2, "visual": "ice_camera_watchdog"},
    "door_arbiter": {"label": "Door Arbiter", "hp": 7, "buffer": 1, "visual": "ice_door_arbiter"},
    "trace_sentinel": {"label": "Trace Sentinel", "hp": 5, "trace": 3, "visual": "ice_trace_sentinel"},
    "compliance_daemon": {"label": "Compliance Daemon", "hp": 6, "trace": 1, "visual": "ice_compliance_daemon"},
    "quarantine_gate": {"label": "Quarantine Gate", "hp": 8, "trace": 1, "visual": "ice_quarantine_gate"},
    "corruptor": {"label": "Corruptor", "hp": 6, "buffer": 1, "visual": "ice_corruptor"},
}

OFFENSIVE_PROGRAMS = {"door_latch", "camera_loop", "data_siphon_shell", "spike", "ice_cutter"}


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
        "revealed": False,
    }


def _initial_ice_entities(scene, *, security=1):
    nodes = list(scene.get("nodes", ()) or ())
    target_class = _clean_key(scene.get("target_class"))
    scene_id = _clean_text(scene.get("scene_id"))
    security = _int(security, 1, minimum=0)
    rows = []
    dx, dy = _entity_at_node(nodes, "diagnostic")
    rows.append(_ice_entity(scene, "camera_watchdog", "ice-watchdog-1", dx, dy))
    if target_class == "access_panel":
        rx, ry = _entity_at_node(nodes, "door_alarm_relay")
        rows.append(_ice_entity(scene, "door_arbiter", "ice-arbiter-1", rx, ry))
    else:
        sx, sy = _entity_at_node(nodes, "service_index")
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


def initialize_wire_combat_scene(scene, *, interface_metadata=None, security=1):
    if not isinstance(scene, dict):
        return scene
    interface_metadata = dict(interface_metadata or {})
    security = _int(security or scene.get("security_tier"), 1, minimum=0)
    trace_resistance = _int(interface_metadata.get("trace_resistance"), 0, minimum=0)
    buffer_max = max(1, _int(interface_metadata.get("buffer_size"), 4, minimum=1))
    initial_trace = max(0, _int(interface_metadata.get("noise_floor"), 0, minimum=0) + max(0, security - 1))
    scene.setdefault("wire_combat_schema_version", WIRE_COMBAT_SCHEMA_VERSION)
    scene["security_tier"] = security
    scene.setdefault("buffer_max", buffer_max)
    scene.setdefault("buffer_current", _int(scene.get("buffer_current"), scene["buffer_max"], minimum=0))
    scene.setdefault("trace_limit", 12 + trace_resistance * 4)
    scene.setdefault("trace_current", initial_trace)
    scene.setdefault("trace_alert_level", "quiet")
    scene.setdefault("active_effects", [])
    scene.setdefault("program_cooldowns", {})
    scene.setdefault("last_program_result", {})
    scene.setdefault("combat_log", [])
    scene.setdefault("clean_exit_blocked", False)
    scene.setdefault("ejection_state", {})
    scene.setdefault("wire_turn_index", 0)
    scene.setdefault("last_hostile_program_instance_id", "")
    scene["interface_memory_speed"] = _memory_speed(interface_metadata)
    if not scene.get("wire_entities_initialized"):
        scene["wire_entities"] = _initial_ice_entities(scene, security=security)
        scene["wire_entities_initialized"] = True
    else:
        scene.setdefault("wire_entities", [])
    _refresh_clean_exit_block(scene)
    _refresh_trace_alert(scene)
    return scene


def ensure_wire_combat_state(sim, actor_eid, *, item_catalog=None):
    state = wire_state_for_actor(sim, actor_eid, create=False)
    if state is None or not isinstance(getattr(state, "active_scene", None), Mapping):
        return None
    scene = dict(state.active_scene)
    _item_id, interface_metadata = _interface_metadata(sim, actor_eid, scene, item_catalog=item_catalog)
    program_slots = _int(interface_metadata.get("program_slots"), getattr(state, "program_slots", 2), minimum=0)
    state.program_slots = program_slots
    normalize_wire_ram_slots(state, item_catalog=item_catalog)
    if len(getattr(state, "ram_slots", ()) or ()) > 0 and wire_ram_used_points(state, item_catalog=item_catalog) > program_slots:
        while state.ram_slots and wire_ram_used_points(state, item_catalog=item_catalog) > program_slots:
            state.ram_slots.pop()
    initialize_wire_combat_scene(scene, interface_metadata=interface_metadata, security=scene.get("security_tier", 1))
    state.active_scene = scene
    return scene


def load_wire_program_to_ram(sim, actor_eid, instance_id=None, *, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    state = wire_state_for_actor(sim, actor_eid, create=True)
    scene = ensure_wire_combat_state(sim, actor_eid, item_catalog=item_catalog)
    if scene is None:
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
    for entry in candidates:
        if not _is_program_entry(entry, item_catalog=item_catalog):
            continue
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
        sim.emit(Event(
            "wire_program_loaded",
            eid=actor_eid,
            item_id=clean.get("item_id"),
            instance_id=clean.get("instance_id"),
            program_key=_program_key_for_item(clean.get("item_id"), item_catalog=item_catalog),
            program_name=_program_name(clean, item_catalog=item_catalog),
        ))
        return {"ok": True, "reason": None, "entry": dict(clean)}
    reason = "ram_full" if candidates else "no_program_available"
    sim.emit(Event("wire_program_blocked", eid=actor_eid, reason=reason))
    return {"ok": False, "reason": reason}


def unload_wire_ram_slot(sim, actor_eid, *, index=None, instance_id=None, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    state = wire_state_for_actor(sim, actor_eid, create=False)
    if state is None:
        return {"ok": False, "reason": "missing_wire_state"}
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
    ensure_wire_combat_state(sim, actor_eid, item_catalog=item_catalog)
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
        suffix = f"cd {cooldown}, dur {durability}"
        if runs_max:
            suffix += f", runs {runs}/{runs_max}"
        rows.append({
            "index": idx,
            "instance_id": _clean_text(entry.get("instance_id")),
            "item_id": _clean_key(entry.get("item_id")),
            "program_key": key,
            "entry": dict(entry),
            "label": f"{_program_name(entry, item_catalog=item_catalog)} [{suffix}]",
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
        entities = _live_ice_entities(scene)
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
    if trace >= limit:
        level = "forced"
    elif trace >= int(limit * 0.75):
        level = "hot"
    elif trace >= int(limit * 0.45):
        level = "rising"
    else:
        level = "quiet"
    scene["trace_alert_level"] = level
    scene["trace"] = f"{trace}/{limit} {level}"
    scene["buffer"] = f"{_int(scene.get('buffer_current'), 0)}/{_int(scene.get('buffer_max'), 1)}"


def _add_trace(sim, actor_eid, scene, amount, *, reason="wire_action"):
    amount = int(amount)
    if amount == 0:
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


def _append_effect(scene, kind, *, turns=1, instance_id=""):
    effects = [dict(effect) for effect in scene.get("active_effects", ()) or () if isinstance(effect, Mapping)]
    effects.append({"kind": _clean_key(kind), "turns": max(1, int(turns)), "instance_id": _clean_text(instance_id)})
    scene["active_effects"] = effects


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
        if _clean_key(entity.get("kind")) == "quarantine_gate":
            blocked = True
        if "quarantine_anchor" in tuple(entity.get("traits", ()) or ()):
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


def advance_wire_combat_turn(sim, actor_eid, *, cause="action", skip_cooldown_instance_id="", item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    state = wire_state_for_actor(sim, actor_eid, create=False)
    if state is None or not isinstance(getattr(state, "active_scene", None), Mapping):
        return {"ok": False, "reason": "missing_scene"}
    scene = ensure_wire_combat_state(sim, actor_eid, item_catalog=item_catalog)
    if scene is None:
        return {"ok": False, "reason": "missing_scene"}
    scene["wire_turn_index"] = _int(scene.get("wire_turn_index"), 0, minimum=0) + 1
    _decrement_ram_cooldowns(state, skip_instance_id=skip_cooldown_instance_id, item_catalog=item_catalog)
    _decrement_effects(scene)
    security = _scene_security(scene)
    passive = max(1, security)
    if _effect_active(scene, "signal_cloak"):
        passive = max(0, passive - 1)
    _add_trace(sim, actor_eid, scene, passive, reason=f"passive_{cause}")
    memory_speed = _int(scene.get("interface_memory_speed"), 1, minimum=0)
    for entity in _live_ice_entities(scene):
        kind = _clean_key(entity.get("kind"))
        spec = ICE_SPECS.get(kind, {})
        trace = _int(spec.get("trace"), 0, minimum=0)
        buffer_damage = _int(spec.get("buffer"), 0, minimum=0)
        if _effect_active(scene, "signal_cloak"):
            trace = max(0, trace - 1)
            buffer_damage = max(0, buffer_damage - 1)
        traits = tuple(entity.get("traits", ()) or ())
        if "memory_speed_trace" in traits:
            trace += max(1, memory_speed // 2)
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
                    break
            if healed:
                trace = 0
        if kind == "quarantine_gate":
            scene["clean_exit_blocked"] = True
        if kind == "corruptor":
            target_iid = _clean_text(scene.get("last_hostile_program_instance_id"))
            if target_iid:
                _damage_program(sim, actor_eid, state, scene, target_iid, reason="corruptor", item_catalog=item_catalog)
                buffer_damage = 0
        if "ram_reset_attack" in traits:
            _reset_ram(sim, actor_eid, state, scene, item_catalog=item_catalog)
        if trace:
            _add_trace(sim, actor_eid, scene, trace, reason=f"ice_{kind}")
        if buffer_damage:
            _add_buffer_damage(sim, actor_eid, scene, buffer_damage, reason=f"ice_{kind}")
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
    metadata["ram_reload_ticks_remaining"] = _int(profile.get("reload_ticks"), 0, minimum=0)
    durability = _int(metadata.get("durability"), profile.get("durability_max", 1), minimum=0)
    metadata["durability"] = max(0, durability - 1)
    runs_max = _int(metadata.get("runs_max"), profile.get("runs_max", 0), minimum=0)
    if runs_max:
        metadata["runs"] = max(0, _int(metadata.get("runs"), runs_max, minimum=0) - 1)
    entry["metadata"] = metadata
    _set_ram_entry(state, entry, item_catalog=item_catalog)


def _active_trait(scene, trait):
    needle = _clean_key(trait)
    for entity in _live_ice_entities(scene):
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
    if program_key in {"door_latch", "camera_loop", "data_siphon_shell"}:
        from game.wire_consequences import wire_physical_effect_preflight

        preflight = wire_physical_effect_preflight(sim, scene, program_key)
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
                item_catalog=item_catalog,
            )
            if not data_preflight.get("ok"):
                reason = str(data_preflight.get("reason", "blocked") or "blocked")
                sim.emit(Event("wire_program_blocked", eid=actor_eid, reason=reason, program_key=program_key))
                return {"ok": False, "reason": reason}

    trace_add = _int(metadata.get("trace_cost"), profile.get("trace_cost", 0), minimum=0)
    trace_add += _int(metadata.get("noise"), profile.get("noise", 0), minimum=0)
    if _active_trait(scene, "blackbox_auditor") and program_key in OFFENSIVE_PROGRAMS:
        trace_add += 1
    _add_trace(sim, actor_eid, scene, trace_add, reason=f"program_{program_key}")
    feedback = f"{PROGRAM_SPECS.get(program_key, {}).get('label', program_key)} runs."
    forced_disconnect_after_run = False
    if program_key == "route_probe":
        entities = []
        for entity in _live_ice_entities(scene):
            entity["revealed"] = True
            _set_entity(scene, entity)
            traits = ", ".join(entity.get("traits", ()) or ()) or "standard"
            entities.append(f"{_entity_label(entity)} [{traits}]")
        feedback = "Route probe reveals " + (", ".join(entities) if entities else "no active ICE") + "."
    elif program_key in {"spike", "ice_cutter"}:
        entity = dict(resolved_target.get("entity") or {})
        damage = _int(PROGRAM_SPECS[program_key].get("damage"), 1)
        if program_key == "ice_cutter" and _clean_key(entity.get("kind")) not in {"quarantine_gate", "door_arbiter"}:
            damage = max(2, damage - 1)
        _damage_ice(sim, actor_eid, scene, entity, damage, program_key=program_key)
        scene["last_hostile_program_instance_id"] = _clean_text(entry.get("instance_id"))
        feedback = f"{PROGRAM_SPECS[program_key]['label']} hits {_entity_label(entity)} for {damage}."
    elif program_key == "trace_scrubber":
        _add_trace(sim, actor_eid, scene, _int(PROGRAM_SPECS[program_key].get("trace_delta"), -5), reason="trace_scrubber")
        feedback = "Trace scrubber drags the trace back."
    elif program_key == "signal_cloak":
        _append_effect(scene, "signal_cloak", turns=PROGRAM_SPECS[program_key].get("effect_turns", 4), instance_id=entry.get("instance_id"))
        feedback = "Signal cloak softens the link signature."
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
    elif program_key == "data_siphon_shell":
        from game.wire_consequences import apply_wire_physical_effect
        from game.wire_data_market import extract_wire_data_cache

        effect = apply_wire_physical_effect(sim, actor_eid, scene, program_key, target=resolved_target)
        extraction = extract_wire_data_cache(sim, actor_eid, scene, target=resolved_target, item_catalog=item_catalog)
        scene["data_siphon_primed"] = True
        scene["last_hostile_program_instance_id"] = _clean_text(entry.get("instance_id"))
        forced_disconnect_after_run = bool(effect.get("forced_disconnect"))
        if extraction.get("ok"):
            extracted = extraction.get("entry") if isinstance(extraction.get("entry"), Mapping) else {}
            display_name = str((extracted.get("metadata") or {}).get("display_name", "data cache") or "data cache")
            scene["last_data_cache_instance_id"] = extracted.get("instance_id")
            feedback = f"Data siphon shell pulls {display_name}."
        else:
            feedback = str(effect.get("feedback", "Data siphon shell dirties the records surface.") or "")
    elif program_key == "talk":
        from game.wire_users import open_wire_dialogue

        dialogue = open_wire_dialogue(sim, actor_eid, scene, resolved_target)
        if not dialogue.get("ok"):
            reason = str(dialogue.get("reason", "wire_user_refused") or "wire_user_refused")
            sim.emit(Event("wire_program_blocked", eid=actor_eid, reason=reason, program_key=program_key))
            return {"ok": False, "reason": reason}
        feedback = str(dialogue.get("feedback", "Talk channel open.") or "Talk channel open.")

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
    ))
    if forced_disconnect_after_run:
        scene["ejection_state"] = {
            "kind": "forced",
            "reason": "wire_network_locked",
            "trace": scene.get("trace_current"),
            "trace_limit": scene.get("trace_limit"),
            "buffer": scene.get("buffer_current"),
            "tick": int(getattr(sim, "tick", 0)),
        }
        state.last_ejection_state = dict(scene["ejection_state"])
        from game.wire_scene import close_wire_scene

        close_wire_scene(sim, actor_eid, reason="wire_network_locked", disconnect=True)
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
    if _refresh_clean_exit_block(scene):
        reason = "clean_exit_blocked"
        scene["last_feedback"] = "Quarantine ICE blocks a clean disconnect."
        state.active_scene = dict(scene)
        sim.emit(Event("wire_program_blocked", eid=actor_eid, reason=reason))
        return {"ok": False, "reason": reason}
    from game.wire_scene import close_wire_scene

    return close_wire_scene(sim, actor_eid, reason="manual", disconnect=True)
