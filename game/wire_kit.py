"""Player wire-kit storage helpers."""

from __future__ import annotations

from collections.abc import Mapping

from game.components import Inventory, WireState
from game.items import ITEM_CATALOG, item_inventory_slot_cost
from game.wire_runtime import (
    is_wire_item,
    normalize_wire_entry_metadata,
    wire_entry_display_name,
    wire_entry_storage_points,
    wire_profile_for_item,
)


WIRE_KIT_TABS = ("kit", "pack", "programs", "data", "credentials", "backups", "corrupted")


def _clean_item_id(item_id):
    return str(item_id or "").strip().lower()


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _entry_copy(entry, *, item_catalog=None, storage_status=None):
    if not isinstance(entry, Mapping):
        return None
    item_id = _clean_item_id(entry.get("item_id"))
    if not item_id:
        return None
    metadata = normalize_wire_entry_metadata(
        entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {},
        item_id=item_id,
        profile=wire_profile_for_item(item_id, item_catalog=item_catalog or ITEM_CATALOG),
    )
    if storage_status:
        metadata["storage_status"] = str(storage_status)
    return {
        "instance_id": str(entry.get("instance_id", "") or ""),
        "item_id": item_id,
        "quantity": max(1, _int(entry.get("quantity"), 1)),
        "owner_eid": entry.get("owner_eid"),
        "owner_tag": entry.get("owner_tag"),
        "metadata": metadata,
    }


def wire_state_for_actor(sim, actor_eid, *, create=True):
    states = sim.ecs.get(WireState)
    state = states.get(actor_eid)
    if state is None and create:
        state = WireState()
        sim.ecs.add(actor_eid, state)
    return normalize_wire_state(state)


def normalize_wire_state(state):
    if state is None:
        return None
    if not hasattr(state, "schema_version"):
        state.schema_version = 1
    if not hasattr(state, "capacity_points"):
        state.capacity_points = 24
    if not hasattr(state, "program_slots"):
        state.program_slots = 2
    if not hasattr(state, "kit_entries"):
        state.kit_entries = []
    if not hasattr(state, "ram_slots"):
        state.ram_slots = []
    if not hasattr(state, "equipped_interface_instance_id"):
        state.equipped_interface_instance_id = None
    if not hasattr(state, "active_connection"):
        state.active_connection = None
    if not hasattr(state, "active_scene"):
        state.active_scene = None
    if not hasattr(state, "connection_status"):
        state.connection_status = "offline"
    if not hasattr(state, "last_wire_feedback"):
        state.last_wire_feedback = ""
    if not hasattr(state, "last_ejection_state"):
        state.last_ejection_state = None
    state.capacity_points = int(max(1, _int(getattr(state, "capacity_points", 24), 24)))
    state.program_slots = int(max(0, _int(getattr(state, "program_slots", 2), 2)))
    state.kit_entries = [
        clean
        for clean in (
            _entry_copy(entry, item_catalog=ITEM_CATALOG, storage_status="wire_kit")
            for entry in getattr(state, "kit_entries", ()) or ()
        )
        if clean is not None
    ]
    ram_slots = []
    for row in getattr(state, "ram_slots", ()) or ():
        if isinstance(row, Mapping):
            ram_slots.append(dict(row))
    state.ram_slots = ram_slots[: state.program_slots]
    state.active_scene = dict(state.active_scene) if isinstance(state.active_scene, Mapping) else None
    state.last_ejection_state = (
        dict(state.last_ejection_state)
        if isinstance(getattr(state, "last_ejection_state", None), Mapping)
        else None
    )
    return state


def _wire_ram_used_points(state, *, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    total = 0
    for entry in getattr(state, "ram_slots", ()) or ():
        if not isinstance(entry, Mapping):
            continue
        profile = wire_profile_for_item(entry.get("item_id"), item_catalog=item_catalog)
        total += max(1, _int(profile.get("ram_cost"), 1))
    return int(total)


def wire_kit_used_points(state, *, item_catalog=None):
    normalize_wire_state(state)
    return sum(
        wire_entry_storage_points(entry, item_catalog=item_catalog or ITEM_CATALOG)
        for entry in getattr(state, "kit_entries", ()) or ()
        if isinstance(entry, Mapping)
    )


def wire_kit_summary(state, *, item_catalog=None):
    normalize_wire_state(state)
    if state is None:
        return {
            "entries": 0,
            "points_used": 0,
            "capacity_points": 24,
            "program_slots": 2,
            "ram_used": 0,
        }
    return {
        "entries": len(getattr(state, "kit_entries", ()) or ()),
        "points_used": wire_kit_used_points(state, item_catalog=item_catalog),
        "capacity_points": int(getattr(state, "capacity_points", 24)),
        "program_slots": int(getattr(state, "program_slots", 2)),
        "ram_used": _wire_ram_used_points(state, item_catalog=item_catalog),
    }


def wire_kit_status_lines(state, *, item_catalog=None):
    summary = wire_kit_summary(state, item_catalog=item_catalog)
    connection = str(getattr(state, "connection_status", "offline") if state else "offline" or "offline")
    return [
        f"Storage {summary['points_used']}/{summary['capacity_points']} pts across {summary['entries']} entries",
        f"RAM {summary['ram_used']}/{summary['program_slots']} pts | connection {connection}",
        "Slice 4: RAM-loaded programs can execute inside a WireScene.",
    ]


def wire_kit_can_accept_entry(state, entry, *, item_catalog=None):
    normalize_wire_state(state)
    clean = _entry_copy(entry, item_catalog=item_catalog or ITEM_CATALOG, storage_status="wire_kit")
    if state is None or clean is None:
        return False, "invalid_entry"
    item_catalog = item_catalog or ITEM_CATALOG
    if not is_wire_item(clean.get("item_id"), item_catalog=item_catalog):
        return False, "not_wire_item"
    profile = wire_profile_for_item(clean.get("item_id"), item_catalog=item_catalog)
    if not bool(profile.get("loadable", True)):
        return False, "not_loadable"
    used = wire_kit_used_points(state, item_catalog=item_catalog)
    cost = wire_entry_storage_points(clean, item_catalog=item_catalog) * max(1, _int(clean.get("quantity"), 1))
    if used + cost > int(getattr(state, "capacity_points", 24)):
        return False, "wire_kit_full"
    return True, None


def wire_kit_find_entry(state, instance_id):
    normalize_wire_state(state)
    instance_id = str(instance_id or "").strip()
    if not state or not instance_id:
        return None
    for entry in tuple(getattr(state, "kit_entries", ()) or ()):
        if isinstance(entry, Mapping) and str(entry.get("instance_id", "") or "") == instance_id:
            return dict(entry)
    return None


def wire_kit_add_entry(state, entry, *, item_catalog=None):
    normalize_wire_state(state)
    clean = _entry_copy(entry, item_catalog=item_catalog or ITEM_CATALOG, storage_status="wire_kit")
    ok, reason = wire_kit_can_accept_entry(state, clean, item_catalog=item_catalog)
    if not ok:
        return {"ok": False, "reason": reason, "entry": clean}
    state.kit_entries.append(clean)
    return {
        "ok": True,
        "reason": None,
        "entry": dict(clean),
        "summary": wire_kit_summary(state, item_catalog=item_catalog),
    }


def wire_kit_remove_entry(state, instance_id):
    normalize_wire_state(state)
    instance_id = str(instance_id or "").strip()
    if state is None or not instance_id:
        return None
    entries = list(getattr(state, "kit_entries", ()) or ())
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            continue
        if str(entry.get("instance_id", "") or "") != instance_id:
            continue
        removed = dict(entries.pop(index))
        state.kit_entries = entries
        return removed
    return None


def load_inventory_entry_to_wire_kit(sim, actor_eid, instance_id, *, item_catalog=None):
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if inventory is None:
        return {"ok": False, "reason": "missing_inventory"}
    entry = inventory.find(instance_id=instance_id)
    if entry is None:
        return {"ok": False, "reason": "item_unavailable"}
    item_catalog = item_catalog or ITEM_CATALOG
    if not is_wire_item(entry.get("item_id"), item_catalog=item_catalog):
        return {"ok": False, "reason": "not_wire_item", "entry": dict(entry)}
    wire_state = wire_state_for_actor(sim, actor_eid, create=True)
    ok, reason = wire_kit_can_accept_entry(wire_state, entry, item_catalog=item_catalog)
    if not ok:
        return {"ok": False, "reason": reason, "entry": dict(entry)}
    removed = inventory.remove_item(instance_id=instance_id, quantity=max(1, _int(entry.get("quantity"), 1)))
    if not removed:
        return {"ok": False, "reason": "item_remove_failed"}
    result = wire_kit_add_entry(wire_state, removed, item_catalog=item_catalog)
    if not result.get("ok"):
        inventory.items.append(dict(removed))
        return {"ok": False, "reason": result.get("reason", "blocked"), "entry": dict(removed)}
    result.update({"entry": dict(result.get("entry") or removed)})
    return result


def unload_wire_kit_entry_to_inventory(sim, actor_eid, instance_id, *, item_catalog=None):
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    wire_state = wire_state_for_actor(sim, actor_eid, create=True)
    if inventory is None:
        return {"ok": False, "reason": "missing_inventory"}
    entry = wire_kit_find_entry(wire_state, instance_id)
    if entry is None:
        return {"ok": False, "reason": "wire_entry_unavailable"}
    item_catalog = item_catalog or ITEM_CATALOG
    normalized = _entry_copy(entry, item_catalog=item_catalog, storage_status="backpack")
    if item_inventory_slot_cost(normalized) > 0 and inventory.slot_count() + item_inventory_slot_cost(normalized) > inventory.capacity:
        return {"ok": False, "reason": "inventory_full", "entry": dict(entry)}
    removed = wire_kit_remove_entry(wire_state, instance_id)
    if removed is None:
        return {"ok": False, "reason": "wire_entry_remove_failed", "entry": dict(entry)}
    item_def = item_catalog.get(removed.get("item_id"), {})
    metadata = dict((normalized or removed).get("metadata") or {})
    metadata["storage_status"] = "backpack"
    added, iid = inventory.add_item(
        removed.get("item_id"),
        quantity=max(1, _int(removed.get("quantity"), 1)),
        stack_max=max(1, _int(item_def.get("stack_max"), 1)),
        instance_id=removed.get("instance_id"),
        instance_factory=getattr(sim, "new_item_instance_id", None),
        owner_eid=removed.get("owner_eid"),
        owner_tag=removed.get("owner_tag"),
        metadata=metadata,
    )
    if not added:
        wire_state.kit_entries.append(dict(removed))
        return {"ok": False, "reason": "inventory_full", "entry": dict(removed)}
    return {"ok": True, "reason": None, "entry": dict(removed), "instance_id": iid}


def _wire_kind_bucket(item_id, *, item_catalog=None):
    profile = wire_profile_for_item(item_id, item_catalog=item_catalog or ITEM_CATALOG)
    kind = str(profile.get("kind", "") or "").strip().lower()
    if kind == "data_packet":
        return "data"
    if kind in {"credential", "license"}:
        return "credentials"
    if kind == "backup":
        return "backups"
    if kind in {"trace", "corrupted_file"}:
        return "corrupted"
    if kind == "program":
        return "programs"
    return "kit"


def _row_label(entry, *, source, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    name = wire_entry_display_name(entry, item_catalog=item_catalog)
    profile = wire_profile_for_item(entry.get("item_id"), item_catalog=item_catalog)
    kind = str(profile.get("kind", "wire") or "wire").replace("_", " ")
    points = wire_entry_storage_points(entry, item_catalog=item_catalog)
    quality = str((entry.get("metadata") or {}).get("quality", "") or "").strip()
    suffix = f"{kind}, {points} pt"
    if quality:
        suffix += f", {quality}"
    if source == "pack":
        return f"{name} [{suffix}] -> load"
    return f"{name} [{suffix}] -> backpack"


def wire_kit_rows(sim, actor_eid, tab="kit", *, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    tab = str(tab or "kit").strip().lower() or "kit"
    if tab not in WIRE_KIT_TABS:
        tab = "kit"
    state = wire_state_for_actor(sim, actor_eid, create=True)
    rows = []
    if tab == "pack":
        inventory = sim.ecs.get(Inventory).get(actor_eid)
        for entry in tuple(getattr(inventory, "items", ()) or ()):
            if not isinstance(entry, Mapping):
                continue
            if not is_wire_item(entry.get("item_id"), item_catalog=item_catalog):
                continue
            rows.append({
                "kind": "pack",
                "instance_id": str(entry.get("instance_id", "") or ""),
                "entry": dict(entry),
                "label": _row_label(entry, source="pack", item_catalog=item_catalog),
                "action": "load",
            })
        return rows
    for entry in tuple(getattr(state, "kit_entries", ()) or ()):
        if not isinstance(entry, Mapping):
            continue
        if tab != "kit" and _wire_kind_bucket(entry.get("item_id"), item_catalog=item_catalog) != tab:
            continue
        rows.append({
            "kind": "kit",
            "instance_id": str(entry.get("instance_id", "") or ""),
            "entry": dict(entry),
            "label": _row_label(entry, source="kit", item_catalog=item_catalog),
            "action": "unload",
        })
    return rows
