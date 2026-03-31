import random

from engine.sites import site_gameplay_profile
from game.components import (
    AI,
    ContactLedger,
    CreatureIdentity,
    FinancialProfile,
    Inventory,
    NPCNeeds,
    Occupation,
    PlayerAssets,
    Position,
    PropertyKnowledge,
)
from game.economy import chunk_economy_profile
from game.items import ITEM_CATALOG, item_display_name


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
        "distance_delivery",
        "distance_delivery_procure",
    },
    "networked_extraction": {
        "contact_run",
        "paper_trail",
        "shelter_stop",
        "district_contract",
        "property_dispute",
        "service_friction",
        "distance_delivery",
        "distance_delivery_procure",
        "distance_pickup",
    },
    "high_value_retrieval": {
        "intel_scout",
        "landmark_survey",
        "lead_followup",
        "district_contract",
        "missing_person",
        "service_friction",
        "property_dispute",
    },
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


def _player_metrics(sim, player_eid):
    assets = sim.ecs.get(PlayerAssets).get(player_eid) if sim is not None else None
    finance = sim.ecs.get(FinancialProfile).get(player_eid) if sim is not None else None
    ledger = sim.ecs.get(ContactLedger).get(player_eid) if sim is not None else None
    knowledge = sim.ecs.get(PropertyKnowledge).get(player_eid) if sim is not None else None
    inventory = sim.ecs.get(Inventory).get(player_eid) if sim is not None else None
    current_chunk = _player_chunk(sim, player_eid)
    visited_chunks = _visited_chunks(sim, player_eid, current_chunk=current_chunk)
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
    return {
        "wallet_credits": wallet,
        "bank_credits": bank,
        "reserve_credits": reserve,
        "contact_count": int(contact_count),
        "intel_leads": int(intel_leads),
        "current_chunk": current_chunk,
        "visited_chunks": visited_chunks,
        "inventory_counts": _inventory_counts(inventory),
        "killed_npc_eids": killed_eids,
    }


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


def _contact_variant_candidate(sim, prop, property_id, entry, objective_id):
    if not isinstance(prop, dict):
        return None
    standing = float((entry or {}).get("standing", 0.5))
    cx, cy = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
    prop_name = _property_label(prop, property_id)
    pools = {
        "debt_exit": ("debt_marker", "supply_shortage"),
        "networked_extraction": ("property_dispute", "service_friction"),
        "high_value_retrieval": ("service_friction", "property_dispute"),
    }
    pool = pools.get(objective_id, ("debt_marker", "service_friction", "property_dispute", "supply_shortage"))
    kind = random.Random(f"{getattr(sim, 'seed', 'seed')}:opp-contact:{objective_id}:{property_id}").choice(pool)

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
            "reward": {
                "credits": max(10, _safe_int(standing * 20, default=10)),
                "standing": 1,
            },
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
        "reward": {
            "credits": max(6, _safe_int(standing * 12, default=6)),
            "standing": 1,
            "intel": 2,
        },
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

    if lead_kind == "workplace":
        kind = "missing_person"
    elif lead_kind in {"access", "security", "hours"}:
        kind = "service_friction"
    elif lead_kind == "owner":
        kind = "property_dispute"
    else:
        pools = {
            "debt_exit": ("debt_marker", "supply_shortage", "lead_followup"),
            "networked_extraction": ("property_dispute", "missing_person", "lead_followup"),
            "high_value_retrieval": ("missing_person", "service_friction", "lead_followup"),
        }
        pool = pools.get(objective_id, ("lead_followup", "missing_person", "property_dispute", "service_friction"))
        kind = random.Random(f"{getattr(sim, 'seed', 'seed')}:opp-intel:{objective_id}:{property_id}:{lead_kind}").choice(pool)

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
            "reward": {"credits": rng.randint(16, 32), "standing": 1},
            "weight": 1.35,
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
            "reward": {"credits": rng.randint(12, 26), "intel": 1},
            "weight": 1.25,
        })
    elif discovery_kind == "supplies":
        candidates.append({
            "kind": "supply_grab",
            "source": "overworld_tag",
            "title": "Supply Grab",
            "summary": "Leverage local supply caches.",
            "playstyles": ("economic", "social", "stealth"),
            "reward": {"credits": rng.randint(10, 22), "energy": 4, "safety": 2},
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

    if features["has_storefront"] or "trade" in support_tags:
        candidates.append({
            "kind": "trade_loop",
            "source": "property_service",
            "title": "Street Exchange",
            "summary": "Work the local storefront loop for profit.",
            "playstyles": ("economic", "social", "stealth"),
            "reward": {"credits": rng.randint(12, 28), "standing": 1},
            "weight": 1.1,
        })

    if features["has_finance"] or "services" in support_tags:
        candidates.append({
            "kind": "paper_trail",
            "source": "property_service",
            "title": "Paper Trail Run",
            "summary": "Use service channels to stabilize your run.",
            "playstyles": ("social", "economic", "stealth"),
            "reward": {"credits": rng.randint(10, 20), "standing": 2},
            "weight": 1.0,
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
            "reward": {"credits": rng.randint(14, 30), "standing": 1},
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
        if area_type != "city" and candidate.get("source") == "overworld_tag":
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

    candidates = []
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
        candidates.append((eid, ai, identity, pos, occupation_comps.get(eid)))

    if len(candidates) < 2:
        return None

    rng.shuffle(candidates)
    target_eid, target_ai, target_identity, target_pos, target_occ = candidates[0]
    giver_eid = candidates[1][0]

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

    summary = (
        f"Locate and neutralize {target_name}, a {target_role} operating {distance_text}. "
        f"No noise, no trace."
    )
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
        "reward": {"credits": credits_reward, "standing": 2},
        "risk": "hazardous",
        "pressure": "high",
        "requirements": {
            "kill_target_eid": int(target_eid),
            "kill_target_name": target_name,
            "kill_target_role": target_role,
            "kill_target_description": target_description,
            "giver_npc_eid": int(giver_eid),
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


def _completion_detail(opportunity, metrics):
    requirements = opportunity.get("requirements", {}) if isinstance(opportunity.get("requirements", {}), dict) else {}
    visit_chunk = _chunk_tuple(requirements.get("visit_chunk"))
    current_chunk = _chunk_tuple(metrics.get("current_chunk"))
    visited = set(metrics.get("visited_chunks", ()))
    reasons = []
    if visit_chunk and visit_chunk not in visited and visit_chunk != current_chunk:
        return False, ""
    if visit_chunk:
        reasons.append(f"entered target chunk {visit_chunk}")

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

    require_item_id = str(requirements.get("require_item_id", "")).strip().lower()
    require_item_qty = max(1, _safe_int(requirements.get("require_item_qty"), default=1))
    if require_item_id:
        inventory_counts = metrics.get("inventory_counts", {}) if isinstance(metrics.get("inventory_counts", {}), dict) else {}
        have_qty = max(0, _safe_int(inventory_counts.get(require_item_id), default=0))
        if have_qty < require_item_qty:
            return False, ""
        item_label = str(requirements.get("item_label", "")).strip() or _item_label(require_item_id)
        reasons.append(f"carrying {item_label}")

        delivery_chunk = _chunk_tuple(requirements.get("delivery_chunk")) or visit_chunk
        if delivery_chunk and current_chunk != delivery_chunk:
            return False, ""
        if delivery_chunk:
            reasons.append(f"at delivery chunk {delivery_chunk}")

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


def _apply_reward(sim, player_eid, reward):
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
    return ", ".join(bits) if bits else "none"


def resolve_opportunities(sim, player_eid):
    state = _state(sim)
    active = list(state.get("active", ()))
    if not active:
        return []

    metrics = _player_metrics(sim, player_eid)
    completed = []
    remaining = []
    for entry in active:
        if not isinstance(entry, dict):
            continue
        _ensure_provided_item(sim, player_eid, entry, metrics)
        metrics["inventory_counts"] = _inventory_counts(sim.ecs.get(Inventory).get(player_eid) if sim is not None else None)
        is_completed, reason_text = _completion_detail(entry, metrics)
        if not is_completed:
            remaining.append(entry)
            continue

        consumed = _consume_required_item(sim, player_eid, entry)
        requirements = entry.get("requirements", {}) if isinstance(entry.get("requirements", {}), dict) else {}
        if bool(requirements.get("consume_item")) and not consumed:
            remaining.append(entry)
            continue

        reward = dict(entry.get("reward", {}))
        applied = _apply_reward(sim, player_eid, reward)
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
    reasons = []

    if objective_id == "debt_exit":
        if credits > 0:
            reasons.append("pays reserve credits")
        if kind in OBJECTIVE_PREFERENCES.get(objective_id, set()):
            reasons.append("fits a cash-building lane")
    elif objective_id == "networked_extraction":
        if kind in {"contact_run", "paper_trail"} or standing > 0:
            reasons.append("builds contacts")
        if credits > 0:
            reasons.append("adds reserve")
        if distance > 0:
            reasons.append("extends route scouting")
    elif objective_id == "high_value_retrieval":
        if kind in {"intel_scout", "landmark_survey", "lead_followup"} or intel > 0:
            reasons.append("adds leads")
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
