"""Presentation and observation helpers for live organization crime plans."""

from __future__ import annotations

from engine.events import Event
from game.components import OrganizationCrimePlans
from game.organizations import (
    actor_assigned_crime_plans,
    advance_organization_crime_plan,
    crime_plan_method_label,
    organization_crime_plans,
    organization_profile,
)
from game.property_runtime import property_display_position, property_focus_position


CRIME_PLAN_OBSERVATION_SCAN = 0.20
CRIME_PLAN_OBSERVATION_INSPECT = 0.35
CRIME_PLAN_OBSERVATION_WITNESS = 0.45
CRIME_PLAN_DELAY_THRESHOLD = 0.75
CRIME_PLAN_CANCEL_THRESHOLD = 1.25
CRIME_PLAN_DISRUPTION_DELAY_TICKS = 24
CRIME_PLAN_DISRUPTION_MAX = 2.0

_ACTIVE_STAGES = {"forming", "rendezvous", "executing", "disposing", "cooldown"}


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


def _text(value):
    return str(value or "").strip()


def _stage_label(stage):
    key = _text(stage).lower().replace(" ", "_")
    return {
        "forming": "forming",
        "rendezvous": "rendezvous",
        "executing": "working",
        "disposing": "clearing",
        "cooldown": "quieting",
    }.get(key, key.replace("_", " ") or "active")


def _property_anchor(prop):
    if not isinstance(prop, dict):
        return None
    anchor = property_focus_position(prop) or property_display_position(prop)
    if anchor is not None:
        try:
            return (int(anchor[0]), int(anchor[1]), int(anchor[2]))
        except (TypeError, ValueError, IndexError):
            pass
    try:
        return (int(prop.get("x", 0)), int(prop.get("y", 0)), int(prop.get("z", 0)))
    except (TypeError, ValueError, AttributeError):
        return None


def _profile_fields(sim, organization_eid):
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return {"organization_name": "", "organization_key": "", "organization_kind": "other"}
    return {
        "organization_name": _text(getattr(profile, "name", "")),
        "organization_key": _text(getattr(profile, "key", "")),
        "organization_kind": _text(getattr(profile, "kind", "")).lower() or "other",
    }


def _plan_property_role(plan, prop):
    if not isinstance(plan, dict) or not isinstance(prop, dict):
        return ""
    property_id = _text(prop.get("id"))
    if not property_id:
        return ""
    roles = {}
    if _text(plan.get("staging_property_id")) == property_id:
        roles["staging"] = "staging"
    if _text(plan.get("target_property_id")) == property_id:
        roles["target"] = "target"
    if _text(plan.get("disposal_property_id")) == property_id:
        roles["handoff"] = "handoff"
    if not roles:
        return ""
    stage = _text(plan.get("stage")).lower()
    if stage in {"forming", "rendezvous"} and "staging" in roles:
        return "staging"
    if stage in {"disposing", "cooldown"} and "handoff" in roles:
        return "handoff"
    if "target" in roles:
        return "target"
    if "staging" in roles:
        return "staging"
    return "handoff"


def _actor_activity_text(plan):
    stage = _text(plan.get("stage")).lower()
    method_key = _text(plan.get("method_key")).lower()
    if stage in {"forming", "rendezvous"}:
        if method_key in {"covert_sale_handoff", "fence_run_handoff"}:
            return "waiting on a crew handoff"
        return "waiting on a crew move"
    if stage == "executing":
        if method_key == "rear_entry_burglary":
            return "working a rear entry"
        if method_key == "soft_target_sweep":
            return "working a soft target"
        if method_key == "covert_sale_handoff":
            return "moving a covert handoff"
        if method_key == "fence_run_handoff":
            return "moving a fence handoff"
    if stage in {"disposing", "cooldown"}:
        if method_key == "fence_run_handoff":
            return "clearing a fence handoff"
        if method_key == "covert_sale_handoff":
            return "clearing a covert handoff"
        return "clearing a crew handoff"
    return "moving with a crew plan"


def _surface_row_for_plan(sim, plan, *, prop=None, actor_eid=None):
    if not isinstance(plan, dict):
        return None
    stage = _text(plan.get("stage")).lower()
    if stage not in _ACTIVE_STAGES:
        return None
    role = ""
    anchor = None
    property_id = ""
    if isinstance(prop, dict):
        role = _plan_property_role(plan, prop)
        if not role:
            return None
        property_id = _text(prop.get("id"))
        anchor = _property_anchor(prop)
    elif actor_eid is not None:
        role = "member"
        property_id = (
            _text(plan.get("staging_property_id"))
            if stage in {"forming", "rendezvous"}
            else _text(plan.get("disposal_property_id"))
            if stage in {"disposing", "cooldown"}
            else _text(plan.get("target_property_id"))
        )
        anchor_prop = getattr(sim, "properties", {}).get(property_id)
        anchor = _property_anchor(anchor_prop)
    else:
        return None

    organization_eid = _safe_int(plan.get("organization_eid"), default=0)
    profile = _profile_fields(sim, organization_eid)
    method_key = _text(plan.get("method_key")).lower()
    method_label = _text(plan.get("method_label")) or crime_plan_method_label(method_key, plan.get("kind"))
    stage_label = _stage_label(stage)
    org_name = _text(profile.get("organization_name")) or "a local crew"
    site_phrase = {
        "staging": "staging from this site",
        "target": "working this target",
        "handoff": "using this handoff site",
        "member": "assigned to the move",
    }.get(role, "active here")
    surface_text = f"{org_name} is {stage_label} a {method_label}, {site_phrase}"
    actor_text = _actor_activity_text({"stage": stage, "method_key": method_key})
    action = "scan or inspect to mark the crew activity; repeated pressure can spook it"
    return {
        **plan,
        **profile,
        "organization_eid": organization_eid or plan.get("organization_eid"),
        "site_role": role,
        "property_id": property_id or None,
        "anchor": anchor,
        "method_key": method_key,
        "method_label": method_label,
        "stage": stage,
        "stage_label": stage_label,
        "surface_text": surface_text,
        "actor_text": actor_text,
        "action": action,
    }


def crime_plan_surface_rows(sim, prop=None, actor_eid=None, current_tick=None):
    """Return compact live rows for directly relevant plan property/actor reads."""

    tick = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, default=0)
    rows = []
    if actor_eid is not None:
        for plan in actor_assigned_crime_plans(sim, actor_eid, include_inactive=False, current_tick=tick):
            row = _surface_row_for_plan(sim, plan, actor_eid=actor_eid)
            if row:
                rows.append(row)
    elif isinstance(prop, dict):
        for organization_eid in tuple(sim.ecs.get(OrganizationCrimePlans).keys()):
            for plan in organization_crime_plans(sim, organization_eid, include_inactive=False, current_tick=tick):
                row = _surface_row_for_plan(sim, plan, prop=prop)
                if row:
                    rows.append(row)
    rows.sort(
        key=lambda row: (
            0 if row.get("stage") in {"executing", "disposing"} else 1,
            {"target": 0, "staging": 1, "handoff": 2, "member": 3}.get(row.get("site_role"), 4),
            -_safe_float(row.get("disruption_score"), default=0.0),
            -_safe_int(row.get("last_update_tick"), default=0),
            _text(row.get("plan_key")),
        )
    )
    return tuple(rows)


def _active_plan_by_key(sim, plan_key, *, current_tick=None):
    clean_key = _text(plan_key).lower().replace(" ", "_")
    if not clean_key:
        return None
    tick = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, default=0)
    for organization_eid in tuple(sim.ecs.get(OrganizationCrimePlans).keys()):
        for plan in organization_crime_plans(sim, organization_eid, include_inactive=False, current_tick=tick):
            if _text(plan.get("plan_key")).lower() == clean_key:
                return dict(plan)
    return None


def _plan_event_anchor(sim, plan):
    if not isinstance(plan, dict):
        return None
    stage = _text(plan.get("stage")).lower()
    property_ids = ()
    if stage in {"forming", "rendezvous"}:
        property_ids = (_text(plan.get("staging_property_id")), _text(plan.get("target_property_id")))
    elif stage in {"disposing", "cooldown"}:
        property_ids = (_text(plan.get("disposal_property_id")), _text(plan.get("target_property_id")))
    else:
        property_ids = (_text(plan.get("target_property_id")), _text(plan.get("staging_property_id")), _text(plan.get("disposal_property_id")))
    for property_id in property_ids:
        prop = getattr(sim, "properties", {}).get(property_id)
        anchor = _property_anchor(prop)
        if anchor is not None:
            return anchor
    return None


def _emit_disruption_event(sim, plan, *, action, observer_eid=None, score=0.0):
    organization_eid = _safe_int(plan.get("organization_eid"), default=0)
    profile = _profile_fields(sim, organization_eid)
    anchor = _plan_event_anchor(sim, plan)
    x = y = z = None
    if anchor is not None:
        x, y, z = anchor
    sim.emit(
        Event(
            "crime_plan_disrupted",
            observer_eid=observer_eid,
            organization_eid=organization_eid or None,
            organization_name=profile.get("organization_name") or None,
            organization_key=profile.get("organization_key") or None,
            organization_kind=profile.get("organization_kind") or None,
            plan_key=_text(plan.get("plan_key")) or None,
            plan_method_key=_text(plan.get("method_key")) or None,
            plan_method_label=_text(plan.get("method_label")) or crime_plan_method_label(plan.get("method_key"), plan.get("kind")),
            plan_stage=_text(plan.get("stage")).lower() or None,
            action=_text(action).lower() or "observed",
            score=round(float(score), 3),
            x=x,
            y=y,
            z=z,
        )
    )


def record_crime_plan_observation(sim, plan_key, observer_eid=None, source_kind="", score_delta=0.0):
    """Add player-facing observation pressure to one active live crime plan."""

    tick = _safe_int(getattr(sim, "tick", 0), default=0)
    plan = _active_plan_by_key(sim, plan_key, current_tick=tick)
    if not isinstance(plan, dict):
        return False
    stage = _text(plan.get("stage")).lower()
    if stage not in _ACTIVE_STAGES:
        return False
    organization_eid = _safe_int(plan.get("organization_eid"), default=0)
    if organization_eid <= 0:
        return False
    old_score = _safe_float(plan.get("disruption_score"), default=0.0)
    new_score = max(0.0, min(CRIME_PLAN_DISRUPTION_MAX, old_score + max(0.0, _safe_float(score_delta, default=0.0))))
    reason = _text(source_kind).lower().replace(" ", "_") or "observed"
    observed_tick = tick if observer_eid in {None, getattr(sim, "player_eid", None)} else plan.get("observed_by_player_tick")
    last_reason = _text(plan.get("last_disruption_reason")).lower()

    if new_score >= CRIME_PLAN_CANCEL_THRESHOLD and stage in {"forming", "rendezvous", "executing", "disposing"}:
        updated = advance_organization_crime_plan(
            sim,
            organization_eid,
            plan.get("plan_key"),
            stage="cancelled",
            result="spooked",
            resolved_tick=tick,
            observed_by_player_tick=observed_tick,
            disruption_score=new_score,
            last_disruption_reason="spooked",
            summary="crew got spooked and broke off the plan",
        )
        _emit_disruption_event(sim, updated or plan, action="cancelled", observer_eid=observer_eid, score=new_score)
        return True

    if (
        new_score >= CRIME_PLAN_DELAY_THRESHOLD
        and stage in {"forming", "rendezvous"}
        and last_reason != "delayed"
    ):
        execute_after = max(_safe_int(plan.get("execute_after_tick"), default=tick), tick) + CRIME_PLAN_DISRUPTION_DELAY_TICKS
        updated = advance_organization_crime_plan(
            sim,
            organization_eid,
            plan.get("plan_key"),
            execute_after_tick=execute_after,
            observed_by_player_tick=observed_tick,
            disruption_score=new_score,
            last_disruption_reason="delayed",
            summary="crew got spooked and slowed down",
        )
        _emit_disruption_event(sim, updated or plan, action="delayed", observer_eid=observer_eid, score=new_score)
        return True

    advance_organization_crime_plan(
        sim,
        organization_eid,
        plan.get("plan_key"),
        observed_by_player_tick=observed_tick,
        disruption_score=new_score,
        last_disruption_reason=last_reason if last_reason == "delayed" else reason,
    )
    return True
