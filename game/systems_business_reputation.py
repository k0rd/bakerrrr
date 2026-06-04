"""Citywide business reputation knowledge and social spread."""

from __future__ import annotations

from engine.events import Event
from engine.systems import System

from game.components import BusinessKnowledge, IncidentKnowledge, NPCMemory, NPCSocial, NPCTraits, Position, PropertyKnowledge
from game.incident_runtime import incident_record
from game.property_runtime import (
    finance_services_for_property as _finance_services_for_property,
    property_is_storefront as _property_is_storefront,
    resolve_property_record as _resolve_property_record,
    site_services_for_property as _site_services_for_property,
)
from game.system_support.actor_runtime import _detail_tick_allowed
from game.system_support.interaction_ordering import _manhattan
from game.system_support.social_knowledge_runtime import hydrate_business_social_knowledge

_SOCIAL_SECRET_ARCHETYPES = frozenset({
    "nightclub",
    "bar",
    "tavern",
    "club",
    "lounge",
    "cafe",
    "restaurant",
    "gaming_hall",
    "casino",
    "music_venue",
    "pool_hall",
    "karaoke_box",
})
_SOCIAL_NOTEBOOK_ARCHETYPES = _SOCIAL_SECRET_ARCHETYPES | frozenset({
    "diner",
    "park",
    "plaza",
    "market",
    "library",
    "gym",
    "barbershop",
    "salon",
    "street_kitchen",
    "food_cart",
    "arcade",
})


def _clamp_unit(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return float(max(0.0, min(1.0, number)))


def _clamp_signed_unit(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return float(max(-1.0, min(1.0, number)))


def _text(value):
    return str(value or "").strip()


def _property_point(prop):
    if not isinstance(prop, dict):
        return None
    try:
        return (
            int(prop.get("x", 0) or 0),
            int(prop.get("y", 0) or 0),
            int(prop.get("z", 0) or 0),
        )
    except (TypeError, ValueError):
        return None


def _business_reputation_stats(sim):
    stats = getattr(sim, "business_reputation_stats", None)
    if not isinstance(stats, dict):
        stats = {}
        sim.business_reputation_stats = stats
    return stats


def _business_reputation_tick_cache(sim, key):
    stats = _business_reputation_stats(sim)
    cache = stats.get(key)
    if not isinstance(cache, dict):
        cache = {}
        stats[key] = cache
    current_tick = int(getattr(sim, "tick", 0) or 0)
    if int(cache.get("_tick", -1) or -1) != current_tick:
        cache.clear()
        cache["_tick"] = current_tick
    return cache


def _property_business_state_metadata(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    state = metadata.get("player_business")
    return state if isinstance(state, dict) else {}


def _property_business_visibility(prop):
    if not isinstance(prop, dict):
        return 0.0
    visibility = 0.0
    if _property_is_storefront(prop):
        visibility += 0.18
    if _finance_services_for_property(prop):
        visibility += 0.08
    if _site_services_for_property(prop):
        visibility += 0.08
    if _text((prop.get("metadata") or {}).get("business_name")):
        visibility += 0.06
    return _clamp_unit(visibility, default=0.0)


def _player_business_visible_community_signal(prop):
    state = _property_business_state_metadata(prop)
    if not state:
        return {"positive": 0.0, "negative": 0.0}

    positive = 0.0
    negative = 0.0
    customer_policy = _text(state.get("customer_policy")).lower()
    markup_mode = _text(state.get("markup_mode")).lower()
    hours_mode = _text(state.get("hours_mode")).lower()
    last_summary = state.get("last_summary")
    last_summary = last_summary if isinstance(last_summary, dict) else {}

    if customer_policy == "public":
        positive += 0.05
    elif customer_policy == "staff_only":
        negative += 0.08
    elif customer_policy == "closed":
        negative += 0.12

    if markup_mode == "discount":
        positive += 0.08
    elif markup_mode == "standard":
        positive += 0.03
    elif markup_mode == "premium":
        negative += 0.04
    elif markup_mode == "steep":
        negative += 0.10

    if hours_mode in {"always_open", "extended"}:
        positive += 0.04
    elif hours_mode == "limited":
        negative += 0.03

    try:
        service_reliability = float(last_summary.get("service_reliability", 0.0) or 0.0)
    except (TypeError, ValueError):
        service_reliability = 0.0
    if service_reliability >= 0.92:
        positive += 0.08
    elif service_reliability and service_reliability < 0.62:
        negative += 0.08

    operating_note = _text(last_summary.get("operating_note")).lower()
    if operating_note == "tight crew":
        positive += 0.05
    elif operating_note in {"patchy ops", "frayed ops"}:
        negative += 0.06

    if int(last_summary.get("unpaid_wages", 0) or 0) > 0:
        negative += 0.08
    if int(last_summary.get("unpaid_upkeep", 0) or 0) > 0:
        negative += 0.05

    return {
        "positive": _clamp_unit(positive, default=0.0),
        "negative": _clamp_unit(negative, default=0.0),
    }


def _business_scope_profile(
    sim,
    score,
    *,
    secret_gate=0.0,
):
    try:
        chunk_size = int(getattr(sim, "chunk_size", 16) or 16)
    except (TypeError, ValueError):
        chunk_size = 16
    chunk_size = max(12, chunk_size)
    adjusted_score = _clamp_unit(score, default=0.0) * max(0.36, 1.0 - (_clamp_unit(secret_gate, default=0.0) * 0.42))
    adjusted_score = _clamp_unit(adjusted_score, default=0.0)
    if adjusted_score >= 0.72:
        key = "city"
        label = "city-known"
        radius = int(round(chunk_size * 4.4))
    elif adjusted_score >= 0.46:
        key = "district"
        label = "district-known"
        radius = int(round(chunk_size * 2.6))
    elif adjusted_score >= 0.24:
        key = "chunk"
        label = "chunk-known"
        radius = int(round(chunk_size * 1.35))
    else:
        key = "local"
        label = "local talk"
        radius = int(round(chunk_size * 0.75))
    return {
        "key": key,
        "label": label,
        "radius": max(6, int(radius)),
        "score": round(float(adjusted_score), 3),
    }


def _business_record_strength(record):
    if not isinstance(record, dict):
        return 0.0
    return _clamp_unit(
        (float(record.get("familiarity", 0.0) or 0.0) * 0.14)
        + (float(record.get("trust", 0.0) or 0.0) * 0.16)
        + (float(record.get("reliability", 0.0) or 0.0) * 0.16)
        + (float(record.get("fear", 0.0) or 0.0) * 0.12)
        + (float(record.get("heat", 0.0) or 0.0) * 0.12)
        + (float(record.get("loyalty", 0.0) or 0.0) * 0.12)
        + (float(record.get("resentment", 0.0) or 0.0) * 0.12)
        + (abs(float(record.get("price_fairness", 0.0) or 0.0)) * 0.06)
        + (float(record.get("social_interest", 0.0) or 0.0) * 0.1),
        default=0.0,
    )


def property_supports_business_reputation(prop):
    if not isinstance(prop, dict):
        return False
    if _text(prop.get("kind")).lower() not in {"building", "asset"}:
        return False
    return bool(
        _property_is_storefront(prop)
        or _finance_services_for_property(prop)
        or _site_services_for_property(prop)
        or _text((prop.get("metadata") or {}).get("business_name"))
    )


def social_secret_site_trust_gate(prop):
    if not isinstance(prop, dict):
        return 0.0
    metadata = prop.get("metadata", {}) if isinstance(prop.get("metadata", {}), dict) else {}
    archetype = _text(metadata.get("archetype")).lower()
    try:
        explicit_gate = float(metadata.get("social_trust_gate", 0.0) or 0.0)
    except (TypeError, ValueError):
        explicit_gate = 0.0
    gate = max(0.0, min(0.98, explicit_gate))
    if not gate and bool(metadata.get("shared_social_site")):
        gate = 0.62
    if archetype in _SOCIAL_SECRET_ARCHETYPES:
        if _text(metadata.get("customer_policy")).lower() == "staff_only":
            gate = max(gate, 0.58)
        if bool(metadata.get("dialogue_trade_only")):
            gate = max(gate, 0.78)
        if _text(metadata.get("hidden_contact_kind")):
            gate = max(gate, 0.74)
    return _clamp_unit(gate, default=0.0)


def remember_hidden_social_site_for_actor(sim, eid, property_id, *, source_eid=None, confidence=0.5):
    property_key = _text(property_id)
    if sim is None or eid is None or not property_key:
        return False
    prop = _resolve_property_record(sim, property_key)
    if not isinstance(prop, dict) or social_secret_site_trust_gate(prop) <= 0.0:
        return False
    try:
        actor_eid = int(eid)
    except (TypeError, ValueError):
        return False
    knowledge = sim.ecs.get(PropertyKnowledge).get(actor_eid)
    if knowledge is None:
        sim.ecs.add(actor_eid, PropertyKnowledge())
        knowledge = sim.ecs.get(PropertyKnowledge).get(actor_eid)
    if not isinstance(knowledge, PropertyKnowledge):
        return False
    existing = knowledge.property_entry(property_key)
    prior_confidence = float(existing.get("confidence", 0.0) or 0.0) if isinstance(existing, dict) else 0.0
    prior_source = existing.get("source_eid") if isinstance(existing, dict) else None
    prior_hidden = bool(knowledge.is_hidden(property_key))
    next_confidence = _clamp_unit(confidence, default=0.5)
    knowledge.remember(
        property_key,
        owner_eid=prop.get("owner_eid"),
        owner_tag=prop.get("owner_tag"),
        confidence=next_confidence,
        tick=int(getattr(sim, "tick", 0) or 0),
        source_eid=source_eid,
        lead_kind="social",
    )
    knowledge.hide(property_key)
    return (
        not isinstance(existing, dict)
        or prior_confidence + 0.04 < next_confidence
        or prior_source != source_eid
        or not prior_hidden
    )


def business_knowledge_for(sim, eid, *, create=False):
    if sim is None or eid is None:
        return None
    try:
        actor_eid = int(eid)
    except (TypeError, ValueError):
        return None
    knowledge = sim.ecs.get(BusinessKnowledge).get(actor_eid)
    if knowledge is None and create:
        sim.ecs.add(actor_eid, BusinessKnowledge())
        knowledge = sim.ecs.get(BusinessKnowledge).get(actor_eid)
    return knowledge


def _incident_business_pressure(sim, eid, property_id):
    property_id = _text(property_id)
    if sim is None or eid is None or not property_id:
        return 0.0
    knowledge = sim.ecs.get(IncidentKnowledge).get(eid)
    if not isinstance(knowledge, IncidentKnowledge):
        return 0.0
    pressure = 0.0
    for record in tuple(getattr(knowledge, "records", {}).values()):
        if not isinstance(record, dict):
            continue
        incident = incident_record(sim, record.get("incident_id"))
        if not isinstance(incident, dict):
            continue
        if _text(incident.get("property_id")) != property_id:
            continue
        severity = max(0.0, min(1.0, float(int(incident.get("severity", 0) or 0)) / 100.0))
        confidence = _clamp_unit(record.get("confidence", 0.0), default=0.0)
        depth = max(0, int(record.get("propagation_depth", 0) or 0))
        firsthand = bool(record.get("firsthand", False))
        source_mult = 1.0 if firsthand else 0.82 if _text(record.get("source_kind")).lower() == "camera" else 0.72
        pressure += severity * confidence * source_mult * max(0.28, 1.0 - (depth * 0.18))
    return _clamp_unit(pressure, default=0.0)


def business_opinion_profile(sim, eid, property_id):
    property_key = _text(property_id)
    base = {
        "property_id": property_key,
        "familiarity": 0.0,
        "trust": 0.0,
        "reliability": 0.0,
        "fear": 0.0,
        "heat": 0.0,
        "price_fairness": 0.0,
        "loyalty": 0.0,
        "resentment": 0.0,
        "coherence": 0.0,
        "propagation_depth": 0,
        "incident_pressure": 0.0,
        "tags": (),
    }
    if not property_key:
        return dict(base)

    knowledge = business_knowledge_for(sim, eid, create=False)
    record = None
    if isinstance(knowledge, BusinessKnowledge):
        record = (knowledge.records or {}).get(property_key)
    if isinstance(record, dict):
        base.update({
            "familiarity": _clamp_unit(record.get("familiarity", 0.0), default=0.0),
            "trust": _clamp_unit(record.get("trust", 0.0), default=0.0),
            "reliability": _clamp_unit(record.get("reliability", 0.0), default=0.0),
            "fear": _clamp_unit(record.get("fear", 0.0), default=0.0),
            "heat": _clamp_unit(record.get("heat", 0.0), default=0.0),
            "price_fairness": _clamp_signed_unit(record.get("price_fairness", 0.0), default=0.0),
            "loyalty": _clamp_unit(record.get("loyalty", 0.0), default=0.0),
            "resentment": _clamp_unit(record.get("resentment", 0.0), default=0.0),
            "coherence": _clamp_unit(record.get("coherence", 0.0), default=0.0),
            "propagation_depth": max(0, int(record.get("propagation_depth", 0) or 0)),
            "tags": tuple(record.get("tags", ()) or ()),
        })

    pressure = _incident_business_pressure(sim, eid, property_key)
    base["incident_pressure"] = pressure
    if pressure > 0.0:
        base["trust"] = _clamp_unit(base["trust"] * max(0.22, 1.0 - (pressure * 0.58)), default=0.0)
        base["reliability"] = _clamp_unit(base["reliability"] * max(0.28, 1.0 - (pressure * 0.46)), default=0.0)
        base["loyalty"] = _clamp_unit(base["loyalty"] * max(0.32, 1.0 - (pressure * 0.28)), default=0.0)
        base["fear"] = _clamp_unit(max(base["fear"], pressure * 0.74), default=0.0)
        base["heat"] = _clamp_unit(max(base["heat"], pressure * 0.88), default=0.0)
        base["resentment"] = _clamp_unit(max(base["resentment"], pressure * 0.42), default=0.0)
    return base


def business_record_reputation_scope_profile(sim, property_id, record):
    property_key = _text(property_id)
    if sim is None or not property_key or not isinstance(record, dict):
        return {"key": "", "label": "", "radius": 0, "score": 0.0}
    prop = _resolve_property_record(sim, property_key)
    if not property_supports_business_reputation(prop):
        return {"key": "", "label": "", "radius": 0, "score": 0.0}
    depth = max(0, int(record.get("propagation_depth", 0) or 0))
    scope_score = (
        (float(record.get("social_interest", 0.0) or 0.0) * 0.1)
        + (_business_record_strength(record) * 0.44)
        + (_clamp_unit(record.get("coherence", 0.0), default=0.0) * 0.16)
        + (_clamp_unit(record.get("confidence", 0.0), default=0.0) * 0.1)
        + (0.04 if bool(record.get("firsthand", False)) else 0.0)
        - min(0.24, depth * 0.08)
    )
    return _business_scope_profile(
        sim,
        scope_score,
        secret_gate=social_secret_site_trust_gate(prop),
    )


def _snapshot_business_scope_profile(sim, prop, snapshot):
    if sim is None or not isinstance(prop, dict) or not isinstance(snapshot, dict):
        return {"key": "", "label": "", "radius": 0, "score": 0.0}
    awareness = max(
        float(snapshot.get("weighted_awareness", 0.0) or 0.0),
        float(int(snapshot.get("awareness_count", 0) or 0)),
    )
    if awareness < 0.62:
        return {"key": "", "label": "", "radius": 0, "score": 0.0}
    intensity = max(
        _clamp_unit(snapshot.get("patronage_score", 0.0), default=0.0),
        _clamp_unit(snapshot.get("staple_score", 0.0), default=0.0),
        _clamp_unit(snapshot.get("trouble_score", 0.0), default=0.0),
        _clamp_unit(snapshot.get("gouging_score", 0.0), default=0.0),
        _clamp_unit(snapshot.get("incident_pressure", 0.0), default=0.0),
    )
    accent = max(
        _clamp_unit(snapshot.get("trust", 0.0), default=0.0),
        _clamp_unit(snapshot.get("reliability", 0.0), default=0.0),
        _clamp_unit(snapshot.get("fear", 0.0), default=0.0),
        _clamp_unit(snapshot.get("heat", 0.0), default=0.0),
        _clamp_unit(snapshot.get("resentment", 0.0), default=0.0),
        abs(_clamp_signed_unit(snapshot.get("price_fairness", 0.0), default=0.0)),
    )
    awareness_factor = min(1.0, awareness / 4.5)
    holder_factor = min(1.0, float(int(snapshot.get("holder_count", 0) or 0)) / 8.0)
    scope_score = (
        (intensity * 0.54)
        + (awareness_factor * 0.24)
        + (holder_factor * 0.14)
        + (accent * 0.08)
    )
    return _business_scope_profile(
        sim,
        scope_score,
        secret_gate=social_secret_site_trust_gate(prop),
    )


def _property_business_reputation_core_snapshot(sim, property_id):
    property_key = _text(property_id)
    base = {
        "property_id": property_key,
        "awareness_count": 0,
        "holder_count": 0,
        "weighted_awareness": 0.0,
        "familiarity": 0.0,
        "trust": 0.0,
        "reliability": 0.0,
        "fear": 0.0,
        "heat": 0.0,
        "price_fairness": 0.0,
        "loyalty": 0.0,
        "resentment": 0.0,
        "incident_pressure": 0.0,
    }
    if sim is None or not property_key:
        return dict(base)

    cache = _business_reputation_tick_cache(sim, "property_core_cache")
    cached = cache.get(property_key)
    if isinstance(cached, dict):
        return dict(cached)

    total_weight = 0.0
    aggregates = {
        "familiarity": 0.0,
        "trust": 0.0,
        "reliability": 0.0,
        "fear": 0.0,
        "heat": 0.0,
        "price_fairness": 0.0,
        "loyalty": 0.0,
        "resentment": 0.0,
        "incident_pressure": 0.0,
    }
    awareness_count = 0
    holder_count = 0

    for eid, knowledge in sim.ecs.get(BusinessKnowledge).items():
        if not isinstance(knowledge, BusinessKnowledge):
            continue
        record = (knowledge.records or {}).get(property_key)
        if not isinstance(record, dict):
            continue
        holder_count += 1
        profile = business_opinion_profile(sim, eid, property_key)
        familiarity = _clamp_unit(profile.get("familiarity", 0.0), default=0.0)
        coherence = max(
            _clamp_unit(profile.get("coherence", 0.0), default=0.0),
            0.24 if bool(record.get("firsthand", False)) else 0.0,
        )
        awareness_weight = max(
            0.16,
            (familiarity * 0.48)
            + (coherence * 0.28)
            + (float(record.get("confidence", 0.0) or 0.0) * 0.24),
        )
        total_weight += awareness_weight
        awareness_count += 1
        for key in tuple(aggregates.keys()):
            value = profile.get(key, 0.0)
            if key == "price_fairness":
                value = _clamp_signed_unit(value, default=0.0)
            else:
                value = _clamp_unit(value, default=0.0)
            aggregates[key] += float(value) * awareness_weight

    if total_weight <= 0.0:
        cache[property_key] = dict(base)
        return dict(base)

    snapshot = dict(base)
    snapshot["awareness_count"] = int(awareness_count)
    snapshot["holder_count"] = int(holder_count)
    snapshot["weighted_awareness"] = round(float(total_weight), 4)
    for key, total in aggregates.items():
        value = float(total) / float(total_weight)
        if key == "price_fairness":
            snapshot[key] = _clamp_signed_unit(value, default=0.0)
        else:
            snapshot[key] = _clamp_unit(value, default=0.0)

    cache[property_key] = dict(snapshot)
    return snapshot


def _property_business_community_signal(sim, property_id):
    property_key = _text(property_id)
    base = {
        "community_signal_lift": 0.0,
        "community_signal_drag": 0.0,
        "community_signal_radius": 0,
        "community_signal_note": "",
    }
    if sim is None or not property_key:
        return dict(base)
    cache = _business_reputation_tick_cache(sim, "community_signal_cache")
    cached = cache.get(property_key)
    if isinstance(cached, dict):
        return dict(cached)

    prop = _resolve_property_record(sim, property_key)
    if not property_supports_business_reputation(prop):
        cache[property_key] = dict(base)
        return dict(base)

    snapshot = _property_business_reputation_core_snapshot(sim, property_key)
    awareness_count = max(0, int(snapshot.get("awareness_count", 0) or 0))
    weighted_awareness = max(0.0, float(snapshot.get("weighted_awareness", 0.0) or 0.0))
    visibility = _property_business_visibility(prop)
    visible_policy = _player_business_visible_community_signal(prop)
    awareness_strength = _clamp_unit(
        (awareness_count * 0.14)
        + (weighted_awareness * 0.1)
        + visibility
        + (0.08 if max(float(visible_policy.get("positive", 0.0) or 0.0), float(visible_policy.get("negative", 0.0) or 0.0)) > 0.0 else 0.0),
        default=0.0,
    )

    price_good = max(0.0, float(snapshot.get("price_fairness", 0.0) or 0.0))
    price_pain = max(0.0, -float(snapshot.get("price_fairness", 0.0) or 0.0))
    social_lift = _clamp_unit(
        (float(snapshot.get("trust", 0.0) or 0.0) * 0.2)
        + (float(snapshot.get("reliability", 0.0) or 0.0) * 0.2)
        + (float(snapshot.get("loyalty", 0.0) or 0.0) * 0.12)
        + (float(snapshot.get("familiarity", 0.0) or 0.0) * 0.08)
        + (price_good * 0.1)
        - (float(snapshot.get("heat", 0.0) or 0.0) * 0.06)
        - (float(snapshot.get("fear", 0.0) or 0.0) * 0.04),
        default=0.0,
    )
    social_drag = _clamp_unit(
        (float(snapshot.get("heat", 0.0) or 0.0) * 0.16)
        + (float(snapshot.get("fear", 0.0) or 0.0) * 0.1)
        + (float(snapshot.get("resentment", 0.0) or 0.0) * 0.16)
        + (float(snapshot.get("incident_pressure", 0.0) or 0.0) * 0.18)
        + (price_pain * 0.12)
        - (float(snapshot.get("trust", 0.0) or 0.0) * 0.04)
        - (float(snapshot.get("reliability", 0.0) or 0.0) * 0.04),
        default=0.0,
    )
    lift = _clamp_unit((social_lift * max(0.22, awareness_strength)) + float(visible_policy.get("positive", 0.0) or 0.0), default=0.0)
    drag = _clamp_unit((social_drag * max(0.22, awareness_strength)) + float(visible_policy.get("negative", 0.0) or 0.0), default=0.0)

    try:
        chunk_size = int(getattr(sim, "chunk_size", 16) or 16)
    except (TypeError, ValueError):
        chunk_size = 16
    chunk_size = max(12, chunk_size)
    signal_strength = max(lift, drag)
    radius = 0
    if signal_strength >= 0.12:
        radius = max(5, int(round((chunk_size * 0.45) + (chunk_size * signal_strength * 0.9))))

    note = ""
    if lift >= drag + 0.08 and lift >= 0.18:
        note = "lifting the block"
    elif drag >= lift + 0.08 and drag >= 0.18:
        if float(snapshot.get("incident_pressure", 0.0) or 0.0) >= 0.18 or float(snapshot.get("heat", 0.0) or 0.0) >= 0.22 or _text(_property_business_state_metadata(prop).get("customer_policy")).lower() == "closed":
            note = "making the block tense"
        else:
            note = "souring the block"

    result = dict(base)
    result.update({
        "community_signal_lift": round(float(lift), 3),
        "community_signal_drag": round(float(drag), 3),
        "community_signal_radius": int(radius),
        "community_signal_note": note,
    })
    cache[property_key] = dict(result)
    return result


def _property_business_community_ripple(sim, property_id):
    property_key = _text(property_id)
    base = {
        "community_lift": 0.0,
        "community_drag": 0.0,
        "community_note": "",
    }
    if sim is None or not property_key:
        return dict(base)
    cache = _business_reputation_tick_cache(sim, "community_ripple_cache")
    cached = cache.get(property_key)
    if isinstance(cached, dict):
        return dict(cached)

    prop = _resolve_property_record(sim, property_key)
    point = _property_point(prop)
    if not property_supports_business_reputation(prop) or point is None:
        cache[property_key] = dict(base)
        return dict(base)

    lift_total = 0.0
    drag_total = 0.0
    contributors = 0
    for other_id, other_prop in sim.properties.items():
        if _text(other_id) == property_key:
            continue
        if not property_supports_business_reputation(other_prop):
            continue
        other_point = _property_point(other_prop)
        if other_point is None or int(other_point[2]) != int(point[2]):
            continue
        signal = _property_business_community_signal(sim, other_id)
        radius = max(0, int(signal.get("community_signal_radius", 0) or 0))
        if radius <= 0:
            continue
        distance = _manhattan(point[0], point[1], other_point[0], other_point[1])
        if distance > radius:
            continue
        distance_scale = max(0.14, 1.0 - (float(distance) / float(max(1, radius))))
        lift_total += max(0.0, float(signal.get("community_signal_lift", 0.0) or 0.0)) * distance_scale
        drag_total += max(0.0, float(signal.get("community_signal_drag", 0.0) or 0.0)) * distance_scale
        contributors += 1

    community_lift = _clamp_unit(lift_total * 0.5, default=0.0)
    community_drag = _clamp_unit(drag_total * 0.5, default=0.0)
    note = ""
    if contributors > 0:
        if community_lift >= community_drag + 0.06 and community_lift >= 0.08:
            note = "warmer block"
        elif community_drag >= community_lift + 0.08 and community_drag >= 0.1:
            note = "tenser block"

    result = dict(base)
    result.update({
        "community_lift": round(float(community_lift), 3),
        "community_drag": round(float(community_drag), 3),
        "community_note": note,
    })
    cache[property_key] = dict(result)
    return result


def property_business_reputation_snapshot(sim, property_id):
    property_key = _text(property_id)
    base = {
        "property_id": property_key,
        "awareness_count": 0,
        "holder_count": 0,
        "weighted_awareness": 0.0,
        "familiarity": 0.0,
        "trust": 0.0,
        "reliability": 0.0,
        "fear": 0.0,
        "heat": 0.0,
        "price_fairness": 0.0,
        "loyalty": 0.0,
        "resentment": 0.0,
        "incident_pressure": 0.0,
        "community_lift": 0.0,
        "community_drag": 0.0,
        "community_note": "",
        "community_signal_lift": 0.0,
        "community_signal_drag": 0.0,
        "community_signal_radius": 0,
        "community_signal_note": "",
        "patronage_score": 0.0,
        "staple_score": 0.0,
        "trouble_score": 0.0,
        "gouging_score": 0.0,
        "reputation_state": "",
        "reputation_scope_key": "",
        "reputation_scope_label": "",
        "reputation_scope_radius": 0,
        "reputation_scope_score": 0.0,
    }
    if sim is None or not property_key:
        return dict(base)

    cache = _business_reputation_tick_cache(sim, "property_cache")
    cached = cache.get(property_key)
    if isinstance(cached, dict):
        return dict(cached)

    snapshot = dict(base)
    snapshot.update(_property_business_reputation_core_snapshot(sim, property_key))
    snapshot.update(_property_business_community_ripple(sim, property_key))
    snapshot.update(_property_business_community_signal(sim, property_key))

    price_good = max(0.0, float(snapshot.get("price_fairness", 0.0) or 0.0))
    price_pain = max(0.0, -float(snapshot.get("price_fairness", 0.0) or 0.0))
    community_lift = _clamp_unit(snapshot.get("community_lift", 0.0), default=0.0)
    community_drag = _clamp_unit(snapshot.get("community_drag", 0.0), default=0.0)
    patronage_score = (
        (float(snapshot["trust"]) * 0.24)
        + (float(snapshot["reliability"]) * 0.22)
        + (float(snapshot["loyalty"]) * 0.14)
        + (float(snapshot["familiarity"]) * 0.18)
        + (price_good * 0.22)
        + (community_lift * 0.18)
        - (float(snapshot["heat"]) * 0.08)
        - (float(snapshot["fear"]) * 0.08)
        - (community_drag * 0.08)
    )
    staple_score = (
        (
            (float(snapshot["trust"]) * 0.28)
            + (float(snapshot["reliability"]) * 0.24)
            + (float(snapshot["loyalty"]) * 0.16)
            + (float(snapshot["familiarity"]) * 0.15)
            + (price_good * 0.17)
        ) * max(
            0.18,
            1.0
            - (
                (float(snapshot["heat"]) * 0.24)
                + (float(snapshot["fear"]) * 0.16)
                + (float(snapshot["resentment"]) * 0.22)
            ),
        )
    ) + (community_lift * 0.14) - (community_drag * 0.08)
    gouging_score = (
        (price_pain * 0.56)
        + (float(snapshot["resentment"]) * 0.28)
        + (float(snapshot["heat"]) * 0.08)
        + (float(snapshot["incident_pressure"]) * 0.08)
    )
    trouble_score = (
        (float(snapshot["heat"]) * 0.28)
        + (float(snapshot["fear"]) * 0.16)
        + (float(snapshot["resentment"]) * 0.24)
        + (price_pain * 0.2)
        + (float(snapshot["incident_pressure"]) * 0.12)
        + (community_drag * 0.18)
        - (community_lift * 0.04)
    )
    snapshot["patronage_score"] = _clamp_unit(patronage_score, default=0.0)
    snapshot["staple_score"] = _clamp_unit(staple_score, default=0.0)
    snapshot["gouging_score"] = _clamp_unit(gouging_score, default=0.0)
    snapshot["trouble_score"] = _clamp_unit(trouble_score, default=0.0)

    if (
        int(snapshot["awareness_count"]) >= 3
        and float(snapshot["staple_score"]) >= 0.39
        and float(snapshot["patronage_score"]) >= 0.37
        and float(snapshot["trouble_score"]) < 0.42
    ):
        snapshot["reputation_state"] = "staple"
    elif (
        int(snapshot["awareness_count"]) >= 3
        and (
            float(snapshot["trouble_score"]) >= 0.48
            or float(snapshot["gouging_score"]) >= 0.46
        )
    ):
        snapshot["reputation_state"] = "troubled"

    scope = _snapshot_business_scope_profile(sim, _resolve_property_record(sim, property_key), snapshot)
    snapshot["reputation_scope_key"] = str(scope.get("key", "")).strip().lower()
    snapshot["reputation_scope_label"] = str(scope.get("label", "")).strip()
    snapshot["reputation_scope_radius"] = max(0, int(scope.get("radius", 0) or 0))
    snapshot["reputation_scope_score"] = _clamp_unit(scope.get("score", 0.0), default=0.0)

    cache[property_key] = dict(snapshot)
    return snapshot


def property_business_reputation_scope_profile(sim, property_id):
    property_key = _text(property_id)
    if sim is None or not property_key:
        return {"key": "", "label": "", "radius": 0, "score": 0.0}
    prop = _resolve_property_record(sim, property_key)
    if not property_supports_business_reputation(prop):
        return {"key": "", "label": "", "radius": 0, "score": 0.0}
    snapshot = property_business_reputation_snapshot(sim, property_key)
    label = str(snapshot.get("reputation_scope_label", "")).strip()
    if not label:
        return {"key": "", "label": "", "radius": 0, "score": 0.0}
    return {
        "key": str(snapshot.get("reputation_scope_key", "")).strip().lower(),
        "label": label,
        "radius": max(0, int(snapshot.get("reputation_scope_radius", 0) or 0)),
        "score": _clamp_unit(snapshot.get("reputation_scope_score", 0.0), default=0.0),
    }


def property_business_reputation_designations(sim, property_id):
    property_key = _text(property_id)
    if sim is None or not property_key:
        return ()
    prop = _resolve_property_record(sim, property_key)
    if not property_supports_business_reputation(prop):
        return ()

    snapshot = property_business_reputation_snapshot(sim, property_key)
    awareness = max(
        float(snapshot.get("weighted_awareness", 0.0) or 0.0),
        float(int(snapshot.get("awareness_count", 0) or 0)),
    )
    if awareness < 1.12:
        return ()

    metadata = prop.get("metadata", {}) if isinstance(prop.get("metadata", {}), dict) else {}
    archetype = _text(metadata.get("archetype")).lower()
    trust = _clamp_unit(snapshot.get("trust", 0.0), default=0.0)
    reliability = _clamp_unit(snapshot.get("reliability", 0.0), default=0.0)
    fear = _clamp_unit(snapshot.get("fear", 0.0), default=0.0)
    heat = _clamp_unit(snapshot.get("heat", 0.0), default=0.0)
    loyalty = _clamp_unit(snapshot.get("loyalty", 0.0), default=0.0)
    resentment = _clamp_unit(snapshot.get("resentment", 0.0), default=0.0)
    incident_pressure = _clamp_unit(snapshot.get("incident_pressure", 0.0), default=0.0)
    staple_score = _clamp_unit(snapshot.get("staple_score", 0.0), default=0.0)
    trouble_score = _clamp_unit(snapshot.get("trouble_score", 0.0), default=0.0)
    gouging_score = _clamp_unit(snapshot.get("gouging_score", 0.0), default=0.0)
    patronage_score = _clamp_unit(snapshot.get("patronage_score", 0.0), default=0.0)
    try:
        price_fairness = float(snapshot.get("price_fairness", 0.0) or 0.0)
    except (TypeError, ValueError):
        price_fairness = 0.0
    price_fairness = _clamp_signed_unit(price_fairness, default=0.0)

    designations = []

    def _add(key, symbol, label, score):
        designations.append({
            "key": str(key or "").strip().lower(),
            "symbol": str(symbol or "").strip()[:2],
            "label": str(label or "").strip(),
            "score": _clamp_unit(score, default=0.0),
        })

    if awareness >= 1.45 and staple_score >= 0.4 and patronage_score >= 0.36:
        _add("staple", "*", "town staple", max(staple_score, patronage_score))

    if (
        archetype in _SOCIAL_NOTEBOOK_ARCHETYPES
        and trust >= 0.48
        and reliability >= 0.34
        and heat <= 0.22
        and fear <= 0.18
        and trouble_score < 0.28
    ):
        _add("chill", "~", "local chill spot", (trust * 0.42) + (reliability * 0.22) + (loyalty * 0.14) + 0.12)

    if awareness >= 1.36 and reliability >= 0.58 and trust >= 0.46 and incident_pressure <= 0.24:
        _add("quality_plus", "+", "known for quality", (reliability * 0.58) + (trust * 0.22) + max(0.0, price_fairness * 0.12))

    if awareness >= 1.26 and reliability <= 0.28 and (resentment >= 0.2 or incident_pressure >= 0.18):
        _add("quality_minus", "-", "known for rough quality", max(resentment, 1.0 - reliability, incident_pressure))

    if awareness >= 1.3 and (gouging_score >= 0.42 or (price_fairness <= -0.34 and trust <= 0.42)):
        _add("gouging", "$", "price-fixing / swindler talk", max(gouging_score, max(0.0, -price_fairness)))

    if awareness >= 1.22 and (
        trouble_score >= 0.42
        or heat >= 0.48
        or fear >= 0.42
        or (heat >= 0.24 and resentment >= 0.34)
    ):
        _add("troubled", "!", "troubled or street-hot", max(trouble_score, heat, fear))

    priority = {
        "troubled": 0,
        "gouging": 1,
        "staple": 2,
        "quality_plus": 3,
        "quality_minus": 4,
        "chill": 5,
    }
    designations.sort(
        key=lambda row: (
            int(priority.get(str(row.get("key", "")).strip().lower(), 99)),
            -float(row.get("score", 0.0) or 0.0),
            str(row.get("label", "")),
        )
    )
    return tuple(designations[:4])


class BusinessReputationSystem(System):

    MIN_SOCIAL_QUEUE_SCORE = 0.18
    SHARE_COOLDOWN_TICKS = 90
    MAX_PROPAGATION_DEPTH = 3
    MIN_SHARE_COHERENCE = 0.2

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("knowledge_incident_learned", self.on_knowledge_incident_learned)
        self.sim.events.subscribe("trade_bought", self.on_trade_bought)
        self.sim.events.subscribe("trade_sold", self.on_trade_sold)
        self.sim.events.subscribe("site_service_used", self.on_site_service_used)
        self.sim.events.subscribe("npc_social_venue_visited", self.on_npc_social_venue_visited)
        if not hasattr(self.sim, "business_reputation_stats"):
            self.sim.business_reputation_stats = {
                "holders": 0,
                "shares_last_tick": 0,
            }

    def _knowledge_for(self, eid, *, create=False):
        return business_knowledge_for(self.sim, eid, create=create)

    def _actor_traits(self, eid):
        return self.sim.ecs.get(NPCTraits).get(eid) or NPCTraits()

    def _sender_approval_view(self, memory, sender_eid, *, max_age=420):
        if not isinstance(memory, NPCMemory) or sender_eid is None:
            return 0.0
        best = None
        best_score = 0.0
        now = int(getattr(self.sim, "tick", 0) or 0)
        for entry in tuple(getattr(memory, "entries", ()) or ()):
            if entry.get("kind") != "actor_reputation":
                continue
            if now - int(entry.get("tick", 0) or 0) > max_age:
                continue
            data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
            if data.get("actor_eid") != sender_eid:
                continue
            approval = _clamp_signed_unit(data.get("approval", 0.0), default=0.0)
            score = abs(approval) * float(entry.get("strength", 0.0) or 0.0)
            if best is None or score > best_score:
                best = approval
                best_score = score
        return float(best or 0.0)

    def _recipient_sender_credibility(self, to_eid, from_eid, *, socials, memories):
        credibility = 0.42
        target_social = socials.get(to_eid)
        if isinstance(target_social, NPCSocial):
            bond = (target_social.bonds or {}).get(from_eid)
            if isinstance(bond, dict):
                credibility += float(bond.get("trust", 0.0) or 0.0) * 0.28
                credibility += float(bond.get("closeness", 0.0) or 0.0) * 0.16
        target_memory = memories.get(to_eid)
        approval = self._sender_approval_view(target_memory, from_eid)
        credibility += approval * 0.26
        return _clamp_unit(credibility, default=0.0)

    def _property_record_strength(self, record):
        return _business_record_strength(record)

    def _queue_score(self, record):
        if not isinstance(record, dict):
            return 0.0
        return _clamp_unit(
            (self._property_record_strength(record) * 0.7)
            + (float(record.get("coherence", 0.0) or 0.0) * 0.15)
            + (float(record.get("social_interest", 0.0) or 0.0) * 0.25),
            default=0.0,
        )

    def _direct_price_fairness(self, *, price, base_price):
        try:
            price = float(price)
            base_price = float(base_price)
        except (TypeError, ValueError):
            return 0.0
        if base_price <= 0.0:
            return 0.0
        ratio = (base_price - price) / base_price
        return _clamp_signed_unit(ratio, default=0.0)

    def _remember_property_opinion(
        self,
        eid,
        property_id,
        *,
        source_kind="",
        source_eid=None,
        confidence=0.5,
        firsthand=False,
        propagation_depth=0,
        coherence=1.0,
        familiarity_delta=0.0,
        trust_delta=0.0,
        reliability_delta=0.0,
        fear_delta=0.0,
        heat_delta=0.0,
        price_fairness_delta=0.0,
        loyalty_delta=0.0,
        resentment_delta=0.0,
        social_interest=0.0,
        tags=(),
        incident_id=None,
    ):
        prop = _resolve_property_record(self.sim, _text(property_id))
        if not property_supports_business_reputation(prop):
            return None
        knowledge = self._knowledge_for(eid, create=True)
        if not isinstance(knowledge, BusinessKnowledge):
            return None
        record = knowledge.remember(
            property_id,
            learned_tick=getattr(self.sim, "tick", 0),
            source_kind=source_kind,
            source_eid=source_eid,
            confidence=confidence,
            firsthand=firsthand,
            propagation_depth=propagation_depth,
            coherence=coherence,
            familiarity_delta=familiarity_delta,
            trust_delta=trust_delta,
            reliability_delta=reliability_delta,
            fear_delta=fear_delta,
            heat_delta=heat_delta,
            price_fairness_delta=price_fairness_delta,
            loyalty_delta=loyalty_delta,
            resentment_delta=resentment_delta,
            social_interest=social_interest,
            tags=tags,
            incident_id=incident_id,
        )
        if isinstance(record, dict):
            queue_score = self._queue_score(record)
            if queue_score >= self.MIN_SOCIAL_QUEUE_SCORE:
                knowledge.queue_property(property_id, score=queue_score, tick=getattr(self.sim, "tick", 0))
            hydrate_business_social_knowledge(self.sim, eid, source_event="business_knowledge_learned")
            self.sim.emit(Event(
                "business_knowledge_learned",
                eid=eid,
                property_id=_text(property_id),
                source_kind=_text(source_kind).lower(),
                source_eid=source_eid,
                firsthand=bool(firsthand),
                confidence=round(float(record.get("confidence", confidence) or confidence), 3),
                propagation_depth=int(record.get("propagation_depth", 0) or 0),
                coherence=round(float(record.get("coherence", coherence) or coherence), 3),
                queue_score=round(float(queue_score), 3),
            ))
        return record

    def on_trade_bought(self, event):
        if bool(event.data.get("owner_transfer")):
            return
        property_id = _text(event.data.get("property_id"))
        if not property_id:
            return
        fairness = self._direct_price_fairness(
            price=event.data.get("price", 0),
            base_price=event.data.get("base_price", 0),
        )
        tags = []
        if fairness >= 0.12:
            tags.append("fair_deal")
        elif fairness <= -0.16:
            tags.append("overpriced")
        trust_delta = 0.035 if fairness >= -0.08 else -0.02
        resentment_delta = 0.05 if fairness <= -0.18 else 0.0
        loyalty_delta = 0.04 if fairness >= 0.14 else 0.0
        self._remember_property_opinion(
            event.data.get("eid"),
            property_id,
            source_kind="trade_buy",
            confidence=0.72,
            firsthand=True,
            familiarity_delta=0.12,
            trust_delta=trust_delta,
            reliability_delta=0.05,
            price_fairness_delta=fairness * 0.42,
            loyalty_delta=loyalty_delta,
            resentment_delta=resentment_delta,
            social_interest=max(0.1, (abs(fairness) * 0.42) + 0.08),
            tags=tags,
        )

    def on_trade_sold(self, event):
        if bool(event.data.get("owner_transfer")):
            return
        property_id = _text(event.data.get("property_id"))
        if not property_id:
            return
        fairness = self._direct_price_fairness(
            price=event.data.get("price", 0),
            base_price=event.data.get("base_price", 0),
        )
        tags = []
        if fairness >= 0.12:
            tags.append("pays_fair")
        elif fairness <= -0.16:
            tags.append("pays_poorly")
        trust_delta = 0.03 if fairness >= -0.08 else -0.02
        resentment_delta = 0.05 if fairness <= -0.18 else 0.0
        loyalty_delta = 0.035 if fairness >= 0.14 else 0.0
        self._remember_property_opinion(
            event.data.get("eid"),
            property_id,
            source_kind="trade_sell",
            confidence=0.72,
            firsthand=True,
            familiarity_delta=0.12,
            trust_delta=trust_delta,
            reliability_delta=0.04,
            price_fairness_delta=fairness * 0.42,
            loyalty_delta=loyalty_delta,
            resentment_delta=resentment_delta,
            social_interest=max(0.1, (abs(fairness) * 0.42) + 0.08),
            tags=tags,
        )

    def on_site_service_used(self, event):
        property_id = _text(event.data.get("property_id"))
        if not property_id:
            return
        service = _text(event.data.get("service")).lower()
        loyalty_delta = 0.06 if service in {"shelter", "rest", "medical_aid", "repair"} else 0.03
        self._remember_property_opinion(
            event.data.get("eid"),
            property_id,
            source_kind="site_service",
            confidence=0.76,
            firsthand=True,
            familiarity_delta=0.14,
            trust_delta=0.05,
            reliability_delta=0.08,
            loyalty_delta=loyalty_delta,
            social_interest=0.12,
            tags=("reliable",) if service else (),
        )

    def on_npc_social_venue_visited(self, event):
        property_id = _text(event.data.get("property_id"))
        if not property_id:
            return
        prop = _resolve_property_record(self.sim, property_id)
        if not property_supports_business_reputation(prop):
            return
        gate = social_secret_site_trust_gate(prop)
        tags = []
        if gate > 0.0:
            tags.extend(("quiet_spot", "shared_room"))
            remember_hidden_social_site_for_actor(
                self.sim,
                event.data.get("npc_eid"),
                property_id,
                source_eid=event.data.get("source_eid"),
                confidence=max(0.52, 0.44 + (gate * 0.22)),
            )
        self._remember_property_opinion(
            event.data.get("npc_eid"),
            property_id,
            source_kind="social_visit",
            source_eid=event.data.get("source_eid"),
            confidence=0.74 if gate > 0.0 else 0.68,
            firsthand=True,
            familiarity_delta=0.18 if gate > 0.0 else 0.14,
            trust_delta=0.06 if gate > 0.0 else 0.04,
            reliability_delta=0.05 if gate > 0.0 else 0.03,
            loyalty_delta=0.06 if gate > 0.0 else 0.04,
            social_interest=0.22 if gate > 0.0 else 0.14,
            tags=tuple(tags),
        )

    def on_knowledge_incident_learned(self, event):
        eid = event.data.get("eid")
        incident = incident_record(self.sim, event.data.get("incident_id"))
        if not isinstance(incident, dict):
            return
        property_id = _text(incident.get("property_id"))
        if not property_id:
            return
        prop = _resolve_property_record(self.sim, property_id)
        if not property_supports_business_reputation(prop):
            return

        severity = max(0.0, min(1.0, float(int(incident.get("severity", 0) or 0)) / 100.0))
        confidence = _clamp_unit(event.data.get("confidence", 0.5), default=0.5)
        firsthand = bool(event.data.get("firsthand", False))
        source_kind = _text(event.data.get("source_kind")).lower()
        propagation_depth = max(0, int(event.data.get("propagation_depth", 0) or 0))
        coherence = _clamp_unit((0.94 if firsthand else 0.8 if source_kind == "camera" else 0.7) * confidence, default=0.0)
        traits = self._actor_traits(eid)
        empathy = _clamp_unit(getattr(traits, "empathy", 0.5), default=0.5)
        discipline = _clamp_unit(getattr(traits, "discipline", 0.5), default=0.5)
        weight = max(0.2, confidence * (1.0 if firsthand else 0.78) * max(0.36, 1.0 - (propagation_depth * 0.18)))

        fear_delta = 0.0
        heat_delta = 0.0
        trust_delta = 0.0
        reliability_delta = 0.0
        loyalty_delta = 0.0
        resentment_delta = 0.0
        social_interest = 0.0
        tags = []

        kind = _text(incident.get("kind")).lower()
        if kind == "action_offense":
            fear_delta = (0.08 + (0.44 * severity)) * weight
            heat_delta = (0.1 + (0.5 * severity)) * weight
            trust_delta = -(0.05 + (0.24 * severity * (0.68 + (discipline * 0.24)))) * weight
            reliability_delta = -(0.04 + (0.18 * severity)) * weight
            resentment_delta = (0.04 + (0.18 * severity * (0.7 + (empathy * 0.3)))) * weight
            social_interest = 0.18 + (0.42 * severity * weight)
            tags.extend(("dangerous", "hot"))
        elif kind in {"property_tamper", "item_stolen"}:
            heat_delta = (0.06 + (0.26 * severity)) * weight
            reliability_delta = -(0.04 + (0.16 * severity)) * weight
            trust_delta = -(0.03 + (0.1 * severity)) * weight
            resentment_delta = (0.03 + (0.12 * severity)) * weight
            social_interest = 0.14 + (0.28 * severity * weight)
            tags.append("unsafe")
        elif kind in {"property_trespass", "camera_alert"}:
            heat_delta = (0.04 + (0.18 * severity)) * weight
            fear_delta = (0.02 + (0.1 * severity)) * weight
            reliability_delta = -(0.02 + (0.08 * severity)) * weight
            social_interest = 0.1 + (0.2 * severity * weight)
            tags.append("watched")
        else:
            heat_delta = 0.04 * weight
            social_interest = 0.08 + (0.14 * severity * weight)

        self._remember_property_opinion(
            eid,
            property_id,
            source_kind=f"incident_{kind or 'report'}",
            source_eid=event.data.get("source_eid"),
            confidence=confidence,
            firsthand=firsthand,
            propagation_depth=propagation_depth,
            coherence=coherence,
            familiarity_delta=0.04 + (0.08 * weight),
            trust_delta=trust_delta,
            reliability_delta=reliability_delta,
            fear_delta=fear_delta,
            heat_delta=heat_delta,
            loyalty_delta=loyalty_delta,
            resentment_delta=resentment_delta,
            social_interest=social_interest,
            tags=tags,
            incident_id=event.data.get("incident_id"),
        )

    def _best_shareable_record(self, knowledge):
        if not isinstance(knowledge, BusinessKnowledge):
            return None
        records = knowledge.records or {}
        for entry in tuple(getattr(knowledge, "social_queue", ()) or ()):
            property_id = _text(entry.get("property_id"))
            record = records.get(property_id)
            if not isinstance(record, dict):
                continue
            if int(record.get("propagation_depth", 0) or 0) >= self.MAX_PROPAGATION_DEPTH:
                continue
            if float(record.get("coherence", 0.0) or 0.0) < self.MIN_SHARE_COHERENCE:
                continue
            return record
        return None

    def _spread_deltas(self, record, *, share_scale):
        scale = _clamp_unit(share_scale, default=0.0)
        return {
            "familiarity_delta": 0.05 * scale,
            "trust_delta": float(record.get("trust", 0.0) or 0.0) * 0.18 * scale,
            "reliability_delta": float(record.get("reliability", 0.0) or 0.0) * 0.16 * scale,
            "fear_delta": float(record.get("fear", 0.0) or 0.0) * 0.18 * scale,
            "heat_delta": float(record.get("heat", 0.0) or 0.0) * 0.2 * scale,
            "price_fairness_delta": float(record.get("price_fairness", 0.0) or 0.0) * 0.24 * scale,
            "loyalty_delta": float(record.get("loyalty", 0.0) or 0.0) * 0.14 * scale,
            "resentment_delta": float(record.get("resentment", 0.0) or 0.0) * 0.16 * scale,
        }

    def _social_share_pass(self):
        shares = 0
        knowledges = self.sim.ecs.get(BusinessKnowledge)
        socials = self.sim.ecs.get(NPCSocial)
        memories = self.sim.ecs.get(NPCMemory)
        positions = self.sim.ecs.get(Position)
        now = int(getattr(self.sim, "tick", 0) or 0)

        for from_eid, social in socials.items():
            source_knowledge = knowledges.get(from_eid)
            source_pos = positions.get(from_eid)
            if not isinstance(source_knowledge, BusinessKnowledge) or not source_pos:
                continue
            if not _detail_tick_allowed(self.sim, source_pos, from_eid, coarse_divisor=4):
                continue
            if (now + int(from_eid)) % 5 != 0:
                continue

            record = self._best_shareable_record(source_knowledge)
            if not isinstance(record, dict):
                continue
            property_id = _text(record.get("property_id"))
            if not property_id:
                continue
            ranked_bonds = sorted(
                (social.bonds or {}).items(),
                key=lambda row: (float(row[1].get("trust", 0.0) or 0.0) * 0.65) + (float(row[1].get("closeness", 0.0) or 0.0) * 0.35),
                reverse=True,
            )
            for to_eid, bond in ranked_bonds:
                if float(bond.get("trust", 0.0) or 0.0) < 0.48 or float(bond.get("closeness", 0.0) or 0.0) < 0.34:
                    continue
                target_pos = positions.get(to_eid)
                if not target_pos or target_pos.z != source_pos.z:
                    continue
                if _manhattan(source_pos.x, source_pos.y, target_pos.x, target_pos.y) > 6:
                    continue
                prop = _resolve_property_record(self.sim, property_id)
                prop_point = _property_point(prop)
                if prop_point is None:
                    continue
                scope = business_record_reputation_scope_profile(self.sim, property_id, record)
                if int(scope.get("radius", 0) or 0) <= 0:
                    continue
                target_distance = _manhattan(prop_point[0], prop_point[1], target_pos.x, target_pos.y)
                credibility = self._recipient_sender_credibility(to_eid, from_eid, socials=socials, memories=memories)
                if credibility < 0.18:
                    continue
                last_tick = source_knowledge.last_shared.get(property_id, {}) if isinstance(source_knowledge.last_shared.get(property_id), dict) else {}
                if now - int(last_tick.get("social", -10_000) or -10_000) < self.SHARE_COOLDOWN_TICKS:
                    continue

                target_knowledge = self._knowledge_for(to_eid, create=True)
                existing = (target_knowledge.records or {}).get(property_id) if isinstance(target_knowledge, BusinessKnowledge) else None
                existing_strength = self._property_record_strength(existing) if isinstance(existing, dict) else 0.0
                source_strength = self._property_record_strength(record)
                shared_coherence = _clamp_unit(
                    float(record.get("coherence", 0.0) or 0.0)
                    * (0.72 + (float(bond.get("trust", 0.0) or 0.0) * 0.12))
                    * (0.72 + (credibility * 0.22)),
                    default=0.0,
                )
                if shared_coherence < self.MIN_SHARE_COHERENCE:
                    continue
                shared_depth = max(0, int(record.get("propagation_depth", 0) or 0)) + 1
                if shared_depth > self.MAX_PROPAGATION_DEPTH:
                    continue
                shared_strength = _clamp_unit(
                    source_strength
                    * (0.4 + (float(bond.get("trust", 0.0) or 0.0) * 0.24))
                    * (0.68 + (credibility * 0.44)),
                    default=0.0,
                )
                if existing_strength >= shared_strength - 0.025:
                    continue
                if target_distance > int(scope.get("radius", 0) or 0):
                    continue
                deltas = self._spread_deltas(record, share_scale=shared_strength)
                learned = self._remember_property_opinion(
                    to_eid,
                    property_id,
                    source_kind="social_rumor",
                    source_eid=from_eid,
                    confidence=max(0.18, min(0.88, float(record.get("confidence", 0.0) or 0.0) * (0.72 + (credibility * 0.16)))),
                    firsthand=False,
                    propagation_depth=shared_depth,
                    coherence=shared_coherence,
                    social_interest=max(0.08, min(0.75, shared_strength)),
                    tags=tuple(record.get("tags", ()) or ()),
                    incident_id=(tuple(record.get("incident_ids", ()) or ()) or (None,))[0],
                    **deltas,
                )
                if not isinstance(learned, dict):
                    continue
                secret_gate = social_secret_site_trust_gate(prop)
                source_property_knowledge = self.sim.ecs.get(PropertyKnowledge).get(from_eid)
                source_lead_entry = source_property_knowledge.property_entry(property_id) if isinstance(source_property_knowledge, PropertyKnowledge) else None
                source_lead_kind = _text((source_lead_entry or {}).get("lead_kind")).lower()
                source_hidden_lead = bool(source_property_knowledge.is_hidden(property_id)) if isinstance(source_property_knowledge, PropertyKnowledge) else False
                source_lead_confidence = _clamp_unit((source_lead_entry or {}).get("confidence", 0.0), default=0.0)
                lead_share_strength = _clamp_unit(
                    (credibility * 0.32)
                    + (float(bond.get("trust", 0.0) or 0.0) * 0.28)
                    + (float(bond.get("closeness", 0.0) or 0.0) * 0.12)
                    + (source_lead_confidence * 0.16)
                    + (_clamp_unit(record.get("familiarity", 0.0), default=0.0) * 0.08)
                    + (_clamp_unit(record.get("trust", 0.0), default=0.0) * 0.08),
                    default=0.0,
                )
                if (
                    secret_gate > 0.0
                    and (source_hidden_lead or source_lead_kind == "social" or source_lead_confidence >= max(0.44, secret_gate * 0.62))
                    and lead_share_strength >= max(0.54, secret_gate * 0.74)
                    and shared_coherence >= max(self.MIN_SHARE_COHERENCE, secret_gate * 0.66)
                ):
                    if remember_hidden_social_site_for_actor(
                        self.sim,
                        to_eid,
                        property_id,
                        source_eid=from_eid,
                        confidence=max(0.52, min(0.9, lead_share_strength * 0.94)),
                    ):
                        self.sim.emit(Event(
                            "business_secret_site_shared",
                            property_id=property_id,
                            from_eid=from_eid,
                            to_eid=to_eid,
                            confidence=round(max(0.52, min(0.9, lead_share_strength * 0.94)), 3),
                        ))
                source_knowledge.mark_shared(property_id, tick=now, channel="social")
                target_knowledge.mark_shared(property_id, tick=now, channel="social")
                hydrate_business_social_knowledge(self.sim, from_eid, source_event="business_reputation_shared")
                hydrate_business_social_knowledge(self.sim, to_eid, source_event="business_reputation_shared")
                shares += 1
                self.sim.emit(Event(
                    "business_reputation_shared",
                    property_id=property_id,
                    from_eid=from_eid,
                    to_eid=to_eid,
                    coherence=round(shared_coherence, 3),
                    propagation_depth=int(shared_depth),
                    strength=round(shared_strength, 3),
                ))
                break
        return shares

    def update(self):
        shares = self._social_share_pass()
        self.sim.business_reputation_stats["holders"] = len(self.sim.ecs.get(BusinessKnowledge))
        self.sim.business_reputation_stats["shares_last_tick"] = int(shares)


__all__ = [
    "BusinessReputationSystem",
    "business_knowledge_for",
    "business_opinion_profile",
    "business_record_reputation_scope_profile",
    "property_business_reputation_scope_profile",
    "property_business_reputation_snapshot",
    "property_supports_business_reputation",
]
