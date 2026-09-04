"""Cached per-chunk service supply and smoothed unmet-demand reads.

Genesis records the mostly static supply side once as properties are
materialized.  Runtime service changes update the same property contribution
in place.  Unmet lookups retain a short hourly audit trail while exposing an
exponential moving average for economic, travel, and settlement decisions.
None of the public reads scan actors or properties.
"""

from __future__ import annotations

import math
import random


LOCAL_SERVICE_DEMAND_MAX_BUCKETS = 24
LOCAL_SERVICE_DEMAND_EMA_ALPHA = 0.25
LOCAL_SERVICE_UNMET_PRESSURE_WEIGHT = 1.0
LOCAL_SERVICE_SUPPLY_PRESSURE_FLOOR = 1
LOCAL_SERVICE_DEMAND_INTENSITY_CAP = 2.0
LOCAL_SERVICE_DISSATISFACTION_RELIABILITY = 0.82
LOCAL_SERVICE_DISSATISFACTION_WEIGHT = 1.25
LOCAL_SERVICE_PLAYER_INQUIRY_KNOWN_INTENSITY = 0.05
LOCAL_SERVICE_PLAYER_INQUIRY_GAP_INTENSITY = 0.10
LOCAL_SERVICE_SUPPLY_SCHEMA = 2

NEIGHBORHOOD_MARKET_TUNING = {
    "revealed_demand_weight": 1.25,
    "unmet_check_weight": 1.75,
    "unmet_amount_weight": 0.25,
    "avoidance_weight": 0.35,
    "fresh_survey_days": 1.0,
    "baseline_blend_days": 7.0,
    "default_provider_capacity": 1.0,
    "default_provider_attractiveness": 1.0,
}


def _service_registry():
    # service_category_registry imports runtime constants whose population
    # dependency also imports this module during startup.
    from game import service_category_registry
    return service_category_registry

# Playtest-facing taste knobs.  These deliberately live together: genesis
# supplies an initial cultural profile, while later actor-will samples use the
# same 0..INTENSITY_CAP scale and the EMA above decides how quickly culture
# responds to lived behavior.
LOCAL_SERVICE_GENESIS_TASTE = {
    "provisions_base": 0.28,
    "provisions_behavior": 0.42,
    "provisions_need_divisor": 50.0,
    "social_base": 0.18,
    "social_behavior": 0.48,
    "social_need_divisor": 55.0,
    "quirk_base": 0.68,
    "quirk_behavior": 0.32,
    "work_gear_base": 0.34,
    "work_gear_behavior": 0.50,
    "poker_min_affinity": 0.50,
    "poker_base": 0.22,
    "poker_affinity": 0.62,
}


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _ticks_per_hour(sim):
    traits = getattr(sim, "world_traits", {})
    clock = traits.get("clock", {}) if isinstance(traits, dict) else {}
    return max(60, _int((clock or {}).get("ticks_per_hour", 600), 600))


def _state(sim, *, create=True):
    state = getattr(sim, "local_service_demand", None)
    if not isinstance(state, dict):
        if not create:
            return {}
        state = {}
        sim.local_service_demand = state
    return state


def _supply_state(sim, *, create=True):
    state = getattr(sim, "local_service_supply", None)
    if not isinstance(state, dict):
        if not create:
            return {}
        state = {
            "schema": LOCAL_SERVICE_SUPPLY_SCHEMA,
            "chunks": {},
            "category_chunks": {},
            "properties": {},
            "initialized_chunks": {},
            "coverage_misses": {},
            "revision": 0,
        }
        sim.local_service_supply = state
    prior_schema = _int(state.get("schema"), 1)
    if prior_schema < LOCAL_SERVICE_SUPPLY_SCHEMA:
        # Property restore/materialization already visits the relevant records;
        # make that pass rebuild category membership instead of scanning here.
        state["schema"] = LOCAL_SERVICE_SUPPLY_SCHEMA
        state["category_chunks"] = {}
        state["coverage_misses"] = {}
        state["initialized_chunks"] = {}
    state.setdefault("chunks", {})
    state.setdefault("category_chunks", {})
    state.setdefault("properties", {})
    state.setdefault("initialized_chunks", {})
    state.setdefault("coverage_misses", {})
    state.setdefault("revision", 0)
    return state


def _chunk_key(sim, prop, fallback=None):
    metadata = prop.get("metadata") if isinstance(prop, dict) else None
    configured = metadata.get("chunk") if isinstance(metadata, dict) else None
    for candidate in (configured, fallback):
        try:
            return (int(candidate[0]), int(candidate[1]))
        except (TypeError, ValueError, IndexError):
            pass
    try:
        return tuple(int(value) for value in sim.chunk_coords(int(prop["x"]), int(prop["y"]))[:2])
    except (TypeError, ValueError, KeyError, AttributeError):
        return None


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _property_market_profile(sim, prop, topic_id, *, capacity=None, attractiveness=None):
    metadata = prop.get("metadata") if isinstance(prop, dict) and isinstance(prop.get("metadata"), dict) else {}
    runtime = metadata.get("business_economy")
    if not isinstance(runtime, dict):
        runtime = metadata.get("player_business")
    runtime = runtime if isinstance(runtime, dict) else {}
    summary = runtime.get("last_summary") if isinstance(runtime.get("last_summary"), dict) else {}
    reliability = max(0.0, min(1.0, _float(
        summary.get("service_reliability", runtime.get("service_reliability", 1.0)),
        1.0,
    )))
    policy = str(runtime.get("customer_policy", summary.get("customer_policy", "public")) or "public").strip().lower()
    availability = 1.0
    if bool(metadata.get("economic_closed")) or policy == "closed":
        availability = 0.0
    elif policy == "staff_only":
        availability = 0.25
    definition = _service_registry().service_category_definition(topic_id)
    from game.property_access import property_open_window
    opening = property_open_window(sim, prop)
    opening = tuple(int(value) for value in opening[:2]) if isinstance(opening, (tuple, list)) and len(opening) >= 2 else None
    markup = str(runtime.get("markup_mode", summary.get("markup_mode", "standard")) or "standard").strip().lower()
    price_factor = {"bargain": 1.08, "standard": 1.0, "premium": 0.86}.get(markup, 1.0)
    reputation_factor = max(0.55, min(1.35, _float(summary.get("reputation_revenue_mult"), 1.0)))
    scene_factor = max(0.65, min(1.25, _float(summary.get("scene_revenue_mult"), 1.0)))
    health_factor = max(0.55, min(1.25, _float(summary.get("health"), 1.0)))
    frontage = max(0.45, min(1.1, _float(metadata.get("frontage_condition"), 1.0)))
    safety = max(0.55, min(1.15, _float(metadata.get("customer_safety"), 1.0)))
    base_capacity = _float(definition.get("base_capacity"), NEIGHBORHOOD_MARKET_TUNING["default_provider_capacity"])
    effective_capacity = (
        _float(capacity)
        if capacity is not None
        else base_capacity * availability * (0.35 + (0.65 * reliability))
    )
    provider_attractiveness = (
        _float(attractiveness)
        if attractiveness is not None
        else availability
        * (0.45 + (0.55 * reliability))
        * price_factor
        * reputation_factor
        * scene_factor
        * health_factor
        * frontage
        * safety
    )
    return {
        "capacity": round(max(0.0, effective_capacity), 4),
        "attractiveness": round(max(0.0, provider_attractiveness), 4),
        "reliability": round(reliability, 4),
        "available": bool(availability > 0.0),
        "opening_window": opening,
        "attractiveness_components": {
            "reliability": round(reliability, 4),
            "policy": round(availability, 4),
            "price": round(price_factor, 4),
            "reputation": round(reputation_factor, 4),
            "incident_scene": round(scene_factor, 4),
            "health": round(health_factor, 4),
            "frontage": round(frontage, 4),
            "safety": round(safety, 4),
        },
    }


def _provider_open_now(sim, provider):
    if not bool(provider.get("available")):
        return False
    opening = provider.get("opening_window")
    if not isinstance(opening, (tuple, list)) or len(opening) < 2:
        return True
    start, end = _int(opening[0], 0) % 24, _int(opening[1], 0) % 24
    traits = getattr(sim, "world_traits", {})
    clock = traits.get("clock", {}) if isinstance(traits, dict) else {}
    hour = (_int((clock or {}).get("start_hour"), 9) + (_int(getattr(sim, "tick", 0), 0) // _ticks_per_hour(sim))) % 24
    if start == end:
        return True
    return start <= hour < end if start < end else (hour >= start or hour < end)


def _recompute_category_totals(row):
    providers = row.get("providers") if isinstance(row, dict) and isinstance(row.get("providers"), dict) else {}
    row["nominal_sites"] = len(providers)
    row["effective_supply"] = round(sum(
        max(0.0, _float(provider.get("capacity")))
        for provider in providers.values()
        if isinstance(provider, dict)
    ), 4)
    row["aggregate_attractiveness"] = round(sum(
        max(0.0, _float(provider.get("attractiveness")))
        for provider in providers.values()
        if isinstance(provider, dict)
    ), 4)
    return row


def _remove_supply_contribution(state, property_id):
    old = state.get("properties", {}).pop(str(property_id), None)
    if not isinstance(old, dict):
        return False
    try:
        chunk = (int(old["chunk"][0]), int(old["chunk"][1]))
    except (TypeError, ValueError, KeyError, IndexError):
        return False
    chunk_counts = state.get("chunks", {}).get(chunk)
    if isinstance(chunk_counts, dict):
        for service in tuple(old.get("services", ()) or ()):
            service = str(service or "").strip().lower()
            remaining = max(0, _int(chunk_counts.get(service), 0) - 1)
            if remaining:
                chunk_counts[service] = remaining
            else:
                chunk_counts.pop(service, None)
        if not chunk_counts:
            state.get("chunks", {}).pop(chunk, None)

    category_rows = state.get("category_chunks", {}).get(chunk)
    if isinstance(category_rows, dict):
        for topic_id in tuple(old.get("categories", ()) or ()):
            row = category_rows.get(str(topic_id))
            if not isinstance(row, dict):
                continue
            providers = row.get("providers")
            if isinstance(providers, dict):
                providers.pop(str(property_id), None)
            _recompute_category_totals(row)
            if not row.get("providers"):
                category_rows.pop(str(topic_id), None)
        if not category_rows:
            state.get("category_chunks", {}).pop(chunk, None)
    state.get("coverage_misses", {}).pop(str(property_id), None)
    state["revision"] = _int(state.get("revision"), 0) + 1
    return True


def record_local_service_supply(
    sim,
    prop,
    *,
    chunk=None,
    effective_capacity=None,
    attractiveness=None,
    category_overrides=None,
):
    """Replace one property's exact and category supply without a scan."""

    if sim is None or not isinstance(prop, dict):
        return None
    property_id = str(prop.get("id", "") or "").strip()
    if not property_id:
        return None
    state = _supply_state(sim)
    _remove_supply_contribution(state, property_id)

    from game.property_runtime import property_services, property_supports_business_relevance

    services = {
        str(service or "").strip().lower()
        for service in tuple(property_services(prop) or ())
        if str(service or "").strip()
    }
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    archetype = str(metadata.get("archetype", "") or "").strip().lower()
    if archetype and property_supports_business_relevance(prop, include_assets=True):
        services.add(f"business:{archetype}")
    services = tuple(sorted(services))
    categories = _service_registry().service_categories_for_property(prop)
    property_chunk = _chunk_key(sim, prop, fallback=chunk)
    from game.neighborhood_housing import record_housing_property
    record_housing_property(sim, prop, chunk=property_chunk)
    if property_chunk is None or (not services and not categories):
        return {
            "property_id": property_id,
            "chunk": property_chunk,
            "services": (),
            "categories": (),
        }
    if services:
        chunk_counts = state["chunks"].setdefault(property_chunk, {})
        for service in services:
            chunk_counts[service] = max(0, _int(chunk_counts.get(service), 0)) + 1

    overrides = category_overrides if isinstance(category_overrides, dict) else {}
    category_rows = state["category_chunks"].setdefault(property_chunk, {})
    for topic_id in categories:
        override = overrides.get(topic_id) if isinstance(overrides.get(topic_id), dict) else {}
        profile = _property_market_profile(
            sim,
            prop,
            topic_id,
            capacity=override.get("capacity", effective_capacity),
            attractiveness=override.get("attractiveness", attractiveness),
        )
        row = category_rows.setdefault(topic_id, {"providers": {}})
        providers = row.setdefault("providers", {})
        providers[property_id] = {
            "property_id": property_id,
            "services": services,
            **profile,
        }
        _recompute_category_totals(row)
    state["properties"][property_id] = {
        "chunk": property_chunk,
        "services": services,
        "categories": categories,
    }
    if property_supports_business_relevance(prop, include_assets=True) and not categories and not bool(metadata.get("economic_service_exempt")):
        state["coverage_misses"][property_id] = {
            "property_id": property_id,
            "chunk": property_chunk,
            "archetype": archetype,
            "services": services,
        }
    else:
        state["coverage_misses"].pop(property_id, None)
    state["revision"] = _int(state.get("revision"), 0) + 1
    from game.neighborhood_businesses import register_neighborhood_business
    register_neighborhood_business(sim, prop)
    return {
        "property_id": property_id,
        "chunk": property_chunk,
        "services": services,
        "categories": categories,
    }


def refresh_property_market_supply(sim, prop, **kwargs):
    """Refresh one provider after hours, staffing, quality, or policy changes."""

    return record_local_service_supply(sim, prop, **kwargs)


def forget_local_service_supply(sim, property_id):
    """Remove one known property contribution after closure or deletion."""

    if sim is None:
        return False
    removed = _remove_supply_contribution(_supply_state(sim, create=False), property_id)
    from game.neighborhood_housing import forget_housing_property
    housing_removed = forget_housing_property(sim, property_id)
    from game.neighborhood_businesses import forget_neighborhood_business
    business_removed = forget_neighborhood_business(sim, property_id)
    return bool(removed or housing_removed or business_removed)


def initialize_local_service_supply_for_records(sim, chunk, records):
    """Index the already-materialized records for one chunk exactly once."""

    try:
        chunk = (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError, IndexError):
        return ()
    state = _supply_state(sim)
    if bool(state["initialized_chunks"].get(chunk)):
        return ()
    indexed = []
    seen = set()
    properties = getattr(sim, "properties", {})
    for record in tuple(records or ()):
        if not isinstance(record, dict):
            continue
        property_id = str(record.get("id", "") or "").strip()
        if not property_id or property_id in seen:
            continue
        seen.add(property_id)
        prop = properties.get(property_id)
        if not isinstance(prop, dict):
            continue
        result = record_local_service_supply(sim, prop, chunk=chunk)
        if isinstance(result, dict) and result.get("services"):
            indexed.append(result)
    state["initialized_chunks"][chunk] = True
    return tuple(indexed)


def local_service_supply_read(sim, chunk, *, radius=0, service=""):
    """Combine exact cached supply totals for a bounded chunk neighborhood."""

    try:
        center = (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError, IndexError):
        return ()
    radius = max(0, _int(radius, 0))
    service = str(service or "").strip().lower()
    totals = {}
    chunks = _supply_state(sim, create=False).get("chunks", {})
    for cy in range(center[1] - radius, center[1] + radius + 1):
        for cx in range(center[0] - radius, center[0] + radius + 1):
            rows = chunks.get((cx, cy), {})
            if not isinstance(rows, dict):
                continue
            for service_id, count in rows.items():
                service_id = str(service_id or "").strip().lower()
                if not service_id or (service and service_id != service):
                    continue
                totals[service_id] = totals.get(service_id, 0) + max(0, _int(count, 0))
    return tuple(
        {"service": service_id, "supply": totals[service_id]}
        for service_id in sorted(totals, key=lambda value: (-totals[value], value))
    )


def local_service_category_supply_read(sim, chunk, *, topic_id=""):
    """Read unique providers and effective capacity for one exact chunk."""

    try:
        chunk = (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError, IndexError):
        return ()
    topic_id = str(topic_id or "").strip().lower()
    rows = _supply_state(sim, create=False).get("category_chunks", {}).get(chunk, {})
    if not isinstance(rows, dict):
        return ()
    result = []
    for category_id in _service_registry().SERVICE_LOCATOR_TOPICS:
        if topic_id and category_id != topic_id:
            continue
        row = rows.get(category_id)
        if not isinstance(row, dict):
            continue
        providers = row.get("providers") if isinstance(row.get("providers"), dict) else {}
        projected_providers = []
        for key in sorted(providers):
            provider = dict(providers[key])
            provider["available_now"] = _provider_open_now(sim, provider)
            provider["effective_capacity_now"] = round(
                max(0.0, _float(provider.get("capacity"))) if provider["available_now"] else 0.0,
                4,
            )
            provider["effective_attractiveness_now"] = round(
                max(0.0, _float(provider.get("attractiveness"))) if provider["available_now"] else 0.0,
                4,
            )
            projected_providers.append(provider)
        result.append({
            "topic_id": category_id,
            "nominal_sites": max(0, _int(row.get("nominal_sites"), len(providers))),
            "effective_supply": round(sum(provider["effective_capacity_now"] for provider in projected_providers), 4),
            "aggregate_attractiveness": round(sum(provider["effective_attractiveness_now"] for provider in projected_providers), 4),
            "provider_ids": tuple(sorted(str(value) for value in providers)),
            "providers": tuple(projected_providers),
        })
    return tuple(result)


def local_service_provider_candidates(sim, chunk, topic_id, *, available_only=True):
    """Return cached provider records for one category in one chunk."""

    rows = local_service_category_supply_read(sim, chunk, topic_id=topic_id)
    if not rows:
        return ()
    providers = []
    for provider in tuple(rows[0].get("providers", ()) or ()):
        if available_only and not bool(provider.get("available_now")):
            continue
        providers.append(dict(provider))
    providers.sort(key=lambda row: (
        -_float(row.get("attractiveness")),
        -_float(row.get("capacity")),
        str(row.get("property_id", "")),
    ))
    return tuple(providers)


def local_service_supply_coverage_read(sim):
    """Return cached provider coverage misses; this never audits the world."""

    misses = _supply_state(sim, create=False).get("coverage_misses", {})
    if not isinstance(misses, dict):
        return ()
    return tuple(dict(misses[key]) for key in sorted(misses))


def local_service_market_cache_stats(sim, chunk=None):
    """Small debug/performance read over cache metadata only."""

    state = _supply_state(sim, create=False)
    row = {}
    if chunk is not None:
        try:
            chunk = (int(chunk[0]), int(chunk[1]))
        except (TypeError, ValueError, IndexError):
            chunk = None
    if chunk is not None:
        row = state.get("category_chunks", {}).get(chunk, {})
    return {
        "schema": _int(state.get("schema"), 0),
        "revision": _int(state.get("revision"), 0),
        "indexed_properties": len(state.get("properties", {}) or {}),
        "initialized_chunks": len(state.get("initialized_chunks", {}) or {}),
        "coverage_misses": len(state.get("coverage_misses", {}) or {}),
        "chunk_categories": len(row or {}),
    }


def _advance_demand_ema(service_row, bucket):
    """Finalize elapsed hourly samples while doing O(1) gap decay."""

    ema = service_row.setdefault("ema", {
        "bucket": bucket,
        "demand": 0.0,
        "checks": 0.0,
        "amount": 0.0,
        "sample_demand": 0.0,
        "sample_checks": 0,
        "sample_amount": 0,
        "initialized": False,
    })
    previous_bucket = _int(ema.get("bucket"), bucket)
    if bucket <= previous_bucket:
        return ema
    sample_checks = max(0, _int(ema.get("sample_checks"), 0))
    sample_amount = max(0, _int(ema.get("sample_amount"), 0))
    sample_demand = max(0.0, float(ema.get("sample_demand", 0.0) or 0.0))
    if bool(ema.get("initialized")):
        alpha = LOCAL_SERVICE_DEMAND_EMA_ALPHA
        ema["demand"] = (alpha * sample_demand) + ((1.0 - alpha) * float(ema.get("demand", 0.0) or 0.0))
        ema["checks"] = (alpha * sample_checks) + ((1.0 - alpha) * float(ema.get("checks", 0.0) or 0.0))
        ema["amount"] = (alpha * sample_amount) + ((1.0 - alpha) * float(ema.get("amount", 0.0) or 0.0))
    else:
        ema["demand"] = float(sample_demand)
        ema["checks"] = float(sample_checks)
        ema["amount"] = float(sample_amount)
        ema["initialized"] = True
    skipped = max(0, bucket - previous_bucket - 1)
    if skipped:
        decay = (1.0 - LOCAL_SERVICE_DEMAND_EMA_ALPHA) ** skipped
        ema["demand"] = float(ema.get("demand", 0.0) or 0.0) * decay
        ema["checks"] = float(ema.get("checks", 0.0) or 0.0) * decay
        ema["amount"] = float(ema.get("amount", 0.0) or 0.0) * decay
    ema["bucket"] = bucket
    ema["sample_demand"] = 0.0
    ema["sample_checks"] = 0
    ema["sample_amount"] = 0
    return ema


def _project_demand_ema(service_row, current_bucket):
    ema = dict(service_row.get("ema", {}) or {})
    if not ema:
        return 0.0, 0.0, 0.0
    _advance_demand_ema({"ema": ema}, current_bucket)
    sample_checks = max(0, _int(ema.get("sample_checks"), 0))
    sample_amount = max(0, _int(ema.get("sample_amount"), 0))
    sample_demand = max(0.0, float(ema.get("sample_demand", 0.0) or 0.0))
    if not bool(ema.get("initialized")):
        return float(sample_demand), float(sample_checks), float(sample_amount)
    alpha = LOCAL_SERVICE_DEMAND_EMA_ALPHA
    return (
        (alpha * sample_demand) + ((1.0 - alpha) * float(ema.get("demand", 0.0) or 0.0)),
        (alpha * sample_checks) + ((1.0 - alpha) * float(ema.get("checks", 0.0) or 0.0)),
        (alpha * sample_amount) + ((1.0 - alpha) * float(ema.get("amount", 0.0) or 0.0)),
    )


def _record_local_service_demand(
    sim,
    *,
    x,
    y,
    service,
    motive="",
    intensity=1.0,
    unmet=False,
    amount=0,
    tick=None,
):
    service = str(service or "").strip().lower()
    if sim is None or not service:
        return None
    try:
        chunk = tuple(int(value) for value in sim.chunk_coords(int(x), int(y))[:2])
    except (TypeError, ValueError, AttributeError):
        return None
    tick = _int(getattr(sim, "tick", 0) if tick is None else tick, 0)
    bucket = tick // _ticks_per_hour(sim)
    chunk_rows = _state(sim).setdefault(chunk, {})
    service_row = chunk_rows.setdefault(service, {"buckets": {}})
    ema = _advance_demand_ema(service_row, bucket)
    buckets = service_row.get("buckets")
    if not isinstance(buckets, dict):
        buckets = {}
        service_row["buckets"] = buckets
    row = buckets.setdefault(bucket, {
        "samples": 0,
        "demand": 0.0,
        "checks": 0,
        "amount": 0,
        "first_tick": tick,
        "last_tick": tick,
        "motives": {},
    })
    intensity = max(0.0, float(intensity or 0.0))
    row["samples"] = max(0, _int(row.get("samples"), 0)) + 1
    row["demand"] = max(0.0, float(row.get("demand", 0.0) or 0.0)) + intensity
    if unmet:
        row["checks"] = max(0, _int(row.get("checks"), 0)) + 1
        row["amount"] = max(0, _int(row.get("amount"), 0)) + max(0, _int(amount, 0))
    row["first_tick"] = min(_int(row.get("first_tick"), tick), tick)
    row["last_tick"] = max(_int(row.get("last_tick"), tick), tick)
    motive = str(motive or "").strip().lower()
    motives = row.get("motives")
    if not isinstance(motives, dict):
        motives = {}
        row["motives"] = motives
    if motive:
        motives[motive] = max(0, _int(motives.get(motive), 0)) + 1
    ema["sample_demand"] = max(0.0, float(ema.get("sample_demand", 0.0) or 0.0)) + intensity
    if unmet:
        ema["sample_checks"] = max(0, _int(ema.get("sample_checks"), 0)) + 1
        ema["sample_amount"] = max(0, _int(ema.get("sample_amount"), 0)) + max(0, _int(amount, 0))

    for old_bucket in sorted(tuple(buckets))[:-LOCAL_SERVICE_DEMAND_MAX_BUCKETS]:
        buckets.pop(old_bucket, None)
    return {
        "chunk": chunk,
        "service": service,
        "bucket": bucket,
        **dict(row),
    }


def record_local_service_demand_sample(sim, *, x, y, service, motive="", intensity=1.0, tick=None):
    """Record one timed answer to 'what service do you want right now?'"""

    return _record_local_service_demand(
        sim,
        x=x,
        y=y,
        service=service,
        motive=motive,
        intensity=intensity,
        tick=tick,
    )


def record_actor_local_service_demand_sample(
    sim,
    *,
    actor_eid,
    x,
    y,
    service,
    motive="",
    intensity=1.0,
    tick=None,
    interval_ticks=None,
):
    """Record at most one timed consumer-will answer per actor and service."""

    if sim is None:
        return None
    tick = _int(getattr(sim, "tick", 0) if tick is None else tick, 0)
    interval_ticks = max(1, _int(interval_ticks, _ticks_per_hour(sim)))
    bucket = tick // interval_ticks
    service = str(service or "").strip().lower()
    try:
        key = (int(actor_eid), service)
    except (TypeError, ValueError):
        return None
    if not service:
        return None
    actor_samples = getattr(sim, "local_service_actor_samples", None)
    if not isinstance(actor_samples, dict):
        actor_samples = {}
        sim.local_service_actor_samples = actor_samples
    if _int(actor_samples.get(key), -1) == bucket:
        return None
    actor_samples[key] = bucket
    return record_local_service_demand_sample(
        sim,
        x=x,
        y=y,
        service=service,
        motive=motive,
        intensity=intensity,
        tick=tick,
    )


def record_player_service_inquiry_demand(
    sim,
    *,
    x,
    y,
    topic_id,
    respondent_knows_nearby,
    tick=None,
):
    """Silently record one small player-authored market signal per local day.

    Asking where to find a service is evidence that somebody wants that
    capability in the current chunk.  It is deliberately much weaker than an
    NPC's embodied failed service attempt, but a respondent with no nearby lead
    makes the local supply gap slightly stronger evidence.
    """

    if sim is None:
        return None
    topic_id = str(topic_id or "").strip().lower()
    if topic_id not in _service_registry().SERVICE_LOCATOR_TOPICS:
        return None
    try:
        chunk = tuple(int(value) for value in sim.chunk_coords(int(x), int(y))[:2])
    except (TypeError, ValueError, AttributeError):
        return None
    tick = _int(getattr(sim, "tick", 0) if tick is None else tick, 0)
    day = tick // (24 * _ticks_per_hour(sim))
    sample_days = getattr(sim, "local_service_player_inquiry_days", None)
    if not isinstance(sample_days, dict):
        sample_days = {}
        sim.local_service_player_inquiry_days = sample_days
    key = (chunk, topic_id)
    if _int(sample_days.get(key), -1) == day:
        return None

    knows_nearby = bool(respondent_knows_nearby)
    intensity = (
        LOCAL_SERVICE_PLAYER_INQUIRY_KNOWN_INTENSITY
        if knows_nearby
        else LOCAL_SERVICE_PLAYER_INQUIRY_GAP_INTENSITY
    )
    result = record_local_service_demand_sample(
        sim,
        x=x,
        y=y,
        service=topic_id,
        motive=(
            "player_service_inquiry_known"
            if knows_nearby
            else "player_service_inquiry_gap"
        ),
        intensity=intensity,
        tick=tick,
    )
    if not isinstance(result, dict):
        return None
    sample_days[key] = day
    return {
        **result,
        "day": day,
        "respondent_knows_nearby": knows_nearby,
        "inquiry_intensity": intensity,
    }


def initialize_local_service_demand_for_actors(sim, actor_eids):
    """Seed one deterministic current consumer will per new neighborhood actor."""

    if sim is None:
        return ()
    from game.components import BehaviorProfile, NPCNeeds, Occupation, Position

    initialized = getattr(sim, "local_service_demand_initialized_actors", None)
    if not isinstance(initialized, dict):
        initialized = {}
        sim.local_service_demand_initialized_actors = initialized
    positions = sim.ecs.get(Position)
    behaviors = sim.ecs.get(BehaviorProfile)
    needs_map = sim.ecs.get(NPCNeeds)
    occupations = sim.ecs.get(Occupation)
    recorded = []
    quirk_businesses = {
        "caffeine": "business:corner_store",
        "hats": "business:headwear_shop",
        "medical_prepper": "business:pharmacy",
        "tokens": "business:gaming_hall",
        "tools": "business:tool_depot",
        "weapons": "business:surplus_store",
    }
    social_businesses = (
        "business:arcade",
        "business:bar",
        "business:music_venue",
        "business:pool_hall",
        "business:restaurant",
    )
    for raw_eid in tuple(actor_eids or ()):
        try:
            eid = int(raw_eid)
        except (TypeError, ValueError):
            continue
        if bool(initialized.get(eid)):
            continue
        pos = positions.get(eid)
        profile = behaviors.get(eid)
        if pos is None or profile is None:
            continue
        initialized[eid] = True
        needs = needs_map.get(eid)
        occupation = occupations.get(eid)
        preferences = getattr(profile, "preferences", {})
        preferences = preferences if isinstance(preferences, dict) else {}
        candidates = []

        provision = float(profile.get("buy_provisions", 0.0))
        if provision > 0.0:
            hunger = float(getattr(needs, "hunger", 82.0) or 82.0) if needs is not None else 82.0
            thirst = float(getattr(needs, "thirst", 86.0) or 86.0) if needs is not None else 86.0
            need_pressure = max(0.0, (78.0 - min(hunger, thirst)) / LOCAL_SERVICE_GENESIS_TASTE["provisions_need_divisor"])
            candidates.append((
                LOCAL_SERVICE_GENESIS_TASTE["provisions_base"]
                + (provision * LOCAL_SERVICE_GENESIS_TASTE["provisions_behavior"])
                + need_pressure,
                "business:corner_store",
                "provisions",
            ))

        social_behavior = float(profile.get("seek_social_contact", 0.0))
        social = float(getattr(needs, "social", 68.0) or 68.0) if needs is not None else 68.0
        if social_behavior > 0.0 or social < 68.0:
            rng = random.Random(f"{getattr(sim, 'seed', 0)}:local-social-taste:{eid}")
            social_service = social_businesses[rng.randrange(len(social_businesses))]
            social_pressure = max(0.0, (72.0 - social) / LOCAL_SERVICE_GENESIS_TASTE["social_need_divisor"])
            candidates.append((
                LOCAL_SERVICE_GENESIS_TASTE["social_base"]
                + (social_behavior * LOCAL_SERVICE_GENESIS_TASTE["social_behavior"])
                + social_pressure,
                social_service,
                "social_life",
            ))

        quirk = str(preferences.get("shopping_quirk_id", "") or "").strip().lower()
        quirk_service = quirk_businesses.get(quirk)
        if quirk_service:
            candidates.append((
                LOCAL_SERVICE_GENESIS_TASTE["quirk_base"]
                + (float(profile.get("buy_quirky_items", 0.0)) * LOCAL_SERVICE_GENESIS_TASTE["quirk_behavior"]),
                quirk_service,
                f"taste:{quirk}",
            ))

        career = str(getattr(occupation, "career", "") or "").strip().lower()
        practical = float(profile.get("buy_practical_gear", 0.0))
        career_service = ""
        if any(token in career for token in ("mechanic", "engineer", "technician", "repair")):
            career_service = "business:tool_depot"
        elif any(token in career for token in ("guard", "security", "patrol", "officer")):
            career_service = "business:surplus_store"
        elif any(token in career for token in ("medic", "doctor", "nurse", "pharmac")):
            career_service = "business:pharmacy"
        if career_service and practical > 0.0:
            candidates.append((
                LOCAL_SERVICE_GENESIS_TASTE["work_gear_base"]
                + (practical * LOCAL_SERVICE_GENESIS_TASTE["work_gear_behavior"]),
                career_service,
                "work_gear",
            ))

        poker_rng = random.Random(f"{getattr(sim, 'seed', 0)}:leisure:holdem_cash:{eid}")
        poker_affinity = poker_rng.uniform(0.18, 0.94)
        if poker_affinity >= LOCAL_SERVICE_GENESIS_TASTE["poker_min_affinity"]:
            candidates.append((
                LOCAL_SERVICE_GENESIS_TASTE["poker_base"]
                + (poker_affinity * LOCAL_SERVICE_GENESIS_TASTE["poker_affinity"]),
                "holdem_cash",
                "leisure_cards",
            ))

        if not candidates:
            continue
        intensity, service, motive = max(candidates, key=lambda row: (row[0], row[1], row[2]))
        result = record_actor_local_service_demand_sample(
            sim,
            actor_eid=eid,
            x=pos.x,
            y=pos.y,
            service=service,
            motive=motive,
            intensity=min(LOCAL_SERVICE_DEMAND_INTENSITY_CAP, max(0.05, intensity)),
            tick=getattr(sim, "tick", 0),
        )
        if isinstance(result, dict):
            baseline = getattr(sim, "local_service_genesis_baseline", None)
            if not isinstance(baseline, dict):
                baseline = {}
                sim.local_service_genesis_baseline = baseline
            chunk = tuple(result.get("chunk", ()) or ())
            if len(chunk) >= 2:
                chunk = (int(chunk[0]), int(chunk[1]))
                chunk_rows = baseline.setdefault(chunk, {})
                for topic_id in _service_registry().service_categories_for_raw_key(service):
                    baseline_row = chunk_rows.setdefault(topic_id, {"mass": 0.0, "samples": 0})
                    baseline_row["mass"] = round(
                        max(0.0, _float(baseline_row.get("mass")))
                        + min(LOCAL_SERVICE_DEMAND_INTENSITY_CAP, max(0.05, intensity)),
                        4,
                    )
                    baseline_row["samples"] = max(0, _int(baseline_row.get("samples"), 0)) + 1
            recorded.append({
                "actor_eid": eid,
                "service": service,
                "motive": motive,
                "intensity": round(float(intensity), 3),
            })
    return tuple(recorded)


def record_unmet_local_service_demand(sim, *, x, y, service, motive="", amount=0, tick=None):
    """Record stronger evidence after a real local service lookup failed."""

    return _record_local_service_demand(
        sim,
        x=x,
        y=y,
        service=service,
        motive=motive,
        intensity=1.0,
        unmet=True,
        amount=amount,
        tick=tick,
    )


def record_local_service_dissatisfaction(
    sim,
    prop,
    *,
    reliability,
    customer_weight=1.0,
    tick=None,
):
    """Feed poor delivered service back into demand for the offered business."""

    if sim is None or not isinstance(prop, dict):
        return None
    try:
        reliability = max(0.0, min(1.0, float(reliability)))
    except (TypeError, ValueError):
        return None
    if reliability >= LOCAL_SERVICE_DISSATISFACTION_RELIABILITY:
        return None
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    archetype = str(metadata.get("archetype", "") or "").strip().lower()
    if archetype:
        service = f"business:{archetype}"
    else:
        from game.property_runtime import property_services

        services = tuple(property_services(prop) or ())
        service = str(services[0] if services else "").strip().lower()
    if not service:
        return None
    gap = (LOCAL_SERVICE_DISSATISFACTION_RELIABILITY - reliability) / LOCAL_SERVICE_DISSATISFACTION_RELIABILITY
    intensity = min(
        LOCAL_SERVICE_DEMAND_INTENSITY_CAP,
        max(0.05, gap * LOCAL_SERVICE_DISSATISFACTION_WEIGHT * max(0.25, float(customer_weight or 0.0))),
    )
    return record_local_service_demand_sample(
        sim,
        x=prop.get("x", 0),
        y=prop.get("y", 0),
        service=service,
        motive="service_dissatisfaction",
        intensity=intensity,
        tick=tick,
    )


def local_service_demand_read(sim, chunk, *, radius=0, service="", hours=24):
    """Return a bounded aggregate suitable for one deliberate area read."""

    try:
        center = (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError, IndexError):
        return ()
    radius = max(0, _int(radius, 0))
    service = str(service or "").strip().lower()
    current_bucket = _int(getattr(sim, "tick", 0), 0) // _ticks_per_hour(sim)
    minimum_bucket = current_bucket - max(1, min(LOCAL_SERVICE_DEMAND_MAX_BUCKETS, _int(hours, 24))) + 1
    totals = {}
    state = _state(sim, create=False)
    for cy in range(center[1] - radius, center[1] + radius + 1):
        for cx in range(center[0] - radius, center[0] + radius + 1):
            chunk_rows = state.get((cx, cy), {})
            if not isinstance(chunk_rows, dict):
                continue
            for service_id, service_row in chunk_rows.items():
                if service and str(service_id) != service:
                    continue
                buckets = service_row.get("buckets", {}) if isinstance(service_row, dict) else {}
                for bucket_id, row in tuple(buckets.items()):
                    if _int(bucket_id, -1) < minimum_bucket or not isinstance(row, dict):
                        continue
                    total = totals.setdefault(str(service_id), {
                        "service": str(service_id),
                        "demand_samples": 0,
                        "demand_total": 0.0,
                        "demand_ema": 0.0,
                        "unmet_checks": 0,
                        "unmet_amount": 0,
                        "unmet_check_ema": 0.0,
                        "unmet_amount_ema": 0.0,
                        "last_tick": 0,
                        "motives": {},
                    })
                    total["demand_samples"] += max(0, _int(row.get("samples"), 0))
                    total["demand_total"] += max(0.0, float(row.get("demand", 0.0) or 0.0))
                    total["unmet_checks"] += max(0, _int(row.get("checks"), 0))
                    total["unmet_amount"] += max(0, _int(row.get("amount"), 0))
                    total["last_tick"] = max(total["last_tick"], _int(row.get("last_tick"), 0))
                    for motive, count in dict(row.get("motives", {}) or {}).items():
                        total["motives"][str(motive)] = total["motives"].get(str(motive), 0) + max(0, _int(count, 0))
                demand_ema, check_ema, amount_ema = _project_demand_ema(service_row, current_bucket)
                total = totals.setdefault(str(service_id), {
                    "service": str(service_id),
                    "demand_samples": 0,
                    "demand_total": 0.0,
                    "demand_ema": 0.0,
                    "unmet_checks": 0,
                    "unmet_amount": 0,
                    "unmet_check_ema": 0.0,
                    "unmet_amount_ema": 0.0,
                    "last_tick": 0,
                    "motives": {},
                })
                total["demand_ema"] += float(demand_ema)
                total["unmet_check_ema"] += float(check_ema)
                total["unmet_amount_ema"] += float(amount_ema)
    return tuple(
        totals[key]
        for key in sorted(
            totals,
            key=lambda value: (-totals[value]["unmet_checks"], -totals[value]["unmet_amount"], value),
        )
    )


def local_service_economic_read(sim, chunk, *, radius=0, service="", hours=24):
    """Return supply and EMA demand from cached rows only."""

    rows = {}
    for supply in local_service_supply_read(sim, chunk, radius=radius, service=service):
        rows[supply["service"]] = {
            "service": supply["service"],
            "supply": int(supply["supply"]),
            "demand_samples": 0,
            "demand_total": 0.0,
            "demand_ema": 0.0,
            "unmet_checks": 0,
            "unmet_amount": 0,
            "unmet_check_ema": 0.0,
            "unmet_amount_ema": 0.0,
            "last_tick": 0,
            "motives": {},
        }
    for demand in local_service_demand_read(sim, chunk, radius=radius, service=service, hours=hours):
        row = rows.setdefault(demand["service"], {
            "service": demand["service"],
            "supply": 0,
        })
        row.update(demand)
        row.setdefault("supply", 0)
    for row in rows.values():
        row["opportunity_pressure"] = round(
            (
                float(row.get("demand_ema", 0.0) or 0.0)
                + (
                    float(row.get("unmet_check_ema", 0.0) or 0.0)
                    * LOCAL_SERVICE_UNMET_PRESSURE_WEIGHT
                )
            )
            / float(max(LOCAL_SERVICE_SUPPLY_PRESSURE_FLOOR, _int(row.get("supply"), 0))),
            4,
        )
    return tuple(
        rows[key]
        for key in sorted(
            rows,
            key=lambda value: (-rows[value]["opportunity_pressure"], -float(rows[value].get("unmet_amount_ema", 0.0) or 0.0), value),
        )
    )


def neighborhood_service_market_read(sim, chunk, *, topic_id=""):
    """Return the authoritative cached market for one strict chunk boundary."""

    try:
        chunk = (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError, IndexError):
        return ()
    registry = _service_registry()
    topic_id = str(topic_id or "").strip().lower()
    if topic_id and topic_id not in registry.SERVICE_LOCATOR_TOPICS:
        return ()

    exact_rows = local_service_economic_read(sim, chunk, radius=0, hours=24)
    lived = {
        category_id: {
            "revealed_demand": 0.0,
            "unmet_checks": 0.0,
            "unmet_amount": 0.0,
            "last_tick": 0,
            "exact_keys": [],
        }
        for category_id in registry.SERVICE_LOCATOR_TOPICS
    }
    for exact in exact_rows:
        raw_key = str(exact.get("service", "") or "").strip().lower()
        for category_id in registry.service_categories_for_raw_key(raw_key):
            row = lived[category_id]
            row["revealed_demand"] += max(0.0, _float(exact.get("demand_ema")))
            row["unmet_checks"] += max(0.0, _float(exact.get("unmet_check_ema")))
            row["unmet_amount"] += max(0.0, _float(exact.get("unmet_amount_ema")))
            row["last_tick"] = max(row["last_tick"], _int(exact.get("last_tick"), 0))
            row["exact_keys"].append(raw_key)

    supply_rows = {
        row["topic_id"]: row
        for row in local_service_category_supply_read(sim, chunk)
    }
    from game.chunk_service_survey import chunk_service_survey_read

    survey_chunk = chunk_service_survey_read(sim, chunk)
    survey_categories = survey_chunk.get("categories") if isinstance(survey_chunk.get("categories"), dict) else {}
    ticks_per_day = 24 * _ticks_per_hour(sim)
    now = _int(getattr(sim, "tick", 0), 0)
    fresh_days = max(0.0, _float(NEIGHBORHOOD_MARKET_TUNING["fresh_survey_days"], 1.0))
    blend_days = max(fresh_days + 0.01, _float(NEIGHBORHOOD_MARKET_TUNING["baseline_blend_days"], 7.0))
    genesis_categories = getattr(sim, "local_service_genesis_baseline", {})
    genesis_categories = genesis_categories.get(chunk, {}) if isinstance(genesis_categories, dict) else {}
    result = []
    for category_id in registry.SERVICE_LOCATOR_TOPICS:
        if topic_id and category_id != topic_id:
            continue
        survey = survey_categories.get(category_id) if isinstance(survey_categories.get(category_id), dict) else {}
        baseline_signed = max(-1.0, min(1.0,
            _float(survey.get("baseline")) + _float(survey.get("learned_mean"))
        ))
        genesis = genesis_categories.get(category_id) if isinstance(genesis_categories.get(category_id), dict) else {}
        genesis_mass = max(0.0, _float(genesis.get("mass"), 0.0))
        genesis_samples = max(0.0, _float(genesis.get("samples"), 0.0))
        baseline_positive = (
            genesis_mass / max(1.0, genesis_samples)
            if genesis_samples > 0.0
            else max(0.0, baseline_signed)
        )
        baseline_avoidance = max(0.0, -baseline_signed)
        last_survey_tick = _int(survey.get("last_tick"), -1)
        age_days = None if last_survey_tick < 0 else max(0.0, (now - last_survey_tick) / float(ticks_per_day))
        if age_days is None:
            survey_blend = 0.0
        elif age_days <= fresh_days:
            survey_blend = 1.0
        elif age_days >= blend_days:
            survey_blend = 0.0
        else:
            survey_blend = 1.0 - ((age_days - fresh_days) / (blend_days - fresh_days))
        respondent_mass = max(0.0, _float(survey.get("respondents_ema")))
        baseline_respondents = genesis_samples if genesis_samples > 0.0 else respondent_mass
        fresh_mass = max(0.0, _float(survey.get("ema_positive"))) * respondent_mass
        fresh_resistance = max(0.0, _float(survey.get("ema_avoidance"))) * respondent_mass
        baseline_mass = baseline_positive * baseline_respondents
        baseline_resistance = baseline_avoidance * baseline_respondents
        survey_mass = (survey_blend * fresh_mass) + ((1.0 - survey_blend) * baseline_mass)
        resistance = (survey_blend * fresh_resistance) + ((1.0 - survey_blend) * baseline_resistance)
        blended_respondents = (survey_blend * respondent_mass) + ((1.0 - survey_blend) * baseline_respondents)
        positive = survey_mass / max(1.0, blended_respondents)
        avoidance = resistance / max(1.0, blended_respondents)
        lived_row = lived[category_id]
        effective_demand = max(0.0,
            survey_mass
            + (NEIGHBORHOOD_MARKET_TUNING["revealed_demand_weight"] * lived_row["revealed_demand"])
            + (NEIGHBORHOOD_MARKET_TUNING["unmet_check_weight"] * lived_row["unmet_checks"])
            + (NEIGHBORHOOD_MARKET_TUNING["unmet_amount_weight"] * math.log1p(lived_row["unmet_amount"]))
            - (NEIGHBORHOOD_MARKET_TUNING["avoidance_weight"] * resistance)
        )
        supply = supply_rows.get(category_id, {})
        effective_supply = max(0.0, _float(supply.get("effective_supply")))
        pressure = effective_demand / max(1.0, effective_supply)
        definition = registry.service_category_definition(category_id)
        result.append({
            "topic_id": category_id,
            "market_group": definition.get("market_group", category_id),
            "consumer_action": definition.get("consumer_action", "patronage"),
            "protected_capability": bool(definition.get("protected_capability")),
            "survey_positive": round(positive, 4),
            "survey_avoidance": round(avoidance, 4),
            "respondent_mass": round(respondent_mass, 4),
            "genesis_mass": round(genesis_mass, 4),
            "genesis_samples": int(genesis_samples),
            "survey_mass": round(survey_mass, 4),
            "resistance": round(resistance, 4),
            "survey_blend": round(survey_blend, 4),
            "survey_age_days": None if age_days is None else round(age_days, 3),
            "survey_confidence": round(max(0.0, min(1.0, _float(survey_chunk.get("confidence")))), 4),
            "revealed_demand": round(lived_row["revealed_demand"], 4),
            "unmet_checks": round(lived_row["unmet_checks"], 4),
            "unmet_amount": round(lived_row["unmet_amount"], 4),
            "effective_demand": round(effective_demand, 4),
            "nominal_sites": max(0, _int(supply.get("nominal_sites"), 0)),
            "effective_supply": round(effective_supply, 4),
            "aggregate_attractiveness": round(max(0.0, _float(supply.get("aggregate_attractiveness"))), 4),
            "provider_ids": tuple(supply.get("provider_ids", ()) or ()),
            "opportunity_pressure": round(pressure, 4),
            "exact_keys": tuple(sorted(set(lived_row["exact_keys"]))),
            "last_lived_tick": lived_row["last_tick"],
        })
    result.sort(key=lambda row: (-row["opportunity_pressure"], -row["effective_demand"], row["topic_id"]))
    return tuple(result)


__all__ = [
    "NEIGHBORHOOD_MARKET_TUNING",
    "forget_local_service_supply",
    "initialize_local_service_demand_for_actors",
    "initialize_local_service_supply_for_records",
    "local_service_category_supply_read",
    "local_service_market_cache_stats",
    "local_service_economic_read",
    "local_service_demand_read",
    "local_service_provider_candidates",
    "local_service_supply_coverage_read",
    "local_service_supply_read",
    "neighborhood_service_market_read",
    "record_actor_local_service_demand_sample",
    "record_local_service_demand_sample",
    "record_local_service_dissatisfaction",
    "record_local_service_supply",
    "record_player_service_inquiry_demand",
    "record_unmet_local_service_demand",
    "refresh_property_market_supply",
]
