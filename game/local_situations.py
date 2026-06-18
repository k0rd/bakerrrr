"""Player-facing summaries for active local situations.

This module does not stage scenes. It reads already-materialized local runtime
state and turns it into compact report/look cues the player can choose to pursue.
"""

from __future__ import annotations

from game.components import AI, Position
from game.components import PlayerAssets
from game.incident_runtime import incident_record
from game.organization_presence import format_visible_property_org_presence
from game.organizations import local_protective_pressure_snapshot
from game.property_runtime import (
    building_id_from_property,
    property_display_position,
    property_focus_position,
    property_metadata,
    property_supports_business_relevance,
)
from game.system_support.crime_plan_runtime import crime_plan_surface_rows


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
    "fire_response": {
        "title": "Fire Response",
        "summary": "flame and smoke have pushed a live cordon into public view",
        "action": "read the barrier, question responders, or keep your distance",
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


_WORLD_EVENT_PROFILES = {
    "market_day": {
        "title": "Market Day",
        "summary": "a temporary market has opened in public view",
        "action": "trade, question the vendor, or watch who uses the stall",
        "property_name": "temporary market",
    },
    "black_market_window": {
        "title": "Black Market Window",
        "summary": "an off-book seller is taking quiet traffic",
        "action": "browse carefully, talk to the seller, or keep the lead to yourself",
        "property_name": "off-book stall",
    },
    "hunter_party": {
        "title": "Hunter Party",
        "summary": "hunters have set up field work around a visible game rack",
        "action": "inspect the rack or talk to the field crew",
        "property_name": "field work site",
    },
    "campout": {
        "title": "Campout",
        "summary": "a temporary camp is holding local trail traffic",
        "action": "read the camp setup or talk to the people holding it",
        "property_name": "temporary camp",
    },
    "security_sweep": {
        "title": "Security Sweep",
        "summary": "extra guards are sweeping this block",
        "action": "watch patrol routes, ask what triggered the sweep, or stay clean",
        "property_name": "this block",
    },
}


_ROW_PRIORITY_BY_SOURCE = {
    "business_event": 10,
    "business_scene": 10,
    "pulse": 10,
    "seed": 10,
    "opportunity": 10,
    "world_event": 20,
    "reported_incident_hold": 30,
    "crime_plan": 40,
    "protective_pressure": 50,
}

_HIGH_URGENCY_PHASES = {"fire_response", "street_triage"}
_OWNER_ATTENTION_PHASES = {"block_watch", "soft_front"}
_CONCRETE_SCENE_SOURCES = {"business_event", "business_scene", "pulse", "seed", "world_event"}


def _text(value):
    return str(value or "").strip()


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


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


def _world_event_profile(event):
    key = _text((event or {}).get("key")).lower()
    profile = _WORLD_EVENT_PROFILES.get(key)
    if profile:
        return profile
    return {
        "title": _text((event or {}).get("label")) or _title_from_slug(key),
        "summary": "a local event has a concrete handle here",
        "action": "look for the handle, question people nearby, or move on",
        "property_name": "this block",
    }


def _row_priority(row):
    try:
        return int(row.get("priority", 99))
    except (AttributeError, TypeError, ValueError):
        return 99


def _source_priority(source_kind, default=99):
    return _ROW_PRIORITY_BY_SOURCE.get(_text(source_kind).lower(), int(default))


def _distance_band(distance):
    distance = max(0, int(distance or 0))
    if distance <= 1:
        return 0
    if distance <= 5:
        return 1
    if distance <= 10:
        return 2
    return 3


def _row_urgency_priority(row):
    source_kind = _text((row or {}).get("source_kind")).lower()
    event_phase = _text((row or {}).get("event_phase")).lower()
    if source_kind == "reported_incident_hold" or event_phase in _HIGH_URGENCY_PHASES:
        return 0
    if source_kind == "opportunity":
        return 10
    if (
        event_phase in _OWNER_ATTENTION_PHASES
        or _text((row or {}).get("player_business_cue"))
        or _text((row or {}).get("owner_signal_kind"))
    ):
        return 20
    if source_kind in _CONCRETE_SCENE_SOURCES:
        return 30
    if source_kind == "crime_plan":
        return 80
    if source_kind == "protective_pressure":
        return 90
    return 60


def _row_dedupe_priority(row):
    source_kind = _text((row or {}).get("source_kind")).lower()
    event_phase = _text((row or {}).get("event_phase")).lower()
    if source_kind == "reported_incident_hold" or event_phase in _HIGH_URGENCY_PHASES:
        return 0
    if source_kind == "opportunity":
        return 5
    if source_kind == "world_event":
        return 8
    if source_kind in {"business_event", "business_scene", "pulse", "seed"}:
        return 10
    if source_kind == "crime_plan":
        return 80
    if source_kind == "protective_pressure":
        return 90
    return 60


def _with_rank_fields(row):
    if not isinstance(row, dict):
        return row
    result = dict(row)
    distance = int(result.get("distance", 0) or 0)
    result["distance_band"] = _distance_band(distance)
    result["urgency_priority"] = _row_urgency_priority(result)
    result["dedupe_priority"] = _row_dedupe_priority(result)
    return result


def _property_is_player_owned_site(sim, prop, player_eid=None):
    if not isinstance(prop, dict):
        return False
    if player_eid is None:
        player_eid = getattr(sim, "player_eid", None)
    owner_eid = prop.get("owner_eid")
    if owner_eid is not None and player_eid is not None:
        try:
            if int(owner_eid) == int(player_eid):
                return True
        except (TypeError, ValueError):
            if owner_eid == player_eid:
                return True
    if _text(prop.get("owner_tag")).lower() == "player":
        return True
    property_id = _text(prop.get("id"))
    assets = sim.ecs.get(PlayerAssets).get(player_eid) if sim is not None and player_eid is not None else None
    owned_ids = getattr(assets, "owned_property_ids", set()) if assets is not None else set()
    return bool(property_id and property_id in owned_ids)


def _ownership_fields(sim, prop, player_eid=None):
    owned = _property_is_player_owned_site(sim, prop, player_eid=player_eid)
    relevant = bool(owned and property_supports_business_relevance(prop))
    return {
        "is_player_owned_site": bool(owned),
        "player_business_relevance": bool(relevant),
    }


def _owner_cue_fields(scene, relevant):
    if not relevant or not isinstance(scene, dict):
        return {}
    cue = _text(scene.get("player_business_cue"))
    kind = _text(scene.get("owner_signal_kind")).lower()
    reason = _text(scene.get("owner_signal_reason"))
    if not cue:
        return {}
    return {
        "player_business_cue": cue,
        "owner_signal_kind": kind,
        "owner_signal_reason": reason,
    }


def _anchor_tuple(value):
    if not isinstance(value, (tuple, list)) or len(value) < 3:
        return None
    try:
        return (int(value[0]), int(value[1]), int(value[2]))
    except (TypeError, ValueError):
        return None


def _distance_fields(anchor, player_pos=None):
    dx = dy = distance = 0
    if player_pos is not None and anchor is not None:
        dx = int(anchor[0]) - int(player_pos.x)
        dy = int(anchor[1]) - int(player_pos.y)
        distance = abs(dx) + abs(dy)
    return {
        "distance": int(distance),
        "distance_text": _distance_text(distance, dx, dy),
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


def _row_from_scene(sim, scene_id, scene, *, player_pos=None, player_eid=None):
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
    title = _text(profile.get("title")) or "Local Situation"
    summary = _text(profile.get("summary")) or "something local is visible"
    action = _text(profile.get("action")) or "inspect it or ask around"
    fixture_names = _scene_fixture_names(sim, scene)
    organization_presence = format_visible_property_org_presence(sim, prop)
    source_kind = _text(scene.get("source_kind")).lower() or "business_scene"
    ownership = _ownership_fields(sim, prop, player_eid=player_eid)
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
        "source_kind": source_kind,
        "anchor": anchor,
        "fixture_names": fixture_names,
        "organization_presence": organization_presence,
        "priority": _source_priority(source_kind, default=10),
        **_distance_fields(anchor, player_pos),
        **ownership,
        **_owner_cue_fields(scene, ownership.get("player_business_relevance")),
    }


def _row_from_crime_plan(sim, prop, crew_row, *, player_pos=None, player_eid=None):
    if not isinstance(prop, dict) or not isinstance(crew_row, dict):
        return None
    anchor = crew_row.get("anchor") or property_focus_position(prop) or property_display_position(prop)
    if anchor is None:
        return None
    try:
        anchor = (int(anchor[0]), int(anchor[1]), int(anchor[2]))
    except (TypeError, ValueError, IndexError):
        return None
    org_name = _text(crew_row.get("organization_name")) or "a local crew"
    method = _text(crew_row.get("method_label")) or "crew move"
    stage = _text(crew_row.get("stage_label")) or "active"
    role = _text(crew_row.get("site_role")) or "site"
    return {
        "scene_id": f"crew_activity:{_text(crew_row.get('plan_key'))}:{role}",
        "property_id": _text(prop.get("id")),
        "property_name": _property_name(prop),
        "title": "Crew Activity",
        "summary": f"{org_name} is {stage} a {method} at this {role}",
        "action": _text(crew_row.get("action")) or "scan or inspect to mark the crew activity",
        "event_phase": _text(crew_row.get("stage")).lower(),
        "scene_type": "crew_activity",
        "traffic_state": "",
        "community_tone": "",
        "source_kind": "crime_plan",
        "anchor": anchor,
        "fixture_names": (),
        "organization_presence": org_name,
        "priority": _source_priority("crime_plan"),
        **_distance_fields(anchor, player_pos),
        **_ownership_fields(sim, prop, player_eid=player_eid),
    }


def _active_world_event_store(sim):
    traits = getattr(sim, "world_traits", {})
    state = traits.get("world_events") if isinstance(traits, dict) else None
    active = state.get("active", ()) if isinstance(state, dict) else ()
    return tuple(event for event in active if isinstance(event, dict))


def _row_from_world_event_property(sim, event, prop, *, player_pos=None, player_eid=None):
    if not isinstance(event, dict) or not isinstance(prop, dict):
        return None
    key = _text(event.get("key")).lower()
    if key not in _WORLD_EVENT_PROFILES:
        return None
    anchor = property_focus_position(prop) or property_display_position(prop)
    anchor = _anchor_tuple(anchor)
    if anchor is None:
        return None
    profile = _world_event_profile(event)
    property_id = _text(prop.get("id"))
    event_id = _int(event.get("id"), 0)
    title = _text(profile.get("title")) or _text(event.get("label")) or _title_from_slug(key)
    return {
        "scene_id": f"world_event:{event_id}:{key}:{property_id}",
        "property_id": property_id,
        "property_name": _property_name(prop),
        "title": title,
        "summary": _text(profile.get("summary")) or "a local event has a concrete handle here",
        "action": _text(profile.get("action")) or "look for the handle or ask around",
        "event_phase": key,
        "scene_type": "world_event",
        "traffic_state": "",
        "community_tone": "",
        "source_kind": "world_event",
        "anchor": anchor,
        "fixture_names": (),
        "organization_presence": "",
        "priority": _source_priority("world_event"),
        "world_event_id": event_id,
        "world_event_key": key,
        **_distance_fields(anchor, player_pos),
        **_ownership_fields(sim, prop, player_eid=player_eid),
    }


def _event_actor_anchor(sim, event, *, player_pos=None):
    positions = sim.ecs.get(Position)
    best = None
    best_rank = None
    for raw_eid in tuple(event.get("spawned_entity_ids", ()) or ()):
        eid = _int(raw_eid, -1)
        if eid < 0:
            continue
        pos = positions.get(eid)
        if pos is None:
            continue
        anchor = (int(pos.x), int(pos.y), int(pos.z))
        if player_pos is not None:
            distance = abs(anchor[0] - int(player_pos.x)) + abs(anchor[1] - int(player_pos.y))
        else:
            distance = 0
        rank = (distance, int(eid))
        if best_rank is None or rank < best_rank:
            best = anchor
            best_rank = rank
    return best


def _row_from_world_event_actor(sim, event, *, player_pos=None):
    if not isinstance(event, dict):
        return None
    key = _text(event.get("key")).lower()
    if key not in _WORLD_EVENT_PROFILES:
        return None
    anchor = _event_actor_anchor(sim, event, player_pos=player_pos)
    if anchor is None:
        return None
    event_id = _int(event.get("id"), 0)
    profile = _world_event_profile(event)
    return {
        "scene_id": f"world_event:{event_id}:{key}",
        "property_id": "",
        "property_name": _text(profile.get("property_name")) or "this block",
        "title": _text(profile.get("title")) or _text(event.get("label")) or _title_from_slug(key),
        "summary": _text(profile.get("summary")) or "a local event has active people here",
        "action": _text(profile.get("action")) or "watch the people holding it or ask around",
        "event_phase": key,
        "scene_type": "world_event",
        "traffic_state": "",
        "community_tone": "",
        "source_kind": "world_event",
        "anchor": anchor,
        "fixture_names": (),
        "organization_presence": "",
        "priority": _source_priority("world_event"),
        "world_event_id": event_id,
        "world_event_key": key,
        "is_player_owned_site": False,
        "player_business_relevance": False,
        **_distance_fields(anchor, player_pos),
    }


def _world_event_rows(sim, *, player_pos=None, player_eid=None):
    rows = []
    for event in _active_world_event_store(sim):
        key = _text(event.get("key")).lower()
        if key not in _WORLD_EVENT_PROFILES:
            continue
        if not bool(event.get("materialized")):
            continue
        property_rows = []
        for property_id in tuple(event.get("spawned_property_ids", ()) or ()):
            prop = getattr(sim, "properties", {}).get(_text(property_id))
            row = _row_from_world_event_property(
                sim,
                event,
                prop,
                player_pos=player_pos,
                player_eid=player_eid,
            )
            if row:
                property_rows.append(row)
        if property_rows:
            rows.extend(property_rows)
            continue
        if key in {"security_sweep", "hunter_party", "campout"}:
            row = _row_from_world_event_actor(sim, event, player_pos=player_pos)
            if row:
                rows.append(row)
    return tuple(rows)


def _world_event_row_for_property(sim, prop, *, player_pos=None, player_eid=None):
    if not isinstance(prop, dict):
        return None
    property_id = _text(prop.get("id"))
    metadata = property_metadata(prop)
    metadata_event_id = _int(metadata.get("world_event_id"), 0)
    metadata_key = _text(metadata.get("world_event_key")).lower()
    for event in _active_world_event_store(sim):
        if not bool(event.get("materialized")):
            continue
        key = _text(event.get("key")).lower()
        if key not in _WORLD_EVENT_PROFILES:
            continue
        event_id = _int(event.get("id"), 0)
        spawned_ids = {_text(pid) for pid in tuple(event.get("spawned_property_ids", ()) or ())}
        if property_id not in spawned_ids and not (metadata_event_id and metadata_event_id == event_id):
            continue
        if metadata_key and metadata_key != key:
            continue
        row = _row_from_world_event_property(
            sim,
            event,
            prop,
            player_pos=player_pos,
            player_eid=player_eid,
        )
        if row:
            return row
    return None


def _incident_anchor(incident):
    if not isinstance(incident, dict):
        return None
    if incident.get("x") is None or incident.get("y") is None:
        return None
    return (
        _int(incident.get("x"), 0),
        _int(incident.get("y"), 0),
        _int(incident.get("z"), 0),
    )


def _row_from_reported_incident_hold(sim, holder_eid, ai, incident, *, player_pos=None, player_eid=None):
    if not isinstance(incident, dict):
        return None
    positions = sim.ecs.get(Position)
    pos = positions.get(holder_eid)
    anchor = _anchor_tuple(getattr(ai, "target", None))
    if anchor is None and pos is not None:
        anchor = (int(pos.x), int(pos.y), int(pos.z))
    if anchor is None:
        anchor = _incident_anchor(incident)
    if anchor is None:
        return None
    incident_id = _int(incident.get("id"), _int(getattr(ai, "incident_id", 0), 0))
    property_id = _text(incident.get("property_id"))
    prop = getattr(sim, "properties", {}).get(property_id)
    property_name = ""
    ownership = {"is_player_owned_site": False, "player_business_relevance": False}
    if isinstance(prop, dict):
        property_name = _property_name(prop)
        ownership = _ownership_fields(sim, prop, player_eid=player_eid)
    else:
        property_name = _text(incident.get("property_name")) or "nearby incident hold"
    officially_reported = bool(incident.get("officially_reported") or incident.get("justice_accounted"))
    summary = (
        "a reported incident has someone holding the scene in public view"
        if officially_reported
        else "someone is holding the scene while a report route is active"
    )
    return {
        "scene_id": f"reported_hold:{incident_id}",
        "property_id": property_id if isinstance(prop, dict) else "",
        "property_name": property_name,
        "title": "Reported Hold",
        "summary": summary,
        "action": "question the holder, inspect the scene, or give it room",
        "event_phase": _text(incident.get("kind")).lower(),
        "scene_type": "reported_incident_hold",
        "traffic_state": "",
        "community_tone": "",
        "source_kind": "reported_incident_hold",
        "anchor": anchor,
        "fixture_names": (),
        "organization_presence": "",
        "priority": _source_priority("reported_incident_hold"),
        "incident_id": incident_id,
        "holder_eid": int(holder_eid),
        **_distance_fields(anchor, player_pos),
        **ownership,
    }


def _reported_incident_hold_rows(sim, *, player_pos=None, player_eid=None):
    rows = []
    ais = sim.ecs.get(AI)
    for holder_eid, ai in tuple(ais.items()):
        if _text(getattr(ai, "state", "")).lower() != "holding":
            continue
        incident_id = _int(getattr(ai, "incident_id", 0), 0)
        if incident_id <= 0:
            continue
        incident = incident_record(sim, incident_id)
        if not isinstance(incident, dict):
            continue
        row = _row_from_reported_incident_hold(
            sim,
            holder_eid,
            ai,
            incident,
            player_pos=player_pos,
            player_eid=player_eid,
        )
        if row:
            rows.append(row)
    return tuple(rows)


def _reported_incident_hold_row_for_property(sim, prop, *, player_pos=None, player_eid=None):
    if not isinstance(prop, dict):
        return None
    property_id = _text(prop.get("id"))
    for row in _reported_incident_hold_rows(sim, player_pos=player_pos, player_eid=player_eid):
        if property_id and _text(row.get("property_id")) == property_id:
            return row
    return None


def _row_from_protective_pressure(sim, prop, pressure, *, player_pos=None, player_eid=None):
    if not isinstance(prop, dict) or not isinstance(pressure, dict):
        return None
    if not pressure.get("active"):
        return None
    anchor = property_focus_position(prop) or property_display_position(prop)
    anchor = _anchor_tuple(anchor)
    if anchor is None:
        return None
    property_id = _text(prop.get("id"))
    return {
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
        "fixture_names": (),
        "organization_presence": format_visible_property_org_presence(sim, prop),
        "priority": _source_priority("protective_pressure"),
        **_distance_fields(anchor, player_pos),
        **_ownership_fields(sim, prop, player_eid=player_eid),
    }


def _row_dedupe_key(row):
    property_id = _text(row.get("property_id")).lower()
    if property_id:
        return f"property:{property_id}"
    scene_id = _text(row.get("scene_id")).lower()
    if scene_id:
        return f"scene:{scene_id}"
    anchor = row.get("anchor")
    return f"{_text(row.get('source_kind')).lower()}:{anchor}"


def _row_prefer_key(row):
    return (
        int(row.get("dedupe_priority", _row_dedupe_priority(row)) or 0),
        int(row.get("urgency_priority", _row_urgency_priority(row)) or 0),
        int(row.get("distance", 0) or 0),
        _row_priority(row),
        _text(row.get("title")).lower(),
        _text(row.get("property_name")).lower(),
    )


def _dedupe_and_sort_rows(rows, *, limit=4):
    best_by_key = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        row = _with_rank_fields(row)
        key = _row_dedupe_key(row)
        current = best_by_key.get(key)
        if current is None or _row_prefer_key(row) < _row_prefer_key(current):
            best_by_key[key] = row
    deduped = list(best_by_key.values())
    deduped.sort(
        key=lambda row: (
            int(row.get("distance_band", _distance_band(row.get("distance", 0))) or 0),
            int(row.get("urgency_priority", _row_urgency_priority(row)) or 0),
            int(row.get("distance", 0) or 0),
            _row_priority(row),
            _text(row.get("title")).lower(),
            _text(row.get("property_name")).lower(),
        )
    )
    return tuple(deduped[: max(0, int(limit))])


def local_situation_rows(sim, player_eid=None, *, limit=4, current_chunk_only=True):
    """Return compact rows for active local situations near the player."""

    player_pos = _player_position(sim, player_eid)
    rows = []
    for scene_id, scene in _active_scene_store(sim).items():
        row = _row_from_scene(sim, scene_id, scene, player_pos=player_pos, player_eid=player_eid)
        if not row:
            continue
        if current_chunk_only and not _same_chunk(sim, player_pos, row.get("anchor")):
            continue
        rows.append(row)

    for row in _world_event_rows(sim, player_pos=player_pos, player_eid=player_eid):
        if current_chunk_only and not _same_chunk(sim, player_pos, row.get("anchor")):
            continue
        rows.append(row)

    for row in _reported_incident_hold_rows(sim, player_pos=player_pos, player_eid=player_eid):
        if current_chunk_only and not _same_chunk(sim, player_pos, row.get("anchor")):
            continue
        rows.append(row)

    for prop in getattr(sim, "properties", {}).values():
        if not isinstance(prop, dict):
            continue
        anchor = property_focus_position(prop) or property_display_position(prop)
        if anchor is None:
            continue
        if current_chunk_only and not _same_chunk(sim, player_pos, anchor):
            continue
        crew_rows = crime_plan_surface_rows(sim, prop=prop)
        if not crew_rows:
            continue
        row = _row_from_crime_plan(sim, prop, crew_rows[0], player_pos=player_pos, player_eid=player_eid)
        if not row:
            continue
        rows.append(row)

    for prop in getattr(sim, "properties", {}).values():
        if not isinstance(prop, dict):
            continue
        anchor = property_focus_position(prop) or property_display_position(prop)
        if anchor is None:
            continue
        if current_chunk_only and not _same_chunk(sim, player_pos, anchor):
            continue
        pressure = local_protective_pressure_snapshot(sim, prop)
        row = _row_from_protective_pressure(
            sim,
            prop,
            pressure,
            player_pos=player_pos,
            player_eid=player_eid,
        )
        if row:
            rows.append(row)

    return _dedupe_and_sort_rows(rows, limit=limit)


def local_situation_report_lines(sim, player_eid, *, limit=4):
    """Return player-facing operations report lines for active local situations."""

    lines = []
    for row in local_situation_rows(sim, player_eid, limit=limit, current_chunk_only=True):
        fixtures = tuple(row.get("fixture_names", ()) or ())
        fixture_text = f" Fixture: {fixtures[0]}." if fixtures else ""
        org_text = f" Orgs: {row['organization_presence']}." if _text(row.get("organization_presence")) else ""
        owner_cue = _text(row.get("player_business_cue"))
        if row.get("player_business_relevance") and owner_cue:
            owner_text = f" Your business is directly involved: {owner_cue}."
        elif row.get("player_business_relevance"):
            owner_text = " Your business is directly involved."
        else:
            owner_text = ""
        lines.append(
            f"{row['title']} at {row['property_name']} ({row['distance_text']}): "
            f"{row['summary']}; {row['action']}.{org_text}{fixture_text}{owner_text}"
        )
    return tuple(lines)


def _look_owner_text(row):
    if not row.get("player_business_relevance"):
        return ""
    owner_cue = _text(row.get("player_business_cue"))
    if owner_cue:
        return f"; your business is directly involved: {owner_cue}"
    return "; your business is directly involved"


def _look_org_text(row):
    return f"; orgs {row['organization_presence']}" if _text(row.get("organization_presence")) else ""


def _format_property_look_row(row):
    if not row:
        return ""
    return (
        f"situation:{row['title']} active here - {row['summary']}; {row['action']}"
        + _look_org_text(row)
        + _look_owner_text(row)
    )


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

    player_pos = _player_position(sim, viewer_eid)
    candidates = []
    scene = _scene_for_property(sim, prop)
    if scene is not None:
        row = _row_from_scene(
            sim,
            _text(scene.get("scene_id")),
            scene,
            player_pos=player_pos,
            player_eid=viewer_eid,
        )
        if row:
            candidates.append(row)

    world_event_row = _world_event_row_for_property(
        sim,
        prop,
        player_pos=player_pos,
        player_eid=viewer_eid,
    )
    if world_event_row:
        candidates.append(world_event_row)

    incident_hold_row = _reported_incident_hold_row_for_property(
        sim,
        prop,
        player_pos=player_pos,
        player_eid=viewer_eid,
    )
    if incident_hold_row:
        candidates.append(incident_hold_row)

    crew_rows = crime_plan_surface_rows(sim, prop=prop)
    if crew_rows:
        row = _row_from_crime_plan(
            sim,
            prop,
            crew_rows[0],
            player_pos=player_pos,
            player_eid=viewer_eid,
        )
        if row:
            candidates.append(row)

    pressure = local_protective_pressure_snapshot(sim, prop)
    pressure_row = _row_from_protective_pressure(
        sim,
        prop,
        pressure,
        player_pos=player_pos,
        player_eid=viewer_eid,
    )
    if pressure_row:
        candidates.append(pressure_row)

    rows = _dedupe_and_sort_rows(candidates, limit=1)
    if not rows:
        return ""
    row = rows[0]

    metadata = property_metadata(prop)
    if _text(metadata.get("business_scene_id")) and row.get("source_kind") not in {
        "world_event",
        "reported_incident_hold",
        "crime_plan",
        "protective_pressure",
    }:
        fixture_name = _text(prop.get("name")) or "scene fixture"
        return (
            f"situation:{row['title']} for {row['property_name']} - "
            f"{fixture_name} is the visible handle; {row['action']}"
            + _look_org_text(row)
            + _look_owner_text(row)
        )
    if row.get("source_kind") == "world_event":
        fixture_name = _text(prop.get("name")) or _text(row.get("property_name")) or "event handle"
        return (
            f"situation:{row['title']} active here - "
            f"{fixture_name} is the visible handle; {row['action']}"
            + _look_owner_text(row)
        )
    return _format_property_look_row(row)
