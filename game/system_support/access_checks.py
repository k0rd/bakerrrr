"""Shared access-skill resolution and access-tool wear helpers."""

from __future__ import annotations

import random

from engine.events import Event

from game.components import Inventory
from game.items import ITEM_CATALOG, apply_item_durability_loss, item_display_name
from game.skills import access_skill_practice_awards as _access_skill_practice_awards


def _int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _access_attempt_roll_impl():
    try:
        from game import systems as _systems
    except ImportError:
        return _access_attempt_roll
    return getattr(_systems, "_access_attempt_roll", _access_attempt_roll)


def _access_attempt_roll(sim, *, eid, prop, context, channel):
    """Deterministic per-attempt roll keyed by run seed + attempt counter."""
    key = (
        str(channel or "access").strip().lower() or "access",
        str(context or "").strip().lower(),
        int(_int_or_default(eid, 0)),
        str(prop.get("id", "") if isinstance(prop, dict) else ""),
    )
    counters = getattr(sim, "_access_roll_counters", None)
    if not isinstance(counters, dict):
        counters = {}
        setattr(sim, "_access_roll_counters", counters)
    attempt_index = int(counters.get(key, 0)) + 1
    counters[key] = attempt_index
    seed_token = ":".join(
        (
            str(getattr(sim, "seed", 0)),
            str(getattr(sim, "tick", 0)),
            str(key[0]),
            str(key[1]),
            str(key[2]),
            str(key[3]),
            str(attempt_index),
        )
    )
    return random.Random(seed_token).random()


def _access_fumble_chance(score, required):
    margin = float(score) - float(required)
    chance = 0.012
    if margin < 0.0:
        chance += min(0.2, abs(margin) * 0.08)
    return max(0.002, min(0.22, chance))


def _access_success_chance(score, required):
    margin = float(score) - float(required)
    chance = 0.5 + (margin * 0.14)
    if margin > 0.0:
        chance += min(0.08, margin * 0.02)
    elif margin < 0.0:
        chance -= min(0.12, abs(margin) * 0.03)
    return max(0.04, min(0.97, chance))


def _resolve_access_skill_check(
    sim,
    *,
    eid,
    prop,
    context,
    channel,
    score,
    required,
    tool_terms=None,
    allow_fumble=True,
):
    tool_terms = tool_terms or {}
    context_key = str(context or "").strip().lower()
    channel_key = str(channel or "access").strip().lower() or "access"
    roll = _access_attempt_roll_impl()(
        sim,
        eid=eid,
        prop=prop,
        context=context_key,
        channel=channel_key,
    )
    success_chance = _access_success_chance(score, required)
    fumbled = bool(allow_fumble and tool_terms.get("enabled")) and roll < _access_fumble_chance(score, required)
    success = bool(roll <= success_chance and not fumbled)
    property_id = str(prop.get("id", "") if isinstance(prop, dict) else "").strip()
    practice_awards = _access_skill_practice_awards(context_key, success=success, fumbled=fumbled)
    for skill_id, amount in practice_awards.items():
        if float(amount) <= 0.0:
            continue
        sim.emit(Event(
            "skill_practice",
            eid=eid,
            skill_id=str(skill_id or "").strip().lower(),
            amount=float(amount),
            source="access_check",
            context=context_key,
            channel=channel_key,
            property_id=property_id,
            cooldown_key=f"{property_id}:{channel_key}:{context_key}",
            cooldown=0,
            success=bool(success),
            fumbled=bool(fumbled),
        ))
    return {
        "success": success,
        "fumbled": bool(fumbled),
        "roll": float(roll),
        "success_chance": float(success_chance),
        "score": float(score),
        "required": float(required),
        "margin": float(score) - float(required),
    }


def _maybe_damage_access_tool(sim, eid, tool_terms, *, prop, score, required, context, channel, fumbled=False):
    enabled_ids = tuple(str(item_id).strip().lower() for item_id in tool_terms.get("enabled_item_ids", ()))
    selected_instance_id = str(tool_terms.get("selected_instance_id", "")).strip()
    if not enabled_ids:
        return None

    inventories = sim.ecs.get(Inventory)
    inventory = inventories.get(eid) if inventories else None
    if not inventory or not inventory.items:
        return None

    candidates = [
        entry
        for entry in inventory.items
        if int(entry.get("quantity", 0)) > 0
        and (not selected_instance_id or str(entry.get("instance_id", "")).strip() == selected_instance_id)
        and str(entry.get("item_id", "")).strip().lower() in enabled_ids
    ]
    if not candidates and selected_instance_id:
        candidates = [
            entry
            for entry in inventory.items
            if int(entry.get("quantity", 0)) > 0
            and str(entry.get("item_id", "")).strip().lower() in enabled_ids
        ]
    if not candidates:
        return None

    fail_gap = max(0.0, float(required) - float(score))
    try:
        tool_wear_mult = float(tool_terms.get("tool_wear_mult", 1.0) or 1.0)
    except (TypeError, ValueError):
        tool_wear_mult = 1.0
    tool_wear_mult = max(0.25, min(4.0, tool_wear_mult))
    strain_chance = 0.09 + min(0.45, fail_gap * 0.11)
    if fumbled:
        strain_chance += 0.16
    strain_chance *= tool_wear_mult
    strain_chance = max(0.01, min(0.85, strain_chance))

    if _access_attempt_roll_impl()(sim, eid=eid, prop=prop, context=context, channel=f"{channel}:tool_break") >= strain_chance:
        return None

    pick_roll = _access_attempt_roll_impl()(sim, eid=eid, prop=prop, context=context, channel=f"{channel}:tool_pick")
    pick_index = int(pick_roll * len(candidates))
    pick_index = max(0, min(len(candidates) - 1, pick_index))
    picked = candidates[pick_index]
    item_id = str(picked.get("item_id", "")).strip() or "item"
    instance_id = str(picked.get("instance_id", "")).strip() or None
    wear_amount = 1
    if fumbled:
        wear_amount += 1
    if fail_gap >= 2.5:
        wear_amount += 1
    wear_amount = max(1, int(round(float(wear_amount) * tool_wear_mult)))

    wear = apply_item_durability_loss(
        item_id,
        metadata=picked.get("metadata"),
        amount=wear_amount,
        item_catalog=ITEM_CATALOG,
    )
    if int(wear.get("lost", 0)) <= 0:
        return None

    item_name = item_display_name(item_id, metadata=picked.get("metadata"), item_catalog=ITEM_CATALOG)
    if wear.get("broken"):
        removed = inventory.remove_item(instance_id=instance_id, quantity=1)
        if not removed:
            return None
        item_name = item_display_name(
            str(removed.get("item_id", "")).strip() or item_id,
            metadata=removed.get("metadata"),
            item_catalog=ITEM_CATALOG,
        )
        if _int_or_default(eid, -1) == _int_or_default(getattr(sim, "player_eid", None), -2):
            sim.log.add(f"Your {item_name} breaks during the attempt.")

        sim.emit(Event(
            "access_tool_broken",
            eid=eid,
            property_id=prop.get("id") if isinstance(prop, dict) else None,
            item_id=removed.get("item_id"),
            item_name=item_name,
            instance_id=removed.get("instance_id"),
            context=str(context or "").strip().lower(),
            channel=str(channel or "access").strip().lower() or "access",
            fumbled=bool(fumbled),
            durability_before=int(wear.get("before", 0)),
            durability_after=int(wear.get("after", 0)),
            durability_lost=int(wear.get("lost", 0)),
            durability_max=int(wear.get("max_durability", 0)),
        ))
        return {
            "item_id": removed.get("item_id"),
            "instance_id": removed.get("instance_id"),
            "broken": True,
        }

    updated_metadata = inventory.update_item_metadata(instance_id, wear.get("metadata"))
    if updated_metadata is None:
        return None

    if _int_or_default(eid, -1) == _int_or_default(getattr(sim, "player_eid", None), -2):
        strain_text = "takes heavy strain" if int(wear.get("lost", 0)) > 1 else "takes strain"
        sim.log.add(
            f"Your {item_name} {strain_text} ({int(wear.get('after', 0))}/{int(wear.get('max_durability', 0))})."
        )

    sim.emit(Event(
        "access_tool_damaged",
        eid=eid,
        property_id=prop.get("id") if isinstance(prop, dict) else None,
        item_id=item_id,
        item_name=item_name,
        instance_id=instance_id,
        context=str(context or "").strip().lower(),
        channel=str(channel or "access").strip().lower() or "access",
        fumbled=bool(fumbled),
        durability_before=int(wear.get("before", 0)),
        durability_after=int(wear.get("after", 0)),
        durability_lost=int(wear.get("lost", 0)),
        durability_max=int(wear.get("max_durability", 0)),
    ))
    return {
        "item_id": item_id,
        "instance_id": instance_id,
        "broken": False,
        "durability_after": int(wear.get("after", 0)),
        "durability_max": int(wear.get("max_durability", 0)),
    }
