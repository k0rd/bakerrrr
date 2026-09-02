"""Bounded authoritative business adaptation for non-player commerce.

The registry is populated as properties enter the service-supply cache.  Its
heap schedules one daily review per business without iterating the property
registry, and missed time is collapsed into one present-tense review.
"""

from __future__ import annotations

import hashlib
import heapq
import math

from engine.events import Event
from engine.systems import System
from game.components import AI, FinancialProfile, Inventory, NPCWill, PlayerAssets, Position
from game.local_service_demand import (
    local_service_provider_candidates,
    neighborhood_service_market_read,
    refresh_property_market_supply,
)
from game.player_businesses import (
    _required_staff_for,
    _sync_staff_roster,
    player_business_apply_remodel,
    player_business_local_adaptation_read,
    player_business_operating_quality,
    player_business_set_hours_mode,
    player_business_set_markup_mode,
    player_business_staffing_fit,
    player_business_state,
    player_business_role_fit,
    property_supports_player_business,
)
from game.property_ownership import transfer_property_ownership
from game.property_runtime import property_focus_position, resolve_property_record
from game.service_category_registry import (
    property_has_protected_market_capability,
    service_categories_for_property,
)
from game.service_runtime import _transit_services_connecting_chunks
from game.system_support.ai_intent_runtime import _sync_ai_intent
from game.system_support.npc_income_runtime import inventory_liquid_credits


NEIGHBORHOOD_BUSINESS_SCHEMA = 1
NEIGHBORHOOD_BUSINESS_TUNING = {
    "profit_ema_alpha": 0.25,
    "failure_ema_alpha": 0.25,
    "loss_adjust_days": 2,
    "remodel_failure": 0.65,
    "remodel_days": 3,
    "remodel_advantage": 1.25,
    "closure_failure": 0.85,
    "closure_days": 7,
    "recovery_failure": 0.35,
    "listing_discount": 0.60,
    "minimum_buyout_manager_fit": 6.0,
    "daily_review_budget": 2,
    "base_revenue_per_demand": 10.0,
    "base_daily_upkeep": 8,
    "contractor_plan_hours": 4,
    "event_history_limit": 96,
}


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _ticks_per_hour(sim):
    traits = getattr(sim, "world_traits", {})
    clock = traits.get("clock", {}) if isinstance(traits, dict) else {}
    return max(60, _int((clock or {}).get("ticks_per_hour", 600), 600))


def _day_ticks(sim):
    return 24 * _ticks_per_hour(sim)


def _stable_unit(*parts):
    payload = "|".join(str(part) for part in parts).encode("utf-8", "replace")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big") / float(2**64 - 1)


def _state(sim, *, create=True):
    state = getattr(sim, "neighborhood_businesses", None)
    if not isinstance(state, dict):
        if not create:
            return {}
        state = {
            "schema": NEIGHBORHOOD_BUSINESS_SCHEMA,
            "entries": {},
            "chunks": {},
            "due_heap": [],
            "plans": {},
            "events": [],
            "revision": 0,
            "counters": {"reviews": 0, "stale_heap_rows": 0, "max_review_batch": 0},
        }
        sim.neighborhood_businesses = state
    state.setdefault("schema", NEIGHBORHOOD_BUSINESS_SCHEMA)
    state.setdefault("entries", {})
    state.setdefault("chunks", {})
    state.setdefault("due_heap", [])
    state.setdefault("plans", {})
    state.setdefault("events", [])
    state.setdefault("revision", 0)
    state.setdefault("counters", {"reviews": 0, "stale_heap_rows": 0, "max_review_batch": 0})
    return state


def neighborhood_business_state(sim, *, create=True):
    return _state(sim, create=create)


def _is_player_business(sim, prop):
    owner_eid = prop.get("owner_eid") if isinstance(prop, dict) else None
    if owner_eid is not None and owner_eid == getattr(sim, "player_eid", None):
        return True
    if str((prop or {}).get("owner_tag", "") or "").strip().lower() == "player":
        return True
    assets = sim.ecs.get(PlayerAssets).get(getattr(sim, "player_eid", None))
    return bool(assets and str(prop.get("id", "") or "") in getattr(assets, "owned_property_ids", set()))


def _entry_due_tick(sim, property_id, *, now=None):
    now = _int(getattr(sim, "tick", 0) if now is None else now, 0)
    day = _day_ticks(sim)
    day_start = (now // day) * day
    offset = int(_stable_unit(getattr(sim, "seed", 0), property_id, "business-review") * max(1, day - 1))
    due = day_start + offset
    return due if due > now else due + day


def register_neighborhood_business(sim, prop):
    """Incrementally register or refresh one economically relevant site."""

    if sim is None or not isinstance(prop, dict):
        return None
    property_id = str(prop.get("id", "") or "").strip()
    if not property_id or not property_supports_player_business(prop) or not service_categories_for_property(prop):
        return forget_neighborhood_business(sim, property_id)
    state = _state(sim)
    entries = state["entries"]
    entry = entries.get(property_id)
    chunk = _chunk_for(sim, prop)
    if not isinstance(entry, dict):
        due_tick = _entry_due_tick(sim, property_id)
        entry = {
            "property_id": property_id,
            "next_review_tick": due_tick,
            "generation": 1,
            "last_review_tick": None,
            "player_protected": _is_player_business(sim, prop),
            "capability_protected": property_has_protected_market_capability(prop),
            "chunk": chunk,
        }
        entries[property_id] = entry
        heapq.heappush(state["due_heap"], (due_tick, property_id, 1))
    else:
        old_chunk = tuple(entry.get("chunk", ()) or ())
        if len(old_chunk) >= 2 and old_chunk != chunk:
            old_bucket = state["chunks"].get((int(old_chunk[0]), int(old_chunk[1])))
            if isinstance(old_bucket, dict):
                old_bucket.pop(property_id, None)
        entry["player_protected"] = _is_player_business(sim, prop)
        entry["capability_protected"] = property_has_protected_market_capability(prop)
        entry["chunk"] = chunk
    state["chunks"].setdefault(chunk, {})[property_id] = True
    # Registration is intentionally structural only.  It runs from property
    # creation/restore paths while genesis may still be assigning organization
    # defaults, occupations, memberships, and legacy player-business metadata.
    # Mutable business runtime is created lazily by the scheduled review.
    state["revision"] = _int(state.get("revision"), 0) + 1
    return entry


def forget_neighborhood_business(sim, property_id):
    property_id = str(property_id or "").strip()
    if not property_id:
        return False
    state = _state(sim, create=False)
    removed = state.get("entries", {}).pop(property_id, None)
    if isinstance(removed, dict):
        old_chunk = tuple(removed.get("chunk", ()) or ())
        if len(old_chunk) >= 2:
            bucket = state.get("chunks", {}).get((int(old_chunk[0]), int(old_chunk[1])))
            if isinstance(bucket, dict):
                bucket.pop(property_id, None)
    state.get("plans", {}).pop(property_id, None)
    if removed is not None:
        state["revision"] = _int(state.get("revision"), 0) + 1
    return removed is not None


def _chunk_for(sim, prop):
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    chunk = metadata.get("chunk") if isinstance(metadata, dict) else None
    try:
        return (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError, IndexError):
        return tuple(int(value) for value in sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))[:2])


def _market_capture(sim, prop):
    chunk = _chunk_for(sim, prop)
    market = {row["topic_id"]: row for row in neighborhood_service_market_read(sim, chunk)}
    by_group = {}
    for topic_id in service_categories_for_property(prop):
        row = market.get(topic_id)
        if not isinstance(row, dict):
            continue
        group = str(row.get("market_group", topic_id) or topic_id)
        current = by_group.get(group)
        if current is None or _float(row.get("opportunity_pressure")) > _float(current.get("opportunity_pressure")):
            by_group[group] = row
    capture = 0.0
    details = []
    for group, row in sorted(by_group.items()):
        aggregate = max(0.01, _float(row.get("aggregate_attractiveness"), 0.0))
        provider_attractiveness = 0.0
        for provider in local_service_provider_candidates(sim, chunk, row["topic_id"], available_only=False):
            if str(provider.get("property_id", "") or "") == str(prop.get("id", "") or ""):
                provider_attractiveness = max(0.0, _float(provider.get("effective_attractiveness_now")))
                break
        share = min(1.0, provider_attractiveness / aggregate) if aggregate > 0.0 else 0.0
        group_capture = max(0.0, _float(row.get("effective_demand"))) * share
        capture = max(capture, group_capture)
        details.append({
            "group": group,
            "topic_id": row["topic_id"],
            "effective_demand": _float(row.get("effective_demand")),
            "opportunity_pressure": _float(row.get("opportunity_pressure")),
            "provider_share": round(share, 4),
            "captured_demand": round(group_capture, 4),
        })
    return chunk, round(capture, 4), tuple(details)


def _manager_perceived_signal(sim, prop, actual_signal, manager_fit):
    day = _int(getattr(sim, "tick", 0), 0) // _day_ticks(sim)
    uncertainty = max(0.0, min(1.0, 1.0 - (_float(manager_fit) / 10.0)))
    error = ((_stable_unit(getattr(sim, "seed", 0), prop.get("id"), day, "market-read") * 2.0) - 1.0) * uncertainty
    return max(0.0, _float(actual_signal) * (1.0 + (0.75 * error)))


def _ema(prior, sample, alpha):
    if prior is None:
        return _float(sample)
    return (alpha * _float(sample)) + ((1.0 - alpha) * _float(prior))


def _contractor_route(sim, origin_chunk):
    local = local_service_provider_candidates(sim, origin_chunk, "service_contractor")
    if local:
        return {"property_id": local[0]["property_id"], "chunk": origin_chunk, "mode": "local"}
    for radius in (1, 2):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if abs(dx) + abs(dy) != radius:
                    continue
                chunk = (origin_chunk[0] + dx, origin_chunk[1] + dy)
                providers = local_service_provider_candidates(sim, chunk, "service_contractor")
                if not providers:
                    continue
                transit = _transit_services_connecting_chunks(sim, origin_chunk, chunk)
                if transit or radius == 1:
                    return {
                        "property_id": providers[0]["property_id"],
                        "chunk": chunk,
                        "mode": "transit" if transit else "local",
                        "transit_services": tuple(transit),
                    }
    return None


def contractor_route_read(sim, origin_chunk):
    """Return one cached reachable contractor route for economic plans."""

    try:
        origin_chunk = (int(origin_chunk[0]), int(origin_chunk[1]))
    except (TypeError, ValueError, IndexError):
        return None
    route = _contractor_route(sim, origin_chunk)
    return dict(route) if isinstance(route, dict) else None


def _record_event(sim, kind, **data):
    state = _state(sim)
    row = {"tick": _int(getattr(sim, "tick", 0), 0), "kind": str(kind), **data}
    events = state["events"]
    events.append(row)
    del events[:-_int(NEIGHBORHOOD_BUSINESS_TUNING["event_history_limit"], 96)]
    state["revision"] = _int(state.get("revision"), 0) + 1
    sim.emit(Event(f"neighborhood_business_{kind}", **data))
    return row


def record_neighborhood_ownership_change(sim, **data):
    """Append one shared ownership transaction to the bounded economy trace."""

    state = _state(sim)
    row = {"tick": _int(getattr(sim, "tick", 0), 0), "kind": "ownership_changed", **data}
    events = state["events"]
    events.append(row)
    del events[:-_int(NEIGHBORHOOD_BUSINESS_TUNING["event_history_limit"], 96)]
    state["revision"] = _int(state.get("revision"), 0) + 1
    return row


def _buyer_funds(sim, eid):
    finance = sim.ecs.get(FinancialProfile).get(int(eid))
    inventory = sim.ecs.get(Inventory).get(int(eid))
    return (
        max(0, _int(getattr(finance, "bank_balance", 0), 0) if finance is not None else 0)
        + max(0, inventory_liquid_credits(inventory) if inventory is not None else 0)
    )


def _try_employee_buyout(sim, prop, runtime, listing_price):
    candidates = []
    for raw_eid in tuple(runtime.get("staff_roster", ()) or ()):
        eid = _int(raw_eid, 0)
        if eid <= 0 or _buyer_funds(sim, eid) < listing_price:
            continue
        fit = player_business_role_fit(sim, eid, prop, "manager")
        score = _float((fit or {}).get("score"), 0.0)
        if score < _float(NEIGHBORHOOD_BUSINESS_TUNING["minimum_buyout_manager_fit"], 6.0):
            continue
        candidates.append((-score, eid))
    candidates.sort()
    for _neg_score, eid in candidates:
        transfer = transfer_property_ownership(
            sim,
            prop.get("id"),
            new_owner_eid=eid,
            new_owner_tag="npc",
            price=listing_price,
            reason="employee_buyout",
        )
        if not isinstance(transfer, dict):
            continue
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
        metadata["economic_closed"] = False
        metadata["economic_listed"] = False
        runtime["customer_policy"] = "public"
        runtime["failure_ema"] = 0.35
        runtime["closure_days"] = 0
        refresh_property_market_supply(sim, prop)
        _record_event(sim, "employee_buyout", property_id=prop.get("id"), buyer_eid=eid, price=listing_price)
        return eid
    return None


def _close_business(sim, prop, runtime, *, reason):
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    if _is_player_business(sim, prop) or property_has_protected_market_capability(prop):
        return False
    metadata["economic_closed"] = True
    metadata["economic_listed"] = True
    runtime["customer_policy"] = "closed"
    ordinary_quote = max(80, _int(metadata.get("purchase_cost"), 150))
    listing_price = max(40, int(round(ordinary_quote * _float(NEIGHBORHOOD_BUSINESS_TUNING["listing_discount"], 0.60))))
    runtime["listing_price"] = listing_price
    runtime["closure_reason"] = str(reason or "failure")
    refresh_property_market_supply(sim, prop)
    buyer = _try_employee_buyout(sim, prop, runtime, listing_price)
    if buyer is None:
        _record_event(sim, "closed", property_id=prop.get("id"), reason=reason, listing_price=listing_price)
    return True


def _start_remodel_plan(sim, prop, runtime, adaptation):
    chunk = _chunk_for(sim, prop)
    route = _contractor_route(sim, chunk)
    if not isinstance(route, dict):
        runtime["contractor_blocked"] = True
        return False
    cost = max(0, _int(adaptation.get("cost"), 0))
    if _int(runtime.get("account_balance"), 0) < cost:
        runtime["capital_blocked"] = True
        return False
    property_id = str(prop.get("id", "") or "")
    plan = {
        "property_id": property_id,
        "kind": "remodel",
        "target_archetype": str(adaptation.get("target_archetype", "") or ""),
        "cost": cost,
        "contractor_property_id": str(route.get("property_id", "") or ""),
        "route": route,
        "created_tick": _int(getattr(sim, "tick", 0), 0),
        "ready_tick": _int(getattr(sim, "tick", 0), 0) + (_int(NEIGHBORHOOD_BUSINESS_TUNING["contractor_plan_hours"], 4) * _ticks_per_hour(sim)),
        "status": "traveling",
    }
    _state(sim)["plans"][property_id] = plan
    runtime["active_plan"] = dict(plan)

    owner_eid = prop.get("owner_eid")
    owner_pos = sim.ecs.get(Position).get(owner_eid) if owner_eid is not None else None
    contractor = resolve_property_record(sim, plan["contractor_property_id"], include_saved=False)
    target = property_focus_position(contractor) if isinstance(contractor, dict) else None
    ai = sim.ecs.get(AI).get(owner_eid) if owner_eid is not None else None
    if owner_pos is not None and ai is not None and isinstance(target, (tuple, list)) and len(target) >= 3:
        will = sim.ecs.get(NPCWill).get(owner_eid)
        _sync_ai_intent(
            ai,
            will,
            _int(getattr(sim, "tick", 0), 0),
            "seeking_service",
            score=48.0,
            target=(int(target[0]), int(target[1]), int(target[2])),
        )
        ai.service_topic_id = "service_contractor"
        ai.service_property_id = plan["contractor_property_id"]
        ai.service_business_plan_id = property_id
        plan["status"] = "owner_en_route"
    _record_event(sim, "remodel_planned", property_id=property_id, target_archetype=plan["target_archetype"], contractor_property_id=plan["contractor_property_id"])
    return True


def start_housing_conversion_plan(sim, prop, *, target_archetype="apartment"):
    """Fund and route a contractor-led conversion of one vacant building."""

    if not isinstance(prop, dict) or _is_player_business(sim, prop) or property_has_protected_market_capability(prop):
        return False
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    if not bool(metadata.get("economic_closed") or metadata.get("vacant") or metadata.get("abandoned")):
        return False
    property_id = str(prop.get("id", "") or "")
    if property_id in _state(sim).get("plans", {}):
        return False
    owner_eid = prop.get("owner_eid")
    if owner_eid is None:
        return False
    runtime = player_business_state(prop, create=True)
    if not isinstance(runtime, dict):
        return False
    target = "tenement" if str(target_archetype or "").strip().lower() == "tenement" else "apartment"
    source_price = max(80, _int(metadata.get("purchase_cost"), 150))
    cost = max(50, int(round(source_price * (0.52 if target == "tenement" else 0.42))))
    if _int(runtime.get("account_balance"), 0) < cost:
        return False
    route = _contractor_route(sim, _chunk_for(sim, prop))
    if not isinstance(route, dict):
        return False
    plan = {
        "property_id": property_id,
        "kind": "housing_conversion",
        "target_archetype": target,
        "cost": cost,
        "contractor_property_id": str(route.get("property_id", "") or ""),
        "route": route,
        "created_tick": _int(getattr(sim, "tick", 0), 0),
        "ready_tick": _int(getattr(sim, "tick", 0), 0) + (_int(NEIGHBORHOOD_BUSINESS_TUNING["contractor_plan_hours"], 4) * _ticks_per_hour(sim)),
        "status": "traveling",
    }
    _state(sim)["plans"][property_id] = plan
    runtime["active_plan"] = dict(plan)
    contractor = resolve_property_record(sim, plan["contractor_property_id"], include_saved=False)
    target_pos = property_focus_position(contractor) if isinstance(contractor, dict) else None
    owner_pos = sim.ecs.get(Position).get(owner_eid)
    ai = sim.ecs.get(AI).get(owner_eid)
    if owner_pos is not None and ai is not None and isinstance(target_pos, (tuple, list)) and len(target_pos) >= 3:
        _sync_ai_intent(
            ai,
            sim.ecs.get(NPCWill).get(owner_eid),
            _int(getattr(sim, "tick", 0), 0),
            "seeking_service",
            score=48.0,
            target=(int(target_pos[0]), int(target_pos[1]), int(target_pos[2])),
        )
        ai.service_topic_id = "service_contractor"
        ai.service_property_id = plan["contractor_property_id"]
        ai.service_business_plan_id = property_id
        plan["status"] = "owner_en_route"
    _record_event(sim, "housing_conversion_planned", property_id=property_id, target_archetype=target, contractor_property_id=plan["contractor_property_id"])
    return True


def complete_business_contractor_visit(sim, owner_eid, business_property_id):
    """Complete an active owner's embodied contractor visit."""

    state = _state(sim, create=False)
    plan = state.get("plans", {}).get(str(business_property_id or ""))
    if not isinstance(plan, dict) or plan.get("kind") not in {"remodel", "housing_conversion"}:
        return False
    prop = resolve_property_record(sim, business_property_id, include_saved=False)
    if not isinstance(prop, dict) or prop.get("owner_eid") != owner_eid:
        return False
    return _complete_remodel_plan(sim, prop, plan)


def _complete_remodel_plan(sim, prop, plan):
    runtime = player_business_state(prop, create=True)
    cost = max(0, _int(plan.get("cost"), 0))
    if _int(runtime.get("account_balance"), 0) < cost:
        plan["status"] = "capital_lost"
        return False
    if plan.get("kind") == "housing_conversion":
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
        target_archetype = "tenement" if str(plan.get("target_archetype", "") or "").strip().lower() == "tenement" else "apartment"
        metadata["archetype"] = target_archetype
        metadata["is_storefront"] = False
        metadata["site_services"] = []
        metadata["finance_services"] = []
        metadata["economic_closed"] = False
        metadata["economic_listed"] = False
        metadata.pop("business_name", None)
        result = {"target_archetype": target_archetype}
    else:
        result = player_business_apply_remodel(sim, prop, plan.get("target_archetype"))
        if not isinstance(result, dict):
            plan["status"] = "invalidated"
            return False
    runtime["account_balance"] = max(0, _int(runtime.get("account_balance"), 0) - cost)
    runtime["failure_ema"] = min(0.45, _float(runtime.get("failure_ema"), 0.0))
    runtime["remodel_days"] = 0
    runtime["active_plan"] = {}
    _state(sim)["plans"].pop(str(prop.get("id", "") or ""), None)
    refresh_property_market_supply(sim, prop)
    event_kind = "housing_converted" if plan.get("kind") == "housing_conversion" else "remodeled"
    _record_event(sim, event_kind, property_id=prop.get("id"), target_archetype=result.get("target_archetype"), cost=cost)
    return True


def _review_business(sim, prop, entry):
    runtime = player_business_state(prop, create=False)
    created_runtime = not isinstance(runtime, dict)
    if created_runtime:
        runtime = player_business_state(prop, create=True)
    if not isinstance(runtime, dict):
        return None
    if created_runtime and not bool(entry.get("player_protected")):
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
        seed_capital = max(60, int(round(max(80, _int(metadata.get("purchase_cost"), 150)) * 0.25)))
        runtime["account_balance"] = max(seed_capital, _int(runtime.get("account_balance"), 0))
    retain_incumbents = not bool(runtime.get("incumbent_staff_retained", False))
    staffing = _sync_staff_roster(
        sim,
        prop,
        runtime,
        retain_incumbents=retain_incumbents,
    )
    if retain_incumbents:
        runtime["incumbent_staff_retained"] = True
    required = _required_staff_for(prop)
    role_fit = player_business_staffing_fit(sim, prop)
    operating = player_business_operating_quality(
        sim,
        prop,
        required_staff=required,
        staffing=staffing,
        role_fit=role_fit,
    )
    manager_fit = _float(operating.get("manager_fit_score"), 0.0)
    chunk, captured, market_groups = _market_capture(sim, prop)
    pending = max(0, _int(runtime.pop("pending_patronage_revenue", 0), 0))
    reliability = max(0.0, min(1.0, _float(operating.get("service_reliability"), 0.0)))
    gross = pending + int(round(captured * _float(NEIGHBORHOOD_BUSINESS_TUNING["base_revenue_per_demand"], 10.0) * (0.35 + (0.65 * reliability))))
    wage_due = max(0, _int(staffing.get("staff_total"), 0)) * 4
    upkeep = _int(NEIGHBORHOOD_BUSINESS_TUNING["base_daily_upkeep"], 8) + len(service_categories_for_property(prop))
    account_before = max(0, _int(runtime.get("account_balance"), 0))
    available = account_before + gross
    wages_paid = min(available, wage_due)
    available -= wages_paid
    upkeep_paid = min(available, upkeep)
    available -= upkeep_paid
    unpaid_wages = max(0, wage_due - wages_paid)
    unpaid_upkeep = max(0, upkeep - upkeep_paid)
    profit = gross - wage_due - upkeep
    runtime["account_balance"] = max(0, available)
    profit_alpha = _float(NEIGHBORHOOD_BUSINESS_TUNING["profit_ema_alpha"], 0.25)
    failure_alpha = _float(NEIGHBORHOOD_BUSINESS_TUNING["failure_ema_alpha"], 0.25)
    runtime["profit_ema"] = round(_ema(runtime.get("profit_ema"), profit, profit_alpha), 4)
    failure_sample = max(0.0, min(1.0,
        (0.62 if profit < 0 else 0.15)
        + (0.25 * max(0.0, 0.68 - reliability))
        + (0.20 if unpaid_wages > 0 else 0.0)
        + (0.25 if _int(staffing.get("staff_total"), 0) <= 0 else 0.0)
    ))
    runtime["failure_ema"] = round(_ema(runtime.get("failure_ema"), failure_sample, failure_alpha), 4)
    failure = _float(runtime.get("failure_ema"), 0.0)
    runtime["loss_days"] = _int(runtime.get("loss_days"), 0) + 1 if profit < 0 else 0
    runtime["remodel_days"] = _int(runtime.get("remodel_days"), 0) + 1 if failure >= _float(NEIGHBORHOOD_BUSINESS_TUNING["remodel_failure"], 0.65) else 0
    runtime["closure_days"] = _int(runtime.get("closure_days"), 0) + 1 if failure >= _float(NEIGHBORHOOD_BUSINESS_TUNING["closure_failure"], 0.85) else 0
    if failure < _float(NEIGHBORHOOD_BUSINESS_TUNING["recovery_failure"], 0.35):
        runtime["closure_days"] = 0
        runtime["remodel_days"] = 0

    actual_signal = max((_float(row.get("opportunity_pressure")) for row in market_groups), default=0.0)
    perceived = _manager_perceived_signal(sim, prop, actual_signal, manager_fit)
    runtime["last_market_read"] = {
        "chunk": chunk,
        "captured_demand": captured,
        "actual_signal": round(actual_signal, 4),
        "perceived_signal": round(perceived, 4),
        "manager_fit": round(manager_fit, 2),
        "groups": market_groups,
    }
    runtime["last_summary"] = {
        **dict(runtime.get("last_summary", {}) if isinstance(runtime.get("last_summary"), dict) else {}),
        "gross_revenue": gross,
        "realized_revenue": gross,
        "wages_due": wage_due,
        "wages_paid": wages_paid,
        "upkeep_due": upkeep,
        "upkeep_paid": upkeep_paid,
        "unpaid_wages": unpaid_wages,
        "unpaid_upkeep": unpaid_upkeep,
        "service_reliability": reliability,
        "manager_fit_score": manager_fit,
        "staff_fit_score": _float(operating.get("staff_fit_score"), 0.0),
        "account_balance": _int(runtime.get("account_balance"), 0),
        "profit": profit,
        "profit_ema": runtime["profit_ema"],
        "failure_ema": runtime["failure_ema"],
        "market_capture": captured,
    }

    player_protected = _is_player_business(sim, prop)
    capability_protected = property_has_protected_market_capability(prop)
    entry["player_protected"] = player_protected
    entry["capability_protected"] = capability_protected
    active_plan = _state(sim).get("plans", {}).get(str(prop.get("id", "") or ""))
    if isinstance(active_plan, dict) and active_plan.get("status") == "traveling" and _int(getattr(sim, "tick", 0), 0) >= _int(active_plan.get("ready_tick"), 0):
        _complete_remodel_plan(sim, prop, active_plan)
    elif not player_protected:
        if runtime["loss_days"] >= _int(NEIGHBORHOOD_BUSINESS_TUNING["loss_adjust_days"], 2):
            # A deterministic modest response keeps this seam tunable without
            # inventing customers or scanning for replacement workers.
            player_business_set_markup_mode(prop, "bargain", sim=sim)
            player_business_set_hours_mode(sim, prop, "extended")
            runtime["hiring_pressure"] = round(min(1.0, _float(runtime.get("hiring_pressure")) + 0.15), 4)
        cannot_payroll = bool(runtime["last_summary"].get("unpaid_wages"))
        if not capability_protected and (
            runtime["closure_days"] >= _int(NEIGHBORHOOD_BUSINESS_TUNING["closure_days"], 7)
            or (cannot_payroll and _int(runtime.get("account_balance"), 0) <= 0)
        ):
            _close_business(sim, prop, runtime, reason="payroll" if cannot_payroll else "persistent_failure")
        elif not capability_protected and runtime["remodel_days"] >= _int(NEIGHBORHOOD_BUSINESS_TUNING["remodel_days"], 3) and not isinstance(active_plan, dict):
            options = player_business_local_adaptation_read(sim, prop)
            best = options[0] if options else None
            if isinstance(best, dict):
                best_signal = _manager_perceived_signal(sim, prop, best.get("adaptation_signal"), manager_fit)
                if best_signal >= (perceived * _float(NEIGHBORHOOD_BUSINESS_TUNING["remodel_advantage"], 1.25)):
                    _start_remodel_plan(sim, prop, runtime, best)

    refresh_property_market_supply(sim, prop)
    entry["last_review_tick"] = _int(getattr(sim, "tick", 0), 0)
    entry["last_result"] = {
        "profit": profit,
        "profit_ema": runtime["profit_ema"],
        "failure_ema": runtime["failure_ema"],
        "gross_revenue": gross,
        "captured_demand": captured,
        "reliability": reliability,
    }
    return entry["last_result"]


def neighborhood_business_read(sim, chunk=None):
    """Debug read over the business index, never the property registry."""

    state = _state(sim, create=False)
    rows = []
    if chunk is not None:
        try:
            chunk = (int(chunk[0]), int(chunk[1]))
        except (TypeError, ValueError, IndexError):
            return ()
        property_ids = tuple((state.get("chunks", {}).get(chunk, {}) or {}).keys())
    else:
        property_ids = tuple(state.get("entries", {}).keys())
    for property_id in sorted(property_ids):
        entry = state["entries"][property_id]
        prop = resolve_property_record(sim, property_id, include_saved=False)
        if not isinstance(prop, dict):
            continue
        prop_chunk = _chunk_for(sim, prop)
        if chunk is not None and tuple(chunk) != prop_chunk:
            continue
        runtime = player_business_state(prop, create=False) or {}
        rows.append({
            **dict(entry),
            "chunk": prop_chunk,
            "name": str(prop.get("name", property_id) or property_id),
            "archetype": str((prop.get("metadata") or {}).get("archetype", "") or ""),
            "owner_eid": prop.get("owner_eid"),
            "owner_tag": str(prop.get("owner_tag", "") or ""),
            "closed": bool((prop.get("metadata") or {}).get("economic_closed")),
            "listed": bool((prop.get("metadata") or {}).get("economic_listed")),
            "runtime": dict(runtime),
            "plan": dict(state.get("plans", {}).get(property_id, {}) or {}),
        })
    return tuple(rows)


def neighborhood_business_property_ids(sim, chunk):
    """Return cached economic workplaces in one chunk."""

    try:
        chunk = (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError, IndexError):
        return ()
    bucket = _state(sim, create=False).get("chunks", {}).get(chunk, {})
    return tuple(sorted(str(value) for value in bucket)) if isinstance(bucket, dict) else ()


class NeighborhoodBusinessSystem(System):
    """Pop a bounded number of due business reviews per simulation update."""

    def update(self):
        state = _state(self.sim)
        now = _int(getattr(self.sim, "tick", 0), 0)
        heap = state["due_heap"]
        budget = max(1, _int(NEIGHBORHOOD_BUSINESS_TUNING["daily_review_budget"], 2))
        reviewed = 0
        while heap and reviewed < budget and _int(heap[0][0], now + 1) <= now:
            due_tick, property_id, generation = heapq.heappop(heap)
            entry = state["entries"].get(property_id)
            if not isinstance(entry, dict) or _int(entry.get("generation"), 0) != _int(generation, -1) or _int(entry.get("next_review_tick"), -1) != _int(due_tick, -2):
                state["counters"]["stale_heap_rows"] = _int(state["counters"].get("stale_heap_rows"), 0) + 1
                continue
            prop = resolve_property_record(self.sim, property_id, include_saved=False)
            if not isinstance(prop, dict):
                forget_neighborhood_business(self.sim, property_id)
                continue
            _review_business(self.sim, prop, entry)
            reviewed += 1
            entry["generation"] = _int(entry.get("generation"), 0) + 1
            entry["next_review_tick"] = now + _day_ticks(self.sim)
            heapq.heappush(heap, (entry["next_review_tick"], property_id, entry["generation"]))
        counters = state["counters"]
        counters["reviews"] = _int(counters.get("reviews"), 0) + reviewed
        counters["max_review_batch"] = max(_int(counters.get("max_review_batch"), 0), reviewed)
        if reviewed:
            state["revision"] = _int(state.get("revision"), 0) + 1


__all__ = [
    "NEIGHBORHOOD_BUSINESS_TUNING",
    "NeighborhoodBusinessSystem",
    "complete_business_contractor_visit",
    "contractor_route_read",
    "forget_neighborhood_business",
    "neighborhood_business_read",
    "neighborhood_business_property_ids",
    "neighborhood_business_state",
    "register_neighborhood_business",
    "record_neighborhood_ownership_change",
    "start_housing_conversion_plan",
]
