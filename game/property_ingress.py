"""Reusable property ingress runtime.

This module extracts the ingress candidate, profiling, and execution path out
of ``game/systems.py`` so entry attempts can evolve as a shared gameplay seam
instead of living only as inline player-action code.
"""

from engine.events import Event
from engine.tilemap import Tile
from game.components import AI, NPCMemory, PlayerModeState, Position
from game.movement_runtime import try_move_entity
from game.property_doors import _door_is_physically_locked, _operable_door_state_at, _set_door_open_state
from game.property_access import (
    PropertyIngressResult,
    _boundary_tile as _property_boundary_tile,
    evaluate_property_access as _evaluate_property_access,
    property_claim_reason as _property_claim_reason,
    property_access_transition_event_payload as _property_access_transition_event_payload,
    property_ingress_context as _property_ingress_context,
    room_access_event_payload as _room_access_event_payload,
    shared_property_interest_event_payload as _shared_property_interest_event_payload,
    shared_property_interests_for_position as _shared_property_interests_for_position,
)
from game.property_runtime import (
    property_aperture_at as _property_aperture_at,
    property_covering as _property_covering,
    property_enclosing_structure as _property_enclosing_structure,
)
from game.social_boundary_runtime import active_ejection_state, ejection_key
from game.skills import actor_skill as _actor_skill
from game.system_support.access_runtime import _attempt_locked_property_entry_with_sim
from game.system_support.awareness_runtime import observation_payload_for_position
from game.system_support.building_repair_runtime import record_building_damage as _record_building_damage
from game.system_support.structure_damage_runtime import (
    STRUCTURE_MAX_HP,
    apply_structural_damage as _apply_structural_damage,
    structural_surface_kind as _structural_surface_kind,
    structural_surface_label as _structural_surface_label,
)
from game.system_support.access_checks import (
    _maybe_damage_access_tool,
    _resolve_access_skill_check,
)
from game.system_support.intrusion_runtime import (
    _ingress_method_label,
    _ingress_mode_label,
    _is_side_aperture,
    _is_window_aperture,
    _trespass_label_from_score,
)
from game.system_support.player_feedback import _log_player_feedback


def _standing_reason_label(reason):
    reason = str(reason or "").strip().lower()
    mapping = {
        "owner": "owner",
        "employee": "staff",
        "resident": "resident",
        "contact": "contact",
        "family": "family",
        "partner": "partner",
        "neighbor": "neighbor",
        "coworker": "coworker",
        "relationship": "relation",
    }
    return mapping.get(reason, reason.replace("_", " "))


_SOFT_ACCIDENTAL_TRESPASS_INGRESS_KINDS = frozenset({"ordinary_entry", "internal"})
_HARD_TRESPASS_METHODS = frozenset({
    "manual_side_entry",
    "jimmied_side_entry",
    "forced_side_entry",
    "quiet_window_entry",
    "careful_window_entry",
    "crash_window_entry",
    "window_entry",
    "forced_breach",
    "deep_breach",
    "side_entry",
    "alternate_entry",
})
_SCUFFLE_MEMORY_KINDS = frozenset({"threat", "conflict_side", "ally_threatened"})
_SOFT_ROOM_BOUNDARY_LEVELS = frozenset({"staff_only", "private"})
_COVERT_NPC_BOUNDARY_STATES = frozenset({
    "casing_target",
    "committing_property_crime",
})
_SCUFFLE_NOISE_TERMS = (
    "attack",
    "assault",
    "combat",
    "explosion",
    "fight",
    "fire_weapon",
    "gun",
    "gunshot",
    "hit",
    "melee",
    "scuffle",
    "shoot",
    "shot",
    "struggle",
    "violence",
    "weapon",
)


def _text(value):
    return str(value or "").strip()


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _property_id(prop):
    if not isinstance(prop, dict):
        return ""
    return _text(prop.get("id"))


def _observer_eids_from_observation(observation, observer_eids=()):
    if isinstance(observation, dict):
        for key in ("accountable_observer_eids", "witnesses", "observer_eids"):
            values = observation.get(key)
            if values:
                observer_eids = values
                break
    if observer_eids is None:
        return ()
    if isinstance(observer_eids, (int, str)):
        observer_eids = (observer_eids,)
    normalized = []
    seen = set()
    for value in tuple(observer_eids or ()):
        eid = _safe_int(value, default=0)
        if eid <= 0 or eid in seen:
            continue
        seen.add(eid)
        normalized.append(eid)
    return tuple(normalized)


def _active_ejection_covers(sim, property_id, target_eid, *, transition=None):
    key = ejection_key(property_id, target_eid)
    if not key:
        return False
    row = active_ejection_state(sim).get(key)
    if not isinstance(row, dict):
        return False
    if bool(getattr(transition, "entered_more_restricted", False)):
        # Grace to correct one boundary is not permission to continue through a
        # deeper one.  In particular, a stockroom warning cannot immunize a
        # subsequent vault entry.
        return False
    return not bool(row.get("refused", False))


def _boundary_violation_has_listener(sim):
    events = getattr(sim, "events", None)
    subscribers = getattr(events, "subscribers", {}) if events is not None else {}
    return bool(subscribers.get("npc_boundary_violation"))


def _soft_trespass_candidate_allowed(sim, eid, prop, access, ingress, *, ingress_method=""):
    if _safe_int(eid, default=0) != _safe_int(getattr(sim, "player_eid", None), default=-1):
        return False
    if not isinstance(prop, dict) or access is None or ingress is None:
        return False
    if bool(getattr(access, "permitted", False)):
        return False
    if _text(getattr(access, "access_level", "")).lower() != "public":
        return False
    if getattr(access, "currently_open", None) is not False:
        return False
    if bool(getattr(access, "organization_denied_entry", False)):
        return False
    if _safe_int(getattr(access, "severity_score", 0), default=0) > 28:
        return False
    if _text(getattr(access, "severity_label", "")).lower() == "serious_trespass":
        return False

    ingress_kind = _text(getattr(ingress, "ingress_kind", "")).lower()
    if ingress_kind not in _SOFT_ACCIDENTAL_TRESPASS_INGRESS_KINDS:
        return False
    if _safe_float(getattr(ingress, "breach_severity", 0.0), default=0.0) > 0.01:
        return False

    method = _text(ingress_method).lower()
    if method in _HARD_TRESPASS_METHODS:
        return False
    return True


def _soft_room_boundary_candidate_allowed(sim, eid, prop, access, ingress, transition, *, ingress_method=""):
    if not isinstance(prop, dict) or access is None or ingress is None or transition is None:
        return False
    if bool(getattr(access, "permitted", False)):
        return False
    if not bool(getattr(transition, "entered_unauthorized", False)):
        return False
    if _text(getattr(transition, "boundary_kind", "")).lower() != "room_transition":
        return False
    if _text(getattr(access, "room_access_level", "")).lower() not in _SOFT_ROOM_BOUNDARY_LEVELS:
        return False
    if bool(getattr(access, "organization_denied_entry", False)):
        return False
    if _safe_int(getattr(access, "severity_score", 0), default=0) > 28:
        return False
    if _text(getattr(access, "severity_label", "")).lower() == "serious_trespass":
        return False
    if _text(getattr(ingress, "ingress_kind", "")).lower() != "internal":
        return False
    if _safe_float(getattr(ingress, "breach_severity", 0.0), default=0.0) > 0.01:
        return False
    if _text(ingress_method).lower() in _HARD_TRESPASS_METHODS:
        return False
    return True


def _actor_boundary_posture(sim, eid):
    modes = sim.ecs.get(PlayerModeState).get(eid)
    if modes is not None and bool(getattr(modes, "sneak", False)):
        return "visible_sneak"
    ai = sim.ecs.get(AI).get(eid)
    if ai is not None and _text(getattr(ai, "state", "")).lower() in _COVERT_NPC_BOUNDARY_STATES:
        return "covert_intent"
    return "ordinary"


def _prior_room_boundary_warning_count(sim, claimant_eid, target_eid, prop, access, *, max_age=900):
    memory = sim.ecs.get(NPCMemory).get(claimant_eid)
    if memory is None:
        return 0
    property_id = _property_id(prop)
    room_kind = _text(getattr(access, "room_kind", "")).lower()
    room_level = _text(getattr(access, "room_access_level", "")).lower()
    now = _safe_int(getattr(sim, "tick", 0), default=0)
    count = 0
    for entry in tuple(getattr(memory, "entries", ()) or ()):
        if _text(entry.get("kind") if isinstance(entry, dict) else "").lower() != "property_boundary_warning":
            continue
        tick = _safe_int(entry.get("tick") if isinstance(entry, dict) else None, default=-10_000)
        if now - tick < 0 or now - tick > int(max_age):
            continue
        data = entry.get("data") if isinstance(entry, dict) else None
        data = data if isinstance(data, dict) else {}
        if _safe_int(data.get("target_eid"), default=0) != _safe_int(target_eid, default=0):
            continue
        if property_id and _text(data.get("property_id")) != property_id:
            continue
        remembered_room = _text(data.get("room_kind")).lower()
        remembered_level = _text(data.get("room_access_level")).lower()
        if room_kind and remembered_room and room_kind != remembered_room and room_level != remembered_level:
            continue
        count += 1
    return count


def _entry_position(entry):
    data = entry.get("data") if isinstance(entry, dict) else None
    data = data if isinstance(data, dict) else {}
    try:
        return int(data["x"]), int(data["y"]), int(data.get("z", 0))
    except (KeyError, TypeError, ValueError):
        return None


def _memory_entry_mentions_scuffle(entry):
    data = entry.get("data") if isinstance(entry, dict) else None
    data = data if isinstance(data, dict) else {}
    haystack = " ".join(
        _text(data.get(key)).lower()
        for key in ("cause", "action", "context", "source_event", "via")
    )
    return any(term in haystack for term in _SCUFFLE_NOISE_TERMS)


def _recent_scuffle_near_claimant(sim, claimant_eid, prop, x, y, z, *, max_age=18, radius=8):
    memory = sim.ecs.get(NPCMemory).get(claimant_eid)
    if not memory:
        return False
    now = _safe_int(getattr(sim, "tick", 0), default=0)
    property_id = _property_id(prop)
    for entry in tuple(getattr(memory, "entries", ()) or ()):
        kind = _text(entry.get("kind")).lower() if isinstance(entry, dict) else ""
        if kind == "noise":
            if not _memory_entry_mentions_scuffle(entry):
                continue
        elif kind not in _SCUFFLE_MEMORY_KINDS:
            continue

        tick = _safe_int(entry.get("tick") if isinstance(entry, dict) else None, default=-10_000)
        age = now - tick
        if age < 0 or age > int(max_age):
            continue

        data = entry.get("data") if isinstance(entry, dict) else None
        data = data if isinstance(data, dict) else {}
        if property_id and _text(data.get("property_id")) == property_id:
            return True

        entry_pos = _entry_position(entry)
        if entry_pos is None:
            return age <= 4 and kind in _SCUFFLE_MEMORY_KINDS
        ex, ey, ez = entry_pos
        if int(ez) != int(z):
            continue
        if abs(int(ex) - int(x)) + abs(int(ey) - int(y)) <= int(radius):
            return True
    return False


def _soft_trespass_claimants(sim, prop, observer_eids, x, y, z):
    positions = sim.ecs.get(Position)
    candidates = []
    priority_by_reason = {
        "owner": 0,
        "manager": 1,
        "employee": 2,
        "credential_holder": 3,
        "resident": 4,
    }
    for observer_eid in tuple(observer_eids or ()):
        pos = positions.get(observer_eid) if positions else None
        if pos is None:
            continue
        access, reason = _property_claim_reason(
            sim,
            observer_eid,
            prop,
            x=pos.x,
            y=pos.y,
            z=pos.z,
            min_standing=0.58,
        )
        reason = _text(reason).lower()
        if not reason:
            continue
        priority = priority_by_reason.get(reason, 5)
        candidates.append((priority, -_safe_float(getattr(access, "standing", 0.0), default=0.0), observer_eid, reason))
    candidates.sort()
    return tuple(candidates)


def maybe_emit_accidental_trespass_boundary(
    sim,
    *,
    eid,
    prop,
    access,
    ingress,
    x,
    y,
    z,
    observation=None,
    observer_eids=(),
    ingress_method="",
    action="move",
    offense_score=None,
    transition=None,
):
    """Divert a perceived, correctable access mistake into social correction.

    This covers both an ordinary after-hours public entry and the first plainly
    witnessed step from authorized space into an ordinary staff/private room.
    Covert movement, repeated entry after a warning, secure space, forced
    ingress, and recent violence stay on the real trespass path.
    """

    property_id = _property_id(prop)
    if _active_ejection_covers(sim, property_id, eid, transition=transition):
        return True
    if not _boundary_violation_has_listener(sim):
        return False
    after_hours_candidate = _soft_trespass_candidate_allowed(
        sim,
        eid,
        prop,
        access,
        ingress,
        ingress_method=ingress_method,
    )
    room_candidate = _soft_room_boundary_candidate_allowed(
        sim,
        eid,
        prop,
        access,
        ingress,
        transition,
        ingress_method=ingress_method,
    )
    if not after_hours_candidate and not room_candidate:
        return False

    observers = _observer_eids_from_observation(observation, observer_eids)
    claimants = _soft_trespass_claimants(sim, prop, observers, x, y, z)
    if not claimants:
        return False
    if any(
        _recent_scuffle_near_claimant(sim, claimant_eid, prop, x, y, z)
        for _priority, _standing, claimant_eid, _reason in claimants
    ):
        return False

    _priority, _standing, claimant_eid, claim_reason = claimants[0]
    boundary_posture = _actor_boundary_posture(sim, eid)
    warning_count = 0
    if room_candidate:
        warning_count = _prior_room_boundary_warning_count(
            sim,
            claimant_eid,
            eid,
            prop,
            access,
        )
        if boundary_posture != "ordinary" or warning_count > 0:
            return False

    severity = _safe_int(getattr(access, "severity_score", 0), default=0)
    if offense_score is None:
        offense_score = max(14, min(28, severity + 4))
    self_reported_method = _text(ingress_method).lower() or _text(getattr(ingress, "ingress_kind", "")).lower()
    transition_payload = _property_access_transition_event_payload(transition) if transition is not None else {}
    boundary_scope = "room" if room_candidate else "property"
    context = "restricted_room_entry" if room_candidate else "accidental_trespass"
    source_kind = "room_boundary" if room_candidate else "accidental_trespass"
    sim.emit(Event(
        "npc_boundary_violation",
        npc_eid=claimant_eid,
        enforcer_eid=claimant_eid,
        target_eid=eid,
        offender_eid=eid,
        property_id=property_id,
        property_name=prop.get("name"),
        context=context,
        source_kind=source_kind,
        boundary_scope=boundary_scope,
        boundary_response="correct_access",
        boundary_posture=boundary_posture,
        claim_reason=claim_reason,
        action=action,
        offense_score=max(14, min(32, _safe_int(offense_score, default=severity + 4))),
        perceived=max(0.48, min(0.68, 0.44 + (severity / 100.0))),
        violation_count=warning_count,
        violence_eligible=False,
        record_watchlist=False,
        x=x,
        y=y,
        z=z,
        access_level=getattr(access, "access_level", ""),
        property_access_level=getattr(access, "property_access_level", ""),
        room_kind=getattr(access, "room_kind", ""),
        room_access_level=getattr(access, "room_access_level", ""),
        room_access_reason=getattr(access, "room_access_reason", ""),
        room_floor=getattr(access, "room_floor", 0),
        common_area_kind=getattr(access, "common_area_kind", ""),
        currently_open=getattr(access, "currently_open", None),
        current_hour=getattr(access, "current_hour", None),
        ingress_kind=getattr(ingress, "ingress_kind", ""),
        aperture_kind=getattr(ingress, "aperture_kind", ""),
        ingress_method=self_reported_method,
        accidental=True,
        **transition_payload,
    ))
    return True


class PropertyIngressRuntime:
    """Shared ingress runtime owned by ``PlayerActionSystem`` for now."""

    def __init__(self, action_system):
        self.action_system = action_system
        self.sim = action_system.sim

    def locked_ordinary_entry_property(self, eid, pos, target_x, target_y, target_z):
        prop = _property_covering(self.sim, target_x, target_y, target_z)
        if not prop or str(prop.get("kind", "")).strip().lower() != "building":
            return None

        ingress = _property_ingress_context(
            prop,
            from_x=pos.x,
            from_y=pos.y,
            from_z=pos.z,
            to_x=target_x,
            to_y=target_y,
            to_z=target_z,
            sim=self.sim,
        )
        if ingress.ingress_kind != "ordinary_entry":
            return None

        door_state = _operable_door_state_at(self.sim, target_x, target_y, target_z)
        if not _door_is_physically_locked(door_state, prop):
            return None
        if self.action_system._property_credential_access_for(eid, prop):
            return None
        return prop

    def attempt_locked_property_entry(self, eid, prop, *, target_x, target_y, target_z):
        return _attempt_locked_property_entry_with_sim(
            self.sim,
            eid,
            prop,
            target_x=target_x,
            target_y=target_y,
            target_z=target_z,
        )

    def ingress_method_profile(self, eid, prop, ingress, claim_reason):
        modes = self.action_system._mode_state_for(eid)
        sneak_active = bool(modes and modes.sneak)
        ingress_kind = str(getattr(ingress, "ingress_kind", "") or "").strip().lower()
        aperture_kind = str(getattr(ingress, "aperture_kind", "") or "").strip().lower()
        door_like_ingress = (
            ingress_kind == "ordinary_entry"
            or (ingress_kind == "alternate_aperture" and _is_side_aperture(aperture_kind))
        )

        if ingress_kind == "deep_breach":
            return "deep_breach", 10, 12
        if ingress_kind == "boundary_breach":
            return "forced_breach", 8, 10

        side_entry_terms = self.action_system._access_tool_terms_for(eid, prop, context="side_entry")

        if ingress_kind == "alternate_aperture" and _is_window_aperture(aperture_kind):
            if side_entry_terms.get("enabled") and sneak_active:
                return "quiet_window_entry", 2, 4
            if sneak_active:
                return "careful_window_entry", 4, 6
            return "crash_window_entry", 8, 10

        if door_like_ingress:
            if claim_reason:
                return "authorized_side_entry", 0, 0
            if (
                not side_entry_terms.get("enabled")
                and self.action_system._access_override_score(eid, tool_terms=side_entry_terms)
                >= self.action_system._lock_override_required(prop, tool_terms=side_entry_terms)
            ):
                return "manual_side_entry", 2, 4
            if side_entry_terms.get("enabled"):
                return "jimmied_side_entry", 1, 2
            return "forced_side_entry", 6, 8

        if claim_reason:
            return "authorized_side_entry", 0, 0
        return "forced_side_entry", 5, 7

    def ingress_attempt_profile(self, eid, prop, ingress, claim_reason):
        ingress_method, severity_bonus, offense_bonus = self.ingress_method_profile(
            eid,
            prop,
            ingress,
            claim_reason,
        )
        profile = {
            "method": ingress_method,
            "severity_bonus": severity_bonus,
            "offense_bonus": offense_bonus,
            "hostile": ingress_method in {
                "quiet_window_entry",
                "careful_window_entry",
                "crash_window_entry",
                "forced_breach",
                "deep_breach",
            },
            "unauthorized": ingress_method in {
                "manual_side_entry",
                "jimmied_side_entry",
                "forced_side_entry",
            },
            "automatic": ingress_method == "authorized_side_entry",
        }
        if profile["automatic"]:
            return profile

        ingress_kind = str(getattr(ingress, "ingress_kind", "") or "").strip().lower()
        tool_context = "wall_breach" if ingress_kind in {"boundary_breach", "deep_breach"} else "side_entry"
        tool_terms = self.action_system._access_tool_terms_for(eid, prop, context=tool_context)
        score = self.action_system._access_override_score(eid, tool_terms=tool_terms)
        required = self.action_system._lock_override_required(prop, tool_terms=tool_terms)
        aperture_kind = str(getattr(ingress, "aperture_kind", "") or "").strip().lower()
        breach_severity = max(0.0, float(getattr(ingress, "breach_severity", 0.0) or 0.0))
        athletics = _actor_skill(self.sim, eid, "athletics")

        if ingress_kind == "alternate_aperture" and _is_window_aperture(aperture_kind):
            score += max(0.0, athletics - 5.0) * 0.24
            if ingress_method == "quiet_window_entry":
                score += 0.35
            elif ingress_method == "careful_window_entry":
                score += 0.18
            required += 0.35 + (breach_severity * 1.2)
            context = "window_entry"
            channel = "window_entry"
        elif ingress_kind in {"boundary_breach", "deep_breach"}:
            mechanics = _actor_skill(self.sim, eid, "mechanics")
            score += max(0.0, athletics - 5.0) * 0.36
            score += max(0.0, mechanics - 5.0) * 0.14
            required += 0.75 + (breach_severity * 1.9)
            context = "wall_breach"
            channel = "wall_breach"
        else:
            required += 0.2 + (breach_severity * 0.9)
            if ingress_method == "manual_side_entry":
                score += 0.15
            elif ingress_method == "forced_side_entry":
                required += 0.2
            context = "side_entry"
            channel = "door_breach"

        profile["context"] = context
        profile["channel"] = channel
        profile["tool_terms"] = tool_terms
        profile["attempt"] = _resolve_access_skill_check(
            self.sim,
            eid=eid,
            prop=prop,
            context=context,
            channel=channel,
            score=score,
            required=required,
            tool_terms=tool_terms,
            allow_fumble=True,
        )
        return profile

    def failed_ingress_attempt_text(self, ingress_mode, ingress_method, prop, *, fumbled=False, eid=None):
        prop_name = str((prop or {}).get("name", (prop or {}).get("id", "property"))).strip() or "property"
        method = str(ingress_method or "").strip().lower()

        if method in {"quiet_window_entry", "careful_window_entry", "crash_window_entry"}:
            base = f"You {'botch' if fumbled else 'fail'} the window entry at {prop_name}."
        elif method in {"forced_breach", "deep_breach"}:
            base = f"You {'botch' if fumbled else 'fail'} the wall breach at {prop_name}."
        else:
            mode_text = _ingress_mode_label(ingress_mode)
            if fumbled:
                base = f"You botch the {mode_text} at {prop_name}."
            else:
                base = f"You fail to make the {mode_text} at {prop_name}."

        hint = self.ingress_tool_hint(eid, ingress_mode)
        if hint:
            return f"{base} {hint}".strip()
        return base

    def ingress_structure_damage_amount(
        self,
        ingress,
        ingress_method,
        *,
        success=False,
        fumbled=False,
        tool_terms=None,
    ):
        method = str(ingress_method or "").strip().lower()
        ingress_kind = str(getattr(ingress, "ingress_kind", "") or "").strip().lower()
        aperture_kind = str(getattr(ingress, "aperture_kind", "") or "").strip().lower()
        if ingress_kind in {"boundary_breach", "deep_breach"}:
            if bool((tool_terms or {}).get("improvised_wall_tool")):
                wall_damage = max(1, _safe_int((tool_terms or {}).get("wall_damage"), 6))
                if success:
                    return wall_damage
                return max(1, wall_damage // (3 if fumbled else 2))
            if success:
                return STRUCTURE_MAX_HP["wall"] + (14 if ingress_kind == "deep_breach" else 8)
            return 5 if fumbled else 12
        if ingress_kind == "alternate_aperture" and _is_window_aperture(aperture_kind):
            if success:
                return STRUCTURE_MAX_HP["window"] + 3
            if method == "crash_window_entry":
                return 2 if fumbled else 4
            return 1 if fumbled else 2
        if method == "forced_side_entry":
            if success:
                return STRUCTURE_MAX_HP["door"] + 4
            return 3 if fumbled else 6
        return 0

    def apply_ingress_structure_damage(
        self,
        eid,
        candidate,
        ingress_method,
        *,
        success=False,
        fumbled=False,
        tool_terms=None,
    ):
        ingress = candidate.get("ingress")
        amount = self.ingress_structure_damage_amount(
            ingress,
            ingress_method,
            success=success,
            fumbled=fumbled,
            tool_terms=tool_terms,
        )
        if amount <= 0:
            return None
        aperture_kind = str(getattr(ingress, "aperture_kind", "") or "").strip().lower()
        ingress_kind = str(getattr(ingress, "ingress_kind", "") or "").strip().lower()
        kind = ""
        if ingress_kind in {"boundary_breach", "deep_breach"}:
            kind = "wall"
        elif _is_window_aperture(aperture_kind):
            kind = "window"
        elif str(ingress_method or "").strip().lower() == "forced_side_entry":
            kind = "door"
        result = _apply_structural_damage(
            self.sim,
            candidate.get("prop"),
            candidate["x"],
            candidate["y"],
            candidate["z"],
            amount=amount,
            kind=kind,
            aperture_kind=aperture_kind,
            cause=ingress_method,
            damage_kind="ingress",
            offender_eid=eid,
        )
        return result if isinstance(result, dict) and result.get("damaged") else None

    def structural_damage_feedback(self, result):
        if not isinstance(result, dict) or not result.get("damaged"):
            return ""
        kind = _structural_surface_label(result.get("surface_kind"))
        hp = _safe_int(result.get("hp"), 0)
        max_hp = max(1, _safe_int(result.get("max_hp"), 1))
        if result.get("broken"):
            return f"The {kind} gives way."
        return f"The {kind} gives a little ({hp}/{max_hp})."

    def emit_failed_ingress_attempt(self, eid, candidate, prop, ingress, ingress_method, *, severity_bonus=0, offense_bonus=0):
        access = _evaluate_property_access(
            self.sim,
            eid,
            prop,
            x=candidate["x"],
            y=candidate["y"],
            z=candidate["z"],
            breach_severity=ingress.breach_severity,
        )
        observation = observation_payload_for_position(
            self.sim,
            candidate["x"],
            candidate["y"],
            candidate["z"],
            exclude_eid=eid,
            offender_eid=eid,
            observation_channels=("actor_witness",),
        )
        severity_score = max(
            18,
            int(access.severity_score) + int(round(float(ingress.breach_severity) * 10.0)),
        )
        severity_score = min(100, severity_score + int(max(0, severity_bonus)))
        self.sim.emit(Event(
            "property_tamper",
            offender_eid=eid,
            property_id=prop["id"],
            owner_eid=prop.get("owner_eid"),
            x=candidate["x"],
            y=candidate["y"],
            z=candidate["z"],
            **observation,
            access_level=access.access_level,
            severity_score=severity_score,
            severity_label=_trespass_label_from_score(severity_score),
            standing_reason=access.standing_reason,
            ingress_kind=ingress.ingress_kind,
            aperture_kind=ingress.aperture_kind,
            ingress_method=ingress_method,
            breach_severity=ingress.breach_severity,
        ))
        offense_score = min(
            100,
            self.action_system._offense_score_for("tamper", context="ordinary")
            + int(round(float(ingress.breach_severity) * 12.0))
            + int(max(0, offense_bonus)),
        )
        self.action_system._emit_action_offense(
            eid=eid,
            action="tamper",
            context="ordinary",
            score=offense_score,
            x=candidate["x"],
            y=candidate["y"],
            z=candidate["z"],
            **observation,
        )

    def ingress_mode_matches(self, candidate, ingress_mode):
        ingress_mode = str(ingress_mode or "").strip().lower()
        ingress = candidate.get("ingress")
        aperture_kind = str(getattr(ingress, "aperture_kind", "") or "").strip().lower()
        ingress_kind = str(getattr(ingress, "ingress_kind", "") or "").strip().lower()

        if ingress_mode == "side_entry":
            return ingress_kind == "ordinary_entry" or (
                ingress_kind == "alternate_aperture" and _is_side_aperture(aperture_kind)
            )
        if ingress_mode == "window_entry":
            return ingress_kind == "alternate_aperture" and _is_window_aperture(aperture_kind)
        if ingress_mode == "forced_breach":
            return ingress_kind in {"boundary_breach", "deep_breach"}
        return True

    def internal_ingress_candidate(self, pos, prop, target_x, target_y, target_z, *, tile=None, aperture=None):
        origin_prop = _property_enclosing_structure(
            self.sim,
            pos.x,
            pos.y,
            pos.z,
            prop=_property_covering(self.sim, pos.x, pos.y, pos.z),
        )
        if not origin_prop or origin_prop.get("id") != prop.get("id"):
            return None

        if aperture is None:
            aperture = _property_aperture_at(prop, target_x, target_y, target_z)
        if aperture and not bool(aperture.get("ordinary")):
            kind = str(aperture.get("kind", "") or "").strip().lower()
            if kind in {"window", "skylight"}:
                severity = 0.45
            elif kind in {"side_door", "service_door", "employee_door"}:
                severity = 0.22
            else:
                severity = 0.32
            return PropertyIngressResult(
                property_id=prop.get("id") if isinstance(prop, dict) else None,
                from_inside=True,
                to_inside=True,
                entered_bounds=False,
                ingress_kind="alternate_aperture",
                aperture_kind=kind,
                breach_severity=severity,
            )

        if tile is None:
            tile = self.sim.tilemap.tile_at(target_x, target_y, target_z)
        surface_kind = _structural_surface_kind(
            self.sim,
            prop,
            target_x,
            target_y,
            target_z,
            tile=tile,
            aperture=aperture,
        )
        if tile and not tile.walkable and surface_kind == "wall":
            boundary = _property_boundary_tile(prop, target_x, target_y, target_z)
            return PropertyIngressResult(
                property_id=prop.get("id") if isinstance(prop, dict) else None,
                from_inside=True,
                to_inside=True,
                entered_bounds=False,
                ingress_kind="boundary_breach" if boundary else "deep_breach",
                aperture_kind="",
                breach_severity=0.58 if boundary else 0.82,
            )
        return None

    def adjacent_ingress_candidates(self, pos, ingress_mode=None):
        candidates = []
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            tx = pos.x + dx
            ty = pos.y + dy
            tz = pos.z

            covered_prop = _property_covering(self.sim, tx, ty, tz)
            prop = _property_enclosing_structure(
                self.sim,
                tx,
                ty,
                tz,
                prop=covered_prop,
            )
            if not prop or str(prop.get("kind", "") or "").strip().lower() != "building":
                continue

            ingress = _property_ingress_context(
                prop,
                from_x=pos.x,
                from_y=pos.y,
                from_z=pos.z,
                to_x=tx,
                to_y=ty,
                to_z=tz,
                sim=self.sim,
            )
            tile = self.sim.tilemap.tile_at(tx, ty, tz)
            aperture = _property_aperture_at(prop, tx, ty, tz)
            if not ingress.entered_bounds:
                ingress = self.internal_ingress_candidate(
                    pos,
                    prop,
                    tx,
                    ty,
                    tz,
                    tile=tile,
                    aperture=aperture,
                )
                if not ingress:
                    continue
            if ingress.ingress_kind in {"ordinary_entry", "alternate_aperture"}:
                priority = 0
            elif tile and not tile.walkable:
                priority = 1
            else:
                continue

            candidates.append({
                "priority": priority,
                "prop": prop,
                "x": tx,
                "y": ty,
                "z": tz,
                "tile": tile,
                "aperture": aperture,
                "ingress": ingress,
            })

        if ingress_mode:
            candidates = [candidate for candidate in candidates if self.ingress_mode_matches(candidate, ingress_mode)]

        candidates.sort(
            key=lambda row: (
                int(row["priority"]),
                float(row["ingress"].breach_severity),
                row["prop"].get("id", ""),
                row["y"],
                row["x"],
            )
        )
        return candidates

    def authorized_side_entry_reason(self, eid, candidate):
        pos = self.sim.ecs.get(Position).get(eid)
        prop = candidate["prop"]
        ingress = candidate["ingress"]
        aperture_kind = str(ingress.aperture_kind or "").strip().lower()
        if _is_window_aperture(aperture_kind):
            return ""
        if not (
            str(ingress.ingress_kind or "").strip().lower() == "ordinary_entry"
            or _is_side_aperture(aperture_kind)
        ):
            return ""

        access = _evaluate_property_access(
            self.sim,
            eid,
            prop,
            x=candidate["x"],
            y=candidate["y"],
            z=candidate["z"],
            breach_severity=ingress.breach_severity,
        )
        if not access.permitted or not pos:
            return ""

        _, claim_reason = _property_claim_reason(
            self.sim,
            eid,
            prop,
            x=pos.x,
            y=pos.y,
            z=pos.z,
            min_standing=0.52,
        )
        return claim_reason

    def open_ingress_tile(self, candidate, hostile=False):
        tile = candidate.get("tile")
        if tile and tile.walkable:
            return

        ingress = candidate["ingress"]
        aperture_kind = str(ingress.aperture_kind or "").strip().lower()
        if (
            str(ingress.ingress_kind or "").strip().lower() == "ordinary_entry"
            or (ingress.ingress_kind == "alternate_aperture" and _is_side_aperture(aperture_kind))
        ):
            if _set_door_open_state(
                self.sim,
                int(candidate["x"]),
                int(candidate["y"]),
                int(candidate["z"]),
                True,
            ):
                return
        if not hostile and ingress.ingress_kind == "alternate_aperture" and _is_window_aperture(aperture_kind):
            glyph = '"'
        elif not hostile and ingress.ingress_kind == "alternate_aperture":
            glyph = "+"
        else:
            glyph = "/"
        self.sim.tilemap.set_tile(
            int(candidate["x"]),
            int(candidate["y"]),
            Tile(walkable=True, transparent=True, glyph=glyph),
            z=int(candidate["z"]),
        )

    def ingress_tool_hint(self, eid, ingress_mode):
        mode = str(ingress_mode or "").strip().lower()
        if mode not in {"side_entry", "window_entry"}:
            return ""
        side_terms = self.action_system._access_tool_terms_for(eid, context="side_entry")
        if side_terms.get("enabled"):
            return "Sneak plus your current tools improve your odds."
        return "A lockpick kit or prybar can help with door breaches and window ingress."

    def missing_ingress_text(self, ingress_mode, *, eid=None):
        ingress_mode = str(ingress_mode or "").strip().lower()
        if ingress_mode == "side_entry":
            base = "No adjacent door to breach."
            hint = self.ingress_tool_hint(eid, ingress_mode)
            return f"{base} {hint}".strip()
        if ingress_mode == "window_entry":
            base = "No adjacent window to climb through."
            hint = self.ingress_tool_hint(eid, ingress_mode)
            return f"{base} {hint}".strip()
        if ingress_mode == "forced_breach":
            return "No adjacent wall to breach."
        return "No adjacent ingress point."

    def ingress_blocked_text(self, reason, ingress_mode, prop, *, eid=None):
        mode_text = _ingress_mode_label(ingress_mode)
        prop_name = str((prop or {}).get("name", (prop or {}).get("id", "property"))).strip() or "property"
        reason_key = str(reason or "").strip().lower()

        if reason_key.startswith("blocked_entity"):
            base = f"Your {mode_text} path into {prop_name} is blocked by someone in the way."
        elif reason_key == "blocked_tile":
            base = f"That {mode_text} entry into {prop_name} is obstructed."
        elif reason_key == "out_of_bounds":
            base = f"That {mode_text} approach is out of bounds."
        else:
            base = f"{mode_text.title()} ingress into {prop_name} is blocked."

        hint = self.ingress_tool_hint(eid, ingress_mode)
        if hint:
            return f"{base} {hint}".strip()
        return base

    def handle_ingress_action(self, eid, pos, ingress_mode):
        cover = self.action_system._cover_state_for(eid)
        had_cover = bool(cover and cover.active)
        if str(ingress_mode or "").strip().lower() == "forced_breach" and int(pos.z) > 0:
            _log_player_feedback(
                self.sim,
                "You cannot breach structural walls above the ground floor.",
                kind="movement",
            )
            return
        candidates = self.adjacent_ingress_candidates(pos, ingress_mode=ingress_mode)
        if not candidates:
            _log_player_feedback(
                self.sim,
                self.missing_ingress_text(ingress_mode, eid=eid),
                kind="movement",
            )
            return

        candidate = candidates[0]
        prop = candidate["prop"]
        ingress = candidate["ingress"]
        ingress_kind = str(getattr(ingress, "ingress_kind", "") or "").strip().lower()
        wall_breach = ingress_kind in {"boundary_breach", "deep_breach"}
        if wall_breach:
            wall_tool_terms = self.action_system._access_tool_terms_for(eid, prop, context="wall_breach")
            if not wall_tool_terms.get("enabled"):
                _log_player_feedback(
                    self.sim,
                    "You need a sturdy wall-breaching tool, such as a prybar, fire axe, or sledgehammer.",
                    kind="movement",
                )
                return
        claim_reason = self.authorized_side_entry_reason(eid, candidate)
        ingress_profile = self.ingress_attempt_profile(eid, prop, ingress, claim_reason)
        ingress_method = ingress_profile["method"]
        severity_bonus = ingress_profile["severity_bonus"]
        offense_bonus = ingress_profile["offense_bonus"]
        hostile = bool(ingress_profile["hostile"])
        unauthorized_entry = bool(ingress_profile["unauthorized"])

        if not ingress_profile["automatic"]:
            attempt = ingress_profile.get("attempt") or {}
            if not bool(attempt.get("success")):
                damage_result = self.apply_ingress_structure_damage(
                    eid,
                    candidate,
                    ingress_method,
                    success=False,
                    fumbled=bool(attempt.get("fumbled")),
                    tool_terms=ingress_profile.get("tool_terms") or {},
                )
                self.emit_failed_ingress_attempt(
                    eid,
                    candidate,
                    prop,
                    ingress,
                    ingress_method,
                    severity_bonus=severity_bonus,
                    offense_bonus=offense_bonus,
                )
                _maybe_damage_access_tool(
                    self.sim,
                    eid,
                    ingress_profile.get("tool_terms") or {},
                    prop=prop,
                    score=attempt.get("score", 0.0),
                    required=attempt.get("required", 0.0),
                    context=ingress_profile.get("context") or "side_entry",
                    channel=ingress_profile.get("channel") or "ingress_attempt",
                    fumbled=bool(attempt.get("fumbled")),
                    force_wear=wall_breach,
                )
                _log_player_feedback(
                    self.sim,
                    " ".join(
                        part
                        for part in (
                            self.failed_ingress_attempt_text(
                                ingress_mode,
                                ingress_method,
                                prop,
                                fumbled=bool(attempt.get("fumbled")),
                                eid=eid,
                            ),
                            self.structural_damage_feedback(damage_result),
                        )
                        if str(part or "").strip()
                    ),
                    kind="movement",
                )
                return

        damage_result = self.apply_ingress_structure_damage(
            eid,
            candidate,
            ingress_method,
            success=not ingress_profile["automatic"],
            fumbled=False,
            tool_terms=ingress_profile.get("tool_terms") or {},
        )
        if wall_breach:
            attempt = ingress_profile.get("attempt") or {}
            _maybe_damage_access_tool(
                self.sim,
                eid,
                ingress_profile.get("tool_terms") or {},
                prop=prop,
                score=attempt.get("score", 0.0),
                required=attempt.get("required", 0.0),
                context=ingress_profile.get("context") or "wall_breach",
                channel=ingress_profile.get("channel") or "wall_breach",
                fumbled=False,
                force_wear=True,
            )
            if damage_result and not damage_result.get("broken"):
                self.emit_failed_ingress_attempt(
                    eid,
                    candidate,
                    prop,
                    ingress,
                    ingress_method,
                    severity_bonus=severity_bonus,
                    offense_bonus=offense_bonus,
                )
                damage_text = self.structural_damage_feedback(damage_result)
                _log_player_feedback(
                    self.sim,
                    f"Your blow lands, but the wall holds. {damage_text}".strip(),
                    kind="movement",
                )
                return
        self.open_ingress_tile(
            candidate,
            hostile=bool(hostile or ingress_method == "forced_side_entry"),
        )
        damage_text = self.structural_damage_feedback(damage_result)
        if damage_text and damage_result and damage_result.get("broken"):
            _log_player_feedback(self.sim, damage_text, kind="movement")

        moved, reason = try_move_entity(
            self.sim,
            eid=eid,
            new_x=candidate["x"],
            new_y=candidate["y"],
            new_z=candidate["z"],
            reason=str(ingress_mode or "ingress"),
        )
        if not moved:
            _log_player_feedback(
                self.sim,
                self.ingress_blocked_text(reason, ingress_mode, prop, eid=eid),
                kind="movement",
            )
            return

        new_pos = self.sim.ecs.get(Position).get(eid)
        access = _evaluate_property_access(
            self.sim,
            eid,
            prop,
            x=candidate["x"],
            y=candidate["y"],
            z=candidate["z"],
            breach_severity=ingress.breach_severity,
        )
        observation = observation_payload_for_position(
            self.sim,
            candidate["x"],
            candidate["y"],
            candidate["z"],
            exclude_eid=eid,
            offender_eid=eid,
            observation_channels=("actor_witness",),
        )
        ingress_kind = str(ingress.ingress_kind or "").strip().lower()
        aperture_kind = str(ingress.aperture_kind or "").strip().lower()
        if ingress_kind in {"boundary_breach", "deep_breach"}:
            _record_building_damage(
                self.sim,
                prop,
                candidate["x"],
                candidate["y"],
                candidate["z"],
                kind="wall",
                cause=ingress_method,
            )
        elif ingress_kind == "alternate_aperture" and _is_window_aperture(aperture_kind):
            _record_building_damage(
                self.sim,
                prop,
                candidate["x"],
                candidate["y"],
                candidate["z"],
                kind="window",
                aperture_kind=aperture_kind,
                cause=ingress_method,
            )
        elif ingress_method == "forced_side_entry" and _is_side_aperture(aperture_kind):
            _record_building_damage(
                self.sim,
                prop,
                candidate["x"],
                candidate["y"],
                candidate["z"],
                kind="door",
                aperture_kind=aperture_kind,
                cause=ingress_method,
            )

        shared_interests = _shared_property_interests_for_position(
            self.sim,
            candidate["x"],
            candidate["y"],
            candidate["z"],
            primary_prop=prop,
        )
        room_access_payload = _room_access_event_payload(access)
        room_common_area_kind = room_access_payload.pop("common_area_kind", "")
        shared_interest_payload = _shared_property_interest_event_payload(shared_interests)
        if (
            room_common_area_kind
            and not shared_interest_payload.get("common_area_kind")
        ):
            shared_interest_payload["common_area_kind"] = room_common_area_kind

        if hostile:
            severity_score = max(
                24,
                int(access.severity_score) + int(round(float(ingress.breach_severity) * 12.0)),
            )
            severity_score = min(100, severity_score + int(max(0, severity_bonus)))
            severity_label = _trespass_label_from_score(severity_score)
            self.sim.emit(Event(
                "property_tamper",
                offender_eid=eid,
                property_id=prop["id"],
                owner_eid=prop.get("owner_eid"),
                x=candidate["x"],
                y=candidate["y"],
                z=candidate["z"],
                **observation,
                access_level=access.access_level,
                severity_score=severity_score,
                severity_label=severity_label,
                standing_reason=access.standing_reason,
                ingress_kind=ingress.ingress_kind,
                aperture_kind=ingress.aperture_kind,
                ingress_method=ingress_method,
                breach_severity=ingress.breach_severity,
                **room_access_payload,
                **shared_interest_payload,
            ))
            offense_score = min(
                100,
                self.action_system._offense_score_for("tamper", context="ordinary")
                + int(round(float(ingress.breach_severity) * 14.0))
                + int(max(0, offense_bonus)),
            )
            self.action_system._emit_action_offense(
                eid=eid,
                action="tamper",
                context="ordinary",
                score=offense_score,
                x=candidate["x"],
                y=candidate["y"],
                z=candidate["z"],
                **observation,
            )
        elif unauthorized_entry:
            severity_score = max(
                16,
                int(access.severity_score) + int(round(float(ingress.breach_severity) * 10.0)),
            )
            severity_score = min(100, severity_score + int(max(0, severity_bonus)))
            severity_label = _trespass_label_from_score(severity_score)
            offense_score = min(
                100,
                max(
                    self.action_system._offense_score_for("move", context="trespass"),
                    14,
                )
                + int(round(float(ingress.breach_severity) * 10.0))
                + int(max(0, offense_bonus)),
            )
            if maybe_emit_accidental_trespass_boundary(
                self.sim,
                eid=eid,
                prop=prop,
                access=access,
                ingress=ingress,
                x=candidate["x"],
                y=candidate["y"],
                z=candidate["z"],
                observation=observation,
                ingress_method=ingress_method,
                action="move",
                offense_score=offense_score,
            ):
                return
            self.sim.emit(Event(
                "property_trespass",
                offender_eid=eid,
                property_id=prop["id"],
                owner_eid=prop.get("owner_eid"),
                x=candidate["x"],
                y=candidate["y"],
                z=candidate["z"],
                **observation,
                access_level=access.access_level,
                severity_score=severity_score,
                severity_label=severity_label,
                standing_reason=access.standing_reason,
                currently_open=access.currently_open,
                current_hour=access.current_hour,
                ingress_kind=ingress.ingress_kind,
                aperture_kind=ingress.aperture_kind,
                ingress_method=ingress_method,
                breach_severity=ingress.breach_severity,
                **room_access_payload,
                **shared_interest_payload,
            ))
            self.action_system._emit_action_offense(
                eid=eid,
                action="move",
                context="trespass",
                score=offense_score,
                x=candidate["x"],
                y=candidate["y"],
                z=candidate["z"],
                **observation,
            )
        else:
            name = prop.get("name", prop.get("id", "property"))
            reason_text = _standing_reason_label(claim_reason)
            mode_text = _ingress_mode_label(ingress_mode)
            method_text = _ingress_method_label(ingress_method)
            if reason_text:
                if method_text and method_text != "authorized":
                    _log_player_feedback(
                        self.sim,
                        f"Used {mode_text} into {name} ({reason_text}, {method_text}).",
                        kind="movement",
                    )
                else:
                    _log_player_feedback(
                        self.sim,
                        f"Used {mode_text} into {name} ({reason_text}).",
                        kind="movement",
                    )
            else:
                if method_text and method_text != "authorized":
                    _log_player_feedback(
                        self.sim,
                        f"Used {mode_text} into {name} ({method_text}).",
                        kind="movement",
                    )
                else:
                    _log_player_feedback(self.sim, f"Used {mode_text} into {name}.", kind="movement")

        self.action_system._refresh_cover_after_move(eid, new_pos, had_cover=had_cover)
