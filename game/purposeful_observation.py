"""Shared, save-safe intent records for NPCs deliberately watching a subject.

This module does not decide *why* an NPC begins watching somebody.  Sneaking,
bodyguard, criminal-drive, social, justice, and drone systems retain that
authority.  It owns the smaller common contract those decisions need: an
honest last-seen snapshot, a purpose-specific stand-off band, and bounded
behavior after visual contact is lost.  A subject may be an actor or a fixed
world anchor such as the public-facing aperture of a property being cased.
"""

from __future__ import annotations

from collections import deque
from copy import deepcopy

from engine.events import Event
from engine.visibility import observer_can_see_position
from engine.visibility import has_line_of_sight
from game.components import AI, Collider, CreatureIdentity, Position, Vitality
from game.identity_evidence import build_witness_subject_account, description_match_score


PURPOSEFUL_OBSERVATION_KIND = "purposeful_observation"
PURPOSEFUL_STREAM_KEEPALIVE_TICKS = 96


# Only live consumers belong here.  Future purposes should be added as their
# behavior lands, not speculatively just because the roadmap names them.
_PURPOSE_PROFILES = {
    "visible_sneak": {
        "posture": "tailing",
        "min_distance": 3,
        "preferred_distance": 4,
        "max_distance": 5,
        "requires_los": True,
        "loss_policy": "search_last_seen",
        "lost_contact_grace_ticks": 4,
        "search_radius": 5,
        "search_waypoint_limit": 6,
        "search_duration_ticks": 36,
        "reacquisition_radius": 10,
        "reacquisition_policy": "description_candidates",
        "candidate_limit": 12,
        "candidate_min_score": 0.62,
        "candidate_min_evidence": 0.28,
    },
    "criminal_casing": {
        "posture": "casing",
        "min_distance": 2,
        "preferred_distance": 3,
        "max_distance": 5,
        "requires_los": True,
        "loss_policy": "reposition_or_abort",
        "lost_contact_grace_ticks": 4,
        "required_observation_ticks": 6,
    },
    "bodyguard_formation": {
        "posture": "escorting",
        "min_distance": 1,
        "preferred_distance": 2,
        "max_distance": 3,
        "requires_los": True,
        "loss_policy": "return_to_last_seen",
        "lost_contact_grace_ticks": 6,
        "search_radius": 6,
        "search_waypoint_limit": 6,
        "search_duration_ticks": 42,
        "reacquisition_radius": 14,
    },
    "bodyguard_threat_watch": {
        "posture": "screening",
        "min_distance": 1,
        "preferred_distance": 4,
        "max_distance": 8,
        "requires_los": True,
        "loss_policy": "release_warning",
        "lost_contact_grace_ticks": 6,
    },
    "hired_backup": {
        "posture": "escorting",
        "min_distance": 2,
        "preferred_distance": 3,
        "max_distance": 4,
        "requires_los": True,
        "loss_policy": "approach_last_seen",
        "lost_contact_grace_ticks": 6,
        "search_radius": 6,
        "search_waypoint_limit": 6,
        "search_duration_ticks": 48,
        "reacquisition_radius": 12,
    },
    "social_companion": {
        "posture": "accompanying",
        "min_distance": 2,
        "preferred_distance": 3,
        "max_distance": 5,
        "requires_los": True,
        "loss_policy": "approach_last_seen",
        "lost_contact_grace_ticks": 8,
        "search_radius": 5,
        "search_waypoint_limit": 5,
        "search_duration_ticks": 42,
        "reacquisition_radius": 12,
    },
    "peaceful_follow": {
        "posture": "accompanying",
        "min_distance": 1,
        "preferred_distance": 2,
        "max_distance": 3,
        "requires_los": True,
        "loss_policy": "approach_last_seen",
        "lost_contact_grace_ticks": 6,
        "search_radius": 4,
        "search_waypoint_limit": 4,
        "search_duration_ticks": 32,
        "reacquisition_radius": 10,
    },
    "justice_identity_check": {
        "posture": "approaching_for_questioning",
        "min_distance": 1,
        "preferred_distance": 1,
        "max_distance": 2,
        "requires_los": True,
        "loss_policy": "approach_last_seen",
        "lost_contact_grace_ticks": 6,
        "search_radius": 6,
        "search_waypoint_limit": 6,
        "search_duration_ticks": 48,
        "reacquisition_radius": 10,
        # The player-facing question flow can honestly lose a changed-looking
        # player now.  Redirecting the legal interaction onto a similar NPC is
        # reserved for the evidence-handoff/false-lead layer, where that NPC can
        # actually answer or be questioned rather than becoming a dummy target.
        "reacquisition_policy": "description_subject",
        "candidate_limit": 10,
        "candidate_min_score": 0.62,
        "candidate_min_evidence": 0.28,
    },
    "justice_report_search": {
        "posture": "following_reported_description",
        "min_distance": 1,
        "preferred_distance": 1,
        "max_distance": 2,
        "requires_los": True,
        "loss_policy": "search_reported_position",
        "lost_contact_grace_ticks": 0,
        # A report creates a patient local search, never a hidden actor tether.
        # These bounds operate on maintained local spatial indexes.
        "search_radius": 10,
        "search_waypoint_limit": 10,
        "search_duration_ticks": 84,
        "reacquisition_radius": 13,
        "reacquisition_policy": "description_candidates",
        "candidate_limit": 16,
        "candidate_min_score": 0.64,
        "candidate_min_evidence": 0.28,
        # A received description may nominate somebody at a distance, but the
        # handoff is not complete until the responder gets close enough to
        # compare the report against their own observation.
        "candidate_requires_contact_verification": True,
    },
    "justice_detention": {
        "posture": "approaching_for_custody",
        "min_distance": 1,
        "preferred_distance": 1,
        "max_distance": 2,
        "requires_los": True,
        "loss_policy": "approach_last_seen",
        "lost_contact_grace_ticks": 6,
        "search_radius": 7,
        "search_waypoint_limit": 7,
        "search_duration_ticks": 60,
        "reacquisition_radius": 12,
    },
    "bounty_pickup": {
        "posture": "answering_pickup_call",
        "min_distance": 1,
        "preferred_distance": 1,
        "max_distance": 2,
        "requires_los": True,
        "loss_policy": "verify_reported_position",
        "lost_contact_grace_ticks": 8,
    },
    "drone_person_watch": {
        "posture": "tracking",
        "min_distance": 3,
        "preferred_distance": 4,
        "max_distance": 6,
        "requires_los": True,
        "loss_policy": "search_last_seen",
        "lost_contact_grace_ticks": 4,
        "search_radius": 6,
        "search_waypoint_limit": 6,
        "search_duration_ticks": 42,
        "reacquisition_radius": 10,
        "reacquisition_policy": "known_subject",
    },
    "drone_threat_watch": {
        "posture": "intercepting_contact",
        "min_distance": 2,
        "preferred_distance": 3,
        "max_distance": 5,
        # Radar and IR may establish a legitimate contact without ordinary
        # visual LOS.  Their own sensor geometry remains authoritative.
        "requires_los": False,
        "loss_policy": "search_last_seen",
        "lost_contact_grace_ticks": 3,
        "search_radius": 5,
        "search_waypoint_limit": 5,
        "search_duration_ticks": 36,
        "reacquisition_radius": 10,
        "reacquisition_policy": "known_subject",
    },
}


def _clean_key(value):
    return str(value or "").strip().lower().replace(" ", "_")


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_or(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _position_xyz(value):
    if isinstance(value, (tuple, list)) and len(value) >= 3:
        try:
            return (int(value[0]), int(value[1]), int(value[2]))
        except (TypeError, ValueError):
            return None
    try:
        return (int(value.x), int(value.y), int(value.z))
    except (AttributeError, TypeError, ValueError):
        return None


def _position_is_in_property(sim, property_id, position):
    property_key = str(property_id or "").strip()
    xyz = _position_xyz(position)
    if not property_key or xyz is None:
        return False
    coordinate = (xyz[0], xyz[1], xyz[2])
    if property_key in tuple(getattr(sim, "property_anchor_index", {}).get(coordinate, ()) or ()):
        return True
    if property_key in tuple(getattr(sim, "property_cover_index", {}).get(coordinate, ()) or ()):
        return True
    if not hasattr(sim, "property_covering"):
        return False
    prop = sim.property_covering(xyz[0], xyz[1], xyz[2])
    return isinstance(prop, dict) and str(prop.get("id", "") or "").strip() == property_key


def _search_profile(context):
    profile = observation_purpose_profile(observation_context_purpose(context))
    radius = max(0, _int_or(context.get("search_radius"), profile.get("search_radius", 0)))
    waypoint_limit = max(
        0,
        _int_or(context.get("search_waypoint_limit"), profile.get("search_waypoint_limit", 0)),
    )
    duration = max(
        0,
        _int_or(context.get("search_duration_ticks"), profile.get("search_duration_ticks", 0)),
    )
    return radius, waypoint_limit, duration


def _search_tile_feature_score(sim, x, y, z):
    tile = sim.tilemap.tile_at(int(x), int(y), int(z))
    semantic = _clean_key(getattr(tile, "semantic_id", "")) if tile is not None else ""
    glyph = str(getattr(tile, "glyph", "") or "") if tile is not None else ""
    if any(token in semantic for token in ("door", "breach", "stair", "elevator", "ramp", "passage")):
        return 18
    if glyph in {"+", "'", "<", ">", "^", "v"}:
        return 12
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        neighbor = sim.tilemap.tile_at(int(x) + dx, int(y) + dy, int(z))
        neighbor_semantic = _clean_key(getattr(neighbor, "semantic_id", "")) if neighbor is not None else ""
        neighbor_glyph = str(getattr(neighbor, "glyph", "") or "") if neighbor is not None else ""
        if any(token in neighbor_semantic for token in ("door", "breach", "stair", "elevator", "ramp", "passage")):
            return 14
        if neighbor_glyph in {"+", "'", "<", ">", "^", "v"}:
            return 9
    return 0


def _bounded_reachable_search_cells(sim, origin, *, radius):
    """Return only locally reachable cells around an honestly seen origin."""

    origin_xyz = _position_xyz(origin)
    radius = max(0, int(radius))
    if origin_xyz is None or radius <= 0:
        return []
    ox, oy, oz = origin_xyz
    if not sim.tilemap.is_walkable(ox, oy, oz):
        return []
    queue = deque([(ox, oy)])
    distances = {(ox, oy): 0}
    while queue:
        x, y = queue.popleft()
        distance = distances[(x, y)]
        if distance >= radius:
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if (nx, ny) in distances:
                continue
            if abs(nx - ox) + abs(ny - oy) > radius:
                continue
            if not sim.tilemap.in_bounds(nx, ny) or not sim.tilemap.is_walkable(nx, ny, oz):
                continue
            distances[(nx, ny)] = distance + 1
            queue.append((nx, ny))
    return [(x, y, oz, distance) for (x, y), distance in distances.items()]


def purposeful_search_waypoints(sim, context):
    """Build a deterministic, bounded search of the last-seen local topology.

    The route favors the subject's observed heading, apertures, intersections,
    and spatially distinct checks.  It never consults the subject's current
    position or scans actors for a match.
    """

    if not is_purposeful_observation(context, active_only=True):
        return ()
    origin = _position_xyz(context.get("last_seen_position"))
    radius, waypoint_limit, _duration = _search_profile(context)
    if origin is None or radius <= 0 or waypoint_limit <= 0:
        return ()
    cells = _bounded_reachable_search_cells(sim, origin, radius=radius)
    if not cells:
        return ()

    previous = _position_xyz(context.get("previous_seen_position"))
    heading_x = heading_y = 0
    if previous is not None and previous[2] == origin[2]:
        heading_x = 1 if origin[0] > previous[0] else -1 if origin[0] < previous[0] else 0
        heading_y = 1 if origin[1] > previous[1] else -1 if origin[1] < previous[1] else 0

    candidates = []
    for x, y, z, distance in cells:
        if (x, y, z) == origin:
            continue
        open_neighbors = sum(
            1
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            if sim.tilemap.is_walkable(x + dx, y + dy, z)
        )
        projection = ((x - origin[0]) * heading_x) + ((y - origin[1]) * heading_y)
        base_score = (
            _search_tile_feature_score(sim, x, y, z)
            + max(-4, min(8, projection * 3))
            + (6 if open_neighbors >= 3 else 0)
            + min(radius, int(distance))
        )
        candidates.append((base_score, int(distance), int(x), int(y), int(z)))

    selected = [origin]
    while candidates and len(selected) < waypoint_limit:
        ranked = []
        for base_score, distance, x, y, z in candidates:
            separation = min(abs(x - sx) + abs(y - sy) for sx, sy, _sz in selected)
            ranked.append((base_score + (separation * 3), distance, -y, -x, x, y, z))
        _score, _distance, _ny, _nx, x, y, z = max(ranked)
        selected.append((x, y, z))
        candidates = [row for row in candidates if (row[2], row[3], row[4]) != (x, y, z)]
    return tuple(selected)


def _emit_search_transition(sim, event_type, context, *, position=None, reason=None):
    transition_xyz = _position_xyz(position) or _position_xyz(context.get("last_seen_position"))
    observer_eid = _int_or_none(context.get("observer_eid"))
    observer_xyz = _position_xyz(sim.ecs.get(Position).get(observer_eid)) if observer_eid is not None else None
    xyz = observer_xyz or transition_xyz
    data = {
        "observer_eid": observer_eid,
        "subject_eid": _int_or_none(context.get("subject_eid")),
        "original_subject_eid": _int_or_none(context.get("original_subject_eid")),
        "purpose": observation_context_purpose(context),
        "reason": _clean_key(reason) or None,
        "transition_position": transition_xyz,
        "incident_id": _int_or_none(context.get("incident_id")),
        "reporter_eid": _int_or_none(context.get("reporter_eid")),
        "knowledge_channel": _clean_key(context.get("knowledge_channel")) or None,
        "casework_kind": _clean_key(context.get("casework_kind")) or None,
        "received_report": _clean_key(context.get("origin_kind")) == "received_report",
        "identity_resolved": bool(context.get("identity_resolved", True)),
    }
    if xyz is not None:
        data.update({"x": xyz[0], "y": xyz[1], "z": xyz[2]})
    search = context.get("search_state")
    if isinstance(search, dict):
        data["search_origin"] = _position_xyz(search.get("origin"))
        data["waypoint_count"] = len(tuple(search.get("waypoints", ()) or ()))
        data["visited_count"] = len(tuple(search.get("visited", ()) or ()))
    reacquisition = context.get("last_reacquisition")
    if isinstance(reacquisition, dict):
        data.update({
            "reacquisition_basis": _clean_key(reacquisition.get("basis")) or None,
            "candidate_changed": bool(reacquisition.get("candidate_changed", False)),
            "match_score": reacquisition.get("match_score"),
            "evidence_weight": reacquisition.get("evidence_weight"),
            "matched_cues": tuple(reacquisition.get("matched_cues", ()) or ()),
            "conflicting_cues": tuple(reacquisition.get("conflicting_cues", ()) or ()),
            "evaluated_candidate_count": max(0, _int_or(reacquisition.get("evaluated_candidate_count"), 0)),
        })
    sim.emit(Event(str(event_type), **data))


def _actor_is_reacquisition_candidate(sim, eid, *, observer_eid):
    if eid is None or eid == observer_eid:
        return False
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    if identity is None:
        return eid == getattr(sim, "player_eid", None)
    if _clean_key(getattr(identity, "creature_type", "")) != "human":
        return False
    vitality = sim.ecs.get(Vitality).get(eid)
    if vitality is not None and (
        bool(getattr(vitality, "downed", False))
        or _int_or(getattr(vitality, "hp", 1), 1) <= 0
    ):
        return False
    return True


def purposeful_reacquisition_read(sim, observer_eid, context, *, sight_radius=None):
    """Choose a plausible *visible local* subject after genuine contact loss.

    This is deliberately demand-driven: it runs only for an observer already in
    the bounded loss/search lifecycle and past its continuity grace, starts from
    the maintained local entity index, caps detailed comparisons, and observes
    each candidate at current light and distance.  The original witness account
    remains the comparison source and is never rewritten by a later candidate.
    """

    result = {
        "candidate_eid": None,
        "candidate_account": {},
        "match": {},
        "evaluated_candidate_count": 0,
        "visible_candidate_count": 0,
        "rejected_candidates": (),
        "policy": "",
    }
    if not is_purposeful_observation(context, active_only=True):
        return result
    search = context.get("search_state") if isinstance(context, dict) else None
    search_active = isinstance(search, dict) and search.get("active") is True
    lost_since = _int_or_none(context.get("lost_contact_since_tick"))
    grace = max(0, _int_or(context.get("lost_contact_grace_ticks"), 0))
    reacquisition_due = bool(
        search_active
        or (
            lost_since is not None
            and int(getattr(sim, "tick", 0) or 0) - lost_since > grace
        )
    )
    if not reacquisition_due:
        return result
    purpose = observation_context_purpose(context)
    profile = observation_purpose_profile(purpose)
    policy = _clean_key(context.get("reacquisition_policy", profile.get("reacquisition_policy")))
    result["policy"] = policy
    if policy not in {"description_candidates", "description_subject"}:
        return result

    observer_pos = sim.ecs.get(Position).get(observer_eid)
    account = context.get("subject_account") if isinstance(context.get("subject_account"), dict) else {}
    description = account.get("description") if isinstance(account.get("description"), dict) else {}
    if observer_pos is None or not description:
        return result

    radius = max(
        1,
        _int_or(
            sight_radius,
            context.get("reacquisition_radius", profile.get("reacquisition_radius", profile.get("max_distance", 8))),
        ),
    )
    original_subject_eid = _int_or_none(context.get("original_subject_eid"))
    if original_subject_eid is None:
        original_subject_eid = _int_or_none(context.get("subject_eid"))
    limit = max(1, _int_or(context.get("candidate_limit"), profile.get("candidate_limit", 10)))
    minimum_score = max(0.0, min(1.0, float(context.get("candidate_min_score", profile.get("candidate_min_score", 0.62)) or 0.62)))
    minimum_evidence = max(0.0, min(1.0, float(context.get("candidate_min_evidence", profile.get("candidate_min_evidence", 0.28)) or 0.28)))

    nearby = []
    rejected_eids = {
        candidate_eid
        for candidate_eid in (
            _int_or_none(value)
            for value in tuple(context.get("rejected_candidate_eids", ()) or ())
        )
        if candidate_eid is not None
    }
    for eid in sim.entity_ids_in_radius(observer_pos.x, observer_pos.y, observer_pos.z, radius):
        candidate_eid = _int_or_none(eid)
        if not _actor_is_reacquisition_candidate(sim, candidate_eid, observer_eid=observer_eid):
            continue
        if candidate_eid in rejected_eids:
            continue
        if policy == "description_subject" and candidate_eid != original_subject_eid:
            continue
        candidate_pos = sim.ecs.get(Position).get(candidate_eid)
        if candidate_pos is None or int(candidate_pos.z) != int(observer_pos.z):
            continue
        distance = abs(int(candidate_pos.x) - int(observer_pos.x)) + abs(int(candidate_pos.y) - int(observer_pos.y))
        nearby.append((distance, int(candidate_eid), candidate_pos))
    nearby.sort(key=lambda row: (row[0], row[1]))

    ranked = []
    rejected = []
    for distance, candidate_eid, candidate_pos in nearby[:limit]:
        if not observer_can_see_position(
            sim,
            observer_eid=observer_eid,
            observer_x=observer_pos.x,
            observer_y=observer_pos.y,
            observer_z=observer_pos.z,
            target_x=candidate_pos.x,
            target_y=candidate_pos.y,
            target_z=candidate_pos.z,
            radius=radius,
        ):
            continue
        result["visible_candidate_count"] += 1
        current_account = build_witness_subject_account(
            sim,
            observer_eid,
            candidate_eid,
            source_kind="search_reacquisition",
        )
        current_description = current_account.get("description") if isinstance(current_account.get("description"), dict) else {}
        match = description_match_score(description, current_description)
        result["evaluated_candidate_count"] += 1

        currently_recognized = _int_or_none(current_account.get("suspect_eid")) == candidate_eid
        originally_recognized = _int_or_none(account.get("suspect_eid")) == original_subject_eid
        identity_confirmation = bool(
            candidate_eid == original_subject_eid
            and originally_recognized
            and currently_recognized
        )
        identity_contradiction = bool(
            candidate_eid != original_subject_eid
            and originally_recognized
            and currently_recognized
        )
        if identity_contradiction:
            match = dict(match)
            match["conflicting_cues"] = tuple(match.get("conflicting_cues", ()) or ()) + ("recognized identity",)
        plausible = bool(
            not identity_contradiction
            and (
                identity_confirmation
                or (
                    match.get("plausible")
                    and float(match.get("score", 0.0) or 0.0) >= minimum_score
                    and float(match.get("evidence_weight", 0.0) or 0.0) >= minimum_evidence
                )
            )
        )
        if not plausible:
            if identity_contradiction or float(match.get("evidence_weight", 0.0) or 0.0) >= minimum_evidence:
                rejected.append({
                    "candidate_eid": int(candidate_eid),
                    "distance": int(distance),
                    "reason": "recognized_identity_contradiction" if identity_contradiction else "appearance_contradiction",
                    "match": deepcopy(match),
                    "candidate_account": deepcopy(current_account),
                })
            continue
        rank = (
            0 if identity_confirmation else 1,
            -float(match.get("score", 0.0) or 0.0),
            -float(match.get("evidence_weight", 0.0) or 0.0),
            int(distance),
            int(candidate_eid),
        )
        ranked.append((rank, candidate_eid, current_account, match, identity_confirmation))

    rejected.sort(key=lambda row: (
        -float((row.get("match") or {}).get("evidence_weight", 0.0) or 0.0),
        -float((row.get("match") or {}).get("score", 0.0) or 0.0),
        int(row.get("distance", 10_000)),
        int(row.get("candidate_eid", 0)),
    ))
    result["rejected_candidates"] = tuple(rejected[:limit])
    if not ranked:
        return result
    _rank, candidate_eid, current_account, match, identity_confirmation = min(ranked, key=lambda row: row[0])
    result.update({
        "candidate_eid": int(candidate_eid),
        "candidate_account": deepcopy(current_account),
        "match": deepcopy(match),
        "identity_confirmation": bool(identity_confirmation),
    })
    return result


def observation_purpose_profile(purpose):
    """Return a defensive copy of one landed observation-purpose policy."""

    return dict(_PURPOSE_PROFILES.get(_clean_key(purpose), {}))


def _profile_with_distance_band(profile, distance_band):
    result = dict(profile or {})
    if distance_band is None:
        return result
    if isinstance(distance_band, dict):
        minimum = _int_or(distance_band.get("min_distance"), result.get("min_distance", 0))
        preferred = _int_or(distance_band.get("preferred_distance"), result.get("preferred_distance", minimum))
        maximum = _int_or(distance_band.get("max_distance"), result.get("max_distance", preferred))
    elif isinstance(distance_band, (tuple, list)) and len(distance_band) >= 3:
        minimum = _int_or(distance_band[0], result.get("min_distance", 0))
        preferred = _int_or(distance_band[1], result.get("preferred_distance", minimum))
        maximum = _int_or(distance_band[2], result.get("max_distance", preferred))
    else:
        return result
    minimum = max(0, minimum)
    maximum = max(minimum, maximum)
    preferred = max(minimum, min(maximum, preferred))
    result["min_distance"] = minimum
    result["preferred_distance"] = preferred
    result["max_distance"] = maximum
    return result


def observation_context_purpose(context):
    if not isinstance(context, dict):
        return ""
    purpose = _clean_key(context.get("purpose"))
    if purpose:
        return purpose
    # Read the pre-kernel sneak shape so a loaded in-flight actor can migrate
    # naturally the next time it sees the subject.
    if _clean_key(context.get("kind")) == "visible_sneak":
        return "visible_sneak"
    return ""


def is_purposeful_observation(context, *, purpose=None, active_only=False):
    if not isinstance(context, dict):
        return False
    context_purpose = observation_context_purpose(context)
    if not context_purpose:
        return False
    if purpose is not None and context_purpose != _clean_key(purpose):
        return False
    if active_only and context.get("active") is False:
        return False
    return _clean_key(context.get("kind")) in {PURPOSEFUL_OBSERVATION_KIND, "visible_sneak"}


def observation_watch_position(
    sim,
    observer_eid,
    subject_pos,
    *,
    purpose,
    exclude_property_id=None,
    distance_band=None,
    preferred_position=None,
):
    """Choose a walkable, unoccupied watch cell inside the purpose's band.

    A cell that cannot actually see the subject is not a valid observation
    post.  This prevents a tail from carefully pathing to the correct distance
    on the wrong side of a wall.
    """

    profile = _profile_with_distance_band(observation_purpose_profile(purpose), distance_band)
    observer_pos = sim.ecs.get(Position).get(observer_eid)
    subject_xyz = _position_xyz(subject_pos)
    if not profile or observer_pos is None or subject_xyz is None:
        return None
    subject_x, subject_y, subject_z = subject_xyz
    if int(observer_pos.z) != subject_z:
        return None

    minimum = max(0, int(profile.get("min_distance", 0) or 0))
    maximum = max(minimum, int(profile.get("max_distance", minimum) or minimum))
    preferred = max(minimum, min(maximum, int(profile.get("preferred_distance", minimum) or minimum)))
    preferred_xyz = _position_xyz(preferred_position)
    requires_los = bool(profile.get("requires_los", True))
    current = (int(observer_pos.x), int(observer_pos.y), int(observer_pos.z))
    current_distance = abs(int(observer_pos.x) - subject_x) + abs(int(observer_pos.y) - subject_y)
    if minimum <= current_distance <= maximum and not _position_is_in_property(
        sim,
        exclude_property_id,
        current,
    ):
        if not requires_los or has_line_of_sight(
            sim,
            int(observer_pos.x),
            int(observer_pos.y),
            int(observer_pos.z),
            subject_x,
            subject_y,
            subject_z,
        ):
            return current

    colliders = sim.ecs.get(Collider)
    ais = sim.ecs.get(AI)
    candidates = []
    for dx in range(-maximum, maximum + 1):
        for dy in range(-maximum, maximum + 1):
            distance = abs(dx) + abs(dy)
            if distance < minimum or distance > maximum:
                continue
            tx = subject_x + dx
            ty = subject_y + dy
            tz = subject_z
            if not sim.tilemap.in_bounds(tx, ty) or not sim.tilemap.is_walkable(tx, ty, tz):
                continue
            if _position_is_in_property(sim, exclude_property_id, (tx, ty, tz)):
                continue
            if any(
                other_eid != observer_eid
                and (
                    ais.get(other_eid) is not None
                    or bool(getattr(colliders.get(other_eid), "blocks", False))
                )
                for other_eid in sim.tilemap.entities_at(tx, ty, tz)
            ):
                continue
            if requires_los and not has_line_of_sight(
                sim,
                tx,
                ty,
                tz,
                subject_x,
                subject_y,
                subject_z,
            ):
                continue
            travel = abs(int(observer_pos.x) - tx) + abs(int(observer_pos.y) - ty)
            slot_bias = (
                abs(tx - preferred_xyz[0]) + abs(ty - preferred_xyz[1])
                if preferred_xyz is not None and preferred_xyz[2] == tz
                else 0
            )
            candidates.append((
                travel + (abs(distance - preferred) * 2) + (slot_bias * 2),
                slot_bias,
                travel,
                tx,
                ty,
                tz,
            ))

    if not candidates:
        return None
    _, _, _, tx, ty, tz = min(candidates)
    return (tx, ty, tz)


def begin_purposeful_anchor_observation(
    sim,
    observer_eid,
    anchor_position,
    *,
    purpose,
    anchor_kind="world_position",
    anchor_id=None,
    watch_position=None,
    existing=None,
):
    """Create a deliberate-observation record for a fixed world anchor.

    Choosing a post does not itself count as observing.  Progress begins only
    after the observer reaches that post and the anchor is still in line of
    sight.  This distinction prevents pathing toward a known site from
    magically completing surveillance.
    """

    purpose_key = _clean_key(purpose)
    profile = observation_purpose_profile(purpose_key)
    anchor_xyz = _position_xyz(anchor_position)
    if not profile:
        raise ValueError(f"unknown purposeful observation profile: {purpose_key or purpose!r}")
    if anchor_xyz is None:
        raise ValueError("purposeful anchor observation requires a positioned anchor")
    if watch_position is None:
        watch_position = observation_watch_position(
            sim,
            observer_eid,
            anchor_xyz,
            purpose=purpose_key,
            exclude_property_id=anchor_id if _clean_key(anchor_kind) == "property_aperture" else None,
        )
    watch_xyz = _position_xyz(watch_position)
    if watch_xyz is None:
        raise ValueError("purposeful anchor observation requires a valid watch position")

    tick = int(getattr(sim, "tick", 0) or 0)
    previous = dict(existing or {}) if is_purposeful_observation(existing, purpose=purpose_key, active_only=True) else {}
    same_anchor = (
        _position_xyz(previous.get("anchor_position")) == anchor_xyz
        and _clean_key(previous.get("anchor_kind")) == _clean_key(anchor_kind)
        and str(previous.get("anchor_id") or "") == str(anchor_id or "")
    )
    if not same_anchor:
        previous = {}

    return {
        "kind": PURPOSEFUL_OBSERVATION_KIND,
        "purpose": purpose_key,
        "posture": str(profile.get("posture", "watching") or "watching"),
        "active": True,
        "observer_eid": _int_or_none(observer_eid),
        "subject_eid": None,
        "anchor_kind": _clean_key(anchor_kind) or "world_position",
        "anchor_id": str(anchor_id or "").strip() or None,
        "anchor_position": anchor_xyz,
        "excluded_property_id": str(anchor_id or "").strip() if _clean_key(anchor_kind) == "property_aperture" else None,
        "offense_assumed": False,
        "started_tick": _int_or(previous.get("started_tick"), tick) if previous else tick,
        "updated_tick": tick,
        "observation_count": max(0, _int_or(previous.get("observation_count"), 0)),
        "observed_ticks": max(0, _int_or(previous.get("observed_ticks"), 0)),
        "required_observation_ticks": max(1, int(profile.get("required_observation_ticks", 1) or 1)),
        "observation_started_tick": _int_or_none(previous.get("observation_started_tick")),
        "last_observed_tick": _int_or_none(previous.get("last_observed_tick")),
        "last_progress_tick": _int_or_none(previous.get("last_progress_tick")),
        "lost_contact_since_tick": None,
        "watch_position": watch_xyz,
        "min_distance": int(profile.get("min_distance", 0) or 0),
        "preferred_distance": int(profile.get("preferred_distance", 0) or 0),
        "max_distance": int(profile.get("max_distance", 0) or 0),
        "requires_los": bool(profile.get("requires_los", True)),
        "loss_policy": str(profile.get("loss_policy", "reposition_or_abort") or "reposition_or_abort"),
        "lost_contact_grace_ticks": max(0, int(profile.get("lost_contact_grace_ticks", 0) or 0)),
        "subject_account": {},
        # Fixed anchors also expose the generic position aliases used by
        # diagnostics and event presentation.
        "source_eid": None,
        "x": anchor_xyz[0],
        "y": anchor_xyz[1],
        "z": anchor_xyz[2],
    }


def begin_purposeful_report_search(
    sim,
    observer_eid,
    reported_position,
    *,
    subject_account,
    incident_id=None,
    reporter_eid=None,
    knowledge_channel="dispatch_handoff",
    approach_position=None,
    previous_seen_position=None,
    report_conflict_count=0,
    canvas_enabled=False,
    canvas_limit=0,
    canvas_until_exhausted=False,
    casework_kind="",
):
    """Create a dormant, save-safe search from genuinely received evidence.

    The responder receives a place and a subjective account, never a hidden
    actor coordinate.  Search geometry is not generated until they reach the
    reported area, so a radio call does not simulate knowledge of every exit
    while the responder is still across town.
    """

    profile = observation_purpose_profile("justice_report_search")
    origin = _position_xyz(reported_position)
    observer_pos = sim.ecs.get(Position).get(observer_eid)
    if origin is None or observer_pos is None:
        raise ValueError("received-report search requires positioned responder and report")
    approach = _position_xyz(approach_position) or origin
    tick = int(getattr(sim, "tick", 0) or 0)
    account = deepcopy(subject_account) if isinstance(subject_account, dict) else {}
    alleged_subject_eid = _int_or_none(account.get("suspect_eid"))
    return {
        "kind": PURPOSEFUL_OBSERVATION_KIND,
        "purpose": "justice_report_search",
        "posture": str(profile.get("posture", "following_reported_description")),
        "active": True,
        "observer_eid": _int_or_none(observer_eid),
        "subject_eid": None,
        "original_subject_eid": alleged_subject_eid,
        "origin_kind": "received_report",
        "offense_assumed": False,
        "incident_id": _int_or_none(incident_id),
        "reporter_eid": _int_or_none(reporter_eid),
        "knowledge_channel": _clean_key(knowledge_channel) or "dispatch_handoff",
        "report_conflict_count": max(0, _int_or(report_conflict_count, 0)),
        "casework_kind": _clean_key(casework_kind) or None,
        "canvas_enabled": bool(canvas_enabled),
        "canvas_limit": max(0, _int_or(canvas_limit, 0)),
        "canvas_until_exhausted": bool(canvas_enabled and canvas_until_exhausted),
        "canvassed_eids": (),
        "canvas_contacts": (),
        "received_tick": tick,
        "started_tick": tick,
        "updated_tick": tick,
        "last_seen_tick": _int_or((account.get("observation") or {}).get("tick"), tick),
        "last_seen_position": origin,
        "previous_seen_position": _position_xyz(previous_seen_position),
        "approach_position": approach,
        "watch_position": approach,
        "min_distance": int(profile.get("min_distance", 1) or 1),
        "preferred_distance": int(profile.get("preferred_distance", 1) or 1),
        "max_distance": int(profile.get("max_distance", 2) or 2),
        "requires_los": bool(profile.get("requires_los", True)),
        "loss_policy": str(profile.get("loss_policy", "search_reported_position")),
        "lost_contact_grace_ticks": max(0, int(profile.get("lost_contact_grace_ticks", 0) or 0)),
        "lost_contact_since_tick": tick,
        "search_radius": max(0, int(profile.get("search_radius", 0) or 0)),
        "search_waypoint_limit": max(0, int(profile.get("search_waypoint_limit", 0) or 0)),
        "search_duration_ticks": max(0, int(profile.get("search_duration_ticks", 0) or 0)),
        "reacquisition_radius": max(1, int(profile.get("reacquisition_radius", 10) or 10)),
        "reacquisition_policy": _clean_key(profile.get("reacquisition_policy")) or "description_candidates",
        "candidate_limit": max(1, int(profile.get("candidate_limit", 10) or 10)),
        "candidate_min_score": max(0.0, min(1.0, float(profile.get("candidate_min_score", 0.64) or 0.64))),
        "candidate_min_evidence": max(0.0, min(1.0, float(profile.get("candidate_min_evidence", 0.28) or 0.28))),
        "candidate_requires_contact_verification": bool(profile.get("candidate_requires_contact_verification", True)),
        "subject_account": account,
        "search_state": {
            "active": False,
            "phase": "approach_report",
            "origin": origin,
            "waypoints": (),
            "visited": (),
            "waypoint_index": 0,
        },
        "search_reacquisition_count": 0,
        "last_reacquisition": {},
        "rejected_candidate_eids": (),
        "candidate_rejections": (),
        "source_eid": _int_or_none(reporter_eid),
        "x": origin[0],
        "y": origin[1],
        "z": origin[2],
        "seen_tick": _int_or((account.get("observation") or {}).get("tick"), tick),
    }


def activate_purposeful_report_search(sim, context, *, current_tick=None):
    """Start the bounded route once a responder reaches the reported area."""

    if not is_purposeful_observation(context, purpose="justice_report_search", active_only=True):
        return context, "invalid", None
    tick = int(getattr(sim, "tick", 0) if current_tick is None else current_tick)
    result = dict(context)
    search = deepcopy(result.get("search_state")) if isinstance(result.get("search_state"), dict) else {}
    if search.get("active") is True:
        waypoints = tuple(_position_xyz(row) for row in tuple(search.get("waypoints", ()) or ()))
        waypoints = tuple(row for row in waypoints if row is not None)
        index = max(0, _int_or(search.get("waypoint_index"), 0))
        return result, "searching", waypoints[index] if index < len(waypoints) else None
    waypoints = purposeful_search_waypoints(sim, result)
    if not waypoints:
        ended = finish_purposeful_observation(result, current_tick=tick, reason="search_unavailable")
        _emit_search_transition(sim, "purposeful_search_abandoned", ended, reason="search_unavailable")
        return ended, "abandoned", None
    _radius, waypoint_limit, duration = _search_profile(result)
    search = {
        "active": True,
        "phase": "search_report",
        "origin": _position_xyz(result.get("last_seen_position")),
        "started_tick": tick,
        "deadline_tick": tick + duration,
        "radius": max(0, _int_or(result.get("search_radius"), 0)),
        "waypoint_limit": waypoint_limit,
        "waypoints": tuple(waypoints),
        "waypoint_index": 0,
        "visited": (),
    }
    result["search_state"] = search
    result["updated_tick"] = tick
    result["lost_contact_since_tick"] = tick - max(0, _int_or(result.get("lost_contact_grace_ticks"), 0)) - 1
    _emit_search_transition(sim, "purposeful_report_search_activated", result, reason="received_report")
    _emit_search_transition(sim, "purposeful_search_started", result, reason="received_report")
    return result, "searching", waypoints[0]


def reject_purposeful_candidate(sim, context, *, candidate_eid, reason="appearance_contradiction", match=None):
    """Return a reported-description lead to its remaining bounded search."""

    if not is_purposeful_observation(context, purpose="justice_report_search", active_only=True):
        return context
    tick = int(getattr(sim, "tick", 0) or 0)
    result = dict(context)
    candidate_id = _int_or_none(candidate_eid)
    rejected = [
        value
        for value in (_int_or_none(raw) for raw in tuple(result.get("rejected_candidate_eids", ()) or ()))
        if value is not None
    ]
    if candidate_id is not None and candidate_id not in rejected:
        rejected.append(candidate_id)
    result["rejected_candidate_eids"] = tuple(rejected[-12:])
    rows = list(tuple(result.get("candidate_rejections", ()) or ()))
    rows.append({
        "tick": tick,
        "candidate_eid": candidate_id,
        "reason": _clean_key(reason) or "appearance_contradiction",
        "match": deepcopy(match) if isinstance(match, dict) else {},
    })
    result["candidate_rejections"] = tuple(rows[-12:])
    result["subject_eid"] = None
    result["source_eid"] = _int_or_none(result.get("reporter_eid"))
    result["updated_tick"] = tick
    result["contact_pending"] = False
    search = deepcopy(result.get("search_state")) if isinstance(result.get("search_state"), dict) else {}
    if search:
        search["active"] = True
        search["phase"] = "search_report"
        search["suspended"] = False
        search.pop("ended_tick", None)
        search.pop("ended_reason", None)
        search["updated_tick"] = tick
        result["search_state"] = search
    _emit_search_transition(
        sim,
        "purposeful_search_candidate_rejected",
        result,
        reason=_clean_key(reason) or "appearance_contradiction",
    )
    return result


def record_purposeful_canvas_contact(sim, context, *, actor_eid, outcome="questioned", supplied_account=False):
    """Record one bounded investigator interview on the durable search."""

    if not is_purposeful_observation(context, purpose="justice_report_search", active_only=True):
        return context
    result = dict(context)
    actor_id = _int_or_none(actor_eid)
    canvassed = [
        value
        for value in (_int_or_none(raw) for raw in tuple(result.get("canvassed_eids", ()) or ()))
        if value is not None
    ]
    if actor_id is not None and actor_id not in canvassed:
        canvassed.append(actor_id)
    # This is the exhaustion set, not presentation history.  Keeping every
    # interviewed actor prevents a long investigation from cycling back to an
    # old witness after an arbitrary cap.  The detailed contact log below may
    # still remain bounded.
    result["canvassed_eids"] = tuple(canvassed)
    rows = list(tuple(result.get("canvas_contacts", ()) or ()))
    rows.append({
        "tick": int(getattr(sim, "tick", 0) or 0),
        "actor_eid": actor_id,
        "outcome": _clean_key(outcome) or "questioned",
        "supplied_account": bool(supplied_account),
    })
    result["canvas_contacts"] = tuple(rows[-24:])
    result["canvas_contact_pending"] = False
    result.pop("canvas_lead_eid", None)
    result.pop("canvas_lead_position", None)
    result["updated_tick"] = int(getattr(sim, "tick", 0) or 0)
    return result


def advance_purposeful_anchor_observation(sim, observer_eid, context):
    """Advance one arrived observer and return ``(record, status, target)``.

    Status is one of ``observing``, ``complete``, ``reposition``, ``lost``, or
    ``invalid``.  The returned target is populated only when repositioning is
    possible.  Elapsed simulation ticks, rather than update-call count, drive
    dwell progress so actor scheduling may remain sparse.
    """

    if not is_purposeful_observation(context, active_only=True):
        return context, "invalid", None
    anchor_xyz = _position_xyz(context.get("anchor_position"))
    watch_xyz = _position_xyz(context.get("watch_position"))
    observer_pos = sim.ecs.get(Position).get(observer_eid)
    if anchor_xyz is None or watch_xyz is None or observer_pos is None:
        return finish_purposeful_observation(context, current_tick=getattr(sim, "tick", 0), reason="invalid_anchor"), "invalid", None

    tick = int(getattr(sim, "tick", 0) or 0)
    current_xyz = (int(observer_pos.x), int(observer_pos.y), int(observer_pos.z))
    result = dict(context)
    result["updated_tick"] = tick
    if current_xyz != watch_xyz:
        return result, "reposition", watch_xyz

    anchor_x, anchor_y, anchor_z = anchor_xyz
    distance = abs(current_xyz[0] - anchor_x) + abs(current_xyz[1] - anchor_y)
    minimum = max(0, _int_or(result.get("min_distance"), 0))
    maximum = max(minimum, _int_or(result.get("max_distance"), minimum))
    visible = (
        current_xyz[2] == anchor_z
        and minimum <= distance <= maximum
        and (
            not bool(result.get("requires_los", True))
            or has_line_of_sight(
                sim,
                current_xyz[0],
                current_xyz[1],
                current_xyz[2],
                anchor_x,
                anchor_y,
                anchor_z,
            )
        )
    )
    if visible:
        last_progress_tick = _int_or_none(result.get("last_progress_tick"))
        elapsed = 1 if last_progress_tick is None else max(0, tick - last_progress_tick)
        result["observed_ticks"] = max(0, _int_or(result.get("observed_ticks"), 0)) + elapsed
        result["observation_count"] = max(0, _int_or(result.get("observation_count"), 0)) + 1
        result["observation_started_tick"] = (
            _int_or_none(result.get("observation_started_tick"))
            if result.get("observation_started_tick") is not None
            else tick
        )
        result["last_observed_tick"] = tick
        result["last_seen_tick"] = tick
        result["last_progress_tick"] = tick
        result["lost_contact_since_tick"] = None
        required = max(1, _int_or(result.get("required_observation_ticks"), 1))
        if int(result["observed_ticks"]) >= required:
            return finish_purposeful_observation(result, current_tick=tick, reason="complete"), "complete", None
        return result, "observing", None

    lost_since = _int_or_none(result.get("lost_contact_since_tick"))
    if lost_since is None:
        lost_since = tick
        result["lost_contact_since_tick"] = tick
    grace = max(0, _int_or(result.get("lost_contact_grace_ticks"), 0))
    replacement = observation_watch_position(
        sim,
        observer_eid,
        anchor_xyz,
        purpose=observation_context_purpose(result),
        exclude_property_id=result.get("excluded_property_id"),
    )
    replacement_xyz = _position_xyz(replacement)
    if replacement_xyz is not None and replacement_xyz != current_xyz:
        result["watch_position"] = replacement_xyz
        return result, "reposition", replacement_xyz
    if tick - lost_since <= grace:
        return result, "observing", None
    return finish_purposeful_observation(result, current_tick=tick, reason="lost_contact"), "lost", None


def refresh_purposeful_observation(
    sim,
    observer_eid,
    subject_eid,
    *,
    purpose,
    subject_pos=None,
    watch_position=None,
    existing=None,
    capture_subject_account=False,
    include_subject_account=True,
    distance_band=None,
    preferred_position=None,
    reacquisition_details=None,
):
    """Create or refresh the canonical observation record.

    The result contains only ordinary Python data so it can ride on the existing
    pickled AI state.  Subject appearance is captured at observation quality,
    never reconstructed later from present-day clothing and perfect light.
    """

    purpose_key = _clean_key(purpose)
    profile = _profile_with_distance_band(observation_purpose_profile(purpose_key), distance_band)
    if not profile:
        raise ValueError(f"unknown purposeful observation profile: {purpose_key or purpose!r}")
    if subject_pos is None:
        subject_pos = sim.ecs.get(Position).get(subject_eid)
    if subject_pos is None:
        raise ValueError("purposeful observation requires a positioned subject")
    if watch_position is None:
        watch_position = observation_watch_position(
            sim,
            observer_eid,
            subject_pos,
            purpose=purpose_key,
            distance_band=distance_band,
            preferred_position=preferred_position,
        )
    if watch_position is None:
        raise ValueError("purposeful observation requires a valid watch position")

    tick = int(getattr(sim, "tick", 0) or 0)
    previous = dict(existing or {}) if is_purposeful_observation(existing, purpose=purpose_key) else {}
    started_tick = _int_or(previous.get("started_tick"), tick) if "started_tick" in previous else tick
    count = max(0, _int_or(previous.get("observation_count"), 0)) + 1
    previous_last_seen = _position_xyz(previous.get("last_seen_position"))
    new_last_seen = (int(subject_pos.x), int(subject_pos.y), int(subject_pos.z))
    prior_motion_sample = _position_xyz(previous.get("previous_seen_position"))
    previous_seen_position = (
        previous_last_seen
        if previous_last_seen is not None and previous_last_seen != new_last_seen
        else prior_motion_sample
    )
    subject_account = deepcopy(previous.get("subject_account")) if isinstance(previous.get("subject_account"), dict) else {}
    if include_subject_account and (capture_subject_account or not subject_account):
        subject_account = build_witness_subject_account(
            sim,
            observer_eid,
            subject_eid,
            source_kind="deliberate_observation",
        )

    search_state = deepcopy(previous.get("search_state")) if isinstance(previous.get("search_state"), dict) else {}
    search_reacquisition_count = max(0, _int_or(previous.get("search_reacquisition_count"), 0))
    search_was_active = search_state.get("active") is True
    reacquisition_occurred = bool(search_was_active or isinstance(reacquisition_details, dict))
    original_subject_eid = _int_or_none(previous.get("original_subject_eid"))
    if original_subject_eid is None:
        original_subject_eid = _int_or_none(previous.get("subject_eid"))
    if original_subject_eid is None:
        original_subject_eid = _int_or_none(subject_eid)
    last_reacquisition = (
        deepcopy(previous.get("last_reacquisition"))
        if isinstance(previous.get("last_reacquisition"), dict)
        else {}
    )
    contact_verification = bool(
        purpose_key == "justice_report_search"
        and previous.get("candidate_requires_contact_verification", False)
    )
    if search_was_active:
        search_state["active"] = False
        search_state["ended_tick"] = tick
        search_state["ended_reason"] = "candidate_pending_verification" if contact_verification else "reacquired"
        search_state["phase"] = "candidate_pending_verification" if contact_verification else "reacquired"
    if reacquisition_occurred:
        search_reacquisition_count += 1
        details = dict(reacquisition_details or {})
        match = details.get("match") if isinstance(details.get("match"), dict) else {}
        last_reacquisition = {
            "tick": tick,
            "basis": _clean_key(details.get("basis")) or "visual_contact",
            "original_subject_eid": original_subject_eid,
            "candidate_eid": _int_or_none(subject_eid),
            "candidate_changed": _int_or_none(subject_eid) != original_subject_eid,
            "identity_confirmation": bool(details.get("identity_confirmation", False)),
            "match_score": round(float(match.get("score", 0.0) or 0.0), 3),
            "evidence_weight": round(float(match.get("evidence_weight", 0.0) or 0.0), 3),
            "matched_cues": tuple(match.get("matched_cues", ()) or ()),
            "conflicting_cues": tuple(match.get("conflicting_cues", ()) or ()),
            "evaluated_candidate_count": max(0, _int_or(details.get("evaluated_candidate_count"), 0)),
            "visible_candidate_count": max(0, _int_or(details.get("visible_candidate_count"), 0)),
            "candidate_account": deepcopy(details.get("candidate_account")) if isinstance(details.get("candidate_account"), dict) else {},
        }

    result = {
        "kind": PURPOSEFUL_OBSERVATION_KIND,
        "purpose": purpose_key,
        "posture": str(profile.get("posture", "watching") or "watching"),
        "active": True,
        "observer_eid": _int_or_none(observer_eid),
        "subject_eid": _int_or_none(subject_eid),
        "original_subject_eid": original_subject_eid,
        "offense_assumed": False,
        "started_tick": started_tick,
        "last_seen_tick": tick,
        "updated_tick": tick,
        "observation_count": count,
        "last_seen_position": new_last_seen,
        "previous_seen_position": previous_seen_position,
        "watch_position": (int(watch_position[0]), int(watch_position[1]), int(watch_position[2])),
        "preferred_position": _position_xyz(preferred_position),
        "min_distance": int(profile.get("min_distance", 0) or 0),
        "preferred_distance": int(profile.get("preferred_distance", 0) or 0),
        "max_distance": int(profile.get("max_distance", 0) or 0),
        "requires_los": bool(profile.get("requires_los", True)),
        "loss_policy": str(profile.get("loss_policy", "search_last_seen") or "search_last_seen"),
        "lost_contact_grace_ticks": max(0, int(profile.get("lost_contact_grace_ticks", 0) or 0)),
        "lost_contact_since_tick": None,
        "search_radius": max(0, int(profile.get("search_radius", 0) or 0)),
        "search_waypoint_limit": max(0, int(profile.get("search_waypoint_limit", 0) or 0)),
        "search_duration_ticks": max(0, int(profile.get("search_duration_ticks", 0) or 0)),
        "reacquisition_radius": max(1, int(profile.get("reacquisition_radius", profile.get("max_distance", 8)) or 8)),
        "reacquisition_policy": _clean_key(profile.get("reacquisition_policy")) or "known_subject",
        "candidate_limit": max(1, int(profile.get("candidate_limit", 10) or 10)),
        "candidate_min_score": max(0.0, min(1.0, float(profile.get("candidate_min_score", 0.62) or 0.62))),
        "candidate_min_evidence": max(0.0, min(1.0, float(profile.get("candidate_min_evidence", 0.28) or 0.28))),
        "candidate_requires_contact_verification": bool(
            previous.get(
                "candidate_requires_contact_verification",
                profile.get("candidate_requires_contact_verification", False),
            )
        ),
        "search_state": search_state,
        "search_reacquisition_count": search_reacquisition_count,
        "last_reacquisition": last_reacquisition,
        "subject_account": subject_account,
        # Transitional aliases keep generic investigation/debug consumers useful
        # while the richer fields remain authoritative.
        "source_eid": _int_or_none(subject_eid),
        "x": int(subject_pos.x),
        "y": int(subject_pos.y),
        "z": int(subject_pos.z),
        "seen_tick": tick,
    }
    # Received-report searches carry casework state that belongs to the report,
    # not to whichever visually plausible actor was most recently selected.
    for key in (
        "origin_kind",
        "incident_id",
        "reporter_eid",
        "knowledge_channel",
        "report_conflict_count",
        "casework_kind",
        "canvas_enabled",
        "canvas_limit",
        "canvas_until_exhausted",
        "canvassed_eids",
        "canvas_contacts",
        "lead_refresh_count",
        "last_lead_refresh_tick",
        "received_tick",
        "approach_position",
        "rejected_candidate_eids",
        "candidate_rejections",
        "contact_pending",
        "canvas_contact_pending",
    ):
        if key in previous:
            result[key] = deepcopy(previous.get(key))
    if reacquisition_occurred:
        _emit_search_transition(
            sim,
            "purposeful_search_reacquired",
            result,
            position=new_last_seen,
            reason="visual_contact",
        )
    return result


def advance_purposeful_actor_observation(
    sim,
    observer_eid,
    subject_eid,
    *,
    purpose,
    existing=None,
    sight_radius=None,
    capture_subject_account=False,
    include_subject_account=True,
    distance_band=None,
    preferred_position=None,
    refresh_visible=True,
    direct_los=False,
    sensor_visible_positions=None,
):
    """Advance honest sight, last-seen travel, local search, or abandonment.

    The assigned subject is consulted only to ask the observer's ordinary FOV
    whether that actor is presently visible.  A hidden live coordinate never
    becomes a target or influences the generated search route.
    """

    purpose_key = _clean_key(purpose)
    context = existing if is_purposeful_observation(existing, purpose=purpose_key) else None
    observer_pos = sim.ecs.get(Position).get(observer_eid)
    tracked_subject_eid = _int_or_none((context or {}).get("subject_eid"))
    if tracked_subject_eid is None:
        tracked_subject_eid = _int_or_none(subject_eid)
    subject_pos = sim.ecs.get(Position).get(tracked_subject_eid)
    tick = int(getattr(sim, "tick", 0) or 0)
    if observer_pos is None or (subject_pos is None and not is_purposeful_observation(context, active_only=True)):
        if is_purposeful_observation(context, active_only=True):
            result = finish_purposeful_observation(context, current_tick=tick, reason="invalid_subject")
            _emit_search_transition(sim, "purposeful_search_abandoned", result, reason="invalid_subject")
            return result, "invalid", None
        return context, "invalid", None

    profile = observation_purpose_profile(purpose_key)
    radius = max(
        1,
        _int_or(
            sight_radius,
            context.get("reacquisition_radius", profile.get("reacquisition_radius", profile.get("max_distance", 8)))
            if isinstance(context, dict)
            else profile.get("reacquisition_radius", profile.get("max_distance", 8)),
        ),
    )
    search = (context or {}).get("search_state") if isinstance(context, dict) else None
    search_active = isinstance(search, dict) and search.get("active") is True
    policy = _clean_key((context or {}).get("reacquisition_policy", profile.get("reacquisition_policy")))
    lost_since = _int_or_none((context or {}).get("lost_contact_since_tick"))
    grace = max(0, _int_or((context or {}).get("lost_contact_grace_ticks"), 0))
    description_reacquisition_due = bool(
        policy in {"description_candidates", "description_subject"}
        and (
            search_active
            or (lost_since is not None and tick - lost_since > grace)
        )
    )
    if description_reacquisition_due:
        candidate_read = purposeful_reacquisition_read(
            sim,
            observer_eid,
            context,
            sight_radius=radius,
        )
        candidate_eid = _int_or_none(candidate_read.get("candidate_eid"))
        candidate_pos = sim.ecs.get(Position).get(candidate_eid) if candidate_eid is not None else None
        if candidate_pos is not None:
            distance = abs(int(observer_pos.x) - int(candidate_pos.x)) + abs(int(observer_pos.y) - int(candidate_pos.y))
            watch_position = observation_watch_position(
                sim,
                observer_eid,
                candidate_pos,
                purpose=purpose_key,
                distance_band=distance_band,
                preferred_position=preferred_position,
            )
            if watch_position is None and distance <= 1:
                watch_position = (int(observer_pos.x), int(observer_pos.y), int(observer_pos.z))
            if watch_position is not None:
                result = refresh_purposeful_observation(
                    sim,
                    observer_eid,
                    candidate_eid,
                    purpose=purpose_key,
                    subject_pos=candidate_pos,
                    watch_position=watch_position,
                    existing=context,
                    include_subject_account=include_subject_account,
                    distance_band=distance_band,
                    preferred_position=preferred_position,
                    reacquisition_details={
                        "basis": "identity_confirmation" if candidate_read.get("identity_confirmation") else "appearance_match",
                        "candidate_account": candidate_read.get("candidate_account"),
                        "match": candidate_read.get("match"),
                        "identity_confirmation": bool(candidate_read.get("identity_confirmation", False)),
                        "evaluated_candidate_count": candidate_read.get("evaluated_candidate_count", 0),
                        "visible_candidate_count": candidate_read.get("visible_candidate_count", 0),
                    },
                )
                result["reacquisition_radius"] = radius
                return result, "visible", tuple(watch_position)

    distance = (
        abs(int(observer_pos.x) - int(subject_pos.x)) + abs(int(observer_pos.y) - int(subject_pos.y))
        if subject_pos is not None
        else radius + 1
    )
    sensor_visibility = None
    if sensor_visible_positions is not None:
        sensor_visibility = {
            position
            for position in (_position_xyz(value) for value in tuple(sensor_visible_positions or ()))
            if position is not None
        }
    subject_xyz = _position_xyz(subject_pos)
    visible = bool(
        not description_reacquisition_due
        and subject_pos is not None
        and int(observer_pos.z) == int(subject_pos.z)
        and (
            subject_xyz in sensor_visibility
            if sensor_visibility is not None
            else (
                (
                    bool(direct_los)
                    and has_line_of_sight(
                        sim,
                        observer_pos.x,
                        observer_pos.y,
                        observer_pos.z,
                        subject_pos.x,
                        subject_pos.y,
                        subject_pos.z,
                    )
                )
                or (
                    not bool(direct_los)
                    and distance <= radius
                    and observer_can_see_position(
                        sim,
                        observer_eid=observer_eid,
                        observer_x=observer_pos.x,
                        observer_y=observer_pos.y,
                        observer_z=observer_pos.z,
                        target_x=subject_pos.x,
                        target_y=subject_pos.y,
                        target_z=subject_pos.z,
                        radius=radius,
                    )
                )
            )
        )
    )
    if visible:
        if not bool(refresh_visible):
            retained_target = _position_xyz((context or {}).get("watch_position"))
            return context, "visible_unrefreshed", retained_target
        watch_position = observation_watch_position(
            sim,
            observer_eid,
            subject_pos,
            purpose=purpose_key,
            distance_band=distance_band,
            preferred_position=preferred_position,
        )
        if watch_position is None and distance <= 1:
            watch_position = (int(observer_pos.x), int(observer_pos.y), int(observer_pos.z))
        if watch_position is None:
            return context, "blocked", None
        result = refresh_purposeful_observation(
            sim,
            observer_eid,
            tracked_subject_eid,
            purpose=purpose_key,
            subject_pos=subject_pos,
            watch_position=watch_position,
            existing=context,
            capture_subject_account=bool(capture_subject_account and context is None),
            include_subject_account=include_subject_account,
            distance_band=distance_band,
            preferred_position=preferred_position,
        )
        result["reacquisition_radius"] = radius
        return result, "visible", tuple(watch_position)

    if not is_purposeful_observation(context, purpose=purpose_key, active_only=True):
        return context, "lost", None
    result = dict(context)
    result["updated_tick"] = tick
    lost_since = _int_or_none(result.get("lost_contact_since_tick"))
    if lost_since is None:
        lost_since = tick
        result["lost_contact_since_tick"] = tick
    grace = max(0, _int_or(result.get("lost_contact_grace_ticks"), 0))
    last_seen = _position_xyz(result.get("last_seen_position"))
    if tick - lost_since <= grace:
        return result, "last_seen", last_seen

    search_radius, waypoint_limit, search_duration = _search_profile(result)
    if last_seen is None or search_radius <= 0 or waypoint_limit <= 0 or search_duration <= 0:
        ended = finish_purposeful_observation(result, current_tick=tick, reason="lost_contact")
        _emit_search_transition(sim, "purposeful_search_abandoned", ended, reason="search_unavailable")
        return ended, "abandoned", None

    search = deepcopy(result.get("search_state")) if isinstance(result.get("search_state"), dict) else {}
    if search.get("active") is not True:
        waypoints = purposeful_search_waypoints(sim, result)
        if not waypoints:
            ended = finish_purposeful_observation(result, current_tick=tick, reason="search_unavailable")
            _emit_search_transition(sim, "purposeful_search_abandoned", ended, reason="search_unavailable")
            return ended, "abandoned", None
        search = {
            "active": True,
            "origin": last_seen,
            "started_tick": tick,
            "deadline_tick": tick + search_duration,
            "radius": search_radius,
            "waypoint_limit": waypoint_limit,
            "waypoints": tuple(waypoints),
            "waypoint_index": 0,
            "visited": (),
        }
        result["search_state"] = search
        _emit_search_transition(sim, "purposeful_search_started", result, position=last_seen, reason="lost_contact")

    deadline = _int_or(search.get("deadline_tick"), tick)
    waypoints = tuple(_position_xyz(row) for row in tuple(search.get("waypoints", ()) or ()))
    waypoints = tuple(row for row in waypoints if row is not None)
    index = max(0, _int_or(search.get("waypoint_index"), 0))
    previous_index = index
    current = (int(observer_pos.x), int(observer_pos.y), int(observer_pos.z))
    visited = list(tuple(_position_xyz(row) for row in tuple(search.get("visited", ()) or ())))
    visited = [row for row in visited if row is not None]
    while index < len(waypoints) and current == waypoints[index]:
        if waypoints[index] not in visited:
            visited.append(waypoints[index])
        index += 1
    search["waypoint_index"] = index
    search["visited"] = tuple(visited)
    search["updated_tick"] = tick
    if bool(result.get("canvas_until_exhausted", False)) and index > previous_index:
        # For casework, duration is a no-progress failsafe rather than a total
        # interview clock.  Each reached search point renews it; exhaustion of
        # the finite route and its unasked local people is the normal stop.
        deadline = tick + search_duration
        search["deadline_tick"] = deadline
    result["search_state"] = search
    if tick > deadline or index >= len(waypoints):
        search["active"] = False
        search["ended_tick"] = tick
        search["ended_reason"] = "exhausted" if index >= len(waypoints) else "timed_out"
        result["search_state"] = search
        ended = finish_purposeful_observation(result, current_tick=tick, reason="search_abandoned")
        _emit_search_transition(
            sim,
            "purposeful_search_abandoned",
            ended,
            position=current,
            reason=search["ended_reason"],
        )
        return ended, "abandoned", None
    return result, "searching", waypoints[index]


def purposeful_observation_holds_at_target(context, *, current_tick):
    """Whether an arrived watcher should retain its post for now."""

    if not is_purposeful_observation(context, active_only=True):
        return False
    last_seen_tick = _int_or(context.get("last_seen_tick", context.get("seen_tick", -10_000)), -10_000)
    grace = max(0, _int_or(context.get("lost_contact_grace_ticks"), 0))
    return int(current_tick) - last_seen_tick <= grace


def finish_purposeful_observation(context, *, current_tick, reason="lost_contact"):
    if not is_purposeful_observation(context):
        return context
    result = dict(context)
    result["active"] = False
    result["ended_tick"] = int(current_tick)
    result["ended_reason"] = _clean_key(reason) or "complete"
    return result


def purposeful_observation_live_until(context):
    """Return the last tick at which an active observation merits live pursuit.

    Search deadlines remain authoritative.  Contact/approach contexts use a
    bounded keepalive from their last genuine consumer update, long enough to
    bridge warm-scope scheduling without allowing a forgotten record to pin a
    streamed chunk forever.
    """

    if not is_purposeful_observation(context, active_only=True):
        return None
    search = context.get("search_state") if isinstance(context.get("search_state"), dict) else {}
    if search.get("active") is True:
        deadline = _int_or_none(search.get("deadline_tick"))
        if deadline is not None:
            return deadline
    stream_state = context.get("stream_state") if isinstance(context.get("stream_state"), dict) else {}
    if _clean_key(stream_state.get("state")) == "offscreen":
        live_until = _int_or_none(stream_state.get("live_until_tick"))
        if live_until is not None:
            return live_until
    base_tick = max(
        value
        for value in (
            _int_or(context.get("updated_tick"), 0),
            _int_or(context.get("last_seen_tick"), 0),
            _int_or(context.get("received_tick"), 0),
            _int_or(context.get("started_tick"), 0),
        )
    )
    grace = max(0, _int_or(context.get("lost_contact_grace_ticks"), 0))
    search_duration = max(0, _int_or(context.get("search_duration_ticks"), 0))
    keepalive = max(PURPOSEFUL_STREAM_KEEPALIVE_TICKS, grace + search_duration)
    return base_tick + keepalive


def mark_purposeful_observation_offscreen(context, *, current_tick, chunk):
    """Mark an observation as archived without inventing offscreen movement."""

    if not is_purposeful_observation(context, active_only=True):
        return context
    tick = int(current_tick)
    result = dict(context)
    previous = result.get("stream_state") if isinstance(result.get("stream_state"), dict) else {}
    if _clean_key(previous.get("state")) == "offscreen":
        return result
    try:
        chunk_key = (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError, IndexError):
        chunk_key = None
    result["stream_state"] = {
        "state": "offscreen",
        "entered_tick": tick,
        "entered_chunk": chunk_key,
        "live_until_tick": purposeful_observation_live_until(result),
        "resolution": "pending",
    }
    return result


def settle_purposeful_observation_offscreen(sim, context, *, current_tick=None):
    """Resume unchanged state or expire it once when its chunk is restored."""

    if not is_purposeful_observation(context):
        return context, "unchanged"
    stream_state = context.get("stream_state") if isinstance(context.get("stream_state"), dict) else {}
    if _clean_key(stream_state.get("state")) != "offscreen":
        return context, "unchanged"
    tick = int(getattr(sim, "tick", 0) if current_tick is None else current_tick)
    live_until = _int_or_none(stream_state.get("live_until_tick"))
    if live_until is None:
        live_until = purposeful_observation_live_until(context)
    entered_tick = _int_or(stream_state.get("entered_tick"), tick)
    elapsed = max(0, tick - entered_tick)
    if live_until is not None and tick > live_until:
        result = dict(context)
        search = deepcopy(result.get("search_state")) if isinstance(result.get("search_state"), dict) else {}
        if search:
            search["active"] = False
            search["phase"] = "abandoned"
            search["ended_tick"] = tick
            search["ended_reason"] = "offscreen_elapsed"
            result["search_state"] = search
        result = finish_purposeful_observation(
            result,
            current_tick=tick,
            reason="search_abandoned",
        )
        result["stream_state"] = {
            **dict(stream_state),
            "state": "resolved",
            "resolution": "offscreen_elapsed",
            "resolved_tick": tick,
            "offscreen_elapsed_ticks": elapsed,
        }
        _emit_search_transition(
            sim,
            "purposeful_search_abandoned",
            result,
            reason="offscreen_elapsed",
        )
        return result, "expired"

    result = dict(context)
    result["stream_state"] = {
        **dict(stream_state),
        "state": "resumed",
        "resolution": "resumed_without_simulation",
        "resumed_tick": tick,
        "offscreen_elapsed_ticks": elapsed,
    }
    return result, "resumed"


__all__ = [
    "PURPOSEFUL_OBSERVATION_KIND",
    "advance_purposeful_actor_observation",
    "advance_purposeful_anchor_observation",
    "activate_purposeful_report_search",
    "begin_purposeful_anchor_observation",
    "begin_purposeful_report_search",
    "finish_purposeful_observation",
    "is_purposeful_observation",
    "mark_purposeful_observation_offscreen",
    "observation_context_purpose",
    "observation_purpose_profile",
    "observation_watch_position",
    "purposeful_observation_live_until",
    "purposeful_observation_holds_at_target",
    "purposeful_reacquisition_read",
    "purposeful_search_waypoints",
    "record_purposeful_canvas_contact",
    "reject_purposeful_candidate",
    "refresh_purposeful_observation",
    "settle_purposeful_observation_offscreen",
]
