"""Small-scale flora cultivation, potted plants, and crossbreeding helpers."""

from __future__ import annotations

import random
from hashlib import sha256
from collections.abc import Mapping

from engine.events import Event
from engine.systems import System
from game.components import AI, Inventory, Position
from game.flora_runtime import (
    EXHAUSTED_FLORA_STAGES,
    DEFAULT_GLYPH_BY_FORM,
    DEFAULT_RENDER_KEY_BY_FORM,
    flora_at,
    flora_bloom_state,
    flora_harvest_limit,
    load_flora_catalog,
    normalize_flora_harvest_state,
    register_flora_patch,
)
from game.herbal_chemistry_runtime import plant_chemistry_class
from game.items import ITEM_CATALOG, item_display_name
from game.property_runtime import property_fixture_type


PLANT_POT_ITEM_ID = "plant_pot"
SEED_PACKET_ITEM_ID = "seed_packet"
PLANTABLE_MATERIAL_ITEM_IDS = {
    "fresh_blossoms",
    "leaf_clippings",
    "moss_scrapings",
    "vine_cuttings",
}
POLLEN_ITEM_IDS = {"fresh_blossoms"}
NON_POT_GROWTH_FORMS = {"vine"}
FAILED_STAGES = {"withering", "failed"}
MATURE_STAGES = {"mature", "flowering", "open", "closed"}
GARDENER_ROLES = {
    "herbalist",
    "field_herbalist",
    "remedy_mixer",
    "forager",
    "gardener",
    "caretaker",
    "drying_shelf_clerk",
    "recipe_keeper",
}
GROWTH_STAGE_TICKS = (
    ("sprouting", 6 * 600),
    ("young", 18 * 600),
    ("mature", 36 * 600),
)


def _key(value, fallback=""):
    text = str(value if value is not None else "").strip().lower()
    return text or str(fallback or "").strip().lower()


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


def _actor_key(eid):
    return str(eid if eid is not None else "").strip()


def ensure_cultivation_state(sim):
    if not isinstance(getattr(sim, "cultivation_records", None), dict):
        sim.cultivation_records = {}
    if not hasattr(sim, "next_cultivation_id"):
        sim.next_cultivation_id = 1
    if not isinstance(getattr(sim, "cultivation_gardener_cooldowns", None), dict):
        sim.cultivation_gardener_cooldowns = {}
    return sim.cultivation_records


def _next_cultivation_id(sim):
    ensure_cultivation_state(sim)
    next_id = _safe_int(getattr(sim, "next_cultivation_id", 1), 1)
    sim.next_cultivation_id = next_id + 1
    return f"cultivation:{next_id}"


def _chunk_for_xy(sim, x, y):
    try:
        return tuple(int(v) for v in sim.chunk_coords(int(x), int(y)))
    except Exception:
        size = max(1, _safe_int(getattr(sim, "chunk_size", 16), 16))
        return (int(x) // size, int(y) // size)


def _chunk_area_context(sim, x, y):
    cx, cy = _chunk_for_xy(sim, x, y)
    desc = {}
    try:
        desc = sim.world.overworld_descriptor(cx, cy)
    except Exception:
        try:
            chunk = sim.world.get_chunk(cx, cy)
            desc = chunk.get("district", {}) if isinstance(chunk, dict) else {}
        except Exception:
            desc = {}
    if not isinstance(desc, Mapping):
        desc = {}
    raw_area = _key(desc.get("area_type") or desc.get("area") or desc.get("district"), "wilderness")
    district = _key(desc.get("district") or desc.get("district_type"))
    city_districts = {"downtown", "corporate", "residential", "entertainment", "industrial", "slums", "military"}
    area_key = "city" if raw_area in city_districts or district in city_districts else raw_area
    if area_key not in {"city", "wilderness", "frontier", "coastal"}:
        area_key = "wilderness"
    if area_key == "city" and not district:
        district = raw_area if raw_area in city_districts else "residential"
    return area_key, district


def _tile_color_key(sim, x, y, z=0):
    tile = sim.tilemap.tile_at(int(x), int(y), int(z))
    return _key(getattr(tile, "color", ""))


def _tile_allows_ground_planting(sim, x, y, z=0):
    tile = sim.tilemap.tile_at(int(x), int(y), int(z))
    if tile is None or not bool(getattr(tile, "walkable", True)):
        return False
    glyph = str(getattr(tile, "glyph", "") or "")[:1]
    color_key = _tile_color_key(sim, x, y, z)
    if glyph in {"=", ":", "+", "'", '"', "/", "#", "~", "^", ">", "<", "|"}:
        return False
    if color_key in {"terrain_road", "terrain_trail", "feature_door", "feature_window", "terrain_water", "terrain_rock"}:
        return False
    if hasattr(sim, "structure_at") and sim.structure_at(int(x), int(y), int(z)) is not None:
        return False
    if hasattr(sim, "property_covering") and sim.property_covering(int(x), int(y), int(z)):
        return False
    if hasattr(sim, "ground_items_at") and sim.ground_items_at(int(x), int(y), z=int(z)):
        return False
    try:
        if sim.tilemap.entities_at(int(x), int(y), int(z)):
            return False
    except Exception:
        pass
    return True


def _plant_row(plant_id):
    plant_id = _key(plant_id)
    return load_flora_catalog().get(plant_id, {}) if plant_id else {}


def _row_or_source(source):
    if not isinstance(source, Mapping):
        return {}
    row = _plant_row(source.get("plant_id"))
    if row:
        return row
    return {
        "id": _key(source.get("plant_id")),
        "name": str(source.get("plant_name") or source.get("plant_id") or "plant").strip(),
        "growth_form": _key(source.get("growth_form"), "flower"),
        "glyph": str(source.get("glyph") or DEFAULT_GLYPH_BY_FORM.get(_key(source.get("growth_form"), "flower"), "'"))[:1],
        "render_key": _key(source.get("render_key") or source.get("color_key"), DEFAULT_RENDER_KEY_BY_FORM.get(_key(source.get("growth_form"), "flower"), "flora_flower_pink")),
        "colors": tuple(filter(None, (_key(source.get("color_key")), _key(source.get("render_key"))))),
        "rarity": _key(source.get("rarity"), "common"),
        "area_weights": {},
        "terrain_weights": {},
        "district_weights": {},
        "tags": tuple(source.get("tags", ()) or ()),
        "growth_traits": {},
        "genetics": dict(source.get("genetics") or {}) if isinstance(source.get("genetics"), Mapping) else {},
        "harvest_potential": {},
        "crossbreed_tags": tuple(source.get("crossbreed_tags", ()) or ()),
        "spread_profile": {},
    }


def seed_packet_metadata(sim, *, plant_id=None, seed_token="", source_kind="stock", hybrid=None):
    catalog = load_flora_catalog()
    if isinstance(hybrid, Mapping):
        plant_id = _key(hybrid.get("plant_id"))
        row = _row_or_source(hybrid)
    else:
        plant_id = _key(plant_id)
        rng = random.Random(f"{getattr(sim, 'seed', 0)}:seed-packet:{seed_token or plant_id or 'stock'}")
        if not plant_id or plant_id not in catalog:
            rows = tuple(catalog.values())
            weights = []
            rarity_mult = {"common": 10, "uncommon": 5, "rare": 1}
            for row in rows:
                weights.append((row, rarity_mult.get(_key(row.get("rarity"), "common"), 3)))
            total = sum(weight for _row, weight in weights)
            roll = rng.randint(1, max(1, total))
            cursor = 0
            chosen = rows[0]
            for row, weight in weights:
                cursor += weight
                if roll <= cursor:
                    chosen = row
                    break
            plant_id = chosen["id"]
        row = catalog.get(plant_id, {})
    row = row or {}
    growth_form = _key(row.get("growth_form"), "flower")
    color_key = _key(
        (tuple(row.get("colors", ()) or ()) or (row.get("render_key"),))[0],
        DEFAULT_RENDER_KEY_BY_FORM.get(growth_form, "flora_flower_pink"),
    )
    plant_name = str(row.get("name") or plant_id.replace("_", " ")).strip() or "plant"
    display = f"{plant_name.title()} Seed Packet"
    if isinstance(hybrid, Mapping) and hybrid.get("display_name"):
        display = str(hybrid.get("display_name")).strip()
    payload = {
        "source": "cultivation",
        "source_context": source_kind,
        "display_name": display,
        "source_plant_id": plant_id,
        "source_plant_name": plant_name,
        "growth_form": growth_form,
        "color_key": color_key,
        "render_key": _key(row.get("render_key"), color_key),
        "glyph": str(row.get("glyph") or DEFAULT_GLYPH_BY_FORM.get(growth_form, "'"))[:1],
        "rarity": _key(row.get("rarity"), "common"),
        "plantability_flags": {
            "pot": growth_form not in NON_POT_GROWTH_FORMS,
            "planter": True,
            "ground": True,
        },
        "crossbreed_tags": list(row.get("crossbreed_tags", ()) or ()),
        "tags": list(row.get("tags", ()) or ()),
        "hybrid_generation": _safe_int((hybrid or {}).get("hybrid_generation"), 0) if isinstance(hybrid, Mapping) else 0,
        "lineage": dict((hybrid or {}).get("lineage") or {}) if isinstance(hybrid, Mapping) else {},
        "parent_plant_ids": list((hybrid or {}).get("parent_plant_ids", ()) or ()) if isinstance(hybrid, Mapping) else [],
    }
    if isinstance(hybrid, Mapping):
        for key in ("chemistry_class", "parent_chemistry_classes", "hybrid_signature", "genetics"):
            if key in hybrid:
                payload[key] = hybrid[key]
    return payload


def _source_from_entry(sim, entry):
    if not isinstance(entry, Mapping):
        return None
    item_id = _key(entry.get("item_id"))
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}
    if item_id == SEED_PACKET_ITEM_ID:
        if not _key(metadata.get("source_plant_id")):
            metadata = seed_packet_metadata(sim, seed_token=str(entry.get("instance_id") or "blank"))
        plant_id = _key(metadata.get("source_plant_id"))
    elif item_id in PLANTABLE_MATERIAL_ITEM_IDS and _key(metadata.get("source")) == "flora":
        plant_id = _key(metadata.get("source_plant_id"))
    else:
        return None
    if not plant_id:
        return None
    row = _plant_row(plant_id)
    growth_form = _key(metadata.get("growth_form") or row.get("growth_form"), "flower")
    return {
        "item_id": item_id,
        "instance_id": str(entry.get("instance_id", "") or ""),
        "plant_id": plant_id,
        "plant_name": str(metadata.get("source_plant_name") or row.get("name") or plant_id.replace("_", " ")).strip(),
        "growth_form": growth_form,
        "color_key": _key(metadata.get("color_key") or (tuple(row.get("colors", ()) or ()) or ("",))[0], row.get("render_key") or DEFAULT_RENDER_KEY_BY_FORM.get(growth_form, "flora_flower_pink")),
        "render_key": _key(metadata.get("render_key") or row.get("render_key"), DEFAULT_RENDER_KEY_BY_FORM.get(growth_form, "flora_flower_pink")),
        "glyph": str(metadata.get("glyph") or row.get("glyph") or DEFAULT_GLYPH_BY_FORM.get(growth_form, "'"))[:1],
        "rarity": _key(metadata.get("rarity") or row.get("rarity"), "common"),
        "tags": tuple(metadata.get("tags") or row.get("tags", ()) or ()),
        "crossbreed_tags": tuple(metadata.get("crossbreed_tags") or row.get("crossbreed_tags", ()) or ()),
        "genetics": dict(metadata.get("genetics") or row.get("genetics") or {}) if isinstance(metadata.get("genetics") or row.get("genetics"), Mapping) else {},
        "chemistry_class": _key(metadata.get("chemistry_class")) or plant_chemistry_class(sim, plant_id),
        "metadata": dict(metadata),
    }


def _empty_pot_entry(inventory):
    if inventory is None:
        return None
    for entry in tuple(getattr(inventory, "items", ()) or ()):
        if _key(entry.get("item_id")) != PLANT_POT_ITEM_ID:
            continue
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}
        if not metadata.get("cultivation_id") and not metadata.get("cultivation_record"):
            return entry
    return None


def _inventory_can_accept(inventory, item_id, quantity=1, *, metadata=None, owner_eid=None, owner_tag=None):
    if inventory is None:
        return False
    from game.components import Inventory as _Inventory

    clone = _Inventory(capacity=getattr(inventory, "capacity", 10))
    clone.items = [dict(row, metadata=dict(row.get("metadata") or {})) for row in tuple(getattr(inventory, "items", ()) or ())]
    item_def = ITEM_CATALOG.get(item_id, {})
    added, _instance_id = clone.add_item(
        item_id,
        quantity=quantity,
        stack_max=item_def.get("stack_max", 1),
        instance_id="cultivation-probe",
        owner_eid=owner_eid,
        owner_tag=owner_tag,
        metadata=metadata or {},
    )
    return bool(added)


def _add_inventory_item(sim, inventory, item_id, quantity=1, *, metadata=None, owner_eid=None, owner_tag=None):
    item_def = ITEM_CATALOG.get(item_id, {})
    return inventory.add_item(
        item_id,
        quantity=quantity,
        stack_max=max(1, _safe_int(item_def.get("stack_max"), 1)),
        instance_factory=sim.new_item_instance_id,
        owner_eid=owner_eid,
        owner_tag=owner_tag,
        metadata=metadata or {},
    )


def _remove_flora_patch(sim, flora_id):
    flora_id = str(flora_id or "").strip()
    if not flora_id:
        return
    patches = getattr(sim, "flora_patches", None)
    if isinstance(patches, dict):
        patches.pop(flora_id, None)
    chunk_records = getattr(sim, "chunk_flora_records", None)
    if isinstance(chunk_records, dict):
        for key, rows in list(chunk_records.items()):
            cleaned = [dict(row) for row in tuple(rows or ()) if str(row.get("id", "")) != flora_id]
            if len(cleaned) != len(tuple(rows or ())):
                chunk_records[key] = cleaned


def _record_flora_id(record):
    cid = str((record or {}).get("id") or "").strip()
    return f"flora:{cid}" if cid else ""


def _flora_record_from_cultivation(record):
    row = _row_or_source(record)
    growth_form = _key(record.get("growth_form") or row.get("growth_form"), "flower")
    flora_id = str(record.get("linked_flora_id") or _record_flora_id(record))
    stage = _key(record.get("stage"), "seeded")
    harvest_limit = max(1, _safe_int(record.get("harvest_limit"), flora_harvest_limit({"growth_form": growth_form, "rarity": row.get("rarity")})))
    harvest_remaining = max(0, _safe_int(record.get("harvest_remaining"), harvest_limit if stage not in FAILED_STAGES else 0))
    if stage in FAILED_STAGES:
        harvest_remaining = 0
    return normalize_flora_harvest_state({
        "id": flora_id,
        "cultivation_id": record.get("id"),
        "plant_id": record.get("plant_id"),
        "name": record.get("plant_name") or row.get("name") or record.get("plant_id"),
        "x": _safe_int(record.get("x"), 0),
        "y": _safe_int(record.get("y"), 0),
        "z": _safe_int(record.get("z"), 0),
        "chunk": list(record.get("chunk") or _chunk_for_xy_from_record(record)),
        "stage": stage,
        "variant_seed": _safe_int(record.get("variant_seed"), 1),
        "color_key": _key(record.get("color_key"), row.get("render_key") or DEFAULT_RENDER_KEY_BY_FORM.get(growth_form, "flora_leaf")),
        "growth_form": growth_form,
        "glyph": str(record.get("glyph") or row.get("glyph") or DEFAULT_GLYPH_BY_FORM.get(growth_form, ","))[:1],
        "render_key": _key(record.get("render_key") or row.get("render_key"), DEFAULT_RENDER_KEY_BY_FORM.get(growth_form, "flora_leaf")),
        "spread_state": record.get("spread_state") or ("flowering" if growth_form == "flower" else "rooted"),
        "spread_direction": record.get("spread_direction"),
        "cluster_id": f"cultivation:{record.get('id')}",
        "tags": list(record.get("tags") or row.get("tags", ()) or ()),
        "rarity": _key(record.get("rarity") or row.get("rarity"), "common"),
        "harvest_potential": dict(row.get("harvest_potential", {}) or {}),
        "harvest_limit": harvest_limit,
        "harvest_count": max(0, _safe_int(record.get("harvest_count"), 0)),
        "harvest_remaining": harvest_remaining,
        "fertility_remaining": max(0, _safe_int(record.get("fertility_remaining"), 0)),
        "chemistry_class": _key(record.get("chemistry_class")),
        "parent_chemistry_classes": list(record.get("parent_chemistry_classes", ()) or ()),
        "container_kind": _key(record.get("container_kind"), "ground"),
    })


def _chunk_for_xy_from_record(record):
    try:
        return (int(record.get("x", 0)) // 16, int(record.get("y", 0)) // 16)
    except Exception:
        return (0, 0)


def sync_cultivation_flora_patch(sim, record):
    if not isinstance(record, Mapping):
        return None
    if _key(record.get("container_kind")) == "pot" and record.get("carried_by_eid") is not None:
        _remove_flora_patch(sim, record.get("linked_flora_id"))
        return None
    if record.get("x") is None or record.get("y") is None:
        return None
    flora_record = _flora_record_from_cultivation(record)
    flora_id = register_flora_patch(sim, flora_record)
    if flora_id:
        records = ensure_cultivation_state(sim)
        cid = str(record.get("id") or "").strip()
        if cid in records:
            records[cid]["linked_flora_id"] = flora_id
    return flora_id


def sync_cultivation_from_flora_patch(sim, flora_record):
    if not isinstance(flora_record, Mapping):
        return False
    cid = str(flora_record.get("cultivation_id") or "").strip()
    if not cid:
        return False
    records = ensure_cultivation_state(sim)
    record = records.get(cid)
    if not isinstance(record, dict):
        return False
    for key in ("stage", "harvest_count", "harvest_remaining", "harvest_exhausted", "last_harvest_tick", "exhausted_tick"):
        if key in flora_record:
            record[key] = flora_record[key]
    if _safe_int(record.get("harvest_remaining"), 0) <= 0:
        record["stage"] = "picked"
    records[cid] = record
    return True


def _advance_record(sim, record):
    if not isinstance(record, dict):
        return {}
    stage = _key(record.get("stage"), "seeded")
    if stage in FAILED_STAGES or stage in EXHAUSTED_FLORA_STAGES:
        return record
    if _key(record.get("container_kind")) == "pot" and record.get("carried_by_eid") is not None:
        record["growth_paused"] = True
        record["pause_started_tick"] = _safe_int(record.get("pause_started_tick"), _safe_int(getattr(sim, "tick", 0), 0))
        return record
    now = _safe_int(getattr(sim, "tick", 0), 0)
    planted = _safe_int(record.get("planted_tick"), now)
    paused_total = _safe_int(record.get("paused_ticks"), 0)
    elapsed = max(0, now - planted - paused_total)
    next_stage = "seeded"
    for stage_name, threshold in GROWTH_STAGE_TICKS:
        if elapsed >= threshold:
            next_stage = stage_name
    record["stage"] = next_stage
    record["growth_paused"] = False
    record["mature"] = next_stage == "mature"
    if next_stage == "mature" and not record.get("maturity_tick"):
        record["maturity_tick"] = now
    return record


def advance_cultivation_records(sim):
    changed = False
    records = ensure_cultivation_state(sim)
    for cid, record in list(records.items()):
        if not isinstance(record, dict):
            continue
        before_stage = record.get("stage")
        _advance_record(sim, record)
        records[cid] = record
        if record.get("stage") != before_stage:
            changed = True
        if record.get("x") is not None and record.get("y") is not None:
            sync_cultivation_flora_patch(sim, record)
    return changed


def _biome_fit(sim, source, x, y, z=0):
    row = _plant_row(source.get("plant_id"))
    area_key, district_type = _chunk_area_context(sim, x, y)
    terrain_key = _tile_color_key(sim, x, y, z)
    area_weight = _safe_float((row.get("area_weights") or {}).get(area_key), 0.0)
    terrain_weight = _safe_float((row.get("terrain_weights") or {}).get(terrain_key), 0.0)
    district_weights = row.get("district_weights") or {}
    district_weight = _safe_float(district_weights.get(district_type), 1.0 if not district_type else 0.7)
    score = area_weight * terrain_weight * district_weight
    return {
        "ok": bool(score >= 0.08 and area_weight > 0 and terrain_weight > 0),
        "score": round(float(score), 3),
        "area": area_key,
        "district": district_type,
        "terrain": terrain_key,
    }


def _new_cultivation_record(sim, source, *, container_kind, x=None, y=None, z=0, planter_property_id=None, pot_instance_id=None, carried_by_eid=None, biome_fit=None, stage=None):
    cid = _next_cultivation_id(sim)
    now = _safe_int(getattr(sim, "tick", 0), 0)
    growth_form = _key(source.get("growth_form"), "flower")
    failed = isinstance(biome_fit, Mapping) and not bool(biome_fit.get("ok", True))
    stage = _key(stage, "withering" if failed else "seeded")
    harvest_limit = max(1, flora_harvest_limit({"growth_form": growth_form, "rarity": source.get("rarity")}))
    record = {
        "id": cid,
        "plant_id": source.get("plant_id"),
        "plant_name": source.get("plant_name"),
        "container_kind": _key(container_kind, "ground"),
        "linked_flora_id": _record_flora_id({"id": cid}),
        "linked_planter_property_id": planter_property_id,
        "pot_item_instance_id": pot_instance_id,
        "stage": stage,
        "planted_tick": now,
        "maturity_tick": now + 36 * 600 if not failed else None,
        "biome_fit": dict(biome_fit or {"ok": True}),
        "lineage": dict((source.get("metadata") or {}).get("lineage") or {}),
        "parent_plant_ids": list((source.get("metadata") or {}).get("parent_plant_ids") or ()),
        "hybrid_generation": _safe_int((source.get("metadata") or {}).get("hybrid_generation"), 0),
        "variant_seed": random.Random(f"{getattr(sim, 'seed', 0)}:{cid}:{source.get('plant_id')}").randrange(1, 2**31 - 1),
        "color_key": source.get("color_key"),
        "render_key": source.get("render_key"),
        "glyph": source.get("glyph"),
        "growth_form": growth_form,
        "fertility_remaining": 0 if failed else 2,
        "harvest_limit": harvest_limit,
        "harvest_count": 0,
        "harvest_remaining": 0 if failed else harvest_limit,
        "tended_tick": None,
        "tend_count": 0,
        "tags": list(source.get("tags") or ()),
        "crossbreed_tags": list(source.get("crossbreed_tags") or ()),
        "genetics": dict(source.get("genetics") or {}),
        "chemistry_class": source.get("chemistry_class"),
        "parent_chemistry_classes": list((source.get("metadata") or {}).get("parent_chemistry_classes") or ()),
        "carried_by_eid": carried_by_eid,
        "growth_paused": carried_by_eid is not None,
        "paused_ticks": 0,
        "source_item_id": source.get("item_id"),
        "source_instance_id": source.get("instance_id"),
    }
    if x is not None and y is not None:
        record.update({"x": int(x), "y": int(y), "z": int(z), "chunk": list(_chunk_for_xy(sim, x, y))})
    return record


def _consume_source_item(inventory, source):
    return inventory.remove_item(instance_id=source.get("instance_id"), quantity=1) if inventory else None


def plant_source_in_pot(sim, eid, source, pot_entry):
    inventory = sim.ecs.get(Inventory).get(eid)
    if not inventory:
        return {"ok": False, "reason": "no_inventory"}
    if source.get("growth_form") in NON_POT_GROWTH_FORMS:
        return {"ok": False, "reason": "wrong_container", "container_kind": "pot", "plant_name": source.get("plant_name")}
    if not isinstance(pot_entry, Mapping):
        return {"ok": False, "reason": "no_empty_pot", "plant_name": source.get("plant_name")}
    removed = _consume_source_item(inventory, source)
    if not removed:
        return {"ok": False, "reason": "consume_failed", "plant_name": source.get("plant_name")}
    record = _new_cultivation_record(
        sim,
        source,
        container_kind="pot",
        pot_instance_id=pot_entry.get("instance_id"),
        carried_by_eid=eid,
        biome_fit={"ok": True, "container_override": True},
    )
    records = ensure_cultivation_state(sim)
    records[record["id"]] = record
    metadata = dict(pot_entry.get("metadata") or {}) if isinstance(pot_entry.get("metadata"), Mapping) else {}
    metadata.update({
        "cultivation_id": record["id"],
        "cultivation_record": dict(record),
        "display_name": f"Potted {str(record.get('plant_name') or 'Plant').title()}",
    })
    inventory.update_item_metadata(pot_entry.get("instance_id"), metadata=metadata, replace=True)
    sim.emit(Event(
        "flora_planted",
        eid=eid,
        plant_id=record.get("plant_id"),
        plant_name=record.get("plant_name"),
        cultivation_id=record["id"],
        container_kind="pot",
        consumed_item_id=source.get("item_id"),
        consumed_instance_id=source.get("instance_id"),
    ))
    return {"ok": True, "record": record, "container_kind": "pot", "consumed": removed}


def plant_source_at(sim, eid, source, x, y, z=0, *, container_kind="ground", planter_property_id=None):
    inventory = sim.ecs.get(Inventory).get(eid)
    if not inventory:
        return {"ok": False, "reason": "no_inventory"}
    container_kind = _key(container_kind, "ground")
    if container_kind == "ground" and not _tile_allows_ground_planting(sim, x, y, z):
        return {"ok": False, "reason": "bad_ground", "plant_name": source.get("plant_name")}
    if container_kind == "pot" and source.get("growth_form") in NON_POT_GROWTH_FORMS:
        return {"ok": False, "reason": "wrong_container", "container_kind": "pot", "plant_name": source.get("plant_name")}
    biome_fit = {"ok": True, "container_override": True}
    if container_kind == "ground":
        biome_fit = _biome_fit(sim, source, x, y, z)
    removed = _consume_source_item(inventory, source)
    if not removed:
        return {"ok": False, "reason": "consume_failed", "plant_name": source.get("plant_name")}
    record = _new_cultivation_record(
        sim,
        source,
        container_kind=container_kind,
        x=int(x),
        y=int(y),
        z=int(z),
        planter_property_id=planter_property_id,
        biome_fit=biome_fit,
    )
    records = ensure_cultivation_state(sim)
    records[record["id"]] = record
    sync_cultivation_flora_patch(sim, record)
    sim.emit(Event(
        "flora_planted",
        eid=eid,
        plant_id=record.get("plant_id"),
        plant_name=record.get("plant_name"),
        cultivation_id=record["id"],
        container_kind=container_kind,
        consumed_item_id=source.get("item_id"),
        consumed_instance_id=source.get("instance_id"),
        biome_fit=dict(biome_fit),
        failed=not bool(biome_fit.get("ok", True)),
        x=int(x),
        y=int(y),
        z=int(z),
    ))
    return {"ok": True, "record": record, "container_kind": container_kind, "consumed": removed}


def _planter_at(sim, x, y, z=0):
    for prop in getattr(sim, "properties", {}).values():
        if not isinstance(prop, dict):
            continue
        try:
            if int(prop.get("x", 0) or 0) != int(x) or int(prop.get("y", 0) or 0) != int(y) or int(prop.get("z", 0) or 0) != int(z):
                continue
        except (TypeError, ValueError):
            continue
        fixture = property_fixture_type(prop)
        if "planter" in fixture or _key(prop.get("archetype")) == "planter_box":
            return prop
    return None


def _target_steps(sim, eid, x, y, z):
    preferred = _preferred_direction(sim, eid)
    steps = [(0, -1), (1, 0), (0, 1), (-1, 0), (-1, -1), (1, -1), (1, 1), (-1, 1)]
    if preferred in steps:
        steps = [preferred] + [step for step in steps if step != preferred]
    for dx, dy in steps:
        yield int(x) + dx, int(y) + dy, int(z), (dx, dy)


def _preferred_direction(sim, eid):
    state = getattr(sim, "player_interact_directions", None)
    if isinstance(state, dict):
        row = state.get(int(eid))
        if isinstance(row, Mapping):
            dx = _safe_int(row.get("dx"), 0)
            dy = _safe_int(row.get("dy"), 0)
            if max(abs(dx), abs(dy)) == 1:
                return (dx, dy)
    return None


def _source_is_pollen(source):
    if not isinstance(source, Mapping):
        return False
    if _key(source.get("item_id")) not in POLLEN_ITEM_IDS:
        return False
    metadata = source.get("metadata") if isinstance(source.get("metadata"), Mapping) else {}
    return _key(metadata.get("source")) == "flora" and _key(source.get("plant_id"))


def _flora_live_for_crossbreed(sim, record):
    if not isinstance(record, Mapping):
        return False
    stage = _key(record.get("stage"), "mature")
    if stage in FAILED_STAGES or stage in EXHAUSTED_FLORA_STAGES:
        return False
    if stage not in MATURE_STAGES:
        return False
    return flora_bloom_state(sim, record) in {"open", "night_open"}


def _crossbreed_tags(source_or_record):
    if not isinstance(source_or_record, Mapping):
        return set()
    plant_id = _key(source_or_record.get("plant_id"))
    row = _plant_row(plant_id)
    values = set(_key(token) for token in tuple(row.get("crossbreed_tags", ()) or ()) if _key(token))
    values.update(_key(token) for token in tuple(source_or_record.get("crossbreed_tags", ()) or ()) if _key(token))
    return {value for value in values if value}


def _growth_family(value):
    form = _key(value)
    if form in {"flower", "shrub", "fern"}:
        return "broadleaf"
    if form in {"grass", "reed"}:
        return "blade"
    if form in {"moss", "lichen"}:
        return "moss"
    return form


def _crossbreed_compatible(source, target):
    source_tags = _crossbreed_tags(source)
    target_tags = _crossbreed_tags(target)
    if source_tags and target_tags and source_tags & target_tags:
        return True
    return _growth_family(source.get("growth_form")) == _growth_family(target.get("growth_form"))


def _target_fertility_remaining(record):
    if not isinstance(record, Mapping):
        return 0
    if "fertility_remaining" in record:
        return max(0, _safe_int(record.get("fertility_remaining"), 0))
    return 1


def _update_target_fertility(sim, flora_record, remaining):
    flora_id = str(flora_record.get("id") or "").strip()
    if flora_id and flora_id in getattr(sim, "flora_patches", {}):
        sim.flora_patches[flora_id]["fertility_remaining"] = max(0, int(remaining))
    cid = str(flora_record.get("cultivation_id") or "").strip()
    if cid and cid in ensure_cultivation_state(sim):
        sim.cultivation_records[cid]["fertility_remaining"] = max(0, int(remaining))
        sync_cultivation_flora_patch(sim, sim.cultivation_records[cid])


def _hybrid_seed_metadata(sim, source, target):
    target_plant_id = _key(target.get("plant_id"))
    source_plant_id = _key(source.get("plant_id"))
    target_name = str(target.get("name") or target.get("plant_name") or target_plant_id.replace("_", " ")).strip()
    source_name = str(source.get("plant_name") or source_plant_id.replace("_", " ")).strip()
    prior_gen = max(_safe_int(source.get("hybrid_generation"), 0), _safe_int(target.get("hybrid_generation"), 0))
    generation = min(3, prior_gen + 1)
    signature_source = f"{getattr(sim, 'seed', 0)}:{source_plant_id}:{target_plant_id}:{generation}"
    signature = sha256(signature_source.encode("utf-8")).hexdigest()[:8]
    hybrid_id = f"hybrid_{target_plant_id}_{source_plant_id}_{signature}"[:96]
    target_form = _key(target.get("growth_form"), source.get("growth_form") or "flower")
    source_class = _key(source.get("chemistry_class")) or plant_chemistry_class(sim, source_plant_id)
    target_class = _key(target.get("chemistry_class")) or plant_chemistry_class(sim, target_plant_id)
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:hybrid:{source_plant_id}:{target_plant_id}:{generation}:{signature}")
    colors = [value for value in (source.get("color_key"), target.get("color_key")) if value]
    color_key = rng.choice(colors) if colors else DEFAULT_RENDER_KEY_BY_FORM.get(target_form, "flora_leaf")
    hybrid = {
        "plant_id": hybrid_id,
        "plant_name": f"{target_name} x {source_name}",
        "display_name": f"{target_name.title()} x {source_name.title()} Seed Packet",
        "growth_form": target_form,
        "glyph": str(target.get("glyph") or source.get("glyph") or DEFAULT_GLYPH_BY_FORM.get(target_form, "'"))[:1],
        "render_key": _key(target.get("render_key") or source.get("render_key"), DEFAULT_RENDER_KEY_BY_FORM.get(target_form, "flora_leaf")),
        "color_key": color_key,
        "rarity": _key(target.get("rarity") or source.get("rarity"), "common"),
        "crossbreed_tags": sorted((_crossbreed_tags(source) | _crossbreed_tags(target)))[:6],
        "tags": sorted(set(tuple(source.get("tags", ()) or ())) | set(tuple(target.get("tags", ()) or ())))[:10],
        "genetics": {
            "parents": [target_plant_id, source_plant_id],
            "signature": signature,
        },
        "chemistry_class": rng.choice([value for value in (source_class, target_class) if value] or ["mending"]),
        "parent_chemistry_classes": [value for value in (target_class, source_class) if value],
        "parent_plant_ids": [target_plant_id, source_plant_id],
        "hybrid_generation": generation,
        "hybrid_signature": signature,
        "lineage": {
            "target_parent": target_plant_id,
            "pollen_parent": source_plant_id,
            "generation": generation,
        },
    }
    return seed_packet_metadata(sim, source_kind="hybrid_seed", hybrid=hybrid)


def crossbreed_with_flora(sim, eid, source, target):
    inventory = sim.ecs.get(Inventory).get(eid)
    if not inventory:
        return {"ok": False, "reason": "no_inventory"}
    if not _source_is_pollen(source):
        return {"ok": False, "reason": "not_pollen"}
    if not _flora_live_for_crossbreed(sim, target):
        return {"ok": False, "reason": "target_not_open", "target_name": target.get("name")}
    if not _crossbreed_compatible(source, target):
        return {"ok": False, "reason": "incompatible", "target_name": target.get("name")}
    fertility = _target_fertility_remaining(target)
    if fertility <= 0:
        return {"ok": False, "reason": "spent_fertility", "target_name": target.get("name")}
    seed_metadata = _hybrid_seed_metadata(sim, source, target)
    owner_tag = "player" if int(eid) == int(getattr(sim, "player_eid", -999999)) else "npc"
    if not _inventory_can_accept(inventory, SEED_PACKET_ITEM_ID, 1, metadata=seed_metadata, owner_eid=eid, owner_tag=owner_tag):
        return {"ok": False, "reason": "inventory_full", "target_name": target.get("name")}
    removed = _consume_source_item(inventory, source)
    if not removed:
        return {"ok": False, "reason": "consume_failed", "target_name": target.get("name")}
    added, instance_id = _add_inventory_item(sim, inventory, SEED_PACKET_ITEM_ID, 1, metadata=seed_metadata, owner_eid=eid, owner_tag=owner_tag)
    if not added:
        inventory.add_item(
            removed.get("item_id"),
            quantity=removed.get("quantity", 1),
            stack_max=ITEM_CATALOG.get(removed.get("item_id"), {}).get("stack_max", 1),
            instance_id=removed.get("instance_id"),
            owner_eid=removed.get("owner_eid"),
            owner_tag=removed.get("owner_tag"),
            metadata=removed.get("metadata"),
        )
        return {"ok": False, "reason": "inventory_full", "target_name": target.get("name")}
    _update_target_fertility(sim, target, fertility - 1)
    sim.emit(Event(
        "flora_crossbred",
        eid=eid,
        pollen_plant_id=source.get("plant_id"),
        pollen_plant_name=source.get("plant_name"),
        target_plant_id=target.get("plant_id"),
        target_plant_name=target.get("name") or target.get("plant_name"),
        output_item_id=SEED_PACKET_ITEM_ID,
        output_item_name=item_display_name(SEED_PACKET_ITEM_ID, metadata=seed_metadata, item_catalog=ITEM_CATALOG),
        output_instance_id=instance_id,
        hybrid_generation=seed_metadata.get("hybrid_generation"),
        consumed_item_id=source.get("item_id"),
        consumed_instance_id=source.get("instance_id"),
        x=target.get("x"),
        y=target.get("y"),
        z=target.get("z", 0),
    ))
    return {"ok": True, "metadata": seed_metadata, "instance_id": instance_id, "consumed": removed}


def _adjacent_flora_targets(sim, x, y, z, preferred_steps):
    seen = set()
    for tx, ty, tz, _step in preferred_steps:
        for record in flora_at(sim, tx, ty, tz):
            rid = str(record.get("id") or "")
            if rid and rid not in seen:
                seen.add(rid)
                yield record


def _try_targeted_planting(sim, eid, source, x, y, z):
    steps = list(_target_steps(sim, eid, x, y, z))
    if _source_is_pollen(source):
        for target in _adjacent_flora_targets(sim, x, y, z, steps):
            result = crossbreed_with_flora(sim, eid, source, target)
            if result.get("ok"):
                sim.emit(Event(
                    "item_used",
                    eid=eid,
                    item_id=source.get("item_id"),
                    item_name=item_display_name(source.get("item_id"), metadata=source.get("metadata"), item_catalog=ITEM_CATALOG),
                    usage_kind="flora_crossbreed",
                    reason="cultivation",
                    consumed=True,
                    applied=[],
                    item_metadata=dict(source.get("metadata") or {}),
                ))
                return True
            sim.emit(Event("flora_crossbreed_blocked", eid=eid, plant_name=source.get("plant_name"), reason=result.get("reason"), target_name=result.get("target_name")))
            return False
    for tx, ty, tz, _step in steps:
        planter = _planter_at(sim, tx, ty, tz)
        if planter is None:
            continue
        result = plant_source_at(sim, eid, source, tx, ty, tz, container_kind="planter", planter_property_id=planter.get("id"))
        if result.get("ok"):
            sim.emit(Event(
                "item_used",
                eid=eid,
                item_id=source.get("item_id"),
                item_name=item_display_name(source.get("item_id"), metadata=source.get("metadata"), item_catalog=ITEM_CATALOG),
                usage_kind="flora_plant",
                reason="cultivation",
                consumed=True,
                applied=[],
                item_metadata=dict(source.get("metadata") or {}),
            ))
            return True
        sim.emit(Event("flora_planting_blocked", eid=eid, plant_name=source.get("plant_name"), reason=result.get("reason"), container_kind="planter"))
        return False
    for tx, ty, tz, _step in steps:
        if flora_at(sim, tx, ty, tz):
            continue
        if not _tile_allows_ground_planting(sim, tx, ty, tz):
            continue
        result = plant_source_at(sim, eid, source, tx, ty, tz, container_kind="ground")
        if result.get("ok"):
            sim.emit(Event(
                "item_used",
                eid=eid,
                item_id=source.get("item_id"),
                item_name=item_display_name(source.get("item_id"), metadata=source.get("metadata"), item_catalog=ITEM_CATALOG),
                usage_kind="flora_plant",
                reason="cultivation",
                consumed=True,
                applied=[],
                item_metadata=dict(source.get("metadata") or {}),
            ))
            return True
        sim.emit(Event("flora_planting_blocked", eid=eid, plant_name=source.get("plant_name"), reason=result.get("reason"), container_kind="ground"))
        return False
    return None


def try_use_cultivation_item(sim, eid, entry, x, y, z, *, reason="manual"):
    source = _source_from_entry(sim, entry)
    if source is None:
        return None
    if isinstance(entry, dict) and _key(entry.get("item_id")) == SEED_PACKET_ITEM_ID and isinstance(entry.get("metadata"), dict) and not _key(entry["metadata"].get("source_plant_id")):
        entry["metadata"].update(source["metadata"])
    inventory = sim.ecs.get(Inventory).get(eid)
    pot_entry = _empty_pot_entry(inventory)
    if _preferred_direction(sim, eid) is None and pot_entry is not None:
        result = plant_source_in_pot(sim, eid, source, pot_entry)
        if result.get("ok"):
            sim.emit(Event(
                "item_used",
                eid=eid,
                item_id=source.get("item_id"),
                item_name=item_display_name(source.get("item_id"), metadata=source.get("metadata"), item_catalog=ITEM_CATALOG),
                usage_kind="flora_plant",
                reason=reason,
                consumed=True,
                applied=[],
                item_metadata=dict(source.get("metadata") or {}),
            ))
            return True
        sim.emit(Event("flora_planting_blocked", eid=eid, plant_name=source.get("plant_name"), reason=result.get("reason"), container_kind=result.get("container_kind", "pot")))
        return False
    targeted = _try_targeted_planting(sim, eid, source, x, y, z)
    if targeted is not None:
        return bool(targeted)
    if pot_entry is not None:
        result = plant_source_in_pot(sim, eid, source, pot_entry)
        if result.get("ok"):
            sim.emit(Event(
                "item_used",
                eid=eid,
                item_id=source.get("item_id"),
                item_name=item_display_name(source.get("item_id"), metadata=source.get("metadata"), item_catalog=ITEM_CATALOG),
                usage_kind="flora_plant",
                reason=reason,
                consumed=True,
                applied=[],
                item_metadata=dict(source.get("metadata") or {}),
            ))
            return True
        sim.emit(Event("flora_planting_blocked", eid=eid, plant_name=source.get("plant_name"), reason=result.get("reason"), container_kind=result.get("container_kind", "pot")))
        return False
    sim.emit(Event("flora_planting_blocked", eid=eid, plant_name=source.get("plant_name"), reason="no_target"))
    return False


def sync_pot_ground_state(sim, ground):
    if not isinstance(ground, Mapping) or _key(ground.get("item_id")) != PLANT_POT_ITEM_ID:
        return False
    metadata = ground.get("metadata") if isinstance(ground.get("metadata"), Mapping) else {}
    cid = str(metadata.get("cultivation_id") or "").strip()
    if not cid:
        return False
    records = ensure_cultivation_state(sim)
    record = records.get(cid)
    if not isinstance(record, dict):
        record = dict(metadata.get("cultivation_record") or {})
        if not record:
            return False
    if record.get("growth_paused") and record.get("pause_started_tick") is not None:
        paused = max(0, _safe_int(getattr(sim, "tick", 0), 0) - _safe_int(record.get("pause_started_tick"), 0))
        record["paused_ticks"] = _safe_int(record.get("paused_ticks"), 0) + paused
    record.update({
        "id": cid,
        "container_kind": "pot",
        "pot_item_instance_id": ground.get("instance_id"),
        "ground_item_id": ground.get("ground_item_id"),
        "x": _safe_int(ground.get("x"), 0),
        "y": _safe_int(ground.get("y"), 0),
        "z": _safe_int(ground.get("z"), 0),
        "chunk": list(_chunk_for_xy(sim, ground.get("x", 0), ground.get("y", 0))),
        "carried_by_eid": None,
        "growth_paused": False,
        "pause_started_tick": None,
    })
    records[cid] = record
    sync_cultivation_flora_patch(sim, record)
    ground_metadata = dict(metadata)
    ground_metadata["cultivation_record"] = dict(record)
    ground_metadata["display_name"] = f"Potted {str(record.get('plant_name') or 'Plant').title()}"
    ground["metadata"] = ground_metadata
    return True


def sync_pot_inventory_state(sim, eid, entry):
    if not isinstance(entry, Mapping) or _key(entry.get("item_id")) != PLANT_POT_ITEM_ID:
        return False
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}
    cid = str(metadata.get("cultivation_id") or "").strip()
    if not cid:
        return False
    records = ensure_cultivation_state(sim)
    record = records.get(cid)
    if not isinstance(record, dict):
        record = dict(metadata.get("cultivation_record") or {})
        if not record:
            return False
    record.update({
        "id": cid,
        "container_kind": "pot",
        "pot_item_instance_id": entry.get("instance_id"),
        "ground_item_id": None,
        "x": None,
        "y": None,
        "z": None,
        "carried_by_eid": eid,
        "growth_paused": True,
        "pause_started_tick": _safe_int(getattr(sim, "tick", 0), 0),
    })
    records[cid] = record
    _remove_flora_patch(sim, record.get("linked_flora_id"))
    if isinstance(entry, dict):
        updated = dict(metadata)
        updated["cultivation_id"] = cid
        updated["cultivation_record"] = dict(record)
        updated["display_name"] = f"Potted {str(record.get('plant_name') or 'Plant').title()}"
        entry["metadata"] = updated
    return True


def npc_try_gardener_action(sim, eid):
    pos = sim.ecs.get(Position).get(eid)
    ai = sim.ecs.get(AI).get(eid)
    if pos is None or ai is None:
        return False
    role = _key(getattr(ai, "role", ""))
    if role not in GARDENER_ROLES:
        return False
    ensure_cultivation_state(sim)
    cooldowns = getattr(sim, "cultivation_gardener_cooldowns", {})
    if not isinstance(cooldowns, dict):
        sim.cultivation_gardener_cooldowns = {}
        cooldowns = sim.cultivation_gardener_cooldowns
    actor_key = _actor_key(eid)
    now = _safe_int(getattr(sim, "tick", 0), 0)
    if _safe_int(cooldowns.get(actor_key), 0) > now:
        return False
    chunk = _chunk_for_xy(sim, pos.x, pos.y)
    chunk_count = sum(
        1
        for record in ensure_cultivation_state(sim).values()
        if isinstance(record, Mapping) and tuple(record.get("chunk") or ()) == tuple(chunk)
    )
    if chunk_count >= 4:
        cooldowns[actor_key] = now + 2400
        return False
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:npc-gardener:{eid}:{chunk}:{now // 2400}")
    catalog = load_flora_catalog()
    plant = rng.choice(tuple(catalog.values()))
    source = _source_from_entry(sim, {
        "item_id": SEED_PACKET_ITEM_ID,
        "instance_id": f"npc-starter:{eid}:{now}",
        "metadata": seed_packet_metadata(sim, plant_id=plant["id"], seed_token=f"npc:{eid}:{now}", source_kind="npc_starter"),
    })
    if not source:
        return False
    steps = list(_target_steps(sim, eid, pos.x, pos.y, pos.z))
    rng.shuffle(steps)
    inventory = sim.ecs.get(Inventory).get(eid)
    if inventory is None:
        sim.ecs.add(eid, Inventory(capacity=6))
        inventory = sim.ecs.get(Inventory).get(eid)
    added, instance_id = _add_inventory_item(sim, inventory, SEED_PACKET_ITEM_ID, 1, metadata=source["metadata"], owner_eid=eid, owner_tag="npc")
    if not added:
        cooldowns[actor_key] = now + 2400
        return False
    source = dict(source, instance_id=instance_id)
    for tx, ty, tz, _step in steps:
        planter = _planter_at(sim, tx, ty, tz)
        if planter is not None:
            result = plant_source_at(sim, eid, source, tx, ty, tz, container_kind="planter", planter_property_id=planter.get("id"))
            if result.get("ok"):
                cooldowns[actor_key] = now + 3600
                return True
        if _tile_allows_ground_planting(sim, tx, ty, tz) and not flora_at(sim, tx, ty, tz):
            result = plant_source_at(sim, eid, source, tx, ty, tz, container_kind="ground")
            if result.get("ok"):
                cooldowns[actor_key] = now + 3600
                return True
    inventory.remove_item(instance_id=instance_id, quantity=1)
    cooldowns[actor_key] = now + 2400
    return False


class CultivationSystem(System):
    def __init__(self, sim):
        super().__init__(sim)
        ensure_cultivation_state(sim)
        self.sim.events.subscribe("item_dropped", self.on_item_dropped)
        self.sim.events.subscribe("item_picked_up", self.on_item_picked_up)

    def on_item_dropped(self, event):
        ground_id = str(event.data.get("ground_item_id") or "").strip()
        ground = getattr(self.sim, "ground_items", {}).get(ground_id)
        if sync_pot_ground_state(self.sim, ground):
            self.sim.emit(Event(
                "potted_plant_placed",
                eid=event.data.get("eid"),
                ground_item_id=ground_id,
                item_id=PLANT_POT_ITEM_ID,
                item_name=item_display_name(PLANT_POT_ITEM_ID, metadata=ground.get("metadata"), item_catalog=ITEM_CATALOG),
                x=ground.get("x"),
                y=ground.get("y"),
                z=ground.get("z", 0),
            ))

    def on_item_picked_up(self, event):
        eid = event.data.get("eid")
        inventory = self.sim.ecs.get(Inventory).get(eid)
        if inventory is None:
            return
        entry = inventory.find(instance_id=event.data.get("instance_id"))
        if sync_pot_inventory_state(self.sim, eid, entry):
            self.sim.emit(Event(
                "potted_plant_picked_up",
                eid=eid,
                item_id=PLANT_POT_ITEM_ID,
                item_name=item_display_name(PLANT_POT_ITEM_ID, metadata=entry.get("metadata"), item_catalog=ITEM_CATALOG),
            ))

    def update(self):
        advance_cultivation_records(self.sim)
        now = _safe_int(getattr(self.sim, "tick", 0), 0)
        if now % 120 != 0:
            return
        for eid in tuple(self.sim.ecs.get(AI).keys())[:80]:
            npc_try_gardener_action(self.sim, eid)
