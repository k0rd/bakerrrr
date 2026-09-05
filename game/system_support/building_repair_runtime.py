"""Shared contractor and building-repair helpers.

This seam keeps structural damage tracking and contractor-facing repair helpers
out of the monolith and the UI systems. It intentionally focuses on:

- recording structural building damage when windows, walls, or doors are forced
- inferring pre-existing damage from the live tilemap for older saves
- quoting and restoring damaged owned buildings through a single helper API
"""

from __future__ import annotations

from engine.events import Event
from engine.tilemap import Tile
from game.components import PlayerAssets
from game.property_access import property_apertures
from game.system_support.intrusion_runtime import _is_operable_door_aperture, _is_window_aperture


BUILDING_REPAIR_BASE_COSTS = {
    "door": 34,
    "wall": 42,
    "window": 24,
}

_FIRE_DAMAGE_RECORD_INDEX_ATTR = "_building_fire_damage_record_index"


def _text(value):
    return str(value or "").strip()


def _int_or(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _property_metadata(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _footprint_excluded_cells(prop):
    metadata = _property_metadata(prop)
    raw = metadata.get("footprint_excluded_cells")
    cells = set()
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return frozenset()
    for entry in raw:
        if isinstance(entry, dict):
            try:
                cells.add((int(entry.get("x")), int(entry.get("y"))))
            except (TypeError, ValueError):
                continue
        elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
            try:
                cells.add((int(entry[0]), int(entry[1])))
            except (TypeError, ValueError):
                continue
    return frozenset(cells)


def _stored_damage_state(prop, *, create=False):
    metadata = _property_metadata(prop)
    state = metadata.get("building_damage")
    if not isinstance(state, dict):
        if not create:
            return None
        state = {}
        metadata["building_damage"] = state
    records = state.get("records")
    if not isinstance(records, list):
        records = []
        state["records"] = records
    return state


def _normalize_repair_kind(kind="", aperture_kind=""):
    kind = _text(kind).lower()
    aperture_kind = _text(aperture_kind).lower()
    if kind in {"wall", "breach"}:
        return "wall"
    if kind in {"door", "service_door", "side_door", "employee_door"}:
        return "door"
    if kind in {"window", "skylight"}:
        return "window"
    if _is_window_aperture(aperture_kind):
        return "window"
    if _is_operable_door_aperture(aperture_kind):
        return "door"
    return "wall"


def _record_key(record):
    return (
        _int_or(record.get("x"), default=0),
        _int_or(record.get("y"), default=0),
        _int_or(record.get("z"), default=0),
    )


def _clean_damage_record(record, *, default_kind="", default_aperture_kind=""):
    if not isinstance(record, dict):
        return None
    try:
        x = int(record.get("x"))
        y = int(record.get("y"))
        z = int(record.get("z", 0))
    except (TypeError, ValueError):
        return None
    aperture_kind = _text(record.get("aperture_kind", default_aperture_kind)).lower()
    repair_kind = _normalize_repair_kind(
        record.get("repair_kind", default_kind),
        aperture_kind=aperture_kind,
    )
    return {
        "x": int(x),
        "y": int(y),
        "z": int(z),
        "repair_kind": repair_kind,
        "aperture_kind": aperture_kind,
        "cause": _text(record.get("cause")).lower(),
        "offender_eid": _int_or(record.get("offender_eid"), default=0) or None,
        "damage_tick": _int_or(record.get("damage_tick"), default=-10_000),
    }


def _fire_damage_record_index(sim, *, create=False):
    if sim is None:
        return None
    index = getattr(sim, _FIRE_DAMAGE_RECORD_INDEX_ATTR, None)
    if not isinstance(index, dict) and create:
        index = {}
        setattr(sim, _FIRE_DAMAGE_RECORD_INDEX_ATTR, index)
    return index if isinstance(index, dict) else None


def _explicit_damage_records(prop):
    state = _stored_damage_state(prop, create=False)
    records = state.get("records") if isinstance(state, dict) else None
    return records if isinstance(records, list) else None


def index_property_fire_damage_records(sim, prop):
    """Rebuild one building's explicit fire-damage coordinate index."""

    if sim is None or not isinstance(prop, dict) or _text(prop.get("kind")).lower() != "building":
        return {}
    records = _explicit_damage_records(prop)
    by_coord = {}
    for raw_record in tuple(records or ()):
        clean = _clean_damage_record(raw_record)
        if clean is None or _text(clean.get("cause")).lower() != "fire":
            continue
        by_coord[_record_key(clean)] = clean
    index = _fire_damage_record_index(sim, create=True)
    index[id(prop)] = {
        "property": prop,
        "by_coord": by_coord,
    }
    return by_coord


def rebuild_fire_damage_record_index(sim):
    """Rebuild the derived explicit-fire index after construction or restore."""

    if sim is None:
        return {}
    setattr(sim, _FIRE_DAMAGE_RECORD_INDEX_ATTR, {})
    for prop in tuple(getattr(sim, "properties", {}).values()):
        if isinstance(prop, dict) and _text(prop.get("kind")).lower() == "building":
            index_property_fire_damage_records(sim, prop)
    return getattr(sim, _FIRE_DAMAGE_RECORD_INDEX_ATTR)


def forget_property_fire_damage_records(sim, prop):
    """Drop one property's derived fire-damage entry when it leaves runtime."""

    index = _fire_damage_record_index(sim, create=False)
    if not isinstance(index, dict) or not isinstance(prop, dict):
        return False
    key = id(prop)
    entry = index.get(key)
    if isinstance(entry, dict) and entry.get("property") is not prop:
        return False
    return index.pop(key, None) is not None


def fire_damage_record_at(sim, prop, x, y, z=0):
    """Return explicit fire damage at one coordinate without inferred scans."""

    if sim is None or not isinstance(prop, dict) or _text(prop.get("kind")).lower() != "building":
        return None
    try:
        coord = int(x), int(y), int(z)
    except (TypeError, ValueError):
        return None
    index = _fire_damage_record_index(sim, create=True)
    entry = index.get(id(prop))
    if (
        not isinstance(entry, dict)
        or entry.get("property") is not prop
        or not isinstance(entry.get("by_coord"), dict)
    ):
        by_coord = index_property_fire_damage_records(sim, prop)
    else:
        by_coord = entry["by_coord"]
    record = by_coord.get(coord)
    return record if isinstance(record, dict) else None


def _note_damage_record_added(sim, prop, record):
    index = _fire_damage_record_index(sim, create=True)
    entry = index.get(id(prop))
    if (
        not isinstance(entry, dict)
        or entry.get("property") is not prop
        or not isinstance(entry.get("by_coord"), dict)
    ):
        index_property_fire_damage_records(sim, prop)
        return
    if _text(record.get("cause")).lower() == "fire":
        entry["by_coord"][_record_key(record)] = record


def _note_damage_records_removed(sim, prop, removed_keys):
    index = _fire_damage_record_index(sim, create=True)
    entry = index.get(id(prop))
    if (
        not isinstance(entry, dict)
        or entry.get("property") is not prop
        or not isinstance(entry.get("by_coord"), dict)
    ):
        index_property_fire_damage_records(sim, prop)
        return
    for record_key in tuple(removed_keys or ()):
        entry["by_coord"].pop(record_key, None)


def damage_record_repair_cost(prop, record):
    clean = _clean_damage_record(record)
    if clean is None:
        return 0
    repair_kind = _normalize_repair_kind(
        clean.get("repair_kind"),
        aperture_kind=clean.get("aperture_kind"),
    )
    base_cost = int(BUILDING_REPAIR_BASE_COSTS.get(repair_kind, BUILDING_REPAIR_BASE_COSTS["wall"]))
    purchase_cost = max(80, _int_or(_property_metadata(prop).get("purchase_cost"), default=150))
    complexity_mult = 1.0 + min(0.45, max(0.0, float(purchase_cost) / 1000.0))
    return max(0, int(round(float(base_cost) * complexity_mult)))


def record_building_damage(sim, prop, x, y, z=0, *, kind="", aperture_kind="", cause="", offender_eid=None, damage_tick=None):
    if not isinstance(prop, dict) or _text(prop.get("kind")).lower() != "building":
        return None
    clean = _clean_damage_record(
        {
            "x": x,
            "y": y,
            "z": z,
            "repair_kind": kind,
            "aperture_kind": aperture_kind,
            "cause": cause,
            "offender_eid": offender_eid,
            "damage_tick": _int_or(damage_tick, default=_int_or(getattr(sim, "tick", 0), default=0)),
        },
        default_kind=kind,
        default_aperture_kind=aperture_kind,
    )
    if clean is None:
        return None
    state = _stored_damage_state(prop, create=True)
    previous_records = state.get("records")
    records = list(previous_records or ())
    key = _record_key(clean)
    for index, existing in enumerate(records):
        normalized = _clean_damage_record(existing)
        if normalized is None or _record_key(normalized) != key:
            continue
        return normalized
    records.append(clean)
    state["records"] = records
    _note_damage_record_added(sim, prop, clean)
    return clean


def _iter_boundary_cells(prop):
    metadata = _property_metadata(prop)
    footprint = metadata.get("footprint")
    if not isinstance(footprint, dict):
        return ()
    try:
        left = int(footprint.get("left"))
        right = int(footprint.get("right"))
        top = int(footprint.get("top"))
        bottom = int(footprint.get("bottom"))
        base_z = int(prop.get("z", 0))
        floors = max(1, int(metadata.get("floors", 1)))
    except (TypeError, ValueError):
        return ()
    excluded = _footprint_excluded_cells(prop)
    cells = []
    for z in range(base_z, base_z + floors):
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                if (x, y) in excluded:
                    continue
                if x in {left, right} or y in {top, bottom}:
                    cells.append((int(x), int(y), int(z)))
    return tuple(cells)


def _inferred_damage_records(sim, prop):
    if sim is None or not isinstance(prop, dict) or _text(prop.get("kind")).lower() != "building":
        return ()

    inferred = []
    seen = set()
    aperture_keys = set()
    for aperture in property_apertures(prop):
        try:
            ax = int(aperture.get("x"))
            ay = int(aperture.get("y"))
            az = int(aperture.get("z", prop.get("z", 0)))
        except (TypeError, ValueError):
            continue
        key = (ax, ay, az)
        aperture_keys.add(key)
        tile = sim.tilemap.tile_at(ax, ay, az)
        kind = _text(aperture.get("kind", "door")).lower() or "door"
        if _is_window_aperture(kind):
            damaged = tile is None or bool(getattr(tile, "walkable", False)) or str(getattr(tile, "glyph", "")) != '"'
            if damaged and key not in seen:
                seen.add(key)
                inferred.append({
                    "x": ax,
                    "y": ay,
                    "z": az,
                    "repair_kind": "window",
                    "aperture_kind": kind,
                    "cause": "inferred",
                })
            continue
        if _is_operable_door_aperture(kind):
            damaged = tile is not None and str(getattr(tile, "glyph", "")) == "/"
            if damaged and key not in seen:
                seen.add(key)
                inferred.append({
                    "x": ax,
                    "y": ay,
                    "z": az,
                    "repair_kind": "door",
                    "aperture_kind": kind,
                    "cause": "inferred",
                })

    for x, y, z in _iter_boundary_cells(prop):
        key = (int(x), int(y), int(z))
        if key in aperture_keys or key in seen:
            continue
        tile = sim.tilemap.tile_at(x, y, z)
        if tile is None:
            continue
        if bool(getattr(tile, "walkable", False)) or str(getattr(tile, "glyph", "")) == "/":
            seen.add(key)
            inferred.append({
                "x": int(x),
                "y": int(y),
                "z": int(z),
                "repair_kind": "wall",
                "aperture_kind": "",
                "cause": "inferred",
            })
    return tuple(inferred)


def property_damage_records(sim, prop, *, offender_eid=None, damage_tick=None):
    if not isinstance(prop, dict) or _text(prop.get("kind")).lower() != "building":
        return ()
    merged = {}
    state = _stored_damage_state(prop, create=False)
    if isinstance(state, dict):
        for raw_record in list(state.get("records", ()) or ()):
            clean = _clean_damage_record(raw_record)
            if clean is None:
                continue
            merged[_record_key(clean)] = clean
    for raw_record in _inferred_damage_records(sim, prop):
        clean = _clean_damage_record(raw_record)
        if clean is None:
            continue
        merged.setdefault(_record_key(clean), clean)
    rows = []
    wanted_offender = _int_or(offender_eid, default=0) if offender_eid is not None else None
    wanted_tick = _int_or(damage_tick, default=-10_000) if damage_tick is not None else None
    for key in sorted(merged.keys(), key=lambda row: (row[2], row[1], row[0])):
        clean = merged[key]
        if wanted_offender is not None and _int_or(clean.get("offender_eid"), default=0) != wanted_offender:
            continue
        if wanted_tick is not None and _int_or(clean.get("damage_tick"), default=-10_000) != wanted_tick:
            continue
        rows.append(clean)
    return tuple(rows)


def property_damage_summary(sim, prop, *, offender_eid=None, damage_tick=None):
    records = tuple(property_damage_records(sim, prop, offender_eid=offender_eid, damage_tick=damage_tick))
    counts = {"window": 0, "door": 0, "wall": 0}
    total_cost = 0
    for record in records:
        repair_kind = _normalize_repair_kind(
            record.get("repair_kind"),
            aperture_kind=record.get("aperture_kind"),
        )
        counts[repair_kind] = counts.get(repair_kind, 0) + 1
        total_cost += int(damage_record_repair_cost(prop, record))

    base_cost = 0
    for repair_kind, count in counts.items():
        base_cost += int(BUILDING_REPAIR_BASE_COSTS.get(repair_kind, BUILDING_REPAIR_BASE_COSTS["wall"])) * int(count)
    purchase_cost = max(80, _int_or(_property_metadata(prop).get("purchase_cost"), default=150))
    complexity_mult = 1.0 + min(0.45, max(0.0, float(purchase_cost) / 1000.0))
    return {
        "records": records,
        "damage_count": len(records),
        "window_count": int(counts.get("window", 0)),
        "door_count": int(counts.get("door", 0)),
        "wall_count": int(counts.get("wall", 0)),
        "base_cost": int(base_cost),
        "cost": max(0, int(total_cost)),
        "complexity_mult": float(round(complexity_mult, 2)),
    }


def property_needs_building_repair(sim, prop):
    return int(property_damage_summary(sim, prop).get("damage_count", 0) or 0) > 0


def owned_building_properties(sim, owner_eid):
    if sim is None or owner_eid is None:
        return ()
    owned_ids = set()
    assets = sim.ecs.get(PlayerAssets).get(owner_eid) if hasattr(sim, "ecs") else None
    if assets is not None:
        owned_ids.update(str(pid).strip() for pid in tuple(getattr(assets, "owned_property_ids", ()) or ()) if str(pid).strip())
    rows = []
    seen = set()
    for prop in getattr(sim, "properties", {}).values():
        if not isinstance(prop, dict) or _text(prop.get("kind")).lower() != "building":
            continue
        prop_id = _text(prop.get("id"))
        if prop_id in seen:
            continue
        owner_matches = False
        try:
            owner_matches = int(prop.get("owner_eid") or 0) == int(owner_eid)
        except (TypeError, ValueError):
            owner_matches = prop.get("owner_eid") == owner_eid
        if not owner_matches and prop_id not in owned_ids:
            continue
        seen.add(prop_id)
        rows.append(prop)
    rows.sort(key=lambda prop: (_text(prop.get("name", prop.get("id"))).lower(), _text(prop.get("id")).lower()))
    return tuple(rows)


def owned_repairable_buildings(sim, owner_eid):
    rows = []
    for prop in owned_building_properties(sim, owner_eid):
        summary = property_damage_summary(sim, prop)
        if int(summary.get("damage_count", 0) or 0) <= 0:
            continue
        rows.append({
            "prop": prop,
            "summary": summary,
        })
    rows.sort(
        key=lambda row: (
            -int((row.get("summary") or {}).get("damage_count", 0) or 0),
            _text((row.get("prop") or {}).get("name", (row.get("prop") or {}).get("id"))).lower(),
        )
    )
    return tuple(rows)


def _restore_window_tile(sim, x, y, z):
    sim.tilemap.set_tile(
        int(x),
        int(y),
        Tile(
            walkable=False,
            transparent=True,
            glyph='"',
            color="feature_window",
            semantic_id="feature_window",
        ),
        z=int(z),
    )


def _restore_door_tile(sim, prop, x, y, z, aperture_kind="door"):
    kind = _text(aperture_kind).lower() or "door"
    ordinary = kind == "door"
    sim.set_door_state(
        int(x),
        int(y),
        int(z),
        open=False,
        kind=kind,
        ordinary=ordinary,
        property_id=prop.get("id") if isinstance(prop, dict) else None,
        broken=False,
    )
    if not sim.apply_door_state(int(x), int(y), int(z)):
        sim.tilemap.set_tile(
            int(x),
            int(y),
            Tile(
                walkable=False,
                transparent=False,
                glyph="+",
                color="feature_door",
                semantic_id="feature_door",
            ),
            z=int(z),
        )


def _restore_wall_tile(sim, x, y, z):
    sim.tilemap.set_tile(
        int(x),
        int(y),
        Tile(
            walkable=False,
            transparent=False,
            glyph="#",
            color="building_edge",
            semantic_id="wall_building",
        ),
        z=int(z),
    )


def _restore_damage_record(sim, prop, record):
    """Restore one recorded surface and reconcile its durability state.

    The tile and durability stores are both canonical consumers of structural
    damage.  Repairing only the tile leaves a visually intact surface that the
    damage runtime still considers broken, so every repair lane comes through
    this helper.
    """

    x = _int_or(record.get("x"), default=0)
    y = _int_or(record.get("y"), default=0)
    z = _int_or(record.get("z"), default=0)
    repair_kind = _normalize_repair_kind(
        record.get("repair_kind"),
        aperture_kind=record.get("aperture_kind"),
    )
    if repair_kind == "window":
        _restore_window_tile(sim, x, y, z)
    elif repair_kind == "door":
        _restore_door_tile(sim, prop, x, y, z, aperture_kind=record.get("aperture_kind", "door"))
    elif repair_kind == "wall":
        _restore_wall_tile(sim, x, y, z)
    else:
        return ""

    # Local import avoids a module cycle: structural damage records breaks
    # through this module, while repair must reconcile that same state.
    try:
        from game.system_support.structure_damage_runtime import structural_surface_state

        surface = structural_surface_state(sim, prop, x, y, z, kind=repair_kind, create=False)
        if isinstance(surface, dict):
            maximum = max(1, _int_or(surface.get("max_hp"), default=1))
            surface["hp"] = maximum
            surface["broken"] = False
            surface["repaired_tick"] = _int_or(getattr(sim, "tick", 0), default=0)
            surface.pop("broken_tick", None)
    except (ImportError, AttributeError):
        pass
    return repair_kind


def repair_building_damage(sim, prop):
    summary = property_damage_summary(sim, prop)
    records = tuple(summary.get("records", ()) or ())
    if not records:
        return {
            **summary,
            "restored_count": 0,
        }
    for record in records:
        _restore_damage_record(sim, prop, record)

    state = _stored_damage_state(prop, create=True)
    state["records"] = []
    _note_damage_records_removed(
        sim,
        prop,
        {_record_key(record) for record in records},
    )
    return {
        **summary,
        "restored_count": len(records),
    }


def _quiet_maintenance_record_allowed(record):
    if not isinstance(record, dict):
        return False
    repair_kind = _normalize_repair_kind(
        record.get("repair_kind"),
        aperture_kind=record.get("aperture_kind"),
    )
    if repair_kind == "wall":
        return False
    if _int_or(record.get("offender_eid"), default=0):
        return False
    cause = _text(record.get("cause")).lower()
    if cause in {
        "attack",
        "breach",
        "explosion",
        "fire",
        "forced_entry",
        "ramming",
        "sabotage",
        "shooting",
        "vehicle_collision",
    }:
        return False
    return repair_kind in {"window", "door"}


def quiet_maintenance_cleanup(sim, prop, *, max_records=1, source_kind="maintenance_loop", emit_event=True):
    """Let an anchored maintenance scene clean tiny concrete damage only.

    This intentionally avoids full contractor repair semantics. It is for the
    little world-texture cases where a live worker/service cart plausibly fixes
    a loose door or broken pane. Wall damage, offender-linked damage, and
    sabotage-like causes stay on the stronger repair/restitution paths.
    """

    if sim is None or not isinstance(prop, dict) or _text(prop.get("kind")).lower() != "building":
        return {
            "ok": False,
            "reason": "invalid_property",
            "restored_count": 0,
        }
    try:
        limit = max(0, int(max_records))
    except (TypeError, ValueError):
        limit = 1
    if limit <= 0:
        return {
            "ok": False,
            "reason": "no_budget",
            "restored_count": 0,
        }
    records = [
        dict(record)
        for record in tuple(property_damage_records(sim, prop) or ())
        if _quiet_maintenance_record_allowed(record)
    ]
    if not records:
        return {
            "ok": False,
            "reason": "no_minor_damage",
            "restored_count": 0,
        }
    records = records[:limit]
    restored_keys = set()
    restored_kinds = []
    for record in records:
        repair_kind = _restore_damage_record(sim, prop, record)
        if not repair_kind:
            continue
        restored_keys.add(_record_key(record))
        restored_kinds.append(repair_kind)

    if not restored_keys:
        return {
            "ok": False,
            "reason": "nothing_restored",
            "restored_count": 0,
        }
    state = _stored_damage_state(prop, create=True)
    previous_records = state.get("records")
    state["records"] = [
        existing
        for existing in list(previous_records or ())
        if _record_key(_clean_damage_record(existing) or {}) not in restored_keys
    ]
    _note_damage_records_removed(sim, prop, restored_keys)
    result = {
        "ok": True,
        "reason": "restored",
        "property_id": _text(prop.get("id")),
        "property_name": _text(prop.get("name", prop.get("id"))),
        "restored_count": len(restored_keys),
        "restored_kinds": tuple(restored_kinds),
        "source_kind": _text(source_kind).lower() or "maintenance_loop",
    }
    if emit_event:
        try:
            x = int(prop.get("x", 0) or 0)
            y = int(prop.get("y", 0) or 0)
            z = int(prop.get("z", 0) or 0)
        except (TypeError, ValueError):
            x = y = z = 0
        sim.emit(Event(
            "quiet_maintenance_resolved",
            property_id=result["property_id"],
            property_name=result["property_name"],
            restored_count=int(result["restored_count"]),
            restored_kinds=tuple(restored_kinds),
            source_kind=result["source_kind"],
            x=x,
            y=y,
            z=z,
        ))
    return result


def structural_maintenance_cleanup(sim, prop, *, max_records=1, source_kind="structural_crew", emit_event=True):
    """Let an assigned structural crew restore a bounded number of surfaces.

    Unlike quiet maintenance this lane may address offender-linked, fire, wall,
    and breach damage.  It still never acts while the property is actively on
    fire, and callers are expected to provide real workers and elapsed labor.
    """

    if sim is None or not isinstance(prop, dict) or _text(prop.get("kind")).lower() != "building":
        return {"ok": False, "reason": "invalid_property", "restored_count": 0}
    try:
        limit = max(0, int(max_records))
    except (TypeError, ValueError):
        limit = 1
    if limit <= 0:
        return {"ok": False, "reason": "no_budget", "restored_count": 0}

    try:
        from game.system_support.fire_runtime import property_fire_cells

        if property_fire_cells(sim, _text(prop.get("id"))):
            return {"ok": False, "reason": "active_fire", "restored_count": 0}
    except (ImportError, AttributeError):
        pass

    kind_order = {"window": 0, "door": 1, "wall": 2}
    # Inferred rows exist for contractor compatibility with old saves, but can
    # also describe an unloaded or deliberately sparse tilemap.  Autonomous
    # crews only answer explicit damage facts produced by live destruction.
    records = [
        dict(record)
        for record in tuple(property_damage_records(sim, prop) or ())
        if _text(record.get("cause")).lower() != "inferred"
    ]
    records.sort(key=lambda record: (
        kind_order.get(_normalize_repair_kind(record.get("repair_kind"), record.get("aperture_kind")), 3),
        _int_or(record.get("damage_tick"), default=-10_000),
        _record_key(record),
    ))
    records = records[:limit]
    if not records:
        return {"ok": False, "reason": "no_structural_damage", "restored_count": 0}

    restored_keys = set()
    restored_kinds = []
    for record in records:
        repair_kind = _restore_damage_record(sim, prop, record)
        if not repair_kind:
            continue
        restored_keys.add(_record_key(record))
        restored_kinds.append(repair_kind)
    if not restored_keys:
        return {"ok": False, "reason": "nothing_restored", "restored_count": 0}

    state = _stored_damage_state(prop, create=True)
    previous_records = state.get("records")
    state["records"] = [
        existing
        for existing in list(previous_records or ())
        if _record_key(_clean_damage_record(existing) or {}) not in restored_keys
    ]
    _note_damage_records_removed(sim, prop, restored_keys)
    result = {
        "ok": True,
        "reason": "restored",
        "property_id": _text(prop.get("id")),
        "property_name": _text(prop.get("name", prop.get("id"))),
        "restored_count": len(restored_keys),
        "restored_kinds": tuple(restored_kinds),
        "source_kind": _text(source_kind).lower() or "structural_crew",
    }
    if emit_event:
        sim.emit(Event(
            "structural_maintenance_resolved",
            property_id=result["property_id"],
            property_name=result["property_name"],
            restored_count=int(result["restored_count"]),
            restored_kinds=tuple(restored_kinds),
            source_kind=result["source_kind"],
            x=_int_or(prop.get("x"), default=0),
            y=_int_or(prop.get("y"), default=0),
            z=_int_or(prop.get("z"), default=0),
        ))
    return result


__all__ = [
    "owned_building_properties",
    "owned_repairable_buildings",
    "damage_record_repair_cost",
    "fire_damage_record_at",
    "forget_property_fire_damage_records",
    "index_property_fire_damage_records",
    "property_damage_records",
    "property_damage_summary",
    "property_needs_building_repair",
    "quiet_maintenance_cleanup",
    "record_building_damage",
    "rebuild_fire_damage_record_index",
    "repair_building_damage",
    "structural_maintenance_cleanup",
]
