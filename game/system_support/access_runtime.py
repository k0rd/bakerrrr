"""Shared property-access and lock-override runtime helpers."""

from engine.events import Event

from game.components import PlayerModeState
from game.property_access import (
    property_access_controller as _property_access_controller,
    property_access_level as _property_access_level,
)
from game.property_keys import property_lock_state
from game.organizations import actor_org_practices
from game.property_runtime import _int_or_default, property_metadata as _property_metadata
from game.skills import actor_skill as _actor_skill, actor_tool_terms as _actor_tool_terms
from game.system_support.access_checks import _maybe_damage_access_tool, _resolve_access_skill_check
from game.system_support.awareness_runtime import observation_payload_for_position
from game.system_support.intrusion_runtime import _trespass_label_from_score
from game.system_support.offense_runtime import _emit_action_offense_event


def _access_tool_context_for(sim, prop=None, *, ignition=False, context=None):
    if context:
        return str(context).strip().lower()
    if ignition:
        return "vehicle_ignition"
    if isinstance(prop, dict) and str(prop.get("kind", "")).strip().lower() == "building":
        power_cuts = getattr(sim, "fixture_power_cuts", {})
        if power_cuts:
            prop_id = str(prop.get("id", "")).strip()
            cut_until = power_cuts.get(prop_id, 0)
            tick = int(getattr(sim, "tick", 0))
            if isinstance(cut_until, (int, float)) and int(cut_until) > tick:
                return "mechanical_lock"
        controller = _property_access_controller(sim, prop)
        credential_mode = str(controller.get("credential_mode", "mechanical_key")).strip().lower()
        if credential_mode == "badge":
            return "badge_controller"
        if credential_mode == "biometric":
            return "biometric_controller"
    return "mechanical_lock"


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _bounded_mult(value, *, default=1.0, low=0.25, high=4.0):
    return max(float(low), min(float(high), _safe_float(value, default=default)))


def _access_tool_terms_for_actor(sim, eid, prop=None, *, ignition=False, context=None):
    tool_terms = dict(
        _actor_tool_terms(
            sim,
            eid,
            _access_tool_context_for(sim, prop, ignition=ignition, context=context),
        )
    )
    if not isinstance(prop, dict):
        return tool_terms

    practice_rows = []
    practice_notes = []
    aggregated = {}
    for row in actor_org_practices(
        sim,
        eid,
        active_only=True,
        current_tick=getattr(sim, "tick", 0),
    ):
        property_id = str(row.get("membership_site_property_id", "") or "").strip()
        if property_id and property_id != str(prop.get("id", "")).strip():
            continue
        practice_rows.append(row)
        note = str(row.get("summary") or row.get("label") or "").strip()
        if note and note not in practice_notes:
            practice_notes.append(note)
        for raw_key, raw_value in dict(row.get("effect_modifiers", {}) or {}).items():
            key = str(raw_key or "").strip().lower().replace(" ", "_")
            if not key:
                continue
            value = _safe_float(raw_value, default=0.0)
            if key.endswith("_mult") or key.endswith("_scalar"):
                aggregated[key] = _safe_float(aggregated.get(key), default=1.0) * max(0.0, value)
            else:
                aggregated[key] = _safe_float(aggregated.get(key), default=0.0) + value

    modifiers = aggregated
    if not modifiers:
        return tool_terms

    for key in ("intrusion_bonus", "mechanics_bonus", "perception_bonus", "score_bonus", "requirement_delta"):
        tool_terms[key] = _safe_float(tool_terms.get(key), default=0.0) + _safe_float(modifiers.get(key), default=0.0)
    tool_terms["tool_wear_mult"] = _bounded_mult(
        _safe_float(tool_terms.get("tool_wear_mult"), default=1.0) * _safe_float(modifiers.get("tool_wear_mult"), default=1.0),
        default=1.0,
        low=0.25,
        high=4.0,
    )
    tool_terms["tamper_severity_mult"] = _bounded_mult(
        _safe_float(tool_terms.get("tamper_severity_mult"), default=1.0) * _safe_float(modifiers.get("tamper_severity_mult"), default=1.0),
        default=1.0,
        low=0.4,
        high=2.0,
    )
    practice_note = "; ".join(practice_notes[:3])
    if practice_note:
        tool_terms["practice_note"] = practice_note
    return tool_terms


def _access_override_score_for_actor(sim, eid, *, tool_terms=None, ignition=False):
    modes = sim.ecs.get(PlayerModeState).get(eid)
    tool_terms = tool_terms or {}
    intrusion = _actor_skill(sim, eid, "intrusion") + float(tool_terms.get("intrusion_bonus", 0.0))
    mechanics = _actor_skill(sim, eid, "mechanics") + float(tool_terms.get("mechanics_bonus", 0.0))
    perception = _actor_skill(sim, eid, "perception") + float(tool_terms.get("perception_bonus", 0.0))
    score = intrusion
    score += max(0.0, intrusion - 5.0) * 0.28
    score += max(0.0, mechanics - 5.0) * (0.4 if ignition else 0.18)
    score += max(0.0, perception - 5.0) * 0.16
    score += float(tool_terms.get("score_bonus", 0.0))
    if modes and modes.sneak:
        score += 0.5
    return score


def _lock_override_required_for_prop(sim, prop, *, tool_terms=None, ignition=False):
    lock_state = property_lock_state(prop)
    access_level = _property_access_level(prop)
    tool_terms = tool_terms or {}
    required = float(4.75 if tool_terms.get("enabled") else 7.75) + float(lock_state["lock_tier"])
    if access_level == "restricted":
        required += 0.5
    if isinstance(prop, dict) and str(prop.get("kind", "")).strip().lower() == "building":
        controller = _property_access_controller(sim, prop)
        required += max(0.0, (float(_int_or_default(controller.get("security_tier"), 1)) - 1.0) * 0.15)
        credential_mode = str(controller.get("credential_mode", "")).strip().lower()
        if credential_mode == "badge":
            required += 0.35
        elif credential_mode == "biometric":
            required += 0.75
    if ignition:
        required += 0.75
    required += float(tool_terms.get("requirement_delta", 0.0))
    return max(1.0, required)


def _emit_property_lock_tamper_event(sim, eid, prop, *, x, y, z, method, tool_terms=None):
    if not isinstance(prop, dict):
        return
    lock_state = property_lock_state(prop)
    access_level = _property_access_level(prop)
    observation = observation_payload_for_position(
        sim,
        int(x),
        int(y),
        int(z),
        exclude_eid=eid,
        offender_eid=eid,
        observation_channels=("actor_witness",),
    )
    method_key = str(method or "").strip().lower()
    severity_score = min(
        100,
        18 + (lock_state["lock_tier"] * 7) + (6 if access_level == "restricted" else 0),
    )
    if method_key in {"badge_reader_spoof", "biometric_spoof", "biometric_jam"}:
        severity_score = max(8, severity_score - (6 if method_key == "badge_reader_spoof" else 4))
    severity_mult = _bounded_mult((tool_terms or {}).get("tamper_severity_mult"), default=1.0, low=0.4, high=2.0)
    severity_score = max(4, min(100, int(round(float(severity_score) * severity_mult))))
    sim.emit(Event(
        "property_tamper",
        offender_eid=eid,
        property_id=prop.get("id"),
        owner_eid=prop.get("owner_eid"),
        x=int(x),
        y=int(y),
        z=int(z),
        **observation,
        access_level=access_level,
        severity_score=severity_score,
        severity_label=_trespass_label_from_score(severity_score),
        standing_reason="none",
        ingress_kind="ordinary_entry",
        ingress_method=method_key,
    ))
    _emit_action_offense_event(
        sim,
        eid=eid,
        action="tamper",
        context="ordinary",
        x=int(x),
        y=int(y),
        z=int(z),
    )


def _attempt_locked_property_entry_with_sim(sim, eid, prop, *, target_x, target_y, target_z):
    context = _access_tool_context_for(sim, prop)
    tool_terms = _access_tool_terms_for_actor(sim, eid, prop)
    score = _access_override_score_for_actor(sim, eid, tool_terms=tool_terms)
    required = _lock_override_required_for_prop(sim, prop, tool_terms=tool_terms, ignition=False)
    if not tool_terms.get("enabled") and score + 1.5 < required:
        return False, "locked_property"

    if context == "badge_controller":
        method = "badge_reader_spoof" if tool_terms.get("enabled") else "badge_reader_override"
    elif context == "biometric_controller":
        method = "biometric_spoof" if tool_terms.get("enabled") else "biometric_override"
    else:
        method = "picked_front_door" if tool_terms.get("enabled") else "manual_front_door_override"
    _emit_property_lock_tamper_event(
        sim,
        eid,
        prop,
        x=target_x,
        y=target_y,
        z=target_z,
        method=method,
        tool_terms=tool_terms,
    )
    attempt = _resolve_access_skill_check(
        sim,
        eid=eid,
        prop=prop,
        context=context,
        channel="property_override",
        score=score,
        required=required,
        tool_terms=tool_terms,
        allow_fumble=True,
    )
    if not attempt["success"]:
        _maybe_damage_access_tool(
            sim,
            eid,
            tool_terms,
            prop=prop,
            score=attempt["score"],
            required=attempt["required"],
            context=context,
            channel="property_override",
            fumbled=attempt["fumbled"],
        )
        if attempt["fumbled"]:
            return False, "lock_override_fumble"
        return False, "lock_override_failed"

    metadata = _property_metadata(prop)
    metadata["property_locked"] = False
    metadata["property_override_tick"] = int(getattr(sim, "tick", 0))
    metadata["property_override_method"] = method
    return True, method
