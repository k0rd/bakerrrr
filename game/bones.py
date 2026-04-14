from __future__ import annotations

import random

from engine.persistence import append_bones_record, load_bones_archive
from game.components import Inventory, PlayerAssets, Position
from game.items import ITEM_CATALOG

BONES_MAX_STASH_ITEMS = 5
BONES_MAX_SPAWNS_PER_RUN = 2
BONES_SPAWN_CHANCE = 0.08
BONES_ARCHIVE_LIMIT = 64
_CARDINAL_STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _text(value):
    return str(value or "").strip()


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _chunk_key(chunk):
    if isinstance(chunk, dict):
        try:
            return (int(chunk.get("cx", 0)), int(chunk.get("cy", 0)))
        except (TypeError, ValueError):
            return None
    if isinstance(chunk, (list, tuple)) and len(chunk) >= 2:
        try:
            return (int(chunk[0]), int(chunk[1]))
        except (TypeError, ValueError):
            return None
    return None


def _reason_text(reason):
    token = _text(reason).replace("_", " ").strip()
    if not token:
        return "run gone bad"
    return token


def _player_position(sim, player_eid):
    if sim is None or player_eid is None:
        return None
    return sim.ecs.get(Position).get(player_eid)


def _record_area_profile(sim, chunk_key):
    if sim is None or chunk_key is None or getattr(sim, "world", None) is None:
        return {
            "area_type": "",
            "district_type": "",
            "region_name": "",
            "settlement_name": "",
        }
    desc = sim.world.overworld_descriptor(chunk_key[0], chunk_key[1])
    return {
        "area_type": _text(desc.get("area_type")).lower(),
        "district_type": _text(desc.get("district_type")).lower(),
        "region_name": _text(desc.get("region_name")),
        "settlement_name": _text(desc.get("settlement_name")),
    }


def _entry_bones_score(entry):
    item_id = _text((entry or {}).get("item_id")).lower()
    item_def = ITEM_CATALOG.get(item_id, {})
    score = 0
    if item_def.get("weapon_id"):
        score += 120
    if item_def.get("armor"):
        score += 100
    if item_def.get("disguise"):
        score += 90
    if item_def.get("container"):
        score += 80
    if item_def.get("tool_profiles"):
        score += 65
    if item_def.get("effects"):
        score += 55
    tags = {
        str(tag).strip().lower()
        for tag in item_def.get("tags", ())
        if str(tag).strip()
    }
    if "ammo" in tags:
        score += 35
    if "tool" in tags:
        score += 30
    score += min(6, _safe_int((entry or {}).get("quantity"), default=1))
    return score


def _snapshot_stash_items(sim, player_eid):
    inventory = sim.ecs.get(Inventory).get(player_eid) if sim is not None else None
    entries = list(inventory.items) if inventory else []
    rows = []
    used_item_ids = set()
    for entry in sorted(entries, key=lambda row: (_entry_bones_score(row), _text(row.get("item_id"))), reverse=True):
        item_id = _text(entry.get("item_id")).lower()
        if not item_id or item_id in used_item_ids:
            continue
        item_def = ITEM_CATALOG.get(item_id, {})
        stack_max = max(1, _safe_int(item_def.get("stack_max"), default=1))
        quantity = max(1, _safe_int(entry.get("quantity"), default=1))
        rows.append({
            "item_id": item_id,
            "quantity": 1 if stack_max <= 1 else min(quantity, min(stack_max, 3)),
            "metadata": dict(entry.get("metadata") or {}),
            "owner_eid": None,
            "owner_tag": "bones",
        })
        used_item_ids.add(item_id)
        if len(rows) >= BONES_MAX_STASH_ITEMS:
            break

    assets = sim.ecs.get(PlayerAssets).get(player_eid) if sim is not None else None
    bonus_chips = min(4, max(0, _safe_int(getattr(assets, "credits", 0), default=0) // 40))
    if bonus_chips > 0 and len(rows) < BONES_MAX_STASH_ITEMS and "credstick_chip" not in used_item_ids:
        rows.append({
            "item_id": "credstick_chip",
            "quantity": bonus_chips,
            "metadata": {"source": "legacy_run"},
            "owner_eid": None,
            "owner_tag": "bones",
        })
    return rows


def build_failed_run_bones_record(sim, player_eid, *, outcome="", reason="", objective_title="", summary_lines=()):
    if sim is None or player_eid is None or _text(outcome).lower() != "failed":
        return None
    pos = _player_position(sim, player_eid)
    if pos is None:
        return None

    chunk = sim.chunk_coords(int(pos.x), int(pos.y))
    area = _record_area_profile(sim, chunk)
    prop = sim.property_covering(int(pos.x), int(pos.y), int(pos.z)) if hasattr(sim, "property_covering") else None
    character_name = _text(getattr(sim, "character_name", "")) or _text(getattr(sim, "world_traits", {}).get("character_name"))
    character_name = character_name or "Unknown Runner"
    reason_line = _reason_text(reason)
    summary_lines = [str(line).strip() for line in (summary_lines or ()) if str(line).strip()]
    stash_items = _snapshot_stash_items(sim, player_eid)
    prop_name = _text((prop or {}).get("name"))
    epitaph = f"Here lies {character_name}."
    if prop_name:
        epitaph += f" Lost near {prop_name}."
    elif area.get("settlement_name"):
        epitaph += f" Lost around {area['settlement_name']}."

    stash_note = f"Remains of {character_name}. {reason_line.capitalize()}."
    if objective_title:
        stash_note += f" Last run: {objective_title}."

    return {
        "record_id": f"{character_name.lower().replace(' ', '_')}:{getattr(sim, 'seed', 'seed')}:{_safe_int(getattr(sim, 'tick', 0))}:{_text(reason).lower()}",
        "character_name": character_name,
        "outcome": "failed",
        "reason": _text(reason).lower(),
        "objective_title": _text(objective_title),
        "tick": _safe_int(getattr(sim, "tick", 0), default=0),
        "chunk": chunk,
        "position": (int(pos.x), int(pos.y), int(pos.z)),
        "property_name": prop_name,
        "summary_lines": summary_lines[:5],
        "epitaph": epitaph,
        "marker_name": f"Marker of {character_name}",
        "marker_sign": reason_line.capitalize(),
        "stash_name": f"Stash of {character_name}",
        "stash_note": stash_note,
        "stash_items": stash_items,
        **area,
    }


def archive_failed_run_bones(sim, player_eid, *, outcome="", reason="", objective_title="", summary_lines=(), archive_path=None):
    record = build_failed_run_bones_record(
        sim,
        player_eid,
        outcome=outcome,
        reason=reason,
        objective_title=objective_title,
        summary_lines=summary_lines,
    )
    if not isinstance(record, dict):
        return None
    append_bones_record(record, archive_path=archive_path, max_records=BONES_ARCHIVE_LIMIT)
    return record


def prime_bones_runtime(sim, *, archive_path=None):
    if sim is None:
        return {"records": []}
    runtime = getattr(sim, "bones_runtime", None)
    if not isinstance(runtime, dict):
        runtime = {}
        sim.bones_runtime = runtime
    if archive_path is not None:
        runtime["archive_path"] = str(archive_path)
    runtime.setdefault("attempted_chunks", set())
    runtime.setdefault("spawned_record_ids", set())
    runtime.setdefault("spawn_count", 0)
    if not isinstance(runtime.get("records"), list):
        runtime["records"] = load_bones_archive(archive_path=runtime.get("archive_path"))
    return runtime


def _record_match_score(record, chunk):
    if not isinstance(record, dict):
        return -1
    district = chunk.get("district", {}) if isinstance(chunk, dict) else {}
    chunk_area = _text(district.get("area_type")).lower()
    chunk_district = _text(district.get("district_type")).lower()
    score = 0
    if chunk_area and _text(record.get("area_type")).lower() == chunk_area:
        score += 2
    if chunk_district and _text(record.get("district_type")).lower() == chunk_district:
        score += 1
    return score


def _is_outdoor_empty_tile(sim, x, y, z=0):
    tile = sim.tilemap.tile_at(x, y, z) if sim is not None else None
    if not tile or not bool(getattr(tile, "walkable", False)):
        return False
    if hasattr(sim, "property_at") and sim.property_at(x, y, z):
        return False
    if hasattr(sim, "property_covering") and sim.property_covering(x, y, z):
        return False
    return True


def _pick_grave_and_stash_tiles(sim, chunk_key, rng):
    if sim is None or chunk_key is None:
        return None
    origin_x, origin_y = sim.chunk_origin(*chunk_key)
    size = max(8, _safe_int(getattr(sim, "chunk_size", 16), default=16))
    candidates = set()
    for y in range(origin_y + 1, origin_y + size - 1):
        for x in range(origin_x + 1, origin_x + size - 1):
            if _is_outdoor_empty_tile(sim, x, y, 0):
                candidates.add((x, y))
    if not candidates:
        return None

    pairs = []
    for x, y in sorted(candidates):
        for dx, dy in _CARDINAL_STEPS:
            neighbor = (x + dx, y + dy)
            if neighbor not in candidates:
                continue
            grave_tile = sim.tilemap.tile_at(x, y, 0)
            stash_tile = sim.tilemap.tile_at(neighbor[0], neighbor[1], 0)
            score = 0
            if str(getattr(grave_tile, "glyph", "")).strip() in {"=", ":"}:
                score += 2
            if str(getattr(stash_tile, "glyph", "")).strip() in {"=", ":"}:
                score += 1
            pairs.append((score, (x, y, 0), (neighbor[0], neighbor[1], 0)))
    if not pairs:
        return None
    best_score = max(row[0] for row in pairs)
    finalists = [row for row in pairs if row[0] == best_score]
    chosen = rng.choice(finalists)
    return chosen[1], chosen[2]


def _append_chunk_property_record(sim, chunk_key, prop_id, kind, x, y, z, archetype):
    records = getattr(sim, "chunk_property_records", None)
    if not isinstance(records, dict):
        sim.chunk_property_records = {}
        records = sim.chunk_property_records
    chunk_rows = records.setdefault(chunk_key, [])
    chunk_rows.append({
        "id": prop_id,
        "kind": kind,
        "x": x,
        "y": y,
        "z": z,
        "archetype": archetype,
        "building_id": None,
    })


def maybe_seed_bones_for_chunk(sim, chunk, *, force=False):
    chunk_key = _chunk_key(chunk)
    if sim is None or chunk_key is None:
        return None

    runtime = prime_bones_runtime(sim)
    attempted = runtime.setdefault("attempted_chunks", set())
    if chunk_key in attempted:
        return None
    attempted.add(chunk_key)

    if int(runtime.get("spawn_count", 0) or 0) >= BONES_MAX_SPAWNS_PER_RUN:
        return None

    records = [entry for entry in runtime.get("records", ()) if isinstance(entry, dict)]
    if not records:
        return None

    used_ids = runtime.setdefault("spawned_record_ids", set())
    eligible = [entry for entry in records if _text(entry.get("record_id")) not in used_ids]
    if not eligible:
        return None

    rng = random.Random(f"{getattr(sim, 'seed', 'seed')}:bones:{chunk_key[0]}:{chunk_key[1]}")
    if not force and rng.random() > BONES_SPAWN_CHANCE:
        return None

    scored = []
    for record in eligible:
        scored.append((_record_match_score(record, chunk), _text(record.get("record_id")), record))
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    best_score = scored[0][0]
    finalists = [row[2] for row in scored if row[0] == best_score]
    record = rng.choice(finalists)

    tiles = _pick_grave_and_stash_tiles(sim, chunk_key, rng)
    if tiles is None:
        return None
    grave_pos, stash_pos = tiles
    grave_meta = {
        "archetype": "grave_marker",
        "display_glyph": "+",
        "display_color": "property_fixture",
        "public": True,
        "chunk": chunk_key,
        "signage": {"text": _text(record.get("marker_sign"))},
        "bones_record_id": _text(record.get("record_id")),
        "epitaph": _text(record.get("epitaph")),
    }
    grave_id = sim.register_property(
        _text(record.get("marker_name")) or "Old Marker",
        "fixture",
        grave_pos[0],
        grave_pos[1],
        grave_pos[2],
        owner_tag="public",
        metadata=grave_meta,
    )
    _append_chunk_property_record(sim, chunk_key, grave_id, "fixture", grave_pos[0], grave_pos[1], grave_pos[2], "grave_marker")

    stash_meta = {
        "archetype": "bones_stash",
        "display_glyph": "j",
        "display_color": "property_asset",
        "chunk": chunk_key,
        "interaction_role": "bones_stash",
        "fixture_kind": "cache",
        "bones_record_id": _text(record.get("record_id")),
        "bones_note": _text(record.get("stash_note")),
    }
    stash_id = sim.register_property(
        _text(record.get("stash_name")) or "Old Stash",
        "asset",
        stash_pos[0],
        stash_pos[1],
        stash_pos[2],
        owner_tag="public",
        metadata=stash_meta,
    )
    _append_chunk_property_record(sim, chunk_key, stash_id, "asset", stash_pos[0], stash_pos[1], stash_pos[2], "bones_stash")

    inventories_by_kind = getattr(sim, "container_inventories", None)
    if not isinstance(inventories_by_kind, dict):
        sim.container_inventories = {}
        inventories_by_kind = sim.container_inventories
    bones_inventories = inventories_by_kind.setdefault("bones", {})
    bones_inventories[stash_id] = [
        {
            "item_id": _text(entry.get("item_id")).lower(),
            "quantity": max(1, _safe_int(entry.get("quantity"), default=1)),
            "metadata": dict(entry.get("metadata") or {}),
            "owner_eid": None,
            "owner_tag": _text(entry.get("owner_tag")) or "bones",
        }
        for entry in list(record.get("stash_items", ()) or ())
        if _text((entry or {}).get("item_id"))
    ]

    used_ids.add(_text(record.get("record_id")))
    runtime["spawn_count"] = int(runtime.get("spawn_count", 0) or 0) + 1
    return {
        "record_id": _text(record.get("record_id")),
        "grave_property_id": grave_id,
        "stash_property_id": stash_id,
        "character_name": _text(record.get("character_name")),
        "chunk": chunk_key,
    }
