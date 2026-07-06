"""Shared NPC behavior tags and helper routines."""

from __future__ import annotations

import random

from engine.sites import site_entry_front_cell
from engine.events import Event
from game.components import AI, ArmorLoadout, BehaviorProfile, CriminalDriveState, FinancialProfile, Inventory, JusticeProfile, NPCNeeds, NPCRoutine, Occupation, Position, PropertyKnowledge, StatusEffects, Vitality, WeaponLoadout
from game.drone_distribution import drone_item_base_value
from game.item_semantics import (
    appraise_item_for_actor,
    identify_item_for_actor,
    item_category as _item_category,
    item_is_appraised_for_actor,
    item_is_identified_for_actor,
    item_legal_status as _item_legal_status,
    item_requires_identification,
    item_tags as _item_tags,
)
from game.items import CREDSTICK_ITEM_ID, ITEM_CATALOG, credstick_total_credits, is_credstick_item, item_display_name, item_instance_condition
from game.property_access import evaluate_property_access as _evaluate_property_access, world_hour as _world_hour
from game.property_runtime import (
    property_covering as _property_covering,
    property_focus_position as _property_focus_position,
    property_is_public as _property_is_public,
    property_is_storefront as _property_is_storefront,
    site_services_for_property as _site_services_for_property,
)
from game.systems_business_reputation import business_opinion_profile, social_secret_site_trust_gate
from game.system_support.container_runtime import _unlink_removed_item_from_gear
from game.system_support.interaction_ordering import _manhattan
from game.system_support.item_runtime import _apply_item_effects_to_entity
from game.movement_runtime import _is_traversable_for
from game.system_support.opportunity_knowledge_runtime import (
    best_opportunity_lead as _best_opportunity_lead,
    mark_opportunity_failure as _mark_opportunity_failure,
    nearby_opportunity_rows as _nearby_opportunity_rows,
    note_opportunity_success as _note_opportunity_success,
    remember_opportunity_lead as _remember_opportunity_lead,
)
from game.system_support.item_provenance_runtime import item_entitlement_for_actor, stamp_item_provenance
from game.system_support.npc_income_runtime import (
    inventory_liquid_credits as _shared_inventory_liquid_credits,
    spend_npc_wallet_credits as _shared_spend_npc_wallet_credits,
)


BEHAVIOR_COLLECT_GROUND_CREDITS = "collect_ground_credits"
BEHAVIOR_SCAVENGE_LOOSE_ITEMS = "scavenge_loose_items"
BEHAVIOR_SELL_SCAVENGED_ITEMS = "sell_scavenged_items"
BEHAVIOR_APPRAISE_STREET_GOODS = "appraise_street_goods"
BEHAVIOR_BUY_DESIRED_DRUG = "buy_desired_drug"
BEHAVIOR_BUY_PLAYER_GOODS = "buy_player_goods"
BEHAVIOR_BUY_PROVISIONS = "buy_provisions"
BEHAVIOR_BUY_PRACTICAL_GEAR = "buy_practical_gear"
BEHAVIOR_BUY_QUIRKY_ITEMS = "buy_quirky_items"
BEHAVIOR_IDENTIFY_STREET_DRUGS = "identify_street_drugs"
BEHAVIOR_INITIATE_DIALOGUE = "initiate_dialogue"
BEHAVIOR_AVOID_THREAT = "avoid_threat"
BEHAVIOR_AVOID_AUTHORITIES = "avoid_authorities"
BEHAVIOR_ENFORCE_JUSTICE = "enforce_justice"
BEHAVIOR_PROTECT_ALLIES = "protect_allies"
BEHAVIOR_SEEK_SOCIAL_CONTACT = "seek_social_contact"
BEHAVIOR_SEEK_MEDICAL_AID = "seek_medical_aid"
BEHAVIOR_SEEK_SHELTER = "seek_shelter"
BEHAVIOR_FOLLOW_DUTY = "follow_duty"
BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME = "commit_opportunistic_crime"
BEHAVIOR_COMMIT_PLANNED_CRIME = "commit_planned_crime"
BEHAVIOR_SEEK_CRIMINAL_AFFILIATION = "seek_criminal_affiliation"

_PUBLIC_GROUND_OWNER_TAGS = {None, "", "public", "unowned", "city"}
_PUBLIC_PROPERTY_OWNER_TAGS = {"", "public", "unowned", "none", "neutral"}
_SALVAGE_ARCHETYPES = frozenset({
    "pawn_shop",
    "chop_shop",
    "junk_market",
    "salvage_camp",
    "breaker_yard",
    "drydock_yard",
})
_THRIFT_ARCHETYPES = frozenset({
    "thrift_store",
})
_SCAVENGE_SALE_ARCHETYPES = _SALVAGE_ARCHETYPES | _THRIFT_ARCHETYPES | frozenset({"backroom_market"})
_NIGHTLIFE_ARCHETYPES = frozenset({
    "nightclub",
    "bar",
    "music_venue",
    "gaming_hall",
    "arcade",
    "theater",
    "karaoke_box",
    "pool_hall",
})
_SOCIAL_VENUE_ARCHETYPES = _NIGHTLIFE_ARCHETYPES | frozenset({
    "cafe",
    "restaurant",
    "diner",
    "tavern",
    "lounge",
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
_FOOD_VENUE_ARCHETYPES = frozenset({
    "cafe",
    "restaurant",
    "diner",
    "street_kitchen",
    "food_cart",
    "market",
    "tavern",
    "bar",
    "lounge",
})
_DRINK_VENUE_ARCHETYPES = frozenset({
    "cafe",
    "restaurant",
    "diner",
    "street_kitchen",
    "food_cart",
    "market",
    "tavern",
    "bar",
    "lounge",
    "nightclub",
    "music_venue",
    "karaoke_box",
    "pool_hall",
})
_DRUG_IDENTIFICATION_CAREERS = frozenset({
    "broker",
    "dealer",
    "pawnbroker",
    "pharmacist",
    "street_doc",
})
_SCAVENGEABLE_ITEM_CATEGORIES = frozenset({
    "consumable",
    "medical",
    "weapon",
    "armor",
    "tool",
    "token",
    "device",
})
_SCAVENGEABLE_ITEM_TAGS = frozenset({
    "food",
    "drink",
    "medical",
    "stimulant",
    "drug",
    "token",
    "weapon",
    "armor",
    "tool",
    "device",
    "ammo",
    "communication",
})
_STREET_BUY_CAREER_TOKENS = (
    "dealer",
    "broker",
    "fence",
    "pawn",
    "vendor",
    "scav",
    "fixer",
    "street_doc",
)
_PUSHER_CAREER_TOKENS = (
    "dealer",
    "pusher",
    "street_dealer",
)
_STREET_BUY_ARCHETYPES = frozenset({
    "pawn_shop",
    "junk_market",
    "chop_shop",
    "backroom_clinic",
    "nightclub",
    "bar",
    "gaming_hall",
    "street_kitchen",
})
_MEDICAL_ARCHETYPES = frozenset({
    "backroom_clinic",
    "pharmacy",
    "biotech_clinic",
    "field_hospital",
    "tide_station",
    "herbalist_camp",
    "herbalist_shop",
})
_SHELTER_CAREER_TOKENS = (
    "drifter",
    "vagrant",
    "homeless",
    "runaway",
    "squatter",
    "displaced",
)
_AUTHORITY_ROLES = frozenset({
    "guard",
    "scout",
})
_LODGING_SERVICE_IDS = frozenset({"rest", "shelter"})
_LODGING_TARGET_CACHE_TICKS = 3
_LODGING_TARGET_CACHE_JITTER = 2
_STREET_BUY_DEFAULT_CATEGORIES = frozenset({
    "tool",
    "weapon",
    "armor",
    "medical",
    "device",
    "token",
})
_STREET_BUY_DEFAULT_TAGS = frozenset({
    "tool",
    "weapon",
    "armor",
    "medical",
    "stimulant",
    "drug",
    "communication",
    "ammo",
})
_SHOPPING_ROLE_GEAR_TOKENS = (
    "guard",
    "security",
    "patrol",
    "officer",
    "scout",
    "medic",
    "doctor",
    "nurse",
    "pharmacist",
    "mechanic",
    "engineer",
    "technician",
    "courier",
    "runner",
    "scav",
    "fence",
    "dealer",
)
_SHOPPING_QUIRK_PROFILES = {
    "caffeine": {
        "tags": frozenset({"drink", "stimulant", "energy", "social"}),
        "item_ids": frozenset({"spark_brew", "caff_shot", "focus_inhaler", "synth_focus_tabs"}),
        "label": "caffeine",
    },
    "hats": {
        "tags": frozenset({"hat", "headwear", "appearance", "cosmetic", "clothing"}),
        "item_ids": frozenset(),
        "label": "appearance",
    },
    "tools": {
        "tags": frozenset({"tool", "device", "communication"}),
        "item_ids": frozenset({"pocket_notebook", "phone", "burner_phone"}),
        "label": "tools",
    },
    "medical_prepper": {
        "tags": frozenset({"medical", "safety"}),
        "item_ids": frozenset({"med_gel", "micro_medkit", "hydration_salts", "trauma_foam"}),
        "label": "medical prep",
    },
    "tokens": {
        "tags": frozenset({"token", "novelty", "game", "social"}),
        "item_ids": frozenset({"city_pass_token", "transit_daypass", "scratch_ticket", "deck_of_cards"}),
        "label": "novelties",
    },
    "weapons": {
        "tags": frozenset({"weapon", "ammo"}),
        "item_ids": frozenset(),
        "label": "weapons",
    },
}


def _seed_pusher_vendor_preferences(behaviors, preferences, *, seed_token="", role="", career="", archetypes=frozenset()):
    career_key = _behavior_token(career)
    role_key = _behavior_token(role)
    explicit_pusher = any(token in career_key for token in _PUSHER_CAREER_TOKENS)
    rare_context = bool(archetypes & (_NIGHTLIFE_ARCHETYPES | frozenset({"backroom_market", "flophouse"})))
    rare_roll = 1.0
    if rare_context and role_key not in _AUTHORITY_ROLES:
        rng = random.Random(f"{seed_token}:street-pusher:{role_key}:{career_key}:{','.join(sorted(archetypes))}")
        rare_roll = rng.random()
    if not explicit_pusher and not (rare_context and rare_roll < 0.075):
        return
    _seed_behavior(behaviors, BEHAVIOR_BUY_DESIRED_DRUG, 0.76 if explicit_pusher else 0.64)
    _seed_behavior(behaviors, BEHAVIOR_INITIATE_DIALOGUE, 0.34)
    _seed_behavior(behaviors, BEHAVIOR_AVOID_AUTHORITIES, 0.54)
    _seed_behavior(behaviors, BEHAVIOR_APPRAISE_STREET_GOODS, 0.44)
    preferences.setdefault("street_vendor_kind", "drug_pusher")
    preferences.setdefault("street_vendor_modes", ("buy",))
    preferences.setdefault("street_stock_theme", "drugs")
    preferences.setdefault("street_stock_count", 3 if explicit_pusher else 2)
    preferences.setdefault("heat_tolerance", "low")
    preferences.setdefault("authority_avoid_radius", 9)
    preferences.setdefault("initiate_dialogue_cooldown", 300)


_SHOPPING_QUIRK_ORDER = tuple(sorted(_SHOPPING_QUIRK_PROFILES))
_STREET_ITEM_VALUE = {
    "weapon": 46,
    "firearm": 46,
    "launcher": 74,
    "armor": 30,
    "tool": 24,
    "device": 20,
    "communication": 20,
    "medical": 20,
    "ammo": 18,
    "token": 10,
    "access": 28,
    "stimulant": 22,
    "drug": 24,
}
_STREET_ITEM_OVERRIDES = {
    "cocaine_bindle": 32,
    "mdma_capsule": 30,
    "lsd_blotter": 26,
    "black_market_stim": 28,
    "methamphetamine": 34,
    "fentanyl_patch": 30,
    "ketamine_vial": 30,
    "heroin_syringe": 32,
}
_STREET_DEFAULT_VALUE = 14
_SCAVENGE_CATEGORY_VALUES = {
    "consumable": 9.0,
    "medical": 17.0,
    "weapon": 28.0,
    "armor": 22.0,
    "tool": 20.0,
    "token": 12.0,
    "device": 18.0,
}
_SCAVENGE_SALE_PAYOUT_MULTS = {
    "pawn_shop": 0.56,
    "chop_shop": 0.54,
    "junk_market": 0.52,
    "salvage_camp": 0.46,
    "breaker_yard": 0.48,
    "drydock_yard": 0.48,
    "thrift_store": 0.5,
    "backroom_market": 0.64,
}
_REST_SERVICE_COST = 25
RARE_EXTRA_BEHAVIOR_CHANCE = 0.02
_RARE_EXTRA_BEHAVIOR_WEIGHTS = (
    (BEHAVIOR_BUY_DESIRED_DRUG, 8, 0.22, 0.38),
    (BEHAVIOR_IDENTIFY_STREET_DRUGS, 5, 0.16, 0.28),
    (BEHAVIOR_APPRAISE_STREET_GOODS, 6, 0.18, 0.3),
    (BEHAVIOR_BUY_PLAYER_GOODS, 5, 0.18, 0.3),
    (BEHAVIOR_INITIATE_DIALOGUE, 4, 0.14, 0.24),
    (BEHAVIOR_COLLECT_GROUND_CREDITS, 6, 0.2, 0.34),
    (BEHAVIOR_SCAVENGE_LOOSE_ITEMS, 5, 0.18, 0.32),
    (BEHAVIOR_SELL_SCAVENGED_ITEMS, 4, 0.16, 0.26),
    (BEHAVIOR_AVOID_THREAT, 5, 0.18, 0.32),
    (BEHAVIOR_AVOID_AUTHORITIES, 5, 0.16, 0.3),
    (BEHAVIOR_ENFORCE_JUSTICE, 5, 0.18, 0.32),
    (BEHAVIOR_PROTECT_ALLIES, 5, 0.18, 0.32),
    (BEHAVIOR_SEEK_SOCIAL_CONTACT, 5, 0.18, 0.32),
    (BEHAVIOR_SEEK_MEDICAL_AID, 5, 0.18, 0.32),
    (BEHAVIOR_SEEK_SHELTER, 5, 0.18, 0.32),
    (BEHAVIOR_FOLLOW_DUTY, 5, 0.18, 0.32),
    (BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME, 3, 0.12, 0.24),
    (BEHAVIOR_COMMIT_PLANNED_CRIME, 2, 0.1, 0.2),
    (BEHAVIOR_SEEK_CRIMINAL_AFFILIATION, 3, 0.12, 0.24),
)


def _behavior_token(value):
    return str(value or "").strip().lower()


def _clamp_behavior_value(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return float(max(0.0, min(1.0, number)))


def _clamp_need_value(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return float(max(0.0, min(100.0, number)))


def _item_positive_need_delta(item_def, need):
    total = 0.0
    if not isinstance(item_def, dict):
        return 0.0
    for effect in tuple(item_def.get("effects", ()) or ()):
        if not isinstance(effect, dict) or str(effect.get("type", "")).strip().lower() != "modify_need":
            continue
        if str(effect.get("need", "")).strip().lower() != str(need).strip().lower():
            continue
        try:
            delta = float(effect.get("delta", 0.0) or 0.0)
        except (TypeError, ValueError):
            delta = 0.0
        if delta > 0.0:
            total += delta
    return float(total)


def _nutrition_capabilities_for_property(prop):
    if not isinstance(prop, dict):
        return {"food": False, "drink": False}
    metadata = prop.get("metadata", {}) if isinstance(prop.get("metadata"), dict) else {}
    archetype = _behavior_token(metadata.get("archetype"))
    services = {
        str(service or "").strip().lower()
        for service in _site_services_for_property(prop)
        if str(service or "").strip()
    }
    vending = "vending" in services
    return {
        "food": bool(archetype in _FOOD_VENUE_ARCHETYPES or vending),
        "drink": bool(archetype in _DRINK_VENUE_ARCHETYPES or vending),
    }


def _nutrition_item_score(item_def, need):
    tags = _item_tags(item_def)
    need = str(need or "").strip().lower()
    if need == "hunger":
        direct = _item_positive_need_delta(item_def, "hunger")
        if direct <= 0.0 and "food" not in tags:
            return 0.0
        return direct + (4.0 if "food" in tags else 0.0)
    if need == "thirst":
        direct = _item_positive_need_delta(item_def, "thirst")
        if direct <= 0.0 and "drink" not in tags:
            return 0.0
        return direct + (4.0 if "drink" in tags else 0.0)
    return 0.0


def _npc_nutrition_cooldowns(sim):
    cooldowns = getattr(sim, "npc_nutrition_cooldowns", None)
    if not isinstance(cooldowns, dict):
        cooldowns = {}
        setattr(sim, "npc_nutrition_cooldowns", cooldowns)
    return cooldowns


def _npc_try_consume_nutrition(sim, actor_eid, needs, *, low_threshold=45.0, cooldown_ticks=180):
    if sim is None or needs is None:
        return None
    try:
        actor_eid = int(actor_eid)
    except (TypeError, ValueError):
        return None
    if actor_eid == getattr(sim, "player_eid", None):
        return None

    vitality = sim.ecs.get(Vitality).get(actor_eid)
    if vitality is not None and bool(getattr(vitality, "downed", False)):
        return None
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if inventory is None or not getattr(inventory, "items", None):
        return None

    hunger = _clamp_need_value(getattr(needs, "hunger", 100.0))
    thirst = _clamp_need_value(getattr(needs, "thirst", 100.0))
    need_rows = []
    if hunger < float(low_threshold):
        need_rows.append(("hunger", float(low_threshold) - hunger))
    if thirst < float(low_threshold):
        need_rows.append(("thirst", float(low_threshold) - thirst))
    if not need_rows:
        return None
    need_rows.sort(key=lambda row: row[1], reverse=True)

    current_tick = int(getattr(sim, "tick", 0) or 0)
    cooldowns = _npc_nutrition_cooldowns(sim).setdefault(actor_eid, {})
    for need, _urgency in need_rows:
        try:
            if current_tick < int(cooldowns.get(need, 0) or 0):
                continue
        except (TypeError, ValueError):
            pass
        candidates = []
        for entry in list(getattr(inventory, "items", ()) or ()):
            item_id = str(entry.get("item_id", "") or "").strip()
            item_def = ITEM_CATALOG.get(item_id)
            score = _nutrition_item_score(item_def, need)
            if score <= 0.0:
                continue
            candidates.append((score, item_id, entry, item_def))
        if not candidates:
            continue
        candidates.sort(key=lambda row: (row[0], row[1]), reverse=True)
        _score, item_id, entry, item_def = candidates[0]
        before_value = _clamp_need_value(getattr(needs, need, 0.0))
        if sim.ecs.get(StatusEffects).get(actor_eid) is None:
            sim.ecs.add(actor_eid, StatusEffects())
        applied = _apply_item_effects_to_entity(
            sim,
            actor_eid,
            item_def,
            item_metadata=entry.get("metadata") if isinstance(entry, dict) else None,
        )
        if not applied:
            continue
        removed = inventory.remove_item(instance_id=entry.get("instance_id"), quantity=1)
        if not removed:
            continue
        after_value = _clamp_need_value(getattr(needs, need, before_value))
        cooldowns[need] = current_tick + int(max(1, cooldown_ticks))
        sim.emit(Event(
            "npc_nutrition_consumed",
            npc_eid=actor_eid,
            item_id=item_id,
            item_name=item_display_name(item_id),
            need=need,
            before=round(before_value, 2),
            after=round(after_value, 2),
            applied=tuple(applied),
        ))
        return {
            "need": need,
            "item_id": item_id,
            "before": before_value,
            "after": after_value,
            "applied": tuple(applied),
        }
    return None


def _receive_nutrition_at_actor(sim, actor_eid, pos, *, prop=None, redeem_meal_voucher=False):
    if sim is None or pos is None:
        return None
    try:
        actor_eid = int(actor_eid)
    except (TypeError, ValueError):
        return None
    if prop is None:
        prop = _property_covering(sim, pos.x, pos.y, pos.z)
    if not isinstance(prop, dict):
        return None
    caps = _nutrition_capabilities_for_property(prop)
    if not caps.get("food") and not caps.get("drink"):
        return None
    needs = sim.ecs.get(NPCNeeds).get(actor_eid)
    if needs is None:
        return None
    before_hunger = _clamp_need_value(getattr(needs, "hunger", 100.0))
    before_thirst = _clamp_need_value(getattr(needs, "thirst", 100.0))
    changed = {}
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    voucher_redeemed = False
    if bool(redeem_meal_voucher) and caps.get("food") and inventory is not None and before_hunger < 90.0:
        voucher = inventory.find(item_id="meal_voucher")
        if voucher:
            removed = inventory.remove_item(instance_id=voucher.get("instance_id"), quantity=1)
            voucher_redeemed = bool(removed)
    hunger_gain = 38.0 if voucher_redeemed else 22.0
    thirst_gain = 10.0 if voucher_redeemed else 24.0
    if caps.get("food") and (before_hunger < 72.0 or voucher_redeemed):
        needs.hunger = _clamp_need_value(before_hunger + hunger_gain)
        changed["hunger"] = (before_hunger, needs.hunger)
    if caps.get("drink") and before_thirst < 76.0:
        needs.thirst = _clamp_need_value(before_thirst + thirst_gain)
        changed["thirst"] = (before_thirst, needs.thirst)
    if changed and hasattr(needs, "social"):
        needs.social = _clamp_need_value(float(getattr(needs, "social", 0.0) or 0.0) + 0.4)
    if not changed:
        return None
    credits_cost = 0
    if not voucher_redeemed:
        if "hunger" in changed:
            credits_cost += 2
        if "thirst" in changed:
            credits_cost += 1
    credits_spent = 0
    if credits_cost > 0:
        credits_spent = _spend_inventory_credits(inventory, credits_cost) if inventory is not None else 0
        if credits_spent < credits_cost:
            if "hunger" in changed:
                needs.hunger = before_hunger
            if "thirst" in changed:
                needs.thirst = before_thirst
            sim.emit(Event(
                "npc_nutrition_unpaid",
                npc_eid=actor_eid,
                property_id=str(prop.get("id", "") or "").strip() or None,
                property_name=str(prop.get("name", "") or "").strip(),
                credits_cost=int(credits_cost),
                credits_spent=int(credits_spent),
                hunger=round(before_hunger, 2),
                thirst=round(before_thirst, 2),
            ))
            return None

    statuses = sim.ecs.get(StatusEffects).get(actor_eid)
    if statuses is None:
        statuses = StatusEffects()
        sim.ecs.add(actor_eid, statuses)
    statuses.add(
        status="voucher_meal" if voucher_redeemed else "shared_meal" if changed.get("hunger") else "shared_drink",
        duration=18,
        modifiers={
            "hp_tick_delta": 0.1 if voucher_redeemed else 0.06,
            "energy_tick_delta": 0.035 if voucher_redeemed else 0.025,
            "safety_tick_delta": 0.02 if voucher_redeemed else 0.015,
        },
        source_item=None,
    )
    prop_id = str(prop.get("id", "") or "").strip()
    sim.emit(Event(
        "npc_nutrition_shared",
        npc_eid=actor_eid,
        property_id=prop_id or None,
        property_name=str(prop.get("name", "") or "").strip(),
        hunger_before=round(before_hunger, 2),
        hunger_after=round(_clamp_need_value(getattr(needs, "hunger", before_hunger)), 2),
        thirst_before=round(before_thirst, 2),
        thirst_after=round(_clamp_need_value(getattr(needs, "thirst", before_thirst)), 2),
        source="social_venue",
        meal_voucher_redeemed=bool(voucher_redeemed),
        credits_cost=int(credits_cost),
        credits_spent=int(credits_spent),
    ))
    return {
        "property_id": prop_id or None,
        "changed": dict(changed),
    }


def _npc_behavior_runtime_cache(sim, *, current_tick=None):
    if current_tick is None:
        current_tick = getattr(sim, "tick", 0)
    try:
        tick = int(current_tick)
    except (TypeError, ValueError):
        tick = int(getattr(sim, "tick", 0) or 0)
    state = getattr(sim, "npc_behavior_runtime_cache", None)
    if not isinstance(state, dict) or int(state.get("tick", -1) or -1) != tick:
        state = {
            "tick": tick,
            "property_access": {},
        }
        sim.npc_behavior_runtime_cache = state
    return state


def _npc_behavior_search_cache(sim):
    state = getattr(sim, "npc_behavior_search_cache", None)
    if not isinstance(state, dict):
        state = {
            "lodging_targets": {},
        }
        sim.npc_behavior_search_cache = state
    state.setdefault("lodging_targets", {})
    return state


def _cached_behavior_property_access(sim, actor_eid, prop, *, x=None, y=None, z=None):
    if not isinstance(prop, dict):
        return _evaluate_property_access(sim, actor_eid, prop, x=x, y=y, z=z)
    property_id = str(prop.get("id", "") or "").strip()
    if not property_id:
        return _evaluate_property_access(sim, actor_eid, prop, x=x, y=y, z=z)
    cache = _npc_behavior_runtime_cache(sim).setdefault("property_access", {})
    key = (
        int(actor_eid) if actor_eid is not None else 0,
        property_id,
        int(x) if x is not None else None,
        int(y) if y is not None else None,
        int(z) if z is not None else None,
    )
    cached = cache.get(key)
    if cached is not None:
        return cached
    result = _evaluate_property_access(sim, actor_eid, prop, x=x, y=y, z=z)
    cache[key] = result
    return result


def _preferred_hidden_contact_match(prop, preferred_property_id, *, hidden_kind=""):
    property_id = str((prop or {}).get("id", "") or "").strip()
    preferred_property_id = str(preferred_property_id or "").strip()
    if not property_id or not preferred_property_id or property_id != preferred_property_id:
        return False
    metadata = (prop.get("metadata") or {}) if isinstance(prop, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    actual_kind = _behavior_token(metadata.get("hidden_contact_kind") or metadata.get("archetype"))
    expected_kind = _behavior_token(hidden_kind)
    if expected_kind:
        return actual_kind == expected_kind
    return actual_kind in {"backroom_market", "backroom_clinic"}


def _seed_behavior(behaviors, name, value):
    token = _behavior_token(name)
    if not token:
        return 0.0
    amount = _clamp_behavior_value(value)
    if amount <= 0.0:
        return float(behaviors.get(token, 0.0) or 0.0)
    current = float(behaviors.get(token, 0.0) or 0.0)
    behaviors[token] = max(current, amount)
    return float(behaviors[token])


def _roll_rare_spawn_behavior(behaviors, preferences, *, seed_token="", role="", career="", archetypes=()):
    clean_seed = str(seed_token or "").strip()
    if not clean_seed:
        return None

    rng = random.Random(
        "rare-npc-behavior:"
        f"{clean_seed}:{_behavior_token(role)}:{_behavior_token(career)}:{','.join(sorted(archetypes or ())) or 'none'}"
    )
    if rng.random() >= RARE_EXTRA_BEHAVIOR_CHANCE:
        return None

    options = []
    total_weight = 0
    for name, weight, low, high in _RARE_EXTRA_BEHAVIOR_WEIGHTS:
        token = _behavior_token(name)
        if not token:
            continue
        current = _clamp_behavior_value(behaviors.get(token, 0.0), default=0.0)
        if current >= 0.18:
            continue
        try:
            clean_weight = int(weight)
        except (TypeError, ValueError):
            continue
        if clean_weight <= 0:
            continue
        options.append((token, clean_weight, float(low), float(high)))
        total_weight += clean_weight
    if total_weight <= 0:
        return None

    pick = rng.randrange(total_weight)
    cursor = 0
    chosen = None
    for token, weight, low, high in options:
        cursor += weight
        if pick < cursor:
            chosen = (token, low, high)
            break
    if chosen is None:
        token, _weight, low, high = options[-1]
    else:
        token, low, high = chosen

    amount = round(rng.uniform(low, max(low, high)), 2)
    _seed_behavior(behaviors, token, amount)
    preferences["rare_extra_behavior"] = token
    preferences["rare_extra_behavior_value"] = float(behaviors.get(token, amount))
    if token in {
        BEHAVIOR_COLLECT_GROUND_CREDITS,
        BEHAVIOR_SCAVENGE_LOOSE_ITEMS,
        BEHAVIOR_SELL_SCAVENGED_ITEMS,
    }:
        preferences["ground_credit_search_radius"] = max(
            int(preferences.get("ground_credit_search_radius", 0) or 0),
            4,
        )
    if token == BEHAVIOR_SCAVENGE_LOOSE_ITEMS:
        preferences["ground_item_search_radius"] = max(
            int(preferences.get("ground_item_search_radius", 0) or 0),
            4,
        )
    if token == BEHAVIOR_SEEK_SHELTER:
        preferences["shelter_search_radius"] = max(
            int(preferences.get("shelter_search_radius", 0) or 0),
            8,
        )
    return token


def _seed_shopping_preferences(behaviors, preferences, *, seed_token="", role="", career="", archetypes=()):
    role = _behavior_token(role) or "civilian"
    career = _behavior_token(career)
    archetypes = frozenset(_behavior_token(value) for value in tuple(archetypes or ()) if _behavior_token(value))

    _seed_behavior(behaviors, BEHAVIOR_BUY_PROVISIONS, 0.48)
    practical = 0.22
    if role in {"guard", "scout", "worker"}:
        practical += 0.18
    if any(token in career for token in _SHOPPING_ROLE_GEAR_TOKENS):
        practical += 0.24
    if archetypes & (_MEDICAL_ARCHETYPES | _SALVAGE_ARCHETYPES | _THRIFT_ARCHETYPES):
        practical += 0.16
    if archetypes & _NIGHTLIFE_ARCHETYPES:
        _seed_behavior(behaviors, BEHAVIOR_BUY_PROVISIONS, 0.56)
    _seed_behavior(behaviors, BEHAVIOR_BUY_PRACTICAL_GEAR, min(0.82, practical))

    clean_seed = str(seed_token or "").strip()
    if not clean_seed:
        return None
    rng = random.Random(
        "npc-shopping:"
        f"{clean_seed}:{role}:{career}:{','.join(sorted(archetypes)) or 'none'}"
    )
    quirky = rng.random() < 0.12
    impulsive = rng.random() < 0.02
    if not quirky and not impulsive:
        return None
    quirk_id = _SHOPPING_QUIRK_ORDER[rng.randrange(len(_SHOPPING_QUIRK_ORDER))]
    preferences["shopping_quirk_id"] = quirk_id
    preferences["shopping_quirk_label"] = _SHOPPING_QUIRK_PROFILES.get(quirk_id, {}).get("label", quirk_id)
    preferences["shopping_impulsive"] = bool(impulsive)
    preferences["shopping_impulse_cooldown_ticks"] = 3600
    preferences["shopping_search_radius"] = max(int(preferences.get("shopping_search_radius", 0) or 0), 10)
    _seed_behavior(behaviors, BEHAVIOR_BUY_QUIRKY_ITEMS, 0.76 if impulsive else 0.34)
    return quirk_id


def behavior_profile_for_spawn(*, role="", career="", workplace_archetype="", home_archetype="", seed_token=""):
    role_key = _behavior_token(role) or "civilian"
    career_key = _behavior_token(career)
    archetypes = {
        _behavior_token(workplace_archetype),
        _behavior_token(home_archetype),
    }
    archetypes.discard("")

    behaviors = {}
    preferences = {}

    role_behavior_defaults = {
        "guard": {
            BEHAVIOR_AVOID_THREAT: 0.22,
            BEHAVIOR_AVOID_AUTHORITIES: 0.02,
            BEHAVIOR_ENFORCE_JUSTICE: 0.95,
            BEHAVIOR_PROTECT_ALLIES: 0.84,
            BEHAVIOR_SEEK_SOCIAL_CONTACT: 0.18,
            BEHAVIOR_SEEK_MEDICAL_AID: 0.18,
            BEHAVIOR_SEEK_SHELTER: 0.08,
            BEHAVIOR_FOLLOW_DUTY: 0.94,
            BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME: 0.0,
            BEHAVIOR_COMMIT_PLANNED_CRIME: 0.0,
            BEHAVIOR_SEEK_CRIMINAL_AFFILIATION: 0.0,
        },
        "scout": {
            BEHAVIOR_AVOID_THREAT: 0.26,
            BEHAVIOR_AVOID_AUTHORITIES: 0.04,
            BEHAVIOR_ENFORCE_JUSTICE: 0.82,
            BEHAVIOR_PROTECT_ALLIES: 0.72,
            BEHAVIOR_SEEK_SOCIAL_CONTACT: 0.22,
            BEHAVIOR_SEEK_MEDICAL_AID: 0.2,
            BEHAVIOR_SEEK_SHELTER: 0.1,
            BEHAVIOR_FOLLOW_DUTY: 0.84,
            BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME: 0.0,
            BEHAVIOR_COMMIT_PLANNED_CRIME: 0.0,
            BEHAVIOR_SEEK_CRIMINAL_AFFILIATION: 0.0,
        },
        "worker": {
            BEHAVIOR_AVOID_THREAT: 0.42,
            BEHAVIOR_AVOID_AUTHORITIES: 0.12,
            BEHAVIOR_ENFORCE_JUSTICE: 0.48,
            BEHAVIOR_PROTECT_ALLIES: 0.42,
            BEHAVIOR_SEEK_SOCIAL_CONTACT: 0.44,
            BEHAVIOR_SEEK_MEDICAL_AID: 0.26,
            BEHAVIOR_SEEK_SHELTER: 0.18,
            BEHAVIOR_FOLLOW_DUTY: 0.76,
            BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME: 0.04,
            BEHAVIOR_COMMIT_PLANNED_CRIME: 0.02,
            BEHAVIOR_SEEK_CRIMINAL_AFFILIATION: 0.04,
        },
        "civilian": {
            BEHAVIOR_AVOID_THREAT: 0.55,
            BEHAVIOR_AVOID_AUTHORITIES: 0.18,
            BEHAVIOR_ENFORCE_JUSTICE: 0.32,
            BEHAVIOR_PROTECT_ALLIES: 0.34,
            BEHAVIOR_SEEK_SOCIAL_CONTACT: 0.56,
            BEHAVIOR_SEEK_MEDICAL_AID: 0.34,
            BEHAVIOR_SEEK_SHELTER: 0.36,
            BEHAVIOR_FOLLOW_DUTY: 0.24,
            BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME: 0.06,
            BEHAVIOR_COMMIT_PLANNED_CRIME: 0.02,
            BEHAVIOR_SEEK_CRIMINAL_AFFILIATION: 0.06,
        },
        "resident": {
            BEHAVIOR_AVOID_THREAT: 0.48,
            BEHAVIOR_AVOID_AUTHORITIES: 0.16,
            BEHAVIOR_ENFORCE_JUSTICE: 0.28,
            BEHAVIOR_PROTECT_ALLIES: 0.48,
            BEHAVIOR_SEEK_SOCIAL_CONTACT: 0.6,
            BEHAVIOR_SEEK_MEDICAL_AID: 0.38,
            BEHAVIOR_SEEK_SHELTER: 0.28,
            BEHAVIOR_FOLLOW_DUTY: 0.18,
            BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME: 0.04,
            BEHAVIOR_COMMIT_PLANNED_CRIME: 0.02,
            BEHAVIOR_SEEK_CRIMINAL_AFFILIATION: 0.04,
        },
        "thief": {
            BEHAVIOR_AVOID_THREAT: 0.74,
            BEHAVIOR_AVOID_AUTHORITIES: 0.82,
            BEHAVIOR_ENFORCE_JUSTICE: 0.08,
            BEHAVIOR_PROTECT_ALLIES: 0.22,
            BEHAVIOR_SEEK_SOCIAL_CONTACT: 0.28,
            BEHAVIOR_SEEK_MEDICAL_AID: 0.18,
            BEHAVIOR_SEEK_SHELTER: 0.44,
            BEHAVIOR_FOLLOW_DUTY: 0.12,
            BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME: 0.9,
            BEHAVIOR_COMMIT_PLANNED_CRIME: 0.56,
            BEHAVIOR_SEEK_CRIMINAL_AFFILIATION: 0.44,
        },
        "drunk": {
            BEHAVIOR_AVOID_THREAT: 0.68,
            BEHAVIOR_AVOID_AUTHORITIES: 0.58,
            BEHAVIOR_ENFORCE_JUSTICE: 0.12,
            BEHAVIOR_PROTECT_ALLIES: 0.18,
            BEHAVIOR_SEEK_SOCIAL_CONTACT: 0.74,
            BEHAVIOR_SEEK_MEDICAL_AID: 0.42,
            BEHAVIOR_SEEK_SHELTER: 0.78,
            BEHAVIOR_FOLLOW_DUTY: 0.06,
            BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME: 0.18,
            BEHAVIOR_COMMIT_PLANNED_CRIME: 0.02,
            BEHAVIOR_SEEK_CRIMINAL_AFFILIATION: 0.08,
        },
    }
    for name, value in role_behavior_defaults.get(
        role_key,
        {
            BEHAVIOR_AVOID_THREAT: 0.5,
            BEHAVIOR_AVOID_AUTHORITIES: 0.14,
            BEHAVIOR_ENFORCE_JUSTICE: 0.3,
            BEHAVIOR_PROTECT_ALLIES: 0.35,
            BEHAVIOR_SEEK_SOCIAL_CONTACT: 0.45,
            BEHAVIOR_SEEK_MEDICAL_AID: 0.24,
            BEHAVIOR_SEEK_SHELTER: 0.24,
            BEHAVIOR_FOLLOW_DUTY: 0.28,
            BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME: 0.04,
            BEHAVIOR_COMMIT_PLANNED_CRIME: 0.02,
            BEHAVIOR_SEEK_CRIMINAL_AFFILIATION: 0.04,
        },
    ).items():
        _seed_behavior(behaviors, name, value)

    if role_key == "thief":
        _seed_behavior(behaviors, BEHAVIOR_COLLECT_GROUND_CREDITS, 0.95)
        _seed_behavior(behaviors, BEHAVIOR_SCAVENGE_LOOSE_ITEMS, 0.88)
        _seed_behavior(behaviors, BEHAVIOR_SELL_SCAVENGED_ITEMS, 0.82)
        _seed_behavior(behaviors, BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME, 0.95)
        _seed_behavior(behaviors, BEHAVIOR_COMMIT_PLANNED_CRIME, 0.62)
        preferences["ground_credit_search_radius"] = 8
    elif role_key == "drunk":
        _seed_behavior(behaviors, BEHAVIOR_COLLECT_GROUND_CREDITS, 0.56)
        preferences["ground_credit_search_radius"] = 5
        preferences["shelter_search_radius"] = max(
            int(preferences.get("shelter_search_radius", 0) or 0),
            10,
        )

    if archetypes & _SALVAGE_ARCHETYPES:
        _seed_behavior(behaviors, BEHAVIOR_COLLECT_GROUND_CREDITS, 0.76)
        _seed_behavior(behaviors, BEHAVIOR_SCAVENGE_LOOSE_ITEMS, 0.82)
        _seed_behavior(behaviors, BEHAVIOR_SELL_SCAVENGED_ITEMS, 0.9)
        _seed_behavior(behaviors, BEHAVIOR_APPRAISE_STREET_GOODS, 0.72)
        _seed_behavior(behaviors, BEHAVIOR_BUY_PLAYER_GOODS, 0.78)
        preferences["ground_credit_search_radius"] = max(
            int(preferences.get("ground_credit_search_radius", 0) or 0),
            7,
        )
    if archetypes & _THRIFT_ARCHETYPES:
        _seed_behavior(behaviors, BEHAVIOR_SCAVENGE_LOOSE_ITEMS, 0.34)
        _seed_behavior(behaviors, BEHAVIOR_SELL_SCAVENGED_ITEMS, 0.78)
        _seed_behavior(behaviors, BEHAVIOR_APPRAISE_STREET_GOODS, 0.66)
        _seed_behavior(behaviors, BEHAVIOR_BUY_PLAYER_GOODS, 0.58)
        preferences["ground_item_search_radius"] = max(
            int(preferences.get("ground_item_search_radius", 0) or 0),
            5,
        )
    if archetypes & _NIGHTLIFE_ARCHETYPES:
        _seed_behavior(behaviors, BEHAVIOR_COLLECT_GROUND_CREDITS, 0.46)
        _seed_behavior(behaviors, BEHAVIOR_BUY_DESIRED_DRUG, 0.68)
        _seed_behavior(behaviors, BEHAVIOR_APPRAISE_STREET_GOODS, 0.38)
        _seed_behavior(behaviors, BEHAVIOR_INITIATE_DIALOGUE, 0.34)
        _seed_behavior(behaviors, BEHAVIOR_AVOID_AUTHORITIES, 0.34)
        preferences["ground_credit_search_radius"] = max(
            int(preferences.get("ground_credit_search_radius", 0) or 0),
            6,
        )
    if archetypes & _MEDICAL_ARCHETYPES:
        _seed_behavior(behaviors, BEHAVIOR_SEEK_MEDICAL_AID, 0.58)
        preferences["medical_aid_search_radius"] = max(
            int(preferences.get("medical_aid_search_radius", 0) or 0),
            10,
        )
    if "ruin_shelter" in archetypes:
        _seed_behavior(behaviors, BEHAVIOR_SEEK_SHELTER, 0.68)
        preferences["shelter_search_radius"] = max(
            int(preferences.get("shelter_search_radius", 0) or 0),
            12,
        )

    if career_key in _DRUG_IDENTIFICATION_CAREERS or any(
        token in career_key
        for token in ("dealer", "pharmac", "chemist", "broker", "pawn")
    ):
        _seed_behavior(behaviors, BEHAVIOR_IDENTIFY_STREET_DRUGS, 0.85)
        _seed_behavior(behaviors, BEHAVIOR_APPRAISE_STREET_GOODS, 0.76)
        _seed_behavior(behaviors, BEHAVIOR_AVOID_AUTHORITIES, 0.28)

    if any(token in career_key for token in _STREET_BUY_CAREER_TOKENS):
        _seed_behavior(behaviors, BEHAVIOR_BUY_PLAYER_GOODS, 0.78)
        _seed_behavior(behaviors, BEHAVIOR_BUY_DESIRED_DRUG, 0.82)
        _seed_behavior(behaviors, BEHAVIOR_INITIATE_DIALOGUE, 0.46)
        _seed_behavior(behaviors, BEHAVIOR_AVOID_AUTHORITIES, 0.44)
        _seed_behavior(behaviors, BEHAVIOR_COMMIT_PLANNED_CRIME, 0.44)

    if any(token in career_key for token in ("thief", "runner", "dealer", "fence", "drifter", "scav", "fixer")):
        _seed_behavior(behaviors, BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME, 0.52)
        _seed_behavior(behaviors, BEHAVIOR_SEEK_CRIMINAL_AFFILIATION, 0.42)

    if any(token in career_key for token in ("dealer", "runner", "fence", "fixer", "lookout", "smuggler")):
        _seed_behavior(behaviors, BEHAVIOR_COMMIT_PLANNED_CRIME, 0.58)

    if any(token in career_key for token in _SHELTER_CAREER_TOKENS) or "runaway" in career_key:
        _seed_behavior(behaviors, BEHAVIOR_SEEK_CRIMINAL_AFFILIATION, 0.38)

    if any(token in career_key for token in _SHELTER_CAREER_TOKENS):
        _seed_behavior(behaviors, BEHAVIOR_SEEK_SHELTER, 0.86)
        preferences["shelter_search_radius"] = max(
            int(preferences.get("shelter_search_radius", 0) or 0),
            14,
        )

    if archetypes & _STREET_BUY_ARCHETYPES:
        _seed_behavior(behaviors, BEHAVIOR_BUY_PLAYER_GOODS, 0.68)
        _seed_behavior(behaviors, BEHAVIOR_APPRAISE_STREET_GOODS, 0.46)
        _seed_behavior(behaviors, BEHAVIOR_INITIATE_DIALOGUE, 0.26)
        _seed_behavior(behaviors, BEHAVIOR_AVOID_AUTHORITIES, 0.26)

    if _clamp_behavior_value(behaviors.get(BEHAVIOR_BUY_DESIRED_DRUG, 0.0), default=0.0) >= 0.6:
        _seed_behavior(behaviors, BEHAVIOR_INITIATE_DIALOGUE, 0.28)
        _seed_behavior(behaviors, BEHAVIOR_AVOID_AUTHORITIES, 0.24)
        preferences.setdefault("initiate_dialogue_cooldown", 240)
        preferences.setdefault("authority_avoid_radius", 8)

    _seed_pusher_vendor_preferences(
        behaviors,
        preferences,
        seed_token=seed_token,
        role=role_key,
        career=career_key,
        archetypes=archetypes,
    )

    _seed_shopping_preferences(
        behaviors,
        preferences,
        seed_token=seed_token,
        role=role_key,
        career=career_key,
        archetypes=archetypes,
    )

    _roll_rare_spawn_behavior(
        behaviors,
        preferences,
        seed_token=seed_token,
        role=role_key,
        career=career_key,
        archetypes=archetypes,
    )

    return BehaviorProfile(behaviors=behaviors, preferences=preferences)


def _actor_behavior_profile(sim, eid):
    return sim.ecs.get(BehaviorProfile).get(eid)


def _actor_behavior_tags(sim, eid):
    profile = _actor_behavior_profile(sim, eid)
    if not profile:
        return frozenset()
    return frozenset(
        _behavior_token(tag)
        for tag in profile.tags
        if _behavior_token(tag)
    )


def _actor_has_behavior(sim, eid, tag):
    token = _behavior_token(tag)
    if not token:
        return False
    profile = _actor_behavior_profile(sim, eid)
    if not profile:
        return False
    return profile.has(token)


def _actor_behavior_override_value(sim, eid, behavior):
    token = _behavior_token(behavior)
    if not token:
        return None
    profile = _actor_behavior_profile(sim, eid)
    if not profile:
        return None
    if token not in getattr(profile, "behaviors", {}):
        return None
    return _clamp_behavior_value(profile.get(token, 0.0), default=0.0)


def _actor_behavior_value(sim, eid, behavior, default=0.0):
    override = _actor_behavior_override_value(sim, eid, behavior)
    if override is not None:
        return override
    return _clamp_behavior_value(default)


def _effective_behavior_value(sim, eid, behavior, *, traits=None, needs=None, justice=None, vitality=None):
    token = _behavior_token(behavior)
    override = _actor_behavior_override_value(sim, eid, token)
    base = _clamp_behavior_value(override, default=0.0) if override is not None else None

    if token == BEHAVIOR_AVOID_THREAT:
        bravery = _clamp_behavior_value(getattr(traits, "bravery", 0.5), default=0.5)
        safety_gap = _clamp_behavior_value(
            (100.0 - float(getattr(needs, "safety", 75.0) or 75.0)) / 100.0,
            default=0.25,
        )
        situational = _clamp_behavior_value(((1.0 - bravery) * 0.7) + (safety_gap * 0.3))
        if base is None:
            return situational
        return _clamp_behavior_value((base * 0.72) + (situational * 0.28))

    if token == BEHAVIOR_AVOID_AUTHORITIES:
        bravery = _clamp_behavior_value(getattr(traits, "bravery", 0.5), default=0.5)
        discipline = _clamp_behavior_value(getattr(traits, "discipline", 0.5), default=0.5)
        safety_gap = _clamp_behavior_value(
            (100.0 - float(getattr(needs, "safety", 75.0) or 75.0)) / 100.0,
            default=0.25,
        )
        if justice is None:
            justice_level = 0.35
            crime_sensitivity = 0.45
            corruption = 0.0
        else:
            justice_level = _clamp_behavior_value(getattr(justice, "justice", 0.5), default=0.5)
            crime_sensitivity = _clamp_behavior_value(
                getattr(justice, "crime_sensitivity", justice_level),
                default=justice_level,
            )
            corruption = _clamp_behavior_value(getattr(justice, "corruption", 0.0), default=0.0)
        situational = _clamp_behavior_value(
            ((1.0 - bravery) * 0.34)
            + ((1.0 - discipline) * 0.08)
            + ((1.0 - justice_level) * 0.22)
            + ((1.0 - crime_sensitivity) * 0.1)
            + (corruption * 0.08)
            + (safety_gap * 0.18)
            + 0.04
        )
        if base is None:
            return situational
        return _clamp_behavior_value((base * 0.76) + (situational * 0.24))

    if token == BEHAVIOR_ENFORCE_JUSTICE:
        discipline = _clamp_behavior_value(getattr(traits, "discipline", 0.5), default=0.5)
        bravery = _clamp_behavior_value(getattr(traits, "bravery", 0.5), default=0.5)
        if justice is None:
            justice_level = 0.35
            crime_sensitivity = 0.5
            corruption = 0.0
            enforce_all_bonus = 0.0
        else:
            justice_level = _clamp_behavior_value(getattr(justice, "justice", 0.5), default=0.5)
            crime_sensitivity = _clamp_behavior_value(
                getattr(justice, "crime_sensitivity", justice_level),
                default=justice_level,
            )
            corruption = _clamp_behavior_value(getattr(justice, "corruption", 0.0), default=0.0)
            enforce_all_bonus = 0.1 if bool(getattr(justice, "enforce_all", False)) else 0.0
        situational = _clamp_behavior_value(
            (justice_level * 0.55)
            + (crime_sensitivity * 0.2)
            + (discipline * 0.15)
            + (bravery * 0.05)
            + enforce_all_bonus
            - (corruption * 0.4)
        )
        if base is None:
            return situational
        return _clamp_behavior_value((base * 0.74) + (situational * 0.26))

    if token == BEHAVIOR_PROTECT_ALLIES:
        bravery = _clamp_behavior_value(getattr(traits, "bravery", 0.5), default=0.5)
        loyalty = _clamp_behavior_value(getattr(traits, "loyalty", 0.5), default=0.5)
        empathy = _clamp_behavior_value(getattr(traits, "empathy", 0.5), default=0.5)
        situational = _clamp_behavior_value(
            (loyalty * 0.45)
            + (empathy * 0.28)
            + (bravery * 0.17)
            + 0.08
        )
        if base is None:
            return situational
        return _clamp_behavior_value((base * 0.72) + (situational * 0.28))

    if token == BEHAVIOR_SEEK_SOCIAL_CONTACT:
        empathy = _clamp_behavior_value(getattr(traits, "empathy", 0.5), default=0.5)
        social_gap = _clamp_behavior_value(
            (100.0 - float(getattr(needs, "social", 65.0) or 65.0)) / 100.0,
            default=0.35,
        )
        situational = _clamp_behavior_value((empathy * 0.4) + (social_gap * 0.6))
        if base is None:
            return situational
        return _clamp_behavior_value((base * 0.72) + (situational * 0.28))

    if token == BEHAVIOR_SEEK_MEDICAL_AID:
        safety_gap = _clamp_behavior_value(
            (100.0 - float(getattr(needs, "safety", 75.0) or 75.0)) / 100.0,
            default=0.25,
        )
        if vitality is not None:
            max_hp = max(1, int(getattr(vitality, "max_hp", 1) or 1))
            hp = max(0, int(getattr(vitality, "hp", max_hp) or max_hp))
            health_gap = _clamp_behavior_value(1.0 - (float(hp) / float(max_hp)))
        else:
            health_gap = 0.0
        situational = _clamp_behavior_value((health_gap * 0.78) + (safety_gap * 0.14) + 0.04)
        if base is None:
            return situational
        return _clamp_behavior_value((base * 0.7) + (situational * 0.3))

    if token == BEHAVIOR_SEEK_SHELTER:
        energy_gap = _clamp_behavior_value(
            (100.0 - float(getattr(needs, "energy", 80.0) or 80.0)) / 100.0,
            default=0.2,
        )
        safety_gap = _clamp_behavior_value(
            (100.0 - float(getattr(needs, "safety", 80.0) or 80.0)) / 100.0,
            default=0.2,
        )
        social_gap = _clamp_behavior_value(
            (100.0 - float(getattr(needs, "social", 68.0) or 68.0)) / 100.0,
            default=0.18,
        )
        if vitality is not None:
            max_hp = max(1, int(getattr(vitality, "max_hp", 1) or 1))
            hp = max(0, int(getattr(vitality, "hp", max_hp) or max_hp))
            health_gap = _clamp_behavior_value(1.0 - (float(hp) / float(max_hp)))
        else:
            health_gap = 0.0
        hour = int(_world_hour(sim))
        night_bias = 0.16 if hour >= 21 or hour < 6 else 0.0
        situational = _clamp_behavior_value(
            (energy_gap * 0.42)
            + (safety_gap * 0.28)
            + (social_gap * 0.08)
            + (health_gap * 0.12)
            + night_bias
            + 0.02
        )
        if base is None:
            return situational
        return _clamp_behavior_value((base * 0.74) + (situational * 0.26))

    if token == BEHAVIOR_FOLLOW_DUTY:
        discipline = _clamp_behavior_value(getattr(traits, "discipline", 0.5), default=0.5)
        energy = _clamp_behavior_value(
            float(getattr(needs, "energy", 80.0) or 80.0) / 100.0,
            default=0.8,
        )
        situational = _clamp_behavior_value((discipline * 0.75) + (energy * 0.15) + 0.05)
        if base is None:
            return situational
        return _clamp_behavior_value((base * 0.74) + (situational * 0.26))

    if token in {
        BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME,
        BEHAVIOR_COMMIT_PLANNED_CRIME,
        BEHAVIOR_SEEK_CRIMINAL_AFFILIATION,
    }:
        drive = sim.ecs.get(CriminalDriveState).get(eid)
        pressure = _clamp_behavior_value(getattr(drive, "pressure", 0.0), default=0.0)
        confidence = _clamp_behavior_value(getattr(drive, "confidence", 0.0), default=0.0)
        affiliation_interest = _clamp_behavior_value(getattr(drive, "affiliation_interest", 0.0), default=0.0)
        try:
            planned_score = _clamp_behavior_value(float(getattr(drive, "planned_crime_score", 0.0) or 0.0) / 100.0)
        except (TypeError, ValueError):
            planned_score = 0.0
        try:
            opportunistic_score = _clamp_behavior_value(float(getattr(drive, "opportunistic_crime_score", 0.0) or 0.0) / 100.0)
        except (TypeError, ValueError):
            opportunistic_score = 0.0
        try:
            affiliation_score = _clamp_behavior_value(float(getattr(drive, "affiliation_seek_score", 0.0) or 0.0) / 100.0)
        except (TypeError, ValueError):
            affiliation_score = 0.0
        safety_gap = _clamp_behavior_value(
            (100.0 - float(getattr(needs, "safety", 75.0) or 75.0)) / 100.0,
            default=0.25,
        )
        bravery = _clamp_behavior_value(getattr(traits, "bravery", 0.5), default=0.5)
        discipline = _clamp_behavior_value(getattr(traits, "discipline", 0.5), default=0.5)
        if token == BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME:
            situational = _clamp_behavior_value(
                (pressure * 0.42)
                + (confidence * 0.18)
                + (opportunistic_score * 0.24)
                + ((1.0 - discipline) * 0.08)
                + ((1.0 - bravery) * 0.05)
                + (safety_gap * 0.03)
            )
        elif token == BEHAVIOR_COMMIT_PLANNED_CRIME:
            situational = _clamp_behavior_value(
                (pressure * 0.22)
                + (confidence * 0.2)
                + (planned_score * 0.4)
                + (affiliation_interest * 0.12)
                + ((1.0 - discipline) * 0.03)
                + ((1.0 - bravery) * 0.03)
            )
        else:
            situational = _clamp_behavior_value(
                (pressure * 0.28)
                + ((1.0 - confidence) * 0.24)
                + (affiliation_interest * 0.28)
                + (affiliation_score * 0.16)
                + ((1.0 - discipline) * 0.04)
            )
        if base is None:
            return situational
        return _clamp_behavior_value((base * 0.68) + (situational * 0.32))

    if base is not None:
        return base
    return _clamp_behavior_value(0.0)


def _behavior_preference(sim, eid, key, default=None):
    profile = _actor_behavior_profile(sim, eid)
    if not profile:
        return default
    preferences = getattr(profile, "preferences", None)
    if not isinstance(preferences, dict):
        return default
    return preferences.get(key, default)


def _street_drug_item_ids():
    rows = []
    for item_id, item_def in ITEM_CATALOG.items():
        tags = {str(tag).strip().lower() for tag in item_def.get("tags", ()) if str(tag).strip()}
        legal_status = str(item_def.get("legal_status", "legal")).strip().lower()
        if legal_status != "illegal":
            continue
        if "consumable" not in tags:
            continue
        if not tags.intersection({"drug", "stimulant", "injectable", "social"}):
            continue
        rows.append(str(item_id).strip().lower())
    rows.sort()
    return tuple(rows)


def _desired_street_buy_item_id(sim, actor_eid, *, district_type="", career=""):
    desired_item_id = str(_behavior_preference(sim, actor_eid, "desired_drug_item_id", "") or "").strip().lower()
    if desired_item_id:
        return desired_item_id
    if _actor_behavior_value(sim, actor_eid, BEHAVIOR_BUY_DESIRED_DRUG, 0.0) < 0.2:
        return ""
    pool = _street_drug_item_ids()
    if not pool:
        return ""
    chooser = random.Random(
        f"{getattr(sim, 'seed', 0)}:street-buy:{int(actor_eid)}:{_behavior_token(career)}:{_behavior_token(district_type)}:{len(pool)}"
    )
    return pool[chooser.randrange(len(pool))]


def _street_item_value(item_id):
    item_id = str(item_id or "").strip().lower()
    if not item_id:
        return int(_STREET_DEFAULT_VALUE)
    if item_id in _STREET_ITEM_OVERRIDES:
        return int(_STREET_ITEM_OVERRIDES[item_id])
    drone_value = drone_item_base_value(item_id, default=0)
    if drone_value > 0:
        return int(drone_value)
    item_def = ITEM_CATALOG.get(item_id, {})
    tags = {
        str(tag).strip().lower()
        for tag in item_def.get("tags", ())
        if str(tag).strip()
    }
    category = str(item_def.get("category", "") or "").strip().lower()
    for tag, value in _STREET_ITEM_VALUE.items():
        if tag in tags or (category and tag == category):
            return int(value)
    return int(_STREET_DEFAULT_VALUE)


def _street_item_price(entry, *, mult=1.0):
    item_id = str((entry or {}).get("item_id", "") or "").strip().lower()
    if not item_id or is_credstick_item(item_id):
        return 0
    quantity = max(1, int((entry or {}).get("quantity", 1) or 1))
    base = float(_street_item_value(item_id))
    condition = item_instance_condition(
        item_id,
        metadata=(entry or {}).get("metadata"),
        item_catalog=ITEM_CATALOG,
    )
    quality = str(condition.get("quality", "standard") or "").strip().lower() or "standard"
    quality_mult = {
        "poor": 0.78,
        "standard": 1.0,
        "good": 1.18,
        "excellent": 1.34,
    }.get(quality, 1.0)
    if bool((condition.get("profile") or {}).get("supports_durability")):
        quality_mult *= 0.72 + (float(condition.get("durability_ratio", 1.0) or 1.0) * 0.4)
    total = base * quantity * max(0.2, float(mult or 1.0)) * quality_mult
    return max(1, int(round(total)))


def _street_buy_terms(sim, actor_eid, *, district_type="", career=""):
    buy_desired_drug = _actor_behavior_value(sim, actor_eid, BEHAVIOR_BUY_DESIRED_DRUG, 0.0)
    buy_player_goods = _actor_behavior_value(sim, actor_eid, BEHAVIOR_BUY_PLAYER_GOODS, 0.0)
    if buy_desired_drug < 0.2 and buy_player_goods < 0.2:
        return None

    preferred_item_ids = _behavior_preference(sim, actor_eid, "street_buy_item_ids", ())
    item_ids = [
        str(item_id or "").strip().lower()
        for item_id in (
            preferred_item_ids
            if isinstance(preferred_item_ids, (list, tuple, set, frozenset))
            else (preferred_item_ids,)
        )
        if str(item_id or "").strip()
    ]
    desired_item_id = _desired_street_buy_item_id(
        sim,
        actor_eid,
        district_type=district_type,
        career=career,
    )
    if desired_item_id and desired_item_id not in item_ids:
        item_ids.insert(0, desired_item_id)

    preferred_categories = _behavior_preference(sim, actor_eid, "street_buy_categories", ())
    categories = {
        str(value or "").strip().lower()
        for value in (
            preferred_categories
            if isinstance(preferred_categories, (list, tuple, set, frozenset))
            else (preferred_categories,)
        )
        if str(value or "").strip()
    }
    preferred_tags = _behavior_preference(sim, actor_eid, "street_buy_tags", ())
    tags = {
        str(value or "").strip().lower()
        for value in (
            preferred_tags
            if isinstance(preferred_tags, (list, tuple, set, frozenset))
            else (preferred_tags,)
        )
        if str(value or "").strip()
    }
    if buy_player_goods >= 0.2 and not categories and not tags:
        categories.update(_STREET_BUY_DEFAULT_CATEGORIES)
        tags.update(_STREET_BUY_DEFAULT_TAGS)

    generic_mult = max(
        1.2,
        float(_behavior_preference(sim, actor_eid, "street_buy_price_mult", 1.18 + (buy_player_goods * 0.95)) or 1.2),
    )
    desired_mult = max(
        generic_mult,
        float(_behavior_preference(sim, actor_eid, "desired_drug_price_mult", 1.55 + (buy_desired_drug * 1.15)) or generic_mult),
    )
    return {
        "buy_desired_drug": float(buy_desired_drug),
        "buy_player_goods": float(buy_player_goods),
        "item_ids": tuple(item_ids),
        "categories": tuple(sorted(categories)),
        "tags": tuple(sorted(tags)),
        "desired_item_id": desired_item_id,
        "generic_mult": float(generic_mult),
        "desired_mult": float(desired_mult),
    }


def _street_buy_candidate_rows_for_inventory(sim, actor_eid, inventory, *, district_type="", career="", terms=None):
    if inventory is None:
        return []
    terms = terms or _street_buy_terms(
        sim,
        actor_eid,
        district_type=district_type,
        career=career,
    )
    if not terms:
        return []

    wanted_item_ids = {
        str(item_id).strip().lower()
        for item_id in terms.get("item_ids", ())
        if str(item_id).strip()
    }
    wanted_categories = {
        str(value).strip().lower()
        for value in terms.get("categories", ())
        if str(value).strip()
    }
    wanted_tags = {
        str(value).strip().lower()
        for value in terms.get("tags", ())
        if str(value).strip()
    }
    desired_item_id = str(terms.get("desired_item_id", "") or "").strip().lower()

    rows = []
    for entry in list(getattr(inventory, "items", ()) or ()):
        item_id = str(entry.get("item_id", "") or "").strip().lower()
        if not item_id or is_credstick_item(item_id):
            continue
        category = _item_category(entry, item_catalog=ITEM_CATALOG)
        if category == "credential":
            continue
        entry_tags = _item_tags(entry, item_catalog=ITEM_CATALOG)
        matched = item_id in wanted_item_ids
        matched = matched or bool(wanted_categories and category in wanted_categories)
        matched = matched or bool(wanted_tags and entry_tags.intersection(wanted_tags))
        if not matched:
            continue
        mult = float(terms.get("desired_mult", 1.0) if desired_item_id and item_id == desired_item_id else terms.get("generic_mult", 1.0))
        price = _street_item_price(entry, mult=mult)
        if price <= 0:
            continue
        rows.append({
            "entry": entry,
            "instance_id": entry.get("instance_id"),
            "item_id": item_id,
            "item_name": item_display_name(item_id, metadata=entry.get("metadata"), item_catalog=ITEM_CATALOG),
            "quantity": int(max(1, entry.get("quantity", 1) or 1)),
            "price": int(price),
            "desired": bool(desired_item_id and item_id == desired_item_id),
            "illegal": _item_legal_status(entry, item_catalog=ITEM_CATALOG) in {"illegal", "stolen"},
        })
    rows.sort(key=lambda row: (-int(row.get("price", 0)), not bool(row.get("desired")), str(row.get("item_id", ""))))
    return rows


def _street_buy_candidate_rows_for_actor(sim, buyer_eid, seller_eid, *, district_type="", career="", terms=None):
    inventory = sim.ecs.get(Inventory).get(seller_eid)
    return _street_buy_candidate_rows_for_inventory(
        sim,
        buyer_eid,
        inventory,
        district_type=district_type,
        career=career,
        terms=terms,
    )


def _resolve_street_buy_between_actors(sim, buyer_eid, seller_eid, *, district_type="", career=""):
    inventory = sim.ecs.get(Inventory).get(seller_eid)
    if inventory is None:
        return None

    terms = _street_buy_terms(
        sim,
        buyer_eid,
        district_type=district_type,
        career=career,
    )
    rows = _street_buy_candidate_rows_for_inventory(
        sim,
        buyer_eid,
        inventory,
        district_type=district_type,
        career=career,
        terms=terms,
    )
    if not rows:
        return None

    sold_rows = []
    credits_total = 0
    for row in list(rows):
        quantity = int(max(1, row.get("quantity", 1) or 1))
        removed = inventory.remove_item(instance_id=row.get("instance_id"), quantity=quantity)
        if not removed:
            continue
        _unlink_removed_item_from_gear(sim, seller_eid, removed, item_catalog=ITEM_CATALOG)
        credits_total += int(row.get("price", 0) or 0)
        sold_rows.append({
            "item_id": str(removed.get("item_id", "") or "").strip().lower(),
            "quantity": int(max(1, removed.get("quantity", 1) or 1)),
            "credits": int(row.get("price", 0) or 0),
            "desired": bool(row.get("desired")),
        })

    if not sold_rows:
        return None

    if credits_total > 0:
        item_def = ITEM_CATALOG.get(CREDSTICK_ITEM_ID, {})
        inventory.add_item(
            item_id=CREDSTICK_ITEM_ID,
            quantity=1,
            stack_max=max(1, int(item_def.get("stack_max", 1) or 1)),
            instance_factory=sim.new_item_instance_id,
            owner_eid=seller_eid,
            owner_tag="npc",
            metadata={"stored_credits": int(credits_total), "source": "npc_street_buy"},
        )

    seller_pos = sim.ecs.get(Position).get(seller_eid)
    desired_item_id = str((terms or {}).get("desired_item_id", "") or "").strip().lower()
    sim.emit(Event(
        "npc_street_buy_transaction",
        buyer_eid=buyer_eid,
        seller_eid=seller_eid,
        payout=int(credits_total),
        item_count=len(sold_rows),
        desired_item_id=desired_item_id,
        sold_rows=tuple(sold_rows),
        x=int(getattr(seller_pos, "x", 0) or 0),
        y=int(getattr(seller_pos, "y", 0) or 0),
        z=int(getattr(seller_pos, "z", 0) or 0),
    ))
    return {
        "buyer_eid": int(buyer_eid),
        "seller_eid": int(seller_eid),
        "credits_gained": int(credits_total),
        "item_count": len(sold_rows),
        "desired_item_id": desired_item_id,
        "sold_rows": tuple(sold_rows),
    }


def _street_buy_interest_profile(sim, actor_eid, player_eid, *, district_type="", career=""):
    inventory = sim.ecs.get(Inventory).get(player_eid)
    if inventory is None:
        return None

    buy_desired_drug = _actor_behavior_value(sim, actor_eid, BEHAVIOR_BUY_DESIRED_DRUG, 0.0)
    buy_player_goods = _actor_behavior_value(sim, actor_eid, BEHAVIOR_BUY_PLAYER_GOODS, 0.0)
    initiate_dialogue = _actor_behavior_value(sim, actor_eid, BEHAVIOR_INITIATE_DIALOGUE, 0.0)
    if max(buy_desired_drug, buy_player_goods, initiate_dialogue) < 0.18:
        return None

    terms = _street_buy_terms(
        sim,
        actor_eid,
        district_type=district_type,
        career=career,
    )
    rows = _street_buy_candidate_rows_for_inventory(
        sim,
        actor_eid,
        inventory,
        district_type=district_type,
        career=career,
        terms=terms,
    )
    desired_item_id = str((terms or {}).get("desired_item_id", "") or "").strip().lower()
    matched_item_ids = {
        str(row.get("item_id", "") or "").strip().lower()
        for row in rows
        if str(row.get("item_id", "") or "").strip()
    }
    player_has_match = bool(rows)
    player_has_desired = any(bool(row.get("desired")) for row in rows)
    player_has_generic_match = any(not bool(row.get("desired")) for row in rows)
    desired_name = item_display_name(desired_item_id, item_catalog=ITEM_CATALOG) if desired_item_id else ""
    return {
        "buy_desired_drug": float(buy_desired_drug),
        "buy_player_goods": float(buy_player_goods),
        "initiate_dialogue": float(initiate_dialogue),
        "desired_item_id": desired_item_id,
        "desired_name": desired_name,
        "player_has_match": bool(player_has_match),
        "player_has_desired": bool(player_has_desired),
        "player_has_generic_match": bool(player_has_generic_match),
        "matched_item_ids": tuple(sorted(matched_item_ids)),
    }


def _street_appraise_capabilities(sim, actor_eid):
    identify_strength = _actor_behavior_value(sim, actor_eid, BEHAVIOR_IDENTIFY_STREET_DRUGS, 0.0)
    appraise_strength = _actor_behavior_value(sim, actor_eid, BEHAVIOR_APPRAISE_STREET_GOODS, 0.0)
    if identify_strength < 0.2 and appraise_strength < 0.2:
        return None
    return {
        "identify_strength": float(identify_strength),
        "appraise_strength": float(appraise_strength),
    }


def _street_appraise_candidates_for_inventory(sim, appraiser_eid, subject_eid, inventory):
    if inventory is None:
        return {"identify": [], "appraise": []}
    capabilities = _street_appraise_capabilities(sim, appraiser_eid)
    if not capabilities:
        return {"identify": [], "appraise": []}

    identify_rows = []
    appraise_rows = []
    identify_strength = float(capabilities.get("identify_strength", 0.0) or 0.0)
    appraise_strength = float(capabilities.get("appraise_strength", 0.0) or 0.0)

    for entry in list(getattr(inventory, "items", ()) or ()):
        legal_status = _item_legal_status(entry, item_catalog=ITEM_CATALOG)
        if identify_strength >= 0.2 and item_requires_identification(entry, item_catalog=ITEM_CATALOG):
            if not item_is_identified_for_actor(sim, subject_eid, entry, item_catalog=ITEM_CATALOG):
                if legal_status in {"illegal", "restricted", "suspicious"}:
                    identify_rows.append(entry)
        if appraise_strength >= 0.2:
            condition = item_instance_condition(
                str(entry.get("item_id", "") or "").strip().lower(),
                metadata=entry.get("metadata"),
                item_catalog=ITEM_CATALOG,
            )
            profile = condition.get("profile", {}) if isinstance(condition.get("profile"), dict) else {}
            needs_quality = (
                ("item_quality" in (entry.get("metadata") or {}) or profile.get("supports_quality"))
                and not item_is_appraised_for_actor(sim, subject_eid, entry, "item_quality")
            )
            needs_durability = (
                (
                    "item_durability" in (entry.get("metadata") or {})
                    or "item_max_durability" in (entry.get("metadata") or {})
                    or profile.get("supports_durability")
                )
                and not (
                    item_is_appraised_for_actor(sim, subject_eid, entry, "item_durability")
                    and item_is_appraised_for_actor(sim, subject_eid, entry, "item_max_durability")
                )
            )
            if needs_quality or needs_durability:
                appraise_rows.append(entry)

    return {"identify": identify_rows, "appraise": appraise_rows}


def _street_appraise_candidates_for_actor(sim, appraiser_eid, subject_eid):
    inventory = sim.ecs.get(Inventory).get(subject_eid)
    return _street_appraise_candidates_for_inventory(sim, appraiser_eid, subject_eid, inventory)


def _resolve_street_appraise_between_actors(sim, appraiser_eid, subject_eid):
    candidates = _street_appraise_candidates_for_actor(sim, appraiser_eid, subject_eid)
    identified_names = []
    identify_count = 0
    for entry in list(candidates.get("identify", ()) or ()):
        if identify_item_for_actor(
            sim,
            subject_eid,
            entry,
            source_kind="npc_street_appraise",
            item_catalog=ITEM_CATALOG,
        ):
            identify_count += 1
            identified_names.append(
                item_display_name(
                    entry.get("item_id"),
                    metadata=entry.get("metadata"),
                    item_catalog=ITEM_CATALOG,
                )
            )

    appraise_count = 0
    for entry in list(candidates.get("appraise", ()) or ()):
        revealed = appraise_item_for_actor(
            sim,
            subject_eid,
            entry,
            item_catalog=ITEM_CATALOG,
        )
        if revealed:
            appraise_count += 1

    if identify_count <= 0 and appraise_count <= 0:
        return None

    subject_pos = sim.ecs.get(Position).get(subject_eid)
    sim.emit(Event(
        "npc_street_appraise_transaction",
        appraiser_eid=int(appraiser_eid),
        subject_eid=int(subject_eid),
        identify_count=int(identify_count),
        appraise_count=int(appraise_count),
        identified_item_names=tuple(identified_names),
        x=int(getattr(subject_pos, "x", 0) or 0),
        y=int(getattr(subject_pos, "y", 0) or 0),
        z=int(getattr(subject_pos, "z", 0) or 0),
    ))
    return {
        "appraiser_eid": int(appraiser_eid),
        "subject_eid": int(subject_eid),
        "identify_count": int(identify_count),
        "appraise_count": int(appraise_count),
        "identified_item_names": tuple(identified_names),
    }


def _ground_item_pickup_is_safe(sim, actor_eid, ground):
    entitlement = item_entitlement_for_actor(sim, actor_eid, ground)
    return bool(entitlement and entitlement.get("lawful_take"))


def _inventory_can_accept_credsticks(inventory, *, owner_eid):
    if not inventory:
        return False
    item_def = ITEM_CATALOG.get(CREDSTICK_ITEM_ID, {})
    stack_max = max(1, int(item_def.get("stack_max", 1) or 1))
    if stack_max > 1:
        for entry in getattr(inventory, "items", ()):
            if not is_credstick_item(entry.get("item_id")):
                continue
            if entry.get("owner_eid") != owner_eid or entry.get("owner_tag") != "npc":
                continue
            if int(entry.get("quantity", 0) or 0) < stack_max:
                return True
    return inventory.slot_count() < inventory.capacity


def _inventory_can_accept_item(inventory, item_id, *, owner_eid, owner_tag="npc"):
    if not inventory:
        return False
    item_def = ITEM_CATALOG.get(str(item_id or "").strip().lower(), {})
    stack_max = max(1, int(item_def.get("stack_max", 1) or 1))
    if stack_max > 1:
        for entry in getattr(inventory, "items", ()):
            if str(entry.get("item_id", "") or "").strip().lower() != str(item_id or "").strip().lower():
                continue
            if entry.get("owner_eid") != owner_eid or entry.get("owner_tag") != owner_tag:
                continue
            if int(entry.get("quantity", 0) or 0) < stack_max:
                return True
    return inventory.slot_count() < inventory.capacity


def _inventory_liquid_credits(inventory):
    return _shared_inventory_liquid_credits(inventory)


def _spend_inventory_credits(inventory, amount):
    return _shared_spend_npc_wallet_credits(inventory, amount)


def _ground_credit_interest_score(credits, distance):
    credits = max(0, int(credits or 0))
    distance = max(0, int(distance or 0))
    return min(28.0, credits * 0.85) + max(0.0, (6 - distance) * 6.0)


def _inventory_contraband_heat(sim, actor_eid):
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if not inventory:
        return 0.0

    heat = 0.0
    for entry in tuple(getattr(inventory, "items", ()) or ()):
        item_id = str(entry.get("item_id", "") or "").strip().lower()
        if not item_id or is_credstick_item(item_id):
            continue
        legal_status = _item_legal_status(entry, item_catalog=ITEM_CATALOG)
        quantity = max(1, int(entry.get("quantity", 1) or 1))
        if legal_status in {"illegal", "stolen"}:
            heat += 0.28 + (0.12 * min(3, quantity))
        elif legal_status in {"restricted", "suspicious"}:
            heat += 0.16 + (0.08 * min(2, quantity))
    return _clamp_behavior_value(min(1.0, heat), default=0.0)


def _behavior_live_street_heat(sim, actor_eid):
    inventory_heat = _inventory_contraband_heat(sim, actor_eid)
    street_heat = max(
        _actor_behavior_value(sim, actor_eid, BEHAVIOR_BUY_DESIRED_DRUG, 0.0),
        _actor_behavior_value(sim, actor_eid, BEHAVIOR_BUY_PLAYER_GOODS, 0.0),
        _actor_behavior_value(sim, actor_eid, BEHAVIOR_APPRAISE_STREET_GOODS, 0.0) * 0.8,
        _actor_behavior_value(sim, actor_eid, BEHAVIOR_IDENTIFY_STREET_DRUGS, 0.0) * 0.68,
    )
    return _clamp_behavior_value(max(float(inventory_heat), float(street_heat) * 0.72), default=0.0)


def _find_authority_avoidance_target(sim, actor_eid, pos, *, radius=None):
    if not pos:
        return None

    search_radius = radius
    if search_radius is None:
        search_radius = _behavior_preference(sim, actor_eid, "authority_avoid_radius", 8)
    try:
        search_radius = max(3, int(search_radius))
    except (TypeError, ValueError):
        search_radius = 8

    ais = sim.ecs.get(AI)
    positions = sim.ecs.get(Position)
    justices = sim.ecs.get(JusticeProfile)
    nearest = None
    for other_eid, other_ai in ais.items():
        if other_eid == actor_eid:
            continue
        other_pos = positions.get(other_eid)
        if not other_pos or int(other_pos.z) != int(pos.z):
            continue
        distance = _manhattan(pos.x, pos.y, other_pos.x, other_pos.y)
        if distance > search_radius:
            continue
        role = _behavior_token(getattr(other_ai, "role", ""))
        justice = justices.get(other_eid)
        if role not in _AUTHORITY_ROLES and not bool(getattr(justice, "enforce_all", False)):
            continue
        candidate = {
            "authority_eid": int(other_eid),
            "authority_pos": (int(other_pos.x), int(other_pos.y), int(other_pos.z)),
            "distance": int(distance),
            "score": max(0.0, ((search_radius + 1 - distance) * 6.0) + (8.0 if role == "guard" else 5.0)),
        }
        if nearest is None or candidate["distance"] < nearest["distance"] or candidate["score"] > nearest["score"]:
            nearest = candidate
    if nearest is None:
        return None

    routine = sim.ecs.get(NPCRoutine).get(actor_eid)
    home = getattr(routine, "home", None) if routine else None
    if (
        isinstance(home, (tuple, list))
        and len(home) >= 3
        and int(home[2]) == int(pos.z)
        and _manhattan(int(home[0]), int(home[1]), nearest["authority_pos"][0], nearest["authority_pos"][1]) >= nearest["distance"] + 2
    ):
        target = (int(home[0]), int(home[1]), int(home[2]))
    else:
        dx = int(pos.x) - int(nearest["authority_pos"][0])
        dy = int(pos.y) - int(nearest["authority_pos"][1])
        if dx == 0 and dy == 0:
            chooser = random.Random(f"{getattr(sim, 'seed', 0)}:authority-evade:{int(actor_eid)}:{int(getattr(sim, 'tick', 0))}")
            if chooser.random() < 0.5:
                dx = 1
            else:
                dy = 1
        step = max(3, min(6, search_radius - nearest["distance"] + 2))
        target = (
            int(pos.x + ((1 if dx >= 0 else -1) * step)),
            int(pos.y + ((1 if dy >= 0 else -1) * step)),
            int(pos.z),
        )

    nearest["target"] = target
    return nearest


def _business_target_reputation_bonus(sim, actor_eid, property_id, *, purpose="", urgency=0.0, budget_pressure=0.0):
    property_key = str(property_id or "").strip()
    if not property_key:
        return 0.0
    profile = business_opinion_profile(sim, actor_eid, property_key)
    trust = _clamp_behavior_value(profile.get("trust", 0.0), default=0.0)
    reliability = _clamp_behavior_value(profile.get("reliability", 0.0), default=0.0)
    familiarity = _clamp_behavior_value(profile.get("familiarity", 0.0), default=0.0)
    loyalty = _clamp_behavior_value(profile.get("loyalty", 0.0), default=0.0)
    fear = _clamp_behavior_value(profile.get("fear", 0.0), default=0.0)
    heat = _clamp_behavior_value(profile.get("heat", 0.0), default=0.0)
    resentment = _clamp_behavior_value(profile.get("resentment", 0.0), default=0.0)
    incident_pressure = _clamp_behavior_value(profile.get("incident_pressure", 0.0), default=0.0)
    try:
        price_fairness = float(profile.get("price_fairness", 0.0) or 0.0)
    except (TypeError, ValueError):
        price_fairness = 0.0
    price_fairness = max(-1.0, min(1.0, price_fairness))
    urgency = _clamp_behavior_value(urgency, default=0.0)
    budget_pressure = _clamp_behavior_value(budget_pressure, default=0.0)

    if _behavior_token(purpose) == "medical_aid":
        fear_penalty = fear * (7.5 * max(0.35, 1.0 - urgency))
        price_penalty = max(0.0, -price_fairness) * (5.5 * max(0.3, 1.0 - urgency))
        return float(
            (trust * 12.0)
            + (reliability * 13.5)
            + (loyalty * 4.5)
            + (familiarity * 2.5)
            + (max(0.0, price_fairness) * 3.5)
            - fear_penalty
            - (heat * 5.0)
            - (resentment * 3.2)
            - price_penalty
            - (incident_pressure * 2.0)
        )

    if _behavior_token(purpose) == "scavenge_sale":
        return float(
            (trust * 7.0)
            + (reliability * 5.0)
            + (loyalty * 3.0)
            + (familiarity * 2.0)
            + (max(0.0, price_fairness) * 13.0)
            - (max(0.0, -price_fairness) * 13.0)
            - (fear * 3.5)
            - (heat * 2.5)
            - (resentment * 4.0)
            - (incident_pressure * 1.5)
        )

    if _behavior_token(purpose) == "social_venue":
        price_good = max(0.0, price_fairness)
        price_pain = max(0.0, -price_fairness)
        return float(
            (trust * 8.5)
            + (reliability * 6.5)
            + (loyalty * 4.5)
            + (familiarity * 4.0)
            + (price_good * (4.0 - (budget_pressure * 1.4)))
            - (price_pain * (3.5 + (budget_pressure * 7.0)))
            - (fear * 5.2)
            - (heat * 4.5)
            - (resentment * 4.4)
            - (incident_pressure * 2.2)
        )

    return float(
        (trust * 5.0)
        + (reliability * 5.0)
        + (loyalty * 2.5)
        + (familiarity * 1.5)
        + (max(0.0, price_fairness) * 6.0)
        - (max(0.0, -price_fairness) * 6.0)
        - (fear * 3.0)
        - (heat * 3.0)
        - (resentment * 3.0)
        - incident_pressure
    )


def _social_venue_secret_access(sim, actor_eid, prop):
    property_key = str((prop or {}).get("id", "") or "").strip() if isinstance(prop, dict) else ""
    if sim is None or actor_eid is None or not property_key:
        return {"allowed": False, "lead_bonus": 0.0}

    secret_gate = social_secret_site_trust_gate(prop)
    if secret_gate <= 0.0:
        return {"allowed": True, "lead_bonus": 0.0}

    property_knowledge = sim.ecs.get(PropertyKnowledge).get(actor_eid)
    lead_entry = property_knowledge.property_entry(property_key) if isinstance(property_knowledge, PropertyKnowledge) else None
    lead_kind = _behavior_token((lead_entry or {}).get("lead_kind"))
    hidden_lead = bool(property_knowledge.is_hidden(property_key)) if isinstance(property_knowledge, PropertyKnowledge) else False
    lead_confidence = _clamp_behavior_value((lead_entry or {}).get("confidence", 0.0), default=0.0)

    profile = business_opinion_profile(sim, actor_eid, property_key)
    trust = _clamp_behavior_value(profile.get("trust", 0.0), default=0.0)
    reliability = _clamp_behavior_value(profile.get("reliability", 0.0), default=0.0)
    familiarity = _clamp_behavior_value(profile.get("familiarity", 0.0), default=0.0)
    coherence = _clamp_behavior_value(profile.get("coherence", 0.0), default=0.0)
    propagation_depth = max(0, int(profile.get("propagation_depth", 0) or 0))

    has_actionable_lead = (
        isinstance(lead_entry, dict)
        and (
            hidden_lead
            or lead_kind == "social"
            or lead_confidence >= max(0.44, secret_gate * 0.62)
        )
    )
    has_firsthand_familiarity = familiarity >= max(0.54, secret_gate * 0.72) and propagation_depth <= 0
    if not has_actionable_lead and not has_firsthand_familiarity:
        return {"allowed": False, "lead_bonus": 0.0}

    clearance = (
        (trust * 0.42)
        + (familiarity * 0.28)
        + (reliability * 0.14)
        + (coherence * 0.08)
        + (lead_confidence * 0.22)
    )
    if hidden_lead or lead_kind == "social":
        clearance += 0.1
    if has_firsthand_familiarity:
        clearance = max(clearance, (familiarity * 0.68) + (trust * 0.24) + (reliability * 0.12))
    if clearance < secret_gate:
        return {"allowed": False, "lead_bonus": 0.0}

    return {
        "allowed": True,
        "lead_bonus": max(0.0, clearance - secret_gate) * 1.8,
    }


def _venue_aperture_and_front_cells(prop):
    if not isinstance(prop, dict):
        return frozenset()
    metadata = prop.get("metadata", {}) if isinstance(prop.get("metadata"), dict) else {}
    rows = []
    entry = metadata.get("entry")
    if isinstance(entry, dict):
        rows.append(entry)
    apertures = metadata.get("apertures", ())
    if isinstance(apertures, (list, tuple, set, frozenset)):
        rows.extend(row for row in apertures if isinstance(row, dict))

    blocked = set()
    for row in rows:
        try:
            cell = (
                int(row.get("x")),
                int(row.get("y")),
                int(row.get("z", prop.get("z", 0))),
            )
        except (TypeError, ValueError):
            continue
        blocked.add(cell)
        cx, cy, cz = cell
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            blocked.add((int(cx + dx), int(cy + dy), int(cz)))
        front = site_entry_front_cell(row)
        if front is not None:
            front_cell = (int(front[0]), int(front[1]), int(front[2]))
            blocked.add(front_cell)
            fx, fy, fz = front_cell
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                blocked.add((int(fx + dx), int(fy + dy), int(fz)))
    return frozenset(blocked)


def _venue_footprint_cells(prop, fallback_z):
    if not isinstance(prop, dict):
        return ()
    metadata = prop.get("metadata", {}) if isinstance(prop.get("metadata"), dict) else {}
    try:
        prop_z = int(prop.get("z", fallback_z))
    except (TypeError, ValueError):
        prop_z = int(fallback_z)

    configured = metadata.get("footprint_cells")
    cells = []
    if isinstance(configured, (list, tuple, set, frozenset)):
        for cell in configured:
            try:
                if isinstance(cell, dict):
                    cells.append((
                        int(cell.get("x")),
                        int(cell.get("y")),
                        int(cell.get("z", prop_z)),
                    ))
                elif isinstance(cell, (list, tuple)) and len(cell) >= 2:
                    cells.append((
                        int(cell[0]),
                        int(cell[1]),
                        int(cell[2]) if len(cell) >= 3 else prop_z,
                    ))
            except (TypeError, ValueError):
                continue
        if cells:
            return tuple(cells)

    footprint = metadata.get("footprint")
    if isinstance(footprint, dict):
        try:
            left = int(footprint.get("left"))
            right = int(footprint.get("right"))
            top = int(footprint.get("top"))
            bottom = int(footprint.get("bottom"))
            cell_z = int(footprint.get("z", prop_z))
        except (TypeError, ValueError):
            pass
        else:
            return tuple(
                (int(cell_x), int(cell_y), int(cell_z))
                for cell_y in range(top, bottom + 1)
                for cell_x in range(left, right + 1)
            )

    try:
        return ((int(prop.get("x")), int(prop.get("y")), int(prop.get("z", prop_z))),)
    except (TypeError, ValueError):
        return ()


def _social_venue_settle_target(sim, actor_eid, prop, *, origin_x, origin_y, origin_z, fallback=None):
    """Pick a place to be at a venue, not the doorway used to enter it."""
    if sim is None or not isinstance(prop, dict):
        return fallback
    property_id = str(prop.get("id", "") or "").strip()
    blocked = _venue_aperture_and_front_cells(prop)
    scored = []
    for cell_x, cell_y, cell_z in _venue_footprint_cells(prop, origin_z):
        if int(cell_z) != int(origin_z):
            continue
        cell = (int(cell_x), int(cell_y), int(cell_z))
        if cell in blocked:
            continue
        covered = _property_covering(sim, int(cell_x), int(cell_y), int(cell_z))
        if property_id and (
            not isinstance(covered, dict)
            or str(covered.get("id", "") or "").strip() != property_id
        ):
            continue
        tile = sim.tilemap.tile_at(int(cell_x), int(cell_y), int(cell_z))
        if tile is None or not bool(getattr(tile, "walkable", False)):
            continue
        semantic = str(getattr(tile, "semantic_id", "") or "").strip().lower()
        glyph = str(getattr(tile, "glyph", "") or "")[:1]
        if semantic in {"feature_door", "wall_building", "feature_window"} or glyph in {"+", "#"}:
            continue
        traversable, _reason = _is_traversable_for(sim, actor_eid, int(cell_x), int(cell_y), int(cell_z))
        if not traversable:
            continue
        distance = _manhattan(int(origin_x), int(origin_y), int(cell_x), int(cell_y))
        same_floor_blocked = tuple(
            (int(bx), int(by))
            for bx, by, bz in blocked
            if int(bz) == int(cell_z)
        )
        if same_floor_blocked:
            clearance = min(
                _manhattan(int(cell_x), int(cell_y), int(bx), int(by))
                for bx, by in same_floor_blocked
            )
        else:
            clearance = 4
        door_penalty = max(0, 3 - int(clearance)) * 0.75
        scored.append((float(distance) + door_penalty, int(cell_x), int(cell_y), int(cell_z)))

    if not scored:
        return fallback
    scored.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    _score, cell_x, cell_y, cell_z = scored[0]
    return (int(cell_x), int(cell_y), int(cell_z))


def _pick_social_venue(sim, x, y, z, eid, own_prop_id=None, radius=12, nutrition=None):
    """Return a (property, focus_position) pair for a nearby social venue.

    This uses the actor's own business knowledge rather than a global truth
    layer, so trusted rumors and direct experience can change where they
    choose to spend off-shift time.
    """
    if sim is None:
        return None, None

    try:
        origin_x = int(x)
        origin_y = int(y)
        origin_z = int(z)
        actor_eid = int(eid)
        search_radius = max(2, int(radius))
    except (TypeError, ValueError):
        return None, None

    nutrition = str(nutrition or "").strip().lower()
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:{actor_eid}:{int(getattr(sim, 'tick', 0) or 0)}:socialize:{nutrition}")
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    liquid_credits = _inventory_liquid_credits(inventory)
    if liquid_credits <= 6:
        budget_pressure = 1.0
    elif liquid_credits <= 18:
        budget_pressure = 0.7
    elif liquid_credits <= 42:
        budget_pressure = 0.35
    else:
        budget_pressure = 0.08

    scored = []
    for prop in sim.properties_in_radius(origin_x, origin_y, origin_z, r=search_radius):
        if not isinstance(prop, dict):
            continue
        pid = str(prop.get("id", "") or "").strip()
        if pid and own_prop_id and pid == str(own_prop_id):
            continue
        focus = _property_focus_position(prop)
        if focus is None:
            continue
        target = _social_venue_settle_target(
            sim,
            actor_eid,
            prop,
            origin_x=origin_x,
            origin_y=origin_y,
            origin_z=origin_z,
            fallback=(int(focus[0]), int(focus[1]), int(focus[2])),
        )
        if target is None:
            continue
        fx, fy, fz = target
        if int(fz) != origin_z:
            continue
        distance = _manhattan(origin_x, origin_y, int(fx), int(fy))
        if distance <= 0:
            continue

        archetype = _behavior_token(((prop.get("metadata") or {}) if isinstance(prop, dict) else {}).get("archetype"))
        is_public = bool(_property_is_public(prop))
        is_storefront = bool(_property_is_storefront(prop))
        if archetype in _NIGHTLIFE_ARCHETYPES:
            base_score = 6.8
        elif archetype in _SOCIAL_VENUE_ARCHETYPES:
            base_score = 5.6
        elif is_public:
            base_score = 4.2
        elif is_storefront:
            base_score = 3.4
        else:
            continue

        access = _cached_behavior_property_access(
            sim,
            actor_eid,
            prop,
            x=int(focus[0]),
            y=int(focus[1]),
            z=int(focus[2]),
        )
        if not access.permitted and not access.can_use_services and not (is_public or is_storefront):
            continue
        if not access.permitted and not access.can_use_services:
            base_score *= 0.82
        secret_access = _social_venue_secret_access(sim, actor_eid, prop)
        if not secret_access.get("allowed", False):
            continue

        score = base_score + max(0.0, (search_radius + 2 - distance) * 0.42)
        if archetype in _NIGHTLIFE_ARCHETYPES and liquid_credits <= 4:
            score -= 1.8
        caps = _nutrition_capabilities_for_property(prop)
        if nutrition in {"hunger", "food"}:
            score += 5.2 if caps.get("food") else -2.8
        elif nutrition in {"thirst", "water", "drink"}:
            score += 5.0 if caps.get("drink") else -2.4
        elif nutrition in {"both", "nutrition"}:
            score += (3.2 if caps.get("food") else -1.4) + (3.0 if caps.get("drink") else -1.2)
        score += _business_target_reputation_bonus(
            sim,
            actor_eid,
            pid,
            purpose="social_venue",
            budget_pressure=budget_pressure,
        )
        score += float(secret_access.get("lead_bonus", 0.0) or 0.0)
        scored.append((float(score), prop, (int(fx), int(fy), int(fz))))

    if not scored:
        return None, None

    scored.sort(key=lambda row: row[0], reverse=True)
    top = scored[: max(1, min(4, len(scored)))]
    floor = min(float(row[0]) for row in top)
    weighted = []
    total = 0.0
    for score, prop, focus in top:
        weight = max(0.05, (float(score) - floor) + 0.2)
        weighted.append((weight, prop, focus))
        total += weight

    pick = rng.uniform(0.0, total)
    running = 0.0
    chosen_prop, chosen_focus = weighted[-1][1], weighted[-1][2]
    for weight, prop, focus in weighted:
        running += weight
        if pick <= running:
            chosen_prop, chosen_focus = prop, focus
            break
    return chosen_prop, chosen_focus


def _find_medical_aid_target(sim, actor_eid, pos, *, radius=None, preferred_property_id=None, preferred_score_bonus=0.0):
    lead = _best_opportunity_lead(sim, actor_eid, "medical")
    if isinstance(lead, dict):
        if preferred_property_id and str(preferred_property_id).strip() and str(lead.get("property_id", "")).strip() == str(preferred_property_id).strip():
            lead["score"] = float(lead.get("score", 0.0) or 0.0) + float(max(0.0, preferred_score_bonus or 0.0))
        return lead
    if not pos:
        return None

    vitality = sim.ecs.get(Vitality).get(actor_eid)
    if vitality is None or bool(getattr(vitality, "downed", False)):
        return None
    max_hp = max(1, int(getattr(vitality, "max_hp", 1) or 1))
    hp = max(0, int(getattr(vitality, "hp", max_hp) or max_hp))
    if hp >= max_hp:
        return None

    search_radius = radius
    if search_radius is None:
        search_radius = _behavior_preference(sim, actor_eid, "medical_aid_search_radius", 12)
    try:
        search_radius = max(4, int(search_radius))
    except (TypeError, ValueError):
        search_radius = 12

    health_gap = max(0.0, 1.0 - (float(hp) / float(max_hp)))
    best = None
    for row in _nearby_opportunity_rows(sim, pos, radius=search_radius, lead_kind="medical", current_tick=int(getattr(sim, "tick", 0) or 0)):
        target = row.get("target")
        if not isinstance(target, (tuple, list)) or len(target) < 3:
            continue
        distance = _manhattan(pos.x, pos.y, int(target[0]), int(target[1]))
        score = max(0.0, (health_gap * 62.0) + 10.0 - (distance * 1.85))
        property_id = str(row.get("property_id", "")).strip() or None
        score += _business_target_reputation_bonus(
            sim,
            actor_eid,
            property_id,
            purpose="medical_aid",
            urgency=health_gap,
        )
        if preferred_property_id and property_id and str(preferred_property_id).strip() == property_id:
            score += float(max(0.0, preferred_score_bonus or 0.0))
        candidate = {
            "property_id": property_id,
            "property_name": str(row.get("property_name", property_id or "clinic")).strip() or "clinic",
            "archetype": str(row.get("archetype", "") or "").strip().lower(),
            "target": (int(target[0]), int(target[1]), int(target[2])),
            "distance": int(distance),
            "score": float(score),
            "covert_referral": bool(
                preferred_property_id
                and property_id
                and str(preferred_property_id).strip() == property_id
            ),
            "confidence": min(0.95, 0.55 + (health_gap * 0.25)),
            "verification_required": True,
            "service_id": "medical",
            "opportunity_tag": "medical",
        }
        if best is None or float(candidate["score"]) > float(best["score"]):
            best = candidate
    if best is not None:
        _remember_opportunity_lead(
            sim,
            actor_eid,
            "medical",
            best,
            source_kind="surface_snapshot",
            stale_after_ticks=90,
            expires_ticks=360,
        )
    return best


def _find_medical_aid_target_exact(sim, actor_eid, pos, *, radius=None, preferred_property_id=None, preferred_score_bonus=0.0):
    if not pos:
        return None

    vitality = sim.ecs.get(Vitality).get(actor_eid)
    if vitality is None or bool(getattr(vitality, "downed", False)):
        return None
    max_hp = max(1, int(getattr(vitality, "max_hp", 1) or 1))
    hp = max(0, int(getattr(vitality, "hp", max_hp) or max_hp))
    if hp >= max_hp:
        return None

    search_radius = radius
    if search_radius is None:
        search_radius = _behavior_preference(sim, actor_eid, "medical_aid_search_radius", 12)
    try:
        search_radius = max(4, int(search_radius))
    except (TypeError, ValueError):
        search_radius = 12

    health_gap = max(0.0, 1.0 - (float(hp) / float(max_hp)))
    best = None
    for prop in sim.properties_in_radius(pos.x, pos.y, pos.z, r=search_radius):
        archetype = _behavior_token(((prop.get("metadata") or {}) if isinstance(prop, dict) else {}).get("archetype"))
        if archetype not in _MEDICAL_ARCHETYPES:
            continue
        focus = _property_focus_position(prop)
        if not focus:
            continue
        fx, fy, fz = focus
        if int(fz) != int(pos.z):
            continue
        access = _cached_behavior_property_access(
            sim,
            actor_eid,
            prop,
            x=int(fx),
            y=int(fy),
            z=int(fz),
        )
        covert_referral = _preferred_hidden_contact_match(
            prop,
            preferred_property_id,
            hidden_kind="backroom_clinic",
        )
        if not access.can_use_services and not access.permitted and not covert_referral:
            continue
        distance = _manhattan(pos.x, pos.y, fx, fy)
        score = max(0.0, (health_gap * 62.0) + 10.0 - (distance * 2.1))
        property_id = str(prop.get("id", "")).strip() or None
        score += _business_target_reputation_bonus(
            sim,
            actor_eid,
            property_id,
            purpose="medical_aid",
            urgency=health_gap,
        )
        if preferred_property_id and property_id and str(preferred_property_id).strip() == property_id:
            score += float(max(0.0, preferred_score_bonus or 0.0))
        candidate = {
            "property_id": property_id,
            "property_name": str(prop.get("name", prop.get("id", "clinic"))).strip() or "clinic",
            "archetype": archetype,
            "target": (int(fx), int(fy), int(fz)),
            "distance": int(distance),
            "score": float(score),
            "covert_referral": bool(covert_referral),
        }
        if best is None or candidate["score"] > best["score"]:
            best = candidate
    return best


def _find_lodging_target(sim, actor_eid, pos, *, radius=None, preferred_property_id=None, preferred_score_bonus=0.0):
    lead = _best_opportunity_lead(sim, actor_eid, "lodging")
    if isinstance(lead, dict):
        if preferred_property_id and str(preferred_property_id).strip() and str(lead.get("property_id", "")).strip() == str(preferred_property_id).strip():
            lead["score"] = float(lead.get("score", 0.0) or 0.0) + float(max(0.0, preferred_score_bonus or 0.0))
        return lead
    if not pos:
        return None

    needs = sim.ecs.get(NPCNeeds).get(actor_eid)
    if needs is None:
        return None

    vitality = sim.ecs.get(Vitality).get(actor_eid)
    routine = sim.ecs.get(NPCRoutine).get(actor_eid)
    home = getattr(routine, "home", None) if routine else None
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    liquid_credits = _inventory_liquid_credits(inventory)

    energy_gap = _clamp_behavior_value((100.0 - float(getattr(needs, "energy", 85.0) or 85.0)) / 100.0, default=0.15)
    safety_gap = _clamp_behavior_value((100.0 - float(getattr(needs, "safety", 85.0) or 85.0)) / 100.0, default=0.15)
    social_gap = _clamp_behavior_value((100.0 - float(getattr(needs, "social", 70.0) or 70.0)) / 100.0, default=0.12)
    if vitality is not None:
        max_hp = max(1, int(getattr(vitality, "max_hp", 1) or 1))
        hp = max(0, int(getattr(vitality, "hp", max_hp) or max_hp))
        health_gap = _clamp_behavior_value(1.0 - (float(hp) / float(max_hp)))
    else:
        health_gap = 0.0
    night_hour = int(_world_hour(sim))
    night_bias = 1.0 if night_hour >= 21 or night_hour < 6 else 0.0

    if max(energy_gap, safety_gap, social_gap, health_gap, night_bias * 0.3) <= 0.08:
        return None

    search_radius = radius
    if search_radius is None:
        search_radius = _behavior_preference(sim, actor_eid, "shelter_search_radius", 12)
    try:
        search_radius = max(4, int(search_radius))
    except (TypeError, ValueError):
        search_radius = 12

    best = None
    for row in _nearby_opportunity_rows(sim, pos, radius=search_radius, lead_kind="lodging", current_tick=int(getattr(sim, "tick", 0) or 0)):
        target = row.get("target")
        if not isinstance(target, (tuple, list)) or len(target) < 3:
            continue
        services = {
            str(service or "").strip().lower()
            for service in tuple(row.get("services", ()) or ())
            if str(service or "").strip()
        }
        service = None
        service_score = float("-inf")
        if "rest" in services and liquid_credits >= _REST_SERVICE_COST:
            service = "rest"
            service_score = (
                10.0
                + (energy_gap * 24.0)
                + (safety_gap * 10.0)
                + (social_gap * 5.0)
                + (health_gap * 16.0)
                + (night_bias * 6.0)
            )
        if "shelter" in services:
            shelter_score = (
                12.0
                + (energy_gap * 14.0)
                + (safety_gap * 20.0)
                + (social_gap * 6.0)
                + (health_gap * 9.0)
                + (night_bias * 8.0)
            )
            if shelter_score > service_score + 1.0 or service is None:
                service = "shelter"
                service_score = shelter_score
        if service is None:
            continue
        distance = _manhattan(pos.x, pos.y, int(target[0]), int(target[1]))
        score = max(
            0.0,
            service_score
            + (energy_gap * 22.0)
            + (safety_gap * 18.0)
            + (health_gap * 12.0)
            - (distance * 1.7),
        )
        if isinstance(home, (tuple, list)) and len(home) >= 3 and int(home[2]) == int(pos.z):
            score -= 14.0 if service == "shelter" else 10.0
        elif not home:
            score += 6.0 + (night_bias * 4.0)
        property_id = str(row.get("property_id", "")).strip() or None
        if preferred_property_id and property_id and str(preferred_property_id).strip() == property_id:
            score += float(max(0.0, preferred_score_bonus or 0.0))
        candidate = {
            "property_id": property_id,
            "property_name": str(row.get("property_name", property_id or "site")).strip() or "site",
            "target": (int(target[0]), int(target[1]), int(target[2])),
            "distance": int(distance),
            "score": float(score),
            "service": service,
            "services": tuple(sorted(services.intersection(_LODGING_SERVICE_IDS))),
            "credits_cost": int(_REST_SERVICE_COST if service == "rest" else 0),
            "confidence": min(0.95, 0.52 + max(energy_gap, safety_gap, health_gap) * 0.28),
            "verification_required": True,
            "service_id": service,
            "opportunity_tag": "lodging",
        }
        if best is None or float(candidate["score"]) > float(best["score"]):
            best = candidate
    if best is not None:
        _remember_opportunity_lead(
            sim,
            actor_eid,
            "lodging",
            best,
            source_kind="surface_snapshot",
            stale_after_ticks=90,
            expires_ticks=360,
        )
    return best


def _find_lodging_target_exact(sim, actor_eid, pos, *, radius=None, preferred_property_id=None, preferred_score_bonus=0.0):
    if not pos:
        return None

    needs = sim.ecs.get(NPCNeeds).get(actor_eid)
    if needs is None:
        return None

    vitality = sim.ecs.get(Vitality).get(actor_eid)
    routine = sim.ecs.get(NPCRoutine).get(actor_eid)
    home = getattr(routine, "home", None) if routine else None
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    liquid_credits = _inventory_liquid_credits(inventory)

    energy_gap = _clamp_behavior_value((100.0 - float(getattr(needs, "energy", 85.0) or 85.0)) / 100.0, default=0.15)
    safety_gap = _clamp_behavior_value((100.0 - float(getattr(needs, "safety", 85.0) or 85.0)) / 100.0, default=0.15)
    social_gap = _clamp_behavior_value((100.0 - float(getattr(needs, "social", 70.0) or 70.0)) / 100.0, default=0.12)
    if vitality is not None:
        max_hp = max(1, int(getattr(vitality, "max_hp", 1) or 1))
        hp = max(0, int(getattr(vitality, "hp", max_hp) or max_hp))
        health_gap = _clamp_behavior_value(1.0 - (float(hp) / float(max_hp)))
    else:
        health_gap = 0.0
    night_hour = int(_world_hour(sim))
    night_bias = 1.0 if night_hour >= 21 or night_hour < 6 else 0.0

    if max(energy_gap, safety_gap, social_gap, health_gap, night_bias * 0.3) <= 0.08:
        return None

    search_radius = radius
    if search_radius is None:
        search_radius = _behavior_preference(sim, actor_eid, "shelter_search_radius", 12)
    try:
        search_radius = max(4, int(search_radius))
    except (TypeError, ValueError):
        search_radius = 12

    current_tick = int(getattr(sim, "tick", 0) or 0)
    credits_bucket = 1 if liquid_credits >= _REST_SERVICE_COST else 0
    home_bucket = 1 if home else 0
    chunk_key = sim.chunk_coords(int(pos.x), int(pos.y)) if hasattr(sim, "chunk_coords") else (int(pos.x), int(pos.y))
    cache_key = (
        int(actor_eid),
        int(chunk_key[0]),
        int(chunk_key[1]),
        int(pos.z),
        int(search_radius),
        credits_bucket,
        home_bucket,
        str(preferred_property_id or "").strip(),
        int(round(float(preferred_score_bonus or 0.0))),
    )
    cache = _npc_behavior_search_cache(sim).setdefault("lodging_targets", {})
    cached = cache.get(cache_key)
    if isinstance(cached, dict) and current_tick <= int(cached.get("expires_tick", -1) or -1):
        return cached.get("result")

    best = None
    for prop in sim.properties_in_radius(pos.x, pos.y, pos.z, r=search_radius):
        services = {
            str(service or "").strip().lower()
            for service in _site_services_for_property(prop)
            if str(service or "").strip()
        }
        if not services.intersection(_LODGING_SERVICE_IDS):
            continue
        focus = _property_focus_position(prop)
        if not focus:
            continue
        fx, fy, fz = focus
        if int(fz) != int(pos.z):
            continue
        access = _cached_behavior_property_access(
            sim,
            actor_eid,
            prop,
            x=int(fx),
            y=int(fy),
            z=int(fz),
        )
        if not access.can_use_services and not access.permitted:
            continue

        service = None
        service_score = float("-inf")
        if "rest" in services and liquid_credits >= _REST_SERVICE_COST:
            service = "rest"
            service_score = (
                10.0
                + (energy_gap * 24.0)
                + (safety_gap * 10.0)
                + (social_gap * 5.0)
                + (health_gap * 16.0)
                + (night_bias * 6.0)
            )
        if "shelter" in services:
            shelter_score = (
                12.0
                + (energy_gap * 14.0)
                + (safety_gap * 20.0)
                + (social_gap * 6.0)
                + (health_gap * 9.0)
                + (night_bias * 8.0)
            )
            if shelter_score > service_score + 1.0 or service is None:
                service = "shelter"
                service_score = shelter_score
        if service is None:
            continue

        distance = _manhattan(pos.x, pos.y, fx, fy)
        score = max(
            0.0,
            service_score
            + (energy_gap * 22.0)
            + (safety_gap * 18.0)
            + (health_gap * 12.0)
            - (distance * 1.85),
        )
        if isinstance(home, (tuple, list)) and len(home) >= 3 and int(home[2]) == int(pos.z):
            score -= 14.0 if service == "shelter" else 10.0
        elif not home:
            score += 6.0 + (night_bias * 4.0)

        property_id = str(prop.get("id", "")).strip() or None
        if preferred_property_id and property_id and str(preferred_property_id).strip() == property_id:
            score += float(max(0.0, preferred_score_bonus or 0.0))
        candidate = {
            "property_id": property_id,
            "property_name": str(prop.get("name", prop.get("id", "site"))).strip() or "site",
            "target": (int(fx), int(fy), int(fz)),
            "distance": int(distance),
            "score": float(score),
            "service": service,
            "services": tuple(sorted(services.intersection(_LODGING_SERVICE_IDS))),
            "credits_cost": int(_REST_SERVICE_COST if service == "rest" else 0),
        }
        if best is None or candidate["score"] > best["score"]:
            best = candidate
    cache_ttl = _LODGING_TARGET_CACHE_TICKS + (abs(int(actor_eid)) % (_LODGING_TARGET_CACHE_JITTER + 1))
    cache[cache_key] = {
        "expires_tick": current_tick + cache_ttl,
        "result": dict(best) if isinstance(best, dict) else None,
    }
    return best


def _shopping_cooldowns(sim):
    state = getattr(sim, "npc_shopping_cooldowns", None)
    if not isinstance(state, dict):
        state = {}
        sim.npc_shopping_cooldowns = state
    return state


def _shopping_ticks_per_hour(sim):
    traits = getattr(sim, "world_traits", {})
    clock = traits.get("clock", {}) if isinstance(traits, dict) else {}
    if not isinstance(clock, dict):
        clock = {}
    try:
        return max(60, int(clock.get("ticks_per_hour", 600) or 600))
    except (TypeError, ValueError):
        return 600


def _shopping_wallet_buffer(sim, actor_eid):
    profile = sim.ecs.get(FinancialProfile).get(actor_eid) if sim is not None else None
    if profile is None:
        return 24
    try:
        return max(0, int(getattr(profile, "wallet_buffer", 0) or 0))
    except (TypeError, ValueError):
        return 24


def _shopping_actor_role_career(sim, actor_eid):
    ai = sim.ecs.get(AI).get(actor_eid) if sim is not None else None
    occupation = sim.ecs.get(Occupation).get(actor_eid) if sim is not None else None
    role = _behavior_token(getattr(ai, "role", "")) or "civilian"
    career = _behavior_token(getattr(occupation, "career", ""))
    return role, career


def _shopping_item_tags(item_id, row=None):
    tags = set(row.get("tags", ())) if isinstance(row, dict) else set()
    if not tags:
        tags.update(_item_tags({"item_id": item_id, "metadata": {}}))
    item_def = ITEM_CATALOG.get(str(item_id or "").strip().lower(), {})
    tags.update(str(tag).strip().lower() for tag in item_def.get("tags", ()) if str(tag).strip())
    category = str(item_def.get("category", "") or "").strip().lower()
    if category:
        tags.add(category)
    family = str(item_def.get("appearance_family", "") or "").strip().lower()
    if family:
        tags.add(family)
    if item_def.get("weapon_id"):
        tags.add("weapon")
    if isinstance(item_def.get("armor"), dict) and float(item_def["armor"].get("damage_reduction", 0.0) or 0.0) > 0.0:
        tags.add("armor")
    return frozenset(tags)


def _shopping_restore_hp(item_def):
    total = 0
    for effect in tuple((item_def or {}).get("effects", ()) or ()):
        if not isinstance(effect, dict):
            continue
        if str(effect.get("type", "")).strip().lower() != "restore_hp":
            continue
        try:
            total += max(0, int(effect.get("delta", 0) or 0))
        except (TypeError, ValueError):
            continue
    return int(total)


def _inventory_count_matching(inventory, *, item_id=None, tags=frozenset()):
    if not inventory:
        return 0
    item_id = str(item_id or "").strip().lower()
    tags = frozenset(str(tag).strip().lower() for tag in tuple(tags or ()) if str(tag).strip())
    count = 0
    for entry in tuple(getattr(inventory, "items", ()) or ()):
        entry_item_id = str(entry.get("item_id", "") or "").strip().lower()
        if item_id and entry_item_id != item_id:
            continue
        if tags:
            entry_tags = _shopping_item_tags(entry_item_id)
            if not entry_tags.intersection(tags):
                continue
        count += int(max(1, entry.get("quantity", 1) or 1))
    return int(count)


def _shopping_item_is_repeatable(item_id, tags):
    item_def = ITEM_CATALOG.get(str(item_id or "").strip().lower(), {})
    stack_max = max(1, int(item_def.get("stack_max", 1) or 1))
    if stack_max > 1:
        return True
    return bool(frozenset(tags).intersection({"consumable", "food", "drink", "medical", "ammo", "token", "social"}))


def _shopping_quirk_matches(quirk_id, item_id, tags):
    profile = _SHOPPING_QUIRK_PROFILES.get(str(quirk_id or "").strip().lower())
    if not isinstance(profile, dict):
        return False
    clean_item_id = str(item_id or "").strip().lower()
    if clean_item_id in profile.get("item_ids", frozenset()):
        return True
    return bool(frozenset(tags).intersection(profile.get("tags", frozenset())))


def _shopping_role_motivates_gear(role, career, tags):
    role = _behavior_token(role)
    career = _behavior_token(career)
    tags = frozenset(tags)
    role_text = f"{role} {career}"
    if tags.intersection({"weapon", "armor", "ammo"}) and any(token in role_text for token in ("guard", "security", "patrol", "officer", "scout", "runner", "courier")):
        return True
    if tags.intersection({"medical"}) and any(token in role_text for token in ("medic", "doctor", "nurse", "pharmac", "street_doc", "clinic")):
        return True
    if tags.intersection({"tool", "device"}) and any(token in role_text for token in ("mechanic", "engineer", "technician", "scav", "fence", "dealer", "fixer")):
        return True
    return False


def _shopping_interest_for_row(sim, actor_eid, row, *, needs=None, vitality=None, work_active=False):
    inventory = sim.ecs.get(Inventory).get(actor_eid) if sim is not None else None
    if inventory is None or not isinstance(row, dict):
        return None
    item_id = str(row.get("item_id", "") or "").strip().lower()
    item_def = ITEM_CATALOG.get(item_id)
    if not item_id or not isinstance(item_def, dict) or is_credstick_item(item_id):
        return None
    price = max(1, int(row.get("price", 0) or 0))
    wallet = _inventory_liquid_credits(inventory)
    if price > wallet:
        return None
    tags = _shopping_item_tags(item_id, row=row)
    repeatable = _shopping_item_is_repeatable(item_id, tags)
    if not repeatable and _inventory_count_matching(inventory, item_id=item_id) > 0:
        return None
    if not _inventory_can_accept_item(inventory, item_id, owner_eid=actor_eid):
        return None

    role, career = _shopping_actor_role_career(sim, actor_eid)
    profile = _actor_behavior_profile(sim, actor_eid)
    preferences = getattr(profile, "preferences", {}) if profile is not None else {}
    preferences = preferences if isinstance(preferences, dict) else {}
    wallet_buffer = max(wallet, _shopping_wallet_buffer(sim, actor_eid))
    wallet_after = wallet - price
    provision_behavior = _actor_behavior_value(sim, actor_eid, BEHAVIOR_BUY_PROVISIONS, 0.0)
    practical_behavior = _actor_behavior_value(sim, actor_eid, BEHAVIOR_BUY_PRACTICAL_GEAR, 0.0)
    quirk_behavior = _actor_behavior_value(sim, actor_eid, BEHAVIOR_BUY_QUIRKY_ITEMS, 0.0)

    raw_hunger = 100.0 if needs is None else float(getattr(needs, "hunger", 100.0) or 100.0)
    raw_thirst = 100.0 if needs is None else float(getattr(needs, "thirst", 100.0) or 100.0)
    health_gap = 0.0
    if vitality is not None and not bool(getattr(vitality, "downed", False)):
        max_hp = max(1, int(getattr(vitality, "max_hp", 1) or 1))
        hp = max(0, int(getattr(vitality, "hp", max_hp) or max_hp))
        health_gap = _clamp_behavior_value(1.0 - (float(hp) / float(max_hp)))

    candidates = []
    food_count = _inventory_count_matching(inventory, tags={"food"})
    drink_count = _inventory_count_matching(inventory, tags={"drink"})
    medical_count = _inventory_count_matching(inventory, tags={"medical"})
    restore_hp = _shopping_restore_hp(item_def)
    if provision_behavior >= 0.05:
        if "food" in tags and (raw_hunger < 72.0 or food_count <= 0):
            urgent = raw_hunger < 30.0
            if food_count < (3 if urgent else 2):
                reserve = 0 if urgent else min(4, max(1, int(wallet_buffer * 0.08)))
                if wallet_after >= reserve:
                    candidates.append({
                        "motive": BEHAVIOR_BUY_PROVISIONS,
                        "score": (18.0 + max(0.0, 78.0 - raw_hunger) * 0.78 + provision_behavior * 18.0) * (1.25 if urgent else 1.0),
                        "urgent": bool(urgent),
                        "reserve": int(reserve),
                    })
        if "drink" in tags and (raw_thirst < 76.0 or drink_count <= 0):
            urgent = raw_thirst < 30.0
            if drink_count < (3 if urgent else 2):
                reserve = 0 if urgent else min(4, max(1, int(wallet_buffer * 0.08)))
                if wallet_after >= reserve:
                    candidates.append({
                        "motive": BEHAVIOR_BUY_PROVISIONS,
                        "score": (18.0 + max(0.0, 82.0 - raw_thirst) * 0.82 + provision_behavior * 18.0) * (1.25 if urgent else 1.0),
                        "urgent": bool(urgent),
                        "reserve": int(reserve),
                    })
        if "medical" in tags and restore_hp > 0 and (health_gap >= 0.16 or medical_count <= 0):
            urgent = health_gap >= 0.48
            if medical_count < (3 if urgent else 2):
                reserve = 0 if urgent else min(5, max(1, int(wallet_buffer * 0.1)))
                if wallet_after >= reserve:
                    candidates.append({
                        "motive": BEHAVIOR_BUY_PROVISIONS,
                        "score": (14.0 + health_gap * 70.0 + provision_behavior * 14.0 + min(12.0, restore_hp * 0.2)) * (1.25 if urgent else 1.0),
                        "urgent": bool(urgent),
                        "reserve": int(reserve),
                    })

    gear_tags = {"weapon", "armor", "tool", "device", "ammo", "medical"}
    if practical_behavior >= 0.05 and tags.intersection(gear_tags):
        role_motivated = _shopping_role_motivates_gear(role, career, tags)
        reserve = max(4, int(wallet_buffer * (0.12 if role_motivated else 0.2)))
        if wallet_after >= reserve:
            duplicate_ok = bool(tags.intersection({"ammo", "medical"}))
            if duplicate_ok or _inventory_count_matching(inventory, item_id=item_id) <= 0:
                practical_score = 8.0 + practical_behavior * 26.0 + (12.0 if role_motivated else 0.0)
                if "armor" in tags:
                    current = sim.ecs.get(ArmorLoadout).get(actor_eid)
                    current_reduction = float(getattr(current, "damage_reduction", 0.0) or 0.0) if current else 0.0
                    armor = item_def.get("armor") if isinstance(item_def.get("armor"), dict) else {}
                    new_reduction = float(armor.get("damage_reduction", 0.0) or 0.0)
                    if new_reduction <= current_reduction and not role_motivated:
                        practical_score -= 8.0
                    else:
                        practical_score += max(0.0, (new_reduction - current_reduction) * 36.0)
                if "weapon" in tags:
                    loadout = sim.ecs.get(WeaponLoadout).get(actor_eid)
                    if loadout is None or not loadout.current_weapon():
                        practical_score += 14.0
                    elif not role_motivated:
                        practical_score -= 8.0
                if practical_score > 0.0:
                    candidates.append({
                        "motive": BEHAVIOR_BUY_PRACTICAL_GEAR,
                        "score": practical_score,
                        "urgent": False,
                        "reserve": int(reserve),
                    })

    quirk_id = str(preferences.get("shopping_quirk_id", "") or "").strip().lower()
    impulse = bool(preferences.get("shopping_impulsive", False))
    if quirk_id and quirk_behavior >= 0.05 and _shopping_quirk_matches(quirk_id, item_id, tags):
        cooldowns = _shopping_cooldowns(sim)
        cooldown_key = (int(actor_eid), quirk_id)
        cooldown_due = int(cooldowns.get(cooldown_key, 0) or 0) <= int(getattr(sim, "tick", 0) or 0)
        comfortable_reserve = max(8, int(wallet_buffer * 0.32))
        comfortable = wallet_after >= comfortable_reserve and wallet >= max(price * 2, price + 6)
        can_impulse = impulse and cooldown_due
        if comfortable or can_impulse:
            candidates.append({
                "motive": BEHAVIOR_BUY_QUIRKY_ITEMS,
                "score": 7.0 + quirk_behavior * 22.0 + (12.0 if can_impulse and not comfortable else 0.0),
                "urgent": False,
                "reserve": 0 if can_impulse else int(comfortable_reserve),
                "quirk_id": quirk_id,
                "impulse": bool(can_impulse and not comfortable),
            })

    if not candidates:
        return None
    best = max(candidates, key=lambda entry: (float(entry.get("score", 0.0)), -int(entry.get("reserve", 0))))
    if bool(work_active) and not bool(best.get("urgent")):
        return None
    best = dict(best)
    best["price"] = int(price)
    best["wallet"] = int(wallet)
    best["wallet_after"] = int(wallet_after)
    best["item_id"] = item_id
    best["tags"] = tuple(sorted(tags))
    return best


def _find_shopping_target(sim, actor_eid, pos, *, radius=None, work_active=False, preferred_property_id=None, preferred_score_bonus=0.0):
    if sim is None or pos is None:
        return None
    trade_system = getattr(sim, "trade_system", None)
    if trade_system is None or not hasattr(trade_system, "npc_purchase_options"):
        return None
    vitality = sim.ecs.get(Vitality).get(actor_eid)
    if vitality is not None and bool(getattr(vitality, "downed", False)):
        return None
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if inventory is None or _inventory_liquid_credits(inventory) <= 0:
        return None

    if radius is None:
        radius = _behavior_preference(sim, actor_eid, "shopping_search_radius", 10)
    try:
        radius = max(2, int(radius))
    except (TypeError, ValueError):
        radius = 10

    needs = sim.ecs.get(NPCNeeds).get(actor_eid)
    options = trade_system.npc_purchase_options(
        actor_eid,
        pos,
        radius=radius,
        preferred_property_id=preferred_property_id,
    )
    best = None
    for row in options:
        interest = _shopping_interest_for_row(
            sim,
            actor_eid,
            row,
            needs=needs,
            vitality=vitality,
            work_active=work_active,
        )
        if not interest:
            continue
        distance = int(row.get("distance", 0) or 0)
        property_id = str(row.get("property_id", "") or "").strip() or None
        score = float(interest.get("score", 0.0) or 0.0) - (distance * 1.15)
        score += _business_target_reputation_bonus(
            sim,
            actor_eid,
            property_id,
            purpose="shopping",
            urgency=0.7 if interest.get("urgent") else 0.2,
        )
        if preferred_property_id and property_id and str(preferred_property_id).strip() == property_id:
            score += float(max(0.0, preferred_score_bonus or 0.0))
        candidate = {
            "property_id": property_id,
            "property_name": str(row.get("property_name", property_id or "store")).strip() or "store",
            "store_name": str(row.get("store_name", row.get("property_name", "store"))).strip() or "store",
            "archetype": str(row.get("archetype", "") or "").strip().lower(),
            "target": tuple(row.get("target") or (int(pos.x), int(pos.y), int(pos.z))),
            "distance": int(distance),
            "score": float(score),
            "item_id": str(row.get("item_id", "") or "").strip().lower(),
            "item_name": str(row.get("item_name", row.get("item_id", "item"))).strip() or "item",
            "price": int(row.get("price", 0) or 0),
            "motive": str(interest.get("motive", "") or "").strip().lower(),
            "quirk_id": str(interest.get("quirk_id", "") or "").strip().lower(),
            "impulse": bool(interest.get("impulse", False)),
            "urgent": bool(interest.get("urgent", False)),
        }
        if best is None or (
            candidate["score"],
            -candidate["distance"],
            -candidate["price"],
            candidate["item_id"],
        ) > (
            best["score"],
            -best["distance"],
            -best["price"],
            best["item_id"],
        ):
            best = candidate
    return best


def _registered_item_action_runtime(sim):
    runtime = getattr(sim, "item_action_system", None)
    if runtime is not None and hasattr(runtime, "_toggle_weapon_item"):
        return runtime
    item_system = getattr(sim, "item_system", None)
    runtime = getattr(item_system, "item_actions", None)
    if runtime is not None and hasattr(runtime, "_toggle_weapon_item"):
        return runtime
    for system in tuple(getattr(sim, "systems", ()) or ()):
        runtime = getattr(system, "item_actions", None)
        if runtime is not None and hasattr(runtime, "_toggle_weapon_item"):
            return runtime
    return None


def _auto_equip_npc_purchase(sim, actor_eid, purchase):
    if not isinstance(purchase, dict):
        return False
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if inventory is None:
        return False
    entry = inventory.find(instance_id=purchase.get("instance_id"))
    if not entry:
        return False
    item_id = str(entry.get("item_id", "") or "").strip().lower()
    item_def = ITEM_CATALOG.get(item_id)
    if not isinstance(item_def, dict):
        return False
    runtime = _registered_item_action_runtime(sim)
    if runtime is None:
        return False
    if item_def.get("weapon_id"):
        loadout = sim.ecs.get(WeaponLoadout).get(actor_eid)
        if loadout is None or not loadout.current_weapon():
            return bool(runtime._toggle_weapon_item(actor_eid, entry, item_def, reason="npc_shopping"))
        return False
    armor = item_def.get("armor") if isinstance(item_def.get("armor"), dict) else None
    if armor:
        current = sim.ecs.get(ArmorLoadout).get(actor_eid)
        current_reduction = float(getattr(current, "damage_reduction", 0.0) or 0.0) if current else 0.0
        try:
            new_reduction = float(armor.get("damage_reduction", 0.0) or 0.0)
        except (TypeError, ValueError):
            new_reduction = 0.0
        if new_reduction > current_reduction:
            return bool(runtime._toggle_armor_item(actor_eid, entry, item_def, reason="npc_shopping"))
    return False


def _resolve_npc_shopping_at_actor(sim, actor_eid, pos=None, *, preferred_property_id=None, preferred_item_id=None, motive="", quirk_id="", impulse=False):
    if pos is None:
        pos = sim.ecs.get(Position).get(actor_eid)
    if pos is None:
        return None
    target = _find_shopping_target(
        sim,
        actor_eid,
        pos,
        radius=2,
        work_active=False,
        preferred_property_id=preferred_property_id,
        preferred_score_bonus=10.0,
    )
    if target is None:
        return None
    if preferred_item_id and str(target.get("item_id", "") or "").strip().lower() != str(preferred_item_id or "").strip().lower():
        options = getattr(sim.trade_system, "npc_purchase_options", lambda *args, **kwargs: [])(
            actor_eid,
            pos,
            radius=2,
            preferred_property_id=preferred_property_id,
        )
        needs = sim.ecs.get(NPCNeeds).get(actor_eid)
        vitality = sim.ecs.get(Vitality).get(actor_eid)
        for row in options:
            if str(row.get("item_id", "") or "").strip().lower() != str(preferred_item_id or "").strip().lower():
                continue
            interest = _shopping_interest_for_row(sim, actor_eid, row, needs=needs, vitality=vitality, work_active=False)
            if interest:
                target = {
                    **target,
                    "property_id": str(row.get("property_id", "") or "").strip() or target.get("property_id"),
                    "item_id": str(row.get("item_id", "") or "").strip().lower(),
                    "motive": str(interest.get("motive", motive or "") or "").strip().lower(),
                    "quirk_id": str(interest.get("quirk_id", quirk_id or "") or "").strip().lower(),
                    "impulse": bool(interest.get("impulse", impulse)),
                }
                break
    property_id = str(target.get("property_id", "") or "").strip()
    item_id = str(target.get("item_id", "") or "").strip().lower()
    if not property_id or not item_id:
        return None
    purchase = sim.trade_system.npc_buy_item(
        actor_eid,
        property_id,
        item_id,
        motive=str(target.get("motive", motive or "") or "").strip().lower(),
        quirk_id=str(target.get("quirk_id", quirk_id or "") or "").strip().lower(),
        impulse=bool(target.get("impulse", impulse)),
    )
    if isinstance(purchase, dict):
        if purchase.get("impulse"):
            cooldown = max(
                _shopping_ticks_per_hour(sim) * 6,
                int(_behavior_preference(sim, actor_eid, "shopping_impulse_cooldown_ticks", _shopping_ticks_per_hour(sim) * 6) or 0),
            )
            key = (int(actor_eid), str(purchase.get("quirk_id", "") or "").strip().lower())
            _shopping_cooldowns(sim)[key] = int(getattr(sim, "tick", 0) or 0) + int(cooldown)
        purchase["auto_equipped"] = bool(_auto_equip_npc_purchase(sim, actor_eid, purchase))
    return purchase


def _find_safe_spot_target(sim, actor_eid, pos, *, radius=None, preferred_property_id=None, preferred_score_bonus=0.0):
    lead = _best_opportunity_lead(sim, actor_eid, "safe_spot")
    if isinstance(lead, dict):
        if preferred_property_id and str(preferred_property_id).strip() and str(lead.get("property_id", "")).strip() == str(preferred_property_id).strip():
            lead["score"] = float(lead.get("score", 0.0) or 0.0) + float(max(0.0, preferred_score_bonus or 0.0))
        return lead
    if not pos:
        return None

    needs = sim.ecs.get(NPCNeeds).get(actor_eid)
    if needs is None:
        return None

    vitality = sim.ecs.get(Vitality).get(actor_eid)
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    liquid_credits = _inventory_liquid_credits(inventory)

    energy_gap = _clamp_behavior_value((100.0 - float(getattr(needs, "energy", 85.0) or 85.0)) / 100.0, default=0.12)
    safety_gap = _clamp_behavior_value((100.0 - float(getattr(needs, "safety", 85.0) or 85.0)) / 100.0, default=0.12)
    social_gap = _clamp_behavior_value((100.0 - float(getattr(needs, "social", 70.0) or 70.0)) / 100.0, default=0.08)
    if vitality is not None and not bool(getattr(vitality, "downed", False)):
        max_hp = max(1, int(getattr(vitality, "max_hp", 1) or 1))
        hp = max(0, int(getattr(vitality, "hp", max_hp) or max_hp))
        health_gap = _clamp_behavior_value(1.0 - (float(hp) / float(max_hp)))
    else:
        health_gap = 0.0
    live_heat = _behavior_live_street_heat(sim, actor_eid)
    night_bias = 1.0 if (int(_world_hour(sim)) >= 21 or int(_world_hour(sim)) < 6) else 0.0

    if max(safety_gap, health_gap, live_heat, energy_gap * 0.55, night_bias * 0.25) <= 0.08:
        return None

    search_radius = radius
    if search_radius is None:
        search_radius = _behavior_preference(
            sim,
            actor_eid,
            "safe_spot_search_radius",
            _behavior_preference(sim, actor_eid, "shelter_search_radius", 12),
        )
    try:
        search_radius = max(4, int(search_radius))
    except (TypeError, ValueError):
        search_radius = 12

    best = None
    for row in _nearby_opportunity_rows(sim, pos, radius=search_radius, lead_kind="safe_spot", current_tick=int(getattr(sim, "tick", 0) or 0)):
        target = row.get("target")
        if not isinstance(target, (tuple, list)) or len(target) < 3:
            continue
        services = {
            str(service or "").strip().lower()
            for service in tuple(row.get("services", ()) or ())
            if str(service or "").strip()
        }
        distance = _manhattan(pos.x, pos.y, int(target[0]), int(target[1]))
        property_id = str(row.get("property_id", "")).strip() or None
        property_name = str(row.get("property_name", property_id or "site")).strip() or "site"

        candidate = None
        best_local_score = float("-inf")
        if services.intersection(_LODGING_SERVICE_IDS):
            service = None
            service_score = float("-inf")
            if "rest" in services and liquid_credits >= _REST_SERVICE_COST:
                service = "rest"
                service_score = (
                    8.0
                    + (energy_gap * 18.0)
                    + (safety_gap * 18.0)
                    + (social_gap * 5.0)
                    + (health_gap * 10.0)
                    + (live_heat * 22.0)
                    + (night_bias * 4.0)
                )
            if "shelter" in services:
                shelter_score = (
                    12.0
                    + (energy_gap * 14.0)
                    + (safety_gap * 22.0)
                    + (social_gap * 6.0)
                    + (health_gap * 8.0)
                    + (live_heat * 26.0)
                    + (night_bias * 8.0)
                )
                if shelter_score > service_score + 1.0 or service is None:
                    service = "shelter"
                    service_score = shelter_score
            if service is not None:
                score = max(0.0, service_score - (distance * 1.65))
                candidate = {
                    "property_id": property_id,
                    "property_name": property_name,
                    "target": (int(target[0]), int(target[1]), int(target[2])),
                    "distance": int(distance),
                    "score": float(score),
                    "safe_kind": "lodging",
                    "service": service,
                    "services": tuple(sorted(services.intersection(_LODGING_SERVICE_IDS))),
                    "confidence": min(0.95, 0.5 + max(safety_gap, live_heat, health_gap) * 0.32),
                    "verification_required": True,
                    "service_id": service,
                    "opportunity_tag": "safe_spot",
                }
                best_local_score = float(score)
        if "medical" in set(row.get("opportunity_tags", ()) or ()):
            med_score = max(
                0.0,
                10.0
                + (safety_gap * 20.0)
                + (health_gap * 26.0)
                + (live_heat * 12.0)
                - (distance * 1.75),
            )
            if med_score > best_local_score:
                candidate = {
                    "property_id": property_id,
                    "property_name": property_name,
                    "archetype": str(row.get("archetype", "") or "").strip().lower(),
                    "target": (int(target[0]), int(target[1]), int(target[2])),
                    "distance": int(distance),
                    "score": float(med_score),
                    "safe_kind": "medical",
                    "service": "medical",
                    "confidence": min(0.95, 0.52 + max(safety_gap, health_gap, live_heat) * 0.34),
                    "verification_required": True,
                    "service_id": "medical",
                    "opportunity_tag": "safe_spot",
                }
                best_local_score = float(med_score)
        if candidate is None:
            fallback_score = max(
                0.0,
                5.0
                + (safety_gap * 16.0)
                + (live_heat * 18.0)
                + (night_bias * 5.0)
                - (distance * 1.5),
            )
            candidate = {
                "property_id": property_id,
                "property_name": property_name,
                "target": (int(target[0]), int(target[1]), int(target[2])),
                "distance": int(distance),
                "score": float(fallback_score),
                "safe_kind": "hideout",
                "service": None,
                "confidence": min(0.9, 0.48 + max(safety_gap, live_heat) * 0.28),
                "verification_required": True,
                "opportunity_tag": "safe_spot",
            }
        if preferred_property_id and property_id and str(preferred_property_id).strip() == property_id:
            candidate["score"] = float(candidate.get("score", 0.0) or 0.0) + float(max(0.0, preferred_score_bonus or 0.0))
        if best is None or float(candidate.get("score", 0.0) or 0.0) > float(best.get("score", 0.0) or 0.0):
            best = candidate
    if best is not None:
        _remember_opportunity_lead(
            sim,
            actor_eid,
            "safe_spot",
            best,
            source_kind="surface_snapshot",
            stale_after_ticks=90,
            expires_ticks=360,
        )
    return best


def _find_safe_spot_target_exact(sim, actor_eid, pos, *, radius=None, preferred_property_id=None, preferred_score_bonus=0.0):
    if not pos:
        return None

    needs = sim.ecs.get(NPCNeeds).get(actor_eid)
    if needs is None:
        return None

    vitality = sim.ecs.get(Vitality).get(actor_eid)
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    liquid_credits = _inventory_liquid_credits(inventory)

    energy_gap = _clamp_behavior_value((100.0 - float(getattr(needs, "energy", 85.0) or 85.0)) / 100.0, default=0.12)
    safety_gap = _clamp_behavior_value((100.0 - float(getattr(needs, "safety", 85.0) or 85.0)) / 100.0, default=0.12)
    social_gap = _clamp_behavior_value((100.0 - float(getattr(needs, "social", 70.0) or 70.0)) / 100.0, default=0.08)
    if vitality is not None and not bool(getattr(vitality, "downed", False)):
        max_hp = max(1, int(getattr(vitality, "max_hp", 1) or 1))
        hp = max(0, int(getattr(vitality, "hp", max_hp) or max_hp))
        health_gap = _clamp_behavior_value(1.0 - (float(hp) / float(max_hp)))
    else:
        health_gap = 0.0
    live_heat = _behavior_live_street_heat(sim, actor_eid)
    night_bias = 1.0 if (int(_world_hour(sim)) >= 21 or int(_world_hour(sim)) < 6) else 0.0

    if max(safety_gap, health_gap, live_heat, energy_gap * 0.55, night_bias * 0.25) <= 0.08:
        return None

    search_radius = radius
    if search_radius is None:
        search_radius = _behavior_preference(
            sim,
            actor_eid,
            "safe_spot_search_radius",
            _behavior_preference(sim, actor_eid, "shelter_search_radius", 12),
        )
    try:
        search_radius = max(4, int(search_radius))
    except (TypeError, ValueError):
        search_radius = 12

    best = None
    for prop in sim.properties_in_radius(pos.x, pos.y, pos.z, r=search_radius):
        metadata = prop.get("metadata", {}) if isinstance(prop, dict) else {}
        if not isinstance(metadata, dict):
            metadata = {}
        archetype = _behavior_token(metadata.get("archetype"))
        services = {
            str(service or "").strip().lower()
            for service in _site_services_for_property(prop)
            if str(service or "").strip()
        }
        focus = _property_focus_position(prop)
        if not focus:
            continue
        fx, fy, fz = focus
        if int(fz) != int(pos.z):
            continue
        access = _cached_behavior_property_access(
            sim,
            actor_eid,
            prop,
            x=int(fx),
            y=int(fy),
            z=int(fz),
        )
        if not access.can_use_services and not access.permitted:
            continue

        distance = _manhattan(pos.x, pos.y, fx, fy)
        property_id = str(prop.get("id", "")).strip() or None
        property_name = str(prop.get("name", prop.get("id", "site"))).strip() or "site"

        candidate = None
        best_local_score = float("-inf")
        if services.intersection(_LODGING_SERVICE_IDS):
            service = None
            service_score = float("-inf")
            if "rest" in services and liquid_credits >= _REST_SERVICE_COST:
                service = "rest"
                service_score = (
                    8.0
                    + (energy_gap * 18.0)
                    + (safety_gap * 18.0)
                    + (social_gap * 5.0)
                    + (health_gap * 10.0)
                    + (live_heat * 22.0)
                    + (night_bias * 4.0)
                )
            if "shelter" in services:
                shelter_score = (
                    12.0
                    + (energy_gap * 10.0)
                    + (safety_gap * 22.0)
                    + (social_gap * 4.0)
                    + (health_gap * 6.0)
                    + (live_heat * 26.0)
                    + (night_bias * 5.0)
                )
                if shelter_score > service_score + 1.0 or service is None:
                    service = "shelter"
                    service_score = shelter_score
            if service is not None:
                score = max(
                    0.0,
                    service_score
                    + (safety_gap * 18.0)
                    + (health_gap * 8.0)
                    + (live_heat * 20.0)
                    - (distance * 1.75),
                )
                best_local_score = score
                candidate = {
                    "property_id": property_id,
                    "property_name": property_name,
                    "target": (int(fx), int(fy), int(fz)),
                    "distance": int(distance),
                    "score": float(score),
                    "safe_kind": "lodging",
                    "service": service,
                    "archetype": archetype,
                }

        if archetype in _MEDICAL_ARCHETYPES and health_gap > 0.08:
            medical_score = max(
                0.0,
                10.0
                + (health_gap * 34.0)
                + (safety_gap * 10.0)
                + (live_heat * 10.0)
                - (distance * 1.95),
            )
            if medical_score > best_local_score or candidate is None:
                best_local_score = medical_score
                candidate = {
                    "property_id": property_id,
                    "property_name": property_name,
                    "target": (int(fx), int(fy), int(fz)),
                    "distance": int(distance),
                    "score": float(medical_score),
                    "safe_kind": "medical",
                    "service": "medical",
                    "archetype": archetype,
                }

        if candidate is None:
            continue
        if preferred_property_id and property_id and str(preferred_property_id).strip() == property_id:
            candidate["score"] = float(candidate.get("score", 0.0) or 0.0) + float(max(0.0, preferred_score_bonus or 0.0))
        if best is None or float(candidate.get("score", 0.0) or 0.0) > float(best.get("score", 0.0) or 0.0):
            best = candidate
    return best


def _receive_medical_aid_at_actor(sim, actor_eid, pos=None, *, preferred_property_id=None):
    if pos is None:
        pos = sim.ecs.get(Position).get(actor_eid)
    if not pos:
        return None

    vitality = sim.ecs.get(Vitality).get(actor_eid)
    if vitality is None or bool(getattr(vitality, "downed", False)):
        return None
    max_hp = max(1, int(getattr(vitality, "max_hp", 1) or 1))
    before_hp = max(0, int(getattr(vitality, "hp", max_hp) or max_hp))
    if before_hp >= max_hp:
        return None

    current_lead = _best_opportunity_lead(sim, actor_eid, "medical")
    target = _find_medical_aid_target_exact(
        sim,
        actor_eid,
        pos,
        radius=2,
        preferred_property_id=preferred_property_id,
        preferred_score_bonus=22.0 if preferred_property_id else 0.0,
    )
    if not target:
        if current_lead is not None:
            _mark_opportunity_failure(
                sim,
                actor_eid,
                "medical",
                lead=current_lead,
                cooldown_ticks=180,
                reason="medical_site_unavailable",
            )
        return None

    heal_amount = max(3, int(round(float(max_hp) * 0.22)))
    vitality.hp = min(max_hp, before_hp + heal_amount)
    needs = sim.ecs.get(NPCNeeds).get(actor_eid)
    if needs:
        needs.safety = _clamp_need_value(float(getattr(needs, "safety", 70.0) or 70.0) + 8.0)
        needs.energy = _clamp_need_value(float(getattr(needs, "energy", 70.0) or 70.0) + 3.0)

    healed = max(0, int(vitality.hp) - before_hp)
    sim.emit(Event(
        "npc_medical_aid_received",
        npc_eid=actor_eid,
        property_id=target.get("property_id"),
        property_name=target.get("property_name"),
        archetype=target.get("archetype"),
        covert_referral=bool(target.get("covert_referral")),
        healed_hp=int(healed),
        before_hp=int(before_hp),
        after_hp=int(vitality.hp),
        x=int(pos.x),
        y=int(pos.y),
        z=int(pos.z),
    ))
    _remember_opportunity_lead(
        sim,
        actor_eid,
        "medical",
        dict(target),
        source_kind="verified_arrival",
        stale_after_ticks=120,
        expires_ticks=480,
    )
    _note_opportunity_success(sim, actor_eid, "medical", lead=target)
    return {
        "property_id": target.get("property_id"),
        "property_name": target.get("property_name"),
        "healed_hp": int(healed),
        "after_hp": int(vitality.hp),
        "covert_referral": bool(target.get("covert_referral")),
    }


def _receive_lodging_at_actor(sim, actor_eid, pos=None):
    if pos is None:
        pos = sim.ecs.get(Position).get(actor_eid)
    if not pos:
        return None

    current_lead = _best_opportunity_lead(sim, actor_eid, "lodging")
    target = _find_lodging_target_exact(sim, actor_eid, pos, radius=2)
    if not target:
        if current_lead is not None:
            _mark_opportunity_failure(
                sim,
                actor_eid,
                "lodging",
                lead=current_lead,
                cooldown_ticks=240,
                reason="lodging_unavailable",
            )
        return None

    needs = sim.ecs.get(NPCNeeds).get(actor_eid)
    if needs is None:
        return None
    vitality = sim.ecs.get(Vitality).get(actor_eid)
    effects = sim.ecs.get(StatusEffects).get(actor_eid)
    inventory = sim.ecs.get(Inventory).get(actor_eid)

    service = str(target.get("service", "shelter") or "shelter").strip().lower()
    credits_spent = 0
    if service == "rest":
        credits_spent = _spend_inventory_credits(inventory, _REST_SERVICE_COST)
        if credits_spent < _REST_SERVICE_COST:
            if "shelter" in set(target.get("services", ()) or ()):
                service = "shelter"
                credits_spent = 0
            else:
                return None

    energy_gain = safety_gain = social_gain = hp_gain = 0
    if service == "rest":
        energy_gain = min(40, max(10, int(round((100.0 - float(needs.energy)) * 0.7))))
        safety_gain = min(30, max(8, int(round((100.0 - float(needs.safety)) * 0.55))))
        social_gain = min(12, max(3, int(round((75.0 - float(needs.social)) * 0.25))))
        if vitality:
            missing_hp = max(0, int(vitality.max_hp) - int(vitality.hp))
            hp_gain = min(missing_hp, max(5, int(round(missing_hp * 0.6))))
    else:
        if float(needs.energy) < 95.0:
            energy_gain = min(18, max(4, int(round((100.0 - float(needs.energy)) * 0.32))))
        if float(needs.safety) < 92.0:
            safety_gain = min(14, max(3, int(round((100.0 - float(needs.safety)) * 0.24))))
        if float(needs.social) < 70.0:
            social_gain = min(8, max(2, int(round((72.0 - float(needs.social)) * 0.18))))
        if vitality and int(vitality.hp) < int(vitality.max_hp):
            hp_gain = min(2, int(vitality.max_hp) - int(vitality.hp))

    if energy_gain <= 0 and safety_gain <= 0 and social_gain <= 0 and hp_gain <= 0:
        return None

    needs.energy = _clamp_need_value(float(needs.energy) + energy_gain)
    needs.safety = _clamp_need_value(float(needs.safety) + safety_gain)
    needs.social = _clamp_need_value(float(needs.social) + social_gain)
    if vitality and hp_gain > 0:
        vitality.hp = min(int(vitality.max_hp), int(vitality.hp) + hp_gain)
    if service == "rest" and effects is not None:
        effects.add(
            "well_rested",
            900,
            modifiers={
                "perception_buff": 0.5,
                "energy_tick_delta": 0.01,
            },
        )

    sim.emit(Event(
        "npc_lodging_used",
        npc_eid=actor_eid,
        property_id=target.get("property_id"),
        property_name=target.get("property_name"),
        service=service,
        credits_spent=int(credits_spent),
        energy_gain=int(energy_gain),
        safety_gain=int(safety_gain),
        social_gain=int(social_gain),
        hp_gain=int(hp_gain),
        x=int(pos.x),
        y=int(pos.y),
        z=int(pos.z),
    ))
    _remember_opportunity_lead(
        sim,
        actor_eid,
        "lodging",
        dict(target),
        source_kind="verified_arrival",
        stale_after_ticks=120,
        expires_ticks=540,
    )
    _note_opportunity_success(sim, actor_eid, "lodging", lead=target)
    return {
        "property_id": target.get("property_id"),
        "property_name": target.get("property_name"),
        "service": service,
        "credits_spent": int(credits_spent),
    }


def _receive_safe_spot_at_actor(sim, actor_eid, pos=None):
    if pos is None:
        pos = sim.ecs.get(Position).get(actor_eid)
    if not pos:
        return None

    current_lead = _best_opportunity_lead(sim, actor_eid, "safe_spot")
    target = _find_safe_spot_target_exact(sim, actor_eid, pos, radius=2)
    if not target:
        if current_lead is not None:
            _mark_opportunity_failure(
                sim,
                actor_eid,
                "safe_spot",
                lead=current_lead,
                cooldown_ticks=210,
                reason="safe_spot_invalid",
            )
        return None

    safe_kind = str(target.get("safe_kind", "lodging") or "lodging").strip().lower()
    result = None
    if safe_kind == "medical":
        result = _receive_medical_aid_at_actor(sim, actor_eid, pos)
    else:
        result = _receive_lodging_at_actor(sim, actor_eid, pos)

    needs = sim.ecs.get(NPCNeeds).get(actor_eid)
    fallback_hideout = False
    safety_gain = 0
    energy_gain = 0
    if result is None and needs is not None:
        safety_gain = min(12, max(3, int(round((100.0 - float(getattr(needs, "safety", 78.0) or 78.0)) * 0.2))))
        if float(getattr(needs, "energy", 100.0) or 100.0) < 72.0:
            energy_gain = min(6, max(1, int(round((78.0 - float(needs.energy)) * 0.1))))
        if safety_gain > 0 or energy_gain > 0:
            needs.safety = _clamp_need_value(float(needs.safety) + safety_gain)
            needs.energy = _clamp_need_value(float(needs.energy) + energy_gain)
            fallback_hideout = True

    if result is None and not fallback_hideout:
        _mark_opportunity_failure(
            sim,
            actor_eid,
            "safe_spot",
            lead=target,
            cooldown_ticks=210,
            reason="safe_spot_failed",
        )
        return None

    sim.emit(Event(
        "npc_safe_spot_used",
        npc_eid=int(actor_eid),
        property_id=target.get("property_id"),
        property_name=target.get("property_name"),
        safe_kind=safe_kind,
        service=target.get("service"),
        fallback_hideout=bool(fallback_hideout),
        safety_gain=int(safety_gain),
        energy_gain=int(energy_gain),
        x=int(pos.x),
        y=int(pos.y),
        z=int(pos.z),
    ))
    _remember_opportunity_lead(
        sim,
        actor_eid,
        "safe_spot",
        dict(target),
        source_kind="verified_arrival",
        stale_after_ticks=120,
        expires_ticks=420,
    )
    _note_opportunity_success(sim, actor_eid, "safe_spot", lead=target)
    return {
        "property_id": target.get("property_id"),
        "property_name": target.get("property_name"),
        "safe_kind": safe_kind,
        "service": target.get("service"),
        "fallback_hideout": bool(fallback_hideout),
    }


def _scavengeable_ground_item_value(ground):
    if not isinstance(ground, dict):
        return 0.0
    item_id = str(ground.get("item_id", "") or "").strip().lower()
    if not item_id:
        return 0.0
    if is_credstick_item(item_id):
        return float(
            credstick_total_credits(
                quantity=ground.get("quantity", 1),
                metadata=ground.get("metadata"),
            )
        )
    category = _item_category(ground, item_catalog=ITEM_CATALOG)
    if category == "credential":
        return 0.0
    tags = _item_tags(ground, item_catalog=ITEM_CATALOG)
    if category not in _SCAVENGEABLE_ITEM_CATEGORIES and not tags.intersection(_SCAVENGEABLE_ITEM_TAGS):
        return 0.0
    base = float(_SCAVENGE_CATEGORY_VALUES.get(category, 10.0))
    if "drug" in tags or "stimulant" in tags:
        base += 9.0
    if "medical" in tags:
        base += 5.0
    if "ammo" in tags:
        base += 7.0
    legal_status = _item_legal_status(ground, item_catalog=ITEM_CATALOG)
    if legal_status in {"illegal", "stolen"}:
        base += 7.0
    elif legal_status in {"restricted", "suspicious"}:
        base += 3.0
    quantity = max(1, int(ground.get("quantity", 1) or 1))
    return float(base * min(3.0, 0.9 + (0.38 * quantity)))


def _scavenge_item_matches_preferences(sim, actor_eid, ground):
    item_id = str((ground or {}).get("item_id", "") or "").strip().lower()
    if not item_id:
        return False
    if is_credstick_item(item_id):
        return False
    preferred = _behavior_preference(sim, actor_eid, "scavenge_tags", None)
    if not preferred:
        return True
    wanted = {
        _behavior_token(tag)
        for tag in (preferred if isinstance(preferred, (list, tuple, set, frozenset)) else (preferred,))
        if _behavior_token(tag)
    }
    if not wanted:
        return True
    category = _item_category(ground, item_catalog=ITEM_CATALOG)
    tags = _item_tags(ground, item_catalog=ITEM_CATALOG)
    return bool((category and category in wanted) or tags.intersection(wanted))


def _ground_item_interest_score(ground, *, distance):
    if is_credstick_item((ground or {}).get("item_id")):
        credits = credstick_total_credits(
            quantity=(ground or {}).get("quantity", 1),
            metadata=(ground or {}).get("metadata"),
        )
        return _ground_credit_interest_score(credits, distance)
    base = _scavengeable_ground_item_value(ground)
    if base <= 0.0:
        return 0.0
    distance = max(0, int(distance or 0))
    return float(base + max(0.0, (7 - distance) * 4.5))


def _find_ground_credit_target(sim, actor_eid, pos, *, radius=None):
    if not pos:
        return None
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if not _inventory_can_accept_credsticks(inventory, owner_eid=actor_eid):
        return None

    search_radius = radius
    if search_radius is None:
        search_radius = _behavior_preference(sim, actor_eid, "ground_credit_search_radius", 6)
    try:
        search_radius = max(1, int(search_radius))
    except (TypeError, ValueError):
        search_radius = 6

    best = None
    for ground in sim.ground_items_in_radius(pos.x, pos.y, pos.z, r=search_radius):
        if not is_credstick_item(ground.get("item_id")):
            continue
        if not _ground_item_pickup_is_safe(sim, actor_eid, ground):
            continue
        distance = _manhattan(pos.x, pos.y, ground.get("x"), ground.get("y"))
        credits = credstick_total_credits(
            quantity=ground.get("quantity", 1),
            metadata=ground.get("metadata"),
        )
        score = _ground_credit_interest_score(credits, distance)
        candidate = {
            "target": (int(ground.get("x", pos.x)), int(ground.get("y", pos.y)), int(ground.get("z", pos.z))),
            "ground_item_id": str(ground.get("ground_item_id", "")).strip() or None,
            "credits": int(credits),
            "distance": int(distance),
            "score": float(score),
        }
        if best is None or candidate["score"] > best["score"]:
            best = candidate
    return best


def _find_scavenge_ground_item_target(sim, actor_eid, pos, *, radius=None):
    if not pos:
        return None
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if not inventory:
        return None

    search_radius = radius
    if search_radius is None:
        search_radius = _behavior_preference(
            sim,
            actor_eid,
            "ground_item_search_radius",
            _behavior_preference(sim, actor_eid, "ground_credit_search_radius", 6),
        )
    try:
        search_radius = max(1, int(search_radius))
    except (TypeError, ValueError):
        search_radius = 6

    best = None
    for ground in sim.ground_items_in_radius(pos.x, pos.y, pos.z, r=search_radius):
        item_id = str(ground.get("item_id", "") or "").strip().lower()
        if not item_id or is_credstick_item(item_id):
            continue
        if not _ground_item_pickup_is_safe(sim, actor_eid, ground):
            continue
        if not _scavenge_item_matches_preferences(sim, actor_eid, ground):
            continue
        if not _inventory_can_accept_item(inventory, item_id, owner_eid=actor_eid):
            continue
        distance = _manhattan(pos.x, pos.y, ground.get("x"), ground.get("y"))
        value = _scavengeable_ground_item_value(ground)
        score = _ground_item_interest_score(ground, distance=distance)
        if score <= 0.0:
            continue
        candidate = {
            "target": (int(ground.get("x", pos.x)), int(ground.get("y", pos.y)), int(ground.get("z", pos.z))),
            "ground_item_id": str(ground.get("ground_item_id", "")).strip() or None,
            "item_id": item_id,
            "quantity": int(max(1, ground.get("quantity", 1) or 1)),
            "value": float(value),
            "distance": int(distance),
            "score": float(score),
        }
        if best is None or candidate["score"] > best["score"]:
            best = candidate
    return best


def _inventory_scavenge_sale_rows(sim, actor_eid):
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if not inventory:
        return []

    rows = []
    for entry in tuple(getattr(inventory, "items", ()) or ()):
        item_id = str(entry.get("item_id", "") or "").strip().lower()
        if not item_id or is_credstick_item(item_id):
            continue
        category = _item_category(entry, item_catalog=ITEM_CATALOG)
        if category == "credential":
            continue
        value = _scavengeable_ground_item_value(entry)
        if value <= 0.0:
            continue
        rows.append({
            "instance_id": str(entry.get("instance_id", "")).strip() or None,
            "item_id": item_id,
            "quantity": int(max(1, entry.get("quantity", 1) or 1)),
            "metadata": entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {},
            "value": float(value),
        })
    return rows


def _find_scavenged_sale_target(sim, actor_eid, pos, *, radius=None, preferred_property_id=None, preferred_score_bonus=0.0):
    lead = _best_opportunity_lead(sim, actor_eid, "scavenged_sale")
    if isinstance(lead, dict):
        if preferred_property_id and str(preferred_property_id).strip() and str(lead.get("property_id", "")).strip() == str(preferred_property_id).strip():
            lead["score"] = float(lead.get("score", 0.0) or 0.0) + float(max(0.0, preferred_score_bonus or 0.0))
        lead["sale_rows"] = _inventory_scavenge_sale_rows(sim, actor_eid)
        if not lead["sale_rows"]:
            return None
        return lead
    if not pos:
        return None

    sale_rows = _inventory_scavenge_sale_rows(sim, actor_eid)
    if not sale_rows:
        return None

    search_radius = radius
    if search_radius is None:
        search_radius = _behavior_preference(sim, actor_eid, "scavenge_sale_search_radius", 12)
    try:
        search_radius = max(2, int(search_radius))
    except (TypeError, ValueError):
        search_radius = 12

    inventory_value = sum(float(row.get("value", 0.0) or 0.0) for row in sale_rows)
    best = None
    for row in _nearby_opportunity_rows(sim, pos, radius=search_radius, lead_kind="scavenged_sale", current_tick=int(getattr(sim, "tick", 0) or 0)):
        target = row.get("target")
        if not isinstance(target, (tuple, list)) or len(target) < 3:
            continue
        distance = _manhattan(pos.x, pos.y, int(target[0]), int(target[1]))
        archetype = str(row.get("archetype", "") or "").strip().lower()
        payout_mult = float(_SCAVENGE_SALE_PAYOUT_MULTS.get(archetype, 0.46))
        score = max(0.0, (inventory_value * payout_mult) + 8.0 - (distance * 1.65))
        property_id = str(row.get("property_id", "")).strip() or None
        score += _business_target_reputation_bonus(
            sim,
            actor_eid,
            property_id,
            purpose="scavenge_sale",
        )
        if preferred_property_id and property_id and str(preferred_property_id).strip() == property_id:
            score += float(max(0.0, preferred_score_bonus or 0.0))
        candidate = {
            "property_id": property_id,
            "property_name": str(row.get("property_name", property_id or "site")).strip() or "site",
            "archetype": archetype,
            "target": (int(target[0]), int(target[1]), int(target[2])),
            "distance": int(distance),
            "score": float(score),
            "inventory_value": float(inventory_value),
            "sale_rows": sale_rows,
            "covert_referral": bool(
                preferred_property_id
                and property_id
                and str(preferred_property_id).strip() == property_id
            ),
            "confidence": 0.68,
            "verification_required": True,
            "service_id": "trade_sell",
            "opportunity_tag": "scavenged_sale",
        }
        if best is None or float(candidate["score"]) > float(best["score"]):
            best = candidate
    if best is not None:
        _remember_opportunity_lead(
            sim,
            actor_eid,
            "scavenged_sale",
            best,
            source_kind="surface_snapshot",
            stale_after_ticks=120,
            expires_ticks=420,
        )
    return best


def _find_scavenged_sale_target_exact(sim, actor_eid, pos, *, radius=None, preferred_property_id=None, preferred_score_bonus=0.0):
    if not pos:
        return None

    sale_rows = _inventory_scavenge_sale_rows(sim, actor_eid)
    if not sale_rows:
        return None

    search_radius = radius
    if search_radius is None:
        search_radius = _behavior_preference(sim, actor_eid, "scavenge_sale_search_radius", 12)
    try:
        search_radius = max(2, int(search_radius))
    except (TypeError, ValueError):
        search_radius = 12

    inventory_value = sum(float(row.get("value", 0.0) or 0.0) for row in sale_rows)
    best = None
    for prop in sim.properties_in_radius(pos.x, pos.y, pos.z, r=search_radius):
        archetype = _behavior_token(((prop.get("metadata") or {}) if isinstance(prop, dict) else {}).get("archetype"))
        if archetype not in _SCAVENGE_SALE_ARCHETYPES:
            continue
        focus = _property_focus_position(prop)
        if not focus:
            continue
        fx, fy, fz = focus
        if int(fz) != int(pos.z):
            continue
        access = _cached_behavior_property_access(
            sim,
            actor_eid,
            prop,
            x=int(fx),
            y=int(fy),
            z=int(fz),
        )
        covert_referral = _preferred_hidden_contact_match(
            prop,
            preferred_property_id,
            hidden_kind="backroom_market",
        )
        if not access.can_use_services and not access.permitted and not covert_referral:
            continue
        distance = _manhattan(pos.x, pos.y, fx, fy)
        payout_mult = float(_SCAVENGE_SALE_PAYOUT_MULTS.get(archetype, 0.46))
        score = max(0.0, (inventory_value * payout_mult) + 8.0 - (distance * 1.8))
        property_id = str(prop.get("id", "")).strip() or None
        score += _business_target_reputation_bonus(
            sim,
            actor_eid,
            property_id,
            purpose="scavenge_sale",
        )
        if preferred_property_id and property_id and str(preferred_property_id).strip() == property_id:
            score += float(max(0.0, preferred_score_bonus or 0.0))
        candidate = {
            "property_id": property_id,
            "property_name": str(prop.get("name", prop.get("id", "site"))).strip() or "site",
            "archetype": archetype,
            "target": (int(fx), int(fy), int(fz)),
            "distance": int(distance),
            "score": float(score),
            "inventory_value": float(inventory_value),
            "sale_rows": sale_rows,
            "covert_referral": bool(covert_referral),
        }
        if best is None or candidate["score"] > best["score"]:
            best = candidate
    return best


def _sell_scavenged_inventory_at_actor(sim, actor_eid, pos=None, *, preferred_property_id=None):
    if pos is None:
        pos = sim.ecs.get(Position).get(actor_eid)
    if not pos:
        return None

    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if not inventory:
        return None

    current_lead = _best_opportunity_lead(sim, actor_eid, "scavenged_sale")
    prop = None
    best_distance = None
    for candidate in sim.properties_in_radius(pos.x, pos.y, pos.z, r=2):
        if int(candidate.get("z", pos.z) or pos.z) != int(pos.z):
            continue
        archetype = _behavior_token(((candidate.get("metadata") or {}) if isinstance(candidate, dict) else {}).get("archetype"))
        if archetype not in _SCAVENGE_SALE_ARCHETYPES:
            continue
        focus = _property_focus_position(candidate)
        if not focus:
            continue
        distance = _manhattan(pos.x, pos.y, int(focus[0]), int(focus[1]))
        property_id = str(candidate.get("id", "")).strip() or None
        preferred_match = bool(
            preferred_property_id
            and property_id
            and str(preferred_property_id).strip() == property_id
        )
        if (
            best_distance is None
            or preferred_match
            or distance < best_distance
        ):
            prop = candidate
            best_distance = distance
    if not isinstance(prop, dict):
        if current_lead is not None:
            _mark_opportunity_failure(
                sim,
                actor_eid,
                "scavenged_sale",
                lead=current_lead,
                cooldown_ticks=180,
                reason="sale_site_missing",
            )
        return None

    archetype = _behavior_token(((prop.get("metadata") or {}) if isinstance(prop, dict) else {}).get("archetype"))
    covert_referral = _preferred_hidden_contact_match(
        prop,
        preferred_property_id,
        hidden_kind="backroom_market",
    )
    payout_mult = float(_SCAVENGE_SALE_PAYOUT_MULTS.get(archetype, 0.46))
    sale_rows = _inventory_scavenge_sale_rows(sim, actor_eid)
    if not sale_rows:
        return None

    sold_rows = []
    credits_total = 0
    for row in sale_rows:
        instance_id = row.get("instance_id")
        quantity = int(max(1, row.get("quantity", 1) or 1))
        removed = inventory.remove_item(instance_id=instance_id, quantity=quantity)
        if not removed:
            continue
        sale_value = max(1, int(round(float(row.get("value", 0.0) or 0.0) * payout_mult)))
        credits_total += sale_value
        sold_rows.append({
            "item_id": str(removed.get("item_id", "")).strip().lower(),
            "quantity": int(max(1, removed.get("quantity", 1) or 1)),
            "credits": int(sale_value),
        })

    if not sold_rows:
        if current_lead is not None:
            _mark_opportunity_failure(
                sim,
                actor_eid,
                "scavenged_sale",
                lead=current_lead,
                cooldown_ticks=120,
                reason="nothing_to_sell",
            )
        return None

    if credits_total > 0:
        item_def = ITEM_CATALOG.get(CREDSTICK_ITEM_ID, {})
        inventory.add_item(
            item_id=CREDSTICK_ITEM_ID,
            quantity=1,
            stack_max=max(1, int(item_def.get("stack_max", 1) or 1)),
            instance_factory=sim.new_item_instance_id,
            owner_eid=actor_eid,
            owner_tag="npc",
            metadata={"stored_credits": int(credits_total), "source": "npc_scavenge_sale"},
        )

    sim.emit(Event(
        "npc_scavenged_goods_sold",
        npc_eid=actor_eid,
        property_id=str(prop.get("id", "")).strip() or None,
        property_name=str(prop.get("name", prop.get("id", "site"))).strip() or "site",
        archetype=archetype,
        covert_referral=bool(covert_referral),
        item_count=len(sold_rows),
        credits_gained=int(credits_total),
        sold_rows=tuple(sold_rows),
        x=int(pos.x),
        y=int(pos.y),
        z=int(pos.z),
    ))
    _remember_opportunity_lead(
        sim,
        actor_eid,
        "scavenged_sale",
        {
            "property_id": str(prop.get("id", "")).strip() or None,
            "property_name": str(prop.get("name", prop.get("id", "site"))).strip() or "site",
            "target": tuple(_property_focus_position(prop) or (int(pos.x), int(pos.y), int(pos.z))),
            "archetype": archetype,
            "service_id": "trade_sell",
            "opportunity_tag": "scavenged_sale",
            "confidence": 0.8,
        },
        source_kind="verified_arrival",
        stale_after_ticks=120,
        expires_ticks=540,
    )
    _note_opportunity_success(
        sim,
        actor_eid,
        "scavenged_sale",
        lead=current_lead or {"property_id": str(prop.get("id", "")).strip() or None},
    )
    return {
        "property_id": str(prop.get("id", "")).strip() or None,
        "property_name": str(prop.get("name", prop.get("id", "site"))).strip() or "site",
        "credits_gained": int(credits_total),
        "item_count": len(sold_rows),
        "sold_rows": tuple(sold_rows),
        "covert_referral": bool(covert_referral),
    }


def _collect_ground_credits_at_actor(sim, actor_eid, pos=None):
    if pos is None:
        pos = sim.ecs.get(Position).get(actor_eid)
    if not pos:
        return None

    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if not _inventory_can_accept_credsticks(inventory, owner_eid=actor_eid):
        return None

    candidates = []
    for ground in sim.ground_items_at(pos.x, pos.y, pos.z):
        if not is_credstick_item(ground.get("item_id")):
            continue
        if not _ground_item_pickup_is_safe(sim, actor_eid, ground):
            continue
        candidates.append(ground)
    if not candidates:
        return None

    ground = max(
        candidates,
        key=lambda entry: credstick_total_credits(
            quantity=entry.get("quantity", 1),
            metadata=entry.get("metadata"),
        ),
    )
    metadata = ground.get("metadata") if isinstance(ground.get("metadata"), dict) else {}
    item_def = ITEM_CATALOG.get(CREDSTICK_ITEM_ID, {})
    added, instance_id = inventory.add_item(
        item_id=CREDSTICK_ITEM_ID,
        quantity=max(1, int(ground.get("quantity", 1) or 1)),
        stack_max=max(1, int(item_def.get("stack_max", 1) or 1)),
        instance_id=ground.get("instance_id"),
        instance_factory=sim.new_item_instance_id,
        owner_eid=actor_eid,
        owner_tag="npc",
        metadata=stamp_item_provenance(
            sim,
            {
                **ground,
                "metadata": metadata,
            },
            source_context=metadata.get("source_context", "ground_pickup"),
            latent_claim_violation=bool((metadata or {}).get("latent_claim_violation", False)),
            last_transfer_tick=int(getattr(sim, "tick", 0)),
            last_transfer_kind="ground_pickup",
            last_holder_eid=actor_eid,
        ),
    )
    if not added:
        return None

    ground_item_id = str(ground.get("ground_item_id", "")).strip() or None
    credits = int(
        credstick_total_credits(
            quantity=ground.get("quantity", 1),
            metadata=metadata,
        )
    )
    if ground_item_id:
        sim.remove_ground_item(ground_item_id)

    sim.emit(Event(
        "item_picked_up",
        eid=actor_eid,
        item_id=CREDSTICK_ITEM_ID,
        item_name=item_def.get("name", "Credstick"),
        quantity=int(max(1, ground.get("quantity", 1) or 1)),
        instance_id=instance_id,
        ground_item_id=ground_item_id,
        x=int(ground.get("x", pos.x)),
        y=int(ground.get("y", pos.y)),
        z=int(ground.get("z", pos.z)),
        cash_pickup=False,
        credits_gained=credits,
    ))
    sim.emit(Event(
        "npc_ground_credits_collected",
        npc_eid=actor_eid,
        ground_item_id=ground_item_id,
        item_id=CREDSTICK_ITEM_ID,
        quantity=int(max(1, ground.get("quantity", 1) or 1)),
        credits_gained=credits,
        x=int(ground.get("x", pos.x)),
        y=int(ground.get("y", pos.y)),
        z=int(ground.get("z", pos.z)),
    ))
    return {
        "ground_item_id": ground_item_id,
        "instance_id": instance_id,
        "credits_gained": credits,
    }


def _collect_ground_items_at_actor(sim, actor_eid, pos=None):
    if pos is None:
        pos = sim.ecs.get(Position).get(actor_eid)
    if not pos:
        return []

    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if not inventory:
        return []

    candidates = []
    for ground in sim.ground_items_at(pos.x, pos.y, pos.z):
        item_id = str(ground.get("item_id", "") or "").strip().lower()
        if not item_id:
            continue
        if not _ground_item_pickup_is_safe(sim, actor_eid, ground):
            continue
        if is_credstick_item(item_id):
            if not _inventory_can_accept_credsticks(inventory, owner_eid=actor_eid):
                continue
        else:
            if not _scavenge_item_matches_preferences(sim, actor_eid, ground):
                continue
            if not _inventory_can_accept_item(inventory, item_id, owner_eid=actor_eid):
                continue
        score = _ground_item_interest_score(ground, distance=0)
        if score <= 0.0:
            continue
        candidates.append((float(score), ground))

    if not candidates:
        return []

    results = []
    for _score, ground in sorted(candidates, key=lambda row: row[0], reverse=True):
        item_id = str(ground.get("item_id", "") or "").strip().lower()
        item_def = ITEM_CATALOG.get(item_id, {})
        quantity = int(max(1, ground.get("quantity", 1) or 1))
        metadata = ground.get("metadata") if isinstance(ground.get("metadata"), dict) else {}
        stack_max = max(1, int(item_def.get("stack_max", 1) or 1))
        if is_credstick_item(item_id):
            if not _inventory_can_accept_credsticks(inventory, owner_eid=actor_eid):
                continue
        elif not _inventory_can_accept_item(inventory, item_id, owner_eid=actor_eid):
            continue
        added, instance_id = inventory.add_item(
            item_id=item_id,
            quantity=quantity,
            stack_max=stack_max,
            instance_id=ground.get("instance_id"),
            instance_factory=sim.new_item_instance_id,
            owner_eid=actor_eid,
            owner_tag="npc",
            metadata=stamp_item_provenance(
                sim,
                {
                    **ground,
                    "metadata": metadata,
                },
                source_context=metadata.get("source_context", "ground_pickup"),
                latent_claim_violation=bool((metadata or {}).get("latent_claim_violation", False)),
                last_transfer_tick=int(getattr(sim, "tick", 0)),
                last_transfer_kind="ground_pickup",
                last_holder_eid=actor_eid,
            ),
        )
        if not added:
            continue

        ground_item_id = str(ground.get("ground_item_id", "")).strip() or None
        credits = int(
            credstick_total_credits(quantity=quantity, metadata=metadata)
            if is_credstick_item(item_id)
            else 0
        )
        if ground_item_id:
            sim.remove_ground_item(ground_item_id)

        sim.emit(Event(
            "item_picked_up",
            eid=actor_eid,
            item_id=item_id,
            item_name=item_def.get("name", item_id.replace("_", " ").title()),
            quantity=quantity,
            instance_id=instance_id,
            ground_item_id=ground_item_id,
            x=int(ground.get("x", pos.x)),
            y=int(ground.get("y", pos.y)),
            z=int(ground.get("z", pos.z)),
            cash_pickup=False,
            credits_gained=credits,
        ))
        sim.emit(Event(
            "npc_ground_item_scavenged",
            npc_eid=actor_eid,
            ground_item_id=ground_item_id,
            item_id=item_id,
            quantity=quantity,
            credits_gained=credits,
            x=int(ground.get("x", pos.x)),
            y=int(ground.get("y", pos.y)),
            z=int(ground.get("z", pos.z)),
        ))
        if is_credstick_item(item_id):
            sim.emit(Event(
                "npc_ground_credits_collected",
                npc_eid=actor_eid,
                ground_item_id=ground_item_id,
                item_id=item_id,
                quantity=quantity,
                credits_gained=credits,
                x=int(ground.get("x", pos.x)),
                y=int(ground.get("y", pos.y)),
                z=int(ground.get("z", pos.z)),
            ))
        results.append({
            "ground_item_id": ground_item_id,
            "instance_id": instance_id,
            "item_id": item_id,
            "quantity": quantity,
            "credits_gained": credits,
        })

    return results
