"""Shared NPC income and carried-cash helpers."""

from __future__ import annotations

from engine.events import Event
from game.components import AI, FinancialProfile, Inventory, Occupation
from game.economy import chunk_economy_profile
from game.items import CREDSTICK_ITEM_ID, ITEM_CATALOG, credstick_total_credits, is_credstick_item


_MANAGER_TOKENS = ("manager", "owner", "broker", "analyst", "director", "officer", "sergeant")


def _text(value):
    return str(value or "").strip()


def _int_or(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def ensure_financial_income_fields(profile):
    if profile is None:
        return None
    if hasattr(profile, "ensure_income_fields"):
        return profile.ensure_income_fields()
    if not hasattr(profile, "last_income_hour"):
        profile.last_income_hour = None
    if not hasattr(profile, "next_bank_check_tick"):
        profile.next_bank_check_tick = 0
    return profile


def inventory_liquid_credits(inventory):
    if not inventory:
        return 0
    total = 0
    for entry in tuple(getattr(inventory, "items", ()) or ()):
        if not is_credstick_item(entry.get("item_id")):
            continue
        total += int(credstick_total_credits(
            quantity=entry.get("quantity", 1),
            metadata=entry.get("metadata"),
        ))
    return int(max(0, total))


def spend_npc_wallet_credits(inventory, amount):
    """Spend carried credstick credits from an NPC-style inventory."""
    if not inventory:
        return 0
    remaining = max(0, _int_or(amount, default=0))
    if remaining <= 0:
        return 0
    spent = 0
    for entry in tuple(getattr(inventory, "items", ()) or ()):
        if remaining <= 0:
            break
        if not is_credstick_item(entry.get("item_id")):
            continue
        stack_total = int(credstick_total_credits(
            quantity=entry.get("quantity", 1),
            metadata=entry.get("metadata"),
        ))
        if stack_total <= 0:
            continue
        take = min(remaining, stack_total)
        new_total = max(0, stack_total - take)
        if new_total <= 0:
            inventory.remove_item(
                instance_id=entry.get("instance_id"),
                quantity=max(1, _int_or(entry.get("quantity"), default=1)),
            )
        else:
            metadata = dict(entry.get("metadata") or {})
            metadata["stored_credits"] = int(new_total)
            entry["metadata"] = metadata
        spent += take
        remaining -= take
    return int(spent)


def _property_metadata(prop):
    metadata = prop.get("metadata") if isinstance(prop, dict) else None
    return metadata if isinstance(metadata, dict) else {}


def _property_archetype(prop):
    return _text(_property_metadata(prop).get("archetype")).lower()


def _economy_profile_for_property(sim, prop):
    if sim is None or not isinstance(prop, dict):
        return chunk_economy_profile(sim)
    try:
        x = int(prop.get("x", 0) or 0)
        y = int(prop.get("y", 0) or 0)
        cx, cy = sim.chunk_coords(x, y)
    except Exception:
        return chunk_economy_profile(sim)
    chunk = None
    loaded = getattr(getattr(sim, "world", None), "loaded_chunks", {}).get((cx, cy))
    if isinstance(loaded, dict):
        chunk = loaded.get("chunk")
    if not isinstance(chunk, dict) and getattr(sim, "world", None) is not None:
        try:
            chunk = sim.world.get_chunk(cx, cy)
        except Exception:
            chunk = None
    return chunk_economy_profile(sim, chunk if isinstance(chunk, dict) else None)


def _actor_role_and_career(sim, actor_eid, *, role="", career=""):
    role = _text(role).lower()
    career = _text(career).lower()
    if sim is None:
        return role or "civilian", career
    if not role:
        ai = sim.ecs.get(AI).get(actor_eid)
        role = _text(getattr(ai, "role", "")).lower()
    if not career:
        occupation = sim.ecs.get(Occupation).get(actor_eid)
        career = _text(getattr(occupation, "career", "")).lower()
    return role or "civilian", career


def npc_hourly_wage(sim, actor_eid=None, *, role="", career="", workplace_prop=None, staff_role=""):
    """Return a small employer-sensitive hourly NPC wage in credits."""
    from game.population import _npc_wallet_range

    metadata = _property_metadata(workplace_prop)
    explicit_wage = metadata.get("hourly_wage")
    if explicit_wage not in {None, ""}:
        try:
            return int(max(1, min(20, round(float(explicit_wage)))))
        except (TypeError, ValueError):
            pass

    role, career = _actor_role_and_career(sim, actor_eid, role=role, career=career)
    staff_role = _text(staff_role).lower()
    economy_profile = _economy_profile_for_property(sim, workplace_prop)
    low, high = _npc_wallet_range(
        role,
        career=career,
        workplace_prop=workplace_prop,
        economy_profile=economy_profile,
    )
    midpoint = (float(low) + float(high)) / 2.0
    wage = int(round(midpoint / 14.0))
    if staff_role == "manager" and not any(token in career for token in _MANAGER_TOKENS):
        wage += 1
    elif staff_role == "staff":
        wage = max(3, wage)
    return int(max(2, min(9, wage)))


def grant_npc_wallet_credits(
    sim,
    actor_eid,
    amount,
    *,
    source="ambient_job",
    property_id=None,
    property_name="",
    wage_due=None,
    wage_paid=None,
    hour=None,
    emit_event=True,
):
    """Pay real carried credits; ``wallet_buffer`` is a banking target, not a wage cap."""
    if sim is None:
        return None
    try:
        actor_eid = int(actor_eid)
    except (TypeError, ValueError):
        return None
    amount = max(0, _int_or(amount, default=0))
    wage_due = amount if wage_due is None else max(0, _int_or(wage_due, default=0))
    wage_paid = amount if wage_paid is None else max(0, _int_or(wage_paid, default=0))
    if amount <= 0 and wage_paid <= 0 and wage_due <= 0:
        return None

    inventory = sim.ecs.get(Inventory).get(actor_eid)
    profile = sim.ecs.get(FinancialProfile).get(actor_eid)
    if inventory is None or profile is None:
        return None
    ensure_financial_income_fields(profile)

    wallet_before = inventory_liquid_credits(inventory)
    wallet_buffer = max(0, _int_or(getattr(profile, "wallet_buffer", 0), default=0))
    wallet_granted = int(amount)
    instance_id = None
    if wallet_granted > 0:
        existing = next(
            (entry for entry in tuple(getattr(inventory, "items", ()) or ()) if is_credstick_item(entry.get("item_id"))),
            None,
        )
        if existing is not None:
            metadata = dict(existing.get("metadata") or {})
            metadata["stored_credits"] = int(
                credstick_total_credits(
                    quantity=existing.get("quantity", 1),
                    metadata=metadata,
                )
                + wallet_granted
            )
            metadata["income_source"] = _text(source).lower() or "ambient_job"
            metadata["property_id"] = _text(property_id) or None
            existing["metadata"] = metadata
            instance_id = existing.get("instance_id")
        else:
            item_def = ITEM_CATALOG.get(CREDSTICK_ITEM_ID, {})
            metadata = {
                "ambient_spawn": False,
                "stored_credits": int(wallet_granted),
                "source": "npc_wage",
                "income_source": _text(source).lower() or "ambient_job",
                "property_id": _text(property_id) or None,
            }
            added, instance_id = inventory.add_item(
                item_id=CREDSTICK_ITEM_ID,
                quantity=1,
                stack_max=max(1, int(item_def.get("stack_max", 1) or 1)),
                instance_factory=sim.new_item_instance_id,
                owner_eid=actor_eid,
                owner_tag="npc",
                metadata=metadata,
            )
            if not added:
                wallet_granted = 0

    if wage_paid > 0:
        profile.last_income_hour = None if hour in {None, ""} else int(hour)

    wallet_after = inventory_liquid_credits(inventory)
    result = {
        "npc_eid": int(actor_eid),
        "source": _text(source).lower() or "ambient_job",
        "property_id": _text(property_id) or None,
        "property_name": _text(property_name),
        "wage_due": int(wage_due),
        "wage_paid": int(wage_paid),
        "wallet_granted": int(wallet_granted),
        "wallet_before": int(wallet_before),
        "wallet_after": int(wallet_after),
        "wallet_buffer": int(wallet_buffer),
        "item_instance_id": instance_id,
        "hour": None if hour in {None, ""} else int(hour),
    }
    if emit_event:
        sim.emit(Event("npc_wage_paid", **result))
    return result


__all__ = [
    "ensure_financial_income_fields",
    "grant_npc_wallet_credits",
    "inventory_liquid_credits",
    "npc_hourly_wage",
    "spend_npc_wallet_credits",
]
