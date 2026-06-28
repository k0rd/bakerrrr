"""Shared helpers for item-backed weapon equipment."""

from __future__ import annotations

import random

from game.components import Inventory, WeaponLoadout
from game.items import ITEM_CATALOG
from game.system_support.item_runtime import _default_weapon_reserve_ammo, _weapon_uses_ammo
from game.weapons import roll_weapon_instance, weapon_by_id


def item_id_for_weapon_id(weapon_id, *, item_catalog=None):
    """Return the first catalog item that equips the requested weapon id."""
    weapon_id = str(weapon_id or "").strip()
    if not weapon_id:
        return ""
    item_catalog = item_catalog or ITEM_CATALOG
    if weapon_id in item_catalog:
        item_def = item_catalog.get(weapon_id, {})
        if str(item_def.get("weapon_id", "") or "").strip() == weapon_id:
            return weapon_id
    for item_id, item_def in item_catalog.items():
        if str(item_def.get("weapon_id", "") or "").strip() == weapon_id:
            return str(item_id)
    return ""


def weapon_id_for_item_id(item_id, *, item_catalog=None):
    item_id = str(item_id or "").strip()
    if not item_id:
        return ""
    item_catalog = item_catalog or ITEM_CATALOG
    item_def = item_catalog.get(item_id, {})
    return str(item_def.get("weapon_id", "") or "").strip()


def roll_role_weapon_reserve_ammo(rng, weapon_id):
    """Assign a modest, deterministic reserve so NPC weapons are not always full."""
    weapon = weapon_by_id(weapon_id)
    if not weapon or not _weapon_uses_ammo(weapon):
        return 0
    default = int(max(0, _default_weapon_reserve_ammo(weapon)))
    if default <= 0:
        return 0
    rng = rng or random.Random(str(weapon_id))
    roll = float(rng.random())
    if roll < 0.08:
        return max(0, int(round(default * 0.15)))
    if roll < 0.28:
        return max(1, int(round(default * 0.35)))
    if roll < 0.82:
        return max(1, int(round(default * (0.45 + rng.random() * 0.35))))
    if roll < 0.96:
        return max(1, int(round(default * (0.8 + rng.random() * 0.18))))
    return default


def _ensure_inventory(sim, eid, *, capacity=10):
    inventories = sim.ecs.get(Inventory)
    inventory = inventories.get(eid)
    if inventory is None:
        inventory = Inventory(capacity=capacity)
        sim.ecs.add(eid, inventory)
    return inventory


def _ensure_weapon_loadout(sim, eid):
    loadouts = sim.ecs.get(WeaponLoadout)
    loadout = loadouts.get(eid)
    if loadout is None:
        loadout = WeaponLoadout()
        sim.ecs.add(eid, loadout)
    return loadout


def _metadata_reserve_ammo(metadata):
    if not isinstance(metadata, dict):
        return None
    for key in ("reserve_ammo", "weapon_reserve_ammo"):
        if key not in metadata:
            continue
        try:
            return max(0, int(metadata.get(key)))
        except (TypeError, ValueError):
            return None
    return None


def equip_linked_weapon_item(
    sim,
    eid,
    *,
    item_id=None,
    weapon_id=None,
    rng=None,
    owner_tag=None,
    metadata=None,
    source_kind="role_equipment",
    named_chance=0.08,
    reserve_ammo=None,
):
    """Create a real inventory item and link it to an actor weapon loadout."""
    item_id = str(item_id or "").strip()
    weapon_id = str(weapon_id or "").strip()
    if item_id:
        weapon_id = weapon_id or weapon_id_for_item_id(item_id)
    elif weapon_id:
        item_id = item_id_for_weapon_id(weapon_id)
    if not item_id or not weapon_id:
        return {"ok": False, "reason": "missing_weapon_item"}

    item_def = ITEM_CATALOG.get(item_id, {})
    if not item_def:
        return {"ok": False, "reason": "unknown_item"}

    inventory = _ensure_inventory(sim, eid)
    loadout = _ensure_weapon_loadout(sim, eid)
    rng = rng or random.Random(f"{getattr(sim, 'seed', 0)}:weapon-equipment:{eid}:{item_id}")
    owner_tag = str(owner_tag or ("player" if eid == getattr(sim, "player_eid", None) else "npc"))
    meta = dict(metadata or {})
    meta.setdefault("source_kind", str(source_kind or "role_equipment"))
    meta["equipped"] = True
    if reserve_ammo is None:
        reserve_ammo = _metadata_reserve_ammo(meta)
    if reserve_ammo is None:
        reserve_ammo = roll_role_weapon_reserve_ammo(rng, weapon_id)
    reserve_ammo = max(0, int(reserve_ammo))

    added, instance_id = inventory.add_item(
        item_id=item_id,
        quantity=1,
        stack_max=int(max(1, item_def.get("stack_max", 1))),
        instance_factory=sim.new_item_instance_id,
        owner_eid=eid,
        owner_tag=owner_tag,
        metadata=meta,
    )
    if not added or not instance_id:
        return {"ok": False, "reason": "inventory_full"}

    instance = roll_weapon_instance(rng, weapon_id, named_chance=float(named_chance))
    instance["inventory_instance_id"] = instance_id
    custom_name = str(instance.get("custom_name", "") or "").strip()
    linked_meta = dict(meta)
    linked_meta["weapon_instance"] = dict(instance)
    linked_meta["reserve_ammo"] = reserve_ammo
    if custom_name:
        linked_meta["display_name"] = custom_name
    inventory.update_item_metadata(instance_id, metadata=linked_meta, replace=True)

    loadout.add_weapon(weapon_id, instance=instance)
    loadout.equip(weapon_id)
    loadout.set_reserve_ammo_value(weapon_id, reserve_ammo, instance_id=instance_id)
    return {
        "ok": True,
        "item_id": item_id,
        "weapon_id": weapon_id,
        "instance_id": instance_id,
        "reserve_ammo": reserve_ammo,
        "weapon_instance": dict(instance),
    }


def _inventory_entry_for_weapon(inventory, weapon_id, *, instance_id=""):
    if inventory is None:
        return None
    instance_id = str(instance_id or "").strip()
    if instance_id:
        entry = inventory.find(instance_id=instance_id)
        if entry:
            return entry
    weapon_id = str(weapon_id or "").strip()
    if not weapon_id:
        return None
    for entry in getattr(inventory, "items", ()) or ():
        if weapon_id_for_item_id(entry.get("item_id")) == weapon_id:
            return entry
    return None


def _clear_weapon_reserve(loadout, weapon_id, *, instance_id=""):
    if not loadout:
        return
    weapon_id = str(weapon_id or "").strip()
    if not weapon_id:
        return
    instance_id = str(instance_id or "").strip()
    keys = {weapon_id}
    if instance_id:
        keys.add(f"{weapon_id}::{instance_id}")
    for key in list(getattr(loadout, "reserve_ammo", {}) or {}):
        if key in keys or str(key).startswith(f"{weapon_id}::"):
            loadout.reserve_ammo.pop(key, None)


def sync_linked_weapon_item_reserve_ammo(sim, eid, weapon_id, reserve_ammo, *, instance_id=None):
    """Mirror live weapon reserve back onto the linked inventory item metadata."""
    weapon_id = str(weapon_id or "").strip()
    if not weapon_id:
        return False
    loadout = sim.ecs.get(WeaponLoadout).get(eid)
    if instance_id is None and loadout is not None:
        instance_id = loadout.weapon_inventory_instance_id(weapon_id)
    instance_id = str(instance_id or "").strip()
    if not instance_id:
        return False
    inventory = sim.ecs.get(Inventory).get(eid)
    if inventory is None:
        return False
    entry = inventory.find(instance_id=instance_id)
    if not entry:
        return False
    metadata = dict(entry.get("metadata") or {})
    try:
        reserve = max(0, int(reserve_ammo))
    except (TypeError, ValueError):
        reserve = 0
    metadata["reserve_ammo"] = reserve
    inventory.update_item_metadata(instance_id, metadata=metadata, replace=True)
    return True


def drop_actor_equipped_weapon(sim, eid, x, y, z=0, *, reason="drop_weapon"):
    """Move the actor's current equipped weapon item to the ground."""
    loadout = sim.ecs.get(WeaponLoadout).get(eid)
    if loadout is None or not loadout.weapon_ids:
        return {"ok": False, "reason": "unarmed"}

    weapon_id = str(loadout.current_weapon() or loadout.weapon_ids[0] or "").strip()
    if not weapon_id:
        return {"ok": False, "reason": "unarmed"}

    instance = dict(loadout.weapon_instance(weapon_id))
    instance_id = str(loadout.weapon_inventory_instance_id(weapon_id) or "").strip()
    reserve = loadout.reserve_ammo_value(weapon_id, default=None, instance_id=instance_id)
    inventory = sim.ecs.get(Inventory).get(eid)
    entry = _inventory_entry_for_weapon(inventory, weapon_id, instance_id=instance_id)
    removed = None
    if inventory is not None and entry is not None:
        removed = inventory.remove_item(instance_id=entry.get("instance_id"), quantity=1)

    item_id = str((removed or {}).get("item_id", "") or "").strip()
    if not item_id:
        item_id = item_id_for_weapon_id(weapon_id)
    if not item_id:
        loadout.remove_weapon(weapon_id)
        _clear_weapon_reserve(loadout, weapon_id, instance_id=instance_id)
        return {"ok": False, "reason": "missing_weapon_item", "weapon_id": weapon_id}

    ground_instance_id = str((removed or {}).get("instance_id", "") or instance_id or "").strip() or None
    meta = dict((removed or {}).get("metadata") or {})
    meta.pop("equipped", None)
    meta["last_equipped_by_eid"] = eid
    meta["last_equipped_drop_reason"] = str(reason or "drop_weapon")
    if instance:
        if ground_instance_id:
            instance["inventory_instance_id"] = ground_instance_id
        meta["weapon_instance"] = dict(instance)
        custom_name = str(instance.get("custom_name", "") or "").strip()
        if custom_name:
            meta["display_name"] = custom_name
    if reserve is not None:
        meta["reserve_ammo"] = max(0, int(reserve))

    ground_id = sim.register_ground_item(
        item_id=item_id,
        x=int(x),
        y=int(y),
        z=int(z),
        quantity=int(max(1, (removed or {}).get("quantity", 1) or 1)),
        owner_eid=(removed or {}).get("owner_eid", eid),
        owner_tag=(removed or {}).get("owner_tag", "npc"),
        instance_id=ground_instance_id,
        metadata=meta,
    )

    loadout.remove_weapon(weapon_id)
    _clear_weapon_reserve(loadout, weapon_id, instance_id=ground_instance_id or instance_id)
    return {
        "ok": True,
        "weapon_id": weapon_id,
        "item_id": item_id,
        "ground_item_id": ground_id,
        "instance_id": ground_instance_id,
        "reserve_ammo": reserve,
    }
