"""Bounded local WireScene projection for hacking traversal."""

from __future__ import annotations

from collections.abc import Mapping

from engine.events import Event
from game.components import Inventory, Position
from game.items import ITEM_CATALOG, item_display_name
from game.wire_combat import advance_wire_combat_turn, initialize_wire_combat_scene
from game.wire_kit import wire_state_for_actor
from game.wire_runtime import normalize_wire_interface_metadata, wire_interface_profile_for_item
from game.wire_users import seed_wire_users_for_scene
from game.wire_visuals import apply_wire_scene_visuals, wire_scene_hud_lines
from game.wire_targets import (
    resolve_wire_target,
    wire_target_has_live_radio,
    wire_target_identity,
    wire_target_ref_from_connection,
)


WIRE_SCENE_SCHEMA_VERSION = 1
WIRE_SCENE_WIDTH = 27
WIRE_SCENE_HEIGHT = 15


def _clean_text(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _clean_id(value):
    return _clean_text(value).lower()


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _prop_metadata(prop):
    return dict(prop.get("metadata") or {}) if isinstance(prop, Mapping) and isinstance(prop.get("metadata"), Mapping) else {}


def _prop_name(prop, default="wire target"):
    if not isinstance(prop, Mapping):
        return str(default)
    return _clean_text(prop.get("name"), default)


def _actor_position(sim, actor_eid):
    return sim.ecs.get(Position).get(actor_eid)


def _inventory_entry(sim, actor_eid, instance_id):
    instance_key = _clean_text(instance_id)
    if not instance_key:
        return None
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if inventory is None:
        return None
    return inventory.find(instance_id=instance_key)


def _interface_snapshot(sim, actor_eid, connection, *, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    instance_id = _clean_text((connection or {}).get("interface_instance_id"))
    entry = _inventory_entry(sim, actor_eid, instance_id)
    item_id = _clean_id((entry or {}).get("item_id") or (connection or {}).get("interface_item_id"))
    profile = wire_interface_profile_for_item(item_id, item_catalog=item_catalog)
    metadata = normalize_wire_interface_metadata(
        dict((entry or {}).get("metadata") or {}),
        item_id=item_id,
        profile=profile,
    ) if item_id else {}
    return {
        "instance_id": instance_id,
        "item_id": item_id,
        "name": item_display_name(item_id, metadata=metadata, item_catalog=item_catalog) if item_id else "interface",
        "style": _clean_text(metadata.get("style") or profile.get("style"), "plain").lower(),
        "manufacturer": _clean_text(metadata.get("manufacturer") or profile.get("manufacturer"), "unknown"),
        "theme_profile": dict(metadata.get("organization_theme") or {}) if isinstance(metadata.get("organization_theme"), Mapping) else {},
        "diagnostic_voice": dict(metadata.get("diagnostic_voice") or {}) if isinstance(metadata.get("diagnostic_voice"), Mapping) else {},
        "metadata": metadata,
    }


def _diagnostic_lines(interface, security):
    voice = dict(interface.get("diagnostic_voice") or {})
    manufacturer = _clean_text(interface.get("manufacturer"), "unknown maker")
    style = _clean_text(interface.get("style"), "plain")
    metadata = dict(interface.get("metadata") or {})
    motif = _clean_text(metadata.get("product_motif"), "unmarked traces")
    register = _clean_id(voice.get("register") or "procedural")
    address = _clean_text(voice.get("address"), "operator")
    warning_style = _clean_text(voice.get("warning_style"), "state the consequence")
    openers = {
        "clipped": f"READ, {address.upper()}:",
        "neighborly": f"Easy, {address}:",
        "procedural": f"Protocol for {address}:",
        "ceremonial": f"Attend, {address}:",
        "blunt": f"Look, {address}:",
        "aspirational": f"Advance with us, {address}:",
        "solicitous": f"For your assurance, {address}:",
        "wry": f"Funny thing, {address}:",
        "austere": f"Notice, {address}:",
        "breathless": f"Good news, {address}:",
        "measured": f"Current read, {address}:",
        "proprietary": f"Authorized {manufacturer} read:",
        "plainspoken": f"Here's the wire, {address}:",
        "evangelical": f"Receive the signal, {address}:",
    }
    opener = openers.get(register, f"Signal for {address}:")
    first = f"{opener} {manufacturer} resolves {style} through {motif}."
    warnings = {
        "state the consequence": f"Tier {security} security will answer a bad handshake.",
        "offer one clean exit": f"Tier {security} security is awake; a clean exit remains available.",
        "cite the rule": f"Rule {security}: warning confidence follows the connected interface.",
        "make the risk personal": f"Tier {security} is measuring your mistakes, {address}.",
        "bury the threat in courtesy": f"For continued service, kindly respect tier {security} security.",
        "challenge the listener": f"Tier {security} security invites you to prove the route clean.",
        "repeat the boundary": f"Tier {security}. The boundary is tier {security}. Read it twice.",
        "frame compliance as belonging": f"Those who belong here move cleanly under tier {security} security.",
    }
    return [first, warnings.get(warning_style, f"Security read: tier {security}.")]


def _scene_id(sim, actor_eid, connection, target, interface):
    seed = _clean_text(getattr(sim, "seed", ""), "seed")
    target_seed = _clean_text((target or {}).get("identity") or (connection or {}).get("target_identity"))
    if _clean_id((target or {}).get("kind")) == "property":
        target_prop = (target or {}).get("property") if isinstance((target or {}).get("property"), Mapping) else {}
        target_seed = _clean_text(target_prop.get("id"), target_seed)
    return ":".join((
        "wire",
        str(seed),
        str(actor_eid),
        target_seed,
        _clean_text((connection or {}).get("target_class")),
        _clean_text((connection or {}).get("linked_property_id")),
        _clean_text((interface or {}).get("instance_id") or (interface or {}).get("item_id")),
    ))


def _node(node_id, kind, x, y, label, read_lines, *, glyph="?"):
    return {
        "node_id": str(node_id),
        "kind": str(kind),
        "x": int(x),
        "y": int(y),
        "label": str(label),
        "glyph": str(glyph or "?")[:1],
        "read_lines": [str(line) for line in (read_lines or ())],
    }


def _path_points(ax, ay, bx, by):
    points = []
    x = int(ax)
    y = int(ay)
    bx = int(bx)
    by = int(by)
    step_x = 1 if bx >= x else -1
    while x != bx:
        points.append((x, y))
        x += step_x
    step_y = 1 if by >= y else -1
    while y != by:
        points.append((x, y))
        y += step_y
    points.append((bx, by))
    return points


def _build_walkable(nodes, edges):
    by_id = {str(node.get("node_id")): node for node in nodes if isinstance(node, Mapping)}
    points = set()
    for node in by_id.values():
        points.add((int(node.get("x", 0)), int(node.get("y", 0))))
    for left, right in edges:
        a = by_id.get(str(left))
        b = by_id.get(str(right))
        if not a or not b:
            continue
        points.update(_path_points(a["x"], a["y"], b["x"], b["y"]))
    return sorted(points)


def _node_at(scene, x, y):
    for node in scene.get("nodes", ()) or ():
        if not isinstance(node, Mapping):
            continue
        if int(node.get("x", -999)) == int(x) and int(node.get("y", -999)) == int(y):
            return dict(node)
    return None


def _scene_walkable_set(scene):
    return {
        (int(point[0]), int(point[1]))
        for point in (scene.get("walkable") or ())
        if isinstance(point, (list, tuple)) and len(point) >= 2
    }


def build_wire_scene(sim, actor_eid, prop=None, *, target=None, item_catalog=None):
    """Build a deterministic bounded wire scene from an active connection."""

    state = wire_state_for_actor(sim, actor_eid, create=True)
    connection = getattr(state, "active_connection", None)
    if not isinstance(connection, Mapping):
        return {"ok": False, "reason": "not_connected"}
    if not isinstance(target, Mapping):
        target = resolve_wire_target(sim, wire_target_ref_from_connection(connection))
        if not isinstance(target, Mapping):
            return {"ok": False, "reason": "target_unavailable"}
        if isinstance(prop, Mapping) and _clean_text((target.get("property") or {}).get("id")) != _clean_text(prop.get("id")):
            return {"ok": False, "reason": "connection_target_mismatch"}
    target_ref = dict(target.get("ref") or {})
    target_identity = _clean_text(target.get("identity") or wire_target_identity(target_ref))
    connection_identity = _clean_text(connection.get("target_identity") or wire_target_identity(wire_target_ref_from_connection(connection)))
    if not target_identity or target_identity != connection_identity:
        return {"ok": False, "reason": "connection_target_mismatch"}
    pos = _actor_position(sim, actor_eid)
    if pos is None:
        return {"ok": False, "reason": "missing_body"}

    target_class = _clean_id(connection.get("target_class"))
    target_kind = _clean_id(target.get("kind") or "property")
    target_name = _clean_text(target.get("name"), target_class.replace("_", " ") or "wire target")
    metadata = dict(target.get("metadata") or {})
    prop = target.get("property") if isinstance(target.get("property"), Mapping) else {}
    target_property_id = _clean_text(prop.get("id"))
    target_entity_id = target.get("drone_eid") if target_kind == "drone" else None
    linked_id = _clean_text(connection.get("linked_property_id") or target.get("linked_property_id") or metadata.get("linked_property_id"))
    linked_prop = getattr(sim, "properties", {}).get(str(linked_id)) if linked_id else None
    linked_metadata = _prop_metadata(linked_prop)
    linked_name = _prop_name(linked_prop, "linked site") if isinstance(linked_prop, Mapping) else "linked site"
    archetype = _clean_text(
        metadata.get("archetype")
        or metadata.get("service_archetype")
        or linked_metadata.get("archetype")
        or linked_metadata.get("service_archetype"),
        "local system",
    )
    linked_archetype = _clean_text(
        linked_metadata.get("archetype")
        or linked_metadata.get("service_archetype"),
        "",
    )
    source_org_key = _clean_text(
        linked_metadata.get("organization_key")
        or linked_metadata.get("org_key")
        or linked_metadata.get("faction_key")
        or metadata.get("organization_key")
        or metadata.get("org_key")
        or prop.get("owner_tag")
        or metadata.get("owner_tag")
    )
    source_org_name = _clean_text(
        linked_metadata.get("organization_name")
        or linked_metadata.get("org_name")
        or linked_metadata.get("faction_name")
        or metadata.get("organization_name")
        or metadata.get("org_name")
        or source_org_key
    )
    security = _int(metadata.get("security_tier") or linked_metadata.get("security_tier") or metadata.get("security") or linked_metadata.get("security"), 1)
    interface = _interface_snapshot(sim, actor_eid, connection, item_catalog=item_catalog)

    mid = WIRE_SCENE_HEIGHT // 2
    service_words = {
        str(service).strip().lower()
        for service in tuple(metadata.get("finance_services", ()) or ())
        + tuple(metadata.get("site_services", ()) or ())
        + tuple(prop.get("services", ()) or ())
        if str(service).strip()
    }
    is_atm_surface = (
        _clean_id(metadata.get("fixture_type")) in {"atm_kiosk", "banking_kiosk"}
        or _clean_id(metadata.get("archetype")) in {"atm_kiosk", "banking_kiosk"}
        or "banking" in service_words
    )
    if target_kind == "drone":
        branch_kind = "sensor_relay"
        branch_label = "sensor/radio relay"
        module_ids = tuple(metadata.get("module_ids", ()) or ())
        sensor_labels = [
            str(module_id).replace("drone_", "").replace("_module", "").replace("_", " ")
            for module_id in module_ids
            if any(word in str(module_id) for word in ("camera", "sensor", "radar", "lidar", "sonar", "thermal", "radio", "comms"))
        ]
        procedure = _clean_text(metadata.get("procedure_program_id") or metadata.get("procedure_key"), "idle").replace("_", " ")
        branch_read = [
            f"The radio relay exposes {', '.join(sensor_labels) if sensor_labels else 'a minimal command link'}.",
            f"The current routine reports as {procedure}; controller identity remains outside the public handshake.",
        ]
    elif target_kind == "vehicle":
        branch_kind = "vehicle_lock_bus"
        branch_label = "lock controller"
        branch_read = [
            f"{target_name} exposes a local lock controller at the service bus.",
            "The public diagnostic does not disclose an owner identity or grant an ignition credential.",
        ]
    elif target_class == "service_terminal" and is_atm_surface:
        branch_kind = "service_index"
        branch_label = "banking mask"
        branch_read = [
            f"{target_name} presents a synthetic banking mask for ordinary transfers.",
            "Face-to-face wire sessions are common for large or sensitive banking work.",
            "Breaking past the mask requires program action; the polite terminal does not volunteer its deeper layer.",
        ]
    elif target_class == "service_terminal":
        branch_kind = "service_index"
        branch_label = "service index"
        branch_read = [
            f"{target_name} exposes service rows for {archetype}.",
            "The public index is readable; deeper service actions require a matching program and controller route.",
        ]
    else:
        branch_kind = "door_alarm_relay"
        branch_label = "door/alarm relay"
        branch_read = [
            f"The relay references {linked_name}.",
            "Door and camera routes accept matching utility programs; broader alarm control remains isolated.",
        ]

    secondary_kind = "vehicle_tracker" if target_kind == "vehicle" else "records"
    secondary_label = "tracker controller" if target_kind == "vehicle" else "records node"
    secondary_read = (
        [
            "The tracker controller exposes installed/active state only.",
            "No route history, remote coordinates, or unloaded-world location is available from this local read.",
        ]
        if target_kind == "vehicle"
        else [
            f"Local records point toward {linked_name}.",
            "Data siphon programs can pull one bounded packet from this surface.",
        ]
    )
    nodes = [
        _node(
            "entry",
            "entry",
            2,
            mid,
            "entry jack",
            [
                f"{interface['name']} resolves a local layer for {target_name}.",
                "Your body remains outside the wire.",
            ],
            glyph=">",
        ),
        _node(
            "diagnostic",
            "diagnostic",
            8,
            mid - 3,
            "diagnostic node",
            _diagnostic_lines(interface, security),
            glyph="?",
        ),
        _node(
            "controller",
            "controller",
            14,
            mid,
            "controller node",
            [
                f"Controller surface: {target_class.replace('_', ' ') or 'wire target'}.",
                (
                    "The handshake exposes diagnostics and bounded controller routes."
                    if target_kind == "drone"
                    else "The local bus exposes authenticated service routes without changing vehicle ownership."
                    if target_kind == "vehicle"
                    else "Controller effects require a matching utility program."
                ),
            ],
            glyph="C",
        ),
        _node(branch_kind, branch_kind, 20, mid - 3, branch_label, branch_read, glyph="R"),
        _node(
            secondary_kind,
            secondary_kind,
            20,
            mid if target_kind == "vehicle" else mid + 3,
            secondary_label,
            secondary_read,
            glyph="T" if target_kind == "vehicle" else "D",
        ),
        _node(
            "exit",
            "exit",
            24,
            mid,
            "exit route",
            ["Clean disconnect returns attention to the meat layer."],
            glyph="<",
        ),
    ]
    if target_kind == "vehicle":
        nodes.insert(-1, _node(
            "vehicle_ignition",
            "vehicle_ignition",
            20,
            mid + 4,
            "ignition controller",
            [
                "The ignition controller reports start readiness and active override state.",
                "Authenticated service may prime a short local authorization; it does not transfer title or create a reusable key.",
            ],
            glyph="I",
        ))
    edges = [
        ("entry", "diagnostic"),
        ("diagnostic", "controller"),
        ("controller", branch_kind),
        ("controller", secondary_kind),
        ("controller", "exit"),
    ]
    if target_kind == "vehicle":
        edges.insert(-1, ("controller", "vehicle_ignition"))
    walkable = _build_walkable(nodes, edges)
    scene = {
        "schema_version": WIRE_SCENE_SCHEMA_VERSION,
        "scene_id": _scene_id(sim, actor_eid, connection, target, interface),
        "target_ref": target_ref,
        "target_identity": target_identity,
        "target_kind": target_kind,
        "target_property_id": target_property_id,
        "target_entity_id": target_entity_id,
        "target_stable_id": _clean_text(target_ref.get("stable_id")),
        "target_class": target_class,
        "target_name": target_name,
        "linked_property_id": linked_id,
        "linked_name": linked_name,
        "interface_instance_id": interface.get("instance_id", ""),
        "interface_item_id": interface.get("item_id", ""),
        "interface_name": interface.get("name", "interface"),
        "interface_style": interface.get("style", "plain"),
        "interface_manufacturer": interface.get("manufacturer", "unknown"),
        "interface_theme_profile": dict(interface.get("theme_profile") or {}),
        "interface_diagnostic_voice": dict(interface.get("diagnostic_voice") or {}),
        "interface_range": _int((interface.get("metadata") or {}).get("range"), 1),
        "security_tier": int(security),
        "target_archetype": archetype,
        "linked_archetype": linked_archetype,
        "source_org_key": source_org_key,
        "source_org_name": source_org_name,
        "source_refs": {
            "body": {"x": int(pos.x), "y": int(pos.y), "z": int(pos.z)},
            "target_ref": target_ref,
            "target_identity": target_identity,
            "target_kind": target_kind,
            "target_property_id": target_property_id,
            "target_entity_id": target_entity_id,
            "target_stable_id": _clean_text(target_ref.get("stable_id")),
            "target_class": target_class,
            "linked_property_id": linked_id,
            "interface_instance_id": interface.get("instance_id", ""),
            "connected_tick": _int(connection.get("connected_tick"), int(getattr(sim, "tick", 0))),
        },
        "bounds": {"width": WIRE_SCENE_WIDTH, "height": WIRE_SCENE_HEIGHT},
        "avatar": {"x": 2, "y": mid},
        "home": {"x": 2, "y": mid},
        "nodes": nodes,
        "edges": [list(edge) for edge in edges],
        "walkable": [list(point) for point in walkable],
        "last_read_node_id": "entry",
        "last_read_lines": list(nodes[0]["read_lines"]),
        "last_feedback": "Wire layer open.",
        "opened_tick": int(getattr(sim, "tick", 0)),
    }
    apply_wire_scene_visuals(scene, security=security)
    initialize_wire_combat_scene(scene, interface_metadata=interface.get("metadata"), security=security)
    source_prop = prop if prop else {
        "id": target_identity,
        "name": target_name,
        "owner_tag": metadata.get("owner_tag"),
        "metadata": metadata,
    }
    seed_wire_users_for_scene(scene, sim=sim, source_prop=source_prop, linked_prop=linked_prop)
    return {"ok": True, "reason": None, "scene": scene}


def open_wire_scene(sim, actor_eid, prop, *, item_catalog=None):
    return _open_wire_scene_target(sim, actor_eid, prop=prop, item_catalog=item_catalog)


def _open_wire_scene_target(sim, actor_eid, *, prop=None, target=None, item_catalog=None):
    state = wire_state_for_actor(sim, actor_eid, create=True)
    result = build_wire_scene(sim, actor_eid, prop, target=target, item_catalog=item_catalog)
    if not result.get("ok"):
        reason = str(result.get("reason", "blocked") or "blocked")
        state.last_wire_feedback = f"Wire layer blocked: {reason.replace('_', ' ')}."
        sim.emit(Event("wire_scene_blocked", eid=actor_eid, reason=reason))
        return result
    scene = dict(result["scene"])
    state.active_scene = scene
    state.connection_status = "wire_scene"
    state.last_wire_feedback = "Wire layer open."
    ui = getattr(sim, "wire_scene_ui", None)
    if not isinstance(ui, dict):
        ui = {}
        sim.wire_scene_ui = ui
    ui.update({
        "open": True,
        "selected_node_id": "entry",
        "scroll": 0,
        "feedback": scene.get("last_feedback", "Wire layer open."),
        "status_lines": wire_scene_status_lines(scene),
    })
    shell = getattr(sim, "wire_connection_ui", None)
    if isinstance(shell, dict):
        shell["open"] = False
    sim.emit(Event(
        "wire_scene_entered",
        eid=actor_eid,
        scene_id=scene.get("scene_id"),
        target_name=scene.get("target_name"),
        target_class=scene.get("target_class"),
    ))
    return {"ok": True, "reason": None, "scene": scene}


def open_wire_scene_from_connection(sim, actor_eid, *, item_catalog=None):
    state = wire_state_for_actor(sim, actor_eid, create=True)
    connection = getattr(state, "active_connection", None)
    if not isinstance(connection, Mapping):
        return {"ok": False, "reason": "not_connected"}
    target = resolve_wire_target(sim, wire_target_ref_from_connection(connection))
    if not isinstance(target, Mapping):
        return {"ok": False, "reason": "target_unavailable"}
    return _open_wire_scene_target(sim, actor_eid, target=target, item_catalog=item_catalog)


def active_wire_scene(sim, actor_eid):
    state = wire_state_for_actor(sim, actor_eid, create=False)
    scene = getattr(state, "active_scene", None) if state is not None else None
    return dict(scene) if isinstance(scene, Mapping) else None


def wire_scene_status_lines(scene):
    if not isinstance(scene, Mapping):
        return []
    return wire_scene_hud_lines(scene)


def wire_scene_current_read(scene):
    if not isinstance(scene, Mapping):
        return []
    lines = list(scene.get("last_read_lines") or ())
    return [str(line) for line in lines]


def _scene_stale_reason(sim, actor_eid, scene):
    if not isinstance(scene, Mapping):
        return "missing_scene"
    pos = _actor_position(sim, actor_eid)
    if pos is None:
        return "missing_body"
    source_refs = scene.get("source_refs") if isinstance(scene.get("source_refs"), Mapping) else {}
    body = source_refs.get("body") if isinstance(source_refs.get("body"), Mapping) else {}
    if int(pos.z) != _int(body.get("z"), int(pos.z)):
        return "body_floor_changed"
    state = wire_state_for_actor(sim, actor_eid, create=False)
    active = getattr(state, "active_connection", None) if state is not None else None
    if not isinstance(active, Mapping):
        return "connection_lost"
    active_identity = _clean_text(active.get("target_identity") or wire_target_identity(wire_target_ref_from_connection(active)))
    scene_ref = scene.get("target_ref") if isinstance(scene.get("target_ref"), Mapping) else {}
    if not scene_ref and _clean_text(scene.get("target_property_id")):
        scene_ref = {
            "kind": "property",
            "property_id": scene.get("target_property_id"),
            "target_class": scene.get("target_class"),
        }
    scene_identity = _clean_text(scene.get("target_identity") or wire_target_identity(scene_ref))
    if not active_identity or active_identity != scene_identity:
        return "connection_target_mismatch"
    target_kind = _clean_id(scene.get("target_kind") or "property")
    if target_kind in {"property", "vehicle"}:
        prop = getattr(sim, "properties", {}).get(str(scene.get("target_property_id", "") or ""))
        if not isinstance(prop, Mapping):
            return "target_unloaded"
        try:
            dist = abs(int(pos.x) - int(prop.get("x", pos.x))) + abs(int(pos.y) - int(prop.get("y", pos.y)))
            if int(pos.z) != int(prop.get("z", pos.z)) or dist > 1:
                return "body_moved_away"
        except (TypeError, ValueError):
            return "body_moved_away"
    elif target_kind == "drone":
        target = resolve_wire_target(sim, scene.get("target_ref"))
        if not isinstance(target, Mapping):
            return "target_unloaded"
        if not wire_target_has_live_radio(target, tick=int(getattr(sim, "tick", 0) or 0)):
            return "target_radio_unavailable"
        try:
            dist = abs(int(pos.x) - int(target.get("x", pos.x))) + abs(int(pos.y) - int(target.get("y", pos.y)))
            range_limit = max(1, _int(scene.get("interface_range"), 1))
            if int(pos.z) != int(target.get("z", pos.z)) or dist > range_limit:
                return "target_out_of_range"
        except (TypeError, ValueError):
            return "target_out_of_range"
    return ""


def active_wire_scene_stale(sim, actor_eid):
    scene = active_wire_scene(sim, actor_eid)
    if not scene:
        return (False, "")
    reason = _scene_stale_reason(sim, actor_eid, scene)
    return (bool(reason), reason)


def close_wire_scene(sim, actor_eid, *, reason="manual", disconnect=True):
    state = wire_state_for_actor(sim, actor_eid, create=False)
    if state is None:
        return {"ok": False, "reason": "missing_wire_state"}
    had_scene = isinstance(getattr(state, "active_scene", None), Mapping)
    scene_id = state.active_scene.get("scene_id") if had_scene else None
    state.active_scene = None
    if disconnect:
        state.active_connection = None
        state.connection_status = "offline"
    elif state.active_connection is not None:
        state.connection_status = "shell_connected"
    ui = getattr(sim, "wire_scene_ui", None)
    if isinstance(ui, dict):
        ui["open"] = False
        ui["scroll"] = 0
    state.last_wire_feedback = "Wire layer closed." if had_scene else "No active wire scene."
    if had_scene:
        sim.emit(Event("wire_scene_exited", eid=actor_eid, scene_id=scene_id, reason=reason))
    return {"ok": True, "reason": None, "had_scene": had_scene}


def panic_exit_wire_scene(sim, actor_eid):
    scene = active_wire_scene(sim, actor_eid)
    state = wire_state_for_actor(sim, actor_eid, create=False)
    if state is not None:
        state.last_ejection_state = {
            "kind": "hard_panic",
            "reason": "manual",
            "scene_id": (scene or {}).get("scene_id"),
            "tick": int(getattr(sim, "tick", 0)),
        }
    sim.emit(Event(
        "wire_scene_panic_exit",
        eid=actor_eid,
        scene_id=(scene or {}).get("scene_id"),
        target_name=(scene or {}).get("target_name", ""),
    ))
    return close_wire_scene(sim, actor_eid, reason="panic", disconnect=True)


def move_wire_avatar(sim, actor_eid, dx, dy):
    dx = max(-1, min(1, _int(dx, 0)))
    dy = max(-1, min(1, _int(dy, 0)))
    if abs(dx) + abs(dy) != 1:
        return {"ok": False, "reason": "invalid_step"}
    state = wire_state_for_actor(sim, actor_eid, create=False)
    scene = getattr(state, "active_scene", None) if state is not None else None
    if not isinstance(scene, Mapping):
        return {"ok": False, "reason": "missing_scene"}
    stale, stale_reason = active_wire_scene_stale(sim, actor_eid)
    if stale:
        close_wire_scene(sim, actor_eid, reason=stale_reason, disconnect=True)
        return {"ok": False, "reason": stale_reason}
    bounds = scene.get("bounds") if isinstance(scene.get("bounds"), Mapping) else {}
    avatar = dict(scene.get("avatar") or {})
    new_x = _int(avatar.get("x"), 0) + dx
    new_y = _int(avatar.get("y"), 0) + dy
    width = _int(bounds.get("width"), WIRE_SCENE_WIDTH)
    height = _int(bounds.get("height"), WIRE_SCENE_HEIGHT)
    if new_x < 0 or new_y < 0 or new_x >= width or new_y >= height:
        reason = "bounds"
        scene["last_feedback"] = "The local layer ends there."
        sim.emit(Event("wire_scene_move_blocked", eid=actor_eid, reason=reason))
        return {"ok": False, "reason": reason}
    if (new_x, new_y) not in _scene_walkable_set(scene):
        reason = "closed_route"
        scene["last_feedback"] = "No route resolves there."
        sim.emit(Event("wire_scene_move_blocked", eid=actor_eid, reason=reason))
        return {"ok": False, "reason": reason}
    scene["avatar"] = {"x": int(new_x), "y": int(new_y)}
    node = _node_at(scene, new_x, new_y)
    if node:
        scene["last_read_node_id"] = node.get("node_id")
        scene["last_read_lines"] = list(node.get("read_lines", ()))
        scene["last_feedback"] = f"At {node.get('label', 'node')}."
    else:
        scene["last_feedback"] = "Moving through signal path."
    state.active_scene = dict(scene)
    advance_wire_combat_turn(sim, actor_eid, cause="move")
    sim.emit(Event(
        "wire_scene_moved",
        eid=actor_eid,
        scene_id=scene.get("scene_id"),
        x=new_x,
        y=new_y,
        node_id=(node or {}).get("node_id", ""),
        node_label=(node or {}).get("label", ""),
    ))
    return {"ok": True, "reason": None, "scene": dict(scene), "node": node}


def wait_wire_scene(sim, actor_eid):
    scene = active_wire_scene(sim, actor_eid)
    if not scene:
        return {"ok": False, "reason": "missing_scene"}
    stale, stale_reason = active_wire_scene_stale(sim, actor_eid)
    if stale:
        close_wire_scene(sim, actor_eid, reason=stale_reason, disconnect=True)
        return {"ok": False, "reason": stale_reason}
    state = wire_state_for_actor(sim, actor_eid, create=False)
    scene["last_feedback"] = "You hold the connection open."
    if state is not None:
        state.active_scene = dict(scene)
    advance_wire_combat_turn(sim, actor_eid, cause="wait")
    sim.emit(Event("wire_scene_waited", eid=actor_eid, scene_id=scene.get("scene_id")))
    return {"ok": True, "reason": None, "scene": scene}


def read_wire_scene_node(sim, actor_eid):
    state = wire_state_for_actor(sim, actor_eid, create=False)
    scene = getattr(state, "active_scene", None) if state is not None else None
    if not isinstance(scene, Mapping):
        return {"ok": False, "reason": "missing_scene", "lines": []}
    avatar = scene.get("avatar") if isinstance(scene.get("avatar"), Mapping) else {}
    node = _node_at(scene, avatar.get("x", 0), avatar.get("y", 0))
    if node:
        lines = list(node.get("read_lines", ()))
        scene["last_read_node_id"] = node.get("node_id")
        scene["last_read_lines"] = lines
        scene["last_feedback"] = f"Read {node.get('label', 'node')}."
    else:
        lines = ["Signal path. Nothing executable is exposed here yet."]
        scene["last_read_lines"] = lines
        scene["last_feedback"] = "Read signal path."
    state.active_scene = dict(scene)
    sim.emit(Event(
        "wire_scene_read",
        eid=actor_eid,
        scene_id=scene.get("scene_id"),
        node_id=(node or {}).get("node_id", ""),
        node_label=(node or {}).get("label", "signal path"),
    ))
    return {"ok": True, "reason": None, "lines": [str(line) for line in lines], "node": node}
