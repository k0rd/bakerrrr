"""Player drone workshop storage helpers."""

from __future__ import annotations

from collections.abc import Mapping

from game.components import DroneWorkshopState, Inventory, Position
from game.drone_runtime import drone_profile_for_item
from game.items import ITEM_CATALOG, item_display_name


WORKSHOP_PART_KINDS = {"chassis", "power_center", "module"}
MODULE_STORAGE_POINTS = {
    "drone_camera_module": 1,
    "drone_radio_module": 1,
    "drone_remote_receiver_module": 1,
    "drone_light_module": 1,
    "drone_speaker_module": 1,
    "drone_alarm_probe_module": 1,
    "drone_mapping_procedure_module": 1,
    "drone_follow_procedure_module": 1,
    "drone_cargo_clamp_module": 2,
    "drone_ammo_rack_module": 2,
    "drone_fuel_tank_module": 2,
    "drone_armor_shell_module": 3,
    "drone_pistol_module": 3,
    "drone_flame_nozzle_module": 3,
}


def _clean_item_id(item_id):
    return str(item_id or "").strip().lower()


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _entry_copy(entry):
    if not isinstance(entry, Mapping):
        return None
    item_id = _clean_item_id(entry.get("item_id"))
    if not item_id:
        return None
    return {
        "instance_id": str(entry.get("instance_id", "") or ""),
        "item_id": item_id,
        "quantity": max(1, _int(entry.get("quantity"), 1)),
        "owner_eid": entry.get("owner_eid"),
        "owner_tag": entry.get("owner_tag"),
        "metadata": dict(entry.get("metadata") or {}),
    }


def drone_workshop_profile_kind(item_id, *, item_catalog=None):
    profile = drone_profile_for_item(item_id, item_catalog=item_catalog or ITEM_CATALOG)
    return str(profile.get("kind", "") or "").strip().lower()


def is_drone_workshop_part(item_id, *, item_catalog=None):
    return drone_workshop_profile_kind(item_id, item_catalog=item_catalog) in WORKSHOP_PART_KINDS


def drone_workshop_part_points(item_id, *, item_catalog=None):
    item_id = _clean_item_id(item_id)
    profile = drone_profile_for_item(item_id, item_catalog=item_catalog or ITEM_CATALOG)
    kind = str(profile.get("kind", "") or "").strip().lower()
    if kind == "chassis":
        return 0
    if kind == "power_center":
        return max(1, min(5, _int(profile.get("mark"), 1)))
    if kind == "module":
        return max(1, min(5, MODULE_STORAGE_POINTS.get(item_id, _int(profile.get("storage_points"), 1))))
    return 0


def drone_workshop_for_actor(sim, actor_eid, *, create=True, migrate_inventory=False, item_catalog=None):
    workshops = sim.ecs.get(DroneWorkshopState)
    workshop = workshops.get(actor_eid)
    if workshop is None and create:
        workshop = DroneWorkshopState()
        sim.ecs.add(actor_eid, workshop)
    if workshop is not None:
        normalize_drone_workshop(workshop)
        if migrate_inventory:
            migrate_inventory_drone_parts_to_workshop(sim, actor_eid, item_catalog=item_catalog)
    return workshop


def normalize_drone_workshop(workshop):
    if workshop is None:
        return None
    if not hasattr(workshop, "chassis_capacity"):
        workshop.chassis_capacity = 4
    if not hasattr(workshop, "parts_capacity_points"):
        workshop.parts_capacity_points = 60
    workshop.chassis_capacity = int(max(1, _int(getattr(workshop, "chassis_capacity", 4), 4)))
    workshop.parts_capacity_points = int(max(1, _int(getattr(workshop, "parts_capacity_points", 60), 60)))
    workshop.chassis_slots = [
        clean
        for clean in (_entry_copy(entry) for entry in getattr(workshop, "chassis_slots", ()) or ())
        if clean is not None
    ][: workshop.chassis_capacity]
    workshop.parts = [
        clean
        for clean in (_entry_copy(entry) for entry in getattr(workshop, "parts", ()) or ())
        if clean is not None
    ]
    return workshop


def drone_workshop_used_points(workshop, *, item_catalog=None):
    normalize_drone_workshop(workshop)
    return sum(
        drone_workshop_part_points(entry.get("item_id"), item_catalog=item_catalog)
        for entry in getattr(workshop, "parts", ()) or ()
        if isinstance(entry, Mapping)
    )


def drone_workshop_summary(workshop, *, item_catalog=None):
    normalize_drone_workshop(workshop)
    if workshop is None:
        return {
            "chassis_used": 0,
            "chassis_capacity": 4,
            "parts_used": 0,
            "parts_capacity": 60,
        }
    return {
        "chassis_used": len(getattr(workshop, "chassis_slots", ()) or ()),
        "chassis_capacity": int(getattr(workshop, "chassis_capacity", 4)),
        "parts_used": drone_workshop_used_points(workshop, item_catalog=item_catalog),
        "parts_capacity": int(getattr(workshop, "parts_capacity_points", 60)),
    }


def drone_workshop_entries(workshop, *, kind=None, item_catalog=None):
    normalize_drone_workshop(workshop)
    if workshop is None:
        return []
    target_kind = str(kind or "").strip().lower()
    entries = []
    for entry in tuple(getattr(workshop, "chassis_slots", ()) or ()):
        if not isinstance(entry, Mapping):
            continue
        if target_kind and target_kind != "chassis":
            continue
        entries.append(dict(entry))
    for entry in tuple(getattr(workshop, "parts", ()) or ()):
        if not isinstance(entry, Mapping):
            continue
        entry_kind = drone_workshop_profile_kind(entry.get("item_id"), item_catalog=item_catalog)
        if target_kind and entry_kind != target_kind:
            continue
        entries.append(dict(entry))
    return entries


def drone_workshop_find_entry(workshop, instance_id, *, item_catalog=None):
    del item_catalog
    normalize_drone_workshop(workshop)
    instance_id = str(instance_id or "").strip()
    if not workshop or not instance_id:
        return None
    for source in ("chassis_slots", "parts"):
        for entry in tuple(getattr(workshop, source, ()) or ()):
            if isinstance(entry, Mapping) and str(entry.get("instance_id", "") or "") == instance_id:
                return dict(entry)
    return None


def drone_workshop_can_accept_entry(workshop, entry, *, item_catalog=None):
    normalize_drone_workshop(workshop)
    clean = _entry_copy(entry)
    if workshop is None or clean is None:
        return False, "invalid_entry"
    kind = drone_workshop_profile_kind(clean.get("item_id"), item_catalog=item_catalog)
    if kind not in WORKSHOP_PART_KINDS:
        return False, "not_workshop_part"
    if kind == "chassis":
        if len(getattr(workshop, "chassis_slots", ()) or ()) >= int(getattr(workshop, "chassis_capacity", 4)):
            return False, "workshop_chassis_full"
        return True, None
    used = drone_workshop_used_points(workshop, item_catalog=item_catalog)
    cost = drone_workshop_part_points(clean.get("item_id"), item_catalog=item_catalog)
    if used + cost > int(getattr(workshop, "parts_capacity_points", 60)):
        return False, "workshop_parts_full"
    return True, None


def drone_workshop_add_entry(workshop, entry, *, item_catalog=None):
    normalize_drone_workshop(workshop)
    clean = _entry_copy(entry)
    ok, reason = drone_workshop_can_accept_entry(workshop, clean, item_catalog=item_catalog)
    if not ok:
        return {"ok": False, "reason": reason, "entry": clean}
    kind = drone_workshop_profile_kind(clean.get("item_id"), item_catalog=item_catalog)
    if kind == "chassis":
        workshop.chassis_slots.append(clean)
    else:
        workshop.parts.append(clean)
    return {
        "ok": True,
        "reason": None,
        "entry": dict(clean),
        "kind": kind,
        "points": drone_workshop_part_points(clean.get("item_id"), item_catalog=item_catalog),
        "summary": drone_workshop_summary(workshop, item_catalog=item_catalog),
    }


def drone_workshop_remove_entry(workshop, instance_id, *, item_catalog=None):
    normalize_drone_workshop(workshop)
    instance_id = str(instance_id or "").strip()
    if workshop is None or not instance_id:
        return None
    for source in ("chassis_slots", "parts"):
        entries = list(getattr(workshop, source, ()) or ())
        for index, entry in enumerate(entries):
            if not isinstance(entry, Mapping):
                continue
            if str(entry.get("instance_id", "") or "") != instance_id:
                continue
            removed = dict(entries.pop(index))
            setattr(workshop, source, entries)
            return removed
    return None


def migrate_inventory_drone_parts_to_workshop(sim, actor_eid, *, item_catalog=None):
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    workshop = drone_workshop_for_actor(sim, actor_eid, create=True, item_catalog=item_catalog)
    if inventory is None or workshop is None:
        return {"moved": 0, "blocked": 0, "blocked_reason": None}
    item_catalog = item_catalog or ITEM_CATALOG
    moved = 0
    blocked = 0
    blocked_reason = None
    for entry in list(getattr(inventory, "items", ()) or ()):
        if not isinstance(entry, Mapping):
            continue
        item_id = _clean_item_id(entry.get("item_id"))
        if not is_drone_workshop_part(item_id, item_catalog=item_catalog):
            continue
        ok, reason = drone_workshop_can_accept_entry(workshop, entry, item_catalog=item_catalog)
        if not ok:
            blocked += 1
            blocked_reason = blocked_reason or reason
            continue
        removed = inventory.remove_item(instance_id=entry.get("instance_id"), quantity=max(1, _int(entry.get("quantity"), 1)))
        if not removed:
            blocked += 1
            blocked_reason = blocked_reason or "remove_failed"
            continue
        result = drone_workshop_add_entry(workshop, removed, item_catalog=item_catalog)
        if result.get("ok"):
            moved += 1
        else:
            inventory.items.append(dict(removed))
            blocked += 1
            blocked_reason = blocked_reason or result.get("reason", "blocked")
    return {"moved": moved, "blocked": blocked, "blocked_reason": blocked_reason}


def move_inventory_part_to_workshop(sim, actor_eid, instance_id, *, item_catalog=None):
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if inventory is None:
        return {"ok": False, "reason": "missing_inventory"}
    entry = inventory.find(instance_id=instance_id)
    if entry is None:
        return {"ok": False, "reason": "item_unavailable"}
    item_catalog = item_catalog or ITEM_CATALOG
    if not is_drone_workshop_part(entry.get("item_id"), item_catalog=item_catalog):
        return {"ok": False, "reason": "not_workshop_part", "entry": dict(entry)}
    workshop = drone_workshop_for_actor(sim, actor_eid, create=True, item_catalog=item_catalog)
    ok, reason = drone_workshop_can_accept_entry(workshop, entry, item_catalog=item_catalog)
    if not ok:
        return {"ok": False, "reason": reason, "entry": dict(entry)}
    removed = inventory.remove_item(instance_id=instance_id, quantity=max(1, _int(entry.get("quantity"), 1)))
    if not removed:
        return {"ok": False, "reason": "item_remove_failed"}
    result = drone_workshop_add_entry(workshop, removed, item_catalog=item_catalog)
    if not result.get("ok"):
        inventory.items.append(dict(removed))
        return {"ok": False, "reason": result.get("reason", "blocked"), "entry": dict(removed)}
    result.update({"entry": dict(removed)})
    return result


def move_workshop_part_to_inventory(sim, actor_eid, instance_id, *, item_catalog=None):
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    workshop = drone_workshop_for_actor(sim, actor_eid, create=True, item_catalog=item_catalog)
    if inventory is None:
        return {"ok": False, "reason": "missing_inventory"}
    entry = drone_workshop_find_entry(workshop, instance_id, item_catalog=item_catalog)
    if entry is None:
        return {"ok": False, "reason": "workshop_part_unavailable"}
    item_def = (item_catalog or ITEM_CATALOG).get(entry.get("item_id"), {})
    added, iid = inventory.add_item(
        item_id=entry.get("item_id"),
        quantity=max(1, _int(entry.get("quantity"), 1)),
        stack_max=max(1, _int(item_def.get("stack_max"), 1)),
        instance_id=entry.get("instance_id"),
        instance_factory=getattr(sim, "new_item_instance_id", None),
        owner_eid=entry.get("owner_eid"),
        owner_tag=entry.get("owner_tag"),
        metadata=entry.get("metadata"),
    )
    if not added:
        return {"ok": False, "reason": "inventory_full", "entry": entry}
    removed = drone_workshop_remove_entry(workshop, instance_id, item_catalog=item_catalog)
    if removed is None:
        inventory.remove_item(instance_id=iid, quantity=max(1, _int(entry.get("quantity"), 1)))
        return {"ok": False, "reason": "workshop_remove_failed", "entry": entry}
    return {"ok": True, "reason": None, "entry": dict(removed), "instance_id": iid}


def drop_workshop_part(sim, actor_eid, instance_id, *, item_catalog=None):
    workshop = drone_workshop_for_actor(sim, actor_eid, create=True, item_catalog=item_catalog)
    entry = drone_workshop_find_entry(workshop, instance_id, item_catalog=item_catalog)
    if entry is None:
        return {"ok": False, "reason": "workshop_part_unavailable"}
    positions = sim.ecs.get(Position)
    pos = positions.get(actor_eid)
    if pos is None:
        return {"ok": False, "reason": "missing_position", "entry": entry}
    removed = drone_workshop_remove_entry(workshop, instance_id, item_catalog=item_catalog)
    if removed is None:
        return {"ok": False, "reason": "workshop_remove_failed", "entry": entry}
    metadata = dict(removed.get("metadata") or {})
    metadata.setdefault("last_transfer_kind", "drone_workshop_drop")
    metadata.setdefault("source_context", "drone_workshop_drop")
    ground_id = sim.register_ground_item(
        removed.get("item_id"),
        int(pos.x),
        int(pos.y),
        int(pos.z),
        quantity=max(1, _int(removed.get("quantity"), 1)),
        owner_eid=removed.get("owner_eid"),
        owner_tag=removed.get("owner_tag"),
        instance_id=removed.get("instance_id"),
        metadata=metadata,
    )
    return {"ok": True, "reason": None, "entry": dict(removed), "ground_item_id": ground_id}


def workshop_item_name(entry, *, item_catalog=None):
    if not isinstance(entry, Mapping):
        return "drone part"
    return item_display_name(entry.get("item_id"), metadata=entry.get("metadata"), item_catalog=item_catalog or ITEM_CATALOG)
