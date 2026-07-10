"""Shared spatial fire runtime helpers.

Canonical fire truth lives in sparse simulation-owned runtime state keyed by
world cell. Properties and chunks only derive summary state from these cells.
"""

from __future__ import annotations

from engine.tilemap import Tile

from game.property_runtime import (
    building_id_from_structure,
    property_aperture_at,
    property_covering,
    property_enclosing_structure,
    property_fixture_type,
    property_is_public,
    property_is_storefront,
    property_metadata,
)
from game.system_support.building_repair_runtime import property_damage_records


RISKY_ROOM_KINDS = {
    "boiler",
    "fuel_pad",
    "kitchen",
    "kitchenette",
    "power_room",
    "prep_kitchen",
    "service_bay",
}
RISKY_ARCHETYPES = {
    "boiler_room",
    "generator_room",
    "kitchen",
    "power_room",
    "service_station",
    "warehouse",
}
ELECTRICAL_FIXTURE_TYPES = {
    "transformer",
    "live_wire_hazard",
}
CAMPFIRE_FIXTURE_TYPES = {
    "campfire_ring",
}
FUEL_FIXTURE_TYPES = {
    "fuel_pump",
    "fuel_pad",
}
DOOR_APERTURE_KINDS = {
    "door",
    "side_door",
    "service_door",
    "employee_door",
}
WINDOW_APERTURE_KINDS = {
    "window",
    "skylight",
}
WALL_SEMANTICS = {"wall_building"}
FLOOR_SEMANTICS = {"floor_building_fill"}
DOOR_SEMANTICS = {"feature_door"}
WINDOW_SEMANTICS = {"feature_window"}
VEGETATION_SEMANTICS = {
    "terrain_brush",
    "floor_wilderness",
    "floor_frontier",
}
VEGETATION_COLORS = {
    "terrain_brush",
    "floor_wilderness",
    "floor_frontier",
}
VEGETATION_GLYPHS = {",", ";", "\""}
TREE_SEMANTICS = {"terrain_block"}
_STATE_DICT_KEYS = (
    "chunk_index",
    "property_index",
    "building_index",
    "frozen_boundaries",
    "environmental_ignition_days",
    "contact_cooldowns",
    "damage_marks",
    "spent_cells",
    "response_seed_ids",
    "environmental_candidate_cache",
)
_STATE_SET_KEYS = ("last_active_properties", "last_smoke_properties")

_BURN_TIER_PROFILES = {
    "none": {
        "can_ignite": False,
        "can_carry_fire": False,
        "can_carry_smoke": False,
        "spread_bias": 0.0,
        "fuel_strength": 0.0,
        "burn_budget": 0,
    },
    "low": {
        "can_ignite": True,
        "can_carry_fire": True,
        "can_carry_smoke": True,
        "spread_bias": 0.26,
        "fuel_strength": 0.34,
        "burn_budget": 3,
    },
    "spent": {
        "can_ignite": False,
        "can_carry_fire": False,
        "can_carry_smoke": True,
        "spread_bias": 0.0,
        "fuel_strength": 0.0,
        "burn_budget": 0,
    },
    "medium": {
        "can_ignite": True,
        "can_carry_fire": True,
        "can_carry_smoke": True,
        "spread_bias": 0.38,
        "fuel_strength": 0.5,
        "burn_budget": 4,
    },
    "high": {
        "can_ignite": True,
        "can_carry_fire": True,
        "can_carry_smoke": True,
        "spread_bias": 0.56,
        "fuel_strength": 0.72,
        "burn_budget": 5,
    },
    "extreme": {
        "can_ignite": True,
        "can_carry_fire": True,
        "can_carry_smoke": True,
        "spread_bias": 0.78,
        "fuel_strength": 0.96,
        "burn_budget": 6,
    },
}


def _text(value):
    return str(value or "").strip()


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


def _world_day(sim):
    clock = getattr(sim, "world_traits", {}).get("clock", {})
    try:
        ticks_per_hour = max(60, int(clock.get("ticks_per_hour", 600) or 600))
    except (TypeError, ValueError):
        ticks_per_hour = 600
    ticks_per_day = max(1, ticks_per_hour * 24)
    return max(0, int(getattr(sim, "tick", 0) or 0) // ticks_per_day)


def _normalize_chunk_key(chunk):
    if not isinstance(chunk, (tuple, list)) or len(chunk) < 2:
        return None
    try:
        return (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError):
        return None


def _coord_key(x, y, z=0):
    try:
        return (int(x), int(y), int(z))
    except (TypeError, ValueError):
        return None


def _set_bucket(bucket, key):
    if not isinstance(bucket, dict):
        return set()
    values = bucket.get(key)
    if isinstance(values, set):
        return values
    if isinstance(values, (list, tuple)):
        normalized = {
            coord
            for coord in values
            if isinstance(coord, tuple) and len(coord) >= 3
        }
    else:
        normalized = set()
    bucket[key] = normalized
    return normalized


def _int_bucket(bucket, key):
    if not isinstance(bucket, dict):
        return set()
    try:
        clean_key = int(key)
    except (TypeError, ValueError):
        clean_key = 0
    values = bucket.get(clean_key)
    if isinstance(values, set):
        return values
    if isinstance(values, (list, tuple)):
        normalized = {
            coord
            for coord in values
            if isinstance(coord, tuple) and len(coord) >= 3
        }
    else:
        normalized = set()
    bucket[clean_key] = normalized
    return normalized


def _normalize_advance_due(raw_due):
    if isinstance(raw_due, dict) and all(
        isinstance(tick, int)
        and isinstance(values, set)
        and all(isinstance(coord, tuple) and len(coord) >= 3 for coord in values)
        for tick, values in raw_due.items()
    ):
        return raw_due
    due = {}
    if not isinstance(raw_due, dict):
        return due
    for raw_tick, values in tuple(raw_due.items()):
        try:
            tick = int(raw_tick)
        except (TypeError, ValueError):
            continue
        bucket = set()
        for raw_coord in tuple(values or ()):
            if not isinstance(raw_coord, (tuple, list)) or len(raw_coord) < 3:
                continue
            coord = _coord_key(raw_coord[0], raw_coord[1], raw_coord[2])
            if coord is not None:
                bucket.add(coord)
        if bucket:
            due[tick] = bucket
    return due


def _normalize_advance_tick_by_coord(raw_index):
    if isinstance(raw_index, dict) and all(
        isinstance(coord, tuple) and len(coord) >= 3 and isinstance(tick, int)
        for coord, tick in raw_index.items()
    ):
        return raw_index
    index = {}
    if not isinstance(raw_index, dict):
        return index
    for raw_coord, raw_tick in tuple(raw_index.items()):
        if not isinstance(raw_coord, (tuple, list)) or len(raw_coord) < 3:
            continue
        coord = _coord_key(raw_coord[0], raw_coord[1], raw_coord[2])
        if coord is None:
            continue
        try:
            index[coord] = int(raw_tick)
        except (TypeError, ValueError):
            continue
    return index


def _fire_state_runtime_ready(state):
    if not isinstance(state, dict) or not bool(state.get("_runtime_normalized")):
        return False
    if not isinstance(state.get("cells"), dict):
        return False
    for name in _STATE_DICT_KEYS:
        if not isinstance(state.get(name), dict):
            return False
    if not isinstance(state.get("advance_due"), dict):
        return False
    if not isinstance(state.get("advance_tick_by_coord"), dict):
        return False
    if not isinstance(state.get("protected_chunks"), set):
        return False
    for name in _STATE_SET_KEYS:
        if not isinstance(state.get(name), set):
            return False
    return True


def fire_state(sim):
    state = getattr(sim, "fire_state", None)
    if not isinstance(state, dict):
        state = {}
        sim.fire_state = state
    elif _fire_state_runtime_ready(state):
        return state

    cells = state.get("cells")
    if not isinstance(cells, dict):
        cells = {}
        state["cells"] = cells

    for name in _STATE_DICT_KEYS:
        if not isinstance(state.get(name), dict):
            state[name] = {}
    state["advance_due"] = _normalize_advance_due(state.get("advance_due"))
    state["advance_tick_by_coord"] = _normalize_advance_tick_by_coord(state.get("advance_tick_by_coord"))

    protected = state.get("protected_chunks")
    if not isinstance(protected, set):
        if isinstance(protected, (list, tuple)):
            state["protected_chunks"] = {
                key
                for key in (_normalize_chunk_key(entry) for entry in protected)
                if key is not None
            }
        else:
            state["protected_chunks"] = set()
    for name in _STATE_SET_KEYS:
        values = state.get(name)
        if isinstance(values, set):
            continue
        if isinstance(values, (list, tuple)):
            state[name] = {
                _text(value)
                for value in values
                if _text(value)
            }
        else:
            state[name] = set()

    normalized_cells = {}
    for raw_key, raw_value in tuple(cells.items()):
        if not isinstance(raw_value, dict):
            continue
        if isinstance(raw_key, tuple) and len(raw_key) >= 3:
            key = _coord_key(raw_key[0], raw_key[1], raw_key[2])
        else:
            key = None
        if key is None:
            continue
        cell = dict(raw_value)
        cell.setdefault("x", int(key[0]))
        cell.setdefault("y", int(key[1]))
        cell.setdefault("z", int(key[2]))
        cell["fire_intensity"] = max(0, _safe_int(cell.get("fire_intensity"), 0))
        cell["smoke_intensity"] = max(0, _safe_int(cell.get("smoke_intensity"), 0))
        cell["started_tick"] = _safe_int(cell.get("started_tick"), 0)
        cell["last_advanced_tick"] = _safe_int(cell.get("last_advanced_tick"), -10_000)
        cell["burn_budget"] = max(0, _safe_int(cell.get("burn_budget"), 0))
        cell["source_kind"] = _text(cell.get("source_kind")).lower()
        cell["source_property_id"] = _text(cell.get("source_property_id")) or None
        cell["property_id"] = _text(cell.get("property_id")) or None
        cell["building_id"] = _text(cell.get("building_id")) or None
        cell["burn_tier"] = _text(cell.get("burn_tier")).lower() or "none"
        normalized_cells[key] = cell
    state["cells"] = normalized_cells

    if not any(state.get(name) for name in ("chunk_index", "property_index", "building_index")) and normalized_cells:
        state["chunk_index"] = {}
        state["property_index"] = {}
        state["building_index"] = {}
        for coord, cell in tuple(normalized_cells.items()):
            chunk = _normalize_chunk_key(getattr(sim, "chunk_coords", lambda x, y: None)(coord[0], coord[1]))
            if chunk is not None:
                _set_bucket(state["chunk_index"], chunk).add(coord)
            property_id = _text(cell.get("property_id"))
            if property_id:
                _set_bucket(state["property_index"], property_id).add(coord)
            building_id = _text(cell.get("building_id"))
            if building_id:
                _set_bucket(state["building_index"], building_id).add(coord)
    _sync_protected_chunks(sim, state=state)
    state["_runtime_normalized"] = True
    return state


def rebuild_fire_advance_due_index(sim, *, advance_interval=5):
    state = fire_state(sim)
    try:
        interval = max(1, int(advance_interval))
    except (TypeError, ValueError):
        interval = 5
    due = {}
    by_coord = {}
    active_count = 0
    for coord, cell in tuple(state.get("cells", {}).items()):
        if not isinstance(cell, dict):
            continue
        if _safe_int(cell.get("fire_intensity"), 0) <= 0 and _safe_int(cell.get("smoke_intensity"), 0) <= 0:
            continue
        active_count += 1
        next_tick = _safe_int(cell.get("last_advanced_tick"), _safe_int(getattr(sim, "tick", 0), 0)) + interval
        _int_bucket(due, next_tick).add(coord)
        by_coord[coord] = int(next_tick)
    state["advance_due"] = due
    state["advance_tick_by_coord"] = by_coord
    state["advance_due_signature"] = (active_count, interval)
    state["advance_due_dirty"] = False
    return state


def ensure_fire_advance_due_index(sim, *, advance_interval=5):
    state = fire_state(sim)
    try:
        interval = max(1, int(advance_interval))
    except (TypeError, ValueError):
        interval = 5
    by_coord = state.get("advance_tick_by_coord", {})
    due = state.get("advance_due", {})
    if (
        bool(state.get("advance_due_dirty"))
        or state.get("advance_due_signature") is None
        or not isinstance(by_coord, dict)
        or not isinstance(due, dict)
        or (
            not by_coord
            and any(
                isinstance(cell, dict)
                and (
                    _safe_int(cell.get("fire_intensity"), 0) > 0
                    or _safe_int(cell.get("smoke_intensity"), 0) > 0
                )
                for cell in tuple(state.get("cells", {}).values())
            )
        )
    ):
        return rebuild_fire_advance_due_index(sim, advance_interval=interval)
    return state


def schedule_fire_cell_advance(sim, coord, *, due_tick=None, advance_interval=5):
    key = _coord_key(*(coord or (None, None, None)))
    if key is None:
        return None
    state = fire_state(sim)
    cell = state.get("cells", {}).get(key)
    if not isinstance(cell, dict):
        return None
    if _safe_int(cell.get("fire_intensity"), 0) <= 0 and _safe_int(cell.get("smoke_intensity"), 0) <= 0:
        unschedule_fire_cell_advance(sim, key)
        return None
    try:
        interval = max(1, int(advance_interval))
    except (TypeError, ValueError):
        interval = 5
    if due_tick is None:
        due_tick = _safe_int(cell.get("last_advanced_tick"), _safe_int(getattr(sim, "tick", 0), 0)) + interval
    due_tick = int(max(0, _safe_int(due_tick, 0)))
    old_tick = state.setdefault("advance_tick_by_coord", {}).get(key)
    if old_tick is not None and int(old_tick) != due_tick:
        old_bucket = _int_bucket(state.setdefault("advance_due", {}), old_tick)
        old_bucket.discard(key)
        if not old_bucket:
            state.setdefault("advance_due", {}).pop(int(old_tick), None)
    _int_bucket(state.setdefault("advance_due", {}), due_tick).add(key)
    state.setdefault("advance_tick_by_coord", {})[key] = due_tick
    active_count = sum(
        1
        for cell in tuple(state.get("cells", {}).values())
        if isinstance(cell, dict)
        and (
            _safe_int(cell.get("fire_intensity"), 0) > 0
            or _safe_int(cell.get("smoke_intensity"), 0) > 0
        )
    )
    state["advance_due_signature"] = (active_count, interval)
    return due_tick


def unschedule_fire_cell_advance(sim, coord):
    key = _coord_key(*(coord or (None, None, None)))
    if key is None:
        return False
    state = fire_state(sim)
    old_tick = state.setdefault("advance_tick_by_coord", {}).pop(key, None)
    if old_tick is None:
        return False
    bucket = _int_bucket(state.setdefault("advance_due", {}), old_tick)
    bucket.discard(key)
    if not bucket:
        state.setdefault("advance_due", {}).pop(int(old_tick), None)
    state["advance_due_dirty"] = True
    return True


def pop_due_fire_cells(sim, *, current_tick=None, advance_interval=5):
    if current_tick is None:
        current_tick = _safe_int(getattr(sim, "tick", 0), 0)
    state = ensure_fire_advance_due_index(sim, advance_interval=advance_interval)
    due = state.setdefault("advance_due", {})
    by_coord = state.setdefault("advance_tick_by_coord", {})
    ready = []
    for due_tick in sorted(tick for tick in due.keys() if int(tick) <= int(current_tick)):
        bucket = due.pop(due_tick, set())
        for coord in tuple(bucket or ()):
            if by_coord.get(coord) == due_tick:
                by_coord.pop(coord, None)
            ready.append(coord)
    return tuple(ready)


def _rebuild_fire_indexes(sim):
    state = fire_state(sim)
    state["chunk_index"] = {}
    state["property_index"] = {}
    state["building_index"] = {}
    for coord, cell in tuple(state.get("cells", {}).items()):
        chunk = _normalize_chunk_key(getattr(sim, "chunk_coords", lambda x, y: None)(coord[0], coord[1]))
        if chunk is not None:
            _set_bucket(state["chunk_index"], chunk).add(coord)
        property_id = _text(cell.get("property_id"))
        if property_id:
            _set_bucket(state["property_index"], property_id).add(coord)
        building_id = _text(cell.get("building_id"))
        if building_id:
            _set_bucket(state["building_index"], building_id).add(coord)
    _sync_protected_chunks(sim, state=state)
    return state


def _index_fire_cell(sim, coord, cell):
    state = fire_state(sim)
    chunk = _normalize_chunk_key(sim.chunk_coords(coord[0], coord[1]))
    if chunk is not None:
        _set_bucket(state["chunk_index"], chunk).add(coord)
    property_id = _text(cell.get("property_id"))
    if property_id:
        _set_bucket(state["property_index"], property_id).add(coord)
    building_id = _text(cell.get("building_id"))
    if building_id:
        _set_bucket(state["building_index"], building_id).add(coord)
    _sync_protected_chunks(sim, state=state)


def _unindex_fire_cell(sim, coord, cell):
    state = fire_state(sim)
    chunk = _normalize_chunk_key(sim.chunk_coords(coord[0], coord[1]))
    if chunk is not None:
        bucket = _set_bucket(state["chunk_index"], chunk)
        bucket.discard(coord)
        if not bucket:
            state["chunk_index"].pop(chunk, None)
    property_id = _text(cell.get("property_id"))
    if property_id:
        bucket = _set_bucket(state["property_index"], property_id)
        bucket.discard(coord)
        if not bucket:
            state["property_index"].pop(property_id, None)
    building_id = _text(cell.get("building_id"))
    if building_id:
        bucket = _set_bucket(state["building_index"], building_id)
        bucket.discard(coord)
        if not bucket:
            state["building_index"].pop(building_id, None)
    _sync_protected_chunks(sim, state=state)


def _sync_protected_chunks(sim, *, state=None):
    if not isinstance(state, dict):
        state = getattr(sim, "fire_state", None)
        if not isinstance(state, dict):
            state = fire_state(sim)
    protected = set()
    chunk_index = state.get("chunk_index", {})
    cells = state.get("cells", {})
    for raw_chunk, coords in tuple(chunk_index.items()):
        chunk = _normalize_chunk_key(raw_chunk)
        if chunk is None:
            continue
        for coord in tuple(coords or ()):
            cell = cells.get(coord)
            if not isinstance(cell, dict):
                continue
            if _safe_int(cell.get("fire_intensity"), 0) > 0:
                protected.add(chunk)
                break
    state["protected_chunks"] = protected
    return protected


def fire_protected_chunks(sim):
    return set(_sync_protected_chunks(sim, state=fire_state(sim)))


def fire_cell_state(sim, x, y, z=0):
    key = _coord_key(x, y, z)
    if key is None:
        return None
    cell = fire_state(sim).get("cells", {}).get(key)
    return cell if isinstance(cell, dict) else None


def remove_fire_cell(sim, x, y, z=0):
    key = _coord_key(x, y, z)
    if key is None:
        return False
    state = fire_state(sim)
    cell = state.get("cells", {}).pop(key, None)
    if not isinstance(cell, dict):
        return False
    unschedule_fire_cell_advance(sim, key)
    _unindex_fire_cell(sim, key, cell)
    state.get("frozen_boundaries", {}).pop(key, None)
    return True


def _structure_aperture_kind(sim, structure, x, y, z):
    apertures = structure.get("apertures") if isinstance(structure, dict) else None
    if isinstance(apertures, (list, tuple)):
        for aperture in apertures:
            if not isinstance(aperture, dict):
                continue
            try:
                ax = int(aperture.get("x"))
                ay = int(aperture.get("y"))
                az = int(aperture.get("z", z))
            except (TypeError, ValueError):
                continue
            if (ax, ay, az) == (int(x), int(y), int(z)):
                return _text(aperture.get("kind")).lower()
    return ""


def _active_fire_at(sim, key):
    state = getattr(sim, "fire_state", None)
    if not isinstance(state, dict):
        return False
    cell = (state.get("cells") or {}).get(key)
    if not isinstance(cell, dict):
        return False
    return _safe_int(cell.get("fire_intensity"), 0) > 0


def _fire_damage_record_at(sim, prop, key):
    if not isinstance(prop, dict) or key is None:
        return None
    for record in property_damage_records(sim, prop):
        if _text(record.get("cause")).lower() != "fire":
            continue
        try:
            record_key = (int(record.get("x")), int(record.get("y")), int(record.get("z", 0)))
        except (TypeError, ValueError):
            continue
        if record_key == key:
            return record
    return None


def _fire_spent_record_at(sim, key):
    if key is None:
        return None
    state = getattr(sim, "fire_state", None)
    if not isinstance(state, dict):
        return None
    record = (state.get("spent_cells") or {}).get(key)
    return record if isinstance(record, dict) else None


def _behavior_should_leave_spent_fuel(behavior):
    if not isinstance(behavior, dict):
        return False
    burn_tier = _text(behavior.get("burn_tier")).lower()
    if burn_tier in {"", "none", "spent"}:
        return False
    tags = {
        _text(tag).lower()
        for tag in tuple(behavior.get("source_tags", ()) or ())
        if _text(tag)
    }
    if tags.intersection({"campfire"}):
        return False
    if tags.intersection({"open_air"}) and not tags.intersection({"vegetation", "brush", "tree"}):
        return False
    if _text(behavior.get("structural_damage_kind")).lower() in {"door", "window", "wall"}:
        return False
    if tags.intersection({"vegetation", "brush", "tree"}):
        return True
    return bool(
        behavior.get("building_id")
        or behavior.get("property_id")
        or behavior.get("room_kind")
        or behavior.get("archetype")
        or tags.intersection({"interior", "risky_room", "fuel", "electrical", "hazard"})
    )


def mark_fire_cell_spent(sim, x, y, z=0, *, cell=None, behavior=None, reason="burned_out"):
    key = _coord_key(x, y, z)
    if sim is None or key is None:
        return None
    behavior = dict(behavior or {}) if isinstance(behavior, dict) else fire_behavior_for_cell(sim, key[0], key[1], key[2])
    if not _behavior_should_leave_spent_fuel(behavior):
        return None
    state = fire_state(sim)
    existing = dict(state.get("spent_cells", {}).get(key, {}) or {})
    cell = dict(cell or {}) if isinstance(cell, dict) else {}
    tags = tuple(
        _text(tag).lower()
        for tag in tuple(behavior.get("source_tags", ()) or ())
        if _text(tag)
    )
    record = {
        "x": int(key[0]),
        "y": int(key[1]),
        "z": int(key[2]),
        "property_id": _text(cell.get("property_id")) or _text(behavior.get("property_id")) or existing.get("property_id"),
        "building_id": _text(cell.get("building_id")) or _text(behavior.get("building_id")) or existing.get("building_id"),
        "property_name": _text(behavior.get("property_name")) or existing.get("property_name"),
        "burn_tier": _text(cell.get("burn_tier")) or _text(behavior.get("burn_tier")) or existing.get("burn_tier"),
        "room_kind": _text(behavior.get("room_kind")) or existing.get("room_kind"),
        "archetype": _text(behavior.get("archetype")) or existing.get("archetype"),
        "fixture_type": _text(behavior.get("fixture_type")) or existing.get("fixture_type"),
        "hazard_profile": _text(behavior.get("hazard_profile")) or existing.get("hazard_profile"),
        "aperture_kind": _text(behavior.get("aperture_kind")) or existing.get("aperture_kind"),
        "source_tags": tags or tuple(existing.get("source_tags", ()) or ()),
        "reason": _text(reason).lower() or "burned_out",
        "spent_tick": _safe_int(getattr(sim, "tick", 0), 0),
    }
    state.get("spent_cells", {})[key] = record
    if "vegetation" in set(tags) or "brush" in set(tags) or "tree" in set(tags):
        _mark_terrain_burned(sim, key, behavior=behavior)
    return record


def _mark_terrain_burned(sim, key, *, behavior=None):
    if sim is None or key is None or not hasattr(sim, "tilemap"):
        return False
    tile = sim.tilemap.tile_at(key[0], key[1], key[2])
    if tile is None:
        return False
    if getattr(tile, "semantic_id", None) == "terrain_burned":
        return True
    if hasattr(tile, "set_appearance"):
        tile.set_appearance(
            glyph=".",
            color="terrain_burned",
            semantic_id="terrain_burned",
            effects=tuple(dict.fromkeys(tuple(getattr(tile, "effects", ()) or ()) + ("scorched",))),
        )
        tile.walkable = True
        tile.transparent = True
    else:
        sim.tilemap.set_tile(
            key[0],
            key[1],
            Tile(
                walkable=True,
                transparent=True,
                glyph=".",
                color="terrain_burned",
                semantic_id="terrain_burned",
                effects=("scorched",),
            ),
            z=key[2],
        )
    return True


def fire_behavior_for_cell(sim, x, y, z=0, *, prop=None):
    key = _coord_key(x, y, z)
    if sim is None or key is None:
        return dict(_BURN_TIER_PROFILES["none"], burn_tier="none")

    tile = sim.tilemap.tile_at(key[0], key[1], key[2]) if hasattr(sim, "tilemap") else None
    structure = sim.structure_at(key[0], key[1], key[2]) if hasattr(sim, "structure_at") else None
    prop_here = sim.property_at(key[0], key[1], key[2]) if hasattr(sim, "property_at") else None
    prop_cover = prop if isinstance(prop, dict) else property_covering(sim, key[0], key[1], key[2])
    enclosing = property_enclosing_structure(sim, key[0], key[1], key[2], prop=prop_cover)
    linked_prop = prop_here if isinstance(prop_here, dict) else prop_cover if isinstance(prop_cover, dict) else enclosing
    linked_metadata = property_metadata(linked_prop)
    fixture_metadata = property_metadata(prop_here)

    semantic = _text(getattr(tile, "semantic_id", "")).lower()
    glyph = _text(getattr(tile, "glyph", ""))
    color = _text(getattr(tile, "color", "")).lower()
    room_kind = _text((structure or {}).get("room_kind")).lower()
    archetype = (
        _text(linked_metadata.get("archetype")).lower()
        or _text((structure or {}).get("archetype")).lower()
    )
    fixture_type = _text(fixture_metadata.get("fixture_type", fixture_metadata.get("archetype"))).lower()
    hazard_profile = _text(fixture_metadata.get("hazard_profile")).lower()
    building_id = _text((structure or {}).get("building_id") or linked_metadata.get("building_id"))
    property_id = _text((linked_prop or {}).get("id"))
    aperture_kind = (
        _text((sim.door_state_at(key[0], key[1], key[2]) or {}).get("kind")).lower()
        or _text((property_aperture_at(linked_prop, key[0], key[1], key[2]) or {}).get("kind")).lower()
        or _structure_aperture_kind(sim, structure, key[0], key[1], key[2])
    )

    spent_record = None
    if not _active_fire_at(sim, key):
        spent_record = _fire_damage_record_at(sim, linked_prop, key) or _fire_spent_record_at(sim, key)
    if spent_record is not None:
        structural_damage_kind = _text(spent_record.get("repair_kind")).lower()
        spent_tags = tuple(_text(tag).lower() for tag in tuple(spent_record.get("source_tags", ()) or ()) if _text(tag))
        profile = dict(_BURN_TIER_PROFILES["spent"])
        profile.update({
            "burn_tier": "spent",
            "property_id": property_id or _text(spent_record.get("property_id")) or None,
            "building_id": building_id or _text(spent_record.get("building_id")) or None,
            "property_name": _text((linked_prop or {}).get("name")) or _text(spent_record.get("property_name")) or None,
            "property_public": bool(linked_prop and (property_is_public(linked_prop) or property_is_storefront(linked_prop))),
            "room_kind": room_kind or _text(spent_record.get("room_kind")) or None,
            "archetype": archetype or _text(spent_record.get("archetype")) or None,
            "fixture_type": fixture_type or _text(spent_record.get("fixture_type")) or None,
            "hazard_profile": hazard_profile or _text(spent_record.get("hazard_profile")) or None,
            "aperture_kind": aperture_kind or _text(spent_record.get("aperture_kind")) or None,
            "structural_damage_kind": structural_damage_kind,
            "source_tags": tuple(dict.fromkeys(("fire_spent",) + spent_tags + (("structural_damage",) if structural_damage_kind else ("burned_out",)))),
        })
        return profile

    burn_tier = "none"
    source_tags = set()
    if fixture_type in ELECTRICAL_FIXTURE_TYPES or hazard_profile == "live_wire":
        burn_tier = "extreme"
        source_tags.update({"electrical", "hazard"})
    elif fixture_type in FUEL_FIXTURE_TYPES:
        burn_tier = "extreme"
        source_tags.update({"fuel", "hazard"})
    elif fixture_type in CAMPFIRE_FIXTURE_TYPES:
        burn_tier = "high"
        source_tags.update({"campfire", "open_air"})
    elif room_kind in RISKY_ROOM_KINDS or archetype in RISKY_ARCHETYPES:
        burn_tier = "high"
        source_tags.update({"risky_room"})
    elif aperture_kind in WINDOW_APERTURE_KINDS:
        burn_tier = "medium"
        source_tags.update({"aperture", "window"})
    elif aperture_kind in DOOR_APERTURE_KINDS or semantic in DOOR_SEMANTICS or glyph in {"+", "'"}:
        burn_tier = "medium"
        source_tags.update({"aperture", "door"})
    elif semantic in WALL_SEMANTICS or glyph in {"#", "/"}:
        burn_tier = "low"
        source_tags.update({"wall"})
    elif structure is not None and (semantic in FLOOR_SEMANTICS or bool(getattr(tile, "walkable", False))):
        burn_tier = "low"
        source_tags.update({"interior"})
    elif structure is None and linked_prop is None and (
        semantic in VEGETATION_SEMANTICS
        or color in VEGETATION_COLORS
        or glyph in VEGETATION_GLYPHS
    ):
        burn_tier = "medium"
        source_tags.update({"vegetation", "brush", "open_air"})
    elif structure is None and linked_prop is None and (
        semantic in TREE_SEMANTICS
        or (glyph == "#" and color == "terrain_block")
    ):
        burn_tier = "low"
        source_tags.update({"vegetation", "tree", "open_air"})

    profile = dict(_BURN_TIER_PROFILES.get(burn_tier, _BURN_TIER_PROFILES["none"]))
    profile.update({
        "burn_tier": burn_tier,
        "property_id": property_id or None,
        "building_id": building_id or None,
        "property_name": _text((linked_prop or {}).get("name")) or None,
        "property_public": bool(linked_prop and (property_is_public(linked_prop) or property_is_storefront(linked_prop))),
        "room_kind": room_kind or None,
        "archetype": archetype or None,
        "fixture_type": fixture_type or None,
        "hazard_profile": hazard_profile or None,
        "aperture_kind": aperture_kind or None,
        "structural_damage_kind": "",
        "source_tags": tuple(sorted(source_tags)),
    })

    if burn_tier == "none":
        return profile

    if aperture_kind in WINDOW_APERTURE_KINDS or semantic in WINDOW_SEMANTICS or glyph == '"':
        profile["structural_damage_kind"] = "window"
    elif aperture_kind in DOOR_APERTURE_KINDS or semantic in DOOR_SEMANTICS or glyph in {"+", "'"}:
        profile["structural_damage_kind"] = "door"
    elif semantic in WALL_SEMANTICS or glyph in {"#", "/"}:
        profile["structural_damage_kind"] = "wall"

    if burn_tier in {"high", "extreme"} and profile["structural_damage_kind"] in {"door", "window"}:
        profile["spread_bias"] = min(0.95, _safe_float(profile["spread_bias"], 0.0) + 0.06)
    return profile


def upsert_fire_cell(
    sim,
    x,
    y,
    z=0,
    *,
    fire_intensity=0,
    smoke_intensity=0,
    source_kind="",
    source_eid=None,
    source_property_id=None,
    property_id=None,
    building_id=None,
    burn_tier="",
    burn_budget=None,
    started_tick=None,
    last_advanced_tick=None,
    sync_protected=True,
    behavior=None,
    advance_interval=None,
    aerosol_status="",
    aerosol_duration=0,
    aerosol_modifiers=None,
    aerosol_exposure_cooldown=0,
    aerosol_label="",
    aerosol_source_item_id="",
    aerosol_source_item_name="",
):
    key = _coord_key(x, y, z)
    if key is None:
        return None
    state = fire_state(sim)
    cells = state.get("cells", {})
    existing = cells.get(key)
    behavior = dict(behavior or {}) if isinstance(behavior, dict) else fire_behavior_for_cell(sim, key[0], key[1], key[2])
    if not bool(behavior.get("can_ignite")) and fire_intensity > 0:
        return None

    if existing is None:
        cell = {
            "x": int(key[0]),
            "y": int(key[1]),
            "z": int(key[2]),
            "fire_intensity": max(0, _safe_int(fire_intensity, 0)),
            "smoke_intensity": max(0, _safe_int(smoke_intensity, 0)),
            "started_tick": _safe_int(started_tick, _safe_int(getattr(sim, "tick", 0), 0)),
            "last_advanced_tick": _safe_int(last_advanced_tick, _safe_int(getattr(sim, "tick", 0), 0)),
            "source_kind": _text(source_kind).lower(),
            "source_eid": source_eid,
            "source_property_id": _text(source_property_id) or behavior.get("property_id"),
            "property_id": _text(property_id) or behavior.get("property_id"),
            "building_id": _text(building_id) or behavior.get("building_id"),
            "burn_tier": _text(burn_tier).lower() or behavior.get("burn_tier") or "none",
            "burn_budget": max(
                0,
                _safe_int(
                    burn_budget,
                    _BURN_TIER_PROFILES.get(
                        _text(burn_tier).lower() or behavior.get("burn_tier") or "none",
                        _BURN_TIER_PROFILES["none"],
                    ).get("burn_budget", 0),
                ),
            ),
        }
        aerosol_status = _text(aerosol_status).lower()
        if aerosol_status and _safe_int(aerosol_duration, 0) > 0:
            cell.update({
                "aerosol_status": aerosol_status,
                "aerosol_duration": max(1, _safe_int(aerosol_duration, 1)),
                "aerosol_modifiers": dict(aerosol_modifiers or {}) if isinstance(aerosol_modifiers, dict) else {},
                "aerosol_exposure_cooldown": max(1, _safe_int(aerosol_exposure_cooldown, 6)),
                "aerosol_label": _text(aerosol_label) or aerosol_status.replace("_", " "),
                "aerosol_source_item_id": _text(aerosol_source_item_id),
                "aerosol_source_item_name": _text(aerosol_source_item_name),
            })
        cells[key] = cell
        _index_fire_cell(sim, key, cell)
        if advance_interval is not None:
            schedule_fire_cell_advance(sim, key, advance_interval=advance_interval)
        else:
            state["advance_due_dirty"] = True
        tracked_property_id = _text(cell.get("property_id"))
        if tracked_property_id:
            if _safe_int(cell.get("fire_intensity"), 0) > 0:
                state.get("last_active_properties", set()).add(tracked_property_id)
            if _safe_int(cell.get("smoke_intensity"), 0) > 0:
                state.get("last_smoke_properties", set()).add(tracked_property_id)
        return cell

    existing["fire_intensity"] = max(_safe_int(existing.get("fire_intensity"), 0), _safe_int(fire_intensity, 0))
    existing["smoke_intensity"] = max(_safe_int(existing.get("smoke_intensity"), 0), _safe_int(smoke_intensity, 0))
    existing["source_kind"] = _text(source_kind).lower() or _text(existing.get("source_kind")).lower()
    existing["source_eid"] = source_eid if source_eid is not None else existing.get("source_eid")
    existing["source_property_id"] = _text(source_property_id) or existing.get("source_property_id") or behavior.get("property_id")
    existing["property_id"] = _text(property_id) or existing.get("property_id") or behavior.get("property_id")
    existing["building_id"] = _text(building_id) or existing.get("building_id") or behavior.get("building_id")
    existing["burn_tier"] = _text(burn_tier).lower() or _text(existing.get("burn_tier")).lower() or behavior.get("burn_tier") or "none"
    existing["burn_budget"] = max(_safe_int(existing.get("burn_budget"), 0), _safe_int(burn_budget, existing.get("burn_budget", 0)))
    aerosol_status = _text(aerosol_status).lower()
    if aerosol_status and _safe_int(aerosol_duration, 0) > 0:
        existing["aerosol_status"] = aerosol_status
        existing["aerosol_duration"] = max(_safe_int(existing.get("aerosol_duration"), 0), _safe_int(aerosol_duration, 1))
        existing["aerosol_modifiers"] = dict(aerosol_modifiers or {}) if isinstance(aerosol_modifiers, dict) else {}
        existing["aerosol_exposure_cooldown"] = max(1, _safe_int(aerosol_exposure_cooldown, existing.get("aerosol_exposure_cooldown", 6)))
        existing["aerosol_label"] = _text(aerosol_label) or existing.get("aerosol_label") or aerosol_status.replace("_", " ")
        existing["aerosol_source_item_id"] = _text(aerosol_source_item_id) or existing.get("aerosol_source_item_id", "")
        existing["aerosol_source_item_name"] = _text(aerosol_source_item_name) or existing.get("aerosol_source_item_name", "")
    if started_tick is not None:
        existing["started_tick"] = min(_safe_int(existing.get("started_tick"), started_tick), _safe_int(started_tick, 0))
    if last_advanced_tick is not None:
        existing["last_advanced_tick"] = min(
            _safe_int(existing.get("last_advanced_tick"), last_advanced_tick),
            _safe_int(last_advanced_tick, 0),
        )
    if advance_interval is not None:
        schedule_fire_cell_advance(sim, key, advance_interval=advance_interval)
    elif _safe_int(existing.get("fire_intensity"), 0) > 0 or _safe_int(existing.get("smoke_intensity"), 0) > 0:
        state["advance_due_dirty"] = True
    tracked_property_id = _text(existing.get("property_id"))
    if tracked_property_id:
        if _safe_int(existing.get("fire_intensity"), 0) > 0:
            state.get("last_active_properties", set()).add(tracked_property_id)
        if _safe_int(existing.get("smoke_intensity"), 0) > 0:
            state.get("last_smoke_properties", set()).add(tracked_property_id)
    if bool(sync_protected):
        _sync_protected_chunks(sim, state=state)
    return existing


def active_fire_cells_near(sim, x, y, z=0, *, radius=4, include_smoke=False):
    try:
        ox = int(x)
        oy = int(y)
        oz = int(z)
    except (TypeError, ValueError):
        return ()
    rows = []
    for coord, cell in tuple(fire_state(sim).get("cells", {}).items()):
        if coord[2] != oz:
            continue
        fire_here = _safe_int(cell.get("fire_intensity"), 0) > 0
        smoke_here = _safe_int(cell.get("smoke_intensity"), 0) > 0
        if not fire_here and not (include_smoke and smoke_here):
            continue
        distance = abs(int(coord[0]) - ox) + abs(int(coord[1]) - oy)
        if distance > int(radius):
            continue
        rows.append((distance, coord, cell))
    rows.sort(key=lambda row: (int(row[0]), row[1][1], row[1][0], row[1][2]))
    return tuple(row[2] for row in rows)


def property_fire_summary(sim, prop):
    if not isinstance(prop, dict):
        return {
            "active": False,
            "active_cells": 0,
            "smoke_cells": 0,
            "max_intensity": 0,
            "property_id": "",
            "building_id": "",
            "chunk": None,
            "public_frontage": False,
            "anchor": None,
        }

    state = fire_state(sim)
    property_id = _text(prop.get("id"))
    building_id = _text(property_metadata(prop).get("building_id"))
    coords = set(_set_bucket(state.get("property_index", {}), property_id))
    if building_id:
        coords.update(_set_bucket(state.get("building_index", {}), building_id))
    cells = []
    max_intensity = 0
    smoke_cells = 0
    active_cells = 0
    for coord in coords:
        cell = state.get("cells", {}).get(coord)
        if not isinstance(cell, dict):
            continue
        cells.append(cell)
        fire_intensity = _safe_int(cell.get("fire_intensity"), 0)
        smoke_intensity = _safe_int(cell.get("smoke_intensity"), 0)
        if fire_intensity > 0:
            active_cells += 1
            max_intensity = max(max_intensity, fire_intensity)
        if smoke_intensity > 0:
            smoke_cells += 1
    anchor = None
    if cells:
        cells.sort(key=lambda row: (_safe_int(row.get("y"), 0), _safe_int(row.get("x"), 0), _safe_int(row.get("z"), 0)))
        first = cells[0]
        anchor = (_safe_int(first.get("x"), 0), _safe_int(first.get("y"), 0), _safe_int(first.get("z"), 0))
    else:
        try:
            anchor = (int(prop.get("x", 0)), int(prop.get("y", 0)), int(prop.get("z", 0)))
        except (TypeError, ValueError):
            anchor = None
    return {
        "active": bool(active_cells),
        "active_cells": int(active_cells),
        "smoke_cells": int(smoke_cells),
        "max_intensity": int(max_intensity),
        "property_id": property_id,
        "property_name": _text(prop.get("name")),
        "building_id": building_id,
        "chunk": _normalize_chunk_key(sim.chunk_coords(anchor[0], anchor[1])) if anchor is not None else None,
        "public_frontage": bool(property_is_public(prop) or property_is_storefront(prop)),
        "anchor": anchor,
    }


def chunk_fire_summary(sim, chunk_coord):
    chunk = _normalize_chunk_key(chunk_coord)
    if chunk is None:
        return {
            "chunk": None,
            "active": False,
            "active_cells": 0,
            "smoke_cells": 0,
            "max_intensity": 0,
        }
    coords = tuple(_set_bucket(fire_state(sim).get("chunk_index", {}), chunk))
    active_cells = 0
    smoke_cells = 0
    max_intensity = 0
    for coord in coords:
        cell = fire_state(sim).get("cells", {}).get(coord)
        if not isinstance(cell, dict):
            continue
        fire_intensity = _safe_int(cell.get("fire_intensity"), 0)
        smoke_intensity = _safe_int(cell.get("smoke_intensity"), 0)
        if fire_intensity > 0:
            active_cells += 1
            max_intensity = max(max_intensity, fire_intensity)
        if smoke_intensity > 0:
            smoke_cells += 1
    return {
        "chunk": chunk,
        "active": bool(active_cells),
        "active_cells": int(active_cells),
        "smoke_cells": int(smoke_cells),
        "max_intensity": int(max_intensity),
    }


def note_frozen_fire_boundary(sim, target_coord, *, from_coord=None, source_kind="", pressure=1):
    target = _coord_key(*(target_coord or (None, None, None)))
    if target is None:
        return None
    state = fire_state(sim)
    record = dict(state.get("frozen_boundaries", {}).get(target, {}) or {})
    if from_coord is not None:
        record["from_coord"] = _coord_key(*(from_coord or (None, None, None)))
    record["source_kind"] = _text(source_kind).lower() or _text(record.get("source_kind")).lower()
    record["pressure"] = max(_safe_int(record.get("pressure"), 0), _safe_int(pressure, 0))
    record["target_coord"] = target
    record["target_chunk"] = _normalize_chunk_key(sim.chunk_coords(target[0], target[1]))
    record["recorded_tick"] = _safe_int(getattr(sim, "tick", 0), 0)
    state["frozen_boundaries"][target] = record
    return record


def clear_frozen_fire_boundary(sim, target_coord):
    target = _coord_key(*(target_coord or (None, None, None)))
    if target is None:
        return None
    return fire_state(sim).get("frozen_boundaries", {}).pop(target, None)


def chunk_environmental_ignition_day(sim, chunk_coord):
    chunk = _normalize_chunk_key(chunk_coord)
    if chunk is None:
        return None
    return fire_state(sim).get("environmental_ignition_days", {}).get(chunk)


def mark_chunk_environmental_ignition(sim, chunk_coord, *, day=None):
    chunk = _normalize_chunk_key(chunk_coord)
    if chunk is None:
        return None
    if day is None:
        day = _world_day(sim)
    fire_state(sim).get("environmental_ignition_days", {})[chunk] = int(day)
    return int(day)


def fire_runtime_day(sim):
    return _world_day(sim)


__all__ = [
    "CAMPFIRE_FIXTURE_TYPES",
    "DOOR_APERTURE_KINDS",
    "ELECTRICAL_FIXTURE_TYPES",
    "FUEL_FIXTURE_TYPES",
    "RISKY_ARCHETYPES",
    "RISKY_ROOM_KINDS",
    "WINDOW_APERTURE_KINDS",
    "active_fire_cells_near",
    "chunk_environmental_ignition_day",
    "chunk_fire_summary",
    "clear_frozen_fire_boundary",
    "fire_behavior_for_cell",
    "fire_cell_state",
    "fire_protected_chunks",
    "fire_runtime_day",
    "fire_state",
    "mark_chunk_environmental_ignition",
    "mark_fire_cell_spent",
    "note_frozen_fire_boundary",
    "pop_due_fire_cells",
    "property_fire_summary",
    "rebuild_fire_advance_due_index",
    "remove_fire_cell",
    "schedule_fire_cell_advance",
    "ensure_fire_advance_due_index",
    "unschedule_fire_cell_advance",
    "upsert_fire_cell",
]
