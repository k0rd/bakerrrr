from __future__ import annotations

import copy
import json
import pickle
import re
import types
from pathlib import Path

from .events import EventBus
from .save_paths import SAVE_DIR
from .sim import Simulation
from game.appearance import AppearanceManager
from game.components import Position, VehicleState
from game.organizations import rebuild_organization_index, refresh_loaded_organization_branch_briefings


def _inventory_item_instance_ids_from_sim(sim):
    ids = []
    components = getattr(getattr(sim, "ecs", None), "components", {})
    if not isinstance(components, dict):
        return ids
    for component_map in components.values():
        if not isinstance(component_map, dict):
            continue
        for component in component_map.values():
            items = getattr(component, "items", None)
            if not isinstance(items, list):
                continue
            for entry in items:
                if isinstance(entry, dict):
                    ids.append(entry.get("instance_id"))
    return ids

SAVE_VERSION = 2


BONES_ARCHIVE_PATH = SAVE_DIR / "bones.json"
RUN_ECHOES_ARCHIVE_PATH = SAVE_DIR / "run_echoes.json"
_EXCLUDED_SIM_STATE_KEYS = {
    "events",
    "systems",
    "mutators",
    "audio_runtime",
    "appearance",
    "npc_social_dynamics_system",
    "mechanical_device_system",
    "social_knowledge_influence_system",
    "run_epilogue_ledger",
    "ecology_registry_runtime",
    "property_anchor_index",
    "property_cover_index",
    "actor_attention_state",
    "pursuit_streaming_state",
    "wildlife_damage_reactions",
    "vision_scene",
    "dream_residue",
    "npc_self_protection_state",
    "rumor_weather_posture_state",
    "action_menu_ui",
    "custom_room_curiosity_flavors",
    "custom_ui_themes",
    "active_ejections",
    "property_order",
    "next_property_order",
    "_properties_in_radius_cache",
    "_properties_in_rect_cache",
    "_mechanical_device_ids",
    "_derived_fact_state",
    "_organization_runtime_cache",
    "_property_access_controller_cache",
    "_player_business_runtime_cache",
    "_npc_path_step_cache",
    "_npc_path_search_failures",
    "_routine_will_signatures",
    "_hidden_contact_referral_property_cache",
    "_herbal_decay_next_tick",
    "_underground_plan_cache",
    "building_regular_chunk_pulse_cache",
    "criminal_drive_runtime_cache",
    "npc_behavior_runtime_cache",
    "npc_behavior_search_cache",
    "ground_item_index",
    "ground_item_order",
    "next_ground_item_order",
    "_ground_items_in_rect_cache",
    "vehicle_occupants",
    "vehicle_by_occupant",
    "vehicle_primary_occupants",
    "_pending_stream_unloads",
    "_stream_unload_flush_active",
}
_SKIP_SNAPSHOT_VALUE = object()


def _is_module_pickle_error(exc):
    text = str(exc or "").strip().lower()
    return "module" in text and ("pickle" in text or "copy" in text)


def _is_runtime_snapshot_object(value):
    cls = type(value)
    module = str(getattr(cls, "__module__", "") or "").strip().lower()
    name = str(getattr(cls, "__name__", "") or "").strip().lower()
    if module.startswith("_curses") or module.startswith("curses"):
        return True
    if module.startswith("pygame"):
        return True
    return name in {"window"} and "curses" in module


def _is_runtime_pickle_error(exc):
    text = str(exc or "").strip().lower()
    if "cannot pickle" not in text:
        return False
    return any(
        marker in text
        for marker in (
            "_curses.window",
            "curses.window",
            "pygame.",
            "pygame surface",
            "pygame.surface",
        )
    )


def _is_snapshot_skip_error(exc):
    return _is_module_pickle_error(exc) or _is_runtime_pickle_error(exc)


def _strip_module_refs(value, memo=None):
    if isinstance(value, types.ModuleType) or _is_runtime_snapshot_object(value):
        return _SKIP_SNAPSHOT_VALUE
    memo = {} if memo is None else memo
    value_id = id(value)
    if value_id in memo:
        return memo[value_id]
    if isinstance(value, dict):
        clone = {}
        memo[value_id] = clone
        for key, inner in value.items():
            safe_key = _strip_module_refs(key, memo)
            safe_inner = _strip_module_refs(inner, memo)
            if safe_key is _SKIP_SNAPSHOT_VALUE or safe_inner is _SKIP_SNAPSHOT_VALUE:
                continue
            clone[safe_key] = safe_inner
        return clone
    if isinstance(value, list):
        clone = []
        memo[value_id] = clone
        for inner in value:
            safe_inner = _strip_module_refs(inner, memo)
            if safe_inner is _SKIP_SNAPSHOT_VALUE:
                continue
            clone.append(safe_inner)
        return clone
    if isinstance(value, tuple):
        placeholder = []
        memo[value_id] = placeholder
        for inner in value:
            safe_inner = _strip_module_refs(inner, memo)
            if safe_inner is _SKIP_SNAPSHOT_VALUE:
                continue
            placeholder.append(safe_inner)
        clone = tuple(placeholder)
        memo[value_id] = clone
        return clone
    if isinstance(value, set):
        clone = set()
        memo[value_id] = clone
        for inner in value:
            safe_inner = _strip_module_refs(inner, memo)
            if safe_inner is _SKIP_SNAPSHOT_VALUE:
                continue
            clone.add(safe_inner)
        return clone
    try:
        return copy.deepcopy(value)
    except TypeError as exc:
        if _is_snapshot_skip_error(exc):
            return _SKIP_SNAPSHOT_VALUE
        raise


def _snapshot_value_or_skip(key, value):
    if isinstance(value, types.ModuleType) or _is_runtime_snapshot_object(value):
        return _SKIP_SNAPSHOT_VALUE
    if key == "log" and hasattr(value, "default_tick_source"):
        # Avoid deep-copying bound runtime callbacks (they recurse back into sim state).
        original_tick_source = value.default_tick_source
        value.default_tick_source = None
        try:
            return copy.deepcopy(value)
        finally:
            value.default_tick_source = original_tick_source
    if key == "tilemap":
        original_add = getattr(value, "on_add_entity", None)
        original_move = getattr(value, "on_move_entity", None)
        original_remove = getattr(value, "on_remove_entity", None)
        value.on_add_entity = None
        value.on_move_entity = None
        value.on_remove_entity = None
        try:
            return copy.deepcopy(value)
        finally:
            value.on_add_entity = original_add
            value.on_move_entity = original_move
            value.on_remove_entity = original_remove
    try:
        return copy.deepcopy(value)
    except TypeError as exc:
        if _is_snapshot_skip_error(exc):
            return _strip_module_refs(value)
        raise


def normalize_character_name(raw_name, max_length=40):
    if raw_name is None:
        return ""
    if isinstance(raw_name, bytes):
        raw_name = raw_name.decode("utf-8", "ignore")
    name = " ".join(str(raw_name).strip().split())
    return name[: max(1, int(max_length))].strip()


def character_save_slug(name):
    normalized = normalize_character_name(name)
    slug = re.sub(r"[^a-z0-9_-]+", "_", normalized.lower()).strip("_")
    return slug or "run"


def character_save_path(name, save_dir=SAVE_DIR):
    return Path(save_dir) / f"{character_save_slug(name)}.sav"


def character_save_exists(name, save_dir=SAVE_DIR):
    return character_save_path(name, save_dir=save_dir).exists()


def delete_character_save(name, save_dir=SAVE_DIR):
    path = character_save_path(name, save_dir=save_dir)
    if not path.exists():
        return False
    path.unlink()
    return True


def _json_safe(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _json_safe(inner)
            for key, inner in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(inner) for inner in value]
    return str(value)


def _load_record_archive(archive_path):
    path = Path(archive_path)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(payload, dict):
        payload = payload.get("records", [])
    if not isinstance(payload, list):
        return []
    return [entry for entry in payload if isinstance(entry, dict)]


def _save_record_archive(records, *, archive_path, max_records=64):
    path = Path(archive_path)
    clean_records = [_json_safe(entry) for entry in records if isinstance(entry, dict)]
    if max_records is not None and int(max_records) > 0:
        clean_records = clean_records[-int(max_records):]
    payload = {
        "version": 1,
        "records": clean_records,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
    return path


def _append_record_archive(record, *, archive_path, max_records=64, id_key="record_id"):
    if not isinstance(record, dict):
        return None
    records = _load_record_archive(archive_path)
    record_id = str(record.get(str(id_key or "record_id"), "") or "").strip()
    if record_id:
        records = [
            entry
            for entry in records
            if str(entry.get(str(id_key or "record_id"), "") or "").strip() != record_id
        ]
    records.append(record)
    return _save_record_archive(records, archive_path=archive_path, max_records=max_records)


def load_bones_archive(archive_path=BONES_ARCHIVE_PATH):
    if archive_path is None:
        archive_path = BONES_ARCHIVE_PATH
    return _load_record_archive(archive_path)


def load_run_echoes_archive(archive_path=RUN_ECHOES_ARCHIVE_PATH):
    if archive_path is None:
        archive_path = RUN_ECHOES_ARCHIVE_PATH
    return _load_record_archive(archive_path)


def save_bones_archive(records, archive_path=BONES_ARCHIVE_PATH, max_records=64):
    if archive_path is None:
        archive_path = BONES_ARCHIVE_PATH
    return _save_record_archive(records, archive_path=archive_path, max_records=max_records)


def save_run_echoes_archive(records, archive_path=RUN_ECHOES_ARCHIVE_PATH, max_records=64):
    if archive_path is None:
        archive_path = RUN_ECHOES_ARCHIVE_PATH
    return _save_record_archive(records, archive_path=archive_path, max_records=max_records)


def append_bones_record(record, archive_path=BONES_ARCHIVE_PATH, max_records=64):
    if archive_path is None:
        archive_path = BONES_ARCHIVE_PATH
    return _append_record_archive(record, archive_path=archive_path, max_records=max_records, id_key="record_id")


def append_run_echo_record(record, archive_path=RUN_ECHOES_ARCHIVE_PATH, max_records=64):
    if archive_path is None:
        archive_path = RUN_ECHOES_ARCHIVE_PATH
    return _append_record_archive(record, archive_path=archive_path, max_records=max_records, id_key="echo_id")


def _chunk_key(value):
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        try:
            return (int(value[0]), int(value[1]))
        except (TypeError, ValueError):
            return None
    return None


def _property_chunk(sim, prop):
    if not isinstance(prop, dict):
        return None
    metadata = prop.get("metadata")
    if isinstance(metadata, dict):
        key = _chunk_key(metadata.get("chunk"))
        if key is not None:
            return key
    try:
        return sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
    except (TypeError, ValueError):
        return None


def _ground_item_chunk(sim, ground):
    if not isinstance(ground, dict):
        return None
    metadata = ground.get("metadata")
    if isinstance(metadata, dict):
        key = _chunk_key(metadata.get("chunk"))
        if key is not None:
            return key
    try:
        return sim.chunk_coords(int(ground.get("x", 0)), int(ground.get("y", 0)))
    except (TypeError, ValueError):
        return None


def _entity_ids_in_chunk(sim, key):
    results = []
    for eid in tuple(getattr(sim, "entity_ids_in_chunk", lambda _key: ())((int(key[0]), int(key[1])))):
        if eid == getattr(sim, "player_eid", None):
            continue
        results.append(int(eid))
    return results


def _entity_snapshot(sim, eid):
    components = {}
    for component_type, bucket in sim.ecs.components.items():
        if not isinstance(bucket, dict) or eid not in bucket:
            continue
        components[component_type] = copy.deepcopy(bucket[eid])
    return components


def _max_numeric_suffix(values, prefix):
    highest = 0
    prefix = str(prefix)
    for value in values:
        text = str(value)
        if not text.startswith(prefix):
            continue
        try:
            highest = max(highest, int(text[len(prefix):]))
        except (TypeError, ValueError):
            continue
    return highest


def snapshot_chunk_state(sim, key):
    key = _chunk_key(key)
    if key is None:
        return None

    property_records = []
    for record in copy.deepcopy(sim.chunk_property_records.get(key, [])):
        if not isinstance(record, dict):
            property_records.append(record)
            continue
        property_id = str(record.get("id", "")).strip()
        live_prop = sim.properties.get(property_id) if property_id else None
        if isinstance(live_prop, dict):
            live_chunk = _property_chunk(sim, live_prop)
            if live_chunk is not None and live_chunk != key:
                continue
            record.update({
                "x": int(live_prop.get("x", record.get("x", 0)) or 0),
                "y": int(live_prop.get("y", record.get("y", 0)) or 0),
                "z": int(live_prop.get("z", record.get("z", 0)) or 0),
                "kind": str(live_prop.get("kind", record.get("kind", "property"))).strip().lower() or "property",
            })
            metadata = live_prop.get("metadata")
            if isinstance(metadata, dict):
                record["archetype"] = metadata.get("archetype", record.get("archetype"))
                record["building_id"] = metadata.get("building_id", record.get("building_id"))
        property_records.append(record)
    raw_ground_item_records = list(sim.chunk_ground_item_records.get(key, []))
    raw_population_records = list(sim.chunk_population_records.get(key, []))

    property_ids = {
        str(record.get("id"))
        for record in property_records
        if isinstance(record, dict) and str(record.get("id", "")).strip()
    }
    for property_id, prop in sim.properties.items():
        if _property_chunk(sim, prop) == key:
            property_ids.add(str(property_id))

    ground_item_ids = {
        str(ground_id)
        for ground_id in raw_ground_item_records
        if str(ground_id).strip()
    }
    for ground_item_id, ground in sim.ground_items.items():
        if _ground_item_chunk(sim, ground) == key:
            ground_item_ids.add(str(ground_item_id))

    entity_ids = set(_entity_ids_in_chunk(sim, key))
    ground_item_records = [ground_id for ground_id in raw_ground_item_records if str(ground_id) in ground_item_ids]
    population_records = []
    for eid in raw_population_records:
        try:
            int_eid = int(eid)
        except (TypeError, ValueError):
            continue
        if int_eid in entity_ids:
            population_records.append(int_eid)

    store_states = {
        property_id: copy.deepcopy(state)
        for property_id, state in sim.stores.items()
        if property_id in property_ids
    }

    if not any((property_records, ground_item_records, population_records, property_ids, ground_item_ids, entity_ids, store_states)):
        return None

    return {
        "chunk": key,
        "property_records": property_records,
        "ground_item_records": ground_item_records,
        "population_records": population_records,
        "properties": {
            property_id: copy.deepcopy(sim.properties[property_id])
            for property_id in sorted(property_ids)
            if property_id in sim.properties
        },
        "ground_items": {
            ground_item_id: copy.deepcopy(sim.ground_items[ground_item_id])
            for ground_item_id in sorted(ground_item_ids)
            if ground_item_id in sim.ground_items
        },
        "entities": {
            int(eid): _entity_snapshot(sim, int(eid))
            for eid in sorted(entity_ids)
        },
        "stores": store_states,
    }


def unload_chunk_state(sim, key, *, rebuild_indexes=True):
    key = _chunk_key(key)
    if key is None:
        return None

    from game.pursuit_streaming_runtime import prepare_pursuit_chunk_unload

    prepare_pursuit_chunk_unload(sim, key)
    snapshot = snapshot_chunk_state(sim, key)
    if snapshot is None:
        sim.chunk_saved_states.pop(key, None)
        sim.chunk_property_records.pop(key, None)
        sim.chunk_ground_item_records.pop(key, None)
        sim.chunk_population_records.pop(key, None)
        return None

    sim.chunk_saved_states[key] = snapshot

    indexes_updated = _remove_snapshot_live_state(sim, snapshot)

    sim.chunk_property_records.pop(key, None)
    sim.chunk_ground_item_records.pop(key, None)
    sim.chunk_population_records.pop(key, None)
    if rebuild_indexes and not indexes_updated and hasattr(sim, "rebuild_spatial_indexes"):
        sim.rebuild_spatial_indexes()
    return snapshot


def _remove_snapshot_live_state(sim, snapshot):
    """Remove one unloaded chunk while preserving the maintained indexes.

    Chunk streaming used to update the entity index through ``remove_entity``
    and then rebuild every entity, property, and ground-item index anyway.
    Unindexing the two record collections at their mutation boundary keeps the
    result authoritative without turning an unload into a global recount.

    The boolean return lets older or reduced simulation doubles retain the
    defensive full-rebuild fallback.
    """
    can_update_indexes = all(
        callable(getattr(sim, method_name, None))
        for method_name in (
            "_unindex_ground_item_record",
            "_unindex_property_record",
            "_invalidate_properties_in_radius_cache",
            "remove_entity",
        )
    )

    property_removed = False
    for ground_item_id in tuple(snapshot.get("ground_items", {}).keys()):
        ground = sim.ground_items.pop(ground_item_id, None)
        if ground is not None and can_update_indexes:
            sim._unindex_ground_item_record(ground_item_id, ground, drop_order=True)
    for property_id in tuple(snapshot.get("stores", {}).keys()):
        sim.stores.pop(property_id, None)
    for property_id in tuple(snapshot.get("properties", {}).keys()):
        prop = sim.properties.pop(property_id, None)
        if prop is None:
            continue
        property_removed = True
        if can_update_indexes:
            sim._unindex_property_record(property_id, prop)
            sim.property_order.pop(property_id, None)
        mechanical_ids = getattr(sim, "_mechanical_device_ids", None)
        if isinstance(mechanical_ids, set):
            mechanical_ids.discard(str(property_id))
    for eid in tuple(snapshot.get("entities", {}).keys()):
        sim.remove_entity(int(eid))

    if property_removed:
        sim.property_registry_dirty = True
        if can_update_indexes:
            sim._invalidate_properties_in_radius_cache()
    return bool(can_update_indexes)


def _merge_snapshot_record_rows(existing_rows, incoming_rows):
    merged = []
    seen = set()
    for row in tuple(existing_rows or ()) + tuple(incoming_rows or ()):
        if isinstance(row, dict):
            key = str(row.get("id", "") or "").strip()
            if not key:
                key = repr(sorted(row.items()))
        else:
            key = row
        if key in seen:
            continue
        seen.add(key)
        merged.append(copy.deepcopy(row))
    return merged


def merge_unload_chunk_state(sim, key, *, rebuild_indexes=True):
    key = _chunk_key(key)
    if key is None:
        return None

    existing = sim.chunk_saved_states.get(key)
    if not isinstance(existing, dict):
        return unload_chunk_state(sim, key, rebuild_indexes=rebuild_indexes)

    from game.pursuit_streaming_runtime import prepare_pursuit_chunk_unload

    prepare_pursuit_chunk_unload(sim, key)
    snapshot = snapshot_chunk_state(sim, key)
    if snapshot is None:
        sim.chunk_property_records.pop(key, None)
        sim.chunk_ground_item_records.pop(key, None)
        sim.chunk_population_records.pop(key, None)
        return None

    for section in ("properties", "ground_items", "entities", "stores"):
        bucket = existing.setdefault(section, {})
        if isinstance(bucket, dict):
            bucket.update(copy.deepcopy(snapshot.get(section, {}) or {}))

    for section in ("property_records", "ground_item_records", "population_records"):
        existing[section] = _merge_snapshot_record_rows(
            existing.get(section, ()),
            snapshot.get(section, ()),
        )

    indexes_updated = _remove_snapshot_live_state(sim, snapshot)

    sim.chunk_property_records.pop(key, None)
    sim.chunk_ground_item_records.pop(key, None)
    sim.chunk_population_records.pop(key, None)
    if rebuild_indexes and not indexes_updated and hasattr(sim, "rebuild_spatial_indexes"):
        sim.rebuild_spatial_indexes()
    return snapshot


def restore_chunk_state(sim, key):
    key = _chunk_key(key)
    if key is None:
        return False

    snapshot = sim.chunk_saved_states.pop(key, None)
    if not isinstance(snapshot, dict):
        return False

    for property_id, prop in snapshot.get("properties", {}).items():
        sim.properties[property_id] = copy.deepcopy(prop)
        metadata = prop.get("metadata") if isinstance(prop, dict) and isinstance(prop.get("metadata"), dict) else {}
        if bool(metadata.get("mechanical_device")):
            mechanical_ids = getattr(sim, "_mechanical_device_ids", None)
            if isinstance(mechanical_ids, set):
                mechanical_ids.add(str(property_id))
    for ground_item_id, ground in snapshot.get("ground_items", {}).items():
        sim.ground_items[ground_item_id] = copy.deepcopy(ground)
    for property_id, state in snapshot.get("stores", {}).items():
        sim.stores[property_id] = copy.deepcopy(state)

    if "property_records" in snapshot:
        sim.chunk_property_records[key] = copy.deepcopy(snapshot.get("property_records", []))
    if "ground_item_records" in snapshot:
        sim.chunk_ground_item_records[key] = copy.deepcopy(snapshot.get("ground_item_records", []))
    if "population_records" in snapshot:
        sim.chunk_population_records[key] = copy.deepcopy(snapshot.get("population_records", []))
        memberships = getattr(sim, "chunk_population_membership", None)
        if isinstance(memberships, dict):
            for eid in tuple(sim.chunk_population_records[key] or ()):
                try:
                    memberships[int(eid)] = key
                except (TypeError, ValueError):
                    continue

    max_entity_id = 0
    for eid, component_map in snapshot.get("entities", {}).items():
        eid = int(eid)
        max_entity_id = max(max_entity_id, eid)
        position = None
        for component_type, component in component_map.items():
            restored = copy.deepcopy(component)
            sim.ecs.components.setdefault(component_type, {})[eid] = restored
            if position is None and all(hasattr(restored, attr) for attr in ("x", "y", "z")):
                position = restored
        if position is not None:
            sim.tilemap.add_entity(eid, int(position.x), int(position.y), int(position.z))

    if max_entity_id:
        sim.ecs.next_id = max(int(sim.ecs.next_id), max_entity_id + 1)
    sim.next_property_id = max(
        int(sim.next_property_id),
        _max_numeric_suffix(sim.properties.keys(), "prop-") + 1,
    )
    sim.next_ground_item_id = max(
        int(sim.next_ground_item_id),
        _max_numeric_suffix(sim.ground_items.keys(), "ground-") + 1,
    )
    sim.next_item_instance_id = max(
        int(sim.next_item_instance_id),
        _max_numeric_suffix(
            [ground.get("instance_id") for ground in sim.ground_items.values()]
            + _inventory_item_instance_ids_from_sim(sim),
            "item-",
        ) + 1,
    )
    sim.property_registry_dirty = True
    if hasattr(sim, "rebuild_spatial_indexes"):
        sim.rebuild_spatial_indexes()
    if hasattr(sim, "reapply_door_states"):
        sim.reapply_door_states(chunk=key)
    from game.pursuit_streaming_runtime import settle_pursuit_chunk_restore

    settle_pursuit_chunk_restore(sim, key, tuple(snapshot.get("entities", {}).keys()))
    refresh_loaded_organization_branch_briefings(
        sim,
        property_ids=tuple(snapshot.get("properties", {}).keys()),
        reason="chunk_restore",
    )
    return True


def _remove_property_record_from_rows(rows, property_id):
    property_id = str(property_id)
    return [
        row
        for row in tuple(rows or ())
        if not (isinstance(row, dict) and str(row.get("id", "")).strip() == property_id)
    ]


def _restore_active_vehicle_properties(sim):
    ecs = getattr(sim, "ecs", None)
    if ecs is None:
        return 0
    vehicle_states = ecs.get(VehicleState)
    positions = ecs.get(Position)
    saved_states = getattr(sim, "chunk_saved_states", None)
    if not isinstance(vehicle_states, dict) or not isinstance(saved_states, dict):
        return 0

    restored = 0
    for eid, state in tuple(vehicle_states.items()):
        if not bool(getattr(state, "in_vehicle", False)):
            continue
        vehicle_id = str(getattr(state, "active_vehicle_id", "") or "").strip()
        if not vehicle_id or vehicle_id in getattr(sim, "properties", {}):
            continue

        found = None
        for _key, snapshot in tuple(saved_states.items()):
            if not isinstance(snapshot, dict):
                continue
            properties = snapshot.get("properties")
            if isinstance(properties, dict) and vehicle_id in properties:
                found = (snapshot, properties[vehicle_id])
                break
        if found is None:
            continue

        snapshot, saved_prop = found
        prop = copy.deepcopy(saved_prop)
        pos = positions.get(eid)
        if pos is not None:
            prop["x"] = int(pos.x)
            prop["y"] = int(pos.y)
            prop["z"] = int(pos.z)
            metadata = prop.get("metadata")
            if isinstance(metadata, dict):
                metadata["chunk"] = sim.chunk_coords(int(pos.x), int(pos.y))

        sim.properties[vehicle_id] = prop

        properties = snapshot.get("properties")
        if isinstance(properties, dict):
            properties.pop(vehicle_id, None)
        stores = snapshot.get("stores")
        if isinstance(stores, dict) and vehicle_id in stores:
            sim.stores[vehicle_id] = copy.deepcopy(stores.pop(vehicle_id))
        if isinstance(snapshot.get("property_records"), list):
            snapshot["property_records"] = _remove_property_record_from_rows(
                snapshot.get("property_records"),
                vehicle_id,
            )

        if isinstance(getattr(sim, "chunk_property_records", None), dict):
            for record_key, records in tuple(sim.chunk_property_records.items()):
                cleaned = _remove_property_record_from_rows(records, vehicle_id)
                if len(cleaned) != len(tuple(records or ())):
                    if cleaned:
                        sim.chunk_property_records[record_key] = cleaned
                    else:
                        sim.chunk_property_records.pop(record_key, None)
            sync_record = getattr(sim, "_sync_property_chunk_record", None)
            if callable(sync_record):
                sync_record(vehicle_id, prop)
        restored += 1
    return restored


def snapshot_simulation(sim):
    state = {}
    for key, value in sim.__dict__.items():
        if key in _EXCLUDED_SIM_STATE_KEYS:
            continue
        copied = _snapshot_value_or_skip(key, value)
        if copied is _SKIP_SNAPSHOT_VALUE:
            continue
        state[key] = copied
    log = state.get("log")
    if log is not None and hasattr(log, "default_tick_source"):
        # Runtime callbacks should be rebound on restore, not pickled into saves.
        log.default_tick_source = None
    return {
        "version": SAVE_VERSION,
        "sim_state": state,
    }


def _report_load_progress(callback, stage, completed, total, detail=""):
    if not callable(callback):
        return
    try:
        callback(str(stage), int(completed), int(total), str(detail or ""))
    except Exception:
        # Save integrity must not depend on a best-effort presentation callback.
        return


def restore_simulation(snapshot, *, progress_callback=None):
    _report_load_progress(progress_callback, "save_restore", 0, 6, "Validating saved city")
    if not isinstance(snapshot, dict):
        raise ValueError("save snapshot must be a dictionary")
    version = int(snapshot.get("version", 0) or 0)
    if version != SAVE_VERSION:
        raise ValueError(f"unsupported save version: {version}")

    state = snapshot.get("sim_state")
    if not isinstance(state, dict):
        raise ValueError("save snapshot missing simulation state")

    tilemap = state.get("tilemap")
    resolution_version = int(state.get("simulation_resolution_version", 1) or 1)
    active_chunk_radius = int(state.get("active_chunk_radius", 1))
    loaded_chunk_radius = int(state.get("loaded_chunk_radius", 2))
    if resolution_version < 2 and active_chunk_radius == 1 and loaded_chunk_radius == 2:
        # Version-one saves used the old ordinary 3x3-active / 5x5-loaded
        # policy.  Preserve explicit compact or custom radii, but let ordinary
        # worlds spend the new runtime headroom on a larger living area.
        active_chunk_radius = 2
        loaded_chunk_radius = 3

    _report_load_progress(progress_callback, "save_restore", 1, 6, "Allocating simulation")
    sim = Simulation(
        seed=state.get("seed", 1234),
        map_width=int(getattr(tilemap, "width", 64) or 64),
        map_height=int(getattr(tilemap, "height", 32) or 32),
        max_floors=int(getattr(tilemap, "max_floors", 1) or 1),
        chunk_size=int(state.get("chunk_size", 16) or 16),
        active_chunk_radius=active_chunk_radius,
        loaded_chunk_radius=loaded_chunk_radius,
    )

    for key, value in state.items():
        sim.__dict__[key] = value

    # Apply the resolved policy after restoring raw state so legacy radius
    # fields cannot overwrite the migration performed above.
    sim.active_chunk_radius = active_chunk_radius
    sim.loaded_chunk_radius = loaded_chunk_radius
    sim.simulation_resolution_version = 2

    sim.events = EventBus()
    sim.systems = []
    sim.mutators = []
    sim.appearance = AppearanceManager(sim)
    sim.running = True
    if hasattr(sim, "_bind_runtime_state"):
        sim._bind_runtime_state()

    _report_load_progress(progress_callback, "save_restore", 2, 6, "Rebinding saved state")
    if hasattr(sim, "tilemap") and hasattr(sim.tilemap, "tiles_by_floor"):
        sim.tilemap.tiles = sim.tilemap.tiles_by_floor.get(0, {})
    if not hasattr(sim, "chunk_saved_states"):
        sim.chunk_saved_states = {}
    if not hasattr(sim, "organization_index"):
        sim.organization_index = {}
    if not getattr(sim, "organization_index", None):
        rebuild_organization_index(sim)

    active_chunk_coord = _chunk_key(getattr(sim, "active_chunk_coord", None))
    if active_chunk_coord is not None and getattr(sim, "world", None) is not None:
        sim.active_chunk = sim.world.get_chunk(*active_chunk_coord)
    if getattr(sim, "world", None) is not None and hasattr(sim.world, "loaded_chunks"):
        sim.chunk_detail = {
            key: data.get("detail", "coarse")
            for key, data in getattr(sim.world, "loaded_chunks", {}).items()
            if isinstance(data, dict)
        }
    _restore_active_vehicle_properties(sim)
    if hasattr(sim, "rebuild_spatial_indexes"):
        sim.rebuild_spatial_indexes()
    _report_load_progress(progress_callback, "save_restore", 4, 6, "Restoring doors and organizations")
    if hasattr(sim, "reapply_door_states"):
        sim.reapply_door_states()
    refresh_loaded_organization_branch_briefings(
        sim,
        property_ids=tuple(getattr(sim, "properties", {}).keys()),
        reason="save_restore",
    )
    _report_load_progress(progress_callback, "save_restore", 6, 6, "Saved city restored")
    return sim


def save_character_run(sim, name, save_dir=SAVE_DIR):
    # Installation-wide registries keep their own files, but an ordinary
    # save/quit is still a natural durability boundary for batched signals.
    from game.fashion_market import flush_fashion_market

    name = normalize_character_name(name)
    if not name:
        raise ValueError("character name is required")

    if not isinstance(getattr(sim, "world_traits", None), dict):
        sim.world_traits = {}
    sim.character_name = name
    sim.world_traits["character_name"] = name
    flush_fashion_market(sim)

    payload = snapshot_simulation(sim)
    path = character_save_path(name, save_dir=save_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
    tmp_path.replace(path)
    return path


def load_character_run(name, save_dir=SAVE_DIR, delete_on_load=True, *, progress_callback=None):
    path = character_save_path(name, save_dir=save_dir)
    total_bytes = max(1, int(path.stat().st_size))
    payload_bytes = bytearray()
    _report_load_progress(progress_callback, "save_read", 0, total_bytes, "Reading saved city")
    with path.open("rb") as save_file:
        while True:
            chunk = save_file.read(1024 * 1024)
            if not chunk:
                break
            payload_bytes.extend(chunk)
            _report_load_progress(
                progress_callback,
                "save_read",
                len(payload_bytes),
                total_bytes,
                "Reading saved city",
            )
    _report_load_progress(progress_callback, "save_decode", 0, 1, "Opening saved city")
    payload = pickle.loads(bytes(payload_bytes))
    _report_load_progress(progress_callback, "save_decode", 1, 1, "Saved city opened")
    sim = restore_simulation(payload, progress_callback=progress_callback)
    if delete_on_load:
        delete_character_save(name, save_dir=save_dir)
    _report_load_progress(progress_callback, "save_ready", 1, 1, "Save restoration ready")
    return sim
