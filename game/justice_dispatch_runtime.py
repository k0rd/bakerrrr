"""Player-requested justice dispatch without creating incident knowledge."""

from engine.events import Event
from game.components import AI, JusticeProfile, NPCWill, Position
from game.system_support.actor_runtime import _entity_is_downed
from game.system_support.player_feedback import _log_player_feedback
from game.systems_observed_dispatch import BUSY_STATES, PEACE_ROLES


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _actor_is_peace(sim, eid):
    ai = sim.ecs.get(AI).get(eid)
    justice = sim.ecs.get(JusticeProfile).get(eid)
    role = str(getattr(ai, "role", "") or "").strip().lower() if ai is not None else ""
    return role in PEACE_ROLES or bool(getattr(justice, "enforce_all", False))


def _available_for_dispatch(sim, eid):
    if _entity_is_downed(sim, eid):
        return False
    ai = sim.ecs.get(AI).get(eid)
    if ai is None:
        return False
    state = str(getattr(ai, "state", "") or "").strip().lower()
    if state in BUSY_STATES:
        return False
    return True


def _dispatch_candidates(sim, x, y, z, *, radius=80):
    positions = sim.ecs.get(Position)
    rows = []
    for eid in sim.entity_ids_in_radius(x, y, z, radius):
        pos = positions.get(eid)
        if pos is None:
            continue
        if _safe_int(getattr(pos, "z", 0)) != int(z):
            continue
        if not _actor_is_peace(sim, eid) or not _available_for_dispatch(sim, eid):
            continue
        distance = abs(_safe_int(getattr(pos, "x", 0)) - int(x)) + abs(_safe_int(getattr(pos, "y", 0)) - int(y))
        if distance > int(radius):
            continue
        rows.append((int(distance), int(eid)))
    rows.sort(key=lambda row: (row[0], row[1]))
    return rows


def request_player_justice_dispatch(sim, eid, x, y, z, *, source="call", property_id=None, property_name=None, radius=80):
    """Send the nearest available peace actor to a player-requested location.

    This is dispatch-only: it does not create incident knowledge, wanted heat,
    or evidence. Responders simply investigate the requested coordinate.
    """
    x = _safe_int(x)
    y = _safe_int(y)
    z = _safe_int(z)
    source = str(source or "call").strip().lower() or "call"
    property_name = str(property_name or "").strip()
    candidates = _dispatch_candidates(sim, x, y, z, radius=radius)
    sim.emit(Event(
        "player_justice_dispatch_requested",
        eid=eid,
        x=x,
        y=y,
        z=z,
        source=source,
        property_id=property_id,
        property_name=property_name,
        incident_created=False,
        heat_created=False,
    ))
    if not candidates:
        _log_player_feedback(
            sim,
            "Dispatch does not have an officer close enough to answer right now.",
            kind="interaction",
        )
        sim.emit(Event(
            "player_justice_dispatch_unavailable",
            eid=eid,
            x=x,
            y=y,
            z=z,
            source=source,
            property_id=property_id,
            property_name=property_name,
            incident_created=False,
            heat_created=False,
        ))
        return {
            "ok": False,
            "reason": "no_available_responder",
            "responder_eid": None,
            "lines": ("Dispatch does not have an officer close enough to answer right now.",),
        }

    distance, responder_eid = candidates[0]
    ai = sim.ecs.get(AI).get(responder_eid)
    will = sim.ecs.get(NPCWill).get(responder_eid)
    target = (int(x), int(y), int(z))
    if ai is not None:
        ai.state = "investigating"
        ai.target = target
        ai.target_eid = None
        ai.response_role = "player_dispatch"
        ai.player_dispatch_source = source
        ai.player_dispatch_property_id = str(property_id or "").strip()
    if will is not None:
        will.intent = "investigating"
        will.score = 74.0
        will.target = target
        will.target_eid = None
        will.last_tick = _safe_int(getattr(sim, "tick", 0))

    place = property_name or "your location"
    _log_player_feedback(sim, f"Dispatch answers. An officer is heading to {place}.", kind="interaction")
    sim.emit(Event(
        "player_justice_dispatch_assigned",
        eid=eid,
        responder_eid=responder_eid,
        distance=int(distance),
        x=x,
        y=y,
        z=z,
        source=source,
        property_id=property_id,
        property_name=property_name,
        incident_created=False,
        heat_created=False,
    ))
    return {
        "ok": True,
        "reason": "assigned",
        "responder_eid": int(responder_eid),
        "distance": int(distance),
        "lines": (f"Dispatch answers. An officer is heading to {place}.",),
    }
