"""Shared, save-safe intent records for NPCs deliberately watching a subject.

This module does not decide *why* an NPC begins watching somebody.  Sneaking,
bodyguard, criminal-drive, social, justice, and drone systems retain that
authority.  It owns the smaller common contract those decisions need: an
honest last-seen snapshot, a purpose-specific stand-off band, and bounded
behavior after visual contact is lost.  A subject may be an actor or a fixed
world anchor such as the public-facing aperture of a property being cased.
"""

from __future__ import annotations

from copy import deepcopy

from engine.visibility import has_line_of_sight
from game.components import AI, Collider, Position
from game.identity_evidence import build_witness_subject_account


PURPOSEFUL_OBSERVATION_KIND = "purposeful_observation"


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
    },
    "social_companion": {
        "posture": "accompanying",
        "min_distance": 2,
        "preferred_distance": 3,
        "max_distance": 5,
        "requires_los": True,
        "loss_policy": "approach_last_seen",
        "lost_contact_grace_ticks": 8,
    },
    "peaceful_follow": {
        "posture": "accompanying",
        "min_distance": 1,
        "preferred_distance": 2,
        "max_distance": 3,
        "requires_los": True,
        "loss_policy": "approach_last_seen",
        "lost_contact_grace_ticks": 6,
    },
    "justice_identity_check": {
        "posture": "approaching_for_questioning",
        "min_distance": 1,
        "preferred_distance": 1,
        "max_distance": 2,
        "requires_los": True,
        "loss_policy": "approach_last_seen",
        "lost_contact_grace_ticks": 6,
    },
    "justice_detention": {
        "posture": "approaching_for_custody",
        "min_distance": 1,
        "preferred_distance": 1,
        "max_distance": 2,
        "requires_los": True,
        "loss_policy": "approach_last_seen",
        "lost_contact_grace_ticks": 6,
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
    subject_account = deepcopy(previous.get("subject_account")) if isinstance(previous.get("subject_account"), dict) else {}
    if include_subject_account and (capture_subject_account or not subject_account):
        subject_account = build_witness_subject_account(
            sim,
            observer_eid,
            subject_eid,
            source_kind="deliberate_observation",
        )

    return {
        "kind": PURPOSEFUL_OBSERVATION_KIND,
        "purpose": purpose_key,
        "posture": str(profile.get("posture", "watching") or "watching"),
        "active": True,
        "observer_eid": _int_or_none(observer_eid),
        "subject_eid": _int_or_none(subject_eid),
        "offense_assumed": False,
        "started_tick": started_tick,
        "last_seen_tick": tick,
        "updated_tick": tick,
        "observation_count": count,
        "last_seen_position": (int(subject_pos.x), int(subject_pos.y), int(subject_pos.z)),
        "watch_position": (int(watch_position[0]), int(watch_position[1]), int(watch_position[2])),
        "preferred_position": _position_xyz(preferred_position),
        "min_distance": int(profile.get("min_distance", 0) or 0),
        "preferred_distance": int(profile.get("preferred_distance", 0) or 0),
        "max_distance": int(profile.get("max_distance", 0) or 0),
        "requires_los": bool(profile.get("requires_los", True)),
        "loss_policy": str(profile.get("loss_policy", "search_last_seen") or "search_last_seen"),
        "lost_contact_grace_ticks": max(0, int(profile.get("lost_contact_grace_ticks", 0) or 0)),
        "subject_account": subject_account,
        # Transitional aliases keep generic investigation/debug consumers useful
        # while the richer fields remain authoritative.
        "source_eid": _int_or_none(subject_eid),
        "x": int(subject_pos.x),
        "y": int(subject_pos.y),
        "z": int(subject_pos.z),
        "seen_tick": tick,
    }


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


__all__ = [
    "PURPOSEFUL_OBSERVATION_KIND",
    "advance_purposeful_anchor_observation",
    "begin_purposeful_anchor_observation",
    "finish_purposeful_observation",
    "is_purposeful_observation",
    "observation_context_purpose",
    "observation_purpose_profile",
    "observation_watch_position",
    "purposeful_observation_holds_at_target",
    "refresh_purposeful_observation",
]
