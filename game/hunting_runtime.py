"""Shared hunting, carcass, and meat-preparation helpers."""

from __future__ import annotations

import copy
from typing import Iterable

from engine.events import Event
from engine.systems import System
from game.components import AnimalPhysicalProfile, CreatureIdentity, EcologyProfile, Inventory, PlayerAssets
from game.items import ITEM_CATALOG, item_display_name
from game.system_support.interaction_ordering import _manhattan


RAW_MEAT_ITEM_ID = "raw_game_meat"
BAGGED_MEAT_ITEM_ID = "bagged_game_meat"
COOKED_MEAT_ITEM_ID = "cooked_game_meat"
PACKAGED_MEAT_ITEM_ID = "packaged_game_meat"
KILL_BAG_ITEM_ID = "kill_bag"
FIELD_KNIFE_ITEM_ID = "field_knife"

FIELD_DRESSING_TOOL_TAGS = {"knife", "blade"}
REDUCED_FIELD_DRESSING_TOOL_IDS = {"pocket_multitool"}
DIRECT_FIELD_DRESSING_TOOL_IDS = {FIELD_KNIFE_ITEM_ID, "trail_machete", "shiv_knife"}

SIZE_CLASS_ORDER = ("tiny", "small", "medium", "large", "huge")
BASE_MEAT_UNITS_BY_SIZE = {
    "tiny": 0,
    "small": 1,
    "medium": 2,
    "large": 4,
    "huge": 6,
}
HUNTABLE_SPECIES = {
    "deer",
    "boar",
    "feral_boar",
    "wild_hog",
    "black_bear",
    "bear",
    "cougar",
    "mountain_lion",
    "wolf",
    "gray_wolf",
    "coyote",
    "alligator",
}
HUNTABLE_TAXONOMY = {"ungulate"}
MEAT_INPUT_ITEM_IDS = {RAW_MEAT_ITEM_ID, BAGGED_MEAT_ITEM_ID}
COOKABLE_MEAT_ITEM_IDS = {RAW_MEAT_ITEM_ID, BAGGED_MEAT_ITEM_ID}


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _slug(value):
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def animal_size_class_for_score(score, juvenile=False):
    """Return the coarse animal size class used by hunting and presentation."""
    score = _safe_float(score, 0.0)
    if score < 12.0:
        size_class = "tiny"
    elif score < 35.0:
        size_class = "small"
    elif score < 55.0:
        size_class = "medium"
    elif score < 80.0:
        size_class = "large"
    else:
        size_class = "huge"
    if juvenile:
        idx = max(0, SIZE_CLASS_ORDER.index(size_class) - 1)
        size_class = SIZE_CLASS_ORDER[idx]
    return size_class


def _animal_identity_payload(sim, animal_eid):
    identities = sim.ecs.get(CreatureIdentity)
    physicals = sim.ecs.get(AnimalPhysicalProfile)
    ecologies = sim.ecs.get(EcologyProfile)
    identity = identities.get(animal_eid)
    physical = physicals.get(animal_eid)
    ecology = ecologies.get(animal_eid)
    payload = {}
    if identity:
        payload.update({
            "creature_type": str(getattr(identity, "creature_type", "") or "").strip().lower(),
            "taxonomy_class": str(getattr(identity, "taxonomy_class", "") or "").strip().lower(),
            "species": str(getattr(identity, "species", "") or "").strip().lower(),
            "common_name": str(getattr(identity, "common_name", "") or "").strip(),
            "display_name": str(identity.display_name() or "").strip(),
        })
    if physical:
        payload.update({
            "size_score": float(getattr(physical, "size_score", 0.0) or 0.0),
            "juvenile": bool(getattr(physical, "juvenile", False)),
        })
    if ecology:
        payload["ecology_species"] = str(getattr(ecology, "species", "") or "").strip().lower()
    return payload


def _payload_species_tokens(payload):
    tokens = set()
    for key in ("ecology_species", "common_name", "species", "display_name"):
        raw = payload.get(key)
        if raw:
            tokens.add(_slug(raw))
    species = str(payload.get("species", "") or "")
    if species:
        bits = species.replace("_", " ").split()
        if bits:
            tokens.add(_slug(bits[-1]))
    return {token for token in tokens if token}


def _payload_huntable(payload):
    creature_type = str(payload.get("creature_type", "") or "").strip().lower()
    if creature_type and creature_type != "animal":
        return False
    size_class = animal_size_class_for_score(payload.get("size_score", 0.0), juvenile=bool(payload.get("juvenile", False)))
    if BASE_MEAT_UNITS_BY_SIZE.get(size_class, 0) <= 0:
        return False
    taxonomy = str(payload.get("taxonomy_class", "") or "").strip().lower()
    if taxonomy in HUNTABLE_TAXONOMY:
        return True
    return bool(_payload_species_tokens(payload).intersection(HUNTABLE_SPECIES))


def hunting_yield_profile(sim, animal_eid=None, *, payload=None):
    payload = dict(payload or (_animal_identity_payload(sim, animal_eid) if animal_eid is not None else {}))
    if not _payload_huntable(payload):
        return None
    size_class = animal_size_class_for_score(payload.get("size_score", 0.0), juvenile=bool(payload.get("juvenile", False)))
    base_units = int(BASE_MEAT_UNITS_BY_SIZE.get(size_class, 0))
    if base_units <= 0:
        return None
    species_label = (
        str(payload.get("common_name", "") or "").strip()
        or str(payload.get("display_name", "") or "").strip()
        or str(payload.get("ecology_species", "") or "").replace("_", " ").strip()
        or "wildlife"
    )
    return {
        "animal_size_class": size_class,
        "base_units": base_units,
        "species_label": species_label,
        "species_key": sorted(_payload_species_tokens(payload))[0] if _payload_species_tokens(payload) else "wildlife",
        "taxonomy_class": str(payload.get("taxonomy_class", "") or "").strip().lower() or "other",
        "size_score": float(_safe_float(payload.get("size_score", 0.0), 0.0)),
        "juvenile": bool(payload.get("juvenile", False)),
    }


def _hunting_state(sim):
    state = getattr(sim, "hunting_carcasses", None)
    if not isinstance(state, dict):
        state = {}
        sim.hunting_carcasses = state
    if not hasattr(sim, "next_hunting_carcass_id"):
        sim.next_hunting_carcass_id = 1
    return state


def _new_carcass_id(sim):
    try:
        next_id = int(getattr(sim, "next_hunting_carcass_id", 1))
    except (TypeError, ValueError):
        next_id = 1
    sim.next_hunting_carcass_id = next_id + 1
    return f"carcass-{next_id}"


def create_hunting_carcass(sim, *, animal_eid=None, x=0, y=0, z=0, source_eid=None, payload=None):
    profile = hunting_yield_profile(sim, animal_eid=animal_eid, payload=payload)
    if not profile:
        return None
    state = _hunting_state(sim)
    carcass_id = _new_carcass_id(sim)
    record = {
        "carcass_id": carcass_id,
        "animal_eid": animal_eid,
        "animal_name": str((payload or {}).get("target_name", "") or profile.get("species_label") or "wildlife").strip(),
        "species_label": profile["species_label"],
        "species_key": profile["species_key"],
        "taxonomy_class": profile["taxonomy_class"],
        "size_score": profile["size_score"],
        "animal_size_class": profile["animal_size_class"],
        "base_units": int(profile["base_units"]),
        "x": int(x),
        "y": int(y),
        "z": int(z),
        "source_eid": source_eid,
        "created_tick": _safe_int(getattr(sim, "tick", 0), 0),
        "harvested": False,
    }
    state[carcass_id] = record
    sim.emit(Event("hunting_carcass_created", **record))
    return record


def hunting_carcasses_at(sim, x, y, z=0, *, include_harvested=False):
    state = _hunting_state(sim)
    rows = []
    for record in state.values():
        if not include_harvested and bool(record.get("harvested")):
            continue
        if int(record.get("x", 0)) == int(x) and int(record.get("y", 0)) == int(y) and int(record.get("z", 0)) == int(z):
            rows.append(record)
    return sorted(rows, key=lambda row: str(row.get("carcass_id", "")))


def nearest_hunting_carcass(sim, x, y, z=0, *, radius=1, preferred_dir=None, exact_direction=False):
    state = _hunting_state(sim)
    candidates = []
    target = None
    if exact_direction and isinstance(preferred_dir, tuple) and len(preferred_dir) >= 2:
        dx = _safe_int(preferred_dir[0], 0)
        dy = _safe_int(preferred_dir[1], 0)
        if dx or dy:
            target = (int(x) + dx, int(y) + dy, int(z))
    for record in state.values():
        if bool(record.get("harvested")):
            continue
        rx, ry, rz = int(record.get("x", 0)), int(record.get("y", 0)), int(record.get("z", 0))
        if int(rz) != int(z):
            continue
        if target is not None and (rx, ry, rz) != target:
            continue
        dist = _manhattan(int(x), int(y), rx, ry)
        if dist > int(radius):
            continue
        candidates.append((dist, str(record.get("carcass_id", "")), record))
    if not candidates:
        return None
    candidates.sort(key=lambda row: (row[0], row[1]))
    return candidates[0][2]


def hunting_carcass_look_text(record):
    if not isinstance(record, dict) or bool(record.get("harvested")):
        return ""
    size_class = str(record.get("animal_size_class", "") or "animal").replace("_", " ")
    species = str(record.get("species_label", "") or record.get("animal_name", "") or "wildlife").strip()
    units = int(record.get("base_units", 0) or 0)
    if units <= 0:
        return f"carcass:{size_class} {species}; no usable cuts"
    return f"carcass:{size_class} {species}; field dress with a blade, about {units} meat"


def _inventory_for(sim, eid):
    return sim.ecs.get(Inventory).get(eid)


def _entry_tags(item_id):
    item = ITEM_CATALOG.get(str(item_id or "").strip().lower(), {})
    return {str(tag).strip().lower() for tag in tuple(item.get("tags", ()) or ()) if str(tag).strip()}


def _field_dressing_tool(inventory):
    if not inventory:
        return None
    fallback = None
    for entry in tuple(getattr(inventory, "items", ()) or ()):
        item_id = str(entry.get("item_id", "") or "").strip().lower()
        tags = _entry_tags(item_id)
        if item_id in DIRECT_FIELD_DRESSING_TOOL_IDS or tags.intersection(FIELD_DRESSING_TOOL_TAGS):
            return {"item_id": item_id, "quality": 1.0}
        if item_id in REDUCED_FIELD_DRESSING_TOOL_IDS and fallback is None:
            fallback = {"item_id": item_id, "quality": 0.65}
    return fallback


def _has_kill_bag(inventory):
    if not inventory:
        return False
    return any(str(entry.get("item_id", "") or "").strip().lower() == KILL_BAG_ITEM_ID for entry in tuple(inventory.items or ()))


def _clone_inventory(inventory):
    clone = Inventory(capacity=getattr(inventory, "capacity", 10))
    clone.items = copy.deepcopy(list(getattr(inventory, "items", ()) or ()))
    return clone


def _inventory_owner_for(sim, eid):
    if eid == getattr(sim, "player_eid", None):
        return eid, "player"
    return eid, "npc"


def _inventory_can_accept(inventory, item_id, quantity, *, metadata=None, owner_eid=None, owner_tag=None):
    if not inventory:
        return False
    item_def = ITEM_CATALOG.get(str(item_id or "").strip().lower(), {})
    clone = _clone_inventory(inventory)
    added, _instance_id = clone.add_item(
        item_id,
        quantity=max(1, int(quantity)),
        stack_max=max(1, int(item_def.get("stack_max", 1) or 1)),
        owner_eid=owner_eid,
        owner_tag=owner_tag,
        metadata=metadata or {},
    )
    return bool(added)


def _add_inventory_item(sim, inventory, item_id, quantity, *, metadata=None, owner_eid=None, owner_tag=None):
    item_def = ITEM_CATALOG.get(str(item_id or "").strip().lower(), {})
    return inventory.add_item(
        item_id,
        quantity=max(1, int(quantity)),
        stack_max=max(1, int(item_def.get("stack_max", 1) or 1)),
        instance_factory=sim.new_item_instance_id,
        owner_eid=owner_eid,
        owner_tag=owner_tag,
        metadata=metadata or {},
    )


def field_dress_carcass(sim, eid, carcass_id=None):
    inventory = _inventory_for(sim, eid)
    if not inventory:
        sim.emit(Event("hunting_carcass_blocked", eid=eid, carcass_id=carcass_id, reason="no_inventory"))
        return False
    state = _hunting_state(sim)
    record = state.get(str(carcass_id or "").strip())
    if not record or bool(record.get("harvested")):
        sim.emit(Event("hunting_carcass_blocked", eid=eid, carcass_id=carcass_id, reason="unavailable"))
        return False
    tool = _field_dressing_tool(inventory)
    if not tool:
        sim.emit(Event("hunting_carcass_blocked", eid=eid, carcass_id=record.get("carcass_id"), reason="no_tool", animal_name=record.get("animal_name")))
        return False
    base_units = max(0, int(record.get("base_units", 0) or 0))
    if base_units <= 0:
        sim.emit(Event("hunting_carcass_blocked", eid=eid, carcass_id=record.get("carcass_id"), reason="no_usable_meat", animal_name=record.get("animal_name")))
        return False
    quality = float(tool.get("quality", 1.0) or 1.0)
    quantity = max(1, int(base_units if quality >= 0.95 else round(base_units * 0.65)))
    kill_bag = _has_kill_bag(inventory)
    if kill_bag and base_units >= 2:
        quantity += 1
    output_item_id = BAGGED_MEAT_ITEM_ID if kill_bag else RAW_MEAT_ITEM_ID
    metadata = {
        "source": "hunting",
        "source_context": "field_dressed",
        "animal_name": record.get("animal_name"),
        "animal_species": record.get("species_label"),
        "animal_size_class": record.get("animal_size_class"),
        "field_dressed_tick": _safe_int(getattr(sim, "tick", 0), 0),
        "field_dressing_tool": tool.get("item_id"),
        "kill_bag_used": bool(kill_bag),
        "legal_status": "legal",
    }
    owner_eid, owner_tag = _inventory_owner_for(sim, eid)
    if not _inventory_can_accept(inventory, output_item_id, quantity, metadata=metadata, owner_eid=owner_eid, owner_tag=owner_tag):
        sim.emit(Event(
            "hunting_carcass_blocked",
            eid=eid,
            carcass_id=record.get("carcass_id"),
            animal_name=record.get("animal_name"),
            reason="inventory_full",
            output_item_id=output_item_id,
            quantity=quantity,
        ))
        return False
    added, _instance_id = _add_inventory_item(sim, inventory, output_item_id, quantity, metadata=metadata, owner_eid=owner_eid, owner_tag=owner_tag)
    if not added:
        sim.emit(Event("hunting_carcass_blocked", eid=eid, carcass_id=record.get("carcass_id"), reason="inventory_full"))
        return False
    record["harvested"] = True
    record["harvested_tick"] = _safe_int(getattr(sim, "tick", 0), 0)
    record["harvested_by_eid"] = eid
    record["output_item_id"] = output_item_id
    record["output_quantity"] = int(quantity)
    sim.emit(Event(
        "hunting_carcass_harvested",
        eid=eid,
        carcass_id=record.get("carcass_id"),
        animal_name=record.get("animal_name"),
        species_label=record.get("species_label"),
        animal_size_class=record.get("animal_size_class"),
        output_item_id=output_item_id,
        output_item_name=item_display_name(output_item_id, metadata=metadata, item_catalog=ITEM_CATALOG),
        quantity=int(quantity),
        tool_item_id=tool.get("item_id"),
        kill_bag_used=bool(kill_bag),
    ))
    return True


def _eligible_meat_entries(inventory, allowed_item_ids: Iterable[str]):
    allowed = {str(item_id or "").strip().lower() for item_id in allowed_item_ids}
    rows = []
    if not inventory:
        return rows
    for entry in tuple(getattr(inventory, "items", ()) or ()):
        item_id = str(entry.get("item_id", "") or "").strip().lower()
        if item_id in allowed:
            rows.append(entry)
    return rows


def _remove_meat_quantity(inventory, entries, quantity):
    remaining = max(0, int(quantity))
    removed = 0
    for entry in list(entries):
        if remaining <= 0:
            break
        amount = min(remaining, max(0, int(entry.get("quantity", 1) or 1)))
        if amount <= 0:
            continue
        removed_entry = inventory.remove_item(instance_id=entry.get("instance_id"), quantity=amount)
        if removed_entry:
            removed += int(removed_entry.get("quantity", amount) or amount)
            remaining -= int(removed_entry.get("quantity", amount) or amount)
    return removed


def _clone_after_removing(inventory, entries, quantity):
    clone = _clone_inventory(inventory)
    clone_entries_by_instance = {
        str(entry.get("instance_id", "")): entry
        for entry in tuple(getattr(clone, "items", ()) or ())
    }
    remaining = max(0, int(quantity))
    for entry in entries:
        if remaining <= 0:
            break
        iid = str(entry.get("instance_id", ""))
        clone_entry = clone_entries_by_instance.get(iid)
        if not clone_entry:
            continue
        amount = min(remaining, max(0, int(clone_entry.get("quantity", 1) or 1)))
        if amount <= 0:
            continue
        clone.remove_item(instance_id=clone_entry.get("instance_id"), quantity=amount)
        remaining -= amount
    return clone


def convert_meat_stack(sim, eid, mode, *, max_units=None):
    mode = str(mode or "").strip().lower()
    inventory = _inventory_for(sim, eid)
    if not inventory:
        return {"ok": False, "reason": "no_inventory"}
    if mode == "campfire_cook":
        entries = _eligible_meat_entries(inventory, COOKABLE_MEAT_ITEM_IDS)
        if not entries:
            return {"ok": False, "reason": "no_meat"}
        input_units = sum(max(0, int(entry.get("quantity", 1) or 1)) for entry in entries)
        if max_units is not None:
            input_units = min(input_units, max(1, int(max_units)))
        output_units = max(1, int(round(float(input_units) * 0.65)))
        output_item_id = COOKED_MEAT_ITEM_ID
        credits_spent = 0
    elif mode == "butcher_prepare":
        entries = _eligible_meat_entries(inventory, MEAT_INPUT_ITEM_IDS)
        if not entries:
            return {"ok": False, "reason": "no_meat"}
        total_units = sum(max(0, int(entry.get("quantity", 1) or 1)) for entry in entries)
        assets = sim.ecs.get(PlayerAssets).get(eid)
        credits = max(0, int(getattr(assets, "credits", 0) if assets else 0))
        fee_per_unit = 3
        affordable_units = credits // fee_per_unit
        input_units = min(total_units, affordable_units)
        if max_units is not None:
            input_units = min(input_units, max(1, int(max_units)))
        if input_units <= 0:
            return {"ok": False, "reason": "no_credits", "cost": min(total_units, 1) * fee_per_unit, "credits": credits}
        output_units = int(input_units)
        output_item_id = PACKAGED_MEAT_ITEM_ID
        credits_spent = int(input_units) * fee_per_unit
    else:
        return {"ok": False, "reason": "unavailable"}
    if input_units <= 0 or output_units <= 0:
        return {"ok": False, "reason": "no_meat"}
    metadata = {
        "source": "hunting",
        "source_context": mode,
        "processed_tick": _safe_int(getattr(sim, "tick", 0), 0),
        "input_units": int(input_units),
        "legal_status": "legal",
    }
    owner_eid, owner_tag = _inventory_owner_for(sim, eid)
    clone = _clone_after_removing(inventory, entries, input_units)
    item_def = ITEM_CATALOG.get(output_item_id, {})
    clone_added, _clone_instance = clone.add_item(
        output_item_id,
        quantity=int(output_units),
        stack_max=max(1, int(item_def.get("stack_max", 1) or 1)),
        owner_eid=owner_eid,
        owner_tag=owner_tag,
        metadata=metadata,
    )
    if not clone_added:
        return {"ok": False, "reason": "inventory_full", "output_item_id": output_item_id, "quantity": int(output_units)}
    removed = _remove_meat_quantity(inventory, entries, input_units)
    if removed < input_units:
        return {"ok": False, "reason": "lost_input"}
    assets = sim.ecs.get(PlayerAssets).get(eid)
    if credits_spent and assets:
        assets.credits = max(0, int(getattr(assets, "credits", 0)) - int(credits_spent))
    added, _instance = _add_inventory_item(sim, inventory, output_item_id, output_units, metadata=metadata, owner_eid=owner_eid, owner_tag=owner_tag)
    if not added:
        return {"ok": False, "reason": "inventory_full", "output_item_id": output_item_id, "quantity": int(output_units)}
    return {
        "ok": True,
        "mode": mode,
        "input_units": int(input_units),
        "output_units": int(output_units),
        "output_item_id": output_item_id,
        "output_item_name": item_display_name(output_item_id, metadata=metadata, item_catalog=ITEM_CATALOG),
        "credits_spent": int(credits_spent),
    }


class HuntingCarcassSystem(System):
    """Creates saved carcass records from eligible wildlife death events."""

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("npc_killed", self.on_npc_killed)
        self.runs_without_turn = True

    def on_npc_killed(self, event):
        payload = dict(event.data.get("animal_payload", {}) or {})
        if not payload:
            return
        payload["target_name"] = event.data.get("target_name")
        create_hunting_carcass(
            self.sim,
            animal_eid=event.data.get("target_eid"),
            x=event.data.get("x", 0),
            y=event.data.get("y", 0),
            z=event.data.get("z", 0),
            source_eid=event.data.get("source_eid"),
            payload=payload,
        )


__all__ = [
    "BAGGED_MEAT_ITEM_ID",
    "COOKED_MEAT_ITEM_ID",
    "FIELD_KNIFE_ITEM_ID",
    "HuntingCarcassSystem",
    "KILL_BAG_ITEM_ID",
    "PACKAGED_MEAT_ITEM_ID",
    "RAW_MEAT_ITEM_ID",
    "animal_size_class_for_score",
    "convert_meat_stack",
    "create_hunting_carcass",
    "field_dress_carcass",
    "hunting_carcass_look_text",
    "hunting_carcasses_at",
    "hunting_yield_profile",
    "nearest_hunting_carcass",
]
