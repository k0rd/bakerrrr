"""Bounded, auditable resolution for inventory carried into a corpse drop."""

from __future__ import annotations

import copy
import hashlib
from collections import defaultdict

from game.appearance_loadout import (
    appearance_metadata_as_loose_item,
    appearance_metadata_for_entry,
    is_entry_worn,
)
from game.items import ITEM_CATALOG


TEXTILE_SCRAP_ITEM_ID = "textile_scrap"
CLOTHING_RECOVERY_DENOMINATOR = 2


def _key(value):
    return str(value or "").strip().lower()


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _worn_clothing_slot(entry, *, item_catalog=None):
    if not isinstance(entry, dict) or not is_entry_worn(entry):
        return ""
    catalog = item_catalog or ITEM_CATALOG
    item_id = _key(entry.get("item_id"))
    item_def = catalog.get(item_id, {}) if isinstance(catalog, dict) else {}
    tags = {_key(tag) for tag in tuple((item_def or {}).get("tags", ()) or ()) if _key(tag)}
    if "clothing" not in tags:
        return ""

    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    nested = metadata.get("appearance") if isinstance(metadata.get("appearance"), dict) else {}
    slot = _key(metadata.get("appearance_slot") or nested.get("worn_slot"))
    if slot:
        return slot
    profile = appearance_metadata_for_entry(entry, item_catalog=catalog)
    slots = tuple(_key(value) for value in tuple(profile.get("slots", ()) or ()) if _key(value))
    return slots[0] if slots else "unslotted_clothing"


def _entry_identity(entry):
    return (
        _key(entry.get("item_id")),
        str(entry.get("instance_id", "") or "").strip(),
        _int(entry.get("quantity"), 1),
    )


def _corpse_loot_roll(sim, target_eid, death_token, label, upper_bound):
    upper_bound = max(0, _int(upper_bound, 0))
    if upper_bound <= 0:
        return 0
    token = repr((
        _int(getattr(sim, "seed", 0), 0),
        target_eid,
        str(death_token or "").strip(),
        str(label or "").strip().lower(),
    )).encode("utf-8")
    digest = hashlib.blake2b(token, digest_size=8).digest()
    return int.from_bytes(digest, "big") % upper_bound


def _textile_scrap_drops(destroyed_clothing, *, item_catalog=None):
    if not destroyed_clothing:
        return ()
    catalog = item_catalog or ITEM_CATALOG
    stack_max = max(1, _int((catalog.get(TEXTILE_SCRAP_ITEM_ID, {}) or {}).get("stack_max"), 99))
    units = []
    for record in destroyed_clothing:
        quantity = max(1, _int(record.get("quantity"), 1))
        units.extend([record] * quantity)

    drops = []
    for start in range(0, len(units), stack_max):
        chunk = units[start:start + stack_max]
        drops.append({
            "item_id": TEXTILE_SCRAP_ITEM_ID,
            "quantity": len(chunk),
            "drop_kind": "textile_scrap",
            "metadata": {
                "source_context": "corpse_clothing_salvage",
                "drop_kind": "textile_scrap",
                "source_clothing_item_ids": tuple(record["item_id"] for record in chunk),
                "source_clothing_instance_ids": tuple(
                    record["instance_id"] for record in chunk if record.get("instance_id")
                ),
                "source_clothing_slots": tuple(record["slot"] for record in chunk),
                "source_clothing_count": len(chunk),
            },
        })
    return tuple(drops)


def resolve_corpse_inventory_drops(
    sim,
    target_eid,
    inventory,
    *,
    death_token="",
    item_catalog=None,
):
    """Resolve normal cargo plus zero-or-one intact garment per worn slot.

    Non-clothing inventory and jewelry keep their existing ordinary-drop
    behavior. Every worn garment that does not win its slot's recovery roll is
    represented by one textile-scrap unit, preserving an exact salvage ledger
    without leaving a complete replacement wardrobe on every corpse.
    """

    catalog = item_catalog or ITEM_CATALOG
    ordinary_drops = []
    clothing_by_slot = defaultdict(list)
    for raw_entry in tuple(getattr(inventory, "items", ()) or ()):
        if not isinstance(raw_entry, dict):
            continue
        entry = copy.deepcopy(raw_entry)
        item_id = _key(entry.get("item_id"))
        if not item_id:
            continue
        entry["item_id"] = item_id
        entry["quantity"] = max(1, _int(entry.get("quantity"), 1))
        slot = _worn_clothing_slot(entry, item_catalog=catalog)
        if slot:
            clothing_by_slot[slot].append(entry)
        else:
            ordinary_drops.append(entry)

    intact_clothing = []
    destroyed_clothing = []
    for slot in sorted(clothing_by_slot):
        candidates = sorted(clothing_by_slot[slot], key=_entry_identity)
        survivor_index = None
        if _corpse_loot_roll(
            sim,
            target_eid,
            death_token,
            f"clothing:{slot}:recover",
            CLOTHING_RECOVERY_DENOMINATOR,
        ):
            survivor_index = _corpse_loot_roll(
                sim,
                target_eid,
                death_token,
                f"clothing:{slot}:choice:{tuple(_entry_identity(entry) for entry in candidates)}",
                len(candidates),
            )
        for index, entry in enumerate(candidates):
            quantity = max(1, _int(entry.get("quantity"), 1))
            if survivor_index == index:
                intact = copy.deepcopy(entry)
                intact["quantity"] = 1
                intact["metadata"] = appearance_metadata_as_loose_item(intact.get("metadata"))
                intact["metadata"]["source_appearance_slot"] = slot
                intact["drop_kind"] = "intact_worn_clothing"
                intact_clothing.append(intact)
                quantity -= 1
            if quantity <= 0:
                continue
            destroyed_clothing.append({
                "item_id": entry["item_id"],
                "instance_id": str(entry.get("instance_id", "") or "").strip() or None,
                "quantity": quantity,
                "slot": slot,
                "resolution": "textile_scrap",
                "salvage_item_id": TEXTILE_SCRAP_ITEM_ID,
            })

    drops = ordinary_drops + intact_clothing
    drops.extend(_textile_scrap_drops(destroyed_clothing, item_catalog=catalog))
    return {
        "drops": tuple(drops),
        "destroyed_items": tuple(destroyed_clothing),
    }
