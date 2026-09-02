"""Bounded actor service pursuits backed by the authoritative chunk market."""

from __future__ import annotations

from engine.events import Event
from game.chunk_service_survey import (
    NPC_SERVICE_SCORE_PROFILE_KEY,
    actor_service_score_vector,
    adjust_actor_service_need_score,
)
from game.components import (
    BehaviorProfile,
    FinancialProfile,
    Inventory,
    NPCNeeds,
    Occupation,
    Position,
    PropertyPortfolio,
    VehicleState,
    Vitality,
)
from game.local_service_demand import (
    local_service_provider_candidates,
    record_actor_local_service_demand_sample,
    record_unmet_local_service_demand,
)
from game.property_access import property_is_open
from game.property_keys import can_receive_property_key, ensure_actor_has_property_key, ensure_property_lock
from game.property_runtime import property_focus_position, resolve_property_record
from game.service_category_registry import (
    SERVICE_LOCATOR_TOPICS,
    service_categories_for_property,
    service_categories_for_raw_key,
    service_category_definition,
)
from game.service_runtime import (
    _transit_services_connecting_chunks,
    _vehicle_sale_lookup_offer,
    _vehicle_sale_remove_offer,
)
from game.system_support.npc_income_runtime import inventory_liquid_credits, npc_hourly_wage, spend_npc_wallet_credits
from game.vehicles import vehicle_metadata


CONSUMER_PURSUIT_TUNING = {
    "interval_hours": 6,
    "strong_threshold": 0.55,
    "failure_window_hours": 72,
    "transit_failure_count": 2,
    "vehicle_failure_count": 3,
    "relocation_failure_count": 4,
    "remote_chunk_radius": 2,
    "remote_candidate_limit": 12,
    "success_learning": 0.02,
    "poor_service_learning": -0.03,
}

_BASE_SERVICE_COST = {
    "service_transit": 3,
    "service_rail": 4,
    "service_bus": 3,
    "service_shuttle": 3,
    "service_ferry": 5,
    "service_coach": 5,
    "service_gaming": 4,
    "service_rest": 8,
    "service_street_doctor": 10,
    "service_herbal": 7,
    "service_appearance": 12,
    "service_vehicle_sales": 20,
    "service_used_cars": 20,
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


def _consumer_state(sim, eid, *, create=True):
    behavior = sim.ecs.get(BehaviorProfile).get(int(eid))
    if behavior is None:
        if not create:
            return {}
        behavior = BehaviorProfile()
        sim.ecs.add(int(eid), behavior)
    preferences = behavior.preferences if isinstance(behavior.preferences, dict) else {}
    behavior.preferences = preferences
    profile = preferences.get(NPC_SERVICE_SCORE_PROFILE_KEY)
    if not isinstance(profile, dict):
        if not create:
            return {}
        actor_service_score_vector(sim, int(eid))
        profile = preferences.get(NPC_SERVICE_SCORE_PROFILE_KEY)
    consumer = profile.get("consumer") if isinstance(profile, dict) else None
    if not isinstance(consumer, dict):
        if not create:
            return {}
        consumer = {
            "next_tick": 0,
            "failures": {},
            "vehicle_pressure": 0.0,
            "relocation_pressure": 0.0,
            "last_success_tick": 0,
        }
        profile["consumer"] = consumer
    consumer.setdefault("next_tick", 0)
    consumer.setdefault("failures", {})
    consumer.setdefault("vehicle_pressure", 0.0)
    consumer.setdefault("relocation_pressure", 0.0)
    return consumer


def actor_consumer_pressure_read(sim, eid):
    return dict(_consumer_state(sim, eid, create=False) or {})


def _actor_has_vehicle(sim, eid):
    vehicle = sim.ecs.get(VehicleState).get(int(eid))
    if vehicle is not None and str(getattr(vehicle, "active_vehicle_id", "") or "").strip():
        return True
    portfolio = sim.ecs.get(PropertyPortfolio).get(int(eid))
    for property_id in tuple(getattr(portfolio, "owned_property_ids", ()) or ()):
        prop = resolve_property_record(sim, property_id, include_saved=False)
        if isinstance(prop, dict) and str(prop.get("kind", "") or "").strip().lower() == "vehicle":
            return True
    return False


def _failure_row(consumer, topic_id, now, *, create=True):
    failures = consumer.setdefault("failures", {})
    row = failures.get(topic_id)
    if not isinstance(row, dict):
        if not create:
            return {}
        row = {"count": 0, "first_tick": now, "last_tick": 0, "last_reason": ""}
        failures[topic_id] = row
    return row


def _note_failure(sim, eid, topic_id, pos, *, reason, transit_available=False):
    now = _int(getattr(sim, "tick", 0), 0)
    consumer = _consumer_state(sim, eid)
    row = _failure_row(consumer, topic_id, now)
    window = _int(CONSUMER_PURSUIT_TUNING["failure_window_hours"], 72) * _ticks_per_hour(sim)
    if now - _int(row.get("last_tick"), 0) > window:
        row.update({"count": 0, "first_tick": now})
    row["count"] = _int(row.get("count"), 0) + 1
    row["last_tick"] = now
    row["last_reason"] = str(reason or "unavailable").strip().lower()
    row["transit_available"] = bool(transit_available)
    count = row["count"]
    if count >= _int(CONSUMER_PURSUIT_TUNING["vehicle_failure_count"], 3) and not transit_available and not _actor_has_vehicle(sim, eid):
        consumer["vehicle_pressure"] = round(min(1.0, _float(consumer.get("vehicle_pressure")) + 0.2), 4)
        adjust_actor_service_need_score(sim, eid, "service_used_cars", 0.18, reason="repeated_service_travel_failure")
    if count >= _int(CONSUMER_PURSUIT_TUNING["relocation_failure_count"], 4):
        consumer["relocation_pressure"] = round(min(1.0, _float(consumer.get("relocation_pressure")) + 0.16), 4)
    record_unmet_local_service_demand(
        sim,
        x=pos.x,
        y=pos.y,
        service=topic_id,
        motive=str(reason or "unavailable"),
        amount=count,
        tick=now,
    )
    sim.emit(Event(
        "npc_service_demand_unmet",
        npc_eid=int(eid),
        service=topic_id,
        motive=str(reason or "unavailable"),
        failure_count=count,
        transit_available=bool(transit_available),
        vehicle_pressure=float(consumer.get("vehicle_pressure", 0.0) or 0.0),
        relocation_pressure=float(consumer.get("relocation_pressure", 0.0) or 0.0),
        x=int(pos.x),
        y=int(pos.y),
        z=int(pos.z),
    ))
    return row


def _candidate_chunks(origin, radius):
    rows = []
    for cy in range(origin[1] - radius, origin[1] + radius + 1):
        for cx in range(origin[0] - radius, origin[0] + radius + 1):
            chunk = (cx, cy)
            if chunk == origin:
                continue
            distance = abs(cx - origin[0]) + abs(cy - origin[1])
            rows.append((distance, chunk))
    rows.sort(key=lambda row: (row[0], row[1][1], row[1][0]))
    return tuple(chunk for _distance, chunk in rows[:_int(CONSUMER_PURSUIT_TUNING["remote_candidate_limit"], 12)])


def _provider_target(sim, provider):
    property_id = str(provider.get("property_id", "") or "").strip()
    prop = resolve_property_record(sim, property_id, include_saved=False)
    if not isinstance(prop, dict):
        return None
    if property_is_open(sim, prop) is False:
        return None
    target = property_focus_position(prop)
    if not isinstance(target, (tuple, list)) or len(target) < 3:
        return None
    return prop, (int(target[0]), int(target[1]), int(target[2]))


def actor_service_pursuit_candidate(sim, eid, pos):
    """Return at most one due pursuit; absence may record one bounded failure."""

    eid = int(eid)
    now = _int(getattr(sim, "tick", 0), 0)
    consumer = _consumer_state(sim, eid)
    if now < _int(consumer.get("next_tick"), 0):
        return None
    interval = _int(CONSUMER_PURSUIT_TUNING["interval_hours"], 6) * _ticks_per_hour(sim)
    consumer["next_tick"] = now + interval
    scores, context, _profile = actor_service_score_vector(sim, eid, tick=now)
    threshold = _float(CONSUMER_PURSUIT_TUNING["strong_threshold"], 0.55)
    ranked = []
    best_by_group = {}
    for topic_id, score in scores.items():
        definition = service_category_definition(topic_id)
        if bool(definition.get("hidden_lead")) or _float(score) < threshold:
            continue
        group = str(definition.get("market_group", topic_id) or topic_id)
        prior = best_by_group.get(group)
        candidate = (_float(score), topic_id)
        if prior is None or candidate > prior:
            best_by_group[group] = candidate
    ranked.extend(best_by_group.values())
    ranked.sort(key=lambda row: (-row[0], row[1]))
    if not ranked:
        return None
    score, topic_id = ranked[0]
    origin = tuple(int(value) for value in sim.chunk_coords(int(pos.x), int(pos.y))[:2])

    for provider in local_service_provider_candidates(sim, origin, topic_id):
        resolved = _provider_target(sim, provider)
        if resolved is None:
            continue
        prop, target = resolved
        record_actor_local_service_demand_sample(
            sim,
            actor_eid=eid,
            x=pos.x,
            y=pos.y,
            service=topic_id,
            motive=f"consumer:{context.get('state', 'idle')}",
            intensity=max(0.05, score),
            tick=now,
            interval_ticks=interval,
        )
        return {
            "topic_id": topic_id,
            "score": score,
            "property_id": str(prop.get("id", "") or "").strip(),
            "target": target,
            "travel_mode": "local",
            "destination_chunk": origin,
        }

    transit_available = False
    has_vehicle = _actor_has_vehicle(sim, eid)
    failure = _failure_row(consumer, topic_id, now, create=False)
    transit_unlocked = _int((failure or {}).get("count"), 0) >= _int(CONSUMER_PURSUIT_TUNING["transit_failure_count"], 2)
    remote_rows = []
    for destination in _candidate_chunks(origin, _int(CONSUMER_PURSUIT_TUNING["remote_chunk_radius"], 2)):
        providers = local_service_provider_candidates(sim, destination, topic_id)
        if not providers:
            continue
        transit = _transit_services_connecting_chunks(sim, origin, destination)
        transit_available = transit_available or bool(transit)
        remote_rows.append((destination, providers, tuple(transit)))

    # Transit is a learned answer to repeated local frustration.  Both ends
    # are selected from cached provider indexes, so boarding never discovers
    # the network by scanning properties.
    if transit_unlocked:
        for destination, providers, transit in remote_rows:
            for raw_service in transit:
                transit_topics = tuple(
                    category for category in service_categories_for_raw_key(raw_service)
                    if service_category_definition(category).get("market_group") == "transit"
                )
                for transit_topic in (*tuple(category for category in transit_topics if category != "service_transit"), "service_transit"):
                    origins = local_service_provider_candidates(sim, origin, transit_topic)
                    destinations = local_service_provider_candidates(sim, destination, transit_topic)
                    if not origins or not destinations:
                        continue
                    origin_resolved = _provider_target(sim, origins[0])
                    destination_resolved = _provider_target(sim, destinations[0])
                    if origin_resolved is None or destination_resolved is None:
                        continue
                    origin_prop, origin_target = origin_resolved
                    _destination_prop, destination_target = destination_resolved
                    for provider in providers:
                        resolved = _provider_target(sim, provider)
                        if resolved is None:
                            continue
                        prop, final_target = resolved
                        return {
                            "topic_id": topic_id,
                            "score": score,
                            "property_id": str(prop.get("id", "") or "").strip(),
                            "target": origin_target,
                            "travel_mode": "transit",
                            "destination_chunk": destination,
                            "transit_services": tuple(transit),
                            "transit_service": str(raw_service),
                            "transit_origin_property_id": str(origin_prop.get("id", "") or ""),
                            "transit_destination_target": destination_target,
                            "service_destination_target": final_target,
                        }

    if has_vehicle:
        for destination, providers, transit in remote_rows:
            for provider in providers:
                resolved = _provider_target(sim, provider)
                if resolved is None:
                    continue
                prop, target = resolved
                return {
                    "topic_id": topic_id,
                    "score": score,
                    "property_id": str(prop.get("id", "") or "").strip(),
                    "target": target,
                    "travel_mode": "vehicle",
                    "destination_chunk": destination,
                    "transit_services": tuple(transit),
                }

    _note_failure(
        sim,
        eid,
        topic_id,
        pos,
        reason="no_local_provider" if not transit_available else "provider_requires_travel",
        transit_available=transit_available,
    )
    return None


def advance_actor_service_transit(sim, eid, ai, pos):
    """Board a planned cached transit connection and continue to the service."""

    if str(getattr(ai, "service_travel_mode", "") or "").strip().lower() != "transit":
        return False
    if str(getattr(ai, "service_transit_phase", "origin") or "origin").strip().lower() == "destination":
        return False
    destination = getattr(ai, "service_transit_destination_target", None)
    final_target = getattr(ai, "service_destination_target", None)
    if not isinstance(destination, (tuple, list)) or len(destination) < 3 or not isinstance(final_target, (tuple, list)) or len(final_target) < 3:
        return False
    inventory = sim.ecs.get(Inventory).get(int(eid))
    fare = max(1, _int(_BASE_SERVICE_COST.get("service_transit"), 3))
    if inventory is None or inventory_liquid_credits(inventory) < fare:
        _note_failure(sim, eid, getattr(ai, "service_topic_id", ""), pos, reason="cannot_afford_transit", transit_available=True)
        return False
    spend_npc_wallet_credits(inventory, fare)
    old_x, old_y, old_z = int(pos.x), int(pos.y), int(pos.z)
    new_x, new_y, new_z = int(destination[0]), int(destination[1]), int(destination[2])
    sim.tilemap.move_entity(
        int(eid),
        oldx=old_x,
        oldy=old_y,
        oldz=old_z,
        newx=new_x,
        newy=new_y,
        newz=new_z,
    )
    pos.x, pos.y, pos.z = new_x, new_y, new_z
    ai.target = (int(final_target[0]), int(final_target[1]), int(final_target[2]))
    ai.service_transit_phase = "destination"
    consumer = _consumer_state(sim, eid)
    consumer["next_tick"] = max(
        _int(consumer.get("next_tick"), 0),
        _int(getattr(sim, "tick", 0), 0) + _ticks_per_hour(sim),
    )
    sim.emit(Event(
        "entity_moved",
        eid=int(eid),
        old_x=old_x,
        old_y=old_y,
        old_z=old_z,
        x=new_x,
        y=new_y,
        z=new_z,
        reason="npc_service_transit",
    ))
    sim.emit(Event(
        "npc_service_transit_used",
        npc_eid=int(eid),
        service=str(getattr(ai, "service_transit_service", "") or "transit"),
        desired_service=str(getattr(ai, "service_topic_id", "") or ""),
        fare=fare,
        origin_chunk=tuple(sim.chunk_coords(old_x, old_y)),
        destination_chunk=tuple(sim.chunk_coords(new_x, new_y)),
    ))
    return True


def _provider_cached_profile(sim, chunk, topic_id, property_id):
    for provider in local_service_provider_candidates(sim, chunk, topic_id, available_only=False):
        if str(provider.get("property_id", "") or "").strip() == str(property_id or "").strip():
            return provider
    return {}


def _vehicle_spawn_tile_near(sim, x, y, z=0, radius=6):
    x, y, z = int(x), int(y), int(z)
    for ring in range(0, max(1, int(radius)) + 1):
        for dy in range(-ring, ring + 1):
            for dx in range(-ring, ring + 1):
                if ring and max(abs(dx), abs(dy)) != ring:
                    continue
                nx, ny = x + dx, y + dy
                if sim.detail_for_xy(nx, ny) == "unloaded":
                    continue
                if sim.structure_at(nx, ny, z) or sim.property_at(nx, ny, z):
                    continue
                if sim.tilemap.is_walkable(nx, ny, z):
                    return nx, ny
    return None


def purchase_vehicle_for_actor(sim, eid, dealer_prop, pos, *, quality="used"):
    """Actor-neutral cash purchase used by economic vehicle pressure."""

    eid = int(eid)
    if _actor_has_vehicle(sim, eid) or not isinstance(dealer_prop, dict):
        return False
    quality = "new" if str(quality or "").strip().lower() == "new" else "used"
    offer = _vehicle_sale_lookup_offer(sim, dealer_prop, quality)
    if not isinstance(offer, dict):
        return False
    price = max(80, _int(offer.get("price"), 500))
    inventory = sim.ecs.get(Inventory).get(eid)
    profile = sim.ecs.get(FinancialProfile).get(eid)
    occupation = sim.ecs.get(Occupation).get(eid)
    if inventory is None or profile is None:
        return False
    wage = npc_hourly_wage(
        sim,
        eid,
        career=getattr(occupation, "career", "") if occupation is not None else "",
        workplace_prop=None,
    )
    living_buffer = max(20, int(wage) * 16)
    available = inventory_liquid_credits(inventory) + max(0, _int(getattr(profile, "bank_balance", 0), 0))
    if available < price + living_buffer:
        return False
    spawn = _vehicle_spawn_tile_near(sim, pos.x, pos.y, z=pos.z, radius=6)
    if spawn is None:
        return False
    sx, sy = spawn
    chunk = tuple(int(value) for value in sim.chunk_coords(sx, sy)[:2])
    vehicle_name = str(offer.get("vehicle_name", "Vehicle") or "Vehicle").strip() or "Vehicle"
    token = f"veh:npc-purchase:{eid}:{getattr(sim, 'tick', 0)}:{offer.get('offering_id', 'offer')}"
    vehicle_profile = {
        "quality": quality,
        "paint": str(offer.get("paint", "") or "").strip(),
        "make": str(offer.get("make", "Unknown") or "Unknown").strip(),
        "model": str(offer.get("model", "Vehicle") or "Vehicle").strip(),
        "vehicle_class": str(offer.get("vehicle_class", "sedan") or "sedan").strip().lower(),
        "power": max(1, min(10, _int(offer.get("power"), 5))),
        "durability": max(1, min(10, _int(offer.get("durability"), 5))),
        "fuel_efficiency": max(1, min(10, _int(offer.get("fuel_efficiency"), 5))),
        "fuel_capacity": max(10, _int(offer.get("fuel_capacity"), 60)),
        "fuel": max(0, _int(offer.get("fuel"), _int(offer.get("fuel_capacity"), 60))),
        "price": price,
        "glyph": str(offer.get("glyph", "&") or "&")[:1],
    }
    metadata = vehicle_metadata(
        vehicle_profile,
        chunk=chunk,
        owner_tag="npc",
        display_color=str(offer.get("display_color", "") or "").strip() or "vehicle_parked",
        locked=True,
        key_id=token,
        key_label=vehicle_name,
        lock_tier=3 if quality == "new" else 2,
    )
    preview = {"id": token, "name": vehicle_name, "kind": "vehicle", "metadata": metadata}
    if not can_receive_property_key(sim, eid, preview):
        return False
    vehicle_id = sim.register_property(
        name=vehicle_name,
        kind="vehicle",
        x=sx,
        y=sy,
        z=int(pos.z),
        owner_eid=eid,
        owner_tag="npc",
        metadata=metadata,
    )
    sim.chunk_property_records.setdefault(chunk, []).append({
        "id": vehicle_id,
        "kind": "vehicle",
        "x": sx,
        "y": sy,
        "z": int(pos.z),
        "archetype": "vehicle",
        "building_id": None,
    })
    vehicle_prop = sim.properties.get(vehicle_id)
    key_ok, _instance_id, _created = ensure_actor_has_property_key(sim, eid, vehicle_prop, owner_tag="npc")
    if not key_ok and isinstance(vehicle_prop, dict):
        ensure_property_lock(vehicle_prop, locked=False)
    wallet_spent = spend_npc_wallet_credits(inventory, price)
    bank_spent = max(0, price - wallet_spent)
    profile.bank_balance = max(0, _int(getattr(profile, "bank_balance", 0), 0) - bank_spent)
    portfolio = sim.ecs.get(PropertyPortfolio).get(eid)
    if portfolio is None:
        portfolio = PropertyPortfolio()
        sim.ecs.add(eid, portfolio)
    portfolio.owned_property_ids.add(vehicle_id)
    vehicle_state = sim.ecs.get(VehicleState).get(eid)
    if vehicle_state is None:
        vehicle_state = VehicleState()
        sim.ecs.add(eid, vehicle_state)
    if not vehicle_state.active_vehicle_id:
        vehicle_state.set_active_vehicle(vehicle_id, tick=getattr(sim, "tick", 0))
    _vehicle_sale_remove_offer(sim, dealer_prop, quality, offer.get("offering_id"))
    sim.emit(Event(
        "npc_vehicle_purchased",
        npc_eid=eid,
        property_id=str(dealer_prop.get("id", "") or "").strip(),
        vehicle_id=vehicle_id,
        vehicle_name=vehicle_name,
        price=price,
        quality=quality,
        key_issued=bool(key_ok),
    ))
    return True


def resolve_actor_service_pursuit(sim, eid, *, property_id, topic_id, pos=None):
    """Settle one embodied visit and feed its result back into the market."""

    eid = int(eid)
    topic_id = str(topic_id or "").strip().lower()
    if topic_id not in SERVICE_LOCATOR_TOPICS:
        return False
    prop = resolve_property_record(sim, property_id, include_saved=False)
    pos = pos or sim.ecs.get(Position).get(eid)
    if pos is None or not isinstance(prop, dict) or topic_id not in service_categories_for_property(prop):
        if pos is not None:
            _note_failure(sim, eid, topic_id, pos, reason="provider_changed")
        return False
    chunk = tuple(int(value) for value in sim.chunk_coords(int(prop.get("x", pos.x)), int(prop.get("y", pos.y)))[:2])
    provider = _provider_cached_profile(sim, chunk, topic_id, property_id)
    reliability = max(0.0, min(1.0, _float(provider.get("reliability"), 1.0)))
    if topic_id in {"service_vehicle_sales", "service_used_cars"}:
        quality = "used" if topic_id == "service_used_cars" else "new"
        if not purchase_vehicle_for_actor(sim, eid, prop, pos, quality=quality):
            _note_failure(sim, eid, topic_id, pos, reason="vehicle_purchase_unaffordable")
            return False
        consumer = _consumer_state(sim, eid)
        consumer["vehicle_pressure"] = 0.0
        failure = _failure_row(consumer, topic_id, _int(getattr(sim, "tick", 0)), create=False)
        if isinstance(failure, dict):
            failure["count"] = 0
        adjust_actor_service_need_score(sim, eid, topic_id, -0.2, reason="vehicle_purchased")
        return True
    cost = max(0, _int(_BASE_SERVICE_COST.get(topic_id, 5), 5))
    inventory = sim.ecs.get(Inventory).get(eid)
    if cost > 0 and (inventory is None or inventory_liquid_credits(inventory) < cost):
        _note_failure(sim, eid, topic_id, pos, reason="cannot_afford")
        return False
    spent = spend_npc_wallet_credits(inventory, cost) if cost > 0 else 0
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    business = metadata.get("business_economy")
    if not isinstance(business, dict):
        business = metadata.get("player_business")
    if not isinstance(business, dict):
        business = {}
        metadata["business_economy"] = business
    business["pending_patronage_revenue"] = _int(business.get("pending_patronage_revenue"), 0) + spent
    business["patronage_count"] = _int(business.get("patronage_count"), 0) + 1

    needs = sim.ecs.get(NPCNeeds).get(eid)
    vitality = sim.ecs.get(Vitality).get(eid)
    if needs is not None:
        if topic_id == "service_rest":
            needs.energy = min(100.0, _float(getattr(needs, "energy", 0.0)) + 8.0)
        elif topic_id == "service_gaming":
            needs.social = min(100.0, _float(getattr(needs, "social", 0.0)) + 6.0)
        elif topic_id == "service_trade":
            needs.hunger = min(100.0, _float(getattr(needs, "hunger", 0.0)) + 2.0)
            needs.thirst = min(100.0, _float(getattr(needs, "thirst", 0.0)) + 2.0)
    if vitality is not None and topic_id in {"service_street_doctor", "service_herbal"}:
        vitality.hp = min(_int(getattr(vitality, "max_hp", vitality.hp), vitality.hp), _int(vitality.hp, 0) + 4)

    consumer = _consumer_state(sim, eid)
    failure = _failure_row(consumer, topic_id, _int(getattr(sim, "tick", 0)), create=False)
    if isinstance(failure, dict):
        failure["count"] = 0
        failure["last_success_tick"] = _int(getattr(sim, "tick", 0), 0)
    consumer["last_success_tick"] = _int(getattr(sim, "tick", 0), 0)
    learning = CONSUMER_PURSUIT_TUNING["success_learning"] if reliability >= 0.68 else CONSUMER_PURSUIT_TUNING["poor_service_learning"]
    adjust_actor_service_need_score(sim, eid, topic_id, learning, reason="service_visit")
    sim.emit(Event(
        "npc_service_patronized",
        npc_eid=eid,
        property_id=str(property_id or "").strip(),
        service=topic_id,
        cost=spent,
        reliability=round(reliability, 3),
        satisfied=bool(reliability >= 0.68),
        x=int(pos.x),
        y=int(pos.y),
        z=int(pos.z),
    ))
    return True


__all__ = [
    "CONSUMER_PURSUIT_TUNING",
    "advance_actor_service_transit",
    "actor_consumer_pressure_read",
    "actor_service_pursuit_candidate",
    "purchase_vehicle_for_actor",
    "resolve_actor_service_pursuit",
]
