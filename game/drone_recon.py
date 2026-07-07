"""Linked camera and recon helpers for deployed drones."""

from __future__ import annotations

from engine.visibility import observer_visible_positions, visibility_state

from game.components import CreatureIdentity, DroneState, Position, Vitality
from game.drone_runtime import (
    drone_profile_for_item,
    drone_state_capabilities,
    drone_state_controlled_by_actor,
    drone_state_has_capability,
)
from game.system_support.fire_runtime import fire_cell_state


DRONE_LINKED_CAMERA_RADIUS = 8
DRONE_SENSOR_DEFAULT_RANGES = {
    "camera": DRONE_LINKED_CAMERA_RADIUS,
    "radar": 14,
    "lidar": 8,
    "sonar": 6,
    "ir": 6,
}
DRONE_LINKED_SENSOR_PRIORITY = ("camera", "radar", "lidar", "sonar", "ir")
DRONE_MAPPING_SENSOR_PRIORITY = ("radar", "lidar", "sonar", "camera")


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _loaded(sim, x, y, z=0):
    chunk_detail = getattr(sim, "chunk_detail", None)
    chunk_coords = getattr(sim, "chunk_coords", None)
    if isinstance(chunk_detail, dict) and callable(chunk_coords):
        chunk = chunk_coords(int(x), int(y))
        if chunk in chunk_detail:
            return str(chunk_detail.get(chunk, "")).strip().lower() != "unloaded"
    detail_for_xy = getattr(sim, "detail_for_xy", None)
    if not callable(detail_for_xy):
        return True
    if str(detail_for_xy(int(x), int(y))).strip().lower() != "unloaded":
        return True
    tilemap = getattr(sim, "tilemap", None)
    tile_at = getattr(tilemap, "tile_at", None)
    return bool(callable(tile_at) and tile_at(int(x), int(y), int(z)) is not None)


def _grid_distance(ax, ay, bx, by):
    return max(abs(int(ax) - int(bx)), abs(int(ay) - int(by)))


def _line_points(ax, ay, bx, by):
    x0 = int(ax)
    y0 = int(ay)
    x1 = int(bx)
    y1 = int(by)
    points = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = err * 2
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
    return tuple(points)


def _opaque_depth_between(sim, ax, ay, az, bx, by, bz):
    if int(az) != int(bz):
        return 10**6
    depth = 0
    for px, py in _line_points(ax, ay, bx, by)[1:-1]:
        if not _loaded(sim, px, py, az):
            return 10**6
        tile = sim.tilemap.tile_at(px, py, az)
        if tile and not bool(getattr(tile, "transparent", True)):
            depth += 1
    return int(depth)


def _module_sensor_mode(module, *, item_catalog=None):
    if not isinstance(module, dict):
        return None
    item_id = str(module.get("item_id", "") or "").strip().lower()
    profile = drone_profile_for_item(item_id, item_catalog=item_catalog)
    if profile.get("kind") != "module":
        return None
    capabilities = {
        str(value or "").strip().lower()
        for value in tuple(profile.get("capabilities", ()) or ())
        if str(value or "").strip()
    }
    sensor_kind = str(profile.get("sensor_kind", "") or "").strip().lower()
    if not sensor_kind:
        if "camera" in capabilities or "visual_identity_sensor" in capabilities:
            sensor_kind = "camera"
        elif "radar" in capabilities:
            sensor_kind = "radar"
        elif "lidar" in capabilities:
            sensor_kind = "lidar"
        elif "sonar" in capabilities:
            sensor_kind = "sonar"
        elif "ir" in capabilities or "thermal" in capabilities:
            sensor_kind = "ir"
    if sensor_kind not in DRONE_SENSOR_DEFAULT_RANGES:
        return None
    visual = bool(sensor_kind == "camera" or "visual_identity_sensor" in capabilities)
    mapping = bool(sensor_kind in {"camera", "radar", "lidar", "sonar"} or "mapping_sensor" in capabilities)
    threat = bool(sensor_kind in {"radar", "ir"} or "threat_sensor" in capabilities)
    linked = bool(visual or mapping or threat or "linked_sensor" in capabilities or "linked_vision" in capabilities)
    if not linked:
        return None
    default_range = DRONE_SENSOR_DEFAULT_RANGES.get(sensor_kind, DRONE_LINKED_CAMERA_RADIUS)
    return {
        "item_id": item_id,
        "sensor_kind": sensor_kind,
        "label": str((profile.get("visible_overlay") or {}).get("label") or sensor_kind).strip().lower() or sensor_kind,
        "range": int(max(1, _int(profile.get("sensor_range"), default_range) or default_range)),
        "power_cost": int(max(0, _int(profile.get("sensor_power_cost"), profile.get("active_draw", 0)))),
        "occlusion_depth": int(max(0, _int(profile.get("sensor_occlusion_depth"), 0))),
        "visual_identity": bool(visual),
        "mapping": bool(mapping),
        "threat": bool(threat),
        "linked": bool(linked),
        "capabilities": tuple(sorted(capabilities)),
    }


def drone_sensor_modes(state, *, item_catalog=None):
    modes = []
    seen = set()
    for module in tuple(getattr(state, "modules", ()) or ()):
        mode = _module_sensor_mode(module, item_catalog=item_catalog)
        if not mode:
            continue
        key = str(mode.get("sensor_kind", ""))
        if key in seen:
            continue
        seen.add(key)
        modes.append(mode)
    return tuple(modes)


def _select_sensor_mode(state, *, item_catalog=None, preferred=None, purpose="linked"):
    modes = tuple(drone_sensor_modes(state, item_catalog=item_catalog))
    if not modes:
        return None
    preferred = str(preferred or "").strip().lower()
    if preferred:
        for mode in modes:
            if str(mode.get("sensor_kind")) == preferred:
                return mode
    if purpose == "mapping":
        priority = DRONE_MAPPING_SENSOR_PRIORITY
        candidates = [mode for mode in modes if bool(mode.get("mapping"))]
    elif purpose == "visual":
        priority = ("camera",)
        candidates = [mode for mode in modes if bool(mode.get("visual_identity"))]
    else:
        priority = DRONE_LINKED_SENSOR_PRIORITY
        candidates = [mode for mode in modes if bool(mode.get("linked"))]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda mode: (
            priority.index(str(mode.get("sensor_kind"))) if str(mode.get("sensor_kind")) in priority else 99,
            -int(mode.get("range", 0) or 0),
            str(mode.get("item_id", "")),
        ),
    )[0]


def _deployed_drone_state(sim, drone_eid):
    state = sim.ecs.get(DroneState).get(drone_eid)
    if state is None:
        return None
    if str(getattr(state, "mode", "") or "").strip().lower() != "deployed":
        return None
    return state


def _range_anchor(sim, state):
    controller_eid = getattr(state, "controller_eid", None)
    controller_pos = sim.ecs.get(Position).get(controller_eid) if controller_eid is not None else None
    if controller_pos is not None:
        return (int(controller_pos.x), int(controller_pos.y), int(controller_pos.z))
    home = getattr(state, "home", None)
    if isinstance(home, (list, tuple)) and len(home) >= 3:
        return (_int(home[0]), _int(home[1]), _int(home[2]))
    return None


def drone_has_visual_identity_sensor(state, *, item_catalog=None):
    return _select_sensor_mode(state, item_catalog=item_catalog, purpose="visual") is not None


def drone_has_camera_sensor(state, *, item_catalog=None):
    return drone_has_visual_identity_sensor(state, item_catalog=item_catalog)


def drone_has_mapping_sensor(state, *, item_catalog=None):
    return _select_sensor_mode(state, item_catalog=item_catalog, purpose="mapping") is not None


def drone_has_threat_sensor(state, *, item_catalog=None):
    return any(bool(mode.get("threat")) for mode in drone_sensor_modes(state, item_catalog=item_catalog))


def drone_has_linked_sensor(state, *, item_catalog=None):
    return _select_sensor_mode(state, item_catalog=item_catalog, purpose="linked") is not None


def drone_has_radio_comms(state, *, item_catalog=None):
    return bool(
        drone_state_has_capability(state, "radio", item_catalog=item_catalog)
        or drone_state_has_capability(state, "comms", item_catalog=item_catalog)
    )


def drone_has_mapping_procedure(state, *, item_catalog=None):
    return bool(
        drone_state_has_capability(state, "mapping", item_catalog=item_catalog)
        or drone_state_has_capability(state, "recon", item_catalog=item_catalog)
    )


def drone_can_live_report(state, *, item_catalog=None):
    return bool(
        drone_has_visual_identity_sensor(state, item_catalog=item_catalog)
        and drone_has_radio_comms(state, item_catalog=item_catalog)
    )


def _sensor_visible_positions(sim, drone_eid, pos, mode):
    sensor_kind = str((mode or {}).get("sensor_kind", "camera") or "camera").strip().lower()
    radius = int(max(1, _int((mode or {}).get("range"), DRONE_SENSOR_DEFAULT_RANGES.get(sensor_kind, DRONE_LINKED_CAMERA_RADIUS))))
    if sensor_kind == "ir":
        visible = set()
        max_depth = int(max(0, _int((mode or {}).get("occlusion_depth"), 1)))
        for x in range(int(pos.x) - radius, int(pos.x) + radius + 1):
            for y in range(int(pos.y) - radius, int(pos.y) + radius + 1):
                if not sim.tilemap.in_bounds(x, y):
                    continue
                if _grid_distance(pos.x, pos.y, x, y) > radius:
                    continue
                if not _loaded(sim, x, y, pos.z):
                    continue
                if _opaque_depth_between(sim, pos.x, pos.y, pos.z, x, y, pos.z) <= max_depth:
                    visible.add((int(x), int(y), int(pos.z)))
        return visible
    visible = observer_visible_positions(
        sim,
        observer_eid=drone_eid,
        x=pos.x,
        y=pos.y,
        z=pos.z,
        radius=radius,
    )
    return {
        (int(x), int(y), int(z))
        for x, y, z in visible
        if int(z) == int(pos.z) and _loaded(sim, x, y, z)
    }


def _entity_is_warm(sim, eid):
    if sim.ecs.get(DroneState).get(eid) is not None:
        return False
    vitality = sim.ecs.get(Vitality).get(eid)
    if vitality is None or int(getattr(vitality, "hp", 0) or 0) <= 0:
        return False
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    if identity is None:
        return True
    taxonomy = str(getattr(identity, "taxonomy_class", "") or "").strip().lower()
    species = str(getattr(identity, "species", "") or "").strip().lower()
    creature_type = str(getattr(identity, "creature_type", "") or "").strip().lower()
    return taxonomy not in {"machine", "robot", "drone"} and species not in {"machine", "robot", "drone"} and creature_type not in {"machine", "robot", "drone"}


def _ir_contacts(sim, drone_eid, pos, mode, visible):
    if str((mode or {}).get("sensor_kind", "") or "").strip().lower() != "ir":
        return tuple()
    radius = int(max(1, _int((mode or {}).get("range"), DRONE_SENSOR_DEFAULT_RANGES["ir"])))
    max_depth = int(max(0, _int((mode or {}).get("occlusion_depth"), 1)))
    contacts = []
    seen = set()

    def add_contact(x, y, z, kind, label):
        coord = (int(x), int(y), int(z))
        if coord in seen or coord not in visible:
            return
        if _grid_distance(pos.x, pos.y, x, y) > radius:
            return
        if _opaque_depth_between(sim, pos.x, pos.y, pos.z, x, y, z) > max_depth:
            return
        seen.add(coord)
        contacts.append({"coord": coord, "kind": kind, "label": label})

    for eid, entity_pos in list(sim.ecs.get(Position).items()):
        if int(eid) == int(drone_eid) or int(entity_pos.z) != int(pos.z):
            continue
        if _entity_is_warm(sim, eid):
            add_contact(entity_pos.x, entity_pos.y, entity_pos.z, "warm_body", "warm body")

    for coord in tuple(visible):
        cell = fire_cell_state(sim, coord[0], coord[1], coord[2])
        if isinstance(cell, dict) and int(cell.get("fire_intensity", 0) or 0) > 0:
            add_contact(coord[0], coord[1], coord[2], "heat_source", "heat source")
    return tuple(contacts)


def _linked_sensor_base_status(sim, controller_eid, drone_eid, *, mode=None, radius=None, item_catalog=None):
    state = _deployed_drone_state(sim, drone_eid)
    default_radius = int(radius or DRONE_LINKED_CAMERA_RADIUS)
    if state is None:
        return {"ok": False, "reason": "not_deployed", "visible": set(), "radius": default_radius}
    pos = sim.ecs.get(Position).get(drone_eid)
    if pos is None:
        return {"ok": False, "reason": "missing_position", "state": state, "visible": set(), "radius": default_radius}
    controller_pos = sim.ecs.get(Position).get(controller_eid)
    if controller_pos is None:
        return {"ok": False, "reason": "missing_controller_position", "state": state, "position": pos, "visible": set(), "radius": default_radius}
    if int(pos.z) != int(controller_pos.z):
        return {"ok": False, "reason": "wrong_floor", "state": state, "position": pos, "visible": set(), "radius": default_radius}
    if not drone_state_controlled_by_actor(state, controller_eid):
        return {"ok": False, "reason": "not_controller", "state": state, "position": pos, "visible": set(), "radius": default_radius}
    if not drone_state_has_capability(state, "remote_control", item_catalog=item_catalog):
        return {"ok": False, "reason": "no_remote_control", "state": state, "position": pos, "visible": set(), "radius": default_radius}
    if mode is None:
        return {"ok": False, "reason": "no_linked_sensor", "state": state, "position": pos, "visible": set(), "radius": default_radius}
    if int(getattr(state, "battery_charge", 0) or 0) <= 0:
        return {"ok": False, "reason": "battery_depleted", "state": state, "position": pos, "visible": set(), "radius": default_radius, "sensor_mode": mode}

    anchor = _range_anchor(sim, state)
    if anchor is None:
        return {"ok": False, "reason": "no_range_anchor", "state": state, "position": pos, "visible": set(), "radius": default_radius, "sensor_mode": mode}
    range_limit = int(max(0, getattr(state, "range_limit", 0) or 0))
    if range_limit <= 0:
        return {"ok": False, "reason": "no_range", "state": state, "position": pos, "visible": set(), "radius": default_radius, "sensor_mode": mode}
    if int(anchor[2]) != int(pos.z) or abs(int(pos.x) - int(anchor[0])) + abs(int(pos.y) - int(anchor[1])) > range_limit:
        return {"ok": False, "reason": "out_of_range", "state": state, "position": pos, "visible": set(), "radius": default_radius, "sensor_mode": mode}

    visible = _sensor_visible_positions(sim, drone_eid, pos, mode)
    radius = int(max(1, _int(mode.get("range"), default_radius)))
    contacts = _ir_contacts(sim, drone_eid, pos, mode, visible)
    capabilities = drone_state_capabilities(state, item_catalog=item_catalog)
    return {
        "ok": True,
        "reason": None,
        "state": state,
        "position": pos,
        "visible": visible,
        "radius": int(radius),
        "sensor_kind": str(mode.get("sensor_kind", "") or "").strip().lower(),
        "sensor_label": str(mode.get("label", "") or mode.get("sensor_kind", "") or "sensor").strip().lower(),
        "sensor_mode": dict(mode),
        "contacts": contacts,
        "capabilities": capabilities,
        "can_live_report": drone_can_live_report(state, item_catalog=item_catalog),
        "has_mapping_procedure": drone_has_mapping_procedure(state, item_catalog=item_catalog),
    }


def linked_sensor_status(sim, controller_eid, drone_eid, *, preferred_sensor=None, item_catalog=None):
    state = _deployed_drone_state(sim, drone_eid)
    mode = _select_sensor_mode(
        state,
        item_catalog=item_catalog,
        preferred=preferred_sensor,
        purpose="linked",
    ) if state is not None else None
    return _linked_sensor_base_status(
        sim,
        controller_eid,
        drone_eid,
        mode=mode,
        item_catalog=item_catalog,
    )


def linked_camera_status(sim, controller_eid, drone_eid, *, radius=DRONE_LINKED_CAMERA_RADIUS, item_catalog=None):
    state = _deployed_drone_state(sim, drone_eid)
    mode = _select_sensor_mode(state, item_catalog=item_catalog, purpose="visual") if state is not None else None
    status = _linked_sensor_base_status(
        sim,
        controller_eid,
        drone_eid,
        mode=mode,
        radius=radius,
        item_catalog=item_catalog,
    )
    if status.get("reason") == "no_linked_sensor":
        status["reason"] = "no_camera"
    return status


def clear_linked_camera_view(sim):
    state = visibility_state(sim)
    state["linked_drone_visible"] = set()
    state["linked_drone_eid"] = None
    state["linked_drone_origin"] = None
    state["linked_drone_radius"] = 0
    state["linked_drone_sensor_kind"] = None
    state["linked_drone_sensor_contacts"] = tuple()


def _apply_linked_sensor_status(sim, controller_eid, drone_eid, status, *, source_name=None, teach_geometry=True):
    if not status.get("ok"):
        clear_linked_camera_view(sim)
        return status

    visible = set(status.get("visible", set()) or set())
    state = visibility_state(sim)
    explored = state.get("player_explored")
    if not isinstance(explored, set):
        explored = set(explored or ())
    before = len(explored)
    if teach_geometry:
        explored.update(visible)
        state["player_explored"] = explored

    sources = state.get("player_explored_sources")
    if not isinstance(sources, dict):
        sources = {}
        state["player_explored_sources"] = sources
    tick = _int(getattr(sim, "tick", 0), 0)
    if teach_geometry:
        sensor_kind = str(status.get("sensor_kind", "camera") or "camera").strip().lower()
        source_name = source_name or ("linked_drone" if sensor_kind == "camera" else f"linked_drone_{sensor_kind}")
        for coord in visible:
            sources[coord] = {
                "source": source_name,
                "sensor_kind": sensor_kind,
                "drone_eid": drone_eid,
                "controller_eid": controller_eid,
                "tick": tick,
            }

    pos = status.get("position")
    state["linked_drone_visible"] = set(visible)
    state["linked_drone_eid"] = drone_eid
    state["linked_drone_origin"] = (int(pos.x), int(pos.y), int(pos.z)) if pos is not None else None
    state["linked_drone_radius"] = int(status.get("radius", DRONE_LINKED_CAMERA_RADIUS) or DRONE_LINKED_CAMERA_RADIUS)
    state["linked_drone_sensor_kind"] = str(status.get("sensor_kind", "camera") or "camera").strip().lower()
    state["linked_drone_sensor_contacts"] = tuple(status.get("contacts", ()) or ())
    status["learned_count"] = max(0, len(explored) - before)
    return status


def apply_linked_sensor_knowledge(sim, controller_eid, drone_eid, *, preferred_sensor=None, item_catalog=None):
    status = linked_sensor_status(
        sim,
        controller_eid,
        drone_eid,
        preferred_sensor=preferred_sensor,
        item_catalog=item_catalog,
    )
    teach_geometry = str(status.get("sensor_kind", "") or "").strip().lower() != "ir"
    return _apply_linked_sensor_status(sim, controller_eid, drone_eid, status, teach_geometry=teach_geometry)


def apply_linked_camera_knowledge(sim, controller_eid, drone_eid, *, radius=DRONE_LINKED_CAMERA_RADIUS, item_catalog=None):
    status = linked_camera_status(
        sim,
        controller_eid,
        drone_eid,
        radius=radius,
        item_catalog=item_catalog,
    )
    return _apply_linked_sensor_status(sim, controller_eid, drone_eid, status, source_name="linked_drone", teach_geometry=True)


def autonomous_mapping_status(sim, recipient_eid, drone_eid, *, radius=DRONE_LINKED_CAMERA_RADIUS, item_catalog=None):
    state = _deployed_drone_state(sim, drone_eid)
    if state is None:
        return {"ok": False, "reason": "not_deployed", "visible": set(), "radius": int(radius)}
    pos = sim.ecs.get(Position).get(drone_eid)
    if pos is None:
        return {"ok": False, "reason": "missing_position", "state": state, "visible": set(), "radius": int(radius)}
    if recipient_eid is not None and not drone_state_controlled_by_actor(state, recipient_eid):
        return {"ok": False, "reason": "not_controller", "state": state, "position": pos, "visible": set(), "radius": int(radius)}
    if not drone_has_mapping_procedure(state, item_catalog=item_catalog):
        return {"ok": False, "reason": "no_mapping_procedure", "state": state, "position": pos, "visible": set(), "radius": int(radius)}
    mode = _select_sensor_mode(state, item_catalog=item_catalog, purpose="mapping")
    if mode is None:
        return {"ok": False, "reason": "no_mapping_sensor", "state": state, "position": pos, "visible": set(), "radius": int(radius)}
    if not drone_has_radio_comms(state, item_catalog=item_catalog):
        return {"ok": False, "reason": "no_radio", "state": state, "position": pos, "visible": set(), "radius": int(radius)}
    if int(getattr(state, "battery_charge", 0) or 0) <= 0:
        return {"ok": False, "reason": "battery_depleted", "state": state, "position": pos, "visible": set(), "radius": int(radius)}

    anchor = _range_anchor(sim, state)
    if anchor is None:
        return {"ok": False, "reason": "no_range_anchor", "state": state, "position": pos, "visible": set(), "radius": int(radius)}
    range_limit = int(max(0, getattr(state, "range_limit", 0) or 0))
    if range_limit <= 0:
        return {"ok": False, "reason": "no_range", "state": state, "position": pos, "visible": set(), "radius": int(radius)}
    if int(anchor[2]) != int(pos.z) or abs(int(pos.x) - int(anchor[0])) + abs(int(pos.y) - int(anchor[1])) > range_limit:
        return {"ok": False, "reason": "out_of_range", "state": state, "position": pos, "visible": set(), "radius": int(radius)}

    radius = int(max(1, _int(mode.get("range"), radius or DRONE_LINKED_CAMERA_RADIUS)))
    visible = _sensor_visible_positions(sim, drone_eid, pos, mode)
    return {
        "ok": True,
        "reason": None,
        "state": state,
        "position": pos,
        "visible": visible,
        "radius": int(radius),
        "sensor_kind": str(mode.get("sensor_kind", "") or "").strip().lower(),
        "sensor_label": str(mode.get("label", "") or mode.get("sensor_kind", "") or "sensor").strip().lower(),
        "sensor_mode": dict(mode),
        "capabilities": drone_state_capabilities(state, item_catalog=item_catalog),
        "can_live_report": drone_can_live_report(state, item_catalog=item_catalog),
        "has_mapping_procedure": True,
    }


def apply_autonomous_mapping_knowledge(sim, recipient_eid, drone_eid, *, radius=DRONE_LINKED_CAMERA_RADIUS, item_catalog=None):
    status = autonomous_mapping_status(
        sim,
        recipient_eid,
        drone_eid,
        radius=radius,
        item_catalog=item_catalog,
    )
    if not status.get("ok"):
        return status

    visible = set(status.get("visible", set()) or set())
    if recipient_eid != getattr(sim, "player_eid", None):
        status["learned_count"] = 0
        return status

    state = visibility_state(sim)
    explored = state.get("player_explored")
    if not isinstance(explored, set):
        explored = set(explored or ())
    before = len(explored)
    explored.update(visible)
    state["player_explored"] = explored

    sources = state.get("player_explored_sources")
    if not isinstance(sources, dict):
        sources = {}
        state["player_explored_sources"] = sources
    tick = _int(getattr(sim, "tick", 0), 0)
    sensor_kind = str(status.get("sensor_kind", "") or "").strip().lower()
    for coord in visible:
        sources[coord] = {
            "source": "autonomous_drone",
            "sensor_kind": sensor_kind,
            "drone_eid": drone_eid,
            "controller_eid": recipient_eid,
            "procedure": "mapping",
            "tick": tick,
        }
    status["learned_count"] = max(0, len(explored) - before)
    return status


def describe_drone_camera_cell(sim, x, y, z):
    x = int(x)
    y = int(y)
    z = int(z)
    if not sim.tilemap.in_bounds(x, y):
        return f"Camera: ({x},{y},{z}) is out of bounds."
    if not _loaded(sim, x, y, z):
        return f"Camera: ({x},{y},{z}) is beyond loaded street detail."
    tile = sim.tilemap.tile_at(x, y, z)
    if tile is None:
        tile_text = "open ground"
        walk_text = "walkable"
    else:
        tile_text = str(getattr(tile, "glyph", ".") or ".")
        walk_text = "walkable" if bool(getattr(tile, "walkable", True)) else "blocked"
    entities = [
        int(eid)
        for eid in sim.tilemap.entities_at(x, y, z)
        if sim.ecs.get(Position).get(eid) is not None
    ]
    entity_text = f" entities:{','.join(str(eid) for eid in sorted(entities)[:3])}" if entities else ""
    ground_items = getattr(sim, "ground_items_at", None)
    items = ground_items(x, y, z=z) if callable(ground_items) else ()
    item_text = f" items:{len(items)}" if items else ""
    return f"Camera: ({x},{y},{z}) {tile_text} {walk_text}.{entity_text}{item_text}"


def describe_drone_sensor_cell(sim, x, y, z, *, sensor_kind=None, contacts=None):
    sensor_kind = str(sensor_kind or "camera").strip().lower() or "camera"
    if sensor_kind == "camera":
        return describe_drone_camera_cell(sim, x, y, z)
    x = int(x)
    y = int(y)
    z = int(z)
    if not sim.tilemap.in_bounds(x, y):
        return f"{sensor_kind.upper()}: ({x},{y},{z}) is out of bounds."
    if not _loaded(sim, x, y, z):
        return f"{sensor_kind.upper()}: ({x},{y},{z}) is beyond loaded street detail."
    if sensor_kind == "ir":
        contact = None
        for row in tuple(contacts or ()):
            if isinstance(row, dict) and tuple(row.get("coord", ())) == (x, y, z):
                contact = row
                break
        if contact:
            return f"IR: ({x},{y},{z}) coarse {contact.get('label', 'heat contact')} contact."
        return f"IR: ({x},{y},{z}) no heat contact."
    tile = sim.tilemap.tile_at(x, y, z)
    if tile is None:
        tile_text = "open return"
        walk_text = "walkable"
    else:
        tile_text = "solid return" if not bool(getattr(tile, "walkable", True)) else "open return"
        walk_text = "transparent" if bool(getattr(tile, "transparent", True)) else "opaque"
    label = {"radar": "Radar", "lidar": "Lidar", "sonar": "Sonar"}.get(sensor_kind, sensor_kind.upper())
    return f"{label}: ({x},{y},{z}) {tile_text}, {walk_text}."
