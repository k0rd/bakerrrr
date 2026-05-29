"""Player-facing summaries for active local situations.

This module does not stage scenes. It reads already-materialized local runtime
state and turns it into compact report/look cues the player can choose to pursue.
"""

from __future__ import annotations

from game.components import Position
from game.organizations import local_protective_pressure_snapshot
from game.property_runtime import (
    building_id_from_property,
    property_display_position,
    property_focus_position,
    property_metadata,
)


_PHASE_PROFILES = {
    "regulars_spill": {
        "title": "Regulars Table",
        "summary": "loyal regulars are making the frontage visibly theirs",
        "action": "talk for the neighborhood read or lean on their vouch",
    },
    "grumbling_front": {
        "title": "Complaint Knot",
        "summary": "complaints have collected where passersby can see them",
        "action": "ask what soured, inspect the crate, or use the disagreement as cover",
    },
    "block_watch": {
        "title": "Block Watch",
        "summary": "locals are watching the door and remembering who presses it",
        "action": "question a watcher, respect the boundary, or risk being marked",
    },
    "soft_front": {
        "title": "Soft Front",
        "summary": "opportunists are testing a weak frontage for easy marks",
        "action": "read the sheet, challenge the nuisance, exploit it, or leave it alone",
    },
    "taped_off_front": {
        "title": "Held Aftermath",
        "summary": "recent trouble still has the frontage held in public view",
        "action": "inspect the hold notes or question nearby witnesses",
    },
    "afterhours_aftermath": {
        "title": "Afterhours Aftermath",
        "summary": "the last incident has left visible residue at the frontage",
        "action": "check the tape, read the room, or ask who stayed late",
    },
    "aftermath_cleanup": {
        "title": "Cleanup Detail",
        "summary": "workers are trying to reset the place after a messy beat",
        "action": "inspect the cleanup kit or ask what had to be scrubbed out",
    },
    "candle_vigil": {
        "title": "Candle Vigil",
        "summary": "neighbors have turned the frontage into a public memory site",
        "action": "listen carefully, inspect the offerings, or avoid drawing heat",
    },
    "street_triage": {
        "title": "Street Triage",
        "summary": "emergency care has spilled into the open street",
        "action": "help, lift supplies, question witnesses, or keep moving",
    },
    "delivery_run": {
        "title": "Delivery Handoff",
        "summary": "goods and route chatter are exposed at the curb",
        "action": "inspect cargo, talk to the driver, or follow the route lead",
    },
    "loading_push": {
        "title": "Loading Push",
        "summary": "freight work is briefly exposed outside the site",
        "action": "check the dolly, ask about cargo, or slip by under work noise",
    },
    "dispatch_surge": {
        "title": "Dispatch Surge",
        "summary": "route work is bunching up in public view",
        "action": "inspect the satchel or ask which run is under pressure",
    },
    "boarding_crush": {
        "title": "Boarding Crush",
        "summary": "passenger movement is crowding the frontage",
        "action": "read the fare rack, ask for connections, or use the bustle",
    },
    "arrival_handoff": {
        "title": "Arrival Handoff",
        "summary": "a transfer point is briefly full of useful local motion",
        "action": "inspect the clipboard or ask who just came through",
    },
    "shift_handoff": {
        "title": "Shift Handoff",
        "summary": "staff turnover is visible enough to expose site routines",
        "action": "question workers or inspect the notice before the shift settles",
    },
    "reset_scramble": {
        "title": "Reset Scramble",
        "summary": "staff are resetting the floor under public pressure",
        "action": "inspect the bus tub or ask what broke the rhythm",
    },
    "table_turnover": {
        "title": "Turnover Rush",
        "summary": "the place is cycling people fast enough to expose service patterns",
        "action": "watch the tray or ask which table keeps turning",
    },
    "barback_reset": {
        "title": "Barback Reset",
        "summary": "late service work has spilled into an exposed reset",
        "action": "inspect restock gear or ask what the night burned through",
    },
    "owner_screening": {
        "title": "Screened Entry",
        "summary": "the business is filtering access at the door",
        "action": "read the roster, talk to the host, or test the policy",
    },
    "owner_closed_turnover": {
        "title": "Closed Turnover",
        "summary": "staff are moving through a closed-door reset",
        "action": "inspect the sign or ask why the floor stayed dark",
    },
    "help_wanted_board": {
        "title": "Help-Wanted Board",
        "summary": "staffing pressure has become visible outside the business",
        "action": "read the board, talk to applicants, or recruit from the scene",
    },
    "paperwork_surge": {
        "title": "Paperwork Surge",
        "summary": "admin pressure has pushed review material into public reach",
        "action": "inspect the packet or ask what is under review",
    },
    "manifest_check": {
        "title": "Manifest Check",
        "summary": "a gate or cargo review is slowing work in public",
        "action": "read the manifest or ask what shipment drew attention",
    },
    "school_run": {
        "title": "School Run",
        "summary": "family traffic is briefly concentrating at the frontage",
        "action": "listen for local routines or inspect the bag cluster",
    },
    "neighbors_lingering": {
        "title": "Neighbor Linger",
        "summary": "nearby residents are hanging around long enough to trade local reads",
        "action": "ask what keeps them here or inspect the shared cooler",
    },
    "clinic_outreach": {
        "title": "Clinic Outreach",
        "summary": "care supplies and cautious advice are visible at the edge of the site",
        "action": "inspect the outreach table or ask what help is real",
    },
    "day_labor_call": {
        "title": "Crew Call",
        "summary": "day labor is being sorted in the open",
        "action": "inspect the call sheet or ask who needs hands",
    },
    "commuter_orientation": {
        "title": "Route Welcome",
        "summary": "new arrivals are being oriented in public",
        "action": "read the route board or ask where people are being sent",
    },
    "tenant_meetup": {
        "title": "Tenant Meetup",
        "summary": "residents are sharing building knowledge at the edge of the property",
        "action": "listen for access habits or inspect the welcome box",
    },
    "mutual_aid_table": {
        "title": "Mutual Aid Table",
        "summary": "neighbors have set out supplies and live local knowledge",
        "action": "take what is offered or ask what the block needs",
    },
}


_SCENE_TYPE_PROFILES = {
    "delivery": {
        "title": "Delivery Handoff",
        "summary": "a delivery has exposed goods, timing, and route chatter",
        "action": "inspect cargo, talk to workers, or follow the route lead",
    },
    "queue": {
        "title": "Frontage Queue",
        "summary": "a visible queue is exposing who uses the place and why",
        "action": "talk to people waiting or use the line as cover",
    },
    "shift": {
        "title": "Work Handoff",
        "summary": "workers are changing over in public view",
        "action": "question staff or inspect whatever they left out",
    },
    "gathering": {
        "title": "Local Gathering",
        "summary": "people have gathered around a visible local concern",
        "action": "ask around or inspect the shared fixture",
    },
}


def _text(value):
    return str(value or "").strip()


def _title_from_slug(value):
    words = [
        part
        for part in str(value or "").strip().replace("-", "_").split("_")
        if part
    ]
    return " ".join(word.capitalize() for word in words) or "Local Situation"


def _property_name(prop):
    if not isinstance(prop, dict):
        return "this frontage"
    metadata = property_metadata(prop)
    return (
        _text(metadata.get("business_name"))
        or _text(prop.get("name"))
        or _text(prop.get("id"))
        or "this frontage"
    )


def _active_scene_store(sim):
    state = getattr(sim, "business_event_scene_state", {})
    if not isinstance(state, dict):
        return {}
    active = state.get("active", {})
    return active if isinstance(active, dict) else {}


def _active_scene_by_id(sim, scene_id):
    scene_id = _text(scene_id)
    if not scene_id:
        return None
    scene = _active_scene_store(sim).get(scene_id)
    return scene if isinstance(scene, dict) else None


def _scene_anchor(sim, scene, prop):
    anchor = (scene or {}).get("anchor")
    if isinstance(anchor, (tuple, list)) and len(anchor) >= 3:
        try:
            return (int(anchor[0]), int(anchor[1]), int(anchor[2]))
        except (TypeError, ValueError):
            pass
    focus = property_focus_position(prop) if isinstance(prop, dict) else None
    if focus is None and isinstance(prop, dict):
        focus = property_display_position(prop)
    if focus is not None:
        return focus
    try:
        return (int(prop.get("x", 0)), int(prop.get("y", 0)), int(prop.get("z", 0)))
    except (AttributeError, TypeError, ValueError):
        return None


def _player_position(sim, player_eid):
    if sim is None or player_eid is None:
        return None
    try:
        return sim.ecs.get(Position).get(player_eid)
    except AttributeError:
        return None


def _chunk_for_anchor(sim, anchor):
    if sim is None or anchor is None or not hasattr(sim, "chunk_coords"):
        return None
    try:
        return sim.chunk_coords(int(anchor[0]), int(anchor[1]))
    except (TypeError, ValueError):
        return None


def _same_chunk(sim, player_pos, anchor):
    if anchor is None:
        return False
    if player_pos is not None:
        player_chunk = _chunk_for_anchor(sim, (player_pos.x, player_pos.y, player_pos.z))
    else:
        player_chunk = getattr(sim, "active_chunk_coord", None)
    if player_chunk is None:
        return True
    return _chunk_for_anchor(sim, anchor) == player_chunk


def _direction(dx, dy):
    parts = []
    if dy < 0:
        parts.append("N")
    elif dy > 0:
        parts.append("S")
    if dx < 0:
        parts.append("W")
    elif dx > 0:
        parts.append("E")
    return "".join(parts) or "HERE"


def _distance_text(distance, dx=0, dy=0):
    distance = max(0, int(distance))
    if distance == 0:
        return "here"
    if distance == 1:
        return "adjacent"
    return f"{distance} {_direction(dx, dy)}"


def _profile_for(scene):
    phase = _text((scene or {}).get("event_phase")).lower()
    if phase in _PHASE_PROFILES:
        return _PHASE_PROFILES[phase]
    scene_type = _text((scene or {}).get("scene_type")).lower()
    if scene_type in _SCENE_TYPE_PROFILES:
        return _SCENE_TYPE_PROFILES[scene_type]
    return {
        "title": _title_from_slug(phase or scene_type),
        "summary": "something local is active enough to leave visible traces",
        "action": "look for the fixture, question people nearby, or move on",
    }


def _scene_fixture_names(sim, scene, *, limit=2):
    names = []
    for property_id in tuple((scene or {}).get("spawned_property_ids", ()) or ()):
        prop = getattr(sim, "properties", {}).get(str(property_id).strip())
        if not isinstance(prop, dict):
            continue
        name = _text(prop.get("name"))
        if name and name not in names:
            names.append(name)
        if len(names) >= int(limit):
            break
    return tuple(names)


def _row_from_scene(sim, scene_id, scene, *, player_pos=None):
    if not isinstance(scene, dict):
        return None
    property_id = _text(scene.get("property_id"))
    prop = getattr(sim, "properties", {}).get(property_id)
    if not isinstance(prop, dict):
        return None
    anchor = _scene_anchor(sim, scene, prop)
    if anchor is None:
        return None
    profile = _profile_for(scene)
    dx = dy = distance = 0
    if player_pos is not None:
        dx = int(anchor[0]) - int(player_pos.x)
        dy = int(anchor[1]) - int(player_pos.y)
        distance = abs(dx) + abs(dy)
    title = _text(profile.get("title")) or "Local Situation"
    summary = _text(profile.get("summary")) or "something local is visible"
    action = _text(profile.get("action")) or "inspect it or ask around"
    fixture_names = _scene_fixture_names(sim, scene)
    return {
        "scene_id": _text(scene.get("scene_id")) or _text(scene_id),
        "property_id": property_id,
        "property_name": _property_name(prop),
        "title": title,
        "summary": summary,
        "action": action,
        "event_phase": _text(scene.get("event_phase")).lower(),
        "scene_type": _text(scene.get("scene_type")).lower(),
        "traffic_state": _text(scene.get("traffic_state")).lower(),
        "community_tone": _text(scene.get("community_tone")).lower(),
        "source_kind": _text(scene.get("source_kind")).lower(),
        "anchor": anchor,
        "distance": int(distance),
        "distance_text": _distance_text(distance, dx, dy),
        "fixture_names": fixture_names,
    }


def local_situation_rows(sim, player_eid=None, *, limit=4, current_chunk_only=True):
    """Return compact rows for active local situations near the player."""

    player_pos = _player_position(sim, player_eid)
    rows = []
    for scene_id, scene in _active_scene_store(sim).items():
        row = _row_from_scene(sim, scene_id, scene, player_pos=player_pos)
        if not row:
            continue
        if current_chunk_only and not _same_chunk(sim, player_pos, row.get("anchor")):
            continue
        rows.append(row)
    seen_properties = {
        _text(row.get("property_id")).lower()
        for row in rows
        if _text(row.get("property_id"))
    }
    for prop in getattr(sim, "properties", {}).values():
        if not isinstance(prop, dict):
            continue
        property_id = _text(prop.get("id"))
        if property_id.lower() in seen_properties:
            continue
        anchor = property_focus_position(prop) or property_display_position(prop)
        if anchor is None:
            continue
        if current_chunk_only and not _same_chunk(sim, player_pos, anchor):
            continue
        pressure = local_protective_pressure_snapshot(sim, prop)
        if not pressure.get("active"):
            continue
        dx = dy = distance = 0
        if player_pos is not None:
            dx = int(anchor[0]) - int(player_pos.x)
            dy = int(anchor[1]) - int(player_pos.y)
            distance = abs(dx) + abs(dy)
        rows.append(
            {
                "scene_id": f"protective:{property_id}",
                "property_id": property_id,
                "property_name": _property_name(prop),
                "title": _text(pressure.get("state_label")) or "Local Pressure",
                "summary": _text(pressure.get("summary")) or "the block has turned watchful",
                "action": _text(pressure.get("action")) or "read the posture or keep moving",
                "event_phase": _text(pressure.get("state_key")).lower(),
                "scene_type": "protective_pressure",
                "traffic_state": "",
                "community_tone": "",
                "source_kind": "protective_pressure",
                "anchor": anchor,
                "distance": int(distance),
                "distance_text": _distance_text(distance, dx, dy),
                "fixture_names": (),
            }
        )
    rows.sort(key=lambda row: (int(row.get("distance", 0)), str(row.get("title", "")), str(row.get("property_name", ""))))
    return tuple(rows[: max(0, int(limit))])


def local_situation_report_lines(sim, player_eid, *, limit=4):
    """Return player-facing operations report lines for active local situations."""

    lines = []
    for row in local_situation_rows(sim, player_eid, limit=limit, current_chunk_only=True):
        fixtures = tuple(row.get("fixture_names", ()) or ())
        fixture_text = f" Fixture: {fixtures[0]}." if fixtures else ""
        lines.append(
            f"{row['title']} at {row['property_name']} ({row['distance_text']}): "
            f"{row['summary']}; {row['action']}.{fixture_text}"
        )
    return tuple(lines)


def _scene_for_property(sim, prop):
    if not isinstance(prop, dict):
        return None
    property_id = _text(prop.get("id"))
    metadata = property_metadata(prop)
    scene_id = _text(metadata.get("business_scene_id"))
    scene = _active_scene_by_id(sim, scene_id)
    if scene is not None:
        return scene

    linked_property_id = _text(metadata.get("linked_property_id"))
    linked_building_id = _text(metadata.get("linked_building_id"))
    own_building_id = building_id_from_property(prop)
    for candidate in _active_scene_store(sim).values():
        if not isinstance(candidate, dict):
            continue
        candidate_property_id = _text(candidate.get("property_id"))
        if property_id and candidate_property_id == property_id:
            return candidate
        if linked_property_id and candidate_property_id == linked_property_id:
            return candidate
        candidate_prop = getattr(sim, "properties", {}).get(candidate_property_id)
        candidate_building_id = building_id_from_property(candidate_prop)
        if own_building_id and candidate_building_id and own_building_id == candidate_building_id:
            return candidate
        if linked_building_id and candidate_building_id and linked_building_id == candidate_building_id:
            return candidate
    return None


def local_situation_look_text_for_property(sim, prop, viewer_eid=None):
    """Return a terse look-mode situation cue for a property or scene fixture."""

    scene = _scene_for_property(sim, prop)
    if scene is None:
        pressure = local_protective_pressure_snapshot(sim, prop)
        if not pressure.get("active"):
            return ""
        return (
            f"situation:{_text(pressure.get('state_label')) or 'Local Pressure'} active here - "
            f"{_text(pressure.get('summary')) or 'the area is on alert'}; "
            f"{_text(pressure.get('action')) or 'read the posture or keep moving'}"
        )
    property_id = _text(scene.get("property_id"))
    scene_prop = getattr(sim, "properties", {}).get(property_id)
    if not isinstance(scene_prop, dict):
        return ""
    row = _row_from_scene(
        sim,
        _text(scene.get("scene_id")),
        scene,
        player_pos=_player_position(sim, viewer_eid),
    )
    if not row:
        return ""

    metadata = property_metadata(prop)
    if _text(metadata.get("business_scene_id")):
        fixture_name = _text(prop.get("name")) or "scene fixture"
        return (
            f"situation:{row['title']} for {row['property_name']} - "
            f"{fixture_name} is the visible handle; {row['action']}"
        )
    return f"situation:{row['title']} active here - {row['summary']}; {row['action']}"
