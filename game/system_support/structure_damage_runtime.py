"""Shared structural durability helpers for doors, windows, and walls."""

from __future__ import annotations

from engine.events import Event
from engine.tilemap import Tile
from game.property_runtime import property_aperture_at, property_covering
from game.system_support.building_repair_runtime import record_building_damage
from game.system_support.intrusion_runtime import _is_operable_door_aperture, _is_window_aperture


STRUCTURE_MAX_HP = {
    "window": 5,
    "door": 24,
    "wall": 56,
}


def _text(value):
    return str(value or "").strip()


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _coord_key(x, y, z=0):
    try:
        return int(x), int(y), int(z)
    except (TypeError, ValueError):
        return None


def _cell_key(x, y, z=0):
    key = _coord_key(x, y, z)
    if key is None:
        return ""
    return f"{key[0]},{key[1]},{key[2]}"


def _property_metadata(prop, *, create=False):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    if not isinstance(metadata, dict):
        if not create:
            return {}
        metadata = {}
        prop["metadata"] = metadata
    return metadata


def _durability_state(prop, *, create=False):
    metadata = _property_metadata(prop, create=create)
    state = metadata.get("structure_durability")
    if not isinstance(state, dict):
        if not create:
            return None
        state = {}
        metadata["structure_durability"] = state
    cells = state.get("cells")
    if not isinstance(cells, dict):
        cells = {}
        state["cells"] = cells
    return state


def _surface_kind_from_tile(tile):
    semantic = _text(getattr(tile, "semantic_id", "")).lower()
    glyph = _text(getattr(tile, "glyph", ""))
    if semantic == "feature_window" or glyph == '"':
        return "window"
    if semantic == "feature_door" or glyph in {"+", "'"}:
        return "door"
    if semantic == "wall_building" or glyph == "#":
        return "wall"
    return ""


def structural_surface_kind(sim, prop, x, y, z=0, *, tile=None, aperture=None):
    key = _coord_key(x, y, z)
    if key is None:
        return ""
    if not isinstance(prop, dict):
        prop = property_covering(sim, key[0], key[1], key[2]) if sim is not None else None
    if not isinstance(aperture, dict) and isinstance(prop, dict):
        aperture = property_aperture_at(prop, key[0], key[1], key[2])
    aperture_kind = _text((aperture or {}).get("kind")).lower()
    if _is_window_aperture(aperture_kind):
        return "window"
    if _is_operable_door_aperture(aperture_kind):
        return "door"
    if sim is not None:
        door_state = getattr(sim, "door_state_at", lambda *_args, **_kwargs: None)(key[0], key[1], key[2])
        door_kind = _text((door_state or {}).get("kind")).lower()
        if _is_operable_door_aperture(door_kind):
            return "door"
    if tile is None and sim is not None and hasattr(sim, "tilemap"):
        tile = sim.tilemap.tile_at(key[0], key[1], key[2])
    return _surface_kind_from_tile(tile)


def structural_surface_label(kind):
    kind = _text(kind).lower()
    if kind == "window":
        return "window"
    if kind == "door":
        return "door"
    if kind == "wall":
        return "wall"
    return "surface"


def structural_surface_state(sim, prop, x, y, z=0, *, kind="", create=False):
    key = _coord_key(x, y, z)
    if key is None or not isinstance(prop, dict):
        return None
    kind = _text(kind).lower() or structural_surface_kind(sim, prop, key[0], key[1], key[2])
    if kind not in STRUCTURE_MAX_HP:
        return None
    state = _durability_state(prop, create=create)
    if state is None:
        return None
    cells = state["cells"]
    ckey = _cell_key(key[0], key[1], key[2])
    row = cells.get(ckey)
    if not isinstance(row, dict):
        if not create:
            return None
        max_hp = int(STRUCTURE_MAX_HP[kind])
        row = {
            "x": key[0],
            "y": key[1],
            "z": key[2],
            "kind": kind,
            "hp": max_hp,
            "max_hp": max_hp,
            "broken": False,
        }
        cells[ckey] = row
    else:
        row["x"] = key[0]
        row["y"] = key[1]
        row["z"] = key[2]
        row["kind"] = _text(row.get("kind")).lower() or kind
        row["max_hp"] = max(1, _safe_int(row.get("max_hp"), STRUCTURE_MAX_HP.get(row["kind"], STRUCTURE_MAX_HP[kind])))
        row["hp"] = max(0, min(row["max_hp"], _safe_int(row.get("hp"), row["max_hp"])))
        row["broken"] = bool(row.get("broken", False)) or row["hp"] <= 0
    return row


def structure_is_broken(sim, prop, x, y, z=0, *, kind=""):
    row = structural_surface_state(sim, prop, x, y, z, kind=kind, create=False)
    return bool(row and (row.get("broken") or _safe_int(row.get("hp"), 0) <= 0))


def _mark_tile_broken(sim, prop, x, y, z, *, kind, aperture_kind=""):
    if kind == "door" and hasattr(sim, "set_door_state"):
        state = sim.set_door_state(
            int(x),
            int(y),
            int(z),
            open=True,
            kind=_text(aperture_kind).lower() or "door",
            ordinary=(_text(aperture_kind).lower() or "door") == "door",
            property_id=prop.get("id") if isinstance(prop, dict) else None,
            broken=True,
        )
        if isinstance(state, dict):
            state["broken"] = True
        if hasattr(sim, "apply_door_state"):
            if sim.apply_door_state(int(x), int(y), int(z)):
                return
    sim.tilemap.set_tile(
        int(x),
        int(y),
        Tile(walkable=True, transparent=True, glyph="/", color="feature_breach", semantic_id="feature_breach"),
        z=int(z),
    )


def break_structural_surface(
    sim,
    prop,
    x,
    y,
    z=0,
    *,
    kind="",
    aperture_kind="",
    cause="",
    offender_eid=None,
    damage_tick=None,
    emit_event=True,
):
    key = _coord_key(x, y, z)
    if key is None or not isinstance(prop, dict):
        return None
    kind = _text(kind).lower() or structural_surface_kind(sim, prop, key[0], key[1], key[2])
    if kind not in STRUCTURE_MAX_HP:
        return None
    row = structural_surface_state(sim, prop, key[0], key[1], key[2], kind=kind, create=True)
    if row is None:
        return None
    row["hp"] = 0
    row["broken"] = True
    row["broken_tick"] = _safe_int(damage_tick, _safe_int(getattr(sim, "tick", 0), 0))
    row["last_cause"] = _text(cause).lower()
    aperture = property_aperture_at(prop, key[0], key[1], key[2]) if isinstance(prop, dict) else None
    aperture_kind = _text(aperture_kind or (aperture or {}).get("kind")).lower()
    _mark_tile_broken(sim, prop, key[0], key[1], key[2], kind=kind, aperture_kind=aperture_kind)
    record_building_damage(
        sim,
        prop,
        key[0],
        key[1],
        key[2],
        kind=kind,
        aperture_kind=aperture_kind,
        cause=cause,
        offender_eid=offender_eid,
        damage_tick=damage_tick,
    )
    if emit_event:
        sim.emit(Event(
            "structure_broken",
            offender_eid=offender_eid,
            property_id=prop.get("id"),
            property_name=prop.get("name"),
            x=key[0],
            y=key[1],
            z=key[2],
            surface_kind=kind,
            aperture_kind=aperture_kind,
            cause=_text(cause).lower(),
            hp=0,
            max_hp=_safe_int(row.get("max_hp"), STRUCTURE_MAX_HP[kind]),
        ))
    return row


def apply_structural_damage(
    sim,
    prop,
    x,
    y,
    z=0,
    *,
    amount=1,
    kind="",
    aperture_kind="",
    cause="",
    damage_kind="",
    weapon_id="",
    offender_eid=None,
    damage_tick=None,
    emit_event=True,
):
    key = _coord_key(x, y, z)
    if sim is None or key is None:
        return {"damaged": False, "broken": False, "reason": "invalid_coord"}
    if not isinstance(prop, dict):
        prop = property_covering(sim, key[0], key[1], key[2])
    if not isinstance(prop, dict) or _text(prop.get("kind")).lower() != "building":
        return {"damaged": False, "broken": False, "reason": "no_property"}
    tile = sim.tilemap.tile_at(key[0], key[1], key[2]) if hasattr(sim, "tilemap") else None
    aperture = property_aperture_at(prop, key[0], key[1], key[2])
    kind = _text(kind).lower() or structural_surface_kind(sim, prop, key[0], key[1], key[2], tile=tile, aperture=aperture)
    if kind not in STRUCTURE_MAX_HP:
        return {"damaged": False, "broken": False, "reason": "not_structural"}
    row = structural_surface_state(sim, prop, key[0], key[1], key[2], kind=kind, create=True)
    if row is None:
        return {"damaged": False, "broken": False, "reason": "no_state"}
    before = _safe_int(row.get("hp"), STRUCTURE_MAX_HP[kind])
    if bool(row.get("broken", False)) or before <= 0:
        return {
            "damaged": False,
            "broken": True,
            "already_broken": True,
            "surface_kind": kind,
            "hp": 0,
            "max_hp": _safe_int(row.get("max_hp"), STRUCTURE_MAX_HP[kind]),
            "property_id": prop.get("id"),
        }
    amount = max(0, _safe_int(amount, 0))
    if amount <= 0:
        return {"damaged": False, "broken": False, "reason": "no_damage", "surface_kind": kind}
    after = max(0, before - amount)
    row["hp"] = after
    row["last_damage_tick"] = _safe_int(damage_tick, _safe_int(getattr(sim, "tick", 0), 0))
    row["last_cause"] = _text(cause).lower()
    row["last_damage_kind"] = _text(damage_kind).lower()
    row["last_weapon_id"] = _text(weapon_id)
    row["last_offender_eid"] = offender_eid
    max_hp = _safe_int(row.get("max_hp"), STRUCTURE_MAX_HP[kind])
    if emit_event:
        sim.emit(Event(
            "structure_damaged",
            offender_eid=offender_eid,
            property_id=prop.get("id"),
            property_name=prop.get("name"),
            x=key[0],
            y=key[1],
            z=key[2],
            surface_kind=kind,
            aperture_kind=_text(aperture_kind or (aperture or {}).get("kind")).lower(),
            cause=_text(cause).lower(),
            damage_kind=_text(damage_kind).lower(),
            weapon_id=_text(weapon_id),
            damage=amount,
            hp=after,
            max_hp=max_hp,
            broken=after <= 0,
        ))
    if after <= 0:
        break_structural_surface(
            sim,
            prop,
            key[0],
            key[1],
            key[2],
            kind=kind,
            aperture_kind=aperture_kind,
            cause=cause,
            offender_eid=offender_eid,
            damage_tick=damage_tick,
            emit_event=emit_event,
        )
    return {
        "damaged": True,
        "broken": after <= 0,
        "surface_kind": kind,
        "hp": after,
        "max_hp": max_hp,
        "damage": amount,
        "property_id": prop.get("id"),
        "property_name": prop.get("name"),
    }
