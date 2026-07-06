"""Linked camera and recon helpers for deployed drones."""

from __future__ import annotations

from engine.visibility import observer_visible_positions, visibility_state

from game.components import DroneState, Position
from game.drone_runtime import (
    drone_state_capabilities,
    drone_state_controlled_by_actor,
    drone_state_has_capability,
)


DRONE_LINKED_CAMERA_RADIUS = 8


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


def drone_has_camera_sensor(state, *, item_catalog=None):
    return bool(
        drone_state_has_capability(state, "camera", item_catalog=item_catalog)
        or drone_state_has_capability(state, "sensor", item_catalog=item_catalog)
    )


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
        drone_has_camera_sensor(state, item_catalog=item_catalog)
        and drone_has_radio_comms(state, item_catalog=item_catalog)
    )


def linked_camera_status(sim, controller_eid, drone_eid, *, radius=DRONE_LINKED_CAMERA_RADIUS, item_catalog=None):
    state = _deployed_drone_state(sim, drone_eid)
    if state is None:
        return {"ok": False, "reason": "not_deployed", "visible": set(), "radius": int(radius)}
    pos = sim.ecs.get(Position).get(drone_eid)
    if pos is None:
        return {"ok": False, "reason": "missing_position", "state": state, "visible": set(), "radius": int(radius)}
    controller_pos = sim.ecs.get(Position).get(controller_eid)
    if controller_pos is None:
        return {"ok": False, "reason": "missing_controller_position", "state": state, "position": pos, "visible": set(), "radius": int(radius)}
    if int(pos.z) != int(controller_pos.z):
        return {"ok": False, "reason": "wrong_floor", "state": state, "position": pos, "visible": set(), "radius": int(radius)}
    if not drone_state_controlled_by_actor(state, controller_eid):
        return {"ok": False, "reason": "not_controller", "state": state, "position": pos, "visible": set(), "radius": int(radius)}
    if not drone_state_has_capability(state, "remote_control", item_catalog=item_catalog):
        return {"ok": False, "reason": "no_remote_control", "state": state, "position": pos, "visible": set(), "radius": int(radius)}
    if not drone_has_camera_sensor(state, item_catalog=item_catalog):
        return {"ok": False, "reason": "no_camera", "state": state, "position": pos, "visible": set(), "radius": int(radius)}
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

    radius = max(1, int(radius or DRONE_LINKED_CAMERA_RADIUS))
    visible = observer_visible_positions(
        sim,
        observer_eid=drone_eid,
        x=pos.x,
        y=pos.y,
        z=pos.z,
        radius=radius,
    )
    visible = {
        (int(x), int(y), int(z))
        for x, y, z in visible
        if int(z) == int(pos.z) and _loaded(sim, x, y, z)
    }
    capabilities = drone_state_capabilities(state, item_catalog=item_catalog)
    return {
        "ok": True,
        "reason": None,
        "state": state,
        "position": pos,
        "visible": visible,
        "radius": int(radius),
        "capabilities": capabilities,
        "can_live_report": drone_can_live_report(state, item_catalog=item_catalog),
        "has_mapping_procedure": drone_has_mapping_procedure(state, item_catalog=item_catalog),
    }


def clear_linked_camera_view(sim):
    state = visibility_state(sim)
    state["linked_drone_visible"] = set()
    state["linked_drone_eid"] = None
    state["linked_drone_origin"] = None
    state["linked_drone_radius"] = 0


def apply_linked_camera_knowledge(sim, controller_eid, drone_eid, *, radius=DRONE_LINKED_CAMERA_RADIUS, item_catalog=None):
    status = linked_camera_status(
        sim,
        controller_eid,
        drone_eid,
        radius=radius,
        item_catalog=item_catalog,
    )
    if not status.get("ok"):
        clear_linked_camera_view(sim)
        return status

    visible = set(status.get("visible", set()) or set())
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
    for coord in visible:
        sources[coord] = {
            "source": "linked_drone",
            "drone_eid": drone_eid,
            "controller_eid": controller_eid,
            "tick": tick,
        }

    pos = status.get("position")
    state["linked_drone_visible"] = set(visible)
    state["linked_drone_eid"] = drone_eid
    state["linked_drone_origin"] = (int(pos.x), int(pos.y), int(pos.z)) if pos is not None else None
    state["linked_drone_radius"] = int(status.get("radius", radius) or radius)
    status["learned_count"] = max(0, len(explored) - before)
    return status


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
    if not drone_has_camera_sensor(state, item_catalog=item_catalog):
        return {"ok": False, "reason": "no_camera", "state": state, "position": pos, "visible": set(), "radius": int(radius)}
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

    radius = max(1, int(radius or DRONE_LINKED_CAMERA_RADIUS))
    visible = observer_visible_positions(
        sim,
        observer_eid=drone_eid,
        x=pos.x,
        y=pos.y,
        z=pos.z,
        radius=radius,
    )
    visible = {
        (int(x), int(y), int(z))
        for x, y, z in visible
        if int(z) == int(pos.z) and _loaded(sim, x, y, z)
    }
    return {
        "ok": True,
        "reason": None,
        "state": state,
        "position": pos,
        "visible": visible,
        "radius": int(radius),
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
    for coord in visible:
        sources[coord] = {
            "source": "autonomous_drone",
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
