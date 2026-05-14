"""Shared disguise scrutiny and security-fixture helpers."""

from engine.events import Event

from game.components import AI, Occupation
from game.population import INDUSTRIAL_ARCHETYPES, SALVAGE_ARCHETYPES, SECURITY_ARCHETYPES
from game.property_access import (
    _property_archetype,
    property_access_level as _property_access_level,
    property_claim_reason as _property_claim_reason,
)
from game.service_runtime import _int_or_default


def _npc_recognizes_player(memory, player_eid):
    """Return the strength of a live ``recognized`` memory entry for player_eid."""
    if memory is None:
        return 0.0
    best = 0.0
    for entry in memory.entries:
        if entry.get("kind") != "recognized":
            continue
        data = entry.get("data") or {}
        if data.get("player_eid") == player_eid:
            best = max(best, float(entry.get("strength", 0.0)))
    return best


def _degrade_player_disguise(sim, player_eid, amount=0.35):
    """Reduce active disguise strength; clear it if it hits zero."""
    disguise = getattr(sim, "disguise_state", None)
    if not isinstance(disguise, dict):
        return
    new_strength = float(disguise.get("strength", 0.0)) - float(amount)
    if new_strength <= 0.0:
        sim.disguise_state = None
        sim.emit(Event(
            "disguise_blown",
            eid=player_eid,
            item_id=disguise.get("item_id"),
            item_name=disguise.get("item_name", ""),
        ))
    else:
        disguise["strength"] = round(new_strength, 3)


def _observer_primary_role(sim, observer_eid):
    if sim is None or observer_eid is None:
        return ""
    ai = sim.ecs.get(AI).get(observer_eid)
    role = str(getattr(ai, "role", "") or "").strip().lower()
    if role and role != "civilian":
        return role

    occupation = sim.ecs.get(Occupation).get(observer_eid)
    career = str(getattr(occupation, "career", "") or "").strip().lower()
    if any(token in career for token in ("guard", "security", "patrol", "watch")):
        return "guard"
    if any(token in career for token in ("worker", "labor", "loader", "mechanic", "salvage", "operator", "janitor", "tech")):
        return "worker"
    return role


def _npc_disguise_scrutiny_profile(sim, observer_eid, prop, *, offender_eid=None):
    if sim is None or observer_eid is None or not isinstance(prop, dict):
        return None
    if offender_eid != getattr(sim, "player_eid", None):
        return None
    disguise = getattr(sim, "disguise_state", None)
    if not isinstance(disguise, dict):
        return None

    role_id = str(disguise.get("role_id", "") or "").strip().lower()
    strength = max(0.0, float(disguise.get("strength", 0.0) or 0.0))
    if role_id not in {"guard", "worker"} or strength <= 0.0:
        return None

    archetype = _property_archetype(prop)
    access_level = _property_access_level(prop)
    security_site = archetype in SECURITY_ARCHETYPES or access_level == "restricted"
    worker_site = archetype in INDUSTRIAL_ARCHETYPES or archetype in SALVAGE_ARCHETYPES
    observer_role = _observer_primary_role(sim, observer_eid)
    observer_access, observer_claim = _property_claim_reason(
        sim,
        observer_eid,
        prop,
        x=prop.get("x"),
        y=prop.get("y"),
        z=prop.get("z", 0),
        min_standing=0.58,
    )
    embedded_observer = observer_claim in {"owner", "employee", "credential_holder", "resident"}

    fit_score = 0
    if role_id == "guard":
        fit_score += 2 if security_site else -2 if worker_site else -1
        if observer_role == "guard":
            fit_score += 2
        elif observer_role == "worker":
            fit_score -= 2
        if embedded_observer and security_site:
            fit_score += 1
    elif role_id == "worker":
        fit_score += 2 if worker_site else -2 if security_site else -1
        if observer_role == "worker":
            fit_score += 2
        elif observer_role == "guard":
            fit_score -= 2
        if embedded_observer and worker_site:
            fit_score += 1

    if fit_score >= 5:
        fit_label = "strong_fit"
        suspicion_mult = 0.52
        recognition_floor = 0.18
    elif fit_score >= 3:
        fit_label = "good_fit"
        suspicion_mult = 0.68
        recognition_floor = 0.24
    elif fit_score >= 1:
        fit_label = "partial_fit"
        suspicion_mult = 0.86
        recognition_floor = 0.32
    elif fit_score <= -3:
        fit_label = "hard_mismatch"
        suspicion_mult = 1.38
        recognition_floor = 0.62
    else:
        fit_label = "soft_mismatch"
        suspicion_mult = 1.18
        recognition_floor = 0.48

    if fit_score >= 1:
        suspicion_mult += max(0.0, (1.0 - strength) * 0.28)
    else:
        suspicion_mult += max(0.0, (1.0 - strength) * 0.12)

    return {
        "role_id": role_id,
        "strength": round(strength, 3),
        "observer_role": observer_role,
        "observer_claim": observer_claim,
        "observer_standing": round(float(observer_access.standing), 3) if observer_access else 0.0,
        "fit_score": int(fit_score),
        "fit_label": fit_label,
        "suspicion_mult": round(float(suspicion_mult), 3),
        "recognition_floor": round(float(recognition_floor), 3),
        "allow_pass": bool(fit_label == "strong_fit" and strength >= 0.72),
        "downgrade_protect": bool(fit_label in {"strong_fit", "good_fit"} and strength >= 0.62),
        "escalate_warn": bool(fit_label == "hard_mismatch"),
    }


def _security_fixture_temporarily_disabled_until(sim, prop):
    if not isinstance(prop, dict):
        return 0
    disabled_map = getattr(sim, "camera_disabled", {})
    if not isinstance(disabled_map, dict):
        return 0
    return _int_or_default(disabled_map.get(prop.get("id"), 0), 0)


def _security_fixture_power_cut_active(sim, prop, *, tick=None):
    if not isinstance(prop, dict):
        return False
    if tick is None:
        tick = int(getattr(sim, "tick", 0))
    power_cuts = getattr(sim, "fixture_power_cuts", {})
    if not isinstance(power_cuts, dict):
        return False
    prop_id = str(prop.get("id", "")).strip()
    if prop_id and _int_or_default(power_cuts.get(prop_id), 0) > int(tick):
        return True
    cover_index = getattr(sim, "property_cover_index", {})
    if not isinstance(cover_index, dict):
        return False
    prop_x = int(prop.get("x", 0))
    prop_y = int(prop.get("y", 0))
    prop_z = int(prop.get("z", 0))
    for covered_pid in cover_index.get((prop_x, prop_y, prop_z), ()):
        if _int_or_default(power_cuts.get(covered_pid), 0) > int(tick):
            return True
    return False


def _security_fixture_is_online(sim, prop, *, tick=None):
    if not isinstance(prop, dict):
        return False
    if tick is None:
        tick = int(getattr(sim, "tick", 0))
    if _security_fixture_power_cut_active(sim, prop, tick=tick):
        return False
    if _security_fixture_temporarily_disabled_until(sim, prop) > int(tick):
        return False
    return True


def _camera_disguise_scrutiny_profile(sim, prop):
    disguise = getattr(sim, "disguise_state", None)
    if not isinstance(disguise, dict):
        return None
    role_id = str(disguise.get("role_id", "") or "").strip().lower()
    strength = max(0.0, float(disguise.get("strength", 0.0) or 0.0))
    if not role_id or strength <= 0.0:
        return None
    archetype = _property_archetype(prop) if isinstance(prop, dict) else ""
    access_level = _property_access_level(prop) if isinstance(prop, dict) else "public"
    protected_site = access_level != "public"
    security_site = archetype in SECURITY_ARCHETYPES or protected_site
    worker_site = archetype in INDUSTRIAL_ARCHETYPES or archetype in SALVAGE_ARCHETYPES
    if role_id == "guard":
        threshold = 1.12 if security_site else 0.78
        increment = 0.34 if security_site else 0.58
    elif role_id == "worker":
        if worker_site:
            threshold = 0.96
            increment = 0.41
        elif security_site:
            threshold = 0.52
            increment = 0.78
        else:
            threshold = 0.4
            increment = 0.9
    else:
        return None

    threshold *= max(0.75, min(1.1, 0.7 + (strength * 0.35)))
    increment *= max(0.72, min(1.08, 1.04 - (strength * 0.16)))
    return {
        "threshold": round(float(threshold), 3),
        "increment": round(float(increment), 3),
        "role_id": role_id,
        "strength": round(float(strength), 3),
    }
