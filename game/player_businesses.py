"""Player-owned business account and operating runtime.

This module adds a thin economics spine for player-owned businesses:

- eligible owned businesses get a dedicated account
- incumbent staff are retained into a simple roster
- businesses run one hourly operating cycle at a time
- revenue and payroll depend on staffing plus local economy health
"""

from __future__ import annotations

import random

from engine.world import World
from engine.events import Event
from engine.systems import System
from game.components import AI, NPCSocial, NPCRoutine, NPCWill, Occupation, OrganizationAffiliations, PlayerAssets, Position
from game.dialogue_runtime import _queue_npc_initiated_dialogue
from game.economy import chunk_economy_profile, pick_career_for_workplace, workplace_archetype_weight
from game.organizations import (
    ensure_property_organization,
    property_org_members,
    property_organization_eid,
    sync_actor_organization_affiliations,
)
from game.property_access import (
    FINANCE_SERVICE_FALLBACKS as _FINANCE_SERVICE_FALLBACKS,
    default_site_services_for_archetype as _default_site_services_for_archetype,
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
    resolve_property_record as _resolve_property_record,
)
from game.skills import actor_skill as _actor_skill
from game.system_support.ai_intent_runtime import _sync_ai_intent
from game.system_support.actor_attention_runtime import record_actor_social_warmth as _record_actor_social_warmth
from game.system_support.business_event_state import _business_event_actor_note
from game.system_support.interaction_ordering import _manhattan
from game.systems_business_reputation import business_opinion_profile, property_business_reputation_snapshot


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
BUSINESS_BOND_RANK = {
    "family": 6,
    "partner": 5,
    "friend": 4,
    "owner": 3,
    "workplace": 3,
    "job_issuer": 3,
    "coworker": 2,
    "neighbor": 1,
    "local": 1,
    "contact": 1,
}
BUSINESS_COWORKER_BASELINES = {
    "manager": {"closeness": 0.52, "trust": 0.62, "protectiveness": 0.58},
    "staff": {"closeness": 0.48, "trust": 0.58, "protectiveness": 0.54},
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
    "contractor_office": 10,
    "corner_store": 9,
    "hotel": 12,
    "nightclub": 11,
    "restaurant": 10,
    "music_venue": 11,
    "gaming_hall": 11,
    "backroom_clinic": 10,
    "pharmacy": 10,
    "auto_garage": 10,
    "outfitter": 10,
    "pawn_shop": 10,
    "service_station": 10,
    "surplus_store": 10,
    "thrift_store": 9,
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
BUSINESS_MARKUP_MODE_ORDER = ("discount", "standard", "premium", "steep")
BUSINESS_MARKUP_MODE_LABELS = {
    "discount": "discount board",
    "standard": "standard pricing",
    "premium": "premium pricing",
    "steep": "high markup",
}
BUSINESS_MARKUP_MODE_PROFILES = {
    "discount": {
        "buy_mult": 0.88,
        "revenue_mult": 0.94,
        "note": "leans on foot traffic and softer shelf pricing",
    },
    "standard": {
        "buy_mult": 1.0,
        "revenue_mult": 1.0,
        "note": "keeps the usual storefront balance",
    },
    "premium": {
        "buy_mult": 1.14,
        "revenue_mult": 1.08,
        "note": "presses margin a little harder on each sale",
    },
    "steep": {
        "buy_mult": 1.28,
        "revenue_mult": 1.12,
        "note": "leans on high margin and thinner demand tolerance",
    },
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
    "thrift_store",
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
    "contractor_office",
    "factory",
    "freight_depot",
    "service_station",
    "tool_depot",
    "warehouse",
}
SECURE_ARCHETYPES = {
    "bank",
    "brokerage",
    "cold_storage",
    "pawn_shop",
    "surplus_store",
    "warehouse",
}
BUSINESS_REMODEL_ELIGIBLE_ARCHETYPES = tuple(sorted(getattr(World, "STOREFRONT_ARCHETYPES", ()) or ()))


def _text(value):
    return str(value or "").strip()


def _int_or(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _player_business_runtime_cache(sim):
    if sim is None:
        return None
    current_tick = _int_or(getattr(sim, "tick", 0), default=0)
    state = getattr(sim, "_player_business_runtime_cache", None)
    if not isinstance(state, dict) or _int_or(state.get("tick"), default=-1) != current_tick:
        state = {
            "tick": current_tick,
            "summary": {},
            "status": {},
            "open_roles": {},
        }
        sim._player_business_runtime_cache = state
    else:
        state.setdefault("summary", {})
        state.setdefault("status", {})
        state.setdefault("open_roles", {})
    return state


def _player_business_cache_key(prop):
    if not isinstance(prop, dict):
        return ""
    property_id = _text(prop.get("id"))
    state = player_business_state(prop, create=False)
    revision = _int_or((state or {}).get("_cache_revision"), default=0)
    if property_id:
        return f"{property_id}:rev:{revision}"
    return f"prop-object:{id(prop)}:rev:{revision}"


def _touch_player_business_runtime(prop, *, sim=None):
    state = player_business_state(prop, create=True)
    if state is None:
        return False
    state["_cache_revision"] = max(0, _int_or(state.get("_cache_revision"), default=0)) + 1
    _invalidate_player_business_runtime_cache(sim, prop)
    return True


def refresh_player_business_runtime(sim, prop):
    return _touch_player_business_runtime(prop, sim=sim)


def _invalidate_player_business_runtime_cache(sim, prop=None):
    if sim is None:
        return False
    state = getattr(sim, "_player_business_runtime_cache", None)
    if not isinstance(state, dict):
        return False
    if prop is None:
        sim._player_business_runtime_cache = {
            "tick": _int_or(getattr(sim, "tick", 0), default=0),
            "summary": {},
            "status": {},
            "open_roles": {},
        }
        return True
    cache_key = _player_business_cache_key(prop)
    if not cache_key:
        return False
    changed = False
    for bucket_name in ("summary", "status", "open_roles"):
        bucket = state.get(bucket_name)
        if isinstance(bucket, dict) and cache_key in bucket:
            bucket.pop(cache_key, None)
            changed = True
    return changed


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


def _normalize_business_markup_mode(value):
    clean = _text(value).lower().replace("-", "_").replace(" ", "_")
    if clean in {"low", "low_markup", "discounted"}:
        clean = "discount"
    elif clean in {"base", "default"}:
        clean = "standard"
    elif clean in {"high", "high_markup"}:
        clean = "premium"
    if clean not in BUSINESS_MARKUP_MODE_ORDER:
        return "standard"
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


def _archetype_title(archetype):
    clean = _text(archetype).lower()
    return clean.replace("_", " ").strip().title() or "Business"


def _property_metadata(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _player_business_warning_issue(summary):
    if not isinstance(summary, dict):
        return ""
    awareness = max(
        0,
        _int_or(
            summary.get("reputation_awareness", summary.get("awareness_count", 0)),
            default=0,
        ),
    )
    if awareness < 2:
        return ""
    reputation_note = _text(summary.get("reputation_note")).lower()
    community_signal_note = _text(summary.get("community_signal_note")).lower()
    community_note = _text(summary.get("community_note")).lower()
    if reputation_note == "price grumbling":
        return "gouging"
    if reputation_note == "front trouble":
        return "front_trouble"
    if community_signal_note == "making the block tense":
        return "block_tense"
    if community_signal_note == "souring the block":
        return "block_sour"
    if community_note == "tenser block":
        return "block_tense"
    return ""


def _player_business_warning_signature(summary):
    issue = _player_business_warning_issue(summary)
    if not issue:
        return ""
    note = (
        _text(summary.get("reputation_note"))
        or _text(summary.get("community_signal_note"))
        or _text(summary.get("community_note"))
    ).lower()
    return f"{issue}:{note}" if note else issue


def _player_business_warning_transition(last_summary, current_summary):
    current_signature = _player_business_warning_signature(current_summary)
    if not current_signature:
        return ""
    if _player_business_warning_signature(last_summary) == current_signature:
        return ""
    return current_signature


def _player_business_warning_history(state):
    if not isinstance(state, dict):
        return {}
    history = state.get("owner_warning_history")
    if isinstance(history, dict):
        return history
    history = {}
    state["owner_warning_history"] = history
    return history


def _player_business_pending_warning(state):
    if not isinstance(state, dict):
        return {}
    pending = state.get("pending_owner_warning")
    return pending if isinstance(pending, dict) else {}


def _player_business_chunk(sim, prop):
    if sim is None or not isinstance(prop, dict):
        return None
    try:
        return tuple(int(bit) for bit in sim.chunk_coords(int(prop.get("x", 0) or 0), int(prop.get("y", 0) or 0)))
    except (TypeError, ValueError):
        return None


def _resolve_owned_property(sim, property_id):
    return _resolve_property_record(sim, _text(property_id))


def _player_business_warning_actor_role(sim, eid, prop):
    property_id = _text((prop or {}).get("id"))
    note = _business_event_actor_note(sim, eid)
    if isinstance(note, dict) and _text(note.get("property_id")) == property_id:
        career = _text(note.get("career")).lower()
        if career == "block_regular":
            return "regular"
    occupation = sim.ecs.get(Occupation).get(eid) if sim is not None else None
    workplace = getattr(occupation, "workplace", None) if occupation else None
    if isinstance(workplace, dict) and _text(workplace.get("property_id")) == property_id:
        return "staff"
    return "local"


def _player_business_warning_issue_score(opinion, issue_kind):
    if not isinstance(opinion, dict):
        return 0.0
    price_pain = max(0.0, -float(opinion.get("price_fairness", 0.0) or 0.0))
    trust_gap = max(0.0, 0.45 - float(opinion.get("trust", 0.0) or 0.0))
    reliability_gap = max(0.0, 0.45 - float(opinion.get("reliability", 0.0) or 0.0))
    familiarity = max(0.0, float(opinion.get("familiarity", 0.0) or 0.0))
    coherence = max(0.0, float(opinion.get("coherence", 0.0) or 0.0))
    resentment = max(0.0, float(opinion.get("resentment", 0.0) or 0.0))
    fear = max(0.0, float(opinion.get("fear", 0.0) or 0.0))
    heat = max(0.0, float(opinion.get("heat", 0.0) or 0.0))
    incident_pressure = max(0.0, float(opinion.get("incident_pressure", 0.0) or 0.0))
    if max(familiarity, coherence) < 0.12:
        return 0.0
    if issue_kind == "gouging":
        return (price_pain * 0.58) + (resentment * 0.28) + (familiarity * 0.14)
    if issue_kind == "front_trouble":
        return (trust_gap * 0.22) + (reliability_gap * 0.18) + (resentment * 0.18) + (heat * 0.18) + (fear * 0.1) + (incident_pressure * 0.14)
    if issue_kind == "block_tense":
        return (heat * 0.34) + (fear * 0.18) + (incident_pressure * 0.22) + (resentment * 0.12) + (familiarity * 0.14)
    if issue_kind == "block_sour":
        return (resentment * 0.34) + (price_pain * 0.18) + (trust_gap * 0.16) + (reliability_gap * 0.16) + (familiarity * 0.16)
    return 0.0


def _player_business_warning_prompt(prop, issue_kind, opinion, summary, *, speaker_role="local"):
    business_name = _text(_property_metadata(prop).get("business_name")) or _text((prop or {}).get("name")) or "this place"
    price_pain = max(0.0, -float((opinion or {}).get("price_fairness", 0.0) or 0.0))
    resentment = max(0.0, float((opinion or {}).get("resentment", 0.0) or 0.0))
    heat = max(0.0, float((opinion or {}).get("heat", 0.0) or 0.0))
    incident_pressure = max(0.0, float((opinion or {}).get("incident_pressure", 0.0) or 0.0))
    trust_gap = max(0.0, 0.45 - float((opinion or {}).get("trust", 0.0) or 0.0))
    if issue_kind == "gouging":
        if price_pain >= 0.34 or resentment >= 0.32:
            return (
                f"You own {business_name}, right? People on this block think the prices there are starting to bite.",
                "If you keep pressing it that hard, the neighborhood is going to turn on the place.",
            )
        return (
            f"People around here are starting to grumble that {business_name} is getting expensive.",
            "You might want to soften that before the place turns sour.",
        )
    if issue_kind == "block_tense":
        return (
            f"{business_name} is putting this stretch on edge.",
            "Folks notice when a place starts making the block feel tense.",
        )
    if issue_kind == "block_sour":
        return (
            f"People around here are souring on {business_name}.",
            "The way it feels lately is getting under the neighborhood's skin.",
        )
    if speaker_role == "staff" and (trust_gap >= 0.24 or heat >= 0.24 or incident_pressure >= 0.18):
        return (
            f"The floor at {business_name} is starting to feel hot, and people are reading it that way.",
            "If you let it keep sliding, this place is going to lose the room.",
        )
    return (
        f"People around here are starting to lose trust in {business_name}.",
        "You should get ahead of it before the trouble becomes the whole story.",
    )


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
    state["markup_mode"] = _normalize_business_markup_mode(state.get("markup_mode"))
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
    state["last_scene_nuisance_note"] = str(state.get("last_scene_nuisance_note", "") or "").strip()
    state["last_scene_nuisance_loss"] = max(0, _int_or(state.get("last_scene_nuisance_loss"), default=0))
    raw_nuisance_tick = state.get("last_scene_nuisance_tick")
    state["last_scene_nuisance_tick"] = None if raw_nuisance_tick in {None, ""} else _int_or(raw_nuisance_tick, default=0)
    state["_cache_revision"] = max(0, _int_or(state.get("_cache_revision"), default=0))
    return state


def player_business_account_balance(prop):
    state = player_business_state(prop, create=False)
    return int(state.get("account_balance", 0)) if state else 0


def player_business_customer_policy(prop):
    if _property_supports_lodging_service(prop):
        return "public"
    state = player_business_state(prop, create=False)
    return _normalize_customer_policy(state.get("customer_policy")) if state else "public"


def player_business_customer_policy_label(policy):
    clean = _normalize_customer_policy(policy)
    return CUSTOMER_POLICY_LABELS.get(clean, "public")


def player_business_next_customer_policy(prop):
    return _cycle_choice(player_business_customer_policy(prop), CUSTOMER_POLICY_ORDER)


def player_business_set_customer_policy(prop, policy, *, sim=None):
    state = player_business_state(prop, create=True)
    if state is None:
        return "public"
    clean = "public" if _property_supports_lodging_service(prop) else _normalize_customer_policy(policy)
    state["customer_policy"] = clean
    _touch_player_business_runtime(prop, sim=sim)
    return clean


def player_business_hours_mode(prop):
    if _property_supports_lodging_service(prop):
        return "always_open"
    state = player_business_state(prop, create=False)
    return _normalize_business_hours_mode(state.get("hours_mode")) if state else "normal"


def player_business_hours_mode_label(mode):
    clean = _normalize_business_hours_mode(mode)
    return BUSINESS_HOURS_MODE_LABELS.get(clean, "normal hours")


def player_business_markup_mode(prop):
    state = player_business_state(prop, create=False)
    return _normalize_business_markup_mode(state.get("markup_mode")) if state else "standard"


def player_business_markup_mode_label(mode):
    clean = _normalize_business_markup_mode(mode)
    return BUSINESS_MARKUP_MODE_LABELS.get(clean, "standard pricing")


def player_business_next_markup_mode(prop):
    return _cycle_choice(player_business_markup_mode(prop), BUSINESS_MARKUP_MODE_ORDER)


def player_business_markup_profile(prop_or_mode):
    if isinstance(prop_or_mode, dict):
        mode = player_business_markup_mode(prop_or_mode)
    else:
        mode = _normalize_business_markup_mode(prop_or_mode)
    profile = BUSINESS_MARKUP_MODE_PROFILES.get(mode, BUSINESS_MARKUP_MODE_PROFILES["standard"])
    return {
        "mode": mode,
        "label": player_business_markup_mode_label(mode),
        "buy_mult": float(profile.get("buy_mult", 1.0) or 1.0),
        "revenue_mult": float(profile.get("revenue_mult", 1.0) or 1.0),
        "note": str(profile.get("note", "")).strip(),
    }


def player_business_set_markup_mode(prop, mode, *, sim=None):
    state = player_business_state(prop, create=True)
    if state is None:
        return "standard"
    clean = _normalize_business_markup_mode(mode)
    state["markup_mode"] = clean
    _touch_player_business_runtime(prop, sim=sim)
    return clean


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

    clean = "always_open" if _property_supports_lodging_service(prop) else _normalize_business_hours_mode(mode)
    opening = player_business_hours_window(sim, prop, mode=clean)
    state["hours_mode"] = clean

    metadata = _property_metadata(prop)
    if opening is not None:
        metadata["access_controller_hours"] = [int(opening[0]) % 24, int(opening[1]) % 24]
    else:
        metadata.pop("access_controller_hours", None)
    _touch_player_business_runtime(prop, sim=sim)

    return {
        "hours_mode": clean,
        "opening_window": opening,
        "hours_text": _hours_text(opening),
    }


def _business_remodel_rarity_counts():
    counts = {}
    for district_rows in tuple(getattr(World, "CORE_BUILDINGS_BY_DISTRICT", {}).values()):
        for archetype in tuple(district_rows or ()):
            key = _text(archetype).lower()
            if key:
                counts[key] = counts.get(key, 0) + 1
    for district_rows in tuple(getattr(World, "OPTIONAL_BUILDINGS_BY_DISTRICT", {}).values()):
        for archetype in tuple(district_rows or ()):
            key = _text(archetype).lower()
            if key:
                counts[key] = counts.get(key, 0) + 1
    return counts


def player_business_remodel_quote(prop, target_archetype):
    if not isinstance(prop, dict):
        return None
    target = _text(target_archetype).lower()
    current = _property_archetype(prop)
    if not target or target == current or target not in BUSINESS_REMODEL_ELIGIBLE_ARCHETYPES:
        return None

    counts = _business_remodel_rarity_counts()
    eligible_counts = {
        archetype: max(1, int(counts.get(archetype, 1)))
        for archetype in BUSINESS_REMODEL_ELIGIBLE_ARCHETYPES
    }
    min_count = min(eligible_counts.values()) if eligible_counts else 1
    max_count = max(eligible_counts.values()) if eligible_counts else 1
    target_count = max(1, int(eligible_counts.get(target, 1)))
    if max_count <= min_count:
        rarity_rank = 0.0
    else:
        rarity_rank = float(max_count - target_count) / float(max_count - min_count)
    if rarity_rank >= 0.72:
        rarity_label = "rare"
    elif rarity_rank >= 0.35:
        rarity_label = "uncommon"
    else:
        rarity_label = "common"

    metadata = _property_metadata(prop)
    source_price = max(80, _int_or(metadata.get("purchase_cost"), default=150))
    current_service_total = len(tuple(_finance_services_for_property(prop) or ())) + len(tuple(_site_services_for_property(prop) or ()))
    service_seed_token = _text(metadata.get("site_service_seed_token")) or _text(prop.get("id")) or _text(prop.get("name"))
    target_service_total = len(tuple(_default_site_services_for_archetype(target, seed_token=service_seed_token) or ()))
    target_service_total += len(tuple(_FINANCE_SERVICE_FALLBACKS.get(target, ()) or ()))
    complexity_delta = max(0, int(target_service_total) - int(current_service_total))

    base_factor = 0.34 + (0.38 * float(rarity_rank))
    complexity_factor = 0.1 * float(complexity_delta)
    total_cost = max(25, int(round(float(source_price) * float(base_factor + complexity_factor))))
    return {
        "target_archetype": target,
        "target_label": _archetype_title(target),
        "source_price": int(source_price),
        "target_count": int(target_count),
        "rarity_rank": float(round(rarity_rank, 3)),
        "rarity_label": rarity_label,
        "cost": int(total_cost),
        "complexity_delta": int(complexity_delta),
    }


def player_business_remodel_options(prop):
    if not isinstance(prop, dict) or not property_supports_player_business(prop):
        return ()
    rows = []
    for archetype in BUSINESS_REMODEL_ELIGIBLE_ARCHETYPES:
        quote = player_business_remodel_quote(prop, archetype)
        if not isinstance(quote, dict):
            continue
        rows.append(quote)
    rows.sort(
        key=lambda row: (
            int(row.get("cost", 0)),
            -float(row.get("rarity_rank", 0.0)),
            str(row.get("target_label", "")).lower(),
        )
    )
    return tuple(rows)


def player_business_apply_remodel(sim, prop, target_archetype):
    quote = player_business_remodel_quote(prop, target_archetype)
    if not isinstance(quote, dict) or not isinstance(prop, dict):
        return None

    metadata = _property_metadata(prop)
    service_seed_token = _text(metadata.get("site_service_seed_token")) or _text(prop.get("id")) or _text(prop.get("name"))
    target = str(quote.get("target_archetype", "")).strip().lower()
    metadata["archetype"] = target
    metadata["is_storefront"] = bool(target in BUSINESS_REMODEL_ELIGIBLE_ARCHETYPES)
    metadata["site_services"] = list(_default_site_services_for_archetype(target, seed_token=service_seed_token))
    finance_defaults = tuple(_FINANCE_SERVICE_FALLBACKS.get(target, ()) or ())
    metadata["finance_services"] = list(finance_defaults)
    metadata.pop("access_controller_hours", None)

    state = player_business_state(prop, create=True)
    if isinstance(state, dict):
        state["required_staff"] = _required_staff_for(prop)
        state["baseline_hours"] = None
        player_business_set_customer_policy(prop, state.get("customer_policy"))
        player_business_set_hours_mode(sim, prop, state.get("hours_mode"))

    return {
        **quote,
        "business_name": _text(metadata.get("business_name")) or _property_label(prop),
        "site_services": tuple(_site_services_for_property(prop) or ()),
        "finance_services": tuple(_finance_services_for_property(prop) or ()),
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
    markup_profile = player_business_markup_profile(prop)
    price_mult = max(0.75, float(profile.get("price_mult", 1.0)) * float(markup_profile.get("buy_mult", 1.0)))

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


def _business_reputation_market_effect(sim, prop):
    base = {
        "awareness_count": 0,
        "weighted_awareness": 0.0,
        "reputation_state": "",
        "reputation_note": "",
        "community_note": "",
        "community_signal_note": "",
        "community_lift": 0.0,
        "community_drag": 0.0,
        "community_signal_lift": 0.0,
        "community_signal_drag": 0.0,
        "patronage_score": 0.0,
        "staple_score": 0.0,
        "trouble_score": 0.0,
        "gouging_score": 0.0,
        "revenue_mult": 1.0,
        "slippage_mult": 1.0,
        "footfall_delta_pct": 0,
        "churn_delta_pct": 0,
    }
    if sim is None or not isinstance(prop, dict):
        return dict(base)

    property_id = _text(prop.get("id"))
    if not property_id:
        return dict(base)

    snapshot = property_business_reputation_snapshot(sim, property_id)
    awareness_count = max(0, _int_or(snapshot.get("awareness_count"), default=0))
    weighted_awareness = max(0.0, float(snapshot.get("weighted_awareness", 0.0) or 0.0))
    trust = _clamp(snapshot.get("trust", 0.0), 0.0, 1.0)
    reliability = _clamp(snapshot.get("reliability", 0.0), 0.0, 1.0)
    fear = _clamp(snapshot.get("fear", 0.0), 0.0, 1.0)
    heat = _clamp(snapshot.get("heat", 0.0), 0.0, 1.0)
    price_fairness = _clamp(snapshot.get("price_fairness", 0.0), -1.0, 1.0)
    loyalty = _clamp(snapshot.get("loyalty", 0.0), 0.0, 1.0)
    resentment = _clamp(snapshot.get("resentment", 0.0), 0.0, 1.0)
    patronage_score = _clamp(snapshot.get("patronage_score", 0.0), 0.0, 1.0)
    staple_score = _clamp(snapshot.get("staple_score", 0.0), 0.0, 1.0)
    trouble_score = _clamp(snapshot.get("trouble_score", 0.0), 0.0, 1.0)
    gouging_score = _clamp(snapshot.get("gouging_score", 0.0), 0.0, 1.0)
    community_lift = _clamp(snapshot.get("community_lift", 0.0), 0.0, 1.0)
    community_drag = _clamp(snapshot.get("community_drag", 0.0), 0.0, 1.0)
    community_signal_lift = _clamp(snapshot.get("community_signal_lift", 0.0), 0.0, 1.0)
    community_signal_drag = _clamp(snapshot.get("community_signal_drag", 0.0), 0.0, 1.0)
    community_note = _text(snapshot.get("community_note"))
    community_signal_note = _text(snapshot.get("community_signal_note"))

    awareness_strength = _clamp((awareness_count * 0.18) + (weighted_awareness * 0.12), 0.0, 1.0)
    price_good = max(0.0, price_fairness)
    price_pain = max(0.0, -price_fairness)
    crowd_pull = awareness_strength * _clamp(
        (patronage_score * 0.52)
        + (staple_score * 0.24)
        + (trust * 0.12)
        + (loyalty * 0.08)
        + (price_good * 0.04),
        0.0,
        1.0,
    )
    churn_pressure = awareness_strength * _clamp(
        (trouble_score * 0.42)
        + (gouging_score * 0.22)
        + (resentment * 0.16)
        + (price_pain * 0.10)
        + (heat * 0.06)
        + (fear * 0.04),
        0.0,
        1.0,
    )
    revenue_mult = _clamp(1.0 + (crowd_pull * 0.24) - (churn_pressure * 0.24), 0.74, 1.3)
    slippage_mult = _clamp(1.0 - (crowd_pull * 0.18) + (churn_pressure * 0.36), 0.72, 1.52)

    reputation_state = str(snapshot.get("reputation_state", "") or "").strip().lower()
    reputation_note = ""
    if awareness_count >= 3:
        if reputation_state == "staple" and crowd_pull >= 0.22:
            reputation_note = "neighborhood staple"
        elif gouging_score >= max(0.46, trouble_score * 0.88):
            reputation_note = "price grumbling"
        elif reputation_state == "troubled" or churn_pressure >= 0.24:
            reputation_note = "front trouble"
        elif crowd_pull >= 0.18 and patronage_score >= 0.34:
            reputation_note = "growing regulars"

    result = dict(base)
    result.update({
        "awareness_count": int(awareness_count),
        "weighted_awareness": round(float(weighted_awareness), 3),
        "reputation_state": reputation_state,
        "reputation_note": reputation_note,
        "community_note": community_note,
        "community_signal_note": community_signal_note,
        "community_lift": round(float(community_lift), 3),
        "community_drag": round(float(community_drag), 3),
        "community_signal_lift": round(float(community_signal_lift), 3),
        "community_signal_drag": round(float(community_signal_drag), 3),
        "patronage_score": round(float(patronage_score), 3),
        "staple_score": round(float(staple_score), 3),
        "trouble_score": round(float(trouble_score), 3),
        "gouging_score": round(float(gouging_score), 3),
        "revenue_mult": round(float(revenue_mult), 3),
        "slippage_mult": round(float(slippage_mult), 3),
        "footfall_delta_pct": int(round((float(revenue_mult) - 1.0) * 100.0)),
        "churn_delta_pct": int(round((float(slippage_mult) - 1.0) * 100.0)),
    })
    return result


def _active_business_scene_market_pressure(sim, prop):
    base = {
        "scene_revenue_mult": 1.0,
        "scene_slippage_mult": 1.0,
        "scene_pressure_note": "",
    }
    if sim is None or not isinstance(prop, dict):
        return dict(base)

    property_id = _text(prop.get("id"))
    if not property_id:
        return dict(base)

    state = getattr(sim, "business_event_scene_state", None)
    active = (state or {}).get("active", {}) if isinstance(state, dict) else {}
    if not isinstance(active, dict):
        return dict(base)

    revenue_mult = 1.0
    slippage_mult = 1.0
    note = ""
    for scene in active.values():
        if not isinstance(scene, dict):
            continue
        if _text(scene.get("property_id")) != property_id:
            continue
        event_phase = _text(scene.get("event_phase")).lower()
        if event_phase == "block_watch":
            revenue_mult *= 1.04
            slippage_mult *= 0.68
            note = "block watch"
        elif event_phase == "soft_front":
            revenue_mult *= 0.94
            slippage_mult *= 1.42
            note = "soft-front trouble"

    result = dict(base)
    result.update({
        "scene_revenue_mult": round(float(_clamp(revenue_mult, 0.72, 1.36)), 3),
        "scene_slippage_mult": round(float(_clamp(slippage_mult, 0.5, 1.75)), 3),
        "scene_pressure_note": note,
    })
    return result


def _sync_staff_roster(sim, prop, state):
    roles = dict(state.get("staff_roles", {})) if isinstance(state.get("staff_roles"), dict) else {}
    owner_eid = prop.get("owner_eid")
    player_eid = getattr(sim, "player_eid", None)
    social_owner_eid = owner_eid
    if social_owner_eid is None and player_eid is not None:
        prop_id = _text(prop.get("id"))
        assets = sim.ecs.get(PlayerAssets).get(player_eid)
        owner_tag = _text(prop.get("owner_tag")).lower()
        if (assets and prop_id in getattr(assets, "owned_property_ids", set())) or owner_tag == "player":
            social_owner_eid = player_eid

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
        if social_owner_eid is not None and player_eid is not None and _int_or(social_owner_eid, default=-1) == _int_or(player_eid, default=-2):
            _ensure_player_business_staff_bond(sim, social_owner_eid, actor_eid, role=role)

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
    cache_state = _player_business_runtime_cache(sim)
    cache_key = _player_business_cache_key(prop)
    if cache_state is not None and cache_key:
        cached = cache_state.get("summary", {}).get(cache_key)
        if isinstance(cached, dict):
            return dict(cached)

    state = player_business_state(prop, create=True)
    if state is None:
        return None

    state["required_staff"] = _required_staff_for(prop)
    staffing = _sync_staff_roster(sim, prop, state)
    role_fit = player_business_staffing_fit(sim, prop)
    market = _business_health(sim, prop)
    reputation = _business_reputation_market_effect(sim, prop)
    scene_pressure = _active_business_scene_market_pressure(sim, prop)
    current_hour = _absolute_hour(sim)
    opening = _property_open_window(sim, prop)
    open_now = bool(_hour_in_window(current_hour % 24, opening)) if opening is not None else bool(_property_is_open(sim, prop))
    customer_policy = player_business_customer_policy(prop)
    hours_mode = player_business_hours_mode(prop)
    markup_profile = player_business_markup_profile(prop)
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
        elif note in {"steady", "strong trade", "soft market", "tight crew"}:
            reputation_note = str(last_summary.get("reputation_note", "")).strip()
            if reputation_note:
                note = reputation_note

    summary = {
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
        "markup_mode": str(markup_profile.get("mode", "standard")).strip() or "standard",
        "markup_mode_label": str(markup_profile.get("label", "standard pricing")).strip() or "standard pricing",
        "markup_note": str(markup_profile.get("note", "")).strip(),
        "customer_policy": customer_policy,
        "customer_policy_label": player_business_customer_policy_label(customer_policy),
        "health": float(market.get("health", 1.0)),
        "market_note": str(market.get("note", "")).strip(),
        "reputation_state": str(reputation.get("reputation_state", "")).strip(),
        "reputation_note": str(reputation.get("reputation_note", "")).strip(),
        "community_note": str(reputation.get("community_note", "")).strip(),
        "community_signal_note": str(reputation.get("community_signal_note", "")).strip(),
        "reputation_awareness": int(reputation.get("awareness_count", 0) or 0),
        "footfall_delta_pct": int(reputation.get("footfall_delta_pct", 0) or 0),
        "churn_delta_pct": int(reputation.get("churn_delta_pct", 0) or 0),
        "scene_pressure_note": str(scene_pressure.get("scene_pressure_note", "")).strip(),
        "last_scene_nuisance_note": str(state.get("last_scene_nuisance_note", "")).strip(),
        "last_scene_nuisance_loss": _int_or(state.get("last_scene_nuisance_loss"), default=0),
        "last_scene_nuisance_tick": None if state.get("last_scene_nuisance_tick") is None else _int_or(state.get("last_scene_nuisance_tick"), default=0),
        "note": note,
    }
    if cache_state is not None and cache_key:
        cache_state.setdefault("summary", {})[cache_key] = dict(summary)
    return summary


def player_business_status_snapshot(sim, prop):
    cache_state = _player_business_runtime_cache(sim)
    cache_key = _player_business_cache_key(prop)
    if cache_state is not None and cache_key:
        cached = cache_state.get("status", {}).get(cache_key)
        if isinstance(cached, dict):
            return dict(cached)

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
        "markup_mode": str(summary.get("markup_mode", "")).strip(),
        "markup_mode_label": str(summary.get("markup_mode_label", "")).strip(),
        "markup_note": str(summary.get("markup_note", "")).strip(),
        "customer_policy": str(summary.get("customer_policy", "")).strip(),
        "customer_policy_label": str(summary.get("customer_policy_label", "")).strip(),
        "reputation_state": str(summary.get("reputation_state", "")).strip(),
        "reputation_note": str(summary.get("reputation_note", "")).strip(),
        "community_note": str(summary.get("community_note", "")).strip(),
        "community_signal_note": str(summary.get("community_signal_note", "")).strip(),
        "reputation_awareness": _int_or(summary.get("reputation_awareness"), default=0),
        "footfall_delta_pct": _int_or(summary.get("footfall_delta_pct"), default=0),
        "churn_delta_pct": _int_or(summary.get("churn_delta_pct"), default=0),
        "scene_pressure_note": str(summary.get("scene_pressure_note", "")).strip(),
        "last_summary": last_summary,
        "last_hour": None if not last_summary else _int_or(last_summary.get("hour"), default=0),
        "gross_revenue": _int_or(last_summary.get("gross_revenue"), default=0),
        "realized_revenue": _int_or(last_summary.get("realized_revenue"), default=_int_or(last_summary.get("gross_revenue"), default=0)),
        "slippage": _int_or(last_summary.get("slippage"), default=0),
        "slippage_rate": float(last_summary.get("slippage_rate", 0.0) or 0.0),
        "service_reliability": float(last_summary.get("service_reliability", 0.0) or 0.0),
        "service_reliability_label": str(last_summary.get("service_reliability_label", "")).strip(),
        "operating_note": str(last_summary.get("operating_note", "")).strip(),
        "last_reputation_state": str(last_summary.get("reputation_state", "")).strip(),
        "last_reputation_note": str(last_summary.get("reputation_note", "")).strip(),
        "last_community_note": str(last_summary.get("community_note", "")).strip(),
        "last_community_signal_note": str(last_summary.get("community_signal_note", "")).strip(),
        "last_scene_pressure_note": str(last_summary.get("scene_pressure_note", "")).strip(),
        "last_scene_nuisance_note": str(summary.get("last_scene_nuisance_note", "")).strip(),
        "last_scene_nuisance_loss": _int_or(summary.get("last_scene_nuisance_loss"), default=0),
        "last_scene_nuisance_tick": None if summary.get("last_scene_nuisance_tick") is None else _int_or(summary.get("last_scene_nuisance_tick"), default=0),
        "last_reputation_awareness": _int_or(last_summary.get("reputation_awareness"), default=0),
        "last_footfall_delta_pct": _int_or(last_summary.get("footfall_delta_pct"), default=_int_or(summary.get("footfall_delta_pct"), default=0)),
        "last_churn_delta_pct": _int_or(last_summary.get("churn_delta_pct"), default=_int_or(summary.get("churn_delta_pct"), default=0)),
        "wages_paid": _int_or(last_summary.get("wages_paid"), default=0),
        "wages_due": _int_or(last_summary.get("wages_due"), default=0),
        "upkeep_paid": _int_or(last_summary.get("upkeep_paid"), default=0),
        "upkeep_due": _int_or(last_summary.get("upkeep_due"), default=0),
        "unpaid_wages": _int_or(last_summary.get("unpaid_wages"), default=0),
        "unpaid_upkeep": _int_or(last_summary.get("unpaid_upkeep"), default=0),
    })
    if cache_state is not None and cache_key:
        cache_state.setdefault("status", {})[cache_key] = dict(snapshot)
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
        prop = _resolve_owned_property(sim, property_id)
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


def _bond_rank(kind):
    return int(BUSINESS_BOND_RANK.get(str(kind or "").strip().lower(), 0))


def _social_for_business_bond(sim, actor_eid):
    if sim is None or actor_eid is None:
        return None
    try:
        actor_eid = int(actor_eid)
    except (TypeError, ValueError):
        return None
    socials = sim.ecs.get(NPCSocial)
    social = socials.get(actor_eid)
    if social is None:
        social = NPCSocial()
        sim.ecs.add(actor_eid, social)
    return social


def _upsert_business_coworker_bond(sim, source_eid, target_eid, *, role):
    if source_eid is None or target_eid is None:
        return False
    try:
        source_id = int(source_eid)
        target_id = int(target_eid)
    except (TypeError, ValueError):
        return False
    if source_id == target_id:
        return False

    social = _social_for_business_bond(sim, source_id)
    if social is None:
        return False

    baseline = BUSINESS_COWORKER_BASELINES.get(str(role or "").strip().lower(), BUSINESS_COWORKER_BASELINES["staff"])
    existing = social.bonds.get(target_id)
    if isinstance(existing, dict) and _bond_rank(existing.get("kind")) > _bond_rank("coworker"):
        return False

    closeness = float(baseline["closeness"])
    trust = float(baseline["trust"])
    protectiveness = float(baseline["protectiveness"])
    if isinstance(existing, dict):
        closeness = max(closeness, float(existing.get("closeness", 0.0) or 0.0))
        trust = max(trust, float(existing.get("trust", 0.0) or 0.0))
        protectiveness = max(protectiveness, float(existing.get("protectiveness", 0.0) or 0.0))

    social.add_bond(
        target_id,
        kind="coworker",
        closeness=closeness,
        trust=trust,
        protectiveness=protectiveness,
    )
    player_eid = getattr(sim, "player_eid", None)
    try:
        player_id = int(player_eid) if player_eid is not None else None
    except (TypeError, ValueError):
        player_id = None
    if player_id is not None and source_id != player_id:
        old_closeness = float(existing.get("closeness", 0.0) or 0.0) if isinstance(existing, dict) else 0.0
        old_trust = float(existing.get("trust", 0.0) or 0.0) if isinstance(existing, dict) else 0.0
        old_protectiveness = float(existing.get("protectiveness", 0.0) or 0.0) if isinstance(existing, dict) else 0.0
        bond = social.bonds.get(target_id)
        _record_actor_social_warmth(
            sim,
            source_id,
            other_eid=target_id,
            reason="player_business_staff_bond",
            trust_delta=float((bond or {}).get("trust", 0.0) or 0.0) - old_trust,
            closeness_delta=float((bond or {}).get("closeness", 0.0) or 0.0) - old_closeness,
            protectiveness_delta=float((bond or {}).get("protectiveness", 0.0) or 0.0) - old_protectiveness,
            post_bond=bond,
        )
    return True


def _ensure_player_business_staff_bond(sim, owner_eid, actor_eid, *, role):
    changed = _upsert_business_coworker_bond(sim, actor_eid, owner_eid, role=role)
    changed = _upsert_business_coworker_bond(sim, owner_eid, actor_eid, role=role) or changed
    return bool(changed)


def _remove_business_seeded_staff_bond(sim, owner_eid, actor_eid):
    if sim is None or owner_eid is None or actor_eid is None:
        return False
    try:
        owner_id = int(owner_eid)
        actor_id = int(actor_eid)
    except (TypeError, ValueError):
        return False
    if owner_id == actor_id:
        return False

    removed = False
    max_baseline = {
        key: max(float(row[key]) for row in BUSINESS_COWORKER_BASELINES.values())
        for key in ("closeness", "trust", "protectiveness")
    }
    for source_id, target_id in ((owner_id, actor_id), (actor_id, owner_id)):
        social = sim.ecs.get(NPCSocial).get(source_id)
        if social is None:
            continue
        bond = social.bonds.get(target_id)
        if not isinstance(bond, dict):
            continue
        if str(bond.get("kind", "") or "").strip().lower() != "coworker":
            continue
        if (
            float(bond.get("closeness", 0.0) or 0.0) <= max_baseline["closeness"] + 0.001
            and float(bond.get("trust", 0.0) or 0.0) <= max_baseline["trust"] + 0.001
            and float(bond.get("protectiveness", 0.0) or 0.0) <= max_baseline["protectiveness"] + 0.001
        ):
            player_eid = getattr(sim, "player_eid", None)
            try:
                player_id = int(player_eid) if player_eid is not None else None
            except (TypeError, ValueError):
                player_id = None
            if player_id is not None and source_id != player_id:
                _record_actor_social_warmth(
                    sim,
                    source_id,
                    other_eid=target_id,
                    reason="player_business_staff_bond_removed",
                    trust_delta=-float(bond.get("trust", 0.0) or 0.0),
                    closeness_delta=-float(bond.get("closeness", 0.0) or 0.0),
                    protectiveness_delta=-float(bond.get("protectiveness", 0.0) or 0.0),
                    post_bond=bond,
                )
            social.bonds.pop(target_id, None)
            removed = True
    return removed


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
    prop = _resolve_owned_property(sim, property_id) if property_id else None
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
    cache_state = _player_business_runtime_cache(sim)
    cache_key = _player_business_cache_key(prop)
    if cache_state is not None and cache_key:
        cached = cache_state.get("open_roles", {}).get(cache_key)
        if isinstance(cached, tuple):
            return cached

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
    result = tuple(open_roles)
    if cache_state is not None and cache_key:
        cache_state.setdefault("open_roles", {})[cache_key] = result
    return result


def player_business_open_role(sim, prop):
    open_roles = player_business_open_roles(sim, prop)
    return open_roles[0] if open_roles else ""


def player_business_staffing_targets(sim, owner_eid):
    assets = sim.ecs.get(PlayerAssets).get(owner_eid) if sim is not None else None
    if not assets:
        return ()

    targets = []
    for property_id in sorted(getattr(assets, "owned_property_ids", ()) or ()):
        prop = _resolve_owned_property(sim, property_id)
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
    _ensure_player_business_staff_bond(sim, owner_eid, actor_eid, role=role)

    state = player_business_state(prop, create=True)
    if state is not None:
        roles = dict(state.get("staff_roles", {}))
        roles[str(int(actor_eid))] = role
        roster = {int(raw_eid) for raw_eid in list(state.get("staff_roster", ()) or ()) if _int_or(raw_eid, default=0) > 0}
        roster.add(int(actor_eid))
        state["staff_roles"] = roles
        state["staff_roster"] = sorted(roster)
        _sync_staff_roster(sim, prop, state)
        _touch_player_business_runtime(prop, sim=sim)

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
    if ai:
        if str(ai.role or "").strip().lower() == "worker":
            ai.role = "civilian"
        ai.state = "idle"
        ai.target = None
        ai.target_eid = None

    will = sim.ecs.get(NPCWill).get(actor_eid)
    if will:
        will.intent = "idle"
        will.score = 0.0
        will.target = None
        will.target_eid = None
        will.last_tick = -1

    component = sim.ecs.get(OrganizationAffiliations).get(actor_eid)
    organization_eid = property_organization_eid(sim, employed_prop, ensure=False)
    if component and organization_eid is not None:
        membership = component.memberships.get(int(organization_eid))
        if isinstance(membership, dict):
            membership["active"] = False
            membership["primary"] = False
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
        _touch_player_business_runtime(employed_prop, sim=sim)

    _remove_business_seeded_staff_bond(sim, owner_eid, actor_eid)

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
        self.sim.events.subscribe("player_business_owner_warning_prompted", self.on_owner_warning_prompted)

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

    def on_owner_warning_prompted(self, event):
        if event.data.get("owner_eid") != self.player_eid:
            return
        prop = self.sim.properties.get(event.data.get("property_id"))
        if not isinstance(prop, dict):
            return
        state = player_business_state(prop, create=True)
        if not isinstance(state, dict):
            return
        pending = _player_business_pending_warning(state)
        signature = _text(event.data.get("signature"))
        if not pending or _text(pending.get("signature")) != signature:
            return
        speaker_eid = _int_or(event.data.get("npc_eid"), default=0)
        if speaker_eid > 0:
            _player_business_warning_history(state)[f"{signature}:{speaker_eid}"] = int(getattr(self.sim, "tick", 0) or 0)
        state["pending_owner_warning"] = {}

    def _set_dialogue_cooldown(self, npc_eid, duration):
        if npc_eid is None:
            return
        cooldowns = getattr(self.sim, "npc_dialogue_cooldowns", None)
        if not isinstance(cooldowns, dict):
            cooldowns = {}
            self.sim.npc_dialogue_cooldowns = cooldowns
        cooldowns[int(npc_eid)] = int(getattr(self.sim, "tick", 0) or 0) + max(0, int(duration or 0))

    def _queue_owner_warning(self, prop, state, current_summary, *, previous_summary=None):
        if not isinstance(prop, dict) or not isinstance(state, dict) or not isinstance(current_summary, dict):
            return
        signature = _player_business_warning_transition(previous_summary, current_summary)
        if not signature:
            return
        state["pending_owner_warning"] = {
            "property_id": _text(prop.get("id")),
            "signature": signature,
            "issue_kind": _player_business_warning_issue(current_summary),
            "reputation_note": _text(current_summary.get("reputation_note")),
            "community_note": _text(current_summary.get("community_note")),
            "community_signal_note": _text(current_summary.get("community_signal_note")),
            "awareness": _int_or(current_summary.get("reputation_awareness", current_summary.get("awareness_count", 0)), default=0),
            "created_tick": int(getattr(self.sim, "tick", 0) or 0),
            "next_attempt_tick": int(getattr(self.sim, "tick", 0) or 0),
            "active_speaker_eid": None,
        }

    def _prune_owner_warning(self, prop, state):
        if not isinstance(prop, dict) or not isinstance(state, dict):
            return {}
        pending = _player_business_pending_warning(state)
        if not pending:
            return {}
        current_signature = _player_business_warning_signature(dict(state.get("last_summary", {})) if isinstance(state.get("last_summary"), dict) else {})
        if not current_signature or current_signature != _text(pending.get("signature")):
            state["pending_owner_warning"] = {}
            return {}
        return pending

    def _warning_candidate_rows(self, prop, issue_kind, player_pos, state):
        if not isinstance(prop, dict) or not issue_kind or player_pos is None:
            return []
        property_id = _text(prop.get("id"))
        property_chunk = _player_business_chunk(self.sim, prop)
        if property_chunk is None:
            return []
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        occupations = self.sim.ecs.get(Occupation)
        history = _player_business_warning_history(state)
        current_signature = _player_business_warning_signature(
            dict(state.get("last_summary", {})) if isinstance(state.get("last_summary"), dict) else {}
        )
        rows = []
        for eid, ai in ais.items():
            if eid == self.player_eid or not ai:
                continue
            pos = positions.get(eid)
            if pos is None or int(pos.z) != int(player_pos.z):
                continue
            try:
                actor_chunk = tuple(int(bit) for bit in self.sim.chunk_coords(int(pos.x), int(pos.y)))
            except (TypeError, ValueError):
                continue
            if actor_chunk != property_chunk:
                continue
            if str(getattr(ai, "role", "") or "").strip().lower() == "wildlife":
                continue
            opinion = business_opinion_profile(self.sim, eid, property_id)
            score = _player_business_warning_issue_score(opinion, issue_kind)
            if score < 0.22:
                continue
            signature_key = f"{current_signature}:{int(eid)}"
            if signature_key in history:
                continue
            role = _player_business_warning_actor_role(self.sim, eid, prop)
            current_cover = _property_covering(self.sim, int(pos.x), int(pos.y), int(pos.z))
            at_property = _text((current_cover or {}).get("id")) == property_id
            workplace = getattr(occupations.get(eid), "workplace", None)
            works_here = isinstance(workplace, dict) and _text(workplace.get("property_id")) == property_id
            distance_to_player = _manhattan(int(pos.x), int(pos.y), int(player_pos.x), int(player_pos.y))
            rows.append((
                0 if role == "regular" else 1 if works_here else 2 if at_property else 3,
                distance_to_player,
                -float(score),
                -float(opinion.get("familiarity", 0.0) or 0.0),
                int(eid),
                role,
                opinion,
            ))
        rows.sort()
        result = []
        for _rank, distance_to_player, _neg_score, _neg_familiarity, eid, role, opinion in rows:
            result.append({
                "eid": int(eid),
                "distance_to_player": int(distance_to_player),
                "role": role,
                "opinion": dict(opinion),
            })
        return result

    def _dispatch_owner_warning(self, prop, state, pending):
        if not isinstance(prop, dict) or not isinstance(state, dict) or not isinstance(pending, dict):
            return False
        player_pos = self.sim.ecs.get(Position).get(self.player_eid)
        if player_pos is None:
            return False
        property_chunk = _player_business_chunk(self.sim, prop)
        if property_chunk is None:
            return False
        try:
            player_chunk = tuple(int(bit) for bit in self.sim.chunk_coords(int(player_pos.x), int(player_pos.y)))
        except (TypeError, ValueError):
            return False
        if player_chunk != property_chunk:
            return False
        if bool(getattr(self.sim, "dialog_ui", {}).get("open")):
            return False
        current_tick = int(getattr(self.sim, "tick", 0) or 0)
        if current_tick < _int_or(pending.get("next_attempt_tick"), default=0):
            return False
        issue_kind = _text(pending.get("issue_kind")).lower()
        if not issue_kind:
            return False
        candidates = self._warning_candidate_rows(prop, issue_kind, player_pos, state)
        if not candidates:
            pending["next_attempt_tick"] = current_tick + 48
            state["pending_owner_warning"] = pending
            return False
        chosen = candidates[0]
        speaker_eid = int(chosen.get("eid", 0) or 0)
        if speaker_eid <= 0:
            return False
        prompt_lines = _player_business_warning_prompt(
            prop,
            issue_kind,
            chosen.get("opinion", {}),
            pending,
            speaker_role=str(chosen.get("role", "")).strip().lower() or "local",
        )
        if not prompt_lines:
            pending["next_attempt_tick"] = current_tick + 48
            state["pending_owner_warning"] = pending
            return False
        signature = _text(pending.get("signature"))
        if int(chosen.get("distance_to_player", 99) or 99) <= 1:
            self._set_dialogue_cooldown(speaker_eid, 240)
            self.sim.emit(Event(
                "npc_dialogue_request",
                eid=self.player_eid,
                npc_eid=speaker_eid,
                prompt_lines=prompt_lines,
            ))
            self.sim.emit(Event(
                "player_business_owner_warning_prompted",
                npc_eid=speaker_eid,
                owner_eid=self.player_eid,
                property_id=_text(prop.get("id")),
                signature=signature,
                issue_kind=issue_kind,
            ))
            return True

        ai = self.sim.ecs.get(AI).get(speaker_eid)
        will = self.sim.ecs.get(NPCWill).get(speaker_eid)
        if ai is None:
            pending["next_attempt_tick"] = current_tick + 48
            state["pending_owner_warning"] = pending
            return False
        _queue_npc_initiated_dialogue(
            self.sim,
            speaker_eid,
            prompt_lines=prompt_lines,
            cooldown=240,
            metadata={
                "event_type": "player_business_owner_warning_prompted",
                "event_data": {
                    "owner_eid": self.player_eid,
                    "property_id": _text(prop.get("id")),
                    "signature": signature,
                    "issue_kind": issue_kind,
                },
            },
        )
        _sync_ai_intent(
            ai,
            will,
            int(getattr(self.sim, "tick", 0) or 0),
            "soliciting_player",
            score=44.0,
            target=(int(player_pos.x), int(player_pos.y), int(player_pos.z)),
            target_eid=self.player_eid,
        )
        pending["active_speaker_eid"] = int(speaker_eid)
        pending["next_attempt_tick"] = current_tick + 72
        state["pending_owner_warning"] = pending
        return True

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
        previous_summary = dict(state.get("last_summary", {})) if isinstance(state.get("last_summary"), dict) else {}
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
        reputation = _business_reputation_market_effect(self.sim, prop)
        scene_pressure = _active_business_scene_market_pressure(self.sim, prop)
        markup_profile = player_business_markup_profile(prop)
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
                * float(markup_profile.get("revenue_mult", 1.0))
                * float(reputation.get("revenue_mult", 1.0))
                * float(scene_pressure.get("scene_revenue_mult", 1.0))
            )
            gross_revenue = max(1, int(round(float(self._base_revenue_for(prop)) * revenue_factor)))
            if policy_revenue_factor <= 0.0:
                gross_revenue = 0
            slippage = int(round(
                float(gross_revenue)
                * float(operating.get("slippage_rate", 0.0))
                * float(policy_slippage_factor)
                * float(reputation.get("slippage_mult", 1.0))
                * float(scene_pressure.get("scene_slippage_mult", 1.0))
            ))
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
        if note in {"steady", "strong trade", "soft market", "tight crew"}:
            reputation_note = str(reputation.get("reputation_note", "")).strip()
            if reputation_note:
                note = reputation_note

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
            "markup_mode": str(markup_profile.get("mode", "standard")).strip() or "standard",
            "markup_mode_label": str(markup_profile.get("label", "standard pricing")).strip() or "standard pricing",
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
            "reputation_state": str(reputation.get("reputation_state", "")).strip(),
            "reputation_note": str(reputation.get("reputation_note", "")).strip(),
            "community_note": str(reputation.get("community_note", "")).strip(),
            "community_signal_note": str(reputation.get("community_signal_note", "")).strip(),
            "scene_pressure_note": str(scene_pressure.get("scene_pressure_note", "")).strip(),
            "reputation_awareness": int(reputation.get("awareness_count", 0) or 0),
            "footfall_delta_pct": int(reputation.get("footfall_delta_pct", 0) or 0),
            "churn_delta_pct": int(reputation.get("churn_delta_pct", 0) or 0),
            "reputation_revenue_mult": float(reputation.get("revenue_mult", 1.0) or 1.0),
            "reputation_slippage_mult": float(reputation.get("slippage_mult", 1.0) or 1.0),
            "scene_revenue_mult": float(scene_pressure.get("scene_revenue_mult", 1.0) or 1.0),
            "scene_slippage_mult": float(scene_pressure.get("scene_slippage_mult", 1.0) or 1.0),
            "account_balance": int(state.get("account_balance", 0)),
            "note": note,
        }
        self._queue_owner_warning(prop, state, dict(state.get("last_summary", {})), previous_summary=previous_summary)

    def update(self):
        assets = self._assets()
        if not assets:
            return

        hour_counter = _absolute_hour(self.sim)
        for property_id in sorted(getattr(assets, "owned_property_ids", ()) or ()):
            prop = _resolve_owned_property(self.sim, property_id)
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
            pending = self._prune_owner_warning(prop, state)
            if pending:
                self._dispatch_owner_warning(prop, state, pending)


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
    "player_business_markup_mode",
    "player_business_markup_mode_label",
    "player_business_markup_profile",
    "player_business_next_customer_policy",
    "player_business_next_hours_mode",
    "player_business_next_markup_mode",
    "player_business_open_role",
    "player_business_apply_remodel",
    "player_business_role_fit",
    "player_business_role_weights",
    "player_business_remodel_options",
    "player_business_remodel_quote",
    "refresh_player_business_runtime",
    "player_business_set_customer_policy",
    "player_business_set_hours_mode",
    "player_business_set_markup_mode",
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
