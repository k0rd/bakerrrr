"""Drone sheet helpers for physical management of deployed drones."""

from __future__ import annotations

from game.components import CreatureIdentity, DroneState, Inventory, Position, Render, Vitality
from game.drone_runtime import (
    PACKED_DRONE_ITEM_ID,
    deployed_drone_common_name,
    deployed_drone_render_spec,
    drone_loadout_summary,
    drone_profile_for_item,
    drone_state_controlled_by_actor,
    is_packed_drone_entry,
    normalize_packed_drone_metadata,
    packed_drone_metadata_from_state,
)
from game.drone_distribution import drone_paint_palette, normalize_drone_paint_word
from game.drone_programs import drone_program_sheet_rows
from game.drone_workshop import (
    drop_workshop_part,
    drone_workshop_add_entry,
    drone_workshop_can_accept_entry,
    drone_workshop_entries,
    drone_workshop_for_actor,
    drone_workshop_part_points,
    drone_workshop_remove_entry,
    drone_workshop_summary,
    move_workshop_part_to_inventory,
)
from game.items import item_display_name, item_inventory_slot_cost


DRONE_SHEET_TABS = ("status", "cargo", "battery", "parts", "modules", "procedures", "schematic")
DRONE_SHEET_VISIBLE_SLOTS = 4
DRONE_CARGO_SLOTS_PER_MODULE = 4
DRONE_PAINT_KEYS = drone_paint_palette()
WORKSHOP_BUILD_METADATA_KEY = "drone_build"


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _clean(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _item_name(item_id, item_catalog=None):
    catalog = item_catalog or {}
    item_def = catalog.get(str(item_id or "").strip().lower(), {}) if isinstance(catalog, dict) else {}
    return item_display_name(item_id, item_catalog=catalog) if item_def else _clean(item_id, "item")


def _deployed_state(sim, drone_eid):
    state = sim.ecs.get(DroneState).get(drone_eid)
    if state is None:
        return None
    if str(getattr(state, "mode", "") or "").strip().lower() != "deployed":
        return None
    return state


def _same_floor_adjacent(sim, actor_eid, drone_eid):
    positions = sim.ecs.get(Position)
    actor_pos = positions.get(actor_eid)
    drone_pos = positions.get(drone_eid)
    if actor_pos is None or drone_pos is None:
        return False
    if int(actor_pos.z) != int(drone_pos.z):
        return False
    return abs(int(actor_pos.x) - int(drone_pos.x)) + abs(int(actor_pos.y) - int(drone_pos.y)) <= 1


def _compatible(profile, chassis_class):
    compatible = profile.get("compatible_chassis")
    if not compatible:
        return True
    chassis = _clean(chassis_class).upper()
    return chassis in {_clean(item).upper() for item in compatible if _clean(item)}


def _sync_source_metadata(state):
    if state is None:
        return
    metadata = getattr(state, "source_metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
        state.source_metadata = metadata
    metadata["chassis_item_id"] = getattr(state, "chassis_item_id", None)
    metadata["chassis_class"] = getattr(state, "chassis_class", None)
    metadata["power_center_item_id"] = getattr(state, "power_center_item_id", None)
    metadata["hull_hp"] = int(max(0, _int(getattr(state, "hull_hp", 0), 0)))
    metadata["hull_hp_max"] = int(max(1, _int(getattr(state, "hull_hp_max", 1), 1)))
    metadata["range_limit"] = int(max(0, _int(getattr(state, "range_limit", 0), 0)))
    metadata["battery_item_id"] = getattr(state, "battery_item_id", None)
    metadata["battery_charge"] = int(max(0, _int(getattr(state, "battery_charge", 0), 0)))
    metadata["battery_charge_max"] = int(max(0, _int(getattr(state, "battery_charge_max", 0), 0)))
    metadata["cargo"] = [dict(entry) for entry in (getattr(state, "cargo", ()) or ()) if isinstance(entry, dict)]
    metadata["modules"] = [dict(entry) for entry in (getattr(state, "modules", ()) or ()) if isinstance(entry, dict)]
    paint = dict(getattr(state, "paint", {}) or {})
    secondary = _clean(paint.get("secondary_color") or paint.get("accent_color"), "blue")
    paint["secondary_color"] = secondary
    paint["accent_color"] = secondary
    metadata["paint"] = paint


def _module_visible_overlays(state, *, item_catalog=None):
    overlays = []
    for module in tuple(getattr(state, "modules", ()) or ()):
        if not isinstance(module, dict):
            continue
        profile = drone_profile_for_item(module.get("item_id"), item_catalog=item_catalog)
        overlay = profile.get("visible_overlay") if isinstance(profile, dict) else None
        if not isinstance(overlay, dict) or not overlay:
            continue
        module_kind = _clean(profile.get("module_kind"), "module")
        row = dict(overlay)
        row.setdefault("semantic_id", f"entity_drone_module_{module_kind}")
        overlays.append(row)
    return tuple(overlays)


def _sync_drone_runtime_shape(sim, drone_eid, state, *, item_catalog=None):
    """Refresh live components after a physical sheet edit."""

    if state is None:
        return {}
    metadata = packed_drone_metadata_from_state(state, item_catalog=item_catalog)
    summary = drone_loadout_summary(metadata, item_catalog=item_catalog)
    state.loadout_errors = tuple(summary.get("errors", ()) or ())
    state.chassis_class = str(summary.get("chassis_class") or getattr(state, "chassis_class", "") or "").strip().upper() or None
    chassis_profile = drone_profile_for_item(getattr(state, "chassis_item_id", None), item_catalog=item_catalog)
    if chassis_profile.get("kind") == "chassis":
        state.range_limit = int(max(0, _int(chassis_profile.get("base_range"), getattr(state, "range_limit", 0))))
        base_hp = int(max(1, _int(chassis_profile.get("base_hp"), getattr(state, "hull_hp_max", 1))))
        state.hull_hp_max = base_hp
        state.hull_hp = int(max(0, min(base_hp, _int(getattr(state, "hull_hp", base_hp), base_hp))))
    vitality = sim.ecs.get(Vitality).get(drone_eid)
    if vitality is not None:
        vitality.max_hp = int(max(1, getattr(state, "hull_hp_max", 1) or 1))
        vitality.hp = int(max(0, min(vitality.max_hp, getattr(state, "hull_hp", vitality.max_hp) or vitality.max_hp)))
        state.hull_hp = int(vitality.hp)
        state.hull_hp_max = int(vitality.max_hp)
    spec = deployed_drone_render_spec(metadata, item_catalog=item_catalog)
    render = sim.ecs.get(Render).get(drone_eid)
    if render is not None:
        render.set_appearance(
            glyph=spec.get("glyph", "d"),
            color=spec.get("color") or "item_restricted",
            color_word=spec.get("color_word"),
            semantic_id="entity_drone",
            overlays=_module_visible_overlays(state, item_catalog=item_catalog),
        )
    identity = sim.ecs.get(CreatureIdentity).get(drone_eid)
    if identity is not None:
        identity.common_name = deployed_drone_common_name(metadata, item_catalog=item_catalog)
    _sync_source_metadata(state)
    return summary


def _candidate_metadata(state, *, item_catalog=None, **updates):
    metadata = packed_drone_metadata_from_state(state, item_catalog=item_catalog)
    metadata.update(updates)
    return metadata


def _loadout_errors_for_candidate(state, *, item_catalog=None, **updates):
    summary = drone_loadout_summary(_candidate_metadata(state, item_catalog=item_catalog, **updates), item_catalog=item_catalog)
    return tuple(str(error) for error in summary.get("errors", ()) if str(error).strip()), summary


def _entry_to_module(entry):
    if not isinstance(entry, dict):
        return None
    item_id = str(entry.get("item_id", "") or "").strip().lower()
    if not item_id:
        return None
    module = {
        "item_id": item_id,
        "metadata": dict(entry.get("metadata") or {}),
    }
    instance_id = str(entry.get("instance_id", "") or "").strip()
    if instance_id:
        module["source_instance_id"] = instance_id
    return module


def _workshop_entry_ids(workshop, *, item_catalog=None):
    return {
        str(entry.get("instance_id", "") or "").strip()
        for entry in drone_workshop_entries(workshop, item_catalog=item_catalog)
        if isinstance(entry, dict) and str(entry.get("instance_id", "") or "").strip()
    }


def _inventory_entry_ids(inventory, *, except_instance_id=None):
    skipped = str(except_instance_id or "").strip()
    return {
        str(entry.get("instance_id", "") or "").strip()
        for entry in tuple(getattr(inventory, "items", ()) or ())
        if isinstance(entry, dict)
        and str(entry.get("instance_id", "") or "").strip()
        and str(entry.get("instance_id", "") or "").strip() != skipped
    }


def _fresh_instance_id(sim, prefix="drone-part"):
    factory = getattr(sim, "new_item_instance_id", None)
    if callable(factory):
        return str(factory())
    return f"{prefix}-{id(sim)}"


def _unique_instance_id(preferred, used, sim, *, prefix="drone-part"):
    candidate = str(preferred or "").strip()
    if candidate and candidate not in used:
        used.add(candidate)
        return candidate
    while True:
        candidate = _fresh_instance_id(sim, prefix=prefix)
        if candidate and candidate not in used:
            used.add(candidate)
            return candidate


def _module_to_inventory_entry(module, *, player_eid=None, instance_factory=None):
    if not isinstance(module, dict):
        return None
    item_id = str(module.get("item_id", "") or module.get("module_item_id", "") or "").strip().lower()
    if not item_id:
        return None
    instance_id = str(module.get("source_instance_id", "") or "").strip()
    if not instance_id:
        instance_id = instance_factory() if callable(instance_factory) else ""
    metadata = dict(module.get("metadata") or {})
    for key, value in module.items():
        if key in {"item_id", "module_item_id", "metadata", "source_instance_id"}:
            continue
        metadata.setdefault(key, value)
    metadata.setdefault("source_context", "drone_module_bay")
    return {
        "instance_id": instance_id,
        "item_id": item_id,
        "quantity": 1,
        "owner_eid": player_eid,
        "owner_tag": "player",
        "metadata": metadata,
    }


def _part_return_entry(item_id, *, player_eid=None, instance_factory=None, source_context="drone_schematic_swap"):
    item_id = str(item_id or "").strip().lower()
    if not item_id:
        return None
    return {
        "instance_id": instance_factory() if callable(instance_factory) else "",
        "item_id": item_id,
        "quantity": 1,
        "owner_eid": player_eid,
        "owner_tag": "player",
        "metadata": {"source_context": source_context},
    }


def _workbench_blocking_errors(errors):
    ignored = {"missing battery", "missing power center"}
    return tuple(
        str(error)
        for error in (errors or ())
        if str(error).strip() and str(error).strip().lower() not in ignored
    )


def _workbench_final_errors(errors):
    return tuple(str(error) for error in (errors or ()) if str(error).strip())


def _workshop_chassis_entry_ref(workshop, instance_id):
    instance_id = str(instance_id or "").strip()
    if not workshop or not instance_id:
        return None
    for entry in getattr(workshop, "chassis_slots", ()) or ():
        if isinstance(entry, dict) and str(entry.get("instance_id", "") or "") == instance_id:
            return entry
    return None


def _workshop_build_metadata_from_chassis_entry(entry, *, item_catalog=None):
    if not isinstance(entry, dict):
        return {}
    item_id = str(entry.get("item_id", "") or "").strip().lower()
    metadata = dict(entry.get("metadata") or {})
    raw_build = metadata.get(WORKSHOP_BUILD_METADATA_KEY)
    build = dict(raw_build) if isinstance(raw_build, dict) else {}
    power_entry = build.get("power_center_entry")
    if isinstance(power_entry, dict) and not str(build.get("power_center_item_id", "") or "").strip():
        build["power_center_item_id"] = str(power_entry.get("item_id", "") or "").strip().lower()
    build["chassis_item_id"] = item_id
    build.setdefault("modules", [])
    build.setdefault("cargo", [])
    build.setdefault("source_context", "drone_workshop_assembly")
    source_instance_id = str(entry.get("instance_id", "") or "").strip()
    if source_instance_id:
        build.setdefault("source_chassis_instance_id", source_instance_id)
        build.setdefault("source_item_instance_id", source_instance_id)
    normalized = normalize_packed_drone_metadata(build, item_catalog=item_catalog)
    if isinstance(power_entry, dict):
        normalized["power_center_entry"] = dict(power_entry)
    return normalized


def _set_workshop_chassis_build_metadata(sim, player_eid, chassis_instance_id, build_metadata, *, item_catalog=None):
    workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
    entry = _workshop_chassis_entry_ref(workshop, chassis_instance_id)
    if entry is None:
        return None
    metadata = dict(entry.get("metadata") or {})
    stored = dict(build_metadata or {})
    stored["chassis_item_id"] = str(entry.get("item_id", "") or "").strip().lower()
    metadata[WORKSHOP_BUILD_METADATA_KEY] = stored
    entry["metadata"] = metadata
    return dict(entry)


def drone_workshop_chassis_records(sim, player_eid, *, item_catalog=None):
    workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
    records = []
    for entry in tuple(drone_workshop_entries(workshop, kind="chassis", item_catalog=item_catalog)):
        metadata = _workshop_build_metadata_from_chassis_entry(entry, item_catalog=item_catalog)
        summary = drone_loadout_summary(metadata, item_catalog=item_catalog)
        state = DroneState.from_packed_metadata(
            metadata,
            source_item_id=str(entry.get("item_id", "") or "").strip().lower(),
            source_item_instance_id=str(entry.get("instance_id", "") or "").strip(),
            owner_eid=player_eid,
            owner_tag="player",
            controller_eid=player_eid,
            controller_tag="player",
            item_catalog=item_catalog,
        )
        state.mode = "workshop"
        state.source_metadata = metadata
        chassis_class = str(summary.get("chassis_class") or getattr(state, "chassis_class", "") or "").strip().upper()
        records.append({
            "eid": None,
            "workshop_chassis": True,
            "workshop_chassis_instance_id": str(entry.get("instance_id", "") or ""),
            "chassis_entry": dict(entry),
            "state": state,
            "position": None,
            "distance": 0,
            "accessible": True,
            "label": f"{chassis_class}-class chassis" if chassis_class else "workshop chassis",
            "summary": summary,
        })
    return sorted(records, key=lambda row: (str(row.get("label", "")), str(row.get("workshop_chassis_instance_id", ""))))


def _workshop_add_or_block(sim, player_eid, entry, *, item_catalog=None):
    workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
    return drone_workshop_add_entry(workshop, entry, item_catalog=item_catalog)


def _workshop_remove_entry(sim, player_eid, instance_id, *, item_catalog=None):
    workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
    return drone_workshop_remove_entry(workshop, instance_id, item_catalog=item_catalog)


def drone_sheet_label(state):
    chassis_class = _clean(getattr(state, "chassis_class", "")).upper()
    return f"{chassis_class}-class drone" if chassis_class else "deployed drone"


def drone_sheet_records(sim, controller_eid, *, item_catalog=None):
    positions = sim.ecs.get(Position)
    controller_pos = positions.get(controller_eid)
    if controller_pos is None:
        return []
    records = []
    for drone_eid, state in sim.ecs.get(DroneState).items():
        if str(getattr(state, "mode", "") or "").strip().lower() != "deployed":
            continue
        if not drone_state_controlled_by_actor(state, controller_eid):
            continue
        pos = positions.get(drone_eid)
        if pos is None or int(pos.z) != int(controller_pos.z):
            continue
        distance = abs(int(controller_pos.x) - int(pos.x)) + abs(int(controller_pos.y) - int(pos.y))
        metadata = packed_drone_metadata_from_state(state, item_catalog=item_catalog)
        summary = drone_loadout_summary(metadata, item_catalog=item_catalog)
        records.append({
            "eid": drone_eid,
            "state": state,
            "position": pos,
            "distance": int(distance),
            "accessible": int(distance) <= 1,
            "label": drone_sheet_label(state),
            "summary": summary,
        })
    return sorted(records, key=lambda row: (int(row.get("distance", 0)), int(row.get("eid", 0))))


def drone_sheet_record(sim, controller_eid, drone_eid, *, item_catalog=None):
    for record in drone_sheet_records(sim, controller_eid, item_catalog=item_catalog):
        if record.get("eid") == drone_eid:
            return record
    return None


def _module_profile(module, item_catalog=None):
    if not isinstance(module, dict):
        return {}
    return drone_profile_for_item(module.get("item_id"), item_catalog=item_catalog)


def cargo_module_count(state, *, item_catalog=None):
    count = 0
    for module in tuple(getattr(state, "modules", ()) or ()):
        profile = _module_profile(module, item_catalog=item_catalog)
        capabilities = {str(value or "").strip().lower() for value in profile.get("capabilities", ())}
        module_kind = str(profile.get("module_kind", "") or "").strip().lower()
        if "cargo" in capabilities or module_kind in {"cargo", "cargo_clamp"}:
            count += 1
    return count


def drone_cargo_capacity_slots(state, *, item_catalog=None):
    return int(cargo_module_count(state, item_catalog=item_catalog) * DRONE_CARGO_SLOTS_PER_MODULE)


def drone_cargo_slot_count(state):
    return sum(item_inventory_slot_cost(entry) for entry in tuple(getattr(state, "cargo", ()) or ()) if isinstance(entry, dict))


def _entry_label(entry, *, item_catalog=None):
    if not isinstance(entry, dict):
        return "(bad entry)"
    item_id = str(entry.get("item_id", "") or "").strip().lower()
    quantity = max(1, _int(entry.get("quantity"), 1))
    name = _item_name(item_id, item_catalog=item_catalog)
    suffix = f" x{quantity}" if quantity != 1 else ""
    return f"{name}{suffix}"


def drone_sheet_status_lines(record, *, item_catalog=None):
    state = record.get("state") if isinstance(record, dict) else None
    pos = record.get("position") if isinstance(record, dict) else None
    summary = record.get("summary", {}) if isinstance(record, dict) else {}
    if state is None:
        return ["No drone selected."]
    if bool(record.get("workshop_chassis")):
        capabilities = ", ".join(summary.get("capabilities", ()) or ()) or "none"
        errors = "; ".join(summary.get("errors", ()) or ())
        modules = [entry for entry in tuple(getattr(state, "modules", ()) or ()) if isinstance(entry, dict)]
        lines = [
            f"Workbench: {record.get('label', 'workshop chassis')} | source {record.get('workshop_chassis_instance_id', '-')}",
            f"Core: {_item_name(getattr(state, 'power_center_item_id', None), item_catalog=item_catalog)} | Battery: choose from Battery tab to pack",
            f"Hull: {getattr(state, 'hull_hp', 0)}/{getattr(state, 'hull_hp_max', 0)} | Modules installed: {len(modules)}",
            f"Slots: {summary.get('slot_used', 0)}/{summary.get('slot_limit', 0)} | Weight: {summary.get('weight_used', 0)}/{summary.get('weight_limit', 0)} | Power: idle {summary.get('standby_draw', 0)}/{summary.get('power_output', 0)} active {summary.get('active_draw', 0)}/{summary.get('power_output', 0)}",
            f"Capabilities: {capabilities}",
            "Install modules from the workshop side; install a power core from Schematic; pack with a backpack battery.",
        ]
        if errors:
            lines.append(f"Not ready: {errors}")
        return lines
    capabilities = ", ".join(summary.get("capabilities", ()) or ()) or "none"
    errors = "; ".join(summary.get("errors", ()) or ())
    cargo_used = drone_cargo_slot_count(state)
    cargo_cap = drone_cargo_capacity_slots(state, item_catalog=item_catalog)
    lines = [
        f"{drone_sheet_label(state)} #{record.get('eid')} | dist {record.get('distance', 0)} | {'adjacent' if record.get('accessible') else 'remote view'}",
        f"Position: ({getattr(pos, 'x', '?')},{getattr(pos, 'y', '?')},{getattr(pos, 'z', '?')}) | range {getattr(state, 'range_limit', 0)}",
        f"Hull: {getattr(state, 'hull_hp', 0)}/{getattr(state, 'hull_hp_max', 0)} | Battery: {getattr(state, 'battery_charge', 0)}/{getattr(state, 'battery_charge_max', 0)}",
        f"Slots: {summary.get('slot_used', 0)}/{summary.get('slot_limit', 0)} | Weight: {summary.get('weight_used', 0)}/{summary.get('weight_limit', 0)} | Power: idle {summary.get('standby_draw', 0)}/{summary.get('power_output', 0)} active {summary.get('active_draw', 0)}/{summary.get('power_output', 0)}",
        f"Cargo: {cargo_used}/{cargo_cap} slots | Capabilities: {capabilities}",
        f"Intent: {getattr(state, 'procedure_key', None) or 'none'} | Last: {getattr(state, 'last_command', None) or 'none'}",
    ]
    if errors:
        lines.append(f"Loadout errors: {errors}")
    return lines


def _candidate_error_suffix(errors):
    errors = tuple(str(error) for error in (errors or ()) if str(error).strip())
    return f" | blocks: {'; '.join(errors)}" if errors else ""


def drone_sheet_parts_rows(sim, player_eid, *, item_catalog=None):
    workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
    summary = drone_workshop_summary(workshop, item_catalog=item_catalog)
    rows = [{
        "id": "workshop-summary",
        "label": (
            f"Workshop: chassis {summary.get('chassis_used', 0)}/{summary.get('chassis_capacity', 0)} | "
            f"loose parts {summary.get('parts_used', 0)}/{summary.get('parts_capacity', 0)} pts"
        ),
        "actionable": False,
    }]
    entries = drone_workshop_entries(workshop, item_catalog=item_catalog)
    for entry in entries:
        item_id = str(entry.get("item_id", "") or "").strip().lower()
        kind = drone_profile_for_item(item_id, item_catalog=item_catalog).get("kind", "part")
        points = drone_workshop_part_points(item_id, item_catalog=item_catalog)
        points_text = "slot" if kind == "chassis" else f"{points} pt"
        rows.append({
            "id": str(entry.get("instance_id", "") or item_id),
            "instance_id": str(entry.get("instance_id", "") or ""),
            "label": (
                f"{_item_name(item_id, item_catalog=item_catalog)} | {kind.replace('_', ' ')} | {points_text} | "
                f"{'Enter workbench, U backpack' if kind == 'chassis' else 'U backpack'} | R drop"
            ),
            "entry": dict(entry),
            "action": "workshop_part",
            "actionable": True,
        })
    packed_rows = backpack_packed_drone_entries(sim, player_eid, item_catalog=item_catalog)
    if packed_rows:
        rows.append({"id": "section:packed_drones", "label": "Backpack packed drones", "actionable": False})
        for entry in packed_rows:
            metadata = dict(entry.get("metadata") or {})
            summary = drone_loadout_summary(metadata, item_catalog=item_catalog)
            chassis = str(summary.get("chassis_class") or metadata.get("chassis_class") or "?").strip().upper() or "?"
            battery = _item_name(metadata.get("battery_item_id"), item_catalog=item_catalog)
            rows.append({
                "id": f"packed:{entry.get('instance_id', '')}",
                "instance_id": str(entry.get("instance_id", "") or ""),
                "label": (
                    f"Unpack {item_display_name(PACKED_DRONE_ITEM_ID, metadata=metadata, item_catalog=item_catalog)} | "
                    f"{chassis}-class | battery returns as {battery} | Enter workshop"
                ),
                "entry": dict(entry),
                "action": "unpack_packed_drone",
                "actionable": True,
            })
    if len(rows) == 1:
        rows.append({"id": "empty", "label": "(workshop empty)", "actionable": False})
    return rows


def backpack_packed_drone_entries(sim, player_eid, *, item_catalog=None):
    inventory = sim.ecs.get(Inventory).get(player_eid)
    entries = []
    for entry in tuple(getattr(inventory, "items", ()) or ()):
        if isinstance(entry, dict) and is_packed_drone_entry(entry, item_catalog=item_catalog):
            entries.append(dict(entry))
    return entries


def has_backpack_packed_drone(sim, player_eid, *, item_catalog=None):
    return bool(backpack_packed_drone_entries(sim, player_eid, item_catalog=item_catalog))


def _packed_drone_unpacked_chassis_build(metadata, *, item_catalog=None):
    build = dict(metadata or {})
    build["source_context"] = "drone_workshop_unpack"
    build["modules"] = []
    build.pop("power_center_entry", None)
    build.pop("power_center_item_id", None)
    build.pop("battery_item_id", None)
    build.pop("battery_charge", None)
    build.pop("battery_charge_max", None)
    build.pop("source_battery_instance_id", None)
    return normalize_packed_drone_metadata(build, item_catalog=item_catalog)


def unpack_packed_drone_to_workshop(sim, player_eid, packed_instance_id, *, item_catalog=None):
    item_catalog = item_catalog or {}
    inventory = sim.ecs.get(Inventory).get(player_eid)
    if inventory is None:
        return {"ok": False, "reason": "missing_inventory"}
    packed_instance_id = str(packed_instance_id or "").strip()
    packed_entry = inventory.find(instance_id=packed_instance_id)
    if packed_entry is None or not is_packed_drone_entry(packed_entry, item_catalog=item_catalog):
        return {"ok": False, "reason": "packed_drone_unavailable"}

    metadata = normalize_packed_drone_metadata(packed_entry.get("metadata"), item_catalog=item_catalog)
    summary = drone_loadout_summary(metadata, item_catalog=item_catalog)
    chassis_item_id = str(metadata.get("chassis_item_id", "") or "").strip().lower()
    chassis_profile = drone_profile_for_item(chassis_item_id, item_catalog=item_catalog)
    if chassis_profile.get("kind") != "chassis":
        return {"ok": False, "reason": "invalid_loadout", "errors": ("missing chassis",), "summary": summary}

    workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
    workshop_ids = _workshop_entry_ids(workshop, item_catalog=item_catalog)
    if packed_instance_id in workshop_ids:
        return {"ok": False, "reason": "instance_id_conflict", "summary": summary}
    used_workshop_ids = set(workshop_ids)
    used_workshop_ids.add(packed_instance_id)

    build = _packed_drone_unpacked_chassis_build(metadata, item_catalog=item_catalog)
    chassis_entry = {
        "instance_id": packed_instance_id,
        "item_id": chassis_item_id,
        "quantity": 1,
        "owner_eid": player_eid,
        "owner_tag": "player",
        "metadata": {
            "source_context": "drone_workshop_unpack",
            "source_packed_instance_id": packed_instance_id,
            WORKSHOP_BUILD_METADATA_KEY: build,
        },
    }
    workshop_entries = [chassis_entry]

    power_center_item_id = str(metadata.get("power_center_item_id", "") or "").strip().lower()
    if power_center_item_id:
        power_profile = drone_profile_for_item(power_center_item_id, item_catalog=item_catalog)
        if power_profile.get("kind") != "power_center":
            return {"ok": False, "reason": "invalid_loadout", "errors": (f"{power_center_item_id} is not a power center",), "summary": summary}
        power_source = metadata.get("power_center_entry") if isinstance(metadata.get("power_center_entry"), dict) else {}
        power_metadata = dict(power_source.get("metadata") or {})
        previous_context = power_metadata.get("source_context")
        if previous_context and previous_context != "drone_workshop_unpack":
            power_metadata.setdefault("original_source_context", previous_context)
        power_metadata["source_context"] = "drone_workshop_unpack"
        power_metadata.setdefault("source_packed_instance_id", packed_instance_id)
        power_entry = {
            "instance_id": _unique_instance_id(
                power_source.get("instance_id") or metadata.get("source_power_center_instance_id"),
                used_workshop_ids,
                sim,
                prefix="drone-core",
            ),
            "item_id": power_center_item_id,
            "quantity": 1,
            "owner_eid": player_eid,
            "owner_tag": "player",
            "metadata": power_metadata,
        }
        workshop_entries.append(power_entry)

    for module in tuple(metadata.get("modules", ()) or ()):
        if not isinstance(module, dict):
            continue
        module_item_id = str(module.get("item_id", "") or module.get("module_item_id", "") or "").strip().lower()
        module_profile = drone_profile_for_item(module_item_id, item_catalog=item_catalog)
        if module_profile.get("kind") != "module":
            return {"ok": False, "reason": "invalid_loadout", "errors": (f"{module_item_id} is not a drone module",), "summary": summary}
        module_entry = _module_to_inventory_entry(
            module,
            player_eid=player_eid,
            instance_factory=lambda: _unique_instance_id(None, used_workshop_ids, sim, prefix="drone-module"),
        )
        if module_entry is None:
            return {"ok": False, "reason": "invalid_loadout", "errors": ("bad module entry",), "summary": summary}
        module_entry["instance_id"] = _unique_instance_id(
            module_entry.get("instance_id"),
            used_workshop_ids,
            sim,
            prefix="drone-module",
        )
        module_entry.setdefault("metadata", {})
        previous_context = module_entry["metadata"].get("source_context")
        if previous_context and previous_context != "drone_workshop_unpack":
            module_entry["metadata"].setdefault("original_source_context", previous_context)
        module_entry["metadata"]["source_context"] = "drone_workshop_unpack"
        module_entry["metadata"].setdefault("source_packed_instance_id", packed_instance_id)
        workshop_entries.append(module_entry)

    shadow_chassis_used = len(getattr(workshop, "chassis_slots", ()) or ())
    shadow_parts_used = drone_workshop_summary(workshop, item_catalog=item_catalog).get("parts_used", 0)
    chassis_capacity = int(getattr(workshop, "chassis_capacity", 4))
    parts_capacity = int(getattr(workshop, "parts_capacity_points", 60))
    for entry in workshop_entries:
        kind = drone_profile_for_item(entry.get("item_id"), item_catalog=item_catalog).get("kind")
        if kind == "chassis":
            if shadow_chassis_used + 1 > chassis_capacity:
                return {"ok": False, "reason": "workshop_chassis_full", "entry": entry, "summary": summary}
            shadow_chassis_used += 1
        elif kind in {"power_center", "module"}:
            cost = drone_workshop_part_points(entry.get("item_id"), item_catalog=item_catalog)
            if shadow_parts_used + cost > parts_capacity:
                return {"ok": False, "reason": "workshop_parts_full", "entry": entry, "summary": summary}
            shadow_parts_used += cost
        else:
            return {"ok": False, "reason": "not_workshop_part", "entry": entry, "summary": summary}

    battery_entry = None
    battery_item_id = str(metadata.get("battery_item_id", "") or "").strip().lower()
    if battery_item_id:
        battery_profile = drone_profile_for_item(battery_item_id, item_catalog=item_catalog)
        if battery_profile.get("kind") != "battery":
            return {"ok": False, "reason": "invalid_loadout", "errors": (f"{battery_item_id} is not a battery",), "summary": summary}
        inventory_ids = _inventory_entry_ids(inventory, except_instance_id=packed_instance_id) | set(used_workshop_ids)
        battery_metadata = {
            "battery_charge": int(max(0, _int(metadata.get("battery_charge"), 0))),
            "battery_charge_max": int(max(0, _int(metadata.get("battery_charge_max"), 0))),
            "source_context": "drone_workshop_unpack",
            "source_packed_instance_id": packed_instance_id,
        }
        battery_entry = {
            "instance_id": _unique_instance_id(
                metadata.get("source_battery_instance_id"),
                inventory_ids,
                sim,
                prefix="drone-battery",
            ),
            "item_id": battery_item_id,
            "quantity": 1,
            "owner_eid": player_eid,
            "owner_tag": "player",
            "metadata": battery_metadata,
        }
        projected_slots = (
            int(inventory.slot_count())
            - int(item_inventory_slot_cost(packed_entry))
            + int(item_inventory_slot_cost(battery_entry))
        )
        if projected_slots > int(inventory.capacity):
            return {"ok": False, "reason": "inventory_full", "entry": battery_entry, "summary": summary}

    removed_packed = inventory.remove_item(instance_id=packed_instance_id, quantity=1)
    if removed_packed is None:
        return {"ok": False, "reason": "packed_remove_failed", "summary": summary}

    added_workshop_ids = []
    added_battery_instance_id = None
    try:
        for entry in workshop_entries:
            result = drone_workshop_add_entry(workshop, entry, item_catalog=item_catalog)
            if not result.get("ok"):
                raise RuntimeError(str(result.get("reason", "workshop_add_failed")))
            added_workshop_ids.append(str(entry.get("instance_id", "") or ""))
        if battery_entry is not None:
            item_def = item_catalog.get(battery_entry.get("item_id"), {}) if isinstance(item_catalog, dict) else {}
            added, added_battery_instance_id = inventory.add_item(
                battery_entry.get("item_id"),
                quantity=1,
                stack_max=max(1, _int(item_def.get("stack_max"), 1)),
                instance_id=battery_entry.get("instance_id"),
                instance_factory=getattr(sim, "new_item_instance_id", None),
                owner_eid=player_eid,
                owner_tag="player",
                metadata=battery_entry.get("metadata"),
            )
            if not added:
                raise RuntimeError("inventory_full")
            battery_entry["instance_id"] = added_battery_instance_id
            found_battery = inventory.find(instance_id=added_battery_instance_id)
            if isinstance(found_battery, dict):
                battery_entry = dict(found_battery)
    except RuntimeError as exc:
        for instance_id in reversed(added_workshop_ids):
            drone_workshop_remove_entry(workshop, instance_id, item_catalog=item_catalog)
        if added_battery_instance_id:
            inventory.remove_item(instance_id=added_battery_instance_id, quantity=1)
        _append_exact_inventory_entry(inventory, removed_packed)
        return {"ok": False, "reason": str(exc) or "unpack_failed", "entry": dict(removed_packed), "summary": summary}

    return {
        "ok": True,
        "reason": None,
        "action": "unpack_packed_drone",
        "entry": dict(removed_packed),
        "chassis_entry": dict(chassis_entry),
        "workshop_entries": [dict(entry) for entry in workshop_entries],
        "battery_entry": dict(battery_entry) if isinstance(battery_entry, dict) else None,
        "summary": summary,
        "instance_id": packed_instance_id,
        "parts_added": max(0, len(workshop_entries) - 1),
    }


def move_drone_workshop_part_to_pack(sim, player_eid, instance_id, *, item_catalog=None):
    return move_workshop_part_to_inventory(sim, player_eid, instance_id, item_catalog=item_catalog)


def drop_drone_workshop_part(sim, player_eid, instance_id, *, item_catalog=None):
    return drop_workshop_part(sim, player_eid, instance_id, item_catalog=item_catalog)


def drone_sheet_module_rows(sim, player_eid, record, *, side="drone", item_catalog=None):
    summary = record.get("summary", {}) if isinstance(record, dict) else {}
    state = record.get("state") if isinstance(record, dict) else None
    is_workbench = bool(record.get("workshop_chassis")) if isinstance(record, dict) else False
    rows = []
    budget = (
        f"Budget: slots {summary.get('slot_used', 0)}/{summary.get('slot_limit', 0)} | "
        f"weight {summary.get('weight_used', 0)}/{summary.get('weight_limit', 0)} | "
        f"power idle {summary.get('standby_draw', 0)}/{summary.get('power_output', 0)} "
        f"active {summary.get('active_draw', 0)}/{summary.get('power_output', 0)}"
    )
    rows.append({"id": "budget", "label": budget, "actionable": False})
    side = str(side or "drone").strip().lower()
    if side in {"pack", "bay", "workshop"}:
        workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
        for entry in tuple(drone_workshop_entries(workshop, kind="module", item_catalog=item_catalog)):
            if not isinstance(entry, dict):
                continue
            item_id = str(entry.get("item_id", "") or "").strip().lower()
            profile = drone_profile_for_item(item_id, item_catalog=item_catalog)
            if profile.get("kind") != "module":
                continue
            candidate_modules = list(getattr(state, "modules", ()) or ()) + [_entry_to_module(entry)]
            errors, _summary = _loadout_errors_for_candidate(state, item_catalog=item_catalog, modules=candidate_modules)
            display_errors = _workbench_blocking_errors(errors) if is_workbench else errors
            capabilities = ",".join(profile.get("capabilities", ()) or ()) or "none"
            label = (
                f"Install {_item_name(item_id, item_catalog=item_catalog)} | kind {profile.get('module_kind', '?')} | "
                f"slots {profile.get('slot_cost', 0)} weight {profile.get('weight', 0)} | caps {capabilities}"
                f"{_candidate_error_suffix(display_errors)}"
            )
            rows.append({
                "id": str(entry.get("instance_id", "") or ""),
                "instance_id": str(entry.get("instance_id", "") or ""),
                "label": label,
                "entry": dict(entry),
                "action": "install_module",
                "actionable": True,
            })
        if len(rows) == 1:
            rows.append({"id": "empty", "label": "(no spare drone modules)", "actionable": False})
        return rows

    for index, module in enumerate(tuple(getattr(state, "modules", ()) or ())):
        if not isinstance(module, dict):
            continue
        item_id = str(module.get("item_id", "") or "").strip().lower()
        profile = drone_profile_for_item(item_id, item_catalog=item_catalog)
        capabilities = ",".join(profile.get("capabilities", ()) or ()) or "none"
        label = (
            f"Remove {_item_name(item_id, item_catalog=item_catalog)} | kind {profile.get('module_kind', '?')} | "
            f"slots {profile.get('slot_cost', 0)} weight {profile.get('weight', 0)} | "
            f"draw {profile.get('standby_draw', 0)}/{profile.get('active_draw', 0)} | caps {capabilities}"
        )
        rows.append({
            "id": f"module:{index}",
            "module_index": int(index),
            "label": label,
            "entry": dict(module),
            "action": "remove_module",
            "actionable": True,
        })
    if len(rows) == 1:
        rows.append({"id": "empty", "label": "(no modules installed)", "actionable": False})
    return rows


def drone_sheet_schematic_rows(sim, player_eid, state, *, item_catalog=None):
    is_workbench = str(getattr(state, "mode", "") or "").strip().lower() == "workshop"
    rows = []
    paint = dict(getattr(state, "paint", {}) or {})
    rows.append({
        "id": "current",
        "label": (
            f"Current: {_item_name(getattr(state, 'chassis_item_id', None), item_catalog=item_catalog)} | "
            f"{_item_name(getattr(state, 'power_center_item_id', None), item_catalog=item_catalog)} | "
            f"paint {paint.get('primary_color', 'steel')}/{paint.get('secondary_color') or paint.get('accent_color', 'blue')}"
        ),
        "actionable": False,
    })
    workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
    power_rows = []
    chassis_rows = []
    for entry in tuple(drone_workshop_entries(workshop, item_catalog=item_catalog)):
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("item_id", "") or "").strip().lower()
        profile = drone_profile_for_item(item_id, item_catalog=item_catalog)
        kind = profile.get("kind")
        if kind == "chassis" and not is_workbench:
            errors, _summary = _loadout_errors_for_candidate(state, item_catalog=item_catalog, chassis_item_id=item_id)
            chassis_rows.append({
                "id": str(entry.get("instance_id", "") or ""),
                "instance_id": str(entry.get("instance_id", "") or ""),
                "label": f"Swap chassis: {_item_name(item_id, item_catalog=item_catalog)}{_candidate_error_suffix(errors)}",
                "entry": dict(entry),
                "action": "swap_chassis",
                "actionable": True,
            })
        elif kind == "power_center":
            errors, _summary = _loadout_errors_for_candidate(state, item_catalog=item_catalog, power_center_item_id=item_id)
            display_errors = _workbench_blocking_errors(errors) if is_workbench else errors
            power_rows.append({
                "id": str(entry.get("instance_id", "") or ""),
                "instance_id": str(entry.get("instance_id", "") or ""),
                "label": f"{'Install' if is_workbench and not getattr(state, 'power_center_item_id', None) else 'Swap'} power core: {_item_name(item_id, item_catalog=item_catalog)}{_candidate_error_suffix(display_errors)}",
                "entry": dict(entry),
                "action": "swap_power_center",
                "actionable": True,
            })
    if power_rows:
        rows.append({"id": "section:power_core", "label": "Power cores", "actionable": False})
        rows.extend(power_rows)
    elif is_workbench and not getattr(state, "power_center_item_id", None):
        rows.append({"id": "section:power_core_empty", "label": "Power cores: none in workshop", "actionable": False})
    if chassis_rows:
        rows.append({"id": "section:chassis", "label": "Chassis", "actionable": False})
        rows.extend(chassis_rows)
    rows.append({"id": "section:paint", "label": "Paint", "actionable": False})
    for target in ("primary_color", "secondary_color"):
        current = str((paint.get(target) or (paint.get("accent_color") if target == "secondary_color" else "")) or "").strip().lower()
        paint_keys = tuple(drone_paint_palette())
        for color_key in paint_keys:
            if color_key == current:
                continue
            label_target = "primary" if target == "primary_color" else "secondary"
            rows.append({
                "id": f"paint:{target}:{color_key}",
                "label": f"Set {label_target} paint: {color_key}",
                "action": "paint",
                "paint_key": target,
                "paint_color": color_key,
                "actionable": True,
            })
    return rows


def drone_sheet_cargo_rows(sim, player_eid, state, *, side="pack", item_catalog=None):
    if str(getattr(state, "mode", "") or "").strip().lower() == "workshop":
        return [{"id": "workbench-cargo", "label": "Workbench chassis cannot carry cargo until it is packed and deployed.", "actionable": False}]
    side = str(side or "pack").strip().lower()
    rows = []
    if side == "drone":
        for entry in tuple(getattr(state, "cargo", ()) or ()):
            if not isinstance(entry, dict):
                continue
            rows.append({
                "id": str(entry.get("instance_id", "") or entry.get("item_id", "") or ""),
                "instance_id": str(entry.get("instance_id", "") or ""),
                "label": _entry_label(entry, item_catalog=item_catalog),
                "entry": dict(entry),
                "action": "to_pack",
                "actionable": True,
            })
        return rows or [{"id": "empty", "label": "(drone cargo empty)", "actionable": False}]

    inventory = sim.ecs.get(Inventory).get(player_eid)
    for entry in tuple(getattr(inventory, "items", ()) or ()):
        if not isinstance(entry, dict):
            continue
        rows.append({
            "id": str(entry.get("instance_id", "") or ""),
            "instance_id": str(entry.get("instance_id", "") or ""),
            "label": _entry_label(entry, item_catalog=item_catalog),
            "entry": dict(entry),
            "action": "to_drone",
            "actionable": True,
        })
    return rows or [{"id": "empty", "label": "(pack empty)", "actionable": False}]


def drone_sheet_battery_rows(sim, player_eid, state, *, item_catalog=None):
    inventory = sim.ecs.get(Inventory).get(player_eid)
    rows = []
    chassis_class = getattr(state, "chassis_class", None)
    for entry in tuple(getattr(inventory, "items", ()) or ()):
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("item_id", "") or "").strip().lower()
        profile = drone_profile_for_item(item_id, item_catalog=item_catalog)
        if profile.get("kind") != "battery":
            continue
        compatible = _compatible(profile, chassis_class)
        metadata = dict(entry.get("metadata") or {})
        charge_max = _int(profile.get("charge_max"), 0)
        charge = _int(metadata.get("battery_charge"), charge_max)
        charge = max(0, min(charge, charge_max)) if charge_max > 0 else max(0, charge)
        label = f"{_item_name(item_id, item_catalog=item_catalog)} | charge {charge}/{charge_max}"
        if str(getattr(state, "mode", "") or "").strip().lower() == "workshop":
            candidate = packed_drone_metadata_from_state(state, item_catalog=item_catalog)
            candidate["battery_item_id"] = item_id
            candidate["battery_charge"] = charge
            candidate["battery_charge_max"] = charge_max
            errors = _workbench_final_errors(drone_loadout_summary(candidate, item_catalog=item_catalog).get("errors", ()))
            label = f"Pack with {label}"
            if errors:
                label += f" | blocks: {'; '.join(errors)}"
            compatible = compatible and not errors
        if not compatible:
            label += f" | incompatible with {chassis_class or '?'}"
        rows.append({
            "id": str(entry.get("instance_id", "") or ""),
            "instance_id": str(entry.get("instance_id", "") or ""),
            "label": label,
            "entry": dict(entry),
            "compatible": bool(compatible),
            "actionable": bool(compatible),
        })
    return rows or [{"id": "empty", "label": "(no spare drone batteries)", "actionable": False}]


def drone_sheet_tab_rows(sim, player_eid, record, *, tab="status", cargo_side="pack", module_side="drone", item_catalog=None, procedure_editor=None):
    tab = str(tab or "status").strip().lower()
    if tab not in DRONE_SHEET_TABS:
        tab = "status"
    if tab == "parts":
        return drone_sheet_parts_rows(sim, player_eid, item_catalog=item_catalog)
    state = record.get("state") if isinstance(record, dict) else None
    if state is None:
        return [{"id": "empty", "label": "No drone selected.", "actionable": False}]
    if tab == "cargo":
        return drone_sheet_cargo_rows(sim, player_eid, state, side=cargo_side, item_catalog=item_catalog)
    if tab == "battery":
        return drone_sheet_battery_rows(sim, player_eid, state, item_catalog=item_catalog)
    if tab == "modules":
        return drone_sheet_module_rows(sim, player_eid, record, side=module_side, item_catalog=item_catalog)
    if tab == "procedures":
        return drone_program_sheet_rows(sim, player_eid, record, item_catalog=item_catalog, editor_state=procedure_editor)
    if tab == "schematic":
        return drone_sheet_schematic_rows(sim, player_eid, state, item_catalog=item_catalog)
    return [{"id": f"status:{idx}", "label": line, "actionable": False} for idx, line in enumerate(drone_sheet_status_lines(record, item_catalog=item_catalog))]


def _inventory_can_accept_exact_entry(inventory, entry):
    if inventory is None or not isinstance(entry, dict):
        return False
    return int(inventory.slot_count()) + int(item_inventory_slot_cost(entry)) <= int(inventory.capacity)


def _append_exact_inventory_entry(inventory, entry):
    if inventory is None or not isinstance(entry, dict):
        return False
    inventory.items.append({
        "instance_id": str(entry.get("instance_id", "") or ""),
        "item_id": str(entry.get("item_id", "") or "").strip().lower(),
        "quantity": max(1, _int(entry.get("quantity"), 1)),
        "owner_eid": entry.get("owner_eid"),
        "owner_tag": entry.get("owner_tag"),
        "metadata": dict(entry.get("metadata") or {}),
    })
    return True


def install_workshop_drone_module(sim, player_eid, chassis_instance_id, module_instance_id, *, item_catalog=None):
    workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
    chassis_entry = _workshop_chassis_entry_ref(workshop, chassis_instance_id)
    if chassis_entry is None:
        return {"ok": False, "reason": "chassis_unavailable"}
    module_entry = next(
        (
            dict(candidate)
            for candidate in drone_workshop_entries(workshop, kind="module", item_catalog=item_catalog)
            if str(candidate.get("instance_id", "") or "") == str(module_instance_id or "")
        ),
        None,
    )
    if module_entry is None:
        return {"ok": False, "reason": "module_unavailable"}
    build = _workshop_build_metadata_from_chassis_entry(chassis_entry, item_catalog=item_catalog)
    module = _entry_to_module(module_entry)
    candidate_modules = list(build.get("modules", ()) or ()) + [module]
    candidate = dict(build)
    candidate["modules"] = candidate_modules
    summary = drone_loadout_summary(candidate, item_catalog=item_catalog)
    errors = _workbench_blocking_errors(summary.get("errors", ()))
    if errors:
        return {"ok": False, "reason": "invalid_loadout", "errors": errors, "summary": summary}
    removed = _workshop_remove_entry(sim, player_eid, module_instance_id, item_catalog=item_catalog)
    if removed is None:
        return {"ok": False, "reason": "module_remove_failed"}
    candidate["modules"] = candidate_modules
    updated = _set_workshop_chassis_build_metadata(sim, player_eid, chassis_instance_id, candidate, item_catalog=item_catalog)
    if updated is None:
        _workshop_add_or_block(sim, player_eid, removed, item_catalog=item_catalog)
        return {"ok": False, "reason": "chassis_unavailable"}
    return {
        "ok": True,
        "reason": None,
        "action": "install_module",
        "entry": dict(removed),
        "module": dict(module),
        "summary": drone_loadout_summary(_workshop_build_metadata_from_chassis_entry(updated, item_catalog=item_catalog), item_catalog=item_catalog),
    }


def remove_workshop_drone_module(sim, player_eid, chassis_instance_id, module_index, *, item_catalog=None):
    workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
    chassis_entry = _workshop_chassis_entry_ref(workshop, chassis_instance_id)
    if chassis_entry is None:
        return {"ok": False, "reason": "chassis_unavailable"}
    build = _workshop_build_metadata_from_chassis_entry(chassis_entry, item_catalog=item_catalog)
    modules = list(build.get("modules", ()) or ())
    try:
        index = int(module_index)
    except (TypeError, ValueError):
        index = -1
    if index < 0 or index >= len(modules) or not isinstance(modules[index], dict):
        return {"ok": False, "reason": "module_unavailable"}
    removed_module = dict(modules[index])
    return_entry = _module_to_inventory_entry(
        removed_module,
        player_eid=player_eid,
        instance_factory=getattr(sim, "new_item_instance_id", None),
    )
    can_accept, reason = drone_workshop_can_accept_entry(workshop, return_entry, item_catalog=item_catalog)
    if not can_accept:
        return {"ok": False, "reason": reason or "workshop_full"}
    modules.pop(index)
    build["modules"] = modules
    updated = _set_workshop_chassis_build_metadata(sim, player_eid, chassis_instance_id, build, item_catalog=item_catalog)
    if updated is None:
        return {"ok": False, "reason": "chassis_unavailable"}
    result = _workshop_add_or_block(sim, player_eid, return_entry, item_catalog=item_catalog)
    if not result.get("ok"):
        modules.insert(index, removed_module)
        build["modules"] = modules
        _set_workshop_chassis_build_metadata(sim, player_eid, chassis_instance_id, build, item_catalog=item_catalog)
        return {"ok": False, "reason": result.get("reason", "workshop_full")}
    return {
        "ok": True,
        "reason": None,
        "action": "remove_module",
        "entry": dict(return_entry),
        "module": removed_module,
        "summary": drone_loadout_summary(_workshop_build_metadata_from_chassis_entry(updated, item_catalog=item_catalog), item_catalog=item_catalog),
    }


def swap_workshop_drone_power_center(sim, player_eid, chassis_instance_id, power_instance_id, *, item_catalog=None):
    workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
    chassis_entry = _workshop_chassis_entry_ref(workshop, chassis_instance_id)
    if chassis_entry is None:
        return {"ok": False, "reason": "chassis_unavailable"}
    replacement = next(
        (
            dict(candidate)
            for candidate in drone_workshop_entries(workshop, kind="power_center", item_catalog=item_catalog)
            if str(candidate.get("instance_id", "") or "") == str(power_instance_id or "")
        ),
        None,
    )
    if replacement is None:
        return {"ok": False, "reason": "power_center_unavailable"}
    build = _workshop_build_metadata_from_chassis_entry(chassis_entry, item_catalog=item_catalog)
    candidate = dict(build)
    candidate["power_center_item_id"] = str(replacement.get("item_id", "") or "").strip().lower()
    summary = drone_loadout_summary(candidate, item_catalog=item_catalog)
    errors = _workbench_blocking_errors(summary.get("errors", ()))
    if errors:
        return {"ok": False, "reason": "invalid_loadout", "errors": errors, "summary": summary}
    old_power_entry = build.get("power_center_entry") if isinstance(build.get("power_center_entry"), dict) else None
    removed = _workshop_remove_entry(sim, player_eid, power_instance_id, item_catalog=item_catalog)
    if removed is None:
        return {"ok": False, "reason": "power_center_remove_failed"}
    if old_power_entry:
        result = _workshop_add_or_block(sim, player_eid, old_power_entry, item_catalog=item_catalog)
        if not result.get("ok"):
            _workshop_add_or_block(sim, player_eid, removed, item_catalog=item_catalog)
            return {"ok": False, "reason": result.get("reason", "workshop_full")}
    candidate["power_center_entry"] = dict(removed)
    updated = _set_workshop_chassis_build_metadata(sim, player_eid, chassis_instance_id, candidate, item_catalog=item_catalog)
    if updated is None:
        if old_power_entry:
            _workshop_remove_entry(sim, player_eid, old_power_entry.get("instance_id"), item_catalog=item_catalog)
        _workshop_add_or_block(sim, player_eid, removed, item_catalog=item_catalog)
        return {"ok": False, "reason": "chassis_unavailable"}
    return {
        "ok": True,
        "reason": None,
        "action": "swap_power_center",
        "entry": dict(removed),
        "old_item_id": (old_power_entry or {}).get("item_id"),
        "new_item_id": removed.get("item_id"),
        "summary": drone_loadout_summary(_workshop_build_metadata_from_chassis_entry(updated, item_catalog=item_catalog), item_catalog=item_catalog),
    }


def paint_workshop_drone(sim, player_eid, chassis_instance_id, paint_key, color_key, *, item_catalog=None):
    workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
    chassis_entry = _workshop_chassis_entry_ref(workshop, chassis_instance_id)
    if chassis_entry is None:
        return {"ok": False, "reason": "chassis_unavailable"}
    key = str(paint_key or "").strip().lower()
    if key == "accent_color":
        key = "secondary_color"
    if key not in {"primary_color", "secondary_color"}:
        return {"ok": False, "reason": "invalid_paint_key"}
    color = normalize_drone_paint_word(color_key)
    if not color:
        return {"ok": False, "reason": "invalid_paint"}
    build = _workshop_build_metadata_from_chassis_entry(chassis_entry, item_catalog=item_catalog)
    paint = dict(build.get("paint", {}) or {})
    paint[key] = color
    if key == "secondary_color":
        paint["accent_color"] = color
    build["paint"] = paint
    updated = _set_workshop_chassis_build_metadata(sim, player_eid, chassis_instance_id, build, item_catalog=item_catalog)
    if updated is None:
        return {"ok": False, "reason": "chassis_unavailable"}
    return {
        "ok": True,
        "reason": None,
        "action": "paint",
        "paint_key": key,
        "paint_color": color,
        "summary": drone_loadout_summary(_workshop_build_metadata_from_chassis_entry(updated, item_catalog=item_catalog), item_catalog=item_catalog),
    }


def pack_workshop_drone(sim, player_eid, chassis_instance_id, battery_instance_id, *, item_catalog=None):
    item_catalog = item_catalog or {}
    inventory = sim.ecs.get(Inventory).get(player_eid)
    if inventory is None:
        return {"ok": False, "reason": "missing_inventory"}
    workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
    chassis_entry = _workshop_chassis_entry_ref(workshop, chassis_instance_id)
    if chassis_entry is None:
        return {"ok": False, "reason": "chassis_unavailable"}
    battery_entry = inventory.find(instance_id=battery_instance_id)
    if battery_entry is None:
        return {"ok": False, "reason": "battery_unavailable"}
    battery_item_id = str(battery_entry.get("item_id", "") or "").strip().lower()
    battery_profile = drone_profile_for_item(battery_item_id, item_catalog=item_catalog)
    if battery_profile.get("kind") != "battery":
        return {"ok": False, "reason": "not_battery"}
    battery_metadata = dict(battery_entry.get("metadata") or {})
    charge_max = _int(battery_profile.get("charge_max"), 0)
    charge = _int(battery_metadata.get("battery_charge"), charge_max)
    charge = max(0, min(charge, charge_max)) if charge_max > 0 else max(0, charge)
    build = _workshop_build_metadata_from_chassis_entry(chassis_entry, item_catalog=item_catalog)
    build["battery_item_id"] = battery_item_id
    build["battery_charge"] = charge
    build["battery_charge_max"] = charge_max
    build["source_context"] = "drone_workshop_pack"
    build["source_item_instance_id"] = str(chassis_entry.get("instance_id", "") or "").strip()
    summary = drone_loadout_summary(build, item_catalog=item_catalog)
    errors = _workbench_final_errors(summary.get("errors", ()))
    if errors:
        return {"ok": False, "reason": "invalid_loadout", "errors": errors, "summary": summary}
    metadata = dict(summary.get("metadata", {}) or {})
    metadata["source_context"] = "drone_workshop_pack"
    metadata["source_chassis_instance_id"] = str(chassis_entry.get("instance_id", "") or "").strip()
    metadata["source_battery_instance_id"] = str(battery_entry.get("instance_id", "") or "").strip()
    removed_battery = inventory.remove_item(instance_id=battery_instance_id, quantity=1)
    if removed_battery is None:
        return {"ok": False, "reason": "battery_remove_failed"}
    removed_chassis = drone_workshop_remove_entry(workshop, chassis_instance_id, item_catalog=item_catalog)
    if removed_chassis is None:
        _append_exact_inventory_entry(inventory, removed_battery)
        return {"ok": False, "reason": "chassis_remove_failed"}
    item_def = item_catalog.get(PACKED_DRONE_ITEM_ID, {}) if isinstance(item_catalog, dict) else {}
    packed_instance_id = str(removed_chassis.get("instance_id", "") or "").strip() or None
    added, instance_id = inventory.add_item(
        PACKED_DRONE_ITEM_ID,
        quantity=1,
        stack_max=max(1, _int(item_def.get("stack_max"), 1)),
        instance_id=packed_instance_id,
        instance_factory=getattr(sim, "new_item_instance_id", None),
        owner_eid=player_eid,
        owner_tag="player",
        metadata=metadata,
    )
    if not added:
        drone_workshop_add_entry(workshop, removed_chassis, item_catalog=item_catalog)
        _append_exact_inventory_entry(inventory, removed_battery)
        return {"ok": False, "reason": "inventory_full"}
    return {
        "ok": True,
        "reason": None,
        "action": "pack_workshop_drone",
        "entry": {
            "instance_id": instance_id,
            "item_id": PACKED_DRONE_ITEM_ID,
            "quantity": 1,
            "owner_eid": player_eid,
            "owner_tag": "player",
            "metadata": metadata,
        },
        "battery_entry": dict(removed_battery),
        "chassis_entry": dict(removed_chassis),
        "summary": summary,
        "instance_id": instance_id,
    }


def transfer_player_cargo_to_drone(sim, player_eid, drone_eid, instance_id, *, item_catalog=None):
    state = _deployed_state(sim, drone_eid)
    if state is None or not drone_state_controlled_by_actor(state, player_eid):
        return {"ok": False, "reason": "selected_unavailable"}
    if not _same_floor_adjacent(sim, player_eid, drone_eid):
        return {"ok": False, "reason": "not_adjacent", "drone_eid": drone_eid}
    capacity = drone_cargo_capacity_slots(state, item_catalog=item_catalog)
    if capacity <= 0:
        return {"ok": False, "reason": "no_cargo_module", "drone_eid": drone_eid}
    inventory = sim.ecs.get(Inventory).get(player_eid)
    if inventory is None:
        return {"ok": False, "reason": "missing_inventory", "drone_eid": drone_eid}
    entry = inventory.find(instance_id=instance_id)
    if entry is None:
        return {"ok": False, "reason": "item_unavailable", "drone_eid": drone_eid}
    used = drone_cargo_slot_count(state)
    cost = item_inventory_slot_cost(entry)
    if used + cost > capacity:
        return {"ok": False, "reason": "drone_cargo_full", "drone_eid": drone_eid, "capacity": capacity, "used": used}
    removed = inventory.remove_item(instance_id=instance_id, quantity=max(1, _int(entry.get("quantity"), 1)))
    if removed is None:
        return {"ok": False, "reason": "item_remove_failed", "drone_eid": drone_eid}
    state.cargo.append(dict(removed))
    _sync_source_metadata(state)
    return {"ok": True, "reason": None, "direction": "to_drone", "drone_eid": drone_eid, "entry": dict(removed), "capacity": capacity, "used": drone_cargo_slot_count(state)}


def transfer_drone_cargo_to_player(sim, player_eid, drone_eid, instance_id, *, item_catalog=None):
    del item_catalog
    state = _deployed_state(sim, drone_eid)
    if state is None or not drone_state_controlled_by_actor(state, player_eid):
        return {"ok": False, "reason": "selected_unavailable"}
    if not _same_floor_adjacent(sim, player_eid, drone_eid):
        return {"ok": False, "reason": "not_adjacent", "drone_eid": drone_eid}
    inventory = sim.ecs.get(Inventory).get(player_eid)
    if inventory is None:
        return {"ok": False, "reason": "missing_inventory", "drone_eid": drone_eid}
    index = None
    entry = None
    for idx, candidate in enumerate(list(getattr(state, "cargo", ()) or ())):
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("instance_id", "") or "") == str(instance_id or ""):
            index = idx
            entry = dict(candidate)
            break
    if entry is None:
        return {"ok": False, "reason": "item_unavailable", "drone_eid": drone_eid}
    if not _inventory_can_accept_exact_entry(inventory, entry):
        return {"ok": False, "reason": "inventory_full", "drone_eid": drone_eid}
    state.cargo.pop(index)
    _append_exact_inventory_entry(inventory, entry)
    _sync_source_metadata(state)
    return {"ok": True, "reason": None, "direction": "to_pack", "drone_eid": drone_eid, "entry": entry, "capacity": drone_cargo_capacity_slots(state), "used": drone_cargo_slot_count(state)}


def swap_drone_battery(sim, player_eid, drone_eid, battery_instance_id, *, item_catalog=None):
    state = _deployed_state(sim, drone_eid)
    if state is None or not drone_state_controlled_by_actor(state, player_eid):
        return {"ok": False, "reason": "selected_unavailable"}
    if not _same_floor_adjacent(sim, player_eid, drone_eid):
        return {"ok": False, "reason": "not_adjacent", "drone_eid": drone_eid}
    inventory = sim.ecs.get(Inventory).get(player_eid)
    if inventory is None:
        return {"ok": False, "reason": "missing_inventory", "drone_eid": drone_eid}
    replacement = inventory.find(instance_id=battery_instance_id)
    if replacement is None:
        return {"ok": False, "reason": "battery_unavailable", "drone_eid": drone_eid}
    replacement_item_id = str(replacement.get("item_id", "") or "").strip().lower()
    profile = drone_profile_for_item(replacement_item_id, item_catalog=item_catalog)
    if profile.get("kind") != "battery":
        return {"ok": False, "reason": "not_battery", "drone_eid": drone_eid}
    if not _compatible(profile, getattr(state, "chassis_class", None)):
        return {"ok": False, "reason": "incompatible_battery", "drone_eid": drone_eid}

    old_item_id = str(getattr(state, "battery_item_id", "") or "").strip().lower()
    old_entry = {
        "instance_id": "",
        "item_id": old_item_id,
        "quantity": 1,
        "owner_eid": player_eid,
        "owner_tag": "player",
        "metadata": {
            "battery_charge": int(max(0, _int(getattr(state, "battery_charge", 0), 0))),
            "battery_charge_max": int(max(0, _int(getattr(state, "battery_charge_max", 0), 0))),
            "source_context": "drone_battery_swap",
        },
    }
    if old_item_id and not _inventory_can_accept_exact_entry(inventory, old_entry):
        return {"ok": False, "reason": "inventory_full", "drone_eid": drone_eid}

    removed = inventory.remove_item(instance_id=battery_instance_id, quantity=1)
    if removed is None:
        return {"ok": False, "reason": "battery_remove_failed", "drone_eid": drone_eid}
    if old_item_id:
        old_entry["instance_id"] = sim.new_item_instance_id() if callable(getattr(sim, "new_item_instance_id", None)) else f"drone-battery-{drone_eid}"
        _append_exact_inventory_entry(inventory, old_entry)

    charge_max = _int(profile.get("charge_max"), 0)
    replacement_metadata = dict(removed.get("metadata") or {})
    charge = _int(replacement_metadata.get("battery_charge"), charge_max)
    charge = max(0, min(charge, charge_max)) if charge_max > 0 else max(0, charge)
    previous = {
        "item_id": old_item_id,
        "battery_charge": old_entry["metadata"]["battery_charge"],
        "battery_charge_max": old_entry["metadata"]["battery_charge_max"],
    }
    state.battery_item_id = replacement_item_id
    state.battery_charge = int(charge)
    state.battery_charge_max = int(charge_max)
    _sync_drone_runtime_shape(sim, drone_eid, state, item_catalog=item_catalog)
    return {
        "ok": True,
        "reason": None,
        "drone_eid": drone_eid,
        "new_battery_item_id": replacement_item_id,
        "old_battery_item_id": old_item_id,
        "battery_charge": int(charge),
        "battery_charge_max": int(charge_max),
        "previous": previous,
        "entry": dict(removed),
    }


def install_drone_module(sim, player_eid, drone_eid, module_instance_id, *, item_catalog=None):
    state = _deployed_state(sim, drone_eid)
    if state is None or not drone_state_controlled_by_actor(state, player_eid):
        return {"ok": False, "reason": "selected_unavailable"}
    if not _same_floor_adjacent(sim, player_eid, drone_eid):
        return {"ok": False, "reason": "not_adjacent", "drone_eid": drone_eid}
    workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
    entry = next(
        (
            candidate
            for candidate in drone_workshop_entries(workshop, kind="module", item_catalog=item_catalog)
            if str(candidate.get("instance_id", "") or "") == str(module_instance_id or "")
        ),
        None,
    )
    if entry is None:
        return {"ok": False, "reason": "module_unavailable", "drone_eid": drone_eid}
    module = _entry_to_module(entry)
    profile = drone_profile_for_item((module or {}).get("item_id"), item_catalog=item_catalog)
    if profile.get("kind") != "module":
        return {"ok": False, "reason": "not_module", "drone_eid": drone_eid}
    candidate_modules = list(getattr(state, "modules", ()) or ()) + [module]
    errors, summary = _loadout_errors_for_candidate(state, item_catalog=item_catalog, modules=candidate_modules)
    if errors:
        return {"ok": False, "reason": "invalid_loadout", "drone_eid": drone_eid, "errors": errors, "summary": summary}
    removed = _workshop_remove_entry(sim, player_eid, module_instance_id, item_catalog=item_catalog)
    if removed is None:
        return {"ok": False, "reason": "module_remove_failed", "drone_eid": drone_eid}
    installed = _entry_to_module(removed)
    state.modules.append(installed)
    summary = _sync_drone_runtime_shape(sim, drone_eid, state, item_catalog=item_catalog)
    return {
        "ok": True,
        "reason": None,
        "action": "install_module",
        "drone_eid": drone_eid,
        "entry": dict(removed),
        "module": dict(installed),
        "summary": summary,
    }


def remove_drone_module(sim, player_eid, drone_eid, module_index, *, item_catalog=None):
    state = _deployed_state(sim, drone_eid)
    if state is None or not drone_state_controlled_by_actor(state, player_eid):
        return {"ok": False, "reason": "selected_unavailable"}
    if not _same_floor_adjacent(sim, player_eid, drone_eid):
        return {"ok": False, "reason": "not_adjacent", "drone_eid": drone_eid}
    modules = list(getattr(state, "modules", ()) or ())
    try:
        index = int(module_index)
    except (TypeError, ValueError):
        index = -1
    if index < 0 or index >= len(modules) or not isinstance(modules[index], dict):
        return {"ok": False, "reason": "module_unavailable", "drone_eid": drone_eid}
    module = dict(modules[index])
    return_entry = _module_to_inventory_entry(module, player_eid=player_eid, instance_factory=None)
    if return_entry is None:
        return {"ok": False, "reason": "not_module", "drone_eid": drone_eid}
    workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
    can_accept, reason = drone_workshop_can_accept_entry(workshop, return_entry, item_catalog=item_catalog)
    if not can_accept:
        return {"ok": False, "reason": reason or "workshop_full", "drone_eid": drone_eid}
    candidate_modules = modules[:index] + modules[index + 1:]
    errors, summary = _loadout_errors_for_candidate(state, item_catalog=item_catalog, modules=candidate_modules)
    if errors:
        return {"ok": False, "reason": "invalid_loadout", "drone_eid": drone_eid, "errors": errors, "summary": summary}
    removed = modules.pop(index)
    state.modules = modules
    return_entry = _module_to_inventory_entry(
        removed,
        player_eid=player_eid,
        instance_factory=getattr(sim, "new_item_instance_id", None),
    )
    result = _workshop_add_or_block(sim, player_eid, return_entry, item_catalog=item_catalog)
    if not result.get("ok"):
        state.modules = list(getattr(state, "modules", ()) or ())
        state.modules.insert(index, removed)
        return {"ok": False, "reason": result.get("reason", "workshop_full"), "drone_eid": drone_eid}
    summary = _sync_drone_runtime_shape(sim, drone_eid, state, item_catalog=item_catalog)
    return {
        "ok": True,
        "reason": None,
        "action": "remove_module",
        "drone_eid": drone_eid,
        "entry": dict(return_entry),
        "module": dict(removed),
        "summary": summary,
    }


def swap_drone_chassis(sim, player_eid, drone_eid, chassis_instance_id, *, item_catalog=None):
    state = _deployed_state(sim, drone_eid)
    if state is None or not drone_state_controlled_by_actor(state, player_eid):
        return {"ok": False, "reason": "selected_unavailable"}
    if not _same_floor_adjacent(sim, player_eid, drone_eid):
        return {"ok": False, "reason": "not_adjacent", "drone_eid": drone_eid}
    workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
    replacement = next(
        (
            candidate
            for candidate in drone_workshop_entries(workshop, kind="chassis", item_catalog=item_catalog)
            if str(candidate.get("instance_id", "") or "") == str(chassis_instance_id or "")
        ),
        None,
    )
    if replacement is None:
        return {"ok": False, "reason": "chassis_unavailable", "drone_eid": drone_eid}
    replacement_item_id = str(replacement.get("item_id", "") or "").strip().lower()
    profile = drone_profile_for_item(replacement_item_id, item_catalog=item_catalog)
    if profile.get("kind") != "chassis":
        return {"ok": False, "reason": "not_chassis", "drone_eid": drone_eid}
    errors, summary = _loadout_errors_for_candidate(state, item_catalog=item_catalog, chassis_item_id=replacement_item_id)
    if errors:
        return {"ok": False, "reason": "invalid_loadout", "drone_eid": drone_eid, "errors": errors, "summary": summary}
    old_item_id = str(getattr(state, "chassis_item_id", "") or "").strip().lower()
    old_entry = _part_return_entry(old_item_id, player_eid=player_eid, source_context="drone_chassis_swap")
    removed = _workshop_remove_entry(sim, player_eid, chassis_instance_id, item_catalog=item_catalog)
    if removed is None:
        return {"ok": False, "reason": "chassis_remove_failed", "drone_eid": drone_eid}
    if old_entry:
        old_entry["instance_id"] = sim.new_item_instance_id() if callable(getattr(sim, "new_item_instance_id", None)) else ""
        result = _workshop_add_or_block(sim, player_eid, old_entry, item_catalog=item_catalog)
        if not result.get("ok"):
            _workshop_add_or_block(sim, player_eid, removed, item_catalog=item_catalog)
            return {"ok": False, "reason": result.get("reason", "workshop_full"), "drone_eid": drone_eid}
    state.chassis_item_id = replacement_item_id
    state.chassis_class = str(profile.get("chassis_class", "") or "").strip().upper() or state.chassis_class
    summary = _sync_drone_runtime_shape(sim, drone_eid, state, item_catalog=item_catalog)
    return {
        "ok": True,
        "reason": None,
        "action": "swap_chassis",
        "drone_eid": drone_eid,
        "entry": dict(removed),
        "old_item_id": old_item_id,
        "new_item_id": replacement_item_id,
        "summary": summary,
    }


def swap_drone_power_center(sim, player_eid, drone_eid, power_instance_id, *, item_catalog=None):
    state = _deployed_state(sim, drone_eid)
    if state is None or not drone_state_controlled_by_actor(state, player_eid):
        return {"ok": False, "reason": "selected_unavailable"}
    if not _same_floor_adjacent(sim, player_eid, drone_eid):
        return {"ok": False, "reason": "not_adjacent", "drone_eid": drone_eid}
    workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
    replacement = next(
        (
            candidate
            for candidate in drone_workshop_entries(workshop, kind="power_center", item_catalog=item_catalog)
            if str(candidate.get("instance_id", "") or "") == str(power_instance_id or "")
        ),
        None,
    )
    if replacement is None:
        return {"ok": False, "reason": "power_center_unavailable", "drone_eid": drone_eid}
    replacement_item_id = str(replacement.get("item_id", "") or "").strip().lower()
    profile = drone_profile_for_item(replacement_item_id, item_catalog=item_catalog)
    if profile.get("kind") != "power_center":
        return {"ok": False, "reason": "not_power_center", "drone_eid": drone_eid}
    errors, summary = _loadout_errors_for_candidate(state, item_catalog=item_catalog, power_center_item_id=replacement_item_id)
    if errors:
        return {"ok": False, "reason": "invalid_loadout", "drone_eid": drone_eid, "errors": errors, "summary": summary}
    old_item_id = str(getattr(state, "power_center_item_id", "") or "").strip().lower()
    old_entry = _part_return_entry(old_item_id, player_eid=player_eid, source_context="drone_power_core_swap")
    removed = _workshop_remove_entry(sim, player_eid, power_instance_id, item_catalog=item_catalog)
    if removed is None:
        return {"ok": False, "reason": "power_center_remove_failed", "drone_eid": drone_eid}
    if old_entry:
        old_entry["instance_id"] = sim.new_item_instance_id() if callable(getattr(sim, "new_item_instance_id", None)) else ""
        result = _workshop_add_or_block(sim, player_eid, old_entry, item_catalog=item_catalog)
        if not result.get("ok"):
            _workshop_add_or_block(sim, player_eid, removed, item_catalog=item_catalog)
            return {"ok": False, "reason": result.get("reason", "workshop_full"), "drone_eid": drone_eid}
    state.power_center_item_id = replacement_item_id
    summary = _sync_drone_runtime_shape(sim, drone_eid, state, item_catalog=item_catalog)
    return {
        "ok": True,
        "reason": None,
        "action": "swap_power_center",
        "drone_eid": drone_eid,
        "entry": dict(removed),
        "old_item_id": old_item_id,
        "new_item_id": replacement_item_id,
        "summary": summary,
    }


def paint_drone(sim, player_eid, drone_eid, paint_key, color_key, *, item_catalog=None):
    state = _deployed_state(sim, drone_eid)
    if state is None or not drone_state_controlled_by_actor(state, player_eid):
        return {"ok": False, "reason": "selected_unavailable"}
    if not _same_floor_adjacent(sim, player_eid, drone_eid):
        return {"ok": False, "reason": "not_adjacent", "drone_eid": drone_eid}
    key = str(paint_key or "").strip().lower()
    if key == "accent_color":
        key = "secondary_color"
    if key not in {"primary_color", "secondary_color"}:
        return {"ok": False, "reason": "invalid_paint_key", "drone_eid": drone_eid}
    color = normalize_drone_paint_word(color_key)
    if not color:
        return {"ok": False, "reason": "invalid_paint", "drone_eid": drone_eid}
    paint = dict(getattr(state, "paint", {}) or {})
    paint[key] = color
    if key == "secondary_color":
        paint["accent_color"] = color
    state.paint = paint
    summary = _sync_drone_runtime_shape(sim, drone_eid, state, item_catalog=item_catalog)
    return {
        "ok": True,
        "reason": None,
        "action": "paint",
        "drone_eid": drone_eid,
        "paint_key": key,
        "paint_color": color,
        "summary": summary,
    }
