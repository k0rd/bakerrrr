"""Shared NPC behavior tags and helper routines."""

from __future__ import annotations

import random

from engine.events import Event
from game.components import BehaviorProfile, Inventory, Position
from game.item_semantics import item_category as _item_category, item_legal_status as _item_legal_status, item_tags as _item_tags
from game.items import CREDSTICK_ITEM_ID, ITEM_CATALOG, credstick_total_credits, is_credstick_item
from game.property_access import evaluate_property_access as _evaluate_property_access
from game.property_runtime import property_covering as _property_covering, property_focus_position as _property_focus_position
from game.system_support.interaction_ordering import _manhattan


BEHAVIOR_COLLECT_GROUND_CREDITS = "collect_ground_credits"
BEHAVIOR_SCAVENGE_LOOSE_ITEMS = "scavenge_loose_items"
BEHAVIOR_SELL_SCAVENGED_ITEMS = "sell_scavenged_items"
BEHAVIOR_APPRAISE_STREET_GOODS = "appraise_street_goods"
BEHAVIOR_BUY_DESIRED_DRUG = "buy_desired_drug"
BEHAVIOR_BUY_PLAYER_GOODS = "buy_player_goods"
BEHAVIOR_IDENTIFY_STREET_DRUGS = "identify_street_drugs"
BEHAVIOR_AVOID_THREAT = "avoid_threat"
BEHAVIOR_ENFORCE_JUSTICE = "enforce_justice"
BEHAVIOR_PROTECT_ALLIES = "protect_allies"
BEHAVIOR_SEEK_SOCIAL_CONTACT = "seek_social_contact"
BEHAVIOR_FOLLOW_DUTY = "follow_duty"

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
_SCAVENGE_SALE_ARCHETYPES = _SALVAGE_ARCHETYPES | _THRIFT_ARCHETYPES
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
}
RARE_EXTRA_BEHAVIOR_CHANCE = 0.02
_RARE_EXTRA_BEHAVIOR_WEIGHTS = (
    (BEHAVIOR_BUY_DESIRED_DRUG, 8, 0.22, 0.38),
    (BEHAVIOR_IDENTIFY_STREET_DRUGS, 5, 0.16, 0.28),
    (BEHAVIOR_APPRAISE_STREET_GOODS, 6, 0.18, 0.3),
    (BEHAVIOR_BUY_PLAYER_GOODS, 5, 0.18, 0.3),
    (BEHAVIOR_COLLECT_GROUND_CREDITS, 6, 0.2, 0.34),
    (BEHAVIOR_SCAVENGE_LOOSE_ITEMS, 5, 0.18, 0.32),
    (BEHAVIOR_SELL_SCAVENGED_ITEMS, 4, 0.16, 0.26),
    (BEHAVIOR_AVOID_THREAT, 5, 0.18, 0.32),
    (BEHAVIOR_ENFORCE_JUSTICE, 5, 0.18, 0.32),
    (BEHAVIOR_PROTECT_ALLIES, 5, 0.18, 0.32),
    (BEHAVIOR_SEEK_SOCIAL_CONTACT, 5, 0.18, 0.32),
    (BEHAVIOR_FOLLOW_DUTY, 5, 0.18, 0.32),
)


def _behavior_token(value):
    return str(value or "").strip().lower()


def _clamp_behavior_value(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return float(max(0.0, min(1.0, number)))


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
    return token


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
            BEHAVIOR_ENFORCE_JUSTICE: 0.95,
            BEHAVIOR_PROTECT_ALLIES: 0.84,
            BEHAVIOR_SEEK_SOCIAL_CONTACT: 0.18,
            BEHAVIOR_FOLLOW_DUTY: 0.94,
        },
        "scout": {
            BEHAVIOR_AVOID_THREAT: 0.26,
            BEHAVIOR_ENFORCE_JUSTICE: 0.82,
            BEHAVIOR_PROTECT_ALLIES: 0.72,
            BEHAVIOR_SEEK_SOCIAL_CONTACT: 0.22,
            BEHAVIOR_FOLLOW_DUTY: 0.84,
        },
        "worker": {
            BEHAVIOR_AVOID_THREAT: 0.42,
            BEHAVIOR_ENFORCE_JUSTICE: 0.48,
            BEHAVIOR_PROTECT_ALLIES: 0.42,
            BEHAVIOR_SEEK_SOCIAL_CONTACT: 0.44,
            BEHAVIOR_FOLLOW_DUTY: 0.76,
        },
        "civilian": {
            BEHAVIOR_AVOID_THREAT: 0.55,
            BEHAVIOR_ENFORCE_JUSTICE: 0.32,
            BEHAVIOR_PROTECT_ALLIES: 0.34,
            BEHAVIOR_SEEK_SOCIAL_CONTACT: 0.56,
            BEHAVIOR_FOLLOW_DUTY: 0.24,
        },
        "resident": {
            BEHAVIOR_AVOID_THREAT: 0.48,
            BEHAVIOR_ENFORCE_JUSTICE: 0.28,
            BEHAVIOR_PROTECT_ALLIES: 0.48,
            BEHAVIOR_SEEK_SOCIAL_CONTACT: 0.6,
            BEHAVIOR_FOLLOW_DUTY: 0.18,
        },
        "thief": {
            BEHAVIOR_AVOID_THREAT: 0.74,
            BEHAVIOR_ENFORCE_JUSTICE: 0.08,
            BEHAVIOR_PROTECT_ALLIES: 0.22,
            BEHAVIOR_SEEK_SOCIAL_CONTACT: 0.28,
            BEHAVIOR_FOLLOW_DUTY: 0.12,
        },
        "drunk": {
            BEHAVIOR_AVOID_THREAT: 0.68,
            BEHAVIOR_ENFORCE_JUSTICE: 0.12,
            BEHAVIOR_PROTECT_ALLIES: 0.18,
            BEHAVIOR_SEEK_SOCIAL_CONTACT: 0.74,
            BEHAVIOR_FOLLOW_DUTY: 0.06,
        },
    }
    for name, value in role_behavior_defaults.get(
        role_key,
        {
            BEHAVIOR_AVOID_THREAT: 0.5,
            BEHAVIOR_ENFORCE_JUSTICE: 0.3,
            BEHAVIOR_PROTECT_ALLIES: 0.35,
            BEHAVIOR_SEEK_SOCIAL_CONTACT: 0.45,
            BEHAVIOR_FOLLOW_DUTY: 0.28,
        },
    ).items():
        _seed_behavior(behaviors, name, value)

    if role_key == "thief":
        _seed_behavior(behaviors, BEHAVIOR_COLLECT_GROUND_CREDITS, 0.95)
        _seed_behavior(behaviors, BEHAVIOR_SCAVENGE_LOOSE_ITEMS, 0.88)
        _seed_behavior(behaviors, BEHAVIOR_SELL_SCAVENGED_ITEMS, 0.82)
        preferences["ground_credit_search_radius"] = 8
    elif role_key == "drunk":
        _seed_behavior(behaviors, BEHAVIOR_COLLECT_GROUND_CREDITS, 0.56)
        preferences["ground_credit_search_radius"] = 5

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
        preferences["ground_credit_search_radius"] = max(
            int(preferences.get("ground_credit_search_radius", 0) or 0),
            6,
        )

    if career_key in _DRUG_IDENTIFICATION_CAREERS or any(
        token in career_key
        for token in ("dealer", "pharmac", "chemist", "broker", "pawn")
    ):
        _seed_behavior(behaviors, BEHAVIOR_IDENTIFY_STREET_DRUGS, 0.85)
        _seed_behavior(behaviors, BEHAVIOR_APPRAISE_STREET_GOODS, 0.76)

    if any(token in career_key for token in _STREET_BUY_CAREER_TOKENS):
        _seed_behavior(behaviors, BEHAVIOR_BUY_PLAYER_GOODS, 0.78)
        _seed_behavior(behaviors, BEHAVIOR_BUY_DESIRED_DRUG, 0.82)

    if archetypes & _STREET_BUY_ARCHETYPES:
        _seed_behavior(behaviors, BEHAVIOR_BUY_PLAYER_GOODS, 0.68)
        _seed_behavior(behaviors, BEHAVIOR_APPRAISE_STREET_GOODS, 0.46)

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


def _effective_behavior_value(sim, eid, behavior, *, traits=None, needs=None, justice=None):
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


def _ground_item_pickup_is_safe(sim, actor_eid, ground):
    if not isinstance(ground, dict):
        return False
    owner_eid = ground.get("owner_eid")
    owner_tag = _behavior_token(ground.get("owner_tag")) or None

    if owner_eid == actor_eid:
        return True

    item_x = ground.get("x")
    item_y = ground.get("y")
    item_z = ground.get("z", 0)
    prop = _property_covering(sim, item_x, item_y, item_z)
    if prop:
        access = _evaluate_property_access(
            sim,
            actor_eid,
            prop,
            x=item_x,
            y=item_y,
            z=item_z,
        )
        if not access.permitted:
            prop_owner_eid = prop.get("owner_eid")
            prop_owner_tag = _behavior_token(prop.get("owner_tag"))
            if prop_owner_eid not in {None, actor_eid}:
                return False
            if prop_owner_eid is None and prop_owner_tag not in _PUBLIC_PROPERTY_OWNER_TAGS:
                return False

    return owner_eid is None and owner_tag in _PUBLIC_GROUND_OWNER_TAGS


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


def _ground_credit_interest_score(credits, distance):
    credits = max(0, int(credits or 0))
    distance = max(0, int(distance or 0))
    return min(28.0, credits * 0.85) + max(0.0, (6 - distance) * 6.0)


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


def _find_scavenged_sale_target(sim, actor_eid, pos, *, radius=None):
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
        access = _evaluate_property_access(
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
        payout_mult = float(_SCAVENGE_SALE_PAYOUT_MULTS.get(archetype, 0.46))
        score = max(0.0, (inventory_value * payout_mult) + 8.0 - (distance * 1.8))
        candidate = {
            "property_id": str(prop.get("id", "")).strip() or None,
            "property_name": str(prop.get("name", prop.get("id", "site"))).strip() or "site",
            "archetype": archetype,
            "target": (int(fx), int(fy), int(fz)),
            "distance": int(distance),
            "score": float(score),
            "inventory_value": float(inventory_value),
            "sale_rows": sale_rows,
        }
        if best is None or candidate["score"] > best["score"]:
            best = candidate
    return best


def _sell_scavenged_inventory_at_actor(sim, actor_eid, pos=None):
    if pos is None:
        pos = sim.ecs.get(Position).get(actor_eid)
    if not pos:
        return None

    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if not inventory:
        return None

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
        if best_distance is None or distance < best_distance:
            prop = candidate
            best_distance = distance
    if not isinstance(prop, dict):
        return None

    archetype = _behavior_token(((prop.get("metadata") or {}) if isinstance(prop, dict) else {}).get("archetype"))
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
        item_count=len(sold_rows),
        credits_gained=int(credits_total),
        sold_rows=tuple(sold_rows),
        x=int(pos.x),
        y=int(pos.y),
        z=int(pos.z),
    ))
    return {
        "property_id": str(prop.get("id", "")).strip() or None,
        "property_name": str(prop.get("name", prop.get("id", "site"))).strip() or "site",
        "credits_gained": int(credits_total),
        "item_count": len(sold_rows),
        "sold_rows": tuple(sold_rows),
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
        metadata=metadata,
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
            metadata=metadata,
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
