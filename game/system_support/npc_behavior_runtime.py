"""Shared NPC behavior tags and helper routines."""

from __future__ import annotations

from engine.events import Event
from game.components import BehaviorProfile, Inventory, Position
from game.items import CREDSTICK_ITEM_ID, ITEM_CATALOG, credstick_total_credits, is_credstick_item
from game.property_access import evaluate_property_access as _evaluate_property_access
from game.property_runtime import property_covering as _property_covering
from game.system_support.interaction_ordering import _manhattan


BEHAVIOR_COLLECT_GROUND_CREDITS = "collect_ground_credits"
BEHAVIOR_SCAVENGE_LOOSE_ITEMS = "scavenge_loose_items"
BEHAVIOR_SELL_SCAVENGED_ITEMS = "sell_scavenged_items"
BEHAVIOR_BUY_DESIRED_DRUG = "buy_desired_drug"
BEHAVIOR_IDENTIFY_STREET_DRUGS = "identify_street_drugs"
BEHAVIOR_AVOID_THREAT = "avoid_threat"
BEHAVIOR_ENFORCE_JUSTICE = "enforce_justice"

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


def behavior_profile_for_spawn(*, role="", career="", workplace_archetype="", home_archetype=""):
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
        },
        "scout": {
            BEHAVIOR_AVOID_THREAT: 0.26,
            BEHAVIOR_ENFORCE_JUSTICE: 0.82,
        },
        "worker": {
            BEHAVIOR_AVOID_THREAT: 0.42,
            BEHAVIOR_ENFORCE_JUSTICE: 0.48,
        },
        "civilian": {
            BEHAVIOR_AVOID_THREAT: 0.55,
            BEHAVIOR_ENFORCE_JUSTICE: 0.32,
        },
        "resident": {
            BEHAVIOR_AVOID_THREAT: 0.48,
            BEHAVIOR_ENFORCE_JUSTICE: 0.28,
        },
        "thief": {
            BEHAVIOR_AVOID_THREAT: 0.74,
            BEHAVIOR_ENFORCE_JUSTICE: 0.08,
        },
        "drunk": {
            BEHAVIOR_AVOID_THREAT: 0.68,
            BEHAVIOR_ENFORCE_JUSTICE: 0.12,
        },
    }
    for name, value in role_behavior_defaults.get(
        role_key,
        {
            BEHAVIOR_AVOID_THREAT: 0.5,
            BEHAVIOR_ENFORCE_JUSTICE: 0.3,
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
        preferences["ground_credit_search_radius"] = max(
            int(preferences.get("ground_credit_search_radius", 0) or 0),
            7,
        )
    if archetypes & _NIGHTLIFE_ARCHETYPES:
        _seed_behavior(behaviors, BEHAVIOR_COLLECT_GROUND_CREDITS, 0.46)
        preferences["ground_credit_search_radius"] = max(
            int(preferences.get("ground_credit_search_radius", 0) or 0),
            6,
        )

    if career_key in _DRUG_IDENTIFICATION_CAREERS or any(
        token in career_key
        for token in ("dealer", "pharmac", "chemist", "broker", "pawn")
    ):
        _seed_behavior(behaviors, BEHAVIOR_IDENTIFY_STREET_DRUGS, 0.85)

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


def _actor_behavior_value(sim, eid, behavior, default=0.0):
    token = _behavior_token(behavior)
    if not token:
        return _clamp_behavior_value(default)
    profile = _actor_behavior_profile(sim, eid)
    if not profile:
        return _clamp_behavior_value(default)
    return _clamp_behavior_value(profile.get(token, default), default=default)


def _effective_behavior_value(sim, eid, behavior, *, traits=None, needs=None, justice=None):
    token = _behavior_token(behavior)
    base = _actor_behavior_value(sim, eid, token, default=0.0)

    if token == BEHAVIOR_AVOID_THREAT:
        bravery = _clamp_behavior_value(getattr(traits, "bravery", 0.5), default=0.5)
        safety_gap = _clamp_behavior_value(
            (100.0 - float(getattr(needs, "safety", 75.0) or 75.0)) / 100.0,
            default=0.25,
        )
        situational = _clamp_behavior_value(((1.0 - bravery) * 0.7) + (safety_gap * 0.3))
        return max(base, situational)

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
        return max(base, situational)

    return base


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


def _ground_credit_interest_score(credits, distance):
    credits = max(0, int(credits or 0))
    distance = max(0, int(distance or 0))
    return min(28.0, credits * 0.85) + max(0.0, (6 - distance) * 6.0)


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
