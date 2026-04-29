import random

from engine.sites import site_gameplay_profile
from game.components import (
    AI,
    ContactLedger,
    CreatureIdentity,
    FinancialProfile,
    Inventory,
    JusticeProfile,
    NPCMemory,
    NPCNeeds,
    NPCSocial,
    NPCTraits,
    Occupation,
    PlayerAssets,
    Position,
    PropertyKnowledge,
)
from game.economy import chunk_economy_profile
from game.items import ITEM_CATALOG, credstick_total_credits, is_credstick_item, item_display_name
from game.organization_reputation import apply_organization_reputation_delta
from game.property_runtime import (
    building_id_from_property,
    building_id_from_structure,
    property_covering,
    property_focus_position,
)
from game.service_runtime import _chunk_site_kinds


MIN_ACTIVE_OPPORTUNITIES = 6
MAX_ACTIVE_OPPORTUNITIES = 10
REMOTE_SEED_MIN_DISTANCE = 3
REMOTE_SEED_FAR_DISTANCE = 5

EXCLUDED_CONTRACT_ROLES = {"guard", "scout"}

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
        "ranger_hut",
        "ruin_shelter",
    ),
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

    intel_by_observer = state.get("intel_by_observer")
    if not isinstance(intel_by_observer, dict):
        intel_by_observer = {}
        state["intel_by_observer"] = intel_by_observer

    state["next_id"] = max(1, _safe_int(state.get("next_id"), default=1))
    state["seeded"] = bool(state.get("seeded", False))
    if "origin_chunk" in state:
        normalized_origin = _chunk_tuple(state.get("origin_chunk"))
        state["origin_chunk"] = normalized_origin
    else:
        state["origin_chunk"] = None
    return state


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

    if _AWARENESS_RANK.get(previous_awareness, 0) > _AWARENESS_RANK.get(awareness, 0):
        awareness = previous_awareness
    confidence = max(previous_confidence, confidence)

    record = {
        "opportunity_id": opportunity_id,
        "awareness_state": awareness,
        "confidence": confidence,
        "source": source,
        "last_updated_tick": int(getattr(sim, "tick", 0)),
    }
    bucket[oid_key] = record
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
        "inventory_counts": _inventory_counts(inventory),
        "killed_npc_eids": killed_eids,
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
    pool = [item_id for item_id in COURIER_ITEM_POOL if item_id in ITEM_CATALOG]
    if not pool:
        pool = sorted(ITEM_CATALOG.keys())
    return str(rng.choice(pool)).strip().lower()


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


def _specialty_chunk_opportunity_candidates(theme_id, *, identity_label="", travel=None, discovery=None, sites=None, rng=None):
    theme_id = str(theme_id or "").strip().lower()
    if not theme_id:
        return ()
    if not isinstance(rng, random.Random):
        rng = random.Random(f"specialty:{theme_id}")

    label = str(identity_label).strip() or "this stretch"
    discovery = discovery if isinstance(discovery, dict) else {}
    discovery_label = str(discovery.get("label", "")).strip()
    anchor = _specialty_anchor_for_sites(theme_id, sites, rng)
    anchor_read = _specialty_anchor_read(anchor.get("anchor_site_name"), label)
    anchor_requirements = _specialty_anchor_requirements(anchor)
    candidates = []

    if theme_id == "route_hub":
        route_cache = discovery_label or "route stash"
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
                "summary": f"A {route_cache} tucked into {anchor_read} can still pay before the next line turns over.",
                "playstyles": ("economic", "stealth", "social"),
                "reward": _reward_with_items(
                    {"credits": rng.randint(14, 28), "intel": 1},
                    rng.choice(("transit_daypass", "bottled_water", "meal_voucher")),
                ),
                "weight": 1.18,
                "requirements": dict(anchor_requirements),
                **anchor,
            },
        ))
    elif theme_id == "parts_yard":
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
                "summary": f"Someone working off {anchor_read} needs a quiet fix before a bad breakdown turns public.",
                "playstyles": ("economic", "social", "stealth"),
                "reward": _reward_with_items(
                    {"credits": rng.randint(14, 26), "standing": 1},
                    rng.choice(("pocket_multitool", "prybar", "battery_pack")),
                ),
                "weight": 1.16,
                "requirements": dict(anchor_requirements),
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
                "summary": f"Carry water and remedies between the rough refuge stops that hang off {anchor_read}.",
                "playstyles": ("social", "stealth", "economic"),
                "reward": _reward_with_items(
                    {"credits": rng.randint(8, 18), "energy": 6, "safety": 3},
                    rng.choice(("bottled_water", "hydration_salts", "med_gel")),
                ),
                "weight": 1.12,
                "requirements": dict(anchor_requirements),
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
    if stage_kind == "pickup":
        return f"O{opp_id} {title}: pickup target staged at {site_name}. Interact there to make the pickup."
    if stage_kind == "delivery":
        return f"O{opp_id} {title}: handoff target staged at {site_name}. Interact there to complete the drop."
    return f"O{opp_id} {title}: work target staged at {site_name}. Interact there to complete the job."


def stage_active_opportunities(sim, player_eid):
    state = _state(sim)
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
        requirements = entry.get("requirements", {}) if isinstance(entry.get("requirements", {}), dict) else {}
        if not _site_task_expected(requirements):
            continue

        item_id = str(requirements.get("require_item_id", "")).strip().lower()
        item_qty = max(1, _safe_int(requirements.get("require_item_qty"), default=1))
        carried_qty = max(0, _safe_int(inventory_counts.get(item_id), default=0)) if item_id else 0

        pickup_chunk = _chunk_tuple(requirements.get("pickup_chunk"))
        if bool(requirements.get("provide_item")) and item_id and carried_qty < item_qty and pickup_chunk == current_chunk:
            existing_pickup = _site_target_for_requirements(
                sim,
                requirements,
                property_key="pickup_property_id",
                building_key="pickup_building_id",
                chunk=current_chunk,
            )
            if existing_pickup is None:
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

    candidates = []

    if discovery_kind == "salvage":
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
            "summary": "Strip the workable parts before the scrappers get there first.",
            "playstyles": ("economic", "stealth", "combat"),
            "reward": _reward_with_items({"credits": rng.randint(14, 28), "intel": 1}, rng.choice(("light_ammo_box", "pocket_multitool"))),
            "weight": 1.28,
        })
    elif discovery_kind == "water":
        candidates.append({
            "kind": "water_run",
            "source": "overworld_tag",
            "title": "Water Relay",
            "summary": "Use the water route for recovery and side deals.",
            "playstyles": ("social", "economic", "stealth"),
            "reward": {"credits": rng.randint(8, 16), "energy": 6, "safety": 4},
            "weight": 1.2,
        })
    elif discovery_kind == "tools":
        candidates.append({
            "kind": "tool_pickup",
            "source": "overworld_tag",
            "title": "Tool Pickup",
            "summary": "Find workable tools and move them to buyers.",
            "playstyles": ("economic", "stealth"),
            "reward": _reward_with_items({"credits": rng.randint(12, 26), "intel": 1}, rng.choice(("lockpick_kit", "pocket_multitool"))),
            "weight": 1.25,
        })
        candidates.append({
            "kind": "tool_procurement",
            "source": "overworld_tag",
            "title": "Tool Procurement",
            "summary": "A local buyer wants fresh tools before the district notices the gap.",
            "playstyles": ("economic", "stealth", "social"),
            "reward": _reward_with_items({"credits": rng.randint(14, 28), "standing": 1}, rng.choice(("lockpick_kit", "pocket_multitool"))),
            "weight": 1.18,
        })
    elif discovery_kind == "supplies":
        candidates.append({
            "kind": "supply_grab",
            "source": "overworld_tag",
            "title": "Supply Grab",
            "summary": "Leverage local supply caches.",
            "playstyles": ("economic", "social", "stealth"),
            "reward": _reward_with_items({"credits": rng.randint(10, 22), "energy": 4, "safety": 2}, rng.choice(("med_gel", "hydration_salts"))),
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
        for entry in list(state.get("active", ())) + list(state.get("completed", ()))
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
        for entry in list(state.get("active", ())) + list(state.get("completed", ()))
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


def refresh_dynamic_opportunities(sim, player_eid, rng=None):
    state = _state(sim)
    seed_run_opportunities(sim, player_eid=player_eid, rng=rng)
    active = state.get("active", [])
    if len(active) >= MAX_ACTIVE_OPPORTUNITIES:
        return state

    if not isinstance(rng, random.Random):
        seed = f"{getattr(sim, 'seed', 'seed')}:opportunity-dynamic:{player_eid}:{getattr(sim, 'tick', 0)}"
        rng = random.Random(seed)

    existing_keys = {
        str(entry.get("key", "")).strip().lower()
        for entry in list(state.get("active", ())) + list(state.get("completed", ()))
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
    return state


def _completion_detail(sim, opportunity, metrics):
    requirements = opportunity.get("requirements", {}) if isinstance(opportunity.get("requirements", {}), dict) else {}
    visit_chunk = _chunk_tuple(requirements.get("visit_chunk"))
    current_chunk = _chunk_tuple(metrics.get("current_chunk"))
    visited = set(metrics.get("visited_chunks", ()))
    reasons = []
    if visit_chunk and visit_chunk not in visited and visit_chunk != current_chunk:
        return False, ""

    target_property_id = str(requirements.get("property_id", "")).strip()
    target_building_id = str(requirements.get("building_id", "")).strip()
    if (target_property_id or target_building_id) and not _matches_site_requirement(
        sim,
        metrics,
        property_id=target_property_id,
        building_id=target_building_id,
    ):
        return False, ""

    min_contacts = _safe_int(requirements.get("contact_count"), default=0)
    if min_contacts > _safe_int(metrics.get("contact_count"), default=0):
        return False, ""
    if min_contacts > 0:
        reasons.append(f"contacts >= {min_contacts}")

    min_leads = _safe_int(requirements.get("intel_leads"), default=0)
    if min_leads > _safe_int(metrics.get("intel_leads"), default=0):
        return False, ""
    if min_leads > 0:
        reasons.append(f"intel leads >= {min_leads}")

    min_reserve = _safe_int(requirements.get("reserve_credits"), default=0)
    if min_reserve > _safe_int(metrics.get("reserve_credits"), default=0):
        return False, ""
    if min_reserve > 0:
        reasons.append(f"reserve >= {min_reserve}c")

    interact_npc_eid = _safe_int(requirements.get("interact_npc_eid"), default=0)
    interaction_requirement = str(requirements.get("interaction_requirement", "contact")).strip().lower() or "contact"
    interact_name = str(requirements.get("interact_npc_name", "the contact")).strip() or "the contact"
    require_item_id = str(requirements.get("require_item_id", "")).strip().lower()
    if interact_npc_eid > 0 and not require_item_id:
        recent_npc_eids = metrics.get("recent_npc_eids", frozenset())
        if interact_npc_eid not in recent_npc_eids:
            return False, ""
        if interaction_requirement == "pressure":
            player_eid = getattr(sim, "player_eid", None)
            if player_eid is None or not _recent_pressure_interaction(sim, interact_npc_eid, player_eid):
                return False, ""
            reasons.append(f"leaned on {interact_name}")
        else:
            reasons.append(f"made contact with {interact_name}")
    require_item_qty = max(1, _safe_int(requirements.get("require_item_qty"), default=1))
    if require_item_id:
        inventory_counts = metrics.get("inventory_counts", {}) if isinstance(metrics.get("inventory_counts", {}), dict) else {}
        have_qty = max(0, _safe_int(inventory_counts.get(require_item_id), default=0))
        if have_qty < require_item_qty:
            return False, ""
        item_label = str(requirements.get("item_label", "")).strip() or _item_label(require_item_id)
        reasons.append(f"carrying {item_label}")

        delivery_chunk = _chunk_tuple(requirements.get("delivery_chunk")) or visit_chunk
        if interact_npc_eid > 0:
            recent_npc_eids = metrics.get("recent_npc_eids", frozenset())
            if interact_npc_eid not in recent_npc_eids:
                return False, ""
            if delivery_chunk and current_chunk != delivery_chunk:
                return False, ""
            reasons.append(f"handed over to {interact_name}")
        else:
            delivery_property_id = str(requirements.get("delivery_property_id", "")).strip() or target_property_id
            delivery_building_id = str(requirements.get("delivery_building_id", "")).strip() or target_building_id
            if not (delivery_property_id or delivery_building_id):
                return False, ""
            if not _matches_site_requirement(
                sim,
                metrics,
                property_id=delivery_property_id,
                building_id=delivery_building_id,
            ):
                return False, ""
            if not _matches_recent_site_interaction(
                metrics,
                property_id=delivery_property_id,
                building_id=delivery_building_id,
            ):
                return False, ""
            reasons.append("completed handoff at delivery site")

        if delivery_chunk and current_chunk != delivery_chunk:
            return False, ""
    elif target_property_id or target_building_id:
        if not _matches_recent_site_interaction(
            metrics,
            property_id=target_property_id,
            building_id=target_building_id,
        ):
            return False, ""
        reasons.append("completed work at target site")
    elif _site_task_expected(requirements):
        return False, ""

    kill_target_eid = _safe_int(requirements.get("kill_target_eid"), default=0)
    if kill_target_eid > 0:
        if not bool(requirements.get("player_accepted")):
            return False, ""
        killed_eids = metrics.get("killed_npc_eids", frozenset())
        if kill_target_eid not in killed_eids:
            return False, ""
        target_name = str(requirements.get("kill_target_name", "target")).strip() or "target"
        reasons.append(f"{target_name} neutralized")
    return True, ", ".join(reasons) if reasons else "requirements met"


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
    requirements = opportunity.get("requirements", {}) if isinstance(opportunity.get("requirements", {}), dict) else {}
    if not bool(requirements.get("provide_item")):
        return

    item_id = str(requirements.get("require_item_id", "")).strip().lower()
    if not item_id:
        return

    pickup_chunk = _chunk_tuple(requirements.get("pickup_chunk"))
    current_chunk = _chunk_tuple(metrics.get("current_chunk"))
    if pickup_chunk and pickup_chunk != current_chunk:
        return
    pickup_property_id = str(requirements.get("pickup_property_id", "")).strip()
    pickup_building_id = str(requirements.get("pickup_building_id", "")).strip()
    if (pickup_property_id or pickup_building_id) and not _matches_site_requirement(
        sim,
        metrics,
        property_id=pickup_property_id,
        building_id=pickup_building_id,
    ):
        return
    pickup_interact_npc_eid = _safe_int(requirements.get("pickup_interact_npc_eid"), default=0)
    if pickup_interact_npc_eid > 0:
        recent_npc_eids = metrics.get("recent_npc_eids", frozenset())
        if pickup_interact_npc_eid not in recent_npc_eids:
            return
    elif pickup_property_id or pickup_building_id:
        if not _matches_recent_site_interaction(
            metrics,
            property_id=pickup_property_id,
            building_id=pickup_building_id,
        ):
            return
    else:
        return

    inventory = sim.ecs.get(Inventory).get(player_eid) if sim is not None else None
    if not inventory:
        return

    counts = _inventory_counts(inventory)
    if _safe_int(counts.get(item_id), default=0) >= max(1, _safe_int(requirements.get("require_item_qty"), default=1)):
        return

    metadata = {
        "quest_opportunity_id": int(opportunity.get("id", 0) or 0),
        "quest_kind": str(opportunity.get("kind", "")).strip().lower(),
        "acquisition": str(requirements.get("acquisition_hint", "provided")).strip().lower() or "provided",
    }
    inventory.add_item(
        item_id=item_id,
        quantity=1,
        stack_max=_item_stack_max(item_id),
        instance_id=f"opp-{int(opportunity.get('id', 0) or 0)}-{item_id}-{int(getattr(sim, 'tick', 0))}",
        owner_tag="opportunity",
        metadata=metadata,
    )


def _consume_required_item(sim, player_eid, opportunity):
    requirements = opportunity.get("requirements", {}) if isinstance(opportunity.get("requirements", {}), dict) else {}
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


def resolve_opportunities(sim, player_eid):
    state = _state(sim)
    active = list(state.get("active", ()))
    if not active:
        return []

    stage_active_opportunities(sim, player_eid)
    metrics = _player_metrics(sim, player_eid)
    completed = []
    remaining = []
    for entry in active:
        if not isinstance(entry, dict):
            continue
        _ensure_provided_item(sim, player_eid, entry, metrics)
        metrics["inventory_counts"] = _inventory_counts(sim.ecs.get(Inventory).get(player_eid) if sim is not None else None)
        is_completed, reason_text = _completion_detail(sim, entry, metrics)
        if not is_completed:
            remaining.append(entry)
            continue

        consumed = _consume_required_item(sim, player_eid, entry)
        requirements = entry.get("requirements", {}) if isinstance(entry.get("requirements", {}), dict) else {}
        if bool(requirements.get("consume_item")) and not consumed:
            remaining.append(entry)
            continue

        reward = dict(entry.get("reward", {}))
        applied = _apply_reward(sim, player_eid, reward, opportunity=entry)
        done = dict(entry)
        done["status"] = "completed"
        done["completed_tick"] = int(getattr(sim, "tick", 0))
        done["reward_applied"] = applied
        completion_reason = str(reason_text).strip() or "requirements met"
        if consumed:
            done["consumed_item"] = consumed
            completion_reason = f"{completion_reason}, delivered {consumed['item_label']}"
        done["completion_reason"] = completion_reason
        state["completed"].append(done)
        _upsert_observer_intel(
            sim,
            state,
            observer_eid=player_eid,
            opportunity_id=int(done.get("id", 0)),
            awareness_state="confirmed",
            confidence=1.0,
            source="completed",
        )
        completed.append(done)

    if completed:
        state["active"] = remaining
    return completed


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
            done = dict(entry)
            done["status"] = str(status or "completed").strip().lower() or "completed"
            done["completed_tick"] = int(getattr(sim, "tick", 0))
            done["reward_applied"] = dict(reward_applied or {})
            done["completion_reason"] = (
                str(completion_reason).strip()
                or f"resolved externally ({done['status']})"
            )
            if isinstance(extra, dict):
                done.update(extra)
            state["completed"].append(done)
            resolved = done
            continue
        remaining.append(entry)

    if resolved is not None:
        state["active"] = remaining
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


def evaluate_opportunity_board(sim, player_eid, limit=3, observer_eid=None):
    state = _state(sim)
    observer = player_eid if observer_eid is None else observer_eid
    if player_eid is not None:
        _bootstrap_player_opportunity_intel(sim, state, player_eid, origin_chunk=_player_chunk(sim, player_eid))
    active = [entry for entry in state.get("active", ()) if isinstance(entry, dict)]
    completed = [entry for entry in state.get("completed", ()) if isinstance(entry, dict)]
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
        reward_text = format_reward_text(entry.get("reward", {}))
        style_bits = [str(style).strip() for style in entry.get("playstyles", ()) if str(style).strip()]
        style_text = "/".join(style_bits[:2]) if style_bits else "mixed"
        source_text = opportunity_source_label(entry.get("source", "unknown"), short=True)
        intel_tag = f"intel:{awareness}/{int(round(confidence * 100.0))}%/{source}"
        lines.append(
            f"O{int(entry.get('id', 0))} {dist_text} "
            f"{str(entry.get('title', 'Opportunity')).strip()} "
            f"@({chunk[0]},{chunk[1]}) src:{source_text} {style_text} "
            f"risk:{str(entry.get('risk', 'low')).strip()} rw:{reward_text} {intel_tag}"
        )

    if scoped:
        nearest_dist, _nearest_risk, _nearest_id, nearest, _aware, _conf, _source = scoped[0]
        nearest_chunk = _chunk_tuple(nearest.get("chunk")) or current
        nearest_dir = _chunk_direction(current, nearest_chunk)
        nearest_text = opportunity_distance_text(nearest_dist, nearest_dir)
        summary_line = (
            f"Opp {len(scoped)} known/{len(completed)} done | "
            f"nearest O{int(nearest.get('id', 0))} {nearest_text} "
            f"{str(nearest.get('title', 'Opportunity')).strip()}"
        )
    else:
        summary_line = f"Opp 0 known/{len(completed)} done"

    remaining = max(0, len(scoped) - len(lines))
    return {
        "active_count": len(scoped),
        "completed_count": len(completed),
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
