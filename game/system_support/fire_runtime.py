"""Shared spatial fire runtime helpers.

Canonical fire truth lives in sparse simulation-owned runtime state keyed by
world cell. Properties and chunks only derive summary state from these cells.
"""

from __future__ import annotations

import random

from engine.derived_facts import mark_derived_fact_changed
from engine.events import Event
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
    "terrain_tree_seedling",
    "terrain_tree_sapling",
    "terrain_reforest_spreader",
}
VEGETATION_COLORS = {
    "terrain_brush",
    "floor_wilderness",
    "floor_frontier",
}
VEGETATION_GLYPHS = {",", ";", "\""}
TREE_SEMANTICS = {"terrain_tree"}
REFORESTATION_SEMANTICS = {
    "terrain_tree_seedling",
    "terrain_tree_sapling",
    "terrain_reforest_spreader",
}
TREE_SEED_DELAY_TICKS = 6 * 600
TREE_SAPLING_DELAY_TICKS = 18 * 600
TREE_MATURITY_DELAY_TICKS = 48 * 600
TREE_SPREADER_DELAY_TICKS = 12 * 600
TREE_SPREADER_MAX_TILES = 3
TREE_SPREADER_MAX_CHECKS = 8
TREE_REFOREST_RETRY_TICKS = 600
_STATE_DICT_KEYS = (
    "chunk_index",
    "z_index",
    "light_revision_by_z",
    "property_index",
    "building_index",
    "frozen_boundaries",
    "environmental_ignition_days",
    "contact_cooldowns",
    "damage_marks",
    "spent_cells",
    "response_seed_ids",
    "environmental_candidate_cache",
    "reforestation",
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


def _overworld_terrain_for_cell(sim, key):
    if sim is None or key is None:
        return ""
    world = getattr(sim, "world", None)
    if world is None or not hasattr(world, "overworld_descriptor"):
        return ""
    try:
        cx, cy = sim.chunk_coords(int(key[0]), int(key[1]))
        descriptor = world.overworld_descriptor(int(cx), int(cy))
    except (AttributeError, TypeError, ValueError):
        return ""
    if not isinstance(descriptor, dict):
        return ""
    return _text(descriptor.get("terrain")).lower()


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
    elif (
        bool(state.get("_runtime_normalized"))
        and isinstance(state.get("z_index"), dict)
        and isinstance(state.get("light_revision_by_z"), dict)
    ):
        # All live mutation paths preserve the normalized containers. Rechecking
        # every index on every cell lookup turns a large due fire wave quadratic.
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

    # These sets are the cheap property-level working truth used by the fire
    # system between real cell-advance waves.  Rebuild them once when loading
    # old state instead of rediscovering them from every property index on
    # every simulation tick.
    derived_active_properties = {
        _text(cell.get("property_id"))
        for cell in normalized_cells.values()
        if _text(cell.get("property_id")) and _safe_int(cell.get("fire_intensity"), 0) > 0
    }
    derived_smoke_properties = {
        _text(cell.get("property_id"))
        for cell in normalized_cells.values()
        if _text(cell.get("property_id")) and _safe_int(cell.get("smoke_intensity"), 0) > 0
    }
    saved_active_properties = set(state.get("last_active_properties", ()) or ())
    saved_smoke_properties = set(state.get("last_smoke_properties", ()) or ())
    state["last_active_properties"] = saved_active_properties | derived_active_properties
    state["last_smoke_properties"] = saved_smoke_properties | derived_smoke_properties
    if (
        saved_active_properties - derived_active_properties
        or saved_smoke_properties - derived_smoke_properties
    ):
        state["fire_property_transition_dirty"] = True

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
    if normalized_cells and not state.get("z_index"):
        for coord in normalized_cells:
            _int_bucket(state["z_index"], coord[2]).add(coord)
    _sync_protected_chunks(sim, state=state)
    state.setdefault("fire_response_dirty", bool(normalized_cells))
    state.setdefault("fire_response_next_tick", 0)
    state["_runtime_normalized"] = True
    return state


def mark_fire_light_changed(sim, *, state=None, z=None):
    state = state if isinstance(state, dict) else fire_state(sim)
    if z is not None:
        z_key = _safe_int(z, 0)
        revisions = state.setdefault("light_revision_by_z", {})
        revisions[z_key] = _safe_int(revisions.get(z_key), 0) + 1
    return mark_derived_fact_changed(sim, "fire_light")


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
    # The due indexes are already maintained incrementally.  Recounting every
    # active fire cell here made a due wave quadratic because every advanced
    # cell schedules itself again.
    state["advance_due_signature"] = (len(state["advance_tick_by_coord"]), interval)
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
    signature = state.get("advance_due_signature")
    interval = signature[1] if isinstance(signature, (tuple, list)) and len(signature) >= 2 else 5
    state["advance_due_signature"] = (len(state.get("advance_tick_by_coord", {})), interval)
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
    state["z_index"] = {}
    state["property_index"] = {}
    state["building_index"] = {}
    for coord, cell in tuple(state.get("cells", {}).items()):
        chunk = _normalize_chunk_key(getattr(sim, "chunk_coords", lambda x, y: None)(coord[0], coord[1]))
        if chunk is not None:
            _set_bucket(state["chunk_index"], chunk).add(coord)
        _int_bucket(state["z_index"], coord[2]).add(coord)
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
    _int_bucket(state["z_index"], coord[2]).add(coord)
    property_id = _text(cell.get("property_id"))
    if property_id:
        _set_bucket(state["property_index"], property_id).add(coord)
    building_id = _text(cell.get("building_id"))
    if building_id:
        _set_bucket(state["building_index"], building_id).add(coord)
    if chunk is not None and _safe_int(cell.get("fire_intensity"), 0) > 0:
        state.setdefault("protected_chunks", set()).add(chunk)


def _refresh_protected_chunk(sim, chunk, *, state=None):
    if not isinstance(state, dict):
        state = fire_state(sim)
    chunk = _normalize_chunk_key(chunk)
    if chunk is None:
        return False
    cells = state.get("cells", {})
    active = any(
        _safe_int((cells.get(coord) or {}).get("fire_intensity"), 0) > 0
        for coord in tuple(state.get("chunk_index", {}).get(chunk, ()) or ())
    )
    protected = state.setdefault("protected_chunks", set())
    if active:
        protected.add(chunk)
    else:
        protected.discard(chunk)
    return active


def refresh_fire_protected_chunk(sim, chunk):
    """Refresh one changed chunk without rescanning the whole fire world."""

    return _refresh_protected_chunk(sim, chunk, state=fire_state(sim))


def _unindex_fire_cell(sim, coord, cell, *, sync_protected=True):
    state = fire_state(sim)
    chunk = _normalize_chunk_key(sim.chunk_coords(coord[0], coord[1]))
    if chunk is not None:
        bucket = _set_bucket(state["chunk_index"], chunk)
        bucket.discard(coord)
        if not bucket:
            state["chunk_index"].pop(chunk, None)
    z_bucket = _int_bucket(state["z_index"], coord[2])
    z_bucket.discard(coord)
    if not z_bucket:
        state["z_index"].pop(int(coord[2]), None)
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
    if chunk is not None and bool(sync_protected):
        _refresh_protected_chunk(sim, chunk, state=state)


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
    return set(fire_state(sim).get("protected_chunks", set()) or ())


def fire_cell_state(sim, x, y, z=0):
    key = _coord_key(x, y, z)
    if key is None:
        return None
    state = getattr(sim, "fire_state", None)
    cells = state.get("cells") if isinstance(state, dict) and bool(state.get("_runtime_normalized")) else None
    if not isinstance(cells, dict):
        cells = fire_state(sim).get("cells", {})
    cell = cells.get(key)
    return cell if isinstance(cell, dict) else None


def property_fire_cells(sim, property_id, *, include_smoke=False):
    """Return one property's live fire cells from the maintained sparse index."""

    property_id = _text(property_id)
    if not property_id:
        return ()
    state = fire_state(sim)
    cells = state.get("cells", {})
    rows = []
    for coord in tuple(state.get("property_index", {}).get(property_id, ()) or ()):
        cell = cells.get(coord)
        if not isinstance(cell, dict):
            continue
        fire_intensity = _safe_int(cell.get("fire_intensity"), 0)
        smoke_intensity = _safe_int(cell.get("smoke_intensity"), 0)
        if fire_intensity <= 0 and not (bool(include_smoke) and smoke_intensity > 0):
            continue
        rows.append(cell)
    rows.sort(key=lambda cell: (
        -_safe_int(cell.get("fire_intensity"), 0),
        -_safe_int(cell.get("smoke_intensity"), 0),
        _safe_int(cell.get("y"), 0),
        _safe_int(cell.get("x"), 0),
        _safe_int(cell.get("z"), 0),
    ))
    return tuple(rows)


def suppress_fire_cell(
    sim,
    x,
    y,
    z=0,
    *,
    amount=1,
    smoke_amount=0,
    source_eid=None,
    source_kind="response_worker",
):
    """Apply bounded external suppression to one canonical fire cell.

    Suppression is deliberately different from burning out: it does not mark
    fuel as spent or repair damage that the fire already caused.  The ordinary
    fire due queue continues to own smoke decay and any remaining flame.
    """

    key = _coord_key(x, y, z)
    if key is None:
        return {
            "ok": False,
            "reason": "invalid_coord",
            "fire_reduced": 0,
            "smoke_reduced": 0,
        }
    try:
        amount = max(0, int(amount))
    except (TypeError, ValueError):
        amount = 1
    try:
        smoke_amount = max(0, int(smoke_amount))
    except (TypeError, ValueError):
        smoke_amount = 0
    if amount <= 0 and smoke_amount <= 0:
        return {
            "ok": False,
            "reason": "no_suppression",
            "fire_reduced": 0,
            "smoke_reduced": 0,
        }

    state = fire_state(sim)
    cell = state.get("cells", {}).get(key)
    if not isinstance(cell, dict):
        return {
            "ok": False,
            "reason": "no_fire_cell",
            "fire_reduced": 0,
            "smoke_reduced": 0,
        }

    previous_fire = _safe_int(cell.get("fire_intensity"), 0)
    previous_smoke = _safe_int(cell.get("smoke_intensity"), 0)
    next_fire = max(0, previous_fire - amount)
    next_smoke = max(0, previous_smoke - smoke_amount)
    if next_fire == previous_fire and next_smoke == previous_smoke:
        return {
            "ok": False,
            "reason": "nothing_to_suppress",
            "fire_reduced": 0,
            "smoke_reduced": 0,
        }

    tick = _safe_int(getattr(sim, "tick", 0), 0)
    cell["fire_intensity"] = next_fire
    cell["smoke_intensity"] = next_smoke
    cell["burn_budget"] = max(0, _safe_int(cell.get("burn_budget"), 0) - max(0, amount))
    cell["last_suppressed_tick"] = tick
    cell["last_suppressed_by_eid"] = source_eid
    cell["last_suppression_kind"] = _text(source_kind).lower() or "response_worker"
    cell["suppression_total"] = max(0, _safe_int(cell.get("suppression_total"), 0)) + (
        previous_fire - next_fire
    )

    if next_fire != previous_fire:
        mark_fire_light_changed(sim, state=state, z=key[2])
    chunk = _normalize_chunk_key(sim.chunk_coords(key[0], key[1]))
    if next_fire <= 0 and next_smoke <= 0:
        remove_fire_cell(sim, key[0], key[1], key[2], sync_protected=True)
    elif chunk is not None:
        _refresh_protected_chunk(sim, chunk, state=state)

    state["fire_response_dirty"] = True
    state["fire_property_transition_dirty"] = True
    result = {
        "ok": True,
        "reason": "suppressed",
        "x": key[0],
        "y": key[1],
        "z": key[2],
        "property_id": _text(cell.get("property_id")),
        "building_id": _text(cell.get("building_id")),
        "fire_before": previous_fire,
        "fire_after": next_fire,
        "smoke_before": previous_smoke,
        "smoke_after": next_smoke,
        "fire_reduced": previous_fire - next_fire,
        "smoke_reduced": previous_smoke - next_smoke,
        "source_eid": source_eid,
        "source_kind": _text(source_kind).lower() or "response_worker",
    }
    sim.emit(Event("fire_suppressed", **result))
    return result


def remove_fire_cell(sim, x, y, z=0, *, sync_protected=True):
    key = _coord_key(x, y, z)
    if key is None:
        return False
    state = fire_state(sim)
    cell = state.get("cells", {}).pop(key, None)
    if not isinstance(cell, dict):
        return False
    if _safe_int(cell.get("fire_intensity"), 0) > 0:
        mark_fire_light_changed(sim, state=state, z=key[2])
    unschedule_fire_cell_advance(sim, key)
    _unindex_fire_cell(sim, key, cell, sync_protected=sync_protected)
    state.get("frozen_boundaries", {}).pop(key, None)
    state["fire_response_dirty"] = True
    state["fire_property_transition_dirty"] = True
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


def _fire_damage_record_at(sim, prop, key, *, records_cache=None):
    if not isinstance(prop, dict) or key is None:
        return None
    cache_key = id(prop)
    records = records_cache.get(cache_key) if isinstance(records_cache, dict) else None
    if records is None:
        records = tuple(property_damage_records(sim, prop))
        if isinstance(records_cache, dict):
            records_cache[cache_key] = records
    for record in records:
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
    tag_set = set(tags)
    tile = sim.tilemap.tile_at(key[0], key[1], key[2]) if hasattr(sim, "tilemap") else None
    tree_semantic = _text(getattr(tile, "semantic_id", "")).lower()
    if "vegetation" in tag_set or "brush" in tag_set or "tree" in tag_set:
        _mark_terrain_burned(sim, key, behavior=behavior)
    if "tree" in tag_set or tree_semantic in TREE_SEMANTICS:
        schedule_tree_reforestation(sim, key, tree_semantic=tree_semantic)
    elif tree_semantic in REFORESTATION_SEMANTICS:
        state.get("reforestation", {}).pop(key, None)
    return record


def _tree_seed_site_available(sim, key):
    if sim is None or key is None or not hasattr(sim, "tilemap"):
        return False
    tile = sim.tilemap.tile_at(key[0], key[1], key[2])
    if tile is None:
        return False
    semantic = _text(getattr(tile, "semantic_id", "")).lower()
    color = _text(getattr(tile, "color", "")).lower()
    if semantic != "terrain_burned" and color != "terrain_burned":
        return False
    if not bool(getattr(tile, "walkable", False)):
        return False
    if hasattr(sim, "structure_at") and sim.structure_at(key[0], key[1], key[2]) is not None:
        return False
    if hasattr(sim, "property_covering") and sim.property_covering(key[0], key[1], key[2]) is not None:
        return False
    return True


def _tree_seed_site_will_be_burned(sim, key):
    if _tree_seed_site_available(sim, key):
        return True
    state = fire_state(sim)
    return _safe_int((state.get("cells", {}).get(key) or {}).get("fire_intensity"), 0) > 0


def schedule_tree_reforestation(sim, key, *, tree_semantic="terrain_tree"):
    """Seed one successor tree and one bounded post-fire spreading line."""

    key = _coord_key(key[0], key[1], key[2]) if isinstance(key, (tuple, list)) and len(key) >= 3 else None
    if sim is None or key is None:
        return ()
    state = fire_state(sim)
    records = state.setdefault("reforestation", {})
    # Mature trees remain the existing generic tree terrain.  Visual variety is
    # coordinate-derived by the renderer rather than creating micro-species in
    # the simulation or save state.
    semantic = "terrain_tree"
    now = _safe_int(getattr(sim, "tick", 0), 0)
    neighbors = [
        (key[0] + dx, key[1] + dy, key[2])
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1))
    ]
    random.Random(
        f"{getattr(sim, 'seed', 0)}:tree-seed:{now}:{key[0]}:{key[1]}:{key[2]}"
    ).shuffle(neighbors)
    scheduled = []
    seed_specs = [(key, "tree")]
    spreader_site = next(
        (candidate for candidate in neighbors if _tree_seed_site_will_be_burned(sim, candidate)),
        None,
    )
    if spreader_site is not None:
        seed_specs.append((spreader_site, "spreader"))
    for candidate, seed_kind in seed_specs:
        if isinstance(records.get(candidate), dict):
            scheduled.append(candidate)
            continue
        germinate_tick = now + TREE_SEED_DELAY_TICKS
        records[candidate] = {
            "x": int(candidate[0]),
            "y": int(candidate[1]),
            "z": int(candidate[2]),
            "source_x": int(key[0]),
            "source_y": int(key[1]),
            "source_z": int(key[2]),
            "tree_semantic": semantic,
            "seed_kind": seed_kind,
            "spread_count": 0,
            "spread_checks": 0,
            "stage": "seed_bank",
            "seeded_tick": int(now),
            "next_tick": int(germinate_tick),
        }
        scheduled.append(candidate)
    if scheduled:
        state["reforestation_next_tick"] = min(
            _safe_int(state.get("reforestation_next_tick"), now + TREE_SEED_DELAY_TICKS),
            now + TREE_SEED_DELAY_TICKS,
        )
    return tuple(scheduled)


def _set_reforestation_tile(sim, key, *, glyph, color, semantic_id, walkable, transparent, effect):
    tile = sim.tilemap.tile_at(key[0], key[1], key[2])
    if tile is None:
        return False
    visibility_changed = bool(getattr(tile, "transparent", True)) != bool(transparent)
    sim.tilemap.set_tile_appearance(
        key[0],
        key[1],
        key[2],
        glyph=glyph,
        color=color,
        semantic_id=semantic_id,
        effects=(effect,),
    )
    tile.walkable = bool(walkable)
    tile.transparent = bool(transparent)
    if visibility_changed and hasattr(sim.tilemap, "mark_visibility_changed"):
        sim.tilemap.mark_visibility_changed(key[0], key[1], key[2])
    return True


def _reforestation_maturity_blocked(sim, key):
    if hasattr(sim, "structure_at") and sim.structure_at(key[0], key[1], key[2]) is not None:
        return True
    if hasattr(sim, "property_covering") and sim.property_covering(key[0], key[1], key[2]) is not None:
        return True
    if hasattr(sim, "ground_items_at") and sim.ground_items_at(key[0], key[1], key[2]):
        return True
    try:
        return bool(sim.tilemap.entities_at(key[0], key[1], key[2]))
    except Exception:
        return False


def advance_tree_reforestation(sim, *, current_tick=None):
    """Advance sparse post-fire tree seeds through brush, sapling, and tree."""

    state = fire_state(sim)
    records = state.setdefault("reforestation", {})
    if not records:
        state["reforestation_next_tick"] = 0
        return {"advanced": 0, "matured": 0}
    now = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, 0)
    if now < _safe_int(state.get("reforestation_next_tick"), 0):
        return {"advanced": 0, "matured": 0}

    loaded = getattr(getattr(sim, "world", None), "loaded_chunks", {})
    advanced = 0
    matured = 0
    for key, record in tuple(records.items()):
        if not isinstance(record, dict) or now < _safe_int(record.get("next_tick"), now):
            continue
        if isinstance(loaded, dict) and loaded and sim.chunk_coords(key[0], key[1]) not in loaded:
            record["next_tick"] = now + TREE_REFOREST_RETRY_TICKS
            continue
        if _safe_int((state.get("cells", {}).get(key) or {}).get("fire_intensity"), 0) > 0:
            record["next_tick"] = now + TREE_REFOREST_RETRY_TICKS
            continue
        stage = _text(record.get("stage")).lower() or "seed_bank"
        if stage == "seed_bank":
            if not _tree_seed_site_available(sim, key):
                records.pop(key, None)
                continue
            state.get("spent_cells", {}).pop(key, None)
            seed_kind = _text(record.get("seed_kind")).lower() or "tree"
            if seed_kind == "spreader":
                _set_reforestation_tile(
                    sim,
                    key,
                    glyph=",",
                    color="terrain_brush",
                    semantic_id="terrain_reforest_spreader",
                    walkable=True,
                    transparent=True,
                    effect="post_fire_pioneer",
                )
                record["stage"] = "spreader"
                record["next_tick"] = now + TREE_SPREADER_DELAY_TICKS
                advanced += 1
                continue
            _set_reforestation_tile(
                sim,
                key,
                glyph=",",
                color="terrain_brush",
                semantic_id="terrain_tree_seedling",
                walkable=True,
                transparent=True,
                effect="tree_seedling",
            )
            record["stage"] = "seedling"
            record["next_tick"] = now + TREE_SAPLING_DELAY_TICKS
            advanced += 1
            continue
        if stage == "spreader":
            spread_count = max(0, _safe_int(record.get("spread_count"), 0))
            spread_checks = max(0, _safe_int(record.get("spread_checks"), 0)) + 1
            record["spread_checks"] = int(spread_checks)
            if spread_count < TREE_SPREADER_MAX_TILES:
                candidates = [
                    (key[0] + dx, key[1] + dy, key[2])
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1))
                ]
                random.Random(
                    f"{getattr(sim, 'seed', 0)}:post-fire-spread:{spread_count}:{key[0]}:{key[1]}:{key[2]}"
                ).shuffle(candidates)
                child = next(
                    (
                        candidate
                        for candidate in candidates
                        if candidate not in records and _tree_seed_site_available(sim, candidate)
                    ),
                    None,
                )
                if child is not None:
                    state.get("spent_cells", {}).pop(child, None)
                    _set_reforestation_tile(
                        sim,
                        child,
                        glyph=",",
                        color="terrain_brush",
                        semantic_id="terrain_reforest_spreader",
                        walkable=True,
                        transparent=True,
                        effect="post_fire_pioneer",
                    )
                    spread_count += 1
                    record["spread_count"] = int(spread_count)
            if spread_count >= TREE_SPREADER_MAX_TILES or spread_checks >= TREE_SPREADER_MAX_CHECKS:
                records.pop(key, None)
            else:
                record["next_tick"] = now + TREE_SPREADER_DELAY_TICKS
            advanced += 1
            continue
        if stage == "seedling":
            _set_reforestation_tile(
                sim,
                key,
                glyph=",",
                color="terrain_brush",
                semantic_id="terrain_tree_sapling",
                walkable=True,
                transparent=True,
                effect="tree_sapling",
            )
            record["stage"] = "sapling"
            record["next_tick"] = now + TREE_MATURITY_DELAY_TICKS
            advanced += 1
            continue
        if _reforestation_maturity_blocked(sim, key):
            record["next_tick"] = now + TREE_REFOREST_RETRY_TICKS
            continue
        _set_reforestation_tile(
            sim,
            key,
            glyph="#",
            color="terrain_brush",
            semantic_id="terrain_tree",
            walkable=False,
            transparent=False,
            effect="mature_tree",
        )
        records.pop(key, None)
        advanced += 1
        matured += 1

    future = [
        _safe_int(record.get("next_tick"), now + TREE_REFOREST_RETRY_TICKS)
        for record in records.values()
        if isinstance(record, dict)
    ]
    state["reforestation_next_tick"] = min(future) if future else 0
    return {"advanced": int(advanced), "matured": int(matured)}


def _mark_terrain_burned(sim, key, *, behavior=None):
    if sim is None or key is None or not hasattr(sim, "tilemap"):
        return False
    tile = sim.tilemap.tile_at(key[0], key[1], key[2])
    if tile is None:
        return False
    if getattr(tile, "semantic_id", None) == "terrain_burned":
        return True
    if hasattr(tile, "set_appearance"):
        visibility_changed = not bool(getattr(tile, "transparent", True))
        sim.tilemap.set_tile_appearance(
            key[0],
            key[1],
            key[2],
            glyph=".",
            color="terrain_burned",
            semantic_id="terrain_burned",
            effects=tuple(dict.fromkeys(tuple(getattr(tile, "effects", ()) or ()) + ("scorched",))),
        )
        tile.walkable = True
        tile.transparent = True
        if visibility_changed and hasattr(sim.tilemap, "mark_visibility_changed"):
            sim.tilemap.mark_visibility_changed(key[0], key[1], key[2])
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


def fire_behavior_for_cell(sim, x, y, z=0, *, prop=None, property_damage_records_cache=None):
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
        spent_record = _fire_damage_record_at(
            sim,
            linked_prop,
            key,
            records_cache=property_damage_records_cache,
        ) or _fire_spent_record_at(sim, key)
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
    open_air = structure is None and linked_prop is None
    terrain = _overworld_terrain_for_cell(sim, key) if open_air else ""
    forest_floor_fallback = open_air and terrain == "forest" and glyph == "."
    forest_tree_fallback = open_air and terrain == "forest" and glyph == "#"
    wall_like = (
        semantic in WALL_SEMANTICS
        or glyph == "/"
        or (
            glyph == "#"
            and not forest_tree_fallback
            and (structure is not None or linked_prop is not None or semantic == "terrain_block")
        )
    )
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
    elif wall_like:
        burn_tier = "low"
        source_tags.update({"wall"})
    elif structure is not None and (semantic in FLOOR_SEMANTICS or bool(getattr(tile, "walkable", False))):
        burn_tier = "low"
        source_tags.update({"interior"})
    elif open_air and (
        semantic in TREE_SEMANTICS
        or forest_tree_fallback
    ):
        burn_tier = "low"
        source_tags.update({"vegetation", "tree", "open_air"})
    elif open_air and (
        semantic in VEGETATION_SEMANTICS
        or color in VEGETATION_COLORS
        or glyph in VEGETATION_GLYPHS
        or forest_floor_fallback
    ):
        burn_tier = "medium"
        source_tags.update({"vegetation", "brush", "open_air"})

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
    elif wall_like:
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
        if _safe_int(cell.get("fire_intensity"), 0) > 0:
            mark_fire_light_changed(sim, state=state, z=key[2])
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
        state["fire_response_dirty"] = True
        return cell

    previous_fire_intensity = _safe_int(existing.get("fire_intensity"), 0)
    existing["fire_intensity"] = max(_safe_int(existing.get("fire_intensity"), 0), _safe_int(fire_intensity, 0))
    existing["smoke_intensity"] = max(_safe_int(existing.get("smoke_intensity"), 0), _safe_int(smoke_intensity, 0))
    if _safe_int(existing.get("fire_intensity"), 0) != previous_fire_intensity:
        mark_fire_light_changed(sim, state=state, z=key[2])
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
    if previous_fire_intensity <= 0 < _safe_int(existing.get("fire_intensity"), 0):
        chunk = _normalize_chunk_key(sim.chunk_coords(key[0], key[1]))
        if chunk is not None:
            state.setdefault("protected_chunks", set()).add(chunk)
    state["fire_response_dirty"] = True
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
    "mark_fire_light_changed",
    "mark_chunk_environmental_ignition",
    "mark_fire_cell_spent",
    "note_frozen_fire_boundary",
    "pop_due_fire_cells",
    "property_fire_summary",
    "property_fire_cells",
    "rebuild_fire_advance_due_index",
    "remove_fire_cell",
    "schedule_fire_cell_advance",
    "ensure_fire_advance_due_index",
    "unschedule_fire_cell_advance",
    "suppress_fire_cell",
    "upsert_fire_cell",
]
