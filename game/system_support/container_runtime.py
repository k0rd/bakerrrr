"""Shared inventory-container runtime helpers."""

from game.appearance_loadout import clear_removed_entry_appearance, mark_inventory_instance_worn
from game.components import ArmorLoadout, Inventory, WeaponLoadout
from game.items import ITEM_CATALOG, item_display_name
from game.weapons import weapon_by_id


def _int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


ITEM_STOWED_CONTAINER_METADATA_KEY = "stowed_in_container"


def _entry_stowed_container_instance(entry):
    if not isinstance(entry, dict):
        return None
    metadata = entry.get("metadata", {})
    if not isinstance(metadata, dict):
        return None
    token = str(metadata.get(ITEM_STOWED_CONTAINER_METADATA_KEY, "") or "").strip()
    return token or None


def _inventory_entries_stowed_in_container(inventory, container_instance_id):
    container_instance_id = str(container_instance_id or "").strip()
    if not inventory or not container_instance_id:
        return []
    return [
        entry
        for entry in list(getattr(inventory, "items", ()) or ())
        if str(entry.get("instance_id", "")).strip() != container_instance_id
        and _entry_stowed_container_instance(entry) == container_instance_id
    ]


def _inventory_entries_loose_for_container(inventory, container_instance_id):
    container_instance_id = str(container_instance_id or "").strip()
    if not inventory:
        return []
    return [
        entry
        for entry in list(getattr(inventory, "items", ()) or ())
        if str(entry.get("instance_id", "")).strip() != container_instance_id
        and _entry_stowed_container_instance(entry) != container_instance_id
    ]


def _clear_inventory_container_assignments(inventory, container_instance_id):
    container_instance_id = str(container_instance_id or "").strip()
    if not inventory or not container_instance_id:
        return 0
    cleared = 0
    for entry in list(getattr(inventory, "items", ()) or ()):
        if _entry_stowed_container_instance(entry) != container_instance_id:
            continue
        metadata = dict(entry.get("metadata") or {})
        metadata.pop(ITEM_STOWED_CONTAINER_METADATA_KEY, None)
        inventory.update_item_metadata(entry["instance_id"], metadata=metadata, replace=True)
        cleared += 1
    return cleared


def _unlink_removed_item_from_gear(sim, eid, removed_entry, item_catalog=None):
    if eid is None or not isinstance(removed_entry, dict):
        return {}

    item_catalog = item_catalog or ITEM_CATALOG
    instance_id = str(removed_entry.get("instance_id", "")).strip()
    if not instance_id:
        return {}

    changes = {}
    armor_loadout = sim.ecs.get(ArmorLoadout).get(eid)
    if armor_loadout and armor_loadout.is_equipped(instance_id):
        changes["armor_name"] = armor_loadout.equipped_name or item_display_name(
            removed_entry.get("item_id"),
            metadata=removed_entry.get("metadata"),
            item_catalog=item_catalog,
        )
        changes["armor_item_id"] = armor_loadout.equipped_item_id or removed_entry.get("item_id")
        armor_loadout.clear()
        mark_inventory_instance_worn(sim, eid, instance_id, worn=False)

    appearance_changes = clear_removed_entry_appearance(sim, eid, removed_entry)
    if appearance_changes:
        changes.update(appearance_changes)

    weapon_loadout = sim.ecs.get(WeaponLoadout).get(eid)
    if weapon_loadout:
        for weapon_id, instance in list(weapon_loadout.weapon_instances.items()):
            if not isinstance(instance, dict):
                continue
            if str(instance.get("inventory_instance_id", "")).strip() != instance_id:
                continue
            weapon_name = str(instance.get("custom_name", "")).strip() or weapon_by_id(weapon_id).get("name", weapon_id)
            weapon_loadout.remove_weapon(weapon_id)
            changes["weapon_id"] = weapon_id
            changes["weapon_name"] = weapon_name
            break

    disguise_state = getattr(sim, "disguise_state", None)
    if isinstance(disguise_state, dict) and str(disguise_state.get("instance_id", "")).strip() == instance_id:
        changes["disguise_name"] = disguise_state.get("item_name") or item_display_name(
            removed_entry.get("item_id"),
            metadata=removed_entry.get("metadata"),
            item_catalog=item_catalog,
        )
        changes["disguise_item_id"] = disguise_state.get("item_id") or removed_entry.get("item_id")
        sim.disguise_state = None

    equipped_container = getattr(sim, "equipped_container", None)
    if isinstance(equipped_container, dict) and str(equipped_container.get("instance_id", "")).strip() == instance_id:
        changes["container_name"] = equipped_container.get("item_name") or item_display_name(
            removed_entry.get("item_id"),
            metadata=removed_entry.get("metadata"),
            item_catalog=item_catalog,
        )
        changes["container_item_id"] = equipped_container.get("item_id") or removed_entry.get("item_id")
        changes["container_bonus_slots"] = int(max(0, _int_or_default(equipped_container.get("bonus_slots"), 0)))
        sim.equipped_container = None
        inventory = sim.ecs.get(Inventory).get(eid)
        if inventory:
            inventory.capacity = max(1, inventory.capacity - changes["container_bonus_slots"])
            changes["released_container_items"] = _clear_inventory_container_assignments(inventory, instance_id)

    return changes
