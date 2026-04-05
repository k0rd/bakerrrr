"""Player-owned business account and operating runtime.

This module adds a thin economics spine for player-owned businesses:

- eligible owned businesses get a dedicated account
- incumbent staff are retained into a simple roster
- businesses run one hourly operating cycle at a time
- revenue and payroll depend on staffing plus local economy health
"""

from __future__ import annotations

import random

from engine.events import Event
from engine.systems import System
from game.components import AI, NPCRoutine, Occupation, OrganizationAffiliations, PlayerAssets, Position
from game.economy import chunk_economy_profile, pick_career_for_workplace, workplace_archetype_weight
from game.organizations import (
    ensure_property_organization,
    property_org_members,
    property_organization_eid,
    sync_actor_organization_affiliations,
)
from game.property_access import (
    finance_services_for_property as _finance_services_for_property,
    property_is_open as _property_is_open,
    property_is_storefront as _property_is_storefront,
    property_open_window as _property_open_window,
    site_services_for_property as _site_services_for_property,
)
from game.property_runtime import (
    property_covering as _property_covering,
    property_distance as _property_distance,
    property_focus_position as _property_focus_position,
)
from game.skills import actor_skill as _actor_skill


RESIDENTIAL_ARCHETYPES = {
    "apartment",
    "house",
    "tenement",
    "ranger_hut",
    "ruin_shelter",
    "field_camp",
    "survey_post",
    "beacon_house",
}
LODGING_ARCHETYPES = RESIDENTIAL_ARCHETYPES | {
    "flophouse",
    "hotel",
}
PUBLIC_OWNER_TAGS = {
    "",
    "city",
    "community",
    "neutral",
    "none",
    "public",
    "unowned",
}
LARGE_STAFF_ARCHETYPES = {
    "hotel",
    "warehouse",
    "factory",
    "nightclub",
    "music_venue",
    "gaming_hall",
    "metro_exchange",
    "field_hospital",
    "freight_depot",
    "bank",
    "cold_storage",
    "brokerage",
}
BUSINESS_BASE_REVENUE = {
    "bank": 12,
    "brokerage": 11,
    "corner_store": 9,
    "hotel": 12,
    "nightclub": 11,
    "restaurant": 10,
    "music_venue": 11,
    "gaming_hall": 11,
    "backroom_clinic": 10,
    "pharmacy": 10,
    "auto_garage": 10,
    "pawn_shop": 10,
    "tool_depot": 10,
}
ROLE_WAGES = {
    "manager": 4,
    "staff": 3,
}
ROLE_WORK_PRACTICE_TOTAL = {
    "manager": 0.14,
    "staff": 0.12,
}
CUSTOMER_POLICY_ORDER = ("public", "staff_only", "closed")
CUSTOMER_POLICY_LABELS = {
    "public": "public",
    "staff_only": "staff-only",
    "closed": "closed",
}
BUSINESS_HOURS_MODE_ORDER = ("normal", "extended", "always_open")
BUSINESS_HOURS_MODE_LABELS = {
    "normal": "normal hours",
    "extended": "extended hours",
    "always_open": "always open",
}
GENERIC_JOBLESS_CAREERS = {
    "",
    "civilian",
    "drunk",
    "resident",
    "thief",
    "unemployed",
}
ROLE_FIT_BASE_WEIGHTS = {
    "manager": {
        "conversation": 0.34,
        "streetwise": 0.22,
        "perception": 0.18,
        "mechanics": 0.10,
        "intrusion": 0.08,
        "athletics": 0.08,
    },
    "staff": {
        "conversation": 0.18,
        "streetwise": 0.12,
        "perception": 0.20,
        "mechanics": 0.24,
        "intrusion": 0.10,
        "athletics": 0.16,
    },
}
SOCIAL_ARCHETYPES = {
    "corner_store",
    "gaming_hall",
    "hotel",
    "music_venue",
    "nightclub",
    "pawn_shop",
    "restaurant",
}
FINANCE_ARCHETYPES = {
    "bank",
    "brokerage",
}
CARE_ARCHETYPES = {
    "backroom_clinic",
    "field_hospital",
    "pharmacy",
}
TECH_ARCHETYPES = {
    "auto_garage",
    "cold_storage",
    "factory",
    "freight_depot",
    "tool_depot",
    "warehouse",
}
SECURE_ARCHETYPES = {
    "bank",
    "brokerage",
    "cold_storage",
    "pawn_shop",
    "warehouse",
}


def _text(value):
    return str(value or "").strip()


def _int_or(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _clamp(value, minimum, maximum):
    lower = float(minimum)
    upper = float(maximum)
    if upper < lower:
        lower, upper = upper, lower
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = lower
    return max(lower, min(upper, numeric))


def _normalize_open_window(window):
    if not isinstance(window, (list, tuple)) or len(window) < 2:
        return None
    try:
        start_hour = int(window[0]) % 24
        end_hour = int(window[1]) % 24
    except (TypeError, ValueError):
        return None
    return (start_hour, end_hour)


def _open_window_duration(opening):
    normalized = _normalize_open_window(opening)
    if normalized is None:
        return 0
    start_hour, end_hour = normalized
    if start_hour == end_hour:
        return 24
    return (end_hour - start_hour) % 24


def _expanded_open_window(opening):
    normalized = _normalize_open_window(opening)
    if normalized is None:
        return (7, 22)
    if _open_window_duration(normalized) >= 20:
        return (0, 24)
    start_hour, end_hour = normalized
    lead = 2
    tail = 3
    if _open_window_duration(normalized) <= 10:
        tail = 4
    expanded = ((start_hour - lead) % 24, (end_hour + tail) % 24)
    return (0, 24) if _open_window_duration(expanded) >= 23 else expanded


def _normalize_customer_policy(value):
    clean = _text(value).lower().replace("-", "_").replace(" ", "_")
    if clean not in CUSTOMER_POLICY_ORDER:
        return "public"
    return clean


def _normalize_business_hours_mode(value):
    clean = _text(value).lower().replace("-", "_").replace(" ", "_")
    if clean in {"always", "alwaysopen", "all_day", "all_day_open"}:
        clean = "always_open"
    if clean not in BUSINESS_HOURS_MODE_ORDER:
        return "normal"
    return clean


def _cycle_choice(current, order):
    choices = tuple(order or ())
    if not choices:
        return ""
    clean = str(current or "").strip().lower()
    if clean not in choices:
        return choices[0]
    index = choices.index(clean)
    return choices[(index + 1) % len(choices)]


def _hours_text(opening):
    normalized = _normalize_open_window(opening)
    if normalized is None:
        return "private"
    start_hour, end_hour = normalized
    if start_hour == end_hour:
        return "all day"
    return f"{start_hour:02d}:00-{end_hour:02d}:00"


def _property_metadata(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _property_archetype(prop):
    return _text(_property_metadata(prop).get("archetype")).lower()


def _property_label(prop):
    metadata = _property_metadata(prop)
    return _text(metadata.get("business_name")) or _text(prop.get("name")) or _text(prop.get("id")) or "property"


def _ticks_per_hour(sim):
    traits = getattr(sim, "world_traits", {})
    clock = traits.get("clock", {}) if isinstance(traits, dict) else {}
    if not isinstance(clock, dict):
        clock = {}
    return max(60, _int_or(clock.get("ticks_per_hour", 600), default=600))


def _absolute_hour(sim):
    traits = getattr(sim, "world_traits", {})
    clock = traits.get("clock", {}) if isinstance(traits, dict) else {}
    if not isinstance(clock, dict):
        clock = {}
    start_hour = _int_or(clock.get("start_hour", 9), default=9)
    return start_hour + (_int_or(getattr(sim, "tick", 0), default=0) // _ticks_per_hour(sim))


def _hour_in_window(hour, opening):
    if not isinstance(opening, (list, tuple)) or len(opening) < 2:
        return False
    start_hour = _int_or(opening[0], default=0) % 24
    end_hour = _int_or(opening[1], default=0) % 24
    hour = _int_or(hour, default=0) % 24
    if start_hour == end_hour:
        return True
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def _commute_distance_limit(sim):
    chunk_size = max(6, _int_or(getattr(sim, "chunk_size", 12), default=12))
    return max(12, min(28, chunk_size * 2))


def _anchor_tuple(anchor):
    if not isinstance(anchor, (list, tuple)) or len(anchor) < 3:
        return None
    try:
        return int(anchor[0]), int(anchor[1]), int(anchor[2])
    except (TypeError, ValueError):
        return None


def _actor_home_anchor(sim, actor_eid):
    routine = sim.ecs.get(NPCRoutine).get(actor_eid) if sim is not None else None
    anchor = _anchor_tuple(getattr(routine, "home", None))
    if anchor is not None:
        return anchor
    position = sim.ecs.get(Position).get(actor_eid) if sim is not None else None
    if position is None:
        return None
    return int(position.x), int(position.y), int(position.z)


def _anchor_distance_to_prop(anchor, prop):
    anchor = _anchor_tuple(anchor)
    focus = _property_focus_position(prop)
    if anchor is None or focus is None:
        return 999999
    distance = abs(int(anchor[0]) - int(focus[0])) + abs(int(anchor[1]) - int(focus[1]))
    if int(anchor[2]) != int(focus[2]):
        distance += 8
    return int(distance)


def _property_supports_housing(prop):
    if not isinstance(prop, dict):
        return False
    if _text(prop.get("kind")).lower() != "building":
        return False
    return _property_archetype(prop) in LODGING_ARCHETYPES


def _property_supports_lodging_service(prop):
    if not isinstance(prop, dict):
        return False
    if _text(prop.get("kind")).lower() != "building":
        return False
    services = {
        str(service).strip().lower()
        for service in tuple(_site_services_for_property(prop) or ())
        if str(service).strip()
    }
    return bool(services.intersection({"rest", "shelter"}))


def _housing_owner_rank(prop, owner_eid):
    if not isinstance(prop, dict):
        return 3
    if owner_eid is not None and int(prop.get("owner_eid") or 0) == int(owner_eid):
        return 0
    owner_tag = _text(prop.get("owner_tag")).lower()
    if owner_tag in PUBLIC_OWNER_TAGS or prop.get("owner_eid") in {None, "", 0}:
        return 1
    return 2


def player_business_housing_plan(sim, owner_eid, actor_eid, prop):
    if sim is None or actor_eid is None or not isinstance(prop, dict):
        return None

    commute_limit = _commute_distance_limit(sim)
    home_anchor = _actor_home_anchor(sim, actor_eid)
    home_prop = None
    home_distance = 999999
    if home_anchor is not None:
        home_prop = _property_covering(sim, home_anchor[0], home_anchor[1], home_anchor[2])
        home_distance = _anchor_distance_to_prop(home_anchor, prop)
        if home_distance <= commute_limit:
            return {
                "kind": "existing_home",
                "prop": home_prop,
                "anchor": home_anchor,
                "label": _property_label(home_prop) if isinstance(home_prop, dict) else "home",
                "distance": int(home_distance),
                "local": True,
                "relocated": False,
            }

    if _property_supports_housing(prop) or _property_supports_lodging_service(prop):
        anchor = _property_focus_position(prop)
        if anchor is not None:
            return {
                "kind": "workplace_lodging",
                "prop": prop,
                "anchor": anchor,
                "label": _property_label(prop),
                "distance": 0,
                "local": True,
                "relocated": home_anchor != _anchor_tuple(anchor),
            }

    candidates = []
    for candidate in getattr(sim, "properties", {}).values():
        if not isinstance(candidate, dict):
            continue
        if _text(candidate.get("id")) == _text(prop.get("id")):
            continue
        kind = ""
        if _property_supports_housing(candidate):
            kind = "nearby_housing"
        elif _property_supports_lodging_service(candidate):
            kind = "nearby_lodging"
        if not kind:
            continue
        anchor = _property_focus_position(candidate)
        if anchor is None:
            continue
        distance = _anchor_distance_to_prop(anchor, prop)
        candidates.append((
            int(distance),
            _housing_owner_rank(candidate, owner_eid),
            0 if kind == "nearby_housing" else 1,
            _property_label(candidate).lower(),
            _text(candidate.get("id")),
            {
                "kind": kind,
                "prop": candidate,
                "anchor": anchor,
                "label": _property_label(candidate),
                "distance": int(distance),
                "local": True,
                "relocated": home_anchor != _anchor_tuple(anchor),
            },
        ))

    if candidates:
        candidates.sort()
        return candidates[0][-1]

    if home_anchor is not None:
        return {
            "kind": "existing_home",
            "prop": home_prop,
            "anchor": home_anchor,
            "label": _property_label(home_prop) if isinstance(home_prop, dict) else "home",
            "distance": int(home_distance),
            "local": False,
            "relocated": False,
        }
    return None


def property_supports_player_business(prop):
    if not isinstance(prop, dict):
        return False
    if _text(prop.get("kind")).lower() != "building":
        return False

    archetype = _property_archetype(prop)
    metadata = _property_metadata(prop)
    if archetype in RESIDENTIAL_ARCHETYPES and not bool(metadata.get("business_name")):
        if not _property_is_storefront(prop) and not _finance_services_for_property(prop) and not _site_services_for_property(prop):
            return False

    return bool(
        _property_is_storefront(prop)
        or _finance_services_for_property(prop)
        or _site_services_for_property(prop)
        or _text(metadata.get("business_name"))
    )


def player_business_state(prop, create=False):
    if not property_supports_player_business(prop):
        return None
    metadata = _property_metadata(prop)
    state = metadata.get("player_business")
    if not isinstance(state, dict):
        if not create:
            return None
        state = {}
        metadata["player_business"] = state

    state["account_balance"] = max(0, _int_or(state.get("account_balance"), default=0))
    raw_last_cycle = state.get("last_cycle_hour")
    state["last_cycle_hour"] = None if raw_last_cycle in {None, ""} else _int_or(raw_last_cycle, default=0)
    state["required_staff"] = max(1, _int_or(state.get("required_staff"), default=1))
    state["customer_policy"] = _normalize_customer_policy(state.get("customer_policy"))
    state["hours_mode"] = _normalize_business_hours_mode(state.get("hours_mode"))
    baseline_hours = _normalize_open_window(state.get("baseline_hours"))
    state["baseline_hours"] = list(baseline_hours) if baseline_hours is not None else None

    roster = []
    seen = set()
    for raw_eid in list(state.get("staff_roster", ()) or ()):
        clean_eid = _int_or(raw_eid, default=0)
        if clean_eid <= 0 or clean_eid in seen:
            continue
        seen.add(clean_eid)
        roster.append(clean_eid)
    state["staff_roster"] = roster

    raw_roles = state.get("staff_roles")
    roles = {}
    if isinstance(raw_roles, dict):
        for raw_eid, raw_role in raw_roles.items():
            clean_eid = _int_or(raw_eid, default=0)
            if clean_eid <= 0:
                continue
            role = str(raw_role or "staff").strip().lower()
            if role == "owner":
                role = "manager"
            if role not in {"manager", "staff"}:
                role = "staff"
            roles[str(clean_eid)] = role
    state["staff_roles"] = roles

    summary = state.get("last_summary")
    state["last_summary"] = dict(summary) if isinstance(summary, dict) else {}
    return state


def player_business_account_balance(prop):
    state = player_business_state(prop, create=False)
    return int(state.get("account_balance", 0)) if state else 0


def player_business_customer_policy(prop):
    state = player_business_state(prop, create=False)
    return _normalize_customer_policy(state.get("customer_policy")) if state else "public"


def player_business_customer_policy_label(policy):
    clean = _normalize_customer_policy(policy)
    return CUSTOMER_POLICY_LABELS.get(clean, "public")


def player_business_next_customer_policy(prop):
    return _cycle_choice(player_business_customer_policy(prop), CUSTOMER_POLICY_ORDER)


def player_business_set_customer_policy(prop, policy):
    state = player_business_state(prop, create=True)
    if state is None:
        return "public"
    clean = _normalize_customer_policy(policy)
    state["customer_policy"] = clean
    return clean


def player_business_hours_mode(prop):
    state = player_business_state(prop, create=False)
    return _normalize_business_hours_mode(state.get("hours_mode")) if state else "normal"


def player_business_hours_mode_label(mode):
    clean = _normalize_business_hours_mode(mode)
    return BUSINESS_HOURS_MODE_LABELS.get(clean, "normal hours")


def player_business_next_hours_mode(prop):
    return _cycle_choice(player_business_hours_mode(prop), BUSINESS_HOURS_MODE_ORDER)


def player_business_hours_window(sim, prop, *, mode=None):
    clean_mode = _normalize_business_hours_mode(mode if mode is not None else player_business_hours_mode(prop))
    state = player_business_state(prop, create=False)
    baseline = _normalize_open_window((state or {}).get("baseline_hours"))
    if baseline is None:
        baseline = _normalize_open_window(_property_open_window(sim, prop))
    if clean_mode == "always_open":
        return (0, 24)
    if clean_mode == "extended":
        return _expanded_open_window(baseline)
    return baseline


def player_business_set_hours_mode(sim, prop, mode):
    state = player_business_state(prop, create=True)
    if state is None:
        return None

    baseline = _normalize_open_window(state.get("baseline_hours"))
    if baseline is None:
        baseline = _normalize_open_window(_property_open_window(sim, prop))
        state["baseline_hours"] = list(baseline) if baseline is not None else None

    clean = _normalize_business_hours_mode(mode)
    opening = player_business_hours_window(sim, prop, mode=clean)
    state["hours_mode"] = clean

    metadata = _property_metadata(prop)
    if opening is not None:
        metadata["access_controller_hours"] = [int(opening[0]) % 24, int(opening[1]) % 24]
    else:
        metadata.pop("access_controller_hours", None)

    return {
        "hours_mode": clean,
        "opening_window": opening,
        "hours_text": _hours_text(opening),
    }


def _required_staff_for(prop):
    metadata = _property_metadata(prop)
    configured = _int_or(metadata.get("business_required_staff"), default=0)
    if configured > 0:
        return max(1, min(4, configured))

    archetype = _property_archetype(prop)
    base = 1
    if archetype in LARGE_STAFF_ARCHETYPES:
        base = 3
    elif archetype in {"bank", "brokerage", "hotel", "office", "tower", "nightclub", "music_venue", "backroom_clinic"}:
        base = 2

    complexity = 0
    if _property_is_storefront(prop):
        complexity += 1
    complexity += len(tuple(_finance_services_for_property(prop)))
    complexity += len(tuple(_site_services_for_property(prop)))
    return max(base, min(4, 1 + (complexity // 2)))


def _normalized_role(role, *, default="staff"):
    clean = str(role or default or "staff").strip().lower() or "staff"
    if clean == "owner":
        clean = "manager"
    if clean not in {"manager", "staff"}:
        clean = str(default or "staff").strip().lower() or "staff"
    return clean


def _role_weight_bump(weights, skill_id, amount):
    key = str(skill_id or "").strip().lower()
    if not key:
        return
    try:
        delta = float(amount)
    except (TypeError, ValueError):
        delta = 0.0
    weights[key] = max(0.0, float(weights.get(key, 0.0)) + delta)


def _normalized_weights(weights):
    cleaned = {}
    total = 0.0
    for skill_id, raw_value in dict(weights or {}).items():
        try:
            amount = max(0.0, float(raw_value))
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0.0:
            continue
        key = str(skill_id or "").strip().lower()
        if not key:
            continue
        cleaned[key] = amount
        total += amount
    if total <= 0.0:
        fallback = dict(ROLE_FIT_BASE_WEIGHTS["staff"])
        total = sum(float(value) for value in fallback.values())
        return {skill_id: float(value) / float(total) for skill_id, value in fallback.items()}
    return {skill_id: float(value) / float(total) for skill_id, value in cleaned.items()}


def _vehicle_sales_service(prop):
    for service in tuple(_site_services_for_property(prop) or ()):
        key = str(service or "").strip().lower()
        if key.startswith("vehicle_sales"):
            return True
    return False


def player_business_role_weights(prop, role):
    role = _normalized_role(role)
    weights = dict(ROLE_FIT_BASE_WEIGHTS.get(role, ROLE_FIT_BASE_WEIGHTS["staff"]))
    archetype = _property_archetype(prop)

    if _property_is_storefront(prop):
        _role_weight_bump(weights, "conversation", 0.06)
    if archetype in SOCIAL_ARCHETYPES:
        _role_weight_bump(weights, "conversation", 0.10 if role == "manager" else 0.08)
        _role_weight_bump(weights, "streetwise", 0.08 if role == "manager" else 0.05)
    if archetype in FINANCE_ARCHETYPES:
        _role_weight_bump(weights, "conversation", 0.08)
        _role_weight_bump(weights, "perception", 0.10)
        _role_weight_bump(weights, "intrusion", 0.04 if role == "staff" else 0.02)
    if archetype in CARE_ARCHETYPES:
        _role_weight_bump(weights, "perception", 0.10)
        _role_weight_bump(weights, "conversation", 0.05)
    if archetype in TECH_ARCHETYPES:
        _role_weight_bump(weights, "mechanics", 0.14 if role == "staff" else 0.08)
        _role_weight_bump(weights, "athletics", 0.07 if role == "staff" else 0.03)
    if archetype in SECURE_ARCHETYPES:
        _role_weight_bump(weights, "perception", 0.05)
        _role_weight_bump(weights, "intrusion", 0.05 if role == "staff" else 0.03)

    finance_services = tuple(_finance_services_for_property(prop) or ())
    if finance_services:
        _role_weight_bump(weights, "conversation", 0.08)
        _role_weight_bump(weights, "perception", 0.08)
    site_services = tuple(_site_services_for_property(prop) or ())
    if _vehicle_sales_service(prop):
        _role_weight_bump(weights, "mechanics", 0.14 if role == "staff" else 0.06)
    if any(str(service or "").strip().lower() in {"rest", "shelter"} for service in site_services):
        _role_weight_bump(weights, "conversation", 0.05)
    if any(str(service or "").strip().lower() in {"medical", "triage"} for service in site_services):
        _role_weight_bump(weights, "perception", 0.08)
    return _normalized_weights(weights)


def _fit_focus_skills(weights, limit=2):
    rows = sorted(
        ((str(skill_id), float(weight)) for skill_id, weight in dict(weights or {}).items() if float(weight) > 0.0),
        key=lambda row: (-row[1], row[0]),
    )
    return tuple(skill_id for skill_id, _weight in rows[: max(1, int(limit or 0))])


def _fit_label(score, *, filled=True):
    if not filled:
        return "unfilled"
    score = float(score)
    if score >= 8.2:
        return "excellent"
    if score >= 7.0:
        return "strong"
    if score >= 5.8:
        return "solid"
    if score >= 4.6:
        return "patchy"
    return "weak"


def player_business_role_fit(sim, actor_eid, prop, role):
    if sim is None or actor_eid is None or not isinstance(prop, dict):
        return None

    role = _normalized_role(role)
    weights = player_business_role_weights(prop, role)
    focus_skills = _fit_focus_skills(weights)

    skill_values = {}
    contributions = {}
    for skill_id, weight in weights.items():
        value = float(_actor_skill(sim, actor_eid, skill_id, default=5.0))
        skill_values[skill_id] = value
        contributions[skill_id] = float(value) * float(weight)

    score = float(sum(contributions.values()))
    strong_skills = tuple(
        skill_id
        for skill_id, _value in sorted(
            contributions.items(),
            key=lambda row: (-float(row[1]), -float(skill_values.get(row[0], 0.0)), row[0]),
        )[:2]
    ) or focus_skills

    weak_candidates = [
        (
            float(weights.get(skill_id, 0.0)) * max(0.0, 7.0 - float(skill_values.get(skill_id, 5.0))),
            skill_id,
        )
        for skill_id in weights.keys()
    ]
    weak_candidates.sort(key=lambda row: (-row[0], row[1]))
    weak_skills = tuple(skill_id for deficit, skill_id in weak_candidates[:2] if deficit > 0.0) or focus_skills

    return {
        "actor_eid": int(actor_eid),
        "role": role,
        "score": round(score, 2),
        "label": _fit_label(score, filled=True),
        "focus_skills": tuple(focus_skills),
        "strong_skills": tuple(strong_skills),
        "weak_skills": tuple(weak_skills),
        "skill_values": {skill_id: round(float(value), 2) for skill_id, value in skill_values.items()},
    }


def player_business_staffing_fit(sim, prop):
    state = player_business_state(prop, create=True)
    if state is None:
        return {}

    _sync_staff_roster(sim, prop, state)
    role_map = dict(state.get("staff_roles", {}))
    result = {}
    for role in ("manager", "staff"):
        weights = player_business_role_weights(prop, role)
        focus_skills = _fit_focus_skills(weights)
        actor_ids = sorted(
            _int_or(raw_eid, default=0)
            for raw_eid, raw_role in role_map.items()
            if _int_or(raw_eid, default=0) > 0 and _normalized_role(raw_role) == role
        )
        actor_ids = [actor_eid for actor_eid in actor_ids if actor_eid > 0]
        if not actor_ids:
            result[role] = {
                "role": role,
                "filled": False,
                "count": 0,
                "score": 0.0,
                "label": _fit_label(0.0, filled=False),
                "focus_skills": tuple(focus_skills),
                "strong_skills": tuple(focus_skills),
                "weak_skills": tuple(focus_skills),
                "actor_ids": (),
                "best_actor_eid": None,
            }
            continue

        fits = [player_business_role_fit(sim, actor_eid, prop, role) for actor_eid in actor_ids]
        fits = [entry for entry in fits if isinstance(entry, dict)]
        if not fits:
            continue

        average_score = sum(float(entry.get("score", 0.0)) for entry in fits) / float(len(fits))
        best_entry = max(
            fits,
            key=lambda entry: (float(entry.get("score", 0.0)), -int(entry.get("actor_eid", 0))),
        )

        average_skill_values = {}
        for skill_id in weights.keys():
            average_skill_values[skill_id] = sum(
                float((entry.get("skill_values") or {}).get(skill_id, 5.0))
                for entry in fits
            ) / float(len(fits))

        strong_skills = tuple(
            skill_id
            for skill_id, _value in sorted(
                average_skill_values.items(),
                key=lambda row: (
                    -(float(row[1]) * float(weights.get(row[0], 0.0))),
                    -float(row[1]),
                    row[0],
                ),
            )[:2]
        ) or focus_skills

        weak_candidates = [
            (
                float(weights.get(skill_id, 0.0)) * max(0.0, 7.0 - float(average_skill_values.get(skill_id, 5.0))),
                skill_id,
            )
            for skill_id in weights.keys()
        ]
        weak_candidates.sort(key=lambda row: (-row[0], row[1]))
        weak_skills = tuple(skill_id for deficit, skill_id in weak_candidates[:2] if deficit > 0.0) or focus_skills

        result[role] = {
            "role": role,
            "filled": True,
            "count": int(len(actor_ids)),
            "score": round(float(average_score), 2),
            "label": _fit_label(average_score, filled=True),
            "focus_skills": tuple(focus_skills),
            "strong_skills": tuple(strong_skills),
            "weak_skills": tuple(weak_skills),
            "actor_ids": tuple(int(actor_eid) for actor_eid in actor_ids),
            "best_actor_eid": int(best_entry.get("actor_eid")) if best_entry.get("actor_eid") is not None else None,
        }
    return result


def _service_reliability_label(value):
    reliability = float(value)
    if reliability >= 0.94:
        return "tight"
    if reliability >= 0.82:
        return "steady"
    if reliability >= 0.68:
        return "patchy"
    return "frayed"


def player_business_operating_quality(sim, prop, *, required_staff=None, staffing=None, role_fit=None):
    if sim is None or not isinstance(prop, dict):
        return {
            "weighted_quality": 0.0,
            "service_reliability": 0.0,
            "service_reliability_label": "frayed",
            "revenue_factor": 0.0,
            "slippage_rate": 0.0,
            "quality_note": "frayed ops",
        }

    required_staff = max(1, _int_or(required_staff, default=_required_staff_for(prop)))
    staffing = dict(staffing or {})
    role_fit = dict(role_fit or {})
    staff_total = max(0, _int_or(staffing.get("staff_total"), default=0))
    manager_count = max(0, _int_or(staffing.get("manager_count"), default=0))
    staff_count = max(0, _int_or(staffing.get("staff_count"), default=0))
    staffing_ratio = max(0.0, min(1.15, float(staff_total) / float(required_staff))) if required_staff > 0 else 0.0
    active_ratio = max(0.0, min(1.0, staffing_ratio))

    manager_target = 1 if required_staff > 0 else 0
    staff_target = max(0, required_staff - manager_target)

    manager_fit = role_fit.get("manager") if isinstance(role_fit.get("manager"), dict) else {}
    staff_fit = role_fit.get("staff") if isinstance(role_fit.get("staff"), dict) else {}
    manager_score = _clamp(manager_fit.get("score", 0.0), 0.0, 10.0) if manager_count > 0 else 0.0
    staff_score = _clamp(staff_fit.get("score", 0.0), 0.0, 10.0) if staff_count > 0 else 0.0

    manager_coverage = 1.0 if manager_target <= 0 else min(1.0, float(manager_count) / float(manager_target))
    staff_coverage = 1.0 if staff_target <= 0 else min(1.0, float(staff_count) / float(staff_target))

    manager_quality = 0.0 if manager_target > 0 and manager_count <= 0 else manager_coverage * (manager_score / 10.0)
    if staff_target <= 0:
        staff_quality = 1.0
    else:
        staff_quality = 0.0 if staff_count <= 0 else staff_coverage * (staff_score / 10.0)

    if staff_target > 0:
        weighted_quality = (manager_quality * 0.44) + (staff_quality * 0.56)
    else:
        weighted_quality = manager_quality
    weighted_quality = _clamp(weighted_quality, 0.0, 1.0) if staff_total > 0 else 0.0

    if staff_total <= 0:
        service_reliability = 0.0
        revenue_factor = 0.0
        slippage_rate = 0.0
    else:
        service_reliability = _clamp(0.18 + (0.32 * active_ratio) + (0.50 * weighted_quality), 0.0, 1.03)
        revenue_factor = _clamp(0.55 + (0.55 * weighted_quality) + (0.10 * active_ratio), 0.25, 1.15)
        slippage_rate = _clamp(
            0.01 + (max(0.0, 1.0 - weighted_quality) * 0.16) + (max(0.0, 1.0 - active_ratio) * 0.12),
            0.0,
            0.38,
        )

    quality_note = "steady ops"
    if staff_total <= 0:
        quality_note = "no crew"
    elif service_reliability < 0.68:
        quality_note = "frayed ops" if service_reliability < 0.45 else "patchy ops"
    elif service_reliability >= 0.94 and slippage_rate <= 0.04:
        quality_note = "tight crew"

    return {
        "weighted_quality": round(float(weighted_quality), 3),
        "service_reliability": round(float(service_reliability), 3),
        "service_reliability_label": _service_reliability_label(service_reliability),
        "revenue_factor": round(float(revenue_factor), 3),
        "slippage_rate": round(float(slippage_rate), 3),
        "quality_note": quality_note,
        "staffing_ratio": round(float(staffing_ratio), 3),
        "manager_target": int(manager_target),
        "staff_target": int(staff_target),
        "manager_fit_score": round(float(manager_score), 2),
        "staff_fit_score": round(float(staff_score), 2),
        "manager_fit_label": str(manager_fit.get("label", "unfilled")).strip().lower() or "unfilled",
        "staff_fit_label": str(staff_fit.get("label", "unfilled")).strip().lower() or "unfilled",
    }


def _economy_profile_for_property(sim, prop):
    cx, cy = sim.chunk_coords(_int_or(prop.get("x"), default=0), _int_or(prop.get("y"), default=0))
    chunk = sim.world.get_chunk(cx, cy)
    return dict(chunk_economy_profile(sim, chunk))


def _business_health(sim, prop):
    profile = _economy_profile_for_property(sim, prop)
    archetype = _property_archetype(prop)
    archetype_weight = float(workplace_archetype_weight(profile, archetype))
    stock_mult = float(profile.get("stock_mult", 1.0))
    price_mult = max(0.75, float(profile.get("price_mult", 1.0)))

    archetype_factor = max(0.62, min(1.32, 0.8 + ((archetype_weight - 1.0) * 0.28)))
    liquidity_factor = max(0.68, min(1.3, (stock_mult / price_mult) ** 0.5))
    demand_factor = max(0.72, min(1.28, ((stock_mult * 0.55) + ((2.0 - price_mult) * 0.45))))
    health = max(0.58, min(1.34, (archetype_factor * 0.4) + (liquidity_factor * 0.3) + (demand_factor * 0.3)))
    note = str(profile.get("pressure_note", "")).strip() or str(profile.get("store_note", "")).strip()
    return {
        "health": float(health),
        "note": note,
        "profile": profile,
    }


def _sync_staff_roster(sim, prop, state):
    roles = dict(state.get("staff_roles", {})) if isinstance(state.get("staff_roles"), dict) else {}
    owner_eid = prop.get("owner_eid")
    player_eid = getattr(sim, "player_eid", None)

    for member in property_org_members(sim, prop):
        actor_eid = _int_or(member.get("eid"), default=0)
        if actor_eid <= 0 or actor_eid == _int_or(player_eid, default=-1):
            continue
        role = str(member.get("role", "staff") or "staff").strip().lower()
        if role == "owner":
            role = "manager" if actor_eid != _int_or(owner_eid, default=-1) else "manager"
        if role not in {"manager", "staff"}:
            role = "staff"
        roles[str(actor_eid)] = role

    roster = sorted(
        _int_or(raw_eid, default=0)
        for raw_eid in roles.keys()
        if _int_or(raw_eid, default=0) > 0
    )
    state["staff_roles"] = roles
    state["staff_roster"] = roster

    manager_count = sum(1 for role in roles.values() if str(role).strip().lower() == "manager")
    staff_count = sum(1 for role in roles.values() if str(role).strip().lower() == "staff")
    return {
        "manager_count": int(manager_count),
        "staff_count": int(staff_count),
        "staff_total": int(manager_count + staff_count),
        "staff_roster": tuple(roster),
    }


def player_business_work_practice_awards(prop, role, *, limit=3):
    role = _normalized_role(role)
    total = float(ROLE_WORK_PRACTICE_TOTAL.get(role, ROLE_WORK_PRACTICE_TOTAL["staff"]))
    weights = player_business_role_weights(prop, role)
    ranked = sorted(
        (
            (str(skill_id).strip().lower(), float(weight))
            for skill_id, weight in dict(weights or {}).items()
            if float(weight) > 0.0
        ),
        key=lambda row: (-row[1], row[0]),
    )
    selected = ranked[: max(1, int(limit or 0))]
    if not selected or total <= 0.0:
        return {}

    selected_total = sum(float(weight) for _skill_id, weight in selected)
    if selected_total <= 0.0:
        return {}

    awards = {}
    for skill_id, weight in selected:
        awards[skill_id] = round(float(total) * (float(weight) / float(selected_total)), 3)
    return awards


def player_business_summary(sim, prop):
    state = player_business_state(prop, create=True)
    if state is None:
        return None

    state["required_staff"] = _required_staff_for(prop)
    staffing = _sync_staff_roster(sim, prop, state)
    role_fit = player_business_staffing_fit(sim, prop)
    market = _business_health(sim, prop)
    current_hour = _absolute_hour(sim)
    opening = _property_open_window(sim, prop)
    open_now = bool(_hour_in_window(current_hour % 24, opening)) if opening is not None else bool(_property_is_open(sim, prop))
    customer_policy = player_business_customer_policy(prop)
    hours_mode = player_business_hours_mode(prop)
    balance = int(state.get("account_balance", 0))
    required = int(state.get("required_staff", 1))
    staff_total = int(staffing.get("staff_total", 0))

    note = "steady"
    if staff_total <= 0:
        note = "no staff"
    elif staff_total < required:
        note = "understaffed"
    elif float(market.get("health", 1.0)) < 0.82:
        note = "soft market"
    elif float(market.get("health", 1.0)) > 1.12:
        note = "strong trade"
    last_summary = state.get("last_summary", {})
    if isinstance(last_summary, dict):
        if _int_or(last_summary.get("unpaid_wages"), default=0) > 0:
            note = "payroll short"
        elif note in {"steady", "strong trade", "soft market"}:
            quality_note = str(last_summary.get("operating_note", "")).strip()
            if quality_note in {"frayed ops", "patchy ops", "tight crew"}:
                note = quality_note
        if customer_policy == "closed" and note in {"steady", "strong trade", "soft market", "tight crew"}:
            note = "closed to customers"
        elif customer_policy == "staff_only" and note in {"steady", "strong trade", "soft market", "tight crew"}:
            note = "staff-only service"

    return {
        "property_id": prop.get("id"),
        "business_name": _text(_property_metadata(prop).get("business_name")) or _text(prop.get("name")) or "Business",
        "account_balance": balance,
        "required_staff": required,
        "staff_total": staff_total,
        "manager_count": int(staffing.get("manager_count", 0)),
        "staff_count": int(staffing.get("staff_count", 0)),
        "role_fit": role_fit,
        "open_now": bool(open_now),
        "opening_window": opening,
        "hours_text": _hours_text(opening),
        "hours_mode": hours_mode,
        "hours_mode_label": player_business_hours_mode_label(hours_mode),
        "customer_policy": customer_policy,
        "customer_policy_label": player_business_customer_policy_label(customer_policy),
        "health": float(market.get("health", 1.0)),
        "market_note": str(market.get("note", "")).strip(),
        "note": note,
    }


def player_business_status_snapshot(sim, prop):
    summary = player_business_summary(sim, prop)
    if not isinstance(summary, dict):
        return None
    state = player_business_state(prop, create=True)
    if state is None:
        return None
    last_summary = dict(state.get("last_summary", {})) if isinstance(state.get("last_summary"), dict) else {}
    open_roles = player_business_open_roles(sim, prop)
    open_role = open_roles[0] if open_roles else ""
    snapshot = dict(summary)
    snapshot.update({
        "role_fit": dict(summary.get("role_fit", {})) if isinstance(summary.get("role_fit"), dict) else {},
        "open_role": open_role,
        "open_roles": tuple(open_roles),
        "opening_window": _normalize_open_window(summary.get("opening_window")),
        "hours_text": str(summary.get("hours_text", "")).strip(),
        "hours_mode": str(summary.get("hours_mode", "")).strip(),
        "hours_mode_label": str(summary.get("hours_mode_label", "")).strip(),
        "customer_policy": str(summary.get("customer_policy", "")).strip(),
        "customer_policy_label": str(summary.get("customer_policy_label", "")).strip(),
        "last_summary": last_summary,
        "last_hour": None if not last_summary else _int_or(last_summary.get("hour"), default=0),
        "gross_revenue": _int_or(last_summary.get("gross_revenue"), default=0),
        "realized_revenue": _int_or(last_summary.get("realized_revenue"), default=_int_or(last_summary.get("gross_revenue"), default=0)),
        "slippage": _int_or(last_summary.get("slippage"), default=0),
        "slippage_rate": float(last_summary.get("slippage_rate", 0.0) or 0.0),
        "service_reliability": float(last_summary.get("service_reliability", 0.0) or 0.0),
        "service_reliability_label": str(last_summary.get("service_reliability_label", "")).strip(),
        "operating_note": str(last_summary.get("operating_note", "")).strip(),
        "wages_paid": _int_or(last_summary.get("wages_paid"), default=0),
        "wages_due": _int_or(last_summary.get("wages_due"), default=0),
        "upkeep_paid": _int_or(last_summary.get("upkeep_paid"), default=0),
        "upkeep_due": _int_or(last_summary.get("upkeep_due"), default=0),
        "unpaid_wages": _int_or(last_summary.get("unpaid_wages"), default=0),
        "unpaid_upkeep": _int_or(last_summary.get("unpaid_upkeep"), default=0),
    })
    return snapshot


def player_owned_business_for_actor(sim, eid, pos=None, radius=2):
    businesses = player_owned_businesses_for_actor(sim, eid, pos=pos)
    if not businesses:
        return None

    assets = sim.ecs.get(PlayerAssets).get(eid) if sim is not None else None
    if not assets:
        return None

    if pos is None:
        return businesses[0]

    current = _property_covering(sim, pos.x, pos.y, pos.z)
    if current and current.get("id") in assets.owned_property_ids and property_supports_player_business(current):
        return current

    max_radius = max(0, _int_or(radius, default=2))
    for prop in businesses:
        if _property_distance(pos.x, pos.y, prop) <= max_radius:
            return prop
    return None


def player_owned_businesses_for_actor(sim, eid, pos=None):
    assets = sim.ecs.get(PlayerAssets).get(eid) if sim is not None else None
    if not assets:
        return []

    if pos is None:
        pos = sim.ecs.get(Position).get(eid)

    current_id = ""
    if pos is not None:
        current = _property_covering(sim, pos.x, pos.y, pos.z)
        if current and current.get("id") in assets.owned_property_ids and property_supports_player_business(current):
            current_id = _text(current.get("id"))

    candidates = []
    seen = set()
    for property_id in sorted(getattr(assets, "owned_property_ids", ()) or ()):
        prop = sim.properties.get(property_id)
        if not property_supports_player_business(prop):
            continue
        prop_id = _text(prop.get("id", property_id))
        if not prop_id or prop_id in seen:
            continue
        seen.add(prop_id)
        distance = _property_distance(pos.x, pos.y, prop) if pos is not None else 999999
        business_name = _text(prop.get("metadata", {}).get("business_name", prop.get("name", prop_id))).lower()
        candidates.append((
            0 if prop_id == current_id else 1,
            int(distance),
            business_name,
            prop_id,
            prop,
        ))
    candidates.sort()
    return [row[-1] for row in candidates]


def _property_owned_by_actor(sim, actor_eid, prop):
    if sim is None or actor_eid is None or not isinstance(prop, dict):
        return False
    if int(prop.get("owner_eid") or 0) == int(actor_eid):
        return True
    assets = sim.ecs.get(PlayerAssets).get(actor_eid)
    return bool(assets and prop.get("id") in getattr(assets, "owned_property_ids", set()))


def _staffing_role_from_workplace(workplace, *, default="staff"):
    if not isinstance(workplace, dict):
        return str(default or "staff").strip().lower() or "staff"
    role = _text(workplace.get("authority_role", workplace.get("access_role", default))).lower()
    if role == "owner":
        role = "manager"
    if role not in {"manager", "staff"}:
        role = str(default or "staff").strip().lower() or "staff"
    return role


def actor_player_business_employment(sim, actor_eid, owner_eid=None):
    occupation = sim.ecs.get(Occupation).get(actor_eid) if sim is not None else None
    if not occupation:
        return None
    workplace = getattr(occupation, "workplace", None)
    if not isinstance(workplace, dict):
        return None
    property_id = _text(workplace.get("property_id"))
    prop = sim.properties.get(property_id) if property_id else None
    if not property_supports_player_business(prop):
        return None
    if owner_eid is not None and not _property_owned_by_actor(sim, owner_eid, prop):
        return None
    return {
        "actor_eid": int(actor_eid),
        "occupation": occupation,
        "prop": prop,
        "property_id": property_id,
        "role": _staffing_role_from_workplace(workplace),
    }


def player_business_open_roles(sim, prop):
    summary = player_business_summary(sim, prop)
    if not isinstance(summary, dict):
        return ()
    manager_count = max(0, _int_or(summary.get("manager_count"), default=0))
    staff_total = max(0, _int_or(summary.get("staff_total"), default=0))
    required_staff = max(1, _int_or(summary.get("required_staff"), default=1))
    open_roles = []
    if manager_count <= 0:
        open_roles.append("manager")
    if staff_total < required_staff:
        open_roles.append("staff")
    return tuple(open_roles)


def player_business_open_role(sim, prop):
    open_roles = player_business_open_roles(sim, prop)
    return open_roles[0] if open_roles else ""


def player_business_staffing_targets(sim, owner_eid):
    assets = sim.ecs.get(PlayerAssets).get(owner_eid) if sim is not None else None
    if not assets:
        return ()

    targets = []
    for property_id in sorted(getattr(assets, "owned_property_ids", ()) or ()):
        prop = sim.properties.get(property_id)
        if not property_supports_player_business(prop):
            continue
        summary = player_business_summary(sim, prop)
        if not isinstance(summary, dict):
            continue
        open_roles = player_business_open_roles(sim, prop)
        if not open_roles:
            continue
        open_role = open_roles[0]
        required_staff = max(1, _int_or(summary.get("required_staff"), default=1))
        staff_total = max(0, _int_or(summary.get("staff_total"), default=0))
        shortage = max(0, required_staff - staff_total)
        targets.append({
            "prop": prop,
            "property_id": _text(prop.get("id")),
            "business_name": str(summary.get("business_name", "")).strip() or _text(prop.get("name")) or "Business",
            "open_role": open_role,
            "open_roles": tuple(open_roles),
            "summary": summary,
            "required_staff": required_staff,
            "staff_total": staff_total,
            "shortage": shortage,
        })
    targets.sort(
        key=lambda row: (
            0 if row["open_role"] == "manager" else 1,
            -int(row["shortage"]),
            row["business_name"].lower(),
            row["property_id"],
        )
    )
    return tuple(targets)


def _business_shift_window(sim, prop):
    opening = _property_open_window(sim, prop)
    if isinstance(opening, (list, tuple)) and len(opening) >= 2:
        return int(opening[0]) % 24, int(opening[1]) % 24
    return 9, 17


def _hire_career_for(sim, actor_eid, prop, role, current_occupation=None):
    current_career = _text(getattr(current_occupation, "career", "")).lower()
    if current_career and current_career not in GENERIC_JOBLESS_CAREERS:
        if role == "manager" and "manager" not in current_career and "supervisor" not in current_career:
            return "manager"
        return current_career

    if role == "manager":
        archetype = _property_archetype(prop)
        if archetype in {"hotel", "nightclub", "music_venue", "gaming_hall"}:
            return "floor_manager"
        if archetype in {"bank", "brokerage"}:
            return "branch_manager"
        return "shop_manager"

    rng = random.Random(f"{getattr(sim, 'seed', 0)}:player-business-hire:{actor_eid}:{_text(prop.get('id'))}:{role}")
    profile = _economy_profile_for_property(sim, prop)
    choice = pick_career_for_workplace(
        getattr(sim, "world", None),
        rng,
        archetype=_property_archetype(prop),
        economy_profile=profile,
    ) if getattr(sim, "world", None) is not None else ""
    clean = _text(choice).lower().replace(" ", "_")
    if clean:
        return clean
    return "clerk"


def _workplace_for_hire(sim, prop, role):
    metadata = _property_metadata(prop)
    organization_eid = ensure_property_organization(sim, prop)
    workplace = {
        "property_id": prop.get("id"),
        "building_id": metadata.get("building_id"),
        "archetype": _property_archetype(prop),
        "authority_role": "manager" if str(role or "").strip().lower() == "manager" else "staff",
    }
    if organization_eid is not None:
        workplace["organization_eid"] = int(organization_eid)
    return workplace


def _ensure_work_routine(sim, actor_eid, prop):
    routine = sim.ecs.get(NPCRoutine).get(actor_eid)
    focus = _property_focus_position(prop)
    position = sim.ecs.get(Position).get(actor_eid)
    if routine is None:
        home = None
        if position is not None:
            home = (int(position.x), int(position.y), int(position.z))
        routine = NPCRoutine(home=home, work=focus)
        sim.ecs.add(actor_eid, routine)
        return routine

    if routine.home is None and position is not None:
        routine.home = (int(position.x), int(position.y), int(position.z))
    routine.work = focus
    return routine


def hire_actor_into_player_business(sim, owner_eid, actor_eid, prop, *, role=""):
    if sim is None or owner_eid is None or actor_eid is None:
        return None
    if int(actor_eid) == int(owner_eid):
        return None
    if not property_supports_player_business(prop) or not _property_owned_by_actor(sim, owner_eid, prop):
        return None

    current = actor_player_business_employment(sim, actor_eid)
    if current and _text(current.get("property_id")) != _text(prop.get("id")):
        return None

    occupation = sim.ecs.get(Occupation).get(actor_eid)
    if occupation and isinstance(getattr(occupation, "workplace", None), dict):
        property_id = _text(getattr(occupation, "workplace", {}).get("property_id"))
        if property_id and property_id != _text(prop.get("id")):
            return None

    open_roles = player_business_open_roles(sim, prop)
    role = str(role or (open_roles[0] if open_roles else "") or "staff").strip().lower()
    if role not in {"manager", "staff"}:
        role = "staff"
    if open_roles and role not in open_roles:
        return None

    if occupation is None:
        occupation = Occupation(career="unemployed", workplace=None, shift_start=None, shift_end=None)
        sim.ecs.add(actor_eid, occupation)

    housing_plan = player_business_housing_plan(sim, owner_eid, actor_eid, prop)
    workplace = _workplace_for_hire(sim, prop, role)
    shift_start, shift_end = _business_shift_window(sim, prop)
    occupation.workplace = workplace
    occupation.shift_start = shift_start
    occupation.shift_end = shift_end
    occupation.career = _hire_career_for(sim, actor_eid, prop, role, current_occupation=occupation)

    routine = _ensure_work_routine(sim, actor_eid, prop)
    if routine is not None and isinstance(housing_plan, dict):
        anchor = _anchor_tuple(housing_plan.get("anchor"))
        if anchor is not None:
            routine.home = anchor
    ai = sim.ecs.get(AI).get(actor_eid)
    if ai and str(ai.role or "").strip().lower() in {"", "civilian", "drunk", "local", "worker"}:
        ai.role = "worker"

    sync_actor_organization_affiliations(sim, actor_eid, occupation=occupation)

    state = player_business_state(prop, create=True)
    if state is not None:
        roles = dict(state.get("staff_roles", {}))
        roles[str(int(actor_eid))] = role
        roster = {int(raw_eid) for raw_eid in list(state.get("staff_roster", ()) or ()) if _int_or(raw_eid, default=0) > 0}
        roster.add(int(actor_eid))
        state["staff_roles"] = roles
        state["staff_roster"] = sorted(roster)
        _sync_staff_roster(sim, prop, state)

    return {
        "actor_eid": int(actor_eid),
        "property_id": _text(prop.get("id")),
        "business_name": _text(_property_metadata(prop).get("business_name")) or _text(prop.get("name")) or "Business",
        "role": role,
        "career": _text(getattr(occupation, "career", "")).lower(),
        "housing_kind": str((housing_plan or {}).get("kind", "")).strip().lower(),
        "housing_local": bool((housing_plan or {}).get("local", False)),
        "housing_relocated": bool((housing_plan or {}).get("relocated", False)),
        "housing_property_id": _text(((housing_plan or {}).get("prop") or {}).get("id")),
        "housing_name": str((housing_plan or {}).get("label", "")).strip(),
    }


def fire_actor_from_player_business(sim, owner_eid, actor_eid, prop=None):
    employment = actor_player_business_employment(sim, actor_eid, owner_eid=owner_eid)
    if not employment:
        return None

    employed_prop = employment.get("prop")
    if isinstance(prop, dict) and _text(prop.get("id")) and _text(prop.get("id")) != _text(employed_prop.get("id")):
        return None

    occupation = employment.get("occupation")
    if occupation:
        occupation.workplace = None
        occupation.shift_start = None
        occupation.shift_end = None
        occupation.career = "unemployed"

    routine = sim.ecs.get(NPCRoutine).get(actor_eid)
    if routine:
        routine.work = None

    ai = sim.ecs.get(AI).get(actor_eid)
    if ai and str(ai.role or "").strip().lower() == "worker":
        ai.role = "civilian"

    component = sim.ecs.get(OrganizationAffiliations).get(actor_eid)
    organization_eid = property_organization_eid(sim, employed_prop, ensure=False)
    if component and organization_eid is not None:
        membership = component.memberships.get(int(organization_eid))
        if isinstance(membership, dict):
            membership["active"] = False
            membership["site_property_id"] = None
            membership["site_building_id"] = None
        else:
            component.memberships.pop(int(organization_eid), None)

    state = player_business_state(employed_prop, create=True)
    if state is not None:
        roles = dict(state.get("staff_roles", {}))
        roles.pop(str(int(actor_eid)), None)
        state["staff_roles"] = roles
        state["staff_roster"] = [
            int(raw_eid)
            for raw_eid in list(state.get("staff_roster", ()) or ())
            if _int_or(raw_eid, default=0) > 0 and int(_int_or(raw_eid, default=0)) != int(actor_eid)
        ]
        _sync_staff_roster(sim, employed_prop, state)

    return {
        "actor_eid": int(actor_eid),
        "property_id": _text(employed_prop.get("id")),
        "business_name": _text(_property_metadata(employed_prop).get("business_name")) or _text(employed_prop.get("name")) or "Business",
        "role": str(employment.get("role", "staff") or "staff").strip().lower() or "staff",
    }


class PlayerBusinessSystem(System):
    """Runs hourly operating cycles for player-owned businesses."""

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.sim.events.subscribe("property_owner_changed", self.on_property_owner_changed)

    def _assets(self):
        return self.sim.ecs.get(PlayerAssets).get(self.player_eid)

    def _ensure_business_account(self, prop, *, announce=False):
        if not property_supports_player_business(prop):
            return None
        state = player_business_state(prop, create=True)
        if state is None:
            return None
        if _normalize_open_window(state.get("baseline_hours")) is None:
            baseline = _normalize_open_window(_property_open_window(self.sim, prop))
            state["baseline_hours"] = list(baseline) if baseline is not None else None
        player_business_set_hours_mode(self.sim, prop, state.get("hours_mode"))
        state["required_staff"] = _required_staff_for(prop)
        if state.get("last_cycle_hour") is None:
            state["last_cycle_hour"] = _absolute_hour(self.sim)
        staffing = _sync_staff_roster(self.sim, prop, state)
        if announce:
            self.sim.emit(Event(
                "player_business_acquired",
                eid=self.player_eid,
                property_id=prop.get("id"),
                business_name=_text(_property_metadata(prop).get("business_name")) or _text(prop.get("name")) or "Business",
                account_balance=int(state.get("account_balance", 0)),
                staff_total=int(staffing.get("staff_total", 0)),
                required_staff=int(state.get("required_staff", 1)),
            ))
        return state

    def on_property_owner_changed(self, event):
        if event.data.get("new_owner_eid") != self.player_eid:
            return
        prop = self.sim.properties.get(event.data.get("property_id"))
        if not isinstance(prop, dict):
            return
        self._ensure_business_account(prop, announce=True)

    def _base_revenue_for(self, prop):
        archetype = _property_archetype(prop)
        base = int(BUSINESS_BASE_REVENUE.get(archetype, 8))
        if _property_is_storefront(prop):
            base += 2
        base += len(tuple(_finance_services_for_property(prop))) * 2
        base += len(tuple(_site_services_for_property(prop))) * 2
        if _text(_property_metadata(prop).get("business_name")):
            base += 1
        return max(6, min(18, base))

    def _emit_work_practice(self, prop, state, hour_counter):
        roles = dict(state.get("staff_roles", {})) if isinstance(state.get("staff_roles"), dict) else {}
        if not roles:
            return

        property_id = _text(prop.get("id"))
        for raw_eid, raw_role in roles.items():
            actor_eid = _int_or(raw_eid, default=0)
            if actor_eid <= 0 or actor_eid == _int_or(self.player_eid, default=-1):
                continue
            role = _normalized_role(raw_role)
            awards = player_business_work_practice_awards(prop, role)
            for skill_id, amount in awards.items():
                if float(amount) <= 0.0:
                    continue
                self.sim.emit(Event(
                    "skill_practice",
                    eid=int(actor_eid),
                    skill_id=str(skill_id),
                    amount=float(amount),
                    source="player_business_work",
                    cooldown_key=f"{property_id}:{int(hour_counter)}:{role}:{skill_id}",
                    cooldown=0,
                ))

    def _process_business_hour(self, prop, state, hour_counter):
        state["required_staff"] = _required_staff_for(prop)
        staffing = _sync_staff_roster(self.sim, prop, state)
        required_staff = int(state.get("required_staff", 1))
        staff_total = int(staffing.get("staff_total", 0))
        manager_count = int(staffing.get("manager_count", 0))
        staff_count = int(staffing.get("staff_count", 0))
        customer_policy = player_business_customer_policy(prop)
        hours_mode = player_business_hours_mode(prop)
        role_fit = player_business_staffing_fit(self.sim, prop)
        operating = player_business_operating_quality(
            self.sim,
            prop,
            required_staff=required_staff,
            staffing=staffing,
            role_fit=role_fit,
        )
        health = _business_health(self.sim, prop)
        opening = _property_open_window(self.sim, prop)
        open_now = bool(_hour_in_window(hour_counter % 24, opening))
        staffing_ratio = max(0.0, min(1.15, (float(staff_total) / float(required_staff)))) if required_staff > 0 else 0.0
        policy_revenue_factor = 1.0
        policy_slippage_factor = 1.0
        policy_note = ""
        if customer_policy == "staff_only":
            policy_revenue_factor = 0.38
            policy_slippage_factor = 0.7
            policy_note = "staff-only service"
        elif customer_policy == "closed":
            policy_revenue_factor = 0.0
            policy_slippage_factor = 0.0
            policy_note = "closed to customers"

        gross_revenue = 0
        realized_revenue = 0
        slippage = 0
        if open_now and staff_total > 0:
            revenue_factor = (
                (0.32 + (0.68 * min(1.0, staffing_ratio)))
                * float(operating.get("revenue_factor", 1.0))
                * float(health.get("health", 1.0))
                * float(policy_revenue_factor)
            )
            gross_revenue = max(1, int(round(float(self._base_revenue_for(prop)) * revenue_factor)))
            if policy_revenue_factor <= 0.0:
                gross_revenue = 0
            slippage = int(round(float(gross_revenue) * float(operating.get("slippage_rate", 0.0)) * float(policy_slippage_factor)))
            if gross_revenue > 0:
                ceiling = gross_revenue - 1 if gross_revenue > 1 else gross_revenue
                slippage = max(0, min(ceiling, slippage))
            realized_revenue = max(0, gross_revenue - slippage)
            self._emit_work_practice(prop, state, hour_counter)

        wages_due = 0
        if open_now:
            wages_due += manager_count * int(ROLE_WAGES["manager"])
            wages_due += staff_count * int(ROLE_WAGES["staff"])
        upkeep_due = 1 + min(2, len(tuple(_finance_services_for_property(prop))) + len(tuple(_site_services_for_property(prop))))

        available = int(state.get("account_balance", 0)) + int(realized_revenue)
        wages_paid = min(available, wages_due)
        available -= wages_paid
        upkeep_paid = min(available, upkeep_due)
        available -= upkeep_paid

        unpaid_wages = max(0, wages_due - wages_paid)
        unpaid_upkeep = max(0, upkeep_due - upkeep_paid)
        state["account_balance"] = max(0, int(available))
        state["last_cycle_hour"] = int(hour_counter + 1)

        note = "steady"
        if unpaid_wages > 0:
            note = "payroll short"
        elif staff_total <= 0:
            note = "no staff"
        elif staff_total < required_staff:
            note = "understaffed"
        elif policy_note:
            note = policy_note
        elif float(operating.get("service_reliability", 1.0)) < 0.68:
            note = str(operating.get("quality_note", "patchy ops")).strip() or "patchy ops"
        elif str(operating.get("quality_note", "")).strip() == "tight crew":
            note = "tight crew"
        elif float(health.get("health", 1.0)) > 1.1:
            note = "strong trade"
        elif float(health.get("health", 1.0)) < 0.82:
            note = "soft market"

        state["last_summary"] = {
            "hour": int(hour_counter % 24),
            "open_now": bool(open_now),
            "gross_revenue": int(gross_revenue),
            "realized_revenue": int(realized_revenue),
            "slippage": int(slippage),
            "slippage_rate": float(operating.get("slippage_rate", 0.0)),
            "service_reliability": float(operating.get("service_reliability", 0.0)),
            "service_reliability_label": str(operating.get("service_reliability_label", "")).strip(),
            "operating_note": str(operating.get("quality_note", "")).strip(),
            "policy_note": policy_note,
            "wages_due": int(wages_due),
            "wages_paid": int(wages_paid),
            "upkeep_due": int(upkeep_due),
            "upkeep_paid": int(upkeep_paid),
            "unpaid_wages": int(unpaid_wages),
            "unpaid_upkeep": int(unpaid_upkeep),
            "customer_policy": customer_policy,
            "customer_policy_label": player_business_customer_policy_label(customer_policy),
            "hours_mode": hours_mode,
            "hours_mode_label": player_business_hours_mode_label(hours_mode),
            "opening_window": list(opening) if opening is not None else None,
            "hours_text": _hours_text(opening),
            "required_staff": int(required_staff),
            "staff_total": int(staff_total),
            "manager_count": int(manager_count),
            "staff_count": int(staff_count),
            "manager_fit_score": float(operating.get("manager_fit_score", 0.0)),
            "staff_fit_score": float(operating.get("staff_fit_score", 0.0)),
            "manager_fit_label": str(operating.get("manager_fit_label", "")).strip(),
            "staff_fit_label": str(operating.get("staff_fit_label", "")).strip(),
            "health": float(health.get("health", 1.0)),
            "market_note": str(health.get("note", "")).strip(),
            "account_balance": int(state.get("account_balance", 0)),
            "note": note,
        }

    def update(self):
        assets = self._assets()
        if not assets:
            return

        hour_counter = _absolute_hour(self.sim)
        for property_id in sorted(getattr(assets, "owned_property_ids", ()) or ()):
            prop = self.sim.properties.get(property_id)
            if not property_supports_player_business(prop):
                continue

            state = self._ensure_business_account(prop, announce=False)
            if state is None:
                continue

            last_cycle_hour = state.get("last_cycle_hour")
            if last_cycle_hour is None:
                state["last_cycle_hour"] = int(hour_counter)
                continue

            while int(state.get("last_cycle_hour", hour_counter)) < int(hour_counter):
                self._process_business_hour(
                    prop,
                    state,
                    int(state.get("last_cycle_hour", hour_counter)),
                )


__all__ = [
    "PlayerBusinessSystem",
    "actor_player_business_employment",
    "fire_actor_from_player_business",
    "hire_actor_into_player_business",
    "player_business_open_roles",
    "player_business_account_balance",
    "player_business_customer_policy",
    "player_business_customer_policy_label",
    "player_business_housing_plan",
    "player_business_hours_mode",
    "player_business_hours_mode_label",
    "player_business_hours_window",
    "player_business_next_customer_policy",
    "player_business_next_hours_mode",
    "player_business_open_role",
    "player_business_role_fit",
    "player_business_role_weights",
    "player_business_set_customer_policy",
    "player_business_set_hours_mode",
    "player_business_operating_quality",
    "player_business_state",
    "player_business_staffing_fit",
    "player_business_staffing_targets",
    "player_business_status_snapshot",
    "player_business_summary",
    "player_business_work_practice_awards",
    "player_owned_businesses_for_actor",
    "player_owned_business_for_actor",
    "property_supports_player_business",
]
