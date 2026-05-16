"""Shared contractor and building-repair helpers.

This seam keeps structural damage tracking and contractor-facing repair helpers
out of the monolith and the UI systems. It intentionally focuses on:

- recording structural building damage when windows, walls, or doors are forced
- inferring pre-existing damage from the live tilemap for older saves
- quoting and restoring damaged owned buildings through a single helper API
"""

from __future__ import annotations

from engine.tilemap import Tile
from game.components import PlayerAssets
from game.property_access import property_apertures
from game.system_support.intrusion_runtime import _is_operable_door_aperture, _is_window_aperture


BUILDING_REPAIR_BASE_COSTS = {
    "door": 34,
    "wall": 42,
    "window": 24,
}


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
    }


def record_building_damage(sim, prop, x, y, z=0, *, kind="", aperture_kind="", cause=""):
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
        },
        default_kind=kind,
        default_aperture_kind=aperture_kind,
    )
    if clean is None:
        return None
    state = _stored_damage_state(prop, create=True)
    records = list(state.get("records", ()))
    key = _record_key(clean)
    replaced = False
    for index, existing in enumerate(records):
        normalized = _clean_damage_record(existing)
        if normalized is None or _record_key(normalized) != key:
            continue
        records[index] = clean
        replaced = True
        break
    if not replaced:
        records.append(clean)
    state["records"] = records
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


def property_damage_records(sim, prop):
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
    return tuple(
        merged[key]
        for key in sorted(merged.keys(), key=lambda row: (row[2], row[1], row[0]))
    )


def property_damage_summary(sim, prop):
    records = tuple(property_damage_records(sim, prop))
    counts = {"window": 0, "door": 0, "wall": 0}
    base_cost = 0
    for record in records:
        repair_kind = _normalize_repair_kind(
            record.get("repair_kind"),
            aperture_kind=record.get("aperture_kind"),
        )
        counts[repair_kind] = counts.get(repair_kind, 0) + 1
        base_cost += int(BUILDING_REPAIR_BASE_COSTS.get(repair_kind, BUILDING_REPAIR_BASE_COSTS["wall"]))

    purchase_cost = max(80, _int_or(_property_metadata(prop).get("purchase_cost"), default=150))
    complexity_mult = 1.0 + min(0.45, max(0.0, float(purchase_cost) / 1000.0))
    total_cost = int(round(float(base_cost) * complexity_mult)) if base_cost > 0 else 0
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


def repair_building_damage(sim, prop):
    summary = property_damage_summary(sim, prop)
    records = tuple(summary.get("records", ()) or ())
    if not records:
        return {
            **summary,
            "restored_count": 0,
        }
    for record in records:
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
        else:
            _restore_wall_tile(sim, x, y, z)

    state = _stored_damage_state(prop, create=True)
    state["records"] = []
    return {
        **summary,
        "restored_count": len(records),
    }


__all__ = [
    "owned_building_properties",
    "owned_repairable_buildings",
    "property_damage_records",
    "property_damage_summary",
    "property_needs_building_repair",
    "record_building_damage",
    "repair_building_damage",
]
