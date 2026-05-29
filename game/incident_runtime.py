"""Canonical incident registry helpers.

This runtime keeps shared, mergeable knowledge incidents out of the monolithic
systems facade so multiple systems can reference the same event identity while
the broader migration from ad-hoc memory entries continues.
"""

from __future__ import annotations


DEFAULT_INCIDENT_MERGE_RULES = {
    "action_offense": {"ticks": 6, "radius": 2},
    "property_trespass": {"ticks": 12, "radius": 1},
    "property_tamper": {"ticks": 16, "radius": 1},
    "item_stolen": {"ticks": 14, "radius": 2},
    "camera_alert": {"ticks": 10, "radius": 2},
    "disturbance": {"ticks": 8, "radius": 3},
}

DEFAULT_INCIDENT_MAX_AGE = {
    "action_offense": 140,
    "property_trespass": 180,
    "property_tamper": 240,
    "item_stolen": 260,
    "camera_alert": 180,
    "disturbance": 90,
}

INCIDENT_LINK_KINDS = {
    "victim_inventory",
    "scene_claimed",
    "precombat_stolen_from_victim",
    "scene_residue",
}


def _int_or_default(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _text(value):
    return str(value or "").strip()


def _incident_tags(tags):
    cleaned = []
    for tag in tags or ():
        text = _text(tag).lower()
        if text and text not in cleaned:
            cleaned.append(text)
    return tuple(cleaned)


def _normalize_incident_link_kind(value, default="scene_claimed"):
    key = _text(value).lower().replace(" ", "_")
    if key not in INCIDENT_LINK_KINDS:
        key = str(default or "scene_claimed")
    return key


def _normalize_linked_item_row(row, *, incident_id=None, capture_tick=0, property_id="", building_id=""):
    row = dict(row or {})
    instance_id = _text(row.get("instance_id"))
    if not instance_id:
        return None
    normalized = {
        "instance_id": instance_id,
        "item_id": _text(row.get("item_id")).lower() or None,
        "link_kind": _normalize_incident_link_kind(row.get("link_kind"), default="scene_claimed"),
        "claim_class": _text(row.get("claim_class")).lower() or None,
        "owner_eid": row.get("owner_eid"),
        "holder_eid_at_capture": row.get("holder_eid_at_capture"),
        "property_id": _text(row.get("property_id") or property_id) or None,
        "building_id": _text(row.get("building_id") or building_id) or None,
        "captured_tick": _int_or_default(row.get("captured_tick"), _int_or_default(capture_tick, 0)),
        "source_victim_eid": row.get("source_victim_eid"),
        "source_incident_id": _int_or_default(row.get("source_incident_id"), _int_or_default(incident_id, 0)) or None,
    }
    return normalized


def incident_linked_items(record):
    if not isinstance(record, dict):
        return ()
    rows = []
    for row in tuple(record.get("linked_items", ()) or ()):
        normalized = _normalize_linked_item_row(
            row,
            incident_id=record.get("id"),
            capture_tick=record.get("scene_capture_tick", record.get("created_tick", 0)),
            property_id=record.get("scene_capture_property_id", record.get("property_id", "")),
            building_id=record.get("scene_capture_building_id", ""),
        )
        if normalized is not None:
            rows.append(normalized)
    return tuple(rows)


def incident_linked_item_counts(record):
    if not isinstance(record, dict):
        return {}
    counts = {"total": 0}
    for row in incident_linked_items(record):
        counts["total"] += 1
        link_kind = _normalize_incident_link_kind(row.get("link_kind"), default="scene_claimed")
        counts[link_kind] = int(counts.get(link_kind, 0) or 0) + 1
    return counts


def record_incident_scene_items(
    sim,
    incident_id,
    *,
    capture_tick=None,
    property_id=None,
    building_id=None,
    linked_items=(),
):
    incident = incident_record(sim, incident_id)
    if not isinstance(incident, dict):
        return None
    capture_tick = _int_or_default(
        capture_tick,
        _int_or_default(incident.get("scene_capture_tick"), _int_or_default(incident.get("created_tick"), 0)),
    )
    property_id = _text(property_id or incident.get("scene_capture_property_id") or incident.get("property_id"))
    building_id = _text(building_id or incident.get("scene_capture_building_id"))
    rows = list(incident_linked_items(incident))
    seen = {
        (
            _text(row.get("instance_id")).lower(),
            _normalize_incident_link_kind(row.get("link_kind"), default="scene_claimed"),
        )
        for row in rows
    }
    for raw_row in tuple(linked_items or ()):
        normalized = _normalize_linked_item_row(
            raw_row,
            incident_id=incident.get("id"),
            capture_tick=capture_tick,
            property_id=property_id,
            building_id=building_id,
        )
        if normalized is None:
            continue
        key = (
            _text(normalized.get("instance_id")).lower(),
            _normalize_incident_link_kind(normalized.get("link_kind"), default="scene_claimed"),
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append(normalized)

    if "scene_capture_tick" not in incident:
        incident["scene_capture_tick"] = capture_tick
    else:
        incident["scene_capture_tick"] = min(
            _int_or_default(incident.get("scene_capture_tick"), capture_tick),
            capture_tick,
        )
    if property_id:
        incident["scene_capture_property_id"] = property_id
    if building_id:
        incident["scene_capture_building_id"] = building_id
    incident["linked_items"] = tuple(rows)
    incident["linked_item_counts"] = incident_linked_item_counts(incident)
    return incident


def _incident_state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits

    state = traits.get("knowledge_incidents")
    if not isinstance(state, dict):
        state = {}
        traits["knowledge_incidents"] = state

    incidents = state.get("incidents")
    if not isinstance(incidents, dict):
        incidents = {}
        state["incidents"] = incidents

    recent_ids = state.get("recent_ids")
    if not isinstance(recent_ids, list):
        recent_ids = []
        state["recent_ids"] = recent_ids

    state["next_id"] = max(1, _int_or_default(state.get("next_id"), 1))
    state["last_pruned_tick"] = _int_or_default(state.get("last_pruned_tick"), -10_000)
    return state


def incident_registry(sim):
    return _incident_state(sim).get("incidents", {})


def incident_record(sim, incident_id):
    try:
        key = int(incident_id)
    except (TypeError, ValueError):
        return None
    return incident_registry(sim).get(key)


def incident_records(sim):
    incidents = incident_registry(sim)
    return tuple(
        incidents[incident_id]
        for incident_id in sorted(incidents.keys())
        if isinstance(incidents.get(incident_id), dict)
    )


def incident_propagation_allowed(record, propagation_depth):
    if not isinstance(record, dict):
        return False
    depth = max(0, _int_or_default(propagation_depth, 0))
    limit = max(0, _int_or_default(record.get("max_propagation"), 0))
    return depth <= limit


def _incident_max_propagation(kind, severity=0, *, official_reportable=False):
    severity = max(0, min(100, _int_or_default(severity, 0)))
    kind_key = _text(kind).lower()
    if kind_key in {"property_tamper", "item_stolen"}:
        base = 2
    elif kind_key == "camera_alert":
        base = 1
    elif kind_key == "action_offense":
        base = 1 if severity < 30 else 2
    elif kind_key == "property_trespass":
        base = 1 if severity < 15 else 2
    else:
        base = 1
    if severity >= 60:
        base += 1
    if official_reportable and severity >= 40:
        base += 1
    return max(0, min(4, base))


def _incident_merge_rule(kind):
    kind_key = _text(kind).lower()
    return dict(DEFAULT_INCIDENT_MERGE_RULES.get(kind_key, {"ticks": 8, "radius": 2}))


def _incident_max_age(kind):
    kind_key = _text(kind).lower()
    return max(30, _int_or_default(DEFAULT_INCIDENT_MAX_AGE.get(kind_key), 120))


def _incident_matches(existing, *, kind="", tick=0, x=None, y=None, z=0, primary_actor_eid=None, victim_eid=None, owner_eid=None, property_id=None, merge_subject="", merge_ticks=8, merge_radius=2):
    if not isinstance(existing, dict):
        return False
    if _text(existing.get("kind")).lower() != _text(kind).lower():
        return False

    if merge_subject:
        current_subject = _text(existing.get("merge_subject")).lower()
        if current_subject and current_subject != _text(merge_subject).lower():
            return False

    if property_id:
        current_property = _text(existing.get("property_id")).lower()
        if current_property and current_property != _text(property_id).lower():
            return False

    existing_actor = existing.get("primary_actor_eid")
    if primary_actor_eid is not None and existing_actor is not None and existing_actor != primary_actor_eid:
        return False
    existing_victim = existing.get("victim_eid")
    if victim_eid is not None and existing_victim is not None and existing_victim != victim_eid:
        return False
    existing_owner = existing.get("owner_eid")
    if owner_eid is not None and existing_owner is not None and existing_owner != owner_eid:
        return False

    last_tick = _int_or_default(existing.get("last_observed_tick"), _int_or_default(existing.get("created_tick"), 0))
    if abs(_int_or_default(tick, 0) - last_tick) > max(1, _int_or_default(merge_ticks, 8)):
        return False

    if x is None or y is None:
        return True
    ex = existing.get("x")
    ey = existing.get("y")
    ez = _int_or_default(existing.get("z"), z)
    if ex is None or ey is None:
        return True
    if _int_or_default(ez, 0) != _int_or_default(z, 0):
        return False
    distance = abs(_int_or_default(ex, 0) - _int_or_default(x, 0)) + abs(_int_or_default(ey, 0) - _int_or_default(y, 0))
    return distance <= max(0, _int_or_default(merge_radius, 2))


def create_or_merge_incident(
    sim,
    *,
    kind,
    x=None,
    y=None,
    z=0,
    tick=None,
    severity=0,
    primary_actor_eid=None,
    victim_eid=None,
    victim_name="",
    owner_eid=None,
    property_id=None,
    property_name="",
    merge_subject="",
    source_event="",
    official_reportable=False,
    note="",
    tags=(),
):
    kind_key = _text(kind).lower() or "incident"
    if tick is None:
        tick = getattr(sim, "tick", 0)
    tick = _int_or_default(tick, 0)
    severity = max(0, min(100, _int_or_default(severity, 0)))
    merge_rule = _incident_merge_rule(kind_key)
    merge_subject = _text(merge_subject).lower()
    victim_name = _text(victim_name)
    property_id = _text(property_id)
    property_name = _text(property_name)
    source_event = _text(source_event).lower()
    note = _text(note)
    tags = _incident_tags(tags)

    state = _incident_state(sim)
    incidents = state["incidents"]
    recent_ids = list(state.get("recent_ids", ()))

    candidate = None
    for incident_id in reversed(recent_ids):
        existing = incidents.get(_int_or_default(incident_id, -1))
        if not isinstance(existing, dict):
            continue
        if _incident_matches(
            existing,
            kind=kind_key,
            tick=tick,
            x=x,
            y=y,
            z=z,
            primary_actor_eid=primary_actor_eid,
            victim_eid=victim_eid,
            owner_eid=owner_eid,
            property_id=property_id,
            merge_subject=merge_subject,
            merge_ticks=merge_rule.get("ticks", 8),
            merge_radius=merge_rule.get("radius", 2),
        ):
            candidate = existing
            break

    if candidate is not None:
        combined_tags = list(_incident_tags(candidate.get("tags", ())))
        for tag in tags:
            if tag not in combined_tags:
                combined_tags.append(tag)
        source_events = list(_incident_tags(candidate.get("source_events", ())))
        if source_event and source_event not in source_events:
            source_events.append(source_event)
        candidate["last_observed_tick"] = tick
        if x is not None:
            candidate["x"] = _int_or_default(x, 0)
        if y is not None:
            candidate["y"] = _int_or_default(y, 0)
        candidate["z"] = _int_or_default(z, 0)
        candidate["severity"] = max(severity, _int_or_default(candidate.get("severity"), severity))
        candidate["official_reportable"] = bool(candidate.get("official_reportable", False) or official_reportable)
        candidate["evidence_count"] = max(1, _int_or_default(candidate.get("evidence_count"), 1)) + 1
        candidate["max_propagation"] = max(
            _int_or_default(candidate.get("max_propagation"), 0),
            _incident_max_propagation(
                kind_key,
                candidate["severity"],
                official_reportable=bool(candidate["official_reportable"]),
            ),
        )
        if victim_name:
            candidate["victim_name"] = victim_name
        if property_name:
            candidate["property_name"] = property_name
        candidate["tags"] = tuple(combined_tags)
        candidate["source_events"] = tuple(source_events)
        if note:
            candidate["note"] = note
        candidate["merge_subject"] = merge_subject or _text(candidate.get("merge_subject")).lower()
        return candidate, True

    incident_id = max(1, _int_or_default(state.get("next_id"), 1))
    state["next_id"] = incident_id + 1
    record = {
        "id": incident_id,
        "kind": kind_key,
        "created_tick": tick,
        "last_observed_tick": tick,
        "x": None if x is None else _int_or_default(x, 0),
        "y": None if y is None else _int_or_default(y, 0),
        "z": _int_or_default(z, 0),
        "primary_actor_eid": primary_actor_eid,
        "victim_eid": victim_eid,
        "victim_name": victim_name,
        "owner_eid": owner_eid,
        "property_id": property_id,
        "property_name": property_name,
        "severity": severity,
        "official_reportable": bool(official_reportable),
        "max_propagation": _incident_max_propagation(
            kind_key,
            severity,
            official_reportable=bool(official_reportable),
        ),
        "current_propagation": 0,
        "evidence_count": 1,
        "merge_subject": merge_subject,
        "note": note,
        "tags": tags,
        "source_events": tuple(tag for tag in (source_event,) if tag),
        "scene_capture_tick": None,
        "scene_capture_property_id": None,
        "scene_capture_building_id": None,
        "linked_items": (),
        "linked_item_counts": {"total": 0},
    }
    incidents[incident_id] = record
    recent_ids.append(incident_id)
    state["recent_ids"] = recent_ids[-256:]
    return record, False


def update_incident_propagation(record, propagation_depth):
    if not isinstance(record, dict):
        return None
    depth = max(0, _int_or_default(propagation_depth, 0))
    record["current_propagation"] = max(depth, _int_or_default(record.get("current_propagation"), 0))
    return record["current_propagation"]


def prune_incidents(sim, *, tick=None):
    if tick is None:
        tick = getattr(sim, "tick", 0)
    tick = _int_or_default(tick, 0)
    state = _incident_state(sim)
    incidents = state.get("incidents", {})
    removed = []
    keep_recent = []
    for incident_id in list(incidents.keys()):
        record = incidents.get(incident_id)
        if not isinstance(record, dict):
            incidents.pop(incident_id, None)
            continue
        last_tick = _int_or_default(record.get("last_observed_tick"), _int_or_default(record.get("created_tick"), tick))

        keep_recent.append(int(incident_id))
    state["recent_ids"] = keep_recent[-256:]
    state["last_pruned_tick"] = tick
    return tuple(sorted(removed))
