"""Intent-aware physical item offers between the player and an NPC.

The exchange is deliberately neutral until the player says what the item is
for.  Favors, opportunity handoffs, practical support, and gifts all use the
same ownership transfer; their meaning is attached as context rather than
inferred from the item alone.

Clothing decisions in this first slice are evaluated only for the recipient
of a completed handoff.  There is intentionally no clock-driven population
scan; later autonomous wardrobe changes should enter through per-actor events
or sparse due work, with weather supplied as optional context once it exists.
"""

from __future__ import annotations

import copy
import random
from collections.abc import Mapping

from engine.events import Event
from game.appearance_loadout import (
    APPEARANCE_SLOTS,
    BASEWEAR_SLOTS,
    appearance_loadout_for,
    appearance_metadata_for_entry,
    equip_appearance_item,
    is_appearance_item,
    unequip_appearance_slot,
)
from game.components import ArmorLoadout, CreatureIdentity, Inventory, NPCMemory, Position, WeaponLoadout
from game.human_description import build_human_description_profile
from game.item_semantics import item_display_name_for_actor
from game.items import ITEM_CATALOG
from game.opportunities import advance_opportunity_lifecycle
from game.social_fact_graph import record_occurrence
from game.social_requests import ITEM_FAVOR_PROFILES
from game.system_support.item_runtime import _item_armor_profile, _item_weapon_id
from game.weapon_equipment_runtime import equip_existing_weapon_item


ITEM_OFFER_SELECT_PREFIX = "item_offer_select:"
ITEM_OFFER_INTENT_PREFIX = "item_offer_intent:"
ITEM_OFFER_CANCEL_ID = "item_offer_cancel"
ITEM_OFFER_PENDING_KEY = "pending_item_offer"
ITEM_EXCHANGE_SCHEMA_VERSION = 1


def _token(value):
    return str(value or "").strip().lower().replace(" ", "_")


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


def is_item_offer_topic(topic_id):
    topic = str(topic_id or "").strip().lower()
    return bool(
        topic == ITEM_OFFER_CANCEL_ID
        or topic.startswith(ITEM_OFFER_SELECT_PREFIX)
        or topic.startswith(ITEM_OFFER_INTENT_PREFIX)
    )


def _dialogue_state(sim):
    state = getattr(sim, "dialog_ui", None)
    if not isinstance(state, dict):
        state = {}
        sim.dialog_ui = state
    return state


def clear_pending_item_offer(sim):
    _dialogue_state(sim)[ITEM_OFFER_PENDING_KEY] = None


def _pending_item_offer(sim, player_eid, npc_eid):
    pending = _dialogue_state(sim).get(ITEM_OFFER_PENDING_KEY)
    if not isinstance(pending, dict):
        return None
    if _int(pending.get("player_eid"), 0) != int(player_eid):
        clear_pending_item_offer(sim)
        return None
    if _int(pending.get("npc_eid"), 0) != int(npc_eid):
        clear_pending_item_offer(sim)
        return None
    if _int(getattr(sim, "tick", 0), 0) - _int(pending.get("selected_tick"), 0) > 60:
        clear_pending_item_offer(sim)
        return None
    inventory = sim.ecs.get(Inventory).get(player_eid)
    entry = inventory.find(instance_id=pending.get("instance_id")) if inventory is not None else None
    if not isinstance(entry, dict) or _int(entry.get("quantity"), 0) <= 0:
        clear_pending_item_offer(sim)
        return None
    return pending


def _actors_adjacent(sim, first_eid, second_eid):
    positions = sim.ecs.get(Position)
    first = positions.get(first_eid)
    second = positions.get(second_eid)
    return bool(
        first is not None
        and second is not None
        and int(first.z) == int(second.z)
        and abs(int(first.x) - int(second.x)) + abs(int(first.y) - int(second.y)) <= 1
    )


def _item_name(sim, actor_eid, entry):
    try:
        return item_display_name_for_actor(
            sim,
            actor_eid,
            entry,
            item_catalog=ITEM_CATALOG,
        )
    except Exception:
        item_id = str((entry or {}).get("item_id", "") or "").strip()
        return str(ITEM_CATALOG.get(item_id, {}).get("name", "") or item_id.replace("_", " ") or "item")


def _entry_is_equipped_or_worn(sim, actor_eid, entry):
    instance_id = str((entry or {}).get("instance_id", "") or "").strip()
    if not instance_id:
        return True
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    if bool(metadata.get("appearance_worn")):
        return True
    loadout = appearance_loadout_for(sim, actor_eid, create=False)
    if loadout is not None and instance_id in {
        str(value or "").strip() for value in loadout.slots.values() if value
    }:
        return True
    weapon_loadout = sim.ecs.get(WeaponLoadout).get(actor_eid)
    if weapon_loadout is not None:
        weapon_id = _item_weapon_id(ITEM_CATALOG.get(str(entry.get("item_id", "") or ""), {}))
        weapon_instance = weapon_loadout.weapon_instance(weapon_id) if weapon_id else {}
        if (
            weapon_id
            and weapon_loadout.current_weapon() == weapon_id
            and str((weapon_instance or {}).get("inventory_instance_id", "") or "").strip() == instance_id
        ):
            return True
    armor_loadout = sim.ecs.get(ArmorLoadout).get(actor_eid)
    if armor_loadout is not None and armor_loadout.is_equipped(instance_id):
        return True
    return False


def _offerable_entries(sim, player_eid):
    inventory = sim.ecs.get(Inventory).get(player_eid)
    if inventory is None:
        return ()
    rows = []
    for entry in tuple(getattr(inventory, "items", ()) or ()):
        if not isinstance(entry, dict) or _int(entry.get("quantity"), 0) <= 0:
            continue
        if _entry_is_equipped_or_worn(sim, player_eid, entry):
            continue
        rows.append(entry)
    rows.sort(key=lambda entry: (_item_name(sim, player_eid, entry).lower(), str(entry.get("instance_id", ""))))
    return tuple(rows)


def _matching_favor(sim, player_eid, npc_eid, entry):
    system = getattr(sim, "social_request_system", None)
    if system is None or not hasattr(system, "player_item_favor_for_entry"):
        return None
    return system.player_item_favor_for_entry(player_eid, npc_eid, entry)


def _active_opportunities(sim):
    traits = getattr(sim, "world_traits", None)
    state = traits.get("opportunities") if isinstance(traits, dict) else None
    active = state.get("active") if isinstance(state, dict) else None
    return tuple(active or ()) if isinstance(active, list) else ()


def _matching_opportunities(sim, npc_eid, entry):
    item_id = _token((entry or {}).get("item_id"))
    rows = []
    for opportunity in _active_opportunities(sim):
        if not isinstance(opportunity, dict) or _token(opportunity.get("status")) not in {"", "active"}:
            continue
        requirements = opportunity.get("requirements") if isinstance(opportunity.get("requirements"), dict) else {}
        if not bool(requirements.get("player_accepted")):
            continue
        if _int(requirements.get("interact_npc_eid"), 0) != int(npc_eid):
            continue
        if _token(requirements.get("require_item_id")) != item_id:
            continue
        rows.append(opportunity)
    return tuple(rows)


def _is_practical_item(entry):
    item_def = ITEM_CATALOG.get(_token((entry or {}).get("item_id")), {})
    return bool(
        _item_weapon_id(item_def)
        or _item_armor_profile(item_def)
        or any(tag in {"tool", "medical", "food", "drink"} for tag in set(item_def.get("tags", ()) or ()))
    )


def item_offer_dialogue_rows(sim, player_eid, npc_eid, context=None):
    """Return dynamic selection or intent rows for one conversation."""

    pending = _pending_item_offer(sim, player_eid, npc_eid)
    inventory = sim.ecs.get(Inventory).get(player_eid)
    if pending is not None and inventory is not None:
        entry = inventory.find(instance_id=pending.get("instance_id"))
        if isinstance(entry, dict):
            item_name = _item_name(sim, player_eid, entry)
            rows = []
            favor = _matching_favor(sim, player_eid, npc_eid, entry)
            if isinstance(favor, dict):
                rows.append({
                    "id": f"{ITEM_OFFER_INTENT_PREFIX}favor:{favor.get('request_id')}",
                    "label": f"Give {item_name} for what they asked for.",
                    "prompt_text": f"Give {item_name} for what they asked for.",
                    "player_line": str(favor.get("player_line", "I brought what you asked for.") or "I brought what you asked for."),
                    "item_offer_action": "intent",
                    "item_offer_intent": "favor",
                    "request_id": str(favor.get("request_id", "") or ""),
                    "item_offer_pending": True,
                })
            for opportunity in _matching_opportunities(sim, npc_eid, entry):
                opportunity_id = _int(opportunity.get("id"), 0)
                title = str(opportunity.get("title", "the handoff") or "the handoff").strip()
                rows.append({
                    "id": f"{ITEM_OFFER_INTENT_PREFIX}opportunity:{opportunity_id}",
                    "label": f"Hand {item_name} over for {title}.",
                    "prompt_text": f"Hand {item_name} over for {title}.",
                    "player_line": f"This is for {title}.",
                    "item_offer_action": "intent",
                    "item_offer_intent": "opportunity",
                    "opportunity_id": opportunity_id,
                    "item_offer_pending": True,
                })
            if _is_practical_item(entry):
                support_label = "Offer it for backup." if _item_weapon_id(ITEM_CATALOG.get(_token(entry.get("item_id")), {})) else "Offer it for them to use."
                rows.append({
                    "id": f"{ITEM_OFFER_INTENT_PREFIX}support",
                    "label": support_label,
                    "prompt_text": support_label,
                    "player_line": "I thought this might be useful to you.",
                    "item_offer_action": "intent",
                    "item_offer_intent": "support",
                    "item_offer_pending": True,
                })
            rows.extend((
                {
                    "id": f"{ITEM_OFFER_INTENT_PREFIX}gift",
                    "label": "Say it is a gift.",
                    "prompt_text": "Say it is a gift.",
                    "player_line": "It's for you, if you want it.",
                    "item_offer_action": "intent",
                    "item_offer_intent": "gift",
                    "item_offer_pending": True,
                },
                {
                    "id": ITEM_OFFER_CANCEL_ID,
                    "label": "Keep it after all.",
                    "prompt_text": "Keep it after all.",
                    "player_line": "Never mind. I'll keep it.",
                    "item_offer_action": "cancel",
                    "item_offer_pending": True,
                },
            ))
            return rows

    rows = []
    for entry in _offerable_entries(sim, player_eid):
        instance_id = str(entry.get("instance_id", "") or "").strip()
        item_name = _item_name(sim, player_eid, entry)
        quantity = _int(entry.get("quantity"), 1)
        quantity_text = f" ({quantity})" if quantity > 1 else ""
        rows.append({
            "id": f"{ITEM_OFFER_SELECT_PREFIX}{instance_id}",
            "label": f"Offer {item_name}{quantity_text}...",
            "prompt_text": f"Offer {item_name}{quantity_text}...",
            "player_line": f"I have {item_name} I could offer you.",
            "item_offer_action": "select",
            "item_offer_group": "item_offers",
            "item_instance_id": instance_id,
            "item_id": str(entry.get("item_id", "") or ""),
        })
    return rows


def _exchange_state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get("npc_item_exchange")
    if not isinstance(state, dict):
        state = {}
        traits["npc_item_exchange"] = state
    state["schema_version"] = ITEM_EXCHANGE_SCHEMA_VERSION
    if not isinstance(state.get("clothing_preferences"), dict):
        state["clothing_preferences"] = {}
    return state


def _worn_appearance_profiles(sim, npc_eid):
    inventory = sim.ecs.get(Inventory).get(npc_eid)
    loadout = appearance_loadout_for(sim, npc_eid, create=False)
    if inventory is None or loadout is None:
        return ()
    rows = []
    seen = set()
    for instance_id in loadout.slots.values():
        instance_id = str(instance_id or "").strip()
        if not instance_id or instance_id in seen:
            continue
        seen.add(instance_id)
        entry = inventory.find(instance_id=instance_id)
        profile = appearance_metadata_for_entry(entry) if isinstance(entry, dict) else {}
        if profile:
            rows.append(profile)
    return tuple(rows)


def clothing_preference_profile(sim, npc_eid):
    """Return the persistent latent taste projected from the seeded motif."""

    state = _exchange_state(sim)
    key = str(int(npc_eid))
    stored = state["clothing_preferences"].get(key)
    if isinstance(stored, dict):
        return copy.deepcopy(stored)

    identity = sim.ecs.get(CreatureIdentity).get(npc_eid)
    human = build_human_description_profile(
        getattr(sim, "seed", 0),
        eid=npc_eid,
        identity=identity,
        personal_name=getattr(identity, "personal_name", None),
    ) or {}
    worn = _worn_appearance_profiles(sim, npc_eid)
    dimensions = {}
    for field in ("color_word", "style", "material", "detail", "pattern", "appearance_type"):
        values = tuple(dict.fromkeys(_token(row.get(field)) for row in worn if _token(row.get(field))))
        if values:
            dimensions[field] = values
    rng = random.Random(
        f"npc-clothing-preference:{getattr(sim, 'seed', 0)}:{npc_eid}:{human.get('seed_token', '')}"
    )
    candidates = list(dimensions)
    rng.shuffle(candidates)
    selected_fields = tuple(candidates[: min(3, len(candidates))])
    likes = {}
    for field in selected_fields:
        values = dimensions[field]
        likes[field] = (rng.choice(values),)
    profile = {
        "source": "seeded_appearance_motif",
        "style_axis": _token(human.get("style_axis")) or "mixed",
        "likes": likes,
        "openness": round(rng.uniform(0.34, 0.78), 3),
    }
    state["clothing_preferences"][key] = copy.deepcopy(profile)
    return profile


def clothing_affinity_for_entry(sim, npc_eid, entry):
    offered = appearance_metadata_for_entry(entry)
    if not offered:
        return {"score": 0.0, "presentation_compatible": True, "matched_dimensions": ()}
    preference = clothing_preference_profile(sim, npc_eid)
    likes = preference.get("likes") if isinstance(preference.get("likes"), dict) else {}
    matched = []
    score = 0.22
    dimension_weight = 0.54 / max(1, len(likes))
    for field, liked_values in likes.items():
        value = _token(offered.get(field))
        if value and value in set(liked_values or ()):
            matched.append(field)
            score += dimension_weight

    style_axis = _token(preference.get("style_axis")) or "mixed"
    presentation = _token(offered.get("presentation"))
    presentation_compatible = bool(
        not presentation
        or presentation in {"neutral", "mixed", "androgynous", style_axis}
        or style_axis == "mixed"
    )
    score += 0.16 if presentation_compatible else -0.22
    return {
        "score": round(max(0.0, min(1.0, score)), 3),
        "presentation_compatible": presentation_compatible,
        "matched_dimensions": tuple(matched),
    }


def _bond_read(context):
    context = context if isinstance(context, Mapping) else {}
    bond = context.get("bond") if isinstance(context.get("bond"), Mapping) else {}
    kind = _token(bond.get("kind") or context.get("dialogue_relationship_band"))
    trust = max(0.0, min(1.0, _float(bond.get("trust"), 0.0)))
    closeness = max(0.0, min(1.0, _float(bond.get("closeness"), 0.0)))
    return kind, trust, closeness


def _support_relationship_ready(context):
    kind, trust, closeness = _bond_read(context)
    if kind in {"friend", "family", "partner", "coworker", "owner", "workplace", "job_issuer"}:
        return True
    return trust >= 0.52 and closeness >= 0.38


def _item_meets_current_need(sim, npc_eid, item_id):
    system = getattr(sim, "social_request_system", None)
    if system is None or not hasattr(system, "_request_need_level"):
        return False
    for kind, profile in ITEM_FAVOR_PROFILES.items():
        if item_id not in tuple(profile.get("item_ids", ()) or ()):
            continue
        if system._request_need_level(npc_eid, kind) < _float(profile.get("threshold"), 0.0):
            return True
    return False


def _acceptance_for(sim, npc_eid, entry, intent, context):
    context = context if isinstance(context, Mapping) else {}
    if bool(context.get("guarded")) or _token(context.get("pressure_tier")) == "high":
        return {"accepted": False, "line": "Not while things are like this. Keep it."}
    if intent in {"favor", "opportunity"}:
        return {"accepted": True, "reason": intent}

    item_id = _token(entry.get("item_id"))
    item_def = ITEM_CATALOG.get(item_id, {})
    kind, trust, closeness = _bond_read(context)
    relationship_score = (trust * 0.55) + (closeness * 0.45)
    if intent == "support":
        if not _support_relationship_ready(context):
            return {"accepted": False, "line": "I understand what you're offering, but we're not there."}
        return {"accepted": True, "reason": "practical_support"}

    if _item_weapon_id(item_def) and relationship_score < 0.72:
        return {"accepted": False, "line": "I don't want to take a weapon from you as a gift."}
    if is_appearance_item(entry):
        affinity = clothing_affinity_for_entry(sim, npc_eid, entry)
        threshold = 0.48 - (relationship_score * 0.20)
        if affinity["score"] < threshold and kind not in {"partner", "family"}:
            return {"accepted": False, "line": "It's thoughtful, but that really isn't for me."}
        return {"accepted": True, "reason": "clothing_gift", "clothing_affinity": affinity}
    if _item_meets_current_need(sim, npc_eid, item_id):
        return {"accepted": True, "reason": "current_need"}
    if relationship_score < 0.18 and not bool(context.get("met_directly")):
        return {"accepted": False, "line": "I don't know you well enough to take that."}
    return {"accepted": True, "reason": "personal_gift"}


def _transfer_one(sim, player_eid, npc_eid, entry, *, intent, context_id=""):
    source = sim.ecs.get(Inventory).get(player_eid)
    if source is None:
        return {"ok": False, "reason": "missing_source_inventory"}
    live = source.find(instance_id=entry.get("instance_id"))
    if not isinstance(live, dict):
        return {"ok": False, "reason": "item_moved"}
    original_quantity = _int(live.get("quantity"), 0)
    removed = source.remove_item(instance_id=live.get("instance_id"), quantity=1)
    if not isinstance(removed, dict):
        return {"ok": False, "reason": "item_moved"}

    inventories = sim.ecs.get(Inventory)
    target = inventories.get(npc_eid)
    if target is None:
        target = Inventory(capacity=10)
        sim.ecs.add(npc_eid, target)
    item_id = _token(removed.get("item_id"))
    item_def = ITEM_CATALOG.get(item_id, {})
    original_metadata = copy.deepcopy(removed.get("metadata") or {})
    metadata = copy.deepcopy(original_metadata)
    exchange = {
        "giver_eid": int(player_eid),
        "recipient_eid": int(npc_eid),
        "tick": _int(getattr(sim, "tick", 0), 0),
        "intent": _token(intent),
        "context_id": str(context_id or "").strip(),
    }
    metadata["item_exchange"] = exchange
    metadata["last_transfer_tick"] = exchange["tick"]
    metadata["last_transfer_kind"] = f"item_offer_{_token(intent)}"
    metadata["last_holder_eid"] = int(player_eid)
    if intent == "gift":
        metadata["gifted_by_eid"] = int(player_eid)
        metadata["gifted_to_eid"] = int(npc_eid)
        metadata["gift_tick"] = exchange["tick"]

    preserve_instance = str(removed.get("instance_id", "") or "").strip() if original_quantity <= 1 else None
    added, received_instance_id = target.add_item(
        item_id,
        quantity=1,
        stack_max=max(1, _int(item_def.get("stack_max"), 1)),
        instance_id=preserve_instance,
        instance_factory=sim.new_item_instance_id,
        owner_eid=npc_eid,
        owner_tag="npc",
        metadata=metadata,
    )
    if added and received_instance_id:
        return {
            "ok": True,
            "item_id": item_id,
            "source_instance_id": str(removed.get("instance_id", "") or ""),
            "received_instance_id": str(received_instance_id),
            "metadata": metadata,
        }

    source.add_item(
        item_id,
        quantity=1,
        stack_max=max(1, _int(item_def.get("stack_max"), 1)),
        instance_id=str(removed.get("instance_id", "") or "").strip() if original_quantity <= 1 else None,
        instance_factory=sim.new_item_instance_id,
        owner_eid=removed.get("owner_eid"),
        owner_tag=removed.get("owner_tag"),
        metadata=original_metadata,
    )
    return {"ok": False, "reason": "recipient_inventory_full"}


def _appearance_conflict_slots(target_slot):
    if target_slot == "full_body":
        return ("full_body", "top", "bottom")
    if target_slot in {"top", "bottom"}:
        return (target_slot, "full_body")
    return (target_slot,)


def _try_wear_received_clothing(sim, npc_eid, instance_id, affinity, relationship_score):
    inventory = sim.ecs.get(Inventory).get(npc_eid)
    entry = inventory.find(instance_id=instance_id) if inventory is not None else None
    profile = appearance_metadata_for_entry(entry) if isinstance(entry, dict) else {}
    if not profile:
        return {"ever_wear": False, "wore_now": False, "reason": "not_clothing"}
    if any(slot in BASEWEAR_SLOTS for slot in tuple(profile.get("slots", ()) or ())):
        return {"ever_wear": bool(affinity.get("score", 0.0) >= 0.54), "wore_now": False, "reason": "private_basewear"}

    wear_score = (
        _float(affinity.get("score"), 0.0)
        + (max(0.0, min(1.0, relationship_score)) * 0.12)
    )
    ever_wear = bool(affinity.get("presentation_compatible", True) and wear_score >= 0.54)
    if not ever_wear or wear_score < 0.70:
        return {"ever_wear": ever_wear, "wore_now": False, "wear_score": round(wear_score, 3)}

    loadout = appearance_loadout_for(sim, npc_eid, create=True)
    slots = tuple(slot for slot in tuple(profile.get("slots", ()) or ()) if slot in APPEARANCE_SLOTS)
    target_slot = slots[0] if slots else ""
    if loadout is None or not target_slot:
        return {"ever_wear": True, "wore_now": False, "reason": "no_slot", "wear_score": round(wear_score, 3)}

    removed = []
    for slot in _appearance_conflict_slots(target_slot):
        old_instance_id = str(loadout.slots.get(slot) or "").strip()
        if not old_instance_id or old_instance_id == str(instance_id):
            continue
        result = unequip_appearance_slot(sim, npc_eid, slot)
        if not getattr(result, "ok", False):
            for restore_slot, restore_instance_id in reversed(removed):
                equip_appearance_item(sim, npc_eid, restore_instance_id, preferred_slot=restore_slot)
            return {"ever_wear": True, "wore_now": False, "reason": getattr(result, "reason", "cannot_change"), "wear_score": round(wear_score, 3)}
        removed.append((slot, old_instance_id))

    equipped = equip_appearance_item(sim, npc_eid, instance_id, preferred_slot=target_slot)
    if not getattr(equipped, "ok", False):
        for restore_slot, restore_instance_id in reversed(removed):
            equip_appearance_item(sim, npc_eid, restore_instance_id, preferred_slot=restore_slot)
        return {"ever_wear": True, "wore_now": False, "reason": getattr(equipped, "reason", "cannot_equip"), "wear_score": round(wear_score, 3)}
    return {
        "ever_wear": True,
        "wore_now": True,
        "slot": target_slot,
        "wear_score": round(wear_score, 3),
    }


def _remember_required_item_transfer(sim, *, item_id, npc_eid, opportunity_id=0):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    records = traits.get("recent_required_item_transfers")
    if not isinstance(records, list):
        records = []
        traits["recent_required_item_transfers"] = records
    recent_npcs = traits.get("recent_npc_interactions")
    if not isinstance(recent_npcs, dict):
        recent_npcs = {}
        traits["recent_npc_interactions"] = recent_npcs
    recent_npcs[str(int(npc_eid))] = _int(getattr(sim, "tick", 0), 0)
    pos = sim.ecs.get(Position).get(npc_eid)
    chunk = sim.chunk_coords(int(pos.x), int(pos.y)) if pos is not None else None
    records.append({
        "tick": _int(getattr(sim, "tick", 0), 0),
        "item_id": _token(item_id),
        "quantity": 1,
        "npc_eid": int(npc_eid),
        "property_id": "",
        "building_id": "",
        "chunk": chunk,
        "source": "item_offer",
        "opportunity_id": int(opportunity_id),
    })
    traits["recent_required_item_transfers"] = records[-20:]


def _record_exchange_memory(sim, player_eid, npc_eid, transfer, *, intent, context_id="", wore_now=False):
    now = _int(getattr(sim, "tick", 0), 0)
    item_id = _token(transfer.get("item_id"))
    occurrence = record_occurrence(
        sim,
        "item_exchanged",
        actor_eids=(player_eid, npc_eid),
        payload={
            "giver_eid": int(player_eid),
            "recipient_eid": int(npc_eid),
            "item_id": item_id,
            "item_instance_id": str(transfer.get("received_instance_id", "") or ""),
            "intent": _token(intent),
            "context_id": str(context_id or "").strip(),
            "wore_now": bool(wore_now),
        },
        flags=("spoken", "in_person", "physical_transfer"),
        dedupe_key=f"item-exchange:{npc_eid}:{transfer.get('received_instance_id')}:{now}",
    )
    memory = sim.ecs.get(NPCMemory).get(npc_eid)
    if memory is not None:
        memory.remember(
            tick=now,
            kind="item_received",
            strength=0.82 if intent == "gift" else 0.68,
            other_eid=int(player_eid),
            item_id=item_id,
            item_instance_id=str(transfer.get("received_instance_id", "") or ""),
            intent=_token(intent),
            context_id=str(context_id or "").strip(),
            occurrence_id=occurrence.get("id"),
            wore_now=bool(wore_now),
        )
    return occurrence


def resolve_item_offer_dialogue_choice(sim, player_eid, npc_eid, topic_id, topic_row, context=None):
    topic = str(topic_id or "").strip().lower()
    choice = dict(topic_row or {})
    if topic == ITEM_OFFER_CANCEL_ID:
        clear_pending_item_offer(sim)
        return {"npc_lines": ["All right."]}

    if topic.startswith(ITEM_OFFER_SELECT_PREFIX):
        instance_id = str(choice.get("item_instance_id", "") or topic[len(ITEM_OFFER_SELECT_PREFIX):]).strip()
        inventory = sim.ecs.get(Inventory).get(player_eid)
        entry = inventory.find(instance_id=instance_id) if inventory is not None else None
        if not isinstance(entry, dict) or _entry_is_equipped_or_worn(sim, player_eid, entry):
            clear_pending_item_offer(sim)
            return {"npc_lines": ["You don't seem able to hand that over right now."]}
        _dialogue_state(sim)[ITEM_OFFER_PENDING_KEY] = {
            "player_eid": int(player_eid),
            "npc_eid": int(npc_eid),
            "instance_id": instance_id,
            "item_id": str(entry.get("item_id", "") or ""),
            "selected_tick": _int(getattr(sim, "tick", 0), 0),
        }
        return {"npc_lines": ["What did you have in mind?"]}

    pending = _pending_item_offer(sim, player_eid, npc_eid)
    if pending is None:
        return {"npc_lines": ["That offer isn't in your hands anymore."]}
    if not _actors_adjacent(sim, player_eid, npc_eid):
        clear_pending_item_offer(sim)
        return {"npc_lines": ["You need to be close enough to actually hand it over."]}
    inventory = sim.ecs.get(Inventory).get(player_eid)
    entry = inventory.find(instance_id=pending.get("instance_id")) if inventory is not None else None
    if not isinstance(entry, dict):
        clear_pending_item_offer(sim)
        return {"npc_lines": ["You don't have it to offer anymore."]}

    intent = _token(choice.get("item_offer_intent"))
    context_id = ""
    if intent == "favor":
        context_id = str(choice.get("request_id", "") or "").strip()
        favor = _matching_favor(sim, player_eid, npc_eid, entry)
        if not isinstance(favor, dict) or str(favor.get("request_id", "") or "") != context_id:
            clear_pending_item_offer(sim)
            return {"npc_lines": ["That isn't what I was waiting on anymore."]}
    elif intent == "opportunity":
        context_id = str(_int(choice.get("opportunity_id"), 0))
        matches = {
            str(_int(row.get("id"), 0)): row for row in _matching_opportunities(sim, npc_eid, entry)
        }
        if context_id not in matches:
            clear_pending_item_offer(sim)
            return {"npc_lines": ["That handoff isn't open anymore."]}
    elif intent not in {"gift", "support"}:
        return {"npc_lines": ["Say what you mean the offer to be for."]}

    acceptance = _acceptance_for(sim, npc_eid, entry, intent, context)
    if not acceptance.get("accepted"):
        clear_pending_item_offer(sim)
        return {"npc_lines": [str(acceptance.get("line", "No. Keep it.") or "No. Keep it.")]}

    transfer = _transfer_one(
        sim,
        player_eid,
        npc_eid,
        entry,
        intent=intent,
        context_id=context_id,
    )
    clear_pending_item_offer(sim)
    if not transfer.get("ok"):
        if transfer.get("reason") == "recipient_inventory_full":
            return {"npc_lines": ["I don't have anywhere safe to put that. Keep it for now."]}
        return {"npc_lines": ["The handoff doesn't quite happen."]}

    kind, trust, closeness = _bond_read(context)
    relationship_score = (trust * 0.55) + (closeness * 0.45)
    equipment = {}
    clothing = {}
    if intent == "support" and _item_weapon_id(ITEM_CATALOG.get(transfer["item_id"], {})):
        equipment = equip_existing_weapon_item(
            sim,
            npc_eid,
            transfer["received_instance_id"],
            reason="player_offered_for_backup",
        )
    if is_appearance_item({"item_id": transfer["item_id"], "metadata": transfer.get("metadata", {})}):
        affinity = acceptance.get("clothing_affinity")
        if not isinstance(affinity, dict):
            received_inventory = sim.ecs.get(Inventory).get(npc_eid)
            received_entry = received_inventory.find(instance_id=transfer["received_instance_id"])
            affinity = clothing_affinity_for_entry(sim, npc_eid, received_entry)
        clothing = _try_wear_received_clothing(
            sim,
            npc_eid,
            transfer["received_instance_id"],
            affinity,
            relationship_score,
        )
        received_inventory = sim.ecs.get(Inventory).get(npc_eid)
        received_entry = received_inventory.find(instance_id=transfer["received_instance_id"])
        if isinstance(received_entry, dict):
            metadata = dict(received_entry.get("metadata") or {})
            metadata["npc_clothing_disposition"] = {
                "ever_wear": bool(clothing.get("ever_wear")),
                "wear_score": _float(clothing.get("wear_score"), _float(affinity.get("score"), 0.0)),
                "presentation_compatible": bool(affinity.get("presentation_compatible", True)),
                "decided_tick": _int(getattr(sim, "tick", 0), 0),
            }
            received_inventory.update_item_metadata(
                transfer["received_instance_id"],
                metadata=metadata,
                replace=True,
            )

    completed_opportunity = None
    if intent == "favor":
        system = getattr(sim, "social_request_system", None)
        if system is not None and hasattr(system, "fulfill_player_item_favor_from_exchange"):
            system.fulfill_player_item_favor_from_exchange(
                player_eid,
                npc_eid,
                context_id,
                item_id=transfer["item_id"],
                received_instance_id=transfer["received_instance_id"],
            )
    elif intent == "opportunity":
        opportunity_id = _int(context_id, 0)
        _remember_required_item_transfer(
            sim,
            item_id=transfer["item_id"],
            npc_eid=npc_eid,
            opportunity_id=opportunity_id,
        )
        lifecycle = advance_opportunity_lifecycle(sim, player_eid)
        completed_opportunity = next(
            (
                row for row in tuple(lifecycle.get("completed", ()) or ())
                if _int((row or {}).get("id"), 0) == opportunity_id
            ),
            None,
        )

    occurrence = _record_exchange_memory(
        sim,
        player_eid,
        npc_eid,
        transfer,
        intent=intent,
        context_id=context_id,
        wore_now=bool(clothing.get("wore_now")),
    )
    sim.emit(Event(
        "npc_item_received",
        eid=player_eid,
        npc_eid=npc_eid,
        item_id=transfer["item_id"],
        instance_id=transfer["received_instance_id"],
        intent=intent,
        context_id=context_id,
        occurrence_id=occurrence.get("id"),
        equipped_for_support=bool(equipment.get("ok")),
        clothing_ever_wear=bool(clothing.get("ever_wear")),
        clothing_wore_now=bool(clothing.get("wore_now")),
        opportunity_completed=bool(completed_opportunity),
    ))

    if intent == "favor":
        line = "Thank you. I needed that."
    elif intent == "opportunity":
        line = "That's it. The handoff is settled." if completed_opportunity else "I have it. I'll take it from here."
    elif equipment.get("ok"):
        line = "All right. I'll keep it ready."
    elif clothing.get("wore_now"):
        line = "This actually feels like me. Thank you."
    elif intent == "gift":
        line = "Thank you. I'll keep it."
    else:
        line = "All right. I can use this."
    return {
        "npc_lines": [line],
        "item_exchange": {
            **transfer,
            "intent": intent,
            "context_id": context_id,
            "equipped_for_support": bool(equipment.get("ok")),
            "clothing_ever_wear": bool(clothing.get("ever_wear")),
            "clothing_wore_now": bool(clothing.get("wore_now")),
            "opportunity_completed": bool(completed_opportunity),
        },
    }


__all__ = [
    "ITEM_OFFER_CANCEL_ID",
    "ITEM_OFFER_INTENT_PREFIX",
    "ITEM_OFFER_PENDING_KEY",
    "ITEM_OFFER_SELECT_PREFIX",
    "clear_pending_item_offer",
    "clothing_affinity_for_entry",
    "clothing_preference_profile",
    "is_item_offer_topic",
    "item_offer_dialogue_rows",
    "resolve_item_offer_dialogue_choice",
]
