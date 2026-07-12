import random

from engine.sites import site_gameplay_profile
from game.criminal_justice_runtime import (
    _justice_booking_seizure_snapshot,
    _justice_held_property_snapshot,
    _justice_snapshot,
)
from game.justice_runtime import record_incident as _record_justice_incident
from game.components import (
    AI,
    ContactLedger,
    CreatureIdentity,
    FinancialProfile,
    Inventory,
    JusticeProfile,
    NPCMemory,
    NPCNeeds,
    NPCRoutine,
    NPCSocial,
    NPCTraits,
    Occupation,
    PlayerAssets,
    Position,
    PropertyKnowledge,
    Vitality,
)
from game.economy import chunk_economy_profile
from game.items import ITEM_CATALOG, credstick_total_credits, is_credstick_item, item_display_name
from game.organization_reputation import apply_organization_reputation_delta
from game.property_access import (
    finance_services_for_property,
    property_is_public,
    property_is_storefront,
    site_services_for_property,
    world_hour,
)
from game.property_runtime import (
    building_id_from_property,
    building_id_from_structure,
    property_covering,
    property_focus_position,
    resolve_property_record,
)
from game.service_runtime import _chunk_site_kinds
from game.system_support.actor_attention_runtime import record_actor_social_warmth as _record_actor_social_warmth


MIN_ACTIVE_OPPORTUNITIES = 6
MAX_ACTIVE_OPPORTUNITIES = 10
REMOTE_SEED_MIN_DISTANCE = 3
REMOTE_SEED_FAR_DISTANCE = 5
BASE_OPPORTUNITY_EXPIRE_HOURS = 24.0
ACCEPTED_OPPORTUNITY_EXPIRE_HOURS = 36.0
URGENT_OPPORTUNITY_EXPIRE_HOURS = 12.0
ACCEPTED_URGENT_OPPORTUNITY_EXPIRE_HOURS = 18.0
OPPORTUNITY_REFILL_COOLDOWN_HOURS = 1.0
OPPORTUNITY_TERMINAL_REFILL_DELAY_HOURS = 0.25
OPPORTUNITY_EMERGENCY_ACTIVE_COUNT = 2
EXPIRE_DISTANCE_BONUS_HOURS_PER_CHUNK = 1.0
EXPIRE_DISTANCE_BONUS_CAP_HOURS = 12.0
SERVICE_JOB_BOARD_SERVICES = frozenset({"courier_jobs", "agency_jobs", "bounty_jobs"})
SERVICE_JOB_DEADLINE_HOURS = {
    "courier_jobs": 8,
    "agency_jobs": 10,
    "bounty_jobs": 12,
}
SERVICE_JOB_PACKAGE_ITEM_ID = "sealed_packet"
SERVICE_JOB_NPC_SCAN_COOLDOWN_TICKS = 60
SERVICE_JOB_NPC_COMPLETE_MIN_TICKS = 80
SERVICE_JOB_NPC_COMPLETE_MAX_TICKS = 420
_OPPORTUNITY_URGENCY_KEYWORDS = (
    "urgent",
    "immediate",
    "right away",
    "asap",
    "tonight",
    "before dawn",
    "before sunrise",
    "before morning",
    "before noon",
)
_OPPORTUNITY_EXPIRE_VERSION = 3

EXCLUDED_CONTRACT_ROLES = {"guard", "scout"}

_FAILURE_FAMILY_BY_CODE = {
    "target_killed": "contact",
    "contact_unavailable": "contact",
    "custody_compromised": "legal",
    "booking_required_item_seized": "legal",
    "booking_confiscated": "legal",
    "booking_compromised": "legal",
    "held_required_item_seized": "legal",
    "held_property_seized": "legal",
    "legal_compromise": "legal",
    "pickup_unavailable": "pickup",
    "handoff_unavailable": "handoff",
    "site_unavailable": "site",
    "activity_unavailable": "service_lane",
    "expired": "expired",
    "provided_item_lost": "item",
    "rival_claimed": "rival",
    "rival_burned": "rival",
}

FINANCE_ARCHETYPES = {
    "bank",
    "office",
    "tower",
    "pawn_shop",
    "backroom_clinic",
}

OBJECTIVE_PREFERENCES = {
    "debt_exit": {
        "salvage_sweep",
        "trade_loop",
        "district_contract",
        "paper_trail",
        "debt_marker",
        "supply_shortage",
        "claims_chase",
        "backroom_buyback",
        "parts_recovery",
        "medical_drop",
        "distance_delivery",
        "distance_delivery_procure",
        "layover_shuffle",
        "route_stash",
        "yard_strip",
        "field_repair_call",
    },
    "networked_extraction": {
        "contact_run",
        "paper_trail",
        "shelter_stop",
        "district_contract",
        "property_dispute",
        "claims_chase",
        "records_pull",
        "watch_post",
        "service_friction",
        "distance_delivery",
        "distance_delivery_procure",
        "distance_pickup",
        "dead_drop_return",
        "layover_shuffle",
        "route_stash",
        "sightline_check",
        "relay_watch",
        "refuge_resupply",
        "spring_run",
    },
    "high_value_retrieval": {
        "intel_scout",
        "landmark_survey",
        "lead_followup",
        "district_contract",
        "missing_person",
        "records_pull",
        "watch_post",
        "contact_run",
        "service_friction",
        "property_dispute",
        "yard_strip",
        "sightline_check",
        "relay_watch",
        "route_stash",
    },
    "neighborhood_control": {
        "trade_loop",
        "district_contract",
        "contact_run",
        "property_dispute",
        "service_friction",
        "paper_trail",
        "claims_chase",
        "backroom_buyback",
        "supply_shortage",
        "tool_procurement",
        "tool_pickup",
        "supply_grab",
    },
}

SPECIALTY_OPPORTUNITY_THEMES = {
    "field_repair_call": "parts_yard",
    "layover_shuffle": "route_hub",
    "refuge_resupply": "field_refuge",
    "relay_watch": "watch_network",
    "route_stash": "route_hub",
    "sightline_check": "watch_network",
    "spring_run": "field_refuge",
    "yard_strip": "parts_yard",
}

SPECIALTY_FOCUS_SITE_KINDS = {
    "route_hub": (
        "bait_shop",
        "dock_shack",
        "ferry_post",
        "relay_post",
        "roadhouse",
        "tide_station",
        "truck_stop",
    ),
    "parts_yard": (
        "breaker_yard",
        "dock_shack",
        "drydock_yard",
        "roadhouse",
        "salvage_camp",
        "truck_stop",
        "work_shed",
    ),
    "watch_network": (
        "beacon_house",
        "coast_watch",
        "firewatch_tower",
        "inspection_shed",
        "lookout_post",
        "relay_post",
        "survey_post",
        "weather_station",
    ),
    "field_refuge": (
        "field_camp",
        "herbalist_camp",
        "herbalist_shop",
        "ranger_hut",
        "ruin_shelter",
    ),
}

OPPORTUNITY_ROUTE_DEFAULTS = {
    "salvage_sweep": {
        "recent_activity_tags": ("discovery_salvage",),
    },
    "parts_recovery": {
        "recent_activity_tags": ("discovery_salvage",),
    },
    "water_run": {
        "recent_activity_tags": ("discovery_water",),
    },
    "tool_pickup": {
        "recent_activity_tags": ("discovery_tools",),
    },
    "tool_procurement": {
        "recent_activity_tags": ("discovery_tools", "trade", "contact"),
        "prefer_storefront": True,
        "prefer_public": True,
    },
    "supply_grab": {
        "recent_activity_tags": ("discovery_supplies",),
    },
    "trade_loop": {
        "recent_activity_tags": ("trade", "contact"),
        "prefer_storefront": True,
        "prefer_public": True,
    },
    "paper_trail": {
        "recent_activity_tags": ("finance", "service", "intel"),
        "prefer_finance_services": True,
        "prefer_site_services": True,
        "prefer_public": True,
    },
    "backroom_buyback": {
        "recent_activity_tags": ("trade", "contact"),
        "prefer_storefront": True,
        "prefer_public": True,
    },
    "debt_marker": {
        "recent_activity_tags": ("contact", "finance", "trade"),
        "prefer_storefront": True,
        "prefer_finance_services": True,
        "prefer_public": True,
    },
    "supply_shortage": {
        "recent_activity_tags": ("trade", "service", "contact"),
        "prefer_storefront": True,
        "prefer_site_services": True,
        "prefer_public": True,
    },
    "contact_run": {
        "recent_activity_tags": ("contact",),
        "prefer_storefront": True,
        "prefer_public": True,
    },
    "missing_person": {
        "recent_activity_tags": ("contact", "intel"),
        "prefer_public": True,
    },
    "property_dispute": {
        "recent_activity_tags": ("contact", "intel"),
        "prefer_public": True,
    },
    "claims_chase": {
        "recent_activity_tags": ("finance", "service", "trade", "contact"),
        "prefer_finance_services": True,
    },
    "records_pull": {
        "recent_activity_tags": ("intel", "service", "finance"),
        "prefer_finance_services": True,
        "prefer_site_services": True,
    },
    "watch_post": {
        "recent_activity_tags": ("stakeout", "intel"),
        "prefer_public": True,
        "prefer_site_services": True,
    },
    "service_friction": {
        "recent_activity_tags": ("service", "trade", "contact", "intel"),
        "prefer_storefront": True,
        "prefer_site_services": True,
        "prefer_public": True,
    },
    "intel_scout": {
        "recent_activity_tags": ("intel", "stakeout"),
        "prefer_site_services": True,
        "prefer_public": True,
    },
    "shelter_stop": {
        "recent_activity_tags": ("service",),
        "prefer_site_services": True,
        "prefer_public": True,
    },
    "district_contract": {
        "recent_activity_tags": ("trade", "service", "finance", "contact"),
        "prefer_storefront": True,
        "prefer_finance_services": True,
        "prefer_site_services": True,
        "prefer_public": True,
    },
    "landmark_survey": {
        "recent_activity_tags": ("discovery_landmark", "intel", "stakeout"),
        "prefer_public": True,
    },
    "layover_shuffle": {
        "recent_activity_tags": ("contact", "trade", "finance"),
        "prefer_public": True,
    },
    "route_stash": {
        "recent_activity_tags": ("contact", "trade", "intel"),
        "prefer_public": True,
    },
    "yard_strip": {
        "recent_activity_tags": ("discovery_salvage", "contact", "trade"),
        "prefer_public": True,
    },
    "field_repair_call": {
        "recent_activity_tags": ("discovery_tools", "contact", "trade", "service"),
        "prefer_public": True,
    },
    "sightline_check": {
        "recent_activity_tags": ("discovery_landmark", "stakeout", "intel"),
        "prefer_public": True,
    },
    "relay_watch": {
        "recent_activity_tags": ("stakeout", "intel"),
        "prefer_public": True,
    },
    "refuge_resupply": {
        "recent_activity_tags": ("service", "contact", "discovery_supplies"),
        "prefer_site_services": True,
        "prefer_public": True,
    },
    "spring_run": {
        "recent_activity_tags": ("discovery_water", "service", "contact"),
        "prefer_site_services": True,
        "prefer_public": True,
    },
    "lead_followup": {
        "recent_activity_tags": ("intel", "stakeout", "contact", "service", "finance"),
        "prefer_public": True,
    },
}

OPPORTUNITY_ACTIVITY_REASON_LABELS = {
    "contact": "made local contact",
    "intel": "pulled intel on the site",
    "service": "worked the site's services",
    "trade": "worked the local counter",
    "finance": "worked the local finance desk",
    "stakeout": "held a quiet watch on the site",
    "discovery": "surveyed the target area",
    "discovery_landmark": "surveyed the landmark route",
    "discovery_salvage": "worked the salvage route",
    "discovery_water": "worked the water route",
    "discovery_tools": "worked the tool route",
    "discovery_supplies": "worked the supply route",
}

SPECIALTY_CONTACT_ROLE_BY_SITE_KIND = {
    "bait_shop": "bait runner",
    "beacon_house": "beacon keeper",
    "breaker_yard": "yard foreman",
    "coast_watch": "watch captain",
    "dock_shack": "dock clerk",
    "drydock_yard": "yard foreman",
    "ferry_post": "dispatcher",
    "field_camp": "quartermaster",
    "firewatch_tower": "watch keeper",
    "herbalist_camp": "remedy keeper",
    "herbalist_shop": "remedy keeper",
    "inspection_shed": "inspector",
    "lookout_post": "watch keeper",
    "ranger_hut": "ranger",
    "relay_post": "dispatcher",
    "roadhouse": "counter manager",
    "ruin_shelter": "caretaker",
    "salvage_camp": "scrap runner",
    "survey_post": "survey hand",
    "tide_station": "tide reader",
    "truck_stop": "night clerk",
    "weather_station": "storm reader",
    "work_shed": "fixer",
}

COURIER_ITEM_POOL = (
    "street_ration",
    "hydration_salts",
    "med_gel",
    "micro_medkit",
    "city_pass_token",
    "transit_daypass",
    "credstick_chip",
    "property_key",
    "access_badge",
)

def opportunity_required_item_survives_pickup(item_id):
    item_key = str(item_id or "").strip().lower()
    if not item_key or item_key not in ITEM_CATALOG:
        return False
    # Player credstick pickup auto-converts into wallet credits, so no carried
    # item remains for later handoffs, dead drops, or delivery checks.
    if is_credstick_item(item_key):
        return False
    return True


def _required_item_pool(item_ids):
    if isinstance(item_ids, str):
        raw = (item_ids,)
    else:
        raw = tuple(item_ids or ())
    return [
        str(item_id).strip().lower()
        for item_id in raw
        if opportunity_required_item_survives_pickup(item_id)
    ]


COURIER_PARTIES = (
    ("a local fixer", "a district runner"),
    ("a clinic assistant", "a remote patient"),
    ("a depot clerk", "a field contact"),
    ("a neighborhood broker", "a tower receptionist"),
)

_AWARENESS_RANK = {
    "unknown": 0,
    "heard": 1,
    "confirmed": 2,
}


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


def _specialty_anchor_read(anchor_name, identity_label):
    anchor_name = _text(anchor_name)
    identity_label = _text(identity_label)
    if anchor_name and identity_label and anchor_name.lower() != identity_label.lower():
        return f"{anchor_name} on the {identity_label}"
    return anchor_name or identity_label or "this stretch"


def _specialty_anchor_for_sites(theme_id, sites, rng):
    theme_id = _text(theme_id).lower()
    focus_kinds = {
        _text(kind).lower()
        for kind in SPECIALTY_FOCUS_SITE_KINDS.get(theme_id, ())
        if _text(kind)
    }
    weighted = []
    for index, site in enumerate(tuple(sites or ())):
        if not isinstance(site, dict):
            continue
        kind = _text(site.get("kind")).lower()
        if focus_kinds and kind not in focus_kinds:
            continue
        site_name = _text(site.get("name")) or kind.replace("_", " ").title()
        founder_name = _text(site.get("business_founder_name"))
        organization_name = _text(site.get("business_name")) or site_name
        contact_role = _text(SPECIALTY_CONTACT_ROLE_BY_SITE_KIND.get(kind))
        score = 1.0
        if founder_name:
            score += 0.9
        if organization_name and organization_name.lower() != site_name.lower():
            score += 0.45
        if contact_role:
            score += 0.2
        if bool(site.get("public")):
            score += 0.1
        weighted.append((score, int(index), site_name, organization_name, founder_name, contact_role, site))

    if not weighted:
        return {}

    total = sum(weight for weight, *_rest in weighted)
    pick = rng.uniform(0.0, total if total > 0.0 else 1.0)
    running = 0.0
    chosen = weighted[-1]
    for weight, *rest in weighted:
        running += weight
        if pick <= running:
            chosen = (weight, *rest)
            break

    _weight, _index, site_name, organization_name, founder_name, contact_role, site = chosen
    kind = _text(site.get("kind")).lower()
    return {
        "anchor_site_name": site_name,
        "anchor_site_kind": kind,
        "anchor_site_id": _text(site.get("site_id")),
        "organization_name": organization_name,
        "contact_name": founder_name,
        "contact_role": contact_role,
    }


def _specialty_anchor_requirements(anchor):
    anchor = anchor if isinstance(anchor, dict) else {}
    requirements = {}
    property_name = _text(anchor.get("anchor_site_name"))
    if property_name:
        requirements["property_name"] = property_name
    site_kind = _text(anchor.get("anchor_site_kind")).lower()
    if site_kind:
        requirements["site_kind"] = site_kind
    site_id = _text(anchor.get("anchor_site_id"))
    if site_id:
        requirements["site_id"] = site_id
    return requirements


def _clamp(value, lo=0.0, hi=100.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(lo)
    return max(float(lo), min(float(hi), number))


def _chunk_tuple(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        return (int(value[0]), int(value[1]))
    except (TypeError, ValueError):
        return None


def _chunk_key(chunk):
    normalized = _chunk_tuple(chunk)
    if normalized is None:
        return ""
    return f"{int(normalized[0])},{int(normalized[1])}"


def _chunk_from_key(raw):
    text = str(raw or "").strip()
    if not text:
        return None
    left, sep, right = text.partition(",")
    if not sep:
        return None
    try:
        return (int(left), int(right))
    except (TypeError, ValueError):
        return None


def _manhattan(a, b):
    if not a or not b:
        return 0
    return abs(int(a[0]) - int(b[0])) + abs(int(a[1]) - int(b[1]))


def _chunk_direction(origin, target):
    if not origin or not target:
        return "HERE"
    dx = int(target[0]) - int(origin[0])
    dy = int(target[1]) - int(origin[1])
    parts = []
    if dy < 0:
        parts.append("N")
    elif dy > 0:
        parts.append("S")
    if dx > 0:
        parts.append("E")
    elif dx < 0:
        parts.append("W")
    return "".join(parts) if parts else "HERE"


def opportunity_distance_text(distance_chunks, direction="HERE"):
    distance = max(0, _safe_int(distance_chunks, default=0))
    direction = str(direction or "HERE").strip().upper() or "HERE"
    if distance <= 0 or direction == "HERE":
        return "here"

    meters = distance * 200
    if meters < 1000:
        metric = f"{meters}m"
    else:
        km = meters / 1000.0
        if abs(km - round(km)) < 0.05:
            metric = f"{int(round(km))}km"
        else:
            metric = f"{km:.1f}km"
    return f"{metric} {direction}"


def _risk_pressure(risk_label):
    risk = str(risk_label or "").strip().lower()
    if risk in {"hazardous"}:
        return "high"
    if risk in {"exposed"}:
        return "medium"
    return "low"


def _travel_tax_components(travel):
    travel = travel if isinstance(travel, dict) else {}
    energy_cost = max(0, _safe_int(travel.get("energy_cost"), default=0))
    safety_cost = max(0, _safe_int(travel.get("safety_cost"), default=0))
    social_cost = max(0, _safe_int(travel.get("social_cost"), default=0))
    return energy_cost, safety_cost, social_cost


def _reward_with_travel_bias(reward, *, risk_label, travel, distance):
    reward = dict(reward or {})
    risk = str(risk_label or "").strip().lower()
    distance = max(0, _safe_int(distance, default=0))
    energy_cost, safety_cost, social_cost = _travel_tax_components(travel)
    tax_total = energy_cost + safety_cost + social_cost

    risk_mult = {
        "calm": 0.92,
        "low": 1.0,
        "exposed": 1.14,
        "hazardous": 1.27,
    }.get(risk, 1.0)
    distance_mult = 1.0 + min(0.8, max(0, distance - 1) * 0.11)
    scalar = risk_mult * distance_mult

    credits = max(0, _safe_int(reward.get("credits"), default=0))
    if credits > 0:
        scaled = int(round(credits * scalar))
        travel_bonus = int(round(tax_total * 1.85))
        distance_bonus = max(0, min(20, max(0, distance - 4) * 4))
        total = scaled + travel_bonus + distance_bonus
        if distance >= 5:
            total = max(total, 32 if risk == "hazardous" else 24)
        elif distance >= 4 and risk in {"exposed", "hazardous"}:
            total = max(total, 26 if risk == "hazardous" else 20)
        reward["credits"] = max(1, min(88, total))

    standing = max(0, _safe_int(reward.get("standing"), default=0))
    if standing > 0 and risk in {"exposed", "hazardous"}:
        reward["standing"] = min(4, standing + 1)

    intel = max(0, _safe_int(reward.get("intel"), default=0))
    if intel > 0 and distance >= 4:
        reward["intel"] = min(6, intel + 1)

    for key, tax_cost in (
        ("energy", energy_cost),
        ("safety", safety_cost),
        ("social", social_cost),
    ):
        if tax_cost <= 0:
            continue
        base = max(0, _safe_int(reward.get(key), default=0))
        reward[key] = min(40, base + max(1, int(round(tax_cost * 0.8))))

    return reward


def _service_label(service):
    service = str(service or "").strip().lower()
    if service == "intel":
        return "intel"
    if service == "shelter":
        return "shelter"
    if service == "banking":
        return "banking"
    if service == "insurance":
        return "insurance"
    return service or "service"


def opportunity_source_label(source, short=False):
    source_key = str(source or "").strip().lower()
    labels = {
        "overworld_tag": ("map", "map signal"),
        "property_service": ("services", "local services"),
        "economy_profile": ("economy", "district economy"),
        "contact": ("contact", "known contact"),
        "intel": ("intel", "known intel"),
    }
    if source_key in labels:
        short_label, long_label = labels[source_key]
        return short_label if short else long_label
    fallback = source_key.replace("_", " ").strip() or "unknown"
    return fallback if short else fallback


def _state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits

    state = traits.get("opportunities")
    if not isinstance(state, dict):
        state = {}
        traits["opportunities"] = state

    active = state.get("active")
    if not isinstance(active, list):
        active = []
        state["active"] = active

    completed = state.get("completed")
    if not isinstance(completed, list):
        completed = []
        state["completed"] = completed

    failed = state.get("failed")
    if not isinstance(failed, list):
        failed = []
        state["failed"] = failed

    intel_by_observer = state.get("intel_by_observer")
    if not isinstance(intel_by_observer, dict):
        intel_by_observer = {}
        state["intel_by_observer"] = intel_by_observer

    service_claims = state.get("service_job_board_claims")
    if not isinstance(service_claims, dict):
        service_claims = {}
        state["service_job_board_claims"] = service_claims

    state["next_id"] = max(1, _safe_int(state.get("next_id"), default=1))
    state["seeded"] = bool(state.get("seeded", False))
    if "origin_chunk" in state:
        normalized_origin = _chunk_tuple(state.get("origin_chunk"))
        state["origin_chunk"] = normalized_origin
    else:
        state["origin_chunk"] = None
    tracked_targets = state.get("tracked_targets")
    if not isinstance(tracked_targets, dict):
        tracked_targets = {}
        state["tracked_targets"] = tracked_targets
    current_tick = _safe_int(getattr(sim, "tick", 0), default=0)
    fallback_refill_tick = _safe_int(
        state.get("last_refresh_tick"),
        default=_safe_int(state.get("seed_tick"), default=current_tick),
    )
    state["last_refill_tick"] = _safe_int(state.get("last_refill_tick"), default=fallback_refill_tick)
    state["next_refill_tick"] = _safe_int(
        state.get("next_refill_tick"),
        default=state["last_refill_tick"],
    )
    state["pending_refill_reason"] = str(state.get("pending_refill_reason", "") or "").strip().lower()
    state["last_refill_reason"] = str(state.get("last_refill_reason", "") or "").strip().lower()
    return state


_OPPORTUNITY_HOT_STAGE_KINDS = {
    "watch_post",
    "relay_watch",
    "sightline_check",
    "intel_scout",
    "rival_followup",
}
_OPPORTUNITY_HOT_ACTIVITY_TAGS = {"stakeout", "intel"}


def _tracked_targets_bucket(state):
    if not isinstance(state, dict):
        return {}
    tracked_targets = state.get("tracked_targets")
    if not isinstance(tracked_targets, dict):
        tracked_targets = {}
        state["tracked_targets"] = tracked_targets
    return tracked_targets


def _tracked_target_key(opportunity_id, stage_kind, property_id):
    try:
        opp_key = int(opportunity_id or 0)
    except (TypeError, ValueError):
        opp_key = 0
    stage_key = str(stage_kind or "").strip().lower() or "task"
    prop_key = str(property_id or "").strip()
    if opp_key <= 0 or not prop_key:
        return ""
    return f"{opp_key}:{stage_key}:{prop_key}"


def _opportunity_recent_activity_tags(opportunity):
    requirements = _opportunity_requirements(opportunity)
    tags = _normalize_activity_tags(requirements.get("recent_activity_tags"))
    if tags:
        return frozenset(tags)
    defaults = opportunity.get("defaults", {}) if isinstance(opportunity.get("defaults", {}), dict) else {}
    return frozenset(_normalize_activity_tags(defaults.get("recent_activity_tags")))


def _opportunity_has_hot_target(opportunity):
    if not isinstance(opportunity, dict):
        return False
    kind = str(opportunity.get("kind", "") or "").strip().lower()
    if kind in _OPPORTUNITY_HOT_STAGE_KINDS:
        return True
    requirements = _opportunity_requirements(opportunity)
    if bool(requirements.get("rival_followup")):
        return True
    risk = str(opportunity.get("risk", "") or "").strip().lower()
    if risk == "hazardous":
        return True
    source = str(opportunity.get("source", "") or "").strip().lower()
    if source in {"public_emergency", "emergency"}:
        return True
    return bool(_opportunity_recent_activity_tags(opportunity).intersection(_OPPORTUNITY_HOT_ACTIVITY_TAGS))


def _opportunity_stage_targets(opportunity):
    requirements = _opportunity_requirements(opportunity)
    stage_rows = []

    pickup_property_id = str(requirements.get("pickup_property_id", "") or "").strip()
    pickup_building_id = str(requirements.get("pickup_building_id", "") or "").strip()
    pickup_chunk = _chunk_tuple(requirements.get("pickup_chunk")) or _chunk_tuple(opportunity.get("chunk"))
    if pickup_property_id:
        stage_rows.append({
            "stage_kind": "pickup",
            "property_id": pickup_property_id,
            "building_id": pickup_building_id,
            "chunk": pickup_chunk,
        })

    require_item_id = str(requirements.get("require_item_id", "") or "").strip().lower()
    if require_item_id:
        delivery_property_id = str(
            requirements.get("delivery_property_id", "") or requirements.get("property_id", "") or ""
        ).strip()
        delivery_building_id = str(
            requirements.get("delivery_building_id", "") or requirements.get("building_id", "") or ""
        ).strip()
        delivery_chunk = _chunk_tuple(requirements.get("delivery_chunk")) or _chunk_tuple(requirements.get("visit_chunk")) or _chunk_tuple(opportunity.get("chunk"))
        if delivery_property_id:
            stage_rows.append({
                "stage_kind": "delivery",
                "property_id": delivery_property_id,
                "building_id": delivery_building_id,
                "chunk": delivery_chunk,
            })
        return tuple(stage_rows)

    property_id = str(requirements.get("property_id", "") or "").strip()
    building_id = str(requirements.get("building_id", "") or "").strip()
    visit_chunk = _chunk_tuple(requirements.get("visit_chunk")) or _chunk_tuple(opportunity.get("chunk"))
    if property_id:
        stage_rows.append({
            "stage_kind": "task",
            "property_id": property_id,
            "building_id": building_id,
            "chunk": visit_chunk,
        })
    return tuple(stage_rows)


def _tracked_target_record_for_stage(sim, opportunity_id, stage_kind, property_id):
    state = _state(sim)
    key = _tracked_target_key(opportunity_id, stage_kind, property_id)
    tracked = _tracked_targets_bucket(state)
    if key:
        row = tracked.get(key)
        if isinstance(row, dict):
            return row
    try:
        target_id = int(opportunity_id or 0)
    except (TypeError, ValueError):
        target_id = 0
    stage_key = str(stage_kind or "").strip().lower() or "task"
    if target_id <= 0:
        return None
    for row in tracked.values():
        if not isinstance(row, dict):
            continue
        try:
            if int(row.get("opportunity_id", 0) or 0) != target_id:
                continue
        except (TypeError, ValueError):
            continue
        if str(row.get("stage_kind", "") or "").strip().lower() != stage_key:
            continue
        return row
    return None


def _tracked_target_rows_for_opportunity(sim, opportunity_id):
    try:
        target_id = int(opportunity_id or 0)
    except (TypeError, ValueError):
        target_id = 0
    if target_id <= 0:
        return ()
    tracked = _tracked_targets_bucket(_state(sim))
    rows = []
    for row in tracked.values():
        if not isinstance(row, dict):
            continue
        try:
            if int(row.get("opportunity_id", 0) or 0) != target_id:
                continue
        except (TypeError, ValueError):
            continue
        rows.append(row)
    rows.sort(
        key=lambda row: (
            str(row.get("stage_kind", "") or ""),
            str(row.get("property_id", "") or ""),
        )
    )
    return tuple(rows)


def _terminal_entries(state):
    if not isinstance(state, dict):
        return ()
    rows = []
    for bucket in ("completed", "failed"):
        entries = state.get(bucket)
        if not isinstance(entries, list):
            continue
        rows.extend(entry for entry in entries if isinstance(entry, dict))
    return tuple(rows)


def _observer_key(observer_eid):
    try:
        return str(int(observer_eid))
    except (TypeError, ValueError):
        return ""


def _normalize_awareness(value):
    awareness = str(value or "unknown").strip().lower() or "unknown"
    if awareness not in _AWARENESS_RANK:
        return "unknown"
    return awareness


def _normalize_confidence(value, awareness):
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    if confidence <= 0.0:
        if awareness == "confirmed":
            return 0.9
        if awareness == "heard":
            return 0.55
        return 0.0
    return confidence


def _intel_bucket(state, observer_eid, create=False):
    key = _observer_key(observer_eid)
    if not key:
        return None
    buckets = state.get("intel_by_observer")
    if not isinstance(buckets, dict):
        if not create:
            return None
        buckets = {}
        state["intel_by_observer"] = buckets
    bucket = buckets.get(key)
    if not isinstance(bucket, dict):
        if not create:
            return None
        bucket = {}
        buckets[key] = bucket
    return bucket


def _intel_for_opportunity(state, observer_eid, opportunity_id):
    bucket = _intel_bucket(state, observer_eid, create=False)
    if not isinstance(bucket, dict):
        return None
    return bucket.get(str(int(opportunity_id)))


def _active_opportunity_by_id(state, opportunity_id):
    if not isinstance(state, dict):
        return None
    try:
        target_id = int(opportunity_id or 0)
    except (TypeError, ValueError):
        target_id = 0
    if target_id <= 0:
        return None
    active = state.get("active")
    if not isinstance(active, list):
        return None
    for entry in active:
        if not isinstance(entry, dict):
            continue
        if int(entry.get("id", 0) or 0) == target_id:
            return entry
    return None


def _upsert_observer_intel(
    sim,
    state,
    *,
    observer_eid,
    opportunity_id,
    awareness_state,
    confidence=0.0,
    source="unknown",
):
    if observer_eid is None:
        return None
    try:
        opportunity_id = int(opportunity_id)
    except (TypeError, ValueError):
        return None
    if opportunity_id <= 0:
        return None

    awareness = _normalize_awareness(awareness_state)
    confidence = _normalize_confidence(confidence, awareness)
    source = str(source or "unknown").strip().lower() or "unknown"
    bucket = _intel_bucket(state, observer_eid, create=True)
    if not isinstance(bucket, dict):
        return None

    oid_key = str(opportunity_id)
    previous = bucket.get(oid_key) if isinstance(bucket.get(oid_key), dict) else {}
    previous_awareness = _normalize_awareness(previous.get("awareness_state"))
    previous_confidence = _normalize_confidence(previous.get("confidence", 0.0), previous_awareness)
    previous_first_known_tick = _safe_int(previous.get("first_known_tick"), default=-1)

    if _AWARENESS_RANK.get(previous_awareness, 0) > _AWARENESS_RANK.get(awareness, 0):
        awareness = previous_awareness
    confidence = max(previous_confidence, confidence)
    now = int(getattr(sim, "tick", 0))
    if previous_first_known_tick >= 0:
        first_known_tick = previous_first_known_tick
    elif awareness == "unknown":
        first_known_tick = -1
    else:
        first_known_tick = now

    record = {
        "opportunity_id": opportunity_id,
        "awareness_state": awareness,
        "confidence": confidence,
        "source": source,
        "last_updated_tick": now,
    }
    if first_known_tick >= 0:
        record["first_known_tick"] = first_known_tick
    bucket[oid_key] = record

    if observer_eid == getattr(sim, "player_eid", None) and first_known_tick >= 0:
        entry = _active_opportunity_by_id(state, opportunity_id)
        if isinstance(entry, dict):
            if _safe_int(entry.get("first_player_known_tick"), default=-1) < 0:
                entry["first_player_known_tick"] = first_known_tick
            _ensure_lifecycle_fields(sim, entry)
    return record


def reveal_opportunity_to_observer(
    sim,
    observer_eid,
    opportunity_id,
    *,
    awareness_state="heard",
    confidence=0.0,
    source="unknown",
):
    """Record/upgrade observer intel for an opportunity.

    This enables separate knowledge slices for player board vs NPC dialogue.
    """

    state = _state(sim)
    return _upsert_observer_intel(
        sim,
        state,
        observer_eid=observer_eid,
        opportunity_id=opportunity_id,
        awareness_state=awareness_state,
        confidence=confidence,
        source=source,
    )


def opportunity_intel_for_observer(sim, observer_eid, opportunity_id):
    """Return normalized observer intel for a single opportunity, if any."""

    state = _state(sim)
    record = _intel_for_opportunity(state, observer_eid, opportunity_id)
    if not isinstance(record, dict):
        return None
    awareness = _normalize_awareness(record.get("awareness_state"))
    if awareness == "unknown":
        return None
    return {
        "opportunity_id": int(opportunity_id),
        "awareness_state": awareness,
        "confidence": _normalize_confidence(record.get("confidence", 0.0), awareness),
        "source": str(record.get("source", "unknown")).strip().lower() or "unknown",
        "last_updated_tick": _safe_int(record.get("last_updated_tick"), default=0),
    }


def _bootstrap_player_opportunity_intel(sim, state, player_eid, origin_chunk=None):
    if player_eid is None:
        return
    traits = getattr(sim, "world_traits", {}) if sim is not None else {}
    if isinstance(traits, dict) and not bool(traits.get("bootstrap_player_opportunity_intel", True)):
        return
    active = [entry for entry in state.get("active", ()) if isinstance(entry, dict)]
    if not active:
        return
    origin = _chunk_tuple(origin_chunk) or _player_chunk(sim, player_eid)
    ranked = []
    for entry in active:
        chunk = _chunk_tuple(entry.get("chunk")) or origin
        dist = _manhattan(origin, chunk)
        risk = str(entry.get("risk", "low")).strip().lower()
        risk_score = {"calm": 0, "low": 1, "exposed": 2, "hazardous": 3}.get(risk, 1)
        ranked.append((dist, risk_score, int(entry.get("id", 0)), entry))
    ranked.sort(key=lambda row: (row[0], row[1], row[2]))

    for idx, (_dist, _risk_score, _eid, entry) in enumerate(ranked):
        oid = int(entry.get("id", 0))
        if oid <= 0:
            continue
        existing = _intel_for_opportunity(state, player_eid, oid)
        if isinstance(existing, dict) and _normalize_awareness(existing.get("awareness_state")) != "unknown":
            continue
        if idx < 3:
            awareness = "confirmed"
            confidence = 0.95
        elif idx < 5:
            awareness = "heard"
            confidence = 0.62
        else:
            continue
        _upsert_observer_intel(
            sim,
            state,
            observer_eid=player_eid,
            opportunity_id=oid,
            awareness_state=awareness,
            confidence=confidence,
            source="run_brief",
        )


def _observer_intel_records(sim, state, observer_eid, *, viewer_chunk=None, player_eid=None):
    active = [entry for entry in state.get("active", ()) if isinstance(entry, dict)]
    records = []
    for entry in active:
        oid = int(entry.get("id", 0))
        if oid <= 0:
            continue
        intel = _intel_for_opportunity(state, observer_eid, oid)
        if not isinstance(intel, dict):
            # NPCs can have ambient awareness even without explicit intel rows.
            if observer_eid is None:
                continue
            if player_eid is not None and observer_eid == player_eid:
                continue
            seed = f"{getattr(sim, 'seed', 0)}:opp-npc-aware:{observer_eid}:{oid}"
            roll = random.Random(seed).random()
            if roll > 0.7:
                continue
            intel = {
                "opportunity_id": oid,
                "awareness_state": "heard",
                "confidence": 0.58,
                "source": "street_rumor",
                "last_updated_tick": int(getattr(sim, "tick", 0)),
            }
        awareness = _normalize_awareness(intel.get("awareness_state"))
        if awareness == "unknown":
            continue
        confidence = _normalize_confidence(intel.get("confidence", 0.0), awareness)
        source = str(intel.get("source", "unknown")).strip().lower() or "unknown"
        chunk = _chunk_tuple(entry.get("chunk")) or _chunk_tuple(viewer_chunk) or (0, 0)
        dist = _manhattan(_chunk_tuple(viewer_chunk) or (0, 0), chunk)
        risk = str(entry.get("risk", "low")).strip().lower()
        risk_score = {"calm": 0, "low": 1, "exposed": 2, "hazardous": 3}.get(risk, 1)
        records.append((dist, risk_score, int(entry.get("id", 0)), entry, awareness, confidence, source))
    records.sort(key=lambda row: (row[0], row[1], row[2]))
    return records


def _player_chunk(sim, player_eid):
    if sim is None:
        return (0, 0)
    pos = sim.ecs.get(Position).get(player_eid) if player_eid is not None else None
    if pos:
        return (int(sim.chunk_coords(pos.x, pos.y)[0]), int(sim.chunk_coords(pos.x, pos.y)[1]))
    active = getattr(sim, "active_chunk_coord", None)
    if isinstance(active, (list, tuple)) and len(active) == 2:
        return (int(active[0]), int(active[1]))
    return (0, 0)


def _visited_chunks(sim, player_eid, current_chunk=None):
    visited = set()
    raw_by_eid = getattr(sim, "overworld_visit_state_by_eid", {})
    if isinstance(raw_by_eid, dict):
        raw = raw_by_eid.get(player_eid, ())
        if isinstance(raw, (list, tuple, set)):
            for chunk in raw:
                normalized = _chunk_tuple(chunk)
                if normalized:
                    visited.add(normalized)
    if current_chunk:
        visited.add((int(current_chunk[0]), int(current_chunk[1])))
    return visited


def _recent_npc_interactions(sim, freshness_ticks=4):
    active = set()
    if sim is None:
        return frozenset()

    current_tick = int(getattr(sim, "tick", 0))
    traits = getattr(sim, "world_traits", None)
    if isinstance(traits, dict):
        recent = traits.get("recent_npc_interactions")
        if isinstance(recent, dict):
            for raw_eid, raw_tick in list(recent.items()):
                npc_eid = _safe_int(raw_eid, default=0)
                interacted_tick = _safe_int(raw_tick, default=-10_000)
                if npc_eid > 0 and current_tick - interacted_tick <= int(max(1, freshness_ticks)):
                    active.add(npc_eid)

    dialog_ui = getattr(sim, "dialog_ui", None)
    if isinstance(dialog_ui, dict) and bool(dialog_ui.get("open")):
        npc_eid = _safe_int(dialog_ui.get("npc_eid"), default=0)
        if npc_eid > 0:
            active.add(npc_eid)

    return frozenset(active)


def _recent_site_interactions(sim, freshness_ticks=8):
    property_ids = set()
    building_ids = set()
    if sim is None:
        return frozenset(), frozenset()

    current_tick = int(getattr(sim, "tick", 0))
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        return frozenset(), frozenset()

    recent_props = traits.get("recent_property_interactions")
    if isinstance(recent_props, dict):
        for raw_property_id, raw_tick in list(recent_props.items()):
            property_id = str(raw_property_id or "").strip()
            interacted_tick = _safe_int(raw_tick, default=-10_000)
            if property_id and current_tick - interacted_tick <= int(max(1, freshness_ticks)):
                property_ids.add(property_id)

    recent_buildings = traits.get("recent_building_interactions")
    if isinstance(recent_buildings, dict):
        for raw_building_id, raw_tick in list(recent_buildings.items()):
            building_id = str(raw_building_id or "").strip()
            interacted_tick = _safe_int(raw_tick, default=-10_000)
            if building_id and current_tick - interacted_tick <= int(max(1, freshness_ticks)):
                building_ids.add(building_id)

    return frozenset(property_ids), frozenset(building_ids)


def _recent_handoff_site_interactions(sim, freshness_ticks=8):
    property_ids = set()
    building_ids = set()
    if sim is None:
        return frozenset(), frozenset()

    current_tick = int(getattr(sim, "tick", 0))
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        return frozenset(), frozenset()

    recent_props = traits.get("recent_handoff_property_interactions")
    if isinstance(recent_props, dict):
        for raw_property_id, raw_tick in list(recent_props.items()):
            property_id = str(raw_property_id or "").strip()
            interacted_tick = _safe_int(raw_tick, default=-10_000)
            if property_id and current_tick - interacted_tick <= int(max(1, freshness_ticks)):
                property_ids.add(property_id)

    recent_buildings = traits.get("recent_handoff_building_interactions")
    if isinstance(recent_buildings, dict):
        for raw_building_id, raw_tick in list(recent_buildings.items()):
            building_id = str(raw_building_id or "").strip()
            interacted_tick = _safe_int(raw_tick, default=-10_000)
            if building_id and current_tick - interacted_tick <= int(max(1, freshness_ticks)):
                building_ids.add(building_id)

    return frozenset(property_ids), frozenset(building_ids)


def _recent_required_item_transfers(sim, freshness_ticks=12):
    records = []
    if sim is None:
        return tuple(records)

    current_tick = int(getattr(sim, "tick", 0))
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        return tuple(records)

    raw_records = traits.get("recent_required_item_transfers")
    if not isinstance(raw_records, list):
        return tuple(records)

    max_age = int(max(1, freshness_ticks))
    kept = []
    for raw in list(raw_records):
        if not isinstance(raw, dict):
            continue
        tick = _safe_int(raw.get("tick"), default=-10_000)
        if current_tick - tick > max_age:
            continue
        item_id = str(raw.get("item_id", "") or "").strip().lower()
        if not item_id:
            continue
        quantity = max(1, _safe_int(raw.get("quantity"), default=1))
        npc_eid = _safe_int(raw.get("npc_eid"), default=0)
        property_id = str(raw.get("property_id", "") or "").strip()
        building_id = str(raw.get("building_id", "") or "").strip()
        chunk = _chunk_tuple(raw.get("chunk"))
        source = str(raw.get("source", "") or "").strip().lower()
        normalized = {
            "tick": int(tick),
            "item_id": item_id,
            "quantity": int(quantity),
            "npc_eid": int(npc_eid) if npc_eid > 0 else 0,
            "property_id": property_id,
            "building_id": building_id,
            "chunk": chunk,
            "source": source,
        }
        kept.append(normalized)
        records.append(normalized)
    traits["recent_required_item_transfers"] = kept[-20:]
    return tuple(records)


def _recent_opportunity_activities(sim, freshness_ticks=18):
    property_tags = {}
    building_tags = {}
    chunk_tags = {}
    if sim is None:
        return property_tags, building_tags, chunk_tags

    current_tick = int(getattr(sim, "tick", 0))
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        return property_tags, building_tags, chunk_tags

    state = traits.get("recent_opportunity_actions")
    if not isinstance(state, dict):
        return property_tags, building_tags, chunk_tags

    max_age = int(max(1, freshness_ticks))
    for bucket_key, target in (("properties", property_tags), ("buildings", building_tags), ("chunks", chunk_tags)):
        bucket = state.get(bucket_key)
        if not isinstance(bucket, dict):
            continue
        for raw_site_id, raw_tags in list(bucket.items()):
            if bucket_key == "chunks":
                site_id = _chunk_from_key(raw_site_id)
            else:
                site_id = str(raw_site_id or "").strip()
            if not site_id or not isinstance(raw_tags, dict):
                bucket.pop(raw_site_id, None)
                continue
            active_tags = set()
            for raw_tag, raw_tick in list(raw_tags.items()):
                tag = str(raw_tag or "").strip().lower()
                tick = _safe_int(raw_tick, default=-10_000)
                if not tag or current_tick - tick > max_age:
                    raw_tags.pop(raw_tag, None)
                    continue
                active_tags.add(tag)
            if active_tags:
                target[site_id] = frozenset(active_tags)
                continue
            bucket.pop(raw_site_id, None)

    return property_tags, building_tags, chunk_tags


def _normalize_activity_tags(raw_tags):
    if isinstance(raw_tags, str):
        raw_tags = (raw_tags,)
    normalized = []
    for raw_tag in tuple(raw_tags or ()):
        tag = str(raw_tag or "").strip().lower()
        if tag and tag not in normalized:
            normalized.append(tag)
    return tuple(normalized)


def _opportunity_requirements(opportunity):
    if not isinstance(opportunity, dict):
        return {}

    requirements = opportunity.get("requirements")
    if not isinstance(requirements, dict):
        requirements = {}
        opportunity["requirements"] = requirements

    kind = str(opportunity.get("kind", "") or "").strip().lower()
    defaults = OPPORTUNITY_ROUTE_DEFAULTS.get(kind)
    if not isinstance(defaults, dict):
        return requirements

    if (
        _safe_int(requirements.get("interact_npc_eid"), default=0) > 0
        or _safe_int(requirements.get("kill_target_eid"), default=0) > 0
        or str(requirements.get("require_item_id", "")).strip().lower()
    ):
        return requirements

    recent_activity_tags = _normalize_activity_tags(requirements.get("recent_activity_tags"))
    if not recent_activity_tags:
        recent_activity_tags = _normalize_activity_tags(defaults.get("recent_activity_tags"))
        if recent_activity_tags:
            requirements["recent_activity_tags"] = recent_activity_tags

    for flag in ("prefer_storefront", "prefer_finance_services", "prefer_site_services", "prefer_public"):
        if flag not in requirements and flag in defaults:
            requirements[flag] = bool(defaults.get(flag))
    return requirements


def _opportunity_ticks_per_hour(sim):
    world_traits = getattr(sim, "world_traits", {}) if sim is not None else {}
    clock = world_traits.get("clock", {}) if isinstance(world_traits, dict) else {}
    if not isinstance(clock, dict):
        clock = {}
    try:
        ticks_per_hour = int(clock.get("ticks_per_hour", 600))
    except (TypeError, ValueError):
        ticks_per_hour = 600
    return max(1, ticks_per_hour)


def _opportunity_hours_to_ticks(sim, hours):
    try:
        value = float(hours)
    except (TypeError, ValueError):
        value = 0.0
    return max(1, int(round(_opportunity_ticks_per_hour(sim) * max(0.0, value))))


def _opportunity_refill_cooldown_ticks(sim):
    return _opportunity_hours_to_ticks(sim, OPPORTUNITY_REFILL_COOLDOWN_HOURS)


def _opportunity_terminal_refill_delay_ticks(sim):
    return _opportunity_hours_to_ticks(sim, OPPORTUNITY_TERMINAL_REFILL_DELAY_HOURS)


def _active_opportunity_count(state):
    if not isinstance(state, dict):
        return 0
    return sum(1 for entry in state.get("active", ()) if isinstance(entry, dict))


def _record_opportunity_refill(state, sim, reason):
    if not isinstance(state, dict):
        return state
    tick = _safe_int(getattr(sim, "tick", 0), default=0)
    reason_key = str(reason or "periodic").strip().lower() or "periodic"
    state["last_refill_tick"] = tick
    state["last_refill_reason"] = reason_key
    state["pending_refill_reason"] = ""
    state["next_refill_tick"] = tick + _opportunity_refill_cooldown_ticks(sim)
    return state


def _schedule_opportunity_refill(state, sim, reason, delay_ticks):
    if not isinstance(state, dict):
        return state
    tick = _safe_int(getattr(sim, "tick", 0), default=0)
    try:
        delay = max(1, int(delay_ticks))
    except (TypeError, ValueError):
        delay = 1
    next_tick = tick + delay
    current_next = _safe_int(state.get("next_refill_tick"), default=0)
    if current_next <= tick or current_next > next_tick:
        state["next_refill_tick"] = next_tick
    state["pending_refill_reason"] = str(reason or "periodic").strip().lower() or "periodic"
    return state


def _schedule_terminal_opportunity_refill(state, sim):
    """Schedule quiet board turnover after a terminal opportunity change."""
    if not isinstance(state, dict):
        return False
    if _active_opportunity_count(state) >= MIN_ACTIVE_OPPORTUNITIES:
        return False
    _schedule_opportunity_refill(
        state,
        sim,
        "terminal",
        _opportunity_terminal_refill_delay_ticks(sim),
    )
    return True


def _opportunity_has_readable_urgency(opportunity):
    if not isinstance(opportunity, dict):
        return False
    requirements = _opportunity_requirements(opportunity)
    policy = opportunity.get("failure_policy")
    if not isinstance(policy, dict):
        policy = {}

    for raw in (
        opportunity.get("urgency"),
        opportunity.get("time_pressure"),
        requirements.get("urgency"),
        requirements.get("time_pressure"),
        policy.get("urgency"),
    ):
        token = str(raw or "").strip().lower()
        if token in {"high", "urgent", "immediate", "time_sensitive"}:
            return True

    if bool(opportunity.get("readable_urgency")) or bool(requirements.get("readable_urgency")):
        return True

    readable_text = " ".join(
        str(opportunity.get(field, "") or "").strip().lower()
        for field in ("title", "summary")
    )
    return any(keyword in readable_text for keyword in _OPPORTUNITY_URGENCY_KEYWORDS)


def _default_opportunity_expire_ticks(sim, opportunity):
    requirements = _opportunity_requirements(opportunity)
    urgent = _opportunity_has_readable_urgency(opportunity)
    if bool(requirements.get("player_accepted")):
        duration_hours = ACCEPTED_URGENT_OPPORTUNITY_EXPIRE_HOURS if urgent else ACCEPTED_OPPORTUNITY_EXPIRE_HOURS
    else:
        duration_hours = URGENT_OPPORTUNITY_EXPIRE_HOURS if urgent else BASE_OPPORTUNITY_EXPIRE_HOURS

    source = str((opportunity or {}).get("source", "") or "").strip().lower()
    if source in {"contact", "intel"}:
        duration_hours += 6.0
    elif source in {"property_service", "economy_profile"}:
        duration_hours += 2.0

    if str((opportunity or {}).get("kind", "") or "").strip().lower() == "contract_kill":
        duration_hours += 8.0

    if str(requirements.get("require_item_id", "") or "").strip().lower():
        duration_hours += 4.0
    if bool(requirements.get("provide_item")):
        duration_hours += 6.0

    risk = str((opportunity or {}).get("risk", "") or "").strip().lower()
    if risk == "exposed":
        duration_hours += 2.0
    elif risk == "hazardous":
        duration_hours += 4.0

    chunk = _chunk_tuple((opportunity or {}).get("chunk"))
    origin = _chunk_tuple((opportunity or {}).get("origin_chunk"))
    if chunk and origin:
        distance = _manhattan(origin, chunk)
        duration_hours += min(
            EXPIRE_DISTANCE_BONUS_CAP_HOURS,
            max(0, int(distance)) * EXPIRE_DISTANCE_BONUS_HOURS_PER_CHUNK,
        )

    ticks_per_hour = _opportunity_ticks_per_hour(sim)
    minimum_hours = URGENT_OPPORTUNITY_EXPIRE_HOURS if urgent else BASE_OPPORTUNITY_EXPIRE_HOURS
    return max(int(minimum_hours * ticks_per_hour), int(duration_hours * ticks_per_hour))


def _ensure_lifecycle_fields(sim, opportunity):
    if sim is None or not isinstance(opportunity, dict):
        return opportunity

    now = int(getattr(sim, "tick", 0))
    requirements = _opportunity_requirements(opportunity)
    kind = str(opportunity.get("kind", "") or "").strip().lower()
    policy = opportunity.get("failure_policy")
    if not isinstance(policy, dict):
        policy = {}
        opportunity["failure_policy"] = policy

    if bool(requirements.get("provide_item")):
        policy.setdefault("fail_on_missing_provided_item", True)
    if bool(requirements.get("player_accepted")):
        policy.setdefault("fail_on_legal_compromise", True)
        if _safe_int(opportunity.get("accepted_tick"), default=-1) < 0:
            opportunity["accepted_tick"] = now
    if (
        kind != "contract_kill"
        and (
            _safe_int(requirements.get("interact_npc_eid"), default=0) > 0
            or _safe_int(requirements.get("pickup_interact_npc_eid"), default=0) > 0
            or _safe_int(requirements.get("bounty_target_eid"), default=0) > 0
        )
    ):
        policy.setdefault("fail_on_target_killed", True)

    origin = _chunk_tuple(getattr(sim, "world_traits", {}).get("origin_chunk")) if isinstance(getattr(sim, "world_traits", None), dict) else None
    if origin and "origin_chunk" not in opportunity:
        opportunity["origin_chunk"] = origin

    current_expire_tick = _safe_int(opportunity.get("expire_tick"), default=0)
    if bool(requirements.get("strict_deadline")) and current_expire_tick > 0:
        opportunity["expire_version"] = _OPPORTUNITY_EXPIRE_VERSION
        return opportunity

    desired_duration = _default_opportunity_expire_ticks(sim, opportunity)
    accepted_tick = _safe_int(opportunity.get("accepted_tick"), default=-1)
    seed_tick = _safe_int(opportunity.get("seed_tick"), default=-1)
    first_player_known_tick = _safe_int(opportunity.get("first_player_known_tick"), default=-1)
    if accepted_tick >= 0 and bool(requirements.get("player_accepted")):
        anchor_tick = accepted_tick
    elif first_player_known_tick >= 0:
        anchor_tick = first_player_known_tick
    else:
        anchor_tick = seed_tick
    if anchor_tick < 0:
        anchor_tick = now
    desired_expire_tick = anchor_tick + desired_duration

    expire_version = _safe_int(opportunity.get("expire_version"), default=0)
    if current_expire_tick <= 0:
        opportunity["expire_tick"] = desired_expire_tick
    elif expire_version < _OPPORTUNITY_EXPIRE_VERSION:
        opportunity["expire_tick"] = max(current_expire_tick, desired_expire_tick)
    opportunity["expire_version"] = _OPPORTUNITY_EXPIRE_VERSION

    return opportunity


def _player_site_state(sim, player_eid):
    pos = sim.ecs.get(Position).get(player_eid) if sim is not None and player_eid is not None else None
    if not pos:
        return {
            "current_pos": None,
            "current_property_id": "",
            "current_building_id": "",
        }

    current_prop = property_covering(sim, pos.x, pos.y, pos.z) if sim is not None else None
    current_property_id = str((current_prop or {}).get("id", "")).strip()
    current_building_id = ""
    if sim is not None and hasattr(sim, "structure_at"):
        current_building_id = building_id_from_structure(sim.structure_at(pos.x, pos.y, pos.z))
    if not current_building_id:
        current_building_id = building_id_from_property(current_prop)

    return {
        "current_pos": (int(pos.x), int(pos.y), int(pos.z)),
        "current_property_id": current_property_id,
        "current_building_id": current_building_id,
    }


def _player_metrics(sim, player_eid):
    assets = sim.ecs.get(PlayerAssets).get(player_eid) if sim is not None else None
    finance = sim.ecs.get(FinancialProfile).get(player_eid) if sim is not None else None
    ledger = sim.ecs.get(ContactLedger).get(player_eid) if sim is not None else None
    knowledge = sim.ecs.get(PropertyKnowledge).get(player_eid) if sim is not None else None
    inventory = sim.ecs.get(Inventory).get(player_eid) if sim is not None else None
    current_chunk = _player_chunk(sim, player_eid)
    visited_chunks = _visited_chunks(sim, player_eid, current_chunk=current_chunk)
    site_state = _player_site_state(sim, player_eid)
    wallet = _safe_int(getattr(assets, "credits", 0), default=0)
    bank = _safe_int(getattr(finance, "bank_balance", 0), default=0)
    reserve = max(0, wallet + bank)
    contact_count = len(getattr(ledger, "by_property", {}) or {})
    intel_leads = len(getattr(knowledge, "known", {}) or {})
    traits = getattr(sim, "world_traits", None) if sim is not None else None
    if not isinstance(traits, dict):
        traits = {}
    killed_raw = traits.get("killed_npc_eids", ())
    killed_eids = frozenset(
        int(e) for e in (killed_raw if isinstance(killed_raw, (list, tuple, set)) else ())
        if e is not None
    )
    recent_property_ids, recent_building_ids = _recent_site_interactions(sim)
    recent_handoff_property_ids, recent_handoff_building_ids = _recent_handoff_site_interactions(sim)
    recent_required_item_transfers = _recent_required_item_transfers(sim)
    recent_activity_property_tags, recent_activity_building_tags, recent_activity_chunk_tags = _recent_opportunity_activities(sim)
    justice_snapshot = _justice_snapshot(sim, player_eid) if sim is not None and player_eid is not None else {}
    held_property = _justice_held_property_snapshot(sim, player_eid) if sim is not None and player_eid is not None else {}
    booking_seizure = _justice_booking_seizure_snapshot(sim, player_eid) if sim is not None and player_eid is not None else {}
    return {
        "wallet_credits": wallet,
        "bank_credits": bank,
        "reserve_credits": reserve,
        "contact_count": int(contact_count),
        "intel_leads": int(intel_leads),
        "current_chunk": current_chunk,
        "visited_chunks": visited_chunks,
        "current_pos": site_state.get("current_pos"),
        "current_property_id": str(site_state.get("current_property_id", "") or "").strip(),
        "current_building_id": str(site_state.get("current_building_id", "") or "").strip(),
        "recent_npc_eids": _recent_npc_interactions(sim),
        "recent_property_ids": recent_property_ids,
        "recent_building_ids": recent_building_ids,
        "recent_handoff_property_ids": recent_handoff_property_ids,
        "recent_handoff_building_ids": recent_handoff_building_ids,
        "recent_required_item_transfers": recent_required_item_transfers,
        "recent_activity_property_tags": recent_activity_property_tags,
        "recent_activity_building_tags": recent_activity_building_tags,
        "recent_activity_chunk_tags": recent_activity_chunk_tags,
        "inventory": inventory,
        "inventory_counts": _inventory_counts(inventory),
        "killed_npc_eids": killed_eids,
        "justice_snapshot": justice_snapshot if isinstance(justice_snapshot, dict) else {},
        "held_property": held_property if isinstance(held_property, dict) else {},
        "booking_seizure": booking_seizure if isinstance(booking_seizure, dict) else {},
    }


def _opportunity_tagged_item_quantity(inventory, opportunity_id, item_id):
    if not inventory:
        return 0
    target_item_id = str(item_id or "").strip().lower()
    target_opportunity_id = _safe_int(opportunity_id, default=0)
    if target_opportunity_id <= 0 or not target_item_id:
        return 0

    total = 0
    for entry in list(getattr(inventory, "items", ()) or ()):
        if str(entry.get("item_id", "")).strip().lower() != target_item_id:
            continue
        metadata = entry.get("metadata", {}) if isinstance(entry.get("metadata"), dict) else {}
        if _safe_int(metadata.get("quest_opportunity_id"), default=0) != target_opportunity_id:
            continue
        total += max(0, _safe_int(entry.get("quantity"), default=0))
    return total


def _recent_required_item_transfer_for_item(metrics, *, item_id="", min_tick=0):
    item_key = str(item_id or "").strip().lower()
    if not item_key:
        return None
    records = (
        metrics.get("recent_required_item_transfers", ())
        if isinstance(metrics.get("recent_required_item_transfers", ()), (list, tuple))
        else ()
    )
    cutoff_tick = int(max(0, _safe_int(min_tick, default=0)))
    for raw in reversed(list(records)):
        if not isinstance(raw, dict):
            continue
        if str(raw.get("item_id", "")).strip().lower() != item_key:
            continue
        if _safe_int(raw.get("tick"), default=-10_000) < cutoff_tick:
            continue
        return raw
    return None


def _required_item_label_for_opportunity(opportunity):
    requirements = _opportunity_requirements(opportunity)
    item_id = str(requirements.get("require_item_id", "")).strip().lower()
    return str(requirements.get("item_label", "")).strip() or _item_label(item_id)


def _matching_required_item_entries(opportunity, entries):
    if not isinstance(opportunity, dict):
        return ()
    requirements = _opportunity_requirements(opportunity)
    item_id = str(requirements.get("require_item_id", "")).strip().lower()
    required_qty = max(1, _safe_int(requirements.get("require_item_qty"), default=1))
    if not item_id:
        return ()

    opportunity_id = _safe_int(opportunity.get("id"), default=0)
    require_tagged = bool(requirements.get("provide_item")) or _safe_int(opportunity.get("provided_item_issued_tick"), default=-1) >= 0
    total = 0
    matched = []
    for raw in tuple(entries or ()):
        if not isinstance(raw, dict):
            continue
        if str(raw.get("item_id", "")).strip().lower() != item_id:
            continue
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        if require_tagged and _safe_int(metadata.get("quest_opportunity_id"), default=0) != opportunity_id:
            continue
        matched.append(dict(raw))
        total += max(0, _safe_int(raw.get("quantity"), default=0))
        if total >= required_qty:
            return tuple(matched)
    return ()


def _required_item_seizure_reason(opportunity, *, site_name="", during_booking=False):
    item_label = _required_item_label_for_opportunity(opportunity)
    requirements = _opportunity_requirements(opportunity)
    provided = bool(requirements.get("provide_item")) or _safe_int(opportunity.get("provided_item_issued_tick"), default=-1) >= 0
    item_phrase = f"the provided {item_label}" if provided else item_label
    site_name = str(site_name or "").strip()
    if during_booking:
        site = site_name or "the justice booking"
        return f"{site} seized {item_phrase} during booking"
    if site_name:
        return f"{site_name} is holding {item_phrase}"
    return f"justice seized {item_phrase}"


def _site_label_from_requirement(sim, requirements, *, property_key="property_id", building_key="building_id", name_key="property_name"):
    requirements = requirements if isinstance(requirements, dict) else {}
    name = str(requirements.get(name_key, "")).strip()
    if name:
        return name

    property_id = str(requirements.get(property_key, "")).strip()
    if property_id and sim is not None and hasattr(sim, "properties"):
        prop = sim.properties.get(property_id)
        if isinstance(prop, dict):
            return _property_label(prop, property_id)

    building_id = str(requirements.get(building_key, "")).strip()
    if building_id and sim is not None and hasattr(sim, "properties"):
        for prop in getattr(sim, "properties", {}).values():
            if building_id_from_property(prop) == building_id:
                return _property_label(prop, prop.get("id") if isinstance(prop, dict) else building_id)
    return ""


def _site_phrase(label):
    label = str(label or "").strip()
    return f" at {label}" if label else ""


def _resolve_required_property(sim, requirements, *, property_key="property_id", building_key="building_id"):
    requirements = requirements if isinstance(requirements, dict) else {}
    if sim is None or not hasattr(sim, "properties"):
        return None

    property_id = str(requirements.get(property_key, "")).strip()
    if property_id:
        prop = resolve_property_record(sim, property_id, include_saved=True)
        if isinstance(prop, dict):
            return prop

    building_id = str(requirements.get(building_key, "")).strip()
    if building_id:
        for prop in getattr(sim, "properties", {}).values():
            if building_id_from_property(prop) == building_id:
                return prop
        saved_states = getattr(sim, "chunk_saved_states", {})
        if isinstance(saved_states, dict):
            for chunk_state in saved_states.values():
                properties = chunk_state.get("properties", {}) if isinstance(chunk_state, dict) else {}
                if not isinstance(properties, dict):
                    continue
                for prop in properties.values():
                    if building_id_from_property(prop) == building_id:
                        return prop
    return None


def _property_supported_activity_tags(prop):
    if not isinstance(prop, dict):
        return set()
    supported = set()
    if property_is_storefront(prop):
        supported.update({"trade", "contact"})
    if property_is_public(prop):
        supported.add("contact")

    finance_services = {
        str(service).strip().lower()
        for service in finance_services_for_property(prop)
        if str(service).strip()
    }
    if finance_services:
        supported.update({"finance", "contact"})

    site_services = {
        str(service).strip().lower()
        for service in site_services_for_property(prop)
        if str(service).strip()
    }
    if site_services:
        supported.update({"service", "contact"})
    if "intel" in site_services:
        supported.add("intel")
    if property_focus_position(prop) is not None:
        supported.add("stakeout")
    return supported


def _activity_lane_closed_reason(site_label, tags):
    site_label = str(site_label or "").strip() or "the site"
    ordered = [str(tag).strip().lower() for tag in tuple(tags or ()) if str(tag).strip()]
    tag_set = set(ordered)
    if "finance" in tag_set:
        return f"{site_label} is no longer running the finance lane this lead depends on"
    if "trade" in tag_set:
        return f"{site_label} is no longer running the counter this lead depends on"
    if "service" in tag_set:
        return f"{site_label} is no longer offering the service this lead depends on"
    if "contact" in tag_set:
        return f"{site_label} is no longer taking the kind of walk-in contact this lead depends on"
    if "intel" in tag_set:
        return f"the intel lane at {site_label} dried up"
    if "stakeout" in tag_set:
        return f"the watch angle around {site_label} went dead"
    return f"{site_label} is no longer supporting the work this lead depends on"


def _expired_failure_reason(sim, opportunity):
    if sim is None or not isinstance(opportunity, dict):
        return "the window expired"

    requirements = _opportunity_requirements(opportunity)
    kind = str((opportunity or {}).get("kind", "")).strip().lower()
    tags = set(_normalize_activity_tags(requirements.get("recent_activity_tags")))
    item_id = str(requirements.get("require_item_id", "")).strip().lower()
    item_label = _required_item_label_for_opportunity(opportunity) if item_id else ""
    acquisition_hint = str(requirements.get("acquisition_hint", "")).strip().lower()
    contact_name = str(requirements.get("interact_npc_name", "")).strip()
    pickup_contact_name = str(requirements.get("pickup_interact_npc_name", "")).strip()

    visit_label = _site_label_from_requirement(sim, requirements)
    delivery_label = _site_label_from_requirement(
        sim,
        requirements,
        property_key="delivery_property_id",
        building_key="delivery_building_id",
        name_key="delivery_property_name",
    )
    pickup_label = _site_label_from_requirement(
        sim,
        requirements,
        property_key="pickup_property_id",
        building_key="pickup_building_id",
        name_key="pickup_property_name",
    )
    primary_label = visit_label or delivery_label or pickup_label

    if kind in {"watch_post", "relay_watch", "sightline_check", "intel_scout"} or "stakeout" in tags:
        return f"the watch window{_site_phrase(primary_label)} closed"

    if kind in {"records_pull", "paper_trail"}:
        return f"the paper trail{_site_phrase(primary_label)} cooled off"
    if kind == "claims_chase":
        return f"the claims trail{_site_phrase(primary_label)} cooled off"
    if kind == "debt_marker":
        return f"the debt trail{_site_phrase(primary_label)} cooled off"

    if "discovery_salvage" in tags or kind in {"salvage_sweep", "parts_recovery", "yard_strip"}:
        return f"the salvage{_site_phrase(primary_label)} was stripped clean"
    if "discovery_supplies" in tags or kind == "refuge_resupply":
        return f"the cache{_site_phrase(primary_label)} was stripped clean"
    if "discovery_water" in tags or kind in {"water_run", "spring_run"}:
        return f"the water route{_site_phrase(primary_label)} ran dry"
    if "discovery_landmark" in tags or kind == "landmark_survey":
        return f"the survey window{_site_phrase(primary_label)} closed"

    if kind in {"distance_pickup", "dead_drop_return", "tool_pickup", "supply_grab", "route_stash"} or acquisition_hint == "pickup":
        if pickup_contact_name:
            return f"{pickup_contact_name} stopped holding the pickup"
        if pickup_label:
            return f"the pickup route through {pickup_label} went stale"
        if item_label:
            return f"the pickup route for {item_label} went stale"
        return "the pickup route went stale"

    if kind in {"distance_delivery", "distance_delivery_procure", "medical_drop"} or item_id:
        if contact_name:
            return f"{contact_name} stopped holding the handoff"
        if delivery_label:
            return f"the handoff window at {delivery_label} closed"
        if item_label:
            return f"the handoff window for {item_label} closed"
        return "the handoff window closed"

    if kind in {
        "contact_run",
        "missing_person",
        "property_dispute",
        "service_friction",
        "lead_followup",
        "local_lead",
        "layover_shuffle",
        "district_contract",
    } or "contact" in tags:
        if contact_name:
            return f"{contact_name} stopped taking the meeting"
        return f"the local contact window{_site_phrase(primary_label)} went cold"

    if kind in {"trade_loop", "backroom_buyback", "supply_shortage"} or "trade" in tags:
        return f"the buyer interest{_site_phrase(primary_label)} cooled off"

    if kind in {"shelter_stop", "field_repair_call"} or "service" in tags:
        return f"the service window{_site_phrase(primary_label)} closed"

    return "the window expired"


def _npc_custody_record(sim, npc_eid):
    if sim is None or npc_eid is None:
        return {}
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        return {}
    justice_state = traits.get("criminal_justice")
    if not isinstance(justice_state, dict):
        return {}
    records = justice_state.get("npc_custody")
    if not isinstance(records, dict):
        return {}
    record = records.get(str(int(npc_eid)))
    return record if isinstance(record, dict) else {}


def _named_contact_unavailable_failure_detail(sim, opportunity, metrics):
    if sim is None or not isinstance(opportunity, dict):
        return None
    killed_eids = metrics.get("killed_npc_eids", frozenset()) if isinstance(metrics, dict) else frozenset()
    positions = sim.ecs.get(Position)
    identities = sim.ecs.get(CreatureIdentity)
    for target_eid, target_name, stage in _opportunity_target_specs(opportunity):
        if target_eid in killed_eids:
            continue
        record = _npc_custody_record(sim, target_eid)
        if bool(record.get("active", False)):
            if stage == "pickup":
                reason = f"{target_name} is in custody and missed the pickup"
            else:
                reason = f"{target_name} is in custody and missed the handoff"
            return {
                "failure_code": "contact_unavailable",
                "failure_reason": reason,
            }
        if positions.get(target_eid) is None and identities.get(target_eid) is None:
            if stage == "pickup":
                reason = f"{target_name} dropped out before the pickup"
            else:
                reason = f"{target_name} dropped out before the handoff"
            return {
                "failure_code": "contact_unavailable",
                "failure_reason": reason,
            }
    return None


def _anchor_unavailable_failure_detail(sim, opportunity):
    if sim is None or not isinstance(opportunity, dict):
        return None

    requirements = _opportunity_requirements(opportunity)
    require_item_id = str(requirements.get("require_item_id", "")).strip().lower()
    interact_npc_eid = _safe_int(requirements.get("interact_npc_eid"), default=0)
    recent_activity_tags = _normalize_activity_tags(requirements.get("recent_activity_tags"))

    pickup_prop = _resolve_required_property(
        sim,
        requirements,
        property_key="pickup_property_id",
        building_key="pickup_building_id",
    )
    pickup_label = _site_label_from_requirement(
        sim,
        requirements,
        property_key="pickup_property_id",
        building_key="pickup_building_id",
        name_key="pickup_property_name",
    )
    if (str(requirements.get("pickup_property_id", "")).strip() or str(requirements.get("pickup_building_id", "")).strip()) and pickup_prop is None:
        if pickup_label:
            reason = f"{pickup_label} is no longer holding the pickup"
        else:
            reason = "the pickup site is no longer available"
        return {
            "failure_code": "pickup_unavailable",
            "failure_reason": reason,
        }

    delivery_prop = _resolve_required_property(
        sim,
        requirements,
        property_key="delivery_property_id",
        building_key="delivery_building_id",
    )
    delivery_label = _site_label_from_requirement(
        sim,
        requirements,
        property_key="delivery_property_id",
        building_key="delivery_building_id",
        name_key="delivery_property_name",
    )
    if (str(requirements.get("delivery_property_id", "")).strip() or str(requirements.get("delivery_building_id", "")).strip()) and delivery_prop is None:
        if delivery_label:
            reason = f"{delivery_label} is no longer taking the handoff"
        else:
            reason = "the handoff site is no longer available"
        return {
            "failure_code": "handoff_unavailable",
            "failure_reason": reason,
        }

    target_prop = _resolve_required_property(sim, requirements)
    target_label = _site_label_from_requirement(sim, requirements)
    if (str(requirements.get("property_id", "")).strip() or str(requirements.get("building_id", "")).strip()) and target_prop is None:
        label = target_label or "the target site"
        return {
            "failure_code": "site_unavailable",
            "failure_reason": f"{label} is no longer available",
        }

    if interact_npc_eid > 0 or require_item_id or not recent_activity_tags or target_prop is None:
        return None

    if any(tag == "discovery" or tag.startswith("discovery_") for tag in recent_activity_tags):
        return None

    supported_tags = _property_supported_activity_tags(target_prop)
    if supported_tags.intersection(recent_activity_tags):
        return None

    return {
        "failure_code": "activity_unavailable",
        "failure_reason": _activity_lane_closed_reason(target_label or _property_label(target_prop), recent_activity_tags),
    }


def _matches_property_target(sim, metrics, property_id):
    property_id = str(property_id or "").strip()
    if not property_id or sim is None:
        return False

    if str(metrics.get("current_property_id", "") or "").strip() == property_id:
        return True

    target = sim.properties.get(property_id) if hasattr(sim, "properties") else None
    if not isinstance(target, dict):
        return False

    target_building_id = building_id_from_property(target)
    current_building_id = str(metrics.get("current_building_id", "") or "").strip()
    if target_building_id and current_building_id and target_building_id == current_building_id:
        return True

    current_pos = metrics.get("current_pos")
    focus = property_focus_position(target)
    if current_pos and focus and int(focus[2]) == int(current_pos[2]):
        return _manhattan(
            (int(current_pos[0]), int(current_pos[1])),
            (int(focus[0]), int(focus[1])),
        ) <= 1
    return False


def _matches_building_target(sim, metrics, building_id):
    building_id = str(building_id or "").strip()
    if not building_id or sim is None:
        return False

    if str(metrics.get("current_building_id", "") or "").strip() == building_id:
        return True

    current_pos = metrics.get("current_pos")
    if not current_pos or not hasattr(sim, "properties"):
        return False

    for prop in list(sim.properties.values()):
        if building_id_from_property(prop) != building_id:
            continue
        focus = property_focus_position(prop)
        if focus and int(focus[2]) == int(current_pos[2]):
            if _manhattan(
                (int(current_pos[0]), int(current_pos[1])),
                (int(focus[0]), int(focus[1])),
            ) <= 1:
                return True
    return False


def _matches_site_requirement(sim, metrics, *, property_id=None, building_id=None):
    property_id = str(property_id or "").strip()
    building_id = str(building_id or "").strip()
    if property_id and _matches_property_target(sim, metrics, property_id):
        return True
    if building_id and _matches_building_target(sim, metrics, building_id):
        return True
    return False


def _matches_recent_site_interaction(metrics, *, property_id=None, building_id=None):
    property_id = str(property_id or "").strip()
    building_id = str(building_id or "").strip()
    recent_property_ids = set(metrics.get("recent_property_ids", ()) or ())
    recent_building_ids = set(metrics.get("recent_building_ids", ()) or ())
    if property_id and property_id in recent_property_ids:
        return True
    if building_id and building_id in recent_building_ids:
        return True
    return False


def _matches_recent_handoff_site_interaction(metrics, *, property_id=None, building_id=None):
    property_id = str(property_id or "").strip()
    building_id = str(building_id or "").strip()
    recent_property_ids = set(metrics.get("recent_handoff_property_ids", ()) or ())
    recent_building_ids = set(metrics.get("recent_handoff_building_ids", ()) or ())
    if property_id and property_id in recent_property_ids:
        return True
    if building_id and building_id in recent_building_ids:
        return True
    return False


def _match_recent_opportunity_activity(metrics, *, property_id=None, building_id=None, chunk=None, accepted_tags=()):
    property_id = str(property_id or "").strip()
    building_id = str(building_id or "").strip()
    chunk = _chunk_tuple(chunk)
    tags = _normalize_activity_tags(accepted_tags)
    if not tags:
        return ""

    property_tags = (
        metrics.get("recent_activity_property_tags", {})
        if isinstance(metrics.get("recent_activity_property_tags", {}), dict)
        else {}
    )
    building_tags = (
        metrics.get("recent_activity_building_tags", {})
        if isinstance(metrics.get("recent_activity_building_tags", {}), dict)
        else {}
    )
    chunk_tags = (
        metrics.get("recent_activity_chunk_tags", {})
        if isinstance(metrics.get("recent_activity_chunk_tags", {}), dict)
        else {}
    )

    if property_id:
        current_tags = set(property_tags.get(property_id, ()) or ())
        for tag in tags:
            if tag in current_tags:
                return tag
    if building_id:
        current_tags = set(building_tags.get(building_id, ()) or ())
        for tag in tags:
            if tag in current_tags:
                return tag
    if chunk:
        current_tags = set(chunk_tags.get(chunk, ()) or ())
        for tag in tags:
            if tag in current_tags:
                return tag
    return ""


def _matching_recent_required_item_transfer(
    metrics,
    *,
    item_id,
    quantity=1,
    npc_eid=0,
    property_id="",
    building_id="",
    chunk=None,
):
    item_id = str(item_id or "").strip().lower()
    property_id = str(property_id or "").strip()
    building_id = str(building_id or "").strip()
    chunk = _chunk_tuple(chunk)
    needed_qty = max(1, _safe_int(quantity, default=1))
    records = (
        metrics.get("recent_required_item_transfers", ())
        if isinstance(metrics.get("recent_required_item_transfers", ()), (list, tuple))
        else ()
    )
    total = 0
    matched = None
    for raw in reversed(tuple(records)):
        if not isinstance(raw, dict):
            continue
        if str(raw.get("item_id", "") or "").strip().lower() != item_id:
            continue
        record_npc_eid = _safe_int(raw.get("npc_eid"), default=0)
        record_property_id = str(raw.get("property_id", "") or "").strip()
        record_building_id = str(raw.get("building_id", "") or "").strip()
        record_chunk = _chunk_tuple(raw.get("chunk"))

        scope_matched = False
        if npc_eid > 0 and record_npc_eid == int(npc_eid):
            scope_matched = True
        if property_id and record_property_id == property_id:
            scope_matched = True
        if building_id and record_building_id == building_id:
            scope_matched = True
        if npc_eid <= 0 and not property_id and not building_id:
            scope_matched = True
        if not scope_matched:
            continue
        if chunk and record_chunk and record_chunk != chunk:
            continue

        total += max(0, _safe_int(raw.get("quantity"), default=0))
        if matched is None:
            matched = dict(raw)
        if total >= needed_qty:
            break
    if matched is None or total < needed_qty:
        return None
    matched["quantity"] = int(total)
    return matched


def _opportunity_activity_instruction(requirements):
    requirements = requirements if isinstance(requirements, dict) else {}
    tags = set(_normalize_activity_tags(requirements.get("recent_activity_tags")))
    discovery_tags = {tag for tag in tags if tag == "discovery" or tag.startswith("discovery_")}
    if not tags:
        return "Interact there to complete the job."
    if tags == {"contact"}:
        return "Talk to someone there to work the lead."
    if discovery_tags and discovery_tags == tags:
        return "Survey the chunk itself to work the lead."
    if discovery_tags and tags <= (discovery_tags | {"intel", "stakeout"}):
        return "Survey the chunk or pull a quiet read there to work the lead."
    if tags <= {"stakeout", "intel"}:
        if "stakeout" in tags:
            return "Hold a quiet watch or pull intel there to work the lead."
        return "Pull intel there to work the lead."
    if tags & {"contact"} and tags & {"service", "trade", "finance"}:
        return "Talk to someone there or work the local counter/services to move the job."
    if tags & {"contact"} and tags & {"intel", "stakeout"}:
        return "Talk to someone there or work the lead quietly on site."
    if tags & {"finance"} and not (tags & {"contact", "intel", "stakeout"}):
        return "Work the local finance desk there to move the job."
    if tags & {"service", "trade", "finance"} and not (tags & {"contact", "intel", "stakeout"}):
        return "Use the local counter or services there to work the job."
    if tags & {"intel", "stakeout"} and tags & {"service", "trade", "finance"}:
        return "Work the site through intel, a quiet watch, or local services."
    return "Work the site there to complete the job."


def _property_archetype(prop):
    metadata = prop.get("metadata") if isinstance((prop or {}).get("metadata"), dict) else {}
    return str(metadata.get("archetype", "") or "").strip().lower()


def _site_task_expected(requirements):
    requirements = requirements if isinstance(requirements, dict) else {}
    if _safe_int(requirements.get("kill_target_eid"), default=0) > 0:
        return False
    if _safe_int(requirements.get("interact_npc_eid"), default=0) > 0:
        return False
    if max(0, _safe_int(requirements.get("contact_count"), default=0)) > 0:
        return False
    if max(0, _safe_int(requirements.get("intel_leads"), default=0)) > 0:
        return False
    if max(0, _safe_int(requirements.get("reserve_credits"), default=0)) > 0:
        return False
    if str(requirements.get("require_item_id", "")).strip().lower():
        return True
    if any(
        str(requirements.get(key, "")).strip()
        for key in ("property_id", "building_id", "property_name", "site_kind", "site_id")
    ):
        return True
    return _chunk_tuple(requirements.get("visit_chunk")) is not None


def _chunk_features(chunk):
    has_storefront = False
    has_finance = False
    site_services = set()
    for block in chunk.get("blocks", ()):
        if not isinstance(block, dict):
            continue
        for building in block.get("buildings", ()):
            if not isinstance(building, dict):
                continue
            archetype = str(building.get("archetype", "")).strip().lower()
            if bool(building.get("is_storefront")):
                has_storefront = True
            if archetype in FINANCE_ARCHETYPES:
                has_finance = True

    for site in chunk.get("sites", ()):
        if not isinstance(site, dict):
            continue
        profile = site_gameplay_profile(site)
        if bool(profile.get("is_storefront")):
            has_storefront = True
        for service in profile.get("site_services", ()):
            service = str(service).strip().lower()
            if service:
                site_services.add(service)
        for service in profile.get("finance_services", ()):
            service = str(service).strip().lower()
            if service:
                has_finance = True

    return {
        "has_storefront": has_storefront,
        "has_finance": has_finance,
        "site_services": tuple(sorted(site_services)),
    }


def _pick_courier_item(rng):
    pool = _required_item_pool(COURIER_ITEM_POOL)
    if not pool:
        pool = _required_item_pool(sorted(ITEM_CATALOG.keys()))
    return str(rng.choice(pool)).strip().lower()


def _discovery_item_pool(discovery, fallback_ids):
    discovery = discovery if isinstance(discovery, dict) else {}
    pool = _required_item_pool(discovery.get("item_pool", ()))
    if pool:
        return pool
    return _required_item_pool(fallback_ids)


def _item_label(item_id):
    return item_display_name(str(item_id or "item").strip().lower(), item_catalog=ITEM_CATALOG)


def _item_stack_max(item_id):
    item_def = ITEM_CATALOG.get(str(item_id or "").strip().lower(), {})
    return max(1, _safe_int(item_def.get("stack_max"), default=1))


def _reward_item(item_id, quantity=1):
    item_id = str(item_id or "").strip().lower()
    quantity = max(1, _safe_int(quantity, default=1))
    if not item_id or item_id not in ITEM_CATALOG:
        return None
    return {
        "item_id": item_id,
        "quantity": quantity,
    }


def _reward_with_items(base_reward, *items):
    reward = dict(base_reward or {})
    parsed = []
    for item in items:
        if isinstance(item, dict):
            spec = _reward_item(item.get("item_id"), quantity=item.get("quantity", 1))
        else:
            spec = _reward_item(item)
        if spec:
            parsed.append(spec)
    if parsed:
        reward["items"] = parsed
    return reward


def _specialty_chunk_opportunity_candidates(theme_id, *, chunk=None, identity_label="", travel=None, discovery=None, sites=None, rng=None):
    theme_id = str(theme_id or "").strip().lower()
    if not theme_id:
        return ()
    if not isinstance(rng, random.Random):
        rng = random.Random(f"specialty:{theme_id}")

    chunk_key = _chunk_tuple(chunk)
    label = str(identity_label).strip() or "this stretch"
    discovery = discovery if isinstance(discovery, dict) else {}
    discovery_label = str(discovery.get("label", "")).strip()
    anchor = _specialty_anchor_for_sites(theme_id, sites, rng)
    anchor_read = _specialty_anchor_read(anchor.get("anchor_site_name"), label)
    anchor_requirements = _specialty_anchor_requirements(anchor)
    candidates = []

    if theme_id == "route_hub":
        route_cache = discovery_label or "route stash"
        stash_item_pool = tuple(
            item_id
            for item_id in ("transit_daypass", "city_pass_token", "meal_voucher", "bottled_water")
            if item_id in ITEM_CATALOG
        )
        stash_item_id = str(rng.choice(stash_item_pool)).strip().lower() if stash_item_pool else "transit_daypass"
        stash_item_label = _item_label(stash_item_id)
        candidates.extend((
            {
                "kind": "layover_shuffle",
                "source": "specialty_theme",
                "title": "Layover Shuffle",
                "summary": f"Catch the turnover around {anchor_read} while travelers trade favors, cover, and small packets.",
                "playstyles": ("social", "economic", "stealth"),
                "reward": _reward_with_items(
                    {"credits": rng.randint(12, 26), "standing": 1},
                    rng.choice(("transit_daypass", "city_pass_token", "meal_voucher")),
                ),
                "weight": 1.24,
                "requirements": dict(anchor_requirements),
                **anchor,
            },
            {
                "kind": "route_stash",
                "source": "specialty_theme",
                "title": "Route Stash",
                "summary": (
                    f"A {route_cache} tucked into {anchor_read} is holding {stash_item_label}; "
                    "lift it clean and walk it to a quiet local handoff before the next line turns over."
                ),
                "playstyles": ("economic", "stealth", "social"),
                "reward": _reward_with_items(
                    {"credits": rng.randint(14, 28), "intel": 1},
                    rng.choice(("transit_daypass", "bottled_water", "meal_voucher")),
                ),
                "weight": 1.18,
                "requirements": {
                    **dict(anchor_requirements),
                    **({"pickup_chunk": chunk_key, "delivery_chunk": chunk_key, "visit_chunk": chunk_key} if chunk_key else {}),
                    "require_item_id": stash_item_id,
                    "require_item_qty": 1,
                    "consume_item": True,
                    "provide_item": True,
                    "item_label": stash_item_label,
                    "acquisition_hint": "pickup",
                },
                **anchor,
            },
        ))
    elif theme_id == "parts_yard":
        repair_item_pool = tuple(
            item_id
            for item_id in ("pocket_multitool", "prybar", "battery_pack")
            if item_id in ITEM_CATALOG
        )
        repair_item_id = str(rng.choice(repair_item_pool)).strip().lower() if repair_item_pool else "pocket_multitool"
        repair_item_label = _item_label(repair_item_id)
        candidates.extend((
            {
                "kind": "yard_strip",
                "source": "specialty_theme",
                "title": "Yard Strip",
                "summary": f"Work the salvage lanes around {anchor_read} before the regular crews strip them clean.",
                "playstyles": ("economic", "stealth", "combat"),
                "reward": _reward_with_items(
                    {"credits": rng.randint(16, 32), "standing": 1},
                    rng.choice(("battery_pack", "scrap_circuit", "pocket_multitool")),
                ),
                "weight": 1.28,
                "requirements": dict(anchor_requirements),
                **anchor,
            },
            {
                "kind": "field_repair_call",
                "source": "specialty_theme",
                "title": "Field Repair Call",
                "summary": f"Someone working off {anchor_read} needs {repair_item_label} before a bad breakdown turns public.",
                "playstyles": ("economic", "social", "stealth"),
                "reward": _reward_with_items(
                    {"credits": rng.randint(14, 26), "standing": 1},
                    rng.choice(("pocket_multitool", "prybar", "battery_pack")),
                ),
                "weight": 1.16,
                "requirements": {
                    **dict(anchor_requirements),
                    "require_item_id": repair_item_id,
                    "require_item_qty": 1,
                    "consume_item": True,
                    "provide_item": False,
                    "item_label": repair_item_label,
                    "acquisition_hint": "buy_or_find",
                },
                **anchor,
            },
        ))
    elif theme_id == "watch_network":
        candidates.extend((
            {
                "kind": "sightline_check",
                "source": "specialty_theme",
                "title": "Sightline Check",
                "summary": f"Use the long sightlines around {anchor_read} to map quiet movement, dead ground, and handoff windows.",
                "playstyles": ("stealth", "social"),
                "reward": _reward_with_items(
                    {"credits": rng.randint(8, 16), "intel": 2},
                    rng.choice(("hydration_salts", "med_gel", "city_pass_token")),
                ),
                "weight": 1.22,
                "requirements": dict(anchor_requirements),
                **anchor,
            },
            {
                "kind": "relay_watch",
                "source": "specialty_theme",
                "title": "Relay Watch",
                "summary": f"Somebody wants a clean read on who keeps using the {anchor_read} chain after dark.",
                "playstyles": ("stealth", "social", "economic"),
                "reward": _reward_with_items(
                    {"credits": rng.randint(10, 18), "intel": 2},
                    rng.choice(("credstick_chip", "hydration_salts")),
                ),
                "weight": 1.14,
                "requirements": dict(anchor_requirements),
                **anchor,
            },
        ))
    elif theme_id == "field_refuge":
        spring_item_pool = tuple(
            item_id
            for item_id in ("bottled_water", "hydration_salts", "med_gel")
            if item_id in ITEM_CATALOG
        )
        spring_item_id = str(rng.choice(spring_item_pool)).strip().lower() if spring_item_pool else "hydration_salts"
        spring_item_label = _item_label(spring_item_id)
        candidates.extend((
            {
                "kind": "refuge_resupply",
                "source": "specialty_theme",
                "title": "Refuge Resupply",
                "summary": f"Quiet shelter points around {anchor_read} are short on basics and paying in goodwill, cover, or both.",
                "playstyles": ("social", "economic", "stealth"),
                "reward": _reward_with_items(
                    {"credits": rng.randint(10, 22), "energy": 4, "safety": 5},
                    rng.choice(("med_gel", "hydration_salts", "street_ration")),
                ),
                "weight": 1.18,
                "requirements": dict(anchor_requirements),
                **anchor,
            },
            {
                "kind": "spring_run",
                "source": "specialty_theme",
                "title": "Spring Run",
                "summary": f"Carry {spring_item_label} between the rough refuge stops that hang off {anchor_read}.",
                "playstyles": ("social", "stealth", "economic"),
                "reward": _reward_with_items(
                    {"credits": rng.randint(8, 18), "energy": 6, "safety": 3},
                    rng.choice(("bottled_water", "hydration_salts", "med_gel")),
                ),
                "weight": 1.12,
                "requirements": {
                    **dict(anchor_requirements),
                    "require_item_id": spring_item_id,
                    "require_item_qty": 1,
                    "consume_item": True,
                    "provide_item": False,
                    "item_label": spring_item_label,
                    "acquisition_hint": "buy_or_find",
                },
                **anchor,
            },
        ))

    return tuple(candidates)


def _run_objective_id(sim):
    traits = getattr(sim, "world_traits", {}) if sim is not None else {}
    if not isinstance(traits, dict):
        return ""
    objective = traits.get("run_objective", {})
    if not isinstance(objective, dict):
        return ""
    return str(objective.get("id", "")).strip().lower()


def _property_label(prop, property_id=None):
    label = str((prop or {}).get("name", property_id or "site")).strip()
    return label or str(property_id or "site")


def _property_service_flags(prop):
    metadata = (prop or {}).get("metadata", {}) if isinstance((prop or {}).get("metadata", {}), dict) else {}
    finance_services = {
        str(service).strip().lower()
        for service in tuple(metadata.get("finance_services", ()) or ())
        if str(service).strip()
    }
    site_services = {
        str(service).strip().lower()
        for service in tuple(metadata.get("site_services", ()) or ())
        if str(service).strip()
    }
    return {
        "is_storefront": bool(metadata.get("is_storefront")),
        "public": bool(metadata.get("public")),
        "archetype": str(metadata.get("archetype", "")).strip().lower(),
        "finance_services": finance_services,
        "site_services": site_services,
    }


def _property_site_tokens(prop):
    metadata = prop.get("metadata") if isinstance((prop or {}).get("metadata"), dict) else {}
    tokens = set()
    for raw in (
        metadata.get("site_id"),
        metadata.get("local_building_id"),
        metadata.get("building_id"),
        prop.get("id"),
    ):
        text = str(raw or "").strip()
        if not text:
            continue
        lowered = text.lower()
        tokens.add(lowered)
        tokens.add(lowered.split(":")[-1])
    return tokens


def _properties_in_chunk(sim, chunk):
    if sim is None or not isinstance(chunk, (tuple, list)) or len(chunk) != 2:
        return []
    try:
        chunk_key = (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError):
        return []
    candidates = []
    for prop in getattr(sim, "properties", {}).values():
        if not isinstance(prop, dict):
            continue
        if str(prop.get("kind", "") or "").strip().lower() != "building":
            continue
        try:
            prop_chunk = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
        except (TypeError, ValueError):
            continue
        if prop_chunk == chunk_key:
            candidates.append(prop)
    return candidates


def _property_matches_chunk_hint(prop, requirements):
    requirements = requirements if isinstance(requirements, dict) else {}
    prop_name = _property_label(prop, prop.get("id"))
    prop_name_norm = prop_name.strip().lower()
    score = 0.0

    target_property_name = str(requirements.get("property_name", "") or "").strip().lower()
    if target_property_name:
        if prop_name_norm == target_property_name:
            score += 6.0
        elif target_property_name in prop_name_norm or prop_name_norm in target_property_name:
            score += 4.0

    target_site_kind = str(requirements.get("site_kind", "") or "").strip().lower()
    if target_site_kind:
        archetype = _property_archetype(prop)
        if archetype == target_site_kind:
            score += 5.0
        elif target_site_kind in archetype:
            score += 2.25

    target_site_id = str(requirements.get("site_id", "") or "").strip().lower()
    if target_site_id and target_site_id in _property_site_tokens(prop):
        score += 4.5

    flags = _property_service_flags(prop)
    if bool(requirements.get("prefer_storefront")) and flags.get("is_storefront"):
        score += 4.0
    if bool(requirements.get("prefer_finance_services")) and flags.get("finance_services"):
        score += 4.2
    if bool(requirements.get("prefer_site_services")) and flags.get("site_services"):
        score += 3.6
    if bool(requirements.get("prefer_public")) and flags.get("public"):
        score += 1.4
    if flags.get("public") or flags.get("is_storefront"):
        score += 0.65
    if flags.get("finance_services") or flags.get("site_services"):
        score += 0.35
    if property_focus_position(prop) is not None:
        score += 0.25
    return score


def _pick_task_property(sim, chunk, requirements, *, reserved_property_ids=None, rng_key=""):
    reserved_property_ids = {
        str(raw_id or "").strip()
        for raw_id in (reserved_property_ids or ())
        if str(raw_id or "").strip()
    }
    candidates = _properties_in_chunk(sim, chunk)
    if not candidates:
        return None

    scored = []
    for prop in candidates:
        prop_id = str(prop.get("id", "") or "").strip()
        if prop_id in reserved_property_ids:
            continue
        score = _property_matches_chunk_hint(prop, requirements)
        scored.append((score, _property_label(prop, prop_id).lower(), prop_id, prop))

    if not scored and reserved_property_ids:
        for prop in candidates:
            prop_id = str(prop.get("id", "") or "").strip()
            score = _property_matches_chunk_hint(prop, requirements)
            scored.append((score, _property_label(prop, prop_id).lower(), prop_id, prop))
    if not scored:
        return None

    scored.sort(key=lambda row: (-float(row[0]), row[1], row[2]))
    best_score = float(scored[0][0])
    shortlist = [prop for score, _label, _prop_id, prop in scored if score >= best_score - 0.75][:4]
    rng = random.Random(f"{getattr(sim, 'seed', 'seed')}:opp-stage:{rng_key}")
    return rng.choice(shortlist) if shortlist else scored[0][3]


def _site_target_for_requirements(sim, requirements, *, property_key, building_key, chunk=None):
    requirements = requirements if isinstance(requirements, dict) else {}
    property_id = str(requirements.get(property_key, "") or "").strip()
    building_id = str(requirements.get(building_key, "") or "").strip()
    if sim is None or not hasattr(sim, "properties"):
        return None
    if property_id:
        prop = sim.properties.get(property_id)
        if isinstance(prop, dict):
            if chunk is None:
                return prop
            try:
                prop_chunk = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
            except (TypeError, ValueError):
                prop_chunk = None
            if prop_chunk == chunk:
                return prop
    if building_id:
        for prop in sim.properties.values():
            if not isinstance(prop, dict):
                continue
            if building_id_from_property(prop) != building_id:
                continue
            if chunk is None:
                return prop
            try:
                prop_chunk = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
            except (TypeError, ValueError):
                prop_chunk = None
            if prop_chunk == chunk:
                return prop
    return None


def _stage_notice(entry, prop, *, stage_kind):
    opp_id = int(entry.get("id", 0) or 0)
    title = str(entry.get("title", "Opportunity")).strip() or "Opportunity"
    site_name = _property_label(prop, prop.get("id"))
    requirements = _opportunity_requirements(entry)
    if stage_kind == "pickup":
        return f"O{opp_id} {title}: pickup target staged at {site_name}. Interact there to make the pickup."
    if stage_kind == "delivery":
        return f"O{opp_id} {title}: handoff target staged at {site_name}. Interact there to complete the drop."
    return f"O{opp_id} {title}: work target staged at {site_name}. {_opportunity_activity_instruction(requirements)}"


def _restore_locked_stage_requirements(requirements, row):
    requirements = requirements if isinstance(requirements, dict) else {}
    row = row if isinstance(row, dict) else {}
    stage_kind = str(row.get("stage_kind", "") or "").strip().lower() or "task"
    property_id = str(row.get("property_id", "") or "").strip()
    building_id = str(row.get("building_id", "") or "").strip()
    chunk = _chunk_tuple(row.get("chunk"))
    if not property_id:
        return
    if stage_kind == "pickup":
        requirements["pickup_property_id"] = property_id
        if building_id:
            requirements["pickup_building_id"] = building_id
        if chunk is not None:
            requirements["pickup_chunk"] = chunk
        return
    if stage_kind == "delivery":
        requirements["delivery_property_id"] = property_id
        if building_id:
            requirements["delivery_building_id"] = building_id
            requirements["building_id"] = requirements.get("building_id") or building_id
        requirements["property_id"] = requirements.get("property_id") or property_id
        if chunk is not None:
            requirements["delivery_chunk"] = chunk
            requirements["visit_chunk"] = requirements.get("visit_chunk") or chunk
        return
    requirements["property_id"] = property_id
    if building_id:
        requirements["building_id"] = building_id
    if chunk is not None:
        requirements["visit_chunk"] = chunk


def _tracked_target_property_record(sim, row):
    row = row if isinstance(row, dict) else {}
    property_id = str(row.get("property_id", "") or "").strip()
    if not property_id:
        return None
    record = resolve_property_record(sim, property_id, include_saved=True)
    return record if isinstance(record, dict) else None


def _tracked_target_category(prop):
    metadata = (prop or {}).get("metadata", {}) if isinstance((prop or {}).get("metadata", {}), dict) else {}
    archetype = str(metadata.get("archetype", "") or "").strip().lower()
    if archetype in {"hospital", "clinic", "pharmacy", "backroom_clinic"}:
        return "medical"
    if archetype in {"police_station", "checkpoint", "courthouse", "jail", "prison", "security_office"}:
        return "secure"
    if archetype in {"bar", "club", "restaurant", "cafe", "hotel"}:
        return "hospitality"
    if archetype in {"warehouse", "yard", "factory", "depot", "garage"}:
        return "industrial"
    if archetype in {"station", "terminal", "bus_stop", "transit_hub"}:
        return "transit"
    if archetype in {"apartment", "residence", "tenement", "shelter"}:
        return "residential"
    if archetype in {"office", "bank", "tower", "pawn_shop"}:
        return "finance" if "bank" in archetype or "pawn" in archetype else "office"
    if property_is_storefront(prop):
        return "retail"
    if property_is_public(prop):
        return "public"
    return "building"


def _tracked_target_state_label(score, *, low, mid, high, top):
    if score >= 0.82:
        return top
    if score >= 0.62:
        return high
    if score >= 0.36:
        return mid
    return low


def _tracked_target_event_phase(category, base_phase, *, stage_kind="", traffic_state="", security_state="", stakes_state="", heat_state="", rng=None):
    rng = rng if isinstance(rng, random.Random) else random.Random("opp-target-phase")
    category = str(category or "").strip().lower()
    base_phase = str(base_phase or "").strip().lower()
    stage_kind = str(stage_kind or "").strip().lower()
    traffic_state = str(traffic_state or "").strip().lower()
    security_state = str(security_state or "").strip().lower()
    stakes_state = str(stakes_state or "").strip().lower()
    heat_state = str(heat_state or "").strip().lower()

    if security_state in {"watched", "tight"}:
        if category in {"secure", "medical", "residential"}:
            return "visitor_screening"
        if category in {"industrial", "transit"}:
            return "manifest_check"
        return "owner_screening"

    if stage_kind == "pickup":
        if category in {"industrial", "transit"}:
            return rng.choice(("loading_push", "arrival_handoff", "dispatch_surge"))
        if category == "hospitality":
            return rng.choice(("reset_scramble", "counter_queue"))
        return rng.choice(("counter_queue", "paperwork_surge"))

    if stage_kind == "delivery":
        if category in {"industrial", "transit"}:
            return rng.choice(("dispatch_surge", "arrival_handoff", "loading_push"))
        if category == "medical":
            return "triage_spill"
        return rng.choice(("paperwork_surge", "counter_queue", "crowd_spillover"))

    if stakes_state in {"rising", "urgent"} or heat_state in {"watched", "hot"}:
        if category in {"industrial", "transit"}:
            return rng.choice(("dispatch_surge", "loading_push"))
        if category == "hospitality":
            return rng.choice(("table_turnover", "crowd_spillover"))
        if category == "medical":
            return rng.choice(("triage_spill", "paperwork_surge"))
        if category == "residential":
            return "neighbors_lingering"
        return rng.choice(("paperwork_surge", "regulars_spill", "counter_queue"))

    if traffic_state in {"thin", "patchy"}:
        if category == "hospitality":
            return "reset_scramble"
        return "maintenance_loop"

    if category in {"industrial", "transit"}:
        return "dispatch_surge"
    if category == "hospitality":
        return "regulars_spill"
    if category == "medical":
        return "triage_spill"
    if category == "residential":
        return "neighbors_lingering"
    if category == "secure":
        return "visitor_screening"
    return "paperwork_surge"


def _tracked_target_surface_bits(row):
    row = row if isinstance(row, dict) else {}
    bits = []
    security_state = str(row.get("security_state", "") or "").strip().lower()
    if security_state == "tight":
        bits.append("tighter access")
    elif security_state == "watched":
        bits.append("more watched")
    traffic_state = str(row.get("traffic_state", "") or "").strip().lower()
    if traffic_state == "thin":
        bits.append("thinner crowd")
    elif traffic_state == "patchy":
        bits.append("patchier foot traffic")
    elif traffic_state in {"busy", "heavy"}:
        bits.append("noisier frontage")
    stakes_state = str(row.get("stakes_state", "") or "").strip().lower()
    if stakes_state == "urgent":
        bits.append("a tightening window")
    elif stakes_state == "rising":
        bits.append("growing pressure")
    heat_state = str(row.get("heat_state", "") or "").strip().lower()
    if heat_state == "hot":
        bits.append("a hotter read")
    community_tone = str(row.get("community_tone", "") or "").strip().lower()
    if community_tone == "protective":
        bits.append("locals holding the edge")
    elif community_tone == "troubled":
        bits.append("a touch of local tension")
    return tuple(bits[:3])


def opportunity_target_summary_text(row, *, include_site=False, site_name=""):
    row = row if isinstance(row, dict) else {}
    bits = list(_tracked_target_surface_bits(row))
    if not bits:
        return ""
    if include_site:
        label = str(site_name or row.get("anchor_site_name", "") or "the site").strip() or "the site"
        if len(bits) == 1:
            return f"{label} feels {bits[0]}."
        if len(bits) == 2:
            return f"{label} feels {bits[0]}, with {bits[1]}."
        return f"{label} feels {bits[0]}, with {bits[1]} and {bits[2]}."
    return "; ".join(bits[:2])


def _opportunity_focus_tracked_target(sim, opportunity, player_eid=None, *, property_id=""):
    opportunity = opportunity if isinstance(opportunity, dict) else {}
    requested_property_id = str(property_id or "").strip()
    rows = list(_tracked_target_rows_for_opportunity(sim, opportunity.get("id")))
    if not rows:
        return None
    if requested_property_id:
        for row in rows:
            if str(row.get("property_id", "") or "").strip() == requested_property_id:
                return row

    requirements = _opportunity_requirements(opportunity)
    require_item_id = str(requirements.get("require_item_id", "") or "").strip().lower()
    if require_item_id and player_eid is not None:
        inventory = sim.ecs.get(Inventory).get(player_eid) if sim is not None and player_eid is not None else None
        counts = _inventory_counts(inventory)
        required_qty = max(1, _safe_int(requirements.get("require_item_qty"), default=1))
        carried_qty = max(0, _safe_int(counts.get(require_item_id), default=0))
        preferred_stage = "pickup" if bool(requirements.get("provide_item")) and carried_qty < required_qty else "delivery"
    else:
        preferred_stage = "task"

    for row in rows:
        if str(row.get("stage_kind", "") or "").strip().lower() == preferred_stage:
            return row
    return rows[0]


def tracked_target_surface_snapshot(sim, property_id, *, player_eid=None):
    property_key = str(property_id or "").strip()
    if not property_key:
        return None
    state = _state(sim)
    active = [entry for entry in state.get("active", ()) if isinstance(entry, dict)]
    best = None
    for entry in active:
        row = _opportunity_focus_tracked_target(sim, entry, player_eid, property_id=property_key)
        if not isinstance(row, dict):
            continue
        if str(row.get("property_id", "") or "").strip() != property_key:
            continue
        summary = opportunity_target_summary_text(row, include_site=False)
        if not summary:
            continue
        score = 0
        if str(row.get("stakes_state", "") or "").strip().lower() == "urgent":
            score += 4
        elif str(row.get("stakes_state", "") or "").strip().lower() == "rising":
            score += 2
        if str(row.get("heat_state", "") or "").strip().lower() == "hot":
            score += 3
        elif str(row.get("heat_state", "") or "").strip().lower() == "watched":
            score += 2
        candidate = {
            "property_id": property_key,
            "opportunity_id": int(entry.get("id", 0) or 0),
            "summary": summary,
            "detail": opportunity_target_summary_text(
                row,
                include_site=True,
                site_name=str(row.get("anchor_site_name", "") or ""),
            ),
            "stage_kind": str(row.get("stage_kind", "") or "").strip().lower(),
            "row": row,
            "score": score,
        }
        if best is None or int(candidate["score"]) > int(best["score"]):
            best = candidate
    return best


def tracked_target_scene_rows(sim, chunk):
    chunk = _chunk_tuple(chunk)
    if chunk is None:
        return ()
    tracked = _tracked_targets_bucket(_state(sim))
    rows = []
    for row in tracked.values():
        if not isinstance(row, dict) or bool(row.get("site_missing")):
            continue
        if _chunk_tuple(row.get("chunk")) != chunk:
            continue
        event_phase = str(row.get("event_phase", "") or "").strip().lower()
        property_id = str(row.get("property_id", "") or "").strip()
        if not property_id or not event_phase:
            continue
        score = 0.8
        if str(row.get("stakes_state", "") or "").strip().lower() == "urgent":
            score += 1.4
        elif str(row.get("stakes_state", "") or "").strip().lower() == "rising":
            score += 0.7
        if str(row.get("heat_state", "") or "").strip().lower() == "hot":
            score += 1.1
        elif str(row.get("heat_state", "") or "").strip().lower() == "watched":
            score += 0.55
        rows.append({
            "property_id": property_id,
            "event_phase": event_phase,
            "traffic_state": str(row.get("traffic_state", "") or "").strip().lower(),
            "community_tone": str(row.get("community_tone", "") or "").strip().lower(),
            "security_state": str(row.get("security_state", "") or "").strip().lower(),
            "stakes_state": str(row.get("stakes_state", "") or "").strip().lower(),
            "heat_state": str(row.get("heat_state", "") or "").strip().lower(),
            "score": score,
        })
    rows.sort(
        key=lambda row: (
            -float(row.get("score", 0.0) or 0.0),
            str(row.get("property_id", "") or ""),
        )
    )
    return tuple(rows)


def opportunity_target_arrival_notes(sim, chunk):
    chunk = _chunk_tuple(chunk)
    if chunk is None:
        return ()
    tracked = _tracked_targets_bucket(_state(sim))
    notes = []
    for row in tracked.values():
        if not isinstance(row, dict) or not bool(row.get("arrival_note_pending")):
            continue
        if _chunk_tuple(row.get("chunk")) != chunk:
            continue
        site_name = str(row.get("anchor_site_name", "") or row.get("property_id", "site")).strip() or "site"
        note = opportunity_target_summary_text(row, include_site=True, site_name=site_name)
        if not note:
            continue
        row["arrival_note_pending"] = False
        row["last_surface_tick"] = int(getattr(sim, "tick", 0))
        notes.append(note)
    return tuple(notes)


def _refresh_tracked_targets(sim):
    state = _state(sim)
    tracked = _tracked_targets_bucket(state)
    active_entries = [entry for entry in state.get("active", ()) if isinstance(entry, dict)]
    live_stage_keys = set()
    for entry in active_entries:
        requirements = _opportunity_requirements(entry)
        accepted = bool(requirements.get("player_accepted"))
        hot = _opportunity_has_hot_target(entry)
        if not (accepted or hot):
            continue
        tracking_reason = "accepted" if accepted else "hot"
        for stage in _opportunity_stage_targets(entry):
            property_id = str(stage.get("property_id", "") or "").strip()
            if not property_id:
                continue
            stage_kind = str(stage.get("stage_kind", "") or "").strip().lower() or "task"
            key = _tracked_target_key(entry.get("id"), stage_kind, property_id)
            if not key:
                continue
            live_stage_keys.add(key)
            row = tracked.get(key)
            if not isinstance(row, dict):
                row = {
                    "opportunity_id": int(entry.get("id", 0) or 0),
                    "stage_kind": stage_kind,
                    "property_id": property_id,
                    "building_id": str(stage.get("building_id", "") or "").strip(),
                    "chunk": _chunk_tuple(stage.get("chunk")),
                    "anchor_site_name": "",
                    "tracking_reason": tracking_reason,
                    "locked_target": True,
                    "last_update_tick": -1,
                    "last_surface_tick": -1,
                    "event_phase": "",
                    "traffic_state": "",
                    "community_tone": "",
                    "security_state": "",
                    "stakes_state": "",
                    "heat_state": "",
                    "arrival_note_pending": False,
                    "site_missing": False,
                }
                tracked[key] = row
            row["tracking_reason"] = tracking_reason
            row["locked_target"] = True
            if str(stage.get("building_id", "") or "").strip():
                row["building_id"] = str(stage.get("building_id", "") or "").strip()
            if _chunk_tuple(stage.get("chunk")) is not None:
                row["chunk"] = _chunk_tuple(stage.get("chunk"))
            prop = _tracked_target_property_record(sim, row)
            if isinstance(prop, dict):
                row["site_missing"] = False
                row["anchor_site_name"] = _property_label(prop, property_id)
                try:
                    row["chunk"] = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
                except (TypeError, ValueError):
                    pass
                if not str(row.get("building_id", "") or "").strip():
                    row["building_id"] = building_id_from_property(prop)
            _restore_locked_stage_requirements(requirements, row)
    for key in list(tracked.keys()):
        if key in live_stage_keys:
            continue
        tracked.pop(key, None)


def _update_tracked_target_drift(sim, player_eid):
    state = _state(sim)
    tracked = _tracked_targets_bucket(state)
    if not tracked:
        return
    current_hour = int(world_hour(sim)) % 24 if sim is not None else 0
    if _safe_int(state.get("tracked_target_world_hour"), default=-1) == current_hour:
        return
    state["tracked_target_world_hour"] = current_hour

    recent_property_tags, recent_building_tags, recent_chunk_tags = _recent_opportunity_activities(sim, freshness_ticks=32)
    try:
        from game.systems_business_events import _base_building_pulse_snapshot
    except Exception:
        _base_building_pulse_snapshot = None

    current_chunk = _player_chunk(sim, player_eid)
    for row in tracked.values():
        if not isinstance(row, dict):
            continue
        previous = {
            "event_phase": str(row.get("event_phase", "") or "").strip().lower(),
            "traffic_state": str(row.get("traffic_state", "") or "").strip().lower(),
            "community_tone": str(row.get("community_tone", "") or "").strip().lower(),
            "security_state": str(row.get("security_state", "") or "").strip().lower(),
            "stakes_state": str(row.get("stakes_state", "") or "").strip().lower(),
            "heat_state": str(row.get("heat_state", "") or "").strip().lower(),
        }
        prop = _tracked_target_property_record(sim, row)
        if not isinstance(prop, dict):
            row["site_missing"] = True
            row["last_update_tick"] = int(getattr(sim, "tick", 0))
            continue

        row["site_missing"] = False
        row["anchor_site_name"] = _property_label(prop, row.get("property_id"))
        if _base_building_pulse_snapshot is not None:
            pulse = _base_building_pulse_snapshot(sim, prop=prop)
        else:
            pulse = {}
        pulse = pulse if isinstance(pulse, dict) else {}
        base_phase = str(pulse.get("event_phase", "") or pulse.get("phase", "") or "").strip().lower()
        traffic_state = str(pulse.get("traffic_state", "") or "").strip().lower()
        if not traffic_state:
            if base_phase in {"rush", "lunch_rush", "evening_crowd", "crowd_spillover", "dispatch_surge", "loading_push"}:
                traffic_state = "busy"
            elif base_phase in {"after_hours", "locked_down", "back_office", "cleanup", "night_watch"}:
                traffic_state = "thin"
            else:
                traffic_state = "steady"
        community_tone = str(pulse.get("community_tone", "") or "").strip().lower()
        category = str(pulse.get("category", "") or "").strip().lower() or _tracked_target_category(prop)

        property_id = str(row.get("property_id", "") or "").strip()
        building_id = str(row.get("building_id", "") or "").strip()
        chunk = _chunk_tuple(row.get("chunk"))
        activity_tags = set()
        activity_tags.update(recent_property_tags.get(property_id, ()))
        if building_id:
            activity_tags.update(recent_building_tags.get(building_id, ()))
        if chunk is not None:
            activity_tags.update(recent_chunk_tags.get(chunk, ()))

        requirements = None
        for entry in state.get("active", ()):
            if not isinstance(entry, dict):
                continue
            if _safe_int(entry.get("id"), default=0) != _safe_int(row.get("opportunity_id"), default=0):
                continue
            requirements = _opportunity_requirements(entry)
            risk = str(entry.get("risk", "") or "").strip().lower()
            expire_tick = _safe_int(entry.get("expire_tick"), default=-1)
            break
        else:
            risk = ""
            expire_tick = -1

        security_score = 0.22 if property_is_public(prop) else 0.38
        if property_is_storefront(prop):
            security_score -= 0.04
        if category in {"secure", "medical"}:
            security_score += 0.26
        if risk == "hazardous":
            security_score += 0.18
        if "stakeout" in activity_tags or "intel" in activity_tags:
            security_score += 0.14
        if not property_is_public(prop):
            security_score += 0.06
        security_state = _tracked_target_state_label(
            security_score,
            low="loose",
            mid="steady",
            high="watched",
            top="tight",
        )

        heat_score = 0.14
        if risk == "hazardous":
            heat_score += 0.26
        if "stakeout" in activity_tags:
            heat_score += 0.2
        if "intel" in activity_tags:
            heat_score += 0.12
        if security_state in {"watched", "tight"}:
            heat_score += 0.12
        heat_state = _tracked_target_state_label(
            heat_score,
            low="calm",
            mid="active",
            high="watched",
            top="hot",
        )

        ticks_left = max(0, expire_tick - int(getattr(sim, "tick", 0))) if expire_tick >= 0 else 999999
        stakes_score = 0.22 if row.get("tracking_reason") == "accepted" else 0.12
        if risk == "hazardous":
            stakes_score += 0.22
        if ticks_left <= max(1, _opportunity_ticks_per_hour(sim) * 8):
            stakes_score += 0.22
        elif ticks_left <= max(1, _opportunity_ticks_per_hour(sim) * 16):
            stakes_score += 0.12
        if heat_state in {"watched", "hot"}:
            stakes_score += 0.12
        stakes_state = _tracked_target_state_label(
            stakes_score,
            low="cooling",
            mid="live",
            high="rising",
            top="urgent",
        )

        if not community_tone:
            if "contact" in activity_tags and property_is_public(prop):
                community_tone = "protective"
            elif risk == "hazardous" or heat_state in {"watched", "hot"}:
                community_tone = "troubled"
            else:
                community_tone = ""

        rng = random.Random(
            f"{getattr(sim, 'seed', 'seed')}:opp-target-drift:"
            f"{row.get('opportunity_id')}:{row.get('stage_kind')}:{property_id}:{current_hour}"
        )
        event_phase = _tracked_target_event_phase(
            category,
            base_phase,
            stage_kind=str(row.get("stage_kind", "") or "").strip().lower(),
            traffic_state=traffic_state,
            security_state=security_state,
            stakes_state=stakes_state,
            heat_state=heat_state,
            rng=rng,
        )

        row["event_phase"] = event_phase
        row["traffic_state"] = traffic_state
        row["community_tone"] = community_tone
        row["security_state"] = security_state
        row["stakes_state"] = stakes_state
        row["heat_state"] = heat_state
        row["last_update_tick"] = int(getattr(sim, "tick", 0))

        current_summary = opportunity_target_summary_text(row, include_site=False)
        previous_row = dict(previous)
        previous_summary = opportunity_target_summary_text(previous_row, include_site=False)
        if current_summary and current_summary != previous_summary and current_chunk != _chunk_tuple(row.get("chunk")):
            row["arrival_note_pending"] = True


def stage_active_opportunities(sim, player_eid):
    state = _state(sim)
    _refresh_tracked_targets(sim)
    active = [entry for entry in state.get("active", ()) if isinstance(entry, dict)]
    if not active:
        return []

    current_chunk = _player_chunk(sim, player_eid)
    if current_chunk is None:
        return []

    inventory = sim.ecs.get(Inventory).get(player_eid) if sim is not None and player_eid is not None else None
    inventory_counts = _inventory_counts(inventory)
    reserved_property_ids = {
        str(raw_id or "").strip()
        for entry in active
        for raw_id in (
            (entry.get("requirements", {}) if isinstance(entry.get("requirements", {}), dict) else {}).get("property_id"),
            (entry.get("requirements", {}) if isinstance(entry.get("requirements", {}), dict) else {}).get("pickup_property_id"),
            (entry.get("requirements", {}) if isinstance(entry.get("requirements", {}), dict) else {}).get("delivery_property_id"),
        )
        if str(raw_id or "").strip()
    }
    notices = []

    for entry in active:
        requirements = _opportunity_requirements(entry)
        if not _site_task_expected(requirements):
            continue

        item_id = str(requirements.get("require_item_id", "")).strip().lower()
        item_qty = max(1, _safe_int(requirements.get("require_item_qty"), default=1))
        carried_qty = max(0, _safe_int(inventory_counts.get(item_id), default=0)) if item_id else 0

        pickup_chunk = _chunk_tuple(requirements.get("pickup_chunk"))
        if bool(requirements.get("provide_item")) and item_id and carried_qty < item_qty and pickup_chunk == current_chunk:
            locked_pickup = _tracked_target_record_for_stage(
                sim,
                entry.get("id"),
                "pickup",
                requirements.get("pickup_property_id"),
            )
            if isinstance(locked_pickup, dict):
                _restore_locked_stage_requirements(requirements, locked_pickup)
            existing_pickup = _site_target_for_requirements(
                sim,
                requirements,
                property_key="pickup_property_id",
                building_key="pickup_building_id",
                chunk=current_chunk,
            )
            if existing_pickup is None:
                if isinstance(locked_pickup, dict) and bool(locked_pickup.get("locked_target")):
                    continue
                prop = _pick_task_property(
                    sim,
                    current_chunk,
                    requirements,
                    reserved_property_ids=reserved_property_ids,
                    rng_key=f"pickup:{int(entry.get('id', 0) or 0)}:{current_chunk[0]}:{current_chunk[1]}",
                )
                if prop is not None:
                    requirements["pickup_property_id"] = str(prop.get("id", "") or "").strip()
                    requirements["pickup_building_id"] = building_id_from_property(prop)
                    reserved_property_ids.add(str(prop.get("id", "") or "").strip())
                    notices.append(_stage_notice(entry, prop, stage_kind="pickup"))

        target_chunk = None
        stage_kind = ""
        if item_id:
            if carried_qty >= item_qty or not bool(requirements.get("provide_item")):
                target_chunk = _chunk_tuple(requirements.get("delivery_chunk")) or _chunk_tuple(requirements.get("visit_chunk"))
                stage_kind = "delivery"
        else:
            target_chunk = _chunk_tuple(requirements.get("visit_chunk"))
            stage_kind = "task"

        if target_chunk != current_chunk or not stage_kind:
            continue

        property_key = "delivery_property_id" if stage_kind == "delivery" else "property_id"
        building_key = "delivery_building_id" if stage_kind == "delivery" else "building_id"
        locked_target = _tracked_target_record_for_stage(
            sim,
            entry.get("id"),
            stage_kind,
            requirements.get(property_key),
        )
        if isinstance(locked_target, dict):
            _restore_locked_stage_requirements(requirements, locked_target)
        existing_target = _site_target_for_requirements(
            sim,
            requirements,
            property_key=property_key,
            building_key=building_key,
            chunk=current_chunk,
        )
        if existing_target is not None:
            if stage_kind == "delivery" and not str(requirements.get("property_id", "")).strip():
                requirements["property_id"] = str(existing_target.get("id", "") or "").strip()
                requirements["building_id"] = building_id_from_property(existing_target)
            continue
        if isinstance(locked_target, dict) and bool(locked_target.get("locked_target")):
            continue

        prop = _pick_task_property(
            sim,
            current_chunk,
            requirements,
            reserved_property_ids=reserved_property_ids,
            rng_key=f"{stage_kind}:{int(entry.get('id', 0) or 0)}:{current_chunk[0]}:{current_chunk[1]}",
        )
        if prop is None:
            continue
        prop_id = str(prop.get("id", "") or "").strip()
        building_id = building_id_from_property(prop)
        requirements[property_key] = prop_id
        requirements[building_key] = building_id
        if stage_kind == "delivery":
            requirements["property_id"] = prop_id
            requirements["building_id"] = building_id
        reserved_property_ids.add(prop_id)
        notices.append(_stage_notice(entry, prop, stage_kind=stage_kind))

    _refresh_tracked_targets(sim)
    return notices


def _contact_variant_candidate(sim, prop, property_id, entry, objective_id):
    if not isinstance(prop, dict):
        return None
    standing = float((entry or {}).get("standing", 0.5))
    cx, cy = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
    prop_name = _property_label(prop, property_id)
    flags = _property_service_flags(prop)
    finance_services = flags["finance_services"]
    site_services = flags["site_services"]
    is_storefront = bool(flags["is_storefront"])
    chooser = random.Random(f"{getattr(sim, 'seed', 'seed')}:opp-contact:{objective_id}:{property_id}")

    if objective_id == "debt_exit":
        pool = ["debt_marker", "supply_shortage"]
        if finance_services:
            pool.append("claims_chase")
        if is_storefront or site_services:
            pool.append("backroom_buyback")
    elif objective_id == "networked_extraction":
        pool = ["contact_run", "property_dispute", "service_friction"]
        if finance_services:
            pool.extend(["claims_chase", "records_pull"])
        if standing >= 0.66:
            pool.append("watch_post")
    elif objective_id == "neighborhood_control":
        pool = ["property_dispute", "contact_run", "service_friction", "supply_shortage"]
        if finance_services:
            pool.extend(["claims_chase", "paper_trail"])
        if is_storefront or site_services:
            pool.append("backroom_buyback")
    elif objective_id == "high_value_retrieval":
        pool = ["service_friction", "property_dispute"]
        if finance_services or "intel" in site_services:
            pool.append("records_pull")
        if standing >= 0.7:
            pool.append("watch_post")
        if standing >= 0.82:
            pool.append("contact_run")
    else:
        pool = ["debt_marker", "service_friction", "property_dispute", "supply_shortage"]
        if finance_services:
            pool.extend(["claims_chase", "records_pull"])
        if is_storefront or site_services:
            pool.append("backroom_buyback")
        if standing >= 0.7:
            pool.append("contact_run")
        if "intel" in site_services:
            pool.append("watch_post")

    kind = chooser.choice(tuple(pool))

    if kind == "debt_marker":
        return {
            "key": f"debt_marker:{property_id}",
            "title": "Debt Pressure",
            "summary": f"Debt pressure around {prop_name} is loosening tongues and valuables.",
            "kind": "debt_marker",
            "source": "contact",
            "chunk": (cx, cy),
            "location": "contact",
            "playstyles": ("social", "economic", "stealth"),
            "reward": {
                "credits": max(12, _safe_int(standing * 24, default=12)),
                "intel": 1,
            },
            "risk": "low",
            "pressure": "low",
            "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
            "status": "active",
            "seed_tick": int(getattr(sim, "tick", 0)),
        }

    if kind == "supply_shortage":
        return {
            "key": f"supply_shortage:{property_id}",
            "title": "Supply Shortage",
            "summary": f"{prop_name} is running short; quick fills and side sales are paying right now.",
            "kind": "supply_shortage",
            "source": "contact",
            "chunk": (cx, cy),
            "location": "contact",
            "playstyles": ("economic", "social", "stealth"),
            "reward": _reward_with_items({
                "credits": max(10, _safe_int(standing * 20, default=10)),
                "standing": 1,
            }, chooser.choice(("street_ration", "hydration_salts"))),
            "risk": "low",
            "pressure": "low",
            "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
            "status": "active",
            "seed_tick": int(getattr(sim, "tick", 0)),
        }

    if kind == "contact_run":
        return {
            "key": f"contact_run:{property_id}",
            "title": "Contact Run",
            "summary": f"A quiet face at {prop_name} is willing to talk business if you show up clean and on time.",
            "kind": "contact_run",
            "source": "contact",
            "chunk": (cx, cy),
            "location": "contact",
            "playstyles": ("social", "stealth", "economic"),
            "reward": _reward_with_items({
                "credits": max(8, _safe_int(standing * 16, default=8)),
                "standing": 2,
                "intel": 1,
            }, chooser.choice(("transit_daypass", "credstick_chip"))),
            "risk": "low",
            "pressure": "low",
            "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
            "status": "active",
            "seed_tick": int(getattr(sim, "tick", 0)),
        }

    if kind == "claims_chase":
        return {
            "key": f"claims_chase:{property_id}",
            "title": "Claims Chase",
            "summary": f"A payout tied to {prop_name} is stuck in the pipe; lean on it before somebody else clips the margin.",
            "kind": "claims_chase",
            "source": "contact",
            "chunk": (cx, cy),
            "location": "contact",
            "playstyles": ("economic", "social", "stealth"),
            "reward": _reward_with_items({
                "credits": max(14, _safe_int(standing * 26, default=14)),
                "standing": 1,
            }, "credstick_chip"),
            "risk": "low",
            "pressure": "low",
            "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
            "status": "active",
            "seed_tick": int(getattr(sim, "tick", 0)),
        }

    if kind == "backroom_buyback":
        return {
            "key": f"backroom_buyback:{property_id}",
            "title": "Backroom Buyback",
            "summary": f"A quiet buyer tied to {prop_name} is paying for compact tools and overlooked kit while the window is open.",
            "kind": "backroom_buyback",
            "source": "contact",
            "chunk": (cx, cy),
            "location": "contact",
            "playstyles": ("economic", "social", "stealth"),
            "reward": _reward_with_items({
                "credits": max(12, _safe_int(standing * 22, default=12)),
                "standing": 1,
            }, chooser.choice(("lockpick_kit", "pocket_multitool"))),
            "risk": "exposed",
            "pressure": "medium",
            "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
            "status": "active",
            "seed_tick": int(getattr(sim, "tick", 0)),
        }

    if kind == "records_pull":
        return {
            "key": f"records_pull:{property_id}",
            "title": "Records Pull",
            "summary": f"Shift sheets and service records around {prop_name} are loose enough to pull something useful before they get cleaned up.",
            "kind": "records_pull",
            "source": "contact",
            "chunk": (cx, cy),
            "location": "contact",
            "playstyles": ("stealth", "social", "economic"),
            "reward": _reward_with_items({
                "credits": max(8, _safe_int(standing * 16, default=8)),
                "intel": 2,
            }, chooser.choice(("credstick_chip", "transit_daypass"))),
            "risk": "exposed",
            "pressure": "medium",
            "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
            "status": "active",
            "seed_tick": int(getattr(sim, "tick", 0)),
        }

    if kind == "watch_post":
        return {
            "key": f"watch_post:{property_id}",
            "title": "Watch Post",
            "summary": f"A patient watch around {prop_name} is catching quiet handoffs, shift changes, and who acts like they belong.",
            "kind": "watch_post",
            "source": "contact",
            "chunk": (cx, cy),
            "location": "contact",
            "playstyles": ("stealth", "social"),
            "reward": _reward_with_items({
                "credits": max(6, _safe_int(standing * 12, default=6)),
                "intel": 2,
            }, chooser.choice(("hydration_salts", "med_gel"))),
            "risk": "low",
            "pressure": "low",
            "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
            "status": "active",
            "seed_tick": int(getattr(sim, "tick", 0)),
        }

    if kind == "property_dispute":
        return {
            "key": f"property_dispute:{property_id}",
            "title": "Local Dispute",
            "summary": f"A dispute tied to {prop_name} is shaking routines and splitting loyalties.",
            "kind": "property_dispute",
            "source": "contact",
            "chunk": (cx, cy),
            "location": "contact",
            "playstyles": ("social", "stealth", "economic"),
            "reward": {
                "credits": max(8, _safe_int(standing * 14, default=8)),
                "standing": 2,
                "intel": 1,
            },
            "risk": "exposed",
            "pressure": "medium",
            "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
            "status": "active",
            "seed_tick": int(getattr(sim, "tick", 0)),
        }

    return {
        "key": f"service_friction:{property_id}",
        "title": "Service Friction",
        "summary": f"{prop_name} is jammed with complaints and delays; staff are getting sloppy and chatty.",
        "kind": "service_friction",
        "source": "contact",
        "chunk": (cx, cy),
        "location": "contact",
        "playstyles": ("social", "stealth"),
        "reward": _reward_with_items({
            "credits": max(6, _safe_int(standing * 12, default=6)),
            "standing": 1,
            "intel": 2,
        }, "transit_daypass"),
        "risk": "exposed",
        "pressure": "medium",
        "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
        "status": "active",
        "seed_tick": int(getattr(sim, "tick", 0)),
    }


def _intel_variant_candidate(sim, prop, property_id, entry, objective_id):
    if not isinstance(prop, dict):
        return None
    confidence = float((entry or {}).get("confidence", 0.0))
    lead_kind = str((entry or {}).get("lead_kind", "") or "").strip().lower()
    cx, cy = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
    prop_name = _property_label(prop, property_id)
    chooser = random.Random(f"{getattr(sim, 'seed', 'seed')}:opp-intel:{objective_id}:{property_id}:{lead_kind}")

    if lead_kind == "workplace":
        kind = chooser.choice(("missing_person", "contact_run"))
    elif lead_kind in {"access", "security", "hours"}:
        kind = chooser.choice(("service_friction", "records_pull", "watch_post"))
    elif lead_kind == "owner":
        kind = chooser.choice(("property_dispute", "claims_chase"))
    else:
        pools = {
            "debt_exit": ("debt_marker", "supply_shortage", "lead_followup", "claims_chase"),
            "networked_extraction": ("property_dispute", "missing_person", "lead_followup", "contact_run", "records_pull"),
            "neighborhood_control": ("property_dispute", "contact_run", "service_friction", "claims_chase", "paper_trail"),
            "high_value_retrieval": ("missing_person", "service_friction", "lead_followup", "records_pull", "watch_post"),
        }
        pool = pools.get(objective_id, ("lead_followup", "missing_person", "property_dispute", "service_friction"))
        kind = chooser.choice(pool)

    if kind == "contact_run":
        return {
            "key": f"contact_run:intel:{property_id}",
            "title": "Contact Run",
            "summary": f"Intel says someone around {prop_name} will talk if you show up like you belong there.",
            "kind": "contact_run",
            "source": "intel",
            "chunk": (cx, cy),
            "location": "lead",
            "playstyles": ("social", "stealth"),
            "reward": _reward_with_items({
                "standing": 1,
                "intel": max(1, _safe_int(confidence * 3, default=1)),
            }, chooser.choice(("transit_daypass", "street_ration"))),
            "risk": "low",
            "pressure": "low",
            "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
            "status": "active",
            "seed_tick": int(getattr(sim, "tick", 0)),
        }

    if kind == "missing_person":
        return {
            "key": f"missing_person:{property_id}",
            "title": "Missing Person Lead",
            "summary": f"Someone tied to {prop_name} is missing, and the search is exposing routines around the site.",
            "kind": "missing_person",
            "source": "intel",
            "chunk": (cx, cy),
            "location": "lead",
            "playstyles": ("social", "stealth"),
            "reward": {
                "standing": 1,
                "intel": max(2, _safe_int(confidence * 4, default=2)),
            },
            "risk": "exposed",
            "pressure": "medium",
            "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
            "status": "active",
            "seed_tick": int(getattr(sim, "tick", 0)),
        }

    if kind == "property_dispute":
        return {
            "key": f"property_dispute:intel:{property_id}",
            "title": "Dispute Trail",
            "summary": f"Tension around {prop_name} is splitting routines and making people talk.",
            "kind": "property_dispute",
            "source": "intel",
            "chunk": (cx, cy),
            "location": "lead",
            "playstyles": ("social", "stealth", "economic"),
            "reward": {
                "credits": 8,
                "standing": 1,
                "intel": max(1, _safe_int(confidence * 3, default=1)),
            },
            "risk": "exposed",
            "pressure": "medium",
            "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
            "status": "active",
            "seed_tick": int(getattr(sim, "tick", 0)),
        }

    if kind == "service_friction":
        return {
            "key": f"service_friction:intel:{property_id}",
            "title": "Service Friction",
            "summary": f"Complaints and delays around {prop_name} are exposing timings, access habits, and weak points.",
            "kind": "service_friction",
            "source": "intel",
            "chunk": (cx, cy),
            "location": "lead",
            "playstyles": ("social", "stealth"),
            "reward": {
                "intel": max(2, _safe_int(confidence * 4, default=2)),
            },
            "risk": "low",
            "pressure": "low",
            "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
            "status": "active",
            "seed_tick": int(getattr(sim, "tick", 0)),
        }

    if kind == "claims_chase":
        return {
            "key": f"claims_chase:intel:{property_id}",
            "title": "Claims Chase",
            "summary": f"Paper around {prop_name} says a claim or payout is hanging loose enough to lean on for quick reserve.",
            "kind": "claims_chase",
            "source": "intel",
            "chunk": (cx, cy),
            "location": "lead",
            "playstyles": ("economic", "social", "stealth"),
            "reward": _reward_with_items({
                "credits": 12,
                "standing": 1,
            }, "credstick_chip"),
            "risk": "low",
            "pressure": "low",
            "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
            "status": "active",
            "seed_tick": int(getattr(sim, "tick", 0)),
        }

    if kind == "records_pull":
        return {
            "key": f"records_pull:intel:{property_id}",
            "title": "Records Pull",
            "summary": f"Loose records around {prop_name} can still turn into routes, names, and something you can use on the next leg.",
            "kind": "records_pull",
            "source": "intel",
            "chunk": (cx, cy),
            "location": "lead",
            "playstyles": ("stealth", "economic", "social"),
            "reward": _reward_with_items({
                "credits": 8,
                "intel": max(2, _safe_int(confidence * 4, default=2)),
            }, chooser.choice(("credstick_chip", "transit_daypass"))),
            "risk": "exposed",
            "pressure": "medium",
            "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
            "status": "active",
            "seed_tick": int(getattr(sim, "tick", 0)),
        }

    if kind == "watch_post":
        return {
            "key": f"watch_post:intel:{property_id}",
            "title": "Watch Post",
            "summary": f"A quiet watch around {prop_name} is enough to catch routines, handoffs, and who really owns the block.",
            "kind": "watch_post",
            "source": "intel",
            "chunk": (cx, cy),
            "location": "lead",
            "playstyles": ("stealth", "social"),
            "reward": _reward_with_items({
                "intel": max(2, _safe_int(confidence * 4, default=2)),
            }, chooser.choice(("hydration_salts", "med_gel"))),
            "risk": "low",
            "pressure": "low",
            "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
            "status": "active",
            "seed_tick": int(getattr(sim, "tick", 0)),
        }

    if kind == "debt_marker":
        return {
            "key": f"debt_marker:intel:{property_id}",
            "title": "Debt Marker",
            "summary": f"Debt around {prop_name} is pushing someone there toward risky side deals.",
            "kind": "debt_marker",
            "source": "intel",
            "chunk": (cx, cy),
            "location": "lead",
            "playstyles": ("social", "economic", "stealth"),
            "reward": {
                "credits": 10,
                "intel": max(1, _safe_int(confidence * 2, default=1)),
            },
            "risk": "low",
            "pressure": "low",
            "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
            "status": "active",
            "seed_tick": int(getattr(sim, "tick", 0)),
        }

    if kind == "supply_shortage":
        return {
            "key": f"supply_shortage:intel:{property_id}",
            "title": "Shortage Tip",
            "summary": f"Supply around {prop_name} is thin, and somebody nearby is paying for fast cover.",
            "kind": "supply_shortage",
            "source": "intel",
            "chunk": (cx, cy),
            "location": "lead",
            "playstyles": ("economic", "stealth"),
            "reward": {
                "credits": 12,
                "standing": 1,
            },
            "risk": "low",
            "pressure": "low",
            "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
            "status": "active",
            "seed_tick": int(getattr(sim, "tick", 0)),
        }

    return {
        "key": f"intel:{property_id}",
        "title": "Follow a Lead",
        "summary": f"Verify intel around {prop_name}.",
        "kind": "lead_followup",
        "source": "intel",
        "chunk": (cx, cy),
        "location": "lead",
        "playstyles": ("social", "stealth", "economic"),
        "reward": {"credits": 6, "intel": max(1, _safe_int(confidence * 3, default=1))},
        "risk": "low",
        "pressure": "low",
        "requirements": {"visit_chunk": (cx, cy), "property_id": property_id},
        "status": "active",
        "seed_tick": int(getattr(sim, "tick", 0)),
    }


def _chunk_opportunity_candidate(sim, cx, cy, objective_id, rng, origin_chunk=None):
    chunk = sim.world.get_chunk(cx, cy)
    desc = sim.world.overworld_descriptor(cx, cy)
    interest = sim.world.overworld_interest(cx, cy, descriptor=desc)
    travel = sim.world.overworld_travel_profile(cx, cy, descriptor=desc, interest=interest)
    discovery = sim.world.overworld_discovery_profile(
        cx,
        cy,
        descriptor=desc,
        interest=interest,
        travel=travel,
    )
    site_kinds = _chunk_site_kinds(chunk)
    identity = sim.world.overworld_identity_profile(
        cx,
        cy,
        descriptor=desc,
        interest=interest,
        travel=travel,
        discovery=discovery,
        site_kinds=site_kinds,
    )
    economy = chunk_economy_profile(sim, chunk)
    features = _chunk_features(chunk)
    support_tags = {
        str(tag).strip().lower()
        for tag in travel.get("support_tags", ())
        if str(tag).strip()
    }
    discovery_kind = str(discovery.get("kind", "")).strip().lower()
    risk_label = str(travel.get("risk_label", "low")).strip().lower() or "low"
    area_type = str(desc.get("area_type", "city")).strip().lower() or "city"
    district_type = str(desc.get("district_type", "unknown")).strip().lower() or "unknown"
    theme_id = str(identity.get("theme_id", "") or "").strip().lower()
    identity_label = str(identity.get("label", "") or "").strip()
    context_label = str(economy.get("context_label", "")).strip()
    landmark = desc.get("landmark") or desc.get("nearest_landmark") or {}
    landmark_name = str(landmark.get("name", "")).strip()
    location = f"{area_type}/{district_type}"
    origin = _chunk_tuple(origin_chunk) or (0, 0)
    distance = _manhattan(origin, (cx, cy))
    can_stage_local_handoff = bool(
        tuple(chunk.get("sites", ()) or ())
        or site_kinds
        or features["has_storefront"]
        or features["has_finance"]
        or features["site_services"]
    )

    candidates = []

    if discovery_kind == "salvage":
        salvage_item_pool = _discovery_item_pool(
            discovery,
            ("battery_pack", "scrap_circuit", "pocket_multitool", "prybar"),
        )
        parts_item_id = str(rng.choice(salvage_item_pool)).strip().lower() if salvage_item_pool else "battery_pack"
        parts_item_label = _item_label(parts_item_id)
        candidates.append({
            "kind": "salvage_sweep",
            "source": "overworld_tag",
            "title": "Salvage Sweep",
            "summary": "Work salvage routes for quick returns.",
            "playstyles": ("economic", "stealth", "combat"),
            "reward": _reward_with_items({"credits": rng.randint(16, 32), "standing": 1}, rng.choice(("credstick_chip", "light_ammo_box"))),
            "weight": 1.35,
        })
        candidates.append({
            "kind": "parts_recovery",
            "source": "overworld_tag",
            "title": "Parts Recovery",
            "summary": (
                f"A local buyer wants {parts_item_label} off the salvage route "
                "before the scrappers get there first."
            ) if can_stage_local_handoff else "Strip the workable parts before the scrappers get there first.",
            "playstyles": ("economic", "stealth", "social") if can_stage_local_handoff else ("economic", "stealth", "combat"),
            "reward": _reward_with_items({"credits": rng.randint(14, 28), "intel": 1}, rng.choice(("light_ammo_box", "pocket_multitool"))),
            **({
                "requirements": {
                    "delivery_chunk": (int(cx), int(cy)),
                    "visit_chunk": (int(cx), int(cy)),
                    "require_item_id": parts_item_id,
                    "require_item_qty": 1,
                    "consume_item": True,
                    "provide_item": False,
                    "item_label": parts_item_label,
                    "acquisition_hint": "buy_or_find",
                },
            } if can_stage_local_handoff else {}),
            "weight": 1.28,
        })
    elif discovery_kind == "water":
        water_item_pool = _discovery_item_pool(
            discovery,
            ("bottled_water", "hydration_salts", "street_ration"),
        )
        water_item_id = str(rng.choice(water_item_pool)).strip().lower() if water_item_pool else "bottled_water"
        water_item_label = _item_label(water_item_id)
        candidates.append({
            "kind": "water_run",
            "source": "overworld_tag",
            "title": "Water Relay",
            "summary": (
                f"Carry {water_item_label} along the water route before the people leaning on it run dry."
            ) if can_stage_local_handoff else "Use the water route for recovery and side deals.",
            "playstyles": ("social", "economic", "stealth"),
            "reward": {"credits": rng.randint(8, 16), "energy": 6, "safety": 4},
            **({
                "requirements": {
                    "delivery_chunk": (int(cx), int(cy)),
                    "visit_chunk": (int(cx), int(cy)),
                    "require_item_id": water_item_id,
                    "require_item_qty": 1,
                    "consume_item": True,
                    "provide_item": False,
                    "item_label": water_item_label,
                    "acquisition_hint": "buy_or_find",
                },
            } if can_stage_local_handoff else {}),
            "weight": 1.2,
        })
    elif discovery_kind == "tools":
        tool_item_pool = _discovery_item_pool(
            discovery,
            ("lockpick_kit", "pocket_multitool"),
        )
        tool_pickup_item_id = str(rng.choice(tool_item_pool)).strip().lower() if tool_item_pool else "lockpick_kit"
        tool_pickup_item_label = _item_label(tool_pickup_item_id)
        tool_procure_item_id = str(rng.choice(tool_item_pool)).strip().lower() if tool_item_pool else "lockpick_kit"
        tool_procure_item_label = _item_label(tool_procure_item_id)
        candidates.append({
            "kind": "tool_pickup",
            "source": "overworld_tag",
            "title": "Tool Pickup",
            "summary": (
                f"A local cache is holding {tool_pickup_item_label}; make the pickup and walk it to a buyer before the district notices the gap."
            ) if can_stage_local_handoff else "Find workable tools and move them to buyers.",
            "playstyles": ("economic", "stealth", "social") if can_stage_local_handoff else ("economic", "stealth"),
            "reward": _reward_with_items({"credits": rng.randint(12, 26), "intel": 1}, rng.choice(("lockpick_kit", "pocket_multitool"))),
            **({
                "requirements": {
                    "pickup_chunk": (int(cx), int(cy)),
                    "delivery_chunk": (int(cx), int(cy)),
                    "visit_chunk": (int(cx), int(cy)),
                    "require_item_id": tool_pickup_item_id,
                    "require_item_qty": 1,
                    "consume_item": True,
                    "provide_item": True,
                    "item_label": tool_pickup_item_label,
                    "acquisition_hint": "pickup",
                },
            } if can_stage_local_handoff else {}),
            "weight": 1.25,
        })
        candidates.append({
            "kind": "tool_procurement",
            "source": "overworld_tag",
            "title": "Tool Procurement",
            "summary": f"A local buyer wants {tool_procure_item_label} before the district notices the gap.",
            "playstyles": ("economic", "stealth", "social"),
            "reward": _reward_with_items({"credits": rng.randint(14, 28), "standing": 1}, rng.choice(("lockpick_kit", "pocket_multitool"))),
            "requirements": {
                "delivery_chunk": (int(cx), int(cy)),
                "visit_chunk": (int(cx), int(cy)),
                "require_item_id": tool_procure_item_id,
                "require_item_qty": 1,
                "consume_item": True,
                "provide_item": False,
                "item_label": tool_procure_item_label,
                "acquisition_hint": "buy_or_find",
            },
            "weight": 1.18,
        })
    elif discovery_kind == "supplies":
        supply_item_pool = _discovery_item_pool(
            discovery,
            ("med_gel", "hydration_salts", "street_ration", "bottled_water"),
        )
        supply_item_id = str(rng.choice(supply_item_pool)).strip().lower() if supply_item_pool else "med_gel"
        supply_item_label = _item_label(supply_item_id)
        candidates.append({
            "kind": "supply_grab",
            "source": "overworld_tag",
            "title": "Supply Grab",
            "summary": (
                f"A cache nearby is holding {supply_item_label}; make the pickup and move it before the locals strip it clean."
            ) if can_stage_local_handoff else "Leverage local supply caches.",
            "playstyles": ("economic", "social", "stealth"),
            "reward": _reward_with_items({"credits": rng.randint(10, 22), "energy": 4, "safety": 2}, rng.choice(("med_gel", "hydration_salts"))),
            **({
                "requirements": {
                    "pickup_chunk": (int(cx), int(cy)),
                    "delivery_chunk": (int(cx), int(cy)),
                    "visit_chunk": (int(cx), int(cy)),
                    "require_item_id": supply_item_id,
                    "require_item_qty": 1,
                    "consume_item": True,
                    "provide_item": True,
                    "item_label": supply_item_label,
                    "acquisition_hint": "pickup",
                },
            } if can_stage_local_handoff else {}),
            "weight": 1.15,
        })
    elif discovery_kind == "landmark":
        title = "Landmark Survey"
        summary = "Use a landmark vantage for route intelligence."
        if landmark_name:
            title = "Landmark Survey"
            summary = f"Use {landmark_name} as a route anchor."
        candidates.append({
            "kind": "landmark_survey",
            "source": "overworld_tag",
            "title": title,
            "summary": summary,
            "playstyles": ("social", "stealth", "economic"),
            "reward": {"credits": rng.randint(8, 14), "intel": 2},
            "weight": 1.3,
        })
        candidates.append({
            "kind": "watch_post",
            "source": "overworld_tag",
            "title": "Watch Post",
            "summary": "Hold the vantage long enough to catch quiet movement and likely handoffs.",
            "playstyles": ("stealth", "social"),
            "reward": _reward_with_items({"credits": rng.randint(6, 12), "intel": 2}, rng.choice(("hydration_salts", "med_gel"))),
            "weight": 1.16,
        })

    if area_type != "city" and theme_id:
        candidates.extend(
            _specialty_chunk_opportunity_candidates(
                theme_id,
                chunk=(cx, cy),
                identity_label=identity_label,
                travel=travel,
                discovery=discovery,
                sites=tuple(chunk.get("sites", ()) or ()),
                rng=rng,
            )
        )

    if features["has_storefront"] or "trade" in support_tags:
        candidates.append({
            "kind": "trade_loop",
            "source": "property_service",
            "title": "Street Exchange",
            "summary": "Work the local storefront loop for profit.",
            "playstyles": ("economic", "social", "stealth"),
            "reward": _reward_with_items({"credits": rng.randint(12, 28), "standing": 1}, "credstick_chip"),
            "weight": 1.1,
        })
        candidates.append({
            "kind": "contact_run",
            "source": "property_service",
            "title": "Contact Run",
            "summary": "A local face is open to a discreet meet if you carry yourself like a regular.",
            "playstyles": ("social", "stealth", "economic"),
            "reward": _reward_with_items({"credits": rng.randint(10, 18), "standing": 2}, rng.choice(("transit_daypass", "street_ration"))),
            "weight": 1.04,
        })
        candidates.append({
            "kind": "backroom_buyback",
            "source": "property_service",
            "title": "Backroom Buyback",
            "summary": "A quiet buyer on the strip is taking compact tools and leftovers at a premium.",
            "playstyles": ("economic", "social", "stealth"),
            "reward": _reward_with_items({"credits": rng.randint(14, 26), "standing": 1}, rng.choice(("lockpick_kit", "pocket_multitool"))),
            "weight": 0.98,
        })

    if features["has_finance"] or "services" in support_tags:
        candidates.append({
            "kind": "paper_trail",
            "source": "property_service",
            "title": "Paper Trail Run",
            "summary": "Use service channels to stabilize your run.",
            "playstyles": ("social", "economic", "stealth"),
            "reward": _reward_with_items({"credits": rng.randint(10, 20), "standing": 2}, rng.choice(("credstick_chip", "transit_daypass"))),
            "weight": 1.0,
        })
        candidates.append({
            "kind": "claims_chase",
            "source": "property_service",
            "title": "Claims Chase",
            "summary": "There is money hung up in local claim traffic if you can get there before it clears.",
            "playstyles": ("economic", "social", "stealth"),
            "reward": _reward_with_items({"credits": rng.randint(14, 28), "standing": 1}, "credstick_chip"),
            "weight": 1.02,
        })
        candidates.append({
            "kind": "records_pull",
            "source": "property_service",
            "title": "Records Pull",
            "summary": "Loose paperwork and stale service logs are paying in routes, names, and small leverage.",
            "playstyles": ("stealth", "economic", "social"),
            "reward": _reward_with_items({"credits": rng.randint(8, 18), "intel": 2}, rng.choice(("credstick_chip", "transit_daypass"))),
            "weight": 0.97,
        })

    if "intel" in support_tags or "intel" in features["site_services"]:
        candidates.append({
            "kind": "intel_scout",
            "source": "property_service",
            "title": "Signal Recon",
            "summary": "Collect local intel and route signals.",
            "playstyles": ("social", "stealth"),
            "reward": {"credits": rng.randint(6, 14), "intel": 2},
            "weight": 1.2,
        })
        candidates.append({
            "kind": "watch_post",
            "source": "property_service",
            "title": "Watch Post",
            "summary": "Find the quiet angle and wait for the routine to betray itself.",
            "playstyles": ("stealth", "social"),
            "reward": _reward_with_items({"credits": rng.randint(6, 12), "intel": 2}, rng.choice(("hydration_salts", "med_gel"))),
            "weight": 1.08,
        })

    if "shelter" in support_tags or "shelter" in features["site_services"]:
        candidates.append({
            "kind": "shelter_stop",
            "source": "property_service",
            "title": "Safehouse Stop",
            "summary": "Use shelter points to recover for the next leg.",
            "playstyles": ("social", "stealth", "economic"),
            "reward": {"credits": rng.randint(6, 12), "energy": 6, "safety": 6},
            "weight": 0.95,
        })

    if context_label:
        candidates.append({
            "kind": "district_contract",
            "source": "economy_profile",
            "title": "District Contract",
            "summary": f"Leverage {context_label} conditions while they last.",
            "playstyles": ("economic", "social", "stealth"),
            "reward": _reward_with_items({"credits": rng.randint(14, 30), "standing": 1}, rng.choice(("credstick_chip", "transit_daypass"))),
            "weight": 0.9,
        })

    if distance >= 2:
        item_id = _pick_courier_item(rng)
        item_label = _item_label(item_id)
        origin_dir = _chunk_direction((cx, cy), origin)
        origin_distance = _manhattan((cx, cy), origin)
        source_party, dest_party = rng.choice(COURIER_PARTIES)

        candidates.append({
            "kind": "distance_delivery",
            "source": "contact",
            "title": "Courier Drop",
            "summary": (
                f"Carry {item_label} from {source_party} to {dest_party} "
                f"{opportunity_distance_text(distance, _chunk_direction(origin, (cx, cy)))}."
            ),
            "playstyles": ("social", "stealth", "economic"),
            "reward": {"credits": rng.randint(16, 34), "standing": 1},
            "requirements": {
                "pickup_chunk": origin,
                "delivery_chunk": (int(cx), int(cy)),
                "visit_chunk": (int(cx), int(cy)),
                "require_item_id": item_id,
                "require_item_qty": 1,
                "consume_item": True,
                "provide_item": True,
                "item_label": item_label,
                "acquisition_hint": "provided",
            },
            "key": f"distance_delivery:{origin[0]}:{origin[1]}:{cx}:{cy}:{item_id}",
            "weight": 1.1 + min(0.6, distance * 0.08),
        })

        candidates.append({
            "kind": "distance_delivery_procure",
            "source": "contact",
            "title": "Procure and Deliver",
            "summary": (
                f"Buy or find {item_label}, then deliver it to {dest_party} "
                f"{opportunity_distance_text(distance, _chunk_direction(origin, (cx, cy)))}."
            ),
            "playstyles": ("economic", "social", "stealth"),
            "reward": {"credits": rng.randint(22, 42), "standing": 1, "intel": 1},
            "requirements": {
                "delivery_chunk": (int(cx), int(cy)),
                "visit_chunk": (int(cx), int(cy)),
                "require_item_id": item_id,
                "require_item_qty": 1,
                "consume_item": True,
                "provide_item": False,
                "item_label": item_label,
                "acquisition_hint": "buy_or_find",
            },
            "key": f"distance_delivery_procure:{cx}:{cy}:{item_id}",
            "weight": 1.0 + min(0.6, distance * 0.09),
        })

        candidates.append({
            "kind": "distance_pickup",
            "source": "contact",
            "title": "Remote Pickup",
            "summary": (
                f"Pick up {item_label} from {dest_party} "
                f"{opportunity_distance_text(distance, _chunk_direction(origin, (cx, cy)))} "
                f"and bring it back {opportunity_distance_text(origin_distance, origin_dir)}."
            ),
            "playstyles": ("social", "stealth", "economic"),
            "reward": {"credits": rng.randint(18, 36), "standing": 1},
            "requirements": {
                "pickup_chunk": (int(cx), int(cy)),
                "delivery_chunk": origin,
                "visit_chunk": origin,
                "require_item_id": item_id,
                "require_item_qty": 1,
                "consume_item": True,
                "provide_item": True,
                "item_label": item_label,
                "acquisition_hint": "pickup",
            },
            "key": f"distance_pickup:{cx}:{cy}:{origin[0]}:{origin[1]}:{item_id}",
            "weight": 1.05 + min(0.65, distance * 0.1),
        })
        medical_item_id = rng.choice(("med_gel", "micro_medkit"))
        medical_item_label = _item_label(medical_item_id)
        candidates.append({
            "kind": "medical_drop",
            "source": "contact",
            "title": "Medical Drop",
            "summary": (
                f"Carry {medical_item_label} to a quiet patient handoff "
                f"{opportunity_distance_text(distance, _chunk_direction(origin, (cx, cy)))}."
            ),
            "playstyles": ("social", "stealth", "economic"),
            "reward": _reward_with_items({"credits": rng.randint(18, 34), "standing": 1}, "med_gel"),
            "requirements": {
                "pickup_chunk": origin,
                "delivery_chunk": (int(cx), int(cy)),
                "visit_chunk": (int(cx), int(cy)),
                "require_item_id": medical_item_id,
                "require_item_qty": 1,
                "consume_item": True,
                "provide_item": True,
                "item_label": medical_item_label,
                "acquisition_hint": "provided",
            },
            "key": f"medical_drop:{origin[0]}:{origin[1]}:{cx}:{cy}:{medical_item_id}",
            "weight": 1.0 + min(0.55, distance * 0.08),
        })
        dead_drop_item_id = rng.choice(("light_ammo_box", "transit_daypass", "access_badge"))
        dead_drop_item_label = _item_label(dead_drop_item_id)
        candidates.append({
            "kind": "dead_drop_return",
            "source": "contact",
            "title": "Dead Drop Return",
            "summary": (
                f"Lift {dead_drop_item_label} from a remote dead drop "
                f"{opportunity_distance_text(distance, _chunk_direction(origin, (cx, cy)))} "
                f"and bring it back {opportunity_distance_text(origin_distance, origin_dir)}."
            ),
            "playstyles": ("stealth", "social", "economic"),
            "reward": _reward_with_items({"credits": rng.randint(18, 36), "standing": 1}, rng.choice(("lockpick_kit", "pocket_multitool"))),
            "requirements": {
                "pickup_chunk": (int(cx), int(cy)),
                "delivery_chunk": origin,
                "visit_chunk": origin,
                "require_item_id": dead_drop_item_id,
                "require_item_qty": 1,
                "consume_item": True,
                "provide_item": True,
                "item_label": dead_drop_item_label,
                "acquisition_hint": "pickup",
            },
            "key": f"dead_drop_return:{cx}:{cy}:{origin[0]}:{origin[1]}:{dead_drop_item_id}",
            "weight": 1.02 + min(0.62, distance * 0.09),
        })

    if not candidates:
        candidates.append({
            "kind": "local_lead",
            "source": "overworld_tag",
            "title": "Local Lead",
            "summary": "Check this chunk for workable opportunities.",
            "playstyles": ("economic", "social", "stealth"),
            "reward": {"credits": rng.randint(8, 16), "intel": 1},
            "weight": 0.8,
        })

    objective_prefs = OBJECTIVE_PREFERENCES.get(str(objective_id or "").strip().lower(), set())
    weighted = []
    for candidate in candidates:
        weight = float(candidate.get("weight", 1.0))
        if candidate.get("kind") in objective_prefs:
            weight += 1.15
        if area_type != "city" and candidate.get("source") in {"overworld_tag", "specialty_theme"}:
            weight += 0.35
        weighted.append((candidate, max(0.05, weight)))

    total = sum(weight for _candidate, weight in weighted)
    roll = rng.uniform(0.0, total if total > 0.0 else 1.0)
    chosen = weighted[-1][0]
    cursor = 0.0
    for candidate, weight in weighted:
        cursor += weight
        if roll <= cursor:
            chosen = candidate
            break

    key = str(chosen.get("key", "")).strip().lower()
    if not key:
        key = f"{chosen['kind']}:{cx}:{cy}"
    requirements = chosen.get("requirements")
    if not isinstance(requirements, dict):
        requirements = {"visit_chunk": (int(cx), int(cy))}
    elif "visit_chunk" not in requirements:
        requirements = dict(requirements)
        requirements["visit_chunk"] = (int(cx), int(cy))
    return {
        "key": key,
        "title": str(chosen.get("title", "Opportunity")).strip() or "Opportunity",
        "summary": str(chosen.get("summary", "")).strip(),
        "kind": str(chosen.get("kind", "local_lead")).strip().lower() or "local_lead",
        "source": str(chosen.get("source", "overworld_tag")).strip().lower() or "overworld_tag",
        "chunk": (int(cx), int(cy)),
        "location": location,
        "playstyles": tuple(chosen.get("playstyles", ("economic", "social"))),
        "reward": _reward_with_travel_bias(
            chosen.get("reward", {}),
            risk_label=risk_label,
            travel=travel,
            distance=distance,
        ),
        "risk": risk_label,
        "pressure": _risk_pressure(risk_label),
        "requirements": requirements,
        "organization_name": _text(chosen.get("organization_name")),
        "contact_name": _text(chosen.get("contact_name")),
        "contact_role": _text(chosen.get("contact_role")),
        "anchor_site_name": _text(chosen.get("anchor_site_name")),
        "anchor_site_kind": _text(chosen.get("anchor_site_kind")).lower(),
        "anchor_site_id": _text(chosen.get("anchor_site_id")),
        "status": "active",
        "seed_tick": int(getattr(sim, "tick", 0)),
    }


def _append_opportunity(state, opportunity, existing_keys):
    key = str(opportunity.get("key", "")).strip().lower()
    if not key or key in existing_keys:
        return None
    next_id = max(1, _safe_int(state.get("next_id"), default=1))
    entry = dict(opportunity)
    entry["id"] = next_id
    entry["status"] = "active"
    if "origin_chunk" not in entry and _chunk_tuple(state.get("origin_chunk")):
        entry["origin_chunk"] = _chunk_tuple(state.get("origin_chunk"))
    state["next_id"] = next_id + 1
    state["active"].append(entry)
    existing_keys.add(key)
    return entry


def append_external_opportunity(
    sim,
    opportunity,
    *,
    observer_eid=None,
    awareness_state="heard",
    confidence=0.0,
    source="unknown",
):
    state = _state(sim)
    existing_keys = {
        str(entry.get("key", "")).strip().lower()
        for entry in state.get("active", ())
        if isinstance(entry, dict)
    }
    entry = _append_opportunity(state, opportunity, existing_keys)
    if not isinstance(entry, dict):
        return None
    if observer_eid is not None:
        _upsert_observer_intel(
            sim,
            state,
            observer_eid=observer_eid,
            opportunity_id=int(entry.get("id", 0) or 0),
            awareness_state=awareness_state,
            confidence=confidence,
            source=source,
        )
    return entry


def _service_job_actor_name(sim, eid):
    identities = sim.ecs.get(CreatureIdentity) if sim is not None else {}
    identity = identities.get(eid) if identities else None
    if identity is not None:
        name = str(
            getattr(identity, "personal_name", "")
            or getattr(identity, "common_name", "")
            or getattr(identity, "creature_type", "")
            or ""
        ).strip()
        if name:
            return name.title()
    return f"Person {eid}"


def _service_job_claims(sim):
    state = _state(sim)
    claims = state.get("service_job_board_claims")
    if not isinstance(claims, dict):
        claims = {}
        state["service_job_board_claims"] = claims
    return claims


def _service_job_origin_chunk(sim, issuer_prop, actor_eid=None):
    if sim is not None and isinstance(issuer_prop, dict):
        try:
            return tuple(
                sim.chunk_coords(
                    int(issuer_prop.get("x", 0)),
                    int(issuer_prop.get("y", 0)),
                )
            )
        except Exception:
            pass
        metadata = issuer_prop.get("metadata") if isinstance(issuer_prop.get("metadata"), dict) else {}
        chunk = _chunk_tuple(metadata.get("chunk") or metadata.get("origin_chunk"))
        if chunk is not None:
            return chunk
    if actor_eid is not None:
        return _player_chunk(sim, actor_eid)
    return None


def _service_job_claim_key(job_key):
    return str(job_key or "").strip()


def _service_job_claim_for(sim, job_key):
    key = _service_job_claim_key(job_key)
    if not key:
        return None
    claim = _service_job_claims(sim).get(key)
    return claim if isinstance(claim, dict) else None


def _service_job_claim_active(claim):
    return isinstance(claim, dict) and str(claim.get("status", "") or "").strip().lower() == "active"


def _service_job_claim_terminal(claim):
    if not isinstance(claim, dict):
        return False
    return str(claim.get("status", "") or "").strip().lower() in {"completed", "failed", "expired", "cancelled"}


def _service_job_claim_terminal_tick(claim):
    if not isinstance(claim, dict):
        return -1
    for key in (
        "terminal_tick",
        "completed_tick",
        "failed_tick",
        "expired_tick",
        "cancelled_tick",
    ):
        tick = _safe_int(claim.get(key), default=-1)
        if tick >= 0:
            return tick
    return _safe_int(claim.get("claimed_tick"), default=-1)


def prune_service_job_board_claims(sim, max_age_hours=24):
    if sim is None:
        return 0
    claims = _service_job_claims(sim)
    if not claims:
        return 0
    now = int(getattr(sim, "tick", 0) or 0)
    try:
        hours = max(0.0, float(max_age_hours))
    except (TypeError, ValueError):
        hours = 24.0
    max_age_ticks = max(1, int(round(hours * _opportunity_ticks_per_hour(sim))))
    removed = 0
    for job_key, claim in list(claims.items()):
        if _service_job_claim_active(claim):
            continue
        if not _service_job_claim_terminal(claim):
            continue
        terminal_tick = _service_job_claim_terminal_tick(claim)
        if terminal_tick < 0:
            continue
        if now - terminal_tick >= max_age_ticks:
            claims.pop(job_key, None)
            removed += 1
    return removed


def _service_job_claimant_name(sim, actor_eid, fallback="someone"):
    try:
        actor_eid = int(actor_eid)
    except (TypeError, ValueError):
        actor_eid = 0
    if actor_eid > 0:
        return _service_job_actor_name(sim, actor_eid)
    return str(fallback or "someone").strip() or "someone"


def _service_job_offer_with_claim(sim, offer):
    offer = dict(offer or {})
    claim = _service_job_claim_for(sim, offer.get("job_key"))
    if not isinstance(claim, dict) or _service_job_claim_terminal(claim):
        return offer
    status = str(claim.get("status", "") or "").strip().lower()
    claimant_name = str(claim.get("claimant_name", "") or "").strip() or _service_job_claimant_name(
        sim,
        claim.get("claimant_eid"),
    )
    if status:
        offer["claim_status"] = status
        offer["claimant_eid"] = _safe_int(claim.get("claimant_eid"), default=0)
        offer["claimant_name"] = claimant_name
        offer["claimant_kind"] = str(claim.get("claimant_kind", "") or "").strip().lower()
        base_label = str(offer.get("base_label", "") or offer.get("label", "Job") or "Job").strip() or "Job"
        offer["label"] = f"{base_label} -> active / {claimant_name}"
    return offer


def service_job_offer_instruction_lines(offer, *, prop=None):
    offer = offer if isinstance(offer, dict) else {}
    prop_name = str((prop or {}).get("name", "") or offer.get("issuer_property_name", "") or "the office").strip()
    target_name = str(offer.get("target_property_name", "") or offer.get("target_name", "") or "the target").strip()
    short_step = str(offer.get("short_step", "") or "").strip()
    summary = str(offer.get("summary", "") or "").strip()
    deadline_hours = max(1, _safe_int(offer.get("deadline_hours"), default=8))
    pay = max(0, _safe_int(offer.get("pay"), default=0))
    standing = max(0, _safe_int(offer.get("standing"), default=0))
    failure_text = str(offer.get("failure_text", "") or "").strip()
    claim_status = str(offer.get("claim_status", "") or "").strip().lower()
    claimant_name = str(offer.get("claimant_name", "") or "").strip()

    lines = []
    if claim_status == "active" and claimant_name:
        lines.append(f"Status: active / {claimant_name}.")
    if summary:
        lines.append(summary)
    elif short_step:
        lines.append(f"From {prop_name}, {short_step}.")
    if short_step:
        lines.append(f"Next: {short_step}.")
    elif target_name:
        lines.append(f"Next: go to {target_name} and check in.")
    lines.append(f"Deadline: {deadline_hours}h. Reward: {pay}c, standing +{standing}.")
    if failure_text:
        lines.append(f"Failure: {failure_text}.")
    return tuple(line for line in lines if str(line).strip())


def _service_job_offer_short_step(service, verb, target_name):
    service = str(service or "").strip().lower()
    verb = str(verb or "").strip().lower()
    target_name = str(target_name or "the target").strip() or "the target"
    if service == "courier_jobs":
        if verb == "deliver":
            return f"receive the sealed packet here, then deliver it to {target_name}"
        if verb == "pick up":
            return f"pick up the sealed packet at {target_name}, then bring it back here"
        if verb == "run":
            return f"check in at {target_name}"
        return f"make the handoff at {target_name}"
    if service == "agency_jobs":
        if verb == "day labor":
            return f"check in for day labor at {target_name}"
        if verb == "supply run":
            return f"check in with the supply desk at {target_name}"
        if verb == "salvage check":
            return f"check the salvage lane at {target_name}"
        return f"handle the local errand at {target_name}"
    return f"work the posting at {target_name}"


def _service_job_offer_failure_text(service, verb):
    service = str(service or "").strip().lower()
    verb = str(verb or "").strip().lower()
    if service == "bounty_jobs":
        return "the target dies, the window expires, or pickup no longer applies"
    if service == "courier_jobs":
        if verb in {"deliver", "pick up"}:
            return "the deadline expires, the packet is lost after receipt, or clean courier standing is burned"
        return "the deadline expires or clean courier standing is burned"
    return "the deadline expires or the site can no longer take the work"


def _opportunity_deadline_hours_left(sim, opportunity):
    expire_tick = _safe_int((opportunity or {}).get("expire_tick"), default=0)
    if expire_tick <= 0:
        return 0
    ticks_left = max(0, expire_tick - int(getattr(sim, "tick", 0) or 0))
    return max(1, int(round(ticks_left / max(1, _opportunity_ticks_per_hour(sim)))))


def opportunity_next_step_text(sim, opportunity):
    opportunity = opportunity if isinstance(opportunity, dict) else {}
    requirements = _opportunity_requirements(opportunity)
    kind = str(opportunity.get("kind", "") or "").strip().lower()
    job_action = str(requirements.get("job_action", "") or "").strip().lower()
    item_id = str(requirements.get("require_item_id", "") or "").strip().lower()
    item_label = str(requirements.get("item_label", "") or "").strip() or _item_label(item_id)
    issued_tick = _safe_int(opportunity.get("provided_item_issued_tick"), default=-1)
    pickup_label = _site_label_from_requirement(
        sim,
        requirements,
        property_key="pickup_property_id",
        building_key="pickup_building_id",
        name_key="pickup_property_name",
    )
    delivery_label = _site_label_from_requirement(
        sim,
        requirements,
        property_key="delivery_property_id",
        building_key="delivery_building_id",
        name_key="delivery_property_name",
    )
    target_label = _site_label_from_requirement(sim, requirements)

    bounty_target = _safe_int(requirements.get("bounty_target_eid"), default=0)
    if bounty_target > 0 or kind == "bounty_capture":
        target_name = str(requirements.get("bounty_target_name", "target") or "target").strip() or "target"
        return f"Find {target_name}, drop them or accept surrender, then use the field restraint jab."

    if item_id:
        acquisition_hint = str(requirements.get("acquisition_hint", "") or "").strip().lower()
        if bool(requirements.get("provide_item")) and issued_tick < 0:
            if acquisition_hint == "pickup":
                pickup = pickup_label or "the pickup site"
                return f"Go to {pickup} and receive {item_label}; make room first if your inventory is full."
            pickup = pickup_label or "the issuing counter"
            return f"Receive {item_label} at {pickup}; make room first if your inventory is full."
        delivery = delivery_label or target_label or "the delivery site"
        return f"Deliver {item_label} to {delivery} and use the handoff there."

    if job_action == "day_labor":
        return f"Go to {target_label or 'the work site'} and check in for day labor."
    if job_action == "supply_run":
        return f"Go to {target_label or 'the supply site'} and check in with the supply desk."
    if job_action == "salvage_check":
        return f"Go to {target_label or 'the salvage site'} and check the salvage lane."
    if job_action in {"route", "handoff", "local_errand"}:
        return f"Go to {target_label or 'the target site'} and check in at the counter."

    tags = set(_normalize_activity_tags(requirements.get("recent_activity_tags")))
    if tags:
        return _opportunity_activity_instruction(requirements)
    if target_label:
        return f"Go to {target_label} and interact there."
    return _opportunity_activity_instruction(requirements)


def opportunity_instruction_lines(sim, opportunity):
    opportunity = opportunity if isinstance(opportunity, dict) else {}
    lines = []
    summary = str(opportunity.get("summary", "") or "").strip()
    if summary:
        lines.append(summary)
    next_step = opportunity_next_step_text(sim, opportunity)
    if next_step:
        lines.append(f"Next: {next_step}")
    hours_left = _opportunity_deadline_hours_left(sim, opportunity)
    reward_text = format_reward_text(opportunity.get("reward", {}))
    if hours_left > 0:
        lines.append(f"Deadline: {hours_left}h. Reward: {reward_text}.")
    elif reward_text:
        lines.append(f"Reward: {reward_text}.")
    requirements = _opportunity_requirements(opportunity)
    if _safe_int(requirements.get("bounty_target_eid"), default=0) > 0:
        lines.append("Failure: the target dies, the window expires, or pickup no longer applies.")
    elif str(opportunity.get("contract_family", "") or "").strip().lower() == "courier_jobs":
        if str(requirements.get("require_item_id", "") or "").strip():
            lines.append("Failure: the deadline expires, the packet is lost after receipt, or clean courier standing is burned.")
        else:
            lines.append("Failure: the deadline expires or clean courier standing is burned.")
    elif str(opportunity.get("contract_family", "") or "").strip().lower() == "agency_jobs":
        lines.append("Failure: the deadline expires or the site can no longer take the work.")
    return tuple(line for line in lines if str(line).strip())


def _service_job_property_candidates(sim, issuer_prop, player_eid, *, limit=12):
    if sim is None or not isinstance(issuer_prop, dict):
        return []
    issuer_id = str(issuer_prop.get("id", "") or "").strip()
    origin_chunk = _service_job_origin_chunk(sim, issuer_prop, player_eid)
    try:
        origin_x = int(issuer_prop.get("x", 0))
        origin_y = int(issuer_prop.get("y", 0))
    except (TypeError, ValueError):
        origin_x = origin_y = 0
    rows = []
    for prop in getattr(sim, "properties", {}).values():
        if not isinstance(prop, dict):
            continue
        prop_id = str(prop.get("id", "") or "").strip()
        if not prop_id or prop_id == issuer_id:
            continue
        if str(prop.get("kind", "") or "").strip().lower() != "building":
            continue
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
        if bool(metadata.get("span_parent")):
            continue
        if not (property_is_public(prop) or property_is_storefront(prop) or tuple(site_services_for_property(prop))):
            continue
        try:
            px = int(prop.get("x", 0))
            py = int(prop.get("y", 0))
        except (TypeError, ValueError):
            continue
        try:
            chunk = sim.chunk_coords(px, py)
        except Exception:
            chunk = _chunk_tuple(metadata.get("chunk")) or origin_chunk
        chunk_dist = _manhattan(origin_chunk, chunk) if origin_chunk and chunk else 0
        tile_dist = abs(px - origin_x) + abs(py - origin_y)
        rows.append((chunk_dist, tile_dist, str(prop.get("name", prop_id)).lower(), prop_id, prop, chunk))
    rows.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    return rows[: max(1, int(limit))]


def _service_job_target_npcs(sim, player_eid, *, limit=12):
    if sim is None:
        return []
    positions = sim.ecs.get(Position)
    ai_map = sim.ecs.get(AI)
    rows = []
    for eid, pos in list(positions.items()) if hasattr(positions, "items") else ():
        if eid == player_eid or not ai_map.get(eid):
            continue
        snapshot = _justice_snapshot(sim, eid)
        tier = str(snapshot.get("wanted_tier", "clear") or "clear").strip().lower() or "clear"
        wanted_rank = {"arrest_on_sight": 0, "wanted": 1, "questioning": 2}.get(tier, 3)
        try:
            chunk = sim.chunk_coords(int(pos.x), int(pos.y))
        except Exception:
            chunk = (0, 0)
        rows.append((
            wanted_rank,
            abs(int(chunk[0])) + abs(int(chunk[1])),
            _service_job_actor_name(sim, eid).lower(),
            int(eid),
            pos,
            tier,
        ))
    rows.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    return rows[: max(1, int(limit))]


def service_job_board_offers(sim, player_eid, prop, service, *, limit=4, include_terminal_claims=False):
    service = str(service or "").strip().lower()
    if service not in SERVICE_JOB_BOARD_SERVICES or not isinstance(prop, dict):
        return []
    prune_service_job_board_claims(sim)
    limit = max(1, int(limit))
    prop_id = str(prop.get("id", "") or "").strip()
    prop_name = str(prop.get("name", prop_id) or prop_id).strip() or "the office"
    tick_bucket = int(getattr(sim, "tick", 0) // max(1, _opportunity_ticks_per_hour(sim) * 4))
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:service-job-board:{prop_id}:{service}:{tick_bucket}")
    origin_chunk = _service_job_origin_chunk(sim, prop, player_eid)
    deadline_hours = int(SERVICE_JOB_DEADLINE_HOURS.get(service, 8))
    offers = []

    if service in {"courier_jobs", "agency_jobs"}:
        candidates = _service_job_property_candidates(sim, prop, player_eid, limit=max(limit * 3, 8))
        verbs = ("Deliver", "Pick up", "Run", "Handoff") if service == "courier_jobs" else ("Day labor", "Supply run", "Local errand", "Salvage check")
        base_pay = 28 if service == "courier_jobs" else 34
        for index, row in enumerate(candidates[:limit]):
            chunk_dist, tile_dist, _name_key, target_id, target_prop, target_chunk = row
            target_name = str(target_prop.get("name", target_id) or target_id).strip()
            verb = verbs[(index + rng.randrange(len(verbs))) % len(verbs)]
            verb_key = verb.lower()
            pay = int(base_pay + (chunk_dist * 10) + min(22, tile_dist // 5) + rng.randint(0, 12))
            standing = 1 + int(chunk_dist >= 2)
            job_key = f"service_job:{service}:{prop_id}:{target_id}:{tick_bucket}:{index}"
            short_step = _service_job_offer_short_step(service, verb_key, target_name)
            label_step = {
                "deliver": "deliver packet",
                "pick up": "pickup + return",
                "run": "check in",
                "handoff": "make handoff",
                "day labor": "check in",
                "supply run": "supply check",
                "local errand": "site errand",
                "salvage check": "salvage check",
            }.get(verb_key, "check in")
            if service == "courier_jobs" and verb_key == "deliver":
                summary = f"Receive a sealed packet at {prop_name}; deliver it to {target_name} within {deadline_hours}h."
                job_action = "delivery"
                item_id = SERVICE_JOB_PACKAGE_ITEM_ID
                item_label = "sealed packet"
                requires_package = True
            elif service == "courier_jobs" and verb_key == "pick up":
                summary = f"Pick up a sealed packet at {target_name}; bring it back to {prop_name} within {deadline_hours}h."
                job_action = "pickup"
                item_id = SERVICE_JOB_PACKAGE_ITEM_ID
                item_label = "sealed packet"
                requires_package = True
            elif service == "courier_jobs" and verb_key == "run":
                summary = f"Check in at {target_name} for {prop_name}; no package is issued."
                job_action = "route"
                item_id = ""
                item_label = ""
                requires_package = False
            elif service == "courier_jobs":
                summary = f"Make a counter handoff at {target_name} for {prop_name}; no package is issued."
                job_action = "handoff"
                item_id = ""
                item_label = ""
                requires_package = False
            elif service == "agency_jobs" and verb_key == "day labor":
                summary = f"Check in for day labor at {target_name}; finish within {deadline_hours}h."
                job_action = "day_labor"
                item_id = ""
                item_label = ""
                requires_package = False
            elif service == "agency_jobs" and verb_key == "supply run":
                summary = f"Check in with the supply desk at {target_name}; finish within {deadline_hours}h."
                job_action = "supply_run"
                item_id = ""
                item_label = ""
                requires_package = False
            elif service == "agency_jobs" and verb_key == "salvage check":
                summary = f"Check the salvage lane at {target_name}; finish within {deadline_hours}h."
                job_action = "salvage_check"
                item_id = ""
                item_label = ""
                requires_package = False
            else:
                summary = f"Handle a local errand at {target_name}; finish within {deadline_hours}h."
                job_action = "local_errand"
                item_id = ""
                item_label = ""
                requires_package = False
            offer = {
                "service": service,
                "job_key": job_key,
                "base_label": f"{verb}: {target_name} ({pay}c/{deadline_hours}h) - {label_step}",
                "label": f"{verb}: {target_name} ({pay}c/{deadline_hours}h) - {label_step}",
                "summary": summary,
                "short_step": short_step,
                "failure_text": _service_job_offer_failure_text(service, verb_key),
                "target_property_id": target_id,
                "target_property_name": target_name,
                "target_chunk": tuple(target_chunk or ()),
                "deadline_hours": deadline_hours,
                "pay": pay,
                "standing": standing,
                "kind": "courier_job" if service == "courier_jobs" else "agency_job",
                "verb": verb_key,
                "job_action": job_action,
                "item_id": item_id,
                "item_label": item_label,
                "requires_package": bool(requires_package),
                "origin_chunk": origin_chunk,
                "issuer_property_id": prop_id,
                "issuer_property_name": prop_name,
            }
            claim = _service_job_claim_for(sim, job_key)
            if _service_job_claim_terminal(claim) and not include_terminal_claims:
                continue
            offers.append(_service_job_offer_with_claim(sim, offer))
        return offers

    if service == "bounty_jobs":
        candidates = _service_job_target_npcs(sim, player_eid, limit=max(limit * 3, 8))
        for index, row in enumerate(candidates[:limit]):
            wanted_rank, _dist, _name_key, target_eid, pos, tier = row
            target_name = _service_job_actor_name(sim, target_eid)
            pay = int(72 + ((3 - min(3, wanted_rank)) * 20) + rng.randint(0, 28))
            job_key = f"service_job:{service}:{prop_id}:{target_eid}:{tick_bucket}:{index}"
            try:
                target_chunk = sim.chunk_coords(int(pos.x), int(pos.y))
            except Exception:
                target_chunk = ()
            offer = {
                "service": service,
                "job_key": job_key,
                "base_label": f"Alive pickup: {target_name} ({pay}c/{deadline_hours}h)",
                "label": f"Alive pickup: {target_name} ({pay}c/{deadline_hours}h)",
                "summary": f"Drop or accept surrender, then use the issued restraint jab within {deadline_hours}h.",
                "short_step": f"find {target_name}, drop or accept surrender, then use the restraint jab",
                "failure_text": _service_job_offer_failure_text(service, "bounty"),
                "target_eid": int(target_eid),
                "target_name": target_name,
                "target_chunk": tuple(target_chunk or ()),
                "target_wanted_tier": tier,
                "court_selected": tier not in {"wanted", "arrest_on_sight"},
                "deadline_hours": deadline_hours,
                "pay": pay,
                "standing": 2,
                "kind": "bounty_capture",
                "origin_chunk": origin_chunk,
                "issuer_property_id": prop_id,
                "issuer_property_name": prop_name,
            }
            claim = _service_job_claim_for(sim, job_key)
            if _service_job_claim_terminal(claim) and not include_terminal_claims:
                continue
            offers.append(_service_job_offer_with_claim(sim, offer))
        return offers
    return offers


def _service_job_offer_by_key(sim, player_eid, prop, service, job_key):
    job_key = str(job_key or "").strip()
    for offer in service_job_board_offers(sim, player_eid, prop, service, limit=8):
        if str(offer.get("job_key", "") or "").strip() == job_key:
            return offer
    return None


def _claim_service_job_offer(sim, offer, *, actor_eid, claimant_kind="player"):
    if sim is None or not isinstance(offer, dict):
        return None, {
            "blocked": True,
            "reason": "job_unavailable",
            "message": "That job posting is no longer available.",
        }
    job_key = _service_job_claim_key(offer.get("job_key"))
    if not job_key:
        return None, {
            "blocked": True,
            "reason": "job_unavailable",
            "message": "That job posting is no longer available.",
        }
    claims = _service_job_claims(sim)
    existing = claims.get(job_key)
    if _service_job_claim_active(existing):
        claimant_eid = _safe_int(existing.get("claimant_eid"), default=0)
        claimant_name = str(existing.get("claimant_name", "") or "").strip() or _service_job_claimant_name(
            sim,
            claimant_eid,
        )
        return None, {
            "blocked": True,
            "reason": "already_claimed",
            "claimant_eid": claimant_eid,
            "claimant_name": claimant_name,
            "message": f"That posting is already active for {claimant_name}.",
        }
    actor_name = _service_job_claimant_name(sim, actor_eid)
    now = int(getattr(sim, "tick", 0))
    target_chunk = _chunk_tuple(offer.get("target_chunk"))
    origin_chunk = _chunk_tuple(offer.get("origin_chunk"))
    distance = _manhattan(origin_chunk, target_chunk) if origin_chunk and target_chunk else 0
    deadline_hours = max(1, _safe_int(offer.get("deadline_hours"), default=8))
    due_ticks = min(
        max(
            SERVICE_JOB_NPC_COMPLETE_MIN_TICKS,
            SERVICE_JOB_NPC_COMPLETE_MIN_TICKS + (distance * 80),
        ),
        SERVICE_JOB_NPC_COMPLETE_MAX_TICKS,
    )
    claim = {
        "job_key": job_key,
        "status": "active",
        "service": str(offer.get("service", "") or "").strip().lower(),
        "kind": str(offer.get("kind", "") or "").strip().lower(),
        "job_action": str(offer.get("job_action", "") or "").strip().lower(),
        "claimant_eid": _safe_int(actor_eid, default=0),
        "claimant_name": actor_name,
        "claimant_kind": str(claimant_kind or "player").strip().lower() or "player",
        "claimed_tick": now,
        "due_tick": now + int(due_ticks),
        "expire_tick": now + int(deadline_hours * _opportunity_ticks_per_hour(sim)),
        "issuer_property_id": str(offer.get("issuer_property_id", "") or "").strip(),
        "issuer_property_name": str(offer.get("issuer_property_name", "") or "").strip(),
        "target_property_id": str(offer.get("target_property_id", "") or "").strip(),
        "target_property_name": str(offer.get("target_property_name", "") or "").strip(),
        "target_chunk": target_chunk,
        "label": str(offer.get("base_label", "") or offer.get("label", "") or "Service job").strip(),
        "summary": str(offer.get("summary", "") or "").strip(),
        "short_step": str(offer.get("short_step", "") or "").strip(),
        "pay": max(0, _safe_int(offer.get("pay"), default=0)),
        "standing": max(0, _safe_int(offer.get("standing"), default=0)),
        "deadline_hours": deadline_hours,
    }
    claims[job_key] = claim
    return claim, None


def _finish_service_job_claim(sim, job_key, *, status="completed", reason=""):
    claim = _service_job_claim_for(sim, job_key)
    if not _service_job_claim_active(claim):
        return None
    terminal = str(status or "completed").strip().lower() or "completed"
    if terminal not in {"completed", "failed", "expired", "cancelled"}:
        terminal = "completed"
    claim["status"] = terminal
    terminal_tick = int(getattr(sim, "tick", 0))
    claim[f"{terminal}_tick"] = terminal_tick
    claim["terminal_tick"] = terminal_tick
    if reason:
        claim["reason"] = str(reason).strip()
    return claim


def _service_job_claim_target(sim, claim):
    if sim is None or not isinstance(claim, dict):
        return None
    prop_id = str(claim.get("target_property_id", "") or "").strip()
    prop = getattr(sim, "properties", {}).get(prop_id) if prop_id else None
    focus = property_focus_position(prop) if isinstance(prop, dict) else None
    if isinstance(focus, (tuple, list)) and len(focus) >= 3:
        try:
            return (int(focus[0]), int(focus[1]), int(focus[2]))
        except (TypeError, ValueError):
            return None
    if isinstance(prop, dict):
        try:
            return (int(prop.get("x", 0)), int(prop.get("y", 0)), int(prop.get("z", 0)))
        except (TypeError, ValueError):
            return None
    return None


def active_service_job_claim_for_actor(sim, actor_eid):
    try:
        actor_eid = int(actor_eid)
    except (TypeError, ValueError):
        return None
    if actor_eid <= 0:
        return None
    for claim in _service_job_claims(sim).values():
        if not _service_job_claim_active(claim):
            continue
        if _safe_int(claim.get("claimant_eid"), default=0) == actor_eid:
            return claim
    return None


def service_job_claim_target(sim, claim):
    return _service_job_claim_target(sim, claim)


def _service_job_claim_at_target(sim, claim, pos=None, *, radius=1):
    if sim is None or not isinstance(claim, dict):
        return False, None
    target = _service_job_claim_target(sim, claim)
    if target is None:
        return False, None
    if pos is None:
        npc_eid = _safe_int(claim.get("claimant_eid"), default=0)
        if npc_eid > 0:
            pos = sim.ecs.get(Position).get(npc_eid)
    if pos is None:
        return False, target
    try:
        if int(getattr(pos, "z", 0) or 0) != int(target[2]):
            return False, target
        distance = abs(int(pos.x) - int(target[0])) + abs(int(pos.y) - int(target[1]))
    except (TypeError, ValueError):
        return False, target
    return distance <= max(0, int(radius)), target


def service_job_claim_is_at_target(sim, claim, pos=None, *, radius=1):
    at_target, _target = _service_job_claim_at_target(sim, claim, pos, radius=radius)
    return bool(at_target)


def mark_service_job_claim_arrival(sim, actor_eid, pos=None):
    claim = active_service_job_claim_for_actor(sim, actor_eid)
    at_target, target = _service_job_claim_at_target(sim, claim, pos, radius=1)
    if not at_target or not isinstance(claim, dict):
        return None
    now = int(getattr(sim, "tick", 0) or 0)
    claim["target"] = target
    claim["last_seen_tick"] = now
    if _safe_int(claim.get("arrived_tick"), default=-1) < 0:
        claim["arrived_tick"] = now
    return claim


def _npc_credit_total(inventory):
    total = 0
    for entry in list(getattr(inventory, "items", ()) or ()):
        if str(entry.get("item_id", "") or "").strip().lower() != "credstick_chip":
            continue
        total += credstick_total_credits(
            quantity=entry.get("quantity", 1),
            metadata=entry.get("metadata"),
        )
    return int(total)


def _npc_needs_service_job(sim, npc_eid, needs):
    if sim is None or needs is None:
        return False
    inventory = sim.ecs.get(Inventory).get(npc_eid)
    credits = _npc_credit_total(inventory) if inventory is not None else 0
    routine = sim.ecs.get(NPCRoutine).get(npc_eid)
    home = getattr(routine, "home", None) if routine is not None else None
    hunger = float(getattr(needs, "hunger", 100.0) or 100.0)
    thirst = float(getattr(needs, "thirst", 100.0) or 100.0)
    energy = float(getattr(needs, "energy", 100.0) or 100.0)
    safety = float(getattr(needs, "safety", 100.0) or 100.0)
    if hunger <= 48.0 or thirst <= 48.0:
        return True
    if credits < 12 and (hunger <= 68.0 or thirst <= 68.0 or energy <= 48.0):
        return True
    if not home and (credits < 30 or safety <= 56.0 or energy <= 44.0):
        return True
    return False


def _nearby_service_job_boards(sim, pos, *, radius=14):
    if sim is None or pos is None:
        return ()
    rows = []
    for prop in getattr(sim, "properties", {}).values():
        if not isinstance(prop, dict):
            continue
        services = set(site_services_for_property(prop))
        services &= {"courier_jobs", "agency_jobs"}
        if not services:
            continue
        try:
            px = int(prop.get("x", 0))
            py = int(prop.get("y", 0))
            pz = int(prop.get("z", 0))
        except (TypeError, ValueError):
            continue
        if pz != int(getattr(pos, "z", 0) or 0):
            continue
        dist = abs(px - int(pos.x)) + abs(py - int(pos.y))
        if dist > int(radius):
            continue
        rows.append((dist, str(prop.get("name", prop.get("id", ""))).lower(), prop))
    rows.sort(key=lambda row: (row[0], row[1], str(row[2].get("id", ""))))
    return tuple(row[2] for row in rows)


def _npc_offer_allowed(offer):
    if not isinstance(offer, dict):
        return False
    if str(offer.get("claim_status", "") or "").strip():
        return False
    service = str(offer.get("service", "") or "").strip().lower()
    if service == "bounty_jobs":
        return False
    if bool(offer.get("requires_package")):
        return False
    return service in {"courier_jobs", "agency_jobs"}


def npc_claim_service_job_from_board(sim, npc_eid):
    if sim is None:
        return None
    if active_service_job_claim_for_actor(sim, npc_eid):
        return None
    now = int(getattr(sim, "tick", 0) or 0)
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    cooldowns = traits.get("npc_service_job_scan_ticks")
    if not isinstance(cooldowns, dict):
        cooldowns = {}
        traits["npc_service_job_scan_ticks"] = cooldowns
    key = str(int(npc_eid))
    next_scan = _safe_int(cooldowns.get(key), default=0)
    if now < next_scan:
        return None
    cooldowns[key] = now + SERVICE_JOB_NPC_SCAN_COOLDOWN_TICKS

    positions = sim.ecs.get(Position)
    pos = positions.get(npc_eid)
    needs = sim.ecs.get(NPCNeeds).get(npc_eid)
    if pos is None or not _npc_needs_service_job(sim, npc_eid, needs):
        return None

    for prop in _nearby_service_job_boards(sim, pos):
        services = tuple(service for service in ("agency_jobs", "courier_jobs") if service in set(site_services_for_property(prop)))
        for service in services:
            for offer in service_job_board_offers(sim, npc_eid, prop, service, limit=5):
                if not _npc_offer_allowed(offer):
                    continue
                claim, blocked = _claim_service_job_offer(
                    sim,
                    offer,
                    actor_eid=npc_eid,
                    claimant_kind="npc",
                )
                if isinstance(claim, dict) and not blocked:
                    target = _service_job_claim_target(sim, claim)
                    if target is not None:
                        claim["target"] = target
                    return claim
    return None


def _reward_npc_service_job(sim, claim):
    if sim is None or not isinstance(claim, dict):
        return
    npc_eid = _safe_int(claim.get("claimant_eid"), default=0)
    if npc_eid <= 0:
        return
    pay = max(0, _safe_int(claim.get("pay"), default=0))
    inventory = sim.ecs.get(Inventory).get(npc_eid)
    if inventory is None:
        inventory = Inventory(capacity=4)
        sim.ecs.add(npc_eid, inventory)
    if pay > 0:
        inventory.add_item(
            "credstick_chip",
            quantity=1,
            stack_max=_item_stack_max("credstick_chip"),
            instance_factory=getattr(sim, "new_item_instance_id", None),
            owner_eid=npc_eid,
            owner_tag="npc_service_job",
            metadata={"stored_credits": pay},
        )
    needs = sim.ecs.get(NPCNeeds).get(npc_eid)
    if needs is not None:
        needs.energy = _clamp(float(getattr(needs, "energy", 0.0) or 0.0) + 8.0)
        needs.safety = _clamp(float(getattr(needs, "safety", 0.0) or 0.0) + 5.0)
        needs.hunger = _clamp(float(getattr(needs, "hunger", 0.0) or 0.0) + 10.0)
        needs.thirst = _clamp(float(getattr(needs, "thirst", 0.0) or 0.0) + 6.0)


def advance_service_job_board_claims(sim):
    if sim is None:
        return []
    prune_service_job_board_claims(sim)
    now = int(getattr(sim, "tick", 0) or 0)
    positions = sim.ecs.get(Position)
    vitalities = sim.ecs.get(Vitality)
    completed = []
    for job_key, claim in list(_service_job_claims(sim).items()):
        if not _service_job_claim_active(claim):
            continue
        if str(claim.get("claimant_kind", "") or "").strip().lower() != "npc":
            continue
        npc_eid = _safe_int(claim.get("claimant_eid"), default=0)
        vitality = vitalities.get(npc_eid)
        if npc_eid <= 0 or positions.get(npc_eid) is None or (vitality is not None and bool(getattr(vitality, "downed", False))):
            _finish_service_job_claim(sim, job_key, status="failed", reason="claimant unavailable")
            continue
        expire_tick = _safe_int(claim.get("expire_tick"), default=0)
        if expire_tick > 0 and now >= expire_tick:
            _finish_service_job_claim(sim, job_key, status="expired", reason="deadline expired")
            continue
        target = _service_job_claim_target(sim, claim)
        if target is None:
            _finish_service_job_claim(sim, job_key, status="failed", reason="target unavailable")
            continue
        pos = positions.get(npc_eid)
        at_target, target = _service_job_claim_at_target(sim, claim, pos, radius=1)
        claim["target"] = target
        if not at_target:
            if now >= _safe_int(claim.get("due_tick"), default=now + 1):
                claim["due_tick"] = now + 60
            continue
        claim["last_seen_tick"] = now
        if _safe_int(claim.get("arrived_tick"), default=-1) < 0:
            claim["arrived_tick"] = now
        if now < _safe_int(claim.get("due_tick"), default=now + 1):
            continue
        _reward_npc_service_job(sim, claim)
        completed_claim = _finish_service_job_claim(sim, job_key, status="completed", reason="npc completed posted work")
        if isinstance(completed_claim, dict):
            completed.append(dict(completed_claim))
    prune_service_job_board_claims(sim)
    return completed


def _grant_bounty_restraint_jab(sim, player_eid, opportunity):
    inventory = sim.ecs.get(Inventory).get(player_eid) if sim is not None else None
    item_def = ITEM_CATALOG.get("field_restraint_jab")
    if inventory is None or not isinstance(item_def, dict):
        return False
    added, _instance_id = inventory.add_item(
        "field_restraint_jab",
        quantity=1,
        stack_max=max(1, _safe_int(item_def.get("stack_max"), default=1)),
        instance_factory=getattr(sim, "new_item_instance_id", None),
        owner_eid=player_eid,
        owner_tag="opportunity",
        metadata={
            "quest_opportunity_id": _safe_int(opportunity.get("id"), default=0),
            "quest_kind": "bounty_capture",
            "issued_by_property_id": str((opportunity.get("issuer") or {}).get("property_id", "") or "").strip(),
        },
    )
    return bool(added)


def _apply_fallback_bounty_heat(sim, target_eid, prop):
    if sim is None or target_eid is None:
        return None
    pos = sim.ecs.get(Position).get(target_eid)
    x = int(getattr(pos, "x", (prop or {}).get("x", 0)) or 0)
    y = int(getattr(pos, "y", (prop or {}).get("y", 0)) or 0)
    first = _record_justice_incident(
        sim,
        target_eid,
        incident_type="bounty_pickup",
        severity=220,
        source_event="bounty_board_pickup",
        property_id=str((prop or {}).get("id", "") or "").strip() or None,
        x=x,
        y=y,
        witnessed=True,
        note="court pickup posted",
    )
    second = _record_justice_incident(
        sim,
        target_eid,
        incident_type="bounty_pickup",
        severity=220,
        source_event="bounty_board_warrant",
        property_id=str((prop or {}).get("id", "") or "").strip() or None,
        x=x,
        y=y,
        witnessed=True,
        note="court pickup posted",
    )
    return second or first


def accept_service_job_offer(sim, player_eid, prop, service, job_key, *, return_blocked=False):
    offer = _service_job_offer_by_key(sim, player_eid, prop, service, job_key)
    if not isinstance(offer, dict):
        if return_blocked:
            return {
                "blocked": True,
                "reason": "job_unavailable",
                "message": "That job posting is no longer available.",
            }
        return None
    claim, blocked = _claim_service_job_offer(
        sim,
        offer,
        actor_eid=player_eid,
        claimant_kind="player",
    )
    if isinstance(blocked, dict):
        return blocked if return_blocked else None
    service = str(service or "").strip().lower()
    prop_id = str((prop or {}).get("id", "") or "").strip()
    prop_name = str((prop or {}).get("name", prop_id) or prop_id).strip()
    now = int(getattr(sim, "tick", 0))
    deadline_hours = max(1, _safe_int(offer.get("deadline_hours"), default=8))
    expire_tick = now + int(deadline_hours * _opportunity_ticks_per_hour(sim))
    reward = {
        "credits": max(0, _safe_int(offer.get("pay"), default=0)),
        "standing": max(0, _safe_int(offer.get("standing"), default=0)),
    }
    issuer = {
        "property_id": prop_id,
        "property_name": prop_name,
        "relation_kind": "job_issuer",
        "property_standing_delta": 0.03,
        "benefits": ("known_name",),
    }
    metadata = (prop or {}).get("metadata") if isinstance((prop or {}).get("metadata"), dict) else {}
    org_key = str(metadata.get("organization_key", "") or metadata.get("root_organization_key", "") or "").strip()
    if org_key:
        issuer["organization_key"] = org_key
        issuer["organization_standing_delta"] = 0.02

    if service in {"courier_jobs", "agency_jobs"}:
        target_chunk = _chunk_tuple(offer.get("target_chunk"))
        job_action = str(offer.get("job_action", "") or "").strip().lower()
        item_id = str(offer.get("item_id", "") or "").strip().lower()
        item_label = str(offer.get("item_label", "") or "").strip()
        requirements = {
            "player_accepted": True,
            "strict_deadline": True,
            "property_id": str(offer.get("target_property_id", "") or "").strip(),
            "property_name": str(offer.get("target_property_name", "") or "").strip(),
            "visit_chunk": target_chunk,
            "job_action": job_action,
            "job_board_service": service,
            "job_key": str(offer.get("job_key", "") or "").strip(),
        }
        if service == "courier_jobs" and job_action == "delivery" and item_id:
            requirements.update({
                "pickup_chunk": _chunk_tuple(offer.get("origin_chunk")),
                "pickup_property_id": prop_id,
                "pickup_property_name": prop_name,
                "delivery_chunk": target_chunk,
                "delivery_property_id": str(offer.get("target_property_id", "") or "").strip(),
                "delivery_property_name": str(offer.get("target_property_name", "") or "").strip(),
                "require_item_id": item_id,
                "require_item_qty": 1,
                "consume_item": True,
                "provide_item": True,
                "item_label": item_label or _item_label(item_id),
                "acquisition_hint": "issued",
            })
        elif service == "courier_jobs" and job_action == "pickup" and item_id:
            requirements.update({
                "property_id": prop_id,
                "property_name": prop_name,
                "visit_chunk": _chunk_tuple(offer.get("origin_chunk")),
                "pickup_chunk": target_chunk,
                "pickup_property_id": str(offer.get("target_property_id", "") or "").strip(),
                "pickup_property_name": str(offer.get("target_property_name", "") or "").strip(),
                "delivery_chunk": _chunk_tuple(offer.get("origin_chunk")),
                "delivery_property_id": prop_id,
                "delivery_property_name": prop_name,
                "require_item_id": item_id,
                "require_item_qty": 1,
                "consume_item": True,
                "provide_item": True,
                "item_label": item_label or _item_label(item_id),
                "acquisition_hint": "pickup",
            })
        opportunity = {
            "key": offer["job_key"],
            "kind": offer.get("kind"),
            "title": str(offer.get("base_label", "") or offer.get("label", "Service job")).strip(),
            "summary": str(offer.get("summary", "")).strip(),
            "source": "property_service",
            "contract_family": service,
            "risk": "low",
            "chunk": target_chunk,
            "origin_chunk": _chunk_tuple(offer.get("origin_chunk")),
            "seed_tick": now,
            "accepted_tick": now,
            "expire_tick": expire_tick,
            "requirements": requirements,
            "reward": reward,
            "issuer": issuer,
            "job_instructions": tuple(service_job_offer_instruction_lines(offer, prop=prop)),
            "failure_policy": {"fail_on_legal_compromise": service == "courier_jobs"},
        }
    else:
        target_eid = _safe_int(offer.get("target_eid"), default=0)
        if bool(offer.get("court_selected")):
            _apply_fallback_bounty_heat(sim, target_eid, prop)
        opportunity = {
            "key": offer["job_key"],
            "kind": "bounty_capture",
            "title": str(offer.get("base_label", "") or offer.get("label", "Alive pickup")).strip(),
            "summary": str(offer.get("summary", "")).strip(),
            "source": "property_service",
            "contract_family": service,
            "risk": "hazardous",
            "chunk": _chunk_tuple(offer.get("target_chunk")),
            "origin_chunk": _chunk_tuple(offer.get("origin_chunk")),
            "seed_tick": now,
            "accepted_tick": now,
            "expire_tick": expire_tick,
            "requirements": {
                "player_accepted": True,
                "strict_deadline": True,
                "bounty_target_eid": target_eid,
                "bounty_target_name": str(offer.get("target_name", "target") or "target").strip(),
                "bounty_restrained": False,
                "field_restraint_item_id": "field_restraint_jab",
                "job_action": "bounty_capture",
                "job_board_service": service,
                "job_key": str(offer.get("job_key", "") or "").strip(),
            },
            "reward": reward,
            "issuer": issuer,
            "job_instructions": tuple(service_job_offer_instruction_lines(offer, prop=prop)),
            "failure_policy": {
                "fail_on_legal_compromise": False,
                "fail_on_target_killed": True,
            },
        }
    entry = append_external_opportunity(
        sim,
        opportunity,
        observer_eid=player_eid,
        awareness_state="confirmed",
        confidence=1.0,
        source="service_job_board",
    )
    if not isinstance(entry, dict):
        _finish_service_job_claim(sim, offer.get("job_key"), status="cancelled", reason="opportunity already active")
        if return_blocked:
            return {
                "blocked": True,
                "reason": "already_active",
                "message": "That job is already active.",
            }
        return None
    if isinstance(claim, dict):
        claim["opportunity_id"] = int(entry.get("id", 0) or 0)
    if isinstance(entry, dict) and service == "bounty_jobs":
        _grant_bounty_restraint_jab(sim, player_eid, entry)
    return entry


def mark_bounty_target_restrained(sim, player_eid, target_eid):
    state = _state(sim)
    target_eid = _safe_int(target_eid, default=0)
    if target_eid <= 0:
        return None
    for entry in state.get("active", ()):
        if not isinstance(entry, dict):
            continue
        requirements = entry.get("requirements") if isinstance(entry.get("requirements"), dict) else {}
        if _safe_int(requirements.get("bounty_target_eid"), default=0) != target_eid:
            continue
        if not bool(requirements.get("player_accepted")):
            continue
        requirements["bounty_restrained"] = True
        requirements["bounty_restrained_tick"] = int(getattr(sim, "tick", 0))
        requirements["bounty_restrained_by_eid"] = player_eid
        return entry
    return None


def _seed_chunk_coordinates(origin, max_radius=8):
    ox, oy = int(origin[0]), int(origin[1])
    coords = []
    for radius in range(1, int(max_radius) + 1):
        ring = []
        for dy in range(-radius, radius + 1):
            dx = radius - abs(dy)
            ring.append((ox + dx, oy + dy))
            if dx != 0:
                ring.append((ox - dx, oy + dy))
        coords.append(ring)
    return coords


def _seed_remote_slice(
    sim,
    *,
    state,
    existing_keys,
    rng,
    objective_id,
    origin_chunk,
    target_count,
    remote_target,
    far_target=0,
    max_radius=9,
    min_distance=REMOTE_SEED_MIN_DISTANCE,
    far_distance=REMOTE_SEED_FAR_DISTANCE,
    visited_chunks=None,
):
    if remote_target <= 0:
        return {"remote_added": 0, "far_added": 0}

    origin_chunk = (int(origin_chunk[0]), int(origin_chunk[1]))
    visited = set(visited_chunks or ())
    rings = _seed_chunk_coordinates(origin_chunk, max_radius=max_radius)
    remote_added = 0
    far_added = 0

    def _pass(require_far):
        nonlocal remote_added, far_added
        for radius, ring in enumerate(rings, start=1):
            if len(state["active"]) >= target_count or remote_added >= remote_target:
                return
            if radius < int(min_distance):
                continue
            shuffled = list(ring)
            rng.shuffle(shuffled)
            for cx, cy in shuffled:
                if len(state["active"]) >= target_count or remote_added >= remote_target:
                    return
                if visited and (cx, cy) in visited:
                    continue
                distance = _manhattan(origin_chunk, (cx, cy))
                if distance < int(min_distance):
                    continue
                if require_far and distance < int(far_distance):
                    continue
                candidate = _chunk_opportunity_candidate(
                    sim,
                    cx,
                    cy,
                    objective_id=objective_id,
                    rng=rng,
                    origin_chunk=origin_chunk,
                )
                if _append_opportunity(state, candidate, existing_keys):
                    remote_added += 1
                    if distance >= int(far_distance):
                        far_added += 1
                    if require_far and far_target > 0 and far_added >= far_target:
                        return

    if far_target > 0:
        _pass(require_far=True)
    if remote_added < remote_target:
        _pass(require_far=False)

    return {"remote_added": remote_added, "far_added": far_added}


def seed_run_opportunities(sim, player_eid=None, rng=None, count_min=MIN_ACTIVE_OPPORTUNITIES, count_max=MAX_ACTIVE_OPPORTUNITIES):
    state = _state(sim)
    if state["seeded"] and state["active"]:
        return state
    before_active_count = _active_opportunity_count(state)

    if not isinstance(rng, random.Random):
        seed = f"{getattr(sim, 'seed', 'seed')}:opportunity-seed"
        rng = random.Random(seed)

    count_min = max(1, int(count_min))
    count_max = max(count_min, int(count_max))
    target_count = rng.randint(count_min, count_max)
    objective = getattr(sim, "world_traits", {}).get("run_objective", {}) if sim is not None else {}
    objective_id = str(objective.get("id", "")).strip().lower()
    origin_chunk = _player_chunk(sim, player_eid)

    state["seeded"] = True
    state["origin_chunk"] = origin_chunk
    state["target_active"] = target_count
    state["seed_tick"] = int(getattr(sim, "tick", 0))

    existing_keys = {
        str(entry.get("key", "")).strip().lower()
        for entry in list(state.get("active", ())) + list(_terminal_entries(state))
        if str(entry.get("key", "")).strip()
    }

    remote_target = min(5, max(2, int(round(target_count * 0.4))))
    far_target = 0
    if remote_target >= 3:
        far_target = min(remote_target, max(1, int(round(target_count * 0.2))))
    _seed_remote_slice(
        sim,
        state=state,
        existing_keys=existing_keys,
        rng=rng,
        objective_id=objective_id,
        origin_chunk=origin_chunk,
        target_count=target_count,
        remote_target=remote_target,
        far_target=far_target,
        max_radius=9,
    )

    rings = _seed_chunk_coordinates(origin_chunk, max_radius=9)
    for ring in rings:
        rng.shuffle(ring)
        for cx, cy in ring:
            if len(state["active"]) >= target_count:
                break
            candidate = _chunk_opportunity_candidate(
                sim,
                cx,
                cy,
                objective_id=objective_id,
                rng=rng,
                origin_chunk=origin_chunk,
            )
            _append_opportunity(state, candidate, existing_keys)
        if len(state["active"]) >= target_count:
            break

    _bootstrap_player_opportunity_intel(sim, state, player_eid, origin_chunk=origin_chunk)
    if _active_opportunity_count(state) > before_active_count:
        _record_opportunity_refill(state, sim, "initial")
    return state


def _contact_and_intel_candidates(sim, player_eid):
    candidates = []
    ledger = sim.ecs.get(ContactLedger).get(player_eid)
    knowledge = sim.ecs.get(PropertyKnowledge).get(player_eid)
    objective_id = _run_objective_id(sim)

    if ledger:
        sorted_contacts = sorted(
            list((ledger.by_property or {}).items()),
            key=lambda row: float((row[1] or {}).get("standing", 0.0)),
            reverse=True,
        )
        for property_id, entry in sorted_contacts[:5]:
            prop = sim.properties.get(property_id)
            if not prop:
                continue
            candidate = _contact_variant_candidate(sim, prop, property_id, entry, objective_id)
            if candidate:
                candidates.append(candidate)

    if knowledge:
        sorted_leads = sorted(
            list((knowledge.known or {}).items()),
            key=lambda row: float((row[1] or {}).get("confidence", 0.0)),
            reverse=True,
        )
        for property_id, entry in sorted_leads[:6]:
            confidence = float((entry or {}).get("confidence", 0.0))
            if confidence < 0.55:
                continue
            prop = sim.properties.get(property_id)
            if not prop:
                continue
            candidate = _intel_variant_candidate(sim, prop, property_id, entry, objective_id)
            if candidate:
                candidates.append(candidate)

    return candidates


def seed_contract_kill_opportunity(sim, player_eid, rng=None):
    """Seed a contract-kill opportunity targeting a live human NPC.

    The opportunity is only visible to the player after they accept it from
    the designated giver NPC via the 'contract' dialogue topic.  Returns the
    seeded opportunity entry, or None if ineligible.
    """
    if sim is None:
        return None

    state = _state(sim)

    # Only allow one active contract_kill at a time.
    existing_keys = {
        str(entry.get("key", "")).strip().lower()
        for entry in list(state.get("active", ())) + list(_terminal_entries(state))
        if str(entry.get("key", "")).strip()
    }
    if any(k.startswith("contract_kill:") for k in existing_keys):
        return None

    if not isinstance(rng, random.Random):
        seed_val = f"{getattr(sim, 'seed', 'seed')}:contract-kill:{getattr(sim, 'tick', 0) // 100}"
        rng = random.Random(seed_val)

    positions = sim.ecs.get(Position)
    ai_comps = sim.ecs.get(AI)
    identity_comps = sim.ecs.get(CreatureIdentity)
    occupation_comps = sim.ecs.get(Occupation)
    memories = sim.ecs.get(NPCMemory)
    socials = sim.ecs.get(NPCSocial)
    traits_map = sim.ecs.get(NPCTraits)
    justices = sim.ecs.get(JusticeProfile)

    candidates = []
    candidate_by_eid = {}
    for eid, ai in ai_comps.items():
        if eid == player_eid:
            continue
        role = str(getattr(ai, "role", "") or "").strip().lower()
        if role in EXCLUDED_CONTRACT_ROLES:
            continue
        identity = identity_comps.get(eid)
        if not identity:
            continue
        if str(getattr(identity, "taxonomy_class", "") or "").strip().lower() != "hominid":
            continue
        pos = positions.get(eid)
        if not pos:
            continue
        row = (eid, ai, identity, pos, occupation_comps.get(eid))
        candidates.append(row)
        candidate_by_eid[int(eid)] = row

    if len(candidates) < 2:
        return None

    def _contract_hit_willingness(eid):
        justice = justices.get(eid)
        traits = traits_map.get(eid) or NPCTraits()
        corruption = _clamp(getattr(justice, "corruption", 0.0) if justice else 0.0, lo=0.0, hi=1.0)
        justice_value = _clamp(getattr(justice, "justice", 0.5) if justice else 0.5, lo=0.0, hi=1.0)
        discipline = _clamp(getattr(traits, "discipline", 0.5), lo=0.0, hi=1.0)
        empathy = _clamp(getattr(traits, "empathy", 0.5), lo=0.0, hi=1.0)
        bravery = _clamp(getattr(traits, "bravery", 0.5), lo=0.0, hi=1.0)
        willingness = (
            0.16
            + (corruption * 0.44)
            + ((1.0 - justice_value) * 0.16)
            + ((1.0 - discipline) * 0.12)
            + (bravery * 0.08)
            - (empathy * 0.06)
        )
        if justice and bool(getattr(justice, "enforce_all", False)):
            willingness -= 0.28
        return _clamp(willingness, lo=0.0, hi=1.0)

    def _contract_hit_support(target_eid, *, exclude_eid=None, max_age=320):
        support = 0.0
        voices = 0
        now = int(getattr(sim, "tick", 0))
        for observer_eid, memory in memories.items():
            if observer_eid == exclude_eid or not memory:
                continue
            local_best = 0.0
            for entry in list(getattr(memory, "entries", ()) or ()):
                if not isinstance(entry, dict):
                    continue
                age = max(0, now - _safe_int(entry.get("tick"), now))
                if age > int(max_age):
                    continue
                data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
                kind = str(entry.get("kind", "")).strip().lower()
                if kind == "actor_reputation" and _safe_int(data.get("actor_eid"), default=0) == int(target_eid):
                    try:
                        approval = float(data.get("approval", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        approval = 0.0
                    if approval >= -0.24:
                        continue
                    local_best = max(local_best, abs(approval) * max(0.08, float(entry.get("strength", 0.0) or 0.0)) * 0.22)
                elif kind == "conflict_side" and _safe_int(data.get("against_eid"), default=0) == int(target_eid):
                    local_best = max(local_best, max(0.08, float(entry.get("strength", 0.0) or 0.0)) * 0.16)
            if local_best > 0.0:
                voices += 1
                support += local_best
        return min(0.42, support), int(voices)

    social_candidates = {}
    now = int(getattr(sim, "tick", 0))
    for giver_eid, giver_ai, _giver_identity, _giver_pos, _giver_occ in candidates:
        giver_memory = memories.get(giver_eid)
        if not giver_memory:
            continue
        willingness = _contract_hit_willingness(giver_eid)
        if willingness < 0.24:
            continue
        social = socials.get(giver_eid)
        for entry in list(getattr(giver_memory, "entries", ()) or ()):
            if not isinstance(entry, dict):
                continue
            age = max(0, now - _safe_int(entry.get("tick"), now))
            data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
            kind = str(entry.get("kind", "")).strip().lower()
            target_eid = 0
            base = 0.0
            reason_tag = "general"

            if kind == "actor_reputation" and age <= 280:
                target_eid = _safe_int(data.get("actor_eid"), default=0)
                try:
                    approval = float(data.get("approval", 0.0) or 0.0)
                except (TypeError, ValueError):
                    approval = 0.0
                if target_eid <= 0 or target_eid == int(giver_eid) or approval > -0.28:
                    continue
                base = abs(approval) * max(0.08, float(entry.get("strength", 0.0) or 0.0))
                against_eid = _safe_int(data.get("against_eid"), default=0)
                if against_eid == int(giver_eid):
                    base += 0.12
                    reason_tag = "crossed_giver"
                elif social and against_eid > 0 and against_eid in social.bonds:
                    bond = social.bonds.get(against_eid, {})
                    bond_score = (float(bond.get("trust", 0.0) or 0.0) * 0.55) + (float(bond.get("closeness", 0.0) or 0.0) * 0.45)
                    if bond_score >= 0.3:
                        base += 0.06 + (bond_score * 0.06)
                        reason_tag = "leaning_on_ally"
            elif kind == "conflict_side" and age <= 180:
                side_eid = _safe_int(data.get("side_eid"), default=0)
                target_eid = _safe_int(data.get("against_eid"), default=0)
                if target_eid <= 0 or target_eid == int(giver_eid):
                    continue
                ally_score = 0.0
                if side_eid == int(giver_eid):
                    ally_score = 0.82
                    reason_tag = "crossed_giver"
                elif social and side_eid > 0 and side_eid in social.bonds:
                    bond = social.bonds.get(side_eid, {})
                    ally_score = (float(bond.get("trust", 0.0) or 0.0) * 0.6) + (float(bond.get("closeness", 0.0) or 0.0) * 0.4)
                    reason_tag = "leaning_on_ally"
                if ally_score < 0.34:
                    continue
                base = max(0.08, float(entry.get("strength", 0.0) or 0.0)) * (0.82 + (ally_score * 0.36))
            else:
                continue

            if target_eid not in candidate_by_eid or target_eid == int(giver_eid):
                continue

            support_score, support_voices = _contract_hit_support(target_eid, exclude_eid=giver_eid)
            total_score = (base * (0.72 + (willingness * 0.68))) + support_score
            if support_voices >= 2:
                total_score += 0.06
            key_pair = (int(giver_eid), int(target_eid))
            current = social_candidates.get(key_pair)
            candidate = {
                "giver_eid": int(giver_eid),
                "target_eid": int(target_eid),
                "score": round(total_score, 3),
                "reason_tag": reason_tag,
                "support_voices": int(support_voices),
            }
            if current is None or float(candidate["score"]) > float(current.get("score", 0.0)):
                social_candidates[key_pair] = candidate

    def _contract_reason_text(candidate):
        if not isinstance(candidate, dict):
            return ""
        voices = _safe_int(candidate.get("support_voices"), default=0)
        tag = str(candidate.get("reason_tag", "general")).strip().lower()
        if tag == "crossed_giver":
            return "Local talk says they have been burning the wrong bridges." if voices >= 2 else "They crossed the wrong local."
        if tag == "leaning_on_ally":
            return "People nearby keep saying they are leaning on the wrong crowd." if voices >= 2 else "They have been leaning on the wrong people."
        return "Local talk says they are becoming a problem." if voices >= 2 else "Somebody local wants them gone."

    def _ensure_memory(eid):
        memory = memories.get(eid) if memories else None
        if memories is not None and memory is None:
            sim.ecs.add(eid, NPCMemory())
            memory = sim.ecs.get(NPCMemory).get(eid)
        return memory

    def _synthetic_contract_pair():
        origin_chunk = _player_chunk(sim, player_eid)
        giver_rows = []
        for row in candidates:
            eid = int(row[0])
            willingness = _contract_hit_willingness(eid)
            if willingness <= 0.08:
                continue
            giver_rows.append((willingness, row))
        if not giver_rows:
            giver_rows = [(0.16, row) for row in candidates]

        ranked_givers = sorted(giver_rows, key=lambda item: float(item[0]), reverse=True)
        giver_shortlist = ranked_givers[: min(5, len(ranked_givers))]
        total_giver_weight = sum(max(0.01, float(weight)) for weight, _row in giver_shortlist)
        giver_pick = rng.uniform(0.0, total_giver_weight)
        giver_running = 0.0
        giver_row = giver_shortlist[-1][1]
        giver_weight = float(giver_shortlist[-1][0])
        for weight, row in giver_shortlist:
            giver_running += max(0.01, float(weight))
            if giver_pick <= giver_running:
                giver_row = row
                giver_weight = float(weight)
                break

        giver_eid = int(giver_row[0])
        target_rows = []
        for row in candidates:
            target_eid = int(row[0])
            if target_eid == giver_eid:
                continue
            _eid, target_ai, _target_identity, target_pos, target_occ = row
            target_chunk = sim.chunk_coords(int(target_pos.x), int(target_pos.y))
            distance = _manhattan(origin_chunk, target_chunk)
            target_role = (
                str(getattr(target_occ, "career", "") or "").replace("_", " ").strip()
                if target_occ
                else str(getattr(target_ai, "role", "") or "").replace("_", " ").strip()
            ).lower()
            role_bonus = 0.0
            if any(token in target_role for token in ("courier", "driver", "dispatcher", "runner", "collector")):
                role_bonus += 0.12
            elif any(token in target_role for token in ("broker", "clerk", "bookkeeper", "manager", "fixer")):
                role_bonus += 0.08
            remote_bonus = min(0.34, max(0, distance) * 0.08)
            if distance >= REMOTE_SEED_MIN_DISTANCE:
                remote_bonus += 0.08
            score = 0.12 + remote_bonus + role_bonus + (max(0.0, giver_weight - 0.24) * 0.14)
            target_rows.append((score, row))
        ranked_targets = sorted(target_rows, key=lambda item: float(item[0]), reverse=True)
        target_shortlist = ranked_targets[: min(6, len(ranked_targets))]
        total_target_weight = sum(max(0.01, float(weight)) for weight, _row in target_shortlist)
        target_pick = rng.uniform(0.0, total_target_weight)
        target_running = 0.0
        target_row = target_shortlist[-1][1]
        for weight, row in target_shortlist:
            target_running += max(0.01, float(weight))
            if target_pick <= target_running:
                target_row = row
                break
        return giver_row, target_row

    def _synthetic_contract_context(giver_eid, target_eid):
        target_row = candidate_by_eid.get(int(target_eid))
        giver_row = candidate_by_eid.get(int(giver_eid))
        target_ai = target_row[1] if target_row else None
        target_occ = target_row[4] if target_row else None
        target_pos = target_row[3] if target_row else None
        giver_occ = giver_row[4] if giver_row else None
        target_role = (
            str(getattr(target_occ, "career", "") or "").replace("_", " ").strip()
            if target_occ
            else str(getattr(target_ai, "role", "") or "").replace("_", " ").strip()
        ).lower()
        giver_role = (
            str(getattr(giver_occ, "career", "") or "").replace("_", " ").strip()
            if giver_occ
            else ""
        ).lower()
        target_chunk = sim.chunk_coords(int(target_pos.x), int(target_pos.y)) if target_pos else None
        player_chunk = _player_chunk(sim, player_eid)
        distance = _manhattan(player_chunk, target_chunk)
        if any(token in target_role for token in ("courier", "driver", "dispatcher", "runner", "collector")):
            return {
                "tag": "burned_route",
                "reason_text": "They stepped on somebody else's route and kept moving.",
            }
        if any(token in target_role for token in ("broker", "clerk", "bookkeeper", "manager")):
            return {
                "tag": "bad_debt",
                "reason_text": "They owe the wrong people and stopped answering.",
            }
        if distance >= REMOTE_SEED_FAR_DISTANCE:
            return {
                "tag": "remote_reach",
                "reason_text": "They started reaching into the wrong block from too far away.",
            }
        if any(token in giver_role for token in ("fixer", "broker", "dispatcher", "runner")):
            return {
                "tag": "double_cross",
                "reason_text": "They tried to skim the wrong deal and vanished into another district.",
            }
        return {
            "tag": "loose_end",
            "reason_text": "They have been showing up in the wrong business and somebody wants it ended.",
        }

    def _seed_synthetic_contract_rivalry(giver_eid, target_eid):
        context = _synthetic_contract_context(giver_eid, target_eid)
        reason_tag = str(context.get("tag", "synthetic")).strip().lower() or "synthetic"
        reason_text = str(context.get("reason_text", "")).strip() or "Somebody local wants them gone."

        giver_memory = _ensure_memory(giver_eid)
        if giver_memory:
            giver_memory.remember(
                tick=now,
                kind="actor_reputation",
                strength=0.52,
                actor_eid=int(target_eid),
                approval=-0.64,
                against_eid=int(giver_eid),
                via="synthetic_contract_grudge",
                synthetic=True,
                contract_reason_tag=reason_tag,
                contract_reason=reason_text,
            )
            giver_memory.remember(
                tick=now,
                kind="conflict_side",
                strength=0.46,
                side_eid=int(giver_eid),
                against_eid=int(target_eid),
                source_eid=int(target_eid),
                via="synthetic_contract_grudge",
                synthetic=True,
                contract_reason_tag=reason_tag,
                contract_reason=reason_text,
            )

        target_memory = _ensure_memory(target_eid)
        if target_memory:
            target_memory.remember(
                tick=now,
                kind="actor_reputation",
                strength=0.38,
                actor_eid=int(giver_eid),
                approval=-0.42,
                against_eid=int(target_eid),
                via="synthetic_contract_grudge",
                synthetic=True,
                contract_reason_tag=reason_tag,
                contract_reason=reason_text,
            )
            target_memory.remember(
                tick=now,
                kind="conflict_side",
                strength=0.32,
                side_eid=int(target_eid),
                against_eid=int(giver_eid),
                source_eid=int(giver_eid),
                via="synthetic_contract_grudge",
                synthetic=True,
                contract_reason_tag=reason_tag,
                contract_reason=reason_text,
            )
        return reason_text

    selected_social = None
    if social_candidates:
        ranked = sorted(social_candidates.values(), key=lambda row: float(row.get("score", 0.0) or 0.0), reverse=True)
        shortlist = ranked[: min(5, len(ranked))]
        total_weight = sum(max(0.01, float(row.get("score", 0.0) or 0.0)) for row in shortlist)
        pick = rng.uniform(0.0, total_weight)
        running = 0.0
        selected_social = shortlist[-1]
        for row in shortlist:
            running += max(0.01, float(row.get("score", 0.0) or 0.0))
            if pick <= running:
                selected_social = row
                break

    if selected_social:
        giver_eid = int(selected_social["giver_eid"])
        target_eid = int(selected_social["target_eid"])
        target_ai, target_identity, target_pos, target_occ = candidate_by_eid[target_eid][1:]
        contract_reason = _contract_reason_text(selected_social)
    else:
        giver_row, target_row = _synthetic_contract_pair()
        giver_eid = int(giver_row[0])
        target_eid, target_ai, target_identity, target_pos, target_occ = target_row
        contract_reason = _seed_synthetic_contract_rivalry(giver_eid, target_eid)

    # Name and role.
    target_name = str(
        target_identity.personal_name
        or target_identity.common_name
        or target_identity.creature_type
        or "Unknown"
    ).strip().title()
    career = str(getattr(target_occ, "career", "") or "").replace("_", " ").strip() if target_occ else ""
    target_role = career or str(getattr(target_ai, "role", "person") or "person").replace("_", " ").strip()

    # Location and distance.
    cx, cy = sim.chunk_coords(int(target_pos.x), int(target_pos.y))
    origin_chunk = _player_chunk(sim, player_eid)
    distance = _manhattan(origin_chunk, (cx, cy))
    direction = _chunk_direction(origin_chunk, (cx, cy))
    distance_text = opportunity_distance_text(distance, direction)

    world = getattr(sim, "world", None)
    desc = world.overworld_descriptor(cx, cy) if world else {}
    area_type = str(desc.get("area_type", "city")).strip().lower() or "city"
    district_type = str(desc.get("district_type", "unknown")).strip().lower() or "unknown"
    location = f"{area_type}/{district_type}"

    credits_reward = rng.randint(30, 55)
    key = f"contract_kill:{target_eid}"

    summary = f"Locate and neutralize {target_name}, a {target_role} operating {distance_text}."
    if contract_reason:
        summary = f"{summary} {contract_reason}"
    summary = f"{summary} No noise, no trace."
    target_description = f"{target_name}, a {target_role} working {distance_text}"

    opportunity = {
        "key": key,
        "title": "Contract Hit",
        "summary": summary,
        "kind": "contract_kill",
        "source": "contact",
        "chunk": (int(cx), int(cy)),
        "location": location,
        "playstyles": ("combat", "stealth"),
        "reward": _reward_with_items(
            {"credits": credits_reward, "standing": 2},
            rng.choice(("light_ammo_box", "med_gel", "credstick_chip")),
        ),
        "risk": "hazardous",
        "pressure": "high",
        "requirements": {
            "kill_target_eid": int(target_eid),
            "kill_target_name": target_name,
            "kill_target_role": target_role,
            "kill_target_description": target_description,
            "giver_npc_eid": int(giver_eid),
            "contract_reason": contract_reason,
            "player_accepted": False,
            "visit_chunk": (int(cx), int(cy)),
        },
        "status": "active",
        "seed_tick": int(getattr(sim, "tick", 0)),
    }

    if _append_opportunity(state, opportunity, existing_keys):
        added_entry = state["active"][-1]
        oid = int(added_entry.get("id", 0))
        # Give the giver NPC confirmed awareness so they can offer it.
        _upsert_observer_intel(
            sim,
            state,
            observer_eid=giver_eid,
            opportunity_id=oid,
            awareness_state="confirmed",
            confidence=0.95,
            source="giver",
        )
        return added_entry
    return None


def refresh_dynamic_opportunities(sim, player_eid, rng=None, refill_reason="immediate"):
    state = _state(sim)
    seed_run_opportunities(sim, player_eid=player_eid, rng=rng)
    before_active_count = _active_opportunity_count(state)
    active = state.get("active", [])
    if len(active) >= MAX_ACTIVE_OPPORTUNITIES:
        return state

    if not isinstance(rng, random.Random):
        seed = f"{getattr(sim, 'seed', 'seed')}:opportunity-dynamic:{player_eid}:{getattr(sim, 'tick', 0)}"
        rng = random.Random(seed)

    existing_keys = {
        str(entry.get("key", "")).strip().lower()
        for entry in list(state.get("active", ())) + list(_terminal_entries(state))
        if str(entry.get("key", "")).strip()
    }

    for candidate in _contact_and_intel_candidates(sim, player_eid):
        if len(state["active"]) >= MAX_ACTIVE_OPPORTUNITIES:
            break
        added = _append_opportunity(state, candidate, existing_keys)
        if added:
            # _append_opportunity historically returns bool; tolerate dict-style returns too.
            added_entry = added if isinstance(added, dict) else (state["active"][-1] if state.get("active") else {})
            _upsert_observer_intel(
                sim,
                state,
                observer_eid=player_eid,
                opportunity_id=int(added_entry.get("id", 0)),
                awareness_state="confirmed",
                confidence=0.9,
                source=str(candidate.get("source", "unknown")),
            )

    metrics = _player_metrics(sim, player_eid)
    current = metrics.get("current_chunk", (0, 0))
    visited = set(metrics.get("visited_chunks", set()))
    objective = getattr(sim, "world_traits", {}).get("run_objective", {}) if sim is not None else {}
    objective_id = str(objective.get("id", "")).strip().lower()

    if len(state["active"]) < MIN_ACTIVE_OPPORTUNITIES:
        deficit = max(1, MIN_ACTIVE_OPPORTUNITIES - len(state["active"]))
        remote_target = max(1, int(round(deficit * 0.4)))
        far_target = 1 if remote_target >= 2 else 0
        _seed_remote_slice(
            sim,
            state=state,
            existing_keys=existing_keys,
            rng=rng,
            objective_id=objective_id,
            origin_chunk=current,
            target_count=MIN_ACTIVE_OPPORTUNITIES,
            remote_target=remote_target,
            far_target=far_target,
            max_radius=8,
            visited_chunks=visited,
        )

        if len(state["active"]) < MIN_ACTIVE_OPPORTUNITIES:
            for ring in _seed_chunk_coordinates(current, max_radius=8):
                rng.shuffle(ring)
                for cx, cy in ring:
                    if len(state["active"]) >= MIN_ACTIVE_OPPORTUNITIES:
                        break
                    if (cx, cy) in visited:
                        continue
                    candidate = _chunk_opportunity_candidate(
                        sim,
                        cx,
                        cy,
                        objective_id=objective_id,
                        rng=rng,
                        origin_chunk=current,
                    )
                    _append_opportunity(state, candidate, existing_keys)
                if len(state["active"]) >= MIN_ACTIVE_OPPORTUNITIES:
                    break

    _bootstrap_player_opportunity_intel(sim, state, player_eid, origin_chunk=current)
    seed_contract_kill_opportunity(sim, player_eid, rng=rng)
    state["last_refresh_tick"] = int(getattr(sim, "tick", 0))
    if _active_opportunity_count(state) > before_active_count:
        _record_opportunity_refill(state, sim, refill_reason)
    return state


def ensure_initial_opportunities(sim, player_eid=None, rng=None):
    state = _state(sim)
    if bool(state.get("seeded", False)):
        return state
    return seed_run_opportunities(sim, player_eid=player_eid, rng=rng)


def refresh_due_dynamic_opportunities(sim, player_eid, rng=None, *, reason="periodic", force=False):
    state = _state(sim)
    if not bool(state.get("seeded", False)):
        return seed_run_opportunities(sim, player_eid=player_eid, rng=rng)

    tick = _safe_int(getattr(sim, "tick", 0), default=0)
    reason_key = str(reason or "periodic").strip().lower() or "periodic"
    active_count = _active_opportunity_count(state)

    def _attempt_refill(refill_reason):
        refreshed = refresh_dynamic_opportunities(sim, player_eid, rng=rng, refill_reason=refill_reason)
        if _active_opportunity_count(refreshed) <= active_count:
            refreshed["next_refill_tick"] = tick + _opportunity_refill_cooldown_ticks(sim)
            refreshed["pending_refill_reason"] = ""
        return refreshed

    if force:
        return _attempt_refill(reason_key)

    if active_count >= MAX_ACTIVE_OPPORTUNITIES:
        if _safe_int(state.get("next_refill_tick"), default=0) <= tick:
            state["next_refill_tick"] = tick + _opportunity_refill_cooldown_ticks(sim)
        if str(state.get("pending_refill_reason", "") or "").strip().lower() == "terminal":
            state["pending_refill_reason"] = ""
        return state

    if active_count <= OPPORTUNITY_EMERGENCY_ACTIVE_COUNT:
        return _attempt_refill("emergency")

    pending_reason = str(state.get("pending_refill_reason", "") or "").strip().lower()
    if pending_reason == "terminal" and active_count >= MIN_ACTIVE_OPPORTUNITIES:
        state["pending_refill_reason"] = ""
        state["next_refill_tick"] = tick + _opportunity_refill_cooldown_ticks(sim)
        return state

    terminal_reason = reason_key in {"terminal", "completed", "failed", "completion", "failure"}
    if terminal_reason and active_count < MIN_ACTIVE_OPPORTUNITIES:
        return _schedule_opportunity_refill(
            state,
            sim,
            "terminal",
            _opportunity_terminal_refill_delay_ticks(sim),
        )

    next_refill_tick = _safe_int(state.get("next_refill_tick"), default=tick)
    if tick < next_refill_tick:
        return state

    refill_reason = pending_reason or reason_key or "periodic"
    return _attempt_refill(refill_reason)


def _completion_detail(sim, opportunity, metrics):
    requirements = _opportunity_requirements(opportunity)
    bounty_target_eid = _safe_int(requirements.get("bounty_target_eid"), default=0)
    if bounty_target_eid > 0:
        if not bool(requirements.get("player_accepted")):
            return False, "", None
        if bool(requirements.get("bounty_restrained")):
            target_name = str(requirements.get("bounty_target_name", "target")).strip() or "target"
            return True, f"{target_name} restrained for pickup", None
        return False, "", None

    visit_chunk = _chunk_tuple(requirements.get("visit_chunk"))
    current_chunk = _chunk_tuple(metrics.get("current_chunk"))
    visited = set(metrics.get("visited_chunks", ()))
    reasons = []
    if visit_chunk and visit_chunk not in visited and visit_chunk != current_chunk:
        return False, "", None

    target_property_id = str(requirements.get("property_id", "")).strip()
    target_building_id = str(requirements.get("building_id", "")).strip()
    if (target_property_id or target_building_id) and not _matches_site_requirement(
        sim,
        metrics,
        property_id=target_property_id,
        building_id=target_building_id,
    ):
        return False, "", None

    min_contacts = _safe_int(requirements.get("contact_count"), default=0)
    if min_contacts > _safe_int(metrics.get("contact_count"), default=0):
        return False, "", None
    if min_contacts > 0:
        reasons.append(f"contacts >= {min_contacts}")

    min_leads = _safe_int(requirements.get("intel_leads"), default=0)
    if min_leads > _safe_int(metrics.get("intel_leads"), default=0):
        return False, "", None
    if min_leads > 0:
        reasons.append(f"intel leads >= {min_leads}")

    min_reserve = _safe_int(requirements.get("reserve_credits"), default=0)
    if min_reserve > _safe_int(metrics.get("reserve_credits"), default=0):
        return False, "", None
    if min_reserve > 0:
        reasons.append(f"reserve >= {min_reserve}c")

    interact_npc_eid = _safe_int(requirements.get("interact_npc_eid"), default=0)
    interaction_requirement = str(requirements.get("interaction_requirement", "contact")).strip().lower() or "contact"
    interact_name = str(requirements.get("interact_npc_name", "the contact")).strip() or "the contact"
    recent_activity_tags = _normalize_activity_tags(requirements.get("recent_activity_tags"))
    require_item_id = str(requirements.get("require_item_id", "")).strip().lower()
    if interact_npc_eid > 0 and not require_item_id:
        recent_npc_eids = metrics.get("recent_npc_eids", frozenset())
        if interact_npc_eid not in recent_npc_eids:
            return False, "", None
        if interaction_requirement == "pressure":
            player_eid = getattr(sim, "player_eid", None)
            if player_eid is None or not _recent_pressure_interaction(sim, interact_npc_eid, player_eid):
                return False, "", None
            reasons.append(f"leaned on {interact_name}")
        else:
            reasons.append(f"made contact with {interact_name}")
    require_item_qty = max(1, _safe_int(requirements.get("require_item_qty"), default=1))
    recent_transfer = None
    if require_item_id:
        inventory_counts = metrics.get("inventory_counts", {}) if isinstance(metrics.get("inventory_counts", {}), dict) else {}
        if bool(requirements.get("provide_item")):
            have_qty = _opportunity_tagged_item_quantity(
                metrics.get("inventory"),
                _safe_int(opportunity.get("id"), default=0),
                require_item_id,
            )
        else:
            have_qty = max(0, _safe_int(inventory_counts.get(require_item_id), default=0))
        delivery_chunk = _chunk_tuple(requirements.get("delivery_chunk")) or visit_chunk
        delivery_property_id = str(requirements.get("delivery_property_id", "")).strip() or target_property_id
        delivery_building_id = str(requirements.get("delivery_building_id", "")).strip() or target_building_id
        if have_qty < require_item_qty:
            recent_transfer = _matching_recent_required_item_transfer(
                metrics,
                item_id=require_item_id,
                quantity=require_item_qty,
                npc_eid=interact_npc_eid,
                property_id=delivery_property_id,
                building_id=delivery_building_id,
                chunk=delivery_chunk,
            )
            if recent_transfer is None:
                return False, "", None
        item_label = str(requirements.get("item_label", "")).strip() or _item_label(require_item_id)
        if recent_transfer is not None and have_qty < require_item_qty:
            source = str(recent_transfer.get("source", "") or "").strip().lower()
            if source == "street_buy":
                reasons.append(f"sold {item_label} to {interact_name}")
            elif source == "trade_sold":
                reasons.append(f"sold {item_label} at delivery site")
            else:
                reasons.append(f"delivered {item_label}")
        else:
            reasons.append(f"carrying {item_label}")

            if interact_npc_eid > 0:
                recent_npc_eids = metrics.get("recent_npc_eids", frozenset())
                if interact_npc_eid not in recent_npc_eids:
                    return False, "", None
                if delivery_chunk and current_chunk != delivery_chunk:
                    return False, "", None
                reasons.append(f"handed over to {interact_name}")
            else:
                if not (delivery_property_id or delivery_building_id):
                    return False, "", None
                if not _matches_site_requirement(
                    sim,
                    metrics,
                    property_id=delivery_property_id,
                    building_id=delivery_building_id,
                ):
                    return False, "", None
                if not _matches_recent_handoff_site_interaction(
                    metrics,
                    property_id=delivery_property_id,
                    building_id=delivery_building_id,
                ):
                    return False, "", None
                reasons.append("completed handoff at delivery site")

        if delivery_chunk and current_chunk != delivery_chunk:
            return False, "", None
    elif recent_activity_tags:
        matched_tag = _match_recent_opportunity_activity(
            metrics,
            property_id=target_property_id,
            building_id=target_building_id,
            chunk=visit_chunk or current_chunk,
            accepted_tags=recent_activity_tags,
        )
        if not matched_tag:
            return False, "", None
        reasons.append(OPPORTUNITY_ACTIVITY_REASON_LABELS.get(matched_tag, "worked the site"))
    elif (target_property_id or target_building_id) and interact_npc_eid <= 0:
        if not _matches_recent_site_interaction(
            metrics,
            property_id=target_property_id,
            building_id=target_building_id,
        ):
            return False, "", None
        reasons.append("completed work at target site")
    elif _site_task_expected(requirements):
        return False, "", None

    kill_target_eid = _safe_int(requirements.get("kill_target_eid"), default=0)
    if kill_target_eid > 0:
        if not bool(requirements.get("player_accepted")):
            return False, "", None
        killed_eids = metrics.get("killed_npc_eids", frozenset())
        if kill_target_eid not in killed_eids:
            return False, "", None
        target_name = str(requirements.get("kill_target_name", "target")).strip() or "target"
        reasons.append(f"{target_name} neutralized")
    return True, ", ".join(reasons) if reasons else "requirements met", recent_transfer


def _recent_pressure_interaction(sim, target_eid, actor_eid, *, max_age=18, min_negative=0.18):
    if sim is None or target_eid is None or actor_eid is None:
        return False
    memory = sim.ecs.get(NPCMemory).get(target_eid) if sim is not None else None
    if not memory:
        return False
    now = int(getattr(sim, "tick", 0))
    for entry in reversed(list(getattr(memory, "entries", ()) or ())):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("kind", "")).strip().lower() != "actor_reputation":
            continue
        age = max(0, now - int(entry.get("tick", now) or now))
        if age > int(max_age):
            continue
        data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
        if _safe_int(data.get("actor_eid"), default=0) != int(actor_eid):
            continue
        try:
            approval = float(data.get("approval", 0.0) or 0.0)
        except (TypeError, ValueError):
            approval = 0.0
        via = str(data.get("via", "") or "").strip().lower()
        if approval <= -abs(float(min_negative)) and via in {
            "npc_offended",
            "dialogue_guard_resolution",
            "witnessed_offense",
            "witnessed_damage",
        }:
            return True
    return False


def _inventory_counts(inventory):
    counts = {}
    if not inventory:
        return counts
    for entry in list(getattr(inventory, "items", ()) or ()):
        item_id = str(entry.get("item_id", "")).strip().lower()
        if not item_id:
            continue
        counts[item_id] = counts.get(item_id, 0) + max(0, _safe_int(entry.get("quantity"), default=0))
    return counts


def _ensure_provided_item(sim, player_eid, opportunity, metrics):
    requirements = _opportunity_requirements(opportunity)
    if not bool(requirements.get("provide_item")):
        return None

    item_id = str(requirements.get("require_item_id", "")).strip().lower()
    if not item_id:
        return None

    pickup_chunk = _chunk_tuple(requirements.get("pickup_chunk"))
    current_chunk = _chunk_tuple(metrics.get("current_chunk"))
    if pickup_chunk and pickup_chunk != current_chunk:
        return None
    pickup_property_id = str(requirements.get("pickup_property_id", "")).strip()
    pickup_building_id = str(requirements.get("pickup_building_id", "")).strip()
    if (pickup_property_id or pickup_building_id) and not _matches_site_requirement(
        sim,
        metrics,
        property_id=pickup_property_id,
        building_id=pickup_building_id,
    ):
        return None
    pickup_interact_npc_eid = _safe_int(requirements.get("pickup_interact_npc_eid"), default=0)
    if pickup_interact_npc_eid > 0:
        recent_npc_eids = metrics.get("recent_npc_eids", frozenset())
        if pickup_interact_npc_eid not in recent_npc_eids:
            return None
    elif pickup_property_id or pickup_building_id:
        acquisition_hint = str(requirements.get("acquisition_hint", "provided") or "provided").strip().lower()
        handoff_required = acquisition_hint in {"provided", "issued", "handoff"}
        if handoff_required:
            ready = _matches_recent_handoff_site_interaction(
                metrics,
                property_id=pickup_property_id,
                building_id=pickup_building_id,
            )
        else:
            ready = _matches_recent_site_interaction(
                metrics,
                property_id=pickup_property_id,
                building_id=pickup_building_id,
            )
        if not ready:
            return None
    else:
        return None

    inventory = sim.ecs.get(Inventory).get(player_eid) if sim is not None else None
    if not inventory:
        return None

    opportunity_id = _safe_int(opportunity.get("id"), default=0)
    required_qty = max(1, _safe_int(requirements.get("require_item_qty"), default=1))
    tagged_qty = _opportunity_tagged_item_quantity(inventory, opportunity_id, item_id)
    item_label = str(requirements.get("item_label", "")).strip() or _item_label(item_id)
    site_id = pickup_property_id or pickup_building_id
    site_name = str(requirements.get("pickup_property_name", "") or "").strip()
    if not site_name and pickup_property_id and sim is not None:
        site_name = _property_label(getattr(sim, "properties", {}).get(pickup_property_id), pickup_property_id)
    if not site_name:
        site_name = site_id or "pickup site"

    if tagged_qty >= required_qty:
        if _safe_int(opportunity.get("provided_item_issued_tick"), default=-1) < 0:
            opportunity["provided_item_issued_tick"] = int(getattr(sim, "tick", 0))
        return None
    if _safe_int(opportunity.get("provided_item_issued_tick"), default=-1) >= 0:
        return None

    metadata = {
        "quest_opportunity_id": int(opportunity.get("id", 0) or 0),
        "quest_kind": str(opportunity.get("kind", "")).strip().lower(),
        "acquisition": str(requirements.get("acquisition_hint", "provided")).strip().lower() or "provided",
    }
    inventory.add_item(
        item_id=item_id,
        quantity=max(1, required_qty - tagged_qty),
        stack_max=_item_stack_max(item_id),
        instance_id=f"opp-{int(opportunity.get('id', 0) or 0)}-{item_id}-{int(getattr(sim, 'tick', 0))}",
        owner_tag="opportunity",
        metadata=metadata,
    )
    tagged_qty = _opportunity_tagged_item_quantity(inventory, opportunity_id, item_id)
    if tagged_qty >= required_qty:
        opportunity["provided_item_issued_tick"] = int(getattr(sim, "tick", 0))
        opportunity.pop("provided_item_blocked_tick", None)
        return {
            "status": "received",
            "opportunity_id": opportunity_id,
            "title": str(opportunity.get("title", "Opportunity")).strip() or "Opportunity",
            "item_id": item_id,
            "item_label": item_label,
            "quantity": required_qty,
            "site_id": site_id,
            "site_name": site_name,
        }

    current_tick = int(getattr(sim, "tick", 0))
    last_blocked_tick = _safe_int(opportunity.get("provided_item_blocked_tick"), default=-10_000)
    if current_tick - last_blocked_tick >= 20:
        opportunity["provided_item_blocked_tick"] = current_tick
        return {
            "status": "inventory_full",
            "opportunity_id": opportunity_id,
            "title": str(opportunity.get("title", "Opportunity")).strip() or "Opportunity",
            "item_id": item_id,
            "item_label": item_label,
            "quantity": required_qty,
            "site_id": site_id,
            "site_name": site_name,
        }
    return None


def _remove_tagged_opportunity_item(inventory, *, opportunity_id=0, item_id="", quantity=1):
    if not inventory:
        return 0
    target_opportunity_id = _safe_int(opportunity_id, default=0)
    target_item_id = str(item_id or "").strip().lower()
    remaining = max(1, _safe_int(quantity, default=1))
    removed_total = 0
    if target_opportunity_id <= 0 or not target_item_id:
        return 0

    tagged_entries = []
    for entry in list(getattr(inventory, "items", ()) or ()):
        if str(entry.get("item_id", "")).strip().lower() != target_item_id:
            continue
        metadata = entry.get("metadata", {}) if isinstance(entry.get("metadata"), dict) else {}
        if _safe_int(metadata.get("quest_opportunity_id"), default=0) != target_opportunity_id:
            continue
        tagged_entries.append(dict(entry))

    for entry in tagged_entries:
        if remaining <= 0:
            break
        removed = inventory.remove_item(instance_id=entry.get("instance_id"), quantity=remaining)
        if not removed:
            continue
        removed_qty = max(0, _safe_int(removed.get("quantity"), default=0))
        removed_total += removed_qty
        remaining -= removed_qty
    return removed_total


def _consume_required_item(sim, player_eid, opportunity):
    requirements = _opportunity_requirements(opportunity)
    if not bool(requirements.get("consume_item")):
        return None

    item_id = str(requirements.get("require_item_id", "")).strip().lower()
    quantity = max(1, _safe_int(requirements.get("require_item_qty"), default=1))
    if not item_id:
        return None

    inventory = sim.ecs.get(Inventory).get(player_eid) if sim is not None else None
    if not inventory:
        return None

    removed_total = 0
    if bool(requirements.get("provide_item")):
        removed_total += _remove_tagged_opportunity_item(
            inventory,
            opportunity_id=_safe_int(opportunity.get("id"), default=0),
            item_id=item_id,
            quantity=quantity,
        )
        if removed_total < quantity:
            return None
    while removed_total < quantity:
        removed = inventory.remove_item(item_id=item_id, quantity=quantity - removed_total)
        if not removed:
            break
        removed_total += max(0, _safe_int(removed.get("quantity"), default=0))

    if removed_total <= 0:
        return None
    return {
        "item_id": item_id,
        "quantity": removed_total,
        "item_label": str(requirements.get("item_label", "")).strip() or _item_label(item_id),
    }


def _apply_contact_favor(sim, player_eid, opportunity):
    if sim is None or player_eid is None or not isinstance(opportunity, dict):
        return {}

    issuer = opportunity.get("issuer")
    if not isinstance(issuer, dict):
        return {}

    ledger = sim.ecs.get(ContactLedger).get(player_eid)
    if not ledger:
        return {}

    person_eid = _safe_int(issuer.get("npc_eid"), default=0)
    person_delta = max(0.0, _safe_float(issuer.get("person_standing_delta"), default=0.0))
    property_id = str(issuer.get("property_id", "")).strip() or None
    relation_kind = str(issuer.get("relation_kind", "job_issuer")).strip().lower() or "job_issuer"
    benefits = tuple(
        str(bit).strip().lower()
        for bit in tuple(issuer.get("benefits", ("known_name",))) or ("known_name",)
        if str(bit).strip()
    )

    applied = {}
    if person_eid > 0 and person_delta > 0.0:
        existing = ledger.person_entry(person_eid) or {}
        existing_standing = _safe_float(existing.get("standing"), default=0.0)
        target_standing = _clamp(max(existing_standing, 0.22) + person_delta, 0.0, 1.0)
        ledger.remember_person(
            person_eid,
            source_eid=person_eid,
            relation_kind=relation_kind,
            standing=target_standing,
            tick=int(getattr(sim, "tick", 0)),
            property_id=property_id,
            benefits=benefits,
            introduced=True,
        )
        applied["contact_favor"] = round(max(0.0, target_standing - existing_standing), 3)

    property_delta = max(0.0, _safe_float(issuer.get("property_standing_delta"), default=0.0))
    if property_id and property_delta > 0.0:
        existing = ledger.property_entry(property_id) or {}
        existing_standing = _safe_float(existing.get("standing"), default=0.0)
        target_standing = _clamp(max(existing_standing, 0.22) + property_delta, 0.0, 1.0)
        ledger.remember(
            property_id,
            source_eid=person_eid or None,
            contact_kind=relation_kind,
            standing=target_standing,
            tick=int(getattr(sim, "tick", 0)),
            benefits=benefits,
        )
        applied["property_favor"] = round(max(0.0, target_standing - existing_standing), 3)

    return applied


def _opportunity_worldview_weights(opportunity):
    family = str((opportunity or {}).get("contract_family", "")).strip().lower()
    kind = str((opportunity or {}).get("kind", "")).strip().lower()
    key = family or kind

    order_families = {
        "medical_resupply",
        "medical_drop",
        "paper_run",
        "claims_packet",
        "records_recovery",
        "records_pull",
        "tool_request",
        "contact_run",
        "claims_chase",
    }
    chaos_families = {
        "dead_drop_return",
        "backroom_transfer",
        "buyback",
        "parts_return",
        "backroom_buyback",
        "contract_kill",
        "pressure_visit",
        "quiet_collection",
    }
    care_families = {
        "medical_resupply",
        "medical_drop",
        "clinic_recovery",
        "missing_person",
        "shelter_stop",
    }

    order = 0.15
    chaos = 0.15
    care = 0.1
    if key in order_families:
        order = 0.92
        chaos = 0.08
    elif key in chaos_families:
        order = 0.08
        chaos = 0.92
    if key in care_families:
        care = 0.88
    neutral = max(0.0, 1.0 - max(order, chaos, care))
    return {
        "family": key or kind or "opportunity",
        "order": float(order),
        "chaos": float(chaos),
        "care": float(care),
        "neutral": float(neutral),
    }


def _apply_personal_issuer_bond(sim, player_eid, opportunity):
    if sim is None or player_eid is None or not isinstance(opportunity, dict):
        return {}

    issuer = opportunity.get("issuer")
    if not isinstance(issuer, dict):
        return {}

    person_eid = _safe_int(issuer.get("npc_eid"), default=0)
    if person_eid <= 0:
        return {}

    social = sim.ecs.get(NPCSocial).get(person_eid)
    if not social:
        return {}

    ledger = sim.ecs.get(ContactLedger).get(player_eid)
    person_entry = ledger.person_entry(person_eid) if ledger else {}
    seeded_standing = _safe_float((person_entry or {}).get("standing"), default=0.0)
    relation_kind = str((person_entry or {}).get("relation_kind") or issuer.get("relation_kind") or "").strip().lower()
    bond = social.bonds.get(player_eid)
    if not isinstance(bond, dict):
        base_kind = "coworker" if relation_kind in {"job_issuer", "coworker", "member"} else "neighbor"
        social.add_bond(
            player_eid,
            kind=base_kind,
            closeness=max(0.18, 0.14 + (seeded_standing * 0.24)),
            trust=max(0.22, 0.18 + (seeded_standing * 0.28)),
            protectiveness=max(0.18, 0.14 + (seeded_standing * 0.2)),
        )
        bond = social.bonds.get(player_eid)
    if not isinstance(bond, dict):
        return {}

    reward = dict(opportunity.get("reward", {}))
    traits = sim.ecs.get(NPCTraits).get(person_eid) or NPCTraits()
    justice = sim.ecs.get(JusticeProfile).get(person_eid)
    memories = sim.ecs.get(NPCMemory)
    worldview = _opportunity_worldview_weights(opportunity)
    justice_value = _clamp(getattr(justice, "justice", 0.5) if justice else 0.5, lo=0.0, hi=1.0)
    corruption = _clamp(getattr(justice, "corruption", 0.0) if justice else 0.0, lo=0.0, hi=1.0)
    order_pref = _clamp(
        (float(getattr(traits, "discipline", 0.5)) * 0.45)
        + (float(justice_value) * 0.33)
        + ((1.0 - float(corruption)) * 0.22),
        lo=0.0,
        hi=1.0,
    )
    chaos_pref = _clamp(
        ((1.0 - float(getattr(traits, "discipline", 0.5))) * 0.34)
        + (float(corruption) * 0.44)
        + ((1.0 - float(justice_value)) * 0.22),
        lo=0.0,
        hi=1.0,
    )
    empathy = _clamp(getattr(traits, "empathy", 0.5), lo=0.0, hi=1.0)
    loyalty = _clamp(getattr(traits, "loyalty", 0.5), lo=0.0, hi=1.0)
    risk_key = str(opportunity.get("risk", "low")).strip().lower() or "low"
    risk_bonus = {"low": 0.0, "exposed": 0.008, "hazardous": 0.016}.get(risk_key, 0.0)
    standing_reward = max(0, _safe_int(reward.get("standing"), default=0))
    person_delta = max(0.0, _safe_float(issuer.get("person_standing_delta"), default=0.0))
    alignment = (
        (worldview["order"] * order_pref)
        + (worldview["chaos"] * chaos_pref)
        + (worldview["care"] * empathy)
        + (worldview["neutral"] * 0.56)
    )
    worldview_mult = 0.82 + (_clamp(alignment, lo=0.0, hi=1.0) * 0.36)

    trust_delta = max(0.008, min(0.085, (0.015 + (person_delta * 0.34) + (standing_reward * 0.005)) * worldview_mult))
    closeness_delta = max(0.006, min(0.072, (0.012 + (person_delta * 0.26) + (empathy * 0.01)) * worldview_mult))
    protectiveness_delta = max(0.003, min(0.06, (0.007 + (loyalty * 0.014) + risk_bonus) * worldview_mult))

    before_trust = _safe_float(bond.get("trust"), default=0.0)
    before_closeness = _safe_float(bond.get("closeness"), default=0.0)
    before_protectiveness = _safe_float(bond.get("protectiveness"), default=0.0)
    bond["trust"] = _clamp(before_trust + trust_delta, lo=0.0, hi=0.98)
    bond["closeness"] = _clamp(before_closeness + closeness_delta, lo=0.0, hi=0.98)
    bond["protectiveness"] = _clamp(before_protectiveness + protectiveness_delta, lo=0.0, hi=0.98)

    if str(bond.get("kind", "")).strip().lower() == "neighbor" and bond["trust"] >= 0.44 and bond["closeness"] >= 0.38:
        bond["kind"] = "coworker" if relation_kind in {"job_issuer", "coworker", "member"} else "friend"
    if bond["trust"] >= 0.62 and bond["closeness"] >= 0.58:
        bond["kind"] = "friend"
        bond["protectiveness"] = max(
            float(bond.get("protectiveness", 0.0)),
            float(NPCSocial.DEFAULT_PROTECT.get("friend", 0.7)),
        )
    _record_actor_social_warmth(
        sim,
        person_eid,
        other_eid=player_eid,
        reason="opportunity_issuer_bond",
        trust_delta=float(bond["trust"] - before_trust),
        closeness_delta=float(bond["closeness"] - before_closeness),
        protectiveness_delta=float(bond["protectiveness"] - before_protectiveness),
        post_bond=bond,
    )

    memory = memories.get(person_eid) if memories else None
    if memories is not None and memory is None:
        sim.ecs.add(person_eid, NPCMemory())
        memory = sim.ecs.get(NPCMemory).get(person_eid)
    if memory:
        worldview_label = "neutral"
        if worldview["order"] > worldview["chaos"] and worldview["order"] >= 0.6:
            worldview_label = "order"
        elif worldview["chaos"] > worldview["order"] and worldview["chaos"] >= 0.6:
            worldview_label = "chaos"
        reputation_strength = min(1.0, 0.42 + (worldview_mult * 0.24))
        memory.remember(
            tick=int(getattr(sim, "tick", 0)),
            kind="player_reputation",
            strength=reputation_strength,
            player_eid=player_eid,
            opportunity_kind=str(opportunity.get("kind", "")).strip().lower() or "opportunity",
            contract_family=worldview["family"],
            worldview=worldview_label,
            trust_delta=round(float(bond["trust"] - before_trust), 3),
            closeness_delta=round(float(bond["closeness"] - before_closeness), 3),
            protectiveness_delta=round(float(bond["protectiveness"] - before_protectiveness), 3),
        )
        memory.remember(
            tick=int(getattr(sim, "tick", 0)),
            kind="actor_reputation",
            strength=max(0.18, reputation_strength * 0.92),
            actor_eid=player_eid,
            approval=round(0.54 + (worldview_mult * 0.12), 3),
            opportunity_kind=str(opportunity.get("kind", "")).strip().lower() or "opportunity",
            contract_family=worldview["family"],
            worldview=worldview_label,
            via="job_completion",
        )

    return {
        "issuer_trust": round(max(0.0, float(bond["trust"] - before_trust)), 3),
        "issuer_closeness": round(max(0.0, float(bond["closeness"] - before_closeness)), 3),
        "issuer_protectiveness": round(max(0.0, float(bond["protectiveness"] - before_protectiveness)), 3),
    }


def _apply_organization_favor(sim, opportunity):
    if sim is None or not isinstance(opportunity, dict):
        return {}

    issuer = opportunity.get("issuer")
    if not isinstance(issuer, dict):
        return {}

    organization_eid = _safe_int(issuer.get("organization_eid"), default=0)
    standing_delta = _safe_float(issuer.get("organization_standing_delta"), default=0.0)
    if organization_eid <= 0 or abs(standing_delta) < 1e-9:
        return {}

    change = apply_organization_reputation_delta(
        sim,
        organization_eid=organization_eid,
        standing_delta=standing_delta,
        source="opportunity_reward",
        reason=f"{str(opportunity.get('kind', 'opportunity')).strip().lower() or 'opportunity'}_completed",
        source_event="opportunity_completed",
    )
    if not isinstance(change, dict):
        return {}
    return {
        "organization_favor": round(_safe_float(change.get("standing_delta"), default=0.0), 3),
    }


def _apply_reward(sim, player_eid, reward, *, opportunity=None):
    reward = dict(reward or {})
    applied = {
        "credits": 0,
        "intel": 0,
        "standing": 0,
        "energy": 0,
        "safety": 0,
        "social": 0,
    }

    assets = sim.ecs.get(PlayerAssets).get(player_eid)
    needs = sim.ecs.get(NPCNeeds).get(player_eid)
    inventory = sim.ecs.get(Inventory).get(player_eid) if sim is not None else None
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits

    credits = max(0, _safe_int(reward.get("credits"), default=0))
    if assets and credits > 0:
        assets.credits += credits
        applied["credits"] = credits

    for key in ("energy", "safety", "social"):
        gain = max(0, _safe_int(reward.get(key), default=0))
        if gain <= 0 or not needs:
            continue
        before = _clamp(getattr(needs, key, 0.0))
        after = _clamp(before + gain)
        setattr(needs, key, after)
        applied[key] = max(0, int(round(after - before)))

    intel = max(0, _safe_int(reward.get("intel"), default=0))
    if intel > 0:
        traits["opportunity_intel"] = _safe_int(traits.get("opportunity_intel"), default=0) + intel
        applied["intel"] = intel

    standing = max(0, _safe_int(reward.get("standing"), default=0))
    if standing > 0:
        traits["opportunity_standing"] = _safe_int(traits.get("opportunity_standing"), default=0) + standing
        applied["standing"] = standing

    reward_items = []
    raw_items = reward.get("items", ())
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if isinstance(raw_items, (list, tuple)):
        reward_items = [item for item in raw_items if isinstance(item, dict)]
    if reward_items:
        granted = []
        for spec in reward_items:
            item_id = str(spec.get("item_id", "")).strip().lower()
            quantity = max(1, _safe_int(spec.get("quantity"), default=1))
            if not item_id or item_id not in ITEM_CATALOG:
                continue
            if is_credstick_item(item_id):
                cash_value = credstick_total_credits(
                    quantity=quantity,
                    metadata={"stored_credits": max(0, _safe_int(spec.get("stored_credits"), default=0))} if "stored_credits" in spec else None,
                )
                if assets and cash_value > 0:
                    assets.credits += cash_value
                    applied["credits"] = int(applied.get("credits", 0)) + int(cash_value)
                    granted.append({
                        "item_id": item_id,
                        "quantity": quantity,
                        "item_label": _item_label(item_id),
                        "auto_converted": True,
                        "credits_gained": int(cash_value),
                    })
                continue
            if not inventory:
                continue
            added, _instance_id = inventory.add_item(
                item_id=item_id,
                quantity=quantity,
                stack_max=_item_stack_max(item_id),
                instance_factory=getattr(sim, "new_item_instance_id", None),
                owner_eid=player_eid,
                owner_tag="opportunity_reward",
                metadata={
                    "acquisition": "reward",
                    "opportunity_kind": str((opportunity or {}).get("kind", "")).strip().lower() or "opportunity",
                },
            )
            if added:
                granted.append({
                    "item_id": item_id,
                    "quantity": quantity,
                    "item_label": _item_label(item_id),
                })
        if granted:
            applied["items"] = granted

    if isinstance(opportunity, dict):
        applied.update(_apply_contact_favor(sim, player_eid, opportunity))
        applied.update(_apply_personal_issuer_bond(sim, player_eid, opportunity))
        applied.update(_apply_organization_favor(sim, opportunity))

    return applied


def format_reward_text(reward):
    reward = reward or {}
    bits = []
    credits = max(0, _safe_int(reward.get("credits"), default=0))
    if credits > 0:
        bits.append(f"+{credits}c")
    intel = max(0, _safe_int(reward.get("intel"), default=0))
    if intel > 0:
        bits.append(f"+{intel} intel")
    standing = max(0, _safe_int(reward.get("standing"), default=0))
    if standing > 0:
        bits.append(f"+{standing} standing")
    for need_key, label in (("energy", "E"), ("safety", "S"), ("social", "So")):
        gain = max(0, _safe_int(reward.get(need_key), default=0))
        if gain > 0:
            bits.append(f"{label}+{gain}")
    raw_items = reward.get("items", ())
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if isinstance(raw_items, (list, tuple)):
        for spec in raw_items:
            if not isinstance(spec, dict):
                continue
            item_id = str(spec.get("item_id", "")).strip().lower()
            quantity = max(1, _safe_int(spec.get("quantity"), default=1))
            if not item_id or item_id not in ITEM_CATALOG:
                continue
            label = _item_label(item_id)
            if quantity > 1:
                bits.append(f"+{quantity} {label}")
            else:
                bits.append(f"+{label}")
    return ", ".join(bits) if bits else "none"


def _failure_family_for_code(code):
    code = str(code or "").strip().lower()
    if not code:
        return "failed"
    return _FAILURE_FAMILY_BY_CODE.get(code, "failed")


def _resolve_terminal_entry(
    sim,
    state,
    player_eid,
    entry,
    *,
    status="completed",
    reason="",
    reward_applied=None,
    extra=None,
    intel_source="completed",
):
    done = dict(entry or {})
    terminal_status = str(status or "completed").strip().lower() or "completed"
    tick = int(getattr(sim, "tick", 0))
    if terminal_status == "completed":
        done["status"] = "completed"
        done["completed_tick"] = tick
        done["reward_applied"] = dict(reward_applied or {})
        done["completion_reason"] = str(reason).strip() or "requirements met"
    else:
        done["status"] = "failed"
        done["failed_tick"] = tick
        done["failure_reason"] = str(reason).strip() or "opportunity failed"
        if isinstance(reward_applied, dict) and reward_applied:
            done["reward_applied"] = dict(reward_applied)
    if isinstance(extra, dict):
        done.update(extra)
    if terminal_status == "completed":
        state["completed"].append(done)
    else:
        failure_code = str(done.get("failure_code", "") or "").strip().lower() or "failed"
        done["failure_code"] = failure_code
        failure_family = str(done.get("failure_family", "") or "").strip().lower()
        done["failure_family"] = failure_family or _failure_family_for_code(failure_code)
        state["failed"].append(done)
    job_key = str(done.get("key", "") or "").strip()
    if job_key.startswith("service_job:"):
        _finish_service_job_claim(
            sim,
            job_key,
            status="completed" if terminal_status == "completed" else "failed",
            reason=str(reason or terminal_status).strip(),
        )
    if player_eid is not None:
        _upsert_observer_intel(
            sim,
            state,
            observer_eid=player_eid,
            opportunity_id=int(done.get("id", 0) or 0),
            awareness_state="confirmed",
            confidence=1.0,
            source=str(intel_source or terminal_status).strip().lower() or terminal_status,
        )
    return done


def _opportunity_target_specs(opportunity):
    if not isinstance(opportunity, dict):
        return ()
    requirements = _opportunity_requirements(opportunity)
    rows = []
    seen = set()
    for eid_key, name_key, fallback_name, stage in (
        ("pickup_interact_npc_eid", "pickup_interact_npc_name", "the pickup contact", "pickup"),
        ("interact_npc_eid", "interact_npc_name", "the contact", "handoff"),
    ):
        target_eid = _safe_int(requirements.get(eid_key), default=0)
        if target_eid <= 0 or target_eid in seen:
            continue
        seen.add(target_eid)
        target_name = str(requirements.get(name_key, "")).strip() or fallback_name
        rows.append((target_eid, target_name, stage))
    return tuple(rows)


def _target_killed_failure_detail(opportunity, metrics):
    killed_eids = metrics.get("killed_npc_eids", frozenset())
    if not killed_eids:
        return None

    kind = str((opportunity or {}).get("kind", "") or "").strip().lower()
    requirements = _opportunity_requirements(opportunity)
    bounty_target_eid = _safe_int(requirements.get("bounty_target_eid"), default=0)
    if bounty_target_eid > 0 and bounty_target_eid in killed_eids:
        target_name = str(requirements.get("bounty_target_name", "target")).strip() or "target"
        return {
            "failure_code": "target_killed",
            "failure_reason": f"{target_name} was killed before pickup",
        }
    for target_eid, target_name, stage in _opportunity_target_specs(opportunity):
        if target_eid not in killed_eids:
            continue
        if kind == "issuer_pressure":
            reason = f"{target_name} was killed before you could lean on them"
        elif stage == "pickup":
            reason = f"{target_name} was killed before the pickup"
        else:
            reason = f"{target_name} was killed before the handoff"
        return {
            "failure_code": "target_killed",
            "failure_reason": reason,
        }
    return None


def _legal_compromise_failure_detail(opportunity, metrics):
    if not isinstance(opportunity, dict):
        return None
    snapshot = metrics.get("justice_snapshot", {}) if isinstance(metrics.get("justice_snapshot"), dict) else {}
    accepted_tick = _safe_int(opportunity.get("accepted_tick"), default=-1)
    if accepted_tick < 0:
        return None

    custody_tick = _safe_int(snapshot.get("custody_tick"), default=-10_000)
    if bool(snapshot.get("in_custody", False)) and custody_tick >= accepted_tick:
        return {
            "failure_code": "custody_compromised",
            "failure_reason": "custody burned the handoff",
        }

    held_property_count = max(0, _safe_int(snapshot.get("held_property_count"), default=0))
    held_property_updated_tick = _safe_int(snapshot.get("held_property_updated_tick"), default=-10_000)
    held_property = metrics.get("held_property", {}) if isinstance(metrics.get("held_property"), dict) else {}
    held_item_entries = _matching_required_item_entries(opportunity, held_property.get("entries", ()))
    booking_tick = _safe_int(snapshot.get("last_booking_tick"), default=-10_000)
    booking_site = str(snapshot.get("last_booking_property_name", "")).strip() or "the justice booking"
    booking_seizure = metrics.get("booking_seizure", {}) if isinstance(metrics.get("booking_seizure"), dict) else {}
    booking_seized_count = max(0, _safe_int(booking_seizure.get("item_count"), default=0))
    booking_item_entries = _matching_required_item_entries(opportunity, booking_seizure.get("entries", ()))
    if booking_tick >= accepted_tick:
        if booking_item_entries:
            return {
                "failure_code": "booking_required_item_seized",
                "failure_reason": _required_item_seizure_reason(opportunity, site_name=booking_site, during_booking=True),
            }
        if booking_seized_count > 0 or held_property_count > 0:
            return {
                "failure_code": "booking_confiscated",
                "failure_reason": f"{booking_site} seized property tied to the handoff",
            }
        return {
            "failure_code": "booking_compromised",
            "failure_reason": f"booking at {booking_site} burned the handoff",
        }

    if held_property_count > 0 and held_property_updated_tick >= accepted_tick:
        if held_item_entries:
            return {
                "failure_code": "held_required_item_seized",
                "failure_reason": _required_item_seizure_reason(
                    opportunity,
                    site_name=str(held_property.get("property_name", "")).strip(),
                    during_booking=False,
                ),
            }
        return {
            "failure_code": "held_property_seized",
            "failure_reason": "justice seized property tied to the handoff",
        }

    last_incident_tick = _safe_int(snapshot.get("last_incident_tick"), default=-10_000)
    wanted_tier = str(snapshot.get("wanted_tier", "clear")).strip().lower() or "clear"
    if last_incident_tick >= accepted_tick and wanted_tier in {"wanted", "arrest_on_sight"}:
        latest_incident = snapshot.get("latest_incident", {}) if isinstance(snapshot.get("latest_incident"), dict) else {}
        latest_label = str(latest_incident.get("label", "")).strip().lower() or "legal trouble"
        return {
            "failure_code": "legal_compromise",
            "failure_reason": f"{latest_label} burned the handoff",
        }
    return None


def _failure_detail(sim, opportunity, metrics, *, include_item_loss=True):
    if sim is None or not isinstance(opportunity, dict):
        return None

    _ensure_lifecycle_fields(sim, opportunity)
    policy = opportunity.get("failure_policy", {}) if isinstance(opportunity.get("failure_policy"), dict) else {}
    if bool(policy.get("fail_on_target_killed")):
        target_failure = _target_killed_failure_detail(opportunity, metrics)
        if isinstance(target_failure, dict):
            return target_failure
        unavailable_contact = _named_contact_unavailable_failure_detail(sim, opportunity, metrics)
        if isinstance(unavailable_contact, dict):
            return unavailable_contact
    if bool(policy.get("fail_on_legal_compromise")):
        legal_failure = _legal_compromise_failure_detail(opportunity, metrics)
        if isinstance(legal_failure, dict):
            return legal_failure
    anchor_failure = _anchor_unavailable_failure_detail(sim, opportunity)
    if isinstance(anchor_failure, dict):
        return anchor_failure

    now = int(getattr(sim, "tick", 0))
    expire_tick = _safe_int(opportunity.get("expire_tick"), default=0)
    if expire_tick > 0 and now >= expire_tick:
        return {
            "failure_code": "expired",
            "failure_reason": _expired_failure_reason(sim, opportunity),
        }

    if not include_item_loss or not bool(policy.get("fail_on_missing_provided_item")):
        return None

    requirements = _opportunity_requirements(opportunity)
    if not bool(requirements.get("provide_item")):
        return None

    issued_tick = _safe_int(opportunity.get("provided_item_issued_tick"), default=-1)
    if issued_tick < 0:
        return None

    require_item_id = str(requirements.get("require_item_id", "")).strip().lower()
    require_item_qty = max(1, _safe_int(requirements.get("require_item_qty"), default=1))
    opportunity_id = _safe_int(opportunity.get("id"), default=0)
    tagged_qty = _opportunity_tagged_item_quantity(metrics.get("inventory"), opportunity_id, require_item_id)
    if tagged_qty >= require_item_qty:
        return None

    visit_chunk = _chunk_tuple(requirements.get("visit_chunk"))
    target_property_id = str(requirements.get("property_id", "")).strip()
    target_building_id = str(requirements.get("building_id", "")).strip()
    delivery_chunk = _chunk_tuple(requirements.get("delivery_chunk")) or visit_chunk
    delivery_property_id = str(requirements.get("delivery_property_id", "")).strip() or target_property_id
    delivery_building_id = str(requirements.get("delivery_building_id", "")).strip() or target_building_id
    interact_npc_eid = _safe_int(requirements.get("interact_npc_eid"), default=0)
    valid_transfer = _matching_recent_required_item_transfer(
        metrics,
        item_id=require_item_id,
        quantity=require_item_qty,
        npc_eid=interact_npc_eid,
        property_id=delivery_property_id,
        building_id=delivery_building_id,
        chunk=delivery_chunk,
    )
    if valid_transfer is not None:
        return None

    item_label = str(requirements.get("item_label", "")).strip() or _item_label(require_item_id)
    transfer = _recent_required_item_transfer_for_item(
        metrics,
        item_id=require_item_id,
        min_tick=issued_tick,
    )
    if isinstance(transfer, dict):
        source = str(transfer.get("source", "") or "").strip().lower()
        if source in {"street_buy", "trade_sold"}:
            reason = f"sold the provided {item_label} before delivery"
        else:
            reason = f"gave up the provided {item_label} before delivery"
    else:
        reason = f"lost the provided {item_label} before delivery"
    return {
        "failure_code": "provided_item_lost",
        "failure_reason": reason,
    }


def advance_opportunity_lifecycle(sim, player_eid):
    state = _state(sim)
    active = list(state.get("active", ()))
    if not active:
        _tracked_targets_bucket(state).clear()
        return {"completed": [], "failed": [], "issued_items": []}

    _refresh_tracked_targets(sim)
    _update_tracked_target_drift(sim, player_eid)
    stage_active_opportunities(sim, player_eid)
    metrics = _player_metrics(sim, player_eid)
    completed = []
    failed = []
    issued_items = []
    remaining = []
    for entry in active:
        if not isinstance(entry, dict):
            continue
        _ensure_lifecycle_fields(sim, entry)
        failure = _failure_detail(sim, entry, metrics, include_item_loss=False)
        if isinstance(failure, dict):
            failed.append(
                _resolve_terminal_entry(
                    sim,
                    state,
                    player_eid,
                    entry,
                    status="failed",
                    reason=str(failure.get("failure_reason", "")).strip() or "opportunity failed",
                    extra={
                        "failure_code": str(failure.get("failure_code", "")).strip().lower() or "failed",
                    },
                    intel_source="failed",
                )
            )
            continue
        issued_item = _ensure_provided_item(sim, player_eid, entry, metrics)
        if isinstance(issued_item, dict):
            issued_items.append(issued_item)
        inventory = sim.ecs.get(Inventory).get(player_eid) if sim is not None else None
        metrics["inventory"] = inventory
        metrics["inventory_counts"] = _inventory_counts(inventory)
        failure = _failure_detail(sim, entry, metrics, include_item_loss=True)
        if isinstance(failure, dict):
            failed.append(
                _resolve_terminal_entry(
                    sim,
                    state,
                    player_eid,
                    entry,
                    status="failed",
                    reason=str(failure.get("failure_reason", "")).strip() or "opportunity failed",
                    extra={
                        "failure_code": str(failure.get("failure_code", "")).strip().lower() or "failed",
                    },
                    intel_source="failed",
                )
            )
            continue
        is_completed, reason_text, recent_transfer = _completion_detail(sim, entry, metrics)
        if not is_completed:
            remaining.append(entry)
            continue

        consumed = _consume_required_item(sim, player_eid, entry)
        requirements = entry.get("requirements", {}) if isinstance(entry.get("requirements", {}), dict) else {}
        if bool(requirements.get("consume_item")) and not consumed and recent_transfer is None:
            remaining.append(entry)
            continue

        reward = dict(entry.get("reward", {}))
        applied = _apply_reward(sim, player_eid, reward, opportunity=entry)
        completion_reason = str(reason_text).strip() or "requirements met"
        extra = {}
        if consumed:
            extra["consumed_item"] = consumed
            completion_reason = f"{completion_reason}, delivered {consumed['item_label']}"
        elif recent_transfer is not None and bool(requirements.get("consume_item")):
            transferred_item = {
                "item_id": str(recent_transfer.get("item_id", "") or "").strip().lower(),
                "quantity": max(1, _safe_int(recent_transfer.get("quantity"), default=1)),
                "item_label": str(requirements.get("item_label", "")).strip() or _item_label(recent_transfer.get("item_id")),
                "already_transferred": True,
                "source": str(recent_transfer.get("source", "") or "").strip().lower(),
            }
            extra["consumed_item"] = transferred_item
        completed.append(
            _resolve_terminal_entry(
                sim,
                state,
                player_eid,
                entry,
                status="completed",
                reason=completion_reason,
                reward_applied=applied,
                extra=extra,
                intel_source="completed",
            )
        )

    refill_scheduled = False
    if completed or failed:
        state["active"] = remaining
        _refresh_tracked_targets(sim)
        refill_scheduled = _schedule_terminal_opportunity_refill(state, sim)
    return {
        "completed": completed,
        "failed": failed,
        "issued_items": issued_items,
        "refill_scheduled": refill_scheduled,
        "next_refill_tick": _safe_int(state.get("next_refill_tick"), default=0),
        "pending_refill_reason": str(state.get("pending_refill_reason", "") or "").strip().lower(),
    }


def resolve_opportunities(sim, player_eid):
    return list(advance_opportunity_lifecycle(sim, player_eid).get("completed", ()))


def resolve_external_opportunity(
    sim,
    opportunity_id,
    *,
    status="completed",
    completion_reason="",
    reward_applied=None,
    extra=None,
):
    """Resolve an active opportunity from a non-player source.

    This is used by abstract world actors such as rival operators so they can
    contest the same opportunity pool the player sees without duplicating the
    board lifecycle logic.
    """

    state = _state(sim)
    active = list(state.get("active", ()))
    if not active:
        return None

    try:
        target_id = int(opportunity_id)
    except (TypeError, ValueError):
        return None
    if target_id <= 0:
        return None

    resolved = None
    remaining = []
    for entry in active:
        if not isinstance(entry, dict):
            continue
        if resolved is None and int(entry.get("id", 0) or 0) == target_id:
            terminal_status = str(status or "completed").strip().lower() or "completed"
            if terminal_status == "completed":
                resolved = _resolve_terminal_entry(
                    sim,
                    state,
                    getattr(sim, "player_eid", None),
                    entry,
                    status="completed",
                    reason=str(completion_reason).strip() or "resolved externally (completed)",
                    reward_applied=reward_applied,
                    extra=extra,
                    intel_source="completed",
                )
            else:
                failure_extra = dict(extra or {})
                failure_extra.setdefault("failure_code", terminal_status)
                resolved = _resolve_terminal_entry(
                    sim,
                    state,
                    getattr(sim, "player_eid", None),
                    entry,
                    status="failed",
                    reason=str(completion_reason).strip() or f"resolved externally ({terminal_status})",
                    reward_applied=reward_applied,
                    extra=failure_extra,
                    intel_source="failed",
                )
            continue
        remaining.append(entry)

    if resolved is not None:
        state["active"] = remaining
        _schedule_terminal_opportunity_refill(state, sim)
    return resolved


def _objective_support_reason(objective_id, entry, current_chunk=None):
    objective_id = str(objective_id or "").strip().lower()
    if not objective_id or not isinstance(entry, dict):
        return ""

    kind = str(entry.get("kind", "")).strip().lower()
    reward = dict(entry.get("reward", {}))
    credits = max(0, _safe_int(reward.get("credits"), default=0))
    standing = max(0, _safe_int(reward.get("standing"), default=0))
    intel = max(0, _safe_int(reward.get("intel"), default=0))
    current = _chunk_tuple(current_chunk) or (0, 0)
    chunk = _chunk_tuple(entry.get("chunk")) or current
    distance = _manhattan(current, chunk)
    specialty_theme = SPECIALTY_OPPORTUNITY_THEMES.get(kind, "")
    reasons = []

    if objective_id == "debt_exit":
        if credits > 0:
            reasons.append("pays reserve credits")
        if kind in OBJECTIVE_PREFERENCES.get(objective_id, set()):
            reasons.append("fits a cash-building lane")
        if specialty_theme == "route_hub":
            reasons.append("uses traveler turnover")
        elif specialty_theme == "parts_yard":
            reasons.append("turns salvage into reserve")
    elif objective_id == "networked_extraction":
        if kind in {"contact_run", "paper_trail", "claims_chase", "records_pull"} or standing > 0:
            reasons.append("builds contacts")
        if credits > 0:
            reasons.append("adds reserve")
        if distance > 0:
            reasons.append("extends route scouting")
        if specialty_theme == "route_hub":
            reasons.append("builds route cover")
        elif specialty_theme == "watch_network":
            reasons.append("adds cleaner route reads")
        elif specialty_theme == "field_refuge":
            reasons.append("creates fallback cover")
    elif objective_id == "high_value_retrieval":
        if kind in {"intel_scout", "landmark_survey", "lead_followup", "records_pull", "watch_post"} or intel > 0:
            reasons.append("adds leads")
        if specialty_theme == "route_hub":
            reasons.append("tracks who moves through the route")
        elif specialty_theme == "watch_network":
            reasons.append("improves sightlines")
        elif specialty_theme == "parts_yard":
            reasons.append("marks discreet repair traffic")
        if distance > 0:
            reasons.append("extends scouting")
    elif objective_id == "neighborhood_control":
        if credits > 0:
            reasons.append("funds nearby expansion")
        if kind in {"property_dispute", "contact_run", "service_friction", "paper_trail"} or standing > 0:
            reasons.append("builds local leverage")
        if distance <= 2:
            reasons.append("keeps you working the same block")
        elif distance > 2:
            reasons.append("is farther from your core holdings")

    seen = []
    for reason in reasons:
        if reason not in seen:
            seen.append(reason)
    return ", ".join(seen[:2])


def objective_focus_lines(sim, player_eid, objective_id, limit=3):
    """Legacy convenience: board-style lines for objective focus.

    This is used by older dialogue/context code and may be replaced by a
    structured alternative in future refactors.
    """

    return [row.get("phrase", "") for row in objective_focus_facts(sim, player_eid, objective_id, limit=limit)]


def objective_focus_facts(sim, player_eid, objective_id, limit=3):
    """Structured objective focus facts used for dialogue and other consumers."""

    objective_id = str(objective_id or "").strip().lower()
    if not objective_id:
        return ()

    state = _state(sim)
    active = [entry for entry in state.get("active", ()) if isinstance(entry, dict)]
    current = _player_chunk(sim, player_eid)
    prefs = OBJECTIVE_PREFERENCES.get(objective_id, set())
    scored = []

    for entry in active:
        kind = str(entry.get("kind", "")).strip().lower()
        chunk = _chunk_tuple(entry.get("chunk")) or current
        distance = _manhattan(current, chunk)
        reward = dict(entry.get("reward", {}))
        credits = max(0, _safe_int(reward.get("credits"), default=0))
        standing = max(0, _safe_int(reward.get("standing"), default=0))
        intel = max(0, _safe_int(reward.get("intel"), default=0))
        score = 0.0
        if kind in prefs:
            score += 3.0
        if objective_id == "debt_exit":
            score += min(3.0, credits / 12.0)
        elif objective_id == "networked_extraction":
            score += min(2.0, standing)
            score += min(2.0, credits / 20.0)
            score += min(1.5, distance * 0.18)
        elif objective_id == "neighborhood_control":
            score += min(2.4, credits / 16.0)
            score += min(1.2, standing)
            score += max(0.0, 1.8 - (distance * 0.35))
        elif objective_id == "high_value_retrieval":
            score += min(2.5, intel * 1.25)
            score += min(1.5, distance * 0.16)
        reason = _objective_support_reason(objective_id, entry, current_chunk=current)
        if score <= 0.0 or not reason:
            continue
        scored.append((-score, distance, int(entry.get("id", 0)), entry, reason))

    scored.sort()
    rows = []
    capped_limit = max(1, int(limit))
    for _score, distance, _entry_id, entry, reason in scored[:capped_limit]:
        chunk = _chunk_tuple(entry.get("chunk")) or current
        direction = _chunk_direction(current, chunk)
        title = str(entry.get("title", "Opportunity")).strip() or "Opportunity"
        rows.append(
            {
                "id": int(entry.get("id", 0)),
                "title": title,
                "kind": str(entry.get("kind", "")).strip().lower(),
                "reason": reason,
                "distance": distance,
                "direction": direction,
                "chunk": chunk,
                "phrase": f"{title} {opportunity_distance_text(distance, direction)}: {reason}.",
            }
        )
    return tuple(rows)


def _plain_label(value, default="unknown"):
    text = str(value or "").strip().replace("_", " ")
    return " ".join(text.split()) or str(default)


def _board_awareness_label(awareness):
    key = str(awareness or "").strip().lower()
    if key == "confirmed":
        return "confirmed"
    if key == "heard":
        return "secondhand"
    return "uncertain"


def _board_site_label(sim, entry):
    requirements = entry.get("requirements", {}) if isinstance(entry.get("requirements", {}), dict) else {}
    for key in ("property_name", "delivery_property_name", "pickup_property_name"):
        label = str(requirements.get(key, "") or "").strip()
        if label:
            return label
    for key in ("property_id", "delivery_property_id", "pickup_property_id"):
        property_id = str(requirements.get(key, "") or "").strip()
        if not property_id or sim is None or not hasattr(sim, "properties"):
            continue
        prop = sim.properties.get(property_id)
        if isinstance(prop, dict):
            return _property_label(prop, property_id)
    return ""


def _board_opportunity_line(sim, entry, *, dist_text, awareness, confidence, intel_source):
    title = str(entry.get("title", "Opportunity")).strip() or "Opportunity"
    source_text = opportunity_source_label(entry.get("source", "unknown"), short=False)
    reward_text = format_reward_text(entry.get("reward", {}))
    risk_text = _plain_label(entry.get("risk", "low"), default="low")
    style_bits = [_plain_label(style, default="").strip() for style in entry.get("playstyles", ()) if str(style).strip()]
    style_text = ", ".join(style_bits[:2]) if style_bits else "mixed approach"
    intel_text = _board_awareness_label(awareness)
    try:
        confidence_value = float(confidence or 0.0)
    except (TypeError, ValueError):
        confidence_value = 0.0
    intel_pct = int(round(max(0.0, min(1.0, confidence_value)) * 100.0))
    intel_source_text = _plain_label(intel_source, default="unknown source")
    site_name = _board_site_label(sim, entry)
    site_part = f" near {site_name}" if site_name else ""
    next_step = opportunity_next_step_text(sim, entry)

    line = (
        f"O{int(entry.get('id', 0))}: {title}{site_part} is {dist_text}. "
        f"Source: {source_text}. Approach: {style_text}. "
        f"Risk looks {risk_text}. Reward: {reward_text}. "
        f"Intel is {intel_text} ({intel_pct}% confidence from {intel_source_text})."
    )
    if next_step:
        line += f" Next step: {next_step}"
    return line


def evaluate_opportunity_board(sim, player_eid, limit=3, observer_eid=None):
    state = _state(sim)
    observer = player_eid if observer_eid is None else observer_eid
    if player_eid is not None:
        _bootstrap_player_opportunity_intel(sim, state, player_eid, origin_chunk=_player_chunk(sim, player_eid))
    active = [entry for entry in state.get("active", ()) if isinstance(entry, dict)]
    completed = [entry for entry in state.get("completed", ()) if isinstance(entry, dict)]
    failed = [entry for entry in state.get("failed", ()) if isinstance(entry, dict)]
    metrics = _player_metrics(sim, player_eid)
    current = _chunk_tuple(metrics.get("current_chunk")) or (0, 0)

    scoped = _observer_intel_records(
        sim,
        state,
        observer,
        viewer_chunk=current,
        player_eid=player_eid,
    )

    lines = []
    capped_limit = max(1, int(limit))
    for dist, _risk_score, _eid, entry, awareness, confidence, source in scoped[:capped_limit]:
        chunk = _chunk_tuple(entry.get("chunk")) or current
        direction = _chunk_direction(current, chunk)
        dist_text = opportunity_distance_text(dist, direction)
        lines.append(
            _board_opportunity_line(
                sim,
                entry,
                dist_text=dist_text,
                awareness=awareness,
                confidence=confidence,
                intel_source=source,
            )
        )

    if scoped:
        nearest_dist, _nearest_risk, _nearest_id, nearest, _aware, _conf, _source = scoped[0]
        nearest_chunk = _chunk_tuple(nearest.get("chunk")) or current
        nearest_dir = _chunk_direction(current, nearest_chunk)
        nearest_text = opportunity_distance_text(nearest_dist, nearest_dir)
        summary_line = (
            f"Opportunities: {len(scoped)} known, {len(completed)} done, {len(failed)} failed. "
            f"Nearest: O{int(nearest.get('id', 0))} "
            f"{str(nearest.get('title', 'Opportunity')).strip()} {nearest_text}."
        )
    else:
        summary_line = f"Opportunities: 0 known, {len(completed)} done, {len(failed)} failed."

    remaining = max(0, len(scoped) - len(lines))
    return {
        "active_count": len(scoped),
        "completed_count": len(completed),
        "failed_count": len(failed),
        "summary_line": summary_line,
        "lines": lines,
        "remaining": remaining,
    }


def evaluate_opportunity_facts(sim, player_eid, limit=3, observer_eid=None):
    """Return structured facts for the top active opportunities.

    This is intended for consumers (dialogue, UI, etc.) that want to make their
    own presentation decisions rather than rely on the board-style text.

    The result is deterministic for a given sim seed / player state.
    """

    state = _state(sim)
    observer = player_eid if observer_eid is None else observer_eid
    if player_eid is not None:
        _bootstrap_player_opportunity_intel(sim, state, player_eid, origin_chunk=_player_chunk(sim, player_eid))
    metrics = _player_metrics(sim, player_eid)
    current = _chunk_tuple(metrics.get("current_chunk")) or (0, 0)

    scoped = _observer_intel_records(
        sim,
        state,
        observer,
        viewer_chunk=current,
        player_eid=player_eid,
    )

    rows = []
    capped_limit = max(1, int(limit))
    for dist, _risk_score, _eid, entry, awareness, confidence, intel_source in scoped[:capped_limit]:
        chunk = _chunk_tuple(entry.get("chunk")) or current
        direction = _chunk_direction(current, chunk)
        reward_text = format_reward_text(entry.get("reward", {}))
        playstyles = tuple(
            str(style).strip() for style in entry.get("playstyles", ()) if str(style).strip()
        )
        risk = str(entry.get("risk", "low")).strip().lower()
        risk_score = {"calm": 0, "low": 1, "exposed": 2, "hazardous": 3}.get(risk, 1)
        tracked_target = _opportunity_focus_tracked_target(sim, entry, player_eid)
        tracked_summary = ""
        tracked_detail = ""
        tracked_stage_kind = ""
        tracked_property_id = ""
        if isinstance(tracked_target, dict):
            tracked_summary = opportunity_target_summary_text(tracked_target, include_site=False)
            tracked_detail = opportunity_target_summary_text(
                tracked_target,
                include_site=True,
                site_name=str(tracked_target.get("anchor_site_name", "") or ""),
            )
            tracked_stage_kind = str(tracked_target.get("stage_kind", "") or "").strip().lower()
            tracked_property_id = str(tracked_target.get("property_id", "") or "").strip()
        rows.append(
            {
                "id": int(entry.get("id", 0)),
                "kind": str(entry.get("kind", "")).strip().lower(),
                "title": str(entry.get("title", "Opportunity")).strip() or "Opportunity",
                "summary": str(entry.get("summary", "")).strip(),
                "risk": risk,
                "source": str(entry.get("source", "unknown")).strip().lower(),
                "source_text": opportunity_source_label(entry.get("source", "unknown"), short=False),
                "distance": dist,
                "direction": direction,
                "chunk": chunk,
                "location": str(entry.get("location", "")).strip(),
                "reward": dict(entry.get("reward", {})),
                "reward_text": reward_text,
                "requirements": dict(entry.get("requirements", {})) if isinstance(entry.get("requirements", {}), dict) else {},
                "playstyles": playstyles,
                "risk_score": risk_score,
                "organization_name": _text(entry.get("organization_name")),
                "contact_name": _text(entry.get("contact_name")),
                "contact_role": _text(entry.get("contact_role")),
                "anchor_site_name": _text(entry.get("anchor_site_name")),
                "anchor_site_kind": _text(entry.get("anchor_site_kind")).lower(),
                "anchor_site_id": _text(entry.get("anchor_site_id")),
                "awareness_state": awareness,
                "confidence": confidence,
                "intel_source": intel_source,
                "tracked_target_summary": tracked_summary,
                "tracked_target_detail": tracked_detail,
                "tracked_target_stage_kind": tracked_stage_kind,
                "tracked_target_property_id": tracked_property_id,
                "next_step": opportunity_next_step_text(sim, entry),
            }
        )
    return tuple(rows)


def opportunity_known_count(sim, player_eid, observer_eid=None):
    """Return how many active opportunities are known by the observer."""

    state = _state(sim)
    observer = player_eid if observer_eid is None else observer_eid
    if player_eid is not None:
        _bootstrap_player_opportunity_intel(sim, state, player_eid, origin_chunk=_player_chunk(sim, player_eid))
    metrics = _player_metrics(sim, player_eid)
    current = _chunk_tuple(metrics.get("current_chunk")) or (0, 0)
    scoped = _observer_intel_records(
        sim,
        state,
        observer,
        viewer_chunk=current,
        player_eid=player_eid,
    )
    return len(scoped)
