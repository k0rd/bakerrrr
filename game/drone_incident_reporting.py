"""Drone camera/radio incident reporting helpers."""

from __future__ import annotations

from engine.visibility import observer_visible_positions

from game.components import DroneState, Position
from game.drone_recon import (
    DRONE_LINKED_CAMERA_RADIUS,
    drone_has_camera_sensor,
    drone_has_radio_comms,
)
from game.drone_runtime import (
    drone_link_disruption_status,
    drone_sensor_suppression_status,
    drone_state_controlled_by_actor,
    drone_state_has_capability,
)
from game.items import ITEM_CATALOG


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _deployed(state):
    return str(getattr(state, "mode", "") or "").strip().lower() == "deployed"


def _loaded(sim, x, y, z=0):
    chunk_detail = getattr(sim, "chunk_detail", None)
    chunk_coords = getattr(sim, "chunk_coords", None)
    if isinstance(chunk_detail, dict) and callable(chunk_coords):
        chunk = chunk_coords(int(x), int(y))
        if chunk in chunk_detail:
            return str(chunk_detail.get(chunk, "")).strip().lower() != "unloaded"
    detail_for_xy = getattr(sim, "detail_for_xy", None)
    if callable(detail_for_xy):
        try:
            return str(detail_for_xy(int(x), int(y))).strip().lower() != "unloaded"
        except (TypeError, ValueError):
            return False
    return True


def _range_anchor(sim, state):
    controller_eid = getattr(state, "controller_eid", None)
    controller_pos = sim.ecs.get(Position).get(controller_eid) if controller_eid is not None else None
    if controller_pos is not None:
        return (int(controller_pos.x), int(controller_pos.y), int(controller_pos.z))
    home = getattr(state, "home", None)
    if isinstance(home, (list, tuple)) and len(home) >= 3:
        return (_int(home[0]), _int(home[1]), _int(home[2]))
    return None


def _within_range(sim, drone_pos, state):
    anchor = _range_anchor(sim, state)
    if anchor is None:
        return False
    range_limit = int(max(0, getattr(state, "range_limit", 0) or 0))
    if range_limit <= 0 or int(anchor[2]) != int(drone_pos.z):
        return False
    distance = abs(int(drone_pos.x) - int(anchor[0])) + abs(int(drone_pos.y) - int(anchor[1]))
    return distance <= range_limit


def _candidate_coords(sim, incident, event):
    data = getattr(event, "data", event)
    if not isinstance(data, dict):
        data = {}
    rows = []

    def _add(x, y, z):
        if x is None or y is None:
            return
        rows.append((_int(x), _int(y), _int(z, 0)))

    _add(data.get("target_x"), data.get("target_y"), data.get("target_z", data.get("z", 0)))
    _add((incident or {}).get("x"), (incident or {}).get("y"), (incident or {}).get("z", 0))
    _add(data.get("x"), data.get("y"), data.get("z", 0))
    for key in ("victim_eid", "target_eid", "primary_actor_eid", "offender_eid", "eid"):
        eid = data.get(key, (incident or {}).get(key))
        pos = sim.ecs.get(Position).get(eid) if eid is not None else None
        if pos is not None:
            _add(pos.x, pos.y, pos.z)
    return tuple(dict.fromkeys(rows))


def _active_player_camera_link(sim, drone_eid, state, *, item_catalog=None):
    player_eid = getattr(sim, "player_eid", None)
    if player_eid is None or not drone_state_controlled_by_actor(state, player_eid):
        return False
    if not drone_state_has_capability(state, "remote_control", item_catalog=item_catalog or ITEM_CATALOG):
        return False
    ui = getattr(sim, "drone_command_ui", None)
    if not isinstance(ui, dict) or not bool(ui.get("open")) or not bool(ui.get("camera_open")):
        return False
    if str(ui.get("camera_sensor_mode", "camera") or "camera").strip().lower() != "camera":
        return False
    try:
        return int(ui.get("camera_drone_eid")) == int(drone_eid)
    except (TypeError, ValueError):
        return False


def _recipient_rows(sim, drone_eid, state, *, active_player_link=False, radio_report=False):
    recipients = []
    seen = set()

    def _add(eid, reason):
        try:
            eid = int(eid)
        except (TypeError, ValueError):
            return
        if eid in seen or eid == int(drone_eid):
            return
        seen.add(eid)
        recipients.append({"recipient_eid": eid, "reason": reason})

    if active_player_link:
        _add(getattr(sim, "player_eid", None), "active_player_link")
    if radio_report:
        _add(getattr(state, "controller_eid", None), "radio_controller")
        _add(getattr(state, "owner_eid", None), "radio_owner")
    return tuple(recipients)


def drone_incident_report_rows(sim, incident, event, *, item_catalog=None):
    """Return firsthand operator/org recipient rows for drones that observed an incident.

    Camera-only drones do not create incident reports. They may later record or
    react locally, but knowledge handoff requires either an active player camera
    link or a camera plus radio/comms package.
    """

    item_catalog = item_catalog or ITEM_CATALOG
    coords = _candidate_coords(sim, incident, event)
    if not coords:
        return ()
    rows = []
    positions = sim.ecs.get(Position)
    for drone_eid, state in list(sim.ecs.get(DroneState).items()):
        if not _deployed(state):
            continue
        pos = positions.get(drone_eid)
        if pos is None or int(getattr(state, "battery_charge", 0) or 0) <= 0:
            continue
        if drone_link_disruption_status(state, tick=int(getattr(sim, "tick", 0) or 0)).get("active"):
            continue
        if drone_sensor_suppression_status(state, tick=int(getattr(sim, "tick", 0) or 0)).get("active"):
            continue
        if not drone_has_camera_sensor(state, item_catalog=item_catalog):
            continue
        active_link = _active_player_camera_link(sim, drone_eid, state, item_catalog=item_catalog)
        radio_report = bool(drone_has_radio_comms(state, item_catalog=item_catalog))
        if radio_report and not _within_range(sim, pos, state):
            radio_report = False
        if not active_link and not radio_report:
            continue
        visible = observer_visible_positions(
            sim,
            observer_eid=drone_eid,
            x=pos.x,
            y=pos.y,
            z=pos.z,
            radius=DRONE_LINKED_CAMERA_RADIUS,
        )
        visible = {
            (int(x), int(y), int(z))
            for x, y, z in visible
            if int(z) == int(pos.z) and _loaded(sim, x, y, z)
        }
        observed_coord = next((coord for coord in coords if coord in visible), None)
        if observed_coord is None:
            continue
        for recipient in _recipient_rows(
            sim,
            drone_eid,
            state,
            active_player_link=active_link,
            radio_report=radio_report,
        ):
            row = dict(recipient)
            row.update({
                "drone_eid": int(drone_eid),
                "observed_coord": observed_coord,
                "active_player_link": bool(active_link and row.get("reason") == "active_player_link"),
                "radio_report": bool(row.get("reason", "").startswith("radio_")),
            })
            rows.append(row)
    return tuple(rows)


__all__ = ["drone_incident_report_rows"]
