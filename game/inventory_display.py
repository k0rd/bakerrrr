"""Display-order helpers for inventory-style panels.

The helpers in this module never mutate inventory storage. They only sort copied
row lists so UI actions can keep using stable inventory instance ids.
"""

from game.appearance_loadout import is_appearance_item, is_entry_worn
from game.components import ArmorLoadout, WeaponLoadout
from game.items import ITEM_CATALOG, item_inventory_slot_cost
from game.item_semantics import item_display_name_for_actor
from game.system_support.container_runtime import _entry_stowed_container_instance
from game.system_support.item_runtime import _item_armor_profile, _item_tags, _item_weapon_id


INVENTORY_SORT_MODES = ("default", "type", "equipped", "action", "slots", "name")
INVENTORY_SORT_LABELS = {
    "default": "pickup order",
    "type": "type",
    "equipped": "equipped",
    "action": "actions",
    "slots": "slots",
    "name": "name",
}


def normalize_inventory_sort_mode(mode):
    mode = str(mode or "default").strip().lower()
    return mode if mode in INVENTORY_SORT_MODES else "default"


def next_inventory_sort_mode(mode):
    mode = normalize_inventory_sort_mode(mode)
    index = INVENTORY_SORT_MODES.index(mode)
    return INVENTORY_SORT_MODES[(index + 1) % len(INVENTORY_SORT_MODES)]


def inventory_sort_label(mode):
    mode = normalize_inventory_sort_mode(mode)
    return INVENTORY_SORT_LABELS.get(mode, mode.replace("_", " "))


def inventory_panel_entries_sortable(panel_kind, container_view):
    panel_kind = str(panel_kind or "inventory").strip().lower() or "inventory"
    container_view = str(container_view or "pack").strip().lower() or "pack"
    return panel_kind != "container" or container_view == "pack"


def sort_inventory_entries(sim, actor_eid, entries, *, sort_mode=None, item_catalog=None):
    entries = list(entries or [])
    mode = normalize_inventory_sort_mode(sort_mode)
    if mode == "default" or len(entries) <= 1:
        return entries

    catalog = item_catalog or ITEM_CATALOG
    indexed = list(enumerate(entries))
    indexed.sort(key=lambda row: _inventory_sort_key(sim, actor_eid, row[1], row[0], mode, catalog))
    return [entry for _index, entry in indexed]


def _inventory_sort_key(sim, actor_eid, entry, original_index, mode, catalog):
    item_id = str((entry or {}).get("item_id", "") or "").strip().lower()
    item_def = catalog.get(item_id, {}) if item_id else {}
    name = item_display_name_for_actor(sim, actor_eid, entry, item_catalog=catalog).lower()
    type_rank = _type_rank(entry, item_def, catalog)
    equipped_rank = _equipped_rank(sim, actor_eid, entry, item_def)
    action_rank = _action_rank(entry, item_def, catalog)
    slot_cost = item_inventory_slot_cost(entry)

    if mode == "type":
        return (type_rank, name, item_id, original_index)
    if mode == "equipped":
        return (equipped_rank, type_rank, name, item_id, original_index)
    if mode == "action":
        return (action_rank, type_rank, name, item_id, original_index)
    if mode == "slots":
        return (-int(slot_cost), type_rank, name, item_id, original_index)
    if mode == "name":
        return (name, type_rank, item_id, original_index)
    return (original_index,)


def _type_rank(entry, item_def, catalog):
    category = str((item_def or {}).get("category", "") or "").strip().lower()
    tags = set(_item_tags(item_def))
    item_id = str((entry or {}).get("item_id", "") or "").strip().lower()
    drone_profile = item_def.get("drone_profile") if isinstance(item_def.get("drone_profile"), dict) else {}
    wire_profile = item_def.get("wire_profile") if isinstance(item_def.get("wire_profile"), dict) else {}
    wire_interface = (
        item_def.get("wire_interface_profile")
        if isinstance(item_def.get("wire_interface_profile"), dict)
        else {}
    )

    if _item_weapon_id(item_def):
        return (10, "weapon")
    if _item_armor_profile(item_def) or category == "armor" or "armor" in tags:
        return (20, "armor")
    if is_appearance_item(entry, item_catalog=catalog) or category == "cosmetic" or "clothing" in tags:
        return (30, "clothing")
    if category == "container" or isinstance(item_def.get("container"), dict):
        return (35, "container")
    if category in {"medical", "consumable"} or tags.intersection({"medical", "food", "drink", "drug"}):
        return (40, "consumable")
    if category == "throwable" or isinstance(item_def.get("throw_profile"), dict):
        return (45, "throwable")
    if drone_profile.get("kind") or category in {"drone", "drone_part"} or item_id.startswith("drone_"):
        return (50, "drone")
    if wire_profile.get("kind") or wire_interface.get("kind") or category in {"wireware", "wire_interface"}:
        return (55, "wire")
    if category in {"tool", "device"} or tags.intersection({"tool", "device"}):
        return (60, "tool")
    if category in {"credential", "token"} or tags.intersection({"credential", "key"}):
        return (70, "credential")
    if category == "ammo" or "ammo" in tags:
        return (80, "ammo")
    return (99, category or "other")


def _equipped_rank(sim, actor_eid, entry, item_def):
    instance_id = str((entry or {}).get("instance_id", "") or "").strip()
    if not instance_id:
        return 4
    armor_loadout = sim.ecs.get(ArmorLoadout).get(actor_eid)
    if armor_loadout and armor_loadout.is_equipped(instance_id):
        return 0
    weapon_loadout = sim.ecs.get(WeaponLoadout).get(actor_eid)
    weapon_id = _item_weapon_id(item_def)
    weapon_instance = weapon_loadout.weapon_instances.get(weapon_id, {}) if weapon_loadout and weapon_id else {}
    if (
        weapon_loadout
        and weapon_id
        and weapon_loadout.current_weapon() == weapon_id
        and isinstance(weapon_instance, dict)
        and str(weapon_instance.get("inventory_instance_id", "")).strip() == instance_id
    ):
        return 0
    active_disguise = getattr(sim, "disguise_state", None)
    if isinstance(active_disguise, dict) and str(active_disguise.get("instance_id", "")).strip() == instance_id:
        return 0
    equipped_container = getattr(sim, "equipped_container", None)
    if isinstance(equipped_container, dict) and str(equipped_container.get("instance_id", "")).strip() == instance_id:
        return 0
    if is_entry_worn(entry):
        return 1
    if _entry_stowed_container_instance(entry):
        return 3
    return 2


def _action_rank(entry, item_def, catalog):
    if _equipped_rank_like_metadata(entry):
        return 0
    if _item_weapon_id(item_def) or _item_armor_profile(item_def):
        return 10
    if is_appearance_item(entry, item_catalog=catalog):
        return 20
    if isinstance(item_def.get("container"), dict):
        return 25
    if item_def.get("effects") or str(item_def.get("category", "")).strip().lower() in {"medical", "consumable"}:
        return 30
    if isinstance(item_def.get("throw_profile"), dict):
        return 35
    drone_profile = item_def.get("drone_profile") if isinstance(item_def.get("drone_profile"), dict) else {}
    if drone_profile.get("kind"):
        return 40
    wire_profile = item_def.get("wire_profile") if isinstance(item_def.get("wire_profile"), dict) else {}
    wire_interface = (
        item_def.get("wire_interface_profile")
        if isinstance(item_def.get("wire_interface_profile"), dict)
        else {}
    )
    if wire_profile.get("kind") or wire_interface.get("kind"):
        return 45
    return 99


def _equipped_rank_like_metadata(entry):
    if is_entry_worn(entry):
        return True
    metadata = (entry or {}).get("metadata") if isinstance((entry or {}).get("metadata"), dict) else {}
    return bool(metadata.get("appearance_worn"))
