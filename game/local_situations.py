"""Player-facing summaries for active local situations.

This module does not stage scenes. It reads already-materialized local runtime
state and turns it into compact report/look cues the player can choose to pursue.
"""

from __future__ import annotations

from game.components import AI, Position
from game.components import PlayerAssets
from game.cult_runtime import cult_local_situation_rows
from game.economy import strongest_local_trade_pressure_for_property
from game.incident_runtime import incident_record
from game.meaningful_objects_runtime import meaningful_object_fixture_cue
from game.organization_presence import format_visible_property_org_presence
from game.organizations import (
    local_protective_pressure_snapshot,
    organization_pressure_for_property,
    organization_pressure_summary,
)
from game.property_runtime import (
    building_id_from_property,
    property_linked_property_id,
    property_display_position,
    property_focus_position,
    property_is_storefront,
    property_metadata,
    property_supports_business_relevance,
)
from game.system_support.crime_plan_runtime import crime_plan_surface_rows
from game.wire_connection import wire_target_class_for_property
from game.world_event_presentation import (
    world_event_effect_summary,
    world_event_uses_direct_row,
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
        "summary": "a temporary market has opened in public view with a real stall to use",
        "action": "trade, question the vendor, or watch who uses the crowd cover",
        "property_name": "temporary market",
    },
    "black_market_window": {
        "title": "Black Market Window",
        "summary": "an off-book seller is taking quiet traffic through a visible stall",
        "action": "browse carefully, talk to the seller, or decide whether the cheap goods are worth the risk",
        "property_name": "off-book stall",
    },
    "hunter_party": {
        "title": "Hunter Party",
        "summary": "hunters have set up field work around a visible game rack",
        "action": "inspect the rack, trade field talk, or ask the crew what moved nearby",
        "property_name": "field work site",
    },
    "campout": {
        "title": "Campout",
        "summary": "a temporary camp is holding local trail traffic around a fire ring",
        "action": "read the camp setup, ask for trail news, or use the light and people as cover",
        "property_name": "temporary camp",
    },
    "security_sweep": {
        "title": "Security Sweep",
        "summary": "extra guards are sweeping this block and widening who gets noticed",
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
    "wire_probe": 35,
    "crime_plan": 40,
    "protective_pressure": 50,
    "trade_pressure": 55,
    "organization_pressure": 58,
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
    if source_kind == "wire_probe":
        return 40
    if source_kind == "crime_plan":
        return 80
    if source_kind == "protective_pressure":
        return 90
    if source_kind == "organization_pressure":
        return 92
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
    if source_kind == "wire_probe":
        return 35
    if source_kind == "crime_plan":
        return 80
    if source_kind == "protective_pressure":
        return 90
    if source_kind == "organization_pressure":
        return 92
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
    style_kind = _text(scene.get("operating_style_kind")).lower()
    style_label = _text(scene.get("operating_style_label"))
    style_reason = _text(scene.get("operating_style_reason"))
    stock_label = _text(scene.get("stock_identity_label"))
    customer_mix = _text(scene.get("customer_mix_label"))
    staff_mood = _text(scene.get("staff_mood_label"))
    if not cue and not style_label:
        return {}
    return {
        "player_business_cue": cue,
        "owner_signal_kind": kind,
        "owner_signal_reason": reason,
        "operating_style_kind": style_kind,
        "operating_style_label": style_label,
        "operating_style_reason": style_reason,
        "stock_identity_label": stock_label,
        "customer_mix_label": customer_mix,
        "staff_mood_label": staff_mood,
    }


def _place_mood_fields(scene):
    if not isinstance(scene, dict):
        return {}
    fields = {}
    for key in (
        "place_mood_kind",
        "place_mood_label",
        "place_mood_reason",
        "place_mood_visible_cue",
        "place_mood_mechanical_tags",
        "place_texture_kind",
        "place_texture_label",
        "place_texture_reason",
        "place_texture_visible_cue",
        "place_texture_mechanical_tags",
        "place_texture_light_profile_hint",
        "rumor_weather_kind",
        "rumor_weather_label",
        "rumor_weather_summary",
        "rumor_weather_dialogue_bias",
        "ambient_ritual_kind",
        "ambient_ritual_label",
        "ambient_ritual_summary",
        "ambient_ritual_action",
        "ambient_ritual_fixture_name",
        "ambient_ritual_mechanical_tags",
    ):
        value = scene.get(key)
        if value in (None, "", (), []):
            continue
        fields[key] = value
    try:
        confidence = float(scene.get("place_mood_confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence > 0.0:
        fields["place_mood_confidence"] = max(0.0, min(1.0, confidence))
    try:
        texture_confidence = float(scene.get("place_texture_confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        texture_confidence = 0.0
    if texture_confidence > 0.0:
        fields["place_texture_confidence"] = max(0.0, min(1.0, texture_confidence))
    return fields


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


def _scene_meaningful_object_cues(sim, scene, *, player_eid=None, limit=2):
    cues = []
    for property_id in tuple((scene or {}).get("spawned_property_ids", ()) or ()):
        prop = getattr(sim, "properties", {}).get(str(property_id).strip())
        if not isinstance(prop, dict):
            continue
        cue = meaningful_object_fixture_cue(sim, prop, viewer_eid=player_eid)
        if cue and cue not in cues:
            cues.append(cue)
        if len(cues) >= int(limit):
            break
    return tuple(cues)


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
    object_cues = _scene_meaningful_object_cues(sim, scene, player_eid=player_eid)
    organization_presence = format_visible_property_org_presence(sim, prop)
    source_kind = _text(scene.get("source_kind")).lower() or "business_scene"
    ownership = _ownership_fields(sim, prop, player_eid=player_eid)
    world_event_context_key = _text(scene.get("world_event_context_key")).lower()
    world_event_context_label = _text(scene.get("world_event_context_label"))
    world_event_context_note = _text(scene.get("world_event_context_note"))
    world_event_context_effect = _text(scene.get("world_event_context_effect"))
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
        "meaningful_object_cues": object_cues,
        "meaningful_object_label": _text((object_cues[0] if object_cues else {}).get("meaningful_object_label")),
        "meaningful_object_summary": _text((object_cues[0] if object_cues else {}).get("meaningful_object_summary")),
        "meaningful_object_action": _text((object_cues[0] if object_cues else {}).get("meaningful_object_action")),
        "organization_presence": organization_presence,
        "world_event_context_key": world_event_context_key,
        "world_event_context_label": world_event_context_label,
        "world_event_context_note": world_event_context_note,
        "world_event_context_effect": world_event_context_effect,
        "priority": _source_priority(source_kind, default=10),
        **_distance_fields(anchor, player_pos),
        **ownership,
        **_owner_cue_fields(scene, ownership.get("player_business_relevance")),
        **_place_mood_fields(scene),
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
    if key not in _WORLD_EVENT_PROFILES or not world_event_uses_direct_row(key):
        return None
    anchor = property_focus_position(prop) or property_display_position(prop)
    anchor = _anchor_tuple(anchor)
    if anchor is None:
        return None
    profile = _world_event_profile(event)
    property_id = _text(prop.get("id"))
    event_id = _int(event.get("id"), 0)
    title = _text(profile.get("title")) or _text(event.get("label")) or _title_from_slug(key)
    effect_summary = world_event_effect_summary(event)
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
        "effect_summary": effect_summary,
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
    if key not in _WORLD_EVENT_PROFILES or not world_event_uses_direct_row(key):
        return None
    anchor = _event_actor_anchor(sim, event, player_pos=player_pos)
    if anchor is None:
        return None
    event_id = _int(event.get("id"), 0)
    profile = _world_event_profile(event)
    effect_summary = world_event_effect_summary(event)
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
        "effect_summary": effect_summary,
        "is_player_owned_site": False,
        "player_business_relevance": False,
        **_distance_fields(anchor, player_pos),
    }


def _world_event_rows(sim, *, player_pos=None, player_eid=None):
    rows = []
    for event in _active_world_event_store(sim):
        key = _text(event.get("key")).lower()
        if key not in _WORLD_EVENT_PROFILES or not world_event_uses_direct_row(key):
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
        if key not in _WORLD_EVENT_PROFILES or not world_event_uses_direct_row(key):
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


def _row_from_trade_pressure(sim, prop, pressure, *, player_pos=None, player_eid=None):
    if not isinstance(prop, dict) or not isinstance(pressure, dict):
        return None
    anchor = property_focus_position(prop) or property_display_position(prop)
    anchor = _anchor_tuple(anchor)
    if anchor is None:
        return None
    property_id = _text(prop.get("id"))
    item_name = _text(pressure.get("item_name")) or "stock"
    label = _text(pressure.get("label")) or "pressure"
    try:
        value = float(pressure.get("value", 0.0) or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    if value >= 0:
        summary = f"the counter has plenty of {item_name} right now"
        action = "buy cheap, sell elsewhere, or wait for the shelf to clear"
    else:
        summary = f"the counter is short on {item_name} right now"
        action = "bring some in, buy before it tightens, or ask who needs it"
    return {
        "scene_id": f"trade_pressure:{property_id}:{_text(pressure.get('item_id'))}",
        "property_id": property_id,
        "property_name": _property_name(prop),
        "title": "Trade Pressure",
        "summary": summary,
        "action": action,
        "event_phase": "trade_pressure",
        "scene_type": "trade_pressure",
        "traffic_state": "",
        "community_tone": label,
        "source_kind": "trade_pressure",
        "anchor": anchor,
        "fixture_names": (),
        "organization_presence": format_visible_property_org_presence(sim, prop),
        "priority": _source_priority("trade_pressure"),
        "trade_pressure_item_id": _text(pressure.get("item_id")),
        "trade_pressure_item_name": item_name,
        "trade_pressure_label": label,
        "trade_pressure_value": round(float(value), 3),
        **_distance_fields(anchor, player_pos),
        **_ownership_fields(sim, prop, player_eid=player_eid),
    }


def _row_from_organization_pressure(sim, prop, pressure, *, player_pos=None, player_eid=None):
    if not isinstance(prop, dict) or not isinstance(pressure, dict):
        return None
    summary = organization_pressure_summary(pressure)
    if not isinstance(summary, dict):
        return None
    anchor = property_focus_position(prop) or property_display_position(prop)
    anchor = _anchor_tuple(anchor)
    if anchor is None:
        return None
    property_id = _text(prop.get("id"))
    return {
        "scene_id": f"organization_pressure:{property_id}:{_text(pressure.get('pressure_key'))}",
        "property_id": property_id,
        "property_name": _property_name(prop),
        "title": _text(summary.get("title")) or "Org Pressure",
        "summary": _text(summary.get("summary")) or "an organization pressure line is visible here",
        "action": _text(summary.get("action")) or "ask around, read the posture, or move on",
        "event_phase": _text(pressure.get("stance")).lower() or "organization_pressure",
        "scene_type": _text(pressure.get("pressure_kind")).lower() or "organization_pressure",
        "traffic_state": "",
        "community_tone": _text(pressure.get("stance")).lower(),
        "source_kind": "organization_pressure",
        "anchor": anchor,
        "fixture_names": (),
        "organization_presence": format_visible_property_org_presence(sim, prop),
        "priority": _source_priority("organization_pressure"),
        "organization_pressure_kind": _text(pressure.get("pressure_kind")),
        "organization_pressure_stance": _text(pressure.get("stance")),
        "organization_pressure_confidence": round(float(summary.get("confidence", 0.0) or 0.0), 3),
        "organization_pressure_reasons": tuple(pressure.get("reason_tags", ()) or ()),
        **_distance_fields(anchor, player_pos),
        **_ownership_fields(sim, prop, player_eid=player_eid),
    }


def _wire_linked_property(sim, prop):
    linked_id = _text(property_linked_property_id(prop))
    if linked_id:
        linked = getattr(sim, "properties", {}).get(linked_id)
        if isinstance(linked, dict):
            return linked
    return None


def _wire_security_tier(prop, linked_prop=None):
    metadata = property_metadata(prop)
    linked_metadata = property_metadata(linked_prop)
    return max(
        1,
        min(
            5,
            _int(
                metadata.get("security_tier")
                or linked_metadata.get("security_tier")
                or metadata.get("security")
                or linked_metadata.get("security"),
                1,
            ),
        ),
    )


def _wire_expected_ice(target_class, security_tier):
    labels = ["Camera Watchdog"]
    labels.append("Door Arbiter" if _text(target_class).lower() == "access_panel" else "Compliance Daemon")
    if int(security_tier) >= 2:
        labels.append("Trace Sentinel")
    if int(security_tier) >= 3:
        labels.append("Quarantine Gate")
    if int(security_tier) >= 4:
        labels.append("Corruptor")
    return tuple(labels)


def _wire_probe_row_for_property(sim, prop, *, player_pos=None, player_eid=None):
    if not isinstance(prop, dict):
        return None
    target_class = wire_target_class_for_property(prop, deliberate=True)
    if not target_class:
        return None
    metadata = property_metadata(prop)
    linked_prop = _wire_linked_property(sim, prop)
    anchor = property_focus_position(prop) or property_display_position(prop)
    anchor = _anchor_tuple(anchor)
    if anchor is None:
        return None
    security_tier = _wire_security_tier(prop, linked_prop=linked_prop)
    expected_ice = _wire_expected_ice(target_class, security_tier)
    linked_name = _property_name(linked_prop) if isinstance(linked_prop, dict) else _property_name(prop)
    fixture_name = _property_name(prop)
    services = {
        _text(service).lower()
        for service in tuple(metadata.get("finance_services", ()) or ())
        + tuple(metadata.get("site_services", ()) or ())
        + tuple(prop.get("services", ()) or ())
        if _text(service)
    }
    fixture_type = _text(metadata.get("fixture_type") or metadata.get("archetype")).lower()
    atm_like = fixture_type in {"atm_kiosk", "banking_kiosk"} or "banking" in services
    if target_class == "access_panel":
        title = "Wire Relay Surface"
        summary = f"{fixture_name} exposes {linked_name} as a local relay and records layer"
        action = "connect with an interface, route-probe the ICE, or test relay and data programs"
    elif atm_like:
        title = "Wire Banking Mask"
        summary = f"{fixture_name} presents a synthetic banking mask with a deeper service layer behind it"
        action = "connect deliberately, talk to the mask, or try service and records programs"
    else:
        title = "Wire Service Surface"
        summary = f"{fixture_name} exposes a service index and records layer for {linked_name}"
        action = "connect with an interface, route-probe the ICE, or test talk and data programs"
    if security_tier >= 4:
        summary += "; high-grade ICE is likely"
    elif security_tier >= 2:
        summary += "; guarded ICE is likely"
    else:
        summary += "; light ICE is likely"
    return {
        "scene_id": f"wire_probe:{_text(prop.get('id'))}",
        "property_id": _text(prop.get("id")),
        "property_name": fixture_name,
        "title": title,
        "summary": summary,
        "action": action,
        "event_phase": "wire_probe",
        "scene_type": target_class,
        "traffic_state": "",
        "community_tone": "security_tier_%d" % int(security_tier),
        "source_kind": "wire_probe",
        "anchor": anchor,
        "fixture_names": (),
        "organization_presence": format_visible_property_org_presence(sim, linked_prop or prop),
        "priority": _source_priority("wire_probe"),
        "wire_target_class": target_class,
        "wire_linked_property_id": _text(property_linked_property_id(prop)),
        "wire_security_tier": int(security_tier),
        "wire_expected_ice": expected_ice,
        "wire_expected_ice_text": ", ".join(expected_ice),
        **_distance_fields(anchor, player_pos),
        **_ownership_fields(sim, linked_prop or prop, player_eid=player_eid),
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

    for row in cult_local_situation_rows(sim, player_pos=player_pos, player_eid=player_eid):
        if current_chunk_only and not _same_chunk(sim, player_pos, row.get("anchor")):
            continue
        rows.append(row)

    for prop in getattr(sim, "properties", {}).values():
        row = _wire_probe_row_for_property(sim, prop, player_pos=player_pos, player_eid=player_eid)
        if not row:
            continue
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

    for prop in getattr(sim, "properties", {}).values():
        if not isinstance(prop, dict):
            continue
        anchor = property_focus_position(prop) or property_display_position(prop)
        if anchor is None:
            continue
        if current_chunk_only and not _same_chunk(sim, player_pos, anchor):
            continue
        pressure = organization_pressure_for_property(sim, prop)
        row = _row_from_organization_pressure(
            sim,
            prop,
            pressure,
            player_pos=player_pos,
            player_eid=player_eid,
        )
        if row:
            rows.append(row)

    for prop in getattr(sim, "properties", {}).values():
        if not isinstance(prop, dict) or not property_is_storefront(prop):
            continue
        anchor = property_focus_position(prop) or property_display_position(prop)
        if anchor is None:
            continue
        if current_chunk_only and not _same_chunk(sim, player_pos, anchor):
            continue
        pressure = strongest_local_trade_pressure_for_property(sim, prop, min_abs=3.0)
        row = _row_from_trade_pressure(
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
        owner_style = _text(row.get("operating_style_label"))
        effect_summary = _text(row.get("effect_summary"))
        effect_text = f" Effect: {effect_summary}." if effect_summary else ""
        world_event_context = _text(row.get("world_event_context_note"))
        context_text = f" World event pressure: {world_event_context}." if world_event_context else ""
        mood_text = _report_place_mood_text(row)
        texture_text = _report_place_texture_text(row)
        ritual_text = _report_ambient_ritual_text(row)
        object_text = _report_meaningful_object_text(row)
        wire_text = _report_wire_text(row)
        if row.get("player_business_relevance") and owner_cue:
            owner_text = f" Your business is directly involved: {owner_cue}."
        elif row.get("player_business_relevance") and owner_style:
            owner_text = f" Your business is directly involved: {owner_style}."
        elif row.get("player_business_relevance"):
            owner_text = " Your business is directly involved."
        else:
            owner_text = ""
        lines.append(
            f"{row['title']} at {row['property_name']} ({row['distance_text']}): "
            f"{row['summary']}; {row['action']}.{org_text}{fixture_text}{effect_text}{context_text}{mood_text}{texture_text}{ritual_text}{object_text}{wire_text}{owner_text}"
        )
    return tuple(lines)


def _report_place_mood_text(row):
    label = _text(row.get("place_mood_label"))
    if not label:
        return ""
    cue = _text(row.get("place_mood_visible_cue")) or _text(row.get("place_mood_reason"))
    return f" Mood: {label} - {cue}." if cue else f" Mood: {label}."


def _report_place_texture_text(row):
    label = _text(row.get("place_texture_label"))
    if not label:
        return ""
    cue = _text(row.get("place_texture_visible_cue")) or _text(row.get("place_texture_reason"))
    rumor = _text(row.get("rumor_weather_label"))
    suffix = f"; rumor weather {rumor}" if rumor and rumor.lower() != label.lower() else ""
    return f" Texture: {label}{suffix} - {cue}." if cue else f" Texture: {label}{suffix}."


def _report_ambient_ritual_text(row):
    label = _text(row.get("ambient_ritual_label"))
    if not label:
        return ""
    summary = _text(row.get("ambient_ritual_summary"))
    return f" Ritual: {label} - {summary}." if summary else f" Ritual: {label}."


def _report_meaningful_object_text(row):
    summary = _text(row.get("meaningful_object_summary"))
    if summary:
        return f" Object: {summary}."
    label = _text(row.get("meaningful_object_label"))
    return f" Object: {label}." if label else ""


def _report_wire_text(row):
    if _text(row.get("source_kind")).lower() != "wire_probe":
        return ""
    ice_text = _text(row.get("wire_expected_ice_text"))
    security = _int(row.get("wire_security_tier"), 1)
    target_class = _text(row.get("wire_target_class")).replace("_", " ")
    bits = [f"Wire: {target_class or 'target'} security {security}"]
    if ice_text:
        bits.append(f"expected ICE {ice_text}")
    return " " + "; ".join(bits) + "."


def _look_owner_text(row):
    if not row.get("player_business_relevance"):
        return ""
    owner_cue = _text(row.get("player_business_cue"))
    if owner_cue:
        return f"; your business is directly involved: {owner_cue}"
    owner_style = _text(row.get("operating_style_label"))
    if owner_style:
        return f"; your business is directly involved: {owner_style}"
    return "; your business is directly involved"


def _look_org_text(row):
    return f"; orgs {row['organization_presence']}" if _text(row.get("organization_presence")) else ""


def _look_effect_text(row):
    effect = _text(row.get("effect_summary"))
    if effect:
        return f"; effect {effect}"
    context_note = _text(row.get("world_event_context_note"))
    if context_note:
        return f"; world event pressure {context_note}"
    return ""


def _look_place_mood_text(row):
    label = _text(row.get("place_mood_label"))
    if not label:
        return ""
    cue = _text(row.get("place_mood_visible_cue")) or _text(row.get("place_mood_reason"))
    if cue:
        return f"; mood {label} - {cue}"
    return f"; mood {label}"


def _look_place_texture_text(row):
    label = _text(row.get("place_texture_label"))
    if not label:
        return ""
    cue = _text(row.get("place_texture_visible_cue")) or _text(row.get("rumor_weather_summary"))
    if cue:
        return f"; texture {label} - {cue}"
    return f"; texture {label}"


def _look_ambient_ritual_text(row):
    label = _text(row.get("ambient_ritual_label"))
    if not label:
        return ""
    action = _text(row.get("ambient_ritual_action")) or _text(row.get("ambient_ritual_summary"))
    if action:
        return f"; ritual {label} - {action}"
    return f"; ritual {label}"


def _look_meaningful_object_text(row):
    label = _text(row.get("meaningful_object_label"))
    if not label:
        return ""
    action = _text(row.get("meaningful_object_action")) or "inspect it"
    return f"; object {label} - {action}"


def _look_wire_text(row):
    if _text(row.get("source_kind")).lower() != "wire_probe":
        return ""
    ice_text = _text(row.get("wire_expected_ice_text"))
    security = _int(row.get("wire_security_tier"), 1)
    if ice_text:
        return f"; wire security {security}; expected ICE {ice_text}"
    return f"; wire security {security}"


def _format_property_look_row(row):
    if not row:
        return ""
    return (
        f"situation:{row['title']} active here - {row['summary']}; {row['action']}"
        + _look_org_text(row)
        + _look_effect_text(row)
        + _look_place_mood_text(row)
        + _look_place_texture_text(row)
        + _look_ambient_ritual_text(row)
        + _look_meaningful_object_text(row)
        + _look_wire_text(row)
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

    wire_row = _wire_probe_row_for_property(
        sim,
        prop,
        player_pos=player_pos,
        player_eid=viewer_eid,
    )
    if wire_row:
        candidates.append(wire_row)

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

    org_pressure = organization_pressure_for_property(sim, prop)
    org_pressure_row = _row_from_organization_pressure(
        sim,
        prop,
        org_pressure,
        player_pos=player_pos,
        player_eid=viewer_eid,
    )
    if org_pressure_row:
        candidates.append(org_pressure_row)

    if property_is_storefront(prop):
        trade_pressure = strongest_local_trade_pressure_for_property(sim, prop, min_abs=3.0)
        trade_pressure_row = _row_from_trade_pressure(
            sim,
            prop,
            trade_pressure,
            player_pos=player_pos,
            player_eid=viewer_eid,
        )
        if trade_pressure_row:
            candidates.append(trade_pressure_row)

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
            + _look_effect_text(row)
            + _look_place_mood_text(row)
            + _look_place_texture_text(row)
            + _look_ambient_ritual_text(row)
            + _look_owner_text(row)
        )
    if row.get("source_kind") == "world_event":
        fixture_name = _text(prop.get("name")) or _text(row.get("property_name")) or "event handle"
        return (
            f"situation:{row['title']} active here - "
            f"{fixture_name} is the visible handle; {row['action']}"
            + _look_effect_text(row)
            + _look_place_mood_text(row)
            + _look_place_texture_text(row)
            + _look_ambient_ritual_text(row)
            + _look_owner_text(row)
        )
    return _format_property_look_row(row)
